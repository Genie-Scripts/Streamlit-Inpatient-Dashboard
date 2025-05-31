# alos_analysis_tab.py - 統一フィルター対応版
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

from alos_charts import (
    create_alos_volume_chart,
    create_alos_benchmark_chart,
    calculate_alos_metrics
)

from utils import (
    get_ward_display_name,
    get_display_name_for_dept,
    safe_date_filter
)

def display_alos_analysis_tab(df_filtered_by_period, start_date_ts, end_date_ts, common_config=None):
    """
    平均在院日数分析タブの表示（統一フィルター対応版）
    Args:
        df_filtered_by_period (pd.DataFrame): 統一フィルターで既にフィルタリング済みのDataFrame
        start_date_ts (pd.Timestamp): 分析期間の開始日
        end_date_ts (pd.Timestamp): 分析期間の終了日
        common_config (dict, optional): 共通設定
    """
    
    logger.info("平均在院日数分析タブを開始します（統一フィルター対応版）")
    
    if df_filtered_by_period is None or df_filtered_by_period.empty:
        st.warning("🔍 分析対象のデータが空です。統一フィルター条件を確認してください。")
        return

    df_analysis = df_filtered_by_period.copy()
    
    total_days = (end_date_ts - start_date_ts).days + 1
    st.info(f"📅 **分析期間:** {start_date_ts.strftime('%Y年%m月%d日')} ～ {end_date_ts.strftime('%Y年%m月%d日')} （{total_days}日間）")
    
    # 必要列の確認と補完
    required_columns = [
        '日付', '病棟コード', '診療科名',
        '入院患者数（在院）', '入院患者数', '緊急入院患者数',
        '退院患者数', '死亡患者数', '総入院患者数', '総退院患者数'
    ]
    
    missing_columns = [col for col in required_columns if col not in df_analysis.columns]
    
    if missing_columns:
        logger.warning(f"不足している列: {missing_columns}")
        
        # 列名補完ロジック
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
    
    if missing_columns:
        st.error(f"❌ 必要な列が見つかりません: {', '.join(missing_columns)}")
        logger.error(f"必須列が不足: {missing_columns}")
        return

    # =================================================================
    # 🔄 統一フィルター対応：サイドバー設定を簡素化
    # =================================================================
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ 平均在院日数分析 詳細設定")
    st.sidebar.info("💡 期間・診療科・病棟は統一フィルターで設定済みです")
    
    # 分析スコープの選択（統一フィルター範囲内での詳細分析）
    analysis_scope = st.sidebar.radio(
        "🔍 分析スコープ",
        ["統一フィルター範囲", "病棟別詳細", "診療科別詳細"],
        help="統一フィルターで既に選択された範囲での分析スコープを選択"
    )
    
    # 詳細分析用の追加設定
    selected_items = []
    if analysis_scope != "統一フィルター範囲":
        available_items = []
        
        if analysis_scope == "病棟別詳細":
            if '病棟コード' in df_analysis.columns:
                available_items = sorted(df_analysis['病棟コード'].unique())
                ward_mapping = st.session_state.get('ward_mapping', {})
                
                # 表示名付きのオプション作成
                display_options = []
                for ward_code in available_items:
                    ward_name = get_ward_display_name(ward_code, ward_mapping)
                    if ward_name != str(ward_code):
                        display_option = f"{ward_code}（{ward_name}）"
                    else:
                        display_option = str(ward_code)
                    display_options.append(display_option)
                
                selected_displays = st.sidebar.multiselect(
                    "🏨 詳細分析対象病棟",
                    display_options,
                    default=display_options[:min(3, len(display_options))],
                    help="統一フィルター範囲内での詳細分析対象"
                )
                
                # 表示名から実際のコードに変換
                selected_items = []
                for display in selected_displays:
                    for i, option in enumerate(display_options):
                        if option == display:
                            selected_items.append(available_items[i])
                            break
                            
        elif analysis_scope == "診療科別詳細":
            if '診療科名' in df_analysis.columns:
                available_items = sorted(df_analysis['診療科名'].unique())
                
                # 表示名付きのオプション作成
                display_options = []
                for dept_code in available_items:
                    dept_name = get_display_name_for_dept(dept_code, default_name=dept_code)
                    if dept_name != str(dept_code):
                        display_option = f"{dept_code}（{dept_name}）"
                    else:
                        display_option = str(dept_code)
                    display_options.append(display_option)
                
                selected_displays = st.sidebar.multiselect(
                    "🏥 詳細分析対象診療科",
                    display_options,
                    default=display_options[:min(3, len(display_options))],
                    help="統一フィルター範囲内での詳細分析対象"
                )
                
                # 表示名から実際のコードに変換
                selected_items = []
                for display in selected_displays:
                    for i, option in enumerate(display_options):
                        if option == display:
                            selected_items.append(available_items[i])
                            break
    
    # 分析パラメータ設定
    st.sidebar.markdown("#### 📊 分析パラメータ")
    
    moving_avg_window = st.sidebar.slider(
        "移動平均期間 (日)", 
        min_value=7, 
        max_value=90, 
        value=30, 
        step=7,
        key="unified_alos_ma_rolling_days",
        help="トレンド分析用の移動平均計算期間"
    )
    
    benchmark_alos_default = common_config.get('benchmark_alos', 12.0) if common_config else 12.0
    benchmark_alos = st.sidebar.number_input(
        "平均在院日数目標値 (日):", 
        min_value=0.0, 
        max_value=100.0,
        value=benchmark_alos_default, 
        step=0.5, 
        key="unified_alos_benchmark",
        help="ベンチマーク比較用の目標値"
    )
    
    # グラフ設定
    show_confidence_interval = st.sidebar.checkbox(
        "信頼区間を表示", 
        value=False, 
        help="移動平均の信頼区間を表示"
    )

    # =================================================================
    # メインコンテンツ
    # =================================================================
    
    st.markdown("### 📊 平均在院日数と平均在院患者数の推移")
    
    # 分析スコープに応じた設定
    if analysis_scope == "統一フィルター範囲":
        selected_unit = '病院全体'
        target_items = []
        st.info("🏥 **分析対象:** 統一フィルター範囲全体")
    elif analysis_scope == "病棟別詳細":
        selected_unit = '病棟別'
        target_items = selected_items
        if target_items:
            st.info(f"🏨 **分析対象:** {len(target_items)}病棟の詳細分析")
        else:
            st.warning("⚠️ 詳細分析対象の病棟を選択してください。")
            return
    else:  # 診療科別詳細
        selected_unit = '診療科別'
        target_items = selected_items
        if target_items:
            st.info(f"🏥 **分析対象:** {len(target_items)}診療科の詳細分析")
        else:
            st.warning("⚠️ 詳細分析対象の診療科を選択してください。")
            return
    
    # チャート生成
    selected_granularity = '日単位(直近30日)'  # 固定値（統一フィルターで期間管理）
    
    try:
        alos_chart, alos_data = create_alos_volume_chart(
            df_analysis,
            selected_granularity,
            selected_unit,
            target_items,
            start_date_ts,
            end_date_ts,
            moving_avg_window
        )

        if alos_chart and alos_data is not None:
            st.plotly_chart(alos_chart, use_container_width=True)
            
            # データ詳細の表示
            with st.expander("📋 集計データ詳細", expanded=False):
                # 表示名への変換
                display_alos_data = alos_data.copy()
                
                if selected_unit == '病棟別' and '集計単位名' in display_alos_data.columns:
                    ward_map_display = st.session_state.get('ward_mapping', {})
                    display_alos_data['集計単位名'] = display_alos_data['集計単位名'].apply(
                        lambda x: get_ward_display_name(x, ward_map_display)
                    )
                elif selected_unit == '診療科別' and '集計単位名' in display_alos_data.columns:
                    display_alos_data['集計単位名'] = display_alos_data['集計単位名'].apply(
                        lambda x: get_display_name_for_dept(x, default_name=x)
                    )
                
                # 表示カラムとフォーマット
                ma_suffix = f"直近{moving_avg_window}日"
                ma_col_name = f'平均在院日数 ({ma_suffix})'
                
                display_cols = [
                    '集計期間', '集計単位名', ma_col_name, 
                    '日平均在院患者数', '平均在院日数_実測', 
                    '延べ在院患者数', '総入院患者数', '総退院患者数', '実日数'
                ]
                existing_cols = [col for col in display_cols if col in display_alos_data.columns]
                
                format_dict = {
                    '日平均在院患者数': "{:.1f}", 
                    '平均在院日数_実測': "{:.2f}",
                    '延べ在院患者数': "{:.0f}", 
                    '総入院患者数': "{:.0f}", 
                    '総退院患者数': "{:.0f}",
                    '実日数': "{:.0f}"
                }
                if ma_col_name in display_alos_data.columns:
                    format_dict[ma_col_name] = "{:.2f}"
                
                st.dataframe(
                    display_alos_data[existing_cols].style.format(format_dict), 
                    height=400
                )
                
                # CSVダウンロード
                csv_data = display_alos_data[existing_cols].to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📊 詳細データをCSVダウンロード",
                    data=csv_data,
                    file_name=f"平均在院日数推移_{selected_unit}_{start_date_ts.strftime('%Y%m%d')}_{end_date_ts.strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
        else:
            st.warning("📊 グラフを作成するためのデータが不足しています。")
            logger.warning("ALOS チャート生成に失敗")
            
    except Exception as e:
        st.error(f"❌ 平均在院日数チャート生成中にエラーが発生しました: {e}")
        logger.error(f"ALOS チャート生成エラー: {e}")

    # ベンチマーク比較
    if benchmark_alos and benchmark_alos > 0:
        st.markdown("### 🎯 平均在院日数ベンチマーク比較")
        
        try:
            benchmark_chart = create_alos_benchmark_chart(
                df_analysis,
                selected_unit,
                target_items if selected_unit != '病院全体' else None,
                start_date_ts,
                end_date_ts,
                benchmark_alos
            )
            
            if benchmark_chart:
                st.plotly_chart(benchmark_chart, use_container_width=True)
                
                # ベンチマーク達成状況
                current_alos = None
                if alos_data is not None and not alos_data.empty and '平均在院日数_実測' in alos_data.columns:
                    current_alos = alos_data['平均在院日数_実測'].mean()
                    
                    if current_alos:
                        diff_from_benchmark = current_alos - benchmark_alos
                        diff_percent = (diff_from_benchmark / benchmark_alos) * 100
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("📊 現在の平均在院日数", f"{current_alos:.2f}日")
                        with col2:
                            st.metric("🎯 目標値", f"{benchmark_alos:.2f}日")
                        with col3:
                            st.metric(
                                "📈 差異", 
                                f"{diff_from_benchmark:+.2f}日",
                                f"{diff_percent:+.1f}%"
                            )
                        
                        if diff_from_benchmark <= 0:
                            st.success(f"✅ 目標値を{abs(diff_percent):.1f}%下回っており、良好な状況です。")
                        elif diff_percent <= 10:
                            st.info(f"ℹ️ 目標値を{diff_percent:.1f}%上回っていますが、許容範囲内です。")
                        else:
                            st.warning(f"⚠️ 目標値を{diff_percent:.1f}%上回っており、改善の余地があります。")
            else:
                st.info("ℹ️ ベンチマーク比較チャートを作成するためのデータが不足しています。")
                
        except Exception as e:
            st.error(f"❌ ベンチマーク比較チャート生成中にエラーが発生しました: {e}")
            logger.error(f"ベンチマークチャート生成エラー: {e}")

    # 詳細メトリクス
    st.markdown("### 📈 詳細メトリクス")
    
    try:
        group_by_column_metrics = None
        if selected_unit == '病棟別':
            group_by_column_metrics = '病棟コード'
        elif selected_unit == '診療科別':
            group_by_column_metrics = '診療科名'

        metrics_df = calculate_alos_metrics(
            df_analysis,
            start_date_ts,
            end_date_ts,
            group_by_column_metrics
        )

        if not metrics_df.empty:
            # 詳細分析対象でフィルタリング
            if selected_unit != '病院全体' and target_items:
                metrics_df_filtered = metrics_df[
                    metrics_df['集計単位'].astype(str).isin([str(item) for item in target_items])
                ]
            else:
                metrics_df_filtered = metrics_df
            
            display_metrics_df = metrics_df_filtered.copy()
            
            # 表示名変換
            if group_by_column_metrics == '病棟コード' and '集計単位' in display_metrics_df.columns:
                ward_map_metrics = st.session_state.get('ward_mapping', {})
                display_metrics_df['集計単位'] = display_metrics_df['集計単位'].apply(
                    lambda x: get_ward_display_name(x, ward_map_metrics)
                )
            elif group_by_column_metrics == '診療科名' and '集計単位' in display_metrics_df.columns:
                display_metrics_df['集計単位'] = display_metrics_df['集計単位'].apply(
                    lambda x: get_display_name_for_dept(x, default_name=x)
                )

            if not display_metrics_df.empty:
                # メトリクス表示用フォーマット
                format_dict_metrics = {
                    '平均在院日数': "{:.2f}", 
                    '日平均在院患者数': "{:.1f}", 
                    '病床回転率': "{:.2f}", 
                    '延べ在院患者数': "{:.0f}", 
                    '総入院患者数': "{:.0f}", 
                    '総退院患者数': "{:.0f}", 
                    '緊急入院率': "{:.1f}%", 
                    '死亡率': "{:.1f}%"
                }
                
                # 追加メトリクスのフォーマット
                for col in display_metrics_df.columns:
                    if col.endswith('割合') and col not in format_dict_metrics:
                        format_dict_metrics[col] = "{:.1f}%"
                
                st.dataframe(
                    display_metrics_df.style.format(format_dict_metrics), 
                    height=min(len(display_metrics_df) * 35 + 40, 500)
                )

                # CSV ダウンロード
                csv_data = display_metrics_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📊 メトリクスをCSVダウンロード",
                    data=csv_data,
                    file_name=f"平均在院日数メトリクス_{selected_unit}_{start_date_ts.strftime('%Y%m%d')}_{end_date_ts.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    help="詳細メトリクスをCSVファイルとしてダウンロードします。"
                )
                
                # 重要指標のハイライト
                if len(display_metrics_df) > 1:
                    st.markdown("#### 🔍 重要指標ハイライト")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if '平均在院日数' in display_metrics_df.columns:
                            max_alos_idx = display_metrics_df['平均在院日数'].idxmax()
                            min_alos_idx = display_metrics_df['平均在院日数'].idxmin()
                            
                            max_unit = display_metrics_df.loc[max_alos_idx, '集計単位']
                            min_unit = display_metrics_df.loc[min_alos_idx, '集計単位']
                            max_alos = display_metrics_df.loc[max_alos_idx, '平均在院日数']
                            min_alos = display_metrics_df.loc[min_alos_idx, '平均在院日数']
                            
                            st.success(f"⭐ **最短在院日数:** {min_unit} ({min_alos:.2f}日)")
                            st.warning(f"⚠️ **最長在院日数:** {max_unit} ({max_alos:.2f}日)")
                    
                    with col2:
                        if '病床回転率' in display_metrics_df.columns:
                            max_turn_idx = display_metrics_df['病床回転率'].idxmax()
                            min_turn_idx = display_metrics_df['病床回転率'].idxmin()
                            
                            max_turn_unit = display_metrics_df.loc[max_turn_idx, '集計単位']
                            min_turn_unit = display_metrics_df.loc[min_turn_idx, '集計単位']
                            max_turn = display_metrics_df.loc[max_turn_idx, '病床回転率']
                            min_turn = display_metrics_df.loc[min_turn_idx, '病床回転率']
                            
                            st.success(f"🔄 **最高回転率:** {max_turn_unit} ({max_turn:.2f})")
                            st.info(f"🔄 **最低回転率:** {min_turn_unit} ({min_turn:.2f})")
                            
            else:
                st.info("ℹ️ 選択された項目のメトリクスデータがありません。")
        else:
            st.warning("📊 メトリクスを計算するためのデータが不足しています。")
            
    except Exception as e:
        st.error(f"❌ メトリクス計算中にエラーが発生しました: {e}")
        logger.error(f"メトリクス計算エラー: {e}")

    # 分析インサイトと推奨アクション
    if not metrics_df.empty:
        st.markdown("### 💡 分析インサイトと推奨アクション")
        
        try:
            # 現在の平均在院日数の取得
            if selected_unit == '病院全体':
                current_alos_for_insight = metrics_df['平均在院日数'].iloc[0] if len(metrics_df) > 0 else None
            else:
                if target_items:
                    metrics_df_for_insight = metrics_df[
                        metrics_df['集計単位'].astype(str).isin([str(item) for item in target_items])
                    ]
                    current_alos_for_insight = metrics_df_for_insight['平均在院日数'].mean() if not metrics_df_for_insight.empty else None
                else:
                    current_alos_for_insight = metrics_df['平均在院日数'].mean() if not metrics_df.empty else None

            if current_alos_for_insight is not None and benchmark_alos > 0:
                # ベンチマーク比較インサイト
                diff_percent = ((current_alos_for_insight - benchmark_alos) / benchmark_alos * 100)
                
                insights_col, actions_col = st.columns(2)
                
                with insights_col:
                    st.markdown("#### 📊 分析インサイト")
                    
                    if current_alos_for_insight < benchmark_alos:
                        st.success(f"✅ 現在の平均在院日数（{current_alos_for_insight:.2f}日）は目標値より {abs(diff_percent):.1f}% 短く、良好な水準です。")
                        
                        if diff_percent < -20:
                            st.info("💡 目標値を大幅に下回っています。この水準を維持しつつ、患者ケアの質も確保できているか確認しましょう。")
                    
                    elif current_alos_for_insight < benchmark_alos * 1.1:
                        st.info(f"ℹ️ 現在の平均在院日数は目標値に近い水準ですが、{diff_percent:.1f}% 超過しています。")
                        st.write("軽微な改善で目標達成が可能な範囲です。")
                    
                    else:
                        st.warning(f"⚠️ 現在の平均在院日数は目標値を {diff_percent:.1f}% 上回っており、短縮の余地があります。")
                        
                        if diff_percent > 50:
                            st.error("🚨 目標値を大幅に超過しています。緊急的な改善策の検討が必要です。")
                
                with actions_col:
                    st.markdown("#### 🎯 推奨アクション")
                    
                    if current_alos_for_insight < benchmark_alos:
                        st.write("- ✅ 現在の退院支援プロセスを標準化・文書化")
                        st.write("- 📋 ベストプラクティスの他部門への展開")
                        st.write("- 🔍 患者満足度調査の実施")
                        
                    elif current_alos_for_insight < benchmark_alos * 1.1:
                        st.write("- 📊 クリニカルパスの遵守状況確認")
                        st.write("- 🤝 退院調整の最適化")
                        st.write("- 📈 定期的なモニタリング強化")
                        
                    else:
                        st.write("- 🔍 長期入院患者のケースレビュー実施")
                        st.write("- 🚫 退院阻害要因の特定と改善")
                        st.write("- 👥 多職種チームでの退院支援強化")
                        st.write("- 📋 クリニカルパスの見直し")

            # 追加のインサイト生成
            if not metrics_df.empty:
                metrics_df_for_additional = metrics_df
                if selected_unit != '病院全体' and target_items:
                    metrics_df_for_additional = metrics_df[
                        metrics_df['集計単位'].astype(str).isin([str(item) for item in target_items])
                    ]
                
                # 病床回転率のインサイト
                if '病床回転率' in metrics_df_for_additional.columns:
                    avg_turnover = metrics_df_for_additional['病床回転率'].mean()
                    
                    if avg_turnover < 0.7:
                        st.info(f"🔄 **病床回転率:** {avg_turnover:.2f}回転と低めです。収益性に影響を与える可能性があります。")
                        st.write("💡 **改善提案:** 入退院プロセスの効率化と、不必要な入院日数の削減を検討してください。")
                        
                    elif avg_turnover > 1.2:
                        st.success(f"🔄 **病床回転率:** {avg_turnover:.2f}回転と高く、効率的な病床運用ができています。")
                        st.write("⚠️ **注意点:** 高い回転率が患者ケアの質に影響していないか確認しつつ、この効率を維持してください。")

                # 緊急入院率のインサイト
                if '緊急入院率' in metrics_df_for_additional.columns:
                    avg_emergency_rate = metrics_df_for_additional['緊急入院率'].mean()
                    
                    if avg_emergency_rate > 30:
                        st.warning(f"🚨 **緊急入院率:** {avg_emergency_rate:.1f}% と高く、計画的な入院管理が難しい状況です。")
                        st.write("💡 **改善提案:** 緊急入院の理由を分析し、予防可能な再入院の減少策を検討してください。")
                    elif avg_emergency_rate < 10:
                        st.success(f"✅ **緊急入院率:** {avg_emergency_rate:.1f}% と低く、計画的な入院管理ができています。")

        except Exception as e:
            st.error(f"❌ インサイト生成中にエラーが発生しました: {e}")
            logger.error(f"インサイト生成エラー: {e}")
    
    logger.info("平均在院日数分析タブの処理が完了しました")