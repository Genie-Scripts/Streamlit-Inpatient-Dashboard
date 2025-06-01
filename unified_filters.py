# unified_filters.py (修正版 - フィルター適用とUI修正)

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 統一フィルター設定
UNIFIED_FILTER_CONFIG = {
    'period_modes': ['全期間', '最近30日', '最近90日', '最近180日', '最近1年', 'カスタム期間'],
    'default_period_mode': '最近90日',
    'session_keys': {
        'period_mode': 'unified_filter_period_mode',
        'start_date': 'unified_filter_start_date',
        'end_date': 'unified_filter_end_date',
        'departments': 'unified_filter_departments',
        'wards': 'unified_filter_wards',
        'applied': 'unified_filter_applied',
        'last_raw_df_hash': 'unified_filter_last_raw_df_hash'
    }
}

def get_df_hash(df):
    """データフレームのハッシュ値を計算"""
    if df is None or df.empty:
        return "empty"
    try:
        # 形状とデータ型の情報でハッシュを作成
        shape_str = f"{df.shape[0]}_{df.shape[1]}"
        cols_str = "_".join(sorted(df.columns.astype(str)))
        return f"{shape_str}_{hash(cols_str)}"
    except Exception:
        return "unknown"

def initialize_filter_session_state(df=None):
    """統一フィルターのセッション状態を初期化"""
    
    # 基本フィルター設定の初期化
    if UNIFIED_FILTER_CONFIG['session_keys']['period_mode'] not in st.session_state:
        st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['period_mode']] = UNIFIED_FILTER_CONFIG['default_period_mode']
    
    if UNIFIED_FILTER_CONFIG['session_keys']['applied'] not in st.session_state:
        st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['applied']] = False
    
    # データが提供された場合の初期化
    if df is not None and not df.empty:
        current_df_hash = get_df_hash(df)
        last_df_hash = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['last_raw_df_hash'])
        
        # データが変更された場合は設定をリセット
        if current_df_hash != last_df_hash:
            logger.info("データ変更検出：統一フィルター設定をリセット")
            reset_filter_settings()
            st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['last_raw_df_hash']] = current_df_hash
        
        # 日付範囲の初期化
        if '日付' in df.columns and not df['日付'].empty:
            min_date = pd.to_datetime(df['日付']).min().date()
            max_date = pd.to_datetime(df['日付']).max().date()
            
            # 期間モードに基づく日付設定
            period_mode = st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['period_mode']]
            if period_mode != 'カスタム期間':
                start_date, end_date = calculate_period_dates(max_date, period_mode)
                st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['start_date']] = start_date
                st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['end_date']] = end_date
            else:
                # カスタム期間の場合、既存の設定を保持または全期間を設定
                if UNIFIED_FILTER_CONFIG['session_keys']['start_date'] not in st.session_state:
                    st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['start_date']] = min_date
                if UNIFIED_FILTER_CONFIG['session_keys']['end_date'] not in st.session_state:
                    st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['end_date']] = max_date
        
        # 部門・病棟フィルターの初期化
        if '診療科名' in df.columns:
            available_depts = sorted(df['診療科名'].dropna().unique().astype(str))
            if UNIFIED_FILTER_CONFIG['session_keys']['departments'] not in st.session_state:
                st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['departments']] = available_depts
        
        if '病棟コード' in df.columns:
            available_wards = sorted(df['病棟コード'].dropna().unique().astype(str))
            if UNIFIED_FILTER_CONFIG['session_keys']['wards'] not in st.session_state:
                st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['wards']] = available_wards

def reset_filter_settings():
    """フィルター設定をリセット"""
    keys_to_reset = [
        UNIFIED_FILTER_CONFIG['session_keys']['departments'],
        UNIFIED_FILTER_CONFIG['session_keys']['wards'],
        UNIFIED_FILTER_CONFIG['session_keys']['start_date'],
        UNIFIED_FILTER_CONFIG['session_keys']['end_date']
    ]
    
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]
    
    st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['applied']] = False

