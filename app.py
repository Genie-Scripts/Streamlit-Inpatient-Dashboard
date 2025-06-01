import streamlit as st
import pandas as pd
import numpy as np # 必要に応じて
# import plotly.express as px # create_management_dashboard_tab では直接不要
# import plotly.graph_objects as go # create_management_dashboard_tab では直接不要
# from plotly.subplots import make_subplots # create_management_dashboard_tab では直接不要
import datetime
import traceback # NameError 解消のため追加

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

# カスタムモジュールのインポート
try:
    from analysis_tabs import create_detailed_analysis_tab, create_data_tables_tab
    from data_processing_tab import create_data_processing_tab
    import pdf_output_tab
    from forecast_analysis_tab import display_forecast_analysis_tab
    from kpi_calculator import calculate_kpis
    # dashboard_overview_tab から display_unified_metrics_layout_colorized をインポート
    from dashboard_overview_tab import display_unified_metrics_layout_colorized # ★★★ 変更点 ★★★
    from unified_filters import (create_unified_filter_sidebar, apply_unified_filters,
                                 get_unified_filter_summary, initialize_unified_filters,
                                 get_unified_filter_config, validate_unified_filters)
    FORECAST_AVAILABLE = True
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.error(traceback.format_exc())
    FORECAST_AVAILABLE = False
    create_detailed_analysis_tab = lambda: st.error("詳細分析機能は利用できません。")
    create_data_tables_tab = lambda: st.error("データテーブル機能は利用できません。")
    create_data_processing_tab = lambda: st.error("データ処理機能は利用できません。")
    pdf_output_tab = type('pdf_output_tab_mock', (object,), {'create_pdf_output_tab': lambda: st.error("PDF出力機能は利用できません。")})()
    display_forecast_analysis_tab = lambda: st.error("予測分析機能は利用できません。")
    calculate_kpis = None
    display_kpi_cards_only = lambda df, start_date, end_date, total_beds_setting, target_occupancy_setting: st.error("経営ダッシュボードKPI表示機能は利用できません。") # ★★★ 変更点 ★★★
    create_unified_filter_sidebar = lambda df: None
    apply_unified_filters = lambda df: df
    get_unified_filter_summary = lambda: "フィルター情報取得不可"
    initialize_unified_filters = lambda df: None
    get_unified_filter_config = lambda: {}
    validate_unified_filters = lambda df: (False, "フィルター検証機能利用不可")
    display_unified_metrics_layout_colorized = lambda metrics, period_info: st.error("KPI表示機能利用不可") # ★★★ フォールバック追加 ★★★



def calculate_preset_period_dates(df, preset_period):
    if df is None or df.empty or '日付' not in df.columns:
        today = pd.Timestamp.now().normalize()
        if preset_period == "直近30日":
            return today - pd.Timedelta(days=29), today
        return today - pd.Timedelta(days=29), today

    latest_date = df['日付'].max()
    min_data_date = df['日付'].min()

    if preset_period == "直近30日":
        start_date_ts = latest_date - pd.Timedelta(days=29)
    elif preset_period == "前月完了分":
        first_day_of_current_month = latest_date.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - pd.Timedelta(days=1)
        start_date_ts = last_day_of_previous_month.replace(day=1)
        end_date_ts = last_day_of_previous_month
        return start_date_ts.normalize(), end_date_ts.normalize()
    elif preset_period == "今年度":
        current_year = latest_date.year
        if latest_date.month >= 4:
            start_date_ts = pd.Timestamp(f"{current_year}-04-01")
        else:
            start_date_ts = pd.Timestamp(f"{current_year-1}-04-01")
    else:
        start_date_ts = latest_date - pd.Timedelta(days=29)

    start_date_ts = max(start_date_ts, min_data_date)
    return start_date_ts.normalize(), latest_date.normalize()


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
            # st.session_state['unified_filter_start_date'] = default_start_ts # unified_filters.pyで管理
            # st.session_state['unified_filter_end_date'] = latest_date.normalize() # unified_filters.pyで管理
            return default_start_ts, latest_date.normalize(), "デフォルト期間 (直近30日)"
        return None, None, "期間未設定"


def filter_data_by_analysis_period(df_original):
    if df_original is None or df_original.empty:
        return pd.DataFrame()
    return apply_unified_filters(df_original)


def check_forecast_dependencies():
    missing_libs = []
    try:
        import statsmodels
    except ImportError:
        missing_libs.append("statsmodels")
    try:
        import pmdarima
    except ImportError:
        missing_libs.append("pmdarima")
    if missing_libs:
        st.sidebar.warning(
            f"予測機能の完全な動作には以下のライブラリが必要です:\n"
            f"{', '.join(missing_libs)}\n\n"
            f"インストール方法:\n"
            f"```\npip install {' '.join(missing_libs)}\n```"
        )
    return len(missing_libs) == 0


