import streamlit as st
import pandas as pd
import numpy as np
import datetime
import traceback

# ===== 設定値とスタイルの読み込み =====
from config import *
from style import inject_global_css
from utils import initialize_all_mappings # safe_date_filter は app.py では直接使われていない可能性

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

def get_analysis_period():
    if not st.session_state.get('data_processed', False):
        return None, None, "データ未処理"
    filter_config = get_unified_filter_config()
    if filter_config and 'start_date' in filter_config and 'end_date' in filter_config:
        start_date_ts = pd.Timestamp(filter_config['start_date']).normalize()
        end_date_ts = pd.Timestamp(filter_config['end_date']).normalize()
        if filter_config.get('period_mode') == "プリセット期間" and filter_config.get('preset'):
            period_description = filter_config['preset']
        else:
            period_description = f"{start_date_ts.strftime('%Y/%m/%d')}～{end_date_ts.strftime('%Y/%m/%d')}"
        return start_date_ts, end_date_ts, period_description
    else:
        df = st.session_state.get('df')
        if df is not None and not df.empty and '日付' in df.columns:
            latest_date = df['日付'].max()
            default_start_ts = (latest_date - pd.Timedelta(days=29)).normalize()
            return default_start_ts, latest_date.normalize(), "デフォルト期間 (直近30日)"
        return None, None, "期間未設定"

def filter_data_by_analysis_period(df_original):
    if df_original is None or df_original.empty:
        return pd.DataFrame()
    return apply_unified_filters(df_original)

def check_forecast_dependencies():
    missing_libs = []
    try: import statsmodels
    except ImportError: missing_libs.append("statsmodels")
    try: import pmdarima
    except ImportError: missing_libs.append("pmdarima")
    if missing_libs:
        st.sidebar.warning(
            f"予測機能の完全な動作には以下のライブラリが必要です:\n"
            f"{', '.join(missing_libs)}\n\n"
            f"インストール方法:\n```\npip install {' '.join(missing_libs)}\n```"
        )
    return len(missing_libs) == 0

