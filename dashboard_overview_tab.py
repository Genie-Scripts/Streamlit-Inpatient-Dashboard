import streamlit as st
import pandas as pd
# from datetime import datetime # display_unified_metrics_layout_colorized では直接不要

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
    DEFAULT_AVG_LENGTH_OF_STAY  # ★★★ この行を追加 ★★★
)


# ===== 新しく配置する関数 =====
def format_number_with_config(value, unit="", format_type="default"):
    # ... (既存のコード) ...
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
    # ... (既存のコード) ...
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
        avg_length_of_stay_target = st.session_state.get('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY) # ここで参照
        st.metric(
            "平均在院日数",
            f"{avg_los_val:.1f}日",
            delta=f"目標: {avg_length_of_stay_target:.1f}日",
            help=f"{selected_period_info}の平均在院日数"
        )
    # ... (以降のコードは変更なし) ...
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
            st.write(f"• 目標平均在院日数: {st.session_state.get('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY):.1f}日") # ここも参照
        with detail_col2:
            st.markdown("**📅 期間情報**")
            st.write(f"• 計算対象期間: {selected_period_info}")
            st.write(f"• アプリバージョン: v{APP_VERSION}")
        with detail_col3:
            st.markdown("**🎯 月間目標値**")
            st.write(f"• 延べ在院日数: {format_number_with_config(st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS), '人日')}")
            target_rev = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS) * st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE)
            st.write(f"• 推定収益: {format_number_with_config(target_rev, format_type='currency')}")
            st.write(f"• 新入院患者数: {st.session_state.get('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS):,}人")


def display_kpi_cards_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent): # target_occupancy_setting を % に変更
    """
    KPIカードのみを表示する関数。
    内部で display_unified_metrics_layout_colorized を呼び出すように変更。
    """
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return

    if calculate_kpis is None:
        st.error("KPI計算関数が利用できません。")
        return

    # 選択された期間のKPIを計算
    kpis_selected_period = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)

    if kpis_selected_period is None or kpis_selected_period.get("error"):
        st.warning(f"選択された期間のKPI計算に失敗しました。理由: {kpis_selected_period.get('error', '不明') if kpis_selected_period else '不明'}")
        return

    # 「直近30日」のKPIも計算（display_unified_metrics_layout_colorized が期待するため）
    # dfの最新日付を基準とする
    latest_date_in_df = df['日付'].max()
    start_30d = latest_date_in_df - pd.Timedelta(days=29)
    df_30d = df[(df['日付'] >= start_30d) & (df['日付'] <= latest_date_in_df)]
    kpis_30d = calculate_kpis(df_30d, start_30d, latest_date_in_df, total_beds=total_beds_setting)

    if kpis_30d is None or kpis_30d.get("error"):
        st.warning(f"直近30日のKPI計算に失敗しました。理由: {kpis_30d.get('error', '不明') if kpis_30d else '不明'}")
        # 30日データがない場合でも、選択期間のデータで表示を試みる
        kpis_30d = {} # 空の辞書でフォールバック

    # display_unified_metrics_layout_colorized に渡す metrics 辞書を構築
    metrics_for_display = {
        'avg_daily_census': kpis_selected_period.get('avg_daily_census'),
        'avg_daily_census_30d': kpis_30d.get('avg_daily_census'), # 30日データ
        'bed_occupancy_rate': kpis_selected_period.get('bed_occupancy_rate'),
        'avg_los': kpis_selected_period.get('alos'),
        'estimated_revenue': kpis_selected_period.get('total_patient_days', 0) * st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE), # 選択期間の推計収益
        'total_patient_days': kpis_selected_period.get('total_patient_days'), # 選択期間の延べ在院日数
        'avg_daily_admissions': kpis_selected_period.get('avg_daily_admissions'),
        'period_days': kpis_selected_period.get('days_count'),
        'total_beds': total_beds_setting,
        # 'target_revenue' は display_unified_metrics_layout_colorized 内部で計算されるか、セッションから取得される
    }
    
    # 期間の説明
    period_description = f"{start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')}"
    
    display_unified_metrics_layout_colorized(metrics_for_display, period_description)


def display_trend_graphs_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent): # target_occupancy_setting を % に変更
    """トレンドグラフのみを表示する関数"""
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    if calculate_kpis is None: return # display_kpi_cards_only でチェック済みだが念のため
    if not all([create_monthly_trend_chart, create_admissions_discharges_chart, create_occupancy_chart]):
        st.warning("グラフ生成関数の一部が利用できません。")
        return

    # KPIデータはグラフ生成に必要なため再計算 (キャッシュが効くはず)
    kpi_data = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)

    if kpi_data is None or kpi_data.get("error"):
        st.warning(f"グラフ表示用のKPIデータ計算に失敗しました。")
        return

    # --- 時系列チャート ---
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

    # --- 病床利用率チャート（全幅） ---
    st.markdown("<div class='chart-container full-width'>", unsafe_allow_html=True)
    st.markdown(f"<div class='chart-title'>月別 病床利用率の推移 (総病床数: {total_beds_setting}床)</div>", unsafe_allow_html=True)
    occupancy_chart_fig = create_occupancy_chart(kpi_data, total_beds_setting, target_occupancy_setting_percent) # %で渡す
    if occupancy_chart_fig:
        st.plotly_chart(occupancy_chart_fig, use_container_width=True)
    else:
        st.info("病床利用率チャート: データ不足または総病床数未設定のため表示できません。")
    st.markdown("</div>", unsafe_allow_html=True)

    # --- 分析インサイト ---
    display_insights(kpi_data, total_beds_setting)


