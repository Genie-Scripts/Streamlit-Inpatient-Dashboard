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

def load_single_file(uploaded_file):
    """
    単一ファイルの読み込み（Excel/CSV対応）
    
    Parameters:
    -----------
    uploaded_file: StreamlitUploadedFile
        アップロードされたファイル
        
    Returns:
    --------
    pd.DataFrame
        読み込まれたデータフレーム
    """
    try:
        # ファイル拡張子の確認
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        
        if file_extension in ['.xlsx', '.xls']:
            # Excel ファイルの場合は既存のload_files関数を使用
            return load_files(None, [uploaded_file])
        
        elif file_extension == '.csv':
            # CSV ファイルの直接読み込み
            try:
                # ファイルポインタを先頭に戻す
                uploaded_file.seek(0)
                
                # まずUTF-8で試行
                try:
                    df = pd.read_csv(uploaded_file, encoding='utf-8')
                except UnicodeDecodeError:
                    # UTF-8で失敗した場合はShift-JISで試行
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, encoding='shift_jis')
                
                print(f"CSV読込成功: {uploaded_file.name} - {len(df)}行 × {len(df.columns)}列")
                print(f"CSV列名: {list(df.columns)}")
                
                return df
                
            except Exception as e:
                print(f"CSV読込エラー ({uploaded_file.name}): {str(e)}")
                return pd.DataFrame()
        
        else:
            print(f"サポートされていないファイル形式: {file_extension}")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"ファイル読込エラー ({uploaded_file.name}): {str(e)}")
        return pd.DataFrame()

