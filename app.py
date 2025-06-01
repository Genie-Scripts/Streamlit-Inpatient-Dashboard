import streamlit as st
import pandas as pd
import numpy as np # 必要に応じて
import plotly.express as px # 必要に応じて
import plotly.graph_objects as go # 必要に応じて
import traceback # ★★★ この行を追加 ★★★
from plotly.subplots import make_subplots # 必要に応じて
import datetime
# try:
#     import jpholiday # jpholiday は forecast.py や integrated_preprocessing.py で使用
#     JPHOLIDAY_AVAILABLE = True
# except ImportError:
#     JPHOLIDAY_AVAILABLE = False

# from scipy import stats # dashboard_overview_tab.py で使用される想定だったが、app.pyでは直接不要か

# ===== 設定値とスタイルの読み込み =====
from config import *
from style import inject_global_css
from utils import safe_date_filter, initialize_all_mappings # safe_date_filter は app.py では直接使われていない可能性

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
    # from integrated_preprocessing import integrated_preprocess_data # data_processing_tab.py で使用
    # from loader import load_files # data_processing_tab.py で使用
    # from revenue_dashboard_tab import create_revenue_dashboard_section # 今回は create_management_dashboard_tab で代替
    from analysis_tabs import create_detailed_analysis_tab, create_data_tables_tab
    from data_processing_tab import create_data_processing_tab
    # from pdf_output_tab import create_pdf_output_tab # pdf_output_tab.py を直接インポート
    import pdf_output_tab # モジュールとしてインポート
    from forecast_analysis_tab import display_forecast_analysis_tab
    from kpi_calculator import calculate_kpis
    # dashboard_overview_tab から経営ダッシュボードの主要機能を取り込むか、別途管理
    from dashboard_overview_tab import display_dashboard_overview
    # unified_filters のインポートを確認
    from unified_filters import create_unified_filter_sidebar, apply_unified_filters, get_unified_filter_summary, initialize_unified_filters, get_unified_filter_config, validate_unified_filters


    FORECAST_AVAILABLE = True # display_forecast_analysis_tab がインポートできればTrue
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.error(traceback.format_exc()) # 詳細なエラー表示
    FORECAST_AVAILABLE = False
    # 失敗した場合のフォールバック関数や変数を定義
    create_detailed_analysis_tab = lambda: st.error("詳細分析機能は利用できません。")
    create_data_tables_tab = lambda: st.error("データテーブル機能は利用できません。")
    create_data_processing_tab = lambda: st.error("データ処理機能は利用できません。")
    pdf_output_tab = type('pdf_output_tab_mock', (object,), {'create_pdf_output_tab': lambda: st.error("PDF出力機能は利用できません。")})()
    display_forecast_analysis_tab = lambda: st.error("予測分析機能は利用できません。")
    calculate_kpis = None
    display_dashboard_overview = lambda df, start_date, end_date, total_beds_setting, target_occupancy_setting: st.error("経営ダッシュボード機能は利用できません。")
    create_unified_filter_sidebar = lambda df: None
    apply_unified_filters = lambda df: df
    get_unified_filter_summary = lambda: "フィルター情報取得不可"
    initialize_unified_filters = lambda df: None
    get_unified_filter_config = lambda: {}
    validate_unified_filters = lambda df: (False, "フィルター検証機能利用不可")
    # st.stop() # 致命的なエラーでなければ停止させない方が良い場合も

# def create_sidebar_period_settings(): # ★★★ この関数は unified_filters.py の期間設定と重複するため削除または役割変更 ★★★
#     """サイドバーの期間設定（app.py内）"""
#     # unified_filters.py の create_unified_sidebar で期間設定UIが提供されるため、
#     # この関数は原則として不要になる。
#     # もし特定のタブ（例：経営ダッシュボード）で unified_filter とは独立した簡易期間選択が必要な場合は、
#     # そのタブのロジック内でUIを作成するか、この関数を大幅に簡略化して特定の目的に特化させる。
#     # 今回は unified_filters で統一するため、この関数の主要なロジックは unified_filters.py に移管されていると見なす。
#     pass


