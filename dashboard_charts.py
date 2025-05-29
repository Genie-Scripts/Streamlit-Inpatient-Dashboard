import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st

@st.cache_data(ttl=3600, show_spinner=False)
def create_monthly_trend_chart(kpi_data):
    """
    月別の平均在院日数と入退院患者数の推移チャートを作成
    
    Parameters:
    -----------
    kpi_data : dict
        KPI計算結果を含む辞書
        
    Returns:
    --------
    plotly.graph_objects.Figure
        プロットされたグラフ
    """
    if kpi_data is None or 'monthly_stats' not in kpi_data or kpi_data['monthly_stats'].empty:
        return None
    
    monthly_data = kpi_data['monthly_stats']
    
    # 二軸グラフの作成
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 平均在院日数（左軸）
    fig.add_trace(
        go.Scatter(
            x=monthly_data['月'], 
            y=monthly_data['平均在院日数'], 
            name='平均在院日数',
            line=dict(color='#3498db', width=3), 
            marker=dict(symbol="circle", size=7)
        ),
        secondary_y=False
    )
    
    # 入院患者数と退院患者数（右軸）
    fig.add_trace(
        go.Bar(
            x=monthly_data['月'], 
            y=monthly_data['総入院患者数'], 
            name='総入院患者数', 
            marker_color='#2ecc71', 
            opacity=0.8
        ),
        secondary_y=True
    )
    
    fig.add_trace(
        go.Bar(
            x=monthly_data['月'], 
            y=monthly_data['総退院患者数'], 
            name='総退院患者数', 
            marker_color='#e74c3c', 
            opacity=0.8
        ),
        secondary_y=True
    )
    
    # レイアウト設定（タイトルを削除）
    fig.update_layout(
        font=dict(size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=20, b=20),  # 上部マージンを減らす
        height=400,
        barmode='group',
        hovermode="x unified"
    )
    
    # 軸の設定
    fig.update_xaxes(title="月", tickangle=-45, showgrid=True, gridwidth=1, gridcolor='LightGray')
    fig.update_yaxes(
        title_text="平均在院日数 (日)", 
        secondary_y=False, 
        showgrid=True, 
        gridwidth=1, 
        gridcolor='LightGray', 
        color='#3498db'
    )
    fig.update_yaxes(
        title_text="患者数 (人)", 
        secondary_y=True, 
        showgrid=False, 
        color='#2471A3'
    )
    
    return fig

@st.cache_data(ttl=3600, show_spinner=False)
def create_admissions_discharges_chart(kpi_data):
    """
    週別の入退院バランスチャートを作成
    
    Parameters:
    -----------
    kpi_data : dict
        KPI計算結果を含む辞書
        
    Returns:
    --------
    plotly.graph_objects.Figure
        プロットされたグラフ
    """
    if kpi_data is None or 'weekly_stats' not in kpi_data or kpi_data['weekly_stats'].empty:
        return None
    
    weekly_data = kpi_data['weekly_stats']
    
    # グラフの作成
    fig = go.Figure()
    
    # 入院患者数
    fig.add_trace(
        go.Bar(
            x=weekly_data['週'], 
            y=weekly_data['週入院患者数'], 
            name='入院患者数', 
            marker_color='#3498db', 
            opacity=0.8
        )
    )
    
    # 退院患者数
    fig.add_trace(
        go.Bar(
            x=weekly_data['週'], 
            y=weekly_data['週退院患者数'], 
            name='退院患者数', 
            marker_color='#e74c3c', 
            opacity=0.8
        )
    )
    
    # 入退院差
    fig.add_trace(
        go.Scatter(
            x=weekly_data['週'], 
            y=weekly_data['入退院差'], 
            name='入退院差 (入院 - 退院)',
            line=dict(color='#f39c12', width=2.5, dash='solid'), 
            mode='lines+markers', 
            marker=dict(symbol="diamond", size=7)
        )
    )
    
    # レイアウト設定（タイトルを削除）
    fig.update_layout(
        font=dict(size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=20, b=20),  # 上部マージンを減らす
        height=400,
        barmode='group',
        hovermode="x unified"
    )
    
    # 軸の設定
    fig.update_xaxes(title="週", tickangle=-45, showgrid=True, gridwidth=1, gridcolor='LightGray')
    fig.update_yaxes(title_text="患者数 (人)", showgrid=True, gridwidth=1, gridcolor='LightGray')
    
    return fig

