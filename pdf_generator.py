import pandas as pd
import streamlit as st # For st.session_state (used by get_chart_cache)
from io import BytesIO
import os
import re
import time
import hashlib
import gc
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# chart.py から Matplotlib ベースの関数をインポート (直接は使わないが型ヒント等で参照可能性あり)
# from chart import create_patient_chart as create_base_patient_chart_from_chart_py
# from chart import create_dual_axis_chart as create_dual_axis_chart_from_chart_py

import matplotlib.font_manager
import matplotlib.pyplot as plt

# --- フォント設定 ---
FONT_DIR = 'fonts'
FONT_FILENAME = 'NotoSansJP-Regular.ttf'
FONT_PATH = os.path.join(FONT_DIR, FONT_FILENAME)
REPORTLAB_FONT_NAME = 'NotoSansJP_RL'
MATPLOTLIB_FONT_NAME_FALLBACK = 'sans-serif'
MATPLOTLIB_FONT_NAME = None

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
            font_entry = matplotlib.font_manager.FontEntry(
                fname=FONT_PATH, name='NotoSansJP_MPL'
            )
            matplotlib.font_manager.fontManager.ttflist.insert(0, font_entry)
            plt.rcParams['font.family'] = font_entry.name
            MATPLOTLIB_FONT_NAME = font_entry.name
            print(f"Matplotlib default font set to '{MATPLOTLIB_FONT_NAME}' using {FONT_PATH}.")
            font_registered_mpl = True
        except Exception as e:
            print(f"Failed to set Matplotlib font '{FONT_PATH}': {e}")
            plt.rcParams['font.family'] = MATPLOTLIB_FONT_NAME_FALLBACK
            MATPLOTLIB_FONT_NAME = None # Ensure it's None if registration failed
    else:
        print(f"Font file not found at '{FONT_PATH}'. Using fallback fonts.")
        plt.rcParams['font.family'] = MATPLOTLIB_FONT_NAME_FALLBACK
        # MATPLOTLIB_FONT_NAME is already None by default

    if not font_registered_rl:
        print(f"ReportLab will use its default font or Helvetica if '{REPORTLAB_FONT_NAME}' was intended as NotoSansJP.")

register_fonts()

# --- キャッシュ設定 (メインプロセスでのみ使用される想定) ---
def get_chart_cache(): # pdf_generator.py 固有のキャッシュ (メインプロセス用)
    if 'pdf_chart_cache' not in st.session_state:
        st.session_state.pdf_chart_cache = {}
    return st.session_state.pdf_chart_cache

def compute_data_hash(data):
    if data is None or data.empty:
        return "empty_data_hash"
    try:
        if '日付' in data.columns and '入院患者数（在院）' in data.columns:
            # More robust hashing for pandas DataFrame
            return hashlib.md5(pd.util.hash_pandas_object(data, index=True).values.tobytes()).hexdigest()
        else:
            return hashlib.md5(pd.util.hash_pandas_object(data.head(20), index=True).values.tobytes()).hexdigest()
    except Exception as e:
        print(f"Error computing data hash: {e}")
        return hashlib.md5(str(time.time()).encode()).hexdigest() # Fallback to time-based hash

def get_chart_cache_key(title, days, target_value=None, chart_type="default", data_hash=None):
    components = [str(title), str(days)]
    if target_value is not None:
        try:
            components.append(f"{float(target_value):.2f}")
        except (ValueError, TypeError):
            components.append(str(target_value))
    else:
        components.append("None")
    components.append(str(chart_type))
    if data_hash:
        components.append(data_hash)
    key_string = "_".join(components)
    return hashlib.md5(key_string.encode()).hexdigest()

# --- グラフ生成関数 (これらはメインプロセスでキャッシュ管理され、結果のバッファがワーカーに渡される) ---
# これらの関数は Streamlit のセッション状態に依存しないようにする
def create_alos_chart_for_pdf(
    chart_data, title_prefix="全体", latest_date=None,
    moving_avg_window=30, font_name_for_mpl_to_use=None, # Use a different name
    days_to_show=90
):
    start_time = time.time()
    fig = None
    actual_font_name = font_name_for_mpl_to_use if font_name_for_mpl_to_use else MATPLOTLIB_FONT_NAME
    try:
        fig, ax1 = plt.subplots(figsize=(10, 5.5))
        if not isinstance(chart_data, pd.DataFrame) or chart_data.empty: return None
        required_columns = ["日付", "入院患者数（在院）", "総入院患者数", "総退院患者数"]
        if any(col not in chart_data.columns for col in required_columns): return None

        data_copy = chart_data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)
        if data_copy.empty: return None

        current_latest_date = latest_date if latest_date else data_copy['日付'].max()
        if pd.isna(current_latest_date): current_latest_date = pd.Timestamp.now()

        start_date_limit = current_latest_date - pd.Timedelta(days=days_to_show -1) # -1 to include the start day

        daily_metrics = []
        # Iterate from start_date_limit up to current_latest_date for the rolling window calculation
        # The data for rolling window should come from `chart_data` (original data before `days_to_show` filter)
        date_range_for_plot = pd.date_range(start=start_date_limit, end=current_latest_date, freq='D')

        for display_date in date_range_for_plot:
            window_start = display_date - pd.Timedelta(days=moving_avg_window - 1)
            # Use original chart_data for window calculation, not chart_data_filtered
            window_data = chart_data[(chart_data['日付'] >= window_start) & (chart_data['日付'] <= display_date)]
            if not window_data.empty:
                total_patient_days = window_data['入院患者数（在院）'].sum()
                total_admissions = window_data['総入院患者数'].sum()
                total_discharges = window_data['総退院患者数'].sum()
                num_days_in_window = window_data['日付'].nunique()
                denominator = (total_admissions + total_discharges) / 2
                alos = total_patient_days / denominator if denominator > 0 else 0
                daily_census = total_patient_days / num_days_in_window if num_days_in_window > 0 else 0
                daily_metrics.append({'日付': display_date, '平均在院日数': alos, '平均在院患者数': daily_census})

        if not daily_metrics: return None
        daily_df = pd.DataFrame(daily_metrics).sort_values('日付')
        if daily_df.empty: return None


        font_kwargs = {'fontname': actual_font_name} if actual_font_name else {}
        ax1.plot(daily_df['日付'], daily_df['平均在院日数'], color='#3498db', linewidth=2, marker='o', markersize=4, label=f"平均在院日数({moving_avg_window}日MA)")
        ax1.set_xlabel('日付', fontsize=10, **font_kwargs)
        ax1.set_ylabel('平均在院日数', fontsize=10, color='#3498db', **font_kwargs)
        ax1.tick_params(axis='y', labelcolor='#3498db', labelsize=8)
        ax1.tick_params(axis='x', labelsize=8, rotation=30, ha='right')

        ax2 = ax1.twinx()
        ax2.plot(daily_df['日付'], daily_df['平均在院患者数'], color='#e74c3c', linewidth=2, linestyle='--', label='平均在院患者数')
        ax2.set_ylabel('平均在院患者数', fontsize=10, color='#e74c3c', **font_kwargs)
        ax2.tick_params(axis='y', labelcolor='#e74c3c', labelsize=8)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_prop = {'size': 8}; legend_prop.update(font_kwargs)
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_prop)
        plt.title(f"{title_prefix} ALOSと在院患者数(直近{days_to_show}日)", fontsize=12, **font_kwargs)
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        plt.tight_layout(pad=0.8)
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        # print(f"ALOS Chart for PDF ({title_prefix}, {days_to_show}d) generated in {time.time() - start_time:.2f}s")
        return buf
    except Exception as e:
        print(f"Error in create_alos_chart_for_pdf for {title_prefix}: {e}")
        import traceback; print(traceback.format_exc())
        return None
    finally:
        if fig: plt.close(fig)
        gc.collect()

