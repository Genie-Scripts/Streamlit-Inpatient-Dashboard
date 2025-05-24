import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px  # ← ★★★ この行を追加 ★★★
from datetime import datetime, timedelta
import calendar # create_dow_heatmap で使用されている場合は残す (前回提案では直接は使っていなかった)
import locale
import streamlit as st # streamlit の機能(st.warningなど)を使用しているためインポート

# 日本語の曜日名を使用するための設定
try:
    locale.setlocale(locale.LC_TIME, 'ja_JP.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'Japanese_Japan.932') # Windows fallback
    except locale.Error:
        st.sidebar.warning("日本語ロケールの設定に失敗しました。曜日が英語表記になる場合があります。") # Streamlitのサイドバーに警告
        pass # 最終フォールバック

DOW_LABELS = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日'] # app 2.py に合わせる
DOW_ORDER_INT = list(range(7)) # 0:月曜, ..., 6:日曜

def get_dow_data(df, unit_type, target_items, start_date, end_date, metric_type='average', patient_cols_to_analyze=None):
    """
    曜日別の入退院データを集計する関数
    
    Parameters:
    -----------
    df : pd.DataFrame
        分析対象のデータフレーム。
        必須列: '日付', '病棟コード', '診療科名', および patient_cols_to_analyze で指定された列
    unit_type : str
        集計単位 ('病院全体', '病棟別', '診療科別')
    target_items : list or None
        選択された病棟コードまたは診療科名のリスト
    start_date : datetime.date or pd.Timestamp
        集計開始日
    end_date : datetime.date or pd.Timestamp
        集計終了日
    metric_type : str, default='average'
        'average' (平均値/日) または 'sum' (合計値)
    patient_cols_to_analyze : list or None, default=['総入院患者数', '総退院患者数']
        曜日別集計の対象とする患者数指標の列名リスト。
        例: ['総入院患者数', '総退院患者数', '入院患者数', '緊急入院患者数', '退院患者数', '死亡患者数']

    Returns:
    --------
    pd.DataFrame or None
        曜日別の集計データ (カラム: '集計単位名', '曜日', '指標タイプ', '患者数')
        またはデータがない場合は None
    """
    if df is None or df.empty:
        st.warning("get_dow_data: 入力データフレームが空です。")
        return None

    if patient_cols_to_analyze is None:
        patient_cols_to_analyze = ['総入院患者数', '総退院患者数']
    
    # 指定された患者数列がdfに存在するか確認
    missing_patient_cols = [col for col in patient_cols_to_analyze if col not in df.columns]
    if missing_patient_cols:
        st.error(f"get_dow_data: 必要な患者数カラムが不足しています: {', '.join(missing_patient_cols)}")
        return None

    df_period_filtered = df[
        (df['日付'] >= pd.to_datetime(start_date)) &
        (df['日付'] <= pd.to_datetime(end_date))
    ].copy()

    if df_period_filtered.empty:
        st.info("get_dow_data: 選択された期間にデータがありません。")
        return None

    # 日付型に変換 (念のため)
    df_period_filtered['日付'] = pd.to_datetime(df_period_filtered['日付'])

    # 1. 日次単位での集計単位ごとの合計 (app 2.py の df_daily_unit_sum に相当)
    daily_unit_sum_list = []
    
    group_by_for_daily_sum = ['日付']
    unit_col_name = None

    if unit_type == '病院全体':
        # 日付ごとに各指標を合計
        daily_sum_temp = df_period_filtered.groupby('日付', as_index=False)[patient_cols_to_analyze].sum()
        daily_sum_temp['集計単位名'] = '病院全体'
        daily_unit_sum_list.append(daily_sum_temp)
    elif unit_type == '病棟別':
        unit_col_name = '病棟コード'
        group_by_for_daily_sum.append(unit_col_name)
        items_to_process = target_items if target_items else df_period_filtered[unit_col_name].unique()
        for item in items_to_process:
            item_df = df_period_filtered[df_period_filtered[unit_col_name].astype(str) == str(item)]
            if not item_df.empty:
                daily_sum_temp = item_df.groupby('日付', as_index=False)[patient_cols_to_analyze].sum()
                daily_sum_temp['集計単位名'] = str(item)
                daily_unit_sum_list.append(daily_sum_temp)
    elif unit_type == '診療科別':
        unit_col_name = '診療科名'
        group_by_for_daily_sum.append(unit_col_name)
        items_to_process = target_items if target_items else df_period_filtered[unit_col_name].unique()
        for item in items_to_process:
            item_df = df_period_filtered[df_period_filtered[unit_col_name].astype(str) == str(item)]
            if not item_df.empty:
                daily_sum_temp = item_df.groupby('日付', as_index=False)[patient_cols_to_analyze].sum()
                daily_sum_temp['集計単位名'] = str(item)
                daily_unit_sum_list.append(daily_sum_temp)
    else:
        st.error(f"get_dow_data: 未知の集計単位タイプです: {unit_type}")
        return None

    if not daily_unit_sum_list:
        st.info("get_dow_data: 日次集計データが作成できませんでした。")
        return None
        
    df_to_process_dow = pd.concat(daily_unit_sum_list, ignore_index=True)

    # 2. 曜日情報の付与 (app 2.py と同様)
    df_to_process_dow['曜日番号'] = df_to_process_dow['日付'].dt.weekday # Monday=0, Sunday=6
    df_to_process_dow['曜日'] = df_to_process_dow['曜日番号'].apply(lambda x: DOW_LABELS[x])
    df_to_process_dow['曜日'] = pd.Categorical(df_to_process_dow['曜日'], categories=DOW_LABELS, ordered=True)

    # 3. 最終的な曜日別集計 (app 2.py と同様)
    aggregation_func = 'mean' if metric_type == 'average' else 'sum'
    
    # 集計対象の列でグループ化して集計
    agg_dict_for_final_dow = {col: aggregation_func for col in patient_cols_to_analyze}
    
    final_dow_df_intermediate = df_to_process_dow.groupby(
        ['集計単位名', '曜日'], # '曜日番号' も含めてソート後、'曜日名' を使う
        observed=False # categories を尊重
    ).agg(agg_dict_for_final_dow).reset_index()

    if final_dow_df_intermediate.empty:
        st.info("get_dow_data: 最終的な曜日別集計結果が空です。")
        return None

    # データをグラフ表示しやすいようにmelt (縦持ち変換)
    final_dow_df_melted = final_dow_df_intermediate.melt(
        id_vars=['集計単位名', '曜日'],
        value_vars=patient_cols_to_analyze, # patient_cols_to_analyze にある列のみをmelt
        var_name='指標タイプ',
        value_name='患者数'
    )
    final_dow_df_melted.sort_values(by=['集計単位名', '曜日'], inplace=True) # 曜日カテゴリでソートされるはず

    return final_dow_df_melted


def create_dow_chart(dow_data_melted: pd.DataFrame, unit_type: str, target_items: list, 
                     metric_type: str = 'average', patient_cols_to_analyze: list = None,
                     title_prefix: str = None):
    """
    曜日別のグラフを作成する関数
    
    Parameters:
    -----------
    dow_data_melted : pd.DataFrame
        get_dow_data関数で生成された曜日別データ (melted形式)
    unit_type : str
        集計単位 ('病院全体', '病棟別', '診療科別')
    target_items : list
        選択された病棟コードまたは診療科名のリスト
    metric_type : str, default='average'
        'average' (平均値/日) または 'sum' (合計値)
    patient_cols_to_analyze : list or None, default=None
        曜日別集計の対象とする患者数指標の列名リスト
    title_prefix : str or None, default=None
        グラフタイトルの前に付加するテキスト (例: '現在期間', '比較期間')
        
    Returns:
    --------
    plotly.graph_objs._figure.Figure or None
        作成されたグラフ、またはエラー時はNone
    """
    if dow_data_melted is None or dow_data_melted.empty:
        return None
    
    if patient_cols_to_analyze is None: # フォールバック
        patient_cols_to_analyze = ['総入院患者数', '総退院患者数']

    unit_suffix = "平均患者数/日" if metric_type == 'average' else "合計患者数"
    y_axis_title = f"患者数 ({unit_suffix})"
    
    num_unique_units = len(dow_data_melted['集計単位名'].unique())
    
    category_orders_legend = {"指標タイプ": patient_cols_to_analyze}

    fig_dow = px.bar(
        dow_data_melted,
        x='曜日', 
        y='患者数', 
        color='指標タイプ', 
        barmode='group',
        facet_col='集計単位名' if num_unique_units > 1 and unit_type != '病院全体' else None,
        facet_col_wrap=min(num_unique_units, 2 if num_unique_units > 1 else 1),
        labels={'曜日': '曜日', '患者数': y_axis_title, '集計単位名': '集計単位', '指標タイプ': '指標'},
        category_orders={"曜日": DOW_LABELS, **category_orders_legend} 
    )
    
    # タイトル設定
    if num_unique_units == 1 or unit_type == '病院全体':
        unit_name_title = dow_data_melted['集計単位名'].iloc[0]
        title_text = f"{unit_name_title} - 曜日別 患者数 ({unit_suffix})"
        # 期間識別子がある場合はタイトルに追加
        if title_prefix:
            title_text = f"{title_prefix}: {title_text}"
        fig_dow.update_layout(title_text=title_text, title_x=0.5)
    else:
        # 複数ユニットの場合もタイトルプレフィックスを適用（必要に応じて）
        if title_prefix:
            fig_dow.update_layout(title_text=f"{title_prefix}", title_x=0.5)
        fig_dow.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))

    # グラフサイズの調整
    num_facet_rows = 1
    if num_unique_units > 1 and unit_type != '病院全体':
        num_facet_rows = (num_unique_units + (2 -1)) // 2 

    plot_height = 450 + (150 * (num_facet_rows -1)) if num_unique_units > 1 else 450
    plot_height = min(plot_height, 2000)

    # レイアウト設定
    fig_dow.update_layout(
        font=dict(size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
        height=plot_height, 
        bargap=0.2, 
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=60 if num_unique_units > 1 and unit_type != '病院全体' else 80, b=20),
    )
    fig_dow.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray', categoryorder='array', categoryarray=DOW_LABELS)
    fig_dow.update_yaxes(title_text=y_axis_title, showgrid=True, gridwidth=1, gridcolor='LightGray')

    return fig_dow


