import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta

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

def validate_hospital_data_structure(df):
    """
    当院のデータ構造を検証し、必要な列の存在確認
    
    Returns:
    --------
    dict: 検証結果と列情報
    """
    validation_result = {
        'is_valid': True,
        'errors': [],
        'warnings': [],
        'column_mapping': {},
        'missing_columns': []
    }
    
    # 当院の必須列定義
    required_columns = {
        '在院患者数': ['在院患者数', '入院患者数（在院）', '現在患者数'],
        '入院患者数': ['入院患者数', '通常入院患者数', '一般入院患者数'],
        '緊急入院患者数': ['緊急入院患者数', '救急入院患者数', '急患入院患者数'],
        '退院患者数': ['退院患者数', '生存退院患者数', '通常退院患者数'],  # 重要：死亡を含まない
        '死亡患者数': ['死亡患者数', '院内死亡患者数', '死亡者数']
    }
    
    # 各列の存在確認と設定
    for standard_name, possible_names in required_columns.items():
        found_column = None
        for possible_name in possible_names:
            if possible_name in df.columns:
                found_column = possible_name
                break
        
        if found_column:
            validation_result['column_mapping'][standard_name] = found_column
        else:
            validation_result['missing_columns'].append(standard_name)
            validation_result['errors'].append(f"必須列が見つかりません: {standard_name} (候補: {possible_names})")
    
    # 致命的エラーのチェック
    critical_columns = ['在院患者数', '入院患者数', '緊急入院患者数']
    missing_critical = [col for col in critical_columns if col in validation_result['missing_columns']]
    
    if missing_critical:
        validation_result['is_valid'] = False
        validation_result['errors'].append(f"重要な列が不足しているため処理を継続できません: {missing_critical}")
    
    # 警告の生成
    if '退院患者数' in validation_result['missing_columns']:
        validation_result['warnings'].append("「退院患者数」列がありません。総退院患者数の計算が不正確になる可能性があります。")
    
    if '死亡患者数' in validation_result['missing_columns']:
        validation_result['warnings'].append("「死亡患者数」列がありません。総退院患者数の計算が不正確になる可能性があります。")
    
    return validation_result

def create_derived_columns_hospital(df, column_mapping):
    """
    当院のビジネスルールに基づいて派生列を作成
    
    重要な計算ロジック:
    - 新入院患者数 = 入院患者数 + 緊急入院患者数
    - 総退院患者数 = 退院患者数 + 死亡患者数 (病院から実際にいなくなった患者数)
    """
    df_result = df.copy()
    
    # 必要な元列を取得
    census_col = column_mapping.get('在院患者数')
    admission_col = column_mapping.get('入院患者数')
    emergency_col = column_mapping.get('緊急入院患者数')
    discharge_col = column_mapping.get('退院患者数')  # 注意：死亡を含まない
    death_col = column_mapping.get('死亡患者数')
    
    # 1. 新入院患者数の計算（入院患者数 + 緊急入院患者数）
    if admission_col and emergency_col:
        df_result['新入院患者数'] = (
            df_result[admission_col].fillna(0) + 
            df_result[emergency_col].fillna(0)
        )
        print(f"✅ 新入院患者数を計算: {admission_col} + {emergency_col}")
    elif admission_col:
        df_result['新入院患者数'] = df_result[admission_col].fillna(0)
        print(f"⚠️ 緊急入院患者数列がないため、通常入院患者数のみを使用: {admission_col}")
    else:
        df_result['新入院患者数'] = 0
        print(f"❌ 入院患者数列がないため、新入院患者数を0に設定")
    
    # 2. 総退院患者数の計算（退院患者数 + 死亡患者数）
    # 重要：これが病院から実際にいなくなった患者数
    if discharge_col and death_col:
        df_result['総退院患者数'] = (
            df_result[discharge_col].fillna(0) + 
            df_result[death_col].fillna(0)
        )
        print(f"✅ 総退院患者数を計算: {discharge_col} + {death_col}")
    elif discharge_col:
        df_result['総退院患者数'] = df_result[discharge_col].fillna(0)
        print(f"⚠️ 死亡患者数列がないため、生存退院患者数のみを使用: {discharge_col}")
    elif death_col:
        df_result['総退院患者数'] = df_result[death_col].fillna(0)
        print(f"⚠️ 退院患者数列がないため、死亡患者数のみを使用: {death_col}")
    else:
        df_result['総退院患者数'] = 0
        print(f"❌ 退院・死亡患者数列がないため、総退院患者数を0に設定")
    
    # 3. 追加の有用な指標
    # 生存退院率（死亡を除く退院の割合）
    if discharge_col and death_col:
        total_exits = df_result['総退院患者数']
        df_result['生存退院率'] = np.where(
            total_exits > 0, 
            (df_result[discharge_col].fillna(0) / total_exits) * 100, 
            0
        )
    
    # 緊急入院比率
    if admission_col and emergency_col:
        total_admissions = df_result['新入院患者数']
        df_result['緊急入院比率'] = np.where(
            total_admissions > 0,
            (df_result[emergency_col].fillna(0) / total_admissions) * 100,
            0
        )
    
    # 在院患者数の列名を標準化（後続処理との整合性のため）
    if census_col:
        df_result['標準_在院患者数'] = df_result[census_col]
    else:
        df_result['標準_在院患者数'] = 0
    
    return df_result

