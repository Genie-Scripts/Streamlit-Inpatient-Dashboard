import pandas as pd
import streamlit as st # Only for type hints or if st.session_state is used in main process
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

import matplotlib.font_manager
import matplotlib.pyplot as plt
import matplotlib

# --- フォント設定 ---
FONT_DIR = 'fonts'
FONT_FILENAME = 'NotoSansJP-Regular.ttf'
FONT_PATH = os.path.join(FONT_DIR, FONT_FILENAME)
REPORTLAB_FONT_NAME = 'NotoSansJP_RL'
MATPLOTLIB_FONT_NAME_FALLBACK = 'sans-serif'
MATPLOTLIB_FONT_NAME = None # register_fonts で設定される

# 🚀 PDF生成最適化設定を追加
PDF_COMPRESSION_LEVEL = 6  # 圧縮レベル (1-9)
PDF_RENDER_DPI = 120      # DPI設定 (高品質かつ軽量)
MATPLOTLIB_DPI = 120      # Matplotlibの解像度

# ReportLabの最適化設定
def optimize_pdf_settings():
    """PDFレンダリングの最適化設定"""
    # ReportLabの内部設定を最適化
    os.environ['REPORTLAB_OPTIMIZE'] = '1'
    
    # メモリ効率の改善
    try:
        import reportlab.lib.styles
        reportlab.lib.styles._baseFontName = 'Helvetica'  # フォールバック最適化
    except:
        pass

# Matplotlibの最適化設定
def optimize_matplotlib_for_pdf():
    """Matplotlib設定の最適化"""
    import matplotlib
    matplotlib.use('Agg')  # GUI不要のバックエンド
    
    import matplotlib.pyplot as plt
    
    # メモリ効率の改善
    plt.ioff()  # インタラクティブモードをオフ
    
    # デフォルト設定の最適化
    plt.rcParams.update({
        'figure.max_open_warning': 0,  # 警告を無効化
        'savefig.format': 'png',
        'savefig.dpi': MATPLOTLIB_DPI,
        'savefig.bbox': 'tight',
        'savefig.facecolor': 'white',
        'font.size': 8,  # フォントサイズを小さく
        'axes.titlesize': 10,
        'axes.labelsize': 8,
        'xtick.labelsize': 7,
        'ytick.labelsize': 7,
        'legend.fontsize': 7
    })

# 🚀 最適化設定を初期化時に適用
optimize_pdf_settings()
optimize_matplotlib_for_pdf()

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
            MATPLOTLIB_FONT_NAME = None # フォールバック設定は後段に任せる
    else:
        print(f"Font file not found at '{FONT_PATH}'. Using fallback fonts for Matplotlib.")
        # MATPLOTLIB_FONT_NAME はこの時点では設定せず、後段でフォールバックさせる
    
    if not MATPLOTLIB_FONT_NAME: # Matplotlibフォントが設定されなかった場合
        MATPLOTLIB_FONT_NAME = MATPLOTLIB_FONT_NAME_FALLBACK
        print(f"Using fallback Matplotlib font: {MATPLOTLIB_FONT_NAME}")


    if not font_registered_rl:
        print(f"ReportLab will use its default font or Helvetica if '{REPORTLAB_FONT_NAME}' was intended as NotoSansJP.")
    
    # 🚀 フォント登録後にMatplotlib最適化を再適用
    optimize_matplotlib_for_pdf()
    
register_fonts() # モジュールインポート時にフォント登録

# --- キャッシュ設定 (メインプロセスでのみ使用される想定) ---
def get_chart_cache():
    # Streamlitのst.session_stateにアクセスする可能性のあるコードは、
    # メインプロセス以外 (multiprocessingのワーカーなど) から呼び出されるとエラーになるため注意が必要
    # この関数はbatch_processor.pyのメインプロセス側でのみ使用されることを想定
    if 'st' in globals() and hasattr(st, 'session_state'):
        if 'pdf_chart_cache' not in st.session_state:
            st.session_state.pdf_chart_cache = {}
        return st.session_state.pdf_chart_cache
    else:
        # Streamlit環境外（例: ワーカープロセス）で呼び出された場合のフォールバック
        # print("Warning: get_chart_cache called outside Streamlit session_state context. Returning a dummy cache.")
        return {}


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


# --- グラフ生成関数 ---
def create_alos_chart_for_pdf(
    chart_data, title_prefix="全体", latest_date=None,
    moving_avg_window=30, font_name_for_mpl_to_use=None,
    days_to_show=90
):
    start_time = time.time()
    fig = None
    # 🚀 最適化: より効率的なフォント処理
    actual_font_name = font_name_for_mpl_to_use or MATPLOTLIB_FONT_NAME or MATPLOTLIB_FONT_NAME_FALLBACK
    font_prop = matplotlib.font_manager.FontProperties(family=actual_font_name)

    try:
        # 🚀 最適化: figureサイズとDPIを最適化
        fig, ax1 = plt.subplots(figsize=(10, 5.5), dpi=MATPLOTLIB_DPI)
        
        if not isinstance(chart_data, pd.DataFrame) or chart_data.empty: 
            return None
        required_columns = ["日付", "入院患者数（在院）", "総入院患者数", "総退院患者数"]
        if any(col not in chart_data.columns for col in required_columns): 
            print(f"ALOS Chart Error: Missing one or more required columns in data for {title_prefix}. Required: {required_columns}")
            return None

        # 🚀 最適化: データコピーを最小化
        data_copy = chart_data.copy() # 変更が加わるためコピーは維持
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)
        if data_copy.empty: 
            return None

        current_latest_date = latest_date if latest_date else data_copy['日付'].max()
        if pd.isna(current_latest_date): 
            current_latest_date = pd.Timestamp.now()

        start_date_limit = current_latest_date - pd.Timedelta(days=days_to_show -1)
        date_range_for_plot = pd.date_range(start=start_date_limit, end=current_latest_date, freq='D')
        
        # 🚀 最適化: ベクトル化された計算
        daily_metrics = []
        # 期間内のデータを事前にフィルタリング
        relevant_data = data_copy[(data_copy['日付'] >= date_range_for_plot.min() - pd.Timedelta(days=moving_avg_window -1)) & (data_copy['日付'] <= date_range_for_plot.max())]
        
        for display_date in date_range_for_plot:
            window_start = display_date - pd.Timedelta(days=moving_avg_window - 1)
            window_data = relevant_data[(relevant_data['日付'] >= window_start) & (relevant_data['日付'] <= display_date)]
            
            if not window_data.empty:
                total_patient_days = window_data['入院患者数（在院）'].sum()
                total_admissions = window_data['総入院患者数'].sum()
                total_discharges = window_data['総退院患者数'].sum()
                num_days_in_window = window_data['日付'].nunique() # 実際のデータが存在する日数
                
                denominator = (total_admissions + total_discharges) / 2
                alos = total_patient_days / denominator if denominator > 0 else np.nan
                daily_census = total_patient_days / num_days_in_window if num_days_in_window > 0 else np.nan
                daily_metrics.append({'日付': display_date, '平均在院日数': alos, '平均在院患者数': daily_census})

        if not daily_metrics: 
            return None
        daily_df = pd.DataFrame(daily_metrics).sort_values('日付')
        if daily_df.empty: 
            return None

        # 🚀 最適化: プロット処理の最適化
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
        # ax2のX軸ラベルはax1と共通なので、フォント設定は不要（重複）
        # for label in ax2.get_xticklabels(): 
        #     label.set_fontproperties(font_prop)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_prop_obj = font_prop.copy()
        legend_prop_obj.set_size(8)
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_prop_obj)

        plt.title(f"{title_prefix} ALOSと在院患者数(直近{days_to_show}日)", fontproperties=font_prop, fontsize=12)
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        plt.tight_layout(pad=0.8)
        
        # 🚀 最適化: 高品質かつ軽量な画像出力
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=PDF_RENDER_DPI, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error in create_alos_chart_for_pdf for {title_prefix}: {e}")
        import traceback; 
        print(traceback.format_exc())
        return None
    finally:
        if fig: 
            plt.close(fig)
        # 🚀 最適化: 強制的なメモリクリーンアップ
        gc.collect()

