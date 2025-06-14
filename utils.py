# utils.py - 共通ユーティリティ関数
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re # 病棟コードのパターンマッチング用
import logging # ロギング用に追加

logger = logging.getLogger(__name__) # ロガーのセットアップ

# --- 診療科マッピング関連関数 ---
def create_dept_mapping_table(target_data_df=None):
    """
    目標データと共通設定から診療科マッピングテーブルを作成する
    """
    # 引数が渡されていない場合はセッションステートから取得
    if target_data_df is None:
        target_data_df = st.session_state.get('target_data')

    dept_mapping = {}
    # 目標データが存在するか確認
    if target_data_df is None or target_data_df.empty or \
       '部門コード' not in target_data_df.columns or '部門名' not in target_data_df.columns:
        logger.warning("診療科マッピング: 目標値データが見つからないか、必要な列（部門コード, 部門名）がありません。")
        # 目標値ファイルがなくても特別なマッピングは適用する可能性があるため、処理を続ける
    else:
        # マッピングテーブルを作成
        for _, row in target_data_df.iterrows():
            code = str(row.get('部門コード', '')).strip()
            name = str(row.get('部門名', '')).strip()
            if code and name:  # コードと名前が両方存在する場合のみマッピング
                dept_mapping[code] = name
                dept_mapping[name] = name   # 追加: 診療科名が部門名と同じ場合も

    # --- 特別なマッピングの読み込みと適用 ---
    # st.session_state.common_config から SPECIAL_DEPT_MAPPINGS を取得
    # common_config が存在しないか、キーがない場合は空の辞書を使用
    common_config_dict = st.session_state.get('common_config', {})
    special_mappings_from_config = common_config_dict.get('SPECIAL_DEPT_MAPPINGS', {}) #

    if special_mappings_from_config:
        dept_mapping.update(special_mappings_from_config)
        logger.info(f"config.py から {len(special_mappings_from_config)} 件の特別な診療科マッピングを適用しました。")
    else:
        logger.info("config.py に SPECIAL_DEPT_MAPPINGS の定義がないか、空です。特別なマッピングは適用されませんでした。")
    # --- ここまでが修正箇所 ---

    logger.info(f"診療科マッピングテーブル作成完了: 合計 {len(dept_mapping)}件のマッピング") #
    st.session_state.dept_mapping = dept_mapping
    st.session_state.dept_mapping_initialized = True #
    return dept_mapping

def get_display_name_for_dept(dept_code, default_name=None):
    """
    部門コードから表示用の部門名を取得する
    """
    # マッピングがまだ作成されていなければ作成
    if not st.session_state.get('dept_mapping_initialized', False):
        create_dept_mapping_table()

    dept_mapping = st.session_state.get('dept_mapping', {})
    dept_code_str = str(dept_code).strip()

    # 部門コードが直接マッピングに存在すれば対応する部門名を返す
    if dept_code_str in dept_mapping:
        return dept_mapping[dept_code_str]

    # 存在しなければデフォルト値またはコードそのものを返す
    return default_name if default_name is not None else dept_code_str

def create_dept_display_options(dept_codes, dept_mapping=None):
    """
    診療科選択用の表示オプションを作成
    """
    options = []
    option_to_code = {}

    # マッピング辞書が指定されていない場合はセッションステートから取得
    if dept_mapping is None:
        if not st.session_state.get('dept_mapping_initialized', False):
            create_dept_mapping_table() # マッピングを初期化
        dept_mapping = st.session_state.get('dept_mapping', {})

    # 実績データの診療科コードをソートして処理
    for dept_code in sorted(list(set(str(c).strip() for c in dept_codes if pd.notna(c)))):
        # 修正: dept_mapping 引数を削除
        display_name = get_display_name_for_dept(dept_code, default_name=dept_code)
        if display_name != dept_code:
            display_option = f"{dept_code}（{display_name}）"
        else:
            display_option = dept_code

        options.append(display_option)
        option_to_code[display_option] = dept_code

    return options, option_to_code

