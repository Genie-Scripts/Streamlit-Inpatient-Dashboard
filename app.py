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

from scipy import stats

# ===== 設定値とスタイルの読み込み =====
from config import *
from style import inject_global_css
from utils import safe_date_filter, initialize_all_mappings

# データ永続化機能のインポート
from data_persistence import (
    auto_load_data, save_data_to_file, load_data_from_file, 
    get_data_info, delete_saved_data, get_file_sizes,
    save_settings_to_file, load_settings_from_file,
    get_backup_info, restore_from_backup
)

# ページ設定
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# グローバルCSS適用
inject_global_css(FONT_SCALE)

# カスタムモジュールのインポート
try:
    from integrated_preprocessing import integrated_preprocess_data
    from loader import load_files
    from revenue_dashboard_tab import create_revenue_dashboard_section
    from analysis_tabs import create_detailed_analysis_tab, create_data_tables_tab
    from data_processing_tab import create_data_processing_tab
    from pdf_output_tab import create_pdf_output_tab
    from forecast_analysis_tab import display_forecast_analysis_tab
    from kpi_calculator import calculate_kpis
    FORECAST_AVAILABLE = True
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    FORECAST_AVAILABLE = False
    st.stop()

from data_persistence import (
    auto_load_data, save_data_to_file, load_data_from_file, 
    get_data_info, delete_saved_data, get_file_sizes,
    save_settings_to_file, load_settings_from_file,
    get_backup_info, restore_from_backup
)

def create_sidebar_period_settings():
    """サイドバーの期間設定（改修版）"""
    with st.sidebar.expander("📅 分析期間設定", expanded=True):
        if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
            df = st.session_state.df
            min_date = df['日付'].min().date()
            max_date = df['日付'].max().date()
            
            # 期間設定モード選択
            period_mode = st.radio(
                "期間設定方法",
                ["プリセット期間", "カスタム期間"],
                key="period_mode",
                help="プリセットまたはカスタム期間を選択"
            )
            
            if period_mode == "プリセット期間":
                preset_period = st.selectbox(
                    "期間選択",
                    PERIOD_OPTIONS,
                    index=0,
                    key="global_preset_period",
                    help="事前定義された期間から選択"
                )
                st.session_state.analysis_period_type = "preset"
                st.session_state.analysis_preset_period = preset_period
                
                # プリセット期間に基づく日付計算
                start_date, end_date = calculate_preset_period_dates(df, preset_period)
                st.session_state.analysis_start_date = start_date
                st.session_state.analysis_end_date = end_date
                
                st.info(f"📊 期間: {start_date.strftime('%Y/%m/%d')} - {end_date.strftime('%Y/%m/%d')}")
                
            else:  # カスタム期間
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.date_input(
                        "開始日",
                        value=st.session_state.get('analysis_start_date', max_date - pd.Timedelta(days=30)),
                        min_value=min_date,
                        max_value=max_date,
                        key="custom_start_date",
                        help="分析開始日を選択してください"
                    )
                    
                with col2:
                    end_date = st.date_input(
                        "終了日",
                        value=st.session_state.get('analysis_end_date', max_date),
                        min_value=min_date,
                        max_value=max_date,
                        key="custom_end_date",
                        help="分析終了日を選択してください"
                    )
                
                st.session_state.analysis_period_type = "custom"
                st.session_state.analysis_start_date = start_date
                st.session_state.analysis_end_date = end_date
                
                if start_date <= end_date:
                    period_days = (end_date - start_date).days + 1
                    st.success(f"✅ 選択期間: {period_days}日間")
                else:
                    st.error("開始日は終了日より前に設定してください")
            
            # 全タブに適用ボタン
            if st.button("🔄 全タブに期間を適用", key="apply_global_period", use_container_width=True):
                st.session_state.period_applied = True
                st.success("期間設定を全タブに適用しました")
                st.experimental_rerun()
                
        else:
            st.info("データを読み込み後に期間設定が利用できます。")

def calculate_preset_period_dates(df, preset_period):
    """プリセット期間から具体的な日付を計算"""
    latest_date = df['日付'].max()
    
    if preset_period == "直近30日":
        start_date = latest_date - pd.Timedelta(days=29)
        end_date = latest_date
    elif preset_period == "前月完了分":
        prev_month_start = (latest_date.replace(day=1) - pd.Timedelta(days=1)).replace(day=1)
        prev_month_end = latest_date.replace(day=1) - pd.Timedelta(days=1)
        start_date = prev_month_start
        end_date = prev_month_end
    elif preset_period == "今年度":
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
    
    return start_date.date(), end_date.date()