def calculate_preset_period_dates(df, preset_period):
    """プリセット期間から具体的な日付を計算 (unified_filters.py にも同様の機能があるため、統合を検討)"""
    if df is None or df.empty or '日付' not in df.columns:
        # データがない場合は、今日を基準とした仮の期間を返すか、エラーとする
        today = pd.Timestamp.now().normalize()
        if preset_period == "直近30日":
            return today - pd.Timedelta(days=29), today
        # 他のプリセットについてもフォールバックを定義
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
        return start_date_ts.normalize(), end_date_ts.normalize() # 前月完了分は end_date も計算
    elif preset_period == "今年度":
        current_year = latest_date.year
        if latest_date.month >= 4: # 4月以降なら当年4月1日開始
            start_date_ts = pd.Timestamp(f"{current_year}-04-01")
        else: # 3月以前なら前年4月1日開始
            start_date_ts = pd.Timestamp(f"{current_year-1}-04-01")
    else:  # デフォルト (直近30日など)
        start_date_ts = latest_date - pd.Timedelta(days=29)

    # 開始日がデータ全体の最小日より前にならないように調整
    start_date_ts = max(start_date_ts, min_data_date)
    return start_date_ts.normalize(), latest_date.normalize()


def get_analysis_period():
    """
    現在の分析期間を取得 (unified_filters.py の設定を正として取得する)
    戻り値: (pd.Timestamp or None, pd.Timestamp or None, str)
            (start_date, end_date, period_description)
    """
    if not st.session_state.get('data_processed', False):
        return None, None, "データ未処理"

    filter_config = get_unified_filter_config() # unified_filters.py から現在の設定を取得

    if filter_config and 'start_date' in filter_config and 'end_date' in filter_config:
        start_date_ts = pd.Timestamp(filter_config['start_date']).normalize()
        end_date_ts = pd.Timestamp(filter_config['end_date']).normalize()

        if filter_config.get('period_mode') == "プリセット期間" and filter_config.get('preset'):
            period_description = filter_config['preset']
        else:
            period_description = f"{start_date_ts.strftime('%Y/%m/%d')}～{end_date_ts.strftime('%Y/%m/%d')}"
        return start_date_ts, end_date_ts, period_description
    else:
        # フォールバック：データ処理タブなどで st.session_state に直接設定された期間情報があればそれを使う
        # ただし、基本は unified_filters の設定を信頼する
        df = st.session_state.get('df')
        if df is not None and not df.empty and '日付' in df.columns:
            latest_date = df['日付'].max()
            default_start_ts = (latest_date - pd.Timedelta(days=29)).normalize()
            st.session_state['unified_filter_start_date'] = default_start_ts # 仮でセッションに設定（望ましくない）
            st.session_state['unified_filter_end_date'] = latest_date.normalize() # 仮でセッションに設定（望ましくない）
            return default_start_ts, latest_date.normalize(), "デフォルト期間 (直近30日)"
        return None, None, "期間未設定"


def filter_data_by_analysis_period(df_original):
    """
    分析期間でデータをフィルタリング (unified_filters.py の apply_unified_filters を使用)
    """
    if df_original is None or df_original.empty:
        return pd.DataFrame() # 空のDFを返す

    # unified_filters.py の apply_unified_filters は、
    # セッションに保存されたフィルター設定 (`get_unified_filter_config()` で取得できるもの) を使って
    # フィルタリングを行うはず。
    # create_unified_filter_sidebar が呼ばれた後に、この設定はセッションに保存される。
    return apply_unified_filters(df_original)


def check_forecast_dependencies():
    """予測機能に必要な依存関係をチェック"""
    # ... (既存のコード)
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

# display_trend_analysis, display_period_comparison_charts は dashboard_overview_tab.py にある想定
# format_number_with_config, display_unified_metrics_layout_colorized も dashboard_overview_tab.py や revenue_dashboard_tab.py にある想定

