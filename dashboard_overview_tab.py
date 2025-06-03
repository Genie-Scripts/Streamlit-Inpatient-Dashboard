# dashboard_overview_tab.py (目標値達成率表示版)

import streamlit as st
import pandas as pd
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# dashboard_charts.py からのインポートは維持
try:
    from dashboard_charts import (
        create_monthly_trend_chart,
        create_admissions_discharges_chart,
        create_occupancy_chart
    )
except ImportError:
    st.error("dashboard_charts.py が見つからないか、必要な関数が定義されていません。")
    create_monthly_trend_chart = None
    create_admissions_discharges_chart = None
    create_occupancy_chart = None

# kpi_calculator.py からのインポートは維持
try:
    from kpi_calculator import calculate_kpis, analyze_kpi_insights, get_kpi_status
except ImportError:
    st.error("kpi_calculator.py が見つからないか、必要な関数が定義されていません。")
    calculate_kpis = None
    analyze_kpi_insights = None
    get_kpi_status = None

# unified_filters.py からのインポート
try:
    from unified_filters import apply_unified_filters, get_unified_filter_config
except ImportError:
    st.error("unified_filters.py が見つからないか、必要な関数が定義されていません。")
    apply_unified_filters = None
    get_unified_filter_config = None

# config.py から定数をインポート
from config import (
    DEFAULT_OCCUPANCY_RATE,
    DEFAULT_ADMISSION_FEE,
    DEFAULT_TARGET_PATIENT_DAYS,
    APP_VERSION,
    NUMBER_FORMAT,
    DEFAULT_TOTAL_BEDS,
    DEFAULT_AVG_LENGTH_OF_STAY,
    DEFAULT_TARGET_ADMISSIONS
)

def format_number_with_config(value, unit="", format_type="default"):
    if pd.isna(value) or value is None:
        return f"0{unit}" if unit else "0"
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return str(value)
    if value == 0:
        return f"0{unit}" if unit else "0"

    if format_type == "currency":
        return f"{value:,.0f}{NUMBER_FORMAT['currency_symbol']}"
    elif format_type == "percentage":
        return f"{value:.1f}{NUMBER_FORMAT['percentage_symbol']}"
    else:
        return f"{value:,.1f}{unit}" if isinstance(value, float) else f"{value:,.0f}{unit}"

def load_target_values_csv():
    """
    目標値CSVファイル読み込み機能
    
    Returns:
        pd.DataFrame: 目標値データフレーム
    """
    if 'target_values_df' not in st.session_state:
        st.session_state.target_values_df = pd.DataFrame()
    
    with st.sidebar.expander("🎯 目標値設定", expanded=False):
        st.markdown("##### 目標値CSVファイル読み込み")
        
        # CSVファイルアップロード
        uploaded_target_file = st.file_uploader(
            "目標値CSVファイルを選択",
            type=['csv'],
            key="target_values_upload",
            help="部門コード、目標値、区分が含まれるCSVファイルをアップロード"
        )
        
        if uploaded_target_file is not None:
            try:
                target_df = pd.read_csv(uploaded_target_file, encoding='utf-8-sig')
                
                # 必要な列の確認
                required_columns = ['部門コード', '目標値', '区分']
                missing_columns = [col for col in required_columns if col not in target_df.columns]
                
                if missing_columns:
                    st.error(f"❌ 必要な列が見つかりません: {', '.join(missing_columns)}")
                    st.info("必要な列: 部門コード, 目標値, 区分")
                else:
                    st.session_state.target_values_df = target_df
                    st.success(f"✅ 目標値データを読み込みました（{len(target_df)}行）")
                    
                    # データプレビュー
                    with st.expander("📋 目標値データプレビュー", expanded=False):
                        st.dataframe(target_df.head(10), use_container_width=True)
                        
            except Exception as e:
                st.error(f"❌ CSVファイル読み込みエラー: {e}")
                logger.error(f"目標値CSVファイル読み込みエラー: {e}", exc_info=True)
        
        # 現在の読み込み状況表示
        if not st.session_state.target_values_df.empty:
            st.info(f"📊 現在の目標値データ: {len(st.session_state.target_values_df)}行")
            
            # クリアボタン
            if st.button("🗑️ 目標値データクリア", key="clear_target_values"):
                st.session_state.target_values_df = pd.DataFrame()
                st.success("目標値データをクリアしました")
                st.rerun()
        else:
            st.info("目標値データが設定されていません")
    
    return st.session_state.target_values_df

