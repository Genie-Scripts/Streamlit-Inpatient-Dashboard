# data_processing_tab.py (修正案)

import warnings
warnings.filterwarnings('ignore', category=FutureWarning) # FutureWarning を無視
import streamlit as st
import pandas as pd
import numpy as np # NaNチェックなどで使用される可能性
import time
import os
import tempfile
import gc
import psutil # メモリ使用量取得のため
import logging # logging を追加
logger = logging.getLogger(__name__)

# integrated_preprocessing と loader から必要な関数をインポート
from integrated_preprocessing import (
    integrated_preprocess_data, calculate_file_hash, efficient_duplicate_check
)
from loader import load_files
from forecast import generate_filtered_summaries
from utils import initialize_all_mappings, create_dept_mapping_table


# --- 定数 ---
EXCEL_USE_COLUMNS = [
    "病棟コード", "診療科名", "日付", "在院患者数",
    "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"
]
EXCEL_DTYPES = {
    "病棟コード": str,
    "診療科名": str,
    "在院患者数": float,
    "入院患者数": float,
    "緊急入院患者数": float,
    "退院患者数": float,
    "死亡患者数": float
}

# --- パフォーマンス監視関数 ---
def log_memory_usage():
    try:
        process = psutil.Process()
        mem_info = process.memory_info()
        mem_usage_mb = mem_info.rss / (1024 * 1024)
        mem_percent = process.memory_percent()
        system_mem = psutil.virtual_memory()
        system_mem_percent = system_mem.percent
        available_mb = system_mem.available / (1024 * 1024)
        return {
            'process_mb': mem_usage_mb, 'process_percent': mem_percent,
            'system_percent': system_mem_percent, 'available_mb': available_mb
        }
    except Exception as e:
        logger.error(f"メモリ情報取得エラー: {e}", exc_info=True)
        return None

def perform_cleanup(deep=False):
    if deep and 'df' in st.session_state and st.session_state.df is not None:
        if 'filtered_results' in st.session_state and st.session_state.get('filtered_results') != st.session_state.get('all_results'):
            st.session_state.filtered_results = None
        if 'forecast_model_results' in st.session_state:
            st.session_state.forecast_model_results = None
    try:
        temp_dir_root = tempfile.gettempdir()
        app_temp_files_pattern = os.path.join(temp_dir_root, "integrated_dashboard_temp_*")
        import glob
        for temp_file_path in glob.glob(app_temp_files_pattern):
            try:
                if os.path.isfile(temp_file_path): os.unlink(temp_file_path)
                elif os.path.isdir(temp_file_path): import shutil; shutil.rmtree(temp_file_path, ignore_errors=True)
            except Exception as e_file_del: logger.warning(f"一時ファイルの削除中にエラー: {e_file_del}")
    except Exception as e_temp_clean: logger.warning(f"一時ファイルクリーンアップ処理中にエラー: {e_temp_clean}")
    gc.collect()
    time.sleep(0.1)
    gc.collect()


# --- データ処理の関数 ---
def get_app_data_dir():
    base_temp_dir = tempfile.gettempdir()
    app_data_dir = os.path.join(base_temp_dir, "integrated_dashboard_data")
    if not os.path.exists(app_data_dir):
        try: os.makedirs(app_data_dir, exist_ok=True)
        except OSError as e: st.error(f"データ保存ディレクトリの作成に失敗: {app_data_dir}\n{e}"); return None
    return app_data_dir

def get_base_file_info(app_data_dir):
    if app_data_dir is None: return None
    info_path = os.path.join(app_data_dir, "base_file_info.json")
    if os.path.exists(info_path):
        try:
            import json;
            with open(info_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"ベースファイル情報の読み込みエラー: {e}", exc_info=True)
            return None
    return None

def save_base_file_info(app_data_dir, file_name, file_size, file_hash):
    if app_data_dir is None: return
    info_path = os.path.join(app_data_dir, "base_file_info.json")
    info = {"file_name": file_name, "file_size": file_size, "file_hash": file_hash}
    try:
        import json;
        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"ベースファイル情報の保存エラー: {e}", exc_info=True)

