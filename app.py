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

def create_sidebar():
    """サイドバーの設定UI"""
    st.sidebar.header("⚙️ 設定")
    
    # 期間設定セクション
    with st.sidebar.expander("📅 期間設定", expanded=True):
        if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
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
            st.info("データを処理してから期間設定が利用できます。")

    # 基本設定セクション
    with st.sidebar.expander("🏥 基本設定", expanded=True):
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
        
        bed_occupancy_rate = st.slider(
            "目標病床稼働率 (%)", 
            min_value=int(HOSPITAL_SETTINGS['min_occupancy_rate'] * 100), 
            max_value=int(HOSPITAL_SETTINGS['max_occupancy_rate'] * 100), 
            value=int(get_safe_value('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE * 100)),
            step=1,
            help="目標とする病床稼働率を設定してください"
        ) / 100
        st.session_state.bed_occupancy_rate = bed_occupancy_rate
        
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
    """経営ダッシュボードタブ"""
    if 'df' not in st.session_state or st.session_state['df'] is None:
        st.warning(MESSAGES['data_not_loaded'])
        return
    
    df = st.session_state['df']
    st.header("💰 経営ダッシュボード")
    
    # 期間選択UI
    st.markdown("### 📊 表示期間設定")
    selected_period = st.radio(
        "期間選択（平均値計算用）",
        PERIOD_OPTIONS,
        index=0,
        horizontal=True,
        key="dashboard_period_selector",
        help="日平均在院患者数、平均在院日数、日平均新入院患者数の計算期間"
    )
    
    st.markdown("---")
    
    # メトリクス計算と表示
    metrics = calculate_dashboard_metrics(df, selected_period)
    if metrics:
        display_unified_metrics_layout_colorized(metrics, selected_period)

def calculate_dashboard_metrics(df, selected_period):
    """ダッシュボードメトリクスの計算"""
    try:
        latest_date = df['日付'].max()
        
        # 直近30日の計算
        fixed_start_date = latest_date - pd.Timedelta(days=29)
        fixed_end_date = latest_date
        
        total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
        fixed_kpis = calculate_kpis(df, fixed_start_date, fixed_end_date, total_beds=total_beds)
        
        if fixed_kpis and fixed_kpis.get("error"):
            st.error(f"KPI計算エラー: {fixed_kpis['error']}")
            return None
        
        # 平均値計算用期間
        period_start_date, period_end_date = get_period_dates(df, selected_period)
        period_kpis = calculate_kpis(df, period_start_date, period_end_date, total_beds=total_beds)
        
        if period_kpis and period_kpis.get("error"):
            st.error(f"期間KPI計算エラー: {period_kpis['error']}")
            return None
        
        # 基本設定値
        avg_admission_fee = st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE)
        monthly_target_patient_days = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS)
        target_revenue = monthly_target_patient_days * avg_admission_fee
        
        # 固定値（直近30日）
        total_patient_days_30d = fixed_kpis.get('total_patient_days', 0)
        avg_daily_census_30d = fixed_kpis.get('avg_daily_census', 0)
        bed_occupancy_rate = fixed_kpis.get('bed_occupancy_rate', 0)
        
        # 直近30日の推計収益
        estimated_revenue_30d = total_patient_days_30d * avg_admission_fee
        
        # 平均値（選択期間）
        avg_daily_census = period_kpis.get('avg_daily_census', 0)
        avg_los = period_kpis.get('alos', 0)
        avg_daily_admissions = period_kpis.get('avg_daily_admissions', 0)
        period_days = period_kpis.get('days_count', 1)
        
        return {
            'total_patient_days_30d': total_patient_days_30d,
            'bed_occupancy_rate': bed_occupancy_rate,
            'estimated_revenue_30d': estimated_revenue_30d,
            'avg_daily_census_30d': avg_daily_census_30d,
            'avg_daily_census': avg_daily_census,
            'avg_los': avg_los,
            'avg_daily_admissions': avg_daily_admissions,
            'period_days': period_days,
            'total_beds': total_beds,
            'target_revenue': target_revenue,
            'selected_period': selected_period
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
    """メイン関数"""
    # セッション状態の初期化
    if 'data_processed' not in st.session_state:
        st.session_state['data_processed'] = False
    if 'df' not in st.session_state:
        st.session_state['df'] = None
    if 'forecast_model_results' not in st.session_state:
        st.session_state.forecast_model_results = {}

    # ヘッダー
    st.markdown(f'<h1 class="main-header">{APP_ICON} {APP_TITLE}</h1>', unsafe_allow_html=True)
    
    # サイドバー設定
    settings_valid = create_sidebar()
    if not settings_valid:
        st.stop()
    
    # メインタブ設定
    if FORECAST_AVAILABLE:
        tabs = st.tabs([
            "📊 データ処理",
            "💰 経営ダッシュボード", 
            "🔮 予測分析",
            "📈 詳細分析",
            "📋 データテーブル",
            "📄 出力・予測"
        ])
    else:
        tabs = st.tabs([
            "📊 データ処理",
            "💰 経営ダッシュボード", 
            "📈 詳細分析",
            "📋 データテーブル",
            "📄 出力・予測"
        ])

    # データ処理タブ
    with tabs[0]:
        try:
            create_data_processing_tab()
            
            # データ処理後のマッピング初期化
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
                    
        except Exception as e:
            st.error(f"データ処理タブでエラーが発生しました: {str(e)}")
    
    # データ処理済みの場合のみ他のタブを有効化
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        
        # 経営ダッシュボードタブ
        with tabs[1]:
            try:
                create_management_dashboard_tab()
            except Exception as e:
                st.error(f"経営ダッシュボードでエラーが発生しました: {str(e)}")
        
        # 予測分析タブ（利用可能な場合）
        if FORECAST_AVAILABLE:
            with tabs[2]:
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
            with tabs[3]:
                try:
                    create_detailed_analysis_tab()
                except Exception as e:
                    st.error(f"詳細分析でエラーが発生しました: {str(e)}")
            
            # データテーブルタブ
            with tabs[4]:
                try:
                    create_data_tables_tab()
                except Exception as e:
                    st.error(f"データテーブルでエラーが発生しました: {str(e)}")
            
            # 出力・予測タブ
            with tabs[5]:
                try:
                    create_pdf_output_tab()
                except Exception as e:
                    st.error(f"出力機能でエラーが発生しました: {str(e)}")
        
        else:
            # 予測機能なしの場合
            with tabs[2]:
                try:
                    create_detailed_analysis_tab()
                except Exception as e:
                    st.error(f"詳細分析でエラーが発生しました: {str(e)}")
            
            with tabs[3]:
                try:
                    create_data_tables_tab()
                except Exception as e:
                    st.error(f"データテーブルでエラーが発生しました: {str(e)}")
            
            with tabs[4]:
                try:
                    create_pdf_output_tab()
                except Exception as e:
                    st.error(f"出力機能でエラーが発生しました: {str(e)}")
    
    else:
        # データ未処理の場合
        for i in range(1, len(tabs)):
            with tabs[i]:
                st.info(MESSAGES['insufficient_data'])
    
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