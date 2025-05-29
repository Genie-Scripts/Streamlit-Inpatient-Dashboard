import streamlit as st

def inject_global_css(font_scale=1.0):
    """
    アプリ全体のフォントサイズとフォントファミリ、テーブルや画像等の基本カスタムCSSを一括適用します。
    font_scale: 倍率（既定値1.5＝5割増し）
    """
    base_px = 16  # ブラウザ標準の基本フォントサイズ
    font_px = int(base_px * font_scale)
    header_px = int(font_px * 1.0)
    
    # ===== サイドバー目標値サマリー用のフォントサイズ設定 =====
    sidebar_target_label_px = int(font_px * 0.8)    # ラベル: 基本サイズの80% (12.8px)
    sidebar_target_value_px = int(font_px * 1.1)    # 値: 基本サイズの110% (17.6px)
    sidebar_target_delta_px = int(font_px * 0.7)    # デルタ: 基本サイズの70% (11.2px)
    
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"] {{
            font-size: {font_px}px !important;
            font-family: 'Arial', 'Noto Sans JP', sans-serif !important;
        }}
        .stApp {{
            font-size: {font_px}px !important;
        }}
        h1, h2, h3, h4, h5, h6 {{
            font-size: {header_px}px !important;
        }}
        /* DataFrameやTableウィジェットのフォントサイズ調整 */
        .stMarkdown p,
        .stDataFrame,
        .stTable,
        .stSelectbox,
        .stButton,
        .stTextInput,
        .stSlider,
        .stRadio,
        .stCheckbox,
        .stNumberInput,
        .stDateInput,
        .stTextArea,
        .stFileUploader,
        .stExpander,
        .stTabs,
        .stMetric {{
            font-size: {font_px}px !important;
        }}
        /* サイドバー等にも適用 */
        section[data-testid="stSidebar"] * {{
            font-size: {font_px}px !important;
        }}
        
        /* ===== サイドバー目標値サマリーの専用フォント設定 ===== */
        /* sidebar-target-summary-metricsクラス内のメトリクス */
        .sidebar-target-summary-metrics [data-testid="stMetricLabel"] {{
            font-size: {sidebar_target_label_px}px !important;
            font-weight: 600 !important;
            color: #262730 !important;
            margin-bottom: 2px !important;
            line-height: 1.2 !important;
        }}
        
        .sidebar-target-summary-metrics [data-testid="stMetricValue"] {{
            font-size: {sidebar_target_value_px}px !important;
            font-weight: 700 !important;
            color: #262730 !important;
            line-height: 1.3 !important;
            margin-bottom: 1px !important;
        }}
        
        .sidebar-target-summary-metrics [data-testid="stMetricDelta"] {{
            font-size: {sidebar_target_delta_px}px !important;
            font-weight: 500 !important;
            margin-top: 1px !important;
        }}
        
        /* より具体的なセレクターでの追加調整 */
        section[data-testid="stSidebar"] .sidebar-target-summary-metrics div[data-testid="stMetric"] label[data-testid="stMetricLabel"] {{
            font-size: {sidebar_target_label_px}px !important;
            font-weight: 600 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }}
        
        section[data-testid="stSidebar"] .sidebar-target-summary-metrics div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
            font-size: {sidebar_target_value_px}px !important;
            font-weight: 700 !important;
            line-height: 1.3 !important;
        }}
        
        section[data-testid="stSidebar"] .sidebar-target-summary-metrics div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {{
            font-size: {sidebar_target_delta_px}px !important;
            font-weight: 500 !important;
        }}
        
        /* ブロックコンテナ余白調整（必要に応じて） */
        .block-container {{
            max-width: 100% !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }}
        /* 独自HTMLテーブル（styled-tableクラス利用時） */
        .styled-table {{
            font-size: {2*font_px}px;
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }}
        .styled-table th, .styled-table td {{
            padding: 14px 24px;
            border: 1px solid #ccc;
            text-align: center;
        }}
        /* DataFrame幅を100%に */
        .stDataFrame {{
            width: 100%;
        }}
        /* 画像表示最大幅調整 */
        .stImage > img {{
            max-width: 100%;
            height: auto;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )