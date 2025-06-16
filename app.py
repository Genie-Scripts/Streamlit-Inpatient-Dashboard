import streamlit as st
import pandas as pd
import numpy as np
import datetime
import traceback

# ===== ページ設定 (スクリプトの最初に移動) と config.py のインポート =====
# config.py を st.set_page_config より先にインポート
from config import *

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== 設定値とスタイルの読み込み =====
from style import inject_global_css
from utils import initialize_all_mappings

# データ永続化機能のインポート
from data_persistence import (
    auto_load_data, save_data_to_file, load_data_from_file,
    get_data_info, delete_saved_data, get_file_sizes,
    save_settings_to_file, load_settings_from_file,
    get_backup_info, restore_from_backup
)

# レスポンシブデザイン機能のインポート（新規追加）
RESPONSIVE_FEATURES_AVAILABLE = False
try:
    from responsive_style import inject_responsive_css, get_mobile_navigation_html
    from mobile_utils import (
        create_responsive_columns,
        create_mobile_friendly_dataframe,
        create_mobile_sidebar_toggle,
        optimize_chart_for_mobile,
        get_device_info,
        create_mobile_metric_card,
        create_swipeable_tabs
    )
    RESPONSIVE_FEATURES_AVAILABLE = True
except ImportError as e:
    print(f"レスポンシブ機能のインポートエラー: {e}")
    print("レスポンシブ機能を使用するには responsive_style.py と mobile_utils.py が必要です")
    
    # フォールバック関数の定義
    def inject_responsive_css(): 
        """レスポンシブCSSの注入（フォールバック）"""
        pass
    
    def create_mobile_sidebar_toggle(): 
        """モバイルサイドバートグル（フォールバック）"""
        pass
    
    def create_responsive_columns(num_columns, mobile_columns=1):
        """レスポンシブカラム作成（フォールバック）"""
        return st.columns(num_columns)
    
    def create_mobile_friendly_dataframe(df, key=None):
        """モバイルフレンドリーなデータフレーム表示（フォールバック）"""
        st.dataframe(df, key=key, use_container_width=True)
    
    def optimize_chart_for_mobile(fig, is_mobile=False):
        """チャートのモバイル最適化（フォールバック）"""
        return fig
    
    def get_device_info():
        """デバイス情報取得（フォールバック）"""
        return {'is_mobile': False, 'is_tablet': False, 'is_desktop': True}

# カスタムモジュールのインポート (エラー時のフォールバックも含む)
try:
    from analysis_tabs import create_data_tables_tab
    from data_processing_tab import create_data_processing_tab
    import pdf_output_tab
    from forecast_analysis_tab import display_forecast_analysis_tab
    from kpi_calculator import calculate_kpis
    from dashboard_overview_tab import display_kpi_cards_only
    from unified_filters import (create_unified_filter_sidebar, apply_unified_filters,
                                 get_unified_filter_summary, initialize_unified_filters,
                                 get_unified_filter_config, validate_unified_filters)
    from alos_analysis_tab import display_alos_analysis_tab
    from dow_analysis_tab import display_dow_analysis_tab
    from individual_analysis_tab import display_individual_analysis_tab
    from analysis_tabs import create_individual_analysis_section

    FORECAST_AVAILABLE = True
except ImportError as e:
    problematic_imports = e
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.error(traceback.format_exc())
    FORECAST_AVAILABLE = False
    create_data_tables_tab = lambda: st.error("データテーブル機能は利用できません。")
    create_data_processing_tab = lambda: st.error("データ処理機能は利用できません。")
    pdf_output_tab = type('pdf_output_tab_mock', (object,), {'create_pdf_output_tab': lambda: st.error("PDF出力機能は利用できません。")})()
    display_forecast_analysis_tab = lambda: st.error("予測分析機能は利用できません。")
    calculate_kpis = None
    display_kpi_cards_only = lambda df, start_date, end_date, total_beds, target_occupancy_setting: st.error("経営ダッシュボードKPI表示機能は利用できません。")
    create_unified_filter_sidebar = lambda df: None
    apply_unified_filters = lambda df: df
    get_unified_filter_summary = lambda: "フィルター情報取得不可"
    initialize_unified_filters = lambda df: None
    get_unified_filter_config = lambda: {}
    validate_unified_filters = lambda df: (False, "フィルター検証機能利用不可")
    display_alos_analysis_tab = lambda df_filtered_by_period, start_date_ts, end_date_ts, common_config=None: st.error("平均在院日数分析機能は利用できません。")
    display_dow_analysis_tab = lambda df, start_date, end_date, common_config=None: st.error("曜日別入退院分析機能は利用できません。")
    display_individual_analysis_tab = lambda df_filtered_main: st.error("個別分析機能は利用できません。")
    create_individual_analysis_section = lambda df_filtered, filter_config_from_caller: st.error("個別分析セクション機能は利用できません。")

try:
    from department_performance_tab import create_department_performance_tab
    DEPT_PERFORMANCE_AVAILABLE = True
except ImportError as e:
    st.error(f"診療科別パフォーマンスタブのインポートに失敗しました: {e}")
    DEPT_PERFORMANCE_AVAILABLE = False
    create_department_performance_tab = lambda: st.error("診療科別パフォーマンス機能は利用できません。")

try:
    from ward_performance_tab import create_ward_performance_tab
    WARD_PERFORMANCE_AVAILABLE = True
except ImportError as e:
    st.error(f"病棟別パフォーマンスタブのインポートに失敗しました: {e}")
    WARD_PERFORMANCE_AVAILABLE = False
    create_ward_performance_tab = lambda: st.error("病棟別パフォーマンス機能は利用できません。")

# グローバルCSSの注入（既存）
inject_global_css(FONT_SCALE)

# レスポンシブCSSの注入（新規追加）
if RESPONSIVE_FEATURES_AVAILABLE:
    inject_responsive_css()
    # モバイルナビゲーションの追加
    st.markdown(get_mobile_navigation_html() if 'get_mobile_navigation_html' in globals() else "", unsafe_allow_html=True)

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

