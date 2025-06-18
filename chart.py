# chart.py (修正・機能追加版)
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
import logging

logger = logging.getLogger(__name__)

# ===== Streamlit UI用関数（キャッシュあり） =====
@st.cache_data(ttl=1800, show_spinner=False)
def create_patient_chart(data, title="入院患者数推移", days=90, show_moving_average=True, font_name_for_mpl=None):
    """データから患者数推移グラフを作成する（Streamlit UI用、キャッシュ対応版）"""
    return _create_patient_chart_core(data, title, days, show_moving_average, font_name_for_mpl)

@st.cache_data(ttl=1800, show_spinner=False)
def create_dual_axis_chart(data, title="入院患者数と患者移動の推移", filename=None, days=90, font_name_for_mpl=None):
    """入院患者数と患者移動の7日移動平均グラフを二軸で作成する（Streamlit UI用、キャッシュ対応版）"""
    return _create_dual_axis_chart_core(data, title, days, font_name_for_mpl)

# ===== PDF生成用関数（キャッシュなし、直接実行） =====
def create_patient_chart_for_pdf(data, title="入院患者数推移", days=90, show_moving_average=True, font_name_for_mpl=None):
    """PDF生成専用の患者数推移グラフ（キャッシュなし）"""
    return _create_patient_chart_core(data, title, days, show_moving_average, font_name_for_mpl)

def create_dual_axis_chart_for_pdf(data, title="入院患者数と患者移動の推移", days=90, font_name_for_mpl=None):
    """PDF生成専用の二軸グラフ（キャッシュなし）"""
    return _create_dual_axis_chart_core(data, title, days, font_name_for_mpl)

# ===== 共通のコア関数 =====
def _create_patient_chart_core(data, title="入院患者数推移", days=90, show_moving_average=True, font_name_for_mpl=None):
    """患者数推移グラフの共通コア関数"""
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

        if len(grouped) > days and days > 0:
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
        # デバッグログはlogger.debugに変更（本番では出力されない）
        logger.debug(f"グラフ '{title}' 生成完了, 処理時間: {end_time - start_time:.2f}秒")
        return buf
        
    except Exception as e:
        logger.error(f"グラフ生成エラー '{title}': {e}", exc_info=True)
        return None
    finally:
        if fig: 
            plt.close(fig)
        gc.collect()

def _create_dual_axis_chart_core(data, title="入院患者数と患者移動の推移", days=90, font_name_for_mpl=None):
    """二軸グラフの共通コア関数"""
    start_time = time.time()
    fig = None
    try:
        fig, ax1 = plt.subplots(figsize=(10, 5.5))

        if not isinstance(data, pd.DataFrame) or data.empty:
            if fig: plt.close(fig)
            return None

        required_columns = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "総退院患者数"]
        if any(col not in data.columns for col in required_columns):
            if fig: plt.close(fig)
            return None

        data_copy = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)

        grouped = data_copy.groupby("日付").agg({
            "入院患者数（在院）": "sum", "新入院患者数": "sum",
            "緊急入院患者数": "sum", "総退院患者数": "sum"
        }).reset_index().sort_values("日付")

        if len(grouped) > days and days > 0: 
            grouped = grouped.tail(days)
        if grouped.empty:
            if fig: plt.close(fig)
            return None

        cols_for_ma = ["入院患者数（在院）", "新入院患者数", "緊急入院患者数", "総退院患者数"]
        for col in cols_for_ma:
            if col in grouped.columns:
                grouped[f'{col}_7日移動平均'] = grouped[col].rolling(window=7, min_periods=1).mean()
            else:
                logger.warning(f"Warning: Column '{col}' not found for MA in '{title}'.")
                grouped[f'{col}_7日移動平均'] = 0

        font_kwargs = {}
        if font_name_for_mpl: 
            font_kwargs['fontname'] = font_name_for_mpl

        if "入院患者数（在院）_7日移動平均" in grouped.columns:
             ax1.plot(grouped["日付"], grouped["入院患者数（在院）_7日移動平均"], color='#3498db', linewidth=2, label="入院患者数（在院）")
        else:
            logger.warning(f"Warning: '入院患者数（在院）_7日移動平均' not found for plotting in '{title}'.")

        ax1.set_xlabel('日付', fontsize=9, **font_kwargs)
        ax1.set_ylabel('入院患者数（在院）', fontsize=9, color='#3498db', **font_kwargs)
        ax1.tick_params(axis='y', labelcolor='#3498db', labelsize=8)
        ax1.tick_params(axis='x', labelsize=8)

        ax2 = ax1.twinx()
        colors_map = {"新入院患者数": "#2ecc71", "緊急入院患者数": "#e74c3c", "総退院患者数": "#f39c12"}
        for col, color_val in colors_map.items():
            ma_col_name = f"{col}_7日移動平均"
            if ma_col_name in grouped.columns:
                ax2.plot(grouped["日付"], grouped[ma_col_name], color=color_val, linewidth=1.5, label=col)

        ax2.set_ylabel('患者移動数', fontsize=9, **font_kwargs)
        ax2.tick_params(axis='y', labelsize=8)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_prop = {'size': 9}
        if font_name_for_mpl: 
            legend_prop['family'] = font_name_for_mpl
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_prop)

        plt.title(title, fontsize=12, **font_kwargs)
        fig.autofmt_xdate(rotation=30, ha='right')
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        plt.tight_layout(pad=0.5)

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        
        end_time = time.time()
        logger.debug(f"二軸グラフ '{title}' 生成完了, 処理時間: {end_time - start_time:.2f}秒")
        return buf
        
    except Exception as e:
        logger.error(f"Error in _create_dual_axis_chart_core ('{title}'): {e}", exc_info=True)
        return None
    finally:
        if fig: 
            plt.close(fig)
        gc.collect()