def get_target_value_for_filter(target_df, filter_config, metric_type="日平均在院患者数"):
    """
    フィルター設定に基づいて目標値を取得
    
    Args:
        target_df (pd.DataFrame): 目標値データフレーム
        filter_config (dict): フィルター設定
        metric_type (str): メトリクス種別
        
    Returns:
        tuple: (目標値, 部門名, 達成対象期間)
    """
    if target_df.empty or not filter_config:
        return None, None, None
    
    try:
        filter_mode = filter_config.get('filter_mode', '全体')
        
        if filter_mode == "特定診療科":
            selected_depts = filter_config.get('selected_depts', [])
            if selected_depts:
                # 複数診療科選択時は合計目標値を計算
                total_target = 0
                matched_depts = []
                
                for dept in selected_depts:
                    dept_targets = target_df[
                        (target_df['部門コード'] == dept) & 
                        (target_df['区分'] == '全日')  # とりあえず全日で
                    ]
                    if not dept_targets.empty:
                        total_target += dept_targets['目標値'].iloc[0]
                        matched_depts.append(dept)
                
                if matched_depts:
                    dept_names = ', '.join(matched_depts)
                    return total_target, f"診療科: {dept_names}", "全日"
        
        elif filter_mode == "特定病棟":
            selected_wards = filter_config.get('selected_wards', [])
            if selected_wards:
                # 複数病棟選択時は合計目標値を計算
                total_target = 0
                matched_wards = []
                
                for ward in selected_wards:
                    ward_targets = target_df[
                        (target_df['部門コード'] == ward) & 
                        (target_df['区分'] == '全日')  # とりあえず全日で
                    ]
                    if not ward_targets.empty:
                        total_target += ward_targets['目標値'].iloc[0]
                        matched_wards.append(ward)
                
                if matched_wards:
                    ward_names = ', '.join(matched_wards)
                    return total_target, f"病棟: {ward_names}", "全日"
        
        return None, None, None
        
    except Exception as e:
        logger.error(f"目標値取得エラー: {e}", exc_info=True)
        return None, None, None

def calculate_previous_year_same_period(df_original, current_end_date, current_filter_config):
    """
    昨年度同期間のデータを計算（統一フィルター適用）
    
    Args:
        df_original (pd.DataFrame): 元のデータフレーム
        current_end_date (pd.Timestamp): 現在の直近データ日付
        current_filter_config (dict): 現在のフィルター設定
        
    Returns:
        tuple: (昨年度同期間データ, 開始日, 終了日, 期間説明文)
    """
    try:
        if df_original is None or df_original.empty:
            return pd.DataFrame(), None, None, "データなし"
        
        # 現在の年度を判定
        if current_end_date.month >= 4:
            current_fiscal_year = current_end_date.year
        else:
            current_fiscal_year = current_end_date.year - 1
        
        # 昨年度の開始日（昨年度4月1日）
        prev_fiscal_start = pd.Timestamp(year=current_fiscal_year - 1, month=4, day=1)
        
        # 昨年度の終了日（昨年度の同月日）
        try:
            prev_fiscal_end = pd.Timestamp(
                year=current_end_date.year - 1, 
                month=current_end_date.month, 
                day=current_end_date.day
            )
        except ValueError:
            # 2月29日などの特殊ケース対応
            prev_fiscal_end = pd.Timestamp(
                year=current_end_date.year - 1, 
                month=current_end_date.month, 
                day=28
            )
        
        # 昨年度同期間のデータをフィルタリング
        if '日付' in df_original.columns:
            df_original['日付'] = pd.to_datetime(df_original['日付'])
            prev_year_data = df_original[
                (df_original['日付'] >= prev_fiscal_start) & 
                (df_original['日付'] <= prev_fiscal_end)
            ].copy()
        else:
            prev_year_data = pd.DataFrame()
        
        # 統一フィルターの部門設定を昨年度データに適用
        if apply_unified_filters and current_filter_config and not prev_year_data.empty:
            filter_mode = current_filter_config.get('filter_mode', '全体')
            
            if filter_mode == "特定診療科" and current_filter_config.get('selected_depts'):
                if '診療科名' in prev_year_data.columns:
                    prev_year_data = prev_year_data[
                        prev_year_data['診療科名'].isin(current_filter_config['selected_depts'])
                    ]
            
            elif filter_mode == "特定病棟" and current_filter_config.get('selected_wards'):
                if '病棟コード' in prev_year_data.columns:
                    prev_year_data = prev_year_data[
                        prev_year_data['病棟コード'].isin(current_filter_config['selected_wards'])
                    ]
        
        # 期間説明文
        period_days = (prev_fiscal_end - prev_fiscal_start).days + 1
        period_description = f"{prev_fiscal_start.strftime('%Y年%m月%d日')} ～ {prev_fiscal_end.strftime('%Y年%m月%d日')} ({period_days}日間)"
        
        logger.info(f"昨年度同期間データ抽出完了: {len(prev_year_data)}行, 期間: {period_description}")
        
        return prev_year_data, prev_fiscal_start, prev_fiscal_end, period_description
        
    except Exception as e:
        logger.error(f"昨年度同期間データ計算エラー: {e}", exc_info=True)
        return pd.DataFrame(), None, None, "計算エラー"

