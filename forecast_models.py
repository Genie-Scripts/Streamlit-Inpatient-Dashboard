import pandas as pd
import numpy as np
from datetime import timedelta
import streamlit as st
import warnings

# statsmodelsとpmdarimaの動的インポート
try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    st.warning("statsmodelsがインストールされていません。Holt-Winters予測は利用できません。")

try:
    import pmdarima as pm
    PMDARIMA_AVAILABLE = True
except ImportError:
    PMDARIMA_AVAILABLE = False
    st.warning("pmdarimaがインストールされていません。ARIMA予測は利用できません。")

# 警告を抑制
warnings.filterwarnings('ignore')

@st.cache_data(ttl=3600, show_spinner=False)
def prepare_daily_total_patients(df):
    """全日入院患者数の日次時系列データを準備する"""
    if df is None or df.empty:
        return pd.Series(dtype=float)

    try:
        # 日付列がdatetime型であることを確認
        if not pd.api.types.is_datetime64_dtype(df['日付']):
            df = df.copy()
            df['日付'] = pd.to_datetime(df['日付'])
        
        # 日次の合計患者数を計算
        daily_total = df.groupby('日付')['入院患者数（在院）'].sum()
        
        # インデックスがDatetimeIndexであることを確認
        if not isinstance(daily_total.index, pd.DatetimeIndex):
            daily_total.index = pd.to_datetime(daily_total.index)
        
        # 日付順にソート
        daily_total = daily_total.sort_index()
        
        # 日付の連続性を確保（欠損日を0で埋める）
        date_range = pd.date_range(
            start=daily_total.index.min(), 
            end=daily_total.index.max(), 
            freq='D'
        )
        daily_total = daily_total.reindex(date_range, fill_value=0)
        
        # 負の値を0に置換
        daily_total = daily_total.clip(lower=0)
        
        return daily_total
        
    except Exception as e:
        st.error(f"日次患者数データの準備中にエラーが発生しました: {e}")
        return pd.Series(dtype=float)

def simple_moving_average_forecast(series, window=7, forecast_horizon=365):
    """単純移動平均による予測"""
    if series.empty or len(series) < window:
        # データ不足の場合は空のSeriesを返す
        return pd.Series(
            index=pd.date_range(
                start=pd.Timestamp.now(),
                periods=forecast_horizon,
                freq='D'
            ),
            dtype=float
        )

    try:
        # 最後のwindow日分の平均を計算
        recent_data = series.iloc[-window:]
        avg_value = recent_data.mean()
        
        # 予測値を生成
        forecast_index = pd.date_range(
            start=series.index[-1] + timedelta(days=1), 
            periods=forecast_horizon, 
            freq='D'
        )
        forecast_values = np.full(forecast_horizon, avg_value)
        
        return pd.Series(forecast_values, index=forecast_index)
        
    except Exception as e:
        st.error(f"移動平均予測でエラーが発生しました: {e}")
        return pd.Series(dtype=float)

def holt_winters_forecast(series, seasonal_periods=7, trend='add', seasonal='add', forecast_horizon=365):
    """Holt-Winters法による予測"""
    if not STATSMODELS_AVAILABLE:
        st.error("Holt-Winters予測にはstatsmodelsが必要です。")
        return pd.Series(dtype=float)
    
    if series.empty or len(series) < seasonal_periods * 2:
        # データ不足時は最終値を使用
        last_value = series.iloc[-1] if not series.empty else 0
        forecast_index = pd.date_range(
            start=series.index[-1] + timedelta(days=1) if not series.empty else pd.Timestamp.now(),
            periods=forecast_horizon,
            freq='D'
        )
        return pd.Series([last_value] * forecast_horizon, index=forecast_index)

    try:
        # データの前処理
        # 負の値や0を小さな正の値に置換（Holt-Wintersは正の値が必要）
        min_value = series.min()
        if min_value <= 0:
            offset = abs(min_value) + 1
            adjusted_series = series + offset
        else:
            adjusted_series = series
            offset = 0

        # Holt-Wintersモデルの作成と学習
        model = ExponentialSmoothing(
            adjusted_series,
            seasonal_periods=seasonal_periods,
            trend=trend,
            seasonal=seasonal,
            initialization_method="estimated"
        )
        
        fit = model.fit(optimized=True, remove_bias=True)
        
        # 予測の実行
        forecast = fit.forecast(forecast_horizon)
        
        # オフセットがある場合は元に戻す
        if offset > 0:
            forecast = forecast - offset
            # 負の値が出た場合は0にクリップ
            forecast = forecast.clip(lower=0)
        
        return forecast

    except Exception as e:
        st.error(f"Holt-Winters予測でエラーが発生しました: {e}")
        # エラー時は単純予測を返す
        if not series.empty:
            last_values = series.iloc[-min(30, len(series)):]
            avg_value = last_values.mean()
            forecast_index = pd.date_range(
                start=series.index[-1] + timedelta(days=1), 
                periods=forecast_horizon, 
                freq='D'
            )
            return pd.Series([avg_value] * forecast_horizon, index=forecast_index)
        else:
            return pd.Series(dtype=float)