@st.cache_data(ttl=3600, show_spinner=False)
def create_occupancy_chart(kpi_data, total_beds, target_occupancy_rate_percent):
    """
    月別の病床利用率チャートを作成
    
    Parameters:
    -----------
    kpi_data : dict
        KPI計算結果を含む辞書
    total_beds : int
        総病床数
    target_occupancy_rate_percent : float
        目標病床利用率（%）
        
    Returns:
    --------
    plotly.graph_objects.Figure
        プロットされたグラフ
    """
    if kpi_data is None or 'monthly_stats' not in kpi_data or kpi_data['monthly_stats'].empty or total_beds == 0:
        return None
    
    monthly_df = kpi_data['monthly_stats'].copy()
    
    # 病床利用率の計算
    monthly_df['病床利用率'] = (monthly_df['日平均在院患者数'] / total_beds) * 100
    
    # グラフの作成
    fig = go.Figure()
    
    # 病床利用率
    fig.add_trace(
        go.Scatter(
            x=monthly_df['月'], 
            y=monthly_df['病床利用率'], 
            mode='lines+markers', 
            name='病床利用率 (%)',
            line=dict(color='#2196f3', width=3), 
            marker=dict(symbol="triangle-up", size=8, color='#2196f3')
        )
    )
    
    # 目標利用率
    fig.add_trace(
        go.Scatter(
            x=monthly_df['月'],
            y=[target_occupancy_rate_percent] * len(monthly_df), 
            mode='lines', 
            name=f'目標利用率 ({target_occupancy_rate_percent}%)',
            line=dict(color='#4caf50', width=2, dash='dash')
        )
    )
    
    # 領域の塗りつぶし（90%以上の領域を強調）
    if target_occupancy_rate_percent > 0:
        # X軸の範囲
        x_range = [monthly_df['月'].iloc[0], monthly_df['月'].iloc[-1]] if not monthly_df.empty else []
        
        if x_range: # X軸の範囲が有効な場合のみ塗りつぶしを実行
            lower_bound = max(0, target_occupancy_rate_percent - 5)
            upper_bound = min(100, target_occupancy_rate_percent + 5)
            
            fig.add_trace(
                go.Scatter(
                    x=x_range + x_range[::-1],
                    y=[lower_bound, lower_bound, upper_bound, upper_bound],
                    fill='toself',
                    fillcolor='rgba(76, 175, 80, 0.1)',
                    line=dict(color='rgba(0,0,0,0)'),
                    name='適正範囲',
                    hoverinfo='skip'
                )
            )
            
            if upper_bound < 90:
                fig.add_trace(
                    go.Scatter(
                        x=x_range + x_range[::-1],
                        y=[90, 90, 100, 100],
                        fill='toself',
                        fillcolor='rgba(255, 87, 34, 0.1)',
                        line=dict(color='rgba(0,0,0,0)'),
                        name='高利用率警告',
                        hoverinfo='skip'
                    )
                )
    
    # レイアウト設定（タイトルを削除）
    fig.update_layout(
        font=dict(size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=20, b=20),  # 上部マージンを減らす
        height=400,
        hovermode="x unified"
    )
    
    # --- Y軸範囲の動的調整 ---
    if monthly_df.empty or '病床利用率' not in monthly_df.columns or monthly_df['病床利用率'].dropna().empty:
        y_start_final = 0.0
        y_end_final = 100.0
    else:
        occupancy_data = monthly_df['病床利用率'].dropna()
        min_val = occupancy_data.min()
        max_val = occupancy_data.max()

        if min_val == max_val: # データがフラットな場合
            y_start_final = max(0.0, min_val - 10.0)
            y_end_final = min(100.0, max_val + 10.0)
            # 値が0または100でフラットな場合の特別な処理
            if min_val == 0.0 and y_end_final <= 10.0 : y_end_final = 20.0 
            elif min_val == 100.0 and y_start_final >= 90.0 : y_start_final = 80.0
            # 上記条件の後でstart >= end になってしまった場合の最終調整
            if y_start_final >= y_end_final:
                 y_start_final = max(0.0, min_val - 10.0) # 再度計算
                 y_end_final = min(100.0, min_val + 10.0) # max_valもmin_valと同じ
                 if y_start_final >= y_end_final: # これでもダメならデフォルト
                      y_start_final = 0.0; y_end_final = 100.0

        else: # データに変動がある場合
            data_span = max_val - min_val
            padding = data_span * 0.15  # データ範囲の15%をパディング
            padding = max(padding, 5.0) # ただし最低でも5パーセントポイントのパディング

            y_start_final = min_val - padding
            y_end_final = max_val + padding
            
            # 0%～100%の範囲にクランプ
            y_start_final = max(0.0, y_start_final)
            y_end_final = min(100.0, y_end_final)

            # 表示範囲が狭すぎる場合（例：10ポイント未満）の調整
            if (y_end_final - y_start_final < 10.0) and data_span > 0 : # data_span > 0 を追加
                center = (min_val + max_val) / 2.0 # 元データの中心
                y_start_final = center - 5.0
                y_end_final = center + 5.0
                
                # 再度0%～100%の範囲にクランプ
                y_start_final = max(0.0, y_start_final)
                y_end_final = min(100.0, y_end_final)

                # それでも範囲が不適切なら最終手段
                if y_start_final >= y_end_final or (y_end_final - y_start_final < 1.0 and data_span > 0) : 
                    y_start_final = max(0.0, min_val - 5.0) # より小さいパディングで試す
                    y_end_final = min(100.0, max_val + 5.0)
                    if y_start_final >= y_end_final: # 絶対的なフォールバック
                         y_start_final = 0.0
                         y_end_final = 100.0
    
    # 軸の設定
    fig.update_xaxes(title="月", showgrid=True, gridcolor='#f0f0f0', tickangle=-45)
    fig.update_yaxes(
        title_text="病床利用率 (%)", 
        showgrid=True, 
        gridcolor='#f0f0f0', 
        range=[y_start_final, y_end_final]
    )
    
    return fig