# github_publisher.py (修正版)

import os
import json
import requests
import base64
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import logging
# ★★★ 修正箇所: 必要なモジュールを追加 ★★★
from config import EXCLUDED_WARDS
import numpy as np
import re

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
            # ファイル名の安全化
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
            # セッションステートから外部ダッシュボード情報を取得
            return st.session_state.get('external_dashboards', [])
        except:
            return []
    
    def _get_relative_path(self, file_path, dashboard_type=None):
        """相対パスを正しく取得する"""
        # ファイル名のみの場合（外部ダッシュボード）
        if '/' not in file_path:
            return file_path
        
        # すでにパスが含まれている場合
        if file_path.startswith('docs/'):
            return file_path.replace('docs/', '')
        
        return file_path
    
    def create_index_page(self, dashboards_info, layout_style="default", content_config=None, external_dashboards=None):
        """ダッシュボード一覧のインデックスページを生成（外部ダッシュボード対応）"""
        
        if content_config is None:
            content_config = ContentCustomizer().default_content
        
        # 外部ダッシュボード情報を統合
        all_dashboards = dashboards_info.copy() if dashboards_info else []
        if external_dashboards:
            # 外部ダッシュボードのファイルパスを修正
            for ext_dash in external_dashboards:
                # ファイルパスからdocs/を削除
                if 'file' in ext_dash and ext_dash['file'].startswith('docs/'):
                    ext_dash['file'] = ext_dash['file'].replace('docs/', '')
            all_dashboards.extend(external_dashboards)
        
        # デバッグ: ダッシュボード総数をログ
        logger.info(f"Total dashboards: {len(all_dashboards)}")
        for dash in all_dashboards:
            logger.info(f"Dashboard: {dash.get('title', 'No title')} - {dash.get('file', 'No file')}")
            
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
            # ダッシュボードタイプに応じた説明文の選択
            if 'department' in dashboard.get('file', '').lower() or '診療科' in dashboard.get('title', ''):
                description = content_config.get('department_dashboard_description', dashboard.get('description', ''))
            elif 'ward' in dashboard.get('file', '').lower() or '病棟' in dashboard.get('title', ''):
                description = content_config.get('ward_dashboard_description', dashboard.get('description', ''))
            elif dashboard.get('type') == 'external':
                description = dashboard.get('description', '外部システムから提供されるダッシュボード')
            else:
                description = dashboard.get('description', '')
                
            update_time = dashboard.get('update_time', '不明')
            
            # 外部ダッシュボードの場合はアイコンを追加
            title_with_icon = dashboard['title']
            if dashboard.get('type') == 'external':
                title_with_icon = f"🔗 {dashboard['title']}"
            
            # 相対パスの正しい処理
            file_path = self._get_relative_path(dashboard['file'], dashboard.get('type'))
            
            dashboard_links += f"""
            <div class="dashboard-card">
                <h3>{title_with_icon}</h3>
                <p>{description}</p>
                <p class="update-time">最終更新: {update_time}</p>
                <a href="{file_path}" class="dashboard-link">{button_text}</a>
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
        return f"https://{self.repo_owner}.github.io/{self.repo_name}/"

class ContentCustomizer:
    def __init__(self):
        self.default_content = {"main_title": "🏥 統合ダッシュボード", "subtitle": "入院管理・手術分析・スマートフォン対応", "show_features": True, "features": [{"icon": "📊", "title": "入院パフォーマンス", "description": "病棟・診療科別の入院指標"}, {"icon": "🏥", "title": "手術分析", "description": "手術実績と効率性の分析"}, {"icon": "📱", "title": "モバイル最適化", "description": "スマートフォンで快適に閲覧"}, {"icon": "🔄", "title": "自動更新", "description": "データは定期的に自動更新"}], "department_dashboard_description": "各診療科の入院患者数、新入院患者数、平均在院日数の実績と目標達成率", "ward_dashboard_description": "各病棟の入院患者数、新入院患者数、平均在院日数の実績と目標達成率", "footer_text": "🏥 病院統合分析システム", "footer_note": "", "dashboard_button_text": "ダッシュボードを開く"}
        self.presets = {"hospital": {"main_title": "🏥 [病院名] 統合ダッシュボード", "subtitle": "入院・手術分析で医療の質向上を目指して", "footer_text": "🏥 [病院名] 医療情報統合システム", "footer_note": "お問い合わせ：情報システム部門（内線xxxx）"}, "executive": {"main_title": "経営統合ダッシュボード", "subtitle": "Hospital Performance & Surgery Analytics", "footer_text": "Hospital Integrated Intelligence System", "footer_note": "Confidential - Internal Use Only"}, "friendly": {"main_title": "📊 みんなの統合ダッシュボード", "subtitle": "入院も手術も！スマホで簡単チェック", "footer_text": "🌟 みんなで作る より良い病院", "footer_note": "質問があったら情報システム課まで気軽にどうぞ♪"}}
    
    def create_streamlit_interface(self):
        """Streamlitで内容編集インターフェースを作成（統合版）"""
        
        # プリセット選択
        st.sidebar.markdown("---")
        st.sidebar.markdown("### ⚡ プリセット選択")
        
        preset_options = {
            "custom": "カスタム（手動設定）",
            "hospital": "🏥 病院標準",
            "executive": "🏢 経営層向け",
            "friendly": "👥 職員親近"
        }
        
        selected_preset = st.sidebar.selectbox(
            "テンプレート選択",
            list(preset_options.keys()),
            format_func=lambda x: preset_options[x],
            index=0,
            key="content_preset_selection",
            help="定型テンプレートから選択するか、カスタムで個別設定"
        )
        
        # プリセットが選択された場合の初期値を取得
        if selected_preset != "custom" and selected_preset in self.presets:
            preset_values = self.presets[selected_preset]
        else:
            preset_values = {}
        
        # 実際の入力フィールド
        st.sidebar.markdown("### 📝 トップページ内容編集")
        
        # ヘッダー部分
        st.sidebar.markdown("**🏠 ヘッダー部分**")
        main_title = st.sidebar.text_input(
            "メインタイトル",
            value=preset_values.get('main_title', st.session_state.get('content_main_title', self.default_content["main_title"])),
            key="content_main_title",
            help="トップページの大見出し"
        )
        
        subtitle = st.sidebar.text_input(
            "サブタイトル",
            value=preset_values.get('subtitle', st.session_state.get('content_subtitle', self.default_content["subtitle"])),
            key="content_subtitle",
            help="タイトル下の説明文"
        )
        
        # 機能紹介部分
        st.sidebar.markdown("**✨ 機能紹介部分**")
        show_features = st.sidebar.checkbox(
            "機能紹介セクションを表示",
            value=st.session_state.get('content_show_features', True),
            key="content_show_features"
        )
        
        if show_features:
            # 機能入力
            st.sidebar.markdown("**主要機能設定**")
            for i in range(4):
                default_feature = self.default_content["features"][i] if i < len(self.default_content["features"]) else {"icon": "📊", "title": "", "description": ""}
                
                col1, col2 = st.sidebar.columns([1, 2])
                with col1:
                    st.text_input(
                        f"機能{i+1}アイコン",
                        value=st.session_state.get(f'content_feature_{i}_icon', default_feature["icon"]),
                        key=f"content_feature_{i}_icon"
                    )
                with col2:
                    st.text_input(
                        f"機能{i+1}タイトル",
                        value=st.session_state.get(f'content_feature_{i}_title', default_feature["title"]),
                        key=f"content_feature_{i}_title"
                    )
                
                st.text_area(
                    f"機能{i+1}説明",
                    value=st.session_state.get(f'content_feature_{i}_description', default_feature["description"]),
                    key=f"content_feature_{i}_description",
                    height=30
                )
        
        # ダッシュボード説明
        st.sidebar.markdown("**📊 ダッシュボード説明**")
        dept_description = st.sidebar.text_area(
            "診療科別ダッシュボード説明",
            value=st.session_state.get('content_dept_description', self.default_content["department_dashboard_description"]),
            key="content_dept_description",
            height=50
        )
        
        ward_description = st.sidebar.text_area(
            "病棟別ダッシュボード説明",
            value=st.session_state.get('content_ward_description', self.default_content["ward_dashboard_description"]),
            key="content_ward_description",
            height=50
        )
        
        # フッター部分
        st.sidebar.markdown("**🔻 フッター部分**")
        footer_text = st.sidebar.text_input(
            "フッターメインテキスト",
            value=preset_values.get('footer_text', st.session_state.get('content_footer_text', self.default_content["footer_text"])),
            key="content_footer_text"
        )
        
        footer_note = st.sidebar.text_area(
            "フッター追加メモ",
            value=preset_values.get('footer_note', st.session_state.get('content_footer_note', self.default_content["footer_note"])),
            key="content_footer_note",
            height=50,
            help="病院名や部署名など"
        )
        
        # ボタンテキスト
        st.sidebar.markdown("**🔘 ボタン・リンク**")
        button_text = st.sidebar.text_input(
            "ダッシュボードボタンテキスト",
            value=st.session_state.get('content_button_text', self.default_content["dashboard_button_text"]),
            key="content_button_text"
        )
        
        # 設定保存
        if st.sidebar.button("💾 内容設定を保存", key="save_content_settings", type="primary"):
            self._save_current_content()
            st.sidebar.success("✅ 内容設定を保存しました")
    
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

def create_external_dashboard_uploader():
    """外部ダッシュボード（手術分析など）アップロード機能"""
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔗 外部ダッシュボード追加")
    
    with st.sidebar.expander("📤 HTMLファイルアップロード", expanded=False):
        st.markdown("**手術分析アプリなど、他システムで生成されたダッシュボードを追加**")
        
        # アップロード方式選択
        upload_method = st.radio(
            "アップロード方式",
            ["HTMLファイル直接アップロード", "HTMLコード貼り付け"],
            key="external_upload_method"
        )
        
        if upload_method == "HTMLファイル直接アップロード":
            # ファイルアップロード
            uploaded_file = st.file_uploader(
                "HTMLファイルを選択",
                type=['html'],
                help="手術分析アプリなどで生成されたHTMLファイル",
                key="external_html_file"
            )
            
            if uploaded_file:
                try:
                    html_content = uploaded_file.read().decode('utf-8')
                    st.success(f"✅ ファイル読み込み完了: {uploaded_file.name}")
                    st.session_state.external_html_content = html_content
                    st.session_state.external_suggested_filename = uploaded_file.name
                except Exception as e:
                    st.error(f"❌ ファイル読み込みエラー: {str(e)}")
        
        else:  # HTMLコード貼り付け
            html_content = st.text_area(
                "HTMLコードを貼り付け",
                height=200,
                help="手術分析アプリなどで生成されたHTMLコード全体",
                key="external_html_code"
            )
            
            if html_content:
                st.session_state.external_html_content = html_content
                st.session_state.external_suggested_filename = "custom_dashboard.html"
        
        # ダッシュボード情報入力
        if st.session_state.get('external_html_content'):
            st.markdown("**📝 ダッシュボード情報**")
            
            dashboard_title = st.text_input(
                "ダッシュボードタイトル",
                value="手術分析ダッシュボード",
                key="external_dashboard_title",
                help="トップページに表示されるタイトル"
            )
            
            dashboard_description = st.text_area(
                "説明文",
                value="手術実績、手術時間、効率性指標の分析結果",
                key="external_dashboard_description",
                height=60,
                help="トップページに表示される説明文"
            )
            
            filename = st.text_input(
                "ファイル名",
                value=st.session_state.get('external_suggested_filename', 'surgery_analysis.html'),
                key="external_filename",
                help="GitHub上に保存されるファイル名（.html自動追加）"
            )
            
            # アップロード実行
            if st.button("🚀 外部ダッシュボードを追加", key="upload_external_dashboard", type="primary"):
                
                if st.session_state.get('github_publisher'):
                    publisher = st.session_state.github_publisher
                    
                    # ファイル名の安全化（upload_external_htmlと同じ処理）
                    safe_filename = filename.lower().replace(' ', '_').replace('　', '_')
                    if not safe_filename.endswith('.html'):
                        safe_filename += '.html'
                    
                    # HTMLアップロード
                    success, message = publisher.upload_external_html(
                        st.session_state.external_html_content,
                        filename,
                        dashboard_title
                    )
                    
                    if success:
                        # 外部ダッシュボード情報をセッションに保存
                        external_dashboards = st.session_state.get('external_dashboards', [])
                        
                        # 既存のダッシュボード情報を更新または追加
                        updated = False
                        for i, dash in enumerate(external_dashboards):
                            if dash['file'] == safe_filename or dash['title'] == dashboard_title:
                                external_dashboards[i] = {
                                    "title": dashboard_title,
                                    "description": dashboard_description,
                                    "file": safe_filename,  # docs/プレフィックスなしで保存
                                    "type": "external",
                                    "update_time": datetime.now().strftime('%Y/%m/%d %H:%M')
                                }
                                updated = True
                                break
                        
                        if not updated:
                            external_dashboards.append({
                                "title": dashboard_title,
                                "description": dashboard_description,
                                "file": safe_filename,  # docs/プレフィックスなしで保存
                                "type": "external",
                                "update_time": datetime.now().strftime('%Y/%m/%d %H:%M')
                            })
                        
                        st.session_state.external_dashboards = external_dashboards
                        
                        st.success(f"✅ 外部ダッシュボード追加成功: {dashboard_title}")
                        st.info("💡 次回の統合公開時に、このダッシュボードもインデックスページに含まれます")
                        
                        # 入力内容をクリア
                        st.session_state.external_html_content = ""
                        st.rerun()
                    else:
                        st.error(f"❌ アップロード失敗: {message}")
                
                else:
                    st.error("❌ GitHub設定が必要です")
    
    # 登録済み外部ダッシュボード一覧
    external_dashboards = st.session_state.get('external_dashboards', [])
    st.sidebar.info(f"登録済み外部ダッシュボード総数: {len(external_dashboards)}")
    
    if external_dashboards:
        with st.sidebar.expander("📋 登録済み外部ダッシュボード", expanded=False):
            for i, dash in enumerate(external_dashboards):
                st.markdown(f"**{dash['title']}**")
                st.markdown(f"ファイル: `{dash['file']}`")
                st.markdown(f"更新: {dash.get('update_time', '不明')}")
                
                if st.button(f"🗑️ 削除", key=f"delete_external_{i}"):
                    external_dashboards.pop(i)
                    st.session_state.external_dashboards = external_dashboards
                    st.rerun()
                
                st.markdown("---")
    else:
        st.sidebar.warning("⚠️ 外部ダッシュボードが登録されていません")

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

def create_github_publisher_interface(df_filtered=None):  # ★★★ 修正: 引数を追加 ★★★
    """Streamlit用のGitHub自動公開インターフェース（統合版）"""
    
    # デバッグ情報表示（開発用）
    with st.sidebar.expander("🐛 デバッグ情報", expanded=False):
        st.markdown("**セッションステート内容:**")
        if 'external_dashboards' in st.session_state:
            st.json(st.session_state.external_dashboards)
        else:
            st.warning("external_dashboardsが存在しません")
        
        # テスト用ボタン
        if st.button("🧪 テスト用外部ダッシュボード追加", key="add_test_external"):
            if 'external_dashboards' not in st.session_state:
                st.session_state.external_dashboards = []
            
            test_dashboard = {
                "title": "手術分析ダッシュボード",
                "description": "手術実績、手術時間、効率性指標の分析結果",
                "file": "surgery_analysis.html",
                "type": "external",
                "update_time": datetime.now().strftime('%Y/%m/%d %H:%M')
            }
            st.session_state.external_dashboards.append(test_dashboard)
            st.success("テスト用外部ダッシュボードを追加しました")
            st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.header("🌐 統合ダッシュボード公開")
    
    # GitHub設定
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
                    
                    current_task += 1
                    progress_bar.progress(current_task / total_tasks)
                
                # 外部ダッシュボード処理（既にアップロード済みなのでスキップ）
                external_count = 0
                for option in publish_options:
                    if option.startswith("外部: "):
                        external_count += 1
                        current_task += 1
                        progress_bar.progress(current_task / total_tasks)
                
                if external_count > 0:
                    results.append(("外部ダッシュボード", True, f"{external_count}件の外部ダッシュボードを統合"))
                
                # 統合インデックスページ
                if "統合インデックス" in publish_options:
                    status_text.text("統合インデックスページを生成中...")
                    
                    dashboards_info = []
                    
                    # 入院ダッシュボード情報追加
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
                    
                    # 外部ダッシュボード情報追加（デバッグ情報付き）
                    external_included = []
                    st.sidebar.info(f"選択された項目: {publish_options}")
                    st.sidebar.info(f"登録済み外部ダッシュボード: {[d['title'] for d in external_dashboards]}")
                    
                    for option in publish_options:
                        if option.startswith("外部: "):
                            # すべての外部ダッシュボードを含める（省略記号の問題を回避）
                            external_included = external_dashboards.copy()
                            break
                    
                    # デバッグ情報
                    st.sidebar.info(f"外部ダッシュボード数: {len(external_included)}")
                    for ext in external_included:
                        st.sidebar.info(f"外部: {ext['title']} - {ext['file']}")
                    
                    # 統合インデックスページ生成
                    index_html = publisher.create_index_page(
                        dashboards_info, 
                        selected_layout, 
                        content_config, 
                        external_included
                    )
                    
                    success, message = publisher.upload_html_file(
                        index_html,
                        f"{publish_path}index.html",
                        f"Update integrated dashboard index - {selected_period} - {layout_styles[selected_layout]}"
                    )
                    results.append(("統合インデックス", success, message))
                    
                    current_task += 1
                    progress_bar.progress(1.0)
                
                status_text.text("統合公開完了！")
                
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
                    
                    st.sidebar.success("🎉 統合ダッシュボード公開完了！")
                    st.sidebar.markdown("### 📱 職員への配布方法")
                    
                    st.sidebar.text_input(
                        "統合公開URL（QRコード生成用）",
                        value=public_url,
                        key="github_integrated_url_display"
                    )
                    
                    st.sidebar.markdown(f"""
                    **✨ 統合公開内容:**
                    - 入院ダッシュボード + 手術分析
                    - レイアウト: {layout_styles[selected_layout]}
                    - カスタム内容適用済み
                    - 期間: {selected_period}
                    
                    **配布手順:**
                    1. [QRコード生成](https://www.qr-code-generator.com/)
                    2. 院内掲示板・メール配布
                    3. 職員向け説明会で案内
                    """)
                
            except Exception as e:
                st.sidebar.error(f"❌ 統合公開処理エラー: {str(e)}")
                logger.error(f"GitHub統合公開エラー: {e}", exc_info=True)
            
            finally:
                progress_bar.empty()
                status_text.empty()
        
        # 90日間総合レポート生成機能
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📑 90日間総合レポート")
        
        with st.sidebar.expander("📊 レポート生成", expanded=False):
            st.markdown("**90日間の包括的分析レポート**")
            st.markdown("- 全体分析（KPI、推移グラフ、月別サマリー）")
            st.markdown("- 診療科別分析（比較、詳細データ、トレンド）")
            st.markdown("- 病棟別分析（稼働率、利用率推移、回転率）")
            
            if st.button("🚀 90日間レポート生成・公開", key="generate_90day_report", type="primary"):
                
                if st.session_state.get('data_processed') and st.session_state.get('df') is not None:
                    df = st.session_state['df']
                    target_data = st.session_state.get('target_data', pd.DataFrame())
                    
                    with st.spinner("90日間レポートを生成中..."):
                        try:
                            # レポートHTML生成（簡易版）
                            html_report = generate_90day_report_html(df, target_data)
                            
                            if html_report:
                                # GitHubにアップロード
                                success, message = publisher.upload_html_file(
                                    html_report,
                                    f"{publish_path}comprehensive_report_90days.html",
                                    f"Update 90-day comprehensive report - {datetime.now().strftime('%Y-%m-%d')}"
                                )
                                
                                if success:
                                    st.success("✅ 90日間レポート生成・公開成功！")
                                    
                                    # 外部ダッシュボードとして登録
                                    external_dashboards = st.session_state.get('external_dashboards', [])
                                    
                                    report_dash = {
                                        "title": "90日間総合レポート",
                                        "description": "全体・診療科別・病棟別の詳細分析（グラフ・テーブル含む）",
                                        "file": "comprehensive_report_90days.html",
                                        "type": "external",
                                        "update_time": datetime.now().strftime('%Y/%m/%d %H:%M')
                                    }
                                    
                                    # 既存のレポートを更新
                                    updated = False
                                    for i, dash in enumerate(external_dashboards):
                                        if dash['title'] == "90日間総合レポート":
                                            external_dashboards[i] = report_dash
                                            updated = True
                                            break
                                    
                                    if not updated:
                                        external_dashboards.append(report_dash)
                                    
                                    st.session_state.external_dashboards = external_dashboards
                                    
                                    public_url = publisher.get_public_url()
                                    st.info(f"""
                                    **📊 レポートURL:**
                                    {public_url}comprehensive_report_90days.html
                                    
                                    **📱 統合インデックスにも自動追加されました**
                                    
                                    **🖨️ PDF保存方法:**
                                    1. 上記URLを開く
                                    2. ブラウザの印刷機能（Ctrl+P）
                                    3. 送信先を「PDFに保存」に設定
                                    """)
                                else:
                                    st.error(f"❌ レポート公開失敗: {message}")
                            else:
                                st.error("❌ レポート生成に失敗しました")
                        
                        except Exception as e:
                            st.error(f"❌ レポート生成エラー: {str(e)}")
                            logger.error(f"90日間レポート生成エラー: {e}", exc_info=True)
                else:
                    st.warning("⚠️ データを読み込んでから実行してください")
    
    else:
        st.sidebar.info("⚙️ 上記でGitHub設定を行ってください")


# ★★★ 修正箇所: PDFジェネレーター風のHTMLレポートを生成する関数に全面的に書き換え ★★★
def generate_90day_report_html(df, target_data):
    """90日間総合レポートのHTML生成（PDFジェネレーター風のレイアウト）"""
    try:
        # --- データ準備 ---
        df_copy = df.copy()
        if '病棟コード' in df_copy.columns and EXCLUDED_WARDS:
            df_copy = df_copy[~df_copy['病棟コード'].isin(EXCLUDED_WARDS)]

        if not pd.api.types.is_datetime64_any_dtype(df_copy['日付']):
            df_copy['日付'] = pd.to_datetime(df_copy['日付'], errors='coerce')
        
        df_copy.dropna(subset=['日付'], inplace=True)
        
        end_date = df_copy['日付'].max()
        start_date = end_date - timedelta(days=89)
        df_90days = df_copy[(df_copy['日付'] >= start_date) & (df_copy['日付'] <= end_date)].copy()
        
        if df_90days.empty:
            return None

        # --- 全体分析データ計算 ---
        total_stats = {}
        if not df_90days.empty:
            total_stats = {
                '平均在院患者数': df_90days.groupby('日付')['在院患者数'].sum().mean(),
                '総入院患者数': df_90days['新入院患者数'].sum(),
                '総退院患者数': df_90days['総退院患者数'].sum(),
                '平均在院日数': df_90days['在院患者数'].sum() / df_90days['総退院患者数'].sum() if df_90days['総退院患者数'].sum() > 0 else 0
            }

        daily_data = df_90days.groupby('日付').agg({
            '在院患者数': 'sum', '新入院患者数': 'sum', '総退院患者数': 'sum'
        }).reset_index()

        # --- 部門別実績データ計算 (pdf_generator.pyロジック参考) ---
        period_definitions = {
            "直近7日": (end_date - timedelta(days=6), end_date),
            "直近14日": (end_date - timedelta(days=13), end_date),
            "直近30日": (end_date - timedelta(days=29), end_date),
            "直近60日": (end_date - timedelta(days=59), end_date),
            "90日間": (start_date, end_date),
        }
        
        unique_depts = sorted(df_90days["診療科名"].unique())
        unique_wards = sorted(df_90days["病棟コード"].astype(str).unique())

        dept_metrics = {dept: {} for dept in unique_depts}
        ward_metrics = {ward: {} for ward in unique_wards}

        for period_label, (start_dt, end_dt) in period_definitions.items():
            period_df = df_90days[(df_90days['日付'] >= start_dt) & (df_90days['日付'] <= end_dt)]
            num_days = period_df['日付'].nunique()
            if num_days == 0: continue

            # 診療科別
            dept_period_stats = period_df.groupby('診療科名')['在院患者数'].sum() / num_days
            for dept, avg_census in dept_period_stats.items():
                dept_metrics[dept][period_label] = avg_census

            # 病棟別
            ward_period_stats = period_df.groupby('病棟コード')['在院患者数'].sum() / num_days
            for ward, avg_census in ward_period_stats.items():
                ward_metrics[ward][period_label] = avg_census

        # --- HTML生成 ---
        
        # 診療科テーブルHTML生成
        dept_table_html = "<table><thead><tr><th>診療科</th>"
        for label in period_definitions.keys():
            dept_table_html += f"<th>{label}</th>"
        dept_table_html += "</tr></thead><tbody>"
        
        # 上位15診療科でソート
        sorted_depts = sorted(unique_depts, key=lambda d: dept_metrics.get(d, {}).get("90日間", 0), reverse=True)[:15]

        for dept in sorted_depts:
            dept_table_html += f"<tr><td>{dept}</td>"
            for period in period_definitions.keys():
                val = dept_metrics.get(dept, {}).get(period)
                dept_table_html += f"<td>{val:.1f}</td>" if pd.notna(val) else "<td>-</td>"
            dept_table_html += "</tr>"
        dept_table_html += "</tbody></table>"
        
        # 病棟テーブルHTML生成
        ward_table_html = "<table><thead><tr><th>病棟</th>"
        for label in period_definitions.keys():
            ward_table_html += f"<th>{label}</th>"
        ward_table_html += "</tr></thead><tbody>"

        # 上位15病棟でソート
        sorted_wards = sorted(unique_wards, key=lambda w: ward_metrics.get(w, {}).get("90日間", 0), reverse=True)[:15]

        for ward in sorted_wards:
            ward_table_html += f"<tr><td>{ward}</td>"
            for period in period_definitions.keys():
                val = ward_metrics.get(ward, {}).get(period)
                ward_table_html += f"<td>{val:.1f}</td>" if pd.notna(val) else "<td>-</td>"
            ward_table_html += "</tr>"
        ward_table_html += "</tbody></table>"

        # グラフ用データ
        dept_chart_data = {dept: dept_metrics.get(dept, {}).get("90日間", 0) for dept in sorted_depts}
        ward_chart_data = {ward: ward_metrics.get(ward, {}).get("90日間", 0) for ward in sorted_wards}

        # メインのHTMLコンテンツ
        html_content = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>入院管理総合レポート - 90日間分析</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Noto Sans JP', -apple-system, BlinkMacSystemFont, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px; border-radius: 10px; margin-bottom: 30px; text-align: center; }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .period {{ font-size: 1.2em; opacity: 0.9; }}
        .nav-section {{ background: white; padding: 15px; border-radius: 10px; margin-bottom: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }}
        .nav-button {{ display: inline-block; padding: 10px 20px; margin: 5px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; transition: all 0.3s; }}
        .nav-button:hover {{ background: #5a67d8; transform: translateY(-2px); }}
        .section {{ background: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .section h2 {{ color: #667eea; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #e2e8f0; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .metric-card {{ background: #f7fafc; padding: 20px; border-radius: 8px; border-left: 4px solid #667eea; }}
        .metric-card h3 {{ font-size: 0.9em; color: #718096; margin-bottom: 5px; }}
        .metric-value {{ font-size: 2em; font-weight: bold; color: #2d3748; }}
        .chart-container {{ position: relative; height: 400px; margin-top: 30px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f7fafc; font-weight: 600; color: #4a5568; text-align: center; }}
        td:first-child {{ font-weight: 500; }}
        td:not(:first-child) {{ text-align: right; }}
        tr:hover {{ background: #f7fafc; }}
        .print-button {{ display: block; width: fit-content; margin: 20px auto; padding: 15px 30px; background: #48bb78; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; cursor: pointer; }}
        @media print {{ .nav-section, .print-button {{ display: none; }} .section {{ page-break-inside: avoid; }} }}
        @media (max-width: 768px) {{ .header h1 {{ font-size: 1.8em; }} .metrics-grid {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏥 入院管理総合レポート</h1>
            <p class="period">分析期間: {start_date.strftime('%Y年%m月%d日')} - {end_date.strftime('%Y年%m月%d日')} (90日間)</p>
        </div>
        <div class="nav-section">
            <a href="#overall" class="nav-button">全体分析</a> <a href="#department" class="nav-button">診療科別分析</a> <a href="#ward" class="nav-button">病棟別分析</a>
        </div>
        
        <div id="overall" class="section">
            <h2>📊 全体分析</h2>
            <div class="metrics-grid">
                <div class="metric-card"><h3>平均在院患者数</h3><div class="metric-value">{total_stats.get('平均在院患者数', 0):.1f}</div></div>
                <div class="metric-card"><h3>総入院患者数</h3><div class="metric-value">{total_stats.get('総入院患者数', 0):,.0f}</div></div>
                <div class="metric-card"><h3>総退院患者数</h3><div class="metric-value">{total_stats.get('総退院患者数', 0):,.0f}</div></div>
                <div class="metric-card"><h3>平均在院日数</h3><div class="metric-value">{total_stats.get('平均在院日数', 0):.1f}日</div></div>
            </div>
            <h3>入院患者数推移（90日間）</h3>
            <div class="chart-container"><canvas id="timeSeriesChart"></canvas></div>
        </div>
        
        <div id="department" class="section">
            <h2>🏥 診療科別分析</h2>
            <h3>診療科別 平均在院患者数</h3>
            {dept_table_html}
            <div class="chart-container"><canvas id="deptChart"></canvas></div>
        </div>
        
        <div id="ward" class="section">
            <h2>🛏️ 病棟別分析</h2>
            <h3>病棟別 平均在院患者数</h3>
            {ward_table_html}
            <div class="chart-container"><canvas id="wardChart"></canvas></div>
        </div>
        
        <button class="print-button" onclick="window.print()">📥 PDFとして保存（印刷）</button>
    </div>
    
    <script>
        // Data for charts
        const dailyLabels = {json.dumps(daily_data['日付'].dt.strftime('%Y-%m-%d').tolist())};
        const dailyInpatients = {json.dumps(daily_data['在院患者数'].tolist())};
        const dailyAdmissions = {json.dumps(daily_data['新入院患者数'].tolist())};
        const dailyDischarges = {json.dumps(daily_data['総退院患者数'].tolist())};
        const deptChartData = {json.dumps(dept_chart_data)};
        const wardChartData = {json.dumps(ward_chart_data)};
        
        // Time Series Chart
        new Chart(document.getElementById('timeSeriesChart'), {{
            type: 'line', data: {{ labels: dailyLabels, datasets: [
                {{ label: '在院患者数', data: dailyInpatients, borderColor: '#667eea', backgroundColor: 'rgba(102, 126, 234, 0.1)', borderWidth: 2, tension: 0.1 }},
                {{ label: '新入院患者数', data: dailyAdmissions, borderColor: '#48bb78', backgroundColor: 'rgba(72, 187, 120, 0.1)', borderWidth: 2, tension: 0.1 }},
                {{ label: '退院患者数', data: dailyDischarges, borderColor: '#f6ad55', backgroundColor: 'rgba(246, 173, 85, 0.1)', borderWidth: 2, tension: 0.1 }}
            ]}}, options: {{ responsive: true, maintainAspectRatio: false, scales: {{ y: {{ beginAtZero: true }} }} }}
        }});
        
        // Department Chart
        new Chart(document.getElementById('deptChart'), {{
            type: 'bar', data: {{ labels: Object.keys(deptChartData), datasets: [{{ label: '平均在院患者数 (90日間)', data: Object.values(deptChartData), backgroundColor: '#667eea' }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: {{ legend: {{ display: false }} }} }}
        }});
        
        // Ward Chart
        new Chart(document.getElementById('wardChart'), {{
            type: 'bar', data: {{ labels: Object.keys(wardChartData), datasets: [{{ label: '平均在院患者数 (90日間)', data: Object.values(wardChartData), backgroundColor: '#764ba2' }}] }},
            options: {{ responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: {{ legend: {{ display: false }} }} }}
        }});
        
        // Smooth scroll
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
            anchor.addEventListener('click', function (e) {{ e.preventDefault(); document.querySelector(this.getAttribute('href')).scrollIntoView({{ behavior: 'smooth' }}); }});
        }});
    </script>
</body>
</html>"""
        
        return html_content
        
    except Exception as e:
        logger.error(f"90日間レポート生成エラー: {e}", exc_info=True)
        return None