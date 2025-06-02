# revenue_dashboard_tab.py (修正版)

import streamlit as st
import pandas as pd
# import plotly.express as px # グラフ部分が残るなら必要
# import plotly.graph_objects as go # グラフ部分が残るなら必要
# from plotly.subplots import make_subplots # グラフ部分が残るなら必要
# import numpy as np # 必要に応じて
# from datetime import datetime, timedelta # 必要に応じて
# import jpholiday # 不要なら削除
from utils import safe_date_filter # 期間フィルターに必要

# dashboard_overview_tab からKPI表示関数をインポート
try:
    from dashboard_overview_tab import display_unified_metrics_layout_colorized, format_number_with_config
except ImportError:
    display_unified_metrics_layout_colorized = None
    format_number_with_config = None # フォールバック

# config.py から定数をインポート
from config import DEFAULT_TOTAL_BEDS, DEFAULT_OCCUPANCY_RATE, DEFAULT_ADMISSION_FEE, DEFAULT_TARGET_PATIENT_DAYS, APP_VERSION, NUMBER_FORMAT

# kpi_calculator.py からKPI計算関数をインポート
try:
    from kpi_calculator import calculate_kpis
except ImportError:
    calculate_kpis = None


def ensure_datetime_compatibility(df, date_columns=None):
    # ... (この関数は変更なし) ...
    if date_columns is None:
        date_columns = ['日付']
    df_result = df.copy()
    for col in date_columns:
        if col in df_result.columns:
            try:
                df_result[col] = pd.to_datetime(df_result[col])
            except Exception as e:
                print(f"列 '{col}' の変換に失敗: {e}")
    return df_result


