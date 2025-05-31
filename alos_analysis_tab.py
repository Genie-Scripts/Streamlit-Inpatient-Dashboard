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

def display_alos_analysis_tab(df, start_date, end_date, common_config=None):
    """平均在院日数分析タブの表示"""
    
    # 病棟マッピングの初期化
    initialize_ward_mapping(df)
    
    # ⭐ 期間情報の取得と表示
    if start_date and end_date:
        # 既にフィルタリング済みのデータを受け取っている場合
        df_analysis = df.copy()
        period_text = f"{start_date} ～ {end_date}"
    else:
        # セッションステートから期間情報を取得
        session_start = st.session_state.get('alos_start_date')
        session_end = st.session_state.get('alos_end_date')
        
        if session_start and session_end:
            df_analysis = safe_date_filter(df, session_start, session_end)
            period_text = f"{session_start} ～ {session_end}"
        else:
            df_analysis = df.copy()
            if not df_analysis.empty and '日付' in df_analysis.columns:
                min_date = df_analysis['日付'].min().strftime('%Y年%m月%d日')
                max_date = df_analysis['日付'].max().strftime('%Y年%m月%d日')
                period_text = f"{min_date} ～ {max_date}"
            else:
                period_text = "期間不明"
    
    # ⭐ 期間情報の表示
    total_days = len(df_analysis['日付'].unique()) if not df_analysis.empty else 0
    st.info(f"📅 選択期間: {period_text} （{total_days}日間）")
    
    if df_analysis.empty:
        st.warning("選択された期間にデータがありません。")
        return
    
    # 列名確認
    required_columns = [
        '日付', '病棟コード', '診療科名', 
        '入院患者数（在院）', '入院患者数', '緊急入院患者数', 
        '退院患者数', '死亡患者数', '総入院患者数', '総退院患者数'
    ]
    
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        # もし入院患者数（在院）がない場合は、在院患者数を代用
        if '入院患者数（在院）' in missing_columns and '在院患者数' in df.columns:
            df['入院患者数（在院）'] = df['在院患者数']
            missing_columns.remove('入院患者数（在院）')
        
        # 総入院患者数と総退院患者数の計算
        if '総入院患者数' in missing_columns and '入院患者数' in df.columns and '緊急入院患者数' in df.columns:
            df['総入院患者数'] = df['入院患者数'] + df['緊急入院患者数']
            missing_columns.remove('総入院患者数')
        
        if '総退院患者数' in missing_columns and '退院患者数' in df.columns and '死亡患者数' in df.columns:
            df['総退院患者数'] = df['退院患者数'] + df['死亡患者数']
            missing_columns.remove('総退院患者数')
    
    if missing_columns:
        st.error(f"必要な列が見つかりません: {', '.join(missing_columns)}")
        return
    
    # 日付範囲の確認
    min_date = pd.to_datetime(start_date)
    max_date = pd.to_datetime(end_date)
    date_range = (max_date - min_date).days + 1
    
    if date_range <= 0:
        st.error("分析終了日は分析開始日より後である必要があります。")
        return
    
    # サイドバー設定
    st.sidebar.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-title' style='font-size:1.1rem; margin-bottom:0.5rem;'>平均在院日数分析 設定</div>", unsafe_allow_html=True)
    
    # 集計粒度（日単位(直近30日)に固定）
    selected_granularity = '日単位(直近30日)'
    st.session_state.alos_granularity = selected_granularity
    
    # 集計単位選択
    selected_unit = st.sidebar.selectbox(
        "集計単位:", 
        ['病院全体', '病棟別', '診療科別'], 
        index=0, 
        key="alos_unit"
    )
    
    # 対象項目選択（病棟または診療科）
    target_items = []
    if selected_unit == '病棟別':
        available_wards = sorted(df['病棟コード'].astype(str).unique())
        
        # 病棟名マッピングを取得
        ward_mapping = st.session_state.get('ward_mapping', {})
        
        # 表示オプションを作成
        ward_options, option_to_code = create_ward_display_options(available_wards, ward_mapping)
        
        selected_ward_options = st.sidebar.multiselect(
            "対象病棟:", 
            ward_options, 
            default=[ward_options[0]] if ward_options else [], 
            key="alos_target_wards",
            help="分析対象の病棟を選択してください"
        )
        
        # 選択された表示名から病棟コードを取得
        target_items = [option_to_code[option] for option in selected_ward_options]
        
    elif selected_unit == '診療科別':
        available_depts = sorted(df['診療科名'].astype(str).unique())
        target_items = st.sidebar.multiselect(
            "対象診療科:", 
            available_depts, 
            default=available_depts[0] if available_depts else None, 
            key="alos_target_depts"
        )

    
    # 移動平均ウィンドウサイズの設定
    # 元のコード（削除）
    # if selected_granularity == '月単位':
    #     moving_avg_window = st.sidebar.slider(
    #         "移動平均期間 (ヶ月)", 
    #         1, 12, 3, 
    #         key="alos_ma_months"
    #     )
    # else:  # 週単位
    #     moving_avg_window = st.sidebar.slider(
    #         "移動平均期間 (週)", 
    #         1, 26, 4, 
    #         key="alos_ma_weeks"
    #     )
    
    # 新しいコード（直近30日用）
    moving_avg_window = st.sidebar.slider(
        "集計期間 (日)", 
        7, 90, 30, 
        key="alos_ma_rolling_days"
    )
    
    # ベンチマーク値設定
    benchmark_alos = None
    if common_config and 'benchmark_alos' in common_config:
        benchmark_alos = common_config['benchmark_alos']
    else:
        benchmark_alos = st.sidebar.number_input(
            "平均在院日数目標値 (日):", 
            min_value=0.0, 
            value=12.0, 
            step=0.5, 
            key="alos_benchmark",
            help="平均在院日数の目標値（ベンチマーク値）を設定します。"
        )
    
    st.sidebar.markdown("</div>", unsafe_allow_html=True)
    
    # メインコンテンツ
    st.markdown("<div class='page-title'>平均在院日数分析</div>", unsafe_allow_html=True)
    
    # データフィルタリングとチェック
    if selected_unit in ['病棟別', '診療科別'] and not target_items:
        st.warning(f"分析対象の{selected_unit.replace('別','')}をサイドバーで選択してください。")
        return
    
    # 主要チャート：平均在院日数と平均在院患者数の推移
    st.markdown("<div class='section-title'>平均在院日数と平均在院患者数の推移（デフォルト30日）</div>", unsafe_allow_html=True)
    st.markdown(f"""
        <div style='font-size: 18px; color: #666; margin-bottom:1rem;'>
            選択期間: {min_date.strftime('%Y年%m月%d日')} ～ {max_date.strftime('%Y年%m月%d日')}
            （{date_range}日間）
        </div>
    """, unsafe_allow_html=True)
    
    # グラフと集計データの取得
    alos_chart, alos_data = create_alos_volume_chart(
        df, 
        selected_granularity, 
        selected_unit, 
        target_items, 
        min_date, 
        max_date, 
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
            df, 
            selected_unit, 
            target_items if selected_unit != '病院全体' else None, 
            min_date, 
            max_date,
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
    
    # グループ化列の指定
    group_by_column = None
    if selected_unit == '病棟別':
        group_by_column = '病棟コード'
    elif selected_unit == '診療科別':
        group_by_column = '診療科名'
    
    # メトリクスの計算
    metrics_df = calculate_alos_metrics(df, min_date, max_date, group_by_column)
    
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