# dow_analysis_tab.py - 統一フィルター対応版
import streamlit as st
import pandas as pd
import numpy as np
from datetime import timedelta, date
import logging

logger = logging.getLogger(__name__)

# dow_charts.py から必要な関数をインポート
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
    # フォールバックとしてダミー関数や変数を定義
    get_dow_data = lambda *args, **kwargs: pd.DataFrame()
    create_dow_chart = lambda *args, **kwargs: None
    calculate_dow_summary = lambda *args, **kwargs: pd.DataFrame()
    create_dow_heatmap = lambda *args, **kwargs: None
    DOW_LABELS = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日']

# utils.py から必要な関数をインポート
from utils import (
    get_ward_display_name,
    create_ward_display_options,
    safe_date_filter,
    get_display_name_for_dept,
    create_dept_display_options
)

def display_dow_analysis_tab(
    df: pd.DataFrame,
    start_date, # Timestamp想定
    end_date,   # Timestamp想定
    common_config=None
):
    """
    曜日別入退院分析タブの表示関数（統一フィルター対応版）
    Args:
        df (pd.DataFrame): 統一フィルターで既にフィルタリング済みのDataFrame
        start_date (pd.Timestamp): 分析期間の開始日
        end_date (pd.Timestamp): 分析期間の終了日
        common_config (dict, optional): 共通設定
    """
    logger.info("曜日別入退院分析タブを開始します（統一フィルター対応版）")
    
    st.header("📆 曜日別入退院分析")

    if df is None or df.empty:
        st.warning("🔍 分析対象のデータが空です。統一フィルター条件を確認してください。")
        return

    # 必要列の確認
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

    try:
        start_date_ts = pd.Timestamp(start_date)
        end_date_ts = pd.Timestamp(end_date)
    except Exception as e:
        st.error(f"❌ 渡された開始日または終了日の形式が正しくありません: {e}")
        logger.error(f"日付変換エラー: {e}")
        return

    # 期間情報の表示
    period_days = (end_date_ts - start_date_ts).days + 1
    st.info(f"📅 **分析期間:** {start_date_ts.strftime('%Y年%m月%d日')} ～ {end_date_ts.strftime('%Y年%m月%d日')} （{period_days}日間）")

    # =================================================================
    # 🔄 統一フィルター対応：サイドバー設定を簡素化
    # =================================================================
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ 曜日別入退院分析 詳細設定")
    st.sidebar.info("💡 期間・診療科・病棟は統一フィルターで設定済みです")

    # 分析スコープの選択
    selected_unit = st.sidebar.selectbox(
        "🔍 分析スコープ:",
        ['統一フィルター範囲', '診療科別詳細', '病棟別詳細'],
        index=0,
        key="dow_unit_selectbox",
        help="統一フィルターで選択された範囲での分析スコープを指定"
    )

    target_items = []  # 内部処理用のコードリスト
    
    if selected_unit == '病棟別詳細':
        if '病棟コード' in df.columns:
            available_wards_codes = sorted(df['病棟コード'].astype(str).unique())
            ward_mapping_dict = st.session_state.get('ward_mapping', {})
            ward_display_options_list, ward_option_to_code_map = create_ward_display_options(available_wards_codes, ward_mapping_dict)
            default_selected_wards_display = ward_display_options_list[:min(3, len(ward_display_options_list))] if ward_display_options_list else []

            selected_wards_display_names = st.sidebar.multiselect(
                "🏨 詳細分析対象病棟:",
                ward_display_options_list,
                default=default_selected_wards_display,
                key="dow_target_wards_display",
                help="統一フィルター範囲内での詳細分析対象病棟（複数選択可、チャート表示は最大5つ程度推奨）"
            )
            target_items = [ward_option_to_code_map[display_name] for display_name in selected_wards_display_names if display_name in ward_option_to_code_map]
        else:
            st.sidebar.warning("⚠️ 病棟コード列が見つかりません")

    elif selected_unit == '診療科別詳細':
        if '診療科名' in df.columns:
            available_depts_codes = sorted(df['診療科名'].astype(str).unique())
            dept_mapping_dict = st.session_state.get('dept_mapping', {})
            dept_display_options_list, dept_option_to_code_map = create_dept_display_options(available_depts_codes, dept_mapping_dict)
            default_selected_depts_display = dept_display_options_list[:min(3, len(dept_display_options_list))] if dept_display_options_list else []

            selected_depts_display_names = st.sidebar.multiselect(
                "🏥 詳細分析対象診療科:",
                dept_display_options_list,
                default=default_selected_depts_display,
                key="dow_target_depts_display",
                help="統一フィルター範囲内での詳細分析対象診療科（複数選択可、チャート表示は最大5つ程度推奨）"
            )
            target_items = [dept_option_to_code_map[display_name] for display_name in selected_depts_display_names if display_name in dept_option_to_code_map]
        else:
            st.sidebar.warning("⚠️ 診療科名列が見つかりません")

    # チャート表示指標の選択
    chart_metric_options = [
        '総入院患者数', '総退院患者数',
        '入院患者数', '緊急入院患者数',
        '退院患者数', '死亡患者数', '在院患者数'
    ]
    valid_chart_metrics = [m for m in chart_metric_options if m in df.columns]
    selected_metrics = st.sidebar.multiselect(
        "📊 チャート表示指標:",
        valid_chart_metrics,
        default=[m for m in ['総入院患者数', '総退院患者数'] if m in valid_chart_metrics],
        key="dow_chart_metrics_multiselect",
        help="チャートに表示する患者数指標を選択"
    )

    # 集計方法の選択
    aggregation_ui = st.sidebar.selectbox(
        "📈 集計方法 (チャート/サマリー共通):",
        ["曜日別 平均患者数/日", "曜日別 合計患者数"],
        index=0,
        key="dow_aggregation_selectbox",
        help="データの集計方法を選択"
    )
    metric_type = 'average' if aggregation_ui == "曜日別 平均患者数/日" else 'sum'

    # 分析対象の確認
    if selected_unit != '統一フィルター範囲' and not target_items:
        unit_label = selected_unit.replace('詳細', '').replace('別', '')
        st.warning(f"⚠️ 詳細分析対象の{unit_label}をサイドバーで選択してください。")
        return

    # 分析スコープの表示
    if selected_unit == '統一フィルター範囲':
        st.success("🏥 **分析対象:** 統一フィルター範囲全体")
    elif selected_unit == '病棟別詳細':
        st.info(f"🏨 **分析対象:** {len(target_items)}病棟の詳細分析")
    else:  # 診療科別詳細
        st.info(f"🏥 **分析対象:** {len(target_items)}診療科の詳細分析")

    # =================================================================
    # メインコンテンツ：曜日別チャート
    # =================================================================
    
    if not DOW_CHARTS_AVAILABLE:
        st.error("❌ dow_charts.py モジュールが利用できません。")
        create_fallback_dow_analysis(df, start_date_ts, end_date_ts, selected_metrics)
        return

    st.markdown(f"### 📊 曜日別 患者数パターン ({aggregation_ui})")
    
    dow_data_for_chart = pd.DataFrame()
    
    if selected_metrics:
        try:
            # 分析スコープを dow_charts の形式に変換
            if selected_unit == '統一フィルター範囲':
                chart_unit_type = '病院全体'
            elif selected_unit == '病棟別詳細':
                chart_unit_type = '病棟別'
            else:  # 診療科別詳細
                chart_unit_type = '診療科別'
            
            dow_data_for_chart = get_dow_data(
                df=df,
                unit_type=chart_unit_type,
                target_items=target_items,  # コードリストを渡す
                start_date=start_date_ts,
                end_date=end_date_ts,
                metric_type=metric_type,
                patient_cols_to_analyze=selected_metrics
            )

            if dow_data_for_chart is not None and not dow_data_for_chart.empty:
                # チャート表示前に集計単位名を表示名に変換
                display_dow_data_for_chart = dow_data_for_chart.copy()
                if '集計単位名' in display_dow_data_for_chart.columns:
                    if chart_unit_type == '病棟別':
                        ward_map_chart = st.session_state.get('ward_mapping', {})
                        display_dow_data_for_chart['集計単位名'] = display_dow_data_for_chart['集計単位名'].apply(
                            lambda x: get_ward_display_name(x, ward_map_chart)
                        )
                    elif chart_unit_type == '診療科別':
                        display_dow_data_for_chart['集計単位名'] = display_dow_data_for_chart['集計単位名'].apply(
                            lambda x: get_display_name_for_dept(x, default_name=x)
                        )

                if create_dow_chart:
                    # 表示名リストの作成
                    if chart_unit_type != '病院全体' and target_items:
                        if chart_unit_type == '診療科別':
                            display_target_items = [get_display_name_for_dept(ti, default_name=ti) for ti in target_items]
                        else:  # 病棟別
                            display_target_items = [get_ward_display_name(ti, st.session_state.get('ward_mapping', {})) for ti in target_items]
                    else:
                        display_target_items = ["統一フィルター範囲"]
                    
                    fig = create_dow_chart(
                        dow_data_melted=display_dow_data_for_chart,  # 表示名に変換したデータを使用
                        unit_type=chart_unit_type,
                        target_items=display_target_items,
                        metric_type=metric_type,
                        patient_cols_to_analyze=selected_metrics
                    )
                    
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("ℹ️ 曜日別チャートを生成できませんでした。")
                        logger.warning("曜日別チャート生成に失敗")
                else:
                    st.warning("⚠️ チャート生成関数 (create_dow_chart) が利用できません。")
            else:
                st.info("ℹ️ 曜日別チャートを表示するためのデータがありません。")
                logger.info("曜日別チャート用データが空")
        
        except Exception as e:
            st.error(f"❌ 曜日別チャート生成中にエラーが発生しました: {e}")
            logger.error(f"曜日別チャート生成エラー: {e}")
    else:
        st.info("ℹ️ チャートに表示する指標が選択されていません。")

    # =================================================================
    # 曜日別詳細サマリー
    # =================================================================
    
    st.markdown(f"### 📋 曜日別 詳細サマリー ({aggregation_ui})")

    group_by_col = None
    if chart_unit_type == '病棟別':
        group_by_col = '病棟コード'
    elif chart_unit_type == '診療科別':
        group_by_col = '診療科名'

    summary_df_from_calc = pd.DataFrame()
    
    try:
        if calculate_dow_summary:
            summary_df_from_calc = calculate_dow_summary(
                df=df,
                start_date=start_date_ts,
                end_date=end_date_ts,
                group_by_column=group_by_col,
                target_items=target_items  # コードリストを渡す
            )

            if summary_df_from_calc is not None and not summary_df_from_calc.empty:
                # 表示用に集計単位名を変換
                display_summary_df = summary_df_from_calc.copy()
                if '集計単位' in display_summary_df.columns:
                    if chart_unit_type == '病棟別':
                        ward_map_summary = st.session_state.get('ward_mapping', {})
                        display_summary_df['集計単位'] = display_summary_df['集計単位'].apply(
                            lambda x: get_ward_display_name(x, ward_map_summary)
                        )
                    elif chart_unit_type == '診療科別':
                        display_summary_df['集計単位'] = display_summary_df['集計単位'].apply(
                            lambda x: get_display_name_for_dept(x, default_name=x)
                        )
                
                # 表示列とフォーマットの設定
                cols_to_show = ['集計単位', '曜日名', '集計日数']
                fmt = {'集計日数': "{:.0f}"}

                base_metrics = [
                    '入院患者数', '緊急入院患者数', '総入院患者数',
                    '退院患者数', '死亡患者数', '総退院患者数', '在院患者数'
                ]
                
                if metric_type == 'average':
                    for bm in base_metrics:
                        col_avg = f"平均{bm}"
                        if col_avg in display_summary_df.columns:
                            cols_to_show.append(col_avg)
                            fmt[col_avg] = "{:.1f}"
                else:  # sum
                    for bm in base_metrics:
                        col_sum = f"{bm}合計"
                        if col_sum in display_summary_df.columns:
                            cols_to_show.append(col_sum)
                            fmt[col_sum] = "{:.0f}"

                for rate_col in ['緊急入院率', '死亡退院率']:
                    if rate_col in display_summary_df.columns:
                        cols_to_show.append(rate_col)
                        fmt[rate_col] = "{:.1f}%"

                cols_to_show = [c for c in cols_to_show if c in display_summary_df.columns]

                if cols_to_show and len(cols_to_show) > 3:
                    st.dataframe(
                        display_summary_df[cols_to_show].style.format(fmt),
                        height=min(len(display_summary_df) * 38 + 40, 600)
                    )
                    
                    # CSVダウンロード
                    csv_bytes = display_summary_df[cols_to_show].to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📊 サマリーデータをCSVダウンロード",
                        data=csv_bytes,
                        file_name=f"曜日別サマリー_{chart_unit_type}_{start_date_ts.strftime('%Y%m%d')}-{end_date_ts.strftime('%Y%m%d')}.csv",
                        mime='text/csv'
                    )
                else:
                    st.info("ℹ️ 表示するサマリー指標がありません。")
            else:
                st.info("ℹ️ 曜日別サマリーデータを表示できませんでした。")
        else:
            st.warning("⚠️ サマリー計算関数 (calculate_dow_summary) が利用できません。")
            
    except Exception as e:
        st.error(f"❌ 曜日別サマリー計算中にエラーが発生しました: {e}")
        logger.error(f"曜日別サマリー計算エラー: {e}")

    # =================================================================
    # ヒートマップ（複数の対象がある場合のみ）
    # =================================================================
    
    if chart_unit_type != '病院全体' and target_items and len(target_items) > 1:
        st.markdown(f"### 🔥 曜日別 ヒートマップ ({aggregation_ui})")
        
        heatmap_metrics = [
            '入院患者数', '緊急入院患者数',
            '総入院患者数', '退院患者数',
            '死亡患者数', '総退院患者数'
        ]
        
        # 利用可能な指標のみに絞る
        available_heatmap_metrics = [m for m in heatmap_metrics if m in df.columns]
        
        if available_heatmap_metrics:
            selected_heatmap_metric = st.selectbox(
                "🎯 ヒートマップ表示指標:",
                available_heatmap_metrics,
                index=available_heatmap_metrics.index('総入院患者数') if '総入院患者数' in available_heatmap_metrics else 0,
                key="dow_heatmap_metric_select",
                help="ヒートマップで可視化する指標を選択"
            )

            try:
                if create_dow_heatmap and summary_df_from_calc is not None and not summary_df_from_calc.empty:
                    heatmap_fig = create_dow_heatmap(
                        dow_data=summary_df_from_calc,  # マッピング前のデータを使用
                        metric=selected_heatmap_metric,
                        unit_type=chart_unit_type
                    )
                    
                    if heatmap_fig:
                        st.plotly_chart(heatmap_fig, use_container_width=True)
                        
                        # ヒートマップの読み方説明
                        st.info("💡 **ヒートマップの見方:** 色が濃いほど患者数が多いことを示します。曜日と対象間のパターンを比較できます。")
                    else:
                        st.info("ℹ️ ヒートマップを生成できませんでした。")
                else:
                    st.info("ℹ️ ヒートマップの元となるサマリーデータが不足しています。")
                    
            except Exception as e:
                st.error(f"❌ ヒートマップ生成中にエラーが発生しました: {e}")
                logger.error(f"ヒートマップ生成エラー: {e}")
        else:
            st.warning("⚠️ ヒートマップ表示用の指標が見つかりません。")

    # =================================================================
    # 分析インサイトと傾向
    # =================================================================
    
    st.markdown("### 💡 分析インサイトと傾向")
    
    if summary_df_from_calc is not None and not summary_df_from_calc.empty:
        try:
            insights = []
            
            # 入院患者数のパターン分析
            if '平均入院患者数' in summary_df_from_calc.columns:
                max_day = summary_df_from_calc.loc[summary_df_from_calc['平均入院患者数'].idxmax()]
                min_day = summary_df_from_calc.loc[summary_df_from_calc['平均入院患者数'].idxmin()]
                insights.append(
                    f"入院患者数は **{max_day['曜日名']}曜日** が最も多く（平均 {max_day['平均入院患者数']:.1f}人/日）、"
                    f" **{min_day['曜日名']}曜日** が最も少ない（平均 {min_day['平均入院患者数']:.1f}人/日）傾向があります。"
                )
            elif '入院患者数合計' in summary_df_from_calc.columns:
                max_day = summary_df_from_calc.loc[summary_df_from_calc['入院患者数合計'].idxmax()]
                min_day = summary_df_from_calc.loc[summary_df_from_calc['入院患者数合計'].idxmin()]
                insights.append(
                    f"入院患者数は **{max_day['曜日名']}曜日** が最も多く（合計 {max_day['入院患者数合計']:.0f}人）、"
                    f" **{min_day['曜日名']}曜日** が最も少ない（合計 {min_day['入院患者数合計']:.0f}人）傾向があります。"
                )

            # 退院患者数のパターン分析
            if '平均退院患者数' in summary_df_from_calc.columns:
                max_day = summary_df_from_calc.loc[summary_df_from_calc['平均退院患者数'].idxmax()]
                min_day = summary_df_from_calc.loc[summary_df_from_calc['平均退院患者数'].idxmin()]
                insights.append(
                    f"退院患者数は **{max_day['曜日名']}曜日** が最も多く（平均 {max_day['平均退院患者数']:.1f}人/日）、"
                    f" **{min_day['曜日名']}曜日** が最も少ない（平均 {min_day['平均退院患者数']:.1f}人/日）傾向があります。"
                )
            elif '退院患者数合計' in summary_df_from_calc.columns:
                max_day = summary_df_from_calc.loc[summary_df_from_calc['退院患者数合計'].idxmax()]
                min_day = summary_df_from_calc.loc[summary_df_from_calc['退院患者数合計'].idxmin()]
                insights.append(
                    f"退院患者数は **{max_day['曜日名']}曜日** が最も多く（合計 {max_day['退院患者数合計']:.0f}人）、"
                    f" **{min_day['曜日名']}曜日** が最も少ない（合計 {min_day['退院患者数合計']:.0f}人）傾向があります。"
                )

            # 緊急入院のパターン分析
            if '平均緊急入院患者数' in summary_df_from_calc.columns:
                max_e = summary_df_from_calc.loc[summary_df_from_calc['平均緊急入院患者数'].idxmax()]
                insights.append(
                    f"緊急入院は **{max_e['曜日名']}曜日** に最も多く発生しています（平均 {max_e['平均緊急入院患者数']:.1f}人/日）。"
                )

            # 平日vs週末の比較分析
            if '曜日番号' in summary_df_from_calc.columns:
                weekend = summary_df_from_calc[summary_df_from_calc['曜日番号'] >= 5]
                weekday = summary_df_from_calc[summary_df_from_calc['曜日番号'] < 5]
                
                if not weekend.empty and not weekday.empty:
                    # 入院患者数の平日vs週末比較
                    if '平均入院患者数' in weekend.columns and '平均入院患者数' in weekday.columns:
                        avg_w_e = weekend['平均入院患者数'].mean()
                        avg_w_d = weekday['平均入院患者数'].mean()
                        
                        if pd.notna(avg_w_e) and pd.notna(avg_w_d) and avg_w_e > 0:
                            diff_pct = (avg_w_d - avg_w_e) / avg_w_e * 100
                            
                            if pd.notna(diff_pct):
                                if diff_pct > 20:
                                    insights.append(
                                        f"平日の入院患者数（平均 {avg_w_d:.1f}人/日）は、"
                                        f"週末（平均 {avg_w_e:.1f}人/日）と比較して **{diff_pct:.1f}%多く**、"
                                        f"明確な平日/週末パターンが見られます。"
                                    )
                                elif diff_pct < -20:
                                    insights.append(
                                        f"週末の入院患者数（平均 {avg_w_e:.1f}人/日）は、"
                                        f"平日（平均 {avg_w_d:.1f}人/日）と比較して **{abs(diff_pct):.1f}%多く**、"
                                        f"特徴的な週末集中パターンが見られます。"
                                    )

                    # 退院患者数の平日vs週末比較
                    if '平均退院患者数' in weekend.columns and '平均退院患者数' in weekday.columns:
                        avg_e_w = weekend['平均退院患者数'].mean()
                        avg_w_d2 = weekday['平均退院患者数'].mean()
                        
                        if pd.notna(avg_e_w) and pd.notna(avg_w_d2) and avg_w_d2 > 0 and avg_e_w < avg_w_d2 * 0.3:
                            insights.append(
                                "週末の退院が極めて少なくなっています（"
                                f"週末平均 {avg_e_w:.1f}人/日 vs 平日平均 {avg_w_d2:.1f}人/日）。"
                                "週末の退院支援体制を強化することで、"
                                "患者の利便性向上と月曜日の業務集中を緩和できる可能性があります。"
                            )

            # インサイト表示
            if insights:
                st.markdown("<div class='info-card'>", unsafe_allow_html=True)
                st.markdown("#### 📊 データ分析インサイト")
                for ins in insights:
                    st.markdown(f"- {ins}")
                st.markdown("</div>", unsafe_allow_html=True)

                # 運用改善提案
                st.markdown("<div class='success-card' style='margin-top:1em;'>", unsafe_allow_html=True)
                st.markdown("#### 🎯 運用改善のためのヒント")

                # 入院・退院ピーク分析
                max_adm_col = '平均入院患者数' if '平均入院患者数' in summary_df_from_calc.columns else '入院患者数合計'
                max_dis_col = '平均退院患者数' if '平均退院患者数' in summary_df_from_calc.columns else '退院患者数合計'
                
                if max_adm_col in summary_df_from_calc.columns and max_dis_col in summary_df_from_calc.columns:
                    max_adm = summary_df_from_calc.loc[summary_df_from_calc[max_adm_col].idxmax()]
                    max_dis = summary_df_from_calc.loc[summary_df_from_calc[max_dis_col].idxmax()]
                    
                    if max_adm['曜日名'] == max_dis['曜日名']:
                        st.markdown(
                            f"- 入院と退院のピークが同じ **{max_adm['曜日名']}曜日** に集中している可能性があります。"
                            "業務負荷を分散するために、予定入院の一部を他の曜日にずらす、"
                            "または週末の退院支援を強化することを検討できます。"
                        )

                # 週末退院支援の提案
                if not weekend.empty and not weekday.empty and avg_e_w < avg_w_d2 * 0.3:
                    st.markdown(
                        "- 週末の退院が平日に比べて著しく少ないようです。"
                        "週末の退院プロセスを見直し、スタッフ配置や関連部門との連携を強化することで、"
                        "患者さんの利便性向上や月曜日の業務負荷軽減に繋がる可能性があります。"
                    )

                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("ℹ️ 分析インサイトを生成するための十分なデータパターンが見つかりませんでした。")
                
        except Exception as e:
            st.error(f"❌ 分析インサイト生成中にエラーが発生しました: {e}")
            logger.error(f"分析インサイト生成エラー: {e}")
    else:
        st.info("ℹ️ 分析インサイトを生成するためのサマリーデータがありません。")

    logger.info("曜日別入退院分析タブの処理が完了しました")


