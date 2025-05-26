import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta
import jpholiday

def ensure_datetime_compatibility(df, date_columns=None):
    """DataFrameの日付列をdatetime型に統一する"""
    if date_columns is None:
        date_columns = ['日付']
    
    df_result = df.copy()
    
    for col in date_columns:
        if col in df_result.columns:
            try:
                df_result[col] = pd.to_datetime(df_result[col])
                print(f"列 '{col}' をdatetime型に変換しました")
            except Exception as e:
                print(f"列 '{col}' の変換に失敗: {e}")
    
    return df_result

def safe_date_filter(df, start_date=None, end_date=None):
    """安全な日付フィルタリング"""
    try:
        if df is None or df.empty:
            return df
            
        df_result = df.copy()
        
        if '日付' not in df_result.columns:
            return df_result
        
        # 日付列をdatetime型に変換
        df_result['日付'] = pd.to_datetime(df_result['日付'])
        
        if start_date is not None:
            start_date_pd = pd.to_datetime(start_date)
            df_result = df_result[df_result['日付'] >= start_date_pd]
        
        if end_date is not None:
            end_date_pd = pd.to_datetime(end_date)
            df_result = df_result[df_result['日付'] <= end_date_pd]
        
        return df_result
        
    except Exception as e:
        print(f"日付フィルタリングエラー: {e}")
        return df

