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
    データフレームの重複を効率的にチェックして除去する関数（修正版）
    
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
    for col in df_raw.select_dtypes(include=['object']).columns:
        try:
            if df_raw[col].nunique() / len(df_raw) < 0.5:
                df_raw[col] = df_raw[col].astype('category')
                logger.debug(f"列 '{col}' をカテゴリ型に変換")
        except Exception as e:
            logger.warning(f"列 '{col}' の型変換エラー: {e}")
    
    try:
        # パフォーマンス計測開始
        mem_before = df_raw.memory_usage(deep=True).sum() / (1024 * 1024)
        
        # ✅ 修正：特定の列のみで重複除去
        # 重要な識別列のみで重複チェック
        key_columns = []
        if '日付' in df_raw.columns:
            key_columns.append('日付')
        if '病棟コード' in df_raw.columns:
            key_columns.append('病棟コード')
        if '診療科名' in df_raw.columns:
            key_columns.append('診療科名')
        
        if key_columns:
            # 識別可能な列がある場合はそれらの列のみで重複除去
            df_processed = df_raw.drop_duplicates(subset=key_columns)
            logger.info(f"重複除去: キー列 {key_columns} で実行")
        else:
            # キー列がない場合は全列で重複除去（従来通り）
            df_processed = df_raw.drop_duplicates()
            logger.warning("重複除去: キー列が見つからないため全列で実行")
        
        # 重複除去後のメモリ使用量
        mem_after = df_processed.memory_usage(deep=True).sum() / (1024 * 1024)
        
        # 結果の集計
        rows_dropped = initial_rows - len(df_processed)
        
        # ✅ 追加：大量削除の警告
        if rows_dropped > 0:
            drop_rate = (rows_dropped / initial_rows) * 100
            if drop_rate > 30:  # 30%以上削除された場合
                logger.error(f"🚨 警告: 重複除去で{rows_dropped:,}件（{drop_rate:.1f}%）削除されました。設定を確認してください。")
            elif drop_rate > 10:  # 10%以上削除された場合
                logger.warning(f"⚠️ 注意: 重複除去で{rows_dropped:,}件（{drop_rate:.1f}%）削除されました。")
        
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

    # データ件数のトラッキング
    initial_record_count = len(df) if df is not None and not df.empty else 0
    validation_results["info"].append(f"初期データ件数: {initial_record_count:,}件")

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
        essential_cols_for_dropna = ["病棟コード", "日付"]

        # 利用可能な列のみを対象とする
        available_cols = [col for col in df.columns if col in expected_cols]
        df_processed = df[available_cols].copy()

        # --- 1. 欠損値の取り扱い ---
        before_ward_filter = len(df_processed)
        df_processed.dropna(subset=['病棟コード'], inplace=True)
        after_ward_filter = len(df_processed)
        rows_dropped_due_to_ward_nan = before_ward_filter - after_ward_filter
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
        before_date_filter = len(df_processed)
        df_processed.dropna(subset=['日付'], inplace=True)
        after_date_filter = len(df_processed)
        rows_dropped_due_to_date_nan = before_date_filter - after_date_filter
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
            if pd.api.types.is_categorical_dtype(df_processed['診療科名']):
                df_processed['診療科名'] = df_processed['診療科名'].astype(str).fillna("空白診療科")
            else:
                df_processed['診療科名'] = df_processed['診療科名'].fillna("空白診療科").astype(str)
            
            # --- 3. 診療科名の集約 ---
            df_processed['診療科名'] = df_processed['診療科名'].apply(
                lambda x: x if x in major_departments_list else 'その他'
            )
            validation_results["info"].append(
                f"診療科名を主要診療科（{len(major_departments_list)}件）と「その他」に集約しました。「空白」も「その他」に含まれます。"
            )
        else:
            validation_results["warnings"].append("「診療科名」列が存在しないため、診療科集約をスキップしました。")
        
        # ✅ 修正：安全な重複除去の再実装
        before_dedup = len(df_processed)
        
        # 重複除去用のキー列を決定
        key_columns = []
        if '日付' in df_processed.columns:
            key_columns.append('日付')
        if '病棟コード' in df_processed.columns:
            key_columns.append('病棟コード')
        if '診療科名' in df_processed.columns:
            key_columns.append('診療科名')
        
        if key_columns:
            # 特定の列のみで重複除去（安全）
            df_processed = df_processed.drop_duplicates(subset=key_columns)
            after_dedup = len(df_processed)
            rows_dropped_due_to_duplicates = before_dedup - after_dedup
            
            if rows_dropped_due_to_duplicates > 0:
                drop_rate = (rows_dropped_due_to_duplicates / before_dedup) * 100
                validation_results["info"].append(
                    f"重複データ {rows_dropped_due_to_duplicates:,} 行を削除しました（{drop_rate:.1f}%）"
                )
                validation_results["info"].append(
                    f"重複除去キー: {key_columns}"
                )
                
                # 大量削除の警告
                if drop_rate > 30:
                    validation_results["warnings"].append(f"⚠️ 大量の重複データ（{drop_rate:.1f}%）が削除されました。")
                elif drop_rate > 10:
                    validation_results["info"].append(f"中程度の重複データ（{drop_rate:.1f}%）が削除されました。")
            else:
                validation_results["info"].append("重複データは見つかりませんでした。")
        else:
            validation_results["warnings"].append("重複除去用のキー列が見つからないため、重複除去をスキップしました。")
    
        # --- 数値列の処理 ---
        numeric_cols_to_process = [
            "在院患者数", "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"
        ]
        for col in numeric_cols_to_process:
            if col in df_processed.columns:
                # 非数値データをNaNに変換
                df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce')
                    
                # 数値列のNaNを0で埋める
                na_vals_before_fill = df_processed[col].isna().sum()
                if na_vals_before_fill > 0:
                    df_processed[col] = df_processed[col].fillna(0)
                    validation_results["info"].append(f"数値列'{col}'の欠損値 {na_vals_before_fill} 件を0で補完しました。")
            else:
                # 数値列が存在しない場合は0で埋めた列を作成
                df_processed[col] = 0
                validation_results["warnings"].append(f"数値列'{col}'が存在しなかったため、0で補完された列を作成しました。")
    
        # --- 列名の統一処理 --- 
        if "在院患者数" in df_processed.columns:
            df_processed["入院患者数（在院）"] = df_processed["在院患者数"].copy()
            validation_results["info"].append("「在院患者数」列を「入院患者数（在院）」列にコピーしました。")
        elif "入院患者数（在院）" not in df_processed.columns:
            validation_results["errors"].append("「在院患者数」または「入院患者数（在院）」列のいずれも存在しません。")
            df_processed["入院患者数（在院）"] = 0
            df_processed["在院患者数"] = 0
    
        # --- 派生指標の計算 ---
        if "入院患者数" in df_processed.columns and "緊急入院患者数" in df_processed.columns:
            df_processed["総入院患者数"] = df_processed["入院患者数"] + df_processed["緊急入院患者数"]
        else:
            validation_results["warnings"].append("「入院患者数」または「緊急入院患者数」列がないため、「総入院患者数」は計算できませんでした。")
            df_processed["総入院患者数"] = 0

        if "退院患者数" in df_processed.columns and "死亡患者数" in df_processed.columns:
            df_processed["総退院患者数"] = df_processed["退院患者数"] + df_processed["死亡患者数"]
        else:
            validation_results["warnings"].append("「退院患者数」または「死亡患者数」列がないため、「総退院患者数」は計算できませんでした。")
            df_processed["総退院患者数"] = 0

        if "総入院患者数" in df_processed.columns:
            df_processed["新入院患者数"] = df_processed["総入院患者数"]
        else:
            df_processed["新入院患者数"] = 0

        # 平日/休日フラグの追加
        if '日付' in df_processed.columns:
            df_processed = add_weekday_flag(df_processed)
        else:
            validation_results["errors"].append("「日付」列がないため、平日/休日フラグを追加できません。")
            
        gc.collect()
        end_time = time.time()
        
        # 最終的なデータ件数の確認
        final_record_count = len(df_processed)
        total_loss = initial_record_count - final_record_count
        loss_rate = (total_loss / initial_record_count) * 100 if initial_record_count > 0 else 0
        
        validation_results["info"].append(f"データ前処理時間: {end_time - start_time:.2f}秒")
        validation_results["info"].append(f"処理後のレコード数: {final_record_count:,}")
        validation_results["info"].append(f"総データ損失: {total_loss:,}件（{loss_rate:.1f}%）")
        
        # 大量データ損失の警告
        if loss_rate > 30:
            validation_results["errors"].append(f"🚨 重大な警告: {loss_rate:.1f}%のデータが失われました。設定を確認してください。")
        elif loss_rate > 10:
            validation_results["warnings"].append(f"⚠️ 注意: {loss_rate:.1f}%のデータが失われました。")
        
        if not df_processed.empty:
            validation_results["info"].append(f"データ期間: {df_processed['日付'].min().strftime('%Y/%m/%d')} - {df_processed['日付'].max().strftime('%Y/%m/%d')}")
        
        if df_processed.empty:
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
    複数のExcelファイルを並列処理で読み込む（修正版）
    """
    start_time = time.time()
    
    # ファイルリストの準備
    df_list = []
    files_to_process = []

    if base_file:
        files_to_process.append(base_file)
        print(f"基本ファイルを処理リストに追加: {base_file.name}")
    
    if new_files:
        files_to_process.extend(new_files)
        print(f"追加ファイル{len(new_files)}件を処理リストに追加")

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
            file_obj.seek(0)
            file_size = len(file_content) / (1024 * 1024)
            print(f"ファイル読込: {file_obj.name} ({file_size:.2f} MB)")
        except Exception as e:
            print(f"ファイル読込エラー ({file_obj.name}): {str(e)}")

    # 並列処理の設定
    max_workers = min(4, len(file_contents)) if file_contents else 1
    print(f"並列処理ワーカー数: {max_workers}")
    
    # 並列処理でExcelファイルを読み込む
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(read_excel_cached, content, 0, usecols_excel, dtype_excel): name
            for name, content in file_contents
        }

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

    if not df_list:
        print("読み込み可能なExcelデータがありません。")
        return pd.DataFrame()

    # データフレームの結合
    try:
        df_raw = pd.concat(df_list, ignore_index=True)
        
        # ✅ 修正：結合後の重複除去を安全に実行
        before_dedup = len(df_raw)
        df_raw = efficient_duplicate_check(df_raw)  # 修正済みの関数を使用
        after_dedup = len(df_raw)
        
        dedup_removed = before_dedup - after_dedup
        print(f"重複除去: {dedup_removed:,}件削除")
        
        # 結果の出力
        end_time = time.time()
        rows, cols = df_raw.shape
        print(f"データ読込完了: {successful_files}/{len(file_contents)}ファイル成功, {rows}行 × {cols}列, 処理時間: {end_time - start_time:.2f}秒")
        
        return df_raw
    except Exception as e:
        print(f"データフレーム結合エラー: {str(e)}")
        return pd.DataFrame()