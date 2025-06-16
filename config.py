# config.py - アプリケーション設定値の管理（更新版）

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
    # デバッグモード切り替え（右上に小さく配置）
    # ===========================================
    col_main, col_debug = st.columns([4, 1])
    with col_debug:
        debug_mode = st.checkbox(
            "デバッグ情報", 
            value=False, 
            key="dashboard_debug_mode",
            help="詳細な処理情報を表示"
        )
    
    # ===========================================
    # KPIカード表示（メイン）
    # ===========================================
    if display_kpi_cards_only:
        display_kpi_cards_only(
            df_for_dashboard, start_date_ts, end_date_ts, 
            total_beds, target_occupancy_rate_percent,
            show_debug=debug_mode  # デバッグモードの制御
        )
    else:
        st.error("KPIカード表示機能が利用できません。dashboard_overview_tab.pyを確認してください。")
    
    # ===========================================
    # 簡潔な分析条件表示（デバッグモード無効時のみ）
    # ===========================================
    if not debug_mode:
        st.markdown("---")
        
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
        
        st.caption("※ 期間変更はサイドバーの「分析フィルター」で行えます")