# dow_analysis_tab.py (修正版)
import streamlit as st
import pandas as pd
import numpy as np
# from datetime import timedelta, date # このファイル内では直接使っていない
import logging

logger = logging.getLogger(__name__)

# dow_charts.py から必要な関数をインポート (変更なし)
try:
    from dow_charts import (
        get_dow_data,
        create_dow_chart,
        calculate_dow_summary,
        create_dow_heatmap,
        DOW_LABELS
    )
    DOW_CHARTS_AVAILABLE = True
except ImportError as e:
    logger.error(f"dow_charts.py のインポートエラー: {e}")
    DOW_CHARTS_AVAILABLE = False
    get_dow_data = lambda *args, **kwargs: pd.DataFrame()
    create_dow_chart = lambda *args, **kwargs: None
    calculate_dow_summary = lambda *args, **kwargs: pd.DataFrame()
    create_dow_heatmap = lambda *args, **kwargs: None
    DOW_LABELS = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日']

# utils.py から必要な関数をインポート (変更なし)
from utils import (
    get_ward_display_name,
    create_ward_display_options, # create_dept_display_options と合わせて使用
    # safe_date_filter, # このファイル内では直接使用していない
    get_display_name_for_dept,
    create_dept_display_options
)

def display_dow_analysis_tab(
    df: pd.DataFrame,
    start_date, # Timestamp想定
    end_date,   # Timestamp想定
    common_config=None # 現状未使用だが、将来的な共通設定のために残す
):
    """
    曜日別入退院分析タブの表示関数（統一フィルター対応・タブ内設定版）
    Args:
        df (pd.DataFrame): 統一フィルターで既にフィルタリング済みのDataFrame
        start_date (pd.Timestamp): 分析期間の開始日
        end_date (pd.Timestamp): 分析期間の終了日
        common_config (dict, optional): 共通設定
    """
    logger.info("曜日別入退院分析タブを開始します（タブ内設定版）")

    st.header("📆 曜日別入退院分析")

    if df is None or df.empty:
        st.warning("🔍 分析対象のデータが空です。統一フィルター条件を確認してください。")
        return

    required_cols = [
        '日付', '病棟コード', '診療科名',
        '総入院患者数', '総退院患者数',
        '入院患者数', '緊急入院患者数', '死亡患者数', '在院患者数'
    ] # '平日判定' は generate_filtered_summaries で追加される想定だが、ここでも確認・追加した方が安全
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"❌ 曜日別分析に必要な列が不足しています: {', '.join(missing_cols)}")
        logger.error(f"必須列が不足: {missing_cols}")
        return

    # '平日判定' 列の確認と追加 (generate_filtered_summaries を通らない場合も考慮)
    df_analysis = df.copy() # 以降はこのコピーを使用
    if '平日判定' not in df_analysis.columns:
        try:
            import jpholiday # jpholiday がないとエラーになる
            def is_holiday_for_dow(date_val):
                return (
                    date_val.weekday() >= 5 or
                    jpholiday.is_holiday(date_val) or
                    (date_val.month == 12 and date_val.day >= 29) or
                    (date_val.month == 1 and date_val.day <= 3)
                )
            df_analysis['平日判定'] = pd.to_datetime(df_analysis['日付']).apply(lambda x: "休日" if is_holiday_for_dow(x) else "平日")
            logger.info("DOWタブ: '平日判定'列を動的に追加しました。")
        except ImportError:
            st.error("jpholidayライブラリが見つかりません。平日/休日の判定ができません。")
            return
        except Exception as e_hd:
            st.error(f"平日判定列の追加中にエラー: {e_hd}")
            logger.error(f"平日判定列の追加エラー: {e_hd}", exc_info=True)
            return


    try:
        start_date_ts = pd.Timestamp(start_date)
        end_date_ts = pd.Timestamp(end_date)
    except Exception as e:
        st.error(f"❌ 渡された開始日または終了日の形式が正しくありません: {e}")
        logger.error(f"日付変換エラー: {e}")
        return

    period_days = (end_date_ts - start_date_ts).days + 1
    st.info(f"📅 **分析期間 (統一フィルター適用済):** {start_date_ts.strftime('%Y年%m月%d日')} ～ {end_date_ts.strftime('%Y年%m月%d日')} （{period_days}日間）")

    # =================================================================
    # ⚙️ 曜日別入退院分析 詳細設定 (タブ内に移動)
    # =================================================================
    with st.expander("⚙️ 表示・分析パラメータ調整", expanded=True):
        col_set1, col_set2, col_set3 = st.columns(3)

        with col_set1:
            st.markdown("##### 🔍 分析スコープ")
            selected_unit = st.selectbox(
                "スコープ選択:", # ラベル簡略化
                ['統一フィルター範囲', '診療科別詳細', '病棟別詳細'],
                index=0,
                key="dow_tab_unit_selectbox", # キー名をタブ固有に
                help="統一フィルターで選択された範囲での分析スコープを指定"
            )

        target_items_actual = []  # 内部処理用のコードリスト
        target_items_display = [] # 表示用の名前リスト

        with col_set2:
            if selected_unit == '病棟別詳細':
                st.markdown("##### 🏨 詳細分析対象病棟")
                if '病棟コード' in df_analysis.columns:
                    available_wards_codes = sorted(df_analysis['病棟コード'].astype(str).unique())
                    ward_mapping_dict = st.session_state.get('ward_mapping', {})
                    ward_display_options_list, ward_option_to_code_map = create_ward_display_options(available_wards_codes, ward_mapping_dict)
                    default_selected_wards_display = ward_display_options_list[:min(3, len(ward_display_options_list))]

                    selected_wards_display_names = st.multiselect(
                        "対象病棟選択:", # ラベル簡略化
                        ward_display_options_list,
                        default=default_selected_wards_display,
                        key="dow_tab_target_wards_display", # キー名をタブ固有に
                        help="詳細分析対象病棟（複数選択可）"
                    )
                    target_items_actual = [ward_option_to_code_map[name] for name in selected_wards_display_names if name in ward_option_to_code_map]
                    target_items_display = selected_wards_display_names
                else:
                    st.warning("⚠️ 病棟コード列が見つかりません")

            elif selected_unit == '診療科別詳細':
                st.markdown("##### 🩺 詳細分析対象診療科")
                if '診療科名' in df_analysis.columns:
                    available_depts_codes = sorted(df_analysis['診療科名'].astype(str).unique())
                    dept_mapping_dict = st.session_state.get('dept_mapping', {}) # 診療科名は通常マッピング不要だが念のため
                    dept_display_options_list, dept_option_to_code_map = create_dept_display_options(available_depts_codes, dept_mapping_dict)
                    default_selected_depts_display = dept_display_options_list[:min(3, len(dept_display_options_list))]

                    selected_depts_display_names = st.multiselect(
                        "対象診療科選択:", # ラベル簡略化
                        dept_display_options_list,
                        default=default_selected_depts_display,
                        key="dow_tab_target_depts_display", # キー名をタブ固有に
                        help="詳細分析対象診療科（複数選択可）"
                    )
                    target_items_actual = [dept_option_to_code_map[name] for name in selected_depts_display_names if name in dept_option_to_code_map]
                    target_items_display = selected_depts_display_names
                else:
                    st.warning("⚠️ 診療科名列が見つかりません")
            else: # 統一フィルター範囲
                st.write("") # スペーサー

        with col_set3:
            st.markdown("##### 📊 チャート・集計設定")
            chart_metric_options = ['総入院患者数', '総退院患者数', '入院患者数', '緊急入院患者数', '退院患者数', '死亡患者数', '在院患者数']
            valid_chart_metrics = [m for m in chart_metric_options if m in df_analysis.columns]
            selected_metrics = st.multiselect(
                "チャート表示指標:",
                valid_chart_metrics,
                default=[m for m in ['総入院患者数', '総退院患者数'] if m in valid_chart_metrics],
                key="dow_tab_chart_metrics_multiselect", # キー名をタブ固有に
                help="チャートに表示する患者数指標を選択"
            )
            aggregation_ui = st.selectbox(
                "集計方法:", # ラベル簡略化
                ["曜日別 平均患者数/日", "曜日別 合計患者数"],
                index=0,
                key="dow_tab_aggregation_selectbox", # キー名をタブ固有に
                help="データの集計方法を選択"
            )
            metric_type_for_logic = 'average' if aggregation_ui == "曜日別 平均患者数/日" else 'sum'

    # 分析対象の確認
    if selected_unit != '統一フィルター範囲' and not target_items_actual:
        unit_label_msg = "病棟" if selected_unit == '病棟別詳細' else "診療科"
        st.warning(f"⚠️ 詳細分析対象の{unit_label_msg}を「表示・分析パラメータ調整」で選択してください。")
        return

    # 分析スコープの表示 (メインコンテンツエリア)
    if selected_unit == '統一フィルター範囲':
        st.success("🏥 **分析対象:** 統一フィルター範囲全体")
        chart_unit_type_for_logic = '病院全体' # dow_charts.py が期待する値
        final_target_items_for_logic = []
        final_target_items_display_for_charts = ["統一フィルター範囲"]
    elif selected_unit == '病棟別詳細':
        st.info(f"🏨 **分析対象:** {len(target_items_actual)}病棟 ({', '.join(target_items_display[:3])}{'...' if len(target_items_display) > 3 else ''}) の詳細分析")
        chart_unit_type_for_logic = '病棟別'
        final_target_items_for_logic = target_items_actual
        final_target_items_display_for_charts = target_items_display
    else:  # 診療科別詳細
        st.info(f"🩺 **分析対象:** {len(target_items_actual)}診療科 ({', '.join(target_items_display[:3])}{'...' if len(target_items_display) > 3 else ''}) の詳細分析")
        chart_unit_type_for_logic = '診療科別'
        final_target_items_for_logic = target_items_actual
        final_target_items_display_for_charts = target_items_display


    # =================================================================
    # メインコンテンツ：曜日別チャート・サマリー・ヒートマップ
    # =================================================================
    if not DOW_CHARTS_AVAILABLE:
        st.error("❌ dow_charts.py モジュールが利用できません。")
        # create_fallback_dow_analysis(df_analysis, start_date_ts, end_date_ts, selected_metrics) # フォールバックは別途検討
        return

    st.markdown(f"### 📊 曜日別 患者数パターン ({aggregation_ui})")
    if selected_metrics:
        try:
            dow_data_for_chart = get_dow_data(
                df=df_analysis, # フィルタ済みのDF
                unit_type=chart_unit_type_for_logic,
                target_items=final_target_items_for_logic, # 実際のコードリスト
                start_date=start_date_ts,
                end_date=end_date_ts,
                metric_type=metric_type_for_logic,
                patient_cols_to_analyze=selected_metrics
            )

            if dow_data_for_chart is not None and not dow_data_for_chart.empty:
                # チャート表示前に集計単位名を表示名に変換する処理は dow_charts.create_dow_chart に任せるか、
                # あるいはここで表示名リスト (final_target_items_display_for_charts) を適切に使う
                fig = create_dow_chart(
                    dow_data_melted=dow_data_for_chart,
                    unit_type=chart_unit_type_for_logic,
                    target_items=final_target_items_display_for_charts, # 表示名リストを使用
                    metric_type=metric_type_for_logic,
                    patient_cols_to_analyze=selected_metrics
                )
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("ℹ️ 曜日別チャートを生成できませんでした。")
            else:
                st.info("ℹ️ 曜日別チャートを表示するためのデータがありません。")
        except Exception as e:
            st.error(f"❌ 曜日別チャート生成中にエラーが発生しました: {e}")
            logger.error(f"曜日別チャート生成エラー: {e}", exc_info=True)
    else:
        st.info("ℹ️ チャートに表示する指標が選択されていません。「表示・分析パラメータ調整」で設定してください。")

    # --- 曜日別詳細サマリー ---
    st.markdown(f"### 📋 曜日別 詳細サマリー ({aggregation_ui})")
    group_by_col_for_summary = None
    if chart_unit_type_for_logic == '病棟別': group_by_col_for_summary = '病棟コード'
    elif chart_unit_type_for_logic == '診療科別': group_by_col_for_summary = '診療科名'

    try:
        if calculate_dow_summary:
            summary_df_from_calc = calculate_dow_summary(
                df=df_analysis,
                start_date=start_date_ts,
                end_date=end_date_ts,
                group_by_column=group_by_col_for_summary,
                target_items=final_target_items_for_logic # 実際のコードリスト
            )
            if summary_df_from_calc is not None and not summary_df_from_calc.empty:
                display_summary_df = summary_df_from_calc.copy()
                if '集計単位' in display_summary_df.columns: # 表示名変換
                    if chart_unit_type_for_logic == '病棟別':
                        ward_map_summary = st.session_state.get('ward_mapping', {})
                        display_summary_df['集計単位'] = display_summary_df['集計単位'].apply(lambda x: get_ward_display_name(str(x), ward_map_summary))
                    elif chart_unit_type_for_logic == '診療科別':
                        display_summary_df['集計単位'] = display_summary_df['集計単位'].apply(lambda x: get_display_name_for_dept(str(x), default_name=str(x)))

                cols_to_show = ['集計単位', '曜日名', '集計日数']
                fmt = {'集計日数': "{:.0f}"}
                base_metrics_summary = ['入院患者数', '緊急入院患者数', '総入院患者数', '退院患者数', '死亡患者数', '総退院患者数', '在院患者数']

                if metric_type_for_logic == 'average':
                    for bm in base_metrics_summary:
                        col_avg = f"平均{bm}"
                        if col_avg in display_summary_df.columns:
                            cols_to_show.append(col_avg); fmt[col_avg] = "{:.1f}"
                else: # sum
                    for bm in base_metrics_summary:
                        col_sum = f"{bm}合計"
                        if col_sum in display_summary_df.columns:
                            cols_to_show.append(col_sum); fmt[col_sum] = "{:.0f}"
                for rate_col in ['緊急入院率', '死亡退院率']:
                    if rate_col in display_summary_df.columns:
                        cols_to_show.append(rate_col); fmt[rate_col] = "{:.1f}%"
                cols_to_show_existing = [c for c in cols_to_show if c in display_summary_df.columns]

                if cols_to_show_existing and len(cols_to_show_existing) > 3:
                    st.dataframe(
                        display_summary_df[cols_to_show_existing].style.format(fmt, na_rep="-"),
                        height=min(len(display_summary_df) * 38 + 40, 600) # テーブル高さを調整
                    )
                    csv_bytes = display_summary_df[cols_to_show_existing].to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📊 サマリーデータをCSVダウンロード", data=csv_bytes,
                        file_name=f"曜日別サマリー_{chart_unit_type_for_logic}_{start_date_ts.strftime('%Y%m%d')}-{end_date_ts.strftime('%Y%m%d')}.csv",
                        mime='text/csv', key="dow_tab_csv_summary_download"
                    )
                else:
                    st.info("ℹ️ 表示するサマリー指標がありません。")
            else:
                st.info("ℹ️ 曜日別サマリーデータを表示できませんでした。")
        else:
            st.warning("⚠️ サマリー計算関数 (calculate_dow_summary) が利用できません。")
    except Exception as e:
        st.error(f"❌ 曜日別サマリー計算中にエラーが発生しました: {e}")
        logger.error(f"曜日別サマリー計算エラー: {e}", exc_info=True)

    # --- ヒートマップ ---
    if chart_unit_type_for_logic != '病院全体' and final_target_items_for_logic and len(final_target_items_for_logic) > 1:
        st.markdown(f"### 🔥 曜日別 ヒートマップ ({aggregation_ui})")
        heatmap_metrics_options = ['総入院患者数', '総退院患者数', '入院患者数', '緊急入院患者数', '退院患者数', '死亡患者数', '在院患者数']
        available_heatmap_metrics = [m for m in heatmap_metrics_options if f"平均{m}" in summary_df_from_calc.columns or f"{m}合計" in summary_df_from_calc.columns]

        if available_heatmap_metrics:
            selected_heatmap_metric_base = st.selectbox(
                "🎯 ヒートマップ表示指標:", available_heatmap_metrics,
                index=available_heatmap_metrics.index('総入院患者数') if '総入院患者数' in available_heatmap_metrics else 0,
                key="dow_tab_heatmap_metric_select",
                help="ヒートマップで可視化する指標を選択"
            )
            try:
                if create_dow_heatmap and summary_df_from_calc is not None and not summary_df_from_calc.empty:
                    # create_dow_heatmap は metric_type (average/sum) も引数に取るか、
                    # あるいは dow_data 内の列名から判断する必要がある。
                    # ここでは、基本指標名だけを渡す。
                    heatmap_fig = create_dow_heatmap(
                        dow_data=summary_df_from_calc, # calculate_dow_summary の結果をそのまま渡す
                        metric=selected_heatmap_metric_base, # '入院患者数' などの基本名
                        unit_type=chart_unit_type_for_logic # '病棟別' or '診療科別'
                    )
                    if heatmap_fig:
                        st.plotly_chart(heatmap_fig, use_container_width=True)
                        st.info("💡 **ヒートマップの見方:** 色が濃いほど患者数が多いことを示します。")
                    else:
                        st.info("ℹ️ ヒートマップを生成できませんでした。")
                else:
                    st.info("ℹ️ ヒートマップの元となるサマリーデータが不足しています。")
            except Exception as e:
                st.error(f"❌ ヒートマップ生成中にエラーが発生しました: {e}")
                logger.error(f"ヒートマップ生成エラー: {e}", exc_info=True)
        else:
            st.warning("⚠️ ヒートマップ表示用の指標が見つかりません。")

    # --- 分析インサイトと傾向 ---
    # ... (既存のインサイト表示ロジックは、summary_df_from_calc を利用するように調整が必要な場合がある) ...
    st.markdown("### 💡 分析インサイトと傾向")
    if summary_df_from_calc is not None and not summary_df_from_calc.empty:
        # ... (既存のインサイト生成・表示ロジック。必要に応じて summary_df_from_calc を参照するように修正) ...
        # 例: insights["alos"] はこのタブでは直接関係ないため、曜日別パターンに特化する
        insights_dow = {"weekday_pattern": [], "general": []} # DOW用のインサイト辞書
        
        # 平日 vs 週末の比較 (例: 総入院患者数)
        metric_for_insight = "総入院患者数" # または選択された主要指標
        avg_metric_col = f"平均{metric_for_insight}"
        sum_metric_col = f"{metric_for_insight}合計"
        
        col_to_use_for_insight = None
        if metric_type_for_logic == 'average' and avg_metric_col in summary_df_from_calc.columns:
            col_to_use_for_insight = avg_metric_col
        elif metric_type_for_logic == 'sum' and sum_metric_col in summary_df_from_calc.columns:
            col_to_use_for_insight = sum_metric_col
        
        if col_to_use_for_insight:
            # 簡単なインサイト例: 最も多い曜日と少ない曜日
            # (複数ユニットある場合は、代表的なユニットか、全体の傾向を見るかなど考慮が必要)
            overall_summary_dow = summary_df_from_calc.groupby('曜日名', observed=False)[col_to_use_for_insight].sum().reset_index() # 全ユニット合計の曜日別傾向
            if not overall_summary_dow.empty :
                max_day_insight = overall_summary_dow.loc[overall_summary_dow[col_to_use_for_insight].idxmax()]
                min_day_insight = overall_summary_dow.loc[overall_summary_dow[col_to_use_for_insight].idxmin()]
                insights_dow["weekday_pattern"].append(f"{metric_for_insight}は**{max_day_insight['曜日名']}**が最も多く、**{min_day_insight['曜日名']}**が最も少ない傾向があります。")

        if insights_dow["weekday_pattern"] or insights_dow["general"]:
            st.markdown("<div class='info-card'>", unsafe_allow_html=True)
            st.markdown("#### 📊 データ分析インサイト")
            for section, ins_list in insights_dow.items():
                for ins in ins_list: st.markdown(f"- {ins}")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("ℹ️ 分析インサイトを生成するための十分なデータパターンが見つかりませんでした。")
    else:
        st.info("ℹ️ 分析インサイトを生成するためのサマリーデータがありません。")

    logger.info("曜日別入退院分析タブの処理が完了しました")