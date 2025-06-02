# table_generator.py
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta
import time
import re # 病棟コードのパターンマッチング用

def get_fiscal_year_info(date_val: pd.Timestamp):
    """
    指定された日付に基づいて、現在の会計年度の開始日・終了日(実績データに基づく)、
    および前年度の開始日・終了日を返す。
    日本の会計年度 (4月1日始まり、翌年3月31日終わり) を想定。
    """
    current_year_start_month = 4
    if date_val.month < current_year_start_month:
        current_fiscal_year_start = pd.Timestamp(year=date_val.year - 1, month=current_year_start_month, day=1)
    else:
        current_fiscal_year_start = pd.Timestamp(year=date_val.year, month=current_year_start_month, day=1)
    current_fiscal_year_end_for_data = date_val
    previous_fiscal_year_start = current_fiscal_year_start - pd.DateOffset(years=1)
    previous_fiscal_year_end = current_fiscal_year_start - timedelta(days=1)
    return current_fiscal_year_start, current_fiscal_year_end_for_data, previous_fiscal_year_start, previous_fiscal_year_end

@st.cache_data(ttl=3600, show_spinner=False)
def generate_department_table(
    df: pd.DataFrame,
    department_type: str,
    start_date: datetime,
    end_date: datetime,
    display_mode: str = 'basic',
    sort_by: str = 'code',
    target_data_df: pd.DataFrame = None,
    included_departments: list = None # 主に診療科テーブルのサイドバー選択用
):
    total_processing_start_time = time.time()

    if df is None or df.empty:
        return pd.DataFrame()

    df_filtered_for_analysis_period = df[
        (df['日付'] >= pd.to_datetime(start_date)) &
        (df['日付'] <= pd.to_datetime(end_date))
    ].copy()

    if df_filtered_for_analysis_period.empty:
        st.info(f"指定された分析期間 ({pd.to_datetime(start_date).strftime('%Y-%m-%d')} ~ {pd.to_datetime(end_date).strftime('%Y-%m-%d')}) にデータがありません。")
        return pd.DataFrame()

    group_col = '病棟コード' if department_type == 'ward' else '診療科名'
    
    # --- 表示対象部門の絞り込み ---
    unique_depts_from_actual_data = sorted(df_filtered_for_analysis_period[group_col].unique())
    
    if department_type == 'ward':
        if target_data_df is not None and not target_data_df.empty and \
           '部門コード' in target_data_df.columns and '部門種別' in target_data_df.columns:
            # 目標CSVから「病棟」と特定できる部門コードのリストを取得
            target_ward_codes = target_data_df[
                target_data_df['部門種別'].astype(str).str.strip() == '病棟'
            ]['部門コード'].astype(str).unique()
            
            if len(target_ward_codes) > 0:
                # 実績データに存在する病棟コードのうち、目標CSVにも存在する病棟コードに絞り込む
                unique_depts_codes = [
                    wd for wd in unique_depts_from_actual_data if wd in target_ward_codes
                ]
                if not unique_depts_codes and unique_depts_from_actual_data:
                    st.info("目標値CSVに記載のある病棟が、選択された期間の実績データに見つかりませんでした。実績データ内の全ての病棟を表示します。")
                    unique_depts_codes = unique_depts_from_actual_data
                elif not unique_depts_codes and not unique_depts_from_actual_data:
                     st.info("表示対象の病棟データがありません。")
                     return pd.DataFrame()
            else: # 目標CSVに病棟の定義がない場合
                st.warning("目標値CSVに「部門種別」が「病棟」として定義されているデータがありません。実績データ内の全ての病棟を表示します。")
                unique_depts_codes = unique_depts_from_actual_data
        else: # 目標値CSVがない、または必要な列がない場合
            st.info("目標値ファイルが未提供または形式が不備のため、実績データ内の全ての病棟を表示します。")
            unique_depts_codes = unique_depts_from_actual_data
    
    elif department_type == 'clinical':
        if included_departments: # サイドバーで診療科が選択されている場合
            unique_depts_codes = [
                dept for dept in unique_depts_from_actual_data if dept in included_departments
            ]
        else: # サイドバーで「すべての診療科」が選択されているか、選択リストが空の場合
              # この場合、目標CSVにリストされている診療科に絞るか、全て表示するかは要件による。
              # 今回は「診療科はそのような仕様になっていると思います」とのことから、
              # サイドバー設定（included_departments）を優先し、それがなければ全実績診療科とする。
              # 目標CSVによる絞り込みを診療科にも適用したい場合は、病棟と同様のロジックを追加する。
            unique_depts_codes = unique_depts_from_actual_data
    else:
        unique_depts_codes = unique_depts_from_actual_data


    if not unique_depts_codes:
        st.info("表示対象の部門データが見つかりません。")
        return pd.DataFrame()

    # --- 以降の集計期間の定義、指標計算、DataFrame整形、ソートのロジックは前回提案の通り ---
    latest_data_date_in_df = df_filtered_for_analysis_period['日付'].max()
    current_fy_start, current_fy_end_for_data, prev_fy_start, prev_fy_end = get_fiscal_year_info(latest_data_date_in_df)

    periods = {
        "直近7日": (latest_data_date_in_df - timedelta(days=6), latest_data_date_in_df),
        "直近14日": (latest_data_date_in_df - timedelta(days=13), latest_data_date_in_df),
        "直近30日": (latest_data_date_in_df - timedelta(days=29), latest_data_date_in_df),
        "直近60日": (latest_data_date_in_df - timedelta(days=59), latest_data_date_in_df),
        "今年度平均": (current_fy_start, current_fy_end_for_data),
        "前年度平均": (prev_fy_start, prev_fy_end),
    }
    period_names_ordered_detailed = ["直近7日", "直近14日", "直近30日", "直近60日", "今年度平均", "前年度平均"]
    period_name_for_basic_and_achievement = "直近30日" 

    all_dept_metrics_list = []

    for dept_code_value in unique_depts_codes: # 絞り込まれた部門リストでループ
        dept_df_for_calc = df_filtered_for_analysis_period[df_filtered_for_analysis_period[group_col] == dept_code_value]
        if dept_df_for_calc.empty: continue

        current_dept_metrics = {'部門コード': dept_code_value}
        dept_patient_count_target = np.nan 

        if target_data_df is not None and not target_data_df.empty:
            target_row_df = target_data_df[target_data_df['部門コード'].astype(str) == str(dept_code_value)]
            if not target_row_df.empty:
                # 「患者数目標値」の取得: 区分='全日' の '目標値' を使用
                target_row_all_day = target_row_df[target_row_df['区分'].astype(str).str.strip() == '全日']
                if not target_row_all_day.empty and '目標値' in target_row_all_day.columns and pd.notna(target_row_all_day['目標値'].iloc[0]):
                    dept_patient_count_target = target_row_all_day['目標値'].iloc[0]
                # もし '全日' がない場合のフォールバック (区分を問わず最初の行の目標値)
                elif '目標値' in target_row_df.columns and pd.notna(target_row_df['目標値'].iloc[0]):
                    # 区分がALOSや利用率専用でないことを確認するようなロジックがより良い
                    first_target_kubun = str(target_row_df['区分'].iloc[0]) if '区分' in target_row_df.columns and pd.notna(target_row_df['区分'].iloc[0]) else ""
                    if "ALOS" not in first_target_kubun.upper() and "利用率" not in first_target_kubun:
                         dept_patient_count_target = target_row_df['目標値'].iloc[0]


        for period_label, (p_start, p_end) in periods.items():
            actual_p_start = max(pd.to_datetime(p_start), df_filtered_for_analysis_period['日付'].min())
            actual_p_end = min(pd.to_datetime(p_end), latest_data_date_in_df)

            if actual_p_start > actual_p_end:
                current_dept_metrics[f'平均在院患者数 ({period_label})'] = np.nan
                current_dept_metrics[f'平均在院日数 ({period_label})'] = np.nan
                continue

            period_data = dept_df_for_calc[
                (dept_df_for_calc['日付'] >= actual_p_start) &
                (dept_df_for_calc['日付'] <= actual_p_end)
            ]

            if period_data.empty:
                current_dept_metrics[f'平均在院患者数 ({period_label})'] = np.nan
                current_dept_metrics[f'平均在院日数 ({period_label})'] = np.nan
                continue

            num_days_in_actual_period = period_data['日付'].nunique()
            if '入院患者数（在院）' not in period_data.columns: continue 

            total_patient_days_p = period_data['入院患者数（在院）'].sum()
            total_admissions_p = period_data['総入院患者数'].sum() if '総入院患者数' in period_data else 0
            total_discharges_p = period_data['総退院患者数'].sum() if '総退院患者数' in period_data else 0
            
            avg_daily_census_p = total_patient_days_p / num_days_in_actual_period if num_days_in_actual_period > 0 else np.nan
            current_dept_metrics[f'平均在院患者数 ({period_label})'] = avg_daily_census_p
            
            alos_denominator_p = (total_admissions_p + total_discharges_p) / 2
            alos_p = total_patient_days_p / alos_denominator_p if alos_denominator_p > 0 else np.nan
            current_dept_metrics[f'平均在院日数 ({period_label})'] = alos_p
        
        avg_inpatients_for_achievement = current_dept_metrics.get(f'平均在院患者数 ({period_name_for_basic_and_achievement})', np.nan)
        current_dept_metrics['患者数目標値'] = dept_patient_count_target if pd.notna(dept_patient_count_target) else np.nan
        if pd.notna(avg_inpatients_for_achievement) and pd.notna(dept_patient_count_target) and dept_patient_count_target > 0:
            current_dept_metrics['患者数達成率(%)'] = (avg_inpatients_for_achievement / dept_patient_count_target) * 100
        else:
            current_dept_metrics['患者数達成率(%)'] = np.nan
            
        all_dept_metrics_list.append(current_dept_metrics)

    if not all_dept_metrics_list:
        return pd.DataFrame()

    result_df = pd.DataFrame(all_dept_metrics_list)
    
    if target_data_df is not None and not target_data_df.empty and \
       all(col in target_data_df.columns for col in ['部門コード', '部門名']):
        mapping_dict = pd.Series(target_data_df['部門名'].values, index=target_data_df['部門コード'].astype(str)).to_dict()
        result_df.insert(0, '部門', result_df['部門コード'].astype(str).map(mapping_dict).fillna(result_df['部門コード']))
        result_df = result_df.drop(columns=['部門コード'])
    else:
        result_df.rename(columns={'部門コード': '部門'}, inplace=True)

    cols_to_show = ['部門']
    if display_mode == 'basic':
        cols_to_show.extend([
            f'平均在院患者数 ({period_name_for_basic_and_achievement})',
            '患者数目標値',
            '患者数達成率(%)',
            f'平均在院日数 ({period_name_for_basic_and_achievement})'
        ])
    else: # detailed
        for metric_base_name in ['平均在院患者数', '平均在院日数']:
            for period_name_key in period_names_ordered_detailed:
                cols_to_show.append(f'{metric_base_name} ({period_name_key})')
        cols_to_show.extend(['患者数目標値', '患者数達成率(%)'])

    final_cols_to_show = [col for col in cols_to_show if col in result_df.columns]
    if not final_cols_to_show or '部門' not in final_cols_to_show:
        return pd.DataFrame()
    result_df_display = result_df[final_cols_to_show]

    sort_col_actual = '部門'
    sort_ascending_actual = True
    if sort_by == 'achievement':
        if '患者数達成率(%)' in result_df_display.columns:
            sort_col_actual = '患者数達成率(%)'
            sort_ascending_actual = False 
    elif sort_by == 'patients':
        patient_col_for_sort = f'平均在院患者数 ({period_name_for_basic_and_achievement})'
        if patient_col_for_sort in result_df_display.columns:
            sort_col_actual = patient_col_for_sort
            sort_ascending_actual = False

    if sort_col_actual in result_df_display.columns:
        result_df_display = result_df_display.sort_values(
            by=sort_col_actual, ascending=sort_ascending_actual, na_position='last'
        )
    else:
        result_df_display = result_df_display.sort_values(by='部門', ascending=True)
    
    total_processing_end_time = time.time()
    print(f"generate_department_table for {department_type} took {total_processing_end_time - total_processing_start_time:.2f}s")

    return result_df_display.set_index('部門')
