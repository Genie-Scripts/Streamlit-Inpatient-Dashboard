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

# global_chart_cache = {} # <--- この行を削除します

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
        if '日付' in data.columns and '入院患者数（在院）' in data.columns:
            sample = data.head(10)
            # データの内容が少しでも変わればハッシュが変わるように、より多くの情報を含めるか、
            # pandasの to_msgpack や to_pickle のバイト列表現のハッシュを取る方が堅牢
            hash_str = pd.util.hash_pandas_object(sample, index=True).to_string()
            return hashlib.md5(hash_str.encode()).hexdigest()[:16] # ハッシュ長を少し長く
        else:
            # 列名や形状だけでもハッシュに含める
            hash_str = str(data.shape) + str(list(data.columns))
            return hashlib.md5(hash_str.encode()).hexdigest()[:16]
    except Exception as e:
        print(f"Data hashing error: {e}")
        return "error_hash_" + str(time.time()) # エラー時はユニークな値を返す

def get_chart_cache_key(title, days, target_value=None, chart_type="default", data_hash=None): # 既存の関数
    """キャッシュキーを生成する"""
    components = [str(title), str(days)]
    if target_value is not None:
        try:
            # 浮動小数点数の比較問題を避けるため、一定の精度で丸める
            components.append(f"{float(target_value):.2f}")
        except (ValueError, TypeError):
            components.append(str(target_value))
    else:
        components.append("None")
    components.append(str(chart_type))
    if data_hash:
        components.append(data_hash)
    # キーが長くなりすぎないように、全体のハッシュを取ることも検討
    key_string = "_".join(components)
    return hashlib.md5(key_string.encode()).hexdigest()


@st.cache_data(ttl=1800, show_spinner=False) # MatplotlibのFigureオブジェクト自体はst.cache_dataでキャッシュすべきではないが、BytesIOはOK
def create_patient_chart(data, title="入院患者数推移", days=90, show_moving_average=True, font_name_for_mpl=None):
    """データから患者数推移グラフを作成する（キャッシュ対応版）- Matplotlib PDF用"""
    start_time = time.time()
    
    chart_cache_instance = get_chart_cache() # セッション状態のキャッシュを取得

    # データハッシュの計算 (より堅牢なハッシュ生成を推奨)
    data_hash = get_data_hash(data)
    cache_key = get_chart_cache_key(title, days, None, "patient_chart_mpl", data_hash) # キーにmplを追加して区別
    
    # キャッシュから取得を試みる
    cached_chart_bytes = chart_cache_instance.get(cache_key) 
    if cached_chart_bytes is not None:
        print(f"キャッシュヒット(st.session_state): {title} ({days}日)")
        # キャッシュされたバイト列からBytesIOオブジェクトを再生成
        buf = BytesIO(cached_chart_bytes)
        buf.seek(0)
        return buf
    
    fig = None # エラー時に close するために先に定義
    try:
        fig, ax = plt.subplots(figsize=(10, 5.5))

        if not isinstance(data, pd.DataFrame) or data.empty:
            if fig: plt.close(fig)
            return None
            
        if "日付" not in data.columns or "入院患者数（在院）" not in data.columns:
            if fig: plt.close(fig)
            return None

        # データ集計の最適化
        # '日付'列が datetime 型であることを確認
        if not pd.api.types.is_datetime64_any_dtype(data['日付']):
            data = data.copy() # SettingWithCopyWarning を避ける
            data['日付'] = pd.to_datetime(data['日付'], errors='coerce')
            data.dropna(subset=['日付'], inplace=True)


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
        if font_name_for_mpl: # pdf_generator.py から渡される MATPLOTLIB_FONT_NAME を使用
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
        # plt.close(fig) # fig オブジェクトはここで閉じる
        buf.seek(0)
        
        # キャッシュにバイト列を保存
        chart_cache_instance[cache_key] = buf.getvalue() # get_chart_cache() を使用して保存
        
        end_time = time.time()
        print(f"グラフ生成完了 (st.session_stateキャッシュ): {title} ({days}日)、処理時間: {end_time - start_time:.2f}秒")
        
        buf.seek(0) # 呼び出し元で再度使えるように
        return buf
    except Exception as e:
        print(f"グラフ生成エラー '{title}': {e}")
        # if fig: plt.close(fig) # tryブロックの先頭でfigをNone初期化しているので、ここでエラーになっても大丈夫
        gc.collect() # エラー時にもGCを試みる
        return None
    finally:
        if fig: # tryブロック内でエラーが発生した場合でもfigがNoneでない可能性があるため
            plt.close(fig)

