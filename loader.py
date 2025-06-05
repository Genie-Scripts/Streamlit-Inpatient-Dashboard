# loader.py (修正案 - ロギング強化・エラー伝達改善)

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

        # まず列名を確認するためにヘッダー行のみ読み込む
        try:
            df_header = pd.read_excel(temp_path, sheet_name=sheet_name, nrows=0, engine='openpyxl')
            available_columns = list(df_header.columns)
        except Exception as e_header:
            logger.warning(f"Excelファイルのヘッダー読み込みに失敗しました (ファイルパス: {temp_path}, シート: {sheet_name}): {e_header}", exc_info=True)
            available_columns = [] # 列情報が取得できない場合は空リスト

        logger.info(f"Excel読込試行: 利用可能な列: {available_columns}, usecols指定: {usecols}, dtype指定: {dtype}")

        # 列名マッピングと使用列の決定ロジック
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

        if usecols: # usecols が指定されている場合のみ列選択とリネームを行う
            if not available_columns: # 列情報が取得できなかった場合はエラー
                 raise ValueError(f"Excelファイルの列情報が読み取れず、指定された列 ({usecols}) の検証ができません。")

            for required_col_standard_name in usecols: # usecols には標準名を期待
                matched_actual_col = None
                if required_col_standard_name in available_columns: # まず標準名で完全一致を探す
                    matched_actual_col = required_col_standard_name
                else: # 見つからなければマッピング候補を探す
                    possible_names_in_file = column_mapping.get(required_col_standard_name, [required_col_standard_name])
                    for possible_name in possible_names_in_file:
                        if possible_name in available_columns:
                            matched_actual_col = possible_name
                            break
                
                if matched_actual_col:
                    final_usecols.append(matched_actual_col) # ファイルに存在する列名で指定
                    if matched_actual_col != required_col_standard_name:
                        column_rename_map[matched_actual_col] = required_col_standard_name # 変換後を標準名に
                    if dtype and required_col_standard_name in dtype: # dtypeは標準名で指定されていると仮定
                        final_dtype[matched_actual_col] = dtype[required_col_standard_name]
                else:
                    # 必須列が見つからない場合は警告ログを出し、エラーにはしない（呼び出し元で列の有無を最終判断）
                    logger.warning(f"指定された必須列 '{required_col_standard_name}' (またはそのエイリアス) がファイルに見つかりませんでした。")
            
            if not final_usecols: # 読み込むべき列が一つも見つからなかった場合
                raise ValueError(f"指定された列 ({usecols}) がExcelファイル中に一つも見つかりませんでした。利用可能な列: {available_columns}")
            logger.info(f"最終的にExcelから読み込む列: {final_usecols}, 列名変換マップ: {column_rename_map}")
        else: # usecolsが指定されていない場合は全ての列を読み込む
            final_usecols = None
            final_dtype = dtype # 指定されていればそのまま使用

        df = pd.read_excel(
            temp_path,
            sheet_name=sheet_name,
            engine='openpyxl',
            usecols=final_usecols, # Noneなら全列
            dtype=final_dtype # Noneなら型推論
        )

        if column_rename_map: # 列名リネーム処理
            df = df.rename(columns=column_rename_map)
            logger.info(f"列名を標準名に変換しました: {list(column_rename_map.values())}")

        if df.empty:
            logger.warning(f"読み込まれたExcelファイルが空です (シート名: {sheet_name})。")
            # 空のDataFrameを返すのは妥当な場合もあるので、ここではエラーとしない

        logger.info(f"Excel読込成功: {df.shape[0]}行 × {df.shape[1]}列 (ファイルパス: {temp_path})")
        return df

    except FileNotFoundError:
        logger.error(f"一時ファイルが見つかりません: {temp_path}", exc_info=True)
        raise # このエラーは呼び出し元で処理すべき
    except ValueError as ve: # 重要な列不足などで発生させた例外
        logger.error(f"Excelデータ検証エラー: {str(ve)} (ファイルパス: {temp_path})", exc_info=True)
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

# EXCEL_USE_COLUMNS_FLEXIBLE と EXCEL_OPTIONAL_COLUMNS は data_processing_tab.py で使用されるため、
# loader.py 内での定義は不要かもしれません。呼び出し元で渡す usecols を制御します。
# process_uploaded_file 関数は data_processing_tab.py に同様のロジックがあるため、
# loader.py からは削除し、data_processing_tab.py 側のロジックを優先します。

