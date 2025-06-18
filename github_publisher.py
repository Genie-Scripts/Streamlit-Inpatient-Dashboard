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
            # ファイル存在確認
            file_url = f"{self.base_url}/contents/{file_path}"
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # 既存ファイルのSHA取得（更新時に必要）
            response = requests.get(file_url, headers=headers)
            sha = None
            if response.status_code == 200:
                sha = response.json()["sha"]
            
            # ファイル内容をBase64エンコード
            content_encoded = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
            
            # コミットメッセージ
            if not commit_message:
                commit_message = f"Update dashboard: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            # アップロードデータ
            data = {
                "message": commit_message,
                "content": content_encoded,
                "branch": self.branch
            }
            
            # 既存ファイルの場合はSHAを追加
            if sha:
                data["sha"] = sha
            
            # ファイルアップロード
            response = requests.put(file_url, json=data, headers=headers)
            
            if response.status_code in [200, 201]:
                return True, f"Successfully uploaded: {file_path}"
            else:
                return False, f"Upload failed: {response.status_code} - {response.text}"
                
        except Exception as e:
            return False, f"Error uploading file: {str(e)}"
    
    def create_index_page(self, dashboards_info):
        """ダッシュボード一覧のインデックスページを生成"""
        dashboard_links = ""
        for dashboard in dashboards_info:
            update_time = dashboard.get('update_time', '不明')
            dashboard_links += f"""
            <div class="dashboard-card">
                <h3>{dashboard['title']}</h3>
                <p>{dashboard['description']}</p>
                <p class="update-time">最終更新: {update_time}</p>
                <a href="{dashboard['file']}" class="dashboard-link">ダッシュボードを開く</a>
            </div>
            """
        
        html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>病院パフォーマンスダッシュボード</title>
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
            margin-bottom: 30px;
            font-size: 2em;
        }}
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 40px;
            font-size: 1.1em;
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
        .qr-info {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 30px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .qr-info h2 {{
            color: #293a27;
            margin-bottom: 15px;
        }}
        .qr-info .url {{
            background: #f8f9fa;
            padding: 12px;
            border-radius: 6px;
            font-family: monospace;
            color: #333;
            margin: 15px 0;
            word-break: break-all;
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
        <h1>🏥 病院パフォーマンスダッシュボード</h1>
        <p class="subtitle">スマートフォン対応・リアルタイム更新</p>
        
        <div class="qr-info">
            <h2>📱 スマートフォンでのアクセス</h2>
            <p>以下のURLをQRコードにして職員に配布できます</p>
            <div class="url">https://{self.repo_owner}.github.io/{self.repo_name}/</div>
            <p style="color: #666; font-size: 0.9em;">
                ブックマーク推奨 | 自動更新 | 個人情報なし
            </p>
        </div>
        
        <div class="features">
            <div class="feature">
                <div class="feature-icon">📊</div>
                <h4>リアルタイム指標</h4>
                <p>最新の病院パフォーマンス指標</p>
            </div>
            <div class="feature">
                <div class="feature-icon">📱</div>
                <h4>モバイル最適化</h4>
                <p>スマートフォンで快適に閲覧</p>
            </div>
            <div class="feature">
                <div class="feature-icon">🔄</div>
                <h4>自動更新</h4>
                <p>データは定期的に自動更新</p>
            </div>
            <div class="feature">
                <div class="feature-icon">🔒</div>
                <h4>プライバシー保護</h4>
                <p>個人情報は含まれません</p>
            </div>
        </div>
        
        <div class="dashboard-grid">
            {dashboard_links}
        </div>
        
        <footer style="text-align: center; margin-top: 50px; color: #999; border-top: 1px solid #eee; padding-top: 30px;">
            <p>最終更新: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
            <p>🏥 病院パフォーマンス分析システム</p>
        </footer>
    </div>
</body>
</html>
"""
        return html_content
    
    def get_public_url(self):
        """公開URLを取得"""
        return f"https://{self.repo_owner}.github.io/{self.repo_name}/"

def generate_department_dashboard_html(df, target_data, period="直近4週間"):
    """診療科別ダッシュボードのHTML生成"""
    try:
        from department_performance_tab import get_period_dates, calculate_department_kpis
        from unified_html_export import generate_unified_html_export
        from utils import safe_date_filter
        from config import EXCLUDED_WARDS
        
        # 期間の計算
        start_date, end_date, period_desc = get_period_dates(df, period)
        
        if start_date is None or end_date is None:
            return None, "期間の計算に失敗しました"
        
        # データフィルタリング
        date_filtered_df = safe_date_filter(df, start_date, end_date)
        
        # 除外病棟のフィルタリング
        if '病棟コード' in date_filtered_df.columns and EXCLUDED_WARDS:
            date_filtered_df = date_filtered_df[~date_filtered_df['病棟コード'].isin(EXCLUDED_WARDS)]

        if date_filtered_df.empty:
            return None, "データがありません"
        
        # 診療科列の特定
        possible_cols = ['部門名', '診療科', '診療科名']
        dept_col = next((c for c in possible_cols if c in date_filtered_df.columns), None)
        if dept_col is None:
            return None, "診療科列が見つかりません"

        # KPIデータの計算
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
        
        # HTMLの生成
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
        
        # 期間の計算
        start_date, end_date, period_desc = get_period_dates(df, period)
        
        if start_date is None or end_date is None:
            return None, "期間の計算に失敗しました"
        
        # データフィルタリング
        date_filtered_df = safe_date_filter(df, start_date, end_date)
        
        if date_filtered_df.empty:
            return None, "データがありません"
        
        # 病棟列の特定
        possible_cols = ['病棟コード', '病棟名', '病棟']
        ward_col = next((c for c in possible_cols if c in date_filtered_df.columns), None)
        if ward_col is None:
            return None, "病棟列が見つかりません"

        # KPIデータの計算
        unique_wards = date_filtered_df[ward_col].unique()
        # 除外病棟をフィルタリング
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
        
        # HTMLの生成
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
    """Streamlit用のGitHub自動公開インターフェース"""
    
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
            key="github_publish_path"
        )
        
        if st.button("💾 GitHub設定を保存", key="save_github_publisher_settings"):
            if github_token and repo_owner and repo_name:
                st.session_state.github_publisher = GitHubPublisher(
                    repo_owner, repo_name, github_token, "main"
                )
                st.session_state.github_publish_path = publish_path
                st.success("✅ GitHub設定を保存しました")
                
                # GitHub Pages設定の案内
                st.info(f"""
                **GitHub Pages設定**  
                1. GitHubリポジトリ → Settings → Pages  
                2. Source: Deploy from a branch  
                3. Branch: main / {publish_path or 'root'}  
                
                **公開URL:** https://{repo_owner}.github.io/{repo_name}/
                """)
            else:
                st.error("すべての項目を入力してください")
    
    # 公開機能（データが読み込まれている場合のみ）
    if (st.session_state.get('github_publisher') and 
        st.session_state.get('data_processed') and 
        st.session_state.get('df') is not None):
        
        st.sidebar.markdown("### 🚀 ダッシュボード公開")
        
        # 公開する期間の選択
        period_options = ["直近4週間", "直近8週", "直近12週", "今年度"]
        selected_period = st.sidebar.selectbox(
            "公開データ期間",
            period_options,
            index=0,
            help="職員向けダッシュボードに使用するデータ期間",
            key="github_publish_period"
        )
        
        # 公開するダッシュボードの選択
        publish_options = st.sidebar.multiselect(
            "公開ダッシュボード",
            ["診療科別パフォーマンス", "病棟別パフォーマンス", "統合インデックス"],
            default=["診療科別パフォーマンス", "病棟別パフォーマンス", "統合インデックス"],
            help="職員向けに公開するダッシュボード",
            key="github_publish_options"
        )
        
        # 自動公開実行
        if st.sidebar.button("🚀 GitHub Pagesに自動公開", key="execute_github_publish", type="primary"):
            
            publisher = st.session_state.github_publisher
            publish_path = st.session_state.get('github_publish_path', 'docs/')
            df = st.session_state['df']
            target_data = st.session_state.get('target_data', pd.DataFrame())
            
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
                
                # インデックスページ
                if "統合インデックス" in publish_options:
                    status_text.text("インデックスページを生成中...")
                    
                    dashboards_info = []
                    
                    if "診療科別パフォーマンス" in publish_options:
                        dashboards_info.append({
                            "title": "診療科別パフォーマンス",
                            "description": f"各診療科の入院患者数、新入院患者数、平均在院日数の実績と目標達成率（{selected_period}）",
                            "file": "dept_performance.html",
                            "update_time": datetime.now().strftime('%Y/%m/%d %H:%M')
                        })
                    
                    if "病棟別パフォーマンス" in publish_options:
                        dashboards_info.append({
                            "title": "病棟別パフォーマンス",
                            "description": f"各病棟の入院患者数、新入院患者数、平均在院日数の実績と目標達成率（{selected_period}）",
                            "file": "ward_performance.html",
                            "update_time": datetime.now().strftime('%Y/%m/%d %H:%M')
                        })
                    
                    index_html = publisher.create_index_page(dashboards_info)
                    
                    success, message = publisher.upload_html_file(
                        index_html,
                        f"{publish_path}index.html",
                        f"Update dashboard index page - {selected_period}"
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
                    
                    # 成功時の案内
                    st.sidebar.success("🎉 全ての公開が完了しました！")
                    st.sidebar.markdown("### 📱 職員への配布方法")
                    
                    # URLの表示
                    st.sidebar.text_input(
                        "公開URL（QRコード生成用）",
                        value=public_url,
                        key="github_public_url_display"
                    )
                    
                    st.sidebar.markdown("""
                    **QRコード生成・配布手順:**
                    1. 上記URLをコピー
                    2. [QRコード生成サイト](https://www.qr-code-generator.com/)でQRコード作成
                    3. 院内掲示板やメールで職員に配布
                    
                    **特徴:**
                    - 📱 スマートフォン最適化
                    - 🔄 自動更新（再公開時）
                    - 🔒 個人情報なし
                    - 📊 指標切り替え可能
                    """)
                    
                    # QRコード生成サイトへのリンク
                    st.sidebar.markdown("**おすすめQRコード生成サイト:**")
                    st.sidebar.markdown("- [QR Code Generator](https://www.qr-code-generator.com/)")
                    st.sidebar.markdown("- [QRのススメ](https://qr.quel.jp/)")
                
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