# ===== インタラクティブグラフ関数 =====

def create_interactive_patient_chart(data, title="入院患者数推移", days=90, show_moving_average=True, target_value=None, chart_type="全日"):
    """【修正】インタラクティブな患者数推移グラフを作成する (Plotly) - PDF版の表示内容に準拠"""
    try:
        if not isinstance(data, pd.DataFrame) or data.empty:
            logger.warning(f"create_interactive_patient_chart: '{title}' のデータが空です。")
            return None
        if "日付" not in data.columns or "入院患者数（在院）" not in data.columns:
            logger.warning(f"create_interactive_patient_chart: '{title}' のデータに必要な列がありません。")
            return None

        data_copy = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)

        grouped = data_copy.groupby("日付")["入院患者数（在院）"].sum().reset_index().sort_values("日付")
        
        if grouped.empty or len(grouped) == 0:
            return None

        if len(grouped) > days and days > 0:
            grouped = grouped.tail(days)

        if grouped.empty:
            return None

        avg = grouped["入院患者数（在院）"].mean()
        if len(grouped) >= 7: 
            grouped['7日移動平均'] = grouped["入院患者数（在院）"].rolling(window=7, min_periods=1).mean()

        fig = go.Figure()
        
        # グラフ要素
        fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped["入院患者数（在院）"], mode='lines', name='入院患者数', line=dict(color='#3498db')))
        
        if show_moving_average and '7日移動平均' in grouped.columns:
            fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped['7日移動平均'], mode='lines', name='7日移動平均', line=dict(color='#2ecc71')))

        fig.add_trace(go.Scatter(x=[grouped["日付"].min(), grouped["日付"].max()], y=[avg, avg], mode='lines', name=f'平均: {avg:.1f}', line=dict(color='#e74c3c', dash='dash')))

        if target_value is not None and pd.notna(target_value):
            fig.add_trace(go.Scatter(x=[grouped["日付"].min(), grouped["日付"].max()], y=[target_value, target_value], mode='lines', name=f'目標値: {target_value:.1f}', line=dict(color='#9b59b6', dash='dot')))

        fig.update_layout(
            title={'text': title, 'x': 0.5},
            xaxis_title='日付', 
            yaxis_title='患者数', 
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), 
            hovermode='x unified', 
            height=400,
            margin=dict(l=40, r=20, t=60, b=20)
        )
        return fig
        
    except Exception as e:
        logger.error(f"インタラクティブグラフ '{title}' 作成中にエラー: {e}", exc_info=True)
        return None

