# 削除した関数はapp_backupに保存
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import io
import zipfile
import tempfile
import os
try:
    import jpholiday
    JPHOLIDAY_AVAILABLE = True
except ImportError:
    JPHOLIDAY_AVAILABLE = False
from scipy import stats
from config import (
    APP_TITLE,                    # "入退院分析ダッシュボード"
    APP_ICON,                     # "🏥"
    APP_VERSION,                  # "2.0"
    DEFAULT_TOTAL_BEDS,           # 612
    DEFAULT_OCCUPANCY_RATE,       # 0.85
    DEFAULT_AVG_LENGTH_OF_STAY,   # 12.0
    DEFAULT_ADMISSION_FEE,        # 55000
    DEFAULT_TARGET_PATIENT_DAYS,  # 17000
    DEFAULT_TARGET_ADMISSIONS,    # 1480
    PERIOD_OPTIONS,               # ["直近30日", "前月完了分", "今年度"]
    CHART_HEIGHT,                 # 400
    DASHBOARD_COLORS,             # カラーパレット辞書
    NUMBER_FORMAT,                # 数値フォーマット設定
    MESSAGES,                     # メッセージ設定
    ANALYSIS_SETTINGS,            # 分析設定
    HOSPITAL_SETTINGS,            # 病院設備設定
    FONT_SCALE                    # 1.0
)

# ページ設定
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)
from style import inject_global_css
from utils import safe_date_filter, initialize_all_mappings

inject_global_css(1.0)  # style.pyの関数を使用

# カスタムCSS
# 削除したCSSはapp_backupに保存

from pdf_output_tab import create_pdf_output_tab

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
            total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
            bed_occupancy_rate_target = st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE)
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

# def validate_kpi_calculations():
# def get_period_data_for_averages(df, selected_period):

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
        
# def calculate_period_metrics(df_filtered, selected_period, period_dates):
# def display_kpi_cards(metrics, selected_period):
# def display_operational_insights(metrics, selected_period):
# 削除した関数はapp_backupに保存
# def display_prediction_confidence(df_actual, period_dates):
# def display_revenue_summary(df_filtered, period_dates, selected_period):
# def display_operations_summary(df_filtered, period_dates, selected_period):
# def display_integrated_charts(df_graph, graph_dates, graph_period):
# def display_fallback_revenue(df_filtered, period_dates, selected_period):
# def normalize_column_names(df):
# def predict_monthly_completion(df_actual, period_dates):

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
    st.markdown(f'<h1 class="main-header">{APP_ICON} {APP_TITLE}</h1>', unsafe_allow_html=True)
    
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
            "📄 出力"
        ])
    else:
        # 予測機能が利用できない場合は従来の5タブ
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 データ処理",
            "💰 経営ダッシュボード", 
            "📈 詳細分析",
            "📋 データテーブル",
            "📄 出力"
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
            
            # 出力タブ（インデックス調整）
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
            f'{APP_ICON} {APP_TITLE} v2.0 | {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
            f'⏰ {datetime.datetime.now().strftime("%H:%M:%S")}'
            '</div>',
            unsafe_allow_html=True
        )

if __name__ == "__main__":
    main()
