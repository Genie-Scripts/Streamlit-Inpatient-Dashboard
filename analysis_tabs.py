# analysis_tabs.py （修正後のコード）

import streamlit as st
import pandas as pd
import plotly.express as px
import logging
from config import EXCLUDED_WARDS
from utils import get_display_name_for_dept, get_ward_display_name, initialize_all_mappings
from unified_filters import apply_unified_filters, get_unified_filter_summary

logger = logging.getLogger(__name__)

# データテーブル表示に関連する関数のみを残す

def create_data_tables_tab():
    """データテーブルタブのメイン関数"""
    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ入力」タブでデータを読み込んでください。")
        return

    df_original = st.session_state.get('df')
    if df_original is None or df_original.empty:
        st.error("分析対象のデータがありません。")
        return

    df_filtered = apply_unified_filters(df_original)
    filter_summary = get_unified_filter_summary()
    st.info(f"🔍 統一フィルター適用中: {filter_summary}")

    if df_filtered.empty:
        st.warning("選択されたフィルター条件にマッチするデータがありません。")
        return

    # department_performance_tab.py と ward_performance_tab.py に機能が分離されたため、
    # このタブは将来的に削除、またはシンプルな表示に戻すことを推奨します。
    # ここでは、簡潔な表示のみ行います。
    st.subheader("データテーブル表示")
    st.caption("詳細な分析は「診療科別パフォーマンス」「病棟別パフォーマンス」タブをご利用ください。")
    st.dataframe(df_filtered, use_container_width=True)

# create_individual_analysis_section やその他の関数はすべて削除します。