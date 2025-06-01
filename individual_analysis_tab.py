# individual_analysis_tab.py (統一フィルター完全対応版)

import streamlit as st
import pandas as pd
import hashlib
from datetime import datetime
import logging

# ログ設定
logger = logging.getLogger(__name__)

# 統一フィルター完全対応のためのインポート
try:
    from forecast import generate_filtered_summaries, create_forecast_dataframe
    from chart import create_interactive_patient_chart, create_interactive_dual_axis_chart
    from pdf_generator import create_pdf, create_landscape_pdf
    from utils import get_display_name_for_dept, get_ward_display_name
    # 統一フィルター関数の完全インポート
    from unified_filters import (
        create_unified_filter_status_card,
        validate_unified_filters,
        apply_unified_filters,
        get_unified_filter_summary,
        get_unified_filter_config
    )
except ImportError as e:
    logger.error(f"個別分析タブに必要なモジュールのインポートに失敗: {e}", exc_info=True)
    st.error(f"個別分析タブに必要なモジュールのインポートに失敗しました: {e}")
    st.error("関連モジュールが正しい場所に配置されているか確認してください。")
    # 関数をNoneに設定
    generate_filtered_summaries = None
    create_forecast_dataframe = None
    create_interactive_patient_chart = None
    create_interactive_dual_axis_chart = None
    create_pdf = None
    create_landscape_pdf = None
    get_display_name_for_dept = None
    get_ward_display_name = None
    create_unified_filter_status_card = None
    validate_unified_filters = None
    apply_unified_filters = None
    get_unified_filter_summary = None
    get_unified_filter_config = None

# 個別分析タブ用の設定
INDIVIDUAL_TAB_CONFIG = {
    'namespace': 'individual_analysis',
    'required_columns': ['患者ID', '日付', '診療科名', '病棟コード'],
    'session_key_prefix': 'ind_ana'
}

class IndividualAnalysisErrorHandler:
    """個別分析タブ専用エラーハンドリング"""
    
    @staticmethod
    def handle_filter_error(error):
        """フィルター関連エラーの処理"""
        logger.error(f"個別分析フィルターエラー: {error}", exc_info=True)
        st.error(f"🚨 フィルター処理エラー: {str(error)}")
        st.info("💡 対処法: サイドバーの統一フィルター設定を確認してください。")
    
    @staticmethod
    def handle_data_error(error):
        """データ処理エラーの処理"""
        logger.error(f"個別分析データエラー: {error}", exc_info=True)
        st.error(f"🚨 データ処理エラー: {str(error)}")
        st.info("💡 対処法: データの形式や内容を確認してください。")
    
    @staticmethod
    def handle_analysis_error(error):
        """分析処理エラーの処理"""
        logger.error(f"個別分析処理エラー: {error}", exc_info=True)
        st.error(f"🚨 分析処理エラー: {str(error)}")
        st.info("💡 対処法: 分析対象データの条件を見直してください。")

def get_session_key(key_name):
    """統一されたセッション状態キー生成"""
    return f"{INDIVIDUAL_TAB_CONFIG['session_key_prefix']}_{key_name}"

def validate_data_for_individual_analysis(df):
    """個別分析用データ妥当性チェック"""
    if df is None or len(df) == 0:
        st.warning("⚠️ 分析対象データがありません。フィルター条件を確認してください。")
        return False
    
    # 必要な列の存在チェック（柔軟に対応）
    essential_columns = ['日付']
    missing_columns = [col for col in essential_columns if col not in df.columns]
    
    if missing_columns:
        st.error(f"❌ 必要な列が不足しています: {missing_columns}")
        return False
    
    return True

def check_required_functions():
    """必要な関数の存在チェック"""
    required_functions = [
        generate_filtered_summaries, create_forecast_dataframe,
        create_interactive_patient_chart, create_interactive_dual_axis_chart,
        create_pdf, create_landscape_pdf
    ]
    
    missing_functions = [func for func in required_functions if func is None]
    
    if missing_functions:
        st.error("❌ 個別分析タブの実行に必要な機能の一部が読み込めませんでした。")
        st.error("アプリケーションのログを確認し、インポートエラーを解決してください。")
        return False
    
    return True

