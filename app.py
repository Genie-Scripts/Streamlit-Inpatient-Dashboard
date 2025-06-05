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
    display_kpi_cards_only = lambda df, start_date, end_date, total_beds_setting, target_occupancy_setting: st.error("経営ダッシュボードKPI表示機能は利用できません。")
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

inject_global_css(FONT_SCALE)


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
    """サイドバーの設定UI（設定値初期化強化版）"""

    # 1. 分析フィルター (データロード後に表示)
    st.sidebar.header("🔍 分析フィルター")
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

    # 2. グローバル設定（設定値初期化を強化）
    st.sidebar.header("⚙️ グローバル設定")
    
    # 設定値の初期化（config.pyからの読み込み強化）
    if 'settings_initialized' not in st.session_state:
        # config.pyからのデフォルト値で初期化
        st.session_state.total_beds = DEFAULT_TOTAL_BEDS
        st.session_state.bed_occupancy_rate = DEFAULT_OCCUPANCY_RATE
        st.session_state.bed_occupancy_rate_percent = int(DEFAULT_OCCUPANCY_RATE * 100)
        st.session_state.avg_length_of_stay = DEFAULT_AVG_LENGTH_OF_STAY
        st.session_state.avg_admission_fee = DEFAULT_ADMISSION_FEE
        st.session_state.monthly_target_patient_days = DEFAULT_TARGET_PATIENT_DAYS
        st.session_state.monthly_target_admissions = DEFAULT_TARGET_ADMISSIONS
        
        # 保存された設定があれば上書き
        saved_settings = load_settings_from_file()
        if saved_settings:
            for key, value in saved_settings.items():
                if key in st.session_state:  # 既存のキーのみ更新
                    st.session_state[key] = value
        
        st.session_state.settings_initialized = True
    
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

    if st.sidebar.button("💾 グローバル設定とKPI目標値を保存", key="save_all_global_settings_sidebar_v5", use_container_width=True):
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
    
    # 現在の設定値確認
    with st.sidebar.expander("📋 現在の設定値確認", expanded=False):
        st.markdown("**🏥 基本設定**")
        st.write(f"• 総病床数: {st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS)}床")
        st.write(f"• 目標病床稼働率: {st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE)*100:.1f}%")
        st.write(f"• 目標平均在院日数: {st.session_state.get('avg_length_of_stay', DEFAULT_AVG_LENGTH_OF_STAY):.1f}日")
        st.write(f"• 平均入院料: {st.session_state.get('avg_admission_fee', DEFAULT_ADMISSION_FEE):,}円/日")
        
        st.markdown("**🎯 KPI目標値**")
        st.write(f"• 月間延べ在院日数目標: {st.session_state.get('monthly_target_patient_days', DEFAULT_TARGET_PATIENT_DAYS):,}人日")
        st.write(f"• 月間新入院患者数目標: {st.session_state.get('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS):,}人")
        
        # 計算値も表示
        st.markdown("**📊 計算値**")
        target_daily_census = st.session_state.get('total_beds', DEFAULT_TOTAL_BEDS) * st.session_state.get('bed_occupancy_rate', DEFAULT_OCCUPANCY_RATE)
        target_daily_admissions = st.session_state.get('monthly_target_admissions', DEFAULT_TARGET_ADMISSIONS) / 30
        st.write(f"• 目標日平均在院患者数: {target_daily_census:.1f}人")
        st.write(f"• 目標日平均新入院患者数: {target_daily_admissions:.1f}人/日")
    
    st.sidebar.markdown("---")

    # 3. データ設定（既存のcreate_sidebar_data_settings関数を呼び出し）
    create_sidebar_data_settings()
    st.sidebar.markdown("---")

    # 4. 目標値ファイル状況（既存関数を呼び出し）
    create_sidebar_target_file_status()

    return True

