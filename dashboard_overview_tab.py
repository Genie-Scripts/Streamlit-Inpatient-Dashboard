# dashboard_overview_tab.py
# 主要指標タブのレイアウト、KPI表示、および目標値関連のロジックを管理します。

import streamlit as st
import pandas as pd
from datetime import timedelta
import logging

# --- モジュールのインポート ---
# 内部モジュールやライブラリをインポートします。
# エラーハンドリングを行い、必要なモジュールが見つからない場合に通知します。
logger = logging.getLogger(__name__)

try:
    from dashboard_charts import (
        create_monthly_trend_chart,
        create_admissions_discharges_chart,
        create_occupancy_chart
    )
except ImportError:
    st.error("dashboard_charts.py が見つからないか、必要な関数が定義されていません。")
    create_monthly_trend_chart = create_admissions_discharges_chart = create_occupancy_chart = None

try:
    from kpi_calculator import calculate_kpis, analyze_kpi_insights
except ImportError:
    st.error("kpi_calculator.py が見つからないか、必要な関数が定義されていません。")
    calculate_kpis = analyze_kpi_insights = None

try:
    from unified_filters import get_unified_filter_config
except ImportError:
    st.error("unified_filters.py が見つからないか、必要な関数が定義されていません。")
    get_unified_filter_config = None

from config import (
    DEFAULT_OCCUPANCY_RATE, DEFAULT_ADMISSION_FEE, DEFAULT_TARGET_PATIENT_DAYS,
    APP_VERSION, NUMBER_FORMAT, DEFAULT_TOTAL_BEDS, DEFAULT_AVG_LENGTH_OF_STAY,
    DEFAULT_TARGET_ADMISSIONS
)


# --- ヘルパー関数 ---

def format_number_with_config(value, unit="", format_type="default"):
    """設定に基づいて数値をフォーマットする"""
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


# --- データロード関連 ---

def load_target_values_csv():
    """
    サイドバーから目標値CSVファイルを読み込み、クリーニングを行う。
    成功した場合、DataFrameをst.session_stateに保存して返す。
    """
    if 'target_values_df' not in st.session_state:
        st.session_state.target_values_df = pd.DataFrame()

    with st.sidebar.expander("🎯 目標値設定", expanded=False):
        uploaded_target_file = st.file_uploader(
            "目標値CSVファイルを選択",
            type=['csv'],
            key="target_values_upload",
            help="部門コード/部門名、目標値、区分を含むCSVファイルをアップロード"
        )

        if uploaded_target_file is not None:
            try:
                # 複数のエンコーディングを試行
                encodings_to_try = ['utf-8-sig', 'utf-8', 'shift_jis', 'cp932']
                target_df = None
                for encoding in encodings_to_try:
                    try:
                        uploaded_target_file.seek(0)
                        target_df = pd.read_csv(uploaded_target_file, encoding=encoding)
                        logger.info(f"目標値CSVを{encoding}で読み込み成功")
                        break
                    except UnicodeDecodeError:
                        continue
                
                if target_df is None:
                    st.error("❌ CSVファイルのエンコーディングが認識できません。")
                    return st.session_state.target_values_df

                # 必須列のチェック
                required_columns = ['目標値', '区分']
                optional_columns = ['部門コード', '部門名']
                if not all(col in target_df.columns for col in required_columns) or \
                   not any(col in target_df.columns for col in optional_columns):
                    st.error("❌ 必要な列['目標値', '区分']と['部門コード'または'部門名']が見つかりません。")
                    return st.session_state.target_values_df

                # データクリーニング
                if '部門コード' in target_df.columns:
                    target_df['部門コード'] = target_df['部門コード'].astype(str).str.strip().str.replace(r'\s+', '', regex=True)
                if '部門名' in target_df.columns:
                    target_df['部門名'] = target_df['部門名'].astype(str).str.strip()
                
                target_df['目標値'] = pd.to_numeric(target_df['目標値'], errors='coerce')
                target_df.dropna(subset=['目標値'], inplace=True)

                st.session_state.target_values_df = target_df
                st.success(f"✅ 目標値データを読み込みました ({len(target_df)}行)")

                with st.expander("プレビュー", expanded=False):
                    st.dataframe(target_df.head())

            except Exception as e:
                st.error(f"❌ CSVファイル読み込みエラー: {e}")
                logger.error(f"目標値CSVファイル読み込みエラー: {e}", exc_info=True)

    return st.session_state.target_values_df


# --- 目標値取得ロジック ---