def display_dataframe_with_title(title, df_data, key_suffix=""):
    """データフレーム表示の統一関数"""
    if df_data is not None and not df_data.empty:
        st.markdown(f"##### {title}")
        st.dataframe(df_data.fillna('-'), use_container_width=True)
    else:
        st.markdown(f"##### {title}")
        st.warning(f"{title} データがありません。")

def show_detailed_filter_settings(filtered_df):
    """詳細フィルター設定UI（統一フィルター適用後の細分化）"""
    
    st.markdown("#### 🔧 詳細分析設定（統一フィルター結果内での細分化）")
    
    # 使用可能な分析単位の確認
    unique_depts = []
    unique_wards = []
    
    if "診療科名" in filtered_df.columns and not filtered_df['診療科名'].empty:
        unique_depts = sorted(filtered_df["診療科名"].astype(str).unique())
    
    if "病棟コード" in filtered_df.columns and not filtered_df['病棟コード'].empty:
        unique_wards = sorted(filtered_df["病棟コード"].astype(str).unique())
    
    col1_filter, col2_filter = st.columns([1, 2])
    
    with col1_filter:
        filter_type_options = ["全体"]
        if unique_depts: 
            filter_type_options.append("診療科別")
        if unique_wards: 
            filter_type_options.append("病棟別")
        
        default_filter_type = "全体"
        current_filter_type = st.session_state.get(get_session_key('filter_type'), default_filter_type)
        
        try:
            current_filter_type_index = filter_type_options.index(current_filter_type)
        except ValueError:
            current_filter_type_index = 0
            
        filter_type = st.radio(
            "詳細分析単位", 
            filter_type_options, 
            index=current_filter_type_index,
            key=get_session_key('filter_type_radio'),
            help="統一フィルター適用後のデータをさらに細分化して分析します"
        )
        st.session_state[get_session_key('filter_type')] = filter_type
    
    filter_value_actual = "全体"
    filter_value_display = "全体"
    
    with col2_filter:
        if filter_type == "診療科別" and unique_depts:
            # 診療科表示名のマッピング
            dept_display_options_map = {"全体": "全体"}
            if get_display_name_for_dept:
                for dept_code in unique_depts:
                    display_name = get_display_name_for_dept(dept_code, dept_code)
                    dept_display_options_map[display_name] = dept_code
            else:
                for dept_code in unique_depts: 
                    dept_display_options_map[dept_code] = dept_code
            
            sorted_dept_display_names = ["全体"] + sorted([k for k in dept_display_options_map.keys() if k != "全体"])
            current_dept_display = st.session_state.get(get_session_key('dept_select'), "全体")
            
            if current_dept_display not in sorted_dept_display_names: 
                current_dept_display = "全体"
            
            try:
                current_dept_idx = sorted_dept_display_names.index(current_dept_display)
            except ValueError: 
                current_dept_idx = 0
                
            filter_value_display = st.selectbox(
                "診療科を選択", 
                sorted_dept_display_names, 
                index=current_dept_idx,
                key=get_session_key('dept_select_box'),
                help="統一フィルター範囲内の診療科から選択"
            )
            st.session_state[get_session_key('dept_select')] = filter_value_display
            filter_value_actual = dept_display_options_map.get(filter_value_display, "全体")
            
        elif filter_type == "病棟別" and unique_wards:
            # 病棟表示名のマッピング
            ward_display_options_map = {"全体": "全体"}
            if get_ward_display_name:
                for ward_code in unique_wards:
                    display_name = get_ward_display_name(ward_code)
                    ward_display_options_map[display_name] = ward_code
            else:
                for ward_code in unique_wards: 
                    ward_display_options_map[ward_code] = ward_code
            
            sorted_ward_display_names = ["全体"] + sorted([k for k in ward_display_options_map.keys() if k != "全体"])
            current_ward_display = st.session_state.get(get_session_key('ward_select'), "全体")
            
            if current_ward_display not in sorted_ward_display_names: 
                current_ward_display = "全体"
            
            try:
                current_ward_idx = sorted_ward_display_names.index(current_ward_display)
            except ValueError: 
                current_ward_idx = 0
                
            filter_value_display = st.selectbox(
                "病棟を選択", 
                sorted_ward_display_names, 
                index=current_ward_idx,
                key=get_session_key('ward_select_box'),
                help="統一フィルター範囲内の病棟から選択"
            )
            st.session_state[get_session_key('ward_select')] = filter_value_display
            filter_value_actual = ward_display_options_map.get(filter_value_display, "全体")
        else:
            st.write("　")  # スペース確保
    
    return filter_type, filter_value_actual, filter_value_display