def create_patient_chart_with_target_wrapper(
    data, title="入院患者数推移", days=90, show_moving_average=True, target_value=None,
    font_name_for_mpl_to_use=None # Use a different name
):
    fig = None
    actual_font_name = font_name_for_mpl_to_use if font_name_for_mpl_to_use else MATPLOTLIB_FONT_NAME
    try:
        fig, ax = plt.subplots(figsize=(8, 4.0))
        if not isinstance(data, pd.DataFrame) or data.empty: return None
        if "日付" not in data.columns or "入院患者数（在院）" not in data.columns: return None

        data_copy = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)
        if data_copy.empty : return None

        grouped = data_copy.groupby("日付")["入院患者数（在院）"].sum().reset_index().sort_values("日付")
        if len(grouped) > days: grouped = grouped.tail(days)
        if grouped.empty: return None

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
                caution_threshold = target_val_float * 0.97
                ax.fill_between(grouped["日付"], caution_threshold, target_val_float, color='orange', alpha=0.15, label='注意ゾーン(目標未達)')
            except ValueError: print(f"Warning: Target value '{target_value}' for {title} not float.")

        font_kwargs = {'fontname': actual_font_name} if actual_font_name else {}
        ax.set_title(title, fontsize=11, **font_kwargs)
        ax.set_xlabel('日付', fontsize=9, **font_kwargs)
        ax.set_ylabel('患者数', fontsize=9, **font_kwargs)
        ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        legend_prop = {'size': 8}; legend_prop.update(font_kwargs)
        ax.legend(prop=legend_prop)
        fig.autofmt_xdate(rotation=30, ha='right')
        ax.tick_params(axis='x', labelsize=7)
        ax.tick_params(axis='y', labelsize=7)
        plt.tight_layout(pad=0.5)
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error in create_patient_chart_with_target_wrapper ('{title}'): {e}")
        return None
    finally:
        if fig: plt.close(fig)
        gc.collect()

def create_dual_axis_chart_for_pdf( # Renamed from create_mpl_dual_axis_chart to avoid confusion
    data, title="患者移動と在院数", days=90, font_name_for_mpl_to_use=None # Use a different name
):
    fig = None
    actual_font_name = font_name_for_mpl_to_use if font_name_for_mpl_to_use else MATPLOTLIB_FONT_NAME
    try:
        fig, ax1 = plt.subplots(figsize=(8, 4.0))
        if not isinstance(data, pd.DataFrame) or data.empty: return None
        required_columns = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "総退院患者数"] # Use 総退院患者数 for consistency
        if any(col not in data.columns for col in required_columns): return None

        data_copy = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)
        if data_copy.empty: return None

        agg_dict = {"入院患者数（在院）": "sum", "新入院患者数": "sum", "緊急入院患者数": "sum", "総退院患者数": "sum"}
        grouped = data_copy.groupby("日付").agg(agg_dict).reset_index().sort_values("日付")
        if len(grouped) > days: grouped = grouped.tail(days)
        if grouped.empty: return None

        cols_for_ma = ["入院患者数（在院）", "新入院患者数", "緊急入院患者数", "総退院患者数"]
        for col in cols_for_ma:
            if col in grouped.columns:
                grouped[f'{col}_7日MA'] = grouped[col].rolling(window=7, min_periods=1).mean()
            else:
                grouped[f'{col}_7日MA'] = 0 # Default if column missing

        font_kwargs = {'fontname': actual_font_name} if actual_font_name else {}
        if "入院患者数（在院）_7日MA" in grouped.columns:
            ax1.plot(grouped["日付"], grouped["入院患者数（在院）_7日MA"], color='#3498db', linewidth=2, label="在院患者数(7日MA)")
        ax1.set_xlabel('日付', fontsize=9, **font_kwargs)
        ax1.set_ylabel('在院患者数', fontsize=9, color='#3498db', **font_kwargs)
        ax1.tick_params(axis='y', labelcolor='#3498db', labelsize=8)
        ax1.tick_params(axis='x', labelsize=8, rotation=30, ha='right')

        ax2 = ax1.twinx()
        colors_map = {"新入院患者数": "#2ecc71", "緊急入院患者数": "#e74c3c", "総退院患者数": "#f39c12"}
        for col, color_val in colors_map.items():
            ma_col_name = f"{col}_7日MA"
            if ma_col_name in grouped.columns:
                ax2.plot(grouped["日付"], grouped[ma_col_name], color=color_val, linewidth=1.5, label=f"{col}(7日MA)")
        ax2.set_ylabel('患者移動数', fontsize=9, **font_kwargs)
        ax2.tick_params(axis='y', labelsize=8)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_prop = {'size': 8}; legend_prop.update(font_kwargs)
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_prop)
        plt.title(title, fontsize=11, **font_kwargs)
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        plt.tight_layout(pad=0.5)
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error in create_dual_axis_chart_for_pdf ('{title}'): {e}")
        return None
    finally:
        if fig: plt.close(fig)
        gc.collect()


