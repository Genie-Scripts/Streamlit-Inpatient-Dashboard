import warnings
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import hashlib
import gc
from utils import safe_date_filter

# 既存モジュールからのインポート
try:
    # ALOS分析関連
    from alos_analysis_tab import display_alos_analysis_tab
    
    # 曜日別分析関連
    from dow_analysis_tab import display_dow_analysis_tab
    
    # 個別分析関連
    from individual_analysis_tab import display_individual_analysis_tab
    
    # 予測分析関連
    from forecast_analysis_tab import display_forecast_analysis_tab
    
    # チャート作成関連
    from chart import (
        create_interactive_patient_chart, 
        create_interactive_dual_axis_chart,
        create_forecast_comparison_chart
    )
    
    # PDF生成関連
    from pdf_generator import create_pdf, create_landscape_pdf
    
    # 予測・集計関連
    from forecast import generate_filtered_summaries, create_forecast_dataframe
    
    # KPI計算関連
    from kpi_calculator import calculate_kpis, analyze_kpi_insights
    
    # ユーティリティ関数
    from utils import get_display_name_for_dept
    
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    # フォールバック用のダミー関数を定義
    display_alos_analysis_tab = None
    display_dow_analysis_tab = None
    display_individual_analysis_tab = None
    display_forecast_analysis_tab = None
    create_interactive_patient_chart = None
    create_interactive_dual_axis_chart = None
    create_forecast_comparison_chart = None
    create_pdf = None
    create_landscape_pdf = None
    generate_filtered_summaries = None
    create_forecast_dataframe = None
    calculate_kpis = None
    analyze_kpi_insights = None
    get_display_name_for_dept = None

# ===============================================================================
# メイン関数群
# ===============================================================================
def create_detailed_analysis_tab():
    """詳細分析タブのメイン関数（期間選択分離対応版）"""
    st.header("📈 詳細分析")
    
    # データの確認
    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return
    
    df = st.session_state.get('df')
    if df is None or df.empty:
        st.error("分析対象のデータがありません。")
        return
    
    # グラフ表示用の期間設定を取得（新しい方式）
    graph_period_type = st.session_state.get('graph_period_selector', '直近12ヶ月')
    
    # グラフ用期間の計算
    latest_date = df['日付'].max()
    if graph_period_type == "直近12ヶ月":
        graph_start_date = latest_date - pd.Timedelta(days=365)
    elif graph_period_type == "直近6ヶ月":
        graph_start_date = latest_date - pd.Timedelta(days=180)
    else:  # 直近3ヶ月
        graph_start_date = latest_date - pd.Timedelta(days=90)
    
    graph_end_date = latest_date
    
    # データ開始日より前にならないように調整
    actual_graph_start_date = max(graph_start_date, df['日付'].min())
    
    # 期間でデータをフィルタリング
    df_filtered = safe_date_filter(df, actual_graph_start_date, graph_end_date)
    
    if df_filtered.empty:
        st.warning(f"選択された期間（{actual_graph_start_date.date()} ～ {graph_end_date.date()}）にデータがありません。")
        return
    
    common_config = st.session_state.get('common_config', {})
    
    # 期間情報を明確に表示
    period_days = (pd.to_datetime(graph_end_date) - pd.to_datetime(actual_graph_start_date)).days + 1
    st.info(f"🔍 分析期間: {graph_period_type}（{actual_graph_start_date.date()} ～ {graph_end_date.date()}、{period_days}日間、{len(df_filtered):,}行のデータ）")
    
    # サブタブの作成
    los_tab, weekday_tab, individual_tab = st.tabs([
        "📊 平均在院日数分析", 
        "📅 曜日別入退院分析", 
        "🔍 個別分析"
    ])
    
    # フィルタリング済みデータと期間情報を各セクションに渡す
    with los_tab:
        create_los_analysis_section(df_filtered, actual_graph_start_date, graph_end_date, common_config)
    
    with weekday_tab:
        create_weekday_analysis_section(df_filtered, actual_graph_start_date, graph_end_date, common_config)
    
    with individual_tab:
        # 個別分析は独自の期間選択を持つ場合があるため、全データを渡す
        create_individual_analysis_section(df, actual_graph_start_date, graph_end_date)

def create_data_tables_tab():
    """データテーブルタブのメイン関数（KPI期間対応版）"""
    st.header("📋 データテーブル")
    
    # データの確認
    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return
    
    df = st.session_state.get('df')
    if df is None or df.empty:
        st.error("分析対象のデータがありません。")
        return
    
    # KPI期間設定を使用（データテーブルは短期間の詳細データを見ることが多いため）
    kpi_period_type = st.session_state.get('kpi_period_selector', '直近30日')
    
    # 期間の計算
    latest_date = df['日付'].max()
    if kpi_period_type == "直近30日":
        start_date = latest_date - pd.Timedelta(days=29)
        end_date = latest_date
    elif kpi_period_type == "前月完了分":
        start_date = (latest_date.replace(day=1) - pd.Timedelta(days=1)).replace(day=1)
        end_date = latest_date.replace(day=1) - pd.Timedelta(days=1)
    elif kpi_period_type == "当月実績（月途中）":
        start_date = latest_date.replace(day=1)
        end_date = latest_date
    else:  # 当月予測
        start_date = latest_date.replace(day=1)
        end_date = latest_date
    
    df_filtered = safe_date_filter(df, start_date, end_date)
    st.info(f"🔍 表示期間: {kpi_period_type}（{start_date.date()} ～ {end_date.date()}）")
    
    # サブタブの作成
    ward_table_tab, dept_table_tab = st.tabs([
        "🏥 病棟別データテーブル", 
        "🩺 診療科別データテーブル"
    ])
    
    with ward_table_tab:
        create_ward_table_section(df_filtered)
    
    with dept_table_tab:
        create_department_table_section(df_filtered)