def create_patient_chart_with_target_wrapper(
    data, title="入院患者数推移", days=90, show_moving_average=True, target_value=None,
    font_name_for_mpl_to_use=None
):
    fig = None
    actual_font_name = font_name_for_mpl_to_use or MATPLOTLIB_FONT_NAME or MATPLOTLIB_FONT_NAME_FALLBACK
    font_prop = matplotlib.font_manager.FontProperties(family=actual_font_name)
    try:
        # 🚀 最適化: DPI設定とサイズ最適化
        fig, ax = plt.subplots(figsize=(8, 4.0), dpi=MATPLOTLIB_DPI)
        
        if not isinstance(data, pd.DataFrame) or data.empty: 
            return None
        if "日付" not in data.columns or "入院患者数（在院）" not in data.columns: 
            print(f"Patient Chart Error: Missing '日付' or '入院患者数（在院）' in data for {title}.")
            return None

        data_copy = data.copy() # 変更が加わるためコピーは維持
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)
        if data_copy.empty : 
            return None

        grouped = data_copy.groupby("日付")["入院患者数（在院）"].sum().reset_index().sort_values("日付")
        if len(grouped) > days: 
            grouped = grouped.tail(days)
        if grouped.empty: 
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
                caution_threshold = target_val_float * 0.97
                ax.fill_between(grouped["日付"], caution_threshold, target_val_float, color='orange', alpha=0.15, label='注意ゾーン(目標未達)')
            except ValueError: 
                print(f"Warning: Target value '{target_value}' for {title} not float.")

        ax.set_title(title, fontproperties=font_prop, fontsize=11)
        ax.set_xlabel('日付', fontproperties=font_prop, fontsize=9)
        ax.set_ylabel('患者数', fontproperties=font_prop, fontsize=9)
        ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        legend_font_prop = font_prop.copy(); 
        legend_font_prop.set_size(8)
        ax.legend(prop=legend_font_prop)
        ax.tick_params(axis='x', labelsize=7, rotation=30)
        for label in ax.get_xticklabels():
            label.set_fontproperties(font_prop)
            label.set_ha('right')
        ax.tick_params(axis='y', labelsize=7)
        for label in ax.get_yticklabels(): 
            label.set_fontproperties(font_prop)

        plt.tight_layout(pad=0.5)
        
        # 🚀 最適化: 高品質かつ軽量な画像出力
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=PDF_RENDER_DPI, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error in create_patient_chart_with_target_wrapper ('{title}'): {e}")
        import traceback; 
        print(traceback.format_exc())
        return None
    finally:
        if fig: 
            plt.close(fig)
        # 🚀 最適化: 強制的なメモリクリーンアップ
        gc.collect()

def create_dual_axis_chart_for_pdf(
    data, title="患者移動と在院数", days=90, font_name_for_mpl_to_use=None
):
    fig = None
    actual_font_name = font_name_for_mpl_to_use or MATPLOTLIB_FONT_NAME or MATPLOTLIB_FONT_NAME_FALLBACK
    font_prop = matplotlib.font_manager.FontProperties(family=actual_font_name)
    try:
        # 🚀 最適化: DPI設定とサイズ最適化
        fig, ax1 = plt.subplots(figsize=(8, 4.0), dpi=MATPLOTLIB_DPI)
        
        if not isinstance(data, pd.DataFrame) or data.empty: 
            return None
        required_cols = ["日付", "入院患者数（在院）", "新入院患者数", "緊急入院患者数", "総退院患者数"]
        if any(col not in data.columns for col in required_cols): 
            print(f"Dual Axis Chart Error: Missing one or more required columns in data for {title}. Required: {required_cols}")
            return None

        data_copy = data.copy() # 変更が加わるためコピーは維持
        if not pd.api.types.is_datetime64_any_dtype(data_copy['日付']):
            data_copy['日付'] = pd.to_datetime(data_copy['日付'], errors='coerce')
            data_copy.dropna(subset=['日付'], inplace=True)
        if data_copy.empty: 
            return None

        agg_dict = {"入院患者数（在院）": "sum", "新入院患者数": "sum", "緊急入院患者数": "sum", "総退院患者数": "sum"}
        grouped = data_copy.groupby("日付").agg(agg_dict).reset_index().sort_values("日付")
        if len(grouped) > days: 
            grouped = grouped.tail(days)
        if grouped.empty: 
            return None

        cols_for_ma = ["入院患者数（在院）", "新入院患者数", "緊急入院患者数", "総退院患者数"]
        for col in cols_for_ma:
            if col in grouped.columns: 
                grouped[f'{col}_7日MA'] = grouped[col].rolling(window=7, min_periods=1).mean()
            else: 
                grouped[f'{col}_7日MA'] = 0 # 念のためカラムが存在しない場合もMAカラムは作成

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
        for label in ax2.get_yticklabels(): 
            label.set_fontproperties(font_prop)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend_font_prop = font_prop.copy(); 
        legend_font_prop.set_size(8)
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left', prop=legend_font_prop)

        plt.title(title, fontproperties=font_prop, fontsize=11)
        ax1.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        plt.tight_layout(pad=0.5)
        
        # 🚀 最適化: 高品質かつ軽量な画像出力
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=PDF_RENDER_DPI, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error in create_dual_axis_chart_for_pdf ('{title}'): {e}")
        import traceback; 
        print(traceback.format_exc())
        return None
    finally:
        if fig: 
            plt.close(fig)
        # 🚀 最適化: 強制的なメモリクリーンアップ
        gc.collect()

