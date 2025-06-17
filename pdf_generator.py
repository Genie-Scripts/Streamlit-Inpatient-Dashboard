import pandas as pd
import streamlit as st
from io import BytesIO
import os
import re
import time
import hashlib
import gc
import numpy as np
from config import EXCLUDED_WARDS

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

import matplotlib.font_manager
import matplotlib.pyplot as plt
import matplotlib

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
                fname=FONT_PATH, name='NotoSansJP_MPL_PDFGEN'
            )
            if font_entry.name not in [f.name for f in matplotlib.font_manager.fontManager.ttflist]:
                 matplotlib.font_manager.fontManager.ttflist.insert(0, font_entry)

            MATPLOTLIB_FONT_NAME = font_entry.name
            print(f"Matplotlib font '{MATPLOTLIB_FONT_NAME}' prepared for use from {FONT_PATH}.")
            font_registered_mpl = True
        except Exception as e:
            print(f"Failed to prepare Matplotlib font '{FONT_PATH}' for pdf_generator: {e}")
            MATPLOTLIB_FONT_NAME = None
    else:
        print(f"Font file not found at '{FONT_PATH}'. Using fallback fonts for Matplotlib.")
        MATPLOTLIB_FONT_NAME = MATPLOTLIB_FONT_NAME_FALLBACK

    if not font_registered_rl:
        print(f"ReportLab will use its default font or Helvetica if '{REPORTLAB_FONT_NAME}' was intended as NotoSansJP.")

register_fonts()

# --- キャッシュ設定 ---
def get_chart_cache():
    if 'pdf_chart_cache' not in st.session_state:
        st.session_state.pdf_chart_cache = {}
    return st.session_state.pdf_chart_cache

def compute_data_hash(data):
    if data is None or data.empty: return "empty_data_hash"
    try:
        return hashlib.md5(pd.util.hash_pandas_object(data, index=True).values.tobytes()).hexdigest()
    except Exception: return hashlib.md5(str(time.time()).encode()).hexdigest()

def get_chart_cache_key(title, days, target_value=None, chart_type="default", data_hash=None):
    components = [str(title), str(days)]
    if target_value is not None:
        try: components.append(f"{float(target_value):.2f}")
        except (ValueError, TypeError): components.append(str(target_value))
    else: components.append("None")
    components.append(str(chart_type))
    if data_hash: components.append(data_hash)
    key_string = "_".join(components)
    return hashlib.md5(key_string.encode()).hexdigest()

# --- データフィルタリング関数（除外病棟対応） ---
def filter_excluded_wards(data):
    """除外病棟をフィルタリングする共通関数"""
    if data is None or data.empty:
        return data
    
    if '病棟コード' in data.columns and EXCLUDED_WARDS:
        original_count = len(data)
        filtered_data = data[~data['病棟コード'].isin(EXCLUDED_WARDS)]
        removed_count = original_count - len(filtered_data)
        if removed_count > 0:
            print(f"PDF生成: 除外病棟フィルタリングで{removed_count}件のレコードを除外")
        return filtered_data
    
    return data

