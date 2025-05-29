# forecast_analysis_tab.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time

# 既存のモジュールから必要な関数をインポート
# パスが通っていること、および関数が期待通りに動作することが前提です。
try:
    from forecast_models import (
        simple_moving_average_forecast,
        holt_winters_forecast,
        arima_forecast,
        prepare_daily_total_patients, # データ準備関数もこちらにある想定
        generate_annual_forecast_summary,
        # evaluate_model # 必要であれば精度評価関数も
    )
    from chart import create_forecast_comparison_chart
    # forecast.py からも必要に応じてインポート
    # from forecast import some_utility_function 
except ImportError as e:
    st.error(f"予測分析タブに必要なモジュールのインポートに失敗しました: {e}")
    # モジュールがなければ、以降の処理でエラーになるため、ダミー関数等を定義するか、処理を制限
    prepare_daily_total_patients = None
    simple_moving_average_forecast = None
    holt_winters_forecast = None
    arima_forecast = None
    generate_annual_forecast_summary = None
    create_forecast_comparison_chart = None

def display_forecast_analysis_tab():
    """
    予測分析タブのUIとロジックを表示する関数。
    必要なデータ (df, latest_data_date_str など) は 
    st.session_state から取得することを想定しています。
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
        current_year = pd.Timestamp.now().year
        # データの最新日に基づいてデフォルトの予測対象年度を決定
        default_pred_year = latest_data_date.year
        if latest_data_date.month < 4: # 1-3月なら前年度の会計年度が進行中
            default_pred_year -= 1
        
        available_pred_years = list(range(default_pred_year - 1, default_pred_year + 3)) # 例: 前年度～2年先
        try:
            default_pred_year_index = available_pred_years.index(default_pred_year)
        except ValueError:
            default_pred_year_index = 0 # リストにない場合は先頭

        predict_fiscal_year = st.selectbox(
            "予測対象年度",
            options=available_pred_years,
            index=default_pred_year_index,
            format_func=lambda year: f"{year}年度" # 表示形式 (例: 2025年度)
        )

    with col_pred_set2:
        model_options = []
        if simple_moving_average_forecast: model_options.append("単純移動平均")
        if holt_winters_forecast: model_options.append("Holt-Winters")
        if arima_forecast: model_options.append("ARIMA")
        
        selected_models = st.multiselect(
            "比較する予測モデルを選択",
            options=model_options,
            default=model_options # デフォルトですべて選択
        )

    with st.expander("モデルパラメータ詳細設定（上級者向け）", expanded=False):
        sma_window = st.slider("単純移動平均: ウィンドウサイズ（日数）", 1, 90, 7, key="pred_sma_window")
        hw_seasonal_periods = st.slider("Holt-Winters: 季節周期（日数）", 1, 365, 7, key="pred_hw_seasonal_periods", help="週周期なら7、年周期なら365など。")
        arima_m = st.slider("ARIMA: 季節周期 (m)", 1, 52, 7, key="pred_arima_m", help="週周期の季節性(m=7)を考慮します。")

    if st.button("予測を実行", key="run_prediction_button_main", use_container_width=True):
        if not selected_models:
            st.warning("比較するモデルを1つ以上選択してください。")
        elif not all([prepare_daily_total_patients, generate_annual_forecast_summary, create_forecast_comparison_chart]):
            st.error("予測に必要な関数がインポートされていません。")
        else:
            with st.spinner(f"{predict_fiscal_year}年度の患者数予測を実行中..."):
                forecast_start_time = time.time()
                
                daily_total_patients = prepare_daily_total_patients(df) # 予測用の日次全患者数データを準備

                if daily_total_patients.empty:
                    st.error("予測用の日次患者数データを作成できませんでした。元データを確認してください。")
                else:
                    forecast_model_results_dict = {} # モデルごとの予測結果 (pd.Series) を格納
                    forecast_annual_summary_list = [] # 年度集計結果を格納するリスト

                    forecast_horizon_end_date = pd.Timestamp(f"{predict_fiscal_year + 1}-03-31")
                    last_data_date_for_pred = daily_total_patients.index.max()
                    
                    horizon_days = 0
                    if last_data_date_for_pred < forecast_horizon_end_date:
                        horizon_days = (forecast_horizon_end_date - last_data_date_for_pred).days
                    
                    if horizon_days <= 0:
                        st.warning(f"{predict_fiscal_year}年度末までの予測期間がありません。実績データが既に年度末を超えているか、対象年度を確認してください。")
                    else:
                        for model_name in selected_models:
                            pred_series = None
                            model_start_time = time.time()
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
                                            "実績総患者数": annual_sum.get("実績総患者数"),
                                            "予測総患者数": annual_sum.get("予測総患者数"),
                                            f"{predict_fiscal_year}年度 総患者数（予測込）": annual_sum.get("年度総患者数（予測込）")
                                        })
                                model_end_time = time.time()
                                print(f"モデル '{model_name}' 予測完了: {model_end_time - model_start_time:.2f}秒")
                            except Exception as e_model:
                                st.warning(f"{model_name}モデルの予測中にエラーが発生しました: {e_model}")
                        
                        # セッションステートに結果を保存
                        st.session_state.forecast_model_results = forecast_model_results_dict
                        if forecast_annual_summary_list:
                            st.session_state.forecast_annual_summary_df = pd.DataFrame(forecast_annual_summary_list).set_index("モデル名")
                        else:
                            st.session_state.forecast_annual_summary_df = pd.DataFrame()

                        forecast_end_time = time.time()
                        st.success(f"{predict_fiscal_year}年度の患者数予測が完了しました。処理時間: {forecast_end_time - forecast_start_time:.1f}秒")
                        # st.rerun() # 必要に応じて再描画

    # --- 予測結果表示 ---
    if 'forecast_model_results' in st.session_state and st.session_state.forecast_model_results:
        st.subheader(f"{predict_fiscal_year}年度 全日入院患者数予測結果")

        if create_forecast_comparison_chart:
            st.markdown("##### 予測比較グラフ")
            daily_total_patients_for_chart = prepare_daily_total_patients(df) # 再度準備
            
            # 表示期間の調整 (実績は過去180日、予測は年度末までなど)
            display_past_days_chart = 180 
            # 予測終了日は予測年度の3月末
            forecast_end_date_chart = pd.Timestamp(f"{predict_fiscal_year + 1}-03-31")
            # 実績の最終日から予測終了日までの日数を計算
            display_future_days_chart = (forecast_end_date_chart - daily_total_patients_for_chart.index.max()).days +1 if not daily_total_patients_for_chart.empty else 0
            display_future_days_chart = max(0, display_future_days_chart) # マイナスにならないように

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
            st.warning("グラフ生成関数 (create_forecast_comparison_chart) が利用できません。")

        if 'forecast_annual_summary_df' in st.session_state and \
           st.session_state.forecast_annual_summary_df is not None and \
           not st.session_state.forecast_annual_summary_df.empty:
            st.markdown("##### 年度総患者数予測（各モデル別）")
            st.dataframe(st.session_state.forecast_annual_summary_df.style.format("{:,.0f}"), use_container_width=True)
        else:
            st.info("年度総患者数の集計結果はありません。")

        with st.expander("各モデルの日次予測データ詳細を見る"):
            for model_name, pred_series_data in st.session_state.forecast_model_results.items():
                if pred_series_data is not None and not pred_series_data.empty:
                    st.markdown(f"###### {model_name}モデルによる日次予測")
                    st.dataframe(pred_series_data.head(100).round(1).rename("予測患者数"), use_container_width=True, height=300)
                else:
                    st.markdown(f"###### {model_name}モデル")
                    st.text("予測データがありません。")
    elif st.session_state.get('data_processed', False):
        st.info("上記で予測対象年度とモデルを選択し、「予測を実行」ボタンを押してください。")

