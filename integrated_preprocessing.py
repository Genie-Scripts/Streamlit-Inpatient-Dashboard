import pandas as pd
import numpy as np
import streamlit as st
import jpholiday
import gc
import time
import hashlib
from io import BytesIO
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import logging

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def efficient_duplicate_check(df_raw):
    start_time = time.time()
    if df_raw is None or df_raw.empty:
        logger.info("重複チェック: 空のデータフレームが渡されました")
        return df_raw

    initial_rows = len(df_raw)
    for col in df_raw.select_dtypes(include=['object']).columns:
        try:
            if df_raw[col].nunique() / len(df_raw) < 0.5:
                df_raw[col] = df_raw[col].astype('category')
        except Exception as e:
            logger.warning(f"列 '{col}' の型変換エラー: {e}")

    try:
        mem_before = df_raw.memory_usage(deep=True).sum() / (1024 * 1024)
        df_processed = df_raw.drop_duplicates()
        mem_after = df_processed.memory_usage(deep=True).sum() / (1024 * 1024)
        rows_dropped = initial_rows - len(df_processed)
        del df_raw
        gc.collect()
        end_time = time.time()
        processing_time = end_time - start_time
        logger.info(f"重複チェック結果: 初期行数={initial_rows:,}, 削除行数={rows_dropped:,}, 最終行数={len(df_processed):,}, 処理時間={processing_time:.2f}秒, メモリ削減={mem_before-mem_after:.2f}MB")
        if 'performance_metrics' not in st.session_state:
            st.session_state.performance_metrics = {}
        st.session_state.performance_metrics['duplicate_check_time'] = processing_time
        st.session_state.performance_metrics['duplicate_rows_removed'] = rows_dropped
        return df_processed
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"重複チェック処理エラー: {e}\n{error_detail}")
        return df_raw

@st.cache_data(ttl=3600, show_spinner=False)
def integrated_preprocess_data(df: pd.DataFrame, target_data_df: pd.DataFrame = None):
    start_time = time.time()
    validation_results = {
        "is_valid": True,
        "warnings": [],
        "errors": [],
        "info": []
    }

    major_departments_list = []
    if target_data_df is not None and not target_data_df.empty and '部門コード' in target_data_df.columns:
        potential_major_depts = target_data_df['部門コード'].astype(str).unique()
        if '部門名' in target_data_df.columns:
            potential_major_depts_from_name = target_data_df['部門名'].astype(str).unique()
            potential_major_depts = np.union1d(potential_major_depts, potential_major_depts_from_name)

        if '診療科名' in df.columns:
            actual_depts_in_df = df['診療科名'].astype(str).unique()
            major_departments_list = [dept for dept in actual_depts_in_df if dept in potential_major_depts]

        if not major_departments_list and len(potential_major_depts) > 0:
            major_departments_list = list(potential_major_depts)
            validation_results["warnings"].append("目標設定ファイルに記載の診療科が、実績データの診療科名と直接一致しませんでした。目標設定ファイルの「部門コード」または「部門名」を主要診療科として扱います。")
        if not major_departments_list:
            validation_results["warnings"].append("目標設定ファイルから主要診療科リストを特定できませんでした。")
    else:
        validation_results["warnings"].append("目標設定ファイルが提供されなかったか、'部門コード'列がありません。全ての診療科を「その他」として扱います。")

    try:
        if df is None or df.empty:
            validation_results["is_valid"] = False
            validation_results["errors"].append("入力データが空です。")
            return None, validation_results

        expected_cols = ["病棟コード", "診療科名", "日付", "在院患者数", "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"]
        available_cols = [col for col in df.columns if col in expected_cols]
        df_processed = df[available_cols].copy()

        df_processed.dropna(subset=['病棟コード'], inplace=True)
        df_processed['日付'] = pd.to_datetime(df_processed['日付'], errors='coerce')
        df_processed.dropna(subset=['日付'], inplace=True)
        if df_processed.empty:
            validation_results["is_valid"] = False
            validation_results["errors"].append("必須の「病棟コード」または「日付」の処理後にデータが空になりました。")
            return None, validation_results

        df_processed["病棟コード"] = df_processed["病棟コード"].astype(str)

        if '診療科名' in df_processed.columns:
            df_processed['診療科名'] = df_processed['診療科名'].fillna("空白診療科").astype(str)
            df_processed['診療科名'] = df_processed['診療科名'].apply(lambda x: x if x in major_departments_list else 'その他')
            validation_results["info"].append(f"診療科名を主要診療科（{len(major_departments_list)}件）と「その他」に集約しました。「空白」も「その他」に含まれます。")

        df_processed = efficient_duplicate_check(df_processed)

        numeric_cols = ["在院患者数", "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数", "入院患者数（在院）"]
        for col in numeric_cols:
            if col in df_processed.columns:
                df_processed[col] = pd.to_numeric(df_processed[col].replace('-', np.nan), errors='coerce').fillna(0)
            else:
                df_processed[col] = 0

        return df_processed, validation_results

    except Exception as e:
        import traceback
        validation_results["is_valid"] = False
        validation_results["errors"].append(f"前処理エラー: {str(e)}")
        logger.error(f"前処理エラー: {e}\n{traceback.format_exc()}")
        return None, validation_results

