# utils.py - 共通ユーティリティ関数
import streamlit as st
import pandas as pd

def safe_date_filter(df, start_date=None, end_date=None):
    """安全な日付フィルタリング"""
    try:
        if df is None or df.empty:
            return df
            
        df_result = df.copy()
        
        if '日付' not in df_result.columns:
            return df_result
        
        # 日付列をdatetime型に変換
        df_result['日付'] = pd.to_datetime(df_result['日付'])
        
        if start_date is not None:
            start_date_pd = pd.to_datetime(start_date)
            df_result = df_result[df_result['日付'] >= start_date_pd]
        
        if end_date is not None:
            end_date_pd = pd.to_datetime(end_date)
            df_result = df_result[df_result['日付'] <= end_date_pd]
        
        return df_result
        
    except Exception as e:
        print(f"日付フィルタリングエラー: {e}")
        return df
        
# ===============================================================================
# 診療科関連の関数
# ===============================================================================

def create_dept_mapping_table(target_data_df=None):
    """
    目標データから診療科マッピングテーブルを作成する
    
    Parameters:
    -----------
    target_data_df : pd.DataFrame, optional
        目標値データフレーム。指定がなければセッションステートから取得
        
    Returns:
    --------
    dict
        診療科コードと表示名のマッピング辞書
    """
    # 引数が渡されていない場合はセッションステートから取得
    if target_data_df is None:
        target_data_df = st.session_state.get('target_data')
    
    # 目標データが存在するか確認
    if target_data_df is None or target_data_df.empty or \
       '部門コード' not in target_data_df.columns or '部門名' not in target_data_df.columns:
        return {}  # 目標データがない場合は空のマッピングを返す
    
    # マッピングテーブルを作成
    dept_mapping = {}
    for _, row in target_data_df.iterrows():
        code = str(row.get('部門コード', '')).strip()
        name = str(row.get('部門名', '')).strip()
        if code and name:  # コードと名前が両方存在する場合のみマッピング
            dept_mapping[code] = name
            
    # 問題となっている診療科のマッピングを明示的に定義
    special_mappings = {
        '総合内科': '総合内科（内科除く）',
        '内科': '内科救急',
        # 他に必要なマッピングがあれば追加
    }
    
    # 特別なマッピングを追加（既存のマッピングを上書き）
    dept_mapping.update(special_mappings)
    
    # デバッグ情報（オプション）
    print(f"診療科マッピングテーブル作成完了: {len(dept_mapping)}件のマッピング")
    
    # セッションステートに保存
    st.session_state.dept_mapping = dept_mapping
    st.session_state.dept_mapping_initialized = True
    
    return dept_mapping

def get_display_name_for_dept(dept_code, default_name=None):
    """
    部門コードから表示用の部門名を取得する
    
    Parameters:
    -----------
    dept_code : str
        部門コード
    default_name : str, optional
        マッピングに存在しない場合のデフォルト名
        
    Returns:
    --------
    str
        表示用の部門名
    """
    # マッピングがまだ作成されていなければ作成
    if not st.session_state.get('dept_mapping_initialized', False):
        create_dept_mapping_table()
    
    # マッピングから部門名を取得
    dept_mapping = st.session_state.get('dept_mapping', {})
    
    # 部門コードが直接マッピングに存在すれば対応する部門名を返す
    if dept_code in dept_mapping:
        return dept_mapping[dept_code]
    
    # 存在しなければデフォルト値またはコードそのものを返す
    return default_name if default_name is not None else dept_code

def get_major_depts_from_target_data(target_df, df_actual_data=None):
    """目標設定ファイルから主要診療科リストを取得する"""
    major_depts = []
    
    # まず診療科マッピングテーブルを確認して作成/更新する
    dept_mapping = create_dept_mapping_table(target_df)
    
    if target_df is not None and not target_df.empty and '部門コード' in target_df.columns:
        # 目標設定ファイルから部門コードリストを取得
        target_dept_codes = target_df['部門コード'].astype(str).unique().tolist()
        
        # デバッグ出力
        print(f"目標設定ファイルの部門コード: {target_dept_codes}")
        print(f"診療科マッピング: {dept_mapping}")
        
        # 実績データから診療科リストを取得
        actual_depts = []
        if df_actual_data is not None and '診療科名' in df_actual_data.columns:
            actual_depts = df_actual_data['診療科名'].astype(str).unique().tolist()
            print(f"実績データの診療科: {actual_depts}")
        
        # 目標設定ファイルの部門コードに対応する実績データの診療科を抽出
        for dept_code in target_dept_codes:
            # 1. 部門コードがそのまま実績データにある場合
            if dept_code in actual_depts:
                major_depts.append(dept_code)
            # 2. 部門名が実績データにある場合
            elif dept_code in dept_mapping:
                dept_name = dept_mapping[dept_code]
                if dept_name in actual_depts:
                    major_depts.append(dept_name)
            # 3. 部門コードに対応するマッピングがない場合
            else:
                # 念のため部門コード自体を追加
                if dept_code not in major_depts:
                    major_depts.append(dept_code)
        
        # もし一致するものがなければ部門名を使用
        if not major_depts and '部門名' in target_df.columns:
            dept_names = target_df['部門名'].astype(str).unique().tolist()
            for dept_name in dept_names:
                if dept_name in actual_depts:
                    major_depts.append(dept_name)
                elif dept_name not in major_depts:
                    major_depts.append(dept_name)
    
    # 結果を出力
    print(f"主要診療科リスト: {sorted(major_depts)}")
    return sorted(list(set(major_depts)))

# ===============================================================================
# 病棟関連の関数（新規追加）
# ===============================================================================