def get_analysis_period():
    """現在の分析期間を取得"""
    if not st.session_state.get('data_processed', False):
        return None, None, "データなし"
    
    start_date = st.session_state.get('analysis_start_date')
    end_date = st.session_state.get('analysis_end_date')
    period_type = st.session_state.get('analysis_period_type', 'preset')
    
    if start_date and end_date:
        return pd.to_datetime(start_date), pd.to_datetime(end_date), period_type
    
    # デフォルト値
    df = st.session_state.get('df')
    if df is not None:
        latest_date = df['日付'].max()
        default_start = latest_date - pd.Timedelta(days=29)
        return default_start, latest_date, "デフォルト"
    
    return None, None, "エラー"

def filter_data_by_analysis_period(df):
    """分析期間でデータをフィルタリング"""
    start_date, end_date, period_type = get_analysis_period()
    
    if start_date is None or end_date is None:
        return df
    
    # データをフィルタリング
    filtered_df = df[
        (df['日付'] >= start_date) & 
        (df['日付'] <= end_date)
    ].copy()
    
    return filtered_df
    
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
        st.subheader("📊 トレンド分析")
        if monthly_data.empty or len(monthly_data) < ANALYSIS_SETTINGS['trend_min_periods']:
            st.info(f"トレンド分析には{ANALYSIS_SETTINGS['trend_min_periods']}期間以上の月次データが必要です。")
            return

        y_col = '日平均在院患者数'
        if y_col not in monthly_data.columns:
            st.error(f"トレンド分析に必要な列 '{y_col}' が月次データにありません。")
            return
        
        monthly_data_cleaned = monthly_data.replace([np.inf, -np.inf], np.nan).dropna(subset=[y_col])
        if len(monthly_data_cleaned) < 2:
            st.info("有効なデータポイントが2未満のため、トレンド分析を実行できません。")
            return

        x = np.arange(len(monthly_data_cleaned))
        y = monthly_data_cleaned[y_col].values
        
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        
        # 統計的有意性の判定
        is_significant = p_value < ANALYSIS_SETTINGS['statistical_significance']
        
        trend_text = "➡️ 明確なトレンドなし"
        if is_significant:
            if slope > 0:
                trend_text = "📈 統計的に有意な上昇トレンド"
            elif slope < 0:
                trend_text = "📉 統計的に有意な下降トレンド"

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("トレンド", trend_text, f"傾き: {slope:.2f}人/月")
        with col2:
            st.metric("相関係数 (R)", f"{r_value:.3f}", help="1に近いほど強い相関")
        with col3:
            st.metric("p値", f"{p_value:.3f}", help=f"{ANALYSIS_SETTINGS['statistical_significance']}未満で統計的に有意")
        
        # トレンド線表示オプション
        if st.checkbox("📊 トレンド線を表示", key="ops_trend_show_trend_line"):
            trend_line_values = intercept + slope * x
            
            fig_trend = go.Figure()
            fig_trend.add_trace(
                go.Scatter(
                    x=monthly_data_cleaned['年月str'], y=y,
                    mode='lines+markers', name='実績',
                    line=dict(color=DASHBOARD_COLORS['primary_blue'])
                )
            )
            fig_trend.add_trace(
                go.Scatter(
                    x=monthly_data_cleaned['年月str'], y=trend_line_values,
                    mode='lines', name='トレンド線', 
                    line=dict(dash='dash', color=DASHBOARD_COLORS['danger_red'])
                )
            )
            
            fig_trend.update_layout(
                title="トレンド分析と予測",
                xaxis_title="年月", 
                yaxis_title=y_col, 
                height=CHART_HEIGHT
            )
            st.plotly_chart(fig_trend, use_container_width=True)
            
            # 統計情報の詳細表示
            with st.expander("📊 詳細な統計情報", expanded=False):
                st.write(f"**回帰式**: y = {slope:.3f}x + {intercept:.3f}")
                st.write(f"**決定係数 (R²)**: {r_value**2:.3f}")
                st.write(f"**標準誤差**: {std_err:.3f}")
                st.write(f"**統計的有意性**: {'有意' if is_significant else '非有意'}")

    except ImportError:
        st.info("トレンド分析にはscipyライブラリが必要です。")
    except Exception as e:
        st.error(f"トレンド分析中にエラーが発生しました: {e}")

