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

# 統一フィルター機能のインポート
from unified_filters import (
    create_unified_filter_sidebar,
    create_unified_filter_status_card,
    apply_unified_filters,
    get_unified_filter_summary,
    get_unified_filter_config,
    validate_unified_filters,
    initialize_filter_session_state  # この行を追加
)

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

def create_main_filter_interface(df):
    """メイン画面上部のフィルターインターフェース（修正版）"""
    if df is None or df.empty:
        st.warning("📊 データが読み込まれていません - データ処理タブでデータをアップロードしてください")
        return None, None
    
    # セッション状態の初期化
    initialize_filter_session_state(df)
    
    st.markdown("### 🔍 分析フィルター状態")
    
    try:
        # 統一フィルターの適用と状態表示
        filtered_df, filter_config = create_unified_filter_status_card(df)
        
        if filter_config is None:
            st.info("📋 フィルター未設定 - サイドバーで設定してください")
            return df, None
        
        # フィルター妥当性チェック
        is_valid, validation_message = validate_unified_filters(df)
        if not is_valid:
            st.error(f"❌ フィルター設定エラー: {validation_message}")
            # エラー時でも元データを返す
            return df, filter_config
        
        # フィルター適用結果の確認
        if filtered_df is None or filtered_df.empty:
            st.warning("⚠️ 選択されたフィルター条件にマッチするデータがありません")
            
            # 解決案の提示
            with st.expander("💡 解決方法", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**フィルター条件を調整：**")
                    st.write("• より広い期間を選択")
                    st.write("• 診療科・病棟の選択を追加")
                with col2:
                    st.write("**現在の設定：**")
                    filter_summary = get_unified_filter_summary()
                    st.write(f"• {filter_summary}")
            
            return df, filter_config
        
        # 成功時の表示
        st.success(f"✅ フィルター適用完了 - {len(filtered_df):,}件のデータで分析します")
        
        return filtered_df, filter_config
        
    except Exception as e:
        st.error(f"フィルター処理エラー: {e}")
        # エラー時は元データを返す
        return df, None

def calculate_preset_period_dates(df, preset_period):
    """プリセット期間から具体的な日付を計算 (pd.Timestampを返すように変更)"""
    latest_date = df['日付'].max()  # df['日付'] は既に Timestamp である想定

    if preset_period == "直近30日":
        start_date_ts = latest_date - pd.Timedelta(days=29)
        end_date_ts = latest_date
    elif preset_period == "前月完了分":
        # latest_date の前月の1日を取得
        prev_month_end = latest_date.replace(day=1) - pd.Timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        start_date_ts = prev_month_start
        end_date_ts = prev_month_end
    elif preset_period == "今年度":
        current_year = latest_date.year
        # 日本の会計年度 (4月始まり)
        if latest_date.month >= 4:
            fiscal_start_year = current_year
        else:
            fiscal_start_year = current_year - 1
        start_date_ts = pd.Timestamp(f"{fiscal_start_year}-04-01")
        end_date_ts = latest_date # 年度末までではなく、最新データ日まで
    else:  # デフォルト (直近30日など、必要に応じて適切なデフォルトを設定)
        start_date_ts = latest_date - pd.Timedelta(days=29)
        end_date_ts = latest_date
    
    # 時刻情報を正規化 (00:00:00 にする)
    # これにより、日付のみの比較でも意図しない挙動を防ぐ
    return start_date_ts.normalize(), end_date_ts.normalize()

def get_analysis_period():
    """現在の分析期間を取得 (Timestampで返す)"""
    if not st.session_state.get('data_processed', False):
        return None, None, "データなし"

    start_date_ts = st.session_state.get('analysis_start_date') # Timestamp が入っているはず
    end_date_ts = st.session_state.get('analysis_end_date')     # Timestamp が入っているはず
    period_type = st.session_state.get('analysis_period_type', 'preset') # これは文字列

    if start_date_ts and end_date_ts:
        # 既にTimestampなのでそのまま返す
        return start_date_ts, end_date_ts, period_type

    # デフォルト値 (dfがロードされている場合)
    df = st.session_state.get('df')
    if df is not None and not df.empty and '日付' in df.columns:
        latest_date = df['日付'].max()
        default_start_ts = (latest_date - pd.Timedelta(days=29)).normalize()
        # analysis_start_date/end_date をセッションに設定するならここで設定しても良い
        st.session_state.analysis_start_date = default_start_ts
        st.session_state.analysis_end_date = latest_date.normalize()
        return default_start_ts, latest_date.normalize(), "デフォルト"

    return None, None, "エラーまたはデータなし"

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
                        
                        # マッピング初期化
                        initialize_all_mappings(df, target_data)
                        
                        st.rerun()
    
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
                        st.rerun()
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
                    st.rerun()
                else:
                    st.error(f"削除失敗: {result}")
        
        # ファイルサイズ情報
        file_sizes = get_file_sizes()
        if any(size != "未保存" for size in file_sizes.values()):
            st.write("📁 **ファイルサイズ:**")
            for name, size in file_sizes.items():
                if size != "未保存":
                    st.write(f"  • {name}: {size}")

def create_sidebar():
    """サイドバーの設定UI（修正版）"""
    
    # データ設定セクション
    create_sidebar_data_settings()
    
    st.sidebar.markdown("---")
    
    # 統一フィルター設定（データが読み込まれている場合のみ）
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        df = st.session_state.get('df')
        
        try:
            # ★ 修正：initialize_unified_filters を削除
            # initialize_filter_session_state(df)  # 必要に応じて
            
            # サイドバーでフィルターUIを作成
            create_unified_filter_sidebar(df)
            
        except Exception as e:
            st.sidebar.error(f"フィルター設定エラー: {e}")
            # デバッグ情報を表示
            if st.sidebar.checkbox("🔧 エラー詳細を表示"):
                st.sidebar.exception(e)
    else:
        st.sidebar.info("📊 データ読み込み後にフィルター設定が利用できます")
    
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ 基本設定")
    
    # 基本設定セクション（既存コードはそのまま）
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

    # 目標値設定セクション（既存コードはそのまま使用）
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
    """経営ダッシュボードタブ（修正版）"""
    st.header("💰 経営ダッシュボード")
    
    if 'df' not in st.session_state or st.session_state['df'] is None:
        st.warning(MESSAGES['data_not_loaded'])
        return
    
    df = st.session_state['df']
    
    # ★ 重要：メインフィルターインターフェースを一度だけ呼び出し
    filtered_df, filter_config = create_main_filter_interface(df)
    
    if filter_config is None:
        st.info("💡 サイドバーでフィルター設定を行ってから分析を開始してください")
        return
    
    if filtered_df is None or filtered_df.empty:
        st.warning("⚠️ フィルター条件に該当するデータがありません")
        return
    
    # フィルター適用済みデータでの分析
    try:
        # フィルター設定から日付を取得
        start_date = filter_config.get('start_date')
        end_date = filter_config.get('end_date')
        
        if start_date and end_date:
            period_days = (end_date - start_date).days + 1
        else:
            period_days = len(filtered_df)
        
        # KPI計算
        total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
        kpis = calculate_kpis(filtered_df, start_date, end_date, total_beds=total_beds)
        
        if kpis and kpis.get("error"):
            st.error(f"KPI計算エラー: {kpis['error']}")
            return
        
        # 基本設定値
        avg_admission_fee = st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE)
        monthly_target_patient_days = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS)
        
        # メトリクス計算
        total_patient_days = kpis.get('total_patient_days', 0)
        avg_daily_census = kpis.get('avg_daily_census', 0)
        bed_occupancy_rate = kpis.get('bed_occupancy_rate', 0)
        avg_los = kpis.get('alos', 0)
        avg_daily_admissions = kpis.get('avg_daily_admissions', 0)
        
        # 推計収益
        estimated_revenue = total_patient_days * avg_admission_fee
        target_revenue = monthly_target_patient_days * avg_admission_fee
        
        # メトリクス辞書
        metrics = {
            'total_patient_days_30d': total_patient_days,
            'bed_occupancy_rate': bed_occupancy_rate,
            'estimated_revenue_30d': estimated_revenue,
            'avg_daily_census_30d': avg_daily_census,
            'avg_daily_census': avg_daily_census,
            'avg_los': avg_los,
            'avg_daily_admissions': avg_daily_admissions,
            'period_days': period_days,
            'total_beds': total_beds,
            'target_revenue': target_revenue,
            'selected_period': f"フィルター期間({period_days}日間)"
        }
        
        # メトリクス表示
        display_unified_metrics_layout_colorized(metrics, f"フィルター期間({period_days}日間)")
        
    except Exception as e:
        st.error(f"ダッシュボード表示エラー: {e}")
        # デバッグ情報
        if st.checkbox("🔧 エラー詳細を表示"):
            st.exception(e)
        
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
    """統一メトリクスレイアウトの表示（統一フィルター対応版）"""
    # 期間情報表示
    st.info(f"📊 分析期間: {selected_period}")
    
    # 主要指標セクション
    st.markdown("### 📊 主要指標")
    st.markdown('<div class="management-dashboard-kpi-card">', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "日平均在院患者数",
            f"{metrics['avg_daily_census']:.1f}人",
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
            help=f"{selected_period}の平均病床利用率"
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
            f"推計収益（{selected_period}）",
            f"{metrics['estimated_revenue_30d']:,.0f}{NUMBER_FORMAT['currency_symbol']}",
            delta=f"単価: {st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE):,}円/日",
            help=f"{selected_period}の推計収益"
        )
    
    with col2:
        monthly_target = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS)
        achievement_days = (metrics['total_patient_days_30d'] / monthly_target) * 100 if monthly_target > 0 else 0
        
        st.metric(
            f"延べ在院日数（{selected_period}）",
            f"{metrics['total_patient_days_30d']:,.0f}人日",
            delta=f"対月間目標: {achievement_days:.1f}%",
            delta_color="normal" if achievement_days >= 95 else "inverse",
            help=f"{selected_period}の延べ在院日数"
        )
    
    with col3:
        st.metric(
            "日平均新入院患者数",
            f"{metrics['avg_daily_admissions']:.1f}人",
            delta=f"期間: {metrics['period_days']}日間",
            help=f"{selected_period}の日平均新入院患者数"
        )

