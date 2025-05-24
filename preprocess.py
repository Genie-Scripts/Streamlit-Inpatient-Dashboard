import streamlit as st  # この行を追加
import pandas as pd
import jpholiday
import gc

@st.cache_data(ttl=3600, show_spinner=False)
def preprocess_data(df):
    """
    より効率的なデータ前処理（不要な列を早期に削除）
    エラーハンドリングと検証を強化
    """
    try:
        # 入力データのバリデーション
        if df is None or df.empty:
            raise ValueError("入力データが空です")
            
        # 必要な列のみを選択
        required_cols = ["病棟コード", "診療科名", "日付", "在院患者数", 
                        "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"]
        
        # 最低限必要な列のチェック
        essential_cols = ["病棟コード", "診療科名", "日付"]
        missing_essentials = [col for col in essential_cols if col not in df.columns]
        if missing_essentials:
            raise ValueError(f"必須列が不足しています: {', '.join(missing_essentials)}")
        
        # 利用可能な列のみを選択（すべての必須列が存在するとは限らない）
        available_cols = [col for col in required_cols if col in df.columns]
        df = df[available_cols].copy()
        
        # 必須列がない行を削除
        df = df.dropna(subset=["病棟コード", "診療科名"])
        
        # 日付の変換 - より効率的な変換方法
        df["日付"] = pd.to_datetime(df["日付"], errors="coerce")
        df = df.dropna(subset=["日付"])
        
        if df.empty:
            raise ValueError("前処理後にデータが空になりました")
        
        # 列計算の最適化 - 存在する場合のみ計算
        if "退院患者数" in df.columns and "死亡患者数" in df.columns:
            df["退院患者数"] = df["退院患者数"] + df["死亡患者数"]
        
        if "入院患者数" in df.columns and "緊急入院患者数" in df.columns:
            df["新入院患者数"] = df["入院患者数"] + df["緊急入院患者数"]
        
        # 列名の変更
        if "在院患者数" in df.columns:
            df = df.rename(columns={"在院患者数": "入院患者数（在院）"})
        
        # "入院患者数（在院）"列が存在するか確認
        if "入院患者数（在院）" not in df.columns:
            raise ValueError("'入院患者数（在院）'列が作成できませんでした。'在院患者数'列が必要です。")
        
        # メモリ解放
        gc.collect()
        
        return df
        
    except Exception as e:
        print(f"データ前処理エラー: {str(e)}")
        st.error(f"データの前処理中にエラーが発生しました: {str(e)}")
        # 空のデータフレームではなくNoneを返すと、呼び出し元でエラーチェックが容易になる
        return None
        
def add_weekday_flag(df):
    """
    平日/休日の判定フラグを追加する
    
    Parameters:
    -----------
    df : pd.DataFrame
        フラグを追加するデータフレーム
    
    Returns:
    --------
    pd.DataFrame
        フラグが追加されたデータフレーム
    """
    def is_holiday(date):
        return (
            date.weekday() >= 5 or  # 土日
            jpholiday.is_holiday(date) or  # 祝日
            (date.month == 12 and date.day >= 29) or  # 年末
            (date.month == 1 and date.day <= 3)  # 年始
        )
    
    # 平日/休日フラグを追加
    df["平日判定"] = df["日付"].apply(lambda x: "休日" if is_holiday(x) else "平日")
    
    return df
