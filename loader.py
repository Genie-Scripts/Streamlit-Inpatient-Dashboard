from concurrent.futures import ThreadPoolExecutor
import concurrent.futures  # 完全なモジュールもインポート
import pandas as pd
import streamlit as st
import hashlib
import os
import tempfile
from io import BytesIO
import time  # time モジュールを追加
import gc  # gc モジュールを追加

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
        import time
        file_size = len(file_content_bytes)
        timestamp = int(time.time())
        return f"size_{file_size}_time_{timestamp}"

@st.cache_data(ttl=3600, show_spinner=False)
def read_excel_cached(file_content_bytes, sheet_name=0, usecols=None, dtype=None):
    """
    ファイル内容に基づいたキャッシュを使用してExcelを読み込む
    列名の柔軟な対応を追加
    """
    temp_path = None
    try:
        # 一時ファイルを作成
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
            temp_file.write(file_content_bytes)
            temp_path = temp_file.name

        # まず列名を確認するために1行だけ読み込む
        try:
            df_header = pd.read_excel(temp_path, sheet_name=sheet_name, nrows=0, engine='openpyxl')
            available_columns = list(df_header.columns)
            print(f"利用可能な列: {available_columns}")
        except Exception as e:
            print(f"ヘッダー読み込みエラー: {e}")
            available_columns = []

        # 期待される列名がない場合は、そのファイルをスキップ
        expected_columns = ['病棟コード', '診療科名', '日付', '在院患者数']
        matching_columns = [col for col in expected_columns if col in available_columns]
        
        if len(matching_columns) < 2:  # 最低2列は必要
            print(f"警告: ファイルの列名が期待される形式と大きく異なります。スキップします。")
            print(f"期待列: {expected_columns}")
            print(f"実際列: {available_columns}")
            return None

        # 列名のマッピング辞書（柔軟な対応）
        column_mapping = {
            # 標準名: [可能な列名のリスト]
            '日付': ['日付', 'Date', '年月日', 'DATE'],
            '病棟コード': ['病棟コード', '病棟', 'Ward Code', 'Ward', '病棟CD'],
            '診療科名': ['診療科名', '診療科', 'Department', 'Dept', '科名'],
            '在院患者数': ['在院患者数', '在院', 'Current Patients', '現在患者数'],
            '入院患者数': ['入院患者数', '入院', 'Admissions', '新入院'],
            '緊急入院患者数': ['緊急入院患者数', '緊急入院', 'Emergency Admissions', '救急入院'],
            '退院患者数': ['退院患者数', '退院', 'Discharges', '退院者数'],
            '死亡患者数': ['死亡患者数', '死亡', 'Deaths', '死亡者数']
        }

        # 実際に使用する列名を決定
        final_usecols = []
        final_dtype = {}
        column_rename_map = {}

        if usecols and available_columns:
            for required_col in usecols:
                matched_col = None
                
                # 完全一致をまず試す
                if required_col in available_columns:
                    matched_col = required_col
                else:
                    # マッピングから検索
                    possible_names = column_mapping.get(required_col, [required_col])
                    for possible_name in possible_names:
                        if possible_name in available_columns:
                            matched_col = possible_name
                            break
                
                if matched_col:
                    final_usecols.append(matched_col)
                    if matched_col != required_col:
                        column_rename_map[matched_col] = required_col
                    
                    # データ型も対応
                    if dtype and required_col in dtype:
                        final_dtype[matched_col] = dtype[required_col]
                else:
                    print(f"警告: 列 '{required_col}' が見つかりません")

            print(f"最終使用列: {final_usecols}")
            print(f"列名変換: {column_rename_map}")
            
            # 最終チェック：重要な列が見つからない場合はファイルをスキップ
            essential_columns = ['病棟コード', '診療科名', '日付']
            found_essential = [col for col in essential_columns if col in [column_rename_map.get(c, c) for c in final_usecols]]
            
            if len(found_essential) < 2:
                print(f"重要な列が不足しているため、このファイルをスキップします。")
                return None
                
        else:
            # usecolsが指定されていない、または列名が取得できない場合は全て読み込む
            final_usecols = None
            final_dtype = dtype

        # Excelファイルの読み込み
        df = pd.read_excel(
            temp_path, 
            sheet_name=sheet_name, 
            engine='openpyxl', 
            usecols=final_usecols, 
            dtype=final_dtype
        )
        
        # 列名の変換
        if column_rename_map:
            df = df.rename(columns=column_rename_map)
            print(f"列名を変換しました: {column_rename_map}")
        
        # 基本的な検証
        if df.empty:
            print(f"警告: 読み込まれたExcelファイルが空です: sheet_name={sheet_name}")
            return None
            
        print(f"Excel読込成功: {df.shape[0]}行 × {df.shape[1]}列")
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