def apply_detailed_filters(filtered_df, filter_type, filter_value_actual):
    """詳細フィルターの適用"""
    
    current_filter_title_display = "全体（統一フィルター適用済み）"
    chart_data_for_graphs = filtered_df.copy()
    filter_code_for_target = "全体"
    
    if filter_type == "全体" or filter_value_actual == "全体":
        current_filter_title_display = "全体（統一フィルター適用済み）"
        current_results_data = generate_filtered_summaries(filtered_df, None, None) if generate_filtered_summaries else None
        
    elif filter_type == "診療科別":
        current_filter_title_display = f"診療科: {filter_value_actual}（統一フィルター範囲内）"
        filter_code_for_target = filter_value_actual
        
        if generate_filtered_summaries:
            current_results_data = generate_filtered_summaries(filtered_df, "診療科名", filter_value_actual)
        else:
            current_results_data = None
            
        if "診療科名" in filtered_df.columns and not filtered_df.empty:
            chart_data_for_graphs = filtered_df[filtered_df["診療科名"] == filter_value_actual]
        else:
            chart_data_for_graphs = pd.DataFrame()
            
    elif filter_type == "病棟別":
        current_filter_title_display = f"病棟: {filter_value_actual}（統一フィルター範囲内）"
        filter_code_for_target = filter_value_actual
        
        if generate_filtered_summaries:
            current_results_data = generate_filtered_summaries(filtered_df, "病棟コード", filter_value_actual)
        else:
            current_results_data = None
            
        if "病棟コード" in filtered_df.columns and not filtered_df.empty:
            chart_data_for_graphs = filtered_df[filtered_df["病棟コード"] == filter_value_actual]
        else:
            chart_data_for_graphs = pd.DataFrame()
    
    return current_results_data, chart_data_for_graphs, current_filter_title_display, filter_code_for_target