def main():
    """メイン関数（修正版）"""
    # セッション状態の初期化
    if 'data_processed' not in st.session_state:
        st.session_state['data_processed'] = False
    if 'df' not in st.session_state:
        st.session_state['df'] = None
    if 'forecast_model_results' not in st.session_state:
        st.session_state.forecast_model_results = {}
        
    # 緊急診断モードの追加
    if st.sidebar.checkbox("🚨 緊急診断モード"):
        emergency_diagnosis()
        return
        
    # 自動データ読み込み
    auto_loaded = auto_load_data()
    if auto_loaded:
        st.success("💾 保存されたデータを自動読み込みしました")
        # マッピング初期化
        df = st.session_state.get('df')
        target_data = st.session_state.get('target_data')
        if df is not None:
            initialize_all_mappings(df, target_data)

    # ヘッダー
    st.markdown(f'<h1 class="main-header">{APP_ICON} {APP_TITLE}</h1>', unsafe_allow_html=True)
    
    # ★ 重要：サイドバー設定（ここで一度だけ統一フィルターを作成）
    settings_valid = create_sidebar()
    if not settings_valid:
        st.stop()
    
    # メインタブ設定
    if FORECAST_AVAILABLE:
        tabs = st.tabs([
            "💰 経営ダッシュボード", 
            "🔮 予測分析",
            "📈 詳細分析",
            "📋 データテーブル",
            "📄 出力・予測",
            "📊 データ処理"
        ])
    else:
        tabs = st.tabs([
            "💰 経営ダッシュボード", 
            "📈 詳細分析",
            "📋 データテーブル",
            "📄 出力・予測",
            "📊 データ処理"
        ])

    # データ処理済みの場合のみタブ群を有効化
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        
        # 経営ダッシュボードタブ
        with tabs[0]:
            try:
                create_management_dashboard_tab()
            except Exception as e:
                st.error(f"経営ダッシュボードでエラーが発生しました: {str(e)}")
                if st.checkbox("🔧 エラー詳細を表示"):
                    st.exception(e)
        
        # 予測分析タブ（利用可能な場合）
        if FORECAST_AVAILABLE:
            with tabs[1]:
                try:
                    # フィルター適用
                    df = st.session_state.get('df')
                    filtered_df, filter_config = create_main_filter_interface(df)
                    
                    if filter_config is not None and filtered_df is not None and not filtered_df.empty:
                        # 一時的にフィルター済みデータをセッションに設定
                        original_df = st.session_state.get('df')
                        st.session_state['df'] = filtered_df
                        
                        display_forecast_analysis_tab()
                        
                        # 元のデータに戻す
                        st.session_state['df'] = original_df
                    else:
                        st.info("💡 フィルター設定を完了してから予測分析を開始してください")
                except Exception as e:
                    st.error(f"予測分析でエラーが発生しました: {str(e)}")
                    if st.checkbox("🔧 予測分析エラー詳細", key="forecast_error_detail"):
                        st.exception(e)
            
            # 詳細分析タブ
            with tabs[2]:
                try:
                    # ★ 重要：他のタブでは統一フィルターを再作成せず、状態表示のみ
                    df = st.session_state.get('df')
                    filtered_df, filter_config = create_main_filter_interface(df)
                    
                    if filter_config is not None and filtered_df is not None and not filtered_df.empty:
                        # フィルター済みデータで詳細分析を実行
                        original_df = st.session_state.get('df')
                        st.session_state['df'] = filtered_df
                        
                        create_detailed_analysis_tab()
                        
                        # 元のデータに戻す
                        st.session_state['df'] = original_df
                    else:
                        st.info("💡 フィルター設定を完了してから詳細分析を開始してください")
                        
                except Exception as e:
                    st.error(f"詳細分析でエラーが発生しました: {str(e)}")
                    if st.checkbox("🔧 詳細分析エラー詳細", key="detail_error_detail"):
                        st.exception(e)
            
            # データテーブルタブ
            with tabs[3]:
                try:
                    # フィルター適用
                    df = st.session_state.get('df')
                    filtered_df, filter_config = create_main_filter_interface(df)
                    
                    if filter_config is not None and filtered_df is not None and not filtered_df.empty:
                        original_df = st.session_state.get('df')
                        st.session_state['df'] = filtered_df
                        
                        create_data_tables_tab()
                        
                        st.session_state['df'] = original_df
                    else:
                        st.info("💡 フィルター設定を完了してからデータテーブルを表示してください")
                        
                except Exception as e:
                    st.error(f"データテーブルでエラーが発生しました: {str(e)}")
                    if st.checkbox("🔧 データテーブルエラー詳細", key="table_error_detail"):
                        st.exception(e)
            
            # 出力・予測タブ
            with tabs[4]:
                try:
                    # フィルター適用
                    df = st.session_state.get('df')
                    filtered_df, filter_config = create_main_filter_interface(df)
                    
                    if filter_config is not None and filtered_df is not None and not filtered_df.empty:
                        original_df = st.session_state.get('df')
                        st.session_state['df'] = filtered_df
                        
                        create_pdf_output_tab()
                        
                        st.session_state['df'] = original_df
                    else:
                        st.info("💡 フィルター設定を完了してから出力機能を使用してください")
                        
                except Exception as e:
                    st.error(f"出力機能でエラーが発生しました: {str(e)}")
                    if st.checkbox("🔧 出力エラー詳細", key="output_error_detail"):
                        st.exception(e)
        
        else:
            # 予測機能なしの場合
            with tabs[1]:
                try:
                    df = st.session_state.get('df')
                    filtered_df, filter_config = create_main_filter_interface(df)
                    
                    if filter_config is not None and filtered_df is not None and not filtered_df.empty:
                        original_df = st.session_state.get('df')
                        st.session_state['df'] = filtered_df
                        
                        create_detailed_analysis_tab()
                        
                        st.session_state['df'] = original_df
                    else:
                        st.info("💡 フィルター設定を完了してから詳細分析を開始してください")
                        
                except Exception as e:
                    st.error(f"詳細分析でエラーが発生しました: {str(e)}")
            
            with tabs[2]:
                try:
                    df = st.session_state.get('df')
                    filtered_df, filter_config = create_main_filter_interface(df)
                    
                    if filter_config is not None and filtered_df is not None and not filtered_df.empty:
                        original_df = st.session_state.get('df')
                        st.session_state['df'] = filtered_df
                        
                        create_data_tables_tab()
                        
                        st.session_state['df'] = original_df
                    else:
                        st.info("💡 フィルター設定を完了してからデータテーブルを表示してください")
                        
                except Exception as e:
                    st.error(f"データテーブルでエラーが発生しました: {str(e)}")
            
            with tabs[3]:
                try:
                    df = st.session_state.get('df')
                    filtered_df, filter_config = create_main_filter_interface(df)
                    
                    if filter_config is not None and filtered_df is not None and not filtered_df.empty:
                        original_df = st.session_state.get('df')
                        st.session_state['df'] = filtered_df
                        
                        create_pdf_output_tab()
                        
                        st.session_state['df'] = original_df
                    else:
                        st.info("💡 フィルター設定を完了してから出力機能を使用してください")
                        
                except Exception as e:
                    st.error(f"出力機能でエラーが発生しました: {str(e)}")
        
        # データ処理タブ（最後）
        with tabs[-1]:
            try:
                st.info("💡 新しいデータをアップロードする場合はこのタブを使用してください")
                create_data_processing_tab()
                        
            except Exception as e:
                st.error(f"データ処理タブでエラーが発生しました: {str(e)}")
    
    else:
        # データ未処理の場合
        for i in range(len(tabs) - 1):
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