# --- グラフ生成関数（修正版：目標値対応） ---
def create_alos_chart_for_pdf(
    chart_data, title_prefix="全体", latest_date=None,
    moving_avg_window=30, font_name_for_mpl_to_use=None,
    days_to_show=90
):
    start_time = time.time()
    fig = None
    actual_font_name = font_name_for_mpl_to_use or MATPLOTLIB_FONT_NAME or MATPLOTLIB_FONT_NAME_FALLBACK
    font_prop = matplotlib.font_manager.FontProperties(family=actual_font_name)

    # 除外病棟フィルタリング
    chart_data = filter_excluded_wards(chart_data)

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

        start_date_limit = current_latest_date - pd.Timedelta(days=days_to_show -1)
        date_range_for_plot = pd.date_range(start=start_date_limit, end=current_latest_date, freq='D')
        daily_metrics = []

        for display_date in date_range_for_plot:
            window_start = display_date - pd.Timedelta(days=moving_avg_window - 1)
            window_data = chart_data[(chart_data['日付'] >= window_start) & (chart_data['日付'] <= display_date)]
            if not window_data.empty:
                total_patient_days = window_data['入院患者数（在院）'].sum()
                total_admissions = window_data['総入院患者数'].sum()
                total_discharges = window_data['総退院患者数'].sum()
                num_days_in_window = window_data['日付'].nunique()
                denominator = (total_admissions + total_discharges) / 2
                alos = total_patient_days / denominator if denominator > 0 else np.nan
                daily_census = total_patient_days / num_days_in_window if num_days_in_window > 0 else np.nan
                daily_metrics.append({'日付': display_date, '平均在院日数': alos, '平均在院患者数': daily_census})

        if not daily_metrics: return None
        daily_df = pd.DataFrame(daily_metrics).sort_values('日付')
        if daily_df.empty: return None

        ax1.plot(daily_df['日付'], daily_df['平均在院日数'], color='#3498db', linewidth=2, marker='o', markersize=4, label=f"平均在院日数({moving_avg_window}日MA)")
        ax1.set_xlabel('日付', fontproperties=font_prop, fontsize=10)
        ax1.set_ylabel('平均在院日数', fontproperties=font_prop, fontsize=10, color='#3498db')
        ax1.tick_params(axis='y', labelcolor='#3498db', labelsize=8)
        ax1.tick_params(axis='x', labelsize=8, rotation=30)
        for label in ax1.get_xticklabels():
            label.set_fontproperties(font_prop)
            label.set_ha('right')

        ax2 = ax1.twinx()
        ax2.plot(daily_df['日付'], daily_df['平均在院患者数'], color='#e74c3c', linewidth=2, linestyle='--', label='平均在院患者数')
        ax2.set_ylabel('平均在院患者数', fontproperties=font_prop, fontsize=10, color='#e74c3c')
        ax2.tick_params(axis='y', labelcolor='#e74c3c', labelsize=8)
        for label in ax2.get_xticklabels(): label.set_fontproperties(font_prop)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_prop_obj = font_prop.copy()
        legend_prop_obj.set_size(8)
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_prop_obj)

        plt.title(f"{title_prefix} ALOSと在院患者数(直近{days_to_show}日)", fontproperties=font_prop, fontsize=12)
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        plt.tight_layout(pad=0.8)
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
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
    font_name_for_mpl_to_use=None
):
    fig = None
    actual_font_name = font_name_for_mpl_to_use or MATPLOTLIB_FONT_NAME or MATPLOTLIB_FONT_NAME_FALLBACK
    font_prop = matplotlib.font_manager.FontProperties(family=actual_font_name)
    
    # 除外病棟フィルタリング
    data = filter_excluded_wards(data)
    
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

        # 目標値ライン追加（修正版）
        if target_value is not None and pd.notna(target_value):
            try:
                target_val_float = float(target_value)
                if target_val_float > 0:  # 0より大きい場合のみ表示
                    print(f"PDF目標値ライン追加: {target_val_float} (グラフ: {title})")
                    ax.axhline(y=target_val_float, color='#9b59b6', linestyle='-.', linewidth=1.2, label=f'目標値: {target_val_float:.1f}')
                    caution_threshold = target_val_float * 0.97
                    ax.fill_between(grouped["日付"], caution_threshold, target_val_float, color='orange', alpha=0.15, label='注意ゾーン(目標未達)')
                else:
                    print(f"PDF: 目標値が0以下のためスキップ: {target_val_float}")
            except (ValueError, TypeError): 
                print(f"Warning: Target value '{target_value}' for {title} not convertible to float.")

        ax.set_title(title, fontproperties=font_prop, fontsize=11)
        ax.set_xlabel('日付', fontproperties=font_prop, fontsize=9)
        ax.set_ylabel('患者数', fontproperties=font_prop, fontsize=9)
        ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        legend_font_prop = font_prop.copy(); legend_font_prop.set_size(8)
        ax.legend(prop=legend_font_prop)
        ax.tick_params(axis='x', labelsize=7, rotation=30)
        for label in ax.get_xticklabels():
            label.set_fontproperties(font_prop)
            label.set_ha('right')
        ax.tick_params(axis='y', labelsize=7)
        for label in ax.get_yticklabels(): label.set_fontproperties(font_prop)

        plt.tight_layout(pad=0.5)
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error in create_patient_chart_with_target_wrapper ('{title}'): {e}")
        import traceback; print(traceback.format_exc())
        return None
    finally:
        if fig: plt.close(fig)
        gc.collect()

