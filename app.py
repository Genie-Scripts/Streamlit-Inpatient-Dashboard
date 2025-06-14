
# department_performance_debug.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# ダミーCSS（ステップ1）
def inject_test_css():
    st.markdown("""
    <style>
    .dept-performance-card {
        background-color: #f8f9fa;
        border-left: 6px solid #007bff;
        border-radius: 12px;
        padding: 20px;
        margin: 20px 0;
        box-shadow: 0 4px 8px rgba(0,0,0,0.08);
    }
    .metric-label { color: #6c757d; font-size: 0.9em; }
    .metric-value { color: #007bff; font-size: 2em; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# ダミーKPI計算（ステップ2, 3）
def create_dummy_kpi(dept_name):
    return {
        'dept_name': dept_name,
        'avg_daily_census': 42.3,
        'weekly_admissions': 133,
        'alos': 10.2,
        'latest_week_census': 41.5,
        'latest_week_admissions': 128,
        'latest_week_alos': 10.0,
        'target_daily_census': 40.0,
        'target_weekly_admissions': 120,
        'census_achievement': 105.8,
        'admissions_achievement': 110.8,
        'total_days': 28,
        'data_count': 28
    }

# カードHTML生成（ステップ3）
def create_department_card_html(kpi_data):
    return f"""
    <div class="dept-performance-card">
        <div style="font-weight:bold; font-size:1.2em;">🏥 {kpi_data['dept_name']}</div>
        <div class="metric-label">日平均在院患者数</div>
        <div class="metric-value">{kpi_data['avg_daily_census']:.1f}</div>
        <div class="metric-label">週間新入院患者数</div>
        <div class="metric-value">{kpi_data['weekly_admissions']}</div>
        <div class="metric-label">平均在院日数</div>
        <div class="metric-value">{kpi_data['alos']:.1f}日</div>
    </div>
    """

# ===== メイン処理 =====
st.set_page_config(page_title="診療科カード表示テスト", layout="wide")
st.title("🏥 診療科メトリクスカード 表示デバッグ")

# ステップ1：CSS注入
inject_test_css()
st.success("✅ CSSインジェクション済（ステップ1）")

# ステップ2：診療科一覧作成
departments = ["総合内科", "整形外科", "小児科"]
dept_kpis = [create_dummy_kpi(name) for name in departments]

st.info(f"診療科一覧（ステップ2）: {departments}")
st.info(f"KPI生成件数: {len(dept_kpis)}")

# ステップ3＋4：カードHTMLを確認表示
st.subheader("📋 KPIカード表示（ステップ3〜4）")
for kpi in dept_kpis:
    card_html = create_department_card_html(kpi)
    st.markdown(card_html, unsafe_allow_html=True)
    st.markdown("---")
    st.code(card_html, language='html')  # HTML表示内容を確認（ステップ3）

# ステップ5：データフィルター想定チェック
df = pd.DataFrame({
    "診療科名": departments * 10,
    "日付": pd.date_range(end=datetime.today(), periods=30).tolist() * len(departments),
    "入院患者数（在院）": [40 + i % 5 for i in range(90)],
    "総入院患者数": [5 + (i % 3) for i in range(90)],
    "総退院患者数": [4 + (i % 2) for i in range(90)]
})
st.write("📊 データ件数（ステップ5フィルター確認用）:", df.shape)
