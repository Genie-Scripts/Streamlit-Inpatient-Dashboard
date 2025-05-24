import pandas as pd
import streamlit as st
from io import BytesIO
import os
import re
import time
import hashlib
import gc
import numpy as np  # NumPyのインポートを追加

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# chart.py から Matplotlib ベースの関数をインポート
from chart import create_patient_chart as create_base_patient_chart_from_chart_py # 目標値なし版
from chart import create_dual_axis_chart as create_dual_axis_chart_from_chart_py

import matplotlib.font_manager
import matplotlib.pyplot as plt

# --- フォント設定 ---
FONT_DIR = 'fonts'
FONT_FILENAME = 'NotoSansJP-Regular.ttf'
FONT_PATH = os.path.join(FONT_DIR, FONT_FILENAME)
REPORTLAB_FONT_NAME = 'NotoSansJP_RL' # ReportLab用
MATPLOTLIB_FONT_NAME_FALLBACK = 'sans-serif' # Matplotlib用フォールバック
MATPLOTLIB_FONT_NAME = None # register_fonts で設定される

def register_fonts():
    global MATPLOTLIB_FONT_NAME
    font_registered_rl = False
    font_registered_mpl = False

    if os.path.exists(FONT_PATH):
        try:
            pdfmetrics.registerFont(TTFont(REPORTLAB_FONT_NAME, FONT_PATH))
            print(f"ReportLab font '{REPORTLAB_FONT_NAME}' ({FONT_PATH}) registered.")
            font_registered_rl = True
        except Exception as e:
            print(f"Failed to register ReportLab font '{FONT_PATH}': {e}")

        try:
            # Matplotlibにフォントを追加し、デフォルトファミリーに設定
            font_entry = matplotlib.font_manager.FontEntry(
                fname=FONT_PATH, name='NotoSansJP_MPL' # Matplotlib内での名前
            )
            matplotlib.font_manager.fontManager.ttflist.insert(0, font_entry) # リストの先頭に追加して優先度を上げる
            plt.rcParams['font.family'] = font_entry.name
            MATPLOTLIB_FONT_NAME = font_entry.name
            print(f"Matplotlib default font set to '{MATPLOTLIB_FONT_NAME}' using {FONT_PATH}.")
            font_registered_mpl = True
        except Exception as e:
            print(f"Failed to set Matplotlib font '{FONT_PATH}': {e}")
            plt.rcParams['font.family'] = MATPLOTLIB_FONT_NAME_FALLBACK
            MATPLOTLIB_FONT_NAME = None
    else:
        print(f"Font file not found at '{FONT_PATH}'. Using fallback fonts.")
        plt.rcParams['font.family'] = MATPLOTLIB_FONT_NAME_FALLBACK

    if not font_registered_rl:
        # global REPORTLAB_FONT_NAME # グローバル変数を変更する場合
        # REPORTLAB_FONT_NAME = 'Helvetica' # ReportLabのデフォルトは Helvetica
        print(f"ReportLab will use its default font or Helvetica if '{REPORTLAB_FONT_NAME}' was intended as NotoSansJP.")


register_fonts()

# --- キャッシュ設定 ---
def get_chart_cache():
    if 'pdf_chart_cache' not in st.session_state: # キー名を他と区別
        st.session_state.pdf_chart_cache = {}
    return st.session_state.pdf_chart_cache

def compute_data_hash(data):
    if data is None or data.empty:
        return "empty_data_hash"
    try:
        # データの主要な部分からハッシュを生成 (例: '日付' と '入院患者数（在院）' 列の最初の10行と最後の10行)
        if '日付' in data.columns and '入院患者数（在院）' in data.columns:
            sampled_data = pd.concat([data.head(10), data.tail(10)]).to_string()
        else:
            sampled_data = data.head(10).to_string() # Fallback
        return hashlib.md5(sampled_data.encode()).hexdigest()
    except: # どんなエラーでもキャッチ
        return hashlib.md5(str(data.shape).encode()).hexdigest() # 最終手段

def get_chart_cache_key(title, days, target_value=None, chart_type="default", data_hash=None):
    components = [str(title), str(days)]
    if target_value is not None:
        try:
            components.append(str(round(float(target_value), 2)))
        except (ValueError, TypeError):
            components.append(str(target_value)) # 数値でない場合はそのまま
    else:
        components.append("None")
    components.append(str(chart_type))
    if data_hash:
        components.append(data_hash)
    # print(f"Generated cache key: {'_'.join(components)}") # デバッグ用
    return "_".join(components)

# --- グラフ生成関数 (chart.pyのものをラップして目標値などを追加) ---
def create_alos_chart_for_pdf(
    chart_data, title_prefix="全体", latest_date=None, 
    moving_avg_window=30, font_name_for_mpl=None,
    days_to_show=90  # この引数を追加
):
    """
    PDF用の平均在院日数グラフを作成する関数
    """
    start_time = time.time()
    
    fig = None
    try:
        fig, ax1 = plt.subplots(figsize=(10, 5.5))
        
        if not isinstance(chart_data, pd.DataFrame) or chart_data.empty:
            if fig: plt.close(fig)
            return None
            
        # 必要な列が存在するか確認
        required_columns = ["日付", "入院患者数（在院）", "総入院患者数", "総退院患者数"]
        if any(col not in chart_data.columns for col in required_columns):
            if fig: plt.close(fig)
            return None
        
        # 日付型の確認と変換
        if not pd.api.types.is_datetime64_any_dtype(chart_data['日付']):
            chart_data['日付'] = pd.to_datetime(chart_data['日付'])
        
        # 直近データのみに絞る（引数で指定された日数分）
        if latest_date is None:
            latest_date = chart_data['日付'].max()
        
        # days_to_showを使用
        start_date = latest_date - pd.Timedelta(days=days_to_show)
        chart_data_filtered = chart_data[(chart_data['日付'] >= start_date) & (chart_data['日付'] <= latest_date)].copy()
        
        if chart_data_filtered.empty:
            if fig: plt.close(fig)
            return None
        
        # 平均在院日数の計算（日単位での推移）
        daily_metrics = []
        date_range = pd.date_range(start=start_date, end=latest_date)
        
        for current_date in date_range:
            # current_dateを含む直近30日分のデータを抽出
            window_start = current_date - pd.Timedelta(days=moving_avg_window-1)
            window_data = chart_data[(chart_data['日付'] >= window_start) & (chart_data['日付'] <= current_date)]
            
            if not window_data.empty:
                # 集計値
                total_patient_days = window_data['入院患者数（在院）'].sum()
                total_admissions = window_data['総入院患者数'].sum()
                total_discharges = window_data['総退院患者数'].sum()
                num_days = window_data['日付'].nunique()
                
                # 平均在院日数と平均在院患者数
                denominator = (total_admissions + total_discharges) / 2
                alos = total_patient_days / denominator if denominator > 0 else 0
                daily_census = total_patient_days / num_days if num_days > 0 else 0
                
                daily_metrics.append({
                    '日付': current_date,
                    '平均在院日数': alos,
                    '平均在院患者数': daily_census
                })
        
        if not daily_metrics:
            if fig: plt.close(fig)
            return None
        
        daily_df = pd.DataFrame(daily_metrics)
        daily_df = daily_df.sort_values('日付')
        
        # グラフ描画
        font_kwargs = {}
        if font_name_for_mpl:
            font_kwargs['fontname'] = font_name_for_mpl
        
        # 平均在院日数（左軸）
        ax1.plot(daily_df['日付'], daily_df['平均在院日数'], color='#3498db', linewidth=2, marker='o', 
                 markersize=4, label=f"平均在院日数（直近{moving_avg_window}日）")
        ax1.set_xlabel('日付', fontsize=12, **font_kwargs)
        ax1.set_ylabel('平均在院日数', fontsize=12, color='#3498db', **font_kwargs)
        ax1.tick_params(axis='y', labelcolor='#3498db', labelsize=10)
        ax1.tick_params(axis='x', labelsize=10)
        
        # 平均在院患者数（右軸）
        ax2 = ax1.twinx()
        ax2.plot(daily_df['日付'], daily_df['平均在院患者数'], color='#e74c3c', linewidth=2, 
                 linestyle='--', label='平均在院患者数')
        ax2.set_ylabel('平均在院患者数', fontsize=12, **font_kwargs)
        ax2.tick_params(axis='y', labelsize=10)
        
        # 凡例
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_prop = {'size': 10}
        if font_name_for_mpl: legend_prop['family'] = font_name_for_mpl
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_prop)
        
        plt.title(f"{title_prefix} 平均在院日数と平均在院患者数の推移", fontsize=14, **font_kwargs)
        fig.autofmt_xdate(rotation=30, ha='right')
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        
        plt.tight_layout(pad=0.5)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        plt.close(fig)
        buf.seek(0)
        
        end_time = time.time()
        print(f"ALOS Chart generated for {title_prefix} in {end_time - start_time:.2f}s")
        return buf
    
    except Exception as e:
        print(f"Error creating ALOS chart for {title_prefix}: {e}")
        import traceback
        print(traceback.format_exc())
        if fig: plt.close(fig)
        return None

