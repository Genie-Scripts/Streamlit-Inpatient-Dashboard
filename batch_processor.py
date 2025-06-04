import pandas as pd
import streamlit as st # Only for type hints or if st.session_state is used in main process
from io import BytesIO
import zipfile
import os
import time
from functools import partial
import multiprocessing
import tempfile
import gc
import psutil
import re # re モジュールをインポート
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import threading

# forecast モジュールの関数
from forecast import generate_filtered_summaries, create_forecast_dataframe

# pdf_generator モジュールの関数 (修正されたものをインポート)
from pdf_generator import (
    create_pdf, create_landscape_pdf, register_fonts,
    MATPLOTLIB_FONT_NAME, REPORTLAB_FONT_NAME, # フォント名
    create_alos_chart_for_pdf,
    create_patient_chart_with_target_wrapper, # pdf_generator内のラッパー関数
    create_dual_axis_chart_for_pdf, # pdf_generator内のMatplotlib二軸グラフ関数
    get_chart_cache_key as get_pdf_gen_chart_cache_key, # pdf_generatorのキャッシュキー関数
    compute_data_hash as compute_pdf_gen_data_hash,   # pdf_generatorのハッシュ関数
    get_chart_cache as get_pdf_gen_main_process_cache # メインプロセス用キャッシュ取得
)

# 🚀 最適化設定
OPTIMAL_CHUNK_SIZE = 3
MAX_MEMORY_USAGE_PERCENT = 85
GRAPH_THREAD_WORKERS = 4

class SystemOptimizer:
    """システムリソースを監視・最適化するクラス"""
    
    @staticmethod
    def get_optimal_config():
        """システム環境に基づく最適設定を計算"""
        cpu_cores = multiprocessing.cpu_count()
        memory_gb = psutil.virtual_memory().total / (1024**3)
        
        # 最適なワーカー数を計算
        optimal_workers = min(
            cpu_cores - 1,  # CPUコア数 - 1
            int(memory_gb / 1.5),  # メモリGB / 1.5
            8  # 最大8ワーカー
        )
        
        # チャンクサイズの最適化
        chunk_size = max(2, min(OPTIMAL_CHUNK_SIZE, optimal_workers))
        
        return {
            'max_workers': max(1, optimal_workers),
            'chunk_size': chunk_size,
            'memory_limit': MAX_MEMORY_USAGE_PERCENT,
            'cpu_cores': cpu_cores,
            'memory_gb': memory_gb
        }
    
    @staticmethod
    def check_memory_usage():
        """現在のメモリ使用率をチェック"""
        return psutil.virtual_memory().percent
    
    @staticmethod
    def force_cleanup():
        """強制的なメモリクリーンアップ"""
        gc.collect()

class DataOptimizer:
    """データ処理を最適化するクラス"""
    
    @staticmethod
    def optimize_dataframe(df):
        """データフレームのメモリ使用量を最適化"""
        if df.empty:
            return df
        
        try:
            optimized_df = df.copy()
            
            # カテゴリカル変換
            categorical_columns = ['診療科名', '病棟コード']
            for col in categorical_columns:
                if col in optimized_df.columns and optimized_df[col].dtype == 'object':
                    optimized_df[col] = optimized_df[col].astype('category')
            
            # 数値型の最適化
            numeric_cols = optimized_df.select_dtypes(include=['int64', 'float64']).columns
            for col in numeric_cols:
                if col != '日付':  # 日付列は除外
                    if optimized_df[col].dtype == 'int64':
                        col_min = optimized_df[col].min()
                        col_max = optimized_df[col].max()
                        
                        if col_min >= 0 and col_max <= 4294967295:
                            optimized_df[col] = optimized_df[col].astype('uint32')
                        elif col_min >= -2147483648 and col_max <= 2147483647:
                            optimized_df[col] = optimized_df[col].astype('int32')
                    elif optimized_df[col].dtype == 'float64':
                        optimized_df[col] = optimized_df[col].astype('float32')
            
            return optimized_df
            
        except Exception as e:
            print(f"Data optimization failed: {e}")
            return df

