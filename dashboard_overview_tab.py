# dashboard_overview_tab.py (高度目標値管理対応版)
# 既存のdashboard_overview_tab.pyと置き換えてください

import streamlit as st
import pandas as pd
from datetime import timedelta, datetime
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
    """数値フォーマット関数（既存と同じ）"""
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

def get_current_period_type(current_date=None):
    """
    現在の期間タイプ（平日/休日）を判定
    
    Args:
        current_date (pd.Timestamp, optional): 判定対象日（Noneの場合は今日）
        
    Returns:
        str: "平日", "休日", または "全日"
    """
    if current_date is None:
        current_date = pd.Timestamp.now()
    
    if isinstance(current_date, str):
        current_date = pd.to_datetime(current_date)
    
    # 土日は休日、平日は平日として判定
    if current_date.weekday() in [5, 6]:  # 土曜日(5), 日曜日(6)
        return "休日"
    else:
        return "平日"

def load_advanced_target_values_csv():
    """
    高度目標値CSVファイル読み込み機能（7列構造対応）
    
    Returns:
        pd.DataFrame: 目標値データフレーム
    """
    if 'advanced_target_values_df' not in st.session_state:
        st.session_state.advanced_target_values_df = pd.DataFrame()
    
    with st.sidebar.expander("🎯 高度目標値設定", expanded=False):
        st.markdown("##### 高度目標値CSVファイル読み込み")
        
        # CSVファイルアップロード
        uploaded_target_file = st.file_uploader(
            "高度目標値CSVファイルを選択",
            type=['csv'],
            key="advanced_target_values_upload",
            help="部門コード、部門名、部門種別、指標タイプ、期間区分、単位、目標値が含まれるCSVファイルをアップロード"
        )
        
        if uploaded_target_file is not None:
            try:
                target_df = pd.read_csv(uploaded_target_file, encoding='utf-8-sig')
                
                # 必要な列の確認（新しい7列構造）
                required_columns = ['部門コード', '部門名', '部門種別', '指標タイプ', '期間区分', '単位', '目標値']
                missing_columns = [col for col in required_columns if col not in target_df.columns]
                
                if missing_columns:
                    st.error(f"❌ 必要な列が見つかりません: {', '.join(missing_columns)}")
                    st.info("必要な列: 部門コード, 部門名, 部門種別, 指標タイプ, 期間区分, 単位, 目標値")
                    st.info(f"読み込まれた列: {', '.join(target_df.columns.tolist())}")
                else:
                    # データ型の変換とクリーニング
                    target_df['部門コード'] = target_df['部門コード'].astype(str).str.strip()
                    target_df['部門名'] = target_df['部門名'].astype(str).str.strip()
                    target_df['部門種別'] = target_df['部門種別'].astype(str).str.strip()
                    target_df['指標タイプ'] = target_df['指標タイプ'].astype(str).str.strip()
                    target_df['期間区分'] = target_df['期間区分'].astype(str).str.strip()
                    target_df['単位'] = target_df['単位'].astype(str).str.strip()
                    target_df['目標値'] = pd.to_numeric(target_df['目標値'], errors='coerce')
                    
                    # 無効なデータの除去
                    invalid_rows = target_df['目標値'].isna()
                    if invalid_rows.any():
                        st.warning(f"⚠️ 無効な目標値を持つ行を除外しました: {invalid_rows.sum()}行")
                        target_df = target_df[~invalid_rows]
                    
                    st.session_state.advanced_target_values_df = target_df
                    st.success(f"✅ 高度目標値データを読み込みました（{len(target_df)}行）")
                    
                    # データプレビューとデバッグ情報
                    with st.expander("📋 高度目標値データプレビュー", expanded=False):
                        st.dataframe(target_df.head(10), use_container_width=True)
                        
                        # 統計情報表示
                        st.markdown("**🔍 統計情報**")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            unique_depts = target_df['部門コード'].unique()
                            unique_dept_types = target_df['部門種別'].unique()
                            st.write(f"**部門数**: {len(unique_depts)}件")
                            st.write(f"**部門種別**: {', '.join(unique_dept_types)}")
                        
                        with col2:
                            unique_indicators = target_df['指標タイプ'].unique()
                            unique_periods = target_df['期間区分'].unique()
                            st.write(f"**指標タイプ**: {len(unique_indicators)}種類")
                            st.write(f"**期間区分**: {', '.join(unique_periods)}")
                        
                        with col3:
                            unique_units = target_df['単位'].unique()
                            target_range = f"{target_df['目標値'].min():.1f} ～ {target_df['目標値'].max():.1f}"
                            st.write(f"**単位種類**: {len(unique_units)}種類")
                            st.write(f"**目標値範囲**: {target_range}")
                        
                        # 指標タイプ別の詳細
                        st.markdown("**📊 指標タイプ別データ数**")
                        indicator_counts = target_df['指標タイプ'].value_counts()
                        for indicator, count in indicator_counts.items():
                            st.caption(f"• {indicator}: {count}件")
                        
            except Exception as e:
                st.error(f"❌ CSVファイル読み込みエラー: {e}")
                logger.error(f"高度目標値CSVファイル読み込みエラー: {e}", exc_info=True)
        
        # 現在の読み込み状況表示
        if not st.session_state.advanced_target_values_df.empty:
            current_df = st.session_state.advanced_target_values_df
            st.info(f"📊 現在の高度目標値データ: {len(current_df)}行")
            
            # 簡単な統計情報表示
            if len(current_df) > 0:
                dept_count = current_df['部門コード'].nunique()
                indicator_count = current_df['指標タイプ'].nunique()
                st.caption(f"部門数: {dept_count}件, 指標種類: {indicator_count}種類")
            
            # フィルター状況との照合
            current_filter_config = get_unified_filter_config() if get_unified_filter_config else None
            if current_filter_config:
                filter_mode = current_filter_config.get('filter_mode', '全体')
                
                if filter_mode == "特定診療科":
                    selected_depts = current_filter_config.get('selected_depts', [])
                    if selected_depts:
                        # 診療科の目標値確認
                        matched_targets = []
                        for dept in selected_depts:
                            dept_targets = current_df[
                                (current_df['部門コード'] == dept) | 
                                (current_df['部門名'] == dept)
                            ]
                            if not dept_targets.empty:
                                matched_targets.extend(dept_targets['指標タイプ'].unique())
                        
                        if matched_targets:
                            st.success(f"🎯 診療科目標値: {len(set(matched_targets))}種類の指標")
                            st.caption(f"対象指標: {', '.join(set(matched_targets))}")
                        else:
                            st.warning(f"⚠️ 選択診療科の目標値が見つかりません")
                
                elif filter_mode == "特定病棟":
                    selected_wards = current_filter_config.get('selected_wards', [])
                    if selected_wards:
                        # 病棟の目標値確認
                        matched_targets = []
                        for ward in selected_wards:
                            ward_targets = current_df[
                                (current_df['部門コード'] == ward) | 
                                (current_df['部門名'] == ward)
                            ]
                            if not ward_targets.empty:
                                matched_targets.extend(ward_targets['指標タイプ'].unique())
                        
                        if matched_targets:
                            st.success(f"🎯 病棟目標値: {len(set(matched_targets))}種類の指標")
                            st.caption(f"対象指標: {', '.join(set(matched_targets))}")
                        else:
                            st.warning(f"⚠️ 選択病棟の目標値が見つかりません")
            
            # クリアボタン
            if st.button("🗑️ 高度目標値データクリア", key="clear_advanced_target_values"):
                st.session_state.advanced_target_values_df = pd.DataFrame()
                st.success("高度目標値データをクリアしました")
                st.rerun()
        else:
            st.info("高度目標値データが設定されていません")
            
            # 高度サンプルCSVのダウンロードリンク
            st.markdown("**📁 高度サンプルCSVファイル**")
            
            # 包括的サンプル
            sample_comprehensive = """部門コード,部門名,部門種別,指標タイプ,期間区分,単位,目標値
内科,内科,診療科,日平均在院患者数,全日,人/日,45.0
内科,内科,診療科,日平均在院患者数,平日,人/日,48.0
内科,内科,診療科,日平均在院患者数,休日,人/日,40.0
内科,内科,診療科,週間新入院患者数,全日,人/週,28.0
外科,外科,診療科,日平均在院患者数,全日,人/日,35.0
外科,外科,診療科,週間新入院患者数,全日,人/週,21.0
ICU,ICU,病棟,日平均在院患者数,全日,人/日,12.5
A1病棟,A1病棟,病棟,日平均在院患者数,全日,人/日,30.0
病院全体,病院全体,全体,日平均在院患者数,平日,人/日,480.0
病院全体,病院全体,全体,日平均在院患者数,休日,人/日,400.0
病院全体,病院全体,全体,日平均新入院患者数,平日,人/日,32.0
病院全体,病院全体,全体,病床利用率,全日,%,85.0"""
            
            st.download_button(
                label="📄 包括的サンプルCSVダウンロード",
                data=sample_comprehensive,
                file_name="advanced_targets_comprehensive.csv",
                mime="text/csv",
                help="複数指標・期間区分対応の包括的な目標値設定サンプル"
            )
    
    return st.session_state.advanced_target_values_df

