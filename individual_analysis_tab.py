# individual_analysis_tab.py (クリーンアップ・最適化・グラフ表示更新版)

import streamlit as st
import pandas as pd
import logging
from config import EXCLUDED_WARDS
import time

logger = logging.getLogger(__name__)

try:
    from forecast import generate_filtered_summaries, create_forecast_dataframe
    # ★★★ 修正箇所 ★★★: 新しいALOSグラフ関数をインポート
    from chart import create_interactive_patient_chart, create_interactive_dual_axis_chart, create_interactive_alos_chart
    from utils import get_display_name_for_dept
    from unified_filters import get_unified_filter_summary, get_unified_filter_config
except ImportError as e:
    logger.error(f"個別分析タブに必要なモジュールのインポートに失敗: {e}", exc_info=True)
    st.error(f"個別分析タブに必要なモジュールのインポートに失敗しました: {e}")
    # 関数をNoneに設定して後で条件分岐
    generate_filtered_summaries = None
    create_forecast_dataframe = None
    create_interactive_patient_chart = None
    create_interactive_dual_axis_chart = None
    create_interactive_alos_chart = None # ★★★ 追加 ★★★
    get_display_name_for_dept = None
    get_unified_filter_summary = None
    get_unified_filter_config = None

def find_department_code_in_targets_optimized(dept_name, target_dict, metric_name):
    """最適化された診療科名検索"""
    if not target_dict or not dept_name:
        return None, False
    
    dept_name_clean = str(dept_name).strip()
    
    test_key = (dept_name_clean, metric_name, '全日')
    if test_key in target_dict:
        return dept_name_clean, True
    
    relevant_keys = [key for key in target_dict.keys() if key[1] == metric_name and key[2] == '全日']
    
    for (dept_code, indicator, period), value in [(key, target_dict[key]) for key in relevant_keys]:
        if dept_name_clean in str(dept_code) or str(dept_code) in dept_name_clean:
            return str(dept_code), True
    
    import re
    dept_name_normalized = re.sub(r'[^\w]', '', dept_name_clean)
    if dept_name_normalized:
        for (dept_code, indicator, period), value in [(key, target_dict[key]) for key in relevant_keys]:
            dept_code_normalized = re.sub(r'[^\w]', '', str(dept_code))
            if dept_code_normalized and dept_name_normalized == dept_code_normalized:
                return str(dept_code), True
    
    return None, False

def display_dataframe_with_title_optimized(title, df_data, key_suffix=""):
    """最適化されたデータフレーム表示"""
    if df_data is not None and not df_data.empty:
        st.markdown(f"##### {title}")
        if len(df_data) > 100:
            st.info(f"データが多いため、最初の100行のみ表示します（全{len(df_data)}行）")
            st.dataframe(df_data.head(100), use_container_width=True)
        else:
            st.dataframe(df_data, use_container_width=True)
    else:
        st.markdown(f"##### {title}")
        st.warning(f"{title} データがありません。")

@st.cache_data(ttl=1800, show_spinner=False)
def create_target_dict_cached(target_data):
    """目標値辞書の生成（キャッシュ対応）"""
    if target_data is None or target_data.empty:
        return {}
    
    target_dict = {}
    period_col_name = '区分' if '区分' in target_data.columns else '期間区分'
    indicator_col_name = '指標タイプ'
    
    if all(col in target_data.columns for col in ['部門コード', '目標値', period_col_name, indicator_col_name]):
        for _, row in target_data.iterrows():
            dept_code = str(row['部門コード']).strip()
            indicator = str(row[indicator_col_name]).strip()
            period = str(row[period_col_name]).strip()
            key = (dept_code, indicator, period)
            target_dict[key] = row['目標値']
    
    return target_dict