def calculate_period_dates(max_date, period_mode):
    """期間モードに基づいて開始・終了日を計算"""
    end_date = max_date
    
    if period_mode == '全期間':
        # データの最小日付を使用（後で設定）
        start_date = max_date - timedelta(days=365*2)  # 仮の値
    elif period_mode == '最近30日':
        start_date = max_date - timedelta(days=30)
    elif period_mode == '最近90日':
        start_date = max_date - timedelta(days=90)
    elif period_mode == '最近180日':
        start_date = max_date - timedelta(days=180)
    elif period_mode == '最近1年':
        start_date = max_date - timedelta(days=365)
    else:  # カスタム期間
        start_date = max_date - timedelta(days=90)  # デフォルト
    
    return start_date, end_date

def create_unified_filter_sidebar(df):
    """統一フィルターのサイドバーUI作成"""
    
    if df is None or df.empty:
        st.sidebar.warning("⚠️ データが読み込まれていません")
        return
    
    # セッション状態の初期化
    initialize_filter_session_state(df)
    
    st.sidebar.markdown("## 🔍 統一分析フィルター")
    st.sidebar.markdown("*全タブで共通使用*")
    
    # データ情報表示
    with st.sidebar.expander("📊 データ情報", expanded=False):
        if '日付' in df.columns and not df['日付'].empty:
            min_date = pd.to_datetime(df['日付']).min().date()
            max_date = pd.to_datetime(df['日付']).max().date()
            st.write(f"**データ期間**: {min_date} ～ {max_date}")
        st.write(f"**総データ数**: {len(df):,}行")
        if '診療科名' in df.columns:
            dept_count = df['診療科名'].nunique()
            st.write(f"**診療科数**: {dept_count}")
        if '病棟コード' in df.columns:
            ward_count = df['病棟コード'].nunique()
            st.write(f"**病棟数**: {ward_count}")
    
    # 期間フィルター
    st.sidebar.markdown("### 📅 期間フィルター")
    
    current_period_mode = st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['period_mode']]
    period_mode = st.sidebar.selectbox(
        "期間選択",
        UNIFIED_FILTER_CONFIG['period_modes'],
        index=UNIFIED_FILTER_CONFIG['period_modes'].index(current_period_mode),
        key="period_mode_selector",
        help="分析対象期間を選択します"
    )
    
    # 期間モード変更時の処理
    if period_mode != current_period_mode:
        st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['period_mode']] = period_mode
        
        if '日付' in df.columns and not df['日付'].empty:
            max_date = pd.to_datetime(df['日付']).max().date()
            min_date = pd.to_datetime(df['日付']).min().date()
            
            if period_mode == '全期間':
                start_date, end_date = min_date, max_date
            elif period_mode != 'カスタム期間':
                start_date, end_date = calculate_period_dates(max_date, period_mode)
            else:
                # カスタム期間の場合は現在の設定を保持
                start_date = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['start_date'], min_date)
                end_date = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['end_date'], max_date)
            
            st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['start_date']] = start_date
            st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['end_date']] = end_date
        
        st.rerun()  # 画面を再描画
    
    # カスタム期間の場合の日付選択
    if period_mode == 'カスタム期間' and '日付' in df.columns:
        min_date = pd.to_datetime(df['日付']).min().date()
        max_date = pd.to_datetime(df['日付']).max().date()
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            start_date = st.date_input(
                "開始日",
                value=st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['start_date'], min_date),
                min_value=min_date,
                max_value=max_date,
                key="custom_start_date"
            )
        with col2:
            end_date = st.date_input(
                "終了日",
                value=st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['end_date'], max_date),
                min_value=min_date,
                max_value=max_date,
                key="custom_end_date"
            )
        
        # 日付の妥当性チェック
        if start_date > end_date:
            st.sidebar.error("❌ 開始日は終了日より前に設定してください")
            return
        
        st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['start_date']] = start_date
        st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['end_date']] = end_date
    
    # 診療科フィルター
    if '診療科名' in df.columns:
        st.sidebar.markdown("### 🏥 診療科フィルター")
        available_depts = sorted(df['診療科名'].dropna().unique().astype(str))
        
        # 全選択/全解除のボタン
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("全選択", key="select_all_depts", use_container_width=True):
                st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['departments']] = available_depts
                st.rerun()
        with col2:
            if st.button("全解除", key="deselect_all_depts", use_container_width=True):
                st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['departments']] = []
                st.rerun()
        
        current_depts = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['departments'], available_depts)
        selected_depts = st.sidebar.multiselect(
            "診療科選択",
            available_depts,
            default=current_depts,
            key="dept_multiselect",
            help="分析対象の診療科を選択します"
        )
        st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['departments']] = selected_depts
    
    # 病棟フィルター
    if '病棟コード' in df.columns:
        st.sidebar.markdown("### 🏢 病棟フィルター")
        available_wards = sorted(df['病棟コード'].dropna().unique().astype(str))
        
        # 全選択/全解除のボタン
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("全選択", key="select_all_wards", use_container_width=True):
                st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['wards']] = available_wards
                st.rerun()
        with col2:
            if st.button("全解除", key="deselect_all_wards", use_container_width=True):
                st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['wards']] = []
                st.rerun()
        
        current_wards = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['wards'], available_wards)
        selected_wards = st.sidebar.multiselect(
            "病棟選択",
            available_wards,
            default=current_wards,
            key="ward_multiselect",
            help="分析対象の病棟を選択します"
        )
        st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['wards']] = selected_wards
    
    # フィルター適用ボタン
    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 フィルター適用", type="primary", use_container_width=True):
        st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['applied']] = True
        st.rerun()
    
    # フィルタークリアボタン
    if st.sidebar.button("🗑️ フィルタークリア", use_container_width=True):
        reset_filter_settings()
        initialize_filter_session_state(df)
        st.rerun()

