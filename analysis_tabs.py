import warnings
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import hashlib
import gc
import logging

# 統一フィルター関連のインポート
from unified_filters import (
    create_unified_filter_sidebar,
    apply_unified_filters,
    get_unified_filter_summary,
    initialize_unified_filters,
    validate_unified_filters,
    get_unified_filter_config
)

# ユーティリティ関数のインポート
from utils import safe_date_filter

# 既存モジュールからのインポート
try:
    from alos_analysis_tab import display_alos_analysis_tab
    from dow_analysis_tab import display_dow_analysis_tab
    from individual_analysis_tab import display_individual_analysis_tab
    from forecast_analysis_tab import display_forecast_analysis_tab
    from chart import (
        create_interactive_patient_chart,
        create_interactive_dual_axis_chart,
        create_forecast_comparison_chart
    )
    from pdf_generator import create_pdf, create_landscape_pdf
    from forecast import generate_filtered_summaries, create_forecast_dataframe
    from kpi_calculator import calculate_kpis, analyze_kpi_insights
    from utils import get_display_name_for_dept
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    display_alos_analysis_tab = None
    display_dow_analysis_tab = None
    display_individual_analysis_tab = None
    display_forecast_analysis_tab = None
    create_interactive_patient_chart = None
    create_interactive_dual_axis_chart = None
    create_forecast_comparison_chart = None
    create_pdf = None
    create_landscape_pdf = None
    generate_filtered_summaries = None
    create_forecast_dataframe = None
    calculate_kpis = None
    analyze_kpi_insights = None
    get_display_name_for_dept = None
    get_unified_filter_config = None

logger = logging.getLogger(__name__)

# ===============================================================================
# メイン関数群（統一フィルター対応版）
# ===============================================================================
def create_detailed_analysis_tab():
    """詳細分析タブのメイン関数（統一フィルター対応版）"""
    st.header("📈 詳細分析")

    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return

    df = st.session_state.get('df')
    if df is None or df.empty:
        st.error("分析対象のデータがありません。")
        return

    if get_unified_filter_config is None:
        st.error("統一フィルター機能が利用できません。unified_filters.py を確認してください。")
        return

    initialize_unified_filters(df)
    filter_config = create_unified_filter_sidebar(df)
    if filter_config is None:
        return

    is_valid, validation_message = validate_unified_filters(df)
    if not is_valid:
        st.error(f"フィルター設定エラー: {validation_message}")
        return

    df_filtered = apply_unified_filters(df)

    if df_filtered.empty:
        filter_summary_on_empty = get_unified_filter_summary()
        st.info(f"🔍 {filter_summary_on_empty}")
        st.warning("選択されたフィルター条件にマッチするデータがありません。")
        return

    filter_summary = get_unified_filter_summary()
    data_count = len(df_filtered)
    st.info(f"🔍 {filter_summary}")
    st.success(f"📊 該当データ: {data_count:,}行")

    common_config = st.session_state.get('common_config', {})

    los_tab, weekday_tab, individual_tab = st.tabs([
        "📊 平均在院日数分析",
        "📅 曜日別入退院分析",
        "🔍 個別分析"
    ])

    with los_tab:
        create_los_analysis_section(df_filtered, filter_config, common_config)

    with weekday_tab:
        create_weekday_analysis_section(df_filtered, filter_config, common_config)

    with individual_tab:
        create_individual_analysis_section(df_filtered, filter_config)

def create_data_tables_tab():
    """データテーブルタブのメイン関数（統一フィルター対応版）"""
    st.header("📋 データテーブル")

    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return

    df_original = st.session_state.get('df')
    if df_original is None or df_original.empty:
        st.error("分析対象のデータがありません。")
        return

    if get_unified_filter_config is None:
        st.error("統一フィルター機能が利用できません。unified_filters.py を確認してください。")
        return
    initialize_unified_filters(df_original)

    # 統一フィルターを適用するために filter_config を取得 (サイドバー表示はメインの create_detailed_analysis_tab で行われる想定)
    # もしこのタブ単独でフィルターを操作させたい場合は create_unified_filter_sidebar を呼ぶ必要があるが、
    # 通常はメインのフィルター設定が引き継がれるべき。
    # get_unified_filter_config() で現在のフィルター設定を取得できる。
    current_filter_config = get_unified_filter_config()
    if current_filter_config is None:
        # フィルターがまだ設定されていない場合（初回アクセスなど）、
        # create_unified_filter_sidebar を呼んで初期化・設定を促すか、
        # デフォルトフィルターを適用する。ここでは apply_unified_filters がよしなに扱うことを期待。
        pass


    df_filtered = apply_unified_filters(df_original)
    filter_summary = get_unified_filter_summary()
    st.info(f"🔍 {filter_summary}")

    if df_filtered.empty:
        st.warning("選択されたフィルター条件にマッチするデータがありません。")
        return

    ward_table_tab, dept_table_tab = st.tabs([
        "🏥 病棟別データテーブル",
        "🩺 診療科別データテーブル"
    ])

    with ward_table_tab:
        create_ward_table_section(df_filtered)

    with dept_table_tab:
        create_department_table_section(df_filtered)