def create_output_prediction_tab():
    """出力・予測タブのメイン関数（期間選択対応版）"""
    st.header("📄 出力・予測")
    
    # データの確認
    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return
    
    # PDF出力用の期間選択UI
    st.markdown("### PDF出力期間設定")
    col1, col2 = st.columns(2)
    
    with col1:
        pdf_period_options = [
            "KPI期間と同じ",
            "グラフ期間と同じ", 
            "カスタム期間"
        ]
        pdf_period_type = st.radio(
            "PDF出力期間",
            pdf_period_options,
            index=1,  # デフォルトはグラフ期間
            key="pdf_period_selector"
        )
    
    with col2:
        if pdf_period_type == "カスタム期間":
            df_for_pdf_dates = st.session_state.get('df') # Ensure it's the original df for min/max
            if df_for_pdf_dates is not None and not df_for_pdf_dates.empty and '日付' in df_for_pdf_dates.columns:
                min_date_dt = df_for_pdf_dates['日付'].min().date()
                max_date_dt = df_for_pdf_dates['日付'].max().date()

                # st.date_input の value は datetime.date を期待
                default_pdf_start_dt = (pd.Timestamp(max_date_dt) - pd.Timedelta(days=90)).date()
                if default_pdf_start_dt < min_date_dt: default_pdf_start_dt = min_date_dt

                pdf_start_date_input = st.date_input(
                    "開始日",
                    value=default_pdf_start_dt, # date型
                    min_value=min_date_dt,
                    max_value=max_date_dt,
                    key="pdf_custom_start"
                )
                pdf_end_date_input = st.date_input(
                    "終了日",
                    value=max_date_dt, # date型
                    min_value=pdf_start_date_input, # 選択された開始日以降
                    max_value=max_date_dt,
                    key="pdf_custom_end"
                )
                # 後続処理のためにTimestampに変換して保持するならここで
                # st.session_state.pdf_actual_start_date = pd.to_datetime(pdf_start_date_input).normalize()
                # st.session_state.pdf_actual_end_date = pd.to_datetime(pdf_end_date_input).normalize()
                # これらを実際に safe_date_filter や PDF生成関数に渡す
            else:
                st.warning("データが読み込まれていません")
                # pdf_start_date = None # 変数名が衝突しないように
                # pdf_end_date = None
        else:
            # 選択された期間タイプに応じて期間を設定
            if pdf_period_type == "KPI期間と同じ":
                # KPI期間の設定を使用
                kpi_period_type = st.session_state.get('kpi_period_selector', '直近30日')
                st.info(f"KPI期間（{kpi_period_type}）を使用します")
            else:  # グラフ期間と同じ
                graph_period_type = st.session_state.get('graph_period_selector', '直近12ヶ月')
                st.info(f"グラフ期間（{graph_period_type}）を使用します")
    
    st.markdown("---")
    
    # サブタブの作成
    individual_pdf_tab, bulk_pdf_tab, prediction_tab = st.tabs([
        "📄 個別PDF出力", 
        "📚 一括PDF出力", 
        "🔮 予測分析"
    ])
    
    with individual_pdf_tab:
        create_individual_pdf_section()
    
    with bulk_pdf_tab:
        create_bulk_pdf_section()
    
    with prediction_tab:
        create_prediction_analysis_section()

# フォールバック関数の修正（期間情報を明示）
def create_fallback_los_analysis(df, start_date, end_date):
    """平均在院日数分析のフォールバック版（期間明示版）"""
    # 期間情報を明確に表示
    period_days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
    st.info(f"簡易版の平均在院日数分析を表示しています。（{period_days}日間のデータ）")

# ===============================================================================
# 詳細分析セクション
# ===============================================================================

def create_los_analysis_section(df_filtered, start_date, end_date, common_config):
    """平均在院日数分析セクション（期間対応版）"""
    st.subheader("📊 平均在院日数分析")
    
    if display_alos_analysis_tab:
        try:
            # フィルタリング済みデータと期間情報を渡す
            display_alos_analysis_tab(df_filtered, start_date, end_date, common_config)
            
        except Exception as e:
            st.error(f"平均在院日数分析でエラーが発生しました: {e}")
            st.info("詳細なエラー情報はログを確認してください。")
    else:
        st.warning("平均在院日数分析機能が利用できません。alos_analysis_tab.pyを確認してください。")
        create_fallback_los_analysis(df_filtered, start_date, end_date)

