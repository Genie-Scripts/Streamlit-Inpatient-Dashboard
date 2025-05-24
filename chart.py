import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.font_manager
import gc
import time  # 処理時間計測用
import hashlib  # データハッシュ計算用

# キーベースのグラフキャッシュ
global_chart_cache = {}

def get_chart_cache():
    """セッション状態のチャートキャッシュを取得"""
    if 'chart_cache' not in st.session_state:
        st.session_state.chart_cache = {}
    return st.session_state.chart_cache

def get_data_hash(data):
    """データフレームのハッシュを計算"""
    if data is None or data.empty:
        return "empty"
    try:
        # 簡易ハッシュ - 主要カラムのみ使用
        if '日付' in data.columns and '入院患者数（在院）' in data.columns:
            sample = data.head(10)
            hash_str = str(sample['日付'].tolist()) + str(sample['入院患者数（在院）'].tolist())
            return hashlib.md5(hash_str.encode()).hexdigest()[:8]
        else:
            return hashlib.md5(str(data.shape).encode()).hexdigest()[:8]
    except:
        return "error_hash"
        
@st.cache_data(ttl=1800, show_spinner=False)
def create_patient_chart(data, title="入院患者数推移", days=90, show_moving_average=True, font_name_for_mpl=None):
    """データから患者数推移グラフを作成する（キャッシュ対応版）- Matplotlib PDF用"""
    start_time = time.time()
    
    # データハッシュの計算
    data_hash = get_data_hash(data)
    cache_key = get_chart_cache_key(title, days, None, "patient_chart", data_hash)
    
    # キャッシュから取得を試みる
    cached_chart = get_cached_chart(cache_key)
    if cached_chart is not None:
        print(f"キャッシュヒット: {title} ({days}日)")
        return cached_chart
    
    fig = None
    try:
        fig, ax = plt.subplots(figsize=(10, 5.5))

        if not isinstance(data, pd.DataFrame) or data.empty:
            if fig: plt.close(fig)
            return None
            
        if "日付" not in data.columns or "入院患者数（在院）" not in data.columns:
            if fig: plt.close(fig)
            return None

        # データ集計の最適化
        grouped = data.groupby("日付")["入院患者数（在院）"].sum().reset_index()
        
        # 日付でソート
        grouped = grouped.sort_values("日付")
        
        # 対象期間に絞る
        if len(grouped) > days: 
            grouped = grouped.tail(days)
            
        if grouped.empty:
            if fig: plt.close(fig)
            return None

        ax.plot(grouped["日付"], grouped["入院患者数（在院）"], marker='o', linestyle='-', linewidth=1.5, markersize=3, color='#3498db', label='入院患者数')
        avg = grouped["入院患者数（在院）"].mean()
        ax.axhline(y=avg, color='#e74c3c', linestyle='--', alpha=0.7, linewidth=1, label=f'平均: {avg:.1f}')

        if show_moving_average and len(grouped) >= 7:
            # 移動平均の計算を最適化
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
        plt.close(fig)
        buf.seek(0)
        
        # キャッシュに保存
        cache_chart(cache_key, buf)
        
        end_time = time.time()
        print(f"グラフ生成完了: {title} ({days}日)、処理時間: {end_time - start_time:.2f}秒")
        
        return buf
    except Exception as e:
        print(f"グラフ生成エラー '{title}': {e}")
        if fig: plt.close(fig)
        gc.collect()
        return None

