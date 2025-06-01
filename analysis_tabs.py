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
import traceback # NameError 解消のため追加

# 統一フィルター関連のインポート
from unified_filters import (
    # create_unified_filter_sidebar, # app.py で呼び出すのでここでは不要
    apply_unified_filters,
    get_unified_filter_summary,
    initialize_unified_filters, # app.py で呼び出すのでここでは不要
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
    # get_unified_filter_config は上でインポート済み

logger = logging.getLogger(__name__)

# ===============================================================================
# メイン関数群（統一フィルター対応版）
# ===============================================================================
def create_detailed_analysis_tab():
    """
    詳細分析タブのメイン関数（役割変更により内容は空または削除予定）
    この関数は app.py からは呼び出されなくなります。
    各分析機能 (ALOS, DOW, Individual) は app.py から直接タブとして呼び出されます。
    """
    # st.header("📈 詳細分析 (旧)")
    # st.info("このタブの各機能はトップレベルのタブに移動しました。")
    # この関数は呼び出されないようにするか、完全に削除することを推奨します。
    # ここでは、もし誤って呼び出された場合のためにメッセージを残します。
    pass

def create_data_tables_tab(): # この関数は「データ出力」タブ内で使用
    """データテーブルタブのメイン関数（統一フィルター対応版）"""
    # st.header("📋 データテーブル") # ヘッダーは「データ出力」タブ側で管理

    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ入力」タブでデータを読み込んでください。") # 名称変更を反映
        return

    df_original = st.session_state.get('df')
    if df_original is None or df_original.empty:
        st.error("分析対象のデータがありません。")
        return

    if get_unified_filter_config is None:
        st.error("統一フィルター機能が利用できません。unified_filters.py を確認してください。")
        return
    # initialize_unified_filters(df_original) # app.pyで実行

    current_filter_config = get_unified_filter_config() # 現在のフィルター設定を取得

    df_filtered = apply_unified_filters(df_original)
    filter_summary = get_unified_filter_summary()
    st.info(f"🔍 統一フィルター適用中: {filter_summary}")

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


# create_output_prediction_tab は「データ出力」と「予測分析」に分割されるため、
# この関数自体は不要になる。PDF出力は create_pdf_output_tab (pdf_output_tab.py)
# 予測分析は display_forecast_analysis_tab (forecast_analysis_tab.py)

# ===============================================================================
# 詳細分析セクションの個別関数は app.py から直接呼び出されるため、
# analysis_tabs.py 内での create_los_analysis_section, create_weekday_analysis_section,
# create_individual_analysis_section は不要になります。
# 各 ~_tab.py ファイルの display_..._tab 関数が直接使われます。
# ===============================================================================

# ... (calculate_ward_summary, calculate_department_summary などのヘルパー関数は残す) ...
# (display_ward_table_with_filters, display_department_table_with_filters, create_table_format_dict, create_csv_download_button)
# (create_ward_comparison_charts, create_department_comparison_charts)
# (generate_individual_pdfs, create_fallback_... 関数群は、それぞれの機能が app.py から直接呼び出されるか、
#  各専用タブモジュール内に実装されるため、このファイルからは削除または移動を検討)

# このファイルは主に create_data_tables_tab とそのヘルパー関数に特化する形になります。
# 以下、データテーブルタブ関連の関数は残します。

def create_ward_table_section(df_filtered):
    """病棟別データテーブルセクション（統一フィルター対応版）"""
    st.subheader("🏥 病棟別データテーブル")
    # ... (既存のコード)
    try:
        if df_filtered.empty:
            st.warning("指定された期間にデータがありません。")
            return
        from utils import initialize_all_mappings, get_ward_display_name
        initialize_all_mappings(df_filtered, st.session_state.get('target_data')) # target_dataも渡す
        ward_mapping = st.session_state.get('ward_mapping', {})
        if '日付' in df_filtered.columns and not df_filtered['日付'].empty: # 空チェック追加
            min_date = df_filtered['日付'].min().date()
            max_date = df_filtered['日付'].max().date()
            st.info(f"データ期間: {min_date} ～ {max_date}")
        ward_summary = calculate_ward_summary(df_filtered)
        if not ward_summary.empty:
            ward_summary['病棟名'] = ward_summary['病棟コード'].apply(
                lambda x: get_ward_display_name(x, ward_mapping)
            )
            cols = ward_summary.columns.tolist()
            if '病棟名' in cols and '病棟コード' in cols: # 両方の列があるか確認
                code_idx = cols.index('病棟コード')
                cols.insert(code_idx + 1, cols.pop(cols.index('病棟名')))
                ward_summary = ward_summary[cols]
            display_ward_table_with_filters(ward_summary, df_filtered)
            create_ward_comparison_charts(ward_summary)
        else:
            st.warning("病棟別集計データを作成できませんでした。")
    except Exception as e:
        logger.error(f"病棟別テーブル作成エラー: {e}", exc_info=True) # exc_info追加
        st.error(f"病棟別テーブル作成中にエラーが発生しました: {e}")


def create_department_table_section(df_filtered):
    """診療科別データテーブルセクション（統一フィルター対応版）"""
    st.subheader("🩺 診療科別データテーブル")
    # ... (既存のコード)
    try:
        if df_filtered.empty:
            st.warning("指定された期間にデータがありません。")
            return
        if '日付' in df_filtered.columns and not df_filtered['日付'].empty: # 空チェック追加
            min_date = df_filtered['日付'].min().date()
            max_date = df_filtered['日付'].max().date()
            st.info(f"データ期間: {min_date} ～ {max_date}")
        dept_summary = calculate_department_summary(df_filtered)
        if not dept_summary.empty:
            if get_display_name_for_dept:
                dept_summary['診療科表示名'] = dept_summary['診療科名'].apply(
                    lambda x: get_display_name_for_dept(x, default_name=x)
                )
                cols = dept_summary.columns.tolist()
                if '診療科表示名' in cols and '診療科名' in cols: # 両方の列があるか確認
                    name_idx = cols.index('診療科名') # 診療科名の後に表示名
                    cols.insert(name_idx + 1, cols.pop(cols.index('診療科表示名')))
                    dept_summary = dept_summary[cols]
            display_department_table_with_filters(dept_summary, df_filtered)
            create_department_comparison_charts(dept_summary)
        else:
            st.warning("診療科別集計データを作成できませんでした。")
    except Exception as e:
        logger.error(f"診療科別テーブル作成エラー: {e}", exc_info=True) # exc_info追加
        st.error(f"診療科別テーブル作成中にエラーが発生しました: {e}")

# display_ward_table_with_filters, display_department_table_with_filters, 
# create_table_format_dict, create_csv_download_button,
# calculate_ward_summary, calculate_department_summary,
# create_ward_comparison_charts, create_department_comparison_charts は残す
# (create_data_tables_tab がこれらを使用するため)

# ただし、calculate_ward_summary と calculate_department_summary は、
# kpi_calculator.py や他の集計関数とロジックが重複している可能性が高いため、
# 将来的には kpi_calculator.py の関数を利用するように統合することを検討。

def display_ward_table_with_filters(ward_summary, df_filtered):
    # ... (既存のコード)
    col1, col2 = st.columns(2)
    with col1:
        ward_display_options = []
        if not ward_summary.empty: # 空でないか確認
            for _, row in ward_summary.iterrows():
                code = row['病棟コード']
                name = row['病棟名']
                display_option = f"{code}（{name}）" if name != str(code) else str(code)
                ward_display_options.append(display_option)
        selected_wards = st.multiselect(
            "表示する病棟を選択（空白の場合は全て表示）", options=ward_display_options, key="ward_table_filter_dt" # キー変更
        )
    with col2:
        sort_column = st.selectbox(
            "並び替え基準", options=['病棟コード', '平均在院患者数', '総入院患者数', '総退院患者数', '平均在院日数'], key="ward_table_sort_dt" # キー変更
        )
    display_summary = ward_summary.copy()
    if selected_wards:
        selected_codes = []
        for display_ward in selected_wards:
            code = display_ward.split('（')[0] if '（' in display_ward else display_ward
            selected_codes.append(code)
        display_summary = display_summary[display_summary['病棟コード'].isin(selected_codes)]
    if sort_column in display_summary.columns:
        ascending = st.checkbox("昇順で並び替え", key="ward_table_ascending_dt") # キー変更
        display_summary = display_summary.sort_values(sort_column, ascending=ascending)
    format_dict = create_table_format_dict(display_summary)
    st.dataframe(display_summary.style.format(format_dict, na_rep='-'), use_container_width=True, height=400) # na_rep追加
    create_csv_download_button(display_summary, df_filtered, "病棟別データ")

def display_department_table_with_filters(dept_summary, df_filtered):
    # ... (既存のコード)
    col1, col2 = st.columns(2)
    with col1:
        options_dept = sorted(dept_summary['診療科名'].unique()) if not dept_summary.empty and '診療科名' in dept_summary.columns else []
        selected_depts = st.multiselect(
            "表示する診療科を選択（空白の場合は全て表示）", options=options_dept, key="dept_table_filter_dt" # キー変更
        )
    with col2:
        sort_column = st.selectbox(
            "並び替え基準", options=['診療科名', '平均在院患者数', '総入院患者数', '総退院患者数', '平均在院日数'], key="dept_table_sort_dt" # キー変更
        )
    display_summary = dept_summary.copy()
    if selected_depts:
        display_summary = display_summary[display_summary['診療科名'].isin(selected_depts)]
    if sort_column in display_summary.columns:
        ascending = st.checkbox("昇順で並び替え", key="dept_table_ascending_dt") # キー変更
        display_summary = display_summary.sort_values(sort_column, ascending=ascending)
    format_dict = create_table_format_dict(display_summary)
    st.dataframe(display_summary.style.format(format_dict, na_rep='-'), use_container_width=True, height=400) # na_rep追加
    create_csv_download_button(display_summary, df_filtered, "診療科別データ")

def create_table_format_dict(summary_df):
    # ... (既存のコード)
    format_dict = {}
    if summary_df is None or summary_df.empty: return format_dict # 空チェック
    for col in summary_df.columns:
        if col in ['病棟コード', '診療科名', '診療科表示名', '病棟名', '集計単位']: continue
        elif col in ['期間日数', '延べ在院患者数', '総入院患者数', '総退院患者数', '緊急入院患者数', '死亡患者数']:
            format_dict[col] = "{:,.0f}" # カンマ区切り追加
        elif col in ['平均在院患者数', '平均在院日数', '病床回転率']:
            format_dict[col] = "{:,.1f}" # カンマ区切り追加
        elif col in ['緊急入院率', '死亡率', '在院患者数割合', '入院患者数割合', '退院患者数割合']: # 割合系カラム追加
            format_dict[col] = "{:.1f}%"
        else:
            if pd.api.types.is_numeric_dtype(summary_df[col]):
                if summary_df[col].dtype in ['int64', 'int32', 'Int64', 'Int32'] or (summary_df[col].dropna() % 1 == 0).all(): # 整数判定改善
                    format_dict[col] = "{:,.0f}"
                else:
                    format_dict[col] = "{:,.1f}" # デフォルトは小数点1桁 + カンマ
    return format_dict

def create_csv_download_button(summary_df, df_filtered, data_type):
    # ... (既存のコード、キーの衝突を避けるためにdata_typeをキーに含めるなど検討)
    csv_data = summary_df.to_csv(index=False).encode('utf-8-sig')
    period_str = "全期間"
    if '日付' in df_filtered.columns and not df_filtered['日付'].empty:
        min_date = df_filtered['日付'].min().date()
        max_date = df_filtered['日付'].max().date()
        period_str = f"{min_date}_{max_date}"
    st.download_button(
        label=f"{data_type}をCSVダウンロード", data=csv_data,
        file_name=f"{data_type}_{period_str}.csv", mime="text/csv",
        key=f"csv_download_btn_{data_type.replace(' ', '_')}" # キーをユニークに
    )

def calculate_ward_summary(df):
    # ... (既存のコード、エラーハンドリング強化)
    try:
        # ... (既存の列名マッピングと集計ロジック) ...
        # 欠損値処理の改善
        required_cols = ['病棟コード', '日付', '入院患者数（在院）', '総入院患者数', '総退院患者数', '緊急入院患者数', '死亡患者数']
        if not all(col in df.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df.columns]
            logger.error(f"病棟別サマリー計算に必要な列が不足: {missing}")
            st.warning(f"病棟別サマリー計算に必要な列が不足しています: {', '.join(missing)}。一部指標が計算できません。")
            # 不足列を0で埋めるか、エラーにするか。ここでは一部計算を試みる。
            for m_col in missing:
                if m_col not in ['病棟コード', '日付']: df[m_col] = 0


        ward_groups = df.groupby('病棟コード', observed=True) # observed=True はカテゴリ型の場合に有効
        ward_summary_data = {
            '病棟コード': ward_groups['病棟コード'].first(),
            '期間日数': ward_groups['日付'].nunique(),
            '延べ在院患者数': ward_groups['入院患者数（在院）'].sum() if '入院患者数（在院）' in df.columns else 0,
            '総入院患者数': ward_groups['総入院患者数'].sum() if '総入院患者数' in df.columns else 0,
            '総退院患者数': ward_groups['総退院患者数'].sum() if '総退院患者数' in df.columns else 0,
            '緊急入院患者数': ward_groups['緊急入院患者数'].sum() if '緊急入院患者数' in df.columns else 0,
            '死亡患者数': ward_groups['死亡患者数'].sum() if '死亡患者数' in df.columns else 0,
        }
        ward_summary = pd.DataFrame(ward_summary_data).reset_index(drop=True)
        # ... (以降の計算も同様に列存在チェックと0除算ケア) ...
        ward_summary['平均在院患者数'] = ward_summary.apply(lambda row: row['延べ在院患者数'] / row['期間日数'] if row['期間日数'] > 0 else 0, axis=1)
        ward_summary['平均在院日数'] = ward_summary.apply(lambda row: row['延べ在院患者数'] / ((row['総入院患者数'] + row['総退院患者数']) / 2) if (row['総入院患者数'] + row['総退院患者数']) > 0 else 0, axis=1)
        ward_summary['病床回転率'] = ward_summary.apply(lambda row: row['総退院患者数'] / row['平均在院患者数'] if row['平均在院患者数'] > 0 else 0, axis=1)
        ward_summary['緊急入院率'] = ward_summary.apply(lambda row: (row['緊急入院患者数'] / row['総入院患者数'] * 100) if row['総入院患者数'] > 0 else 0, axis=1)
        ward_summary['死亡率'] = ward_summary.apply(lambda row: (row['死亡患者数'] / row['総退院患者数'] * 100) if row['総退院患者数'] > 0 else 0, axis=1)
        return ward_summary
    except Exception as e:
        logger.error(f"病棟別サマリー計算エラー: {e}", exc_info=True)
        return pd.DataFrame()


def calculate_department_summary(df):
    # ... (calculate_ward_summary と同様の修正) ...
    try:
        required_cols = ['診療科名', '日付', '入院患者数（在院）', '総入院患者数', '総退院患者数', '緊急入院患者数', '死亡患者数']
        if not all(col in df.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df.columns]
            logger.error(f"診療科別サマリー計算に必要な列が不足: {missing}")
            st.warning(f"診療科別サマリー計算に必要な列が不足しています: {', '.join(missing)}。一部指標が計算できません。")
            for m_col in missing:
                if m_col not in ['診療科名', '日付']: df[m_col] = 0

        dept_groups = df.groupby('診療科名', observed=True)
        dept_summary_data = {
            '診療科名': dept_groups['診療科名'].first(),
            '期間日数': dept_groups['日付'].nunique(),
            '延べ在院患者数': dept_groups['入院患者数（在院）'].sum() if '入院患者数（在院）' in df.columns else 0,
            '総入院患者数': dept_groups['総入院患者数'].sum() if '総入院患者数' in df.columns else 0,
            '総退院患者数': dept_groups['総退院患者数'].sum() if '総退院患者数' in df.columns else 0,
            '緊急入院患者数': dept_groups['緊急入院患者数'].sum() if '緊急入院患者数' in df.columns else 0,
            '死亡患者数': dept_groups['死亡患者数'].sum() if '死亡患者数' in df.columns else 0,
        }
        dept_summary = pd.DataFrame(dept_summary_data).reset_index(drop=True)
        dept_summary['平均在院患者数'] = dept_summary.apply(lambda row: row['延べ在院患者数'] / row['期間日数'] if row['期間日数'] > 0 else 0, axis=1)
        dept_summary['平均在院日数'] = dept_summary.apply(lambda row: row['延べ在院患者数'] / ((row['総入院患者数'] + row['総退院患者数']) / 2) if (row['総入院患者数'] + row['総退院患者数']) > 0 else 0, axis=1)
        dept_summary['病床回転率'] = dept_summary.apply(lambda row: row['総退院患者数'] / row['平均在院患者数'] if row['平均在院患者数'] > 0 else 0, axis=1)
        dept_summary['緊急入院率'] = dept_summary.apply(lambda row: (row['緊急入院患者数'] / row['総入院患者数'] * 100) if row['総入院患者数'] > 0 else 0, axis=1)
        dept_summary['死亡率'] = dept_summary.apply(lambda row: (row['死亡患者数'] / row['総退院患者数'] * 100) if row['総退院患者数'] > 0 else 0, axis=1)
        return dept_summary
    except Exception as e:
        logger.error(f"診療科別サマリー計算エラー: {e}", exc_info=True)
        return pd.DataFrame()

def create_ward_comparison_charts(ward_summary):
    # ... (既存のコード、空データチェックを追加)
    try:
        if ward_summary is None or ward_summary.empty:
            st.info("病棟別比較グラフ: 表示するデータがありません。")
            return
        st.markdown("---")
        st.subheader("病棟別比較グラフ")
        col1, col2 = st.columns(2)
        with col1:
            fig_census = px.bar(ward_summary, x='病棟コード', y='平均在院患者数', title='病棟別 平均在院患者数', color='平均在院患者数', color_continuous_scale='Blues')
            fig_census.update_layout(height=400)
            st.plotly_chart(fig_census, use_container_width=True)
        with col2:
            fig_alos = px.bar(ward_summary, x='病棟コード', y='平均在院日数', title='病棟別 平均在院日数', color='平均在院日数', color_continuous_scale='Reds')
            fig_alos.update_layout(height=400)
            st.plotly_chart(fig_alos, use_container_width=True)
        fig_scatter = px.scatter(
            ward_summary, x='平均在院患者数', y='平均在院日数', size='総入院患者数',
            hover_name='病棟コード', title='平均在院患者数 vs 平均在院日数（バブルサイズ：総入院患者数）',
            labels={'平均在院患者数': '平均在院患者数（人）', '平均在院日数': '平均在院日数（日）'}
        )
        fig_scatter.update_layout(height=400)
        st.plotly_chart(fig_scatter, use_container_width=True)
    except Exception as e:
        logger.error(f"病棟別グラフ作成エラー: {e}", exc_info=True)
        st.error(f"病棟別グラフ作成中にエラー: {e}")


def create_department_comparison_charts(dept_summary):
    # ... (既存のコード、空データチェックを追加)
    try:
        if dept_summary is None or dept_summary.empty:
            st.info("診療科別比較グラフ: 表示するデータがありません。")
            return
        st.markdown("---")
        st.subheader("診療科別比較グラフ")
        col1, col2 = st.columns(2)
        with col1:
            top_census = dept_summary.nlargest(10, '平均在院患者数') if '平均在院患者数' in dept_summary.columns else pd.DataFrame()
            if not top_census.empty:
                fig_census = px.bar(top_census, x='平均在院患者数', y='診療科名', orientation='h', title='診療科別 平均在院患者数（上位10位）', color='平均在院患者数', color_continuous_scale='Blues')
                fig_census.update_layout(height=400)
                st.plotly_chart(fig_census, use_container_width=True)
            else: st.caption("平均在院患者数データなし")
        with col2:
            top_alos = dept_summary.nlargest(10, '平均在院日数') if '平均在院日数' in dept_summary.columns else pd.DataFrame()
            if not top_alos.empty:
                fig_alos = px.bar(top_alos, x='平均在院日数', y='診療科名', orientation='h', title='診療科別 平均在院日数（上位10位）', color='平均在院日数', color_continuous_scale='Reds')
                fig_alos.update_layout(height=400)
                st.plotly_chart(fig_alos, use_container_width=True)
            else: st.caption("平均在院日数データなし")
        
        if all(col in dept_summary.columns for col in ['緊急入院率', '死亡率', '総入院患者数']):
            fig_rates = px.scatter(
                dept_summary, x='緊急入院率', y='死亡率', size='総入院患者数',
                hover_name='診療科名', title='緊急入院率 vs 死亡率（バブルサイズ：総入院患者数）',
                labels={'緊急入院率': '緊急入院率（%）', '死亡率': '死亡率（%）'}
            )
            fig_rates.update_layout(height=400)
            st.plotly_chart(fig_rates, use_container_width=True)
        else:
            st.caption("緊急入院率、死亡率、または総入院患者数データなし")
    except Exception as e:
        logger.error(f"診療科別グラフ作成エラー: {e}", exc_info=True)
        st.error(f"診療科別グラフ作成中にエラー: {e}")