def create_weekday_analysis_section(df_filtered, start_date, end_date, common_config):
    """曜日別分析セクション（期間対応版）"""
    st.subheader("📅 曜日別入退院分析")
    
    if display_dow_analysis_tab:
        try:
            # フィルタリング済みデータと期間情報を渡す
            display_dow_analysis_tab(df_filtered, start_date, end_date, common_config)
        except Exception as e:
            st.error(f"曜日別分析でエラーが発生しました: {e}")
            st.info("詳細なエラー情報はログを確認してください。")
    else:
        st.warning("曜日別分析機能が利用できません。dow_analysis_tab.pyを確認してください。")
        create_fallback_dow_analysis(df_filtered, start_date, end_date)

def create_individual_analysis_section(df_filtered, start_date, end_date):
    """個別分析セクション（期間対応版）"""
    st.subheader("🔍 個別分析")
    
    if display_individual_analysis_tab:
        try:
            # 個別分析用にセッション状態を一時的に更新
            original_df = st.session_state.get('df')
            st.session_state['df'] = df_filtered  # フィルタリング済みデータを設定
            
            # 個別分析実行
            display_individual_analysis_tab()
            
            # 元のデータを復元
            st.session_state['df'] = original_df
            
        except Exception as e:
            st.error(f"個別分析でエラーが発生しました: {e}")
            st.info("詳細なエラー情報はログを確認してください。")
        finally:
            # 念のため元のデータを復元
            if 'original_df' in locals():
                st.session_state['df'] = original_df
    else:
        st.warning("個別分析機能が利用できません。individual_analysis_tab.pyを確認してください。")
        create_fallback_individual_analysis()

# ===============================================================================
# データテーブルセクション
# ===============================================================================

def create_ward_table_section(df_filtered):
    """病棟別データテーブルセクション（病棟名表示対応）"""
    st.subheader("🏥 病棟別データテーブル")
    
    try:
        if df_filtered.empty:
            st.warning("指定された期間にデータがありません。")
            return
        
        # 病棟マッピングの初期化
        from utils import initialize_all_mappings, get_ward_display_name
        initialize_all_mappings(df_filtered)
        ward_mapping = st.session_state.get('ward_mapping', {})
        
        # 期間情報の表示
        if '日付' in df_filtered.columns:
            min_date = df_filtered['日付'].min().date()
            max_date = df_filtered['日付'].max().date()
            st.info(f"データ期間: {min_date} ～ {max_date}")
        
        # 病棟別集計
        ward_summary = calculate_ward_summary(df_filtered)
        
        if not ward_summary.empty:
            # 病棟名列を追加
            ward_summary['病棟名'] = ward_summary['病棟コード'].apply(
                lambda x: get_ward_display_name(x, ward_mapping)
            )
            
            # 列の順序を調整（病棟名を病棟コードの後に配置）
            cols = ward_summary.columns.tolist()
            if '病棟名' in cols:
                # 病棟コードの後に病棟名を配置
                code_idx = cols.index('病棟コード')
                cols.insert(code_idx + 1, cols.pop(cols.index('病棟名')))
                ward_summary = ward_summary[cols]
            
            # フィルタリングオプション（病棟名も含めて選択可能に）
            col1, col2 = st.columns(2)
            with col1:
                # 選択肢を「コード（名前）」形式で表示
                ward_display_options = []
                for _, row in ward_summary.iterrows():
                    code = row['病棟コード']
                    name = row['病棟名']
                    if name != str(code):
                        display_option = f"{code}（{name}）"
                    else:
                        display_option = str(code)
                    ward_display_options.append(display_option)
                
                selected_wards = st.multiselect(
                    "表示する病棟を選択（空白の場合は全て表示）",
                    options=ward_display_options,
                    key="ward_table_filter"
                )
            
            with col2:
                sort_column = st.selectbox(
                    "並び替え基準",
                    options=['病棟コード', '平均在院患者数', '総入院患者数', '総退院患者数', '平均在院日数'],
                    key="ward_table_sort"
                )
            
            # データフィルタリングと並び替え
            if selected_wards:
                ward_summary = ward_summary[ward_summary['病棟コード'].isin(selected_wards)]
            
            if sort_column in ward_summary.columns:
                ascending = st.checkbox("昇順で並び替え", key="ward_table_ascending")
                ward_summary = ward_summary.sort_values(sort_column, ascending=ascending)
            
            # テーブル表示
            # フォーマット辞書を詳細に定義
            format_dict = {}
            
            # 各列のデータ型に応じてフォーマットを設定
            for col in ward_summary.columns:
                if col in ['病棟コード', '集計単位']:
                    # 文字列列はそのまま
                    continue
                elif col in ['期間日数', '延べ在院患者数', '総入院患者数', '総退院患者数', 
                           '緊急入院患者数', '死亡患者数']:
                    # 整数値として表示（合計値・カウント数）
                    format_dict[col] = "{:.0f}"
                elif col in ['平均在院患者数']:
                    # 小数点1桁で表示（平均値）
                    format_dict[col] = "{:.1f}"
                elif col in ['平均在院日数', '病床回転率']:
                    # 小数点1桁で表示（比率・日数）
                    format_dict[col] = "{:.1f}"
                elif col in ['緊急入院率', '死亡率']:
                    # パーセンテージは小数点1桁 + %
                    format_dict[col] = "{:.1f}%"
                else:
                    # その他の数値列は小数点1桁
                    if pd.api.types.is_numeric_dtype(ward_summary[col]):
                        # 整数かどうかを判定
                        if ward_summary[col].dtype in ['int64', 'int32', 'Int64', 'Int32']:
                            format_dict[col] = "{:.0f}"
                        else:
                            # 平均値かどうかを名前から判定
                            if '平均' in col or '率' in col or '日数' in col:
                                format_dict[col] = "{:.1f}"
                            else:
                                format_dict[col] = "{:.0f}"
            
            # テーブル表示
            st.dataframe(
                ward_summary.style.format(format_dict),
                use_container_width=True,
                height=400
            )
            
            # CSVダウンロード
            csv_data = ward_summary.to_csv(index=False).encode('utf-8-sig')
            period_str = f"{min_date}_{max_date}" if '日付' in df_filtered.columns else "全期間"
            st.download_button(
                label="病棟別データをCSVダウンロード",
                data=csv_data,
                file_name=f"病棟別データ_{period_str}.csv",
                mime="text/csv"
            )
            
            # 病棟別グラフ
            create_ward_comparison_charts(ward_summary)
        else:
            st.warning("病棟別集計データを作成できませんでした。")
            
    except Exception as e:
        st.error(f"病棟別テーブル作成中にエラーが発生しました: {e}")