def emergency_diagnosis():
    """緊急診断：フィルター問題の根本特定"""
    
    st.markdown("## 🚨 緊急診断モード")
    st.markdown("以下の診断結果を確認してください")
    
    # 診断1: セッション状態の確認
    st.markdown("### 1️⃣ セッション状態診断")
    all_keys = list(st.session_state.keys())
    filter_keys = [k for k in all_keys if 'filter' in k.lower()]
    
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**総セッション状態数**: {len(all_keys)}")
        st.write(f"**フィルター関連キー数**: {len(filter_keys)}")
        
        if filter_keys:
            st.write("**フィルターキー一覧**:")
            for key in filter_keys:
                value = st.session_state.get(key)
                st.write(f"  • `{key}`: {type(value).__name__} = {value}")
        else:
            st.error("❌ フィルター関連セッション状態が見つかりません")
    
    with col2:
        # 重要なキーの存在確認
        critical_keys = [
            'unified_filter_period_mode',
            'unified_filter_start_date', 
            'unified_filter_end_date',
            'unified_filter_departments',
            'unified_filter_wards',
            'unified_filter_applied'
        ]
        
        st.write("**重要キー存在確認**:")
        for key in critical_keys:
            exists = key in st.session_state
            status = "✅" if exists else "❌"
            st.write(f"  {status} `{key}`")
    
    # 診断2: データ状態の確認
    st.markdown("### 2️⃣ データ状態診断")
    df = st.session_state.get('df')
    
    if df is not None:
        st.success(f"✅ データ読み込み済み: {len(df):,}行")
        
        # データの基本情報
        col1, col2, col3 = st.columns(3)
        with col1:
            if '日付' in df.columns:
                min_date = df['日付'].min()
                max_date = df['日付'].max()
                st.write(f"**日付範囲**: {min_date.date()} ～ {max_date.date()}")
            else:
                st.error("❌ '日付'列が見つかりません")
        
        with col2:
            if '診療科名' in df.columns:
                dept_count = df['診療科名'].nunique()
                st.write(f"**診療科数**: {dept_count}")
            else:
                st.error("❌ '診療科名'列が見つかりません")
        
        with col3:
            if '病棟コード' in df.columns:
                ward_count = df['病棟コード'].nunique()
                st.write(f"**病棟数**: {ward_count}")
            else:
                st.error("❌ '病棟コード'列が見つかりません")
    else:
        st.error("❌ データが読み込まれていません")
    
    # 診断3: フィルター関数の動作確認
    st.markdown("### 3️⃣ フィルター関数診断")
    
    try:
        from unified_filters import (
            create_unified_filter_sidebar,
            create_unified_filter_status_card,
            apply_unified_filters,
            get_unified_filter_summary,
            validate_unified_filters
        )
        st.success("✅ unified_filters モジュールの基本インポート成功")
        
        # 各関数の存在確認
        functions_to_check = [
            create_unified_filter_sidebar,
            create_unified_filter_status_card, 
            apply_unified_filters,
            get_unified_filter_summary,
            validate_unified_filters
        ]
        
        for func in functions_to_check:
            st.write(f"  ✅ `{func.__name__}` 利用可能")
            
    except ImportError as e:
        st.error(f"❌ unified_filters インポートエラー: {e}")
        return
    except Exception as e:
        st.error(f"❌ フィルター関数チェックエラー: {e}")
        return
    
    # 診断4: 実際のフィルター適用テスト
    st.markdown("### 4️⃣ フィルター適用テスト")
    
    if df is not None:
        try:
            # 強制的にフィルター設定を作成
            if 'unified_filter_period_mode' not in st.session_state:
                st.session_state['unified_filter_period_mode'] = '最近90日'
            
            if 'unified_filter_start_date' not in st.session_state and '日付' in df.columns:
                max_date = df['日付'].max()
                start_date = max_date - pd.Timedelta(days=90)
                st.session_state['unified_filter_start_date'] = start_date.date()
                st.session_state['unified_filter_end_date'] = max_date.date()
            
            if 'unified_filter_departments' not in st.session_state and '診療科名' in df.columns:
                st.session_state['unified_filter_departments'] = sorted(df['診療科名'].unique())
            
            if 'unified_filter_wards' not in st.session_state and '病棟コード' in df.columns:
                st.session_state['unified_filter_wards'] = sorted(df['病棟コード'].unique())
            
            # フィルター適用テスト
            filtered_df = apply_unified_filters(df)
            
            if filtered_df is not None:
                filter_ratio = len(filtered_df) / len(df) * 100 if len(df) > 0 else 0
                
                if len(filtered_df) == len(df):
                    st.warning(f"⚠️ フィルター適用結果: {len(filtered_df):,}行 (元データと同じ - フィルターが効いていない)")
                else:
                    st.success(f"✅ フィルター適用結果: {len(filtered_df):,}行 ({filter_ratio:.1f}% 残存)")
                    
                # フィルター設定の表示
                st.write("**現在のフィルター設定**:")
                st.write(f"  • 期間モード: {st.session_state.get('unified_filter_period_mode', '未設定')}")
                st.write(f"  • 開始日: {st.session_state.get('unified_filter_start_date', '未設定')}")
                st.write(f"  • 終了日: {st.session_state.get('unified_filter_end_date', '未設定')}")
                
                selected_depts = st.session_state.get('unified_filter_departments', [])
                total_depts = df['診療科名'].nunique() if '診療科名' in df.columns else 0
                st.write(f"  • 診療科: {len(selected_depts)}/{total_depts}科選択")
                
                selected_wards = st.session_state.get('unified_filter_wards', [])
                total_wards = df['病棟コード'].nunique() if '病棟コード' in df.columns else 0
                st.write(f"  • 病棟: {len(selected_wards)}/{total_wards}病棟選択")
                
            else:
                st.error("❌ フィルター適用が None を返しました")
                
        except Exception as e:
            st.error(f"❌ フィルター適用テストエラー: {e}")
            st.exception(e)
    
    # 診断5: 緊急修復オプション
    st.markdown("### 5️⃣ 緊急修復オプション")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🗑️ 全セッション状態クリア"):
            keys_to_remove = list(st.session_state.keys())
            for key in keys_to_remove:
                del st.session_state[key]
            st.success("セッション状態をクリアしました")
            st.rerun()
    
    with col2:
        if st.button("🔄 フィルター強制初期化"):
            if df is not None:
                # 強制的にフィルター設定を初期化
                if '日付' in df.columns:
                    max_date = df['日付'].max()
                    start_date = max_date - pd.Timedelta(days=90)
                    st.session_state['unified_filter_period_mode'] = '最近90日'
                    st.session_state['unified_filter_start_date'] = start_date.date()
                    st.session_state['unified_filter_end_date'] = max_date.date()
                
                if '診療科名' in df.columns:
                    st.session_state['unified_filter_departments'] = sorted(df['診療科名'].unique())
                
                if '病棟コード' in df.columns:
                    st.session_state['unified_filter_wards'] = sorted(df['病棟コード'].unique())
                
                st.session_state['unified_filter_applied'] = True
                st.success("フィルター設定を強制初期化しました")
                st.rerun()
    
    with col3:
        if st.button("🔬 詳細デバッグ"):
            st.session_state['debug_mode'] = True
            st.success("詳細デバッグモードを有効にしました")
    
    # 診断結果サマリー
    st.markdown("### 📋 診断結果サマリー")
    
    # 問題スコア計算
    issues = []
    
    if not filter_keys:
        issues.append("フィルター関連セッション状態が存在しない")
    
    if df is None:
        issues.append("データが読み込まれていない")
    
    try:
        filtered_df = apply_unified_filters(df) if df is not None else None
        if filtered_df is not None and len(filtered_df) == len(df):
            issues.append("フィルターが実際にデータを絞り込んでいない")
    except:
        issues.append("フィルター適用関数でエラーが発生")
    
    if issues:
        st.error("🚨 **発見された問題**:")
        for issue in issues:
            st.write(f"  • {issue}")
        
        st.markdown("**推奨解決策**:")
        st.write("1. 「フィルター強制初期化」ボタンを押す")
        st.write("2. ブラウザを完全リフレッシュ (Ctrl+F5)")
        st.write("3. 新しいブラウザタブで開き直す")
    else:
        st.success("✅ **基本的な設定は正常です**")
        st.write("問題は設定レベルではなく、実装レベルにある可能性があります")
    
