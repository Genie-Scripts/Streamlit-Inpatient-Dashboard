# individual_analysis_tab.py - 統一フィルター対応版

import streamlit as st
import pandas as pd
import hashlib # キャッシュキー生成用 (必要に応じて)
from datetime import datetime # latest_data_date の変換用
import logging

logger = logging.getLogger(__name__)

# 既存のモジュールから関数をインポート
# パスが通っていること、および関数が期待通りに動作することが前提です。
# 開発プランや既存コードに合わせて、モジュール名や関数名を適宜修正してください。
try:
    # forecast.py から必要な関数をインポート (または統合された新しいモジュールから)
    from forecast import generate_filtered_summaries, create_forecast_dataframe
    # chart.py から必要な関数をインポート
    from chart import create_interactive_patient_chart, create_interactive_dual_axis_chart
    # pdf_generator.py から必要な関数をインポート
    from pdf_generator import create_pdf, create_landscape_pdf
    # utils.py から必要な関数をインポート
    from utils import get_display_name_for_dept
    # 統一フィルター関連のインポート
    from unified_filters import get_unified_filter_summary, get_unified_filter_config
except ImportError as e:
    logger.error(f"個別分析タブに必要なモジュールのインポートに失敗: {e}")
    st.error(f"個別分析タブに必要なモジュールのインポートに失敗しました: {e}")
    st.error("関連モジュール (forecast.py, chart.py, pdf_generator.py, utils.py, unified_filters.py) が正しい場所に配置されているか確認してください。")
    # モジュールがなければ、以降の処理でエラーになるため、ここで停止するか、ダミー関数を定義します。
    # ここでは、主要な関数がNoneになるようにして、後続の処理でチェックします。
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

    # --- セッションステートから必要なデータを取得 ---
    if 'data_processed' not in st.session_state or not st.session_state.data_processed:
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return

    df = st.session_state.get('df')
    target_data = st.session_state.get('target_data')
    all_results = st.session_state.get('all_results')
    latest_data_date_str = st.session_state.get('latest_data_date_str', pd.Timestamp.now().strftime("%Y年%m月%d日"))

    # 統一フィルターが適用されているかチェック
    unified_filter_applied = st.session_state.get('unified_filter_applied', False)
    
    if df is None or df.empty:
        st.error("分析対象のデータフレームが読み込まれていません。「データ処理」タブを再実行してください。")
        return

    # 統一フィルター情報の表示
    if unified_filter_applied and get_unified_filter_summary:
        filter_summary = get_unified_filter_summary()
        st.info(f"🔍 適用中のフィルター: {filter_summary}")
        st.success(f"📊 フィルター適用後データ: {len(df):,}行")
    else:
        st.info("📊 全データでの個別分析")

    # 全体集計データの準備
    if all_results is None and generate_filtered_summaries:
        st.info("「全体」の集計データを生成します。")
        st.session_state.all_results = generate_filtered_summaries(df, None, None)
        all_results = st.session_state.all_results
        if not all_results:
            st.error("「全体」の集計データが生成できませんでした。")
            return
    elif all_results is None:
        st.error("「全体」の集計データがありません。また、集計関数も利用できません。")
        return
    
    try:
        latest_data_date = pd.to_datetime(latest_data_date_str, format="%Y年%m月%d日")
    except ValueError:
        logger.warning(f"最新データ日付の形式が無効: {latest_data_date_str}")
        st.error(f"最新データ日付の形式が無効です: {latest_data_date_str}")
        latest_data_date = pd.Timestamp.now().normalize() # フォールバック

    # --- フィルターオプション ---
    # 統一フィルターが適用されている場合は、さらなる細分化フィルターを提供
    if unified_filter_applied:
        st.markdown("---")
        st.markdown("#### 🔍 詳細フィルター（統一フィルター内での細分化）")
        st.info("統一フィルターで絞り込まれたデータをさらに詳細に分析できます。")
    else:
        st.markdown("---")
        st.markdown("#### 🔍 分析対象選択")

    # 診療科と病棟の選択肢を準備（現在のデータフレームから）
    unique_depts = sorted(df["診療科名"].astype(str).unique())
    unique_wards = sorted(df["病棟コード"].astype(str).unique())
    
    # --- UI要素 ---
    col1_filter, col2_filter, col3_filter = st.columns([1,2,1])

    with col1_filter:
        # セッションステートでフィルタタイプを管理
        filter_type_options = ["全体", "診療科別", "病棟別"]
        
        # 統一フィルターが適用されている場合のデフォルト設定
        if unified_filter_applied:
            # 統一フィルターで単一の診療科または病棟が選択されている場合は自動設定
            filter_config = get_unified_filter_config() if get_unified_filter_config else {}
            if filter_config:
                if (filter_config.get('dept_filter_mode') == "特定診療科" and 
                    len(filter_config.get('selected_depts', [])) == 1):
                    default_filter_type = "診療科別"
                elif (filter_config.get('ward_filter_mode') == "特定病棟" and 
                      len(filter_config.get('selected_wards', [])) == 1):
                    default_filter_type = "病棟別"
                else:
                    default_filter_type = "全体"
            else:
                default_filter_type = "全体"
        else:
            default_filter_type = st.session_state.get('ind_filter_type', "全体")
        
        try:
            current_filter_type_index = filter_type_options.index(default_filter_type)
        except ValueError:
            current_filter_type_index = 0
        
        filter_type = st.radio(
            "分析単位",
            filter_type_options,
            index=current_filter_type_index,
            key="ind_filter_type_widget" # state更新用キー
        )
        st.session_state.ind_filter_type = filter_type # 選択をセッションに保存

    filter_value_actual = "全体"
    filter_value_display = "全体"

    with col2_filter:
        if filter_type == "診療科別":
            # 統一フィルターで既に診療科が絞り込まれている場合の処理
            available_depts_for_selection = unique_depts
            
            if unified_filter_applied:
                filter_config = get_unified_filter_config() if get_unified_filter_config else {}
                if (filter_config.get('dept_filter_mode') == "特定診療科" and 
                    filter_config.get('selected_depts')):
                    available_depts_for_selection = filter_config['selected_depts']
                    if len(available_depts_for_selection) == 1:
                        st.info(f"統一フィルターで選択済み: {available_depts_for_selection[0]}")
            
            # 診療科表示名のマッピングを作成
            sorted_dept_display_names = []
            dept_display_options_map = {"全体": "全体"}
            
            # マッピング関数を使用
            try:
                for dept_code in available_depts_for_selection:
                    if get_display_name_for_dept:
                        display_name = get_display_name_for_dept(dept_code, dept_code)
                    else:
                        display_name = dept_code
                    dept_display_options_map[display_name] = dept_code
                sorted_dept_display_names = sorted(list(dept_display_options_map.keys()))
            except Exception as e:  # Exception を明示的に捕捉
                logger.warning(f"診療科マッピングエラー: {e}")
                # 従来のマッピング方法（フォールバック）
                if target_data is not None and not target_data.empty and \
                all(col in target_data.columns for col in ['部門コード', '部門名']):
                    dept_names_dict = dict(zip(target_data['部門コード'].astype(str), target_data['部門名']))
                    for dept_code in available_depts_for_selection:
                        display_name = dept_names_dict.get(dept_code, dept_code)
                        dept_display_options_map[display_name] = dept_code
                else:
                    for dept_code in available_depts_for_selection:
                        dept_display_options_map[dept_code] = dept_code
                sorted_dept_display_names = sorted(list(dept_display_options_map.keys()))
            
            current_dept_display = st.session_state.get('ind_dept_select_display', "全体")
            if current_dept_display not in sorted_dept_display_names and sorted_dept_display_names:
                current_dept_display = sorted_dept_display_names[0]
            
            filter_value_display = st.selectbox(
                "診療科を選択",
                sorted_dept_display_names,
                index=sorted_dept_display_names.index(current_dept_display) if current_dept_display in sorted_dept_display_names else 0,
                key="ind_dept_select_widget"
            )
            st.session_state.ind_dept_select_display = filter_value_display
            filter_value_actual = dept_display_options_map.get(filter_value_display, "全体")
        
        elif filter_type == "病棟別":
            # 統一フィルターで既に病棟が絞り込まれている場合の処理
            available_wards_for_selection = unique_wards
            
            if unified_filter_applied:
                filter_config = get_unified_filter_config() if get_unified_filter_config else {}
                if (filter_config.get('ward_filter_mode') == "特定病棟" and 
                    filter_config.get('selected_wards')):
                    available_wards_for_selection = filter_config['selected_wards']
                    if len(available_wards_for_selection) == 1:
                        st.info(f"統一フィルターで選択済み: {available_wards_for_selection[0]}")
            
            # 病棟表示名のマッピングを作成
            sorted_ward_display_names = []
            ward_display_options_map = {"全体": "全体"}
            
            try:
                # 部門種別が「病棟」のもののみをフィルタリング
                ward_depts = []
                if target_data is not None and not target_data.empty:
                    # 「部門種別」列があるか確認
                    if '部門種別' in target_data.columns:
                        # 部門種別が「病棟」であるもののみを抽出
                        ward_depts = target_data[target_data['部門種別'].astype(str).str.strip() == '病棟']
                        ward_dept_codes = ward_depts['部門コード'].astype(str).unique() if '部門コード' in ward_depts.columns else []
                        
                        # 実績データの病棟コードと照合
                        for ward_code in available_wards_for_selection:
                            if ward_code in ward_dept_codes:
                                # マッチする病棟コードの部門名を取得
                                ward_row = ward_depts[ward_depts['部門コード'].astype(str) == ward_code]
                                if not ward_row.empty and '部門名' in ward_row.columns and pd.notna(ward_row['部門名'].iloc[0]):
                                    # 部門名を表示
                                    display_name = ward_row['部門名'].iloc[0]
                                    ward_display_options_map[display_name] = ward_code
                    else:
                        # 部門種別列がない場合は、部門名が明らかに病棟を示す場合のみを抽出
                        for ward_code in available_wards_for_selection:
                            ward_row = target_data[target_data['部門コード'].astype(str) == ward_code]
                            if not ward_row.empty and '部門名' in ward_row.columns and pd.notna(ward_row['部門名'].iloc[0]):
                                dept_name = ward_row['部門名'].iloc[0]
                                # 部門名に「病棟」「階」などが含まれるものを病棟とみなす
                                if '病棟' in dept_name or '階' in dept_name:
                                    ward_display_options_map[dept_name] = ward_code
                
                # 病棟が見つからなかった場合のフォールバック
                if len(ward_display_options_map) <= 1:  # "全体"のみの場合
                    logger.info("部門種別「病棟」が見つからないため、すべての病棟コードを表示します")
                    for ward_code in available_wards_for_selection:
                        ward_row = target_data[target_data['部門コード'].astype(str) == ward_code] if target_data is not None and not target_data.empty else None
                        if ward_row is not None and not ward_row.empty and '部門名' in ward_row.columns and pd.notna(ward_row['部門名'].iloc[0]):
                            # 部門名を表示
                            display_name = ward_row['部門名'].iloc[0]
                        else:
                            # 部門名がない場合はコードを表示
                            display_name = f"{ward_code}"
                        ward_display_options_map[display_name] = ward_code
                        
            except Exception as e:
                # エラーが発生した場合は単純にコードを表示
                logger.error(f"病棟マッピングエラー: {e}")
                for ward_code in available_wards_for_selection:
                    ward_display_options_map[ward_code] = ward_code
            
            # ソートした表示名リストを作成
            sorted_ward_display_names = ["全体"] + sorted([k for k in ward_display_options_map.keys() if k != "全体"])
            
            current_ward_display = st.session_state.get('ind_ward_select_display', "全体")
            if current_ward_display not in sorted_ward_display_names and sorted_ward_display_names:
                current_ward_display = sorted_ward_display_names[0]
            
            # 結果のリスト（部門種別が「病棟」のもののみ）が空でない場合のみ表示
            if len(sorted_ward_display_names) > 1:
                filter_value_display = st.selectbox(
                    "病棟を選択",
                    sorted_ward_display_names,
                    index=sorted_ward_display_names.index(current_ward_display) if current_ward_display in sorted_ward_display_names else 0,
                    key="ind_ward_select_widget"
                )
                st.session_state.ind_ward_select_display = filter_value_display
            else:
                # 病棟が見つからない場合は「全体」のみ表示
                st.warning("部門種別「病棟」のデータが見つかりません。")
                filter_value_display = "全体"
                st.session_state.ind_ward_select_display = "全体"
            
            filter_value_actual = ward_display_options_map.get(filter_value_display, "全体")
        
        else: # 全体の場合
            st.write(" ") # プレースホルダ

    # --- フィルタリングされたデータの取得と表示 ---
    current_filter_title_display = "全体"
    current_results_data = all_results
    chart_data_for_graphs = df.copy() # グラフ用データはコピーして使う
    filter_code_for_target = "全体"

    if filter_type == "全体" or filter_value_actual == "全体":
        if unified_filter_applied:
            current_filter_title_display = "全体（統一フィルター適用済み）"
        else:
            current_filter_title_display = "全体"
        # all_results は既に st.session_state にある想定
    elif filter_type == "診療科別":
        current_filter_title_display = f"診療科: {filter_value_display}"
        if unified_filter_applied:
            current_filter_title_display += "（統一フィルター適用済み）"
        filter_code_for_target = filter_value_actual
        if generate_filtered_summaries:
            current_results_data = generate_filtered_summaries(df, "診療科名", filter_value_actual)
        else:
            current_results_data = None
        chart_data_for_graphs = df[df["診療科名"] == filter_value_actual]
    elif filter_type == "病棟別":
        current_filter_title_display = f"病棟: {filter_value_display}"
        if unified_filter_applied:
            current_filter_title_display += "（統一フィルター適用済み）"
        filter_code_for_target = filter_value_actual
        if generate_filtered_summaries:
            current_results_data = generate_filtered_summaries(df, "病棟コード", filter_value_actual)
        else:
            current_results_data = None
        chart_data_for_graphs = df[df["病棟コード"] == filter_value_actual]

    if not current_results_data or not isinstance(current_results_data, dict) or current_results_data.get("summary") is None:
        st.warning(f"「{current_filter_title_display}」には表示できる集計データがありません。")
        # グラフ表示期間選択などは行わない
    else:
        st.markdown(f"#### 分析結果: {current_filter_title_display}")

        # データ概要の表示
        if chart_data_for_graphs is not None and not chart_data_for_graphs.empty:
            data_period_info = ""
            if '日付' in chart_data_for_graphs.columns:
                min_date = chart_data_for_graphs['日付'].min().date()
                max_date = chart_data_for_graphs['日付'].max().date()
                data_period_info = f"期間: {min_date} ～ {max_date}"
            
            st.info(f"📊 対象データ: {len(chart_data_for_graphs):,}行　{data_period_info}")

        display_period_options = ["直近90日間", "直近180日間"]
        selected_period_label = st.radio("グラフ表示期間", display_period_options, horizontal=True, key="ind_graph_display_period_widget")
        selected_days = 90 if selected_period_label == display_period_options[0] else 180

        # 目標値取得
        target_val_all, target_val_weekday, target_val_holiday = None, None, None
        if target_data is not None and not target_data.empty and \
           all(col in target_data.columns for col in ['部門コード', '区分', '目標値']):
            if '_target_dict' not in st.session_state: # キャッシュされた辞書がなければ作成
                st.session_state._target_dict = {}
                for _, row in target_data.iterrows():
                    key = (str(row['部門コード']), str(row['区分']))
                    st.session_state._target_dict[key] = row['目標値']
            
            target_val_all = st.session_state._target_dict.get((str(filter_code_for_target), '全日'))
            target_val_weekday = st.session_state._target_dict.get((str(filter_code_for_target), '平日'))
            target_val_holiday = st.session_state._target_dict.get((str(filter_code_for_target), '休日'))

        # グラフタブ
        graph_tab1, graph_tab2 = st.tabs(["📈 入院患者数推移", "📊 複合指標推移（二軸）"])

        with graph_tab1:
            if create_interactive_patient_chart:
                st.markdown("##### 全日 入院患者数推移")
                try:
                    fig_all_ind = create_interactive_patient_chart(
                        chart_data_for_graphs, 
                        title=f"{current_filter_title_display} 全日 入院患者数推移", 
                        days=selected_days, 
                        target_value=target_val_all, 
                        chart_type="全日"
                    )
                    if fig_all_ind: 
                        st.plotly_chart(fig_all_ind, use_container_width=True)
                    else: 
                        st.warning("全日グラフの生成に失敗しました。")
                except Exception as e:
                    logger.error(f"全日グラフ作成エラー: {e}")
                    st.error(f"全日グラフの作成中にエラーが発生しました: {e}")

                if "平日判定" in chart_data_for_graphs.columns:
                    weekday_data_ind = chart_data_for_graphs[chart_data_for_graphs["平日判定"] == "平日"]
                    holiday_data_ind = chart_data_for_graphs[chart_data_for_graphs["平日判定"] == "休日"]

                    st.markdown("##### 平日 入院患者数推移")
                    try:
                        fig_weekday_ind = create_interactive_patient_chart(
                            weekday_data_ind, 
                            title=f"{current_filter_title_display} 平日 入院患者数推移", 
                            days=selected_days, 
                            show_moving_average=False, 
                            target_value=target_val_weekday, 
                            chart_type="平日"
                        )
                        if fig_weekday_ind: 
                            st.plotly_chart(fig_weekday_ind, use_container_width=True)
                        else: 
                            st.warning("平日グラフの生成に失敗しました。")
                    except Exception as e:
                        logger.error(f"平日グラフ作成エラー: {e}")
                        st.error(f"平日グラフの作成中にエラーが発生しました: {e}")

                    st.markdown("##### 休日 入院患者数推移")
                    try:
                        fig_holiday_ind = create_interactive_patient_chart(
                            holiday_data_ind, 
                            title=f"{current_filter_title_display} 休日 入院患者数推移", 
                            days=selected_days, 
                            show_moving_average=False, 
                            target_value=target_val_holiday, 
                            chart_type="休日"
                        )
                        if fig_holiday_ind: 
                            st.plotly_chart(fig_holiday_ind, use_container_width=True)
                        else: 
                            st.warning("休日グラフの生成に失敗しました。")
                    except Exception as e:
                        logger.error(f"休日グラフ作成エラー: {e}")
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
                        days=selected_days
                    )
                    if fig_dual_ind: 
                        st.plotly_chart(fig_dual_ind, use_container_width=True)
                    else: 
                        st.warning("複合グラフの生成に失敗しました。")
                except Exception as e:
                    logger.error(f"複合グラフ作成エラー: {e}")
                    st.error(f"複合グラフの作成中にエラーが発生しました: {e}")
            else:
                st.warning("グラフ生成関数 (create_interactive_dual_axis_chart) が利用できません。")

        # --- 在院患者数予測 ---
        st.markdown("##### 在院患者数予測")
        if create_forecast_dataframe and \
            current_results_data.get("weekday") is not None and \
            current_results_data.get("holiday") is not None:
            try:
                forecast_df_ind = create_forecast_dataframe(
                    current_results_data.get("summary"),  # df_summary を渡す
                    current_results_data.get("weekday"),
                    current_results_data.get("holiday"),
                    latest_data_date  # today 引数
                )
                if forecast_df_ind is not None and not forecast_df_ind.empty:
                    display_df_ind = forecast_df_ind.copy()
                    if "年間平均人日（実績＋予測）" in display_df_ind.columns:
                        display_df_ind = display_df_ind.rename(columns={"年間平均人日（実績＋予測）": "年度予測"})
                    if "延べ予測人日" in display_df_ind.columns:
                        display_df_ind = display_df_ind.drop(columns=["延べ予測人日"])
                    st.dataframe(display_df_ind, use_container_width=True)
                else:
                    st.warning("予測データを作成できませんでした。必要な平日または休日の平均値データが不足している可能性があります。")
            except Exception as e:
                logger.error(f"予測データ作成エラー: {e}")
                st.error(f"予測データの作成中にエラーが発生しました: {e}")
        else:
            st.warning("予測データフレーム作成関数または必要な集計データ (平日/休日平均) が不足しています。")

        # --- 集計データ表示 ---
        display_dataframe_with_title("全日平均値（平日・休日含む）", current_results_data.get("summary"), "ind_summary_widget")
        display_dataframe_with_title("平日平均値", current_results_data.get("weekday"), "ind_weekday_widget")
        display_dataframe_with_title("休日平均値", current_results_data.get("holiday"), "ind_holiday_widget")
        
        with st.expander("月次平均値を見る"):
            display_dataframe_with_title("月次 全体平均", current_results_data.get("monthly_all"), "ind_monthly_all_widget")
            display_dataframe_with_title("月次 平日平均", current_results_data.get("monthly_weekday"), "ind_monthly_weekday_widget")
            display_dataframe_with_title("月次 休日平均", current_results_data.get("monthly_holiday"), "ind_monthly_holiday_widget")

        # --- 個別PDF出力 ---
        st.markdown("##### 個別PDF出力")
        pdf_col1, pdf_col2 = st.columns(2)
        
        pdf_forecast_df_data = pd.DataFrame() # 初期化
        if create_forecast_dataframe and current_results_data.get("weekday") is not None and current_results_data.get("holiday") is not None:
            try:
                pdf_forecast_df_data = create_forecast_dataframe(
                    current_results_data.get("summary"),  # df_summary を渡す
                    current_results_data.get("weekday"),
                    current_results_data.get("holiday"),
                    latest_data_date  # today 引数
                )
            except Exception as e:
                logger.error(f"PDF用予測データ作成エラー: {e}")
                pdf_forecast_df_data = pd.DataFrame()
        
        with pdf_col1:
            if create_pdf and st.button("📄 縦向きPDF出力", key="ind_single_pdf_button_widget", use_container_width=True):
                with st.spinner(f'{current_filter_title_display}の縦向きPDFを生成中...'):
                    try:
                        pdf_data_portrait = create_pdf(
                            forecast_df=pdf_forecast_df_data,
                            df_weekday=current_results_data.get("weekday"),
                            df_holiday=current_results_data.get("holiday"),
                            df_all_avg=current_results_data.get("summary"),
                            chart_data=chart_data_for_graphs,
                            title_prefix=current_filter_title_display,
                            latest_date=latest_data_date,
                            target_data=target_data, # session_stateから取得したものを渡す
                            filter_code=filter_code_for_target,
                            graph_days=[selected_days]
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
                                key="download_ind_portrait_pdf"
                            )
                        else:
                            st.error("縦向きPDFの生成に失敗しました。")
                    except Exception as e:
                        logger.error(f"縦向きPDF生成エラー: {e}")
                        st.error(f"縦向きPDFの生成中にエラーが発生しました: {e}")

        with pdf_col2:
            if create_landscape_pdf and st.button("📄 横向きPDF出力", key="ind_single_landscape_pdf_button_widget", use_container_width=True):
                with st.spinner(f'{current_filter_title_display}の横向きPDFを生成中...'):
                    try:
                        pdf_data_landscape = create_landscape_pdf(
                            forecast_df=pdf_forecast_df_data,
                            df_weekday=current_results_data.get("weekday"),
                            df_holiday=current_results_data.get("holiday"),
                            df_all_avg=current_results_data.get("summary"),
                            chart_data=chart_data_for_graphs,
                            title_prefix=current_filter_title_display,
                            latest_date=latest_data_date,
                            target_data=target_data, # session_stateから取得したものを渡す
                            filter_code=filter_code_for_target,
                            graph_days=[selected_days]
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
                                key="download_ind_landscape_pdf"
                            )
                        else:
                            st.error("横向きPDFの生成に失敗しました。")
                    except Exception as e:
                        logger.error(f"横向きPDF生成エラー: {e}")
                        st.error(f"横向きPDFの生成中にエラーが発生しました: {e}")

        # 統一フィルター情報の再表示（ページ下部）
        if unified_filter_applied and get_unified_filter_summary:
            st.markdown("---")
            filter_summary = get_unified_filter_summary()
            st.info(f"🔍 適用中のフィルター: {filter_summary}")