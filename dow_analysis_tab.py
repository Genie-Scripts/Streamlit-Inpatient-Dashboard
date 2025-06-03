# dow_analysis_tab.py (修正版 - 統一フィルター専用)
import streamlit as st
import pandas as pd
import numpy as np
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

def display_dow_analysis_tab(
    df: pd.DataFrame,
    start_date, # Timestamp想定
    end_date,   # Timestamp想定
    common_config=None # 現状未使用だが、将来的な共通設定のために残す
):
    """
    曜日別入退院分析タブの表示関数（統一フィルター専用版）
    Args:
        df (pd.DataFrame): 統一フィルターで既にフィルタリング済みのDataFrame
        start_date (pd.Timestamp): 分析期間の開始日
        end_date (pd.Timestamp): 分析期間の終了日
        common_config (dict, optional): 共通設定
    """
    logger.info("曜日別入退院分析タブを開始します（統一フィルター専用版）")

    st.header("📆 曜日別入退院分析")

    if df is None or df.empty:
        st.warning("🔍 分析対象のデータが空です。統一フィルター条件を確認してください。")
        return

    required_cols = [
        '日付', '病棟コード', '診療科名',
        '総入院患者数', '総退院患者数',
        '入院患者数', '緊急入院患者数', '死亡患者数', '在院患者数'
    ]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"❌ 曜日別分析に必要な列が不足しています: {', '.join(missing_cols)}")
        logger.error(f"必須列が不足: {missing_cols}")
        return

    # '平日判定' 列の確認と追加
    df_analysis = df.copy()
    if '平日判定' not in df_analysis.columns:
        try:
            import jpholiday
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
    # ⚙️ 曜日別入退院分析 詳細設定 (統一フィルター専用)
    # =================================================================
    with st.expander("⚙️ 表示・分析パラメータ調整", expanded=True):
        col_set1, col_set2 = st.columns(2)

        with col_set1:
            st.markdown("##### 📊 チャート・集計設定")
            chart_metric_options = ['総入院患者数', '総退院患者数', '入院患者数', '緊急入院患者数', '退院患者数', '死亡患者数', '在院患者数']
            valid_chart_metrics = [m for m in chart_metric_options if m in df_analysis.columns]
            selected_metrics = st.multiselect(
                "チャート表示指標:",
                valid_chart_metrics,
                default=[m for m in ['総入院患者数', '総退院患者数'] if m in valid_chart_metrics],
                key="dow_tab_chart_metrics_multiselect",
                help="チャートに表示する患者数指標を選択"
            )

        with col_set2:
            aggregation_ui = st.selectbox(
                "集計方法:",
                ["曜日別 平均患者数/日", "曜日別 合計患者数"],
                index=0,
                key="dow_tab_aggregation_selectbox",
                help="データの集計方法を選択"
            )
            metric_type_for_logic = 'average' if aggregation_ui == "曜日別 平均患者数/日" else 'sum'

    # =================================================================
    # メインコンテンツ：曜日別チャート・サマリー・ヒートマップ
    # =================================================================
    if not DOW_CHARTS_AVAILABLE:
        st.error("❌ dow_charts.py モジュールが利用できません。")
        return

    # 統一フィルター範囲全体での分析
    st.success("🏥 **分析対象:** 統一フィルター範囲全体")
    chart_unit_type_for_logic = '病院全体'
    final_target_items_for_logic = []
    final_target_items_display_for_charts = ["統一フィルター範囲"]

    st.markdown(f"### 📊 曜日別 患者数パターン ({aggregation_ui})")
    if selected_metrics:
        try:
            dow_data_for_chart = get_dow_data(
                df=df_analysis,
                unit_type=chart_unit_type_for_logic,
                target_items=final_target_items_for_logic,
                start_date=start_date_ts,
                end_date=end_date_ts,
                metric_type=metric_type_for_logic,
                patient_cols_to_analyze=selected_metrics
            )

            if dow_data_for_chart is not None and not dow_data_for_chart.empty:
                fig = create_dow_chart(
                    dow_data_melted=dow_data_for_chart,
                    unit_type=chart_unit_type_for_logic,
                    target_items=final_target_items_display_for_charts,
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
    
    try:
        if calculate_dow_summary:
            summary_df_from_calc = calculate_dow_summary(
                df=df_analysis,
                start_date=start_date_ts,
                end_date=end_date_ts,
                group_by_column=None,  # 全体集計のためNone
                target_items=final_target_items_for_logic
            )
            if summary_df_from_calc is not None and not summary_df_from_calc.empty:
                display_summary_df = summary_df_from_calc.copy()

                cols_to_show = ['曜日名', '集計日数']
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

                if cols_to_show_existing and len(cols_to_show_existing) > 2:
                    st.dataframe(
                        display_summary_df[cols_to_show_existing].style.format(fmt, na_rep="-"),
                        height=min(len(display_summary_df) * 38 + 40, 600)
                    )
                    csv_bytes = display_summary_df[cols_to_show_existing].to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📊 サマリーデータをCSVダウンロード", data=csv_bytes,
                        file_name=f"曜日別サマリー_統一フィルター範囲_{start_date_ts.strftime('%Y%m%d')}-{end_date_ts.strftime('%Y%m%d')}.csv",
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

    # --- 分析インサイトと傾向 ---
    st.markdown("### 💡 分析インサイトと傾向")
    if 'summary_df_from_calc' in locals() and summary_df_from_calc is not None and not summary_df_from_calc.empty:
        insights_dow = {"weekday_pattern": [], "general": []}
        
        # 平日 vs 週末の比較
        metric_for_insight = "総入院患者数"
        avg_metric_col = f"平均{metric_for_insight}"
        sum_metric_col = f"{metric_for_insight}合計"
        
        col_to_use_for_insight = None
        if metric_type_for_logic == 'average' and avg_metric_col in summary_df_from_calc.columns:
            col_to_use_for_insight = avg_metric_col
        elif metric_type_for_logic == 'sum' and sum_metric_col in summary_df_from_calc.columns:
            col_to_use_for_insight = sum_metric_col
        
        if col_to_use_for_insight:
            overall_summary_dow = summary_df_from_calc.groupby('曜日名', observed=False)[col_to_use_for_insight].sum().reset_index()
            if not overall_summary_dow.empty:
                max_day_insight = overall_summary_dow.loc[overall_summary_dow[col_to_use_for_insight].idxmax()]
                min_day_insight = overall_summary_dow.loc[overall_summary_dow[col_to_use_for_insight].idxmin()]
                insights_dow["weekday_pattern"].append(f"{metric_for_insight}は**{max_day_insight['曜日名']}**が最も多く、**{min_day_insight['曜日名']}**が最も少ない傾向があります。")

        if insights_dow["weekday_pattern"] or insights_dow["general"]:
            st.markdown("<div class='info-card'>", unsafe_allow_html=True)
            st.markdown("#### 📊 データ分析インサイト")
            for section, ins_list in insights_dow.items():
                for ins in ins_list: 
                    st.markdown(f"- {ins}")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("ℹ️ 分析インサイトを生成するための十分なデータパターンが見つかりませんでした。")
    else:
        st.info("ℹ️ 分析インサイトを生成するためのサマリーデータがありません。")

    logger.info("曜日別入退院分析タブの処理が完了しました")