# memory_manager.py - メモリ管理モジュール

import gc
import time
import os
import psutil
import warnings
import streamlit as st

class MemoryManager:
    """メモリ使用状況を監視し、最適化するクラス"""
    
    def __init__(self, check_interval=300, high_threshold=85, critical_threshold=95):
        """
        Parameters:
        -----------
        check_interval : int
            メモリチェックの間隔（秒）
        high_threshold : int
            警告を発するメモリ使用率のしきい値（%）
        critical_threshold : int
            強制的なメモリ解放を行うしきい値（%）
        """
        self.check_interval = check_interval
        self.high_threshold = high_threshold
        self.critical_threshold = critical_threshold
        self.last_check_time = 0
        self.global_caches = {}
        
    def register_cache(self, name, cache_obj):
        """グローバルキャッシュを登録する"""
        self.global_caches[name] = cache_obj
        
    def get_memory_usage(self):
        """現在のメモリ使用率を取得する"""
        try:
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            mem_percent = process.memory_percent()
            return {
                'rss': mem_info.rss / (1024 * 1024),  # MB
                'vms': mem_info.vms / (1024 * 1024),  # MB
                'percent': mem_percent
            }
        except Exception:
            # psutilが使えない場合はNoneを返す
            return None
            
    def check_memory(self, force=False):
        """
        メモリ使用状況をチェックし、必要に応じて最適化する
        
        Parameters:
        -----------
        force : bool
            強制的にチェックを実行するかどうか
        
        Returns:
        --------
        dict or None
            メモリ使用状況の情報、またはエラー時はNone
        """
        current_time = time.time()
        
        # 強制実行でない場合、前回のチェックからinterval秒以上経過していない場合はスキップ
        if not force and (current_time - self.last_check_time) < self.check_interval:
            return None
            
        self.last_check_time = current_time
        
        # メモリ使用率を取得
        mem_usage = self.get_memory_usage()
        if mem_usage is None:
            return None
            
        # 使用率に応じた処理
        if mem_usage['percent'] >= self.critical_threshold:
            # 危険なレベルのメモリ使用 - 強制クリーンアップ
            self._force_cleanup()
            warnings.warn(f"メモリ使用率が危険なレベル ({mem_usage['percent']:.1f}%) に達したため、強制クリーンアップを実行しました")
            
        elif mem_usage['percent'] >= self.high_threshold:
            # 高いメモリ使用 - 不要なキャッシュをクリア
            self._clear_unused_caches()
            warnings.warn(f"メモリ使用率が高い ({mem_usage['percent']:.1f}%) ため、不要なキャッシュをクリアしました")
            
        return mem_usage
    
    def _clear_unused_caches(self):
        """不要なキャッシュを削除する"""
        # アクティブなキャッシュキーを取得
        active_keys = st.session_state.get('active_cache_keys', set())
        
        # 各キャッシュをチェック
        for cache_name, cache_obj in self.global_caches.items():
            # キャッシュオブジェクトの型に応じて処理
            if isinstance(cache_obj, dict):
                # 辞書型キャッシュ
                keys_to_remove = []
                
                for k in cache_obj.keys():
                    if k not in active_keys:
                        keys_to_remove.append(k)
                
                # 不要なキーを半分だけ削除
                for k in keys_to_remove[:len(keys_to_remove)//2]:
                    cache_obj.pop(k, None)
            
            # 他の型のキャッシュがあれば、それに応じた処理を追加
        
        # ガベージコレクションを実行
        gc.collect()
    
# memory_manager.py - メモリ管理モジュール (続き)

    def _force_cleanup(self):
        """強制的にメモリを解放する"""
        # すべてのグローバルキャッシュをクリア
        for cache_name, cache_obj in self.global_caches.items():
            if isinstance(cache_obj, dict):
                cache_obj.clear()
        
        # セッションステートから不要なデータを削除
        if 'filtered_results' in st.session_state and st.session_state.filtered_results != st.session_state.all_results:
            st.session_state.filtered_results = None
            
        if 'forecast_model_results' in st.session_state:
            st.session_state.forecast_model_results = None
            
        # その他の不要な大きなデータを削除
        # テンポラリディレクトリのクリーンアップ
        self._cleanup_temp_files()
        
        # ガベージコレクションを実行
        gc.collect()
        
    def _cleanup_temp_files(self):
        """一時ファイルをクリーンアップする"""
        try:
            import tempfile
            import os
            import glob
            
            # アプリケーション用のテンポラリディレクトリを特定
            app_temp_dir = os.path.join(tempfile.gettempdir(), 'patient_forecast_app_*')
            
            # 古い一時ファイルを削除
            for temp_dir in glob.glob(app_temp_dir):
                # 24時間以上前のファイルのみ削除
                if os.path.isdir(temp_dir):
                    dir_mtime = os.path.getmtime(temp_dir)
                    if (time.time() - dir_mtime) > 86400:  # 24時間
                        try:
                            import shutil
                            shutil.rmtree(temp_dir, ignore_errors=True)
                        except Exception:
                            pass
        except Exception:
            # エラーは無視
            pass
            
    def log_memory_stats(self):
        """メモリ使用状況をログに記録する"""
        mem_usage = self.get_memory_usage()
        if mem_usage:
            print(f"メモリ使用: {mem_usage['rss']:.1f} MB, {mem_usage['percent']:.1f}%")