def create_interactive_patient_chart(data, title="入院患者数推移", days=90, show_moving_average=True, target_value=None, chart_type="全日"):
    """
    インタラクティブな患者数推移グラフを作成する (Plotly)
    """
    try:
        if not isinstance(data, pd.DataFrame) or data.empty:
            return None
        if "日付" not in data.columns or "入院患者数（在院）" not in data.columns:
            return None

        # '日付'列が datetime 型であることを確認
        if not pd.api.types.is_datetime64_any_dtype(data['日付']):
            data = data.copy()
            data['日付'] = pd.to_datetime(data['日付'], errors='coerce')
            data.dropna(subset=['日付'], inplace=True)

        grouped = data.groupby("日付")["入院患者数（在院）"].sum().reset_index().sort_values("日付")
        if len(grouped) > days: grouped = grouped.tail(days)
        if grouped.empty: return None

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
        # st.error(f"インタラクティブグラフ '{title}' 作成中にエラー: {e}") # UI要素なので呼び出し元で制御
        print(f"Error in create_interactive_patient_chart ('{title}'): {e}")
        return None

def create_interactive_dual_axis_chart(data, title="入院患者数と患者移動の推移", days=90):
    """
    インタラクティブな入院患者数と患者移動の7日移動平均グラフを二軸で作成する (Plotly)
    """
    try:
        if not isinstance(data, pd.DataFrame) or data.empty:
            return None
        required_columns = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "退院患者数"]
        if any(col not in data.columns for col in required_columns):
            return None
        
        # '日付'列が datetime 型であることを確認
        if not pd.api.types.is_datetime64_any_dtype(data['日付']):
            data = data.copy()
            data['日付'] = pd.to_datetime(data['日付'], errors='coerce')
            data.dropna(subset=['日付'], inplace=True)

        grouped = data.groupby("日付").agg({"入院患者数（在院）": "sum", "新入院患者数": "sum", "緊急入院患者数": "sum", "退院患者数": "sum"}).reset_index().sort_values("日付")
        if len(grouped) > days: grouped = grouped.tail(days)
        if grouped.empty: return None

        for col in required_columns[1:]: grouped[f'{col}_7日移動平均'] = grouped[col].rolling(window=7, min_periods=1).mean()

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped["入院患者数（在院）_7日移動平均"], name="入院患者数（在院）", line=dict(color="#3498db", width=3), mode="lines"), secondary_y=False)

        colors_map = {"新入院患者数": "#2ecc71", "緊急入院患者数": "#e74c3c", "退院患者数": "#f39c12"}
        for col, color_val in colors_map.items():
            if f"{col}_7日移動平均" in grouped.columns: # 列が存在するか確認
                fig.add_trace(go.Scatter(x=grouped["日付"], y=grouped[f"{col}_7日移動平均"], name=col, line=dict(color=color_val, width=2), mode="lines"), secondary_y=True)

        fig.update_layout(title=title, xaxis_title="日付", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5), hovermode="x unified", font=dict(family="Arial, 'Noto Sans JP', sans-serif", size=12), height=500)
        fig.update_yaxes(title_text="入院患者数（在院）", secondary_y=False)
        fig.update_yaxes(title_text="患者移動数", secondary_y=True)
        fig.update_xaxes(tickformat="%Y-%m-%d", tickangle=-45, tickmode='auto', nticks=10)
        return fig
    except Exception as e:
        # st.error(f"インタラクティブ2軸グラフ '{title}' 作成中にエラー: {e}") # UI要素なので呼び出し元で制御
        print(f"Error in create_interactive_dual_axis_chart ('{title}'): {e}")
        return None

