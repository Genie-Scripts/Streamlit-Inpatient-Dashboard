import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
try:
    import jpholiday
    JPHOLIDAY_AVAILABLE = True
except ImportError:
    JPHOLIDAY_AVAILABLE = False
import io
import zipfile
import tempfile
import os

# ページ設定
st.set_page_config(
    page_title="入退院分析ダッシュボード",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS
st.markdown("""
<style>
    /* 全体的なフォントサイズの拡大 */
    .stApp {
        font-size: 18px !important;  /* デフォルト14pxから18pxに（約30%増） */
        line-height: 1.6 !important;
    }

    /* メインコンテンツエリア */
    .main .block-container {
        font-size: 18px !important;
        padding-top: 2rem !important;
    }

    /* ヘッダー */
    .main-header {
        font-size: 3.5rem !important;  /* 2.5remから3.5remに（40%増） */
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }

    /* 通常のテキスト */
    .stMarkdown, .stText {
        font-size: 18px !important;
        line-height: 1.6 !important;
    }

    /* サブヘッダー */
    h2, .stMarkdown h2 {
        font-size: 2.2rem !important;  /* 約40%増 */
        margin-bottom: 1rem !important;
    }

    h3, .stMarkdown h3 {
        font-size: 1.8rem !important;  /* 約40%増 */
        margin-bottom: 0.8rem !important;
    }

    h4, .stMarkdown h4 {
        font-size: 1.4rem !important;  /* 約40%増 */
        margin-bottom: 0.6rem !important;
    }

    /* メトリクス (st.metric) の一般的なスタイル */
    /* これが多くのメトリック表示に影響する */
    [data-testid="metric-container"] {
        background-color: white;
        border: 1px solid #e1e5e9;
        padding: 0.8rem 1rem !important; /* パディングを少し調整 */
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }

    [data-testid="metric-container"] label[data-testid="stMetricLabel"] { /* st.metric のラベル */
        font-size: 0.7rem !important; /* 1.0rem → 0.7rem に変更 */
        font-weight: 600 !important;
        color: #262730 !important;
        margin-bottom: 0.1rem !important; /* 値との間隔を調整 */
    }

    [data-testid="metric-container"] div[data-testid="stMetricValue"] { /* st.metric の値 */
        font-size: 1.0rem !important; /* 2.2rem → 1.0rem に変更 */
        font-weight: 600 !important;
        color: #262730 !important;
        line-height: 1.2 !important;
    }

    [data-testid="metric-container"] div[data-testid="stMetricDelta"] { /* st.metric のデルタ */
        font-size: 0.9rem !important; /* やや大きめ */
        margin-top: 0.1rem !important;
    }

    /* KPIカードの一般的なスタイル (dashboard_overview_tab.py などで使われるカスタムHTMLカード用) */
    .kpi-card {
        background-color: white;
        padding: 1.5rem !important;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid #1f77b4;
        margin-bottom: 1rem;
        font-size: 18px !important;
    }

    .kpi-card h2 {
        font-size: 2.2rem !important;
        margin: 0.5rem 0 !important;
    }

    .kpi-card h4 {
        font-size: 1.2rem !important;
        margin: 0 !important;
    }

    .kpi-card p {
        font-size: 1rem !important;
        margin: 0 !important;
    }

    /* チャートコンテナ */
    .chart-container {
        background-color: white;
        padding: 1.5rem !important;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
        font-size: 18px !important;
    }

    /* サイドバー全体 */
    /* .css-1d391kg はStreamlitのバージョンで変わりうるため、より安定な [data-testid="stSidebar"] を推奨 */
    [data-testid="stSidebar"] {
        font-size: 16px !important;
    }

    /* サイドバー内のウィジェットラベル */
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stNumberInput label,
    [data-testid="stSidebar"] .stSlider label,
    [data-testid="stSidebar"] .stDateInput label {
        font-size: 15px !important;
        font-weight: 600 !important;
    }

    /* ボタン */
    .stButton button {
        font-size: 16px !important;
        padding: 0.6rem 1.2rem !important;
        height: auto !important;
        min-height: 44px !important;
    }

    /* タブ */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }

    .stTabs [data-baseweb="tab"] {
        height: auto !important;
        min-height: 3.5rem !important;
        white-space: pre-wrap;
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 0.8rem 1.2rem !important;
        font-size: 16px !important;
        font-weight: 600 !important;
    }

    .stTabs [aria-selected="true"] {
        background-color: #1f77b4;
        color: white;
        font-size: 17px !important;
    }

    /* データフレーム */
    .stDataFrame {
        font-size: 15px !important;
    }

    .stDataFrame table {
        font-size: 15px !important;
    }

    .stDataFrame th {
        font-size: 16px !important;
        font-weight: 600 !important;
        background-color: #f8f9fa !important;
    }

    /* セレクトボックス、入力フィールド */
    .stSelectbox > div > div > div { /* 選択された値の表示部分 */
        font-size: 16px !important;
    }

    .stNumberInput input, /* Streamlit 1.23以降のセレクタ */
    .stTextInput input {
        font-size: 16px !important;
    }
    /* 古いStreamlitバージョンのためのセレクタも残す場合 */
    .stNumberInput > div > div > input,
    .stTextInput > div > div > input {
        font-size: 16px !important;
    }


    /* アラート・情報ボックス */
    .stAlert {
        font-size: 16px !important;
        padding: 1rem 1.2rem !important;
    }

    .stInfo, .stSuccess, .stWarning, .stError {
        font-size: 16px !important;
        padding: 1rem 1.2rem !important;
    }

    /* エクスパンダー */
    .streamlit-expanderHeader {
        font-size: 17px !important;
        font-weight: 600 !important;
    }

    .streamlit-expanderContent {
        font-size: 16px !important;
    }

    /* フッター */
    .stMarkdown div[style*="text-align: center"] {
        font-size: 14px !important;
    }

    /* プロットリーチャート内のテキスト調整 */
    .js-plotly-plot .plotly .modebar {
        font-size: 14px !important;
    }

    /* レスポンシブ対応 */
    @media (max-width: 768px) {
        .stApp {
            font-size: 16px !important;
        }

        .main-header {
            font-size: 2.8rem !important;
        }

        .stTabs [data-baseweb="tab"] {
            font-size: 14px !important;
            padding: 0.6rem 0.8rem !important;
        }
    }

    /* ダークモード対応（オプション） */
    @media (prefers-color-scheme: dark) {
        .kpi-card {
            background-color: #262730 !important;
            color: #fafafa !important;
        }

        .chart-container {
            background-color: #262730 !important;
            color: #fafafa !important;
        }
        [data-testid="metric-container"] {
            background-color: #2E3138 !important;
            border: 1px solid #4A4D55 !important;
        }
        [data-testid="metric-container"] label[data-testid="stMetricLabel"],
        [data-testid="metric-container"] div[data-testid="stMetricValue"],
        [data-testid="metric-container"] div[data-testid="stMetricDelta"] {
            color: #FAFAFA !important;
        }
    }

/* ▼▼▼▼▼ KPIカードと目標値サマリーの数字・タイトル縮小版 ▼▼▼▼▼ */

    /* 経営ダッシュボードタブのKPIカードのフォントサイズ調整 */
    /* (display_kpi_cards 関数内で <div class="management-dashboard-kpi-card"> で囲まれた st.metric を対象) */

    /* 経営ダッシュボードKPIカードの調整（少し小さく） */
    .management-dashboard-kpi-card [data-testid="stMetricValue"] {
        font-size: 0.9rem !important; /* 1.1rem → 0.9rem に縮小 */
        line-height: 1.0 !important;
        padding-top: 1px !important;
        padding-bottom: 1px !important;
        word-break: break-all !important;
        overflow-wrap: break-word !important;
        white-space: normal !important;
    }

    .management-dashboard-kpi-card [data-testid="stMetricLabel"] {
        font-size: 0.55rem !important; /* 0.65rem → 0.55rem に縮小 */
        margin-bottom: -3px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    .management-dashboard-kpi-card [data-testid="stMetricDelta"] {
        font-size: 0.5rem !important; /* 0.6rem → 0.5rem に縮小 */
        margin-top: -3px !important;
        word-break: break-all !important;
        overflow-wrap: break-word !important;
    }

    .management-dashboard-kpi-card .stCaption {
        font-size: 0.45rem !important; /* 0.55rem → 0.45rem に縮小 */
        margin-top: -5px !important;
        line-height: 1.1 !important;
        word-break: break-all !important;
        overflow-wrap: break-word !important;
    }

    /* より具体的なセレクタでの追加調整 */
    div.management-dashboard-kpi-card div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 0.85rem !important; /* 1.0rem → 0.85rem に縮小 */
        line-height: 1.0 !important;
        padding-top: 1px !important;
        padding-bottom: 1px !important;
        word-break: break-all !important;
        overflow-wrap: break-word !important;
        max-width: 100% !important;
    }

    div.management-dashboard-kpi-card div[data-testid="stMetric"] label[data-testid="stMetricLabel"] {
        font-size: 0.5rem !important; /* 0.6rem → 0.5rem に縮小 */
        margin-bottom: -3px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    div.management-dashboard-kpi-card div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {
        font-size: 0.45rem !important; /* 0.55rem → 0.45rem に縮小 */
        margin-top: -3px !important;
        word-break: break-all !important;
        overflow-wrap: break-word !important;
    }

    /* サイドバーの目標値サマリーの調整（少し小さく） */
    [data-testid="stSidebar"] .sidebar-target-summary-metrics [data-testid="stMetricLabel"] {
        font-size: 9px !important; /* 10px → 9px に縮小 */
        font-weight: normal !important;
        margin-bottom: -2px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    [data-testid="stSidebar"] .sidebar-target-summary-metrics [data-testid="stMetricValue"] {
        font-size: 0.75rem !important; /* 0.9rem → 0.75rem に縮小 */
        line-height: 1.0 !important;
        padding-top: 0px !important;
        padding-bottom: 1px !important;
        word-break: break-all !important;
        overflow-wrap: break-word !important;
    }

    [data-testid="stSidebar"] .sidebar-target-summary-metrics [data-testid="stMetricDelta"] {
        font-size: 0.5rem !important; /* 0.6rem → 0.5rem に縮小 */
        margin-top: -2px !important;
        word-break: break-all !important;
    }

    /* より具体的なサイドバー指定 */
    section[data-testid="stSidebar"] div.sidebar-target-summary-metrics div[data-testid="stMetric"] label[data-testid="stMetricLabel"] {
        font-size: 8px !important; /* 9px → 8px に縮小 */
        font-weight: normal !important;
        margin-bottom: -2px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    section[data-testid="stSidebar"] div.sidebar-target-summary-metrics div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 0.7rem !important; /* 0.8rem → 0.7rem に縮小 */
        line-height: 1.0 !important;
        padding-top: 0px !important;
        padding-bottom: 1px !important;
        word-break: break-all !important;
        overflow-wrap: break-word !important;
    }

    section[data-testid="stSidebar"] div.sidebar-target-summary-metrics div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {
        font-size: 0.45rem !important; /* 0.55rem → 0.45rem に縮小 */
        margin-top: -2px !important;
        word-break: break-all !important;
    }

    /* KPIカードコンテナの高さも少し調整 */
    .management-dashboard-kpi-card [data-testid="metric-container"] {
        min-height: 100px !important; /* 120px → 100px に縮小 */
        padding: 0.5rem 0.7rem !important; /* パディングも少し縮小 */
        width: 100% !important;
        overflow: hidden !important;
    }

    /* レスポンシブ対応も調整 */
    @media (max-width: 1400px) {
        .management-dashboard-kpi-card [data-testid="stMetricValue"] {
            font-size: 0.8rem !important; /* さらに縮小 */
        }
        
        .management-dashboard-kpi-card [data-testid="stMetricLabel"] {
            font-size: 0.5rem !important;
        }

        div.management-dashboard-kpi-card div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            font-size: 0.75rem !important;
        }
    }

    @media (max-width: 1200px) {
        .management-dashboard-kpi-card [data-testid="stMetricValue"] {
            font-size: 0.7rem !important;
        }
        
        .management-dashboard-kpi-card [data-testid="stMetricLabel"] {
            font-size: 0.45rem !important;
        }

        div.management-dashboard-kpi-card div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            font-size: 0.65rem !important;
        }

        .management-dashboard-kpi-card [data-testid="metric-container"] {
            min-height: 90px !important;
            padding: 0.4rem 0.6rem !important;
        }
    }

    @media (max-width: 768px) {
        .management-dashboard-kpi-card [data-testid="stMetricValue"] {
            font-size: 0.6rem !important;
        }
        
        .management-dashboard-kpi-card [data-testid="stMetricLabel"] {
            font-size: 0.4rem !important;
        }

        div.management-dashboard-kpi-card div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            font-size: 0.55rem !important;
        }

        .management-dashboard-kpi-card [data-testid="metric-container"] {
            min-height: 80px !important;
            padding: 0.3rem 0.4rem !important;
        }

        /* モバイル時はサイドバーも調整 */
        section[data-testid="stSidebar"] div.sidebar-target-summary-metrics div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            font-size: 0.6rem !important;
        }

        section[data-testid="stSidebar"] div.sidebar-target-summary-metrics div[data-testid="stMetric"] label[data-testid="stMetricLabel"] {
            font-size: 7px !important;
        }
    }

    /* ▲▲▲▲▲ ここまでがKPIカードと目標値サマリーの数字・タイトル縮小版 ▲▲▲▲▲ */

    /* 数値が非常に長い場合の緊急対応 */
    .management-dashboard-kpi-card [data-testid="stMetricValue"]:has-text("000,000") {
        font-size: 0.7rem !important;
        transform: scale(0.8) !important;
        transform-origin: left center !important;
    }

    /* テキストが溢れた場合の最終手段 */
    .management-dashboard-kpi-card [data-testid="metric-container"] {
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    /* ▲▲▲▲▲ ここまでが経営ダッシュボードとサイドバー目標値サマリーの調整（修正版） ▲▲▲▲▲ */

</style>
""", unsafe_allow_html=True)

from concurrent.futures import ThreadPoolExecutor, as_completed
import psutil
import time
from pdf_output_tab import create_pdf_output_tab
from scipy import stats # display_trend_analysis で使用 (pip install scipy が必要)

# カスタムモジュールのインポート
try:
    from integrated_preprocessing import integrated_preprocess_data
    from loader import load_files, read_excel_cached
    from revenue_dashboard_tab import create_revenue_dashboard_section
    from analysis_tabs import create_detailed_analysis_tab, create_data_tables_tab, create_output_prediction_tab
    from data_processing_tab import create_data_processing_tab
    
    # 予測機能のインポート（新規追加）
    from forecast_analysis_tab import display_forecast_analysis_tab
    FORECAST_AVAILABLE = True

except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.error("以下のファイルが存在することを確認してください：")
    st.error("- integrated_preprocessing.py")
    st.error("- loader.py") 
    st.error("- revenue_dashboard_tab.py")
    st.error("- analysis_tabs.py")
    st.error("- data_processing_tab.py")
    st.error("- forecast_analysis_tab.py (予測機能)")  # 追加
    FORECAST_AVAILABLE = False
    st.stop()

# 必要なライブラリの確認と警告
def check_forecast_dependencies():
    """予測機能に必要な依存関係をチェック"""
    missing_libs = []
    
    try:
        import statsmodels
    except ImportError:
        missing_libs.append("statsmodels")
    
    try:
        import pmdarima
    except ImportError:
        missing_libs.append("pmdarima")
    
    try:
        import jpholiday
    except ImportError:
        missing_libs.append("jpholiday")
    
    if missing_libs:
        st.sidebar.warning(
            f"予測機能の完全な動作には以下のライブラリが必要です:\n"
            f"{', '.join(missing_libs)}\n\n"
            f"インストール方法:\n"
            f"```\npip install {' '.join(missing_libs)}\n```"
        )
    
    return len(missing_libs) == 0

def display_trend_analysis(monthly_data):
    """トレンド分析の詳細表示"""
    try:
        st.subheader("📊 トレンド分析") # ここでサブヘッダーを追加
        if monthly_data.empty or len(monthly_data) < 2:
            st.info("トレンド分析には2期間以上の月次データが必要です。")
            return

        y_col = '日平均在院患者数'
        if y_col not in monthly_data.columns:
            st.error(f"トレンド分析に必要な列 '{y_col}' が月次データにありません。利用可能な列: {monthly_data.columns.tolist()}")
            return
        
        monthly_data_cleaned = monthly_data.replace([np.inf, -np.inf], np.nan).dropna(subset=[y_col])
        if len(monthly_data_cleaned) < 2:
            st.info("有効なデータポイントが2未満のため、トレンド分析を実行できません。")
            return

        x = np.arange(len(monthly_data_cleaned))
        y = monthly_data_cleaned[y_col].values
        
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        
        trend_text = "➡️ 明確なトレンドなし"
        if p_value < 0.05:
            if slope > 0:
                trend_text = "📈 統計的に有意な上昇トレンド"
            elif slope < 0:
                trend_text = "📉 統計的に有意な下降トレンド"
            else:
                trend_text = "➡️ トレンドなし (傾きゼロ)"

        col1_metric, col2_metric, col3_metric = st.columns(3)
        with col1_metric:
            st.metric("トレンド", trend_text, f"傾き: {slope:.2f}人/月")
        with col2_metric:
            st.metric("相関係数 (R)", f"{r_value:.3f}", help="1に近いほど強い相関")
        with col3_metric:
            st.metric("p値", f"{p_value:.3f}", help="0.05未満で統計的に有意")
        
        if st.checkbox("📊 トレンド線を表示", key="ops_trend_show_trend_line"): # キーをより具体的に
            trend_line_values = intercept + slope * x
            
            fig_trend = go.Figure()
            fig_trend.add_trace(
                go.Scatter(
                    x=monthly_data_cleaned['年月str'], y=y,
                    mode='lines+markers', name='実績'
                )
            )
            fig_trend.add_trace(
                go.Scatter(
                    x=monthly_data_cleaned['年月str'], y=trend_line_values,
                    mode='lines', name='トレンド線', line=dict(dash='dash')
                )
            )
            
            if st.checkbox("信頼区間を表示", key="ops_trend_show_confidence_interval"):
                n_display = len(x) # x は x_valid に相当する長さ
                x_mean_display = np.mean(x)
                sxx_display = np.sum((x - x_mean_display) ** 2)
                
                y_pred_display = intercept + slope * x
                residuals_display = y - y_pred_display # y は y_valid に相当
                residual_std_error_display = np.sqrt(np.sum(residuals_display ** 2) / (n_display - 2)) if (n_display - 2) > 0 else 0
                
                if residual_std_error_display > 0:
                    t_val_display = stats.t.ppf(0.975, n_display - 2)
                    
                    confidence_interval_display = []
                    for xi_display in x:
                        se_display = residual_std_error_display * np.sqrt(1/n_display + (xi_display - x_mean_display)**2 / sxx_display) if sxx_display > 0 else residual_std_error_display * np.sqrt(1/n_display)
                        ci_display = t_val_display * se_display
                        confidence_interval_display.append(ci_display)
                    
                    upper_bound_display = trend_line_values + np.array(confidence_interval_display)
                    lower_bound_display = trend_line_values - np.array(confidence_interval_display)
                    
                    fig_trend.add_trace(go.Scatter(
                        x=monthly_data_cleaned['年月str'], y=upper_bound_display, mode='lines',
                        name='95%信頼区間(上限)', line=dict(color='rgba(231,76,60,0.3)', width=1, dash='dot'), showlegend=False
                    ))
                    fig_trend.add_trace(go.Scatter(
                        x=monthly_data_cleaned['年月str'], y=lower_bound_display, mode='lines',
                        name='95%信頼区間', line=dict(color='rgba(231,76,60,0.3)', width=1, dash='dot'),
                        fill='tonexty', fillcolor='rgba(231,76,60,0.1)', showlegend=True
                    ))

            if st.checkbox("将来予測を表示", key="ops_trend_show_future_prediction"):
                future_months = st.slider("予測月数", min_value=1, max_value=12, value=3, key="ops_trend_future_months_slider")
                last_date_dt = pd.to_datetime(monthly_data_cleaned.iloc[-1]['年月str'])
                future_dates_str = [(last_date_dt + pd.DateOffset(months=i)).strftime('%Y-%m') for i in range(1, future_months + 1)]
                future_x_values = np.arange(len(monthly_data_cleaned), len(monthly_data_cleaned) + future_months)
                future_y_values = intercept + slope * future_x_values
                
                fig_trend.add_trace(go.Scatter(
                    x=future_dates_str, y=future_y_values, mode='lines+markers', name='将来予測',
                    line=dict(color='#27ae60', width=2, dash='dashdot'), marker=dict(symbol='diamond')
                ))

            fig_trend.update_layout(
                title="トレンド分析と予測",
                xaxis_title="年月", yaxis_title=y_col, height=400, hovermode='x unified',
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
            )
            fig_trend.update_xaxes(tickangle=-45)
            st.plotly_chart(fig_trend, use_container_width=True)

            with st.expander("📊 詳細な統計情報", expanded=False):
                st.write(f"**回帰式**: y = {slope:.3f}x + {intercept:.3f}")
                st.write(f"**決定係数 (R²)**: {r_value**2:.3f}")
                st.write(f"**標準誤差 (回帰)**: {std_err:.3f}")
                if len(monthly_data_cleaned) >= 24:
                    st.subheader("季節性分析（月別平均）")
                    monthly_data_cleaned['月'] = pd.to_datetime(monthly_data_cleaned['年月str']).dt.month
                    seasonal_avg = monthly_data_cleaned.groupby('月')[y_col].mean()
                    
                    fig_seasonal = go.Figure()
                    fig_seasonal.add_trace(go.Bar(
                        x=['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
                        y=seasonal_avg.reindex(range(1,13)).values, # 月の順序を保証
                        marker_color='#3498db'
                    ))
                    fig_seasonal.update_layout(title="月別平均在院患者数", xaxis_title="月", yaxis_title=y_col, height=300)
                    st.plotly_chart(fig_seasonal, use_container_width=True)
                    
                    seasonal_cv = (seasonal_avg.std() / seasonal_avg.mean()) * 100 if seasonal_avg.mean() != 0 else 0
                    if seasonal_cv > 10:
                        st.warning(f"季節変動が大きい可能性があります（月別平均の変動係数: {seasonal_cv:.1f}%）")
                    else:
                        st.info(f"季節変動は比較的小さいです（月別平均の変動係数: {seasonal_cv:.1f}%）")

    except ImportError:
        st.info("トレンド分析にはscipyライブラリが必要です。`pip install scipy numpy`でインストールしてください。")
    except Exception as e:
        st.error(f"トレンド分析中に予期せぬエラーが発生しました: {e}")
        # import traceback # デバッグ時のみ
        # st.code(traceback.format_exc()) # デバッグ時のみ

def display_period_comparison_charts(df_graph, graph_dates, graph_period):
    """期間比較チャートの表示（integrated_preprocessing.py の出力を前提とする）"""
    try:
        if df_graph.empty:
            st.warning("比較用データがありません。")
            return
        
        # integrated_preprocess_data で処理済みのデータを期待するため、
        # ここでの normalize_column_names の呼び出しは削除またはコメントアウト
        # df_normalized = normalize_column_names(df_graph) # ← コメントアウトまたは削除
        df_graph_copy = df_graph.copy() # 直接 df_graph を使用

        if '日付' not in df_graph_copy.columns:
            st.error("期間比較チャートのデータに「日付」列がありません。")
            return
        df_graph_copy['日付'] = pd.to_datetime(df_graph_copy['日付'])
        df_graph_copy['年月'] = df_graph_copy['日付'].dt.to_period('M')
        
        # integrated_preprocess_data により '入院患者数（在院）' が主要な在院患者数列として期待される
        census_col = '入院患者数（在院）' # kpi_calculator.py もこの列を参照
        
        if census_col not in df_graph_copy.columns:
            st.warning(f"期間比較チャートのための主要な在院患者数データ ('{census_col}') が見つかりません。")
            # integrated_preprocess_data でエラーとして処理されるはずなので、ここでは return する
            return
            
        monthly_data = df_graph_copy.groupby('年月').agg({
            census_col: 'mean'
        }).reset_index()
        
        monthly_data.columns = ['年月', '日平均在院患者数'] # この列名はグラフ表示や display_trend_analysis で使用
        monthly_data['年月str'] = monthly_data['年月'].astype(str)
        
        # 以降のグラフ作成ロジックは前回と同様だが、エラーハンドリングやキーの重複を避ける修正を含む
        if len(monthly_data) >= 12:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=monthly_data['年月str'], y=monthly_data['日平均在院患者数'],
                    mode='lines+markers', name='日平均在院患者数',
                    line=dict(color='#3498db', width=3), marker=dict(size=8)
                )
            )
            avg_census = monthly_data['日平均在院患者数'].mean()
            fig.add_hline(
                y=avg_census, line_dash="dash", line_color="red",
                annotation_text=f"平均: {avg_census:.1f}人", annotation_position="right"
            )
            total_beds = st.session_state.get('total_beds', 612)
            bed_occupancy_rate_target = st.session_state.get('bed_occupancy_rate', 0.85)
            target_census = total_beds * bed_occupancy_rate_target
            fig.add_hline(
                y=target_census, line_dash="dot", line_color="green",
                annotation_text=f"目標: {target_census:.1f}人", annotation_position="left"
            )
            fig.update_layout(
                title=f"運営指標 月次トレンド（{graph_period}）",
                xaxis_title="年月", yaxis_title="日平均在院患者数",
                height=400, showlegend=True
            )
            st.plotly_chart(fig, use_container_width=True)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "期間平均", f"{avg_census:.1f}人",
                    delta=f"{((avg_census / target_census) - 1) * 100:.1f}% (対目標)" if target_census > 0 else "N/A"
                )
            with col2:
                if len(monthly_data) >= 2:
                    latest_month_val = monthly_data.iloc[-1]['日平均在院患者数']
                    prev_month_val = monthly_data.iloc[-2]['日平均在院患者数']
                    change_rate = ((latest_month_val / prev_month_val) - 1) * 100 if prev_month_val > 0 else 0
                    st.metric("最新月", f"{latest_month_val:.1f}人", delta=f"{change_rate:+.1f}% (前月比)")
            with col3:
                cv = (monthly_data['日平均在院患者数'].std() / avg_census) * 100 if avg_census > 0 else 0
                st.metric("変動係数", f"{cv:.1f}%", help="値が小さいほど安定している")

            if st.checkbox("運営指標のトレンド詳細分析を表示", value=False, key="show_operations_trend_analysis_checkbox"):
                 display_trend_analysis(monthly_data)
        
        elif len(df_graph_copy) >= 7: # 7日以上のデータがあれば日次グラフ
            st.info("月次トレンドは12ヶ月以上のデータで表示されます。代わりに日次推移を表示します。")
            df_graph_copy['日付'] = pd.to_datetime(df_graph_copy['日付']) # 再度確認
            daily_data = df_graph_copy.groupby(df_graph_copy['日付'].dt.date)[census_col].mean().reset_index()
            daily_data.columns = ['日付', '日次在院患者数'] # 列名を変更して区別
            daily_data['日付'] = pd.to_datetime(daily_data['日付'])
            
            fig_daily = go.Figure()
            fig_daily.add_trace(
                go.Scatter(
                    x=daily_data['日付'], y=daily_data['日次在院患者数'],
                    mode='lines', name=census_col, line=dict(color='#3498db', width=2)
                )
            )
            if len(daily_data) >= 7:
                daily_data['7日移動平均'] = daily_data['日次在院患者数'].rolling(window=7, min_periods=1).mean()
                fig_daily.add_trace(
                    go.Scatter(
                        x=daily_data['日付'], y=daily_data['7日移動平均'],
                        mode='lines', name='7日移動平均', line=dict(color='#e74c3c', width=2, dash='dash')
                    )
                )
            fig_daily.update_layout(
                title=f"運営指標 日次推移（{graph_period}）",
                xaxis_title="日付", yaxis_title=census_col,
                height=400, showlegend=True
            )
            st.plotly_chart(fig_daily, use_container_width=True)
        else:
            st.info("期間比較グラフを表示するためのデータが不足しています（最低7日分の日次データまたは12ヶ月分の月次データが必要です）。")

    except Exception as e:
        st.error(f"期間比較チャート作成エラー (運営指標): {e}")
        import traceback
        with st.expander("エラー詳細 (運営指標)"):
            st.code(traceback.format_exc())

