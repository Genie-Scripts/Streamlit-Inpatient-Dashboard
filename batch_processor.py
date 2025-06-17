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
import concurrent.futures
from multiprocessing import Manager
import pickle

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
# chart.py からはここでは直接インポートしない (pdf_generator経由で使用)

def find_department_code_in_targets_for_pdf(dept_name, target_data_df, metric_name='日平均在院患者数'):
    """診療科名に対応する部門コードを目標値データから探す（PDF用）"""
    if target_data_df is None or target_data_df.empty:
        return None, False
    
    # 直接一致をチェック
    test_rows = target_data_df[
        (target_data_df['部門コード'].astype(str) == str(dept_name).strip()) |
        (target_data_df.get('部門名', pd.Series()).astype(str) == str(dept_name).strip())
    ]
    if not test_rows.empty:
        return str(test_rows.iloc[0]['部門コード']), True
    
    # 部分一致をチェック
    dept_name_clean = str(dept_name).strip()
    for _, row in target_data_df.iterrows():
        dept_code = str(row['部門コード'])
        dept_name_in_target = str(row.get('部門名', ''))
        if dept_name_clean in dept_code or dept_code in dept_name_clean:
            return dept_code, True
        if dept_name_clean in dept_name_in_target or dept_name_in_target in dept_name_clean:
            return dept_code, True
    
    # 正規化一致をチェック（スペースや特殊文字を無視）
    dept_name_normalized = re.sub(r'[^\w]', '', dept_name_clean)
    for _, row in target_data_df.iterrows():
        dept_code = str(row['部門コード'])
        dept_code_normalized = re.sub(r'[^\w]', '', dept_code)
        if dept_name_normalized and dept_code_normalized:
            if dept_name_normalized == dept_code_normalized:
                return dept_code, True
    
    return None, False

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

def generate_graph_batch_parallel(tasks, max_workers=None):
    """グラフを並列で一括生成"""
    if max_workers is None:
        max_workers = min(multiprocessing.cpu_count(), 8)
    
    graph_results = {}
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {}
        
        for task_id, task_params in tasks.items():
            future = executor.submit(generate_single_graph_set, task_params)
            future_to_task[future] = task_id
        
        for future in concurrent.futures.as_completed(future_to_task):
            task_id = future_to_task[future]
            try:
                result = future.result()
                graph_results[task_id] = result
            except Exception as e:
                print(f"グラフ生成エラー (task_id: {task_id}): {e}")
                graph_results[task_id] = None
    
    return graph_results

def generate_single_graph_set(params):
    """単一タスクのグラフセットを生成"""
    data = params['data']
    display_name = params['display_name']
    latest_date = params['latest_date']
    targets = params['targets']
    days_list = params['days_list']
    font_name = params.get('font_name', MATPLOTLIB_FONT_NAME)
    
    results = {
        'alos': {},
        'patient_all': {},
        'patient_weekday': {},
        'patient_holiday': {},
        'dual_axis': {}
    }
    
    # ALOSグラフ
    for days in days_list:
        buf = create_alos_chart_for_pdf(
            data, display_name, latest_date, 30, 
            font_name, days_to_show=days
        )
        if buf:
            results['alos'][str(days)] = buf.getvalue()
    
    # 患者数グラフ（全日・平日・休日）
    for chart_type, target_val in targets.items():
        data_subset = data
        if chart_type == 'weekday' and '平日判定' in data.columns:
            data_subset = data[data['平日判定'] == '平日']
        elif chart_type == 'holiday' and '平日判定' in data.columns:
            data_subset = data[data['平日判定'] == '休日']
        
        if not data_subset.empty:
            for days in days_list:
                buf = create_patient_chart_with_target_wrapper(
                    data_subset, 
                    title=f"{display_name} {chart_type}推移({days}日)",
                    days=days,
                    target_value=target_val,
                    font_name_for_mpl_to_use=font_name
                )
                if buf:
                    results[f'patient_{chart_type}'][str(days)] = buf.getvalue()
    
    # 二軸グラフ
    for days in days_list:
        buf = create_dual_axis_chart_for_pdf(
            data, 
            title=f"{display_name} 患者移動({days}日)",
            days=days,
            font_name_for_mpl_to_use=font_name
        )
        if buf:
            results['dual_axis'][str(days)] = buf.getvalue()
    
    return results

