# utils.py - 共通ユーティリティ関数
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def safe_date_input(
    label, 
    df, 
    session_key, 
    default_offset_days=30, 
    is_end_date=False,
    related_start_key=None
):
    """
    安全な日付選択UI
    
    Parameters:
    -----------
    label : str
        日付選択のラベル
    df : pd.DataFrame
        データフレーム（日付範囲の計算用）
    session_key : str
        セッション状態のキー
    default_offset_days : int
        デフォルト値の計算用オフセット日数
    is_end_date : bool
        終了日かどうか
    related_start_key : str
        関連する開始日のセッションキー（終了日の場合）
    
    Returns:
    --------
    datetime.date
        選択された日付
    """
    
    if df is None or df.empty or '日付' not in df.columns:
        st.error("日付データが利用できません。")
        return datetime.now().date()
    
    # データの日付範囲を取得
    data_min_date = df['日付'].min().date()
    data_max_date = df['日付'].max().date()
    
    # セッション状態から値を取得
    session_value = st.session_state.get(session_key)
    
    # デフォルト値の計算
    if is_end_date:
        # 終了日の場合
        if related_start_key and related_start_key in st.session_state:
            related_start = st.session_state[related_start_key]
            if isinstance(related_start, datetime.date):
                # 開始日から適切な期間を設定
                ideal_end = related_start + timedelta(days=default_offset_days)
                default_value = min(ideal_end, data_max_date)
            else:
                default_value = data_max_date
        else:
            default_value = data_max_date
    else:
        # 開始日の場合
        ideal_start = data_max_date - timedelta(days=default_offset_days)
        default_value = max(ideal_start, data_min_date)
    
    # セッション値の安全性チェック
    if session_value is not None:
        if isinstance(session_value, str):
            try:
                session_value = datetime.strptime(session_value, '%Y-%m-%d').date()
            except:
                session_value = None
        
        if (session_value and 
            isinstance(session_value, datetime.date) and 
            data_min_date <= session_value <= data_max_date):
            default_value = session_value
        else:
            # 範囲外の場合は警告表示
            if session_value:
                st.warning(f"{label}: 前回の設定({session_value})が範囲外のため、デフォルト値を調整しました。")
    
    # 日付入力
    selected_date = st.date_input(
        label,
        value=default_value,
        min_value=data_min_date,
        max_value=data_max_date,
        key=f"{session_key}_widget"
    )
    
    # セッション状態に保存
    st.session_state[session_key] = selected_date
    
    return selected_date

def clear_date_session_states():
    """日付関連のセッション状態をクリア"""
    
    date_session_keys = [
        'dow_comparison_start_date', 'dow_comparison_end_date',
        'alos_start_date', 'alos_end_date',
        'analysis_start_date', 'analysis_end_date',
        'dow_analysis_start_date', 'dow_analysis_end_date',
        'custom_start_date', 'custom_end_date'
    ]
    
    cleared_count = 0
    for key in date_session_keys:
        if key in st.session_state:
            del st.session_state[key]
            cleared_count += 1
    
    return cleared_count

def validate_date_range(start_date, end_date, max_days=365):
    """日付範囲の妥当性をチェック"""
    
    if start_date > end_date:
        return False, "開始日は終了日以前である必要があります。"
    
    period_days = (end_date - start_date).days + 1
    
    if period_days > max_days:
        return False, f"期間が長すぎます（最大{max_days}日）。"
    
    if period_days < 1:
        return False, "期間は最低1日必要です。"
    
    return True, f"選択期間: {period_days}日間"

# dow_analysis_tab.py での使用例
def create_safe_comparison_period_selector(df, start_date, end_date):
    """安全な期間比較セレクター"""
    
    st.markdown("### 📅 比較期間選択")
    
    col1, col2 = st.columns(2)
    
    with col1:
        comp_start = safe_date_input(
            "比較期間：開始日",
            df=df,
            session_key="dow_comparison_start_date",
            default_offset_days=365,  # 1年前
            is_end_date=False
        )
    
    with col2:
        # 現在期間と同じ長さにする
        current_period_days = (end_date - start_date).days
        
        comp_end = safe_date_input(
            "比較期間：終了日",
            df=df,
            session_key="dow_comparison_end_date", 
            default_offset_days=current_period_days,
            is_end_date=True,
            related_start_key="dow_comparison_start_date"
        )
    
    # 期間の妥当性チェック
    is_valid, message = validate_date_range(comp_start, comp_end)
    
    if is_valid:
        st.success(message)
    else:
        st.error(message)
        return None, None
    
    return comp_start, comp_end

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