def create_patient_chart_with_target_wrapper(
    data, title="入院患者数推移", days=90, show_moving_average=True, target_value=None
    ):
    """
    chart.pyのcreate_base_patient_chart_from_chart_pyをラップし、目標値描画機能を追加。
    これはpdf_generator_org.pyのcreate_patient_chart_with_targetに相当する機能を目指す。
    """
    fig = None
    try:
        # chart.pyの関数はfont_name_for_mplを引数に取るので、グローバルなMATPLOTLIB_FONT_NAMEを使用
        # create_base_patient_chart_from_chart_py は BytesIO を返す前提
        # しかし、目標値などを追加で描画するには、一度Figureオブジェクトを取得するか、
        # BytesIOから画像を読み込んで再描画する必要があり、効率が悪い。
        # ここでは、元の create_patient_chart_with_target のロジックを再実装する。

        fig, ax = plt.subplots(figsize=(8, 4.0)) # PDFのスペースに合わせてサイズ調整

        if not isinstance(data, pd.DataFrame) or data.empty:
            if fig: plt.close(fig); fig = None
            return None
        if "日付" not in data.columns or "入院患者数（在院）" not in data.columns:
            if fig: plt.close(fig); fig = None
            return None

        if not pd.api.types.is_datetime64_any_dtype(data['日付']):
            data['日付'] = pd.to_datetime(data['日付'])

        grouped = data.groupby("日付")["入院患者数（在院）"].sum().reset_index().sort_values("日付")
        if len(grouped) > days:
            grouped = grouped.tail(days)
        if grouped.empty:
            if fig: plt.close(fig); fig = None
            return None

        ax.plot(grouped["日付"], grouped["入院患者数（在院）"], marker='o', linestyle='-', linewidth=1.5, markersize=3, color='#3498db', label='入院患者数')
        avg = grouped["入院患者数（在院）"].mean()
        ax.axhline(y=avg, color='#e74c3c', linestyle='--', alpha=0.7, linewidth=1, label=f'平均: {avg:.1f}')

        if show_moving_average and len(grouped) >= 7:
            grouped['7日移動平均'] = grouped["入院患者数（在院）"].rolling(window=7, min_periods=1).mean()
            ax.plot(grouped["日付"], grouped['7日移動平均'], linestyle='-', linewidth=1.2, color='#2ecc71', label='7日移動平均')

        if target_value is not None and pd.notna(target_value):
            try:
                target_val_float = float(target_value)
                ax.axhline(y=target_val_float, color='#9b59b6', linestyle='-.', linewidth=1.2, label=f'目標値: {target_val_float:.1f}')
                
                # 注意ゾーンを追加 (目標値に対して97%以下の領域)
                caution_threshold = target_val_float * 0.97
                ax.fill_between(
                    grouped["日付"], 
                    caution_threshold, 
                    target_val_float, 
                    color='orange', 
                    alpha=0.15, 
                    label='注意ゾーン'
                )
            except ValueError:
                print(f"Warning: Target value '{target_value}' could not be converted to float.")


        # MATPLOTLIB_FONT_NAME が設定されていれば、それが自動的に使われるはず (plt.rcParams設定済みのため)
        ax.set_title(title, fontsize=11) # サイズ調整
        ax.set_xlabel('日付', fontsize=9)  # フォントサイズを大きく
        ax.set_ylabel('患者数', fontsize=9)  # フォントサイズを大きく

        ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        # ここで凡例のフォントサイズを大きくする
        legend_prop = {'size': 9}  # 7から9に変更
        if MATPLOTLIB_FONT_NAME:
            legend_prop['family'] = MATPLOTLIB_FONT_NAME
        ax.legend(prop=legend_prop)
        
        fig.autofmt_xdate(rotation=30, ha='right')
        ax.tick_params(axis='x', labelsize=8)  # 軸ラベルも大きく
        ax.tick_params(axis='y', labelsize=8)  # 軸ラベルも大きく

        plt.tight_layout(pad=0.5)
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120) # 解像度を少し下げることも検討
        plt.close(fig) # メモリリークを防ぐ
        fig = None
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error in create_patient_chart_with_target_wrapper ('{title}'): {e}")
        if fig: plt.close(fig)
        return None

# 同様に create_dual_axis_chart 関数も修正
@st.cache_data(ttl=1800)
def create_dual_axis_chart(data, title="入院患者数と患者移動の推移", filename=None, days=90, font_name_for_mpl=None): # font_name_for_mpl 引数を追加
    """
    入院患者数と患者移動の7日移動平均グラフを二軸で作成する（Matplotlib版、PDF用）
    """
    fig = None
    try:
        fig, ax1 = plt.subplots(figsize=(10, 5.5)) # サイズ調整

        if not isinstance(data, pd.DataFrame) or data.empty:
            # st.warning(f"2軸グラフ生成スキップ (データ不正): '{title}'") # PDF生成時はst要素不適切
            if fig: plt.close(fig)
            return None

        required_columns = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "退院患者数"]
        if any(col not in data.columns for col in required_columns):
            # st.warning(f"2軸グラフ生成スキップ (列不足): '{title}'")
            if fig: plt.close(fig)
            return None

        grouped = data.groupby("日付").agg({"入院患者数（在院）": "sum", "新入院患者数": "sum", "緊急入院患者数": "sum", "退院患者数": "sum"}).reset_index().sort_values("日付")
        if len(grouped) > days: grouped = grouped.tail(days)
        if grouped.empty:
            # st.warning(f"2軸グラフ生成スキップ (フィルタ後データ空): '{title}'")
            if fig: plt.close(fig)
            return None

        for col in required_columns[1:]: grouped[f'{col}_7日移動平均'] = grouped[col].rolling(window=7, min_periods=1).mean()

        font_kwargs = {}
        if font_name_for_mpl:
            font_kwargs['fontname'] = font_name_for_mpl

        ax1.plot(grouped["日付"], grouped["入院患者数（在院）_7日移動平均"], color='#3498db', linewidth=2, label="入院患者数（在院）") # linewidth調整
        ax1.set_xlabel('日付', fontsize=9, **font_kwargs)  # フォントサイズを大きく
        ax1.set_ylabel('入院患者数（在院）', fontsize=9, color='#3498db', **font_kwargs)  # フォントサイズを大きく
        ax1.tick_params(axis='y', labelcolor='#3498db', labelsize=8)  # 軸ラベルも大きく
        ax1.tick_params(axis='x', labelsize=8) # X軸も大きく

        ax2 = ax1.twinx()
        colors_map = {"新入院患者数": "#2ecc71", "緊急入院患者数": "#e74c3c", "退院患者数": "#f39c12"}
        for col, color_val in colors_map.items():
            ax2.plot(grouped["日付"], grouped[f"{col}_7日移動平均"], color=color_val, linewidth=1.5, label=col) # linewidth調整

        ax2.set_ylabel('患者移動数', fontsize=9, **font_kwargs)  # フォントサイズを大きく
        ax2.tick_params(axis='y', labelsize=8)  # 軸ラベルも大きく

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_prop = {'size': 9}  # 7から9に変更
        if font_name_for_mpl: legend_prop['family'] = font_name_for_mpl
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_prop)

        plt.title(title, fontsize=12, **font_kwargs)
        fig.autofmt_xdate(rotation=30, ha='right')
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7) # グリッドはax1に

        plt.tight_layout(pad=0.5)

        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150) # DPI調整
        plt.close(fig)
        buf.seek(0)
        return buf

    except Exception as e:
        # st.error(f"2軸グラフ '{title}' 作成中にエラー: {e}") # PDF生成時はst要素不適切
        print(f"Error in create_dual_axis_chart ('{title}'): {e}") # サーバーログに出力
        if fig: plt.close(fig)
        return None
        
