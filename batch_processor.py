import pandas as pd
import streamlit as st
from io import BytesIO
import zipfile
import os
import time
from functools import partial
import multiprocessing
import tempfile # prepare_data_for_multiprocessing で使用
import gc
import psutil
from forecast import generate_filtered_summaries, create_forecast_dataframe # これらは既存と仮定
# pdf_generator の関数をインポート (修正後のもの)
from pdf_generator import create_pdf, create_landscape_pdf, register_fonts, get_chart_cache, MATPLOTLIB_FONT_NAME, REPORTLAB_FONT_NAME

# グローバルな chart_cache は pdf_generator.py 側で st.session_state を使うため、ここでは不要。
# ただし、マルチプロセスワーカーからは st.session_state に直接アクセスできない点に注意。
# ワーカー内でのキャッシュが必要な場合は、異なるメカニズムが必要。
# register_fonts() # ここで呼ぶか、メインアプリで一度呼ぶ

def process_pdf_in_worker_revised(
    df_path, filter_type, filter_value, display_name, latest_date_str, landscape,
    target_data_path=None, reduced_graphs=True,
    ):
    """
    ワーカープロセスでPDFを生成する (改訂版)
    """
    try:
        pid = os.getpid()
        process_start_time = time.time()

        df = pd.read_feather(df_path)
        latest_date = pd.Timestamp(latest_date_str)
        
        target_data = None
        if target_data_path and os.path.exists(target_data_path):
            target_data = pd.read_feather(target_data_path)
        
        if filter_type == "all":
            current_chart_data = df
            current_filter_column = None
            current_filter_code = "全体"
            title_prefix_worker = "全体"
        elif filter_type == "dept":
            current_chart_data = df[df["診療科名"] == filter_value].copy()
            current_filter_column = "診療科名"
            current_filter_code = filter_value
            title_prefix_worker = f"診療科別 {display_name}"  # display_nameを使用
        elif filter_type == "ward":
            current_chart_data = df[df["病棟コード"] == filter_value].copy()
            current_filter_column = "病棟コード"
            current_filter_code = str(filter_value)
            title_prefix_worker = f"病棟別 {display_name}"  # display_nameを使用
        else:
            return None

        if current_chart_data.empty and filter_type != "all":
            print(f"PID {pid}: Filtered data empty for {title_prefix_worker}. Skipping.")
            return None
            
        # generate_filtered_summaries はフィルタリングされたデータ(current_chart_data)を期待する
        summaries = generate_filtered_summaries(current_chart_data, current_filter_column, filter_value if filter_type != "all" else None)
        
        if not summaries:
            print(f"PID {pid}: Failed to generate summaries for {title_prefix_worker}.")
            return None

        forecast_df_worker = create_forecast_dataframe(summaries["weekday"], summaries["holiday"], latest_date)
        graph_days_worker = [90] if reduced_graphs else [90, 180]

        # 平均在院日数グラフを生成（90日と180日の両方）
        alos_chart_buffers = {}
        graph_days_worker = [90] if reduced_graphs else [90, 180]
        
        try:
            from pdf_generator import create_alos_chart_for_pdf
            for days_val in graph_days_worker:
                alos_buffer = create_alos_chart_for_pdf(
                    current_chart_data, 
                    title_prefix_worker, 
                    latest_date, 
                    30,  # 直近30日の移動平均
                    MATPLOTLIB_FONT_NAME,
                    days_to_show=days_val  # 表示期間
                )
                if alos_buffer:
                    alos_chart_buffers[str(days_val)] = alos_buffer
                    print(f"ALOS Chart ({days_val}日) generated for {title_prefix_worker}")
        except (ImportError, Exception) as e:
            print(f"PID {pid}: Failed to generate ALOS charts: {e}")

        # pdf_generator 内の create_pdf / create_landscape_pdf を使用
        # alos_chart_bufferパラメータを追加
        if landscape:
            pdf_bytes = create_landscape_pdf(
                forecast_df=forecast_df_worker,
                df_weekday=summaries["weekday"],
                df_holiday=summaries["holiday"],
                df_all_avg=summaries.get("summary"), 
                chart_data=current_chart_data, 
                title_prefix=title_prefix_worker,
                latest_date=latest_date,
                target_data=target_data,
                filter_code=current_filter_code,
                graph_days=graph_days_worker,
                alos_chart_buffer=alos_chart_buffers if alos_chart_buffers else None  # この行を追加
            )
        else:
            pdf_bytes = create_pdf(
                forecast_df=forecast_df_worker,
                df_weekday=summaries["weekday"],
                df_holiday=summaries["holiday"],
                df_all_avg=summaries.get("summary"),
                chart_data=current_chart_data,
                title_prefix=title_prefix_worker,
                latest_date=latest_date,
                target_data=target_data,
                filter_code=current_filter_code,
                graph_days=graph_days_worker,
                alos_chart_buffer=alos_chart_buffers if alos_chart_buffers else None  # この行を追加
            )
        
        del df, current_chart_data, summaries, forecast_df_worker
        gc.collect()
        
        process_end_time = time.time()
        # print(f"PID {pid}: PDF for {title_prefix_worker} generated in {process_end_time - process_start_time:.2f}s")
        return (title_prefix_worker, pdf_bytes) if pdf_bytes else None

    except Exception as e:
        print(f"PID {os.getpid()}: Error in worker for {filter_type} {filter_value}: {e}")
        import traceback
        print(traceback.format_exc())
        return None

