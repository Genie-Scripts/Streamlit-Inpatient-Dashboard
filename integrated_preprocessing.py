import pandas as pd
import numpy as np
import streamlit as st
import jpholiday
import gc
import time
import hashlib
from io import BytesIO
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import logging
from utils import create_dept_mapping_table

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- ここから preprocess.py より移植する関数群 ---

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
    df_processed = df.copy()
    
    required_cols = ['入院患者数（在院）', '退院患者数']
    available_cols = [col for col in required_cols if col in df_processed.columns]
    
    if '入院患者数（在院）' not in available_cols:
        logger.warning("延べ在院日数の計算に必要な「入院患者数（在院）」列が見つかりません。")
        df_processed['延べ在院日数（人日）'] = 0
        return df_processed
    
    if '退院患者数' in available_cols:
        df_processed['延べ在院日数（人日）'] = df_processed['入院患者数（在院）'] + df_processed['退院患者数']
        logger.info("延べ在院日数（人日）を計算しました: 入院患者数（在院） + 退院患者数")
    else:
        logger.warning("延べ在院日数の計算に必要な「退院患者数」列が見つかりません。在院患者数のみで計算します。")
        df_processed['延べ在院日数（人日）'] = df_processed['入院患者数（在院）']
    
    df_processed['延べ在院日数（人日）'] = df_processed['延べ在院日数（人日）'].clip(lower=0)
    df_processed['延べ在院日数（人日）'] = df_processed['延べ在院日数（人日）'].astype(int)
    
    return df_processed

def validate_patient_days_data(df):
    """
    延べ在院日数データの妥当性を検証する
    """
    validation_sub_results = {
        "warnings": [],
        "errors": [],
        "summary": {}
    }
    
    if '延べ在院日数（人日）' not in df.columns:
        validation_sub_results["errors"].append("延べ在院日数（人日）列が存在しません。")
        return validation_sub_results
    
    patient_days = df['延べ在院日数（人日）']
    if patient_days.empty:
        validation_sub_results["warnings"].append("延べ在院日数（人日）データが空です。")
        return validation_sub_results

    validation_sub_results["summary"] = {
        "total_patient_days": patient_days.sum(),
        "avg_daily_patient_days": patient_days.mean(),
        "max_daily_patient_days": patient_days.max(),
        "min_daily_patient_days": patient_days.min(),
        "zero_days_count": (patient_days == 0).sum(),
        "data_days": len(patient_days)
    }
    
    if pd.notna(patient_days.max()) and patient_days.max() > 1000:
        validation_sub_results["warnings"].append(
            f"延べ在院日数（人日）に異常に大きな値が検出されました: 最大値 {patient_days.max()}"
        )
    
    if pd.notna(patient_days.min()) and patient_days.min() < 0:
        validation_sub_results["errors"].append("延べ在院日数（人日）に負の値が検出されました。")
    
    if len(patient_days) > 0:
        zero_ratio = (patient_days == 0).sum() / len(patient_days)
        if zero_ratio > 0.1:
            validation_sub_results["warnings"].append(
                f"延べ在院日数（人日）がゼロの日が多く検出されました: {zero_ratio:.1%}"
            )
    
    if '入院患者数（在院）' in df.columns:
        census_data = df['入院患者数（在院）']
        if not census_data.empty and not patient_days.empty and (patient_days < census_data).any():
            validation_sub_results["warnings"].append(
                "延べ在院日数（人日）が入院患者数（在院）より少ない日があります。退院患者数が負になっているか、計算ロジックの確認が必要です。"
            )
    
    return validation_sub_results

