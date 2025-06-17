# chart.py (修正版)
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.font_manager
import gc
import time
import hashlib
import logging # ロギングを追加

logger = logging.getLogger(__name__) # ロガーを取得

# get_chart_cache, get_data_hash, get_chart_cache_key は、
# @st.cache_data を全面的に使用する場合、必須ではなくなります。
# BytesIOオブジェクト自体を@st.cache_dataでキャッシュできるためです。
# ただし、Plotlyのグラフオブジェクトなど、キャッシュできないものを扱う場合は
# 別の戦略が必要になることがあります。ここではMatplotlib生成のBytesIOをキャッシュします。

@st.cache_data(ttl=1800, show_spinner=False)
def create_patient_chart(data, title="入院患者数推移", days=90, show_moving_average=True, font_name_for_mpl=None):
    """データから患者数推移グラフを作成する（キャッシュ対応版）- Matplotlib PDF用"""
    start_time = time.time()
    fig = None
    try:
        fig, ax = plt.subplots(figsize=(10, 5.5))

        if not isinstance(data, pd.DataFrame) or data.empty:
            if fig: plt.close(fig)
            return None

        if "日付" not in data.columns or "入院患者数（在院）" not in data.columns:
            if fig: plt.close(fig)
            return None

        data_copy = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)

        grouped = data_copy.groupby("日付")["入院患者数（在院）"].sum().reset_index().sort_values("日付")

        if len(grouped) > days:
            grouped = grouped.tail(days)

        if grouped.empty:
            if fig: plt.close(fig)
            return None

        ax.plot(grouped["日付"], grouped["入院患者数（在院）"], marker='o', linestyle='-', linewidth=1.5, markersize=3, color='#3498db', label='入院患者数')
        avg = grouped["入院患者数（在院）"].mean()
        ax.axhline(y=avg, color='#e74c3c', linestyle='--', alpha=0.7, linewidth=1, label=f'平均: {avg:.1f}')

        if show_moving_average and len(grouped) >= 7:
            grouped['7日移動平均'] = grouped["入院患者数（在院）"].rolling(window=7, min_periods=1).mean()
            ax.plot(grouped["日付"], grouped['7日移動平均'], linestyle='-', linewidth=1.2, color='#2ecc71', label='7日移動平均')

        font_kwargs = {}
        if font_name_for_mpl:
            font_kwargs['fontname'] = font_name_for_mpl

        ax.set_title(title, fontsize=12, **font_kwargs)
        ax.set_xlabel('日付', fontsize=9, **font_kwargs)
        ax.set_ylabel('患者数', fontsize=9, **font_kwargs)

        ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        legend_prop = {'size': 7}
        if font_name_for_mpl: legend_prop['family'] = font_name_for_mpl
        ax.legend(prop=legend_prop)

        fig.autofmt_xdate(rotation=30, ha='right')
        ax.tick_params(axis='x', labelsize=7)
        ax.tick_params(axis='y', labelsize=7)

        plt.tight_layout(pad=0.5)
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)

        end_time = time.time()
        logger.info(f"グラフ '{title}' 生成完了 (@st.cache_data), 処理時間: {end_time - start_time:.2f}秒")
        return buf
    except Exception as e:
        logger.error(f"グラフ生成エラー '{title}': {e}", exc_info=True)
        return None
    finally:
        if fig: plt.close(fig)
        gc.collect()