# --- PDF生成メイン関数 ---
def create_pdf(
    forecast_df, df_weekday, df_holiday, df_all_avg=None,
    chart_data=None, # この引数は部門別テーブル生成に使用
    title_prefix="全体", latest_date=None,
    target_data=None, filter_code="全体", graph_days=None, # graph_daysは使用されなくなる
    alos_chart_buffers=None,        # Dict[str, bytes] days_str: bytes
    patient_chart_buffers=None,     # Dict[str, Dict[str, bytes]] type_key: {days_str: bytes}
    dual_axis_chart_buffers=None    # Dict[str, bytes] days_str: bytes
):
    pdf_start_time = time.time()
    elements = []
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=18*mm, bottomMargin=18*mm)
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Normal_JP', parent=styles['Normal'], fontName=REPORTLAB_FONT_NAME, fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='Heading1_JP', parent=styles['Heading1'], fontName=REPORTLAB_FONT_NAME, fontSize=14, spaceAfter=5*mm, leading=16))
    styles.add(ParagraphStyle(name='Heading2_JP', parent=styles['Heading2'], fontName=REPORTLAB_FONT_NAME, fontSize=11, spaceAfter=3*mm, leading=14))
    styles.add(ParagraphStyle(name='Normal_Center_JP', parent=styles['Normal_JP'], alignment=TA_CENTER, fontSize=7, leading=8))

    normal_ja = styles['Normal_JP']
    ja_style = styles['Heading1_JP']
    ja_heading2 = styles['Heading2_JP']
    para_style_normal_center = styles['Normal_Center_JP']

    current_latest_date = latest_date if latest_date else pd.Timestamp.now().normalize()
    if isinstance(current_latest_date, str): current_latest_date = pd.Timestamp(current_latest_date)
    data_date_str = current_latest_date.strftime("%Y年%m月%d日")
    today_str = pd.Timestamp.now().strftime("%Y年%m月%d日")
    
    report_title_text = f"入院患者数予測 - {title_prefix}（データ基準日: {data_date_str}）"
    elements.append(Paragraph(report_title_text, ja_style))
    elements.append(Spacer(1, 5*mm))
    page_width = A4[0] - doc.leftMargin - doc.rightMargin
    graphs_on_current_page = 0
    max_graphs_per_page = 2

    # ALOSグラフ (バッファから)
    if alos_chart_buffers:
        for days_val_str, chart_buffer_bytes in sorted(alos_chart_buffers.items(), key=lambda item: int(item[0])): #日数順
            if graphs_on_current_page >= max_graphs_per_page:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0
            if chart_buffer_bytes:
                img_buf = BytesIO(chart_buffer_bytes); img_buf.seek(0)
                elements.append(Paragraph(f"平均在院日数と平均在院患者数の推移（直近{days_val_str}日間）", ja_heading2))
                elements.append(Spacer(1, 1.5*mm)); elements.append(Image(img_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page += 1
        if graphs_on_current_page > 0: elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0

    # 患者数推移グラフ (バッファから)
    if patient_chart_buffers:
        type_name_map = {"all": "全日", "weekday": "平日", "holiday": "休日"}
        for chart_type_key in ["all", "weekday", "holiday"]: # 表示順序を固定
            day_buffers_dict = patient_chart_buffers.get(chart_type_key, {})
            if not day_buffers_dict: continue
            display_name = type_name_map.get(chart_type_key, chart_type_key.capitalize())
            for days_val_str, chart_buffer_bytes in sorted(day_buffers_dict.items(), key=lambda item: int(item[0])):
                if graphs_on_current_page >= max_graphs_per_page:
                    elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0
                if chart_buffer_bytes:
                    img_buf = BytesIO(chart_buffer_bytes); img_buf.seek(0)
                    elements.append(Paragraph(f"{display_name} 入院患者数推移（直近{days_val_str}日間）", ja_heading2))
                    elements.append(Spacer(1, 1.5*mm)); elements.append(Image(img_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page += 1
            if graphs_on_current_page > 0: elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0
            
    # 二軸グラフ (バッファから)
    if dual_axis_chart_buffers:
        for days_val_str, chart_buffer_bytes in sorted(dual_axis_chart_buffers.items(), key=lambda item: int(item[0])):
            if graphs_on_current_page >= max_graphs_per_page:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0
            if chart_buffer_bytes:
                img_buf = BytesIO(chart_buffer_bytes); img_buf.seek(0)
                elements.append(Paragraph(f"患者移動と在院数の推移（直近{days_val_str}日間）", ja_heading2))
                elements.append(Spacer(1, 1.5*mm)); elements.append(Image(img_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page += 1
        if graphs_on_current_page > 0: elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0

    # テーブル生成・追加 (既存のロジックを踏襲)
    common_table_style_cmds = [
        ('FONTNAME', (0,0), (-1,-1), REPORTLAB_FONT_NAME), ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,0), 'CENTER'), 
        ('ALIGN', (1,1), (-1,-1), 'RIGHT'), ('ALIGN', (0,1), (0,-1), 'LEFT'),   
        ('FONTSIZE', (0,0), (-1,0), 9), ('FONTSIZE', (0,1), (-1,-1), 8),   
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('LEFTPADDING', (0,0), (-1,-1), 2*mm), 
        ('RIGHTPADDING', (0,0), (-1,-1), 2*mm),
    ]
    if df_all_avg is not None and not df_all_avg.empty:
        elements.append(Paragraph("全日平均値（平日・休日含む）", ja_heading2))
        header = [df_all_avg.index.name if df_all_avg.index.name else "区分"] + df_all_avg.columns.tolist()
        table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x,(float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_all_avg.iterrows()]
        num_cols = len(header); col_widths = [page_width*0.2] + [(page_width*0.8)/(num_cols-1 if num_cols > 1 else 1)]*(num_cols-1)
        elements.append(Table(table_data, colWidths=col_widths, style=TableStyle(common_table_style_cmds + [('BACKGROUND', (0,0), (-1,0), colors.green)])))
        elements.append(Spacer(1, 4*mm))

    if forecast_df is not None and not forecast_df.empty:
        elements.append(Paragraph("在院患者数予測", ja_heading2))
        fc_df_mod = forecast_df.copy()
        if "年間平均人日（実績＋予測）" in fc_df_mod.columns: fc_df_mod.rename(columns={"年間平均人日（実績＋予測）": "年度予測"}, inplace=True)
        if "延べ予測人日" in fc_df_mod.columns: fc_df_mod.drop(columns=["延べ予測人日"], inplace=True)
        header = [fc_df_mod.index.name if fc_df_mod.index.name else "基準"] + fc_df_mod.columns.tolist()
        table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x,(float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in fc_df_mod.iterrows()]
        num_cols = len(header); col_widths_fc = [page_width*0.25] + [(page_width*0.75)/(num_cols-1 if num_cols > 1 else 1)]*(num_cols-1)
        elements.append(Table(table_data, colWidths=col_widths_fc, style=TableStyle(common_table_style_cmds + [('BACKGROUND', (0,0), (-1,0), colors.blue)])))
        elements.append(Spacer(1, 4*mm))
    
    elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm))

    if df_weekday is not None and not df_weekday.empty:
        elements.append(Paragraph("平日平均値", ja_heading2))
        header = [df_weekday.index.name if df_weekday.index.name else "区分"] + df_weekday.columns.tolist()
        table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x,(float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_weekday.iterrows()]
        num_cols = len(header); col_widths = [page_width*0.2] + [(page_width*0.8)/(num_cols-1 if num_cols > 1 else 1)]*(num_cols-1)
        elements.append(Table(table_data, colWidths=col_widths, style=TableStyle(common_table_style_cmds + [('BACKGROUND', (0,0), (-1,0), colors.teal)])))
        elements.append(Spacer(1, 4*mm))
    if df_holiday is not None and not df_holiday.empty:
        elements.append(Paragraph("休日平均値", ja_heading2))
        header = [df_holiday.index.name if df_holiday.index.name else "区分"] + df_holiday.columns.tolist()
        table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x,(float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_holiday.iterrows()]
        num_cols = len(header); col_widths = [page_width*0.2] + [(page_width*0.8)/(num_cols-1 if num_cols > 1 else 1)]*(num_cols-1)
        elements.append(Table(table_data, colWidths=col_widths, style=TableStyle(common_table_style_cmds + [('BACKGROUND', (0,0), (-1,0), colors.orange)])))
        elements.append(Spacer(1, 4*mm))

    # chart_data 引数は部門別テーブル生成に必要
    if chart_data is not None and not chart_data.empty:
        generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward = create_department_tables(
            chart_data, current_latest_date, target_data, filter_code, para_style_normal_center
        )
        dept_ward_common_style = [
            ('FONTNAME', (0,0), (-1,-1), REPORTLAB_FONT_NAME), ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTSIZE', (0,0), (-1,0), 8), ('FONTSIZE', (0,1), (-1,-1), 7), ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ]
        is_ward_pdf = "病棟別" in title_prefix; is_dept_pdf = "診療科別" in title_prefix
        if (is_ward_pdf and not is_dept_pdf) or (not is_ward_pdf and not is_dept_pdf) :
            if generated_ward_table_data and len(generated_ward_table_data) > 1:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm))
                elements.append(Paragraph("病棟別 入院患者数（在院）平均", ja_heading2))
                num_cols = len(generated_ward_table_data[0])
                period_count = len(period_labels_dept_ward) if period_labels_dept_ward else 0
                col_widths_ward = [page_width * 0.12] + [(page_width * 0.70) / period_count if period_count > 0 else 0] * period_count + [page_width * 0.09] * 2
                if num_cols != len(col_widths_ward) and num_cols > 0: col_widths_ward = [page_width/num_cols] * num_cols
                elements.append(Table(generated_ward_table_data, colWidths=col_widths_ward, style=TableStyle(dept_ward_common_style + [('BACKGROUND', (0,0), (-1,0), colors.lightgrey)])))
                elements.append(Spacer(1, 4*mm))
        if (is_dept_pdf and not is_ward_pdf) or (not is_ward_pdf and not is_dept_pdf) :
            if generated_dept_table_data and len(generated_dept_table_data) > 1:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm))
                elements.append(Paragraph("診療科別 入院患者数（在院）平均", ja_heading2))
                num_cols = len(generated_dept_table_data[0])
                period_count = len(period_labels_dept_ward) if period_labels_dept_ward else 0
                col_widths_dept = [page_width * 0.12] + [(page_width * 0.70) / period_count if period_count > 0 else 0] * period_count + [page_width * 0.09] * 2
                if num_cols != len(col_widths_dept) and num_cols > 0: col_widths_dept = [page_width/num_cols] * num_cols
                elements.append(Table(generated_dept_table_data, colWidths=col_widths_dept, style=TableStyle(dept_ward_common_style + [('BACKGROUND', (0,0), (-1,0), colors.lightcyan)])))
                elements.append(Spacer(1, 4*mm))

    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph(f"作成日時: {today_str}", normal_ja))
    doc.build(elements)
    buffer.seek(0)
    # print(f"PDF '{title_prefix}' generated in {time.time() - pdf_start_time:.2f} seconds.")
    gc.collect()
    return buffer

