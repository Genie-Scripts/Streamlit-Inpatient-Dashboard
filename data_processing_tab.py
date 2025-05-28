import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
import streamlit as st
import pandas as pd
import numpy as np
import time
import os
import tempfile
import gc
import psutil
from integrated_preprocessing import (
    integrated_preprocess_data, calculate_file_hash, efficient_duplicate_check
)
from loader import read_excel_cached # process_uploaded_file は直接使われていないようなので一旦削除
from forecast import generate_filtered_summaries


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
    """現在のメモリ使用状況をログに出力する（改善版）"""
    try:
        process = psutil.Process()
        mem_info = process.memory_info()
        mem_usage_mb = mem_info.rss / (1024 * 1024)
        mem_percent = process.memory_percent()

        system_mem = psutil.virtual_memory()
        system_mem_percent = system_mem.percent
        available_mb = system_mem.available / (1024 * 1024)

        return {
            'process_mb': mem_usage_mb,
            'process_percent': mem_percent,
            'system_percent': system_mem_percent,
            'available_mb': available_mb
        }
    except Exception as e:
        print(f"メモリ情報取得エラー: {e}")
        return None

def perform_cleanup(deep=False):
    """メモリを解放する"""
    if deep and 'df' in st.session_state and st.session_state.df is not None:
        if 'filtered_results' in st.session_state and st.session_state.filtered_results != st.session_state.all_results:
            st.session_state.filtered_results = None
        if 'forecast_model_results' in st.session_state:
            st.session_state.forecast_model_results = None
    try:
        temp_dir_root = tempfile.gettempdir()
        app_temp_files_pattern = os.path.join(temp_dir_root, "integrated_dashboard_temp_*")
        import glob
        for temp_file_path in glob.glob(app_temp_files_pattern):
            try:
                if os.path.isfile(temp_file_path):
                    os.unlink(temp_file_path)
                elif os.path.isdir(temp_file_path):
                    import shutil
                    shutil.rmtree(temp_file_path, ignore_errors=True)
            except Exception as e:
                print(f"一時ファイルの削除中にエラー: {e}")
    except Exception as e:
        print(f"一時ファイルクリーンアップ処理中にエラー: {e}")
    gc.collect()
    time.sleep(0.1)
    gc.collect()

# --- データ処理の関数 ---
def get_app_data_dir():
    """アプリケーションのデータディレクトリを取得する"""
    base_temp_dir = tempfile.gettempdir()
    app_data_dir = os.path.join(base_temp_dir, "integrated_dashboard_data")
    if not os.path.exists(app_data_dir):
        try:
            os.makedirs(app_data_dir, exist_ok=True)
        except OSError as e:
            st.error(f"データ保存ディレクトリの作成に失敗しました: {app_data_dir}\n{e}")
            return None
    return app_data_dir

def get_base_file_info(app_data_dir):
    """キャッシュされたベースファイル情報を取得する"""
    if app_data_dir is None: return None
    info_path = os.path.join(app_data_dir, "base_file_info.json")
    if os.path.exists(info_path):
        try:
            import json
            with open(info_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"ベースファイル情報の読み込みエラー: {e}")
            return None
    return None

def save_base_file_info(app_data_dir, file_name, file_size, file_hash):
    """ベースファイル情報を保存する"""
    if app_data_dir is None: return
    info_path = os.path.join(app_data_dir, "base_file_info.json")
    info = {
        "file_name": file_name,
        "file_size": file_size,
        "file_hash": file_hash
    }
    try:
        import json
        with open(info_path, 'w') as f:
            json.dump(info, f)
    except Exception as e:
        print(f"ベースファイル情報の保存エラー: {e}")

def debug_target_file_processing(target_data, search_keywords=['全体', '病院全体', '病院']):
    """目標値ファイルのデバッグ情報を表示"""
    debug_info = {
        'file_loaded': target_data is not None,
        'columns': [],
        'shape': (0, 0),
        'search_results': {},
        'sample_data': None
    }

    if target_data is not None:
        debug_info['columns'] = list(target_data.columns)
        debug_info['shape'] = target_data.shape
        debug_info['sample_data'] = target_data.head(3).to_dict('records') if len(target_data) > 0 else []

        for keyword in search_keywords:
            results = []
            for col in target_data.columns:
                if target_data[col].dtype == 'object':
                    matches = target_data[target_data[col].astype(str).str.contains(keyword, na=False, case=False)]
                    if len(matches) > 0:
                        results.append({
                            'column': col,
                            'matches': len(matches),
                            'sample_values': matches[col].unique()[:3].tolist()
                        })
            debug_info['search_results'][keyword] = results

    return debug_info