def display_analysis_charts(chart_data_for_graphs, current_filter_title_display, selected_days_for_graph, target_data, filter_code_for_target):
    """分析チャートの表示"""
    
    if chart_data_for_graphs is None or chart_data_for_graphs.empty:
        st.warning("⚠️ グラフを表示するためのデータがありません。")
        return
    
    # データ期間情報の表示
    data_period_info = ""
    min_date_chart_obj = None
    max_date_chart_obj = None
    
    if '日付' in chart_data_for_graphs.columns and not chart_data_for_graphs['日付'].empty:
        min_date_chart_obj = chart_data_for_graphs['日付'].min()
        max_date_chart_obj = chart_data_for_graphs['日付'].max()
        data_period_info = f"期間: {min_date_chart_obj.date()} ～ {max_date_chart_obj.date()}"
    
    st.info(f"📊 対象データ: {len(chart_data_for_graphs):,}行　{data_period_info}")
    
    # 目標値の取得
    target_val_all, target_val_weekday, target_val_holiday = None, None, None
    if target_data is not None and not target_data.empty:
        if '_target_dict' not in st.session_state:
            st.session_state._target_dict = {}
            for _, row in target_data.iterrows():
                if all(col in target_data.columns for col in ['部門コード', '区分', '目標値']):
                    st.session_state._target_dict[(str(row['部門コード']), str(row['区分']))] = row['目標値']
        
        target_val_all = st.session_state._target_dict.get((str(filter_code_for_target), '全日'))
        target_val_weekday = st.session_state._target_dict.get((str(filter_code_for_target), '平日'))
        target_val_holiday = st.session_state._target_dict.get((str(filter_code_for_target), '休日'))
    
    # タブでチャートを分離
    graph_tab1, graph_tab2 = st.tabs(["📈 入院患者数推移", "📊 複合指標推移（二軸）"])
    
    with graph_tab1:
        if create_interactive_patient_chart:
            try:
                # 全日グラフ
                st.markdown("##### 全日 入院患者数推移")
                fig_all_ind = create_interactive_patient_chart(
                    chart_data_for_graphs, 
                    title=f"{current_filter_title_display} 全日", 
                    days=selected_days_for_graph, 
                    target_value=target_val_all, 
                    chart_type="全日"
                )
                if fig_all_ind: 
                    st.plotly_chart(fig_all_ind, use_container_width=True)
                else: 
                    st.warning("全日グラフの生成に失敗しました。")
                
                # 平日・休日グラフ
                if "平日判定" in chart_data_for_graphs.columns:
                    weekday_data_ind = chart_data_for_graphs[chart_data_for_graphs["平日判定"] == "平日"]
                    holiday_data_ind = chart_data_for_graphs[chart_data_for_graphs["平日判定"] == "休日"]
                    
                    # 平日グラフ
                    st.markdown("##### 平日 入院患者数推移")
                    fig_weekday_ind = create_interactive_patient_chart(
                        weekday_data_ind, 
                        title=f"{current_filter_title_display} 平日", 
                        days=selected_days_for_graph, 
                        show_moving_average=False, 
                        target_value=target_val_weekday, 
                        chart_type="平日"
                    )
                    if fig_weekday_ind: 
                        st.plotly_chart(fig_weekday_ind, use_container_width=True)
                    else: 
                        st.warning("平日グラフの生成に失敗しました。")
                    
                    # 休日グラフ
                    st.markdown("##### 休日 入院患者数推移")
                    fig_holiday_ind = create_interactive_patient_chart(
                        holiday_data_ind, 
                        title=f"{current_filter_title_display} 休日", 
                        days=selected_days_for_graph, 
                        show_moving_average=False, 
                        target_value=target_val_holiday, 
                        chart_type="休日"
                    )
                    if fig_holiday_ind: 
                        st.plotly_chart(fig_holiday_ind, use_container_width=True)
                    else: 
                        st.warning("休日グラフの生成に失敗しました。")
                        
            except Exception as e:
                IndividualAnalysisErrorHandler.handle_analysis_error(e)
        else:
            st.warning("⚠️ グラフ生成関数 (create_interactive_patient_chart) が利用できません。")
    
    with graph_tab2:
        if create_interactive_dual_axis_chart:
            try:
                st.markdown("##### 入院患者数と患者移動の推移（7日移動平均）")
                fig_dual_ind = create_interactive_dual_axis_chart(
                    chart_data_for_graphs, 
                    title=f"{current_filter_title_display} 患者数と移動", 
                    days=selected_days_for_graph
                )
                if fig_dual_ind: 
                    st.plotly_chart(fig_dual_ind, use_container_width=True)
                else: 
                    st.warning("複合グラフの生成に失敗しました。")
            except Exception as e:
                IndividualAnalysisErrorHandler.handle_analysis_error(e)
        else:
            st.warning("⚠️ グラフ生成関数 (create_interactive_dual_axis_chart) が利用できません。")

