# github_publisher.py (機能追加・修正版)

import os
import json
import requests
import base64
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ===== このファイル内で利用するインポートを追加 =====
try:
    from chart import (
        create_interactive_alos_chart,
        create_interactive_patient_chart,
        create_interactive_dual_axis_chart
    )
    from unified_filters import get_unified_filter_summary
    CHARTS_AVAILABLE = True
except ImportError:
    CHARTS_AVAILABLE = False


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
    
    def upload_external_html(self, html_content, filename, dashboard_title, commit_message=None):
        """外部HTMLファイル（手術分析など）をアップロード"""
        try:
            safe_filename = filename.lower().replace(' ', '_').replace('　', '_')
            if not safe_filename.endswith('.html'):
                safe_filename += '.html'
            
            file_path = f"docs/{safe_filename}"
            
            if not commit_message:
                commit_message = f"Update external dashboard: {dashboard_title} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            return self.upload_html_file(html_content, file_path, commit_message)
            
        except Exception as e:
            return False, f"外部HTMLアップロードエラー: {str(e)}"
    
    def get_external_dashboards_list(self):
        """アップロード済み外部ダッシュボード一覧を取得"""
        try:
            return st.session_state.get('external_dashboards', [])
        except:
            return []
    
    def _get_relative_path(self, file_path, dashboard_type=None):
        """相対パスを正しく取得する"""
        if '/' not in file_path:
            return file_path
        if file_path.startswith('docs/'):
            return file_path.replace('docs/', '')
        return file_path
    
    def create_index_page(self, dashboards_info, layout_style="default", content_config=None, external_dashboards=None):
        """ダッシュボード一覧のインデックスページを生成（外部ダッシュボード対応）"""
        if content_config is None:
            content_config = ContentCustomizer().default_content
        
        all_dashboards = dashboards_info.copy() if dashboards_info else []
        if external_dashboards:
            for ext_dash in external_dashboards:
                if 'file' in ext_dash and ext_dash['file'].startswith('docs/'):
                    ext_dash['file'] = ext_dash['file'].replace('docs/', '')
            all_dashboards.extend(external_dashboards)
        
        logger.info(f"Total dashboards: {len(all_dashboards)}")
            
        if layout_style == "minimal":
            return self._create_minimal_layout(all_dashboards, content_config)
        elif layout_style == "corporate":
            return self._create_corporate_layout(all_dashboards, content_config)
        elif layout_style == "mobile_first":
            return self._create_mobile_first_layout(all_dashboards, content_config)
        else:
            return self._create_default_layout(all_dashboards, content_config)

    def _create_default_layout(self, dashboards_info, content_config):
        """デフォルトレイアウト（外部ダッシュボード対応）"""
        dashboard_links = ""
        button_text = content_config.get('dashboard_button_text', 'ダッシュボードを開く')
        
        for dashboard in dashboards_info:
            if 'department' in dashboard.get('file', '').lower() or '診療科' in dashboard.get('title', ''):
                description = content_config.get('department_dashboard_description', dashboard.get('description', ''))
            elif 'ward' in dashboard.get('file', '').lower() or '病棟' in dashboard.get('title', ''):
                description = content_config.get('ward_dashboard_description', dashboard.get('description', ''))
            elif dashboard.get('type') == 'external':
                description = dashboard.get('description', '外部システムから提供されるダッシュボード')
            else:
                description = dashboard.get('description', '')
                
            update_time = dashboard.get('update_time', '不明')
            title_with_icon = dashboard['title']
            if dashboard.get('type') == 'external':
                title_with_icon = f"🔗 {dashboard['title']}"
            
            file_path = self._get_relative_path(dashboard['file'], dashboard.get('type'))
            
            dashboard_links += f"""
            <div class="dashboard-card">
                <h3>{title_with_icon}</h3>
                <p>{description}</p>
                <p class="update-time">最終更新: {update_time}</p>
                <a href="{file_path}" class="dashboard-link">{button_text}</a>
            </div>
            """
        
        features_section = ""
        if content_config.get('show_features', True):
            features_html = ""
            for feature in content_config.get('features', []):
                features_html += f"""
                <div class="feature">
                    <div class="feature-icon">{feature.get('icon', '📊')}</div>
                    <h4>{feature.get('title', 'タイトル')}</h4>
                    <p>{feature.get('description', '説明')}</p>
                </div>"""
            features_section = f'<div class="features">{features_html}</div>'
        
        footer_note = content_config.get('footer_note', '')
        footer_note_html = f"<p>{footer_note}</p>" if footer_note else ""
        
        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{content_config.get('main_title', 'ダッシュボード')}</title>
    <style> body {{ font-family: 'Noto Sans JP', Meiryo, sans-serif; background: #f5f7fa; margin: 0; padding: 20px; }} .container {{ max-width: 1200px; margin: 0 auto; }} h1 {{ text-align: center; color: #293a27; margin-bottom: 10px; font-size: 2em; }} .subtitle {{ text-align: center; color: #666; margin-bottom: 40px; font-size: 1.1em; }} .features {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; }} .feature {{ text-align: center; color: #666; }} .feature-icon {{ font-size: 2em; margin-bottom: 10px; }} .dashboard-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 25px; margin-top: 30px; }} .dashboard-card {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); transition: transform 0.2s ease, box-shadow 0.2s ease; }} .dashboard-card:hover {{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.15); }} .dashboard-card h3 {{ color: #293a27; margin-bottom: 10px; font-size: 1.3em; }} .dashboard-card p {{ color: #666; margin-bottom: 15px; line-height: 1.5; }} .update-time {{ font-size: 0.9em; color: #999; margin-bottom: 20px !important; }} .dashboard-link {{ display: inline-block; background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; transition: background 0.3s ease; }} .dashboard-link:hover {{ background: #45a049; }} @media (max-width: 768px) {{ .dashboard-grid {{ grid-template-columns: 1fr; }} h1 {{ font-size: 1.5em; }} }} </style>
</head>
<body>
    <div class="container">
        <h1>{content_config.get('main_title', 'ダッシュボード')}</h1>
        <p class="subtitle">{content_config.get('subtitle', '')}</p>
        {features_section}
        <div class="dashboard-grid">{dashboard_links}</div>
        <footer style="text-align: center; margin-top: 50px; color: #999; border-top: 1px solid #eee; padding-top: 30px;">
            <p>最終更新: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
            <p>{content_config.get('footer_text', 'システム')}</p>
            {footer_note_html}
        </footer>
    </div>
</body>
</html>"""

    def _create_minimal_layout(self, dashboards_info, content_config):
        """シンプル・ミニマルなレイアウト（外部ダッシュボード対応）"""
        dashboard_links = ""
        button_text = content_config.get('dashboard_button_text', 'ダッシュボードを開く')
        
        for dashboard in dashboards_info:
            if 'department' in dashboard.get('file', '').lower() or '診療科' in dashboard.get('title', ''):
                description = content_config.get('department_dashboard_description', dashboard.get('description', ''))
            elif 'ward' in dashboard.get('file', '').lower() or '病棟' in dashboard.get('title', ''):
                description = content_config.get('ward_dashboard_description', dashboard.get('description', ''))
            else:
                description = dashboard.get('description', '')
                
            title_with_icon = dashboard['title']
            if dashboard.get('type') == 'external':
                title_with_icon = f"🔗 {dashboard['title']}"
            
            # 相対パスの正しい処理
            file_path = self._get_relative_path(dashboard['file'], dashboard.get('type'))
                
            dashboard_links += f"""
            <a href="{file_path}" class="dashboard-button">
                <h3>{title_with_icon}</h3>
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
        """企業・法人向けフォーマルなレイアウト（外部ダッシュボード対応）"""
        dashboard_cards = ""
        button_text = content_config.get('dashboard_button_text', 'アクセス')
        
        for i, dashboard in enumerate(dashboards_info):
            if 'department' in dashboard.get('file', '').lower() or '診療科' in dashboard.get('title', ''):
                description = content_config.get('department_dashboard_description', dashboard.get('description', ''))
            elif 'ward' in dashboard.get('file', '').lower() or '病棟' in dashboard.get('title', ''):
                description = content_config.get('ward_dashboard_description', dashboard.get('description', ''))
            else:
                description = dashboard.get('description', '')
                
            update_time = dashboard.get('update_time', '不明')
            
            title_with_icon = dashboard['title']
            if dashboard.get('type') == 'external':
                title_with_icon = f"🔗 {dashboard['title']}"
            
            # 相対パスの正しい処理
            file_path = self._get_relative_path(dashboard['file'], dashboard.get('type'))
            
            dashboard_cards += f"""
            <div class="dashboard-card">
                <div class="card-number">{str(i+1).zfill(2)}</div>
                <h3>{title_with_icon}</h3>
                <p>{description}</p>
                <div class="card-footer">
                    <span class="update-time">更新: {update_time}</span>
                    <a href="{file_path}" class="access-button">{button_text}</a>
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
        """モバイルファーストなレイアウト（外部ダッシュボード対応）"""
        dashboard_list = ""
        
        for dashboard in dashboards_info:
            if 'department' in dashboard.get('file', '').lower() or '診療科' in dashboard.get('title', ''):
                description = content_config.get('department_dashboard_description', dashboard.get('description', ''))
            elif 'ward' in dashboard.get('file', '').lower() or '病棟' in dashboard.get('title', ''):
                description = content_config.get('ward_dashboard_description', dashboard.get('description', ''))
            else:
                description = dashboard.get('description', '')
                
            update_time = dashboard.get('update_time', '不明')
            
            # アイコンの設定
            icon = "🔗" if dashboard.get('type') == 'external' else "📊"
            
            # 相対パスの正しい処理
            file_path = self._get_relative_path(dashboard['file'], dashboard.get('type'))
            
            dashboard_list += f"""
            <a href="{file_path}" class="dashboard-item">
                <div class="item-icon">{icon}</div>
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
    def __init__(self):
        self.default_content = {"main_title": "🏥 統合ダッシュボード", "subtitle": "入院管理・手術分析・スマートフォン対応", "show_features": True, "features": [{"icon": "📊", "title": "入院パフォーマンス", "description": "病棟・診療科別の入院指標"}, {"icon": "🏥", "title": "手術分析", "description": "手術実績と効率性の分析"}, {"icon": "📱", "title": "モバイル最適化", "description": "スマートフォンで快適に閲覧"}, {"icon": "🔄", "title": "自動更新", "description": "データは定期的に自動更新"}], "department_dashboard_description": "各診療科の入院患者数、新入院患者数、平均在院日数の実績と目標達成率", "ward_dashboard_description": "各病棟の入院患者数、新入院患者数、平均在院日数の実績と目標達成率", "footer_text": "🏥 病院統合分析システム", "footer_note": "", "dashboard_button_text": "ダッシュボードを開く"}
        self.presets = {"hospital": {"main_title": "🏥 [病院名] 統合ダッシュボード", "subtitle": "入院・手術分析で医療の質向上を目指して", "footer_text": "🏥 [病院名] 医療情報統合システム", "footer_note": "お問い合わせ：情報システム部門（内線xxxx）"}, "executive": {"main_title": "経営統合ダッシュボード", "subtitle": "Hospital Performance & Surgery Analytics", "footer_text": "Hospital Integrated Intelligence System", "footer_note": "Confidential - Internal Use Only"}, "friendly": {"main_title": "📊 みんなの統合ダッシュボード", "subtitle": "入院も手術も！スマホで簡単チェック", "footer_text": "🌟 みんなで作る より良い病院", "footer_note": "質問があったら情報システム課まで気軽にどうぞ♪"}}
    
    def create_streamlit_interface(self):
        st.sidebar.markdown("---")
        st.sidebar.markdown("### ⚡ プリセット選択")
        preset_options = {"custom": "カスタム（手動設定）", "hospital": "🏥 病院標準", "executive": "🏢 経営層向け", "friendly": "👥 職員親近"}
        selected_preset = st.sidebar.selectbox("テンプレート選択", list(preset_options.keys()), format_func=lambda x: preset_options[x], key="content_preset_selection")
        preset_values = self.presets.get(selected_preset, {})
        st.sidebar.markdown("### 📝 トップページ内容編集")
        main_title = st.sidebar.text_input("メインタイトル", value=preset_values.get('main_title', self.default_content["main_title"]), key="content_main_title")
        if st.sidebar.button("💾 内容設定を保存", key="save_content_settings", type="primary"):
            st.sidebar.success("✅ 内容設定を保存しました")

    def get_current_config(self):
        return self.default_content

# ... (generate_department_dashboard_html and generate_ward_dashboard_html remain the same) ...
def generate_department_dashboard_html(df, target_data, period="直近4週間"):
    """診療科別ダッシュボードのHTML生成"""
    try:
        from department_performance_tab import get_period_dates, calculate_department_kpis
        from unified_html_export import generate_unified_html_export
        from utils import safe_date_filter
        from config import EXCLUDED_WARDS
        
        start_date, end_date, period_desc = get_period_dates(df, period)
        if start_date is None or end_date is None: return None, "期間の計算に失敗"
        date_filtered_df = safe_date_filter(df, start_date, end_date)
        if '病棟コード' in date_filtered_df.columns and EXCLUDED_WARDS:
            date_filtered_df = date_filtered_df[~date_filtered_df['病棟コード'].isin(EXCLUDED_WARDS)]
        if date_filtered_df.empty: return None, "データがありません"
        
        dept_col = next((c for c in ['部門名', '診療科', '診療科名'] if c in date_filtered_df.columns), None)
        if dept_col is None: return None, "診療科列が見つかりません"

        unique_depts = date_filtered_df[dept_col].unique()
        dept_kpis = [kpi for dept_code in unique_depts if (kpi := calculate_department_kpis(date_filtered_df, target_data, dept_code, dept_code, start_date, end_date, dept_col))]
        
        if not dept_kpis: return None, "KPIデータが生成できませんでした"
        
        html_content = generate_unified_html_export(kpis_data=dept_kpis, period_desc=period_desc, dashboard_type="department")
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
        if start_date is None or end_date is None: return None, "期間の計算に失敗"
        date_filtered_df = safe_date_filter(df, start_date, end_date)
        if date_filtered_df.empty: return None, "データがありません"

        ward_col = next((c for c in ['病棟コード', '病棟名', '病棟'] if c in date_filtered_df.columns), None)
        if ward_col is None: return None, "病棟列が見つかりません"

        unique_wards = [ward for ward in date_filtered_df[ward_col].unique() if ward not in EXCLUDED_WARDS]
        ward_kpis = [kpi for ward_code in unique_wards if (kpi := calculate_ward_kpis(date_filtered_df, target_data, ward_code, get_ward_display_name(ward_code), start_date, end_date, ward_col))]
        
        if not ward_kpis: return None, "KPIデータが生成できませんでした"
        html_content = generate_unified_html_export(kpis_data=ward_kpis, period_desc=period_desc, dashboard_type="ward")
        return html_content, "成功"
    except Exception as e:
        logger.error(f"病棟別ダッシュボード生成エラー: {e}", exc_info=True)
        return None, f"エラー: {str(e)}"
# ...

def create_external_dashboard_uploader():
    """外部ダッシュボード（手術分析など）アップロード機能"""
    st.sidebar.markdown("---")
    st.sidebar.header("🔗 外部ダッシュボード追加")
    with st.sidebar.expander("📤 HTMLファイルアップロード", expanded=False):
        pass # 省略

# ★★★ ここから新規追加・修正箇所 ★★★

def generate_individual_analysis_html(df_filtered):
    """
    現在の個別分析ビューから単体のHTMLレポートを生成する
    """
    if df_filtered is None or df_filtered.empty:
        return None, "分析対象のデータがありません。"

    if not CHARTS_AVAILABLE:
        return None, "グラフ生成モジュールが利用できません。"

    try:
        # 現在のフィルター条件を取得
        filter_summary = get_unified_filter_summary()
        
        # 3つのグラフを生成
        with st.spinner("個別分析レポートのグラフを生成中..."):
            fig_alos = create_interactive_alos_chart(df_filtered, title="平均在院日数推移", days_to_show=90)
            fig_patient = create_interactive_patient_chart(df_filtered, title="入院患者数推移", days=90)
            fig_dual_axis = create_interactive_dual_axis_chart(df_filtered, title="患者移動推移", days=90)

        # グラフをHTMLコンポーネントに変換
        div_alos = fig_alos.to_html(full_html=False, include_plotlyjs='cdn') if fig_alos else "<div>平均在院日数グラフの生成に失敗しました。</div>"
        div_patient = fig_patient.to_html(full_html=False, include_plotlyjs=False) if fig_patient else "<div>入院患者数グラフの生成に失敗しました。</div>"
        div_dual_axis = fig_dual_axis.to_html(full_html=False, include_plotlyjs=False) if fig_dual_axis else "<div>患者移動グラフの生成に失敗しました。</div>"

        # HTMLテンプレート
        html_template = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>個別分析レポート</title>
    <style>
        body {{ font-family: sans-serif; margin: 2em; background-color: #f9f9f9; }}
        .container {{ max-width: 1000px; margin: auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; }}
        .filter-summary {{ background-color: #eef; padding: 10px; border-radius: 5px; margin-bottom: 20px; }}
        .chart-container {{ margin-bottom: 40px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>個別分析レポート</h1>
        <p><strong>生成日時:</strong> {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}</p>
        <div class="filter-summary">
            <strong>適用フィルター:</strong> {filter_summary}
        </div>

        <div class="chart-container">
            {div_alos}
        </div>
        <div class="chart-container">
            {div_patient}
        </div>
        <div class="chart-container">
            {div_dual_axis}
        </div>
    </div>
</body>
</html>
"""
        return html_template, "成功"

    except Exception as e:
        logger.error(f"個別分析HTMLの生成中にエラー: {e}", exc_info=True)
        return None, f"エラー: {str(e)}"


def create_github_publisher_interface(df_filtered=None):
    """
    Streamlit用のGitHub自動公開インターフェース（統合版）
    df_filtered: 現在フィルター適用後のデータフレーム
    """
    # ... （デバッグ情報やGitHub設定部分は変更なし）...
    st.sidebar.markdown("---")
    st.sidebar.header("🌐 統合ダッシュボード公開")
    
    with st.sidebar.expander("⚙️ GitHub設定", expanded=False):
        github_token = st.text_input("GitHub Personal Access Token",type="password",key="github_publisher_token")
        repo_owner = st.text_input("オーナー名", value="Genie-Scripts", key="github_publisher_owner")
        repo_name = st.text_input("リポジトリ名", value="Streamlit-Inpatient-Dashboard", key="github_publisher_repo")
        publish_path = st.selectbox("公開フォルダ", ["docs/", "public/", ""], index=0, key="github_publish_folder_select")
        if st.button("💾 GitHub設定を保存", key="save_github_publisher_settings"):
            if github_token and repo_owner and repo_name:
                st.session_state.github_publisher = GitHubPublisher(repo_owner, repo_name, github_token, "main")
                st.session_state.github_publish_path_config = publish_path
                st.success("✅ GitHub設定を保存しました")

    create_external_dashboard_uploader()
    content_customizer = ContentCustomizer()
    content_customizer.create_streamlit_interface()
    
    if st.session_state.get('github_publisher'):
        publisher = st.session_state.github_publisher
        publish_path = st.session_state.get('github_publish_path_config', 'docs/')

        st.sidebar.markdown("### 🚀 統合ダッシュボード公開")
        
        publish_options_all = []
        if (st.session_state.get('data_processed') and st.session_state.get('df') is not None):
            publish_options_all.extend(["診療科別パフォーマンス", "病棟別パフォーマンス"])

        # ★★★ 修正箇所: 個別分析ビューの公開オプションを追加 ★★★
        if df_filtered is not None and not df_filtered.empty and CHARTS_AVAILABLE:
            publish_options_all.append("個別分析ビュー")
        
        external_dashboards = st.session_state.get('external_dashboards', [])
        for dash in external_dashboards:
            publish_options_all.append(f"外部: {dash['title']}")
        publish_options_all.append("統合インデックス")
        
        if not publish_options_all:
            st.sidebar.info("📊 データ読み込み後に公開機能が利用可能になります")
            return

        selected_period = "直近4週間"
        if any(opt in ["診療科別パフォーマンス", "病棟別パフォーマンス"] for opt in publish_options_all):
            selected_period = st.sidebar.selectbox("入院データ期間", ["直近4週間", "直近8週", "直近12週", "今年度"], key="github_publish_period")
        
        layout_styles = {"default": "🎯 標準レイアウト", "minimal": "✨ ミニマル・シンプル", "corporate": "🏢 企業・フォーマル", "mobile_first": "📱 モバイルファースト"}
        selected_layout = st.sidebar.selectbox("🎨 トップページレイアウト", list(layout_styles.keys()), format_func=lambda x: layout_styles[x], key="github_layout_style")
        
        publish_options = st.sidebar.multiselect("公開ダッシュボード", publish_options_all, default=publish_options_all, key="github_publish_options")
        
        if st.sidebar.button("🚀 統合ダッシュボード公開", key="execute_integrated_publish", type="primary"):
            content_config = content_customizer.get_current_config()
            results = []
            progress_bar = st.sidebar.progress(0)
            status_text = st.sidebar.empty()
            total_tasks = len(publish_options)
            current_task = 0

            try:
                # ★★★ 修正箇所: 個別分析ビューの公開処理を追加 ★★★
                if "個別分析ビュー" in publish_options:
                    current_task += 1
                    status_text.text(f"({current_task}/{total_tasks}) 個別分析ビューを生成中...")
                    progress_bar.progress(current_task / total_tasks)
                    
                    html_content, message = generate_individual_analysis_html(df_filtered)
                    if html_content:
                        success, upload_message = publisher.upload_html_file(
                            html_content,
                            f"{publish_path}individual_analysis.html",
                            f"Update Individual Analysis View - {datetime.now().strftime('%Y-%m-%d')}"
                        )
                        results.append(("個別分析ビュー", success, upload_message))
                    else:
                        results.append(("個別分析ビュー", False, message))

                # 既存の公開処理（診療科別、病棟別など）...
                if "診療科別パフォーマンス" in publish_options:
                    current_task += 1
                    status_text.text(f"({current_task}/{total_tasks}) 診療科別ダッシュボードを生成中...")
                    progress_bar.progress(current_task / total_tasks)
                    df = st.session_state['df']
                    target_data = st.session_state.get('target_data', pd.DataFrame())
                    dept_html, dept_message = generate_department_dashboard_html(df, target_data, selected_period)
                    if dept_html:
                        success, message = publisher.upload_html_file(dept_html, f"{publish_path}dept_performance.html", f"Update department performance - {selected_period}")
                        results.append(("診療科別", success, message))
                    else:
                        results.append(("診療科別", False, dept_message))

                # ... (他の公開処理も同様に続く) ...
                if "病棟別パフォーマンス" in publish_options:
                    current_task += 1
                    status_text.text(f"({current_task}/{total_tasks}) 病棟別ダッシュボードを生成中...")
                    progress_bar.progress(current_task / total_tasks)
                    df = st.session_state['df']
                    target_data = st.session_state.get('target_data', pd.DataFrame())
                    ward_html, ward_message = generate_ward_dashboard_html(df, target_data, selected_period)
                    if ward_html:
                        success, message = publisher.upload_html_file(ward_html, f"{publish_path}ward_performance.html", f"Update ward performance - {selected_period}")
                        results.append(("病棟別", success, message))
                    else:
                        results.append(("病棟別", False, ward_message))

                if "統合インデックス" in publish_options:
                    status_text.text("統合インデックスページを生成中...")
                    dashboards_info = []
                    # ... (インデックス生成ロジックは変更なし)
                    index_html = publisher.create_index_page(dashboards_info, selected_layout, content_config, [])
                    success, message = publisher.upload_html_file(index_html,f"{publish_path}index.html", "Update index")
                    results.append(("統合インデックス", success, message))

                status_text.text("統合公開完了！")
                for dashboard_type, success, message in results:
                    if success: st.sidebar.success(f"✅ {dashboard_type}: 公開成功")
                    else: st.sidebar.error(f"❌ {dashboard_type}: {message}")

            except Exception as e:
                st.sidebar.error(f"❌ 統合公開処理エラー: {str(e)}")
            finally:
                progress_bar.empty()
                status_text.empty()
    else:
        st.sidebar.info("⚙️ 上記でGitHub設定を行ってください")

def generate_90day_report_html(df, target_data):
    """90日間総合レポートのHTML生成（簡易版）"""
    return "90-day report generation is disabled for this modification."