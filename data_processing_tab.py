# data_processing_tab.py - 永続化対応版

import streamlit as st
import pandas as pd
from datetime import datetime
import os

# 永続化機能のインポート
from persistent_data import (
    auto_load_persistent_data,
    save_persistent_data, 
    get_persistent_data_info,
    clear_persistent_data,
    restore_from_backup,
    export_data_info
)

# 既存機能のインポート
from integrated_preprocessing import integrated_preprocess_data
from loader import load_files

def create_data_processing_tab():
    """データ処理タブ（永続化対応版）"""
    
    st.header("📊 データ処理")
    
    # ===== アプリ起動時の自動データ読み込み =====
    if not st.session_state.get('auto_load_attempted', False):
        with st.spinner("保存されたデータを確認中..."):
            if auto_load_persistent_data():
                st.success("💾 前回のデータを自動読み込みしました！")
                st.balloons()
            st.session_state['auto_load_attempted'] = True
            st.rerun()
    
    # ===== データ状況の表示 =====
    display_data_status()
    
    # ===== データ処理セクション =====
    if st.session_state.get('data_processed', False):
        # データが既に存在する場合
        display_data_update_section()
    else:
        # データが存在しない場合
        display_initial_upload_section()
    
    # ===== データ管理セクション =====
    display_data_management_section()

def display_data_status():
    """データ状況の表示"""
    st.markdown("### 📊 現在のデータ状況")
    
    info = get_persistent_data_info()
    
    if info.get('exists') and st.session_state.get('data_processed', False):
        # データ存在時の表示
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "データ状況",
                "✅ 読み込み済み",
                delta="継続利用可能"
            )
        
        with col2:
            record_count = info.get('record_count', 0)
            st.metric(
                "データ件数", 
                f"{record_count:,}件",
                delta=info.get('date_range', 'N/A')
            )
        
        with col3:
            if 'save_timestamp' in info:
                last_update = info['save_timestamp']
                if isinstance(last_update, datetime):
                    update_str = last_update.strftime('%m/%d %H:%M')
                    days_ago = (datetime.now() - last_update).days
                    delta_str = f"{days_ago}日前" if days_ago > 0 else "今日"
                else:
                    update_str = "不明"
                    delta_str = ""
                
                st.metric(
                    "最終更新",
                    update_str,
                    delta=delta_str
                )
        
        # 詳細情報の表示
        with st.expander("📋 データ詳細情報", expanded=False):
            data_info = export_data_info()
            for key, value in data_info.items():
                st.write(f"**{key}**: {value}")
    
    else:
        # データ未存在時の表示
        st.info("📁 データがアップロードされていません。下記からファイルをアップロードしてください。")

def display_initial_upload_section():
    """初回アップロードセクション"""
    st.markdown("### 📁 ファイルアップロード")
    
    # ファイルアップローダー
    uploaded_files = st.file_uploader(
        "ファイルを選択してください",
        type=['xlsx', 'xls', 'csv'],
        accept_multiple_files=True,
        help="Excel形式またはCSV形式のファイルをアップロードできます"
    )
    
    # 目標値ファイルのアップロード
    with st.expander("🎯 目標値ファイル（オプション）", expanded=False):
        target_file = st.file_uploader(
            "目標値ファイル",
            type=['xlsx', 'xls', 'csv'],
            help="目標値が設定されたファイルをアップロードできます"
        )
    
    # 処理実行
    if uploaded_files:
        if st.button("📊 データ処理を開始", type="primary", use_container_width=True):
            process_and_save_data(uploaded_files, target_file)

