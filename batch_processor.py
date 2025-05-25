import pandas as pd
import streamlit as st # st要素はワーカー内では直接使用しない方が良いが、型ヒント等で残る場合あり
from io import BytesIO
import zipfile
import os
import time
# from functools import partial # 今回の修正では直接使わない
import multiprocessing # ProcessPoolExecutor を使うのであればこちら
# from concurrent.futures import ProcessPoolExecutor, as_completed # ProcessPoolExecutor を使う場合
import tempfile
import gc
import psutil
import logging # logging をインポート
import traceback # traceback をインポート

# --- 既存のインポート ---
from forecast import generate_filtered_summaries, create_forecast_dataframe
from pdf_generator import create_pdf, create_landscape_pdf, register_fonts, get_chart_cache, MATPLOTLIB_FONT_NAME, REPORTLAB_FONT_NAME

# ロガーのセットアップ (モジュールのトップレベルで行う)
logger = logging.getLogger(__name__)
# Streamlit Cloudのログにも出力されるように、基本的な設定を行う
# (メインのapp.pyでも設定している場合は、そちらの設定が優先されるか、二重に出力される可能性に注意)
if not logger.hasHandlers(): # ハンドラが重複しないように
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    )

# register_fonts() # メインアプリのエントリーポイントで呼ぶのが一般的