def create_fallback_dow_analysis(df, start_date_ts, end_date_ts, selected_metrics):
    """曜日別分析のフォールバック版（統一フィルター対応）"""
    st.info("🔧 dow_charts.py が利用できないため、簡易版の曜日別分析を表示しています。")
    
    if df.empty or '日付' not in df.columns:
        st.warning("📋 分析対象のデータまたは日付列がありません。")
        return
    
    try:
        # 曜日の追加
        df_copy = df.copy()
        df_copy['曜日'] = df_copy['日付'].dt.day_name()
        df_copy['曜日番号'] = df_copy['日付'].dt.dayofweek
        
        # 曜日名を日本語に変換
        dow_mapping = {
            'Monday': '月曜日', 'Tuesday': '火曜日', 'Wednesday': '水曜日',
            'Thursday': '木曜日', 'Friday': '金曜日', 'Saturday': '土曜日', 'Sunday': '日曜日'
        }
        df_copy['曜日'] = df_copy['曜日'].map(dow_mapping)
        
        # 利用可能な患者数列を特定
        if selected_metrics:
            available_metrics = [col for col in selected_metrics if col in df_copy.columns]
        else:
            numeric_columns = df_copy.select_dtypes(include=[np.number]).columns
            available_metrics = [col for col in numeric_columns if '患者数' in col][:3]
        
        if not available_metrics:
            st.warning("📊 分析対象の患者数データが見つかりません。")
            return
        
        # 曜日別集計
        agg_dict = {col: 'mean' for col in available_metrics}
        dow_summary = df_copy.groupby(['曜日', '曜日番号'], observed=True).agg(agg_dict).reset_index()
        dow_summary = dow_summary.sort_values('曜日番号')
        
        # グラフ表示
        import plotly.express as px
        
        fig = px.bar(
            dow_summary,
            x='曜日',
            y=available_metrics,
            title=f"曜日別平均患者数 ({start_date_ts.date()} ～ {end_date_ts.date()})",
            barmode='group'
        )
        fig.update_layout(
            xaxis_title="曜日",
            yaxis_title="平均患者数 (人/日)",
            legend_title="指標"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # テーブル表示
        display_cols = ['曜日'] + available_metrics
        format_dict = {col: "{:.1f}" for col in available_metrics}
        
        st.markdown("#### 📋 曜日別平均患者数")
        st.dataframe(
            dow_summary[display_cols].style.format(format_dict),
            use_container_width=True
        )
        
        # 簡単な分析コメント
        if '総入院患者数' in available_metrics:
            max_admission_day = dow_summary.loc[dow_summary['総入院患者数'].idxmax(), '曜日']
            min_admission_day = dow_summary.loc[dow_summary['総入院患者数'].idxmin(), '曜日']
            
            st.info(f"💡 **簡易分析:** 入院患者数は{max_admission_day}が最多、{min_admission_day}が最少となっています。")
        
    except Exception as e:
        st.error(f"❌ フォールバック版曜日別分析でエラーが発生しました: {e}")
        logger.error(f"フォールバック版曜日別分析エラー: {e}")