def create_revenue_dashboard_section(df, targets_df=None, period_info=None):
    """
    収益管理ダッシュボードセクションの作成
    
    Parameters:
    -----------
    df : pd.DataFrame
        分析対象のデータフレーム
    targets_df : pd.DataFrame, optional
        目標値データフレーム
    period_info : dict, optional
        期間情報（'start_date', 'end_date', 'period_type'を含む）
    """
    
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    
    # 日付型の確実な変換を最初に実行
    df = ensure_datetime_compatibility(df)
    
    # サイドバーの設定値を取得
    monthly_target_patient_days = st.session_state.get('monthly_target_patient_days', 17000)
    monthly_target_admissions = st.session_state.get('monthly_target_admissions', 1480)
    avg_admission_fee = st.session_state.get('avg_admission_fee', 55000)
    alert_threshold_low = st.session_state.get('alert_threshold_low', 85)
    alert_threshold_high = st.session_state.get('alert_threshold_high', 115)
    
    try:
        # 期間情報から日付を取得（新しい方式）
        if period_info:
            start_date = period_info.get('start_date')
            end_date = period_info.get('end_date')
            period_type = period_info.get('period_type', '')
        else:
            # 従来の方式（後方互換性）
            start_date = st.session_state.get('start_date')
            end_date = st.session_state.get('end_date')
            period_type = ''
        
        df_filtered = safe_date_filter(df, start_date, end_date)
        
        if df_filtered.empty:
            st.warning("指定された期間にデータがありません。")
            return
        
        # デバッグ情報の削除（本番環境では不要）
        # st.write(f"**期間設定確認:** {start_date} ～ {end_date}")
        # st.write(f"**フィルタ前データ:** {len(df):,}行")
        # st.write(f"**フィルタ後データ:** {len(df_filtered):,}行")
        
        # 期間タイプに応じたヘッダー表示
        if period_type:
            st.subheader(f"💰 収益管理ダッシュボード - {period_type}")
        
        # ⭐ 利用可能な列名の確認
        available_cols = df_filtered.columns.tolist()
        # st.write("**利用可能な列名:**", available_cols)
        
        # 在院患者数の列名を特定
        census_col = None
        for col in ['在院患者数', '入院患者数（在院）', '現在患者数']:
            if col in df_filtered.columns:
                census_col = col
                break
        
        if not census_col:
            st.error("在院患者数の列が見つかりません。")
            return
        
        # ⭐ 修正：正しい月別集計方法
        df_filtered['年月'] = df_filtered['日付'].dt.to_period('M')
        
        # まず日別に集計してから月別に集計
        daily_aggregated = df_filtered.groupby(['年月', '日付']).agg({
            census_col: 'sum',  # 同日の全診療科・病棟を合計
            admission_col: 'sum' if admission_col else lambda x: 0,
            discharge_col: 'sum' if discharge_col else lambda x: 0
        }).reset_index()
        
        # 月別集計（正しい方法）
        monthly_summary = daily_aggregated.groupby('年月').agg({
            census_col: 'mean',        # 日別合計の平均 = 日平均在院患者数
            admission_col: 'sum' if admission_col else lambda x: 0,     # 月間総入院患者数
            discharge_col: 'sum' if discharge_col else lambda x: 0      # 月間総退院患者数
        }).reset_index()
        
        # 延べ在院日数の計算（日平均×日数 または 日別合計の総和）
        monthly_summary['延べ在院日数'] = daily_aggregated.groupby('年月')[census_col].sum().values
        
        # 列名を標準化
        rename_dict = {census_col: '日平均在院患者数'}
        if admission_col:
            rename_dict[admission_col] = '総入院患者数'
        if discharge_col:
            rename_dict[discharge_col] = '総退院患者数'
        
        monthly_summary = monthly_summary.rename(columns=rename_dict)
        
        # ⭐ 修正：診療科別月間集計も同様に修正
        dept_daily_aggregated = df_filtered.groupby(['年月', '診療科名', '日付']).agg({
            census_col: 'sum',
            admission_col: 'sum' if admission_col else lambda x: 0,
            discharge_col: 'sum' if discharge_col else lambda x: 0
        }).reset_index()
        
        dept_monthly = dept_daily_aggregated.groupby(['年月', '診療科名']).agg({
            census_col: 'mean',  # 日平均
            admission_col: 'sum' if admission_col else lambda x: 0,
            discharge_col: 'sum' if discharge_col else lambda x: 0
        }).reset_index()
        
        dept_monthly['延べ在院日数'] = dept_daily_aggregated.groupby(['年月', '診療科名'])[census_col].sum().values
        dept_monthly = dept_monthly.rename(columns=rename_dict)
        
        # ⭐ 計算検証の表示
        if st.checkbox("🔧 収益計算の詳細を表示", key="show_revenue_calculation_debug"):
            st.markdown("#### 📊 収益計算詳細")
            
            latest_month = monthly_summary['年月'].max()
            latest_month_daily = daily_aggregated[daily_aggregated['年月'] == latest_month]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**旧計算方法（間違い）**")
                # 間違った方法をデモ
                wrong_calc = df_filtered[df_filtered['年月'] == latest_month][census_col].mean()
                st.write(f"全行の平均: {wrong_calc:.1f}人")
                
                st.markdown("**正しい計算方法**")
                correct_calc = latest_month_daily[census_col].mean()
                st.write(f"日別合計の平均: {correct_calc:.1f}人")
                
                st.write(f"**差異**: {abs(wrong_calc - correct_calc):.1f}人")
            
            with col2:
                st.markdown("**日別データ（最新月）**")
                st.dataframe(
                    latest_month_daily[['日付', census_col]].rename(columns={census_col: '日合計在院患者数'}),
                    hide_index=True
                )
        
        with col3:
            st.markdown(create_kpi_card(
                "推計収益",
                f"¥{estimated_revenue:,.0f}",
                f"目標達成率: {revenue_achievement:.1f}%",
                f"目標: ¥{target_revenue:,.0f}",
                get_status_color(revenue_achievement, alert_threshold_low, alert_threshold_high)
            ), unsafe_allow_html=True)
        
        with col4:
            st.markdown(create_kpi_card(
                "病床利用率",
                f"{bed_utilization:.1f}%",
                f"日平均在院: {current_avg_census:.0f}人",
                f"総病床数: {total_beds}床",
                get_status_color(bed_utilization, 80, 95)
            ), unsafe_allow_html=True)
        
        # ===== グラフ表示 =====
        st.markdown("---")
        
        # 月別トレンドグラフ
        col1, col2 = st.columns(2)
        
        with col1:
            fig_trend = create_monthly_trend_chart(monthly_summary, monthly_target_patient_days, monthly_target_admissions)
            st.plotly_chart(fig_trend, use_container_width=True)
        
        with col2:
            fig_revenue = create_revenue_trend_chart(monthly_summary, monthly_target_patient_days, avg_admission_fee)
            st.plotly_chart(fig_revenue, use_container_width=True)
        
        # 診療科別分析
        st.markdown("---")
        st.subheader("🏥 診療科別収益分析")
        
        # 最新月の診療科別データ
        latest_dept_data = dept_monthly[dept_monthly['年月'] == latest_month].copy()
        latest_dept_data['推計収益'] = latest_dept_data['延べ在院日数'] * avg_admission_fee
        latest_dept_data = latest_dept_data.sort_values('推計収益', ascending=False)
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig_dept_revenue = create_department_revenue_chart(latest_dept_data)
            st.plotly_chart(fig_dept_revenue, use_container_width=True)
        
        with col2:
            fig_dept_patients = create_department_patients_chart(latest_dept_data)
            st.plotly_chart(fig_dept_patients, use_container_width=True)
        
        # 詳細テーブル
        st.markdown("---")
        st.subheader("📋 診療科別詳細データ")
        
        # テーブル用データの準備
        table_columns = ['診療科名', '延べ在院日数']
        
        if '総入院患者数' in latest_dept_data.columns:
            table_columns.append('総入院患者数')
        if '総退院患者数' in latest_dept_data.columns:
            table_columns.append('総退院患者数')
        if '日平均在院患者数' in latest_dept_data.columns:
            table_columns.append('日平均在院患者数')
        
        table_columns.append('推計収益')
        
        table_data = latest_dept_data[table_columns].copy()
        table_data['収益構成比'] = (table_data['推計収益'] / table_data['推計収益'].sum()) * 100
        
        # 数値の書式設定
        if '日平均在院患者数' in table_data.columns:
            table_data['日平均在院患者数'] = table_data['日平均在院患者数'].round(1)
        table_data['収益構成比'] = table_data['収益構成比'].apply(lambda x: f"{x:.1f}%")
        table_data['推計収益_display'] = table_data['推計収益'].apply(lambda x: f"¥{x:,.0f}")
        
        # 表示用データの作成
        display_columns = ['診療科名', '延べ在院日数']
        if '総入院患者数' in table_data.columns:
            display_columns.append('総入院患者数')
        if '総退院患者数' in table_data.columns:
            display_columns.append('総退院患者数')
        if '日平均在院患者数' in table_data.columns:
            display_columns.append('日平均在院患者数')
        
        display_columns.extend(['推計収益_display', '収益構成比'])
        
        display_data = table_data[display_columns].copy()
        
        # 列名の変更
        new_column_names = {'推計収益_display': '推計収益'}
        if '総入院患者数' in display_data.columns:
            new_column_names['総入院患者数'] = '新入院患者数'
        
        display_data = display_data.rename(columns=new_column_names)
        
        st.dataframe(display_data, use_container_width=True, hide_index=True)
        
        # アラート表示
        st.markdown("---")
        display_alerts(patient_days_achievement, admissions_achievement, revenue_achievement, 
                      alert_threshold_low, alert_threshold_high)
        
    except Exception as e:
        st.error(f"収益ダッシュボード作成中にエラー: {e}")
        print(f"詳細エラー: {e}")
        import traceback
        print(traceback.format_exc())