def create_ward_name_mapping(df):
    """
    病棟コードから病棟名へのマッピング辞書を作成
    
    Parameters:
    -----------
    df : pd.DataFrame
        データフレーム（病棟コード列を含む）
        
    Returns:
    --------
    dict
        病棟コードと病棟名のマッピング辞書
    """
    ward_mapping = {}
    
    # データから病棟コードを取得
    if df is None or df.empty or '病棟コード' not in df.columns:
        return ward_mapping
    
    ward_codes = df['病棟コード'].unique()
    
    for code in ward_codes:
        # 病棟コードから病棟名を生成するロジック
        # 例: "02A" → "2階A病棟", "03B" → "3階B病棟"
        if pd.isna(code):
            continue
            
        code_str = str(code).strip()
        if len(code_str) >= 3:
            try:
                # 先頭2文字を階数として取得
                floor_part = code_str[:2]
                # 数値部分を抽出（先頭0を除去）
                floor_num = str(int(floor_part))
                # 3文字目以降を病棟識別子として取得
                ward_letter = code_str[2:]
                # 病棟名を生成
                ward_name = f"{floor_num}階{ward_letter}病棟"
                ward_mapping[code] = ward_name
            except (ValueError, IndexError) as e:
                # 変換できない場合はそのまま使用
                ward_mapping[code] = code_str
        else:
            # 3文字未満の場合はそのまま使用
            ward_mapping[code] = code_str
    
    # セッションステートにも保存
    st.session_state.ward_mapping = ward_mapping
    st.session_state.ward_mapping_initialized = True
    
    return ward_mapping

def get_ward_display_name(ward_code, ward_mapping=None):
    """
    病棟コードに対応する表示名を取得
    
    Parameters:
    -----------
    ward_code : str
        病棟コード
    ward_mapping : dict, optional
        病棟マッピング辞書。指定がなければセッションステートから取得
        
    Returns:
    --------
    str
        表示用病棟名
    """
    if pd.isna(ward_code):
        return str(ward_code)
    
    # マッピング辞書が指定されていない場合はセッションステートから取得
    if ward_mapping is None:
        ward_mapping = st.session_state.get('ward_mapping', {})
    
    # マッピングから病棟名を取得
    return ward_mapping.get(ward_code, str(ward_code))

def create_ward_display_options(ward_codes, ward_mapping=None):
    """
    病棟選択用の表示オプションを作成
    
    Parameters:
    -----------
    ward_codes : list
        病棟コードのリスト
    ward_mapping : dict, optional
        病棟マッピング辞書
        
    Returns:
    --------
    tuple
        (表示オプションリスト, オプション→コードのマッピング辞書)
    """
    options = []
    code_to_option = {}
    option_to_code = {}
    
    for ward_code in sorted(ward_codes):
        if pd.isna(ward_code):
            continue
            
        ward_name = get_ward_display_name(ward_code, ward_mapping)
        
        # 病棟名が病棟コードと異なる場合は「コード（名前）」形式で表示
        if ward_name != str(ward_code):
            display_option = f"{ward_code}（{ward_name}）"
        else:
            display_option = str(ward_code)
        
        options.append(display_option)
        code_to_option[ward_code] = display_option
        option_to_code[display_option] = ward_code
    
    return options, option_to_code

def initialize_ward_mapping(df):
    """
    病棟マッピングを初期化（一度だけ実行）
    
    Parameters:
    -----------
    df : pd.DataFrame
        データフレーム
    """
    if not st.session_state.get('ward_mapping_initialized', False):
        create_ward_name_mapping(df)

# ===============================================================================
# 共通のヘルパー関数
# ===============================================================================

def safe_convert_to_str(value):
    """
    値を安全に文字列に変換
    
    Parameters:
    -----------
    value : any
        変換する値
        
    Returns:
    --------
    str
        変換された文字列
    """
    if pd.isna(value):
        return ""
    return str(value).strip()

def get_unique_values_as_str(df, column_name):
    """
    指定された列のユニークな値を文字列のリストとして取得
    
    Parameters:
    -----------
    df : pd.DataFrame
        データフレーム
    column_name : str
        列名
        
    Returns:
    --------
    list
        ユニークな値のリスト（文字列）
    """
    if df is None or df.empty or column_name not in df.columns:
        return []
    
    unique_values = df[column_name].dropna().unique()
    return [safe_convert_to_str(val) for val in unique_values if safe_convert_to_str(val)]

# ===============================================================================
# 設定関連の関数
# ===============================================================================

def initialize_all_mappings(df, target_data_df=None):
    """
    全てのマッピング（診療科・病棟）を初期化
    
    Parameters:
    -----------
    df : pd.DataFrame
        メインのデータフレーム
    target_data_df : pd.DataFrame, optional
        目標データフレーム
    """
    try:
        # 診療科マッピングの初期化
        if target_data_df is not None:
            create_dept_mapping_table(target_data_df)
        
        # 病棟マッピングの初期化
        if df is not None and '病棟コード' in df.columns:
            create_ward_name_mapping(df)
            
        print("全てのマッピングが正常に初期化されました")
        
    except Exception as e:
        print(f"マッピング初期化中にエラーが発生しました: {e}")
        # エラーが発生してもアプリケーションを継続

def get_mapping_status():
    """
    マッピングの初期化状況を取得
    
    Returns:
    --------
    dict
        マッピング状況の辞書
    """
    return {
        'dept_mapping_initialized': st.session_state.get('dept_mapping_initialized', False),
        'ward_mapping_initialized': st.session_state.get('ward_mapping_initialized', False),
        'dept_mapping_count': len(st.session_state.get('dept_mapping', {})),
        'ward_mapping_count': len(st.session_state.get('ward_mapping', {}))
    }