def load_files(base_file, new_files, usecols_excel=None, dtype_excel=None):
    """
    複数のExcelファイルを並列処理で読み込む。
    エラーハンドリングを強化し、処理結果を詳細に返す。
    """
    start_time = time.time()
    all_dfs_list = [] # 読み込まれたDataFrameを格納するリスト
    processed_files_info = [] # 各ファイルの処理結果情報を格納するリスト

    files_to_process_with_source = []
    if base_file:
        files_to_process_with_source.append({'file_obj': base_file, 'source_type': 'base'})
    if new_files:
        for f_new in new_files:
            files_to_process_with_source.append({'file_obj': f_new, 'source_type': 'new'})

    if not files_to_process_with_source:
        logger.info("処理対象ファイルがありません。")
        return pd.DataFrame(), [] # 空のDFと空の処理情報リスト

    file_byte_contents = []
    for item in files_to_process_with_source:
        file_obj = item['file_obj']
        source_type = item['source_type']
        try:
            file_obj.seek(0)
            content = file_obj.read()
            file_obj.seek(0)
            file_byte_contents.append({'name': file_obj.name, 'content': content, 'source_type': source_type, 'status': 'pending'})
            logger.debug(f"ファイル内容読み込み: {file_obj.name} ({len(content)/(1024*1024):.2f} MB)")
        except Exception as e:
            logger.error(f"ファイル内容のバイト列取得エラー ({file_obj.name}): {str(e)}", exc_info=True)
            processed_files_info.append({'name': file_obj.name, 'status': 'error_reading_bytes', 'message': str(e), 'rows': 0, 'cols': 0})

    if not file_byte_contents:
        logger.warning("読み込み可能なファイル内容がありません。")
        return pd.DataFrame(), processed_files_info

    # 実際のCPUコア数に基づいてワーカー数を決定 (最大4まで)
    num_available_cores = os.cpu_count() or 1
    max_workers = min(4, num_available_cores, len(file_byte_contents))
    logger.info(f"並列処理ワーカー数: {max_workers} (利用可能コア: {num_available_cores})")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file_info = {
            executor.submit(read_excel_cached, item['content'], 0, usecols_excel, dtype_excel): item
            for item in file_byte_contents
        }
        for future in concurrent.futures.as_completed(future_to_file_info):
            file_info_item = future_to_file_info[future]
            file_name = file_info_item['name']
            source_type = file_info_item['source_type']
            try:
                df_single = future.result() # read_excel_cached が例外を発生させる可能性あり
                if df_single is not None and not df_single.empty:
                    df_single['_source_file_'] = file_name # どのファイル由来か追跡用列を追加
                    df_single['_source_type_'] = source_type
                    all_dfs_list.append(df_single)
                    processed_files_info.append({'name': file_name, 'status': 'success', 'message': '読み込み成功', 'rows': df_single.shape[0], 'cols': df_single.shape[1]})
                    logger.info(f"ファイル '{file_name}' の読込成功: {df_single.shape[0]}行 × {df_single.shape[1]}列")
                elif df_single is None: # read_excel_cached が None を返した場合（例：列不足、致命的エラー）
                    processed_files_info.append({'name': file_name, 'status': 'skipped_critical', 'message': '重要な列不足または読み込み不可', 'rows': 0, 'cols': 0})
                    logger.warning(f"ファイル '{file_name}' は期待される形式ではないため、スキップされました（致命的）。")
                else: # df_single is empty
                    processed_files_info.append({'name': file_name, 'status': 'empty_content', 'message': 'ファイル内容は空でした', 'rows': 0, 'cols': 0})
                    logger.warning(f"ファイル '{file_name}' の読込結果が空です。")
            except ValueError as ve:
                processed_files_info.append({'name': file_name, 'status': 'error_validation', 'message': str(ve), 'rows': 0, 'cols': 0})
                logger.error(f"ファイル '{file_name}' の処理エラー（データ検証）: {str(ve)}")
            except Exception as e:
                processed_files_info.append({'name': file_name, 'status': 'error_processing', 'message': str(e), 'rows': 0, 'cols': 0})
                logger.error(f"ファイル '{file_name}' の処理中に予期せぬエラー: {str(e)}", exc_info=True)

    if not all_dfs_list:
        logger.warning("読み込み可能なExcelデータがありませんでした。")
        return pd.DataFrame(), processed_files_info # 処理情報リストは返す

    try:
        df_combined_raw = pd.concat(all_dfs_list, ignore_index=True)
        del all_dfs_list # メモリ解放
        gc.collect()
        end_time = time.time()
        logger.info(
            f"データ読込完了: {len(processed_files_info)}ファイル試行, "
            f"結合後: {df_combined_raw.shape[0]}行 × {df_combined_raw.shape[1]}列 (ソース情報列含む), "
            f"処理時間: {end_time - start_time:.2f}秒"
        )
        # _source_file_ と _source_type_ は data_processing_tab.py で重複チェック後に削除する
        return df_combined_raw, processed_files_info
    except Exception as e:
        logger.error(f"データフレーム結合エラー: {str(e)}", exc_info=True)
        return pd.DataFrame(), processed_files_info # 処理情報リストは返す