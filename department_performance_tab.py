# department_performance_tab.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import logging

logger = logging.getLogger(__name__)

# 既存モジュールからのインポート
try:
    from kpi_calculator import calculate_kpis
    from utils import get_display_name_for_dept, safe_date_filter
    from config import DEFAULT_TARGET_PATIENT_DAYS, DEFAULT_TOTAL_BEDS
    from unified_filters import get_unified_filter_config
except ImportError as e:
    logger.error(f"必要なモジュールのインポートに失敗: {e}")
    calculate_kpis = None
# 既存のインポートに追加
# ★★★ 修正点 ★★★: CSS注入関数をインポート
from style import inject_department_performance_css, get_achievement_color_class, get_card_class

def get_period_dates(df, period_type):
    """
    期間タイプに基づいて開始日・終了日を計算
    """
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

def calculate_department_kpis(df, dept_name, start_date, end_date, target_data=None):
    """
    診療科別のKPI計算
    """
    try:
        dept_df = df[df['診療科名'] == dept_name].copy()
        if dept_df.empty: return None
        
        dept_df_period = safe_date_filter(dept_df, start_date, end_date)
        if dept_df_period.empty: return None
        
        total_days = (end_date - start_date).days + 1
        total_weeks = max(1, total_days / 7)
        
        avg_daily_census = dept_df_period['入院患者数（在院）'].mean() if '入院患者数（在院）' in dept_df_period.columns else 0
        total_admissions = dept_df_period['総入院患者数'].sum() if '総入院患者数' in dept_df_period.columns else 0
        weekly_admissions = total_admissions / total_weeks
        
        total_patient_days = dept_df_period['入院患者数（在院）'].sum() if '入院患者数（在院）' in dept_df_period.columns else 0
        total_discharges = dept_df_period['総退院患者数'].sum() if '総退院患者数' in dept_df_period.columns else 0
        alos = total_patient_days / ((total_admissions + total_discharges) / 2) if total_admissions > 0 and total_discharges > 0 else 0
        
        latest_week_start = end_date - pd.Timedelta(days=6)
        latest_week_df = safe_date_filter(dept_df, latest_week_start, end_date)
        
        latest_week_census = latest_week_df['入院患者数（在院）'].mean() if not latest_week_df.empty and '入院患者数（在院）' in latest_week_df.columns else 0
        latest_week_admissions = latest_week_df['総入院患者数'].sum() if not latest_week_df.empty and '総入院患者数' in latest_week_df.columns else 0
        
        if not latest_week_df.empty:
            week_patient_days = latest_week_df['入院患者数（在院）'].sum()
            week_admissions = latest_week_df['総入院患者数'].sum()
            week_discharges = latest_week_df['総退院患者数'].sum()
            latest_week_alos = week_patient_days / ((week_admissions + week_discharges) / 2) if week_admissions > 0 and week_discharges > 0 else 0
        else:
            latest_week_alos = 0
            
        target_daily_census, target_weekly_admissions = None, None
        if target_data is not None and not target_data.empty:
            dept_targets = target_data[
                (target_data['部門名'].astype(str).str.strip() == dept_name) |
                (target_data['部門コード'].astype(str).str.strip() == dept_name)
            ]
            if not dept_targets.empty:
                if '日平均在院患者数目標' in dept_targets.columns:
                    target_daily_census = dept_targets['日平均在院患者数目標'].iloc[0]
                elif '目標値' in dept_targets.columns:
                    target_daily_census = dept_targets['目標値'].iloc[0]
                if '週間新入院患者数目標' in dept_targets.columns:
                    target_weekly_admissions = dept_targets['週間新入院患者数目標'].iloc[0]
        
        census_achievement = (avg_daily_census / target_daily_census * 100) if target_daily_census and target_daily_census > 0 else None
        admissions_achievement = (weekly_admissions / target_weekly_admissions * 100) if target_weekly_admissions and target_weekly_admissions > 0 else None
        
        return {
            'dept_name': dept_name, 'avg_daily_census': avg_daily_census,
            'weekly_admissions': weekly_admissions, 'alos': alos,
            'latest_week_census': latest_week_census, 'latest_week_admissions': latest_week_admissions,
            'latest_week_alos': latest_week_alos, 'target_daily_census': target_daily_census,
            'target_weekly_admissions': target_weekly_admissions, 'census_achievement': census_achievement,
            'admissions_achievement': admissions_achievement, 'total_days': total_days,
            'data_count': len(dept_df_period)
        }
    except Exception as e:
        logger.error(f"診療科KPI計算エラー ({dept_name}): {e}", exc_info=True)
        return None