def check_forecast_dependencies():
    """予測機能に必要な依存関係をチェック"""
    missing_libs = []
    
    try:
        import statsmodels
    except ImportError:
        missing_libs.append("statsmodels")
    
    try:
        import pmdarima
    except ImportError:
        missing_libs.append("pmdarima")
    
    try:
        import jpholiday
    except ImportError:
        missing_libs.append("jpholiday")
    
    if missing_libs:
        st.sidebar.warning(
            f"予測機能の完全な動作には以下のライブラリが必要です:\n"
            f"{', '.join(missing_libs)}\n\n"
            f"インストール方法:\n"
            f"```\npip install {' '.join(missing_libs)}\n```"
        )
    
    return len(missing_libs) == 0


# load_and_process_files 関数を作成（app.py内に定義）
def load_and_process_files(files):
    """
    ファイルを読み込み、前処理を実行する統合関数
    
    Parameters:
    -----------
    files : list
        アップロードされたファイルのリスト
        
    Returns:
    --------
    tuple
        (処理済みDataFrame, 処理情報)
    """
    try:
        start_time = time.time()
        
        # ファイルの読み込み
        df_raw = load_files(None, files)
        
        if df_raw is None or df_raw.empty:
            return None, {"error": "ファイルの読み込みに失敗しました"}
        
        # 前処理の実行
        df_processed, validation_results = integrated_preprocess_data(df_raw)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # 処理情報の作成
        processing_info = {
            "processing_time": processing_time,
            "memory_usage_mb": psutil.Process().memory_info().rss / (1024 * 1024),
            "files_processed": len(files),
            "validation_results": validation_results
        }
        
        return df_processed, processing_info
        
    except Exception as e:
        error_info = {
            "error": f"データ処理中にエラーが発生しました: {str(e)}",
            "processing_time": 0,
            "memory_usage_mb": 0,
            "files_processed": 0
        }
        return None, error_info



