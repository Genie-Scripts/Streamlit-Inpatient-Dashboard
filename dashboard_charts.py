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
    月別の病床利用率チャートを作成（縦軸範囲を適切に調整）
    
    Parameters:
    -----------
    kmp_data : dict
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
    
    # 縦軸範囲の動的計算
    if not monthly_df['病床利用率'].empty:
        min_rate = monthly_df['病床利用率'].min()
        max_rate = monthly_df['病床利用率'].max()
        
        # データ範囲に基づいて適切な表示範囲を設定
        data_range = max_rate - min_rate
        margin = max(data_range * 0.15, 5)  # 最低5%のマージンを確保
        
        # 表示範囲の計算
        y_min = max(0, min_rate - margin)
        y_max = min(100, max_rate + margin)
        
        # 目標値も考慮して範囲を調整
        if target_occupancy_rate_percent > 0:
            y_min = min(y_min, target_occupancy_rate_percent - 10)
            y_max = max(y_max, target_occupancy_rate_percent + 10)
        
        # 最終的な範囲調整（0-100%の範囲内）
        y_min = max(0, y_min)
        y_max = min(100, y_max)
        
        # 範囲が狭すぎる場合の調整
        if y_max - y_min < 15:
            center = (y_max + y_min) / 2
            y_min = max(0, center - 10)
            y_max = min(100, center + 10)
    else:
        # データがない場合のデフォルト範囲
        y_min, y_max = 60, 100
    
    # グラフの作成
    fig = go.Figure()
    
    # 適正範囲の塗りつぶし（目標値±5%）
    if target_occupancy_rate_percent > 0:
        lower_bound = max(y_min, target_occupancy_rate_percent - 5)
        upper_bound = min(y_max, target_occupancy_rate_percent + 5)
        
        # X軸の範囲
        x_range = [monthly_df['月'].iloc[0], monthly_df['月'].iloc[-1]]
        
        # 適正範囲
        fig.add_trace(
            go.Scatter(
                x=x_range + x_range[::-1],
                y=[lower_bound, lower_bound, upper_bound, upper_bound],
                fill='toself',
                fillcolor='rgba(76, 175, 80, 0.15)',
                line=dict(color='rgba(0,0,0,0)'),
                name='適正範囲 (目標±5%)',
                hoverinfo='skip',
                showlegend=True
            )
        )
        
        # 高利用率警告範囲（90%以上が表示範囲内にある場合）
        if y_max >= 90 and upper_bound < 90:
            fig.add_trace(
                go.Scatter(
                    x=x_range + x_range[::-1],
                    y=[90, 90, min(100, y_max), min(100, y_max)],
                    fill='toself',
                    fillcolor='rgba(255, 152, 0, 0.15)',
                    line=dict(color='rgba(0,0,0,0)'),
                    name='注意範囲 (90%以上)',
                    hoverinfo='skip',
                    showlegend=True
                )
            )
    
    # 目標利用率の線
    if target_occupancy_rate_percent > 0:
        fig.add_trace(
            go.Scatter(
                x=monthly_df['月'],
                y=[target_occupancy_rate_percent] * len(monthly_df), 
                mode='lines', 
                name=f'目標利用率 ({target_occupancy_rate_percent}%)',
                line=dict(color='#4caf50', width=2, dash='dash'),
                hovertemplate=f'目標利用率: {target_occupancy_rate_percent}%<extra></extra>'
            )
        )
    
    # 実際の病床利用率
    fig.add_trace(
        go.Scatter(
            x=monthly_df['月'], 
            y=monthly_df['病床利用率'], 
            mode='lines+markers', 
            name='実際の利用率',
            line=dict(color='#2196f3', width=3), 
            marker=dict(symbol="circle", size=8, color='#2196f3'),
            hovertemplate='%{x}<br>病床利用率: %{y:.1f}%<br>在院患者数: %{customdata:.0f}人<extra></extra>',
            customdata=monthly_df['日平均在院患者数']
        )
    )
    
    # レイアウト設定
    fig.update_layout(
        font=dict(size=12),
        legend=dict(
            orientation="h", 
            yanchor="bottom", 
            y=1.02, 
            xanchor="right", 
            x=1, 
            font=dict(size=11)
        ),
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=20, b=20),
        height=400,
        hovermode="x unified"
    )
    
    # 軸の設定
    fig.update_xaxes(
        title="月", 
        showgrid=True, 
        gridcolor='#f0f0f0', 
        tickangle=-45
    )
    fig.update_yaxes(
        title="病床利用率 (%)", 
        showgrid=True, 
        gridcolor='#f0f0f0',
        range=[y_min, y_max],  # 動的に計算された範囲を使用
        tickformat='.1f'
    )
    
    # Y軸に主要な目盛り線を追加（10%刻み）
    tick_vals = []
    tick_start = int(y_min // 10) * 10
    tick_end = int(y_max // 10 + 1) * 10
    for i in range(tick_start, tick_end + 1, 10):
        if y_min <= i <= y_max:
            tick_vals.append(i)
    
    fig.update_yaxes(
        tickvals=tick_vals,
        ticktext=[f'{val}%' for val in tick_vals]
    )
    
    return fig