def create_management_dashboard_tab():
    st.header("📊 主要指標")
    
    if not st.session_state.get('data_processed', False) or st.session_state.get('df') is None:
        st.warning("データを読み込み後に利用可能になります。")
        return
    
    df_original = st.session_state.get('df')
    start_date_ts, end_date_ts, period_description = get_analysis_period()
    
    if start_date_ts is None or end_date_ts is None:
        st.error("分析期間が設定されていません。サイドバーの「分析フィルター」で期間を設定してください。")
        return
    
    df_for_dashboard = filter_data_by_analysis_period(df_original)
    
    if df_for_dashboard.empty:
        st.warning("選択されたフィルター条件に合致するデータがありません。")
        return
    
    total_beds = st.session_state.get('total_beds', 500)
    target_occupancy_rate_percent = st.session_state.get('bed_occupancy_rate', 0.85) * 100
    
    # ===========================================
    # メインコンテンツ：KPIカードを最初に表示
    # ===========================================
    if display_kpi_cards_only:
        display_kpi_cards_only(df_for_dashboard, start_date_ts, end_date_ts, total_beds, target_occupancy_rate_percent)
    else:
        st.error("KPIカード表示機能が利用できません。dashboard_overview_tab.pyを確認してください。")
    
    # ===========================================
    # 分析条件の表示（簡潔に）
    # ===========================================
    st.markdown("---")
    
    # 分析期間の表示（シンプルに）
    col_period, col_records, col_target = st.columns(3)
    
    with col_period:
        date_range_days = (end_date_ts - start_date_ts).days + 1
        st.metric(
            "📊 分析期間", 
            f"{date_range_days}日間",
            f"{start_date_ts.strftime('%Y/%m/%d')} ～ {end_date_ts.strftime('%Y/%m/%d')}"
        )
    
    with col_records:
        record_count = len(df_for_dashboard)
        st.metric("📋 分析レコード数", f"{record_count:,}件")
    
    with col_target:
        target_data = st.session_state.get('target_data')
        if target_data is not None and not target_data.empty:
            target_records = len(target_data)
            st.metric("🎯 目標値データ", f"{target_records}行", "使用中")
        else:
            st.metric("🎯 目標値データ", "未設定", "")
    
    # ===========================================
    # 詳細情報（expanderで格納）
    # ===========================================
    with st.expander("🔧 詳細設定・デバッグ情報", expanded=False):
        st.caption("※ 期間変更はサイドバーの「分析フィルター」で行えます")
        
        # フィルター適用状況
        try:
            from unified_filters import get_unified_filter_summary
            filter_summary = get_unified_filter_summary()
            st.info(f"🔍 適用中フィルター: {filter_summary}")
        except ImportError:
            st.info("🔍 フィルター情報を取得できません")
        
        # 目標値データの詳細
        if target_data is not None and not target_data.empty:
            st.markdown("**🎯 目標値データの詳細:**")
            
            # extracted_targets の情報
            extracted_targets = st.session_state.get('extracted_targets')
            if extracted_targets:
                if extracted_targets.get('target_days') or extracted_targets.get('target_admissions'):
                    col_t1, col_t2 = st.columns(2)
                    with col_t1:
                        if extracted_targets.get('target_days'):
                            st.metric("延べ在院日数目標", f"{extracted_targets['target_days']:,.0f}人日")
                    with col_t2:
                        if extracted_targets.get('target_admissions'):
                            st.metric("新入院患者数目標", f"{extracted_targets['target_admissions']:,.0f}人")
                    
                    if extracted_targets.get('used_pattern'):
                        st.caption(f"検索条件: {extracted_targets['used_pattern']}")
            
            # 目標値ファイルの内容確認
            if st.checkbox("📋 目標値ファイル内容を確認", key="show_target_details_dashboard"):
                st.dataframe(target_data.head(10), use_container_width=True)
                st.caption(f"表示: 先頭10行 / 全{len(target_data)}行")
        else:
            st.info("🎯 目標値データが設定されていません。「データ入力」タブで目標値ファイルをアップロードできます。")
        
        # システム情報
        st.markdown("**⚙️ システム情報:**")
        col_sys1, col_sys2 = st.columns(2)
        with col_sys1:
            st.metric("総病床数設定", f"{total_beds}床")
        with col_sys2:
            st.metric("目標病床稼働率", f"{target_occupancy_rate_percent:.1f}%")


