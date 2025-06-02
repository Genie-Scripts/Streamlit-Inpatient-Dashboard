# loader.py (修正案)

from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import pandas as pd
import streamlit as st # 主に @st.cache_data のため
import hashlib
import os
import tempfile
from io import BytesIO
import time
import gc
import logging # logging をインポート

logger = logging.getLogger(__name__) # logger を設定

def calculate_file_hash(file_content_bytes):
    """
    ファイルのハッシュ値を計算して一意の識別子を作成
    """
    try:
        max_bytes = 10 * 1024 * 1024  # 10MB上限
        if len(file_content_bytes) > max_bytes:
            head = file_content_bytes[:5 * 1024 * 1024]
            tail = file_content_bytes[-5 * 1024 * 1024:]
            combined = head + tail
            return hashlib.md5(combined).hexdigest()
        else:
            return hashlib.md5(file_content_bytes).hexdigest()
    except Exception as e:
        logger.error(f"ファイルハッシュ計算エラー: {str(e)}", exc_info=True) # loggerを使用し、スタックトレースも記録
        file_size = len(file_content_bytes)
        timestamp = int(time.time())
        return f"size_{file_size}_time_{timestamp}" # フォールバックは維持

@st.cache_data(ttl=3600, show_spinner=False)
def read_excel_cached(file_content_bytes, sheet_name=0, usecols=None, dtype=None):
    """
    ファイル内容に基づいたキャッシュを使用してExcelを読み込む
    列名の柔軟な対応を追加
    エラーハンドリングを強化
    """
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
            temp_file.write(file_content_bytes)
            temp_path = temp_file.name

        df_header = pd.read_excel(temp_path, sheet_name=sheet_name, nrows=0, engine='openpyxl')
        available_columns = list(df_header.columns)
        logger.info(f"Excel読込試行: 利用可能な列: {available_columns}, usecols指定: {usecols}, dtype指定: {dtype}")


        expected_columns = ['病棟コード', '診療科名', '日付', '在院患者数'] # 最低限期待する列の例
        matching_columns = [col for col in expected_columns if col in available_columns]

        if len(matching_columns) < 2:
            logger.warning(f"ファイルの列名が期待される形式と大きく異なります。期待列: {expected_columns}, 実際列: {available_columns}")
            # StreamlitのUI要素はここでは使わず、呼び出し元でユーザーに通知する
            # return None # またはエラーを発生させる

        column_mapping = {
            '日付': ['日付', 'Date', '年月日', 'DATE'],
            '病棟コード': ['病棟コード', '病棟', 'Ward Code', 'Ward', '病棟CD'],
            '診療科名': ['診療科名', '診療科', 'Department', 'Dept', '科名'],
            '在院患者数': ['在院患者数', '在院', 'Current Patients', '現在患者数'],
            '入院患者数': ['入院患者数', '入院', 'Admissions', '新入院'],
            '緊急入院患者数': ['緊急入院患者数', '緊急入院', 'Emergency Admissions', '救急入院'],
            '退院患者数': ['退院患者数', '退院', 'Discharges', '退院者数'],
            '死亡患者数': ['死亡患者数', '死亡', 'Deaths', '死亡者数']
        }

        final_usecols = []
        final_dtype = {}
        column_rename_map = {}

        if usecols and available_columns:
            for required_col in usecols:
                matched_col = None
                if required_col in available_columns:
                    matched_col = required_col
                else:
                    possible_names = column_mapping.get(required_col, [required_col])
                    for possible_name in possible_names:
                        if possible_name in available_columns:
                            matched_col = possible_name
                            break
                if matched_col:
                    final_usecols.append(matched_col)
                    if matched_col != required_col:
                        column_rename_map[matched_col] = required_col
                    if dtype and required_col in dtype:
                        final_dtype[matched_col] = dtype[required_col]
                else:
                    logger.warning(f"指定された列 '{required_col}' がファイルに見つかりませんでした。")
            logger.info(f"最終的に使用する列: {final_usecols}, 列名変換マップ: {column_rename_map}")
            
            essential_columns_to_check = ['病棟コード', '診療科名', '日付'] # 読み込み後の標準名でチェック
            found_essential_after_mapping = [col for col in essential_columns_to_check if col in [column_rename_map.get(c, c) for c in final_usecols]]
            if len(found_essential_after_mapping) < 2: # 少なくとも2つの必須列が必要という仮定
                logger.error(f"重要な列が不足しているため、このファイルは処理できません。検出された必須列: {found_essential_after_mapping}")
                # return None # エラーとして扱う
                # あるいは、呼び出し元にエラーを伝播させるために例外を発生させる
                raise ValueError(f"重要な列が不足しているため、ファイル処理を中断します。検出された必須列: {found_essential_after_mapping}")


        else: # usecolsが指定されていない場合
            final_usecols = None # すべての列を読み込む
            final_dtype = dtype # 指定されたdtypeをそのまま使用

        df = pd.read_excel(
            temp_path,
            sheet_name=sheet_name,
            engine='openpyxl',
            usecols=final_usecols if final_usecols else None, # final_usecolsが空リストならNoneとして全列読む
            dtype=final_dtype if final_dtype else None      # final_dtypeが空辞書ならNoneとして型推論
        )

        if column_rename_map:
            df = df.rename(columns=column_rename_map)
            logger.info(f"列名を標準名に変換しました: {column_rename_map}")

        if df.empty:
            logger.warning(f"読み込まれたExcelファイルが空です (シート名: {sheet_name})。")
            # return None # 空のDFを返すか、エラーにするか
        
        logger.info(f"Excel読込成功: {df.shape[0]}行 × {df.shape[1]}列")
        return df

    except FileNotFoundError:
        logger.error(f"一時ファイルが見つかりません: {temp_path}", exc_info=True)
        raise # このエラーは呼び出し元で処理すべき
    except ValueError as ve: # 重要な列不足などで発生させた例外
        logger.error(f"Excelデータ検証エラー: {str(ve)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Excel読込中に予期せぬエラーが発生しました: {str(e)} (ファイルパス: {temp_path})", exc_info=True)
        raise # エラーを再発生させて呼び出し元に通知
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception as e_unlink:
                logger.error(f"一時ファイル削除エラー: {str(e_unlink)} (ファイルパス: {temp_path})", exc_info=True)