def get_advanced_target_values(target_df, filter_config, analysis_date=None):
    """
    高度フィルター設定に基づいて複数の目標値を取得
    
    Args:
        target_df (pd.DataFrame): 高度目標値データフレーム
        filter_config (dict): フィルター設定
        analysis_date (pd.Timestamp, optional): 分析対象日（期間区分判定用）
        
    Returns:
        dict: 指標タイプ別の目標値情報
    """
    if target_df.empty or not filter_config:
        logger.info("高度目標値取得: 目標値データまたはフィルター設定が空です")
        return {}
    
    try:
        filter_mode = filter_config.get('filter_mode', '全体')
        logger.info(f"高度目標値取得: フィルターモード = {filter_mode}")
        
        # 現在の期間タイプを判定
        current_period_type = get_current_period_type(analysis_date)
        logger.info(f"期間タイプ判定: {current_period_type}")
        
        target_results = {}
        
        if filter_mode == "特定診療科":
            selected_depts = filter_config.get('selected_depts', [])
            logger.info(f"選択された診療科: {selected_depts}")
            
            if selected_depts:
                for dept in selected_depts:
                    # 診療科の目標値を検索
                    dept_targets = target_df[
                        ((target_df['部門コード'] == dept) | (target_df['部門名'] == dept)) &
                        (target_df['部門種別'] == '診療科')
                    ]
                    
                    for _, target_row in dept_targets.iterrows():
                        indicator_type = target_row['指標タイプ']
                        period_type = target_row['期間区分']
                        target_value = target_row['目標値']
                        unit = target_row['単位']
                        
                        # 期間区分が一致するか、全日の場合は適用
                        if period_type == '全日' or period_type == current_period_type:
                            if indicator_type not in target_results:
                                target_results[indicator_type] = {
                                    'value': 0,
                                    'unit': unit,
                                    'departments': [],
                                    'period_type': period_type
                                }
                            
                            target_results[indicator_type]['value'] += target_value
                            target_results[indicator_type]['departments'].append(dept)
        
        elif filter_mode == "特定病棟":
            selected_wards = filter_config.get('selected_wards', [])
            logger.info(f"選択された病棟: {selected_wards}")
            
            if selected_wards:
                for ward in selected_wards:
                    # 病棟の目標値を検索
                    ward_targets = target_df[
                        ((target_df['部門コード'] == ward) | (target_df['部門名'] == ward)) &
                        (target_df['部門種別'] == '病棟')
                    ]
                    
                    for _, target_row in ward_targets.iterrows():
                        indicator_type = target_row['指標タイプ']
                        period_type = target_row['期間区分']
                        target_value = target_row['目標値']
                        unit = target_row['単位']
                        
                        # 期間区分が一致するか、全日の場合は適用
                        if period_type == '全日' or period_type == current_period_type:
                            if indicator_type not in target_results:
                                target_results[indicator_type] = {
                                    'value': 0,
                                    'unit': unit,
                                    'departments': [],
                                    'period_type': period_type
                                }
                            
                            target_results[indicator_type]['value'] += target_value
                            target_results[indicator_type]['departments'].append(ward)
        
        else:  # 全体フィルター
            # 病院全体の目標値を検索
            hospital_targets = target_df[target_df['部門種別'] == '全体']
            
            for _, target_row in hospital_targets.iterrows():
                indicator_type = target_row['指標タイプ']
                period_type = target_row['期間区分']
                target_value = target_row['目標値']
                unit = target_row['単位']
                
                # 期間区分が一致するか、全日の場合は適用
                if period_type == '全日' or period_type == current_period_type:
                    target_results[indicator_type] = {
                        'value': target_value,
                        'unit': unit,
                        'departments': ['病院全体'],
                        'period_type': period_type
                    }
        
        logger.info(f"取得された目標値: {len(target_results)}種類の指標")
        return target_results
        
    except Exception as e:
        logger.error(f"高度目標値取得エラー: {e}", exc_info=True)
        return {}

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