def add_weekday_flag(df):
    """
    平日/休日の判定フラグを追加する
    
    Parameters:
    -----------
    df : pd.DataFrame
        フラグを追加するデータフレーム
    
    Returns:
    --------
    pd.DataFrame
        フラグが追加されたデータフレーム
    """
    def is_holiday(date):
        return (
            date.weekday() >= 5 or  # 土日
            jpholiday.is_holiday(date) or  # 祝日
            (date.month == 12 and date.day >= 29) or  # 年末
            (date.month == 1 and date.day <= 3)  # 年始
        )
    
    # 平日/休日フラグを追加
    df["平日判定"] = df["日付"].apply(lambda x: "休日" if is_holiday(x) else "平日")
    
    return df  # この行がインデントされていることを確認
    
def calculate_file_hash(file_content_bytes):
    """
    ファイルのハッシュ値を計算して一意の識別子を作成
    
    Parameters:
    -----------
    file_content_bytes: bytes
        ファイルの内容をバイト列で表したもの
        
    Returns:
    --------
    str
        MD5ハッシュ値の16進数文字列
    """
    try:
        # ファイルサイズが大きすぎる場合、先頭部分のみを使用してハッシュ計算
        max_bytes = 10 * 1024 * 1024  # 10MB上限
        if len(file_content_bytes) > max_bytes:
            # 先頭5MBと末尾5MBを組み合わせてハッシュ計算
            head = file_content_bytes[:5 * 1024 * 1024]  # 先頭5MB
            tail = file_content_bytes[-5 * 1024 * 1024:]  # 末尾5MB
            combined = head + tail
            return hashlib.md5(combined).hexdigest()
        else:
            # 通常のハッシュ計算
            return hashlib.md5(file_content_bytes).hexdigest()
    except Exception as e:
        print(f"ファイルハッシュ計算エラー: {str(e)}")
        # エラー時にはファイルサイズとタイムスタンプの組み合わせを返す
        file_size = len(file_content_bytes)
        timestamp = int(time.time())
        return f"size_{file_size}_time_{timestamp}"