# process_uploaded_file 関数は loader.py の中にはありませんでした。
# load_files 関数は data_processing_tab.py から呼び出されるため、エラーハンドリングはその中で行います。

def load_files(base_file, new_files, usecols_excel=None, dtype_excel=None):
    """
    複数のExcelファイルを並列処理で読み込む。
    エラーハンドリングを強化
    """
    start_time = time.time()
    df_list = []
    files_to_process = []
    processed_file_names = [] # 処理したファイル名を記録

    if base_file:
        files_to_process.append(base_file)
    if new_files:
        files_to_process.extend(new_files)

    if not files_to_process:
        logger.info("処理対象ファイルがありません。")
        return pd.DataFrame(), [] # 空のDFと空のファイル名リストを返す

    file_contents = []
    for file_obj in files_to_process:
        try:
            file_obj.seek(0)
            file_content = file_obj.read()
            file_contents.append((file_obj.name, file_content))
            file_obj.seek(0)
            file_size_mb = len(file_content) / (1024 * 1024)
            logger.debug(f"ファイル内容読み込み: {file_obj.name} ({file_size_mb:.2f} MB)")
        except Exception as e:
            logger.error(f"ファイル内容のバイト列取得エラー ({file_obj.name}): {str(e)}", exc_info=True)
            # このファイルは処理対象から外す

    if not file_contents:
        logger.warning("読み込み可能なファイル内容がありません。")
        return pd.DataFrame(), []

    max_workers = min(4, os.cpu_count() or 1, len(file_contents)) # CPUコア数も考慮
    logger.info(f"並列処理ワーカー数: {max_workers}")

    successful_reads = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_name = {
            executor.submit(read_excel_cached, content, 0, usecols_excel, dtype_excel): name
            for name, content in file_contents
        }
        for future in concurrent.futures.as_completed(future_to_name):
            file_name = future_to_name[future]
            try:
                df_single = future.result() # read_excel_cached が例外を発生させる可能性あり
                if df_single is not None and not df_single.empty:
                    df_list.append(df_single)
                    processed_file_names.append(file_name) # 成功したファイル名を追加
                    successful_reads += 1
                    logger.info(f"ファイル '{file_name}' の読込成功: {df_single.shape[0]}行 × {df_single.shape[1]}列")
                elif df_single is None: # read_excel_cached が None を返した場合（例：列不足）
                    logger.warning(f"ファイル '{file_name}' は期待される形式ではないため、スキップされました。")
                else: # df_single is empty
                    logger.warning(f"ファイル '{file_name}' の読込結果が空です。")
            except ValueError as ve: # read_excel_cached 内で発生させた重要な列不足エラー
                logger.error(f"ファイル '{file_name}' の処理エラー（データ検証）: {str(ve)}")
            except Exception as e: # その他の read_excel_cached からの予期せぬエラー
                logger.error(f"ファイル '{file_name}' の処理中に予期せぬエラー: {str(e)}", exc_info=True)

    if not df_list:
        logger.warning("読み込み可能なExcelデータがありませんでした。")
        return pd.DataFrame(), []

    try:
        df_raw = pd.concat(df_list, ignore_index=True)
        del df_list # メモリ解放
        gc.collect()

        # efficient_duplicate_check は integrated_preprocessing.py にあるので、
        # ここでは呼び出さず、呼び出し元 (data_processing_tab.py) で行う。
        # df_raw = efficient_duplicate_check(df_raw) # ここでは行わない

        end_time = time.time()
        logger.info(
            f"データ読込完了: {successful_reads}/{len(file_contents)}ファイル成功, "
            f"結合後: {df_raw.shape[0]}行 × {df_raw.shape[1]}列, "
            f"処理時間: {end_time - start_time:.2f}秒"
        )
        return df_raw, processed_file_names # 処理したファイル名も返す
    except Exception as e:
        logger.error(f"データフレーム結合エラー: {str(e)}", exc_info=True)
        return pd.DataFrame(), []