import pandas as pd
import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing
import pmdarima as pm
from sklearn.metrics import mean_squared_error
from datetime import timedelta
import streamlit as st
import time
import threading
import concurrent.futures
import os
import gc
import psutil  # プロセス情報取得用に追加
import warnings  # 警告メッセージ用に追加

# スレッド数の最適化
N_JOBS = min(4, max(1, (os.cpu_count() or 1) - 1))
# forecast_models.py - 予測モデル並列処理

def run_forecasts_in_parallel(daily_total_patients, predict_fiscal_year, selected_models, model_params):
    """
    複数の予測モデルを並列実行する

    Parameters:
    -----------
    daily_total_patients : pd.Series
        日次患者データ
    predict_fiscal_year : int
        予測対象年度
    selected_models : list
        選択されたモデル名のリスト
    model_params : dict
        モデルごとのパラメータ

    Returns:
    --------
    dict
        モデル名 -> 予測結果の辞書
    """
    results = {}
    forecast_horizon_end_date = pd.Timestamp(f"{predict_fiscal_year + 1}-03-31")

    # 学習データ最終日から予測終了日までの日数を計算
    if daily_total_patients.index.max() < forecast_horizon_end_date:
        horizon_days = (forecast_horizon_end_date - daily_total_patients.index.max()).days
    else:
        horizon_days = 0

    if horizon_days <= 0:
        st.warning(f"{predict_fiscal_year}年度末までの予測期間がありません。")
        return {}

    # 進捗バーの初期化
    progress_placeholder = st.empty()
    progress_bar = progress_placeholder.progress(0, text="予測モデルの実行準備中...")

    start_time = time.time()

    try:
        # ThreadPoolExecutorで並列処理
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(selected_models), 4)) as executor:
            futures = {}

            # 各モデルの実行をスケジュール
            for idx, model_name in enumerate(selected_models):
                if model_name == "単純移動平均":
                    window = model_params.get("sma_window", 7)
                    futures[executor.submit(simple_moving_average_forecast, daily_total_patients, window, horizon_days)] = model_name

                elif model_name == "Holt-Winters":
                    seasonal_periods = model_params.get("hw_seasonal_periods", 7)
                    futures[executor.submit(holt_winters_forecast, daily_total_patients, seasonal_periods, forecast_horizon=horizon_days)] = model_name

                elif model_name == "ARIMA":
                    m = model_params.get("arima_m", 7)
                    futures[executor.submit(arima_forecast, daily_total_patients, forecast_horizon=horizon_days, m=m)] = model_name

            # 完了したモデルをカウント
            completed = 0
            total = len(futures)

            # 結果を収集
            for future in concurrent.futures.as_completed(futures):
                model_name = futures[future]
                try:
                    forecast_result = future.result()
                    if forecast_result is not None and not forecast_result.empty:
                        results[model_name] = forecast_result

                    # 進捗更新
                    completed += 1
                    progress = int(completed / total * 100)
                    progress_bar.progress(progress, f"予測計算中: {completed}/{total} モデル完了")

                except Exception as e:
                    st.warning(f"{model_name}モデルの予測に失敗: {e}")

    except Exception as e:
        st.error(f"予測処理中にエラーが発生しました: {e}")

    finally:
        # 進捗表示を削除
        progress_placeholder.empty()

        end_time = time.time()
        print(f"予測モデル実行完了: {len(results)} モデル、処理時間: {end_time - start_time:.2f}秒")

        # メモリ解放
        gc.collect()

    return results

# データを準備するための最適化関数（キャッシュ対応）
@st.cache_data(ttl=3600, show_spinner=False)
def prepare_daily_total_patients(df):
    """全日入院患者数の日次時系列データを準備する（最適化版）"""
    if df is None or df.empty:
        return pd.Series(dtype=float)

    start_time = time.time()

    # 集計の高速化 - sorted=Falseを追加（既にソートされていることを前提）
    daily_total = df.groupby('日付')['入院患者数（在院）'].sum()
    daily_total.index = pd.to_datetime(daily_total.index)

    # データが既にソートされているか確認し、必要ならソート
    if not daily_total.index.is_monotonic_increasing:
        daily_total = daily_total.sort_index()

    # asfreqの代わりにreindexを使用（より効率的）
    date_range = pd.date_range(daily_total.index.min(), daily_total.index.max(), freq='D')
    daily_total = daily_total.reindex(date_range)

    # 欠損値を効率的に補完
    if daily_total.isna().any():
        # 線形補間（大きな欠損がない場合に効果的）
        daily_total = daily_total.interpolate(method='linear')

        # 残りの欠損値を処理
        daily_total = daily_total.fillna(method='bfill').fillna(method='ffill')

    end_time = time.time()
    print(f"患者データ準備完了: {len(daily_total)}日分、処理時間: {end_time - start_time:.2f}秒")

    return daily_total