# --- 🔧 グラフ重複検証関数を追加 ---
def validate_and_deduplicate_chart_buffers(chart_buffers_dict, chart_type_name, allowed_days=None):
    """グラフバッファの検証と重複除去"""
    if not chart_buffers_dict:
        return {}
    
    print(f"🔎 VALIDATING ({chart_type_name}): Input keys: {list(chart_buffers_dict.keys())}, Allowed days: {allowed_days}") # 追加ログ
    validated_buffers = {}
    processed_days = set()
    
    # 許可された日数のチェック
    if allowed_days:
        allowed_days_set = set(str(d) for d in allowed_days) # 文字列に変換して比較
    else:
        # allowed_days が None や空の場合は、すべてのバッファを許可（フィルタリングしない）
        # ただし、実際には呼び出し元でデフォルト値が設定される想定
        allowed_days_set = None 
    
    for days_str_key, buffer_data in chart_buffers_dict.items():
        days_str = str(days_str_key) # キーを文字列として確実に扱う
        
        # 重複チェック (同じ日数のキーが複数回処理されるのを防ぐ)
        if days_str in processed_days:
            print(f"  ⚠️ VALIDATE SKIP (Duplicate Day) ({chart_type_name}): Skipping duplicate day key '{days_str}'") # 詳細ログ
            continue
        
        # 許可された日数のチェック
        if allowed_days_set and days_str not in allowed_days_set:
            print(f"  ⚠️ VALIDATE SKIP (Not Allowed) ({chart_type_name}): Skipping day key '{days_str}' (Not in {allowed_days_set})") # 詳細ログ
            continue
        
        # バッファの有効性チェック
        if buffer_data and (isinstance(buffer_data, bytes) or hasattr(buffer_data, 'getvalue')):
            validated_buffers[days_str] = buffer_data # 有効なバッファを文字列キーで保存
            processed_days.add(days_str)
            buffer_length = 'N/A'
            if isinstance(buffer_data, bytes):
                buffer_length = len(buffer_data)
            elif hasattr(buffer_data, 'getvalue'):
                try:
                    # BytesIOの場合、getvalue()で内容を取得し長さを確認
                    buffer_length = len(buffer_data.getvalue())
                except Exception:
                    pass # getvalue() が失敗する場合など（通常はないはず）
            print(f"  ✅ VALIDATE OK ({chart_type_name}): Added buffer for day '{days_str}' (Size: {buffer_length})") # 詳細ログ
        else:
            print(f"  ❌ VALIDATE FAIL (Invalid Buffer) ({chart_type_name}): Invalid buffer for day '{days_str}' (Type: {type(buffer_data)})") # 詳細ログ
    
    print(f"🏁 VALIDATED ({chart_type_name}): Output keys: {list(validated_buffers.keys())}") # 追加ログ
    return validated_buffers

# Example usage (for context, not part of the function itself):
if __name__ == '__main__':
    # Dummy buffer data
    dummy_buffer_90 = BytesIO(b"graph_data_90_days").getvalue() # Simulating bytes
    dummy_buffer_180 = BytesIO(b"graph_data_180_days_longer").getvalue()
    dummy_buffer_30_invalid = None
    dummy_buffer_90_duplicate = BytesIO(b"graph_data_90_days_duplicate").getvalue()


    print("--- Test Case 1: Basic 90 and 180 days ---")
    test_buffers1 = {'90': dummy_buffer_90, '180': dummy_buffer_180}
    allowed1 = ['90', '180']
    validate_and_deduplicate_chart_buffers(test_buffers1, "ALOS_Test1", allowed1)
    # Expected: Both 90 and 180 should be validated.

    print("\n--- Test Case 2: Only 90 days allowed ---")
    allowed2 = ['90']
    validate_and_deduplicate_chart_buffers(test_buffers1, "ALOS_Test2", allowed2)
    # Expected: Only 90 should be validated, 180 skipped.

    print("\n--- Test Case 3: Invalid buffer and not allowed day ---")
    test_buffers3 = {'90': dummy_buffer_90, '30': dummy_buffer_30_invalid, '180': dummy_buffer_180}
    allowed3 = ['90', '180']
    validate_and_deduplicate_chart_buffers(test_buffers3, "Patient_Test3", allowed3)
    # Expected: 90 and 180 validated, 30 skipped (invalid buffer).

    print("\n--- Test Case 4: Duplicate day key (though dicts inherently handle this by overwrite) ---")
    # Python dicts don't allow true duplicate keys in literal, last one wins.
    # This part of the function's logic (if days_str in processed_days:) is more for
    # scenarios where keys might be generated in a loop and could accidentally repeat.
    test_buffers4 = {}
    test_buffers4['90'] = dummy_buffer_90
    # If there was a way to force {'90':val1, '90':val2}, the logic would be tested.
    # Instead, we simulate chart_buffers_dict being built in a way that might lead to this,
    # but practically, the processed_days check ensures each unique day string is added once.
    print("Simulating a scenario where '90' might appear multiple times before this function if keys were not unique.")
    # This test case isn't perfect for dicts, but shows the processed_days logic.
    # A more realistic test would be to call it with a dict that already has a key, then another call.
    
    print("\n--- Test Case 5: Integer keys in input dict ---")
    test_buffers5 = {90: dummy_buffer_90, 180: dummy_buffer_180, '30': dummy_buffer_90} # Mix of int and str keys
    allowed5 = ['90', '180'] # Allowed days are strings
    validate_and_deduplicate_chart_buffers(test_buffers5, "DualAxis_Test5", allowed5)
    # Expected: 90 and 180 (from int keys) should be validated and converted to string keys. '30' also validated.

