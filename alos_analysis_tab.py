# alos_analysis_tab.py
import streamlit as st
import pandas as pd
import numpy as np
# plotly.graph_objects や plotly.express は alos_charts.py で使用されるため、
# このファイルで直接使用していなければインポートは不要になる可能性があります。
# ただし、将来的にこのファイル内でPlotlyオブジェクトを直接操作する場合は残しておきます。
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from datetime import datetime, timedelta

from alos_charts import (
    create_alos_volume_chart,
    create_alos_benchmark_chart,
    calculate_alos_metrics
)

# utils.pyから病棟・診療科関連の関数をインポート
from utils import (
    # create_ward_name_mapping, # initialize_all_mappings で処理される想定
    get_ward_display_name, # <--- この行を追加またはコメント解除
    create_ward_display_options,
    # initialize_ward_mapping, # initialize_all_mappings で処理される想定
    safe_date_filter,
    # get_dept_display_name, # 表示時に必要なら (get_display_name_for_dept を使う)
    get_display_name_for_dept, # 診療科名取得用
    create_dept_display_options # 診療科選択肢生成用
)

def display_alos_analysis_tab(df_filtered_by_period, start_date_ts, end_date_ts, common_config=None):
    """
    平均在院日数分析タブの表示
    Args:
        df_filtered_by_period (pd.DataFrame): 呼び出し元で既に期間フィルタリングされたDataFrame
        start_date_ts (pd.Timestamp): 分析期間の開始日 (Timestamp型)
        end_date_ts (pd.Timestamp): 分析期間の終了日 (Timestamp型)
        common_config (dict, optional): 共通設定
    """

    # マッピング情報が初期化されていることを確認 (app.py等でデータロード後にinitialize_all_mappingsが呼ばれている前提)
    # もし、このタブが直接呼び出される前にマッピングが保証されていない場合は、
    # ここで st.session_state.get('dept_mapping_initialized') 等をチェックし、
    # 未初期化なら initialize_all_mappings を呼び出す処理を追加することも検討できます。
    # (ただし、通常はデータ処理フローの一部としてマッピング初期化が行われるべきです)

    if df_filtered_by_period is not None and not df_filtered_by_period.empty:
        # initialize_ward_mapping(df_filtered_by_period) # utils.pyのinitialize_all_mappingsで対応
        pass # マッピングは initialize_all_mappings で行われる想定
    else:
        st.warning("分析対象のデータが空です。")
        return

    if start_date_ts and end_date_ts:
        df_analysis = df_filtered_by_period.copy()
        period_text = f"{start_date_ts.strftime('%Y年%m月%d日')} ～ {end_date_ts.strftime('%Y年%m月%d日')}"
    else:
        st.error("期間情報が正しく渡されませんでした。")
        df_analysis = pd.DataFrame()
        period_text = "期間不明"

    total_days = (end_date_ts - start_date_ts).days + 1 if start_date_ts and end_date_ts else 0 # df_analysis['日付'].nunique() から変更
    st.info(f"📅 分析期間: {period_text} （{total_days}日間）") #

    if df_analysis.empty:
        st.warning("選択された期間にデータがありません。")
        return

    required_columns = [
        '日付', '病棟コード', '診療科名',
        '入院患者数（在院）', '入院患者数', '緊急入院患者数',
        '退院患者数', '死亡患者数', '総入院患者数', '総退院患者数'
    ]
    missing_columns = [col for col in required_columns if col not in df_analysis.columns]
    if missing_columns:
        # 列名補完ロジック (前回レビューで確認済みのため変更なし)
        if '入院患者数（在院）' in missing_columns and '在院患者数' in df_analysis.columns: #
            df_analysis['入院患者数（在院）'] = df_analysis['在院患者数'] #
            missing_columns.remove('入院患者数（在院）') #
        if '総入院患者数' in missing_columns and '入院患者数' in df_analysis.columns and '緊急入院患者数' in df_analysis.columns: #
            df_analysis['総入院患者数'] = df_analysis['入院患者数'] + df_analysis['緊急入院患者数'] #
            missing_columns.remove('総入院患者数') #
        if '総退院患者数' in missing_columns and '退院患者数' in df_analysis.columns and '死亡患者数' in df_analysis.columns: #
            df_analysis['総退院患者数'] = df_analysis['退院患者数'] + df_analysis['死亡患者数'] #
            missing_columns.remove('総退院患者数') #
    if missing_columns: # 再度チェック
        st.error(f"必要な列が見つかりません: {', '.join(missing_columns)}") #
        return

    min_date_for_chart = start_date_ts
    max_date_for_chart = end_date_ts
    date_range_days = (max_date_for_chart - min_date_for_chart).days + 1

    if date_range_days <= 0:
        st.error("分析終了日は分析開始日より後である必要があります。")
        return

    # サイドバー設定
    st.sidebar.markdown("<div class='sidebar-section'>", unsafe_allow_html=True) #
    st.sidebar.markdown("<div class='sidebar-title' style='font-size:1.1rem; margin-bottom:0.5rem;'>平均在院日数分析 設定</div>", unsafe_allow_html=True) #
    
    # selected_granularity は現状固定値なのでそのまま
    selected_granularity = '日単位(直近30日)' #
    st.session_state.alos_granularity = selected_granularity #
    
    selected_unit = st.sidebar.selectbox("集計単位:", ['病院全体', '病棟別', '診療科別'], index=0, key="alos_unit") #
    target_items = []

    if selected_unit == '病棟別':
        # 実績データから利用可能な病棟コードを取得
        available_wards_codes = sorted(df_analysis['病棟コード'].astype(str).unique()) if '病棟コード' in df_analysis.columns else [] #
        # セッションステートから病棟マッピングを取得 (utils.pyのinitialize_all_mappingsで設定済み想定)
        ward_mapping_dict = st.session_state.get('ward_mapping', {}) #
        # 表示用オプションと、表示名からコードへのマッピング辞書を生成
        ward_display_options_list, ward_option_to_code_map = create_ward_display_options(available_wards_codes, ward_mapping_dict) #

        # デフォルト選択 (最初の1つ、または空リスト)
        default_selected_wards = [ward_display_options_list[0]] if ward_display_options_list else [] #
        
        selected_ward_display_names = st.sidebar.multiselect( # 変数名を変更
            "対象病棟:",
            ward_display_options_list, # 表示名リストを使用
            default=default_selected_wards,
            key="alos_target_wards_display", # キーを新しいものに変更 (または既存キーでも良いが混同を避ける)
            help="分析対象の病棟を選択してください"
        )
        # 選択された表示名から実際の病棟コードに変換
        target_items = [ward_option_to_code_map[display_name] for display_name in selected_ward_display_names if display_name in ward_option_to_code_map] #

    elif selected_unit == '診療科別':
        # 実績データから利用可能な診療科名/コードを取得
        available_depts_codes = sorted(df_analysis['診療科名'].astype(str).unique()) if '診療科名' in df_analysis.columns else [] #
        # セッションステートから診療科マッピングを取得
        dept_mapping_dict = st.session_state.get('dept_mapping', {})
        # 表示用オプションと、表示名からコードへのマッピング辞書を生成
        # (create_dept_display_options は utils.py に実装されている想定)
        dept_display_options_list, dept_option_to_code_map = create_dept_display_options(available_depts_codes, dept_mapping_dict) #

        # デフォルト選択 (最初の1つ、または空リスト)
        default_selected_depts_display = [dept_display_options_list[0]] if dept_display_options_list else []
        
        selected_dept_display_names = st.sidebar.multiselect( # 変数名を変更
            "対象診療科:",
            dept_display_options_list, # 表示名リストを使用
            default=default_selected_depts_display,
            key="alos_target_depts_display" # キーを新しいものに変更
        )
        # 選択された表示名から実際の診療科コード (または実績データの診療科名) に変換
        target_items = [dept_option_to_code_map[display_name] for display_name in selected_dept_display_names if display_name in dept_option_to_code_map] #

    moving_avg_window = st.sidebar.slider("集計期間 (日)", 7, 90, 30, key="alos_ma_rolling_days") #
    benchmark_alos_default = common_config.get('benchmark_alos', 12.0) if common_config else 12.0 #
    benchmark_alos = st.sidebar.number_input("平均在院日数目標値 (日):", min_value=0.0, value=benchmark_alos_default, step=0.5, key="alos_benchmark", help="平均在院日数の目標値（ベンチマーク値）を設定します。") #
    st.sidebar.markdown("</div>", unsafe_allow_html=True) #

    # メインコンテンツ
    st.markdown("<div class='page-title'>平均在院日数分析</div>", unsafe_allow_html=True) #
    if selected_unit in ['病棟別', '診療科別'] and not target_items: #
        st.warning(f"分析対象の{selected_unit.replace('別','')}をサイドバーで選択してください。") #
        return
    st.markdown("<div class='section-title'>平均在院日数と平均在院患者数の推移（デフォルト30日）</div>", unsafe_allow_html=True) #

    st.markdown(f""" 
        <div style='font-size: 18px; color: #666; margin-bottom:1rem;'>
            選択期間: {min_date_for_chart.strftime('%Y年%m月%d日')} ～ {max_date_for_chart.strftime('%Y年%m月%d日')}
            （{date_range_days}日間）
        </div>
    """, unsafe_allow_html=True) #

    alos_chart, alos_data = create_alos_volume_chart(
        df_analysis,
        selected_granularity,
        selected_unit,
        target_items, # ここは変換後のコードリスト
        min_date_for_chart,
        max_date_for_chart,
        moving_avg_window
    ) #

    if alos_chart and alos_data is not None:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True) #
        st.plotly_chart(alos_chart, use_container_width=True) #
        st.markdown("</div>", unsafe_allow_html=True) #

        with st.expander("集計データ詳細", expanded=False): #
            # 集計データ表示ロジック (前回レビューで確認済みのため変更なし)
            if selected_granularity == '月単位': ma_suffix = f"{moving_avg_window}ヶ月移動平均" #
            elif selected_granularity == '週単位': ma_suffix = f"{moving_avg_window}週移動平均" #
            else: ma_suffix = f"直近{moving_avg_window}日" #
            ma_col_name = f'平均在院日数 ({ma_suffix})' #
            
            # alos_data の '集計単位名' を表示用に変換する
            display_alos_data = alos_data.copy()
            if selected_unit == '病棟別' and '集計単位名' in display_alos_data.columns:
                ward_map_display = st.session_state.get('ward_mapping', {})
                display_alos_data['集計単位名'] = display_alos_data['集計単位名'].apply(
                    lambda x: get_ward_display_name(x, ward_map_display)
                )
            elif selected_unit == '診療科別' and '集計単位名' in display_alos_data.columns:
                # dept_map_display = st.session_state.get('dept_mapping', {}) # この行は不要
                display_alos_data['集計単位名'] = display_alos_data['集計単位名'].apply(
                    lambda x: get_display_name_for_dept(x, default_name=x) # dept_mapping引数を削除
                )

            display_cols = ['集計期間', '集計単位名', ma_col_name, '日平均在院患者数', '平均在院日数_実測', '延べ在院患者数', '総入院患者数', '総退院患者数', '実日数'] #
            existing_cols = [col for col in display_cols if col in display_alos_data.columns] #
            format_dict = {'日平均在院患者数': "{:.1f}", '平均在院日数_実測': "{:.2f}",'延べ在院患者数': "{:.0f}", '総入院患者数': "{:.0f}", '総退院患者数': "{:.0f}", '実日数': "{:.0f}"} #
            if ma_col_name in display_alos_data.columns: format_dict[ma_col_name] = "{:.2f}" #
            st.dataframe(display_alos_data[existing_cols].style.format(format_dict), height=400) #
    else:
        st.warning("グラフを作成するためのデータが不足しています。期間や選択項目を確認してください。") #

    if benchmark_alos and benchmark_alos > 0:
        st.markdown("<div class='section-title'>平均在院日数ベンチマーク比較</div>", unsafe_allow_html=True) #
        benchmark_chart = create_alos_benchmark_chart(
            df_analysis,
            selected_unit,
            target_items if selected_unit != '病院全体' else None, # ここもコードリスト
            min_date_for_chart,
            max_date_for_chart,
            benchmark_alos
        ) #
        if benchmark_chart:
            st.markdown("<div class='chart-container'>", unsafe_allow_html=True) #
            st.plotly_chart(benchmark_chart, use_container_width=True) #
            st.markdown("</div>", unsafe_allow_html=True) #
        else:
            st.info("ベンチマーク比較チャートを作成するためのデータが不足しています。") #

    st.markdown("<div class='section-title'>詳細メトリクス</div>", unsafe_allow_html=True) #
    group_by_column_metrics = None
    if selected_unit == '病棟別': group_by_column_metrics = '病棟コード' #
    elif selected_unit == '診療科別': group_by_column_metrics = '診療科名' #

    metrics_df = calculate_alos_metrics(
        df_analysis,
        min_date_for_chart,
        max_date_for_chart,
        group_by_column_metrics
    ) #

    if not metrics_df.empty:
        # metrics_df の '集計単位' を表示用に変換する
        display_metrics_df = metrics_df.copy()
        if group_by_column_metrics == '病棟コード' and '集計単位' in display_metrics_df.columns:
            ward_map_metrics = st.session_state.get('ward_mapping', {})
            display_metrics_df['集計単位'] = display_metrics_df['集計単位'].apply(
                lambda x: get_ward_display_name(x, ward_map_metrics) # ward_mapping は引数として渡せる
            )

        elif group_by_column_metrics == '診療科名' and '集計単位' in display_metrics_df.columns:
            # dept_map_metrics = st.session_state.get('dept_mapping', {}) # この行は不要
            display_metrics_df['集計単位'] = display_metrics_df['集計単位'].apply(lambda x: get_display_name_for_dept(x, default_name=x)) # dept_mapping引数を削除

            # フィルタリングも表示名ベースではなく、元のコード(target_items)で行う必要があるため、
            # metrics_df のフィルタリングは表示名変換前に行う。
            # ただし、ユーザーが選択するのは表示名なので、target_items がコードであることを確認。

        if selected_unit != '病院全体' and target_items:
            metrics_df_filtered_for_display = metrics_df[metrics_df['集計単位'].astype(str).isin([str(item) for item in target_items])]
            display_metrics_df = metrics_df_filtered_for_display.copy()
            if group_by_column_metrics == '病棟コード' and '集計単位' in display_metrics_df.columns:
                ward_map_metrics = st.session_state.get('ward_mapping', {})
                display_metrics_df['集計単位'] = display_metrics_df['集計単位'].apply(lambda x: get_ward_display_name(x, ward_map_metrics))
            elif group_by_column_metrics == '診療科名' and '集計単位' in display_metrics_df.columns:
                # dept_map_metrics = st.session_state.get('dept_mapping', {}) # この行は不要
                display_metrics_df['集計単位'] = display_metrics_df['集計単位'].apply(lambda x: get_display_name_for_dept(x, default_name=x)) # dept_mapping引数を削除
        else: # 病院全体の場合、またはフィルタリング不要の場合
            pass # display_metrics_df は既に変換済み（または全体なので変換不要）

        if not display_metrics_df.empty:
            format_dict_metrics = {'平均在院日数': "{:.2f}", '日平均在院患者数': "{:.1f}", '病床回転率': "{:.2f}", '延べ在院患者数': "{:.0f}", '総入院患者数': "{:.0f}", '総退院患者数': "{:.0f}", '緊急入院率': "{:.1f}%", '死亡率': "{:.1f}%"} #
            if '在院患者数割合' in display_metrics_df.columns: format_dict_metrics.update({'在院患者数割合': "{:.1f}%", '入院患者数割合': "{:.1f}%", '退院患者数割合': "{:.1f}%"}) #
            st.dataframe(display_metrics_df.style.format(format_dict_metrics), height=min(len(display_metrics_df) * 35 + 40, 500)) #

            csv_data = display_metrics_df.to_csv(index=False).encode('utf-8-sig') # 表示用DFをCSVに
            # CSVファイル名の selected_unit も表示名に合わせるか検討 (例: selected_unit_display_name)
            selected_unit_display_name = selected_unit
            if selected_unit == '病棟別' and target_items:
                # 複数の場合、最初の表示名などを使うか、総称にする
                selected_unit_display_name = "選択病棟"
            elif selected_unit == '診療科別' and target_items:
                selected_unit_display_name = "選択診療科"

            st.download_button(
                label="CSVダウンロード",
                data=csv_data,
                file_name=f"平均在院日数分析_{selected_unit_display_name}_{min_date_for_chart.strftime('%Y%m%d')}_{max_date_for_chart.strftime('%Y%m%d')}.csv",
                mime="text/csv",
                help="詳細メトリクスをCSVファイルとしてダウンロードします。"
            ) #
        else:
            st.info("選択された項目のメトリクスデータがありません。") #
    else:
        st.warning("メトリクスを計算するためのデータが不足しています。") #

    # 分析インサイト (前回レビューで確認済み、表示名の扱いは metrics_df の変換に依存)
    st.markdown("<div class='section-title'>分析インサイトと推奨アクション</div>", unsafe_allow_html=True) #
    if not metrics_df.empty: # 元のmetrics_dfで計算、表示は不要
        current_alos_for_insight = None
        if selected_unit == '病院全体':
            current_alos_for_insight = metrics_df['平均在院日数'].iloc[0] if len(metrics_df) > 0 else None #
        else:
            if target_items: # 特定の項目が選択されている場合
                 # metrics_df はフィルタリング前の可能性があるので、target_itemsでフィルタリング
                metrics_df_for_insight = metrics_df[metrics_df['集計単位'].astype(str).isin([str(item) for item in target_items])]
                current_alos_for_insight = metrics_df_for_insight['平均在院日数'].mean() if not metrics_df_for_insight.empty else None #
            else: # 何も選択されていない場合（通常は発生しないはずだが念のため）
                current_alos_for_insight = metrics_df['平均在院日数'].mean() if not metrics_df.empty else None

        if current_alos_for_insight is not None:
            insights = [] #
            actions = [] #
            if benchmark_alos and benchmark_alos > 0: # benchmark_alos > 0 を追加
                diff_percent = ((current_alos_for_insight - benchmark_alos) / benchmark_alos * 100) if benchmark_alos > 0 else 0 #
                if current_alos_for_insight < benchmark_alos: #
                    insights.append(f"現在の平均在院日数は目標値より {abs(diff_percent):.1f}% 短く、良好な水準です。") #
                    actions.append("この水準を維持するために、現在の退院支援プロセスを標準化し、文書化してください。") #
                elif current_alos_for_insight < benchmark_alos * 1.1: #
                    insights.append(f"現在の平均在院日数は目標値に近い水準ですが、{diff_percent:.1f}% 超過しています。") #
                    actions.append("クリニカルパスの遵守状況を確認し、退院調整を適切に進めることで改善できる可能性があります。") #
                else: #
                    insights.append(f"現在の平均在院日数は目標値を {diff_percent:.1f}% 上回っており、短縮の余地があります。") #
                    actions.append("長期入院患者のケースレビューを行い、退院阻害要因を特定して改善策を検討してください。") #

            # metrics_df は target_items でフィルタリングされたものを使うべき
            metrics_df_for_insight_other = metrics_df
            if selected_unit != '病院全体' and target_items:
                 metrics_df_for_insight_other = metrics_df[metrics_df['集計単位'].astype(str).isin([str(item) for item in target_items])]


            turnover_rate = metrics_df_for_insight_other['病床回転率'].mean() if '病床回転率' in metrics_df_for_insight_other.columns and not metrics_df_for_insight_other.empty else None #
            if turnover_rate is not None:
                if turnover_rate < 0.7: #
                    insights.append(f"病床回転率が {turnover_rate:.2f} 回転と低めです。収益性に影響を与える可能性があります。") #
                    actions.append("入退院プロセスの効率化と、不必要な入院日数の削減を検討してください。") #
                elif turnover_rate > 1.2: #
                    insights.append(f"病床回転率が {turnover_rate:.2f} 回転と高く、効率的な病床運用ができています。") #
                    actions.append("高い回転率が患者ケアの質に影響していないか確認しつつ、この効率を維持してください。") #

            emergency_rate = metrics_df_for_insight_other['緊急入院率'].mean() if '緊急入院率' in metrics_df_for_insight_other.columns and not metrics_df_for_insight_other.empty else None #
            if emergency_rate is not None and emergency_rate > 30: #
                insights.append(f"緊急入院率が {emergency_rate:.1f}% と高く、計画的な入院管理が難しい状況です。") #
                actions.append("緊急入院の理由を分析し、予防可能な再入院の減少策を検討してください。") #

            if insights:
                st.markdown("<div class='info-card'>", unsafe_allow_html=True) #
                st.markdown("#### インサイト") #
                for insight in insights:
                    st.markdown(f"- {insight}") #
                st.markdown("</div>", unsafe_allow_html=True) #

            if actions:
                st.markdown("<div class='success-card'>", unsafe_allow_html=True) #
                st.markdown("#### 推奨アクション") #
                for action in actions:
                    st.markdown(f"- {action}") #
                st.markdown("</div>", unsafe_allow_html=True) #
        else:
            st.info("平均在院日数の分析インサイトを生成するためのデータが不足しています。") #
    else:
        st.info("分析インサイトを生成するためのデータが不足しています。") #