def emergency_diagnosis():
    """緊急診断：フィルター問題の根本特定"""
    
    st.markdown("## 🚨 緊急診断モード")
    st.markdown("以下の診断結果を確認してください")
    
    # 診断1: セッション状態の確認
    st.markdown("### 1️⃣ セッション状態診断")
    all_keys = list(st.session_state.keys())
    filter_keys = [k for k in all_keys if 'filter' in k.lower()]
    
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**総セッション状態数**: {len(all_keys)}")
        st.write(f"**フィルター関連キー数**: {len(filter_keys)}")
        
        if filter_keys:
            st.write("**フィルターキー一覧**:")
            for key in filter_keys:
                value = st.session_state.get(key)
                st.write(f"  • `{key}`: {type(value).__name__} = {value}")
        else:
            st.error("❌ フィルター関連セッション状態が見つかりません")
    
    with col2:
        # 重要なキーの存在確認
        critical_keys = [
            'unified_filter_period_mode',
            'unified_filter_start_date', 
            'unified_filter_end_date',
            'unified_filter_departments',
            'unified_filter_wards',
            'unified_filter_applied'
        ]
        
        st.write("**重要キー存在確認**:")
        for key in critical_keys:
            exists = key in st.session_state
            status = "✅" if exists else "❌"
            st.write(f"  {status} `{key}`")
    
    # 診断2: データ状態の確認
    st.markdown("### 2️⃣ データ状態診断")
    df = st.session_state.get('df')
    
    if df is not None:
        st.success(f"✅ データ読み込み済み: {len(df):,}行")
        
        # データの基本情報
        col1, col2, col3 = st.columns(3)
        with col1:
            if '日付' in df.columns:
                min_date = df['日付'].min()
                max_date = df['日付'].max()
                st.write(f"**日付範囲**: {min_date.date()} ～ {max_date.date()}")
            else:
                st.error("❌ '日付'列が見つかりません")
        
        with col2:
            if '診療科名' in df.columns:
                dept_count = df['診療科名'].nunique()
                st.write(f"**診療科数**: {dept_count}")
            else:
                st.error("❌ '診療科名'列が見つかりません")
        
        with col3:
            if '病棟コード' in df.columns:
                ward_count = df['病棟コード'].nunique()
                st.write(f"**病棟数**: {ward_count}")
            else:
                st.error("❌ '病棟コード'列が見つかりません")
    else:
        st.error("❌ データが読み込まれていません")
    
    # 診断3: フィルター関数の動作確認
    st.markdown("### 3️⃣ フィルター関数診断")
    
    try:
        from unified_filters import (
            create_unified_filter_sidebar,
            create_unified_filter_status_card,
            apply_unified_filters,
            get_unified_filter_summary,
            validate_unified_filters
        )
        st.success("✅ unified_filters モジュールの基本インポート成功")
        
        # 各関数の存在確認
        functions_to_check = [
            create_unified_filter_sidebar,
            create_unified_filter_status_card, 
            apply_unified_filters,
            get_unified_filter_summary,
            validate_unified_filters
        ]
        
        for func in functions_to_check:
            st.write(f"  ✅ `{func.__name__}` 利用可能")
            
    except ImportError as e:
        st.error(f"❌ unified_filters インポートエラー: {e}")
        return
    except Exception as e:
        st.error(f"❌ フィルター関数チェックエラー: {e}")
        return
    
    # 診断4: 実際のフィルター適用テスト
    st.markdown("### 4️⃣ フィルター適用テスト")
    
    if df is not None:
        try:
            # 強制的にフィルター設定を作成
            if 'unified_filter_period_mode' not in st.session_state:
                st.session_state['unified_filter_period_mode'] = '最近90日'
            
            if 'unified_filter_start_date' not in st.session_state and '日付' in df.columns:
                max_date = df['日付'].max()
                start_date = max_date - pd.Timedelta(days=90)
                st.session_state['unified_filter_start_date'] = start_date.date()
                st.session_state['unified_filter_end_date'] = max_date.date()
            
            if 'unified_filter_departments' not in st.session_state and '診療科名' in df.columns:
                st.session_state['unified_filter_departments'] = sorted(df['診療科名'].unique())
            
            if 'unified_filter_wards' not in st.session_state and '病棟コード' in df.columns:
                st.session_state['unified_filter_wards'] = sorted(df['病棟コード'].unique())
            
            # フィルター適用テスト
            filtered_df = apply_unified_filters(df)
            
            if filtered_df is not None:
                filter_ratio = len(filtered_df) / len(df) * 100 if len(df) > 0 else 0
                
                if len(filtered_df) == len(df):
                    st.warning(f"⚠️ フィルター適用結果: {len(filtered_df):,}行 (元データと同じ - フィルターが効いていない)")
                else:
                    st.success(f"✅ フィルター適用結果: {len(filtered_df):,}行 ({filter_ratio:.1f}% 残存)")
                    
                # フィルター設定の表示
                st.write("**現在のフィルター設定**:")
                st.write(f"  • 期間モード: {st.session_state.get('unified_filter_period_mode', '未設定')}")
                st.write(f"  • 開始日: {st.session_state.get('unified_filter_start_date', '未設定')}")
                st.write(f"  • 終了日: {st.session_state.get('unified_filter_end_date', '未設定')}")
                
                selected_depts = st.session_state.get('unified_filter_departments', [])
                total_depts = df['診療科名'].nunique() if '診療科名' in df.columns else 0
                st.write(f"  • 診療科: {len(selected_depts)}/{total_depts}科選択")
                
                selected_wards = st.session_state.get('unified_filter_wards', [])
                total_wards = df['病棟コード'].nunique() if '病棟コード' in df.columns else 0
                st.write(f"  • 病棟: {len(selected_wards)}/{total_wards}病棟選択")
                
            else:
                st.error("❌ フィルター適用が None を返しました")
                
        except Exception as e:
            st.error(f"❌ フィルター適用テストエラー: {e}")
            st.exception(e)
    
    # 診断5: 緊急修復オプション
    st.markdown("### 5️⃣ 緊急修復オプション")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🗑️ 全セッション状態クリア"):
            keys_to_remove = list(st.session_state.keys())
            for key in keys_to_remove:
                del st.session_state[key]
            st.success("セッション状態をクリアしました")
            st.rerun()
    
    with col2:
        if st.button("🔄 フィルター強制初期化"):
            if df is not None:
                # 強制的にフィルター設定を初期化
                if '日付' in df.columns:
                    max_date = df['日付'].max()
                    start_date = max_date - pd.Timedelta(days=90)
                    st.session_state['unified_filter_period_mode'] = '最近90日'
                    st.session_state['unified_filter_start_date'] = start_date.date()
                    st.session_state['unified_filter_end_date'] = max_date.date()
                
                if '診療科名' in df.columns:
                    st.session_state['unified_filter_departments'] = sorted(df['診療科名'].unique())
                
                if '病棟コード' in df.columns:
                    st.session_state['unified_filter_wards'] = sorted(df['病棟コード'].unique())
                
                st.session_state['unified_filter_applied'] = True
                st.success("フィルター設定を強制初期化しました")
                st.rerun()
    
    with col3:
        if st.button("🔬 詳細デバッグ"):
            st.session_state['debug_mode'] = True
            st.success("詳細デバッグモードを有効にしました")
    
    # 診断結果サマリー
    st.markdown("### 📋 診断結果サマリー")
    
    # 問題スコア計算
    issues = []
    
    if not filter_keys:
        issues.append("フィルター関連セッション状態が存在しない")
    
    if df is None:
        issues.append("データが読み込まれていない")
    
    try:
        filtered_df = apply_unified_filters(df) if df is not None else None
        if filtered_df is not None and len(filtered_df) == len(df):
            issues.append("フィルターが実際にデータを絞り込んでいない")
    except:
        issues.append("フィルター適用関数でエラーが発生")
    
    if issues:
        st.error("🚨 **発見された問題**:")
        for issue in issues:
            st.write(f"  • {issue}")
        
        st.markdown("**推奨解決策**:")
        st.write("1. 「フィルター強制初期化」ボタンを押す")
        st.write("2. ブラウザを完全リフレッシュ (Ctrl+F5)")
        st.write("3. 新しいブラウザタブで開き直す")
    else:
        st.success("✅ **基本的な設定は正常です**")
        st.write("問題は設定レベルではなく、実装レベルにある可能性があります")

if __name__ == "__main__":
    main()