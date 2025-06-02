# individual_analysis_tab.py (修正版 - 個別PDF出力機能削除)

import streamlit as st
import pandas as pd
# import hashlib # このファイルでは直接使用されていないようですが、元のコードにあったため残します
# from datetime import datetime # このファイルでは直接使用されていないようですが、元のコードにあったため残します
import logging

logger = logging.getLogger(__name__)

try:
    from forecast import generate_filtered_summaries, create_forecast_dataframe
    from chart import create_interactive_patient_chart, create_interactive_dual_axis_chart
    # from pdf_generator import create_pdf, create_landscape_pdf # PDF個別出力削除のためコメントアウト
    from utils import get_display_name_for_dept
    from unified_filters import get_unified_filter_summary, get_unified_filter_config
except ImportError as e:
    logger.error(f"個別分析タブに必要なモジュールのインポートに失敗: {e}", exc_info=True)
    st.error(f"個別分析タブに必要なモジュールのインポートに失敗しました: {e}")
    st.error("関連モジュール (forecast.py, chart.py, utils.py, unified_filters.py) が正しい場所に配置されているか、またはそれらのモジュール内でエラーが発生していないか確認してください。") # pdf_generator をメッセージから削除
    generate_filtered_summaries = None
    create_forecast_dataframe = None
    create_interactive_patient_chart = None
    create_interactive_dual_axis_chart = None
    # create_pdf = None # 削除
    # create_landscape_pdf = None # 削除
    get_display_name_for_dept = None
    get_unified_filter_summary = None
    get_unified_filter_config = None

def display_dataframe_with_title(title, df_data, key_suffix=""):
    if df_data is not None and not df_data.empty:
        st.markdown(f"##### {title}")
        st.dataframe(df_data.fillna('-'), use_container_width=True)
    else:
        st.markdown(f"##### {title}")
        st.warning(f"{title} データがありません。")

def _clear_session_state_key(key_to_delete): # この関数はPDF出力がなくなれば不要になる可能性
    if key_to_delete in st.session_state:
        del st.session_state[key_to_delete]