def apply_unified_filters(df):
    """統一フィルターをデータフレームに適用"""
    
    if df is None or df.empty:
        return df
    
    try:
        filtered_df = df.copy()
        
        # 期間フィルターの適用
        if '日付' in filtered_df.columns:
            start_date = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['start_date'])
            end_date = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['end_date'])
            
            if start_date and end_date:
                filtered_df['日付'] = pd.to_datetime(filtered_df['日付'])
                start_datetime = pd.to_datetime(start_date)
                end_datetime = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                
                filtered_df = filtered_df[
                    (filtered_df['日付'] >= start_datetime) & 
                    (filtered_df['日付'] <= end_datetime)
                ]
                
                logger.info(f"期間フィルター適用: {start_date} ～ {end_date}, 結果: {len(filtered_df)}行")
        
        # 診療科フィルターの適用
        if '診療科名' in filtered_df.columns:
            selected_depts = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['departments'], [])
            if selected_depts:
                filtered_df = filtered_df[filtered_df['診療科名'].astype(str).isin(selected_depts)]
                logger.info(f"診療科フィルター適用: {len(selected_depts)}科選択, 結果: {len(filtered_df)}行")
        
        # 病棟フィルターの適用
        if '病棟コード' in filtered_df.columns:
            selected_wards = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['wards'], [])
            if selected_wards:
                filtered_df = filtered_df[filtered_df['病棟コード'].astype(str).isin(selected_wards)]
                logger.info(f"病棟フィルター適用: {len(selected_wards)}病棟選択, 結果: {len(filtered_df)}行")
        
        return filtered_df
        
    except Exception as e:
        logger.error(f"統一フィルター適用エラー: {e}", exc_info=True)
        st.error(f"フィルター適用中にエラーが発生しました: {e}")
        return df