def create_sidebar():
    """サイドバーの設定UI"""
    st.sidebar.header("⚙️ 設定")
    
    # デバッグ: セッション状態の型をチェック
    if st.sidebar.checkbox("🔧 デバッグ情報を表示", value=False):
        st.sidebar.write("**セッション状態の型チェック:**")
        debug_keys = ['total_beds', 'bed_occupancy_rate', 'avg_length_of_stay', 'avg_admission_fee']
        for key in debug_keys:
            value = st.session_state.get(key, 'None')
            st.sidebar.write(f"{key}: {type(value).__name__} = {value}")
    
    # --- 期間設定セクション ---
    with st.sidebar.expander("📅 期間設定", expanded=True):
        # データが処理されている場合のみ期間設定を表示
        if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
            df = st.session_state.df
            min_date = df['日付'].min().date()
            max_date = df['日付'].max().date()
            
            # デフォルトの期間設定（直近3ヶ月）
            default_start = max(min_date, max_date - pd.Timedelta(days=90))
            default_end = max_date
            
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input(
                    "開始日",
                    value=st.session_state.get('analysis_start_date', default_start),
                    min_value=min_date,
                    max_value=max_date,
                    help="分析開始日を選択してください"
                )
                st.session_state.analysis_start_date = start_date
                
            with col2:
                end_date = st.date_input(
                    "終了日",
                    value=st.session_state.get('analysis_end_date', default_end),
                    min_value=min_date,
                    max_value=max_date,
                    help="分析終了日を選択してください"
                )
                st.session_state.analysis_end_date = end_date
            
            # 期間の妥当性チェック
            if start_date > end_date:
                st.error("開始日は終了日より前の日付を選択してください。")
            else:
                # 選択された期間の情報を表示
                period_days = (end_date - start_date).days + 1
                st.info(f"選択期間: {period_days}日間")
                
                # 期間別の推奨設定
                if period_days <= 7:
                    st.info("💡 短期間分析: 日別詳細分析に適しています")
                elif period_days <= 30:
                    st.info("💡 月次分析: 週別・日別分析に適しています")
                elif period_days <= 90:
                    st.info("💡 四半期分析: 月別・週別分析に適しています")
                else:
                    st.info("💡 長期分析: 月別・四半期分析に適しています")
            
            # 期間プリセット
            st.markdown("**📋 期間プリセット:**")
            preset_col1, preset_col2 = st.columns(2)
            
            with preset_col1:
                if st.button("直近1ヶ月", key="preset_1month"):
                    st.session_state.analysis_start_date = max(min_date, max_date - pd.Timedelta(days=30))
                    st.session_state.analysis_end_date = max_date
                    st.rerun()
                    
                if st.button("直近6ヶ月", key="preset_6months"):
                    st.session_state.analysis_start_date = max(min_date, max_date - pd.Timedelta(days=180))
                    st.session_state.analysis_end_date = max_date
                    st.rerun()
            
            with preset_col2:
                if st.button("直近3ヶ月", key="preset_3months"):
                    st.session_state.analysis_start_date = max(min_date, max_date - pd.Timedelta(days=90))
                    st.session_state.analysis_end_date = max_date
                    st.rerun()
                    
                if st.button("全期間", key="preset_all"):
                    st.session_state.analysis_start_date = min_date
                    st.session_state.analysis_end_date = max_date
                    st.rerun()
        else:
            st.info("データを処理してから期間設定が利用できます。")

    # --- 基本設定セクション ---
    with st.sidebar.expander("🏥 基本設定", expanded=True):
        # 総病床数設定（型安全な値の取得）
        default_total_beds = st.session_state.get('total_beds', 612)
        if isinstance(default_total_beds, list):
            default_total_beds = default_total_beds[0] if default_total_beds else 612
        elif not isinstance(default_total_beds, (int, float)):
            default_total_beds = 612
            
        total_beds = st.number_input(
            "総病床数", 
            min_value=1, 
            max_value=2000, 
            value=int(default_total_beds),
            step=1,
            help="病院の総病床数を入力してください"
        )
        st.session_state.total_beds = total_beds
        
        # 病床稼働率設定（型安全な値の取得）
        default_bed_occupancy = st.session_state.get('bed_occupancy_rate', 90)
        # リスト型の場合は最初の要素を取得、数値でない場合はデフォルト値を使用
        if isinstance(default_bed_occupancy, list):
            default_bed_occupancy = default_bed_occupancy[0] if default_bed_occupancy else 90
        elif not isinstance(default_bed_occupancy, (int, float)):
            default_bed_occupancy = 90
        # パーセンテージ値の場合（0-1の範囲）は100倍する
        if isinstance(default_bed_occupancy, float) and default_bed_occupancy <= 1:
            default_bed_occupancy = int(default_bed_occupancy * 100)
        
        bed_occupancy_rate = st.slider(
            "目標病床稼働率 (%)", 
            min_value=50, 
            max_value=100, 
            value=int(default_bed_occupancy),
            step=1,
            help="目標とする病床稼働率を設定してください"
        ) / 100
        st.session_state.bed_occupancy_rate = bed_occupancy_rate
        
        # 平均在院日数設定（型安全な値の取得）
        default_avg_stay = st.session_state.get('avg_length_of_stay', 12.0)
        if isinstance(default_avg_stay, list):
            default_avg_stay = default_avg_stay[0] if default_avg_stay else 12.0
        elif not isinstance(default_avg_stay, (int, float)):
            default_avg_stay = 12.0
            
        avg_length_of_stay = st.number_input(
            "平均在院日数", 
            min_value=1.0, 
            max_value=30.0, 
            value=float(default_avg_stay),
            step=0.1,
            help="平均在院日数を入力してください"
        )
        st.session_state.avg_length_of_stay = avg_length_of_stay
        
        # 平均入院料設定（型安全な値の取得）
        default_admission_fee = st.session_state.get('avg_admission_fee', 55000)
        if isinstance(default_admission_fee, list):
            default_admission_fee = default_admission_fee[0] if default_admission_fee else 55000
        elif not isinstance(default_admission_fee, (int, float)):
            default_admission_fee = 55000
            
        avg_admission_fee = st.number_input(
            "平均入院料（円/日）", 
            min_value=1000, 
            max_value=100000, 
            value=int(default_admission_fee),
            step=1000,
            help="1日あたりの平均入院料を入力してください"
        )
        st.session_state.avg_admission_fee = avg_admission_fee

    # --- 目標値セクション ---
    with st.sidebar.expander("🎯 目標値設定", expanded=True):
        # 目標値ファイルからの値を取得または手動設定
        extracted_targets = st.session_state.get('extracted_targets', {})
        
        # 延べ在院日数目標の設定（型安全）
        if extracted_targets and extracted_targets.get('target_days'):
            # ファイルから値が取得できた場合
            default_target_days = extracted_targets['target_days']
            if isinstance(default_target_days, list):
                default_target_days = default_target_days[0] if default_target_days else total_beds * bed_occupancy_rate * 30
            st.info(f"📁 目標値ファイルから取得: {default_target_days:,.0f}人日")
        else:
            # 病床設定から推計
            monthly_target_patient_days_calc = total_beds * bed_occupancy_rate * 30
            default_target_days = monthly_target_patient_days_calc
            st.info(f"📊 病床設定から推計: {default_target_days:,.0f}人日")
        
        monthly_target_patient_days = st.number_input(
            "月間延べ在院日数目標（人日）",
            min_value=100,
            max_value=50000,
            value=int(default_target_days),
            step=100,
            help="月間の延べ在院日数目標を設定してください"
        )
        st.session_state.monthly_target_patient_days = monthly_target_patient_days
        
        # 新入院患者数目標の設定（型安全）
        if extracted_targets and extracted_targets.get('target_admissions'):
            # ファイルから値が取得できた場合
            default_target_admissions = extracted_targets['target_admissions']
            if isinstance(default_target_admissions, list):
                default_target_admissions = default_target_admissions[0] if default_target_admissions else monthly_target_patient_days / avg_length_of_stay
            st.info(f"📁 目標値ファイルから取得: {default_target_admissions:,.0f}人")
        else:
            # 延べ在院日数から推計
            default_target_admissions = monthly_target_patient_days / avg_length_of_stay
            st.info(f"📊 在院日数から推計: {default_target_admissions:.0f}人")
        
        monthly_target_admissions = st.number_input(
            "月間新入院患者数目標（人）",
            min_value=10,
            max_value=5000,
            value=int(default_target_admissions),
            step=10,
            help="月間の新入院患者数目標を設定してください"
        )
        st.session_state.monthly_target_admissions = monthly_target_admissions
        
        # 収益目標の計算（avg_admission_fee を使用）
        monthly_revenue_estimate = monthly_target_patient_days * avg_admission_fee
        st.session_state.monthly_revenue_estimate = monthly_revenue_estimate
        
        # 目標値の表示（修正：1列4行に変更）
        st.markdown("### 📈 目標値サマリー")
        st.markdown('<div class="sidebar-target-summary-metrics">', unsafe_allow_html=True)
        
        # ✅ 修正：2列から1列4行に変更
        st.metric(
            "延べ在院日数",
            f"{monthly_target_patient_days:,}人日",
            help="月間目標延べ在院日数"
        )
        
        st.metric(
            "新入院患者数",
            f"{monthly_target_admissions:,}人",
            help="月間目標新入院患者数"
        )
        
        st.metric(
            "推定月間収益",
            f"{monthly_revenue_estimate:,.0f}円",
            help="月間目標収益"
        )
        
        st.metric(
            "病床稼働率",
            f"{bed_occupancy_rate:.1%}",
            help="目標病床稼働率"
        )
        
        st.markdown('</div>', unsafe_allow_html=True)
        
    # --- 表示設定セクション ---
    with st.sidebar.expander("📊 表示設定", expanded=False):
        show_weekday_analysis = st.checkbox(
            "平日・休日分析を表示", 
            value=st.session_state.get('show_weekday_analysis', True),
            help="平日と休日の比較分析を表示します"
        )
        st.session_state.show_weekday_analysis = show_weekday_analysis
        
        show_monthly_trend = st.checkbox(
            "月次推移を表示", 
            value=st.session_state.get('show_monthly_trend', True),
            help="月次の推移グラフを表示します"
        )
        st.session_state.show_monthly_trend = show_monthly_trend
        
        show_department_analysis = st.checkbox(
            "診療科別分析を表示", 
            value=st.session_state.get('show_department_analysis', True),
            help="診療科別の詳細分析を表示します"
        )
        st.session_state.show_department_analysis = show_department_analysis
        
        # グラフの高さ設定
        chart_height = st.select_slider(
            "グラフの高さ",
            options=[300, 400, 500, 600, 700],
            value=st.session_state.get('chart_height', 400),
            help="グラフの表示高さを調整します"
        )
        st.session_state.chart_height = chart_height

    # --- データ品質情報 ---
    if st.session_state.get('data_processed', False):
        with st.sidebar.expander("📊 データ情報", expanded=False):
            df = st.session_state.get('df')
            if df is not None and not df.empty:
                st.write(f"**データ期間:** {df['日付'].min().strftime('%Y/%m/%d')} - {df['日付'].max().strftime('%Y/%m/%d')}")
                st.write(f"**総レコード数:** {len(df):,}")
                st.write(f"**病棟数:** {df['病棟コード'].nunique()}")
                st.write(f"**診療科数:** {df['診療科名'].nunique()}")
                
                # 最新の実績値
                latest_date = df['日付'].max()
                latest_data = df[df['日付'] == latest_date]
                if not latest_data.empty:
                    latest_total_patients = latest_data['在院患者数'].sum()
                    latest_admissions = latest_data['入院患者数'].sum()
                    
                    st.markdown("**最新実績 (直近日):**")
                    st.write(f"在院患者数: {latest_total_patients:,}人")
                    st.write(f"入院患者数: {latest_admissions:,}人")
                    
                    # 目標との比較
                    daily_target_patients = monthly_target_patient_days / 30
                    daily_target_admissions = monthly_target_admissions / 30
                    
                    patients_vs_target = (latest_total_patients / daily_target_patients) * 100 if daily_target_patients > 0 else 0
                    admissions_vs_target = (latest_admissions / daily_target_admissions) * 100 if daily_target_admissions > 0 else 0
                    
                    st.markdown("**目標達成率:**")
                    st.write(f"在院患者: {patients_vs_target:.1f}%")
                    st.write(f"入院患者: {admissions_vs_target:.1f}%")

    # 設定が有効かどうかを返す
    return (total_beds > 0 and 
            bed_occupancy_rate > 0 and 
            avg_length_of_stay > 0 and
            avg_admission_fee > 0 and
            monthly_target_patient_days > 0 and 
            monthly_target_admissions > 0)
            