def validate_general_data(df):
    """
    データの一般的な検証を行い、異常値や欠損値を確認する
    """
    validation_sub_results = {
        "warnings": [],
        "errors": []
    }
    
    required_cols_for_validation = ["病棟コード", "診療科名", "日付", "入院患者数（在院）"]
    missing_cols = [col for col in required_cols_for_validation if col not in df.columns]
    
    if missing_cols:
        validation_sub_results["errors"].append(f"一般的なデータ検証に必要な列が不足しています: {', '.join(missing_cols)}")
        return validation_sub_results
        
    if df.empty:
        validation_sub_results["errors"].append("一般的なデータ検証の対象データが空です。")
        return validation_sub_results
        
    if '日付' in df.columns and not df['日付'].empty:
        min_date = df["日付"].min()
        max_date = df["日付"].max()
        if pd.notna(min_date) and pd.notna(max_date): # NaTでないことを確認
            date_range_days = (max_date - min_date).days
            if date_range_days < 30:
                validation_sub_results["warnings"].append(f"データ期間が短いです ({date_range_days}日間)。最低30日以上のデータを推奨します。")
        else:
            validation_sub_results["warnings"].append("日付データの最小値または最大値が無効です。期間の検証をスキップします。")

    cols_to_check_negative = ["入院患者数（在院）", "新入院患者数", "総退院患者数"]
    for col in cols_to_check_negative:
        if col in df.columns and not df[col].empty and pd.api.types.is_numeric_dtype(df[col]) and (df[col] < 0).any():
            negative_count = (df[col] < 0).sum()
            validation_sub_results["warnings"].append(f"列 '{col}' に負の値が {negative_count} 件あります。")
    
    cols_for_outlier_check = ["入院患者数（在院）", "新入院患者数", "総退院患者数"]
    for col in cols_for_outlier_check:
        if col in df.columns and not df[col].empty and pd.api.types.is_numeric_dtype(df[col]) and len(df[col].dropna()) > 1:
            mean = df[col].mean()
            std = df[col].std()
            if pd.notna(std) and std > 0:
                outliers = df[np.abs(df[col] - mean) > 3 * std]
                if not outliers.empty:
                    validation_sub_results["warnings"].append(f"列 '{col}' に外れ値の可能性があるデータが {len(outliers)} 件あります（3標準偏差外）。")
    
    return validation_sub_results

def get_patient_days_summary_integrated(df, start_date=None, end_date=None):
    """
    延べ在院日数の集計サマリーを取得する (integrated_preprocessing.py バージョン)
    """
    if df is None or df.empty:
        logger.warning("get_patient_days_summary_integrated: 入力データが空です。")
        return {"error": "入力データが空です。"}
    if '延べ在院日数（人日）' not in df.columns:
        logger.error("get_patient_days_summary_integrated: 延べ在院日数（人日）列が存在しません。")
        return {"error": "延べ在院日数（人日）列が存在しません。"}
    if '日付' not in df.columns:
        logger.error("get_patient_days_summary_integrated: 日付列が存在しません。")
        return {"error": "日付列が存在しません。"}
    
    df_filtered = df.copy()
    if start_date and end_date:
        try:
            start_date_ts = pd.to_datetime(start_date)
            end_date_ts = pd.to_datetime(end_date)
            # Ensure '日付' column is in datetime format for proper filtering
            if not pd.api.types.is_datetime64_any_dtype(df_filtered['日付']):
                df_filtered['日付'] = pd.to_datetime(df_filtered['日付'])
            df_filtered = df_filtered[
                (df_filtered['日付'] >= start_date_ts) & 
                (df_filtered['日付'] <= end_date_ts)
            ]
        except Exception as e:
            logger.error(f"get_patient_days_summary_integrated: 日付フィルタリングエラー: {e}")
            return {"error": f"日付フィルタリングエラー: {e}"}
    
    if df_filtered.empty:
        logger.info("get_patient_days_summary_integrated: 指定期間にデータがありません。")
        return {"error": "指定期間にデータがありません。"}
    
    patient_days_series = df_filtered['延べ在院日数（人日）']
    summary = {
        "period": {
            "start_date": df_filtered['日付'].min().strftime('%Y-%m-%d') if not df_filtered['日付'].empty and pd.notna(df_filtered['日付'].min()) else None,
            "end_date": df_filtered['日付'].max().strftime('%Y-%m-%d') if not df_filtered['日付'].empty and pd.notna(df_filtered['日付'].max()) else None,
            "days_count": df_filtered['日付'].nunique()
        },
        "total_patient_days": patient_days_series.sum(),
        "avg_daily_patient_days": round(patient_days_series.mean(), 1) if not patient_days_series.empty else 0,
        "max_daily_patient_days": patient_days_series.max() if not patient_days_series.empty else 0,
        "min_daily_patient_days": patient_days_series.min() if not patient_days_series.empty else 0
    }
    
    if '診療科名' in df_filtered.columns:
        try:
            dept_summary = df_filtered.groupby('診療科名')['延べ在院日数（人日）'].sum().to_dict()
            summary["by_department"] = dept_summary
        except Exception as e:
            logger.warning(f"診療科別集計エラー: {e}")
            summary["by_department"] = {}
    
    if '病棟コード' in df_filtered.columns:
        try:
            ward_summary = df_filtered.groupby('病棟コード')['延べ在院日数（人日）'].sum().to_dict()
            summary["by_ward"] = ward_summary
        except Exception as e:
            logger.warning(f"病棟別集計エラー: {e}")
            summary["by_ward"] = {}
            
    return summary