def process_and_save_data(uploaded_files, target_file=None):
    """データ処理と保存（CSV対応版）"""
    try:
        with st.spinner("データを処理中..."):
            # ファイル読み込み
            progress_bar = st.progress(0)
            progress_bar.progress(25, "ファイルを読み込み中...")
            
            df_raw = load_files(None, uploaded_files)
            if df_raw is None or df_raw.empty:
                st.error("ファイルの読み込みに失敗しました。")
                return
            
            st.write(f"📊 読み込み完了: {len(df_raw):,}件")
            
            progress_bar.progress(50, "目標データを処理中...")
            
            # ✅ 修正：目標データの処理（CSV対応）
            target_data = None
            if target_file is not None:
                try:
                    # ✅ 修正：CSVファイルに対応した読み込み
                    target_data = load_single_file(target_file)
                    
                    if target_data is not None and not target_data.empty:
                        st.write(f"🎯 目標データ読み込み完了: {len(target_data):,}件")
                        st.write(f"🏷️ 目標データ列: {list(target_data.columns)}")
                        
                        # 部門コード列の確認
                        if '部門コード' in target_data.columns:
                            unique_depts = target_data['部門コード'].nunique()
                            dept_list = target_data['部門コード'].unique()[:10]  # 最初の10個を表示
                            st.success(f"✅ 部門コード列を確認: {unique_depts}部門")
                            st.info(f"📋 部門コード例: {list(dept_list)}")
                        else:
                            st.warning("⚠️ 目標データに'部門コード'列が見つかりません")
                            st.write(f"利用可能な列: {list(target_data.columns)}")
                        
                        # 部門名列の確認
                        if '部門名' in target_data.columns:
                            dept_names = target_data['部門名'].unique()[:10]
                            st.info(f"🏥 部門名例: {list(dept_names)}")
                            
                    else:
                        st.warning("⚠️ 目標データが空です")
                        
                except Exception as e:
                    st.error(f"目標データの読み込みに失敗しました: {e}")
                    import traceback
                    st.error(traceback.format_exc())
                    target_data = None
            
            progress_bar.progress(75, "データを前処理中...")
            
            # ✅ 修正：target_dataを明示的に渡す
            df_processed, validation_results = integrated_preprocess_data(df_raw, target_data_df=target_data)
            if df_processed is None or df_processed.empty:
                st.error("データの前処理に失敗しました。")
                return
            
            st.write(f"📊 前処理完了: {len(df_processed):,}件")
            loss_count = len(df_raw) - len(df_processed)
            if loss_count > 0:
                loss_rate = (loss_count / len(df_raw)) * 100
                st.warning(f"⚠️ 前処理で{loss_count:,}件削除されました（{loss_rate:.1f}%）")
                if loss_rate > 10:
                    st.error("🚨 大量のデータが失われています。設定を確認してください。")
            else:
                st.success("✅ データ損失なし")
            
            progress_bar.progress(90, "データを保存中...")
            
            # メタデータの準備
            metadata = {
                'upload_files': [f.name for f in uploaded_files],
                'target_file': target_file.name if target_file else None,
                'validation_results': validation_results,
                'processing_timestamp': datetime.now(),
                'raw_record_count': len(df_raw),
                'processed_record_count': len(df_processed)
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
                
                # バリデーション結果の詳細表示
                if validation_results:
                    with st.expander("🔍 処理結果詳細", expanded=False):
                        if validation_results.get('warnings'):
                            st.warning("⚠️ 警告:")
                            for warning in validation_results['warnings']:
                                st.write(f"• {warning}")
                        
                        if validation_results.get('info'):
                            st.info("ℹ️ 情報:")
                            for info in validation_results['info']:
                                st.write(f"• {info}")
                        
                        if validation_results.get('errors'):
                            st.error("❌ エラー:")
                            for error in validation_results['errors']:
                                st.write(f"• {error}")
                
                # ✅ 追加：診療科マッピング状況の表示
                if target_data is not None and not target_data.empty:
                    with st.expander("🏥 診療科マッピング状況", expanded=False):
                        # 実データの診療科名
                        actual_depts = df_processed['診療科名'].unique() if '診療科名' in df_processed.columns else []
                        st.write(f"**実データの診療科:** {len(actual_depts)}種類")
                        st.write(f"例: {list(actual_depts[:10])}")
                        
                        # 目標データの部門
                        target_dept_codes = target_data['部門コード'].unique() if '部門コード' in target_data.columns else []
                        target_dept_names = target_data['部門名'].unique() if '部門名' in target_data.columns else []
                        
                        st.write(f"**目標データの部門コード:** {len(target_dept_codes)}種類")
                        st.write(f"例: {list(target_dept_codes[:10])}")
                        
                        if len(target_dept_names) > 0:
                            st.write(f"**目標データの部門名:** {len(target_dept_names)}種類")
                            st.write(f"例: {list(target_dept_names[:10])}")
                
                # データ統計の表示
                show_processing_results(df_processed, validation_results)
                
            else:
                st.error("データの保存に失敗しました。")
                
    except Exception as e:
        st.error(f"データ処理中にエラーが発生しました: {str(e)}")
        import traceback
        st.error(traceback.format_exc())

def update_existing_data(new_files, target_file, update_mode):
    """既存データの更新（目標値ファイル対応版）"""
    try:
        with st.spinner(f"データを{update_mode}中..."):
            # 新しいデータの読み込み・処理
            df_new = load_files(None, new_files)
            st.write(f"📊 新データ読み込み: {len(df_new):,}件")
            
            # ✅ 修正：目標データの処理
            target_data = None
            if target_file is not None:
                try:
                    target_data = load_files(None, [target_file])
                    if target_data is not None and not target_data.empty:
                        st.write(f"🎯 目標データ更新: {len(target_data):,}件")
                except Exception as e:
                    st.warning(f"目標データの更新に失敗: {e}")
            else:
                target_data = st.session_state.get('target_data')
            
            # ✅ 修正：前処理時に目標データを渡す
            df_new_processed, validation_results = integrated_preprocess_data(df_new, target_data_df=target_data)
            st.write(f"📊 新データ前処理完了: {len(df_new_processed):,}件")
            
            if update_mode == "完全置換":
                df_final = df_new_processed
                st.info("既存データを新しいデータで完全に置き換えました。")
            else:  # データ追加
                df_existing = st.session_state.get('df')
                if df_existing is not None:
                    st.write(f"📊 既存データ: {len(df_existing):,}件")
                    
                    # データ結合
                    df_combined = pd.concat([df_existing, df_new_processed], ignore_index=True)
                    st.write(f"📊 結合後: {len(df_combined):,}件")
                    
                    # 重複除去を安全に実行
                    before_dedup = len(df_combined)
                    if '日付' in df_combined.columns and '病棟コード' in df_combined.columns:
                        df_final = df_combined.drop_duplicates(
                            subset=['日付', '病棟コード', '診療科名'] if '診療科名' in df_combined.columns else ['日付', '病棟コード']
                        )
                    else:
                        df_final = df_combined
                        st.warning("⚠️ 適切な重複除去キーが見つからないため、重複除去をスキップしました。")
                    
                    after_dedup = len(df_final)
                    removed_count = before_dedup - after_dedup
                    
                    st.write(f"📊 重複除去後: {len(df_final):,}件")
                    if removed_count > 0:
                        st.info(f"🔄 {removed_count:,}件の重複データを除去しました。")
                else:
                    df_final = df_new_processed
            
            st.write(f"📊 最終データ: {len(df_final):,}件")
            
            # メタデータと設定の準備
            metadata = {
                'update_mode': update_mode,
                'update_files': [f.name for f in new_files],
                'target_file': target_file.name if target_file else None,
                'update_timestamp': datetime.now(),
                'final_record_count': len(df_final)
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
        import traceback
        st.error(traceback.format_exc())

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