def create_management_dashboard_tab():
    """修正版：正しい収益達成率計算を使用"""
    if 'df' not in st.session_state or st.session_state['df'] is None:
        st.warning("⚠️ データが読み込まれていません。先にデータ処理タブでファイルをアップロードしてください。")
        return
    
    df = st.session_state['df']
    
    st.header("💰 経営ダッシュボード")
    
    # 期間選択UI
    st.markdown("### 📊 表示期間設定")
    
    period_options = ["直近30日", "前月完了分", "今年度"]
    selected_period = st.radio(
        "期間選択（平均値計算用）",
        period_options,
        index=0,
        horizontal=True,
        key="dashboard_period_selector",
        help="日平均在院患者数、平均在院日数、日平均新入院患者数の計算期間"
    )
    
    st.markdown("---")
    
    # ✅ 修正版のメトリクス計算を使用
    metrics = calculate_dashboard_metrics(df, selected_period)
    
    if not metrics:
        st.error("データの計算に失敗しました。")
        return
    
    # 色分けされた統一レイアウトで数値表示
    display_unified_metrics_layout_colorized(metrics, selected_period)
    
# 色の定義（参考用）
DASHBOARD_COLORS = {
    'primary_blue': '#3498db',      # 日平均在院患者数
    'success_green': '#27ae60',     # 病床利用率（達成時）
    'warning_orange': '#f39c12',    # 平均在院日数
    'danger_red': '#e74c3c',        # 延べ在院日数、推計収益
    'info_purple': '#9b59b6',       # 日平均新入院患者数
    'secondary_teal': '#16a085',    # 日平均収益
    'dark_gray': '#2c3e50',         # テキスト
    'light_gray': '#6c757d'         # サブテキスト
}

def calculate_dashboard_metrics(df, selected_period):
    """修正版：不足していた関数を含む完全版メトリクス計算"""
    try:
        from kpi_calculator import calculate_kpis
        
        latest_date = df['日付'].max()
        
        # 1. 固定期間データ（直近30日）の計算
        fixed_start_date = latest_date - pd.Timedelta(days=29)
        fixed_end_date = latest_date
        
        total_beds = st.session_state.get('total_beds', 612)
        fixed_kpis = calculate_kpis(df, fixed_start_date, fixed_end_date, total_beds=total_beds)
        
        if fixed_kpis and fixed_kpis.get("error"):
            st.error(f"固定期間のKPI計算エラー: {fixed_kpis['error']}")
            return None
        
        # 2. 平均値計算用期間データの計算
        period_start_date, period_end_date = get_period_dates(df, selected_period)
        period_kpis = calculate_kpis(df, period_start_date, period_end_date, total_beds=total_beds)
        
        if period_kpis and period_kpis.get("error"):
            st.error(f"平均値計算期間のKPI計算エラー: {period_kpis['error']}")
            return None
        
        # 3. ✅ 月次収益達成率の正しい計算
        current_month_start = latest_date.replace(day=1)
        current_month_end = latest_date
        
        # 当月実績の計算
        current_month_kpis = calculate_kpis(df, current_month_start, current_month_end, total_beds=total_beds)
        
        # 基本設定値
        avg_admission_fee = st.session_state.get('avg_admission_fee', 55000)
        monthly_target_patient_days = st.session_state.get('monthly_target_patient_days', 17000)
        target_revenue = monthly_target_patient_days * avg_admission_fee
        
        # 固定値（直近30日）の取得
        total_patient_days_30d = fixed_kpis.get('total_patient_days', 0)
        avg_daily_census_30d = fixed_kpis.get('avg_daily_census', 0)
        bed_occupancy_rate = fixed_kpis.get('bed_occupancy_rate', 0)
        
        # 直近30日の推計収益（月次目標とは比較しない）
        estimated_revenue_30d = total_patient_days_30d * avg_admission_fee
        
        # ✅ 正しい月次収益達成率の計算
        if current_month_kpis and not current_month_kpis.get("error"):
            current_month_patient_days = current_month_kpis.get('total_patient_days', 0)
            current_month_revenue = current_month_patient_days * avg_admission_fee
            
            # 月途中の場合は月次換算
            days_elapsed = (current_month_end - current_month_start).days + 1
            days_in_month = pd.Timestamp(current_month_end.year, current_month_end.month, 1).days_in_month
            
            if days_elapsed < days_in_month:
                # 月途中の場合：月次換算収益を計算
                projected_monthly_revenue = current_month_revenue * (days_in_month / days_elapsed)
                monthly_achievement_rate = (projected_monthly_revenue / target_revenue) * 100 if target_revenue > 0 else 0
                revenue_calculation_note = f"月途中換算（{days_elapsed}/{days_in_month}日）"
            else:
                # 月完了の場合：実績そのまま
                monthly_achievement_rate = (current_month_revenue / target_revenue) * 100 if target_revenue > 0 else 0
                projected_monthly_revenue = current_month_revenue
                revenue_calculation_note = "月完了実績"
        else:
            # 当月データが取得できない場合
            projected_monthly_revenue = 0
            monthly_achievement_rate = 0
            revenue_calculation_note = "当月データなし"
        
        # 平均値（選択期間）の取得
        avg_daily_census = period_kpis.get('avg_daily_census', 0)
        avg_los = period_kpis.get('alos', 0)
        avg_daily_admissions = period_kpis.get('avg_daily_admissions', 0)
        period_days = period_kpis.get('days_count', 1)
        
        return {
            # 固定値（直近30日）
            'total_patient_days_30d': total_patient_days_30d,
            'bed_occupancy_rate': bed_occupancy_rate,
            'estimated_revenue_30d': estimated_revenue_30d,  # 直近30日の収益
            'avg_daily_census_30d': avg_daily_census_30d,
            
            # ✅ 修正：正しい月次達成率
            'monthly_achievement_rate': monthly_achievement_rate if 'monthly_achievement_rate' in locals() else 0,
            'projected_monthly_revenue': projected_monthly_revenue if 'projected_monthly_revenue' in locals() else 0,
            'revenue_calculation_note': revenue_calculation_note if 'revenue_calculation_note' in locals() else "計算エラー",
            
            # 平均値（選択期間）
            'avg_daily_census': avg_daily_census,
            'avg_los': avg_los,
            'avg_daily_admissions': avg_daily_admissions,
            'period_days': period_days,
            
            # 設定値
            'total_beds': total_beds,
            'target_revenue': target_revenue,
            'selected_period': selected_period
        }
        
    except ImportError as e:
        st.error(f"kpi_calculator.pyのインポートに失敗しました: {e}")
        return None
    except Exception as e:
        st.error(f"メトリクス計算エラー: {e}")
        import traceback
        st.error(traceback.format_exc())
        return None