def create_output_prediction_tab():
    """出力・予測タブのメイン関数（統一フィルター対応版）"""
    st.header("📄 出力・予測")

    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return

    df_original = st.session_state.get('df')
    if df_original is None or df_original.empty:
        st.error("分析対象のデータがありません。")
        return

    if get_unified_filter_config is None:
        st.error("統一フィルター機能が利用できません。unified_filters.py を確認してください。")
        return
    initialize_unified_filters(df_original)

    df_filtered = apply_unified_filters(df_original)
    filter_summary = get_unified_filter_summary()
    st.info(f"🔍 出力・予測期間: {filter_summary}")

    if df_filtered.empty:
        st.warning("選択されたフィルター条件にマッチするデータがありません。")
        return

    individual_pdf_tab, bulk_pdf_tab, prediction_tab = st.tabs([
        "📄 個別PDF出力",
        "📚 一括PDF出力",
        "🔮 予測分析"
    ])

    with individual_pdf_tab:
        create_individual_pdf_section(df_filtered)

    with bulk_pdf_tab:
        create_bulk_pdf_section(df_filtered)

    with prediction_tab:
        create_prediction_analysis_section(df_filtered)

# ===============================================================================
# 詳細分析セクション（統一フィルター対応版）
# ===============================================================================

def create_los_analysis_section(df_filtered, filter_config, common_config):
    """平均在院日数分析セクション（統一フィルター対応版）"""
    st.subheader("📊 平均在院日数分析")

    if display_alos_analysis_tab:
        try:
            start_date = filter_config.get('start_date')
            end_date = filter_config.get('end_date')

            if start_date is None or end_date is None:
                st.error("期間設定がフィルター設定に含まれていません。")
                logger.error("LOS分析: filter_configからstart_dateまたはend_dateが取得できませんでした。")
                return

            if not isinstance(start_date, pd.Timestamp):
                start_date = pd.Timestamp(start_date)
            if not isinstance(end_date, pd.Timestamp):
                end_date = pd.Timestamp(end_date)

            display_alos_analysis_tab(df_filtered, start_date, end_date, common_config)

        except Exception as e:
            logger.error(f"平均在院日数分析でエラー: {e}", exc_info=True)
            st.error(f"平均在院日数分析でエラーが発生しました: {e}")
            st.info("詳細なエラー情報はログを確認してください。")
    else:
        st.warning("平均在院日数分析機能が利用できません。alos_analysis_tab.pyを確認してください。")
        create_fallback_los_analysis(df_filtered, filter_config)

def create_weekday_analysis_section(df_filtered, filter_config, common_config):
    """曜日別分析セクション（統一フィルター対応版）"""
    st.subheader("📅 曜日別入退院分析")

    if display_dow_analysis_tab:
        try:
            start_date = filter_config.get('start_date')
            end_date = filter_config.get('end_date')

            if start_date is None or end_date is None:
                st.error("期間設定がフィルター設定に含まれていません。")
                logger.error("曜日別分析: filter_configからstart_dateまたはend_dateが取得できませんでした。")
                return

            if not isinstance(start_date, pd.Timestamp):
                start_date = pd.Timestamp(start_date)
            if not isinstance(end_date, pd.Timestamp):
                end_date = pd.Timestamp(end_date)

            display_dow_analysis_tab(df_filtered, start_date, end_date, common_config)
        except Exception as e:
            logger.error(f"曜日別分析でエラー: {e}", exc_info=True)
            st.error(f"曜日別分析でエラーが発生しました: {e}")
            st.info("詳細なエラー情報はログを確認してください。")
    else:
        st.warning("曜日別分析機能が利用できません。dow_analysis_tab.pyを確認してください。")
        create_fallback_dow_analysis(df_filtered, filter_config)

def create_individual_analysis_section(df_filtered, filter_config_from_caller):
    """個別分析セクション（統一フィルター対応版）"""
    st.subheader("🔍 個別分析")

    if display_individual_analysis_tab:
        original_df_in_session = st.session_state.get('df')
        original_all_results = st.session_state.get('all_results') # 元のall_resultsを保持
        original_latest_date_str = st.session_state.get('latest_data_date_str') # 元のlatest_data_date_strを保持


        # フィルター済みデータに基づいて all_results を生成/設定
        if generate_filtered_summaries and df_filtered is not None and not df_filtered.empty:
            st.session_state.all_results = generate_filtered_summaries(df_filtered, None, None)
        else:
            st.session_state.all_results = None

        # フィルター済みデータに基づいて latest_data_date_str を設定
        if df_filtered is not None and not df_filtered.empty and '日付' in df_filtered.columns:
            st.session_state.latest_data_date_str = df_filtered['日付'].max().strftime("%Y年%m月%d日")
        elif original_latest_date_str: # フォールバックとして元の値
             st.session_state.latest_data_date_str = original_latest_date_str
        else: # それもなければ現在時刻
            st.session_state.latest_data_date_str = pd.Timestamp.now().strftime("%Y年%m月%d日")


        st.session_state['df'] = df_filtered
        st.session_state['unified_filter_applied'] = True
        # filter_config_from_caller は individual_analysis_tab.py が get_unified_filter_config() で取得するため、
        # ここでセッションに 'current_filter_config' として保存する必要はない。
        # get_unified_filter_config() が正しく filter_config_from_caller (または同等のもの) を返すように
        # unified_filters.py が st.session_state[self.config_key] に保存していることが前提。

        try:
            display_individual_analysis_tab()
        except Exception as e:
            logger.error(f"個別分析でエラー: {e}", exc_info=True)
            st.error(f"個別分析でエラーが発生しました: {e}")
            st.info("詳細なエラー情報はログを確認してください。")
        finally:
            st.session_state['df'] = original_df_in_session
            st.session_state['unified_filter_applied'] = False
            st.session_state['all_results'] = original_all_results # 元のall_resultsに戻す
            st.session_state['latest_data_date_str'] = original_latest_date_str # 元の日付文字列に戻す

    else:
        st.warning("個別分析機能が利用できません。individual_analysis_tab.pyを確認してください。")
        create_fallback_individual_analysis(df_filtered, filter_config_from_caller)