def create_interactive_patient_chart(data, title="入院患者数推移", days=90, show_moving_average=True, target_value=None, chart_type="全日"):
    """
    インタラクティブな患者数推移グラフを作成する (Plotly)
    """
    try:
        if not isinstance(data, pd.DataFrame) or data.empty:
            logger.warning(f"create_interactive_patient_chart: '{title}' のデータが空です。")
            return None
        if "日付" not in data.columns or "入院患者数（在院）" not in data.columns:
            logger.warning(f"create_interactive_patient_chart: '{title}' のデータに必要な列（日付, 入院患者数（在院））がありません。")
            return None

        data_copy = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)

        grouped = data_copy.groupby("日付")["入院患者数（在院）"].sum().reset_index().sort_values("日付")
        
        if grouped.empty:
            logger.warning(f"create_interactive_patient_chart: '{title}' のグループ化後データが空です。")
            return None
            
        if len(grouped) > days:
            if days > 0:
                grouped = grouped.tail(days)

        if grouped.empty:
            logger.warning(f"create_interactive_patient_chart: '{title}' の期間絞り込み後データが空です（days: {days}）。")
            return None

        avg = grouped["入院患者数（在院）"].mean()
        if len(grouped) >= 7: 
            grouped['7日移動平均'] = grouped["入院患者数（在院）"].rolling(window=7, min_periods=1).mean()

        fig = make_subplots()
        
        # 基本的なグラフ要素
        fig.add_trace(go.Scatter(
            x=grouped["日付"], 
            y=grouped["入院患者数（在院）"], 
            mode='lines+markers', 
            name='入院患者数', 
            line=dict(color='#3498db', width=2), 
            marker=dict(size=6)
        ))
        
        if show_moving_average and '7日移動平均' in grouped.columns:
            fig.add_trace(go.Scatter(
                x=grouped["日付"], 
                y=grouped['7日移動平均'], 
                mode='lines', 
                name='7日移動平均', 
                line=dict(color='#2ecc71', width=2)
            ))
        
        if not grouped.empty:
            # 平均線
            fig.add_trace(go.Scatter(
                x=[grouped["日付"].min(), grouped["日付"].max()], 
                y=[avg, avg], 
                mode='lines', 
                name=f'平均: {avg:.1f}', 
                line=dict(color='#e74c3c', width=2, dash='dash')
            ))

            if target_value is not None and pd.notna(target_value):
                # 目標線
                fig.add_trace(go.Scatter(
                    x=[grouped["日付"].min(), grouped["日付"].max()], 
                    y=[target_value, target_value], 
                    mode='lines', 
                    name=f'目標値: {target_value:.1f}', 
                    line=dict(color='#9b59b6', width=2, dash='dot')
                ))
                
                # Y軸の範囲を取得（達成ゾーン表示用）
                y_max = max(grouped["入院患者数（在院）"].max() * 1.1, target_value * 1.2)
                
                # 達成ゾーン（目標値以上）- 薄い緑色
                fig.add_trace(go.Scatter(
                    x=[grouped["日付"].min(), grouped["日付"].max(), grouped["日付"].max(), grouped["日付"].min()], 
                    y=[target_value, target_value, y_max, y_max], 
                    fill='toself', 
                    fillcolor='rgba(46, 204, 113, 0.15)',  # 薄い緑色
                    line=dict(color='rgba(46, 204, 113, 0)', width=0), 
                    name='達成ゾーン',
                    showlegend=True,
                    hoverinfo='skip'
                ))
                
                # 注意ゾーン（目標値の97%～目標値）- 薄いオレンジ色
                caution_threshold = target_value * 0.97
                fig.add_trace(go.Scatter(
                    x=[grouped["日付"].min(), grouped["日付"].max(), grouped["日付"].max(), grouped["日付"].min()], 
                    y=[caution_threshold, caution_threshold, target_value, target_value], 
                    fill='toself', 
                    fillcolor='rgba(255, 165, 0, 0.15)',  # 薄いオレンジ色
                    line=dict(color='rgba(255, 165, 0, 0)', width=0), 
                    name='注意ゾーン',
                    showlegend=True,
                    hoverinfo='skip'
                ))
                
                # Y軸の範囲を設定
                fig.update_yaxes(range=[0, y_max])

        fig.update_layout(
            title=title, 
            xaxis_title='日付', 
            yaxis_title='患者数', 
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01), 
            hovermode='x unified', 
            height=500, 
            margin=dict(l=10, r=10, t=50, b=10)
        )
        fig.update_xaxes(tickformat="%Y-%m-%d", tickangle=-45, tickmode='auto', nticks=10)
        
        return fig
        
    except Exception as e:
        logger.error(f"インタラクティブグラフ '{title}' 作成中にエラー: {e}", exc_info=True)
        return None

