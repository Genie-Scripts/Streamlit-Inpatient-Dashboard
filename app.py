import streamlit as st
import pandas as pd
import numpy as np
import pyarrow # PyArrowを直接使う場合に備えてインポート

st.title("Minimal Arrow Conversion Test")

# ケース1: ログでは問題ないとされるデータフレームを模倣
st.subheader("ケース1: ログで問題ないとされたデータフレーム")
data1 = {'入院患者数（在院）': [1.0, 15.0, 2.0, 3.0, 0.0, np.nan]} # NaNも含むケース
df1 = pd.DataFrame(data1)
df1['入院患者数（在院）'] = pd.to_numeric(df1['入院患者数（在院）'], errors='coerce').fillna(0.0)
df1['入院患者数（在院）'] = df1['入院患者数（在院）'].astype('float64')
st.write("df1 の情報:", df1.info())
st.write("df1['入院患者数（在院）'].unique():", df1['入院患者数（在院）'].unique())
try:
    st.write("df1 を st.dataframe で表示:")
    st.dataframe(df1) # これでエラーが出るか？
    st.success("ケース1: df1 の表示成功")
except Exception as e:
    st.error(f"ケース1: df1 の表示でエラー: {e}")
    st.code(traceback.format_exc())

st.divider()

# ケース2: エラーメッセージにある '-' を含むデータから変換
st.subheader("ケース2: '-' を含むデータから変換")
data2_raw = {'入院患者数（在院）': ['1', '15', '-', '3', '0']}
df2 = pd.DataFrame(data2_raw)
st.write("df2 (raw) の情報:", df2.info())
st.write("df2['入院患者数（在院）'].unique() (raw):", df2['入院患者数（在院）'].unique())
try:
    # わざとエラーを起こす (変換前)
    st.write("df2 (raw) を st.dataframe で表示（エラー期待）:")
    st.dataframe(df2)
    st.warning("ケース2: df2 (raw) がエラーなく表示された（予期せぬ動作）")
except Exception as e:
    st.info(f"ケース2: df2 (raw) の表示で期待通りのエラー: {e}") # ここで PyArrowエラーが出るはず

df2['入院患者数（在院）'] = pd.to_numeric(df2['入院患者数（在院）'], errors='coerce').fillna(0.0)
df2['入院患者数（在院）'] = df2['入院患者数（在院）'].astype('float64')
st.write("df2 (cleaned) の情報:", df2.info())
st.write("df2['入院患者数（在院）'].unique() (cleaned):", df2['入院患者数（在院）'].unique())
try:
    st.write("df2 (cleaned) を st.dataframe で表示:")
    st.dataframe(df2) # これでエラーが出るか？
    st.success("ケース2: df2 (cleaned) の表示成功")
except Exception as e:
    st.error(f"ケース2: df2 (cleaned) の表示でエラー: {e}")
    st.code(traceback.format_exc())