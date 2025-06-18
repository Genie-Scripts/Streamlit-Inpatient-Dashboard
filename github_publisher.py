import os
import json
import requests
import base64
from datetime import datetime
import streamlit as st
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class GitHubPublisher:
    def __init__(self, repo_owner, repo_name, token, branch="main"):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.token = token
        self.branch = branch
        self.base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        
    def upload_html_file(self, html_content, file_path, commit_message=None):
        """HTMLファイルをGitHubにアップロード"""
        try:
            file_url = f"{self.base_url}/contents/{file_path}"
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            response = requests.get(file_url, headers=headers)
            sha = None
            if response.status_code == 200:
                sha = response.json()["sha"]
            
            content_encoded = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
            
            if not commit_message:
                commit_message = f"Update dashboard: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            data = {
                "message": commit_message,
                "content": content_encoded,
                "branch": self.branch
            }
            
            if sha:
                data["sha"] = sha
            
            response = requests.put(file_url, json=data, headers=headers)
            
            if response.status_code in [200, 201]:
                return True, f"Successfully uploaded: {file_path}"
            else:
                return False, f"Upload failed: {response.status_code} - {response.text}"
                
        except Exception as e:
            return False, f"Error uploading file: {str(e)}"
    
    def create_index_page(self, dashboards_info, layout_style="default", content_config=None):
        """ダッシュボード一覧のインデックスページを生成"""
        
        if content_config is None:
            content_config = ContentCustomizer().default_content
            
        if layout_style == "minimal":
            return self._create_minimal_layout(dashboards_info, content_config)
        elif layout_style == "corporate":
            return self._create_corporate_layout(dashboards_info, content_config)
        elif layout_style == "mobile_first":
            return self._create_mobile_first_layout(dashboards_info, content_config)
        else:
            return self._create_default_layout(dashboards_info, content_config)

    def _create_default_layout(self, dashboards_info, content_config):
        """デフォルトレイアウト"""
        dashboard_links = ""
        button_text = content_config.get('dashboard_button_text', 'ダッシュボードを開く')
        
        for dashboard in dashboards_info:
            if 'department' in dashboard.get('file', '').lower() or '診療科' in dashboard.get('title', ''):
                description = content_config.get('department_dashboard_description', dashboard.get('description', ''))
            else:
                description = content_config.get('ward_dashboard_description', dashboard.get('description', ''))
                
            update_time = dashboard.get('update_time', '不明')
            dashboard_links += f"""
            <div class="dashboard-card">
                <h3>{dashboard['title']}</h3>
                <p>{description}</p>
                <p class="update-time">最終更新: {update_time}</p>
                <a href="{dashboard['file']}" class="dashboard-link">{button_text}</a>
            </div>
            """
        
        # 機能セクション
        features_section = ""
        if content_config.get('show_features', True):
            features_html = ""
            for feature in content_config.get('features', []):
                features_html += f"""
                <div class="feature">
                    <div class="feature-icon">{feature.get('icon', '📊')}</div>
                    <h4>{feature.get('title', 'タイトル')}</h4>
                    <p>{feature.get('description', '説明')}</p>
                </div>
                """
            
            features_section = f"""
            <div class="features">
                {features_html}
            </div>
            """
        
        # フッター
        footer_note = content_config.get('footer_note', '')
        footer_note_html = f"<p>{footer_note}</p>" if footer_note else ""
        
        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{content_config.get('main_title', 'ダッシュボード')}</title>
    <style>
        body {{
            font-family: 'Noto Sans JP', Meiryo, sans-serif;
            background: #f5f7fa;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1 {{
            text-align: center;
            color: #293a27;
            margin-bottom: 10px;
            font-size: 2em;
        }}
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 40px;
            font-size: 1.1em;
        }}
        .features {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .feature {{
            text-align: center;
            color: #666;
        }}
        .feature-icon {{
            font-size: 2em;
            margin-bottom: 10px;
        }}
        .dashboard-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 25px;
            margin-top: 30px;
        }}
        .dashboard-card {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        .dashboard-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
        }}
        .dashboard-card h3 {{
            color: #293a27;
            margin-bottom: 10px;
            font-size: 1.3em;
        }}
        .dashboard-card p {{
            color: #666;
            margin-bottom: 15px;
            line-height: 1.5;
        }}
        .update-time {{
            font-size: 0.9em;
            color: #999;
            margin-bottom: 20px !important;
        }}
        .dashboard-link {{
            display: inline-block;
            background: #4CAF50;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
            transition: background 0.3s ease;
        }}
        .dashboard-link:hover {{
            background: #45a049;
        }}
        @media (max-width: 768px) {{
            .dashboard-grid {{
                grid-template-columns: 1fr;
            }}
            h1 {{
                font-size: 1.5em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{content_config.get('main_title', 'ダッシュボード')}</h1>
        <p class="subtitle">{content_config.get('subtitle', '')}</p>
        
        {features_section}
        
        <div class="dashboard-grid">
            {dashboard_links}
        </div>
        
        <footer style="text-align: center; margin-top: 50px; color: #999; border-top: 1px solid #eee; padding-top: 30px;">
            <p>最終更新: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
            <p>{content_config.get('footer_text', 'システム')}</p>
            {footer_note_html}
        </footer>
    </div>
</body>
</html>"""

    def _create_minimal_layout(self, dashboards_info, content_config):
        """シンプル・ミニマルなレイアウト"""
        dashboard_links = ""
        button_text = content_config.get('dashboard_button_text', 'ダッシュボードを開く')
        
        for dashboard in dashboards_info:
            if 'department' in dashboard.get('file', '').lower() or '診療科' in dashboard.get('title', ''):
                description = content_config.get('department_dashboard_description', dashboard.get('description', ''))
            else:
                description = content_config.get('ward_dashboard_description', dashboard.get('description', ''))
                
            dashboard_links += f"""
            <a href="{dashboard['file']}" class="dashboard-button">
                <h3>{dashboard['title']}</h3>
                <p>{description}</p>
            </a>
            """
        
        footer_note = content_config.get('footer_note', '')
        footer_note_html = f"<p>{footer_note}</p>" if footer_note else ""
        
        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{content_config.get('main_title', 'ダッシュボード')}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Noto Sans JP', sans-serif;
            background: #f8f9fa;
            padding: 20px;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }}
        .container {{
            max-width: 600px;
            text-align: center;
        }}
        h1 {{
            font-size: 2.5em;
            color: #2c3e50;
            margin-bottom: 20px;
        }}
        .subtitle {{
            color: #7f8c8d;
            margin-bottom: 40px;
            font-size: 1.1em;
        }}
        .dashboard-button {{
            display: block;
            background: white;
            margin: 20px 0;
            padding: 30px;
            border-radius: 12px;
            text-decoration: none;
            color: #2c3e50;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
            border: 2px solid transparent;
        }}
        .dashboard-button:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.15);
            border-color: #3498db;
        }}
        .dashboard-button h3 {{
            font-size: 1.4em;
            margin-bottom: 10px;
            color: #2c3e50;
        }}
        .dashboard-button p {{
            color: #7f8c8d;
            line-height: 1.5;
        }}
        .footer {{
            margin-top: 40px;
            padding: 20px;
            color: #7f8c8d;
            font-size: 0.9em;
        }}
        @media (max-width: 600px) {{
            h1 {{ font-size: 2em; }}
            .dashboard-button {{ padding: 20px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{content_config.get('main_title', 'ダッシュボード')}</h1>
        <p class="subtitle">{content_config.get('subtitle', '')}</p>
        
        {dashboard_links}
        
        <div class="footer">
            <p>{content_config.get('footer_text', 'システム')}</p>
            {footer_note_html}
            <p>最終更新: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
        </div>
    </div>
</body>
</html>"""

    def _create_corporate_layout(self, dashboards_info, content_config):
        """企業・法人向けフォーマルなレイアウト"""
        dashboard_cards = ""
        button_text = content_config.get('dashboard_button_text', 'アクセス')
        
        for i, dashboard in enumerate(dashboards_info):
            if 'department' in dashboard.get('file', '').lower() or '診療科' in dashboard.get('title', ''):
                description = content_config.get('department_dashboard_description', dashboard.get('description', ''))
            else:
                description = content_config.get('ward_dashboard_description', dashboard.get('description', ''))
                
            update_time = dashboard.get('update_time', '不明')
            dashboard_cards += f"""
            <div class="dashboard-card">
                <div class="card-number">{str(i+1).zfill(2)}</div>
                <h3>{dashboard['title']}</h3>
                <p>{description}</p>
                <div class="card-footer">
                    <span class="update-time">更新: {update_time}</span>
                    <a href="{dashboard['file']}" class="access-button">{button_text}</a>
                </div>
            </div>
            """
        
        footer_note = content_config.get('footer_note', '')
        footer_note_html = f"<p>{footer_note}</p>" if footer_note else ""
        
        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{content_config.get('main_title', 'ダッシュボード')}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Noto Sans JP', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        .header {{
            text-align: center;
            color: white;
            margin-bottom: 50px;
        }}
        .header h1 {{
            font-size: 3em;
            font-weight: 300;
            margin-bottom: 10px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }}
        .header .subtitle {{
            font-size: 1.2em;
            opacity: 0.9;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .dashboard-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
            margin-top: 40px;
        }}
        .dashboard-card {{
            background: white;
            border-radius: 15px;
            padding: 35px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            position: relative;
            overflow: hidden;
            transition: transform 0.3s ease;
        }}
        .dashboard-card:hover {{
            transform: translateY(-10px);
        }}
        .card-number {{
            position: absolute;
            top: -10px;
            right: -10px;
            width: 60px;
            height: 60px;
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5em;
            font-weight: bold;
        }}
        .dashboard-card h3 {{
            color: #2c3e50;
            font-size: 1.6em;
            margin-bottom: 15px;
            padding-right: 60px;
        }}
        .dashboard-card p {{
            color: #7f8c8d;
            line-height: 1.6;
            margin-bottom: 25px;
        }}
        .card-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .update-time {{
            color: #95a5a6;
            font-size: 0.9em;
        }}
        .access-button {{
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            padding: 12px 24px;
            border-radius: 25px;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.3s ease;
        }}
        .access-button:hover {{
            transform: scale(1.05);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }}
        .footer {{
            text-align: center;
            margin-top: 60px;
            color: white;
            opacity: 0.8;
        }}
        @media (max-width: 768px) {{
            .header h1 {{ font-size: 2em; }}
            .dashboard-grid {{ grid-template-columns: 1fr; }}
            .dashboard-card {{ padding: 25px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{content_config.get('main_title', 'ダッシュボード')}</h1>
            <p class="subtitle">{content_config.get('subtitle', '')}</p>
        </div>
        
        <div class="dashboard-grid">
            {dashboard_cards}
        </div>
        
        <div class="footer">
            <p>最終更新: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
            <p>{content_config.get('footer_text', 'システム')}</p>
            {footer_note_html}
        </div>
    </div>
</body>
</html>"""

    def _create_mobile_first_layout(self, dashboards_info, content_config):
        """モバイルファーストなレイアウト"""
        dashboard_list = ""
        
        for dashboard in dashboards_info:
            if 'department' in dashboard.get('file', '').lower() or '診療科' in dashboard.get('title', ''):
                description = content_config.get('department_dashboard_description', dashboard.get('description', ''))
            else:
                description = content_config.get('ward_dashboard_description', dashboard.get('description', ''))
                
            update_time = dashboard.get('update_time', '不明')
            dashboard_list += f"""
            <a href="{dashboard['file']}" class="dashboard-item">
                <div class="item-icon">📊</div>
                <div class="item-content">
                    <h3>{dashboard['title']}</h3>
                    <p>{description}</p>
                    <span class="update-badge">最新: {update_time}</span>
                </div>
                <div class="item-arrow">›</div>
            </a>
            """
        
        footer_note = content_config.get('footer_note', '')
        footer_note_html = f"<p>{footer_note}</p>" if footer_note else ""
        
        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{content_config.get('main_title', 'ダッシュボード')}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans JP', sans-serif;
            background: #f2f2f7;
            color: #1c1c1e;
        }}
        .header {{
            background: linear-gradient(180deg, #007AFF 0%, #5856D6 100%);
            color: white;
            padding: 60px 20px 40px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2.2em;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        .header p {{
            opacity: 0.9;
            font-size: 1.1em;
        }}
        .dashboard-list {{
            padding: 20px 16px;
        }}
        .dashboard-item {{
            background: white;
            border-radius: 12px;
            margin-bottom: 12px;
            padding: 20px;
            display: flex;
            align-items: center;
            text-decoration: none;
            color: inherit;
            box-shadow: 0 2px 10px rgba(0,0,0,0.06);
            transition: all 0.2s ease;
        }}
        .dashboard-item:active {{
            transform: scale(0.98);
            background: #f2f2f7;
        }}
        .item-icon {{
            font-size: 2em;
            margin-right: 16px;
            width: 50px;
            text-align: center;
        }}
        .item-content {{
            flex: 1;
        }}
        .item-content h3 {{
            font-size: 1.2em;
            font-weight: 600;
            margin-bottom: 4px;
            color: #1c1c1e;
        }}
        .item-content p {{
            color: #8e8e93;
            font-size: 0.9em;
            line-height: 1.4;
            margin-bottom: 6px;
        }}
        .update-badge {{
            display: inline-block;
            background: #007AFF;
            color: white;
            font-size: 0.75em;
            padding: 3px 8px;
            border-radius: 10px;
            font-weight: 500;
        }}
        .item-arrow {{
            font-size: 1.8em;
            color: #c7c7cc;
            text-decoration: none;
            margin-left: 10px;
        }}
        .footer-note {{
            text-align: center;
            padding: 40px 20px;
            color: #8e8e93;
            font-size: 0.9em;
        }}
        @media (min-width: 768px) {{
            .header {{ padding: 80px 40px 60px; }}
            .dashboard-list {{ max-width: 600px; margin: 0 auto; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{content_config.get('main_title', 'ダッシュボード')}</h1>
        <p>{content_config.get('subtitle', '')}</p>
    </div>
    
    <div class="dashboard-list">
        {dashboard_list}
    </div>
    
    <div class="footer-note">
        <p>{content_config.get('footer_text', 'システム')}</p>
        {footer_note_html}
        <p>最終更新: {datetime.now().strftime('%Y年%m月%d日 %H時%M分')}</p>
    </div>
</body>
</html>"""
    
    def get_public_url(self):
        """公開URLを取得"""
        return f"https://{self.repo_owner}.github.io/{self.repo_name}/"

class ContentCustomizer:
    """トップページの内容・文章をカスタマイズ"""
    
    def __init__(self):
        self.default_content = {
            # ヘッダー部分
            "main_title": "🏥 病院パフォーマンスダッシュボード",
            "subtitle": "スマートフォン対応・リアルタイム更新",
            
            # 機能紹介部分
            "show_features": True,
            "features": [
                {
                    "icon": "📊",
                    "title": "リアルタイム指標",
                    "description": "最新の病院パフォーマンス指標"
                },
                {
                    "icon": "📱",
                    "title": "モバイル最適化",
                    "description": "スマートフォンで快適に閲覧"
                },
                {
                    "icon": "🔄",
                    "title": "自動更新",
                    "description": "データは定期的に自動更新"
                },
                {
                    "icon": "🔒",
                    "title": "プライバシー保護",
                    "description": "個人情報は含まれません"
                }
            ],
            
            # ダッシュボード説明
            "department_dashboard_description": "各診療科の入院患者数、新入院患者数、平均在院日数の実績と目標達成率",
            "ward_dashboard_description": "各病棟の入院患者数、新入院患者数、平均在院日数の実績と目標達成率",
            
            # フッター
            "footer_text": "🏥 病院パフォーマンス分析システム",
            "footer_note": "",
            
            # ボタンテキスト
            "dashboard_button_text": "ダッシュボードを開く"
        }
    
    def create_streamlit_interface(self):
        """Streamlitで内容編集インターフェースを作成"""
        
        with st.sidebar.expander("📝 トップページ内容編集", expanded=False):
            
            # ヘッダー部分
            st.markdown("### 🏠 ヘッダー部分")
            main_title = st.text_input(
                "メインタイトル",
                value=st.session_state.get('content_main_title', self.default_content["main_title"]),
                key="content_main_title",
                help="トップページの大見出し"
            )
            
            subtitle = st.text_input(
                "サブタイトル",
                value=st.session_state.get('content_subtitle', self.default_content["subtitle"]),
                key="content_subtitle",
                help="タイトル下の説明文"
            )
            
            # 機能紹介部分
            st.markdown("### ✨ 機能紹介部分")
            show_features = st.checkbox(
                "機能紹介セクションを表示",
                value=st.session_state.get('content_show_features', True),
                key="content_show_features"
            )
            
            if show_features:
                for i in range(4):
                    with st.expander(f"機能 {i+1}", expanded=False):
                        feature_icon = st.text_input(
                            "アイコン",
                            value=st.session_state.get(f'content_feature_{i}_icon', self.default_content["features"][i]["icon"]),
                            key=f"content_feature_{i}_icon"
                        )
                        feature_title = st.text_input(
                            "タイトル",
                            value=st.session_state.get(f'content_feature_{i}_title', self.default_content["features"][i]["title"]),
                            key=f"content_feature_{i}_title"
                        )
                        feature_desc = st.text_area(
                            "説明",
                            value=st.session_state.get(f'content_feature_{i}_description', self.default_content["features"][i]["description"]),
                            key=f"content_feature_{i}_description",
                            height=50
                        )
            
            # ダッシュボード説明
            st.markdown("### 📊 ダッシュボード説明")
            dept_description = st.text_area(
                "診療科別ダッシュボード説明",
                value=st.session_state.get('content_dept_description', self.default_content["department_dashboard_description"]),
                key="content_dept_description",
                height=60
            )
            
            ward_description = st.text_area(
                "病棟別ダッシュボード説明",
                value=st.session_state.get('content_ward_description', self.default_content["ward_dashboard_description"]),
                key="content_ward_description",
                height=60
            )
            
            # フッター部分
            st.markdown("### 🔻 フッター部分")
            footer_text = st.text_input(
                "フッターメインテキスト",
                value=st.session_state.get('content_footer_text', self.default_content["footer_text"]),
                key="content_footer_text"
            )
            
            footer_note = st.text_area(
                "フッター追加メモ",
                value=st.session_state.get('content_footer_note', self.default_content["footer_note"]),
                key="content_footer_note",
                height=60,
                help="病院名や部署名など"
            )
            
            # ボタンテキスト
            st.markdown("### 🔘 ボタン・リンク")
            button_text = st.text_input(
                "ダッシュボードボタンテキスト",
                value=st.session_state.get('content_button_text', self.default_content["dashboard_button_text"]),
                key="content_button_text"
            )
            
            # プリセット適用
            st.markdown("### ⚡ プリセット適用")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("🏥 病院標準", key="content_preset_hospital", use_container_width=True):
                    self._apply_hospital_content_preset()
            
            with col2:
                if st.button("🏢 経営層向け", key="content_preset_executive", use_container_width=True):
                    self._apply_executive_content_preset()
            
            with col3:
                if st.button("👥 職員親近", key="content_preset_friendly", use_container_width=True):
                    self._apply_friendly_content_preset()
            
            # 設定保存
            st.markdown("---")
            if st.button("💾 内容設定を保存", key="save_content_settings", type="primary"):
                self._save_current_content()
                st.success("✅ 内容設定を保存しました")
    
    def _apply_hospital_content_preset(self):
        """病院標準プリセット"""
        st.session_state.content_main_title = "🏥 [病院名] パフォーマンスダッシュボード"
        st.session_state.content_subtitle = "医療の質向上と効率化を目指して"
        st.session_state.content_footer_text = "🏥 [病院名] 医療情報管理システム"
        st.session_state.content_footer_note = "お問い合わせ：情報システム部門（内線xxxx）"
        st.rerun()
    
    def _apply_executive_content_preset(self):
        """経営層向けプリセット"""
        st.session_state.content_main_title = "経営管理ダッシュボード"
        st.session_state.content_subtitle = "Hospital Performance Management System"
        st.session_state.content_footer_text = "Hospital Management Intelligence System"
        st.session_state.content_footer_note = "Confidential - Internal Use Only"
        st.rerun()
    
    def _apply_friendly_content_preset(self):
        """職員親近プリセット"""
        st.session_state.content_main_title = "📊 みんなのダッシュボード"
        st.session_state.content_subtitle = "スマホで簡単！病院の「今」をチェック"
        st.session_state.content_footer_text = "🌟 みんなで作る より良い病院"
        st.session_state.content_footer_note = "質問があったら情報システム課まで気軽にどうぞ♪"
        st.rerun()
    
    def _save_current_content(self):
        """現在の設定をセッションに保存"""
        content_config = {
            "main_title": st.session_state.get('content_main_title', ''),
            "subtitle": st.session_state.get('content_subtitle', ''),
            "show_features": st.session_state.get('content_show_features', True),
            "features": [],
            "department_dashboard_description": st.session_state.get('content_dept_description', ''),
            "ward_dashboard_description": st.session_state.get('content_ward_description', ''),
            "footer_text": st.session_state.get('content_footer_text', ''),
            "footer_note": st.session_state.get('content_footer_note', ''),
            "dashboard_button_text": st.session_state.get('content_button_text', '')
        }
        
        # 機能紹介の保存
        for i in range(4):
            feature = {
                "icon": st.session_state.get(f'content_feature_{i}_icon', ''),
                "title": st.session_state.get(f'content_feature_{i}_title', ''),
                "description": st.session_state.get(f'content_feature_{i}_description', '')
            }
            content_config["features"].append(feature)
        
        st.session_state.custom_content_config = content_config
    
    def get_current_config(self):
        """現在の設定を取得"""
        if hasattr(st.session_state, 'custom_content_config'):
            return st.session_state.custom_content_config
        else:
            return self.default_content

def generate_department_dashboard_html(df, target_data, period="直近4週間"):
    """診療科別ダッシュボードのHTML生成"""
    try:
        from department_performance_tab import get_period_dates, calculate_department_kpis
        from unified_html_export import generate_unified_html_export
        from utils import safe_date_filter
        from config import EXCLUDED_WARDS
        
        start_date, end_date, period_desc = get_period_dates(df, period)
        
        if start_date is None or end_date is None:
            return None, "期間の計算に失敗しました"
        
        date_filtered_df = safe_date_filter(df, start_date, end_date)
        
        if '病棟コード' in date_filtered_df.columns and EXCLUDED_WARDS:
            date_filtered_df = date_filtered_df[~date_filtered_df['病棟コード'].isin(EXCLUDED_WARDS)]

        if date_filtered_df.empty:
            return None, "データがありません"
        
        possible_cols = ['部門名', '診療科', '診療科名']
        dept_col = next((c for c in possible_cols if c in date_filtered_df.columns), None)
        if dept_col is None:
            return None, "診療科列が見つかりません"

        unique_depts = date_filtered_df[dept_col].unique()
        dept_kpis = []
        
        for dept_code in unique_depts:
            dept_name = dept_code
            kpi = calculate_department_kpis(
                date_filtered_df, target_data, dept_code, dept_name, 
                start_date, end_date, dept_col
            )
            if kpi:
                dept_kpis.append(kpi)
        
        if not dept_kpis:
            return None, "KPIデータが生成できませんでした"
        
        html_content = generate_unified_html_export(
            kpis_data=dept_kpis,
            period_desc=period_desc,
            dashboard_type="department"
        )
        
        return html_content, "成功"
        
    except Exception as e:
        logger.error(f"診療科別ダッシュボード生成エラー: {e}", exc_info=True)
        return None, f"エラー: {str(e)}"

def generate_ward_dashboard_html(df, target_data, period="直近4週間"):
    """病棟別ダッシュボードのHTML生成"""
    try:
        from ward_performance_tab import get_period_dates, calculate_ward_kpis
        from unified_html_export import generate_unified_html_export
        from utils import safe_date_filter, get_ward_display_name
        from config import EXCLUDED_WARDS
        
        start_date, end_date, period_desc = get_period_dates(df, period)
        
        if start_date is None or end_date is None:
            return None, "期間の計算に失敗しました"
        
        date_filtered_df = safe_date_filter(df, start_date, end_date)
        
        if date_filtered_df.empty:
            return None, "データがありません"
        
        possible_cols = ['病棟コード', '病棟名', '病棟']
        ward_col = next((c for c in possible_cols if c in date_filtered_df.columns), None)
        if ward_col is None:
            return None, "病棟列が見つかりません"

        unique_wards = date_filtered_df[ward_col].unique()
        unique_wards = [ward for ward in unique_wards if ward not in EXCLUDED_WARDS]
        ward_kpis = []
        
        for ward_code in unique_wards:
            ward_name = get_ward_display_name(ward_code)
            kpi = calculate_ward_kpis(
                date_filtered_df, target_data, ward_code, ward_name, 
                start_date, end_date, ward_col
            )
            if kpi:
                ward_kpis.append(kpi)
        
        if not ward_kpis:
            return None, "KPIデータが生成できませんでした"
        
        html_content = generate_unified_html_export(
            kpis_data=ward_kpis,
            period_desc=period_desc,
            dashboard_type="ward"
        )
        
        return html_content, "成功"
        
    except Exception as e:
        logger.error(f"病棟別ダッシュボード生成エラー: {e}", exc_info=True)
        return None, f"エラー: {str(e)}"

def create_github_publisher_interface():
    """Streamlit用のGitHub自動公開インターフェース（完全版）"""
    
    st.sidebar.markdown("---")
    st.sidebar.header("🌐 職員向け自動公開")
    
    # GitHub設定
    with st.sidebar.expander("⚙️ GitHub設定", expanded=False):
        st.markdown("**Personal Access Token作成方法:**")
        st.markdown("1. GitHub → Settings → Developer settings")
        st.markdown("2. Personal access tokens → Tokens (classic)")
        st.markdown("3. Generate new token → repo権限を選択")
        
        github_token = st.text_input(
            "GitHub Personal Access Token",
            type="password",
            help="リポジトリへの書き込み権限が必要",
            key="github_publisher_token"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            repo_owner = st.text_input(
                "オーナー名",
                value="Genie-Scripts",
                key="github_publisher_owner"
            )
        with col2:
            repo_name = st.text_input(
                "リポジトリ名", 
                value="Streamlit-Inpatient-Dashboard",
                key="github_publisher_repo"
            )
        
        publish_path = st.selectbox(
            "公開フォルダ",
            ["docs/", "public/", ""],
            index=0,
            help="GitHub Pagesの公開元フォルダ",
            key="github_publish_folder_select"
        )
        
        if st.button("💾 GitHub設定を保存", key="save_github_publisher_settings"):
            if github_token and repo_owner and repo_name:
                st.session_state.github_publisher = GitHubPublisher(
                    repo_owner, repo_name, github_token, "main"
                )
                st.session_state.github_publish_path_config = publish_path
                st.success("✅ GitHub設定を保存しました")
                
                st.info(f"""
                **GitHub Pages設定**  
                1. GitHubリポジトリ → Settings → Pages  
                2. Source: Deploy from a branch  
                3. Branch: main / {publish_path or 'root'}  
                
                **公開URL:** https://{repo_owner}.github.io/{repo_name}/
                """)
            else:
                st.error("すべての項目を入力してください")
    
    # 内容カスタマイズ機能
    content_customizer = ContentCustomizer()
    content_customizer.create_streamlit_interface()
    
    # 公開機能（データが読み込まれている場合のみ）
    if (st.session_state.get('github_publisher') and 
        st.session_state.get('data_processed') and 
        st.session_state.get('df') is not None):
        
        st.sidebar.markdown("### 🚀 ダッシュボード公開")
        
        # 期間選択
        period_options = ["直近4週間", "直近8週", "直近12週", "今年度"]
        selected_period = st.sidebar.selectbox(
            "公開データ期間",
            period_options,
            index=0,
            help="職員向けダッシュボードに使用するデータ期間",
            key="github_publish_period"
        )
        
        # レイアウトスタイルの選択
        layout_styles = {
            "default": "🎯 標準レイアウト",
            "minimal": "✨ ミニマル・シンプル", 
            "corporate": "🏢 企業・フォーマル",
            "mobile_first": "📱 モバイルファースト"
        }
        
        selected_layout = st.sidebar.selectbox(
            "🎨 トップページレイアウト",
            list(layout_styles.keys()),
            format_func=lambda x: layout_styles[x],
            index=0,
            help="職員向けトップページのデザインスタイル",
            key="github_layout_style"
        )
        
        # レイアウトプレビュー
        with st.sidebar.expander("👀 レイアウトプレビュー", expanded=False):
            if selected_layout == "minimal":
                st.markdown("""
                **✨ ミニマル・シンプル**
                - 中央配置のシンプルなデザイン
                - 大きなボタン形式
                - 余計な情報を排除
                - 高齢者にも見やすい
                """)
            elif selected_layout == "corporate":
                st.markdown("""
                **🏢 企業・フォーマル**
                - プロフェッショナルなグラデーション
                - 番号付きカード
                - 更新時刻明記
                - 経営層向けデザイン
                """)
            elif selected_layout == "mobile_first":
                st.markdown("""
                **📱 モバイルファースト**
                - iOS/Android風リスト形式
                - タップしやすい大きな領域
                - スマホアプリライク
                - 若手職員向け
                """)
            else:
                st.markdown("""
                **🎯 標準レイアウト**
                - バランスの取れたデザイン
                - 機能説明付き
                - 全年齢層対応
                - 多機能表示
                """)
        
        # 公開するダッシュボードの選択
        publish_options = st.sidebar.multiselect(
            "公開ダッシュボード",
            ["診療科別パフォーマンス", "病棟別パフォーマンス", "統合インデックス"],
            default=["診療科別パフォーマンス", "病棟別パフォーマンス", "統合インデックス"],
            help="職員向けに公開するダッシュボード",
            key="github_publish_options"
        )
        
        # 内容プレビュー
        with st.sidebar.expander("👀 内容プレビュー", expanded=False):
            content_config = content_customizer.get_current_config()
            st.markdown(f"**タイトル:** {content_config.get('main_title', 'デフォルト')}")
            st.markdown(f"**サブタイトル:** {content_config.get('subtitle', 'デフォルト')}")
            st.markdown(f"**レイアウト:** {layout_styles[selected_layout]}")
            st.markdown(f"**ボタンテキスト:** {content_config.get('dashboard_button_text', 'デフォルト')}")
        
        # 自動公開実行
        if st.sidebar.button("🚀 GitHub Pagesに自動公開", key="execute_github_publish", type="primary"):
            
            publisher = st.session_state.github_publisher
            publish_path = st.session_state.get('github_publish_path_config', 'docs/')
            df = st.session_state['df']
            target_data = st.session_state.get('target_data', pd.DataFrame())
            
            # カスタム内容設定を取得
            content_config = content_customizer.get_current_config()
            
            results = []
            progress_bar = st.sidebar.progress(0)
            status_text = st.sidebar.empty()
            
            total_tasks = len(publish_options)
            current_task = 0
            
            try:
                # 診療科別ダッシュボード
                if "診療科別パフォーマンス" in publish_options:
                    status_text.text("診療科別ダッシュボードを生成中...")
                    progress_bar.progress(current_task / total_tasks)
                    
                    dept_html, dept_message = generate_department_dashboard_html(
                        df, target_data, selected_period
                    )
                    
                    if dept_html:
                        success, message = publisher.upload_html_file(
                            dept_html,
                            f"{publish_path}dept_performance.html",
                            f"Update department performance dashboard - {selected_period}"
                        )
                        results.append(("診療科別", success, message))
                    else:
                        results.append(("診療科別", False, dept_message))
                    
                    current_task += 1
                    progress_bar.progress(current_task / total_tasks)
                
                # 病棟別ダッシュボード
                if "病棟別パフォーマンス" in publish_options:
                    status_text.text("病棟別ダッシュボードを生成中...")
                    
                    ward_html, ward_message = generate_ward_dashboard_html(
                        df, target_data, selected_period
                    )
                    
                    if ward_html:
                        success, message = publisher.upload_html_file(
                            ward_html,
                            f"{publish_path}ward_performance.html",
                            f"Update ward performance dashboard - {selected_period}"
                        )
                        results.append(("病棟別", success, message))
                    else:
                        results.append(("病棟別", False, ward_message))
                    
                    current_task += 1
                    progress_bar.progress(current_task / total_tasks)
                
                # インデックスページ（カスタム内容・レイアウト対応）
                if "統合インデックス" in publish_options:
                    status_text.text("インデックスページを生成中...")
                    
                    dashboards_info = []
                    
                    if "診療科別パフォーマンス" in publish_options:
                        dashboards_info.append({
                            "title": "診療科別パフォーマンス",
                            "description": content_config.get('department_dashboard_description', 
                                f"各診療科の入院患者数、新入院患者数、平均在院日数の実績と目標達成率（{selected_period}）"),
                            "file": "dept_performance.html",
                            "update_time": datetime.now().strftime('%Y/%m/%d %H:%M')
                        })
                    
                    if "病棟別パフォーマンス" in publish_options:
                        dashboards_info.append({
                            "title": "病棟別パフォーマンス",
                            "description": content_config.get('ward_dashboard_description',
                                f"各病棟の入院患者数、新入院患者数、平均在院日数の実績と目標達成率（{selected_period}）"),
                            "file": "ward_performance.html",
                            "update_time": datetime.now().strftime('%Y/%m/%d %H:%M')
                        })
                    
                    # カスタム内容・レイアウトでインデックスページ生成
                    index_html = publisher.create_index_page(dashboards_info, selected_layout, content_config)
                    
                    success, message = publisher.upload_html_file(
                        index_html,
                        f"{publish_path}index.html",
                        f"Update dashboard index page - {selected_period} - {layout_styles[selected_layout]}"
                    )
                    results.append(("インデックス", success, message))
                    
                    current_task += 1
                    progress_bar.progress(1.0)
                
                status_text.text("公開完了！")
                
                # 結果表示
                all_success = True
                for dashboard_type, success, message in results:
                    if success:
                        st.sidebar.success(f"✅ {dashboard_type}: 公開成功")
                    else:
                        st.sidebar.error(f"❌ {dashboard_type}: {message}")
                        all_success = False
                
                if all_success and results:
                    public_url = publisher.get_public_url()
                    
                    st.sidebar.success("🎉 カスタム公開完了！")
                    st.sidebar.markdown("### 📱 職員への配布方法")
                    
                    st.sidebar.text_input(
                        "公開URL（QRコード生成用）",
                        value=public_url,
                        key="github_public_url_display"
                    )
                    
                    st.sidebar.markdown(f"""
                    **✨ 公開内容:**
                    - レイアウト: {layout_styles[selected_layout]}
                    - カスタム内容適用済み
                    - 期間: {selected_period}
                    
                    **配布手順:**
                    1. [QRコード生成](https://www.qr-code-generator.com/)
                    2. 院内掲示板・メール配布
                    3. 職員向け説明会で案内
                    """)
                
            except Exception as e:
                st.sidebar.error(f"❌ 公開処理エラー: {str(e)}")
                logger.error(f"GitHub公開エラー: {e}", exc_info=True)
            
            finally:
                progress_bar.empty()
                status_text.empty()
    
    elif st.session_state.get('github_publisher'):
        st.sidebar.info("📊 データを読み込み後に公開機能が利用可能になります")
    else:
        st.sidebar.info("⚙️ 上記でGitHub設定を行ってください")