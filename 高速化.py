# batch_processor.py の改良版

import concurrent.futures
from multiprocessing import Manager
import pickle

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
            MATPLOTLIB_FONT_NAME, days_to_show=days
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
                    font_name_for_mpl_to_use=MATPLOTLIB_FONT_NAME
                )
                if buf:
                    results[f'patient_{chart_type}'][str(days)] = buf.getvalue()
    
    # 二軸グラフ
    for days in days_list:
        buf = create_dual_axis_chart_for_pdf(
            data, 
            title=f"{display_name} 患者移動({days}日)",
            days=days,
            font_name_for_mpl_to_use=MATPLOTLIB_FONT_NAME
        )
        if buf:
            results['dual_axis'][str(days)] = buf.getvalue()
    
    return results

def batch_generate_pdfs_mp_optimized_v2(
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
    
    # タスク定義の準備
    graph_tasks = {}
    pdf_tasks = []
    
    # ... (タスク定義のコードは既存と同様) ...
    
    # グラフ生成タスクの準備
    task_id = 0
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
            'days_list': settings['days']
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
    
    # クリーンアップ
    try:
        import shutil
        shutil.rmtree(temp_dir_main, ignore_errors=True)
    except Exception:
        pass
    
    total_time = time.time() - batch_start_time
    if progress_callback:
        progress_callback(1.0, f"完了! 処理時間: {total_time:.1f}秒")
    
    return zip_buffer

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
    












# 追加の最適化オプション
# グラフ生成の最適化設定を追加
def create_optimized_chart_settings(quality='medium'):
    """品質設定に基づいてグラフ生成パラメータを返す"""
    settings = {
        'low': {
            'dpi': 72,
            'figure_size': (8, 4),
            'line_width': 1.5,
            'marker_size': 4,
            'grid_alpha': 0.5
        },
        'medium': {
            'dpi': 120,
            'figure_size': (10, 5.5),
            'line_width': 2,
            'marker_size': 6,
            'grid_alpha': 0.7
        },
        'high': {
            'dpi': 150,
            'figure_size': (12, 6),
            'line_width': 2.5,
            'marker_size': 8,
            'grid_alpha': 0.8
        }
    }
    return settings.get(quality, settings['medium'])

# メモリ効率的なデータ処理
def optimize_dataframe_for_pdf(df):
    """PDF生成用にデータフレームを最適化"""
    df_optimized = df.copy()
    
    # 数値型の最適化
    for col in df_optimized.select_dtypes(include=['float64']).columns:
        df_optimized[col] = df_optimized[col].astype('float32')
    
    for col in df_optimized.select_dtypes(include=['int64']).columns:
        max_val = df_optimized[col].max()
        if max_val < 32767:
            df_optimized[col] = df_optimized[col].astype('int16')
        else:
            df_optimized[col] = df_optimized[col].astype('int32')
    
    # カテゴリ型の最適化
    for col in ['病棟コード', '診療科名', '平日判定']:
        if col in df_optimized.columns:
            df_optimized[col] = df_optimized[col].astype('category')
    
    return df_optimized