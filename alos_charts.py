import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import streamlit as st

@st.cache_data(ttl=3600, show_spinner=False)
def create_alos_volume_chart(df, selected_granularity, selected_unit, target_items, start_date, end_date, moving_avg_window=30):
    """
    平均在院日数と日平均在院患者数の推移を表示するグラフを作成する
    
    Parameters:
    -----------
    df : pd.DataFrame
        分析対象のデータフレーム
    selected_granularity : str
        '日単位', '週単位', '月単位'のいずれか
    selected_unit : str
        '病院全体', '病棟別', '診療科別'のいずれか
    target_items : list
        選択された病棟コードまたは診療科名のリスト（selected_unitが'病院全体'以外の場合）
    start_date : datetime-like
        分析開始日
    end_date : datetime-like
        分析終了日
    moving_avg_window : int, default 30
        移動平均のウィンドウサイズ（日数/週数/月数）
        
    Returns:
    --------
    tuple
        (plotly.graph_objects.Figure, pd.DataFrame)
        グラフオブジェクトと集計データを含むDataFrame
    """
    # 日付変換と期間フィルタリング
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    
    # 期間の長さを計算
    period_days = (end_date - start_date).days + 1
    
    # 「直近30日」方式の場合、データ取得期間を移動平均計算のために拡張
    if selected_granularity == '日単位(直近30日)':
        extended_start_date = start_date - pd.Timedelta(days=moving_avg_window-1)
        df_filtered = df[(df['日付'] >= extended_start_date) & (df['日付'] <= end_date)].copy()
        window_suffix = f"直近{moving_avg_window}日"
    else:
        df_filtered = df[(df['日付'] >= start_date) & (df['日付'] <= end_date)].copy()
    
    if df_filtered.empty:
        return None, None
    
    # 集計期間の設定
    if selected_granularity == '月単位':
        df_filtered['集計期間'] = df_filtered['日付'].dt.to_period('M').astype(str)
        ma_suffix = f"{moving_avg_window}ヶ月移動平均"
    elif selected_granularity == '週単位':
        df_filtered['集計期間'] = df_filtered['日付'].dt.to_period('W').astype(str)
        ma_suffix = f"{moving_avg_window}週移動平均"
    elif selected_granularity == '日単位(直近30日)':
        # 日付そのものをそのまま使用
        df_filtered['集計期間'] = df_filtered['日付']
        ma_suffix = window_suffix
    else:  # 通常の日単位
        df_filtered['集計期間'] = df_filtered['日付'].dt.strftime('%Y-%m-%d')
        ma_suffix = f"{moving_avg_window}日移動平均"
    
    # 集計単位ごとの処理
    results_df_list = []
    
    # 直近30日方式の特別処理
    if selected_granularity == '日単位(直近30日)':
        # 連続した日付を生成
        all_dates = pd.date_range(start=start_date, end=end_date)
        
        if selected_unit == '病院全体':
            # 病院全体の直近30日移動集計
            daily_metrics = []
            
            for current_date in all_dates:
                # current_dateを含む直近30日分のデータを抽出
                window_start = current_date - pd.Timedelta(days=moving_avg_window-1)
                window_data = df_filtered[(df_filtered['日付'] >= window_start) & (df_filtered['日付'] <= current_date)]
                
                if not window_data.empty:
                    # 指定期間の合計値
                    total_patient_days = window_data['入院患者数（在院）'].sum()
                    total_admissions = window_data['総入院患者数'].sum()
                    total_discharges = window_data['総退院患者数'].sum()
                    days_in_window = window_data['日付'].nunique()
                    
                    # 平均在院日数の計算
                    denominator = (total_admissions + total_discharges) / 2
                    alos = total_patient_days / denominator if denominator > 0 else 0
                    daily_census = total_patient_days / days_in_window if days_in_window > 0 else 0
                    
                    daily_metrics.append({
                        '集計期間': current_date,
                        '集計単位名': '病院全体',
                        '延べ在院患者数': total_patient_days,
                        '総入院患者数': total_admissions,
                        '総退院患者数': total_discharges,
                        '実日数': days_in_window,
                        '平均在院日数_実測': alos,
                        '日平均在院患者数': daily_census
                    })
            
            if daily_metrics:
                results_df_list.append(pd.DataFrame(daily_metrics))
                
        elif selected_unit in ['病棟別', '診療科別'] and target_items:
            column_to_group_on = '病棟コード' if selected_unit == '病棟別' else '診療科名'
            
            for item in target_items:
                item_data = df_filtered[df_filtered[column_to_group_on].astype(str) == str(item)]
                
                if not item_data.empty:
                    daily_metrics = []
                    
                    for current_date in all_dates:
                        # current_dateを含む直近30日分のデータを抽出
                        window_start = current_date - pd.Timedelta(days=moving_avg_window-1)
                        window_data = item_data[(item_data['日付'] >= window_start) & (item_data['日付'] <= current_date)]
                        
                        if not window_data.empty:
                            # 指定期間の合計値
                            total_patient_days = window_data['入院患者数（在院）'].sum()
                            total_admissions = window_data['総入院患者数'].sum()
                            total_discharges = window_data['総退院患者数'].sum()
                            days_in_window = window_data['日付'].nunique()
                            
                            # 平均在院日数の計算
                            denominator = (total_admissions + total_discharges) / 2
                            alos = total_patient_days / denominator if denominator > 0 else 0
                            daily_census = total_patient_days / days_in_window if days_in_window > 0 else 0
                            
                            daily_metrics.append({
                                '集計期間': current_date,
                                '集計単位名': str(item),
                                '延べ在院患者数': total_patient_days,
                                '総入院患者数': total_admissions,
                                '総退院患者数': total_discharges,
                                '実日数': days_in_window,
                                '平均在院日数_実測': alos,
                                '日平均在院患者数': daily_census
                            })
                    
                    if daily_metrics:
                        results_df_list.append(pd.DataFrame(daily_metrics))
    
    else:
        # 通常の集計処理（月単位/週単位/日単位）
        group_by_columns = ['集計期間']
        
        if selected_unit == '病院全体':
            # 病院全体の集計
            grouped = df_filtered.groupby(group_by_columns).agg(
                延べ在院患者数=('入院患者数（在院）', 'sum'),
                総入院患者数=('総入院患者数', 'sum'),
                総退院患者数=('総退院患者数', 'sum'),
                実日数=('日付', 'nunique')
            ).reset_index()
            grouped['集計単位名'] = '病院全体'
            results_df_list.append(grouped)
        elif selected_unit in ['病棟別', '診療科別'] and target_items:
            # 病棟別または診療科別の集計
            column_to_group_on = '病棟コード' if selected_unit == '病棟別' else '診療科名'
            for item in target_items:
                df_item_filtered = df_filtered[df_filtered[column_to_group_on].astype(str) == str(item)]
                if not df_item_filtered.empty:
                    grouped = df_item_filtered.groupby(group_by_columns).agg(
                        延べ在院患者数=('入院患者数（在院）', 'sum'),
                        総入院患者数=('総入院患者数', 'sum'),
                        総退院患者数=('総退院患者数', 'sum'),
                        実日数=('日付', 'nunique')
                    ).reset_index()
                    grouped['集計単位名'] = str(item)
                    results_df_list.append(grouped)
    
    if not results_df_list:
        return None, None
    
    # 結果の結合と集計
    final_df = pd.concat(results_df_list)
    
    # 直近30日方式では、既に平均在院日数_実測が計算済み
    if selected_granularity != '日単位(直近30日)':
        # 平均在院日数と日平均在院患者数の計算
        final_df['平均在院日数_実測'] = final_df.apply(
            lambda row: row['延べ在院患者数'] / ((row['総入院患者数'] + row['総退院患者数']) / 2)
            if (row['総入院患者数'] + row['総退院患者数']) > 0 else 0,
            axis=1
        )
        final_df['日平均在院患者数'] = final_df.apply(
            lambda row: row['延べ在院患者数'] / row['実日数'] if row['実日数'] > 0 else 0,
            axis=1
        )
    
    # ソート
    if selected_granularity == '日単位(直近30日)':
        final_df.sort_values(by=['集計単位名', '集計期間'], inplace=True)
    else:
        # 通常の集計方式では、期間文字列を適切にソートする必要がある
        final_df.sort_values(by=['集計単位名', '集計期間'], inplace=True)
    
    # 直近30日方式ではすでに平均計算済み
    if selected_granularity != '日単位(直近30日)':
        # 移動平均の計算
        ma_col_name = f'平均在院日数 ({ma_suffix})'
        final_df[ma_col_name] = final_df.groupby('集計単位名')['平均在院日数_実測']\
                                        .transform(lambda x: x.rolling(window=moving_avg_window, min_periods=1).mean())
    else:
        # 直近30日方式では、実測値と移動平均が同じ
        ma_col_name = f'平均在院日数 ({ma_suffix})'
        final_df[ma_col_name] = final_df['平均在院日数_実測']
    
    # グラフの作成
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    colors_ma_palette = px.colors.qualitative.Plotly
    colors_vol_palette = px.colors.qualitative.Bold
    
    # 各単位ごとにグラフを追加
    unique_units = final_df['集計単位名'].unique()
    
    # X軸の日付フォーマット設定
    x_tickformat = None
    hover_format = None
    
    if selected_granularity == '日単位(直近30日)':
        x_tickformat = '%Y-%m-%d'
        hover_format = '%Y-%m-%d'
    
    for i, unit_name in enumerate(unique_units):
        unit_df = final_df[final_df['集計単位名'] == unit_name]
        line_color_ma = colors_ma_palette[i % len(colors_ma_palette)]
        line_color_vol = colors_vol_palette[i % len(colors_vol_palette)]
        
        # 平均在院日数のグラフ（左軸）
        fig.add_trace(
            go.Scatter(
                x=unit_df['集計期間'], 
                y=unit_df[ma_col_name], 
                mode='lines+markers',
                name=f"{unit_name} - {ma_suffix}", 
                line=dict(color=line_color_ma, width=2.5), 
                marker=dict(size=7)  # マーカーサイズを大きく
            ),
            secondary_y=False,
        )
        
        # 日平均在院患者数のグラフ（右軸）
        fig.add_trace(
            go.Scatter(
                x=unit_df['集計期間'], 
                y=unit_df['日平均在院患者数'], 
                mode='lines',
                name=f"{unit_name} - 日平均在院患者数", 
                line=dict(color=line_color_vol, width=2, dash='dash')
            ),
            secondary_y=True,
        )

    # グラフのレイアウト設定（フォントサイズを大きく、タイトルを動的に変更）
    # タイトルに期間の情報を追加
    if period_days <= 90:
        period_text = f"直近{period_days}日間"
    elif period_days <= 180:
        period_text = "直近6ヶ月"
    elif period_days <= 365:
        period_text = "直近12ヶ月"
    else:
        period_text = f"{period_days}日間"
    
    fig.update_layout(
        title=f"平均在院日数と平均在院患者数の推移（{period_text}）",  # タイトルを動的に変更
        title_font=dict(size=18),  # タイトルのフォントサイズを大きく
        font=dict(size=14),  # 全体のフォントサイズを大きく
        legend=dict(
            orientation="h", 
            yanchor="bottom", 
            y=1.02, 
            xanchor="right", 
            x=1, 
            font=dict(size=14)  # 凡例のフォントサイズを大きく
        ),
        height=550, 
        hovermode="x unified", 
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=50, b=20),
    )
    
    # 軸の設定（フォントサイズを大きく）
    fig.update_xaxes(
        title_text="集計期間", 
        tickangle=-45, 
        showgrid=True, 
        gridwidth=1, 
        gridcolor='LightGray',
        title_font=dict(size=16),  # X軸タイトルのフォントサイズを大きく
        tickfont=dict(size=14)     # X軸目盛りのフォントサイズを大きく
    )
    fig.update_yaxes(
        title_text=f"平均在院日数 ({ma_suffix})", 
        secondary_y=False, 
        showgrid=True, 
        gridwidth=1, 
        gridcolor='LightGray', 
        color=colors_ma_palette[0],
        title_font=dict(size=16),  # Y軸タイトルのフォントサイズを大きく
        tickfont=dict(size=14)     # Y軸目盛りのフォントサイズを大きく
    )
    fig.update_yaxes(
        title_text="平均在院患者数 (人)",  # 文言を「日平均」から「平均」に変更
        secondary_y=True, 
        showgrid=False, 
        color=colors_vol_palette[0],
        title_font=dict(size=16),  # 二次Y軸タイトルのフォントサイズを大きく
        tickfont=dict(size=14)     # 二次Y軸目盛りのフォントサイズを大きく
    )
    
    return fig, final_df

