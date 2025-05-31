# individual_analysis_tab.py (修正版)

import streamlit as st
import pandas as pd
import hashlib # キャッシュキー生成用 (必要に応じて)
from datetime import datetime # latest_data_date の変換用
import logging

logger = logging.getLogger(__name__)

# 既存のモジュールから関数をインポート
try:
    from forecast import generate_filtered_summaries, create_forecast_dataframe
    from chart import create_interactive_patient_chart, create_interactive_dual_axis_chart # このインポートが成功することが前提
    from pdf_generator import create_pdf, create_landscape_pdf
    from utils import get_display_name_for_dept
    from unified_filters import get_unified_filter_summary, get_unified_filter_config
except ImportError as e:
    logger.error(f"個別分析タブに必要なモジュールのインポートに失敗: {e}", exc_info=True) # exc_info=True を追加
    st.error(f"個別分析タブに必要なモジュールのインポートに失敗しました: {e}")
    st.error("関連モジュール (forecast.py, chart.py, pdf_generator.py, utils.py, unified_filters.py) が正しい場所に配置されているか、またはそれらのモジュール内でエラーが発生していないか確認してください。")
    generate_filtered_summaries = None
    create_forecast_dataframe = None
    create_interactive_patient_chart = None
    create_interactive_dual_axis_chart = None
    create_pdf = None
    create_landscape_pdf = None
    get_display_name_for_dept = None
    get_unified_filter_summary = None
    get_unified_filter_config = None

def display_dataframe_with_title(title, df_data, key_suffix=""):
    """指定されたタイトルでデータフレームを表示するヘルパー関数"""
    if df_data is not None and not df_data.empty:
        st.markdown(f"##### {title}")
        st.dataframe(df_data.fillna('-'), use_container_width=True)
    else:
        st.markdown(f"##### {title}")
        st.warning(f"{title} データがありません。")

