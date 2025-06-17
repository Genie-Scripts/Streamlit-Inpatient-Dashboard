# individual_analysis_tab.py (クラッシュバグ修正版)

import streamlit as st
import pandas as pd
import logging
from config import EXCLUDED_WARDS
logger = logging.getLogger(__name__)

try:
    from forecast import generate_filtered_summaries, create_forecast_dataframe
    from chart import create_interactive_patient_chart, create_interactive_dual_axis_chart
    from utils import get_display_name_for_dept
    from unified_filters import get_unified_filter_summary, get_unified_filter_config
except ImportError as e:
    logger.error(f"個別分析タブに必要なモジュールのインポートに失敗: {e}", exc_info=True)
    st.error(f"個別分析タブに必要なモジュールのインポートに失敗しました: {e}")
    st.error("関連モジュール (forecast.py, chart.py, utils.py, unified_filters.py) が正しい場所に配置されているか、またはそれらのモジュール内でエラーが発生していないか確認してください。")
    generate_filtered_summaries = None
    create_forecast_dataframe = None
    create_interactive_patient_chart = None
    create_interactive_dual_axis_chart = None
    get_display_name_for_dept = None
    get_unified_filter_summary = None
    get_unified_filter_config = None

def display_dataframe_with_title(title, df_data, key_suffix=""):
    if df_data is not None and not df_data.empty:
        st.markdown(f"##### {title}")
        st.dataframe(df_data, use_container_width=True)
    else:
        st.markdown(f"##### {title}")
        st.warning(f"{title} データがありません。")

