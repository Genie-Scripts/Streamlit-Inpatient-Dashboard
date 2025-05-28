# dashboard_overview_tab.py

import streamlit as st
import pandas as pd
from datetime import datetime

# --- dashboard_charts.py からグラフ関数をインポート ---
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

# --- kpi_calculator.py からKPI計算関数をインポート ---
try:
    from kpi_calculator import calculate_kpis, analyze_kpi_insights, get_kpi_status
except ImportError:
    st.error("kpi_calculator.py が見つからないか、必要な関数が定義されていません。")
    calculate_kpis = None
    analyze_kpi_insights = None
    get_kpi_status = None

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