def display_period_comparison_charts(df_graph, graph_dates, graph_period):
    """期間比較チャートの表示"""
    try:
        if df_graph.empty:
            st.warning("比較用データがありません。")
            return
        
        df_graph_copy = df_graph.copy()
        df_graph_copy['日付'] = pd.to_datetime(df_graph_copy['日付'])
        df_graph_copy['年月'] = df_graph_copy['日付'].dt.to_period('M')
        
        census_col = '入院患者数（在院）'
        
        if census_col not in df_graph_copy.columns:
            st.warning(f"期間比較チャートのための主要な在院患者数データが見つかりません。")
            return
            
        monthly_data = df_graph_copy.groupby('年月').agg({
            census_col: 'mean'
        }).reset_index()
        
        monthly_data.columns = ['年月', '日平均在院患者数']
        monthly_data['年月str'] = monthly_data['年月'].astype(str)
        
        if len(monthly_data) >= ANALYSIS_SETTINGS['trend_min_periods']:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=monthly_data['年月str'], 
                    y=monthly_data['日平均在院患者数'],
                    mode='lines+markers', 
                    name='日平均在院患者数',
                    line=dict(color=DASHBOARD_COLORS['primary_blue'], width=3), 
                    marker=dict(size=8)
                )
            )
            
            # 平均線
            avg_census = monthly_data['日平均在院患者数'].mean()
            fig.add_hline(
                y=avg_census, 
                line_dash="dash", 
                line_color=DASHBOARD_COLORS['danger_red'],
                annotation_text=f"平均: {avg_census:.1f}人"
            )
            
            # 目標線
            total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
            bed_occupancy_rate_target = st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE)
            target_census = total_beds * bed_occupancy_rate_target
            fig.add_hline(
                y=target_census, 
                line_dash="dot", 
                line_color=DASHBOARD_COLORS['success_green'],
                annotation_text=f"目標: {target_census:.1f}人"
            )
            
            fig.update_layout(
                title=f"運営指標 月次トレンド（{graph_period}）",
                xaxis_title="年月", 
                yaxis_title="日平均在院患者数",
                height=CHART_HEIGHT
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # メトリクス表示
            col1, col2, col3 = st.columns(3)
            with col1:
                target_diff = ((avg_census / target_census) - 1) * 100 if target_census > 0 else 0
                st.metric(
                    "期間平均", 
                    f"{avg_census:.1f}人",
                    delta=f"{target_diff:.1f}% (対目標)"
                )
            with col2:
                if len(monthly_data) >= 2:
                    latest_month_val = monthly_data.iloc[-1]['日平均在院患者数']
                    prev_month_val = monthly_data.iloc[-2]['日平均在院患者数']
                    change_rate = ((latest_month_val / prev_month_val) - 1) * 100 if prev_month_val > 0 else 0
                    st.metric(
                        "最新月", 
                        f"{latest_month_val:.1f}人", 
                        delta=f"{change_rate:+.1f}% (前月比)"
                    )
            with col3:
                cv = (monthly_data['日平均在院患者数'].std() / avg_census) * 100 if avg_census > 0 else 0
                st.metric(
                    "変動係数", 
                    f"{cv:.1f}%", 
                    help="値が小さいほど安定している"
                )

            # トレンド詳細分析オプション
            if st.checkbox("運営指標のトレンド詳細分析を表示", key="show_operations_trend_analysis"):
                display_trend_analysis(monthly_data)

    except Exception as e:
        st.error(f"期間比較チャート作成エラー: {e}")

def create_sidebar_data_settings():
    """サイドバーのデータ設定セクション"""
    st.sidebar.header("💾 データ設定")
    
    # 現在のデータ状況表示
    with st.sidebar.expander("📊 現在のデータ状況", expanded=True):
        if st.session_state.get('data_processed', False):
            df = st.session_state.get('df')
            if df is not None:
                data_source = st.session_state.get('data_source', 'unknown')
                latest_date_str = st.session_state.get('latest_data_date_str', '不明')
                
                st.success("✅ データ読み込み済み")
                st.write(f"📅 最新日付: {latest_date_str}")
                st.write(f"📊 レコード数: {len(df):,}件")
                
                source_text = {
                    'auto_loaded': '自動読み込み',
                    'manual_loaded': '手動読み込み',
                    'sidebar_upload': 'サイドバー',
                    'unknown': '不明'
                }.get(data_source, '不明')
                st.write(f"🔄 読み込み元: {source_text}")
                
                # 保存されたデータの情報
                data_info = get_data_info()
                if data_info:
                    last_saved = data_info.get('last_saved', '不明')
                    if last_saved != '不明':
                        try:
                            saved_date = datetime.datetime.fromisoformat(last_saved.replace('Z', '+00:00'))
                            formatted_date = saved_date.strftime('%Y/%m/%d %H:%M')
                            st.write(f"💾 最終保存: {formatted_date}")
                        except:
                            st.write(f"💾 最終保存: {last_saved}")
            else:
                st.warning("⚠️ データ処理エラー")
        else:
            st.info("📂 データ未読み込み")
            
            # 保存されたデータがあるかチェック
            data_info = get_data_info()
            if data_info:
                st.write("💾 保存済みデータあり")
                if st.button("🔄 保存データを読み込む", key="load_saved_data"):
                    df, target_data, metadata = load_data_from_file()
                    if df is not None:
                        st.session_state['df'] = df
                        st.session_state['target_data'] = target_data
                        st.session_state['data_processed'] = True
                        st.session_state['data_source'] = 'manual_loaded'
                        st.session_state['data_metadata'] = metadata
                        
                        if '日付' in df.columns:
                            latest_date = df['日付'].max()
                            st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                        
                        st.experimental_rerun()
    
    # データ操作
    with st.sidebar.expander("🔧 データ操作", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 データ保存", key="save_current_data", use_container_width=True):
                if st.session_state.get('data_processed', False):
                    df = st.session_state.get('df')
                    target_data = st.session_state.get('target_data')
                    
                    if save_data_to_file(df, target_data):
                        st.success("保存完了!")
                        st.experimental_rerun()
                    else:
                        st.error("保存失敗")
                else:
                    st.warning("保存するデータがありません")
        
        with col2:
            if st.button("🗑️ データ削除", key="delete_saved_data", use_container_width=True):
                success, result = delete_saved_data()
                if success:
                    st.success(f"削除完了")
                    # セッション状態もクリア
                    keys_to_clear = ['df', 'target_data', 'data_processed', 'data_source', 'data_metadata']
                    for key in keys_to_clear:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.experimental_rerun()
                else:
                    st.error(f"削除失敗: {result}")
        
        # ファイルサイズ情報
        file_sizes = get_file_sizes()
        if any(size != "未保存" for size in file_sizes.values()):
            st.write("📁 **ファイルサイズ:**")
            for name, size in file_sizes.items():
                if size != "未保存":
                    st.write(f"  • {name}: {size}")
    
    # バックアップ管理
    with st.sidebar.expander("🗂️ バックアップ管理", expanded=False):
        backup_info = get_backup_info()
        if backup_info:
            st.write("📋 **利用可能なバックアップ:**")
            for backup in backup_info:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"📄 {backup['timestamp']}")
                    st.caption(f"サイズ: {backup['size']}")
                with col2:
                    if st.button("復元", key=f"restore_{backup['filename']}", use_container_width=True):
                        success, message = restore_from_backup(backup['filename'])
                        if success:
                            st.success(message)
                            st.experimental_rerun()
                        else:
                            st.error(message)
        else:
            st.info("バックアップファイルはありません")
    
    # 新しいデータのアップロード
    with st.sidebar.expander("📤 簡易データアップロード", expanded=False):
        st.write("**簡易的なファイル読み込み**")
        st.caption("詳細な処理は「データ処理」タブを使用")
        
        # 直接ファイルアップロード（簡易版）
        uploaded_file = st.file_uploader(
            "ファイルを選択",
            type=SUPPORTED_FILE_TYPES,
            key="sidebar_file_upload",
            help="Excel/CSVファイルをアップロード"
        )
        
        if uploaded_file is not None:
            if st.button("⚡ 簡易処理で読み込む", key="quick_process", use_container_width=True):
                try:
                    # 簡易的なファイル読み込み
                    if uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(uploaded_file, encoding='utf-8')
                    else:
                        df = pd.read_excel(uploaded_file)
                    
                    # 基本的な前処理
                    if '日付' in df.columns:
                        df['日付'] = pd.to_datetime(df['日付'])
                    
                    # セッション状態に保存
                    st.session_state['df'] = df
                    st.session_state['data_processed'] = True
                    st.session_state['data_source'] = 'sidebar_upload'
                    st.session_state['target_data'] = None
                    
                    if '日付' in df.columns:
                        latest_date = df['日付'].max()
                        st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                    
                    st.success("簡易読み込み完了!")
                    st.experimental_rerun()
                    
                except Exception as e:
                    st.error(f"読み込みエラー: {e}")

def create_sidebar():
    # データ設定セクション
    create_sidebar_data_settings()
    
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ 基本設定")
    
    # 期間設定セクション（統合版）
    create_sidebar_period_settings()

    # 基本設定セクション（従来と同じ）
    with st.sidebar.expander("🏥 基本設定", expanded=True):        if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
            df = st.session_state.df
            min_date = df['日付'].min().date()
            max_date = df['日付'].max().date()
            
            # デフォルト期間設定
            default_start = max(min_date, max_date - pd.Timedelta(days=DEFAULT_ANALYSIS_DAYS))
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
            
            # 期間妥当性チェック
            if start_date <= end_date:
                period_days = (end_date - start_date).days + 1
                st.info(f"選択期間: {period_days}日間")
                
                # 期間別推奨表示
                if period_days <= 7:
                    st.info("💡 短期間分析: 日別詳細分析に適しています")
                elif period_days <= 30:
                    st.info("💡 月次分析: 週別・日別分析に適しています")
                elif period_days <= 90:
                    st.info("💡 四半期分析: 月別・週別分析に適しています")
                else:
                    st.info("💡 長期分析: 月別・四半期分析に適しています")
            else:
                st.error("開始日は終了日より前の日付を選択してください。")
                
        else:
            st.info("データを読み込み後に期間設定が利用できます。")

    # 基本設定セクション
    with st.sidebar.expander("🏥 基本設定", expanded=True):
        # 設定値の自動読み込み
        if 'settings_loaded' not in st.session_state:
            saved_settings = load_settings_from_file()
            if saved_settings:
                for key, value in saved_settings.items():
                    st.session_state[key] = value
            st.session_state.settings_loaded = True
        
        # 型安全な設定値取得
        def get_safe_value(key, default, value_type=int):
            value = st.session_state.get(key, default)
            if isinstance(value, list):
                value = value[0] if value else default
            elif not isinstance(value, (int, float)):
                value = default
            return value_type(value)
        
        total_beds = st.number_input(
            "総病床数", 
            min_value=HOSPITAL_SETTINGS['min_beds'], 
            max_value=HOSPITAL_SETTINGS['max_beds'], 
            value=get_safe_value('total_beds', DEFAULT_TOTAL_BEDS),
            step=1,
            help="病院の総病床数を入力してください"
        )
        st.session_state.total_beds = total_beds
        
        # 修正：目標病床稼働率のデフォルト値問題を解決
        current_occupancy_percent = st.session_state.get('bed_occupancy_rate_percent', int(DEFAULT_OCCUPANCY_RATE * 100))
        bed_occupancy_rate = st.slider(
            "目標病床稼働率 (%)", 
            min_value=int(HOSPITAL_SETTINGS['min_occupancy_rate'] * 100), 
            max_value=int(HOSPITAL_SETTINGS['max_occupancy_rate'] * 100), 
            value=current_occupancy_percent,
            step=1,
            help="目標とする病床稼働率を設定してください"
        ) / 100
        st.session_state.bed_occupancy_rate = bed_occupancy_rate
        st.session_state.bed_occupancy_rate_percent = int(bed_occupancy_rate * 100)
        
        avg_length_of_stay = st.number_input(
            "平均在院日数", 
            min_value=HOSPITAL_SETTINGS['min_avg_stay'], 
            max_value=HOSPITAL_SETTINGS['max_avg_stay'], 
            value=get_safe_value('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY, float),
            step=0.1,
            help="平均在院日数を入力してください"
        )
        st.session_state.avg_length_of_stay = avg_length_of_stay
        
        avg_admission_fee = st.number_input(
            "平均入院料（円/日）", 
            min_value=1000, 
            max_value=100000, 
            value=get_safe_value('avg_admission_fee', DEFAULT_ADMISSION_FEE),
            step=1000,
            help="1日あたりの平均入院料を入力してください"
        )
        st.session_state.avg_admission_fee = avg_admission_fee
        
        # 設定の保存ボタン
        if st.button("💾 設定を保存", key="save_settings"):
            settings_to_save = {
                'total_beds': total_beds,
                'bed_occupancy_rate': bed_occupancy_rate,
                'bed_occupancy_rate_percent': int(bed_occupancy_rate * 100),
                'avg_length_of_stay': avg_length_of_stay,
                'avg_admission_fee': avg_admission_fee
            }
            if save_settings_to_file(settings_to_save):
                st.success("設定保存完了!")
            else:
                st.error("設定保存失敗")

    # 目標値設定セクション
    with st.sidebar.expander("🎯 目標値設定", expanded=True):
        # 目標値の計算
        monthly_target_patient_days = st.number_input(
            "月間延べ在院日数目標（人日）",
            min_value=100, 
            max_value=50000,
            value=get_safe_value('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS),
            step=100,
            help="月間の延べ在院日数目標を設定してください"
        )
        st.session_state.monthly_target_patient_days = monthly_target_patient_days
        
        monthly_target_admissions = st.number_input(
            "月間新入院患者数目標（人）",
            min_value=10, 
            max_value=5000,
            value=get_safe_value('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS),
            step=10,
            help="月間の新入院患者数目標を設定してください"
        )
        st.session_state.monthly_target_admissions = monthly_target_admissions
        
        # 推定収益計算
        monthly_revenue_estimate = monthly_target_patient_days * avg_admission_fee
        st.session_state.monthly_revenue_estimate = monthly_revenue_estimate
        
        # 目標値サマリー表示
        st.markdown("### 📈 目標値サマリー")
        st.markdown('<div class="sidebar-target-summary-metrics">', unsafe_allow_html=True)
        
        st.metric("延べ在院日数", f"{monthly_target_patient_days:,}人日")
        st.metric("新入院患者数", f"{monthly_target_admissions:,}人")
        st.metric("推定月間収益", f"{monthly_revenue_estimate:,.0f}{NUMBER_FORMAT['currency_symbol']}")
        st.metric("病床稼働率", f"{bed_occupancy_rate:.1%}")
        
        st.markdown('</div>', unsafe_allow_html=True)

    return (total_beds > 0 and bed_occupancy_rate > 0 and 
            avg_length_of_stay > 0 and avg_admission_fee > 0)

def create_management_dashboard_tab():
    """経営ダッシュボードタブ（期間設定統合版）"""
    if 'df' not in st.session_state or st.session_state['df'] is None:
        st.warning(MESSAGES['data_not_loaded'])
        return
    
    df = st.session_state['df']
    st.header("💰 経営ダッシュボード")
    
    # サイドバーの期間設定を表示
    start_date, end_date, period_type = get_analysis_period()
    
    if start_date and end_date:
        period_days = (end_date - start_date).days + 1
        st.info(f"📊 分析期間: {start_date.strftime('%Y/%m/%d')} - {end_date.strftime('%Y/%m/%d')} ({period_days}日間)")
        st.caption("※期間設定はサイドバーで変更できます")
        
        # 期間でフィルタリングされたデータを使用
        filtered_df = filter_data_by_analysis_period(df)
        
        if len(filtered_df) == 0:
            st.warning("選択期間にデータがありません。サイドバーで期間を調整してください。")
            return
        
        st.success(f"✅ 対象データ: {len(filtered_df):,}件")
        
        # 既存のメトリクス計算を使用（フィルタリングされたデータで）
        metrics = calculate_dashboard_metrics(filtered_df, start_date, end_date)
        if metrics:
            display_unified_metrics_layout_colorized(metrics, f"{start_date.strftime('%m/%d')}-{end_date.strftime('%m/%d')}")
    else:
        st.error("期間設定に問題があります。サイドバーで期間を設定してください。")
        
def calculate_dashboard_metrics(df, selected_period):
    """フィルタリング済みデータでのダッシュボードメトリクス計算"""
    try:
        total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
        kpis = calculate_kpis(df, start_date, end_date, total_beds=total_beds)
        
        if kpis and kpis.get("error"):
            st.error(f"KPI計算エラー: {kpis['error']}")
            return None
        
        # 基本設定値
        avg_admission_fee = st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE)
        monthly_target_patient_days = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS)
        
        # 期間内の値（既存のロジックを再利用）
        total_patient_days = kpis.get('total_patient_days', 0)
        avg_daily_census = kpis.get('avg_daily_census', 0)
        bed_occupancy_rate = kpis.get('bed_occupancy_rate', 0)
        avg_los = kpis.get('alos', 0) 
        avg_daily_admissions = kpis.get('avg_daily_admissions', 0)
        period_days = kpis.get('days_count', 1)
        
        # 推計収益
        estimated_revenue = total_patient_days * avg_admission_fee
        
        # 既存のメトリクス形式に合わせて返す
        return {
            'total_patient_days_30d': total_patient_days,  # 名前は既存に合わせる
            'bed_occupancy_rate': bed_occupancy_rate,
            'estimated_revenue_30d': estimated_revenue,
            'avg_daily_census_30d': avg_daily_census,
            'avg_daily_census': avg_daily_census,
            'avg_los': avg_los,
            'avg_daily_admissions': avg_daily_admissions,
            'period_days': period_days,
            'total_beds': total_beds,
            'target_revenue': monthly_target_patient_days * avg_admission_fee,
            'selected_period': f"カスタム期間"
        }
        
    except Exception as e:
        st.error(f"メトリクス計算エラー: {e}")
        return None

def get_period_dates(df, selected_period):
    """選択期間の開始日・終了日を取得"""
    latest_date = df['日付'].max()
    
    if selected_period == "直近30日":
        start_date = latest_date - pd.Timedelta(days=29)
        end_date = latest_date
    elif selected_period == "前月完了分":
        prev_month_start = (latest_date.replace(day=1) - pd.Timedelta(days=1)).replace(day=1)
        prev_month_end = latest_date.replace(day=1) - pd.Timedelta(days=1)
        start_date = prev_month_start
        end_date = prev_month_end
    elif selected_period == "今年度":
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

def format_number_with_config(value, unit="", format_type="default"):
    """設定に基づいた数値フォーマット"""
    if pd.isna(value) or value == 0:
        return f"0{unit}"
    
    if format_type == "currency":
        return f"{value:,.0f}{NUMBER_FORMAT['currency_symbol']}"
    elif format_type == "percentage":
        return f"{value:.1f}{NUMBER_FORMAT['percentage_symbol']}"
    else:
        return f"{value:,.0f}{unit}"

def display_unified_metrics_layout_colorized(metrics, selected_period):
    """統一メトリクスレイアウトの表示"""
    # 期間情報表示
    st.info(f"📊 平均値計算期間: {selected_period}")
    st.caption("※延べ在院日数、病床利用率は直近30日固定。")
    
    # 主要指標セクション
    st.markdown("### 📊 主要指標")
    st.markdown('<div class="management-dashboard-kpi-card">', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "日平均在院患者数",
            f"{metrics['avg_daily_census']:.1f}人",
            delta=f"参考：直近30日 {metrics['avg_daily_census_30d']:.1f}人",
            help=f"{selected_period}の日平均在院患者数"
        )
    
    with col2:
        target_occupancy = st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE) * 100
        occupancy_delta = metrics['bed_occupancy_rate'] - target_occupancy
        delta_color = "normal" if abs(occupancy_delta) <= 5 else "inverse"
        
        st.metric(
            "病床利用率",
            f"{metrics['bed_occupancy_rate']:.1f}%",
            delta=f"{occupancy_delta:+.1f}% (対目標{target_occupancy:.0f}%)",
            delta_color=delta_color,
            help="直近30日の平均病床利用率"
        )
    
    with col3:
        st.metric(
            "平均在院日数",
            f"{metrics['avg_los']:.1f}日",
            delta="標準: 12-16日",
            help=f"{selected_period}の平均在院日数"
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("---")
    
    # 収益指標セクション
    st.markdown("### 💰 収益指標")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "推計収益（直近30日）",
            format_number_with_config(metrics['estimated_revenue_30d'], format_type="currency"),
            delta=f"単価: {st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE):,}円/日",
            help="直近30日の推計収益"
        )
    
    with col2:
        monthly_target = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS)
        achievement_days = (metrics['total_patient_days_30d'] / monthly_target) * 100 if monthly_target > 0 else 0
        
        st.metric(
            "延べ在院日数（直近30日）",
            format_number_with_config(metrics['total_patient_days_30d'], "人日"),
            delta=f"対月間目標: {achievement_days:.1f}%",
            delta_color="normal" if achievement_days >= 95 else "inverse",
            help="直近30日間の延べ在院日数"
        )
    
    with col3:
        st.metric(
            "日平均新入院患者数",
            f"{metrics['avg_daily_admissions']:.1f}人",
            delta=f"期間: {metrics['period_days']}日間",
            help=f"{selected_period}の日平均新入院患者数"
        )
    
    # 詳細情報セクション
    with st.expander("📋 詳細データと設定値", expanded=False):
        detail_col1, detail_col2, detail_col3 = st.columns(3)
        
        with detail_col1:
            st.markdown("**🏥 基本設定**")
            st.write(f"• 総病床数: {metrics['total_beds']:,}床")
            st.write(f"• 目標病床稼働率: {st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE):.1%}")
            st.write(f"• 平均入院料: {st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE):,}円/日")
        
        with detail_col2:
            st.markdown("**📅 期間情報**")
            st.write(f"• 平均値計算: {selected_period}")
            st.write(f"• 固定値計算: 直近30日")
            st.write(f"• アプリバージョン: v{APP_VERSION}")
        
        with detail_col3:
            st.markdown("**🎯 目標値**")
            st.write(f"• 月間延べ在院日数: {format_number_with_config(monthly_target, '人日')}")
            st.write(f"• 月間目標収益: {format_number_with_config(metrics['target_revenue'], format_type='currency')}")
            st.write(f"• 月間新入院目標: {st.session_state.get('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS):,}人")

