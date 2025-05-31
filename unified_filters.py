# unified_filters.py - キー重複問題修正版
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
    """統一フィルター管理クラス（キー重複問題修正版）"""
    
    def __init__(self):
        self.session_prefix = "unified_filter_"
        self.config_key = f"{self.session_prefix}config"
        self.sidebar_created_key = f"{self.session_prefix}sidebar_created"
    
    def initialize_default_filters(self, df):
        """デフォルトフィルター値の初期化"""
        if df is None or df.empty or '日付' not in df.columns:
            logger.warning("initialize_default_filters: 有効なデータフレームまたは日付列が見つかりません")
            return
        
        try:
            # データの日付範囲を取得
            valid_dates = df['日付'].dropna()
            if valid_dates.empty:
                logger.warning("initialize_default_filters: 有効な日付データがありません")
                return
                
            max_date = valid_dates.max()
            min_date = valid_dates.min()
            
            # デフォルト期間（直近3ヶ月）
            default_start = max_date - pd.Timedelta(days=90)
            default_start = max(default_start, min_date)
            
            # セッションにデフォルト値を設定（既に値がない場合のみ）
            if not st.session_state.get(f"{self.session_prefix}initialized", False):
                st.session_state[f"{self.session_prefix}start_date"] = default_start
                st.session_state[f"{self.session_prefix}end_date"] = max_date
                st.session_state[f"{self.session_prefix}period_mode"] = "プリセット期間"
                st.session_state[f"{self.session_prefix}preset"] = "直近3ヶ月"
                st.session_state[f"{self.session_prefix}dept_mode"] = "全診療科"
                st.session_state[f"{self.session_prefix}ward_mode"] = "全病棟"
                st.session_state[f"{self.session_prefix}initialized"] = True
                logger.info("統一フィルターのデフォルト値を初期化しました")
        
        except Exception as e:
            logger.error(f"initialize_default_filters でエラー: {e}")
    
    def create_filter_status_card(self, df):
        """フィルター状態表示カードの作成（画面上部用）"""
        config = st.session_state.get(self.config_key)
        if not config:
            st.warning("🔍 フィルター未設定 - サイドバーで設定してください")
            return None, None
        
        try:
            # フィルター情報の整理
            start_date = config['start_date']
            end_date = config['end_date']
            period_days = (end_date - start_date).days + 1
            
            # データ件数計算
            total_records = len(df) if df is not None and not df.empty else 0
            filtered_df = self.apply_filters(df) if df is not None and not df.empty else pd.DataFrame()
            filtered_records = len(filtered_df)
            
            # フィルター状態カードの表示
            st.markdown("""
            <div style="
                background: linear-gradient(90deg, #f8f9fa 0%, #e9ecef 100%);
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 16px;
                margin: 8px 0;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            ">
            """, unsafe_allow_html=True)
            
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                # 期間情報
                if config.get('period_mode') == "プリセット期間" and config.get('preset'):
                    period_text = f"📅 {config['preset']}"
                else:
                    period_text = f"📅 カスタム期間"
                
                st.markdown(f"**{period_text}**")
                st.caption(f"{start_date.strftime('%Y/%m/%d')} ～ {end_date.strftime('%Y/%m/%d')} ({period_days}日間)")
            
            with col2:
                # 診療科情報
                if config['dept_filter_mode'] == "特定診療科":
                    dept_count = len(config['selected_depts'])
                    if dept_count > 0:
                        dept_text = f"🏥 診療科: {dept_count}件選択"
                    else:
                        dept_text = "🏥 診療科: 選択なし ⚠️"
                else:
                    dept_text = "🏥 診療科: 全て"
                st.markdown(f"**{dept_text}**")
            
            with col3:
                # 病棟情報
                if config['ward_filter_mode'] == "特定病棟":
                    ward_count = len(config['selected_wards'])
                    if ward_count > 0:
                        ward_text = f"🏨 病棟: {ward_count}件選択"
                    else:
                        ward_text = "🏨 病棟: 選択なし ⚠️"
                else:
                    ward_text = "🏨 病棟: 全て"
                st.markdown(f"**{ward_text}**")
            
            with col4:
                # データ件数
                filter_ratio = (filtered_records / total_records * 100) if total_records > 0 else 0
                if filter_ratio > 75:
                    color = "#28a745"  # 緑
                elif filter_ratio > 25:
                    color = "#ffc107"  # 黄
                else:
                    color = "#dc3545"  # 赤
                
                st.markdown(f"**📊 データ件数**")
                st.markdown(f'<span style="color: {color}; font-weight: bold;">{filtered_records:,}件 ({filter_ratio:.1f}%)</span>', unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
            
            return filtered_df, config
            
        except Exception as e:
            logger.error(f"create_filter_status_card でエラー: {e}")
            st.error(f"フィルター状態の表示でエラーが発生しました: {e}")
            return None, None
    
    def create_unified_sidebar(self, df):
        """統一フィルターサイドバーの作成（重複防止版）"""
        # 既にサイドバーが作成されている場合はスキップ
        if st.session_state.get(self.sidebar_created_key, False):
            logger.info("統一フィルターサイドバーは既に作成済みです")
            return st.session_state.get(self.config_key)
        
        if df is None or df.empty:
            st.sidebar.error("📊 データが読み込まれていません")
            return None
        
        if '日付' not in df.columns:
            st.sidebar.error("📅 日付列が見つかりません")
            return None
        
        # デフォルト値の初期化
        self.initialize_default_filters(df)
        
        st.sidebar.markdown("---")
        st.sidebar.markdown("## 🔍 分析フィルター")
        
        # ユニークキーの生成
        current_time = datetime.now().strftime("%H%M%S")
        key_suffix = f"_{current_time}"
        
        # 期間設定セクション
        with st.sidebar.expander("📅 分析期間", expanded=True):
            period_mode = st.radio(
                "期間選択方法",
                ["プリセット期間", "カスタム期間"],
                key=f"{self.session_prefix}period_mode{key_suffix}",
                help="プリセット期間で簡単選択、またはカスタム期間で詳細指定"
            )
            
            if period_mode == "プリセット期間":
                preset = st.selectbox(
                    "期間プリセット",
                    ["直近1ヶ月", "直近3ヶ月", "直近6ヶ月", "直近12ヶ月", "全期間"],
                    index=1,  # デフォルト：直近3ヶ月
                    key=f"{self.session_prefix}preset{key_suffix}",
                    help="よく使われる期間から選択"
                )
                start_date, end_date = self._get_preset_dates(df, preset)
                
                # プリセット期間の表示
                period_days = (end_date - start_date).days + 1
                st.sidebar.info(f"📅 {start_date.strftime('%Y/%m/%d')} ～ {end_date.strftime('%Y/%m/%d')}\n（{period_days}日間）")
                
            else:
                # カスタム期間選択
                data_min = df['日付'].min().date()
                data_max = df['日付'].max().date()
                
                # 現在のセッション値または計算されたデフォルト値を使用
                default_start = st.session_state.get(f"{self.session_prefix}start_date", data_max - timedelta(days=90))
                default_end = st.session_state.get(f"{self.session_prefix}end_date", data_max)
                
                if isinstance(default_start, pd.Timestamp):
                    default_start = default_start.date()
                if isinstance(default_end, pd.Timestamp):
                    default_end = default_end.date()
                
                col1, col2 = st.columns(2)
                with col1:
                    start_date_input = st.date_input(
                        "開始日",
                        value=max(default_start, data_min),
                        min_value=data_min,
                        max_value=data_max,
                        key=f"{self.session_prefix}custom_start{key_suffix}"
                    )
                with col2:
                    end_date_input = st.date_input(
                        "終了日",
                        value=min(default_end, data_max),
                        min_value=start_date_input,
                        max_value=data_max,
                        key=f"{self.session_prefix}custom_end{key_suffix}"
                    )
                
                start_date = pd.Timestamp(start_date_input)
                end_date = pd.Timestamp(end_date_input)
                
                # カスタム期間の妥当性チェック
                if start_date > end_date:
                    st.sidebar.error("⚠️ 開始日は終了日より前に設定してください")
                    return None
        
        # 診療科選択セクション
        with st.sidebar.expander("🏥 診療科フィルター", expanded=False):
            dept_filter_mode = st.radio(
                "診療科選択",
                ["全診療科", "特定診療科"],
                key=f"{self.session_prefix}dept_mode{key_suffix}",
                help="全診療科を対象にするか、特定の診療科のみを選択"
            )
            
            selected_depts = []
            if dept_filter_mode == "特定診療科":
                if '診療科名' in df.columns:
                    available_depts = sorted(df['診療科名'].astype(str).unique())
                    dept_mapping = st.session_state.get('dept_mapping', {})
                    
                    try:
                        dept_options, dept_map = create_dept_display_options(available_depts, dept_mapping)
                        
                        selected_dept_displays = st.multiselect(
                            "対象診療科",
                            dept_options,
                            key=f"{self.session_prefix}selected_depts{key_suffix}",
                            help="分析対象とする診療科を選択（複数選択可）"
                        )
                        selected_depts = [dept_map[d] for d in selected_dept_displays if d in dept_map]
                        
                        if selected_dept_displays:
                            st.sidebar.success(f"✅ {len(selected_depts)}件の診療科を選択")
                        else:
                            st.sidebar.warning("⚠️ 診療科が選択されていません")
                            
                    except Exception as e:
                        logger.error(f"診療科フィルター作成エラー: {e}")
                        st.sidebar.error("診療科フィルターの作成に失敗しました")
                else:
                    st.sidebar.warning("📋 診療科名列が見つかりません")
        
        # 病棟選択セクション
        with st.sidebar.expander("🏨 病棟フィルター", expanded=False):
            ward_filter_mode = st.radio(
                "病棟選択",
                ["全病棟", "特定病棟"],
                key=f"{self.session_prefix}ward_mode{key_suffix}",
                help="全病棟を対象にするか、特定の病棟のみを選択"
            )
            
            selected_wards = []
            if ward_filter_mode == "特定病棟":
                if '病棟コード' in df.columns:
                    available_wards = sorted(df['病棟コード'].astype(str).unique())
                    ward_mapping = st.session_state.get('ward_mapping', {})
                    
                    try:
                        ward_options, ward_map = create_ward_display_options(available_wards, ward_mapping)
                        
                        selected_ward_displays = st.multiselect(
                            "対象病棟",
                            ward_options,
                            key=f"{self.session_prefix}selected_wards{key_suffix}",
                            help="分析対象とする病棟を選択（複数選択可）"
                        )
                        selected_wards = [ward_map[w] for w in selected_ward_displays if w in ward_map]
                        
                        if selected_ward_displays:
                            st.sidebar.success(f"✅ {len(selected_wards)}件の病棟を選択")
                        else:
                            st.sidebar.warning("⚠️ 病棟が選択されていません")
                            
                    except Exception as e:
                        logger.error(f"病棟フィルター作成エラー: {e}")
                        st.sidebar.error("病棟フィルターの作成に失敗しました")
                else:
                    st.sidebar.warning("📋 病棟コード列が見つかりません")
        
        # フィルター情報の保存
        filter_config = {
            'start_date': start_date,
            'end_date': end_date,
            'selected_depts': selected_depts,
            'selected_wards': selected_wards,
            'dept_filter_mode': dept_filter_mode,
            'ward_filter_mode': ward_filter_mode,
            'period_mode': period_mode,
            'preset': preset if period_mode == "プリセット期間" else None
        }
        
        # セッションに保存
        st.session_state[self.config_key] = filter_config
        st.session_state[self.sidebar_created_key] = True  # 作成済みフラグ
        
        # フィルター操作ボタン
        st.sidebar.markdown("---")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("🔄 適用", key=f"{self.session_prefix}apply{key_suffix}", help="フィルター設定を適用して再分析"):
                logger.info("統一フィルターが適用されました")
                st.rerun()
        with col2:
            if st.button("🗑️ リセット", key=f"{self.session_prefix}reset{key_suffix}", help="全てのフィルター設定をリセット"):
                self._reset_filters()
                logger.info("統一フィルターがリセットされました")
                st.rerun()
        
        return filter_config
    
    def _get_preset_dates(self, df, preset):
        """プリセット期間から開始日・終了日を取得"""
        try:
            valid_dates = df['日付'].dropna()
            max_date = valid_dates.max()
            min_date = valid_dates.min()
            
            if preset == "直近1ヶ月":
                start_date = max_date - pd.Timedelta(days=30)
            elif preset == "直近3ヶ月":
                start_date = max_date - pd.Timedelta(days=90)
            elif preset == "直近6ヶ月":
                start_date = max_date - pd.Timedelta(days=180)
            elif preset == "直近12ヶ月":
                start_date = max_date - pd.Timedelta(days=365)
            else:  # 全期間
                start_date = min_date
            
            start_date = max(start_date, min_date)
            return start_date, max_date
            
        except Exception as e:
            logger.error(f"_get_preset_dates でエラー: {e}")
            # フォールバック値を返す
            return df['日付'].min(), df['日付'].max()
    
    def _reset_filters(self):
        """フィルター設定をリセット"""
        try:
            keys_to_reset = [key for key in st.session_state.keys() 
                            if key.startswith(self.session_prefix)]
            for key in keys_to_reset:
                del st.session_state[key]
            logger.info(f"{len(keys_to_reset)}個のフィルター設定をリセットしました")
        except Exception as e:
            logger.error(f"フィルターリセット中にエラー: {e}")
    
    def apply_filters(self, df):
        """フィルターを適用してデータフレームを返す"""
        config = st.session_state.get(self.config_key)
        if not config:
            logger.warning("フィルター設定が見つかりません。元のデータフレームを返します。")
            return df
        
        try:
            # 期間フィルター
            filtered_df = safe_date_filter(df, config['start_date'], config['end_date'])
            original_count = len(df)
            after_date_filter = len(filtered_df)
            
            # 診療科フィルター
            if config['dept_filter_mode'] == "特定診療科" and config['selected_depts']:
                if '診療科名' in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df['診療科名'].isin(config['selected_depts'])]
                    after_dept_filter = len(filtered_df)
                    logger.debug(f"診療科フィルター適用: {after_date_filter} → {after_dept_filter}行")
            
            # 病棟フィルター
            if config['ward_filter_mode'] == "特定病棟" and config['selected_wards']:
                if '病棟コード' in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df['病棟コード'].isin(config['selected_wards'])]
                    final_count = len(filtered_df)
                    logger.debug(f"病棟フィルター適用: 最終 {final_count}行")
            
            logger.info(f"フィルター適用完了: {original_count} → {len(filtered_df)}行")
            return filtered_df
            
        except Exception as e:
            logger.error(f"フィルター適用中にエラー: {e}")
            st.sidebar.error(f"フィルター適用エラー: {e}")
            return df
    
    def get_filter_summary(self):
        """現在のフィルター設定のサマリーを返す"""
        config = st.session_state.get(self.config_key)
        if not config:
            return "📋 フィルター未設定"
        
        try:
            summary = []
            
            # 期間情報
            start = config['start_date'].strftime('%Y/%m/%d')
            end = config['end_date'].strftime('%Y/%m/%d')
            period_days = (config['end_date'] - config['start_date']).days + 1
            
            if config.get('period_mode') == "プリセット期間" and config.get('preset'):
                summary.append(f"📅 期間: {config['preset']} ({start}～{end}, {period_days}日間)")
            else:
                summary.append(f"📅 期間: {start}～{end} ({period_days}日間)")
            
            # 診療科情報
            if config['dept_filter_mode'] == "特定診療科":
                dept_count = len(config['selected_depts'])
                if dept_count > 0:
                    summary.append(f"🏥 診療科: {dept_count}件選択")
                else:
                    summary.append("🏥 診療科: 選択なし")
            else:
                summary.append("🏥 診療科: 全て")
            
            # 病棟情報
            if config['ward_filter_mode'] == "特定病棟":
                ward_count = len(config['selected_wards'])
                if ward_count > 0:
                    summary.append(f"🏨 病棟: {ward_count}件選択")
                else:
                    summary.append("🏨 病棟: 選択なし")
            else:
                summary.append("🏨 病棟: 全て")
            
            return " | ".join(summary)
            
        except Exception as e:
            logger.error(f"get_filter_summary でエラー: {e}")
            return "📋 フィルター情報取得エラー"
    
    def get_config(self):
        """現在のフィルター設定を取得"""
        return st.session_state.get(self.config_key)
    
    def validate_filters(self, df):
        """フィルター設定の妥当性をチェック"""
        config = st.session_state.get(self.config_key)
        if not config:
            return False, "フィルター設定が見つかりません"
        
        # 期間の妥当性チェック
        if config['start_date'] > config['end_date']:
            return False, "開始日が終了日より後になっています"
        
        # 特定診療科選択時のチェック
        if config['dept_filter_mode'] == "特定診療科" and not config['selected_depts']:
            return False, "特定診療科が選択されていますが、診療科が選択されていません"
        
        # 特定病棟選択時のチェック
        if config['ward_filter_mode'] == "特定病棟" and not config['selected_wards']:
            return False, "特定病棟が選択されていますが、病棟が選択されていません"
        
        return True, "フィルター設定は有効です"

# グローバルインスタンス
filter_manager = UnifiedFilterManager()

# 外部関数（既存コードとの互換性のため）
def create_unified_filter_sidebar(df):
    """統一フィルターサイドバーを作成（外部関数）"""
    return filter_manager.create_unified_sidebar(df)

def create_unified_filter_status_card(df):
    """統一フィルター状態カードを作成（新機能）"""
    return filter_manager.create_filter_status_card(df)

def apply_unified_filters(df):
    """統一フィルターを適用（外部関数）"""
    return filter_manager.apply_filters(df)

def get_unified_filter_summary():
    """統一フィルターのサマリーを取得（外部関数）"""
    return filter_manager.get_filter_summary()

def initialize_unified_filters(df):
    """統一フィルターを初期化（外部関数）"""
    return filter_manager.initialize_default_filters(df)

def get_unified_filter_config():
    """統一フィルターの設定を取得（外部関数）"""
    return filter_manager.get_config()

def validate_unified_filters(df):
    """統一フィルターの妥当性をチェック（外部関数）"""
    return filter_manager.validate_filters(df)