def create_sidebar_data_settings():
    # ... (既存の create_sidebar_data_settings 関数 - 変更なし) ...
    # (この関数は `st.sidebar.header("💾 データ設定")` から始まる想定)
    st.sidebar.header("💾 データ設定")
    with st.sidebar.expander("📊 現在のデータ状況", expanded=True):
        if st.session_state.get('data_processed', False):
            df = st.session_state.get('df')
            if df is not None:
                data_source = st.session_state.get('data_source', 'unknown')
                latest_date_str = st.session_state.get('latest_data_date_str', '不明')
                st.success("✅ データ読み込み済み")
                st.write(f"📅 最新日付: {latest_date_str}")
                st.write(f"📊 レコード数: {len(df):,}件")
                source_text = {'auto_loaded': '自動読み込み', 'manual_loaded': '手動読み込み', 'sidebar_upload': 'サイドバー', 'unknown': '不明'}.get(data_source, '不明')
                st.write(f"🔄 読み込み元: {source_text}")
                data_info = get_data_info()
                if data_info:
                    last_saved = data_info.get('last_saved', '不明')
                    if last_saved != '不明':
                        try:
                            saved_date = datetime.datetime.fromisoformat(last_saved.replace('Z', '+00:00'))
                            formatted_date = saved_date.strftime('%Y/%m/%d %H:%M')
                            st.write(f"💾 最終保存: {formatted_date}")
                        except: # pylint: disable=bare-except
                            st.write(f"💾 最終保存: {last_saved}")
            else:
                st.warning("⚠️ データ処理エラー")
        else:
            st.info("📂 データ未読み込み")
            data_info = get_data_info()
            if data_info:
                st.write("💾 保存済みデータあり")
                if st.button("🔄 保存データを読み込む", key="load_saved_data_sidebar_app_v2"): # キー変更
                    df_loaded, target_data_loaded, metadata_loaded = load_data_from_file() # 変数名変更
                    if df_loaded is not None:
                        st.session_state['df'] = df_loaded
                        st.session_state['target_data'] = target_data_loaded
                        st.session_state['data_processed'] = True
                        st.session_state['data_source'] = 'manual_loaded'
                        st.session_state['data_metadata'] = metadata_loaded
                        if '日付' in df_loaded.columns and not df_loaded['日付'].empty:
                            latest_date = df_loaded['日付'].max()
                            st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                        else:
                             st.session_state.latest_data_date_str = "日付不明"
                        initialize_all_mappings(st.session_state.df, st.session_state.target_data)
                        st.rerun()

    with st.sidebar.expander("🔧 データ操作", expanded=False):
        col1_ds, col2_ds = st.columns(2) # 変数名変更
        with col1_ds:
            if st.button("💾 データ保存", key="save_current_data_sidebar_app_v2", use_container_width=True): # キー変更
                if st.session_state.get('data_processed', False):
                    df_to_save = st.session_state.get('df')
                    target_data_to_save = st.session_state.get('target_data')
                    if save_data_to_file(df_to_save, target_data_to_save):
                        st.success("保存完了!")
                        st.rerun()
                    else:
                        st.error("保存失敗")
                else:
                    st.warning("保存するデータがありません")
        with col2_ds:
            if st.button("🗑️ データ削除", key="delete_saved_data_sidebar_app_v2", use_container_width=True): # キー変更
                success, result = delete_saved_data()
                if success:
                    st.success(f"削除完了: {result}")
                    keys_to_clear = ['df', 'target_data', 'data_processed', 'data_source', 'data_metadata',
                                     'latest_data_date_str', 'all_results', 'current_unified_filter_config',
                                     'mappings_initialized_after_processing', 'unified_filter_initialized',
                                     'unified_filter_start_date', 'unified_filter_end_date',
                                     'unified_filter_period_mode', 'unified_filter_preset',
                                     'unified_filter_dept_mode', 'unified_filter_selected_depts',
                                     'unified_filter_ward_mode', 'unified_filter_selected_wards'
                                     ]
                    for key in keys_to_clear:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()
                else:
                    st.error(f"削除失敗: {result}")
        file_sizes = get_file_sizes()
        if any(size != "未保存" for size in file_sizes.values()):
            st.write("📁 **ファイルサイズ:**")
            for name, size in file_sizes.items():
                if size != "未保存":
                    st.write(f"  • {name}: {size}")

    with st.sidebar.expander("🗂️ バックアップ管理", expanded=False):
        backup_info = get_backup_info()
        if backup_info:
            st.write("📋 **利用可能なバックアップ:**")
            for backup in backup_info:
                col1_bk_v2, col2_bk_v2 = st.columns([3, 1]) # 変数名変更
                with col1_bk_v2:
                    st.write(f"📄 {backup['timestamp']}")
                    st.caption(f"サイズ: {backup['size']}")
                with col2_bk_v2:
                    if st.button("復元", key=f"restore_{backup['filename']}_sidebar_app_v2", use_container_width=True): # キー変更
                        success, message = restore_from_backup(backup['filename'])
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
        else:
            st.info("バックアップファイルはありません")

    with st.sidebar.expander("📤 簡易データアップロード", expanded=False):
        st.write("**簡易的なファイル読み込み**")
        st.caption("詳細な処理は「データ処理」タブを使用")
        uploaded_file_sidebar_v2 = st.file_uploader( # 変数名変更
            "ファイルを選択", type=SUPPORTED_FILE_TYPES, key="sidebar_file_upload_widget_app_v2", # キー変更
            help="Excel/CSVファイルをアップロード"
        )
        if uploaded_file_sidebar_v2 is not None:
            if st.button("⚡ 簡易処理で読み込む", key="quick_process_sidebar_app_v2", use_container_width=True): # キー変更
                try:
                    df_uploaded_v2 = None # 変数名変更
                    if uploaded_file_sidebar_v2.name.endswith('.csv'):
                        df_uploaded_v2 = pd.read_csv(uploaded_file_sidebar_v2, encoding='utf-8')
                    else:
                        df_uploaded_v2 = pd.read_excel(uploaded_file_sidebar_v2)

                    if '日付' in df_uploaded_v2.columns:
                        df_uploaded_v2['日付'] = pd.to_datetime(df_uploaded_v2['日付'], errors='coerce').dt.normalize()
                        df_uploaded_v2.dropna(subset=['日付'], inplace=True)

                    st.session_state['df'] = df_uploaded_v2
                    st.session_state['data_processed'] = True
                    st.session_state['data_source'] = 'sidebar_upload'
                    st.session_state['target_data'] = None
                    if '日付' in df_uploaded_v2.columns and not df_uploaded_v2['日付'].empty:
                        latest_date = df_uploaded_v2['日付'].max()
                        st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                    else:
                        st.session_state.latest_data_date_str = "日付不明"
                    initialize_all_mappings(st.session_state.df, None)
                    st.session_state.mappings_initialized_after_processing = True
                    if 'df' in st.session_state and st.session_state.df is not None:
                        initialize_unified_filters(st.session_state.df)
                    st.success("簡易読み込み完了!")
                    st.rerun()
                except Exception as e:
                    st.error(f"読み込みエラー: {e}")

