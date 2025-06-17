# ===== 基本設定 =====
APP_VERSION = "1.1"  # バージョンアップ
APP_TITLE = "入退院分析ダッシュボード"
APP_ICON = "🏥"

# ===== デフォルト値 =====
DEFAULT_TOTAL_BEDS = 621
DEFAULT_OCCUPANCY_RATE = 0.9  # 90%
DEFAULT_AVG_LENGTH_OF_STAY = 12.0  # 日
DEFAULT_ADMISSION_FEE = 55000  # 円/日
DEFAULT_TARGET_PATIENT_DAYS = 17000  # 人日/月
DEFAULT_TARGET_ADMISSIONS = 1700  # 人/月

# ===== 除外設定 =====
EXCLUDED_WARDS = ['03B']  # 表示・分析から除外する病棟のリスト

# ===== UI設定 =====
CHART_HEIGHT = 400
FONT_SCALE = 1.0  # style.pyで使用

# ===== 期間設定 =====
PERIOD_OPTIONS = ["直近30日", "前月完了分", "今年度"]
DEFAULT_ANALYSIS_DAYS = 90  # 直近90日

# ===== カラーパレット =====
DASHBOARD_COLORS = {
    'primary_blue': '#3498db',
    'success_green': '#27ae60',
    'warning_orange': '#f39c12',
    'danger_red': '#e74c3c',
    'info_purple': '#9b59b6',
    'secondary_teal': '#16a085',
    'dark_gray': '#2c3e50',
    'light_gray': '#6c757d'
}

# ===== 数値フォーマット設定 =====
NUMBER_FORMAT = {
    'decimal_places': 1,
    'thousand_separator': ',',
    'currency_symbol': '円',
    'percentage_symbol': '%'
}

# ===== メッセージ設定 =====
MESSAGES = {
    'data_not_loaded': "⚠️ データが読み込まれていません。サイドバーから保存データを読み込むか、データ処理タブでファイルをアップロードしてください。",
    'data_processing_complete': "✅ データ処理が完了しました。",
    'insufficient_data': "📊 データを読み込み後に利用可能になります。サイドバーの「データ設定」をご確認ください。",
    'forecast_libs_missing': "📋 予測機能を使用するには必要なライブラリをインストールしてください。",
    'auto_load_success': "💾 保存されたデータを自動読み込みしました。",
    'data_save_success': "✅ データが保存されました。次回起動時に自動読み込みされます。",
    'data_save_error': "❌ データ保存に失敗しました。"
}

# ===== ファイル設定 =====
SUPPORTED_FILE_TYPES = ['.xlsx', '.xls', '.csv']
MAX_FILE_SIZE_MB = 100

# ===== データ永続化設定 =====
DATA_PERSISTENCE = {
    'auto_load_enabled': True,  # 自動読み込み機能
    'auto_save_on_process': True,  # 処理後自動保存
    'max_saved_versions': 5,  # 最大保存バージョン数（将来の拡張用）
    'compression_enabled': True,  # 圧縮保存（将来の拡張用）
}

# ===== 予測機能設定 =====
FORECAST_SETTINGS = {
    'max_forecast_days': 365,
    'min_historical_days': 30,
    'confidence_interval': 0.95
}

# ===== 病院設備設定 =====
HOSPITAL_SETTINGS = {
    'max_beds': 2000,
    'min_beds': 10,
    'max_occupancy_rate': 1.0,
    'min_occupancy_rate': 0.3,
    'max_avg_stay': 30.0,
    'min_avg_stay': 1.0
}

# ===== 分析設定 =====
ANALYSIS_SETTINGS = {
    'trend_min_periods': 12,  # トレンド分析に必要な最小期間数
    'seasonal_min_periods': 24,  # 季節性分析に必要な最小期間数
    'statistical_significance': 0.05  # 統計的有意水準
}

# ===== セッション管理設定 =====
SESSION_SETTINGS = {
    'persistent_keys': [  # 永続化するセッション状態のキー
        'total_beds',
        'bed_occupancy_rate', 
        'bed_occupancy_rate_percent',
        'avg_length_of_stay',
        'avg_admission_fee',
        'monthly_target_patient_days',
        'monthly_target_admissions'
    ],
    'auto_clear_on_new_data': False,  # 新データ時の自動クリア
}

PDF_DEBUG_MODE = False  # デバッグ出力の有効/無効
PDF_CACHE_SIZE_MB = 500  # キャッシュサイズ制限
PDF_MAX_WORKERS = 2  # 最大ワーカー数制限
PDF_DPI = 120  # PDF画像のDPI設定
PDF_FAST_MODE_DEFAULT = True  # 高速モードのデフォルト値