# 🔧 新しい目標値ファイル構造に対応した目標値取得関数
def get_targets_for_pdf(task_value, task_type, target_data_df):
    """新しい目標値ファイル構造に対応した目標値取得関数"""
    t_all, t_wd, t_hd = None, None, None
    if target_data_df is None or target_data_df.empty: 
        return t_all, t_wd, t_hd
    
    filter_code = task_value if task_type != "all" else "全体"
    
    # 🔧 新しいCSVファイル構造をチェック
    required_cols_new = ['部門コード', '指標タイプ', '期間区分', '目標値']  # 新しい構造
    required_cols_old = ['部門コード', '区分', '目標値']  # 古い構造
    
    if all(col in target_data_df.columns for col in required_cols_new):
        # 🔧 新しい構造の処理
        # 日平均在院患者数の目標値を取得
        daily_census_targets = target_data_df[
            (target_data_df['指標タイプ'].str.contains('日平均在院患者数|在院患者数', case=False, na=False)) &
            (target_data_df['部門コード'].astype(str) == str(filter_code))
        ]
        
        if not daily_census_targets.empty:
            for _, row_t in daily_census_targets.iterrows():
                val_t = row_t.get('目標値')
                period_category = row_t.get('期間区分', '')
                
                if pd.notna(val_t):
                    if period_category == '全日': 
                        t_all = float(val_t)
                    elif period_category == '平日': 
                        t_wd = float(val_t)
                    elif period_category == '休日': 
                        t_hd = float(val_t)
        
    elif all(col in target_data_df.columns for col in required_cols_old):
        # 🔧 古い構造の処理（既存コードと同じ）
        target_rows_df = target_data_df[target_data_df['部門コード'].astype(str) == str(filter_code)]
        if not target_rows_df.empty:
            for _, row_t in target_rows_df.iterrows():
                val_t = row_t.get('目標値')
                if pd.notna(val_t):
                    if row_t.get('区分') == '全日': 
                        t_all = float(val_t)
                    elif row_t.get('区分') == '平日': 
                        t_wd = float(val_t)
                    elif row_t.get('区分') == '休日': 
                        t_hd = float(val_t)
    
    return t_all, t_wd, t_hd

# 🔧 新しい目標値ファイル構造に対応した表示名マッピング作成
def create_display_mapping_with_new_target_format(target_data_main):
    """新しい目標値ファイル構造に対応した表示名マッピング作成"""
    dept_display_map = {}
    ward_display_map = {}
    
    if target_data_main is not None and not target_data_main.empty:
        # 🔧 新旧両方の構造に対応
        if '部門コード' in target_data_main.columns and '部門名' in target_data_main.columns:
            # 重複を避けるため、部門コードと部門名のユニークな組み合わせを取得
            unique_mappings = target_data_main[['部門コード', '部門名']].drop_duplicates()
            
            for _, row in unique_mappings.iterrows():
                if pd.notna(row['部門コード']) and pd.notna(row['部門名']):
                    code_str = str(row['部門コード'])
                    name_str = str(row['部門名'])
                    dept_display_map[code_str] = name_str
                    ward_display_map[code_str] = name_str
                    
                    # 診療科名も部門名として使用される場合があるため、逆マッピングも作成
                    dept_display_map[name_str] = name_str
    
    return dept_display_map, ward_display_map

def process_pdf_in_worker_revised(
    df_path, filter_type, filter_value, display_name, latest_date_str, landscape,
    target_data_path=None, reduced_graphs=True,
    alos_chart_buffers_payload=None,
    patient_chart_buffers_payload=None,
    dual_axis_chart_buffers_payload=None
    ):
    """
    ワーカープロセスでPDFを生成する (グラフバッファを受け取る)
    """
    try:
        pid = os.getpid()
        # register_fonts() # モジュールインポート時に実行されるはず
        # print(f"PID {pid}: Worker for '{display_name}' started. Font: {MATPLOTLIB_FONT_NAME if MATPLOTLIB_FONT_NAME else 'Default'}")

        df_worker = pd.read_feather(df_path)
        latest_date_worker = pd.Timestamp(latest_date_str)
        
        target_data_worker = None
        if target_data_path and os.path.exists(target_data_path):
            target_data_worker = pd.read_feather(target_data_path)
        
        current_data_for_tables_worker = df_worker.copy() # テーブル生成用
        current_filter_code_worker = "全体"
        title_prefix_for_pdf = "全体"

        if filter_type == "dept":
            current_data_for_tables_worker = df_worker[df_worker["診療科名"] == filter_value].copy()
            current_filter_code_worker = filter_value
            title_prefix_for_pdf = f"診療科別 {display_name}"
        elif filter_type == "ward":
            current_data_for_tables_worker = df_worker[df_worker["病棟コード"] == filter_value].copy()
            current_filter_code_worker = str(filter_value)
            title_prefix_for_pdf = f"病棟別 {display_name}"
        
        if current_data_for_tables_worker.empty and filter_type != "all":
            # print(f"PID {pid}: Filtered data for tables empty for {title_prefix_for_pdf}. Skipping.")
            return None # データがない場合はNoneを返す
            
        summaries_worker = generate_filtered_summaries(
            current_data_for_tables_worker, 
            "診療科名" if filter_type == "dept" else ("病棟コード" if filter_type == "ward" else None),
            filter_value if filter_type != "all" else None
        )
        
        if not summaries_worker:
            # print(f"PID {pid}: Failed to generate summaries for {title_prefix_for_pdf}.")
            return None

        forecast_df_for_pdf = create_forecast_dataframe(
            summaries_worker.get("summary"), summaries_worker.get("weekday"), 
            summaries_worker.get("holiday"), latest_date_worker
        )
        
        # 🔧 グラフ日数リストを統一（reduced_graphsに関係なく固定）
        graph_days_list_for_pdf = ["90"] if reduced_graphs else ["90", "180"]

        pdf_creation_func = create_landscape_pdf if landscape else create_pdf
        
        pdf_bytes_io_result = pdf_creation_func(
            forecast_df=forecast_df_for_pdf,
            df_weekday=summaries_worker.get("weekday"),
            df_holiday=summaries_worker.get("holiday"),
            df_all_avg=summaries_worker.get("summary"),
            chart_data=current_data_for_tables_worker, # 部門別テーブル用
            title_prefix=title_prefix_for_pdf,
            latest_date=latest_date_worker,
            target_data=target_data_worker,
            filter_code=current_filter_code_worker,
            graph_days=graph_days_list_for_pdf, # この引数はpdf_generator側で使われなくなる想定
            alos_chart_buffers=alos_chart_buffers_payload,
            patient_chart_buffers=patient_chart_buffers_payload,
            dual_axis_chart_buffers=dual_axis_chart_buffers_payload
        )
        
        # メモリ解放
        del df_worker, current_data_for_tables_worker, summaries_worker, forecast_df_for_pdf, target_data_worker
        gc.collect()
        
        return (title_prefix_for_pdf, pdf_bytes_io_result) if pdf_bytes_io_result else None

    except Exception as e:
        print(f"PID {os.getpid()}: Error in worker for {filter_type} {filter_value} ('{display_name}'): {e}")
        import traceback
        print(traceback.format_exc())
        return None