def create_sidebar_target_file_status():
    """目標値ファイル状況をサイドバーに表示するヘルパー関数"""
    if st.session_state.get('target_data') is not None:
        st.sidebar.markdown("---")
        st.sidebar.subheader("🎯 目標値ファイル状況") # ヘッダーレベル変更
        # with st.sidebar.expander("🎯 目標値ファイル状況", expanded=False): # expander にしても良い
        st.sidebar.success("✅ 目標値ファイル読み込み済み")
        extracted_targets = st.session_state.get('extracted_targets')
        if extracted_targets:
            if extracted_targets.get('target_days') or extracted_targets.get('target_admissions'):
                st.sidebar.markdown("###### <span style='color:green;'>目標値ファイルから取得:</span>", unsafe_allow_html=True) # success の代わりに markdown
                if extracted_targets.get('target_days'):
                    st.sidebar.write(f"- 延べ在院日数目標: {extracted_targets['target_days']:,.0f}人日")
                if extracted_targets.get('target_admissions'):
                    st.sidebar.write(f"- 新入院患者数目標: {extracted_targets['target_admissions']:,.0f}人")
                if extracted_targets.get('used_pattern'):
                    st.sidebar.caption(f"検索条件: {extracted_targets['used_pattern']}") # info から caption へ
            else:
                st.sidebar.warning("⚠️ 目標値を抽出できませんでした")
        
        if st.sidebar.checkbox("🔍 目標値ファイル内容確認", key="sidebar_show_target_details"): # Expander の代わりにチェックボックス
            target_data_disp = st.session_state.get('target_data')
            if target_data_disp is not None:
                st.sidebar.write(f"**ファイル情報:** {target_data_disp.shape[0]}行 × {target_data_disp.shape[1]}列")
                st.sidebar.write("**列名:**", list(target_data_disp.columns))
                st.sidebar.dataframe(target_data_disp.head(), use_container_width=True)
                debug_info_disp = st.session_state.get('target_file_debug_info')
                if debug_info_disp and debug_info_disp.get('search_results'):
                    st.sidebar.markdown("###### **検索結果詳細:**")
                    for keyword, results in debug_info_disp['search_results'].items():
                        if results:
                            st.sidebar.write(f"「{keyword}」の検索結果:")
                            for result in results:
                                st.sidebar.write(f"  - {result['column']}: {result['matches']}件")
                        else:
                            st.sidebar.write(f"「{keyword}」: 該当なし")
    else:
        # 目標値ファイルが読み込まれていない場合の情報も表示（任意）
        # st.sidebar.markdown("---")
        # st.sidebar.info("🎯 目標値ファイルは読み込まれていません。")
        pass