# ===== 使用方法の説明 =====

"""
修正後の使用方法:

1. utils.py に病棟関連の関数を追加
2. alos_analysis_tab.py と dow_analysis_tab.py で utils.py をインポート
3. 病棟選択UI で「02A（2階A病棟）」のような表示に変更
4. 内部的には病棟コードを使用し、表示のみ病棟名を使用

主な変更点:
- 病棟コード → 病棟名の変換ロジック
- 選択肢の表示形式の改善
- セッションステートでのマッピング管理
- エラーハンドリングの強化

これにより、ユーザーは分かりやすい病棟名で選択でき、
システム内部では既存の病棟コードベースの処理をそのまま使用できます。
"""

def create_department_table_section(df_filtered):
    """診療科別データテーブルセクション（期間フィルタリング済み）"""
    st.subheader("🩺 診療科別データテーブル")
    
    try:
        if df_filtered.empty:
            st.warning("指定された期間にデータがありません。")
            return
        
        # 期間情報の表示
        if '日付' in df_filtered.columns:
            min_date = df_filtered['日付'].min().date()
            max_date = df_filtered['日付'].max().date()
            st.info(f"データ期間: {min_date} ～ {max_date}")
        
        # 診療科別集計
        dept_summary = calculate_department_summary(df_filtered)
        
        if not dept_summary.empty:
            # フィルタリングオプション
            col1, col2 = st.columns(2)
            with col1:
                selected_depts = st.multiselect(
                    "表示する診療科を選択（空白の場合は全て表示）",
                    options=sorted(dept_summary['診療科名'].unique()),
                    key="dept_table_filter"
                )
            
            with col2:
                sort_column = st.selectbox(
                    "並び替え基準",
                    options=['診療科名', '平均在院患者数', '総入院患者数', '総退院患者数', '平均在院日数'],
                    key="dept_table_sort"
                )
            
            # データフィルタリングと並び替え
            if selected_depts:
                dept_summary = dept_summary[dept_summary['診療科名'].isin(selected_depts)]
            
            if sort_column in dept_summary.columns:
                ascending = st.checkbox("昇順で並び替え", key="dept_table_ascending")
                dept_summary = dept_summary.sort_values(sort_column, ascending=ascending)
            
            # 診療科名の表示名変換
            if get_display_name_for_dept:
                dept_summary['診療科表示名'] = dept_summary['診療科名'].apply(
                    lambda x: get_display_name_for_dept(x, x)
                )
                # 表示用に列の順序を調整
                cols = dept_summary.columns.tolist()
                if '診療科表示名' in cols:
                    cols.insert(1, cols.pop(cols.index('診療科表示名')))
                    dept_summary = dept_summary[cols]
            
            # ===== 修正：数値フォーマットの改善 =====
            # フォーマット辞書を詳細に定義
            format_dict = {}
            
            # 各列のデータ型に応じてフォーマットを設定
            for col in dept_summary.columns:
                if col in ['診療科名', '診療科表示名', '集計単位']:
                    # 文字列列はそのまま
                    continue
                elif col in ['期間日数', '延べ在院患者数', '総入院患者数', '総退院患者数', 
                           '緊急入院患者数', '死亡患者数']:
                    # 整数値として表示（合計値など）
                    format_dict[col] = "{:.0f}"
                elif col in ['平均在院患者数']:
                    # 小数点1桁で表示（平均値）
                    format_dict[col] = "{:.1f}"
                elif col in ['平均在院日数', '病床回転率']:
                    # 小数点1桁で表示（比率・日数）
                    format_dict[col] = "{:.1f}"
                elif col in ['緊急入院率', '死亡率']:
                    # パーセンテージは小数点1桁 + %
                    format_dict[col] = "{:.1f}%"
                else:
                    # その他の数値列は小数点1桁
                    if pd.api.types.is_numeric_dtype(dept_summary[col]):
                        # 整数かどうかを判定
                        if dept_summary[col].dtype in ['int64', 'int32', 'Int64', 'Int32']:
                            format_dict[col] = "{:.0f}"
                        else:
                            # 平均値かどうかを名前から判定
                            if '平均' in col or '率' in col or '日数' in col:
                                format_dict[col] = "{:.1f}"
                            else:
                                format_dict[col] = "{:.0f}"
            
            # テーブル表示
            st.dataframe(
                dept_summary.style.format(format_dict),
                use_container_width=True,
                height=400
            )
            
            # CSVダウンロード
            csv_data = dept_summary.to_csv(index=False).encode('utf-8-sig')
            period_str = f"{min_date}_{max_date}" if '日付' in df_filtered.columns else "全期間"
            st.download_button(
                label="診療科別データをCSVダウンロード",
                data=csv_data,
                file_name=f"診療科別データ_{period_str}.csv",
                mime="text/csv"
            )
            
            # 診療科別グラフ
            create_department_comparison_charts(dept_summary)
        else:
            st.warning("診療科別集計データを作成できませんでした。")
            
    except Exception as e:
        st.error(f"診療科別テーブル作成中にエラーが発生しました: {e}")