# --- 病棟マッピング関連関数 ---
def create_ward_name_mapping(df_actual_data, target_data_df=None):
    """
    病棟コードから病棟名へのマッピング辞書を作成
    目標値ファイルの情報も考慮して、より正確な表示名を目指す
    """
    ward_mapping = {}

    # 1. 目標値ファイルから病棟の正式名称を優先的に取得
    if target_data_df is not None and not target_data_df.empty and \
       all(col in target_data_df.columns for col in ['部門コード', '部門名', '部門種別']):
        # 「部門種別」が「病棟」である行をフィルタリング
        ward_rows_from_target = target_data_df[target_data_df['部門種別'].astype(str).str.strip() == '病棟']
        for _, row in ward_rows_from_target.iterrows():
            code = str(row.get('部門コード', '')).strip()
            name = str(row.get('部門名', '')).strip()
            if code and name:
                ward_mapping[code] = name
        logger.info(f"目標値ファイルから {len(ward_mapping)} 件の病棟マッピングを登録しました。")

    # 2. 実績データから病棟コードを取得し、マッピングが存在しない場合はルールベースで生成
    if df_actual_data is None or df_actual_data.empty or '病棟コード' not in df_actual_data.columns:
        if not ward_mapping: # 目標値からも実績からも何も得られなかった場合
            logger.warning("病棟マッピング: 実績データが見つからないか、「病棟コード」列がありません。")
        st.session_state.ward_mapping = ward_mapping
        st.session_state.ward_mapping_initialized = True
        return ward_mapping

    unique_ward_codes = df_actual_data['病棟コード'].unique()

    for code in unique_ward_codes:
        if pd.isna(code):
            continue
        code_str = str(code).strip()

        # 既に目標値ファイルからマッピングされていればスキップ
        if code_str in ward_mapping:
            continue

        # ルールベースでの病棟名生成
        if len(code_str) >= 3:
            try:
                floor_part = code_str[:2]
                floor_num = str(int(floor_part)) # 先頭の0を除去
                ward_letter = code_str[2:]
                generated_name = f"{floor_num}階{ward_letter}病棟"
                ward_mapping[code_str] = generated_name
            except (ValueError, IndexError):
                ward_mapping[code_str] = code_str # 変換できない場合はそのまま使用
        else:
            ward_mapping[code_str] = code_str # 3文字未満はそのまま

    logger.info(f"病棟マッピングテーブル作成完了: 合計 {len(ward_mapping)}件のマッピング")
    st.session_state.ward_mapping = ward_mapping
    st.session_state.ward_mapping_initialized = True
    return ward_mapping

def get_ward_display_name(ward_code, ward_mapping=None):
    """
    病棟コードに対応する表示名を取得
    """
    if pd.isna(ward_code):
        return str(ward_code) # NaNの場合はそのまま文字列として返す

    ward_code_str = str(ward_code).strip()

    # マッピング辞書が指定されていない場合はセッションステートから取得
    if ward_mapping is None:
        if not st.session_state.get('ward_mapping_initialized', False):
            # 実績データと目標値データを渡して初期化を試みる
            # これらがセッションに存在することが前提
            df_for_init = st.session_state.get('df')
            target_df_for_init = st.session_state.get('target_data')
            create_ward_name_mapping(df_for_init, target_df_for_init)
        ward_mapping = st.session_state.get('ward_mapping', {})

    # マッピングから病棟名を取得、なければコード自体を返す
    return ward_mapping.get(ward_code_str, ward_code_str)

def create_ward_display_options(ward_codes, ward_mapping=None):
    """
    病棟選択用の表示オプションを作成
    """
    options = []
    option_to_code = {}

    # マッピング辞書が指定されていない場合はセッションステートから取得
    if ward_mapping is None:
        if not st.session_state.get('ward_mapping_initialized', False):
            df_for_init = st.session_state.get('df')
            target_df_for_init = st.session_state.get('target_data')
            create_ward_name_mapping(df_for_init, target_df_for_init)
        ward_mapping = st.session_state.get('ward_mapping', {})

    # 実績データの病棟コードをソートして処理
    for ward_code in sorted(list(set(str(c).strip() for c in ward_codes if pd.notna(c)))): #
        ward_name = get_ward_display_name(ward_code, ward_mapping=ward_mapping) # マッピングを渡す

        # 病棟名が病棟コードと異なる場合は「コード（名前）」形式で表示
        if ward_name != ward_code:
            display_option = f"{ward_code}（{ward_name}）"
        else:
            display_option = ward_code

        options.append(display_option)
        option_to_code[display_option] = ward_code

    return options, option_to_code

# --- マッピング初期化関数 ---
def initialize_all_mappings(df_actual_data, target_data_df=None):
    """
    全てのマッピング（診療科・病棟）を初期化
    """
    logger.info("全てのマッピングの初期化を開始します。")
    try:
        # 既存のマッピングをリセットするために初期化フラグをFalseにする
        st.session_state.dept_mapping_initialized = False
        st.session_state.ward_mapping_initialized = False
        st.session_state.dept_mapping = {} # 辞書もクリア
        st.session_state.ward_mapping = {} # 辞書もクリア

        # 診療科マッピングの初期化
        create_dept_mapping_table(target_data_df) #

        # 病棟マッピングの初期化 (実績データ df_actual_data と目標値データ target_data_df を渡す)
        create_ward_name_mapping(df_actual_data, target_data_df) #

        logger.info("全てのマッピングが正常に初期化されました。") #

    except Exception as e:
        logger.error(f"マッピング初期化中にエラーが発生しました: {e}", exc_info=True) #
        # エラーが発生してもアプリケーションを継続

# --- マッピング状況確認関数 ---
def get_mapping_status():
    """
    マッピングの初期化状況を取得
    """
    return {
        'dept_mapping_initialized': st.session_state.get('dept_mapping_initialized', False), #
        'ward_mapping_initialized': st.session_state.get('ward_mapping_initialized', False), #
        'dept_mapping_count': len(st.session_state.get('dept_mapping', {})), #
        'ward_mapping_count': len(st.session_state.get('ward_mapping', {})) #
    }

# --- 日付関連ユーティリティ関数 ---
def safe_date_filter(df, start_date=None, end_date=None):
    """安全な日付フィルタリング"""
    try:
        if df is None or df.empty:
            return pd.DataFrame()

        df_result = df.copy()

        if '日付' not in df_result.columns:
            logger.warning("safe_date_filter: '日付'列がデータフレームに存在しません。")
            return df_result

        if not pd.api.types.is_datetime64_any_dtype(df_result['日付']):
            df_result['日付'] = pd.to_datetime(df_result['日付'], errors='coerce')
            nat_count = df_result['日付'].isna().sum()
            if nat_count > 0:
                logger.warning(f"safe_date_filter: '日付'列の変換でNaTが {nat_count} 件発生しました。")
                df_result = df_result.dropna(subset=['日付']) # NaT行を除外

        if start_date is not None:
            try:
                start_date_pd = pd.Timestamp(start_date).normalize()
                df_result = df_result[df_result['日付'] >= start_date_pd]
            except Exception as e_start:
                logger.error(f"safe_date_filter: 開始日の処理エラー: {e_start}")

        if end_date is not None:
            try:
                end_date_pd = pd.Timestamp(end_date).normalize()
                df_result = df_result[df_result['日付'] <= end_date_pd]
            except Exception as e_end:
                logger.error(f"safe_date_filter: 終了日の処理エラー: {e_end}")

        return df_result

    except Exception as e:
        logger.error(f"日付フィルタリング処理全体でエラー: {e}", exc_info=True)
        return df # エラー時は元のDFを返すか、空のDFを返すのが適切

