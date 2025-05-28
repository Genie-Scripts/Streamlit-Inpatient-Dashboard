
        # --- 数値列の徹底処理（全データ型対応・欠損防止） ---
        numeric_cols_to_process = [
            "在院患者数", "入院患者数", "緊急入院患者数",
            "退院患者数", "死亡患者数", "入院患者数（在院）"
        ]

        for col in numeric_cols_to_process:
            if col in df_processed.columns:
                df_processed[col] = (
                    df_processed[col]
                    .astype(str)
                    .replace(['-', '', ' ', 'nan', 'NaN', 'N/A', 'None'], np.nan)
                    .astype(float)
                    .fillna(0.0)
                )
            else:
                df_processed[col] = 0.0
                validation_results["warnings"].append(f"数値列'{col}'が存在しなかったため、0.0で補完されました。")