# ===============================================================================
# データテーブルセクション（統一フィルター対応版）
# ===============================================================================

def create_ward_table_section(df_filtered):
    """病棟別データテーブルセクション（統一フィルター対応版）"""
    st.subheader("🏥 病棟別データテーブル")
    
    try:
        if df_filtered.empty:
            st.warning("指定された期間にデータがありません。")
            return
        
        # 病棟マッピングの初期化
        from utils import initialize_all_mappings, get_ward_display_name
        initialize_all_mappings(df_filtered)
        ward_mapping = st.session_state.get('ward_mapping', {})
        
        # 期間情報の表示
        if '日付' in df_filtered.columns:
            min_date = df_filtered['日付'].min().date()
            max_date = df_filtered['日付'].max().date()
            st.info(f"データ期間: {min_date} ～ {max_date}")
        
        # 病棟別集計
        ward_summary = calculate_ward_summary(df_filtered)
        
        if not ward_summary.empty:
            # 病棟名列を追加
            ward_summary['病棟名'] = ward_summary['病棟コード'].apply(
                lambda x: get_ward_display_name(x, ward_mapping)
            )
            
            # 列の順序を調整（病棟名を病棟コードの後に配置）
            cols = ward_summary.columns.tolist()
            if '病棟名' in cols:
                # 病棟コードの後に病棟名を配置
                code_idx = cols.index('病棟コード')
                cols.insert(code_idx + 1, cols.pop(cols.index('病棟名')))
                ward_summary = ward_summary[cols]
            
            # テーブル表示と処理
            display_ward_table_with_filters(ward_summary, df_filtered)
            
            # 病棟別グラフ
            create_ward_comparison_charts(ward_summary)
        else:
            st.warning("病棟別集計データを作成できませんでした。")
            
    except Exception as e:
        logger.error(f"病棟別テーブル作成エラー: {e}")
        st.error(f"病棟別テーブル作成中にエラーが発生しました: {e}")

def create_department_table_section(df_filtered):
    """診療科別データテーブルセクション（統一フィルター対応版）"""
    st.subheader("🩺 診療科別データテーブル")
    
    try:
        if df_filtered.empty:
            st.warning("指定された期間にデータがありません。")
            return
        
        # 期間情報の表示
        if '日付' in df_filtered.columns:
            min_date = df_filtered['日付'].min().date()
            max_date = df_filtered['日付'].max().date()
            st.info(f"データ期間: {min_date} ～ {max_date}")
        
        # 診療科別集計
        dept_summary = calculate_department_summary(df_filtered)
        
        if not dept_summary.empty:
            # 診療科名の表示名変換
            if get_display_name_for_dept:
                dept_summary['診療科表示名'] = dept_summary['診療科名'].apply(
                    lambda x: get_display_name_for_dept(x, default_name=x)
                )
                # 表示用に列の順序を調整
                cols = dept_summary.columns.tolist()
                if '診療科表示名' in cols:
                    cols.insert(1, cols.pop(cols.index('診療科表示名')))
                    dept_summary = dept_summary[cols]
            
            # テーブル表示と処理
            display_department_table_with_filters(dept_summary, df_filtered)
            
            # 診療科別グラフ
            create_department_comparison_charts(dept_summary)
        else:
            st.warning("診療科別集計データを作成できませんでした。")
            
    except Exception as e:
        logger.error(f"診療科別テーブル作成エラー: {e}")
        st.error(f"診療科別テーブル作成中にエラーが発生しました: {e}")

# ===============================================================================
# テーブル表示ヘルパー関数
# ===============================================================================

def display_ward_table_with_filters(ward_summary, df_filtered):
    """病棟テーブルの表示とフィルタリング処理"""
    # フィルタリングオプション
    col1, col2 = st.columns(2)
    with col1:
        # 選択肢を「コード（名前）」形式で表示
        ward_display_options = []
        for _, row in ward_summary.iterrows():
            code = row['病棟コード']
            name = row['病棟名']
            if name != str(code):
                display_option = f"{code}（{name}）"
            else:
                display_option = str(code)
            ward_display_options.append(display_option)
        
        selected_wards = st.multiselect(
            "表示する病棟を選択（空白の場合は全て表示）",
            options=ward_display_options,
            key="ward_table_filter"
        )
    
    with col2:
        sort_column = st.selectbox(
            "並び替え基準",
            options=['病棟コード', '平均在院患者数', '総入院患者数', '総退院患者数', '平均在院日数'],
            key="ward_table_sort"
        )
    
    # データフィルタリングと並び替え
    display_summary = ward_summary.copy()
    if selected_wards:
        # 選択された表示名から病棟コードを抽出
        selected_codes = []
        for display_ward in selected_wards:
            # 「コード（名前）」形式から病棟コードを抽出
            if '（' in display_ward:
                code = display_ward.split('（')[0]
            else:
                code = display_ward
            selected_codes.append(code)
        display_summary = display_summary[display_summary['病棟コード'].isin(selected_codes)]
    
    if sort_column in display_summary.columns:
        ascending = st.checkbox("昇順で並び替え", key="ward_table_ascending")
        display_summary = display_summary.sort_values(sort_column, ascending=ascending)
    
    # フォーマット適用とテーブル表示
    format_dict = create_table_format_dict(display_summary)
    st.dataframe(
        display_summary.style.format(format_dict),
        use_container_width=True,
        height=400
    )
    
    # CSVダウンロード
    create_csv_download_button(display_summary, df_filtered, "病棟別データ")

