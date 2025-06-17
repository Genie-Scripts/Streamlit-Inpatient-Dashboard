import pandas as pd
import streamlit as st
from io import BytesIO
import zipfile
import os
import time
from functools import partial
import multiprocessing
import tempfile
import gc
import psutil
import re
import matplotlib.pyplot as plt

from forecast import generate_filtered_summaries, create_forecast_dataframe
from config import EXCLUDED_WARDS  # 追加: 除外病棟設定をインポート

from pdf_generator import (
    create_pdf, create_landscape_pdf, register_fonts,
    MATPLOTLIB_FONT_NAME, REPORTLAB_FONT_NAME,
    create_alos_chart_for_pdf,
    create_patient_chart_with_target_wrapper,
    create_dual_axis_chart_for_pdf,
    get_chart_cache_key as get_pdf_gen_chart_cache_key,
    compute_data_hash as compute_pdf_gen_data_hash,
    get_chart_cache as get_pdf_gen_main_process_cache,
    filter_excluded_wards  # 追加: 除外病棟フィルタリング関数
)

EXCLUDED_WARDS_SET = set(EXCLUDED_WARDS) if EXCLUDED_WARDS else set()

def cleanup_memory():
    """メモリの積極的な解放"""
    plt.close('all')
    gc.collect()

def should_skip_ward_optimized(ward_code, display_name=None):
    """最適化された除外病棟チェック"""
    if not EXCLUDED_WARDS_SET:
        return False
    
    ward_str = str(ward_code).strip()
    
    # 直接チェック（O(1)）
    if ward_str in EXCLUDED_WARDS_SET:
        return True
    
    # 0パディングバリエーションチェック
    if not ward_str.startswith('0'):
        if f"0{ward_str}" in EXCLUDED_WARDS_SET or f"00{ward_str}" in EXCLUDED_WARDS_SET:
            return True
    
    # 表示名からの抽出（必要な場合のみ）
    if display_name and "病棟" in display_name:
        match = re.search(r'(\d+[A-Za-z]*?)病棟', display_name)
        if match:
            extracted = match.group(1)
            if extracted in EXCLUDED_WARDS_SET:
                return True
    
    return False


# 2. グラフ生成の並列化改善
def prepare_graph_buffers_parallel(task_definitions, df_main, target_index, latest_date, graph_days, progress_callback=None):
    """グラフバッファの並列準備"""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    
    total_tasks = len(task_definitions)
    completed = 0
    
    # ワーカー数の最適化
    max_workers = min(multiprocessing.cpu_count(), 4)
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        
        for task_def in task_definitions:
            if task_def["type"] == "ward" and should_skip_ward_optimized(task_def["value"], task_def["display_name"]):
                continue
            
            future = executor.submit(
                generate_task_graphs,
                task_def,
                target_index,
                latest_date,
                graph_days
            )
            futures[future] = task_def
        
        results = []
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
                
                completed += 1
                if progress_callback and total_tasks > 0:
                    progress = 0.1 + (completed / total_tasks) * 0.15
                    progress_callback(progress, f"グラフ準備中: {completed}/{total_tasks}")
                    
            except Exception as e:
                print(f"グラフ生成エラー: {e}")
        
        return results


# 3. メモリ効率の改善
def process_pdf_batch_optimized(df_main, mode="all", landscape=False, target_data=None, 
                               progress_callback=None, max_workers=None, fast_mode=True):
    """最適化されたバッチPDF生成"""
    
    # 早期の除外病棟フィルタリング
    if df_main is not None and not df_main.empty:
        df_main = df_main[~df_main['病棟コード'].astype(str).isin(EXCLUDED_WARDS_SET)]
        
        if df_main.empty:
            if progress_callback:
                progress_callback(1.0, "除外病棟フィルタリング後データなし")
            return BytesIO()
    
    # 目標値インデックスの作成（一度だけ）
    target_index = batch_create_target_index(target_data) if target_data is not None else {}
    
    # タスク定義の準備
    task_definitions = prepare_task_definitions(df_main, mode)
    
    # グラフの並列生成
    graph_days = ["90"] if fast_mode else ["90", "180"]
    graph_results = prepare_graph_buffers_parallel(
        task_definitions, 
        df_main, 
        target_index, 
        pd.Timestamp.now(), 
        graph_days,
        progress_callback
    )
    
    # PDFの並列生成
    pdf_results = generate_pdfs_parallel(
        graph_results, 
        df_main, 
        target_data, 
        landscape, 
        max_workers,
        progress_callback
    )
    
    # ZIP作成
    return create_zip_archive(pdf_results, progress_callback)


