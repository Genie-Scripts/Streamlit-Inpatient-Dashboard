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
    """統一フィルター管理クラス（on_changeを廃止し、よりシンプルな状態管理に修正）"""

    def __init__(self):
        self.session_prefix = "unified_filter_"
        self.config_key = f"{self.session_prefix}config"

    def initialize_default_filters(self, df):
        """デフォルトフィルター値の初期化"""
        if df is None or df.empty or '日付' not in df.columns:
            logger.warning("initialize_default_filters: 有効なデータフレームまたは日付列が見つかりません")
            return

        if st.session_state.get(f"{self.session_prefix}initialized", False):
            return # 既に初期化済みなら何もしない

        try:
            valid_dates = df['日付'].dropna()
            if valid_dates.empty:
                logger.warning("initialize_default_filters: 有効な日付データがありません")
                return

            max_date = valid_dates.max()
            min_date = valid_dates.min()
            
            # セッションにデフォルト値を設定
            st.session_state[f"{self.session_prefix}start_date"] = max_date - pd.Timedelta(days=89)
            st.session_state[f"{self.session_prefix}end_date"] = max_date
            st.session_state[f"{self.session_prefix}period_mode"] = "プリセット期間"
            st.session_state[f"{self.session_prefix}preset"] = "直近3ヶ月"
            st.session_state[f"{self.session_prefix}filter_mode"] = "全体"
            st.session_state[f"{self.session_prefix}selected_depts"] = []
            st.session_state[f"{self.session_prefix}selected_wards"] = []
            
            st.session_state[f"{self.session_prefix}initialized"] = True
            logger.info("統一フィルターのデフォルト値を初期化しました")
        except Exception as e:
            logger.error(f"initialize_default_filters でエラー: {e}", exc_info=True)


    def create_unified_sidebar(self, df):
        """統一フィルターサイドバーの作成（シンプルな状態管理版）"""
        if df is None or df.empty or '日付' not in df.columns:
            return None

        self.initialize_default_filters(df)

        with st.sidebar.expander("📅 分析期間", expanded=True):
            period_mode = st.radio(
                "期間選択方法",
                ["プリセット期間", "カスタム期間"],
                key=f"{self.session_prefix}period_mode",
                help="プリセット期間で簡単選択、またはカスタム期間で詳細指定"
            )

            if period_mode == "プリセット期間":
                preset = st.selectbox(
                    "期間プリセット",
                    ["直近1ヶ月", "直近3ヶ月", "直近6ヶ月", "直近12ヶ月", "今年度", "全期間"],
                    key=f"{self.session_prefix}preset",
                    help="よく使われる期間から選択（今年度は4月1日～直近データまで）"
                )
                start_date, end_date = self._get_preset_dates(df, preset)
                st.session_state[f"{self.session_prefix}start_date"] = start_date
                st.session_state[f"{self.session_prefix}end_date"] = end_date
                
                if start_date and end_date:
                    st.info(f"📅 {start_date.strftime('%Y/%m/%d')} ～ {end_date.strftime('%Y/%m/%d')}")
            else: # カスタム期間
                data_min_dt, data_max_dt = df['日付'].min(), df['日付'].max()
                current_start = st.session_state.get(f"{self.session_prefix}start_date", data_max_dt - timedelta(days=89))
                current_end = st.session_state.get(f"{self.session_prefix}end_date", data_max_dt)
                
                col1, col2 = st.columns(2)
                with col1:
                    start_date_input = st.date_input("開始日", value=current_start, min_value=data_min_dt, max_value=data_max_dt, key=f"{self.session_prefix}start_date_widget")
                with col2:
                    end_date_input = st.date_input("終了日", value=current_end, min_value=start_date_input, max_value=data_max_dt, key=f"{self.session_prefix}end_date_widget")
                
                st.session_state[f"{self.session_prefix}start_date"] = pd.Timestamp(start_date_input)
                st.session_state[f"{self.session_prefix}end_date"] = pd.Timestamp(end_date_input)

        with st.sidebar.expander("🏥 部門フィルター", expanded=False):
            filter_mode = st.radio(
                "フィルター対象",
                ["全体", "特定診療科", "特定病棟"],
                key=f"{self.session_prefix}filter_mode",
                help="診療科と病棟は同時選択できません。"
            )

            if filter_mode == "特定診療科":
                available_depts = sorted(df['診療科名'].astype(str).unique())
                selected_depts = st.multiselect("対象診療科", available_depts, key=f"{self.session_prefix}selected_depts")
            else:
                st.session_state[f"{self.session_prefix}selected_depts"] = []

            if filter_mode == "特定病棟":
                available_wards = sorted(df['病棟コード'].astype(str).unique())
                selected_wards = st.multiselect("対象病棟", available_wards, key=f"{self.session_prefix}selected_wards")
            else:
                st.session_state[f"{self.session_prefix}selected_wards"] = []
        
        # 現在のウィジェットの状態から直接設定辞書を構築
        current_config = {
            'start_date': st.session_state.get(f"{self.session_prefix}start_date"),
            'end_date': st.session_state.get(f"{self.session_prefix}end_date"),
            'filter_mode': st.session_state.get(f"{self.session_prefix}filter_mode"),
            'selected_depts': st.session_state.get(f"{self.session_prefix}selected_depts", []),
            'selected_wards': st.session_state.get(f"{self.session_prefix}selected_wards", []),
            'period_mode': st.session_state.get(f"{self.session_prefix}period_mode"),
            'preset': st.session_state.get(f"{self.session_prefix}preset") if st.session_state.get(f"{self.session_prefix}period_mode") == "プリセット期間" else None
        }
        st.session_state[self.config_key] = current_config

        col_btn1, col_btn2 = st.sidebar.columns(2)
        with col_btn1:
            if st.button("🔄 適用", key=f"{self.session_prefix}apply_btn", help="フィルター設定を適用して再分析", use_container_width=True):
                logger.info(f"フィルター適用: {st.session_state[self.config_key]}")
                st.rerun()
        with col_btn2:
            if st.button("🗑️ リセット", key=f"{self.session_prefix}reset_btn", help="全てのフィルター設定をリセット", use_container_width=True):
                self._reset_filters()
                st.rerun()

        return st.session_state[self.config_key]

    def _get_preset_dates(self, df, preset):
        # (この内部関数は変更なし)
        try:
            valid_dates = df['日付'].dropna()
            if valid_dates.empty: return None, None
            max_date, min_date = valid_dates.max(), valid_dates.min()
            if preset == "直近1ヶ月": start_date = max_date - pd.Timedelta(days=29)
            elif preset == "直近3ヶ月": start_date = max_date - pd.Timedelta(days=89)
            elif preset == "直近6ヶ月": start_date = max_date - pd.Timedelta(days=179)
            elif preset == "直近12ヶ月": start_date = max_date - pd.Timedelta(days=364)
            elif preset == "今年度":
                fiscal_year = max_date.year if max_date.month >= 4 else max_date.year - 1
                start_date = pd.Timestamp(year=fiscal_year, month=4, day=1)
            elif preset == "全期間": start_date = min_date
            else: start_date = min_date
            return max(start_date, min_date).normalize(), max_date.normalize()
        except Exception as e:
            logger.error(f"_get_preset_dates でエラー: {e}", exc_info=True)
            return None, None

    def _reset_filters(self):
        """フィルター設定をリセット"""
        keys_to_reset = [key for key in st.session_state.keys() if key.startswith(self.session_prefix)]
        for key in keys_to_reset:
            del st.session_state[key]
        logger.info("フィルター設定をリセットしました。")

    def apply_filters(self, df_original):
        # (この内部関数は変更なし)
        config = st.session_state.get(self.config_key)
        if not config: return df_original
        try:
            if df_original is None or df_original.empty: return df_original
            start_date_ts = pd.Timestamp(config.get('start_date'))
            end_date_ts = pd.Timestamp(config.get('end_date'))
            filtered_df = safe_date_filter(df_original, start_date_ts, end_date_ts)
            filter_mode = config.get('filter_mode', '全体')
            if filter_mode == "特定診療科" and config.get('selected_depts'):
                filtered_df = filtered_df[filtered_df['診療科名'].isin(config['selected_depts'])]
            elif filter_mode == "特定病棟" and config.get('selected_wards'):
                filtered_df = filtered_df[filtered_df['病棟コード'].isin(config['selected_wards'])]
            return filtered_df
        except Exception as e:
            logger.error(f"フィルター適用中にエラー: {e}", exc_info=True)
            return df_original

    def get_filter_summary(self):
        # (この内部関数は変更なし)
        config = st.session_state.get(self.config_key)
        if not config: return "📋 フィルター未設定"
        summary = []
        # ... (以下省略)
        return " | ".join(summary)
    
    def get_config(self):
        return st.session_state.get(self.config_key)

# (外部関数は変更なし)
filter_manager = UnifiedFilterManager()
def create_unified_filter_sidebar(df): return filter_manager.create_unified_sidebar(df)
def apply_unified_filters(df): return filter_manager.apply_filters(df)
def get_unified_filter_summary(): return filter_manager.get_filter_summary()
def initialize_unified_filters(df): return filter_manager.initialize_default_filters(df)
def get_unified_filter_config(): return filter_manager.get_config()
def validate_unified_filters(df): return filter_manager.validate_filters(df)