# data_processing_tab.py の EXCEL_USE_COLUMNS も柔軟にする
EXCEL_USE_COLUMNS_FLEXIBLE = [
    "病棟コード", "診療科名", "日付", "在院患者数",
    "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"
]

# より柔軟な列名リスト（オプション）
EXCEL_OPTIONAL_COLUMNS = [
    "転科入院患者数", "転科退院患者数", "平均在院日数"
]

def process_uploaded_file(uploaded_file):
    """
    アップロードされたファイルを処理する
    
    Parameters:
    -----------
    uploaded_file: StreamlitUploadedFile
        Streamlitのファイルアップローダーからのファイルオブジェクト
        
    Returns:
    --------
    pd.DataFrame
        読み込まれたデータフレーム
    """
    start_time = time.time()
    
    try:
        # ファイルをバイトとして読み込む
        uploaded_file.seek(0)
        file_content = uploaded_file.read()
        uploaded_file.seek(0)  # ファイルポインタを戻す
        
        file_size = len(file_content) / (1024 * 1024)  # MBに変換
        print(f"ファイル読込開始: {uploaded_file.name} ({file_size:.2f} MB)")
        
        # ファイル拡張子の確認
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        
        if file_extension in ['.xlsx', '.xls']:
            # Excel ファイルの読み込み
            df = read_excel_cached(file_content)
        elif file_extension == '.csv':
            # CSV ファイルの読み込み
            try:
                # UTF-8 で試みる
                df = pd.read_csv(BytesIO(file_content), encoding='utf-8')
            except UnicodeDecodeError:
                # Shift-JIS で試みる
                df = pd.read_csv(BytesIO(file_content), encoding='shift-jis')
        else:
            print(f"サポートされていないファイル形式: {file_extension}")
            return pd.DataFrame()
        
        if df is None or df.empty:
            print(f"ファイル '{uploaded_file.name}' が空か読み込みに失敗しました")
            return pd.DataFrame()
        
        end_time = time.time()
        rows, cols = df.shape
        print(f"ファイル '{uploaded_file.name}' の読込成功: {rows}行 × {cols}列, 処理時間: {end_time - start_time:.2f}秒")
        
        return df
    
    except Exception as e:
        print(f"ファイル '{uploaded_file.name}' の処理エラー: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return pd.DataFrame()

def load_files(base_file, new_files, usecols_excel=None, dtype_excel=None):
    """
    複数のExcelファイルを並列処理で読み込む（修正版）
    
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
        
        # ✅ 修正：重複除去を削除（後段のintegrated_preprocess_dataで適切に処理される）
        # 元のコード（削除）：
        # from integrated_preprocessing import efficient_duplicate_check
        # df_raw = efficient_duplicate_check(df_raw)
        
        print(f"重複除去処理をスキップ（後段で適切に処理されます）")
        
        # 結果の出力
        end_time = time.time()
        rows, cols = df_raw.shape
        print(f"データ読込完了: {successful_files}/{len(file_contents)}ファイル成功, {rows}行 × {cols}列, 処理時間: {end_time - start_time:.2f}秒")
        
        return df_raw
    except Exception as e:
        print(f"データフレーム結合エラー: {str(e)}")
        return pd.DataFrame()