def debug_target_file_processing(target_data, search_keywords=['全体', '病院全体', '病院']):
    debug_info = {'file_loaded': target_data is not None, 'columns': [], 'shape': (0,0), 'search_results': {}, 'sample_data': None}
    if target_data is not None:
        debug_info['columns'] = list(target_data.columns); debug_info['shape'] = target_data.shape
        debug_info['sample_data'] = target_data.head(3).to_dict('records') if len(target_data) > 0 else []
        for keyword in search_keywords:
            results = []
            for col in target_data.columns:
                if target_data[col].dtype == 'object':
                    try:
                        matches = target_data[target_data[col].astype(str).str.contains(keyword, na=False, case=False)]
                        if len(matches) > 0:
                            results.append({'column': col, 'matches': len(matches), 'sample_values': matches[col].unique()[:3].tolist()})
                    except Exception as e_search: logger.debug(f"目標値ファイルデバッグ検索中エラー ({col}, {keyword}): {e_search}")
            debug_info['search_results'][keyword] = results
    return debug_info


def extract_targets_from_file(target_data):
    if target_data is None or target_data.empty: return None, None
    debug_info = debug_target_file_processing(target_data)
    search_patterns = [('部門コード', ['全体', '病院', '総合']), ('部門名', ['病院全体', '全体', '病院', '総合']),
                       ('診療科名', ['病院全体', '全体', '病院', '総合']), ('科名', ['病院全体', '全体', '病院', '総合'])]
    target_row = None; used_pattern = None
    for col_name, keywords in search_patterns:
        if col_name in target_data.columns:
            for keyword in keywords:
                try:
                    mask = target_data[col_name].astype(str).str.contains(keyword, na=False, case=False)
                    matches = target_data[mask]
                    if len(matches) > 0: target_row = matches.iloc[0]; used_pattern = f"{col_name}='{keyword}'"; logger.info(f"目標値データ検索成功: {used_pattern}"); break
                except Exception as e_pat: logger.debug(f"目標値検索パターンエラー ({col_name}, {keyword}): {e_pat}")
            if target_row is not None: break
    if target_row is None:
        logger.warning("目標値データで「全体」に相当する行が見つかりませんでした。")
        logger.warning(f"利用可能な列: {list(target_data.columns)}")
        logger.warning(f"サンプルデータ:\n{target_data.head()}")
        return None, debug_info

    target_days = None; target_admissions = None
    days_columns = ['延べ在院日数目標', '在院日数目標', '目標在院日数', '延べ在院日数', '在院日数'];
    admission_columns = ['新入院患者数目標', '入院患者数目標', '目標入院患者数', '新入院患者数', '入院患者数']

    for col in days_columns:
        if col in target_data.columns: # target_data で列の存在を確認
            try:
                value = target_row[col] # target_rowはNoneでないことが上で保証されている想定
                if pd.notna(value) and str(value).strip() != '':
                    target_days = float(str(value).replace(',', '').replace('人日', '').strip())
                    logger.info(f"延べ在院日数目標を取得: {target_days} (列: {col})")
                    break
            except (ValueError, TypeError) as e:
                logger.warning(f"延べ在院日数目標の変換エラー (列: {col}): {e}")

    for col in admission_columns:
        if col in target_data.columns: # target_data で列の存在を確認
            try:
                value = target_row[col] # target_rowはNoneでないことが上で保証されている想定
                if pd.notna(value) and str(value).strip() != '':
                    target_admissions = float(str(value).replace(',', '').replace('人', '').strip())
                    logger.info(f"新入院患者数目標を取得: {target_admissions} (列: {col})")
                    break
            except (ValueError, TypeError) as e:
                logger.warning(f"新入院患者数目標の変換エラー (列: {col}): {e}")

    if (target_days is None or target_admissions is None) and '目標値' in target_data.columns: # target_data で列の存在を確認
        try:
            general_target = float(str(target_row['目標値']).replace(',', '').strip()) # target_rowはNoneでないことが上で保証されている想定
            if target_days is None:
                target_days = general_target
                logger.info(f"一般目標値から延べ在院日数目標を設定: {target_days}")
            if target_admissions is None: # target_daysが設定されていてもadmissionsが未設定なら
                target_admissions = general_target
                logger.info(f"一般目標値から新入院患者数目標を設定: {target_admissions}")
        except (ValueError, TypeError) as e:
            logger.warning(f"一般目標値の変換エラー: {e}")

    extracted_targets = {'target_days': target_days, 'target_admissions': target_admissions, 'used_pattern': used_pattern, 'source_row': target_row.to_dict() if target_row is not None else None}
    return extracted_targets, debug_info


