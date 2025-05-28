import pandas as pd
import jpholiday # jpholiday.is_holiday のために必要
import streamlit as st
from datetime import datetime, timedelta # datetime.now(), timedelta のために必要
import numpy as np # pd.isna での NaN チェックは pandas に含まれますが、numpy も関連ライブラリとして記載
# この関数は calculate_fiscal_year_days を呼び出しているので、
# 同じファイル内に定義されているか、適切にインポートされている必要があります。
# 例:
# def calculate_fiscal_year_days(year):
#     """指定された年度の日数を計算する（うるう年考慮）"""
#     start_date = pd.Timestamp(f"{year}-04-01")
#     end_date = pd.Timestamp(f"{year+1}-03-31")
#     return (end_date - start_date).days + 1
from datetime import datetime, timedelta # timedelta も使用されているため

def predict_monthly_completion(df_actual, period_dates):
    """月末までの予測（簡易版）"""
    try:
        # 現在の日数と月の総日数
        days_elapsed = (period_dates['end_date'] - period_dates['start_date']).days + 1
        days_in_month = pd.Timestamp(period_dates['end_date'].year, period_dates['end_date'].month, 1).days_in_month
        remaining_days = days_in_month - days_elapsed
        
        if remaining_days <= 0:
            return pd.DataFrame()  # 既に月末
        
        # 直近7日間の平均を使用して予測
        recent_data = df_actual.tail(7)
        daily_averages = recent_data.groupby('日付')[['在院患者数', '入院患者数', '退院患者数', '緊急入院患者数']].sum().mean()
        
        # 残り日数分の予測データを生成
        predicted_dates = pd.date_range(
            start=period_dates['end_date'] + pd.Timedelta(days=1),
            periods=remaining_days,
            freq='D'
        )
        
        predicted_data = []
        for date in predicted_dates:
            # 曜日効果を考慮（簡易版）
            day_of_week = date.dayofweek
            weekend_factor = 0.7 if day_of_week >= 5 else 1.0  # 土日は70%
            
            predicted_data.append({
                '日付': date,
                '在院患者数': daily_averages['在院患者数'] * weekend_factor,
                '入院患者数': daily_averages['入院患者数'] * weekend_factor,
                '退院患者数': daily_averages['退院患者数'] * weekend_factor,
                '緊急入院患者数': daily_averages['緊急入院患者数'] * weekend_factor,
                '病棟コード': '予測',
                '診療科名': '予測'
            })
        
        return pd.DataFrame(predicted_data)
        
    except Exception as e:
        print(f"予測データ生成エラー: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600, max_entries=100)
def filter_dataframe(df, filter_type=None, filter_value=None):
    """データフレームのフィルタリングを効率的に行う（キャッシュ対応）"""
    if filter_type and filter_value and filter_value != "全体":
        if filter_type not in df.columns:
            return None
        return df[df[filter_type] == filter_value].copy()
    return df.copy()

@st.cache_data(ttl=3600)
def generate_filtered_summaries(df, filter_type=None, filter_value=None):
    """
    指定されたフィルター条件でデータを集計し、各種平均値を計算する
    """
    # from datetime import datetime # モジュールレベルでインポート済みの場合は不要

    try:
        # フィルタリングを適用
        if filter_type and filter_value and filter_value != "全体":
            if filter_type not in df.columns:
                st.error(f"フィルタするカラム '{filter_type}' がデータに存在しません")
                return {}

            filtered_df = df[df[filter_type] == filter_value].copy()
            if filtered_df.empty:
                # st.info(f"フィルター条件 '{filter_type} = {filter_value}' に一致するデータがありません。")
                return {}
        else:
            filtered_df = df.copy()
            if filtered_df.empty:
                # st.info("入力データフレームが空です。")
                return {}

        # 日付列の処理
        if '日付' not in filtered_df.columns:
            st.error("必須の「日付」列がフィルタリング後のデータに存在しません。")
            return {}
        if not pd.api.types.is_datetime64_dtype(filtered_df["日付"]):
            filtered_df["日付"] = pd.to_datetime(filtered_df["日付"], errors="coerce")
            # NaTになった行（無効な日付）を削除
            initial_rows = len(filtered_df)
            filtered_df = filtered_df.dropna(subset=["日付"])
            if len(filtered_df) < initial_rows:
                st.warning(f"{initial_rows - len(filtered_df)}件の無効な日付データが削除されました。")

        if filtered_df.empty: # 日付処理後に空になる可能性
            # st.info("日付処理後、有効なデータが残りませんでした。")
            return {}
            
        # '平日判定'列の存在確認と追加
        if '平日判定' not in filtered_df.columns:
            # integrated_preprocessing.py の add_weekday_flag と同様のロジック
            def is_holiday(date_val):
                return (
                    date_val.weekday() >= 5 or
                    jpholiday.is_holiday(date_val) or
                    (date_val.month == 12 and date_val.day >= 29) or
                    (date_val.month == 1 and date_val.day <= 3)
                )
            filtered_df['平日判定'] = filtered_df['日付'].apply(lambda x: "休日" if is_holiday(x) else "平日")


        # 日付単位で合算
        agg_cols = {
            "入院患者数（在院）": "sum",
            "緊急入院患者数": "sum",
            "新入院患者数": "sum",
            "退院患者数": "sum",
            "平日判定": "first" # 平日判定は日付ごとにユニークなのでfirstで良い
        }
        # 存在しない可能性のある列をagg_colsから除外
        cols_for_agg_existing = {k: v for k, v in agg_cols.items() if k in filtered_df.columns}
        if not cols_for_agg_existing:
             st.error("集計に必要な数値列（在院患者数など）が存在しません。")
             return {}

        grouped = filtered_df.groupby("日付", as_index=False).agg(cols_for_agg_existing)


        if grouped.empty:
            # st.info("グループ化後、データが空になりました。")
            return {}

        # 最新日付を取得 (フィルタリング前のdfの最新日を使うべきか、フィルタリング後のgroupedの最新日か検討。ここでは元dfの最新日)
        latest_data_date = df['日付'].max() if '日付' in df.columns and not df.empty else None
        if latest_data_date is None:
            # grouped が空でなければ grouped の日付を使う (より安全)
            if not grouped.empty and '日付' in grouped.columns:
                latest_data_date = grouped['日付'].max()
            else:
                st.error("データの最新日付が特定できませんでした。")
                return {}

        # today = datetime.now().date() # この行は不要。latest_data_date を基準とする
        summary = {}
        weekday_summary = {}
        holiday_summary = {}

        # 集計対象のカラムリスト (実際にgroupedに存在する列のみ)
        cols_to_agg = [col for col in ["入院患者数（在院）", "緊急入院患者数", "新入院患者数", "退院患者数"] if col in grouped.columns]
        if not cols_to_agg: # 集計できる数値列がなければ終了
            st.error("平均値計算のための主要な数値列がgroupedデータにありません。")
            return {}

        def add_summary(label, data):
            # dataがNoneまたは空の場合の処理を強化
            if data is None or data.empty or len(data) == 0:
                summary[label] = pd.Series(index=cols_to_agg, dtype=float)
                weekday_summary[label] = pd.Series(index=cols_to_agg, dtype=float)
                holiday_summary[label] = pd.Series(index=cols_to_agg, dtype=float)
                return

            # 全体平均
            summary[label] = data[cols_to_agg].mean().round(1)
            
            # 平日データ
            if "平日判定" in data.columns:
                weekday_data = data[data["平日判定"] == "平日"]
                if not weekday_data.empty:
                    weekday_summary[label] = weekday_data[cols_to_agg].mean().round(1)
                else:
                    weekday_summary[label] = pd.Series(index=cols_to_agg, dtype=float)
            else: # 平日判定列がない場合
                weekday_summary[label] = pd.Series(index=cols_to_agg, dtype=float)

            # 休日データ
            if "平日判定" in data.columns:
                holiday_data = data[data["平日判定"] == "休日"]
                if not holiday_data.empty:
                    holiday_summary[label] = holiday_data[cols_to_agg].mean().round(1)
                else:
                    holiday_summary[label] = pd.Series(index=cols_to_agg, dtype=float)
            else: # 平日判定列がない場合
                holiday_summary[label] = pd.Series(index=cols_to_agg, dtype=float)


        # 期間別の計算
        periods = [
            (7, "直近7日平均"),
            (14, "直近14日平均"),
            (30, "直近30日平均"),
            (60, "直近60日平均")
        ]
        
        for days, label in periods:
            # NameError修正: latest_date -> latest_data_date
            start_date_period = latest_data_date - pd.Timedelta(days=days-1)
            period_data = grouped[
                (grouped["日付"] >= start_date_period) &
                (grouped["日付"] <= latest_data_date) # NameError修正: latest_date -> latest_data_date
            ]
            add_summary(label, period_data)

        # 年度期間の設定
        fy2024_start = pd.Timestamp("2024-04-01")
        fy2024_end = pd.Timestamp("2025-03-31")
        # grouped データの日付範囲でフィルタリング
        fy2024_data = grouped[
            (grouped["日付"] >= fy2024_start) &
            (grouped["日付"] <= fy2024_end)
        ]
        add_summary("2024年度平均", fy2024_data)

        # 2024年度（同期間）の計算
        # NameError修正: latest_date -> latest_data_date
        if latest_data_date >= pd.Timestamp("2025-04-01"):
            # NameError修正: latest_date -> latest_data_date
            days_elapsed = (latest_data_date - pd.Timestamp("2025-04-01")).days
            same_period_end_2024 = fy2024_start + pd.Timedelta(days=days_elapsed)
            
            if same_period_end_2024 >= fy2024_start:
                fy2024_same_period = grouped[
                    (grouped["日付"] >= fy2024_start) &
                    (grouped["日付"] <= same_period_end_2024)
                ]
                add_summary("2024年度（同期間）", fy2024_same_period)
            else:
                add_summary("2024年度（同期間）", pd.DataFrame(columns=grouped.columns)) # 空のデータフレームを渡す
        else:
            add_summary("2024年度（同期間）", pd.DataFrame(columns=grouped.columns)) # 空のデータフレームを渡す

        # 2025年度平均
        fy2025_start = pd.Timestamp("2025-04-01")
        # NameError修正: latest_date -> latest_data_date
        fy2025_data = grouped[
            (grouped["日付"] >= fy2025_start) &
            (grouped["日付"] <= latest_data_date)
        ]
        add_summary("2025年度平均", fy2025_data)

        # 表示順序
        display_order = [
            "直近7日平均",
            "直近14日平均",
            "直近30日平均",
            "直近60日平均",
            "2024年度平均",
            "2024年度（同期間）",
            "2025年度平均"
        ]

        # DataFrameを作成
        df_summary = pd.DataFrame(summary).T
        if not df_summary.empty:
            df_summary = df_summary.reindex(display_order)

        df_weekday = pd.DataFrame(weekday_summary).T
        if not df_weekday.empty:
            df_weekday = df_weekday.reindex(display_order)

        df_holiday = pd.DataFrame(holiday_summary).T
        if not df_holiday.empty:
            df_holiday = df_holiday.reindex(display_order)

        # 月次集計 (cols_to_agg は上で grouped に存在する列にフィルタリング済み)
        # grouped に '年月' 列を追加する前に、grouped が空でないことを確認
        if grouped.empty or '日付' not in grouped.columns:
             monthly_all = pd.DataFrame()
             monthly_weekday = pd.DataFrame()
             monthly_holiday = pd.DataFrame()
        else:
            grouped["年月"] = grouped["日付"].dt.to_period("M")
            monthly_all = grouped.groupby("年月")[cols_to_agg].mean().round(1) if cols_to_agg else pd.DataFrame()
            if "平日判定" in grouped.columns and cols_to_agg:
                monthly_weekday = grouped[grouped["平日判定"] == "平日"].groupby("年月")[cols_to_agg].mean().round(1)
                monthly_holiday = grouped[grouped["平日判定"] == "休日"].groupby("年月")[cols_to_agg].mean().round(1)
            else:
                monthly_weekday = pd.DataFrame()
                monthly_holiday = pd.DataFrame()


        return {
            "summary": df_summary,
            "weekday": df_weekday,
            "holiday": df_holiday,
            "monthly_all": monthly_all,
            "monthly_weekday": monthly_weekday,
            "monthly_holiday": monthly_holiday,
            "latest_date": latest_data_date # NameError修正: latest_date -> latest_data_date
        }

    except Exception as e:
        st.error(f"データ集計中にエラーが発生しました: {str(e)}")
        import traceback
        st.error(traceback.format_exc()) # 詳細なトレースバックも表示
        return {}

# calculate_fiscal_year_days 関数 (変更なしのため省略)
# create_forecast_dataframe 関数 (この関数の修正は別途議論したため、ここでは省略)

def calculate_fiscal_year_days(year):
    """指定された年度の日数を計算する（うるう年考慮）"""
    start_date = pd.Timestamp(f"{year}-04-01")
    end_date = pd.Timestamp(f"{year+1}-03-31")
    return (end_date - start_date).days + 1

@st.cache_data(ttl=1800)
def create_forecast_dataframe(df_summary, df_weekday, df_holiday, today):
    """
    予測データフレームを作成。
    平日・休日の平均値データから将来の予測値を計算します。

    Args:
        df_summary (pd.DataFrame): 全日平均の集計データ（インデックスに期間ラベル、列に指標）。
        df_weekday (pd.DataFrame): 平日平均の集計データ（インデックスに期間ラベル、列に指標）。
        df_holiday (pd.DataFrame): 休日平均の集計データ（インデックスに期間ラベル、列に指標）。
        today (datetime.date or str or pd.Timestamp): 予測の基準となる日付。
                                                      この日付の翌日から予測を開始します。
    """
    # today がNoneの場合のフォールバックは残すが、呼び出し側で日付を指定することを推奨
    if today is None:
        today_obj = datetime.now().date()
        st.warning("予測基準日(today)が指定されなかったため、現在の日付を使用します。")
    else:
        today_obj = today

    try:
        if df_weekday is None or df_weekday.empty or df_holiday is None or df_holiday.empty:
            st.warning("予測計算に必要な平日または休日の平均データがありません。")
            return pd.DataFrame()

        # 基準日をPandas Timestampに変換
        today_ts = pd.Timestamp(today_obj).normalize()

        # 2025年度末までの日付範囲を生成
        end_fy2025 = pd.Timestamp("2026-03-31")

        if today_ts >= end_fy2025:
            st.info("予測対象期間（2025年度末まで）が終了しています。")
            return pd.DataFrame()

        # 残りの日数を計算
        # 予測開始日は基準日の翌日
        forecast_start_date = today_ts + pd.Timedelta(days=1)
        if forecast_start_date > end_fy2025:
            st.info("予測対象期間の残りがありません（基準日が年度末以降）。")
            return pd.DataFrame()
            
        remain_dates = pd.date_range(start=forecast_start_date, end=end_fy2025)
        if remain_dates.empty: # 通常は上のチェックでカバーされるが一応残す
            st.info("予測対象期間の残りがありません。")
            return pd.DataFrame()

        remain_df = pd.DataFrame({"日付": remain_dates})

        # 平日/休日の判定
        def is_holiday_for_forecast(date_val):
            return (
                date_val.weekday() >= 5 or  # 土曜日または日曜日
                jpholiday.is_holiday(date_val) or
                (date_val.month == 12 and date_val.day >= 29) or  # 年末
                (date_val.month == 1 and date_val.day <= 3)  # 年始
            )
        
        remain_df["平日判定"] = remain_df["日付"].apply(
            lambda x: "休日" if is_holiday_for_forecast(x) else "平日"
        )

        num_weekdays = (remain_df["平日判定"] == "平日").sum()
        num_holidays = len(remain_df) - num_weekdays

        # 2025年度の経過日数を計算 (基準日 today_ts まで)
        fy2025_start_ts = pd.Timestamp("2025-04-01")
        elapsed_days_fy2025 = 0
        if today_ts >= fy2025_start_ts:
            elapsed_days_fy2025 = (today_ts - fy2025_start_ts).days + 1
        
        # 年度の総日数
        # この関数が同じファイル内またはインポートされていることを確認
        total_days_in_fy2025 = calculate_fiscal_year_days(2025) 

        forecast_rows = []
        
        # 予測に使用する基準期間を選択（直近期間と年度平均）
        relevant_labels = [
            "直近7日平均", "直近14日平均", "直近30日平均", "直近60日平均", "2025年度平均"
        ]
        
        for label in relevant_labels:
            if label not in df_weekday.index or label not in df_holiday.index:
                st.warning(f"基準期間 '{label}' のデータが平日または休日の集計にありません。スキップします。")
                continue
            
            # df_summary は実績計算で使用
            if label == "2025年度平均" and (df_summary is None or label not in df_summary.index):
                 st.warning(f"基準期間 '{label}' のデータが全日集計にありません（実績計算用）。スキップします。")
                 continue
                
            try:
                weekday_avg_series = df_weekday.loc[label]
                holiday_avg_series = df_holiday.loc[label]

                if "入院患者数（在院）" not in weekday_avg_series or pd.isna(weekday_avg_series["入院患者数（在院）"]) or \
                   "入院患者数（在院）" not in holiday_avg_series or pd.isna(holiday_avg_series["入院患者数（在院）"]):
                    st.warning(f"基準期間 '{label}' の入院患者数（在院）データ(平日/休日)が不足またはNaNです。スキップします。")
                    continue

                weekday_avg = weekday_avg_series["入院患者数（在院）"]
                holiday_avg = holiday_avg_series["入院患者数（在院）"]

                # NaN値の処理（上記でチェック済みだが念のため）
                weekday_avg = 0 if pd.isna(weekday_avg) else weekday_avg
                holiday_avg = 0 if pd.isna(holiday_avg) else holiday_avg

                # 将来の予測延べ患者数
                future_total = weekday_avg * num_weekdays + holiday_avg * num_holidays

                # 実績の計算（2025年度平均を使用）
                actual_total = 0
                if label == "2025年度平均": # 2025年度平均の場合のみ実績を加味する（他のラベルは将来の平均値としての予測）
                    if df_summary is not None and "2025年度平均" in df_summary.index and \
                       "入院患者数（在院）" in df_summary.loc["2025年度平均"] and \
                       not pd.isna(df_summary.loc["2025年度平均"]["入院患者数（在院）"]):
                        
                        actual_avg_2025 = df_summary.loc["2025年度平均"]["入院患者数（在院）"]
                        actual_total = actual_avg_2025 * elapsed_days_fy2025
                    else:
                        st.warning("2025年度平均の実績値が取得できないため、実績加算は0とします。")

                # 年間平均人日
                # 「2025年度平均」ラベルの場合のみ実績を含めて計算
                # それ以外のラベルは、その平均が将来も続いた場合の純粋な予測を示す
                if label == "2025年度平均":
                    total_for_avg = actual_total + future_total
                else:
                    # 他ラベルでは、その平均値が通年続いた場合の仮想的な年度平均
                    # もし「実績＋予測」という列名が誤解を招くなら、列名変更か計算方法の再考が必要
                    # ここでは、提供されたロジックに基づき、実績は2025年度平均の場合のみ加味
                    total_for_avg = (weekday_avg * (total_days_in_fy2025 * (num_weekdays / (num_weekdays + num_holidays + 1e-6)))) + \
                                  (holiday_avg * (total_days_in_fy2025 * (num_holidays / (num_weekdays + num_holidays + 1e-6))))


                forecast_avg_per_day = total_for_avg / total_days_in_fy2025 if total_days_in_fy2025 > 0 else 0

                forecast_rows.append({
                    "基準期間": label,
                    "平日平均": round(weekday_avg, 1),
                    "休日平均": round(holiday_avg, 1),
                    "残平日": int(num_weekdays),
                    "残休日": int(num_holidays),
                    "延べ予測人日": round(future_total, 0), # これは残日数に対する予測
                    "年間平均人日（実績＋予測）": round(forecast_avg_per_day, 1)
                })
                
            except KeyError as e_key:
                st.warning(f"予測計算中にキーエラーが発生しました (基準期間: {label}, 詳細: {str(e_key)})。この期間の予測をスキップします。")
                continue
            except Exception as e_inner:
                st.warning(f"予測計算中に予期せぬエラーが発生しました (基準期間: {label}, 詳細: {str(e_inner)})。この期間の予測をスキップします。")
                continue

        if not forecast_rows:
            st.warning("有効な予測結果を生成できませんでした。入力データや基準期間の設定を確認してください。")
            return pd.DataFrame()

        forecast_df = pd.DataFrame(forecast_rows)
        
        if not forecast_df.empty:
            # 2024年度関連を除外 (もし '2024年度平均' などがあれば)
            forecast_df = forecast_df[~forecast_df["基準期間"].str.contains("2024年度", na=False)]
            
            if not forecast_df.empty:
                forecast_df = forecast_df.set_index("基準期間")

        return forecast_df

    except Exception as e_outer:
        st.error(f"予測データフレーム作成処理の全体でエラーが発生しました: {str(e_outer)}")
        import traceback
        st.error(traceback.format_exc()) # 詳細なトレースバックを表示
        return pd.DataFrame()

# `calculate_fiscal_year_days`関数が同じファイル内に定義されているか、
# もしくは正しくインポートされている必要があります。
# 例:
def calculate_fiscal_year_days(year):
    """指定された年度の日数を計算する（うるう年考慮）"""
    start_date = pd.Timestamp(f"{year}-04-01")
    end_date = pd.Timestamp(f"{year+1}-03-31")
    return (end_date - start_date).days + 1