# --- PDF生成メイン関数 ---
def create_pdf(
    forecast_df, df_weekday, df_holiday, df_all_avg=None,
    chart_data=None, title_prefix="全体", latest_date=None,
    target_data=None, filter_code="全体", graph_days=None, # graph_days は古い引数名、allowed_graph_days を優先
    alos_chart_buffers=None,
    patient_chart_buffers=None,
    dual_axis_chart_buffers=None,
    allowed_graph_days=None  # 🔧 このパラメータを正しく使用する
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
    max_graphs_per_page = 2 # 1ページあたりの最大グラフ数

    # 🔧 許可された日数の設定を修正
    if not allowed_graph_days: # None または空のリストの場合
        current_allowed_graph_days = ["90"]  # デフォルトでFast Mode相当
        print(f"⚠️ PDF生成 ({title_prefix}): allowed_graph_days が指定されなかったか空のため、デフォルトの ['90'] 日を使用します。")
    else:
        current_allowed_graph_days = [str(d) for d in allowed_graph_days] # 文字列に変換
    
    print(f"🔧 PDF生成 ({title_prefix}): create_pdf 関数が使用するグラフ日数: {current_allowed_graph_days}")
    
    # 🔧 グラフバッファの検証と重複除去 (修正された current_allowed_graph_days を使用)
    validated_alos_buffers = validate_and_deduplicate_chart_buffers(
        alos_chart_buffers, "ALOSグラフ", current_allowed_graph_days
    ) if alos_chart_buffers else {}
    
    validated_patient_buffers = {}
    if patient_chart_buffers:
        for chart_type, buffers in patient_chart_buffers.items():
            validated_patient_buffers[chart_type] = validate_and_deduplicate_chart_buffers(
                buffers, f"患者数推移グラフ({chart_type})", current_allowed_graph_days
            )
    
    validated_dual_axis_buffers = validate_and_deduplicate_chart_buffers(
        dual_axis_chart_buffers, "二軸グラフ", current_allowed_graph_days
    ) if dual_axis_chart_buffers else {}

    # 🔧 検証済みバッファの内容確認 (デバッグ用)
    # print(f"🔧 検証済みALOSバッファ ({title_prefix}): {list(validated_alos_buffers.keys())}")
    # for chart_type, buffers in validated_patient_buffers.items():
    #     if buffers: print(f"🔧 検証済み患者数推移バッファ({chart_type}, {title_prefix}): {list(buffers.keys())}")
    # print(f"🔧 検証済み二軸バッファ ({title_prefix}): {list(validated_dual_axis_buffers.keys())}")

    # グラフ追加処理 (ALOS, 患者数推移, 二軸)
    # グラフの種類ごとに追加し、ページ区切りを適切に管理
    
    all_graph_types_to_process = []
    if validated_alos_buffers:
        all_graph_types_to_process.append(
            ("ALOS", validated_alos_buffers, f"平均在院日数と平均在院患者数の推移（直近%s日間）")
        )
    if validated_patient_buffers:
        type_name_map = {"all": "全日", "weekday": "平日", "holiday": "休日"}
        for chart_type_key in ["all", "weekday", "holiday"]: # 表示順を固定
            day_buffers_dict = validated_patient_buffers.get(chart_type_key, {})
            if day_buffers_dict:
                display_name = type_name_map.get(chart_type_key, chart_type_key.capitalize())
                all_graph_types_to_process.append(
                    (f"患者数推移_{chart_type_key}", day_buffers_dict, f"{display_name} 入院患者数推移（直近%s日間）")
                )
    if validated_dual_axis_buffers:
        all_graph_types_to_process.append(
            ("二軸", validated_dual_axis_buffers, f"患者移動と在院数の推移（直近%s日間）")
        )

    # グラフ描画ループ
    for graph_name, buffers_dict, title_template in all_graph_types_to_process:
        print(f"📄 ADDING GRAPHS TO PDF ({title_prefix}): Processing graph type '{graph_name}'")
        print(f"  Buffers_dict for '{graph_name}': Keys = {list(buffers_dict.keys())}")
        
        try:
            valid_items_for_sorting = []
            for k, v_buf in buffers_dict.items():
                try:
                    int(k) 
                    valid_items_for_sorting.append((k,v_buf))
                except ValueError:
                    print(f"  ⚠️ SORTING WARNING ({title_prefix}, {graph_name}): Key '{k}' cannot be converted to int, skipping for sort.")
            
            if not valid_items_for_sorting:
                print(f"  ⚠️ NO VALID ITEMS FOR SORTING ({title_prefix}, {graph_name})")
                continue

            sorted_buffer_items = sorted(valid_items_for_sorting, key=lambda item: int(item[0]))
            print(f"  Sorted items for '{graph_name}': {[item[0] for item in sorted_buffer_items]}")
        except Exception as e_sort:
            print(f"  ❌ SORTING ERROR ({title_prefix}, {graph_name}): {e_sort}. Original keys: {list(buffers_dict.keys())}")
            continue

        for days_val_str, chart_buffer_bytes in sorted_buffer_items:
            print(f"    Attempting to add '{graph_name}' for '{days_val_str}' days.")
            if graphs_on_current_page >= max_graphs_per_page:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style))
                elements.append(Spacer(1, 5*mm))
                graphs_on_current_page = 0
                
            if chart_buffer_bytes:
                try:
                    if isinstance(chart_buffer_bytes, bytes):
                        img_buf = BytesIO(chart_buffer_bytes)
                    elif hasattr(chart_buffer_bytes, 'getvalue'): 
                        img_buf = chart_buffer_bytes 
                    else:
                        print(f"    ❌ SKIPPING '{graph_name}' ('{days_val_str}' days): Invalid buffer type {type(chart_buffer_bytes)}")
                        continue
                    
                    img_buf.seek(0) # BytesIOのポインタを先頭に
                    
                    # === ここからデバッグ用: 画像ファイル保存 ===
                    # ファイル名にPIDを追加して、並列処理でもファイルが上書きされないようにする
                    pid_for_filename = os.getpid() 
                    safe_title_prefix = "".join(c if c.isalnum() else '_' for c in title_prefix) # ファイル名安全化
                    debug_image_filename = f"debug_pid{pid_for_filename}_{safe_title_prefix}_{graph_name.replace('/', '_')}_{days_val_str}.png"
                    try:
                        with open(debug_image_filename, "wb") as f_debug_img:
                            f_debug_img.write(img_buf.getvalue()) # getvalue()で全バイト取得
                        print(f"    🖼️ DEBUG IMAGE SAVED: {debug_image_filename}")
                    except Exception as e_debug_save:
                        print(f"    ⚠️ DEBUG IMAGE SAVE FAILED for {debug_image_filename}: {e_debug_save}")
                    img_buf.seek(0) # 保存後、再度ポインタを先頭に戻す (Imageで使われるため)
                    # === デバッグ用ここまで ===

                    elements.append(Paragraph(title_template % days_val_str, ja_heading2))
                    elements.append(Spacer(1, 1.5*mm))
                    elements.append(Image(img_buf, width=page_width*0.9, height=(page_width*0.9)*0.45))
                    elements.append(Spacer(1, 3*mm))
                    graphs_on_current_page += 1
                    print(f"    ✅ Added '{graph_name}' for '{days_val_str}' days successfully.")
                except Exception as e:
                    print(f"    ❌ ERROR adding '{graph_name}' for '{days_val_str}' days to PDF: {e}")
                    import traceback
                    print(traceback.format_exc()) # エラーの詳細を出力
            else:
                print(f"    ℹ️ SKIPPING '{graph_name}' ('{days_val_str}' days): Buffer is empty/None.")
        
        # 最後のグラフセットの後で、次の要素がテーブルならページブレークを入れる判断を改善
        if graphs_on_current_page > 0 and graph_name != all_graph_types_to_process[-1][0] : # 最後のグラフタイプでなければ
             if graphs_on_current_page >= max_graphs_per_page : # ページが埋まっていたら改ページ
                 pass # ループの先頭で改ページされる
             elif graphs_on_current_page > 0 : # ページにグラフが残っていて、次のグラフタイプに移るなら
                 elements.append(PageBreak())
                 elements.append(Paragraph(report_title_text, ja_style))
                 elements.append(Spacer(1, 5*mm))
                 graphs_on_current_page = 0


    # テーブル生成ロジックの前に、グラフでページが途中なら改ページ
    if graphs_on_current_page > 0:
        elements.append(PageBreak())
        elements.append(Paragraph(report_title_text, ja_style)) # 新しいページにもタイトル
        elements.append(Spacer(1, 5*mm))
        # graphs_on_current_page = 0 # テーブルは別カウント

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
    
    # 平日・休日テーブルの前に改ページ
    if (df_weekday is not None and not df_weekday.empty) or \
       (df_holiday is not None and not df_holiday.empty):
        elements.append(PageBreak())
        elements.append(Paragraph(report_title_text, ja_style))
        elements.append(Spacer(1, 5*mm))

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
        
        # 病棟別テーブル
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
        
        # 診療科別テーブル
        if (is_dept_pdf and not is_ward_pdf) or (not is_ward_pdf and not is_dept_pdf) :
            if generated_dept_table_data and len(generated_dept_table_data) > 1:
                # 病棟別テーブルが出力されていなければ改ページ
                if not ((is_ward_pdf and not is_dept_pdf) or (not is_ward_pdf and not is_dept_pdf and generated_ward_table_data and len(generated_ward_table_data) > 1)):
                    elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style)); elements.append(Spacer(1, 5*mm))
                elements.append(Paragraph("診療科別 入院患者数（在院）平均", ja_heading2))
                num_cols = len(generated_dept_table_data[0])
                period_count = len(period_labels_dept_ward) if period_labels_dept_ward else 0
                col_widths_dept = [page_width * 0.12] + [(page_width * 0.70) / period_count if period_count > 0 else 0] * period_count + [page_width * 0.09] * 2
                if num_cols != len(col_widths_dept) and num_cols > 0: col_widths_dept = [page_width/num_cols] * num_cols
                elements.append(Table(generated_dept_table_data, colWidths=col_widths_dept, style=TableStyle(dept_ward_common_style + [('BACKGROUND', (0,0), (-1,0), colors.lightcyan)])))
                elements.append(Spacer(1, 4*mm))

    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph(f"作成日時: {today_str}", normal_ja))
    
    try:
        doc.build(elements)
    except Exception as e:
        print(f"❌ PDF構築エラー ({title_prefix}): {e}")
        import traceback
        print(traceback.format_exc())
        # エラー発生時もバッファを返すか、Noneを返すか検討
        buffer.seek(0) # 空のバッファや部分的なバッファを返す可能性
        return buffer # または return None
        
    buffer.seek(0)
    gc.collect()
    
    # print(f"🔧 PDF生成完了 - {title_prefix} (所要時間: {time.time() - pdf_start_time:.2f}秒)")
    return buffer

