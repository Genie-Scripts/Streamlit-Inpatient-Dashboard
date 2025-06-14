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
from style import inject_department_performance_css, get_achievement_color_class, get_card_class

def get_period_dates(df, period_type):
    """
    期間タイプに基づいて開始日・終了日を計算
    
    Args:
        df: データフレーム
        period_type: '直近4週', '直近8週', '直近12週', '今年度', '昨年度'
    
    Returns:
        tuple: (start_date, end_date, period_description)
    """
    if df is None or df.empty or '日付' not in df.columns:
        return None, None, "データなし"
    
    max_date = df['日付'].max()
    min_date = df['日付'].min()
    
    if period_type == "直近4週":
        start_date = max_date - pd.Timedelta(days=27)  # 4週間 = 28日
        period_desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "直近8週":
        start_date = max_date - pd.Timedelta(days=55)  # 8週間 = 56日
        period_desc = f"直近8週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "直近12週":
        start_date = max_date - pd.Timedelta(days=83)  # 12週間 = 84日
        period_desc = f"直近12週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "今年度":
        # 年度は4月1日開始
        current_year = max_date.year if max_date.month >= 4 else max_date.year - 1
        start_date = pd.Timestamp(year=current_year, month=4, day=1)
        start_date = max(start_date, min_date)  # データ範囲内に調整
        period_desc = f"今年度 ({start_date.strftime('%Y/%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "昨年度":
        current_year = max_date.year if max_date.month >= 4 else max_date.year - 1
        start_date = pd.Timestamp(year=current_year-1, month=4, day=1)
        end_date = pd.Timestamp(year=current_year, month=3, day=31)
        end_date = min(end_date, max_date)  # データ範囲内に調整
        start_date = max(start_date, min_date)  # データ範囲内に調整
        period_desc = f"昨年度 ({start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')})"
        return start_date, end_date, period_desc
    else:
        start_date = max_date - pd.Timedelta(days=27)  # デフォルトは4週間
        period_desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    
    start_date = max(start_date, min_date)  # データ範囲内に調整
    return start_date, max_date, period_desc

