# forecast_analysis_tab.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time

# 既存のモジュールから必要な関数をインポート
try:
    from forecast_models import (
        simple_moving_average_forecast,
        holt_winters_forecast,
        arima_forecast,
        prepare_daily_total_patients,
        generate_annual_forecast_summary,
    )
except ImportError as e:
    st.error(f"予測分析に必要なモジュール forecast_models のインポートに失敗しました: {e}")
    prepare_daily_total_patients = None
    simple_moving_average_forecast = None
    holt_winters_forecast = None
    arima_forecast = None
    generate_annual_forecast_summary = None

# グラフ作成関数をインポート（dashboard_charts.py から）
try:
    from dashboard_charts import create_monthly_trend_chart
    # 予測比較チャート用の関数を作成
    def create_forecast_comparison_chart(actual_series, forecast_dict, title="予測比較", display_days_past=180, display_days_future=365):
        """予測比較チャートを作成"""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        
        if actual_series.empty:
            return None
            
        fig = go.Figure()
        
        # 実績データの表示範囲を制限
        if display_days_past > 0:
            start_date = actual_series.index.max() - pd.Timedelta(days=display_days_past)
            actual_display = actual_series[actual_series.index >= start_date]
        else:
            actual_display = actual_series
            
        # 実績データをプロット
        fig.add_trace(
            go.Scatter(
                x=actual_display.index,
                y=actual_display.values,
                mode='lines',
                name='実績',
                line=dict(color='#2196f3', width=2)
            )
        )
        
        # 各予測モデルをプロット
        colors = ['#ff9800', '#4caf50', '#f44336', '#9c27b0']
        for i, (model_name, forecast_series) in enumerate(forecast_dict.items()):
            if forecast_series is not None and not forecast_series.empty:
                # 予測データの表示範囲を制限
                if display_days_future > 0:
                    end_date = forecast_series.index.min() + pd.Timedelta(days=display_days_future)
                    forecast_display = forecast_series[forecast_series.index <= end_date]
                else:
                    forecast_display = forecast_series
                    
                fig.add_trace(
                    go.Scatter(
                        x=forecast_display.index,
                        y=forecast_display.values,
                        mode='lines',
                        name=f'{model_name} 予測',
                        line=dict(color=colors[i % len(colors)], width=2, dash='dash')
                    )
                )
        
        # レイアウト設定
        fig.update_layout(
            title=title,
            xaxis_title="日付",
            yaxis_title="患者数 (人)",
            hovermode='x unified',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=500
        )
        
        return fig
        
except ImportError as e:
    st.error(f"グラフ作成に必要なモジュールのインポートに失敗しました: {e}")
    create_forecast_comparison_chart = None