def process_pdf_in_worker_revised(
    task_id, # タスク識別用のIDを追加
    df_path, filter_type, filter_value, display_name, latest_date_str, landscape,
    target_data_path=None, reduced_graphs=True,
    ):
    """
    ワーカープロセスでPDFを生成する (エラーハンドリングとロギング強化版)
    """
    pid = os.getpid()
    process_start_time = time.time()
    start_mem_mb = psutil.Process(pid).memory_info().rss / (1024 * 1024)
    logger.info(f"PID {pid}, タスクID {task_id}: 開始 - {display_name}. 初期メモリ: {start_mem_mb:.2f} MB")

    try:
        df = pd.read_feather(df_path)
        latest_date = pd.Timestamp(latest_date_str)

        target_data = None
        if target_data_path and os.path.exists(target_data_path):
            target_data = pd.read_feather(target_data_path)

        # (略: current_chart_data, current_filter_column, current_filter_code, title_prefix_worker の準備)
        # ... (以前のコードから流用、ただし title_prefix_worker は display_name を使う)
        if filter_type == "all":
            current_chart_data = df.copy() # df全体をコピー
            current_filter_column = None
            current_filter_code = "全体"
            title_prefix_worker = display_name # "全体"
        elif filter_type == "dept":
            current_chart_data = df[df["診療科名"] == filter_value].copy()
            current_filter_column = "診療科名"
            current_filter_code = filter_value
            title_prefix_worker = display_name
        elif filter_type == "ward":
            current_chart_data = df[df["病棟コード"] == str(filter_value)].copy() # filter_valueを文字列に
            current_filter_column = "病棟コード"
            current_filter_code = str(filter_value)
            title_prefix_worker = display_name
        else:
            logger.error(f"PID {pid}, タスクID {task_id}: 未知のfilter_type: {filter_type} for {display_name}")
            return {"task_id": task_id, "name": display_name, "data": None, "error": f"未知のfilter_type: {filter_type}", "success": False}


        if current_chart_data.empty and filter_type != "all":
            logger.warning(f"PID {pid}, タスクID {task_id}: フィルタリング後のデータが空です for {display_name} (タイプ: {filter_type}, 値: {filter_value})。スキップします。")
            return {"task_id": task_id, "name": display_name, "data": None, "error": "Filtered data is empty", "success": False}

        summaries = generate_filtered_summaries(current_chart_data, current_filter_column, filter_value if filter_type != "all" else None)
        
        # 修正箇所: summaries の内容をより安全にチェック
        summaries_valid = False
        if isinstance(summaries, dict):
            weekday_summary = summaries.get("weekday")
            holiday_summary = summaries.get("holiday")
            # "weekday" と "holiday" が存在し、かつDataFrameであり、空でないことを確認
            if (weekday_summary is not None and isinstance(weekday_summary, pd.DataFrame) and not weekday_summary.empty and
                holiday_summary is not None and isinstance(holiday_summary, pd.DataFrame) and not holiday_summary.empty):
                summaries_valid = True
            # もし Series の場合も考慮するなら (forecast.py の実装による)
            elif (weekday_summary is not None and isinstance(weekday_summary, pd.Series) and not weekday_summary.empty and
                  holiday_summary is not None and isinstance(holiday_summary, pd.Series) and not holiday_summary.empty and
                  "入院患者数（在院）" in weekday_summary and "入院患者数（在院）" in holiday_summary): # Seriesの場合、必要なキーが存在するか確認
                   summaries_valid = True


        if not summaries_valid: # 修正後の判定
            logger.error(f"PID {pid}, タスクID {task_id}: サマリー生成に失敗または必要なキー/データが不足 for {display_name}. Summaries content: {type(summaries)}")
            if isinstance(summaries, dict):
                logger.debug(f"Summaries keys: {summaries.keys()}")
                if "weekday" in summaries:
                    logger.debug(f"Type of summaries['weekday']: {type(summaries.get('weekday'))}, Empty: {summaries.get('weekday').empty if isinstance(summaries.get('weekday'), (pd.DataFrame, pd.Series)) else 'N/A'}")
                if "holiday" in summaries:
                    logger.debug(f"Type of summaries['holiday']: {type(summaries.get('holiday'))}, Empty: {summaries.get('holiday').empty if isinstance(summaries.get('holiday'), (pd.DataFrame, pd.Series)) else 'N/A'}")
            return {"task_id": task_id, "name": display_name, "data": None, "error": "Failed to generate summaries or essential summary data is missing/empty", "success": False}

        # create_forecast_dataframe の呼び出しとエラーチェックも同様に強化
        # forecast_df_worker = create_forecast_dataframe(summaries["weekday"], summaries["holiday"], latest_date)
        # の前に summaries["weekday"] と summaries["holiday"] が適切なDataFrameであることを確認
        if not (isinstance(summaries.get("weekday"), (pd.DataFrame, pd.Series)) and not summaries.get("weekday").empty and
                isinstance(summaries.get("holiday"), (pd.DataFrame, pd.Series)) and not summaries.get("holiday").empty):
            logger.error(f"PID {pid}, タスクID {task_id}: forecast_df生成に必要なweekday/holidayデータが不適切 for {display_name}.")
            return {"task_id": task_id, "name": display_name, "data": None, "error": "Weekday/holiday summary data for forecast is invalid or empty", "success": False}

        forecast_df_worker = create_forecast_dataframe(summaries["weekday"], summaries["holiday"], latest_date)
        graph_days_worker = [90] if reduced_graphs else [90, 180]
        logger.info(f"PID {pid}, タスクID {task_id}: graph_days_worker set to {graph_days_worker} based on reduced_graphs={reduced_graphs}")

        alos_chart_buffers = {}
        try:
            from pdf_generator import create_alos_chart_for_pdf # 念のため再インポート
            # graph_days_worker が上で定義されているので、ここで NameError は起きないはず
            for days_val in graph_days_worker:
                alos_buffer = create_alos_chart_for_pdf(
                    current_chart_data,
                    title_prefix_worker,
                    latest_date,
                    30,
                    MATPLOTLIB_FONT_NAME,
                    days_to_show=days_val
                )
                if alos_buffer:
                    alos_chart_buffers[str(days_val)] = alos_buffer
                    logger.info(f"PID {pid}, タスクID {task_id}: ALOSチャート ({days_val}日) 生成完了 for {display_name}")
        except Exception as chart_exc:
            logger.error(f"PID {pid}, タスクID {task_id}: ALOSチャート生成中にエラー for {display_name}: {chart_exc}", exc_info=True)

        # landscape や create_pdf/create_landscape_pdf の呼び出し時にも graph_days=graph_days_worker となっていることを確認
        if landscape:
            pdf_bytes_io = create_landscape_pdf(
                forecast_df=forecast_df_worker,
                df_weekday=summaries["weekday"],
                df_holiday=summaries["holiday"],
                df_all_avg=summaries.get("summary"),
                chart_data=current_chart_data,
                title_prefix=title_prefix_worker,
                latest_date=latest_date,
                target_data=target_data,
                filter_code=current_filter_code,
                graph_days=graph_days_worker, # 正しく参照
                alos_chart_buffer=alos_chart_buffers if alos_chart_buffers else None
            )
        else:
            pdf_bytes_io = create_pdf(
                forecast_df=forecast_df_worker,
                df_weekday=summaries["weekday"],
                df_holiday=summaries["holiday"],
                df_all_avg=summaries.get("summary"),
                chart_data=current_chart_data,
                title_prefix=title_prefix_worker,
                latest_date=latest_date,
                target_data=target_data,
                filter_code=current_filter_code,
                graph_days=graph_days_worker, # 正しく参照
                alos_chart_buffer=alos_chart_buffers if alos_chart_buffers else None
            )

        del df, current_chart_data, summaries, forecast_df_worker, alos_chart_buffers
        gc.collect()

        process_end_time = time.time()
        end_mem_mb = psutil.Process(pid).memory_info().rss / (1024 * 1024)
        duration = process_end_time - process_start_time
        mem_change = end_mem_mb - start_mem_mb

        if pdf_bytes_io and pdf_bytes_io.getbuffer().nbytes > 0:
            logger.info(f"PID {pid}, タスクID {task_id}: 成功 - {display_name}. 時間: {duration:.2f}s. メモリ: {end_mem_mb:.2f}MB (変化: {mem_change:+.2f}MB)")
            return {"task_id": task_id, "name": display_name, "data": pdf_bytes_io.getvalue(), "error": None, "success": True} # バイト列を返す
        else:
            logger.warning(f"PID {pid}, タスクID {task_id}: 生成されたPDFデータが空です for {display_name}. 時間: {duration:.2f}s. メモリ: {end_mem_mb:.2f}MB (変化: {mem_change:+.2f}MB)")
            return {"task_id": task_id, "name": display_name, "data": None, "error": "Generated PDF data is empty", "success": False}

    except Exception as e:
        pid = os.getpid() # エラー時にもpidを取得
        end_mem_mb = psutil.Process(pid).memory_info().rss / (1024 * 1024)
        error_message = f"PID {pid}, タスクID {task_id}: ワーカー処理中に致命的なエラー for {display_name}: {str(e)}"
        logger.error(error_message, exc_info=True)
        logger.error(f"スタックトレース for {display_name}:\n{traceback.format_exc()}")
        return {"task_id": task_id, "name": display_name, "data": None, "error": error_message, "success": False}

