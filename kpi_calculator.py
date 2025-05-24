import pandas as pd
import numpy as np
import streamlit as st
import time
import gc

@st.cache_data(ttl=3600, show_spinner=False)
def calculate_kpis(df, start_date, end_date, total_beds=None):
    """
    指定された期間のKPIを計算する統合関数
    
    Parameters:
    -----------
    df : pd.DataFrame
        分析対象のデータフレーム
    start_date : str or pd.Timestamp
        分析開始日
    end_date : str or pd.Timestamp
        分析終了日
    total_beds : int or None
        総病床数（病床利用率計算用）
        
    Returns:
    --------
    dict
        計算されたKPI値と集計データを含む辞書
    """
    start_time = time.time()
    
    # 日付の変換
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    
    # 指定期間のデータをフィルタリング
    df_filtered = df[(df['日付'] >= start_date) & (df['日付'] <= end_date)].copy()
    
    if df_filtered.empty:
        # データがない場合は空の結果を返す
        return {
            "error": "指定された期間にデータがありません。"
        }
    
    # 日数の計算
    days_count = (end_date - start_date).days + 1
    
    # 日次の集計
    daily_stats = df_filtered.groupby('日付').agg(
        日在院患者数合計=('入院患者数（在院）', 'sum'),
        日入院患者数=('入院患者数', 'sum'),
        日緊急入院患者数=('緊急入院患者数', 'sum'),
        日総入院患者数=('総入院患者数', 'sum'),
        日退院患者数=('退院患者数', 'sum'),
        日死亡患者数=('死亡患者数', 'sum'),
        日総退院患者数=('総退院患者数', 'sum')
    ).reset_index()
    
    # 期間合計の計算
    total_patient_days = daily_stats['日在院患者数合計'].sum()  # 期間延べ在院患者数
    total_admissions = daily_stats['日総入院患者数'].sum()      # 期間総入院患者数
    total_discharges = daily_stats['日総退院患者数'].sum()      # 期間総退院患者数
    total_emergency_admissions = daily_stats['日緊急入院患者数'].sum()  # 期間緊急入院患者数
    total_deaths = daily_stats['日死亡患者数'].sum()            # 期間死亡患者数
    
    # 平均値の計算
    avg_daily_census = total_patient_days / days_count if days_count > 0 else 0  # 日平均在院患者数
    avg_daily_admissions = total_admissions / days_count if days_count > 0 else 0  # 日平均入院患者数
    avg_daily_discharges = total_discharges / days_count if days_count > 0 else 0  # 日平均退院患者数
    
    # 平均在院日数 (ALOS)
    denominator_alos = (total_admissions + total_discharges) / 2
    alos = total_patient_days / denominator_alos if denominator_alos > 0 else 0
    
    # 病床回転率
    turnover_rate = total_discharges / avg_daily_census if avg_daily_census > 0 else 0
    
    # 病床利用率
    bed_occupancy_rate = None
    if total_beds is not None and total_beds > 0:
        bed_occupancy_rate = (avg_daily_census / total_beds) * 100
    
    # 緊急入院率と死亡率
    emergency_admission_rate = (total_emergency_admissions / total_admissions * 100) if total_admissions > 0 else 0
    mortality_rate = (total_deaths / total_discharges * 100) if total_discharges > 0 else 0
    
    # 病棟数と診療科数
    ward_count = df_filtered['病棟コード'].nunique()
    dept_count = df_filtered['診療科名'].nunique()
    
    # 月次集計
    df_filtered['年月'] = df_filtered['日付'].dt.to_period('M')
    monthly_stats = df_filtered.groupby('年月').agg(
        延べ在院患者数=('入院患者数（在院）', 'sum'),
        総入院患者数=('総入院患者数', 'sum'),
        総退院患者数=('総退院患者数', 'sum'),
        日付数=('日付', 'nunique')
    ).reset_index()
    
    monthly_stats['月'] = monthly_stats['年月'].astype(str)
    
    # 月別の平均在院日数
    monthly_stats['平均在院日数'] = monthly_stats.apply(
        lambda row: row['延べ在院患者数'] / ((row['総入院患者数'] + row['総退院患者数']) / 2)
        if (row['総入院患者数'] + row['総退院患者数']) > 0 else 0,
        axis=1
    )
    
    # 月別の日平均在院患者数
    monthly_stats['日平均在院患者数'] = monthly_stats.apply(
        lambda row: row['延べ在院患者数'] / row['日付数'] if row['日付数'] > 0 else 0,
        axis=1
    )
    
    # 前月比変化率の計算
    n_months = len(monthly_stats)
    current_alos = monthly_stats['平均在院日数'].iloc[-1] if n_months > 0 else 0
    
    alos_mom_change = 0
    if n_months > 1:
        prev_alos = monthly_stats['平均在院日数'].iloc[-2]
        alos_mom_change = ((current_alos - prev_alos) / prev_alos * 100) if prev_alos != 0 else 0
    
    # 曜日別集計
    weekday_data = df_filtered[df_filtered['平日判定'] == '平日']
    holiday_data = df_filtered[df_filtered['平日判定'] == '休日']
    
    weekday_stats = weekday_data.groupby('日付').agg(
        日在院患者数合計=('入院患者数（在院）', 'sum'),
        日総入院患者数=('総入院患者数', 'sum'),
        日総退院患者数=('総退院患者数', 'sum')
    ).reset_index()
    
    holiday_stats = holiday_data.groupby('日付').agg(
        日在院患者数合計=('入院患者数（在院）', 'sum'),
        日総入院患者数=('総入院患者数', 'sum'),
        日総退院患者数=('総退院患者数', 'sum')
    ).reset_index()
    
    weekday_avg_census = weekday_stats['日在院患者数合計'].mean() if not weekday_stats.empty else 0
    holiday_avg_census = holiday_stats['日在院患者数合計'].mean() if not holiday_stats.empty else 0
    
    # 週次集計（入退院バランス用）
    df_filtered['週'] = df_filtered['日付'].dt.to_period('W').astype(str)
    weekly_stats = df_filtered.groupby('週').agg(
        週入院患者数=('総入院患者数', 'sum'),
        週退院患者数=('総退院患者数', 'sum')
    ).reset_index()
    
    weekly_stats['入退院差'] = weekly_stats['週入院患者数'] - weekly_stats['週退院患者数']
    
    # 結果の組み立て
    end_time = time.time()
    processing_time = end_time - start_time
    
    return {
        # 基本KPI
        "avg_daily_census": avg_daily_census,
        "avg_daily_admissions": avg_daily_admissions,
        "avg_daily_discharges": avg_daily_discharges,
        "alos": alos,
        "turnover_rate": turnover_rate,
        "bed_occupancy_rate": bed_occupancy_rate,
        "emergency_admission_rate": emergency_admission_rate,
        "mortality_rate": mortality_rate,
        
        # 数量情報
        "ward_count": ward_count,
        "dept_count": dept_count,
        "days_count": days_count,
        "total_patient_days": total_patient_days,
        "total_admissions": total_admissions,
        "total_discharges": total_discharges,
        
        # 時系列データ
        "daily_stats": daily_stats,
        "weekly_stats": weekly_stats,
        "monthly_stats": monthly_stats,
        
        # 曜日別データ
        "weekday_avg_census": weekday_avg_census,
        "holiday_avg_census": holiday_avg_census,
        
        # 変化率
        "alos_mom_change": alos_mom_change,
        
        # その他
        "latest_date": df_filtered['日付'].max(),
        "start_date": start_date,
        "end_date": end_date,
        "processing_time": processing_time
    }

