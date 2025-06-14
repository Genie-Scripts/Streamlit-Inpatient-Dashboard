# department_performance_tab.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import textwrap

logger = logging.getLogger(__name__)

# 必要な外部モジュールをインポート
try:
    from utils import safe_date_filter
    from unified_filters import get_unified_filter_config
    # スタイル定義とCSSクラスを生成するヘルパー関数をインポート
    from style import inject_department_performance_css, get_achievement_color_class, get_card_class
except ImportError as e:
    # 必要なモジュールがない場合はエラーを表示して停止
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.stop()


def get_period_dates(df, period_type):
    """期間タイプに基づいて開始日・終了日を計算する"""
    if df is None or df.empty or '日付' not in df.columns:
        return None, None, "データなし"
    
    max_date = df['日付'].max()
    min_date = df['日付'].min()
    
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
        current_year = max_date.year if max_date.month >= 4 else max_date.year - 1
        start_date = pd.Timestamp(year=current_year, month=4, day=1)
        start_date = max(start_date, min_date)
        period_desc = f"今年度 ({start_date.strftime('%Y/%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "昨年度":
        current_year = max_date.year if max_date.month >= 4 else max_date.year - 1
        start_date = pd.Timestamp(year=current_year-1, month=4, day=1)
        end_date = pd.Timestamp(year=current_year, month=3, day=31)
        end_date = min(end_date, max_date)
        start_date = max(start_date, min_date)
        period_desc = f"昨年度 ({start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')})"
        return start_date, end_date, period_desc
    else:
        start_date = max_date - pd.Timedelta(days=27)
        period_desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    
    start_date = max(start_date, min_date)
    return start_date, max_date, period_desc


def calculate_department_kpis(df, target_data, dept_name, start_date, end_date):
    # KPI 計算ロジック
    try:
        dept_df = df[df['部門名'] == dept_name]
        dept_df_period = safe_date_filter(dept_df, start_date, end_date)
        if dept_df_period.empty: return None
        
        total_days = (end_date - start_date).days + 1
        total_weeks = max(1, total_days / 7)
        
        avg_daily_census = dept_df_period['入院患者数（在院）'].mean()
        total_admissions = dept_df_period['総入院患者数'].sum()
        weekly_admissions = total_admissions / total_weeks
        
        total_patient_days = dept_df_period['入院患者数（在院）'].sum()
        total_discharges = dept_df_period['総退院患者数'].sum()
        alos = (total_patient_days / ((total_admissions + total_discharges) / 2)) if (total_admissions > 0 and total_discharges > 0) else 0
        
        latest_week_start = end_date - pd.Timedelta(days=6)
        latest_week_df = safe_date_filter(dept_df, latest_week_start, end_date)
        latest_week_census = latest_week_df['入院患者数（在院）'].mean() if not latest_week_df.empty else 0
        latest_week_admissions = latest_week_df['総入院患者数'].sum() if not latest_week_df.empty else 0
        week_patient_days = latest_week_df['入院患者数（在院）'].sum()
        week_admissions = latest_week_df['総入院患者数'].sum()
        week_discharges = latest_week_df['総退院患者数'].sum()
        latest_week_alos = (week_patient_days / ((week_admissions + week_discharges) / 2)) if (week_admissions > 0 and week_discharges > 0) else 0
        
        target_daily_census = None
        target_weekly_admissions = None
        if target_data is not None and not target_data.empty:
            dept_targets = target_data[target_data['部門名'].astype(str).str.strip() == dept_name]
            if not dept_targets.empty:
                if '日平均在院患者数目標' in dept_targets.columns:
                    target_daily_census = dept_targets['日平均在院患者数目標'].iloc[0]
                if '週間新入院患者数目標' in dept_targets.columns:
                    target_weekly_admissions = dept_targets['週間新入院患者数目標'].iloc[0]
        
        census_achievement = (avg_daily_census / target_daily_census * 100) if target_daily_census else None
        admissions_achievement = (weekly_admissions / target_weekly_admissions * 100) if target_weekly_admissions else None
        
        return {
            'dept_name': dept_name,
            'avg_daily_census': avg_daily_census,
            'weekly_admissions': weekly_admissions,
            'alos': alos,
            'latest_week_census': latest_week_census,
            'latest_week_admissions': latest_week_admissions,
            'latest_week_alos': latest_week_alos,
            'target_daily_census': target_daily_census,
            'target_weekly_admissions': target_weekly_admissions,
            'census_achievement': census_achievement,
            'admissions_achievement': admissions_achievement,
            'total_days': total_days,
            'data_count': len(dept_df_period)
        }
    except Exception as e:
        logger.error(f"診療科KPI計算エラー ({dept_name}): {e}", exc_info=True)
        return None