def create_sidebar_data_settings():
    """サイドバーのデータ設定セクション"""
    # ... (既存のコード)
    st.sidebar.header("💾 データ設定")
    with st.sidebar.expander("📊 現在のデータ状況", expanded=True):
        # ... (略) ...
        pass # 既存のコードを想定
    with st.sidebar.expander("🔧 データ操作", expanded=False):
        # ... (略) ...
        pass # 既存のコードを想定
    with st.sidebar.expander("🗂️ バックアップ管理", expanded=False):
        # ... (略) ...
        pass # 既存のコードを想定
    with st.sidebar.expander("📤 簡易データアップロード", expanded=False):
        # ... (略) ...
        pass # 既存のコードを想定

    
    # データ操作
    with st.sidebar.expander("🔧 データ操作", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 データ保存", key="save_current_data", use_container_width=True):
                if st.session_state.get('data_processed', False):
                    df = st.session_state.get('df')
                    target_data = st.session_state.get('target_data')
                    
                    if save_data_to_file(df, target_data):
                        st.success("保存完了!")
                        st.experimental_rerun()
                    else:
                        st.error("保存失敗")
                else:
                    st.warning("保存するデータがありません")
        
        with col2:
            if st.button("🗑️ データ削除", key="delete_saved_data", use_container_width=True):
                success, result = delete_saved_data()
                if success:
                    st.success(f"削除完了")
                    # セッション状態もクリア
                    keys_to_clear = ['df', 'target_data', 'data_processed', 'data_source', 'data_metadata']
                    for key in keys_to_clear:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.experimental_rerun()
                else:
                    st.error(f"削除失敗: {result}")
        
        # ファイルサイズ情報
        file_sizes = get_file_sizes()
        if any(size != "未保存" for size in file_sizes.values()):
            st.write("📁 **ファイルサイズ:**")
            for name, size in file_sizes.items():
                if size != "未保存":
                    st.write(f"  • {name}: {size}")
    
    # バックアップ管理
    with st.sidebar.expander("🗂️ バックアップ管理", expanded=False):
        backup_info = get_backup_info()
        if backup_info:
            st.write("📋 **利用可能なバックアップ:**")
            for backup in backup_info:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"📄 {backup['timestamp']}")
                    st.caption(f"サイズ: {backup['size']}")
                with col2:
                    if st.button("復元", key=f"restore_{backup['filename']}", use_container_width=True):
                        success, message = restore_from_backup(backup['filename'])
                        if success:
                            st.success(message)
                            st.experimental_rerun()
                        else:
                            st.error(message)
        else:
            st.info("バックアップファイルはありません")
    
    # 新しいデータのアップロード
    with st.sidebar.expander("📤 簡易データアップロード", expanded=False):
        st.write("**簡易的なファイル読み込み**")
        st.caption("詳細な処理は「データ処理」タブを使用")
        
        # 直接ファイルアップロード（簡易版）
        uploaded_file = st.file_uploader(
            "ファイルを選択",
            type=SUPPORTED_FILE_TYPES,
            key="sidebar_file_upload",
            help="Excel/CSVファイルをアップロード"
        )
        
        if uploaded_file is not None:
            if st.button("⚡ 簡易処理で読み込む", key="quick_process", use_container_width=True):
                try:
                    # 簡易的なファイル読み込み
                    if uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(uploaded_file, encoding='utf-8')
                    else:
                        df = pd.read_excel(uploaded_file)
                    
                    # 基本的な前処理
                    if '日付' in df.columns:
                        df['日付'] = pd.to_datetime(df['日付'])
                    
                    # セッション状態に保存
                    st.session_state['df'] = df
                    st.session_state['data_processed'] = True
                    st.session_state['data_source'] = 'sidebar_upload'
                    st.session_state['target_data'] = None
                    
                    if '日付' in df.columns:
                        latest_date = df['日付'].max()
                        st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                    
                    st.success("簡易読み込み完了!")
                    st.experimental_rerun()
                    
                except Exception as e:
                    st.error(f"読み込みエラー: {e}")