def extract_targets_from_file(target_data):
    """目標値ファイルから目標値を抽出する（改善版）"""
    if target_data is None or target_data.empty:
        return None, None

    debug_info = debug_target_file_processing(target_data)

    search_patterns = [
        ('部門コード', ['全体', '病院', '総合']),
        ('部門名', ['病院全体', '全体', '病院', '総合']),
        ('診療科名', ['病院全体', '全体', '病院', '総合']),
        ('科名', ['病院全体', '全体', '病院', '総合'])
    ]

    target_row = None
    used_pattern = None

    for col_name, keywords in search_patterns:
        if col_name in target_data.columns:
            for keyword in keywords:
                mask = target_data[col_name].astype(str).str.contains(keyword, na=False, case=False)
                matches = target_data[mask]
                if len(matches) > 0:
                    target_row = matches.iloc[0]
                    used_pattern = f"{col_name}='{keyword}'"
                    print(f"目標値データ検索成功: {used_pattern}")
                    break
            if target_row is not None:
                break

    if target_row is None:
        print("目標値データで「全体」に相当する行が見つかりませんでした")
        print(f"利用可能な列: {list(target_data.columns)}")
        print(f"サンプルデータ:\n{target_data.head()}")
        return None, debug_info

    target_days = None
    target_admissions = None

    days_columns = ['延べ在院日数目標', '在院日数目標', '目標在院日数', '延べ在院日数', '在院日数']
    for col in days_columns:
        if col in target_data.columns:
            try:
                value = target_row[col]
                if pd.notna(value) and value != '' and str(value).strip() != '':
                    target_days = float(str(value).replace(',', '').replace('人日', '').strip())
                    print(f"延べ在院日数目標を取得: {target_days} (列: {col})")
                    break
            except (ValueError, TypeError) as e:
                print(f"延べ在院日数目標の変換エラー (列: {col}): {e}")
                continue

    admission_columns = ['新入院患者数目標', '入院患者数目標', '目標入院患者数', '新入院患者数', '入院患者数']
    for col in admission_columns:
        if col in target_data.columns:
            try:
                value = target_row[col]
                if pd.notna(value) and value != '' and str(value).strip() != '':
                    target_admissions = float(str(value).replace(',', '').replace('人', '').strip())
                    print(f"新入院患者数目標を取得: {target_admissions} (列: {col})")
                    break
            except (ValueError, TypeError) as e:
                print(f"新入院患者数目標の変換エラー (列: {col}): {e}")
                continue

    if (target_days is None or target_admissions is None) and '目標値' in target_data.columns:
        try:
            general_target = float(str(target_row['目標値']).replace(',', '').strip())
            if target_days is None:
                target_days = general_target
                print(f"一般目標値から延べ在院日数目標を設定: {target_days}")
            elif target_admissions is None:
                target_admissions = general_target
                print(f"一般目標値から新入院患者数目標を設定: {target_admissions}")
        except (ValueError, TypeError) as e:
            print(f"一般目標値の変換エラー: {e}")

    extracted_targets = {
        'target_days': target_days,
        'target_admissions': target_admissions,
        'used_pattern': used_pattern,
        'source_row': target_row.to_dict() if target_row is not None else None
    }

    return extracted_targets, debug_info