def display_individual_analysis_tab(df_filtered_main):
    st.header("📊 個別分析")

    # PDF関連の関数がインポートリストから 빠져도 all() のチェックは問題ない
    if not all([generate_filtered_summaries, create_forecast_dataframe, create_interactive_patient_chart,
                create_interactive_dual_axis_chart, # create_pdf, create_landscape_pdf を削除
                get_display_name_for_dept, get_unified_filter_summary, get_unified_filter_config]):
        st.error("個別分析タブの実行に必要な機能の一部が読み込めませんでした。アプリケーションのログを確認し、インポートエラーを解決してください。")
        return

    df = df_filtered_main
    target_data = st.session_state.get('target_data')
    all_results = st.session_state.get('all_results')
    latest_data_date_str_from_session = st.session_state.get('latest_data_date_str', pd.Timestamp.now().strftime("%Y年%m月%d日"))
    unified_filter_applied = st.session_state.get('unified_filter_applied', False)

    if df is None or df.empty:
        st.error("分析対象のデータフレームが読み込まれていません。「データ処理」タブを再実行するか、フィルター条件を見直してください。")
        return

    if unified_filter_applied and get_unified_filter_summary:
        filter_summary = get_unified_filter_summary()
        st.info(f"🔍 適用中のフィルター: {filter_summary}")
        st.success(f"📊 フィルター適用後データ: {len(df):,}行")
    else:
        st.info("📊 全データでの個別分析（注意：統一フィルターは未適用または不明）")

    if all_results is None:
        if generate_filtered_summaries:
            logger.warning("個別分析: st.session_state.all_results が未設定のため、渡されたdfから再生成します。")
            all_results = generate_filtered_summaries(df, None, None)
            st.session_state.all_results = all_results
            if not all_results:
                st.error("「全体（フィルター適用後）」の集計データが生成できませんでした。")
                return
        else:
            st.error("「全体」の集計データがありません。また、集計関数も利用できません。")
            return

    try:
        if not df.empty and '日付' in df.columns:
            latest_data_date_from_df = df['日付'].max()
            latest_data_date = pd.Timestamp(latest_data_date_from_df).normalize()
        else:
            latest_data_date = pd.to_datetime(latest_data_date_str_from_session, format="%Y年%m月%d日").normalize()
        logger.info(f"個別分析: 予測基準日として {latest_data_date.strftime('%Y-%m-%d')} を使用します。")
    except Exception as e:
        logger.error(f"最新データ日付の処理中にエラー: {e}", exc_info=True)
        st.error(f"最新データ日付の処理中にエラーが発生しました。予測基準日として本日の日付を使用します。")
        latest_data_date = pd.Timestamp.now().normalize()

    st.markdown("---")
    if unified_filter_applied:
        st.markdown("#### 🔍 詳細フィルター（統一フィルター結果内での細分化）")
    else:
        st.markdown("#### 🔍 分析対象選択")

    unique_depts = sorted(df["診療科名"].astype(str).unique()) if "診療科名" in df.columns and not df['診療科名'].empty else []
    unique_wards = sorted(df["病棟コード"].astype(str).unique()) if "病棟コード" in df.columns and not df['病棟コード'].empty else []

    col1_filter, col2_filter = st.columns([1, 2])

    with col1_filter:
        filter_type_options = ["全体"]
        if unique_depts: filter_type_options.append("診療科別")
        if unique_wards: filter_type_options.append("病棟別")
        default_filter_type = "全体"
        try:
            current_filter_type_index = filter_type_options.index(st.session_state.get('ind_filter_type', default_filter_type))
        except ValueError:
            current_filter_type_index = 0
        filter_type = st.radio(
            "分析単位", filter_type_options, index=current_filter_type_index, key="ind_filter_type_radio_final"
        )
        st.session_state.ind_filter_type = filter_type

    filter_value_actual = "全体"
    filter_value_display = "全体"

    with col2_filter:
        if filter_type == "診療科別":
            dept_display_options_map = {"全体": "全体"}
            if get_display_name_for_dept:
                for dept_code in unique_depts:
                    dept_display_options_map[get_display_name_for_dept(dept_code, dept_code)] = dept_code
            else:
                for dept_code in unique_depts: dept_display_options_map[dept_code] = dept_code
            sorted_dept_display_names = ["全体"] + sorted([k for k in dept_display_options_map.keys() if k != "全体"])
            current_dept_display = st.session_state.get('ind_dept_select_display', "全体")
            if current_dept_display not in sorted_dept_display_names: current_dept_display = "全体"
            try:
                current_dept_idx = sorted_dept_display_names.index(current_dept_display)
            except ValueError: current_dept_idx = 0
            filter_value_display = st.selectbox(
                "診療科を選択", sorted_dept_display_names, index=current_dept_idx, key="ind_dept_select_sb_final"
            )
            st.session_state.ind_dept_select_display = filter_value_display
            filter_value_actual = dept_display_options_map.get(filter_value_display, "全体")

        elif filter_type == "病棟別":
            from utils import get_ward_display_name
            ward_display_options_map = {"全体": "全体"}
            if get_ward_display_name:
                 for ward_code in unique_wards:
                    ward_display_options_map[get_ward_display_name(ward_code)] = ward_code
            else:
                for ward_code in unique_wards: ward_display_options_map[ward_code] = ward_code
            sorted_ward_display_names = ["全体"] + sorted([k for k in ward_display_options_map.keys() if k != "全体"])
            current_ward_display = st.session_state.get('ind_ward_select_display', "全体")
            if current_ward_display not in sorted_ward_display_names: current_ward_display = "全体"
            try:
                current_ward_idx = sorted_ward_display_names.index(current_ward_display)
            except ValueError: current_ward_idx = 0
            filter_value_display = st.selectbox(
                "病棟を選択", sorted_ward_display_names, index=current_ward_idx, key="ind_ward_select_sb_final"
            )
            st.session_state.ind_ward_select_display = filter_value_display
            filter_value_actual = ward_display_options_map.get(filter_value_display, "全体")
        else:
            st.write(" ")

    current_filter_title_display = "全体"
    current_results_data = all_results
    chart_data_for_graphs = df.copy()
    filter_code_for_target = "全体"

    if filter_type == "全体" or filter_value_actual == "全体":
        current_filter_title_display = "全体（統一フィルター適用済み）" if unified_filter_applied else "全体"
    elif filter_type == "診療科別":
        current_filter_title_display = f"診療科: {filter_value_display}"
        if unified_filter_applied: current_filter_title_display += "（統一フィルター範囲内）"
        filter_code_for_target = filter_value_actual
        current_results_data = generate_filtered_summaries(df, "診療科名", filter_value_actual) if generate_filtered_summaries else None
        chart_data_for_graphs = df[df["診療科名"] == filter_value_actual] if "診療科名" in df.columns and not df.empty else pd.DataFrame()
    elif filter_type == "病棟別":
        current_filter_title_display = f"病棟: {filter_value_display}"
        if unified_filter_applied: current_filter_title_display += "（統一フィルター範囲内）"
        filter_code_for_target = filter_value_actual
        current_results_data = generate_filtered_summaries(df, "病棟コード", filter_value_actual) if generate_filtered_summaries else None
        chart_data_for_graphs = df[df["病棟コード"] == filter_value_actual] if "病棟コード" in df.columns and not df.empty else pd.DataFrame()

    if not current_results_data or not isinstance(current_results_data, dict) or current_results_data.get("summary") is None:
        st.warning(f"「{current_filter_title_display}」には表示できる集計データがありません。")
    else:
        st.markdown(f"#### 分析結果: {current_filter_title_display}")

        selected_days_for_graph = 90
        # pdf_graph_days_to_use = selected_days_for_graph # PDF出力削除のため不要

        if chart_data_for_graphs is not None and not chart_data_for_graphs.empty:
            data_period_info = ""
            min_date_chart_obj = None
            max_date_chart_obj = None
            if '日付' in chart_data_for_graphs.columns and not chart_data_for_graphs['日付'].empty:
                min_date_chart_obj = chart_data_for_graphs['日付'].min()
                max_date_chart_obj = chart_data_for_graphs['日付'].max()
                data_period_info = f"期間: {min_date_chart_obj.date()} ～ {max_date_chart_obj.date()}"
            st.info(f"📊 対象データ: {len(chart_data_for_graphs):,}行　{data_period_info}")

            if min_date_chart_obj and max_date_chart_obj:
                calculated_days = (max_date_chart_obj - min_date_chart_obj).days + 1
                if calculated_days > 0 :
                    selected_days_for_graph = calculated_days
            if min_date_chart_obj and max_date_chart_obj:
                 st.markdown(f"##### グラフ表示期間: フィルター適用期間全体 ({min_date_chart_obj.strftime('%Y/%m/%d')} - {max_date_chart_obj.strftime('%Y/%m/%d')}, {selected_days_for_graph}日間)")
            else:
                st.markdown(f"##### グラフ表示期間: フィルター適用期間全体 ({selected_days_for_graph}日間)")
            # pdf_graph_days_to_use = selected_days_for_graph # PDF出力削除のため不要

            target_val_all, target_val_weekday, target_val_holiday = None, None, None
            if target_data is not None and not target_data.empty and \
               all(col in target_data.columns for col in ['部門コード', '区分', '目標値']):
                if '_target_dict' not in st.session_state:
                    st.session_state._target_dict = {}
                    for _, row in target_data.iterrows():
                        st.session_state._target_dict[(str(row['部門コード']), str(row['区分']))] = row['目標値']
                target_val_all = st.session_state._target_dict.get((str(filter_code_for_target), '全日'))
                target_val_weekday = st.session_state._target_dict.get((str(filter_code_for_target), '平日'))
                target_val_holiday = st.session_state._target_dict.get((str(filter_code_for_target), '休日'))

            graph_tab1, graph_tab2 = st.tabs(["📈 入院患者数推移", "📊 複合指標推移（二軸）"])

            with graph_tab1:
                if create_interactive_patient_chart:
                    st.markdown("##### 全日 入院患者数推移")
                    try:
                        fig_all_ind = create_interactive_patient_chart(
                            chart_data_for_graphs, title=f"{current_filter_title_display} 全日", days=selected_days_for_graph, target_value=target_val_all, chart_type="全日"
                        )
                        if fig_all_ind: st.plotly_chart(fig_all_ind, use_container_width=True)
                        else: st.warning("全日グラフの生成に失敗しました。")
                    except Exception as e:
                        logger.error(f"全日グラフ作成エラー: {e}", exc_info=True)
                        st.error(f"全日グラフの作成中にエラーが発生しました: {e}")

                    if "平日判定" in chart_data_for_graphs.columns:
                        weekday_data_ind = chart_data_for_graphs[chart_data_for_graphs["平日判定"] == "平日"]
                        holiday_data_ind = chart_data_for_graphs[chart_data_for_graphs["平日判定"] == "休日"]
                        st.markdown("##### 平日 入院患者数推移")
                        try:
                            fig_weekday_ind = create_interactive_patient_chart(
                                weekday_data_ind, title=f"{current_filter_title_display} 平日", days=selected_days_for_graph, show_moving_average=False, target_value=target_val_weekday, chart_type="平日"
                            )
                            if fig_weekday_ind: st.plotly_chart(fig_weekday_ind, use_container_width=True)
                            else: st.warning("平日グラフの生成に失敗しました。")
                        except Exception as e:
                            logger.error(f"平日グラフ作成エラー: {e}", exc_info=True)
                            st.error(f"平日グラフの作成中にエラーが発生しました: {e}")
                        st.markdown("##### 休日 入院患者数推移")
                        try:
                            fig_holiday_ind = create_interactive_patient_chart(
                                holiday_data_ind, title=f"{current_filter_title_display} 休日", days=selected_days_for_graph, show_moving_average=False, target_value=target_val_holiday, chart_type="休日"
                            )
                            if fig_holiday_ind: st.plotly_chart(fig_holiday_ind, use_container_width=True)
                            else: st.warning("休日グラフの生成に失敗しました。")
                        except Exception as e:
                            logger.error(f"休日グラフ作成エラー: {e}", exc_info=True)
                            st.error(f"休日グラフの作成中にエラーが発生しました: {e}")
                else:
                    st.warning("グラフ生成関数 (create_interactive_patient_chart) が利用できません。")

            with graph_tab2:
                if create_interactive_dual_axis_chart:
                    st.markdown("##### 入院患者数と患者移動の推移（7日移動平均）")
                    try:
                        fig_dual_ind = create_interactive_dual_axis_chart(
                            chart_data_for_graphs, title=f"{current_filter_title_display} 患者数と移動", days=selected_days_for_graph
                        )
                        if fig_dual_ind: st.plotly_chart(fig_dual_ind, use_container_width=True)
                        else: st.warning("複合グラフの生成に失敗しました。")
                    except Exception as e:
                        logger.error(f"複合グラフ作成エラー: {e}", exc_info=True)
                        st.error(f"複合グラフの作成中にエラーが発生しました: {e}")
                else:
                    st.warning("グラフ生成関数 (create_interactive_dual_axis_chart) が利用できません。")
        else:
            st.warning("グラフを表示するためのデータがありません。")

        st.markdown("##### 在院患者数予測")
        if create_forecast_dataframe and current_results_data and \
            current_results_data.get("summary") is not None and \
            current_results_data.get("weekday") is not None and \
            current_results_data.get("holiday") is not None:
            try:
                forecast_df_ind = create_forecast_dataframe(
                    current_results_data.get("summary"), current_results_data.get("weekday"), current_results_data.get("holiday"), latest_data_date
                )
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
            st.warning("予測データフレーム作成関数または必要な集計データ (全日/平日/休日平均) が不足しています。")

        display_dataframe_with_title("全日平均値（平日・休日含む）", current_results_data.get("summary") if current_results_data else None)
        display_dataframe_with_title("平日平均値", current_results_data.get("weekday") if current_results_data else None)
        display_dataframe_with_title("休日平均値", current_results_data.get("holiday") if current_results_data else None)

        with st.expander("月次平均値を見る"):
            display_dataframe_with_title("月次 全体平均", current_results_data.get("monthly_all") if current_results_data else None)
            display_dataframe_with_title("月次 平日平均", current_results_data.get("monthly_weekday") if current_results_data else None)
            display_dataframe_with_title("月次 休日平均", current_results_data.get("monthly_holiday") if current_results_data else None)

        # --- 個別PDF出力セクション全体を削除 ---
        # st.markdown("##### 個別PDF出力")
        # ... (関連する pdf_col1, pdf_col2, ボタンなどのロジック全体を削除) ...

        if unified_filter_applied and get_unified_filter_summary:
            st.markdown("---")
            filter_summary_bottom = get_unified_filter_summary()
            st.info(f"🔍 適用中のフィルター: {filter_summary_bottom}")