# --- 既存の integrated_preprocessing.py の関数 ---
def efficient_duplicate_check(df_raw): # 既存の関数
    start_time = time.time()
    if df_raw is None or df_raw.empty:
        logger.info("重複チェック: 空のデータフレームが渡されました")
        return df_raw
    initial_rows = len(df_raw)
    for col in df_raw.select_dtypes(include=['object']).columns:
        try:
            if df_raw[col].nunique() / len(df_raw) < 0.5:
                df_raw[col] = df_raw[col].astype('category')
                logger.debug(f"列 '{col}' をカテゴリ型に変換")
        except Exception as e:
            logger.warning(f"列 '{col}' の型変換エラー: {e}")
    try:
        mem_before = df_raw.memory_usage(deep=True).sum() / (1024 * 1024)
        df_processed = df_raw.drop_duplicates()
        mem_after = df_processed.memory_usage(deep=True).sum() / (1024 * 1024)
        rows_dropped = initial_rows - len(df_processed)
        del df_raw
        gc.collect()
        end_time = time.time()
        processing_time = end_time - start_time
        logger.info(f"重複チェック結果: 初期行数={initial_rows:,}, 削除行数={rows_dropped:,}, "
                   f"最終行数={len(df_processed):,}, 処理時間={processing_time:.2f}秒, "
                   f"メモリ削減={mem_before-mem_after:.2f}MB")
        if 'st' in globals() and hasattr(st, 'session_state'): # Streamlitコンテキストでのみ実行
            if 'performance_metrics' not in st.session_state:
                st.session_state.performance_metrics = {}
            st.session_state.performance_metrics['duplicate_check_time'] = processing_time
            st.session_state.performance_metrics['duplicate_rows_removed'] = rows_dropped
        return df_processed
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"重複チェック処理エラー: {e}\n{error_detail}")
        return df_raw # Return original if error

def add_weekday_flag(df): # 既存の関数
    """
    平日/休日の判定フラグを追加する
    """
    def is_holiday(date):
        return (
            date.weekday() >= 5 or
            jpholiday.is_holiday(date) or
            (date.month == 12 and date.day >= 29) or
            (date.month == 1 and date.day <= 3)
        )
    if '日付' not in df.columns:
        logger.error("add_weekday_flag: '日付'列が見つかりません。")
        return df # またはエラーを発生させる

    df_copy = df.copy() # 元のDataFrameを変更しないようにコピー
    # Ensure '日付' is datetime
    if not pd.api.types.is_datetime64_any_dtype(df_copy['日付']):
        df_copy['日付'] = pd.to_datetime(df_copy['日付'], errors='coerce')
        # Drop rows where date conversion failed
        df_copy.dropna(subset=['日付'], inplace=True)

    df_copy["平日判定"] = df_copy["日付"].apply(lambda x: "休日" if is_holiday(x) else "平日")
    return df_copy


# --- integrated_preprocess_data 関数の修正箇所 ---
# @st.cache_data(ttl=3600, show_spinner=False) # キャッシュデコレータは維持
def integrated_preprocess_data(df: pd.DataFrame, target_data_df: pd.DataFrame = None):
    start_time = time.time()
    validation_results = {
        "is_valid": True,
        "warnings": [],
        "errors": [],
        "info": [],
        "summaries": {}
    }

    major_departments_list = []
    dept_name_to_code = {}

    if target_data_df is not None and not target_data_df.empty and '部門コード' in target_data_df.columns:
        potential_major_depts = target_data_df['部門コード'].astype(str).unique()
        # 部門名も診療科名の参照候補に含める（両方混在ケースに備える）
        if '部門名' in target_data_df.columns:
            potential_major_depts_from_name = target_data_df['部門名'].astype(str).unique()
            potential_major_depts = np.union1d(potential_major_depts, potential_major_depts_from_name)
            # マッピング用（診療科名→部門名 or コード）の対応表を作成
            for _, row in target_data_df.iterrows():
                code = str(row.get('部門コード', '')).strip()
                name = str(row.get('部門名', '')).strip()
                if name:
                    dept_name_to_code[name] = code  # 診療科名として部門名が出現する場合
                if code:
                    dept_name_to_code[code] = name  # コードで出てきた場合

        # 実データの診療科名と、部門コード/部門名のどちらとも突き合わせ
        if '診療科名' in df.columns:
            actual_depts_in_df = df['診療科名'].astype(str).unique() if df is not None and not df.empty else []
            # major_departments_listは、診療科名がpotential_major_deptsに含まれるものすべて
            major_departments_list = [dept for dept in actual_depts_in_df if dept in potential_major_depts]
            # さらに、診療科名が「部門名→部門コード」にマッピングできる場合も主要診療科とする
            if dept_name_to_code:
                for dept in actual_depts_in_df:
                    mapped_code = dept_name_to_code.get(dept)
                    if mapped_code and (mapped_code in potential_major_depts):
                        major_departments_list.append(dept)
                # 重複を排除
                major_departments_list = list(set(major_departments_list))

        if not major_departments_list and len(potential_major_depts) > 0:
            major_departments_list = list(potential_major_depts)
            validation_results["warnings"].append(
                "目標設定ファイルの部門名・コードが実データの診療科名と一致しなかったため、目標設定ファイル上の全診療科を主要診療科として扱います。"
            )
        if not major_departments_list:
            validation_results["warnings"].append("目標設定ファイルから主要診療科リストを特定できませんでした。")
    else:
        validation_results["warnings"].append("目標設定ファイルが提供されなかったか、'部門コード'列がありません。全ての診療科を「その他」として扱います。")

    try:
        if df is None or df.empty:
            validation_results["is_valid"] = False
            validation_results["errors"].append("入力データが空です。")
            return None, validation_results

        expected_cols = ["病棟コード", "診療科名", "日付", "在院患者数",
                         "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"]
        available_cols = [col for col in df.columns if col in expected_cols]
        df_processed = df[available_cols].copy()

        initial_rows = len(df_processed)
        df_processed.dropna(subset=['病棟コード'], inplace=True)
        rows_dropped_due_to_ward_nan = initial_rows - len(df_processed)
        if rows_dropped_due_to_ward_nan > 0:
            validation_results["warnings"].append(
                f"「病棟コード」が欠損している行が {rows_dropped_due_to_ward_nan} 件ありました。これらの行は除外されました。"
            )
        
        if '日付' not in df_processed.columns:
            validation_results["is_valid"] = False
            validation_results["errors"].append("必須列「日付」が存在しません。")
            return None, validation_results

        df_processed['日付'] = pd.to_datetime(df_processed['日付'], errors='coerce')
        initial_rows = len(df_processed)
        df_processed.dropna(subset=['日付'], inplace=True)
        rows_dropped_due_to_date_nan = initial_rows - len(df_processed)
        if rows_dropped_due_to_date_nan > 0:
             validation_results["warnings"].append(
                f"無効な日付または日付が欠損している行が {rows_dropped_due_to_date_nan} 件ありました。これらの行は除外されました。"
            )

        if df_processed.empty:
            validation_results["is_valid"] = False
            validation_results["errors"].append("必須の「病棟コード」または「日付」の処理後にデータが空になりました。")
            return None, validation_results
            
        df_processed["病棟コード"] = df_processed["病棟コード"].astype(str)

        # ここで診療科名を主要診療科＋その他へ集約
        if '診療科名' in df_processed.columns:
            if pd.api.types.is_categorical_dtype(df_processed['診療科名']):
                df_processed['診療科名'] = df_processed['診療科名'].astype(str).fillna("空白診療科")
            else:
                df_processed['診療科名'] = df_processed['診療科名'].fillna("空白診療科").astype(str)
            # 集約判定: major_departments_list, もしくはマッピング先に含まれているもの
            def map_dept_name(x):
                if x in major_departments_list:
                    return x
                elif dept_name_to_code and dept_name_to_code.get(x) and dept_name_to_code.get(x) in major_departments_list:
                    return dept_name_to_code.get(x)  # 診療科名→部門名のマッピングが成立
                else:
                    return "その他"
            df_processed['診療科名'] = df_processed['診療科名'].apply(map_dept_name)
            validation_results["info"].append(
                f"診療科名を主要診療科（{len(major_departments_list)}件）と「その他」に集約しました。"
            )
        else:
            validation_results["warnings"].append("「診療科名」列が存在しないため、診療科集約をスキップしました。")
        
        initial_rows = len(df_processed)
        df_processed = efficient_duplicate_check(df_processed)
        rows_dropped_due_to_duplicates = initial_rows - len(df_processed)
        if rows_dropped_due_to_duplicates > 0:
            validation_results["info"].append(
                f"重複データ {rows_dropped_due_to_duplicates} 行を削除しました"
            )

        numeric_cols_to_process = [
            "在院患者数", "入院患者数", "緊急入院患者数", "退院患者数", "死亡患者数"
        ]
        for col in numeric_cols_to_process:
            if col in df_processed.columns:
                df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce')
                na_vals_before_fill = df_processed[col].isna().sum()
                if na_vals_before_fill > 0:
                    df_processed[col] = df_processed[col].fillna(0)
                    validation_results["info"].append(f"数値列'{col}'の欠損値 {na_vals_before_fill} 件を0で補完しました。")
            else:
                df_processed[col] = 0
                validation_results["warnings"].append(f"数値列'{col}'が存在しなかったため、0で補完された列を作成しました。")

        if "在院患者数" in df_processed.columns:
            df_processed["入院患者数（在院）"] = df_processed["在院患者数"].copy()
            validation_results["info"].append("「在院患者数」列を「入院患者数（在院）」列にコピーしました。")
        elif "入院患者数（在院）" not in df_processed.columns:
            df_processed["入院患者数（在院）"] = 0
            validation_results["errors"].append("「在院患者数」または「入院患者数（在院）」列が存在しません。「入院患者数（在院）」を0で作成します。")

        if "入院患者数" in df_processed.columns and "緊急入院患者数" in df_processed.columns:
            df_processed["総入院患者数"] = df_processed["入院患者数"] + df_processed["緊急入院患者数"]
        elif "入院患者数" in df_processed.columns:
            df_processed["総入院患者数"] = df_processed["入院患者数"]
            validation_results["info"].append("「緊急入院患者数」列がないため、「総入院患者数」は「入院患者数」と同じ値になります。")
        else:
            validation_results["warnings"].append("「入院患者数」列がないため、「総入院患者数」は計算できませんでした。0で作成します。")
            df_processed["総入院患者数"] = 0

        if "退院患者数" in df_processed.columns and "死亡患者数" in df_processed.columns:
            df_processed["総退院患者数"] = df_processed["退院患者数"] + df_processed["死亡患者数"]
        elif "退院患者数" in df_processed.columns:
            df_processed["総退院患者数"] = df_processed["退院患者数"]
            validation_results["info"].append("「死亡患者数」列がないため、「総退院患者数」は「退院患者数」と同じ値になります。")
        else:
            validation_results["warnings"].append("「退院患者数」列がないため、「総退院患者数」は計算できませんでした。0で作成します。")
            df_processed["総退院患者数"] = 0
            
        if "総入院患者数" in df_processed.columns:
            df_processed["新入院患者数"] = df_processed["総入院患者数"]
        else:
            df_processed["新入院患者数"] = 0

        # 延べ在院日数の計算
        df_processed = add_patient_days_calculation(df_processed)
        validation_results["info"].append("延べ在院日数（人日）を計算しました。")

        if '日付' in df_processed.columns:
            df_processed = add_weekday_flag(df_processed)
            validation_results["info"].append("平日/休日フラグを追加しました。")
        else:
            validation_results["errors"].append("「日付」列がないため、平日/休日フラグを追加できません。")

        general_validation_res = validate_general_data(df_processed)
        validation_results["warnings"].extend(general_validation_res.get("warnings", []))
        validation_results["errors"].extend(general_validation_res.get("errors", []))
        
        patient_days_validation_res = validate_patient_days_data(df_processed)
        validation_results["warnings"].extend(patient_days_validation_res.get("warnings", []))
        validation_results["errors"].extend(patient_days_validation_res.get("errors", []))
        if "summary" in patient_days_validation_res:
            validation_results["summaries"]["patient_days_summary"] = patient_days_validation_res["summary"]

        if validation_results["errors"]:
            validation_results["is_valid"] = False

        gc.collect()
        end_time = time.time()
        validation_results["info"].append(f"データ前処理全体時間: {end_time - start_time:.2f}秒")
        validation_results["info"].append(f"処理後のレコード数: {len(df_processed)}")
        if not df_processed.empty and '日付' in df_processed.columns:
            min_date_obj = df_processed['日付'].min()
            max_date_obj = df_processed['日付'].max()
            min_date_str = min_date_obj.strftime('%Y/%m/%d') if pd.notna(min_date_obj) else "不明"
            max_date_str = max_date_obj.strftime('%Y/%m/%d') if pd.notna(max_date_obj) else "不明"
            validation_results["info"].append(f"データ期間: {min_date_str} - {max_date_str}")
        
        if df_processed.empty and validation_results["is_valid"]:
            validation_results["is_valid"] = False
            validation_results["errors"].append("前処理の結果、有効なデータが残りませんでした。")
            logger.warning("Data became empty after processing but was initially considered valid.")
            return None, validation_results

        return df_processed, validation_results

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        validation_results["is_valid"] = False
        validation_results["errors"].append(f"データの前処理中に予期せぬエラーが発生しました: {str(e)}")
        logger.error(f"前処理エラー: {error_detail}")
        return None, validation_results
        
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
    
    return df  # この行がインデントされていることを確認
    
