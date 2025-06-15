import streamlit as st
import pandas as pd
import logging
from datetime import datetime
import calendar

logger = logging.getLogger(__name__)

try:
    from utils import safe_date_filter, get_ward_display_name, create_ward_name_mapping
    from unified_filters import get_unified_filter_config
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.stop()

def get_period_dates(df, period_type):
    """
    期間タイプに基づいて開始日と終了日を計算
    """
    if df is None or df.empty or '日付' not in df.columns:
        return None, None, "データなし"
    
    max_date = df['日付'].max()
    min_date = df['日付'].min()
    
    if period_type == "直近4週間":
        start_date = max_date - pd.Timedelta(days=27)
        desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    
    elif period_type == "直近8週":
        start_date = max_date - pd.Timedelta(days=55)
        desc = f"直近8週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    
    elif period_type == "直近12週":
        start_date = max_date - pd.Timedelta(days=83)
        desc = f"直近12週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    
    elif period_type == "今年度":
        # 4月始まりの年度
        year = max_date.year if max_date.month >= 4 else max_date.year - 1
        start_date = pd.Timestamp(year=year, month=4, day=1)
        # 年度末または最新データまで
        end_of_fiscal = pd.Timestamp(year=year+1, month=3, day=31)
        end_date = min(end_of_fiscal, max_date)
        desc = f"今年度 ({start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%m/%d')})"
        return max(start_date, min_date), end_date, desc
    
    elif period_type == "先月":
        # 最新データの前月
        if max_date.month == 1:
            year = max_date.year - 1
            month = 12
        else:
            year = max_date.year
            month = max_date.month - 1
        
        start_date = pd.Timestamp(year=year, month=month, day=1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = pd.Timestamp(year=year, month=month, day=last_day)
        
        # データ範囲内に収める
        if end_date > max_date:
            end_date = max_date
        if start_date < min_date:
            start_date = min_date
            
        desc = f"{year}年{month}月 ({start_date.strftime('%m/%d')}～{end_date.strftime('%m/%d')})"
        return start_date, end_date, desc
    
    elif period_type == "昨年度":
        # 前年度（4月～3月）
        current_year = max_date.year if max_date.month >= 4 else max_date.year - 1
        prev_year = current_year - 1
        start_date = pd.Timestamp(year=prev_year, month=4, day=1)
        end_date = pd.Timestamp(year=current_year, month=3, day=31)
        
        # データ範囲内に収める
        if end_date > max_date:
            end_date = max_date
        if start_date < min_date:
            start_date = min_date
            
        desc = f"{prev_year}年度 ({start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')})"
        return start_date, end_date, desc
    
    else:
        # デフォルトは直近4週間
        start_date = max_date - pd.Timedelta(days=27)
        desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    
    # データ範囲内に収める
    start_date = max(start_date, min_date)
    return start_date, max_date, desc

def get_target_values_for_ward(target_data, ward_code, ward_name=None):
    """
    病棟コードまたは病棟名で目標値を取得
    """
    targets = {
        'daily_census_target': None,
        'weekly_admissions_target': None,
        'avg_los_target': None,
        'bed_count': None,  # 病棟の病床数
        'display_name': ward_code  # デフォルトは病棟コード
    }
    
    if target_data is None or target_data.empty:
        return targets
    
    try:
        # まず病棟コードで検索（部門種別が「病棟」のレコードのみ）
        if '部門種別' in target_data.columns:
            ward_targets = target_data[
                (target_data['部門コード'] == ward_code) & 
                (target_data['部門種別'] == '病棟')
            ]
        else:
            ward_targets = target_data[target_data['部門コード'] == ward_code]
        
        # 病棟コードで見つからない場合、部門名でも検索
        if ward_targets.empty and '部門名' in target_data.columns:
            if '部門種別' in target_data.columns:
                ward_targets = target_data[
                    ((target_data['部門名'] == ward_code) | 
                     (target_data['部門名'] == ward_name) |
                     (target_data['部門名'].str.contains(ward_code, na=False)) |
                     (target_data['部門名'].str.contains(ward_name, na=False) if ward_name else False)) &
                    (target_data['部門種別'] == '病棟')
                ]
            else:
                ward_targets = target_data[
                    (target_data['部門名'] == ward_code) | 
                    (target_data['部門名'] == ward_name) |
                    (target_data['部門名'].str.contains(ward_code, na=False)) |
                    (target_data['部門名'].str.contains(ward_name, na=False) if ward_name else False)
                ]
        
        if not ward_targets.empty:
            # 目標値ファイルの部門名を表示名として使用
            if '部門名' in ward_targets.columns:
                display_name = ward_targets.iloc[0]['部門名']
                targets['display_name'] = display_name
            
            # 病床数の取得（もしあれば）
            if '病床数' in ward_targets.columns:
                bed_count = ward_targets.iloc[0]['病床数']
                if pd.notna(bed_count):
                    targets['bed_count'] = int(bed_count)
            
            for _, row in ward_targets.iterrows():
                indicator_type = str(row.get('指標タイプ', '')).strip()
                target_value = row.get('目標値', None)
                
                if indicator_type == '日平均在院患者数':
                    targets['daily_census_target'] = target_value
                elif indicator_type == '週間新入院患者数':
                    targets['weekly_admissions_target'] = target_value
                elif indicator_type == '平均在院日数':
                    targets['avg_los_target'] = target_value
        else:
            logger.warning(f"病棟の目標値が見つかりません - 病棟コード: {ward_code}")
            
    except Exception as e:
        logger.error(f"病棟目標値取得エラー ({ward_code}): {e}")
    
    return targets

def calculate_ward_kpis(df, target_data, ward_code, ward_name, start_date, end_date, ward_col):
    try:
        # 病棟でフィルタリング
        ward_df = df[df[ward_col] == ward_code]
        period_df = safe_date_filter(ward_df, start_date, end_date)
        
        if period_df.empty:
            return None
        
        total_days = (end_date - start_date).days + 1
        total_patient_days = period_df['在院患者数'].sum() if '在院患者数' in period_df.columns else 0
        total_admissions = period_df['新入院患者数'].sum() if '新入院患者数' in period_df.columns else 0
        total_discharges = period_df['退院患者数'].sum() if '退院患者数' in period_df.columns else 0
        
        daily_avg_census = total_patient_days / total_days if total_days > 0 else 0
        
        # 直近週の計算
        recent_week_end = end_date
        recent_week_start = end_date - pd.Timedelta(days=6)
        recent_week_df = safe_date_filter(ward_df, recent_week_start, recent_week_end)
        recent_week_patient_days = recent_week_df['在院患者数'].sum() if '在院患者数' in recent_week_df.columns and not recent_week_df.empty else 0
        recent_week_admissions = recent_week_df['新入院患者数'].sum() if '新入院患者数' in recent_week_df.columns and not recent_week_df.empty else 0
        recent_week_discharges = recent_week_df['退院患者数'].sum() if '退院患者数' in recent_week_df.columns and not recent_week_df.empty else 0
        recent_week_daily_census = recent_week_patient_days / 7 if recent_week_patient_days > 0 else 0
        
        avg_length_of_stay = total_patient_days / total_discharges if total_discharges > 0 else 0
        recent_week_avg_los = recent_week_patient_days / recent_week_discharges if recent_week_discharges > 0 else 0
        
        weekly_avg_admissions = (total_admissions / total_days) * 7 if total_days > 0 else 0
        
        # 目標値の取得
        targets = get_target_values_for_ward(target_data, ward_code, ward_name)
        
        # 達成率の計算
        daily_census_achievement = (daily_avg_census / targets['daily_census_target'] * 100) if targets['daily_census_target'] else 0
        weekly_admissions_achievement = (weekly_avg_admissions / targets['weekly_admissions_target'] * 100) if targets['weekly_admissions_target'] else 0
        los_achievement = (targets['avg_los_target'] / avg_length_of_stay * 100) if targets['avg_los_target'] and avg_length_of_stay else 0
        
        # 病床稼働率の計算（病床数がある場合）
        bed_occupancy_rate = None
        if targets['bed_count'] and targets['bed_count'] > 0:
            bed_occupancy_rate = (daily_avg_census / targets['bed_count']) * 100
        
        return {
            'ward_code': ward_code,
            'ward_name': targets['display_name'],  # 表示名を使用
            'daily_avg_census': daily_avg_census,
            'recent_week_daily_census': recent_week_daily_census,
            'daily_census_target': targets['daily_census_target'],
            'daily_census_achievement': daily_census_achievement,
            'weekly_avg_admissions': weekly_avg_admissions,
            'recent_week_admissions': recent_week_admissions,
            'weekly_admissions_target': targets['weekly_admissions_target'],
            'weekly_admissions_achievement': weekly_admissions_achievement,
            'avg_length_of_stay': avg_length_of_stay,
            'recent_week_avg_los': recent_week_avg_los,
            'avg_los_target': targets['avg_los_target'],
            'avg_los_achievement': los_achievement,
            'bed_count': targets['bed_count'],
            'bed_occupancy_rate': bed_occupancy_rate
        }
    except Exception as e:
        logger.error(f"病棟KPI計算エラー ({ward_code}): {e}", exc_info=True)
        return None

def get_color(val):
    if val >= 100:
        return "#22a350"
    elif val >= 80:
        return "#f6c700"
    else:
        return "#d53a3a"

def render_metric_card(label, period_avg, recent, target, achievement, unit, card_color, bed_info=None):
    ach_str = f"{achievement:.1f}%" if achievement or achievement == 0 else "--"
    ach_label = "達成率:"
    target_color = "#b3b9b3" if not target or target == '--' else "#7b8a7a"
    
    # 病床情報の追加（病床数と稼働率）
    bed_info_html = ""
    if bed_info and bed_info['bed_count']:
        occupancy_str = f"{bed_info['occupancy_rate']:.1f}%" if bed_info['occupancy_rate'] is not None else "--"
        bed_info_html = f"""
        <div style="margin-top:4px; padding-top:4px; border-top:1px solid #e0e0e0;">
            <div style="display:flex; justify-content:space-between;">
                <span style="font-size:0.85em; color:#999;">病床数:</span>
                <span style="font-size:0.9em; color:#666;">{bed_info['bed_count']}床</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="font-size:0.85em; color:#999;">稼働率:</span>
                <span style="font-size:0.9em; font-weight:600; color:#666;">{occupancy_str}</span>
            </div>
        </div>
        """
    
    return f"""
    <div style="
        background: {card_color}0E;
        border-radius: 11px;
        border-left: 6px solid {card_color};
        margin-bottom: 12px;
        padding: 12px 16px 7px 16px;
        min-height: 1px;
        ">
        <div style="font-size:1.13em; font-weight:700; margin-bottom:7px; color:#293a27;">{label}</div>
        <div style="display:flex; flex-direction:column; gap:2px;">
            <div style="display:flex; justify-content:space-between;">
                <span style="font-size:0.93em; color:#7b8a7a;">期間平均:</span>
                <span style="font-size:1.07em; font-weight:700; color:#2e3532;">{period_avg} {unit}</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="font-size:0.93em; color:#7b8a7a;">直近週実績:</span>
                <span style="font-size:1.07em; font-weight:700; color:#2e3532;">{recent} {unit}</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
                <span style="font-size:0.93em; color:#7b8a7a;">目標:</span>
                <span style="font-size:1.07em; font-weight:700; color:{target_color};">{target if target else '--'} {unit}</span>
            </div>
        </div>
        <div style="margin-top:7px; display:flex; justify-content:space-between; align-items:center;">
          <div style="font-weight:700; font-size:1.03em; color:{card_color};">{ach_label}</div>
          <div style="font-weight:700; font-size:1.20em; color:{card_color};">{ach_str}</div>
        </div>
        {bed_info_html}
    </div>
    """

def display_ward_performance_dashboard():
    st.header("🏨 病棟別パフォーマンスダッシュボード")

    if not st.session_state.get('data_processed', False):
        st.warning("データを読み込み後に利用可能になります。")
        return
    
    df_original = st.session_state['df']
    target_data = st.session_state.get('target_data', pd.DataFrame())
    
    # 病棟マッピングを初期化
    if not st.session_state.get('ward_mapping_initialized', False):
        create_ward_name_mapping(df_original, target_data)
    
    # 期間選択と指標選択を横に並べる
    col1, col2 = st.columns(2)
    
    with col1:
        period_options = ["直近4週間", "直近8週", "直近12週", "今年度", "先月", "昨年度"]
        selected_period = st.selectbox(
            "📅 集計期間",
            period_options,
            index=0,
            key="ward_performance_period"
        )
    
    with col2:
        metric_options = ["日平均在院患者数", "週合計新入院患者数", "平均在院日数"]
        selected_metric = st.selectbox(
            "📊 表示指標",
            metric_options,
            index=0,
            key="ward_performance_metric"
        )
    
    # 選択された期間に基づいて日付を計算
    start_date, end_date, period_desc = get_period_dates(df_original, selected_period)
    
    if start_date is None or end_date is None:
        st.error("期間の計算に失敗しました。データを確認してください。")
        return
    
    date_filtered_df = safe_date_filter(df_original, start_date, end_date)
    
    if date_filtered_df.empty:
        st.warning(f"選択された期間（{period_desc}）にデータがありません。")
        return
    
    possible_cols = ['病棟コード', '病棟名', '病棟']
    ward_col = next((c for c in possible_cols if c in date_filtered_df.columns), None)
    if ward_col is None:
        st.error(f"病棟列が見つかりません。期待する列: {possible_cols}")
        return

    # 病棟のユニークなリストを取得
    unique_wards = date_filtered_df[ward_col].unique()
    ward_kpis = []
    
    for ward_code in unique_wards:
        ward_name = get_ward_display_name(ward_code)
        kpi = calculate_ward_kpis(
            date_filtered_df, target_data, ward_code, ward_name, 
            start_date, end_date, ward_col
        )
        if kpi:
            ward_kpis.append(kpi)
    
    if not ward_kpis:
        st.warning("表示可能な病棟データがありません。")
        return

    # 指標の詳細設定
    metric_opts = {
        "日平均在院患者数": {
            "avg": "daily_avg_census", "recent": "recent_week_daily_census",
            "target": "daily_census_target", "ach": "daily_census_achievement", "unit": "人"
        },
        "週合計新入院患者数": {
            "avg": "weekly_avg_admissions", "recent": "recent_week_admissions",
            "target": "weekly_admissions_target", "ach": "weekly_admissions_achievement", "unit": "件"
        },
        "平均在院日数": {
            "avg": "avg_length_of_stay", "recent": "recent_week_avg_los",
            "target": "avg_los_target", "ach": "avg_los_achievement", "unit": "日"
        }
    }
    opt = metric_opts[selected_metric]

    # ソート（達成率降順 or 在院日数のみ昇順）
    rev = False if selected_metric == "平均在院日数" else True
    ward_kpis.sort(key=lambda x: x.get(opt["ach"], 0), reverse=rev)

    st.markdown(f"### 📈 **{period_desc}** の病棟別パフォーマンス（{selected_metric}）")
    
    # パフォーマンスカードの表示
    cols = st.columns(3)
    for idx, kpi in enumerate(ward_kpis):
        avg = kpi.get(opt["avg"], 0)
        recent = kpi.get(opt["recent"], 0)
        target = kpi.get(opt["target"], None)
        ach = kpi.get(opt["ach"], 0)
        color = get_color(ach)
        avg_disp = f"{avg:.1f}" if avg or avg == 0 else "--"
        recent_disp = f"{recent:.1f}" if recent or recent == 0 else "--"
        target_disp = f"{target:.1f}" if target else "--"
        
        # 病床情報（日平均在院患者数の場合のみ表示）
        bed_info = None
        if selected_metric == "日平均在院患者数" and kpi.get('bed_count'):
            bed_info = {
                'bed_count': kpi['bed_count'],
                'occupancy_rate': kpi.get('bed_occupancy_rate')
            }
        
        html = render_metric_card(
            label=kpi["ward_name"],
            period_avg=avg_disp,
            recent=recent_disp,
            target=target_disp,
            achievement=ach,
            unit=opt["unit"],
            card_color=color,
            bed_info=bed_info
        )
        with cols[idx % 3]:
            st.markdown(html, unsafe_allow_html=True)
            
    # デバッグ開始
    unique_wards = date_filtered_df[ward_col].unique()
    
    # デバッグ情報の表示
    with st.expander("🔍 デバッグ情報", expanded=True):
        st.write("実データの病棟コード一覧:", sorted(unique_wards))
        
        # 各病棟のKPI計算をデバッグ
        debug_info = []
        for ward_code in unique_wards:
            ward_name = get_ward_display_name(ward_code)
            targets = get_target_values_for_ward(target_data, ward_code, ward_name)
            
            # 期間内の新入院患者数を確認
            ward_df = date_filtered_df[date_filtered_df[ward_col] == ward_code]
            period_df = safe_date_filter(ward_df, start_date, end_date)
            weekly_admissions = period_df['新入院患者数'].sum() / ((end_date - start_date).days + 1) * 7 if not period_df.empty else 0
            
            debug_info.append({
                '病棟コード': ward_code,
                '表示名': targets['display_name'],
                '週間新入院実績': round(weekly_admissions, 1),
                '週間新入院目標': targets['weekly_admissions_target'],
                '達成率': round((weekly_admissions / targets['weekly_admissions_target'] * 100) if targets['weekly_admissions_target'] else 0, 1)
            })
        
        st.dataframe(pd.DataFrame(debug_info))
    
    ward_kpis = []
    # デバッグ修了
    
    # ダウンロードボタン
    html_cards = ""
    for kpi in ward_kpis:
        avg = kpi.get(opt["avg"], 0)
        recent = kpi.get(opt["recent"], 0)
        target = kpi.get(opt["target"], None)
        ach = kpi.get(opt["ach"], 0)
        color = get_color(ach)
        avg_disp = f"{avg:.1f}" if avg or avg == 0 else "--"
        recent_disp = f"{recent:.1f}" if recent or recent == 0 else "--"
        target_disp = f"{target:.1f}" if target else "--"
        
        bed_info = None
        if selected_metric == "日平均在院患者数" and kpi.get('bed_count'):
            bed_info = {
                'bed_count': kpi['bed_count'],
                'occupancy_rate': kpi.get('bed_occupancy_rate')
            }
        
        html_cards += render_metric_card(
            label=kpi["ward_name"],
            period_avg=avg_disp,
            recent=recent_disp,
            target=target_disp,
            achievement=ach,
            unit=opt["unit"],
            card_color=color,
            bed_info=bed_info
        )
    
    dl_html = f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="UTF-8"><title>病棟別 {selected_metric} パフォーマンス - {period_desc}</title></head>
<body style="background:#f5f7fa; font-family: 'Noto Sans JP', Meiryo, sans-serif;">
<h2>{selected_metric} 病棟別パフォーマンス - {period_desc}</h2>
{html_cards}
</body></html>
"""
    st.download_button(
        label=f"{selected_metric}のパフォーマンスをHTMLダウンロード",
        data=dl_html.encode("utf-8"),
        file_name=f"ward_{selected_metric}_performance_{selected_period}.html",
        mime="text/html"
    )

def create_ward_performance_tab():
    display_ward_performance_dashboard()