def get_period_dates(df, selected_period):
    """選択期間の開始日・終了日を取得"""
    latest_date = df['日付'].max()
    
    if selected_period == "直近30日":
        start_date = latest_date - pd.Timedelta(days=29)
        end_date = latest_date
    elif selected_period == "前月完了分":
        # 前月の1日から末日まで
        prev_month_start = (latest_date.replace(day=1) - pd.Timedelta(days=1)).replace(day=1)
        prev_month_end = latest_date.replace(day=1) - pd.Timedelta(days=1)
        start_date = prev_month_start
        end_date = prev_month_end
    elif selected_period == "今年度":
        # 今年度（4月1日から現在まで）
        current_year = latest_date.year
        if latest_date.month >= 4:
            fiscal_start = pd.Timestamp(current_year, 4, 1)
        else:
            fiscal_start = pd.Timestamp(current_year - 1, 4, 1)
        start_date = fiscal_start
        end_date = latest_date
    else:
        start_date = latest_date - pd.Timedelta(days=29)
        end_date = latest_date
    
    return start_date, end_date

def validate_kpi_calculations():
    """KPI計算の検証（オプション機能）"""
    if not st.session_state.get('data_processed', False):
        return
    
    df = st.session_state.get('df')
    if df is None or df.empty:
        return
    
    st.markdown("#### 🔍 KPI計算検証")
    
    # 検証期間の設定
    latest_date = df['日付'].max()
    test_start = latest_date - pd.Timedelta(days=29)
    test_end = latest_date
    
    # kpi_calculator.pyの計算結果
    from kpi_calculator import calculate_kpis
    kpi_result = calculate_kpis(df, test_start, test_end, 
                               total_beds=st.session_state.get('total_beds', 612))
    
    if kpi_result and not kpi_result.get("error"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**✅ kpi_calculator.py による計算**")
            st.write(f"日平均在院患者数: {kpi_result.get('avg_daily_census', 0):.2f}人")
            st.write(f"平均在院日数: {kpi_result.get('alos', 0):.2f}日")
            st.write(f"病床利用率: {kpi_result.get('bed_occupancy_rate', 0):.2f}%")
            st.write(f"処理時間: {kpi_result.get('processing_time', 0):.3f}秒")
        
        with col2:
            # 手動計算での検証
            test_data = df[(df['日付'] >= test_start) & (df['日付'] <= test_end)]
            manual_days = len(test_data['日付'].unique())
            
            if '入院患者数（在院）' in test_data.columns:
                manual_total_census = test_data['入院患者数（在院）'].sum()
                manual_avg_census = manual_total_census / manual_days if manual_days > 0 else 0
                
                st.markdown("**🔧 手動検証計算**")
                st.write(f"期間日数: {manual_days}日")
                st.write(f"延べ在院日数: {manual_total_census:,.0f}人日")
                st.write(f"日平均在院患者数: {manual_avg_census:.2f}人")
                
                # 差異の確認
                diff = abs(kpi_result.get('avg_daily_census', 0) - manual_avg_census)
                st.write(f"**計算差異**: {diff:.6f}人")
                
                if diff < 0.01:
                    st.success("✅ 計算結果が一致しています")
                else:
                    st.warning(f"⚠️ 計算差異があります: {diff:.6f}人")
                    
def get_period_data_for_averages(df, selected_period):
    """平均値計算用の期間データを取得"""
    latest_date = df['日付'].max()
    
    if selected_period == "直近30日":
        start_date = latest_date - pd.Timedelta(days=29)
        end_date = latest_date
        return df[(df['日付'] >= start_date) & (df['日付'] <= end_date)].copy()
    
    elif selected_period == "前月完了分":
        # 前月の1日から末日まで
        prev_month_start = (latest_date.replace(day=1) - pd.Timedelta(days=1)).replace(day=1)
        prev_month_end = latest_date.replace(day=1) - pd.Timedelta(days=1)
        return df[(df['日付'] >= prev_month_start) & (df['日付'] <= prev_month_end)].copy()
    
    elif selected_period == "今年度":
        # 今年度（4月1日から現在まで）
        current_year = latest_date.year
        if latest_date.month >= 4:
            fiscal_start = pd.Timestamp(current_year, 4, 1)
        else:
            fiscal_start = pd.Timestamp(current_year - 1, 4, 1)
        return df[(df['日付'] >= fiscal_start) & (df['日付'] <= latest_date)].copy()
    
    else:
        return df.copy()

def display_unified_metrics_layout_colorized(metrics, selected_period):
    """修正版：正しい収益達成率を表示（完全版）"""
    
    def format_number_normal(value, unit=""):
        """通常のカンマ区切り数値表記"""
        if pd.isna(value) or value == 0:
            return f"0{unit}"
        
        if isinstance(value, (int, float)) and value == int(value):
            return f"{int(value):,}{unit}"
        else:
            return f"{value:,.0f}{unit}"
    
    # 期間表示
    period_info = get_period_display_info(selected_period)
    st.info(f"📊 平均値計算期間: {period_info}")
    st.caption("※延べ在院日数、病床利用率は直近30日固定。収益達成率は当月実績ベース。")
    
    # === 1行目：日平均在院患者数、病床利用率、平均在院日数 ===
    st.markdown(f"### 📊 主要指標 （最新月: {pd.Timestamp.now().strftime('%Y-%m')}）")
    
    st.markdown('<div class="management-dashboard-kpi-card">', unsafe_allow_html=True)
    
    col1_1, col1_2, col1_3 = st.columns(3)
    
    with col1_1:
        st.metric(
            "日平均在院患者数",
            f"{metrics['avg_daily_census']:.1f}人",
            delta=f"参考：直近30日 {metrics['avg_daily_census_30d']:.1f}人",
            help=f"{selected_period}の日平均在院患者数"
        )
    
    with col1_2:
        target_occupancy = st.session_state.get('bed_occupancy_rate', 0.85) * 100
        occupancy_delta = metrics['bed_occupancy_rate'] - target_occupancy
        delta_color = "normal" if abs(occupancy_delta) <= 5 else "inverse"
        
        st.metric(
            "病床利用率",
            f"{metrics['bed_occupancy_rate']:.1f}%",
            delta=f"{occupancy_delta:+.1f}% (対目標{target_occupancy:.0f}%)",
            delta_color=delta_color,
            help="直近30日の平均病床利用率"
        )
    
    with col1_3:
        st.metric(
            "平均在院日数",
            f"{metrics['avg_los']:.1f}日",
            delta="標準: 12-16日",
            help=f"{selected_period}の平均在院日数"
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("---")
    
    # === 2行目：日平均新入院患者数、延べ在院日数 ===
    st.markdown("### 📊 患者動向指標")
    
    col2_1, col2_2, col2_3 = st.columns(3)
    
    with col2_1:
        st.metric(
            "日平均新入院患者数",
            f"{metrics['avg_daily_admissions']:.1f}人",
            delta=f"期間: {metrics['period_days']}日間",
            help=f"{selected_period}の日平均新入院患者数"
        )
    
    with col2_2:
        monthly_target = st.session_state.get('monthly_target_patient_days', 17000)
        achievement_days = (metrics['total_patient_days_30d'] / monthly_target) * 100
        
        st.metric(
            "延べ在院日数（直近30日）",
            f"{format_number_normal(metrics['total_patient_days_30d'])}人日",
            delta=f"対月間目標: {achievement_days:.1f}%",
            delta_color="normal" if achievement_days >= 95 else "inverse",
            help="直近30日間の延べ在院日数（参考値）"
        )
    
    with col2_3:
        st.metric(
            "延べ在院日数達成率",
            f"{achievement_days:.1f}%",
            delta=f"目標: {format_number_normal(monthly_target)}人日",
            delta_color="normal" if achievement_days >= 100 else "inverse",
            help="直近30日の月間目標に対する参考達成率"
        )
    
    st.markdown("---")
    
    # === 3行目：推計収益、達成率（修正版） ===
    st.markdown("### 💰 収益指標")
    
    col3_1, col3_2, col3_3 = st.columns(3)
    
    with col3_1:
        # 直近30日の推計収益（参考値として表示）
        st.metric(
            "推計収益（直近30日）",
            f"{format_number_normal(metrics['estimated_revenue_30d'])}円",
            delta=f"単価: {st.session_state.get('avg_admission_fee', 55000):,}円/日",
            help="直近30日の推計収益（参考値）"
        )
    
    with col3_2:
        # ✅ 修正：正しい月次達成率
        monthly_rate = metrics.get('monthly_achievement_rate', 0)
        achievement_status = "✅ 達成" if monthly_rate >= 100 else "📈 未達"
        
        st.metric(
            "月次収益達成率",
            f"{monthly_rate:.1f}%",
            delta=f"{achievement_status} ({metrics.get('revenue_calculation_note', 'N/A')})",
            delta_color="normal" if monthly_rate >= 100 else "inverse",
            help="当月の収益達成率（月途中の場合は換算値）"
        )
    
    with col3_3:
        # 月次換算収益
        projected_revenue = metrics.get('projected_monthly_revenue', 0)
        st.metric(
            "月次換算収益",
            f"{format_number_normal(projected_revenue)}円",
            delta=f"目標: {format_number_normal(metrics['target_revenue'])}円",
            help="当月の月次換算収益"
        )
    
    # === 詳細情報セクション ===
    st.markdown("---")
    with st.expander("📋 詳細データと設定値", expanded=False):
        detail_col1, detail_col2, detail_col3 = st.columns(3)
        
        with detail_col1:
            st.markdown("**🏥 基本設定**")
            st.write(f"• 総病床数: {metrics['total_beds']:,}床")
            st.write(f"• 目標病床稼働率: {st.session_state.get('bed_occupancy_rate', 0.85):.1%}")
            st.write(f"• 平均入院料: {st.session_state.get('avg_admission_fee', 55000):,}円/日")
        
        with detail_col2:
            st.markdown("**📅 期間情報**")
            st.write(f"• 平均値計算: {selected_period}")
            st.write(f"• 固定値計算: 直近30日")
            st.write(f"• 収益計算: 当月ベース")
        
        with detail_col3:
            st.markdown("**🎯 目標値**")
            st.write(f"• 月間延べ在院日数: {format_number_normal(st.session_state.get('monthly_target_patient_days', 17000))}人日")
            st.write(f"• 月間目標収益: {format_number_normal(metrics['target_revenue'])}円")
            st.write(f"• 月間新入院目標: {st.session_state.get('monthly_target_admissions', 1480):,}人")
    
    # === 数値の見方説明 ===
    st.markdown("---")
    st.markdown("### 📊 表示について")
    
    info_col1, info_col2 = st.columns(2)
    
    with info_col1:
        st.markdown("""
        **🔢 数値の見方**
        - **緑の矢印**: 目標達成または改善
        - **赤の矢印**: 目標未達または悪化
        - **グレーの矢印**: 参考情報
        """)
    
    with info_col2:
        st.markdown("""
        **📋 単位の説明**
        - **人日**: 延べ在院日数（例: 10,500人日）
        - **円**: 収益金額（例: 580,000,000円）  
        - **%**: 達成率、利用率（例: 95.5%）
        """)

def get_period_display_info(selected_period):
    """期間の表示情報を取得"""
    if selected_period == "直近30日":
        return "直近30日間"
    elif selected_period == "前月完了分":
        return "前月1ヶ月間（完了分）"
    elif selected_period == "今年度":
        return "今年度（4月〜現在）"
    else:
        return selected_period
        
def calculate_period_metrics(df_filtered, selected_period, period_dates):
    """期間別メトリクスの計算"""
    # 数値列の確認
    numeric_columns = ['在院患者数', '入院患者数', '退院患者数', '緊急入院患者数']
    for col in numeric_columns:
        if col in df_filtered.columns:
            df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce').fillna(0)
    
    # 基本メトリクス
    total_patient_days = df_filtered['在院患者数'].sum()
    total_admissions = df_filtered['入院患者数'].sum()
    total_discharges = df_filtered['退院患者数'].sum()
    total_emergency = df_filtered['緊急入院患者数'].sum()
    
    period_days = (period_dates['end_date'] - period_dates['start_date']).days + 1
    avg_daily_census = total_patient_days / period_days if period_days > 0 else 0
    
    # 平均在院日数
    avg_los = total_patient_days / ((total_admissions + total_discharges) / 2) if (total_admissions + total_discharges) > 0 else 0
    
    # 病床利用率
    total_beds = st.session_state.get('total_beds', 612)
    bed_occupancy = (avg_daily_census / total_beds) * 100 if total_beds > 0 else 0
    
    # 期間調整（月途中の場合は月次換算）
    if selected_period in ["当月実績（月途中）", "当月予測（実績+予測）"]:
        days_in_month = pd.Timestamp(period_dates['end_date'].year, period_dates['end_date'].month, 1).days_in_month
        month_adjustment_factor = days_in_month / period_days
        
        return {
            'total_patient_days': total_patient_days,
            'monthly_projected_patient_days': total_patient_days * month_adjustment_factor,
            'avg_daily_census': avg_daily_census,
            'avg_los': avg_los,
            'bed_occupancy': bed_occupancy,
            'total_admissions': total_admissions,
            'monthly_projected_admissions': total_admissions * month_adjustment_factor,
            'total_discharges': total_discharges,
            'emergency_rate': (total_emergency / total_admissions * 100) if total_admissions > 0 else 0,
            'period_days': period_days,
            'month_adjustment_factor': month_adjustment_factor,
            'is_partial_month': True
        }
    else:
        return {
            'total_patient_days': total_patient_days,
            'avg_daily_census': avg_daily_census,
            'avg_los': avg_los,
            'bed_occupancy': bed_occupancy,
            'total_admissions': total_admissions,
            'total_discharges': total_discharges,
            'emergency_rate': (total_emergency / total_admissions * 100) if total_admissions > 0 else 0,
            'period_days': period_days,
            'is_partial_month': False
        }

def display_kpi_cards(metrics, selected_period):
    """修正版：通常のst.metricを使用したKPIカード"""
    
    def format_large_number(value, unit=""):
        """大きな数値を短縮表示"""
        if pd.isna(value) or value == 0:
            return f"0{unit}"
            
        abs_value = abs(value)
        
        if abs_value >= 100000000:  # 1億以上
            return f"{value/100000000:.1f}億{unit}"
        elif value >= 10000000:  # 1000万以上
            return f"{value/10000000:.0f}千万{unit}"
        elif abs_value >= 1000000:   # 100万以上
            return f"{value/1000000:.0f}百万{unit}"
        elif abs_value >= 10000:     # 1万以上
            return f"{value/10000:.1f}万{unit}"
        elif abs_value >= 1000:      # 1000以上
            return f"{value/1000:.1f}千{unit}"
        else:
            return f"{value:,.0f}{unit}"
    
    # メトリクス値の取得
    alos = metrics.get('avg_los', 0)
    patient_days = metrics.get('total_patient_days', 0)
    bed_occupancy = metrics.get('bed_occupancy', 0)
    admissions = metrics.get('total_admissions', 0)
    
    # 月次換算計算
    if metrics.get('is_partial_month'):
        projected_days = metrics.get('monthly_projected_patient_days', 0)
        projected_admissions = metrics.get('monthly_projected_admissions', 0)
        is_projection = True
    else:
        projected_days = patient_days
        projected_admissions = admissions
        is_projection = False
    
    # 収益計算
    avg_admission_fee = st.session_state.get('avg_admission_fee', 55000)
    revenue = projected_days * avg_admission_fee
    
    # 目標値
    target_occupancy = st.session_state.get('bed_occupancy_rate', 0.85) * 100
    target_revenue = st.session_state.get('monthly_target_patient_days', 17000) * avg_admission_fee
    
    # デルタ計算
    occupancy_delta = bed_occupancy - target_occupancy
    revenue_achievement = (revenue / target_revenue) * 100 if target_revenue > 0 else 0
    
    st.markdown("### 📊 主要指標")
    
    # management-dashboard-kpi-card クラスでKPIカードを囲む
    st.markdown('<div class="management-dashboard-kpi-card">', unsafe_allow_html=True)
    
    # 4列レイアウト
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "平均在院日数",
            f"{alos:.1f}日",
            help="患者の平均滞在期間"
        )
    
    with col2:
        if is_projection:
            main_value = format_large_number(projected_days, "人日")
            delta_text = f"実績: {format_large_number(patient_days, '人日')}"
        else:
            main_value = format_large_number(patient_days, "人日")
            delta_text = "期間合計"
        
        st.metric(
            "延べ在院日数",
            main_value,
            delta=delta_text,
            help="延べ在院日数（予測含む）"
        )
    
    with col3:
        delta_text = f"目標差: {occupancy_delta:+.1f}%"
        
        st.metric(
            "病床利用率",
            f"{bed_occupancy:.1f}%", 
            delta=delta_text,
            help=f"目標: {target_occupancy:.1f}%"
        )
    
    with col4:
        if is_projection:
            main_value = format_large_number(projected_admissions, "人")
            delta_text = f"実績: {format_large_number(admissions, '人')}"
        else:
            main_value = format_large_number(admissions, "人")
            delta_text = "期間合計"
        
        st.metric(
            "総入院患者数",
            main_value,
            delta=delta_text,
            help="新入院患者数（予測含む）"
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 収益指標（別行）
    st.markdown("### 💰 収益指標")
    col5, col6, col7 = st.columns(3)
    
    with col5:
        st.metric(
            "推計収益",
            format_large_number(revenue, "円"),
            delta=f"単価: {avg_admission_fee:,}円/日",
            help="延べ在院日数×平均入院料で算出"
        )
    
    with col6:
        achievement_delta = "✅ 目標達成" if revenue_achievement >= 100 else "📈 目標未達"
        st.metric(
            "目標達成率",
            f"{revenue_achievement:.1f}%",
            delta=achievement_delta,
            help=f"目標: {format_large_number(target_revenue, '円')}"
        )
    
    with col7:
        daily_revenue = revenue / max(metrics.get('period_days', 1), 1)
        st.metric(
            "日平均収益",
            format_large_number(daily_revenue, "円"),
            delta="1日あたり平均",
            help="期間中の1日あたり平均収益"
        )

# ===== 月次予測関連の関数（forecast.py に実装予定） =====

def create_operations_dashboard_section(df, targets_df=None):
    """運営指標セクションの作成"""
    try:
        # 期間フィルタリング
        start_date = st.session_state.get('start_date')
        end_date = st.session_state.get('end_date')
        
        if start_date and end_date:
            # 日付型の変換を確実に行う
            if isinstance(start_date, str):
                start_date = pd.to_datetime(start_date).date()
            if isinstance(end_date, str):
                end_date = pd.to_datetime(end_date).date()
            
            # DataFrameの日付列をdatetime型に変換
            df_copy = df.copy()
            df_copy['日付'] = pd.to_datetime(df_copy['日付'])
            
            df_filtered = df_copy[
                (df_copy['日付'].dt.date >= start_date) & 
                (df_copy['日付'].dt.date <= end_date)
            ].copy()
        else:
            df_filtered = df.copy()
        
        if df_filtered.empty:
            st.warning("指定された期間にデータがありません。")
            return
        
        # 数値列の確認と変換
        numeric_columns = ['在院患者数', '入院患者数', '退院患者数', '緊急入院患者数']
        for col in numeric_columns:
            if col in df_filtered.columns:
                df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce').fillna(0)
        
        # KPI計算
        total_patient_days = df_filtered['在院患者数'].sum()
        total_admissions = df_filtered['入院患者数'].sum()
        total_discharges = df_filtered['退院患者数'].sum()
        total_emergency_admissions = df_filtered['緊急入院患者数'].sum()
        
        avg_daily_patients = df_filtered['在院患者数'].mean()
        avg_los = total_patient_days / ((total_admissions + total_discharges) / 2) if (total_admissions + total_discharges) > 0 else 0
        bed_turnover = total_discharges / avg_daily_patients if avg_daily_patients > 0 else 0
        emergency_ratio = (total_emergency_admissions / total_admissions * 100) if total_admissions > 0 else 0
        bed_occupancy = (avg_daily_patients / st.session_state.get('total_beds', 612)) * 100
        
        # KPI表示
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "平均在院日数",
                f"{avg_los:.1f}日",
                delta=f"目標: 14.0日"
            )
        
        with col2:
            st.metric(
                "病床利用率",
                f"{bed_occupancy:.1f}%",
                delta=f"目標: {st.session_state.get('target_occupancy', 85)}%"
            )
        
        with col3:
            st.metric(
                "病床回転数",
                f"{bed_turnover:.2f}回",
                delta="期間合計"
            )
        
        with col4:
            st.metric(
                "緊急入院比率",
                f"{emergency_ratio:.1f}%",
                delta=f"{total_emergency_admissions}/{total_admissions}"
            )
        
        # 月別トレンドグラフ
        st.subheader("📈 月別運営指標推移")
        
        try:
            # 月別集計
            df_filtered['年月'] = pd.to_datetime(df_filtered['日付']).dt.to_period('M')
            monthly_ops = df_filtered.groupby('年月').agg({
                '在院患者数': ['mean', 'sum'],
                '入院患者数': 'sum',
                '退院患者数': 'sum',
                '緊急入院患者数': 'sum'
            }).round(2)
            
            monthly_ops.columns = ['日平均在院患者数', '延べ在院日数', '入院患者数', '退院患者数', '緊急入院患者数']
            monthly_ops = monthly_ops.reset_index()
            monthly_ops['年月文字'] = monthly_ops['年月'].astype(str)
            
            # 平均在院日数の計算
            monthly_ops['平均在院日数'] = monthly_ops['延べ在院日数'] / ((monthly_ops['入院患者数'] + monthly_ops['退院患者数']) / 2)
            monthly_ops['病床利用率'] = (monthly_ops['日平均在院患者数'] / st.session_state.get('total_beds', 612)) * 100
            monthly_ops['緊急入院比率'] = (monthly_ops['緊急入院患者数'] / monthly_ops['入院患者数']) * 100
            
            # NaNや無限大の値を処理
            monthly_ops = monthly_ops.replace([np.inf, -np.inf], 0).fillna(0)
            
            # グラフ作成
            if len(monthly_ops) > 0:
                col1, col2 = st.columns(2)
                
                with col1:
                    fig_los = go.Figure()
                    fig_los.add_trace(go.Scatter(
                        x=monthly_ops['年月文字'],
                        y=monthly_ops['平均在院日数'],
                        mode='lines+markers',
                        name='平均在院日数',
                        line=dict(color='#1f77b4', width=3),
                        marker=dict(size=8)
                    ))
                    fig_los.update_layout(
                        title="月別平均在院日数推移",
                        xaxis_title="月",
                        yaxis_title="日数",
                        height=300
                    )
                    st.plotly_chart(fig_los, use_container_width=True)
                
                with col2:
                    fig_occupancy = go.Figure()
                    fig_occupancy.add_trace(go.Scatter(
                        x=monthly_ops['年月文字'],
                        y=monthly_ops['病床利用率'],
                        mode='lines+markers',
                        name='病床利用率',
                        line=dict(color='#2ecc71', width=3),
                        marker=dict(size=8)
                    ))
                    # 目標線
                    target_occupancy = st.session_state.get('target_occupancy', 85)
                    fig_occupancy.add_hline(
                        y=target_occupancy,
                        line_dash="dash",
                        line_color="red",
                        annotation_text=f"目標: {target_occupancy}%"
                    )
                    fig_occupancy.update_layout(
                        title="月別病床利用率推移",
                        xaxis_title="月",
                        yaxis_title="利用率 (%)",
                        height=300
                    )
                    st.plotly_chart(fig_occupancy, use_container_width=True)
            else:
                st.info("月別データが不足しているため、グラフを表示できません。")
        
        except Exception as e:
            st.warning(f"月別トレンドグラフの作成中にエラーが発生しました: {str(e)}")
        
        # 分析インサイト
        st.subheader("💡 分析インサイト")
        
        insight_col1, insight_col2 = st.columns(2)
        
        with insight_col1:
            st.info(f"""
            **平均在院日数について**
            - 現在の平均在院日数: {avg_los:.1f}日
            - 在院日数の短縮は病床回転率向上につながります
            - 適切な在院日数管理により収益最適化が可能です
            """)
        
        with insight_col2:
            st.success(f"""
            **病床利用率について**
            - 現在の病床利用率: {bed_occupancy:.1f}%
            - 目標利用率: {st.session_state.get('target_occupancy', 85)}%
            - 利用率向上により収益増加が期待できます
            """)
        
    except Exception as e:
        st.error(f"運営指標の計算中にエラーが発生しました: {str(e)}")
        st.info("データの形式を確認してください。必要な列（日付、在院患者数、入院患者数など）が存在することを確認してください。")

def display_operational_insights(metrics, selected_period):
    """運営インサイトの表示"""
    try:
        insights = []
        
        # 平均在院日数の評価
        alos = metrics.get('avg_los', 0)
        if alos > 0:
            if alos < 10:
                insights.append("⚠️ 平均在院日数が10日未満と短く、早期退院が適切に行われているか確認が必要です。")
            elif alos < 14:
                insights.append("✅ 平均在院日数が14日未満で良好な水準です。")
            elif alos < 18:
                insights.append("⚠️ 平均在院日数が14-18日の範囲にあり、改善の余地があります。")
            else:
                insights.append("🚨 平均在院日数が18日以上と長期化しています。退院支援の強化が必要です。")
        
        # 病床利用率の評価
        bed_occupancy = metrics.get('bed_occupancy', 0)
        if bed_occupancy > 0:
            if bed_occupancy < 70:
                insights.append("🚨 病床利用率が70%未満と低く、収益性に影響しています。")
            elif bed_occupancy < 80:
                insights.append("⚠️ 病床利用率が70-80%の範囲にあり、改善の余地があります。")
            elif bed_occupancy < 90:
                insights.append("✅ 病床利用率が80-90%で適正な水準です。")
            else:
                insights.append("⚠️ 病床利用率が90%以上と高く、患者受入に影響する可能性があります。")
        
        # 緊急入院率の評価
        emergency_rate = metrics.get('emergency_rate', 0)
        if emergency_rate > 30:
            insights.append("⚠️ 緊急入院率が30%を超えており、計画的な入院管理が困難になっています。")
        elif emergency_rate > 20:
            insights.append("ℹ️ 緊急入院率が20-30%の範囲にあり、適度なバランスが保たれています。")
        
        # 月途中の場合の注意点
        if selected_period in ["当月実績（月途中）", "当月予測（実績+予測）"]:
            if metrics.get('is_partial_month', False):
                adjustment_factor = metrics.get('month_adjustment_factor', 1)
                insights.append(f"ℹ️ 月途中のデータのため、月次換算値（{adjustment_factor:.1f}倍）で評価しています。")
        
        # インサイトの表示
        if insights:
            st.markdown("##### 🔍 運営インサイト")
            for insight in insights:
                if "🚨" in insight:
                    st.error(insight)
                elif "⚠️" in insight:
                    st.warning(insight)
                elif "✅" in insight:
                    st.success(insight)
                else:
                    st.info(insight)
        else:
            st.info("十分なデータが蓄積されると、詳細な運営インサイトが表示されます。")
            
    except Exception as e:
        st.error(f"インサイト生成エラー: {e}")


def display_prediction_confidence(df_actual, period_dates):
    """予測の信頼性情報を表示"""
    try:
        days_elapsed = (period_dates['end_date'] - period_dates['start_date']).days + 1
        days_in_month = pd.Timestamp(period_dates['end_date'].year, period_dates['end_date'].month, 1).days_in_month
        completion_rate = (days_elapsed / days_in_month) * 100
        
        st.info(f"📊 予測の信頼性情報: 月の{completion_rate:.1f}%が経過済み。残り{days_in_month - days_elapsed}日の予測を含みます。")
        
        if completion_rate < 30:
            st.warning("⚠️ 月初のため予測の不確実性が高くなっています。")
        elif completion_rate > 80:
            st.success("✅ 月末に近いため予測の信頼性が高くなっています。")
            
    except Exception as e:
        st.error(f"予測信頼性情報表示エラー: {e}")


def display_revenue_summary(df_filtered, period_dates, selected_period):
    """収益指標のサマリー表示"""
    try:
        # 利用可能な列名を確認
        census_col = None
        for col in ['在院患者数', '入院患者数（在院）', '現在患者数']:
            if col in df_filtered.columns:
                census_col = col
                break
        
        if not census_col:
            st.warning("在院患者数データが見つかりません。")
            return
        
        # 基本メトリクスの計算
        total_patient_days = df_filtered[census_col].sum()
        period_days = (period_dates['end_date'] - period_dates['start_date']).days + 1
        avg_daily_census = total_patient_days / period_days if period_days > 0 else 0
        
        # 収益推計
        avg_admission_fee = st.session_state.get('avg_admission_fee', 55000)
        estimated_revenue = total_patient_days * avg_admission_fee
        
        # 目標比較
        monthly_target_patient_days = st.session_state.get('monthly_target_patient_days', 17000)
        target_revenue = monthly_target_patient_days * avg_admission_fee
        
        # 月次換算（月途中の場合）
        if selected_period in ["当月実績（月途中）", "当月予測（実績+予測）"]:
            days_in_month = pd.Timestamp(period_dates['end_date'].year, period_dates['end_date'].month, 1).days_in_month
            monthly_projected_revenue = estimated_revenue * (days_in_month / period_days) if period_days > 0 else 0
            
            st.metric(
                "月次換算収益", 
                f"¥{monthly_projected_revenue:,.0f}",
                delta=f"実績: ¥{estimated_revenue:,.0f}"
            )
        else:
            st.metric("推計収益", f"¥{estimated_revenue:,.0f}")
        
        # 目標達成率
        if monthly_target_patient_days > 0:
            if selected_period in ["当月実績（月途中）", "当月予測（実績+予測）"]:
                achievement_rate = (monthly_projected_revenue / target_revenue) * 100 if 'monthly_projected_revenue' in locals() else 0
            else:
                achievement_rate = (estimated_revenue / target_revenue) * 100
            
            st.metric("目標達成率", f"{achievement_rate:.1f}%")
        
    except Exception as e:
        st.error(f"収益サマリー計算エラー: {e}")


def display_operations_summary(df_filtered, period_dates, selected_period):
    """運営指標のサマリー表示"""
    try:
        # 利用可能な列名を確認
        census_col = None
        for col in ['在院患者数', '入院患者数（在院）', '現在患者数']:
            if col in df_filtered.columns:
                census_col = col
                break
        
        if not census_col:
            st.warning("在院患者数データが見つかりません。")
            return
        
        # 基本メトリクスの計算
        total_patient_days = df_filtered[census_col].sum()
        period_days = (period_dates['end_date'] - period_dates['start_date']).days + 1
        avg_daily_census = total_patient_days / period_days if period_days > 0 else 0
        
        # 病床利用率
        total_beds = st.session_state.get('total_beds', 612)
        bed_occupancy = (avg_daily_census / total_beds) * 100 if total_beds > 0 else 0
        
        # 入退院数
        admission_col = None
        discharge_col = None
        for col in ['総入院患者数', '入院患者数']:
            if col in df_filtered.columns:
                admission_col = col
                break
        for col in ['総退院患者数', '退院患者数']:
            if col in df_filtered.columns:
                discharge_col = col
                break
        
        # 平均在院日数
        if admission_col and discharge_col:
            total_admissions = df_filtered[admission_col].sum()
            total_discharges = df_filtered[discharge_col].sum()
            alos = total_patient_days / ((total_admissions + total_discharges) / 2) if (total_admissions + total_discharges) > 0 else 0
            st.metric("平均在院日数", f"{alos:.1f}日")
        
        st.metric("病床利用率", f"{bed_occupancy:.1f}%")
        st.metric("日平均在院患者数", f"{avg_daily_census:.1f}人")
        
    except Exception as e:
        st.error(f"運営サマリー計算エラー: {e}")


def display_integrated_charts(df_graph, graph_dates, graph_period):
    """統合チャートの表示"""
    try:
        # 長期間データを使用した統合チャート
        if df_graph.empty:
            st.warning("グラフ用データがありません。")
            return
        
        # 月別集計
        df_graph_copy = df_graph.copy()
        df_graph_copy['年月'] = df_graph_copy['日付'].dt.to_period('M')
        
        # 利用可能な列名を確認
        census_col = None
        for col in ['在院患者数', '入院患者数（在院）', '現在患者数']:
            if col in df_graph_copy.columns:
                census_col = col
                break
        
        if not census_col:
            st.warning("在院患者数データが見つかりません。")
            return
        
        monthly_data = df_graph_copy.groupby('年月').agg({
            census_col: ['sum', 'mean'],
            '総入院患者数': 'sum' if '総入院患者数' in df_graph_copy.columns else lambda x: 0,
            '総退院患者数': 'sum' if '総退院患者数' in df_graph_copy.columns else lambda x: 0
        }).reset_index()
        
        # 列名を整理
        monthly_data.columns = ['年月', '延べ在院日数', '日平均在院患者数', '総入院患者数', '総退院患者数']
        monthly_data['年月str'] = monthly_data['年月'].astype(str)
        
        # 収益計算
        avg_admission_fee = st.session_state.get('avg_admission_fee', 55000)
        monthly_data['推計収益'] = monthly_data['延べ在院日数'] * avg_admission_fee
        
        # 複合グラフの作成
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('延べ在院日数推移', '日平均在院患者数推移', '推計収益推移', '入退院バランス'),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )
        
        # 延べ在院日数
        fig.add_trace(
            go.Scatter(x=monthly_data['年月str'], y=monthly_data['延べ在院日数'], 
                      mode='lines+markers', name='延べ在院日数'),
            row=1, col=1
        )
        
        # 日平均在院患者数
        fig.add_trace(
            go.Scatter(x=monthly_data['年月str'], y=monthly_data['日平均在院患者数'], 
                      mode='lines+markers', name='日平均在院患者数'),
            row=1, col=2
        )
        
        # 推計収益
        fig.add_trace(
            go.Scatter(x=monthly_data['年月str'], y=monthly_data['推計収益'], 
                      mode='lines+markers', name='推計収益'),
            row=2, col=1
        )
        
        # 入退院バランス
        fig.add_trace(
            go.Scatter(x=monthly_data['年月str'], y=monthly_data['総入院患者数'], 
                      mode='lines+markers', name='総入院患者数'),
            row=2, col=2
        )
        fig.add_trace(
            go.Scatter(x=monthly_data['年月str'], y=monthly_data['総退院患者数'], 
                      mode='lines+markers', name='総退院患者数'),
            row=2, col=2
        )
        
        fig.update_layout(
            height=600,
            title_text=f"統合トレンド分析（{graph_period}）",
            showlegend=True
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"統合チャート作成エラー: {e}")