def calculate_department_kpis(df, dept_name, start_date, end_date, target_data=None):
    """
    診療科別のKPI計算
    
    Args:
        df: 全体データフレーム
        dept_name: 診療科名
        start_date: 開始日
        end_date: 終了日
        target_data: 目標値データフレーム
    
    Returns:
        dict: 診療科のKPI情報
    """
    try:
        # 診療科でフィルタ
        dept_df = df[df['診療科名'] == dept_name].copy()
        
        if dept_df.empty:
            return None
        
        # 期間でフィルタ
        dept_df_period = safe_date_filter(dept_df, start_date, end_date)
        
        if dept_df_period.empty:
            return None
        
        # 基本KPI計算
        total_days = (end_date - start_date).days + 1
        total_weeks = max(1, total_days / 7)  # 週数
        
        # 日平均在院患者数
        avg_daily_census = dept_df_period['入院患者数（在院）'].mean() if '入院患者数（在院）' in dept_df_period.columns else 0
        
        # 週合計新入院患者数（期間全体の新入院患者数を週平均に変換）
        total_admissions = dept_df_period['総入院患者数'].sum() if '総入院患者数' in dept_df_period.columns else 0
        weekly_admissions = total_admissions / total_weeks
        
        # 平均在院日数（ALOS）
        total_patient_days = dept_df_period['入院患者数（在院）'].sum() if '入院患者数（在院）' in dept_df_period.columns else 0
        total_discharges = dept_df_period['総退院患者数'].sum() if '総退院患者数' in dept_df_period.columns else 0
        
        if total_admissions > 0 and total_discharges > 0:
            alos = total_patient_days / ((total_admissions + total_discharges) / 2)
        else:
            alos = 0
        
        # 直近週のデータ（最新7日間）
        latest_week_start = end_date - pd.Timedelta(days=6)
        latest_week_df = safe_date_filter(dept_df, latest_week_start, end_date)
        
        latest_week_census = latest_week_df['入院患者数（在院）'].mean() if not latest_week_df.empty and '入院患者数（在院）' in latest_week_df.columns else 0
        latest_week_admissions = latest_week_df['総入院患者数'].sum() if not latest_week_df.empty and '総入院患者数' in latest_week_df.columns else 0
        
        # 直近週のALOS
        if not latest_week_df.empty:
            week_patient_days = latest_week_df['入院患者数（在院）'].sum()
            week_admissions = latest_week_df['総入院患者数'].sum()
            week_discharges = latest_week_df['総退院患者数'].sum()
            if week_admissions > 0 and week_discharges > 0:
                latest_week_alos = week_patient_days / ((week_admissions + week_discharges) / 2)
            else:
                latest_week_alos = 0
        else:
            latest_week_alos = 0
        
        # 目標値の取得
        target_daily_census = None
        target_weekly_admissions = None
        
        if target_data is not None and not target_data.empty:
            # 目標値データから該当診療科の目標を検索
            dept_targets = target_data[
                (target_data['部門名'].astype(str).str.strip() == dept_name) |
                (target_data['部門コード'].astype(str).str.strip() == dept_name)
            ]
            
            if not dept_targets.empty:
                # 日平均在院患者数目標
                if '日平均在院患者数目標' in dept_targets.columns:
                    target_daily_census = dept_targets['日平均在院患者数目標'].iloc[0]
                elif '目標値' in dept_targets.columns:
                    target_daily_census = dept_targets['目標値'].iloc[0]
                
                # 週間新入院患者数目標
                if '週間新入院患者数目標' in dept_targets.columns:
                    target_weekly_admissions = dept_targets['週間新入院患者数目標'].iloc[0]
        
        # 達成率計算
        census_achievement = (avg_daily_census / target_daily_census * 100) if target_daily_census and target_daily_census > 0 else None
        admissions_achievement = (weekly_admissions / target_weekly_admissions * 100) if target_weekly_admissions and target_weekly_admissions > 0 else None
        
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

def get_achievement_color(achievement_rate):
    """
    達成率に基づく色を取得
    
    Args:
        achievement_rate: 達成率（％）
    
    Returns:
        str: カラーコード
    """
    if achievement_rate is None:
        return "#f0f0f0"  # グレー（目標なし）
    elif achievement_rate >= 100:
        return "#d4edda"  # 緑（達成）
    elif achievement_rate >= 90:
        return "#fff3cd"  # 黄（注意）
    else:
        return "#f8d7da"  # 赤（未達成）

def get_achievement_text_color(achievement_rate):
    """
    達成率に基づくテキスト色を取得
    """
    if achievement_rate is None:
        return "#6c757d"
    elif achievement_rate >= 100:
        return "#155724"  # 濃い緑
    elif achievement_rate >= 90:
        return "#856404"  # 濃い黄
    else:
        return "#721c24"  # 濃い赤