def calculate_dow_summary(df: pd.DataFrame, start_date: datetime, end_date: datetime, 
                          group_by_column: str = None, target_items: list = None):
    """
    曜日別の入退院サマリーメトリクスを計算する (app 2.py のロジックを参考)

    Parameters:
    -----------
    df : pd.DataFrame
        分析対象のデータフレーム。
        必須列: '日付', '病棟コード', '診療科名', '入院患者数', '緊急入院患者数', 
                '総入院患者数', '退院患者数', '死亡患者数', '総退院患者数'
    start_date : datetime.date or pd.Timestamp
        分析開始日
    end_date : datetime.date or pd.Timestamp
        分析終了日
    group_by_column : str or None, default None
        集計単位の列名 ('病棟コード', '診療科名')。None の場合は病院全体。
    target_items : list or None, default None
        group_by_column が指定された場合に、集計対象とする項目のリスト。

    Returns:
    --------
    pd.DataFrame or None
        曜日別の詳細メトリクスを含むDataFrame、またはデータがない場合はNone
    """
    if df is None or df.empty:
        st.warning("calculate_dow_summary: 入力データフレームが空です。")
        return None

    df_period_filtered = df[
        (df['日付'] >= pd.to_datetime(start_date)) &
        (df['日付'] <= pd.to_datetime(end_date))
    ].copy()

    if df_period_filtered.empty:
        st.info("calculate_dow_summary: 選択された期間にデータがありません。")
        return None
    
    df_period_filtered['日付'] = pd.to_datetime(df_period_filtered['日付'])

    # 集計対象とする患者数指標の列
    # 注意:「在院患者数」はスナップショットのため、日次で単純合計するのは通常不適切。
    #       曜日別の平均在院者数などを出したい場合は、元データの持ち方や集計方法の再検討が必要。
    #       ここではイベントベースの患者数を主に扱います。
    sum_cols_daily = ['入院患者数', '緊急入院患者数', '総入院患者数', 
                      '退院患者数', '死亡患者数', '総退院患者数', '在院患者数']  # '在院患者数'を追加]
    
    # dfに存在する列のみを対象とする
    actual_sum_cols_daily = [col for col in sum_cols_daily if col in df_period_filtered.columns]
    if not actual_sum_cols_daily:
        st.error("calculate_dow_summary: 集計対象の患者数カラムが見つかりません。")
        return None

    # 1. 日次レベルでの集計 (選択された集計単位ごと)
    daily_aggregated_list = []
    
    if group_by_column is None: # 病院全体
        daily_temp_df = df_period_filtered.groupby('日付', as_index=False)[actual_sum_cols_daily].sum()
        daily_temp_df['集計単位'] = '病院全体'
        daily_aggregated_list.append(daily_temp_df)
    elif group_by_column in ['病棟コード', '診療科名']:
        items_to_process_daily = target_items if target_items else df_period_filtered[group_by_column].unique()
        for item in items_to_process_daily:
            item_daily_df = df_period_filtered[df_period_filtered[group_by_column].astype(str) == str(item)]
            if not item_daily_df.empty:
                summed_item_daily_df = item_daily_df.groupby('日付', as_index=False)[actual_sum_cols_daily].sum()
                summed_item_daily_df['集計単位'] = str(item)
                daily_aggregated_list.append(summed_item_daily_df)
    else:
        st.error(f"calculate_dow_summary: 未知のgroup_by_columnです: {group_by_column}")
        return None

    if not daily_aggregated_list:
        st.info("calculate_dow_summary: 日次集計データが作成できませんでした。")
        return None
        
    daily_aggregated_df = pd.concat(daily_aggregated_list, ignore_index=True)

    # 2. 曜日情報の付与
    daily_aggregated_df['曜日番号'] = daily_aggregated_df['日付'].dt.weekday # Monday=0, Sunday=6
    daily_aggregated_df['曜日名'] = daily_aggregated_df['曜日番号'].apply(lambda x: DOW_LABELS[x])
    
    # 3. 曜日別の最終集計
    # 各曜日が何回出現したか（集計日数）も計算
    # 指標ごとの合計値と、各曜日が期間内に何日あったかを計算
    
    final_group_by_cols = ['集計単位', '曜日番号', '曜日名']
    
    # 各指標の合計値を計算
    agg_funcs_for_sum = {col: 'sum' for col in actual_sum_cols_daily}
    # 各曜日が何日あったかをカウント
    agg_funcs_for_sum['日付'] = 'count' # その曜日の日数をカウントするため

    summary_sum_df = daily_aggregated_df.groupby(final_group_by_cols, as_index=False, observed=False).agg(agg_funcs_for_sum)
    summary_sum_df.rename(columns={'日付': '集計日数'}, inplace=True)

    # 各指標の平均値/日を計算 (合計値 / 集計日数)
    summary_avg_df = summary_sum_df.copy()
    for col in actual_sum_cols_daily:
        avg_col_name = f"平均{col}"
        sum_col_name = col # summary_sum_dfでは合計値が元の列名で入っている
        summary_avg_df[avg_col_name] = summary_avg_df.apply(
            lambda row: row[sum_col_name] / row['集計日数'] if row['集計日数'] > 0 else 0, axis=1
        )

    # 率の計算 (緊急入院率、死亡退院率など) - 合計ベースで計算
    if '総入院患者数' in summary_avg_df.columns and '緊急入院患者数' in summary_avg_df.columns:
        summary_avg_df['緊急入院率'] = summary_avg_df.apply(
            lambda row: (row['緊急入院患者数'] / row['総入院患者数'] * 100) if row['総入院患者数'] > 0 else 0, axis=1
        )
    else:
        summary_avg_df['緊急入院率'] = np.nan

    if '総退院患者数' in summary_avg_df.columns and '死亡患者数' in summary_avg_df.columns:
        summary_avg_df['死亡退院率'] = summary_avg_df.apply(
            lambda row: (row['死亡患者数'] / row['総退院患者数'] * 100) if row['総退院患者数'] > 0 else 0, axis=1
        )
    else:
        summary_avg_df['死亡退院率'] = np.nan

    # 列名を調整 (app 2.py の run_dow_trend_analysis 関数の最終的なmelt前のカラム名に近い形にする)
    # ここでは、合計値と平均値の両方を持つDataFrameを返すようにする
    # 表示側 (dow_analysis_tab.py) で、ユーザーが選択した metric_type ('average' or 'sum') に応じて
    # 表示する列を選択する形が良いでしょう。
    
    # 合計値のカラム名を変更 (例: "総入院患者数" -> "総入院患者数合計")
    rename_map_sum = {col: f"{col}合計" for col in actual_sum_cols_daily}
    summary_avg_df.rename(columns=rename_map_sum, inplace=True)
    
    # 曜日の順序でソート
    summary_avg_df['曜日名'] = pd.Categorical(summary_avg_df['曜日名'], categories=DOW_LABELS, ordered=True)
    final_summary_df = summary_avg_df.sort_values(['集計単位', '曜日番号'])

    # 不要な曜日番号列を削除しても良い
    # final_summary_df = final_summary_df.drop(columns=['曜日番号'])
    
    return final_summary_df


