import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import jpholiday
import io
import zipfile
import tempfile
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import psutil
import time
from pdf_output_tab import create_pdf_output_tab

# カスタムモジュールのインポート
try:
    from integrated_preprocessing import integrated_preprocess_data
    from loader import load_files, read_excel_cached
    from revenue_dashboard_tab import create_revenue_dashboard_section
    from analysis_tabs import create_detailed_analysis_tab, create_data_tables_tab, create_output_prediction_tab
    from data_processing_tab import create_data_processing_tab
        
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.error("以下のファイルが存在することを確認してください：")
    st.error("- integrated_preprocessing.py")
    st.error("- loader.py") 
    st.error("- revenue_dashboard_tab.py")
    st.error("- analysis_tabs.py")
    st.error("- data_processing_tab.py")
    st.stop()

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

# ページ設定
st.set_page_config(
    page_title="入退院分析ダッシュボード",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS（フォントサイズ拡大版）
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
    
    /* メトリクス */
    .metric-container .metric-value {
        font-size: 2.5rem !important;  /* 約40%増 */
    }
    
    .metric-container .metric-label {
        font-size: 1.1rem !important;  /* 約30%増 */
    }
    
    /* KPIカード */
    .kpi-card {
        background-color: white;
        padding: 1.5rem !important;  /* 余白も拡大 */
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
    
    /* サイドバー */
    .css-1d391kg {  /* サイドバーのセレクタ */
        font-size: 16px !important;  /* サイドバーは少し控えめに */
    }
    
    .sidebar .stSelectbox label,
    .sidebar .stNumberInput label,
    .sidebar .stSlider label,
    .sidebar .stDateInput label {
        font-size: 16px !important;
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
        min-height: 3.5rem !important;  /* タブの高さを拡大 */
        white-space: pre-wrap;
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 0.8rem 1.2rem !important;  /* パディングを拡大 */
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
    .stSelectbox > div > div > div {
        font-size: 16px !important;
    }
    
    .stNumberInput > div > div > input {
        font-size: 16px !important;
    }
    
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
    
    /* メトリック表示 */
    [data-testid="metric-container"] {
        background-color: white;
        border: 1px solid #e1e5e9;
        padding: 1rem 1.2rem !important;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    [data-testid="metric-container"] > label {
        font-size: 16px !important;
        font-weight: 600 !important;
        color: #262730 !important;
    }
    
    [data-testid="metric-container"] > div {
        font-size: 2rem !important;
        font-weight: 600 !important;
        color: #262730 !important;
    }
    
    [data-testid="metric-container"] > div > div {
        font-size: 1rem !important;
        margin-top: 0.2rem !important;
    }
    
    /* 列（columns）の調整 */
    .metric-container {
        display: flex;
        flex-wrap: wrap;
        gap: 1.5rem !important;  /* ギャップを拡大 */
        margin-bottom: 2rem;
    }
    
    /* フッター */
    .stMarkdown div[style*="text-align: center"] {
        font-size: 14px !important;  /* フッターは控えめに */
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
    }
</style>
""", unsafe_allow_html=True)

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
        
        # 目標値の表示
        st.markdown("### 📈 目標値サマリー")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("延べ在院日数", f"{monthly_target_patient_days:,}人日")
            st.metric("新入院患者数", f"{monthly_target_admissions:,}人")
        with col2:
            st.metric("推定月間収益", f"{monthly_revenue_estimate:,.0f}円")
            st.metric("病床稼働率", f"{bed_occupancy_rate:.1%}")

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
    """経営ダッシュボードタブの作成（期間選択機能付き）"""
    if 'df' not in st.session_state or st.session_state['df'] is None:
        st.warning("⚠️ データが読み込まれていません。先にデータ処理タブでファイルをアップロードしてください。")
        return
    
    df = st.session_state['df']
    targets_df = st.session_state.get('target_data', None)
    
    st.header("💰 経営ダッシュボード")
    
    # 期間選択UI（上部に配置）- KPIカード用とグラフ用を分離
    st.markdown("### 📊 表示期間設定")
    
    period_col1, period_col2, col3 = st.columns(3)
    
    with period_col1:
        st.markdown("#### KPIカード期間")
        kpi_period_options = [
            "直近30日",
            "前月完了分", 
            "当月実績（月途中）",
            "当月予測（実績+予測）"
        ]
        
        selected_kpi_period = st.radio(
            "",
            kpi_period_options,
            index=get_default_period_index(df),
            horizontal=False,
            key="kpi_period_selector",
            help="KPIカードは短期的な状況把握に適しています"
        )
    
    with period_col2:
        st.markdown("#### グラフ期間")
        graph_period_options = [
            "直近12ヶ月",
            "直近6ヶ月",
            "直近3ヶ月",
            "カスタム期間"
        ]
        
        selected_graph_period = st.radio(
            "",
            graph_period_options,
            index=0,
            horizontal=False,
            key="graph_period_selector",
            help="グラフは長期的なトレンド分析に適しています"
        )
        
        # カスタム期間の場合の日付選択
        if selected_graph_period == "カスタム期間":
            custom_start = st.date_input(
                "開始日",
                value=df['日付'].max() - pd.Timedelta(days=365),
                key="custom_graph_start"
            )
            custom_end = st.date_input(
                "終了日", 
                value=df['日付'].max(),
                key="custom_graph_end"
            )
    
    with col3:
        # 期間情報の表示
        kpi_period_info = get_period_info(df, selected_kpi_period)
        if kpi_period_info['warning']:
            st.warning(kpi_period_info['warning'])
        else:
            st.info(kpi_period_info['description'])
    
    st.markdown("---")
    
    # セクション選択
    dashboard_section = st.selectbox(
        "表示セクション",
        ["概要ダッシュボード", "収益管理", "運営指標", "統合ビュー"],
        key="dashboard_section"
    )
    
    # KPI用とグラフ用でそれぞれデータをフィルタリング
    df_kpi_filtered, kpi_period_dates = filter_data_by_period(df, selected_kpi_period)
    df_graph_filtered, graph_period_dates = filter_data_by_graph_period(df, selected_graph_period)
    
    if df_kpi_filtered.empty:
        st.warning("選択された期間にデータがありません。")
        return
    
    # 各セクションの表示（修正版）
    if dashboard_section == "概要ダッシュボード":
        display_overview_dashboard_modified(
            df_kpi_filtered, kpi_period_dates, selected_kpi_period,
            df_graph_filtered, graph_period_dates, selected_graph_period,
            targets_df
        )
    elif dashboard_section == "収益管理":
        display_revenue_management_modified(
            df_kpi_filtered, kpi_period_dates, selected_kpi_period,
            df_graph_filtered, graph_period_dates, selected_graph_period,
            targets_df
        )
    elif dashboard_section == "運営指標":
        display_operations_metrics_modified(
            df_kpi_filtered, kpi_period_dates, selected_kpi_period,
            df_graph_filtered, graph_period_dates, selected_graph_period,
            targets_df
        )
    else:  # 統合ビュー
        display_integrated_view_modified(
            df_kpi_filtered, kpi_period_dates, selected_kpi_period,
            df_graph_filtered, graph_period_dates, selected_graph_period,
            targets_df
        )

def get_default_period_index(df):
    """月途中かどうかに基づいてデフォルトの期間を決定"""
    latest_date = df['日付'].max()
    current_date = pd.Timestamp.now()
    
    # 最新データが今月のもので、かつ月の前半（15日以前）の場合
    if (latest_date.month == current_date.month and 
        latest_date.year == current_date.year and 
        latest_date.day <= 15):
        return 1  # "前月完了分"をデフォルト
    else:
        return 0  # "直近30日"をデフォルト

def get_period_info(df, selected_period):
    """期間情報と警告メッセージを取得"""
    latest_date = df['日付'].max()
    current_date = pd.Timestamp.now()
    
    if selected_period == "直近30日":
        start_date = latest_date - pd.Timedelta(days=29)
        return {
            'description': f"📊 {start_date.strftime('%m/%d')} - {latest_date.strftime('%m/%d')}",
            'warning': None
        }
    
    elif selected_period == "前月完了分":
        prev_month_start = (latest_date.replace(day=1) - pd.Timedelta(days=1)).replace(day=1)
        prev_month_end = latest_date.replace(day=1) - pd.Timedelta(days=1)
        return {
            'description': f"📅 {prev_month_start.strftime('%m月')}完了分",
            'warning': None
        }
    
    elif selected_period == "当月実績（月途中）":
        current_month_start = latest_date.replace(day=1)
        days_elapsed = (latest_date - current_month_start).days + 1
        return {
            'description': f"📆 {latest_date.strftime('%m月')}{days_elapsed}日分",
            'warning': "⚠️ 月途中のため参考値です" if days_elapsed < 20 else None
        }
    
    else:  # 当月予測
        current_month_start = latest_date.replace(day=1)
        days_elapsed = (latest_date - current_month_start).days + 1
        return {
            'description': f"🔮 {latest_date.strftime('%m月')}予測値",
            'warning': "📊 実績+予測の組み合わせです" if days_elapsed < 25 else None
        }

def filter_data_by_period(df, selected_period):
    """選択された期間でデータをフィルタリング"""
    latest_date = df['日付'].max()
    
    if selected_period == "直近30日":
        start_date = latest_date - pd.Timedelta(days=29)
        end_date = latest_date
        df_filtered = df[(df['日付'] >= start_date) & (df['日付'] <= end_date)].copy()
        
    elif selected_period == "前月完了分":
        prev_month_start = (latest_date.replace(day=1) - pd.Timedelta(days=1)).replace(day=1)
        prev_month_end = latest_date.replace(day=1) - pd.Timedelta(days=1)
        df_filtered = df[(df['日付'] >= prev_month_start) & (df['日付'] <= prev_month_end)].copy()
        start_date, end_date = prev_month_start, prev_month_end
        
    elif selected_period == "当月実績（月途中）":
        current_month_start = latest_date.replace(day=1)
        df_filtered = df[(df['日付'] >= current_month_start) & (df['日付'] <= latest_date)].copy()
        start_date, end_date = current_month_start, latest_date
        
    else:  # 当月予測
        current_month_start = latest_date.replace(day=1)
        df_filtered = df[(df['日付'] >= current_month_start) & (df['日付'] <= latest_date)].copy()
        start_date, end_date = current_month_start, latest_date
        
    return df_filtered, {'start_date': start_date, 'end_date': end_date, 'period_type': selected_period}

def filter_data_by_graph_period(df, selected_graph_period):
    """グラフ用の長期間データフィルタリング"""
    latest_date = df['日付'].max()
    
    if selected_graph_period == "直近12ヶ月":
        start_date = latest_date - pd.Timedelta(days=365)
        end_date = latest_date
    elif selected_graph_period == "直近6ヶ月":
        start_date = latest_date - pd.Timedelta(days=180)
        end_date = latest_date
    else:  # 直近3ヶ月
        start_date = latest_date - pd.Timedelta(days=90)
        end_date = latest_date
    
    # データ開始日より前にならないように調整
    actual_start_date = max(start_date, df['日付'].min())
    
    df_filtered = df[(df['日付'] >= actual_start_date) & (df['日付'] <= end_date)].copy()
    
    return df_filtered, {
        'start_date': actual_start_date,
        'end_date': end_date,
        'period_type': selected_graph_period
    }
    
def display_overview_dashboard_modified(df_kpi, kpi_dates, kpi_period,
                                       df_graph, graph_dates, graph_period, targets_df):
    """修正版：概要ダッシュボードの表示（KPIとグラフで異なる期間を使用）"""
    try:
        # dashboard_overview_tab から必要な関数をインポート
        from dashboard_overview_tab import display_kpi_cards_only, display_trend_graphs_only
        
        # 基本設定を取得
        total_beds = st.session_state.get('total_beds', 612)
        target_occupancy = st.session_state.get('bed_occupancy_rate', 0.85) * 100
        
        # KPIカードの表示（短期間データ使用）
        st.markdown("### 📊 KPIカード（" + kpi_period + "）")
        
        if kpi_period == "当月予測（実績+予測）":
            df_kpi_with_prediction = add_monthly_prediction(df_kpi, kpi_dates)
            display_kpi_cards_only(df_kpi_with_prediction, kpi_dates['start_date'], 
                                 kpi_dates['end_date'], total_beds, target_occupancy)
        else:
            display_kpi_cards_only(df_kpi, kpi_dates['start_date'], 
                                 kpi_dates['end_date'], total_beds, target_occupancy)
        
        display_period_specific_notes(kpi_period, kpi_dates) # この関数も app.py 内にあるか確認
        
        st.markdown("---")
        
        # グラフの表示（長期間データ使用）
        st.markdown("### 📈 トレンドグラフ（" + graph_period + "）")
        display_trend_graphs_only(df_graph, graph_dates['start_date'], 
                                graph_dates['end_date'], total_beds, target_occupancy)
        
    except ImportError as e: # 具体的なエラーも表示すると良いでしょう
        st.error(f"概要ダッシュボード機能のインポートに失敗しました: {e}")
        st.error("dashboard_overview_tab.pyに必要な関数 (display_kpi_cards_only, display_trend_graphs_only) が存在するか確認してください。")
        # display_fallback_overview(df_kpi, kpi_dates, kpi_period) # フォールバック処理

def display_revenue_management(df_filtered, period_dates, selected_period, targets_df):
    """収益管理セクションの表示"""
    try:
        from revenue_dashboard_tab import create_revenue_dashboard_section
        
        # 期間情報を含めて収益管理を表示
        st.subheader(f"💰 収益管理 - {selected_period}")
        
        if selected_period == "当月予測（実績+予測）":
            df_with_prediction = add_monthly_prediction(df_filtered, period_dates)
            create_revenue_dashboard_section(df_with_prediction, targets_df)
            
            # 予測の信頼性情報
            display_prediction_confidence(df_filtered, period_dates)
        else:
            create_revenue_dashboard_section(df_filtered, targets_df)
            
    except ImportError:
        st.error("収益管理機能が利用できません。")
        display_fallback_revenue(df_filtered, period_dates, selected_period)

def display_operations_metrics(df_filtered, period_dates, selected_period, targets_df):
    """運営指標セクションの表示"""
    st.subheader(f"📊 運営指標 - {selected_period}")
    
    # 基本メトリクスの計算
    metrics = calculate_period_metrics(df_filtered, selected_period, period_dates)
    
    # KPI表示
    display_kpi_cards(metrics, selected_period)
    
    # 期間比較グラフ
    if st.checkbox("📈 期間比較グラフを表示", value=True, key="show_comparison_charts"):
        display_period_comparison_charts(df_filtered, period_dates, selected_period)
    
    # 運営インサイト
    display_operational_insights(metrics, selected_period)

def display_integrated_view(df_filtered, period_dates, selected_period, targets_df):
    """統合ビューの表示"""
    st.subheader(f"🔍 統合ビュー - {selected_period}")
    
    # 概要メトリクス（簡約版）
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 💰 収益指標")
        display_revenue_summary(df_filtered, period_dates, selected_period)
    
    with col2:
        st.markdown("#### 📊 運営指標")
        display_operations_summary(df_filtered, period_dates, selected_period)
    
    # 統合チャート
    st.markdown("#### 📈 統合トレンド")
    display_integrated_charts(df_filtered, period_dates, selected_period)

def add_monthly_prediction(df_filtered, period_dates):
    """月末までの予測データを追加"""
    try:
        from forecast import predict_monthly_completion
        
        # 現在の実績から月末までを予測
        predicted_data = predict_monthly_completion(df_filtered, period_dates)
        
        if predicted_data is not None and not predicted_data.empty:
            # 実績データに予測フラグを追加
            df_filtered['データ種別'] = '実績'
            predicted_data['データ種別'] = '予測'
            
            # 実績と予測を結合
            df_combined = pd.concat([df_filtered, predicted_data], ignore_index=True)
            return df_combined
        else:
            df_filtered['データ種別'] = '実績'
            return df_filtered
            
    except ImportError:
        st.warning("予測機能が利用できません。実績データのみ表示します。")
        df_filtered['データ種別'] = '実績'
        return df_filtered

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
    """KPIカードの表示"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if metrics.get('is_partial_month'):
            st.metric(
                "平均在院日数", 
                f"{metrics['avg_los']:.1f}日",
                help="現在の実績値"
            )
            st.caption(f"期間実績: {metrics['period_days']}日分")
        else:
            st.metric("平均在院日数", f"{metrics['avg_los']:.1f}日")
    
    with col2:
        if metrics.get('is_partial_month'):
            st.metric(
                "月次換算患者数", 
                f"{metrics['monthly_projected_patient_days']:,.0f}人日",
                help="月末まで同じペースが続いた場合の予測値"
            )
            st.caption(f"実績: {metrics['total_patient_days']:,.0f}人日")
        else:
            st.metric("延べ在院患者数", f"{metrics['total_patient_days']:,.0f}人日")
    
    with col3:
        st.metric("病床利用率", f"{metrics['bed_occupancy']:.1f}%")
        if metrics.get('is_partial_month'):
            st.caption("現在のペース")
    
    with col4:
        if metrics.get('is_partial_month'):
            st.metric(
                "月次換算入院数", 
                f"{metrics['monthly_projected_admissions']:,.0f}人",
                help="月末まで同じペースが続いた場合の予測値"
            )
            st.caption(f"実績: {metrics['total_admissions']:,.0f}人")
        else:
            st.metric("総入院患者数", f"{metrics['total_admissions']:,.0f}人")

def display_period_specific_notes(selected_period, period_dates):
    """期間別の特別な注意事項"""
    if selected_period == "当月実績（月途中）":
        days_elapsed = (period_dates['end_date'] - period_dates['start_date']).days + 1
        if days_elapsed < 15:
            st.info("💡 月前半のデータのため、月次トレンド分析は限定的です。前月完了分または直近30日での分析をお勧めします。")
    
    elif selected_period == "当月予測（実績+予測）":
        st.info("🔮 予測値が含まれています。実際の結果と異なる場合があります。")
    
    elif selected_period == "前月完了分":
        st.success("✅ 完了月のデータのため、正確な月次分析が可能です。")

def display_fallback_overview(df_filtered, period_dates, selected_period):
    """フォールバック版の概要表示"""
    st.info("簡易版の概要を表示しています。")
    
    metrics = calculate_period_metrics(df_filtered, selected_period, period_dates)
    display_kpi_cards(metrics, selected_period)

# ===== 月次予測関連の関数（forecast.py に実装予定） =====

def predict_monthly_completion(df_actual, period_dates):
    """月末までの予測（簡易版）"""
    try:
        # 現在の日数と月の総日数
        days_elapsed = (period_dates['end_date'] - period_dates['start_date']).days + 1
        days_in_month = pd.Timestamp(period_dates['end_date'].year, period_dates['end_date'].month, 1).days_in_month
        remaining_days = days_in_month - days_elapsed
        
        if remaining_days <= 0:
            return pd.DataFrame()  # 既に月末
        
        # 直近7日間の平均を使用して予測
        recent_data = df_actual.tail(7)
        daily_averages = recent_data.groupby('日付')[['在院患者数', '入院患者数', '退院患者数', '緊急入院患者数']].sum().mean()
        
        # 残り日数分の予測データを生成
        predicted_dates = pd.date_range(
            start=period_dates['end_date'] + pd.Timedelta(days=1),
            periods=remaining_days,
            freq='D'
        )
        
        predicted_data = []
        for date in predicted_dates:
            # 曜日効果を考慮（簡易版）
            day_of_week = date.dayofweek
            weekend_factor = 0.7 if day_of_week >= 5 else 1.0  # 土日は70%
            
            predicted_data.append({
                '日付': date,
                '在院患者数': daily_averages['在院患者数'] * weekend_factor,
                '入院患者数': daily_averages['入院患者数'] * weekend_factor,
                '退院患者数': daily_averages['退院患者数'] * weekend_factor,
                '緊急入院患者数': daily_averages['緊急入院患者数'] * weekend_factor,
                '病棟コード': '予測',
                '診療科名': '予測'
            })
        
        return pd.DataFrame(predicted_data)
        
    except Exception as e:
        print(f"予測データ生成エラー: {e}")
        return pd.DataFrame()

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

def main():
    """メイン関数"""
    
    # セッション状態の初期化
    if 'data_processed' not in st.session_state:
        st.session_state['data_processed'] = False
    if 'df' not in st.session_state:
        st.session_state['df'] = None
    
    # ヘッダー
    st.markdown('<h1 class="main-header">🏥 入退院分析ダッシュボード</h1>', unsafe_allow_html=True)
    
    # サイドバー設定
    settings_valid = create_sidebar()
    
    if not settings_valid:
        st.stop()
    
    # メインタブ（5タブ構成）
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 データ処理",
        "💰 経営ダッシュボード", 
        "📈 詳細分析",
        "📋 データテーブル",
        "📄 出力・予測"
    ])
    
    with tab1:
        # data_processing_tab.pyの関数を使用
        try:
            create_data_processing_tab()
        except Exception as e:
            st.error(f"データ処理タブでエラーが発生しました: {str(e)}")
            st.info("データ処理機能に問題があります。開発者に連絡してください。")
    
    # データが処理されている場合のみ他のタブを有効化
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        with tab2:
            create_management_dashboard_tab()
        
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
        
        with tab5:  # 出力・予測タブ
            create_pdf_output_tab()
    
    else:
        # データ未処理の場合の表示
        with tab2:
            st.info("💰 データを読み込み後、収益管理ダッシュボードが利用可能になります。")
        
        with tab3:
            st.info("📈 データを読み込み後、詳細分析が利用可能になります。")
        
        with tab4:
            st.info("📋 データを読み込み後、データテーブルが利用可能になります。")
        
        with tab5:  # PDF出力タブは常に表示（データ未処理でも警告が表示される）
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