# ===============================================================================
# 集計処理関数
# ===============================================================================

def calculate_ward_summary(df):
    """病棟別サマリーデータの計算"""
    try:
        # 実際に存在する列名を確認
        available_columns = df.columns.tolist()
        
        # 列名のマッピング（柔軟な対応）
        column_mapping = {
            '在院患者数': ['入院患者数（在院）', '在院患者数', '現在患者数'],
            '入院患者数': ['総入院患者数', '入院患者数', '新規入院患者数'],
            '退院患者数': ['総退院患者数', '退院患者数', '退院者数'],
            '緊急入院患者数': ['緊急入院患者数', '救急入院患者数', '緊急入院'],
            '死亡患者数': ['死亡患者数', '死亡者数', '死亡']
        }
        
        # 実際に使用する列名を決定
        actual_columns = {}
        missing_columns = []
        
        for standard_name, possible_names in column_mapping.items():
            found_column = None
            for possible_name in possible_names:
                if possible_name in available_columns:
                    found_column = possible_name
                    break
            
            if found_column:
                actual_columns[standard_name] = found_column
            else:
                missing_columns.append(standard_name)
        
        if missing_columns:
            st.error(f"病棟別集計に必要な列が見つかりません: {missing_columns}")
            return pd.DataFrame()
        
        # 病棟別集計（実際の列名を使用）
        ward_groups = df.groupby('病棟コード', observed=True)
        
        ward_summary = pd.DataFrame({
            '病棟コード': ward_groups['病棟コード'].first(),
            '期間日数': ward_groups['日付'].nunique(),
            '延べ在院患者数': ward_groups[actual_columns['在院患者数']].sum(),
            '総入院患者数': ward_groups[actual_columns['入院患者数']].sum(),
            '総退院患者数': ward_groups[actual_columns['退院患者数']].sum(),
            '緊急入院患者数': ward_groups[actual_columns['緊急入院患者数']].sum(),
            '死亡患者数': ward_groups[actual_columns['死亡患者数']].sum()
        }).reset_index(drop=True)
        
        # 計算指標の追加
        ward_summary['平均在院患者数'] = ward_summary['延べ在院患者数'] / ward_summary['期間日数']
        
        # 平均在院日数の計算
        ward_summary['平均在院日数'] = ward_summary.apply(
            lambda row: row['延べ在院患者数'] / ((row['総入院患者数'] + row['総退院患者数']) / 2)
            if (row['総入院患者数'] + row['総退院患者数']) > 0 else 0,
            axis=1
        )
        
        # 病床回転率の計算
        ward_summary['病床回転率'] = ward_summary.apply(
            lambda row: row['総退院患者数'] / row['平均在院患者数'] 
            if row['平均在院患者数'] > 0 else 0,
            axis=1
        )
        
        # 緊急入院率と死亡率
        ward_summary['緊急入院率'] = ward_summary.apply(
            lambda row: (row['緊急入院患者数'] / row['総入院患者数'] * 100)
            if row['総入院患者数'] > 0 else 0,
            axis=1
        )
        
        ward_summary['死亡率'] = ward_summary.apply(
            lambda row: (row['死亡患者数'] / row['総退院患者数'] * 100)
            if row['総退院患者数'] > 0 else 0,
            axis=1
        )
        
        return ward_summary
        
    except Exception as e:
        st.error(f"病棟別サマリー計算中にエラー: {e}")
        return pd.DataFrame()