# create_landscape_pdf も同様に修正
def create_landscape_pdf(
    forecast_df, df_weekday, df_holiday, df_all_avg=None,
    chart_data=None, title_prefix="全体", latest_date=None,
    target_data=None, filter_code="全体", graph_days=None,
    alos_chart_buffers=None,
    patient_chart_buffers=None,
    dual_axis_chart_buffers=None,
    allowed_graph_days=None  # 🔧 このパラメータを正しく使用する
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
    styles.add(ParagraphStyle(name='Normal_Center_JP_Land', parent=styles['Normal_JP_Land'], alignment=TA_CENTER, fontSize=6.5, leading=8))

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
    page_width_land, page_height_land = landscape(A4)
    content_width_land = page_width_land - doc.leftMargin - doc.rightMargin
    content_height_land = page_height_land - doc.topMargin - doc.bottomMargin
    graphs_on_current_page = 0
    max_graphs_per_page_land = 2 # 横向きの場合も1ページ2グラフ想定

    # 🔧 許可された日数の設定を修正
    if not allowed_graph_days: # None または空のリストの場合
        current_allowed_graph_days = ["90"]  # デフォルトでFast Mode相当
        print(f"⚠️ 横向きPDF生成 ({title_prefix}): allowed_graph_days が指定されなかったか空のため、デフォルトの ['90'] 日を使用します。")
    else:
        current_allowed_graph_days = [str(d) for d in allowed_graph_days]
    
    print(f"🔧 横向きPDF生成 ({title_prefix}): create_landscape_pdf 関数が使用するグラフ日数: {current_allowed_graph_days}")
    
    # 🔧 グラフバッファの検証と重複除去
    validated_alos_buffers = validate_and_deduplicate_chart_buffers(
        alos_chart_buffers, "ALOSグラフ(横向き)", current_allowed_graph_days
    ) if alos_chart_buffers else {}
    
    validated_patient_buffers = {}
    if patient_chart_buffers:
        for chart_type, buffers in patient_chart_buffers.items():
            validated_patient_buffers[chart_type] = validate_and_deduplicate_chart_buffers(
                buffers, f"患者数推移グラフ(横向き)({chart_type})", current_allowed_graph_days
            )
    
    validated_dual_axis_buffers = validate_and_deduplicate_chart_buffers(
        dual_axis_chart_buffers, "二軸グラフ(横向き)", current_allowed_graph_days
    ) if dual_axis_chart_buffers else {}
    
    # グラフ追加処理 (create_pdfと同様のロジックで)
    all_graph_types_to_process_land = []
    if validated_alos_buffers:
        all_graph_types_to_process_land.append(
            ("ALOS", validated_alos_buffers, f"平均在院日数と平均在院患者数の推移（直近%s日間）")
        )
    if validated_patient_buffers:
        type_name_map = {"all": "全日", "weekday": "平日", "holiday": "休日"}
        for chart_type_key in ["all", "weekday", "holiday"]: # 表示順を固定
            day_buffers_dict = validated_patient_buffers.get(chart_type_key, {})
            if day_buffers_dict:
                display_name = type_name_map.get(chart_type_key, chart_type_key.capitalize())
                all_graph_types_to_process_land.append(
                    (f"患者数推移_{chart_type_key}", day_buffers_dict, f"{display_name} 入院患者数推移（直近%s日間）")
                )
    if validated_dual_axis_buffers:
        all_graph_types_to_process_land.append(
            ("二軸", validated_dual_axis_buffers, f"患者移動と在院数の推移（直近%s日間）")
        )

    for graph_name, buffers_dict, title_template in all_graph_types_to_process_land:
        sorted_buffer_items = sorted(buffers_dict.items(), key=lambda item: int(item[0]))
        
        for days_val_str, chart_buffer_bytes in sorted_buffer_items:
            if graphs_on_current_page >= max_graphs_per_page_land:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style_land))
                elements.append(Spacer(1, 3*mm))
                graphs_on_current_page = 0
                
            if chart_buffer_bytes:
                try:
                    if isinstance(chart_buffer_bytes, bytes):
                        img_buf = BytesIO(chart_buffer_bytes)
                    elif hasattr(chart_buffer_bytes, 'getvalue'):
                        img_buf = chart_buffer_bytes
                    else:
                        print(f"❌ {graph_name}グラフ(横) ({days_val_str}日) のバッファタイプが不正: {type(chart_buffer_bytes)}")
                        continue
                    
                    img_buf.seek(0)
                    elements.append(Paragraph(title_template % days_val_str, ja_heading2_land))
                    elements.append(Spacer(1, 1*mm))
                    # 横向きPDFでの画像サイズ調整 (例: コンテンツ幅の90%, 高さはアスペクト比0.4)
                    elements.append(Image(img_buf, width=content_width_land*0.9, height=(content_width_land*0.9)*0.4)) 
                    elements.append(Spacer(1, 2*mm))
                    graphs_on_current_page += 1
                except Exception as e:
                    print(f"❌ {graph_name}グラフ(横)追加エラー ({title_prefix}, {days_val_str}日): {e}")
            else:
                print(f"ℹ️ {graph_name}グラフ(横)のバッファが空です ({title_prefix}, {days_val_str}日)")
        
        if graphs_on_current_page > 0 and graph_name != all_graph_types_to_process_land[-1][0]:
            if graphs_on_current_page >= max_graphs_per_page_land:
                pass
            elif graphs_on_current_page > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(report_title_text, ja_style_land))
                elements.append(Spacer(1, 3*mm))
                graphs_on_current_page = 0

    if graphs_on_current_page > 0: # 最後のグラフセットの後
        elements.append(PageBreak())
        elements.append(Paragraph(report_title_text, ja_style_land))
        elements.append(Spacer(1, 3*mm))

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
        num_cols = len(header); col_widths = [content_width_land*0.2] + [(content_width_land*0.8)/(num_cols-1 if num_cols > 1 else 1)]*(num_cols-1)
        elements.append(Table(table_data, colWidths=col_widths, style=TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.blue)])))
        elements.append(Spacer(1, 2*mm))

    # 平日・休日テーブルの前に改ページ
    if (df_weekday is not None and not df_weekday.empty) or \
       (df_holiday is not None and not df_holiday.empty):
        elements.append(PageBreak())
        elements.append(Paragraph(report_title_text, ja_style_land))
        elements.append(Spacer(1, 3*mm))
        
    left_col_elements, right_col_elements = [], []
    table_half_width = content_width_land * 0.48 # 左右のテーブル幅
    
    if df_weekday is not None and not df_weekday.empty:
        left_col_elements.append(Paragraph("平日平均値", ja_heading2_land))
        header_wd = [df_weekday.index.name if df_weekday.index.name else "区分"] + df_weekday.columns.tolist()
        table_data_wd = [header_wd] + [[str(idx)] + [f"{x:.1f}" if isinstance(x,(float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_weekday.iterrows()]
        num_cols_wd = len(header_wd); col_widths_wd = [table_half_width*0.25] + [(table_half_width*0.75)/(num_cols_wd-1 if num_cols_wd > 1 else 1)]*(num_cols_wd-1)
        left_col_elements.append(Table(table_data_wd, colWidths=col_widths_wd, style=TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.teal)])))
    
    if df_holiday is not None and not df_holiday.empty:
        right_col_elements.append(Paragraph("休日平均値", ja_heading2_land))
        header_hd = [df_holiday.index.name if df_holiday.index.name else "区分"] + df_holiday.columns.tolist()
        table_data_hd = [header_hd] + [[str(idx)] + [f"{x:.1f}" if isinstance(x,(float,int)) and pd.notna(x) else (str(x) if pd.notna(x) else "-") for x in row] for idx, row in df_holiday.iterrows()]
        num_cols_hd = len(header_hd); col_widths_hd = [table_half_width*0.25] + [(table_half_width*0.75)/(num_cols_hd-1 if num_cols_hd > 1 else 1)]*(num_cols_hd-1)
        right_col_elements.append(Table(table_data_hd, colWidths=col_widths_hd, style=TableStyle(common_table_style_land_cmds + [('BACKGROUND', (0,0), (-1,0), colors.orange)])))
    
    if left_col_elements or right_col_elements:
        # Tableのセルに直接リストを渡す
        elements.append(Table([[left_col_elements, right_col_elements]], 
                                colWidths=[table_half_width, content_width_land - table_half_width - 2*mm], # 隙間を考慮
                                style=TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))) # 上揃え
    elements.append(Spacer(1, 2*mm))


    if chart_data is not None and not chart_data.empty:
        generated_ward_table_data, generated_dept_table_data, period_labels_dept_ward = create_department_tables(
            chart_data, current_latest_date, target_data, filter_code, para_style_normal_center_land
        )
        dept_ward_style_land = [
            ('FONTNAME', (0,0), (-1,-1), REPORTLAB_FONT_NAME), ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTSIZE', (0,0), (-1,0), 7), ('FONTSIZE', (0,1), (-1,-1), 6.5), ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ]
        is_ward_pdf = "病棟別" in title_prefix; is_dept_pdf = "診療科別" in title_prefix
        
        if (is_ward_pdf and not is_dept_pdf) or (not is_ward_pdf and not is_dept_pdf) : # 病棟PDF または 全体PDF の場合
            if generated_ward_table_data and len(generated_ward_table_data) > 1:
                elements.append(PageBreak()); elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm))
                elements.append(Paragraph("病棟別 入院患者数（在院）平均", ja_heading2_land))
                num_cols = len(generated_ward_table_data[0]); period_count = len(period_labels_dept_ward) if period_labels_dept_ward else 0
                col_widths_w = [content_width_land*0.10] + [(content_width_land*0.72)/period_count if period_count > 0 else 0]*period_count + [content_width_land*0.09]*2
                if num_cols != len(col_widths_w) and num_cols > 0: col_widths_w = [content_width_land/num_cols] * num_cols
                elements.append(Table(generated_ward_table_data, colWidths=col_widths_w, style=TableStyle(dept_ward_style_land + [('BACKGROUND', (0,0), (-1,0), colors.lightgrey)])))
                elements.append(Spacer(1, 2*mm))
        
        if (is_dept_pdf and not is_ward_pdf) or (not is_ward_pdf and not is_dept_pdf) : # 診療科PDF または 全体PDF の場合
            if generated_dept_table_data and len(generated_dept_table_data) > 1:
                # 病棟別テーブルが出力されていなければ改ページ (全体PDFで病棟テーブルが先に出ている場合)
                needs_page_break_before_dept = True
                if (not is_ward_pdf and not is_dept_pdf) and (generated_ward_table_data and len(generated_ward_table_data) > 1):
                    # 全体PDFで、かつ病棟テーブルが既に出力されている場合は、改ページ済みとみなす
                     pass # 改ページは既に行われているか、病棟テーブルの直後
                else:
                    elements.append(PageBreak())
                
                elements.append(Paragraph(report_title_text, ja_style_land)); elements.append(Spacer(1, 3*mm))
                elements.append(Paragraph("診療科別 入院患者数（在院）平均", ja_heading2_land))
                num_cols = len(generated_dept_table_data[0]); period_count = len(period_labels_dept_ward) if period_labels_dept_ward else 0
                col_widths_d = [content_width_land*0.10] + [(content_width_land*0.72)/period_count if period_count > 0 else 0]*period_count + [content_width_land*0.09]*2
                if num_cols != len(col_widths_d) and num_cols > 0: col_widths_d = [content_width_land/num_cols] * num_cols
                elements.append(Table(generated_dept_table_data, colWidths=col_widths_d, style=TableStyle(dept_ward_style_land + [('BACKGROUND', (0,0), (-1,0), colors.lightcyan)])))
                elements.append(Spacer(1, 2*mm))

    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph(f"作成日時: {today_str}", normal_ja_land))
    
    try:
        doc.build(elements)
    except Exception as e:
        print(f"❌ 横向きPDF構築エラー ({title_prefix}): {e}")
        import traceback
        print(traceback.format_exc())
        buffer.seek(0)
        return buffer # または return None
        
    buffer.seek(0)
    gc.collect()
    
    # print(f"🔧 横向きPDF生成完了 - {title_prefix} (所要時間: {time.time() - pdf_start_time:.2f}秒)")
    return buffer