# --- PDF生成メイン関数 (基本的に前回の修正案を維持しつつ、グラフ呼び出しを調整) ---
@st.cache_data(ttl=600, show_spinner=False, max_entries=50)
def create_pdf(
    forecast_df, df_weekday, df_holiday, df_all_avg=None,
    chart_data=None, title_prefix="全体", latest_date=None,
    target_data=None, filter_code="全体", graph_days=[90, 180],
    alos_chart_buffer=None  # バッファもしくはバッファのディクショナリ
):

    chart_cache = get_chart_cache()
    pdf_start_time = time.time()

    try:
        is_ward_pdf = "病棟別" in title_prefix
        is_dept_pdf = "診療科別" in title_prefix

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=15*mm, rightMargin=15*mm,
                                topMargin=18*mm, bottomMargin=18*mm) # マージン微調整
        
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='Normal_JP', parent=styles['Normal'], fontName=REPORTLAB_FONT_NAME, fontSize=8, leading=10))
        styles.add(ParagraphStyle(name='Heading1_JP', parent=styles['Heading1'], fontName=REPORTLAB_FONT_NAME, fontSize=14, spaceAfter=5*mm, leading=16))
        styles.add(ParagraphStyle(name='Heading2_JP', parent=styles['Heading2'], fontName=REPORTLAB_FONT_NAME, fontSize=11, spaceAfter=3*mm, leading=14))
        styles.add(ParagraphStyle(name='Normal_Center_JP', parent=styles['Normal_JP'], alignment=TA_CENTER, fontSize=7, leading=8))

        normal_ja = styles['Normal_JP']
        ja_style = styles['Heading1_JP']
        ja_heading2 = styles['Heading2_JP']
        para_style_normal_center = styles['Normal_Center_JP']

        if latest_date:
            if isinstance(latest_date, str): latest_date = pd.Timestamp(latest_date)
            data_date_str = latest_date.strftime("%Y年%m月%d日")
        else:
            latest_date = pd.Timestamp.now().normalize()
            data_date_str = latest_date.strftime("%Y年%m月%d日")
        
        today_str = pd.Timestamp.now().strftime("%Y年%m月%d日")
        elements = []
        
        report_title_text = f"入院患者数予測 - {title_prefix}（データ基準日: {data_date_str}）"
        elements.append(Paragraph(report_title_text, ja_style))
        elements.append(Spacer(1, 5*mm))

        page_width = A4[0] - doc.leftMargin - doc.rightMargin

        target_val_all, target_val_weekday, target_val_holiday = None, None, None
        if target_data is not None and not target_data.empty and filter_code is not None:
            str_filter_code = str(filter_code)
            target_rows = target_data[target_data['部門コード'].astype(str) == str_filter_code]
            if not target_rows.empty:
                for _, row in target_rows.iterrows():
                    val = row.get('目標値')
                    if pd.notna(val): # NaNでないことを確認
                        if row.get('区分') == '全日': target_val_all = float(val)
                        elif row.get('区分') == '平日': target_val_weekday = float(val)
                        elif row.get('区分') == '休日': target_val_holiday = float(val)
        
        if chart_data is not None and not chart_data.empty:
            data_hash_main = compute_data_hash(chart_data)
            
            # グラフのカウンター（2枚ごとに改ページするため）
            graphs_on_current_page = 0
            max_graphs_per_page = 2
            
            # ===== 1. 平均在院日数グラフ (ALOS) =====
            for days_val in graph_days:
                if graphs_on_current_page >= max_graphs_per_page:
                    elements.append(PageBreak())
                    elements.append(Paragraph(report_title_text, ja_style))
                    elements.append(Spacer(1, 5*mm))
                    graphs_on_current_page = 0
                
                used_alos_chart_buffer = None
                # alos_chart_bufferが辞書形式で、該当する日数のキーがある場合
                if isinstance(alos_chart_buffer, dict) and str(days_val) in alos_chart_buffer:
                    used_alos_chart_buffer = alos_chart_buffer[str(days_val)]
                # alos_chart_bufferが単一のバッファで、90日のグラフの場合
                elif alos_chart_buffer is not None and days_val == 90:
                    used_alos_chart_buffer = alos_chart_buffer
                # それ以外の場合は内部で生成
                else:
                    used_alos_chart_buffer = create_alos_chart_for_pdf(
                        chart_data, title_prefix, latest_date, 30, MATPLOTLIB_FONT_NAME, days_to_show=days_val
                    )
                
                if used_alos_chart_buffer:
                    elements.append(Paragraph(f"平均在院日数と平均在院患者数の推移（直近{days_val}日間）", ja_heading2))
                    elements.append(Spacer(1, 1.5*mm))
                    elements.append(Image(used_alos_chart_buffer, width=page_width*0.9, height=(page_width*0.9)*0.45))
                    elements.append(Spacer(1, 3*mm))
                    graphs_on_current_page += 1

            # グラフセットごとに改ページ
            if graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style))
                elements.append(Spacer(1, 5*mm))
                graphs_on_current_page = 0
            
            # ===== 2. 全日入院患者数推移グラフ =====
            for days_val in graph_days:
                if graphs_on_current_page >= max_graphs_per_page:
                    elements.append(PageBreak())
                    elements.append(Paragraph(report_title_text, ja_style))
                    elements.append(Spacer(1, 5*mm))
                    graphs_on_current_page = 0
                    
                cache_key_all = get_chart_cache_key(title_prefix, days_val, target_val_all, "全日患者数", data_hash_main)
                chart_buffer_all_val = chart_cache.get(cache_key_all)
                if chart_buffer_all_val is None:
                    temp_buf = create_patient_chart_with_target_wrapper(
                        chart_data, title=f"{title_prefix} 全日推移({days_val}日)",
                        days=days_val, show_moving_average=True, target_value=target_val_all
                    )
                    if temp_buf: chart_buffer_all_val = temp_buf.getvalue(); chart_cache[cache_key_all] = chart_buffer_all_val
                if chart_buffer_all_val:
                    img_buf = BytesIO(chart_buffer_all_val); img_buf.seek(0)
                    elements.append(Paragraph(f"全日 入院患者数推移（直近{days_val}日間）", ja_heading2))
                    elements.append(Spacer(1, 1.5*mm)); elements.append(Image(img_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm))
                    graphs_on_current_page += 1
            
            # グラフセットごとに改ページ
            if graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style))
                elements.append(Spacer(1, 5*mm))
                graphs_on_current_page = 0
            
            # ===== 3. 平日入院患者数推移グラフ =====
            # weekday_data, holiday_data の準備
            if "平日判定" in chart_data.columns:
                weekday_data = chart_data[chart_data["平日判定"] == "平日"].copy()
                holiday_data = chart_data[chart_data["平日判定"] == "休日"].copy()
            else:
                weekday_data, holiday_data = pd.DataFrame(), pd.DataFrame() # 空DF
        
            if not weekday_data.empty:
                data_hash_wd = compute_data_hash(weekday_data)
                for days_val in graph_days:
                    if graphs_on_current_page >= max_graphs_per_page:
                        elements.append(PageBreak())
                        elements.append(Paragraph(report_title_text, ja_style))
                        elements.append(Spacer(1, 5*mm))
                        graphs_on_current_page = 0
                        
                    cache_key_wd = get_chart_cache_key(title_prefix, days_val, target_val_weekday, "平日患者数", data_hash_wd)
                    chart_buffer_wd_val = chart_cache.get(cache_key_wd)
                    if chart_buffer_wd_val is None:
                        temp_buf = create_patient_chart_with_target_wrapper(
                            weekday_data, title=f"{title_prefix} 平日推移({days_val}日)",
                            days=days_val, show_moving_average=False, target_value=target_val_weekday
                        )
                        if temp_buf: chart_buffer_wd_val = temp_buf.getvalue(); chart_cache[cache_key_wd] = chart_buffer_wd_val
                    if chart_buffer_wd_val:
                        img_buf = BytesIO(chart_buffer_wd_val); img_buf.seek(0)
                        elements.append(Paragraph(f"平日 入院患者数推移（直近{days_val}日間）", ja_heading2))
                        elements.append(Spacer(1, 1.5*mm)); elements.append(Image(img_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm))
                        graphs_on_current_page += 1
            
            # グラフセットごとに改ページ
            if graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style))
                elements.append(Spacer(1, 5*mm))
                graphs_on_current_page = 0
        
            # ===== 4. 休日入院患者数推移グラフ =====
            if not holiday_data.empty:
                data_hash_hd = compute_data_hash(holiday_data)
                for days_val in graph_days:
                    if graphs_on_current_page >= max_graphs_per_page:
                        elements.append(PageBreak())
                        elements.append(Paragraph(report_title_text, ja_style))
                        elements.append(Spacer(1, 5*mm))
                        graphs_on_current_page = 0
                        
                    cache_key_hd = get_chart_cache_key(title_prefix, days_val, target_val_holiday, "休日患者数", data_hash_hd)
                    chart_buffer_hd_val = chart_cache.get(cache_key_hd)
                    if chart_buffer_hd_val is None:
                        temp_buf = create_patient_chart_with_target_wrapper(
                            holiday_data, title=f"{title_prefix} 休日推移({days_val}日)",
                            days=days_val, show_moving_average=False, target_value=target_val_holiday
                        )
                        if temp_buf: chart_buffer_hd_val = temp_buf.getvalue(); chart_cache[cache_key_hd] = chart_buffer_hd_val
                    if chart_buffer_hd_val:
                        img_buf = BytesIO(chart_buffer_hd_val); img_buf.seek(0)
                        elements.append(Paragraph(f"休日 入院患者数推移（直近{days_val}日間）", ja_heading2))
                        elements.append(Spacer(1, 1.5*mm)); elements.append(Image(img_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm))
                        graphs_on_current_page += 1
            
            # グラフセットごとに改ページ
            if graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style))
                elements.append(Spacer(1, 5*mm))
                graphs_on_current_page = 0
            
            # ===== 5. 二軸グラフ (患者移動と在院数) =====
            for days_val in graph_days:
                if graphs_on_current_page >= max_graphs_per_page:
                    elements.append(PageBreak())
                    elements.append(Paragraph(report_title_text, ja_style))
                    elements.append(Spacer(1, 5*mm))
                    graphs_on_current_page = 0
                    
                cache_key_dual = get_chart_cache_key(title_prefix, days_val, None, "二軸患者移動", data_hash_main)
                chart_buffer_dual_val = chart_cache.get(cache_key_dual)
                if chart_buffer_dual_val is None:
                    # create_dual_axis_chart_from_chart_py は font_name_for_mpl を取るので MATPLOTLIB_FONT_NAME を渡す
                    temp_buf = create_dual_axis_chart_from_chart_py(
                        chart_data, title=f"{title_prefix} 患者移動と在院数 ({days_val}日)", days=days_val, font_name_for_mpl=MATPLOTLIB_FONT_NAME
                    )
                    if temp_buf: chart_buffer_dual_val = temp_buf.getvalue(); chart_cache[cache_key_dual] = chart_buffer_dual_val
                if chart_buffer_dual_val:
                    img_buf = BytesIO(chart_buffer_dual_val); img_buf.seek(0)
                    elements.append(Paragraph(f"患者移動と在院数の推移（直近{days_val}日間）", ja_heading2))
                    elements.append(Spacer(1, 1.5*mm)); elements.append(Image(img_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm))
                    graphs_on_current_page += 1
            
            # 現在のページにグラフが表示されていれば改ページを入れる（テーブルの前に）
            if graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style))
                elements.append(Spacer(1, 5*mm))
        
        # テーブルスタイル共通設定 (前回のものを流用・調整)
        common_table_style_cmds = [
            ('FONTNAME', (0,0), (-1,-1), REPORTLAB_FONT_NAME),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,0), 'CENTER'), 
            ('ALIGN', (1,1), (-1,-1), 'RIGHT'), 
            ('ALIGN', (0,1), (0,-1), 'LEFT'),   
            ('FONTSIZE', (0,0), (-1,0), 9),    
            ('FONTSIZE', (0,1), (-1,-1), 8),   
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), # ヘッダ文字白
            ('LEFTPADDING', (0,0), (-1,-1), 2*mm), # パディング調整
            ('RIGHTPADDING', (0,0), (-1,-1), 2*mm),
        ]

        # 全日平均値テーブル
        if df_all_avg is not None and not df_all_avg.empty:
            elements.append(Paragraph("全日平均値（平日・休日含む）", ja_heading2))
            header = [df_all_avg.index.name if df_all_avg.index.name else "区分"] + df_all_avg.columns.tolist()
            table_data = [header]
            for index, row in df_all_avg.iterrows():
                table_data.append([str(index)] + [f"{x:.1f}" if isinstance(x, (float, int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row])
            
            num_cols = len(header)
            col_widths = [page_width * 0.2] + [(page_width * 0.8) / (num_cols - 1 if num_cols > 1 else 1)] * (num_cols - 1)
            avg_table = Table(table_data, colWidths=col_widths)
            avg_table.setStyle(TableStyle(common_table_style_cmds + [('BACKGROUND', (0,0), (-1,0), colors.green)]))
            elements.append(avg_table); elements.append(Spacer(1, 4*mm))
        else: elements.append(Paragraph("全日平均データなし", normal_ja)); elements.append(Spacer(1, 4*mm))

        # 在院患者数予測テーブル
        if forecast_df is not None and not forecast_df.empty:
            elements.append(Paragraph("在院患者数予測", ja_heading2))
            fc_df_mod = forecast_df.copy()
            if "年間平均人日（実績＋予測）" in fc_df_mod.columns: fc_df_mod = fc_df_mod.rename(columns={"年間平均人日（実績＋予測）": "年度予測"})
            if "延べ予測人日" in fc_df_mod.columns: fc_df_mod = fc_df_mod.drop(columns=["延べ予測人日"])
            
            header = [fc_df_mod.index.name if fc_df_mod.index.name else "基準"] + fc_df_mod.columns.tolist()
            table_data = [header]
            for index, row in fc_df_mod.iterrows():
                table_data.append([str(index)] + [f"{x:.1f}" if isinstance(x, (float, int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row])
            
            num_cols = len(header)
            col_widths = [page_width / num_cols] * num_cols # 均等
            if "基準期間" in header:
                 idx_kikan = header.index("基準期間")
                 col_widths = [page_width * 0.15 if i == idx_kikan else (page_width * 0.85) / (num_cols -1 if num_cols >1 else 1) for i in range(num_cols)]

            forecast_table_obj = Table(table_data, colWidths=col_widths)
            forecast_table_obj.setStyle(TableStyle(common_table_style_cmds + [('BACKGROUND', (0,0), (-1,0), colors.blue)]))
            elements.append(forecast_table_obj); elements.append(Spacer(1, 4*mm))
        else: elements.append(Paragraph("在院患者数予測データなし", normal_ja)); elements.append(Spacer(1, 4*mm))
        
        elements.append(PageBreak())
        elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm))

        # 平日平均値テーブル
        if df_weekday is not None and not df_weekday.empty:
            elements.append(Paragraph("平日平均値", ja_heading2))
            header = [df_weekday.index.name if df_weekday.index.name else "区分"] + df_weekday.columns.tolist()
            table_data = [header]
            for index, row in df_weekday.iterrows():
                table_data.append([str(index)] + [f"{x:.1f}" if isinstance(x, (float, int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row])
            num_cols = len(header)
            col_widths = [page_width * 0.2] + [(page_width * 0.8) / (num_cols - 1 if num_cols > 1 else 1)] * (num_cols - 1)
            weekday_table_obj = Table(table_data, colWidths=col_widths)
            weekday_table_obj.setStyle(TableStyle(common_table_style_cmds + [('BACKGROUND', (0,0), (-1,0), colors.teal)]))
            elements.append(weekday_table_obj); elements.append(Spacer(1, 4*mm))
        else: elements.append(Paragraph("平日平均データなし", normal_ja)); elements.append(Spacer(1, 4*mm))

        # 休日平均値テーブル
        if df_holiday is not None and not df_holiday.empty:
            elements.append(Paragraph("休日平均値", ja_heading2))
            header = [df_holiday.index.name if df_holiday.index.name else "区分"] + df_holiday.columns.tolist()
            table_data = [header]
            for index, row in df_holiday.iterrows():
                table_data.append([str(index)] + [f"{x:.1f}" if isinstance(x, (float, int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row])
            num_cols = len(header)
            col_widths = [page_width * 0.2] + [(page_width * 0.8) / (num_cols - 1 if num_cols > 1 else 1)] * (num_cols - 1)
            holiday_table_obj = Table(table_data, colWidths=col_widths)
            holiday_table_obj.setStyle(TableStyle(common_table_style_cmds + [('BACKGROUND', (0,0), (-1,0), colors.orange)]))
            elements.append(holiday_table_obj); elements.append(Spacer(1, 4*mm))
        else: elements.append(Paragraph("休日平均データなし", normal_ja)); elements.append(Spacer(1, 4*mm))

        # 部門別テーブル
        generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward = [], [], []
        if chart_data is not None and not chart_data.empty and latest_date is not None:
            data_hash_dept_tables = compute_data_hash(chart_data) # このハッシュは chart_data 全体で良い
            cache_key_dept_ward = f"dept_ward_tables_{title_prefix}_{latest_date.strftime('%Y%m%d')}_{data_hash_dept_tables}"
            cached_tables = chart_cache.get(cache_key_dept_ward)
            if cached_tables:
                generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward = cached_tables
            else:
                # create_department_tables は前回の修正案のものを流用
                generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward = create_department_tables(
                    chart_data, latest_date, target_data, filter_code, para_style_normal_center)
                if generated_ward_table_data or generated_dept_table_data:
                    chart_cache[cache_key_dept_ward] = (generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward)
        
        dept_ward_common_style = [
            ('FONTNAME', (0,0), (-1,-1), REPORTLAB_FONT_NAME),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTSIZE', (0,0), (-1,0), 8), 
            ('FONTSIZE', (0,1), (-1,-1), 7),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black), # ヘッダ文字黒
        ]

        if (is_ward_pdf and not is_dept_pdf) or (not is_ward_pdf and not is_dept_pdf) : # 全体または病棟別
            if generated_ward_table_data and len(generated_ward_table_data) > 1:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm))
                elements.append(Paragraph("病棟別 入院患者数（在院）平均", ja_heading2))
                num_cols = len(generated_ward_table_data[0])
                col_widths_ward = [page_width * 0.12] + \
                                  [(page_width * 0.70) / (len(period_labels_dept_ward) if period_labels_dept_ward else 1)] * (len(period_labels_dept_ward) if period_labels_dept_ward else 0) + \
                                  [page_width * 0.09] * 2 # 名称、期間平均、目標、達成率の列幅調整
                if num_cols != len(col_widths_ward) and num_cols > 0: col_widths_ward = [page_width/num_cols] * num_cols
                
                ward_table_obj = Table(generated_ward_table_data, colWidths=col_widths_ward)
                ward_table_obj.setStyle(TableStyle(dept_ward_common_style + [('BACKGROUND', (0,0), (-1,0), colors.lightgrey)])) # 色変更
                elements.append(ward_table_obj); elements.append(Spacer(1, 4*mm))

        if (is_dept_pdf and not is_ward_pdf) or (not is_ward_pdf and not is_dept_pdf) : # 全体または診療科別
            if generated_dept_table_data and len(generated_dept_table_data) > 1:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm))
                elements.append(Paragraph("診療科別 入院患者数（在院）平均", ja_heading2))
                num_cols = len(generated_dept_table_data[0])
                col_widths_dept = [page_width * 0.12] + \
                                   [(page_width * 0.70) / (len(period_labels_dept_ward) if period_labels_dept_ward else 1)] * (len(period_labels_dept_ward) if period_labels_dept_ward else 0) + \
                                   [page_width * 0.09] * 2
                if num_cols != len(col_widths_dept) and num_cols > 0: col_widths_dept = [page_width/num_cols] * num_cols

                dept_table_obj = Table(generated_dept_table_data, colWidths=col_widths_dept)
                dept_table_obj.setStyle(TableStyle(dept_ward_common_style + [('BACKGROUND', (0,0), (-1,0), colors.lightcyan)])) # 色変更
                elements.append(dept_table_obj); elements.append(Spacer(1, 4*mm))

        elements.append(Spacer(1, 8*mm))
        elements.append(Paragraph(f"作成日時: {today_str}", normal_ja))

        doc.build(elements)
        buffer.seek(0)
        pdf_end_time = time.time()
        # print(f"PDF '{title_prefix}' generated in {pdf_end_time - pdf_start_time:.2f} seconds. Size: {len(buffer.getvalue()) / 1024:.1f} KB")
        gc.collect()
        return buffer
    except Exception as e:
        print(f"Error generating PDF for '{title_prefix}': {e}")
        import traceback
        print(traceback.format_exc())
        return None

@st.cache_data(ttl=600, show_spinner=False, max_entries=50)
def create_landscape_pdf(
    forecast_df, df_weekday, df_holiday, df_all_avg=None,
    chart_data=None, title_prefix="全体", latest_date=None,
    target_data=None, filter_code="全体", graph_days=[90, 180],
    alos_chart_buffer=None  # 新しいパラメータを追加
):
    chart_cache = get_chart_cache()
    pdf_start_time = time.time()
    try:
        # (中身は縦PDFとほぼ同様の構成で、グラフとテーブルの配置を横長に最適化)
        # フォント、キャッシュ、データ取得、基本スタイル設定はcreate_pdfと同様
        # ページサイズは landscape(A4)
        # グラフのサイズや配置、テーブルの列幅などを横向き用に調整

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                                leftMargin=12*mm, rightMargin=12*mm,
                                topMargin=12*mm, bottomMargin=12*mm)
        
        styles = getSampleStyleSheet() # 基本スタイル取得
        # 横向き用のスタイル定義
        styles.add(ParagraphStyle(name='Normal_JP_Land', parent=styles['Normal'], fontName=REPORTLAB_FONT_NAME, fontSize=7.5, leading=9))
        styles.add(ParagraphStyle(name='Heading1_JP_Land', parent=styles['Heading1'], fontName=REPORTLAB_FONT_NAME, fontSize=13, spaceAfter=3*mm, leading=15))
        styles.add(ParagraphStyle(name='Heading2_JP_Land', parent=styles['Heading2'], fontName=REPORTLAB_FONT_NAME, fontSize=10, spaceAfter=2*mm, leading=12))
        styles.add(ParagraphStyle(name='Normal_Center_JP_Land', parent=styles['Normal_JP_Land'], alignment=TA_CENTER, fontSize=6.5, leading=8))

        normal_ja_land = styles['Normal_JP_Land']
        ja_style_land = styles['Heading1_JP_Land']
        ja_heading2_land = styles['Heading2_JP_Land']
        para_style_normal_center_land = styles['Normal_Center_JP_Land']

        if latest_date:
            if isinstance(latest_date, str): latest_date = pd.Timestamp(latest_date)
            data_date_str = latest_date.strftime("%Y年%m月%d日")
        else:
            latest_date = pd.Timestamp.now().normalize(); data_date_str = latest_date.strftime("%Y年%m月%d日")
        today_str = pd.Timestamp.now().strftime("%Y年%m月%d日")
        
        elements = []
        report_title_text = f"入院患者数予測 - {title_prefix}（データ基準日: {data_date_str}）"
        elements.append(Paragraph(report_title_text, ja_style_land))
        elements.append(Spacer(1, 3*mm))

        page_width_land, page_height_land = landscape(A4)
        content_width_land = page_width_land - doc.leftMargin - doc.rightMargin

        # グラフカウンターを初期化
        graphs_on_current_page = 0
        max_graphs_per_page = 2  # 横向きPDFでのページあたりの最大グラフ数

        target_val_all, target_val_weekday, target_val_holiday = None, None, None # 目標値取得 (create_pdfと同様)
        if target_data is not None and not target_data.empty and filter_code is not None:
            str_filter_code = str(filter_code)
            target_rows = target_data[target_data['部門コード'].astype(str) == str_filter_code]
            if not target_rows.empty:
                for _, row in target_rows.iterrows():
                    val = row.get('目標値')
                    if pd.notna(val):
                        if row.get('区分') == '全日': target_val_all = float(val)
                        elif row.get('区分') == '平日': target_val_weekday = float(val)
                        elif row.get('区分') == '休日': target_val_holiday = float(val)
        
        # グラフ (横向きでは2x2などで配置可能)
        if chart_data is not None and not chart_data.empty:
            data_hash_main_land = compute_data_hash(chart_data)
            
            # ===== 1. 平均在院日数グラフ (ALOS) =====
            for days_val in graph_days:
                if graphs_on_current_page >= max_graphs_per_page:
                    elements.append(PageBreak())
                    elements.append(Paragraph(report_title_text, ja_style_land))
                    elements.append(Spacer(1, 3*mm))
                    graphs_on_current_page = 0
                
                used_alos_chart_buffer = None
                # alos_chart_bufferが辞書形式で、該当する日数のキーがある場合
                if isinstance(alos_chart_buffer, dict) and str(days_val) in alos_chart_buffer:
                    used_alos_chart_buffer = alos_chart_buffer[str(days_val)]
                # alos_chart_bufferが単一のバッファで、90日のグラフの場合
                elif alos_chart_buffer is not None and days_val == 90:
                    used_alos_chart_buffer = alos_chart_buffer
                # それ以外の場合は内部で生成
                else:
                    used_alos_chart_buffer = create_alos_chart_for_pdf(
                        chart_data, title_prefix, latest_date, 30, MATPLOTLIB_FONT_NAME, days_to_show=days_val
                    )
                
                if used_alos_chart_buffer:
                    elements.append(Paragraph(f"平均在院日数と平均在院患者数の推移（直近{days_val}日間）", ja_heading2_land))
                    elements.append(Spacer(1, 1.5*mm))
                    elements.append(Image(used_alos_chart_buffer, width=content_width_land*0.9, height=(content_width_land*0.9)*0.4))
                    elements.append(Spacer(1, 3*mm))
                    graphs_on_current_page += 1
            
            # グラフセットごとに改ページ
            if graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style_land))
                elements.append(Spacer(1, 3*mm))
                graphs_on_current_page = 0
            
            # ===== 2. 全日入院患者数推移グラフ =====
            for days_val in graph_days:
                if graphs_on_current_page >= max_graphs_per_page:
                    elements.append(PageBreak())
                    elements.append(Paragraph(report_title_text, ja_style_land))
                    elements.append(Spacer(1, 3*mm))
                    graphs_on_current_page = 0
                
                cache_key_all_land = get_chart_cache_key(title_prefix, days_val, target_val_all, "全日患者数_Land", data_hash_main_land)
                chart_all_val = chart_cache.get(cache_key_all_land)
                if chart_all_val is None:
                    temp_buf = create_patient_chart_with_target_wrapper(chart_data, title=f"{title_prefix} 全日({days_val}日)", days=days_val, target_value=target_val_all)
                    if temp_buf: chart_all_val = temp_buf.getvalue(); chart_cache[cache_key_all_land] = chart_all_val
                if chart_all_val:
                    img_buf = BytesIO(chart_all_val); img_buf.seek(0)
                    elements.append(Paragraph(f"全日 入院患者数推移（直近{days_val}日間）", ja_heading2_land))
                    elements.append(Spacer(1, 1.5*mm))
                    elements.append(Image(img_buf, width=content_width_land*0.9, height=(content_width_land*0.9)*0.4))
                    elements.append(Spacer(1, 3*mm))
                    graphs_on_current_page += 1
            
            # グラフセットごとに改ページ
            if graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style_land))
                elements.append(Spacer(1, 3*mm))
                graphs_on_current_page = 0
            
            # ===== 3. 平日入院患者数推移グラフ =====
            # 平日データの準備
            if "平日判定" in chart_data.columns:
                weekday_data = chart_data[chart_data["平日判定"] == "平日"].copy()
                holiday_data = chart_data[chart_data["平日判定"] == "休日"].copy()
            else:
                weekday_data, holiday_data = pd.DataFrame(), pd.DataFrame() # 空DF
                
            if not weekday_data.empty:
                data_hash_wd_land = compute_data_hash(weekday_data)
                for days_val in graph_days:
                    if graphs_on_current_page >= max_graphs_per_page:
                        elements.append(PageBreak())
                        elements.append(Paragraph(report_title_text, ja_style_land))
                        elements.append(Spacer(1, 3*mm))
                        graphs_on_current_page = 0
                        
                    cache_key_wd_land = get_chart_cache_key(title_prefix, days_val, target_val_weekday, "平日患者数_Land", data_hash_wd_land)
                    chart_wd_val = chart_cache.get(cache_key_wd_land)
                    if chart_wd_val is None:
                        temp_buf = create_patient_chart_with_target_wrapper(weekday_data, title=f"{title_prefix} 平日({days_val}日)", days=days_val, target_value=target_val_weekday)
                        if temp_buf: chart_wd_val = temp_buf.getvalue(); chart_cache[cache_key_wd_land] = chart_wd_val
                    if chart_wd_val:
                        img_buf = BytesIO(chart_wd_val); img_buf.seek(0)
                        elements.append(Paragraph(f"平日 入院患者数推移（直近{days_val}日間）", ja_heading2_land))
                        elements.append(Spacer(1, 1.5*mm))
                        elements.append(Image(img_buf, width=content_width_land*0.9, height=(content_width_land*0.9)*0.4))
                        elements.append(Spacer(1, 3*mm))
                        graphs_on_current_page += 1
            
            # グラフセットごとに改ページ
            if graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style_land))
                elements.append(Spacer(1, 3*mm))
                graphs_on_current_page = 0
            
            # ===== 4. 休日入院患者数推移グラフ =====
            if not holiday_data.empty:
                data_hash_hd_land = compute_data_hash(holiday_data)
                for days_val in graph_days:
                    if graphs_on_current_page >= max_graphs_per_page:
                        elements.append(PageBreak())
                        elements.append(Paragraph(report_title_text, ja_style_land))
                        elements.append(Spacer(1, 3*mm))
                        graphs_on_current_page = 0
                        
                    cache_key_hd_land = get_chart_cache_key(title_prefix, days_val, target_val_holiday, "休日患者数_Land", data_hash_hd_land)
                    chart_hd_val = chart_cache.get(cache_key_hd_land)
                    if chart_hd_val is None:
                        temp_buf = create_patient_chart_with_target_wrapper(holiday_data, title=f"{title_prefix} 休日({days_val}日)", days=days_val, target_value=target_val_holiday)
                        if temp_buf: chart_hd_val = temp_buf.getvalue(); chart_cache[cache_key_hd_land] = chart_hd_val
                    if chart_hd_val:
                        img_buf = BytesIO(chart_hd_val); img_buf.seek(0)
                        elements.append(Paragraph(f"休日 入院患者数推移（直近{days_val}日間）", ja_heading2_land))
                        elements.append(Spacer(1, 1.5*mm))
                        elements.append(Image(img_buf, width=content_width_land*0.9, height=(content_width_land*0.9)*0.4))
                        elements.append(Spacer(1, 3*mm))
                        graphs_on_current_page += 1
                        
            # グラフセットごとに改ページ
            if graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style_land))
                elements.append(Spacer(1, 3*mm))
                graphs_on_current_page = 0
            
            # ===== 5. 二軸グラフ (患者移動と在院数) =====
            for days_val in graph_days:
                if graphs_on_current_page >= max_graphs_per_page:
                    elements.append(PageBreak())
                    elements.append(Paragraph(report_title_text, ja_style_land))
                    elements.append(Spacer(1, 3*mm))
                    graphs_on_current_page = 0
                    
                cache_key_dual_land = get_chart_cache_key(title_prefix, days_val, None, "二軸_Land", data_hash_main_land)
                chart_dual_val = chart_cache.get(cache_key_dual_land)
                if chart_dual_val is None:
                    temp_buf = create_dual_axis_chart_from_chart_py(chart_data, title=f"{title_prefix} 患者移動({days_val}日)", days=days_val, font_name_for_mpl=MATPLOTLIB_FONT_NAME)
                    if temp_buf: chart_dual_val = temp_buf.getvalue(); chart_cache[cache_key_dual_land] = chart_dual_val
                if chart_dual_val:
                    img_buf = BytesIO(chart_dual_val); img_buf.seek(0)
                    elements.append(Paragraph(f"患者移動と在院数の推移（直近{days_val}日間）", ja_heading2_land))
                    elements.append(Spacer(1, 1.5*mm))
                    elements.append(Image(img_buf, width=content_width_land*0.9, height=(content_width_land*0.9)*0.4))
                    elements.append(Spacer(1, 3*mm))
                    graphs_on_current_page += 1
            
            # グラフが表示されていれば改ページ
            if graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style_land))
                elements.append(Spacer(1, 3*mm))
                graphs_on_current_page = 0

        # テーブル (横向き用に列幅や配置を調整)
        common_table_style_land_cmds = [ # create_pdfから流用、フォントサイズなど調整
            ('FONTNAME', (0,0), (-1,-1), REPORTLAB_FONT_NAME),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,0), 'CENTER'), 
            ('ALIGN', (1,1), (-1,-1), 'RIGHT'), 
            ('ALIGN', (0,1), (0,-1), 'LEFT'),   
            ('FONTSIZE', (0,0), (-1,0), 8),    # ヘッダー少し小さめ
            ('FONTSIZE', (0,1), (-1,-1), 7.5),   # データ少し小さめ
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('LEFTPADDING', (0,0), (-1,-1), 1.5*mm), 
            ('RIGHTPADDING', (0,0), (-1,-1), 1.5*mm),
        ]
        
        # 全日平均テーブル (横幅いっぱい)
        if df_all_avg is not None and not df_all_avg.empty:
            elements.append(Paragraph("全日平均値", ja_heading2_land))
            header = [df_all_avg.index.name if df_all_avg.index.name else "区分"] + df_all_avg.columns.tolist()
            table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x, (float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_all_avg.iterrows()]
            num_cols = len(header)
            col_widths = [content_width_land * 0.15] + [(content_width_land * 0.85) / (num_cols - 1 if num_cols > 1 else 1)] * (num_cols-1)
            tbl = Table(table_data, colWidths=col_widths)
            tbl.setStyle(TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.green)]))
            elements.append(tbl); elements.append(Spacer(1, 2*mm))

        # 予測テーブル (横幅いっぱい)
        if forecast_df is not None and not forecast_df.empty:
            elements.append(Paragraph("在院患者数予測", ja_heading2_land))
            # (create_pdfと同様のデータ準備)
            fc_df_mod = forecast_df.copy()
            if "年間平均人日（実績＋予測）" in fc_df_mod.columns: fc_df_mod = fc_df_mod.rename(columns={"年間平均人日（実績＋予測）": "年度予測"})
            if "延べ予測人日" in fc_df_mod.columns: fc_df_mod = fc_df_mod.drop(columns=["延べ予測人日"])
            header = [fc_df_mod.index.name if fc_df_mod.index.name else "基準"] + fc_df_mod.columns.tolist()
            table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x, (float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in fc_df_mod.iterrows()]
            num_cols = len(header)
            col_widths = [content_width_land / num_cols] * num_cols # 均等割りが多い
            tbl = Table(table_data, colWidths=col_widths)
            tbl.setStyle(TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.blue)]))
            elements.append(tbl); elements.append(Spacer(1, 2*mm))

        elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm))

        # 平日・休日テーブルを左右に配置
        left_col_elements = []
        right_col_elements = []
        table_half_width = content_width_land * 0.48

        if df_weekday is not None and not df_weekday.empty:
            left_col_elements.append(Paragraph("平日平均値", ja_heading2_land))
            header = [df_weekday.index.name if df_weekday.index.name else "区分"] + df_weekday.columns.tolist()
            table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x, (float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_weekday.iterrows()]
            num_cols = len(header)
            col_widths = [table_half_width * 0.25] + [(table_half_width*0.75)/(num_cols-1 if num_cols > 1 else 1)] * (num_cols-1)
            tbl = Table(table_data, colWidths=col_widths)
            tbl.setStyle(TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.teal)]))
            left_col_elements.append(tbl)
        
        if df_holiday is not None and not df_holiday.empty:
            right_col_elements.append(Paragraph("休日平均値", ja_heading2_land))
            header = [df_holiday.index.name if df_holiday.index.name else "区分"] + df_holiday.columns.tolist()
            table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x, (float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_holiday.iterrows()]
            num_cols = len(header)
            col_widths = [table_half_width * 0.25] + [(table_half_width*0.75)/(num_cols-1 if num_cols > 1 else 1)] * (num_cols-1)
            tbl = Table(table_data, colWidths=col_widths)
            tbl.setStyle(TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.orange)]))
            right_col_elements.append(tbl)

        if left_col_elements or right_col_elements:
            elements.append(Table([[left_col_elements if left_col_elements else "", right_col_elements if right_col_elements else ""]], 
                                colWidths=[table_half_width, content_width_land - table_half_width - 2*mm])) # Spacer分を考慮
        elements.append(Spacer(1, 2*mm))

        # 部門別テーブル (create_pdf と同様のロジックで、横向き用にスタイル調整)
        generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward = [], [], []
        if chart_data is not None and not chart_data.empty and latest_date is not None:
            # キャッシュキーは Land をつけるなどして区別
            cache_key_dept_ward_land = f"dept_ward_tables_land_{title_prefix}_{latest_date.strftime('%Y%m%d')}_{compute_data_hash(chart_data)}"
            cached_tables = chart_cache.get(cache_key_dept_ward_land)
            if cached_tables:
                generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward = cached_tables
            else:
                generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward = create_department_tables(
                    chart_data, latest_date, target_data, filter_code, para_style_normal_center_land) # 横向き用スタイル
                if generated_ward_table_data or generated_dept_table_data:
                    chart_cache[cache_key_dept_ward_land] = (generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward)

        dept_ward_style_land = [ # フォントサイズなど横向き用に調整
            ('FONTNAME', (0,0), (-1,-1), REPORTLAB_FONT_NAME), ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTSIZE', (0,0), (-1,0), 7), ('FONTSIZE', (0,1), (-1,-1), 6.5),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ]
        is_ward_pdf = "病棟別" in title_prefix
        is_dept_pdf = "診療科別" in title_prefix

        if (is_ward_pdf and not is_dept_pdf) or (not is_ward_pdf and not is_dept_pdf) :
            if generated_ward_table_data and len(generated_ward_table_data) > 1:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm))
                elements.append(Paragraph("病棟別 入院患者数（在院）平均", ja_heading2_land))
                num_cols = len(generated_ward_table_data[0])
                col_widths = [content_width_land * 0.10] + \
                             [(content_width_land * 0.72) / (len(period_labels_dept_ward) if period_labels_dept_ward else 1)] * (len(period_labels_dept_ward) if period_labels_dept_ward else 0) + \
                             [content_width_land * 0.09] * 2
                if num_cols != len(col_widths) and num_cols > 0: col_widths = [content_width_land/num_cols] * num_cols
                tbl = Table(generated_ward_table_data, colWidths=col_widths)
                tbl.setStyle(TableStyle(dept_ward_style_land + [('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
                elements.append(tbl); elements.append(Spacer(1, 2*mm))
        
        if (is_dept_pdf and not is_ward_pdf) or (not is_ward_pdf and not is_dept_pdf) :
            if generated_dept_table_data and len(generated_dept_table_data) > 1:
                # 病棟別テーブルが同じページに既にあれば改ページ不要、なければ改ページ
                if not ((is_ward_pdf and not is_dept_pdf) or (not is_ward_pdf and not is_dept_pdf) and generated_ward_table_data and len(generated_ward_table_data) > 1 and elements[-1] != PageBreak()):
                     elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm))
                elements.append(Paragraph("診療科別 入院患者数（在院）平均", ja_heading2_land))
                num_cols = len(generated_dept_table_data[0])
                col_widths = [content_width_land * 0.10] + \
                             [(content_width_land * 0.72) / (len(period_labels_dept_ward) if period_labels_dept_ward else 1)] * (len(period_labels_dept_ward) if period_labels_dept_ward else 0) + \
                             [content_width_land * 0.09] * 2
                if num_cols != len(col_widths) and num_cols > 0: col_widths = [content_width_land/num_cols] * num_cols
                tbl = Table(generated_dept_table_data, colWidths=col_widths)
                tbl.setStyle(TableStyle(dept_ward_style_land + [('BACKGROUND', (0,0), (-1,0), colors.lightcyan)]))
                elements.append(tbl); elements.append(Spacer(1, 2*mm))

        elements.append(Spacer(1, 5*mm))
        elements.append(Paragraph(f"作成日時: {today_str}", normal_ja_land))

        doc.build(elements)
        buffer.seek(0)
        pdf_end_time = time.time()
        # print(f"Landscape PDF '{title_prefix}' generated in {pdf_end_time - pdf_start_time:.2f} seconds. Size: {len(buffer.getvalue()) / 1024:.1f} KB")
        gc.collect()
        return buffer
    except Exception as e:
        print(f"Error generating landscape PDF for '{title_prefix}': {e}")
        import traceback
        print(traceback.format_exc())
        return None

# --- 部門別テーブル生成関数 (前回の修正案を流用) ---
def create_department_tables(chart_data, latest_date, target_data=None, filter_code=None, para_style=None):
    """
    診療科別・病棟別のテーブルデータを作成する (table_generator.py と同じ計算方法を使用)
    """
    dept_tbl_start_time = time.time()
    if chart_data is None or chart_data.empty or latest_date is None:
        print("部門別テーブル生成に必要なデータ不足 (chart_data or latest_date is None or empty)")
        return [], [], []

    if not pd.api.types.is_datetime64_any_dtype(chart_data['日付']):
        try:
            chart_data['日付'] = pd.to_datetime(chart_data['日付'])
        except Exception as e:
            print(f"Error converting '日付' to datetime: {e}")
            return [], [], []
    if not isinstance(latest_date, pd.Timestamp):
        latest_date = pd.Timestamp(latest_date)

    # table_generator.py と同じ期間定義を使用
    # 会計年度情報を取得
    current_year_start_month = 4
    if latest_date.month < current_year_start_month:
        current_fiscal_year_start = pd.Timestamp(year=latest_date.year - 1, month=current_year_start_month, day=1)
    else:
        current_fiscal_year_start = pd.Timestamp(year=latest_date.year, month=current_year_start_month, day=1)
    current_fiscal_year_end_for_data = latest_date
    previous_fiscal_year_start = current_fiscal_year_start - pd.DateOffset(years=1)
    previous_fiscal_year_end = current_fiscal_year_start - pd.Timedelta(days=1)

    # 期間定義を table_generator.py と一致させる
    period_definitions = {
        "直近7日": (latest_date - pd.Timedelta(days=6), latest_date),
        "直近14日": (latest_date - pd.Timedelta(days=13), latest_date),
        "直近30日": (latest_date - pd.Timedelta(days=29), latest_date),
        "直近60日": (latest_date - pd.Timedelta(days=59), latest_date),
        f"{current_fiscal_year_start.year}年度": (current_fiscal_year_start, current_fiscal_year_end_for_data),
        f"{previous_fiscal_year_start.year}年度": (previous_fiscal_year_start, previous_fiscal_year_end),
    }
    period_labels_for_data = list(period_definitions.keys())
    period_name_for_achievement = "直近30日"  # table_generator.py と同じ期間を使用
    
    if para_style is None:
        styles = getSampleStyleSheet() # 基本スタイル
        font_name_to_use = REPORTLAB_FONT_NAME if REPORTLAB_FONT_NAME and pdfmetrics.getFont(REPORTLAB_FONT_NAME) else 'Helvetica'
        para_style = ParagraphStyle('ParaNormalCenterDefault_Dept', parent=styles['Normal'], fontName=font_name_to_use, fontSize=6.5, alignment=TA_CENTER, leading=7)

    period_labels_for_header = [Paragraph(label.replace("直近", "直近<br/>").replace("年度", "<br/>年度"), para_style) for label in period_labels_for_data]

    # 部門リストの取得
    ward_codes_unique = sorted(chart_data["病棟コード"].astype(str).unique())
    dept_names_original = sorted(chart_data["診療科名"].unique())
    
    # サイドバーの診療科表示設定を考慮
    show_all_depts = True 
    use_selected_depts = False
    selected_depts_list = []
    try:
        if 'st' in globals() and hasattr(st, 'session_state'):
            show_all_depts = st.session_state.get('show_all_depts', True)
            use_selected_depts = st.session_state.get('use_selected_depts', False)
            selected_depts_list = st.session_state.get('selected_depts', [])
    except Exception:
        pass

    dept_names_to_process = dept_names_original
    if not show_all_depts:
        if use_selected_depts and selected_depts_list:
            dept_names_to_process = [dept for dept in dept_names_original if dept in selected_depts_list]
    
    # 病棟表示名の作成
    ward_display_names = {}
    for ward_code in ward_codes_unique:
        if target_data is not None and not target_data.empty and '部門コード' in target_data.columns and '部門名' in target_data.columns:
            target_row = target_data[target_data['部門コード'].astype(str) == ward_code]
            if not target_row.empty and pd.notna(target_row['部門名'].iloc[0]):
                ward_display_names[ward_code] = target_row['部門名'].iloc[0]
                continue
        
        # デフォルト名を使用
        match = re.match(r'0*(\d+)([A-Za-z]*)', ward_code)
        if match:
            num_part, alpha_part = match.group(1), match.group(2)
            ward_display_names[ward_code] = f"{num_part}{alpha_part}病棟"  # 修正: 例 "3A病棟"
        else: 
            ward_display_names[ward_code] = ward_code

    # 結果格納用の辞書を初期化
    ward_metrics = {ward_code: {} for ward_code in ward_codes_unique}
    dept_metrics = {dept_name: {} for dept_name in dept_names_to_process}

    # 各期間ごとに集計 - table_generator.py と同じ計算方法
    for period_label, (start_date, end_date) in period_definitions.items():
        if start_date > end_date: 
            continue
            
        # 期間データをフィルタリング
        period_data = chart_data[(chart_data["日付"] >= start_date) & (chart_data["日付"] <= end_date)]
        if period_data.empty:
            continue
            
        # 期間内の日数を計算
        num_days_in_period = period_data['日付'].nunique()
        if num_days_in_period == 0:
            continue
            
        # 病棟別集計
        for ward_code in ward_codes_unique:
            ward_data = period_data[period_data["病棟コード"].astype(str) == ward_code]
            if not ward_data.empty and '入院患者数（在院）' in ward_data.columns:
                # 日別の患者数総計を計算 - table_generator.py と同じ計算方法
                total_patient_days = ward_data.groupby('日付')['入院患者数（在院）'].sum().sum()
                avg_daily_census = total_patient_days / num_days_in_period
                ward_metrics[ward_code][period_label] = avg_daily_census
            else:
                ward_metrics[ward_code][period_label] = float('nan')
        
        # 診療科別集計
        for dept_name in dept_names_to_process:
            dept_data = period_data[period_data["診療科名"] == dept_name]
            if not dept_data.empty and '入院患者数（在院）' in dept_data.columns:
                # 日別の患者数総計を計算 - table_generator.py と同じ計算方法
                total_patient_days = dept_data.groupby('日付')['入院患者数（在院）'].sum().sum()
                avg_daily_census = total_patient_days / num_days_in_period
                dept_metrics[dept_name][period_label] = avg_daily_census
            else:
                dept_metrics[dept_name][period_label] = float('nan')
    
    # 目標値と達成率の取得
    target_dict_cache = {}
    
    # 目標値と達成率を計算する関数
    def get_targets_achievements(items, metrics_dict, target_data_df, achievement_period=period_name_for_achievement):
        targets = {}
        achievements = {}
        
        if target_data_df is not None and not target_data_df.empty and \
           all(col in target_data_df.columns for col in ['部門コード', '区分', '目標値']):
            target_data_df['部門コード'] = target_data_df['部門コード'].astype(str)
            
            # 全日目標値のキャッシュ
            if 'all_targets' not in target_dict_cache:
                all_targets_map = {}
                for _, row in target_data_df[target_data_df['区分'] == '全日'].iterrows():
                    if pd.notna(row.get('部門コード')) and pd.notna(row.get('目標値')):
                        all_targets_map[str(row['部門コード'])] = float(row['目標値'])
                target_dict_cache['all_targets'] = all_targets_map
            
            all_targets_map = target_dict_cache.get('all_targets', {})
            
            for item_id in items:
                item_id_str = str(item_id)
                target_value = all_targets_map.get(item_id_str)
                
                if target_value is not None:
                    targets[item_id] = target_value
                    # 達成率を計算
                    actual_value = metrics_dict[item_id].get(achievement_period)
                    if actual_value is not None and pd.notna(actual_value) and target_value > 0:
                        achievements[item_id] = (actual_value / target_value) * 100
        
        return targets, achievements

    # 目標値と達成率を取得
    ward_targets, ward_achievements = get_targets_achievements(ward_codes_unique, ward_metrics, target_data)
    dept_targets, dept_achievements = get_targets_achievements(dept_names_to_process, dept_metrics, target_data)
    
    # 達成率に基づいたソート
    def sort_entities(entities, achievements_ref, targets_ref):
        sorted_by_achievement = sorted([e for e in entities if e in achievements_ref], key=lambda x: achievements_ref.get(x, 0), reverse=True)
        sorted_by_target_only = sorted([e for e in entities if e in targets_ref and e not in achievements_ref])
        sorted_by_no_target = sorted([e for e in entities if e not in targets_ref])
        return sorted_by_achievement + sorted_by_target_only + sorted_by_no_target

    # 病棟と診療科をソート
    sorted_ward_codes = sort_entities(ward_codes_unique, ward_achievements, ward_targets)
    sorted_dept_names = sort_entities(dept_names_to_process, dept_achievements, dept_targets)
    
    # テーブルヘッダー
    header_items = [Paragraph("部門", para_style)] + period_labels_for_header + [Paragraph("目標値", para_style), Paragraph("達成率<br/>(%)", para_style)]
    
    # 病棟別テーブルデータ
    ward_table_data = [header_items]
    for ward_code in sorted_ward_codes:
        row_items = [Paragraph(ward_display_names.get(ward_code, ward_code), para_style)]
        for period in period_labels_for_data:
            val = ward_metrics[ward_code].get(period)
            row_items.append(f"{val:.1f}" if pd.notna(val) else "-")
        row_items.append(f"{ward_targets[ward_code]:.1f}" if ward_code in ward_targets else "-")
        row_items.append(f"{ward_achievements[ward_code]:.1f}" if ward_code in ward_achievements else "-")
        ward_table_data.append(row_items)

    # 診療科別テーブルデータ
    dept_table_data = [header_items]
    for dept_name in sorted_dept_names:
        row_items = [Paragraph(str(dept_name), para_style)]
        for period in period_labels_for_data:
            val = dept_metrics[dept_name].get(period)
            row_items.append(f"{val:.1f}" if pd.notna(val) else "-")
        row_items.append(f"{dept_targets[dept_name]:.1f}" if dept_name in dept_targets else "-")
        row_items.append(f"{dept_achievements[dept_name]:.1f}" if dept_name in dept_achievements else "-")
        dept_table_data.append(row_items)
    
    print(f"Department tables generated in {time.time() - dept_tbl_start_time:.2f} seconds.")
    return ward_table_data, dept_table_data, period_labels_for_data