def create_sidebar_data_settings():
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
                        except:
                            st.write(f"💾 最終保存: {last_saved}")
            else:
                st.warning("⚠️ データ処理エラー")
        else:
            st.info("📂 データ未読み込み")
            data_info = get_data_info()
            if data_info:
                st.write("💾 保存済みデータあり")
                if st.button("🔄 保存データを読み込む", key="load_saved_data_sidebar"): # キー変更
                    df, target_data, metadata = load_data_from_file()
                    if df is not None:
                        st.session_state['df'] = df
                        st.session_state['target_data'] = target_data
                        st.session_state['data_processed'] = True
                        st.session_state['data_source'] = 'manual_loaded'
                        st.session_state['data_metadata'] = metadata
                        if '日付' in df.columns:
                            latest_date = df['日付'].max()
                            st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                        initialize_all_mappings(st.session_state.df, st.session_state.target_data) # マッピング初期化
                        st.rerun() # st.experimental_rerun() -> st.rerun()

    with st.sidebar.expander("🔧 データ操作", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 データ保存", key="save_current_data_sidebar", use_container_width=True): # キー変更
                if st.session_state.get('data_processed', False):
                    df_to_save = st.session_state.get('df') # df -> df_to_save
                    target_data_to_save = st.session_state.get('target_data') # target_data -> target_data_to_save
                    if save_data_to_file(df_to_save, target_data_to_save): # 引数名変更
                        st.success("保存完了!")
                        st.rerun()
                    else:
                        st.error("保存失敗")
                else:
                    st.warning("保存するデータがありません")
        with col2:
            if st.button("🗑️ データ削除", key="delete_saved_data_sidebar", use_container_width=True): # キー変更
                success, result = delete_saved_data()
                if success:
                    st.success(f"削除完了: {result}")
                    keys_to_clear = ['df', 'target_data', 'data_processed', 'data_source', 'data_metadata',
                                     'latest_data_date_str', 'all_results', 'current_unified_filter_config',
                                     'mappings_initialized_after_processing'] # クリアするキーを追加
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
                col1_bk, col2_bk = st.columns([3, 1]) # col1 -> col1_bk, col2 -> col2_bk
                with col1_bk:
                    st.write(f"📄 {backup['timestamp']}")
                    st.caption(f"サイズ: {backup['size']}")
                with col2_bk:
                    if st.button("復元", key=f"restore_{backup['filename']}_sidebar", use_container_width=True): # キー変更
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
        uploaded_file_sidebar = st.file_uploader( # uploaded_file -> uploaded_file_sidebar
            "ファイルを選択", type=SUPPORTED_FILE_TYPES, key="sidebar_file_upload_widget", # キー変更
            help="Excel/CSVファイルをアップロード"
        )
        if uploaded_file_sidebar is not None:
            if st.button("⚡ 簡易処理で読み込む", key="quick_process_sidebar", use_container_width=True): # キー変更
                try:
                    df_uploaded = None # df -> df_uploaded
                    if uploaded_file_sidebar.name.endswith('.csv'):
                        df_uploaded = pd.read_csv(uploaded_file_sidebar, encoding='utf-8')
                    else:
                        df_uploaded = pd.read_excel(uploaded_file_sidebar)
                    if '日付' in df_uploaded.columns:
                        df_uploaded['日付'] = pd.to_datetime(df_uploaded['日付'])
                    st.session_state['df'] = df_uploaded
                    st.session_state['data_processed'] = True
                    st.session_state['data_source'] = 'sidebar_upload'
                    st.session_state['target_data'] = None
                    if '日付' in df_uploaded.columns:
                        latest_date = df_uploaded['日付'].max()
                        st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                    initialize_all_mappings(st.session_state.df, None) # マッピング初期化
                    st.session_state.mappings_initialized_after_processing = True
                    st.success("簡易読み込み完了!")
                    st.rerun()
                except Exception as e:
                    st.error(f"読み込みエラー: {e}")


def create_sidebar():
    create_sidebar_data_settings()
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ グローバル設定")
    with st.sidebar.expander("🏥 基本病院設定", expanded=True):
        if 'settings_loaded' not in st.session_state:
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
            value=get_safe_value('total_beds', DEFAULT_TOTAL_BEDS), step=1, help="病院の総病床数"
        )
        st.session_state.total_beds = total_beds
        current_occupancy_percent = st.session_state.get('bed_occupancy_rate_percent', int(DEFAULT_OCCUPANCY_RATE * 100))
        bed_occupancy_rate = st.slider(
            "目標病床稼働率 (%)", min_value=int(HOSPITAL_SETTINGS['min_occupancy_rate'] * 100),
            max_value=int(HOSPITAL_SETTINGS['max_occupancy_rate'] * 100),
            value=current_occupancy_percent, step=1, help="目標とする病床稼働率"
        ) / 100
        st.session_state.bed_occupancy_rate = bed_occupancy_rate
        st.session_state.bed_occupancy_rate_percent = int(bed_occupancy_rate * 100)
        avg_length_of_stay = st.number_input(
            "平均在院日数目標", min_value=HOSPITAL_SETTINGS['min_avg_stay'], max_value=HOSPITAL_SETTINGS['max_avg_stay'],
            value=get_safe_value('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY, float), step=0.1, help="目標とする平均在院日数"
        )
        st.session_state.avg_length_of_stay = avg_length_of_stay
        avg_admission_fee = st.number_input(
            "平均入院料（円/日）", min_value=1000, max_value=100000,
            value=get_safe_value('avg_admission_fee', DEFAULT_ADMISSION_FEE), step=1000, help="1日あたりの平均入院料"
        )
        st.session_state.avg_admission_fee = avg_admission_fee
        if st.button("💾 グローバル設定を保存", key="save_global_settings_sidebar"): # キー変更
            settings_to_save = {
                'total_beds': total_beds, 'bed_occupancy_rate': bed_occupancy_rate,
                'bed_occupancy_rate_percent': int(bed_occupancy_rate * 100),
                'avg_length_of_stay': avg_length_of_stay, 'avg_admission_fee': avg_admission_fee
            }
            if 'monthly_target_patient_days' in st.session_state:
                settings_to_save['monthly_target_patient_days'] = st.session_state.monthly_target_patient_days
            if 'monthly_target_admissions' in st.session_state:
                settings_to_save['monthly_target_admissions'] = st.session_state.monthly_target_admissions
            if save_settings_to_file(settings_to_save): st.success("設定保存完了!")
            else: st.error("設定保存失敗")

    with st.sidebar.expander("🎯 KPI目標値設定", expanded=False):
        monthly_target_patient_days = st.number_input(
            "月間延べ在院日数目標（人日）", min_value=100, max_value=50000,
            value=get_safe_value('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS), step=100, help="月間の延べ在院日数目標"
        )
        st.session_state.monthly_target_patient_days = monthly_target_patient_days
        monthly_target_admissions = st.number_input(
            "月間新入院患者数目標（人）", min_value=10, max_value=5000,
            value=get_safe_value('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS), step=10, help="月間の新入院患者数目標"
        )
        st.session_state.monthly_target_admissions = monthly_target_admissions

    st.sidebar.markdown("---")
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        df_for_filter_init = st.session_state.get('df')
        initialize_unified_filters(df_for_filter_init)
        filter_config = create_unified_filter_sidebar(df_for_filter_init)
        if filter_config:
            st.session_state['current_unified_filter_config'] = filter_config
    else:
        st.sidebar.info("データを読み込むと分析フィルターが表示されます。")
    return True


def create_management_dashboard_tab():
    """経営ダッシュボードタブ（統一KPIレイアウト使用）"""
    st.header(f"{APP_ICON} 経営ダッシュボード")

    if not st.session_state.get('data_processed', False) or st.session_state.get('df') is None:
        st.warning(MESSAGES['data_not_loaded'])
        return

    df_original = st.session_state.get('df')
    total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
    # avg_admission_fee = st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE) # display_unified_metrics_layout_colorized内で使用
    # monthly_target_patient_days = st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS) # display_unified_metrics_layout_colorized内で使用

    # 統一フィルターから期間設定を取得
    start_date_ts, end_date_ts, period_description = get_analysis_period()

    if start_date_ts is None or end_date_ts is None:
        st.error("分析期間が設定されていません。サイドバーの「分析フィルター」で期間を設定してください。")
        return

    # 選択期間のKPIを計算
    df_selected_period = df_original[(df_original['日付'] >= start_date_ts) & (df_original['日付'] <= end_date_ts)]
    kpis_selected = calculate_kpis(df_selected_period, start_date_ts, end_date_ts, total_beds=total_beds) if calculate_kpis else {}

    if not kpis_selected or kpis_selected.get("error"):
        st.warning(f"選択期間のKPI計算に失敗: {kpis_selected.get('error', '不明') if kpis_selected else '不明'}")
        # グラフなしでKPIカードだけ表示する場合、ここで metrics_for_display を構築して表示を試みるか、return する
        # 今回は display_unified_metrics_layout_colorized がグラフも含むため、ここで return するのが無難
        return


    # 「直近30日」のKPIを計算 (display_unified_metrics_layout_colorized が期待するため)
    latest_date_in_data = df_original['日付'].max()
    start_30d = latest_date_in_data - pd.Timedelta(days=29)
    end_30d = latest_date_in_data # end_30d を定義
    df_30d = df_original[(df_original['日付'] >= start_30d) & (df_original['日付'] <= end_30d)] # end_30d を使用
    kpis_30d = calculate_kpis(df_30d, start_30d, end_30d, total_beds=total_beds) if calculate_kpis and not df_30d.empty else {}


    # display_unified_metrics_layout_colorized に渡す metrics 辞書を構築
    metrics_for_display = {
        'avg_daily_census': kpis_selected.get('avg_daily_census'),
        'avg_daily_census_30d': kpis_30d.get('avg_daily_census'),
        'bed_occupancy_rate': kpis_selected.get('bed_occupancy_rate'), # 選択期間の利用率を表示するように変更
        'avg_los': kpis_selected.get('alos'),
        'estimated_revenue': kpis_selected.get('total_patient_days', 0) * st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE),
        'total_patient_days': kpis_selected.get('total_patient_days'),
        # 'estimated_revenue_30d': kpis_30d.get('total_patient_days', 0) * st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE), # もし30日収益も必要なら
        # 'total_patient_days_30d': kpis_30d.get('total_patient_days'), # もし30日延べ患者数も必要なら
        'avg_daily_admissions': kpis_selected.get('avg_daily_admissions'),
        'period_days': kpis_selected.get('days_count'),
        'total_beds': total_beds,
        # 'target_revenue' は display_unified_metrics_layout_colorized の中で計算されるか、セッションから取得される
    }

    if display_unified_metrics_layout_colorized:
        display_unified_metrics_layout_colorized(metrics_for_display, period_description)
        # 経営ダッシュボードではグラフは表示しないため、display_trend_graphs_only の呼び出しは行わない
    else:
        st.error("KPI表示機能が利用できません。dashboard_overview_tab.pyを確認してください。")


def main():
    if 'app_initialized' not in st.session_state:
        st.session_state.app_initialized = True

    if 'data_processed' not in st.session_state: st.session_state['data_processed'] = False
    if 'df' not in st.session_state: st.session_state['df'] = None
    if 'forecast_model_results' not in st.session_state: st.session_state.forecast_model_results = {}

    auto_loaded = auto_load_data()
    if auto_loaded and st.session_state.get('df') is not None:
        st.success(MESSAGES['auto_load_success'])
        if 'target_data' not in st.session_state: st.session_state.target_data = None
        initialize_all_mappings(st.session_state.df, st.session_state.target_data)


    st.markdown(f'<h1 class="main-header">{APP_ICON} {APP_TITLE}</h1>', unsafe_allow_html=True)

    settings_valid = create_sidebar()

    tab_names = ["💰 経営ダッシュボード"]
    if FORECAST_AVAILABLE: tab_names.append("🔮 予測分析")
    tab_names.extend(["📈 詳細分析", "📋 データテーブル", "📄 PDF出力", "📊 データ処理"])

    tabs = st.tabs(tab_names)

    with tabs[-1]: # データ処理タブ
        try:
            create_data_processing_tab()
            if st.session_state.get('data_processed') and st.session_state.get('df') is not None \
               and not st.session_state.get('mappings_initialized_after_processing', False):
                initialize_all_mappings(st.session_state.df, st.session_state.get('target_data'))
                st.session_state.mappings_initialized_after_processing = True
        except Exception as e:
            st.error(f"データ処理タブでエラー: {str(e)}\n{traceback.format_exc()}")


    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        with tabs[0]: # 経営ダッシュボードタブ
            try:
                create_management_dashboard_tab()
            except Exception as e:
                st.error(f"経営ダッシュボードでエラー: {str(e)}\n{traceback.format_exc()}")

        tab_offset = 0
        if FORECAST_AVAILABLE:
            with tabs[1]:
                try:
                    deps_ok = check_forecast_dependencies()
                    if deps_ok: display_forecast_analysis_tab()
                    else: st.info(MESSAGES['forecast_libs_missing'])
                except Exception as e:
                    st.error(f"予測分析でエラー: {str(e)}\n{traceback.format_exc()}")
            tab_offset = 1

        with tabs[1 + tab_offset]: # 詳細分析タブ
            try:
                create_detailed_analysis_tab()
            except Exception as e:
                st.error(f"詳細分析でエラー: {str(e)}\n{traceback.format_exc()}")

        with tabs[2 + tab_offset]: # データテーブルタブ
            try:
                create_data_tables_tab()
            except Exception as e:
                st.error(f"データテーブルでエラー: {str(e)}\n{traceback.format_exc()}")

        with tabs[3 + tab_offset]: # PDF出力タブ
            try:
                pdf_output_tab.create_pdf_output_tab()
            except Exception as e:
                st.error(f"PDF出力機能でエラー: {str(e)}\n{traceback.format_exc()}")

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
    if 'mappings_initialized_after_processing' not in st.session_state:
        st.session_state.mappings_initialized_after_processing = False
    main()