# --- サイドバーセクション作成関数の定義 (create_sidebar より前に定義) ---
def create_sidebar_data_settings():
    """サイドバーのデータ設定セクション（既存コードベース強化版）"""
    st.sidebar.header("💾 データ設定")
    
    # 現在のデータ状況表示（強化版）
    with st.sidebar.expander("📊 現在のデータ状況", expanded=True):
        if st.session_state.get('data_processed', False):
            df = st.session_state.get('df')
            if df is not None:
                data_source = st.session_state.get('data_source', 'unknown')
                latest_date_str = st.session_state.get('latest_data_date_str', '不明')
                st.success("✅ データ読み込み済み")
                st.write(f"📅 最新日付: {latest_date_str}")
                st.write(f"📊 レコード数: {len(df):,}件")
                
                # データソース表示（強化）
                source_text = {
                    'auto_loaded': '自動読み込み', 
                    'manual_loaded': '手動読み込み', 
                    'sidebar_upload': 'サイドバー',
                    'data_processing_tab': 'データ入力タブ',
                    'incremental_add': '追加読み込み',
                    'unknown': '不明'
                }.get(data_source, '不明')
                st.write(f"🔄 読み込み元: {source_text}")
                
                # データ期間情報（新規追加）
                if '日付' in df.columns and not df['日付'].empty:
                    min_date = df['日付'].min()
                    max_date = df['日付'].max()
                    period_days = (max_date - min_date).days + 1
                    st.write(f"📅 データ期間: {period_days}日間")
                    st.caption(f"{min_date.strftime('%Y/%m/%d')} ～ {max_date.strftime('%Y/%m/%d')}")
                
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
                    st.warning("⚠️ 未保存データ")
            else:
                st.warning("⚠️ データ処理エラー")
        else:
            st.info("📂 データ未読み込み")
            data_info = get_data_info()
            if data_info:
                st.write("💾 保存済みデータあり")
                # 保存データの詳細情報（新規追加）
                try:
                    st.caption(f"📊 {data_info.get('data_rows', 0):,}件")
                    if data_info.get('file_size_mb'):
                        st.caption(f"📁 {data_info['file_size_mb']} MB")
                    
                    # 日付範囲情報
                    date_range = data_info.get('date_range', {})
                    if date_range.get('min_date') and date_range.get('max_date'):
                        min_dt = datetime.datetime.fromisoformat(date_range['min_date'])
                        max_dt = datetime.datetime.fromisoformat(date_range['max_date'])
                        st.caption(f"📅 {min_dt.strftime('%Y/%m/%d')} ～ {max_dt.strftime('%Y/%m/%d')}")
                except Exception:
                    pass
                
                if st.button("🔄 保存データを読み込む", key="load_saved_data_sidebar_enhanced_v2", use_container_width=True):
                    df_loaded, target_data_loaded, metadata_loaded = load_data_from_file()
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

    # データ操作（強化版）
    with st.sidebar.expander("🔧 データ操作", expanded=False):
        # 基本操作（保存・読込）
        st.markdown("**📁 基本操作**")
        col1_ds, col2_ds = st.columns(2)
        
        with col1_ds:
            if st.button("💾 保存", key="save_current_data_sidebar_enhanced_v2", use_container_width=True):
                if st.session_state.get('data_processed', False):
                    df_to_save = st.session_state.get('df')
                    target_data_to_save = st.session_state.get('target_data')
                    
                    # 保存時にメタデータを追加
                    enhanced_metadata = {
                        'save_timestamp': datetime.datetime.now().isoformat(),
                        'data_source': st.session_state.get('data_source', 'unknown'),
                        'processing_info': st.session_state.get('performance_metrics', {}),
                        'filter_state': st.session_state.get('current_unified_filter_config', {}),
                    }
                    
                    if save_data_to_file(df_to_save, target_data_to_save, enhanced_metadata):
                        st.success("✅ 保存完了!")
                        st.rerun()
                    else:
                        st.error("❌ 保存失敗")
                else:
                    st.warning("保存するデータがありません")
        
        with col2_ds:
            if st.button("📥 読込", key="load_saved_data_manual_v2", use_container_width=True):
                df_loaded, target_data_loaded, metadata_loaded = load_data_from_file()
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
                    if st.session_state.df is not None and not st.session_state.df.empty:
                        initialize_unified_filters(st.session_state.df)
                    
                    st.success("✅ 読込完了!")
                    st.rerun()
                else:
                    st.error("❌ 読込失敗")

        # 追加データ読み込み機能（新規）
        if st.session_state.get('data_processed', False):
            st.markdown("---")
            st.markdown("**➕ 追加データ読み込み**")
            st.caption("現在のデータに新しいデータを追加")
            
            additional_file = st.file_uploader(
                "追加ファイル", 
                type=["xlsx", "xls", "csv"], 
                key="additional_data_upload_sidebar_v2",
                help="現在のデータに追加するファイル"
            )
            
            if additional_file is not None:
                col_mode, col_exec = st.columns(2)
                
                with col_mode:
                    merge_mode = st.selectbox(
                        "結合方式",
                        ["追加", "更新"],
                        key="merge_mode_sidebar_v2",
                        help="追加: 単純結合、更新: 既存データ更新"
                    )
                
                with col_exec:
                    if st.button("🔄 実行", key="execute_additional_load_sidebar_v2", use_container_width=True):
                        try:
                            # 追加ファイルの読み込み
                            if additional_file.name.endswith('.csv'):
                                df_additional = pd.read_csv(additional_file, encoding='utf-8')
                            else:
                                df_additional = pd.read_excel(additional_file)
                            
                            # 日付列の正規化
                            if '日付' in df_additional.columns:
                                df_additional['日付'] = pd.to_datetime(df_additional['日付'], errors='coerce').dt.normalize()
                                df_additional.dropna(subset=['日付'], inplace=True)
                            
                            current_df = st.session_state.get('df')
                            combined_df = None  # 初期化
                            
                            if merge_mode == "追加":
                                combined_df = pd.concat([current_df, df_additional], ignore_index=True)
                                combined_df.drop_duplicates(inplace=True)
                                
                            elif merge_mode == "更新":
                                if all(col in df_additional.columns for col in ['日付', '病棟コード', '診療科名']):
                                    merge_keys = ['日付', '病棟コード', '診療科名']
                                    df_additional_keys = df_additional[merge_keys].drop_duplicates()
                                    
                                    mask = current_df.set_index(merge_keys).index.isin(
                                        df_additional_keys.set_index(merge_keys).index
                                    )
                                    df_remaining = current_df[~mask].reset_index(drop=True)
                                    combined_df = pd.concat([df_remaining, df_additional], ignore_index=True)
                                else:
                                    st.error("更新モードには日付、病棟コード、診療科名の列が必要です")
                                    combined_df = None
                            
                            # 正常に結合できた場合のみセッション状態を更新
                            if combined_df is not None:
                                # セッション状態の更新
                                st.session_state['df'] = combined_df
                                st.session_state['data_source'] = 'incremental_add'
                                
                                if '日付' in combined_df.columns and not combined_df['日付'].empty:
                                    latest_date = combined_df['日付'].max()
                                    st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                                
                                # マッピングとフィルターの再初期化
                                initialize_all_mappings(st.session_state.df, st.session_state.target_data)
                                initialize_unified_filters(st.session_state.df)
                                
                                st.success(f"✅ {merge_mode}完了! レコード数: {len(combined_df):,}件")
                                st.rerun()
                            
                        except Exception as e:
                            st.error(f"❌ 追加読み込みエラー: {str(e)}")

        # リセット機能（強化版）
        st.markdown("---")
        st.markdown("**🔄 データリセット**")
        
        col_reset1, col_reset2 = st.columns(2)
        
        with col_reset1:
            if st.button("🔄 セッション\nクリア", key="reset_session_sidebar_v2", use_container_width=True):
                keys_to_clear = [
                    'df', 'target_data', 'data_processed', 'data_source', 'data_metadata',
                    'latest_data_date_str', 'all_results', 'current_unified_filter_config',
                    'mappings_initialized_after_processing', 'unified_filter_initialized',
                    'validation_results', 'performance_metrics'
                ]
                for key in keys_to_clear:
                    if key in st.session_state:
                        del st.session_state[key]
                
                st.success("✅ セッションクリア完了")
                st.info("💾 保存データは維持されています")
                st.rerun()
        
        with col_reset2:
            if st.button("🗑️ 完全\n削除", key="delete_all_data_sidebar_v2", use_container_width=True):
                if st.session_state.get('confirm_delete_ready', False):
                    success, result = delete_saved_data()
                    if success:
                        st.success("✅ 完全削除完了")
                        keys_to_clear = [
                            'df', 'target_data', 'data_processed', 'data_source', 'data_metadata',
                            'latest_data_date_str', 'all_results', 'current_unified_filter_config',
                            'mappings_initialized_after_processing', 'unified_filter_initialized',
                            'validation_results', 'performance_metrics', 'confirm_delete_ready'
                        ]
                        for key in keys_to_clear:
                            if key in st.session_state:
                                del st.session_state[key]
                        st.rerun()
                    else:
                        st.error(f"❌ 削除失敗: {result}")
                else:
                    st.session_state['confirm_delete_ready'] = True
                    st.warning("⚠️ もう一度クリックで完全削除")

        # ファイルサイズ情報
        file_sizes = get_file_sizes()
        if any(size != "未保存" for size in file_sizes.values()):
            st.markdown("---")
            st.markdown("**📁 ファイルサイズ:**")
            for name, size in file_sizes.items():
                if size != "未保存":
                    st.caption(f"• {name}: {size}")

    # バックアップ管理（既存コードベース + 強化）
    with st.sidebar.expander("🗂️ バックアップ管理", expanded=False):
        backup_info = get_backup_info()
        if backup_info:
            st.write("📋 **利用可能なバックアップ:**")
            for backup in backup_info:
                col1_bk, col2_bk = st.columns([3, 1])
                with col1_bk:
                    st.write(f"📄 {backup['timestamp']}")
                    st.caption(f"サイズ: {backup['size']}")
                    # 経過日数表示（新規追加）
                    if backup.get('age_days', 0) == 0:
                        st.caption("📅 今日作成")
                    else:
                        st.caption(f"📅 {backup['age_days']}日前")
                with col2_bk:
                    if st.button("復元", key=f"restore_{backup['filename']}_sidebar_enhanced_v2", use_container_width=True):
                        success, message = restore_from_backup(backup['filename'])
                        if success:
                            st.success(message)
                            st.info("🔄 ページを再読み込みして復元データを確認してください")
                            st.rerun()
                        else:
                            st.error(message)
        else:
            st.info("バックアップファイルはありません")
            st.caption("データを保存すると自動的にバックアップが作成されます")
        
        # 手動バックアップ作成（新規追加）
        st.markdown("---")
        if st.button("📦 手動バックアップ作成", key="create_manual_backup_sidebar_v2", use_container_width=True):
            if st.session_state.get('data_processed', False):
                from data_persistence import create_backup
                if create_backup(force_create=True):
                    st.success("✅ バックアップ作成完了")
                    st.rerun()
                else:
                    st.error("❌ バックアップ作成失敗")
            else:
                st.warning("バックアップするデータがありません")

    # 簡易データアップロード（既存機能を強化）
    with st.sidebar.expander("📤 簡易データアップロード", expanded=False):
        st.write("**簡易的なファイル読み込み**")
        st.caption("詳細な処理は「データ入力」タブを使用")
        uploaded_file_sidebar = st.file_uploader(
            "ファイルを選択", type=SUPPORTED_FILE_TYPES, key="sidebar_file_upload_widget_enhanced_v2",
            help="Excel/CSVファイルをアップロード"
        )
        if uploaded_file_sidebar is not None:
            col_simple1, col_simple2 = st.columns(2)
            
            with col_simple1:
                replace_mode = st.radio(
                    "読み込み方式",
                    ["新規", "追加"],
                    key="simple_upload_mode_sidebar_v2",
                    help="新規: 既存データ置換、追加: 既存データに追加"
                )
            
            with col_simple2:
                if st.button("⚡ 実行", key="quick_process_sidebar_enhanced_v2", use_container_width=True):
                    try:
                        if uploaded_file_sidebar.name.endswith('.csv'):
                            df_uploaded = pd.read_csv(uploaded_file_sidebar, encoding='utf-8')
                        else:
                            df_uploaded = pd.read_excel(uploaded_file_sidebar)

                        if '日付' in df_uploaded.columns:
                            df_uploaded['日付'] = pd.to_datetime(df_uploaded['日付'], errors='coerce').dt.normalize()
                            df_uploaded.dropna(subset=['日付'], inplace=True)

                        if replace_mode == "新規" or not st.session_state.get('data_processed', False):
                            st.session_state['df'] = df_uploaded
                            st.session_state['data_source'] = 'sidebar_upload'
                        else:
                            current_df = st.session_state.get('df')
                            combined_df = pd.concat([current_df, df_uploaded], ignore_index=True)
                            combined_df.drop_duplicates(inplace=True)
                            st.session_state['df'] = combined_df
                            st.session_state['data_source'] = 'incremental_add'

                        st.session_state['data_processed'] = True
                        st.session_state['target_data'] = None
                        
                        if '日付' in st.session_state['df'].columns and not st.session_state['df']['日付'].empty:
                            latest_date = st.session_state['df']['日付'].max()
                            st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                        else:
                            st.session_state.latest_data_date_str = "日付不明"
                        
                        initialize_all_mappings(st.session_state.df, None)
                        initialize_unified_filters(st.session_state.df)
                        st.session_state.mappings_initialized_after_processing = True
                        
                        st.success(f"✅ {replace_mode}読み込み完了!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 読み込みエラー: {e}")