def display_advanced_metrics_layout(metrics, selected_period_info, prev_year_metrics=None, prev_year_period_info=None, advanced_targets=None):
    """
    高度目標値対応の統合メトリクス表示
    
    Args:
        metrics (dict): 計算されたメトリクス
        selected_period_info (str): 選択期間の説明
        prev_year_metrics (dict, optional): 昨年度同期間のメトリクス
        prev_year_period_info (str, optional): 昨年度同期間の説明
        advanced_targets (dict, optional): 高度目標値データ
    """
    if not metrics:
        st.warning("表示するメトリクスデータがありません。")
        return

    # 設定値の取得
    total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
    target_occupancy_rate = st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE)
    avg_length_of_stay_target = st.session_state.get('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY)
    target_admissions_monthly = st.session_state.get('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS)

    # 期間表示は下部のシンプルな表示のみ使用

    # 高度目標値情報の表示
    if advanced_targets:
        st.markdown("### 🎯 設定目標値")
        target_cols = st.columns(min(len(advanced_targets), 4))
        
        for i, (indicator_type, target_info) in enumerate(advanced_targets.items()):
            col_idx = i % 4
            with target_cols[col_idx]:
                departments_str = ', '.join(target_info['departments'])
                st.metric(
                    f"{indicator_type}",
                    f"{target_info['value']:.1f}{target_info['unit']}",
                    delta=f"{target_info['period_type']} | {departments_str}",
                    delta_color="off"
                )

    # 主要指標を4つ横一列で表示
    st.markdown("### 📊 主要指標")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # 日平均在院患者数（高度目標値対応）
        avg_daily_census_val = metrics.get('avg_daily_census', 0)
        
        # 高度目標値から対応する目標を取得
        target_census = None
        target_source = "デフォルト"
        
        if advanced_targets and '日平均在院患者数' in advanced_targets:
            target_census = advanced_targets['日平均在院患者数']['value']
            target_source = "設定目標"
        else:
            target_census = total_beds * target_occupancy_rate
            target_source = "理論値"
        
        census_delta = avg_daily_census_val - target_census
        census_color = "normal" if census_delta >= 0 else "inverse"
        
        st.metric(
            "👥 日平均在院患者数",
            f"{avg_daily_census_val:.1f}人",
            delta=f"{census_delta:+.1f}人 ({target_source}比)",
            delta_color=census_color,
            help=f"{selected_period_info}の日平均在院患者数"
        )
        st.caption(f"目標: {target_census:.1f}人")
        if target_census > 0:
            achievement_rate = (avg_daily_census_val / target_census * 100)
            st.caption(f"達成率: {achievement_rate:.1f}%")

    with col2:
        # 病床利用率（高度目標値対応）
        bed_occupancy_rate_val = metrics.get('bed_occupancy_rate', 0)
        
        # 高度目標値から目標病床利用率を取得
        target_occupancy = None
        if advanced_targets and '病床利用率' in advanced_targets:
            target_occupancy = advanced_targets['病床利用率']['value']
        else:
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

    with col3:
        # 平均在院日数
        avg_los_val = metrics.get('avg_los', 0)
        alos_delta = avg_los_val - avg_length_of_stay_target
        alos_color = "inverse" if alos_delta > 0 else "normal"
        
        st.metric(
            "📅 平均在院日数",
            f"{avg_los_val:.1f}日",
            delta=f"{alos_delta:+.1f}日 (目標比)",
            delta_color=alos_color,
            help=f"{selected_period_info}の平均在院日数"
        )
        st.caption(f"目標: {avg_length_of_stay_target:.1f}日")

    with col4:
        # 日平均新入院患者数（高度目標値対応）
        avg_daily_admissions_val = metrics.get('avg_daily_admissions', 0)
        
        # 高度目標値から目標を取得
        target_daily_admissions = None
        if advanced_targets and '日平均新入院患者数' in advanced_targets:
            target_daily_admissions = advanced_targets['日平均新入院患者数']['value']
        else:
            target_daily_admissions = target_admissions_monthly / 30
        
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

    # 週間目標値がある場合の追加表示
    if advanced_targets and '週間新入院患者数' in advanced_targets:
        st.markdown("---")
        st.markdown("### 📈 週間指標")
        
        week_col1, week_col2, week_col3 = st.columns(3)
        
        with week_col1:
            # 週間新入院患者数の計算
            period_days_val = metrics.get('period_days', 7)
            total_admissions = metrics.get('total_admissions', 0)
            weekly_admissions_equivalent = (total_admissions / period_days_val) * 7 if period_days_val > 0 else 0
            
            target_weekly_admissions = advanced_targets['週間新入院患者数']['value']
            weekly_delta = weekly_admissions_equivalent - target_weekly_admissions
            weekly_color = "normal" if weekly_delta >= 0 else "inverse"
            
            st.metric(
                "📊 週換算新入院患者数",
                f"{weekly_admissions_equivalent:.1f}人/週",
                delta=f"{weekly_delta:+.1f}人/週 (目標比)",
                delta_color=weekly_color,
                help="期間データを週換算した新入院患者数"
            )
            st.caption(f"目標: {target_weekly_admissions:.1f}人/週")

    # 昨年度同期間との比較（既存機能維持）
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

    # 詳細情報セクション
    st.markdown("---")
    with st.expander("📋 高度目標値設定詳細", expanded=False):
        if advanced_targets:
            detail_col1, detail_col2 = st.columns(2)
            
            with detail_col1:
                st.markdown("**🎯 設定済み目標値**")
                for indicator_type, target_info in advanced_targets.items():
                    departments_str = ', '.join(target_info['departments'])
                    st.write(f"• **{indicator_type}**: {target_info['value']:.1f}{target_info['unit']}")
                    st.caption(f"　対象: {departments_str} ({target_info['period_type']})")
            
            with detail_col2:
                st.markdown("**📊 達成状況サマリー**")
                achievement_summary = []
                
                if '日平均在院患者数' in advanced_targets:
                    target_val = advanced_targets['日平均在院患者数']['value']
                    actual_val = avg_daily_census_val
                    achievement = (actual_val / target_val * 100) if target_val > 0 else 0
                    achievement_summary.append(f"日平均在院患者数: {achievement:.1f}%")
                
                if '日平均新入院患者数' in advanced_targets:
                    target_val = advanced_targets['日平均新入院患者数']['value']
                    actual_val = avg_daily_admissions_val
                    achievement = (actual_val / target_val * 100) if target_val > 0 else 0
                    achievement_summary.append(f"日平均新入院患者数: {achievement:.1f}%")
                
                for summary_item in achievement_summary:
                    st.write(f"• {summary_item}")
        else:
            st.info("高度目標値が設定されていません。サイドバーの「高度目標値設定」からCSVファイルをアップロードしてください。")

def display_kpi_cards_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent):
    """
    高度目標値対応のKPIカード表示（メイン関数）
    """
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    if calculate_kpis is None:
        st.error("KPI計算関数が利用できません。")
        return
    
    # 高度目標値データの読み込み
    advanced_target_df = load_advanced_target_values_csv()
    
    # 現在期間のKPI計算
    kpis_selected_period = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)
    if kpis_selected_period is None or kpis_selected_period.get("error"):
        st.warning(f"選択された期間のKPI計算に失敗しました。理由: {kpis_selected_period.get('error', '不明') if kpis_selected_period else '不明'}")
        return
    
    # メトリクス準備
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
    
    # フィルター設定取得と高度目標値取得
    current_filter_config = get_unified_filter_config() if get_unified_filter_config else None
    advanced_targets = {}
    
    if not advanced_target_df.empty and current_filter_config:
        # 分析期間の終了日を取得して期間区分判定に使用
        analysis_end_date = end_date
        advanced_targets = get_advanced_target_values(advanced_target_df, current_filter_config, analysis_end_date)
        logger.info(f"取得された高度目標値: {len(advanced_targets)}種類")
    
    # 昨年度同期間データの計算
    df_original = st.session_state.get('df')
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
        except Exception as e:
            logger.error(f"昨年度同期間データ処理エラー: {e}", exc_info=True)
    
    period_description = f"{start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')}"
    display_advanced_metrics_layout(
        metrics_for_display, 
        period_description, 
        prev_year_metrics, 
        prev_year_period_info,
        advanced_targets
    )

# 既存の関数はそのまま維持（display_trend_graphs_only, display_insights）
def display_trend_graphs_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent):
    """既存のグラフ表示関数（変更なし）"""
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
    """既存のインサイト表示関数（変更なし）"""
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