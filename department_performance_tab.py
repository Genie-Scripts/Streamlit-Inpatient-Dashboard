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
    from style import inject_department_performance_css, get_achievement_color_class, get_card_class
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.stop()


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
    """各診療科のKPIを計算して辞書で返す（Wordファイル形式に対応）"""
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


def create_department_card_html(kpi_data):
    """各診療科の KPI を HTML カード形式で描画する（Wordファイル形式）"""
    
    # 達成率に基づく色分け
    daily_census_color = get_achievement_color_class(kpi_data.get('daily_census_achievement', 0))
    weekly_admissions_color = get_achievement_color_class(kpi_data.get('weekly_admissions_achievement', 0))
    
    # カード全体のクラス
    card_class = get_card_class(
        kpi_data.get('daily_census_achievement', 0),
        kpi_data.get('weekly_admissions_achievement', 0)
    )
    
    # 値のフォーマット
    def format_value(value, decimal_places=1):
        if value is None or value == 0:
            return "0"
        return f"{value:.{decimal_places}f}"
    
    def format_achievement(value):
        if value is None or value == 0:
            return "0%"
        return f"{value:.1f}%"

    html = f"""
        <div class="dept-performance-card-new {card_class}">
            <!-- 診療科名ヘッダー -->
            <div class="dept-header">
                <h3>{kpi_data['dept_name']}</h3>
            </div>
            
            <!-- 3つの主要指標を横並び -->
            <div class="metrics-container">
                <!-- 日平均在院患者数 -->
                <div class="metric-section">
                    <div class="metric-title">日平均在院患者数</div>
                    <div class="metric-main-value">{format_value(kpi_data.get('daily_avg_census', 0))}</div>
                    <div class="metric-details">
                        <div class="metric-detail-row">
                            <span class="detail-label">直近週</span>
                            <span class="detail-value">{format_value(kpi_data.get('recent_week_daily_census', 0))}人/日</span>
                        </div>
                        <div class="metric-detail-row">
                            <span class="detail-label">目標</span>
                            <span class="detail-value">{format_value(kpi_data.get('daily_census_target', 0)) if kpi_data.get('daily_census_target') else '未設定'}人</span>
                        </div>
                        <div class="metric-detail-row">
                            <span class="detail-label">達成率</span>
                            <span class="achievement-badge {daily_census_color}">{format_achievement(kpi_data.get('daily_census_achievement', 0))}</span>
                        </div>
                    </div>
                </div>
                
                <!-- 週合計新入院患者数 -->
                <div class="metric-section">
                    <div class="metric-title">週合計新入院患者数</div>
                    <div class="metric-main-value">{format_value(kpi_data.get('weekly_avg_admissions', 0), 0)}</div>
                    <div class="metric-details">
                        <div class="metric-detail-row">
                            <span class="detail-label">直近週</span>
                            <span class="detail-value">{format_value(kpi_data.get('recent_week_admissions', 0), 0)}人/週</span>
                        </div>
                        <div class="metric-detail-row">
                            <span class="detail-label">目標</span>
                            <span class="detail-value">{format_value(kpi_data.get('weekly_admissions_target', 0)) if kpi_data.get('weekly_admissions_target') else '未設定'}人</span>
                        </div>
                        <div class="metric-detail-row">
                            <span class="detail-label">達成率</span>
                            <span class="achievement-badge {weekly_admissions_color}">{format_achievement(kpi_data.get('weekly_admissions_achievement', 0))}</span>
                        </div>
                    </div>
                </div>
                
                <!-- 平均在院日数 -->
                <div class="metric-section">
                    <div class="metric-title">平均在院日数</div>
                    <div class="metric-main-value">{format_value(kpi_data.get('avg_length_of_stay', 0))}</div>
                    <div class="metric-details">
                        <div class="metric-detail-row">
                            <span class="detail-label">直近週</span>
                            <span class="detail-value">{format_value(kpi_data.get('recent_week_avg_los', 0))}日</span>
                        </div>
                        <div class="metric-detail-row">
                            <span class="detail-label">目標</span>
                            <span class="detail-value">{format_value(kpi_data.get('avg_los_target', 0)) if kpi_data.get('avg_los_target') else '未設定'}日</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    """
    # インデントと先頭空白を除去
    return textwrap.dedent(html).lstrip()


def render_performance_cards(dept_kpis, columns_count):
    for i in range(0, len(dept_kpis), columns_count):
        cols = st.columns(columns_count)
        for j in range(columns_count):
            if i + j < len(dept_kpis):
                with cols[j]:
                    html = create_department_card_html(dept_kpis[i+j])
                    st.markdown(html, unsafe_allow_html=True)


def display_department_performance_dashboard():
    st.header("🏥 診療科別パフォーマンスダッシュボード")
    inject_department_performance_css()

    if not st.session_state.get('data_processed', False):
        st.warning("データを読み込み後に利用可能になります。")
        return

    df_original = st.session_state['df']
    target_data = st.session_state.get('target_data', {})

    # 統一設定から期間・ソート・列数を取得
    unified_config = get_unified_filter_config()
    period_key = unified_config.get('period') or unified_config.get('period_type') or '直近4週'
    sort_key = unified_config.get('sort', '診療科名（昇順）')
    columns_count = unified_config.get('columns', 2)  # Wordファイル形式に合わせて2列に変更

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

    # KPIリストのソート
    sort_map = {
        "週新入院患者数達成率（降順）": ('weekly_admissions_achievement', True),
        "日平均在院患者数達成率（降順）": ('daily_census_achievement', True),
        "日平均在院患者数（降順）": ('daily_avg_census', True),
        "診療科名（昇順）": ('dept_name', False)
    }
    key, rev = sort_map.get(sort_key, ('dept_name', False))
    dept_kpis.sort(key=lambda x: x.get(key) or 0, reverse=rev)

    # タイトルとカード表示
    st.markdown(f"**{period_desc}** の診療科別パフォーマンス")
    st.markdown("---")
    render_performance_cards(dept_kpis, columns_count)


def create_department_performance_tab():
    display_department_performance_dashboard()