import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from datetime import datetime, timedelta

from alos_charts import (
    create_alos_volume_chart,
    create_alos_benchmark_chart,
    calculate_alos_metrics
)

# utils.pyから病棟関連の関数をインポート
from utils import (
    create_ward_name_mapping,
    get_ward_display_name,
    create_ward_display_options,
    initialize_ward_mapping,
    safe_date_filter
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
    
    # (1) 病棟マッピングの初期化: 渡されたフィルタ済みデータに対して行う
    #     df_filtered_by_period が空でないことを確認してから初期化するとより安全
    if df_filtered_by_period is not None and not df_filtered_by_period.empty:
        initialize_ward_mapping(df_filtered_by_period)
    else:
        st.warning("分析対象のデータが空です。")
        return

    # (2) 期間情報の取得と表示: 引数で渡された Timestamp を使用
    #     このセクションの else ブロック (セッションステートからの読み込みや全期間の計算) は不要になる
    if start_date_ts and end_date_ts:
        # (3) df_analysis の作成: 引数でフィルタ済みなのでそのまま使用
        df_analysis = df_filtered_by_period.copy() # 変更を加える可能性があるのでコピー
        
        # (4) period_text の作成: Timestamp をフォーマット
        period_text = f"{start_date_ts.strftime('%Y年%m月%d日')} ～ {end_date_ts.strftime('%Y年%m月%d日')}"
    else:
        # 引数が正しく渡されなかった場合のフォールバック (通常は発生しないはず)
        st.error("期間情報が正しく渡されませんでした。")
        df_analysis = pd.DataFrame() # 空のDF
        period_text = "期間不明"
        
    # (7) total_days の計算
    total_days = len(df_analysis['日付'].unique()) if not df_analysis.empty and '日付' in df_analysis.columns else 0
    # (8) st.info の表示
    st.info(f"📅 分析期間: {period_text} （{total_days}日間）")
    
    if df_analysis.empty: # (3) の結果 df_analysis が空ならここでリターン
        st.warning("選択された期間にデータがありません。")
        return
    
    # (9) 列名確認 (これは df_analysis に対して行う)
    required_columns = [
        '日付', '病棟コード', '診療科名', 
        '入院患者数（在院）', '入院患者数', '緊急入院患者数', 
        '退院患者数', '死亡患者数', '総入院患者数', '総退院患者数'
    ]
    
    missing_columns = [col for col in required_columns if col not in df_analysis.columns]
    if missing_columns:
        # ... (既存の列補完ロジック - df_analysis を変更) ...
        if '入院患者数（在院）' in missing_columns and '在院患者数' in df_analysis.columns:
            df_analysis['入院患者数（在院）'] = df_analysis['在院患者数']
            missing_columns.remove('入院患者数（在院）')
        
        if '総入院患者数' in missing_columns and '入院患者数' in df_analysis.columns and '緊急入院患者数' in df_analysis.columns:
            df_analysis['総入院患者数'] = df_analysis['入院患者数'] + df_analysis['緊急入院患者数']
            missing_columns.remove('総入院患者数')
        
        if '総退院患者数' in missing_columns and '退院患者数' in df_analysis.columns and '死亡患者数' in df_analysis.columns:
            df_analysis['総退院患者数'] = df_analysis['退院患者数'] + df_analysis['死亡患者数']
            missing_columns.remove('総退院患者数')

    if missing_columns: # 再度チェック
        st.error(f"必要な列が見つかりません: {', '.join(missing_columns)}")
        return
    
    # (10) min_date, (11) max_date の再定義: 引数で渡された Timestamp をそのまま使用
    #     pd.to_datetime() による変換は不要
    #     変数名を start_date_ts, end_date_ts に合わせるか、このまま min_date, max_date としても良い
    min_date_for_chart = start_date_ts
    max_date_for_chart = end_date_ts
    
    # (12) date_range の計算
    date_range_days = (max_date_for_chart - min_date_for_chart).days + 1 # 変数名修正
    
    # (13) date_range_days のチェック
    if date_range_days <= 0:
        st.error("分析終了日は分析開始日より後である必要があります。")
        return
    
    # (14) サイドバー設定 (変更なし)
    st.sidebar.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-title' style='font-size:1.1rem; margin-bottom:0.5rem;'>平均在院日数分析 設定</div>", unsafe_allow_html=True)
    selected_granularity = '日単位(直近30日)' # 固定
    st.session_state.alos_granularity = selected_granularity
    selected_unit = st.sidebar.selectbox("集計単位:", ['病院全体', '病棟別', '診療科別'], index=0, key="alos_unit")
    target_items = []
    if selected_unit == '病棟別':
        # initialize_ward_mapping は df_analysis (フィルタ済み) で実行済みなので、
        # df_analysis から unique な病棟コードを取得する方が適切かもしれない。
        # ただし、選択肢としては全病棟を提示したい場合もあるので、元の df (st.session_state.df) から取るのが良い場合も。
        # ここでは、UIの選択肢は全病棟からとし、実際の分析は df_analysis で行う。
        # 元の df を参照する場合は、この関数の引数として渡すか、st.session_state.df を直接参照する。
        # ここでは、簡単のため df_analysis から取得する。
        available_wards = sorted(df_analysis['病棟コード'].astype(str).unique()) if '病棟コード' in df_analysis.columns else []
        ward_mapping = st.session_state.get('ward_mapping', {})
        ward_options, option_to_code = create_ward_display_options(available_wards, ward_mapping)
        selected_ward_options = st.sidebar.multiselect("対象病棟:", ward_options, default=[ward_options[0]] if ward_options else [], key="alos_target_wards", help="分析対象の病棟を選択してください")
        target_items = [option_to_code[option] for option in selected_ward_options]
    elif selected_unit == '診療科別':
        available_depts = sorted(df_analysis['診療科名'].astype(str).unique()) if '診療科名' in df_analysis.columns else []
        target_items = st.sidebar.multiselect("対象診療科:", available_depts, default=available_depts[0] if available_depts else None, key="alos_target_depts")
    moving_avg_window = st.sidebar.slider("集計期間 (日)", 7, 90, 30, key="alos_ma_rolling_days")
    benchmark_alos = st.sidebar.number_input("平均在院日数目標値 (日):", min_value=0.0, value=common_config.get('benchmark_alos', 12.0) if common_config else 12.0, step=0.5, key="alos_benchmark", help="平均在院日数の目標値（ベンチマーク値）を設定します。")
    st.sidebar.markdown("</div>", unsafe_allow_html=True)
    
    # (15) メインコンテンツ (変更なし)
    st.markdown("<div class='page-title'>平均在院日数分析</div>", unsafe_allow_html=True)
    if selected_unit in ['病棟別', '診療科別'] and not target_items:
        st.warning(f"分析対象の{selected_unit.replace('別','')}をサイドバーで選択してください。")
        return
    st.markdown("<div class='section-title'>平均在院日数と平均在院患者数の推移（デフォルト30日）</div>", unsafe_allow_html=True)
    st.markdown(f"""
        <div style='font-size: 18px; color: #666; margin-bottom:1rem;'>
            選択期間: {min_date_for_chart.strftime('%Y年%m月%d日')} ～ {max_date_for_chart.strftime('%Y年%m月%d日')}
            （{date_range_days}日間）
        </div>
    """, unsafe_allow_html=True)
    
    # (16) グラフと集計データの取得
    # (17) create_alos_volume_chart に渡す df は、フィルタ済みの df_analysis を使用
    # (18) start_date, (19) end_date も Timestamp 型の min_date_for_chart, max_date_for_chart を使用
    alos_chart, alos_data = create_alos_volume_chart(
        df_analysis, # フィルタリング済みのデータ
        selected_granularity, 
        selected_unit, 
        target_items, 
        min_date_for_chart, # Timestamp
        max_date_for_chart, # Timestamp
        moving_avg_window
    )

    
    if alos_chart and alos_data is not None:
        # グラフの表示
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        st.plotly_chart(alos_chart, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        # 詳細データ表示
        with st.expander("集計データ詳細", expanded=False):
            if selected_granularity == '月単位':
                ma_suffix = f"{moving_avg_window}ヶ月移動平均"
            elif selected_granularity == '週単位':
                ma_suffix = f"{moving_avg_window}週移動平均"
            else:  # 日単位(直近30日)
                ma_suffix = f"直近{moving_avg_window}日"
            
            ma_col_name = f'平均在院日数 ({ma_suffix})'
            
            # 列が存在するか確認し、ない場合は表示から除外
            display_cols = [
                '集計期間', '集計単位名', ma_col_name, '日平均在院患者数', 
                '平均在院日数_実測', '延べ在院患者数', '総入院患者数', '総退院患者数', '実日数'
            ]
            
            # 存在する列のみをフィルタリング
            existing_cols = [col for col in display_cols if col in alos_data.columns]
            
            # フォーマット辞書を動的に作成
            format_dict = {
                '日平均在院患者数': "{:.1f}", 
                '平均在院日数_実測': "{:.2f}",
                '延べ在院患者数': "{:.0f}", 
                '総入院患者数': "{:.0f}", 
                '総退院患者数': "{:.0f}", 
                '実日数': "{:.0f}"
            }
            
            # 移動平均列が存在する場合のみフォーマットを追加
            if ma_col_name in alos_data.columns:
                format_dict[ma_col_name] = "{:.2f}"
            
            st.dataframe(
                alos_data[existing_cols].style.format(format_dict),
                height=400
            )
    else:
        st.warning("グラフを作成するためのデータが不足しています。期間や選択項目を確認してください。")
    
    # ベンチマーク比較チャート
    if benchmark_alos and benchmark_alos > 0:
        st.markdown("<div class='section-title'>平均在院日数ベンチマーク比較</div>", unsafe_allow_html=True)
        
        # ベンチマークチャートの作成
        benchmark_chart = create_alos_benchmark_chart(
            df_analysis, # df から df_analysis に変更
            selected_unit, 
            target_items if selected_unit != '病院全体' else None, 
            min_date_for_chart, # Timestamp
            max_date_for_chart, # Timestamp
            benchmark_alos
        )        

        if benchmark_chart:
            st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
            st.plotly_chart(benchmark_chart, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("ベンチマーク比較チャートを作成するためのデータが不足しています。")
    
    # 詳細メトリクス表示
    st.markdown("<div class='section-title'>詳細メトリクス</div>", unsafe_allow_html=True)
    group_by_column_metrics = None
    if selected_unit == '病棟別': group_by_column_metrics = '病棟コード'
    elif selected_unit == '診療科別': group_by_column_metrics = '診療科名'
    
    metrics_df = calculate_alos_metrics(
        df_analysis, # フィルタ済みデータを使用
        min_date_for_chart, # Timestamp
        max_date_for_chart, # Timestamp
        group_by_column_metrics
    )
    
    if not metrics_df.empty:
        # 選択された項目のみをフィルタリング
        if selected_unit != '病院全体' and target_items:
            metrics_df = metrics_df[metrics_df['集計単位'].astype(str).isin([str(item) for item in target_items])]
        
        # メトリクスの表示
        if not metrics_df.empty:
            # 表示用のフォーマット
            format_dict = {
                '平均在院日数': "{:.2f}",
                '日平均在院患者数': "{:.1f}",
                '病床回転率': "{:.2f}",
                '延べ在院患者数': "{:.0f}",
                '総入院患者数': "{:.0f}",
                '総退院患者数': "{:.0f}",
                '緊急入院率': "{:.1f}%",
                '死亡率': "{:.1f}%"
            }
            
            # 割合列がある場合のフォーマット追加
            if '在院患者数割合' in metrics_df.columns:
                format_dict.update({
                    '在院患者数割合': "{:.1f}%",
                    '入院患者数割合': "{:.1f}%",
                    '退院患者数割合': "{:.1f}%"
                })
            
            st.dataframe(
                metrics_df.style.format(format_dict),
                height=min(len(metrics_df) * 35 + 40, 500)
            )
            
            # ダウンロードボタン
            csv_data = metrics_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="CSVダウンロード",
                data=csv_data,
                file_name=f"平均在院日数分析_{selected_unit}_{min_date.strftime('%Y%m%d')}_{max_date.strftime('%Y%m%d')}.csv",
                mime="text/csv",
                help="詳細メトリクスをCSVファイルとしてダウンロードします。"
            )
        else:
            st.info("選択された項目のメトリクスデータがありません。")
    else:
        st.warning("メトリクスを計算するためのデータが不足しています。")
    
    # 分析インサイト
    st.markdown("<div class='section-title'>分析インサイトと推奨アクション</div>", unsafe_allow_html=True)
    
    # 平均在院日数の評価
    if not metrics_df.empty:
        # 病院全体または選択された項目の評価
        if selected_unit == '病院全体':
            current_alos = metrics_df['平均在院日数'].iloc[0] if len(metrics_df) > 0 else None
        else:
            # 選択された項目の平均値
            current_alos = metrics_df['平均在院日数'].mean() if len(metrics_df) > 0 else None
        
        if current_alos is not None:
            # インサイトの生成
            insights = []
            actions = []
            
            # 平均在院日数のインサイト
            if benchmark_alos:
                diff_percent = ((current_alos - benchmark_alos) / benchmark_alos * 100) if benchmark_alos > 0 else 0
                
                if current_alos < benchmark_alos:
                    insights.append(f"現在の平均在院日数は目標値より {abs(diff_percent):.1f}% 短く、良好な水準です。")
                    actions.append("この水準を維持するために、現在の退院支援プロセスを標準化し、文書化してください。")
                elif current_alos < benchmark_alos * 1.1:  # 目標の10%以内
                    insights.append(f"現在の平均在院日数は目標値に近い水準ですが、{diff_percent:.1f}% 超過しています。")
                    actions.append("クリニカルパスの遵守状況を確認し、退院調整を適切に進めることで改善できる可能性があります。")
                else:  # 目標の10%超過
                    insights.append(f"現在の平均在院日数は目標値を {diff_percent:.1f}% 上回っており、短縮の余地があります。")
                    actions.append("長期入院患者のケースレビューを行い、退院阻害要因を特定して改善策を検討してください。")
            
            # 病床回転率のインサイト
            turnover_rate = metrics_df['病床回転率'].mean() if '病床回転率' in metrics_df.columns else None
            if turnover_rate is not None:
                if turnover_rate < 0.7:
                    insights.append(f"病床回転率が {turnover_rate:.2f} 回転と低めです。収益性に影響を与える可能性があります。")
                    actions.append("入退院プロセスの効率化と、不必要な入院日数の削減を検討してください。")
                elif turnover_rate > 1.2:
                    insights.append(f"病床回転率が {turnover_rate:.2f} 回転と高く、効率的な病床運用ができています。")
                    actions.append("高い回転率が患者ケアの質に影響していないか確認しつつ、この効率を維持してください。")
            
            # 緊急入院率のインサイト
            emergency_rate = metrics_df['緊急入院率'].mean() if '緊急入院率' in metrics_df.columns else None
            if emergency_rate is not None and emergency_rate > 30:
                insights.append(f"緊急入院率が {emergency_rate:.1f}% と高く、計画的な入院管理が難しい状況です。")
                actions.append("緊急入院の理由を分析し、予防可能な再入院の減少策を検討してください。")
            
            # インサイトとアクションの表示
            if insights:
                st.markdown("<div class='info-card'>", unsafe_allow_html=True)
                st.markdown("#### インサイト")
                for insight in insights:
                    st.markdown(f"- {insight}")
                st.markdown("</div>", unsafe_allow_html=True)
            
            if actions:
                st.markdown("<div class='success-card'>", unsafe_allow_html=True)
                st.markdown("#### 推奨アクション")
                for action in actions:
                    st.markdown(f"- {action}")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("平均在院日数の分析インサイトを生成するためのデータが不足しています。")
    else:
        st.info("分析インサイトを生成するためのデータが不足しています。")