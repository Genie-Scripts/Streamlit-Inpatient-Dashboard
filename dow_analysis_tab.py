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
    create_ward_name_mapping,
    get_ward_display_name,
    create_ward_display_options,
    initialize_all_mappings,
    safe_date_filter
)

def display_dow_analysis_tab(
    df: pd.DataFrame,
    start_date,
    end_date,
    common_config=None
):
    """
    曜日別入退院分析タブの表示関数

    引数:
        df: Pandas DataFrame - 日付／病棟コード／診療科名などを含むデータフレーム
        start_date: 日付文字列または pd.Timestamp - 分析対象開始日
        end_date: 日付文字列または pd.Timestamp - 分析対象終了日
        common_config: 任意の設定情報（現在は未使用）
    """
    st.header("📆 曜日別入退院分析")

    # ---- データ存在チェック ----
    if df is None or df.empty:
        st.warning("データが読み込まれていません。「データ処理」タブでデータを読み込んでください。")
        return

    # ---- 必須カラムのチェック ----
    required_cols = [
        '日付', '病棟コード', '診療科名',
        '総入院患者数', '総退院患者数',
        '入院患者数', '緊急入院患者数', '死亡患者数', '在院患者数'
    ]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.error(f"曜日別分析に必要な列が不足しています: {', '.join(missing_cols)}")
        return

    # ---- 病棟マッピング初期化 ----
    initialize_all_mappings(df)

    # ---- 開始日／終了日を Pandas Timestamp に統一 ----
    try:
        start_date_ts = pd.Timestamp(start_date)
        end_date_ts = pd.Timestamp(end_date)
    except Exception:
        st.error("渡された開始日または終了日の形式が正しくありません。")
        return

    # サイドバーに設定用の区切り線とタイトルを表示
    st.sidebar.markdown("<hr style='margin-top:1rem; margin-bottom:0.5rem;'>", unsafe_allow_html=True)
    st.sidebar.markdown(
        "<div class='sidebar-title' style='font-size:1.1rem; margin-bottom:0.5rem;'>曜日別入退院分析 設定</div>",
        unsafe_allow_html=True
    )

    # ---- 集計単位の選択 ----
    selected_unit = st.sidebar.selectbox(
        "集計単位:",
        ['病院全体', '診療科別', '病棟別'],
        index=0,
        key="dow_unit_selectbox"
    )

    target_items = []
    if selected_unit == '病棟別':
        available_wards = sorted(df['病棟コード'].astype(str).unique())
        ward_mapping = st.session_state.get('ward_mapping', {})
        ward_options, option_to_code = create_ward_display_options(available_wards, ward_mapping)
        default_selected = ward_options[:min(2, len(ward_options))] if ward_options else []
        selected_wards = st.sidebar.multiselect(
            "対象病棟:",
            ward_options,
            default=default_selected,
            key="dow_target_wards_multiselect",
            help="複数選択可（チャート表示は最大5つ程度推奨）"
        )
        target_items = [option_to_code[w] for w in selected_wards]

    elif selected_unit == '診療科別':
        available_depts = sorted(df['診療科名'].astype(str).unique())
        default_depts = available_depts[:min(2, len(available_depts))] if available_depts else []
        selected_depts = st.sidebar.multiselect(
            "対象診療科:",
            available_depts,
            default=default_depts,
            key="dow_target_depts_multiselect",
            help="複数選択可（チャート表示は最大5つ程度推奨）"
        )
        target_items = selected_depts

    # ---- チャートに表示する指標の選択 ----
    chart_metric_options = [
        '総入院患者数', '総退院患者数',
        '入院患者数', '緊急入院患者数',
        '退院患者数', '死亡患者数', '在院患者数'
    ]
    valid_chart_metrics = [m for m in chart_metric_options if m in df.columns]
    selected_metrics = st.sidebar.multiselect(
        "チャート表示指標:",
        valid_chart_metrics,
        default=[m for m in ['総入院患者数', '総退院患者数'] if m in valid_chart_metrics],
        key="dow_chart_metrics_multiselect"
    )

    # ---- 集計方法の選択（平均 or 合計） ----
    aggregation_ui = st.sidebar.selectbox(
        "集計方法 (チャート/サマリー共通):",
        ["曜日別 平均患者数/日", "曜日別 合計患者数"],
        index=0,
        key="dow_aggregation_selectbox"
    )
    metric_type = 'average' if aggregation_ui == "曜日別 平均患者数/日" else 'sum'

    # 選択期間を画面に表示
    st.markdown(
        f"<div style='font-size:14px; color:#666; margin-bottom:1rem;'>"
        f"選択期間: {start_date_ts.strftime('%Y年%m月%d日')} ～ {end_date_ts.strftime('%Y年%m月%d日')}"
        f"</div>",
        unsafe_allow_html=True
    )

    # 対象ユニットが未選択の場合は警告して終了
    if selected_unit != '病院全体' and not target_items:
        unit_label = selected_unit.replace('別', '')
        st.warning(f"分析対象の{unit_label}をサイドバーで選択してください。")
        return

    #
    # ===== 1. 曜日別チャートデータの取得と表示 =====
    #
    st.markdown(
        f"<div class='chart-title'>曜日別 患者数パターン ({aggregation_ui})</div>",
        unsafe_allow_html=True
    )
    dow_data_for_chart = pd.DataFrame()
    if selected_metrics:
        dow_data_for_chart = get_dow_data(
            df=df,
            unit_type=selected_unit,
            target_items=target_items,
            start_date=start_date_ts,
            end_date=end_date_ts,
            metric_type=metric_type,
            patient_cols_to_analyze=selected_metrics
        )

        if dow_data_for_chart is not None and not dow_data_for_chart.empty:
            if create_dow_chart:
                fig = create_dow_chart(
                    dow_data_melted=dow_data_for_chart,
                    unit_type=selected_unit,
                    target_items=target_items,
                    metric_type=metric_type,
                    patient_cols_to_analyze=selected_metrics
                )
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("曜日別チャートを生成できませんでした。")
            else:
                st.warning("チャート生成関数 (create_dow_chart) が利用できません。")
        else:
            st.info("曜日別チャートを表示するためのデータがありません。")
    else:
        st.info("チャートに表示する指標が選択されていません。")

    #
    # ===== 2. 曜日別詳細サマリーの取得と表示 =====
    #
    st.markdown(
        f"<div class='chart-title' style='margin-top:2rem;'>曜日別 詳細サマリー ({aggregation_ui})</div>",
        unsafe_allow_html=True
    )

    # group_by 用の列名を設定
    group_by_col = None
    if selected_unit == '病棟別':
        group_by_col = '病棟コード'
    elif selected_unit == '診療科別':
        group_by_col = '診療科名'

    summary_df = pd.DataFrame()
    if calculate_dow_summary:
        summary_df = calculate_dow_summary(
            df=df,
            start_date=start_date_ts,
            end_date=end_date_ts,
            group_by_column=group_by_col,
            target_items=target_items
        )

        if summary_df is not None and not summary_df.empty:
            # 表示する列とフォーマットを決定
            cols_to_show = ['集計単位', '曜日名', '集計日数']
            fmt = {'集計日数': "{:.0f}"}

            base_metrics = [
                '入院患者数', '緊急入院患者数', '総入院患者数',
                '退院患者数', '死亡患者数', '総退院患者数', '在院患者数'
            ]
            if metric_type == 'average':
                for bm in base_metrics:
                    col_avg = f"平均{bm}"
                    if col_avg in summary_df.columns:
                        cols_to_show.append(col_avg)
                        fmt[col_avg] = "{:.1f}"
            else:  # sum
                for bm in base_metrics:
                    col_sum = f"{bm}合計"
                    if col_sum in summary_df.columns:
                        cols_to_show.append(col_sum)
                        fmt[col_sum] = "{:.0f}"

            for rate_col in ['緊急入院率', '死亡退院率']:
                if rate_col in summary_df.columns:
                    cols_to_show.append(rate_col)
                    fmt[rate_col] = "{:.1f}%"

            # 実際に存在する列だけをフィルタ
            cols_to_show = [c for c in cols_to_show if c in summary_df.columns]

            if cols_to_show and len(cols_to_show) > 3:
                st.dataframe(
                    summary_df[cols_to_show].style.format(fmt),
                    height=min(len(summary_df) * 38 + 40, 600)
                )
                csv_bytes = summary_df[cols_to_show].to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="サマリーデータをCSVダウンロード",
                    data=csv_bytes,
                    file_name=f"曜日別サマリー_{selected_unit}_{start_date_ts.strftime('%Y%m%d')}-{end_date_ts.strftime('%Y%m%d')}.csv",
                    mime='text/csv'
                )
            else:
                st.info("表示するサマリー指標がありません。")
        else:
            st.info("曜日別サマリーデータを表示できませんでした。")
    else:
        st.warning("サマリー計算関数 (calculate_dow_summary) が利用できません。")

    #
    # ===== 3. ヒートマップ表示 =====
    #
    if selected_unit != '病院全体' and target_items and len(target_items) > 1:
        st.markdown(
            f"<div class='chart-title' style='margin-top:2rem;'>曜日別 ヒートマップ ({aggregation_ui})</div>",
            unsafe_allow_html=True
        )
        heatmap_metrics = [
            '入院患者数', '緊急入院患者数',
            '総入院患者数', '退院患者数',
            '死亡患者数', '総退院患者数'
        ]
        selected_heatmap_metric = st.selectbox(
            "ヒートマップ表示指標:",
            heatmap_metrics,
            index=heatmap_metrics.index('総入院患者数') if '総入院患者数' in heatmap_metrics else 0,
            key="dow_heatmap_metric_select"
        )

        if create_dow_heatmap and not summary_df.empty:
            heatmap_fig = create_dow_heatmap(
                dow_data=summary_df,
                metric=selected_heatmap_metric,
                unit_type=selected_unit
            )
            if heatmap_fig:
                st.plotly_chart(heatmap_fig, use_container_width=True)
            else:
                st.info("ヒートマップを生成できませんでした。")
        else:
            st.info("ヒートマップの元となるサマリーデータが不足しています。")

    #
    # ===== 4. 分析インサイト =====
    #
    st.markdown("<div class='section-title'>分析インサイトと傾向</div>", unsafe_allow_html=True)
    if not summary_df.empty:
        insights = []

        # --- 入院患者数の曜日パターン ---
        if '平均入院患者数' in summary_df.columns:
            max_day = summary_df.loc[summary_df['平均入院患者数'].idxmax()]
            min_day = summary_df.loc[summary_df['平均入院患者数'].idxmin()]
            insights.append(
                f"入院患者数は**{max_day['曜日名']}曜日**が最も多く（平均 {max_day['平均入院患者数']:.1f}人/日）、"
                f"**{min_day['曜日名']}曜日**が最も少ない（平均 {min_day['平均入院患者数']:.1f}人/日）傾向があります。"
            )
        elif '入院患者数合計' in summary_df.columns:
            max_day = summary_df.loc[summary_df['入院患者数合計'].idxmax()]
            min_day = summary_df.loc[summary_df['入院患者数合計'].idxmin()]
            insights.append(
                f"入院患者数は**{max_day['曜日名']}曜日**が最も多く（合計 {max_day['入院患者数合計']:.0f}人）、"
                f"**{min_day['曜日名']}曜日**が最も少ない（合計 {min_day['入院患者数合計']:.0f}人）傾向があります。"
            )

        # --- 退院患者数の曜日パターン ---
        if '平均退院患者数' in summary_df.columns:
            max_day = summary_df.loc[summary_df['平均退院患者数'].idxmax()]
            min_day = summary_df.loc[summary_df['平均退院患者数'].idxmin()]
            insights.append(
                f"退院患者数は**{max_day['曜日名']}曜日**が最も多く（平均 {max_day['平均退院患者数']:.1f}人/日）、"
                f"**{min_day['曜日名']}曜日**が最も少ない（平均 {min_day['平均退院患者数']:.1f}人/日）傾向があります。"
            )
        elif '退院患者数合計' in summary_df.columns:
            max_day = summary_df.loc[summary_df['退院患者数合計'].idxmax()]
            min_day = summary_df.loc[summary_df['退院患者数合計'].idxmin()]
            insights.append(
                f"退院患者数は**{max_day['曜日名']}曜日**が最も多く（合計 {max_day['退院患者数合計']:.0f}人）、"
                f"**{min_day['曜日名']}曜日**が最も少ない（合計 {min_day['退院患者数合計']:.0f}人）傾向があります。"
            )

        # --- 緊急入院の曜日パターン ---
        if '平均緊急入院患者数' in summary_df.columns:
            max_e = summary_df.loc[summary_df['平均緊急入院患者数'].idxmax()]
            insights.append(
                f"緊急入院は**{max_e['曜日名']}曜日**に最も多く発生しています（平均 {max_e['平均緊急入院患者数']:.1f}人/日）。"
            )

        # --- 週末と平日の比較 ---
        if '曜日番号' in summary_df.columns:
            weekend = summary_df[summary_df['曜日番号'] >= 5]
            weekday = summary_df[summary_df['曜日番号'] < 5]
            if not weekend.empty and not weekday.empty and \
               '平均入院患者数' in weekend.columns and '平均入院患者数' in weekday.columns:

                avg_w_e = weekend['平均入院患者数'].mean()
                avg_w_d = weekday['平均入院患者数'].mean()
                if pd.notna(avg_w_e) and pd.notna(avg_w_d) and avg_w_d > 0:
                    diff_pct = (avg_w_d - avg_w_e) / avg_w_e * 100 if avg_w_e > 0 else np.nan
                    if pd.notna(diff_pct):
                        if diff_pct > 20:
                            insights.append(
                                f"平日の入院患者数（平均 {avg_w_d:.1f}人/日）は、"
                                f"週末（平均 {avg_w_e:.1f}人/日）と比較して**{diff_pct:.1f}%多く**、"
                                f"明確な平日/週末パターンが見られます。"
                            )
                        elif diff_pct < -20:
                            insights.append(
                                f"週末の入院患者数（平均 {avg_w_e:.1f}人/日）は、"
                                f"平日（平均 {avg_w_d:.1f}人/日）と比較して**{abs(diff_pct):.1f}%多く**、"
                                f"特徴的な週末集中パターンが見られます。"
                            )

            # 退院患者数についても同様に比較
            if not weekend.empty and not weekday.empty and \
               '平均退院患者数' in weekend.columns and '平均退院患者数' in weekday.columns:
                avg_e_w = weekend['平均退院患者数'].mean()
                avg_w_d2 = weekday['平均退院患者数'].mean()
                if pd.notna(avg_e_w) and pd.notna(avg_w_d2) and avg_w_d2 > 0:
                    if avg_e_w < avg_w_d2 * 0.3:
                        insights.append(
                            "週末の退院が極めて少なくなっています（"
                            f"週末平均 {avg_e_w:.1f}人/日 vs 平日平均 {avg_w_d2:.1f}人/日）。"
                            "週末の退院支援体制を強化することで、"
                            "患者の利便性向上と月曜日の業務集中を緩和できる可能性があります。"
                        )

        if insights:
            st.markdown("<div class='info-card'>", unsafe_allow_html=True)
            st.markdown("#### <span style='color: #191970;'>インサイト</span>", unsafe_allow_html=True)
            for ins in insights:
                st.markdown(f"<p style='margin-bottom:0.5em;'>- {ins}</p>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            # 運用改善のためのヒント
            st.markdown("<div class='success-card' style='margin-top:1em;'>", unsafe_allow_html=True)
            st.markdown("#### <span style='color: #006400;'>運用改善のためのヒント</span>", unsafe_allow_html=True)

            max_adm = summary_df.loc[summary_df['平均入院患者数'].idxmax()] if '平均入院患者数' in summary_df.columns else None
            max_dis = summary_df.loc[summary_df['平均退院患者数'].idxmax()] if '平均退院患者数' in summary_df.columns else None
            if max_adm is not None and max_dis is not None:
                if max_adm['曜日名'] == max_dis['曜日名']:
                    st.markdown(
                        f"<p style='margin-bottom:0.5em;'>"
                        f"- 入院と退院のピークが同じ**{max_adm['曜日名']}曜日**に集中している可能性があります。"
                        "業務負荷を分散するために、予定入院の一部を他の曜日にずらす、"
                        "または週末の退院支援を強化することを検討できます。</p>",
                        unsafe_allow_html=True
                    )

            if '曜日番号' in summary_df.columns and not weekend.empty and not weekday.empty:
                if '平均退院患者数' in weekend.columns and '平均退院患者数' in weekday.columns:
                    if pd.notna(weekday['平均退院患者数'].mean()) and weekday['平均退院患者数'].mean() > 0 and \
                       pd.notna(weekend['平均退院患者数'].mean()) and weekend['平均退院患者数'].mean() < weekday['平均退院患者数'].mean() * 0.3:
                        st.markdown(
                            f"<p style='margin-bottom:0.5em;'>"
                            "- 週末の退院が平日に比べて著しく少ないようです。"
                            "週末の退院プロセスを見直し、スタッフ配置や関連部門との連携を強化することで、"
                            "患者さんの利便性向上や月曜日の業務負荷軽減に繋がる可能性があります。"
                            "</p>",
                            unsafe_allow_html=True
                        )

            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("分析インサイトを生成するための十分なデータパターンが見つかりませんでした。")
    else:
        st.info("分析インサイトを生成するためのサマリーデータがありません。")

    #
    # ===== 5. 期間比較設定（完全版） =====
    #
    st.markdown(
        f"<div class='chart-title' style='margin-top:2rem;'>期間比較</div>",
        unsafe_allow_html=True
    )
    # 日付の範囲を取得
    try:
        data_min_ts = df['日付'].min()
        data_max_ts = df['日付'].max()
        data_min_date = data_min_ts.date()
        data_max_date = data_max_ts.date()
    except Exception as e:
        st.error(f"データの日付範囲取得でエラーが発生しました: {e}")
        return

    # セッションステートのクリアチェック
    for key in ['dow_comparison_start_date', 'dow_comparison_end_date']:
        if key in st.session_state:
            stored = st.session_state[key]
            if isinstance(stored, date) and (stored < data_min_date or stored > data_max_date):
                del st.session_state[key]

    enable_comp = st.checkbox("別の期間と比較する", key="dow_enable_comparison")
    if enable_comp:
        col1, col2 = st.columns(2)
        with col1:
            sess_start = st.session_state.get("dow_comparison_start_date")
            ideal_start_ts = start_date_ts - pd.Timedelta(days=365)
            if sess_start and isinstance(sess_start, date) and data_min_date <= sess_start <= data_max_date:
                default_start = sess_start
            elif ideal_start_ts.date() >= data_min_date:
                default_start = ideal_start_ts.date()
            else:
                default_start = min(data_min_date + timedelta(days=90), data_max_date)

            default_start = max(default_start, data_min_date)
            default_start = min(default_start, data_max_date)

            comp_start_date_input = st.date_input(
                "比較期間：開始日",
                value=default_start,
                min_value=data_min_date,
                max_value=data_max_date,
                key="dow_comparison_start_date"
            )
            comp_start_date = pd.Timestamp(comp_start_date_input).normalize()

        with col2:
            sess_end = st.session_state.get("dow_comparison_end_date")
            period_len = (end_date_ts.date() - start_date_ts.date()).days
            ideal_end = comp_start_date + timedelta(days=period_len)

            if sess_end and isinstance(sess_end, date) and data_min_date <= sess_end <= data_max_date and sess_end >= comp_start_date:
                default_end = sess_end
            elif ideal_end <= data_max_date and ideal_end >= comp_start_date:
                default_end = ideal_end
            else:
                default_end = data_max_date

            default_end = max(default_end, comp_start_date)
            default_end = min(default_end, data_max_date)
            default_end = max(default_end, data_min_date)

            comp_end_date_input = st.date_input(
                "比較期間：終了日",
                value=default_end,
                min_value=comp_start_date_input,  # date型のまま使用
                max_value=data_max_date,
                key="dow_comparison_end_date"
            )
            comp_end_date = pd.Timestamp(comp_end_date_input).normalize()

        if st.button("現在期間と同じ長さに設定", key="set_same_length"):
            length_days = (end_date_ts.date() - start_date_ts.date()).days
            cur_start = st.session_state.dow_comparison_start_date
            tgt_end = cur_start + timedelta(days=length_days)
            if tgt_end > data_max_date:
                tgt_end = data_max_date
                cur_start = max(data_min_date, tgt_end - timedelta(days=length_days))
            st.session_state.dow_comparison_start_date = cur_start
            st.session_state.dow_comparison_end_date = tgt_end
            st.experimental_rerun()

        if comp_start_date > comp_end_date:
            st.error("比較期間の終了日は開始日以降に設定してください。")
            return

        # ---- 比較用データ取得 ----
        comp_dow_data = pd.DataFrame()
        if selected_metrics:
            comp_dow_data = get_dow_data(
                df=df,
                unit_type=selected_unit,
                target_items=target_items,
                start_date=pd.Timestamp(comp_start_date),
                end_date=pd.Timestamp(comp_end_date),
                metric_type=metric_type,
                patient_cols_to_analyze=selected_metrics
            )

        st.markdown(
            f"<div class='chart-title'>期間比較：曜日別 患者数パターン</div>",
            unsafe_allow_html=True
        )
        comp_mode = st.radio(
            "比較表示モード:",
            ["縦に並べて表示", "1つのグラフで比較"],
            key="dow_comparison_display_mode"
        )

        if comp_dow_data is not None and not comp_dow_data.empty:
            # 「縦に並べて表示」の場合
            if comp_mode == "縦に並べて表示":
                if not dow_data_for_chart.empty:
                    fig_cur = create_dow_chart(
                        dow_data_melted=dow_data_for_chart,
                        unit_type=selected_unit,
                        target_items=target_items,
                        metric_type=metric_type,
                        patient_cols_to_analyze=selected_metrics,
                        title_prefix="現在期間"
                    )
                else:
                    fig_cur = None

                fig_comp = create_dow_chart(
                    dow_data_melted=comp_dow_data,
                    unit_type=selected_unit,
                    target_items=target_items,
                    metric_type=metric_type,
                    patient_cols_to_analyze=selected_metrics,
                    title_prefix="比較期間"
                )
                if fig_cur and fig_comp:
                    st.plotly_chart(fig_cur, use_container_width=True)
                    st.markdown("<div style='text-align:center; margin-bottom:1rem;'>↓ 比較 ↓</div>", unsafe_allow_html=True)
                    st.plotly_chart(fig_comp, use_container_width=True)
                    st.markdown(
                        "<div class='info-card'>"
                        "<p>現在期間と比較期間の曜日パターンを比較して、変化点や傾向の違いを確認できます。</p>"
                        "</div>",
                        unsafe_allow_html=True
                    )
                else:
                    st.info("比較グラフを生成できませんでした。")

            # 「1つのグラフで比較」の場合（元ファイルから詳細版を復元）
            else:
                combined = pd.DataFrame()
                if not dow_data_for_chart.empty:
                    current_name = f"現在期間 ({start_date_ts.strftime('%Y/%m/%d')}～{end_date_ts.strftime('%Y/%m/%d')})"
                    dow_data_for_chart['期間'] = current_name
                if not comp_dow_data.empty:
                    comp_name = f"比較期間 ({comp_start_date.strftime('%Y/%m/%d')}～{comp_end_date.strftime('%Y/%m/%d')})"
                    comp_dow_data['期間'] = comp_name

                if not dow_data_for_chart.empty and not comp_dow_data.empty:
                    combined = pd.concat([dow_data_for_chart, comp_dow_data], ignore_index=True)
                elif not dow_data_for_chart.empty:
                    combined = dow_data_for_chart
                    st.warning("比較期間のデータがありません。現在期間のみ表示します。")
                elif not comp_dow_data.empty:
                    combined = comp_dow_data
                    st.warning("現在期間のデータがありません。比較期間のみ表示します。")
                else:
                    combined = pd.DataFrame()
                    st.info("表示するデータがありません。")

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
                                labels={
                                    '曜日': '曜日',
                                    '患者数': y_title,
                                    '集計単位名': '集計単位',
                                    '指標タイプ': '指標',
                                    '期間': '分析期間'
                                },
                                category_orders={
                                    "曜日": DOW_LABELS,
                                    "指標タイプ": selected_metrics,
                                    "期間": [current_name, comp_name]
                                }
                            )
                            # Y軸の範囲を揃える
                            fig_all.update_yaxes(matches=None)
                            max_y = combined['患者数'].max() * 1.1
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
                                labels={
                                    '曜日': '曜日',
                                    '患者数': y_title,
                                    '集計単位名': '集計単位',
                                    '指標タイプ': '指標',
                                    '期間': '分析期間'
                                },
                                category_orders={
                                    "曜日": DOW_LABELS,
                                    "指標タイプ": selected_metrics,
                                    "期間": [current_name, comp_name]
                                }
                            )
                            # ユニットごとに Y軸を揃える
                            y_max_per_unit = combined.groupby('集計単位名')['患者数'].max()
                            for unit_name, unit_val in y_max_per_unit.items():
                                limit = unit_val * 1.1
                                fig_all.for_each_yaxis(
                                    lambda yaxis: yaxis.update(range=[0, limit]) \
                                        if yaxis.title.text.endswith(f"={unit_name}") else None
                                )

                        # グラフの高さを調整
                        num_rows = 2  # 期間が2つ
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
                                labels={
                                    '曜日': '曜日',
                                    '患者数': y_title,
                                    '集計単位名': '集計単位',
                                    '指標タイプ': '指標',
                                    '期間': '分析期間'
                                },
                                category_orders={
                                    "曜日": DOW_LABELS,
                                    "指標タイプ": selected_metrics,
                                    "期間": [current_name, comp_name]
                                }
                            )
                            fig_all.update_yaxes(matches=None)
                            max_y = combined['患者数'].max() * 1.1
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
                                labels={
                                    '曜日': '曜日',
                                    '患者数': y_title,
                                    '集計単位名': '集計単位',
                                    '指標タイプ': '指標',
                                    '期間': '分析期間'
                                },
                                category_orders={
                                    "曜日": DOW_LABELS,
                                    "指標タイプ": selected_metrics,
                                    "期間": [current_name, comp_name]
                                }
                            )
                            # ユニットごとに Y軸を揃える
                            for idx, unit_name in enumerate(combined['集計単位名'].unique()):
                                unit_data = combined[combined['集計単位名'] == unit_name]
                                limit = unit_data['患者数'].max() * 1.1
                                # 2 つの期間を想定して、row=row_index, col=0/1 を更新
                                row_idx = idx
                                for col_idx in [0, 1]:
                                    fig_all.update_yaxes(range=[0, limit], row=row_idx, col=col_idx)

                        if num_units > 1 and selected_unit != '病院全体':
                            height = 250 * num_units
                        else:
                            height = 400

                    # --- 期間を同じグラフ内で並べて表示 ---
                    else:
                        bar_style = st.radio(
                            "バースタイル:", 
                            ["期間を色分け", "指標タイプを色分け"],
                            key="dow_comparison_bar_style"
                        )

                        if bar_style == "期間を色分け":
                            if num_units == 1 or selected_unit == '病院全体':
                                fig_all = px.bar(
                                    combined,
                                    x='曜日',
                                    y='患者数',
                                    color='期間',
                                    barmode='group',
                                    facet_col='指標タイプ',
                                    labels={
                                        '曜日': '曜日',
                                        '患者数': y_title,
                                        '集計単位名': '集計単位',
                                        '指標タイプ': '指標',
                                        '期間': '分析期間'
                                    },
                                    category_orders={
                                        "曜日": DOW_LABELS,
                                        "指標タイプ": selected_metrics,
                                        "期間": [current_name, comp_name]
                                    }
                                )
                            else:
                                # 複数ユニットかつ指標が複数の場合、一旦指標を選択させてから表示
                                if len(selected_metrics) > 1:
                                    sel_metric = st.selectbox(
                                        "表示する指標:",
                                        selected_metrics,
                                        key="dow_comparison_metric_selector"
                                    )
                                    filtered = combined[combined['指標タイプ'] == sel_metric]
                                else:
                                    sel_metric = selected_metrics[0]
                                    filtered = combined

                                fig_all = px.bar(
                                    filtered,
                                    x='曜日',
                                    y='患者数',
                                    color='期間',
                                    barmode='group',
                                    facet_col='集計単位名',
                                    facet_col_wrap=min(num_units, 3),
                                    labels={
                                        '曜日': '曜日',
                                        '患者数': y_title,
                                        '集計単位名': '集計単位',
                                        '指標タイプ': '指標',
                                        '期間': '分析期間'
                                    },
                                    category_orders={
                                        "曜日": DOW_LABELS,
                                        "期間": [current_name, comp_name]
                                    }
                                )
                                # ユニットごとに Y軸を揃える
                                for idx, unit_name in enumerate(filtered['集計単位名'].unique()):
                                    unit_data = filtered[filtered['集計単位名'] == unit_name]
                                    limit = unit_data['患者数'].max() * 1.1
                                    col_idx = idx % 3
                                    fig_all.update_yaxes(range=[0, limit], col=col_idx)
                        else:  # 「指標タイプを色分け」
                            if num_units == 1 or selected_unit == '病院全体':
                                fig_all = px.bar(
                                    combined,
                                    x='曜日',
                                    y='患者数',
                                    color='指標タイプ',
                                    barmode='group',
                                    facet_col='期間',
                                    labels={
                                        '曜日': '曜日',
                                        '患者数': y_title,
                                        '集計単位名': '集計単位',
                                        '指標タイプ': '指標',
                                        '期間': '分析期間'
                                    },
                                    category_orders={
                                        "曜日": DOW_LABELS,
                                        "指標タイプ": selected_metrics,
                                        "期間": [current_name, comp_name]
                                    }
                                )
                            else:
                                sel_period = st.radio(
                                    "表示する期間:",
                                    [current_name, comp_name],
                                    key="dow_comparison_period_selector"
                                )
                                period_df = combined[combined['期間'] == sel_period]
                                fig_all = px.bar(
                                    period_df,
                                    x='曜日',
                                    y='患者数',
                                    color='指標タイプ',
                                    barmode='group',
                                    facet_col='集計単位名',
                                    facet_col_wrap=min(num_units, 3),
                                    labels={
                                        '曜日': '曜日',
                                        '患者数': y_title,
                                        '集計単位名': '集計単位',
                                        '指標タイプ': '指標'
                                    },
                                    category_orders={
                                        "曜日": DOW_LABELS,
                                        "指標タイプ": selected_metrics
                                    }
                                )
                                fig_all.update_layout(title_text=f"{sel_period} - 曜日別 患者数パターン")

                        # グラフの高さを決定
                        if num_units > 1 and selected_unit != '病院全体':
                            height = 400 * ((num_units + 2) // 3)
                        else:
                            if len(selected_metrics) > 1 and bar_style == "期間を色分け":
                                height = 400 * ((len(selected_metrics) + 2) // 3)
                            else:
                                height = 500

                    # 共通のレイアウト調整
                    height = max(height, 500)
                    height = min(height, 1200)
                    fig_all.update_layout(
                        title_text=f"曜日別 患者数パターン ({unit_suffix}) - 期間比較",
                        title_x=0.5,
                        height=height,
                        font=dict(size=12),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
                        bargap=0.2,
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=20, r=20, t=60, b=20)
                    )
                    fig_all.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray', categoryorder='array', categoryarray=DOW_LABELS)
                    fig_all.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')

                    st.plotly_chart(fig_all, use_container_width=True)

                    # ===== 期間比較インサイト（元ファイルから復元） =====
                    st.markdown("<div class='info-card'>", unsafe_allow_html=True)
                    st.markdown("#### <span style='color: #191970;'>期間比較インサイト</span>", unsafe_allow_html=True)

                    comp_summary = None
                    if calculate_dow_summary:
                        filtered_comp_df = safe_date_filter(df, pd.Timestamp(comp_start_date), pd.Timestamp(comp_end_date))
                        if filtered_comp_df is not None and not filtered_comp_df.empty:
                            comp_summary = calculate_dow_summary(
                                df=filtered_comp_df,
                                start_date=pd.Timestamp(comp_start_date),
                                end_date=pd.Timestamp(comp_end_date),
                                group_by_column=group_by_col,
                                target_items=target_items
                            )
                        else:
                            st.info("比較期間のサマリーデータを生成するためのフィルタリング済みデータがありません。")

                    # 詳細な比較分析（サマリーデータがある場合）
                    if not summary_df.empty and comp_summary is not None and not comp_summary.empty:
                        current_cols = summary_df.columns
                        comp_cols = comp_summary.columns
                        common_cols = [c for c in current_cols if c in comp_cols]

                        # メトリクス列（平均/合計）と率の列を抽出
                        if metric_type == 'average':
                            metric_cols = [c for c in common_cols if c.startswith('平均')]
                        else:
                            metric_cols = [c for c in common_cols if c.endswith('合計')]
                        rate_cols = [c for c in common_cols if c in ['緊急入院率', '死亡退院率']]
                        analysis_cols = metric_cols + rate_cols

                        unique_units = summary_df['集計単位'].unique()
                        for unit in unique_units:
                            cur_unit_df = summary_df[summary_df['集計単位'] == unit]
                            comp_unit_df = comp_summary[comp_summary['集計単位'] == unit]
                            if cur_unit_df.empty or comp_unit_df.empty:
                                continue

                            st.markdown(f"##### {unit} の期間比較:", unsafe_allow_html=True)
                            unit_insights = []

                            for col in analysis_cols:
                                # 列名から表示名を生成
                                if col.startswith('平均'):
                                    disp = col[2:]  # "平均" を除去
                                elif col.endswith('合計'):
                                    disp = col[:-2]  # "合計" を除去
                                else:
                                    disp = col

                                # ピーク曜日の変化
                                try:
                                    cur_max_idx = cur_unit_df[col].idxmax()
                                    comp_max_idx = comp_unit_df[col].idxmax()
                                    cur_max_day = cur_unit_df.loc[cur_max_idx, '曜日名']
                                    comp_max_day = comp_unit_df.loc[comp_max_idx, '曜日名']
                                    if cur_max_day != comp_max_day:
                                        unit_insights.append(
                                            f"**{disp}** のピーク曜日が変化しています: {comp_max_day}曜日 → {cur_max_day}曜日"
                                        )
                                except Exception:
                                    pass

                                # 平均値の変化率
                                cur_avg = cur_unit_df[col].mean()
                                comp_avg = comp_unit_df[col].mean()
                                if pd.notna(cur_avg) and pd.notna(comp_avg) and comp_avg != 0:
                                    change_pct = (cur_avg - comp_avg) / abs(comp_avg) * 100
                                    if abs(change_pct) >= 15:
                                        direction = "増加" if change_pct > 0 else "減少"
                                        unit_insights.append(
                                            f"**{disp}** の平均値が {abs(change_pct):.1f}% {direction}しています"
                                        )

                                # 曜日ごとの変化（大きな変化のみ）
                                for dow in DOW_LABELS:
                                    cur_d = cur_unit_df[cur_unit_df['曜日名'] == dow]
                                    comp_d = comp_unit_df[comp_unit_df['曜日名'] == dow]
                                    if not cur_d.empty and not comp_d.empty:
                                        cur_val = cur_d[col].iloc[0]
                                        comp_val = comp_d[col].iloc[0]
                                        if pd.notna(cur_val) and pd.notna(comp_val) and comp_val != 0:
                                            dow_pct = (cur_val - comp_val) / abs(comp_val) * 100
                                            if abs(dow_pct) >= 30:
                                                direction = "増加" if dow_pct > 0 else "減少"
                                                unit_insights.append(
                                                    f"**{dow}** の **{disp}** が大きく変化: "
                                                    f"{comp_val:.1f} → {cur_val:.1f} ({abs(dow_pct):.1f}% {direction})"
                                                )

                            if unit_insights:
                                for ui in unit_insights:
                                    st.markdown(f"- {ui}", unsafe_allow_html=True)
                            else:
                                st.markdown("- 顕著な変化は見られません", unsafe_allow_html=True)

                            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

                        # 週末/平日パターン変化分析
                        st.markdown("##### 週末/平日パターンの変化:", unsafe_allow_html=True)
                        weekend_insights = []
                        for unit in unique_units:
                            cur_df = summary_df[summary_df['集計単位'] == unit]
                            comp_df2 = comp_summary[comp_summary['集計単位'] == unit]
                            if '曜日番号' not in cur_df.columns or '曜日番号' not in comp_df2.columns:
                                continue

                            cur_wend = cur_df[cur_df['曜日番号'] >= 5]
                            cur_wday = cur_df[cur_df['曜日番号'] < 5]
                            comp_wend = comp_df2[comp_df2['曜日番号'] >= 5]
                            comp_wday = comp_df2[comp_df2['曜日番号'] < 5]

                            for col in ['平均入院患者数', '平均退院患者数']:
                                if col in cur_df.columns and col in comp_df2.columns:
                                    cur_wend_avg = cur_wend[col].mean() if not cur_wend.empty else None
                                    cur_wday_avg = cur_wday[col].mean() if not cur_wday.empty else None
                                    comp_wend_avg = comp_wend[col].mean() if not comp_wend.empty else None
                                    comp_wday_avg = comp_wday[col].mean() if not comp_wday.empty else None
                                    if (
                                        pd.notna(cur_wend_avg) and pd.notna(cur_wday_avg) and
                                        pd.notna(comp_wend_avg) and pd.notna(comp_wday_avg) and
                                        cur_wday_avg > 0 and comp_wday_avg > 0
                                    ):
                                        cur_ratio = cur_wend_avg / cur_wday_avg
                                        comp_ratio = comp_wend_avg / comp_wday_avg
                                        ratio_change = (cur_ratio - comp_ratio) / comp_ratio * 100
                                        if abs(ratio_change) >= 20:
                                            if ratio_change > 0:
                                                weekend_insights.append(
                                                    f"{unit}の**{col[2:]}**：週末と平日の差が縮小しています "
                                                    f"（週末/平日比：{comp_ratio:.2f} → {cur_ratio:.2f}）"
                                                )
                                            else:
                                                weekend_insights.append(
                                                    f"{unit}の**{col[2:]}**：週末と平日の差が拡大しています "
                                                    f"（週末/平日比：{comp_ratio:.2f} → {cur_ratio:.2f}）"
                                                )

                        if weekend_insights:
                            for wi in weekend_insights:
                                st.markdown(f"- {wi}", unsafe_allow_html=True)
                        else:
                            st.markdown("- 週末/平日パターンに顕著な変化は見られません", unsafe_allow_html=True)

                    # 簡易比較（サマリーデータがない場合）
                    else:
                        if selected_metrics and not dow_data_for_chart.empty:
                            st.markdown("##### 指標ごとの全体的な変化:", unsafe_allow_html=True)
                            for m in selected_metrics:
                                cur_df_m = dow_data_for_chart[dow_data_for_chart['指標タイプ'] == m]
                                comp_df_m = comp_dow_data[comp_dow_data['指標タイプ'] == m]
                                if not cur_df_m.empty and not comp_df_m.empty:
                                    cur_avg_m = cur_df_m['患者数'].mean()
                                    comp_avg_m = comp_df_m['患者数'].mean()
                                    if pd.notna(cur_avg_m) and pd.notna(comp_avg_m) and comp_avg_m != 0:
                                        pct = (cur_avg_m - comp_avg_m) / comp_avg_m * 100
                                        dir_str = "増加" if pct > 0 else "減少"
                                        st.markdown(
                                            f"- **{m}** の平均値： {comp_avg_m:.1f} → {cur_avg_m:.1f} ({abs(pct):.1f}% {dir_str})"
                                        )
                                    else:
                                        st.markdown(f"- **{m}** の変化を計算できません（データが不足しています）")

                            st.markdown("##### 曜日パターンの変化:", unsafe_allow_html=True)
                            st.markdown(
                                "期間間の曜日パターンを比較して、特に変化が大きい曜日や指標に注目することで、運用方法の改善点を見つけられます。",
                                unsafe_allow_html=True
                            )

                    st.markdown("</div>", unsafe_allow_html=True)

                    # ===== 期間比較からの運用改善ヒント（元ファイルから復元） =====
                    st.markdown("<div class='success-card' style='margin-top: 1em;'>", unsafe_allow_html=True)
                    st.markdown("#### <span style='color: #006400;'>期間比較からの運用改善ヒント</span>", unsafe_allow_html=True)
                    
                    # 基本的な運用改善ヒント
                    st.markdown(
                        "<p style='margin-bottom: 0.5em;'>- 曜日パターンの変化から運用方法の改善効果を評価できます。例えば、週末の退院支援強化策を実施した場合、"
                        "その前後の期間を比較することで効果測定が可能です。</p>", unsafe_allow_html=True
                    )
                    
                    st.markdown(
                        "<p style='margin-bottom: 0.5em;'>- 特定の曜日に患者数が増加している場合、その曜日のスタッフ配置や業務プロセスを見直すことで、より効率的な運用が可能になります。</p>", unsafe_allow_html=True
                    )
                    
                    st.markdown(
                        "<p style='margin-bottom: 0.5em;'>- 期間による変化が大きい場合は、季節性や特定のイベント（例：診療体制の変更、地域の人口動態変化など）の影響を考慮する必要があります。</p>", unsafe_allow_html=True
                    )

                    # メトリクス別の具体的な提案（元ファイルから復元）
                    metric_specific_tips = []
                    
                    # 入院患者数のパターン変化に基づく提案
                    if '入院患者数' in selected_metrics or '総入院患者数' in selected_metrics:
                        target_metric = '入院患者数' if '入院患者数' in selected_metrics else '総入院患者数'
                        
                        if (dow_data_for_chart is not None and not dow_data_for_chart.empty and 
                            comp_dow_data is not None and not comp_dow_data.empty and 
                            '指標タイプ' in dow_data_for_chart.columns and '指標タイプ' in comp_dow_data.columns):

                            current_data = dow_data_for_chart[dow_data_for_chart['指標タイプ'] == target_metric]
                            comp_data = comp_dow_data[comp_dow_data['指標タイプ'] == target_metric]
                            
                            if not current_data.empty and not comp_data.empty:
                                # 曜日ごとの比較
                                for dow in DOW_LABELS:
                                    current_dow = current_data[current_data['曜日'] == dow]['患者数'].mean()
                                    comp_dow = comp_data[comp_data['曜日'] == dow]['患者数'].mean()
                                    
                                    if pd.notna(current_dow) and pd.notna(comp_dow) and comp_dow > 0:
                                        change_pct = (current_dow - comp_dow) / comp_dow * 100
                                        
                                        if change_pct >= 20:
                                            metric_specific_tips.append(
                                                f"**{dow}の{target_metric}**が{change_pct:.1f}%増加しています。この曜日の入院受け入れ体制を強化し、"
                                                f"病床管理や看護配置を最適化することで、質の高いケアを維持できる可能性があります。"
                                            )
                                        elif change_pct <= -20:
                                            metric_specific_tips.append(
                                                f"**{dow}の{target_metric}**が{abs(change_pct):.1f}%減少しています。この曜日の空床を有効活用するため、"
                                                f"外来からの予定入院の調整や他の曜日からの入院シフトを検討できます。"
                                            )
                    
                    # 退院患者数のパターン変化に基づく提案
                    if '退院患者数' in selected_metrics or '総退院患者数' in selected_metrics:
                        target_metric = '退院患者数' if '退院患者数' in selected_metrics else '総退院患者数'
                        
                        if (dow_data_for_chart is not None and not dow_data_for_chart.empty and 
                            comp_dow_data is not None and not comp_dow_data.empty and 
                            '指標タイプ' in dow_data_for_chart.columns and '指標タイプ' in comp_dow_data.columns):

                            current_data = dow_data_for_chart[dow_data_for_chart['指標タイプ'] == target_metric]
                            comp_data = comp_dow_data[comp_dow_data['指標タイプ'] == target_metric]
                            
                            if not current_data.empty and not comp_data.empty:
                                # 週末（土日）の退院パターンの変化を分析
                                current_weekend = current_data[current_data['曜日'].isin(['土曜日', '日曜日'])]['患者数'].mean()
                                comp_weekend = comp_data[comp_data['曜日'].isin(['土曜日', '日曜日'])]['患者数'].mean()
                                
                                if pd.notna(current_weekend) and pd.notna(comp_weekend) and comp_weekend > 0:
                                    weekend_change_pct = (current_weekend - comp_weekend) / comp_weekend * 100
                                    
                                    if weekend_change_pct >= 30:
                                        metric_specific_tips.append(
                                            f"**週末の{target_metric}**が{weekend_change_pct:.1f}%増加しています。週末の退院支援が強化されたようです。"
                                            f"この良い変化を継続・発展させるため、週末の退院調整業務の成功要因を分析し、さらなる最適化を検討できます。"
                                        )
                                    elif weekend_change_pct <= -30:
                                        metric_specific_tips.append(
                                            f"**週末の{target_metric}**が{abs(weekend_change_pct):.1f}%減少しています。週末の退院支援体制に課題がある可能性があります。"
                                            f"薬剤部や医事課など関連部門との連携強化や、退院前カンファレンスの週末実施などの対策が有効かもしれません。"
                                        )
                    
                    # 緊急入院患者数のパターン変化に基づく提案
                    if '緊急入院患者数' in selected_metrics:
                        if (dow_data_for_chart is not None and not dow_data_for_chart.empty and 
                            comp_dow_data is not None and not comp_dow_data.empty and 
                            '指標タイプ' in dow_data_for_chart.columns and '指標タイプ' in comp_dow_data.columns):

                            current_data = dow_data_for_chart[dow_data_for_chart['指標タイプ'] == '緊急入院患者数']
                            comp_data = comp_dow_data[comp_dow_data['指標タイプ'] == '緊急入院患者数']

                            if not current_data.empty and not comp_data.empty:
                                current_avg = current_data['患者数'].mean()
                                comp_avg = comp_data['患者数'].mean()
                                
                                if pd.notna(current_avg) and pd.notna(comp_avg) and comp_avg > 0:
                                    change_pct = (current_avg - comp_avg) / comp_avg * 100
                                    
                                    if abs(change_pct) >= 20:
                                        direction = "増加" if change_pct > 0 else "減少"
                                        metric_specific_tips.append(
                                            f"**緊急入院患者数**が全体的に{abs(change_pct):.1f}%{direction}しています。"
                                            f"{'緊急対応体制の強化や救急部門との連携見直しが必要かもしれません。' if change_pct > 0 else '緊急入院の減少傾向を分析し、地域連携や診療体制に変化があったか確認するとよいでしょう。'}"
                                        )
                    
                    # メトリクス別提案の表示
                    if metric_specific_tips:
                        for tip in metric_specific_tips:
                            st.markdown(f"<p style='margin-bottom: 0.5em;'>- {tip}</p>", unsafe_allow_html=True)

                    st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("曜日別グラフまたは比較用データが不足しているため、期間比較ができません。")