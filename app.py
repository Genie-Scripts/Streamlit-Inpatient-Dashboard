import streamlit as st
import pandas as pd
import numpy as np
import datetime
import traceback

# PWA設定
PWA_CONFIG = {
    "name": "入退院分析ダッシュボード",
    "short_name": "入退院分析",
    "description": "医療機関向け入退院患者分析PWAダッシュボード",
    "theme_color": "#007bff",
    "background_color": "#ffffff",
    "display": "standalone",
    "scope": "/",
    "start_url": "/",
    "orientation": "portrait-primary"
}

# ページ設定（PWA対応）
st.set_page_config(
    page_title=PWA_CONFIG["name"],
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': f"# {PWA_CONFIG['name']}\n医療現場向けPWAダッシュボード"
    }
)

import json
import os
from pathlib import Path

# ===== 修正: 冒頭でimport実行 =====
try:
    from config import (
        create_sidebar, 
        create_management_dashboard_tab,
        create_data_processing_tab,
        create_department_performance_tab,
        create_ward_performance_tab
    )
    CONFIG_IMPORTED = True
except ImportError as e:
    st.warning(f"設定モジュール読み込みエラー: {e}")
    CONFIG_IMPORTED = False
    FORECAST_AVAILABLE = False


# CSS & PWA Assets 注入
def inject_pwa_assets():
    """PWA必須アセットとCSS注入"""
    
    # PWA Manifest生成
    manifest = {
        "name": PWA_CONFIG["name"],
        "short_name": PWA_CONFIG["short_name"],
        "description": PWA_CONFIG["description"],
        "theme_color": PWA_CONFIG["theme_color"],
        "background_color": PWA_CONFIG["background_color"],
        "display": PWA_CONFIG["display"],
        "scope": PWA_CONFIG["scope"],
        "start_url": PWA_CONFIG["start_url"],
        "orientation": PWA_CONFIG["orientation"],
        "icons": [
            {
                "src": "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNTEyIiBoZWlnaHQ9IjUxMiIgdmlld0JveD0iMCAwIDUxMiA1MTIiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSI1MTIiIGhlaWdodD0iNTEyIiBmaWxsPSIjMDA3YmZmIi8+Cjx0ZXh0IHg9IjI1NiIgeT0iMjgwIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMjAwIiBmaWxsPSJ3aGl0ZSIgdGV4dC1hbmNob3I9Im1pZGRsZSI+8J+PpTwvdGV4dD4KPC9zdmc+",
                "sizes": "512x512",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            }
        ]
    }
    
    # HTML Head要素
    st.markdown(f"""
    <script>
        // PWA Manifest 動的挿入
        const manifestBlob = new Blob([JSON.stringify({json.dumps(manifest)})], {{type: 'application/json'}});
        const manifestURL = URL.createObjectURL(manifestBlob);
        const link = document.createElement('link');
        link.rel = 'manifest';
        link.href = manifestURL;
        document.head.appendChild(link);
        
        // メタタグ設定
        const viewport = document.querySelector('meta[name="viewport"]');
        if (viewport) {{
            viewport.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover';
        }}
        
        // PWA用メタタグ追加
        const metaTags = [
            {{'name': 'theme-color', 'content': '{PWA_CONFIG["theme_color"]}'}},
            {{'name': 'apple-mobile-web-app-capable', 'content': 'yes'}},
            {{'name': 'apple-mobile-web-app-status-bar-style', 'content': 'black-translucent'}},
            {{'name': 'apple-mobile-web-app-title', 'content': '{PWA_CONFIG["short_name"]}'}},
            {{'name': 'mobile-web-app-capable', 'content': 'yes'}}
        ];
        
        metaTags.forEach(tag => {{
            const meta = document.createElement('meta');
            Object.keys(tag).forEach(key => meta.setAttribute(key, tag[key]));
            document.head.appendChild(meta);
        }});
        
        // Service Worker 登録準備
        if ('serviceWorker' in navigator) {{
            console.log('Service Worker サポート確認済み');
        }}
    </script>
    """, unsafe_allow_html=True)
    
    # モバイルファーストCSS
    st.markdown("""
    <style>
    /* =========================== */
    /* PWA モバイルファースト CSS */
    /* =========================== */
    
    /* 基本設定 */
    :root {
        --primary-color: #007bff;
        --secondary-color: #6c757d;
        --success-color: #28a745;
        --warning-color: #ffc107;
        --danger-color: #dc3545;
        --info-color: #17a2b8;
        --light-color: #f8f9fa;
        --dark-color: #343a40;
        
        --border-radius: 12px;
        --box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        --transition: all 0.3s ease;
        
        --mobile-header-height: 60px;
        --mobile-nav-height: 70px;
        --mobile-spacing: 1rem;
    }
    
    /* 全体レイアウト調整 */
    .main > div {
        padding: 0.5rem;
        max-width: 100%;
    }
    
    /* ヘッダー */
    .mobile-header {
        position: sticky;
        top: 0;
        z-index: 1000;
        background: linear-gradient(135deg, var(--primary-color), #0056b3);
        color: white;
        padding: 1rem;
        text-align: center;
        box-shadow: var(--box-shadow);
        border-radius: 0 0 var(--border-radius) var(--border-radius);
        margin-bottom: var(--mobile-spacing);
    }
    
    .mobile-header h1 {
        margin: 0;
        font-size: 1.5rem;
        font-weight: 600;
    }
    
    .mobile-header .subtitle {
        font-size: 0.875rem;
        opacity: 0.9;
        margin-top: 0.25rem;
    }
    
    /* メインナビゲーション */
    .mobile-main-nav {
        position: sticky;
        top: var(--mobile-header-height);
        z-index: 999;
        background: white;
        padding: 0.75rem;
        border-radius: var(--border-radius);
        box-shadow: var(--box-shadow);
        margin-bottom: var(--mobile-spacing);
    }
    
    .nav-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
        gap: 0.5rem;
        justify-content: center;
    }
    
    .nav-button {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 1rem 0.5rem;
        background: var(--light-color);
        border: 2px solid transparent;
        border-radius: var(--border-radius);
        color: var(--dark-color);
        text-decoration: none;
        font-size: 0.875rem;
        font-weight: 500;
        min-height: 80px;
        transition: var(--transition);
        cursor: pointer;
        position: relative;
        overflow: hidden;
    }
    
    .nav-button:hover {
        transform: translateY(-2px);
        box-shadow: var(--box-shadow);
    }
    
    .nav-button.active {
        background: var(--primary-color);
        color: white;
        border-color: var(--primary-color);
    }
    
    /* メトリクスカード */
    .metric-card-mobile {
        background: white;
        border-radius: var(--border-radius);
        padding: 1.25rem;
        margin: 0.75rem 0;
        box-shadow: var(--box-shadow);
        border-left: 4px solid var(--primary-color);
        transition: var(--transition);
        position: relative;
        overflow: hidden;
    }
    
    .metric-card-mobile:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.15);
    }
    
    .metric-title {
        font-size: 0.875rem;
        color: var(--secondary-color);
        margin-bottom: 0.5rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: var(--dark-color);
        margin-bottom: 0.25rem;
        line-height: 1;
    }
    
    .metric-delta {
        font-size: 0.875rem;
        font-weight: 500;
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
    }
    
    .metric-delta.success { color: var(--success-color); }
    .metric-delta.warning { color: var(--warning-color); }
    .metric-delta.error { color: var(--danger-color); }
    .metric-delta.info { color: var(--info-color); }
    
    /* ボタン強化 */
    .stButton > button {
        background: linear-gradient(135deg, var(--primary-color), #0056b3) !important;
        color: white !important;
        border: none !important;
        border-radius: var(--border-radius) !important;
        padding: 0.75rem 1.5rem !important;
        font-size: 1rem !important;
        font-weight: 500 !important;
        min-height: 48px !important;
        width: 100% !important;
        transition: var(--transition) !important;
        box-shadow: var(--box-shadow) !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 20px rgba(0,123,255,0.3) !important;
    }
    
    /* アラート */
    .alert-mobile {
        padding: 1rem;
        border-radius: var(--border-radius);
        margin: 1rem 0;
        border-left: 4px solid;
        animation: slideInRight 0.3s ease;
    }
    
    .alert-mobile.success {
        background: #d4edda;
        border-color: var(--success-color);
        color: #155724;
    }
    
    .alert-mobile.warning {
        background: #fff3cd;
        border-color: var(--warning-color);
        color: #856404;
    }
    
    .alert-mobile.error {
        background: #f8d7da;
        border-color: var(--danger-color);
        color: #721c24;
    }
    
    @keyframes slideInRight {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    
    /* タブレット対応 */
    @media (min-width: 768px) and (max-width: 1024px) {
        .main > div {
            padding: 1rem;
        }
        
        .nav-grid {
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
        }
        
        .metric-value {
            font-size: 2.5rem;
        }
    }
    
    /* デスクトップ対応 */
    @media (min-width: 1025px) {
        .mobile-header {
            position: relative;
        }
        
        .mobile-main-nav {
            position: relative;
        }
        
        .nav-grid {
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            max-width: 1200px;
            margin: 0 auto;
        }
    }
    </style>
    """, unsafe_allow_html=True)