def batch_generate_pdfs_mp_optimized(df, mode="all", landscape=False, target_data=None, 
                                    progress_callback=None, max_workers=None, fast_mode=True): # fast_mode追加
    """最適化された一括PDF生成処理 (マルチプロセス)"""
    batch_start_time = time.time()
    
    # register_fonts() # メインプロセスでフォント登録を保証 (ワーカーでもインポート時に実行されるはず)

    if progress_callback: progress_callback(5, "データを準備中...")

    # マルチプロセス用にデータ準備 (Feather)
    temp_dir = tempfile.mkdtemp()
    
    # 病棟コードから表示名へのマッピングを作成
    ward_name_mapping = {}
    
    # 1. target_dataに部門名が含まれている場合はそれを使用
    if target_data is not None and not target_data.empty and '部門コード' in target_data.columns and '部門名' in target_data.columns:
        for _, row in target_data.iterrows():
            if pd.notna(row['部門コード']) and pd.notna(row['部門名']):
                ward_name_mapping[str(row['部門コード'])] = row['部門名']
    
    # 2. コードからデフォルト名を生成（例: 03A → 3A病棟）
    import re
    for ward_code in df["病棟コード"].astype(str).unique():
        if ward_code not in ward_name_mapping:
            match = re.match(r'0*(\d+)([A-Za-z]*)', ward_code)
            if match:
                num_part, alpha_part = match.group(1), match.group(2)
                ward_name_mapping[ward_code] = f"{num_part}{alpha_part}病棟"
            else:
                ward_name_mapping[ward_code] = ward_code

    df_path = os.path.join(temp_dir, "main_data.feather")
    df.reset_index(drop=True).to_feather(df_path)
    
    target_data_path = None
    if target_data is not None and not target_data.empty:
        target_data_path = os.path.join(temp_dir, "target_data.feather")
        target_data.reset_index(drop=True).to_feather(target_data_path)

    try:
        # 全体の最新日付はdfから取得する方が良いか、generate_filtered_summariesに任せる
        # ここではgenerate_filtered_summaries(df)の結果から取得
        all_summaries_for_date = generate_filtered_summaries(df) # 全体用サマリー
        if not all_summaries_for_date or "latest_date" not in all_summaries_for_date:
            latest_date_obj = pd.Timestamp.now().normalize() # フォールバック
            print("Warning: Could not determine latest_date from all_summaries, using current date.")
        else:
            latest_date_obj = all_summaries_for_date["latest_date"]
        
        if progress_callback: progress_callback(10, "PDF生成タスクを準備中...")
        
        tasks_to_run = []
        if mode == "all_only_filter": # UIからの「全体のみ」に対応
            tasks_to_run.append(("all", "全体", "全体"))
        else:
            if mode == "all":
                tasks_to_run.append(("all", "全体", "全体"))
            
            if mode == "all" or mode == "dept":
                # 診療科リスト (ソートなど元のロジックを維持)
                departments = sorted(df["診療科名"].unique()) 
                for dept in departments:
                    tasks_to_run.append(("dept", dept, dept))  # 診療科は名称をそのまま使用
            
            if mode == "all" or mode == "ward":
                # 病棟リスト (ソートなど元のロジックを維持)
                wards = sorted(df["病棟コード"].astype(str).unique()) # 文字列に統一
                for ward in wards:
                    display_name = ward_name_mapping.get(ward, ward)  # マッピングから表示名を取得
                    tasks_to_run.append(("ward", ward, display_name))  # 表示名を追加

        total_tasks_count = len(tasks_to_run)
        if progress_callback: progress_callback(15, f"タスク準備完了 (合計: {total_tasks_count}件)")
        
        if max_workers is None:
            cpu_cores = multiprocessing.cpu_count()
            # メモリ上限も考慮してワーカー数を調整 (例: 1ワーカーあたり2GB必要なら)
            # available_memory_gb = psutil.virtual_memory().available / (1024**3)
            # max_workers_by_memory = int(available_memory_gb / 2) # 仮に2GB/worker
            # max_workers = max(1, min(cpu_cores -1 if cpu_cores > 1 else 1, max_workers_by_memory, 4)) # 上限4など
            max_workers = max(1, min(cpu_cores -1 if cpu_cores > 1 else 1, 4)) # シンプルにコア数-1、上限4
        
        print(f"PDF生成開始 (マルチプロセス): ワーカー数={max_workers}, タスク数={total_tasks_count}, 高速モード={fast_mode}")
        
        zip_buffer_mp = BytesIO()
        with zipfile.ZipFile(zip_buffer_mp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf_mp:
            date_suffix = latest_date_obj.strftime("%Y%m%d")
            
            completed_count = 0
            # starmap に渡す引数リストを作成
            worker_args = [
                (df_path, task_type, task_val, task_display_name, latest_date_obj.isoformat(), landscape, target_data_path, fast_mode)
                for task_type, task_val, task_display_name in tasks_to_run
            ]
            
            with multiprocessing.Pool(processes=max_workers) as pool:
                results_mp = pool.starmap(process_pdf_in_worker_revised, worker_args)

            for res_item in results_mp:
                if res_item:
                    pdf_title, pdf_content_bytes = res_item
                    if pdf_content_bytes and pdf_content_bytes.getbuffer().nbytes > 0:
                        # ファイル名に使用する文字列をサニタイズ
                        safe_filename_prefix = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in pdf_title)
                        
                        folder_name = ""
                        if "診療科別" in pdf_title: folder_name = "診療科別/"
                        elif "病棟別" in pdf_title: folder_name = "病棟別/"
                        
                        pdf_filename = f"{folder_name}入院患者数予測_{safe_filename_prefix}_{date_suffix}.pdf"
                        zipf_mp.writestr(pdf_filename, pdf_content_bytes.getvalue())
                        completed_count +=1
            
                if progress_callback and total_tasks_count > 0 :
                    current_prog = int(15 + (completed_count / total_tasks_count) * 85)
                    progress_callback(min(100, current_prog), f"PDF生成中: {completed_count}/{total_tasks_count} 完了")
            
        batch_end_time = time.time()
        total_batch_time = batch_end_time - batch_start_time
        if progress_callback: progress_callback(100, f"処理完了! ({completed_count}件) 所要時間: {total_batch_time:.1f}秒")
        print(f"PDF一括生成完了: {completed_count}/{total_tasks_count} ファイル, 処理時間: {total_batch_time:.1f}秒")
        
        zip_buffer_mp.seek(0)
        return zip_buffer_mp

    except Exception as e_mp:
        print(f"一括PDF生成(MP)でエラー: {e_mp}")
        import traceback
        print(traceback.format_exc())
        if progress_callback: progress_callback(100, f"エラーが発生しました: {str(e_mp)}")
        return BytesIO()
    finally:
        # 一時ファイルをクリーンアップ
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"Temporary directory {temp_dir} removed.")
        except Exception as e_clean:
            print(f"一時ファイルの削除に失敗: {e_clean}")


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