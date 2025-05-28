# dashboard_overview_tab.py

import streamlit as st
import pandas as pd
# import plotly.graph_objects as go # 必要に応じて
# from plotly.subplots import make_subplots # 必要に応じて
# import plotly.express as px # 必要に応じて
from datetime import datetime
# import locale # 必要に応じて

# --- dashboard_charts.py からグラフ関数をインポート ---
try:
    from dashboard_charts import (
        create_monthly_trend_chart,
        create_admissions_discharges_chart,
        create_occupancy_chart
    )
except ImportError:
    st.error("dashboard_charts.py が見つからないか、必要な関数が定義されていません。")
    # フォールバックとしてダミー関数を定義するか、エラーで停止
    create_monthly_trend_chart = None
    create_admissions_discharges_chart = None
    create_occupancy_chart = None

# --- kpi_calculator.py からKPI計算関数をインポート ---
try:
    from kpi_calculator import calculate_kpis, analyze_kpi_insights # 開発プランに沿って
except ImportError:
    st.error("kpi_calculator.py が見つからないか、必要な関数が定義されていません。")
    calculate_kpis = None
    analyze_kpi_insights = None

def get_color_from_status_string(status_string):
    """KPIステータス文字列に基づいて色コードを返します。"""
    if status_string == "good":
        return "#2ecc71"  # 緑
    elif status_string == "warning":
        return "#f39c12"  # オレンジ
    elif status_string == "alert":
        return "#e74c3c"  # 赤
    elif status_string == "neutral": # "neutral" ステータス（色付けなしなど）の場合
        return "#7f8c8d"     # 濃いグレー (デフォルト色の一つとして)
    else: # 未定義のステータスやその他の場合
        return "#BDC3C7"     # 薄いグレー (汎用的なデフォルト色)