def create_unified_filter_status_card(df):
    """統一フィルターの状態表示カードとフィルター適用"""
    
    if df is None or df.empty:
        st.warning("⚠️ データが読み込まれていません")
        return df, {}
    
    # セッション状態の初期化
    initialize_filter_session_state(df)
    
    # フィルターの適用
    filtered_df = apply_unified_filters(df)
    
    # フィルター設定の取得
    period_mode = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['period_mode'], '全期間')
    start_date = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['start_date'])
    end_date = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['end_date'])
    selected_depts = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['departments'], [])
    selected_wards = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['wards'], [])
    
    # フィルター設定の構成
    filter_config = {
        'period_mode': period_mode,
        'start_date': start_date,
        'end_date': end_date,
        'departments': selected_depts,
        'wards': selected_wards,
        'original_count': len(df),
        'filtered_count': len(filtered_df)
    }
    
    # 状態表示カードの作成
    with st.container():
        st.markdown("### 🔍 適用中のフィルター")
        
        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
        
        with col1:
            # 期間情報
            if period_mode == 'カスタム期間' and start_date and end_date:
                period_text = f"📅 {start_date} ～ {end_date}"
            else:
                period_text = f"📅 {period_mode}"
            st.metric("期間", period_text)
        
        with col2:
            # データ件数
            filter_rate = (len(filtered_df) / len(df) * 100) if len(df) > 0 else 0
            st.metric(
                "データ件数", 
                f"{len(filtered_df):,}行",
                f"{filter_rate:.1f}% ({len(df):,}行中)"
            )
        
        with col3:
            # 診療科情報
            if '診療科名' in df.columns:
                total_depts = df['診療科名'].nunique()
                selected_dept_count = len(selected_depts)
                if selected_dept_count == total_depts:
                    dept_text = "全科"
                else:
                    dept_text = f"{selected_dept_count}/{total_depts}科"
                st.metric("診療科", dept_text)
        
        with col4:
            # 病棟情報
            if '病棟コード' in df.columns:
                total_wards = df['病棟コード'].nunique()
                selected_ward_count = len(selected_wards)
                if selected_ward_count == total_wards:
                    ward_text = "全病棟"
                else:
                    ward_text = f"{selected_ward_count}/{total_wards}病棟"
                st.metric("病棟", ward_text)
    
    # データ不足の警告
    if len(filtered_df) == 0:
        st.error("⚠️ フィルター条件に該当するデータがありません。条件を見直してください。")
    elif len(filtered_df) < 100:
        st.warning(f"⚠️ フィルター適用後のデータが少なくなっています（{len(filtered_df)}行）。分析結果の精度が低下する可能性があります。")
    
    # フィルター適用状態をセッション状態に記録
    st.session_state[UNIFIED_FILTER_CONFIG['session_keys']['applied']] = True
    
    return filtered_df, filter_config

def validate_unified_filters(df):
    """統一フィルターの妥当性チェック"""
    
    if df is None or df.empty:
        return False, "データが読み込まれていません"
    
    try:
        # 基本的な妥当性チェック
        start_date = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['start_date'])
        end_date = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['end_date'])
        
        if start_date and end_date and start_date > end_date:
            return False, "開始日が終了日より後に設定されています"
        
        # フィルター適用後のデータ件数チェック
        filtered_df = apply_unified_filters(df)
        if len(filtered_df) == 0:
            return False, "フィルター条件に該当するデータがありません"
        
        return True, "フィルター設定は有効です"
        
    except Exception as e:
        logger.error(f"フィルター妥当性チェックエラー: {e}", exc_info=True)
        return False, f"フィルター設定の検証中にエラーが発生しました: {e}"

def get_unified_filter_summary():
    """統一フィルターの設定概要を取得"""
    
    try:
        period_mode = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['period_mode'], '設定なし')
        selected_depts = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['departments'], [])
        selected_wards = st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['wards'], [])
        
        summary_parts = [f"期間: {period_mode}"]
        
        if selected_depts:
            summary_parts.append(f"診療科: {len(selected_depts)}科選択")
        
        if selected_wards:
            summary_parts.append(f"病棟: {len(selected_wards)}病棟選択")
        
        return " | ".join(summary_parts)
        
    except Exception as e:
        logger.error(f"フィルター概要取得エラー: {e}", exc_info=True)
        return "フィルター設定の取得に失敗"

def get_unified_filter_config():
    """統一フィルターの詳細設定を取得"""
    
    try:
        return {
            'period_mode': st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['period_mode']),
            'start_date': st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['start_date']),
            'end_date': st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['end_date']),
            'departments': st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['departments'], []),
            'wards': st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['wards'], []),
            'applied': st.session_state.get(UNIFIED_FILTER_CONFIG['session_keys']['applied'], False)
        }
    except Exception as e:
        logger.error(f"フィルター設定取得エラー: {e}", exc_info=True)
        return {}

# デバッグ用関数
def debug_filter_state():
    """デバッグ用：フィルター状態の表示"""
    
    st.sidebar.markdown("---")
    with st.sidebar.expander("🔧 デバッグ情報"):
        st.write("**セッション状態:**")
        for key, session_key in UNIFIED_FILTER_CONFIG['session_keys'].items():
            value = st.session_state.get(session_key, "未設定")
            st.write(f"{key}: {value}")
        
        if st.button("🗑️ 全フィルター状態クリア", key="debug_clear_all"):
            for session_key in UNIFIED_FILTER_CONFIG['session_keys'].values():
                if session_key in st.session_state:
                    del st.session_state[session_key]
            st.rerun()