def create_interactive_patient_chart(data, title="入院患者数推移", days=90, show_moving_average=True, target_value=None, chart_type="全日"):
    """
    インタラクティブな患者数推移グラフを作成する (Plotly)
    """
    try:
        if not isinstance(data, pd.DataFrame) or data.empty:
            # st.error("グラフ作成には空でないデータフレームが必要です。") # Streamlit要素は適切
            return None
        if "日付" not in data.columns or "入院患者数（在院）" not in data.columns:
            # st.error("グラフ作成に必要なカラム（日付または入院患者数（在院））がデータに存在しません。")
            return None

        grouped = data.groupby("日付")["入院患者数（在院）"].sum().reset_index().sort_values("日付")
        if len(grouped) > days: grouped = grouped.tail(days)
        if grouped.empty: return None # データがない場合はNoneを返す

        avg = grouped["入院患者数（在院）"].mean()
        if len(grouped) >= 7: grouped['7日移動平均'] = grouped["入院患者数（在院）"].rolling(window=7, min_periods=1).mean()

        fig = make_subplots()
        fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped["入院患者数（在院）"], mode='lines+markers', name='入院患者数', line=dict(color='#3498db', width=2), marker=dict(size=6)))
        if show_moving_average and '7日移動平均' in grouped.columns:
            fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped['7日移動平均'], mode='lines', name='7日移動平均', line=dict(color='#2ecc71', width=2)))
        fig.add_trace(go.Scatter(x=[grouped["日付"].min(), grouped["日付"].max()], y=[avg, avg], mode='lines', name=f'平均: {avg:.1f}', line=dict(color='#e74c3c', width=2, dash='dash')))

        if target_value is not None and pd.notna(target_value):
            fig.add_trace(go.Scatter(x=[grouped["日付"].min(), grouped["日付"].max()], y=[target_value, target_value], mode='lines', name=f'目標値: {target_value:.1f}', line=dict(color='#9b59b6', width=2, dash='dot')))
            caution_threshold = target_value * 0.97
            fig.add_trace(go.Scatter(x=[grouped["日付"].min(), grouped["日付"].max(), grouped["日付"].max(), grouped["日付"].min()], y=[caution_threshold, caution_threshold, target_value, target_value], fill='toself', fillcolor='rgba(255, 165, 0, 0.2)', line=dict(color='rgba(255,165,0,0)', width=0), name='注意ゾーン', hoverinfo='none'))

        fig.update_layout(title=title, xaxis_title='日付', yaxis_title='患者数', legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01), hovermode='x unified', height=500, margin=dict(l=10, r=10, t=50, b=10))
        fig.update_xaxes(tickformat="%Y-%m-%d", tickangle=-45, tickmode='auto', nticks=10)
        return fig
    except Exception as e:
        st.error(f"インタラクティブグラフ '{title}' 作成中にエラー: {e}")
        return None

def create_interactive_dual_axis_chart(data, title="入院患者数と患者移動の推移", days=90):
    """
    インタラクティブな入院患者数と患者移動の7日移動平均グラフを二軸で作成する (Plotly)
    """
    try:
        if not isinstance(data, pd.DataFrame) or data.empty:
            # st.error("グラフ作成には空でないデータフレームが必要です。")
            return None
        required_columns = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "退院患者数"]
        if any(col not in data.columns for col in required_columns):
            # st.error(f"グラフ作成に必要なカラムがデータに存在しません: {', '.join(col for col in required_columns if col not in data.columns)}")
            return None

        grouped = data.groupby("日付").agg({"入院患者数（在院）": "sum", "新入院患者数": "sum", "緊急入院患者数": "sum", "退院患者数": "sum"}).reset_index().sort_values("日付")
        if len(grouped) > days: grouped = grouped.tail(days)
        if grouped.empty: return None

        for col in required_columns[1:]: grouped[f'{col}_7日移動平均'] = grouped[col].rolling(window=7, min_periods=1).mean()

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped["入院患者数（在院）_7日移動平均"], name="入院患者数（在院）", line=dict(color="#3498db", width=3), mode="lines"), secondary_y=False)

        colors_map = {"新入院患者数": "#2ecc71", "緊急入院患者数": "#e74c3c", "退院患者数": "#f39c12"}
        for col, color_val in colors_map.items():
            fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped[f"{col}_7日移動平均"], name=col, line=dict(color=color_val, width=2), mode="lines"), secondary_y=True)

        fig.update_layout(title=title, xaxis_title="日付", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5), hovermode="x unified", font=dict(family="Arial, 'Noto Sans JP', sans-serif", size=12), height=500)
        fig.update_yaxes(title_text="入院患者数（在院）", secondary_y=False)
        fig.update_yaxes(title_text="患者移動数", secondary_y=True)
        fig.update_xaxes(tickformat="%Y-%m-%d", tickangle=-45, tickmode='auto', nticks=10)
        return fig
    except Exception as e:
        st.error(f"インタラクティブ2軸グラフ '{title}' 作成中にエラー: {e}")
        return None