def create_landscape_pdf(
    forecast_df, df_weekday, df_holiday, df_all_avg=None,
    chart_data=None, # この引数は部門別テーブル生成に使用
    title_prefix="全体", latest_date=None,
    target_data=None, filter_code="全体", graph_days=None, # graph_daysは使用されなくなる
    alos_chart_buffers=None,        # Dict[str, bytes]
    patient_chart_buffers=None,     # Dict[str, Dict[str, bytes]]
    dual_axis_chart_buffers=None    # Dict[str, bytes]
):
    pdf_start_time = time.time()
    elements = []
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=12*mm, rightMargin=12*mm,
                            topMargin=12*mm, bottomMargin=12*mm)
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Normal_JP_Land', parent=styles['Normal'], fontName=REPORTLAB_FONT_NAME, fontSize=7.5, leading=9))
    styles.add(ParagraphStyle(name='Heading1_JP_Land', parent=styles['Heading1'], fontName=REPORTLAB_FONT_NAME, fontSize=13, spaceAfter=3*mm, leading=15))
    styles.add(ParagraphStyle(name='Heading2_JP_Land', parent=styles['Heading2'], fontName=REPORTLAB_FONT_NAME, fontSize=10, spaceAfter=2*mm, leading=12))
    styles.add(ParagraphStyle(name='Normal_Center_JP_Land', parent=styles['Normal_JP_Land'], alignment=TA_CENTER, fontSize=6.5, leading=8)) # For create_department_tables

    ja_style_land = styles['Heading1_JP_Land']
    ja_heading2_land = styles['Heading2_JP_Land']
    normal_ja_land = styles['Normal_JP_Land']
    para_style_normal_center_land = styles['Normal_Center_JP_Land']

    current_latest_date = latest_date if latest_date else pd.Timestamp.now().normalize()
    if isinstance(current_latest_date, str): current_latest_date = pd.Timestamp(current_latest_date)
    data_date_str = current_latest_date.strftime("%Y年%m月%d日")
    today_str = pd.Timestamp.now().strftime("%Y年%m月%d日")
    
    report_title_text = f"入院患者数予測 - {title_prefix}（データ基準日: {data_date_str}）"
    elements.append(Paragraph(report_title_text, ja_style_land))
    elements.append(Spacer(1, 3*mm))
    page_width_land, _ = landscape(A4)
    content_width_land = page_width_land - doc.leftMargin - doc.rightMargin
    graphs_on_current_page = 0
    max_graphs_per_page_land = 2

    # ALOSグラフ (バッファから)
    if alos_chart_buffers:
        for days_val_str, chart_buffer_bytes in sorted(alos_chart_buffers.items(), key=lambda item: int(item[0])):
            if graphs_on_current_page >= max_graphs_per_page_land:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page = 0
            if chart_buffer_bytes:
                img_buf = BytesIO(chart_buffer_bytes); img_buf.seek(0)
                elements.append(Paragraph(f"平均在院日数と平均在院患者数の推移（直近{days_val_str}日間）", ja_heading2_land))
                elements.append(Spacer(1, 1*mm)); elements.append(Image(img_buf, width=content_width_land*0.9, height=(content_width_land*0.9)*0.4)); elements.append(Spacer(1, 2*mm)); graphs_on_current_page += 1
        if graphs_on_current_page > 0: elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page = 0

    # 患者数推移グラフ (バッファから)
    if patient_chart_buffers:
        type_name_map = {"all": "全日", "weekday": "平日", "holiday": "休日"}
        for chart_type_key in ["all", "weekday", "holiday"]:
            day_buffers_dict = patient_chart_buffers.get(chart_type_key, {})
            if not day_buffers_dict: continue
            display_name = type_name_map.get(chart_type_key, chart_type_key.capitalize())
            for days_val_str, chart_buffer_bytes in sorted(day_buffers_dict.items(), key=lambda item: int(item[0])):
                if graphs_on_current_page >= max_graphs_per_page_land:
                    elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page = 0
                if chart_buffer_bytes:
                    img_buf = BytesIO(chart_buffer_bytes); img_buf.seek(0)
                    elements.append(Paragraph(f"{display_name} 入院患者数推移（直近{days_val_str}日間）", ja_heading2_land))
                    elements.append(Spacer(1, 1*mm)); elements.append(Image(img_buf, width=content_width_land*0.9, height=(content_width_land*0.9)*0.4)); elements.append(Spacer(1, 2*mm)); graphs_on_current_page += 1
            if graphs_on_current_page > 0: elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page = 0

    # 二軸グラフ (バッファから)
    if dual_axis_chart_buffers:
        for days_val_str, chart_buffer_bytes in sorted(dual_axis_chart_buffers.items(), key=lambda item: int(item[0])):
            if graphs_on_current_page >= max_graphs_per_page_land:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page = 0
            if chart_buffer_bytes:
                img_buf = BytesIO(chart_buffer_bytes); img_buf.seek(0)
                elements.append(Paragraph(f"患者移動と在院数の推移（直近{days_val_str}日間）", ja_heading2_land))
                elements.append(Spacer(1, 1*mm)); elements.append(Image(img_buf, width=content_width_land*0.9, height=(content_width_land*0.9)*0.4)); elements.append(Spacer(1, 2*mm)); graphs_on_current_page += 1
        if graphs_on_current_page > 0: elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page = 0

    # テーブル (横向き用に列幅や配置を調整)
    common_table_style_land_cmds = [
        ('FONTNAME', (0,0), (-1,-1), REPORTLAB_FONT_NAME),('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),('ALIGN', (0,0), (-1,0), 'CENTER'), 
        ('ALIGN', (1,1), (-1,-1), 'RIGHT'), ('ALIGN', (0,1), (0,-1), 'LEFT'),   
        ('FONTSIZE', (0,0), (-1,0), 8), ('FONTSIZE', (0,1), (-1,-1), 7.5),   
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('LEFTPADDING', (0,0), (-1,-1), 1.5*mm), 
        ('RIGHTPADDING', (0,0), (-1,-1), 1.5*mm),
    ]
    if df_all_avg is not None and not df_all_avg.empty:
        elements.append(Paragraph("全日平均値", ja_heading2_land))
        header = [df_all_avg.index.name if df_all_avg.index.name else "区分"] + df_all_avg.columns.tolist()
        table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x,(float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_all_avg.iterrows()]
        num_cols = len(header); col_widths = [content_width_land*0.15] + [(content_width_land*0.85)/(num_cols-1 if num_cols > 1 else 1)]*(num_cols-1)
        elements.append(Table(table_data, colWidths=col_widths, style=TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.green)])))
        elements.append(Spacer(1, 2*mm))

    if forecast_df is not None and not forecast_df.empty:
        elements.append(Paragraph("在院患者数予測", ja_heading2_land))
        fc_df_mod = forecast_df.copy()
        if "年間平均人日（実績＋予測）" in fc_df_mod.columns: fc_df_mod.rename(columns={"年間平均人日（実績＋予測）": "年度予測"}, inplace=True)
        if "延べ予測人日" in fc_df_mod.columns: fc_df_mod.drop(columns=["延べ予測人日"], inplace=True)
        header = [fc_df_mod.index.name if fc_df_mod.index.name else "基準"] + fc_df_mod.columns.tolist()
        table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x,(float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in fc_df_mod.iterrows()]
        num_cols = len(header); col_widths = [content_width_land*0.2] + [(content_width_land*0.8)/(num_cols-1 if num_cols > 1 else 1)]*(num_cols-1) # 基準列を少し広く
        elements.append(Table(table_data, colWidths=col_widths, style=TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.blue)])))
        elements.append(Spacer(1, 2*mm))

    elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm))
    left_col_elements, right_col_elements = [], []
    table_half_width = content_width_land * 0.48
    if df_weekday is not None and not df_weekday.empty:
        left_col_elements.append(Paragraph("平日平均値", ja_heading2_land))
        header = [df_weekday.index.name if df_weekday.index.name else "区分"] + df_weekday.columns.tolist()
        table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x,(float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_weekday.iterrows()]
        num_cols = len(header); col_widths = [table_half_width*0.25] + [(table_half_width*0.75)/(num_cols-1 if num_cols > 1 else 1)]*(num_cols-1)
        left_col_elements.append(Table(table_data, colWidths=col_widths, style=TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.teal)])))
    if df_holiday is not None and not df_holiday.empty:
        right_col_elements.append(Paragraph("休日平均値", ja_heading2_land))
        header = [df_holiday.index.name if df_holiday.index.name else "区分"] + df_holiday.columns.tolist()
        table_data = [header] + [[str(idx)] + [f"{x:.1f}" if isinstance(x,(float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_holiday.iterrows()]
        num_cols = len(header); col_widths = [table_half_width*0.25] + [(table_half_width*0.75)/(num_cols-1 if num_cols > 1 else 1)]*(num_cols-1)
        right_col_elements.append(Table(table_data, colWidths=col_widths, style=TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.orange)])))
    if left_col_elements or right_col_elements:
        elements.append(Table([[left_col_elements if left_col_elements else "", right_col_elements if right_col_elements else ""]], 
                                colWidths=[table_half_width, content_width_land - table_half_width - 2*mm]))
    elements.append(Spacer(1, 2*mm))

    if chart_data is not None and not chart_data.empty: #部門別テーブルはchart_dataが必要
        generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward = create_department_tables(
            chart_data, current_latest_date, target_data, filter_code, para_style_normal_center_land
        )
        dept_ward_style_land = [
            ('FONTNAME', (0,0), (-1,-1), REPORTLAB_FONT_NAME), ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTSIZE', (0,0), (-1,0), 7), ('FONTSIZE', (0,1), (-1,-1), 6.5), ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ]
        is_ward_pdf = "病棟別" in title_prefix; is_dept_pdf = "診療科別" in title_prefix
        if (is_ward_pdf and not is_dept_pdf) or (not is_ward_pdf and not is_dept_pdf) :
            if generated_ward_table_data and len(generated_ward_table_data) > 1:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm))
                elements.append(Paragraph("病棟別 入院患者数（在院）平均", ja_heading2_land))
                num_cols = len(generated_ward_table_data[0]); period_count = len(period_labels_dept_ward) if period_labels_dept_ward else 0
                col_widths_w = [content_width_land*0.10] + [(content_width_land*0.72)/period_count if period_count > 0 else 0]*period_count + [content_width_land*0.09]*2
                if num_cols != len(col_widths_w) and num_cols > 0: col_widths_w = [content_width_land/num_cols] * num_cols
                elements.append(Table(generated_ward_table_data, colWidths=col_widths_w, style=TableStyle(dept_ward_style_land + [('BACKGROUND', (0,0), (-1,0), colors.lightgrey)])))
                elements.append(Spacer(1, 2*mm))
        if (is_dept_pdf and not is_ward_pdf) or (not is_ward_pdf and not is_dept_pdf) :
            if generated_dept_table_data and len(generated_dept_table_data) > 1:
                if not (is_ward_pdf and elements[-1] != PageBreak()): # 病棟テーブルが同じページにない場合のみ改ページ
                     elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm))
                elements.append(Paragraph("診療科別 入院患者数（在院）平均", ja_heading2_land))
                num_cols = len(generated_dept_table_data[0]); period_count = len(period_labels_dept_ward) if period_labels_dept_ward else 0
                col_widths_d = [content_width_land*0.10] + [(content_width_land*0.72)/period_count if period_count > 0 else 0]*period_count + [content_width_land*0.09]*2
                if num_cols != len(col_widths_d) and num_cols > 0: col_widths_d = [content_width_land/num_cols] * num_cols
                elements.append(Table(generated_dept_table_data, colWidths=col_widths_d, style=TableStyle(dept_ward_style_land + [('BACKGROUND', (0,0), (-1,0), colors.lightcyan)])))
                elements.append(Spacer(1, 2*mm))

    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph(f"作成日時: {today_str}", normal_ja_land))
    doc.build(elements)
    buffer.seek(0)
    # print(f"Landscape PDF '{title_prefix}' generated in {time.time() - pdf_start_time:.2f} seconds.")
    gc.collect()
    return buffer