# モバイル検出とページ状態管理
class MobileAppManager:
    """モバイルアプリケーション管理クラス"""
    
    def __init__(self):
        self.init_session_state()
        self.is_mobile = self.detect_mobile_mode()
        
    def init_session_state(self):
        """セッション状態初期化"""
        defaults = {
            'current_page': 'home',
            'mobile_mode': False,
            'data_processed': False,
            'df': None,
            'last_activity': datetime.datetime.now(),
            'app_installed': False,
            'notifications_enabled': False
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    def detect_mobile_mode(self) -> bool:
        """モバイルモード検出"""
        return st.sidebar.checkbox(
            "📱 モバイルモード", 
            value=st.session_state.get('mobile_mode', False),
            key="global_mobile_mode",
            help="モバイル最適化UIに切り替え"
        )
    
    def update_activity(self):
        """ユーザー活動更新"""
        st.session_state.last_activity = datetime.datetime.now()
    
    def render_mobile_header(self):
        """モバイルヘッダー表示"""
        if not self.is_mobile:
            return
            
        current_time = datetime.datetime.now().strftime("%H:%M")
        data_status = "🟢 データ読み込み済み" if st.session_state.get('data_processed') else "🔴 データ未読み込み"
        
        st.markdown(f"""
        <div class="mobile-header">
            <h1>🏥 入退院分析</h1>
            <div class="subtitle">
                {current_time} | {data_status}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    def render_main_navigation(self) -> str:
        """メインナビゲーション表示"""
        
        pages = {
            'home': {'icon': '🏠', 'label': 'ホーム', 'desc': 'ダッシュボード概要'},
            'kpi': {'icon': '📊', 'label': 'KPI', 'desc': '主要指標'},
            'input': {'icon': '📥', 'label': '入力', 'desc': 'データ管理'},
            'dept': {'icon': '🏥', 'label': '診療科', 'desc': '科別分析'},
            'ward': {'icon': '🏨', 'label': '病棟', 'desc': '病棟別分析'},
            'analysis': {'icon': '📈', 'label': '分析', 'desc': '詳細分析メニュー'}
        }
        
        if self.is_mobile:
            # モバイル用ナビゲーション
            st.markdown('<div class="mobile-main-nav">', unsafe_allow_html=True)
            st.markdown('<div class="nav-grid">', unsafe_allow_html=True)
            
            nav_cols = st.columns(3)
            for i, (page_key, config) in enumerate(pages.items()):
                with nav_cols[i % 3]:
                    if st.button(
                        f"{config['icon']}\n{config['label']}", 
                        key=f"nav_{page_key}",
                        use_container_width=True,
                        help=config['desc']
                    ):
                        st.session_state.current_page = page_key
                        self.update_activity()
                        st.rerun()
            
            st.markdown('</div></div>', unsafe_allow_html=True)
            
        else:
            # デスクトップ用タブナビゲーション
            tab_names = [f"{config['icon']} {config['label']}" for config in pages.values()]
            tabs = st.tabs(tab_names)
            
            # タブクリック検出のための一時的な実装
            current_tab = st.session_state.get('current_tab', 0)
            page_keys = list(pages.keys())
            if current_tab < len(page_keys):
                st.session_state.current_page = page_keys[current_tab]
            
        return st.session_state.current_page
    
    def render_page_content(self, page: str):
        """ページコンテンツ表示"""
        
        # データ処理状況確認
        data_available = st.session_state.get('data_processed', False)
        
        if page == 'home':
            self.render_home_page()
        elif page == 'kpi':
            if data_available and CONFIG_IMPORTED:
                try:
                    create_management_dashboard_tab()
                except Exception as e:
                    st.error(f"KPI表示エラー: {str(e)}")
            else:
                self.render_no_data_message("KPI表示")
        elif page == 'input':
            if CONFIG_IMPORTED:
                try:
                    create_data_processing_tab()
                except Exception as e:
                    st.error(f"データ入力エラー: {str(e)}")
            else:
                st.info("データ入力機能を読み込み中...")
        elif page == 'dept':
            if data_available and CONFIG_IMPORTED:
                try:
                    create_department_performance_tab()
                except Exception as e:
                    st.error(f"診療科別分析エラー: {str(e)}")
            else:
                self.render_no_data_message("診療科別分析")
        elif page == 'ward':
            if data_available and CONFIG_IMPORTED:
                try:
                    create_ward_performance_tab()
                except Exception as e:
                    st.error(f"病棟別分析エラー: {str(e)}")
            else:
                self.render_no_data_message("病棟別分析")
        elif page == 'analysis':
            if data_available:
                self.render_analysis_menu()
            else:
                self.render_no_data_message("詳細分析")
        else:
            st.error(f"ページ '{page}' が見つかりません。")
    
    def render_home_page(self):
        """ホームページ表示"""
        if self.is_mobile:
            st.markdown("### 🏠 ダッシュボード概要")
            
            # クイックステータス
            self.render_quick_status()
            
            # 重要アラート
            self.render_alerts()
            
            # クイックアクション
            self.render_quick_actions()
            
        else:
            # デスクトップ版は従来通り
            try:
                if CONFIG_IMPORTED:
                    create_management_dashboard_tab()
                else:
                    self.render_quick_status()
                    self.render_quick_actions()
            except Exception as e:
                st.error(f"ダッシュボード表示エラー: {str(e)}")
                self.render_quick_status()
    
    def render_quick_status(self):
        """クイックステータス表示"""
        
        if st.session_state.get('data_processed'):
            # 実際のデータから計算
            df = st.session_state.get('df')
            if df is not None and not df.empty:
                # 簡易KPI計算
                total_records = len(df)
                latest_date = df['日付'].max() if '日付' in df.columns else "不明"
                
                metrics = [
                    {"title": "データ状況", "value": "✅ 正常", "delta": f"{total_records:,}件", "type": "success"},
                    {"title": "最新データ", "value": latest_date.strftime("%m/%d") if latest_date != "不明" else "不明", "delta": "", "type": "info"},
                    {"title": "システム", "value": "🟢 稼働中", "delta": "PWA対応", "type": "success"}
                ]
            else:
                metrics = [{"title": "データ状況", "value": "❌ エラー", "delta": "", "type": "error"}]
        else:
            metrics = [
                {"title": "データ状況", "value": "⚠️ 未読み込み", "delta": "", "type": "warning"},
                {"title": "次のアクション", "value": "データ入力", "delta": "📥 タブへ", "type": "info"}
            ]
        
        for metric in metrics:
            delta_class = f"metric-delta {metric['type']}"
            st.markdown(f"""
            <div class="metric-card-mobile">
                <div class="metric-title">{metric['title']}</div>
                <div class="metric-value">{metric['value']}</div>
                <div class="{delta_class}">{metric['delta']}</div>
            </div>
            """, unsafe_allow_html=True)
    
    def render_alerts(self):
        """アラート表示"""
        st.markdown("### 🚨 重要な通知")
        
        # 実際のアラートロジック
        alerts = []
        
        if not st.session_state.get('data_processed'):
            alerts.append({
                "type": "warning",
                "title": "データ未読み込み",
                "message": "分析を開始するためにデータを読み込んでください。"
            })
        
        if not CONFIG_IMPORTED:
            alerts.append({
                "type": "error",
                "title": "モジュール読み込みエラー",
                "message": "一部機能が利用できません。設定を確認してください。"
            })
        
        if not alerts:
            alerts.append({
                "type": "success", 
                "title": "システム正常",
                "message": "すべての機能が正常に動作しています。"
            })
        
        for alert in alerts:
            st.markdown(f"""
            <div class="alert-mobile {alert['type']}">
                <strong>{alert['title']}</strong><br>
                {alert['message']}
            </div>
            """, unsafe_allow_html=True)
    
    def render_quick_actions(self):
        """クイックアクション表示"""
        st.markdown("### 🚀 クイックアクション")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 KPI確認", key="quick_kpi", use_container_width=True):
                st.session_state.current_page = 'kpi'
                st.rerun()
        
        with col2:
            if st.button("📥 データ入力", key="quick_input", use_container_width=True):
                st.session_state.current_page = 'input'
                st.rerun()
        
        # 保存データがある場合の読み込みボタン
        if not st.session_state.get('data_processed'):
            try:
                from data_persistence import get_data_info
                data_info = get_data_info()
                if data_info:
                    st.markdown("### 💾 保存データ")
                    if st.button("🔄 保存データを読み込む", key="load_saved", use_container_width=True):
                        self.load_saved_data()
            except ImportError:
                pass
    
    def render_no_data_message(self, feature_name: str):
        """データなしメッセージ表示"""
        st.warning(f"📊 {feature_name}を利用するにはデータを読み込んでください。")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 データ入力へ", key=f"goto_input_{feature_name}", use_container_width=True):
                st.session_state.current_page = 'input'
                st.rerun()
        
        with col2:
            if st.button("🔄 保存データ読み込み", key=f"load_data_{feature_name}", use_container_width=True):
                self.load_saved_data()
    
    def render_analysis_menu(self):
        """分析メニューページ"""
        st.markdown("### 📈 詳細分析メニュー")
        
        analysis_options = [
            {"title": "🗓️ 平均在院日数分析", "page": "alos", "desc": "在院日数のトレンドと要因分析"},
            {"title": "📅 曜日別入退院分析", "page": "dow", "desc": "曜日パターンの詳細分析"},
            {"title": "🔍 個別患者分析", "page": "individual", "desc": "個別ケースの深堀り分析"}
        ]
        
        if FORECAST_AVAILABLE:
            analysis_options.append({"title": "🔮 予測分析", "page": "forecast", "desc": "将来トレンドの予測モデル"})
        
        for option in analysis_options:
            st.markdown(f"""
            <div class="metric-card-mobile">
                <div class="metric-title">{option['title']}</div>
                <div style="font-size: 0.9rem; color: #6c757d; margin-top: 0.5rem;">
                    {option['desc']}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"▶️ {option['title']}", key=f"analysis_{option['page']}", use_container_width=True):
                st.session_state.current_page = option['page']
                st.rerun()
    
    def load_saved_data(self):
        """保存データ読み込み"""
        try:
            from data_persistence import load_data_from_file
            from utils import initialize_all_mappings
            from unified_filters import initialize_unified_filters
            
            with st.spinner("データを読み込み中..."):
                df_loaded, target_data_loaded, metadata_loaded = load_data_from_file()
                
                if df_loaded is not None:
                    st.session_state['df'] = df_loaded
                    st.session_state['target_data'] = target_data_loaded
                    st.session_state['data_processed'] = True
                    st.session_state['data_source'] = 'saved_data'
                    st.session_state['data_metadata'] = metadata_loaded
                    
                    if '日付' in df_loaded.columns and not df_loaded['日付'].empty:
                        latest_date = df_loaded['日付'].max()
                        st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                    
                    initialize_all_mappings(st.session_state.df, st.session_state.target_data)
                    initialize_unified_filters(st.session_state.df)
                    
                    st.success("✅ データ読み込み完了!")
                    st.rerun()
                else:
                    st.error("❌ データ読み込みに失敗しました")
        except ImportError:
            st.error("データ読み込み機能が利用できません")
        except Exception as e:
            st.error(f"読み込みエラー: {str(e)}")

# メイン実行関数
def main():
    """メイン関数（PWA対応版）"""
    
    # PWA assets注入
    inject_pwa_assets()
    
    # モバイルアプリマネージャー初期化
    app_manager = MobileAppManager()
    
    # 必要なモジュールの動的インポート（修正版）
    try:
        from data_persistence import auto_load_data
        from utils import initialize_all_mappings
        from unified_filters import initialize_unified_filters
        
        # 自動データ読み込み
        auto_loaded = auto_load_data()
        if auto_loaded and st.session_state.get('df') is not None:
            st.sidebar.success("✅ 保存データを自動読み込みしました")
            if 'target_data' not in st.session_state:
                st.session_state.target_data = None
            initialize_all_mappings(st.session_state.df, st.session_state.target_data)
            if not st.session_state.df.empty:
                initialize_unified_filters(st.session_state.df)
            
    except ImportError as e:
        st.sidebar.warning(f"一部機能が利用できません: {e}")
    except Exception as e:
        st.sidebar.error(f"初期化エラー: {e}")
    
    # メインUI表示
    app_manager.render_mobile_header()
    current_page = app_manager.render_main_navigation()
    
    # サイドバー（設定とフィルター）
    if not app_manager.is_mobile or st.sidebar.checkbox("⚙️ 詳細設定表示", key="show_sidebar"):
        try:
            if CONFIG_IMPORTED:
                create_sidebar()
            else:
                st.sidebar.info("設定機能を読み込み中...")
        except Exception as e:
            st.sidebar.error(f"サイドバーエラー: {str(e)}")
    
    # ページコンテンツ表示
    app_manager.render_page_content(current_page)
    
    # フッター（デスクトップのみ）
    if not app_manager.is_mobile:
        st.markdown("---")
        st.markdown(
            f'<div style="text-align: center; color: #666666; font-size: 0.8rem;">'
            f'🏥 {PWA_CONFIG["name"]} | PWA対応 | {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
            f'</div>',
            unsafe_allow_html=True
        )

if __name__ == "__main__":
    main()