def create_enhanced_department_card(kpi_data):
    """
    強化版診療科別パフォーマンスカードの作成
    既存の create_department_card 関数を置き換える
    
    Args:
        kpi_data: 診療科のKPI情報
    
    Returns:
        HTML string: カードのHTMLコード
    """
    if not kpi_data:
        return ""
    
    dept_name = kpi_data['dept_name']
    
    # CSS関数が利用可能な場合のみ強化版を使用
    if get_card_class and get_achievement_color_class:
        # 総合達成率によるカードクラス決定
        census_achievement = kpi_data.get('census_achievement')
        admissions_achievement = kpi_data.get('admissions_achievement')
        
        card_class = get_card_class(census_achievement, admissions_achievement)
        census_badge_class = get_achievement_color_class(census_achievement)
        admissions_badge_class = get_achievement_color_class(admissions_achievement)
        
        # 強化版カードHTML
        card_html = f"""
        <div class="dept-performance-card {card_class}">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h3 style="margin: 0; color: #2c3e50; font-size: 1.3em; font-weight: 700;">
                    {dept_name}
                </h3>
                <div style="font-size: 0.7em; color: #868e96; text-align: right;">
                    {kpi_data['total_days']}日間 | {kpi_data['data_count']}件
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 15px;">
                <!-- 日平均在院患者数 -->
                <div style="text-align: center;">
                    <div class="metric-label">日平均在院患者数</div>
                    <div class="metric-value">{kpi_data['avg_daily_census']:.1f}</div>
                    <div class="metric-detail">直近週 {kpi_data['latest_week_census']:.1f}人/日</div>
                    {f'''
                    <div class="metric-detail">目標 {kpi_data['target_daily_census']:.1f}人</div>
                    <div class="achievement-badge {census_badge_class}">
                        {kpi_data['census_achievement']:.1f}%
                    </div>
                    ''' if kpi_data.get('target_daily_census') and kpi_data.get('census_achievement') is not None else ''}
                </div>
                
                <!-- 週合計新入院患者数 -->
                <div style="text-align: center;">
                    <div class="metric-label">週合計新入院患者数</div>
                    <div class="metric-value">{kpi_data['weekly_admissions']:.0f}</div>
                    <div class="metric-detail">直近週 {kpi_data['latest_week_admissions']:.0f}人/週</div>
                    {f'''
                    <div class="metric-detail">目標 {kpi_data['target_weekly_admissions']:.1f}人</div>
                    <div class="achievement-badge {admissions_badge_class}">
                        {kpi_data['admissions_achievement']:.1f}%
                    </div>
                    ''' if kpi_data.get('target_weekly_admissions') and kpi_data.get('admissions_achievement') is not None else ''}
                </div>
                
                <!-- 平均在院日数 -->
                <div style="text-align: center;">
                    <div class="metric-label">平均在院日数</div>
                    <div class="metric-value">{kpi_data['alos']:.1f}</div>
                    <div class="metric-detail">直近週 {kpi_data['latest_week_alos']:.1f}日</div>
                </div>
            </div>
        </div>
        """
    else:
        # フォールバック: 基本版カードHTML（既存版）
        card_html = create_basic_department_card(kpi_data)
    
    return card_html
    