# --- 部門別テーブル生成関数 (これは変更なし) ---
def create_department_tables(chart_data, latest_date, target_data=None, filter_code=None, para_style=None):
    dept_tbl_start_time = time.time()
    if chart_data is None or chart_data.empty or latest_date is None:
        return [], [], []

    if not pd.api.types.is_datetime64_any_dtype(chart_data['日付']):
        try:
            chart_data['日付'] = pd.to_datetime(chart_data['日付'])
        except Exception:
            return [], [], [] # Should log this error
    if not isinstance(latest_date, pd.Timestamp):
        latest_date = pd.Timestamp(latest_date)

    current_year_start_month = 4
    if latest_date.month < current_year_start_month:
        current_fiscal_year_start = pd.Timestamp(year=latest_date.year - 1, month=current_year_start_month, day=1)
    else:
        current_fiscal_year_start = pd.Timestamp(year=latest_date.year, month=current_year_start_month, day=1)
    current_fiscal_year_end_for_data = latest_date
    previous_fiscal_year_start = current_fiscal_year_start - pd.DateOffset(years=1)
    previous_fiscal_year_end = current_fiscal_year_start - pd.Timedelta(days=1)

    period_definitions = {
        "直近7日": (latest_date - pd.Timedelta(days=6), latest_date),
        "直近14日": (latest_date - pd.Timedelta(days=13), latest_date),
        "直近30日": (latest_date - pd.Timedelta(days=29), latest_date),
        "直近60日": (latest_date - pd.Timedelta(days=59), latest_date),
        f"{current_fiscal_year_start.year}年度": (current_fiscal_year_start, current_fiscal_year_end_for_data),
        f"{previous_fiscal_year_start.year}年度": (previous_fiscal_year_start, previous_fiscal_year_end),
    }
    period_labels_for_data = list(period_definitions.keys())
    period_name_for_achievement = "直近30日"
    
    if para_style is None:
        styles = getSampleStyleSheet()
        font_name_to_use = REPORTLAB_FONT_NAME if REPORTLAB_FONT_NAME and pdfmetrics.getFont(REPORTLAB_FONT_NAME) else 'Helvetica'
        para_style = ParagraphStyle('ParaNormalCenterDefault_Dept', parent=styles['Normal'], fontName=font_name_to_use, fontSize=6.5, alignment=TA_CENTER, leading=7)

    period_labels_for_header = [Paragraph(label.replace("直近", "直近<br/>").replace("年度", "<br/>年度"), para_style) for label in period_labels_for_data]

    ward_codes_unique = sorted(chart_data["病棟コード"].astype(str).unique()) if "病棟コード" in chart_data.columns else []
    dept_names_original = sorted(chart_data["診療科名"].unique()) if "診療科名" in chart_data.columns else []
    
    show_all_depts = True 
    use_selected_depts = False
    selected_depts_list = []
    # Note: Accessing st.session_state here might be an issue if called from a non-Streamlit thread (e.g., worker)
    # This function should ideally not rely on st.session_state directly.
    # For batch processing, these parameters should be passed down or determined differently.
    # Assuming for now it's called in a context where st.session_state might be available or not critical.
    if 'st' in globals() and hasattr(st, 'session_state'):
        try:
            show_all_depts = st.session_state.get('show_all_depts', True)
            use_selected_depts = st.session_state.get('use_selected_depts', False)
            selected_depts_list = st.session_state.get('selected_depts', []) # This key seems to be missing in main app
        except Exception: # Catch errors if st.session_state is not available
            pass


    dept_names_to_process = dept_names_original
    if not show_all_depts: # This logic will likely not work as intended in worker
        if use_selected_depts and selected_depts_list:
            dept_names_to_process = [dept for dept in dept_names_original if dept in selected_depts_list]
    
    ward_display_names = {}
    for ward_code in ward_codes_unique:
        if target_data is not None and not target_data.empty and '部門コード' in target_data.columns and '部門名' in target_data.columns:
            target_row = target_data[target_data['部門コード'].astype(str) == ward_code]
            if not target_row.empty and pd.notna(target_row['部門名'].iloc[0]):
                ward_display_names[ward_code] = target_row['部門名'].iloc[0]
                continue
        match = re.match(r'0*(\d+)([A-Za-z]*)', ward_code)
        if match:
            num_part, alpha_part = match.group(1), match.group(2)
            ward_display_names[ward_code] = f"{num_part}{alpha_part}病棟"
        else: 
            ward_display_names[ward_code] = ward_code

    ward_metrics = {ward_code: {} for ward_code in ward_codes_unique}
    dept_metrics = {dept_name: {} for dept_name in dept_names_to_process}

    for period_label, (start_dt_period, end_dt_period) in period_definitions.items():
        if start_dt_period > end_dt_period: continue
        period_data_df = chart_data[(chart_data["日付"] >= start_dt_period) & (chart_data["日付"] <= end_dt_period)]
        if period_data_df.empty: continue
        num_days_in_period_calc = period_data_df['日付'].nunique()
        if num_days_in_period_calc == 0: continue
            
        for ward_code in ward_codes_unique:
            ward_data_df = period_data_df[period_data_df["病棟コード"].astype(str) == ward_code]
            if not ward_data_df.empty and '入院患者数（在院）' in ward_data_df.columns:
                total_patient_days_val = ward_data_df.groupby('日付')['入院患者数（在院）'].sum().sum() # Ensure this is correct aggregation
                avg_daily_census_val = total_patient_days_val / num_days_in_period_calc
                ward_metrics[ward_code][period_label] = avg_daily_census_val
            else:
                ward_metrics[ward_code][period_label] = np.nan # Use np.nan for missing data

        for dept_name in dept_names_to_process:
            dept_data_df = period_data_df[period_data_df["診療科名"] == dept_name]
            if not dept_data_df.empty and '入院患者数（在院）' in dept_data_df.columns:
                total_patient_days_val = dept_data_df.groupby('日付')['入院患者数（在院）'].sum().sum()
                avg_daily_census_val = total_patient_days_val / num_days_in_period_calc
                dept_metrics[dept_name][period_label] = avg_daily_census_val
            else:
                dept_metrics[dept_name][period_label] = np.nan
    
    target_dict_cache_local = {} # Local cache for this function call
    def get_targets_achievements(items, metrics_dict, target_data_df, achievement_period=period_name_for_achievement):
        targets = {}
        achievements = {}
        if target_data_df is not None and not target_data_df.empty and \
           all(col in target_data_df.columns for col in ['部門コード', '区分', '目標値']):
            target_data_df['部門コード'] = target_data_df['部門コード'].astype(str)
            
            # Use local cache
            if 'all_targets' not in target_dict_cache_local:
                all_targets_map_local = {}
                for _, row_val in target_data_df[target_data_df['区分'] == '全日'].iterrows():
                    if pd.notna(row_val.get('部門コード')) and pd.notna(row_val.get('目標値')):
                        all_targets_map_local[str(row_val['部門コード'])] = float(row_val['目標値'])
                target_dict_cache_local['all_targets'] = all_targets_map_local
            
            all_targets_map_local = target_dict_cache_local.get('all_targets', {})
            
            for item_id_val in items:
                item_id_str_val = str(item_id_val)
                target_value_val = all_targets_map_local.get(item_id_str_val)
                if target_value_val is not None:
                    targets[item_id_val] = target_value_val
                    actual_value_val = metrics_dict.get(item_id_val, {}).get(achievement_period) # metrics_dict can be {} for an item
                    if actual_value_val is not None and pd.notna(actual_value_val) and target_value_val > 0:
                        achievements[item_id_val] = (actual_value_val / target_value_val) * 100
        return targets, achievements

    ward_targets, ward_achievements = get_targets_achievements(ward_codes_unique, ward_metrics, target_data)
    dept_targets, dept_achievements = get_targets_achievements(dept_names_to_process, dept_metrics, target_data)
    
    def sort_entities(entities_list, achievements_ref_dict, targets_ref_dict):
        # Ensure entities are hashable if they are used as dict keys later
        entities_list_str = [str(e) for e in entities_list]
        achievements_ref_str = {str(k): v for k, v in achievements_ref_dict.items()}
        targets_ref_str = {str(k): v for k, v in targets_ref_dict.items()}

        sorted_by_achievement = sorted([e for e in entities_list_str if e in achievements_ref_str], key=lambda x: achievements_ref_str.get(x, 0), reverse=True)
        sorted_by_target_only = sorted([e for e in entities_list_str if e in targets_ref_str and e not in achievements_ref_str])
        sorted_by_no_target = sorted([e for e in entities_list_str if e not in targets_ref_str])
        return sorted_by_achievement + sorted_by_target_only + sorted_by_no_target

    sorted_ward_codes = sort_entities(ward_codes_unique, ward_achievements, ward_targets)
    sorted_dept_names = sort_entities(dept_names_to_process, dept_achievements, dept_targets)
    
    header_items = [Paragraph("部門", para_style)] + period_labels_for_header + [Paragraph("目標値", para_style), Paragraph("達成率<br/>(%)", para_style)]
    
    ward_table_data = [header_items]
    for ward_code_str in sorted_ward_codes:
        row_items = [Paragraph(ward_display_names.get(ward_code_str, ward_code_str), para_style)]
        for period_label_val in period_labels_for_data:
            val = ward_metrics.get(ward_code_str, {}).get(period_label_val)
            row_items.append(f"{val:.1f}" if pd.notna(val) else "-")
        row_items.append(f"{ward_targets.get(ward_code_str):.1f}" if ward_code_str in ward_targets else "-") # Use .get for safety
        row_items.append(f"{ward_achievements.get(ward_code_str):.1f}" if ward_code_str in ward_achievements else "-")
        ward_table_data.append(row_items)

    dept_table_data = [header_items]
    for dept_name_str in sorted_dept_names:
        row_items = [Paragraph(str(dept_name_str), para_style)] # Ensure dept_name is str
        for period_label_val in period_labels_for_data:
            val = dept_metrics.get(dept_name_str, {}).get(period_label_val)
            row_items.append(f"{val:.1f}" if pd.notna(val) else "-")
        row_items.append(f"{dept_targets.get(dept_name_str):.1f}" if dept_name_str in dept_targets else "-")
        row_items.append(f"{dept_achievements.get(dept_name_str):.1f}" if dept_name_str in dept_achievements else "-")
        dept_table_data.append(row_items)
    
    # print(f"Department tables for PDF generated in {time.time() - dept_tbl_start_time:.2f} seconds.")
    return ward_table_data, dept_table_data, period_labels_for_data