def get_target_value_for_filter(target_df, filter_config):
    """
    現在のフィルター設定に基づいて、目標値データフレームから対応する目標値を取得する。
    """
    if target_df.empty or not filter_config:
        return None, None, None

    try:
        filter_mode = filter_config.get('filter_mode', '全体')
        logger.info(f"目標値取得: モード='{filter_mode}', 選択='{filter_config.get('selected_depts') or filter_config.get('selected_wards')}'")

        if filter_mode == "特定診療科" or filter_mode == "特定病棟":
            is_dept = (filter_mode == "特定診療科")
            selected_items = filter_config.get('selected_depts' if is_dept else 'selected_wards', [])
            key_column = '部門名' if is_dept else '部門コード'
            item_name = "診療科" if is_dept else "病棟"

            if not selected_items:
                return None, None, None

            # 選択された項目に一致する目標値を探す
            matched_targets = target_df[target_df[key_column].isin(selected_items)]
            if not matched_targets.empty:
                total_target = matched_targets['目標値'].sum()
                matched_names = ', '.join(matched_targets[key_column].unique())
                return total_target, f"{item_name}: {matched_names}", "全日"

        elif filter_mode == "全体":
            # 「全体」を示すキーワードで目標値を探す
            overall_keywords = ['全体', '病院全体', '総合']
            for keyword in overall_keywords:
                # まず部門名で検索
                if '部門名' in target_df.columns:
                    target_row = target_df[target_df['部門名'] == keyword]
                    if not target_row.empty:
                        return float(target_row['目標値'].iloc[0]), f"全体 ({keyword})", "全日"
                # 次に部門コードで検索
                if '部門コード' in target_df.columns:
                    target_row = target_df[target_df['部門コード'] == keyword]
                    if not target_row.empty:
                        return float(target_row['目標値'].iloc[0]), f"全体 ({keyword})", "全日"

            # 見つからない場合は全部門の合計を計算
            total_sum = target_df['目標値'].sum()
            return total_sum, f"全体 (全部門合計)", "全日"

        return None, None, None

    except Exception as e:
        logger.error(f"目標値取得エラー: {e}", exc_info=True)
        return None, None, None


# --- 表示用コンポーネント ---