def create_basic_department_card(kpi_data):
    """
    基本版診療科別パフォーマンスカード（スタイル関数が利用できない場合のフォールバック）
    """
    if not kpi_data:
        return ""
    
    dept_name = kpi_data['dept_name']
    
    # 基本的な色分け
    census_achievement = kpi_data.get('census_achievement', 0) or 0
    if census_achievement >= 100:
        border_color = "#28a745"
        bg_color = "#f8fff9"
    elif census_achievement >= 90:
        border_color = "#ffc107"
        bg_color = "#fffdf0"
    else:
        border_color = "#dc3545"
        bg_color = "#fff5f5"
    
    # 基本版カードHTML
    card_html = f"""
    <div style="
        background-color: {bg_color};
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        padding: 20px;
        margin: 10px;
        border-left: 5px solid {border_color};
    ">
        <h3 style="margin: 0 0 15px 0; color: #2c3e50; font-size: 1.2em; font-weight: bold;">
            {dept_name}
        </h3>
        
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 15px;">
            <!-- 日平均在院患者数 -->
            <div style="text-align: center;">
                <div style="font-weight: bold; color: #495057; font-size: 0.9em; margin-bottom: 5px;">
                    日平均在院患者数
                </div>
                <div style="font-size: 1.8em; font-weight: bold; color: #2c3e50; margin-bottom: 5px;">
                    {kpi_data['avg_daily_census']:.1f}
                </div>
                <div style="font-size: 0.8em; color: #6c757d;">
                    直近週 {kpi_data['latest_week_census']:.1f}人/日
                </div>
                {f'''
                <div style="font-size: 0.8em; color: #6c757d;">
                    目標 {kpi_data['target_daily_census']:.1f}人
                </div>
                <div style="
                    font-size: 0.9em; 
                    font-weight: bold; 
                    color: #155724;
                    background-color: #d4edda;
                    padding: 2px 8px;
                    border-radius: 12px;
                    margin-top: 5px;
                    display: inline-block;
                ">
                    達成率 {kpi_data['census_achievement']:.1f}%
                </div>
                ''' if kpi_data.get('target_daily_census') and kpi_data.get('census_achievement') is not None else ''}
            </div>
            
            <!-- 週合計新入院患者数 -->
            <div style="text-align: center;">
                <div style="font-weight: bold; color: #495057; font-size: 0.9em; margin-bottom: 5px;">
                    週合計新入院患者数
                </div>
                <div style="font-size: 1.8em; font-weight: bold; color: #2c3e50; margin-bottom: 5px;">
                    {kpi_data['weekly_admissions']:.0f}
                </div>
                <div style="font-size: 0.8em; color: #6c757d;">
                    直近週 {kpi_data['latest_week_admissions']:.0f}人/週
                </div>
                {f'''
                <div style="font-size: 0.8em; color: #6c757d;">
                    目標 {kpi_data['target_weekly_admissions']:.1f}人
                </div>
                <div style="
                    font-size: 0.9em; 
                    font-weight: bold; 
                    color: #155724;
                    background-color: #d4edda;
                    padding: 2px 8px;
                    border-radius: 12px;
                    margin-top: 5px;
                    display: inline-block;
                ">
                    達成率 {kpi_data['admissions_achievement']:.1f}%
                </div>
                ''' if kpi_data.get('target_weekly_admissions') and kpi_data.get('admissions_achievement') is not None else ''}
            </div>
            
            <!-- 平均在院日数 -->
            <div style="text-align: center;">
                <div style="font-weight: bold; color: #495057; font-size: 0.9em; margin-bottom: 5px;">
                    平均在院日数
                </div>
                <div style="font-size: 1.8em; font-weight: bold; color: #2c3e50; margin-bottom: 5px;">
                    {kpi_data['alos']:.1f}
                </div>
                <div style="font-size: 0.8em; color: #6c757d;">
                    直近週 {kpi_data['latest_week_alos']:.1f}日
                </div>
            </div>
        </div>
        
        <div style="font-size: 0.7em; color: #868e96; text-align: right;">
            分析期間: {kpi_data['total_days']}日間 | データ件数: {kpi_data['data_count']}件
        </div>
    </div>
    """
    
    return card_html
    
