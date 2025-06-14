# html_card_test_streamlitcloud.py

import streamlit as st

st.set_page_config(page_title="HTML＋CSSカードテスト", layout="centered")

# --- CSS定義 ---
st.markdown("""
<style>
.card {
    background-color: #f8f9fa;
    border-left: 6px solid #007bff;
    border-radius: 12px;
    padding: 20px;
    margin: 20px 0;
    box-shadow: 0 4px 8px rgba(0,0,0,0.08);
}
.card-title {
    font-size: 1.3em;
    font-weight: bold;
    color: #2c3e50;
    margin-bottom: 10px;
}
.metric-block {
    margin: 10px 0;
}
.metric-label {
    font-size: 0.9em;
    color: #6c757d;
}
.metric-value {
    font-size: 2.0em;
    font-weight: bold;
    color: #007bff;
}
</style>
""", unsafe_allow_html=True)

# --- HTMLカード表示 ---
st.markdown("""
<div class="card">
    <div class="card-title">🏥 総合内科</div>
    <div class="metric-block">
        <div class="metric-label">日平均在院患者数</div>
        <div class="metric-value">41.7</div>
    </div>
    <div class="metric-block">
        <div class="metric-label">週間新入院患者数</div>
        <div class="metric-value">133</div>
    </div>
    <div class="metric-block">
        <div class="metric-label">平均在院日数</div>
        <div class="metric-value">10.2日</div>
    </div>
</div>
""", unsafe_allow_html=True)

# 補足説明
st.info("このカードがスタイル付きで表示されていれば、Streamlit Cloudで `unsafe_allow_html=True` + CSS が正常に機能しています。")