def display_forecast_and_summary(current_results_data, latest_data_date):
    """予測データと集計結果の表示"""
    
    # 予測データの表示
    st.markdown("##### 📈 在院患者数予測")
    if (create_forecast_dataframe and current_results_data and 
        current_results_data.get("summary") is not None and 
        current_results_data.get("weekday") is not None and 
        current_results_data.get("holiday") is not None):
        
        try:
            forecast_df_ind = create_forecast_dataframe(
                current_results_data.get("summary"), 
                current_results_data.get("weekday"), 
                current_results_data.get("holiday"), 
                latest_data_date
            )
            
            if forecast_df_ind is not None and not forecast_df_ind.empty:
                display_df_ind = forecast_df_ind.copy()
                if "年間平均人日（実績＋予測）" in display_df_ind.columns:
                    display_df_ind = display_df_ind.rename(columns={"年間平均人日（実績＋予測）": "年度予測"})
                if "延べ予測人日" in display_df_ind.columns:
                    display_df_ind = display_df_ind.drop(columns=["延べ予測人日"])
                st.dataframe(display_df_ind, use_container_width=True)
            else:
                st.warning("⚠️ 予測データを作成できませんでした。")
        except Exception as e:
            IndividualAnalysisErrorHandler.handle_analysis_error(e)
    else:
        st.warning("⚠️ 予測データフレーム作成関数または必要な集計データが不足しています。")
    
    # 集計結果の表示
    display_dataframe_with_title("📊 全日平均値（平日・休日含む）", current_results_data.get("summary") if current_results_data else None)
    display_dataframe_with_title("📅 平日平均値", current_results_data.get("weekday") if current_results_data else None)
    display_dataframe_with_title("🎌 休日平均値", current_results_data.get("holiday") if current_results_data else None)
    
    # 月次データをエクスパンダーで表示
    with st.expander("📊 月次平均値を見る"):
        display_dataframe_with_title("月次 全体平均", current_results_data.get("monthly_all") if current_results_data else None)
        display_dataframe_with_title("月次 平日平均", current_results_data.get("monthly_weekday") if current_results_data else None)
        display_dataframe_with_title("月次 休日平均", current_results_data.get("monthly_holiday") if current_results_data else None)

def display_pdf_export_options(current_results_data, chart_data_for_graphs, current_filter_title_display, 
                              latest_data_date, target_data, filter_code_for_target, pdf_graph_days_to_use, 
                              filter_type, filter_value_actual):
    """PDF出力オプションの表示"""
    
    st.markdown("##### 📄 個別PDF出力")
    
    # PDF用予測データの準備
    pdf_forecast_df_data = pd.DataFrame()
    if (create_forecast_dataframe and current_results_data and 
        current_results_data.get("summary") is not None and 
        current_results_data.get("weekday") is not None and 
        current_results_data.get("holiday") is not None):
        
        try:
            pdf_forecast_df_data = create_forecast_dataframe(
                current_results_data.get("summary"), 
                current_results_data.get("weekday"), 
                current_results_data.get("holiday"), 
                latest_data_date
            )
        except Exception as e:
            IndividualAnalysisErrorHandler.handle_analysis_error(e)
    
    # 安全なファイル名用の文字列生成
    safe_filter_value = str(filter_value_actual).replace('/', '_').replace(' ', '_') if filter_value_actual else "all"
    date_str_pdf = latest_data_date.strftime("%Y%m%d")
    safe_title_pdf = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in current_filter_title_display)
    
    pdf_col1, pdf_col2 = st.columns(2)
    
    # 縦向きPDF
    with pdf_col1:
        portrait_button_key = get_session_key(f"pdf_portrait_{filter_type}_{safe_filter_value}")
        portrait_dl_button_key = get_session_key(f"dl_portrait_{filter_type}_{safe_filter_value}")
        
        if create_pdf and st.button("📄 縦向きPDF出力", key=portrait_button_key, use_container_width=True):
            if chart_data_for_graphs is None or chart_data_for_graphs.empty:
                st.warning("⚠️ PDF生成に必要なグラフデータがありません。")
            else:
                with st.spinner(f'{current_filter_title_display}の縦向きPDFを生成中...'):
                    try:
                        pdf_data_portrait = create_pdf(
                            forecast_df=pdf_forecast_df_data,
                            df_weekday=current_results_data.get("weekday"), 
                            df_holiday=current_results_data.get("holiday"),
                            df_all_avg=current_results_data.get("summary"), 
                            chart_data=chart_data_for_graphs,
                            title_prefix=current_filter_title_display, 
                            latest_date=latest_data_date,
                            target_data=target_data, 
                            filter_code=filter_code_for_target, 
                            graph_days=[pdf_graph_days_to_use]
                        )
                        
                        if pdf_data_portrait:
                            filename_pdf = f"入院患者数予測_{safe_title_pdf}_{date_str_pdf}.pdf"
                            st.download_button(
                                label="📥 縦向きPDFをダウンロード", 
                                data=pdf_data_portrait, 
                                file_name=filename_pdf,
                                mime="application/pdf", 
                                key=portrait_dl_button_key
                            )
                        else: 
                            st.error("❌ 縦向きPDFの生成に失敗しました。")
                    except Exception as e:
                        IndividualAnalysisErrorHandler.handle_analysis_error(e)
    
    # 横向きPDF
    with pdf_col2:
        landscape_button_key = get_session_key(f"pdf_landscape_{filter_type}_{safe_filter_value}")
        landscape_dl_button_key = get_session_key(f"dl_landscape_{filter_type}_{safe_filter_value}")
        
        if create_landscape_pdf and st.button("📄 横向きPDF出力", key=landscape_button_key, use_container_width=True):
            if chart_data_for_graphs is None or chart_data_for_graphs.empty:
                st.warning("⚠️ PDF生成に必要なグラフデータがありません。")
            else:
                with st.spinner(f'{current_filter_title_display}の横向きPDFを生成中...'):
                    try:
                        pdf_data_landscape = create_landscape_pdf(
                            forecast_df=pdf_forecast_df_data,
                            df_weekday=current_results_data.get("weekday"), 
                            df_holiday=current_results_data.get("holiday"),
                            df_all_avg=current_results_data.get("summary"), 
                            chart_data=chart_data_for_graphs,
                            title_prefix=current_filter_title_display, 
                            latest_date=latest_data_date,
                            target_data=target_data, 
                            filter_code=filter_code_for_target, 
                            graph_days=[pdf_graph_days_to_use]
                        )
                        
                        if pdf_data_landscape:
                            filename_pdf_land = f"入院患者数予測_{safe_title_pdf}_{date_str_pdf}_横向き.pdf"
                            st.download_button(
                                label="📥 横向きPDFをダウンロード", 
                                data=pdf_data_landscape, 
                                file_name=filename_pdf_land,
                                mime="application/pdf", 
                                key=landscape_dl_button_key
                            )
                        else: 
                            st.error("❌ 横向きPDFの生成に失敗しました。")
                    except Exception as e:
                        IndividualAnalysisErrorHandler.handle_analysis_error(e)