def create_sidebar_target_file_status():
    """目標値ファイル状況をサイドバーに表示するヘルパー関数"""
    if st.session_state.get('target_data') is not None:
        st.sidebar.markdown("---") # 他セクションとの区切り
        st.sidebar.subheader("🎯 目標値ファイル状況")
        st.sidebar.success("✅ 目標値ファイル読み込み済み")
        extracted_targets = st.session_state.get('extracted_targets')
        if extracted_targets:
            if extracted_targets.get('target_days') or extracted_targets.get('target_admissions'):
                st.sidebar.markdown("###### <span style='color:green;'>目標値ファイルから取得:</span>", unsafe_allow_html=True)
                if extracted_targets.get('target_days'):
                    st.sidebar.write(f"- 延べ在院日数目標: {extracted_targets['target_days']:,.0f}人日")
                if extracted_targets.get('target_admissions'):
                    st.sidebar.write(f"- 新入院患者数目標: {extracted_targets['target_admissions']:,.0f}人")
                if extracted_targets.get('used_pattern'):
                    st.sidebar.caption(f"検索条件: {extracted_targets['used_pattern']}")
            else:
                st.sidebar.warning("⚠️ 目標値を抽出できませんでした")
        if st.sidebar.checkbox("🔍 目標値ファイル内容確認", key="sidebar_show_target_details_app_v2"): # キー変更
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
                            for result_item in results:
                                st.sidebar.write(f"  - {result_item['column']}: {result_item['matches']}件")
                        else:
                            st.sidebar.write(f"「{keyword}」: 該当なし")

# --- メインのサイドバー作成関数 ---
# app.py の create_sidebar() 関数内の設定値初期化部分を修正

