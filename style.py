import streamlit as st

def inject_global_css(font_scale=1.5):
    """
    アプリ全体のフォントサイズとフォントファミリ、テーブルや画像等の基本カスタムCSSを一括適用します。
    font_scale: 倍率（既定値1.5＝5割増し）
    """
    base_px = 16  # ブラウザ標準の基本フォントサイズ
    font_px = int(base_px * font_scale)
    header_px = int(font_px * 1.0)
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

# def apply_custom_style():
    # """アプリケーションのカスタムCSSスタイルを適用する"""
    # st.markdown("""
        # <style>
            # html, body {
                # font-family: 'Arial', 'Noto Sans JP', sans-serif !important;
            # }

            # .block-container {
                # max-width: 100% !important;
                # padding-left: 2rem !important;
                # padding-right: 2rem !important;
            # }

            # .styled-table {
                # font-size: 32px;
                # width: 100%;
                # border-collapse: collapse;
                # margin-top: 1rem;
            # }

            # .styled-table th, .styled-table td {
                # padding: 14px 24px;
                # border: 1px solid #ccc;
                # text-align: center;
            # }
            
            # .stDataFrame {
                # width: 100%;
            # }
            
            # /* グラフ表示の調整 */
            # .stImage > img {
                # max-width: 100%;
                # height: auto;
            # }
        # </style>
    # """, unsafe_allow_html=True)

# ダークモード関連の関数は削除しました