def validate_data(df):
    """
    データの検証を行い、異常値や欠損値を確認する
    
    Parameters:
    -----------
    df : pd.DataFrame
        検証するデータフレーム
    
    Returns:
    --------
    dict
        検証結果を含む辞書
    """
    validation_results = {
        "is_valid": True,
        "warnings": [],
        "errors": []
    }
    
    try:
        # 必須列の存在確認
        required_columns = ["病棟コード", "診療科名", "日付", "入院患者数（在院）"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            validation_results["is_valid"] = False
            validation_results["errors"].append(f"必須列が不足しています: {', '.join(missing_columns)}")
            return validation_results
        
        # データサイズの確認
        if df.empty:
            validation_results["is_valid"] = False
            validation_results["errors"].append("データが空です")
            return validation_results
        
        # 日付範囲の確認
        date_range = df["日付"].max() - df["日付"].min()
        if date_range.days < 30:
            validation_results["warnings"].append(f"データ期間が短いです ({date_range.days}日間)。最低30日以上のデータを推奨します。")
        
        # 異常値のチェック - 負の値がないか
        for col in ["入院患者数（在院）", "新入院患者数", "退院患者数"]:
            if col in df.columns and (df[col] < 0).any():
                negative_count = (df[col] < 0).sum()
                validation_results["warnings"].append(f"{col}に負の値が{negative_count}件あります。")
        
        # 外れ値のチェック - 平均から大きく離れている値
        for col in ["入院患者数（在院）", "新入院患者数", "退院患者数"]:
            if col in df.columns:
                mean = df[col].mean()
                std = df[col].std()
                # 平均から3標準偏差以上離れている値を外れ値とする
                outliers = df[abs(df[col] - mean) > 3 * std]
                if not outliers.empty:
                    validation_results["warnings"].append(f"{col}に外れ値が{len(outliers)}件あります。")
        
        return validation_results
        
    except Exception as e:
        validation_results["is_valid"] = False
        validation_results["errors"].append(f"データ検証中にエラーが発生しました: {str(e)}")
        return validation_results
        
def add_patient_days_calculation(df):
    """
    延べ在院日数（人日）を計算してデータフレームに追加する
    
    Parameters:
    -----------
    df : pd.DataFrame
        病院データのデータフレーム
        
    Returns:
    --------
    pd.DataFrame
        延べ在院日数（人日）列が追加されたデータフレーム
    """
    df = df.copy()
    
    # 必要な列の存在確認
    required_cols = ['入院患者数（在院）', '退院患者数']
    available_cols = [col for col in required_cols if col in df.columns]
    
    if len(available_cols) == 0:
        print("警告: 延べ在院日数の計算に必要な列が見つかりません")
        df['延べ在院日数（人日）'] = 0
        return df
    
    # 延べ在院日数（人日）の計算
    # = 在院患者数 + 退院患者数（退院日も算定対象のため）
    if '入院患者数（在院）' in df.columns and '退院患者数' in df.columns:
        df['延べ在院日数（人日）'] = df['入院患者数（在院）'] + df['退院患者数']
        print("延べ在院日数（人日）を計算しました: 在院患者数 + 退院患者数")
    elif '入院患者数（在院）' in df.columns:
        # 退院患者数がない場合のフォールバック
        df['延べ在院日数（人日）'] = df['入院患者数（在院）']
        print("警告: 退院患者数データがないため、在院患者数のみで計算しています")
    else:
        df['延べ在院日数（人日）'] = 0
        print("エラー: 在院患者数データが見つかりません")
    
    # 負の値をゼロに修正
    df['延べ在院日数（人日）'] = df['延べ在院日数（人日）'].clip(lower=0)
    
    # データ型を整数に変換
    df['延べ在院日数（人日）'] = df['延べ在院日数（人日）'].astype(int)
    
    return df


def validate_patient_days_data(df):
    """
    延べ在院日数データの妥当性を検証する
    
    Parameters:
    -----------
    df : pd.DataFrame
        検証対象のデータフレーム
        
    Returns:
    --------
    dict
        検証結果の辞書
    """
    validation_results = {
        "is_valid": True,
        "warnings": [],
        "errors": [],
        "summary": {}
    }
    
    if '延べ在院日数（人日）' not in df.columns:
        validation_results["errors"].append("延べ在院日数（人日）列が存在しません")
        validation_results["is_valid"] = False
        return validation_results
    
    # 基本統計
    patient_days = df['延べ在院日数（人日）']
    validation_results["summary"] = {
        "total_patient_days": patient_days.sum(),
        "avg_daily_patient_days": patient_days.mean(),
        "max_daily_patient_days": patient_days.max(),
        "min_daily_patient_days": patient_days.min(),
        "zero_days_count": (patient_days == 0).sum(),
        "data_days": len(patient_days)
    }
    
    # 異常値のチェック
    if patient_days.max() > 1000:  # 1日1000人日は異常
        validation_results["warnings"].append(
            f"異常に大きな値が検出されました: 最大値 {patient_days.max()}"
        )
    
    if patient_days.min() < 0:  # 負の値は異常
        validation_results["errors"].append("負の延べ在院日数が検出されました")
        validation_results["is_valid"] = False
    
    # ゼロが多すぎる場合の警告
    zero_ratio = (patient_days == 0).sum() / len(patient_days)
    if zero_ratio > 0.1:  # 10%以上がゼロ
        validation_results["warnings"].append(
            f"延べ在院日数がゼロの日が多く検出されました: {zero_ratio:.1%}"
        )
    
    # 在院患者数との整合性チェック
    if '入院患者数（在院）' in df.columns:
        census_data = df['入院患者数（在院）']
        if (patient_days < census_data).any():
            validation_results["warnings"].append(
                "延べ在院日数が在院患者数より少ない日があります（退院患者数が負の可能性）"
            )
    
    return validation_results


# preprocess.py のメイン処理関数に統合
def preprocess_data(df_raw):
    """
    データの前処理を行う（既存関数の修正版）
    """
    # 既存の前処理...
    df = df_raw.copy()
    
    # 日付列の処理
    if '日付' in df.columns:
        df['日付'] = pd.to_datetime(df['日付'])
    
    # 数値列の処理
    numeric_columns = [
        '在院患者数', '入院患者数', '緊急入院患者数', 
        '退院患者数', '死亡患者数'
    ]
    
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 標準列名への変換
    column_mapping = {
        '在院患者数': '入院患者数（在院）',
        '入院患者数': '新入院患者数',
        # 他のマッピング...
    }
    
    df = df.rename(columns=column_mapping)
    
    # 総入院患者数、総退院患者数の計算（既存処理）
    if '新入院患者数' in df.columns and '緊急入院患者数' in df.columns:
        df['総入院患者数'] = df['新入院患者数'] + df['緊急入院患者数']
    elif '新入院患者数' in df.columns:
        df['総入院患者数'] = df['新入院患者数']
    
    if '退院患者数' in df.columns and '死亡患者数' in df.columns:
        df['総退院患者数'] = df['退院患者数'] + df['死亡患者数']
    elif '退院患者数' in df.columns:
        df['総退院患者数'] = df['退院患者数']
    
    # ★ 延べ在院日数（人日）の計算を追加 ★
    df = add_patient_days_calculation(df)
    
    # データ検証
    validation_results = validate_patient_days_data(df)
    
    # 検証結果をセッション状態に保存
    if 'st' in globals():
        import streamlit as st
        st.session_state.patient_days_validation = validation_results
        
        # 警告やエラーがあればログ出力
        for warning in validation_results["warnings"]:
            print(f"警告: {warning}")
        for error in validation_results["errors"]:
            print(f"エラー: {error}")
    
    return df


def get_patient_days_summary(df, start_date=None, end_date=None):
    """
    延べ在院日数の集計サマリーを取得する
    
    Parameters:
    -----------
    df : pd.DataFrame
        データフレーム
    start_date : datetime, optional
        集計開始日
    end_date : datetime, optional
        集計終了日
        
    Returns:
    --------
    dict
        集計結果の辞書
    """
    if '延べ在院日数（人日）' not in df.columns:
        return {"error": "延べ在院日数（人日）列が存在しません"}
    
    # 期間フィルタ
    df_filtered = df.copy()
    if start_date and end_date:
        df_filtered = df_filtered[
            (df_filtered['日付'] >= pd.to_datetime(start_date)) & 
            (df_filtered['日付'] <= pd.to_datetime(end_date))
        ]
    
    if df_filtered.empty:
        return {"error": "指定期間にデータがありません"}
    
    # 全体集計
    total_patient_days = df_filtered['延べ在院日数（人日）'].sum()
    avg_daily_patient_days = df_filtered['延べ在院日数（人日）'].mean()
    days_count = len(df_filtered)
    
    summary = {
        "period": {
            "start_date": df_filtered['日付'].min().strftime('%Y-%m-%d'),
            "end_date": df_filtered['日付'].max().strftime('%Y-%m-%d'),
            "days_count": days_count
        },
        "total_patient_days": total_patient_days,
        "avg_daily_patient_days": round(avg_daily_patient_days, 1),
        "max_daily_patient_days": df_filtered['延べ在院日数（人日）'].max(),
        "min_daily_patient_days": df_filtered['延べ在院日数（人日）'].min()
    }
    
    # 診療科別集計（可能な場合）
    if '診療科名' in df_filtered.columns:
        dept_summary = df_filtered.groupby('診療科名')['延べ在院日数（人日）'].sum().to_dict()
        summary["by_department"] = dept_summary
    
    # 病棟別集計（可能な場合）
    if '病棟コード' in df_filtered.columns:
        ward_summary = df_filtered.groupby('病棟コード')['延べ在院日数（人日）'].sum().to_dict()
        summary["by_ward"] = ward_summary
    
    return summary