def get_kpi_status(value, good_threshold, warning_threshold, reverse=False):
    """
    KPIの状態（良好・注意・警告）を判定する
    
    Parameters:
    -----------
    value : float
        KPI値
    good_threshold : float
        良好とみなす閾値
    warning_threshold : float
        警告とみなす閾値
    reverse : bool, default False
        Trueの場合、小さい値が良いとみなす（平均在院日数など）
        
    Returns:
    --------
    str
        "good", "warning", "alert"のいずれか
    """
    if reverse:
        if value < good_threshold:
            return "good"
        elif value < warning_threshold:
            return "warning"
        else:
            return "alert"
    else:
        if value > good_threshold:
            return "good"
        elif value > warning_threshold:
            return "warning"
        else:
            return "alert"

def analyze_kpi_insights(kpi_data, total_beds):
    """
    KPIデータからインサイトを導き出す
    
    Parameters:
    -----------
    kpi_data : dict
        calculate_kpisで計算されたKPIデータ
    total_beds : int
        総病床数
        
    Returns:
    --------
    dict
        インサイトを含む辞書
    """
    insights = {
        "alos": [],
        "occupancy": [],
        "weekday_pattern": [],
        "general": []
    }
    
    # 平均在院日数に関するインサイト
    alos = kpi_data.get("alos", 0)
    alos_mom_change = kpi_data.get("alos_mom_change", 0)
    
    if alos > 0:
        if alos < 14:
            insights["alos"].append("平均在院日数は14日未満で良好な水準です。")
        elif alos < 18:
            insights["alos"].append("平均在院日数は注意すべき範囲（14日～18日）にあります。")
        else:
            insights["alos"].append("平均在院日数が18日以上と長期化しています。改善が必要かもしれません。")
    
    if abs(alos_mom_change) > 5:
        trend_text = "減少" if alos_mom_change < 0 else "増加"
        insights["alos"].append(f"平均在院日数は前月比で{abs(alos_mom_change):.1f}%{trend_text}しています。")
        
        if alos_mom_change < -5:
            insights["alos"].append("平均在院日数の大幅な減少は、病床回転率の向上につながりますが、早期退院の適切性も確認しましょう。")
        elif alos_mom_change > 5:
            insights["alos"].append("平均在院日数の増加傾向には注意が必要です。退院支援の強化や長期入院患者の見直しを検討しましょう。")
    
    # 病床利用率に関するインサイト
    occupancy_rate = kpi_data.get("bed_occupancy_rate")
    if occupancy_rate is not None:
        if occupancy_rate > 90:
            insights["occupancy"].append(f"病床利用率が{occupancy_rate:.1f}%と非常に高くなっています。患者受入に影響が出る可能性があります。")
        elif occupancy_rate > 85:
            insights["occupancy"].append(f"病床利用率は{occupancy_rate:.1f}%と適正な水準です。効率的な病床運用ができています。")
        elif occupancy_rate > 75:
            insights["occupancy"].append(f"病床利用率は{occupancy_rate:.1f}%と許容範囲内ですが、収益面での最適化の余地があります。")
        else:
            insights["occupancy"].append(f"病床利用率が{occupancy_rate:.1f}%と低めです。空床が多い状況を改善するための対策を検討しましょう。")
    
    # 平日/休日パターンに関するインサイト
    weekday_avg = kpi_data.get("weekday_avg_census", 0)
    holiday_avg = kpi_data.get("holiday_avg_census", 0)
    
    if weekday_avg > 0 and holiday_avg > 0:
        weekday_holiday_diff = (weekday_avg - holiday_avg) / weekday_avg * 100 if weekday_avg > 0 else 0
        
        if abs(weekday_holiday_diff) > 15:
            if weekday_holiday_diff > 0:
                insights["weekday_pattern"].append(f"平日と休日で在院患者数に{abs(weekday_holiday_diff):.1f}%の差があります。平日の方が多くなっています。")
                insights["weekday_pattern"].append("休日の入院受入体制や退院調整を見直すことで、平準化できる可能性があります。")
            else:
                insights["weekday_pattern"].append(f"平日と休日で在院患者数に{abs(weekday_holiday_diff):.1f}%の差があります。休日の方が多くなっています。")
                insights["weekday_pattern"].append("平日の退院促進や入院受入体制を強化することを検討しましょう。")
    
    # 全般的なインサイト
    turnover_rate = kpi_data.get("turnover_rate", 0)
    if turnover_rate > 0:
        if turnover_rate < 0.7:
            insights["general"].append(f"病床回転率が{turnover_rate:.2f}回転と低めです。在院日数の適正化や入退院の効率化を検討しましょう。")
        elif turnover_rate > 1.0:
            insights["general"].append(f"病床回転率が{turnover_rate:.2f}回転と高く、効率的な病床運用ができています。")
    
    emergency_rate = kpi_data.get("emergency_admission_rate", 0)
    if emergency_rate > 30:
        insights["general"].append(f"緊急入院の割合が{emergency_rate:.1f}%と高くなっています。計画的な入院管理が難しい状況かもしれません。")
    
    # データの質に関するインサイト
    if len(insights["alos"]) == 0 and len(insights["occupancy"]) == 0 and len(insights["weekday_pattern"]) == 0 and len(insights["general"]) == 0:
        insights["general"].append("十分なデータが集まると、より詳細な分析インサイトが表示されます。")
    
    return insights