def create_revenue_dashboard_section(df, targets_df=None, period_info=None):
    """
    収益管理ダッシュボードセクションの作成 (統一KPIレイアウト使用)
    """
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return

    if display_unified_metrics_layout_colorized is None or calculate_kpis is None:
        st.error("収益ダッシュボードの表示に必要な機能がインポートできませんでした。")
        return

    df = ensure_datetime_compatibility(df)

    monthly_target_patient_days = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS)
    # monthly_target_admissions = st.session_state.get('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS) # 現在のレイアウトでは直接使わない
    avg_admission_fee = st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE)
    # alert_threshold_low = st.session_state.get('alert_threshold_low', 85) # unified_metrics_layout では直接使わない
    # alert_threshold_high = st.session_state.get('alert_threshold_high', 115) # unified_metrics_layout では直接使わない
    total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)


    start_date_ts, end_date_ts = None, None
    period_description = "選択期間"

    if period_info: # app.py の get_analysis_period から渡される想定
        start_date_ts = period_info.get('start_date')
        end_date_ts = period_info.get('end_date')
        period_description = period_info.get('period_type', 'カスタム期間')
    else: # フォールバック (しかし、通常は period_info が渡されるべき)
        # unified_filters から取得することを試みる
        from unified_filters import get_unified_filter_config # ここでインポート
        filter_config = get_unified_filter_config()
        if filter_config and 'start_date' in filter_config and 'end_date' in filter_config:
            start_date_ts = pd.Timestamp(filter_config['start_date']).normalize()
            end_date_ts = pd.Timestamp(filter_config['end_date']).normalize()
            if filter_config.get('period_mode') == "プリセット期間" and filter_config.get('preset'):
                period_description = filter_config['preset']
            else:
                period_description = f"{start_date_ts.strftime('%Y/%m/%d')}～{end_date_ts.strftime('%Y/%m/%d')}"
        else:
            st.error("分析期間が特定できません。")
            return

    if start_date_ts is None or end_date_ts is None:
        st.error("分析期間が正しく設定されていません。")
        return

    df_filtered = safe_date_filter(df, start_date_ts, end_date_ts)

    if df_filtered.empty:
        st.warning(f"指定された期間 ({period_description}) にデータがありません。")
        return

    st.subheader(f"💰 収益管理ダッシュボード - {period_description}")

    # ----- KPI計算と表示 -----
    kpis_selected = calculate_kpis(df_filtered, start_date_ts, end_date_ts, total_beds=total_beds)

    if not kpis_selected or kpis_selected.get("error"):
        st.warning(f"選択期間のKPI計算に失敗: {kpis_selected.get('error', '不明') if kpis_selected else '不明'}")
        return

    # 「直近30日」のKPIも計算
    latest_date_in_df = df['日付'].max() # 元のdfの最新日
    start_30d = latest_date_in_df - pd.Timedelta(days=29)
    end_30d = latest_date_in_df
    df_30d = safe_date_filter(df, start_30d, end_30d) # 元のdfから30日分をフィルタ
    kpis_30d = calculate_kpis(df_30d, start_30d, end_30d, total_beds=total_beds) if not df_30d.empty else {}


    metrics_for_display = {
        'avg_daily_census': kpis_selected.get('avg_daily_census'),
        'avg_daily_census_30d': kpis_30d.get('avg_daily_census'),
        'bed_occupancy_rate': kpis_selected.get('bed_occupancy_rate'),
        'avg_los': kpis_selected.get('alos'),
        'estimated_revenue': kpis_selected.get('total_patient_days', 0) * avg_admission_fee,
        'total_patient_days': kpis_selected.get('total_patient_days'),
        'avg_daily_admissions': kpis_selected.get('avg_daily_admissions'),
        'period_days': kpis_selected.get('days_count'),
        'total_beds': total_beds,
    }
    display_unified_metrics_layout_colorized(metrics_for_display, period_description)
    # ----- KPI表示ここまで -----


    # ===== グラフ表示 (既存のロジックを流用または調整) =====
    # このセクションは、もし収益タブでKPIカード以外のグラフも表示したい場合に調整する
    # st.markdown("---")
    # try:
        # # 月別集計 (既存のコードを参考に)
        # df_filtered['年月'] = df_filtered['日付'].dt.to_period('M')
        # census_col = '入院患者数（在院）' # or dynamic detection
        # admission_col = '総入院患者数' # or dynamic detection
        #
        # agg_dict = {census_col: 'mean'}
        # if admission_col in df_filtered.columns: agg_dict[admission_col] = 'sum'
        # if '延べ在院日数' not in df_filtered.columns and census_col in df_filtered.columns : # 延べ在院日数がなければ計算
        #     df_filtered['延べ在院日数'] = df_filtered[census_col] # 簡易的に在院患者数を延べ日数として扱う
        # if '延べ在院日数' in df_filtered.columns: agg_dict['延べ在院日数'] = 'sum'
        #
        # monthly_summary = df_filtered.groupby('年月').agg(agg_dict).reset_index()
        # monthly_summary = monthly_summary.rename(columns={census_col: '日平均在院患者数'})


        # if not monthly_summary.empty:
        #     col1_graph, col2_graph = st.columns(2)
        #     with col1_graph:
        #         # from dashboard_overview_tab import create_monthly_trend_chart (もし使うなら)
        #         # fig_trend = create_monthly_trend_chart_for_revenue(monthly_summary, monthly_target_patient_days, kpis_selected.get('avg_daily_admissions',0)) # 仮の関数名
        #         # st.plotly_chart(fig_trend, use_container_width=True)
        #         st.info("収益タブ用トレンドグラフはここに表示されます（実装待ち）")
        #     with col2_graph:
        #         # fig_revenue = create_revenue_trend_chart_for_revenue(monthly_summary, monthly_target_patient_days, avg_admission_fee) # 仮の関数名
        #         # st.plotly_chart(fig_revenue, use_container_width=True)
        #         st.info("収益タブ用収益トレンドグラフはここに表示されます（実装待ち）")
        # else:
        #     st.info("グラフを表示するための月次データがありません。")

    # except Exception as e:
    #     st.error(f"収益ダッシュボードのグラフ生成中にエラー: {e}")
    #     import traceback
    #     st.error(traceback.format_exc())

    # 診療科別分析や詳細テーブルも、もし収益タブで必要なら同様に
    # display_unified_metrics_layout_colorized が期待する形式でデータを準備し、
    # 適切な表示関数を呼び出す形になります。
    # 今回はKPIカードの統一が主目的なので、グラフ以下の部分はコメントアウトしています。

# create_kpi_card, create_monthly_trend_chart などのローカル定義は削除 (共通関数へ移行したため)
# display_alerts も display_unified_metrics_layout_colorized に統合されるか、別途呼び出し