def calculate_department_summary(df):
    """診療科別サマリーデータの計算"""
    try:
        # 病棟別集計と同じロジックを使用
        available_columns = df.columns.tolist()
        
        column_mapping = {
            '在院患者数': ['入院患者数（在院）', '在院患者数', '現在患者数'],
            '入院患者数': ['総入院患者数', '入院患者数', '新規入院患者数'],
            '退院患者数': ['総退院患者数', '退院患者数', '退院者数'],
            '緊急入院患者数': ['緊急入院患者数', '救急入院患者数', '緊急入院'],
            '死亡患者数': ['死亡患者数', '死亡者数', '死亡']
        }
        
        actual_columns = {}
        missing_columns = []
        
        for standard_name, possible_names in column_mapping.items():
            found_column = None
            for possible_name in possible_names:
                if possible_name in available_columns:
                    found_column = possible_name
                    break
            
            if found_column:
                actual_columns[standard_name] = found_column
            else:
                missing_columns.append(standard_name)
        
        if missing_columns:
            st.error(f"診療科別集計に必要な列が見つかりません: {missing_columns}")
            return pd.DataFrame()
        
        # 診療科別集計（実際の列名を使用）
        dept_groups = df.groupby('診療科名', observed=True)
        
        dept_summary = pd.DataFrame({
            '診療科名': dept_groups['診療科名'].first(),
            '期間日数': dept_groups['日付'].nunique(),
            '延べ在院患者数': dept_groups[actual_columns['在院患者数']].sum(),
            '総入院患者数': dept_groups[actual_columns['入院患者数']].sum(),
            '総退院患者数': dept_groups[actual_columns['退院患者数']].sum(),
            '緊急入院患者数': dept_groups[actual_columns['緊急入院患者数']].sum(),
            '死亡患者数': dept_groups[actual_columns['死亡患者数']].sum()
        }).reset_index(drop=True)
        
        # 計算指標の追加（ward_summaryと同じロジック）
        dept_summary['平均在院患者数'] = dept_summary['延べ在院患者数'] / dept_summary['期間日数']
        
        dept_summary['平均在院日数'] = dept_summary.apply(
            lambda row: row['延べ在院患者数'] / ((row['総入院患者数'] + row['総退院患者数']) / 2)
            if (row['総入院患者数'] + row['総退院患者数']) > 0 else 0,
            axis=1
        )
        
        dept_summary['病床回転率'] = dept_summary.apply(
            lambda row: row['総退院患者数'] / row['平均在院患者数'] 
            if row['平均在院患者数'] > 0 else 0,
            axis=1
        )
        
        dept_summary['緊急入院率'] = dept_summary.apply(
            lambda row: (row['緊急入院患者数'] / row['総入院患者数'] * 100)
            if row['総入院患者数'] > 0 else 0,
            axis=1
        )
        
        dept_summary['死亡率'] = dept_summary.apply(
            lambda row: (row['死亡患者数'] / row['総退院患者数'] * 100)
            if row['総退院患者数'] > 0 else 0,
            axis=1
        )
        
        return dept_summary
        
    except Exception as e:
        st.error(f"診療科別サマリー計算中にエラー: {e}")
        return pd.DataFrame()

# ===============================================================================
# グラフ作成関数
# ===============================================================================

def create_ward_comparison_charts(ward_summary):
    """病棟別比較チャートの作成"""
    try:
        st.markdown("---")
        st.subheader("病棟別比較グラフ")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 平均在院患者数の比較
            fig_census = px.bar(
                ward_summary,
                x='病棟コード',
                y='平均在院患者数',
                title='病棟別 平均在院患者数',
                color='平均在院患者数',
                color_continuous_scale='Blues'
            )
            fig_census.update_layout(height=400)
            st.plotly_chart(fig_census, use_container_width=True)
        
        with col2:
            # 平均在院日数の比較
            fig_alos = px.bar(
                ward_summary,
                x='病棟コード',
                y='平均在院日数',
                title='病棟別 平均在院日数',
                color='平均在院日数',
                color_continuous_scale='Reds'
            )
            fig_alos.update_layout(height=400)
            st.plotly_chart(fig_alos, use_container_width=True)
        
        # 散布図による相関分析
        fig_scatter = px.scatter(
            ward_summary,
            x='平均在院患者数',
            y='平均在院日数',
            size='総入院患者数',
            hover_name='病棟コード',
            title='平均在院患者数 vs 平均在院日数（バブルサイズ：総入院患者数）',
            labels={'平均在院患者数': '平均在院患者数（人）', '平均在院日数': '平均在院日数（日）'}
        )
        fig_scatter.update_layout(height=400)
        st.plotly_chart(fig_scatter, use_container_width=True)
        
    except Exception as e:
        st.error(f"病棟別グラフ作成中にエラー: {e}")