def process_data_with_progress(base_file_uploader_obj, new_files_uploader_list, target_file_uploader_obj, progress_bar): # 引数名変更
    """ファイルをロードし、前処理を実行する（進捗表示付き・エラーハンドリング強化版）"""
    try:
        start_time_total = time.time()
        st.session_state.performance_metrics = st.session_state.get('performance_metrics', {})
        st.session_state.performance_metrics['data_conversion_time'] = 0

        progress_bar.progress(5, text="1. ファイルデータの読み込み準備中...")
        load_start_time = time.time()

        df_raw, processed_files_info = load_files(
            base_file_uploader_obj, # 引数名変更
            new_files_uploader_list, # 引数名変更
            usecols_excel=EXCEL_USE_COLUMNS,
            dtype_excel=EXCEL_DTYPES
        )
        load_end_time = time.time()
        st.session_state.performance_metrics['data_load_time'] = load_end_time - load_start_time

        successful_reads = 0
        failed_files = []
        if processed_files_info:
            for info in processed_files_info:
                if info['status'] == 'success':
                    successful_reads += 1
                else:
                    failed_files.append(f"{info['name']} ({info['message']})")
            if successful_reads > 0:
                st.success(f"{successful_reads} 件のファイルが正常に読み込まれました。")
            if failed_files:
                st.warning(f"{len(failed_files)} 件のファイルの読み込みに失敗またはスキップされました:")
                for f_info in failed_files:
                    st.caption(f"- {f_info}")
        elif df_raw.empty:
            st.error("読み込むデータがありません。固定ファイルまたは追加ファイルをアップロードしてください。")
            progress_bar.progress(100, text="データ読み込み失敗。")
            return False, None, None, None, None

        if df_raw.empty:
            st.error("読み込まれたデータが空です。ファイル内容を確認してください。")
            progress_bar.progress(100, text="データ内容が空です。")
            return False, None, None, None, None

        progress_bar.progress(20, text="1. ファイル読み込み完了。データ結合中...")

        source_info_cols = ['_source_file_', '_source_type_']
        cols_to_drop_before_dup_check = [col for col in source_info_cols if col in df_raw.columns]
        df_raw_for_dup_check = df_raw.drop(columns=cols_to_drop_before_dup_check, errors='ignore')

        progress_bar.progress(22, text="2. 重複チェック中...")
        df_processed_duplicates = efficient_duplicate_check(df_raw_for_dup_check)
        del df_raw_for_dup_check, df_raw
        gc.collect()

        target_data = None
        target_file_debug_info = None
        extracted_targets = None
        if target_file_uploader_obj: # 引数名変更
            progress_bar.progress(25, text="目標値ファイルの読み込み中...")
            try:
                target_file_uploader_obj.seek(0)
                encodings_to_try = ['utf-8', 'shift_jis', 'cp932', 'utf-8-sig']
                target_df_temp = None
                for enc in encodings_to_try:
                    try:
                        target_df_temp = pd.read_csv(target_file_uploader_obj, encoding=enc) # 引数名変更
                        logger.info(f"目標値ファイルを{enc}で読み込み成功")
                        target_file_uploader_obj.seek(0) # 引数名変更
                        break
                    except UnicodeDecodeError:
                        logger.debug(f"目標値ファイルのエンコード試行失敗: {enc}")
                        target_file_uploader_obj.seek(0) # 引数名変更
                        continue
                if target_df_temp is None or target_df_temp.empty:
                    st.warning("目標値ファイルの読み込みに失敗しました（適切なエンコードが見つからないか、ファイルが空です）。")
                else:
                    target_data = target_df_temp
                    extracted_targets, target_file_debug_info = extract_targets_from_file(target_data)
                    st.session_state.target_file_debug_info = target_file_debug_info
                    st.session_state.extracted_targets = extracted_targets
                    st.success("目標値ファイルの読み込みと解析が完了しました。")
            except Exception as e_target:
                st.warning(f"目標値ファイルの処理中にエラーが発生しました: {str(e_target)}")
                logger.error(f"目標値ファイル処理エラー: {e_target}", exc_info=True)
                target_data = None
        else:
            logger.info("目標値ファイルはアップロードされていません。")
        progress_bar.progress(28, text="目標値ファイルの処理完了。")

        progress_bar.progress(30, text="3. データの前処理中...")
        preprocess_start_time = time.time()
        df_final, validation_results = integrated_preprocess_data(df_processed_duplicates, target_data_df=target_data)
        preprocess_end_time = time.time()
        st.session_state.performance_metrics['processing_time'] = preprocess_end_time - preprocess_start_time
        del df_processed_duplicates
        gc.collect()

        if df_final is None or df_final.empty:
            progress_bar.progress(100, text="データ前処理に失敗しました。")
            st.error("データ前処理の結果、有効なデータが残りませんでした。")
            if validation_results and validation_results.get('errors'):
                for err_msg in validation_results.get('errors', []): st.error(err_msg)
            return False, None, None, None, validation_results

        progress_bar.progress(50, text="4. データの検証中...")
        st.session_state.validation_results = validation_results
        if validation_results:
            if validation_results.get("warnings"):
                with st.expander("データ検証の警告", expanded=True):
                    for warn_msg in validation_results["warnings"]: st.warning(warn_msg)
            if validation_results.get("errors"):
                st.error("データ検証で以下のエラーが検出されました。処理を継続できません。")
                for err_msg in validation_results["errors"]: st.error(err_msg)
                return False, None, None, None, validation_results
        
        progress_bar.progress(85, text="5. 全体データの集計中...")
        all_results = None
        try:
            all_results = generate_filtered_summaries(df_final, None, None)
        except Exception as e_summary:
            st.warning(f"全体データの集計中にエラーが発生しました: {e_summary}")
            logger.error(f"全体データ集計エラー: {e_summary}", exc_info=True)
        
        if all_results is None or not all_results.get("summary", pd.DataFrame()).empty is False:
            default_latest_date = df_final["日付"].max() if not df_final.empty and "日付" in df_final.columns else pd.Timestamp.now().normalize()
            all_results = {
                "latest_date": default_latest_date,
                "summary": pd.DataFrame(), "weekday": pd.DataFrame(), "holiday": pd.DataFrame(),
                "monthly_all": pd.DataFrame(), "monthly_weekday": pd.DataFrame(), "monthly_holiday": pd.DataFrame(),
            }
            if df_final is not None and not df_final.empty :
                 st.warning("全体結果の集計に一部失敗したため、限定的な結果になります。")

        latest_data_date_obj = all_results.get("latest_date", pd.Timestamp.now().normalize())

        progress_bar.progress(95, text="6. マッピング情報の初期化中...")
        if df_final is not None and not df_final.empty:
            initialize_all_mappings(df_final, target_data)
            logger.info("診療科および病棟のマッピング情報を初期化・更新しました。")
        
        total_time_taken = time.time() - start_time_total
        logger.info(f"データ処理全体完了。処理時間: {total_time_taken:.1f}秒, レコード数: {len(df_final) if df_final is not None else 0}")
        
        if 'performance_logs' not in st.session_state: st.session_state.performance_logs = []
        st.session_state.performance_logs.append({
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"), 'operation': 'データ処理全体', 'duration': total_time_taken,
            'details': {
                'rows': len(df_final) if df_final is not None else 0,
                'columns': len(df_final.columns) if df_final is not None and hasattr(df_final, 'columns') else 0,
                'files_new': len(new_files_uploader_list) if new_files_uploader_list else 0, # 引数名変更
            }
        })

        progress_bar.progress(100, text=f"データの処理が完了しました。処理時間: {total_time_taken:.1f}秒")
        return True, df_final, target_data, all_results, latest_data_date_obj

    except Exception as e_main:
        logger.error(f"データ処理のメインプロセスでエラーが発生しました: {e_main}", exc_info=True)
        progress_bar.progress(100, text=f"エラーが発生しました: {str(e_main)}")
        st.error(f"データ処理中に予期せぬエラーが発生しました: {str(e_main)}")
        st.error(traceback.format_exc())
        return False, None, None, None, None