def create_dow_heatmap(dow_data: pd.DataFrame, metric: str = '入院患者数', unit_type: str = '病院全体'):
    """
    曜日別のヒートマップまたはバーチャートを作成する関数。
    dow_data は calculate_dow_summary から返される、合計値と平均値の両方を含むDataFrameを想定。

    Parameters:
    -----------
    dow_data : pd.DataFrame
        曜日別の集計データ。期待される列: '集計単位', '曜日名', 
                                       '平均{指標名}', '{指標名}合計' など。
    metric : str, default='入院患者数'
        ヒートマップで表示する基本的な指標名（例: '総入院患者数', '総退院患者数'）。
        この関数内で '平均'プレフィックスや '合計'サフィックスを付加して列を特定します。
    unit_type : str, default='病院全体'
        集計単位 ('病院全体', '病棟別', '診療科別')。
        これは主にタイトルや軸ラベル、およびピボットの要否を決定するために使用します。

    Returns:
    --------
    plotly.graph_objs._figure.Figure or None
        生成されたPlotlyのFigureオブジェクト、またはエラー時はNone。
    """
    if dow_data is None or dow_data.empty:
        # 呼び出し元 (dow_analysis_tab.py) で st.info や st.warning を出すことを推奨
        print("create_dow_heatmap: 入力データ (dow_data) が空です。")
        return None

    # 表示する値の列名を決定 (平均値か合計値か)
    # dow_analysis_tab.py で metric_type ('average' or 'sum') が選択されるので、
    # それに応じて適切な列名を選択する。
    # ここでは、dow_data に '平均{metric}' と '{metric}合計' の両方が存在すると仮定。
    # どちらを表示するかは、呼び出し元の選択（またはこの関数の引数）で決めるべきだが、
    # ここではまず平均を優先し、なければ合計を探すロジックにする。
    # より良いのは、表示すべき列名を直接引数で受け取るか、metric_type ('average'/'sum') を引数で受け取ること。
    
    # --- dow_analysis_tab.py からの metric_type の選択を反映させるため、
    # --- この関数の引数にも metric_type を追加するか、
    # --- あるいは呼び出し元で value_col を決定して渡すのが望ましい。
    # --- ここでは仮に、渡された metric 名から平均値の列を探し、なければ合計値の列を探す。
    
    value_col_avg = f'平均{metric}'
    value_col_sum = f'{metric}合計'
    value_col_to_use = None
    actual_metric_type_for_suffix = "" # グラフタイトル用

    if value_col_avg in dow_data.columns:
        value_col_to_use = value_col_avg
        actual_metric_type_for_suffix = "平均/日"
    elif value_col_sum in dow_data.columns:
        value_col_to_use = value_col_sum
        actual_metric_type_for_suffix = "合計"
    else:
        # st.warning(f"ヒートマップ用の指標 '{metric}' (平均または合計) がデータに見つかりません。")
        print(f"create_dow_heatmap: 指標 '{metric}' (平均または合計) がdow_dataに見つかりません。利用可能な列: {dow_data.columns.tolist()}")
        return None

    fig = None
    title_metric_part = f"{metric} ({actual_metric_type_for_suffix})"

    try:
        if unit_type == '病院全体':
            # 病院全体の場合は、曜日ごとのバーチャートでパターンを示す
            fig = px.bar(
                dow_data[dow_data['集計単位'] == '病院全体'], # 念のためフィルタ
                x='曜日名',
                y=value_col_to_use,
                title=f"曜日別 {title_metric_part} パターン (病院全体)",
                color=value_col_to_use, # バーの色を値の大小で変える
                color_continuous_scale='Viridis', # カラースケール
                labels={
                    '曜日名': '曜日',
                    value_col_to_use: title_metric_part # Y軸ラベル
                },
                category_orders={'曜日名': DOW_LABELS} # X軸の曜日順
            )
        else: # 病棟別または診療科別
            if '集計単位' not in dow_data.columns:
                print(f"create_dow_heatmap: '集計単位' 列がデータにありません (unit_type: {unit_type})。")
                return None
            
            # ピボットテーブルを作成 (曜日を行、集計単位を列、値を患者数)
            try:
                # '曜日名' をカテゴリカル型にして順序を保証
                dow_data_copy = dow_data.copy() # 元のDFを変更しないようにコピー
                dow_data_copy['曜日名'] = pd.Categorical(dow_data_copy['曜日名'], categories=DOW_LABELS, ordered=True)
                
                pivot_data = dow_data_copy.pivot_table(
                    index='曜日名',
                    columns='集計単位',
                    values=value_col_to_use,
                    aggfunc='first' # 既に集計済みなので 'first' または 'mean'
                )
                # pivot_table の結果、インデックスの順序が保たれない場合があるので、DOW_LABELSで再インデックス
                pivot_data = pivot_data.reindex(DOW_LABELS)

            except KeyError as e: # ピボットに必要な列がない場合
                print(f"create_dow_heatmap: ピボット操作に必要な列がありません ({e})。")
                return None
            except Exception as e: # その他のピボットエラー
                print(f"create_dow_heatmap: ピボット操作中にエラー: {e}")
                # st.error(f"ヒートマップデータの準備中にエラーが発生しました: {e}")
                return None

            if pivot_data.empty:
                print("create_dow_heatmap: ピボット後のデータが空です。")
                return None

            # ヒートマップの作成
            fig = px.imshow(
                pivot_data,
                x=pivot_data.columns, # 集計単位 (病棟/診療科)
                y=pivot_data.index,   # 曜日名 (DOW_LABELS の順序を期待)
                color_continuous_scale='Viridis', # カラースケール
                aspect="auto", # アスペクト比を自動調整
                title=f"曜日別 {title_metric_part} ヒートマップ ({unit_type})",
                labels={
                    'x': unit_type.replace('別', ''), # X軸ラベル (例: 病棟, 診療科)
                    'y': '曜日',                     # Y軸ラベル
                    'color': title_metric_part       # カラーバーのラベル
                }
            )
            # Y軸のカテゴリ順を明示的に指定 (imshowの場合、これで順序が保たれるはず)
            fig.update_yaxes(categoryorder='array', categoryarray=DOW_LABELS)

    except Exception as e:
        # st.error(f"ヒートマップ作成中に予期せぬエラーが発生しました: {e}")
        print(f"create_dow_heatmap: グラフ作成中に予期せぬエラー: {e}")
        import traceback
        print(traceback.format_exc())
        return None

    if fig is None:
        return None

    # 共通のグラフ外観調整
    fig.update_layout(
        height=500,
        margin=dict(l=50, r=50, t=80, b=50), # 上マージンを少し広げてタイトルスペース確保
        plot_bgcolor='rgba(0,0,0,0)', # プロットエリア背景を透明に
        paper_bgcolor='white',
        font=dict(family="Arial, sans-serif", size=12) # フォント指定
    )
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
    
    return fig