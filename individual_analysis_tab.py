# individual_analysis_tab.py (このテストコードに完全に置き換えてください)
import streamlit as st
import pandas as pd

def display_individual_analysis_tab(df):
    """
    インポートが成功するかを確認するための最小限のテスト関数です。
    """
    st.header("📊 個別分析 (テストモード)")
    st.success("✅ 個別分析モジュールのインポートに成功しました！")
    st.balloons() # 成功を分かりやすくするため風船を飛ばします
    
    st.info("この画面が表示された場合、問題の原因は元の individual_analysis_tab.py のコード内部にあります。")
    
    if df is not None and not df.empty:
        st.write(f"受け取ったデータの行数: {len(df)}行")
        st.dataframe(df.head())
    else:
        st.warning("データは受け取っていません。")