def create_interactive_dual_axis_chart(data, title="入院患者数と患者移動の推移", days=90):
    """
    インタラクティブな入院患者数と患者移動の7日移動平均グラフを二軸で作成する (Plotly)
    """
    try:
        if not isinstance(data, pd.DataFrame) or data.empty:
            logger.warning(f"create_interactive_dual_axis_chart: '{title}' のデータが空です。")
            return None
        required_columns = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "退院患者数"]
        if any(col not in data.columns for col in required_columns):
            missing_cols_str = ", ".join([col for col in required_columns if col not in data.columns])
            logger.warning(f"create_interactive_dual_axis_chart: '{title}' のデータに必要な列がありません。不足列: {missing_cols_str}")
            return None
        
        data_copy = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)

        grouped = data_copy.groupby("日付").agg({"入院患者数（在院）": "sum", "新入院患者数": "sum", "緊急入院患者数": "sum", "退院患者数": "sum"}).reset_index().sort_values("日付")
        
        if grouped.empty:
            logger.warning(f"create_interactive_dual_axis_chart: '{title}' のグループ化後データが空です。")
            return None

        if len(grouped) > days:
            if days > 0:
                grouped = grouped.tail(days)
        
        if grouped.empty:
            logger.warning(f"create_interactive_dual_axis_chart: '{title}' の期間絞り込み後データが空です（days: {days}）。")
            return None

        for col in required_columns[1:]: # "日付"以外
             if col in grouped.columns: # groupedに列が存在するか確認
                grouped[f'{col}_7日移動平均'] = grouped[col].rolling(window=7, min_periods=1).mean()
             else: # 実際にはaggで列が作られるはずだが念のため
                grouped[f'{col}_7日移動平均'] = 0


        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        if "入院患者数（在院）_7日移動平均" in grouped.columns:
            fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped["入院患者数（在院）_7日移動平均"], name="入院患者数（在院）", line=dict(color="#3498db", width=3), mode="lines"), secondary_y=False)

        colors_map = {"新入院患者数": "#2ecc71", "緊急入院患者数": "#e74c3c", "退院患者数": "#f39c12"}
        for col, color_val in colors_map.items():
            ma_col_name = f"{col}_7日移動平均"
            if ma_col_name in grouped.columns:
                fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped[ma_col_name], name=col, line=dict(color=color_val, width=2), mode="lines"), secondary_y=True)

        fig.update_layout(title=title, xaxis_title="日付", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5), hovermode="x unified", font=dict(family="Arial, 'Noto Sans JP', sans-serif", size=12), height=500)
        fig.update_yaxes(title_text="入院患者数（在院）", secondary_y=False)
        fig.update_yaxes(title_text="患者移動数", secondary_y=True)
        fig.update_xaxes(tickformat="%Y-%m-%d", tickangle=-45, tickmode='auto', nticks=10)
        return fig
    except Exception as e:
        logger.error(f"インタラクティブ2軸グラフ '{title}' 作成中にエラー: {e}", exc_info=True)
        return None

@st.cache_data(ttl=1800, show_spinner=False)
def create_dual_axis_chart(data, title="入院患者数と患者移動の推移", filename=None, days=90, font_name_for_mpl=None):
    """
    入院患者数と患者移動の7日移動平均グラフを二軸で作成する（Matplotlib版、PDF用）
    @st.cache_data によるキャッシュ
    """
    start_time = time.time()
    fig = None
    try:
        fig, ax1 = plt.subplots(figsize=(10, 5.5))

        if not isinstance(data, pd.DataFrame) or data.empty:
            if fig: plt.close(fig)
            return None

        required_columns = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "退院患者数"]
        if any(col not in data.columns for col in required_columns):
            if fig: plt.close(fig)
            return None

        data_copy = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)

        grouped = data_copy.groupby("日付").agg({
            "入院患者数（在院）": "sum", "新入院患者数": "sum",
            "緊急入院患者数": "sum", "退院患者数": "sum"
        }).reset_index().sort_values("日付")

        if len(grouped) > days: grouped = grouped.tail(days)
        if grouped.empty:
            if fig: plt.close(fig)
            return None

        cols_for_ma = ["入院患者数（在院）", "新入院患者数", "緊急入院患者数", "退院患者数"]
        for col in cols_for_ma:
            if col in grouped.columns:
                grouped[f'{col}_7日移動平均'] = grouped[col].rolling(window=7, min_periods=1).mean()
            else:
                logger.warning(f"Warning: Column '{col}' not found for MA in '{title}'.")
                grouped[f'{col}_7日移動平均'] = 0

        font_kwargs = {}
        if font_name_for_mpl: font_kwargs['fontname'] = font_name_for_mpl

        if "入院患者数（在院）_7日移動平均" in grouped.columns:
             ax1.plot(grouped["日付"], grouped["入院患者数（在院）_7日移動平均"], color='#3498db', linewidth=2, label="入院患者数（在院）")
        else:
            logger.warning(f"Warning: '入院患者数（在院）_7日移動平均' not found for plotting in '{title}'.")


        ax1.set_xlabel('日付', fontsize=9, **font_kwargs)
        ax1.set_ylabel('入院患者数（在院）', fontsize=9, color='#3498db', **font_kwargs)
        ax1.tick_params(axis='y', labelcolor='#3498db', labelsize=8)
        ax1.tick_params(axis='x', labelsize=8)

        ax2 = ax1.twinx()
        colors_map = {"新入院患者数": "#2ecc71", "緊急入院患者数": "#e74c3c", "退院患者数": "#f39c12"}
        for col, color_val in colors_map.items():
            ma_col_name = f"{col}_7日移動平均"
            if ma_col_name in grouped.columns:
                ax2.plot(grouped["日付"], grouped[ma_col_name], color=color_val, linewidth=1.5, label=col)

        ax2.set_ylabel('患者移動数', fontsize=9, **font_kwargs)
        ax2.tick_params(axis='y', labelsize=8)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_prop = {'size': 9}
        if font_name_for_mpl: legend_prop['family'] = font_name_for_mpl
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_prop)

        plt.title(title, fontsize=12, **font_kwargs)
        fig.autofmt_xdate(rotation=30, ha='right')
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        plt.tight_layout(pad=0.5)

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        
        end_time = time.time()
        logger.info(f"二軸グラフ '{title}' 生成完了 (@st.cache_data), 処理時間: {end_time - start_time:.2f}秒")
        return buf
    except Exception as e:
        logger.error(f"Error in create_dual_axis_chart ('{title}'): {e}", exc_info=True)
        return None
    finally:
        if fig: plt.close(fig)
        gc.collect()

