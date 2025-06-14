import streamlit as st
import pandas as pd
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

def get_rate_color(rate):
    if rate is None:
        return "#666"
    if rate >= 100:
        return "#28a745"  # 緑
    elif rate >= 95:
        return "#f4b400"  # 黄
    else:
        return "#e74c3c"  # 赤

def build_card_grid(dept_kpis, metric_type):
    card_htmls = []
    for kpi in dept_kpis:
        name = get_display_name_for_dept(kpi['dept_code'], kpi['dept_name'])
        if metric_type == "日平均在院患者数":
            period = kpi.get('daily_avg_census', 0)
            recent = kpi.get('recent_week_daily_census', 0)
            target = kpi.get('daily_census_target')
            achv = kpi.get('daily_census_achievement')
            unit = "人/日"
        elif metric_type == "週合計新入院患者数":
            period = kpi.get('weekly_avg_admissions', 0)
            recent = kpi.get('recent_week_admissions', 0)
            target = kpi.get('weekly_admissions_target')
            achv = kpi.get('weekly_admissions_achievement')
            unit = "人"
        else:
            period = kpi.get('avg_length_of_stay', 0)
            recent = kpi.get('recent_week_avg_los', 0)
            target = kpi.get('avg_los_target')
            achv = (target / period * 100) if target and period else 0
            unit = "日"
        rate_color = get_rate_color(achv)
        # 罫線無し・行間詰め・数字右寄せ・ラベル小さめ・実績値太字
        card_htmls.append(f"""
        <div class="dept-card">
            <div class="dept-title">{name}</div>
            <div class="dept-meta">
                <span class="dept-label">期間平均:</span><span class="dept-num">{period:.1f}{unit}</span><br>
                <span class="dept-label">直近週実績:</span><span class="dept-num">{recent:.1f}{unit}</span><br>
                <span class="dept-label">目標:</span><span class="dept-num">{target if target else "--"}{unit}</span>
            </div>
            <div class="dept-achv-label">達成率:</div>
            <div class="dept-achv-value" style="color:{rate_color};">{achv:.1f}%</div>
        </div>
        """)

    # 3列グリッドでラップ
    grid_html = ""
    for i in range(0, len(card_htmls), 3):
        grid_html += "<div class='dept-grid-row'>" + "".join(card_htmls[i:i+3]) + "</div>\n"
    html = f"""
    <style>
    .dept-grid-row {{
        display: flex; gap:18px; margin-bottom:14px;
    }}
    .dept-card {{
        flex:1;
        background:#fff;
        border-radius:17px;
        box-shadow:0 2px 10px #eee;
        padding:14px 20px 9px 18px;
        min-width:0;
        min-height:120px;
        display:flex;
        flex-direction:column;
        justify-content:flex-start;
    }}
    .dept-title {{
        font-size:1.35em; font-weight:700; color:#26352c; margin-bottom:5px; letter-spacing:0.03em;
    }}
    .dept-meta {{
        font-size:1.05em; color:#7c8b7c; line-height:1.28; margin-bottom:2px; font-weight:400;
    }}
    .dept-label {{
        font-size:0.98em; color:#7c8b7c; font-weight:400; min-width:7em; display:inline-block; letter-spacing:0.01em;
    }}
    .dept-num {{
        font-size:1.17em; font-weight:600; color:#28303b; float:right; margin-left:12px; letter-spacing:0.01em;
    }}
    .dept-achv-label {{
        font-size:1.12em; color:#2a8b36; font-weight:700; margin-top:2px; display:inline-block;
    }}
    .dept-achv-value {{
        font-size:1.33em; font-weight:800; display:inline-block; margin-left:13px;
    }}
    </style>
    {grid_html}
    """
    return html

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
    if dept_col not in date_filtered_df.columns:
        st.error(f"診療科列が見つかりません: {dept_col}")
        return
    metric_type = st.radio("表示項目", ("日平均在院患者数", "週合計新入院患者数", "平均在院日数"),
                           horizontal=True, index=0, key="dept_perf_metric_type")
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
    # 選択項目ごとに達成率または目標値順でソート
    if metric_type == "日平均在院患者数":
        dept_kpis.sort(key=lambda x: x.get('daily_census_achievement', 0), reverse=True)
    elif metric_type == "週合計新入院患者数":
        dept_kpis.sort(key=lambda x: x.get('weekly_admissions_achievement', 0), reverse=True)
    else:
        dept_kpis.sort(key=lambda x: (x.get('avg_los_target', 0) or 0))
    st.markdown(f"**{period_desc}** の診療科別パフォーマンス")
    st.markdown(build_card_grid(dept_kpis, metric_type), unsafe_allow_html=True)

def create_department_performance_tab():
    display_department_performance_dashboard()