def process_data_with_progress(base_file_uploaded, new_files_uploaded, target_file_uploaded, progress_bar):
    """ファイルをロードし、前処理を実行する（進捗表示付き）"""
    try:
        start_time_total = time.time()
        df_list_for_concat = []
        app_data_dir = get_app_data_dir()
        parquet_base_path = os.path.join(app_data_dir, "processed_base_data.parquet") if app_data_dir else None
        st.session_state.performance_metrics = st.session_state.get('performance_metrics', {})
        st.session_state.performance_metrics['data_conversion_time'] = 0

        progress_bar.progress(5, text="1. ベースデータの準備中...")
        load_start_time = time.time()

        current_base_file_hash = None
        if base_file_uploaded:
            base_file_uploaded.seek(0)
            current_base_file_hash = calculate_file_hash(base_file_uploaded.read())
            base_file_uploaded.seek(0)

        saved_base_file_info = get_base_file_info(app_data_dir)
        base_data_loaded_from_parquet = False

        if parquet_base_path and os.path.exists(parquet_base_path):
            should_load_parquet = False
            if base_file_uploaded:
                if saved_base_file_info and saved_base_file_info.get("file_hash") == current_base_file_hash:
                    should_load_parquet = True
                else:
                    print("アップロードされたベースファイルが前回と異なる（または情報なし）ため、Parquetを再作成します。")
                    if os.path.exists(parquet_base_path): os.remove(parquet_base_path)
                    if os.path.exists(os.path.join(app_data_dir, "base_file_info.json")):
                        os.remove(os.path.join(app_data_dir, "base_file_info.json"))
            else:
                should_load_parquet = True

            if should_load_parquet:
                try:
                    print(f"Parquetベースファイル '{parquet_base_path}' を読み込みます。")
                    df_base = pd.read_parquet(parquet_base_path)
                    df_base['ファイルソース'] = 'ベース'
                    df_list_for_concat.append(df_base)
                    base_data_loaded_from_parquet = True
                    progress_bar.progress(10, text="1. ベースデータをParquetから読み込み完了。")
                except Exception as e:
                    st.warning(f"Parquetベースファイルの読み込みに失敗しました: {e}。Excelから読み込みます。")
                    if os.path.exists(parquet_base_path): os.remove(parquet_base_path)
                    if os.path.exists(os.path.join(app_data_dir, "base_file_info.json")):
                        os.remove(os.path.join(app_data_dir, "base_file_info.json"))
                    base_data_loaded_from_parquet = False

        if not base_data_loaded_from_parquet and base_file_uploaded:
            print("ベースファイルをExcelから読み込みます。")
            base_file_bytes = base_file_uploaded.getvalue()
            df_base_excel = read_excel_cached(base_file_bytes, usecols=EXCEL_USE_COLUMNS, dtype=EXCEL_DTYPES)
            if df_base_excel is not None and not df_base_excel.empty:
                df_base_excel['ファイルソース'] = 'ベース'
                df_list_for_concat.append(df_base_excel)
                progress_bar.progress(10, text="1. ベースデータをExcelから読み込み完了。")
                if parquet_base_path:
                    try:
                        conversion_start_time = time.time()
                        df_to_save = df_base_excel.drop(columns=['ファイルソース'], errors='ignore')
                        df_to_save.to_parquet(parquet_base_path, index=False)
                        save_base_file_info(app_data_dir,
                                            base_file_uploaded.name,
                                            base_file_uploaded.size,
                                            current_base_file_hash)
                        conversion_end_time = time.time()
                        st.session_state.performance_metrics['data_conversion_time'] = conversion_end_time - conversion_start_time
                        print(f"ベースデータをParquetとして '{parquet_base_path}' に保存しました。")
                    except Exception as e:
                        st.warning(f"ベースデータのParquet保存に失敗: {e}")
            else:
                st.warning("ベースファイルの読み込みに失敗しました。")

        successful_additional_files = 0
        if new_files_uploaded:
            progress_bar.progress(15, text="1. 追加データの読み込み中...")
            for i, file in enumerate(new_files_uploaded):
                try:
                    file_bytes = file.getvalue()
                    df_file = read_excel_cached(file_bytes, usecols=EXCEL_USE_COLUMNS, dtype=EXCEL_DTYPES)
                    if df_file is not None and not df_file.empty:
                        df_file['ファイルソース'] = f'追加_{i}'
                        df_list_for_concat.append(df_file)
                        successful_additional_files += 1
                        print(f"追加ファイル '{file.name}' の読み込み成功: {len(df_file)}行")
                    else:
                        print(f"追加ファイル '{file.name}' は期待される形式ではないため、スキップしました。")
                except Exception as e:
                    print(f"追加ファイル '{file.name}' の読み込み中にエラー: {e}")
                    continue
            if successful_additional_files > 0:
                progress_bar.progress(20, text=f"1. 追加データ {successful_additional_files}/{len(new_files_uploaded)} ファイルの読み込み完了。")
                st.info(f"追加ファイル: {successful_additional_files}/{len(new_files_uploaded)} 件が正常に読み込まれました。")
            else:
                progress_bar.progress(20, text="1. 追加データの読み込み完了（利用可能なファイルなし）。")
                if new_files_uploaded:
                    st.warning("追加ファイルはすべて期待される形式と異なるため、スキップされました。")

        load_end_time = time.time()
        st.session_state.performance_metrics['data_load_time'] = load_end_time - load_start_time

        if not df_list_for_concat:
            st.error("読み込むデータがありません。固定ファイルまたは追加ファイルをアップロードしてください。")
            progress_bar.progress(100, text="データ読み込み失敗。")
            return False, None, None, None, None

        progress_bar.progress(25, text="2. データの結合中...")
        df_raw = pd.concat(df_list_for_concat, ignore_index=True)
        # --- ここからデバッグコード ---
        print("--- [DP_TAB] DataFrame結合完了 ---")
        if not df_raw.empty:
            print(f"--- [DP_TAB] 結合後df_rawの行数: {len(df_raw)} ---")
            if "入院患者数（在院）" in df_raw.columns:
                print(f"--- [DP_TAB] 結合後df_raw['入院患者数（在院）'].dtype: {df_raw['入院患者数（在院）'].dtype} ---")
                if df_raw['入院患者数（在院）'].dtype == 'object':
                    try:
                        hyphen_exists_concat = df_raw['入院患者数（在院）'].astype(str).str.contains('-').any()
                        print(f"--- [DP_TAB] 結合後df_raw['入院患者数（在院）']にハイフン存在: {hyphen_exists_concat} ---")
                    except Exception as e_concat_debug:
                        print(f"--- [DP_TAB] 結合後df_rawデバッグエラー: {e_concat_debug} ---")
            else:
                print("--- [DP_TAB] 結合後df_rawに '入院患者数（在院）' 列なし ---")
        else:
            print("--- [DP_TAB] 結合後df_rawは空 ---")
        # --- ここまでデバッグコード ---

        progress_bar.progress(26, text="2. 重複チェック中...")
        df_raw = efficient_duplicate_check(df_raw) # この関数のログは既に出ているはず
        # --- ここからデバッグコード ---
        print("--- [DP_TAB] 最初のefficient_duplicate_check完了 ---")
        if not df_raw.empty:
            print(f"--- [DP_TAB] 最初の重複チェック後df_rawの行数: {len(df_raw)} ---")
            if "入院患者数（在院）" in df_raw.columns:
                print(f"--- [DP_TAB] 最初の重複チェック後df_raw['入院患者数（在院）'].dtype: {df_raw['入院患者数（在院）'].dtype} ---")
                if df_raw['入院患者数（在院）'].dtype == 'object':
                    try:
                        hyphen_exists_dedup1 = df_raw['入院患者数（在院）'].astype(str).str.contains('-').any()
                        print(f"--- [DP_TAB] 最初の重複チェック後df_raw['入院患者数（在院）']にハイフン存在: {hyphen_exists_dedup1} ---")
                    except Exception as e_dedup1_debug:
                        print(f"--- [DP_TAB] 最初の重複チェック後df_rawデバッグエラー: {e_dedup1_debug} ---")
            else:
                print("--- [DP_TAB] 最初の重複チェック後df_rawに '入院患者数（在院）' 列なし ---")
        else:
            print("--- [DP_TAB] 最初の重複チェック後df_rawは空 ---")
        # --- ここまでデバッグコード ---

        if 'ファイルソース' in df_raw.columns:
            df_raw = df_raw.drop(columns=['ファイルソース'], errors='ignore')
        print("--- [DP_TAB] ファイルソース列削除完了 ---") # 追加

        del df_list_for_concat
        gc.collect()
        print("--- [DP_TAB] df_list_for_concat メモリ解放完了 ---") # 追加

        target_data = None
        target_file_debug_info = None
        extracted_targets = None
        if target_file_uploaded:
            print("--- [DP_TAB] 目標値ファイル処理開始 ---") # 追加
            progress_bar.progress(28, text="目標値ファイルの読み込み中...")
            try:
                target_file_uploaded.seek(0)
                file_content = target_file_uploaded.read()
                target_file_uploaded.seek(0)
                encodings = ['utf-8', 'shift_jis', 'cp932', 'utf-8-sig']
                target_df_temp = None
                for encoding in encodings:
                    try:
                        target_df_temp = pd.read_csv(target_file_uploaded, encoding=encoding)
                        print(f"目標値ファイルを{encoding}で読み込み成功")
                        break
                    except UnicodeDecodeError:
                        target_file_uploaded.seek(0)
                        continue
                    except Exception as e:
                        print(f"目標値ファイル読み込みエラー ({encoding}): {e}")
                        target_file_uploaded.seek(0)
                        continue
                if target_df_temp is None or target_df_temp.empty:
                    st.warning("目標値ファイルの読み込みに失敗しました。")
                    target_data = None
                else:
                    target_data = target_df_temp
                    print(f"目標値ファイル読み込み成功: {target_data.shape}")
                    extracted_targets, target_file_debug_info = extract_targets_from_file(target_data)
                    st.session_state.target_file_debug_info = target_file_debug_info
                    st.session_state.extracted_targets = extracted_targets
                    try:
                        from utils import create_dept_mapping_table
                        create_dept_mapping_table(target_data)
                        print("診療科マッピングテーブルを作成しました。")
                    except ImportError:
                        print("utils.pyが見つかりません。診療科マッピングはスキップします。")
                    except Exception as e_map:
                        print(f"診療科マッピングテーブル作成中にエラー: {e_map}")
                    st.success("目標値ファイルの読み込みが完了しました。")
            except Exception as e:
                st.warning(f"目標値ファイルの読み込みに失敗しました: {str(e)}")
                target_data = None
                print(f"目標値ファイル処理エラー: {e}")
            print("--- [DP_TAB] 目標値ファイル処理完了 ---") # 追加
        else:
            print("--- [DP_TAB] 目標値ファイルなし ---") # 追加

        progress_bar.progress(30, text="2. データの前処理中...")
        preprocess_start = time.time()
        # --- ここからデバッグコード ---
        print("--- [DP_TAB] integrated_preprocess_data呼び出し直前 ---")
        if df_raw is not None and not df_raw.empty:
            print(f"--- [DP_TAB] integrated_preprocess_dataに渡すdf_rawの行数: {len(df_raw)} ---")
            if "入院患者数（在院）" in df_raw.columns:
                print(f"--- [DP_TAB] integrated_preprocess_dataに渡すdf_raw['入院患者数（在院）'].dtype: {df_raw['入院患者数（在院）'].dtype} ---")
                if df_raw['入院患者数（在院）'].dtype == 'object':
                    try:
                        hyphen_exists_before_integration = df_raw['入院患者数（在院）'].astype(str).str.contains('-').any()
                        print(f"--- [DP_TAB] integrated_preprocess_dataに渡すdf_raw['入院患者数（在院）']にハイフン存在: {hyphen_exists_before_integration} ---")
                    except Exception as e_before_integration_debug:
                        print(f"--- [DP_TAB] integrated_preprocess_data呼び出し直前df_rawデバッグエラー: {e_before_integration_debug} ---")
            else:
                print("--- [DP_TAB] integrated_preprocess_dataに渡すdf_rawに '入院患者数（在院）' 列なし ---")
        else:
            print("--- [DP_TAB] integrated_preprocess_dataに渡すdf_rawがNoneまたは空 ---")
        # --- ここまでデバッグコード ---

        df, validation_results = integrated_preprocess_data(df_raw, target_data_df=target_data)
        del df_raw
        gc.collect()

        if df is None or df.empty:
            progress_bar.progress(100, text="データ処理に失敗しました。")
            st.error("データ処理に失敗しました。")
            if validation_results and validation_results.get('errors'):
                for err in validation_results.get('errors', []):
                    st.error(err)
            return False, None, None, None, validation_results

        progress_bar.progress(50, text="3. データの検証中...")
        st.session_state.validation_results = validation_results
        if validation_results.get("warnings", []):
            with st.expander("データ検証の警告", expanded=True):
                for warning in validation_results["warnings"]:
                    st.warning(warning)
        if not validation_results.get("is_valid", True) and validation_results.get("errors"):
            st.error("データ検証で致命的なエラーが検出されました。処理を中断します。")
            return False, None, None, None, validation_results

        progress_bar.progress(90, text="5. 全体データの集計中...")
        all_results = None
        try:
            all_results = generate_filtered_summaries(df, None, None)
        except NameError:
            st.warning("集計関数 'generate_filtered_summaries' が見つかりません。forecast.pyからのインポートを確認してください。")
            all_results = None
        except Exception as e_summary:
            st.warning(f"全体データの集計中にエラーが発生しました: {e_summary}")
            all_results = None

        if all_results is None:
            st.warning("全体結果は限定的になります。")
            all_results = {
                "latest_date": df["日付"].max() if not df.empty else pd.Timestamp.now().normalize(),
                "summary": pd.DataFrame(),
                "weekday": pd.DataFrame(),
                "holiday": pd.DataFrame(),
                "monthly_all": pd.DataFrame(),
            }

        preprocess_end = time.time()
        st.session_state.performance_metrics['processing_time'] = preprocess_end - preprocess_start

        latest_date = all_results.get("latest_date", pd.Timestamp.now().normalize())
        end_time_total = time.time()
        total_time = end_time_total - start_time_total

        st.session_state.performance_logs = st.session_state.get('performance_logs', [])
        log_entry = {
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'operation': 'データ処理全体',
            'duration': total_time,
            'details': {
                'rows': len(df) if df is not None else 0,
                'columns': len(df.columns) if df is not None else 0,
                'files_new': len(new_files_uploaded) if new_files_uploaded else 0,
                'base_file_processed_as_parquet': base_data_loaded_from_parquet
            }
        }
        st.session_state.performance_logs.append(log_entry)

        progress_bar.progress(100, text=f"データの処理が完了しました。処理時間: {total_time:.1f}秒")
        return True, df, target_data, all_results, latest_date

    except Exception as e:
        progress_bar.progress(100, text=f"エラーが発生しました: {str(e)}")
        import traceback
        st.error(f"データ処理エラー: {traceback.format_exc()}")
        return False, None, None, None, None