def create_department_comparison_charts(dept_summary):
    """診療科別比較チャートの作成"""
    try:
        st.markdown("---")
        st.subheader("診療科別比較グラフ")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 平均在院患者数の比較（上位10位）
            top_census = dept_summary.nlargest(10, '平均在院患者数')
            fig_census = px.bar(
                top_census,
                x='平均在院患者数',
                y='診療科名',
                orientation='h',
                title='診療科別 平均在院患者数（上位10位）',
                color='平均在院患者数',
                color_continuous_scale='Blues'
            )
            fig_census.update_layout(height=400)
            st.plotly_chart(fig_census, use_container_width=True)
        
        with col2:
            # 平均在院日数の比較（上位10位）
            top_alos = dept_summary.nlargest(10, '平均在院日数')
            fig_alos = px.bar(
                top_alos,
                x='平均在院日数',
                y='診療科名',
                orientation='h',
                title='診療科別 平均在院日数（上位10位）',
                color='平均在院日数',
                color_continuous_scale='Reds'
            )
            fig_alos.update_layout(height=400)
            st.plotly_chart(fig_alos, use_container_width=True)
        
        # 緊急入院率と死亡率の散布図
        fig_rates = px.scatter(
            dept_summary,
            x='緊急入院率',
            y='死亡率',
            size='総入院患者数',
            hover_name='診療科名',
            title='緊急入院率 vs 死亡率（バブルサイズ：総入院患者数）',
            labels={'緊急入院率': '緊急入院率（%）', '死亡率': '死亡率（%）'}
        )
        fig_rates.update_layout(height=400)
        st.plotly_chart(fig_rates, use_container_width=True)
        
    except Exception as e:
        st.error(f"診療科別グラフ作成中にエラー: {e}")

# ===============================================================================
# 出力・予測セクション
# ===============================================================================

def create_individual_pdf_section():
    """個別PDF出力セクション"""
    st.subheader("📄 個別PDF出力")
    
    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return
    
    df = st.session_state.get('df')
    target_data = st.session_state.get('target_data')
    
    if df is None or df.empty:
        st.error("分析対象のデータがありません。")
        return
    
    # 期間設定の適用
    start_date = st.session_state.get('analysis_start_date')
    end_date = st.session_state.get('analysis_end_date')
    
    if start_date and end_date:
        df_for_pdf = safe_date_filter(df, start_date, end_date)
        st.info(f"📄 PDF出力期間: {start_date} ～ {end_date}")
    else:
        df_for_pdf = df
        st.info("📄 全期間のデータでPDF出力")
    
    try:
        # PDF出力設定
        col1, col2 = st.columns(2)
        
        with col1:
            output_type = st.selectbox(
                "出力単位",
                ["全体", "診療科別", "病棟別"],
                key="pdf_output_type"
            )
        
        with col2:
            pdf_orientation = st.selectbox(
                "PDF向き",
                ["縦向き", "横向き"],
                key="pdf_orientation"
            )
        
        # 対象選択
        target_items = []
        if output_type == "診療科別":
            available_depts = sorted(df_for_pdf['診療科名'].unique())
            target_items = st.multiselect(
                "出力対象診療科",
                available_depts,
                default=available_depts[:3] if len(available_depts) >= 3 else available_depts,
                key="pdf_target_depts"
            )
        elif output_type == "病棟別":
            available_wards = sorted(df_for_pdf['病棟コード'].unique())
            target_items = st.multiselect(
                "出力対象病棟",
                available_wards,
                default=available_wards[:3] if len(available_wards) >= 3 else available_wards,
                key="pdf_target_wards"
            )
        
        # グラフ表示期間
        graph_days = st.slider(
            "グラフ表示期間（日数）",
            min_value=30,
            max_value=365,
            value=90,
            step=30,
            key="pdf_graph_days"
        )
        
        # PDF生成ボタン
        if st.button("PDF生成", key="generate_individual_pdf"):
            if output_type != "全体" and not target_items:
                st.warning("出力対象を選択してください。")
            else:
                generate_individual_pdfs(
                    df_for_pdf, target_data, output_type, target_items, 
                    pdf_orientation, graph_days
                )
    
    except Exception as e:
        st.error(f"個別PDF出力設定中にエラーが発生しました: {e}")

def create_bulk_pdf_section():
    """一括PDF出力セクション"""
    st.subheader("📚 一括PDF出力")
    
    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return
    
    df = st.session_state.get('df')
    target_data = st.session_state.get('target_data')
    
    if df is None or df.empty:
        st.error("分析対象のデータがありません。")
        return
    
    # 期間設定の適用
    start_date = st.session_state.get('analysis_start_date')
    end_date = st.session_state.get('analysis_end_date')
    
    if start_date and end_date:
        df_for_pdf = safe_date_filter(df, start_date, end_date)
        st.info(f"📚 一括PDF期間: {start_date} ～ {end_date}")
    else:
        df_for_pdf = df
        st.info("📚 全期間のデータで一括PDF出力")
    
    st.info("一括PDF出力機能により、全診療科または全病棟のPDFレポートを一度に生成できます。")

def create_prediction_analysis_section():
    """予測分析セクション"""
    st.subheader("🔮 予測分析")
    
    if display_forecast_analysis_tab:
        try:
            display_forecast_analysis_tab()
        except Exception as e:
            st.error(f"予測分析でエラーが発生しました: {e}")
            st.info("詳細なエラー情報はログを確認してください。")
    else:
        st.warning("予測分析機能が利用できません。forecast_analysis_tab.pyを確認してください。")
        create_fallback_prediction_analysis()