def safe_date_input(
    label,
    df,
    session_key,
    default_offset_days=30,
    is_end_date=False,
    related_start_key=None
): #
    """
    安全な日付選択UI

    Returns:
    --------
    pd.Timestamp
        選択された日付（Timestamp型）
    """

    if df is None or df.empty or '日付' not in df.columns:
        logger.error(f"safe_date_input ({label}): 日付データが利用できません。")
        # フォールバックとして今日の日付を返すか、エラーを発生させる
        st.error(f"{label}: 分析データの日付列が見つかりません。")
        return pd.Timestamp(datetime.now().date()).normalize()

    # データの日付範囲を取得
    try:
        # NaTが含まれているとmin/maxでエラーになるため、dropnaする
        valid_dates = df['日付'].dropna()
        if valid_dates.empty:
            logger.error(f"safe_date_input ({label}): 有効な日付データがありません。")
            st.error(f"{label}: 有効な日付データがありません。")
            return pd.Timestamp(datetime.now().date()).normalize()
        data_min_date = valid_dates.min().date()
        data_max_date = valid_dates.max().date()
    except Exception as e:
        logger.error(f"safe_date_input ({label}): データの日付範囲取得エラー: {e}")
        st.error(f"{label}: データの日付範囲が取得できませんでした。")
        return pd.Timestamp(datetime.now().date()).normalize()


    # セッション状態から値を取得
    session_value_dt = st.session_state.get(session_key)
    if isinstance(session_value_dt, pd.Timestamp): # Timestampならdate型に
        session_value_dt = session_value_dt.date()
    elif not isinstance(session_value_dt, datetime.date): # それ以外ならNone
        session_value_dt = None

    # デフォルト値の計算
    default_value_dt = None
    if is_end_date:
        # 終了日の場合
        related_start_dt = None
        if related_start_key and related_start_key in st.session_state:
            related_start_val = st.session_state[related_start_key]
            if isinstance(related_start_val, pd.Timestamp):
                related_start_dt = related_start_val.date()
            elif isinstance(related_start_val, datetime.date):
                related_start_dt = related_start_val

        if related_start_dt:
            ideal_end_dt = related_start_dt + timedelta(days=default_offset_days)
            default_value_dt = min(ideal_end_dt, data_max_date)
        else:
            default_value_dt = data_max_date
    else:
        # 開始日の場合
        ideal_start_dt = data_max_date - timedelta(days=default_offset_days)
        default_value_dt = max(ideal_start_dt, data_min_date)

    # セッション値の安全性チェックと適用
    if session_value_dt and data_min_date <= session_value_dt <= data_max_date:
        # 終了日の場合、開始日より前にならないように調整
        if is_end_date and related_start_key:
            related_start_dt_for_check = None
            related_start_val_check = st.session_state.get(related_start_key)
            if isinstance(related_start_val_check, pd.Timestamp):
                related_start_dt_for_check = related_start_val_check.date()
            elif isinstance(related_start_val_check, datetime.date):
                 related_start_dt_for_check = related_start_val_check

            if related_start_dt_for_check and session_value_dt < related_start_dt_for_check:
                final_default_value_dt = default_value_dt # セッション値が無効なので計算したデフォルトを使う
                logger.warning(f"{label}: 保存されていた日付({session_value_dt})が開始日({related_start_dt_for_check})より前です。デフォルト値({final_default_value_dt})を使用します。")
            else:
                final_default_value_dt = session_value_dt # セッション値が有効
        else: # 開始日の場合、または終了日で関連開始キーがない場合
            final_default_value_dt = session_value_dt
    else:
        final_default_value_dt = default_value_dt
        if session_value_dt: # 範囲外だった場合
            logger.warning(f"{label}: 保存されていた日付({session_value_dt})がデータの範囲外です。デフォルト値({final_default_value_dt})を使用します。")

    # st.date_inputの最小値・最大値調整（終了日の場合）
    min_val_for_widget = data_min_date
    if is_end_date and related_start_key:
        related_start_dt_for_widget = None
        related_start_val_widget = st.session_state.get(related_start_key)
        if isinstance(related_start_val_widget, pd.Timestamp):
            related_start_dt_for_widget = related_start_val_widget.date()
        elif isinstance(related_start_val_widget, datetime.date):
            related_start_dt_for_widget = related_start_val_widget

        if related_start_dt_for_widget:
            min_val_for_widget = max(data_min_date, related_start_dt_for_widget)
            if final_default_value_dt < min_val_for_widget: # デフォルト値が最小値より小さい場合は調整
                final_default_value_dt = min_val_for_widget


    # 日付入力ウィジェット
    selected_date_dt = st.date_input(
        label,
        value=final_default_value_dt,
        min_value=min_val_for_widget,
        max_value=data_max_date,
        key=f"widget_{session_key}" # ウィジェットキーをセッションキーと区別
    )
    selected_timestamp = pd.Timestamp(selected_date_dt).normalize()
    st.session_state[session_key] = selected_timestamp # Timestampで保存
    return selected_timestamp