def batch_generate_pdfs_mp_optimized(df_main, mode="all", landscape=False, target_data_main=None, 
                                    progress_callback=None, max_workers=None, fast_mode=True):
    batch_start_time = time.time()
    # register_fonts() # メインプロセス開始時に一度実行 (モジュールインポート時にも実行される)

    if progress_callback: progress_callback(0.05, "データを準備中...")

    temp_dir_main = tempfile.mkdtemp()
    df_path_main = os.path.join(temp_dir_main, "main_data.feather")
    df_main.reset_index(drop=True).to_feather(df_path_main)
    
    target_data_path_main = None
    if target_data_main is not None and not target_data_main.empty:
        target_data_path_main = os.path.join(temp_dir_main, "target_data.feather")
        target_data_main.reset_index(drop=True).to_feather(target_data_path_main)

    # メインプロセスでのみ使用するキャッシュ (pdf_generator.py から取得)
    main_process_chart_cache = get_pdf_gen_main_process_cache()

    try:
        summaries_for_latest_date = generate_filtered_summaries(df_main)
        latest_date_for_batch = summaries_for_latest_date.get("latest_date", pd.Timestamp.now().normalize())
        
        if progress_callback: progress_callback(0.10, "PDF生成タスクとグラフを準備中...")
        
        tasks_for_worker_with_buffers = []
        
        # 🔧 新しい目標値ファイル構造に対応した表示名マッピング
        dept_display_map, ward_display_map = create_display_mapping_with_new_target_format(target_data_main)
        
        # 既存の病棟表示名生成ロジックは保持
        unique_wards = df_main["病棟コード"].astype(str).unique()
        for ward in unique_wards:
            if ward not in ward_display_map:
                match = re.match(r'0*(\d+)([A-Za-z]*)', ward)
                if match: ward_display_map[ward] = f"{match.group(1)}{match.group(2)}病棟"
                else: ward_display_map[ward] = ward
        
        # 既存の診療科表示名生成ロジックは保持
        unique_depts = df_main["診療科名"].unique()
        for dept in unique_depts:
            if dept not in dept_display_map:
                 dept_display_map[dept] = dept

        # 🔧 グラフ日数リストを統一
        graph_days_to_pre_generate = ["90"] if fast_mode else ["90", "180"]
        
        task_definitions_list = []
        if mode == "all_only_filter":
            task_definitions_list.append({"type": "all", "value": "全体", "display_name": "全体", "data_for_graphs": df_main.copy()})
        else:
            if mode == "all":
                task_definitions_list.append({"type": "all", "value": "全体", "display_name": "全体", "data_for_graphs": df_main.copy()})
            if mode == "all" or mode == "dept":
                for dept_val in unique_depts:
                    task_definitions_list.append({
                        "type": "dept", "value": dept_val, 
                        "display_name": dept_display_map.get(dept_val, dept_val),
                        "data_for_graphs": df_main[df_main["診療科名"] == dept_val].copy()
                    })
            if mode == "all" or mode == "ward":
                for ward_val in unique_wards:
                    task_definitions_list.append({
                        "type": "ward", "value": ward_val, 
                        "display_name": ward_display_map.get(ward_val, ward_val),
                        "data_for_graphs": df_main[df_main["病棟コード"] == ward_val].copy()
                    })

        num_task_defs = len(task_definitions_list)
        for i, task_def_item in enumerate(task_definitions_list):
            graph_buffers_for_task = {"alos": {}, "patient_all": {}, "patient_weekday": {}, "patient_holiday": {}, "dual_axis": {}}
            data_for_current_task_graphs = task_def_item["data_for_graphs"]
            display_name_for_graphs = task_def_item["display_name"]
            
            target_all, target_weekday, target_holiday = get_targets_for_pdf(task_def_item["value"], task_def_item["type"], target_data_main)

            # ALOSグラフ - 🔧 統一されたグラフ日数リストを使用
            for days_val_str in graph_days_to_pre_generate:
                days_val_int = int(days_val_str)
                key = get_pdf_gen_chart_cache_key(f"ALOS_{display_name_for_graphs}", days_val_int, None, "alos_pdf", compute_pdf_gen_data_hash(data_for_current_task_graphs))
                buffer_val = main_process_chart_cache.get(key)
                if buffer_val is None and not data_for_current_task_graphs.empty:
                    img_buf = create_alos_chart_for_pdf(data_for_current_task_graphs, display_name_for_graphs, latest_date_for_batch, 30, MATPLOTLIB_FONT_NAME, days_to_show=days_val_int)
                    if img_buf: 
                        buffer_val = img_buf.getvalue()
                        main_process_chart_cache[key] = buffer_val
                        img_buf.close()  # 🔧 バッファを適切に閉じる
                if buffer_val: 
                    graph_buffers_for_task["alos"][days_val_str] = buffer_val
            
            # 患者数推移グラフ - 🔧 統一されたグラフ日数リストを使用
            patient_chart_types = {"all": target_all, "weekday": target_weekday, "holiday": target_holiday}
            for type_key, target_val in patient_chart_types.items():
                data_subset = data_for_current_task_graphs
                if type_key == "weekday" and "平日判定" in data_for_current_task_graphs.columns: 
                    data_subset = data_for_current_task_graphs[data_for_current_task_graphs["平日判定"] == "平日"]
                elif type_key == "holiday" and "平日判定" in data_for_current_task_graphs.columns: 
                    data_subset = data_for_current_task_graphs[data_for_current_task_graphs["平日判定"] == "休日"]
                if data_subset.empty and type_key != "all": 
                    continue

                for days_val_str in graph_days_to_pre_generate:  # 🔧 統一されたリストを使用
                    days_val_int = int(days_val_str)
                    key = get_pdf_gen_chart_cache_key(f"Patient_{type_key}_{display_name_for_graphs}", days_val_int, target_val, f"patient_{type_key}_pdf", compute_pdf_gen_data_hash(data_subset))
                    buffer_val = main_process_chart_cache.get(key)
                    if buffer_val is None and not data_subset.empty:
                        img_buf = create_patient_chart_with_target_wrapper(data_subset, title=f"{display_name_for_graphs} {type_key.capitalize()}推移({days_val_int}日)", days=days_val_int, target_value=target_val, font_name_for_mpl_to_use=MATPLOTLIB_FONT_NAME)
                        if img_buf: 
                            buffer_val = img_buf.getvalue()
                            main_process_chart_cache[key] = buffer_val
                            img_buf.close()  # 🔧 バッファを適切に閉じる
                    if buffer_val: 
                        graph_buffers_for_task[f"patient_{type_key}"][days_val_str] = buffer_val
            
            # 二軸グラフ - 🔧 統一されたグラフ日数リストを使用
            for days_val_str in graph_days_to_pre_generate:  # 🔧 統一されたリストを使用
                days_val_int = int(days_val_str)
                key = get_pdf_gen_chart_cache_key(f"DualAxis_{display_name_for_graphs}", days_val_int, None, "dual_axis_pdf", compute_pdf_gen_data_hash(data_for_current_task_graphs))
                buffer_val = main_process_chart_cache.get(key)
                if buffer_val is None and not data_for_current_task_graphs.empty:
                    img_buf = create_dual_axis_chart_for_pdf(data_for_current_task_graphs, title=f"{display_name_for_graphs} 患者移動({days_val_int}日)", days=days_val_int, font_name_for_mpl_to_use=MATPLOTLIB_FONT_NAME)
                    if img_buf: 
                        buffer_val = img_buf.getvalue()
                        main_process_chart_cache[key] = buffer_val
                        img_buf.close()  # 🔧 バッファを適切に閉じる
                if buffer_val: 
                    graph_buffers_for_task["dual_axis"][days_val_str] = buffer_val
            
            tasks_for_worker_with_buffers.append(
                (df_path_main, task_def_item["type"], task_def_item["value"], task_def_item["display_name"], 
                 latest_date_for_batch.isoformat(), landscape, target_data_path_main, fast_mode,
                 graph_buffers_for_task["alos"], 
                 {"all": graph_buffers_for_task["patient_all"], "weekday": graph_buffers_for_task["patient_weekday"], "holiday": graph_buffers_for_task["patient_holiday"]},
                 graph_buffers_for_task["dual_axis"])
            )
            if progress_callback and num_task_defs > 0:
                progress_val = int(10 + ( (i+1) / num_task_defs) * 15) # 10-25%
                progress_callback(progress_val / 100.0, f"グラフ準備中: {i+1}/{num_task_defs}")
        
        del df_main, target_data_main, task_definitions_list # メモリ解放
        gc.collect()

        total_tasks_to_process = len(tasks_for_worker_with_buffers)
        if progress_callback: progress_callback(0.25, f"タスク準備完了 (合計: {total_tasks_to_process}件)")
        
        if max_workers is None:
            cpu_cores = multiprocessing.cpu_count()
            max_workers = max(1, min(cpu_cores -1 if cpu_cores > 1 else 1, 4))
        
        zip_archive_buffer = BytesIO()
        with zipfile.ZipFile(zip_archive_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf_archive:
            date_suffix_str = latest_date_for_batch.strftime("%Y%m%d")
            pdfs_completed = 0
            
            if total_tasks_to_process == 0: # タスクがない場合は空のZIP
                if progress_callback: progress_callback(1.0, "処理対象なし")
                print("一括PDF生成: 処理対象なし")
                zip_archive_buffer.seek(0)
                return zip_archive_buffer

            with multiprocessing.Pool(processes=max_workers) as pool_obj:
                pdf_results = pool_obj.starmap(process_pdf_in_worker_revised, tasks_for_worker_with_buffers)

            for result_item_pdf in pdf_results:
                if result_item_pdf:
                    title_from_worker, pdf_content_io_obj = result_item_pdf
                    if pdf_content_io_obj and pdf_content_io_obj.getbuffer().nbytes > 0:
                        safe_pdf_title = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in title_from_worker)
                        folder_prefix = ""
                        if "診療科別" in title_from_worker: folder_prefix = "診療科別/"
                        elif "病棟別" in title_from_worker: folder_prefix = "病棟別/"
                        pdf_file_name_in_zip = f"{folder_prefix}入院患者数予測_{safe_pdf_title}_{date_suffix_str}.pdf"
                        zipf_archive.writestr(pdf_file_name_in_zip, pdf_content_io_obj.getvalue())
                        pdfs_completed +=1
                        pdf_content_io_obj.close()
            
                if progress_callback and total_tasks_to_process > 0 :
                    current_progress_val = int(25 + (pdfs_completed / total_tasks_to_process) * 75)
                    progress_callback(min(100, current_progress_val) / 100.0, f"PDF生成中: {pdfs_completed}/{total_tasks_to_process} 完了")
            
        batch_end_time_main = time.time()
        total_batch_duration = batch_end_time_main - batch_start_time
        if progress_callback: progress_callback(1.0, f"処理完了! ({pdfs_completed}件) 所要時間: {total_batch_duration:.1f}秒")
        
        zip_archive_buffer.seek(0)
        return zip_archive_buffer

    except Exception as e_main_batch:
        print(f"一括PDF生成(MP)のメイン処理でエラー: {e_main_batch}")
        import traceback
        print(traceback.format_exc())
        if progress_callback: progress_callback(1.0, f"エラーが発生しました: {str(e_main_batch)}")
        return BytesIO()
    finally:
        try:
            import shutil
            shutil.rmtree(temp_dir_main, ignore_errors=True)
        except Exception as e_cleanup:
            print(f"一時ディレクトリの削除に失敗: {e_cleanup}")