def display_hospital_data_verification(validation_result, monthly_summary=None):
    """当院データの検証結果表示"""
    
    # 警告の表示
    if validation_result.get('warnings'):
        st.warning("⚠️ 以下の警告があります：")
        for warning in validation_result['warnings']:
            st.warning(f"• {warning}")
    
    # 列マッピングの表示
    with st.expander("📋 使用された列名マッピング", expanded=False):
        column_mapping = validation_result.get('column_mapping', {})
        if column_mapping:
            for standard_name, actual_name in column_mapping.items():
                st.write(f"• **{standard_name}** ← `{actual_name}`")
        else:
            st.write("列マッピング情報がありません。")
    
    # 計算ロジックの説明
    with st.expander("🧮 当院の計算ロジック", expanded=False):
        st.markdown("""
        **当院のデータ構造に基づく重要な計算:**
        
        1. **新入院患者数** = 入院患者数 + 緊急入院患者数
           - 当日に入院した全患者数（通常入院 + 緊急入院）
        
        2. **総退院患者数** = 退院患者数 + 死亡患者数
           - 実際に病院からいなくなった患者数
           - 注意：「退院患者数」は死亡を含まない生存退院のみ
        
        3. **生存退院率** = (退院患者数 ÷ 総退院患者数) × 100
           - 医療の質を示す重要な指標
        
        4. **緊急入院比率** = (緊急入院患者数 ÷ 新入院患者数) × 100
           - 救急体制の稼働状況を示す指標
        """)