def get_status_color(value, low_threshold, high_threshold):
    """達成率に基づいてステータス色を決定"""
    if value < low_threshold:
        return "#e74c3c"  # 赤
    elif value > high_threshold:
        return "#f39c12"  # オレンジ
    else:
        return "#2ecc71"  # 緑

def create_kpi_card(title, value, subtitle, additional_info, color):
    """KPIカードのHTML生成"""
    return f"""
    <div style="
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid {color};
        margin-bottom: 1rem;
    ">
        <h4 style="margin: 0; font-size: 0.9rem; color: #666;">{title}</h4>
        <h2 style="margin: 0.5rem 0; color: #333;">{value}</h2>
        <p style="margin: 0; font-size: 0.8rem; color: {color}; font-weight: bold;">{subtitle}</p>
        <p style="margin: 0; font-size: 0.7rem; color: #888;">{additional_info}</p>
    </div>
    """

def create_monthly_trend_chart(monthly_summary, target_patient_days, target_admissions):
    """月別トレンドチャートの作成"""
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=('延べ在院日数の推移', '新入院患者数の推移'),
        vertical_spacing=0.15
    )
    
    months = [str(period) for period in monthly_summary['年月']]
    
    # 延べ在院日数
    fig.add_trace(
        go.Scatter(
            x=months,
            y=monthly_summary['延べ在院日数'],
            mode='lines+markers',
            name='実績',
            line=dict(color='#3498db', width=3),
            marker=dict(size=8)
        ),
        row=1, col=1
    )
    
    # 目標線（延べ在院日数）
    fig.add_trace(
        go.Scatter(
            x=months,
            y=[target_patient_days] * len(months),
            mode='lines',
            name='目標',
            line=dict(color='#e74c3c', width=2, dash='dash')
        ),
        row=1, col=1
    )
    
    # 新入院患者数（存在する場合のみ）
    if '総入院患者数' in monthly_summary.columns:
        fig.add_trace(
            go.Scatter(
                x=months,
                y=monthly_summary['総入院患者数'],
                mode='lines+markers',
                name='実績',
                line=dict(color='#2ecc71', width=3),
                marker=dict(size=8),
                showlegend=False
            ),
            row=2, col=1
        )
        
        # 目標線（新入院患者数）
        fig.add_trace(
            go.Scatter(
                x=months,
                y=[target_admissions] * len(months),
                mode='lines',
                name='目標',
                line=dict(color='#e74c3c', width=2, dash='dash'),
                showlegend=False
            ),
            row=2, col=1
        )
    
    fig.update_layout(
        title="月別実績トレンド",
        height=500,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    return fig

def create_revenue_trend_chart(monthly_summary, target_patient_days, avg_admission_fee):
    """収益トレンドチャートの作成"""
    monthly_summary_copy = monthly_summary.copy()
    monthly_summary_copy['推計収益'] = monthly_summary_copy['延べ在院日数'] * avg_admission_fee
    target_revenue = target_patient_days * avg_admission_fee
    
    fig = go.Figure()
    
    months = [str(period) for period in monthly_summary_copy['年月']]
    
    fig.add_trace(
        go.Bar(
            x=months,
            y=monthly_summary_copy['推計収益'],
            name='推計収益',
            marker_color='#3498db',
            opacity=0.8
        )
    )
    
    fig.add_trace(
        go.Scatter(
            x=months,
            y=[target_revenue] * len(months),
            mode='lines',
            name='目標収益',
            line=dict(color='#e74c3c', width=3, dash='dash')
        )
    )
    
    fig.update_layout(
        title="月別推計収益",
        xaxis_title="月",
        yaxis_title="収益 (円)",
        yaxis=dict(tickformat=',.0f'),
        height=250
    )
    
    return fig

def create_department_revenue_chart(dept_data):
    """診療科別収益チャートの作成"""
    top_10 = dept_data.head(10)
    
    fig = go.Figure(data=[
        go.Bar(
            x=top_10['推計収益'],
            y=top_10['診療科名'],
            orientation='h',
            marker_color='#3498db',
            opacity=0.8
        )
    ])
    
    fig.update_layout(
        title="診療科別推計収益（上位10科）",
        xaxis_title="推計収益 (円)",
        yaxis_title="診療科",
        xaxis=dict(tickformat=',.0f'),
        height=400
    )
    
    return fig

def create_department_patients_chart(dept_data):
    """診療科別延べ在院日数チャートの作成"""
    top_10 = dept_data.head(10)
    
    fig = go.Figure(data=[
        go.Bar(
            x=top_10['延べ在院日数'],
            y=top_10['診療科名'],
            orientation='h',
            marker_color='#2ecc71',
            opacity=0.8
        )
    ])
    
    fig.update_layout(
        title="診療科別延べ在院日数（上位10科）",
        xaxis_title="延べ在院日数 (人日)",
        yaxis_title="診療科",
        height=400
    )
    
    return fig

def display_alerts(patient_days_achievement, admissions_achievement, revenue_achievement, 
                  alert_threshold_low, alert_threshold_high):
    """アラート表示"""
    alerts = []
    
    if patient_days_achievement < alert_threshold_low:
        alerts.append(f"⚠️ 延べ在院日数が目標を下回っています（{patient_days_achievement:.1f}%）")
    elif patient_days_achievement > alert_threshold_high:
        alerts.append(f"📈 延べ在院日数が目標を上回っています（{patient_days_achievement:.1f}%）")
    
    if admissions_achievement < alert_threshold_low:
        alerts.append(f"⚠️ 新入院患者数が目標を下回っています（{admissions_achievement:.1f}%）")
    elif admissions_achievement > alert_threshold_high:
        alerts.append(f"📈 新入院患者数が目標を上回っています（{admissions_achievement:.1f}%）")
    
    if revenue_achievement < alert_threshold_low:
        alerts.append(f"🚨 推計収益が目標を下回っています（{revenue_achievement:.1f}%）")
    elif revenue_achievement > alert_threshold_high:
        alerts.append(f"💰 推計収益が目標を上回っています（{revenue_achievement:.1f}%）")
    
    if alerts:
        st.subheader("🚨 アラート")
        for alert in alerts:
            if "🚨" in alert or "⚠️" in alert:
                st.warning(alert)
            else:
                st.success(alert)
    else:
        st.success("✅ すべての指標が正常範囲内です。")
        
def validate_monthly_calculations(df_filtered):
    """月別計算の妥当性を検証"""
    
    df_filtered['年月'] = df_filtered['日付'].dt.to_period('M')
    
    validation_results = []
    
    for month in df_filtered['年月'].unique():
        month_data = df_filtered[df_filtered['年月'] == month]
        
        # 基本統計
        days_in_month = len(month_data['日付'].unique())
        total_census = month_data['在院患者数'].sum()
        avg_census_method1 = month_data['在院患者数'].mean()  # groupby.mean()と同じ
        avg_census_method2 = total_census / days_in_month     # 手動計算
        
        validation_results.append({
            '年月': str(month),
            '日数': days_in_month,
            '延べ在院日数': total_census,
            '日平均（method1）': avg_census_method1,
            '日平均（method2）': avg_census_method2,
            '差異': abs(avg_census_method1 - avg_census_method2)
        })
    
    return pd.DataFrame(validation_results)