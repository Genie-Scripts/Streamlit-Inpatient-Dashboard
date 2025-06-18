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
import logging

# config から除外病棟設定をインポート
from config import EXCLUDED_WARDS

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
    get_chart_cache as get_pdf_gen_main_process_cache, # メインプロセス用キャッシュ取得
    cleanup_matplotlib_figure as cleanup_matplotlib_resources # クリーンアップ関数をインポート
)

# ロガーの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===========================================
# PDF最適化設定
# ===========================================
PDF_OPTIMIZATION_CONFIG = {
    # Matplotlib設定
    'matplotlib_dpi': 100,  # 150→100に削減
    'figure_size_reduction': 0.8,  # サイズを20%削減
    'grid_alpha': 0.5,  # グリッドの透明度を下げて高速化
    
    # ReportLab設定
    'table_font_size': 7,  # 8→7に削減
    'margin_reduction': 0.8,  # マージンを20%削減
    
    # 処理設定
    'max_cache_entries': 50,  # キャッシュエントリ数制限
    'data_sample_threshold': 30000,  # データサンプリング閾値
    'memory_warning_threshold': 1500,  # メモリ警告閾値（MB）
}

# ===========================================
# パフォーマンス監視クラス
# ===========================================
class PDFPerformanceMonitor:
    """PDF生成の性能監視クラス"""
    
    def __init__(self):
        self.start_time = None
        self.memory_start = None
        
    def start_monitoring(self, task_name):
        """監視開始"""
        self.start_time = time.time()
        try:
            self.memory_start = psutil.Process().memory_info().rss / 1024 / 1024
            logger.debug(f"開始: {task_name} (メモリ: {self.memory_start:.1f}MB)")
        except Exception:
            self.memory_start = 0
        
    def end_monitoring(self, task_name):
        """監視終了"""
        if self.start_time:
            duration = time.time() - self.start_time
            try:
                memory_end = psutil.Process().memory_info().rss / 1024 / 1024
                memory_diff = memory_end - self.memory_start
                
                # 注意が必要な場合のみログ出力
                if duration > 3.0 or abs(memory_diff) > 100:
                    logger.warning(f"完了: {task_name} - 時間: {duration:.2f}s, メモリ変化: {memory_diff:+.1f}MB")
                else:
                    logger.debug(f"完了: {task_name} - 時間: {duration:.2f}s")
            except Exception:
                logger.debug(f"完了: {task_name} - 時間: {duration:.2f}s")

# ===========================================
# リソースクリーンアップ関数
# ===========================================
def cleanup_matplotlib_resources():
    """Matplotlibリソースの完全クリーンアップ"""
    try:
        import matplotlib.pyplot as plt
        plt.close('all')  # 全図を閉じる
        plt.clf()  # 現在の図をクリア
        plt.cla()  # 現在の軸をクリア
        gc.collect()  # ガベージコレクション
    except Exception as e:
        logger.debug(f"Matplotlibクリーンアップエラー: {e}")