def display_forecast_analysis_tab():
    """
    予測分析タブのUIとロジックを表示する関数。
    """
    st.header("📉 予測分析")

    if 'data_processed' not in st.session_state or not st.session_state.data_processed:
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return

    df = st.session_state.get('df')
    latest_data_date_str = st.session_state.get('latest_data_date_str')

    if df is None or df.empty:
        st.error("分析対象のデータフレームが読み込まれていません。")
        return
    if latest_data_date_str is None:
        st.error("データの最新日付が不明です。")
        return
        
    try:
        latest_data_date = pd.to_datetime(latest_data_date_str, format="%Y年%m月%d日")
    except ValueError:
        st.error(f"最新データ日付の形式が無効です: {latest_data_date_str}")
        latest_data_date = pd.Timestamp.now().normalize()

    st.subheader("予測設定")
    col_pred_set1, col_pred_set2 = st.columns(2)

    with col_pred_set1:
        # データの最新日に基づいてデフォルトの予測対象年度を決定
        default_pred_year = latest_data_date.year
        if latest_data_date.month < 4:  # 1-3月なら前年度の会計年度が進行中
            default_pred_year -= 1
        
        available_pred_years = list(range(default_pred_year - 1, default_pred_year + 3))
        try:
            default_pred_year_index = available_pred_years.index(default_pred_year)
        except ValueError:
            default_pred_year_index = 0

        predict_fiscal_year = st.selectbox(
            "予測対象年度",
            options=available_pred_years,
            index=default_pred_year_index,
            format_func=lambda year: f"{year}年度"
        )

    with col_pred_set2:
        model_options = []
        if simple_moving_average_forecast: model_options.append("単純移動平均")
        if holt_winters_forecast: model_options.append("Holt-Winters")
        if arima_forecast: model_options.append("ARIMA")
        
        if not model_options:
            st.error("利用可能な予測モデルがありません。forecast_models.py を確認してください。")
            return
        
        selected_models = st.multiselect(
            "比較する予測モデルを選択",
            options=model_options,
            default=model_options[:2]  # デフォルトで最初の2つを選択
        )

    with st.expander("モデルパラメータ詳細設定（上級者向け）", expanded=False):
        sma_window = st.slider("単純移動平均: ウィンドウサイズ（日数）", 3, 30, 7, key="pred_sma_window")
        hw_seasonal_periods = st.slider("Holt-Winters: 季節周期（日数）", 7, 365, 7, key="pred_hw_seasonal_periods", help="週周期なら7、年周期なら365など。")
        arima_m = st.slider("ARIMA: 季節周期 (m)", 7, 52, 7, key="pred_arima_m", help="週周期の季節性(m=7)を考慮します。")

    if st.button("予測を実行", key="run_prediction_button_main", use_container_width=True):
        if not selected_models:
            st.warning("比較するモデルを1つ以上選択してください。")
        elif not all([prepare_daily_total_patients, generate_annual_forecast_summary]):
            st.error("予測に必要な関数がインポートされていません。")
        else:
            with st.spinner(f"{predict_fiscal_year}年度の患者数予測を実行中..."):
                forecast_start_time = time.time()
                
                # 予測用の日次全患者数データを準備
                daily_total_patients = prepare_daily_total_patients(df)

                if daily_total_patients.empty:
                    st.error("予測用の日次患者数データを作成できませんでした。元データを確認してください。")
                else:
                    forecast_model_results_dict = {} 
                    forecast_annual_summary_list = []

                    forecast_horizon_end_date = pd.Timestamp(f"{predict_fiscal_year + 1}-03-31")
                    last_data_date_for_pred = daily_total_patients.index.max()
                    
                    horizon_days = 0
                    if last_data_date_for_pred < forecast_horizon_end_date:
                        horizon_days = (forecast_horizon_end_date - last_data_date_for_pred).days
                    
                    if horizon_days <= 0:
                        st.warning(f"{predict_fiscal_year}年度末までの予測期間がありません。実績データが既に年度末を超えているか、対象年度を確認してください。")
                    else:
                        # 進捗表示
                        progress_bar = st.progress(0)
                        progress_text = st.empty()
                        
                        for idx, model_name in enumerate(selected_models):
                            progress_text.text(f"予測実行中: {model_name}")
                            progress_bar.progress((idx) / len(selected_models))
                            
                            pred_series = None
                            try:
                                if model_name == "単純移動平均" and simple_moving_average_forecast:
                                    pred_series = simple_moving_average_forecast(daily_total_patients, window=sma_window, forecast_horizon=horizon_days)
                                elif model_name == "Holt-Winters" and holt_winters_forecast:
                                    pred_series = holt_winters_forecast(daily_total_patients, seasonal_periods=hw_seasonal_periods, forecast_horizon=horizon_days)
                                elif model_name == "ARIMA" and arima_forecast:
                                    pred_series = arima_forecast(daily_total_patients, forecast_horizon=horizon_days, m=arima_m)
                                
                                if pred_series is not None and not pred_series.empty:
                                    forecast_model_results_dict[model_name] = pred_series
                                    if generate_annual_forecast_summary:
                                        annual_sum = generate_annual_forecast_summary(
                                            daily_total_patients,
                                            pred_series,
                                            last_data_date_for_pred,
                                            predict_fiscal_year
                                        )
                                        forecast_annual_summary_list.append({
                                            "モデル名": model_name,
                                            "実績総患者数": annual_sum.get("実績総患者数", 0),
                                            "予測総患者数": annual_sum.get("予測総患者数", 0),
                                            f"{predict_fiscal_year}年度 総患者数（予測込）": annual_sum.get("年度総患者数（予測込）", 0)
                                        })
                                else:
                                    st.warning(f"{model_name}モデルの予測結果が空です。")
                                    
                            except Exception as e_model:
                                st.error(f"{model_name}モデルの予測中にエラーが発生しました: {e_model}")
                                continue
                        
                        # 進捗バーを完了に更新
                        progress_bar.progress(1.0)
                        progress_text.text("予測完了")
                        
                        # セッションステートに結果を保存
                        st.session_state.forecast_model_results = forecast_model_results_dict
                        if forecast_annual_summary_list:
                            st.session_state.forecast_annual_summary_df = pd.DataFrame(forecast_annual_summary_list).set_index("モデル名")
                        else:
                            st.session_state.forecast_annual_summary_df = pd.DataFrame()

                        forecast_end_time = time.time()
                        st.success(f"{predict_fiscal_year}年度の患者数予測が完了しました。処理時間: {forecast_end_time - forecast_start_time:.1f}秒")
                        
                        # 進捗表示をクリア
                        progress_bar.empty()
                        progress_text.empty()

    # --- 予測結果表示 ---
    if 'forecast_model_results' in st.session_state and st.session_state.forecast_model_results:
        st.subheader(f"{predict_fiscal_year}年度 全日入院患者数予測結果")

        # 年度総患者数予測テーブル
        if 'forecast_annual_summary_df' in st.session_state and \
           st.session_state.forecast_annual_summary_df is not None and \
           not st.session_state.forecast_annual_summary_df.empty:
            st.markdown("##### 年度総患者数予測（各モデル別）")
            st.dataframe(
                st.session_state.forecast_annual_summary_df.style.format("{:,.0f}"), 
                use_container_width=True
            )

        # 予測比較グラフ
        if create_forecast_comparison_chart:
            st.markdown("##### 予測比較グラフ")
            daily_total_patients_for_chart = prepare_daily_total_patients(df)
            
            # 表示期間の調整
            display_past_days_chart = 180 
            forecast_end_date_chart = pd.Timestamp(f"{predict_fiscal_year + 1}-03-31")
            display_future_days_chart = min(365, (forecast_end_date_chart - daily_total_patients_for_chart.index.max()).days + 1) if not daily_total_patients_for_chart.empty else 365
            display_future_days_chart = max(0, display_future_days_chart)

            forecast_comparison_fig = create_forecast_comparison_chart(
                daily_total_patients_for_chart,
                st.session_state.forecast_model_results,
                title=f"{predict_fiscal_year}年度 全日入院患者数予測比較",
                display_days_past=display_past_days_chart,
                display_days_future=display_future_days_chart 
            )
            if forecast_comparison_fig:
                st.plotly_chart(forecast_comparison_fig, use_container_width=True)
            else:
                st.warning("予測比較グラフの生成に失敗しました。")
        else:
            st.warning("グラフ生成関数が利用できません。")

        # 詳細データの表示
        with st.expander("各モデルの日次予測データ詳細を見る"):
            for model_name, pred_series_data in st.session_state.forecast_model_results.items():
                if pred_series_data is not None and not pred_series_data.empty:
                    st.markdown(f"###### {model_name}モデルによる日次予測")
                    # データを見やすい形式で表示
                    display_data = pred_series_data.head(100).round(1).to_frame("予測患者数")
                    display_data.index = display_data.index.strftime('%Y-%m-%d')
                    st.dataframe(display_data, use_container_width=True, height=300)
                else:
                    st.markdown(f"###### {model_name}モデル")
                    st.text("予測データがありません。")
    elif st.session_state.get('data_processed', False):
        st.info("上記で予測対象年度とモデルを選択し、「予測を実行」ボタンを押してください。")