def display_fallback_revenue(df_filtered, period_dates, selected_period):
    """収益管理のフォールバック表示"""
    st.info("簡易版の収益管理を表示しています。")
    
    try:
        # 基本的な収益メトリクス
        census_col = None
        for col in ['在院患者数', '入院患者数（在院）', '現在患者数']:
            if col in df_filtered.columns:
                census_col = col
                break
        
        if census_col:
            total_patient_days = df_filtered[census_col].sum()
            avg_admission_fee = st.session_state.get('avg_admission_fee', 55000)
            estimated_revenue = total_patient_days * avg_admission_fee
            
            st.metric("推計収益", f"¥{estimated_revenue:,.0f}")
            st.metric("延べ在院日数", f"{total_patient_days:,.0f}人日")
        else:
            st.warning("収益計算に必要なデータが見つかりません。")
            
    except Exception as e:
        st.error(f"フォールバック収益表示エラー: {e}")


def normalize_column_names(df):
    """
    データフレームのカラム名を正規化する
    """
    # カラム名マッピング
    column_mapping = {
        # 既存のカラム名 -> 期待されるカラム名
        '在院患者数': '日在院患者数',
        '入院患者数（在院）': '日在院患者数',
        '現在患者数': '日在院患者数',
        
        '入院患者数': '日入院患者数',
        '新入院患者数': '日入院患者数',
        
        '総入院患者数': '日総入院患者数',
        '総退院患者数': '日総退院患者数',
        
        '退院患者数': '日退院患者数',
        
        '緊急入院患者数': '日緊急入院患者数',
        
        '死亡患者数': '日死亡患者数',
        '死亡退院数': '日死亡患者数',
    }
    
    # カラム名を変更
    df_normalized = df.copy()
    for old_name, new_name in column_mapping.items():
        if old_name in df_normalized.columns and new_name not in df_normalized.columns:
            df_normalized = df_normalized.rename(columns={old_name: new_name})
    
    # 必須カラムがない場合は0で埋める
    required_columns = [
        '日入院患者数', '日在院患者数', '日死亡患者数', 
        '日緊急入院患者数', '日総入院患者数', '日総退院患者数', '日退院患者数'
    ]
    
    for col in required_columns:
        if col not in df_normalized.columns:
            # 代替ロジック
            if col == '日総入院患者数' and '日入院患者数' in df_normalized.columns:
                df_normalized[col] = df_normalized['日入院患者数']
            elif col == '日総退院患者数' and '日退院患者数' in df_normalized.columns:
                df_normalized[col] = df_normalized['日退院患者数']
            elif col == '日死亡患者数':
                df_normalized[col] = 0  # デフォルト値
            else:
                df_normalized[col] = 0
    
    return df_normalized