# 🚀 ハイパー最適化されたPDF一括生成
def batch_generate_pdfs_hyper_optimized(
    df_main, mode="all", landscape=False, target_data_main=None,
    progress_callback=None, max_workers=None, fast_mode=True
):
    """ハイパー最適化されたPDF一括生成"""
    start_time = time.time()
    
    if progress_callback:
        progress_callback(0.01, "システム最適化中...")
    
    # システム設定の最適化
    config = SystemOptimizer.get_optimal_config()
    
    if progress_callback:
        progress_callback(0.03, f"データ最適化中... (CPU:{config['cpu_cores']}コア, RAM:{config['memory_gb']:.1f}GB)")
    
    # データの最適化
    df_optimized = DataOptimizer.optimize_dataframe(df_main)
    
    # 一時ディレクトリの準備
    temp_dir = tempfile.mkdtemp()
    df_path = os.path.join(temp_dir, "hyper_optimized_data.feather")
    df_optimized.reset_index(drop=True).to_feather(df_path)
    
    target_data_path = None
    if target_data_main is not None and not target_data_main.empty:
        target_data_path = os.path.join(temp_dir, "target_data.feather")
        target_data_main.reset_index(drop=True).to_feather(target_data_path)
    
    try:
        # 最新日付の取得
        summaries = generate_filtered_summaries(df_optimized)
        latest_date = summaries.get("latest_date", pd.Timestamp.now().normalize())
        
        if progress_callback:
            progress_callback(0.08, "タスク最適化中...")
        
        # 🔧 新しい目標値ファイル構造に対応した表示名マッピング
        dept_display_map, ward_display_map = create_display_mapping_with_new_target_format(target_data_main)
        
        # 既存の病棟表示名生成ロジックは保持
        unique_wards = df_optimized["病棟コード"].astype(str).unique()
        for ward in unique_wards:
            if ward not in ward_display_map:
                match = re.match(r'0*(\d+)([A-Za-z]*)', ward)
                if match: ward_display_map[ward] = f"{match.group(1)}{match.group(2)}病棟"
                else: ward_display_map[ward] = ward
        
        # 既存の診療科表示名生成ロジックは保持
        unique_depts = df_optimized["診療科名"].unique()
        for dept in unique_depts:
            if dept not in dept_display_map:
                dept_display_map[dept] = dept

        task_definitions_list = []
        if mode == "all_only_filter":
            task_definitions_list.append({"type": "all", "value": "全体", "display_name": "全体"})
        else:
            if mode == "all":
                task_definitions_list.append({"type": "all", "value": "全体", "display_name": "全体"})
            if mode == "all" or mode == "dept":
                for dept_val in unique_depts:
                    task_definitions_list.append({
                        "type": "dept", "value": dept_val, 
                        "display_name": dept_display_map.get(dept_val, dept_val)
                    })
            if mode == "all" or mode == "ward":
                for ward_val in unique_wards:
                    task_definitions_list.append({
                        "type": "ward", "value": ward_val, 
                        "display_name": ward_display_map.get(ward_val, ward_val)
                    })

        if not task_definitions_list:
            return BytesIO()
        
        if progress_callback:
            progress_callback(0.15, f"ハイパー並列処理開始 ({len(task_definitions_list)}タスク, {config['max_workers']}ワーカー)")
        
        # 最適なワーカー数の決定
        if max_workers is None:
            max_workers = config['max_workers']
        
        # ZIP作成とデータ収集
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
            date_suffix = latest_date.strftime("%Y%m%d")
            completed_count = 0
            total_tasks = len(task_definitions_list)
            
            # チャンク単位で処理
            chunk_size = config['chunk_size']
            task_chunks = [task_definitions_list[i:i + chunk_size] for i in range(0, len(task_definitions_list), chunk_size)]
            
            # ProcessPoolExecutorでハイパー並列処理
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                # 全チャンクを並列でスケジューリング
                future_to_chunk = {}
                for chunk in task_chunks:
                    future = executor.submit(
                        process_chunk_hyper_optimized,
                        chunk, df_path, landscape, target_data_path,
                        fast_mode, latest_date.isoformat()
                    )
                    future_to_chunk[future] = chunk
                
                # 結果の並列収集とZIP書き込み
                for future in as_completed(future_to_chunk):
                    try:
                        chunk_results = future.result(timeout=900)  # 15分タイムアウト
                        
                        for result in chunk_results:
                            if result:
                                title, pdf_content = result
                                if pdf_content and hasattr(pdf_content, 'getbuffer') and pdf_content.getbuffer().nbytes > 0:
                                    # 安全なファイル名生成
                                    safe_title = "".join(
                                        c if c.isalnum() or c in ['-', '_'] else '_'
                                        for c in title
                                    )
                                    
                                    # フォルダ構造
                                    folder = ""
                                    if "診療科別" in title:
                                        folder = "診療科別/"
                                    elif "病棟別" in title:
                                        folder = "病棟別/"
                                    
                                    filename = f"{folder}入院患者数予測_{safe_title}_{date_suffix}.pdf"
                                    zipf.writestr(filename, pdf_content.getvalue())
                                    pdf_content.close()
                                    completed_count += 1
                        
                        # リアルタイムプログレス更新
                        if progress_callback and total_tasks > 0:
                            progress = int(15 + (completed_count / total_tasks) * 80)
                            progress_callback(
                                min(95, progress) / 100.0,
                                f"ハイパー処理中: {completed_count}/{total_tasks} 完了 (メモリ: {SystemOptimizer.check_memory_usage():.1f}%)"
                            )
                    
                    except Exception as e:
                        print(f"Hyper processing error for chunk: {e}")
                        continue
        
        end_time = time.time()
        duration = end_time - start_time
        
        if progress_callback:
            rate = completed_count / duration if duration > 0 else 0
            progress_callback(
                1.0,
                f"ハイパー処理完了! {completed_count}件のPDFを{duration:.1f}秒で生成 ({rate:.1f}件/秒)"
            )
        
        zip_buffer.seek(0)
        return zip_buffer
        
    except Exception as e:
        print(f"Hyper optimized batch generation error: {e}")
        import traceback
        print(traceback.format_exc())
        if progress_callback:
            progress_callback(1.0, f"エラー: {str(e)}")
        return BytesIO()
    
    finally:
        # 徹底的なクリーンアップ
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass
        SystemOptimizer.force_cleanup()