def display_unified_metrics_layout_colorized(metrics, selected_period_info, prev_year_metrics=None, prev_year_period_info=None, target_info=None):
    if not metrics:
        st.warning("表示するメトリクスデータがありません。")
        return

    # 設定値の取得（デフォルト値でフォールバック）
    total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
    target_occupancy_rate = st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE)
    avg_length_of_stay_target = st.session_state.get('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY)
    target_admissions_monthly = st.session_state.get('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS)
    avg_admission_fee_val = st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE)

    st.info(f"📊 分析期間: {selected_period_info}")
    st.caption("※期間はサイドバーの「分析フィルター」で変更できます。")

    # 目標値情報の表示
    if target_info and target_info[0] is not None:
        target_value, target_dept_name, target_period = target_info
        st.success(f"🎯 目標値設定: {target_dept_name} - {target_value:.1f}人/日 ({target_period})")

    # 主要指標を4つ横一列で表示
    st.markdown("### 📊 主要指標")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # 日平均在院患者数（目標値対応）
        avg_daily_census_val = metrics.get('avg_daily_census', 0)
        
        # 目標値がある場合は目標値を使用、ない場合は従来の計算
        if target_info and target_info[0] is not None:
            target_census = target_info[0]
            census_delta = avg_daily_census_val - target_census
            census_color = "normal" if census_delta >= 0 else "inverse"
            delta_label = "目標比"
        else:
            target_census = total_beds * target_occupancy_rate
            census_delta = avg_daily_census_val - target_census
            census_color = "normal" if census_delta >= 0 else "inverse"
            delta_label = "理論値比"
        
        st.metric(
            "👥 日平均在院患者数",
            f"{avg_daily_census_val:.1f}人",
            delta=f"{census_delta:+.1f}人 ({delta_label})",
            delta_color=census_color,
            help=f"{selected_period_info}の日平均在院患者数"
        )
        st.caption(f"目標: {target_census:.1f}人")
        if target_info and target_info[0] is not None:
            achievement_rate = (avg_daily_census_val / target_census * 100) if target_census > 0 else 0
            st.caption(f"達成率: {achievement_rate:.1f}%")
        else:
            st.caption(f"総病床数: {total_beds}床")

    with col2:
        # 病床利用率
        bed_occupancy_rate_val = metrics.get('bed_occupancy_rate', 0)
        target_occupancy = target_occupancy_rate * 100
        occupancy_delta = bed_occupancy_rate_val - target_occupancy if bed_occupancy_rate_val is not None else 0
        delta_color = "normal" if abs(occupancy_delta) <= 5 else ("inverse" if occupancy_delta < -5 else "normal")
        
        st.metric(
            "🏥 病床利用率",
            f"{bed_occupancy_rate_val:.1f}%" if bed_occupancy_rate_val is not None else "N/A",
            delta=f"{occupancy_delta:+.1f}% (目標比)",
            delta_color=delta_color,
            help="日平均在院患者数と総病床数から算出"
        )
        st.caption(f"目標: {target_occupancy:.1f}%")
        st.caption("適正範囲: 80-90%")

    with col3:
        # 平均在院日数
        avg_los_val = metrics.get('avg_los', 0)
        alos_delta = avg_los_val - avg_length_of_stay_target
        alos_color = "inverse" if alos_delta > 0 else "normal"  # 短い方が良い
        
        st.metric(
            "📅 平均在院日数",
            f"{avg_los_val:.1f}日",
            delta=f"{alos_delta:+.1f}日 (目標比)",
            delta_color=alos_color,
            help=f"{selected_period_info}の平均在院日数"
        )
        st.caption(f"目標: {avg_length_of_stay_target:.1f}日")
        total_admissions = metrics.get('total_admissions', 0)
        if total_admissions > 0:
            st.caption(f"総入院: {total_admissions:,.0f}人")

    with col4:
        # 日平均新入院患者数
        avg_daily_admissions_val = metrics.get('avg_daily_admissions', 0)
        target_daily_admissions = target_admissions_monthly / 30  # 月目標を日割り
        daily_delta = avg_daily_admissions_val - target_daily_admissions
        daily_color = "normal" if daily_delta >= 0 else "inverse"
        
        st.metric(
            "📈 日平均新入院患者数",
            f"{avg_daily_admissions_val:.1f}人/日",
            delta=f"{daily_delta:+.1f}人/日 (目標比)",
            delta_color=daily_color,
            help=f"{selected_period_info}の日平均新入院患者数"
        )
        st.caption(f"目標: {target_daily_admissions:.1f}人/日")
        period_days_val = metrics.get('period_days', 0)
        if period_days_val > 0:
            total_period_admissions = avg_daily_admissions_val * period_days_val
            st.caption(f"期間計: {total_period_admissions:.0f}人")

    # 昨年度同期間との比較指標
    if prev_year_metrics and prev_year_period_info:
        st.markdown("---")
        st.markdown("### 📊 昨年度同期間比較")
        st.info(f"📊 昨年度同期間: {prev_year_period_info}")
        st.caption("※部門フィルターが適用された昨年度同期間データとの比較")
        
        prev_col1, prev_col2, prev_col3, prev_col4 = st.columns(4)
        
        with prev_col1:
            # 昨年度日平均在院患者数
            prev_avg_daily_census = prev_year_metrics.get('avg_daily_census', 0)
            yoy_census_change = avg_daily_census_val - prev_avg_daily_census
            yoy_census_pct = (yoy_census_change / prev_avg_daily_census * 100) if prev_avg_daily_census > 0 else 0
            yoy_census_color = "normal" if yoy_census_change >= 0 else "inverse"
            
            st.metric(
                "👥 日平均在院患者数",
                f"{prev_avg_daily_census:.1f}人",
                delta=f"{yoy_census_change:+.1f}人 ({yoy_census_pct:+.1f}%)",
                delta_color=yoy_census_color,
                help=f"昨年度同期間の日平均在院患者数との比較"
            )
            
        with prev_col2:
            # 昨年度病床利用率
            prev_bed_occupancy = prev_year_metrics.get('bed_occupancy_rate', 0)
            yoy_occupancy_change = bed_occupancy_rate_val - prev_bed_occupancy
            yoy_occupancy_color = "normal" if yoy_occupancy_change >= 0 else "inverse"
            
            st.metric(
                "🏥 病床利用率",
                f"{prev_bed_occupancy:.1f}%",
                delta=f"{yoy_occupancy_change:+.1f}%",
                delta_color=yoy_occupancy_color,
                help="昨年度同期間の病床利用率との比較"
            )
            
        with prev_col3:
            # 昨年度平均在院日数
            prev_avg_los = prev_year_metrics.get('avg_los', 0)
            yoy_los_change = avg_los_val - prev_avg_los
            yoy_los_color = "inverse" if yoy_los_change > 0 else "normal"  # 短縮が良い
            
            st.metric(
                "📅 平均在院日数",
                f"{prev_avg_los:.1f}日",
                delta=f"{yoy_los_change:+.1f}日",
                delta_color=yoy_los_color,
                help="昨年度同期間の平均在院日数との比較"
            )
            
        with prev_col4:
            # 昨年度日平均新入院患者数
            prev_avg_daily_admissions = prev_year_metrics.get('avg_daily_admissions', 0)
            yoy_admissions_change = avg_daily_admissions_val - prev_avg_daily_admissions
            yoy_admissions_pct = (yoy_admissions_change / prev_avg_daily_admissions * 100) if prev_avg_daily_admissions > 0 else 0
            yoy_admissions_color = "normal" if yoy_admissions_change >= 0 else "inverse"
            
            st.metric(
                "📈 日平均新入院患者数",
                f"{prev_avg_daily_admissions:.1f}人/日",
                delta=f"{yoy_admissions_change:+.1f}人/日 ({yoy_admissions_pct:+.1f}%)",
                delta_color=yoy_admissions_color,
                help="昨年度同期間の日平均新入院患者数との比較"
            )

    # 追加の詳細情報
    st.markdown("---")
    
    # 収益関連指標（必要に応じて表示）
    with st.expander("💰 収益関連指標", expanded=False):
        col_rev1, col_rev2, col_rev3 = st.columns(3)
        
        with col_rev1:
            estimated_revenue_val = metrics.get('estimated_revenue', 0)
            st.metric(
                f"推計収益",
                format_number_with_config(estimated_revenue_val, format_type="currency"),
                delta=f"単価: {avg_admission_fee_val:,}円/日",
                help=f"{selected_period_info}の推計収益"
            )

        with col_rev2:
            total_patient_days_val = metrics.get('total_patient_days', 0)
            monthly_target_days = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS)
            days_in_selected_period = metrics.get('period_days', 1)
            proportional_target_days = (monthly_target_days / 30.44) * days_in_selected_period if days_in_selected_period > 0 else 0
            achievement_days = (total_patient_days_val / proportional_target_days) * 100 if proportional_target_days > 0 else 0
            st.metric(
                f"延べ在院日数",
                format_number_with_config(total_patient_days_val, "人日"),
                delta=f"対期間目標: {achievement_days:.1f}%" if proportional_target_days > 0 else "目標計算不可",
                delta_color="normal" if achievement_days >= 95 else "inverse",
                help=f"{selected_period_info}の延べ在院日数。目標は月間目標を選択期間日数で按分して計算。"
            )

        with col_rev3:
            # 月換算での表示など
            days_in_selected_period = metrics.get('period_days', 1)
            monthly_equivalent_revenue = estimated_revenue_val * (30 / days_in_selected_period) if days_in_selected_period > 0 else 0
            st.metric(
                "月換算推計収益",
                format_number_with_config(monthly_equivalent_revenue, format_type="currency"),
                help="期間の収益を30日換算した推計値"
            )

    # 指標の説明
    with st.expander("📋 指標の説明", expanded=False):
        st.markdown("""
        **👥 日平均在院患者数**: 分析期間中の在院患者数の平均値
        - 病院の日々の患者数規模を示す基本指標
        - 目標値CSVが設定されている場合は部門別目標値と比較
        - 目標値がない場合は病床利用率での理論値と比較
        
        **🏥 病床利用率**: 日平均在院患者数 ÷ 総病床数 × 100
        - 病院の効率性を示す重要指標
        - 一般的に80-90%が適正範囲
        - 稼働率とも呼ばれる
        
        **📅 平均在院日数**: 延べ在院日数 ÷ 新入院患者数
        - 患者の回転効率を示す指標
        - 短いほど効率的だが、医療の質も考慮が必要
        - ALOS (Average Length of Stay) とも呼ばれる
        
        **📈 日平均新入院患者数**: 期間中の新入院患者数 ÷ 分析期間日数
        - 日々の入院受け入れペースを示す指標
        - 稼働計画や人員配置の参考値
        - 病院の活動量を表す重要指標
        
        **昨年度同期間比較**: フィルター適用された昨年度同期間（昨年度4月1日～昨年度の同月日）との比較
        - 季節性を考慮した前年比較が可能
        - 部門フィルターが昨年度データにも適用される
        - 年度の成長・改善状況を把握
        
        **🎯 目標値設定**: CSVファイルで部門別目標値を設定可能
        - 部門コード、目標値、区分（全日/平日/休日）を含むCSVファイル
        - フィルター選択時に該当部門の目標値を自動参照
        - 達成率の自動計算・表示
        """)

    # 詳細データと設定値
    with st.expander("📋 詳細データと設定値", expanded=False):
        detail_col1, detail_col2, detail_col3 = st.columns(3)
        with detail_col1:
            st.markdown("**🏥 基本設定**")
            st.write(f"• 総病床数: {total_beds:,}床")
            st.write(f"• 目標病床利用率: {target_occupancy_rate:.1%}")
            st.write(f"• 平均入院料: {avg_admission_fee_val:,}円/日")
            st.write(f"• 目標平均在院日数: {avg_length_of_stay_target:.1f}日")
        with detail_col2:
            st.markdown("**📅 期間情報**")
            st.write(f"• 計算対象期間: {selected_period_info}")
            st.write(f"• 期間日数: {metrics.get('period_days', 0)}日")
            if prev_year_period_info:
                st.write(f"• 昨年度同期間: {prev_year_period_info}")
            st.write(f"• アプリバージョン: v{APP_VERSION}")
        with detail_col3:
            st.markdown("**🎯 目標値情報**")
            if target_info and target_info[0] is not None:
                st.write(f"• {target_info[1]}")
                st.write(f"• 目標値: {target_info[0]:.1f}人/日")
                st.write(f"• 区分: {target_info[2]}")
            else:
                st.write("• 目標値: 未設定")
                st.write("• デフォルト目標使用中")
            monthly_target_days = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS)
            st.write(f"• 月間目標延べ日数: {format_number_with_config(monthly_target_days, '人日')}")