def display_individual_analysis_tab(df_filtered_main):
    """個別分析タブの表示（最適化・グラフ表示更新版）"""
    st.header("📊 個別分析")

    METRIC_FOR_CHART = '日平均在院患者数'

    if not all([generate_filtered_summaries, create_forecast_dataframe, create_interactive_patient_chart,
                create_interactive_dual_axis_chart, create_interactive_alos_chart, get_display_name_for_dept,
                get_unified_filter_summary, get_unified_filter_config]):
        st.error("個別分析タブの実行に必要な機能の一部が読み込めませんでした。")
        st.info("アプリケーションを再起動するか、関連モジュールの設置を確認してください。")
        return

    df = df_filtered_main
    if df is not None and not df.empty and '病棟コード' in df.columns and EXCLUDED_WARDS:
        initial_count = len(df)
        df = df[~df['病棟コード'].isin(EXCLUDED_WARDS)]
        removed_count = initial_count - len(df)
        if removed_count > 0:
            st.info(f"除外病棟設定により{removed_count}件のレコードを除外しました。")

    if df is None or df.empty:
        st.error("分析対象のデータが読み込まれていません。")
        st.info("「データ入力」タブでデータを読み込むか、フィルター条件を見直してください。")
        return

    target_data = st.session_state.get('target_data')
    all_results = st.session_state.get('all_results')
    latest_data_date_str_from_session = st.session_state.get('latest_data_date_str', pd.Timestamp.now().strftime("%Y年%m月%d日"))
    unified_filter_applied = st.session_state.get('unified_filter_applied', False)

    if unified_filter_applied and get_unified_filter_summary:
        filter_summary = get_unified_filter_summary()
        st.info(f"🔍 適用中のフィルター: {filter_summary}")
        st.success(f"📊 フィルター適用後データ: {len(df):,}行")
    else:
        st.info("📊 全データでの個別分析")

    if all_results is None:
        if generate_filtered_summaries:
            logger.info("個別分析: 集計データを再生成中...")
            with st.spinner("集計データを生成中..."):
                start_time = time.time()
                all_results = generate_filtered_summaries(df, None, None)
                end_time = time.time()
                if end_time - start_time > 5.0:
                    st.info(f"集計処理に{end_time - start_time:.1f}秒かかりました。")
            st.session_state.all_results = all_results
            if not all_results:
                st.error("統一フィルター適用範囲の集計データが生成できませんでした。")
                return
        else:
            st.error("統一フィルター適用範囲の集計データがありません。また、集計関数も利用できません。")
            return

    try:
        if not df.empty and '日付' in df.columns:
            latest_data_date = pd.Timestamp(df['日付'].max()).normalize()
        else:
            latest_data_date = pd.to_datetime(latest_data_date_str_from_session, format="%Y年%m月%d日").normalize()
    except Exception as e:
        logger.error(f"最新データ日付の処理中にエラー: {e}", exc_info=True)
        latest_data_date = pd.Timestamp.now().normalize()

    current_filter_title_display = "統一フィルター適用範囲全体" if unified_filter_applied else "全体"
    chart_data_for_graphs = df.copy()
    filter_code_for_target = "全体"
    
    filter_config = get_unified_filter_config() if get_unified_filter_config else {}
    
    if filter_config:
        selected_departments = (filter_config.get('selected_departments', []) or filter_config.get('selected_depts', []))
        selected_wards = (filter_config.get('selected_wards', []) or filter_config.get('selected_ward', []))
        
        if selected_departments and len(selected_departments) == 1:
            selected_dept_identifier = str(selected_departments[0]).strip()
            filter_code_for_target = selected_dept_identifier
            display_name = get_display_name_for_dept(selected_dept_identifier) if get_display_name_for_dept else selected_dept_identifier
            current_filter_title_display = f"診療科: {display_name}"
        elif selected_wards and len(selected_wards) == 1:
            selected_ward = str(selected_wards[0]).strip()
            filter_code_for_target = selected_ward
            current_filter_title_display = f"病棟: {selected_ward}"

    st.markdown(f"#### 分析対象: {current_filter_title_display}")

    if not all_results or not isinstance(all_results, dict) or all_results.get("summary") is None:
        st.warning(f"「{current_filter_title_display}」には表示できる集計データがありません。")
        return

    # ★★★ 修正箇所: グラフ表示部分を刷新 ★★★
    st.markdown("---")
    st.subheader("主要指標グラフ")
    graph_days = 90 # 表示日数を90日に固定

    # 1. 平均在院日数推移グラフ
    with st.container():
        st.markdown(f"##### 平均在院日数推移（{graph_days}日間）")
        if create_interactive_alos_chart and chart_data_for_graphs is not None and not chart_data_for_graphs.empty:
            fig_alos = create_interactive_alos_chart(chart_data_for_graphs, title="", days_to_show=graph_days)
            if fig_alos:
                st.plotly_chart(fig_alos, use_container_width=True)
            else:
                st.warning("平均在院日数グラフの生成に失敗しました。")
        else:
            st.warning("平均在院日数グラフの生成に必要なデータまたは関数がありません。")

    # 2. 全日 入院患者数推移グラフ
    with st.container():
        st.markdown(f"##### 入院患者数推移（{graph_days}日間）")
        if create_interactive_patient_chart and chart_data_for_graphs is not None and not chart_data_for_graphs.empty:
            # 目標値の取得
            target_val_all = None
            if target_data is not None and not target_data.empty:
                if '_target_dict_cached' not in st.session_state:
                    st.session_state._target_dict_cached = create_target_dict_cached(target_data)
                target_dict = st.session_state._target_dict_cached
                key = (filter_code_for_target, METRIC_FOR_CHART, '全日')
                if key in target_dict:
                    target_val_all = float(target_dict[key])

            fig_patient = create_interactive_patient_chart(chart_data_for_graphs, title="", days=graph_days, target_value=target_val_all)
            if fig_patient:
                st.plotly_chart(fig_patient, use_container_width=True)
            else:
                st.warning("入院患者数グラフの生成に失敗しました。")
        else:
            st.warning("入院患者数グラフの生成に必要なデータまたは関数がありません。")

    # 3. 患者移動推移グラフ
    with st.container():
        st.markdown(f"##### 患者移動推移（{graph_days}日間）")
        if create_interactive_dual_axis_chart and chart_data_for_graphs is not None and not chart_data_for_graphs.empty:
            fig_dual = create_interactive_dual_axis_chart(chart_data_for_graphs, title="", days=graph_days)
            if fig_dual:
                st.plotly_chart(fig_dual, use_container_width=True)
            else:
                st.warning("患者移動グラフの生成に失敗しました。")
        else:
            st.warning("患者移動グラフの生成に必要なデータまたは関数がありません。")

    # 予測データ表示
    st.markdown("---")
    st.subheader("在院患者数予測")
    if create_forecast_dataframe and all_results:
        summary_data = all_results.get("summary")
        weekday_data = all_results.get("weekday") 
        holiday_data = all_results.get("holiday")
        
        if all([summary_data is not None, weekday_data is not None, holiday_data is not None]):
            try:
                with st.spinner("予測データを生成中..."):
                    forecast_df_ind = create_forecast_dataframe(summary_data, weekday_data, holiday_data, latest_data_date)
                
                if forecast_df_ind is not None and not forecast_df_ind.empty:
                    display_df_ind = forecast_df_ind.copy()
                    if "年間平均人日（実績＋予測）" in display_df_ind.columns:
                        display_df_ind = display_df_ind.rename(columns={"年間平均人日（実績＋予測）": "年度予測"})
                    if "延べ予測人日" in display_df_ind.columns:
                        display_df_ind = display_df_ind.drop(columns=["延べ予測人日"])
                    st.dataframe(display_df_ind, use_container_width=True)
                else:
                    st.warning("予測データを作成できませんでした。")
            except Exception as e:
                logger.error(f"予測データ作成エラー: {e}", exc_info=True)
                st.error(f"予測データの作成中にエラーが発生しました: {e}")
        else:
            st.warning("予測に必要な集計データが不足しています。")
    else:
        st.warning("予測データフレーム作成関数が利用できません。")

    # 集計データ表示（エクスパンダーで整理）
    with st.expander("📊 詳細集計データ", expanded=False):
        display_dataframe_with_title_optimized("全日平均値（平日・休日含む）", all_results.get("summary"))
        display_dataframe_with_title_optimized("平日平均値", all_results.get("weekday"))
        display_dataframe_with_title_optimized("休日平均値", all_results.get("holiday"))

    with st.expander("📅 月次平均値", expanded=False):
        display_dataframe_with_title_optimized("月次 全体平均", all_results.get("monthly_all"))
        display_dataframe_with_title_optimized("月次 平日平均", all_results.get("monthly_weekday"))
        display_dataframe_with_title_optimized("月次 休日平均", all_results.get("monthly_holiday"))

def create_individual_analysis_section(df_filtered, filter_config_from_caller):
    """個別分析セクション作成（analysis_tabs.pyから呼び出される）"""
    display_individual_analysis_tab(df_filtered)