# --- 部門別テーブル生成関数 (この関数は変更なしと仮定) ---
def create_department_tables(chart_data, latest_date, target_data=None, filter_code=None, para_style=None):
    dept_tbl_start_time = time.time()
    if chart_data is None or chart_data.empty or latest_date is None:
        return [], [], []

    if not pd.api.types.is_datetime64_any_dtype(chart_data['日付']):
        try: 
            chart_data['日付'] = pd.to_datetime(chart_data['日付'])
        except Exception: 
            print("Error: Could not convert '日付' to datetime in create_department_tables.")
            return [], [], []
    if not isinstance(latest_date, pd.Timestamp): 
        try:
            latest_date = pd.Timestamp(latest_date)
        except Exception:
            print(f"Error: Could not convert latest_date '{latest_date}' to Timestamp.")
            return [], [], []


    current_year_start_month = 4 # 年度開始月 (4月)
    if latest_date.month < current_year_start_month:
        current_fiscal_year_start = pd.Timestamp(year=latest_date.year - 1, month=current_year_start_month, day=1)
    else:
        current_fiscal_year_start = pd.Timestamp(year=latest_date.year, month=current_year_start_month, day=1)
    current_fiscal_year_end_for_data = latest_date # データは最新日まで
    
    previous_fiscal_year_start = current_fiscal_year_start - pd.DateOffset(years=1)
    previous_fiscal_year_end = current_fiscal_year_start - pd.Timedelta(days=1) # 前年度の最終日

    period_definitions = {
        "直近7日": (latest_date - pd.Timedelta(days=6), latest_date),
        "直近14日": (latest_date - pd.Timedelta(days=13), latest_date),
        "直近30日": (latest_date - pd.Timedelta(days=29), latest_date),
        "直近60日": (latest_date - pd.Timedelta(days=59), latest_date),
        f"{current_fiscal_year_start.year}年度": (current_fiscal_year_start, current_fiscal_year_end_for_data),
        f"{previous_fiscal_year_start.year}年度": (previous_fiscal_year_start, previous_fiscal_year_end),
    }
    period_labels_for_data = list(period_definitions.keys())
    period_name_for_achievement = "直近30日" # 達成率計算の基準期間
    
    if para_style is None: # ReportLabのParagraphStyleオブジェクトを期待
        styles_default = getSampleStyleSheet()
        # フォントが存在するか確認し、なければフォールバック
        font_name_to_use = REPORTLAB_FONT_NAME
        try:
            pdfmetrics.getFont(font_name_to_use)
        except KeyError:
            print(f"Warning: Font '{font_name_to_use}' not found in ReportLab. Falling back to Helvetica.")
            font_name_to_use = 'Helvetica' # ReportLabのデフォルトフォントの一つ
            
        para_style = ParagraphStyle('ParaNormalCenterDefault_Dept', 
                                    parent=styles_default['Normal'], 
                                    fontName=font_name_to_use, 
                                    fontSize=6.5, 
                                    alignment=TA_CENTER, 
                                    leading=7)

    # ヘッダーのラベルに改行を挿入 (ReportLabのParagraphはHTMLライクな<br/>タグで改行可能)
    period_labels_for_header = [Paragraph(label.replace("直近", "直近<br/>").replace("年度", "<br/>年度"), para_style) for label in period_labels_for_data]

    ward_codes_unique = sorted(chart_data["病棟コード"].astype(str).unique()) if "病棟コード" in chart_data.columns else []
    dept_names_original = sorted(chart_data["診療科名"].unique()) if "診療科名" in chart_data.columns else []
    dept_names_to_process = dept_names_original # 特にフィルタリングがなければそのまま
    
    # 表示名マッピング (target_data から取得、なければルールベースで生成)
    ward_display_names = {}
    if target_data is not None and not target_data.empty and '部門コード' in target_data.columns and '部門名' in target_data.columns:
        # '部門コード'を文字列に変換してマッピングを作成
        unique_target_wards = target_data[['部門コード', '部門名']].drop_duplicates('部門コード')
        ward_display_map_from_target = pd.Series(unique_target_wards.部門名.values, index=unique_target_wards.部門コード.astype(str)).to_dict()
    else:
        ward_display_map_from_target = {}

    for ward_code in ward_codes_unique:
        display_name = ward_display_map_from_target.get(ward_code)
        if display_name and pd.notna(display_name):
            ward_display_names[ward_code] = display_name
        else: # target_dataにないか、部門名がNaNの場合のフォールバック
            match = re.match(r'0*(\d+)([A-Za-z]*)', ward_code) # 先頭の0を除去
            if match: 
                ward_display_names[ward_code] = f"{match.group(1)}{match.group(2)}病棟"
            else: 
                ward_display_names[ward_code] = ward_code # マッチしない場合はそのままコードを使用

    # 集計用辞書
    ward_metrics = {ward_code: {} for ward_code in ward_codes_unique}
    dept_metrics = {dept_name: {} for dept_name in dept_names_to_process}

    # 期間別集計
    for period_label, (start_dt_period, end_dt_period) in period_definitions.items():
        if start_dt_period > end_dt_period: # 前年度データがない場合など
            continue
        period_data_df = chart_data[(chart_data["日付"] >= start_dt_period) & (chart_data["日付"] <= end_dt_period)]
        if period_data_df.empty: 
            continue
        
        num_days_in_period_calc = period_data_df['日付'].nunique() # 期間内の実データ日数
        if num_days_in_period_calc == 0: 
            continue
            
        # 病棟別集計
        for ward_code in ward_codes_unique:
            ward_data_df = period_data_df[period_data_df["病棟コード"].astype(str) == ward_code]
            if not ward_data_df.empty and '入院患者数（在院）' in ward_data_df.columns:
                # 日付ごとに合計してから期間で合計 (重複日がある場合に備える)
                total_patient_days_val = ward_data_df.groupby('日付')['入院患者数（在院）'].sum().sum()
                avg_daily_census_val = total_patient_days_val / num_days_in_period_calc if num_days_in_period_calc > 0 else np.nan
                ward_metrics[ward_code][period_label] = avg_daily_census_val
            else: 
                ward_metrics[ward_code][period_label] = np.nan # データなし

        # 診療科別集計
        for dept_name in dept_names_to_process:
            dept_data_df = period_data_df[period_data_df["診療科名"] == dept_name]
            if not dept_data_df.empty and '入院患者数（在院）' in dept_data_df.columns:
                total_patient_days_val = dept_data_df.groupby('日付')['入院患者数（在院）'].sum().sum()
                avg_daily_census_val = total_patient_days_val / num_days_in_period_calc if num_days_in_period_calc > 0 else np.nan
                dept_metrics[dept_name][period_label] = avg_daily_census_val
            else: 
                dept_metrics[dept_name][period_label] = np.nan
    
    # 目標値と達成率の取得 (新しい目標値ファイル構造に対応)
    target_dict_cache_local = {} # 関数内での簡易キャッシュ

    def get_targets_achievements_new_format(items_list, metrics_data_dict, target_data_df, achievement_period_name=period_name_for_achievement):
        targets_map = {}
        achievements_map = {}
        
        if target_data_df is None or target_data_df.empty:
            return targets_map, achievements_map

        # 必要な列を確認
        required_cols_new = ['部門コード', '指標タイプ', '期間区分', '目標値']
        required_cols_old = ['部門コード', '区分', '目標値'] # 古い形式
        
        target_data_df_local = target_data_df.copy() # 元のDFを変更しない

        is_new_format = all(col in target_data_df_local.columns for col in required_cols_new)
        is_old_format = all(col in target_data_df_local.columns for col in required_cols_old)

        if is_new_format:
            # print("Using new target file format.")
            # 「日平均在院患者数」または「在院患者数」に関連する「全日」の目標値を取得
            census_targets_df = target_data_df_local[
                (target_data_df_local['指標タイプ'].astype(str).str.contains('日平均在院患者数|在院患者数', case=False, na=False)) &
                (target_data_df_local['期間区分'].astype(str) == '全日') & # 全日の目標値のみ
                (pd.notna(target_data_df_local['部門コード'])) &
                (pd.notna(target_data_df_local['目標値']))
            ]
            if not census_targets_df.empty:
                # 部門コードを文字列に変換して重複を削除し、辞書を作成
                target_mapping = dict(zip(census_targets_df['部門コード'].astype(str), census_targets_df['目標値'].astype(float)))
                
                for item_id in items_list:
                    item_id_str = str(item_id)
                    target_val = target_mapping.get(item_id_str)
                    if target_val is not None:
                        targets_map[item_id] = target_val
                        actual_val = metrics_data_dict.get(item_id, {}).get(achievement_period_name)
                        if pd.notna(actual_val) and target_val > 0:
                            achievements_map[item_id] = (actual_val / target_val) * 100
        elif is_old_format:
            # print("Using old target file format.")
            # 古い形式の処理（既存のロジックに近い）
            old_census_targets_df = target_data_df_local[
                (target_data_df_local['区分'].astype(str) == '全日') & # 全日の目標値のみ
                (pd.notna(target_data_df_local['部門コード'])) &
                (pd.notna(target_data_df_local['目標値']))
            ]
            if not old_census_targets_df.empty:
                target_mapping = dict(zip(old_census_targets_df['部門コード'].astype(str), old_census_targets_df['目標値'].astype(float)))

                for item_id in items_list:
                    item_id_str = str(item_id)
                    target_val = target_mapping.get(item_id_str)
                    if target_val is not None:
                        targets_map[item_id] = target_val
                        actual_val = metrics_data_dict.get(item_id, {}).get(achievement_period_name)
                        if pd.notna(actual_val) and target_val > 0:
                            achievements_map[item_id] = (actual_val / target_val) * 100
        else:
            print(f"Target file columns do not match known formats. Available columns: {list(target_data_df_local.columns)}")

        return targets_map, achievements_map

    ward_targets, ward_achievements = get_targets_achievements_new_format(ward_codes_unique, ward_metrics, target_data)
    dept_targets, dept_achievements = get_targets_achievements_new_format(dept_names_to_process, dept_metrics, target_data)
    
    # テーブル表示順のソート (達成率 > 目標値あり > 目標値なし)
    def sort_entities_for_table(entities, achievements_dict, targets_dict, display_names_dict=None):
        # display_names_dictはソートキーには直接使わないが、元のentity IDを保持するためにラップする
        def get_sort_key(entity_id):
            ach = achievements_dict.get(entity_id, -float('inf')) # 達成率がない場合は最後に
            has_target = entity_id in targets_dict
            # 達成率で降順、目標値ありを優先、最後にIDで昇順 (文字列として)
            return (-ach, not has_target, str(entity_id)) 
            
        return sorted(entities, key=get_sort_key)

    sorted_ward_codes = sort_entities_for_table(ward_codes_unique, ward_achievements, ward_targets, ward_display_names)
    # 診療科名は既に文字列なので、display_names_dictは不要
    sorted_dept_names = sort_entities_for_table(dept_names_to_process, dept_achievements, dept_targets)
    
    # テーブルヘッダー
    header_items = [Paragraph("部門", para_style)] + period_labels_for_header + \
                   [Paragraph("目標値", para_style), Paragraph("達成率<br/>(%)", para_style)]
    
    # 病棟テーブルデータ作成
    ward_table_data = [header_items]
    for ward_code_val in sorted_ward_codes: # ソート済みのリストを使用
        display_name_ward = ward_display_names.get(ward_code_val, str(ward_code_val))
        row_items = [Paragraph(display_name_ward, para_style)]
        for period_label_val in period_labels_for_data: 
            val = ward_metrics.get(ward_code_val, {}).get(period_label_val)
            row_items.append(f"{val:.1f}" if pd.notna(val) else "-")
        row_items.append(f"{ward_targets.get(ward_code_val):.1f}" if ward_code_val in ward_targets else "-")
        row_items.append(f"{ward_achievements.get(ward_code_val):.1f}" if ward_code_val in ward_achievements else "-")
        ward_table_data.append(row_items)
    
    # 診療科テーブルデータ作成
    dept_table_data = [header_items]
    for dept_name_val in sorted_dept_names: # ソート済みのリストを使用
        # 診療科名はそのまま表示
        row_items = [Paragraph(str(dept_name_val), para_style)]
        for period_label_val in period_labels_for_data: 
            val = dept_metrics.get(dept_name_val, {}).get(period_label_val)
            row_items.append(f"{val:.1f}" if pd.notna(val) else "-")
        row_items.append(f"{dept_targets.get(dept_name_val):.1f}" if dept_name_val in dept_targets else "-")
        row_items.append(f"{dept_achievements.get(dept_name_val):.1f}" if dept_name_val in dept_achievements else "-")
        dept_table_data.append(row_items)
    
    # print(f"Department table generation took: {time.time() - dept_tbl_start_time:.2f}s")
    return ward_table_data, dept_table_data, period_labels_for_data