def display_individual_analysis_tab():
    """
    個別分析タブのUIとロジックを表示する関数（統一フィルター対応版）。
    必要なデータは st.session_state から取得します。
    """
    st.header("📊 個別分析")

    # 外部モジュールのインポート確認 (再度)
    if not all([generate_filtered_summaries, create_forecast_dataframe, create_interactive_patient_chart,
                create_interactive_dual_axis_chart, create_pdf, create_landscape_pdf,
                get_display_name_for_dept, get_unified_filter_summary, get_unified_filter_config]):
        st.error("個別分析タブの実行に必要な機能の一部が読み込めませんでした。アプリケーションのログを確認してください。")
        return

    if 'data_processed' not in st.session_state or not st.session_state.data_processed:
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return

    df = st.session_state.get('df')
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
            logger.warning("個別分析: all_resultsが未設定のため、フィルター済みdfから再生成します。")
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
            latest_data_date_str_for_display = latest_data_date.strftime("%Y年%m月%d日")
            logger.info(f"個別分析: フィルター済みデータ内の最新日 ({latest_data_date_str_for_display}) を予測基準日として使用します。")
        else:
            logger.warning(f"個別分析: フィルター済みdfから最新日を取得できないため、セッションのlatest_data_date_str ({latest_data_date_str_from_session}) を使用します。")
            latest_data_date = pd.to_datetime(latest_data_date_str_from_session, format="%Y年%m月%d日").normalize()
    except ValueError as ve:
        logger.error(f"最新データ日付の形式が無効です: {ve}", exc_info=True)
        st.error(f"最新データ日付の形式が無効です。予測基準日としてデフォルトの日付を使用します。")
        latest_data_date = pd.Timestamp.now().normalize()
    except Exception as e:
        logger.error(f"最新データ日付の処理中に予期せぬエラー: {e}", exc_info=True)
        st.error(f"最新データ日付の処理中にエラーが発生しました。予測基準日としてデフォルトの日付を使用します。")
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
            "分析単位",
            filter_type_options,
            index=current_filter_type_index,
            key="ind_filter_type_radio_v3" # キーを更新
        )
        st.session_state.ind_filter_type = filter_type

    filter_value_actual = "全体"
    filter_value_display = "全体"

    with col2_filter:
        if filter_type == "診療科別":
            dept_display_options_map = {"全体": "全体"}
            if get_display_name_for_dept:
                for dept_code in unique_depts:
                    display_name = get_display_name_for_dept(dept_code, dept_code)
                    dept_display_options_map[display_name] = dept_code
            else:
                for dept_code in unique_depts: dept_display_options_map[dept_code] = dept_code
            
            sorted_dept_display_names = ["全体"] + sorted([k for k in dept_display_options_map.keys() if k != "全体"])
            
            current_dept_display = st.session_state.get('ind_dept_select_display', "全体")
            if current_dept_display not in sorted_dept_display_names: current_dept_display = "全体"
            
            try:
                current_dept_idx = sorted_dept_display_names.index(current_dept_display)
            except ValueError:
                current_dept_idx = 0

            filter_value_display = st.selectbox(
                "診療科を選択",
                sorted_dept_display_names,
                index=current_dept_idx,
                key="ind_dept_select_sb_v3" # キーを更新
            )
            st.session_state.ind_dept_select_display = filter_value_display
            filter_value_actual = dept_display_options_map.get(filter_value_display, "全体")

        elif filter_type == "病棟別":
            from utils import get_ward_display_name # get_ward_display_nameは必要
            ward_display_options_map = {"全体": "全体"}
            if get_ward_display_name:
                 for ward_code in unique_wards:
                    display_name = get_ward_display_name(ward_code)
                    ward_display_options_map[display_name] = ward_code
            else:
                for ward_code in unique_wards: ward_display_options_map[ward_code] = ward_code

            sorted_ward_display_names = ["全体"] + sorted([k for k in ward_display_options_map.keys() if k != "全体"])
            
            current_ward_display = st.session_state.get('ind_ward_select_display', "全体")
            if current_ward_display not in sorted_ward_display_names: current_ward_display = "全体"

            try:
                current_ward_idx = sorted_ward_display_names.index(current_ward_display)
            except ValueError:
                current_ward_idx = 0
                
            filter_value_display = st.selectbox(
                "病棟を選択",
                sorted_ward_display_names,
                index=current_ward_idx,
                key="ind_ward_select_sb_v3" # キーを更新
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
        pdf_graph_days_to_use = selected_days_for_graph

        if chart_data_for_graphs is not None and not chart_data_for_graphs.empty:
            data_period_info = ""
            min_date_chart_obj = None
            max_date_chart_obj = None
            if '日付' in chart_data_for_graphs.columns and not chart_data_for_graphs['日付'].empty:
                min_date_chart_obj = chart_data_for_graphs['日付'].min()
                max_date_chart_obj = chart_data_for_graphs['日付'].max()
                data_period_info = f"期間: {min_date_chart_obj.date()} ～ {max_date_chart_obj.date()}"
            st.info(f"📊 対象データ: {len(chart_data_for_graphs):,}行　{data_period_info}")

            if min_date_chart_obj and max_date_chart_obj :
                calculated_days = (max_date_chart_obj - min_date_chart_obj).days + 1
                if calculated_days > 0 :
                    selected_days_for_graph = calculated_days
            
            # ラジオボタンは表示せず、フィルター適用期間全体をグラフ表示期間とする
            if min_date_chart_obj and max_date_chart_obj:
                 st.markdown(f"##### グラフ表示期間: フィルター適用期間全体 ({min_date_chart_obj.strftime('%Y/%m/%d')} - {max_date_chart_obj.strftime('%Y/%m/%d')}, {selected_days_for_graph}日間)")
            else: # 通常は通らないフォールバック
                st.markdown(f"##### グラフ表示期間: フィルター適用期間全体 ({selected_days_for_graph}日間)")
            
            pdf_graph_days_to_use = selected_days_for_graph

            target_val_all, target_val_weekday, target_val_holiday = None, None, None
            if target_data is not None and not target_data.empty and \
               all(col in target_data.columns for col in ['部門コード', '区分', '目標値']):
                if '_target_dict' not in st.session_state:
                    st.session_state._target_dict = {}
                    for _, row in target_data.iterrows():
                        key = (str(row['部門コード']), str(row['区分']))
                        st.session_state._target_dict[key] = row['目標値']
                target_val_all = st.session_state._target_dict.get((str(filter_code_for_target), '全日'))
                target_val_weekday = st.session_state._target_dict.get((str(filter_code_for_target), '平日'))
                target_val_holiday = st.session_state._target_dict.get((str(filter_code_for_target), '休日'))

            graph_tab1, graph_tab2 = st.tabs(["📈 入院患者数推移", "📊 複合指標推移（二軸）"])

            with graph_tab1:
                if create_interactive_patient_chart:
                    st.markdown("##### 全日 入院患者数推移")
                    try:
                        fig_all_ind = create_interactive_patient_chart(
                            chart_data_for_graphs,
                            title=f"{current_filter_title_display} 全日 入院患者数推移",
                            days=selected_days_for_graph,
                            target_value=target_val_all,
                            chart_type="全日"
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
                                weekday_data_ind,
                                title=f"{current_filter_title_display} 平日 入院患者数推移",
                                days=selected_days_for_graph,
                                show_moving_average=False,
                                target_value=target_val_weekday,
                                chart_type="平日"
                            )
                            if fig_weekday_ind: st.plotly_chart(fig_weekday_ind, use_container_width=True)
                            else: st.warning("平日グラフの生成に失敗しました。")
                        except Exception as e:
                            logger.error(f"平日グラフ作成エラー: {e}", exc_info=True)
                            st.error(f"平日グラフの作成中にエラーが発生しました: {e}")

                        st.markdown("##### 休日 入院患者数推移")
                        try:
                            fig_holiday_ind = create_interactive_patient_chart(
                                holiday_data_ind,
                                title=f"{current_filter_title_display} 休日 入院患者数推移",
                                days=selected_days_for_graph,
                                show_moving_average=False,
                                target_value=target_val_holiday,
                                chart_type="休日"
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
                            chart_data_for_graphs,
                            title=f"{current_filter_title_display} 入院患者数と患者移動の推移",
                            days=selected_days_for_graph
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
        if create_forecast_dataframe and \
            current_results_data and \
            current_results_data.get("summary") is not None and \
            current_results_data.get("weekday") is not None and \
            current_results_data.get("holiday") is not None:
            try:
                forecast_df_ind = create_forecast_dataframe(
                    current_results_data.get("summary"),
                    current_results_data.get("weekday"),
                    current_results_data.get("holiday"),
                    latest_data_date
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
            st.warning("予測データフレーム作成関数または必要な集計データ (平日/休日平均) が不足しています。")

        display_dataframe_with_title("全日平均値（平日・休日含む）", current_results_data.get("summary") if current_results_data else None)
        display_dataframe_with_title("平日平均値", current_results_data.get("weekday") if current_results_data else None)
        display_dataframe_with_title("休日平均値", current_results_data.get("holiday") if current_results_data else None)

        with st.expander("月次平均値を見る"):
            display_dataframe_with_title("月次 全体平均", current_results_data.get("monthly_all") if current_results_data else None)
            display_dataframe_with_title("月次 平日平均", current_results_data.get("monthly_weekday") if current_results_data else None)
            display_dataframe_with_title("月次 休日平均", current_results_data.get("monthly_holiday") if current_results_data else None)

        st.markdown("##### 個別PDF出力")
        pdf_col1, pdf_col2 = st.columns(2)

        pdf_forecast_df_data = pd.DataFrame()
        if create_forecast_dataframe and current_results_data and \
           current_results_data.get("summary") is not None and \
           current_results_data.get("weekday") is not None and \
           current_results_data.get("holiday") is not None:
            try:
                pdf_forecast_df_data = create_forecast_dataframe(
                    current_results_data.get("summary"),
                    current_results_data.get("weekday"),
                    current_results_data.get("holiday"),
                    latest_data_date
                )
            except Exception as e:
                logger.error(f"PDF用予測データ作成エラー: {e}", exc_info=True)
                pdf_forecast_df_data = pd.DataFrame()

        with pdf_col1:
            safe_filter_value = str(filter_value_actual).replace('/', '_') if filter_value_actual else "all"
            portrait_button_key = f"ind_pdf_portrait_btn_{filter_type}_{safe_filter_value}_v2" # キーを更新
            portrait_dl_button_key = f"dl_ind_portrait_pdf_{filter_type}_{safe_filter_value}_v2" # キーを更新

            if create_pdf and st.button("📄 縦向きPDF出力", key=portrait_button_key, use_container_width=True):
                if chart_data_for_graphs is None or chart_data_for_graphs.empty:
                    st.warning("PDF生成に必要なグラフデータがありません。")
                else:
                    with st.spinner(f'{current_filter_title_display}の縦向きPDFを生成中...'):
                        try:
                            pdf_data_portrait = create_pdf(
                                forecast_df=pdf_forecast_df_data,
                                df_weekday=current_results_data.get("weekday") if current_results_data else None,
                                df_holiday=current_results_data.get("holiday") if current_results_data else None,
                                df_all_avg=current_results_data.get("summary") if current_results_data else None,
                                chart_data=chart_data_for_graphs,
                                title_prefix=current_filter_title_display,
                                latest_date=latest_data_date,
                                target_data=target_data,
                                filter_code=filter_code_for_target,
                                graph_days=[pdf_graph_days_to_use] # 修正された日数を使用
                            )
                            if pdf_data_portrait:
                                date_str_pdf = latest_data_date.strftime("%Y%m%d")
                                safe_title_pdf = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in current_filter_title_display)
                                filename_pdf = f"入院患者数予測_{safe_title_pdf}_{date_str_pdf}.pdf"
                                st.download_button(
                                    label="📥 縦向きPDFをダウンロード",
                                    data=pdf_data_portrait,
                                    file_name=filename_pdf,
                                    mime="application/pdf",
                                    key=portrait_dl_button_key
                                )
                            else: st.error("縦向きPDFの生成に失敗しました。")
                        except Exception as e:
                            logger.error(f"縦向きPDF生成エラー: {e}", exc_info=True)
                            st.error(f"縦向きPDFの生成中にエラーが発生しました: {e}")

        with pdf_col2:
            landscape_button_key = f"ind_pdf_landscape_btn_{filter_type}_{safe_filter_value}_v2" # キーを更新
            landscape_dl_button_key = f"dl_ind_landscape_pdf_{filter_type}_{safe_filter_value}_v2" # キーを更新

            if create_landscape_pdf and st.button("📄 横向きPDF出力", key=landscape_button_key, use_container_width=True):
                if chart_data_for_graphs is None or chart_data_for_graphs.empty:
                    st.warning("PDF生成に必要なグラフデータがありません。")
                else:
                    with st.spinner(f'{current_filter_title_display}の横向きPDFを生成中...'):
                        try:
                            pdf_data_landscape = create_landscape_pdf(
                                forecast_df=pdf_forecast_df_data,
                                df_weekday=current_results_data.get("weekday") if current_results_data else None,
                                df_holiday=current_results_data.get("holiday") if current_results_data else None,
                                df_all_avg=current_results_data.get("summary") if current_results_data else None,
                                chart_data=chart_data_for_graphs,
                                title_prefix=current_filter_title_display,
                                latest_date=latest_data_date,
                                target_data=target_data,
                                filter_code=filter_code_for_target,
                                graph_days=[pdf_graph_days_to_use] # 修正された日数を使用
                            )
                            if pdf_data_landscape:
                                date_str_pdf_land = latest_data_date.strftime("%Y%m%d")
                                safe_title_pdf_land = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in current_filter_title_display)
                                filename_pdf_land = f"入院患者数予測_{safe_title_pdf_land}_{date_str_pdf_land}_横向き.pdf"
                                st.download_button(
                                    label="📥 横向きPDFをダウンロード",
                                    data=pdf_data_landscape,
                                    file_name=filename_pdf_land,
                                    mime="application/pdf",
                                    key=landscape_dl_button_key
                                )
                            else: st.error("横向きPDFの生成に失敗しました。")
                        except Exception as e:
                            logger.error(f"横向きPDF生成エラー: {e}", exc_info=True)
                            st.error(f"横向きPDFの生成中にエラーが発生しました: {e}")

        if unified_filter_applied and get_unified_filter_summary:
            st.markdown("---")
            filter_summary_bottom = get_unified_filter_summary()
            st.info(f"🔍 適用中のフィルター: {filter_summary_bottom}")