def main():
    """メイン関数（改修版）"""
    # セッション状態の初期化
    if 'data_processed' not in st.session_state:
        st.session_state['data_processed'] = False
    if 'df' not in st.session_state:
        st.session_state['df'] = None
    if 'forecast_model_results' not in st.session_state:
        st.session_state.forecast_model_results = {}

    # 自動データ読み込み
    auto_loaded = auto_load_data()
    if auto_loaded:
        st.success("💾 保存されたデータを自動読み込みしました")

    # ヘッダー
    st.markdown(f'<h1 class="main-header">{APP_ICON} {APP_TITLE}</h1>', unsafe_allow_html=True)
    
    # サイドバー設定
    settings_valid = create_sidebar()
    if not settings_valid:
        st.stop()
    
    # メインタブ設定（順序変更：データ処理を最後に）
    if FORECAST_AVAILABLE:
        tabs = st.tabs([
            "💰 経営ダッシュボード", 
            "🔮 予測分析",
            "📈 詳細分析",
            "📋 データテーブル",
            "📄 出力・予測",
            "📊 データ処理"  # 最後に移動
        ])
    else:
        tabs = st.tabs([
            "💰 経営ダッシュボード", 
            "📈 詳細分析",
            "📋 データテーブル",
            "📄 出力・予測",
            "📊 データ処理"  # 最後に移動
        ])

    # データ処理済みの場合のみ最初のタブ群を有効化
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        
        # 経営ダッシュボードタブ
        with tabs[0]:
            try:
                create_management_dashboard_tab()
            except Exception as e:
                st.error(f"経営ダッシュボードでエラーが発生しました: {str(e)}")
        
        # 予測分析タブ（利用可能な場合）
        if FORECAST_AVAILABLE:
            with tabs[1]:
                try:
                    deps_ok = check_forecast_dependencies()
                    if deps_ok:
                        display_forecast_analysis_tab()
                    else:
                        st.info(MESSAGES['forecast_libs_missing'])
                        st.markdown("""
                        ### 🔮 予測機能について
                        このタブでは以下の予測機能が利用できます：
                        - **単純移動平均**: 過去の平均値を未来に延長
                        - **Holt-Winters**: 季節性とトレンドを考慮した予測
                        - **ARIMA**: 時系列の自己回帰モデル
                        """)
                except Exception as e:
                    st.error(f"予測分析でエラーが発生しました: {str(e)}")
            
            # 詳細分析タブ
            with tabs[2]:
                try:
                    create_detailed_analysis_tab()
                except Exception as e:
                    st.error(f"詳細分析でエラーが発生しました: {str(e)}")
            
            # データテーブルタブ
            with tabs[3]:
                try:
                    create_data_tables_tab()
                except Exception as e:
                    st.error(f"データテーブルでエラーが発生しました: {str(e)}")
            
            # 出力・予測タブ
            with tabs[4]:
                try:
                    create_pdf_output_tab()
                except Exception as e:
                    st.error(f"出力機能でエラーが発生しました: {str(e)}")
        
        else:
            # 予測機能なしの場合
            with tabs[1]:
                try:
                    create_detailed_analysis_tab()
                except Exception as e:
                    st.error(f"詳細分析でエラーが発生しました: {str(e)}")
            
            with tabs[2]:
                try:
                    create_data_tables_tab()
                except Exception as e:
                    st.error(f"データテーブルでエラーが発生しました: {str(e)}")
            
            with tabs[3]:
                try:
                    create_pdf_output_tab()
                except Exception as e:
                    st.error(f"出力機能でエラーが発生しました: {str(e)}")
        
        # データ処理タブ（最後）
        with tabs[-1]:
            try:
                st.info("💡 新しいデータをアップロードする場合はこのタブを使用してください")
                create_data_processing_tab()
                
                # データ処理後の自動保存オプション
                if (st.session_state.get('data_processed', False) and 
                    st.session_state.get('df') is not None and
                    st.session_state.get('data_source') != 'auto_loaded'):
                    
                    st.markdown("---")
                    st.markdown("### 💾 データ保存")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("💾 処理したデータを保存", key="auto_save_processed", use_container_width=True):
                            df = st.session_state['df']
                            target_data = st.session_state.get('target_data')
                            
                            if save_data_to_file(df, target_data):
                                st.success("✅ データが保存されました。次回起動時に自動読み込みされます。")
                            else:
                                st.error("❌ データ保存に失敗しました。")
                    
                    with col2:
                        st.info("💡 保存すると次回起動時に自動読み込みされます")
                            
            except Exception as e:
                st.error(f"データ処理タブでエラーが発生しました: {str(e)}")
    
    else:
        # データ未処理の場合
        for i in range(len(tabs) - 1):  # 最後のデータ処理タブ以外
            with tabs[i]:
                st.info("📊 データを読み込み後に利用可能になります。")
                data_info = get_data_info()
                if data_info:
                    st.info("💾 保存されたデータがあります。サイドバーから読み込めます。")
                else:
                    st.info("📋 データ処理タブから新しいデータをアップロードしてください。")
        
        # データ処理タブは常に利用可能
        with tabs[-1]:
            try:
                st.markdown("### 📊 データ処理")
                st.info("💡 新しいデータをアップロードしてください")
                create_data_processing_tab()
                
                # データ処理後の処理
                if (st.session_state.get('data_processed', False) and 
                    st.session_state.get('df') is not None):
                    df = st.session_state['df']
                    target_data = st.session_state.get('target_data')
                    
                    # マッピングの初期化
                    initialize_all_mappings(df, target_data)
                    
                    # 最新データ日付の更新
                    if '日付' in df.columns:
                        latest_date = df['日付'].max()
                        st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                    
                    # 自動保存オプション
                    st.markdown("---")
                    st.markdown("### 💾 データ保存")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("💾 処理したデータを保存", key="save_new_processed", use_container_width=True):
                            if save_data_to_file(df, target_data):
                                st.success("✅ データが保存されました。次回起動時に自動読み込みされます。")
                            else:
                                st.error("❌ データ保存に失敗しました。")
                    
                    with col2:
                        st.info("💡 保存すると他の端末でも利用可能になります")
                            
            except Exception as e:
                st.error(f"データ処理タブでエラーが発生しました: {str(e)}")
    
    # フッター
    st.markdown("---")
    st.markdown(
        f'<div style="text-align: center; color: {DASHBOARD_COLORS["light_gray"]}; font-size: 0.8rem;">'
        f'{APP_ICON} {APP_TITLE} v{APP_VERSION} | {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        f'</div>',
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()