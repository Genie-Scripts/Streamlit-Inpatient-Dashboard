# forecast.py の改善
import pandas as pd
import jpholiday
import streamlit as st
from datetime import timedelta
import functools
import concurrent.futures
import numpy as np
import gc
import time
from datetime import timedelta

# メモ化デコレータの導入（インメモリキャッシュ）
def memoize(func):
    cache = {}
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]
    return wrapper

# より効率的なフィルタリング
@st.cache_data(ttl=3600, max_entries=100)
def filter_dataframe(df, filter_type=None, filter_value=None):
    """データフレームのフィルタリングを効率的に行う（キャッシュ対応）"""
    if filter_type and filter_value and filter_value != "全体":
        if filter_type not in df.columns:
            return None
        return df[df[filter_type] == filter_value].copy()
    return df.copy()

@st.cache_data(ttl=3600, show_spinner=False)
def generate_filtered_summaries_optimized(df, filter_type=None, filter_value=None):
    """
    フィルタリングと集計を最適化（並列処理版）
    """
    start_time = time.time()
    
    try:
        # フィルタリングを高速化
        if filter_type and filter_value and filter_value != "全体":
            if filter_type not in df.columns:
                print(f"フィルターカラム '{filter_type}' がデータに存在しません")
                return {}
            filtered_df = df[df[filter_type] == filter_value].copy()
            if filtered_df.empty:
                return {}
        else:
            filtered_df = df.copy()
        
        # インデックスを設定して集計を高速化
        if not pd.api.types.is_datetime64_dtype(filtered_df["日付"]):
            filtered_df["日付"] = pd.to_datetime(filtered_df["日付"], errors="coerce")
            filtered_df = filtered_df.dropna(subset=["日付"])
        
        # 並列処理で期間ごとの集計を実行
        # 全体の最新日付を取得
        latest_date = filtered_df["日付"].max()
        
        # 並列処理用に期間定義を作成
        period_definitions = {
            "直近7日平均": (latest_date - pd.Timedelta(days=6), latest_date),
            "直近14日平均": (latest_date - pd.Timedelta(days=13), latest_date),
            "直近30日平均": (latest_date - pd.Timedelta(days=29), latest_date),
            "直近60日平均": (latest_date - pd.Timedelta(days=59), latest_date),
            "2024年度平均": (pd.Timestamp("2024-04-01"), pd.Timestamp("2025-03-31")),
            "2025年度平均": (pd.Timestamp("2025-04-01"), latest_date)
        }
        
        # 2024年度（同期間）の計算
        if latest_date >= pd.Timestamp("2025-04-01"):
            days_elapsed_in_fy2025 = (latest_date - pd.Timestamp("2025-04-01")).days
            same_period_end_2024 = pd.Timestamp("2024-04-01") + pd.Timedelta(days=days_elapsed_in_fy2025)
            if same_period_end_2024 >= pd.Timestamp("2024-04-01"):
                period_definitions["2024年度（同期間）"] = (pd.Timestamp("2024-04-01"), same_period_end_2024)
        
        # 集計結果を格納する辞書
        summary = {}
        weekday_summary = {}
        holiday_summary = {}
        
        # データの日付インデックスを作成して検索を高速化
        grouped_by_date = filtered_df.set_index("日付")
        
        # 集計カラム
        cols_to_agg = ["入院患者数（在院）", "緊急入院患者数", "新入院患者数", "退院患者数"]
        
        def process_period(label, start_date, end_date):
            """指定された期間のデータを集計する"""
            # 期間データの抽出
            period_data = grouped_by_date[start_date:end_date].reset_index()
            
            if period_data.empty:
                # 空の結果
                return (
                    label, 
                    pd.Series(index=cols_to_agg, dtype=float),
                    pd.Series(index=cols_to_agg, dtype=float),
                    pd.Series(index=cols_to_agg, dtype=float)
                )
                
            # 全体平均
            all_avg = period_data[cols_to_agg].mean().round(1)
            
            # 平日データの計算
            weekday_data = period_data[period_data["平日判定"] == "平日"]
            if not weekday_data.empty:
                weekday_avg = weekday_data[cols_to_agg].mean().round(1)
            else:
                weekday_avg = pd.Series(index=cols_to_agg, dtype=float)
                
            # 休日データの計算
            holiday_data = period_data[period_data["平日判定"] == "休日"]
            if not holiday_data.empty:
                holiday_avg = holiday_data[cols_to_agg].mean().round(1)
            else:
                holiday_avg = pd.Series(index=cols_to_agg, dtype=float)
                
            return (label, all_avg, weekday_avg, holiday_avg)
        
        # 並列処理で各期間の集計を実行
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(period_definitions))) as executor:
            futures = [
                executor.submit(process_period, label, start, end)
                for label, (start, end) in period_definitions.items()
            ]
            
            for future in concurrent.futures.as_completed(futures):
                label, all_avg, weekday_avg, holiday_avg = future.result()
                summary[label] = all_avg
                weekday_summary[label] = weekday_avg
                holiday_summary[label] = holiday_avg
        
        # 表示順序を定義
        display_order = [
            "直近7日平均",
            "直近14日平均",
            "直近30日平均",
            "直近60日平均",
            "2024年度平均",
            "2024年度（同期間）",
            "2025年度平均"
        ]
        
        # DataFrameを作成し、表示順序で並び替え
        df_summary = pd.DataFrame(summary).T.reindex([label for label in display_order if label in summary])
        df_weekday = pd.DataFrame(weekday_summary).T.reindex([label for label in display_order if label in weekday_summary])
        df_holiday = pd.DataFrame(holiday_summary).T.reindex([label for label in display_order if label in holiday_summary])
        
        # 月次集計の最適化（並列処理はせず、一括処理）
        # 年月列を事前に一度だけ計算
        filtered_df["年月"] = filtered_df["日付"].dt.to_period("M")
        monthly_groups = filtered_df.groupby(["年月", "平日判定"])
        
        monthly_all = filtered_df.groupby("年月")[cols_to_agg].mean().round(1)
        monthly_weekday = monthly_groups.get_group(("平日"))[cols_to_agg].mean().round(1) if ("平日",) in monthly_groups.groups else pd.DataFrame()
        monthly_holiday = monthly_groups.get_group(("休日"))[cols_to_agg].mean().round(1) if ("休日",) in monthly_groups.groups else pd.DataFrame()
        
        end_time = time.time()
        print(f"集計処理完了: 処理時間 {end_time - start_time:.2f}秒")
        
        # 結果を辞書で返す
        return {
            "summary": df_summary,
            "weekday": df_weekday,
            "holiday": df_holiday,
            "monthly_all": monthly_all,
            "monthly_weekday": monthly_weekday,
            "monthly_holiday": monthly_holiday,
            "latest_date": latest_date
        }
        
    except Exception as e:
        print(f"集計処理エラー: {e}")
        import traceback
        print(traceback.format_exc())
        return {}

