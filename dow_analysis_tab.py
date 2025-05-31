# dow_analysis_tab.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import timedelta, date

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

# utils.py から病棟関連および日付フィルタリング用の関数をインポート
from utils import (
    # create_ward_name_mapping, # initialize_all_mappings で処理
    get_ward_display_name,
    create_ward_display_options,
    # initialize_ward_mapping, # initialize_all_mappings で処理
    safe_date_filter, #
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
    曜日別入退院分析タブの表示関数
    """
    st.header("📆 曜日別入退院分析")

    if df is None or df.empty:
        st.warning("データが読み込まれていません。「データ処理」タブでデータを読み込んでください。")
        return

    required_cols = [
        '日付', '病棟コード', '診療科名',
        '総入院患者数', '総退院患者数',
        '入院患者数', '緊急入院患者数', '死亡患者数', '在院患者数' # '在院患者数' はdow_charts.pyのcalculate_dow_summaryで利用される可能性
    ] #
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"曜日別分析に必要な列が不足しています: {', '.join(missing_cols)}") #
        return

    # initialize_ward_mapping(df) # initialize_all_mappings で対応済み

    try:
        start_date_ts = pd.Timestamp(start_date) #
        end_date_ts = pd.Timestamp(end_date) #
    except Exception:
        st.error("渡された開始日または終了日の形式が正しくありません。") #
        return

    st.sidebar.markdown("<hr style='margin-top:1rem; margin-bottom:0.5rem;'>", unsafe_allow_html=True) #
    st.sidebar.markdown(
        "<div class='sidebar-title' style='font-size:1.1rem; margin-bottom:0.5rem;'>曜日別入退院分析 設定</div>", #
        unsafe_allow_html=True
    )

    selected_unit = st.sidebar.selectbox(
        "集計単位:",
        ['病院全体', '診療科別', '病棟別'],
        index=0,
        key="dow_unit_selectbox"
    ) #

    target_items = [] # 内部処理用のコードリスト
    if selected_unit == '病棟別':
        available_wards_codes = sorted(df['病棟コード'].astype(str).unique()) #
        ward_mapping_dict = st.session_state.get('ward_mapping', {}) #
        ward_display_options_list, ward_option_to_code_map = create_ward_display_options(available_wards_codes, ward_mapping_dict) #
        default_selected_wards_display = ward_display_options_list[:min(2, len(ward_display_options_list))] if ward_display_options_list else [] #

        selected_wards_display_names = st.sidebar.multiselect(
            "対象病棟:",
            ward_display_options_list,
            default=default_selected_wards_display,
            key="dow_target_wards_display", # 新しいキー
            help="複数選択可（チャート表示は最大5つ程度推奨）"
        ) #
        target_items = [ward_option_to_code_map[display_name] for display_name in selected_wards_display_names if display_name in ward_option_to_code_map] #

    elif selected_unit == '診療科別':
        available_depts_codes = sorted(df['診療科名'].astype(str).unique()) #
        dept_mapping_dict = st.session_state.get('dept_mapping', {})
        dept_display_options_list, dept_option_to_code_map = create_dept_display_options(available_depts_codes, dept_mapping_dict) #
        default_selected_depts_display = dept_display_options_list[:min(2, len(dept_display_options_list))] if dept_display_options_list else [] #

        selected_depts_display_names = st.sidebar.multiselect(
            "対象診療科:",
            dept_display_options_list,
            default=default_selected_depts_display,
            key="dow_target_depts_display", # 新しいキー
            help="複数選択可（チャート表示は最大5つ程度推奨）"
        ) #
        target_items = [dept_option_to_code_map[display_name] for display_name in selected_depts_display_names if display_name in dept_option_to_code_map] #

    chart_metric_options = [
        '総入院患者数', '総退院患者数',
        '入院患者数', '緊急入院患者数',
        '退院患者数', '死亡患者数', '在院患者数'
    ] #
    valid_chart_metrics = [m for m in chart_metric_options if m in df.columns] #
    selected_metrics = st.sidebar.multiselect(
        "チャート表示指標:",
        valid_chart_metrics,
        default=[m for m in ['総入院患者数', '総退院患者数'] if m in valid_chart_metrics],
        key="dow_chart_metrics_multiselect"
    ) #

    aggregation_ui = st.sidebar.selectbox(
        "集計方法 (チャート/サマリー共通):",
        ["曜日別 平均患者数/日", "曜日別 合計患者数"],
        index=0,
        key="dow_aggregation_selectbox"
    ) #
    metric_type = 'average' if aggregation_ui == "曜日別 平均患者数/日" else 'sum' #

    st.markdown(
        f"<div style='font-size:14px; color:#666; margin-bottom:1rem;'>"
        f"選択期間: {start_date_ts.strftime('%Y年%m月%d日')} ～ {end_date_ts.strftime('%Y年%m月%d日')}"
        f"</div>",
        unsafe_allow_html=True
    ) #

    if selected_unit != '病院全体' and not target_items:
        unit_label = selected_unit.replace('別', '')
        st.warning(f"分析対象の{unit_label}をサイドバーで選択してください。") #
        return

    st.markdown(
        f"<div class='chart-title'>曜日別 患者数パターン ({aggregation_ui})</div>",
        unsafe_allow_html=True
    ) #
    dow_data_for_chart = pd.DataFrame()
    if selected_metrics:
        dow_data_for_chart = get_dow_data(
            df=df,
            unit_type=selected_unit,
            target_items=target_items, # コードリストを渡す
            start_date=start_date_ts,
            end_date=end_date_ts,
            metric_type=metric_type,
            patient_cols_to_analyze=selected_metrics
        ) #

        if dow_data_for_chart is not None and not dow_data_for_chart.empty:
            # チャート表示前に集計単位名を表示名に変換
            display_dow_data_for_chart = dow_data_for_chart.copy()
            if '集計単位名' in display_dow_data_for_chart.columns:
                if selected_unit == '病棟別':
                    ward_map_chart = st.session_state.get('ward_mapping', {})
                    display_dow_data_for_chart['集計単位名'] = display_dow_data_for_chart['集計単位名'].apply(
                        lambda x: get_ward_display_name(x, ward_map_chart)
                    )
                elif selected_unit == '診療科別':
                    dept_map_chart = st.session_state.get('dept_mapping', {})
                    display_dow_data_for_chart['集計単位名'] = display_dow_data_for_chart['集計単位名'].apply(
                        lambda x: get_display_name_for_dept(x, default_name=x, dept_mapping=dept_map_chart)
                    )

            if create_dow_chart: #
                fig = create_dow_chart(
                    dow_data_melted=display_dow_data_for_chart, # 表示名に変換したデータを使用
                    unit_type=selected_unit,
                    # target_items はチャート関数内では直接使われず、dow_data_melted の集計単位名で処理される
                    target_items=[get_display_name_for_dept(ti, ti) if selected_unit == '診療科別' else get_ward_display_name(ti, st.session_state.get('ward_mapping', {})) for ti in target_items] if target_items else ["病院全体"],
                    metric_type=metric_type,
                    patient_cols_to_analyze=selected_metrics
                ) #
                if fig:
                    st.plotly_chart(fig, use_container_width=True) #
                else:
                    st.info("曜日別チャートを生成できませんでした。") #
            else:
                st.warning("チャート生成関数 (create_dow_chart) が利用できません。") #
        else:
            st.info("曜日別チャートを表示するためのデータがありません。") #
    else:
        st.info("チャートに表示する指標が選択されていません。") #

    st.markdown(
        f"<div class='chart-title' style='margin-top:2rem;'>曜日別 詳細サマリー ({aggregation_ui})</div>",
        unsafe_allow_html=True
    ) #

    group_by_col = None
    if selected_unit == '病棟別':
        group_by_col = '病棟コード' #
    elif selected_unit == '診療科別':
        group_by_col = '診療科名' #

    summary_df_from_calc = pd.DataFrame() # 変数名を変更
    if calculate_dow_summary: #
        summary_df_from_calc = calculate_dow_summary(
            df=df,
            start_date=start_date_ts,
            end_date=end_date_ts,
            group_by_column=group_by_col,
            target_items=target_items # コードリストを渡す
        ) #

        if summary_df_from_calc is not None and not summary_df_from_calc.empty:
            # 表示用に集計単位名を変換
            display_summary_df = summary_df_from_calc.copy()
            if '集計単位' in display_summary_df.columns:
                if selected_unit == '病棟別':
                    ward_map_summary = st.session_state.get('ward_mapping', {})
                    display_summary_df['集計単位'] = display_summary_df['集計単位'].apply(
                        lambda x: get_ward_display_name(x, ward_map_summary)
                    )
                elif selected_unit == '診療科別':
                    # dept_map_summary = st.session_state.get('dept_mapping', {}) # この行は不要
                    display_summary_df['集計単位'] = display_summary_df['集計単位'].apply(
                        lambda x: get_display_name_for_dept(x, default_name=x) # dept_mapping引数を削除
                    )
            cols_to_show = ['集計単位', '曜日名', '集計日数'] #
            fmt = {'集計日数': "{:.0f}"} #

            base_metrics = [
                '入院患者数', '緊急入院患者数', '総入院患者数',
                '退院患者数', '死亡患者数', '総退院患者数', '在院患者数'
            ] #
            if metric_type == 'average':
                for bm in base_metrics:
                    col_avg = f"平均{bm}"
                    if col_avg in display_summary_df.columns: # display_summary_df で確認
                        cols_to_show.append(col_avg) #
                        fmt[col_avg] = "{:.1f}" #
            else:  # sum
                for bm in base_metrics:
                    col_sum = f"{bm}合計"
                    if col_sum in display_summary_df.columns: # display_summary_df で確認
                        cols_to_show.append(col_sum) #
                        fmt[col_sum] = "{:.0f}" #

            for rate_col in ['緊急入院率', '死亡退院率']:
                if rate_col in display_summary_df.columns: # display_summary_df で確認
                    cols_to_show.append(rate_col) #
                    fmt[rate_col] = "{:.1f}%" #

            cols_to_show = [c for c in cols_to_show if c in display_summary_df.columns] #

            if cols_to_show and len(cols_to_show) > 3:
                st.dataframe(
                    display_summary_df[cols_to_show].style.format(fmt), # 表示用DFを使用
                    height=min(len(display_summary_df) * 38 + 40, 600)
                ) #
                csv_bytes = display_summary_df[cols_to_show].to_csv(index=False).encode('utf-8-sig') # 表示用DFをCSVに
                st.download_button(
                    label="サマリーデータをCSVダウンロード",
                    data=csv_bytes,
                    file_name=f"曜日別サマリー_{selected_unit}_{start_date_ts.strftime('%Y%m%d')}-{end_date_ts.strftime('%Y%m%d')}.csv",
                    mime='text/csv'
                ) #
            else:
                st.info("表示するサマリー指標がありません。") #
        else:
            st.info("曜日別サマリーデータを表示できませんでした。") #
    else:
        st.warning("サマリー計算関数 (calculate_dow_summary) が利用できません。") #

    if selected_unit != '病院全体' and target_items and len(target_items) > 1:
        st.markdown(
            f"<div class='chart-title' style='margin-top:2rem;'>曜日別 ヒートマップ ({aggregation_ui})</div>",
            unsafe_allow_html=True
        ) #
        heatmap_metrics = [
            '入院患者数', '緊急入院患者数',
            '総入院患者数', '退院患者数',
            '死亡患者数', '総退院患者数'
        ] #
        selected_heatmap_metric = st.selectbox(
            "ヒートマップ表示指標:",
            heatmap_metrics,
            index=heatmap_metrics.index('総入院患者数') if '総入院患者数' in heatmap_metrics else 0,
            key="dow_heatmap_metric_select"
        ) #

        if create_dow_heatmap and summary_df_from_calc is not None and not summary_df_from_calc.empty: # 元の summary_df_from_calc を使用
            heatmap_fig = create_dow_heatmap(
                dow_data=summary_df_from_calc, # マッピング前のデータを使用
                metric=selected_heatmap_metric,
                unit_type=selected_unit # ヒートマップ関数内で表示名変換を行うか、この関数に表示名変換済みのデータを渡すか検討
                                        # create_dow_heatmap は内部でピボットするため、コードのままの方が扱いやすい場合がある
            ) #
            if heatmap_fig:
                st.plotly_chart(heatmap_fig, use_container_width=True) #
            else:
                st.info("ヒートマップを生成できませんでした。") #
        else:
            st.info("ヒートマップの元となるサマリーデータが不足しています。") #

    st.markdown("<div class='section-title'>分析インサイトと傾向</div>", unsafe_allow_html=True) #
    if summary_df_from_calc is not None and not summary_df_from_calc.empty: # 元の summary_df_from_calc で判定
        insights = [] #
        # インサイト生成ロジック (前回レビューで確認済みのため変更なし、ただし summary_df_from_calc を参照する)
        # ... (略)...
        # 以下のロジックは summary_df_from_calc を使用するように注意
        if '平均入院患者数' in summary_df_from_calc.columns: #
            max_day = summary_df_from_calc.loc[summary_df_from_calc['平均入院患者数'].idxmax()] #
            min_day = summary_df_from_calc.loc[summary_df_from_calc['平均入院患者数'].idxmin()] #
            insights.append(
                f"入院患者数は**{max_day['曜日名']}曜日**が最も多く（平均 {max_day['平均入院患者数']:.1f}人/日）、" #
                f"**{min_day['曜日名']}曜日**が最も少ない（平均 {min_day['平均入院患者数']:.1f}人/日）傾向があります。" #
            ) #
        elif '入院患者数合計' in summary_df_from_calc.columns: #
            max_day = summary_df_from_calc.loc[summary_df_from_calc['入院患者数合計'].idxmax()] #
            min_day = summary_df_from_calc.loc[summary_df_from_calc['入院患者数合計'].idxmin()] #
            insights.append(
                f"入院患者数は**{max_day['曜日名']}曜日**が最も多く（合計 {max_day['入院患者数合計']:.0f}人）、" #
                f"**{min_day['曜日名']}曜日**が最も少ない（合計 {min_day['入院患者数合計']:.0f}人）傾向があります。" #
            ) #

        if '平均退院患者数' in summary_df_from_calc.columns: #
            max_day = summary_df_from_calc.loc[summary_df_from_calc['平均退院患者数'].idxmax()] #
            min_day = summary_df_from_calc.loc[summary_df_from_calc['平均退院患者数'].idxmin()] #
            insights.append(
                f"退院患者数は**{max_day['曜日名']}曜日**が最も多く（平均 {max_day['平均退院患者数']:.1f}人/日）、" #
                f"**{min_day['曜日名']}曜日**が最も少ない（平均 {min_day['平均退院患者数']:.1f}人/日）傾向があります。" #
            ) #
        elif '退院患者数合計' in summary_df_from_calc.columns: #
            max_day = summary_df_from_calc.loc[summary_df_from_calc['退院患者数合計'].idxmax()] #
            min_day = summary_df_from_calc.loc[summary_df_from_calc['退院患者数合計'].idxmin()] #
            insights.append(
                f"退院患者数は**{max_day['曜日名']}曜日**が最も多く（合計 {max_day['退院患者数合計']:.0f}人）、" #
                f"**{min_day['曜日名']}曜日**が最も少ない（合計 {min_day['退院患者数合計']:.0f}人）傾向があります。" #
            ) #

        if '平均緊急入院患者数' in summary_df_from_calc.columns: #
            max_e = summary_df_from_calc.loc[summary_df_from_calc['平均緊急入院患者数'].idxmax()] #
            insights.append(
                f"緊急入院は**{max_e['曜日名']}曜日**に最も多く発生しています（平均 {max_e['平均緊急入院患者数']:.1f}人/日）。" #
            ) #

        if '曜日番号' in summary_df_from_calc.columns: #
            weekend = summary_df_from_calc[summary_df_from_calc['曜日番号'] >= 5] #
            weekday = summary_df_from_calc[summary_df_from_calc['曜日番号'] < 5] #
            if not weekend.empty and not weekday.empty and \
               '平均入院患者数' in weekend.columns and '平均入院患者数' in weekday.columns: #

                avg_w_e = weekend['平均入院患者数'].mean() #
                avg_w_d = weekday['平均入院患者数'].mean() #
                if pd.notna(avg_w_e) and pd.notna(avg_w_d) and avg_w_d > 0: #
                    diff_pct = (avg_w_d - avg_w_e) / avg_w_e * 100 if avg_w_e > 0 else np.nan #
                    if pd.notna(diff_pct): #
                        if diff_pct > 20: #
                            insights.append(
                                f"平日の入院患者数（平均 {avg_w_d:.1f}人/日）は、" #
                                f"週末（平均 {avg_w_e:.1f}人/日）と比較して**{diff_pct:.1f}%多く**、" #
                                f"明確な平日/週末パターンが見られます。" #
                            ) #
                        elif diff_pct < -20: #
                            insights.append(
                                f"週末の入院患者数（平均 {avg_w_e:.1f}人/日）は、" #
                                f"平日（平均 {avg_w_d:.1f}人/日）と比較して**{abs(diff_pct):.1f}%多く**、" #
                                f"特徴的な週末集中パターンが見られます。" #
                            ) #

            if not weekend.empty and not weekday.empty and \
               '平均退院患者数' in weekend.columns and '平均退院患者数' in weekday.columns: #
                avg_e_w = weekend['平均退院患者数'].mean() #
                avg_w_d2 = weekday['平均退院患者数'].mean() #
                if pd.notna(avg_e_w) and pd.notna(avg_w_d2) and avg_w_d2 > 0: #
                    if avg_e_w < avg_w_d2 * 0.3: #
                        insights.append(
                            "週末の退院が極めて少なくなっています（" #
                            f"週末平均 {avg_e_w:.1f}人/日 vs 平日平均 {avg_w_d2:.1f}人/日）。" #
                            "週末の退院支援体制を強化することで、" #
                            "患者の利便性向上と月曜日の業務集中を緩和できる可能性があります。" #
                        ) #
        # ... (インサイト表示部分のHTMLも同様) ...
        if insights: #
            st.markdown("<div class='info-card'>", unsafe_allow_html=True) #
            st.markdown("#### <span style='color: #191970;'>インサイト</span>", unsafe_allow_html=True) #
            for ins in insights: #
                st.markdown(f"<p style='margin-bottom:0.5em;'>- {ins}</p>", unsafe_allow_html=True) #
            st.markdown("</div>", unsafe_allow_html=True) #

            st.markdown("<div class='success-card' style='margin-top:1em;'>", unsafe_allow_html=True) #
            st.markdown("#### <span style='color: #006400;'>運用改善のためのヒント</span>", unsafe_allow_html=True) #

            max_adm = summary_df_from_calc.loc[summary_df_from_calc['平均入院患者数'].idxmax()] if '平均入院患者数' in summary_df_from_calc.columns else None #
            max_dis = summary_df_from_calc.loc[summary_df_from_calc['平均退院患者数'].idxmax()] if '平均退院患者数' in summary_df_from_calc.columns else None #
            if max_adm is not None and max_dis is not None: #
                if max_adm['曜日名'] == max_dis['曜日名']: #
                    st.markdown(
                        f"<p style='margin-bottom:0.5em;'>" #
                        f"- 入院と退院のピークが同じ**{max_adm['曜日名']}曜日**に集中している可能性があります。" #
                        "業務負荷を分散するために、予定入院の一部を他の曜日にずらす、" #
                        "または週末の退院支援を強化することを検討できます。</p>", #
                        unsafe_allow_html=True
                    ) #

            if '曜日番号' in summary_df_from_calc.columns and not weekend.empty and not weekday.empty: #
                if '平均退院患者数' in weekend.columns and '平均退院患者数' in weekday.columns: #
                    if pd.notna(weekday['平均退院患者数'].mean()) and weekday['平均退院患者数'].mean() > 0 and \
                       pd.notna(weekend['平均退院患者数'].mean()) and weekend['平均退院患者数'].mean() < weekday['平均退院患者数'].mean() * 0.3: #
                        st.markdown(
                            f"<p style='margin-bottom:0.5em;'>" #
                            "- 週末の退院が平日に比べて著しく少ないようです。" #
                            "週末の退院プロセスを見直し、スタッフ配置や関連部門との連携を強化することで、" #
                            "患者さんの利便性向上や月曜日の業務負荷軽減に繋がる可能性があります。" #
                            "</p>", #
                            unsafe_allow_html=True
                        ) #
            st.markdown("</div>", unsafe_allow_html=True) #
        else:
            st.info("分析インサイトを生成するための十分なデータパターンが見つかりませんでした。") #
    else:
        st.info("分析インサイトを生成するためのサマリーデータがありません。") #


    # 期間比較機能 (前回レビューで確認済み、表示名への対応は上記同様に検討)
    # ... (期間比較のロジックは長いため、主要な修正ポイントのみ示す) ...
    st.markdown(
        f"<div class='chart-title' style='margin-top:2rem;'>期間比較</div>",
        unsafe_allow_html=True
    ) #
    enable_comp = st.checkbox("別の期間と比較する", key="dow_enable_comparison") #
    if enable_comp:
        # ... (日付選択UI: create_safe_comparison_period_selector を utils.py に移管し、呼び出す)
        # from utils import create_safe_comparison_period_selector (既にインポート済み想定)
        # comp_start_date, comp_end_date = create_safe_comparison_period_selector(df, start_date_ts, end_date_ts)
        # 上記の create_safe_comparison_period_selector は utils.py にある想定で、
        # dow_analysis_tab.py 内の期間比較UIロジックを置き換える。
        # 以下は既存のUIロジックを流用しつつ、必要な箇所で表示名を使うイメージ。

        try: #
            data_min_ts = df['日付'].min() #
            data_max_ts = df['日付'].max() #
            data_min_date = data_min_ts.date() #
            data_max_date = data_max_ts.date() #
        except Exception as e: #
            st.error(f"データの日付範囲取得でエラーが発生しました: {e}") #
            return #

        for key in ['dow_comparison_start_date', 'dow_comparison_end_date']: #
            if key in st.session_state: #
                stored = st.session_state[key] #
                if isinstance(stored, date) and (stored < data_min_date or stored > data_max_date): #
                    del st.session_state[key] #
        
        col1_comp, col2_comp = st.columns(2) # col1, col2 -> col1_comp, col2_comp
        with col1_comp:
            sess_start = st.session_state.get("dow_comparison_start_date") #
            ideal_start_ts = start_date_ts - pd.Timedelta(days=365) #
            if sess_start and isinstance(sess_start, date) and data_min_date <= sess_start <= data_max_date: #
                default_start = sess_start #
            elif ideal_start_ts.date() >= data_min_date: #
                default_start = ideal_start_ts.date() #
            else: #
                default_start = min(data_min_date + timedelta(days=90), data_max_date) #
            default_start = max(default_start, data_min_date) #
            default_start = min(default_start, data_max_date) #
            comp_start_date_input = st.date_input(
                "比較期間：開始日",
                value=default_start,
                min_value=data_min_date,
                max_value=data_max_date,
                key="dow_comparison_start_date"
            ) #
            comp_start_date = pd.Timestamp(comp_start_date_input).normalize() #
        with col2_comp:
            sess_end = st.session_state.get("dow_comparison_end_date") #
            period_len = (end_date_ts.date() - start_date_ts.date()).days #
            ideal_end = comp_start_date + timedelta(days=period_len) #
            if sess_end and isinstance(sess_end, date) and data_min_date <= sess_end <= data_max_date and sess_end >= comp_start_date.date(): # comp_start_date を .date() に
                default_end = sess_end #
            elif ideal_end.date() <= data_max_date and ideal_end.date() >= comp_start_date.date(): # ideal_end, comp_start_date を .date() に
                default_end = ideal_end.date() #
            else: #
                default_end = data_max_date #
            default_end = max(default_end, comp_start_date.date()) # comp_start_date を .date() に
            default_end = min(default_end, data_max_date) #
            default_end = max(default_end, data_min_date) #
            comp_end_date_input = st.date_input(
                "比較期間：終了日",
                value=default_end,
                min_value=comp_start_date_input,
                max_value=data_max_date,
                key="dow_comparison_end_date"
            ) #
            comp_end_date = pd.Timestamp(comp_end_date_input).normalize() #

        if st.button("現在期間と同じ長さに設定", key="set_same_length"): #
            length_days = (end_date_ts.date() - start_date_ts.date()).days #
            cur_start = st.session_state.dow_comparison_start_date #
            tgt_end = cur_start + timedelta(days=length_days) #
            if tgt_end > data_max_date: #
                tgt_end = data_max_date #
                cur_start = max(data_min_date, tgt_end - timedelta(days=length_days)) #
            st.session_state.dow_comparison_start_date = cur_start #
            st.session_state.dow_comparison_end_date = tgt_end #
            st.experimental_rerun() #

        if comp_start_date > comp_end_date: #
            st.error("比較期間の終了日は開始日以降に設定してください。") #
            return #

        comp_dow_data = pd.DataFrame() #
        if selected_metrics: #
            comp_dow_data = get_dow_data(
                df=df,
                unit_type=selected_unit,
                target_items=target_items, # コードリストを渡す
                start_date=comp_start_date, # pd.Timestamp を使用
                end_date=comp_end_date,     # pd.Timestamp を使用
                metric_type=metric_type,
                patient_cols_to_analyze=selected_metrics
            ) #

        st.markdown(
            f"<div class='chart-title'>期間比較：曜日別 患者数パターン</div>",
            unsafe_allow_html=True
        ) #
        comp_mode = st.radio(
            "比較表示モード:",
            ["縦に並べて表示", "1つのグラフで比較"],
            key="dow_comparison_display_mode"
        ) #

        if comp_dow_data is not None and not comp_dow_data.empty:
            # 比較チャート表示前に集計単位名を表示名に変換
            display_comp_dow_data = comp_dow_data.copy()
            if '集計単位名' in display_comp_dow_data.columns:
                if selected_unit == '病棟別':
                    ward_map_comp_chart = st.session_state.get('ward_mapping', {})
                    display_comp_dow_data['集計単位名'] = display_comp_dow_data['集計単位名'].apply(
                        lambda x: get_ward_display_name(x, ward_map_comp_chart)
                    )
                elif selected_unit == '診療科別':
                    dept_map_comp_chart = st.session_state.get('dept_mapping', {})
                    display_comp_dow_data['集計単位名'] = display_comp_dow_data['集計単位名'].apply(
                        lambda x: get_display_name_for_dept(x, default_name=x, dept_mapping=dept_map_comp_chart)
                    )
            # display_dow_data_for_chart も再度ここで変換（既に上で変換済みだが念のため）
            display_dow_data_for_chart_comp = dow_data_for_chart.copy()
            if '集計単位名' in display_dow_data_for_chart_comp.columns:
                if selected_unit == '病棟別':
                    ward_map_chart = st.session_state.get('ward_mapping', {})
                    display_dow_data_for_chart_comp['集計単位名'] = display_dow_data_for_chart_comp['集計単位名'].apply(
                        lambda x: get_ward_display_name(x, ward_map_chart)
                    )
                elif selected_unit == '診療科別':
                    # dept_map_chart = st.session_state.get('dept_mapping', {}) # この行は不要
                    display_dow_data_for_chart['集計単位名'] = display_dow_data_for_chart['集計単位名'].apply(
                        lambda x: get_display_name_for_dept(x, default_name=x) # dept_mapping引数を削除
                    )

            if comp_mode == "縦に並べて表示": #
                fig_cur = None
                if not display_dow_data_for_chart_comp.empty:
                    fig_cur = create_dow_chart(
                        dow_data_melted=display_dow_data_for_chart_comp,
                        unit_type=selected_unit,
                        # target_items の表示名変換で dept_mapping を渡さない
                        target_items=[get_display_name_for_dept(ti, default_name=ti) if selected_unit == '診療科別' else get_ward_display_name(ti, st.session_state.get('ward_mapping', {})) for ti in target_items] if target_items else ["病院全体"],
                        metric_type=metric_type,
                        patient_cols_to_analyze=selected_metrics,
                        title_prefix="現在期間"
                    )
                fig_comp = create_dow_chart(
                    dow_data_melted=display_comp_dow_data,
                    unit_type=selected_unit,
                    # target_items の表示名変換で dept_mapping を渡さない
                    target_items=[get_display_name_for_dept(ti, default_name=ti) if selected_unit == '診療科別' else get_ward_display_name(ti, st.session_state.get('ward_mapping', {})) for ti in target_items] if target_items else ["病院全体"],
                    metric_type=metric_type,
                    patient_cols_to_analyze=selected_metrics,
                    title_prefix="比較期間"
                )
                
                if fig_cur and fig_comp: #
                    st.plotly_chart(fig_cur, use_container_width=True) #
                    st.markdown("<div style='text-align:center; margin-bottom:1rem;'>↓ 比較 ↓</div>", unsafe_allow_html=True) #
                    st.plotly_chart(fig_comp, use_container_width=True) #
                    st.markdown(
                        "<div class='info-card'>" #
                        "<p>現在期間と比較期間の曜日パターンを比較して、変化点や傾向の違いを確認できます。</p>" #
                        "</div>", #
                        unsafe_allow_html=True
                    ) #
                else: #
                    st.info("比較グラフを生成できませんでした。") #
            else: # 1つのグラフで比較
                combined = pd.DataFrame() #
                current_name = f"現在期間 ({start_date_ts.strftime('%Y/%m/%d')}～{end_date_ts.strftime('%Y/%m/%d')})" #
                comp_name = f"比較期間 ({comp_start_date.strftime('%Y/%m/%d')}～{comp_end_date.strftime('%Y/%m/%d')})" #

                if not display_dow_data_for_chart_comp.empty: # 表示名変換済みデータを使用
                    display_dow_data_for_chart_comp['期間'] = current_name #
                if not display_comp_dow_data.empty: # 表示名変換済みデータを使用
                    display_comp_dow_data['期間'] = comp_name #

                if not display_dow_data_for_chart_comp.empty and not display_comp_dow_data.empty: #
                    combined = pd.concat([display_dow_data_for_chart_comp, display_comp_dow_data], ignore_index=True) #
                elif not display_dow_data_for_chart_comp.empty: #
                    combined = display_dow_data_for_chart_comp #
                    st.warning("比較期間のデータがありません。現在期間のみ表示します。") #
                elif not display_comp_dow_data.empty: #
                    combined = display_comp_dow_data #
                    st.warning("現在期間のデータがありません。比較期間のみ表示します。") #
                else: #
                    combined = pd.DataFrame() #
                    st.info("表示するデータがありません。") #

                # ... (以降の combined を使ったPlotly Expressのグラフ生成ロジックも、
                #     '集計単位名' が表示名になっていることを前提に動作するはずなので、変更は最小限で済む可能性が高い) ...
                # (多数の行が該当するため、以降このブロックはまとめて参照)
                if not combined.empty:
                    import plotly.express as px
                    combined['曜日'] = pd.Categorical(combined['曜日'], categories=DOW_LABELS, ordered=True)

                    unit_suffix = "平均患者数/日" if metric_type == 'average' else "合計患者数"
                    y_title = f"患者数 ({unit_suffix})"
                    num_units = len(combined['集計単位名'].unique())

                    layout_mode = st.radio(
                        "グラフ表示方法:",
                        ["縦に期間を分けて表示", "横に並べて表示", "期間を同じグラフ内で並べて表示"],
                        key="dow_comparison_graph_layout"
                    )
                    # ... (この中のグラフ生成ロジックは、combined DataFrame の '集計単位名' が表示名になっていることを前提とする)
                    # ... (前回レビューで確認済みのため、表示名対応以外の大きな変更は不要のはず) ...
                    # --- 縦に期間を分けて表示 ---
                    if layout_mode == "縦に期間を分けて表示":
                        if num_units == 1 or selected_unit == '病院全体':
                            fig_all = px.bar(
                                combined,
                                x='曜日',
                                y='患者数',
                                color='指標タイプ',
                                barmode='group',
                                facet_row='期間',
                                labels={'曜日': '曜日', '患者数': y_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_metrics, "期間": [current_name, comp_name]}
                            )
                            fig_all.update_yaxes(matches=None)
                            max_y = combined['患者数'].max() * 1.1 if not combined.empty and '患者数' in combined.columns else 10
                            fig_all.update_yaxes(range=[0, max_y])
                        else:
                            fig_all = px.bar(
                                combined,
                                x='曜日',
                                y='患者数',
                                color='指標タイプ',
                                barmode='group',
                                facet_row='期間',
                                facet_col='集計単位名',
                                facet_col_wrap=min(num_units, 2),
                                labels={'曜日': '曜日', '患者数': y_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_metrics, "期間": [current_name, comp_name]}
                            )
                            y_max_per_unit = combined.groupby('集計単位名')['患者数'].max() if not combined.empty and '集計単位名' in combined.columns and '患者数' in combined.columns else pd.Series()
                            for unit_name, unit_val in y_max_per_unit.items():
                                limit = unit_val * 1.1
                                fig_all.for_each_yaxis(lambda yaxis: yaxis.update(range=[0, limit]) if yaxis.title.text.endswith(f"={unit_name}") else None)
                        num_rows = 2
                        if num_units > 1 and selected_unit != '病院全体':
                            cols_wrap = min(num_units, 2)
                            height = 250 * num_rows * cols_wrap
                        else:
                            height = 250 * num_rows
                    # --- 横に並べて表示 ---
                    elif layout_mode == "横に並べて表示":
                        if num_units == 1 or selected_unit == '病院全体':
                            fig_all = px.bar(
                                combined,
                                x='曜日',
                                y='患者数',
                                color='指標タイプ',
                                barmode='group',
                                facet_col='期間',
                                labels={'曜日': '曜日', '患者数': y_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_metrics, "期間": [current_name, comp_name]}
                            )
                            fig_all.update_yaxes(matches=None)
                            max_y = combined['患者数'].max() * 1.1 if not combined.empty and '患者数' in combined.columns else 10
                            fig_all.update_yaxes(range=[0, max_y])
                        else:
                            fig_all = px.bar(
                                combined,
                                x='曜日',
                                y='患者数',
                                color='指標タイプ',
                                barmode='group',
                                facet_col='期間',
                                facet_row='集計単位名',
                                labels={'曜日': '曜日', '患者数': y_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_metrics, "期間": [current_name, comp_name]}
                            )
                            for idx, unit_name in enumerate(combined['集計単位名'].unique() if not combined.empty and '集計単位名' in combined.columns else []):
                                unit_data = combined[combined['集計単位名'] == unit_name]
                                limit = unit_data['患者数'].max() * 1.1 if not unit_data.empty and '患者数' in unit_data.columns else 10
                                row_idx = idx + 1 # Plotlyのrow/colは1-indexed
                                for col_idx_loop in [1, 2]: # 期間が2つあるので
                                    fig_all.update_yaxes(range=[0, limit], row=row_idx, col=col_idx_loop)
                        if num_units > 1 and selected_unit != '病院全体':
                            height = 250 * num_units
                        else:
                            height = 400
                    # --- 期間を同じグラフ内で並べて表示 ---
                    else:
                        bar_style = st.radio("バースタイル:", ["期間を色分け", "指標タイプを色分け"], key="dow_comparison_bar_style")
                        if bar_style == "期間を色分け":
                            if num_units == 1 or selected_unit == '病院全体':
                                fig_all = px.bar(
                                    combined, x='曜日', y='患者数', color='期間', barmode='group', facet_col='指標タイプ',
                                    labels={'曜日': '曜日', '患者数': y_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                    category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_metrics, "期間": [current_name, comp_name]}
                                )
                            else:
                                if len(selected_metrics) > 1:
                                    sel_metric = st.selectbox("表示する指標:", selected_metrics, key="dow_comparison_metric_selector")
                                    filtered = combined[combined['指標タイプ'] == sel_metric]
                                else:
                                    sel_metric = selected_metrics[0] if selected_metrics else None
                                    filtered = combined[combined['指標タイプ'] == sel_metric] if sel_metric else combined # sel_metricがNoneならcombinedのまま(エラー回避)
                                if not filtered.empty:
                                    fig_all = px.bar(
                                        filtered, x='曜日', y='患者数', color='期間', barmode='group', facet_col='集計単位名',
                                        facet_col_wrap=min(num_units, 3),
                                        labels={'曜日': '曜日', '患者数': y_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                        category_orders={"曜日": DOW_LABELS, "期間": [current_name, comp_name]}
                                    )
                                    for idx, unit_name in enumerate(filtered['集計単位名'].unique() if not filtered.empty and '集計単位名' in filtered.columns else []):
                                        unit_data = filtered[filtered['集計単位名'] == unit_name]
                                        limit = unit_data['患者数'].max() * 1.1 if not unit_data.empty and '患者数' in unit_data.columns else 10
                                        col_idx = (idx % 3) +1
                                        fig_all.update_yaxes(range=[0, limit], col=col_idx) # colは1-indexed
                                else:
                                    fig_all = go.Figure() # 空のグラフ
                                    st.info("選択された指標のデータがありません。")

                        else:  # 「指標タイプを色分け」
                            if num_units == 1 or selected_unit == '病院全体':
                                fig_all = px.bar(
                                    combined, x='曜日', y='患者数', color='指標タイプ', barmode='group', facet_col='期間',
                                    labels={'曜日': '曜日', '患者数': y_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                    category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_metrics, "期間": [current_name, comp_name]}
                                )
                            else:
                                sel_period = st.radio("表示する期間:", [current_name, comp_name], key="dow_comparison_period_selector")
                                period_df = combined[combined['期間'] == sel_period]
                                if not period_df.empty:
                                    fig_all = px.bar(
                                        period_df, x='曜日', y='患者数', color='指標タイプ', barmode='group', facet_col='集計単位名',
                                        facet_col_wrap=min(num_units, 3),
                                        labels={'曜日': '曜日', '患者数': y_title, '集計単位名': '集計単位', '指標タイプ': '指標'},
                                        category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_metrics}
                                    )
                                    fig_all.update_layout(title_text=f"{sel_period} - 曜日別 患者数パターン")
                                else:
                                    fig_all = go.Figure()
                                    st.info("選択された期間のデータがありません。")

                        if num_units > 1 and selected_unit != '病院全体':
                            height = 400 * ((num_units + 2) // 3)
                        else:
                            if len(selected_metrics) > 1 and bar_style == "期間を色分け":
                                height = 400 * ((len(selected_metrics) + 2) // 3)
                            else:
                                height = 500
                    
                    if fig_all is not None: # fig_allが生成された場合のみ
                        height = max(height, 500) if 'height' in locals() else 500
                        height = min(height, 1200)
                        fig_all.update_layout(
                            title_text=f"曜日別 患者数パターン ({unit_suffix}) - 期間比較", title_x=0.5, height=height,
                            font=dict(size=12),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
                            bargap=0.2, plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=20, r=20, t=60, b=20)
                        )
                        fig_all.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray', categoryorder='array', categoryarray=DOW_LABELS)
                        fig_all.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
                        st.plotly_chart(fig_all, use_container_width=True)
                    # ... (期間比較インサイトの表示ロジックも、表示名変換を考慮して修正が必要な場合は行う) ...
                    # (多数の行が該当するため、以降このブロックはまとめて参照)
                    st.markdown("<div class='info-card'>", unsafe_allow_html=True)
                    st.markdown("#### <span style='color: #191970;'>期間比較インサイト</span>", unsafe_allow_html=True)
                    comp_summary_for_insight = None
                    if calculate_dow_summary:
                        filtered_comp_df_insight = safe_date_filter(df, comp_start_date, comp_end_date)
                        if filtered_comp_df_insight is not None and not filtered_comp_df_insight.empty:
                            comp_summary_for_insight = calculate_dow_summary(
                                df=filtered_comp_df_insight, start_date=comp_start_date, end_date=comp_end_date,
                                group_by_column=group_by_col, target_items=target_items # コードで渡す
                            )
                        else:
                            st.info("比較期間のサマリーデータを生成するためのフィルタリング済みデータがありません。")
                    if summary_df_from_calc is not None and not summary_df_from_calc.empty and \
                       comp_summary_for_insight is not None and not comp_summary_for_insight.empty:
                        current_cols_insight = summary_df_from_calc.columns
                        comp_cols_insight = comp_summary_for_insight.columns
                        common_cols_insight = [c for c in current_cols_insight if c in comp_cols_insight]
                        if metric_type == 'average':
                            metric_cols_insight = [c for c in common_cols_insight if c.startswith('平均')]
                        else:
                            metric_cols_insight = [c for c in common_cols_insight if c.endswith('合計')]
                        rate_cols_insight = [c for c in common_cols_insight if c in ['緊急入院率', '死亡退院率']]
                        analysis_cols_insight = metric_cols_insight + rate_cols_insight
                        unique_units_insight = summary_df_from_calc['集計単位'].unique() # これはコードのまま
                        for unit_code_insight in unique_units_insight:
                            # 表示用に変換
                            unit_display_name_insight = get_display_name_for_dept(unit_code_insight, default_name=unit_code_insight) if selected_unit == '診療科別' else get_ward_display_name(unit_code_insight, st.session_state.get('ward_mapping', {}))
                            cur_unit_df_insight = summary_df_from_calc[summary_df_from_calc['集計単位'] == unit_code_insight]
                            comp_unit_df_insight = comp_summary_for_insight[comp_summary_for_insight['集計単位'] == unit_code_insight]
                            if cur_unit_df_insight.empty or comp_unit_df_insight.empty: continue
                            st.markdown(f"##### {unit_display_name_insight} の期間比較:", unsafe_allow_html=True)
                            unit_insights_list = []
                            for col_insight in analysis_cols_insight:
                                disp_insight = col_insight[2:] if col_insight.startswith('平均') else (col_insight[:-2] if col_insight.endswith('合計') else col_insight)
                                try:
                                    cur_max_idx_insight = cur_unit_df_insight[col_insight].idxmax()
                                    comp_max_idx_insight = comp_unit_df_insight[col_insight].idxmax()
                                    cur_max_day_insight = cur_unit_df_insight.loc[cur_max_idx_insight, '曜日名']
                                    comp_max_day_insight = comp_unit_df_insight.loc[comp_max_idx_insight, '曜日名']
                                    if cur_max_day_insight != comp_max_day_insight:
                                        unit_insights_list.append(f"**{disp_insight}** のピーク曜日が変化しています: {comp_max_day_insight}曜日 → {cur_max_day_insight}曜日")
                                except Exception: pass
                                cur_avg_insight = cur_unit_df_insight[col_insight].mean()
                                comp_avg_insight = comp_unit_df_insight[col_insight].mean()
                                if pd.notna(cur_avg_insight) and pd.notna(comp_avg_insight) and comp_avg_insight != 0:
                                    change_pct_insight = (cur_avg_insight - comp_avg_insight) / abs(comp_avg_insight) * 100
                                    if abs(change_pct_insight) >= 15:
                                        direction_insight = "増加" if change_pct_insight > 0 else "減少"
                                        unit_insights_list.append(f"**{disp_insight}** の平均値が {abs(change_pct_insight):.1f}% {direction_insight}しています")
                                for dow_insight in DOW_LABELS:
                                    cur_d_insight = cur_unit_df_insight[cur_unit_df_insight['曜日名'] == dow_insight]
                                    comp_d_insight = comp_unit_df_insight[comp_unit_df_insight['曜日名'] == dow_insight]
                                    if not cur_d_insight.empty and not comp_d_insight.empty:
                                        cur_val_insight = cur_d_insight[col_insight].iloc[0]
                                        comp_val_insight = comp_d_insight[col_insight].iloc[0]
                                        if pd.notna(cur_val_insight) and pd.notna(comp_val_insight) and comp_val_insight != 0:
                                            dow_pct_insight = (cur_val_insight - comp_val_insight) / abs(comp_val_insight) * 100
                                            if abs(dow_pct_insight) >= 30:
                                                direction_insight_dow = "増加" if dow_pct_insight > 0 else "減少"
                                                unit_insights_list.append(f"**{dow_insight}** の **{disp_insight}** が大きく変化: {comp_val_insight:.1f} → {cur_val_insight:.1f} ({abs(dow_pct_insight):.1f}% {direction_insight_dow})")
                            if unit_insights_list:
                                for ui_item in unit_insights_list: st.markdown(f"- {ui_item}", unsafe_allow_html=True)
                            else: st.markdown("- 顕著な変化は見られません", unsafe_allow_html=True)
                            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
                        st.markdown("##### 週末/平日パターンの変化:", unsafe_allow_html=True)
                        weekend_insights_list = []
                        for unit_code_insight_wend in unique_units_insight:
                            unit_display_name_insight_wend = get_display_name_for_dept(unit_code_insight_wend, unit_code_insight_wend) if selected_unit == '診療科別' else get_ward_display_name(unit_code_insight_wend, st.session_state.get('ward_mapping', {}))
                            cur_df_wend = summary_df_from_calc[summary_df_from_calc['集計単位'] == unit_code_insight_wend]
                            comp_df2_wend = comp_summary_for_insight[comp_summary_for_insight['集計単位'] == unit_code_insight_wend]
                            if '曜日番号' not in cur_df_wend.columns or '曜日番号' not in comp_df2_wend.columns: continue
                            cur_wend_data = cur_df_wend[cur_df_wend['曜日番号'] >= 5]
                            cur_wday_data = cur_df_wend[cur_df_wend['曜日番号'] < 5]
                            comp_wend_data = comp_df2_wend[comp_df2_wend['曜日番号'] >= 5]
                            comp_wday_data = comp_df2_wend[comp_df2_wend['曜日番号'] < 5]
                            for col_wend in ['平均入院患者数', '平均退院患者数']:
                                if col_wend in cur_df_wend.columns and col_wend in comp_df2_wend.columns:
                                    cur_wend_avg_val = cur_wend_data[col_wend].mean() if not cur_wend_data.empty else None
                                    cur_wday_avg_val = cur_wday_data[col_wend].mean() if not cur_wday_data.empty else None
                                    comp_wend_avg_val = comp_wend_data[col_wend].mean() if not comp_wend_data.empty else None
                                    comp_wday_avg_val = comp_wday_data[col_wend].mean() if not comp_wday_data.empty else None
                                    if pd.notna(cur_wend_avg_val) and pd.notna(cur_wday_avg_val) and pd.notna(comp_wend_avg_val) and pd.notna(comp_wday_avg_val) and cur_wday_avg_val > 0 and comp_wday_avg_val > 0:
                                        cur_ratio_wend = cur_wend_avg_val / cur_wday_avg_val
                                        comp_ratio_wend = comp_wend_avg_val / comp_wday_avg_val
                                        ratio_change_wend = (cur_ratio_wend - comp_ratio_wend) / comp_ratio_wend * 100 if comp_ratio_wend !=0 else np.nan
                                        if pd.notna(ratio_change_wend) and abs(ratio_change_wend) >= 20:
                                            direction_wend = "縮小" if ratio_change_wend > 0 else "拡大"
                                            weekend_insights_list.append(f"{unit_display_name_insight_wend}の**{col_wend[2:]}**：週末と平日の差が{direction_wend}しています （週末/平日比：{comp_ratio_wend:.2f} → {cur_ratio_wend:.2f}）")
                        if weekend_insights_list:
                            for wi_item in weekend_insights_list: st.markdown(f"- {wi_item}", unsafe_allow_html=True)
                        else: st.markdown("- 週末/平日パターンに顕著な変化は見られません", unsafe_allow_html=True)
                    else:
                        if selected_metrics and not dow_data_for_chart.empty and not comp_dow_data.empty: # dow_data_for_chart -> display_dow_data_for_chart_comp, comp_dow_data -> display_comp_dow_data
                            st.markdown("##### 指標ごとの全体的な変化:", unsafe_allow_html=True)
                            for m_insight in selected_metrics:
                                cur_df_m_insight = display_dow_data_for_chart_comp[display_dow_data_for_chart_comp['指標タイプ'] == m_insight]
                                comp_df_m_insight = display_comp_dow_data[display_comp_dow_data['指標タイプ'] == m_insight]
                                if not cur_df_m_insight.empty and not comp_df_m_insight.empty:
                                    cur_avg_m_insight = cur_df_m_insight['患者数'].mean()
                                    comp_avg_m_insight = comp_df_m_insight['患者数'].mean()
                                    if pd.notna(cur_avg_m_insight) and pd.notna(comp_avg_m_insight) and comp_avg_m_insight != 0:
                                        pct_insight = (cur_avg_m_insight - comp_avg_m_insight) / comp_avg_m_insight * 100
                                        dir_str_insight = "増加" if pct_insight > 0 else "減少"
                                        st.markdown(f"- **{m_insight}** の平均値： {comp_avg_m_insight:.1f} → {cur_avg_m_insight:.1f} ({abs(pct_insight):.1f}% {dir_str_insight})")
                                    else: st.markdown(f"- **{m_insight}** の変化を計算できません（データが不足しています）")
                            st.markdown("##### 曜日パターンの変化:", unsafe_allow_html=True)
                            st.markdown("期間間の曜日パターンを比較して、特に変化が大きい曜日や指標に注目することで、運用方法の改善点を見つけられます。", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                    st.markdown("<div class='success-card' style='margin-top: 1em;'>", unsafe_allow_html=True)
                    st.markdown("#### <span style='color: #006400;'>期間比較からの運用改善ヒント</span>", unsafe_allow_html=True)
                    st.markdown("<p style='margin-bottom: 0.5em;'>- 曜日パターンの変化から運用方法の改善効果を評価できます。例えば、週末の退院支援強化策を実施した場合、その前後の期間を比較することで効果測定が可能です。</p>", unsafe_allow_html=True)
                    st.markdown("<p style='margin-bottom: 0.5em;'>- 特定の曜日に患者数が増加している場合、その曜日のスタッフ配置や業務プロセスを見直すことで、より効率的な運用が可能になります。</p>", unsafe_allow_html=True)
                    st.markdown("<p style='margin-bottom: 0.5em;'>- 期間による変化が大きい場合は、季節性や特定のイベント（例：診療体制の変更、地域の人口動態変化など）の影響を考慮する必要があります。</p>", unsafe_allow_html=True)
                    metric_specific_tips_list = []
                    if '入院患者数' in selected_metrics or '総入院患者数' in selected_metrics:
                        target_metric_insight = '入院患者数' if '入院患者数' in selected_metrics else '総入院患者数'
                        if not display_dow_data_for_chart_comp.empty and not display_comp_dow_data.empty and '指標タイプ' in display_dow_data_for_chart_comp.columns and '指標タイプ' in display_comp_dow_data.columns:
                            current_data_insight = display_dow_data_for_chart_comp[display_dow_data_for_chart_comp['指標タイプ'] == target_metric_insight]
                            comp_data_insight = display_comp_dow_data[display_comp_dow_data['指標タイプ'] == target_metric_insight]
                            if not current_data_insight.empty and not comp_data_insight.empty:
                                for dow_tip in DOW_LABELS:
                                    current_dow_tip = current_data_insight[current_data_insight['曜日'] == dow_tip]['患者数'].mean()
                                    comp_dow_tip = comp_data_insight[comp_data_insight['曜日'] == dow_tip]['患者数'].mean()
                                    if pd.notna(current_dow_tip) and pd.notna(comp_dow_tip) and comp_dow_tip > 0:
                                        change_pct_tip = (current_dow_tip - comp_dow_tip) / comp_dow_tip * 100
                                        if change_pct_tip >= 20: metric_specific_tips_list.append(f"**{dow_tip}の{target_metric_insight}**が{change_pct_tip:.1f}%増加しています。この曜日の入院受け入れ体制を強化し、病床管理や看護配置を最適化することで、質の高いケアを維持できる可能性があります。")
                                        elif change_pct_tip <= -20: metric_specific_tips_list.append(f"**{dow_tip}の{target_metric_insight}**が{abs(change_pct_tip):.1f}%減少しています。この曜日の空床を有効活用するため、外来からの予定入院の調整や他の曜日からの入院シフトを検討できます。")
                    if '退院患者数' in selected_metrics or '総退院患者数' in selected_metrics:
                        target_metric_insight_dis = '退院患者数' if '退院患者数' in selected_metrics else '総退院患者数'
                        if not display_dow_data_for_chart_comp.empty and not display_comp_dow_data.empty and '指標タイプ' in display_dow_data_for_chart_comp.columns and '指標タイプ' in display_comp_dow_data.columns:
                            current_data_insight_dis = display_dow_data_for_chart_comp[display_dow_data_for_chart_comp['指標タイプ'] == target_metric_insight_dis]
                            comp_data_insight_dis = display_comp_dow_data[display_comp_dow_data['指標タイプ'] == target_metric_insight_dis]
                            if not current_data_insight_dis.empty and not comp_data_insight_dis.empty:
                                current_weekend_dis = current_data_insight_dis[current_data_insight_dis['曜日'].isin(['土曜日', '日曜日'])]['患者数'].mean()
                                comp_weekend_dis = comp_data_insight_dis[comp_data_insight_dis['曜日'].isin(['土曜日', '日曜日'])]['患者数'].mean()
                                if pd.notna(current_weekend_dis) and pd.notna(comp_weekend_dis) and comp_weekend_dis > 0:
                                    weekend_change_pct_dis = (current_weekend_dis - comp_weekend_dis) / comp_weekend_dis * 100
                                    if weekend_change_pct_dis >= 30: metric_specific_tips_list.append(f"**週末の{target_metric_insight_dis}**が{weekend_change_pct_dis:.1f}%増加しています。週末の退院支援が強化されたようです。この良い変化を継続・発展させるため、週末の退院調整業務の成功要因を分析し、さらなる最適化を検討できます。")
                                    elif weekend_change_pct_dis <= -30: metric_specific_tips_list.append(f"**週末の{target_metric_insight_dis}**が{abs(weekend_change_pct_dis):.1f}%減少しています。週末の退院支援体制に課題がある可能性があります。薬剤部や医事課など関連部門との連携強化や、退院前カンファレンスの週末実施などの対策が有効かもしれません。")
                    if '緊急入院患者数' in selected_metrics:
                        if not display_dow_data_for_chart_comp.empty and not display_comp_dow_data.empty and '指標タイプ' in display_dow_data_for_chart_comp.columns and '指標タイプ' in display_comp_dow_data.columns:
                            current_data_insight_em = display_dow_data_for_chart_comp[display_dow_data_for_chart_comp['指標タイプ'] == '緊急入院患者数']
                            comp_data_insight_em = display_comp_dow_data[display_comp_dow_data['指標タイプ'] == '緊急入院患者数']
                            if not current_data_insight_em.empty and not comp_data_insight_em.empty:
                                current_avg_em = current_data_insight_em['患者数'].mean()
                                comp_avg_em = comp_data_insight_em['患者数'].mean()
                                if pd.notna(current_avg_em) and pd.notna(comp_avg_em) and comp_avg_em > 0:
                                    change_pct_em = (current_avg_em - comp_avg_em) / comp_avg_em * 100
                                    if abs(change_pct_em) >= 20:
                                        direction_em = "増加" if change_pct_em > 0 else "減少"
                                        metric_specific_tips_list.append(f"**緊急入院患者数**が全体的に{abs(change_pct_em):.1f}%{direction_em}しています。{'緊急対応体制の強化や救急部門との連携見直しが必要かもしれません。' if change_pct_em > 0 else '緊急入院の減少傾向を分析し、地域連携や診療体制に変化があったか確認するとよいでしょう。'}")
                    if metric_specific_tips_list:
                        for tip_item in metric_specific_tips_list: st.markdown(f"<p style='margin-bottom: 0.5em;'>- {tip_item}</p>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("曜日別グラフまたは比較用データが不足しているため、期間比較ができません。") #