def create_data_processing_tab():
    st.header("📊 データ入力")

    with st.expander("ℹ️ データ入力について", expanded=False):
        st.markdown("""
        **データ入力の流れ:**
        1. **固定ファイル**: メインとなる入院患者データ（必須またはキャッシュ利用）
        2. **追加ファイル**: 補完データ（オプション、複数可）
        3. **目標値ファイル**: 部門別目標設定（オプション、CSV形式）

        **対応ファイル形式 (入院データ):** Excel (.xlsx, .xls)
        **必要な列名 (柔軟に対応試行):**
        病棟コード, 診療科名, 日付, 在院患者数, 入院患者数, 緊急入院患者数, 退院患者数, 死亡患者数
        """)

    if 'data_processing_initialized' not in st.session_state:
        st.session_state.data_processing_initialized = True
        st.session_state.data_processed = False
        st.session_state.df = None
        st.session_state.target_data = None
        st.session_state.all_results = None
        st.session_state.validation_results = None
        st.session_state.latest_data_date_str = "データ読込前"
        st.session_state.target_file_debug_info = None
        st.session_state.extracted_targets = None
        if 'performance_metrics' not in st.session_state:
            st.session_state.performance_metrics = {'data_load_time': 0, 'data_conversion_time': 0, 'processing_time': 0}

    st.subheader("📁 ファイルアップロード")
    col_f1_dp, col_f2_dp, col_f3_dp = st.columns(3) # 変数名変更
    with col_f1_dp:
        base_file_uploader_widget_dp = st.file_uploader( # 変数名変更
            "固定ファイル (Excel)", type=["xlsx", "xls"], key="base_file_dp_tab_v3", # キー変更
            help="メインのExcelファイル。過去処理済みの同一ファイルはキャッシュ利用可（アップロード不要）。"
        )
    with col_f2_dp:
        new_files_uploader_widget_dp = st.file_uploader( # 変数名変更
            "追加ファイル (Excel)", type=["xlsx", "xls"], accept_multiple_files=True,
            key="new_files_dp_tab_v3", help="補完データファイル（複数可）。" # キー変更
        )
    with col_f3_dp:
        target_file_uploader_widget_dp = st.file_uploader( # 変数名変更
            "目標値ファイル (CSV)", type=["csv"], key="target_file_dp_tab_v3", # キー変更
            help="部門別の目標値データ（CSV形式）。"
        )

    app_data_dir_val_dp = get_app_data_dir() # 変数名変更
    parquet_base_path_val_dp = os.path.join(app_data_dir_val_dp, "processed_base_data.parquet") if app_data_dir_val_dp else None # 変数名変更
    can_process_now_dp = False # 変数名変更
    if base_file_uploader_widget_dp:
        can_process_now_dp = True
    elif parquet_base_path_val_dp and os.path.exists(parquet_base_path_val_dp):
        can_process_now_dp = True
    elif new_files_uploader_widget_dp:
        can_process_now_dp = True

    if can_process_now_dp:
        if not st.session_state.get('data_processed', False):
            process_button_key_dp = "process_data_button_dp_tab_v3" # キー変更
            if st.button("データ処理を実行", key=process_button_key_dp, use_container_width=True):
                base_file_to_process_dp = base_file_uploader_widget_dp # 変数名変更
                new_files_to_process_dp = new_files_uploader_widget_dp if new_files_uploader_widget_dp else [] # 変数名変更
                target_file_to_process_dp = target_file_uploader_widget_dp # 変数名変更

                progress_bar_ui_main_dp = st.progress(0, text="データ処理を開始します...") # 変数名変更
                success_flag_dp, df_result_main_dp, target_data_result_main_dp, all_results_main_dp, latest_date_obj_main_dp = process_data_with_progress( # 変数名変更
                    base_file_to_process_dp, new_files_to_process_dp, target_file_to_process_dp, progress_bar_ui_main_dp
                )
                if success_flag_dp and df_result_main_dp is not None and not df_result_main_dp.empty:
                    st.session_state.df = df_result_main_dp
                    st.session_state.target_data = target_data_result_main_dp
                    st.session_state.all_results = all_results_main_dp
                    st.session_state.data_processed = True
                    if isinstance(latest_date_obj_main_dp, pd.Timestamp):
                        st.session_state.latest_data_date_str = latest_date_obj_main_dp.strftime("%Y年%m月%d日")
                    else:
                        st.session_state.latest_data_date_str = "データ処理完了 (日付不明)"
                    st.success(f"データの処理が完了しました。最新データ日付: {st.session_state.latest_data_date_str}")
                    st.session_state.mappings_initialized_after_processing = True
                    perform_cleanup(deep=True)
                    st.rerun()
                else:
                    if latest_date_obj_main_dp is None and not success_flag_dp:
                        st.error("データ処理中に致命的なエラーが発生しました。詳細はログを確認してください。")
                    elif latest_date_obj_main_dp and isinstance(latest_date_obj_main_dp, dict) and latest_date_obj_main_dp.get('errors'):
                        st.error("データ検証でエラーが検出されました。詳細は上記メッセージを確認してください。")
        else:
            st.success(f"データ処理済み（最新データ日付: {st.session_state.latest_data_date_str}）")
            if st.session_state.get('target_data') is not None: st.success("目標値データも読み込み済みです。")
            else: st.info("目標値データは読み込まれていません。")

            if st.session_state.get('df') is not None:
                df_display_main_dp = st.session_state.df # 変数名変更
                with st.expander("データ概要", expanded=True):
                    col1_sum_dp, col2_sum_dp, col3_sum_dp = st.columns(3) # 変数名変更
                    with col1_sum_dp:
                        if not df_display_main_dp.empty and '日付' in df_display_main_dp.columns:
                            min_dt_dp = df_display_main_dp['日付'].min() # 変数名変更
                            max_dt_dp = df_display_main_dp['日付'].max() # 変数名変更
                            if pd.notna(min_dt_dp) and pd.notna(max_dt_dp):
                                st.metric("データ期間", f"{min_dt_dp.strftime('%Y/%m/%d')} - {max_dt_dp.strftime('%Y/%m/%d')}")
                            else: st.metric("データ期間", "N/A (無効な日付)")
                        else: st.metric("データ期間", "N/A")
                    with col2_sum_dp: st.metric("総レコード数", f"{len(df_display_main_dp):,}")
                    with col3_sum_dp: st.metric("病棟数", f"{df_display_main_dp['病棟コード'].nunique() if '病棟コード' in df_display_main_dp.columns else 'N/A'}")
                    col1_sum2_dp, col2_sum2_dp, col3_sum2_dp = st.columns(3) # 変数名変更
                    with col1_sum2_dp: st.metric("診療科数", f"{df_display_main_dp['診療科名'].nunique() if '診療科名' in df_display_main_dp.columns else 'N/A'}")
                    with col2_sum2_dp: st.metric("平日数", f"{(df_display_main_dp['平日判定'] == '平日').sum()}" if "平日判定" in df_display_main_dp.columns else "N/A")
                    with col3_sum2_dp: st.metric("休日数", f"{(df_display_main_dp['平日判定'] == '休日').sum()}" if "平日判定" in df_display_main_dp.columns else "N/A")

                    perf_metrics_disp_dp = st.session_state.get('performance_metrics', {}) # 変数名変更
                    if perf_metrics_disp_dp:
                        st.subheader("処理パフォーマンス")
                        pcol1_dp, pcol2_dp, pcol3_dp, pcol4_dp = st.columns(4) # 変数名変更
                        with pcol1_dp: st.metric("データ読込時間", f"{perf_metrics_disp_dp.get('data_load_time', 0):.1f}秒")
                        with pcol2_dp: pass
                        with pcol3_dp: st.metric("データ処理時間", f"{perf_metrics_disp_dp.get('processing_time', 0):.1f}秒")
                        with pcol4_dp:
                            try: mem_info_disp_dp = log_memory_usage(); # 変数名変更
                                if mem_info_disp_dp: st.metric("現在のメモリ使用", f"{mem_info_disp_dp.get('process_mb', 0):.1f} MB ({mem_info_disp_dp.get('process_percent', 0):.1f}%)")
                                else: st.metric("メモリ情報", "取得不可")
                            except Exception: st.metric("メモリ情報", "取得不可")

                validation_res_main_dp = st.session_state.get('validation_results') # 変数名変更
                if validation_res_main_dp:
                    if validation_res_main_dp.get("warnings") or validation_res_main_dp.get("info") or validation_res_main_dp.get("errors"):
                        with st.expander("データ検証結果", expanded=False):
                            for err_msg_disp_dp in validation_res_main_dp.get("errors", []): st.error(err_msg_disp_dp) # 変数名変更
                            for info_msg_disp_dp in validation_res_main_dp.get("info", []): st.info(info_msg_disp_dp) # 変数名変更
                            for warn_msg_disp_main_dp in validation_res_main_dp.get("warnings", []): st.warning(warn_msg_disp_main_dp) # 変数名変更
            
            if st.button("データをリセット (キャッシュも削除)", key="reset_data_button_dp_tab_v3", use_container_width=True): # ラベルとキー変更
                st.session_state.data_processed = False
                st.session_state.df = None; st.session_state.all_results = None; st.session_state.target_data = None
                st.session_state.validation_results = None; st.session_state.latest_data_date_str = "データ読込前"
                st.session_state.target_file_debug_info = None; st.session_state.extracted_targets = None
                st.session_state.performance_metrics = {'data_load_time': 0, 'data_conversion_time': 0, 'processing_time': 0}
                st.session_state.dept_mapping = {}; st.session_state.dept_mapping_initialized = False
                st.session_state.ward_mapping = {}; st.session_state.ward_mapping_initialized = False
                st.session_state.mappings_initialized_after_processing = False

                if app_data_dir_val_dp: # 変数名変更
                    parquet_to_delete_main_dp = os.path.join(app_data_dir_val_dp, "processed_base_data.parquet") # 変数名変更
                    info_to_delete_main_dp = os.path.join(app_data_dir_val_dp, "base_file_info.json") # 変数名変更
                    if os.path.exists(parquet_to_delete_main_dp):
                        try: os.remove(parquet_to_delete_main_dp); st.info("キャッシュされたベースデータを削除しました。")
                        except Exception as e_del_pq_dp: logger.warning(f"Parquet削除エラー: {e_del_pq_dp}") # 変数名変更
                    if os.path.exists(info_to_delete_main_dp):
                        try: os.remove(info_to_delete_main_dp)
                        except Exception as e_del_info_dp: logger.warning(f"Infoファイル削除エラー: {e_del_info_dp}") # 変数名変更
                perform_cleanup(deep=True)
                st.rerun()
    else:
        st.info("「固定ファイル」をアップロードするか、以前処理したベースデータキャッシュを利用できる状態にしてください。または「追加ファイル」のみでも処理を開始できます。")