# --- 予測モデル ---
# 予測モデル関数の最適化
@st.cache_data(ttl=3600, show_spinner=False)
def simple_moving_average_forecast(series, window, forecast_horizon):
    """単純移動平均による予測（最適化版）"""
    if series.empty or len(series) < window:
        empty_forecast = pd.Series(
            index=pd.date_range(
                start=pd.Timestamp.now(),
                periods=forecast_horizon,
                freq='D'
            ),
            dtype=float
        )
        return empty_forecast

    # 移動平均の計算を最適化
    last_window = series.iloc[-window:]
    window_mean = last_window.mean()

    # numpy配列を使用した効率的な予測値生成
    forecast_values = np.full(forecast_horizon, window_mean)
    forecast_index = pd.date_range(start=series.index[-1] + timedelta(days=1), periods=forecast_horizon, freq='D')

    return pd.Series(forecast_values, index=forecast_index)

@st.cache_data(ttl=7200, show_spinner=False)
def holt_winters_forecast(series, seasonal_periods, trend='add', seasonal='add', forecast_horizon=365):
    """Holt-Winters法による予測（最適化版）"""
    if series.empty or len(series) < seasonal_periods * 2:
        # データ不足時は最終値を使用
        last_value = series.iloc[-1] if not series.empty else 0
        return pd.Series(
            [last_value] * forecast_horizon,
            index=pd.date_range(
                start=series.index[-1] + timedelta(days=1) if not series.empty else pd.Timestamp.now(),
                periods=forecast_horizon,
                freq='D'
            )
        )

    try:
        start_time = time.time()

        # 値が正である必要があるため、負の値を処理
        min_value = series.min()
        if min_value <= 0:
            offset = abs(min_value) + 1
            adjusted_series = series + offset
        else:
            adjusted_series = series
            offset = 0

        # モデルフィッティングの最適化
        model = ExponentialSmoothing(
            adjusted_series,
            seasonal_periods=seasonal_periods,
            trend=trend,
            seasonal=seasonal,
            initialization_method="estimated",
            use_boxcox=False  # Falseの方が高速
        )
        fit = model.fit(optimized=True, remove_bias=True, use_brute=False)

        # 予測の実行
        forecast = fit.forecast(forecast_horizon)

        # オフセットがある場合は元に戻す
        if offset > 0:
            forecast = forecast - offset

        end_time = time.time()
        print(f"Holt-Winters予測完了: {len(forecast)}日分、処理時間: {end_time - start_time:.2f}秒")

        return forecast

    except Exception as e:
        print(f"Holt-Wintersモデルエラー: {e}")
        # エラー時は単純予測を返す
        if not series.empty:
            last_values = series.iloc[-min(30, len(series)):]
            avg_value = last_values.mean()
            return pd.Series(
                [avg_value] * forecast_horizon,
                index=pd.date_range(start=series.index[-1] + timedelta(days=1), periods=forecast_horizon, freq='D')
            )
        else:
            # 空のシリーズの場合
            return pd.Series(
                [0] * forecast_horizon,
                index=pd.date_range(start=pd.Timestamp.now(), periods=forecast_horizon, freq='D')
            )

