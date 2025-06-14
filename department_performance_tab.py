import streamlit as st
import pandas as pd
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

try:
    from utils import safe_date_filter, get_display_name_for_dept
    from unified_filters import get_unified_filter_config
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.stop()

def get_period_dates(df, period_type):
    if df is None or df.empty or '日付' not in df.columns:
        return None, None, "データなし"
    max_date = df['日付'].max()
    min_date = df['日付'].min()
    if period_type == "直近4週":
        start_date = max_date - pd.Timedelta(days=27)
        desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "今年度":
        year = max_date.year if max_date.month >= 4 else max_date.year - 1
        start_date = pd.Timestamp(year=year, month=4, day=1)
        start_date = max(start_date, min_date)
        desc = f"今年度 ({start_date.strftime('%Y/%m/%d')}～{max_date.strftime('%m/%d')})"
    else:
        start_date = max_date - pd.Timedelta(days=27)
        desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    start_date = max(start_date, min_date)
    return start_date, max_date, desc

def get_target_values_for_dept(target_data, dept_code, dept_name):
    """
    目標値を「部門コード」または「部門名」のいずれかで取得
    """
    targets = {
        'daily_census_target': None,
        'weekly_admissions_target': None,
        'avg_los_target': None
    }
    if target_data is None or target_data.empty:
        return targets
    try:
        # コードで一致を最優先、なければ名称で一致を探す
        matched = target_data[
            (target_data['部門コード'] == dept_code)
            | (target_data['部門名'] == dept_name)
        ]
        for _, row in matched.iterrows():
            indicator_type = str(row.get('指標タイプ', '')).strip()
            target_value = row.get('目標値', None)
            if indicator_type == '日平均在院患者数':
                targets['daily_census_target'] = target_value
            elif indicator_type == '週間新入院患者数':
                targets['weekly_admissions_target'] = target_value
            elif indicator_type == '平均在院日数':
                targets['avg_los_target'] = target_value
    except Exception as e:
        logger.error(f"目標値取得エラー ({dept_code}/{dept_name}): {e}")
    return targets

def calculate_department_kpis(df, target_data, dept_code, dept_name, start_date, end_date, dept_col):
    try:
        dept_df = df[df[dept_col] == dept_code]
        period_df = safe_date_filter(dept_df, start_date, end_date)
        if period_df.empty:
            return None
        total_days = (end_date - start_date).days + 1
        total_patient_days = period_df['在院患者数'].sum() if '在院患者数' in period_df.columns else 0
        total_admissions = period_df['新入院患者数'].sum() if '新入院患者数' in period_df.columns else 0
        total_discharges = period_df['退院患者数'].sum() if '退院患者数' in period_df.columns else 0
        daily_avg_census = total_patient_days / total_days if total_days > 0 else 0
        recent_week_end = end_date
        recent_week_start = end_date - pd.Timedelta(days=6)
        recent_week_df = safe_date_filter(dept_df, recent_week_start, recent_week_end)
        recent_week_patient_days = recent_week_df['在院患者数'].sum() if '在院患者数' in recent_week_df.columns and not recent_week_df.empty else 0
        recent_week_admissions = recent_week_df['新入院患者数'].sum() if '新入院患者数' in recent_week_df.columns and not recent_week_df.empty else 0
        recent_week_discharges = recent_week_df['退院患者数'].sum() if '退院患者数' in recent_week_df.columns and not recent_week_df.empty else 0
        recent_week_daily_census = recent_week_patient_days / 7 if recent_week_patient_days > 0 else 0
        avg_length_of_stay = total_patient_days / total_discharges if total_discharges > 0 else 0
        recent_week_avg_los = recent_week_patient_days / recent_week_discharges if recent_week_discharges > 0 else 0
        weekly_avg_admissions = (total_admissions / total_days) * 7 if total_days > 0 else 0
        targets = get_target_values_for_dept(target_data, dept_code, dept_name)
        daily_census_achievement = (daily_avg_census / targets['daily_census_target'] * 100) if targets['daily_census_target'] else 0
        weekly_admissions_achievement = (weekly_avg_admissions / targets['weekly_admissions_target'] * 100) if targets['weekly_admissions_target'] else 0
        return {
            'dept_code': dept_code,
            'dept_name': dept_name,
            'total_days': total_days,
            'data_count': len(period_df),
            'daily_avg_census': daily_avg_census,
            'recent_week_daily_census': recent_week_daily_census,
            'daily_census_target': targets['daily_census_target'],
            'daily_census_achievement': daily_census_achievement,
            'weekly_avg_admissions': weekly_avg_admissions,
            'recent_week_admissions': recent_week_admissions,
            'weekly_admissions_target': targets['weekly_admissions_target'],
            'weekly_admissions_achievement': weekly_admissions_achievement,
            'avg_length_of_stay': avg_length_of_stay,
            'recent_week_avg_los': recent_week_avg_los,
            'avg_los_target': targets['avg_los_target']
        }
    except Exception as e:
        logger.error(f"KPI計算エラー ({dept_code}/{dept_name}): {e}", exc_info=True)
        return None