@st.cache_data(ttl=3600, show_spinner=False)
def create_alos_benchmark_chart(df, selected_unit, target_items, start_date, end_date, benchmark_value=None):
    """
    平均在院日数のベンチマーク比較チャートを作成する
    
    Parameters:
    -----------
    df : pd.DataFrame
        分析対象のデータフレーム
    selected_unit : str
        '病院全体', '病棟別', '診療科別'のいずれか
    target_items : list
        選択された病棟コードまたは診療科名のリスト（selected_unitが'病院全体'以外の場合）
    start_date : datetime-like
        分析開始日
    end_date : datetime-like
        分析終了日
    benchmark_value : float or None, default None
        比較するベンチマーク値（平均在院日数の目標値など）
        
    Returns:
    --------
    plotly.graph_objects.Figure
        プロットされたグラフ
    """
    # 日付変換と期間フィルタリング
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    df_filtered = df[(df['日付'] >= start_date) & (df['日付'] <= end_date)].copy()
    
    if df_filtered.empty:
        return None
    
    # 集計単位ごとの処理
    results = []
    
    if selected_unit == '病院全体':
        # 病院全体の平均在院日数を計算
        total_patient_days = df_filtered['入院患者数（在院）'].sum()
        total_admissions = df_filtered['総入院患者数'].sum()
        total_discharges = df_filtered['総退院患者数'].sum()
        
        denominator = (total_admissions + total_discharges) / 2
        alos = total_patient_days / denominator if denominator > 0 else 0
        
        results.append({
            '集計単位名': '病院全体',
            '平均在院日数': alos,
            '延べ在院患者数': total_patient_days,
            '総入院患者数': total_admissions,
            '総退院患者数': total_discharges
        })
    elif selected_unit in ['病棟別', '診療科別'] and target_items:
        # 病棟別または診療科別の平均在院日数を計算
        column_to_group_on = '病棟コード' if selected_unit == '病棟別' else '診療科名'
        
        # 各項目ごとに集計
        for item in target_items:
            df_item = df_filtered[df_filtered[column_to_group_on].astype(str) == str(item)]
            
            if not df_item.empty:
                item_patient_days = df_item['入院患者数（在院）'].sum()
                item_admissions = df_item['総入院患者数'].sum()
                item_discharges = df_item['総退院患者数'].sum()
                
                item_denominator = (item_admissions + item_discharges) / 2
                item_alos = item_patient_days / item_denominator if item_denominator > 0 else 0
                
                results.append({
                    '集計単位名': str(item),
                    '平均在院日数': item_alos,
                    '延べ在院患者数': item_patient_days,
                    '総入院患者数': item_admissions,
                    '総退院患者数': item_discharges
                })
    
    if not results:
        return None
    
    # 結果をDataFrameに変換
    result_df = pd.DataFrame(results)
    result_df.sort_values(by='平均在院日数', ascending=True, inplace=True)
    
    # グラフの作成
    colors = px.colors.qualitative.Plotly
    
    fig = go.Figure()
    
    # 平均在院日数の横棒グラフ
    fig.add_trace(
        go.Bar(
            y=result_df['集計単位名'],
            x=result_df['平均在院日数'],
            orientation='h',
            marker_color=colors[0],
            name='平均在院日数',
            text=result_df['平均在院日数'].round(1).astype(str) + ' 日',
            textposition='outside',
            textfont=dict(size=16),  # テキストのフォントサイズを大きく
            hovertemplate='%{y}: %{x:.1f} 日<br>延べ在院患者数: %{customdata[0]:.0f}<br>総入院患者数: %{customdata[1]:.0f}<br>総退院患者数: %{customdata[2]:.0f}',
            customdata=result_df[['延べ在院患者数', '総入院患者数', '総退院患者数']].values
        )
    )
    
    # ベンチマークがある場合は追加
    if benchmark_value is not None and benchmark_value > 0:
        fig.add_vline(
            x=benchmark_value,
            line_dash="dash",
            line_color="red",
            annotation_text=f"目標: {benchmark_value:.1f} 日",
            annotation_position="top right",
            annotation_font=dict(size=16)  # ベンチマーク注釈のフォントサイズを大きく
        )
    
    # レイアウト設定
    fig.update_layout(
        title=f"{selected_unit}別 平均在院日数",
        xaxis_title="平均在院日数 (日)",
        yaxis_title=selected_unit.replace('別', ''),
        font=dict(size=16),  # 全体のフォントサイズを12から14に
        title_font=dict(size=16),  # タイトルのフォントサイズを大きく
        height=max(350, len(result_df) * 40 + 150),  # 項目数に応じて高さを調整
        margin=dict(l=20, r=20, t=50, b=20),
        plot_bgcolor='rgba(0,0,0,0)'
    )
    
    # 軸の設定
    fig.update_xaxes(
        title_font=dict(size=16),  # X軸タイトルのフォントサイズ
        tickfont=dict(size=14)     # X軸目盛りのフォントサイズ
    )
    fig.update_yaxes(
        title_font=dict(size=16),  # Y軸タイトルのフォントサイズ
        tickfont=dict(size=14)     # Y軸目盛りのフォントサイズ
    )
    
    return fig