def batch_generate_pdfs_mp_optimized(
    df_main, mode="all", landscape=False, target_data_main=None,
    progress_callback=None, max_workers=None, fast_mode=True,
    graph_resolution='medium'  # 'low', 'medium', 'high'
):
    """高速化版PDF一括生成"""
    batch_start_time = time.time()
    
    # 解像度設定
    resolution_settings = {
        'low': {'dpi': 100, 'days': [90]},
        'medium': {'dpi': 120, 'days': [90, 180]},
        'high': {'dpi': 150, 'days': [90, 180, 365]}
    }
    settings = resolution_settings.get(graph_resolution, resolution_settings['medium'])
    
    # CPUコア数に基づいてワーカー数を決定（より積極的に）
    if max_workers is None:
        cpu_count = multiprocessing.cpu_count()
        max_workers = min(cpu_count, 16)  # 最大16プロセスまで拡張
    
    if progress_callback:
        progress_callback(0.05, f"データ準備中... (使用プロセス数: {max_workers})")
    
    # データの準備
    temp_dir_main = tempfile.mkdtemp()
    df_path_main = os.path.join(temp_dir_main, "main_data.feather")
    df_main.reset_index(drop=True).to_feather(df_path_main)
    
    target_data_path_main = None
    if target_data_main is not None and not target_data_main.empty:
        target_data_path_main = os.path.join(temp_dir_main, "target_data.feather")
        target_data_main.reset_index(drop=True).to_feather(target_data_path_main)
    
    try:
        # 最新日付の取得
        summaries_for_latest_date = generate_filtered_summaries(df_main)
        latest_date_for_batch = summaries_for_latest_date.get("latest_date", pd.Timestamp.now().normalize())
        
        if progress_callback:
            progress_callback(0.10, "PDF生成タスクとグラフを準備中...")
        
        # 表示名マッピング準備
        dept_display_map = {}
        ward_display_map = {}
        if target_data_main is not None and not target_data_main.empty and '部門コード' in target_data_main.columns and '部門名' in target_data_main.columns:
            for _, row in target_data_main.iterrows():
                if pd.notna(row['部門コード']) and pd.notna(row['部門名']):
                    code_str = str(row['部門コード'])
                    dept_display_map[code_str] = row['部門名']
                    ward_display_map[code_str] = row['部門名']
        
        unique_wards = df_main["病棟コード"].astype(str).unique()
        for ward in unique_wards:
            if ward not in ward_display_map:
                match = re.match(r'0*(\d+)([A-Za-z]*)', ward)
                if match:
                    ward_display_map[ward] = f"{match.group(1)}{match.group(2)}病棟"
                else:
                    ward_display_map[ward] = ward
        
        unique_depts = df_main["診療科名"].unique()
        for dept in unique_depts:
            if dept not in dept_display_map:
                dept_display_map[dept] = dept
        
        # タスク定義の準備
        task_definitions_list = []
        if mode == "all_only_filter":
            task_definitions_list.append({
                "type": "all", 
                "value": "全体", 
                "display_name": "全体", 
                "data_for_graphs": df_main.copy()
            })
        else:
            if mode == "all":
                task_definitions_list.append({
                    "type": "all", 
                    "value": "全体", 
                    "display_name": "全体", 
                    "data_for_graphs": df_main.copy()
                })
            if mode == "all" or mode == "dept":
                for dept_val in unique_depts:
                    task_definitions_list.append({
                        "type": "dept", 
                        "value": dept_val, 
                        "display_name": dept_display_map.get(dept_val, dept_val),
                        "data_for_graphs": df_main[df_main["診療科名"] == dept_val].copy()
                    })
            if mode == "all" or mode == "ward":
                for ward_val in unique_wards:
                    task_definitions_list.append({
                        "type": "ward", 
                        "value": ward_val, 
                        "display_name": ward_display_map.get(ward_val, ward_val),
                        "data_for_graphs": df_main[df_main["病棟コード"] == ward_val].copy()
                    })
        
        # グラフ生成タスクの準備
        graph_tasks = {}
        pdf_tasks = []
        task_id = 0
        
        # get_targets_for_pdf関数は既存のものを使用
        def get_targets_for_pdf(task_value, task_type, target_data_df):
            # 既存のget_targets_for_pdf関数の内容をそのまま使用
            t_all, t_wd, t_hd = None, None, None
            if target_data_df is None or target_data_df.empty: 
                return t_all, t_wd, t_hd
            
            # 指標タイプの列名を特定
            indicator_col_name = '指標タイプ' if '指標タイプ' in target_data_df.columns else None
            period_col_name = '区分' if '区分' in target_data_df.columns else '期間区分' if '期間区分' in target_data_df.columns else None
            
            if not indicator_col_name or not period_col_name:
                # 旧形式の目標値データの場合
                filter_code = task_value if task_type != "all" else "全体"
                
                # 全体の場合、複数の可能性をチェック
                if task_type == "all":
                    possible_codes = ["000", "全体", "病院全体", "病院", "総合", "0"]
                    for code in possible_codes:
                        target_rows_df = target_data_df[
                            (target_data_df['部門コード'].astype(str) == code) |
                            (target_data_df.get('部門名', pd.Series()).astype(str) == code)
                        ]
                        if not target_rows_df.empty:
                            break
                else:
                    # 診療科・病棟の場合は柔軟に検索
                    if task_type == "dept":
                        actual_code, found = find_department_code_in_targets_for_pdf(task_value, target_data_df)
                        if found:
                            filter_code = actual_code
                    
                    target_rows_df = target_data_df[target_data_df['部門コード'].astype(str) == str(filter_code)]
                
                if not target_rows_df.empty:
                    for _, row_t in target_rows_df.iterrows():
                        val_t = row_t.get('目標値')
                        if pd.notna(val_t):
                            period = row_t.get('区分', row_t.get('期間区分', ''))
                            if period == '全日': t_all = float(val_t)
                            elif period == '平日': t_wd = float(val_t)
                            elif period == '休日': t_hd = float(val_t)
            else:
                # 新形式の目標値データの場合
                metric_name = '日平均在院患者数'
                
                # 全体の場合
                if task_type == "all":
                    possible_codes = ["000", "全体", "病院全体", "病院", "総合", "0"]
                    for code in possible_codes:
                        mask = (
                            ((target_data_df['部門コード'].astype(str) == code) |
                            (target_data_df.get('部門名', pd.Series()).astype(str) == code)) &
                            (target_data_df[indicator_col_name] == metric_name)
                        )
                        filtered_rows = target_data_df[mask]
                        if not filtered_rows.empty:
                            for _, row in filtered_rows.iterrows():
                                period = row[period_col_name]
                                value = row.get('目標値')
                                if pd.notna(value):
                                    if period == '全日': t_all = float(value)
                                    elif period == '平日': t_wd = float(value)
                                    elif period == '休日': t_hd = float(value)
                            break
                else:
                    # 診療科・病棟の場合
                    actual_code = task_value
                    if task_type == "dept":
                        found_code, found = find_department_code_in_targets_for_pdf(task_value, target_data_df, metric_name)
                        if found:
                            actual_code = found_code
                    
                    mask = (
                        (target_data_df['部門コード'].astype(str) == str(actual_code)) &
                        (target_data_df[indicator_col_name] == metric_name)
                    )
                    filtered_rows = target_data_df[mask]
                    for _, row in filtered_rows.iterrows():
                        period = row[period_col_name]
                        value = row.get('目標値')
                        if pd.notna(value):
                            if period == '全日': t_all = float(value)
                            elif period == '平日': t_wd = float(value)
                            elif period == '休日': t_hd = float(value)
            
            return t_all, t_wd, t_hd
        
        for task_def in task_definitions_list:
            task_id += 1
            
            # 目標値の取得
            target_all, target_weekday, target_holiday = get_targets_for_pdf(
                task_def["value"], task_def["type"], target_data_main
            )
            
            graph_tasks[task_id] = {
                'data': task_def["data_for_graphs"],
                'display_name': task_def["display_name"],
                'latest_date': latest_date_for_batch,
                'targets': {
                    'all': target_all,
                    'weekday': target_weekday,
                    'holiday': target_holiday
                },
                'days_list': settings['days'],
                'font_name': MATPLOTLIB_FONT_NAME
            }
            
            pdf_tasks.append({
                'task_id': task_id,
                'filter_type': task_def["type"],
                'filter_value': task_def["value"],
                'display_name': task_def["display_name"]
            })
        
        if progress_callback:
            progress_callback(0.1, f"グラフ生成中... ({len(graph_tasks)}セット)")
        
        # グラフを並列生成
        graph_results = generate_graph_batch_parallel(graph_tasks, max_workers=max_workers)
        
        if progress_callback:
            progress_callback(0.5, "PDF生成中...")
        
        # PDF生成タスクの実行
        pdf_generation_tasks = []
        for pdf_task in pdf_tasks:
            task_id = pdf_task['task_id']
            graphs = graph_results.get(task_id, {})
            
            if graphs:
                pdf_generation_tasks.append((
                    df_path_main,
                    pdf_task['filter_type'],
                    pdf_task['filter_value'],
                    pdf_task['display_name'],
                    latest_date_for_batch.isoformat(),
                    landscape,
                    target_data_path_main,
                    fast_mode,
                    graphs.get('alos', {}),
                    {
                        'all': graphs.get('patient_all', {}),
                        'weekday': graphs.get('patient_weekday', {}),
                        'holiday': graphs.get('patient_holiday', {})
                    },
                    graphs.get('dual_axis', {})
                ))
        
        # PDF生成を並列実行
        zip_buffer = create_zip_from_pdfs_parallel(
            pdf_generation_tasks, 
            latest_date_for_batch,
            max_workers=max_workers,
            progress_callback=progress_callback
        )
        
        total_time = time.time() - batch_start_time
        if progress_callback:
            progress_callback(1.0, f"完了! 処理時間: {total_time:.1f}秒")
        
        return zip_buffer
        
    except Exception as e:
        print(f"一括PDF生成(V2)のメイン処理でエラー: {e}")
        import traceback
        print(traceback.format_exc())
        if progress_callback:
            progress_callback(1.0, f"エラーが発生しました: {str(e)}")
        return BytesIO()
    finally:
        try:
            import shutil
            shutil.rmtree(temp_dir_main, ignore_errors=True)
        except Exception:
            pass

