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
            if col in available_cols:
                census_col = col
                break
        
        # 入院患者数の列名を特定
        admission_col = None
        for col in ['総入院患者数', '入院患者数', '新入院患者数']:
            if col in available_cols:
                admission_col = col
                break
        
        # 退院患者数の列名を特定
        discharge_col = None
        for col in ['総退院患者数', '退院患者数']:
            if col in available_cols:
                discharge_col = col
                break
        
        # st.write(f"**使用する列:**")
        # st.write(f"- 在院患者数: {census_col}")
        # st.write(f"- 入院患者数: {admission_col}")
        # st.write(f"- 退院患者数: {discharge_col}")
        
        if not census_col:
            st.error("在院患者数の列が見つかりません。")
            return
        
        # ⭐ 延べ在院日数の計算
        df_filtered['延べ在院日数'] = df_filtered[census_col]
        
        # ⭐ 月別集計
        df_filtered['年月'] = df_filtered['日付'].dt.to_period('M')
        
        # 集計用辞書の準備
        agg_dict = {
            '延べ在院日数': 'sum',
            census_col: 'mean'  # 日平均在院患者数
        }
        
        if admission_col:
            agg_dict[admission_col] = 'sum'
        if discharge_col:
            agg_dict[discharge_col] = 'sum'
        
        monthly_summary = df_filtered.groupby('年月').agg(agg_dict).reset_index()
        
        # 列名を標準化
        rename_dict = {census_col: '日平均在院患者数'}
        if admission_col:
            rename_dict[admission_col] = '総入院患者数'
        if discharge_col:
            rename_dict[discharge_col] = '総退院患者数'
        
        monthly_summary = monthly_summary.rename(columns=rename_dict)
        
        # ⭐ 診療科別月間集計
        dept_agg_dict = {
            '延べ在院日数': 'sum',
            census_col: 'mean'
        }
        if admission_col:
            dept_agg_dict[admission_col] = 'sum'
        if discharge_col:
            dept_agg_dict[discharge_col] = 'sum'
        
        dept_monthly = df_filtered.groupby(['年月', '診療科名']).agg(dept_agg_dict).reset_index()
        dept_monthly = dept_monthly.rename(columns=rename_dict)
        
        # ⭐ 最新月データの詳細確認
        latest_month = monthly_summary['年月'].max()
        latest_month_data = df_filtered[df_filtered['年月'] == latest_month]
        
        # 手動計算での検証
        manual_total_census = latest_month_data[census_col].sum()
        manual_days = len(latest_month_data['日付'].unique())
        manual_avg_census = manual_total_census / manual_days if manual_days > 0 else 0
        
        # st.write("**最新月の詳細データ確認:**")
        # st.write(f"- 最新月: {latest_month}")
        # st.write(f"- 最新月の日数: {manual_days}日")
        # st.write(f"- 最新月の延べ在院日数（手動計算）: {manual_total_census:,.0f}人日")
        # st.write(f"- 最新月の日平均在院患者数（手動計算）: {manual_avg_census:.1f}人")
        
        if admission_col:
            manual_admissions = latest_month_data[admission_col].sum()
            # st.write(f"- 最新月の総入院患者数: {manual_admissions:.0f}人")
        
        # ⭐ 集計結果との比較
        latest_data = monthly_summary[monthly_summary['年月'] == latest_month].iloc[0]
        
        # st.write("**集計結果との比較:**")
        # st.write(f"- 延べ在院日数（集計）: {latest_data['延べ在院日数']:,.0f}人日")
        # st.write(f"- 日平均在院患者数（集計）: {latest_data['日平均在院患者数']:.1f}人")
        
        # ⭐ 異常値の検出と修正
        census_diff = abs(latest_data['日平均在院患者数'] - manual_avg_census)
        patient_days_diff = abs(latest_data['延べ在院日数'] - manual_total_census)
        
        # st.write(f"**計算差異:**")
        # st.write(f"- 延べ在院日数の差異: {patient_days_diff:.0f}人日")
        # st.write(f"- 日平均在院患者数の差異: {census_diff:.1f}人")
        
        # 異常値がある場合は手動計算値を使用
        if census_diff > 1.0 or patient_days_diff > 100:
            st.warning("⚠️ 集計値に異常が検出されました。手動計算値を使用します。")
            current_patient_days = manual_total_census
            current_avg_census = manual_avg_census
        else:
            current_patient_days = latest_data['延べ在院日数']
            current_avg_census = latest_data['日平均在院患者数']
        
        # ⭐ 新入院患者数の取得
        if '総入院患者数' in latest_data.index and pd.notna(latest_data['総入院患者数']):
            current_admissions = latest_data['総入院患者数']
        elif admission_col:
            current_admissions = manual_admissions
        else:
            current_admissions = 0
            st.warning("新入院患者数データが利用できません。")
        
        # ⭐ 最終的な計算値
        total_beds = st.session_state.get('total_beds', 612)
        bed_utilization = (current_avg_census / total_beds) * 100
        
        # st.write("**最終的な計算値:**")
        # st.write(f"- 延べ在院日数: {current_patient_days:,.0f}人日")
        # st.write(f"- 新入院患者数: {current_admissions:,.0f}人")
        # st.write(f"- 日平均在院患者数: {current_avg_census:.1f}人")
        # st.write(f"- 総病床数: {total_beds}床")
        # st.write(f"- 病床利用率: {bed_utilization:.1f}%")
        
        # ⭐ 妥当性チェック
        # if current_avg_census < 10:
            # st.error("❌ 日平均在院患者数が異常に小さいです。データまたは計算に問題があります。")
        # elif bed_utilization < 5:
            # st.error("❌ 病床利用率が異常に小さいです。データまたは計算に問題があります。")
        # else:
            # st.success("✅ 計算値は妥当な範囲内です。")
        
        # 前月データ
        if len(monthly_summary) > 1:
            prev_month_data = monthly_summary.iloc[-2]  # 最新月の前の月
        else:
            prev_month_data = latest_data
        
        # ⭐ 目標達成率と前月比の計算
        patient_days_achievement = (current_patient_days / monthly_target_patient_days) * 100
        
        if current_admissions > 0:
            admissions_achievement = (current_admissions / monthly_target_admissions) * 100
        else:
            admissions_achievement = 0
        
        # 前月比
        if prev_month_data['延べ在院日数'] > 0:
            patient_days_mom = ((current_patient_days - prev_month_data['延べ在院日数']) / prev_month_data['延べ在院日数']) * 100
        else:
            patient_days_mom = 0
        
        if '総入院患者数' in prev_month_data.index and prev_month_data['総入院患者数'] > 0:
            admissions_mom = ((current_admissions - prev_month_data['総入院患者数']) / prev_month_data['総入院患者数']) * 100
        else:
            admissions_mom = 0
        
        # 収益推計
        estimated_revenue = current_patient_days * avg_admission_fee
        target_revenue = monthly_target_patient_days * avg_admission_fee
        revenue_achievement = (estimated_revenue / target_revenue) * 100
        
        # ===== KPIカード表示 =====
        st.subheader(f"📊 主要指標（最新月: {latest_month}）")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(create_kpi_card(
                "延べ在院日数",
                f"{current_patient_days:,.0f}人日",
                f"目標達成率: {patient_days_achievement:.1f}%",
                f"前月比: {patient_days_mom:+.1f}%",
                get_status_color(patient_days_achievement, alert_threshold_low, alert_threshold_high)
            ), unsafe_allow_html=True)
        
        with col2:
            st.markdown(create_kpi_card(
                "新入院患者数",
                f"{current_admissions:,.0f}人",
                f"目標達成率: {admissions_achievement:.1f}%",
                f"前月比: {admissions_mom:+.1f}%",
                get_status_color(admissions_achievement, alert_threshold_low, alert_threshold_high)
            ), unsafe_allow_html=True)
        
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

# 以下、既存の関数群をそのまま使用...

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