# @st.cache_data(ttl=1800) # この関数もMatplotlibを使っているので、同様にst.session_stateキャッシュを検討可能
@st.cache_data(ttl=1800, show_spinner=False)
def create_dual_axis_chart(data, title="入院患者数と患者移動の推移", filename=None, days=90, font_name_for_mpl=None):
    """
    入院患者数と患者移動の7日移動平均グラフを二軸で作成する（Matplotlib版、PDF用）
    st.session_state を使ったキャッシュに対応
    """
    start_time = time.time()

    chart_cache_instance = get_chart_cache()

    data_hash = get_data_hash(data)
    cache_key = get_chart_cache_key(title, days, None, "dual_axis_mpl", data_hash)

    cached_chart_bytes = chart_cache_instance.get(cache_key)
    if cached_chart_bytes is not None:
        print(f"キャッシュヒット(st.session_state): {title} ({days}日, 二軸)")
        buf = BytesIO(cached_chart_bytes)
        buf.seek(0)
        return buf

    fig = None
    try:
        fig, ax1 = plt.subplots(figsize=(10, 5.5))

        if not isinstance(data, pd.DataFrame) or data.empty:
            # fig が初期化されていない可能性があるので、ここでは plt.close(fig) は呼び出さない
            return None

        required_columns = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "退院患者数"]
        if any(col not in data.columns for col in required_columns):
            # fig が初期化されていない可能性
            return None

        data_copy = data.copy() # 元のデータを変更しないようにコピー
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)

        grouped = data_copy.groupby("日付").agg({
            "入院患者数（在院）": "sum",
            "新入院患者数": "sum",
            "緊急入院患者数": "sum",
            "退院患者数": "sum"
        }).reset_index().sort_values("日付")

        if len(grouped) > days:
            grouped = grouped.tail(days)
        if grouped.empty:
            # fig が初期化されていない可能性
            return None

        cols_for_ma = ["入院患者数（在院）", "新入院患者数", "緊急入院患者数", "退院患者数"]
        for col in cols_for_ma:
            if col in grouped.columns: # grouped に列が存在するか確認
                grouped[f'{col}_7日移動平均'] = grouped[col].rolling(window=7, min_periods=1).mean()
            else:
                # 警告を出すか、デフォルト値（例: 0）で列を作成
                print(f"Warning: Column '{col}' not found in grouped data for moving average calculation in '{title}'. Skipping MA for this column.")
                grouped[f'{col}_7日移動平均'] = 0 # または pd.NA など

        font_kwargs = {}
        if font_name_for_mpl:
            font_kwargs['fontname'] = font_name_for_mpl

        # '入院患者数（在院）_7日移動平均' が存在するか確認してからプロット
        if "入院患者数（在院）_7日移動平均" in grouped.columns:
            ax1.plot(grouped["日付"], grouped["入院患者数（在院）_7日移動平均"], color='#3498db', linewidth=2, label="入院患者数（在院）")
        else:
            print(f"Warning: '入院患者数（在院）_7日移動平均' not found for plotting in '{title}'.")

        ax1.set_xlabel('日付', fontsize=9, **font_kwargs)
        ax1.set_ylabel('入院患者数（在院）', fontsize=9, color='#3498db', **font_kwargs)
        ax1.tick_params(axis='y', labelcolor='#3498db', labelsize=8)
        ax1.tick_params(axis='x', labelsize=8)

        ax2 = ax1.twinx()
        colors_map = {"新入院患者数": "#2ecc71", "緊急入院患者数": "#e74c3c", "退院患者数": "#f39c12"}
        for col, color_val in colors_map.items():
            ma_col_name = f"{col}_7日移動平均"
            if ma_col_name in grouped.columns: # 移動平均列が存在するか確認
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
        # plt.close(fig) # finally ブロックで閉じる
        buf.seek(0)

        chart_cache_instance[cache_key] = buf.getvalue()
        
        end_time = time.time()
        print(f"二軸グラフ生成完了 (st.session_stateキャッシュ): {title} ({days}日)、処理時間: {end_time - start_time:.2f}秒")

        buf.seek(0)
        return buf

    except Exception as e:
        print(f"Error in create_dual_axis_chart ('{title}'): {e}")
        import traceback
        print(traceback.format_exc())
        return None
    finally:
        if fig: # figがNoneでない（plt.subplotsが成功した）場合のみ閉じる
            plt.close(fig)
        gc.collect()

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
            # st.warning("実績データが空のため、予測比較グラフを作成できません。") # UI要素なので呼び出し元で制御
            print("実績データが空のため、予測比較グラフを作成できません。")
            return None

        fig = go.Figure()

        if not actual_series.index.is_monotonic_increasing:
             actual_series = actual_series.sort_index()
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

            if not actual_series.empty:
                 forecast_display_start_date = actual_series.index.max() + pd.Timedelta(days=1)
            else:
                 forecast_display_start_date = forecast_series.index.min()

            forecast_display_end_date = forecast_display_start_date + pd.Timedelta(days=display_days_future -1)
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
        # st.error(f"予測比較グラフ '{title}' 作成中にエラー: {e}") # UI要素なので呼び出し元で制御
        print(f"Error in create_forecast_comparison_chart ('{title}'): {e}")
        return None