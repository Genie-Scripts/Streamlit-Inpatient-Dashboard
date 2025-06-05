# alos_analysis_tab.py (修正版 - 統一フィルター専用)
import streamlit as st
import pandas as pd
import numpy as np
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
)

def display_alos_analysis_tab(df_filtered_by_period, start_date_ts, end_date_ts, common_config=None):
    """
    平均在院日数分析タブの表示（統一フィルター専用版）
    Args:
        df_filtered_by_period (pd.DataFrame): 統一フィルターで既にフィルタリング済みのDataFrame
        start_date_ts (pd.Timestamp): 分析期間の開始日
        end_date_ts (pd.Timestamp): 分析期間の終了日
        common_config (dict, optional): 共通設定
    """
    logger.info("平均在院日数分析タブを開始します（統一フィルター専用版）")

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

    if missing_columns:
        st.error(f"❌ 必要な列が見つかりません: {', '.join(missing_columns)}")
        logger.error(f"必須列が不足: {missing_columns}")
        return

    # =================================================================
    # ⚙️ 平均在院日数分析 詳細設定 (統一フィルター専用)
    # =================================================================
    with st.expander("⚙️ 表示・分析パラメータ調整", expanded=True):
        col_params1, col_params2 = st.columns(2)

        with col_params1:
            st.markdown("##### 📊 分析パラメータ")
            moving_avg_window = st.slider(
                "移動平均期間 (日)",
                min_value=7, max_value=90, value=30, step=7,
                key="alos_tab_ma_rolling_days",
                help="トレンド分析用の移動平均計算期間"
            )

        with col_params2:
            benchmark_alos_default = common_config.get('benchmark_alos', 12.0) if common_config else 12.0
            benchmark_alos = st.number_input(
                "平均在院日数目標値 (日):",
                min_value=0.0, max_value=100.0, value=benchmark_alos_default, step=0.5,
                key="alos_tab_benchmark_alos",
                help="ベンチマーク比較用の目標値"
            )

    # =================================================================
    # メインコンテンツ - 統一フィルター範囲全体の分析
    # =================================================================
    st.markdown("### 📊 平均在院日数と平均在院患者数の推移")
    
    # 統一フィルター範囲全体での分析
    selected_unit_for_charts = '病院全体'
    target_items_for_charts = []
    st.success("🏥 **分析対象:** 統一フィルター範囲全体")

    try:
        alos_chart, alos_data = create_alos_volume_chart(
            df_analysis,
            selected_granularity='日単位',
            selected_unit=selected_unit_for_charts,
            target_items=target_items_for_charts,
            start_date=start_date_ts,
            end_date=end_date_ts,
            moving_avg_window=moving_avg_window
        )

        if alos_chart and alos_data is not None and not alos_data.empty:
            st.plotly_chart(alos_chart, use_container_width=True)

            with st.expander("📋 集計データ詳細", expanded=False):
                display_alos_data = alos_data.copy()

                # 移動平均列名を動的に取得
                ma_col_name_actual = None
                for col in display_alos_data.columns:
                    if '平均在院日数 (' in col and '移動平均)' in col or '直近' in col:
                        ma_col_name_actual = col
                        break
                if ma_col_name_actual is None and f'平均在院日数 ({moving_avg_window}日移動平均)' in display_alos_data.columns:
                     ma_col_name_actual = f'平均在院日数 ({moving_avg_window}日移動平均)'
                elif ma_col_name_actual is None and '平均在院日数_実測' in display_alos_data.columns:
                    ma_col_name_actual = '平均在院日数_実測'

                display_cols = ['集計期間']
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
                    file_name=f"平均在院日数推移_統一フィルター範囲_{start_date_ts.strftime('%Y%m%d')}_{end_date_ts.strftime('%Y%m%d')}.csv",
                    mime="text/csv", key="alos_tab_csv_download"
                )
        elif alos_data is not None and alos_data.empty:
            st.info("集計対象のデータがありませんでした。")
        else:
            st.warning("📊 グラフを作成するためのデータが不足しているか、計算できませんでした。")
            logger.warning("ALOS チャート生成に失敗 (alos_chart or alos_data is None)")

    except Exception as e:
        st.error(f"❌ 平均在院日数チャート生成中にエラーが発生しました: {e}")
        logger.error(f"ALOS チャート生成エラー: {e}", exc_info=True)

    # ベンチマーク比較
    if benchmark_alos and benchmark_alos > 0:
        st.markdown("### 🎯 平均在院日数ベンチマーク比較")
        try:
            benchmark_chart = create_alos_benchmark_chart(
                df_analysis,
                selected_unit_for_charts,
                None,  # target_items は None（全体分析のため）
                start_date_ts,
                end_date_ts,
                benchmark_alos
            )
            if benchmark_chart:
                st.plotly_chart(benchmark_chart, use_container_width=True)
                
                current_alos_for_metric = None
                if alos_data is not None and not alos_data.empty and '平均在院日数_実測' in alos_data.columns:
                    current_alos_for_metric = alos_data['平均在院日数_実測'].mean()

                    if pd.notna(current_alos_for_metric):
                        diff_from_benchmark = current_alos_for_metric - benchmark_alos
                        diff_percent = (diff_from_benchmark / benchmark_alos) * 100 if benchmark_alos > 0 else 0
                        
                        bm_col1, bm_col2, bm_col3 = st.columns(3)
                        with bm_col1:
                            st.metric("統一フィルター範囲の平均在院日数", f"{current_alos_for_metric:.2f}日")
                        with bm_col2:
                            st.metric("目標値", f"{benchmark_alos:.2f}日")
                        with bm_col3:
                            st.metric("差異", f"{diff_from_benchmark:+.2f}日", f"{diff_percent:+.1f}%")
                        
                        if diff_from_benchmark <= 0: 
                            st.success(f"✅ 目標値を{abs(diff_percent):.1f}%下回っており、良好な状況です。")
                        elif diff_percent <= 10: 
                            st.info(f"ℹ️ 目標値を{diff_percent:.1f}%上回っていますが、許容範囲内です。")
                        else: 
                            st.warning(f"⚠️ 目標値を{diff_percent:.1f}%上回っており、改善の余地があります。")
                    else:
                        st.info("統一フィルター範囲の平均在院日数を計算できませんでした（データ不足の可能性）。")
            else:
                st.info("ℹ️ ベンチマーク比較チャートを作成するためのデータが不足しています。")
        except Exception as e:
            st.error(f"❌ ベンチマーク比較チャート生成中にエラーが発生しました: {e}")
            logger.error(f"ベンチマークチャート生成エラー: {e}", exc_info=True)

    # 詳細メトリクス
    st.markdown("### 📈 詳細メトリクス")
    try:
        # 統一フィルター範囲全体でのメトリクス計算
        metrics_df = calculate_alos_metrics(
            df_analysis, start_date_ts, end_date_ts, None  # group_by_column=None（全体集計）
        )
        if not metrics_df.empty:
            format_dict_metrics = {
                '平均在院日数': "{:.2f}", '日平均在院患者数': "{:.1f}", '病床回転率': "{:.2f}",
                '延べ在院患者数': "{:.0f}", '総入院患者数': "{:.0f}", '総退院患者数': "{:.0f}",
                '緊急入院率': "{:.1f}%", '死亡率': "{:.1f}%"
            }
            for col in metrics_df.columns:
                if col.endswith('割合') and col not in format_dict_metrics: 
                    format_dict_metrics[col] = "{:.1f}%"
            
            st.dataframe(
                metrics_df.style.format(format_dict_metrics, na_rep="-"),
                height=min(len(metrics_df) * 35 + 40, 500), use_container_width=True
            )
            
            csv_data_metrics = metrics_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📊 メトリクスをCSVダウンロード", data=csv_data_metrics,
                file_name=f"平均在院日数メトリクス_統一フィルター範囲_{start_date_ts.strftime('%Y%m%d')}_{end_date_ts.strftime('%Y%m%d')}.csv",
                mime="text/csv", key="alos_tab_metrics_csv_download"
            )
        else:
            st.warning("📊 メトリクスを計算するためのデータが不足しています。")
    except Exception as e:
        st.error(f"❌ メトリクス計算中にエラーが発生しました: {e}")
        logger.error(f"メトリクス計算エラー: {e}", exc_info=True)

    # 分析インサイトと推奨アクション
    if not metrics_df.empty:
        st.markdown("### 💡 分析インサイトと推奨アクション")
        try:
            current_alos_for_insight = metrics_df['平均在院日数'].iloc[0] if len(metrics_df) > 0 else None

            if pd.notna(current_alos_for_insight) and benchmark_alos > 0:
                diff_percent_insight = ((current_alos_for_insight - benchmark_alos) / benchmark_alos * 100)
                insights_col, actions_col = st.columns(2)
                
                with insights_col:
                    st.markdown("#### 📊 分析インサイト")
                    if current_alos_for_insight < benchmark_alos: 
                        st.success(f"✅ 現在の平均在院日数（{current_alos_for_insight:.2f}日）は目標値より {abs(diff_percent_insight):.1f}% 短く、良好です。")
                    elif current_alos_for_insight < benchmark_alos * 1.1: 
                        st.info(f"ℹ️ 平均在院日数は目標に近いですが、{diff_percent_insight:.1f}% 超過しています。")
                    else: 
                        st.warning(f"⚠️ 平均在院日数は目標を {diff_percent_insight:.1f}% 上回っており、短縮の余地があります。")
                
                with actions_col:
                    st.markdown("#### 🎯 推奨アクション")
                    if current_alos_for_insight < benchmark_alos: 
                        st.write("- ✅ 現状プロセスの標準化・維持")
                    elif current_alos_for_insight < benchmark_alos * 1.1: 
                        st.write("- 📊 クリニカルパス遵守確認")
                    else: 
                        st.write("- 🔍 長期入院患者レビュー実施")

            if '病床回転率' in metrics_df.columns:
                avg_turnover_insight = metrics_df['病床回転率'].iloc[0] if len(metrics_df) > 0 else 0
                if 0 < avg_turnover_insight < 0.7: 
                    st.info(f"🔄 **病床回転率:** {avg_turnover_insight:.2f}回転と低めです。")
                elif avg_turnover_insight > 1.2: 
                    st.success(f"🔄 **病床回転率:** {avg_turnover_insight:.2f}回転と高く、効率的です。")
            
            if '緊急入院率' in metrics_df.columns:
                avg_emergency_rate_insight = metrics_df['緊急入院率'].iloc[0] if len(metrics_df) > 0 else 0
                if avg_emergency_rate_insight > 30: 
                    st.warning(f"🚨 **緊急入院率:** {avg_emergency_rate_insight:.1f}% と高いです。")
                elif 0 < avg_emergency_rate_insight < 10: 
                    st.success(f"✅ **緊急入院率:** {avg_emergency_rate_insight:.1f}% と低く、計画的です。")

        except Exception as e:
            st.error(f"❌ インサイト生成中にエラーが発生しました: {e}")
            logger.error(f"インサイト生成エラー: {e}", exc_info=True)

    logger.info("平均在院日数分析タブの処理が完了しました")