def display_insights(kpi_data, total_beds_setting):
    """分析インサイトを表示する関数"""
    # ... (既存のコードをそのまま使用) ...
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


# display_dashboard_overview は app.py から直接 display_kpi_cards_only や display_trend_graphs_only を呼び出すため、
# このファイル内での display_dashboard_overview は不要になるか、あるいは app.py の create_management_dashboard_tab の
# ロジックをこちらに集約する形も考えられます。
# 今回は app.py 側で制御するため、ここでは display_dashboard_overview はコメントアウトまたは削除します。
# def display_dashboard_overview(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent):
#     """ダッシュボード概要タブの内容を表示するメイン関数"""
#     display_kpi_cards_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent)
#     st.markdown("---")
#     display_trend_graphs_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent)


def get_color_from_status_string(status_string):
    """KPIステータス文字列に基づいて色コードを返します。"""
    if status_string == "good":
        return "#2ecc71"  # 緑
    elif status_string == "warning":
        return "#f39c12"  # オレンジ
    elif status_string == "alert":
        return "#e74c3c"  # 赤
    elif status_string == "neutral":
        return "#7f8c8d"  # 濃いグレー
    else:
        return "#BDC3C7"  # 薄いグレー

def display_kpi_card(title, value, subtitle, status_string="neutral"):
    """個別のKPIカードをHTMLで表示します。"""
    color = get_color_from_status_string(status_string)
    
    card_html = f"""
    <div style="
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 5px solid {color};
        margin-bottom: 1rem;
        height: 130px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        overflow: hidden;
    ">
        <h4 style="margin: 0 0 0.3rem 0; font-size: 0.95em; color: #555; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{title}">{title}</h4>
        <h2 style="margin: 0.1rem 0 0.3rem 0; color: #333; font-size: 1.7em; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{value}">{value}</h2>
        <p style="margin: 0; font-size: 0.85em; color: {color}; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{subtitle}">{subtitle}</p>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

def display_kpi_cards_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting):
    """KPIカードのみを表示する関数"""
    
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    
    if calculate_kpis is None:
        st.error("KPI計算関数が利用できません。")
        return

    kpi_data = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)
    
    if kpi_data is None or kpi_data.get("error"):
        st.warning(f"選択された期間のKPI計算に失敗しました。理由: {kpi_data.get('error', '不明') if kpi_data else '不明'}")
        return
    
    # --- KPIカード表示 ---
    st.markdown("<div class='kpi-container'>", unsafe_allow_html=True)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        # 平均在院日数 (ALOS)
        if "alos" in kpi_data and "alos_mom_change" in kpi_data and get_kpi_status:
            alos_status = get_kpi_status(kpi_data["alos"], 14, 18, reverse=True)
            alos_trend_icon = "↓" if kpi_data["alos_mom_change"] < 0 else ("↑" if kpi_data["alos_mom_change"] > 0 else "→")
            alos_trend_text = f"{alos_trend_icon} {abs(kpi_data['alos_mom_change']):.1f}% 前月比"
            display_kpi_card("平均在院日数", f"{kpi_data['alos']:.1f} 日", 
                           alos_trend_text if kpi_data.get("alos_mom_change", 0) != 0 else "前月と変動なし", 
                           alos_status)

    with col2:
        # 日平均在院患者数
        if "avg_daily_census" in kpi_data and "total_patient_days" in kpi_data:
            display_kpi_card("日平均在院患者数", f"{kpi_data['avg_daily_census']:.1f} 人", 
                           f"期間延べ: {kpi_data['total_patient_days']:,.0f} 人日", 
                           "neutral")

    with col3:
        # 病床利用率
        if "bed_occupancy_rate" in kpi_data and kpi_data["bed_occupancy_rate"] is not None and get_kpi_status:
            occupancy_status = get_kpi_status(kpi_data["bed_occupancy_rate"], 
                                            target_occupancy_setting + 5, 
                                            target_occupancy_setting - 5)
            display_kpi_card("病床利用率", f"{kpi_data['bed_occupancy_rate']:.1f}%", 
                           f"目標: {target_occupancy_setting:.0f}%", 
                           occupancy_status)
    
    with col4:
        # 病床回転数
        if "turnover_rate" in kpi_data and "days_count" in kpi_data and get_kpi_status:
            turnover_status = get_kpi_status(kpi_data["turnover_rate"], 1.0, 0.7)
            display_kpi_card("病床回転数 (期間)", f"{kpi_data['turnover_rate']:.2f} 回転", 
                           f"{kpi_data['days_count']} 日間実績", 
                           turnover_status)

    with col5:
        # 緊急入院比率
        if "emergency_admission_rate" in kpi_data and "total_admissions" in kpi_data and get_kpi_status:
            emergency_status = get_kpi_status(kpi_data["emergency_admission_rate"], 15, 25, reverse=True)
            display_kpi_card("緊急入院比率", f"{kpi_data['emergency_admission_rate']:.1f}%", 
                           f"全入院 {kpi_data['total_admissions']:.0f} 人中", 
                           emergency_status)
    
    st.markdown("</div>", unsafe_allow_html=True)

def display_trend_graphs_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting):
    """トレンドグラフのみを表示する関数"""
    
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    
    if calculate_kpis is None:
        st.error("KPI計算関数が利用できません。")
        return

    kpi_data = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)
    
    if kpi_data is None or kpi_data.get("error"):
        st.warning(f"グラフ表示用のデータ計算に失敗しました。")
        return
    
    # --- 時系列チャート ---
    col1_chart, col2_chart = st.columns(2)
    
    with col1_chart:
        if create_monthly_trend_chart:
            st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
            st.markdown("<div class='chart-title'>月別 平均在院日数と入退院患者数の推移</div>", unsafe_allow_html=True)
            monthly_chart = create_monthly_trend_chart(kpi_data)
            if monthly_chart: 
                st.plotly_chart(monthly_chart, use_container_width=True)
            else: 
                st.info("月次トレンドチャート: データ不足のため表示できません。")
            st.markdown("</div>", unsafe_allow_html=True)
    
    with col2_chart:
        if create_admissions_discharges_chart:
            st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
            st.markdown("<div class='chart-title'>週別 入退院バランス</div>", unsafe_allow_html=True)
            balance_chart = create_admissions_discharges_chart(kpi_data)
            if balance_chart: 
                st.plotly_chart(balance_chart, use_container_width=True)
            else: 
                st.info("入退院バランスチャート: データ不足のため表示できません。")
            st.markdown("</div>", unsafe_allow_html=True)
            
    # --- 病床利用率チャート（全幅） ---
    if create_occupancy_chart:
        st.markdown("<div class='chart-container full-width'>", unsafe_allow_html=True)
        st.markdown(f"<div class='chart-title'>月別 病床利用率の推移 (総病床数: {total_beds_setting}床)</div>", unsafe_allow_html=True)
        occupancy_chart_fig = create_occupancy_chart(kpi_data, total_beds_setting, target_occupancy_setting)
        if occupancy_chart_fig: 
            st.plotly_chart(occupancy_chart_fig, use_container_width=True)
        else: 
            st.info("病床利用率チャート: データ不足または総病床数未設定のため表示できません。")
        st.markdown("</div>", unsafe_allow_html=True)
    
    # --- 分析インサイト ---
    display_insights(kpi_data, total_beds_setting)

def display_insights(kpi_data, total_beds_setting):
    """分析インサイトを表示する関数"""
    if analyze_kpi_insights and kpi_data:
        insights = analyze_kpi_insights(kpi_data, total_beds_setting)
        
        st.markdown("<div class='chart-container full-width'>", unsafe_allow_html=True)
        st.markdown("<div class='chart-title'>分析インサイトと考慮事項</div>", unsafe_allow_html=True)
        insight_col1, insight_col2 = st.columns(2)
        
        with insight_col1:
            if insights.get("alos"):
                st.markdown("<div class='info-card'><h4>平均在院日数 (ALOS) に関する考察</h4>" + 
                          "".join([f"<p>- {i}</p>" for i in insights["alos"]]) + "</div>", 
                          unsafe_allow_html=True)
            if insights.get("weekday_pattern"):
                st.markdown("<div class='neutral-card'><h4>曜日別パターンの活用</h4>" + 
                          "".join([f"<p>- {i}</p>" for i in insights["weekday_pattern"]]) + "</div>", 
                          unsafe_allow_html=True)
        
        with insight_col2:
            if insights.get("occupancy"):
                st.markdown("<div class='success-card'><h4>病床利用率と回転数</h4>" + 
                          "".join([f"<p>- {i}</p>" for i in insights["occupancy"]]) + "</div>", 
                          unsafe_allow_html=True)
            if insights.get("general"):
                st.markdown("<div class='warning-card'><h4>データ解釈上の注意点</h4>" + 
                          "".join([f"<p>- {i}</p>" for i in insights["general"]]) + "</div>", 
                          unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("インサイトを生成するためのデータまたは関数が不足しています。")

def display_dashboard_overview(df, start_date, end_date, total_beds_setting, target_occupancy_setting):
    """ダッシュボード概要タブの内容を表示するメイン関数"""
    
    if df is None or df.empty:
        st.warning("データが読み込まれていません。「データ処理」タブを実行してください。")
        return
    
    if calculate_kpis is None:
        st.error("KPI計算関数が利用できません。")
        return

    # KPIカード表示
    display_kpi_cards_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting)
    
    # 区切り線
    st.markdown("---")
    
    # トレンドグラフ表示
    display_trend_graphs_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting)