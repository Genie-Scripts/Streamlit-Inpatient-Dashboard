# dashboard_overview_tab.py

import streamlit as st
import pandas as pd
from datetime import timedelta # pd.Timedelta のために必要

# dashboard_charts.py からのインポートは維持
try:
    from dashboard_charts import (
        create_monthly_trend_chart,
        create_admissions_discharges_chart,
        create_occupancy_chart
    )
except ImportError:
    st.error("dashboard_charts.py が見つからないか、必要な関数が定義されていません。")
    create_monthly_trend_chart = None
    create_admissions_discharges_chart = None
    create_occupancy_chart = None

# kpi_calculator.py からのインポートは維持
try:
    from kpi_calculator import calculate_kpis, analyze_kpi_insights, get_kpi_status
except ImportError:
    st.error("kpi_calculator.py が見つからないか、必要な関数が定義されていません。")
    calculate_kpis = None
    analyze_kpi_insights = None
    get_kpi_status = None

# config.py から定数をインポート
from config import (
    DEFAULT_OCCUPANCY_RATE,
    DEFAULT_ADMISSION_FEE,
    DEFAULT_TARGET_PATIENT_DAYS,
    APP_VERSION,
    NUMBER_FORMAT,
    DEFAULT_TOTAL_BEDS,
    DEFAULT_AVG_LENGTH_OF_STAY,
    DEFAULT_TARGET_ADMISSIONS  # ★★★ この行が重要 ★★★
)


# ===== 新しく配置する関数 =====
def format_number_with_config(value, unit="", format_type="default"):
    if pd.isna(value) or value is None:
        return f"0{unit}" if unit else "0"
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return str(value)
    if value == 0:
        return f"0{unit}" if unit else "0"

    if format_type == "currency":
        return f"{value:,.0f}{NUMBER_FORMAT['currency_symbol']}"
    elif format_type == "percentage":
        return f"{value:.1f}{NUMBER_FORMAT['percentage_symbol']}"
    else:
        return f"{value:,.1f}{unit}" if isinstance(value, float) else f"{value:,.0f}{unit}"


def display_unified_metrics_layout_colorized(metrics, selected_period_info):
    if not metrics:
        st.warning("表示するメトリクスデータがありません。")
        return

    st.info(f"📊 平均値計算期間: {selected_period_info}")
    st.caption("※延べ在院日数、病床利用率などは、それぞれの指標の計算ロジックに基づいた期間の値を表示します。")

    st.markdown("### 📊 主要指標")
    col1, col2, col3 = st.columns(3)

    with col1:
        avg_daily_census_val = metrics.get('avg_daily_census', 0)
        avg_daily_census_30d_val = metrics.get('avg_daily_census_30d', 0)
        st.metric(
            "日平均在院患者数",
            f"{avg_daily_census_val:.1f}人",
            delta=f"参考(直近30日): {avg_daily_census_30d_val:.1f}人" if avg_daily_census_30d_val is not None else None,
            help=f"{selected_period_info}の日平均在院患者数"
        )

    with col2:
        bed_occupancy_rate_val = metrics.get('bed_occupancy_rate', 0)
        target_occupancy = st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE) * 100
        occupancy_delta = bed_occupancy_rate_val - target_occupancy if bed_occupancy_rate_val is not None else 0
        delta_color = "normal" if abs(occupancy_delta) <= 5 else ("inverse" if occupancy_delta < -5 else "off")
        st.metric(
            "病床利用率",
            f"{bed_occupancy_rate_val:.1f}%" if bed_occupancy_rate_val is not None else "N/A",
            delta=f"{occupancy_delta:+.1f}% (対目標{target_occupancy:.0f}%)" if bed_occupancy_rate_val is not None else None,
            delta_color=delta_color,
            help="選択期間の日平均在院患者数と基本設定の総病床数から算出"
        )

    with col3:
        avg_los_val = metrics.get('avg_los', 0)
        avg_length_of_stay_target = st.session_state.get('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY)
        st.metric(
            "平均在院日数",
            f"{avg_los_val:.1f}日",
            delta=f"目標: {avg_length_of_stay_target:.1f}日",
            help=f"{selected_period_info}の平均在院日数"
        )
    st.markdown("---")

    st.markdown("### 💰 収益関連指標")
    col_rev1, col_rev2, col_rev3 = st.columns(3)

    with col_rev1:
        estimated_revenue_val = metrics.get('estimated_revenue', 0)
        avg_admission_fee_val = st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE)
        st.metric(
            f"推計収益 ({selected_period_info})",
            format_number_with_config(estimated_revenue_val, format_type="currency"),
            delta=f"単価: {avg_admission_fee_val:,}円/日",
            help=f"{selected_period_info}の推計収益"
        )

    with col_rev2:
        total_patient_days_val = metrics.get('total_patient_days', 0)
        monthly_target_days = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS)
        days_in_selected_period = metrics.get('period_days', 1)
        proportional_target_days = (monthly_target_days / 30.44) * days_in_selected_period if days_in_selected_period > 0 else 0
        achievement_days = (total_patient_days_val / proportional_target_days) * 100 if proportional_target_days > 0 else 0
        st.metric(
            f"延べ在院日数 ({selected_period_info})",
            format_number_with_config(total_patient_days_val, "人日"),
            delta=f"対期間目標: {achievement_days:.1f}%" if proportional_target_days > 0 else "目標計算不可",
            delta_color="normal" if achievement_days >= 95 else "inverse",
            help=f"{selected_period_info}の延べ在院日数。目標は月間目標を選択期間日数で按分して計算。"
        )

    with col_rev3:
        avg_daily_admissions_val = metrics.get('avg_daily_admissions', 0)
        period_days_val = metrics.get('period_days', 0)
        st.metric(
            "日平均新入院患者数",
            f"{avg_daily_admissions_val:.1f}人",
            delta=f"期間: {period_days_val}日間",
            help=f"{selected_period_info}の日平均新入院患者数"
        )

    with st.expander("📋 詳細データと設定値 (経営ダッシュボード)", expanded=False):
        detail_col1, detail_col2, detail_col3 = st.columns(3)
        with detail_col1:
            st.markdown("**🏥 基本設定**")
            st.write(f"• 総病床数: {metrics.get('total_beds', st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)):,}床")
            st.write(f"• 目標病床稼働率: {st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE):.1%}")
            st.write(f"• 平均入院料: {st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE):,}円/日")
            st.write(f"• 目標平均在院日数: {st.session_state.get('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY):.1f}日")
        with detail_col2:
            st.markdown("**📅 期間情報**")
            st.write(f"• 計算対象期間: {selected_period_info}")
            st.write(f"• アプリバージョン: v{APP_VERSION}")
        with detail_col3:
            st.markdown("**🎯 月間目標値**")
            st.write(f"• 延べ在院日数: {format_number_with_config(st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS), '人日')}")
            target_rev = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS) * st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE)
            st.write(f"• 推定収益: {format_number_with_config(target_rev, format_type='currency')}")
            st.write(f"• 新入院患者数: {st.session_state.get('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS):,}人") # ここで参照


def display_kpi_cards_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent):
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    if calculate_kpis is None:
        st.error("KPI計算関数が利用できません。")
        return
    kpis_selected_period = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)
    if kpis_selected_period is None or kpis_selected_period.get("error"):
        st.warning(f"選択された期間のKPI計算に失敗しました。理由: {kpis_selected_period.get('error', '不明') if kpis_selected_period else '不明'}")
        return
    latest_date_in_df = df['日付'].max()
    start_30d = latest_date_in_df - pd.Timedelta(days=29)
    end_30d = latest_date_in_df
    df_30d = df[(df['日付'] >= start_30d) & (df['日付'] <= end_30d)]
    kpis_30d = calculate_kpis(df_30d, start_30d, end_30d, total_beds=total_beds_setting) if not df_30d.empty else {}
    metrics_for_display = {
        'avg_daily_census': kpis_selected_period.get('avg_daily_census'),
        'avg_daily_census_30d': kpis_30d.get('avg_daily_census'),
        'bed_occupancy_rate': kpis_selected_period.get('bed_occupancy_rate'),
        'avg_los': kpis_selected_period.get('alos'),
        'estimated_revenue': kpis_selected_period.get('total_patient_days', 0) * st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE),
        'total_patient_days': kpis_selected_period.get('total_patient_days'),
        'avg_daily_admissions': kpis_selected_period.get('avg_daily_admissions'),
        'period_days': kpis_selected_period.get('days_count'),
        'total_beds': total_beds_setting,
    }
    period_description = f"{start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')}"
    display_unified_metrics_layout_colorized(metrics_for_display, period_description)

