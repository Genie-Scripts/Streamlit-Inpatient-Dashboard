# individual_analysis_tab.py (クリーンアップ・最適化版)

import streamlit as st
import pandas as pd
import logging
from config import EXCLUDED_WARDS
import time

logger = logging.getLogger(__name__)

try:
    from forecast import generate_filtered_summaries, create_forecast_dataframe
    from chart import create_interactive_patient_chart, create_interactive_dual_axis_chart
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
    get_display_name_for_dept = None
    get_unified_filter_summary = None
    get_unified_filter_config = None

def find_department_code_in_targets_optimized(dept_name, target_dict, metric_name):
    """最適化された診療科名検索"""
    if not target_dict or not dept_name:
        return None, False
    
    dept_name_clean = str(dept_name).strip()
    
    # 1. 直接一致（最も高速）
    test_key = (dept_name_clean, metric_name, '全日')
    if test_key in target_dict:
        return dept_name_clean, True
    
    # 2. キーの事前フィルタリングで高速化
    relevant_keys = [key for key in target_dict.keys() if key[1] == metric_name and key[2] == '全日']
    
    # 3. 部分一致
    for (dept_code, indicator, period), value in [(key, target_dict[key]) for key in relevant_keys]:
        if dept_name_clean in str(dept_code) or str(dept_code) in dept_name_clean:
            return str(dept_code), True
    
    # 4. 正規化一致（最も重い処理なので最後）
    import re
    dept_name_normalized = re.sub(r'[^\w]', '', dept_name_clean)
    if dept_name_normalized:  # 空文字チェック
        for (dept_code, indicator, period), value in [(key, target_dict[key]) for key in relevant_keys]:
            dept_code_normalized = re.sub(r'[^\w]', '', str(dept_code))
            if dept_code_normalized and dept_name_normalized == dept_code_normalized:
                return str(dept_code), True
    
    return None, False

