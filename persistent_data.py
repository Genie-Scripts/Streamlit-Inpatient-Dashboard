# persistent_data.py - データ永続化機能
import os
import pickle
import pandas as pd
import streamlit as st
from datetime import datetime
import hashlib
import shutil

# ===== 設定値 =====
DATA_DIR = "data"
PERSISTENT_FILE = os.path.join(DATA_DIR, "persistent_data.pkl")
BACKUP_FILE = os.path.join(DATA_DIR, "persistent_data_backup.pkl")
MAX_FILE_SIZE_MB = 100  # 最大ファイルサイズ

def ensure_data_directory():
    """データディレクトリの作成"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        print(f"データディレクトリを作成しました: {DATA_DIR}")

def calculate_checksum(data):
    """データのチェックサム計算"""
    try:
        data_str = str(data).encode('utf-8')
        return hashlib.md5(data_str).hexdigest()
    except Exception as e:
        print(f"チェックサム計算エラー: {e}")
        return None

def save_persistent_data(df, target_data=None, settings=None, metadata=None):
    """
    データの永続化保存
    
    Parameters:
    -----------
    df : pd.DataFrame
        メインのデータフレーム
    target_data : pd.DataFrame, optional
        目標データ
    settings : dict, optional
        基本設定値
    metadata : dict, optional
        メタデータ
    
    Returns:
    --------
    bool
        保存成功時True、失敗時False
    """
    try:
        ensure_data_directory()
        
        # 既存ファイルのバックアップ作成
        if os.path.exists(PERSISTENT_FILE):
            shutil.copy2(PERSISTENT_FILE, BACKUP_FILE)
            print("既存データのバックアップを作成しました。")
        
        # 保存データの準備
        save_data = {
            'df': df,
            'target_data': target_data,
            'settings': settings or {},
            'metadata': metadata or {},
            'save_timestamp': datetime.now(),
            'app_version': '2.0',
            'data_shape': df.shape if df is not None else (0, 0),
            'checksum': calculate_checksum(df)
        }
        
        # ファイルサイズチェック
        with open(PERSISTENT_FILE, 'wb') as f:
            pickle.dump(save_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        file_size_mb = os.path.getsize(PERSISTENT_FILE) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            os.remove(PERSISTENT_FILE)
            raise ValueError(f"ファイルサイズが制限を超えています: {file_size_mb:.1f}MB > {MAX_FILE_SIZE_MB}MB")
        
        print(f"データを正常に保存しました。ファイルサイズ: {file_size_mb:.2f}MB")
        return True
        
    except Exception as e:
        print(f"データ保存エラー: {e}")
        st.error(f"データの保存に失敗しました: {str(e)}")
        return False

def load_persistent_data():
    """
    永続化データの読み込み
    
    Returns:
    --------
    dict or None
        読み込み成功時はデータ辞書、失敗時はNone
    """
    try:
        if not os.path.exists(PERSISTENT_FILE):
            print("永続化ファイルが存在しません。")
            return None
        
        with open(PERSISTENT_FILE, 'rb') as f:
            data = pickle.load(f)
        
        # データ整合性チェック
        if not isinstance(data, dict):
            raise ValueError("無効なデータ形式です。")
        
        required_keys = ['df', 'save_timestamp']
        for key in required_keys:
            if key not in data:
                raise ValueError(f"必要なキー '{key}' が見つかりません。")
        
        # チェックサム検証（可能な場合）
        if 'checksum' in data and data['checksum']:
            current_checksum = calculate_checksum(data['df'])
            if current_checksum != data['checksum']:
                print("警告: データのチェックサムが一致しません。")
        
        print(f"データを正常に読み込みました。保存日時: {data['save_timestamp']}")
        return data
        
    except Exception as e:
        print(f"データ読み込みエラー: {e}")
        st.error(f"データの読み込みに失敗しました: {str(e)}")
        
        # バックアップからの復旧を試行
        return load_backup_data()

def load_backup_data():
    """バックアップデータの読み込み"""
    try:
        if not os.path.exists(BACKUP_FILE):
            print("バックアップファイルも存在しません。")
            return None
        
        with open(BACKUP_FILE, 'rb') as f:
            data = pickle.load(f)
        
        print("バックアップからデータを復旧しました。")
        st.warning("メインファイルの読み込みに失敗したため、バックアップから復旧しました。")
        return data
        
    except Exception as e:
        print(f"バックアップ読み込みエラー: {e}")
        return None

def check_persistent_data_exists():
    """永続化データの存在確認"""
    return os.path.exists(PERSISTENT_FILE)

def get_persistent_data_info():
    """
    永続化データの情報取得
    
    Returns:
    --------
    dict
        データ情報の辞書
    """
    try:
        if not check_persistent_data_exists():
            return {
                'exists': False,
                'message': 'データが保存されていません'
            }
        
        # ファイル情報
        file_size_mb = os.path.getsize(PERSISTENT_FILE) / (1024 * 1024)
        file_mtime = datetime.fromtimestamp(os.path.getmtime(PERSISTENT_FILE))
        
        # データ内容の確認（ヘッダーのみ読み込み）
        try:
            with open(PERSISTENT_FILE, 'rb') as f:
                data = pickle.load(f)
            
            df_shape = data.get('data_shape', (0, 0))
            save_time = data.get('save_timestamp', file_mtime)
            app_version = data.get('app_version', '不明')
            
            # データ期間の取得
            df = data.get('df')
            date_range = "不明"
            if df is not None and '日付' in df.columns:
                min_date = df['日付'].min().strftime('%Y-%m-%d')
                max_date = df['日付'].max().strftime('%Y-%m-%d')
                date_range = f"{min_date} ～ {max_date}"
            
            return {
                'exists': True,
                'file_size_mb': file_size_mb,
                'last_modified': file_mtime,
                'save_timestamp': save_time,
                'data_shape': df_shape,
                'date_range': date_range,
                'app_version': app_version,
                'record_count': df_shape[0] if df_shape else 0
            }
            
        except Exception as e:
            return {
                'exists': True,
                'file_size_mb': file_size_mb,
                'last_modified': file_mtime,
                'error': f"データ読み込みエラー: {str(e)}"
            }
            
    except Exception as e:
        return {
            'exists': False,
            'error': f"情報取得エラー: {str(e)}"
        }

def clear_persistent_data():
    """永続化データのクリア"""
    try:
        files_removed = []
        
        if os.path.exists(PERSISTENT_FILE):
            os.remove(PERSISTENT_FILE)
            files_removed.append("メインデータ")
        
        if os.path.exists(BACKUP_FILE):
            os.remove(BACKUP_FILE)
            files_removed.append("バックアップデータ")
        
        if files_removed:
            print(f"削除完了: {', '.join(files_removed)}")
            return True
        else:
            print("削除対象のファイルが見つかりませんでした。")
            return False
            
    except Exception as e:
        print(f"データクリアエラー: {e}")
        st.error(f"データの削除に失敗しました: {str(e)}")
        return False

def restore_from_backup():
    """バックアップからの復元"""
    try:
        if not os.path.exists(BACKUP_FILE):
            st.error("バックアップファイルが存在しません。")
            return False
        
        shutil.copy2(BACKUP_FILE, PERSISTENT_FILE)
        st.success("バックアップからデータを復元しました。")
        return True
        
    except Exception as e:
        st.error(f"復元に失敗しました: {str(e)}")
        return False

def auto_load_persistent_data():
    """
    アプリ起動時の自動データ読み込み
    セッション状態を自動で設定
    """
    try:
        # 既にデータが読み込まれている場合はスキップ
        if st.session_state.get('data_processed', False):
            return True
        
        # 永続化データの読み込み
        persistent_data = load_persistent_data()
        if persistent_data is None:
            return False
        
        # セッション状態の復元
        st.session_state['df'] = persistent_data.get('df')
        st.session_state['target_data'] = persistent_data.get('target_data')
        st.session_state['data_processed'] = True
        st.session_state['data_loaded_from_persistent'] = True
        st.session_state['persistent_data_info'] = get_persistent_data_info()
        
        # 設定値の復元
        settings = persistent_data.get('settings', {})
        for key, value in settings.items():
            if key not in st.session_state:
                st.session_state[key] = value
        
        print("永続化データからセッション状態を復元しました。")
        return True
        
    except Exception as e:
        print(f"自動読み込みエラー: {e}")
        return False

def export_data_info():
    """データ情報のエクスポート用辞書作成"""
    info = get_persistent_data_info()
    if info.get('exists'):
        return {
            '保存状況': '✅ データ保存済み',
            '最終更新': info.get('save_timestamp', '不明').strftime('%Y-%m-%d %H:%M:%S') if isinstance(info.get('save_timestamp'), datetime) else str(info.get('save_timestamp', '不明')),
            'レコード数': f"{info.get('record_count', 0):,}件",
            'データ期間': info.get('date_range', '不明'),
            'ファイルサイズ': f"{info.get('file_size_mb', 0):.2f}MB",
            'アプリバージョン': info.get('app_version', '不明')
        }
    else:
        return {
            '保存状況': '❌ データ未保存',
            'メッセージ': info.get('message', '不明なエラー')
        }