@st.cache_data(ttl=1800)
def create_forecast_comparison_chart(actual_series, forecast_results, title="年度患者数予測比較", display_days_past=365, display_days_future=365):
    """
    実績データと複数の予測モデルの結果を比較するインタラクティブグラフを作成する (Plotly)
    """
    try:
        if actual_series.empty:
            logger.warning(f"create_forecast_comparison_chart: '{title}' の実績データが空です。")
            return None

        fig = go.Figure()

        if not actual_series.index.is_monotonic_increasing:
             actual_series = actual_series.sort_index()
        
        actual_display_data = actual_series # デフォルトでは全期間
        if display_days_past > 0 and len(actual_series) > display_days_past:
            actual_display_start_date = actual_series.index.max() - pd.Timedelta(days=display_days_past -1)
            actual_display_data = actual_series[actual_series.index >= actual_display_start_date]


        fig.add_trace(go.Scatter(
            x=actual_display_data.index,
            y=actual_display_data,
            mode='lines',
            name='実績患者数',
            line=dict(color='blue', width=2)
        ))

        colors = ['red', 'green', 'purple', 'orange', 'brown']

        for i, (model_name, forecast_series) in enumerate(forecast_results.items()):
            if forecast_series is None or forecast_series.empty:
                continue

            # 予測開始日と終了日を設定
            forecast_display_data = forecast_series
            if display_days_future > 0 :
                # 予測開始日を実績の最終日の翌日にするか、予測の最初の日付にするか
                pred_start_date = forecast_series.index.min()
                if not actual_series.empty:
                    pred_start_date = max(pred_start_date, actual_series.index.max() + pd.Timedelta(days=1))

                pred_end_date = pred_start_date + pd.Timedelta(days=display_days_future -1)
                forecast_display_data = forecast_series[(forecast_series.index >= pred_start_date) &
                                                        (forecast_series.index <= pred_end_date)]


            if not forecast_display_data.empty:
                fig.add_trace(go.Scatter(
                    x=forecast_display_data.index,
                    y=forecast_display_data,
                    mode='lines',
                    name=f'{model_name} (予測)',
                    line=dict(color=colors[i % len(colors)], width=2, dash='dash')
                ))

        fig.update_layout(
            title=title,
            xaxis_title='日付',
            yaxis_title='入院患者数（全日）',
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
            hovermode='x unified',
            height=500,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        fig.update_xaxes(tickformat="%Y-%m-%d", tickangle=-45)
        return fig

    except Exception as e:
        logger.error(f"予測比較グラフ '{title}' 作成中にエラー: {e}", exc_info=True)
        return None