def calculate_file_hash(file_content_bytes):
    """
    ファイルのハッシュ値を計算して一意の識別子を作成
    
    Parameters:
    -----------
    file_content_bytes: bytes
        ファイルの内容をバイト列で表したもの
        
    Returns:
    --------
    str
        MD5ハッシュ値の16進数文字列
    """
    try:
        # ファイルサイズが大きすぎる場合、先頭部分のみを使用してハッシュ計算
        max_bytes = 10 * 1024 * 1024  # 10MB上限
        if len(file_content_bytes) > max_bytes:
            # 先頭5MBと末尾5MBを組み合わせてハッシュ計算
            head = file_content_bytes[:5 * 1024 * 1024]  # 先頭5MB
            tail = file_content_bytes[-5 * 1024 * 1024:]  # 末尾5MB
            combined = head + tail
            return hashlib.md5(combined).hexdigest()
        else:
            # 通常のハッシュ計算
            return hashlib.md5(file_content_bytes).hexdigest()
    except Exception as e:
        print(f"ファイルハッシュ計算エラー: {str(e)}")
        # エラー時にはファイルサイズとタイムスタンプの組み合わせを返す
        file_size = len(file_content_bytes)
        timestamp = int(time.time())
        return f"size_{file_size}_time_{timestamp}"


