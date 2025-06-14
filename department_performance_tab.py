# department_performance_tab.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 必要な外部モジュールをインポート
try:
    from utils import safe_date_filter
    from unified_filters import get_unified_filter_config
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.stop()

# スタイル関連の関数を直接定義（インポートエラーを回避）
def get_achievement_color_class(achievement_rate):
    """達成率に基づくCSSクラス名を返す"""
    if achievement_rate is None:
        return "achievement-good"
    elif achievement_rate >= 100:
        return "achievement-excellent"
    elif achievement_rate >= 95:
        return "achievement-good"
    elif achievement_rate >= 85:
        return "achievement-warning"
    else:
        return "achievement-danger"


def get_card_class(census_achievement, admissions_achievement):
    """KPI達成率に基づくカードCSSクラス名を返す"""
    census_rate = census_achievement or 0
    admissions_rate = admissions_achievement or 0
    
    if census_rate >= 100 and admissions_rate >= 100:
        return "dept-card-excellent"
    elif census_rate >= 95 or admissions_rate >= 95:
        return "dept-card-good"
    elif census_rate >= 85 or admissions_rate >= 85:
        return "dept-card-warning"
    else:
        return "dept-card-danger"


def inject_custom_css():
    """診療科別パフォーマンスダッシュボード用のカスタムCSS"""
    st.markdown("""
    <style>
    /* カードのコンテナスタイル */
    .dept-card-container {
        margin-bottom: 20px;
    }
    
    /* 達成率バッジのスタイル */
    .achievement-badge-excellent {
        background-color: #d4edda;
        color: #155724;
        padding: 6px 12px;
        border-radius: 15px;
        font-size: 0.85em;
        font-weight: 600;
        display: inline-block;
        border: 1px solid #c3e6cb;
    }
    
    .achievement-badge-good {
        background-color: #d1ecf1;
        color: #0c5460;
        padding: 6px 12px;
        border-radius: 15px;
        font-size: 0.85em;
        font-weight: 600;
        display: inline-block;
        border: 1px solid #bee5eb;
    }
    
    .achievement-badge-warning {
        background-color: #fff3cd;
        color: #856404;
        padding: 6px 12px;
        border-radius: 15px;
        font-size: 0.85em;
        font-weight: 600;
        display: inline-block;
        border: 1px solid #ffeaa7;
    }
    
    .achievement-badge-danger {
        background-color: #f8d7da;
        color: #721c24;
        padding: 6px 12px;
        border-radius: 15px;
        font-size: 0.85em;
        font-weight: 600;
        display: inline-block;
        border: 1px solid #f5c6cb;
    }
    
    /* メトリクスセクション */
    .metric-section {
        background: #ffffff;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        height: 100%;
    }
    
    /* 診療科名ヘッダー */
    .dept-header {
        text-align: center;
        padding: 15px;
        margin-bottom: 20px;
        border-bottom: 2px solid #e9ecef;
    }
    
    .dept-header h3 {
        margin: 0;
        font-size: 1.4em;
        font-weight: 700;
        color: #2c3e50;
    }
    </style>
    """, unsafe_allow_html=True)


def get_period_dates(df, period_type):
    """期間タイプに基づいて開始日・終了日・説明文を計算する"""
    if df is None or df.empty or '日付' not in df.columns:
        return None, None, "データなし"
    max_date = df['日付'].max()
    min_date = df['日付'].min()

    # 期間タイプに応じた計算
    if period_type == "直近4週":
        start_date = max_date - pd.Timedelta(days=27)
        period_desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "直近8週":
        start_date = max_date - pd.Timedelta(days=55)
        period_desc = f"直近8週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "直近12週":
        start_date = max_date - pd.Timedelta(days=83)
        period_desc = f"直近12週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "今年度":
        year = max_date.year if max_date.month >= 4 else max_date.year - 1
        start_date = pd.Timestamp(year=year, month=4, day=1)
        start_date = max(start_date, min_date)
        period_desc = f"今年度 ({start_date.strftime('%Y/%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "昨年度":
        year = max_date.year if max_date.month >= 4 else max_date.year - 1
        start_date = pd.Timestamp(year=year-1, month=4, day=1)
        end_date = pd.Timestamp(year=year, month=3, day=31)
        end_date = min(end_date, max_date)
        start_date = max(start_date, min_date)
        period_desc = f"昨年度 ({start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')})"
        return start_date, end_date, period_desc
    else:
        # デフォルトは直近4週
        start_date = max_date - pd.Timedelta(days=27)
        period_desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"

    start_date = max(start_date, min_date)
    return start_date, max_date, period_desc