def get_color(daily_achv):
    if daily_achv >= 100:
        return "#28a745"
    elif daily_achv >= 80:
        return "#ffc107"
    else:
        return "#dc3545"

def create_metric_card(kpi, metric_type):
    color = get_color(kpi.get('daily_census_achievement', 0))
    # 表示する値・キャプション選択
    if metric_type == 'census':
        period = kpi.get('daily_avg_census', 0)
        recent = kpi.get('recent_week_daily_census', 0)
        target = kpi.get('daily_census_target', None)
        achievement = kpi.get('daily_census_achievement', 0)
        unit = "人/日"
        label = "日平均在院患者数"
    elif metric_type == 'admissions':
        period = kpi.get('weekly_avg_admissions', 0)
        recent = kpi.get('recent_week_admissions', 0)
        target = kpi.get('weekly_admissions_target', None)
        achievement = kpi.get('weekly_admissions_achievement', 0)
        unit = "人/週"
        label = "週合計新入院患者数"
    else:
        period = kpi.get('avg_length_of_stay', 0)
        recent = kpi.get('recent_week_avg_los', 0)
        target = kpi.get('avg_los_target', None)
        achievement = (target / period * 100) if target and period else 0
        unit = "日"
        label = "平均在院日数"
    st.markdown(
        f"""
        <div style="background:#fff;border-radius:12px;box-shadow:0 2px 8px #ddd;padding:16px 14px 8px 14px;margin-bottom:8px;">
            <div style="font-size:1.1em;font-weight:600;margin-bottom:3px; color:#343a40;">{get_display_name_for_dept(kpi['dept_code'], kpi['dept_name'])}</div>
            <div style="font-size:1em;margin-bottom:3px;">{label}</div>
            <div style="font-size:0.92em; color:#555;">
                <span style="margin-right:16px;">期間平均: <b>{period:.1f}{unit}</b></span>
                <span style="margin-right:16px;">直近週実績: <b>{recent:.1f}{unit}</b></span>
                <span style="margin-right:16px;">目標: <b>{target if target else '-'}{unit}</b></span>
                <span style="margin-right:8px;">達成率: <span style="color:{color};font-weight:700;">{achievement:.1f}%</span></span>
            </div>
        </div>
        """, unsafe_allow_html=True
    )

def display_department_performance_dashboard():
    st.header("🏥 診療科別パフォーマンスダッシュボード")
    if not st.session_state.get('data_processed', False):
        st.warning("データを読み込み後に利用可能になります。")
        return
    df_original = st.session_state['df']
    target_data = st.session_state.get('target_data', {})
    unified_config = get_unified_filter_config()
    period_key = unified_config.get('period') or unified_config.get('period_type') or '直近4週'
    start_date, end_date, period_desc = get_period_dates(df_original, period_key)
    date_filtered_df = safe_date_filter(df_original, start_date, end_date)
    dept_col = '診療科名'
    code_col = '診療科名'
    # 診療科名を部門コードとして利用
    if dept_col not in date_filtered_df.columns:
        st.error(f"診療科列が見つかりません: {dept_col}")
        return
    # セレクトボックスでメトリクス種別選択
    metric_type = st.radio("表示項目", ("日平均在院患者数", "週合計新入院患者数", "平均在院日数"), horizontal=True,
                           index=0,
                           key="dept_perf_metric_type")
    metric_key = {'日平均在院患者数': 'census', '週合計新入院患者数': 'admissions', '平均在院日数': 'alos'}[metric_type]
    dept_kpis = []
    for dept_code in date_filtered_df[code_col].unique():
        dept_name = get_display_name_for_dept(dept_code, dept_code)
        kpi = calculate_department_kpis(
            date_filtered_df, target_data, dept_code, dept_name, start_date, end_date, code_col
        )
        if kpi:
            dept_kpis.append(kpi)
    if not dept_kpis:
        st.warning("表示可能な診療科データがありません。")
        return
    # ソート（日平均在院患者数の達成率順）
    dept_kpis.sort(key=lambda x: x.get('daily_census_achievement', 0), reverse=True)
    st.markdown(f"**{period_desc}** の診療科別パフォーマンス")
    n_cols = 3
    for i in range(0, len(dept_kpis), n_cols):
        cols = st.columns(n_cols)
        for j, kpi in enumerate(dept_kpis[i:i + n_cols]):
            with cols[j]:
                create_metric_card(kpi, metric_key)

def create_department_performance_tab():
    display_department_performance_dashboard()
