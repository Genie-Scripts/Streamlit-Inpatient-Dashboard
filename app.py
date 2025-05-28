import streamlit as st
import pandas as pd
import numpy as np
# integrated_preprocessing.py が同じディレクトリにあるか、
# Pythonがインポートできるようにパスが通っている必要があります。
from integrated_preprocessing import integrated_preprocess_data 
import logging
import traceback # traceback をインポート

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

st.set_page_config(layout="wide") # 全体的なレイアウトを合わせる
st.title("`integrated_preprocess_data` 出力テスト")

# 1. `integrated_preprocess_data` に渡すための最小限の入力データを作成
#    実際のデータでエラーを引き起こす可能性のあるパターンをできるだけ模倣します。
#    特に「在院患者数」列に '-' を含むデータを用意します。
st.subheader("1. テスト用入力データ")
sample_data_raw_dict = {
    "病棟コード": ["A", "A", "B", "B", "C"],
    "診療科名": ["内科", "内科", "外科", "外科", "内科"],
    "日付": pd.to_datetime(["2023-01-01", "2023-01-01", "2023-01-02", "2023-01-02", "2023-01-03"]),
    "在院患者数": [10, '-', 15, '20', 5],  # '-' を含む。これが「入院患者数（在院）」に影響
    "入院患者数": [1, 0, 2, 1, 0],
    "緊急入院患者数": [0, 0, 1, 0, 1],
    "退院患者数": [1, 0, 1, 1, 0],
    "死亡患者数": [0, 0, 0, 0, 0]
    # integrated_preprocess_data が期待する他の必須列があれば、最小限で追加してください。
    # もし target_data_df が処理に影響する場合、それも最小限のダミーで用意します。
}
dummy_df_raw = pd.DataFrame(sample_data_raw_dict)
# 入力データの型を object にして、より実際の状況に近づける
for col in ["在院患者数", "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"]:
    if col in dummy_df_raw.columns:
        dummy_df_raw[col] = dummy_df_raw[col].astype(object)
st.write("入力するダミーデータ (`dummy_df_raw`):")
st.dataframe(dummy_df_raw)

# target_data_df の準備 (もし必須でなければ None や空のDataFrameでOK)
# もし目標値ファイルの内容が診療科の集約などに影響する場合、
# その挙動を再現できる最小限のダミー target_data_df を作成してください。
# 例: target_data_for_test = pd.DataFrame({'部門コード': ['内科', '外科'], '部門名': ['内科系', '外科系']})
target_data_for_test = pd.DataFrame() # ここでは空のDataFrameを使用

st.subheader("2. `integrated_preprocess_data` の実行")
# integrated_preprocess_data を呼び出し
# エラーハンドリングのため try-except で囲む
try:
    processed_df, validation_results = integrated_preprocess_data(dummy_df_raw.copy(), target_data_df=target_data_for_test)
    st.success("`integrated_preprocess_data` の呼び出しは完了しました（Python例外なし）。")

    if validation_results:
        st.write("`integrated_preprocess_data` からの検証結果:")
        st.json(validation_results)

    if processed_df is not None and not processed_df.empty:
        st.subheader("3. `integrated_preprocess_data` から返されたデータフレーム (`processed_df`)")
        
        logger.info("最小テストアプリ: Processed DataFrame を受け取りました。")
        if "入院患者数（在院）" in processed_df.columns:
            log_msg_dtype = f"Processed df - '入院患者数（在院）' dtype: {processed_df['入院患者数（在院）'].dtype}"
            log_msg_unique = f"Processed df - '入院患者数（在院）' unique: {processed_df['入院患者数（在院）'].unique()[:20]}"
            logger.info(log_msg_dtype)
            logger.info(log_msg_unique)
            st.write(log_msg_dtype)
            st.write(log_msg_unique)
        else:
            logger.warning("最小テストアプリ: '入院患者数（在院）' 列が processed_df に見つかりません。")
            st.warning("'入院患者数（在院）' 列が processed_df に見つかりません。")
        
        st.write("`processed_df` の全列名:", processed_df.columns.tolist())
        # st.info("`processed_df.info()` の内容はコンソールに出力されます。")
        # processed_df.info() # 詳細情報をコンソールに出力

        st.subheader("4. `processed_df` 全体を `st.dataframe` で表示テスト")
        try:
            st.dataframe(processed_df) # ★★★ これが核心のテスト ★★★
            st.success("最小テストアプリ: `processed_df` の `st.dataframe` での表示に成功しました！")
            logger.info("最小テストアプリ: `processed_df` の `st.dataframe` での表示に成功しました！")
        except Exception as e_display: # PyArrowエラーもここでキャッチされるはず
            st.error(f"最小テストアプリ: `processed_df` の `st.dataframe` 表示中にエラーが発生: {e_display}")
            logger.error(f"最小テストアプリ: `processed_df` の `st.dataframe` 表示中にエラー: {e_display}", exc_info=True)
            st.code(traceback.format_exc()) # エラー詳細を画面にも表示
    elif processed_df is not None and processed_df.empty:
        st.warning("`processed_df` は空のデータフレームです。")
        logger.warning("最小テストアプリ: `processed_df` は空のデータフレームです。")
    else:
        st.error("`processed_df` が None です。")
        logger.error("最小テストアプリ: `processed_df` が None です。")

except Exception as e_preprocess:
    st.error(f"`integrated_preprocess_data` の呼び出し中にPython例外が発生: {e_preprocess}")
    logger.error(f"`integrated_preprocess_data` の呼び出し中にPython例外: {e_preprocess}", exc_info=True)
    st.code(traceback.format_exc())