def display_data_update_section():
    """データ更新セクション"""
    st.markdown("### 🔄 データ更新")
    
    with st.expander("📁 新しいデータをアップロード", expanded=False):
        st.info("💡 新しいファイルをアップロードして既存データを更新できます。")
        
        # 更新オプション
        update_mode = st.radio(
            "更新方法を選択",
            ["完全置換", "データ追加"],
            help="完全置換: 既存データを新データで置き換え\nデータ追加: 既存データに新データを追加"
        )
        
        # ファイルアップローダー
        new_files = st.file_uploader(
            "新しいファイルを選択",
            type=['xlsx', 'xls', 'csv'],
            accept_multiple_files=True,
            key="update_files"
        )
        
        # 目標値ファイル更新
        new_target_file = st.file_uploader(
            "新しい目標値ファイル（オプション）",
            type=['xlsx', 'xls', 'csv'],
            key="update_target_file"
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            if new_files and st.button("🔄 データを更新", type="primary"):
                update_existing_data(new_files, new_target_file, update_mode)
        
        with col2:
            if st.button("🔃 現在のデータを再処理"):
                reprocess_current_data()

def display_data_management_section():
    """データ管理セクション"""
    
    if st.session_state.get('data_processed', False):
        st.markdown("### ⚙️ データ管理")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📤 データエクスポート"):
                export_current_data()
        
        with col2:
            if st.button("🔄 バックアップ復元"):
                if restore_from_backup():
                    st.success("バックアップから復元しました。")
                    st.rerun()
        
        with col3:
            if st.button("🔃 データ再読み込み"):
                reload_persistent_data()
        
        with col4:
            if st.button("🗑️ データクリア", type="secondary"):
                show_data_clear_confirmation()

def process_and_save_data(uploaded_files, target_file=None):
    """データ処理と保存"""
    try:
        with st.spinner("データを処理中..."):
            # ファイル読み込み
            progress_bar = st.progress(0)
            progress_bar.progress(25, "ファイルを読み込み中...")
            
            df_raw = load_files(None, uploaded_files)
            if df_raw is None or df_raw.empty:
                st.error("ファイルの読み込みに失敗しました。")
                return
            
            progress_bar.progress(50, "データを前処理中...")
            
            # データ前処理
            df_processed, validation_results = integrated_preprocess_data(df_raw)
            if df_processed is None or df_processed.empty:
                st.error("データの前処理に失敗しました。")
                return
            
            progress_bar.progress(75, "目標データを処理中...")
            
            # 目標データの処理
            target_data = None
            if target_file is not None:
                try:
                    target_data = load_files(None, [target_file])
                except Exception as e:
                    st.warning(f"目標データの読み込みに失敗しました: {e}")
            
            progress_bar.progress(90, "データを保存中...")
            
            # メタデータの準備
            metadata = {
                'upload_files': [f.name for f in uploaded_files],
                'target_file': target_file.name if target_file else None,
                'validation_results': validation_results,
                'processing_timestamp': datetime.now()
            }
            
            # 基本設定の準備
            settings = {
                'total_beds': st.session_state.get('total_beds', 612),
                'bed_occupancy_rate': st.session_state.get('bed_occupancy_rate', 0.85),
                'avg_length_of_stay': st.session_state.get('avg_length_of_stay', 12.0),
                'avg_admission_fee': st.session_state.get('avg_admission_fee', 55000)
            }
            
            # データ保存
            if save_persistent_data(df_processed, target_data, settings, metadata):
                # セッション状態の更新
                st.session_state['df'] = df_processed
                st.session_state['target_data'] = target_data
                st.session_state['data_processed'] = True
                st.session_state['data_loaded_from_persistent'] = True
                
                progress_bar.progress(100, "完了!")
                st.success("✅ データの処理と保存が完了しました！")
                st.balloons()
                
                # データ統計の表示
                show_processing_results(df_processed, validation_results)
                
            else:
                st.error("データの保存に失敗しました。")
                
    except Exception as e:
        st.error(f"データ処理中にエラーが発生しました: {str(e)}")

def update_existing_data(new_files, target_file, update_mode):
    """既存データの更新"""
    try:
        with st.spinner(f"データを{update_mode}中..."):
            # 新しいデータの読み込み・処理
            df_new = load_files(None, new_files)
            df_new_processed, validation_results = integrated_preprocess_data(df_new)
            
            if update_mode == "完全置換":
                df_final = df_new_processed
                st.info("既存データを新しいデータで完全に置き換えました。")
            else:  # データ追加
                df_existing = st.session_state.get('df')
                if df_existing is not None:
                    df_final = pd.concat([df_existing, df_new_processed], ignore_index=True)
                    # 重複データの除去
                    df_final = df_final.drop_duplicates()
                    st.info(f"既存データに{len(df_new_processed)}件のデータを追加しました。")
                else:
                    df_final = df_new_processed
            
            # 目標データの処理
            target_data = None
            if target_file is not None:
                target_data = load_files(None, [target_file])
            else:
                target_data = st.session_state.get('target_data')
            
            # メタデータと設定の準備
            metadata = {
                'update_mode': update_mode,
                'update_files': [f.name for f in new_files],
                'update_timestamp': datetime.now()
            }
            
            settings = {key: st.session_state.get(key) for key in [
                'total_beds', 'bed_occupancy_rate', 'avg_length_of_stay', 'avg_admission_fee'
            ]}
            
            # 保存と状態更新
            if save_persistent_data(df_final, target_data, settings, metadata):
                st.session_state['df'] = df_final
                st.session_state['target_data'] = target_data
                st.success("✅ データの更新が完了しました！")
                st.rerun()
                
    except Exception as e:
        st.error(f"データ更新中にエラーが発生しました: {str(e)}")

def reprocess_current_data():
    """現在のデータの再処理"""
    try:
        with st.spinner("データを再処理中..."):
            df_current = st.session_state.get('df')
            if df_current is None:
                st.error("再処理するデータが見つかりません。")
                return
            
            # 再処理（設定値の変更を反映）
            settings = {key: st.session_state.get(key) for key in [
                'total_beds', 'bed_occupancy_rate', 'avg_length_of_stay', 'avg_admission_fee'
            ]}
            
            metadata = {
                'reprocess_timestamp': datetime.now(),
                'action': 'reprocess'
            }
            
            if save_persistent_data(df_current, st.session_state.get('target_data'), settings, metadata):
                st.success("✅ データの再処理が完了しました！")
                st.rerun()
                
    except Exception as e:
        st.error(f"再処理中にエラーが発生しました: {str(e)}")

def export_current_data():
    """現在のデータのエクスポート"""
    try:
        df = st.session_state.get('df')
        if df is None:
            st.error("エクスポートするデータがありません。")
            return
        
        # CSV形式でダウンロード
        csv_data = df.to_csv(index=False).encode('utf-8-sig')
        
        st.download_button(
            label="📥 CSVファイルをダウンロード",
            data=csv_data,
            file_name=f"hospital_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
        
        st.success("ダウンロードボタンが生成されました。")
        
    except Exception as e:
        st.error(f"エクスポート中にエラーが発生しました: {str(e)}")

def reload_persistent_data():
    """永続化データの再読み込み"""
    try:
        with st.spinner("データを再読み込み中..."):
            if auto_load_persistent_data():
                st.success("✅ データを再読み込みしました！")
                st.rerun()
            else:
                st.error("データの再読み込みに失敗しました。")
                
    except Exception as e:
        st.error(f"再読み込み中にエラーが発生しました: {str(e)}")

def show_data_clear_confirmation():
    """データクリア確認ダイアログ"""
    st.warning("⚠️ この操作により、保存されたすべてのデータが削除されます。")
    
    if st.button("🗑️ 確認してデータを削除", type="secondary"):
        if clear_persistent_data():
            # セッション状態のクリア
            keys_to_clear = ['df', 'target_data', 'data_processed', 'data_loaded_from_persistent']
            for key in keys_to_clear:
                if key in st.session_state:
                    del st.session_state[key]
            
            st.success("✅ データを削除しました。")
            st.rerun()
        else:
            st.error("データの削除に失敗しました。")

def show_processing_results(df, validation_results):
    """処理結果の表示"""
    st.markdown("### 📊 処理結果")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("総レコード数", f"{len(df):,}件")
    
    with col2:
        date_range = "不明"
        if '日付' in df.columns:
            min_date = df['日付'].min().strftime('%Y-%m-%d')
            max_date = df['日付'].max().strftime('%Y-%m-%d')
            date_range = f"{min_date} ～ {max_date}"
        st.metric("データ期間", date_range)
    
    with col3:
        unique_wards = df['病棟コード'].nunique() if '病棟コード' in df.columns else 0
        st.metric("病棟数", f"{unique_wards}箇所")
    
    # バリデーション結果
    if validation_results:
        with st.expander("🔍 データ検証結果", expanded=False):
            for key, value in validation_results.items():
                st.write(f"**{key}**: {value}")