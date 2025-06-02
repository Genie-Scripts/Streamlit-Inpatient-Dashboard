# data_persistence.py - データ永続化機能

import pickle
import os
import pandas as pd
import streamlit as st
from datetime import datetime
import json
import shutil

# ===== 設定 =====
DATA_DIR = "saved_data"
MAIN_DATA_FILE = os.path.join(DATA_DIR, "main_data.pkl")
METADATA_FILE = os.path.join(DATA_DIR, "metadata.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
BACKUP_DIR = os.path.join(DATA_DIR, "backup")

def ensure_data_directory():
    """データディレクトリの存在確認・作成"""
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        return True
    except Exception as e:
        st.error(f"ディレクトリ作成エラー: {e}")
        return False

def create_backup():
    """現在のデータのバックアップを作成"""
    try:
        if os.path.exists(MAIN_DATA_FILE):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(BACKUP_DIR, f"main_data_backup_{timestamp}.pkl")
            shutil.copy2(MAIN_DATA_FILE, backup_file)
            
            # 古いバックアップファイルを削除（最新5個まで保持）
            backup_files = [f for f in os.listdir(BACKUP_DIR) if f.startswith("main_data_backup_")]
            backup_files.sort(reverse=True)
            
            for old_backup in backup_files[5:]:
                try:
                    os.remove(os.path.join(BACKUP_DIR, old_backup))
                except:
                    pass
            
            return True
    except Exception as e:
        st.warning(f"バックアップ作成エラー: {e}")
        return False

def save_data_to_file(df, target_data=None, metadata=None):
    """データをファイルに保存"""
    try:
        if not ensure_data_directory():
            return False
        
        # 既存データのバックアップ
        create_backup()
        
        # メインデータの保存
        data_to_save = {
            'df': df,
            'target_data': target_data,
            'saved_at': datetime.now(),
            'data_shape': df.shape if df is not None else None,
            'version': '1.1'
        }
        
        with open(MAIN_DATA_FILE, 'wb') as f:
            pickle.dump(data_to_save, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        # メタデータの保存
        if metadata is None:
            metadata = {}
        
        metadata.update({
            'last_saved': datetime.now().isoformat(),
            'data_rows': len(df) if df is not None else 0,
            'data_columns': list(df.columns) if df is not None else [],
            'file_size_mb': round(os.path.getsize(MAIN_DATA_FILE) / (1024 * 1024), 2),
            'date_range': {
                'min_date': df['日付'].min().isoformat() if df is not None and '日付' in df.columns else None,
                'max_date': df['日付'].max().isoformat() if df is not None and '日付' in df.columns else None
            }
        })
        
        with open(METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2, default=str)
        
        return True
        
    except Exception as e:
        st.error(f"データ保存エラー: {e}")
        return False

def load_data_from_file():
    """ファイルからデータを読み込み"""
    try:
        if not os.path.exists(MAIN_DATA_FILE):
            return None, None, None
        
        # メインデータの読み込み
        with open(MAIN_DATA_FILE, 'rb') as f:
            saved_data = pickle.load(f)
        
        # メタデータの読み込み
        metadata = None
        if os.path.exists(METADATA_FILE):
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        
        # データの妥当性チェック
        df = saved_data.get('df')
        if df is not None and isinstance(df, pd.DataFrame):
            # 日付列の型確認・修正
            if '日付' in df.columns:
                df['日付'] = pd.to_datetime(df['日付'])
        
        return df, saved_data.get('target_data'), metadata
        
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return None, None, None

def save_settings_to_file(settings):
    """設定をファイルに保存"""
    try:
        if not ensure_data_directory():
            return False
        
        settings_to_save = {
            'saved_at': datetime.now().isoformat(),
            'settings': settings,
            'version': '1.1'
        }
        
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings_to_save, f, ensure_ascii=False, indent=2)
        
        return True
        
    except Exception as e:
        st.error(f"設定保存エラー: {e}")
        return False

def load_settings_from_file():
    """ファイルから設定を読み込み"""
    try:
        if not os.path.exists(SETTINGS_FILE):
            return None
        
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            saved_settings = json.load(f)
        
        return saved_settings.get('settings')
        
    except Exception as e:
        st.error(f"設定読み込みエラー: {e}")
        return None

def get_data_info():
    """保存されたデータの情報を取得"""
    try:
        if not os.path.exists(METADATA_FILE):
            return None
        
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        return metadata
        
    except Exception as e:
        return None

def delete_saved_data():
    """保存されたデータを削除"""
    try:
        files_to_delete = [MAIN_DATA_FILE, METADATA_FILE, SETTINGS_FILE]
        deleted_files = []
        
        for file_path in files_to_delete:
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted_files.append(os.path.basename(file_path))
        
        # バックアップディレクトリも削除
        if os.path.exists(BACKUP_DIR):
            shutil.rmtree(BACKUP_DIR)
            deleted_files.append("backup/")
        
        return True, deleted_files
        
    except Exception as e:
        return False, str(e)

def auto_load_data():
    """アプリ起動時の自動データ読み込み"""
    if 'auto_load_attempted' not in st.session_state:
        st.session_state.auto_load_attempted = True
        
        # 既にセッション状態にデータがある場合はスキップ
        if st.session_state.get('data_processed', False):
            return False
        
        df, target_data, metadata = load_data_from_file()
        
        if df is not None:
            st.session_state['df'] = df
            st.session_state['target_data'] = target_data
            st.session_state['data_processed'] = True
            st.session_state['data_source'] = 'auto_loaded'
            st.session_state['data_metadata'] = metadata
            
            # 最新データ日付の設定
            if '日付' in df.columns:
                latest_date = df['日付'].max()
                st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
            
            return True
    
    return False

def get_file_sizes():
    """保存ファイルのサイズ情報を取得"""
    try:
        sizes = {}
        files = [
            ('main_data', MAIN_DATA_FILE, 'メインデータ'),
            ('metadata', METADATA_FILE, 'メタデータ'), 
            ('settings', SETTINGS_FILE, '設定ファイル')
        ]
        
        for name, filepath, display_name in files:
            if os.path.exists(filepath):
                size_bytes = os.path.getsize(filepath)
                if size_bytes < 1024:
                    sizes[display_name] = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    sizes[display_name] = f"{size_bytes / 1024:.1f} KB"
                else:
                    sizes[display_name] = f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                sizes[display_name] = "未保存"
        
        return sizes
        
    except Exception:
        return {}

def get_backup_info():
    """バックアップファイルの情報を取得"""
    try:
        if not os.path.exists(BACKUP_DIR):
            return []
        
        backup_files = [f for f in os.listdir(BACKUP_DIR) if f.startswith("main_data_backup_")]
        backup_info = []
        
        for backup_file in sorted(backup_files, reverse=True):
            file_path = os.path.join(BACKUP_DIR, backup_file)
            timestamp_str = backup_file.replace("main_data_backup_", "").replace(".pkl", "")
            
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                formatted_time = timestamp.strftime("%Y/%m/%d %H:%M:%S")
                file_size = os.path.getsize(file_path)
                
                if file_size < 1024 * 1024:
                    size_str = f"{file_size / 1024:.1f} KB"
                else:
                    size_str = f"{file_size / (1024 * 1024):.1f} MB"
                
                backup_info.append({
                    'filename': backup_file,
                    'timestamp': formatted_time,
                    'size': size_str,
                    'path': file_path
                })
            except:
                continue
        
        return backup_info[:5]  # 最新5個まで
        
    except Exception:
        return []

def restore_from_backup(backup_filename):
    """バックアップからデータを復元"""
    try:
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        if not os.path.exists(backup_path):
            return False, "バックアップファイルが見つかりません"
        
        # 現在のファイルをバックアップ
        create_backup()
        
        # バックアップファイルを復元
        shutil.copy2(backup_path, MAIN_DATA_FILE)
        
        # セッション状態をクリア
        keys_to_clear = ['df', 'target_data', 'data_processed', 'data_source', 'data_metadata']
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        return True, "復元完了"
        
    except Exception as e:
        return False, f"復元エラー: {e}"

def export_data_package(export_path=None):
    """データパッケージのエクスポート（他端末への移行用）"""
    try:
        if export_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = f"data_export_{timestamp}.zip"
        
        import zipfile
        
        with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            files_to_export = [
                (MAIN_DATA_FILE, "main_data.pkl"),
                (METADATA_FILE, "metadata.json"),
                (SETTINGS_FILE, "settings.json")
            ]
            
            for source_path, archive_name in files_to_export:
                if os.path.exists(source_path):
                    zipf.write(source_path, archive_name)
        
        return True, export_path
        
    except Exception as e:
        return False, str(e)

def import_data_package(import_file):
    """データパッケージのインポート"""
    try:
        import zipfile
        
        if not ensure_data_directory():
            return False, "ディレクトリ作成失敗"
        
        # 現在のデータをバックアップ
        create_backup()
        
        with zipfile.ZipFile(import_file, 'r') as zipf:
            zipf.extractall(DATA_DIR)
        
        # セッション状態をクリア
        keys_to_clear = ['df', 'target_data', 'data_processed', 'data_source', 'data_metadata']
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        return True, "インポート完了"
        
    except Exception as e:
        return False, f"インポートエラー: {e}"