def display_department_table_with_filters(dept_summary, df_filtered):
    """診療科テーブルの表示とフィルタリング処理"""
    # フィルタリングオプション
    col1, col2 = st.columns(2)
    with col1:
        selected_depts = st.multiselect(
            "表示する診療科を選択（空白の場合は全て表示）",
            options=sorted(dept_summary['診療科名'].unique()),
            key="dept_table_filter"
        )
    
    with col2:
        sort_column = st.selectbox(
            "並び替え基準",
            options=['診療科名', '平均在院患者数', '総入院患者数', '総退院患者数', '平均在院日数'],
            key="dept_table_sort"
        )
    
    # データフィルタリングと並び替え
    display_summary = dept_summary.copy()
    if selected_depts:
        display_summary = display_summary[display_summary['診療科名'].isin(selected_depts)]
    
    if sort_column in display_summary.columns:
        ascending = st.checkbox("昇順で並び替え", key="dept_table_ascending")
        display_summary = display_summary.sort_values(sort_column, ascending=ascending)
    
    # フォーマット適用とテーブル表示
    format_dict = create_table_format_dict(display_summary)
    st.dataframe(
        display_summary.style.format(format_dict),
        use_container_width=True,
        height=400
    )
    
    # CSVダウンロード
    create_csv_download_button(display_summary, df_filtered, "診療科別データ")

def create_table_format_dict(summary_df):
    """テーブル表示用フォーマット辞書の作成"""
    format_dict = {}
    
    for col in summary_df.columns:
        if col in ['病棟コード', '診療科名', '診療科表示名', '病棟名', '集計単位']:
            # 文字列列はそのまま
            continue
        elif col in ['期間日数', '延べ在院患者数', '総入院患者数', '総退院患者数', 
                   '緊急入院患者数', '死亡患者数']:
            # 整数値として表示（合計値・カウント数）
            format_dict[col] = "{:.0f}"
        elif col in ['平均在院患者数']:
            # 小数点1桁で表示（平均値）
            format_dict[col] = "{:.1f}"
        elif col in ['平均在院日数', '病床回転率']:
            # 小数点1桁で表示（比率・日数）
            format_dict[col] = "{:.1f}"
        elif col in ['緊急入院率', '死亡率']:
            # パーセンテージは小数点1桁 + %
            format_dict[col] = "{:.1f}%"
        else:
            # その他の数値列は小数点1桁
            if pd.api.types.is_numeric_dtype(summary_df[col]):
                # 整数かどうかを判定
                if summary_df[col].dtype in ['int64', 'int32', 'Int64', 'Int32']:
                    format_dict[col] = "{:.0f}"
                else:
                    # 平均値かどうかを名前から判定
                    if '平均' in col or '率' in col or '日数' in col:
                        format_dict[col] = "{:.1f}"
                    else:
                        format_dict[col] = "{:.0f}"
    
    return format_dict

def create_csv_download_button(summary_df, df_filtered, data_type):
    """CSVダウンロードボタンの作成"""
    csv_data = summary_df.to_csv(index=False).encode('utf-8-sig')
    
    # 期間文字列の生成
    if '日付' in df_filtered.columns:
        min_date = df_filtered['日付'].min().date()
        max_date = df_filtered['日付'].max().date()
        period_str = f"{min_date}_{max_date}"
    else:
        period_str = "全期間"
    
    st.download_button(
        label=f"{data_type}をCSVダウンロード",
        data=csv_data,
        file_name=f"{data_type}_{period_str}.csv",
        mime="text/csv"
    )

# ===============================================================================
# 集計処理関数（既存関数をそのまま使用）
# ===============================================================================