def create_enhanced_department_card(kpi_data):
    """
    強化版診療科別パフォーマンスカードの作成（修正版：HTML生成ロジックを改善）
    """
    if not kpi_data:
        return ""

    # スタイル関数が利用できない場合のフォールバック
    if not (get_card_class and get_achievement_color_class):
        return create_basic_department_card(kpi_data)

    # KPI達成率に基づくCSSクラス名を取得
    census_achievement = kpi_data.get('census_achievement')
    admissions_achievement = kpi_data.get('admissions_achievement')
    card_class = get_card_class(census_achievement, admissions_achievement)
    census_badge_class = get_achievement_color_class(census_achievement)
    admissions_badge_class = get_achievement_color_class(admissions_achievement)

    # ---- ★★★ ここから修正 ★★★ ----
    # オプションで表示するHTMLパーツを事前に生成

    # 1. 日平均在院患者数の目標値・達成率部分のHTML
    census_target_html = ""
    if kpi_data.get('target_daily_census') and census_achievement is not None:
        census_target_html = f"""
            <div class="metric-detail">目標 {kpi_data['target_daily_census']:.1f}人</div>
            <div class="achievement-badge {census_badge_class}">{census_achievement:.1f}%</div>
        """

    # 2. 週合計新入院患者数の目標値・達成率部分のHTML
    admissions_target_html = ""
    if kpi_data.get('target_weekly_admissions') and admissions_achievement is not None:
        admissions_target_html = f"""
            <div class="metric-detail">目標 {kpi_data['target_weekly_admissions']:.1f}人</div>
            <div class="achievement-badge {admissions_badge_class}">{admissions_achievement:.1f}%</div>
        """

    # 事前に生成したパーツを使って、最終的なHTMLカードを組み立てる
    card_html = f"""
    <div class="dept-performance-card {card_class}">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
            <h3 style="margin: 0; color: #2c3e50; font-size: 1.3em; font-weight: 700;">{kpi_data['dept_name']}</h3>
            <div style="font-size: 0.7em; color: #868e96; text-align: right;">{kpi_data['total_days']}日間 | {kpi_data['data_count']}件</div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 15px;">
            <div style="text-align: center;">
                <div class="metric-label">日平均在院患者数</div>
                <div class="metric-value">{kpi_data['avg_daily_census']:.1f}</div>
                <div class="metric-detail">直近週 {kpi_data['latest_week_census']:.1f}人/日</div>
                {census_target_html}
            </div>

            <div style="text-align: center;">
                <div class="metric-label">週合計新入院患者数</div>
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
    # ---- ★★★ ここまで修正 ★★★ ----

    return card_html

def create_basic_department_card(kpi_data):
    """
    基本版診療科別パフォーマンスカード（フォールバック用）
    """
    if not kpi_data: return ""
    dept_name = kpi_data['dept_name']
    census_achievement = kpi_data.get('census_achievement', 0) or 0
    border_color = "#28a745" if census_achievement >= 100 else ("#ffc107" if census_achievement >= 90 else "#dc3545")
    bg_color = "#f8fff9" if census_achievement >= 100 else ("#fffdf0" if census_achievement >= 90 else "#fff5f5")
    
    return f"""
    <div style="background-color: {bg_color}; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 20px; margin: 10px; border-left: 5px solid {border_color};">
        <h3 style="margin: 0 0 15px 0; color: #2c3e50; font-size: 1.2em; font-weight: bold;">{dept_name}</h3>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 15px;">
            <div style="text-align: center;">
                <div style="font-weight: bold; color: #495057; font-size: 0.9em; margin-bottom: 5px;">日平均在院患者数</div>
                <div style="font-size: 1.8em; font-weight: bold; color: #2c3e50; margin-bottom: 5px;">{kpi_data['avg_daily_census']:.1f}</div>
                <div style="font-size: 0.8em; color: #6c757d;">直近週 {kpi_data['latest_week_census']:.1f}人/日</div>
            </div>
            <div style="text-align: center;">
                <div style="font-weight: bold; color: #495057; font-size: 0.9em; margin-bottom: 5px;">週合計新入院患者数</div>
                <div style="font-size: 1.8em; font-weight: bold; color: #2c3e50; margin-bottom: 5px;">{kpi_data['weekly_admissions']:.0f}</div>
                <div style="font-size: 0.8em; color: #6c757d;">直近週 {kpi_data['latest_week_admissions']:.0f}人/週</div>
            </div>
            <div style="text-align: center;">
                <div style="font-weight: bold; color: #495057; font-size: 0.9em; margin-bottom: 5px;">平均在院日数</div>
                <div style="font-size: 1.8em; font-weight: bold; color: #2c3e50; margin-bottom: 5px;">{kpi_data['alos']:.1f}</div>
                <div style="font-size: 0.8em; color: #6c757d;">直近週 {kpi_data['latest_week_alos']:.1f}日</div>
            </div>
        </div>
    </div>
    """

def display_department_performance_dashboard():
    """
    診療科別パフォーマンスダッシュボードのメイン表示関数
    """
    # ★★★ 修正点 ★★★: カード表示に必要なCSSをここで注入
    inject_department_performance_css()

    st.header("🏥 診療科別パフォーマンスダッシュボード")
    
    if not st.session_state.get('data_processed', False):
        st.warning("データを読み込み後に利用可能になります。「データ入力」タブでデータをアップロードしてください。")
        return
    
    df_original, target_data = st.session_state.get('df'), st.session_state.get('target_data')
    
    if df_original is None or df_original.empty:
        st.error("分析対象のデータがありません。")
        return
    if '診療科名' not in df_original.columns:
        st.error("診療科名列が見つかりません。")
        return
    
    filter_config = get_unified_filter_config() if get_unified_filter_config else {}
    df_filtered = df_original.copy()
    
    if filter_config:
        filter_mode = filter_config.get('filter_mode', '全体')
        if filter_mode == "特定診療科" and filter_config.get('selected_depts'):
            df_filtered = df_filtered[df_filtered['診療科名'].isin(filter_config['selected_depts'])]
        elif filter_mode == "特定病棟" and filter_config.get('selected_wards') and '病棟コード' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['病棟コード'].isin(filter_config['selected_wards'])]
    
    with st.expander("⚙️ 表示設定", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            selected_period = st.selectbox("📅 分析期間", ["直近4週", "直近8週", "直近12週", "今年度", "昨年度"], 0, key="dept_p_period")
        with col2:
            sort_options = ["診療科名（昇順）", "日平均在院患者数達成率（降順）", "日平均在院患者数達成率（昇順）", "週新入院患者数達成率（降順）", "週新入院患者数達成率（昇順）", "日平均在院患者数（降順）", "平均在院日数（昇順）"]
            selected_sort = st.selectbox("📊 並び順", sort_options, 1, key="dept_p_sort")
        with col3:
            columns_count = st.slider("🗂️ 表示列数", 1, 4, 3, key="dept_p_cols")
    
    start_date, end_date, period_desc = get_period_dates(df_filtered, selected_period)
    if start_date is None or end_date is None:
        st.error("期間の計算に失敗しました。")
        return
    st.info(f"📊 {period_desc}")
    
    departments = sorted(df_filtered['診療科名'].unique())
    progress_bar = st.progress(0)
    status_text = st.empty()
    dept_kpis = []
    for i, dept in enumerate(departments):
        status_text.text(f"計算中: {dept} ({i+1}/{len(departments)})")
        kpi_data = calculate_department_kpis(df_filtered, dept, start_date, end_date, target_data)
        if kpi_data: dept_kpis.append(kpi_data)
        progress_bar.progress((i + 1) / len(departments))
    progress_bar.empty()
    status_text.empty()
    
    if not dept_kpis:
        st.warning("表示する診療科データがありません。")
        return
        
    sort_key_map = {
        "日平均在院患者数達成率（降順）": ('census_achievement', True), "日平均在院患者数達成率（昇順）": ('census_achievement', False),
        "週新入院患者数達成率（降順）": ('admissions_achievement', True), "週新入院患者数達成率（昇順）": ('admissions_achievement', False),
        "日平均在院患者数（降順）": ('avg_daily_census', True), "平均在院日数（昇順）": ('alos', False),
        "診療科名（昇順）": ('dept_name', False)
    }
    sort_key, reverse = sort_key_map.get(selected_sort, ('dept_name', False))
    dept_kpis.sort(key=lambda x: x.get(sort_key, 0) or 0, reverse=reverse)
    
    with st.expander("📊 全体サマリー", expanded=False):
        census_achievements = [k.get('census_achievement') for k in dept_kpis if k.get('census_achievement') is not None]
        admissions_achievements = [k.get('admissions_achievement') for k in dept_kpis if k.get('admissions_achievement') is not None]
        col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
        col_sum1.metric("対象診療科数", f"{len(dept_kpis)}科")
        if census_achievements:
            col_sum2.metric("日平均在院患者数", f"{np.mean(census_achievements):.1f}%", f"{sum(1 for x in census_achievements if x >= 100)}/{len(census_achievements)}科達成")
        if admissions_achievements:
            col_sum3.metric("週新入院患者数", f"{np.mean(admissions_achievements):.1f}%", f"{sum(1 for x in admissions_achievements if x >= 100)}/{len(admissions_achievements)}科達成")
        col_sum4.metric("平均在院日数", f"{np.mean([k.get('alos', 0) for k in dept_kpis]):.1f}日")
        
    st.markdown("### 📋 診療科別詳細")
    # ★★★ 修正点 ★★★: 修正されたレンダリング関数を呼び出す
    render_performance_cards(dept_kpis, columns_count)
    
    st.markdown("---")
    if st.button("📊 データをCSVエクスポート", key="export_dept_perf"):
        export_df = pd.DataFrame(dept_kpis)
        st.download_button(label="📥 CSVダウンロード", data=export_df.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f"診療科別パフォーマンス_{selected_period}.csv", mime="text/csv")

# ★★★ 修正点 ★★★: 関数名を変更し、ロジックを修正
def render_performance_cards(dept_kpis, columns_count):
    """
    診療科別パフォーマンスカード表示（修正版）
    create_enhanced_department_card を使用してカードを生成・表示します。
    """
    for i in range(0, len(dept_kpis), columns_count):
        cols = st.columns(columns_count)
        for j in range(columns_count):
            if i + j < len(dept_kpis):
                with cols[j]:
                    kpi_data = dept_kpis[i + j]
                    # HTMLを生成し、unsafe_allow_html=Trueで正しくレンダリング
                    card_html = create_enhanced_department_card(kpi_data)
                    if card_html:
                        st.markdown(card_html, unsafe_allow_html=True)

# ★★★ 修正点 ★★★: 問題のあった古い関数を削除
# create_dashboard_style_card 関数は削除されました。

def create_department_performance_tab():
    """診療科別パフォーマンスダッシュボードタブの作成"""
    display_department_performance_dashboard()