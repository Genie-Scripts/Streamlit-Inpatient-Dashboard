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
    """
    データフレームの重複を効率的にチェックして除去する関数
    
    Args:
        df_raw (pd.DataFrame): 重複チェック対象のデータフレーム
        
    Returns:
        pd.DataFrame: 重複が除去されたデータフレーム
    """
    start_time = time.time()
    
    # 空のデータフレームチェック
    if df_raw is None or df_raw.empty:
        logger.info("重複チェック: 空のデータフレームが渡されました")
        return df_raw
    
    initial_rows = len(df_raw)
    
    # メモリ使用量最適化のための型変換
    # カーディナリティが低い文字列列をカテゴリ型に変換
    # ここは変換先なので問題なし
    for col in df_raw.select_dtypes(include=['object']).columns:
        try:
            # カーディナリティ（ユニーク値の比率）が低い列のみカテゴリ型に変換
            if df_raw[col].nunique() / len(df_raw) < 0.5:
                df_raw[col] = df_raw[col].astype('category')
                logger.debug(f"列 '{col}' をカテゴリ型に変換")
        except Exception as e:
            logger.warning(f"列 '{col}' の型変換エラー: {e}")
    
    try:
        # パフォーマンス計測開始
        mem_before = df_raw.memory_usage(deep=True).sum() / (1024 * 1024)
        
        # 重複除去実行（inplace=Falseでコピーを作成）
        df_processed = df_raw.drop_duplicates()
        
        # 重複除去後のメモリ使用量
        mem_after = df_processed.memory_usage(deep=True).sum() / (1024 * 1024)
        
        # 結果の集計
        rows_dropped = initial_rows - len(df_processed)
        
        # 元のデータフレームとその関連リソースを解放
        del df_raw
        gc.collect()
        
        # 終了時間とパフォーマンス情報
        end_time = time.time()
        processing_time = end_time - start_time
        
        # 結果をログに出力
        logger.info(f"重複チェック結果: 初期行数={initial_rows:,}, 削除行数={rows_dropped:,}, "
                   f"最終行数={len(df_processed):,}, 処理時間={processing_time:.2f}秒, "
                   f"メモリ削減={mem_before-mem_after:.2f}MB")
        
        # セッション状態にパフォーマンス情報を記録
        if 'performance_metrics' not in st.session_state:
            st.session_state.performance_metrics = {}
        st.session_state.performance_metrics['duplicate_check_time'] = processing_time
        st.session_state.performance_metrics['duplicate_rows_removed'] = rows_dropped
        
        return df_processed
    
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"重複チェック処理エラー: {e}\n{error_detail}")
        
        # エラーが発生した場合は元のデータフレームを返す
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
    # target_data_df を使って major_departments_list を生成するロジック
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
            validation_results["warnings"].append(
                "目標設定ファイルに記載の診療科が、実績データの診療科名と直接一致しませんでした。"
                "目標設定ファイルの「部門コード」または「部門名」を主要診療科として扱います。"
            )
        if not major_departments_list:
            validation_results["warnings"].append("目標設定ファイルから主要診療科リストを特定できませんでした。")
    else:
        validation_results["warnings"].append("目標設定ファイルが提供されなかったか、'部門コード'列がありません。全ての診療科を「その他」として扱います。")

    try:
        if df is None or df.empty:
            validation_results["is_valid"] = False
            validation_results["errors"].append("入力データが空です。")
            return None, validation_results

        # 必要な列の確認
        expected_cols = ["病棟コード", "診療科名", "日付", "在院患者数",
                         "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"]
        # 必須は「病棟コード」と「日付」のみとする（診療科名は後で処理）
        essential_cols_for_dropna = ["病棟コード", "日付"]

        # 利用可能な列のみを対象とする
        available_cols = [col for col in df.columns if col in expected_cols]
        df_processed = df[available_cols].copy()

        # --- 1. 欠損値の取り扱い変更 ---
        # 「病棟コード」が欠損している行のみを除外
        initial_rows = len(df_processed)
        df_processed.dropna(subset=['病棟コード'], inplace=True)
        rows_dropped_due_to_ward_nan = initial_rows - len(df_processed)
        if rows_dropped_due_to_ward_nan > 0:
            validation_results["warnings"].append(
                f"「病棟コード」が欠損している行が {rows_dropped_due_to_ward_nan} 件ありました。これらの行は除外されました。"
            )
        
        # 日付列の処理と欠損行の除外
        if '日付' not in df_processed.columns:
            validation_results["is_valid"] = False
            validation_results["errors"].append("必須列「日付」が存在しません。")
            return None, validation_results
        df_processed['日付'] = pd.to_datetime(df_processed['日付'], errors='coerce')
        initial_rows = len(df_processed)
        df_processed.dropna(subset=['日付'], inplace=True)
        rows_dropped_due_to_date_nan = initial_rows - len(df_processed)
        if rows_dropped_due_to_date_nan > 0:
             validation_results["warnings"].append(
                f"無効な日付または日付が欠損している行が {rows_dropped_due_to_date_nan} 件ありました。これらの行は除外されました。"
            )

        if df_processed.empty:
            validation_results["is_valid"] = False
            validation_results["errors"].append("必須の「病棟コード」または「日付」の処理後にデータが空になりました。")
            return None, validation_results
            
        # 病棟コードを文字列型に変換
        df_processed["病棟コード"] = df_processed["病棟コード"].astype(str)
    
        # 診療科名の欠損値処理のみ実施
        if '診療科名' in df_processed.columns:
            # カテゴリカル型かどうかをチェック
            if pd.api.types.is_categorical_dtype(df_processed['診療科名']):
                # カテゴリカル型の場合は、新しいカテゴリを追加する前に一度stringに変換
                df_processed['診療科名'] = df_processed['診療科名'].astype(str).fillna("空白診療科")
            else:
                # 通常の型の場合は直接fillnaとastype
                df_processed['診療科名'] = df_processed['診療科名'].fillna("空白診療科").astype(str)
            
            # --- 3. 診療科名の集約 ---
            # 主要診療科以外を「その他」に集約、「空白診療科」も「その他」に含める
            df_processed['診療科名'] = df_processed['診療科名'].apply(
                lambda x: x if x in major_departments_list else 'その他'
            )
            validation_results["info"].append(
                f"診療科名を主要診療科（{len(major_departments_list)}件）と「その他」に集約しました。「空白」も「その他」に含まれます。"
            )
        else:
            validation_results["warnings"].append("「診療科名」列が存在しないため、診療科集約をスキップしました。")
        
        # 新しい効率的な重複チェック関数を呼び出す
        initial_rows = len(df_processed)
        df_processed = efficient_duplicate_check(df_processed)
        rows_dropped_due_to_duplicates = initial_rows - len(df_processed)
        
        if rows_dropped_due_to_duplicates > 0:
            validation_results["info"].append(
                f"重複データ {rows_dropped_due_to_duplicates} 行を削除しました"
            )
    
        # --- 数値列の処理 ---
        # --- 数値列の徹底処理（全データ型対応・欠損防止） ---
        numeric_cols_to_process = [
            "在院患者数", "入院患者数", "緊急入院患者数",
            "退院患者数", "死亡患者数", "入院患者数（在院）"
        ]

        for col in numeric_cols_to_process:
            if col in df_processed.columns:
                # 変更点: pd.to_numeric を使用して、より堅牢な数値変換を行う
                df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce').fillna(0.0)
            else:
                df_processed[col] = 0.0 # 列が存在しない場合は0.0で初期化（float型）
                validation_results["warnings"].append(f"数値列'{col}'が存在しなかったため、0.0で補完されました。")
    
        # --- 列名の統一処理を修正 --- 
        # 在院患者数 -> 入院患者数（在院）へのリネーム
        if "在院患者数" in df_processed.columns:
            # リネーム前に値をコピー (データ保全)
            df_processed["入院患者数（在院）"] = df_processed["在院患者数"].copy()
            validation_results["info"].append("「在院患者数」列を「入院患者数（在院）」列にコピーしました。")
            # 元の列も残す (互換性のため)
            # df_processed.rename(columns={"在院患者数": "入院患者数（在院）"}, inplace=True)
        elif "入院患者数（在院）" not in df_processed.columns:
            # いずれもない場合は明示的なエラー
            validation_results["errors"].append("「在院患者数」または「入院患者数（在院）」列のいずれも存在しません。")
            df_processed["入院患者数（在院）"] = 0 # エラー回避
            # 在院患者数も作成 (互換性のため)
            df_processed["在院患者数"] = 0
    
        # --- 派生指標の計算 ---
        # 総入院患者数 (入院患者数 + 緊急入院患者数)
        if "入院患者数" in df_processed.columns and "緊急入院患者数" in df_processed.columns:
            df_processed["総入院患者数"] = df_processed["入院患者数"] + df_processed["緊急入院患者数"]
        else:
            validation_results["warnings"].append("「入院患者数」または「緊急入院患者数」列がないため、「総入院患者数」は計算できませんでした。")
            df_processed["総入院患者数"] = 0 # エラー回避のため0で列作成

        # 総退院患者数 (退院患者数 + 死亡患者数)
        if "退院患者数" in df_processed.columns and "死亡患者数" in df_processed.columns:
            df_processed["総退院患者数"] = df_processed["退院患者数"] + df_processed["死亡患者数"]
        else:
            validation_results["warnings"].append("「退院患者数」または「死亡患者数」列がないため、「総退院患者数」は計算できませんでした。")
            df_processed["総退院患者数"] = 0 # エラー回避のため0で列作成

        # 新入院患者数 (総入院患者数と同じと仮定)
        if "総入院患者数" in df_processed.columns:
            df_processed["新入院患者数"] = df_processed["総入院患者数"]
        else:
            df_processed["新入院患者数"] = 0

        # 平日/休日フラグの追加
        if '日付' in df_processed.columns:
            df_processed = add_weekday_flag(df_processed) # 既存のadd_weekday_flag関数を呼び出す
        else:
            validation_results["errors"].append("「日付」列がないため、平日/休日フラグを追加できません。")
            
        gc.collect()
        end_time = time.time()
        validation_results["info"].append(f"データ前処理時間: {end_time - start_time:.2f}秒")
        validation_results["info"].append(f"処理後のレコード数: {len(df_processed)}")
        if not df_processed.empty:
            validation_results["info"].append(f"データ期間: {df_processed['日付'].min().strftime('%Y/%m/%d')} - {df_processed['日付'].max().strftime('%Y/%m/%d')}")
        
        if df_processed.empty: # 最終的に空になった場合はエラーとする
            validation_results["is_valid"] = False
            validation_results["errors"].append("前処理の結果、有効なデータが残りませんでした。")
            return None, validation_results

        return df_processed, validation_results

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        validation_results["is_valid"] = False
        validation_results["errors"].append(f"データの前処理中に予期せぬエラーが発生しました: {str(e)}")
        validation_results["errors"].append(f"詳細: {error_detail}")
        print(f"前処理エラー: {error_detail}")
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