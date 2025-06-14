import streamlit as st

def inject_global_css(font_scale=1.0):
    """
    アプリ全体のフォントサイズとフォントファミリ、テーブルや画像等の基本カスタムCSSを一括適用します。
    font_scale: 倍率（既定値1.5＝5割増し）
    """
    base_px = 16  # ブラウザ標準の基本フォントサイズ
    font_px = int(base_px * font_scale)
    header_px = int(font_px * 1.0)
    
    # ===== サイドバー目標値サマリー用のフォントサイズ設定 =====
    sidebar_target_label_px = int(font_px * 0.8)    # ラベル: 基本サイズの80% (12.8px)
    sidebar_target_value_px = int(font_px * 1.1)    # 値: 基本サイズの110% (17.6px)
    sidebar_target_delta_px = int(font_px * 0.7)    # デルタ: 基本サイズの70% (11.2px)
    
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"] {{
            font-size: {font_px}px !important;
            font-family: 'Arial', 'Noto Sans JP', sans-serif !important;
        }}
        .stApp {{
            font-size: {font_px}px !important;
        }}
        h1, h2, h3, h4, h5, h6 {{
            font-size: {header_px}px !important;
        }}
        /* DataFrameやTableウィジェットのフォントサイズ調整 */
        .stMarkdown p,
        .stDataFrame,
        .stTable,
        .stSelectbox,
        .stButton,
        .stTextInput,
        .stSlider,
        .stRadio,
        .stCheckbox,
        .stNumberInput,
        .stDateInput,
        .stTextArea,
        .stFileUploader,
        .stExpander,
        .stTabs,
        .stMetric {{
            font-size: {font_px}px !important;
        }}
        /* サイドバー等にも適用 */
        section[data-testid="stSidebar"] * {{
            font-size: {font_px}px !important;
        }}
        
        /* ===== サイドバー目標値サマリーの専用フォント設定 ===== */
        /* sidebar-target-summary-metricsクラス内のメトリクス */
        .sidebar-target-summary-metrics [data-testid="stMetricLabel"] {{
            font-size: {sidebar_target_label_px}px !important;
            font-weight: 600 !important;
            color: #262730 !important;
            margin-bottom: 2px !important;
            line-height: 1.2 !important;
        }}
        
        .sidebar-target-summary-metrics [data-testid="stMetricValue"] {{
            font-size: {sidebar_target_value_px}px !important;
            font-weight: 700 !important;
            color: #262730 !important;
            line-height: 1.3 !important;
            margin-bottom: 1px !important;
        }}
        
        .sidebar-target-summary-metrics [data-testid="stMetricDelta"] {{
            font-size: {sidebar_target_delta_px}px !important;
            font-weight: 500 !important;
            margin-top: 1px !important;
        }}
        
        /* より具体的なセレクターでの追加調整 */
        section[data-testid="stSidebar"] .sidebar-target-summary-metrics div[data-testid="stMetric"] label[data-testid="stMetricLabel"] {{
            font-size: {sidebar_target_label_px}px !important;
            font-weight: 600 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }}
        
        section[data-testid="stSidebar"] .sidebar-target-summary-metrics div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
            font-size: {sidebar_target_value_px}px !important;
            font-weight: 700 !important;
            line-height: 1.3 !important;
        }}
        
        section[data-testid="stSidebar"] .sidebar-target-summary-metrics div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {{
            font-size: {sidebar_target_delta_px}px !important;
            font-weight: 500 !important;
        }}
        
        /* ブロックコンテナ余白調整（必要に応じて） */
        .block-container {{
            max-width: 100% !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }}
        /* 独自HTMLテーブル（styled-tableクラス利用時） */
        .styled-table {{
            font-size: {2*font_px}px;
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }}
        .styled-table th, .styled-table td {{
            padding: 14px 24px;
            border: 1px solid #ccc;
            text-align: center;
        }}
        /* DataFrame幅を100%に */
        .stDataFrame {{
            width: 100%;
        }}
        /* 画像表示最大幅調整 */
        .stImage > img {{
            max-width: 100%;
            height: auto;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

# def apply_custom_style():
    # """アプリケーションのカスタムCSSスタイルを適用する"""
    # st.markdown("""
        # <style>
            # html, body {
                # font-family: 'Arial', 'Noto Sans JP', sans-serif !important;
            # }

            # .block-container {
                # max-width: 100% !important;
                # padding-left: 2rem !important;
                # padding-right: 2rem !important;
            # }

            # .styled-table {
                # font-size: 32px;
                # width: 100%;
                # border-collapse: collapse;
                # margin-top: 1rem;
            # }

            # .styled-table th, .styled-table td {
                # padding: 14px 24px;
                # border: 1px solid #ccc;
                # text-align: center;
            # }
            
            # .stDataFrame {
                # width: 100%;
            # }
            
            # /* グラフ表示の調整 */
            # .stImage > img {
                # max-width: 100%;
                # height: auto;
            # }
        # </style>
    # """, unsafe_allow_html=True)

# ダークモード関連の関数は削除しました

def inject_department_performance_css():
    """
    診療科別パフォーマンスダッシュボード用CSS
    department_performance_tab.py から呼び出される専用スタイル
    """
    st.markdown("""
    <style>
    /* ===== 診療科別パフォーマンスダッシュボード専用CSS ===== */
    
    /* 基本カードスタイル */
    .dept-performance-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
        border-radius: 12px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.08);
        padding: 20px;
        margin: 15px;
        border-left: 5px solid #007bff;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }

    .dept-performance-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0,0,0,0.12);
    }

    .dept-performance-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, #007bff, #28a745, #ffc107);
    }

    /* 達成状態による色分け */
    .dept-card-excellent {
        border-left-color: #28a745;
        background: linear-gradient(135deg, #f8fff9 0%, #e8f5e8 100%);
    }

    .dept-card-good {
        border-left-color: #17a2b8;
        background: linear-gradient(135deg, #f0fcff 0%, #e1f7fa 100%);
    }

    .dept-card-warning {
        border-left-color: #ffc107;
        background: linear-gradient(135deg, #fffdf0 0%, #fff3cd 100%);
    }

    .dept-card-danger {
        border-left-color: #dc3545;
        background: linear-gradient(135deg, #fff5f5 0%, #f8d7da 100%);
    }

    /* メトリクス表示スタイル */
    .metric-value {
        font-size: 2.2em;
        font-weight: 700;
        color: #2c3e50;
        line-height: 1.2;
        margin: 8px 0;
    }

    .metric-label {
        font-size: 0.9em;
        font-weight: 600;
        color: #495057;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .metric-detail {
        font-size: 0.85em;
        color: #6c757d;
        margin: 4px 0;
    }

    /* 達成率バッジスタイル */
    .achievement-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85em;
        font-weight: 600;
        margin-top: 8px;
        text-align: center;
        min-width: 80px;
    }

    .achievement-excellent {
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }

    .achievement-good {
        background-color: #d1ecf1;
        color: #0c5460;
        border: 1px solid #bee5eb;
    }

    .achievement-warning {
        background-color: #fff3cd;
        color: #856404;
        border: 1px solid #ffeaa7;
    }

    .achievement-danger {
        background-color: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
    }

    /* レスポンシブグリッドレイアウト */
    .dept-performance-grid {
        display: grid;
        gap: 20px;
        margin: 20px 0;
    }

    .grid-1-col { grid-template-columns: 1fr; }
    .grid-2-col { grid-template-columns: repeat(2, 1fr); }
    .grid-3-col { grid-template-columns: repeat(3, 1fr); }
    .grid-4-col { grid-template-columns: repeat(4, 1fr); }

    /* レスポンシブ対応 */
    @media (max-width: 1200px) {
        .grid-4-col { grid-template-columns: repeat(3, 1fr); }
    }

    @media (max-width: 900px) {
        .grid-3-col, .grid-4-col { grid-template-columns: repeat(2, 1fr); }
    }

    @media (max-width: 600px) {
        .grid-2-col, .grid-3-col, .grid-4-col { grid-template-columns: 1fr; }
        .dept-performance-card { 
            margin: 10px 5px; 
            padding: 15px; 
        }
        .metric-value { 
            font-size: 1.8em; 
        }
    }

    /* サマリーカードスタイル */
    .summary-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0 20px 0;
        box-shadow: 0 4px 16px rgba(102, 126, 234, 0.3);
    }

    .summary-card .metric-value {
        color: white;
        text-shadow: 0 1px 2px rgba(0,0,0,0.2);
    }

    .summary-card .metric-label {
        color: rgba(255,255,255,0.9);
    }

    /* アニメーション効果 */
    @keyframes slideInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .dept-performance-card {
        animation: slideInUp 0.5s ease-out;
    }

    /* ツールチップスタイル */
    .tooltip {
        position: relative;
        cursor: help;
    }

    .tooltip::after {
        content: attr(data-tooltip);
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        background-color: #333;
        color: white;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 0.8em;
        white-space: nowrap;
        opacity: 0;
        visibility: hidden;
        transition: all 0.3s ease;
        z-index: 1000;
    }

    .tooltip:hover::after {
        opacity: 1;
        visibility: visible;
    }

    /* 印刷用スタイル */
    @media print {
        .dept-performance-card {
            break-inside: avoid;
            box-shadow: none;
            border: 1px solid #ddd;
            margin: 10px 0;
        }
        
        .dept-performance-grid {
            grid-template-columns: repeat(2, 1fr) !important;
        }
        
        .dept-performance-card::before {
            display: none;
        }
    }
    
    /* ダークモード対応（オプション） */
    @media (prefers-color-scheme: dark) {
        .dept-performance-card {
            background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%);
            color: #e2e8f0;
        }
        
        .metric-value {
            color: #e2e8f0;
        }
        
        .metric-label {
            color: #a0aec0;
        }
        
        .metric-detail {
            color: #718096;
        }
    }
    </style>
    """, unsafe_allow_html=True)

def inject_enhanced_global_css(font_scale=1.0):
    """
    既存のグローバルCSSを拡張した版
    既存の inject_global_css を置き換える場合に使用
    """
    # 既存のグローバルCSS
    inject_global_css(font_scale)
    
    # 診療科別パフォーマンス用CSS
    inject_department_performance_css()

# ============================================
# ユーティリティ関数（オプション）
# ============================================

def get_achievement_color_class(achievement_rate):
    """
    達成率に基づくCSSクラス名を返す
    
    Args:
        achievement_rate: 達成率（％）
    
    Returns:
        str: CSSクラス名
    """
    if achievement_rate is None:
        return "achievement-good"
    elif achievement_rate >= 100:
        return "achievement-excellent"
    elif achievement_rate >= 95:
        return "achievement-good"
    elif achievement_rate >= 85:
        return "achievement-warning"
    else:
        return "achievement-danger"

def get_card_class(census_achievement, admissions_achievement):
    """
    KPI達成率に基づくカードCSSクラス名を返す
    
    Args:
        census_achievement: 日平均在院患者数達成率
        admissions_achievement: 週新入院患者数達成率
    
    Returns:
        str: カードCSSクラス名
    """
    census_rate = census_achievement or 0
    admissions_rate = admissions_achievement or 0
    
    if census_rate >= 100 and admissions_rate >= 100:
        return "dept-card-excellent"
    elif census_rate >= 95 or admissions_rate >= 95:
        return "dept-card-good"
    elif census_rate >= 85 or admissions_rate >= 85:
        return "dept-card-warning"
    else:
        return "dept-card-danger"