def arima_forecast(series, forecast_horizon=365, seasonal=True, m=7):
    """ARIMA/SARIMAモデルによる予測"""
    if not PMDARIMA_AVAILABLE:
        st.error("ARIMA予測にはpmdarimaが必要です。")
        return pd.Series(dtype=float)
    
    if series.empty or len(series) < m * 2:
        # データ不足時は最終値を使用
        last_value = series.iloc[-1] if not series.empty else 0
        forecast_index = pd.date_range(
            start=series.index[-1] + timedelta(days=1) if not series.empty else pd.Timestamp.now(),
            periods=forecast_horizon,
            freq='D'
        )
        return pd.Series([last_value] * forecast_horizon, index=forecast_index)

    try:
        # ARIMAモデルの自動選択と学習
        model = pm.auto_arima(
            series,
            seasonal=seasonal,
            m=m,  # 季節周期
            stepwise=True,  # 高速化
            suppress_warnings=True,
            error_action='ignore',
            max_order=3,  # 計算量削減のため次数を制限
            max_p=2, max_d=1, max_q=2,
            max_P=1, max_D=1, max_Q=1,
            trace=False,
            information_criterion='aic'
        )

        # 予測の実行
        forecast, conf_int = model.predict(n_periods=forecast_horizon, return_conf_int=True)

        forecast_index = pd.date_range(
            start=series.index[-1] + timedelta(days=1), 
            periods=forecast_horizon, 
            freq='D'
        )
        forecast_series = pd.Series(forecast, index=forecast_index)
        
        # 負の値を0にクリップ
        forecast_series = forecast_series.clip(lower=0)

        return forecast_series

    except Exception as e:
        st.error(f"ARIMA予測でエラーが発生しました: {e}")
        # エラー時は単純予測を返す
        if not series.empty:
            last_value = series.iloc[-1]
            forecast_index = pd.date_range(
                start=series.index[-1] + timedelta(days=1), 
                periods=forecast_horizon, 
                freq='D'
            )
            return pd.Series([last_value] * forecast_horizon, index=forecast_index)
        else:
            return pd.Series(dtype=float)

def generate_annual_forecast_summary(actual_series, forecast_series, current_date, target_fiscal_year):
    """
    実績と予測から指定年度の総患者数を計算する
    """
    try:
        fy_start = pd.Timestamp(f"{target_fiscal_year}-04-01")
        fy_end = pd.Timestamp(f"{target_fiscal_year + 1}-03-31")

        # 実績期間の計算（年度開始から現在まで）
        actual_period_data = actual_series[
            (actual_series.index >= fy_start) & 
            (actual_series.index <= current_date)
        ]
        total_actual_patients = actual_period_data.sum() if not actual_period_data.empty else 0

        # 予測期間の計算（現在の翌日から年度末まで）
        forecast_start_date = current_date + timedelta(days=1)
        if forecast_start_date > fy_end:
            # 既に年度末を過ぎている場合
            total_forecast_patients = 0
        else:
            forecast_period_data = forecast_series[
                (forecast_series.index >= forecast_start_date) & 
                (forecast_series.index <= fy_end)
            ]
            total_forecast_patients = forecast_period_data.sum() if not forecast_period_data.empty else 0

        total_fiscal_year_patients = total_actual_patients + total_forecast_patients

        return {
            "実績総患者数": round(total_actual_patients, 0),
            "予測総患者数": round(total_forecast_patients, 0),
            "年度総患者数（予測込）": round(total_fiscal_year_patients, 0)
        }
        
    except Exception as e:
        st.error(f"年度集計計算でエラーが発生しました: {e}")
        return {
            "実績総患者数": 0,
            "予測総患者数": 0,
            "年度総患者数（予測込）": 0
        }