# 4. キャッシュ効率の改善
class OptimizedChartCache:
    """最適化されたグラフキャッシュ"""
    def __init__(self, max_size_mb=500):
        self.cache = {}
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.current_size = 0
        self.access_count = {}
        
    def get(self, key):
        if key in self.cache:
            self.access_count[key] = self.access_count.get(key, 0) + 1
            return self.cache[key]
        return None
    
    def put(self, key, value):
        if not value:
            return
            
        value_size = len(value) if isinstance(value, bytes) else 0
        
        # サイズ制限チェック
        while self.current_size + value_size > self.max_size_bytes and self.cache:
            # LRU削除
            lru_key = min(self.access_count.items(), key=lambda x: x[1])[0]
            self._remove(lru_key)
        
        self.cache[key] = value
        self.current_size += value_size
        self.access_count[key] = 1
    
    def _remove(self, key):
        if key in self.cache:
            value = self.cache[key]
            value_size = len(value) if isinstance(value, bytes) else 0
            self.current_size -= value_size
            del self.cache[key]
            del self.access_count[key]

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
        
        # ===== 除外病棟の早期チェック =====
        if filter_type == "ward":
            if should_skip_ward(filter_value, display_name):
                debug_print(f"PID {pid}: 除外病棟のためスキップ - {filter_value} ({display_name})")
                return None

        df_worker = pd.read_feather(df_path)
        latest_date_worker = pd.Timestamp(latest_date_str)
        
        target_data_worker = None
        if target_data_path and os.path.exists(target_data_path):
            target_data_worker = pd.read_feather(target_data_path)
        
        current_data_for_tables_worker = df_worker.copy()
        current_filter_code_worker = "全体"
        title_prefix_for_pdf = "全体"

        if filter_type == "dept":
            current_data_for_tables_worker = df_worker[df_worker["診療科名"] == filter_value].copy()
            current_filter_code_worker = filter_value
            title_prefix_for_pdf = f"診療科別 {display_name}"
        elif filter_type == "ward":
            # 病棟コードの比較を文字列として厳密に行う
            current_data_for_tables_worker = df_worker[df_worker["病棟コード"].astype(str) == str(filter_value)].copy()
            current_filter_code_worker = str(filter_value)
            title_prefix_for_pdf = f"病棟別 {display_name}"
        
        # ===== 除外病棟フィルタリングの適用 =====
        if not current_data_for_tables_worker.empty:
            original_count = len(current_data_for_tables_worker)
            current_data_for_tables_worker = filter_excluded_wards(current_data_for_tables_worker)
            
            if current_data_for_tables_worker.empty:
                debug_print(f"PID {pid}: 除外病棟フィルタリング後データが空 - {title_prefix_for_pdf}")
                return None
            
            # 除外病棟の残存チェック
            if '病棟コード' in current_data_for_tables_worker.columns:
                remaining_wards = current_data_for_tables_worker['病棟コード'].astype(str).unique()
                excluded_found = [ward for ward in remaining_wards if ward in EXCLUDED_WARDS]
                if excluded_found:
                    debug_print(f"PID {pid}: 除外病棟が残存 - {excluded_found} in {title_prefix_for_pdf}")
                    return None
        
        if current_data_for_tables_worker.empty:
            debug_print(f"PID {pid}: フィルタ後データが空 - {title_prefix_for_pdf}")
            return None
            
        summaries_worker = generate_filtered_summaries(
            current_data_for_tables_worker, 
            "診療科名" if filter_type == "dept" else ("病棟コード" if filter_type == "ward" else None),
            filter_value if filter_type != "all" else None
        )
        
        if not summaries_worker:
            debug_print(f"PID {pid}: 集計データ生成失敗 - {title_prefix_for_pdf}")
            return None

        forecast_df_for_pdf = create_forecast_dataframe(
            summaries_worker.get("summary"), summaries_worker.get("weekday"), 
            summaries_worker.get("holiday"), latest_date_worker
        )
        
        graph_days_list_for_pdf = ["90"] if reduced_graphs else ["90", "180"]

        pdf_creation_func = create_landscape_pdf if landscape else create_pdf
        
        pdf_bytes_io_result = pdf_creation_func(
            forecast_df=forecast_df_for_pdf,
            df_weekday=summaries_worker.get("weekday"),
            df_holiday=summaries_worker.get("holiday"),
            df_all_avg=summaries_worker.get("summary"),
            chart_data=current_data_for_tables_worker,
            title_prefix=title_prefix_for_pdf,
            latest_date=latest_date_worker,
            target_data=target_data_worker,
            filter_code=current_filter_code_worker,
            graph_days=graph_days_list_for_pdf,
            alos_chart_buffers=alos_chart_buffers_payload,
            patient_chart_buffers=patient_chart_buffers_payload,
            dual_axis_chart_buffers=dual_axis_chart_buffers_payload
        )
        
        # メモリ解放
        del df_worker, current_data_for_tables_worker, summaries_worker, forecast_df_for_pdf, target_data_worker
        cleanup_memory()  # ← これを追加
        gc.collect()
        
        return (title_prefix_for_pdf, pdf_bytes_io_result) if pdf_bytes_io_result else None

    except Exception as e:
        debug_print(f"PID {os.getpid()}: Error in worker for {filter_type} {filter_value} ('{display_name}'): {e}")
        import traceback
        cleanup_memory()  # ← これを追加
        debug_print(traceback.format_exc())
        return None
    finally:
        cleanup_memory()  # ← finally節を追加


