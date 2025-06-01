import streamlit as st
import pandas as pd
import numpy as np
import datetime
import traceback

# ===== 設定値とスタイルの読み込み =====
from config import *
from style import inject_global_css
from utils import initialize_all_mappings

# データ永続化機能のインポート
from data_persistence import (
    auto_load_data, save_data_to_file, load_data_from_file,
    get_data_info, delete_saved_data, get_file_sizes,
    save_settings_to_file, load_settings_from_file,
    get_backup_info, restore_from_backup
)

# ページ設定
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# グローバルCSS適用
inject_global_css(FONT_SCALE)

# カスタムモジュールのインポート (エラー時のフォールバックも含む)
try:
    from analysis_tabs import create_detailed_analysis_tab, create_data_tables_tab
    from data_processing_tab import create_data_processing_tab
    import pdf_output_tab
    from forecast_analysis_tab import display_forecast_analysis_tab
    from kpi_calculator import calculate_kpis
    from dashboard_overview_tab import display_kpi_cards_only
    from alos_analysis_tab import display_alos_analysis_tab
    from dow_analysis_tab import display_dow_analysis_tab
    from individual_analysis_tab import display_individual_analysis_tab
    from unified_filters import (create_unified_filter_sidebar, apply_unified_filters,
                                 get_unified_filter_summary, initialize_unified_filters,
                                 get_unified_filter_config, validate_unified_filters)
    FORECAST_AVAILABLE = True
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.error(traceback.format_exc())
    FORECAST_AVAILABLE = False
    # フォールバック定義 (前回と同様)
    create_detailed_analysis_tab = lambda: st.error("詳細分析機能は利用できません。")
    create_data_tables_tab = lambda: st.error("データテーブル機能は利用できません。")
    create_data_processing_tab = lambda: st.error("データ処理機能は利用できません。")
    pdf_output_tab = type('pdf_output_tab_mock', (object,), {'create_pdf_output_tab': lambda: st.error("PDF出力機能は利用できません。")})()
    display_forecast_analysis_tab = lambda: st.error("予測分析機能は利用できません。")
    calculate_kpis = None
    display_kpi_cards_only = lambda df, start_date, end_date, total_beds_setting, target_occupancy_setting: st.error("経営ダッシュボードKPI表示機能は利用できません。")
    create_unified_filter_sidebar = lambda df: None
    apply_unified_filters = lambda df: df
    get_unified_filter_summary = lambda: "フィルター情報取得不可"
    initialize_unified_filters = lambda df: None
    get_unified_filter_config = lambda: {}
    validate_unified_filters = lambda df: (False, "フィルター検証機能利用不可")

