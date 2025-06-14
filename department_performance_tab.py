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
            indicator_type = str(row.get('指標タイプ', '')).strip()
            target_value = row.get('目標値', None)
            # 完全一致優先、該当したらbreak
            if indicator_type == '日平均在院患者数':
                targets['daily_census_target'] = target_value
            elif indicator_type == '週間新入院患者数':
                targets['weekly_admissions_target'] = target_value
            elif indicator_type == '平均在院日数':
                targets['avg_los_target'] = target_value
        # 他の指標タイプ（新入院、月間新入院患者数、入院患者数等）は一切weeklyにセットしない
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
    daily = kpi_data.get('daily_avg_census', 0)
    daily_target = kpi_data.get('daily_census_target', None)
    daily_achv = kpi_data.get('daily_census_achievement', 0)
    weekly = kpi_data.get('weekly_avg_admissions', 0)
    weekly_target = kpi_data.get('weekly_admissions_target', None)
    weekly_achv = kpi_data.get('weekly_admissions_achievement', 0)
    los = kpi_data.get('avg_length_of_stay', 0)
    los_target = kpi_data.get('avg_los_target', None)
    if los_target and los:
        los_achv = los_target / los * 100
    else:
        los_achv = 0

    # ★ 色分け基準を「日平均在院患者数達成率」だけにする
    if daily_achv >= 100:
        color = "#28a745"   # 緑
    elif daily_achv >= 80:
        color = "#ffc107"   # 黄
    else:
        color = "#dc3545"   # 赤
    bar_width = min(daily_achv, 100)

    # HTML一体で描画
    st.markdown(f"""
    <div style="
        background-color: {color}10;
        border-left: 6px solid {color};
        padding: 18px 18px 10px 18px;
        border-radius: 11px;
        margin-bottom: 12px;
        box-shadow: 0 3px 12px rgba(0,0,0,0.07);
    ">
        <div style="font-size:1.18em; font-weight:bold; margin-bottom:12px; color:#23292f;">{kpi_data.get('dept_name') or kpi_data.get('診療科') or '診療科未設定'}</div>
        <div style="display:flex; gap:22px;">
            <div style="flex:1; text-align:center;">
                <div style="font-size:0.97em;">日平均在院患者数</div>
                <div style="font-size:1.7em; font-weight:bold; margin:7px 0;">{daily:.1f}</div>
                <div style="font-size:0.92em; color:#666;">目標: {daily_target if daily_target else '未設定'}</div>
                <div style="font-size:0.92em; color:#666;">達成率: <span style="color:{color}; font-weight:bold;">{daily_achv:.1f}%</span></div>
            </div>
            <div style="flex:1; text-align:center;">
                <div style="font-size:0.97em;">週合計新入院患者数</div>
                <div style="font-size:1.7em; font-weight:bold; margin:7px 0;">{weekly:.1f}</div>
                <div style="font-size:0.92em; color:#666;">目標: {weekly_target if weekly_target else '未設定'}</div>
                <div style="font-size:0.92em; color:#666;">達成率: <span style="color:{color}; font-weight:bold;">{weekly_achv:.1f}%</span></div>
            </div>
            <div style="flex:1; text-align:center;">
                <div style="font-size:0.97em;">平均在院日数</div>
                <div style="font-size:1.7em; font-weight:bold; margin:7px 0;">{los:.1f}</div>
                <div style="font-size:0.92em; color:#666;">目標: {los_target if los_target else '未設定'}</div>
                <div style="font-size:0.92em; color:#666;">達成率: <span style="color:{color}; font-weight:bold;">{los_achv:.1f}%</span></div>
            </div>
        </div>
        <div style="background-color:#e9ecef; border-radius:4px; height:7px; margin:13px 4px 0 4px;">
            <div style="width:{bar_width}%; background-color:{color}; height:7px; border-radius:4px;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("")

def display_department_performance_dashboard():
    """診療科別パフォーマンスダッシュボードのメイン表示関数"""
    st.header("🏥 診療科別パフォーマンスダッシュボード")
    
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
    dept_kpis.sort(key=lambda x: x.get('daily_census_achievement', 0), reverse=True)
    cols = st.columns(3)
    for idx, kpi_data in enumerate(dept_kpis):
        with cols[idx % 3]:
            create_department_card_styled(kpi_data)

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