def create_dual_axis_chart_for_pdf(
    data, title="患者移動と在院数", days=90, font_name_for_mpl_to_use=None
):
    fig = None
    actual_font_name = font_name_for_mpl_to_use or MATPLOTLIB_FONT_NAME or MATPLOTLIB_FONT_NAME_FALLBACK
    font_prop = matplotlib.font_manager.FontProperties(family=actual_font_name)
    
    # 除外病棟フィルタリング
    data = filter_excluded_wards(data)
    
    try:
        fig, ax1 = plt.subplots(figsize=(8, 4.0))
        if not isinstance(data, pd.DataFrame) or data.empty: return None
        required_cols = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "総退院患者数"]
        if any(col not in data.columns for col in required_cols): return None

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
            if col in grouped.columns: grouped[f'{col}_7日MA'] = grouped[col].rolling(window=7, min_periods=1).mean()
            else: grouped[f'{col}_7日MA'] = 0

        if "入院患者数（在院）_7日MA" in grouped.columns:
            ax1.plot(grouped["日付"], grouped["入院患者数（在院）_7日MA"], color='#3498db', linewidth=2, label="在院患者数(7日MA)")
        ax1.set_xlabel('日付', fontproperties=font_prop, fontsize=9)
        ax1.set_ylabel('在院患者数', fontproperties=font_prop, fontsize=9, color='#3498db')
        ax1.tick_params(axis='y', labelcolor='#3498db', labelsize=8)
        ax1.tick_params(axis='x', labelsize=8, rotation=30)
        for label in ax1.get_xticklabels():
            label.set_fontproperties(font_prop)
            label.set_ha('right')

        ax2 = ax1.twinx()
        colors_map = {"新入院患者数": "#2ecc71", "緊急入院患者数": "#e74c3c", "総退院患者数": "#f39c12"}
        for col, color_val in colors_map.items():
            ma_col_name = f"{col}_7日MA"
            if ma_col_name in grouped.columns:
                ax2.plot(grouped["日付"], grouped[ma_col_name], color=color_val, linewidth=1.5, label=f"{col}(7日MA)")
        ax2.set_ylabel('患者移動数', fontproperties=font_prop, fontsize=9)
        ax2.tick_params(axis='y', labelsize=8)
        for label in ax2.get_yticklabels(): label.set_fontproperties(font_prop)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_font_prop = font_prop.copy(); legend_font_prop.set_size(8)
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_font_prop)

        plt.title(title, fontproperties=font_prop, fontsize=11)
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        plt.tight_layout(pad=0.5)
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error in create_dual_axis_chart_for_pdf ('{title}'): {e}")
        import traceback; print(traceback.format_exc())
        return None
    finally:
        if fig: plt.close(fig)
        gc.collect()