def create_interactive_dual_axis_chart(data, title="患者移動と在院数の推移", days=90):
    """【修正】インタラクティブな患者移動グラフ (Plotly) - PDF版の表示内容に準拠"""
    try:
        if data is None or data.empty:
            return None
            
        required_cols = ["日付", "入院患者数（在院）", "新入院患者数", "総退院患者数"]
        if any(col not in data.columns for col in required_cols):
            return None

        data_copy = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce').dropna(subset=['日付'])

        agg_dict = {col: "sum" for col in required_cols if col != "日付"}
        grouped = data_copy.groupby("日付").agg(agg_dict).reset_index().sort_values("日付")
        
        if len(grouped) > days and days > 0:
            grouped = grouped.tail(days)
        if grouped.empty: return None

        for col in required_cols[1:]:
            grouped[f'{col}_7日MA'] = grouped[col].rolling(window=7, min_periods=1).mean()

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # 主軸: 在院患者数
        fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped["入院患者数（在院）_7日MA"], name="在院患者数(7日MA)", line=dict(color='#3498db', width=2.5)), secondary_y=False)

        # 副軸: 患者移動
        colors_map = {"新入院患者数": "#2ecc71", "総退院患者数": "#f39c12"}
        for col, color in colors_map.items():
            fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped[f'{col}_7日MA'], name=f"{col}(7日MA)", line=dict(color=color, width=2)), secondary_y=True)

        fig.update_layout(
            title={'text': title, 'x': 0.5},
            xaxis_title='日付',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode='x unified',
            height=400,
            margin=dict(l=40, r=20, t=60, b=20)
        )
        fig.update_yaxes(title_text="在院患者数", secondary_y=False)
        fig.update_yaxes(title_text="患者移動数", secondary_y=True)
        return fig
    except Exception as e:
        logger.error(f"インタラクティブ2軸グラフ '{title}' 作成中にエラー: {e}", exc_info=True)
        return None

# ★★★ 新規追加関数 ★★★
def create_interactive_alos_chart(chart_data, title="ALOS推移", days_to_show=90, moving_avg_window=30):
    """【新規】インタラクティブなALOS（平均在院日数）グラフを作成する (Plotly) - PDF版のロジックを移植"""
    try:
        if not isinstance(chart_data, pd.DataFrame) or chart_data.empty:
            return None
        
        required_columns = ["日付", "入院患者数（在院）", "総入院患者数", "総退院患者数"]
        if any(col not in chart_data.columns for col in required_columns):
            return None

        data_copy = chart_data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)
        if data_copy.empty: return None

        latest_date = data_copy['日付'].max()
        start_date_limit = latest_date - pd.Timedelta(days=days_to_show - 1)
        date_range_for_plot = pd.date_range(start=start_date_limit, end=latest_date, freq='D')
        
        daily_metrics = []
        for display_date in date_range_for_plot:
            window_start = display_date - pd.Timedelta(days=moving_avg_window - 1)
            window_data = data_copy[(data_copy['日付'] >= window_start) & (data_copy['日付'] <= display_date)]
            
            if not window_data.empty:
                total_patient_days = window_data['入院患者数（在院）'].sum()
                total_admissions = window_data['総入院患者数'].sum()
                total_discharges = window_data['総退院患者数'].sum()
                num_days_in_window = window_data['日付'].nunique()
                
                denominator = (total_admissions + total_discharges) / 2
                alos = total_patient_days / denominator if denominator > 0 else np.nan
                daily_census = total_patient_days / num_days_in_window if num_days_in_window > 0 else np.nan
                
                daily_metrics.append({'日付': display_date, '平均在院日数': alos, '平均在院患者数': daily_census})

        if not daily_metrics: return None
        daily_df = pd.DataFrame(daily_metrics).sort_values('日付')
        if daily_df.empty: return None

        # Plotlyで二軸グラフを作成
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # 主軸: 平均在院日数
        fig.add_trace(
            go.Scatter(x=daily_df['日付'], y=daily_df['平均在院日数'], name=f'平均在院日数 ({moving_avg_window}日MA)', line=dict(color='#3498db', width=2)),
            secondary_y=False
        )
        # 副軸: 平均在院患者数
        fig.add_trace(
            go.Scatter(x=daily_df['日付'], y=daily_df['平均在院患者数'], name='平均在院患者数', line=dict(color='#e74c3c', width=2, dash='dash')),
            secondary_y=True
        )

        fig.update_layout(
            title={'text': title, 'x': 0.5},
            xaxis_title='日付',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode='x unified',
            height=400,
            margin=dict(l=40, r=20, t=60, b=20)
        )
        fig.update_yaxes(title_text="平均在院日数", secondary_y=False)
        fig.update_yaxes(title_text="平均在院患者数", secondary_y=True)
        return fig

    except Exception as e:
        logger.error(f"インタラクティブALOSグラフ '{title}' 作成中にエラー: {e}", exc_info=True)
        return None

@st.cache_data(ttl=1800)
def create_forecast_comparison_chart(actual_series, forecast_results, title="年度患者数予測比較", display_days_past=365, display_days_future=365):
    """実績データと複数の予測モデルの結果を比較するインタラクティブグラフを作成する (Plotly)"""
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