def calculate_ward_summary(df):
    """病棟別サマリーデータの計算"""
    try:
        available_columns = df.columns.tolist()
        column_mapping = {
            '在院患者数': ['入院患者数（在院）', '在院患者数', '現在患者数'],
            '入院患者数': ['総入院患者数', '入院患者数', '新規入院患者数'],
            '退院患者数': ['総退院患者数', '退院患者数', '退院者数'],
            '緊急入院患者数': ['緊急入院患者数', '救急入院患者数', '緊急入院'],
            '死亡患者数': ['死亡患者数', '死亡者数', '死亡']
        }
        actual_columns = {}
        missing_columns = []
        
        for standard_name, possible_names in column_mapping.items():
            found_column = next((pn for pn in possible_names if pn in available_columns), None)
            if found_column:
                actual_columns[standard_name] = found_column
            else:
                missing_columns.append(standard_name)
        
        if missing_columns:
            # st.error は呼び出し元で行うか、エラー状態を返すようにする
            logger.error(f"病棟別集計に必要な列が見つかりません: {missing_columns}")
            return pd.DataFrame() # 空のDataFrameを返す
        
        ward_groups = df.groupby('病棟コード', observed=True)
        ward_summary_data = {
            '病棟コード': ward_groups['病棟コード'].first(),
            '期間日数': ward_groups['日付'].nunique(),
        }
        for standard_name, actual_col_name in actual_columns.items():
            # Ensure the column exists before trying to sum it, even if mapped
            if actual_col_name in df.columns:
                 # Standardize the output column name using the sum of the actual column name
                if standard_name == '在院患者数':
                    ward_summary_data['延べ在院患者数'] = ward_groups[actual_col_name].sum()
                elif standard_name == '入院患者数':
                     ward_summary_data['総入院患者数'] = ward_groups[actual_col_name].sum()
                elif standard_name == '退院患者数':
                     ward_summary_data['総退院患者数'] = ward_groups[actual_col_name].sum()
                elif standard_name == '緊急入院患者数':
                     ward_summary_data['緊急入院患者数'] = ward_groups[actual_col_name].sum()
                elif standard_name == '死亡患者数':
                     ward_summary_data['死亡患者数'] = ward_groups[actual_col_name].sum()

            else:
                # This case should ideally not be reached if missing_columns check is robust
                logger.warning(f"病棟別集計: 列 '{actual_col_name}' (対応する標準名: '{standard_name}') がデータに存在しません。集計から除外します。")


        ward_summary = pd.DataFrame(ward_summary_data).reset_index(drop=True)

        # Check if all necessary sum columns were created before proceeding
        required_sum_cols = ['延べ在院患者数', '総入院患者数', '総退院患者数', '緊急入院患者数', '死亡患者数']
        if not all(col in ward_summary.columns for col in required_sum_cols):
            logger.error(f"病棟別サマリー計算に必要な集計列が不足しています。生成された列: {list(ward_summary.columns)}")
            return pd.DataFrame()

        ward_summary['平均在院患者数'] = ward_summary['延べ在院患者数'] / ward_summary['期間日数']
        ward_summary['平均在院日数'] = ward_summary.apply(
            lambda row: row['延べ在院患者数'] / ((row['総入院患者数'] + row['総退院患者数']) / 2)
            if (row['総入院患者数'] + row['総退院患者数']) > 0 else 0,
            axis=1
        )
        ward_summary['病床回転率'] = ward_summary.apply(
            lambda row: row['総退院患者数'] / row['平均在院患者数'] 
            if row['平均在院患者数'] > 0 else 0,
            axis=1
        )
        ward_summary['緊急入院率'] = ward_summary.apply(
            lambda row: (row['緊急入院患者数'] / row['総入院患者数'] * 100)
            if row['総入院患者数'] > 0 else 0,
            axis=1
        )
        ward_summary['死亡率'] = ward_summary.apply(
            lambda row: (row['死亡患者数'] / row['総退院患者数'] * 100)
            if row['総退院患者数'] > 0 else 0,
            axis=1
        )
        return ward_summary
        
    except Exception as e:
        logger.error(f"病棟別サマリー計算エラー: {e}", exc_info=True)
        # st.error(f"病棟別サマリー計算中にエラー: {e}") # UIエラーは呼び出し元で
        return pd.DataFrame()