def display_trend_graphs_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent):
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    if calculate_kpis is None: return
    if not all([create_monthly_trend_chart, create_admissions_discharges_chart, create_occupancy_chart]):
        st.warning("グラフ生成関数の一部が利用できません。")
        return
    kpi_data = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)
    if kpi_data is None or kpi_data.get("error"):
        st.warning(f"グラフ表示用のKPIデータ計算に失敗しました。")
        return
    col1_chart, col2_chart = st.columns(2)
    with col1_chart:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        st.markdown("<div class='chart-title'>月別 平均在院日数と入退院患者数の推移</div>", unsafe_allow_html=True)
        monthly_chart = create_monthly_trend_chart(kpi_data)
        if monthly_chart:
            st.plotly_chart(monthly_chart, use_container_width=True)
        else:
            st.info("月次トレンドチャート: データ不足のため表示できません。")
        st.markdown("</div>", unsafe_allow_html=True)
    with col2_chart:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        st.markdown("<div class='chart-title'>週別 入退院バランス</div>", unsafe_allow_html=True)
        balance_chart = create_admissions_discharges_chart(kpi_data)
        if balance_chart:
            st.plotly_chart(balance_chart, use_container_width=True)
        else:
            st.info("入退院バランスチャート: データ不足のため表示できません。")
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='chart-container full-width'>", unsafe_allow_html=True)
    st.markdown(f"<div class='chart-title'>月別 病床利用率の推移 (総病床数: {total_beds_setting}床)</div>", unsafe_allow_html=True)
    occupancy_chart_fig = create_occupancy_chart(kpi_data, total_beds_setting, target_occupancy_setting_percent)
    if occupancy_chart_fig:
        st.plotly_chart(occupancy_chart_fig, use_container_width=True)
    else:
        st.info("病床利用率チャート: データ不足または総病床数未設定のため表示できません。")
    st.markdown("</div>", unsafe_allow_html=True)
    display_insights(kpi_data, total_beds_setting)

def display_insights(kpi_data, total_beds_setting):
    if analyze_kpi_insights and kpi_data:
        insights = analyze_kpi_insights(kpi_data, total_beds_setting)
        st.markdown("<div class='chart-container full-width'>", unsafe_allow_html=True)
        st.markdown("<div class='chart-title'>分析インサイトと考慮事項</div>", unsafe_allow_html=True)
        insight_col1, insight_col2 = st.columns(2)
        with insight_col1:
            if insights.get("alos"):
                st.markdown("<div class='info-card'><h4>平均在院日数 (ALOS) に関する考察</h4>" + "".join([f"<p>- {i}</p>" for i in insights["alos"]]) + "</div>", unsafe_allow_html=True)
            if insights.get("weekday_pattern"):
                st.markdown("<div class='neutral-card'><h4>曜日別パターンの活用</h4>" + "".join([f"<p>- {i}</p>" for i in insights["weekday_pattern"]]) + "</div>", unsafe_allow_html=True)
        with insight_col2:
            if insights.get("occupancy"):
                st.markdown("<div class='success-card'><h4>病床利用率と回転数</h4>" + "".join([f"<p>- {i}</p>" for i in insights["occupancy"]]) + "</div>", unsafe_allow_html=True)
            if insights.get("general"):
                st.markdown("<div class='warning-card'><h4>データ解釈上の注意点</h4>" + "".join([f"<p>- {i}</p>" for i in insights["general"]]) + "</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("インサイトを生成するためのデータまたは関数が不足しています。")