# --- 目標値取得関数（強化版） ---
def get_target_values_for_pdf(target_data, filter_code="全体", metric_name="日平均在院患者数"):
    """PDF生成用の目標値を取得する関数（強化版）"""
    target_values = {
        'all': None,
        'weekday': None, 
        'holiday': None
    }
    
    if target_data is None or target_data.empty:
        print(f"目標値データが空です。filter_code: {filter_code}")
        return target_values
    
    try:
        print(f"目標値検索開始 - filter_code: {filter_code}, metric: {metric_name}")
        print(f"目標データ列: {list(target_data.columns)}")
        
        # 目標値辞書の構築（複数の列名パターンに対応）
        target_dict = {}
        period_col_candidates = ['区分', '期間区分', '期間', '分類']
        indicator_col_candidates = ['指標タイプ', '指標名', '指標', 'メトリクス']
        
        period_col_name = None
        indicator_col_name = None
        
        # 期間列の特定
        for col in period_col_candidates:
            if col in target_data.columns:
                period_col_name = col
                break
        
        # 指標列の特定
        for col in indicator_col_candidates:
            if col in target_data.columns:
                indicator_col_name = col
                break
        
        # 基本的な列の存在確認
        required_cols = ['部門コード', '目標値']
        if not all(col in target_data.columns for col in required_cols):
            print(f"必要な列が不足: {required_cols}")
            return target_values
        
        # 目標値辞書の構築
        for _, row in target_data.iterrows():
            dept_code = str(row['部門コード']).strip()
            target_val = row['目標値']
            
            if pd.notna(target_val):
                # 期間情報の取得
                period = '全日'  # デフォルト
                if period_col_name and pd.notna(row[period_col_name]):
                    period = str(row[period_col_name]).strip()
                
                # 指標情報の取得
                indicator = metric_name  # デフォルト
                if indicator_col_name and pd.notna(row[indicator_col_name]):
                    indicator = str(row[indicator_col_name]).strip()
                
                key = (dept_code, indicator, period)
                target_dict[key] = target_val
                print(f"目標値登録: {key} = {target_val}")
        
        print(f"構築された目標値辞書: {len(target_dict)}件")
        
        # 目標値の検索（拡張版）
        if target_dict:
            search_codes = []
            
            if filter_code == "全体":
                search_codes = ["000", "全体", "病院全体", "総合"]
            else:
                search_codes = [str(filter_code)]
            
            # 各期間での検索
            for period_type, period_names in [('all', ['全日', '全て']), 
                                            ('weekday', ['平日']), 
                                            ('holiday', ['休日', '祝日'])]:
                
                for search_code in search_codes:
                    for period_name in period_names:
                        # 指標名での検索
                        for indicator in [metric_name, "日平均在院患者数", "在院患者数", "患者数"]:
                            key = (search_code, indicator, period_name)
                            if key in target_dict:
                                try:
                                    target_values[period_type] = float(target_dict[key])
                                    print(f"目標値発見: {key} = {target_values[period_type]}")
                                    break
                                except (ValueError, TypeError):
                                    continue
                        
                        if target_values[period_type] is not None:
                            break
                    
                    if target_values[period_type] is not None:
                        break
        
        # 結果のログ出力
        for period_type, value in target_values.items():
            if value is not None:
                print(f"最終目標値 ({period_type}): {value}")
            else:
                print(f"目標値未発見 ({period_type})")
                    
    except Exception as e:
        print(f"目標値取得エラー: {e}")
        import traceback
        print(traceback.format_exc())
    
    return target_values