def calculate_department_summary(df):
    """診療科別サマリーデータの計算"""
    try:
        available_columns = df.columns.tolist()
        column_mapping = {
            '在院患者数': ['入院患者数（在院）', '在院患者数', '現在患者数'],
            '入院患者数': ['総入院患者数', '入院患者数', '新規入院患者数'],
            '退院患者数': ['総退院患者数', '退院患者数', '退院者数'],
            '緊急入院患者数': ['緊急入院患者数', '救急入院患者数', '緊急入院'],
            '死亡患者数': ['死亡患者数', '死亡者数', '死亡']
        }
        actual_columns = {}
        missing_columns = []

        for standard_name, possible_names in column_mapping.items():
            found_column = next((pn for pn in possible_names if pn in available_columns), None)
            if found_column:
                actual_columns[standard_name] = found_column
            else:
                missing_columns.append(standard_name)
        
        if missing_columns:
            logger.error(f"診療科別集計に必要な列が見つかりません: {missing_columns}")
            return pd.DataFrame()
        
        dept_groups = df.groupby('診療科名', observed=True)
        dept_summary_data = {
            '診療科名': dept_groups['診療科名'].first(),
            '期間日数': dept_groups['日付'].nunique(),
        }

        for standard_name, actual_col_name in actual_columns.items():
            if actual_col_name in df.columns:
                if standard_name == '在院患者数':
                    dept_summary_data['延べ在院患者数'] = dept_groups[actual_col_name].sum()
                elif standard_name == '入院患者数':
                    dept_summary_data['総入院患者数'] = dept_groups[actual_col_name].sum()
                elif standard_name == '退院患者数':
                    dept_summary_data['総退院患者数'] = dept_groups[actual_col_name].sum()
                elif standard_name == '緊急入院患者数':
                    dept_summary_data['緊急入院患者数'] = dept_groups[actual_col_name].sum()
                elif standard_name == '死亡患者数':
                    dept_summary_data['死亡患者数'] = dept_groups[actual_col_name].sum()
            else:
                logger.warning(f"診療科別集計: 列 '{actual_col_name}' (対応する標準名: '{standard_name}') がデータに存在しません。集計から除外します。")


        dept_summary = pd.DataFrame(dept_summary_data).reset_index(drop=True)

        required_sum_cols = ['延べ在院患者数', '総入院患者数', '総退院患者数', '緊急入院患者数', '死亡患者数']
        if not all(col in dept_summary.columns for col in required_sum_cols):
            logger.error(f"診療科別サマリー計算に必要な集計列が不足しています。生成された列: {list(dept_summary.columns)}")
            return pd.DataFrame()

        dept_summary['平均在院患者数'] = dept_summary['延べ在院患者数'] / dept_summary['期間日数']
        dept_summary['平均在院日数'] = dept_summary.apply(
            lambda row: row['延べ在院患者数'] / ((row['総入院患者数'] + row['総退院患者数']) / 2)
            if (row['総入院患者数'] + row['総退院患者数']) > 0 else 0,
            axis=1
        )
        dept_summary['病床回転率'] = dept_summary.apply(
            lambda row: row['総退院患者数'] / row['平均在院患者数'] 
            if row['平均在院患者数'] > 0 else 0,
            axis=1
        )
        dept_summary['緊急入院率'] = dept_summary.apply(
            lambda row: (row['緊急入院患者数'] / row['総入院患者数'] * 100)
            if row['総入院患者数'] > 0 else 0,
            axis=1
        )
        dept_summary['死亡率'] = dept_summary.apply(
            lambda row: (row['死亡患者数'] / row['総退院患者数'] * 100)
            if row['総退院患者数'] > 0 else 0,
            axis=1
        )
        return dept_summary
        
    except Exception as e:
        logger.error(f"診療科別サマリー計算エラー: {e}", exc_info=True)
        # st.error(f"診療科別サマリー計算中にエラー: {e}") # UIエラーは呼び出し元で
        return pd.DataFrame()

# ===============================================================================
# グラフ作成関数（既存関数をそのまま使用）
# ===============================================================================

def create_ward_comparison_charts(ward_summary):
    """病棟別比較チャートの作成"""
    try:
        st.markdown("---")
        st.subheader("病棟別比較グラフ")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 平均在院患者数の比較
            fig_census = px.bar(
                ward_summary,
                x='病棟コード',
                y='平均在院患者数',
                title='病棟別 平均在院患者数',
                color='平均在院患者数',
                color_continuous_scale='Blues'
            )
            fig_census.update_layout(height=400)
            st.plotly_chart(fig_census, use_container_width=True)
        
        with col2:
            # 平均在院日数の比較
            fig_alos = px.bar(
                ward_summary,
                x='病棟コード',
                y='平均在院日数',
                title='病棟別 平均在院日数',
                color='平均在院日数',
                color_continuous_scale='Reds'
            )
            fig_alos.update_layout(height=400)
            st.plotly_chart(fig_alos, use_container_width=True)
        
        # 散布図による相関分析
        fig_scatter = px.scatter(
            ward_summary,
            x='平均在院患者数',
            y='平均在院日数',
            size='総入院患者数',
            hover_name='病棟コード',
            title='平均在院患者数 vs 平均在院日数（バブルサイズ：総入院患者数）',
            labels={'平均在院患者数': '平均在院患者数（人）', '平均在院日数': '平均在院日数（日）'}
        )
        fig_scatter.update_layout(height=400)
        st.plotly_chart(fig_scatter, use_container_width=True)
        
    except Exception as e:
        logger.error(f"病棟別グラフ作成エラー: {e}")
        st.error(f"病棟別グラフ作成中にエラー: {e}")

def create_department_comparison_charts(dept_summary):
    """診療科別比較チャートの作成"""
    try:
        st.markdown("---")
        st.subheader("診療科別比較グラフ")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 平均在院患者数の比較（上位10位）
            top_census = dept_summary.nlargest(10, '平均在院患者数')
            fig_census = px.bar(
                top_census,
                x='平均在院患者数',
                y='診療科名',
                orientation='h',
                title='診療科別 平均在院患者数（上位10位）',
                color='平均在院患者数',
                color_continuous_scale='Blues'
            )
            fig_census.update_layout(height=400)
            st.plotly_chart(fig_census, use_container_width=True)
        
        with col2:
            # 平均在院日数の比較（上位10位）
            top_alos = dept_summary.nlargest(10, '平均在院日数')
            fig_alos = px.bar(
                top_alos,
                x='平均在院日数',
                y='診療科名',
                orientation='h',
                title='診療科別 平均在院日数（上位10位）',
                color='平均在院日数',
                color_continuous_scale='Reds'
            )
            fig_alos.update_layout(height=400)
            st.plotly_chart(fig_alos, use_container_width=True)
        
        # 緊急入院率と死亡率の散布図
        fig_rates = px.scatter(
            dept_summary,
            x='緊急入院率',
            y='死亡率',
            size='総入院患者数',
            hover_name='診療科名',
            title='緊急入院率 vs 死亡率（バブルサイズ：総入院患者数）',
            labels={'緊急入院率': '緊急入院率（%）', '死亡率': '死亡率（%）'}
        )
        fig_rates.update_layout(height=400)
        st.plotly_chart(fig_rates, use_container_width=True)
        
    except Exception as e:
        logger.error(f"診療科別グラフ作成エラー: {e}")
        st.error(f"診療科別グラフ作成中にエラー: {e}")