def display_unified_metrics_layout(metrics, selected_period_info, prev_year_metrics=None, prev_year_period_info=None, target_info=None):
    """
    主要KPIメトリクスをカード形式で表示する。
    """
    if not metrics:
        st.warning("表示するメトリクスデータがありません。")
        return

    # 設定値の取得
    total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
    target_occupancy_rate = st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE)
    avg_length_of_stay_target = st.session_state.get('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY)
    target_admissions_monthly = st.session_state.get('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS)
    
    st.info(f"📊 分析期間: {selected_period_info}")
    st.caption("※期間はサイドバーの「分析フィルター」で変更できます。")

    # 目標値情報の表示
    if target_info and target_info[0] is not None:
        target_value, target_dept_name, target_period = target_info
        st.success(f"🎯 目標値設定: {target_dept_name} - {target_value:.1f}人/日 ({target_period})")
    else:
        st.info("🎯 目標値: 未設定（理論値を使用）")

    st.markdown("### 📊 主要指標")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # 日平均在院患者数
        avg_daily_census_val = metrics.get('avg_daily_census', 0)
        target_census = target_info[0] if (target_info and target_info[0] is not None) else (total_beds * target_occupancy_rate)
        delta_label = "目標比" if (target_info and target_info[0] is not None) else "理論値比"
        census_delta = avg_daily_census_val - target_census
        
        st.metric("👥 日平均在院患者数", f"{avg_daily_census_val:.1f}人", f"{census_delta:+.1f}人 ({delta_label})", delta_color="normal" if census_delta >= 0 else "inverse")
        st.caption(f"目標: {target_census:.1f}人")

    with col2:
        # 病床利用率
        bed_occupancy_rate_val = metrics.get('bed_occupancy_rate', 0)
        target_occupancy = target_occupancy_rate * 100
        occupancy_delta = bed_occupancy_rate_val - target_occupancy
        
        st.metric("🏥 病床利用率", f"{bed_occupancy_rate_val:.1f}%", f"{occupancy_delta:+.1f}% (目標比)", delta_color="normal" if occupancy_delta >= -5 else "inverse")
        st.caption(f"目標: {target_occupancy:.1f}%")

    with col3:
        # 平均在院日数
        avg_los_val = metrics.get('avg_los', 0)
        alos_delta = avg_los_val - avg_length_of_stay_target

        st.metric("📅 平均在院日数", f"{avg_los_val:.1f}日", f"{alos_delta:+.1f}日 (目標比)", delta_color="inverse" if alos_delta > 0 else "normal")
        st.caption(f"目標: {avg_length_of_stay_target:.1f}日")

    with col4:
        # 日平均新入院患者数
        avg_daily_admissions_val = metrics.get('avg_daily_admissions', 0)
        target_daily_admissions = target_admissions_monthly / 30.4
        daily_delta = avg_daily_admissions_val - target_daily_admissions
        
        st.metric("📈 日平均新入院患者数", f"{avg_daily_admissions_val:.1f}人/日", f"{daily_delta:+.1f}人/日 (目標比)", delta_color="normal" if daily_delta >= 0 else "inverse")
        st.caption(f"目標: {target_daily_admissions:.1f}人/日")


def display_kpi_cards_only(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent, show_debug=False):
    """
    KPIカード表示のメインコントローラー。
    データ準備、KPI計算、表示関数の呼び出しを行う。
    """
    if df is None or df.empty:
        st.warning("データが読み込まれていません。")
        return
    if not calculate_kpis:
        st.error("KPI計算関数が利用できません。")
        return
    
    # 1. 目標値データの準備
    target_df = st.session_state.get('target_values_df', pd.DataFrame())
    if target_df.empty:
        # サイドバーから読み込みを試行
        target_df = load_target_values_csv()

    # 2. KPI計算
    kpis_selected_period = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)
    if not kpis_selected_period or kpis_selected_period.get("error"):
        st.warning(f"選択された期間のKPI計算に失敗しました。")
        return

    metrics_for_display = {
        'avg_daily_census': kpis_selected_period.get('avg_daily_census'),
        'bed_occupancy_rate': kpis_selected_period.get('bed_occupancy_rate'),
        'avg_los': kpis_selected_period.get('alos'),
        'avg_daily_admissions': kpis_selected_period.get('avg_daily_admissions'),
    }

    # 3. 目標値の取得
    current_filter_config = get_unified_filter_config()
    target_info = get_target_value_for_filter(target_df, current_filter_config)

    # 4. KPIカードの表示
    period_description = f"{start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')}"
    display_unified_metrics_layout(
        metrics_for_display,
        period_description,
        target_info=target_info
    )

    # 5. デバッグ情報（オプション）
    if show_debug:
        with st.expander("🔧 詳細設定・デバッグ情報", expanded=False):
            st.markdown("#### フィルター設定")
            st.json(current_filter_config or {})
            
            st.markdown("#### KPI計算結果")
            st.json({k: (f"{v:.2f}" if isinstance(v, float) else v) for k, v in kpis_selected_period.items() if not isinstance(v, pd.DataFrame)})
            
            st.markdown("#### 目標値検索結果")
            st.json(target_info or {"result": "No target found"})

# --- グラフとインサイト表示 ---

def display_trend_graphs_and_insights(df, start_date, end_date, total_beds_setting, target_occupancy_setting_percent):
    """
    トレンドグラフと分析インサイトを表示する。
    """
    if df is None or df.empty: return
    if not all([calculate_kpis, create_monthly_trend_chart, create_admissions_discharges_chart, create_occupancy_chart, analyze_kpi_insights]):
        st.info("グラフまたはインサイト表示に必要なモジュールが不足しています。")
        return

    kpi_data = calculate_kpis(df, start_date, end_date, total_beds=total_beds_setting)
    if not kpi_data or kpi_data.get("error"):
        st.warning("グラフ表示用のデータ計算に失敗しました。")
        return

    # グラフ表示
    st.markdown("---")
    st.markdown("### 📈 トレンドグラフ")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("###### 月別 平均在院日数と入退院数")
        monthly_chart = create_monthly_trend_chart(kpi_data)
        st.plotly_chart(monthly_chart, use_container_width=True)

    with col2:
        st.markdown("###### 週別 入退院バランス")
        balance_chart = create_admissions_discharges_chart(kpi_data)
        st.plotly_chart(balance_chart, use_container_width=True)

    st.markdown("###### 月別 病床利用率の推移")
    occupancy_chart = create_occupancy_chart(kpi_data, total_beds_setting, target_occupancy_setting_percent)
    st.plotly_chart(occupancy_chart, use_container_width=True)

    # インサイト表示
    insights = analyze_kpi_insights(kpi_data, total_beds_setting)
    if insights:
        st.markdown("---")
        st.markdown("### 💡 分析インサイト")
        for category, messages in insights.items():
            if messages:
                with st.container(border=True):
                    st.markdown(f"**{category.capitalize()}に関する考察**")
                    for msg in messages:
                        st.write(f"- {msg}")