@st.cache_data(ttl=3600)  # 1時間キャッシュ
def generate_filtered_summaries(df, filter_type=None, filter_value=None):
    """
    指定されたフィルター条件でデータを集計し、各種平均値を計算する
    （キャッシュ対応版）

    Parameters:
    -----------
    df : pd.DataFrame
        元データ
    filter_type : str, optional
        フィルタするカラム名
    filter_value : str or int, optional
        フィルタする値

    Returns:
    --------
    dict
        集計結果を含む辞書
    """
    try:
        # フィルタリングを適用
        if filter_type and filter_value and filter_value != "全体":
            if filter_type not in df.columns:
                raise KeyError(f"フィルタするカラム '{filter_type}' がデータに存在しません")

            filtered_df = df[df[filter_type] == filter_value].copy()
            # データがない場合は空の辞書を返す
            if filtered_df.empty:
                return {}
        else:
            filtered_df = df.copy()
            # 全体の場合でもデータがない場合は空の辞書を返す
            if filtered_df.empty:
                return {}

        # 平均値を出すために、日付単位で合算
        try:
            # --- ここからインデントを修正 ---
            grouped = filtered_df.groupby("日付").agg({
                "入院患者数（在院）": "sum",
                "緊急入院患者数": "sum",
                "新入院患者数": "sum",
                "退院患者数": "sum",
                "平日判定": "first" # 日付ごとの平日/休日判定を取得
            }).reset_index()
            # --- ここまでインデントを修正 ---
        except KeyError as e:
            missing_col = str(e).strip("'")
            st.error(f"集計に必要なカラム '{missing_col}' がデータに存在しません")
            return {}

        # groupedが空の場合も考慮
        if grouped.empty:
            return {}

        # 全データの最新日付を取得（フィルタリング前のデータから）
        all_data_latest_date = df["日付"].max()
        
        # フィルタリング後のデータの最新日付（グラフ等で使用）
        if not grouped.empty:
            filtered_latest_date = grouped["日付"].max()
        else:
            filtered_latest_date = all_data_latest_date  # フィルタリング後のデータがない場合

        # 基準日として全データの最新日付を使用
        latest_date = all_data_latest_date

        summary = {}
        weekday_summary = {}
        holiday_summary = {}

        # 集計対象のカラムリスト
        cols_to_agg = ["入院患者数（在院）", "緊急入院患者数", "新入院患者数", "退院患者数"]

        def add_summary(label, data):
            # データが空でないことを確認
            if not data.empty and len(data) > 0:
                # 全体平均
                summary[label] = data[cols_to_agg].mean().round(1)
                # 平日データ抽出と平均計算
                weekday_data = data[data["平日判定"] == "平日"]
                if not weekday_data.empty and len(weekday_data) > 0:
                    weekday_summary[label] = weekday_data[cols_to_agg].mean().round(1)
                else:
                    # データが0件の場合はNaN（空）の行を作成
                    weekday_summary[label] = pd.Series(index=cols_to_agg, dtype=float)
                # 休日データ抽出と平均計算
                holiday_data = data[data["平日判定"] == "休日"]
                if not holiday_data.empty and len(holiday_data) > 0:
                    holiday_summary[label] = holiday_data[cols_to_agg].mean().round(1)
                else:
                    # データが0件の場合はNaN（空）の行を作成
                    holiday_summary[label] = pd.Series(index=cols_to_agg, dtype=float)
            else:
                # 対象期間にデータがない場合もNaNで埋める
                summary[label] = pd.Series(index=cols_to_agg, dtype=float)
                weekday_summary[label] = pd.Series(index=cols_to_agg, dtype=float)
                holiday_summary[label] = pd.Series(index=cols_to_agg, dtype=float)

        # 各期間の計算（全データの最新日付を基準に使用）
        for days, label in [(7, "直近7日平均"), (14, "直近14日平均"), (30, "直近30日平均"), (60, "直近60日平均")]:
            # 基準日から逆算した期間
            start_date_period = latest_date - pd.Timedelta(days=days-1)
            period_data = grouped[(grouped["日付"] >= start_date_period) & (grouped["日付"] <= latest_date)]
            add_summary(label, period_data)

        # 年度期間の設定 (2024年度: 2024-04-01 to 2025-03-31)
        fy2024_start = pd.Timestamp("2024-04-01")
        fy2024_end = pd.Timestamp("2025-03-31")
        fy2024_data = grouped[(grouped["日付"] >= fy2024_start) & (grouped["日付"] <= fy2024_end)]
        add_summary("2024年度平均", fy2024_data)

        # 2024年度（同期間）の計算
        # 基準日（最新日）から見た、今年度（2025年度）の開始日からの経過日数
        if latest_date >= pd.Timestamp("2025-04-01"):
            days_elapsed_in_fy2025 = (latest_date - pd.Timestamp("2025-04-01")).days
            # 2024年度の対応する終了日を計算
            try:
                same_period_end_2024 = fy2024_start + pd.Timedelta(days=days_elapsed_in_fy2025)
            except ValueError:
                # 2/29の場合など、単純な年置換ができない場合は2/28等に調整（簡易対応）
                 same_period_end_2024 = fy2024_start + pd.Timedelta(days=days_elapsed_in_fy2025 -1) # 調整例

            # 計算した終了日が2024年度の開始日以降であることを確認
            if same_period_end_2024 >= fy2024_start:
                 # 2024年度の同期間データを抽出
                 fy2024_same_period = grouped[(grouped["日付"] >= fy2024_start) & (grouped["日付"] <= same_period_end_2024)]
                 add_summary("2024年度（同期間）", fy2024_same_period)
            else:
                 # 同期間データが存在しない場合（例：2025年度開始直後）
                 add_summary("2024年度（同期間）", pd.DataFrame(columns=grouped.columns)) # 空のDFでNaNを生成
        else:
            # 基準日がまだ2025年度に入っていない場合は、同期間のデータはなし
            add_summary("2024年度（同期間）", pd.DataFrame(columns=grouped.columns)) # 空のDFでNaNを生成

        # 2025年度期間の設定 (2025-04-01 to 2026-03-31)
        fy2025_start = pd.Timestamp("2025-04-01")
        fy2025_end = pd.Timestamp("2026-03-31")
        # 2025年度データは、年度開始日以降かつ基準日（最新日）までのデータ
        fy2025_data = grouped[(grouped["日付"] >= fy2025_start) & (grouped["日付"] <= latest_date)]
        add_summary("2025年度平均", fy2025_data)

        # 表示順序を定義
        display_order = [
            "直近7日平均",
            "直近14日平均",
            "直近30日平均",
            "直近60日平均",
            "2024年度平均",
            "2024年度（同期間）",
            "2025年度平均"
        ]

        # DataFrameを作成し、表示順序で並び替え
        df_summary = pd.DataFrame(summary).T.reindex(display_order)
        df_weekday = pd.DataFrame(weekday_summary).T.reindex(display_order)
        df_holiday = pd.DataFrame(holiday_summary).T.reindex(display_order)

        # 月次集計
        grouped["年月"] = grouped["日付"].dt.to_period("M")
        monthly_all = grouped.groupby("年月")[cols_to_agg].mean().round(1)
        monthly_weekday = grouped[grouped["平日判定"] == "平日"].groupby("年月")[cols_to_agg].mean().round(1)
        monthly_holiday = grouped[grouped["平日判定"] == "休日"].groupby("年月")[cols_to_agg].mean().round(1)

        # 結果を辞書で返す (latest_date も含める)
        return {
            "summary": df_summary,
            "weekday": df_weekday,
            "holiday": df_holiday,
            "monthly_all": monthly_all,
            "monthly_weekday": monthly_weekday,
            "monthly_holiday": monthly_holiday,
            "latest_date": latest_date # 最新日付を追加
        }

    except KeyError as e:
        # キーエラー（カラム存在しない場合など）
        st.error(f"必要なカラムが見つかりません: {str(e)}")
        return {}
    except TypeError as e:
        # 型エラー
        st.error(f"データ型の問題が発生しました: {str(e)}")
        return {}
    except Exception as e:
        # その他のエラー
        st.error(f"データ集計中に予期せぬエラーが発生しました: {str(e)}")
        return {}