def clear_date_session_states(): #
    """日付関連のセッション状態をクリア"""
    date_session_keys = [
        # dow_analysis_tab.py
        'dow_comparison_start_date', 'dow_comparison_end_date',
        'dow_unit_selectbox', 'dow_target_wards_multiselect', 'dow_target_depts_multiselect',
        'dow_chart_metrics_multiselect', 'dow_aggregation_selectbox', 'dow_enable_comparison',
        'dow_comparison_display_mode', 'dow_comparison_graph_layout',
        'dow_comparison_metric_selector', 'dow_comparison_bar_style', 'dow_comparison_period_selector',

        # alos_analysis_tab.py (想定されるキー)
        'alos_granularity', 'alos_unit', 'alos_target_wards', 'alos_target_depts',
        'alos_ma_rolling_days', 'alos_benchmark',

        # individual_analysis_tab.py (想定されるキー)
        'ind_filter_type', 'ind_dept_select_display', 'ind_ward_select_display',
        'ind_graph_display_period_widget',

        # app.py / global (想定されるキー)
        'analysis_start_date', 'analysis_end_date', 'period_mode', 'global_preset_period',
        'custom_start_date', 'custom_end_date', 'sidebar_start_date', 'sidebar_end_date',
        'analysis_period_type', 'analysis_preset_period' # これらは get_analysis_period で使われる

        # pdf_output_tab.py (想定されるキー)
        'pdf_period_selector', 'pdf_custom_start', 'pdf_custom_end'
    ]
    cleared_count = 0
    for key in date_session_keys:
        if key in st.session_state:
            del st.session_state[key]
            cleared_count += 1
    logger.info(f"{cleared_count}個の日付・期間関連セッション状態をクリアしました。")
    return cleared_count

def validate_date_range(start_date_ts, end_date_ts, max_days=None): # max_daysはオプションに
    """日付範囲の妥当性をチェック (入力はTimestampを想定)"""
    if not isinstance(start_date_ts, pd.Timestamp) or not isinstance(end_date_ts, pd.Timestamp):
        return False, "開始日または終了日が有効な日付形式ではありません。"

    if start_date_ts > end_date_ts:
        return False, "開始日は終了日以前である必要があります。"

    period_days = (end_date_ts - start_date_ts).days + 1

    if period_days < 1: # 通常は start_date > end_date で捕捉されるが一応
        return False, "期間は最低1日必要です。"

    if max_days is not None and period_days > max_days:
        return False, f"期間が長すぎます（最大{max_days}日）。現在: {period_days}日間"

    return True, f"選択期間: {period_days}日間"


def create_safe_comparison_period_selector(df, current_start_date_ts, current_end_date_ts): #
    """
    安全な期間比較セレクター (dow_analysis_tab.py での使用を想定)
    df: 分析対象の全データフレーム
    current_start_date_ts, current_end_date_ts: 現在の分析期間の開始日と終了日 (Timestamp)
    """
    st.markdown("### 📅 比較期間選択")
    col1, col2 = st.columns(2)

    with col1:
        comp_start_ts = safe_date_input(
            "比較期間：開始日",
            df=df, # 全データの日付範囲を参照
            session_key="dow_comparison_start_date", # dow_analysis_tab 専用のセッションキー
            default_offset_days=365, # デフォルトは1年前
            is_end_date=False
        )
    with col2:
        # 現在の分析期間と同じ長さをデフォルトとする
        current_period_length_days = (current_end_date_ts - current_start_date_ts).days
        comp_end_ts = safe_date_input(
            "比較期間：終了日",
            df=df, # 全データの日付範囲を参照
            session_key="dow_comparison_end_date", # dow_analysis_tab 専用のセッションキー
            default_offset_days=current_period_length_days, # 現在期間の長さをオフセットに
            is_end_date=True,
            related_start_key="dow_comparison_start_date" # 開始日ウィジェットのキー
        )

    is_valid, message = validate_date_range(comp_start_ts, comp_end_ts) # 最大日数は設定しない
    if is_valid:
        st.success(message)
    else:
        st.error(message)
        return None, None # 無効な場合はNoneを返す

    return comp_start_ts, comp_end_ts


# --- 文字列変換ユーティリティ (変更なし) ---
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
    try:
        unique_values = df[column_name].dropna().unique()
        # safe_convert_to_str を適用し、結果をソート
        return sorted([safe_convert_to_str(val) for val in unique_values if safe_convert_to_str(val)])
    except Exception as e:
        logger.error(f"get_unique_values_as_str ({column_name}) でエラー: {e}")
        return []