def create_sidebar():
    """サイドバーの設定UI（改修版）"""
    create_sidebar_data_settings() # データ設定は一番上でも良いかもしれません

    st.sidebar.markdown("---")
    # 「基本設定」と「目標値設定」はグローバルな設定として残す
    st.sidebar.header("⚙️ グローバル設定")
    with st.sidebar.expander("🏥 基本病院設定", expanded=True):
        # ... (既存の total_beds, bed_occupancy_rate, avg_length_of_stay, avg_admission_fee のUI)
        # (st.session_state への保存ロジックも含む)
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
        
        if st.button("💾 グローバル設定を保存", key="save_global_settings"): # キー変更
            settings_to_save = {
                'total_beds': total_beds, 'bed_occupancy_rate': bed_occupancy_rate,
                'bed_occupancy_rate_percent': int(bed_occupancy_rate * 100),
                'avg_length_of_stay': avg_length_of_stay, 'avg_admission_fee': avg_admission_fee
            }
             # 目標値設定もここで一緒に保存するなら追加
            if 'monthly_target_patient_days' in st.session_state:
                settings_to_save['monthly_target_patient_days'] = st.session_state.monthly_target_patient_days
            if 'monthly_target_admissions' in st.session_state:
                settings_to_save['monthly_target_admissions'] = st.session_state.monthly_target_admissions

            if save_settings_to_file(settings_to_save): st.success("設定保存完了!")
            else: st.error("設定保存失敗")

    with st.sidebar.expander("🎯 KPI目標値設定", expanded=False): # 展開状態を調整
        # ... (既存の monthly_target_patient_days, monthly_target_admissions のUI)
        # (st.session_state への保存ロジックも含む)
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

        # サマリー表示は削除、またはメイン画面のKPIカードで確認するように促す
        # st.markdown("### 📈 目標値サマリー")
        # ... (メトリクス表示はここでは不要かも) ...

    st.sidebar.markdown("---")
    # 「統一分析フィルター」は unified_filters.py から呼び出す
    # これは create_detailed_analysis_tab など、分析系タブを表示する際に呼び出される想定
    # 全てのタブで常に表示させたい場合は、main() 関数の最初の方で st.session_state.df の存在を確認後に呼び出す
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        df_for_filter_init = st.session_state.get('df')
        initialize_unified_filters(df_for_filter_init) # フィルターのデフォルト値をデータに基づいて初期化
        filter_config = create_unified_filter_sidebar(df_for_filter_init) # これがフィルターUIを描画し、設定を返す
        if filter_config:
            st.session_state['current_unified_filter_config'] = filter_config # 必要ならセッションに保存
    else:
        st.sidebar.info("データを読み込むと分析フィルターが表示されます。")

    # settings_valid の判定ロジックは、グローバル設定が入力されているかで判定
    # return (total_beds > 0 and bed_occupancy_rate > 0 and avg_length_of_stay > 0 and avg_admission_fee > 0)
    # 統一フィルターが適用されるまでは settings_valid は True としても良いかもしれない
    return True


def create_management_dashboard_tab():
    """経営ダッシュボードタブ（期間設定を統一フィルターに合わせる）"""
    st.header(f"{APP_ICON} 経営ダッシュボード") # アイコンをAPP_ICONから取得

    if not st.session_state.get('data_processed', False) or st.session_state.get('df') is None:
        st.warning(MESSAGES['data_not_loaded'])
        return

    df_original = st.session_state.get('df')
    
    # 統一フィルターから期間設定を取得
    start_date_ts, end_date_ts, period_description = get_analysis_period()

    if start_date_ts is None or end_date_ts is None:
        st.error("分析期間が設定されていません。サイドバーの「分析フィルター」で期間を設定してください。")
        return

    st.info(f"📊 分析期間: {period_description} ({start_date_ts.strftime('%Y/%m/%d')} ～ {end_date_ts.strftime('%Y/%m/%d')})")
    st.caption("※期間はサイドバーの「分析フィルター」で変更できます。")

    # 統一フィルターを適用してダッシュボード用のデータを取得
    # 注意: display_dashboard_overview はフィルタリング前のdfと期間を引数に取る想定なので、
    #       ここではフィルタリング前のdf_originalと、統一フィルターで決定された期間を渡す。
    #       display_dashboard_overview 内部で、その期間を使ってKPIを計算する。
    #       あるいは、ここで df_filtered = filter_data_by_analysis_period(df_original) を行い、
    #       display_dashboard_overview がフィルタリング済みdfを期待するように変更する。
    #       後者の方が一貫性がある。
    
    df_for_dashboard = filter_data_by_analysis_period(df_original) # 統一フィルターを適用

    if df_for_dashboard.empty:
        st.warning("選択されたフィルター条件に合致するデータがありません。")
        return

    total_beds = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)
    target_occupancy_rate = st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE) * 100 # %に変換

    # display_dashboard_overview はフィルタリング済みのdfと、そのdfに対応する期間を渡す
    # get_analysis_period() が返す期間は、df_for_dashboard の期間と一致するはず
    display_dashboard_overview(df_for_dashboard, start_date_ts, end_date_ts, total_beds, target_occupancy_rate)