@st.cache_data(ttl=3600, show_spinner=False)
def calculate_alos_metrics(df, start_date, end_date, group_by_column=None):
    """
    平均在院日数に関する詳細メトリクスを計算する
    
    Parameters:
    -----------
    df : pd.DataFrame
        分析対象のデータフレーム
    start_date : datetime-like
        分析開始日
    end_date : datetime-like
        分析終了日
    group_by_column : str or None, default None
        グループ化する列名（例: '診療科名', '病棟コード'）
        
    Returns:
    --------
    pd.DataFrame
        計算されたメトリクスを含むDataFrame
    """
    # 日付変換と期間フィルタリング
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    df_filtered = df[(df['日付'] >= start_date) & (df['日付'] <= end_date)].copy()
    
    if df_filtered.empty:
        return pd.DataFrame()
    
    # グループ化列の設定
    if group_by_column:
        # 指定された列でグループ化
        metrics_df = df_filtered.groupby(group_by_column).agg(
            延べ在院患者数=('入院患者数（在院）', 'sum'),
            総入院患者数=('総入院患者数', 'sum'),
            総退院患者数=('総退院患者数', 'sum'),
            緊急入院患者数=('緊急入院患者数', 'sum'),
            死亡患者数=('死亡患者数', 'sum'),
            データ日数=('日付', 'nunique')
        ).reset_index()
        metrics_df.rename(columns={group_by_column: '集計単位'}, inplace=True)
    else:
        # 病院全体の集計
        metrics = {
            '延べ在院患者数': df_filtered['入院患者数（在院）'].sum(),
            '総入院患者数': df_filtered['総入院患者数'].sum(),
            '総退院患者数': df_filtered['総退院患者数'].sum(),
            '緊急入院患者数': df_filtered['緊急入院患者数'].sum(),
            '死亡患者数': df_filtered['死亡患者数'].sum(),
            'データ日数': df_filtered['日付'].nunique()
        }
        metrics_df = pd.DataFrame([metrics])
        metrics_df['集計単位'] = '病院全体'
    
    # 各種メトリクスの計算
    metrics_df['平均在院日数'] = metrics_df.apply(
        lambda row: row['延べ在院患者数'] / ((row['総入院患者数'] + row['総退院患者数']) / 2)
        if (row['総入院患者数'] + row['総退院患者数']) > 0 else 0,
        axis=1
    )
    
    metrics_df['日平均在院患者数'] = metrics_df.apply(
        lambda row: row['延べ在院患者数'] / row['データ日数'] if row['データ日数'] > 0 else 0,
        axis=1
    )
    
    metrics_df['病床回転率'] = metrics_df.apply(
        lambda row: row['総退院患者数'] / row['日平均在院患者数'] if row['日平均在院患者数'] > 0 else 0,
        axis=1
    )
    
    metrics_df['緊急入院率'] = metrics_df.apply(
        lambda row: row['緊急入院患者数'] / row['総入院患者数'] * 100 if row['総入院患者数'] > 0 else 0,
        axis=1
    )
    
    metrics_df['死亡率'] = metrics_df.apply(
        lambda row: row['死亡患者数'] / row['総退院患者数'] * 100 if row['総退院患者数'] > 0 else 0,
        axis=1
    )
    
    # 各単位の割合計算（病院全体に対する比率）
    if group_by_column:
        total_patient_days = metrics_df['延べ在院患者数'].sum()
        total_admissions = metrics_df['総入院患者数'].sum()
        total_discharges = metrics_df['総退院患者数'].sum()
        
        # 割合の計算
        metrics_df['在院患者数割合'] = metrics_df['延べ在院患者数'] / total_patient_days * 100 if total_patient_days > 0 else 0
        metrics_df['入院患者数割合'] = metrics_df['総入院患者数'] / total_admissions * 100 if total_admissions > 0 else 0
        metrics_df['退院患者数割合'] = metrics_df['総退院患者数'] / total_discharges * 100 if total_discharges > 0 else 0
    
    # 列の順序を調整
    cols_order = ['集計単位', '平均在院日数', '日平均在院患者数', '病床回転率', '延べ在院患者数', 
                 '総入院患者数', '総退院患者数', '緊急入院率', '死亡率']
    
    if group_by_column:
        cols_order.extend(['在院患者数割合', '入院患者数割合', '退院患者数割合'])
    
    # 存在する列だけを選択
    cols_order = [col for col in cols_order if col in metrics_df.columns]
    metrics_df = metrics_df[cols_order]
    
    return metrics_df