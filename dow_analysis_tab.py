import streamlit as st
import pandas as pd
import numpy as np
import datetime
from datetime import timedelta

# dow_charts.py から必要な関数をインポート
try:
    from dow_charts import (
        get_dow_data,
        create_dow_chart,
        calculate_dow_summary,
        create_dow_heatmap,
        DOW_LABELS
    )
except ImportError:
    st.error("dow_charts.py が見つからないか、必要な関数・変数が定義されていません。")
    # フォールバックとしてダミー関数や変数を定義
    get_dow_data = lambda *args, **kwargs: pd.DataFrame()
    create_dow_chart = lambda *args, **kwargs: None
    calculate_dow_summary = lambda *args, **kwargs: pd.DataFrame()
    create_dow_heatmap = lambda *args, **kwargs: None
    DOW_LABELS = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日']

# utils.pyから病棟関連の関数をインポート
from utils import (
    create_ward_name_mapping,
    get_ward_display_name,
    create_ward_display_options,
    initialize_ward_mapping
)

def display_dow_analysis_tab(df, start_date, end_date, common_config=None):
    """
    曜日別入退院分析タブの表示
    
    Parameters:
    -----------
    df : pd.DataFrame
        分析対象のデータフレーム (st.session_state.df を想定)
    start_date : datetime.date or pd.Timestamp
        分析開始日 (st.session_state.sidebar_start_date を想定)
    end_date : datetime.date or pd.Timestamp
        分析終了日 (st.session_state.sidebar_end_date を想定)
    common_config : dict or None, default None
        共通設定（現在は未使用だが将来的な拡張のため残す）
    """
    st.header("📆 曜日別入退院分析")
    
    metric_specific_tips = []  # ここで初期化

    if df is None or df.empty:
        st.warning("データが読み込まれていません。「データ処理」タブでデータを読み込んでください。")
        return

    # 列名確認 (dow_charts.py に移譲しても良いが、ここでも基本的なチェックは有用)
    required_cols_for_tab = ['日付', '病棟コード', '診療科名', 
                             '総入院患者数', '総退院患者数', # get_dow_data のデフォルトで使用
                             '入院患者数', '緊急入院患者数', '死亡患者数', '在院患者数']  # '在院患者数'を追加
    
    missing_cols = [col for col in required_cols_for_tab if col not in df.columns]
    if missing_cols:
        st.error(f"曜日別分析に必要な列が不足しています: {', '.join(missing_cols)}")
        st.info("データ処理タブでデータが正しく読み込まれ、'総入院患者数' や '総退院患者数' が計算されているか確認してください。")
        return
        
    # 病棟マッピングの初期化
    initialize_ward_mapping(df)
    
    # --- サイドバーでの設定取得 (app.py で st.session_state に保存されている前提) ---
    # または、app.py から引数として渡されても良い
    # ここでは、app.py の曜日別分析タブ用の設定キーを参照すると仮定
    
    st.sidebar.markdown("<hr style='margin-top:1rem; margin-bottom:0.5rem;'>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-title' style='font-size:1.1rem; margin-bottom:0.5rem;'>曜日別入退院分析 設定</div>", unsafe_allow_html=True)
    
    selected_unit_dow = st.sidebar.selectbox(
        "集計単位:", 
        ['病院全体', '診療科別', '病棟別'], 
        index=0,
        key="dow_unit_selectbox"
    )
    
    target_items_dow = []
    if selected_unit_dow == '病棟別':
        available_items_dow = sorted(df['病棟コード'].astype(str).unique())
        
        # 病棟名マッピングを取得
        ward_mapping = st.session_state.get('ward_mapping', {})
        
        # 表示オプションを作成
        ward_options, option_to_code = create_ward_display_options(available_items_dow, ward_mapping)
        
        # デフォルト選択（最大2つ）
        default_ward_options = ward_options[:min(2, len(ward_options))] if ward_options else []
        
        selected_ward_options = st.sidebar.multiselect(
            "対象病棟:", 
            ward_options, 
            default=default_ward_options, 
            key="dow_target_wards_multiselect", 
            help="複数選択可（チャート表示は最大5つ程度推奨）"
        )
        
        # 選択された表示名から病棟コードを取得
        target_items_dow = [option_to_code[option] for option in selected_ward_options]
        
    elif selected_unit_dow == '診療科別':
        available_items_dow = sorted(df['診療科名'].astype(str).unique())
        default_depts = available_items_dow[:min(2, len(available_items_dow))] if available_items_dow else []
        target_items_dow = st.sidebar.multiselect(
            "対象診療科:", available_items_dow, 
            default=default_depts, 
            key="dow_target_depts_multiselect", 
            help="複数選択可（チャート表示は最大5つ程度推奨）"
        )
    
    # 曜日別チャート用の指標選択
    chart_metrics_options = ['総入院患者数', '総退院患者数', '入院患者数', '緊急入院患者数', '退院患者数', '死亡患者数', '在院患者数']  # '在院患者数'を追加
    # dfに存在する列のみを選択肢とする
    valid_chart_metrics_options = [opt for opt in chart_metrics_options if opt in df.columns]
    
    selected_chart_metrics = st.sidebar.multiselect(
        "チャート表示指標:",
        valid_chart_metrics_options,
        default=[opt for opt in ['総入院患者数', '総退院患者数'] if opt in valid_chart_metrics_options], # デフォルト
        key="dow_chart_metrics_multiselect"
    )

    selected_aggregation_method_ui = st.sidebar.selectbox(
        "集計方法 (チャート/サマリー共通):", 
        ["曜日別 平均患者数/日", "曜日別 合計患者数"], 
        index=0, 
        key="dow_aggregation_selectbox"
    )
    metric_type_for_logic = 'average' if selected_aggregation_method_ui == "曜日別 平均患者数/日" else 'sum'

    # --- メイン表示エリア ---
    st.markdown(f"<div style='font-size: 14px; color: #666; margin-bottom:1rem;'>選択期間: {start_date.strftime('%Y年%m月%d日')} ～ {end_date.strftime('%Y年%m月%d日')}</div>", unsafe_allow_html=True)

    if selected_unit_dow != '病院全体' and not target_items_dow:
        st.warning(f"分析対象の{selected_unit_dow.replace('別','')}をサイドバーで選択してください。")
        return
    if not selected_chart_metrics:
        st.warning("チャートに表示する指標を1つ以上選択してください。")
        # return # 指標がなくてもサマリーは表示できるようにするならコメントアウト

    # 1. 曜日別チャートデータの取得と表示
    st.markdown(f"<div class='chart-title'>曜日別 患者数パターン ({selected_aggregation_method_ui})</div>", unsafe_allow_html=True)
    if selected_chart_metrics: # 選択された指標がある場合のみチャート生成
        dow_data_for_chart = get_dow_data(
            df=df,
            unit_type=selected_unit_dow,
            target_items=target_items_dow,
            start_date=start_date,
            end_date=end_date,
            metric_type=metric_type_for_logic,
            patient_cols_to_analyze=selected_chart_metrics
        )

        if dow_data_for_chart is not None and not dow_data_for_chart.empty:
            if create_dow_chart:
                dow_chart_fig = create_dow_chart(
                    dow_data_melted=dow_data_for_chart, # get_dow_data は melt 済みデータを返す
                    unit_type=selected_unit_dow,
                    target_items=target_items_dow,
                    metric_type=metric_type_for_logic,
                    patient_cols_to_analyze=selected_chart_metrics
                )
                if dow_chart_fig:
                    st.plotly_chart(dow_chart_fig, use_container_width=True)
                else:
                    st.info("曜日別チャートを生成できませんでした。")
            else:
                st.warning("チャート生成関数 (create_dow_chart) が利用できません。")
        else:
            st.info("曜日別チャートを表示するためのデータがありません。")
    else:
        st.info("チャートに表示する指標が選択されていません。")


    # 2. 曜日別詳細サマリーデータの取得と表示
    st.markdown(f"<div class='chart-title' style='margin-top: 2rem;'>曜日別 詳細サマリー ({selected_aggregation_method_ui})</div>", unsafe_allow_html=True)
    
    group_by_col_name = None
    if selected_unit_dow == '病棟別': group_by_col_name = '病棟コード'
    elif selected_unit_dow == '診療科別': group_by_col_name = '診療科名'

    if calculate_dow_summary:
        summary_df = calculate_dow_summary(
            df=df,
            start_date=start_date,
            end_date=end_date,
            group_by_column=group_by_col_name,
            target_items=target_items_dow
        )

        if summary_df is not None and not summary_df.empty:
            cols_to_show_summary = ['集計単位', '曜日名', '集計日数']
            format_dict_summary = {'集計日数': "{:.0f}"}
            
            # 表示する指標列を動的に選択
            # calculate_dow_summary は '平均{指標名}' と '{指標名}合計' の両方を持つ
            base_metrics_for_summary = ['入院患者数', '緊急入院患者数', '総入院患者数', 
                                        '退院患者数', '死亡患者数', '総退院患者数', '在院患者数']  # '在院患者数'を追加

            if metric_type_for_logic == 'average':
                for bm in base_metrics_for_summary:
                    col_name = f"平均{bm}"
                    if col_name in summary_df.columns:
                        cols_to_show_summary.append(col_name)
                        format_dict_summary[col_name] = "{:.1f}"
            else: # sum
                for bm in base_metrics_for_summary:
                    col_name = f"{bm}合計"
                    if col_name in summary_df.columns:
                        cols_to_show_summary.append(col_name)
                        format_dict_summary[col_name] = "{:.0f}"
            
            # 率の列を追加
            rate_cols = ['緊急入院率', '死亡退院率']
            for rc in rate_cols:
                if rc in summary_df.columns:
                    cols_to_show_summary.append(rc)
                    format_dict_summary[rc] = "{:.1f}%"
            
            # 実際に存在する列のみにフィルタ
            cols_to_show_summary = [col for col in cols_to_show_summary if col in summary_df.columns]

            if cols_to_show_summary and len(cols_to_show_summary) > 3: # 基本列以外に表示する指標がある場合
                st.dataframe(
                    summary_df[cols_to_show_summary].style.format(format_dict_summary),
                    height=min(len(summary_df) * 38 + 40, 600) # 表示行数に応じて高さを調整
                )
                # CSVダウンロード
                csv_summary = summary_df[cols_to_show_summary].to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="サマリーデータをCSVダウンロード",
                    data=csv_summary,
                    file_name=f"曜日別サマリー_{selected_unit_dow}_{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.csv",
                    mime='text/csv',
                )
            else:
                st.info("表示するサマリー指標がありません。")
        else:
            st.info("曜日別サマリーデータを表示できませんでした。")
    else:
        st.warning("サマリー計算関数 (calculate_dow_summary) が利用できません。")

    # 3. ヒートマップ表示 (複数選択時)
    if selected_unit_dow != '病院全体' and target_items_dow and len(target_items_dow) > 1:
        st.markdown(f"<div class='chart-title' style='margin-top: 2rem;'>曜日別 ヒートマップ ({selected_aggregation_method_ui})</div>", unsafe_allow_html=True)
        
        heatmap_metric_options = ['入院患者数', '緊急入院患者数', '総入院患者数', '退院患者数', '死亡患者数', '総退院患者数']
        # summary_df に存在する指標から選択肢を生成
        # (平均か合計かは create_dow_heatmap 内部で判定される想定)
        
        selected_heatmap_metric = st.selectbox(
            "ヒートマップ表示指標:",
            heatmap_metric_options,
            index=heatmap_metric_options.index('総入院患者数') if '総入院患者数' in heatmap_metric_options else 0,
            key="dow_heatmap_metric_select"
        )

        if create_dow_heatmap and summary_df is not None and not summary_df.empty:
            heatmap_fig = create_dow_heatmap(
                dow_data=summary_df, # calculate_dow_summary の結果を使用
                metric=selected_heatmap_metric, # '平均'や'合計'はつけない基本名
                unit_type=selected_unit_dow
            )
            if heatmap_fig:
                st.plotly_chart(heatmap_fig, use_container_width=True)
            else:
                st.info("ヒートマップを生成できませんでした。データまたは指標を確認してください。")
        elif summary_df is None or summary_df.empty:
             st.info("ヒートマップの元となるサマリーデータがありません。")
        else:
            st.warning("ヒートマップ生成関数 (create_dow_heatmap) が利用できません。")
    
    # 分析インサイト
    st.markdown("<div class='section-title'>分析インサイトと傾向</div>", unsafe_allow_html=True)
    
    if summary_df is not None and not summary_df.empty:
        # 基本的な週間パターンの分析
        insights = []
        
        # 入院患者数の曜日パターン
        if '平均入院患者数' in summary_df.columns:
            # 平均で分析
            max_admission_day = summary_df.loc[summary_df['平均入院患者数'].idxmax()]
            min_admission_day = summary_df.loc[summary_df['平均入院患者数'].idxmin()]
            
            insights.append(
                f"入院患者数は**{max_admission_day['曜日名']}曜日**が最も多く（平均 {max_admission_day['平均入院患者数']:.1f}人/日）、"
                f"**{min_admission_day['曜日名']}曜日**が最も少ない（平均 {min_admission_day['平均入院患者数']:.1f}人/日）傾向があります。"
            )
        elif '入院患者数合計' in summary_df.columns:
            # 合計で分析
            max_admission_day = summary_df.loc[summary_df['入院患者数合計'].idxmax()]
            min_admission_day = summary_df.loc[summary_df['入院患者数合計'].idxmin()]
            
            insights.append(
                f"入院患者数は**{max_admission_day['曜日名']}曜日**が最も多く（合計 {max_admission_day['入院患者数合計']:.0f}人）、"
                f"**{min_admission_day['曜日名']}曜日**が最も少ない（合計 {min_admission_day['入院患者数合計']:.0f}人）傾向があります。"
            )
        
        # 退院患者数の曜日パターン
        if '平均退院患者数' in summary_df.columns:
            # 平均で分析
            max_discharge_day = summary_df.loc[summary_df['平均退院患者数'].idxmax()]
            min_discharge_day = summary_df.loc[summary_df['平均退院患者数'].idxmin()]
            
            insights.append(
                f"退院患者数は**{max_discharge_day['曜日名']}曜日**が最も多く（平均 {max_discharge_day['平均退院患者数']:.1f}人/日）、"
                f"**{min_discharge_day['曜日名']}曜日**が最も少ない（平均 {min_discharge_day['平均退院患者数']:.1f}人/日）傾向があります。"
            )
        elif '退院患者数合計' in summary_df.columns:
            # 合計で分析
            max_discharge_day = summary_df.loc[summary_df['退院患者数合計'].idxmax()]
            min_discharge_day = summary_df.loc[summary_df['退院患者数合計'].idxmin()]
            
            insights.append(
                f"退院患者数は**{max_discharge_day['曜日名']}曜日**が最も多く（合計 {max_discharge_day['退院患者数合計']:.0f}人）、"
                f"**{min_discharge_day['曜日名']}曜日**が最も少ない（合計 {min_discharge_day['退院患者数合計']:.0f}人）傾向があります。"
            )
        
        # 緊急入院の曜日パターン
        if '平均緊急入院患者数' in summary_df.columns: # または合計でも良い
            max_emergency_day = summary_df.loc[summary_df['平均緊急入院患者数'].idxmax()]
            insights.append(
                f"緊急入院は**{max_emergency_day['曜日名']}曜日**に最も多く発生しています（平均 {max_emergency_day['平均緊急入院患者数']:.1f}人/日）。"
            )
        
        # 週末と平日の比較
        if '曜日番号' in summary_df.columns: # '曜日番号' 列の存在を確認
            weekend_data = summary_df[summary_df['曜日番号'] >= 5].copy()  # 土日 (5,6)
            weekday_data = summary_df[summary_df['曜日番号'] < 5].copy()   # 月～金 (0,1,2,3,4)

            # 以降の平日・週末比較ロジックも、この if 文に合わせてインデントを調整
            if not weekend_data.empty and not weekday_data.empty and \
               '平均入院患者数' in weekend_data.columns and '平均入院患者数' in weekday_data.columns:
                
                avg_weekend_admission = weekend_data['平均入院患者数'].mean()
                avg_weekday_admission = weekday_data['平均入院患者数'].mean()

                if pd.notna(avg_weekend_admission) and pd.notna(avg_weekday_admission) and avg_weekday_admission > 0: # avg_weekday_admission > 0 で比較、ゼロ除算とNaNを避ける
                    diff_percent = (avg_weekday_admission - avg_weekend_admission) / avg_weekend_admission * 100 if avg_weekend_admission > 0 else np.nan # ゼロ除算回避

                    if pd.notna(diff_percent): # diff_percent が計算できた場合のみ
                        if diff_percent > 20:
                            insights.append(
                                f"平日の入院患者数（平均 {avg_weekday_admission:.1f}人/日）は、"
                                f"週末（平均 {avg_weekend_admission:.1f}人/日）と比較して**{diff_percent:.1f}%多く**、"
                                f"明確な平日/週末パターンが見られます。"
                            )
                        elif diff_percent < -20:
                             insights.append(
                                f"週末の入院患者数（平均 {avg_weekend_admission:.1f}人/日）は、"
                                f"平日（平均 {avg_weekday_admission:.1f}人/日）と比較して**{abs(diff_percent):.1f}%多く**、"
                                f"特徴的な週末集中パターンが見られます。"
                            )

            # 同様に退院患者数の比較も '曜日番号' を使う
            if not weekend_data.empty and not weekday_data.empty and \
               '平均退院患者数' in weekend_data.columns and '平均退院患者数' in weekday_data.columns:
                avg_weekend_discharge = weekend_data['平均退院患者数'].mean()
                avg_weekday_discharge = weekday_data['平均退院患者数'].mean()
                if pd.notna(avg_weekend_discharge) and pd.notna(avg_weekday_discharge) and avg_weekday_discharge > 0: # avg_weekday_discharge > 0 で比較
                    if avg_weekend_discharge < avg_weekday_discharge * 0.3:
                        insights.append( # insights リストに追加
                            f"週末の退院が極めて少なくなっています（週末平均 {avg_weekend_discharge:.1f}人/日 vs 平日平均 {avg_weekday_discharge:.1f}人/日）。週末の退院支援体制を強化することで、"
                            f"患者の利便性向上と月曜日の業務集中を緩和できる可能性があります。"
                        )
        else:
            st.warning("インサイト生成に必要な '曜日番号' 列がサマリーデータにありません。")
        
        # インサイトの表示
        if insights:
            st.markdown("<div class='info-card'>", unsafe_allow_html=True)
            st.markdown("#### <span style='color: #191970;'>インサイト</span>", unsafe_allow_html=True) # タイトルに色付けの例
            for insight in insights:
                st.markdown(f"<p style='margin-bottom: 0.5em;'>- {insight}</p>", unsafe_allow_html=True) # 各インサイトの行間調整
            st.markdown("</div>", unsafe_allow_html=True)
            
            # 運用提案 (insights の内容に基づいて表示するか、あるいは固定の提案を表示)
            # ここでは固定の提案の例
            st.markdown("<div class='success-card' style='margin-top: 1em;'>", unsafe_allow_html=True)
            st.markdown("#### <span style='color: #006400;'>運用改善のためのヒント</span>", unsafe_allow_html=True)
            # 以下は運用提案の例です。実際のデータや分析結果に基づいて内容を調整してください。
            if summary_df is not None and not summary_df.empty and \
               '平均入院患者数' in summary_df.columns and \
               '平均退院患者数' in summary_df.columns and \
               '曜日名' in summary_df.columns:
                
                max_adm_day_series = summary_df.loc[summary_df['平均入院患者数'].idxmax()]
                max_dis_day_series = summary_df.loc[summary_df['平均退院患者数'].idxmax()]

                if max_adm_day_series['曜日名'] == max_dis_day_series['曜日名']:
                    st.markdown(
                        f"<p style='margin-bottom: 0.5em;'>- 入院と退院のピークが同じ**{max_adm_day_series['曜日名']}曜日**に集中している可能性があります。"
                        f"業務負荷を分散するために、予定入院の一部を他の曜日にずらす、または週末の退院支援を強化することを検討できます。</p>", unsafe_allow_html=True
                    )
                
                if '曜日番号' in summary_df.columns: # 再度 weekday_data, weekend_data を使用するためチェック
                    # この時点で weekend_data, weekday_data が存在することを期待
                    if not weekend_data.empty and not weekday_data.empty:
                         if '平均退院患者数' in weekend_data.columns and '平均退院患者数' in weekday_data.columns and \
                            pd.notna(weekday_data['平均退院患者数'].mean()) and weekday_data['平均退院患者数'].mean() > 0 and \
                            pd.notna(weekend_data['平均退院患者数'].mean()) and \
                            weekend_data['平均退院患者数'].mean() < weekday_data['平均退院患者数'].mean() * 0.3:
                            st.markdown(
                                f"<p style='margin-bottom: 0.5em;'>- 週末の退院が平日に比べて著しく少ないようです。週末の退院プロセスを見直し、"
                                f"スタッフ配置や関連部門との連携を強化することで、患者さんの利便性向上や月曜日の業務負荷軽減に繋がる可能性があります。</p>", unsafe_allow_html=True
                            )
            st.markdown("</div>", unsafe_allow_html=True)

        else: # insights リストが空の場合
            st.info("分析インサイトを生成するための十分なデータパターンが見つかりませんでした。")
    else: # summary_df が空の場合
        st.info("分析インサイトを生成するためのサマリーデータがありません。")

    # 期間比較の設定を追加
    st.markdown(f"<div class='chart-title' style='margin-top: 2rem;'>期間比較</div>", unsafe_allow_html=True)
    
    enable_comparison = st.checkbox("別の期間と比較する", key="dow_enable_comparison")
    
    if enable_comparison:
        # 比較用の期間選択UI
        col1_comp, col2_comp = st.columns(2)
        with col1_comp:
            # 比較期間の開始日（デフォルトは現在の期間の1年前）
            default_comp_start = (start_date - timedelta(days=365)) if isinstance(start_date, datetime.date) else start_date - pd.Timedelta(days=365)
            comp_start_date = st.date_input(
                "比較期間：開始日", 
                value=default_comp_start,
                min_value=df['日付'].min().date(),
                max_value=df['日付'].max().date(),
                key="dow_comparison_start_date"
            )
        
        with col2_comp:
            # 比較期間の終了日（期間の長さを同じにするデフォルト）
            period_length = (end_date - start_date).days if isinstance(start_date, datetime.date) else (end_date - start_date).days
            default_comp_end = comp_start_date + timedelta(days=period_length)
            # データの最大日付を超えないように調整
            if default_comp_end > df['日付'].max().date():
                default_comp_end = df['日付'].max().date()
                
            comp_end_date = st.date_input(
                "比較期間：終了日", 
                value=default_comp_end,
                min_value=df['日付'].min().date(),
                max_value=df['日付'].max().date(),
                key="dow_comparison_end_date"
            )
        
        # 期間の長さを現在の期間と揃えるボタン
        if st.button("現在期間と同じ長さに設定", key="set_same_length"):
            period_length = (end_date - start_date).days if isinstance(start_date, datetime.date) else (end_date - start_date).days
            comp_start_date = st.session_state.dow_comparison_start_date
            comp_end_date = comp_start_date + timedelta(days=period_length)
            
            # データの範囲内に収める
            if comp_end_date > df['日付'].max().date():
                comp_end_date = df['日付'].max().date()
                comp_start_date = comp_end_date - timedelta(days=period_length)
                # さらに開始日がデータ範囲外になった場合の調整
                if comp_start_date < df['日付'].min().date():
                    comp_start_date = df['日付'].min().date()
            
            # セッション状態を更新
            st.session_state.dow_comparison_start_date = comp_start_date
            st.session_state.dow_comparison_end_date = comp_end_date
            st.experimental_rerun()  # 画面を再読み込みして値を反映
        
        if comp_start_date > comp_end_date:
            st.error("比較期間の終了日は開始日以降に設定してください。")
            return
        
        # 既存のグラフ生成時と同様にデータを取得するが、比較期間用
        if selected_chart_metrics:
            comp_dow_data = get_dow_data(
                df=df,
                unit_type=selected_unit_dow,
                target_items=target_items_dow,
                start_date=comp_start_date,
                end_date=comp_end_date,
                metric_type=metric_type_for_logic,
                patient_cols_to_analyze=selected_chart_metrics
            )
            
            # 比較用グラフの生成
            st.markdown(f"<div class='chart-title'>期間比較：曜日別 患者数パターン</div>", unsafe_allow_html=True)
            
            # 表示モードの選択
            comparison_display_mode = st.radio(
                "比較表示モード:",
                ["縦に並べて表示", "1つのグラフで比較"],
                key="dow_comparison_display_mode"
            )
            
            if comp_dow_data is not None and not comp_dow_data.empty:
                if comparison_display_mode == "縦に並べて表示":
                    # 現在期間と比較期間のグラフを生成
                    current_chart_fig = create_dow_chart(
                        dow_data_melted=dow_data_for_chart,
                        unit_type=selected_unit_dow,
                        target_items=target_items_dow,
                        metric_type=metric_type_for_logic,
                        patient_cols_to_analyze=selected_chart_metrics,
                        title_prefix="現在期間"  # タイトルに期間識別子を追加
                    )
                    
                    comp_chart_fig = create_dow_chart(
                        dow_data_melted=comp_dow_data,
                        unit_type=selected_unit_dow,
                        target_items=target_items_dow,
                        metric_type=metric_type_for_logic,
                        patient_cols_to_analyze=selected_chart_metrics,
                        title_prefix="比較期間"  # タイトルに期間識別子を追加
                    )
                    
                    # 2つのグラフを縦に表示
                    if current_chart_fig and comp_chart_fig:
                        st.plotly_chart(current_chart_fig, use_container_width=True)
                        st.markdown(f"<div style='text-align: center; margin-bottom: 1rem;'>↓ 比較 ↓</div>", unsafe_allow_html=True)
                        st.plotly_chart(comp_chart_fig, use_container_width=True)
                        
                        # 比較分析のインサイト
                        st.markdown("<div class='info-card'>", unsafe_allow_html=True)
                        st.markdown("#### <span style='color: #191970;'>期間比較インサイト</span>", unsafe_allow_html=True)
                        st.markdown("現在期間と比較期間の曜日パターンを比較して、変化点や傾向の違いを確認できます。", unsafe_allow_html=True)
                        st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        st.info("比較グラフを生成できませんでした。")
                else:  # 1つのグラフで比較
                    # 2つの期間のデータを結合
                    if dow_data_for_chart is not None and comp_dow_data is not None:
                        # 期間情報を追加
                        # より簡潔な表示のために期間名を設定
                        current_period_name = f"現在期間 ({start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')})"
                        comp_period_name = f"比較期間 ({comp_start_date.strftime('%Y/%m/%d')}～{comp_end_date.strftime('%Y/%m/%d')})"
                        
                        dow_data_for_chart['期間'] = current_period_name
                        comp_dow_data['期間'] = comp_period_name
                        
                        # データを結合
                        combined_data = pd.concat([dow_data_for_chart, comp_dow_data], ignore_index=True)
                        
                        # 結合したデータで1つのグラフを作成
                        import plotly.express as px
                        
                        # カテゴリカル型として曜日を設定
                        combined_data['曜日'] = pd.Categorical(combined_data['曜日'], categories=DOW_LABELS, ordered=True)
                        
                        unit_suffix = "平均患者数/日" if metric_type_for_logic == 'average' else "合計患者数"
                        y_axis_title = f"患者数 ({unit_suffix})"
                        
                        num_unique_units = len(combined_data['集計単位名'].unique())
                        
                        # グラフの作成方法を選択
                        graph_layout = st.radio(
                            "グラフ表示方法:",
                            ["縦に期間を分けて表示", "横に並べて表示", "期間を同じグラフ内で並べて表示"],
                            key="dow_comparison_graph_layout"
                        )
                        
                        if graph_layout == "縦に期間を分けて表示":
                            # 期間ごとに行を分けるレイアウト
                            if num_unique_units == 1 or selected_unit_dow == '病院全体':
                                # 病院全体または単一ユニットの場合
                                combined_fig = px.bar(
                                    combined_data,
                                    x='曜日', 
                                    y='患者数',
                                    color='指標タイプ',
                                    barmode='group',
                                    facet_row='期間',     # 期間ごとに行を分ける
                                    labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                    category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics,
                                                    "期間": [current_period_name, comp_period_name]} 
                                )
                                
                                # Y軸の範囲を揃える
                                combined_fig.update_yaxes(matches=None)
                                max_y_value = combined_data['患者数'].max() * 1.1  # 余白のために10%増
                                combined_fig.update_yaxes(range=[0, max_y_value])
                                
                            else:
                                # 複数ユニットの場合
                                combined_fig = px.bar(
                                    combined_data,
                                    x='曜日', 
                                    y='患者数',
                                    color='指標タイプ',
                                    barmode='group',
                                    facet_row='期間',     # 期間ごとに行を分ける
                                    facet_col='集計単位名', # 集計単位ごとに列を分ける
                                    facet_col_wrap=min(num_unique_units, 2),
                                    labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                    category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics,
                                                    "期間": [current_period_name, comp_period_name]} 
                                )
                                # 集計単位ラベルの調整
                                combined_fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
                                
                                # Y軸の範囲を各集計単位ごとに揃える
                                y_max_per_unit = combined_data.groupby('集計単位名')['患者数'].max()
                                for unit_name in y_max_per_unit.index:
                                    unit_max = y_max_per_unit[unit_name] * 1.1  # 余白のために10%増
                                    combined_fig.for_each_yaxis(lambda yaxis: yaxis.update(range=[0, unit_max]) 
                                                            if yaxis.title.text.endswith(f"={unit_name}") else None)
                            
                            # グラフの高さを調整（ファセットの数に基づいて）
                            num_facet_rows = 2  # 期間が2つあるため
                            if num_unique_units > 1 and selected_unit_dow != '病院全体':
                                num_facet_cols = min(num_unique_units, 2)
                                plot_height = 250 * num_facet_rows * num_facet_cols
                            else:
                                plot_height = 250 * num_facet_rows
                            
                        elif graph_layout == "横に並べて表示":
                            # 期間ごとに列を分けるレイアウト
                            if num_unique_units == 1 or selected_unit_dow == '病院全体':
                                # 病院全体または単一ユニットの場合
                                combined_fig = px.bar(
                                    combined_data,
                                    x='曜日', 
                                    y='患者数',
                                    color='指標タイプ',
                                    barmode='group',
                                    facet_col='期間',     # 期間ごとに列を分ける
                                    labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                    category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics,
                                                    "期間": [current_period_name, comp_period_name]} 
                                )
                                
                                # Y軸の範囲を揃える
                                combined_fig.update_yaxes(matches=None)
                                max_y_value = combined_data['患者数'].max() * 1.1  # 余白のために10%増
                                combined_fig.update_yaxes(range=[0, max_y_value])
                                
                            else:
                                # 複数ユニットの場合
                                # ユニットを行、期間を列にする
                                combined_fig = px.bar(
                                    combined_data,
                                    x='曜日', 
                                    y='患者数',
                                    color='指標タイプ',
                                    barmode='group',
                                    facet_col='期間',     # 期間ごとに列を分ける
                                    facet_row='集計単位名', # 集計単位ごとに行を分ける
                                    labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                    category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics,
                                                    "期間": [current_period_name, comp_period_name]} 
                                )
                                # 集計単位ラベルの調整
                                combined_fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
                                
                                # Y軸の範囲を各集計単位ごとに揃える
                                for unit_name in combined_data['集計単位名'].unique():
                                    unit_data = combined_data[combined_data['集計単位名'] == unit_name]
                                    unit_max = unit_data['患者数'].max() * 1.1  # 余白のために10%増
                                    for i in range(2):  # 2期間
                                        row = combined_data['集計単位名'].unique().tolist().index(unit_name)
                                        combined_fig.update_yaxes(range=[0, unit_max], row=row, col=i)
                            
                            # グラフの高さを調整（ファセットの数に基づいて）
                            if num_unique_units > 1 and selected_unit_dow != '病院全体':
                                plot_height = 250 * num_unique_units
                            else:
                                plot_height = 400
                        
                        else:  # "期間を同じグラフ内で並べて表示"
                            # 期間を色分けするか、パターンを使うかを選択
                            bar_style = st.radio(
                                "バースタイル:",
                                ["期間を色分け", "指標タイプを色分け"],
                                key="dow_comparison_bar_style"
                            )
                            
                            if bar_style == "期間を色分け":
                                # 期間を色分けし、指標タイプでグループ化
                                if num_unique_units == 1 or selected_unit_dow == '病院全体':
                                    combined_fig = px.bar(
                                        combined_data,
                                        x='曜日', 
                                        y='患者数',
                                        color='期間',
                                        barmode='group',
                                        facet_col='指標タイプ',  # 指標タイプごとに列を分ける
                                        labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                        category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics,
                                                        "期間": [current_period_name, comp_period_name]} 
                                    )
                                else:
                                    # 複数ユニットの場合、特定の指標に絞って表示
                                    if len(selected_chart_metrics) > 1:
                                        selected_metric_for_display = st.selectbox(
                                            "表示する指標:",
                                            selected_chart_metrics,
                                            key="dow_comparison_metric_selector"
                                        )
                                        metric_filtered_data = combined_data[combined_data['指標タイプ'] == selected_metric_for_display]
                                    else:
                                        selected_metric_for_display = selected_chart_metrics[0]
                                        metric_filtered_data = combined_data
                                    
                                    combined_fig = px.bar(
                                        metric_filtered_data,
                                        x='曜日', 
                                        y='患者数',
                                        color='期間',
                                        barmode='group',
                                        facet_col='集計単位名',  # 集計単位ごとに列を分ける
                                        facet_col_wrap=min(num_unique_units, 3),
                                        labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                        category_orders={"曜日": DOW_LABELS, "期間": [current_period_name, comp_period_name]} 
                                    )
                                    # 集計単位ラベルの調整
                                    combined_fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
                                    
                                    # Y軸の範囲を各集計単位ごとに設定
                                    for unit_name in metric_filtered_data['集計単位名'].unique():
                                        unit_data = metric_filtered_data[metric_filtered_data['集計単位名'] == unit_name]
                                        unit_max = unit_data['患者数'].max() * 1.1  # 余白のために10%増
                                        col_idx = metric_filtered_data['集計単位名'].unique().tolist().index(unit_name) % 3
                                        combined_fig.update_yaxes(range=[0, unit_max], col=col_idx)
                            else:  # "指標タイプを色分け"
                                # 指標タイプを色分けし、期間でグループ化
                                if num_unique_units == 1 or selected_unit_dow == '病院全体':
                                    combined_fig = px.bar(
                                        combined_data,
                                        x='曜日', 
                                        y='患者数',
                                        color='指標タイプ',
                                        barmode='group',
                                        facet_col='期間',  # 期間ごとに列を分ける
                                        labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標', '期間': '分析期間'},
                                        category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics,
                                                        "期間": [current_period_name, comp_period_name]} 
                                    )
                                else:
                                    # 特定の期間を選択
                                    selected_period = st.radio(
                                        "表示する期間:",
                                        [current_period_name, comp_period_name],
                                        key="dow_comparison_period_selector"
                                    )
                                    period_filtered_data = combined_data[combined_data['期間'] == selected_period]
                                    
                                    combined_fig = px.bar(
                                        period_filtered_data,
                                        x='曜日', 
                                        y='患者数',
                                        color='指標タイプ',
                                        barmode='group',
                                        facet_col='集計単位名',  # 集計単位ごとに列を分ける
                                        facet_col_wrap=min(num_unique_units, 3),
                                        labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標'},
                                        category_orders={"曜日": DOW_LABELS, "指標タイプ": selected_chart_metrics} 
                                    )
                                    # 集計単位ラベルの調整
                                    combined_fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
                                    
                                    # タイトルに期間を表示
                                    combined_fig.update_layout(title_text=f"{selected_period} - 曜日別 患者数パターン")
                            
                            # グラフの高さ調整
                            if num_unique_units > 1 and selected_unit_dow != '病院全体':
                                plot_height = 400 * ((num_unique_units + 2) // 3)  # 3列で表示する場合
                            else:
                                if len(selected_chart_metrics) > 1 and bar_style == "期間を色分け":
                                    plot_height = 400 * ((len(selected_chart_metrics) + 2) // 3)  # 指標ごとに分ける場合
                                else:
                                    plot_height = 500
                        
                        # 共通のグラフ設定
                        plot_height = max(plot_height, 500)  # 最小高さを確保
                        plot_height = min(plot_height, 1200)  # 最大高さを制限
                        
                        # グラフのレイアウト調整
                        combined_fig.update_layout(
                            title_text=f"曜日別 患者数パターン ({unit_suffix}) - 期間比較",
                            title_x=0.5,
                            height=plot_height,
                            font=dict(size=12),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
                            bargap=0.2,
                            plot_bgcolor='rgba(0,0,0,0)',
                            margin=dict(l=20, r=20, t=60, b=20),
                        )
                        combined_fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray', categoryorder='array', categoryarray=DOW_LABELS)
                        combined_fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
                        
                        # グラフの表示
                        st.plotly_chart(combined_fig, use_container_width=True)
                        
                        # 期間比較のインサイト
                        st.markdown("<div class='info-card'>", unsafe_allow_html=True)
                        st.markdown("#### <span style='color: #191970;'>期間比較インサイト</span>", unsafe_allow_html=True)
                        
                        # 比較期間データからサマリー計算
                        comp_summary_df = None
                        if calculate_dow_summary:
                            comp_summary_df = calculate_dow_summary(
                                df=df,
                                start_date=comp_start_date,
                                end_date=comp_end_date,
                                group_by_column=group_by_col_name,
                                target_items=target_items_dow
                            )
                        
                        # 詳細な比較分析（サマリーデータがある場合）
                        if summary_df is not None and comp_summary_df is not None and not summary_df.empty and not comp_summary_df.empty:
                            # 比較分析条件：両方のデータに存在する列だけを対象とする
                            current_cols = summary_df.columns
                            comp_cols = comp_summary_df.columns
                            common_cols = [col for col in current_cols if col in comp_cols]
                            
                            # メトリクス列の特定
                            if metric_type_for_logic == 'average':
                                # 平均値の列
                                metric_cols = [col for col in common_cols if col.startswith('平均')]
                            else:
                                # 合計値の列
                                metric_cols = [col for col in common_cols if col.endswith('合計')]
                            
                            # 率の列
                            rate_cols = [col for col in common_cols if col in ['緊急入院率', '死亡退院率']]
                            
                            # 分析対象の列
                            analysis_cols = metric_cols + rate_cols
                            
                            # ユニット別に分析
                            unique_units = summary_df['集計単位'].unique()
                            
                            for unit in unique_units:
                                unit_current = summary_df[summary_df['集計単位'] == unit]
                                unit_comp = comp_summary_df[comp_summary_df['集計単位'] == unit]
                                
                                # データが両方にある場合のみ分析
                                if not unit_current.empty and not unit_comp.empty:
                                    st.markdown(f"##### {unit} の期間比較:", unsafe_allow_html=True)
                                    
                                    # 分析結果を保存するリスト
                                    unit_insights = []
                                    
                                    # 各指標の曜日別変化を分析
                                    for col in analysis_cols:
                                        # 列名から表示名を生成
                                        if col.startswith('平均'):
                                            display_name = col[2:]  # "平均" を除去
                                        elif col.endswith('合計'):
                                            display_name = col[:-2]  # "合計" を除去
                                        else:
                                            display_name = col
                                        
                                        # 最大値の曜日が変わったかチェック
                                        current_max_idx = unit_current[col].idxmax()
                                        comp_max_idx = unit_comp[col].idxmax()
                                        
                                        if current_max_idx is not None and comp_max_idx is not None:
                                            current_max_day = unit_current.loc[current_max_idx, '曜日名']
                                            comp_max_day = unit_comp.loc[comp_max_idx, '曜日名']
                                            
                                            if current_max_day != comp_max_day:
                                                unit_insights.append(
                                                    f"**{display_name}** のピーク曜日が変化しています: "
                                                    f"{comp_max_day}曜日 → {current_max_day}曜日"
                                                )
                                        
                                        # 平均値の変化を計算
                                        current_avg = unit_current[col].mean()
                                        comp_avg = unit_comp[col].mean()
                                        
                                        if pd.notna(current_avg) and pd.notna(comp_avg) and comp_avg != 0:
                                            change_pct = (current_avg - comp_avg) / abs(comp_avg) * 100
                                            
                                            if abs(change_pct) >= 15:  # 15%以上の変化を表示
                                                change_direction = "増加" if change_pct > 0 else "減少"
                                                unit_insights.append(
                                                    f"**{display_name}** の平均値が {abs(change_pct):.1f}% {change_direction}しています"
                                                )
                                        
                                        # 曜日ごとの大きな変化を検出
                                        for dow in DOW_LABELS:
                                            current_dow_data = unit_current[unit_current['曜日名'] == dow]
                                            comp_dow_data = unit_comp[unit_comp['曜日名'] == dow]
                                            
                                            if not current_dow_data.empty and not comp_dow_data.empty:
                                                current_val = current_dow_data[col].iloc[0]
                                                comp_val = comp_dow_data[col].iloc[0]
                                                
                                                if pd.notna(current_val) and pd.notna(comp_val) and comp_val != 0:
                                                    dow_change_pct = (current_val - comp_val) / abs(comp_val) * 100
                                                    
                                                    if abs(dow_change_pct) >= 30:  # 30%以上の大きな変化を表示
                                                        change_direction = "増加" if dow_change_pct > 0 else "減少"
                                                        unit_insights.append(
                                                            f"**{dow}** の **{display_name}** が大きく変化: "
                                                            f"{comp_val:.1f} → {current_val:.1f} ({abs(dow_change_pct):.1f}% {change_direction})"
                                                        )
                                    
                                    # 分析結果の表示
                                    if unit_insights:
                                        for insight in unit_insights:
                                            st.markdown(f"- {insight}", unsafe_allow_html=True)
                                    else:
                                        st.markdown("- 顕著な変化は見られません", unsafe_allow_html=True)
                                    
                                    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
                            
                            # 週末/平日パターンの変化分析
                            st.markdown("##### 週末/平日パターンの変化:", unsafe_allow_html=True)
                            
                            weekend_pattern_insights = []
                            
                            for unit in unique_units:
                                unit_current = summary_df[summary_df['集計単位'] == unit]
                                unit_comp = comp_summary_df[comp_summary_df['集計単位'] == unit]
                                
                                if '曜日番号' in unit_current.columns and '曜日番号' in unit_comp.columns:
                                    # 現在期間の週末/平日データ
                                    current_weekend = unit_current[unit_current['曜日番号'] >= 5]
                                    current_weekday = unit_current[unit_current['曜日番号'] < 5]
                                    
                                    # 比較期間の週末/平日データ
                                    comp_weekend = unit_comp[unit_comp['曜日番号'] >= 5]
                                    comp_weekday = unit_comp[unit_comp['曜日番号'] < 5]
                                    
                                    # 主要メトリクスの分析
                                    for col in ['平均入院患者数', '平均退院患者数']:
                                        if col in unit_current.columns and col in unit_comp.columns:
                                            # 表示名を生成
                                            display_name = col[2:]  # "平均" を除去
                                            
                                            # 現在期間の週末/平日比
                                            current_weekend_avg = current_weekend[col].mean() if not current_weekend.empty else None
                                            current_weekday_avg = current_weekday[col].mean() if not current_weekday.empty else None
                                            
                                            # 比較期間の週末/平日比
                                            comp_weekend_avg = comp_weekend[col].mean() if not comp_weekend.empty else None
                                            comp_weekday_avg = comp_weekday[col].mean() if not comp_weekday.empty else None
                                            
                                            # 週末/平日比の変化を分析
                                            if (pd.notna(current_weekend_avg) and pd.notna(current_weekday_avg) and
                                                pd.notna(comp_weekend_avg) and pd.notna(comp_weekday_avg) and
                                                current_weekday_avg > 0 and comp_weekday_avg > 0):
                                                
                                                current_ratio = current_weekend_avg / current_weekday_avg
                                                comp_ratio = comp_weekend_avg / comp_weekday_avg
                                                
                                                ratio_change = (current_ratio - comp_ratio) / comp_ratio * 100
                                                
                                                if abs(ratio_change) >= 20:  # 20%以上の変化を表示
                                                    if ratio_change > 0:
                                                        weekend_pattern_insights.append(
                                                            f"{unit}の**{display_name}**：週末と平日の差が縮小しています "
                                                            f"（週末/平日比：{comp_ratio:.2f} → {current_ratio:.2f}）"
                                                        )
                                                    else:
                                                        weekend_pattern_insights.append(
                                                            f"{unit}の**{display_name}**：週末と平日の差が拡大しています "
                                                            f"（週末/平日比：{comp_ratio:.2f} → {current_ratio:.2f}）"
                                                        )
                            
                            # 週末/平日パターン変化の表示
                            if weekend_pattern_insights:
                                for insight in weekend_pattern_insights:
                                    st.markdown(f"- {insight}", unsafe_allow_html=True)
                            else:
                                st.markdown("- 週末/平日パターンに顕著な変化は見られません", unsafe_allow_html=True)
                            
                        # 簡易比較（サマリーデータがない場合）
                        else:
                            # グラフデータから簡易分析
                            if selected_chart_metrics:
                                # 指標ごとの全体的な変化率を計算
                                st.markdown("##### 指標ごとの全体的な変化:", unsafe_allow_html=True)
                                
                                for metric in selected_chart_metrics:
                                    current_data = dow_data_for_chart[dow_data_for_chart['指標タイプ'] == metric]
                                    comp_data = comp_dow_data[comp_dow_data['指標タイプ'] == metric]
                                    
                                    if not current_data.empty and not comp_data.empty:
                                        current_avg = current_data['患者数'].mean()
                                        comp_avg = comp_data['患者数'].mean()
                                        
                                        if pd.notna(current_avg) and pd.notna(comp_avg) and comp_avg != 0:
                                            change_pct = (current_avg - comp_avg) / comp_avg * 100
                                            change_direction = "増加" if change_pct > 0 else "減少"
                                            
                                            st.markdown(
                                                f"- **{metric}** の平均値： {comp_avg:.1f} → {current_avg:.1f} "
                                                f"({abs(change_pct):.1f}% {change_direction})"
                                            )
                                        else:
                                            st.markdown(f"- **{metric}** の変化を計算できません（データが不足しています）")
                                
                                # 曜日ごとのパターン変化
                                st.markdown("##### 曜日パターンの変化:", unsafe_allow_html=True)
                                st.markdown("期間間の曜日パターンを比較して、特に変化が大きい曜日や指標に注目することで、運用方法の改善点を見つけられます。", unsafe_allow_html=True)
                            
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        # 期間比較からの運用改善ヒント
                        st.markdown("<div class='success-card' style='margin-top: 1em;'>", unsafe_allow_html=True)
                        st.markdown("#### <span style='color: #006400;'>期間比較からの運用改善ヒント</span>", unsafe_allow_html=True)
                        
                        # 必ず初期化する
                        metric_specific_tips = []
                        
                        st.markdown(
                            "<p style='margin-bottom: 0.5em;'>- 曜日パターンの変化から運用方法の改善効果を評価できます。例えば、週末の退院支援強化策を実施した場合、"
                            "その前後の期間を比較することで効果測定が可能です。</p>", unsafe_allow_html=True
                        )
                        
                        st.markdown(
                            "<p style='margin-bottom: 0.5em;'>- 特定の曜日に患者数が増加している場合、その曜日のスタッフ配置や業務プロセスを見直すことで、より効率的な運用が可能になります。</p>", unsafe_allow_html=True
                        )
                        
                        st.markdown(
                            "<p style='margin-bottom: 0.5em;'>- 期間による変化が大きい場合は、季節性や特定のイベント（例：診療体制の変更、地域の人口動態変化など）の影響を考慮する必要があります。</p>", unsafe_allow_html=True
                        )
                        
                        # メトリクス別の具体的な提案
                        if dow_data_for_chart is not None and comp_dow_data is not None:
                            metric_specific_tips = []
                            
                            # 入院患者数のパターン変化に基づく提案
                            if '入院患者数' in selected_chart_metrics or '総入院患者数' in selected_chart_metrics:
                                target_metric = '入院患者数' if '入院患者数' in selected_chart_metrics else '総入院患者数'

                                # デフォルト値として空のデータフレームを設定
                                current_data = pd.DataFrame()
                                comp_data = pd.DataFrame()

                                # データフレームが存在し、かつ必要な列が含まれることを確認
                                if (dow_data_for_chart is not None and not dow_data_for_chart.empty and 
                                    comp_dow_data is not None and not comp_dow_data.empty and 
                                    '指標タイプ' in dow_data_for_chart.columns and '指標タイプ' in comp_dow_data.columns):
        
                                    current_data = dow_data_for_chart[dow_data_for_chart['指標タイプ'] == target_metric]
                                    comp_data = comp_dow_data[comp_dow_data['指標タイプ'] == target_metric]
                                
                                if not current_data.empty and not comp_data.empty:
                                    # 曜日ごとの比較
                                    for dow in DOW_LABELS:
                                        current_dow = current_data[current_data['曜日'] == dow]['患者数'].mean()
                                        comp_dow = comp_data[comp_data['曜日'] == dow]['患者数'].mean()
                                        
                                        if pd.notna(current_dow) and pd.notna(comp_dow) and comp_dow > 0:
                                            change_pct = (current_dow - comp_dow) / comp_dow * 100
                                            
                                            # 入院患者数が20%以上増加した曜日の対応提案
                                            if change_pct >= 20:
                                                metric_specific_tips.append(
                                                    f"**{dow}の{target_metric}**が{change_pct:.1f}%増加しています。この曜日の入院受け入れ体制を強化し、"
                                                    f"病床管理や看護配置を最適化することで、質の高いケアを維持できる可能性があります。"
                                                )
                                            
                                            # 入院患者数が20%以上減少した曜日の対応提案
                                            elif change_pct <= -20:
                                                metric_specific_tips.append(
                                                    f"**{dow}の{target_metric}**が{abs(change_pct):.1f}%減少しています。この曜日の空床を有効活用するため、"
                                                    f"外来からの予定入院の調整や他の曜日からの入院シフトを検討できます。"
                                                )
                            
                            # 退院患者数のパターン変化に基づく提案
                            if '退院患者数' in selected_chart_metrics or '総退院患者数' in selected_chart_metrics:
                                target_metric = '退院患者数' if '退院患者数' in selected_chart_metrics else '総退院患者数'
                                
                                # デフォルト値として空のデータフレームを設定
                                current_data = pd.DataFrame()
                                comp_data = pd.DataFrame()

                                if (dow_data_for_chart is not None and not dow_data_for_chart.empty and 
                                    comp_dow_data is not None and not comp_dow_data.empty and 
                                    '指標タイプ' in dow_data_for_chart.columns and '指標タイプ' in comp_dow_data.columns):
        
                                    current_data = dow_data_for_chart[dow_data_for_chart['指標タイプ'] == target_metric]
                                    comp_data = comp_dow_data[comp_dow_data['指標タイプ'] == target_metric]
                                
                                if not current_data.empty and not comp_data.empty:
                                    # 週末（土日）の退院パターンの変化を分析
                                    current_weekend = current_data[current_data['曜日'].isin(['土曜日', '日曜日'])]['患者数'].mean()
                                    comp_weekend = comp_data[comp_data['曜日'].isin(['土曜日', '日曜日'])]['患者数'].mean()
                                    
                                    if pd.notna(current_weekend) and pd.notna(comp_weekend) and comp_weekend > 0:
                                        weekend_change_pct = (current_weekend - comp_weekend) / comp_weekend * 100
                                        
                                        if weekend_change_pct >= 30:
                                            metric_specific_tips.append(
                                                f"**週末の{target_metric}**が{weekend_change_pct:.1f}%増加しています。週末の退院支援が強化されたようです。"
                                                f"この良い変化を継続・発展させるため、週末の退院調整業務の成功要因を分析し、さらなる最適化を検討できます。"
                                            )
                                        elif weekend_change_pct <= -30:
                                            metric_specific_tips.append(
                                                f"**週末の{target_metric}**が{abs(weekend_change_pct):.1f}%減少しています。週末の退院支援体制に課題がある可能性があります。"
                                                f"薬剤部や医事課など関連部門との連携強化や、退院前カンファレンスの週末実施などの対策が有効かもしれません。"
                                            )
                            
                            # 緊急入院患者数のパターン変化に基づく提案
                            if '緊急入院患者数' in selected_chart_metrics:
                                # デフォルト値として空のデータフレームを設定
                                current_data = pd.DataFrame()
                                comp_data = pd.DataFrame()
                                change_pct = 0  # デフォルト値として0を設定

                                if (dow_data_for_chart is not None and not dow_data_for_chart.empty and 
                                    comp_dow_data is not None and not comp_dow_data.empty and 
                                    '指標タイプ' in dow_data_for_chart.columns and '指標タイプ' in comp_dow_data.columns):
        
                                    current_data = dow_data_for_chart[dow_data_for_chart['指標タイプ'] == '緊急入院患者数']
                                    comp_data = comp_dow_data[comp_dow_data['指標タイプ'] == '緊急入院患者数']

                                if not current_data.empty and not comp_data.empty:
                                    current_avg = current_data['患者数'].mean()
                                    comp_avg = comp_data['患者数'].mean()
                                    
                                    if pd.notna(current_avg) and pd.notna(comp_avg) and comp_avg > 0:
                                        change_pct = (current_avg - comp_avg) / comp_avg * 100
                                    
                                    if abs(change_pct) >= 20:
                                        direction = "増加" if change_pct > 0 else "減少"
                                        metric_specific_tips.append(
                                    f"**緊急入院患者数**が全体的に{abs(change_pct):.1f}%{direction}しています。"
                                    f"{'緊急対応体制の強化や救急部門との連携見直しが必要かもしれません。' if change_pct > 0 else '緊急入院の減少傾向を分析し、地域連携や診療体制に変化があったか確認するとよいでしょう。'}"
                                )
                
                # メトリクス別提案の表示
                if metric_specific_tips:
                    for tip in metric_specific_tips:
                        st.markdown(f"<p style='margin-bottom: 0.5em;'>- {tip}</p>", unsafe_allow_html=True)
        
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("比較グラフを生成するためのデータが不足しています。")