def predict_monthly_completion(df_actual, period_dates):
    """月末までの予測（簡易版）- 列名をintegrated_preprocessingに合わせる"""
    try:
        days_elapsed = (period_dates['end_date'] - period_dates['start_date']).days + 1
        days_in_month = pd.Timestamp(period_dates['end_date'].year, period_dates['end_date'].month, 1).days_in_month
        remaining_days = days_in_month - days_elapsed

        if remaining_days <= 0:
            return pd.DataFrame()

        # integrated_preprocessing.py の出力に存在するであろう主要な列名
        # '在院患者数' の役割は '入院患者数（在院）' が担う
        census_col_actual = '入院患者数（在院）' # 実績の在院患者数
        admission_col_actual = '入院患者数'
        emergency_col_actual = '緊急入院患者数'
        discharge_col_actual = '総退院患者数' # 死亡を含む退院数
        
        # 予測に使用する列リスト
        cols_for_avg = [census_col_actual, admission_col_actual, emergency_col_actual, discharge_col_actual]

        missing_cols = [col for col in cols_for_avg if col not in df_actual.columns]
        if missing_cols:
            st.warning(f"predict_monthly_completion: 予測に必要な列が実績データに不足: {', '.join(missing_cols)}")
            return pd.DataFrame()

        recent_data = df_actual.tail(7)
        if recent_data.empty:
            st.warning("predict_monthly_completion: 予測のための直近データが不足。")
            return pd.DataFrame()
        
        # 日付ごとの合計の平均を計算 (df_actual が日次・病棟・診療科別の場合、まず日次に集計する必要があるかもしれない)
        # ここでは df_actual が既に日次の集計済みデータ、あるいはそれに近いと仮定
        if not recent_data.index.name == '日付' and '日付' in recent_data.columns: # 必要に応じて日付で集計
            daily_sum_recent = recent_data.groupby(pd.to_datetime(recent_data['日付']).dt.date)[cols_for_avg].sum()
            daily_averages = daily_sum_recent.mean()
        else: # 既に日次データと仮定
            daily_averages = recent_data[cols_for_avg].mean()


        predicted_dates = pd.date_range(
            start=period_dates['end_date'] + pd.Timedelta(days=1),
            periods=remaining_days,
            freq='D'
        )

        predicted_data_list = []
        common_ward = df_actual['病棟コード'].mode()[0] if not df_actual['病棟コード'].empty else '予測病棟'
        common_dept = df_actual['診療科名'].mode()[0] if not df_actual['診療科名'].empty else '予測診療科'

        for date_val in predicted_dates:
            day_of_week = date_val.dayofweek
            is_holiday_flag = (day_of_week >= 5)
            if JPHOLIDAY_AVAILABLE and jpholiday.is_holiday(date_val): # JPHOLIDAY_AVAILABLE を参照
                is_holiday_flag = True
            
            weekend_factor = 0.85 if is_holiday_flag else 1.0

            pred_row = {'日付': date_val}
            pred_row[census_col_actual] = daily_averages.get(census_col_actual, 0) * weekend_factor
            pred_row[admission_col_actual] = daily_averages.get(admission_col_actual, 0) * weekend_factor
            pred_row[emergency_col_actual] = daily_averages.get(emergency_col_actual, 0) * weekend_factor
            pred_row[discharge_col_actual] = daily_averages.get(discharge_col_actual, 0) * weekend_factor
            
            # integrated_preprocessing.py の出力に合わせて他の列も生成
            pred_row['在院患者数'] = pred_row[census_col_actual] # '入院患者数（在院）'と同じ
            pred_row['総入院患者数'] = pred_row[admission_col_actual] + pred_row[emergency_col_actual]
            # pred_row['総退院患者数'] は discharge_col_actual が既に総退院患者数を指す想定
            pred_row['退院患者数'] = pred_row[discharge_col_actual] # 死亡を含まない退院患者数が必要な場合は別途計算
            pred_row['死亡患者数'] = 0 # 予測では死亡を0と仮定（または別途予測モデルが必要）
            
            pred_row['病棟コード'] = common_ward
            pred_row['診療科名'] = common_dept
            pred_row['平日判定'] = "休日" if is_holiday_flag else "平日"
            
            predicted_data_list.append(pred_row)
        
        if not predicted_data_list:
            return pd.DataFrame()

        return pd.DataFrame(predicted_data_list)

    except Exception as e:
        st.error(f"予測データ生成エラー (predict_monthly_completion): {e}")
        st.error(traceback.format_exc())
        return pd.DataFrame()

