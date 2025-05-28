import streamlit as st
import pandas as pd
import numpy as np
import datetime # Ensure datetime is imported if not already
from datetime import timedelta

# dow_charts.py から必要な関数をインポート
try:
    from dow_charts import (
        get_dow_data,
        create_dow_chart,
        calculate_dow_summary,
        create_dow_heatmap,
        DOW_LABELS
    )
except ImportError:
    st.error("dow_charts.py が見つからないか、必要な関数・変数が定義されていません。")
    # フォールバックとしてダミー関数や変数を定義
    get_dow_data = lambda *args, **kwargs: pd.DataFrame()
    create_dow_chart = lambda *args, **kwargs: None
    calculate_dow_summary = lambda *args, **kwargs: pd.DataFrame()
    create_dow_heatmap = lambda *args, **kwargs: None
    DOW_LABELS = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日']

# utils.pyから病棟関連の関数をインポート
from utils import (
    create_ward_name_mapping,
    get_ward_display_name,
    create_ward_display_options,
    initialize_ward_mapping
)

def display_dow_analysis_tab(df, start_date, end_date, common_config=None):
    """
    曜日別入退院分析タブの表示
    
    Parameters:
    -----------
    df : pd.DataFrame
        分析対象のデータフレーム (st.session_state.df を想定)
    start_date : datetime.date or pd.Timestamp
        分析開始日 (st.session_state.sidebar_start_date を想定)
    end_date : datetime.date or pd.Timestamp
        分析終了日 (st.session_state.sidebar_end_date を想定)
    common_config : dict or None, default None
        共通設定（現在は未使用だが将来的な拡張のため残す）
    """
    st.header("📆 曜日別入退院分析")
    
    metric_specific_tips = []

    if df is None or df.empty:
        st.warning("データが読み込まれていません。「データ処理」タブでデータを読み込んでください。")
        return

    required_cols_for_tab = ['日付', '病棟コード', '診療科名', 
                             '総入院患者数', '総退院患者数', 
                             '入院患者数', '緊急入院患者数', '死亡患者数', '在院患者数']
    
    missing_cols = [col for col in required_cols_for_tab if col not in df.columns]
    if missing_cols:
        st.error(f"曜日別分析に必要な列が不足しています: {', '.join(missing_cols)}")
        st.info("データ処理タブでデータが正しく読み込まれ、'総入院患者数' や '総退院患者数' が計算されているか確認してください。")
        return
        
    initialize_ward_mapping(df)
    
    st.sidebar.markdown("<hr style='margin-top:1rem; margin-bottom:0.5rem;'>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-title' style='font-size:1.1rem; margin-bottom:0.5rem;'>曜日別入退院分析 設定</div>", unsafe_allow_html=True)
    
    selected_unit_dow = st.sidebar.selectbox(
        "集計単位:", 
        ['病院全体', '診療科別', '病棟別'], 
        index=0,
        key="dow_unit_selectbox"
    )
    
    target_items_dow = []
    if selected_unit_dow == '病棟別':
        available_items_dow = sorted(df['病棟コード'].astype(str).unique())
        ward_mapping = st.session_state.get('ward_mapping', {})
        ward_options, option_to_code = create_ward_display_options(available_items_dow, ward_mapping)
        default_ward_options = ward_options[:min(2, len(ward_options))] if ward_options else []
        selected_ward_options = st.sidebar.multiselect(
            "対象病棟:", ward_options, default=default_ward_options, 
            key="dow_target_wards_multiselect", help="複数選択可（チャート表示は最大5つ程度推奨）"
        )
        target_items_dow = [option_to_code[option] for option in selected_ward_options]
        
    elif selected_unit_dow == '診療科別':
        available_items_dow = sorted(df['診療科名'].astype(str).unique())
        default_depts = available_items_dow[:min(2, len(available_items_dow))] if available_items_dow else []
        target_items_dow = st.sidebar.multiselect(
            "対象診療科:", available_items_dow, default=default_depts, 
            key="dow_target_depts_multiselect", help="複数選択可（チャート表示は最大5つ程度推奨）"
        )
    
    chart_metrics_options = ['総入院患者数', '総退院患者数', '入院患者数', '緊急入院患者数', '退院患者数', '死亡患者数', '在院患者数']
    valid_chart_metrics_options = [opt for opt in chart_metrics_options if opt in df.columns]
    
    selected_chart_metrics = st.sidebar.multiselect(
        "チャート表示指標:", valid_chart_metrics_options,
        default=[opt for opt in ['総入院患者数', '総退院患者数'] if opt in valid_chart_metrics_options],
        key="dow_chart_metrics_multiselect"
    )

    selected_aggregation_method_ui = st.sidebar.selectbox(
        "集計方法 (チャート/サマリー共通):", 
        ["曜日別 平均患者数/日", "曜日別 合計患者数"], 
        index=0, 
        key="dow_aggregation_selectbox"
    )
    metric_type_for_logic = 'average' if selected_aggregation_method_ui == "曜日別 平均患者数/日" else 'sum'

    # Ensure start_date and end_date are datetime.date objects
    current_display_start_date = start_date.date() if isinstance(start_date, pd.Timestamp) else start_date
    current_display_end_date = end_date.date() if isinstance(end_date, pd.Timestamp) else end_date
    
    st.markdown(f"<div style='font-size: 14px; color: #666; margin-bottom:1rem;'>選択期間: {current_display_start_date.strftime('%Y年%m月%d日')} ～ {current_display_end_date.strftime('%Y年%m月%d日')}</div>", unsafe_allow_html=True)

    if selected_unit_dow != '病院全体' and not target_items_dow:
        st.warning(f"分析対象の{selected_unit_dow.replace('別','')}をサイドバーで選択してください。")
        return
    if not selected_chart_metrics:
        st.warning("チャートに表示する指標を1つ以上選択してください。")

    dow_data_for_chart = get_dow_data(
        df=df, unit_type=selected_unit_dow, target_items=target_items_dow,
        start_date=current_display_start_date, end_date=current_display_end_date,
        metric_type=metric_type_for_logic, patient_cols_to_analyze=selected_chart_metrics
    )
    
    st.markdown(f"<div class='chart-title'>曜日別 患者数パターン ({selected_aggregation_method_ui})</div>", unsafe_allow_html=True)
    if selected_chart_metrics:
        if dow_data_for_chart is not None and not dow_data_for_chart.empty:
            if create_dow_chart:
                dow_chart_fig = create_dow_chart(
                    dow_data_melted=dow_data_for_chart, unit_type=selected_unit_dow,
                    target_items=target_items_dow, metric_type=metric_type_for_logic,
                    patient_cols_to_analyze=selected_chart_metrics
                )
                if dow_chart_fig:
                    st.plotly_chart(dow_chart_fig, use_container_width=True)
                else:
                    st.info("曜日別チャートを生成できませんでした。")
            else:
                st.warning("チャート生成関数 (create_dow_chart) が利用できません。")
        else:
            st.info("曜日別チャートを表示するためのデータがありません。")
    else:
        st.info("チャートに表示する指標が選択されていません。")

    st.markdown(f"<div class='chart-title' style='margin-top: 2rem;'>曜日別 詳細サマリー ({selected_aggregation_method_ui})</div>", unsafe_allow_html=True)
    group_by_col_name = None
    if selected_unit_dow == '病棟別': group_by_col_name = '病棟コード'
    elif selected_unit_dow == '診療科別': group_by_col_name = '診療科名'

    summary_df = None # Initialize summary_df
    if calculate_dow_summary:
        summary_df = calculate_dow_summary(
            df=df, start_date=current_display_start_date, end_date=current_display_end_date,
            group_by_column=group_by_col_name, target_items=target_items_dow
        )

        if summary_df is not None and not summary_df.empty:
            cols_to_show_summary = ['集計単位', '曜日名', '集計日数']
            format_dict_summary = {'集計日数': "{:.0f}"}
            base_metrics_for_summary = ['入院患者数', '緊急入院患者数', '総入院患者数', 
                                        '退院患者数', '死亡患者数', '総退院患者数', '在院患者数']

            if metric_type_for_logic == 'average':
                for bm in base_metrics_for_summary:
                    col_name = f"平均{bm}"
                    if col_name in summary_df.columns:
                        cols_to_show_summary.append(col_name)
                        format_dict_summary[col_name] = "{:.1f}"
            else:
                for bm in base_metrics_for_summary:
                    col_name = f"{bm}合計"
                    if col_name in summary_df.columns:
                        cols_to_show_summary.append(col_name)
                        format_dict_summary[col_name] = "{:.0f}"
            
            rate_cols = ['緊急入院率', '死亡退院率']
            for rc in rate_cols:
                if rc in summary_df.columns:
                    cols_to_show_summary.append(rc)
                    format_dict_summary[rc] = "{:.1f}%"
            
            cols_to_show_summary = [col for col in cols_to_show_summary if col in summary_df.columns]

            if cols_to_show_summary and len(cols_to_show_summary) > 3:
                st.dataframe(
                    summary_df[cols_to_show_summary].style.format(format_dict_summary),
                    height=min(len(summary_df) * 38 + 40, 600)
                )
                csv_summary = summary_df[cols_to_show_summary].to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="サマリーデータをCSVダウンロード", data=csv_summary,
                    file_name=f"曜日別サマリー_{selected_unit_dow}_{current_display_start_date.strftime('%Y%m%d')}-{current_display_end_date.strftime('%Y%m%d')}.csv",
                    mime='text/csv',
                )
            else:
                st.info("表示するサマリー指標がありません。")
        else:
            st.info("曜日別サマリーデータを表示できませんでした。")
    else:
        st.warning("サマリー計算関数 (calculate_dow_summary) が利用できません。")

    if selected_unit_dow != '病院全体' and target_items_dow and len(target_items_dow) > 1:
        st.markdown(f"<div class='chart-title' style='margin-top: 2rem;'>曜日別 ヒートマップ ({selected_aggregation_method_ui})</div>", unsafe_allow_html=True)
        heatmap_metric_options = ['入院患者数', '緊急入院患者数', '総入院患者数', '退院患者数', '死亡患者数', '総退院患者数']
        selected_heatmap_metric = st.selectbox(
            "ヒートマップ表示指標:", heatmap_metric_options,
            index=heatmap_metric_options.index('総入院患者数') if '総入院患者数' in heatmap_metric_options else 0,
            key="dow_heatmap_metric_select"
        )

        if create_dow_heatmap and summary_df is not None and not summary_df.empty:
            heatmap_fig = create_dow_heatmap(
                dow_data=summary_df, metric=selected_heatmap_metric, unit_type=selected_unit_dow
            )
            if heatmap_fig:
                st.plotly_chart(heatmap_fig, use_container_width=True)
            else:
                st.info("ヒートマップを生成できませんでした。データまたは指標を確認してください。")
        elif summary_df is None or summary_df.empty:
             st.info("ヒートマップの元となるサマリーデータがありません。")
        else:
            st.warning("ヒートマップ生成関数 (create_dow_heatmap) が利用できません。")
    
    # --- Analysis Insights (existing code) ---
    st.markdown("<div class='section-title'>分析インサイトと傾向</div>", unsafe_allow_html=True)
    if summary_df is not None and not summary_df.empty:
        insights = []
        if '平均入院患者数' in summary_df.columns:
            max_admission_day = summary_df.loc[summary_df['平均入院患者数'].idxmax()]
            min_admission_day = summary_df.loc[summary_df['平均入院患者数'].idxmin()]
            insights.append(
                f"入院患者数は**{max_admission_day['曜日名']}曜日**が最も多く（平均 {max_admission_day['平均入院患者数']:.1f}人/日）、"
                f"**{min_admission_day['曜日名']}曜日**が最も少ない（平均 {min_admission_day['平均入院患者数']:.1f}人/日）傾向があります。"
            )
        elif '入院患者数合計' in summary_df.columns:
            max_admission_day = summary_df.loc[summary_df['入院患者数合計'].idxmax()]
            min_admission_day = summary_df.loc[summary_df['入院患者数合計'].idxmin()]
            insights.append(
                f"入院患者数は**{max_admission_day['曜日名']}曜日**が最も多く（合計 {max_admission_day['入院患者数合計']:.0f}人）、"
                f"**{min_admission_day['曜日名']}曜日**が最も少ない（合計 {min_admission_day['入院患者数合計']:.0f}人）傾向があります。"
            )
        
        if '平均退院患者数' in summary_df.columns:
            max_discharge_day = summary_df.loc[summary_df['平均退院患者数'].idxmax()]
            min_discharge_day = summary_df.loc[summary_df['平均退院患者数'].idxmin()]
            insights.append(
                f"退院患者数は**{max_discharge_day['曜日名']}曜日**が最も多く（平均 {max_discharge_day['平均退院患者数']:.1f}人/日）、"
                f"**{min_discharge_day['曜日名']}曜日**が最も少ない（平均 {min_discharge_day['平均退院患者数']:.1f}人/日）傾向があります。"
            )
        elif '退院患者数合計' in summary_df.columns:
            max_discharge_day = summary_df.loc[summary_df['退院患者数合計'].idxmax()]
            min_discharge_day = summary_df.loc[summary_df['退院患者数合計'].idxmin()]
            insights.append(
                f"退院患者数は**{max_discharge_day['曜日名']}曜日**が最も多く（合計 {max_discharge_day['退院患者数合計']:.0f}人）、"
                f"**{min_discharge_day['曜日名']}曜日**が最も少ない（合計 {min_discharge_day['退院患者数合計']:.0f}人）傾向があります。"
            )
        
        if '平均緊急入院患者数' in summary_df.columns:
            max_emergency_day = summary_df.loc[summary_df['平均緊急入院患者数'].idxmax()]
            insights.append(
                f"緊急入院は**{max_emergency_day['曜日名']}曜日**に最も多く発生しています（平均 {max_emergency_day['平均緊急入院患者数']:.1f}人/日）。"
            )
        
        if '曜日番号' in summary_df.columns:
            weekend_data = summary_df[summary_df['曜日番号'] >= 5].copy()
            weekday_data = summary_df[summary_df['曜日番号'] < 5].copy()
            if not weekend_data.empty and not weekday_data.empty and \
               '平均入院患者数' in weekend_data.columns and '平均入院患者数' in weekday_data.columns:
                avg_weekend_admission = weekend_data['平均入院患者数'].mean()
                avg_weekday_admission = weekday_data['平均入院患者数'].mean()
                if pd.notna(avg_weekend_admission) and pd.notna(avg_weekday_admission) and avg_weekend_admission > 0: # Check avg_weekend_admission > 0 for division
                    diff_percent = (avg_weekday_admission - avg_weekend_admission) / avg_weekend_admission * 100
                    if pd.notna(diff_percent):
                        if diff_percent > 20:
                            insights.append(
                                f"平日の入院患者数（平均 {avg_weekday_admission:.1f}人/日）は、"
                                f"週末（平均 {avg_weekend_admission:.1f}人/日）と比較して**{diff_percent:.1f}%多く**、"
                                f"明確な平日/週末パターンが見られます。"
                            )
                        elif diff_percent < -20:
                             insights.append(
                                f"週末の入院患者数（平均 {avg_weekend_admission:.1f}人/日）は、"
                                f"平日（平均 {avg_weekday_admission:.1f}人/日）と比較して**{abs(diff_percent):.1f}%多く**、"
                                f"特徴的な週末集中パターンが見られます。"
                            )
            if not weekend_data.empty and not weekday_data.empty and \
               '平均退院患者数' in weekend_data.columns and '平均退院患者数' in weekday_data.columns:
                avg_weekend_discharge = weekend_data['平均退院患者数'].mean()
                avg_weekday_discharge = weekday_data['平均退院患者数'].mean()
                if pd.notna(avg_weekend_discharge) and pd.notna(avg_weekday_discharge) and avg_weekday_discharge > 0:
                    if avg_weekend_discharge < avg_weekday_discharge * 0.3:
                        insights.append(
                            f"週末の退院が極めて少なくなっています（週末平均 {avg_weekend_discharge:.1f}人/日 vs 平日平均 {avg_weekday_discharge:.1f}人/日）。週末の退院支援体制を強化することで、"
                            f"患者の利便性向上と月曜日の業務集中を緩和できる可能性があります。"
                        )
        else:
            st.warning("インサイト生成に必要な '曜日番号' 列がサマリーデータにありません。")
        
        if insights:
            st.markdown("<div class='info-card'>", unsafe_allow_html=True)
            st.markdown("#### <span style='color: #191970;'>インサイト</span>", unsafe_allow_html=True)
            for insight in insights:
                st.markdown(f"<p style='margin-bottom: 0.5em;'>- {insight}</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
            st.markdown("<div class='success-card' style='margin-top: 1em;'>", unsafe_allow_html=True)
            st.markdown("#### <span style='color: #006400;'>運用改善のためのヒント</span>", unsafe_allow_html=True)
            if summary_df is not None and not summary_df.empty and \
               '平均入院患者数' in summary_df.columns and \
               '平均退院患者数' in summary_df.columns and \
               '曜日名' in summary_df.columns:
                max_adm_day_series = summary_df.loc[summary_df['平均入院患者数'].idxmax()]
                max_dis_day_series = summary_df.loc[summary_df['平均退院患者数'].idxmax()]
                if max_adm_day_series['曜日名'] == max_dis_day_series['曜日名']:
                    st.markdown(
                        f"<p style='margin-bottom: 0.5em;'>- 入院と退院のピークが同じ**{max_adm_day_series['曜日名']}曜日**に集中している可能性があります。"
                        f"業務負荷を分散するために、予定入院の一部を他の曜日にずらす、または週末の退院支援を強化することを検討できます。</p>", unsafe_allow_html=True
                    )
                if '曜日番号' in summary_df.columns:
                    weekend_data = summary_df[summary_df['曜日番号'] >= 5].copy() # Re-define for this scope if needed
                    weekday_data = summary_df[summary_df['曜日番号'] < 5].copy() # Re-define for this scope if needed
                    if not weekend_data.empty and not weekday_data.empty:
                         if '平均退院患者数' in weekend_data.columns and '平均退院患者数' in weekday_data.columns and \
                            pd.notna(weekday_data['平均退院患者数'].mean()) and weekday_data['平均退院患者数'].mean() > 0 and \
                            pd.notna(weekend_data['平均退院患者数'].mean()) and \
                            weekend_data['平均退院患者数'].mean() < weekday_data['平均退院患者数'].mean() * 0.3:
                            st.markdown(
                                f"<p style='margin-bottom: 0.5em;'>- 週末の退院が平日に比べて著しく少ないようです。週末の退院プロセスを見直し、"
                                f"スタッフ配置や関連部門との連携を強化することで、患者さんの利便性向上や月曜日の業務負荷軽減に繋がる可能性があります。</p>", unsafe_allow_html=True
                            )
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("分析インサイトを生成するための十分なデータパターンが見つかりませんでした。")
    else:
        st.info("分析インサイトを生成するためのサマリーデータがありません。")


    # --- 期間比較の修正箇所 ---
    st.markdown(f"<div class='chart-title' style='margin-top: 2rem;'>期間比較</div>", unsafe_allow_html=True)
    enable_comparison = st.checkbox("別の期間と比較する", key="dow_enable_comparison")
    
    if enable_comparison:
        min_data_date = df['日付'].min().date()
        max_data_date = df['日付'].max().date()
        
        # Ensure current_display_start_date and current_display_end_date are date objects
        main_period_start = current_display_start_date
        main_period_end = current_display_end_date
        
        period_length_days = (main_period_end - main_period_start).days

        # Initialize session state for comparison dates if they don't exist or to reset them
        # if the main period changes significantly (though this example doesn't track main period change to reset)

        # Default start for comparison: one year before main_period_start
        default_comp_s = main_period_start - timedelta(days=365)
        # Clamp it within data boundaries
        default_comp_s = max(min_data_date, default_comp_s)
        default_comp_s = min(default_comp_s, max_data_date) # Cannot be after max_data_date

        # Default end for comparison: based on clamped default_comp_s + period_length_days
        default_comp_e = default_comp_s + timedelta(days=period_length_days)
        # Clamp it
        default_comp_e = min(max_data_date, default_comp_e)
        
        # If clamping end date made it earlier than start date, adjust start date
        if default_comp_e < default_comp_s:
            default_comp_s = default_comp_e - timedelta(days=period_length_days)
            default_comp_s = max(min_data_date, default_comp_s)
            # Recalculate default_comp_e to be sure (it should hold if period_length_days >=0)
            default_comp_e = default_comp_s + timedelta(days=period_length_days)
            default_comp_e = min(max_data_date, default_comp_e)


        # Ensure start is not after end (can happen if data range is very small)
        if default_comp_s > default_comp_e:
            default_comp_s = default_comp_e


        # Use session state to store and retrieve the comparison dates
        if 'dow_comparison_start_session' not in st.session_state:
            st.session_state.dow_comparison_start_session = default_comp_s
        if 'dow_comparison_end_session' not in st.session_state:
            st.session_state.dow_comparison_end_session = default_comp_e

        # Ensure session state values are within bounds before passing to widget
        # This handles cases where data might have changed, making previous session state values invalid
        
        st.session_state.dow_comparison_start_session = max(min_data_date, min(st.session_state.dow_comparison_start_session, max_data_date))
        st.session_state.dow_comparison_end_session = max(min_data_date, min(st.session_state.dow_comparison_end_session, max_data_date))

        # If, after clamping, start is still > end (e.g., if loaded from an old session state with different data)
        if st.session_state.dow_comparison_start_session > st.session_state.dow_comparison_end_session:
            # Reset to calculated defaults to ensure validity
            st.session_state.dow_comparison_start_session = default_comp_s
            st.session_state.dow_comparison_end_session = default_comp_e
            # And re-clamp just in case defaults were also problematic with new bounds (should not be if calculated as above)
            st.session_state.dow_comparison_start_session = max(min_data_date, min(st.session_state.dow_comparison_start_session, max_data_date))
            st.session_state.dow_comparison_end_session = max(min_data_date, min(st.session_state.dow_comparison_end_session, max_data_date))
            if st.session_state.dow_comparison_start_session > st.session_state.dow_comparison_end_session:
                 st.session_state.dow_comparison_end_session = st.session_state.dow_comparison_start_session


        col1_comp, col2_comp = st.columns(2)
        with col1_comp:
            comp_start_input = st.date_input(
                "比較期間：開始日", 
                value=st.session_state.dow_comparison_start_session,
                min_value=min_data_date,
                max_value=max_data_date,
                key="dow_comparison_start_date_key" # Unique key
            )
            if comp_start_input != st.session_state.dow_comparison_start_session:
                st.session_state.dow_comparison_start_session = comp_start_input
                # Auto-adjust end date to maintain period length
                new_end = comp_start_input + timedelta(days=period_length_days)
                new_end = min(new_end, max_data_date)
                if new_end < comp_start_input : new_end = comp_start_input # Ensure end >= start
                st.session_state.dow_comparison_end_session = new_end
                st.rerun()
        
        with col2_comp:
            comp_end_input = st.date_input(
                "比較期間：終了日", 
                value=st.session_state.dow_comparison_end_session,
                min_value=min_data_date, # Technically should be comp_start_input
                max_value=max_data_date,
                key="dow_comparison_end_date_key" # Unique key
            )
            if comp_end_input != st.session_state.dow_comparison_end_session:
                st.session_state.dow_comparison_end_session = comp_end_input
                # If end date changes, start date is not auto-adjusted to maintain period length by default.
                # User has to adjust start or use the button.
                st.rerun()
        
        if st.button("現在期間と同じ長さに設定", key="set_same_length_dow_button"):
            # Use the current value of the comparison start date from session state
            start_val_for_button = st.session_state.dow_comparison_start_session
            
            new_end_for_button = start_val_for_button + timedelta(days=period_length_days)
            new_end_for_button = min(new_end_for_button, max_data_date)
            if new_end_for_button < start_val_for_button : new_end_for_button = start_val_for_button

            st.session_state.dow_comparison_end_session = new_end_for_button
            st.rerun()
        
        # Use the (potentially updated by widgets or button) session state values for processing
        comp_start_date_for_analysis = st.session_state.dow_comparison_start_session
        comp_end_date_for_analysis = st.session_state.dow_comparison_end_session

        if comp_start_date_for_analysis > comp_end_date_for_analysis:
            st.error("比較期間の終了日は開始日以降に設定してください。")
            return # Or st.stop() to halt further rendering of this tab

        # --- 期間比較のグラフ等表示ロジック (既存のものを流用) ---
        if selected_chart_metrics:
            comp_dow_data = get_dow_data(
                df=df, unit_type=selected_unit_dow, target_items=target_items_dow,
                start_date=comp_start_date_for_analysis, # Use processed date
                end_date=comp_end_date_for_analysis,     # Use processed date
                metric_type=metric_type_for_logic,
                patient_cols_to_analyze=selected_chart_metrics
            )
            
            st.markdown(f"<div class='chart-title'>期間比較：曜日別 患者数パターン</div>", unsafe_allow_html=True)
            comparison_display_mode = st.radio(
                "比較表示モード:", ["縦に並べて表示", "1つのグラフで比較"],
                key="dow_comparison_display_mode"
            )
            
            if comp_dow_data is not None and not comp_dow_data.empty:
                if comparison_display_mode == "縦に並べて表示":
                    current_chart_fig = create_dow_chart(
                        dow_data_melted=dow_data_for_chart, unit_type=selected_unit_dow,
                        target_items=target_items_dow, metric_type=metric_type_for_logic,
                        patient_cols_to_analyze=selected_chart_metrics, title_prefix="現在期間"
                    )
                    comp_chart_fig = create_dow_chart(
                        dow_data_melted=comp_dow_data, unit_type=selected_unit_dow,
                        target_items=target_items_dow, metric_type=metric_type_for_logic,
                        patient_cols_to_analyze=selected_chart_metrics, title_prefix="比較期間"
                    )
                    if current_chart_fig and comp_chart_fig:
                        st.plotly_chart(current_chart_fig, use_container_width=True)
                        st.markdown(f"<div style='text-align: center; margin-bottom: 1rem;'>↓ 比較 ↓</div>", unsafe_allow_html=True)
                        st.plotly_chart(comp_chart_fig, use_container_width=True)
                        st.markdown("<div class='info-card'>", unsafe_allow_html=True)
                        st.markdown("#### <span style='color: #191970;'>期間比較インサイト</span>", unsafe_allow_html=True)
                        st.markdown("現在期間と比較期間の曜日パターンを比較して、変化点や傾向の違いを確認できます。", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        st.info("比較グラフを生成できませんでした。")
                else: # 1つのグラフで比較
                    if dow_data_for_chart is not None and comp_dow_data is not None:
                        current_period_name = f"現在 ({main_period_start.strftime('%y/%m/%d')}～{main_period_end.strftime('%y/%m/%d')})"
                        comp_period_name = f"比較 ({comp_start_date_for_analysis.strftime('%y/%m/%d')}～{comp_end_date_for_analysis.strftime('%y/%m/%d')})"
                        
                        dow_data_for_chart['期間'] = current_period_name
                        comp_dow_data['期間'] = comp_period_name
                        combined_data = pd.concat([dow_data_for_chart, comp_dow_data], ignore_index=True)
                        
                        import plotly.express as px
                        combined_data['曜日'] = pd.Categorical(combined_data['曜日'], categories=DOW_LABELS, ordered=True)
                        unit_suffix = "平均患者数/日" if metric_type_for_logic == 'average' else "合計患者数"
                        y_axis_title = f"患者数 ({unit_suffix})"
                        num_unique_units = len(combined_data['集計単位名'].unique())
                        
                        graph_layout = st.radio(
                            "グラフ表示方法:",
                            ["縦に期間を分けて表示", "横に並べて表示", "期間を同じグラフ内で並べて表示"],
                            key="dow_comparison_graph_layout"
                        )
                        # (以降のグラフ生成ロジックは既存のものを利用)
                        # ... (display_dow_analysis_tab の既存のグラフ生成ロジックをここに展開) ...
                        # Ensure combined_fig is defined within this block based on graph_layout
                        plot_height = 500 # Default height
                        if graph_layout == "縦に期間を分けて表示":
                            if num_unique_units == 1 or selected_unit_dow == '病院全体':
                                combined_fig = px.bar(
                                    combined_data, x='曜日', y='患者数', color='指標タイプ', barmode='group',
                                    facet_row='期間', labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                    category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics, "期間": [current_period_name, comp_period_name]} 
                                )
                                combined_fig.update_yaxes(matches=None)
                                max_y_value = combined_data['患者数'].max() * 1.1
                                combined_fig.update_yaxes(range=[0, max_y_value])
                            else:
                                combined_fig = px.bar(
                                    combined_data, x='曜日', y='患者数', color='指標タイプ', barmode='group',
                                    facet_row='期間', facet_col='集計単位名', facet_col_wrap=min(num_unique_units, 2),
                                    labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                    category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics, "期間": [current_period_name, comp_period_name]} 
                                )
                                combined_fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
                                y_max_per_unit = combined_data.groupby('集計単位名')['患者数'].max()
                                for unit_name_iter in y_max_per_unit.index: # Renamed variable
                                    unit_max_iter = y_max_per_unit[unit_name_iter] * 1.1
                                    # This yaxis update logic might need refinement for facet_col_wrap
                                    # For simplicity, we might not apply individual y-axis limits here if too complex
                            num_facet_rows_calc = 2
                            if num_unique_units > 1 and selected_unit_dow != '病院全体':
                                num_facet_cols_calc = min(num_unique_units, 2)
                                plot_height = 250 * num_facet_rows_calc * ((num_unique_units + num_facet_cols_calc -1) // num_facet_cols_calc) # Approximate height
                            else:
                                plot_height = 250 * num_facet_rows_calc
                        
                        elif graph_layout == "横に並べて表示":
                            if num_unique_units == 1 or selected_unit_dow == '病院全体':
                                combined_fig = px.bar(
                                    combined_data, x='曜日', y='患者数', color='指標タイプ', barmode='group',
                                    facet_col='期間', labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                    category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics, "期間": [current_period_name, comp_period_name]} 
                                )
                                combined_fig.update_yaxes(matches=None)
                                max_y_value = combined_data['患者数'].max() * 1.1
                                combined_fig.update_yaxes(range=[0, max_y_value])
                            else:
                                combined_fig = px.bar(
                                    combined_data, x='曜日', y='患者数', color='指標タイプ', barmode='group',
                                    facet_col='期間', facet_row='集計単位名',
                                    labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                    category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics, "期間": [current_period_name, comp_period_name]} 
                                )
                                combined_fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
                            if num_unique_units > 1 and selected_unit_dow != '病院全体':
                                plot_height = 250 * num_unique_units
                            else:
                                plot_height = 400
                        
                        else:  # "期間を同じグラフ内で並べて表示"
                            bar_style = st.radio("バースタイル:", ["期間を色分け", "指標タイプを色分け"], key="dow_comparison_bar_style")
                            if bar_style == "期間を色分け":
                                if num_unique_units == 1 or selected_unit_dow == '病院全体':
                                    combined_fig = px.bar(
                                        combined_data, x='曜日', y='患者数', color='期間', barmode='group', facet_col='指標タイプ',
                                        labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                        category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics, "期間": [current_period_name, comp_period_name]} 
                                    )
                                else:
                                    selected_metric_for_display = selected_chart_metrics[0]
                                    if len(selected_chart_metrics) > 1:
                                        selected_metric_for_display = st.selectbox("表示する指標:", selected_chart_metrics, key="dow_comparison_metric_selector")
                                    metric_filtered_data = combined_data[combined_data['指標タイプ'] == selected_metric_for_display]
                                    combined_fig = px.bar(
                                        metric_filtered_data, x='曜日', y='患者数', color='期間', barmode='group', facet_col='集計単位名',
                                        facet_col_wrap=min(num_unique_units, 3),
                                        labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                        category_orders={"曜日": DOW_LABELS, "期間": [current_period_name, comp_period_name]} 
                                    )
                                    combined_fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
                            else:  # "指標タイプを色分け"
                                if num_unique_units == 1 or selected_unit_dow == '病院全体':
                                    combined_fig = px.bar(
                                        combined_data, x='曜日', y='患者数', color='指標タイプ', barmode='group', facet_col='期間',
                                        labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                        category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics, "期間": [current_period_name, comp_period_name]} 
                                    )
                                else:
                                    selected_period_display = current_period_name # Default
                                    if len(combined_data['期間'].unique()) > 1:
                                         selected_period_display = st.radio("表示する期間:", combined_data['期間'].unique(), key="dow_comparison_period_selector")
                                    period_filtered_data = combined_data[combined_data['期間'] == selected_period_display]
                                    combined_fig = px.bar(
                                        period_filtered_data, x='曜日', y='患者数', color='指標タイプ', barmode='group', facet_col='集計単位名',
                                        facet_col_wrap=min(num_unique_units, 3),
                                        labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標'},
                                        category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics} 
                                    )
                                    combined_fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
                                    combined_fig.update_layout(title_text=f"{selected_period_display} - 曜日別 患者数パターン")
                            
                            if num_unique_units > 1 and selected_unit_dow != '病院全体':
                                plot_height = 400 * ((num_unique_units + 2) // 3)
                            else:
                                if len(selected_chart_metrics) > 1 and bar_style == "期間を色分け":
                                    plot_height = 400 * ((len(selected_chart_metrics) + 2) // 3)
                                else:
                                    plot_height = 500
                        
                        plot_height = max(plot_height, 500)
                        plot_height = min(plot_height, 1200)
                        
                        combined_fig.update_layout(
                            title_text=f"曜日別 患者数パターン ({unit_suffix}) - 期間比較", title_x=0.5, height=plot_height,
                            font=dict(size=12), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
                            bargap=0.2, plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=20, r=20, t=60, b=20),
                        )
                        combined_fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray', categoryorder='array', categoryarray=DOW_LABELS)
                        combined_fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
                        st.plotly_chart(combined_fig, use_container_width=True)
                        
                        # --- 期間比較インサイト (既存のものを流用) ---
                        st.markdown("<div class='info-card'>", unsafe_allow_html=True)
                        st.markdown("#### <span style='color: #191970;'>期間比較インサイト</span>", unsafe_allow_html=True)
                        comp_summary_df = None
                        if calculate_dow_summary:
                            comp_summary_df = calculate_dow_summary(
                                df=df, start_date=comp_start_date_for_analysis, end_date=comp_end_date_for_analysis,
                                group_by_column=group_by_col_name, target_items=target_items_dow
                            )
                        
                        if summary_df is not None and comp_summary_df is not None and not summary_df.empty and not comp_summary_df.empty:
                            current_cols = summary_df.columns
                            comp_cols_list = comp_summary_df.columns # Renamed variable
                            common_cols = [col for col in current_cols if col in comp_cols_list]
                            metric_cols = []
                            if metric_type_for_logic == 'average':
                                metric_cols = [col for col in common_cols if col.startswith('平均')]
                            else:
                                metric_cols = [col for col in common_cols if col.endswith('合計')]
                            rate_cols_analysis = [col for col in common_cols if col in ['緊急入院率', '死亡退院率']] # Renamed variable
                            analysis_cols = metric_cols + rate_cols_analysis
                            unique_units_analysis = summary_df['集計単位'].unique() # Renamed variable
                            
                            for unit_iter in unique_units_analysis: # Renamed variable
                                unit_current = summary_df[summary_df['集計単位'] == unit_iter]
                                unit_comp = comp_summary_df[comp_summary_df['集計単位'] == unit_iter]
                                if not unit_current.empty and not unit_comp.empty:
                                    st.markdown(f"##### {unit_iter} の期間比較:", unsafe_allow_html=True)
                                    unit_insights = []
                                    for col_iter in analysis_cols: # Renamed variable
                                        display_name = col_iter
                                        if col_iter.startswith('平均'): display_name = col_iter[2:]
                                        elif col_iter.endswith('合計'): display_name = col_iter[:-2]
                                        
                                        current_max_idx = unit_current[col_iter].idxmax() if not unit_current[col_iter].empty else None
                                        comp_max_idx = unit_comp[col_iter].idxmax() if not unit_comp[col_iter].empty else None
                                        
                                        if current_max_idx is not None and comp_max_idx is not None:
                                            current_max_day = unit_current.loc[current_max_idx, '曜日名']
                                            comp_max_day = unit_comp.loc[comp_max_idx, '曜日名']
                                            if current_max_day != comp_max_day:
                                                unit_insights.append(f"**{display_name}** のピーク曜日が変化: {comp_max_day}曜日 → {current_max_day}曜日")
                                        
                                        current_avg = unit_current[col_iter].mean()
                                        comp_avg = unit_comp[col_iter].mean()
                                        if pd.notna(current_avg) and pd.notna(comp_avg) and abs(comp_avg) > 1e-6: # Avoid division by zero
                                            change_pct = (current_avg - comp_avg) / abs(comp_avg) * 100
                                            if abs(change_pct) >= 15:
                                                change_direction = "増加" if change_pct > 0 else "減少"
                                                unit_insights.append(f"**{display_name}** の平均値が {abs(change_pct):.1f}% {change_direction}")
                                        
                                        for dow_iter in DOW_LABELS: # Renamed variable
                                            current_dow_data = unit_current[unit_current['曜日名'] == dow_iter]
                                            comp_dow_data = unit_comp[unit_comp['曜日名'] == dow_iter]
                                            if not current_dow_data.empty and not comp_dow_data.empty:
                                                current_val = current_dow_data[col_iter].iloc[0]
                                                comp_val = comp_dow_data[col_iter].iloc[0]
                                                if pd.notna(current_val) and pd.notna(comp_val) and abs(comp_val) > 1e-6: # Avoid division by zero
                                                    dow_change_pct = (current_val - comp_val) / abs(comp_val) * 100
                                                    if abs(dow_change_pct) >= 30:
                                                        change_direction = "増加" if dow_change_pct > 0 else "減少"
                                                        unit_insights.append(f"**{dow_iter}** の **{display_name}** が変化: {comp_val:.1f} → {current_val:.1f} ({abs(dow_change_pct):.1f}% {change_direction})")
                                    if unit_insights:
                                        for insight_item in unit_insights: st.markdown(f"- {insight_item}", unsafe_allow_html=True) # Renamed variable
                                    else: st.markdown("- 顕著な変化は見られません", unsafe_allow_html=True)
                                    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
                            
                            st.markdown("##### 週末/平日パターンの変化:", unsafe_allow_html=True)
                            weekend_pattern_insights = []
                            for unit_iter_pattern in unique_units_analysis: # Renamed variable
                                unit_current_pattern = summary_df[summary_df['集計単位'] == unit_iter_pattern] # Renamed variable
                                unit_comp_pattern = comp_summary_df[comp_summary_df['集計単位'] == unit_iter_pattern] # Renamed variable
                                if '曜日番号' in unit_current_pattern.columns and '曜日番号' in unit_comp_pattern.columns:
                                    current_weekend = unit_current_pattern[unit_current_pattern['曜日番号'] >= 5]
                                    current_weekday = unit_current_pattern[unit_current_pattern['曜日番号'] < 5]
                                    comp_weekend = unit_comp_pattern[unit_comp_pattern['曜日番号'] >= 5]
                                    comp_weekday = unit_comp_pattern[unit_comp_pattern['曜日番号'] < 5]
                                    for col_pattern in ['平均入院患者数', '平均退院患者数']: # Renamed variable
                                        if col_pattern in unit_current_pattern.columns and col_pattern in unit_comp_pattern.columns:
                                            display_name_pattern = col_pattern[2:] # Renamed variable
                                            current_weekend_avg = current_weekend[col_pattern].mean() if not current_weekend.empty else None
                                            current_weekday_avg = current_weekday[col_pattern].mean() if not current_weekday.empty else None
                                            comp_weekend_avg = comp_weekend[col_pattern].mean() if not comp_weekend.empty else None
                                            comp_weekday_avg = comp_weekday[col_pattern].mean() if not comp_weekday.empty else None
                                            if (pd.notna(current_weekend_avg) and pd.notna(current_weekday_avg) and
                                                pd.notna(comp_weekend_avg) and pd.notna(comp_weekday_avg) and
                                                abs(current_weekday_avg) > 1e-6 and abs(comp_weekday_avg) > 1e-6): # Avoid division by zero
                                                current_ratio = current_weekend_avg / current_weekday_avg
                                                comp_ratio = comp_weekend_avg / comp_weekday_avg
                                                if abs(comp_ratio) > 1e-6: # Avoid division by zero for ratio_change
                                                    ratio_change = (current_ratio - comp_ratio) / comp_ratio * 100
                                                    if abs(ratio_change) >= 20:
                                                        direction_text = "差が縮小" if ratio_change > 0 else "差が拡大" # Simplified
                                                        weekend_pattern_insights.append(
                                                            f"{unit_iter_pattern}の**{display_name_pattern}**：週末と平日の{direction_text}（週末/平日比：{comp_ratio:.2f} → {current_ratio:.2f}）"
                                                        )
                            if weekend_pattern_insights:
                                for insight_item_pattern in weekend_pattern_insights: st.markdown(f"- {insight_item_pattern}", unsafe_allow_html=True) # Renamed variable
                            else: st.markdown("- 週末/平日パターンに顕著な変化は見られません", unsafe_allow_html=True)
                        else:
                            if selected_chart_metrics:
                                st.markdown("##### 指標ごとの全体的な変化:", unsafe_allow_html=True)
                                for metric_iter in selected_chart_metrics: # Renamed variable
                                    current_data_metric = dow_data_for_chart[dow_data_for_chart['指標タイプ'] == metric_iter] # Renamed variable
                                    comp_data_metric = comp_dow_data[comp_dow_data['指標タイプ'] == metric_iter] # Renamed variable
                                    if not current_data_metric.empty and not comp_data_metric.empty:
                                        current_avg_metric = current_data_metric['患者数'].mean() # Renamed variable
                                        comp_avg_metric = comp_data_metric['患者数'].mean() # Renamed variable
                                        if pd.notna(current_avg_metric) and pd.notna(comp_avg_metric) and abs(comp_avg_metric) > 1e-6: # Avoid division by zero
                                            change_pct_metric = (current_avg_metric - comp_avg_metric) / comp_avg_metric * 100 # Renamed variable
                                            change_direction_metric = "増加" if change_pct_metric > 0 else "減少" # Renamed variable
                                            st.markdown(f"- **{metric_iter}** の平均値： {comp_avg_metric:.1f} → {current_avg_metric:.1f} ({abs(change_pct_metric):.1f}% {change_direction_metric})")
                                        else: st.markdown(f"- **{metric_iter}** の変化を計算できません")
                                st.markdown("##### 曜日パターンの変化:", unsafe_allow_html=True)
                                st.markdown("期間間の曜日パターンを比較して、特に変化が大きい曜日や指標に注目することで、運用方法の改善点を見つけられます。", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        st.markdown("<div class='success-card' style='margin-top: 1em;'>", unsafe_allow_html=True)
                        st.markdown("#### <span style='color: #006400;'>期間比較からの運用改善ヒント</span>", unsafe_allow_html=True)
                        metric_specific_tips = [] # Ensure initialized
                        st.markdown("<p style='margin-bottom: 0.5em;'>- 曜日パターンの変化から運用方法の改善効果を評価できます...</p>", unsafe_allow_html=True)
                        st.markdown("<p style='margin-bottom: 0.5em;'>- 特定の曜日に患者数が増加している場合...</p>", unsafe_allow_html=True)
                        st.markdown("<p style='margin-bottom: 0.5em;'>- 期間による変化が大きい場合は...</p>", unsafe_allow_html=True)
                        if dow_data_for_chart is not None and comp_dow_data is not None:
                            metric_specific_tips = []
                            # ... (Existing logic for metric_specific_tips with unique variable names if needed)
                        if metric_specific_tips:
                            for tip_item in metric_specific_tips: st.markdown(f"<p style='margin-bottom: 0.5em;'>- {tip_item}</p>", unsafe_allow_html=True) # Renamed variable
                        st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("比較グラフを生成するためのデータが不足しています。")