def create_zip_from_pdfs_parallel(pdf_tasks, latest_date, max_workers, progress_callback=None):
    """PDFを並列生成してZIPファイルを作成"""
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        date_suffix = latest_date.strftime("%Y%m%d")
        completed = 0
        total = len(pdf_tasks)
        
        # PDFを並列生成
        with multiprocessing.Pool(processes=max_workers) as pool:
            pdf_results = pool.starmap(process_pdf_in_worker_revised, pdf_tasks)
        
        # 結果をZIPに追加
        for result in pdf_results:
            if result:
                title, pdf_content = result
                if pdf_content and pdf_content.getbuffer().nbytes > 0:
                    safe_title = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in title)
                    folder = ""
                    if "診療科別" in title:
                        folder = "診療科別/"
                    elif "病棟別" in title:
                        folder = "病棟別/"
                    
                    filename = f"{folder}入院患者数予測_{safe_title}_{date_suffix}.pdf"
                    zipf.writestr(filename, pdf_content.getvalue())
                    completed += 1
                    
                    if progress_callback and total > 0:
                        progress = 0.5 + (completed / total) * 0.5
                        progress_callback(progress, f"PDF生成中: {completed}/{total}")
    
    zip_buffer.seek(0)
    return zip_buffer

def batch_generate_pdfs_full_optimized(
    df, mode="all", landscape=False, target_data=None, 
    progress_callback=None, use_parallel=True, max_workers=None, fast_mode=True
    ):
    if df is None or df.empty:
        if progress_callback: progress_callback(0, "データがありません。")
        # st.warning("分析対象のデータフレームが空です。") # ここではUI要素は使わない
        print("batch_generate_pdfs_full_optimized: 分析対象のデータフレームが空です。")
        return BytesIO()

    if progress_callback: progress_callback(0, "処理開始...")
    
    if use_parallel:
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
        # ... (batch_generate_pdfs_mp_optimized と同様のタスク定義ロジック) ...
        # (表示名マッピングも同様に)
        dept_display_map_seq = {dept: dept for dept in df["診療科名"].unique()} # 簡易版
        ward_display_map_seq = {ward: ward for ward in df["病棟コード"].astype(str).unique()} # 簡易版
        if target_data is not None and not target_data.empty:
            # (より詳細なマッピングロジックをここにも適用可能)
            pass

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
        
        try: shutil.rmtree(temp_dir_seq, ignore_errors=True)
        except Exception: pass
        zip_buffer_seq.seek(0)
        return zip_buffer_seq