@st.cache_data(ttl=3600, show_spinner=False)
def read_excel_cached(file_content_bytes, sheet_name=0, usecols=None, dtype=None):
    """
    ファイル内容に基づいたキャッシュを使用してExcelを読み込む
    例外処理を強化
    
    Parameters:
    -----------
    file_content_bytes: bytes
        Excelファイルの内容をバイト列で表したもの
    sheet_name: int or str, default 0
        読み込むシート名またはインデックス
    usecols: list or None, default None
        読み込む列のリスト
    dtype: dict or None, default None
        列のデータ型を指定する辞書
        
    Returns:
    --------
    pd.DataFrame
        読み込まれたExcelデータ
    """
    temp_path = None
    try:
        # 一時ファイルを作成
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
            temp_file.write(file_content_bytes)
            temp_path = temp_file.name

        # 読み込み時のパラメータをログ出力（デバッグ用）
        print(f"Excel読込: usecols={usecols}, dtype={dtype}")
        
        # Excelファイルの読み込み
        df = pd.read_excel(
            temp_path, 
            sheet_name=sheet_name, 
            engine='openpyxl', 
            usecols=usecols, 
            dtype=dtype
        )
        
        # 基本的な検証
        if df.empty:
            print(f"警告: 読み込まれたExcelファイルが空です: sheet_name={sheet_name}")
            return None
            
        return df
    except Exception as e:
        # 詳細なエラーメッセージをログに出力
        print(f"Excel読込エラー: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return None
    finally:
        # 確実に一時ファイルを削除
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception as e:
                print(f"一時ファイル削除エラー: {str(e)}")


def load_files(base_file, new_files, usecols_excel=None, dtype_excel=None):
    """
    複数のExcelファイルを並列処理で読み込む。
    
    Parameters:
    -----------
    base_file: Streamlit UploadedFile object or None
        基本ファイル（通常は過去データ）
    new_files: list of Streamlit UploadedFile objects or None
        追加のファイルリスト
    usecols_excel: list or None
        Excel読み込み時に指定する列のリスト
    dtype_excel: dict or None
        Excel読み込み時に指定するデータ型の辞書
        
    Returns:
    --------
    pandas.DataFrame
        読み込まれたすべてのファイルを結合したデータフレーム
        ファイルがないか読み込みに失敗した場合は空のデータフレーム
    """
    start_time = time.time()
    
    # ファイルリストの準備
    df_list = []
    files_to_process = []

    # base_fileとnew_filesをファイルリストに追加
    if base_file:  # base_fileがNoneでない場合
        files_to_process.append(base_file)
        print(f"基本ファイルを処理リストに追加: {base_file.name}")
    
    if new_files:  # new_filesがNoneでない、かつ空でない場合
        files_to_process.extend(new_files)
        print(f"追加ファイル{len(new_files)}件を処理リストに追加")

    # 処理対象ファイルがない場合は空のデータフレームを返す
    if not files_to_process:
        print("処理対象ファイルがありません。")
        return pd.DataFrame()

    # ファイル内容をメモリに読み込む
    file_contents = []
    for file_obj in files_to_process:
        try:
            file_obj.seek(0)
            file_content = file_obj.read()
            file_contents.append((file_obj.name, file_content))
            file_obj.seek(0)  # ファイルポインタを戻す
            file_size = len(file_content) / (1024 * 1024)  # MBに変換
            print(f"ファイル読込: {file_obj.name} ({file_size:.2f} MB)")
        except Exception as e:
            print(f"ファイル読込エラー ({file_obj.name}): {str(e)}")

    # 並列処理の設定（最大ワーカー数を制限）
    max_workers = min(4, len(file_contents)) if file_contents else 1
    print(f"並列処理ワーカー数: {max_workers}")
    
    # 並列処理でExcelファイルを読み込む
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 各ファイルの読み込みタスクを登録
        futures = {
            executor.submit(read_excel_cached, content, 0, usecols_excel, dtype_excel): name
            for name, content in file_contents
        }

        # 各タスクの結果を処理
        successful_files = 0
        for future in concurrent.futures.as_completed(futures):
            file_name = futures[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    df_list.append(df)
                    rows, cols = df.shape
                    print(f"ファイル '{file_name}' の読込成功: {rows}行 × {cols}列")
                    successful_files += 1
                else:
                    print(f"ファイル '{file_name}' の読込結果が空です")
            except Exception as e:
                print(f"ファイル '{file_name}' の処理中にエラー: {str(e)}")
                import traceback
                print(traceback.format_exc())

    # 読み込み結果の確認
    if not df_list:
        print("読み込み可能なExcelデータがありません。")
        return pd.DataFrame()

    # データフレームの結合
    try:
        df_raw = pd.concat(df_list, ignore_index=True)
        
        # 効率的な重複チェックを行う
        df_raw = efficient_duplicate_check(df_raw)
        
        # 結果の出力
        end_time = time.time()
        rows, cols = df_raw.shape
        print(f"データ読込完了: {successful_files}/{len(file_contents)}ファイル成功, {rows}行 × {cols}列, 処理時間: {end_time - start_time:.2f}秒")
        
        return df_raw
    except Exception as e:
        print(f"データフレーム結合エラー: {str(e)}")
        return pd.DataFrame()