def create_department_card_html(kpi_data):
    """
    単一の診療科パフォーマンスカードのHTML文字列を生成する。
    この関数はHTMLを「返す」だけで、表示は行わない。
    """
    if not kpi_data:
        return ""

    # KPI達成率に基づくCSSクラス名を取得
    card_class = get_card_class(kpi_data.get('census_achievement'), kpi_data.get('admissions_achievement'))
    census_badge_class = get_achievement_color_class(kpi_data.get('census_achievement'))
    admissions_badge_class = get_achievement_color_class(kpi_data.get('admissions_achievement'))

    # 目標・達成率部分のHTMLを事前に生成
    census_target_html = ""
    if kpi_data.get('target_daily_census') and kpi_data.get('census_achievement') is not None:
        census_target_html = f"""
            <div class="metric-detail">目標 {kpi_data['target_daily_census']:.1f}人</div>
            <div class="achievement-badge {census_badge_class}">{kpi_data['census_achievement']:.1f}%</div>
        """

    admissions_target_html = ""
    if kpi_data.get('target_weekly_admissions') and kpi_data.get('admissions_achievement') is not None:
        admissions_target_html = f"""
            <div class="metric-detail">目標 {kpi_data['target_weekly_admissions']:.1f}人</div>
            <div class="achievement-badge {admissions_badge_class}">{kpi_data['admissions_achievement']:.1f}%</div>
        """

    # 最終的なHTMLを組み立てる
    html = f"""
        <div class="dept-performance-card {card_class}">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h3 style="margin: 0; color: #2c3e50; font-size: 1.2em; font-weight: 700;">{kpi_data['dept_name']}</h3>
                <div style="font-size: 0.7em; color: #868e96; text-align: right;">{kpi_data['total_days']}日間 | {kpi_data['data_count']}件</div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;">
                <div style="text-align: center;">
                    <div class="metric-label">日平均在院患者数</div>
                    <div class="metric-value">{kpi_data['avg_daily_census']:.1f}</div>
                    <div class="metric-detail">直近週 {kpi_data['latest_week_census']:.1f}人/日</div>
                    {census_target_html}
                </div>
                <div style="text-align: center;">
                    <div class="metric-label">週新入院患者数</div>
                    <div class="metric-value">{kpi_data['weekly_admissions']:.0f}</div>
                    <div class="metric-detail">直近週 {kpi_data['latest_week_admissions']:.0f}人/週</div>
                    {admissions_target_html}
                </div>
                <div style="text-align: center;">
                    <div class="metric-label">平均在院日数</div>
                    <div class="metric-value">{kpi_data['alos']:.1f}</div>
                    <div class="metric-detail">直近週 {kpi_data['latest_week_alos']:.1f}日</div>
                </div>
            </div>
        </div>
    """
    return textwrap.dedent(html)


def render_performance_cards(dept_kpis, columns_count):
    """
    生成されたHTMLをst.columnsとst.markdownを使って画面に表示（レンダリング）する。
    """
    for i in range(0, len(dept_kpis), columns_count):
        cols = st.columns(columns_count)
        for j in range(columns_count):
            if i + j < len(dept_kpis):
                with cols[j]:
                    kpi_data = dept_kpis[i + j]
                    # カードのHTMLを生成
                    card_html = create_department_card_html(kpi_data)
                    # unsafe_allow_html=True を使って正しくレンダリング
                    st.markdown(card_html, unsafe_allow_html=True)


def display_department_performance_dashboard():
    """診療科別パフォーマンスダッシュボードのメイン表示関数"""
    st.header("🏥 診療科別パフォーマンスダッシュボード")
    
    # このダッシュボード専用のCSSを適用
    inject_department_performance_css()
    
    if not st.session_state.get('data_processed', False):
        st.warning("データを読み込み後に利用可能になります。「データ入力」タブでデータをアップロードしてください。")
        return
    
    df_original = st.session_state.get('df')
    target_data = st.session_state.get('target_data')
    
    # フィルタリングされたデータフレームを取得
    unified_config = get_unified_filter_config()
    date_filtered_df = safe_date_filter(df_original, *get_period_dates(df_original, unified_config['period']))
    dept_names = date_filtered_df['部門名'].unique().tolist()
    
    # KPI を各診療科ごとに計算
    dept_kpis = []
    for dept in dept_names:
        kpi = calculate_department_kpis(date_filtered_df, target_data, dept, *get_period_dates(df_original, unified_config['period']))
        if kpi:
            dept_kpis.append(kpi)
    
    # 表示設定
    selected_sort = unified_config['sort']
    columns_count = unified_config['columns']
    
    # ソート
    sort_key_map = {
        "週新入院患者数達成率（降順）": ('admissions_achievement', True),
        "日平均在院患者数（降順）": ('avg_daily_census', True),
        "診療科名（昇順）": ('dept_name', False)
    }
    sort_key, reverse = sort_key_map.get(selected_sort, ('dept_name', False))
    dept_kpis.sort(key=lambda x: x.get(sort_key, 0) or -1, reverse=reverse)
    
    st.markdown("### 📋 診療科別詳細")
    render_performance_cards(dept_kpis, columns_count)


# --- app.pyから呼び出されるメイン関数 ---
def create_department_performance_tab():
    """このモジュールのエントリーポイント"""
    display_department_performance_dashboard()
