# app.py (超最小構成テストバージョン)
import streamlit as st
import pandas as pd
import numpy as np
# integrated_preprocessing.py が @st.cache_data 無効化された状態でインポートされるようにする
from integrated_preprocessing import integrated_preprocess_data 
import logging
import traceback

# ロギング設定 (他のファイルと同様)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__) # app.py 用のロガー

# ページ設定は残しても良いでしょう
st.set_page_config(page_title="APP 超最小テスト", layout="wide")

def main():
    st.title("`app.py` 超最小構成での `integrated_preprocess_data` テスト")

    # integrated_preprocess_data に渡すためのテスト入力データ
    # (test_preprocessor_output.py で成功したデータと同様のものを使用)
    st.subheader("1. テスト用固定入力データ")
    sample_data_raw_dict = {
        "病棟コード": ["A", "A", "B", "B", "C"],
        "診療科名": ["内科", "内科", "外科", "外科", "内科"],
        "日付": pd.to_datetime(["2023-01-01", "2023-01-01", "2023-01-02", "2023-01-02", "2023-01-03"]),
        "在院患者数": [10, '-', 15, '20', 5],
        "入院患者数": [1, 0, 2, 1, 0],
        "緊急入院患者数": [0, 0, 1, 0, 1],
        "退院患者数": [1, 0, 1, 1, 0],
        "死亡患者数": [0, 0, 0, 0, 0]
    }
    df_raw = pd.DataFrame(sample_data_raw_dict)
    for col in ["在院患者数", "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"]:
        if col in df_raw.columns: df_raw[col] = df_raw[col].astype(object)

    st.write("入力する固定ダミーデータ (`df_raw`):")
    st.dataframe(df_raw)

    target_data_for_test = pd.DataFrame() # ダミーの目標値データ

    st.subheader("2. `integrated_preprocess_data` の実行")
    try:
        # integrated_preprocess_data を呼び出し (@st.cache_data は無効化されていること)
        processed_df, validation_results = integrated_preprocess_data(df_raw.copy(), target_data_df=target_data_for_test)
        st.success("`integrated_preprocess_data` の呼び出しは完了しました（Python例外なし）。")

        if validation_results:
            st.write("`integrated_preprocess_data` からの検証結果:")
            st.json(validation_results)

        if processed_df is not None and not processed_df.empty:
            st.subheader("3. `integrated_preprocess_data` から返されたデータフレーム (`processed_df`)")

            logger.info("超最小app.py: Processed DataFrame を受け取りました。")
            if "入院患者数（在院）" in processed_df.columns:
                log_msg_dtype = f"Processed df - '入院患者数（在院）' dtype: {processed_df['入院患者数（在院）'].dtype}"
                log_msg_unique = f"Processed df - '入院患者数（在院）' unique: {processed_df['入院患者数（在院）'].unique()[:20]}"
                logger.info(log_msg_dtype)
                logger.info(log_msg_unique)
                st.write(log_msg_dtype)
                st.write(log_msg_unique)
            else:
                logger.warning("超最小app.py: '入院患者数（在院）' 列が processed_df に見つかりません。")
                st.warning("'入院患者数（在院）' 列が processed_df に見つかりません。")

            st.subheader("4. `processed_df` 全体を `st.dataframe` で表示テスト")
            try:
                st.dataframe(processed_df) # ★★★ これが核心のテスト ★★★
                st.success("超最小app.py: `processed_df` の `st.dataframe` での表示に成功しました！")
                logger.info("超最小app.py: `processed_df` の `st.dataframe` での表示に成功しました！")
            except Exception as e_display:
                st.error(f"超最小app.py: `processed_df` の `st.dataframe` 表示中にエラーが発生: {e_display}")
                logger.error(f"超最小app.py: `processed_df` の `st.dataframe` 表示中にエラー: {e_display}", exc_info=True)
                st.code(traceback.format_exc())
        elif processed_df is not None and processed_df.empty:
            st.warning("`processed_df` は空のデータフレームです。")
        else:
            st.error("`processed_df` が None です。")

    except Exception as e_preprocess_main:
        st.error(f"`integrated_preprocess_data` の呼び出し中またはその後の処理でPython例外が発生: {e_preprocess_main}")
        logger.error(f"`integrated_preprocess_data` 呼び出し中または後続処理でPython例外: {e_preprocess_main}", exc_info=True)
        st.code(traceback.format_exc())

if __name__ == "__main__":
    main()