def display_individual_analysis_tab(df_filtered_main):
    st.header("📊 個別分析")

    # このグラフで分析する指標名を関数の先頭で定義
    METRIC_FOR_CHART = '日平均在院患者数'

    if not all([generate_filtered_summaries, create_forecast_dataframe, create_interactive_patient_chart,
                create_interactive_dual_axis_chart, get_display_name_for_dept,
                get_unified_filter_summary, get_unified_filter_config]):
        st.error("個別分析タブの実行に必要な機能の一部が読み込めませんでした。アプリケーションのログを確認し、インポートエラーを解決してください。")
        return

    df = df_filtered_main

    if df is not None and not df.empty and '病棟コード' in df.columns and EXCLUDED_WARDS:
        df = df[~df['病棟コード'].isin(EXCLUDED_WARDS)]
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
                st.error("「統一フィルター適用範囲」の集計データが生成できませんでした。")
                return
        else:
            st.error("「統一フィルター適用範囲」の集計データがありません。また、集計関数も利用できません。")
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

    current_filter_title_display = "統一フィルター適用範囲全体" if unified_filter_applied else "全体"
    current_results_data = all_results
    chart_data_for_graphs = df.copy()

    filter_code_for_target = None
    filter_config = get_unified_filter_config() if get_unified_filter_config else {}

    if filter_config:
        if filter_config.get('selected_departments') and len(filter_config['selected_departments']) == 1:
            selected_dept_identifier = str(filter_config.get('selected_departments')[0]).strip()
            filter_code_for_target = selected_dept_identifier
            current_filter_title_display = f"診療科: {get_display_name_for_dept(selected_dept_identifier)}"
        
        elif filter_config.get('selected_wards') and len(filter_config['selected_wards']) == 1:
            selected_ward = str(filter_config['selected_wards'][0]).strip()
            filter_code_for_target = selected_ward
            current_filter_title_display = f"病棟: {selected_ward}"

    if filter_code_for_target is None:
        filter_code_for_target = "全体"

    st.markdown(f"#### 分析結果: {current_filter_title_display}")

    if not current_results_data or not isinstance(current_results_data, dict) or current_results_data.get("summary") is None:
        st.warning(f"「{current_filter_title_display}」には表示できる集計データがありません。")
        return

    selected_days_for_graph = 90

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
            if calculated_days > 0:
                selected_days_for_graph = calculated_days

        if min_date_chart_obj and max_date_chart_obj:
            st.markdown(f"##### グラフ表示期間: フィルター適用期間全体 ({min_date_chart_obj.strftime('%Y/%m/%d')} - {max_date_chart_obj.strftime('%Y/%m/%d')}, {selected_days_for_graph}日間)")
        else:
            st.markdown(f"##### グラフ表示期間: フィルター適用期間全体 ({selected_days_for_graph}日間)")

        target_val_all, target_val_weekday, target_val_holiday = None, None, None
        
        period_col_name = None
        indicator_col_name = None
        
        if target_data is not None and not target_data.empty:
            if '区分' in target_data.columns:
                period_col_name = '区分'
            elif '期間区分' in target_data.columns:
                period_col_name = '期間区分'
            
            if '指標タイプ' in target_data.columns:
                indicator_col_name = '指標タイプ'

        if target_data is not None and not target_data.empty and \
           period_col_name and indicator_col_name and \
           all(col in target_data.columns for col in ['部門コード', '目標値']):
            
            if '_target_dict' not in st.session_state:
                st.session_state._target_dict = {}
                for _, row in target_data.iterrows():
                    dept_code = str(row['部門コード']).strip()
                    indicator = str(row[indicator_col_name]).strip()
                    period = str(row[period_col_name]).strip()
                    key = (dept_code, indicator, period)
                    st.session_state._target_dict[key] = row['目標値']
            
            if filter_code_for_target == "全体":
                key_all_1 = ("000", METRIC_FOR_CHART, '全日')
                key_all_2 = ("全体", METRIC_FOR_CHART, '全日')
                target_val_all = st.session_state._target_dict.get(key_all_1, st.session_state._target_dict.get(key_all_2))
                key_weekday_1 = ("000", METRIC_FOR_CHART, '平日')
                key_weekday_2 = ("全体", METRIC_FOR_CHART, '平日')
                target_val_weekday = st.session_state._target_dict.get(key_weekday_1, st.session_state._target_dict.get(key_weekday_2))
                key_holiday_1 = ("000", METRIC_FOR_CHART, '休日')
                key_holiday_2 = ("全体", METRIC_FOR_CHART, '休日')
                target_val_holiday = st.session_state._target_dict.get(key_holiday_1, st.session_state._target_dict.get(key_holiday_2))
            else:
                key_all = (str(filter_code_for_target), METRIC_FOR_CHART, '全日')
                target_val_all = st.session_state._target_dict.get(key_all)
                key_weekday = (str(filter_code_for_target), METRIC_FOR_CHART, '平日')
                target_val_weekday = st.session_state._target_dict.get(key_weekday)
                key_holiday = (str(filter_code_for_target), METRIC_FOR_CHART, '休日')
                target_val_holiday = st.session_state._target_dict.get(key_holiday)

            if target_val_all is not None:
                try: target_val_all = float(target_val_all)
                except (ValueError, TypeError): target_val_all = None
            if target_val_weekday is not None:
                try: target_val_weekday = float(target_val_weekday)
                except (ValueError, TypeError): target_val_weekday = None
            if target_val_holiday is not None:
                try: target_val_holiday = float(target_val_holiday)
                except (ValueError, TypeError): target_val_holiday = None

        if st.checkbox("🎯 目標値設定状況を確認", key="show_target_debug_main"):
            st.markdown("---")
            st.subheader("詳細デバッグ: 目標値辞書と検索キーの比較")

            st.markdown("##### 1. プログラムが使用している検索キー")
            search_key_all = (str(filter_code_for_target), METRIC_FOR_CHART, '全日')
            st.info(f"**全日用検索キー:** `{search_key_all}`")

            if '_target_dict' in st.session_state:
                st.markdown("##### 2. 検索キーの存在チェック結果")
                if search_key_all in st.session_state._target_dict:
                    st.success(f"✅ 検索キーは目標値辞書内に **存在します**。")
                    st.write(f"取得された目標値: `{st.session_state._target_dict.get(search_key_all)}`")
                else:
                    st.error(f"❌ 検索キーは目標値辞書内に **存在しません**。")
                    st.write("**原因：** フィルターで選択された診療科名と、目標値ファイルの「部門コード」列のテキストが完全一致していません（余分なスペース等も不一致の原因となります）。")
                    st.write("**解決策：**")
                    st.write("1. 以下の「利用可能なキー」のリストから、対応する正しい「部門コード」のテキストをコピーしてください。")
                    st.write("2. 日々の実績データ（入退院クロス.csvなど）の「診療科名」列を、コピーしたテキストに修正・統一してください。")

                st.markdown("##### 3. 目標値ファイルから読み込まれた利用可能なキー（部門コード）のリスト")
                st.caption(f"指標タイプが「{METRIC_FOR_CHART}」のものに絞って表示しています。")
                
                available_keys = {k: v for k, v in st.session_state._target_dict.items() if k[1] == METRIC_FOR_CHART}
                
                if not available_keys:
                    st.warning(f"辞書内に「{METRIC_FOR_CHART}」の指標を持つキーが見つかりませんでした。")
                else:
                    key_df_data = []
                    for key, value in available_keys.items():
                        key_df_data.append({
                            "部門コード (キー)": key[0],
                            "期間区分 (キー)": key[2],
                            "目標値": value
                        })
                    key_df = pd.DataFrame(key_df_data)
                    st.dataframe(key_df, use_container_width=True)
            else:
                st.error("目標値辞書(_target_dict)が作成されていません。")

        graph_tab1, graph_tab2 = st.tabs(["📈 入院患者数推移", "📊 複合指標推移（二軸）"])
        
        with graph_tab1:
            if create_interactive_patient_chart:
                st.markdown("##### 全日 入院患者数推移")
                try:
                    fig_all_ind = create_interactive_patient_chart(
                        chart_data_for_graphs,
                        title=f"{current_filter_title_display} 全日",
                        days=selected_days_for_graph,
                        target_value=target_val_all,
                        chart_type="全日"
                    )
                    if fig_all_ind:
                        st.plotly_chart(fig_all_ind, use_container_width=True)
                    else:
                        st.warning("全日グラフの生成に失敗しました。")
                except Exception as e:
                    logger.error(f"全日グラフ作成エラー: {e}", exc_info=True)
                    st.error(f"全日グラフの作成中にエラーが発生しました: {e}")

                if "平日判定" in chart_data_for_graphs.columns:
                    weekday_data_ind = chart_data_for_graphs[chart_data_for_graphs["平日判定"] == "平日"]
                    holiday_data_ind = chart_data_for_graphs[chart_data_for_graphs["平日判定"] == "休日"]

                    st.markdown("##### 平日 入院患者数推移")
                    try:
                        fig_weekday_ind = create_interactive_patient_chart(
                            weekday_data_ind,
                            title=f"{current_filter_title_display} 平日",
                            days=selected_days_for_graph,
                            show_moving_average=False,
                            target_value=target_val_weekday,
                            chart_type="平日"
                        )
                        if fig_weekday_ind:
                            st.plotly_chart(fig_weekday_ind, use_container_width=True)
                        else:
                            st.warning("平日グラフの生成に失敗しました。")
                    except Exception as e:
                        logger.error(f"平日グラフ作成エラー: {e}", exc_info=True)
                        st.error(f"平日グラフの作成中にエラーが発生しました: {e}")

                    st.markdown("##### 休日 入院患者数推移")
                    try:
                        fig_holiday_ind = create_interactive_patient_chart(
                            holiday_data_ind,
                            title=f"{current_filter_title_display} 休日",
                            days=selected_days_for_graph,
                            show_moving_average=False,
                            target_value=target_val_holiday,
                            chart_type="休日"
                        )
                        if fig_holiday_ind:
                            st.plotly_chart(fig_holiday_ind, use_container_width=True)
                        else:
                            st.warning("休日グラフの生成に失敗しました。")
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
                        chart_data_for_graphs, title=f"{current_filter_title_display} 患者数と移動",
                        days=selected_days_for_graph
                    )
                    if fig_dual_ind:
                        st.plotly_chart(fig_dual_ind, use_container_width=True)
                    else:
                        st.warning("複合グラフの生成に失敗しました。")
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
                current_results_data.get("summary"), current_results_data.get("weekday"),
                current_results_data.get("holiday"), latest_data_date
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

    if unified_filter_applied and get_unified_filter_summary:
        st.markdown("---")
        filter_summary_bottom = get_unified_filter_summary()
        st.info(f"🔍 適用中のフィルター: {filter_summary_bottom}")