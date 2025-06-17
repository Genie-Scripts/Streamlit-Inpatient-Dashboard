# analysis_tabs.py （最終的な修正コード）

import streamlit as st
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def create_data_tables_tab():
    """データテーブルタブのメイン関数"""
    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ入力」タブでデータを読み込んでください。")
        return

    df_original = st.session_state.get('df')
    if df_original is None or df_original.empty:
        st.error("分析対象のデータがありません。")
        return

    # 統一フィルターをインポートして適用
    try:
        from unified_filters import apply_unified_filters, get_unified_filter_summary
        df_filtered = apply_unified_filters(df_original)
        filter_summary = get_unified_filter_summary()
        st.info(f"🔍 統一フィルター適用中: {filter_summary}")
    except ImportError:
        st.error("フィルター機能の読み込みに失敗しました。")
        df_filtered = df_original # フォールバック

    if df_filtered.empty:
        st.warning("選択されたフィルター条件にマッチするデータがありません。")
        return

    st.subheader("データテーブル表示")
    st.caption("詳細な分析は各分析タブをご利用ください。")
    st.dataframe(df_filtered, use_container_width=True)