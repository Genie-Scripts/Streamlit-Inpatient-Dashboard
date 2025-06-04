# data_processing_tab.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import traceback

# utilsから必要な関数をインポート
from utils import initialize_all_mappings

# unified_filtersから必要な関数をインポート
try:
    from unified_filters import initialize_unified_filters
except ImportError:
    initialize_unified_filters = None

# data_persistenceから必要な関数をインポート
try:
    from data_persistence import save_data_to_file
except ImportError:
    save_data_to_file = None

logger = logging.getLogger(__name__)

def validate_uploaded_data(df):
    """
    アップロードされたデータの妥当性をチェック
    
    Args:
        df (pd.DataFrame): チェック対象のデータフレーム
        
    Returns:
        dict: バリデーション結果
    """
    validation_results = {
        'is_valid': True,
        'warnings': [],
        'errors': [],
        'info': []
    }
    
    try:
        # 基本的なデータ構造チェック
        if df is None or df.empty:
            validation_results['errors'].append("データが空です")
            validation_results['is_valid'] = False
            return validation_results
        
        # 必須列のチェック
        required_columns = ['日付']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            validation_results['errors'].append(f"必須列が不足しています: {', '.join(missing_columns)}")
            validation_results['is_valid'] = False
        
        # 日付列のチェック
        if '日付' in df.columns:
            # 日付として変換可能かチェック
            try:
                date_series = pd.to_datetime(df['日付'], errors='coerce')
                invalid_dates = date_series.isna().sum()
                if invalid_dates > 0:
                    validation_results['warnings'].append(f"無効な日付データが{invalid_dates}件あります（除外されます）")
                
                # 日付範囲のチェック
                valid_dates = date_series.dropna()
                if not valid_dates.empty:
                    min_date = valid_dates.min()
                    max_date = valid_dates.max()
                    date_range = (max_date - min_date).days
                    
                    if date_range > 3650:  # 10年以上
                        validation_results['warnings'].append(f"データ期間が長すぎます（{date_range}日間）")
                    
                    validation_results['info'].append(f"データ期間: {min_date.strftime('%Y/%m/%d')} ～ {max_date.strftime('%Y/%m/%d')} ({date_range + 1}日間)")
                
            except Exception as e:
                validation_results['errors'].append(f"日付列の処理でエラー: {str(e)}")
                validation_results['is_valid'] = False
        
        # 推奨列のチェック
        recommended_columns = ['病棟コード', '診療科名', '在院患者数', '入院患者数', '退院患者数']
        missing_recommended = [col for col in recommended_columns if col not in df.columns]
        if missing_recommended:
            validation_results['warnings'].append(f"推奨列が不足しています: {', '.join(missing_recommended)}")
        
        # データ型のチェック
        numeric_columns = ['在院患者数', '入院患者数', '退院患者数']
        for col in numeric_columns:
            if col in df.columns:
                try:
                    numeric_data = pd.to_numeric(df[col], errors='coerce')
                    invalid_numeric = numeric_data.isna().sum()
                    if invalid_numeric > 0:
                        validation_results['warnings'].append(f"{col}列に数値でないデータが{invalid_numeric}件あります")
                except Exception as e:
                    validation_results['warnings'].append(f"{col}列の数値チェックでエラー: {str(e)}")
        
        # 基本統計情報
        validation_results['info'].append(f"総レコード数: {len(df):,}件")
        validation_results['info'].append(f"列数: {len(df.columns)}列")
        
        # 重複チェック
        if len(df.columns) >= 3:
            key_columns = ['日付']
            if '病棟コード' in df.columns:
                key_columns.append('病棟コード')
            if '診療科名' in df.columns:
                key_columns.append('診療科名')
            
            duplicates = df.duplicated(subset=key_columns).sum()
            if duplicates > 0:
                validation_results['warnings'].append(f"重複レコードが{duplicates}件あります")
        
    except Exception as e:
        validation_results['errors'].append(f"バリデーション処理でエラー: {str(e)}")
        validation_results['is_valid'] = False
        logger.error(f"データバリデーションエラー: {e}", exc_info=True)
    
    return validation_results