def display_kpi_card(title, value, subtitle, status_string):
    """個別のKPIカードをHTMLで表示します。"""
    color = get_color_from_status_string(status_string)
    
    # カードのHTMLコンテンツ
    # スタイルは app.py の .kpi-card や revenue_dashboard_tab.py のカード を参考に調整
    card_html = f"""
    <div style="
        background-color: white;
        padding: 1rem; /* app.py の .kpi-card は 1.5rem ですが、ここでは1remに */
        border-radius: 10px; /* app.py の .kpi-card と同様 */
        box-shadow: 0 2px 4px rgba(0,0,0,0.1); /* app.py の .kpi-card と同様 */
        border-left: 5px solid {color}; /* 色と太さを変更 */
        margin-bottom: 1rem; /* app.py の .kpi-card と同様 */
        height: 130px; /* 高さを固定してカードの見た目を揃える */
        display: flex;
        flex-direction: column;
        justify-content: center;
        overflow: hidden; /* 内容がはみ出した場合に隠す */
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
    
    # 平均在院日数 (ALOS)
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        if "alos" in kpi_data and "alos_mom_change" in kpi_data:
            from kpi_calculator import get_kpi_status
            alos_status = get_kpi_status(kpi_data["alos"], 14, 18, reverse=True)
            alos_trend_icon = "↓" if kpi_data["alos_mom_change"] < 0 else ("↑" if kpi_data["alos_mom_change"] > 0 else "→")
            alos_trend_text = f"{alos_trend_icon} {abs(kpi_data['alos_mom_change']):.1f}% 前月比"
            display_kpi_card("平均在院日数", f"{kpi_data['alos']:.1f} 日", 
                           alos_trend_text if kpi_data["alos_mom_change"] != 0 else "前月と変動なし", 
                           alos_status)

    with col2: # ★修正箇所★
        if "avg_daily_census" in kpi_data and "total_patient_days" in kpi_data: #
            display_kpi_card("日平均在院患者数", f"{kpi_data['avg_daily_census']:.1f} 人", 
                           f"期間延べ: {kpi_data['total_patient_days']:,.0f} 人日", # subtitle
                           "neutral") # status_string として "neutral" を追加

    with col3:
        if "bed_occupancy_rate" in kpi_data and kpi_data["bed_occupancy_rate"] is not None: #
            from kpi_calculator import get_kpi_status #
            # target_occupancy_setting は % 値 (例: 85) と想定される
            # app.py で total_beds と target_occupancy が display_overview_dashboard_modified に渡され、
            # それが display_kpi_cards_only に渡される。
            # kpi_calculator.get_kpi_status の閾値も % 値で与える。
            occupancy_status = get_kpi_status(kpi_data["bed_occupancy_rate"], 
                                            target_occupancy_setting + 5, 
                                            target_occupancy_setting - 5) #
            display_kpi_card("病床利用率", f"{kpi_data['bed_occupancy_rate']:.1f}%", 
                           f"目標: {target_occupancy_setting:.0f}%", # 目標値を表示
                           occupancy_status) #
    
    with col4:
        if "turnover_rate" in kpi_data and "days_count" in kpi_data: #
            from kpi_calculator import get_kpi_status #
            turnover_status = get_kpi_status(kpi_data["turnover_rate"], 1.0, 0.7) #
            display_kpi_card("病床回転数 (期間)", f"{kpi_data['turnover_rate']:.2f} 回転", 
                           f"{kpi_data['days_count']} 日間実績", 
                           turnover_status) #

    with col5:
        if "emergency_admission_rate" in kpi_data and "total_admissions" in kpi_data: #
            from kpi_calculator import get_kpi_status #
            emergency_status = get_kpi_status(kpi_data["emergency_admission_rate"], 15, 25, reverse=True) #
            display_kpi_card("緊急入院比率", f"{kpi_data['emergency_admission_rate']:.1f}%", 
                           f"全入院 {kpi_data['total_admissions']:.0f} 人中", 
                           emergency_status) #
    
    st.markdown("</div>", unsafe_allow_html=True) #

def display_trend_graphs_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting):
    """トレンドグラフのみを表示する関数"""
    
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    
    if calculate_kpis is None:
        st.error("KPI計算関数が利用できません。")
        return

    # 長期間データでKPIを再計算
    kpi_data = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)
    
    if kpi_data is None or kpi_data.get("error"):
        st.warning(f"グラフ表示用のデータ計算に失敗しました。")
        return
    
    # --- 時系列チャート ---
    col1_chart, col2_chart = st.columns(2)
    
    with col1_chart:
        if create_monthly_trend_chart:
            st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
            # タイトルはHTMLで表示済みなので、チャート関数側では表示しない
            monthly_chart = create_monthly_trend_chart(kpi_data)
            if monthly_chart: 
                st.plotly_chart(monthly_chart, use_container_width=True)
            else: 
                st.info("月次トレンドチャート: データ不足のため表示できません。")
            st.markdown("</div>", unsafe_allow_html=True)
    
    with col2_chart:
        if create_admissions_discharges_chart:
            st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
            balance_chart = create_admissions_discharges_chart(kpi_data)
            if balance_chart: 
                st.plotly_chart(balance_chart, use_container_width=True)
            else: 
                st.info("入退院バランスチャート: データ不足のため表示できません。")
            st.markdown("</div>", unsafe_allow_html=True)
            
    # --- 病床利用率チャート（全幅） ---
    if create_occupancy_chart:
        st.markdown("<div class='chart-container full-width'>", unsafe_allow_html=True)
        occupancy_chart_fig = create_occupancy_chart(kpi_data, total_beds_setting, target_occupancy_setting)
        if occupancy_chart_fig: 
            st.plotly_chart(occupancy_chart_fig, use_container_width=True)
        else: 
            st.info("病床利用率チャート: データ不足または総病床数未設定のため表示できません。")
        st.markdown("</div>", unsafe_allow_html=True)
    
    # --- 分析インサイト（長期データに基づく） ---
    display_insights(kpi_data, total_beds_setting)

# 既存の display_dashboard_overview 関数は残しておく（後方互換性のため）
def display_dashboard_overview(df, start_date, end_date, total_beds_setting, target_occupancy_setting):
    """既存の統合版関数（後方互換性のため残す）"""
    # KPIカードとグラフを同じデータで表示
    display_kpi_cards_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting)
    st.markdown("---")
    display_trend_graphs_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting)

def get_status(value, good_threshold, warning_threshold, reverse=False): # 仮の関数
    # kpi_calculator.py に get_kpi_status があるので、そちらを使うべき
    # from kpi_calculator import get_kpi_status
    # ここではダミー実装
    if reverse:
        if value < good_threshold: return "status-good"
        if value < warning_threshold: return "status-warning"
        return "status-alert"
    else:
        if value > good_threshold: return "status-good"
        if value > warning_threshold: return "status-warning"
        return "status-alert"

# display_insights 関数の定義 (もし dashboard_overview_tab.py 内にある場合)
def display_insights(kpi_data, total_beds_setting): # 仮の引数とtotal_beds_setting追加
    # analyze_kpi_insights を kpi_calculator からインポートして使用
    if analyze_kpi_insights and kpi_data:
        insights = analyze_kpi_insights(kpi_data, total_beds_setting) # total_beds を渡す
        
        st.markdown("<div class='chart-container full-width'>", unsafe_allow_html=True)
        st.markdown("<div class='chart-title'>分析インサイトと考慮事項</div>", unsafe_allow_html=True)
        insight_col1, insight_col2 = st.columns(2)
        with insight_col1:
            if insights["alos"]:
                st.markdown("<div class='info-card'><h4>平均在院日数 (ALOS) に関する考察</h4>" + "".join([f"<p>- {i}</p>" for i in insights["alos"]]) + "</div>", unsafe_allow_html=True)
            if insights["weekday_pattern"]:
                 st.markdown("<div class='neutral-card'><h4>曜日別パターンの活用</h4>" + "".join([f"<p>- {i}</p>" for i in insights["weekday_pattern"]]) + "</div>", unsafe_allow_html=True)
        with insight_col2:
            if insights["occupancy"]:
                st.markdown("<div class='success-card'><h4>病床利用率と回転数</h4>" + "".join([f"<p>- {i}</p>" for i in insights["occupancy"]]) + "</div>", unsafe_allow_html=True)
            if insights["general"]:
                 st.markdown("<div class='warning-card'><h4>データ解釈上の注意点</h4>" + "".join([f"<p>- {i}</p>" for i in insights["general"]]) + "</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("インサイトを生成するためのデータまたは関数が不足しています。")


# メインの表示関数 display_dashboard_overview (app.py から呼び出される想定)
def display_dashboard_overview(df, start_date, end_date, total_beds_setting, target_occupancy_setting):
    """ダッシュボード概要タブの内容を表示する関数"""
    
    if df is None or df.empty:
        st.warning("データが読み込まれていません。「データ処理」タブを実行してください。")
        return
    if calculate_kpis is None:
        st.error("KPI計算関数が利用できません。")
        return

    kpi_data = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting) # total_beds を渡す
    
    if kpi_data is None or kpi_data.get("error"):
        st.warning(f"選択された期間のKPI計算に失敗しました。理由: {kpi_data.get('error', '不明') if kpi_data else '不明'}")
        return
    
    # --- KPIカード表示 ---
    st.markdown("<div class='kpi-container'>", unsafe_allow_html=True)
    
    # 平均在院日数 (ALOS)
    if "alos" in kpi_data and "alos_mom_change" in kpi_data:
        # get_kpi_status は kpi_calculator.py からインポート想定
        from kpi_calculator import get_kpi_status as get_kpi_status_actual
        alos_status = get_kpi_status_actual(kpi_data["alos"], 14, 18, reverse=True) # 例: 14日未満が良好
        alos_trend_icon = "↓" if kpi_data["alos_mom_change"] < 0 else ("↑" if kpi_data["alos_mom_change"] > 0 else "→")
        alos_trend_text = f"{alos_trend_icon} {abs(kpi_data['alos_mom_change']):.1f}% 前月比"
        display_kpi_card("平均在院日数", f"{kpi_data['alos']:.1f} 日", alos_trend_text if kpi_data["alos_mom_change"] != 0 else "前月と変動なし", alos_status)

    # 日平均在院患者数
    if "avg_daily_census" in kpi_data and "total_patient_days" in kpi_data:
        display_kpi_card("日平均在院患者数", f"{kpi_data['avg_daily_census']:.1f} 人", f"期間延べ: {kpi_data['total_patient_days']:,.0f} 人日")

    # 病床利用率 (calculate_kpis で計算されるように修正が必要)
    if "bed_occupancy_rate" in kpi_data and kpi_data["bed_occupancy_rate"] is not None:
        from kpi_calculator import get_kpi_status as get_kpi_status_actual
        occupancy_status = get_kpi_status_actual(kpi_data["bed_occupancy_rate"], target_occupancy_setting + 5, target_occupancy_setting - 5) # 目標±5%が良いと仮定
        display_kpi_card("病床利用率", f"{kpi_data['bed_occupancy_rate']:.1f}%", f"目標: {target_occupancy_setting}%", occupancy_status)
    
    # 病床回転率
    if "turnover_rate" in kpi_data and "days_count" in kpi_data:
        from kpi_calculator import get_kpi_status as get_kpi_status_actual
        turnover_status = get_kpi_status_actual(kpi_data["turnover_rate"], 1.0, 0.7) # 例: 1.0以上が良い
        display_kpi_card("病床回転数 (期間)", f"{kpi_data['turnover_rate']:.2f} 回転", f"{kpi_data['days_count']} 日間実績", turnover_status)

    # 緊急入院比率
    if "emergency_admission_rate" in kpi_data and "total_admissions" in kpi_data:
        from kpi_calculator import get_kpi_status as get_kpi_status_actual
        emergency_status = get_kpi_status_actual(kpi_data["emergency_admission_rate"], 15, 25, reverse=True) # 例: 15%未満が良い
        display_kpi_card("緊急入院比率", f"{kpi_data['emergency_admission_rate']:.1f}%", f"全入院 {kpi_data['total_admissions']:.0f} 人中", emergency_status)
    
    st.markdown("</div>", unsafe_allow_html=True) # KPIコンテナここまで
    
    # --- 時系列チャート ---
    col1_chart, col2_chart = st.columns(2)
    with col1_chart:
        if create_monthly_trend_chart:
            st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
            st.markdown("<div class='chart-title'>月別 平均在院日数と入退院患者数の推移</div>", unsafe_allow_html=True)
            monthly_chart = create_monthly_trend_chart(kpi_data) # ★★★ ここで呼び出し ★★★
            if monthly_chart: st.plotly_chart(monthly_chart, use_container_width=True)
            else: st.info("月次トレンドチャート: データ不足のため表示できません。")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.warning("月次トレンドチャート関数が利用できません。")
    
    with col2_chart:
        if create_admissions_discharges_chart:
            st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
            st.markdown("<div class='chart-title'>週別 入退院バランス</div>", unsafe_allow_html=True)
            balance_chart = create_admissions_discharges_chart(kpi_data)
            if balance_chart: st.plotly_chart(balance_chart, use_container_width=True)
            else: st.info("入退院バランスチャート: データ不足のため表示できません。")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.warning("入退院バランスチャート関数が利用できません。")
            
    # --- 病床利用率チャート ---
    if create_occupancy_chart:
        st.markdown("<div class='chart-container full-width'>", unsafe_allow_html=True)
        st.markdown(f"<div class='chart-title'>月別 病床利用率の推移 (総病床数: {total_beds_setting}床)</div>", unsafe_allow_html=True)
        occupancy_chart_fig = create_occupancy_chart(kpi_data, total_beds_setting, target_occupancy_setting)
        if occupancy_chart_fig: st.plotly_chart(occupancy_chart_fig, use_container_width=True)
        else: st.info("病床利用率チャート: データ不足または総病床数未設定のため表示できません。")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.warning("病床利用率チャート関数が利用できません。")
    
    # --- 分析インサイト ---
    display_insights(kpi_data, total_beds_setting)


# このファイルが直接実行された場合の処理 (テスト用など、通常はapp.pyから呼び出される)
# if __name__ == "__main__":
#     # テスト用のダミーデータやst.session_stateの設定
#     # st.session_state.df = pd.DataFrame(...) # ダミーデータ
#     # st.session_state.data_processed = True
#     # st.session_state.sidebar_start_date = datetime.now().date() - timedelta(days=365)
#     # st.session_state.sidebar_end_date = datetime.now().date()
#     # st.session_state.total_beds_input = 200
#     # st.session_state.target_occupancy_input = 85

#     # if 'df' in st.session_state and st.session_state.df is not None:
#     #     display_dashboard_overview(
#     #         st.session_state.df,
#     #         st.session_state.sidebar_start_date,
#     #         st.session_state.sidebar_end_date,
#     #         st.session_state.total_beds_input,
#     #         st.session_state.target_occupancy_input
#     #     )
#     # else:
#     #     st.info("テスト実行: データがありません。")
#     pass # app.py から呼び出されることを前提とするため、直接実行時の処理は省略または簡易化