def create_data_processing_tab():
    """データ処理タブのUI実装"""
    st.header("📊 データ処理")

    with st.expander("ℹ️ データ処理について", expanded=False):
        st.markdown("""
        **データ処理の流れ:**
        1. **固定ファイル**: メインとなる入院患者データ（必須）
        2. **追加ファイル**: 補完データ（オプション、複数可）
        3. **目標値ファイル**: 部門別目標設定（オプション）

        **対応ファイル形式:**
        - Excel: .xlsx, .xls
        - CSV: .csv (目標値ファイルのみ)

        **必要な列名:**
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
            st.session_state.performance_metrics = {
                'data_load_time': 0,
                'data_conversion_time': 0,
                'processing_time': 0
            }

    st.subheader("📁 ファイルアップロード")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**🔴 必須ファイル**")
        base_file_uploader = st.file_uploader(
            "固定ファイル (Excel)",
            type=["xlsx", "xls"],
            key="base_file_dp_tab",
            help="病院の入院患者データを含むメインのExcelファイル"
        )

    with col2:
        st.markdown("**🟡 オプション**")
        new_files_uploader = st.file_uploader(
            "追加ファイル (Excel)",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="new_files_dp_tab",
            help="補完データファイル（複数選択可）。同じ列構成である必要があります。"
        )

    with col3:
        st.markdown("**🟢 オプション**")
        target_file_uploader = st.file_uploader(
            "目標値ファイル (CSV)",
            type=["csv"],
            key="target_file_dp_tab",
            help="部門別の目標値データ（CSV形式）"
        )

    if st.session_state.get('target_data') is not None:
        with st.sidebar:
            st.markdown("---")
            st.subheader("🎯 目標値ファイル状況")
            st.success("✅ 目標値ファイル読み込み済み")
            extracted_targets = st.session_state.get('extracted_targets')
            if extracted_targets:
                if extracted_targets.get('target_days') or extracted_targets.get('target_admissions'):
                    st.success("✅ 目標値ファイルから取得:")
                    if extracted_targets.get('target_days'):
                        st.write(f"- 延べ在院日数目標: {extracted_targets['target_days']:,.0f}人日")
                    if extracted_targets.get('target_admissions'):
                        st.write(f"- 新入院患者数目標: {extracted_targets['target_admissions']:,.0f}人")
                    if extracted_targets.get('used_pattern'):
                        st.info(f"検索条件: {extracted_targets['used_pattern']}")
                else:
                    st.warning("⚠️ 目標値を抽出できませんでした")
            with st.expander("🔍 目標値ファイル内容確認", expanded=False):
                target_data_display = st.session_state.get('target_data')
                if target_data_display is not None:
                    st.write(f"**ファイル情報:** {target_data_display.shape[0]}行 × {target_data_display.shape[1]}列")
                    st.write("**列名:**")
                    for i, col_name_target in enumerate(target_data_display.columns):
                        st.write(f"{i+1}. {col_name_target}")
                    st.write("**サンプルデータ:**")
                    st.dataframe(target_data_display.head(), use_container_width=True)
                    debug_info_target = st.session_state.get('target_file_debug_info')
                    if debug_info_target and debug_info_target.get('search_results'):
                        st.write("**検索結果詳細:**")
                        for keyword, results in debug_info_target['search_results'].items():
                            if results:
                                st.write(f"「{keyword}」の検索結果:")
                                for result in results:
                                    st.write(f"  - {result['column']}: {result['matches']}件")
                            else:
                                st.write(f"「{keyword}」: 該当なし")

    if base_file_uploader:
        with st.expander("📋 固定ファイル列名確認", expanded=False):
            show_excel_column_info(base_file_uploader)

    if new_files_uploader:
        st.subheader("📂 追加ファイルの確認")
        for i, file_item in enumerate(new_files_uploader):
            with st.expander(f"📋 {file_item.name} の列名確認", expanded=False):
                show_excel_column_info(file_item)

    app_data_dir_check = get_app_data_dir()
    parquet_base_path_check = os.path.join(app_data_dir_check, "processed_base_data.parquet") if app_data_dir_check else None
    can_process = False
    if base_file_uploader:
        can_process = True
    elif parquet_base_path_check and os.path.exists(parquet_base_path_check):
        can_process = True
    elif new_files_uploader:
        can_process = True

    if can_process:
        if not st.session_state.get('data_processed', False):
            process_data_button = st.button("データ処理を実行", key="process_data_button_dp_tab", use_container_width=True)
            if process_data_button:
                files_to_add = new_files_uploader if new_files_uploader is not None else []
                progress_bar_ui = st.progress(0, text="データ処理を開始します...")
                success, df_result, target_data_result, all_results_result, latest_date_or_val_res = process_data_with_progress(
                    base_file_uploader, files_to_add, target_file_uploader, progress_bar_ui
                )
                if success and df_result is not None and not df_result.empty:
                    st.session_state.df = df_result
                    st.session_state.target_data = target_data_result
                    st.session_state.all_results = all_results_result
                    st.session_state.data_processed = True
                    if isinstance(latest_date_or_val_res, pd.Timestamp):
                        st.session_state.latest_data_date_str = latest_date_or_val_res.strftime("%Y年%m月%d日")
                    else:
                        st.session_state.latest_data_date_str = "データ処理完了 (日付不明)"
                        if isinstance(latest_date_or_val_res, dict) and latest_date_or_val_res.get('errors'):
                            for err_msg in latest_date_or_val_res.get('errors', []):
                                st.error(err_msg)
                    st.success(f"データの処理が完了しました。最新データ日付: {st.session_state.latest_data_date_str}")
                    perform_cleanup(deep=True)
                    st.rerun()
                else:
                    if isinstance(latest_date_or_val_res, dict) and latest_date_or_val_res.get('errors'):
                        for err_msg in latest_date_or_val_res.get('errors', []):
                            st.error(err_msg)
                    elif st.session_state.get('validation_results') and st.session_state.validation_results.get('errors'):
                        for err_msg in st.session_state.validation_results.get('errors', []):
                            st.error(err_msg)
                    else:
                        st.error("データ処理に失敗しました。詳細はログを確認してください。")
        else:
            st.success(f"データ処理済み（最新データ日付: {st.session_state.latest_data_date_str}）")
            if st.session_state.get('target_data') is not None:
                st.success("目標値データ読み込み済み")
            else:
                st.info("目標値データは未読み込みです")
            if st.session_state.get('df') is not None:
                df_display = st.session_state.df
                with st.expander("データ概要", expanded=True):
                    col1_sum, col2_sum, col3_sum = st.columns(3)
                    with col1_sum:
                        if not df_display.empty and '日付' in df_display.columns:
                            st.metric("データ期間", f"{df_display['日付'].min().strftime('%Y/%m/%d')} - {df_display['日付'].max().strftime('%Y/%m/%d')}")
                        else:
                            st.metric("データ期間", "N/A")
                    with col2_sum:
                        st.metric("総レコード数", f"{len(df_display):,}")
                    with col3_sum:
                        st.metric("病棟数", f"{df_display['病棟コード'].nunique() if '病棟コード' in df_display.columns else 'N/A'}")
                    col1_sum2, col2_sum2, col3_sum2 = st.columns(3)
                    with col1_sum2:
                        st.metric("診療科数", f"{df_display['診療科名'].nunique() if '診療科名' in df_display.columns else 'N/A'}")
                    with col2_sum2:
                        if "平日判定" in df_display.columns:
                            st.metric("平日数", f"{(df_display['平日判定'] == '平日').sum():,}")
                        else:
                            st.metric("平日数", "N/A")
                    with col3_sum2:
                        if "平日判定" in df_display.columns:
                            st.metric("休日数", f"{(df_display['平日判定'] == '休日').sum():,}")
                        else:
                            st.metric("休日数", "N/A")
                    perf_metrics = st.session_state.get('performance_metrics', {})
                    if perf_metrics:
                        st.subheader("処理パフォーマンス")
                        pcol1, pcol2, pcol3, pcol4 = st.columns(4)
                        with pcol1:
                            st.metric("データ読込時間", f"{perf_metrics.get('data_load_time', 0):.1f}秒")
                        with pcol2:
                            st.metric("Parquet変換時間", f"{perf_metrics.get('data_conversion_time', 0):.1f}秒")
                        with pcol3:
                            st.metric("データ処理時間", f"{perf_metrics.get('processing_time', 0):.1f}秒")
                        with pcol4:
                            try:
                                mem_info_dict = log_memory_usage()
                                if mem_info_dict is not None:
                                    process_mb = mem_info_dict.get('process_mb', 0)
                                    process_percent = mem_info_dict.get('process_percent', 0)
                                    st.metric("現在のメモリ使用", f"{process_mb:.1f} MB ({process_percent:.1f}%)")
                                else:
                                    st.metric("メモリ情報", "取得不可")
                            except Exception as e_mem:
                                print(f"メモリ表示エラー: {e_mem}")
                                st.metric("メモリ情報", "取得不可")
                validation_res = st.session_state.get('validation_results')
                if validation_res:
                    if validation_res.get("warnings") or validation_res.get("info") or validation_res.get("errors"):
                        with st.expander("データ検証結果", expanded=False):
                            for err_item in validation_res.get("errors", []):
                                st.error(err_item)
                            for info_msg_item in validation_res.get("info", []):
                                st.info(info_msg_item)
                            for warning_msg_item in validation_res.get("warnings", []):
                                st.warning(warning_msg_item)
                if st.session_state.get('data_processed', False) and st.session_state.get('target_data') is not None:
                    with st.expander("診療科マッピング設定", expanded=False):
                        st.write("実績データの診療科コードと表示名のマッピングを確認します。")
                        try:
                            from utils import get_display_name_for_dept, create_dept_mapping_table
                            dept_mapping = st.session_state.get('dept_mapping', {})
                            if not dept_mapping:
                                create_dept_mapping_table(st.session_state.target_data)
                                dept_mapping = st.session_state.get('dept_mapping', {})
                            if dept_mapping:
                                df_mapping = pd.DataFrame({
                                    '診療科コード': list(dept_mapping.keys()),
                                    '表示名': list(dept_mapping.values())
                                })
                                st.dataframe(df_mapping)
                                problematic_depts = ["総合内科（内科除く）", "内科救急"]
                                st.subheader("確認対象の診療科")
                                for dept_item in problematic_depts:
                                    display_name = get_display_name_for_dept(dept_item, "マッピングなし")
                                    if display_name == "マッピングなし":
                                        st.warning(f"「{dept_item}」→マッピングがありません")
                                    else:
                                        st.success(f"「{dept_item}」→「{display_name}」")
                            else:
                                st.warning("診療科マッピングが作成されていません。目標値ファイルを確認してください。")
                        except ImportError:
                            st.warning("診療科マッピング機能が利用できません。")
                        except Exception as e_map_display:
                            st.error(f"マッピング表示エラー: {str(e_map_display)}")

            if st.button("データをリセット (Parquetベースデータも削除)", key="reset_data_button_dp_tab", use_container_width=True):
                st.session_state.data_processed = False
                st.session_state.df = None
                st.session_state.all_results = None
                st.session_state.target_data = None
                st.session_state.validation_results = None
                st.session_state.latest_data_date_str = "データ読込前"
                st.session_state.target_file_debug_info = None
                st.session_state.extracted_targets = None
                st.session_state.performance_metrics = {
                    'data_load_time': 0,
                    'data_conversion_time': 0,
                    'processing_time': 0
                }
                if app_data_dir_check:
                    parquet_to_delete = os.path.join(app_data_dir_check, "processed_base_data.parquet")
                    info_to_delete = os.path.join(app_data_dir_check, "base_file_info.json")
                    if os.path.exists(parquet_to_delete):
                        try: os.remove(parquet_to_delete); st.info("キャッシュされたデータを削除しました。")
                        except Exception as e_del_parquet: st.warning(f"Parquet削除エラー: {e_del_parquet}")
                    if os.path.exists(info_to_delete):
                        try: os.remove(info_to_delete)
                        except Exception as e_del_info: st.warning(f"Infoファイル削除エラー: {e_del_info}")
                perform_cleanup(deep=True)
                st.rerun()
    else:
        st.info("「固定ファイル」をアップロードするか、以前処理したデータがあれば「追加ファイル」をアップロードしてください。")
        st.markdown("#### サンプルデータ")
        st.markdown("サンプルデータを使用して機能を試すことができます。")
        if st.button("サンプルデータを使用", key="sample_data_button_dp_tab"):
            st.info("この機能は開発中です。現在は自分のデータをアップロードしてください。")

def show_excel_column_info(uploaded_file):
    """アップロードされたExcelファイルの列名情報を表示（改善版）"""
    try:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.getvalue()
        uploaded_file.seek(0)
        if len(file_bytes) == 0:
            st.warning("ファイルが空です。")
            return
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file_obj:
            temp_file_obj.write(file_bytes)
            temp_path = temp_file_obj.name
        try:
            df_sample = None
            engines = ['openpyxl', 'xlrd']
            for engine_name in engines:
                try:
                    df_sample = pd.read_excel(temp_path, nrows=3, engine=engine_name)
                    break
                except Exception:
                    if engine_name == engines[-1]: raise
                    continue
            if df_sample is None or df_sample.empty:
                st.warning("ファイルの内容を読み取れませんでした。")
                return

            df_sample_display = df_sample.copy()
            cols_to_clean_in_sample = []
            potential_numeric_cols_sample = ["在院患者数", "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数", "入院患者数（在院）"]
            for col_name_sample in potential_numeric_cols_sample:
                if col_name_sample in df_sample_display.columns:
                    cols_to_clean_in_sample.append(col_name_sample)
            for col_clean_sample in cols_to_clean_in_sample:
                if df_sample_display[col_clean_sample].dtype == 'object':
                    df_sample_display[col_clean_sample] = df_sample_display[col_clean_sample].replace(['-', '－', ' ', '　', 'なし', 'NA', 'N/A', 'NULL', 'null'], np.nan, regex=False)
                df_sample_display[col_clean_sample] = pd.to_numeric(df_sample_display[col_clean_sample], errors='coerce')

            st.subheader(f"📋 {uploaded_file.name} の列名確認")
            file_size_mb = len(file_bytes) / (1024 * 1024)
            st.info(f"ファイルサイズ: {file_size_mb:.2f} MB | 行数（サンプル）: {len(df_sample_display)} | 列数: {len(df_sample_display.columns)}")
            col1_info, col2_info = st.columns(2)
            with col1_info:
                st.write("**検出された列名:**")
                for i, col_detected in enumerate(df_sample_display.columns):
                    dtype_str = str(df_sample_display[col_detected].dtype)
                    st.write(f"{i+1}. {col_detected} ({dtype_str})")
            with col2_info:
                st.write("**期待される列名:**")
                expected_cols_list = [
                    "病棟コード", "診療科名", "日付", "在院患者数",
                    "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"
                ]
                matched_columns_list = []
                for col_expected_item in expected_cols_list:
                    if col_expected_item in df_sample_display.columns:
                        st.write(f"✅ {col_expected_item}")
                        matched_columns_list.append(col_expected_item)
                    else:
                        similar_cols_list = [c_item for c_item in df_sample_display.columns if col_expected_item.replace('患者数', '') in c_item or col_expected_item.replace('数', '') in c_item]
                        if similar_cols_list:
                            st.write(f"❓ {col_expected_item} (類似: {similar_cols_list[0]})")
                        else:
                            st.write(f"❌ {col_expected_item}")
            available_count = len(matched_columns_list)
            essential_columns_list = ["病棟コード", "診療科名", "日付"]
            essential_count = sum(1 for col_essential_item in essential_columns_list if col_essential_item in matched_columns_list)
            if essential_count >= 2 and available_count >= 4:
                st.success(f"✅ このファイルは完全に利用可能です（{available_count}/{len(expected_cols_list)}列が一致）")
            elif essential_count >= 2:
                st.warning(f"⚠️ このファイルは部分的に利用可能です（{available_count}/{len(expected_cols_list)}列が一致、必須列:{essential_count}/3）")
                st.info("不足している列は自動的に0で補完されるか、処理がスキップされます。")
            else:
                st.error(f"❌ このファイルは利用できません（必須列が不足: {essential_count}/3）")
                st.info("このファイルは処理をスキップされます。")
            st.write("**データ品質チェック:**")
            quality_issues_list = []
            for col_match_item in matched_columns_list:
                null_count = df_sample_display[col_match_item].isnull().sum()
                if null_count > 0:
                    quality_issues_list.append(f"'{col_match_item}': {null_count}個の欠損値（数値変換後）")
            if quality_issues_list:
                st.warning("品質上の問題:")
                for issue_item in quality_issues_list:
                    st.write(f"  • {issue_item}")
            else:
                st.success("サンプルデータに品質上の問題は見つかりませんでした。")
            st.markdown("---")
            st.write("**📊 サンプルデータ（最初の3行）:**")
            show_details_checkbox = st.checkbox(f"詳細データを表示 - {uploaded_file.name}", key=f"show_details_{uploaded_file.name}")
            if show_details_checkbox:
                st.dataframe(df_sample_display, use_container_width=True)
                numeric_cols_display_list = df_sample_display.select_dtypes(include=[np.number]).columns
                if len(numeric_cols_display_list) > 0:
                    st.write("**数値列の基本統計:**")
                    st.dataframe(df_sample_display[numeric_cols_display_list].describe(), use_container_width=True)
            else:
                st.dataframe(df_sample_display.head(2), use_container_width=True)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    except Exception as e_show_info:
        st.error(f"列名確認エラー: {e_show_info}")
        st.markdown("---")
        st.write("**🔧 詳細エラー情報:**")
        show_error_details_checkbox = st.checkbox(f"エラー詳細を表示 - {uploaded_file.name}", key=f"show_error_{uploaded_file.name}")
        if show_error_details_checkbox:
            import traceback
            st.code(traceback.format_exc())