def create_sidebar():
    """サイドバーの設定UI（レスポンシブ対応版）"""
    
    # モバイル用のサイドバーヘッダー
    if RESPONSIVE_FEATURES_AVAILABLE:
        # モバイルでのサイドバー制御
        sidebar_container = st.sidebar.container()
        with sidebar_container:
            # モバイル用クローズボタン
            st.sidebar.markdown("""
            <style>
            /* デスクトップではクローズボタンを非表示 */
            @media (min-width: 769px) {
                .mobile-sidebar-header { display: none !important; }
            }
            
            /* モバイルでのサイドバーヘッダースタイル */
            @media (max-width: 768px) {
                .mobile-sidebar-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 0.5rem 1rem;
                    background: #f8f9fa;
                    margin: -1rem -1rem 1rem -1rem;
                    border-bottom: 1px solid #dee2e6;
                }
                
                .mobile-close-btn {
                    background: transparent;
                    border: none;
                    font-size: 1.5rem;
                    cursor: pointer;
                    padding: 0.25rem;
                    color: #666;
                }
                
                /* サイドバー全体のモバイルスタイル */
                section[data-testid="stSidebar"] > div {
                    padding-top: 0 !important;
                }
                
                /* サイドバー内の要素の間隔調整 */
                .sidebar .element-container {
                    margin-bottom: 0.75rem !important;
                }
            }
            </style>
            
            <div class="mobile-sidebar-header">
                <h3 style="margin: 0; font-size: 1.2rem;">設定メニュー</h3>
                <button class="mobile-close-btn" onclick="closeSidebar()">✕</button>
            </div>
            
            <script>
            function closeSidebar() {
                const sidebar = document.querySelector('[data-testid="stSidebar"]');
                if (sidebar) {
                    sidebar.setAttribute('aria-expanded', 'false');
                    // Streamlitのサイドバー状態を更新
                    sidebar.style.transform = 'translateX(-100%)';
                }
            }
            </script>
            """, unsafe_allow_html=True)

    # 1. 分析フィルター (データロード後に表示)
    st.sidebar.header("🔍 分析フィルター")
    
    # モバイル用の折りたたみ可能なフィルター
    if RESPONSIVE_FEATURES_AVAILABLE:
        filter_expander = st.sidebar.expander("フィルター設定", expanded=False)
        with filter_expander:
            if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
                df_for_filter_init = st.session_state.get('df')
                if not df_for_filter_init.empty:
                    initialize_unified_filters(df_for_filter_init)
                    filter_config = create_unified_filter_sidebar(df_for_filter_init)
                    if filter_config:
                        st.session_state['current_unified_filter_config'] = filter_config
                else:
                    st.warning("分析フィルターを表示するためのデータが空です。")
            else:
                st.info("データを読み込むと、ここに分析フィルターが表示されます。")
    else:
        # デスクトップ版（既存のコード）
        if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
            df_for_filter_init = st.session_state.get('df')
            if not df_for_filter_init.empty:
                initialize_unified_filters(df_for_filter_init)
                filter_config = create_unified_filter_sidebar(df_for_filter_init)
                if filter_config:
                    st.session_state['current_unified_filter_config'] = filter_config
            else:
                st.sidebar.warning("分析フィルターを表示するためのデータが空です。")
        else:
            st.sidebar.info("「データ入力」タブでデータを読み込むと、ここに分析フィルターが表示されます。")
    
    st.sidebar.markdown("---")

    # 2. グローバル設定（レスポンシブ対応）
    st.sidebar.header("⚙️ グローバル設定")
    
    # モバイルでは設定を折りたたみ可能に
    if RESPONSIVE_FEATURES_AVAILABLE:
        # 基本病院設定
        with st.sidebar.expander("🏥 基本病院設定", expanded=False):
            # モバイル用のコンパクトなレイアウト
            col1, col2 = st.sidebar.columns(2)
            
            with col1:
                total_beds = st.number_input(
                    "総病床数", 
                    min_value=HOSPITAL_SETTINGS['min_beds'], 
                    max_value=HOSPITAL_SETTINGS['max_beds'],
                    value=get_safe_value('total_beds', DEFAULT_TOTAL_BEDS), 
                    step=1, 
                    help="病院の総病床数",
                    key="sidebar_total_beds_global_responsive"
                )
            
            with col2:
                avg_length_of_stay = st.number_input(
                    "平均在院日数", 
                    min_value=HOSPITAL_SETTINGS['min_avg_stay'], 
                    max_value=HOSPITAL_SETTINGS['max_avg_stay'],
                    value=get_safe_value('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY, float), 
                    step=0.1, 
                    help="目標とする平均在院日数",
                    key="sidebar_avg_length_of_stay_global_responsive"
                )
            
            # スライダーは全幅で表示
            current_occupancy_percent = st.session_state.get('bed_occupancy_rate_percent', int(DEFAULT_OCCUPANCY_RATE * 100))
            bed_occupancy_rate = st.slider(
                "目標病床稼働率 (%)", 
                min_value=int(HOSPITAL_SETTINGS['min_occupancy_rate'] * 100),
                max_value=int(HOSPITAL_SETTINGS['max_occupancy_rate'] * 100),
                value=current_occupancy_percent, 
                step=1, 
                help="目標とする病床稼働率",
                key="sidebar_bed_occupancy_rate_slider_global_responsive"
            ) / 100
            
            avg_admission_fee = st.number_input(
                "平均入院料（円/日）", 
                min_value=1000, 
                max_value=100000,
                value=get_safe_value('avg_admission_fee', DEFAULT_ADMISSION_FEE), 
                step=1000, 
                help="1日あたりの平均入院料",
                key="sidebar_avg_admission_fee_global_responsive"
            )
            
            # 値の更新
            st.session_state.total_beds = total_beds
            st.session_state.bed_occupancy_rate = bed_occupancy_rate
            st.session_state.bed_occupancy_rate_percent = int(bed_occupancy_rate * 100)
            st.session_state.avg_length_of_stay = avg_length_of_stay
            st.session_state.avg_admission_fee = avg_admission_fee
        
        # KPI目標値設定
        with st.sidebar.expander("🎯 KPI目標値設定", expanded=False):
            monthly_target_patient_days = st.number_input(
                "月間延べ在院日数目標", 
                min_value=100, 
                max_value=50000,
                value=get_safe_value('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS), 
                step=100, 
                help="月間の延べ在院日数目標（人日）",
                key="sidebar_monthly_target_pd_global_responsive"
            )
            
            monthly_target_admissions = st.number_input(
                "月間新入院患者数目標", 
                min_value=10, 
                max_value=5000,
                value=get_safe_value('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS), 
                step=10, 
                help="月間の新入院患者数目標（人）",
                key="sidebar_monthly_target_adm_global_responsive"
            )
            
            st.session_state.monthly_target_patient_days = monthly_target_patient_days
            st.session_state.monthly_target_admissions = monthly_target_admissions
    else:
        # デスクトップ版（既存のコードをそのまま使用）
        with st.sidebar.expander("🏥 基本病院設定", expanded=False):
            def get_safe_value(key, default, value_type=int):
                value = st.session_state.get(key, default)
                if isinstance(value, list): 
                    value = value[0] if value else default
                elif not isinstance(value, (int, float)): 
                    value = default
                return value_type(value)
    
            total_beds = st.number_input(
                "総病床数", 
                min_value=HOSPITAL_SETTINGS['min_beds'], 
                max_value=HOSPITAL_SETTINGS['max_beds'],
                value=get_safe_value('total_beds', DEFAULT_TOTAL_BEDS), 
                step=1, 
                help="病院の総病床数",
                key="sidebar_total_beds_global_v4"
            )
            st.session_state.total_beds = total_beds
            
            current_occupancy_percent = st.session_state.get('bed_occupancy_rate_percent', int(DEFAULT_OCCUPANCY_RATE * 100))
            bed_occupancy_rate = st.slider(
                "目標病床稼働率 (%)", 
                min_value=int(HOSPITAL_SETTINGS['min_occupancy_rate'] * 100),
                max_value=int(HOSPITAL_SETTINGS['max_occupancy_rate'] * 100),
                value=current_occupancy_percent, 
                step=1, 
                help="目標とする病床稼働率",
                key="sidebar_bed_occupancy_rate_slider_global_v4"
            ) / 100
            st.session_state.bed_occupancy_rate = bed_occupancy_rate
            st.session_state.bed_occupancy_rate_percent = int(bed_occupancy_rate * 100)
            
            avg_length_of_stay = st.number_input(
                "平均在院日数目標", 
                min_value=HOSPITAL_SETTINGS['min_avg_stay'], 
                max_value=HOSPITAL_SETTINGS['max_avg_stay'],
                value=get_safe_value('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY, float), 
                step=0.1, 
                help="目標とする平均在院日数",
                key="sidebar_avg_length_of_stay_global_v4"
            )
            st.session_state.avg_length_of_stay = avg_length_of_stay
            
            avg_admission_fee = st.number_input(
                "平均入院料（円/日）", 
                min_value=1000, 
                max_value=100000,
                value=get_safe_value('avg_admission_fee', DEFAULT_ADMISSION_FEE), 
                step=1000, 
                help="1日あたりの平均入院料",
                key="sidebar_avg_admission_fee_global_v4"
            )
            st.session_state.avg_admission_fee = avg_admission_fee
    
        with st.sidebar.expander("🎯 KPI目標値設定", expanded=False):
            monthly_target_patient_days = st.number_input(
                "月間延べ在院日数目標（人日）", 
                min_value=100, 
                max_value=50000,
                value=get_safe_value('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS), 
                step=100, 
                help="月間の延べ在院日数目標",
                key="sidebar_monthly_target_pd_global_v4"
            )
            st.session_state.monthly_target_patient_days = monthly_target_patient_days
            
            monthly_target_admissions = st.number_input(
                "月間新入院患者数目標（人）", 
                min_value=10, 
                max_value=5000,
                value=get_safe_value('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS), 
                step=10, 
                help="月間の新入院患者数目標",
                key="sidebar_monthly_target_adm_global_v4"
            )
            st.session_state.monthly_target_admissions = monthly_target_admissions

    if st.sidebar.button("💾 設定を保存", key="save_all_settings_responsive", use_container_width=True):
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
            st.sidebar.success("✅ 設定保存完了!")
        else:
            st.sidebar.error("❌ 設定保存失敗")
    
    st.sidebar.markdown("---")

    # 3. データ設定（既存の関数を呼び出し）
    create_sidebar_data_settings()
    st.sidebar.markdown("---")

    # 4. 目標値ファイル状況（既存関数を呼び出し）
    create_sidebar_target_file_status()

    # モバイル用の最下部パディング（スクロール時の余白確保）
    if RESPONSIVE_FEATURES_AVAILABLE:
        st.sidebar.markdown("""
        <style>
        @media (max-width: 768px) {
            /* サイドバー最下部にパディング追加 */
            section[data-testid="stSidebar"] > div {
                padding-bottom: 100px !important;
            }
        }
        </style>
        """, unsafe_allow_html=True)

    return True

def get_safe_value(key, default, value_type=int):
    value = st.session_state.get(key, default)
    if isinstance(value, list): 
        value = value[0] if value else default
    elif not isinstance(value, (int, float)): 
        value = default
    return value_type(value)

def create_management_dashboard_tab():
    """主要指標タブ - レスポンシブ対応版"""
    
    # レスポンシブ対応のスタイル注入
    st.markdown("""
    <style>
    /* 主要指標タブ専用のレスポンシブスタイル */
    @media (max-width: 768px) {
        /* ヘッダーのサイズ調整 */
        h2 {
            font-size: 1.3rem !important;
            margin-bottom: 1rem !important;
        }
        
        /* デバッグチェックボックスをモバイル用に調整 */
        .debug-container {
            position: fixed;
            top: 10px;
            right: 10px;
            z-index: 100;
            background: rgba(255, 255, 255, 0.9);
            padding: 0.5rem;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        /* メトリクスカードのモバイル最適化 */
        [data-testid="metric-container"] {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 0.75rem !important;
            margin-bottom: 0.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        /* メトリクスのラベルと値のサイズ調整 */
        [data-testid="metric-container"] label {
            font-size: 0.85rem !important;
        }
        
        [data-testid="metric-container"] [data-testid="metric-value"] {
            font-size: 1.2rem !important;
        }
        
        /* カラムを縦並びに */
        .responsive-metrics {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }
        
        /* タップ可能領域の拡大 */
        .stButton > button {
            min-height: 44px !important;
            width: 100% !important;
        }
    }
    
    /* タブレット対応 */
    @media (min-width: 768px) and (max-width: 1024px) {
        /* 2カラムレイアウト */
        .responsive-metrics {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
        }
    }
    
    /* 共通のアニメーション */
    [data-testid="metric-container"] {
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    
    [data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # モバイル検出用JavaScript
    st.markdown("""
    <script>
    // デバイスタイプの検出と保存
    function detectDevice() {
        const width = window.innerWidth;
        let deviceType = 'desktop';
        
        if (width < 768) {
            deviceType = 'mobile';
        } else if (width < 1024) {
            deviceType = 'tablet';
        }
        
        document.body.setAttribute('data-device', deviceType);
        return deviceType;
    }
    
    // 初期化とリサイズ時の更新
    detectDevice();
    window.addEventListener('resize', detectDevice);
    
    // タッチデバイス検出
    if ('ontouchstart' in window) {
        document.body.classList.add('touch-device');
    }
    </script>
    """, unsafe_allow_html=True)
    
    # ヘッダー（モバイルでは短縮版も検討）
    st.header("📊 主要指標")
    
    # データチェック
    if not st.session_state.get('data_processed', False) or st.session_state.get('df') is None:
        # モバイルフレンドリーな警告メッセージ
        st.warning("📱 データを読み込み後に利用可能になります。")
        
        # モバイルでの簡単なデータ読み込みボタン
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("📥 データ読込", key="mobile_load_data_dashboard", use_container_width=True):
                st.switch_page("pages/data_input.py")  # データ入力タブへ
        return
    
    # データ取得と期間設定
    df_original = st.session_state.get('df')
    start_date_ts, end_date_ts, period_description = get_analysis_period()
    
    if start_date_ts is None or end_date_ts is None:
        st.error("📅 分析期間が設定されていません。")
        # モバイル用の簡易期間設定
        with st.expander("🔧 期間を設定", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                quick_start = st.date_input("開始日", key="quick_start_dashboard")
            with col2:
                quick_end = st.date_input("終了日", key="quick_end_dashboard")
            
            # プリセットボタン（モバイル最適化）
            st.write("**クイック選択:**")
            preset_cols = st.columns(4)
            presets = [
                ("7日", 7),
                ("30日", 30),
                ("90日", 90),
                ("1年", 365)
            ]
            for col, (label, days) in zip(preset_cols, presets):
                with col:
                    if st.button(label, key=f"preset_{days}_dashboard", use_container_width=True):
                        # 期間設定ロジック
                        pass
        return
    
    # フィルター適用
    df_for_dashboard = filter_data_by_analysis_period(df_original)
    
    if df_for_dashboard.empty:
        st.warning("📊 選択されたフィルター条件に合致するデータがありません。")
        st.info("💡 フィルター条件を調整してください。")
        return
    
    # 設定値取得
    total_beds = st.session_state.get('total_beds', 500)
    target_occupancy_rate_percent = st.session_state.get('bed_occupancy_rate', 0.85) * 100
    
    # ===========================================
    # デバッグモード切り替え（レスポンシブ対応）
    # ===========================================
    # モバイルでは固定位置、デスクトップでは右上配置
    st.markdown('<div class="debug-container-wrapper">', unsafe_allow_html=True)
    
    # デスクトップレイアウト
    col_main, col_debug = st.columns([4, 1])
    
    with col_debug:
        # モバイルでは小さく表示
        debug_mode = st.checkbox(
            "🐛", # モバイルではアイコンのみ
            value=False, 
            key="dashboard_debug_mode",
            help="詳細な処理情報を表示"
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # ===========================================
    # KPIカード表示（レスポンシブ対応）
    # ===========================================
    if display_kpi_cards_only:
        # レスポンシブコンテナ
        st.markdown('<div class="kpi-cards-responsive-container">', unsafe_allow_html=True)
        
        display_kpi_cards_only(
            df_for_dashboard, start_date_ts, end_date_ts, 
            total_beds, target_occupancy_rate_percent,
            show_debug=debug_mode
        )
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # モバイル用のスワイプヒント
        st.markdown("""
        <div class="swipe-hint" style="display: none;">
            <style>
            @media (max-width: 768px) {
                .swipe-hint {
                    display: block !important;
                    text-align: center;
                    color: #666;
                    font-size: 0.85rem;
                    margin: 1rem 0;
                    padding: 0.5rem;
                    background: #f0f0f0;
                    border-radius: 20px;
                }
            }
            </style>
            ← 左右にスワイプで詳細を確認 →
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error("❌ KPIカード表示機能が利用できません。")
    
    # ===========================================
    # 分析条件表示（レスポンシブ対応）
    # ===========================================
    if not debug_mode:
        st.markdown("---")
        
        # レスポンシブメトリクスコンテナ
        st.markdown('<div class="responsive-metrics">', unsafe_allow_html=True)
        
        # デスクトップでは3カラム、モバイルでは縦並び
        metrics_container = st.container()
        with metrics_container:
            # CSSグリッドで自動調整
            col_period, col_records, col_target = st.columns(3)
            
            with col_period:
                date_range_days = (end_date_ts - start_date_ts).days + 1
                
                # モバイル対応の短縮表示
                period_label = "📊 分析期間"
                period_value = f"{date_range_days}日間"
                
                # 日付範囲の表示（モバイルでは改行）
                if date_range_days > 365:
                    period_delta = f"{start_date_ts.strftime('%Y/%m/%d')}～"
                else:
                    period_delta = f"{start_date_ts.strftime('%m/%d')}～{end_date_ts.strftime('%m/%d')}"
                
                st.metric(
                    period_label,
                    period_value,
                    period_delta
                )
            
            with col_records:
                record_count = len(df_for_dashboard)
                
                # 大きな数値の短縮表示（モバイル対応）
                if record_count >= 10000:
                    display_count = f"{record_count/1000:.1f}K"
                else:
                    display_count = f"{record_count:,}"
                
                st.metric(
                    "📋 レコード数",
                    f"{display_count}件",
                    f"フィルター適用済" if record_count < len(df_original) else None
                )
            
            with col_target:
                target_data = st.session_state.get('target_data')
                if target_data is not None and not target_data.empty:
                    target_records = len(target_data)
                    st.metric(
                        "🎯 目標値",
                        "設定済",
                        f"{target_records}行"
                    )
                else:
                    st.metric(
                        "🎯 目標値",
                        "未設定",
                        "設定推奨"
                    )
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # モバイル用の操作ヒント
        st.markdown("""
        <div class="mobile-hint" style="display: none;">
            <style>
            @media (max-width: 768px) {
                .mobile-hint {
                    display: block !important;
                    text-align: center;
                    font-size: 0.8rem;
                    color: #666;
                    margin-top: 0.5rem;
                }
            }
            </style>
            💡 期間変更は左上メニュー → 分析フィルター
        </div>
        """, unsafe_allow_html=True)
        
        # デスクトップ用のキャプション
        st.markdown("""
        <div class="desktop-caption">
            <style>
            @media (min-width: 769px) {
                .mobile-hint { display: none !important; }
            }
            @media (max-width: 768px) {
                .desktop-caption { display: none !important; }
            }
            </style>
            <p style="font-size: 0.85rem; color: #666; margin-top: 0.5rem;">
            ※ 期間変更はサイドバーの「分析フィルター」で行えます
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    # パフォーマンス最適化：モバイルでの遅延読み込み
    st.markdown("""
    <script>
    // モバイルでの遅延読み込み実装
    if (window.innerWidth < 768) {
        // 重いコンポーネントの遅延読み込み
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    // 要素が見えたら読み込み
                    entry.target.classList.add('loaded');
                }
            });
        });
        
        // 監視対象の設定
        document.querySelectorAll('[data-testid="stPlotlyChart"]').forEach(el => {
            observer.observe(el);
        });
    }
    </script>
    """, unsafe_allow_html=True)

def main():
    # セッション状態の初期化
    if 'app_initialized' not in st.session_state:
        st.session_state.app_initialized = True
        # レスポンシブ対応のための追加初期化
        st.session_state.device_type = 'desktop'
        st.session_state.is_mobile = False
    if 'data_processed' not in st.session_state: 
        st.session_state['data_processed'] = False
    if 'df' not in st.session_state: 
        st.session_state['df'] = None
    if 'forecast_model_results' not in st.session_state: 
        st.session_state.forecast_model_results = {}
    if 'mappings_initialized_after_processing' not in st.session_state: 
        st.session_state.mappings_initialized_after_processing = False

    # 設定値の初期化（config.pyから）
    if 'global_settings_initialized' not in st.session_state:
        st.session_state.total_beds = DEFAULT_TOTAL_BEDS
        st.session_state.bed_occupancy_rate = DEFAULT_OCCUPANCY_RATE
        st.session_state.bed_occupancy_rate_percent = int(DEFAULT_OCCUPANCY_RATE * 100)
        st.session_state.avg_length_of_stay = DEFAULT_AVG_LENGTH_OF_STAY
        st.session_state.avg_admission_fee = DEFAULT_ADMISSION_FEE
        st.session_state.monthly_target_patient_days = DEFAULT_TARGET_PATIENT_DAYS
        st.session_state.monthly_target_admissions = DEFAULT_TARGET_ADMISSIONS
        st.session_state.global_settings_initialized = True

    # レスポンシブデザイン機能のインポートと初期化
    RESPONSIVE_FEATURES_AVAILABLE = False
    try:
        from responsive_style import inject_responsive_css, get_mobile_navigation_html
        from mobile_utils import (
            create_responsive_columns,
            create_mobile_friendly_dataframe,
            create_mobile_sidebar_toggle,
            optimize_chart_for_mobile,
            get_device_info
        )
        RESPONSIVE_FEATURES_AVAILABLE = True
    except ImportError as e:
        print(f"レスポンシブ機能のインポートエラー: {e}")
        # フォールバック関数の定義
        def inject_responsive_css(): pass
        def create_mobile_sidebar_toggle(): pass

    # 自動読み込み実行（シンプル版）
    try:
        auto_loaded = auto_load_data()
        if auto_loaded and st.session_state.get('df') is not None:
            st.success("✅ 保存されたデータを自動読み込みしました")
            
            # target_dataの初期化
            if 'target_data' not in st.session_state: 
                st.session_state.target_data = None
                
            # マッピングとフィルターの初期化
            initialize_all_mappings(st.session_state.df, st.session_state.target_data)
            if st.session_state.df is not None and not st.session_state.df.empty:
                initialize_unified_filters(st.session_state.df)
            st.session_state.mappings_initialized_after_processing = True
            
    except Exception as e:
        st.error(f"自動読み込み中にエラーが発生しました: {str(e)}")

    # グローバルCSSとレスポンシブCSSの注入
    inject_global_css(FONT_SCALE)
    if RESPONSIVE_FEATURES_AVAILABLE:
        inject_responsive_css()
        create_mobile_sidebar_toggle()

    # デバイス検出スクリプトの注入
    st.markdown("""
    <script>
    // デバイスタイプの検出
    function detectDevice() {
        const width = window.innerWidth;
        let deviceType = 'desktop';
        
        if (width < 768) {
            deviceType = 'mobile';
            document.body.classList.add('is-mobile');
        } else if (width < 1024) {
            deviceType = 'tablet';
            document.body.classList.add('is-tablet');
        } else {
            document.body.classList.add('is-desktop');
        }
        
        // Streamlitの要素にもクラスを追加
        const stApp = document.querySelector('.stApp');
        if (stApp) {
            stApp.setAttribute('data-device', deviceType);
        }
        
        return deviceType;
    }
    
    // 初期化とリサイズ時の更新
    detectDevice();
    window.addEventListener('resize', () => {
        // 既存のクラスを削除
        document.body.classList.remove('is-mobile', 'is-tablet', 'is-desktop');
        detectDevice();
    });
    
    // タッチデバイス検出
    if ('ontouchstart' in window || navigator.maxTouchPoints > 0) {
        document.body.classList.add('touch-device');
    }
    </script>
    """, unsafe_allow_html=True)

    # メインヘッダー（レスポンシブ対応）
    st.markdown(f"""
    <style>
    @media (max-width: 768px) {{
        .main-header {{
            font-size: 1.5rem !important;
            padding: 1rem 0 !important;
            text-align: center;
        }}
    }}
    </style>
    <h1 class="main-header">{APP_ICON} {APP_TITLE}</h1>
    """, unsafe_allow_html=True)
    
    # サイドバー作成
    create_sidebar()

    # タブの作成と処理（レスポンシブ対応）
    # デスクトップ用のフルタイトル
    desktop_tab_titles = ["📊 主要指標", "🏥 診療科別パフォーマンス", "🏨 病棟別パフォーマンス", 
                          "🗓️ 平均在院日数分析", "📅 曜日別入退院分析", "🔍 個別分析"]
    
    # モバイル用の短縮タイトル
    mobile_tab_titles = ["📊 KPI", "🏥 診療科", "🏨 病棟", 
                         "🗓️ 在院日数", "📅 曜日別", "🔍 個別"]
    
    # 条件に応じてタブを追加
    if FORECAST_AVAILABLE:
        desktop_tab_titles.append("🔮 予測分析")
        mobile_tab_titles.append("🔮 予測")
    
    desktop_tab_titles.extend(["📤 データ出力", "📥 データ入力"])
    mobile_tab_titles.extend(["📤 出力", "📥 入力"])
    
    # デフォルトはデスクトップタイトルを使用
    tab_titles = desktop_tab_titles
    
    # タブのレスポンシブスタイル
    st.markdown("""
    <style>
    /* タブのレスポンシブ対応 */
    @media (max-width: 768px) {
        /* タブコンテナの横スクロール対応 */
        [data-testid="stTabs"] {
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch;
            scroll-snap-type: x mandatory;
        }
        
        [data-testid="stTabs"] > div:first-child {
            display: flex !important;
            flex-wrap: nowrap !important;
            gap: 0.25rem;
        }
        
        /* タブボタンのスタイル調整 */
        [data-testid="stTabs"] button {
            flex-shrink: 0;
            white-space: nowrap;
            padding: 0.5rem 0.75rem !important;
            font-size: 0.85rem !important;
            min-width: fit-content !important;
            scroll-snap-align: start;
        }
        
        /* アクティブタブの視認性向上 */
        [data-testid="stTabs"] button[aria-selected="true"] {
            background-color: #007bff !important;
            color: white !important;
            font-weight: bold;
            box-shadow: 0 2px 4px rgba(0, 123, 255, 0.3);
        }
        
        /* スクロールヒント */
        [data-testid="stTabs"]::after {
            content: '→';
            position: absolute;
            right: 0;
            top: 50%;
            transform: translateY(-50%);
            background: linear-gradient(to right, transparent, rgba(255,255,255,0.9));
            padding: 0 10px;
            pointer-events: none;
            font-size: 1.2rem;
            color: #666;
        }
    }
    
    /* タブレット対応 */
    @media (min-width: 768px) and (max-width: 1024px) {
        [data-testid="stTabs"] button {
            padding: 0.75rem 1rem !important;
            font-size: 0.9rem !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # タブの作成
    tabs = st.tabs(tab_titles)
    
    # モバイル用のJavaScriptでタブ名を動的に変更
    st.markdown(f"""
    <script>
    // モバイルでタブ名を短縮
    function updateTabNames() {{
        const width = window.innerWidth;
        if (width < 768) {{
            const tabs = document.querySelectorAll('[data-testid="stTabs"] button');
            const mobileNames = {mobile_tab_titles};
            tabs.forEach((tab, index) => {{
                if (mobileNames[index]) {{
                    // アイコンと短縮名を組み合わせる
                    const icon = mobileNames[index].split(' ')[0];
                    const shortName = mobileNames[index].split(' ')[1] || '';
                    tab.innerHTML = `${{icon}} <span class="tab-text">${{shortName}}</span>`;
                }}
            }});
        }}
    }}
    
    // 初期化とリサイズ時の更新
    setTimeout(updateTabNames, 100); // DOMが完全に読み込まれるのを待つ
    window.addEventListener('resize', updateTabNames);
    </script>
    """, unsafe_allow_html=True)

    # データ入力タブ
    data_input_tab_index = tab_titles.index("📥 データ入力")
    with tabs[data_input_tab_index]:
        try:
            create_data_processing_tab()
            if st.session_state.get('data_processed') and st.session_state.get('df') is not None:
                 if not st.session_state.get('df').empty:
                    initialize_unified_filters(st.session_state.df)
        except Exception as e:
            st.error(f"データ入力タブでエラー: {str(e)}\n{traceback.format_exc()}")

    # データが読み込まれている場合の処理
    if st.session_state.get('data_processed', False) and st.session_state.get('df') is not None:
        df_original_main = st.session_state.get('df')
        common_config_main = st.session_state.get('common_config', {})
        df_filtered_unified = filter_data_by_analysis_period(df_original_main)
        current_filter_config = get_unified_filter_config()

        # 各タブの処理（レスポンシブ対応の追加）
        with tabs[tab_titles.index("📊 主要指標")]:
            try: 
                create_management_dashboard_tab()
            except Exception as e: 
                st.error(f"主要指標でエラー: {str(e)}\n{traceback.format_exc()}")

        # 診療科別パフォーマンス
        with tabs[tab_titles.index("🏥 診療科別パフォーマンス")]:
            try:
                if DEPT_PERFORMANCE_AVAILABLE:
                    # モバイル用の注意書き
                    if RESPONSIVE_FEATURES_AVAILABLE:
                        st.markdown("""
                        <div class="mobile-notice" style="display: none;">
                            <style>
                            @media (max-width: 768px) {
                                .mobile-notice {
                                    display: block !important;
                                    background: #e3f2fd;
                                    padding: 0.75rem;
                                    border-radius: 5px;
                                    margin-bottom: 1rem;
                                    font-size: 0.85rem;
                                }
                            }
                            </style>
                            📱 ヒント: 表は左右にスクロールできます
                        </div>
                        """, unsafe_allow_html=True)
                    create_department_performance_tab()
                else:
                    st.error("診療科別パフォーマンス機能が利用できません。")
            except Exception as e:
                st.error(f"診療科別パフォーマンスでエラー: {str(e)}\n{traceback.format_exc()}")

        # 病棟別パフォーマンス
        with tabs[tab_titles.index("🏨 病棟別パフォーマンス")]:
            try:
                if WARD_PERFORMANCE_AVAILABLE:
                    create_ward_performance_tab()
                else:
                    st.error("病棟別パフォーマンス機能が利用できません。")
            except Exception as e:
                st.error(f"病棟別パフォーマンスでエラー: {str(e)}\n{traceback.format_exc()}")

        # 平均在院日数分析
        with tabs[tab_titles.index("🗓️ 平均在院日数分析")]:
            try:
                if display_alos_analysis_tab:
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
                if create_individual_analysis_section:
                    create_individual_analysis_section(df_filtered_unified, current_filter_config)
                else: 
                    st.error("個別分析機能が利用できません。")
            except Exception as e: 
                st.error(f"個別分析でエラー: {str(e)}\n{traceback.format_exc()}")

        # 予測分析（オプション）
        if FORECAST_AVAILABLE:
            with tabs[tab_titles.index("🔮 予測分析")]:
                try:
                    deps_ok = check_forecast_dependencies()
                    if deps_ok:
                        original_df_for_forecast = st.session_state.get('df')
                        st.session_state['df'] = df_filtered_unified
                        display_forecast_analysis_tab()
                        st.session_state['df'] = original_df_for_forecast
                    else: 
                        st.info("予測分析には追加ライブラリが必要です。")
                except Exception as e: 
                    st.error(f"予測分析でエラー: {str(e)}\n{traceback.format_exc()}")

        # データ出力
        data_output_tab_index = tab_titles.index("📤 データ出力")
        with tabs[data_output_tab_index]:
            st.header("📤 データ出力")
            
            # サブタブもレスポンシブ対応
            st.markdown("""
            <style>
            @media (max-width: 768px) {
                /* サブタブの調整 */
                .stTabs [data-baseweb="tab-list"] {
                    gap: 0.5rem;
                }
                
                .stTabs [data-baseweb="tab"] {
                    padding: 0.5rem !important;
                    font-size: 0.9rem !important;
                }
            }
            </style>
            """, unsafe_allow_html=True)
            
            output_sub_tab1, output_sub_tab2 = st.tabs(["📋 データテーブル", "📄 PDF出力"])
            with output_sub_tab1:
                try: 
                    # モバイル対応のデータテーブル表示
                    if RESPONSIVE_FEATURES_AVAILABLE:
                        st.markdown("""
                        <div class="mobile-table-hint" style="display: none;">
                            <style>
                            @media (max-width: 768px) {
                                .mobile-table-hint {
                                    display: block !important;
                                    text-align: center;
                                    color: #666;
                                    font-size: 0.85rem;
                                    margin: 0.5rem 0;
                                    padding: 0.5rem;
                                    background: #f0f0f0;
                                    border-radius: 20px;
                                }
                            }
                            </style>
                            📱 左右にスワイプでテーブル全体を確認
                        </div>
                        """, unsafe_allow_html=True)
                    create_data_tables_tab()
                except Exception as e: 
                    st.error(f"データテーブル表示でエラー: {str(e)}\n{traceback.format_exc()}")
            with output_sub_tab2:
                try: 
                    pdf_output_tab.create_pdf_output_tab()
                except Exception as e: 
                    st.error(f"PDF出力機能でエラー: {str(e)}\n{traceback.format_exc()}")
    else:
        # データが読み込まれていない場合（レスポンシブ対応）
        non_input_tab_indices = [i for i, title in enumerate(tab_titles) if title != "📥 データ入力"]
        for i in non_input_tab_indices:
            with tabs[i]:
                st.info("📊 データを読み込み後に利用可能になります。")
                
                # 保存データの確認と読み込みボタン
                data_info = get_data_info()
                if data_info: 
                    st.info("💾 保存されたデータがあります。以下から読み込むことができます。")
                    
                    # レスポンシブなメトリクス表示
                    st.markdown("""
                    <style>
                    @media (max-width: 768px) {
                        /* モバイルでメトリクスを縦並びに */
                        .element-container:has([data-testid="metric-container"]) {
                            margin-bottom: 0.5rem;
                        }
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    # 保存データの簡易情報
                    if RESPONSIVE_FEATURES_AVAILABLE:
                        # モバイルでは縦並び、デスクトップでは横並び
                        metric_cols = st.columns([1, 1, 1])
                    else:
                        metric_cols = st.columns(3)
                    
                    with metric_cols[0]:
                        st.metric("データ件数", f"{data_info.get('data_rows', 0):,}件")
                    with metric_cols[1]:
                        if data_info.get('file_size_mb'):
                            st.metric("ファイルサイズ", f"{data_info['file_size_mb']} MB")
                    with metric_cols[2]:
                        if data_info.get('last_saved'):
                            try:
                                saved_date = datetime.datetime.fromisoformat(data_info['last_saved'].replace('Z', '+00:00'))
                                st.metric("最終保存", saved_date.strftime('%m/%d %H:%M'))
                            except:
                                st.metric("最終保存", "不明")
                    
                    # データ読み込みボタン（レスポンシブ対応）
                    button_cols = st.columns([1, 1])
                    with button_cols[0]:
                        if st.button("🚀 データを読み込む", key=f"quick_load_tab_{i}", use_container_width=True):
                            df_loaded, target_data_loaded, metadata_loaded = load_data_from_file()
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
                                if st.session_state.df is not None and not st.session_state.df.empty:
                                    initialize_unified_filters(st.session_state.df)
                                st.session_state.mappings_initialized_after_processing = True
                                
                                st.success("✅ データ読み込み完了!")
                                st.rerun()
                            else:
                                st.error("❌ データ読み込みに失敗しました")
                    
                    with button_cols[1]:
                        st.caption("または「データ入力」タブから新しいデータをアップロード")
                else: 
                    st.info("📋 「データ入力」タブから新しいデータをアップロードしてください。")

    # フッター（レスポンシブ対応）
    st.markdown("---")
    st.markdown(f"""
    <style>
    @media (max-width: 768px) {{
        .footer {{
            font-size: 0.7rem !important;
            padding: 0.5rem !important;
        }}
    }}
    </style>
    <div class="footer" style="text-align: center; color: #666666; font-size: 0.8rem;">
        {APP_ICON} {APP_TITLE} | {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()