def create_sidebar():
    """サイドバーの設定UI（並び順変更版）"""

    # 1. 分析フィルター (データロード後に表示)
    st.sidebar.header("🔍 分析フィルター") # ヘッダー追加
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        df_for_filter_init = st.session_state.get('df')
        if not df_for_filter_init.empty:
            initialize_unified_filters(df_for_filter_init)
            filter_config = create_unified_filter_sidebar(df_for_filter_init) # これがUIを描画
            if filter_config:
                st.session_state['current_unified_filter_config'] = filter_config
        else:
            st.sidebar.warning("分析フィルターを表示するためのデータが空です。")
    else:
        st.sidebar.info("「データ処理」タブでデータを読み込むと、ここに分析フィルターが表示されます。")
    st.sidebar.markdown("---")

    # 2. グローバル設定
    st.sidebar.header("⚙️ グローバル設定")
    with st.sidebar.expander("🏥 基本病院設定", expanded=False):
        if 'settings_loaded' not in st.session_state: # 設定の読み込みは一度だけで良い
            saved_settings = load_settings_from_file()
            if saved_settings:
                for key, value in saved_settings.items():
                    st.session_state[key] = value
            st.session_state.settings_loaded = True
        def get_safe_value(key, default, value_type=int):
            value = st.session_state.get(key, default)
            if isinstance(value, list): value = value[0] if value else default
            elif not isinstance(value, (int, float)): value = default
            return value_type(value)

        total_beds = st.number_input(
            "総病床数", min_value=HOSPITAL_SETTINGS['min_beds'], max_value=HOSPITAL_SETTINGS['max_beds'],
            value=get_safe_value('total_beds', DEFAULT_TOTAL_BEDS), step=1, help="病院の総病床数",
            key="sidebar_total_beds_global" # キー名変更
        )
        st.session_state.total_beds = total_beds

        current_occupancy_percent = st.session_state.get('bed_occupancy_rate_percent', int(DEFAULT_OCCUPANCY_RATE * 100))
        bed_occupancy_rate = st.slider(
            "目標病床稼働率 (%)", min_value=int(HOSPITAL_SETTINGS['min_occupancy_rate'] * 100),
            max_value=int(HOSPITAL_SETTINGS['max_occupancy_rate'] * 100),
            value=current_occupancy_percent, step=1, help="目標とする病床稼働率",
            key="sidebar_bed_occupancy_rate_slider_global" # キー名変更
        ) / 100
        st.session_state.bed_occupancy_rate = bed_occupancy_rate
        st.session_state.bed_occupancy_rate_percent = int(bed_occupancy_rate * 100)

        avg_length_of_stay = st.number_input(
            "平均在院日数目標", min_value=HOSPITAL_SETTINGS['min_avg_stay'], max_value=HOSPITAL_SETTINGS['max_avg_stay'],
            value=get_safe_value('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY, float), step=0.1, help="目標とする平均在院日数",
            key="sidebar_avg_length_of_stay_global" # キー名変更
        )
        st.session_state.avg_length_of_stay = avg_length_of_stay

        avg_admission_fee = st.number_input(
            "平均入院料（円/日）", min_value=1000, max_value=100000,
            value=get_safe_value('avg_admission_fee', DEFAULT_ADMISSION_FEE), step=1000, help="1日あたりの平均入院料",
            key="sidebar_avg_admission_fee_global" # キー名変更
        )
        st.session_state.avg_admission_fee = avg_admission_fee

    with st.sidebar.expander("🎯 KPI目標値設定", expanded=False):
        monthly_target_patient_days = st.number_input(
            "月間延べ在院日数目標（人日）", min_value=100, max_value=50000,
            value=get_safe_value('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS), step=100, help="月間の延べ在院日数目標",
            key="sidebar_monthly_target_pd_global" # キー名変更
        )
        st.session_state.monthly_target_patient_days = monthly_target_patient_days

        monthly_target_admissions = st.number_input(
            "月間新入院患者数目標（人）", min_value=10, max_value=5000,
            value=get_safe_value('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS), step=10, help="月間の新入院患者数目標",
            key="sidebar_monthly_target_adm_global" # キー名変更
        )
        st.session_state.monthly_target_admissions = monthly_target_admissions

    if st.sidebar.button("💾 グローバル設定とKPI目標値を保存", key="save_all_global_settings_sidebar_v2", use_container_width=True): # キー名変更
        settings_to_save = {
            'total_beds': st.session_state.total_beds,
            'bed_occupancy_rate': st.session_state.bed_occupancy_rate,
            'bed_occupancy_rate_percent': st.session_state.bed_occupancy_rate_percent,
            'avg_length_of_stay': st.session_state.avg_length_of_stay,
            'avg_admission_fee': st.session_state.avg_admission_fee,
            'monthly_target_patient_days': st.session_state.monthly_target_patient_days,
            'monthly_target_admissions': st.session_state.monthly_target_admissions
        }
        if save_settings_to_file(settings_to_save):
            st.sidebar.success("設定保存完了!")
        else:
            st.sidebar.error("設定保存失敗")
    st.sidebar.markdown("---")

    # 3. データ設定
    create_sidebar_data_settings() # この関数が st.sidebar.header("💾 データ設定") から始まる
    st.sidebar.markdown("---")

    # 4. 目標値ファイル状況
    create_sidebar_target_file_status() # ヘルパー関数として呼び出し

    return True


def create_management_dashboard_tab():
    # ... (既存の create_management_dashboard_tab 関数 - 変更なし) ...
    st.header(f"{APP_ICON} 経営ダッシュボード")
    if not st.session_state.get('data_processed', False) or st.session_state.get('df') is None:
        st.warning(MESSAGES['data_not_loaded'])
        return
    df_original = st.session_state.get('df')
    start_date_ts, end_date_ts, period_description = get_analysis_period()
    if start_date_ts is None or end_date_ts is None:
        st.error("分析期間が設定されていません。サイドバーの「分析フィルター」で期間を設定してください。")
        return
    st.info(f"📊 分析期間: {period_description} ({start_date_ts.strftime('%Y/%m/%d')} ～ {end_date_ts.strftime('%Y/%m/%d')})")
    st.caption("※期間はサイドバーの「分析フィルター」で変更できます。")
    df_for_dashboard = filter_data_by_analysis_period(df_original)
    if df_for_dashboard.empty:
        st.warning("選択されたフィルター条件に合致するデータがありません。")
        return
    total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
    target_occupancy_rate_percent = st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE) * 100
    if display_kpi_cards_only:
        display_kpi_cards_only(df_for_dashboard, start_date_ts, end_date_ts, total_beds, target_occupancy_rate_percent)
    else:
        st.error("KPIカード表示機能が利用できません。dashboard_overview_tab.pyを確認してください。")


def main():
    # ... (既存の main 関数 - create_sidebar の呼び出し以外はほぼ変更なし) ...
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
        if st.session_state.df is not None and not st.session_state.df.empty: # dfが空でないことを確認
             initialize_unified_filters(st.session_state.df)
        st.session_state.mappings_initialized_after_processing = True

    st.markdown(f'<h1 class="main-header">{APP_ICON} {APP_TITLE}</h1>', unsafe_allow_html=True)

    create_sidebar() # ★★★ 修正された create_sidebar を呼び出す ★★★

    tab_names = ["💰 経営ダッシュボード"]
    if FORECAST_AVAILABLE: tab_names.append("🔮 予測分析")
    tab_names.extend(["📈 詳細分析", "📋 データテーブル", "📄 PDF出力", "📊 データ処理"])
    tabs = st.tabs(tab_names)

    with tabs[-1]:
        try:
            create_data_processing_tab()
            if st.session_state.get('data_processed') and st.session_state.get('df') is not None:
                 if not st.session_state.get('df').empty: # dfが空でないことを確認
                    initialize_unified_filters(st.session_state.df)
        except Exception as e:
            st.error(f"データ処理タブでエラー: {str(e)}\n{traceback.format_exc()}")

    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        with tabs[0]:
            try: create_management_dashboard_tab()
            except Exception as e: st.error(f"経営ダッシュボードでエラー: {str(e)}\n{traceback.format_exc()}")
        tab_offset = 0
        if FORECAST_AVAILABLE:
            with tabs[1]:
                try:
                    deps_ok = check_forecast_dependencies()
                    if deps_ok: display_forecast_analysis_tab()
                    else: st.info(MESSAGES['forecast_libs_missing'])
                except Exception as e: st.error(f"予測分析でエラー: {str(e)}\n{traceback.format_exc()}")
            tab_offset = 1
        with tabs[1 + tab_offset]:
            try: create_detailed_analysis_tab()
            except Exception as e: st.error(f"詳細分析でエラー: {str(e)}\n{traceback.format_exc()}")
        with tabs[2 + tab_offset]:
            try: create_data_tables_tab()
            except Exception as e: st.error(f"データテーブルでエラー: {str(e)}\n{traceback.format_exc()}")
        with tabs[3 + tab_offset]:
            try: pdf_output_tab.create_pdf_output_tab()
            except Exception as e: st.error(f"PDF出力機能でエラー: {str(e)}\n{traceback.format_exc()}")
    else:
        for i in range(len(tabs) - 1):
            with tabs[i]:
                st.info(MESSAGES['insufficient_data'])
                data_info = get_data_info()
                if data_info: st.info("💾 保存されたデータがあります。「データ設定」から読み込めます。")
                else: st.info("📋 「データ処理」タブから新しいデータをアップロードしてください。")

    st.markdown("---")
    st.markdown(
        f'<div style="text-align: center; color: {DASHBOARD_COLORS["light_gray"]}; font-size: 0.8rem;">'
        f'{APP_ICON} {APP_TITLE} v{APP_VERSION} | {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        f'</div>',
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()