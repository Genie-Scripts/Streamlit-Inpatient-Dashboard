# responsive_style.py
"""
レスポンシブデザイン対応のスタイルモジュール
モバイル、タブレット、デスクトップに対応したスタイル定義
"""

def get_responsive_css():
    """レスポンシブ対応のCSSを返す"""
    return """
    <style>
    /* ベースとなるレスポンシブ設定 */
    @media (max-width: 768px) {
        /* モバイル向けスタイル */
        
        /* サイドバーの調整 */
        [data-testid="stSidebar"] {
            min-width: 100% !important;
            width: 100% !important;
            transform: translateX(-100%);
            transition: transform 0.3s ease;
        }
        
        [data-testid="stSidebar"][aria-expanded="true"] {
            transform: translateX(0);
        }
        
        /* メインコンテンツのパディング調整 */
        .main > div {
            padding: 1rem !important;
        }
        
        /* タブの横スクロール対応 */
        [data-testid="stTabs"] {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        
        [data-testid="stTabs"] > div:first-child {
            display: flex;
            flex-wrap: nowrap;
        }
        
        /* カラムレイアウトの縦並び対応 */
        [data-testid="column"] {
            width: 100% !important;
            flex: unset !important;
            min-width: unset !important;
        }
        
        /* メトリクスカードのレスポンシブ化 */
        [data-testid="metric-container"] {
            padding: 0.5rem !important;
        }
        
        [data-testid="metric-container"] > div > div {
            font-size: 0.9rem !important;
        }
        
        /* データフレームのスクロール対応 */
        [data-testid="stDataFrame"] {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        
        /* ボタンのタッチターゲット拡大 */
        .stButton > button {
            min-height: 44px !important;
            touch-action: manipulation;
            font-size: 1rem !important;
        }
        
        /* エキスパンダーのタッチ対応 */
        [data-testid="stExpander"] {
            touch-action: manipulation;
        }
        
        /* フォント調整 */
        h1 { font-size: 1.5rem !important; }
        h2 { font-size: 1.3rem !important; }
        h3 { font-size: 1.1rem !important; }
        
        /* グラフのレスポンシブ化 */
        [data-testid="stPlotlyChart"] {
            width: 100% !important;
            height: auto !important;
        }
        
        /* 入力フィールドの最適化 */
        input, select, textarea {
            font-size: 16px !important; /* iOS zoom防止 */
            touch-action: manipulation;
        }
        
        /* モバイル用フローティングメニューボタン */
        .mobile-menu-button {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 999;
            background-color: #007bff;
            color: white;
            border-radius: 50%;
            width: 56px;
            height: 56px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
            touch-action: manipulation;
        }
    }
    
    @media (min-width: 768px) and (max-width: 1024px) {
        /* タブレット向けスタイル */
        
        /* 2カラムレイアウトに調整 */
        [data-testid="column"]:nth-child(n+3) {
            margin-top: 1rem;
        }
        
        /* サイドバー幅調整 */
        [data-testid="stSidebar"] {
            min-width: 300px !important;
            max-width: 350px !important;
        }
        
        /* グラフサイズ調整 */
        [data-testid="stPlotlyChart"] {
            max-height: 400px !important;
        }
    }
    
    /* 共通のレスポンシブ設定 */
    
    /* スクロール性能の向上 */
    * {
        -webkit-overflow-scrolling: touch;
    }
    
    /* タッチデバイス用の調整 */
    @media (hover: none) and (pointer: coarse) {
        /* ホバー効果の無効化 */
        *:hover {
            opacity: 1 !important;
        }
        
        /* タップハイライトの調整 */
        * {
            -webkit-tap-highlight-color: rgba(0,0,0,0.1);
        }
    }
    
    /* 印刷対応 */
    @media print {
        [data-testid="stSidebar"] {
            display: none !important;
        }
        
        .main > div {
            padding: 0 !important;
        }
        
        [data-testid="stTabs"] {
            display: none !important;
        }
    }
    
    /* ダークモード対応 */
    @media (prefers-color-scheme: dark) {
        /* 必要に応じてダークモード用スタイルを追加 */
    }
    </style>
    """

def get_mobile_navigation_html():
    """モバイル用ナビゲーションのHTMLを返す"""
    return """
    <div class="mobile-menu-button" onclick="toggleSidebar()">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="3" y1="12" x2="21" y2="12"></line>
            <line x1="3" y1="6" x2="21" y2="6"></line>
            <line x1="3" y1="18" x2="21" y2="18"></line>
        </svg>
    </div>
    
    <script>
    function toggleSidebar() {
        const sidebar = document.querySelector('[data-testid="stSidebar"]');
        if (sidebar) {
            const isExpanded = sidebar.getAttribute('aria-expanded') === 'true';
            sidebar.setAttribute('aria-expanded', !isExpanded);
        }
    }
    
    // スワイプでサイドバー開閉
    let touchStartX = 0;
    let touchEndX = 0;
    
    document.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].screenX;
    });
    
    document.addEventListener('touchend', e => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    });
    
    function handleSwipe() {
        const swipeDistance = touchEndX - touchStartX;
        const sidebar = document.querySelector('[data-testid="stSidebar"]');
        
        if (Math.abs(swipeDistance) > 50) {
            if (swipeDistance > 0 && touchStartX < 50) {
                // 左端から右スワイプでサイドバーを開く
                sidebar?.setAttribute('aria-expanded', 'true');
            } else if (swipeDistance < 0 && sidebar?.getAttribute('aria-expanded') === 'true') {
                // 左スワイプでサイドバーを閉じる
                sidebar?.setAttribute('aria-expanded', 'false');
            }
        }
    }
    </script>
    """

def inject_responsive_css():
    """レスポンシブCSSを注入する"""
    import streamlit as st
    
    css = get_responsive_css()
    navigation = get_mobile_navigation_html()
    
    st.markdown(css, unsafe_allow_html=True)
    st.markdown(navigation, unsafe_allow_html=True)