def batch_generate_pdfs_mp_optimized(df_main, mode="all", landscape=False, target_data_main=None, 
                                    progress_callback=None, max_workers=None, fast_mode=True):
    batch_start_time = time.time()

    if progress_callback: progress_callback(0.05, "データを準備中...")

    # ===== 除外病棟フィルタリングを最初に適用 =====
    if df_main is not None and not df_main.empty:
        original_count = len(df_main)
        df_main = filter_excluded_wards(df_main)
        filtered_count = len(df_main)
        
        if original_count > filtered_count:
            debug_print(f"バッチ処理: {original_count - filtered_count}件の除外病棟データを削除")
        
        if df_main.empty:
            debug_print("バッチ処理: 除外病棟フィルタリング後、データが空になりました")
            if progress_callback: progress_callback(1.0, "除外病棟フィルタリング後データなし")
            return BytesIO()

    temp_dir_main = tempfile.mkdtemp()
    df_path_main = os.path.join(temp_dir_main, "main_data.feather")
    df_main.reset_index(drop=True).to_feather(df_path_main)
    
    target_data_path_main = None
    if target_data_main is not None and not target_data_main.empty:
        target_data_path_main = os.path.join(temp_dir_main, "target_data.feather")
        target_data_main.reset_index(drop=True).to_feather(target_data_path_main)

    main_process_chart_cache = get_pdf_gen_main_process_cache()

    try:
        summaries_for_latest_date = generate_filtered_summaries(df_main)
        latest_date_for_batch = summaries_for_latest_date.get("latest_date", pd.Timestamp.now().normalize())
        
        if progress_callback: progress_callback(0.10, "PDF生成タスクとグラフを準備中...")
        
        tasks_for_worker_with_buffers = []
        
        # 表示名マッピング準備
        dept_display_map = {}
        ward_display_map = {}
        if target_data_main is not None and not target_data_main.empty and '部門コード' in target_data_main.columns and '部門名' in target_data_main.columns:
            for _, row in target_data_main.iterrows():
                if pd.notna(row['部門コード']) and pd.notna(row['部門名']):
                    code_str = str(row['部門コード'])
                    dept_display_map[code_str] = row['部門名']
                    ward_display_map[code_str] = row['部門名']
        
        # 病棟コードを文字列として扱う
        unique_wards = df_main["病棟コード"].astype(str).unique()
        # ===== 除外病棟を事前に除去（改善版） =====
        unique_wards_filtered = []
        for ward in unique_wards:
            display_name = ward_display_map.get(ward, ward)
            if not should_skip_ward(ward, display_name):
                unique_wards_filtered.append(ward)
            else:
                debug_print(f"バッチ処理: 除外病棟をスキップ - {ward} ({display_name})")
        unique_wards = unique_wards_filtered
        
        for ward in unique_wards:
            if ward not in ward_display_map:
                # 正規表現を修正：先頭の0を保持
                match = re.match(r'(0*)(\d+[A-Za-z]*)', ward)
                if match: 
                    # 先頭の0を保持したまま表示名を生成
                    ward_display_map[ward] = f"{match.group(1)}{match.group(2)}病棟"
                else: 
                    ward_display_map[ward] = ward
        
        unique_depts = df_main["診療科名"].unique()
        for dept in unique_depts:
            if dept not in dept_display_map:
                 dept_display_map[dept] = dept

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
                    # ===== 除外病棟の再チェック（改善版） =====
                    if should_skip_ward(ward_val, ward_display_map.get(ward_val, ward_val)):
                        debug_print(f"バッチ処理: 除外病棟をスキップ - {ward_val}")
                        continue
                        
                    task_definitions_list.append({
                        "type": "ward", "value": ward_val, 
                        "display_name": ward_display_map.get(ward_val, ward_val),
                        "data_for_graphs": df_main[df_main["病棟コード"].astype(str) == ward_val].copy()
                    })

        def get_targets_for_pdf(task_value, task_type, target_data_df):
            """PDF用の目標値を取得する（修正版）"""
            t_all, t_wd, t_hd = None, None, None
            if target_data_df is None or target_data_df.empty: 
                return t_all, t_wd, t_hd
            
            filter_code = str(task_value) if task_type != "all" else "全体"
            
            # 目標値の検索を複数パターンで実行
            search_codes = []
            if task_type == "all":
                search_codes = ["全体", "000", "病院全体", "総合", "0", "00"]
            else:
                # 病棟の場合、文字列として正確に比較
                search_codes = [str(task_value)]
                # 0パディングのバリエーションも追加
                if task_type == "ward" and not str(task_value).startswith('0'):
                    search_codes.extend([f"0{task_value}", f"00{task_value}"])
            
            debug_print(f"目標値検索: type={task_type}, value={task_value}, search_codes={search_codes}")
            
            for search_code in search_codes:
                # 部門コードを文字列として比較
                target_rows_df = target_data_df[target_data_df['部門コード'].astype(str).str.strip() == search_code.strip()]
                if not target_rows_df.empty:
                    debug_print(f"目標値発見: {search_code} -> {len(target_rows_df)}行")
                    for _, row_t in target_rows_df.iterrows():
                        val_t = row_t.get('目標値')
                        if pd.notna(val_t):
                            try:
                                val_float = float(val_t)
                                period_str = str(row_t.get('区分', ''))
                                if '全日' in period_str or '全て' in period_str: 
                                    t_all = val_float
                                    debug_print(f"  全日目標値: {val_float}")
                                elif '平日' in period_str: 
                                    t_wd = val_float
                                    debug_print(f"  平日目標値: {val_float}")
                                elif '休日' in period_str or '祝日' in period_str: 
                                    t_hd = val_float
                                    debug_print(f"  休日目標値: {val_float}")
                            except (ValueError, TypeError):
                                continue
                    break  # 一つでも見つかったら終了
            
            return t_all, t_wd, t_hd

        num_task_defs = len(task_definitions_list)
        for i, task_def_item in enumerate(task_definitions_list):
            # ===== 除外病棟の最終チェック =====
            if task_def_item["type"] == "ward":
                if should_skip_ward(task_def_item["value"], task_def_item["display_name"]):
                    debug_print(f"グラフ生成段階で除外病棟をスキップ - {task_def_item['value']}")
                    continue
                    
            graph_buffers_for_task = {"alos": {}, "patient_all": {}, "patient_weekday": {}, "patient_holiday": {}, "dual_axis": {}}
            data_for_current_task_graphs = task_def_item["data_for_graphs"]
            
            # データが空の場合はスキップ
            if data_for_current_task_graphs.empty:
                debug_print(f"グラフ生成: データが空のためスキップ - {task_def_item['display_name']}")
                continue
                
            display_name_for_graphs = task_def_item["display_name"]
            
            # 目標値取得（修正版を使用）
            target_all, target_weekday, target_holiday = get_targets_for_pdf(task_def_item["value"], task_def_item["type"], target_data_main)

            # ALOSグラフ
            for days_val_str in graph_days_to_pre_generate:
                days_val_int = int(days_val_str)
                key = get_pdf_gen_chart_cache_key(f"ALOS_{display_name_for_graphs}", days_val_int, None, "alos_pdf", compute_pdf_gen_data_hash(data_for_current_task_graphs))
                buffer_val = main_process_chart_cache.get(key)
                if buffer_val is None and not data_for_current_task_graphs.empty:
                    img_buf = create_alos_chart_for_pdf(data_for_current_task_graphs, display_name_for_graphs, latest_date_for_batch, 30, MATPLOTLIB_FONT_NAME, days_to_show=days_val_int)
                    if img_buf: 
                        buffer_val = img_buf.getvalue()
                        main_process_chart_cache[key] = buffer_val
                if buffer_val: 
                    graph_buffers_for_task["alos"][days_val_str] = buffer_val
            
            # 患者数推移グラフ（目標値付き）
            patient_chart_types = {"all": target_all, "weekday": target_weekday, "holiday": target_holiday}
            for type_key, target_val in patient_chart_types.items():
                data_subset = data_for_current_task_graphs
                if type_key == "weekday" and "平日判定" in data_for_current_task_graphs.columns: 
                    data_subset = data_for_current_task_graphs[data_for_current_task_graphs["平日判定"] == "平日"]
                elif type_key == "holiday" and "平日判定" in data_for_current_task_graphs.columns: 
                    data_subset = data_for_current_task_graphs[data_for_current_task_graphs["平日判定"] == "休日"]
                
                if data_subset.empty and type_key != "all": 
                    continue

                for days_val_str in graph_days_to_pre_generate:
                    days_val_int = int(days_val_str)
                    key = get_pdf_gen_chart_cache_key(f"Patient_{type_key}_{display_name_for_graphs}", days_val_int, target_val, f"patient_{type_key}_pdf", compute_pdf_gen_data_hash(data_subset))
                    buffer_val = main_process_chart_cache.get(key)
                    if buffer_val is None and not data_subset.empty:
                        debug_print(f"グラフ生成: {display_name_for_graphs} {type_key} (目標値: {target_val})")
                        img_buf = create_patient_chart_with_target_wrapper(
                            data_subset, 
                            title=f"{display_name_for_graphs} {type_key.capitalize()}推移({days_val_int}日)", 
                            days=days_val_int, 
                            target_value=target_val, 
                            font_name_for_mpl_to_use=MATPLOTLIB_FONT_NAME
                        )
                        if img_buf: 
                            buffer_val = img_buf.getvalue()
                            main_process_chart_cache[key] = buffer_val
                    if buffer_val: 
                        graph_buffers_for_task[f"patient_{type_key}"][days_val_str] = buffer_val
            
            # 二軸グラフ
            for days_val_str in graph_days_to_pre_generate:
                days_val_int = int(days_val_str)
                key = get_pdf_gen_chart_cache_key(f"DualAxis_{display_name_for_graphs}", days_val_int, None, "dual_axis_pdf", compute_pdf_gen_data_hash(data_for_current_task_graphs))
                buffer_val = main_process_chart_cache.get(key)
                if buffer_val is None and not data_for_current_task_graphs.empty:
                    img_buf = create_dual_axis_chart_for_pdf(data_for_current_task_graphs, title=f"{display_name_for_graphs} 患者移動({days_val_int}日)", days=days_val_int, font_name_for_mpl_to_use=MATPLOTLIB_FONT_NAME)
                    if img_buf: 
                        buffer_val = img_buf.getvalue()
                        main_process_chart_cache[key] = buffer_val
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
                progress_val = int(10 + ( (i+1) / num_task_defs) * 15)
                progress_callback(progress_val / 100.0, f"グラフ準備中: {i+1}/{num_task_defs}")
        
        del df_main, target_data_main, task_definitions_list
        gc.collect()

        total_tasks_to_process = len(tasks_for_worker_with_buffers)
        if progress_callback: 
            progress_callback(0.25, f"タスク準備完了 (合計: {total_tasks_to_process}件)")
        
        if max_workers is None:
            cpu_cores = multiprocessing.cpu_count()
            max_workers = max(1, min(cpu_cores -1 if cpu_cores > 1 else 1, 4))
        
        zip_archive_buffer = BytesIO()
        with zipfile.ZipFile(zip_archive_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf_archive:
            date_suffix_str = latest_date_for_batch.strftime("%Y%m%d")
            pdfs_completed = 0
            
            if total_tasks_to_process == 0:
                if progress_callback: 
                    progress_callback(1.0, "処理対象なし（除外病棟等により全て除外）")
                debug_print("一括PDF生成: 処理対象なし")
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
                        if "診療科別" in title_from_worker: 
                            folder_prefix = "診療科別/"
                        elif "病棟別" in title_from_worker: 
                            folder_prefix = "病棟別/"
                        pdf_file_name_in_zip = f"{folder_prefix}入院患者数予測_{safe_pdf_title}_{date_suffix_str}.pdf"
                        zipf_archive.writestr(pdf_file_name_in_zip, pdf_content_io_obj.getvalue())
                        pdfs_completed +=1
                        pdf_content_io_obj.close()
            
                if progress_callback and total_tasks_to_process > 0 :
                    current_progress_val = int(25 + (pdfs_completed / total_tasks_to_process) * 75)
                    progress_callback(min(100, current_progress_val) / 100.0, f"PDF生成中: {pdfs_completed}/{total_tasks_to_process} 完了")
            
        batch_end_time_main = time.time()
        total_batch_duration = batch_end_time_main - batch_start_time
        if progress_callback: 
            progress_callback(1.0, f"処理完了! ({pdfs_completed}件) 所要時間: {total_batch_duration:.1f}秒")
        
        zip_archive_buffer.seek(0)
        return zip_archive_buffer

    except Exception as e_main_batch:
        debug_print(f"一括PDF生成(MP)のメイン処理でエラー: {e_main_batch}")
        import traceback
        debug_print(traceback.format_exc())
        if progress_callback: 
            progress_callback(1.0, f"エラーが発生しました: {str(e_main_batch)}")
        return BytesIO()
    finally:
        try:
            import shutil
            shutil.rmtree(temp_dir_main, ignore_errors=True)
        except Exception as e_cleanup:
            debug_print(f"一時ディレクトリの削除に失敗: {e_cleanup}")


def batch_generate_pdfs_full_optimized(
    df, mode="all", landscape=False, target_data=None, 
    progress_callback=None, use_parallel=True, max_workers=None, fast_mode=True
    ):
    if df is None or df.empty:
        if progress_callback: 
            progress_callback(0, "データがありません。")
        debug_print("batch_generate_pdfs_full_optimized: 分析対象のデータフレームが空です。")
        return BytesIO()

    if progress_callback: 
        progress_callback(0, "処理開始...")
    
    if use_parallel:
        return batch_generate_pdfs_mp_optimized(df, mode, landscape, target_data, progress_callback, max_workers, fast_mode)
    else:
        # シングルプロセス版（簡略化のため省略）
        debug_print("Sequential processing not fully implemented in this version.")
        return BytesIO()