def display_kpi_cards_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent):
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    if calculate_kpis is None:
        st.error("KPI計算関数が利用できません。")
        return
    
    # 目標値データの読み込み
    target_df = load_target_values_csv()
    
    # 現在期間のKPI計算
    kpis_selected_period = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)
    if kpis_selected_period is None or kpis_selected_period.get("error"):
        st.warning(f"選択された期間のKPI計算に失敗しました。理由: {kpis_selected_period.get('error', '不明') if kpis_selected_period else '不明'}")
        return
    
    # 追加のメトリクス計算
    period_df = df[(df['日付'] >= start_date) & (df['日付'] <= end_date)]
    total_admissions = 0
    if '入院患者数' in period_df.columns:
        total_admissions = period_df['入院患者数'].sum()
    
    metrics_for_display = {
        'avg_daily_census': kpis_selected_period.get('avg_daily_census'),
        'bed_occupancy_rate': kpis_selected_period.get('bed_occupancy_rate'),
        'avg_los': kpis_selected_period.get('alos'),
        'estimated_revenue': kpis_selected_period.get('total_patient_days', 0) * st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE),
        'total_patient_days': kpis_selected_period.get('total_patient_days'),
        'avg_daily_admissions': kpis_selected_period.get('avg_daily_admissions'),
        'period_days': kpis_selected_period.get('days_count'),
        'total_beds': total_beds_setting,
        'total_admissions': total_admissions,
    }
    
    # フィルター設定に基づく目標値取得
    current_filter_config = get_unified_filter_config() if get_unified_filter_config else None
    target_info = get_target_value_for_filter(target_df, current_filter_config) if not target_df.empty else (None, None, None)
    
    # 昨年度同期間データの計算
    df_original = st.session_state.get('df')  # 元のフィルタリング前データ
    
    prev_year_metrics = None
    prev_year_period_info = None
    
    if df_original is not None and not df_original.empty:
        try:
            latest_date_in_current = end_date
            prev_year_data, prev_start, prev_end, prev_period_desc = calculate_previous_year_same_period(
                df_original, latest_date_in_current, current_filter_config
            )
            
            if not prev_year_data.empty and prev_start and prev_end:
                prev_year_kpis = calculate_kpis(prev_year_data, prev_start, prev_end, total_beds=total_beds_setting)
                if prev_year_kpis and not prev_year_kpis.get("error"):
                    # 昨年度の追加メトリクス計算
                    prev_total_admissions = 0
                    if '入院患者数' in prev_year_data.columns:
                        prev_total_admissions = prev_year_data['入院患者数'].sum()
                    
                    prev_year_metrics = {
                        'avg_daily_census': prev_year_kpis.get('avg_daily_census'),
                        'bed_occupancy_rate': prev_year_kpis.get('bed_occupancy_rate'),
                        'avg_los': prev_year_kpis.get('alos'),
                        'avg_daily_admissions': prev_year_kpis.get('avg_daily_admissions'),
                        'total_admissions': prev_total_admissions,
                    }
                    prev_year_period_info = prev_period_desc
                    logger.info(f"昨年度同期間KPI計算完了: {prev_year_period_info}")
                else:
                    logger.warning("昨年度同期間のKPI計算に失敗しました。")
            else:
                logger.info("昨年度同期間のデータが見つかりませんでした。")
        except Exception as e:
            logger.error(f"昨年度同期間データ処理エラー: {e}", exc_info=True)
    
    period_description = f"{start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')}"
    display_unified_metrics_layout_colorized(
        metrics_for_display, 
        period_description, 
        prev_year_metrics, 
        prev_year_period_info,
        target_info
    )

