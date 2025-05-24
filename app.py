import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import io
from datetime import timedelta

# オプショナルライブラリのインポート
try:
    import jpholiday
    JPHOLIDAY_AVAILABLE = True
except ImportError:
    JPHOLIDAY_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

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
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-container {
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid #1f77b4;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """セッション状態の初期化"""
    if 'data_processed' not in st.session_state:
        st.session_state.data_processed = False
    if 'df' not in st.session_state:
        st.session_state.df = None
    if 'total_beds' not in st.session_state:
        st.session_state.total_beds = 612
    if 'target_occupancy' not in st.session_state:
        st.session_state.target_occupancy = 85

def create_sidebar():
    """サイドバーの設定"""
    st.sidebar.header("⚙️ 設定")
    
    # 基本設定
    with st.sidebar.expander("🏥 基本設定", expanded=True):
        total_beds = st.number_input(
            "総病床数", 
            min_value=1, 
            max_value=2000, 
            value=st.session_state.total_beds,
            step=1
        )
        st.session_state.total_beds = total_beds
        
        target_occupancy = st.slider(
            "目標病床利用率 (%)", 
            min_value=50, 
            max_value=100, 
            value=st.session_state.target_occupancy,
            step=1
        )
        st.session_state.target_occupancy = target_occupancy
    
    # システム状況
    with st.sidebar.expander("📊 システム状況", expanded=False):
        st.info(f"データ処理済み: {'✅' if st.session_state.data_processed else '❌'}")
        st.info(f"祝日機能: {'✅' if JPHOLIDAY_AVAILABLE else '❌'}")
        st.info(f"システム監視: {'✅' if PSUTIL_AVAILABLE else '❌'}")
        
        if st.session_state.data_processed and st.session_state.df is not None:
            df = st.session_state.df
            st.success(f"データ件数: {len(df):,}")
            if '日付' in df.columns:
                st.success(f"期間: {df['日付'].min()} ～ {df['日付'].max()}")

def is_holiday(date):
    """祝日・休日判定"""
    if JPHOLIDAY_AVAILABLE:
        return jpholiday.is_holiday(date) or date.weekday() >= 5
    else:
        return date.weekday() >= 5

def create_data_processing_tab():
    """データ処理タブ"""
    st.header("📊 データ処理")
    
    uploaded_file = st.file_uploader(
        "患者データのCSVファイルを選択してください",
        type=['csv'],
        help="日付、患者数、病床情報等を含むCSVファイルをアップロードしてください。"
    )
    
    if uploaded_file is not None:
        st.info(f"ファイル名: {uploaded_file.name}")
        st.info(f"ファイルサイズ: {uploaded_file.size:,} bytes")
        
        if st.button("データを処理", type="primary", use_container_width=True):
            with st.spinner("データを処理中..."):
                try:
                    # CSVファイルの読み込み
                    df = pd.read_csv(uploaded_file)
                    
                    # 基本的なデータ処理
                    if '日付' in df.columns:
                        df['日付'] = pd.to_datetime(df['日付'], errors='coerce')
                        df = df.dropna(subset=['日付'])
                        
                        # 平日・休日判定
                        df['平日判定'] = df['日付'].apply(
                            lambda x: '休日' if is_holiday(x) else '平日'
                        )
                    
                    # 数値列の処理
                    numeric_columns = []
                    for col in df.columns:
                        if '患者数' in col or '入院' in col or '退院' in col:
                            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                            numeric_columns.append(col)
                    
                    # セッション状態に保存
                    st.session_state.df = df
                    st.session_state.data_processed = True
                    
                    st.success("✅ データの処理が完了しました！")
                    
                    # データの概要
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("総レコード数", f"{len(df):,}")
                    with col2:
                        st.metric("データ期間", f"{(df['日付'].max() - df['日付'].min()).days}日")
                    with col3:
                        st.metric("最新データ", df['日付'].max().strftime('%Y-%m-%d'))
                    with col4:
                        st.metric("数値列数", len(numeric_columns))
                    
                    # データプレビュー
                    st.subheader("データプレビュー")
                    st.dataframe(df.head(10), use_container_width=True)
                    
                except Exception as e:
                    st.error(f"データ処理中にエラーが発生しました: {str(e)}")
    else:
        st.info("👆 上記からCSVファイルをアップロードしてください。")

def calculate_kpis(df, start_date=None, end_date=None):
    """KPI計算"""
    if df is None or df.empty:
        return {}
    
    # 期間フィルタ
    if start_date and end_date:
        df_filtered = df[
            (df['日付'] >= pd.to_datetime(start_date)) & 
            (df['日付'] <= pd.to_datetime(end_date))
        ]
    else:
        df_filtered = df
    
    if df_filtered.empty:
        return {}
    
    # 患者数列を特定
    patient_columns = [col for col in df_filtered.columns if '患者数' in col]
    if not patient_columns:
        return {}
    
    main_patient_col = patient_columns[0]  # 最初の患者数列を使用
    
    try:
        # 基本KPI計算
        total_patient_days = df_filtered[main_patient_col].sum()
        period_days = len(df_filtered['日付'].unique())
        avg_daily_census = total_patient_days / period_days if period_days > 0 else 0
        
        # 病床利用率
        total_beds = st.session_state.get('total_beds', 612)
        bed_occupancy_rate = (avg_daily_census / total_beds) * 100 if total_beds > 0 else 0
        
        return {
            'total_patient_days': total_patient_days,
            'avg_daily_census': avg_daily_census,
            'bed_occupancy_rate': bed_occupancy_rate,
            'period_days': period_days,
            'total_beds': total_beds
        }
    except Exception as e:
        st.error(f"KPI計算エラー: {e}")
        return {}

def create_dashboard_tab():
    """ダッシュボードタブ"""
    if not st.session_state.data_processed:
        st.warning("⚠️ まず「データ処理」タブでデータを読み込んでください。")
        return
    
    df = st.session_state.df
    st.header("💰 経営ダッシュボード")
    
    # 期間選択
    if '日付' in df.columns:
        min_date = df['日付'].min().date()
        max_date = df['日付'].max().date()
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("開始日", value=min_date, min_value=min_date, max_value=max_date)
        with col2:
            end_date = st.date_input("終了日", value=max_date, min_value=min_date, max_value=max_date)
        
        # KPI計算
        kpis = calculate_kpis(df, start_date, end_date)
        
        if kpis:
            # KPIメトリクス表示
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "延べ在院日数",
                    f"{kpis['total_patient_days']:,.0f}日",
                    help="選択期間の延べ在院日数"
                )
            
            with col2:
                st.metric(
                    "日平均在院患者数",
                    f"{kpis['avg_daily_census']:.1f}人",
                    help="1日あたりの平均在院患者数"
                )
            
            with col3:
                st.metric(
                    "病床利用率",
                    f"{kpis['bed_occupancy_rate']:.1f}%",
                    delta=f"目標: {st.session_state.target_occupancy}%"
                )
            
            with col4:
                st.metric(
                    "分析期間",
                    f"{kpis['period_days']}日",
                    help="分析対象日数"
                )
            
            # グラフ作成
            st.subheader("📈 患者数推移")
            
            # 日次推移グラフ
            patient_columns = [col for col in df.columns if '患者数' in col]
            if patient_columns:
                daily_data = df.groupby('日付')[patient_columns[0]].sum().reset_index()
                
                fig = px.line(
                    daily_data, 
                    x='日付', 
                    y=patient_columns[0],
                    title="日次患者数推移"
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("データからKPIを計算できませんでした。")

def create_output_tab():
    """出力タブ"""
    st.header("📄 出力・ダウンロード")
    
    if not st.session_state.data_processed:
        st.warning("⚠️ まず「データ処理」タブでデータを読み込んでください。")
        return
    
    df = st.session_state.df
    
    # CSVダウンロード
    if st.button("📥 処理済みデータをダウンロード", use_container_width=True):
        csv = df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="CSVファイルをダウンロード",
            data=csv,
            file_name=f"processed_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    # データサマリー
    st.subheader("📊 データサマリー")
    if df is not None:
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"**総レコード数**: {len(df):,}")
            st.info(f"**列数**: {len(df.columns)}")
            if '日付' in df.columns:
                st.info(f"**データ期間**: {(df['日付'].max() - df['日付'].min()).days}日")
        
        with col2:
            # 基本統計
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                st.info(f"**数値列数**: {len(numeric_cols)}")
                for col in numeric_cols[:3]:  # 最初の3列のみ表示
                    st.info(f"**{col}** 平均: {df[col].mean():.1f}")

def main():
    """メイン関数"""
    # セッション状態初期化
    initialize_session_state()
    
    # ヘッダー
    st.markdown('<h1 class="main-header">🏥 入退院分析ダッシュボード</h1>', unsafe_allow_html=True)
    
    # サイドバー
    create_sidebar()
    
    # メインタブ
    tab1, tab2, tab3 = st.tabs([
        "📊 データ処理",
        "💰 経営ダッシュボード", 
        "📄 出力・ダウンロード"
    ])
    
    with tab1:
        create_data_processing_tab()
    
    with tab2:
        create_dashboard_tab()
    
    with tab3:
        create_output_tab()
    
    # フッター
    st.markdown("---")
    st.markdown(
        '<div style="text-align: center; color: #666; font-size: 0.9rem;">'
        f'🏥 入退院分析ダッシュボード | 最終更新: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        '</div>',
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