# ===============================================================================
# PDF生成関数（シンプル版）
# ===============================================================================

def generate_individual_pdfs(df, target_data, output_type, target_items, orientation, graph_days):
    """個別PDF生成処理（シンプル版）"""
    try:
        if not create_pdf:
            st.error("PDF生成機能が利用できません。")
            return
        
        st.info("PDF生成機能は実装中です。")
        
    except Exception as e:
        st.error(f"PDF生成中にエラーが発生しました: {e}")

# ===============================================================================
# フォールバック関数群
# ===============================================================================

def create_fallback_los_analysis(df, start_date, end_date):
    """平均在院日数分析のフォールバック版"""
    st.info("簡易版の平均在院日数分析を表示しています。")
    
    try:
        if df.empty:
            st.warning("指定された期間にデータがありません。")
            return
        
        # 利用可能な列名を確認
        available_columns = df.columns.tolist()
        
        # 列名のマッピング
        column_mapping = {
            '在院患者数': ['入院患者数（在院）', '在院患者数', '現在患者数'],
            '入院患者数': ['総入院患者数', '入院患者数', '新規入院患者数'],
            '退院患者数': ['総退院患者数', '退院患者数', '退院者数']
        }
        
        # 実際に使用する列名を決定
        actual_columns = {}
        for standard_name, possible_names in column_mapping.items():
            for possible_name in possible_names:
                if possible_name in available_columns:
                    actual_columns[standard_name] = possible_name
                    break
        
        # 必要な列が揃っているかチェック
        required_columns = ['在院患者数', '入院患者数', '退院患者数']
        missing_columns = [col for col in required_columns if col not in actual_columns]
        
        if missing_columns:
            st.error(f"平均在院日数計算に必要な列がありません: {missing_columns}")
            return
        
        # 基本的な平均在院日数計算
        total_patient_days = df[actual_columns['在院患者数']].sum()
        total_admissions = df[actual_columns['入院患者数']].sum()
        total_discharges = df[actual_columns['退院患者数']].sum()
        
        if (total_admissions + total_discharges) > 0:
            alos = total_patient_days / ((total_admissions + total_discharges) / 2)
            st.metric("平均在院日数", f"{alos:.2f}日")
        
        # 日別トレンド
        daily_alos = df.groupby('日付', observed=True).agg({
            actual_columns['在院患者数']: 'sum',
            actual_columns['入院患者数']: 'sum',
            actual_columns['退院患者数']: 'sum'
        }).reset_index()
        
        # 列名を標準化
        daily_alos = daily_alos.rename(columns={
            actual_columns['在院患者数']: '在院患者数',
            actual_columns['入院患者数']: '入院患者数',
            actual_columns['退院患者数']: '退院患者数'
        })
        
        daily_alos['平均在院日数'] = daily_alos.apply(
            lambda row: row['在院患者数'] / ((row['入院患者数'] + row['退院患者数']) / 2)
            if (row['入院患者数'] + row['退院患者数']) > 0 else 0,
            axis=1
        )
        
        fig = px.line(
            daily_alos,
            x='日付',
            y='平均在院日数',
            title=f'日別平均在院日数推移 ({start_date} ～ {end_date})'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    except Exception as e:
        st.error(f"フォールバック版平均在院日数分析でエラー: {e}")

def create_fallback_dow_analysis(df, start_date, end_date):
    """曜日別分析のフォールバック版"""
    st.info("簡易版の曜日別分析を表示しています。")
    
    try:
        if df.empty:
            st.warning("指定された期間にデータがありません。")
            return
        
        # 曜日の追加
        df_copy = df.copy()
        df_copy['曜日'] = df_copy['日付'].dt.day_name()
        df_copy['曜日番号'] = df_copy['日付'].dt.dayofweek
        
        # 利用可能な列の確認
        numeric_columns = df_copy.select_dtypes(include=[np.number]).columns
        patient_columns = [col for col in numeric_columns if '患者数' in col]
        
        if not patient_columns:
            st.error("患者数データが見つかりません。")
            return
        
        # 曜日別集計
        agg_dict = {col: 'mean' for col in patient_columns}
        dow_summary = df_copy.groupby(['曜日', '曜日番号'], observed=True).agg(agg_dict).reset_index()
        dow_summary = dow_summary.sort_values('曜日番号')
        
        # グラフ表示
        fig = px.bar(
            dow_summary,
            x='曜日',
            y=patient_columns[:3],  # 最大3つまで表示
            title=f'曜日別平均患者数 ({start_date} ～ {end_date})',
            barmode='group'
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # テーブル表示
        st.dataframe(dow_summary, use_container_width=True)
        
    except Exception as e:
        st.error(f"フォールバック版曜日別分析でエラー: {e}")

def create_fallback_individual_analysis():
    """個別分析のフォールバック版"""
    st.info("個別分析機能が利用できません。")
    st.write("individual_analysis_tab.pyモジュールを確認してください。")

def create_fallback_prediction_analysis():
    """予測分析のフォールバック版"""
    st.info("予測分析機能が利用できません。")
    st.write("forecast_analysis_tab.pyモジュールを確認してください。")