def get_target_values_for_dept(target_data, dept_name):
    """目標値ファイルから診療科の目標値を取得"""
    targets = {
        'daily_census_target': None,
        'weekly_admissions_target': None,
        'avg_los_target': None
    }
    
    if target_data is None or target_data.empty:
        return targets
    
    try:
        dept_targets = target_data[target_data['部門名'] == dept_name]
        
        for _, row in dept_targets.iterrows():
            indicator_type = row.get('指標タイプ', '')
            target_value = row.get('目標値', None)
            
            if '日平均在院' in indicator_type or '在院患者数' in indicator_type:
                targets['daily_census_target'] = target_value
            elif '新入院' in indicator_type or '入院患者数' in indicator_type:
                # 月間目標を週間に変換（月間÷4.33）
                if target_value:
                    targets['weekly_admissions_target'] = target_value / 4.33
            elif '平均在院日数' in indicator_type:
                targets['avg_los_target'] = target_value
                
    except Exception as e:
        logger.error(f"目標値取得エラー ({dept_name}): {e}")
    
    return targets


def calculate_department_kpis(df, target_data, dept_name, start_date, end_date, dept_col):
    """各診療科のKPIを計算して辞書で返す"""
    try:
        # 部門列名を動的に使用
        dept_df = df[df[dept_col] == dept_name]
        period_df = safe_date_filter(dept_df, start_date, end_date)
        
        if period_df.empty:
            return None

        # 基本統計
        total_days = (end_date - start_date).days + 1
        total_patient_days = period_df['在院患者数'].sum() if '在院患者数' in period_df.columns else 0
        total_admissions = period_df['新入院患者数'].sum() if '新入院患者数' in period_df.columns else 0
        total_discharges = period_df['退院患者数'].sum() if '退院患者数' in period_df.columns else 0
        
        # 日平均在院患者数
        daily_avg_census = total_patient_days / total_days if total_days > 0 else 0
        
        # 直近週の計算（過去7日間）
        recent_week_end = end_date
        recent_week_start = end_date - pd.Timedelta(days=6)
        recent_week_df = safe_date_filter(dept_df, recent_week_start, recent_week_end)
        
        recent_week_patient_days = recent_week_df['在院患者数'].sum() if '在院患者数' in recent_week_df.columns and not recent_week_df.empty else 0
        recent_week_admissions = recent_week_df['新入院患者数'].sum() if '新入院患者数' in recent_week_df.columns and not recent_week_df.empty else 0
        recent_week_discharges = recent_week_df['退院患者数'].sum() if '退院患者数' in recent_week_df.columns and not recent_week_df.empty else 0
        
        recent_week_daily_census = recent_week_patient_days / 7 if recent_week_patient_days > 0 else 0
        
        # 平均在院日数（期間全体）
        avg_length_of_stay = total_patient_days / total_discharges if total_discharges > 0 else 0
        
        # 直近週の平均在院日数
        recent_week_avg_los = recent_week_patient_days / recent_week_discharges if recent_week_discharges > 0 else 0
        
        # 週合計新入院患者数（期間全体の週平均）
        weekly_avg_admissions = (total_admissions / total_days) * 7 if total_days > 0 else 0
        
        # 目標値取得
        targets = get_target_values_for_dept(target_data, dept_name)
        
        # 達成率計算
        daily_census_achievement = (daily_avg_census / targets['daily_census_target'] * 100) if targets['daily_census_target'] else 0
        weekly_admissions_achievement = (weekly_avg_admissions / targets['weekly_admissions_target'] * 100) if targets['weekly_admissions_target'] else 0
        
        return {
            'dept_name': dept_name,
            'total_days': total_days,
            'data_count': len(period_df),
            
            # 日平均在院患者数
            'daily_avg_census': daily_avg_census,
            'recent_week_daily_census': recent_week_daily_census,
            'daily_census_target': targets['daily_census_target'],
            'daily_census_achievement': daily_census_achievement,
            
            # 週合計新入院患者数
            'weekly_avg_admissions': weekly_avg_admissions,
            'recent_week_admissions': recent_week_admissions,
            'weekly_admissions_target': targets['weekly_admissions_target'],
            'weekly_admissions_achievement': weekly_admissions_achievement,
            
            # 平均在院日数
            'avg_length_of_stay': avg_length_of_stay,
            'recent_week_avg_los': recent_week_avg_los,
            'avg_los_target': targets['avg_los_target']
        }
        
    except Exception as e:
        logger.error(f"診療科KPI計算エラー ({dept_name}): {e}", exc_info=True)
        return None


