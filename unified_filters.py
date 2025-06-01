import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import logging

# utilsから必要な関数をインポート
from utils import (
    safe_date_filter,
    create_ward_display_options,
    create_dept_display_options,
    get_ward_display_name,
    get_display_name_for_dept
)

logger = logging.getLogger(__name__)

class UnifiedFilterManager:
    """統一フィルター管理クラス"""

    def __init__(self):
        self.session_prefix = "unified_filter_"
        self.config_key = f"{self.session_prefix}config"

    def initialize_default_filters(self, df):
        """デフォルトフィルター値の初期化"""
        if df is None or df.empty or '日付' not in df.columns:
            logger.warning("initialize_default_filters: 有効なデータフレームまたは日付列が見つかりません")
            return

        try:
            valid_dates = df['日付'].dropna()
            if valid_dates.empty:
                logger.warning("initialize_default_filters: 有効な日付データがありません")
                return

            max_date = valid_dates.max()
            min_date = valid_dates.min()

            default_start = max_date - pd.Timedelta(days=90) # 直近3ヶ月の開始日
            default_start = max(default_start, min_date)
            default_preset = "直近3ヶ月" # デフォルトのプリセット期間

            # セッションにデフォルト値を設定（既に値がない場合、または初期化フラグが立っていない場合）
            # initialized フラグで初回のみ実行されるように制御
            if not st.session_state.get(f"{self.session_prefix}initialized", False):
                st.session_state[f"{self.session_prefix}start_date"] = default_start
                st.session_state[f"{self.session_prefix}end_date"] = max_date
                st.session_state[f"{self.session_prefix}period_mode"] = "プリセット期間" # デフォルトモード
                st.session_state[f"{self.session_prefix}preset"] = default_preset # デフォルトプリセット
                st.session_state[f"{self.session_prefix}dept_mode"] = "全診療科"
                st.session_state[f"{self.session_prefix}ward_mode"] = "全病棟"
                # selected_depts や selected_wards は初回は空で良い、またはここで空リストを設定
                st.session_state[f"{self.session_prefix}selected_depts_display"] = [] # 表示名用
                st.session_state[f"{self.session_prefix}selected_wards_display"] = [] # 表示名用

                st.session_state[f"{self.session_prefix}initialized"] = True
                logger.info("統一フィルターのデフォルト値を初期化しました")
        except Exception as e:
            logger.error(f"initialize_default_filters でエラー: {e}", exc_info=True)


    def create_unified_sidebar(self, df):
        """統一フィルターサイドバーの作成"""
        if df is None or df.empty:
            # st.sidebar.error("📊 データが読み込まれていません") # app.py側で制御
            return None

        if '日付' not in df.columns:
            # st.sidebar.error("📅 日付列が見つかりません") # app.py側で制御
            return None

        self.initialize_default_filters(df) # 最初にデフォルト値を（必要なら）設定

        # st.sidebar.markdown("---") # app.py側で制御
        # st.sidebar.markdown("## 🔍 分析フィルター") # app.py側で制御 (st.sidebar.header)

        start_date, end_date = None, None # スコープ外エラーを避けるため初期化
        preset = None # 同上

        with st.sidebar.expander("📅 分析期間", expanded=True):
            # period_mode は initialize_default_filters で初期化されているはず
            current_period_mode = st.session_state.get(f"{self.session_prefix}period_mode", "プリセット期間")
            period_mode_options = ["プリセット期間", "カスタム期間"]
            try:
                period_mode_index = period_mode_options.index(current_period_mode)
            except ValueError:
                period_mode_index = 0 # 見つからなければデフォルト

            period_mode = st.radio(
                "期間選択方法",
                period_mode_options,
                index=period_mode_index, # セッションの値に基づいてindexを設定
                key=f"{self.session_prefix}period_mode_widget", # キーを少し変更して明確化
                help="プリセット期間で簡単選択、またはカスタム期間で詳細指定",
                on_change=self.update_session_from_widget, # セッションを更新するコールバック
                args=(f"{self.session_prefix}period_mode", f"{self.session_prefix}period_mode_widget")
            )
            st.session_state[f"{self.session_prefix}period_mode"] = period_mode # radioの戻り値をセッションに反映

            if period_mode == "プリセット期間":
                preset_options = ["直近1ヶ月", "直近3ヶ月", "直近6ヶ月", "直近12ヶ月", "全期間"]
                # セッションステートから現在のプリセット選択を取得
                current_preset = st.session_state.get(f"{self.session_prefix}preset", "直近3ヶ月")
                try:
                    preset_index = preset_options.index(current_preset)
                except ValueError:
                    preset_index = 1 # デフォルト "直近3ヶ月"

                preset_widget_key = f"{self.session_prefix}preset_widget"
                preset = st.selectbox(
                    "期間プリセット",
                    preset_options,
                    index=preset_index, # セッションの値に基づいてindexを設定
                    key=preset_widget_key,
                    help="よく使われる期間から選択",
                    on_change=self.update_session_from_widget,
                    args=(f"{self.session_prefix}preset", preset_widget_key)
                )
                st.session_state[f"{self.session_prefix}preset"] = preset # selectboxの戻り値をセッションに反映
                start_date, end_date = self._get_preset_dates(df, preset)

                if start_date and end_date:
                    period_days = (end_date - start_date).days + 1
                    st.info(f"📅 {start_date.strftime('%Y/%m/%d')} ～ {end_date.strftime('%Y/%m/%d')}\n（{period_days}日間）")
                else:
                    st.warning("プリセット期間の計算に失敗しました。")


            else: # カスタム期間
                data_min_dt = df['日付'].min().date()
                data_max_dt = df['日付'].max().date()

                # セッションから日付を取得、なければデフォルト計算
                session_start_date_val = st.session_state.get(f"{self.session_prefix}start_date")
                session_end_date_val = st.session_state.get(f"{self.session_prefix}end_date")

                default_start_dt_val = pd.Timestamp(session_start_date_val).date() if session_start_date_val else (data_max_dt - timedelta(days=90))
                default_end_dt_val = pd.Timestamp(session_end_date_val).date() if session_end_date_val else data_max_dt

                col1, col2 = st.columns(2)
                with col1:
                    custom_start_key = f"{self.session_prefix}custom_start_widget"
                    start_date_input = st.date_input(
                        "開始日",
                        value=max(default_start_dt_val, data_min_dt),
                        min_value=data_min_dt,
                        max_value=data_max_dt,
                        key=custom_start_key,
                        on_change=self.update_session_from_widget_date,
                        args=(f"{self.session_prefix}start_date", custom_start_key)
                    )
                    st.session_state[f"{self.session_prefix}start_date"] = pd.Timestamp(start_date_input)
                with col2:
                    custom_end_key = f"{self.session_prefix}custom_end_widget"
                    end_date_input = st.date_input(
                        "終了日",
                        value=min(default_end_dt_val, data_max_dt),
                        min_value=start_date_input, # 選択された開始日以降
                        max_value=data_max_dt,
                        key=custom_end_key,
                        on_change=self.update_session_from_widget_date,
                        args=(f"{self.session_prefix}end_date", custom_end_key)
                    )
                    st.session_state[f"{self.session_prefix}end_date"] = pd.Timestamp(end_date_input)

                start_date = pd.Timestamp(start_date_input)
                end_date = pd.Timestamp(end_date_input)

                if start_date > end_date:
                    st.error("⚠️ 開始日は終了日より前に設定してください")
                    # return None # エラー時は設定を返さない

        # 診療科選択セクション
        with st.sidebar.expander("🏥 診療科フィルター", expanded=False):
            dept_mode_options = ["全診療科", "特定診療科"]
            current_dept_mode = st.session_state.get(f"{self.session_prefix}dept_mode", "全診療科")
            try: dept_mode_index = dept_mode_options.index(current_dept_mode)
            except ValueError: dept_mode_index = 0

            dept_mode_widget_key = f"{self.session_prefix}dept_mode_widget"
            dept_filter_mode = st.radio(
                "診療科選択", dept_mode_options, index=dept_mode_index,
                key=dept_mode_widget_key,
                on_change=self.update_session_from_widget,
                args=(f"{self.session_prefix}dept_mode", dept_mode_widget_key)
            )
            st.session_state[f"{self.session_prefix}dept_mode"] = dept_filter_mode
            selected_depts_codes = [] # 実際のコードを格納

            if dept_filter_mode == "特定診療科":
                if '診療科名' in df.columns:
                    available_depts_actual = sorted(df['診療科名'].astype(str).unique())
                    dept_mapping_session = st.session_state.get('dept_mapping', {})
                    dept_options_display, dept_display_to_code_map = create_dept_display_options(available_depts_actual, dept_mapping_session)

                    # セッションから選択中の表示名を取得
                    current_selected_dept_displays = st.session_state.get(f"{self.session_prefix}selected_depts_display", [])
                    # 表示オプションに存在しないものは除去
                    valid_current_selected_dept_displays = [d for d in current_selected_dept_displays if d in dept_options_display]


                    selected_depts_widget_key = f"{self.session_prefix}selected_depts_widget"
                    selected_dept_displays_widget = st.multiselect(
                        "対象診療科", dept_options_display,
                        default=valid_current_selected_dept_displays,
                        key=selected_depts_widget_key,
                        help="分析対象とする診療科を選択（複数選択可）",
                        on_change=self.update_session_from_widget,
                        args=(f"{self.session_prefix}selected_depts_display", selected_depts_widget_key)
                    )
                    st.session_state[f"{self.session_prefix}selected_depts_display"] = selected_dept_displays_widget
                    selected_depts_codes = [dept_display_to_code_map[d] for d in selected_dept_displays_widget if d in dept_display_to_code_map]

                    if selected_dept_displays_widget: st.success(f"✅ {len(selected_depts_codes)}件の診療科を選択")
                    else: st.warning("⚠️ 診療科が選択されていません")
                else:
                    st.warning("📋 診療科名列が見つかりません")

        # 病棟選択セクション (診療科と同様の修正)
        with st.sidebar.expander("🏨 病棟フィルター", expanded=False):
            ward_mode_options = ["全病棟", "特定病棟"]
            current_ward_mode = st.session_state.get(f"{self.session_prefix}ward_mode", "全病棟")
            try: ward_mode_index = ward_mode_options.index(current_ward_mode)
            except ValueError: ward_mode_index = 0

            ward_mode_widget_key = f"{self.session_prefix}ward_mode_widget"
            ward_filter_mode = st.radio(
                "病棟選択", ward_mode_options, index=ward_mode_index,
                key=ward_mode_widget_key,
                on_change=self.update_session_from_widget,
                args=(f"{self.session_prefix}ward_mode", ward_mode_widget_key)
            )
            st.session_state[f"{self.session_prefix}ward_mode"] = ward_filter_mode
            selected_wards_codes = []

            if ward_filter_mode == "特定病棟":
                if '病棟コード' in df.columns:
                    available_wards_actual = sorted(df['病棟コード'].astype(str).unique())
                    ward_mapping_session = st.session_state.get('ward_mapping', {})
                    ward_options_display, ward_display_to_code_map = create_ward_display_options(available_wards_actual, ward_mapping_session)

                    current_selected_ward_displays = st.session_state.get(f"{self.session_prefix}selected_wards_display", [])
                    valid_current_selected_ward_displays = [w for w in current_selected_ward_displays if w in ward_options_display]

                    selected_wards_widget_key = f"{self.session_prefix}selected_wards_widget"
                    selected_ward_displays_widget = st.multiselect(
                        "対象病棟", ward_options_display,
                        default=valid_current_selected_ward_displays,
                        key=selected_wards_widget_key,
                        help="分析対象とする病棟を選択（複数選択可）",
                        on_change=self.update_session_from_widget,
                        args=(f"{self.session_prefix}selected_wards_display", selected_wards_widget_key)
                    )
                    st.session_state[f"{self.session_prefix}selected_wards_display"] = selected_ward_displays_widget
                    selected_wards_codes = [ward_display_to_code_map[w] for w in selected_ward_displays_widget if w in ward_display_to_code_map]

                    if selected_ward_displays_widget: st.success(f"✅ {len(selected_wards_codes)}件の病棟を選択")
                    else: st.warning("⚠️ 病棟が選択されていません")
                else:
                    st.warning("📋 病棟コード列が見つかりません")

        # フィルター情報
        filter_config_data = {
            'start_date': start_date if start_date else st.session_state.get(f"{self.session_prefix}start_date"),
            'end_date': end_date if end_date else st.session_state.get(f"{self.session_prefix}end_date"),
            'selected_depts': selected_depts_codes,
            'selected_wards': selected_wards_codes,
            'dept_filter_mode': dept_filter_mode,
            'ward_filter_mode': ward_filter_mode,
            'period_mode': period_mode,
            'preset': preset if period_mode == "プリセット期間" else None
        }
        st.session_state[self.config_key] = filter_config_data # 最新の設定をセッションに保存

        # st.sidebar.markdown("---") # app.py側で制御
        col_btn1, col_btn2 = st.sidebar.columns(2)
        with col_btn1:
            if st.button("🔄 適用", key=f"{self.session_prefix}apply_btn", help="フィルター設定を適用して再分析", use_container_width=True):
                logger.info("統一フィルターが適用されました")
                st.rerun()
        with col_btn2:
            if st.button("🗑️ リセット", key=f"{self.session_prefix}reset_btn", help="全てのフィルター設定をリセット", use_container_width=True):
                self._reset_filters() # 内部で initialize_default_filters を呼ぶように変更も検討
                # リセット後、再度 initialize_default_filters を呼んでデフォルト値を再設定
                self.initialize_default_filters(df) # df を渡す
                logger.info("統一フィルターがリセットされ、デフォルト値が再設定されました")
                st.rerun()

        return filter_config_data

    def update_session_from_widget(self, session_key, widget_key):
        """ウィジェットの値をセッションステートに反映するコールバック"""
        st.session_state[session_key] = st.session_state[widget_key]
        # プリセット期間が変更された場合、対応する日付も更新する必要がある
        if session_key == f"{self.session_prefix}preset":
            df_for_dates = st.session_state.get('df') # df を取得する必要がある
            if df_for_dates is not None:
                start_dt, end_dt = self._get_preset_dates(df_for_dates, st.session_state[widget_key])
                st.session_state[f"{self.session_prefix}start_date"] = start_dt
                st.session_state[f"{self.session_prefix}end_date"] = end_dt

    def update_session_from_widget_date(self, session_key, widget_key):
        """日付ウィジェットの値をTimestampとしてセッションステートに反映するコールバック"""
        st.session_state[session_key] = pd.Timestamp(st.session_state[widget_key])


    def _get_preset_dates(self, df, preset):
        # ... (この関数は変更なし) ...
        try:
            valid_dates = df['日付'].dropna()
            if valid_dates.empty: return None, None # 修正: データがない場合はNoneを返す
            max_date = valid_dates.max()
            min_date = valid_dates.min()

            if preset == "直近1ヶ月": start_date = max_date - pd.Timedelta(days=29) # 30日間なので29を引く
            elif preset == "直近3ヶ月": start_date = max_date - pd.Timedelta(days=89) # 90日間なので89を引く
            elif preset == "直近6ヶ月": start_date = max_date - pd.Timedelta(days=179) # 180日間
            elif preset == "直近12ヶ月": start_date = max_date - pd.Timedelta(days=364) # 365日間
            elif preset == "全期間": start_date = min_date
            else: start_date = min_date # 不明なプリセットの場合は全期間

            start_date = max(start_date, min_date) # データ開始日より前にはしない
            return start_date.normalize(), max_date.normalize()
        except Exception as e:
            logger.error(f"_get_preset_dates でエラー: {e}", exc_info=True)
            return None, None # エラー時もNoneを返す

    def _reset_filters(self):
        """フィルター設定をリセット (initialized フラグもリセット)"""
        try:
            keys_to_reset = [key for key in st.session_state.keys()
                            if key.startswith(self.session_prefix)]
            for key in keys_to_reset:
                del st.session_state[key]
            # `initialized` フラグも削除することで、次回 initialize_default_filters が呼ばれた際に
            # 再度デフォルト値が設定されるようにする
            if f"{self.session_prefix}initialized" in st.session_state:
                 del st.session_state[f"{self.session_prefix}initialized"]
            logger.info(f"{len(keys_to_reset)}個のフィルター設定をリセットしました（初期化フラグ含む）。")
        except Exception as e:
            logger.error(f"フィルターリセット中にエラー: {e}", exc_info=True)

    def apply_filters(self, df_original): # df -> df_original に変更
        # ... (この関数は変更なし) ...
        config = st.session_state.get(self.config_key)
        if not config:
            logger.warning("フィルター設定が見つかりません。元のデータフレームを返します。")
            return df_original

        try:
            # df_original が None または空の場合は、そのまま返す
            if df_original is None or df_original.empty:
                logger.warning("apply_filters: 元のデータフレームが空です。")
                return df_original

            # 期間フィルター
            # configの日付がTimestampであることを確認
            start_date_ts = pd.Timestamp(config['start_date']) if config.get('start_date') else None
            end_date_ts = pd.Timestamp(config['end_date']) if config.get('end_date') else None

            filtered_df = safe_date_filter(df_original, start_date_ts, end_date_ts)
            # original_count = len(df_original) # この行はログ用なので、ロガーレベルで調整
            # after_date_filter = len(filtered_df)

            # 診療科フィルター
            if config['dept_filter_mode'] == "特定診療科" and config['selected_depts']:
                if '診療科名' in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df['診療科名'].isin(config['selected_depts'])]
                    # after_dept_filter = len(filtered_df)
                    # logger.debug(f"診療科フィルター適用: {after_date_filter} → {after_dept_filter}行")

            # 病棟フィルター
            if config['ward_filter_mode'] == "特定病棟" and config['selected_wards']:
                if '病棟コード' in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df['病棟コード'].isin(config['selected_wards'])]
                    # final_count = len(filtered_df)
                    # logger.debug(f"病棟フィルター適用: 最終 {final_count}行")

            # logger.info(f"フィルター適用完了: {original_count} → {len(filtered_df)}行")
            return filtered_df

        except Exception as e:
            logger.error(f"フィルター適用中にエラー: {e}", exc_info=True)
            if 'st' in globals() and hasattr(st, 'sidebar') and hasattr(st.sidebar, 'error'): # Streamlitコンテキスト確認
                st.sidebar.error(f"フィルター適用エラー: {e}")
            return df_original


    def get_filter_summary(self):
        # ... (この関数は変更なし) ...
        config = st.session_state.get(self.config_key)
        if not config:
            return "📋 フィルター未設定"
        try:
            summary = []
            start_date_ts = pd.Timestamp(config['start_date']) if config.get('start_date') else None
            end_date_ts = pd.Timestamp(config['end_date']) if config.get('end_date') else None

            if start_date_ts and end_date_ts:
                start = start_date_ts.strftime('%Y/%m/%d')
                end = end_date_ts.strftime('%Y/%m/%d')
                period_days = (end_date_ts - start_date_ts).days + 1
                if config.get('period_mode') == "プリセット期間" and config.get('preset'):
                    summary.append(f"📅 期間: {config['preset']} ({start}～{end}, {period_days}日間)")
                else:
                    summary.append(f"📅 期間: {start}～{end} ({period_days}日間)")
            else:
                summary.append("📅 期間: 未設定")

            if config['dept_filter_mode'] == "特定診療科":
                dept_count = len(config['selected_depts'])
                summary.append(f"🏥 診療科: {dept_count}件選択" if dept_count > 0 else "🏥 診療科: 選択なし")
            else:
                summary.append("🏥 診療科: 全て")
            if config['ward_filter_mode'] == "特定病棟":
                ward_count = len(config['selected_wards'])
                summary.append(f"🏨 病棟: {ward_count}件選択" if ward_count > 0 else "🏨 病棟: 選択なし")
            else:
                summary.append("🏨 病棟: 全て")
            return " | ".join(summary)
        except Exception as e:
            logger.error(f"get_filter_summary でエラー: {e}", exc_info=True)
            return "📋 フィルター情報取得エラー"


    def get_config(self):
        return st.session_state.get(self.config_key)

    def validate_filters(self, df_for_validation): # df -> df_for_validation に変更
        # ... (この関数は df を引数に取らないように修正したが、もし df が必要なら元に戻す) ...
        # dfは_get_preset_datesなどで日付範囲のmin/max取得に利用されるため、引数として渡す方が良い
        config = st.session_state.get(self.config_key)
        if not config: return False, "フィルター設定が見つかりません"
        
        start_date_ts = pd.Timestamp(config.get('start_date')) if config.get('start_date') else None
        end_date_ts = pd.Timestamp(config.get('end_date')) if config.get('end_date') else None

        if not start_date_ts or not end_date_ts: return False, "開始日または終了日が設定されていません"
        if start_date_ts > end_date_ts: return False, "開始日が終了日より後になっています"
        if config['dept_filter_mode'] == "特定診療科" and not config['selected_depts']: return False, "特定診療科が選択されていますが、診療科が選択されていません"
        if config['ward_filter_mode'] == "特定病棟" and not config['selected_wards']: return False, "特定病棟が選択されていますが、病棟が選択されていません"
        return True, "フィルター設定は有効です"


# グローバルインスタンス (変更なし)
filter_manager = UnifiedFilterManager()

# 外部関数 (変更なし)
def create_unified_filter_sidebar(df):
    return filter_manager.create_unified_sidebar(df)
def apply_unified_filters(df):
    return filter_manager.apply_filters(df)
def get_unified_filter_summary():
    return filter_manager.get_filter_summary()
def initialize_unified_filters(df):
    return filter_manager.initialize_default_filters(df)
def get_unified_filter_config():
    return filter_manager.get_config()
def validate_unified_filters(df): # dfを引数に取るように戻す
    return filter_manager.validate_filters(df)