def main():
    """改修版メイン関数（経営ダッシュボードタブ部分のみ抜粋）"""
    # セッション状態の初期化
    if 'data_processed' not in st.session_state:
        st.session_state['data_processed'] = False
    if 'df' not in st.session_state:
        st.session_state['df'] = None

    # 予測関連のセッションステート初期化（新規追加）
    if 'forecast_model_results' not in st.session_state:
        st.session_state.forecast_model_results = {}
    if 'forecast_annual_summary_df' not in st.session_state:
        st.session_state.forecast_annual_summary_df = pd.DataFrame()
    if 'latest_data_date_str' not in st.session_state:
        st.session_state.latest_data_date_str = None

    # ヘッダー
    st.markdown('<h1 class="main-header">🏥 入退院分析ダッシュボード</h1>', unsafe_allow_html=True)
    
    # サイドバー設定
    settings_valid = create_sidebar()
    
    if not settings_valid:
        st.stop()
    
    # メインタブ（6タブ構成に変更 - 予測分析タブを追加）
    if FORECAST_AVAILABLE:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📊 データ処理",
            "💰 経営ダッシュボード", 
            "🔮 予測分析",         # 新規追加
            "📈 詳細分析",
            "📋 データテーブル",
            "📄 出力・予測"
        ])
    else:
        # 予測機能が利用できない場合は従来の5タブ
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 データ処理",
            "💰 経営ダッシュボード", 
            "📈 詳細分析",
            "📋 データテーブル",
            "📄 出力・予測"
        ])

    # データ処理タブ
    with tab1:
        # data_processing_tab.pyの関数を使用
        try:
            create_data_processing_tab()
            
            # 最新データ日付の更新（予測機能用）
            if (st.session_state.get('data_processed', False) and 
                st.session_state.get('df') is not None):
                df = st.session_state['df']
                if '日付' in df.columns:
                    latest_date = df['日付'].max()
                    st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                    
        except Exception as e:
            st.error(f"データ処理タブでエラーが発生しました: {str(e)}")
            st.info("データ処理機能に問題があります。開発者に連絡してください。")
    
    # データが処理されている場合のみ他のタブを有効化
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        
        # 経営ダッシュボードタブ
        with tab2:
            create_management_dashboard_tab()
        
            # オプション：KPI計算の検証機能
            if st.checkbox("🔍 KPI計算検証を表示", key="show_kpi_validation"):
                validate_kpi_calculations()
            
        # 予測分析タブ（新規追加）
        if FORECAST_AVAILABLE:
            with tab3:
                # 依存関係のチェック
                deps_ok = check_forecast_dependencies()
                
                if not deps_ok:
                    st.info("📋 予測機能を使用するには上記のライブラリをインストールしてください。")
                    st.markdown("""
                    ### 🔮 予測機能について
                    このタブでは以下の予測機能が利用できます：
                    
                    #### 📈 利用可能な予測モデル
                    - **単純移動平均**: 過去n日間の平均値を未来に延長
                    - **Holt-Winters**: 季節性とトレンドを考慮した指数平滑法  
                    - **ARIMA**: 自己回帰和分移動平均モデル
                    
                    #### 🎯 予測の活用
                    - 年度末までの患者数予測
                    - 病床利用率の将来推移
                    - 収益計画の立案支援
                    
                    各モデルで年度末までの患者数を予測し、年度総患者数を算出します。
                    """)
                else:
                    display_forecast_analysis_tab()
            
            # 詳細分析タブ（インデックス調整）
            with tab4:
                try:
                    create_detailed_analysis_tab()
                except Exception as e:
                    st.error(f"詳細分析タブでエラーが発生しました: {str(e)}")
                    st.info("詳細分析機能は開発中です。")
            
            # データテーブルタブ（インデックス調整）
            with tab5:
                try:
                    create_data_tables_tab()
                except Exception as e:
                    st.error(f"データテーブルタブでエラーが発生しました: {str(e)}")
                    st.info("データテーブル機能は開発中です。")
            
            # 出力・予測タブ（インデックス調整）
            with tab6:
                create_pdf_output_tab()
        
        else:
            # 予測機能が利用できない場合（従来の構成）
            with tab3:
                try:
                    create_detailed_analysis_tab()
                except Exception as e:
                    st.error(f"詳細分析タブでエラーが発生しました: {str(e)}")
                    st.info("詳細分析機能は開発中です。")
            
            with tab4:
                try:
                    create_data_tables_tab()
                except Exception as e:
                    st.error(f"データテーブルタブでエラーが発生しました: {str(e)}")
                    st.info("データテーブル機能は開発中です。")
            
            with tab5:  
                create_pdf_output_tab()
    
    else:
        # データ未処理の場合の表示（調整）
        with tab2:
            st.info("💰 データを読み込み後、収益管理ダッシュボードが利用可能になります。")
        
        if FORECAST_AVAILABLE:
            with tab3:
                st.info("🔮 データを読み込み後、予測分析が利用可能になります。")
            with tab4:
                st.info("📈 データを読み込み後、詳細分析が利用可能になります。")
            with tab5:
                st.info("📋 データを読み込み後、データテーブルが利用可能になります。")
            with tab6:
                create_pdf_output_tab()
        else:
            with tab3:
                st.info("📈 データを読み込み後、詳細分析が利用可能になります。")
            with tab4:
                st.info("📋 データを読み込み後、データテーブルが利用可能になります。")
            with tab5:  
                create_pdf_output_tab()
            
    # フッター
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            '<div style="text-align: center; color: #666; font-size: 0.8rem;">'
            f'🏥 入院患者数予測アプリ v2.0 | 最終更新: {datetime.datetime.now().strftime("%Y-%m-%d")} | '
            f'⏰ {datetime.datetime.now().strftime("%H:%M:%S")}'
            '</div>',
            unsafe_allow_html=True
        )

if __name__ == "__main__":
    main()