def main():
    if 'app_initialized' not in st.session_state:
        st.session_state.app_initialized = True
    if 'data_processed' not in st.session_state: st.session_state['data_processed'] = False
    if 'df' not in st.session_state: st.session_state['df'] = None
    if 'forecast_model_results' not in st.session_state: st.session_state.forecast_model_results = {}
    if 'mappings_initialized_after_processing' not in st.session_state: st.session_state.mappings_initialized_after_processing = False

    auto_loaded = auto_load_data()
    if auto_loaded and st.session_state.get('df') is not None:
        st.success(MESSAGES['auto_load_success'])
        if 'target_data' not in st.session_state: st.session_state.target_data = None
        initialize_all_mappings(st.session_state.df, st.session_state.target_data)
        if st.session_state.df is not None and not st.session_state.df.empty:
             initialize_unified_filters(st.session_state.df)
        st.session_state.mappings_initialized_after_processing = True

    st.markdown(f'<h1 class="main-header">{APP_ICON} {APP_TITLE}</h1>', unsafe_allow_html=True)
    create_sidebar()

    # 新しいタブの並び順
    tab_titles = ["💰 経営ダッシュボード", "🗓️ 平均在院日数分析", "📅 曜日別入退院分析", "🔍 個別分析"]
    if FORECAST_AVAILABLE:
        tab_titles.append("🔮 予測分析")
    tab_titles.extend(["📤 データ出力", "📥 データ入力"]) # 名称変更と統合

    tabs = st.tabs(tab_titles)

    # データ入力タブ (旧データ処理タブ)
    with tabs[tab_titles.index("📥 データ入力")]:
        try:
            create_data_processing_tab()
            if st.session_state.get('data_processed') and st.session_state.get('df') is not None:
                 if not st.session_state.get('df').empty:
                    initialize_unified_filters(st.session_state.df)
        except Exception as e:
            st.error(f"データ入力タブでエラー: {str(e)}\n{traceback.format_exc()}")

    # データ処理済みの場合のみ他のタブを表示
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        df_original_main = st.session_state.get('df') # フィルター前のオリジナルDF
        common_config_main = st.session_state.get('common_config', {}) # 共通設定

        # 統一フィルターを適用したDFを取得 (各分析タブで使用)
        df_filtered_unified = filter_data_by_analysis_period(df_original_main)
        current_filter_config = get_unified_filter_config() # 現在のフィルター設定を取得

        # 経営ダッシュボード
        with tabs[tab_titles.index("💰 経営ダッシュボード")]:
            try:
                # create_management_dashboard_tab は filter_data_by_analysis_period を内部で呼ぶので df_original_main を渡す
                create_management_dashboard_tab() # この関数が get_analysis_period と filter_data_by_analysis_period を使う
            except Exception as e:
                st.error(f"経営ダッシュボードでエラー: {str(e)}\n{traceback.format_exc()}")

        # 平均在院日数分析
        with tabs[tab_titles.index("🗓️ 平均在院日数分析")]:
            try:
                if display_alos_analysis_tab:
                    # display_alos_analysis_tab には統一フィルター適用後のdfと期間を渡す
                    start_dt, end_dt, _ = get_analysis_period()
                    if start_dt and end_dt:
                         display_alos_analysis_tab(df_filtered_unified, start_dt, end_dt, common_config_main)
                    else:
                        st.warning("平均在院日数分析: 分析期間が設定されていません。")
                else:
                    st.error("平均在院日数分析機能が利用できません。")
            except Exception as e:
                st.error(f"平均在院日数分析でエラー: {str(e)}\n{traceback.format_exc()}")

        # 曜日別入退院分析
        with tabs[tab_titles.index("📅 曜日別入退院分析")]:
            try:
                if display_dow_analysis_tab:
                    start_dt, end_dt, _ = get_analysis_period()
                    if start_dt and end_dt:
                        display_dow_analysis_tab(df_filtered_unified, start_dt, end_dt, common_config_main)
                    else:
                        st.warning("曜日別入退院分析: 分析期間が設定されていません。")
                else:
                    st.error("曜日別入退院分析機能が利用できません。")
            except Exception as e:
                st.error(f"曜日別入退院分析でエラー: {str(e)}\n{traceback.format_exc()}")

        # 個別分析
        with tabs[tab_titles.index("🔍 個別分析")]:
            try:
                if display_individual_analysis_tab:
                    # display_individual_analysis_tab はフィルタリング済みdfを引数に取るように修正済み
                    # filter_config は get_unified_filter_config() で取得できるので、ここでは渡さない
                    create_individual_analysis_section(df_filtered_unified, current_filter_config) # analysis_tabs.pyの関数を呼び出す
                else:
                    st.error("個別分析機能が利用できません。")
            except Exception as e:
                st.error(f"個別分析でエラー: {str(e)}\n{traceback.format_exc()}")

        # 予測分析 (FORECAST_AVAILABLE の場合のみ)
        if FORECAST_AVAILABLE:
            with tabs[tab_titles.index("🔮 予測分析")]:
                try:
                    deps_ok = check_forecast_dependencies()
                    if deps_ok:
                        # display_forecast_analysis_tab は内部で st.session_state.df を参照するので、
                        # 統一フィルター適用後のdfをセッションに一時的に設定するか、関数を修正する必要がある。
                        # ここでは、一時的にセッションを設定する。
                        original_df_for_forecast = st.session_state.get('df')
                        st.session_state['df'] = df_filtered_unified # 予測分析用にフィルター済みdfを設定
                        display_forecast_analysis_tab()
                        st.session_state['df'] = original_df_for_forecast # 元に戻す
                    else:
                        st.info(MESSAGES['forecast_libs_missing'])
                except Exception as e:
                    st.error(f"予測分析でエラー: {str(e)}\n{traceback.format_exc()}")
        
        # データ出力タブ
        data_output_tab_index = tab_titles.index("📤 データ出力")
        with tabs[data_output_tab_index]:
            st.header("📤 データ出力") # タブヘッダー
            output_sub_tab1, output_sub_tab2 = st.tabs(["📋 データテーブル", "📄 PDF出力"])
            with output_sub_tab1:
                try:
                    # create_data_tables_tab は内部で apply_unified_filters を呼ぶので df_original_main を渡す
                    # ただし、UI上は統一フィルターの結果が表示されるべきなので、df_filtered_unified を渡す方が直感的かもしれない。
                    # create_data_tables_tab の実装を確認・調整。現状は apply_unified_filters を内部で呼ぶ。
                    create_data_tables_tab() # この関数は session_state.df を参照するため、df_original_main が設定されている前提
                except Exception as e:
                    st.error(f"データテーブル表示でエラー: {str(e)}\n{traceback.format_exc()}")
            with output_sub_tab2:
                try:
                    # create_pdf_output_tab も同様に df_original_main を参照し、内部でフィルター適用を期待するか、
                    # df_filtered_unified を渡すようにするか。
                    # pdf_output_tab.py の display_batch_pdf_tab が session_state.df を参照するため、
                    # df_original_main が設定されている前提。
                    # 統一フィルターの結果を渡すように pdf_output_tab.py を修正するのが望ましい。
                    # 現状の pdf_output_tab.py の display_batch_pdf_tab は session_state.df を参照するので、
                    # ここでは session_state.df が df_original_main であることを確認。
                    # もし df_filtered_unified を渡すなら pdf_output_tab の修正が必要。
                    pdf_output_tab.create_pdf_output_tab()
                except Exception as e:
                    st.error(f"PDF出力機能でエラー: {str(e)}\n{traceback.format_exc()}")
    
    else: # データ未処理の場合
        # データ入力タブ以外のタブにメッセージ表示
        non_input_tab_indices = [i for i, title in enumerate(tab_titles) if title != "📥 データ入力"]
        for i in non_input_tab_indices:
            with tabs[i]:
                st.info(MESSAGES['insufficient_data'])
                data_info = get_data_info()
                if data_info: st.info("💾 保存されたデータがあります。サイドバーまたは「データ入力」タブから読み込めます。") # メッセージ修正
                else: st.info("📋 「データ入力」タブから新しいデータをアップロードしてください。")


    st.markdown("---")
    st.markdown(
        f'<div style="text-align: center; color: {DASHBOARD_COLORS["light_gray"]}; font-size: 0.8rem;">'
        f'{APP_ICON} {APP_TITLE} v{APP_VERSION} | {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        f'</div>',
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()