@st.cache_data(ttl=7200, show_spinner=False)
def arima_forecast(series, forecast_horizon=365, seasonal=True, m=7):
    """ARIMA/SARIMAモデルによる予測（最適化版）"""
    if series.empty or len(series) < m * 2:
        return pd.Series(
            [0] * forecast_horizon,
            index=pd.date_range(start=pd.Timestamp.now(), periods=forecast_horizon, freq='D')
        )

    try:
        start_time = time.time()

        # ARIMAモデルのパラメータ
        # より効率的なパラメータ探索のための設定
        model = pm.auto_arima(
            series,
            seasonal=seasonal,
            m=m,  # 週周期
            stepwise=True,  # ステップワイズ探索（高速）
            suppress_warnings=True,
            error_action='ignore',
            max_order=5,  # 高次の次数は避ける（計算量削減）
            max_p=2, max_d=1, max_q=2,  # パラメータ範囲を制限
            max_P=1, max_D=1, max_Q=1,  # 季節パラメータも制限
            n_jobs=N_JOBS,  # 並列処理
            trace=False,
            information_criterion='aic'
        )

        # 予測の実行
        forecast, conf_int = model.predict(n_periods=forecast_horizon, return_conf_int=True)

        forecast_series = pd.Series(
            forecast,
            index=pd.date_range(start=series.index[-1] + timedelta(days=1), periods=forecast_horizon, freq='D')
        )

        end_time = time.time()
        print(f"ARIMA予測完了: {len(forecast_series)}日分、処理時間: {end_time - start_time:.2f}秒")

        return forecast_series

    except Exception as e:
        print(f"ARIMAモデルエラー: {e}")
        # エラー時は単純予測を返す
        last_value = series.iloc[-1] if not series.empty else 0
        return pd.Series(
            [last_value] * forecast_horizon,
            index=pd.date_range(start=series.index[-1] + timedelta(days=1), periods=forecast_horizon, freq='D')
        )

# --- 予測結果の集計と評価 ---
def calculate_fiscal_year_total(series, fiscal_year_start_date, fiscal_year_end_date):
    """ 指定された会計年度の合計値を計算する """
    return series[(series.index >= fiscal_year_start_date) & (series.index <= fiscal_year_end_date)].sum()

def generate_annual_forecast_summary(actual_series, forecast_series, current_date, target_fiscal_year):
    """
    実績と予測から指定年度の総患者数を計算する

    Parameters:
    -----------
    actual_series : pd.Series
        実績の日次患者数 (インデックスは日付)
    forecast_series : pd.Series
        予測の日次患者数 (インデックスは日付)
    current_date : pd.Timestamp
        データ上の最新日
    target_fiscal_year : int
        予測対象の年度 (例: 2025)

    Returns:
    --------
    dict
        実績総数, 予測総数, 年度総計
    """
    fy_start = pd.Timestamp(f"{target_fiscal_year}-04-01")
    fy_end = pd.Timestamp(f"{target_fiscal_year + 1}-03-31")

    # 実績期間の計算
    actual_period_data = actual_series[(actual_series.index >= fy_start) & (actual_series.index <= current_date)]
    total_actual_patients = actual_period_data.sum()

    # 予測期間の計算
    # current_date の翌日から年度末まで
    forecast_start_date = current_date + timedelta(days=1)
    if forecast_start_date > fy_end: # 既に年度末を過ぎている場合
        total_forecast_patients = 0
    else:
        forecast_period_data = forecast_series[(forecast_series.index >= forecast_start_date) & (forecast_series.index <= fy_end)]
        total_forecast_patients = forecast_period_data.sum()
        # 予測期間が実績期間と重複しないようにする（通常は問題ないはず）
        if not forecast_period_data.empty and not actual_period_data.empty and forecast_period_data.index.min() <= actual_period_data.index.max():
             st.warning("予測期間と実績期間が重複しています。予測ロジックを確認してください。")


    total_fiscal_year_patients = total_actual_patients + total_forecast_patients

    return {
        "実績総患者数": round(total_actual_patients,0),
        "予測総患者数": round(total_forecast_patients,0),
        "年度総患者数（予測込）": round(total_fiscal_year_patients,0)
    }


def evaluate_model(actual_series, forecast_series):
    """ モデルの精度を評価する (RMSE) """
    # 共通の期間で比較
    common_index = actual_series.index.intersection(forecast_series.index)
    if common_index.empty:
        return np.nan
    rmse = np.sqrt(mean_squared_error(actual_series[common_index], forecast_series[common_index]))
    return round(rmse, 2)