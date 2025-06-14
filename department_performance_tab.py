# department_performance_tab.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import textwrap

logger = logging.getLogger(__name__)

# 必要な外部モジュールをインポート
try:
    from utils import safe_date_filter
    from unified_filters import get_unified_filter_config
    from style import inject_department_performance_css, get_achievement_color_class, get_card_class
except ImportError as e:
    st.error(f"必要なモジュールのインポートに失敗しました: {e}")
    st.stop()


def get_period_dates(df, period_type):
    """期間タイプに基づいて開始日・終了日・説明文を計算する"""
    if df is None or df.empty or '日付' not in df.columns:
        return None, None, "データなし"
    max_date = df['日付'].max()
    min_date = df['日付'].min()

    # 期間タイプに応じた計算
    if period_type == "直近4週":
        start_date = max_date - pd.Timedelta(days=27)
        period_desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "直近8週":
        start_date = max_date - pd.Timedelta(days=55)
        period_desc = f"直近8週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "直近12週":
        start_date = max_date - pd.Timedelta(days=83)
        period_desc = f"直近12週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "今年度":
        year = max_date.year if max_date.month >= 4 else max_date.year - 1
        start_date = pd.Timestamp(year=year, month=4, day=1)
        start_date = max(start_date, min_date)
        period_desc = f"今年度 ({start_date.strftime('%Y/%m/%d')}～{max_date.strftime('%m/%d')})"
    elif period_type == "昨年度":
        year = max_date.year if max_date.month >= 4 else max_date.year - 1
        start_date = pd.Timestamp(year=year-1, month=4, day=1)
        end_date = pd.Timestamp(year=year, month=3, day=31)
        end_date = min(end_date, max_date)
        start_date = max(start_date, min_date)
        period_desc = f"昨年度 ({start_date.strftime('%Y/%m/%d')}～{end_date.strftime('%Y/%m/%d')})"
        return start_date, end_date, period_desc
    else:
        # デフォルトは直近4週
        start_date = max_date - pd.Timedelta(days=27)
        period_desc = f"直近4週間 ({start_date.strftime('%m/%d')}～{max_date.strftime('%m/%d')})"

    start_date = max(start_date, min_date)
    return start_date, max_date, period_desc


def calculate_department_kpis(df, target_data, dept_name, start_date, end_date, dept_col):
    """各診療科のKPIを計算して辞書で返す"""
    try:
        # 部門列名を動的に使用
        dept_df = df[df[dept_col] == dept_name]
        period_df = safe_date_filter(dept_df, start_date, end_date)
        if period_df.empty:
            return None
        # KPI計算ロジック（例）
        total_days = (end_date - start_date).days + 1
        data_count = len(period_df)
        avg_daily_census = data_count / total_days
        # 例: admissions_achievement を算出
        admissions_achievement = np.random.rand()  # 実ロジックに置き換えてください
        # その他KPIも同様に計算
        return {
            'dept_name': dept_name,
            'total_days': total_days,
            'data_count': data_count,
            'avg_daily_census': avg_daily_census,
            'admissions_achievement': admissions_achievement,
            'census_achievement': avg_daily_census / target_data.get('census_target', 1)
        }
    except Exception as e:
        logger.error(f"診療科KPI計算エラー ({dept_name}): {e}", exc_info=True)
        return None


def create_department_card_html(kpi_data):
    """各診療科の KPI を HTML カード形式で描画する"""
    # CSS クラス取得
    card_class = get_card_class(
        kpi_data.get('census_achievement', 0),
        kpi_data.get('admissions_achievement', 0)
    )
    census_color = get_achievement_color_class(kpi_data.get('census_achievement', 0))
    admissions_color = get_achievement_color_class(kpi_data.get('admissions_achievement', 0))

    html = f"""
        <div class="dept-performance-card {card_class}">
            <!-- ヘッダー -->
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <h3 style="margin:0; font-size:1em; font-weight:700;">{kpi_data['dept_name']}</h3>
                <span style="font-size:0.75em; color:#666;">{kpi_data['total_days']}日間 | {kpi_data['data_count']}件</span>
            </div>
            <!-- ボディ -->
            <div style="background:#fff; border-radius:8px; padding:10px;">
                <div style="text-align:center; margin-bottom:8px;">
                    <div style="font-size:0.75em; color:#999;">日平均在院患者数</div>
                    <div style="font-size:1.5em; font-weight:600;">{kpi_data['avg_daily_census']:.1f}</div>
                    <div style="font-size:0.75em; color:#999;">直近期間</div>
                </div>
                <div style="display:flex; justify-content:space-around;">
                    <div style="text-align:center;">
                        <div style="font-size:0.75em; color:#999;">在院達成率</div>
                        <div class="achievement-badge {census_color}" style="display:inline-block; padding:2px 6px; border-radius:4px;">{kpi_data['census_achievement']*100:.1f}%</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:0.75em; color:#999;">週入院達成率</div>
                        <div class="achievement-badge {admissions_color}" style="display:inline-block; padding:2px 6px; border-radius:4px;">{kpi_data['admissions_achievement']*100:.1f}%</div>
                    </div>
                </div>
            </div>
        </div>
    """
    # インデントと先頭空白を除去
    return textwrap.dedent(html).lstrip()


def render_performance_cards(dept_kpis, columns_count):
    for i in range(0, len(dept_kpis), columns_count):
        cols = st.columns(columns_count)
        for j in range(columns_count):
            if i + j < len(dept_kpis):
                with cols[j]:
                    html = create_department_card_html(dept_kpis[i+j])
                    st.markdown(html, unsafe_allow_html=True)


def display_department_performance_dashboard():
    st.header("🏥 診療科別パフォーマンスダッシュボード")
    inject_department_performance_css()

    if not st.session_state.get('data_processed', False):
        st.warning("データを読み込み後に利用可能になります。")
        return

    df_original = st.session_state['df']
    target_data = st.session_state.get('target_data', {})

    # 統一設定から期間・ソート・列数を取得
    unified_config = get_unified_filter_config()
    period_key = unified_config.get('period') or unified_config.get('period_type') or '直近4週'
    sort_key = unified_config.get('sort', '診療科名（昇順）')
    columns_count = unified_config.get('columns', 3)

    # 開始日・終了日・説明文を取得
    start_date, end_date, period_desc = get_period_dates(df_original, period_key)
    date_filtered_df = safe_date_filter(df_original, start_date, end_date)

    # 部門名／診療科名の列を自動検出
    possible_cols = ['部門名', '診療科', '診療科名']
    dept_col = next((c for c in possible_cols if c in date_filtered_df.columns), None)
    if dept_col is None:
        st.error(f"診療科列が見つかりません。期待する列: {possible_cols}")
        return

    # 各診療科のKPI計算
    dept_kpis = []
    for dept in date_filtered_df[dept_col].unique():
        kpi = calculate_department_kpis(date_filtered_df, target_data, dept, start_date, end_date, dept_col)
        if kpi:
            dept_kpis.append(kpi)

    # KPIリストのソート
    sort_map = {
        "週新入院患者数達成率（降順）": ('admissions_achievement', True),
        "日平均在院患者数（降順）": ('avg_daily_census', True),
        "診療科名（昇順）": ('dept_name', False)
    }
    key, rev = sort_map.get(sort_key, ('dept_name', False))
    dept_kpis.sort(key=lambda x: x.get(key) or 0, reverse=rev)

    # タイトルとカード表示
    st.markdown(f"**{period_desc}** の診療科別パフォーマンス")
    st.markdown("---")
    render_performance_cards(dept_kpis, columns_count)


def create_department_performance_tab():
    display_department_performance_dashboard()