def batch_generate_pdfs_mp_optimized(df, mode="all", landscape=False, target_data=None,
                                    progress_callback=None, max_workers=None, fast_mode=True):
    """最適化された一括PDF生成処理 (マルチプロセス) - エラーハンドリング強化"""
    batch_start_time = time.time()
    overall_success_count = 0
    overall_failure_count = 0
    failed_pdf_details = [] # 失敗したPDFの詳細を格納するリスト

    # (略: register_fonts, データ準備, latest_date_obj の取得, tasks_to_run の作成, max_workers の決定)
    # ... (前回と同様のコード) ...
    # register_fonts() # app.pyのメインで一度呼ぶことを推奨

    if progress_callback: progress_callback(5, "データを一時ファイルに保存中...")
    temp_dir = tempfile.mkdtemp()
    df_path = os.path.join(temp_dir, "main_data.feather")
    df.reset_index(drop=True).to_feather(df_path)
    logger.info(f"メインデータをFeather形式で保存: {df_path}")

    target_data_path = None
    if target_data is not None and not target_data.empty:
        target_data_path = os.path.join(temp_dir, "target_data.feather")
        target_data.reset_index(drop=True).to_feather(target_data_path)
        logger.info(f"目標値をFeather形式で保存: {target_data_path}")

    all_summaries_for_date = generate_filtered_summaries(df)
    if not all_summaries_for_date or "latest_date" not in all_summaries_for_date:
        latest_date_obj = pd.Timestamp.now().normalize()
        logger.warning("全体の最新日付を決定できませんでした。現在の日付を使用します。")
    else:
        latest_date_obj = all_summaries_for_date["latest_date"]
    logger.info(f"PDF生成の基準日: {latest_date_obj.isoformat()}")

    if progress_callback: progress_callback(10, "PDF生成タスクを準備中...")
    tasks_to_run = []
    ward_name_mapping = {} # Ward name mapping logic from previous version
    if target_data is not None and not target_data.empty and '部門コード' in target_data.columns and '部門名' in target_data.columns:
        for _, row in target_data.iterrows():
            if pd.notna(row['部門コード']) and pd.notna(row['部門名']):
                ward_name_mapping[str(row['部門コード'])] = row['部門名']
    import re
    for ward_code_iter in df["病棟コード"].astype(str).unique(): # Use a different variable name
        if ward_code_iter not in ward_name_mapping:
            match = re.match(r'0*(\d+)([A-Za-z]*)', ward_code_iter)
            if match: num_part, alpha_part = match.group(1), match.group(2); ward_name_mapping[ward_code_iter] = f"{num_part}{alpha_part}病棟"
            else: ward_name_mapping[ward_code_iter] = ward_code_iter

    if mode == "all_only_filter": tasks_to_run.append(("all", "全体", "全体"))
    else:
        if mode == "all": tasks_to_run.append(("all", "全体", "全体"))
        if mode == "all" or mode == "dept":
            departments = sorted(df["診療科名"].unique())
            for dept in departments: tasks_to_run.append(("dept", dept, dept))
        if mode == "all" or mode == "ward":
            wards = sorted(df["病棟コード"].astype(str).unique())
            for ward in wards: tasks_to_run.append(("ward", ward, ward_name_mapping.get(ward, ward)))

    total_tasks_count = len(tasks_to_run)
    if total_tasks_count == 0:
        logger.warning("生成するPDFタスクがありません。")
        if progress_callback: progress_callback(100, "対象なし")
        return BytesIO(), [] # 空のBytesIOと空の失敗リスト

    if progress_callback: progress_callback(15, f"タスク準備完了 (合計: {total_tasks_count}件)")

    if max_workers is None:
        cpu_cores = multiprocessing.cpu_count()
        max_workers = max(1, min(cpu_cores - 1 if cpu_cores > 1 else 1, 2)) # デフォルトを2に維持
    logger.info(f"PDF生成開始 (マルチプロセス): ワーカー数={max_workers}, タスク数={total_tasks_count}, 高速モード={fast_mode}")

    zip_buffer_mp = BytesIO()
    with zipfile.ZipFile(zip_buffer_mp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf_mp:
        date_suffix = latest_date_obj.strftime("%Y%m%d")
        worker_args_list = [] # 引数リストを事前に作成

        for i, (task_type, task_val, task_display_name) in enumerate(tasks_to_run):
            worker_args_list.append(
                (f"task_{i}", df_path, task_type, task_val, task_display_name, latest_date_obj.isoformat(), landscape, target_data_path, fast_mode)
            )

        # ProcessPoolExecutor を使用
        # Streamlit Cloudの環境によっては、ThreadPoolExecutorの方が安定する場合もあるので注意
        # with ProcessPoolExecutor(max_workers=max_workers) as pool:
        #    results_mp = pool.starmap(process_pdf_in_worker_revised, worker_args_list)
        # ワーカ数を2にしたら動いたとのことなので、ProcessPoolExecutorを試す価値はあるが、
        # もしそれで不安定ならThreadPoolExecutorに戻す。
        # ここでは、より安全そうなThreadPoolExecutor（またはシングルプロセス）を推奨
        # ※ ただし、multiprocessing.Pool().starmap がログにあったので ProcessPoolExecutor を試してみる

        results_mp = []
        if total_tasks_count > 0 : # タスクがある場合のみ実行
            try:
                # マルチプロセッシングプールの作成
                # `get_context("spawn")` は、特に macOS や Windows での安定性を高めることがあります。
                # Linux環境であるStreamlit Cloudではデフォルトの "fork" でも問題ないことが多いですが、
                # 状況によっては "spawn" や "forkserver" を試す価値があります。
                # ctx = multiprocessing.get_context("spawn")
                # with ctx.Pool(processes=max_workers) as pool:
                with multiprocessing.Pool(processes=max_workers) as pool: # Streamlit Cloudのログに合わせる
                    results_mp = pool.starmap(process_pdf_in_worker_revised, worker_args_list)
            except Exception as pool_exc:
                logger.error(f"プロセスプール実行中にエラー: {pool_exc}", exc_info=True)
                if progress_callback: progress_callback(100, f"プールエラー: {str(pool_exc)}")
                # プール自体が失敗した場合、全タスクを失敗として扱うか、部分的な結果を返すか検討
                # ここでは空のZIPとエラー情報を返す
                failed_pdf_details = [{"name": args[4], "reason": f"プロセスプールエラー: {str(pool_exc)}"} for args in worker_args_list]
                return BytesIO(), failed_pdf_details


        completed_task_count_for_progress = 0
        for result_item in results_mp: # starmap は結果を順序通り返す
            completed_task_count_for_progress += 1
            if result_item and result_item.get("success"):
                pdf_title = result_item["name"]
                pdf_content_bytes_val = result_item["data"] # getvalue()は不要、バイト列が直接返る想定
                
                if pdf_content_bytes_val and len(pdf_content_bytes_val) > 0:
                    safe_filename_prefix = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in pdf_title)
                    folder_name = ""
                    if "診療科別" in pdf_title: folder_name = "診療科別/"
                    elif "病棟別" in pdf_title: folder_name = "病棟別/"
                    pdf_filename = f"{folder_name}入院患者数予測_{safe_filename_prefix}_{date_suffix}.pdf"
                    zipf_mp.writestr(pdf_filename, pdf_content_bytes_val)
                    overall_success_count += 1
                else:
                    logger.warning(f"タスクID {result_item.get('task_id')}: {pdf_title} のPDF内容は空でした（zipに追加せず）。")
                    overall_failure_count += 1
                    failed_pdf_details.append({"name": pdf_title, "reason": result_item.get("error", "PDF内容が空")})
            elif result_item: # エラーがあった場合
                overall_failure_count += 1
                failed_pdf_details.append({"name": result_item.get("name", "不明なタスク"), "reason": result_item.get("error", "不明なエラー")})
            else: # result_itemがNoneなどの予期せぬケース
                logger.error(f"予期せぬ結果がワーカーから返されました: {result_item}")
                overall_failure_count += 1
                failed_pdf_details.append({"name": "不明なタスク（結果不正）", "reason": "ワーカーからの結果が不正"})


            if progress_callback and total_tasks_count > 0:
                current_prog = int(15 + (completed_task_count_for_progress / total_tasks_count) * 85)
                progress_callback(min(100, current_prog), f"PDF生成中: {completed_task_count_for_progress}/{total_tasks_count} 処理完了")

    # (略: batch_end_time, total_batch_time, ログ出力, ZIPバッファ返却)
    # ... (前回と同様のコード) ...
    batch_end_time = time.time()
    total_batch_time = batch_end_time - batch_start_time
    logger.info(f"PDF一括生成完了: 成功 {overall_success_count}/{total_tasks_count}, 失敗 {overall_failure_count}/{total_tasks_count}, 処理時間: {total_batch_time:.1f}秒")
    if progress_callback: progress_callback(100, f"全処理完了! (成功 {overall_success_count}件, 失敗 {overall_failure_count}件) 所要時間: {total_batch_time:.1f}秒")

    zip_buffer_mp.seek(0)
    # 一時ファイルのクリーンアップ
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"一時ディレクトリ {temp_dir} を削除しました。")
    except Exception as e_clean:
        logger.error(f"一時ファイルの削除に失敗しました: {e_clean}")

    return zip_buffer_mp, failed_pdf_details # 失敗情報も返す