def create_revenue_dashboard_section(df, targets_df=None, period_info=None):
    """
    当院データ構造に対応した収益管理ダッシュボードセクションの作成
    
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
        # 期間情報から日付を取得
        if period_info:
            start_date = period_info.get('start_date')
            end_date = period_info.get('end_date')
            period_type = period_info.get('period_type', '')
        else:
            start_date = st.session_state.get('start_date')
            end_date = st.session_state.get('end_date')
            period_type = ''
        
        df_filtered = safe_date_filter(df, start_date, end_date)
        
        if df_filtered.empty:
            st.warning("指定された期間にデータがありません。")
            return
        
        # 🏥 当院データ構造の検証
        st.markdown("---")
        
        # データ検証の詳細表示オプション
        show_verification = st.checkbox("🔍 当院データ構造の検証詳細を表示", key="show_hospital_verification")
        
        validation_result = validate_hospital_data_structure(df_filtered)
        
        if not validation_result['is_valid']:
            st.error("❌ データ構造に問題があります。処理を継続できません。")
            for error in validation_result['errors']:
                st.error(f"• {error}")
            return
        
        # 派生列の作成
        df_processed = create_derived_columns_hospital(df_filtered, validation_result['column_mapping'])
        
        # 期間列の作成
        df_processed['年月'] = pd.to_datetime(df_processed['日付']).dt.to_period('M')
        
        # 日別集計（同日の複数記録を合計）
        daily_agg = df_processed.groupby(['年月', '日付']).agg({
            '標準_在院患者数': 'sum',
            '新入院患者数': 'sum',
            '総退院患者数': 'sum'
        }).reset_index()
        
        # 追加の指標も日別集計に含める
        if '生存退院率' in df_processed.columns:
            daily_agg_detailed = df_processed.groupby(['年月', '日付']).agg({
                '標準_在院患者数': 'sum',
                '新入院患者数': 'sum',
                '総退院患者数': 'sum',
                '生存退院率': 'mean',
                '緊急入院比率': 'mean'
            }).reset_index()
        else:
            daily_agg_detailed = daily_agg.copy()
        
        # 月別集計（正しい方法）
        agg_columns = {
            '標準_在院患者数': 'mean',  # 日平均在院患者数
            '新入院患者数': 'sum',      # 月間総新入院患者数
            '総退院患者数': 'sum'       # 月間総退院患者数
        }
        
        if '生存退院率' in daily_agg_detailed.columns:
            agg_columns['生存退院率'] = 'mean'
        if '緊急入院比率' in daily_agg_detailed.columns:
            agg_columns['緊急入院比率'] = 'mean'
        
        monthly_summary = daily_agg_detailed.groupby('年月').agg(agg_columns).reset_index()
        
        # 延べ在院日数の計算（日別在院患者数の合計）
        monthly_summary['延べ在院日数'] = daily_agg.groupby('年月')['標準_在院患者数'].sum().values
        
        if monthly_summary.empty:
            st.warning("集計可能なデータがありません。")
            return
        
        # 検証詳細の表示
        if show_verification:
            display_hospital_data_verification(validation_result, monthly_summary)
        
        # 期間タイプに応じたヘッダー表示
        if period_type:
            st.subheader(f"💰 収益管理ダッシュボード - {period_type}")
        else:
            st.subheader("💰 収益管理ダッシュボード（当院データ対応）")
        
        # KPI計算（当院ルールに基づく）
        latest_month_data = monthly_summary.iloc[-1]
        
        # 基本指標の取得
        current_patient_days = latest_month_data['延べ在院日数']
        current_avg_census = latest_month_data['標準_在院患者数']
        current_new_admissions = latest_month_data['新入院患者数']  # 通常 + 緊急
        current_total_discharges = latest_month_data['総退院患者数']  # 退院 + 死亡
        
        # 達成率計算
        patient_days_achievement = (current_patient_days / monthly_target_patient_days) * 100 if monthly_target_patient_days > 0 else 0
        admissions_achievement = (current_new_admissions / monthly_target_admissions) * 100 if monthly_target_admissions > 0 else 0
        
        # 収益計算
        estimated_revenue = current_patient_days * avg_admission_fee
        target_revenue = monthly_target_patient_days * avg_admission_fee
        revenue_achievement = (estimated_revenue / target_revenue) * 100 if target_revenue > 0 else 0
        
        # 病床利用率計算
        total_beds = st.session_state.get('total_beds', 612)
        bed_utilization = (current_avg_census / total_beds) * 100 if total_beds > 0 else 0
        
        # KPIカード表示（当院仕様）
        st.markdown("### 📊 主要指標（当院データ構造対応）")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(create_kpi_card(
                "延べ在院日数",
                f"{current_patient_days:,.0f}人日",
                f"達成率: {patient_days_achievement:.1f}%",
                f"目標: {monthly_target_patient_days:,}人日",
                get_status_color(patient_days_achievement, alert_threshold_low, alert_threshold_high)
            ), unsafe_allow_html=True)
        
        with col2:
            st.markdown(create_kpi_card(
                "新入院患者数",
                f"{current_new_admissions:,.0f}人",
                f"達成率: {admissions_achievement:.1f}%",
                f"通常+緊急の合計",
                get_status_color(admissions_achievement, alert_threshold_low, alert_threshold_high)
            ), unsafe_allow_html=True)
            
            # 内訳を小さく表示（当院特有）
            column_mapping = validation_result['column_mapping']
            if '入院患者数' in column_mapping and '緊急入院患者数' in column_mapping:
                # 最新月の詳細データを取得
                latest_month_period = latest_month_data.name
                latest_month_detailed_data = df_processed[df_processed['年月'] == latest_month_period]
                
                normal_count = latest_month_detailed_data[column_mapping['入院患者数']].sum()
                emergency_count = latest_month_detailed_data[column_mapping['緊急入院患者数']].sum()
                st.caption(f"内訳: 通常{normal_count:,.0f} + 緊急{emergency_count:,.0f}")
        
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
        
        # 当院特有の指標（追加）
        st.markdown("### 🏥 当院特有指標")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 総退院患者数（実際に病院からいなくなった患者数）
            st.metric(
                "総退院患者数",
                f"{current_total_discharges:,.0f}人",
                help="実際に病院からいなくなった患者数（生存退院+死亡）"
            )
            
            # 内訳表示（当院特有）
            if '退院患者数' in column_mapping and '死亡患者数' in column_mapping:
                latest_month_period = latest_month_data.name
                latest_month_detailed_data = df_processed[df_processed['年月'] == latest_month_period]
                
                discharge_count = latest_month_detailed_data[column_mapping['退院患者数']].sum()
                death_count = latest_month_detailed_data[column_mapping['死亡患者数']].sum()
                st.caption(f"内訳: 生存退院{discharge_count:,.0f} + 死亡{death_count:,.0f}")
        
        with col2:
            # 生存退院率
            if '生存退院率' in latest_month_data and pd.notna(latest_month_data['生存退院率']):
                survival_rate = latest_month_data['生存退院率']
                color = "#2ecc71" if survival_rate >= 90 else "#f39c12" if survival_rate >= 80 else "#e74c3c"
                st.markdown(f"""
                <div style="background-color: white; padding: 1rem; border-radius: 10px; 
                           box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 4px solid {color};">
                    <h4 style="margin: 0; font-size: 0.9rem; color: #666;">生存退院率</h4>
                    <h2 style="margin: 0.5rem 0; color: #333;">{survival_rate:.1f}%</h2>
                    <p style="margin: 0; font-size: 0.8rem; color: {color}; font-weight: bold;">
                        医療の質指標
                    </p>
                </div>
                """, unsafe_allow_html=True)
        
        with col3:
            # 緊急入院比率
            if '緊急入院比率' in latest_month_data and pd.notna(latest_month_data['緊急入院比率']):
                emergency_rate = latest_month_data['緊急入院比率']
                color = "#3498db" if emergency_rate <= 30 else "#f39c12" if emergency_rate <= 40 else "#e74c3c"
                st.markdown(f"""
                <div style="background-color: white; padding: 1rem; border-radius: 10px; 
                           box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 4px solid {color};">
                    <h4 style="margin: 0; font-size: 0.9rem; color: #666;">緊急入院比率</h4>
                    <h2 style="margin: 0.5rem 0; color: #333;">{emergency_rate:.1f}%</h2>
                    <p style="margin: 0; font-size: 0.8rem; color: {color}; font-weight: bold;">
                        救急体制指標
                    </p>
                </div>
                """, unsafe_allow_html=True)
        
        # グラフ表示（当院データ対応）
        st.markdown("---")
        st.markdown("### 📈 推移グラフ")
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig_trend = create_hospital_trend_chart(monthly_summary, monthly_target_patient_days, monthly_target_admissions)
            st.plotly_chart(fig_trend, use_container_width=True)
        
        with col2:
            fig_revenue = create_revenue_trend_chart(monthly_summary, monthly_target_patient_days, avg_admission_fee)
            st.plotly_chart(fig_revenue, use_container_width=True)
        
        # 診療科別分析（当院対応）
        if '診療科名' in df_processed.columns:
            st.markdown("---")
            st.subheader("🏥 診療科別収益分析（当院データ）")
            
            # 診療科別の月別集計
            dept_monthly = create_department_analysis_hospital(df_processed, latest_month_data.name, avg_admission_fee)
            
            if not dept_monthly.empty:
                col1, col2 = st.columns(2)
                
                with col1:
                    fig_dept_revenue = create_department_revenue_chart(dept_monthly)
                    st.plotly_chart(fig_dept_revenue, use_container_width=True)
                
                with col2:
                    fig_dept_patients = create_department_patients_chart(dept_monthly)
                    st.plotly_chart(fig_dept_patients, use_container_width=True)
                
                # 詳細テーブル（当院対応）
                st.markdown("### 📋 診療科別詳細データ")
                display_department_table_hospital(dept_monthly, column_mapping)
        
        # アラート表示（当院対応）
        st.markdown("---")
        display_hospital_alerts(
            patient_days_achievement, 
            admissions_achievement, 
            revenue_achievement,
            latest_month_data.get('生存退院率', 95),
            latest_month_data.get('緊急入院比率', 20),
            alert_threshold_low, 
            alert_threshold_high
        )
        
    except Exception as e:
        st.error(f"収益ダッシュボード作成中にエラー: {e}")
        print(f"詳細エラー: {e}")
        import traceback
        print(traceback.format_exc())

def create_department_analysis_hospital(df_processed, latest_month_period, avg_admission_fee):
    """当院データに基づく診療科別分析"""
    try:
        # 最新月の診療科別データ
        latest_dept_data = df_processed[df_processed['年月'] == latest_month_period]
        
        if latest_dept_data.empty:
            return pd.DataFrame()
        
        # 診療科別集計
        dept_summary = latest_dept_data.groupby('診療科名').agg({
            '標準_在院患者数': 'sum',  # 延べ在院日数
            '新入院患者数': 'sum',
            '総退院患者数': 'sum'
        }).reset_index()
        
        # 推計収益の計算
        dept_summary['推計収益'] = dept_summary['標準_在院患者数'] * avg_admission_fee
        dept_summary = dept_summary.sort_values('推計収益', ascending=False)
        
        # 列名を変更
        dept_summary = dept_summary.rename(columns={
            '標準_在院患者数': '延べ在院日数',
            '新入院患者数': '新入院患者数（通常+緊急）',
            '総退院患者数': '総退院患者数（生存退院+死亡）'
        })
        
        return dept_summary
        
    except Exception as e:
        print(f"診療科別分析エラー: {e}")
        return pd.DataFrame()

def display_department_table_hospital(dept_data, column_mapping):
    """当院データの診療科別詳細テーブル表示"""
    if dept_data.empty:
        st.warning("表示する診療科データがありません。")
        return
    
    table_data = dept_data.copy()
    
    # 収益構成比の計算
    if '推計収益' in table_data.columns:
        table_data['収益構成比'] = (table_data['推計収益'] / table_data['推計収益'].sum()) * 100
        table_data['収益構成比'] = table_data['収益構成比'].apply(lambda x: f"{x:.1f}%")
        table_data['推計収益_display'] = table_data['推計収益'].apply(lambda x: f"¥{x:,.0f}")
    
    # 表示列の設定
    display_columns = ['診療科名', '延べ在院日数', '新入院患者数（通常+緊急）', '総退院患者数（生存退院+死亡）']
    
    if '推計収益_display' in table_data.columns:
        display_columns.extend(['推計収益_display', '収益構成比'])
    
    # 実際に存在する列のみを選択
    available_columns = [col for col in display_columns if col in table_data.columns]
    
    if available_columns:
        display_data = table_data[available_columns].copy()
        
        # 列名の最終調整
        if '推計収益_display' in display_data.columns:
            display_data = display_data.rename(columns={'推計収益_display': '推計収益'})
        
        st.dataframe(display_data, use_container_width=True, hide_index=True)
    else:
        st.warning("表示可能な列がありません。")

def create_hospital_trend_chart(monthly_summary, target_patient_days, target_admissions):
    """当院データに基づく月別トレンドチャート"""
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=(
            '延べ在院日数の推移', 
            '新入院患者数の推移（通常+緊急）', 
            '総退院患者数の推移（生存退院+死亡）'
        ),
        vertical_spacing=0.1
    )
    
    months = [str(period) for period in monthly_summary['年月']]
    
    # 延べ在院日数
    fig.add_trace(
        go.Scatter(
            x=months, y=monthly_summary['延べ在院日数'],
            mode='lines+markers', name='実績',
            line=dict(color='#3498db', width=3), marker=dict(size=8)
        ), row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=months, y=[target_patient_days] * len(months),
            mode='lines', name='目標', line=dict(color='#e74c3c', width=2, dash='dash')
        ), row=1, col=1
    )
    
    # 新入院患者数（通常+緊急）
    fig.add_trace(
        go.Scatter(
            x=months, y=monthly_summary['新入院患者数'],
            mode='lines+markers', name='新入院（通常+緊急）',
            line=dict(color='#2ecc71', width=3), marker=dict(size=8), showlegend=False
        ), row=2, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=months, y=[target_admissions] * len(months),
            mode='lines', name='目標', line=dict(color='#e74c3c', width=2, dash='dash'), showlegend=False
        ), row=2, col=1
    )
    
    # 総退院患者数（生存退院+死亡）
    fig.add_trace(
        go.Scatter(
            x=months, y=monthly_summary['総退院患者数'],
            mode='lines+markers', name='総退院（生存+死亡）',
            line=dict(color='#f39c12', width=3), marker=dict(size=8), showlegend=False
        ), row=3, col=1
    )
    
    fig.update_layout(
        title="当院データ月別トレンド",
        height=600,
        showlegend=True
    )
    
    return fig

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
    """月別トレンドチャートの作成（当院データ対応版）"""
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=('延べ在院日数の推移', '新入院患者数の推移（通常+緊急）'),
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
    
    # 新入院患者数（通常+緊急の合計）
    if '新入院患者数' in monthly_summary.columns:
        fig.add_trace(
            go.Scatter(
                x=months,
                y=monthly_summary['新入院患者数'],
                mode='lines+markers',
                name='新入院（通常+緊急）',
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
        title="月別実績トレンド（当院データ）",
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
        title="月別推計収益（当院基準）",
        xaxis_title="月",
        yaxis_title="収益 (円)",
        yaxis=dict(tickformat=',.0f'),
        height=250
    )
    
    return fig

def create_department_revenue_chart(dept_data):
    """診療科別収益チャートの作成"""
    if dept_data.empty:
        return go.Figure().add_annotation(text="データがありません", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    
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
    if dept_data.empty:
        return go.Figure().add_annotation(text="データがありません", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    
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

def display_hospital_alerts(patient_days_achievement, admissions_achievement, revenue_achievement,
                          survival_rate, emergency_rate, alert_threshold_low, alert_threshold_high):
    """当院特有のアラート表示"""
    alerts = []
    
    # 基本アラート
    if patient_days_achievement < alert_threshold_low:
        alerts.append(f"⚠️ 延べ在院日数が目標を下回っています（{patient_days_achievement:.1f}%）")
    elif patient_days_achievement > alert_threshold_high:
        alerts.append(f"📈 延べ在院日数が目標を上回っています（{patient_days_achievement:.1f}%）")
    
    if admissions_achievement < alert_threshold_low:
        alerts.append(f"⚠️ 新入院患者数（通常+緊急）が目標を下回っています（{admissions_achievement:.1f}%）")
    elif admissions_achievement > alert_threshold_high:
        alerts.append(f"📈 新入院患者数（通常+緊急）が目標を上回っています（{admissions_achievement:.1f}%）")
    
    if revenue_achievement < alert_threshold_low:
        alerts.append(f"🚨 推計収益が目標を下回っています（{revenue_achievement:.1f}%）")
    elif revenue_achievement > alert_threshold_high:
        alerts.append(f"💰 推計収益が目標を上回っています（{revenue_achievement:.1f}%）")
    
    # 当院特有のアラート
    if survival_rate and pd.notna(survival_rate):
        if survival_rate < 85:
            alerts.append(f"⚠️ 生存退院率が低下しています（{survival_rate:.1f}%）。医療の質を確認してください。")
        elif survival_rate > 98:
            alerts.append(f"✅ 生存退院率が非常に良好です（{survival_rate:.1f}%）")
    
    if emergency_rate and pd.notna(emergency_rate):
        if emergency_rate > 40:
            alerts.append(f"🚨 緊急入院比率が高くなっています（{emergency_rate:.1f}%）。救急体制を確認してください。")
        elif emergency_rate < 10:
            alerts.append(f"📊 緊急入院比率が低くなっています（{emergency_rate:.1f}%）")
    
    if alerts:
        st.subheader("🚨 アラート")
        for alert in alerts:
            if "🚨" in alert or "⚠️" in alert:
                st.warning(alert)
            else:
                st.success(alert)
    else:
        st.success("✅ すべての指標が正常範囲内です。")

def display_alerts(patient_days_achievement, admissions_achievement, revenue_achievement, 
                  alert_threshold_low, alert_threshold_high):
    """基本的なアラート表示（後方互換性のため）"""
    display_hospital_alerts(
        patient_days_achievement, 
        admissions_achievement, 
        revenue_achievement,
        None,  # survival_rate
        None,  # emergency_rate
        alert_threshold_low, 
        alert_threshold_high
    )

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