# ===============================================================================
# 出力・予測セクション（統一フィルター対応版）
# ===============================================================================

def create_individual_pdf_section(df_filtered):
    """個別PDF出力セクション（統一フィルター対応版）"""
    st.subheader("📄 個別PDF出力")
    
    target_data = st.session_state.get('target_data')
    
    try:
        # PDF出力設定
        col1, col2 = st.columns(2)
        
        with col1:
            output_type = st.selectbox(
                "出力単位",
                ["全体", "診療科別", "病棟別"],
                key="pdf_output_type"
            )
        
        with col2:
            pdf_orientation = st.selectbox(
                "PDF向き",
                ["縦向き", "横向き"],
                key="pdf_orientation"
            )
        
        # 対象選択
        target_items = []
        if output_type == "診療科別":
            available_depts = sorted(df_filtered['診療科名'].unique())
            target_items = st.multiselect(
                "出力対象診療科",
                available_depts,
                default=available_depts[:3] if len(available_depts) >= 3 else available_depts,
                key="pdf_target_depts"
            )
        elif output_type == "病棟別":
            available_wards = sorted(df_filtered['病棟コード'].unique())
            target_items = st.multiselect(
                "出力対象病棟",
                available_wards,
                default=available_wards[:3] if len(available_wards) >= 3 else available_wards,
                key="pdf_target_wards"
            )
        
        # グラフ表示期間
        graph_days = st.slider(
            "グラフ表示期間（日数）",
            min_value=30,
            max_value=365,
            value=90,
            step=30,
            key="pdf_graph_days"
        )
        
        # PDF生成ボタン
        if st.button("PDF生成", key="generate_individual_pdf"):
            if output_type != "全体" and not target_items:
                st.warning("出力対象を選択してください。")
            else:
                generate_individual_pdfs(
                    df_filtered, target_data, output_type, target_items, 
                    pdf_orientation, graph_days
                )
    
    except Exception as e:
        logger.error(f"個別PDF出力設定エラー: {e}")
        st.error(f"個別PDF出力設定中にエラーが発生しました: {e}")

def create_bulk_pdf_section(df_filtered):
    """一括PDF出力セクション（統一フィルター対応版）"""
    st.subheader("📚 一括PDF出力")
    
    filter_summary = get_unified_filter_summary()
    st.info(f"📚 一括PDF対象: {filter_summary}")
    st.info("一括PDF出力機能により、フィルター条件に該当する全診療科または全病棟のPDFレポートを一度に生成できます。")

def create_prediction_analysis_section(df_filtered):
    """予測分析セクション（統一フィルター対応版）"""
    st.subheader("🔮 予測分析")
    
    if display_forecast_analysis_tab:
        try:
            # フィルタリング済みデータで予測分析を実行
            original_df = st.session_state.get('df')
            st.session_state['df'] = df_filtered
            
            display_forecast_analysis_tab()
            
            st.session_state['df'] = original_df
        except Exception as e:
            logger.error(f"予測分析エラー: {e}")
            st.error(f"予測分析でエラーが発生しました: {e}")
            st.info("詳細なエラー情報はログを確認してください。")
        finally:
            if 'original_df' in locals():
                st.session_state['df'] = original_df
    else:
        st.warning("予測分析機能が利用できません。forecast_analysis_tab.pyを確認してください。")
        create_fallback_prediction_analysis(df_filtered)

# ===============================================================================
# PDF生成関数（シンプル版）
# ===============================================================================

def generate_individual_pdfs(df, target_data, output_type, target_items, orientation, graph_days):
    """個別PDF生成処理（シンプル版）"""
    try:
        if not create_pdf:
            st.error("PDF生成機能が利用できません。")
            return
        
        filter_summary = get_unified_filter_summary()
        st.info(f"PDF生成対象: {filter_summary}")
        st.info("PDF生成機能は実装中です。")
        
    except Exception as e:
        logger.error(f"PDF生成エラー: {e}")
        st.error(f"PDF生成中にエラーが発生しました: {e}")

# ===============================================================================
# フォールバック関数群（統一フィルター対応版）
# ===============================================================================

