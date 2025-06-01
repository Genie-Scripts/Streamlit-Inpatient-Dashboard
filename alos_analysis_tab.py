# alos_analysis_tab.py (修正版)
import streamlit as st
import pandas as pd
import numpy as np
# import plotly.graph_objects as go # alos_charts.py で使用
# from plotly.subplots import make_subplots # alos_charts.py で使用
# import plotly.express as px # alos_charts.py で使用
# from datetime import datetime, timedelta # display_alos_analysis_tab では直接不要かも
import logging

logger = logging.getLogger(__name__)

# alos_charts.py からインポート (変更なし)
from alos_charts import (
    create_alos_volume_chart,
    create_alos_benchmark_chart,
    calculate_alos_metrics
)

# utils.py からインポート (変更なし)
from utils import (
    get_ward_display_name,
    get_display_name_for_dept,
    # safe_date_filter # このファイル内では直接使用していない
)

def display_alos_analysis_tab(df_filtered_by_period, start_date_ts, end_date_ts, common_config=None):
    """
    平均在院日数分析タブの表示（統一フィルター対応・タブ内設定版）
    Args:
        df_filtered_by_period (pd.DataFrame): 統一フィルターで既にフィルタリング済みのDataFrame
        start_date_ts (pd.Timestamp): 分析期間の開始日
        end_date_ts (pd.Timestamp): 分析期間の終了日
        common_config (dict, optional): 共通設定
    """
    logger.info("平均在院日数分析タブを開始します（タブ内設定版）")

    if df_filtered_by_period is None or df_filtered_by_period.empty:
        st.warning("🔍 分析対象のデータが空です。統一フィルター条件を確認してください。")
        return

    df_analysis = df_filtered_by_period.copy()

    total_days = (end_date_ts - start_date_ts).days + 1
    st.info(f"📅 **分析期間 (統一フィルター適用済):** {start_date_ts.strftime('%Y年%m月%d日')} ～ {end_date_ts.strftime('%Y年%m月%d日')} （{total_days}日間）")

    required_columns = [
        '日付', '病棟コード', '診療科名',
        '入院患者数（在院）', '入院患者数', '緊急入院患者数',
        '退院患者数', '死亡患者数', '総入院患者数', '総退院患者数'
    ]
    missing_columns = [col for col in required_columns if col not in df_analysis.columns]
    if missing_columns:
        # ... (既存の列名補完ロジックは維持) ...
        logger.warning(f"不足している列: {missing_columns}")
        if '入院患者数（在院）' in missing_columns and '在院患者数' in df_analysis.columns:
            df_analysis['入院患者数（在院）'] = df_analysis['在院患者数']
            missing_columns.remove('入院患者数（在院）')
            logger.info("'在院患者数'を'入院患者数（在院）'として使用")
        if '総入院患者数' in missing_columns and '入院患者数' in df_analysis.columns and '緊急入院患者数' in df_analysis.columns:
            df_analysis['総入院患者数'] = df_analysis['入院患者数'] + df_analysis['緊急入院患者数']
            missing_columns.remove('総入院患者数')
            logger.info("'入院患者数'+'緊急入院患者数'を'総入院患者数'として計算")
        if '総退院患者数' in missing_columns and '退院患者数' in df_analysis.columns and '死亡患者数' in df_analysis.columns:
            df_analysis['総退院患者数'] = df_analysis['退院患者数'] + df_analysis['死亡患者数']
            missing_columns.remove('総退院患者数')
            logger.info("'退院患者数'+'死亡患者数'を'総退院患者数'として計算")

    if missing_columns: # 補完後も不足しているか再チェック
        st.error(f"❌ 必要な列が見つかりません: {', '.join(missing_columns)}")
        logger.error(f"必須列が不足: {missing_columns}")
        return

    # =================================================================
    # ⚙️ 平均在院日数分析 詳細設定 (タブ内に移動)
    # =================================================================
    with st.expander("⚙️ 表示・分析パラメータ調整", expanded=True):
        col_scope, col_params = st.columns([1, 2])

        with col_scope:
            st.markdown("##### 🔍 分析スコープ")
            analysis_scope = st.radio(
                "スコープ選択", # ラベル簡略化
                ["統一フィルター範囲", "病棟別詳細", "診療科別詳細"],
                key="alos_tab_analysis_scope", # キー名をタブ固有に
                help="統一フィルターで既に選択された範囲での分析スコープを選択"
            )

            selected_items_display = [] # 表示用
            selected_items_actual = []  # 内部処理用コードリスト

            if analysis_scope == "病棟別詳細":
                if '病棟コード' in df_analysis.columns:
                    available_items_codes = sorted(df_analysis['病棟コード'].astype(str).unique())
                    ward_mapping = st.session_state.get('ward_mapping', {})
                    display_options_wards = []
                    code_to_display_map_wards = {} # 表示名からコードへの逆引き用ではない
                    display_to_code_map_wards = {} # 表示名からコードへのマップ

                    for ward_code in available_items_codes:
                        ward_name = get_ward_display_name(ward_code, ward_mapping)
                        display_option = f"{ward_code} ({ward_name})" if ward_name != str(ward_code) else str(ward_code)
                        display_options_wards.append(display_option)
                        display_to_code_map_wards[display_option] = ward_code

                    selected_displays_wards = st.multiselect(
                        "詳細分析対象病棟",
                        display_options_wards,
                        default=display_options_wards[:min(3, len(display_options_wards))], # デフォルト選択を調整
                        key="alos_tab_selected_wards_display",
                        help="統一フィルター範囲内での詳細分析対象病棟（複数選択可）"
                    )
                    selected_items_actual = [display_to_code_map_wards[d] for d in selected_displays_wards if d in display_to_code_map_wards]
                    selected_items_display = selected_displays_wards
                else:
                    st.warning("病棟コード列が見つかりません。")

            elif analysis_scope == "診療科別詳細":
                if '診療科名' in df_analysis.columns:
                    available_items_codes = sorted(df_analysis['診療科名'].astype(str).unique())
                    # 診療科のマッピングは utils.get_display_name_for_dept で行われる想定
                    display_options_depts = []
                    display_to_code_map_depts = {}

                    for dept_code in available_items_codes:
                        dept_name = get_display_name_for_dept(dept_code, default_name=dept_code)
                        display_option = f"{dept_code} ({dept_name})" if dept_name != str(dept_code) else str(dept_code)
                        display_options_depts.append(display_option)
                        display_to_code_map_depts[display_option] = dept_code

                    selected_displays_depts = st.multiselect(
                        "詳細分析対象診療科",
                        display_options_depts,
                        default=display_options_depts[:min(3, len(display_options_depts))],
                        key="alos_tab_selected_depts_display",
                        help="統一フィルター範囲内での詳細分析対象診療科（複数選択可）"
                    )
                    selected_items_actual = [display_to_code_map_depts[d] for d in selected_displays_depts if d in display_to_code_map_depts]
                    selected_items_display = selected_displays_depts
                else:
                    st.warning("診療科名列が見つかりません。")

        with col_params:
            st.markdown("##### 📊 分析パラメータ")
            moving_avg_window = st.slider(
                "移動平均期間 (日)",
                min_value=7, max_value=90, value=30, step=7,
                key="alos_tab_ma_rolling_days", # キー名をタブ固有に
                help="トレンド分析用の移動平均計算期間"
            )
            benchmark_alos_default = common_config.get('benchmark_alos', 12.0) if common_config else 12.0
            benchmark_alos = st.number_input(
                "平均在院日数目標値 (日):",
                min_value=0.0, max_value=100.0, value=benchmark_alos_default, step=0.5,
                key="alos_tab_benchmark_alos", # キー名をタブ固有に
                help="ベンチマーク比較用の目標値"
            )
            # 「信頼区間を表示」は create_alos_volume_chart 関数自体には直接影響しないため、
            # もしグラフ描画ロジックで使うなら引数に追加するか、このオプションを削除する。
            # create_alos_volume_chart は信頼区間を描画していないため、一旦コメントアウト。
            # show_confidence_interval = st.checkbox(
            #     "信頼区間を表示", value=False, help="移動平均の信頼区間を表示", key="alos_tab_show_ci"
            # )

    # =================================================================
    # メインコンテンツ
    # =================================================================
    st.markdown("### 📊 平均在院日数と平均在院患者数の推移")

    # 分析スコープに応じた設定
    if analysis_scope == "統一フィルター範囲":
        selected_unit_for_charts = '病院全体' # alos_charts.py の関数が期待する値
        target_items_for_charts = []
        st.success("🏥 **分析対象:** 統一フィルター範囲全体")
    elif analysis_scope == "病棟別詳細":
        selected_unit_for_charts = '病棟別'
        target_items_for_charts = selected_items_actual
        if target_items_for_charts:
            st.info(f"🏨 **分析対象:** {len(target_items_for_charts)}病棟 ({', '.join(selected_items_display[:3])}{'...' if len(selected_items_display) > 3 else ''}) の詳細分析")
        else:
            st.warning("⚠️ 詳細分析対象の病棟を「表示・分析パラメータ調整」で選択してください。")
            return
    else:  # 診療科別詳細
        selected_unit_for_charts = '診療科別'
        target_items_for_charts = selected_items_actual
        if target_items_for_charts:
            st.info(f"🩺 **分析対象:** {len(target_items_for_charts)}診療科 ({', '.join(selected_items_display[:3])}{'...' if len(selected_items_display) > 3 else ''}) の詳細分析")
        else:
            st.warning("⚠️ 詳細分析対象の診療科を「表示・分析パラメータ調整」で選択してください。")
            return

    # チャート生成の粒度は「直近30日」相当の移動平均で固定とするか、
    # あるいは統一フィルターの期間に応じて動的に変更するか検討。
    # ここでは、統一フィルターの期間全体を対象とし、その中で移動平均を計算する方式を維持。
    # `selected_granularity` は `create_alos_volume_chart` の挙動に影響する。
    # 統一フィルターの期間が短い場合は '日単位'、長い場合は '月単位' などに自動調整も可能。
    # ここではシンプルに、移動平均を適用する日単位のチャートとする。
    # ただし、`create_alos_volume_chart` の '日単位(直近30日)' モードは特定の日数固定の移動平均なので、
    # 期間全体に対する移動平均を表示したい場合は、そのロジックの調整が必要。
    # 今回は、期間全体に対して指定された `moving_avg_window` で移動平均を計算する想定で進める。
    # `create_alos_volume_chart` は `selected_granularity` 引数を取りますが、
    # ここでは統一フィルタ期間全体を対象とするため、`selected_granularity` を固定値とするか、
    # `create_alos_volume_chart` のロジックを期間全体対応に修正する必要があります。
    # 一旦、`create_alos_volume_chart` が期間全体を扱えると仮定して `None` や `'日単位'` を渡すことを想定。
    # 元の `alos_analysis_tab.py` では `selected_granularity = '日単位(直近30日)'` と固定されていました。
    # これは統一フィルター期間と矛盾する可能性があるため、見直します。
    # 期間全体のデータに対して移動平均をかけるのが適切でしょう。

    # `create_alos_volume_chart` は第2引数に `selected_granularity` を取ります。
    # ここでは、統一フィルターで選択された期間全体を対象とし、そのデータに対して
    # `moving_avg_window` で指定された移動平均を計算・表示します。
    # そのため、`selected_granularity` は実質的に「日単位」のような扱いになります。
    # `create_alos_volume_chart` 内部で期間の扱いを調整するか、この呼び出し側でデータを事前に整形します。
    # 今回は、`create_alos_volume_chart` が `start_date`, `end_date` を受け取り、
    # その期間のデータで `moving_avg_window` を使って移動平均を計算すると仮定します。
    # `selected_granularity` 引数は、チャートのX軸の粒度やMA計算の単位を示唆するものでした。
    # ここではシンプルに「期間全体の日次データに対する移動平均」とします。
    # `create_alos_volume_chart` の `selected_granularity` 引数の意味合いを再確認。
    # `日単位(直近30日)` は特殊なモードだったため、それ以外の例えば `'日単位'` などを指定するか、
    # `create_alos_volume_chart` を修正して、期間全体を対象とした移動平均を正しく扱えるようにする。
    # `alos_charts.py` を見ると、`日単位(直近30日)` 以外のモードでは `df_filtered['集計期間']` を
    # 日付文字列にしていました。期間全体を対象とする場合、この集計期間の扱いに注意。
    # ここでは、`create_alos_volume_chart`が`start_date_ts`, `end_date_ts`を直接使うと想定し、
    # `selected_granularity`は`moving_avg_window`の単位を示すものとする。
    # 既存の `create_alos_volume_chart` は `selected_granularity` に応じてX軸の集計単位を変える。
    # 統一フィルタの期間でX軸を日単位で表示し、`moving_avg_window` のMAを引くのが自然。
    # この場合、`selected_granularity` は `'日単位'` (あるいは内部で日付をそのまま使うような指定) になる。

    try:
        # `selected_granularity` はグラフのX軸の粒度と移動平均の計算単位を決める。
        # ここでは統一フィルターで期間が決定されているので、日単位の推移を見るのが基本。
        # `create_alos_volume_chart` の `selected_granularity` 引数に `'日単位'` を渡すことで、
        # X軸を日単位にし、`moving_avg_window` (日数) で移動平均を計算させる。
        alos_chart, alos_data = create_alos_volume_chart(
            df_analysis, # フィルター済みの全データ
            selected_granularity='日単位', # X軸は日単位
            selected_unit=selected_unit_for_charts,
            target_items=target_items_for_charts,
            start_date=start_date_ts, # 統一フィルターの開始日
            end_date=end_date_ts,     # 統一フィルターの終了日
            moving_avg_window=moving_avg_window # タブ内で設定したMA期間
        )

        if alos_chart and alos_data is not None and not alos_data.empty:
            st.plotly_chart(alos_chart, use_container_width=True)

            with st.expander("📋 集計データ詳細", expanded=False):
                display_alos_data = alos_data.copy()
                if selected_unit_for_charts == '病棟別' and '集計単位名' in display_alos_data.columns:
                    ward_map_display = st.session_state.get('ward_mapping', {})
                    display_alos_data['集計単位名'] = display_alos_data['集計単位名'].apply(
                        lambda x: get_ward_display_name(str(x), ward_map_display)
                    )
                elif selected_unit_for_charts == '診療科別' and '集計単位名' in display_alos_data.columns:
                    display_alos_data['集計単位名'] = display_alos_data['集計単位名'].apply(
                        lambda x: get_display_name_for_dept(str(x), default_name=str(x))
                    )

                # 移動平均列名を動的に取得
                ma_col_name_actual = None
                for col in display_alos_data.columns:
                    if '平均在院日数 (' in col and '移動平均)' in col or '直近' in col: # MA列名のパターン
                        ma_col_name_actual = col
                        break
                if ma_col_name_actual is None and f'平均在院日数 ({moving_avg_window}日移動平均)' in display_alos_data.columns: # フォールバック
                     ma_col_name_actual = f'平均在院日数 ({moving_avg_window}日移動平均)'
                elif ma_col_name_actual is None and '平均在院日数_実測' in display_alos_data.columns: # さらにフォールバック
                    ma_col_name_actual = '平均在院日数_実測'


                display_cols = ['集計期間', '集計単位名']
                if ma_col_name_actual: display_cols.append(ma_col_name_actual)
                display_cols.extend(['日平均在院患者数', '平均在院日数_実測', '延べ在院患者数', '総入院患者数', '総退院患者数', '実日数'])
                existing_cols = [col for col in display_cols if col in display_alos_data.columns]

                format_dict = {'日平均在院患者数': "{:.1f}", '平均在院日数_実測': "{:.2f}",
                               '延べ在院患者数': "{:.0f}", '総入院患者数': "{:.0f}",
                               '総退院患者数': "{:.0f}", '実日数': "{:.0f}"}
                if ma_col_name_actual and ma_col_name_actual in display_alos_data.columns:
                    format_dict[ma_col_name_actual] = "{:.2f}"

                st.dataframe(
                    display_alos_data[existing_cols].style.format(format_dict, na_rep="-"),
                    height=400, use_container_width=True
                )
                csv_data = display_alos_data[existing_cols].to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📊 詳細データをCSVダウンロード", data=csv_data,
                    file_name=f"平均在院日数推移_{selected_unit_for_charts}_{start_date_ts.strftime('%Y%m%d')}_{end_date_ts.strftime('%Y%m%d')}.csv",
                    mime="text/csv", key="alos_tab_csv_download"
                )
        elif alos_data is not None and alos_data.empty :
            st.info("集計対象のデータがありませんでした。")
        else: # alos_chart is None or alos_data is None
            st.warning("📊 グラフを作成するためのデータが不足しているか、計算できませんでした。")
            logger.warning("ALOS チャート生成に失敗 (alos_chart or alos_data is None)")

    except Exception as e:
        st.error(f"❌ 平均在院日数チャート生成中にエラーが発生しました: {e}")
        logger.error(f"ALOS チャート生成エラー: {e}", exc_info=True)


    # ベンチマーク比較 (変更なし)
    if benchmark_alos and benchmark_alos > 0:
        st.markdown("### 🎯 平均在院日数ベンチマーク比較")
        try:
            # create_alos_benchmark_chart は target_items としてコードのリストを期待
            benchmark_chart = create_alos_benchmark_chart(
                df_analysis,
                selected_unit_for_charts,
                target_items_for_charts if selected_unit_for_charts != '病院全体' else None,
                start_date_ts,
                end_date_ts,
                benchmark_alos
            )
            if benchmark_chart:
                st.plotly_chart(benchmark_chart, use_container_width=True)
                # ... (既存のメトリクス表示ロジック) ...
                current_alos_for_metric = None
                if alos_data is not None and not alos_data.empty and '平均在院日数_実測' in alos_data.columns:
                    # analysis_scope に応じて平均の取り方を変える
                    if analysis_scope == "統一フィルター範囲":
                        current_alos_for_metric = alos_data['平均在院日数_実測'].mean()
                    elif target_items_for_charts: # 詳細分析対象が選択されている場合
                        # alos_data は既に target_items_for_charts でフィルタリングされているか、
                        # あるいは target_items_for_charts の各項目についてデータが含まれている。
                        # ここでは、表示されている項目の平均を取るのが適切か、あるいは代表的な値か。
                        # alos_data の構造に依存。一旦、全体の平均で。
                         current_alos_for_metric = alos_data[alos_data['集計単位名'].isin(target_items_for_charts)]['平均在院日数_実測'].mean()

                    if pd.notna(current_alos_for_metric):
                        diff_from_benchmark = current_alos_for_metric - benchmark_alos
                        diff_percent = (diff_from_benchmark / benchmark_alos) * 100 if benchmark_alos > 0 else 0
                        
                        bm_col1, bm_col2, bm_col3 = st.columns(3)
                        with bm_col1:
                            st.metric("選択範囲の平均在院日数", f"{current_alos_for_metric:.2f}日")
                        with bm_col2:
                            st.metric("目標値", f"{benchmark_alos:.2f}日")
                        with bm_col3:
                            st.metric("差異", f"{diff_from_benchmark:+.2f}日", f"{diff_percent:+.1f}%")
                        if diff_from_benchmark <= 0: st.success(f"✅ 目標値を{abs(diff_percent):.1f}%下回っており、良好な状況です。")
                        elif diff_percent <= 10: st.info(f"ℹ️ 目標値を{diff_percent:.1f}%上回っていますが、許容範囲内です。")
                        else: st.warning(f"⚠️ 目標値を{diff_percent:.1f}%上回っており、改善の余地があります。")
                    else:
                        st.info("選択範囲の平均在院日数を計算できませんでした（データ不足の可能性）。")

            else:
                st.info("ℹ️ ベンチマーク比較チャートを作成するためのデータが不足しています。")
        except Exception as e:
            st.error(f"❌ ベンチマーク比較チャート生成中にエラーが発生しました: {e}")
            logger.error(f"ベンチマークチャート生成エラー: {e}", exc_info=True)

    # 詳細メトリクス (変更なし)
    st.markdown("### 📈 詳細メトリクス")
    try:
        group_by_column_metrics = None
        if selected_unit_for_charts == '病棟別': group_by_column_metrics = '病棟コード'
        elif selected_unit_for_charts == '診療科別': group_by_column_metrics = '診療科名'

        metrics_df = calculate_alos_metrics(
            df_analysis, start_date_ts, end_date_ts, group_by_column_metrics
        )
        if not metrics_df.empty:
            metrics_df_filtered = metrics_df
            if selected_unit_for_charts != '病院全体' and target_items_for_charts:
                metrics_df_filtered = metrics_df[
                    metrics_df['集計単位'].astype(str).isin([str(item) for item in target_items_for_charts])
                ]
            display_metrics_df = metrics_df_filtered.copy()
            if group_by_column_metrics == '病棟コード' and '集計単位' in display_metrics_df.columns:
                ward_map_metrics = st.session_state.get('ward_mapping', {})
                display_metrics_df['集計単位'] = display_metrics_df['集計単位'].apply(lambda x: get_ward_display_name(str(x), ward_map_metrics))
            elif group_by_column_metrics == '診療科名' and '集計単位' in display_metrics_df.columns:
                display_metrics_df['集計単位'] = display_metrics_df['集計単位'].apply(lambda x: get_display_name_for_dept(str(x), default_name=str(x)))

            if not display_metrics_df.empty:
                format_dict_metrics = {'平均在院日数': "{:.2f}", '日平均在院患者数': "{:.1f}", '病床回転率': "{:.2f}",
                                       '延べ在院患者数': "{:.0f}", '総入院患者数': "{:.0f}", '総退院患者数': "{:.0f}",
                                       '緊急入院率': "{:.1f}%", '死亡率': "{:.1f}%"}
                for col in display_metrics_df.columns:
                    if col.endswith('割合') and col not in format_dict_metrics: format_dict_metrics[col] = "{:.1f}%"
                st.dataframe(
                    display_metrics_df.style.format(format_dict_metrics, na_rep="-"),
                    height=min(len(display_metrics_df) * 35 + 40, 500), use_container_width=True
                )
                # ... (CSVダウンロード、重要指標ハイライトのロジックは維持) ...
                csv_data_metrics = display_metrics_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📊 メトリクスをCSVダウンロード", data=csv_data_metrics,
                    file_name=f"平均在院日数メトリクス_{selected_unit_for_charts}_{start_date_ts.strftime('%Y%m%d')}_{end_date_ts.strftime('%Y%m%d')}.csv",
                    mime="text/csv", key="alos_tab_metrics_csv_download"
                )
                if len(display_metrics_df) > 1:
                    st.markdown("#### 🔍 重要指標ハイライト")
                    col1_highlight, col2_highlight = st.columns(2)
                    with col1_highlight:
                        if '平均在院日数' in display_metrics_df.columns:
                            max_alos_idx = display_metrics_df['平均在院日数'].idxmax()
                            min_alos_idx = display_metrics_df['平均在院日数'].idxmin()
                            max_unit = display_metrics_df.loc[max_alos_idx, '集計単位']; min_unit = display_metrics_df.loc[min_alos_idx, '集計単位']
                            max_alos_val = display_metrics_df.loc[max_alos_idx, '平均在院日数']; min_alos_val = display_metrics_df.loc[min_alos_idx, '平均在院日数']
                            st.success(f"⭐ **最短在院日数:** {min_unit} ({min_alos_val:.2f}日)")
                            st.warning(f"⚠️ **最長在院日数:** {max_unit} ({max_alos_val:.2f}日)")
                    with col2_highlight:
                        if '病床回転率' in display_metrics_df.columns:
                            max_turn_idx = display_metrics_df['病床回転率'].idxmax()
                            min_turn_idx = display_metrics_df['病床回転率'].idxmin()
                            max_turn_unit = display_metrics_df.loc[max_turn_idx, '集計単位']; min_turn_unit = display_metrics_df.loc[min_turn_idx, '集計単位']
                            max_turn_val = display_metrics_df.loc[max_turn_idx, '病床回転率']; min_turn_val = display_metrics_df.loc[min_turn_idx, '病床回転率']
                            st.success(f"🔄 **最高回転率:** {max_turn_unit} ({max_turn_val:.2f})")
                            st.info(f"🔄 **最低回転率:** {min_turn_unit} ({min_turn_val:.2f})")
            else:
                st.info("ℹ️ 選択された項目のメトリクスデータがありません。")
        else:
            st.warning("📊 メトリクスを計算するためのデータが不足しています。")
    except Exception as e:
        st.error(f"❌ メトリクス計算中にエラーが発生しました: {e}")
        logger.error(f"メトリクス計算エラー: {e}", exc_info=True)

    # 分析インサイトと推奨アクション (変更なし)
    if not metrics_df.empty: # metrics_df が calculate_alos_metrics から返されたもの
        st.markdown("### 💡 分析インサイトと推奨アクション")
        try:
            # ... (既存のインサイト生成・表示ロジックは維持) ...
            current_alos_for_insight = None
            if selected_unit_for_charts == '病院全体':
                current_alos_for_insight = metrics_df['平均在院日数'].iloc[0] if len(metrics_df) > 0 else None
            else:
                if target_items_for_charts:
                    metrics_df_for_insight = metrics_df[metrics_df['集計単位'].astype(str).isin([str(item) for item in target_items_for_charts])]
                    current_alos_for_insight = metrics_df_for_insight['平均在院日数'].mean() if not metrics_df_for_insight.empty else None
                else: # ターゲットアイテムが空（通常は発生しないはずだが）
                    current_alos_for_insight = metrics_df['平均在院日数'].mean() if not metrics_df.empty else None

            if pd.notna(current_alos_for_insight) and benchmark_alos > 0:
                diff_percent_insight = ((current_alos_for_insight - benchmark_alos) / benchmark_alos * 100)
                insights_col, actions_col = st.columns(2)
                with insights_col:
                    st.markdown("#### 📊 分析インサイト")
                    if current_alos_for_insight < benchmark_alos: st.success(f"✅ 現在の平均在院日数（{current_alos_for_insight:.2f}日）は目標値より {abs(diff_percent_insight):.1f}% 短く、良好です。")
                    elif current_alos_for_insight < benchmark_alos * 1.1: st.info(f"ℹ️ 平均在院日数は目標に近いですが、{diff_percent_insight:.1f}% 超過しています。")
                    else: st.warning(f"⚠️ 平均在院日数は目標を {diff_percent_insight:.1f}% 上回っており、短縮の余地があります。")
                with actions_col:
                    st.markdown("#### 🎯 推奨アクション")
                    if current_alos_for_insight < benchmark_alos: st.write("- ✅ 現状プロセスの標準化・維持")
                    elif current_alos_for_insight < benchmark_alos * 1.1: st.write("- 📊 クリニカルパス遵守確認")
                    else: st.write("- 🔍 長期入院患者レビュー実施")
            # ... (追加のインサイトも同様に)
            if '病床回転率' in metrics_df.columns:
                avg_turnover_insight = metrics_df_filtered['病床回転率'].mean() if not metrics_df_filtered.empty else 0
                if avg_turnover_insight < 0.7 and avg_turnover_insight > 0 : st.info(f"🔄 **病床回転率:** {avg_turnover_insight:.2f}回転と低めです。")
                elif avg_turnover_insight > 1.2 : st.success(f"🔄 **病床回転率:** {avg_turnover_insight:.2f}回転と高く、効率的です。")
            if '緊急入院率' in metrics_df.columns:
                avg_emergency_rate_insight = metrics_df_filtered['緊急入院率'].mean() if not metrics_df_filtered.empty else 0
                if avg_emergency_rate_insight > 30 : st.warning(f"🚨 **緊急入院率:** {avg_emergency_rate_insight:.1f}% と高いです。")
                elif avg_emergency_rate_insight < 10 and avg_emergency_rate_insight > 0 : st.success(f"✅ **緊急入院率:** {avg_emergency_rate_insight:.1f}% と低く、計画的です。")

        except Exception as e:
            st.error(f"❌ インサイト生成中にエラーが発生しました: {e}")
            logger.error(f"インサイト生成エラー: {e}", exc_info=True)

    logger.info("平均在院日数分析タブの処理が完了しました")