def preprocess_data(df):
    """
    データの前処理を実行
    
    Args:
        df (pd.DataFrame): 前処理対象のデータフレーム
        
    Returns:
        pd.DataFrame: 前処理済みのデータフレーム
    """
    try:
        if df is None or df.empty:
            return df
        
        processed_df = df.copy()
        
        # 日付列の正規化
        if '日付' in processed_df.columns:
            processed_df['日付'] = pd.to_datetime(processed_df['日付'], errors='coerce')
            processed_df = processed_df.dropna(subset=['日付'])
            processed_df['日付'] = processed_df['日付'].dt.normalize()
        
        # 数値列の変換
        numeric_columns = ['在院患者数', '入院患者数', '退院患者数']
        for col in numeric_columns:
            if col in processed_df.columns:
                processed_df[col] = pd.to_numeric(processed_df[col], errors='coerce').fillna(0)
        
        # 文字列列のクリーニング
        string_columns = ['病棟コード', '診療科名']
        for col in string_columns:
            if col in processed_df.columns:
                processed_df[col] = processed_df[col].astype(str).str.strip()
        
        # 重複の除去
        if len(processed_df.columns) >= 3:
            key_columns = ['日付']
            if '病棟コード' in processed_df.columns:
                key_columns.append('病棟コード')
            if '診療科名' in processed_df.columns:
                key_columns.append('診療科名')
            
            processed_df = processed_df.drop_duplicates(subset=key_columns, keep='last')
        
        # 日付でソート
        if '日付' in processed_df.columns:
            processed_df = processed_df.sort_values('日付').reset_index(drop=True)
        
        return processed_df
        
    except Exception as e:
        logger.error(f"データ前処理エラー: {e}", exc_info=True)
        return df