def create_department_card_styled(kpi_data):
    """スタイリッシュなカード表示（JPG画像に近い）"""
    
    # カード全体の達成率で背景色を決定
    daily_achievement = kpi_data.get('daily_census_achievement', 0)
    weekly_achievement = kpi_data.get('weekly_admissions_achievement', 0)
    avg_achievement = (daily_achievement + weekly_achievement) / 2
    
    # カードの枠線色を決定
    if avg_achievement >= 100:
        border_color = "#28a745"  # 緑
        card_status = "excellent"
    elif avg_achievement >= 95:
        border_color = "#17a2b8"  # 青
        card_status = "good"
    elif avg_achievement >= 85:
        border_color = "#ffc107"  # 黄
        card_status = "warning"
    else:
        border_color = "#dc3545"  # 赤
        card_status = "danger"
    
    # カードコンテナ
    with st.container():
        # カスタムHTMLでカードのヘッダーとボーダーを作成
        st.markdown(
            f"""
            <div style="
                border-left: 5px solid {border_color};
                border-radius: 12px;
                padding: 20px;
                margin: 15px 0;
                box-shadow: 0 4px 16px rgba(0,0,0,0.08);
                background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
            ">
                <div class="dept-header">
                    <h3>{kpi_data['dept_name']}</h3>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # 3つの指標を横並びで表示
        col1, col2, col3 = st.columns(3)
        
        # 日平均在院患者数
        with col1:
            with st.container():
                st.markdown(
                    """<div class="metric-section">""",
                    unsafe_allow_html=True
                )
                st.markdown("**日平均在院患者数**")
                st.metric(
                    label="",
                    value=f"{kpi_data.get('daily_avg_census', 0):.1f}",
                    delta=None,
                    label_visibility="collapsed"
                )
                st.caption(f"直近週: {kpi_data.get('recent_week_daily_census', 0):.1f}人/日")
                st.caption(f"目標: {kpi_data.get('daily_census_target', 0):.1f}人" if kpi_data.get('daily_census_target') else "目標: 未設定")
                
                achievement = kpi_data.get('daily_census_achievement', 0)
                achievement_class = get_achievement_color_class(achievement)
                st.markdown(
                    f'<div class="achievement-badge-{achievement_class.split("-")[1]}">'
                    f'達成率: {achievement:.1f}%'
                    '</div>',
                    unsafe_allow_html=True
                )
                st.markdown("</div>", unsafe_allow_html=True)
        
        # 週合計新入院患者数
        with col2:
            with st.container():
                st.markdown(
                    """<div class="metric-section">""",
                    unsafe_allow_html=True
                )
                st.markdown("**週合計新入院患者数**")
                st.metric(
                    label="",
                    value=f"{kpi_data.get('weekly_avg_admissions', 0):.1f}",
                    delta=None,
                    label_visibility="collapsed"
                )
                st.caption(f"直近週: {kpi_data.get('recent_week_admissions', 0):.0f}人")
                st.caption(f"目標: {kpi_data.get('weekly_admissions_target', 0):.1f}人" if kpi_data.get('weekly_admissions_target') else "目標: 未設定")
                
                achievement = kpi_data.get('weekly_admissions_achievement', 0)
                achievement_class = get_achievement_color_class(achievement)
                st.markdown(
                    f'<div class="achievement-badge-{achievement_class.split("-")[1]}">'
                    f'達成率: {achievement:.1f}%'
                    '</div>',
                    unsafe_allow_html=True
                )
                st.markdown("</div>", unsafe_allow_html=True)
        
        # 平均在院日数
        with col3:
            with st.container():
                st.markdown(
                    """<div class="metric-section">""",
                    unsafe_allow_html=True
                )
                st.markdown("**平均在院日数**")
                st.metric(
                    label="",
                    value=f"{kpi_data.get('avg_length_of_stay', 0):.1f}",
                    delta=None,
                    label_visibility="collapsed"
                )
                st.caption(f"直近週: {kpi_data.get('recent_week_avg_los', 0):.1f}日")
                st.caption(f"目標: {kpi_data.get('avg_los_target', 0):.1f}日" if kpi_data.get('avg_los_target') else "目標: 未設定")
                
                # 平均在院日数は低い方が良いので、達成率の計算を逆にする
                if kpi_data.get('avg_los_target') and kpi_data.get('avg_length_of_stay', 0) > 0:
                    achievement = (kpi_data.get('avg_los_target', 0) / kpi_data.get('avg_length_of_stay', 1) * 100)
                else:
                    achievement = 0
                
                achievement_class = get_achievement_color_class(achievement)
                st.markdown(
                    f'<div class="achievement-badge-{achievement_class.split("-")[1]}">'
                    f'達成率: {achievement:.1f}%'
                    '</div>',
                    unsafe_allow_html=True
                )
                st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("---")


def display_department_performance_dashboard():
    """診療科別パフォーマンスダッシュボードのメイン表示関数"""
    st.header("🏥 診療科別パフォーマンスダッシュボード")
    
    # カスタムCSSを注入
    inject_custom_css()

    if not st.session_state.get('data_processed', False):
        st.warning("データを読み込み後に利用可能になります。")
        return

    df_original = st.session_state['df']
    target_data = st.session_state.get('target_data', {})

    # 統一設定から期間・ソート・列数を取得
    unified_config = get_unified_filter_config()
    period_key = unified_config.get('period') or unified_config.get('period_type') or '直近4週'
    sort_key = unified_config.get('sort', '診療科名（昇順）')

    # 開始日・終了日・説明文を取得
    start_date, end_date, period_desc = get_period_dates(df_original, period_key)
    date_filtered_df = safe_date_filter(df_original, start_date, end_date)

    # 部門名／診療科名の列を自動検出
    possible_cols = ['部門名', '診療科', '診療科名']
    dept_col = next((c for c in possible_cols if c in date_filtered_df.columns), None)
    if dept_col is None:
        st.error(f"診療科列が見つかりません。期待する列: {possible_cols}")
        return

    # 各診療科のKPI計算
    dept_kpis = []
    for dept in date_filtered_df[dept_col].unique():
        kpi = calculate_department_kpis(date_filtered_df, target_data, dept, start_date, end_date, dept_col)
        if kpi:
            dept_kpis.append(kpi)

    if not dept_kpis:
        st.warning("表示可能な診療科データがありません。")
        return

    # KPIリストのソート
    sort_map = {
        "週新入院患者数達成率（降順）": ('weekly_admissions_achievement', True),
        "日平均在院患者数達成率（降順）": ('daily_census_achievement', True),
        "日平均在院患者数（降順）": ('daily_avg_census', True),
        "診療科名（昇順）": ('dept_name', False)
    }
    key, rev = sort_map.get(sort_key, ('dept_name', False))
    dept_kpis.sort(key=lambda x: x.get(key) or 0, reverse=rev)

    # サマリー情報を表示
    total_depts = len(dept_kpis)
    avg_daily_census = sum(kpi.get('daily_avg_census', 0) for kpi in dept_kpis) / total_depts if total_depts > 0 else 0
    avg_weekly_admissions = sum(kpi.get('weekly_avg_admissions', 0) for kpi in dept_kpis) / total_depts if total_depts > 0 else 0
    
    # タイトルとサマリー表示
    st.markdown(f"**{period_desc}** の診療科別パフォーマンス")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("対象診療科数", f"{total_depts}科")
    with col2:
        st.metric("平均日在院患者数", f"{avg_daily_census:.1f}人")
    with col3:
        st.metric("平均週新入院患者数", f"{avg_weekly_admissions:.1f}人")
    
    st.markdown("---")
    
    # カード表示
    for kpi_data in dept_kpis:
        create_department_card_styled(kpi_data)


def create_department_performance_tab():
    """診療科別パフォーマンスタブのエントリーポイント"""
    display_department_performance_dashboard()