def display_dataframe_with_title_optimized(title, df_data, key_suffix=""):
    """最適化されたデータフレーム表示"""
    if df_data is not None and not df_data.empty:
        st.markdown(f"##### {title}")
        # 大きなデータフレームの場合は行数制限
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
    """個別分析タブの表示（最適化版）"""
    st.header("📊 個別分析")

    METRIC_FOR_CHART = '日平均在院患者数'

    # 必要な関数の存在チェック
    if not all([generate_filtered_summaries, create_forecast_dataframe, create_interactive_patient_chart,
                create_interactive_dual_axis_chart, get_display_name_for_dept,
                get_unified_filter_summary, get_unified_filter_config]):
        st.error("個別分析タブの実行に必要な機能の一部が読み込めませんでした。")
        st.info("アプリケーションを再起動するか、関連モジュールの設置を確認してください。")
        return

    # データの準備と検証
    df = df_filtered_main
    if df is not None and not df.empty and '病棟コード' in df.columns and EXCLUDED_WARDS:
        initial_count = len(df)
        df = df[~df['病棟コード'].isin(EXCLUDED_WARDS)]
        removed_count = initial_count - len(df)
        if removed_count > 0:
            st.info(f"除外病棟設定により{removed_count}件のレコードを除外しました。")

    if df is None or df.empty:
        st.error("分析対象のデータフレームが読み込まれていません。")
        st.info("「データ入力」タブでデータを読み込むか、フィルター条件を見直してください。")
        return

    # セッション状態の取得
    target_data = st.session_state.get('target_data')
    all_results = st.session_state.get('all_results')
    latest_data_date_str_from_session = st.session_state.get('latest_data_date_str', pd.Timestamp.now().strftime("%Y年%m月%d日"))
    unified_filter_applied = st.session_state.get('unified_filter_applied', False)

    # フィルター情報の表示
    if unified_filter_applied and get_unified_filter_summary:
        filter_summary = get_unified_filter_summary()
        st.info(f"🔍 適用中のフィルター: {filter_summary}")
        st.success(f"📊 フィルター適用後データ: {len(df):,}行")
    else:
        st.info("📊 全データでの個別分析")

    # 集計データの準備
    if all_results is None:
        if generate_filtered_summaries:
            logger.info("個別分析: 集計データを再生成中...")
            with st.spinner("集計データを生成中..."):
                start_time = time.time()
                all_results = generate_filtered_summaries(df, None, None)
                end_time = time.time()
                
                if end_time - start_time > 5.0:  # 5秒以上かかった場合
                    st.info(f"集計処理に{end_time - start_time:.1f}秒かかりました。")
                
            st.session_state.all_results = all_results
            if not all_results:
                st.error("統一フィルター適用範囲の集計データが生成できませんでした。")
                return
        else:
            st.error("統一フィルター適用範囲の集計データがありません。また、集計関数も利用できません。")
            return

    # 最新データ日付の処理（エラーハンドリング強化）
    try:
        if not df.empty and '日付' in df.columns:
            latest_data_date_from_df = df['日付'].max()
            latest_data_date = pd.Timestamp(latest_data_date_from_df).normalize()
        else:
            latest_data_date = pd.to_datetime(latest_data_date_str_from_session, format="%Y年%m月%d日").normalize()
    except Exception as e:
        logger.error(f"最新データ日付の処理中にエラー: {e}", exc_info=True)
        st.warning("最新データ日付の処理でエラーが発生しました。本日の日付を使用します。")
        latest_data_date = pd.Timestamp.now().normalize()

    # フィルター設定の解析
    current_filter_title_display = "統一フィルター適用範囲全体" if unified_filter_applied else "全体"
    current_results_data = all_results
    chart_data_for_graphs = df.copy()
    filter_code_for_target = "全体"
    
    filter_config = get_unified_filter_config() if get_unified_filter_config else {}
    
    if filter_config:
        # 複数の可能なキー名に対応
        selected_departments = (filter_config.get('selected_departments', []) or 
                              filter_config.get('selected_depts', []))
        selected_wards = (filter_config.get('selected_wards', []) or 
                         filter_config.get('selected_ward', []))
        
        if selected_departments and len(selected_departments) == 1:
            selected_dept_identifier = str(selected_departments[0]).strip()
            filter_code_for_target = selected_dept_identifier
            display_name = get_display_name_for_dept(selected_dept_identifier) if get_display_name_for_dept else selected_dept_identifier
            current_filter_title_display = f"診療科: {display_name}"
        elif selected_wards and len(selected_wards) == 1:
            selected_ward = str(selected_wards[0]).strip()
            filter_code_for_target = selected_ward
            current_filter_title_display = f"病棟: {selected_ward}"

    st.markdown(f"#### 分析結果: {current_filter_title_display}")

    # 集計データの検証
    if not current_results_data or not isinstance(current_results_data, dict) or current_results_data.get("summary") is None:
        st.warning(f"「{current_filter_title_display}」には表示できる集計データがありません。")
        return

    # データ期間情報の表示（最適化）
    selected_days_for_graph = 90
    if chart_data_for_graphs is not None and not chart_data_for_graphs.empty:
        data_period_info = ""
        if '日付' in chart_data_for_graphs.columns and not chart_data_for_graphs['日付'].empty:
            min_date_chart_obj = chart_data_for_graphs['日付'].min()
            max_date_chart_obj = chart_data_for_graphs['日付'].max()
            data_period_info = f"期間: {min_date_chart_obj.date()} ～ {max_date_chart_obj.date()}"
            
            calculated_days = (max_date_chart_obj - min_date_chart_obj).days + 1
            if calculated_days > 0:
                selected_days_for_graph = calculated_days
        
        # メトリック表示（コンパクト化）
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("対象データ", f"{len(chart_data_for_graphs):,}行")
        with col2:
            if data_period_info:
                st.metric("期間", f"{selected_days_for_graph}日間")
        with col3:
            if min_date_chart_obj and max_date_chart_obj:
                st.metric("最新日", max_date_chart_obj.strftime('%m/%d'))

    # 目標値の取得（最適化版）
    target_val_all, target_val_weekday, target_val_holiday = None, None, None
    
    if target_data is not None and not target_data.empty:
        # キャッシュされた目標値辞書を使用
        if '_target_dict_cached' not in st.session_state:
            with st.spinner("目標値データを処理中..."):
                st.session_state._target_dict_cached = create_target_dict_cached(target_data)
        
        target_dict = st.session_state._target_dict_cached
        
        if target_dict:
            if filter_code_for_target == "全体":
                # 全体の目標値検索（複数パターン対応）
                for code in ["000", "全体", "病院全体", "病院", "総合", "0"]:
                    for period, target_var in [('全日', 'target_val_all'), ('平日', 'target_val_weekday'), ('休日', 'target_val_holiday')]:
                        key = (code, METRIC_FOR_CHART, period)
                        if key in target_dict:
                            try:
                                value = float(target_dict[key])
                                if target_var == 'target_val_all':
                                    target_val_all = value
                                elif target_var == 'target_val_weekday':
                                    target_val_weekday = value
                                elif target_var == 'target_val_holiday':
                                    target_val_holiday = value
                            except (ValueError, TypeError):
                                pass
            else:
                # 個別部門の目標値検索
                actual_dept_code = filter_code_for_target
                
                # 診療科の場合、目標値辞書から対応する部門コードを探す
                selected_depts = (filter_config.get('selected_departments', []) or 
                                filter_config.get('selected_depts', []))
                if selected_depts:
                    dept_code_found, target_exists = find_department_code_in_targets_optimized(
                        filter_code_for_target, target_dict, METRIC_FOR_CHART
                    )
                    if dept_code_found:
                        actual_dept_code = dept_code_found
                
                # 目標値の取得
                for period, target_var in [('全日', 'target_val_all'), ('平日', 'target_val_weekday'), ('休日', 'target_val_holiday')]:
                    key = (str(actual_dept_code), METRIC_FOR_CHART, period)
                    if key in target_dict:
                        try:
                            value = float(target_dict[key])
                            if target_var == 'target_val_all':
                                target_val_all = value
                            elif target_var == 'target_val_weekday':
                                target_val_weekday = value
                            elif target_var == 'target_val_holiday':
                                target_val_holiday = value
                        except (ValueError, TypeError):
                            pass

    # デバッグ機能（簡略版、パフォーマンス考慮）
    if st.checkbox("🎯 目標値設定状況を確認", key="show_target_debug_main"):
        with st.expander("目標値設定デバッグ", expanded=False):
            col_debug1, col_debug2 = st.columns(2)
            
            with col_debug1:
                st.markdown("**フィルター状況**")
                st.write(f"分析対象: {current_filter_title_display}")
                st.write(f"検索キー: `('{filter_code_for_target}', '{METRIC_FOR_CHART}', '全日')`")
            
            with col_debug2:
                st.markdown("**目標値検索結果**")
                if target_val_all is not None:
                    st.success(f"✅ 目標値: {target_val_all}")
                else:
                    st.warning("❌ 目標値なし")
                
                if '_target_dict_cached' in st.session_state:
                    available_keys = {k: v for k, v in st.session_state._target_dict_cached.items() 
                                    if k[1] == METRIC_FOR_CHART and k[2] == '全日'}
                    st.write(f"利用可能な部門: {len(available_keys)}件")

    # グラフ表示（タブ化で整理）
    graph_tab1, graph_tab2 = st.tabs(["📈 入院患者数推移", "📊 複合指標推移"])
    
    with graph_tab1:
        if create_interactive_patient_chart:
            # 全日グラフ
            with st.container():
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

            # 平日・休日グラフ（データが存在する場合のみ）
            if "平日判定" in chart_data_for_graphs.columns:
                weekday_data_ind = chart_data_for_graphs[chart_data_for_graphs["平日判定"] == "平日"]
                holiday_data_ind = chart_data_for_graphs[chart_data_for_graphs["平日判定"] == "休日"]

                # 平日・休日グラフを並列表示
                col_wd, col_hd = st.columns(2)
                
                with col_wd:
                    st.markdown("##### 平日推移")
                    try:
                        if not weekday_data_ind.empty:
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
                                st.warning("平日グラフ生成失敗")
                        else:
                            st.info("平日データがありません")
                    except Exception as e:
                        logger.error(f"平日グラフ作成エラー: {e}", exc_info=True)
                        st.error("平日グラフ作成エラー")

                with col_hd:
                    st.markdown("##### 休日推移")
                    try:
                        if not holiday_data_ind.empty:
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
                                st.warning("休日グラフ生成失敗")
                        else:
                            st.info("休日データがありません")
                    except Exception as e:
                        logger.error(f"休日グラフ作成エラー: {e}", exc_info=True)
                        st.error("休日グラフ作成エラー")
        else:
            st.warning("グラフ生成関数が利用できません。")

    with graph_tab2:
        if create_interactive_dual_axis_chart:
            st.markdown("##### 入院患者数と患者移動の推移（7日移動平均）")
            try:
                fig_dual_ind = create_interactive_dual_axis_chart(
                    chart_data_for_graphs, 
                    title=f"{current_filter_title_display} 患者数と移動",
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
            st.warning("複合グラフ生成関数が利用できません。")

    # 予測データ表示
    st.markdown("##### 在院患者数予測")
    if create_forecast_dataframe and current_results_data:
        summary_data = current_results_data.get("summary")
        weekday_data = current_results_data.get("weekday") 
        holiday_data = current_results_data.get("holiday")
        
        if all([summary_data is not None, weekday_data is not None, holiday_data is not None]):
            try:
                with st.spinner("予測データを生成中..."):
                    forecast_df_ind = create_forecast_dataframe(
                        summary_data, weekday_data, holiday_data, latest_data_date
                    )
                
                if forecast_df_ind is not None and not forecast_df_ind.empty:
                    display_df_ind = forecast_df_ind.copy()
                    
                    # 列名の整理
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
            st.warning("予測に必要な集計データ（全日/平日/休日平均）が不足しています。")
    else:
        st.warning("予測データフレーム作成関数が利用できません。")

    # 集計データ表示（エクスパンダーで整理）
    with st.expander("📊 詳細集計データ", expanded=False):
        display_dataframe_with_title_optimized("全日平均値（平日・休日含む）", current_results_data.get("summary"))
        display_dataframe_with_title_optimized("平日平均値", current_results_data.get("weekday"))
        display_dataframe_with_title_optimized("休日平均値", current_results_data.get("holiday"))

    with st.expander("📅 月次平均値", expanded=False):
        display_dataframe_with_title_optimized("月次 全体平均", current_results_data.get("monthly_all"))
        display_dataframe_with_title_optimized("月次 平日平均", current_results_data.get("monthly_weekday"))
        display_dataframe_with_title_optimized("月次 休日平均", current_results_data.get("monthly_holiday"))

    # フィルター情報の再表示（下部）
    if unified_filter_applied and get_unified_filter_summary:
        st.markdown("---")
        filter_summary_bottom = get_unified_filter_summary()
        st.info(f"🔍 適用中のフィルター: {filter_summary_bottom}")

def create_individual_analysis_section(df_filtered, filter_config_from_caller):
    """個別分析セクション作成（analysis_tabs.pyから呼び出される）"""
    display_individual_analysis_tab(df_filtered)