def create_data_processing_tab():
    """
    データ入力・処理タブのメイン関数
    """
    st.header("📥 データ入力・処理")
    
    # データアップロードセクション
    st.markdown("### 📂 ファイルアップロード")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "入院データファイルを選択してください",
            type=['xlsx', 'xls', 'csv'],
            help="Excel形式またはCSV形式のファイルをアップロードしてください"
        )
    
    with col2:
        st.markdown("**📋 必要な列:**")
        st.markdown("• 日付（必須）")
        st.markdown("• 病棟コード（推奨）")
        st.markdown("• 診療科名（推奨）")
        st.markdown("• 在院患者数（推奨）")
        st.markdown("• 入院患者数（推奨）")
        st.markdown("• 退院患者数（推奨）")
    
    # ファイル処理オプション
    if uploaded_file is not None:
        st.markdown("### ⚙️ 処理オプション")
        
        col_opt1, col_opt2, col_opt3 = st.columns(3)
        
        with col_opt1:
            file_encoding = st.selectbox(
                "ファイルエンコーディング",
                ["utf-8", "shift_jis", "cp932"],
                index=0,
                help="CSVファイルの文字エンコーディング"
            )
        
        with col_opt2:
            data_validation = st.checkbox(
                "データ検証を実行",
                value=True,
                help="アップロード時にデータの妥当性をチェック"
            )
        
        with col_opt3:
            auto_preprocess = st.checkbox(
                "自動前処理を実行",
                value=True,
                help="データ型変換、重複除去等を自動実行"
            )
        
        # ファイル処理実行
        if st.button("🚀 ファイルを処理", type="primary", use_container_width=True):
            try:
                with st.spinner("ファイルを読み込み中..."):
                    # ファイル読み込み
                    if uploaded_file.name.endswith('.csv'):
                        try:
                            df = pd.read_csv(uploaded_file, encoding=file_encoding)
                        except UnicodeDecodeError:
                            # エンコーディングエラーの場合、他のエンコーディングを試行
                            st.warning(f"指定されたエンコーディング（{file_encoding}）で読み込めませんでした。他のエンコーディングを試行します。")
                            for alt_encoding in ['utf-8', 'shift_jis', 'cp932']:
                                if alt_encoding != file_encoding:
                                    try:
                                        uploaded_file.seek(0)  # ファイルポインタをリセット
                                        df = pd.read_csv(uploaded_file, encoding=alt_encoding)
                                        st.success(f"エンコーディング {alt_encoding} で読み込み成功")
                                        break
                                    except UnicodeDecodeError:
                                        continue
                            else:
                                raise UnicodeDecodeError("すべてのエンコーディングで読み込みに失敗しました")
                    else:
                        df = pd.read_excel(uploaded_file)
                
                if df.empty:
                    st.error("❌ アップロードされたファイルにデータがありません")
                    return
                
                st.success(f"✅ ファイル読み込み完了: {len(df):,}行 × {len(df.columns)}列")
                
                # データプレビュー
                st.markdown("### 👀 データプレビュー")
                st.dataframe(df.head(10), use_container_width=True)
                
                # データ検証
                if data_validation:
                    st.markdown("### 🔍 データ検証結果")
                    validation_results = validate_uploaded_data(df)
                    
                    # エラー表示
                    if validation_results['errors']:
                        for error in validation_results['errors']:
                            st.error(f"❌ {error}")
                    
                    # 警告表示
                    if validation_results['warnings']:
                        for warning in validation_results['warnings']:
                            st.warning(f"⚠️ {warning}")
                    
                    # 情報表示
                    if validation_results['info']:
                        for info in validation_results['info']:
                            st.info(f"ℹ️ {info}")
                    
                    if not validation_results['is_valid']:
                        st.error("データ検証に失敗しました。ファイルを確認してください。")
                        return
                
                # 自動前処理
                if auto_preprocess:
                    st.markdown("### 🔧 データ前処理")
                    with st.spinner("データ前処理中..."):
                        processed_df = preprocess_data(df)
                        
                        if len(processed_df) != len(df):
                            st.info(f"前処理により {len(df) - len(processed_df)} 行が除去されました（重複、無効データ等）")
                        
                        df = processed_df
                
                # セッション状態に保存
                st.session_state['df'] = df
                st.session_state['target_data'] = None  # 目標値データはリセット
                st.session_state['data_processed'] = True
                st.session_state['data_source'] = 'data_processing_tab'
                
                # 最新日付の設定
                if '日付' in df.columns and not df['日付'].empty:
                    latest_date = df['日付'].max()
                    st.session_state.latest_data_date_str = latest_date.strftime('%Y年%m月%d日')
                else:
                    st.session_state.latest_data_date_str = "日付不明"
                
                # マッピングとフィルターの初期化
                initialize_all_mappings(df, None)
                if initialize_unified_filters:
                    initialize_unified_filters(df)
                st.session_state.mappings_initialized_after_processing = True
                
                st.success("✅ データ処理が完了しました！")
                
                # 自動保存オプション
                if st.checkbox("処理済みデータを自動保存", value=True):
                    if save_data_to_file:
                        metadata = {
                            'processing_timestamp': datetime.now().isoformat(),
                            'source_file': uploaded_file.name,
                            'validation_performed': data_validation,
                            'preprocessing_performed': auto_preprocess
                        }
                        
                        if save_data_to_file(df, None, metadata):
                            st.success("💾 データを自動保存しました")
                        else:
                            st.warning("⚠️ 自動保存に失敗しました")
                
                # 処理完了後の情報表示
                st.markdown("### 📊 処理完了データ情報")
                col_info1, col_info2, col_info3 = st.columns(3)
                
                with col_info1:
                    st.metric("総レコード数", f"{len(df):,}件")
                
                with col_info2:
                    if '日付' in df.columns:
                        min_date = df['日付'].min()
                        max_date = df['日付'].max()
                        period_days = (max_date - min_date).days + 1
                        st.metric("データ期間", f"{period_days}日間")
                    else:
                        st.metric("データ期間", "不明")
                
                with col_info3:
                    unique_depts = df['診療科名'].nunique() if '診療科名' in df.columns else 0
                    unique_wards = df['病棟コード'].nunique() if '病棟コード' in df.columns else 0
                    st.metric("部門数", f"診療科{unique_depts}、病棟{unique_wards}")
                
                # 他のタブへの誘導
                st.markdown("---")
                st.info("🎉 データ処理が完了しました！他のタブで分析を開始できます。")
                
            except Exception as e:
                st.error(f"❌ ファイル処理中にエラーが発生しました: {str(e)}")
                logger.error(f"ファイル処理エラー: {e}", exc_info=True)
                st.error(traceback.format_exc())
    
    else:
        # ファイルが選択されていない場合の表示
        st.markdown("### 💡 使用方法")
        st.markdown("""
        1. **ファイル選択**: Excel (.xlsx, .xls) または CSV ファイルを選択
        2. **処理オプション設定**: エンコーディングや処理方法を指定
        3. **処理実行**: 「ファイルを処理」ボタンをクリック
        4. **検証・前処理**: データの妥当性チェックと自動前処理
        5. **完了**: 他のタブで分析開始
        """)
        
        # 現在のデータ状況表示
        if st.session_state.get('data_processed', False):
            st.markdown("### 📊 現在のデータ状況")
            df_current = st.session_state.get('df')
            if df_current is not None and not df_current.empty:
                st.success(f"✅ データ読み込み済み: {len(df_current):,}件")
                
                col_current1, col_current2 = st.columns(2)
                with col_current1:
                    st.write(f"📅 最新日付: {st.session_state.get('latest_data_date_str', '不明')}")
                    st.write(f"🔄 読み込み元: {st.session_state.get('data_source', '不明')}")
                
                with col_current2:
                    if '日付' in df_current.columns:
                        min_date = df_current['日付'].min()
                        max_date = df_current['日付'].max()
                        period_days = (max_date - min_date).days + 1
                        st.write(f"📊 データ期間: {period_days}日間")
                    
                    st.write(f"📋 列数: {len(df_current.columns)}列")
            else:
                st.warning("⚠️ データ処理エラーが発生している可能性があります")
        else:
            st.info("📁 データが読み込まれていません")
    
    # サンプルデータダウンロード
    st.markdown("---")
    st.markdown("### 📋 サンプルデータ")
    
    # サンプルデータの作成
    sample_dates = pd.date_range(start='2024-01-01', end='2024-01-31', freq='D')
    sample_data = []
    
    for date in sample_dates:
        for ward in ['A1病棟', 'B2病棟', 'ICU']:
            for dept in ['内科', '外科', '小児科']:
                sample_data.append({
                    '日付': date.strftime('%Y-%m-%d'),
                    '病棟コード': ward,
                    '診療科名': dept,
                    '在院患者数': np.random.randint(20, 50),
                    '入院患者数': np.random.randint(1, 5),
                    '退院患者数': np.random.randint(1, 5)
                })
    
    sample_df = pd.DataFrame(sample_data)
    sample_csv = sample_df.to_csv(index=False, encoding='utf-8')
    
    st.download_button(
        label="📄 サンプルCSVファイルをダウンロード",
        data=sample_csv,
        file_name="sample_inpatient_data.csv",
        mime="text/csv",
        help="データ形式の参考として使用してください"
    )
    
    # データ形式説明
    with st.expander("📖 データ形式の詳細説明", expanded=False):
        st.markdown("""
        **📅 日付列**
        - 形式: YYYY-MM-DD（例: 2024-01-15）
        - 必須項目です
        
        **🏥 病棟コード列**
        - 各病棟の識別コード
        - 例: A1病棟, B2病棟, ICU
        
        **⚕️ 診療科名列**
        - 診療科の名称
        - 例: 内科, 外科, 小児科
        
        **👥 在院患者数列**
        - その日の在院患者数
        - 数値（整数）
        
        **📈 入院患者数列**
        - その日の新入院患者数
        - 数値（整数）
        
        **📉 退院患者数列**
        - その日の退院患者数
        - 数値（整数）
        """)