def display_trend_graphs_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent):
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    if calculate_kpis is None: return
    if not all([create_monthly_trend_chart, create_admissions_discharges_chart, create_occupancy_chart]):
        st.warning("グラフ生成関数の一部が利用できません。")
        return
    kpi_data = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)
    if kpi_data is None or kpi_data.get("error"):
        st.warning(f"グラフ表示用のKPIデータ計算に失敗しました。")
        return
    col1_chart, col2_chart = st.columns(2)
    with col1_chart:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        st.markdown("<div class='chart-title'>月別 平均在院日数と入退院患者数の推移</div>", unsafe_allow_html=True)
        monthly_chart = create_monthly_trend_chart(kpi_data)
        if monthly_chart:
            st.plotly_chart(monthly_chart, use_container_width=True)
        else:
            st.info("月次トレンドチャート: データ不足のため表示できません。")
        st.markdown("</div>", unsafe_allow_html=True)
    with col2_chart:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        st.markdown("<div class='chart-title'>週別 入退院バランス</div>", unsafe_allow_html=True)
        balance_chart = create_admissions_discharges_chart(kpi_data)
        if balance_chart:
            st.plotly_chart(balance_chart, use_container_width=True)
        else:
            st.info("入退院バランスチャート: データ不足のため表示できません。")
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='chart-container full-width'>", unsafe_allow_html=True)
    st.markdown(f"<div class='chart-title'>月別 病床利用率の推移 (総病床数: {total_beds_setting}床)</div>", unsafe_allow_html=True)
    occupancy_chart_fig = create_occupancy_chart(kpi_data, total_beds_setting, target_occupancy_setting_percent)
    if occupancy_chart_fig:
        st.plotly_chart(occupancy_chart_fig, use_container_width=True)
    else:
        st.info("病床利用率チャート: データ不足または総病床数未設定のため表示できません。")
    st.markdown("</div>", unsafe_allow_html=True)
    display_insights(kpi_data, total_beds_setting)