def main():
    # セッション状態の初期化
    if 'app_initialized' not in st.session_state:
        st.session_state.app_initialized = True
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

    # メインヘッダー
    st.markdown(f'<h1 class="main-header">{APP_ICON} {APP_TITLE}</h1>', unsafe_allow_html=True)
    
    # サイドバー作成
    create_sidebar()

    # タブの作成と処理
    tab_titles = ["📊 主要指標", "🗓️ 平均在院日数分析", "📅 曜日別入退院分析", "🔍 個別分析"]
    if FORECAST_AVAILABLE:
        tab_titles.append("🔮 予測分析")
    tab_titles.extend(["📤 データ出力", "📥 データ入力"])

    tabs = st.tabs(tab_titles)

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

        with tabs[tab_titles.index("📊 主要指標")]:
            try: 
                create_management_dashboard_tab()
            except Exception as e: 
                st.error(f"主要指標でエラー: {str(e)}\n{traceback.format_exc()}")

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

        with tabs[tab_titles.index("🔍 個別分析")]:
            try:
                if create_individual_analysis_section:
                    create_individual_analysis_section(df_filtered_unified, current_filter_config)
                else: 
                    st.error("個別分析機能が利用できません。")
            except Exception as e: 
                st.error(f"個別分析でエラー: {str(e)}\n{traceback.format_exc()}")

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

        data_output_tab_index = tab_titles.index("📤 データ出力")
        with tabs[data_output_tab_index]:
            st.header("📤 データ出力")
            output_sub_tab1, output_sub_tab2 = st.tabs(["📋 データテーブル", "📄 PDF出力"])
            with output_sub_tab1:
                try: 
                    create_data_tables_tab()
                except Exception as e: 
                    st.error(f"データテーブル表示でエラー: {str(e)}\n{traceback.format_exc()}")
            with output_sub_tab2:
                try: 
                    pdf_output_tab.create_pdf_output_tab()
                except Exception as e: 
                    st.error(f"PDF出力機能でエラー: {str(e)}\n{traceback.format_exc()}")
    else:
        # データが読み込まれていない場合
        non_input_tab_indices = [i for i, title in enumerate(tab_titles) if title != "📥 データ入力"]
        for i in non_input_tab_indices:
            with tabs[i]:
                st.info("📊 データを読み込み後に利用可能になります。")
                
                # 保存データの確認と読み込みボタン
                data_info = get_data_info()
                if data_info: 
                    st.info("💾 保存されたデータがあります。以下から読み込むことができます。")
                    
                    # 保存データの簡易情報
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("データ件数", f"{data_info.get('data_rows', 0):,}件")
                    with col2:
                        if data_info.get('file_size_mb'):
                            st.metric("ファイルサイズ", f"{data_info['file_size_mb']} MB")
                    with col3:
                        if data_info.get('last_saved'):
                            try:
                                saved_date = datetime.datetime.fromisoformat(data_info['last_saved'].replace('Z', '+00:00'))
                                st.metric("最終保存", saved_date.strftime('%m/%d %H:%M'))
                            except:
                                st.metric("最終保存", "不明")
                    
                    # データ読み込みボタン
                    col_load1, col_load2 = st.columns(2)
                    with col_load1:
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
                    
                    with col_load2:
                        st.caption("または「データ入力」タブから新しいデータをアップロード")
                else: 
                    st.info("📋 「データ入力」タブから新しいデータをアップロードしてください。")

    # フッター
    st.markdown("---")
    st.markdown(
        f'<div style="text-align: center; color: #666666; font-size: 0.8rem;">'
        f'{APP_ICON} {APP_TITLE} | {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        f'</div>',
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()