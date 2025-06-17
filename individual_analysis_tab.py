# individual_analysis_tab.py (目標値取得改良版)

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
    generate_filtered_summaries = None
    create_forecast_dataframe = None
    create_interactive_patient_chart = None
    create_interactive_dual_axis_chart = None
    get_display_name_for_dept = None
    get_unified_filter_summary = None
    get_unified_filter_config = None



def display_individual_analysis_tab(df_filtered_main):

    # ▼▼▼▼▼ ここから内側のヘルパー関数として定義 ▼▼▼▼▼
    def find_department_code_in_targets_enhanced(dept_name, target_dict, metric_name):
        """診療科名に対応する部門コードを目標値辞書から探す（強化版）"""
        if not target_dict:
            return None, False
        
        dept_name_clean = str(dept_name).strip()
        
        # 1. 直接一致をチェック
        test_key = (dept_name_clean, metric_name, '全日')
        if test_key in target_dict:
            print(f"目標値発見（直接一致）: {test_key} = {target_dict[test_key]}")
            return dept_name_clean, True
        
        # 2. 部分一致をチェック
        for (dept_code, indicator, period), value in target_dict.items():
            if indicator == metric_name and period == '全日':
                if dept_name_clean in str(dept_code) or str(dept_code) in dept_name_clean:
                    print(f"目標値発見（部分一致）: ({dept_code}, {indicator}, {period}) = {value}")
                    return str(dept_code), True
        
        # 3. 正規化一致をチェック（スペースや特殊文字を無視）
        import re
        dept_name_normalized = re.sub(r'[^\w]', '', dept_name_clean)
        for (dept_code, indicator, period), value in target_dict.items():
            if indicator == metric_name and period == '全日':
                dept_code_normalized = re.sub(r'[^\w]', '', str(dept_code))
                if dept_name_normalized and dept_code_normalized:
                    if dept_name_normalized == dept_code_normalized:
                        print(f"目標値発見（正規化一致）: ({dept_code}, {indicator}, {period}) = {value}")
                        return str(dept_code), True
        
        # 4. 拡張検索（キーワード部分検索）
        for (dept_code, indicator, period), value in target_dict.items():
            if period == '全日':
                # 指標名の部分一致もチェック
                if any(keyword in indicator for keyword in ['在院', '患者', '人数']):
                    if dept_name_clean in str(dept_code) or str(dept_code) in dept_name_clean:
                        print(f"目標値発見（拡張検索）: ({dept_code}, {indicator}, {period}) = {value}")
                        return str(dept_code), True
        
        print(f"目標値未発見: {dept_name_clean} (検索対象: {len(target_dict)}件)")
        return None, False
    
    def get_enhanced_target_values(target_data, filter_code, current_filter_config, metric_name='日平均在院患者数'):
        """強化された目標値取得関数"""
        target_values = {'all': None, 'weekday': None, 'holiday': None}
        
        if not target_data or target_data.empty:
            print(f"目標値データが空 - filter_code: {filter_code}")
            return target_values
        
        try:
            print(f"=== 目標値検索開始 ===")
            print(f"Filter code: {filter_code}")
            print(f"Target data shape: {target_data.shape}")
            print(f"Target data columns: {list(target_data.columns)}")
            
            # 目標値辞書の構築（複数列名パターンに対応）
            target_dict = {}
            
            # 期間列の特定
            period_cols = ['区分', '期間区分', '期間', '分類']
            period_col = None
            for col in period_cols:
                if col in target_data.columns:
                    period_col = col
                    break
            
            # 指標列の特定
            indicator_cols = ['指標タイプ', '指標名', '指標', 'メトリクス']
            indicator_col = None
            for col in indicator_cols:
                if col in target_data.columns:
                    indicator_col = col
                    break
            
            print(f"期間列: {period_col}, 指標列: {indicator_col}")
            
            # 必須列の確認
            if not all(col in target_data.columns for col in ['部門コード', '目標値']):
                print(f"必須列不足 - 必要: ['部門コード', '目標値']")
                return target_values
            
            # 目標値辞書の構築
            for _, row in target_data.iterrows():
                dept_code = str(row['部門コード']).strip()
                target_val = row['目標値']
                
                if pd.notna(target_val):
                    # 期間の取得
                    period = '全日'  # デフォルト
                    if period_col and pd.notna(row[period_col]):
                        period = str(row[period_col]).strip()
                    
                    # 指標の取得
                    indicator = metric_name  # デフォルト
                    if indicator_col and pd.notna(row[indicator_col]):
                        indicator = str(row[indicator_col]).strip()
                    
                    key = (dept_code, indicator, period)
                    target_dict[key] = float(target_val)
                    print(f"目標値登録: {key} = {target_val}")
            
            print(f"目標値辞書構築完了: {len(target_dict)}件")
            
            # 検索対象コードの決定
            search_codes = []
            
            if filter_code == "全体":
                search_codes = ["000", "全体", "病院全体", "総合", "病院"]
            else:
                # フィルター設定から詳細情報を取得
                if current_filter_config:
                    selected_depts = (current_filter_config.get('selected_departments', []) or 
                                    current_filter_config.get('selected_depts', []))
                    selected_wards = (current_filter_config.get('selected_wards', []) or 
                                    current_filter_config.get('selected_ward', []))
                    
                    if selected_depts:
                        # 診療科での検索
                        dept_code, found = find_department_code_in_targets_enhanced(
                            filter_code, target_dict, metric_name
                        )
                        if found:
                            search_codes = [dept_code]
                        else:
                            search_codes = [str(filter_code)]
                    elif selected_wards:
                        # 病棟での検索
                        search_codes = [str(filter_code)]
                    else:
                        search_codes = [str(filter_code)]
                else:
                    search_codes = [str(filter_code)]
            
            print(f"検索対象コード: {search_codes}")
            
            # 目標値の検索（拡張版）
            for period_type, period_names in [
                ('all', ['全日', '全て', '全体']), 
                ('weekday', ['平日']), 
                ('holiday', ['休日', '祝日'])
            ]:
                for search_code in search_codes:
                    for period_name in period_names:
                        # 複数の指標名パターンで検索
                        for indicator in [metric_name, "日平均在院患者数", "在院患者数", "患者数", "入院患者数"]:
                            key = (search_code, indicator, period_name)
                            if key in target_dict:
                                try:
                                    target_values[period_type] = float(target_dict[key])
                                    print(f"✅ 目標値発見: {key} = {target_values[period_type]}")
                                    break
                                except (ValueError, TypeError):
                                    continue
                        
                        if target_values[period_type] is not None:
                            break
                    
                    if target_values[period_type] is not None:
                        break
            
            # 結果の出力
            print(f"=== 目標値検索結果 ===")
            for period_type, value in target_values.items():
                status = f"✅ {value}" if value is not None else "❌ 未発見"
                print(f"{period_type}: {status}")
            
        except Exception as e:
            print(f"目標値取得エラー: {e}")
            import traceback
            print(traceback.format_exc())
        
        return target_values
    
    def display_dataframe_with_title(title, df_data, key_suffix=""):
        if df_data is not None and not df_data.empty:
            st.markdown(f"##### {title}")
            st.dataframe(df_data, use_container_width=True)
        else:
            st.markdown(f"##### {title}")
            st.warning(f"{title} データがありません。")
    # ▲▲▲▲▲ ここまで内側のヘルパー関数 ▲▲▲▲▲

    st.header("📊 個別分析")

    METRIC_FOR_CHART = '日平均在院患者数'

    if not all([generate_filtered_summaries, create_forecast_dataframe, create_interactive_patient_chart,
                create_interactive_dual_axis_chart, get_display_name_for_dept,
                get_unified_filter_summary, get_unified_filter_config]):
        st.error("個別分析タブの実行に必要な機能の一部が読み込めませんでした。")
        return

    df = df_filtered_main

    # 除外病棟フィルタリング
    if df is not None and not df.empty and '病棟コード' in df.columns and EXCLUDED_WARDS:
        original_count = len(df)
        df = df[~df['病棟コード'].isin(EXCLUDED_WARDS)]
        if len(df) < original_count:
            st.info(f"🏥 除外病棟適用: {original_count - len(df)}件のレコードを除外")

    target_data = st.session_state.get('target_data')
    all_results = st.session_state.get('all_results')
    latest_data_date_str_from_session = st.session_state.get('latest_data_date_str', pd.Timestamp.now().strftime("%Y年%m月%d日"))
    unified_filter_applied = st.session_state.get('unified_filter_applied', False)

    if df is None or df.empty:
        st.error("分析対象のデータフレームが読み込まれていません。")
        return

    if unified_filter_applied and get_unified_filter_summary:
        filter_summary = get_unified_filter_summary()
        st.info(f"🔍 適用中のフィルター: {filter_summary}")
        st.success(f"📊 フィルター適用後データ: {len(df):,}行")
    else:
        st.info("📊 全データでの個別分析")

    if all_results is None:
        if generate_filtered_summaries:
            logger.warning("個別分析: st.session_state.all_results が未設定のため、dfから再生成します。")
            all_results = generate_filtered_summaries(df, None, None)
            st.session_state.all_results = all_results
            if not all_results:
                st.error("集計データが生成できませんでした。")
                return
        else:
            st.error("集計データがありません。")
            return

    try:
        if not df.empty and '日付' in df.columns:
            latest_data_date_from_df = df['日付'].max()
            latest_data_date = pd.Timestamp(latest_data_date_from_df).normalize()
        else:
            latest_data_date = pd.to_datetime(latest_data_date_str_from_session, format="%Y年%m月%d日").normalize()
    except Exception as e:
        logger.error(f"最新データ日付の処理中にエラー: {e}", exc_info=True)
        st.error(f"最新データ日付の処理中にエラーが発生しました。")
        latest_data_date = pd.Timestamp.now().normalize()

    current_filter_title_display = "統一フィルター適用範囲全体" if unified_filter_applied else "全体"
    current_results_data = all_results
    chart_data_for_graphs = df.copy()

    filter_code_for_target = None
    filter_config = get_unified_filter_config() if get_unified_filter_config else {}

    # フィルター設定から対象コードを決定
    if filter_config:
        selected_departments = (filter_config.get('selected_departments', []) or 
                              filter_config.get('selected_depts', []))
        selected_wards = (filter_config.get('selected_wards', []) or 
                         filter_config.get('selected_ward', []))
        
        if selected_departments and len(selected_departments) == 1:
            selected_dept_identifier = str(selected_departments[0]).strip()
            filter_code_for_target = selected_dept_identifier
            current_filter_title_display = f"診療科: {get_display_name_for_dept(selected_dept_identifier)}"
        elif selected_wards and len(selected_wards) == 1:
            selected_ward = str(selected_wards[0]).strip()
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

        # ===== 強化された目標値取得 =====
        target_values = get_enhanced_target_values(target_data, filter_code_for_target, filter_config, METRIC_FOR_CHART)
        target_val_all = target_values['all']
        target_val_weekday = target_values['weekday'] 
        target_val_holiday = target_values['holiday']

        # デバッグ機能（強化版）
        if st.checkbox("🎯 目標値設定状況を確認（詳細版）", key="show_target_debug_enhanced"):
            st.markdown("---")
            st.subheader("目標値設定デバッグ（詳細版）")

            st.markdown("##### フィルター状況")
            st.write(f"**分析対象:** {current_filter_title_display}")
            st.write(f"**検索キー:** `{filter_code_for_target}`")
            st.write(f"**メトリクス:** `{METRIC_FOR_CHART}`")
            
            col_debug1, col_debug2, col_debug3 = st.columns(3)
            with col_debug1:
                if target_val_all is not None:
                    st.success(f"✅ 全日目標値: {target_val_all}")
                else:
                    st.error("❌ 全日目標値: 未発見")
            with col_debug2:
                if target_val_weekday is not None:
                    st.success(f"✅ 平日目標値: {target_val_weekday}")
                else:
                    st.warning("⚠️ 平日目標値: 未発見")
            with col_debug3:
                if target_val_holiday is not None:
                    st.success(f"✅ 休日目標値: {target_val_holiday}")
                else:
                    st.warning("⚠️ 休日目標値: 未発見")
                
            if target_data is not None and not target_data.empty:
                st.markdown("##### 目標データ詳細")
                st.write(f"**データ形状:** {target_data.shape}")
                st.write(f"**列名:** {list(target_data.columns)}")
                
                # サンプルデータ表示
                if st.checkbox("目標データサンプル表示", key="show_target_sample_enhanced"):
                    st.dataframe(target_data.head(10), use_container_width=True)
                
                # 利用可能な部門コード一覧
                if '部門コード' in target_data.columns:
                    unique_dept_codes = target_data['部門コード'].unique()
                    st.write(f"**利用可能な部門コード:** {len(unique_dept_codes)}個")
                    if len(unique_dept_codes) <= 20:
                        st.write(", ".join([str(code) for code in unique_dept_codes]))
                    else:
                        st.write(f"最初の20個: {', '.join([str(code) for code in unique_dept_codes[:20]])}...")

        # グラフ表示
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
                        if target_val_all:
                            st.info(f"🎯 目標値ライン表示中: {target_val_all}")
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
                            if target_val_weekday:
                                st.info(f"🎯 平日目標値ライン表示中: {target_val_weekday}")
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
                            if target_val_holiday:
                                st.info(f"🎯 休日目標値ライン表示中: {target_val_holiday}")
                        else:
                            st.warning("休日グラフの生成に失敗しました。")
                    except Exception as e:
                        logger.error(f"休日グラフ作成エラー: {e}", exc_info=True)
                        st.error(f"休日グラフの作成中にエラーが発生しました: {e}")
            else:
                st.warning("グラフ生成関数が利用できません。")

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
                st.warning("グラフ生成関数が利用できません。")
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
        st.warning("予測データフレーム作成関数または必要な集計データが不足しています。")

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