def display_insights(kpi_data, total_beds_setting):
    if analyze_kpi_insights and kpi_data:
        insights = analyze_kpi_insights(kpi_data, total_beds_setting)
        st.markdown("<div class='chart-container full-width'>", unsafe_allow_html=True)
        st.markdown("<div class='chart-title'>分析インサイトと考慮事項</div>", unsafe_allow_html=True)
        insight_col1, insight_col2 = st.columns(2)
        with insight_col1:
            if insights.get("alos"):
                st.markdown("<div class='info-card'><h4>平均在院日数 (ALOS) に関する考察</h4>" + "".join([f"<p>- {i}</p>" for i in insights["alos"]]) + "</div>", unsafe_allow_html=True)
            if insights.get("weekday_pattern"):
                st.markdown("<div class='neutral-card'><h4>曜日別パターンの活用</h4>" + "".join([f"<p>- {i}</p>" for i in insights["weekday_pattern"]]) + "</div>", unsafe_allow_html=True)
        with insight_col2:
            if insights.get("occupancy"):
                st.markdown("<div class='success-card'><h4>病床利用率と回転数</h4>" + "".join([f"<p>- {i}</p>" for i in insights["occupancy"]]) + "</div>", unsafe_allow_html=True)
            if insights.get("general"):
                st.markdown("<div class='warning-card'><h4>データ解釈上の注意点</h4>" + "".join([f"<p>- {i}</p>" for i in insights["general"]]) + "</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("インサイトを生成するためのデータまたは関数が不足しています。")