@st.cache_data(ttl=1800)
def create_dual_axis_chart(data, title="入院患者数と患者移動の推移", filename=None, days=90, font_name_for_mpl=None): # font_name_for_mpl 引数を追加
    """
    入院患者数と患者移動の7日移動平均グラフを二軸で作成する（Matplotlib版、PDF用）
    """
    fig = None
    try:
        fig, ax1 = plt.subplots(figsize=(10, 5.5)) # サイズ調整

        if not isinstance(data, pd.DataFrame) or data.empty:
            # st.warning(f"2軸グラフ生成スキップ (データ不正): '{title}'") # PDF生成時はst要素不適切
            if fig: plt.close(fig)
            return None

        required_columns = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "退院患者数"]
        if any(col not in data.columns for col in required_columns):
            # st.warning(f"2軸グラフ生成スキップ (列不足): '{title}'")
            if fig: plt.close(fig)
            return None

        grouped = data.groupby("日付").agg({"入院患者数（在院）": "sum", "新入院患者数": "sum", "緊急入院患者数": "sum", "退院患者数": "sum"}).reset_index().sort_values("日付")
        if len(grouped) > days: grouped = grouped.tail(days)
        if grouped.empty:
            # st.warning(f"2軸グラフ生成スキップ (フィルタ後データ空): '{title}'")
            if fig: plt.close(fig)
            return None

        for col in required_columns[1:]: grouped[f'{col}_7日移動平均'] = grouped[col].rolling(window=7, min_periods=1).mean()

        font_kwargs = {}
        if font_name_for_mpl:
            font_kwargs['fontname'] = font_name_for_mpl

        ax1.plot(grouped["日付"], grouped["入院患者数（在院）_7日移動平均"], color='#3498db', linewidth=2, label="入院患者数（在院）") # linewidth調整
        ax1.set_xlabel('日付', fontsize=12, **font_kwargs)
        ax1.set_ylabel('入院患者数（在院）', fontsize=12, color='#3498db', **font_kwargs)
        ax1.tick_params(axis='y', labelcolor='#3498db', labelsize=10)
        ax1.tick_params(axis='x', labelsize=10) # X軸も

        ax2 = ax1.twinx()
        colors_map = {"新入院患者数": "#2ecc71", "緊急入院患者数": "#e74c3c", "退院患者数": "#f39c12"}
        for col, color_val in colors_map.items():
            ax2.plot(grouped["日付"], grouped[f"{col}_7日移動平均"], color=color_val, linewidth=1.5, label=col) # linewidth調整

        ax2.set_ylabel('患者移動数', fontsize=12, **font_kwargs)
        ax2.tick_params(axis='y', labelsize=10)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_prop = {'size': 12}
        if font_name_for_mpl: legend_prop['family'] = font_name_for_mpl
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_prop)

        plt.title(title, fontsize=14, **font_kwargs)
        fig.autofmt_xdate(rotation=30, ha='right')
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7) # グリッドはax1に

        plt.tight_layout(pad=0.5)

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150) # DPI調整
        plt.close(fig)
        buf.seek(0)
        return buf

    except Exception as e:
        # st.error(f"2軸グラフ '{title}' 作成中にエラー: {e}") # PDF生成時はst要素不適切
        print(f"Error in create_dual_axis_chart ('{title}'): {e}") # サーバーログに出力
        if fig: plt.close(fig)
        return None

# --- ここから追加 ---
@st.cache_data(ttl=1800)
def create_forecast_comparison_chart(actual_series, forecast_results, title="年度患者数予測比較", display_days_past=365, display_days_future=365):
    """
    実績データと複数の予測モデルの結果を比較するインタラクティブグラフを作成する (Plotly)

    Parameters:
    -----------
    actual_series : pd.Series
        実績の日次患者数 (インデックスは日付)
    forecast_results : dict
        キーがモデル名、バリューが予測結果のpd.Seriesである辞書
    title : str
        グラフタイトル
    display_days_past : int
        表示する過去の日数
    display_days_future : int
        表示する未来の日数

    Returns:
    --------
    plotly.graph_objects.Figure or None
    """
    try:
        if actual_series.empty:
            st.warning("実績データが空のため、予測比較グラフを作成できません。")
            return None

        fig = go.Figure()

        # 実績データの表示範囲を決定
        if not actual_series.index.is_monotonic_increasing:
             actual_series = actual_series.sort_index() # インデックスがソートされていることを保証
        actual_display_start_date = actual_series.index.max() - pd.Timedelta(days=display_days_past -1) # -1 で該当日を含む
        actual_display_data = actual_series[actual_series.index >= actual_display_start_date]

        fig.add_trace(go.Scatter(
            x=actual_display_data.index,
            y=actual_display_data,
            mode='lines',
            name='実績患者数',
            line=dict(color='blue', width=2)
        ))

        colors = ['red', 'green', 'purple', 'orange', 'brown'] # モデルごとの色

        for i, (model_name, forecast_series) in enumerate(forecast_results.items()):
            if forecast_series is None or forecast_series.empty: # Noneチェック追加
                continue

            # 予測データの表示範囲を決定
            # 実績の最終日の翌日から表示
            if not actual_series.empty:
                 forecast_display_start_date = actual_series.index.max() + pd.Timedelta(days=1)
            else:
                 # 実績データがない場合 (通常はないはずだが念のため)
                 forecast_display_start_date = forecast_series.index.min()

            forecast_display_end_date = forecast_display_start_date + pd.Timedelta(days=display_days_future -1)

            # 予測期間が実績期間の最終日より後であることを確認
            display_forecast = forecast_series[(forecast_series.index >= forecast_display_start_date) &
                                               (forecast_series.index <= forecast_display_end_date)]


            if not display_forecast.empty:
                fig.add_trace(go.Scatter(
                    x=display_forecast.index,
                    y=display_forecast,
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
        st.error(f"予測比較グラフ '{title}' 作成中にエラー: {e}")
        return None
# --- 追加ここまで ---