def main():
    """メイン関数（改修版）"""
    if 'app_initialized' not in st.session_state:
        # ... (既存の初回起動時の日付クリア処理) ...
        st.session_state.app_initialized = True

    if 'data_processed' not in st.session_state: st.session_state['data_processed'] = False
    if 'df' not in st.session_state: st.session_state['df'] = None
    if 'forecast_model_results' not in st.session_state: st.session_state.forecast_model_results = {}

    auto_loaded = auto_load_data()
    if auto_loaded and not st.session_state.get('df') is None: # auto_load後、dfがあることを確認
        st.success(MESSAGES['auto_load_success'])
        # マッピング初期化 (データロード後)
        if 'target_data' not in st.session_state: st.session_state.target_data = None # target_dataもロードされる想定
        initialize_all_mappings(st.session_state.df, st.session_state.target_data)


    st.markdown(f'<h1 class="main-header">{APP_ICON} {APP_TITLE}</h1>', unsafe_allow_html=True)
    
    # サイドバー設定 (統一フィルターUIの呼び出しも含む)
    settings_valid = create_sidebar() # create_sidebar内で統一フィルターUIが描画される
    if not settings_valid: # グローバル設定が妥当でない場合は停止（オプション）
        # st.sidebar.error("グローバル設定に不備があります。")
        # st.stop()
        pass


    tab_names = ["💰 経営ダッシュボード"]
    if FORECAST_AVAILABLE: tab_names.append("🔮 予測分析")
    tab_names.extend(["📈 詳細分析", "📋 データテーブル", "📄 PDF出力", "📊 データ処理"]) # PDF出力を修正

    tabs = st.tabs(tab_names)

    # データ処理タブは常にアクセス可能とし、最初に表示させることも検討
    with tabs[-1]: # データ処理タブ
        try:
            create_data_processing_tab()
            # データ処理タブでデータがロード/処理された後にマッピングを初期化
            if st.session_state.get('data_processed') and st.session_state.get('df') is not None \
               and not st.session_state.get('mappings_initialized_after_processing', False):
                initialize_all_mappings(st.session_state.df, st.session_state.get('target_data'))
                st.session_state.mappings_initialized_after_processing = True # 初期化済みフラグ
        except Exception as e:
            st.error(f"データ処理タブでエラー: {str(e)}\n{traceback.format_exc()}")


    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        # 経営ダッシュボードタブ
        with tabs[0]:
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
                # 詳細分析タブ内で create_unified_filter_sidebar が呼ばれ、
                # その設定に基づいて apply_unified_filters が適用されたデータが使われる
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
                pdf_output_tab.create_pdf_output_tab() # モジュール名経由で呼び出し
            except Exception as e:
                st.error(f"PDF出力機能でエラー: {str(e)}\n{traceback.format_exc()}")
    
    else: # データ未処理の場合
        for i in range(len(tabs) - 1): # データ処理タブ以外
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
    # 開発メモの初期化フラグも考慮
    if 'mappings_initialized_after_processing' not in st.session_state:
        st.session_state.mappings_initialized_after_processing = False
    main()