def calculate_fiscal_year_days(year):
    """
    指定された年度の日数を計算する（うるう年考慮）

    Parameters:
    -----------
    year : int
        年度（例: 2025）

    Returns:
    --------
    int
        年度の日数
    """
    start_date = pd.Timestamp(f"{year}-04-01")
    end_date = pd.Timestamp(f"{year+1}-03-31")
    return (end_date - start_date).days + 1

@st.cache_data(ttl=1800)  # 30分キャッシュ
def create_forecast_dataframe(df_weekday, df_holiday, today):
    """
    平日・休日の平均値データフレームから将来の予測値を計算する
    （キャッシュ対応版）

    Parameters:
    -----------
    df_weekday : pd.DataFrame
        平日平均データ
    df_holiday : pd.DataFrame
        休日平均データ
    today : datetime
        基準日（通常はデータの最新日付）

    Returns:
    --------
    pd.DataFrame
        予測データフレーム
    """
    try:
        # df_weekday や df_holiday が None または空の場合は計算不可
        if df_weekday is None or df_weekday.empty or df_holiday is None or df_holiday.empty:
            st.warning("予測計算に必要な平日または休日の平均データがありません。")
            return pd.DataFrame()

        # 今日の日付をPandas Timestampに確実に変換
        today = pd.Timestamp(today).normalize()

        # 2025年度末までの日付範囲を生成
        end_fy2025 = pd.Timestamp("2026-03-31")

        # today が年度末を超えている場合は予測期間がない
        if today >= end_fy2025:
            st.info("予測対象期間（2025年度末まで）が終了しています。")
            return pd.DataFrame()

        # 残りの日数を計算（基準日の翌日から年度末まで）
        remain_dates = pd.date_range(start=today + pd.Timedelta(days=1), end=end_fy2025)
        if remain_dates.empty:
            st.info("予測対象期間（2025年度末まで）の残りがありません。")
            return pd.DataFrame()

        remain_df = pd.DataFrame({"日付": remain_dates})

        # 平日/休日の判定
        def is_holiday_for_forecast(date):
            return (
                date.weekday() >= 5 or
                jpholiday.is_holiday(date) or
                (date.month == 12 and date.day >= 29) or
                (date.month == 1 and date.day <= 3)
            )
        remain_df["平日判定"] = remain_df["日付"].apply(lambda x: "休日" if is_holiday_for_forecast(x) else "平日")

        num_weekdays = (remain_df["平日判定"] == "平日").sum()
        num_holidays = len(remain_df) - num_weekdays

        # 今年度（2025年度）の開始日
        fy2025_start = pd.Timestamp("2025-04-01")

        # 今年度の経過日数を計算 (基準日までの日数)
        if today >= fy2025_start:
            elapsed_days_fy2025 = (today - fy2025_start).days + 1
        else:
            elapsed_days_fy2025 = 0 # まだ2025年度に入っていない場合

        # 年度の日数をうるう年を考慮して計算
        total_days_in_fy2025 = calculate_fiscal_year_days(2025)

        forecast_rows = []
        # df_weekday のインデックス（基準期間ラベル）をループ
        for label in df_weekday.index:
            try:
                # 当該ラベルの平日・休日平均値を取得
                # .loc[] で存在しないラベルを参照するとエラーになる可能性があるため、安全にアクセス
                if label not in df_weekday.index or label not in df_holiday.index:
                    st.warning(f"基準期間 '{label}' のデータが平日または休日に存在しません。スキップします。")
                    continue

                weekday_avg_series = df_weekday.loc[label]
                holiday_avg_series = df_holiday.loc[label]

                # '入院患者数（在院）' 列が存在するか確認
                if "入院患者数（在院）" not in weekday_avg_series or "入院患者数（在院）" not in holiday_avg_series:
                    st.warning(f"基準期間 '{label}' のデータに '入院患者数（在院）' がありません。スキップします。")
                    continue

                weekday_avg = weekday_avg_series["入院患者数（在院）"]
                holiday_avg = holiday_avg_series["入院患者数（在院）"]

                # NaN値のチェックと処理（0に置換）
                weekday_avg = 0 if pd.isna(weekday_avg) else weekday_avg
                holiday_avg = 0 if pd.isna(holiday_avg) else holiday_avg

                # 将来の予測延べ患者数（残りの日数 * 各平均値）
                future_total = weekday_avg * num_weekdays + holiday_avg * num_holidays

                # 実績計算：2025年度の平均値を使って経過日数分の実績を計算
                actual_total = 0
                # '2025年度平均' が df_summary に存在し、かつ '入院患者数（在院）' 列があるか確認
                # Note: 2025年度平均は df_summary (全期間平均) から取得する必要があるかもしれない
                #       ここでは df_weekday を参照しているが、設計に応じて要確認
                #       generate_filtered_summaries の戻り値に df_summary も含めるべき
                #       -> 修正済み：generate_filtered_summariesは辞書で全て返す

                # 全体平均(summary)から2025年度平均を取得する前提で修正
                # generate_filtered_summariesの戻り値resultsからsummaryを取得し、そこから計算するロジックが必要だが、
                # この関数はdf_weekday, df_holiday しか受け取らないため、現状では計算不可
                # -> 引数に df_summary を追加するか、呼び出し元で計算する必要あり
                # -> ここでは仮に weekday の2025年度平均を使うが、設計見直し推奨
                if "2025年度平均" in df_weekday.index and "入院患者数（在院）" in df_weekday.loc["2025年度平均"]:
                    actual_avg_2025 = df_weekday.loc["2025年度平均"]["入院患者数（在院）"]
                    actual_avg_2025 = 0 if pd.isna(actual_avg_2025) else actual_avg_2025
                    actual_total = actual_avg_2025 * elapsed_days_fy2025
                else:
                    # 2025年度平均データがない場合は実績0として扱う
                    actual_total = 0

                # 年間平均人日 (実績 + 予測) / 年度日数
                if total_days_in_fy2025 > 0:
                    forecast_avg_per_day = (actual_total + future_total) / total_days_in_fy2025
                else:
                    forecast_avg_per_day = 0 # 0除算回避

                forecast_rows.append({
                    "基準期間": label,
                    "平日平均": round(weekday_avg, 1),
                    "休日平均": round(holiday_avg, 1),
                    "残平日": int(num_weekdays),
                    "残休日": int(num_holidays),
                    "延べ予測人日": round(future_total, 0), # 将来分のみ
                    "年間平均人日（実績＋予測）": round(forecast_avg_per_day, 1)
                })
            except KeyError as e:
                 st.warning(f"予測計算中にキーエラーが発生しました ({label}): {str(e)}")
                 continue
            except Exception as e:
                st.warning(f"予測計算中に予期せぬエラーが発生しました ({label}): {str(e)}")
                continue

        # DataFrameを作成
        if not forecast_rows:
            st.warning("予測結果を生成できませんでした。")
            return pd.DataFrame()

        forecast_df = pd.DataFrame(forecast_rows)

        # 不要な行（例: 過去年度の平均）を除外 - 2024年度関連は予測には不要
        if not forecast_df.empty:
            forecast_df = forecast_df[~forecast_df["基準期間"].str.contains("2024年度", na=False)]

        # 基準期間をインデックスに設定して返す
        if not forecast_df.empty:
            try:
                forecast_df = forecast_df.set_index("基準期間")
            except KeyError:
                 st.warning("予測結果のDataFrameに'基準期間'列が見つかりませんでした。インデックス設定をスキップします。")

        return forecast_df

    except Exception as e:
        st.error(f"予測データフレーム作成中にエラーが発生しました: {str(e)}")
        return pd.DataFrame()