def process_chunk_hyper_optimized(task_chunk, df_path, landscape, target_data_path, fast_mode, latest_date_str):
    """ハイパー最適化されたチャンク処理"""
    results = []
    
    try:
        for task in task_chunk:
            result = process_pdf_in_worker_revised(
                df_path, task["type"], task["value"], task["display_name"],
                latest_date_str, landscape, target_data_path, fast_mode,
                None, None, None  # グラフバッファは後で最適化
            )
            
            if result:
                results.append(result)
            
            # メモリ使用量チェック
            if SystemOptimizer.check_memory_usage() > MAX_MEMORY_USAGE_PERCENT:
                SystemOptimizer.force_cleanup()
        
        return results
        
    except Exception as e:
        print(f"Chunk processing error: {e}")
        return []
    finally:
        gc.collect()

# 🔧 既存のbatch_generate_pdfs_full_optimized関数を修正
def batch_generate_pdfs_full_optimized(
    df, mode="all", landscape=False, target_data=None, 
    progress_callback=None, use_parallel=True, max_workers=None, fast_mode=True,
    use_hyper_optimization=False  # 🚀 新しいパラメータを追加
    ):
    if df is None or df.empty:
        if progress_callback: progress_callback(0, "データがありません。")
        print("batch_generate_pdfs_full_optimized: 分析対象のデータフレームが空です。")
        return BytesIO()

    if progress_callback: progress_callback(0, "処理開始...")
    
    if use_parallel:
        if use_hyper_optimization:
            # 🚀 ハイパー最適化版を使用
            return batch_generate_pdfs_hyper_optimized(df, mode, landscape, target_data, progress_callback, max_workers, fast_mode)
        else:
            # 既存の最適化版を使用
            return batch_generate_pdfs_mp_optimized(df, mode, landscape, target_data, progress_callback, max_workers, fast_mode)
    else:
        # シングルプロセス版 (フォールバックまたはデバッグ用)
        print("Parallel processing disabled. Using sequential PDF generation.")
        temp_dir_seq = tempfile.mkdtemp()
        df_path_seq = os.path.join(temp_dir_seq, "main_data_seq.feather")
        df.reset_index(drop=True).to_feather(df_path_seq)
        target_data_path_seq = None
        if target_data is not None and not target_data.empty:
            target_data_path_seq = os.path.join(temp_dir_seq, "target_data_seq.feather")
            target_data.reset_index(drop=True).to_feather(target_data_path_seq)

        all_summaries = generate_filtered_summaries(df)
        latest_date_seq = all_summaries.get("latest_date", pd.Timestamp.now().normalize())
        
        tasks_seq = []
        # 🔧 新しい目標値ファイル構造に対応した表示名マッピング
        dept_display_map_seq, ward_display_map_seq = create_display_mapping_with_new_target_format(target_data)
        
        # 病棟表示名の生成
        for ward in df["病棟コード"].astype(str).unique():
            if ward not in ward_display_map_seq:
                match = re.match(r'0*(\d+)([A-Za-z]*)', ward)
                if match: ward_display_map_seq[ward] = f"{match.group(1)}{match.group(2)}病棟"
                else: ward_display_map_seq[ward] = ward
        
        # 診療科表示名の設定
        for dept in df["診療科名"].unique():
            if dept not in dept_display_map_seq:
                dept_display_map_seq[dept] = dept

        if mode == "all_only_filter": tasks_seq.append({"type": "all", "value": "全体", "display_name": "全体"})
        else:
            if mode == "all": tasks_seq.append({"type": "all", "value": "全体", "display_name": "全体"})
            if mode == "all" or mode == "dept":
                for dept in sorted(df["診療科名"].unique()): tasks_seq.append({"type": "dept", "value": dept, "display_name": dept_display_map_seq.get(dept, dept)})
            if mode == "all" or mode == "ward":
                for ward in sorted(df["病棟コード"].astype(str).unique()): tasks_seq.append({"type": "ward", "value": ward, "display_name": ward_display_map_seq.get(ward, ward)})

        zip_buffer_seq = BytesIO()
        with zipfile.ZipFile(zip_buffer_seq, 'w', zipfile.ZIP_DEFLATED) as zipf_seq:
            date_suffix_seq = latest_date_seq.strftime("%Y%m%d")
            completed_seq = 0
            total_seq = len(tasks_seq)
            for task_item in tasks_seq:
                # グラフバッファはここでは生成しない (process_pdf_in_worker_revised が内部で生成する)
                # process_pdf_in_worker_revised はFeatherパスとグラフバッファ引数を期待する
                # シングルプロセスではグラフバッファをNoneとして渡すか、process_pdf_in_worker_revisedを修正
                # または、シングルプロセス用の別関数を用意する方が良い。
                # ここでは、process_pdf_in_worker_revised をそのまま使い、バッファは None とする。
                # その場合、process_pdf_in_worker_revised 側でバッファがNoneの場合の処理が必要になる。
                # (または、シングルプロセスではグラフ生成を process_pdf_in_worker_revised に任せる)

                # シングルプロセス実行のために、グラフを都度生成する。
                # この部分は、メインプロセスのグラフ生成ロジックをここに移植する必要がある。
                # 簡単のため、ALOSグラフのみを仮に生成して渡す形にする。
                # **注意:** このシングルプロセス版は、グラフ事前生成とキャッシュの恩恵を受けないため、
                #           パフォーマンスが大幅に劣る。あくまでデバッグ用やフォールバック。

                current_task_data_seq = df.copy()
                if task_item["type"] == "dept": current_task_data_seq = df[df["診療科名"] == task_item["value"]].copy()
                elif task_item["type"] == "ward": current_task_data_seq = df[df["病棟コード"] == task_item["value"]].copy()

                alos_bufs_seq = {}
                if not current_task_data_seq.empty:
                     for days_str_seq in (["90"] if fast_mode else ["90", "180"]):
                        buf_io = create_alos_chart_for_pdf(current_task_data_seq, task_item["display_name"], latest_date_seq, 30, MATPLOTLIB_FONT_NAME, days_to_show=int(days_str_seq))
                        if buf_io: alos_bufs_seq[days_str_seq] = buf_io.getvalue() # バイト列を保存
                
                # patient_chart_buffers と dual_axis_chart_buffers も同様に生成が必要だが、簡略化のため省略。
                # 実際にはメインプロセスと同じロジックでこれらも生成して渡す。
                patient_bufs_seq = {"all": {}, "weekday": {}, "holiday": {}} # ダミー
                dual_bufs_seq = {} # ダミー


                result_seq = process_pdf_in_worker_revised(
                    df_path_seq, task_item["type"], task_item["value"], task_item["display_name"],
                    latest_date_seq.isoformat(), landscape, target_data_path_seq, fast_mode,
                    alos_chart_buffers_payload=alos_bufs_seq, # バイト列の辞書
                    patient_chart_buffers_payload=patient_bufs_seq, # ダミー
                    dual_axis_chart_buffers_payload=dual_bufs_seq   # ダミー
                )
                if result_seq:
                    title_res_seq, pdf_io_seq = result_seq
                    if pdf_io_seq and pdf_io_seq.getbuffer().nbytes > 0:
                        safe_title_seq = "".join(c if c.isalnum() else '_' for c in title_res_seq)
                        folder_seq = "診療科別/" if "診療科別" in title_res_seq else ("病棟別/" if "病棟別" in title_res_seq else "")
                        zipf_seq.writestr(f"{folder_seq}入院患者数予測_{safe_title_seq}_{date_suffix_seq}.pdf", pdf_io_seq.getvalue())
                        completed_seq += 1
                if progress_callback: progress_callback( (completed_seq/total_seq) if total_seq > 0 else 1, f"PDF生成中 (順次): {completed_seq}/{total_seq}")
        
        try: 
            import shutil
            shutil.rmtree(temp_dir_seq, ignore_errors=True)
        except Exception: 
            pass
        zip_buffer_seq.seek(0)
        return zip_buffer_seq