def batch_generate_pdfs_full_optimized(
    df, mode="all", landscape=False, target_data=None, 
    progress_callback=None, use_parallel=True, max_workers=None, fast_mode=True # fast_mode を追加
    ):
    """
    指定されたモードでPDFを一括生成し、ZIPファイルで返す（メイン呼び出し関数）
    """
    # register_fonts() # アプリのメインエントリーポイントで一度だけ呼ぶのが理想

    if df is None or df.empty:
        if progress_callback: progress_callback(0, "データがありません。")
        st.warning("分析対象のデータフレームが空です。")
        return BytesIO()

    if progress_callback: progress_callback(0, "処理開始...")
    
    # 実際の処理の呼び出し (並列処理の有無をここで分岐しても良い)
    if use_parallel:
        print(f"Starting batch PDF generation with parallel processing. Mode: {mode}, Landscape: {landscape}, Max Workers: {max_workers}, Fast Mode: {fast_mode}")
        return batch_generate_pdfs_mp_optimized(df, mode, landscape, target_data, progress_callback, max_workers, fast_mode)
    else:
        # シングルプロセス版の処理 (もし必要なら別途実装)
        # ここではマルチプロセス版のみを最適化対象としているため、シングルプロセス版は省略。
        # シングルプロセス版が必要な場合は、process_pdf_in_worker_revised をループで呼び出す形になる。
        print("Parallel processing disabled. Falling back to sequential (not fully implemented here).")
        st.warning("シングルプロセスでの一括生成は現在実装されていません。並列処理を有効にしてください。")
        if progress_callback: progress_callback(100, "シングルプロセス未実装")
        return BytesIO()