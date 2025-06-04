# optimization_config.py - 最適化設定を管理（新規作成）

import multiprocessing
import psutil
import time
from dataclasses import dataclass
from typing import Dict, Any, Tuple

@dataclass
class OptimizationConfig:
    """最適化設定を管理するクラス"""
    
    # システム情報
    CPU_CORES: int = multiprocessing.cpu_count()
    MEMORY_GB: float = psutil.virtual_memory().total / (1024**3)
    
    # 基本設定
    MAX_WORKERS: int = None
    CHUNK_SIZE: int = None
    MEMORY_LIMIT_PERCENT: int = 85
    
    # グラフ生成設定
    GRAPH_THREAD_WORKERS: int = 4
    GRAPH_TIMEOUT_SECONDS: int = 90
    MATPLOTLIB_DPI: int = 120
    
    # PDF設定
    PDF_COMPRESSION_LEVEL: int = 6
    PDF_TIMEOUT_SECONDS: int = 300
    PDF_RENDER_DPI: int = 120
    
    # 詳細設定
    ENABLE_MEMORY_MONITORING: bool = True
    ENABLE_PERFORMANCE_LOGGING: bool = True
    CLEANUP_INTERVAL: int = 5  # タスク何個おきにクリーンアップするか
    
    def __post_init__(self):
        """初期化後の設定計算"""
        if self.MAX_WORKERS is None:
            self.MAX_WORKERS = min(self.CPU_CORES - 1, int(self.MEMORY_GB / 1.5), 8)
            self.MAX_WORKERS = max(1, self.MAX_WORKERS)
        
        if self.CHUNK_SIZE is None:
            self.CHUNK_SIZE = max(2, min(4, self.MAX_WORKERS // 2))
    
    @classmethod
    def create_default(cls) -> 'OptimizationConfig':
        """デフォルト設定でインスタンスを作成"""
        return cls()
    
    @classmethod
    def create_for_data_size(cls, data_size_mb: float) -> 'OptimizationConfig':
        """データサイズに応じた最適化設定を作成"""
        config = cls()
        
        if data_size_mb > 1000:  # 1GB以上
            config.MAX_WORKERS = min(config.MAX_WORKERS, 4)
            config.CHUNK_SIZE = 2
            config.MEMORY_LIMIT_PERCENT = 75
            config.GRAPH_THREAD_WORKERS = 3
        elif data_size_mb > 500:  # 500MB以上
            config.MAX_WORKERS = min(config.MAX_WORKERS, 6)
            config.CHUNK_SIZE = 3
            config.MEMORY_LIMIT_PERCENT = 80
        elif data_size_mb < 50:  # 50MB未満
            config.MAX_WORKERS = min(config.MAX_WORKERS, 12)
            config.CHUNK_SIZE = 6
            config.GRAPH_THREAD_WORKERS = 6
        
        return config
    
    def get_config_summary(self) -> Dict[str, Any]:
        """設定概要を取得"""
        return {
            'system': {
                'cpu_cores': self.CPU_CORES,
                'memory_gb': round(self.MEMORY_GB, 1),
                'available_memory_gb': round(psutil.virtual_memory().available / (1024**3), 1)
            },
            'optimization': {
                'max_workers': self.MAX_WORKERS,
                'chunk_size': self.CHUNK_SIZE,
                'memory_limit': self.MEMORY_LIMIT_PERCENT
            },
            'performance': {
                'graph_workers': self.GRAPH_THREAD_WORKERS,
                'matplotlib_dpi': self.MATPLOTLIB_DPI,
                'pdf_compression': self.PDF_COMPRESSION_LEVEL
            },
            'timeouts': {
                'graph_timeout': self.GRAPH_TIMEOUT_SECONDS,
                'pdf_timeout': self.PDF_TIMEOUT_SECONDS
            }
        }
    
    def estimate_performance(self, task_count: int, fast_mode: bool = True) -> Dict[str, Any]:
        """パフォーマンス予測を計算"""
        # 基本処理時間（秒/タスク）
        base_time_per_task = 1.0 if fast_mode else 2.0
        
        # ハイパー最適化での高速化率
        hyper_speedup = 3.0
        standard_speedup = 1.5
        
        # 並列効率
        parallel_efficiency = 0.85 if self.MAX_WORKERS <= 4 else 0.75
        
        # 時間計算
        hyper_time = (task_count * base_time_per_task / hyper_speedup) / (self.MAX_WORKERS * parallel_efficiency)
        standard_time = (task_count * base_time_per_task / standard_speedup) / (self.MAX_WORKERS * parallel_efficiency)
        sequential_time = task_count * base_time_per_task
        
        return {
            'task_count': task_count,
            'estimated_times': {
                'hyper_optimized': hyper_time,
                'standard_parallel': standard_time,
                'sequential': sequential_time
            },
            'speedup_ratios': {
                'hyper_vs_sequential': sequential_time / hyper_time if hyper_time > 0 else 1,
                'hyper_vs_standard': standard_time / hyper_time if hyper_time > 0 else 1,
                'standard_vs_sequential': sequential_time / standard_time if standard_time > 0 else 1
            },
            'throughput': {
                'hyper_tasks_per_sec': task_count / hyper_time if hyper_time > 0 else 0,
                'standard_tasks_per_sec': task_count / standard_time if standard_time > 0 else 0
            }
        }

class PerformanceMonitor:
    """パフォーマンス監視クラス"""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.completed_tasks = 0
        self.total_tasks = 0
        self.memory_usage_history = []
        self.cpu_usage_history = []
    
    def start_monitoring(self, total_tasks: int):
        """監視開始"""
        self.start_time = time.time()
        self.total_tasks = total_tasks
        self.completed_tasks = 0
        self.memory_usage_history = []
        self.cpu_usage_history = []
        
    def update_progress(self, completed_tasks: int):
        """進捗更新"""
        self.completed_tasks = completed_tasks
        
        # システム使用率を記録
        self.memory_usage_history.append(psutil.virtual_memory().percent)
        self.cpu_usage_history.append(psutil.cpu_percent())
        
        # 履歴サイズ制限
        if len(self.memory_usage_history) > 100:
            self.memory_usage_history = self.memory_usage_history[-50:]
            self.cpu_usage_history = self.cpu_usage_history[-50:]
    
    def finish_monitoring(self):
        """監視終了"""
        self.end_time = time.time()
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """パフォーマンス統計を取得"""
        if not self.start_time:
            return {}
        
        current_time = self.end_time or time.time()
        elapsed_time = current_time - self.start_time
        
        # 基本統計
        stats = {
            'elapsed_time': elapsed_time,
            'completed_tasks': self.completed_tasks,
            'total_tasks': self.total_tasks,
            'completion_rate': self.completed_tasks / self.total_tasks if self.total_tasks > 0 else 0,
            'tasks_per_second': self.completed_tasks / elapsed_time if elapsed_time > 0 else 0
        }
        
        # システム使用率統計
        if self.memory_usage_history:
            stats['memory_usage'] = {
                'current': self.memory_usage_history[-1],
                'avg': sum(self.memory_usage_history) / len(self.memory_usage_history),
                'max': max(self.memory_usage_history),
                'min': min(self.memory_usage_history)
            }
        
        if self.cpu_usage_history:
            stats['cpu_usage'] = {
                'current': self.cpu_usage_history[-1],
                'avg': sum(self.cpu_usage_history) / len(self.cpu_usage_history),
                'max': max(self.cpu_usage_history),
                'min': min(self.cpu_usage_history)
            }
        
        # 残り時間予測
        if self.completed_tasks > 0 and elapsed_time > 0:
            remaining_tasks = self.total_tasks - self.completed_tasks
            rate = self.completed_tasks / elapsed_time
            stats['estimated_remaining_time'] = remaining_tasks / rate if rate > 0 else 0
        
        return stats
    
    def get_real_time_info(self) -> Dict[str, Any]:
        """リアルタイム情報を取得"""
        if not self.start_time:
            return {}
        
        current_time = time.time()
        elapsed_time = current_time - self.start_time
        
        return {
            'elapsed_time': elapsed_time,
            'completed_tasks': self.completed_tasks,
            'total_tasks': self.total_tasks,
            'progress_percent': (self.completed_tasks / self.total_tasks * 100) if self.total_tasks > 0 else 0,
            'current_memory_usage': psutil.virtual_memory().percent,
            'current_cpu_usage': psutil.cpu_percent(),
            'tasks_per_second': self.completed_tasks / elapsed_time if elapsed_time > 0 else 0
        }

# グローバルインスタンス
default_config = OptimizationConfig.create_default()
performance_monitor = PerformanceMonitor()

# ユーティリティ関数
def get_system_recommendations() -> Dict[str, str]:
    """システム推奨事項を取得"""
    config = OptimizationConfig.create_default()
    recommendations = []
    
    if config.MEMORY_GB < 4:
        recommendations.append("メモリが不足しています。ハイパー最適化モードの使用は推奨されません。")
    elif config.MEMORY_GB < 8:
        recommendations.append("メモリが限られています。fast_modeの使用を推奨します。")
    else:
        recommendations.append("十分なメモリがあります。ハイパー最適化モードを安全に使用できます。")
    
    if config.CPU_CORES < 4:
        recommendations.append("CPUコアが少ないです。並列処理の効果は限定的です。")
    elif config.CPU_CORES >= 8:
        recommendations.append("十分なCPUコアがあります。並列処理で大幅な高速化が期待できます。")
    
    return {
        'system_info': config.get_config_summary(),
        'recommendations': recommendations
    }

def estimate_processing_time(task_count: int, use_hyper: bool = False, fast_mode: bool = True) -> str:
    """処理時間を見積もり"""
    config = OptimizationConfig.create_default()
    performance = config.estimate_performance(task_count, fast_mode)
    
    if use_hyper:
        estimated_time = performance['estimated_times']['hyper_optimized']
        mode = "ハイパー最適化"
    else:
        estimated_time = performance['estimated_times']['standard_parallel']
        mode = "標準並列"
    
    if estimated_time < 60:
        time_str = f"{estimated_time:.1f}秒"
    else:
        minutes = int(estimated_time // 60)
        seconds = int(estimated_time % 60)
        time_str = f"{minutes}分{seconds}秒"
    
    return f"{mode}: 約{time_str} ({performance['throughput']['hyper_tasks_per_sec' if use_hyper else 'standard_tasks_per_sec']:.1f}件/秒)"