def create_fallback_los_analysis(df_filtered, filter_config):
    """平均在院日数分析のフォールバック版（統一フィルター対応版）"""
    st.info("🔧 平均在院日数分析の主要機能が利用できないため、簡易版を表示します。")
    
    try:
        if df_filtered.empty:
            st.warning("フィルター条件にマッチするデータがありません。")
            return
        
        filter_summary = get_unified_filter_summary()
        st.info(f"分析対象: {filter_summary}")
        
        available_columns = df_filtered.columns.tolist()
        column_mapping = {
            '在院患者数': ['入院患者数（在院）', '在院患者数', '現在患者数'],
            '入院患者数': ['総入院患者数', '入院患者数', '新規入院患者数'],
            '退院患者数': ['総退院患者数', '退院患者数', '退院者数']
        }
        actual_columns = {}
        missing_required = False
        for standard_name, possible_names in column_mapping.items():
            found_column = next((pn for pn in possible_names if pn in available_columns), None)
            if found_column:
                actual_columns[standard_name] = found_column
            elif standard_name in ['在院患者数', '入院患者数', '退院患者数']: # これらは必須
                missing_required = True
                st.error(f"平均在院日数計算に必要な主要列 '{standard_name}' (またはそのエイリアス) がありません。")
                logger.error(f"フォールバックLOS: 必須列 '{standard_name}' が欠落。")
        
        if missing_required:
            return

        total_patient_days = df_filtered[actual_columns['在院患者数']].sum() if '在院患者数' in actual_columns else 0
        total_admissions = df_filtered[actual_columns['入院患者数']].sum() if '入院患者数' in actual_columns else 0
        total_discharges = df_filtered[actual_columns['退院患者数']].sum() if '退院患者数' in actual_columns else 0
        
        if (total_admissions + total_discharges) > 0:
            alos = total_patient_days / ((total_admissions + total_discharges) / 2)
            st.metric("期間全体の平均在院日数", f"{alos:.2f}日")
        else:
            st.metric("期間全体の平均在院日数", "計算不可 (入退院なし)")
        
        # 日別トレンド (より安全に)
        if '日付' in df_filtered.columns and '在院患者数' in actual_columns:
            daily_agg_dict = {actual_columns['在院患者数']: 'sum'}
            if '入院患者数' in actual_columns:
                daily_agg_dict[actual_columns['入院患者数']] = 'sum'
            if '退院患者数' in actual_columns:
                daily_agg_dict[actual_columns['退院患者数']] = 'sum'

            daily_alos = df_filtered.groupby('日付', observed=True).agg(daily_agg_dict).reset_index()
            
            # Rename to standard names for calculation
            rename_map = {v: k for k, v in actual_columns.items() if k in ['在院患者数', '入院患者数', '退院患者数']}
            daily_alos = daily_alos.rename(columns=rename_map)

            if '在院患者数' in daily_alos.columns and '入院患者数' in daily_alos.columns and '退院患者数' in daily_alos.columns:
                daily_alos['日別平均在院日数'] = daily_alos.apply(
                    lambda row: row['在院患者数'] / ((row['入院患者数'] + row['退院患者数']) / 2)
                    if (row['入院患者数'] + row['退院患者数']) > 0 else np.nan, # np.nan for plotting
                    axis=1
                )
                
                fig = px.line(
                    daily_alos.dropna(subset=['日別平均在院日数']), # Drop NaN for cleaner plot
                    x='日付',
                    y='日別平均在院日数',
                    title=f'日別平均在院日数推移（フィルター適用済み）'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("日別平均在院日数の計算に必要なデータが不足しています。")
        else:
            st.warning("日別トレンド表示に必要な日付または在院患者数データがありません。")
            
    except Exception as e:
        logger.error(f"フォールバック版平均在院日数分析エラー: {e}", exc_info=True)
        st.error(f"フォールバック版平均在院日数分析でエラーが発生しました。")

def create_fallback_dow_analysis(df_filtered, filter_config):
    """曜日別分析のフォールバック版（統一フィルター対応版）"""
    st.info("簡易版の曜日別分析を表示しています。")
    
    try:
        if df_filtered.empty:
            st.warning("フィルター条件にマッチするデータがありません。")
            return
        
        # 基本統計の表示
        filter_summary = get_unified_filter_summary()
        st.info(f"分析対象: {filter_summary}")
        
        # 曜日の追加
        df_copy = df_filtered.copy()
        df_copy['曜日'] = df_copy['日付'].dt.day_name()
        df_copy['曜日番号'] = df_copy['日付'].dt.dayofweek
        
        # 利用可能な列の確認
        numeric_columns = df_copy.select_dtypes(include=[np.number]).columns
        patient_columns = [col for col in numeric_columns if '患者数' in col]
        
        if not patient_columns:
            st.error("患者数データが見つかりません。")
            return
        
        # 曜日別集計
        agg_dict = {col: 'mean' for col in patient_columns}
        dow_summary = df_copy.groupby(['曜日', '曜日番号'], observed=True).agg(agg_dict).reset_index()
        dow_summary = dow_summary.sort_values('曜日番号')
        
        # グラフ表示
        fig = px.bar(
            dow_summary,
            x='曜日',
            y=patient_columns[:3],  # 最大3つまで表示
            title=f'曜日別平均患者数（フィルター適用済み）',
            barmode='group'
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # テーブル表示
        st.dataframe(dow_summary, use_container_width=True)
        
    except Exception as e:
        logger.error(f"フォールバック版曜日別分析エラー: {e}")
        st.error(f"フォールバック版曜日別分析でエラー: {e}")

def create_fallback_individual_analysis(df_filtered, filter_config):
    """個別分析のフォールバック版（統一フィルター対応版）"""
    st.info("個別分析機能が利用できません。")
    filter_summary = get_unified_filter_summary()
    st.info(f"分析対象: {filter_summary}")
    st.write("individual_analysis_tab.pyモジュールを確認してください。")

def create_fallback_prediction_analysis(df_filtered):
    """予測分析のフォールバック版（統一フィルター対応版）"""
    st.info("予測分析機能が利用できません。")
    filter_summary = get_unified_filter_summary()
    st.info(f"分析対象: {filter_summary}")
    st.write("forecast_analysis_tab.pyモジュールを確認してください。")