def show_debug_info():
    """デバッグ情報の表示（開発時のみ）"""
    
    with st.expander("🔧 デバッグ情報"):
        st.write("**セッション状態キー:**")
        individual_keys = [k for k in st.session_state.keys() if k.startswith(INDIVIDUAL_TAB_CONFIG['session_key_prefix'])]
        st.write(individual_keys)
        
        st.write("**統一フィルター状態:**")
        unified_keys = [k for k in st.session_state.keys() if k.startswith('unified_filter')]
        st.write(unified_keys)
        
        # セッション状態クリア機能
        if st.button("🗑️ 個別分析タブセッション状態をクリア", key=get_session_key('clear_session')):
            keys_to_remove = [k for k in st.session_state.keys() if k.startswith(INDIVIDUAL_TAB_CONFIG['session_key_prefix'])]
            for key in keys_to_remove:
                del st.session_state[key]
            st.rerun()

def display_individual_analysis_tab():
    """個別分析タブのメイン表示関数（統一フィルター完全対応版）"""
    
    st.header("📊 個別分析")
    
    # 必要な関数の存在チェック
    if not check_required_functions():
        return
    
    # データ処理状態のチェック
    if 'data_processed' not in st.session_state or not st.session_state.data_processed:
        st.warning("⚠️ まず「データ処理」タブでデータを読み込んでください。")
        return
    
    # セッション状態からデータ取得
    raw_df = st.session_state.get('df')
    target_data = st.session_state.get('target_data')
    latest_data_date_str_from_session = st.session_state.get('latest_data_date_str', pd.Timestamp.now().strftime("%Y年%m月%d日"))
    
    if raw_df is None or raw_df.empty:
        st.error("❌ 分析対象のデータフレームが読み込まれていません。「データ処理」タブを再実行してください。")
        return
    
    # 統一フィルターの適用と状態表示
    try:
        if create_unified_filter_status_card:
            filtered_df, filter_config = create_unified_filter_status_card(raw_df)
            
            # フィルター妥当性チェック
            if validate_unified_filters:
                is_valid, message = validate_unified_filters(raw_df)
                if not is_valid:
                    st.error(f"❌ フィルター設定エラー: {message}")
                    return
            
        else:
            st.warning("⚠️ 統一フィルター機能が利用できません。全データで分析を実行します。")
            filtered_df = raw_df
            filter_config = {}
            
    except Exception as e:
        IndividualAnalysisErrorHandler.handle_filter_error(e)
        return
    
    # データ妥当性チェック
    if not validate_data_for_individual_analysis(filtered_df):
        return
    
    # 最新データ日付の処理
    try:
        if not filtered_df.empty and '日付' in filtered_df.columns:
            latest_data_date_from_df = filtered_df['日付'].max()
            latest_data_date = pd.Timestamp(latest_data_date_from_df).normalize()
        else:
            latest_data_date = pd.to_datetime(latest_data_date_str_from_session, format="%Y年%m月%d日").normalize()
        logger.info(f"個別分析: 予測基準日として {latest_data_date.strftime('%Y-%m-%d')} を使用します。")
    except Exception as e:
        logger.error(f"最新データ日付の処理中にエラー: {e}", exc_info=True)
        st.error(f"⚠️ 最新データ日付の処理中にエラーが発生しました。予測基準日として本日の日付を使用します。")
        latest_data_date = pd.Timestamp.now().normalize()
    
    st.markdown("---")
    
    # 詳細フィルター設定
    filter_type, filter_value_actual, filter_value_display = show_detailed_filter_settings(filtered_df)
    
    # 詳細フィルターの適用
    current_results_data, chart_data_for_graphs, current_filter_title_display, filter_code_for_target = apply_detailed_filters(
        filtered_df, filter_type, filter_value_actual
    )
    
    # 結果の表示
    if not current_results_data or not isinstance(current_results_data, dict) or current_results_data.get("summary") is None:
        st.warning(f"⚠️ 「{current_filter_title_display}」には表示できる集計データがありません。")
        st.info("💡 フィルター条件を見直すか、データの範囲を拡大してください。")
    else:
        st.markdown(f"#### 📊 分析結果: {current_filter_title_display}")
        
        # グラフ表示期間の計算
        selected_days_for_graph = 90  # デフォルト
        pdf_graph_days_to_use = selected_days_for_graph
        
        if chart_data_for_graphs is not None and not chart_data_for_graphs.empty:
            if '日付' in chart_data_for_graphs.columns and not chart_data_for_graphs['日付'].empty:
                min_date_chart_obj = chart_data_for_graphs['日付'].min()
                max_date_chart_obj = chart_data_for_graphs['日付'].max()
                
                if min_date_chart_obj and max_date_chart_obj:
                    calculated_days = (max_date_chart_obj - min_date_chart_obj).days + 1
                    if calculated_days > 0:
                        selected_days_for_graph = calculated_days
                    
                    st.markdown(f"##### 📈 グラフ表示期間: フィルター適用期間全体 ({min_date_chart_obj.strftime('%Y/%m/%d')} - {max_date_chart_obj.strftime('%Y/%m/%d')}, {selected_days_for_graph}日間)")
                else:
                    st.markdown(f"##### 📈 グラフ表示期間: フィルター適用期間全体 ({selected_days_for_graph}日間)")
                
                pdf_graph_days_to_use = selected_days_for_graph
            
            # 分析チャートの表示
            display_analysis_charts(chart_data_for_graphs, current_filter_title_display, selected_days_for_graph, target_data, filter_code_for_target)
        
        # 予測データと集計結果の表示
        display_forecast_and_summary(current_results_data, latest_data_date)
        
        # PDF出力オプションの表示
        display_pdf_export_options(
            current_results_data, chart_data_for_graphs, current_filter_title_display,
            latest_data_date, target_data, filter_code_for_target, pdf_graph_days_to_use,
            filter_type, filter_value_actual
        )
        
        # 統一フィルター情報の再表示
        if get_unified_filter_summary:
            st.markdown("---")
            filter_summary_bottom = get_unified_filter_summary()
            st.info(f"🔍 適用中の統一フィルター: {filter_summary_bottom}")
    
    # デバッグ情報の表示（開発時のみ）
    if st.session_state.get('debug_mode', False):
        show_debug_info()

# メイン実行
if __name__ == "__main__":
    display_individual_analysis_tab()