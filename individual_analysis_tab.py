# individual_analysis_tab.py (修正版 - 重複コード削除)

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
        st.dataframe(df_data.fillna('-'), use_container_width=True)
    else:
        st.markdown(f"##### {title}")
        st.warning(f"{title} データがありません。")

def display_individual_analysis_tab(df_filtered_main):
    st.header("📊 個別分析")

    if not all([generate_filtered_summaries, create_forecast_dataframe, create_interactive_patient_chart,
                create_interactive_dual_axis_chart, get_display_name_for_dept,
                get_unified_filter_summary, get_unified_filter_config]):
        st.error("個別分析タブの実行に必要な機能の一部が読み込めませんでした。アプリケーションのログを確認し、インポートエラーを解決してください。")
        return

    df = df_filtered_main
    # 除外病棟をフィルタリング
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

# =================================================================
    # 統一フィルター範囲全体での分析（選択機能削除）
    # =================================================================
    current_filter_title_display = "統一フィルター適用範囲全体" if unified_filter_applied else "全体"
    current_results_data = all_results
    chart_data_for_graphs = df.copy()

    # 統一フィルターから選択された部門を取得
    filter_code_for_target = None  # 初期値をNoneに
    filter_config = get_unified_filter_config() if get_unified_filter_config else {}

    if filter_config:
        # 診療科が選択されている場合
        if filter_config.get('selected_departments') and len(filter_config['selected_departments']) == 1:
            # 単一診療科の場合、その診療科コードを使用
            selected_dept = filter_config['selected_departments'][0]
            filter_code_for_target = selected_dept
            current_filter_title_display = f"診療科: {get_display_name_for_dept(selected_dept)}"

        # 病棟が選択されている場合
        elif filter_config.get('selected_wards') and len(filter_config['selected_wards']) == 1:
            # 単一病棟の場合、その病棟コードを使用
            selected_ward = filter_config['selected_wards'][0]
            filter_code_for_target = selected_ward
            current_filter_title_display = f"病棟: {selected_ward}" # 病棟は表示名関数がない前提

    # 部門が特定されていない場合は全体を対象とする
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
        if target_data is not None and not target_data.empty and \
           all(col in target_data.columns for col in ['部門コード', '区分', '目標値']):
            if '_target_dict' not in st.session_state:
                st.session_state._target_dict = {}
                for _, row in target_data.iterrows():
                    st.session_state._target_dict[(str(row['部門コード']), str(row['区分']))] = row['目標値']

            if filter_code_for_target == "全体":
                target_val_all = st.session_state._target_dict.get(("000", '全日'))
                target_val_weekday = st.session_state._target_dict.get(("000", '平日'))
                target_val_holiday = st.session_state._target_dict.get(("000", '休日'))
            else:
                target_val_all = st.session_state._target_dict.get((str(filter_code_for_target), '全日'))
                target_val_weekday = st.session_state._target_dict.get((str(filter_code_for_target), '平日'))
                target_val_holiday = st.session_state._target_dict.get((str(filter_code_for_target), '休日'))

            # 目標値を確実に数値型に変換
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
                st.write(f"- 検索キー: `{filter_code_for_target}`")
                st.write(f"- 全日目標値: `{target_val_all}` (型: {type(target_val_all).__name__})")
                st.write(f"- 平日目標値: `{target_val_weekday}` (型: {type(target_val_weekday).__name__})")
                st.write(f"- 休日目標値: `{target_val_holiday}` (型: {type(target_val_holiday).__name__})")
                if filter_code_for_target == "全体" and '_target_dict' in st.session_state:
                    st.write("---")
                    st.write("**_target_dict['000']の詳細:**")
                    for key, value in st.session_state._target_dict.items():
                        if key[0] == "000":
                            st.write(f"- `{key}`: `{value}` (型: {type(value).__name__})")

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