@st.cache_data(ttl=3600, show_spinner=False)
def read_excel_cached(file_content_bytes, sheet_name=0, usecols=None, dtype=None):
    """
    ファイル内容に基づいたキャッシュを使用してExcelを読み込む
    例外処理を強化
    
    Parameters:
    -----------
    file_content_bytes: bytes
        Excelファイルの内容をバイト列で表したもの
    sheet_name: int or str, default 0
        読み込むシート名またはインデックス
    usecols: list or None, default None
        読み込む列のリスト
    dtype: dict or None, default None
        列のデータ型を指定する辞書
        
    Returns:
    --------
    pd.DataFrame
        読み込まれたExcelデータ
    """
    temp_path = None
    try:
        # 一時ファイルを作成
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
            temp_file.write(file_content_bytes)
            temp_path = temp_file.name

        # 読み込み時のパラメータをログ出力（デバッグ用）
        print(f"Excel読込: usecols={usecols}, dtype={dtype}")
        
        # Excelファイルの読み込み
        df = pd.read_excel(
            temp_path, 
            sheet_name=sheet_name, 
            engine='openpyxl', 
            usecols=usecols, 
            dtype=dtype
        )
        
        # 基本的な検証
        if df.empty:
            print(f"警告: 読み込まれたExcelファイルが空です: sheet_name={sheet_name}")
            return None
            
        return df
    except Exception as e:
        # 詳細なエラーメッセージをログに出力
        print(f"Excel読込エラー: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return None
    finally:
        # 確実に一時ファイルを削除
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception as e:
                print(f"一時ファイル削除エラー: {str(e)}")


def load_files(base_file, new_files, usecols_excel=None, dtype_excel=None):
    """
    複数のExcelファイルを並列処理で読み込む。
    
    Parameters:
    -----------
    base_file: Streamlit UploadedFile object or None
        基本ファイル（通常は過去データ）
    new_files: list of Streamlit UploadedFile objects or None
        追加のファイルリスト
    usecols_excel: list or None
        Excel読み込み時に指定する列のリスト
    dtype_excel: dict or None
        Excel読み込み時に指定するデータ型の辞書
        
    Returns:
    --------
    pandas.DataFrame
        読み込まれたすべてのファイルを結合したデータフレーム
        ファイルがないか読み込みに失敗した場合は空のデータフレーム
    """
    start_time = time.time()
    
    # ファイルリストの準備
    df_list = []
    files_to_process = []

    # base_fileとnew_filesをファイルリストに追加
    if base_file:  # base_fileがNoneでない場合
        files_to_process.append(base_file)
        print(f"基本ファイルを処理リストに追加: {base_file.name}")
    
    if new_files:  # new_filesがNoneでない、かつ空でない場合
        files_to_process.extend(new_files)
        print(f"追加ファイル{len(new_files)}件を処理リストに追加")

    # 処理対象ファイルがない場合は空のデータフレームを返す
    if not files_to_process:
        print("処理対象ファイルがありません。")
        return pd.DataFrame()

    # ファイル内容をメモリに読み込む
    file_contents = []
    for file_obj in files_to_process:
        try:
            file_obj.seek(0)
            file_content = file_obj.read()
            file_contents.append((file_obj.name, file_content))
            file_obj.seek(0)  # ファイルポインタを戻す
            file_size = len(file_content) / (1024 * 1024)  # MBに変換
            print(f"ファイル読込: {file_obj.name} ({file_size:.2f} MB)")
        except Exception as e:
            print(f"ファイル読込エラー ({file_obj.name}): {str(e)}")

    # 並列処理の設定（最大ワーカー数を制限）
    max_workers = min(4, len(file_contents)) if file_contents else 1
    print(f"並列処理ワーカー数: {max_workers}")
    
    # 並列処理でExcelファイルを読み込む
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 各ファイルの読み込みタスクを登録
        futures = {
            executor.submit(read_excel_cached, content, 0, usecols_excel, dtype_excel): name
            for name, content in file_contents
        }

        # 各タスクの結果を処理
        successful_files = 0
        for future in concurrent.futures.as_completed(futures):
            file_name = futures[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    df_list.append(df)
                    rows, cols = df.shape
                    print(f"ファイル '{file_name}' の読込成功: {rows}行 × {cols}列")
                    successful_files += 1
                else:
                    print(f"ファイル '{file_name}' の読込結果が空です")
            except Exception as e:
                print(f"ファイル '{file_name}' の処理中にエラー: {str(e)}")
                import traceback
                print(traceback.format_exc())

    # 読み込み結果の確認
    if not df_list:
        print("読み込み可能なExcelデータがありません。")
        return pd.DataFrame()

    # データフレームの結合
    try:
        df_raw = pd.concat(df_list, ignore_index=True)
        
        # 効率的な重複チェックを行う
        df_raw = efficient_duplicate_check(df_raw)
        
        # 結果の出力
        end_time = time.time()
        rows, cols = df_raw.shape
        print(f"データ読込完了: {successful_files}/{len(file_contents)}ファイル成功, {rows}行 × {cols}列, 処理時間: {end_time - start_time:.2f}秒")
        
        return df_raw
    except Exception as e:
        print(f"データフレーム結合エラー: {str(e)}")
        return pd.DataFrame()