# --- 修正されたPDF生成関数 ---
def create_pdf(
    forecast_df, df_weekday, df_holiday, df_all_avg=None,
    chart_data=None, title_prefix="全体", latest_date=None,
    target_data=None, filter_code="全体", graph_days=None,
    alos_chart_buffers=None,
    patient_chart_buffers=None,
    dual_axis_chart_buffers=None
):
    """
    修正版PDF生成関数：除外病棟フィルタリングと目標値対応
    """
    # ===== 除外病棟の厳密チェック =====
    if chart_data is not None and not chart_data.empty and '病棟コード' in chart_data.columns:
        # 除外病棟フィルタリング
        original_count = len(chart_data)
        chart_data = filter_excluded_wards(chart_data)
        filtered_count = len(chart_data)
        
        # 除外病棟のチェック（フィルタ後も確認）
        ward_codes = chart_data['病棟コード'].astype(str).unique()
        excluded_found = [ward for ward in ward_codes if ward in EXCLUDED_WARDS]
        if excluded_found:
            print(f"PDF生成スキップ: 除外病棟 {excluded_found} が残存しています")
            return None
        
        # 除外病棟の検出をタイトルからも確認
        if "病棟別" in title_prefix:
            import re
            # タイトルから病棟コードを抽出
            match = re.search(r'(\d+[A-Za-z]*?)病棟', title_prefix)
            if match:
                ward_code_from_title = match.group(1)
                # 先頭ゼロ埋めバージョンもチェック
                ward_variants = [ward_code_from_title, f"0{ward_code_from_title}", f"00{ward_code_from_title}"]
                for variant in ward_variants:
                    if variant in EXCLUDED_WARDS:
                        print(f"PDF生成スキップ: タイトルから除外病棟 {variant} を検出")
                        return None
        
        if original_count > filtered_count:
            print(f"除外病棟フィルタリング: {original_count - filtered_count}件除外")
    
    # ===== 目標値取得（強化版） =====
    target_values = get_target_values_for_pdf(target_data, filter_code)
    print(f"取得した目標値: {target_values}")
    
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

    # ALOSグラフ（バッファまたは動的生成）
    if alos_chart_buffers:
        for days_val_str, chart_buffer_bytes in sorted(alos_chart_buffers.items(), key=lambda item: int(item[0])):
            if graphs_on_current_page >= max_graphs_per_page:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0
            if chart_buffer_bytes:
                img_buf = BytesIO(chart_buffer_bytes); img_buf.seek(0)
                elements.append(Paragraph(f"平均在院日数と平均在院患者数の推移（直近{days_val_str}日間）", ja_heading2))
                elements.append(Spacer(1, 1.5*mm)); elements.append(Image(img_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page += 1
    elif chart_data is not None:
        # バッファがない場合は動的生成
        for days_val in [90, 180]:
            if graphs_on_current_page >= max_graphs_per_page:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0
            
            chart_buf = create_alos_chart_for_pdf(chart_data, title_prefix, current_latest_date, days_to_show=days_val)
            if chart_buf:
                elements.append(Paragraph(f"平均在院日数と平均在院患者数の推移（直近{days_val}日間）", ja_heading2))
                elements.append(Spacer(1, 1.5*mm)); elements.append(Image(chart_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page += 1

    if graphs_on_current_page > 0 and (patient_chart_buffers or chart_data is not None):
        elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0

    # 患者数推移グラフ（目標値対応）
    if patient_chart_buffers:
        # バッファ使用
        type_name_map = {"all": "全日", "weekday": "平日", "holiday": "休日"}
        for chart_type_key in ["all", "weekday", "holiday"]:
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
    elif chart_data is not None:
        # バッファがない場合は動的生成（目標値付き）
        chart_configs = [
            ("all", "全日", chart_data, target_values['all']),
            ("weekday", "平日", chart_data[chart_data.get("平日判定", "") == "平日"] if "平日判定" in chart_data.columns else pd.DataFrame(), target_values['weekday']),
            ("holiday", "休日", chart_data[chart_data.get("平日判定", "") == "休日"] if "平日判定" in chart_data.columns else pd.DataFrame(), target_values['holiday'])
        ]
        
        for chart_type, display_name, data_subset, target_val in chart_configs:
            if data_subset.empty: continue
            for days_val in [90, 180]:
                if graphs_on_current_page >= max_graphs_per_page:
                    elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0
                
                chart_buf = create_patient_chart_with_target_wrapper(
                    data_subset, 
                    title=f"{title_prefix} {display_name}",
                    days=days_val,
                    target_value=target_val,
                    show_moving_average=(chart_type == "all")
                )
                if chart_buf:
                    elements.append(Paragraph(f"{display_name} 入院患者数推移（直近{days_val}日間）", ja_heading2))
                    elements.append(Spacer(1, 1.5*mm)); elements.append(Image(chart_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page += 1

    if graphs_on_current_page > 0 and (dual_axis_chart_buffers or chart_data is not None):
        elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0

    # 二軸グラフ
    if dual_axis_chart_buffers:
        for days_val_str, chart_buffer_bytes in sorted(dual_axis_chart_buffers.items(), key=lambda item: int(item[0])):
            if graphs_on_current_page >= max_graphs_per_page:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0
            if chart_buffer_bytes:
                img_buf = BytesIO(chart_buffer_bytes); img_buf.seek(0)
                elements.append(Paragraph(f"患者移動と在院数の推移（直近{days_val_str}日間）", ja_heading2))
                elements.append(Spacer(1, 1.5*mm)); elements.append(Image(img_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page += 1
    elif chart_data is not None:
        # バッファがない場合は動的生成
        for days_val in [90, 180]:
            if graphs_on_current_page >= max_graphs_per_page:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0
            
            chart_buf = create_dual_axis_chart_for_pdf(chart_data, f"{title_prefix} 患者移動", days_val)
            if chart_buf:
                elements.append(Paragraph(f"患者移動と在院数の推移（直近{days_val}日間）", ja_heading2))
                elements.append(Spacer(1, 1.5*mm)); elements.append(Image(chart_buf, width=page_width*0.9, height=(page_width*0.9)*0.45)); elements.append(Spacer(1, 3*mm)); graphs_on_current_page += 1

    if graphs_on_current_page > 0:
        elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm)); graphs_on_current_page = 0

    # テーブル生成（既存のロジック）
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
    gc.collect()
    return buffer

def create_landscape_pdf(
    forecast_df, df_weekday, df_holiday, df_all_avg=None,
    chart_data=None, title_prefix="全体", latest_date=None,
    target_data=None, filter_code="全体", graph_days=None,
    alos_chart_buffers=None,
    patient_chart_buffers=None,
    dual_axis_chart_buffers=None
):
    """
    横向き(Landscape)のPDFを生成する関数。create_pdfをベースにページサイズを変更。
    """
    # ===== 除外病棟の厳密チェック =====
    if chart_data is not None and not chart_data.empty and '病棟コード' in chart_data.columns:
        original_count = len(chart_data)
        chart_data = filter_excluded_wards(chart_data)
        filtered_count = len(chart_data)
        ward_codes = chart_data['病棟コード'].astype(str).unique()
        excluded_found = [ward for ward in ward_codes if ward in EXCLUDED_WARDS]
        if excluded_found:
            print(f"PDF生成スキップ: 除外病棟 {excluded_found} が残存しています")
            return None
        if "病棟別" in title_prefix:
            import re
            match = re.search(r'(\d+[A-Za-z]*?)病棟', title_prefix)
            if match:
                ward_code_from_title = match.group(1)
                ward_variants = [ward_code_from_title, f"0{ward_code_from_title}", f"00{ward_code_from_title}"]
                for variant in ward_variants:
                    if variant in EXCLUDED_WARDS:
                        print(f"PDF生成スキップ: タイトルから除外病棟 {variant} を検出")
                        return None
        if original_count > filtered_count:
            print(f"除外病棟フィルタリング: {original_count - filtered_count}件除外")
    
    # ===== 目標値取得（強化版） =====
    target_values = get_target_values_for_pdf(target_data, filter_code)
    
    elements = []
    buffer = BytesIO()
    # ▼▼▼ ページサイズを landscape(A4) に変更 ▼▼▼
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)

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
    
    # ▼▼▼ 横向きのページ幅に調整 ▼▼▼
    page_width = landscape(A4)[0] - doc.leftMargin - doc.rightMargin
    
    # グラフとテーブルの配置（create_pdfと共通のロジック）
    # グラフとテーブルは2列に分割して配置すると見やすい
    col_width = page_width / 2.2 # 少しマージンを設ける

    # グラフセクション
    graph_elements = []
    if alos_chart_buffers and alos_chart_buffers.get('90'):
        img_buf = BytesIO(alos_chart_buffers['90']); img_buf.seek(0)
        img = Image(img_buf, width=col_width, height=col_width*0.5)
        graph_elements.append(img)
    
    if dual_axis_chart_buffers and dual_axis_chart_buffers.get('90'):
        img_buf = BytesIO(dual_axis_chart_buffers['90']); img_buf.seek(0)
        img = Image(img_buf, width=col_width, height=col_width*0.5)
        graph_elements.append(img)
        
    if patient_chart_buffers and patient_chart_buffers.get('all', {}).get('90'):
        img_buf = BytesIO(patient_chart_buffers['all']['90']); img_buf.seek(0)
        img = Image(img_buf, width=col_width, height=col_width*0.5)
        graph_elements.append(img)
    
    # テーブルセクション
    table_elements = []
    common_table_style_cmds = [
        ('FONTNAME', (0,0), (-1,-1), REPORTLAB_FONT_NAME), ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('ALIGN', (1,1), (-1,-1), 'RIGHT'), ('ALIGN', (0,1), (0,-1), 'LEFT'),
        ('FONTSIZE', (0,0), (-1,0), 8), ('FONTSIZE', (0,1), (-1,-1), 7),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('LEFTPADDING', (0,0), (-1,-1), 2*mm),
        ('RIGHTPADDING', (0,0), (-1,-1), 2*mm),
    ]

    # 予測テーブル
    if forecast_df is not None and not forecast_df.empty:
        fc_df_mod = forecast_df.copy()
        if "年間平均人日（実績＋予測）" in fc_df_mod.columns: fc_df_mod.rename(columns={"年間平均人日（実績＋予測）": "年度予測"}, inplace=True)
        if "延べ予測人日" in fc_df_mod.columns: fc_df_mod.drop(columns=["延べ予測人日"], inplace=True)
        header = [fc_df_mod.index.name or "基準"] + fc_df_mod.columns.tolist()
        table_data = [header] + [[str(idx)] + [f"{x:.1f}" if pd.notna(x) else "-" for x in row] for idx, row in fc_df_mod.iterrows()]
        num_cols = len(header)
        col_widths = [col_width*0.25] + [(col_width*0.75)/(num_cols-1 or 1)]*(num_cols-1)
        tbl = Table(table_data, colWidths=col_widths, style=TableStyle(common_table_style_cmds + [('BACKGROUND', (0,0), (-1,0), colors.blue)]))
        table_elements.extend([Paragraph("在院患者数予測", ja_heading2), tbl, Spacer(1, 2*mm)])

    # 平均値テーブル
    if df_all_avg is not None and not df_all_avg.empty:
        header = [df_all_avg.index.name or "区分"] + df_all_avg.columns.tolist()
        table_data = [header] + [[str(idx)] + [f"{x:.1f}" if pd.notna(x) else "-" for x in row] for idx, row in df_all_avg.iterrows()]
        num_cols = len(header)
        col_widths = [col_width*0.2] + [(col_width*0.8)/(num_cols-1 or 1)]*(num_cols-1)
        tbl = Table(table_data, colWidths=col_widths, style=TableStyle(common_table_style_cmds + [('BACKGROUND', (0,0), (-1,0), colors.green)]))
        table_elements.extend([Paragraph("全日平均値", ja_heading2), tbl, Spacer(1, 2*mm)])

    # 2列レイアウトで要素を配置
    layout_table = Table([[graph_elements, table_elements]], colWidths=[col_width, col_width])
    layout_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
    elements.append(layout_table)
    
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(f"作成日時: {today_str}", normal_ja))
    
    doc.build(elements)
    buffer.seek(0)
    gc.collect()
    return buffer

def create_department_tables(chart_data, latest_date, target_data=None, filter_code=None, para_style=None):
    """修正版部門別テーブル生成関数：除外病棟対応"""
    dept_tbl_start_time = time.time()
    if chart_data is None or chart_data.empty or latest_date is None:
        return [], [], []

    # 除外病棟フィルタリング
    chart_data_filtered = filter_excluded_wards(chart_data)
    
    if chart_data_filtered.empty:
        print("除外病棟フィルタリング後、データが空になりました")
        return [], [], []
    
    # 既存の処理（chart_data_filteredを使用）
    if not pd.api.types.is_datetime64_any_dtype(chart_data_filtered['日付']):
        try: chart_data_filtered['日付'] = pd.to_datetime(chart_data_filtered['日付'])
        except Exception: return [], [], []
    if not isinstance(latest_date, pd.Timestamp): latest_date = pd.Timestamp(latest_date)

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

    ward_codes_unique = sorted(chart_data_filtered["病棟コード"].astype(str).unique()) if "病棟コード" in chart_data_filtered.columns else []
    # 除外病棟を再度フィルタリング（念のため）
    if EXCLUDED_WARDS:
        ward_codes_unique = [ward for ward in ward_codes_unique if ward not in EXCLUDED_WARDS]
    dept_names_original = sorted(chart_data_filtered["診療科名"].unique()) if "診療科名" in chart_data_filtered.columns else []
    
    dept_names_to_process = dept_names_original
    
    ward_display_names = {}
    for ward_code in ward_codes_unique:
        if target_data is not None and not target_data.empty and '部門コード' in target_data.columns and '部門名' in target_data.columns:
            target_row = target_data[target_data['部門コード'].astype(str) == ward_code]
            if not target_row.empty and pd.notna(target_row['部門名'].iloc[0]):
                ward_display_names[ward_code] = target_row['部門名'].iloc[0]; continue
        match = re.match(r'0*(\d+)([A-Za-z]*)', ward_code)
        if match: ward_display_names[ward_code] = f"{match.group(1)}{match.group(2)}病棟"
        else: ward_display_names[ward_code] = ward_code

    ward_metrics = {ward_code: {} for ward_code in ward_codes_unique}
    dept_metrics = {dept_name: {} for dept_name in dept_names_to_process}

    for period_label, (start_dt_period, end_dt_period) in period_definitions.items():
        if start_dt_period > end_dt_period: continue
        period_data_df = chart_data_filtered[(chart_data_filtered["日付"] >= start_dt_period) & (chart_data_filtered["日付"] <= end_dt_period)]
        if period_data_df.empty: continue
        num_days_in_period_calc = period_data_df['日付'].nunique()
        if num_days_in_period_calc == 0: continue
            
        for ward_code in ward_codes_unique:
            ward_data_df = period_data_df[period_data_df["病棟コード"].astype(str) == ward_code]
            if not ward_data_df.empty and '入院患者数（在院）' in ward_data_df.columns:
                total_patient_days_val = ward_data_df.groupby('日付')['入院患者数（在院）'].sum().sum()
                avg_daily_census_val = total_patient_days_val / num_days_in_period_calc if num_days_in_period_calc > 0 else np.nan
                ward_metrics[ward_code][period_label] = avg_daily_census_val
            else: ward_metrics[ward_code][period_label] = np.nan

        for dept_name in dept_names_to_process:
            dept_data_df = period_data_df[period_data_df["診療科名"] == dept_name]
            if not dept_data_df.empty and '入院患者数（在院）' in dept_data_df.columns:
                total_patient_days_val = dept_data_df.groupby('日付')['入院患者数（在院）'].sum().sum()
                avg_daily_census_val = total_patient_days_val / num_days_in_period_calc if num_days_in_period_calc > 0 else np.nan
                dept_metrics[dept_name][period_label] = avg_daily_census_val
            else: dept_metrics[dept_name][period_label] = np.nan
    
    target_dict_cache_local = {}
    def get_targets_achievements(items, metrics_dict, target_data_df, achievement_period=period_name_for_achievement):
        targets = {}; achievements = {}
        if target_data_df is not None and not target_data_df.empty and all(col in target_data_df.columns for col in ['部門コード', '区分', '目標値']):
            target_data_df['部門コード'] = target_data_df['部門コード'].astype(str)
            if 'all_targets' not in target_dict_cache_local:
                all_targets_map_local = {str(row['部門コード']): float(row['目標値']) for _, row in target_data_df[target_data_df['区分'] == '全日'].iterrows() if pd.notna(row.get('部門コード')) and pd.notna(row.get('目標値'))}
                target_dict_cache_local['all_targets'] = all_targets_map_local
            all_targets_map_local = target_dict_cache_local.get('all_targets', {})
            for item_id_val in items:
                item_id_str_val = str(item_id_val)
                target_value_val = all_targets_map_local.get(item_id_str_val)
                if target_value_val is not None:
                    targets[item_id_val] = target_value_val
                    actual_value_val = metrics_dict.get(item_id_val, {}).get(achievement_period)
                    if actual_value_val is not None and pd.notna(actual_value_val) and target_value_val > 0:
                        achievements[item_id_val] = (actual_value_val / target_value_val) * 100
        return targets, achievements

    ward_targets, ward_achievements = get_targets_achievements(ward_codes_unique, ward_metrics, target_data)
    dept_targets, dept_achievements = get_targets_achievements(dept_names_to_process, dept_metrics, target_data)
    
    def sort_entities(entities_list, achievements_ref_dict, targets_ref_dict):
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
        for period_label_val in period_labels_for_data: val = ward_metrics.get(ward_code_str, {}).get(period_label_val); row_items.append(f"{val:.1f}" if pd.notna(val) else "-")
        row_items.append(f"{ward_targets.get(ward_code_str):.1f}" if ward_code_str in ward_targets else "-")
        row_items.append(f"{ward_achievements.get(ward_code_str):.1f}" if ward_code_str in ward_achievements else "-")
        ward_table_data.append(row_items)
    dept_table_data = [header_items]
    for dept_name_str in sorted_dept_names:
        row_items = [Paragraph(str(dept_name_str), para_style)]
        for period_label_val in period_labels_for_data: val = dept_metrics.get(dept_name_str, {}).get(period_label_val); row_items.append(f"{val:.1f}" if pd.notna(val) else "-")
        row_items.append(f"{dept_targets.get(dept_name_str):.1f}" if dept_name_str in dept_targets else "-")
        row_items.append(f"{dept_achievements.get(dept_name_str):.1f}" if dept_name_str in dept_achievements else "-")
        dept_table_data.append(row_items)
    return ward_table_data, dept_table_data, period_labels_for_data