def display_department_performance_dashboard():
    """
    診療科別パフォーマンスダッシュボードのメイン表示関数
    dashboard_page.py のスタイルを応用したコンパクト表示
    """
    st.header("🏥 診療科別パフォーマンスダッシュボード")
    
    # データの確認
    if not st.session_state.get('data_processed', False):
        st.warning("データを読み込み後に利用可能になります。「データ入力」タブでデータをアップロードしてください。")
        return
    
    df_original = st.session_state.get('df')
    target_data = st.session_state.get('target_data')
    
    if df_original is None or df_original.empty:
        st.error("分析対象のデータがありません。")
        return
    
    if '診療科名' not in df_original.columns:
        st.error("診療科名列が見つかりません。")
        return
    
    # 統一フィルターからの期間情報取得
    filter_config = get_unified_filter_config() if get_unified_filter_config else {}
    df_filtered = df_original.copy()
    
    # 統一フィルターの部門フィルターが適用されている場合は、それに従う
    if filter_config:
        filter_mode = filter_config.get('filter_mode', '全体')
        if filter_mode == "特定診療科" and filter_config.get('selected_depts'):
            df_filtered = df_filtered[df_filtered['診療科名'].isin(filter_config['selected_depts'])]
            st.info(f"🔍 統一フィルター適用中: {len(filter_config['selected_depts'])}診療科を表示")
        elif filter_mode == "特定病棟" and filter_config.get('selected_wards'):
            if '病棟コード' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['病棟コード'].isin(filter_config['selected_wards'])]
                st.info(f"🔍 統一フィルター適用中: {len(filter_config['selected_wards'])}病棟の診療科を表示")
    
    # 設定パネル
    with st.expander("⚙️ 表示設定", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 期間選択
            period_options = ["直近4週", "直近8週", "直近12週", "今年度", "昨年度"]
            selected_period = st.selectbox(
                "📅 分析期間",
                period_options,
                index=0,
                key="dept_performance_period"
            )
        
        with col2:
            # ソート方法
            sort_options = [
                "診療科名（昇順）",
                "日平均在院患者数達成率（降順）",
                "日平均在院患者数達成率（昇順）", 
                "週新入院患者数達成率（降順）",
                "週新入院患者数達成率（昇順）",
                "日平均在院患者数（降順）",
                "平均在院日数（昇順）"
            ]
            selected_sort = st.selectbox(
                "📊 並び順",
                sort_options,
                index=1,
                key="dept_performance_sort"
            )
        
        with col3:
            # カード表示列数
            columns_count = st.slider(
                "🗂️ 表示列数",
                min_value=1,
                max_value=4,
                value=3,
                key="dept_performance_columns"
            )
    
    # 期間の計算
    start_date, end_date, period_desc = get_period_dates(df_filtered, selected_period)
    
    if start_date is None or end_date is None:
        st.error("期間の計算に失敗しました。")
        return
    
    st.info(f"📊 {period_desc}")
    
    # 診療科一覧の取得
    departments = sorted(df_filtered['診療科名'].unique())
    
    # 各診療科のKPI計算
    dept_kpis = []
    
    # プログレスバー
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, dept in enumerate(departments):
        status_text.text(f"計算中: {dept} ({i+1}/{len(departments)})")
        progress_bar.progress((i + 1) / len(departments))
        
        kpi_data = calculate_department_kpis(df_filtered, dept, start_date, end_date, target_data)
        if kpi_data:
            dept_kpis.append(kpi_data)
    
    progress_bar.empty()
    status_text.empty()
    
    if not dept_kpis:
        st.warning("表示する診療科データがありません。")
        return
    
    # ソート処理
    if "日平均在院患者数達成率（降順）" in selected_sort:
        dept_kpis.sort(key=lambda x: x.get('census_achievement', 0) or 0, reverse=True)
    elif "日平均在院患者数達成率（昇順）" in selected_sort:
        dept_kpis.sort(key=lambda x: x.get('census_achievement', 0) or 0, reverse=False)
    elif "週新入院患者数達成率（降順）" in selected_sort:
        dept_kpis.sort(key=lambda x: x.get('admissions_achievement', 0) or 0, reverse=True)
    elif "週新入院患者数達成率（昇順）" in selected_sort:
        dept_kpis.sort(key=lambda x: x.get('admissions_achievement', 0) or 0, reverse=False)
    elif "日平均在院患者数（降順）" in selected_sort:
        dept_kpis.sort(key=lambda x: x.get('avg_daily_census', 0), reverse=True)
    elif "平均在院日数（昇順）" in selected_sort:
        dept_kpis.sort(key=lambda x: x.get('alos', 0), reverse=False)
    else:  # 診療科名（昇順）
        dept_kpis.sort(key=lambda x: x.get('dept_name', ''))
    
    # サマリー情報
    with st.expander("📊 全体サマリー", expanded=False):
        total_depts = len(dept_kpis)
        
        # 達成率の集計
        census_achievements = [kpi.get('census_achievement') for kpi in dept_kpis if kpi.get('census_achievement') is not None]
        admissions_achievements = [kpi.get('admissions_achievement') for kpi in dept_kpis if kpi.get('admissions_achievement') is not None]
        
        col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
        
        with col_sum1:
            st.metric("対象診療科数", f"{total_depts}科")
        
        with col_sum2:
            if census_achievements:
                avg_census_achievement = np.mean(census_achievements)
                achieved_census = sum(1 for x in census_achievements if x >= 100)
                st.metric(
                    "日平均在院患者数", 
                    f"{avg_census_achievement:.1f}%",
                    f"{achieved_census}/{len(census_achievements)}科達成"
                )
            else:
                st.metric("日平均在院患者数", "目標なし")
        
        with col_sum3:
            if admissions_achievements:
                avg_admissions_achievement = np.mean(admissions_achievements)
                achieved_admissions = sum(1 for x in admissions_achievements if x >= 100)
                st.metric(
                    "週新入院患者数", 
                    f"{avg_admissions_achievement:.1f}%",
                    f"{achieved_admissions}/{len(admissions_achievements)}科達成"
                )
            else:
                st.metric("週新入院患者数", "目標なし")
        
        with col_sum4:
            avg_alos = np.mean([kpi.get('alos', 0) for kpi in dept_kpis])
            st.metric("平均在院日数", f"{avg_alos:.1f}日")
    
    # ========== ダッシュボードスタイルのカード表示（メイン）==========
    st.markdown("### 📋 診療科別詳細")
    
    # dashboard_page.py のスタイルを応用したカード表示
    render_dashboard_style_performance_cards(dept_kpis, columns_count)
    
    # エクスポート機能
    st.markdown("---")
    if st.button("📊 データをCSVエクスポート", key="export_dept_performance"):
        # データフレーム作成
        export_data = []
        for kpi in dept_kpis:
            export_data.append({
                '診療科名': kpi['dept_name'],
                '日平均在院患者数': kpi['avg_daily_census'],
                '直近週_日平均在院患者数': kpi['latest_week_census'],
                '目標_日平均在院患者数': kpi.get('target_daily_census', ''),
                '達成率_日平均在院患者数': kpi.get('census_achievement', ''),
                '週合計新入院患者数': kpi['weekly_admissions'],
                '直近週_新入院患者数': kpi['latest_week_admissions'],
                '目標_週新入院患者数': kpi.get('target_weekly_admissions', ''),
                '達成率_週新入院患者数': kpi.get('admissions_achievement', ''),
                '平均在院日数': kpi['alos'],
                '直近週_平均在院日数': kpi['latest_week_alos'],
                '分析期間_日数': kpi['total_days'],
                'データ件数': kpi['data_count']
            })
        
        export_df = pd.DataFrame(export_data)
        csv_data = export_df.to_csv(index=False).encode('utf-8-sig')
        
        st.download_button(
            label="📥 CSVダウンロード",
            data=csv_data,
            file_name=f"診療科別パフォーマンス_{selected_period}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )


def render_dashboard_style_performance_cards(dept_kpis, columns_count):
    """
    dashboard_page.py のスタイルを応用した診療科別パフォーマンスカード表示
    """
    # カードをグリッド形式で表示
    for i in range(0, len(dept_kpis), columns_count):
        cols = st.columns(columns_count)
        for j in range(columns_count):
            if i + j < len(dept_kpis):
                with cols[j]:
                    kpi_data = dept_kpis[i + j]
                    create_dashboard_style_card(kpi_data)


def create_dashboard_style_card(kpi_data):
    """
    dashboard_page.py の _render_performance_cards を参考にした
    診療科別パフォーマンスカード（HTMLテンプレート使用）
    """
    if not kpi_data:
        return
    
    dept_name = kpi_data['dept_name']
    
    # 達成率による色分け（dashboard_page.py と同じロジック）
    census_achievement = kpi_data.get('census_achievement', 0) or 0
    admissions_achievement = kpi_data.get('admissions_achievement', 0) or 0
    
    # 代表達成率を決定（日平均在院患者数を優先）
    primary_rate = census_achievement if census_achievement > 0 else admissions_achievement
    
    def get_color_for_rate(rate):
        if rate >= 100:
            return "#28a745"  # 緑
        elif rate >= 80:
            return "#ffc107"  # 黄
        else:
            return "#dc3545"  # 赤
    
    color = get_color_for_rate(primary_rate)
    bar_width = min(primary_rate, 100) if primary_rate > 0 else 0
    
    # HTMLテンプレート（dashboard_page.py のスタイルを応用）
    html = f"""
    <div style="
        background-color: {color}1A; 
        border-left: 5px solid {color}; 
        padding: 16px; 
        border-radius: 8px; 
        margin-bottom: 16px; 
        height: 220px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    ">
        <!-- ヘッダー部分 -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h5 style="margin: 0; font-weight: bold; color: #333; font-size: 1.1em;">{dept_name}</h5>
            <span style="font-size: 0.8em; color: #666;">{kpi_data['total_days']}日間</span>
        </div>
        
        <!-- メトリクス部分 -->
        <div style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; font-size: 0.9em; margin-bottom: 2px;">
                <span>📋 日平均在院患者数:</span>
                <span style="font-weight: bold;">{kpi_data['avg_daily_census']:.1f} 人</span>
            </div>
            <div style="font-size: 0.8em; color: #666; margin-left: 20px;">
                直近週 {kpi_data['latest_week_census']:.1f}人/日
            </div>
            {f'''
            <div style="font-size: 0.8em; color: #666; margin-left: 20px;">
                目標 {kpi_data['target_daily_census']:.1f}人
            </div>
            ''' if kpi_data.get('target_daily_census') else ''}
        </div>
        
        <div style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; font-size: 0.9em; margin-bottom: 2px;">
                <span>🔄 週新入院患者数:</span>
                <span style="font-weight: bold;">{kpi_data['weekly_admissions']:.0f} 人</span>
            </div>
            <div style="font-size: 0.8em; color: #666; margin-left: 20px;">
                直近週 {kpi_data['latest_week_admissions']:.0f}人/週
            </div>
            {f'''
            <div style="font-size: 0.8em; color: #666; margin-left: 20px;">
                目標 {kpi_data['target_weekly_admissions']:.1f}人
            </div>
            ''' if kpi_data.get('target_weekly_admissions') else ''}
        </div>
        
        <div style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; font-size: 0.9em; margin-bottom: 2px;">
                <span>⏱️ 平均在院日数:</span>
                <span style="font-weight: bold;">{kpi_data['alos']:.1f} 日</span>
            </div>
            <div style="font-size: 0.8em; color: #666; margin-left: 20px;">
                直近週 {kpi_data['latest_week_alos']:.1f}日
            </div>
        </div>
        
        <!-- 達成率表示 -->
        {f'''
        <div style="display: flex; justify-content: space-between; font-size: 1.0em; color: {color}; margin-bottom: 8px;">
            <span style="font-weight: bold;">🎯 日平均達成率:</span>
            <span style="font-weight: bold;">{census_achievement:.1f}%</span>
        </div>
        <!-- プログレスバー -->
        <div style="background-color: #e9ecef; border-radius: 5px; height: 6px; margin-bottom: 4px;">
            <div style="width: {min(census_achievement, 100)}%; background-color: {color}; height: 6px; border-radius: 5px;"></div>
        </div>
        ''' if census_achievement > 0 else ''}
        
        {f'''
        <div style="display: flex; justify-content: space-between; font-size: 0.9em; color: {get_color_for_rate(admissions_achievement)};">
            <span style="font-weight: bold;">📈 新入院達成率:</span>
            <span style="font-weight: bold;">{admissions_achievement:.1f}%</span>
        </div>
        ''' if admissions_achievement > 0 else ''}
        
        <!-- データ件数表示 -->
        <div style="font-size: 0.7em; color: #888; text-align: right; margin-top: 4px;">
            データ件数: {kpi_data['data_count']}件
        </div>
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)

# メイン関数（app.pyから呼び出し用）
def create_department_performance_tab():
    """診療科別パフォーマンスダッシュボードタブの作成"""
    display_department_performance_dashboard()