# ===========================================
# セーフティラッパー
# ===========================================
def safe_pdf_worker_wrapper(func):
    """PDFワーカー関数の安全なラッパー"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except MemoryError:
            logger.error(f"メモリ不足エラー (PID: {os.getpid()})")
            cleanup_matplotlib_resources()
            gc.collect()
            return None
        except Exception as e:
            logger.error(f"PDF生成エラー (PID: {os.getpid()}): {e}")
            return None
        finally:
            # 強制的なクリーンアップ
            cleanup_matplotlib_resources()
    return wrapper

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
    最適化版：性能監視とエラーハンドリング強化
    """
    
    # 性能監視開始
    monitor = PDFPerformanceMonitor()
    monitor.start_monitoring(f"PDF生成: {display_name}")
    
    try:
        pid = os.getpid()
        logger.debug(f"PID {pid}: Worker for '{display_name}' started")

        df_worker = pd.read_feather(df_path)
        latest_date_worker = pd.Timestamp(latest_date_str)
        
        target_data_worker = None
        if target_data_path and os.path.exists(target_data_path):
            target_data_worker = pd.read_feather(target_data_path)
        
        # *** 除外病棟のフィルタリングを追加 ***
        if '病棟コード' in df_worker.columns and EXCLUDED_WARDS:
            original_count = len(df_worker)
            df_worker = df_worker[~df_worker['病棟コード'].isin(EXCLUDED_WARDS)]
            removed_count = original_count - len(df_worker)
            if removed_count > 0:
                logger.debug(f"PID {pid}: 除外病棟フィルタリングで{removed_count}件のレコードを除外")
        
        # データサイズチェックと最適化
        if len(df_worker) > PDF_OPTIMIZATION_CONFIG['data_sample_threshold']:
            logger.info(f"PID {pid}: 大量データ検出 ({len(df_worker):,}件). 最新データに絞り込み...")
            df_worker = df_worker.sort_values('日付').tail(20000)
            logger.info(f"PID {pid}: データを{len(df_worker):,}件に削減")
        
        current_data_for_tables_worker = df_worker.copy() # テーブル生成用
        current_filter_code_worker = "全体"
        title_prefix_for_pdf = "全体"

        if filter_type == "dept":
            current_data_for_tables_worker = df_worker[df_worker["診療科名"] == filter_value].copy()
            current_filter_code_worker = filter_value
            title_prefix_for_pdf = f"診療科別 {display_name}"
        elif filter_type == "ward":
            # *** 病棟別の場合、さらに除外病棟チェック ***
            if filter_value in EXCLUDED_WARDS:
                logger.info(f"PID {pid}: 除外病棟 '{filter_value}' のPDF生成をスキップ")
                return None
            current_data_for_tables_worker = df_worker[df_worker["病棟コード"] == filter_value].copy()
            current_filter_code_worker = str(filter_value)
            title_prefix_for_pdf = f"病棟別 {display_name}"
        
        if current_data_for_tables_worker.empty and filter_type != "all":
            logger.debug(f"PID {pid}: Filtered data for tables empty for {title_prefix_for_pdf}. Skipping.")
            return None # データがない場合はNoneを返す
            
        summaries_worker = generate_filtered_summaries(
            current_data_for_tables_worker, 
            "診療科名" if filter_type == "dept" else ("病棟コード" if filter_type == "ward" else None),
            filter_value if filter_type != "all" else None
        )
        
        if not summaries_worker:
            logger.debug(f"PID {pid}: Failed to generate summaries for {title_prefix_for_pdf}.")
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

    except MemoryError:
        logger.error(f"メモリ不足エラー (PID: {os.getpid()})")
        cleanup_matplotlib_resources()
        gc.collect()
        return None
    except Exception as e:
        logger.error(f"PID {os.getpid()}: Error in worker for {filter_type} {filter_value} ('{display_name}'): {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return None
    finally:
        # 性能監視終了
        monitor.end_monitoring(f"PDF生成: {display_name}")
        # 強制的なクリーンアップ
        cleanup_matplotlib_resources()

def get_optimized_worker_count(max_workers=None):
    """最適化されたワーカー数を算出"""
    if max_workers is not None:
        return max_workers
        
    cpu_cores = multiprocessing.cpu_count()
    try:
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        
        # メモリ制約を考慮（1GB per worker）
        memory_based_workers = max(1, int(available_memory_gb / 1.0))
        cpu_based_workers = max(1, min(cpu_cores - 1, 6))  # 最大6ワーカー
        
        optimized_workers = min(memory_based_workers, cpu_based_workers)
        logger.info(f"最適化ワーカー数: {optimized_workers} (CPU: {cpu_cores}, メモリ: {available_memory_gb:.1f}GB)")
        
        return optimized_workers
    except Exception:
        # フォールバック
        return max(1, min(cpu_cores - 1 if cpu_cores > 1 else 1, 4))

def optimize_main_data_if_needed(df_main):
    """メイン データの最適化（必要に応じて）"""
    # メモリ監視と最適化
    try:
        process = psutil.Process()
        memory_usage_mb = process.memory_info().rss / 1024 / 1024
        
        if memory_usage_mb > PDF_OPTIMIZATION_CONFIG['memory_warning_threshold']:
            logger.warning(f"高メモリ使用量検出: {memory_usage_mb:.1f}MB. 最適化を実行...")
            gc.collect()
            
            # データサイズの削減
            if len(df_main) > PDF_OPTIMIZATION_CONFIG['data_sample_threshold']:
                logger.info(f"大量データ検出 ({len(df_main):,}件). 最新データに絞り込み...")
                df_main = df_main.sort_values('日付').tail(25000)
                logger.info(f"データを{len(df_main):,}件に削減")
                
        return df_main
    except Exception as e:
        logger.debug(f"データ最適化中にエラー: {e}")
        return df_main

def batch_generate_pdfs_mp_optimized(df_main, mode="all", landscape=False, target_data_main=None, 
                                          progress_callback=None, max_workers=None, fast_mode=True):
    """最適化されたバッチPDF生成"""
    
    batch_start_time = time.time()
    
    # データ最適化
    df_main = optimize_main_data_if_needed(df_main)
    
    # ワーカー数の動的調整
    max_workers = get_optimized_worker_count(max_workers)
        
    if progress_callback: 
        progress_callback(0.05, "データを準備中...")

    # *** メインデータから除外病棟をフィルタリング ***
    df_filtered = df_main.copy()
    if '病棟コード' in df_filtered.columns and EXCLUDED_WARDS:
        original_count = len(df_filtered)
        df_filtered = df_filtered[~df_filtered['病棟コード'].isin(EXCLUDED_WARDS)]
        removed_count = original_count - len(df_filtered)
        if removed_count > 0:
            logger.info(f"一括PDF生成: 除外病棟フィルタリングで{removed_count}件のレコードを除外")

    temp_dir_main = tempfile.mkdtemp()
    df_path_main = os.path.join(temp_dir_main, "main_data.feather")
    df_filtered.reset_index(drop=True).to_feather(df_path_main)
    
    target_data_path_main = None
    if target_data_main is not None and not target_data_main.empty:
        target_data_path_main = os.path.join(temp_dir_main, "target_data.feather")
        target_data_main.reset_index(drop=True).to_feather(target_data_path_main)

    # メインプロセスでのみ使用するキャッシュ (pdf_generator.py から取得)
    main_process_chart_cache = get_pdf_gen_main_process_cache()

    try:
        summaries_for_latest_date = generate_filtered_summaries(df_filtered)
        latest_date_for_batch = summaries_for_latest_date.get("latest_date", pd.Timestamp.now().normalize())
        
        if progress_callback: 
            progress_callback(0.10, "PDF生成タスクとグラフを準備中...")
        
        tasks_for_worker_with_buffers = []
        
        # 表示名マッピング準備
        dept_display_map = {}
        ward_display_map = {}
        if target_data_main is not None and not target_data_main.empty and '部門コード' in target_data_main.columns and '部門名' in target_data_main.columns:
            for _, row in target_data_main.iterrows():
                if pd.notna(row['部門コード']) and pd.notna(row['部門名']):
                    code_str = str(row['部門コード'])
                    # 診療科も病棟も同じ「部門コード」「部門名」からマッピングする想定
                    # 必要であれば部門種別などで区別するロジックを追加
                    dept_display_map[code_str] = row['部門名']
                    ward_display_map[code_str] = row['部門名']
        
        # *** 除外病棟を除いたユニークな病棟リストを取得 ***
        unique_wards = df_filtered["病棟コード"].astype(str).unique()
        if EXCLUDED_WARDS:
            unique_wards = [ward for ward in unique_wards if ward not in EXCLUDED_WARDS]
        
        for ward in unique_wards:
            if ward not in ward_display_map:
                match = re.match(r'0*(\d+)([A-Za-z]*)', ward)
                if match: 
                    ward_display_map[ward] = f"{match.group(1)}{match.group(2)}病棟"
                else: 
                    ward_display_map[ward] = ward
        
        unique_depts = df_filtered["診療科名"].unique()
        for dept in unique_depts:
            if dept not in dept_display_map:
                dept_display_map[dept] = dept

        graph_days_to_pre_generate = ["90"] if fast_mode else ["90", "180"]
        
        task_definitions_list = []
        if mode == "all_only_filter":
            task_definitions_list.append({
                "type": "all", 
                "value": "全体", 
                "display_name": "全体", 
                "data_for_graphs": df_filtered.copy()
            })
        else:
            if mode == "all":
                task_definitions_list.append({
                    "type": "all", 
                    "value": "全体", 
                    "display_name": "全体", 
                    "data_for_graphs": df_filtered.copy()
                })
            if mode == "all" or mode == "dept":
                for dept_val in unique_depts:
                    task_definitions_list.append({
                        "type": "dept", 
                        "value": dept_val, 
                        "display_name": dept_display_map.get(dept_val, dept_val),
                        "data_for_graphs": df_filtered[df_filtered["診療科名"] == dept_val].copy()
                    })
            if mode == "all" or mode == "ward":
                # *** 除外病棟を除いた病棟のみでタスクを作成 ***
                for ward_val in unique_wards:
                    task_definitions_list.append({
                        "type": "ward", 
                        "value": ward_val, 
                        "display_name": ward_display_map.get(ward_val, ward_val),
                        "data_for_graphs": df_filtered[df_filtered["病棟コード"] == ward_val].copy()
                    })

        def get_targets_for_pdf(task_value, task_type, target_data_df):
            """PDF用の目標値を取得（改善版）"""
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

        num_task_defs = len(task_definitions_list)
        for i, task_def_item in enumerate(task_definitions_list):
            graph_buffers_for_task = {
                "alos": {}, 
                "patient_all": {}, 
                "patient_weekday": {}, 
                "patient_holiday": {}, 
                "dual_axis": {}
            }
            data_for_current_task_graphs = task_def_item["data_for_graphs"]
            display_name_for_graphs = task_def_item["display_name"]
            
            target_all, target_weekday, target_holiday = get_targets_for_pdf(
                task_def_item["value"], 
                task_def_item["type"], 
                target_data_main
            )

            # ALOSグラフ
            for days_val_str in graph_days_to_pre_generate:
                days_val_int = int(days_val_str)
                key = get_pdf_gen_chart_cache_key(
                    f"ALOS_{display_name_for_graphs}", 
                    days_val_int, 
                    None, 
                    "alos_pdf", 
                    compute_pdf_gen_data_hash(data_for_current_task_graphs)
                )
                buffer_val = main_process_chart_cache.get(key)
                if buffer_val is None and not data_for_current_task_graphs.empty:
                    img_buf = create_alos_chart_for_pdf(
                        data_for_current_task_graphs, 
                        display_name_for_graphs, 
                        latest_date_for_batch, 
                        30, 
                        MATPLOTLIB_FONT_NAME, 
                        days_to_show=days_val_int
                    )
                    if img_buf: 
                        buffer_val = img_buf.getvalue()
                        main_process_chart_cache[key] = buffer_val
                if buffer_val: 
                    graph_buffers_for_task["alos"][days_val_str] = buffer_val
            
            # 患者数推移グラフ
            patient_chart_types = {
                "all": target_all, 
                "weekday": target_weekday, 
                "holiday": target_holiday
            }
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
                    key = get_pdf_gen_chart_cache_key(
                        f"Patient_{type_key}_{display_name_for_graphs}", 
                        days_val_int, 
                        target_val, 
                        f"patient_{type_key}_pdf", 
                        compute_pdf_gen_data_hash(data_subset)
                    )
                    buffer_val = main_process_chart_cache.get(key)
                    if buffer_val is None and not data_subset.empty:
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
                key = get_pdf_gen_chart_cache_key(
                    f"DualAxis_{display_name_for_graphs}", 
                    days_val_int, 
                    None, 
                    "dual_axis_pdf", 
                    compute_pdf_gen_data_hash(data_for_current_task_graphs)
                )
                buffer_val = main_process_chart_cache.get(key)
                if buffer_val is None and not data_for_current_task_graphs.empty:
                    img_buf = create_dual_axis_chart_for_pdf(
                        data_for_current_task_graphs, 
                        title=f"{display_name_for_graphs} 患者移動({days_val_int}日)", 
                        days=days_val_int, 
                        font_name_for_mpl_to_use=MATPLOTLIB_FONT_NAME
                    )
                    if img_buf: 
                        buffer_val = img_buf.getvalue()
                        main_process_chart_cache[key] = buffer_val
                if buffer_val: 
                    graph_buffers_for_task["dual_axis"][days_val_str] = buffer_val
            
            tasks_for_worker_with_buffers.append(
                (df_path_main, 
                 task_def_item["type"], 
                 task_def_item["value"], 
                 task_def_item["display_name"], 
                 latest_date_for_batch.isoformat(), 
                 landscape, 
                 target_data_path_main, 
                 fast_mode,
                 graph_buffers_for_task["alos"], 
                 {"all": graph_buffers_for_task["patient_all"], 
                  "weekday": graph_buffers_for_task["patient_weekday"], 
                  "holiday": graph_buffers_for_task["patient_holiday"]},
                 graph_buffers_for_task["dual_axis"])
            )
            if progress_callback and num_task_defs > 0:
                progress_val = int(10 + ((i+1) / num_task_defs) * 15) # 10-25%
                progress_callback(progress_val / 100.0, f"グラフ準備中: {i+1}/{num_task_defs}")
        
        # メモリ解放
        del df_main, df_filtered, target_data_main, task_definitions_list
        gc.collect()

        total_tasks_to_process = len(tasks_for_worker_with_buffers)
        if progress_callback: 
            progress_callback(0.25, f"タスク準備完了 (合計: {total_tasks_to_process}件)")
        
        zip_archive_buffer = BytesIO()
        with zipfile.ZipFile(zip_archive_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf_archive:
            date_suffix_str = latest_date_for_batch.strftime("%Y%m%d")
            pdfs_completed = 0
            
            if total_tasks_to_process == 0: # タスクがない場合は空のZIP
                if progress_callback: 
                    progress_callback(1.0, "処理対象なし")
                logger.info("一括PDF生成: 処理対象なし")
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
                        pdfs_completed += 1
                        pdf_content_io_obj.close()
            
                if progress_callback and total_tasks_to_process > 0:
                    current_progress_val = int(25 + (pdfs_completed / total_tasks_to_process) * 75)
                    progress_callback(min(100, current_progress_val) / 100.0, f"PDF生成中: {pdfs_completed}/{total_tasks_to_process} 完了")
            
        batch_end_time_main = time.time()
        total_batch_duration = batch_end_time_main - batch_start_time
        if progress_callback: 
            progress_callback(1.0, f"処理完了! ({pdfs_completed}件) 所要時間: {total_batch_duration:.1f}秒")
        
        logger.info(f"一括PDF生成完了: {pdfs_completed}件, 所要時間: {total_batch_duration:.1f}秒")
        
        zip_archive_buffer.seek(0)
        return zip_archive_buffer

    except Exception as e_main_batch:
        logger.error(f"一括PDF生成(MP)のメイン処理でエラー: {e_main_batch}")
        import traceback
        logger.debug(traceback.format_exc())
        if progress_callback: 
            progress_callback(1.0, f"エラーが発生しました: {str(e_main_batch)}")
        return BytesIO()
    finally:
        try:
            import shutil
            shutil.rmtree(temp_dir_main, ignore_errors=True)
        except Exception as e_cleanup:
            logger.debug(f"一時ディレクトリの削除に失敗: {e_cleanup}")


def batch_generate_pdfs_full_optimized(
    df, mode="all", landscape=False, target_data=None, 
    progress_callback=None, use_parallel=True, max_workers=None, fast_mode=True
    ):
    """
    最適化されたバッチPDF生成のメイン関数
    """
    if df is None or df.empty:
        if progress_callback: 
            progress_callback(0, "データがありません。")
        logger.warning("batch_generate_pdfs_full_optimized: 分析対象のデータフレームが空です。")
        return BytesIO()

    if progress_callback: 
        progress_callback(0, "処理開始...")
    
    if use_parallel:
        return batch_generate_pdfs_mp_optimized(
            df, mode, landscape, target_data, progress_callback, max_workers, fast_mode
        )
    else:
        # シングルプロセス版 (フォールバックまたはデバッグ用)
        logger.info("Parallel processing disabled. Using sequential PDF generation.")
        return batch_generate_pdfs_sequential(
            df, mode, landscape, target_data, progress_callback, fast_mode
        )

def batch_generate_pdfs_sequential(
    df, mode="all", landscape=False, target_data=None, 
    progress_callback=None, fast_mode=True
    ):
    """
    シングルプロセス版PDF生成（フォールバック用）
    """
    temp_dir_seq = tempfile.mkdtemp()
    df_path_seq = os.path.join(temp_dir_seq, "main_data_seq.feather")
    df.reset_index(drop=True).to_feather(df_path_seq)
    
    target_data_path_seq = None
    if target_data is not None and not target_data.empty:
        target_data_path_seq = os.path.join(temp_dir_seq, "target_data_seq.feather")
        target_data.reset_index(drop=True).to_feather(target_data_path_seq)

    try:
        all_summaries = generate_filtered_summaries(df)
        latest_date_seq = all_summaries.get("latest_date", pd.Timestamp.now().normalize())
        
        tasks_seq = []
        # 表示名マッピング（簡易版）
        dept_display_map_seq = {dept: dept for dept in df["診療科名"].unique()}
        ward_display_map_seq = {ward: ward for ward in df["病棟コード"].astype(str).unique()}

        if mode == "all_only_filter": 
            tasks_seq.append({"type": "all", "value": "全体", "display_name": "全体"})
        else:
            if mode == "all": 
                tasks_seq.append({"type": "all", "value": "全体", "display_name": "全体"})
            if mode == "all" or mode == "dept":
                for dept in sorted(df["診療科名"].unique()): 
                    tasks_seq.append({
                        "type": "dept", 
                        "value": dept, 
                        "display_name": dept_display_map_seq.get(dept, dept)
                    })
            if mode == "all" or mode == "ward":
                for ward in sorted(df["病棟コード"].astype(str).unique()): 
                    # *** 除外病棟チェック ***
                    if ward not in EXCLUDED_WARDS:
                        tasks_seq.append({
                            "type": "ward", 
                            "value": ward, 
                            "display_name": ward_display_map_seq.get(ward, ward)
                        })

        zip_buffer_seq = BytesIO()
        with zipfile.ZipFile(zip_buffer_seq, 'w', zipfile.ZIP_DEFLATED) as zipf_seq:
            date_suffix_seq = latest_date_seq.strftime("%Y%m%d")
            completed_seq = 0
            total_seq = len(tasks_seq)
            
            for task_item in tasks_seq:
                # シングルプロセスでは簡易的にグラフバッファを生成
                current_task_data_seq = df.copy()
                if task_item["type"] == "dept": 
                    current_task_data_seq = df[df["診療科名"] == task_item["value"]].copy()
                elif task_item["type"] == "ward": 
                    current_task_data_seq = df[df["病棟コード"] == task_item["value"]].copy()

                alos_bufs_seq = {}
                if not current_task_data_seq.empty:
                    for days_str_seq in (["90"] if fast_mode else ["90", "180"]):
                        buf_io = create_alos_chart_for_pdf(
                            current_task_data_seq, 
                            task_item["display_name"], 
                            latest_date_seq, 
                            30, 
                            MATPLOTLIB_FONT_NAME, 
                            days_to_show=int(days_str_seq)
                        )
                        if buf_io: 
                            alos_bufs_seq[days_str_seq] = buf_io.getvalue()
                
                # patient_chart_buffers と dual_axis_chart_buffers は簡略化
                patient_bufs_seq = {"all": {}, "weekday": {}, "holiday": {}}
                dual_bufs_seq = {}

                result_seq = process_pdf_in_worker_revised(
                    df_path_seq, 
                    task_item["type"], 
                    task_item["value"], 
                    task_item["display_name"],
                    latest_date_seq.isoformat(), 
                    landscape, 
                    target_data_path_seq, 
                    fast_mode,
                    alos_chart_buffers_payload=alos_bufs_seq,
                    patient_chart_buffers_payload=patient_bufs_seq,
                    dual_axis_chart_buffers_payload=dual_bufs_seq
                )
                
                if result_seq:
                    title_res_seq, pdf_io_seq = result_seq
                    if pdf_io_seq and pdf_io_seq.getbuffer().nbytes > 0:
                        safe_title_seq = "".join(c if c.isalnum() else '_' for c in title_res_seq)
                        folder_seq = "診療科別/" if "診療科別" in title_res_seq else ("病棟別/" if "病棟別" in title_res_seq else "")
                        zipf_seq.writestr(
                            f"{folder_seq}入院患者数予測_{safe_title_seq}_{date_suffix_seq}.pdf", 
                            pdf_io_seq.getvalue()
                        )
                        completed_seq += 1
                        
                if progress_callback: 
                    progress_callback(
                        (completed_seq/total_seq) if total_seq > 0 else 1, 
                        f"PDF生成中 (順次): {completed_seq}/{total_seq}"
                    )
        
        zip_buffer_seq.seek(0)
        return zip_buffer_seq
        
    finally:
        try: 
            import shutil
            shutil.rmtree(temp_dir_seq, ignore_errors=True)
        except Exception: 
            pass

# ===========================================
# テスト関数
# ===========================================
def test_pdf_optimization():
    """PDF最適化のテスト関数"""
    import numpy as np
    
    logger.info("PDF最適化テストを開始します")
    
    # テストデータ作成
    test_data = pd.DataFrame({
        '日付': pd.date_range('2024-01-01', periods=1000),
        '病棟コード': ['A1', 'B2', 'C3'] * 334,
        '診療科名': ['内科', '外科', '小児科'] * 334,
        '入院患者数（在院）': np.random.randint(10, 50, 1000),
        '新入院患者数': np.random.randint(1, 10, 1000),
        '総退院患者数': np.random.randint(1, 10, 1000),
    })
    
    # 処理時間測定
    start_time = time.time()
    
    try:
        # 最適化されたPDF生成を実行
        zip_result = batch_generate_pdfs_full_optimized(
            test_data, 
            mode="all",
            fast_mode=True,
            max_workers=2,
            use_parallel=True
        )
        
        end_time = time.time()
        
        logger.info(f"テスト完了: {end_time - start_time:.2f}秒")
        logger.info(f"ZIPサイズ: {len(zip_result.getvalue()) / 1024:.1f} KB")
        
        return zip_result
        
    except Exception as e:
        logger.error(f"PDF最適化テストでエラー: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return BytesIO()

# 使用例
if __name__ == "__main__":
    # テスト実行
    result = test_pdf_optimization()
    print("PDF最適化テスト完了")