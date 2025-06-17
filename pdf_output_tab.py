# pdf_output_tab.py (修正版 - 除外病棟・目標値デバッグ対応)

import streamlit as st
import pandas as pd
import time
import os
import gc
import traceback
import multiprocessing
from config import EXCLUDED_WARDS

try:
    from batch_processor import batch_generate_pdfs_full_optimized
except ImportError as e:
    st.error(f"PDF生成機能のインポートに失敗しました: {e}")
    batch_generate_pdfs_full_optimized = None

def get_pdf_output_data(apply_current_filters=False):
    """
    PDF出力用のデータを取得
    """
    original_df = st.session_state.get('df')
    
    if original_df is None or original_df.empty:
        return pd.DataFrame()
    
    if apply_current_filters:
        try:
            from unified_filters import apply_unified_filters
            return apply_unified_filters(original_df)
        except ImportError:
            st.warning("フィルター機能が利用できません。元データを使用します。")
            return original_df.copy()
    else:
        return original_df.copy()

def check_excluded_wards_in_data(df):
    """データ内の除外病棟をチェックし、情報を返す"""
    excluded_info = {
        'has_excluded': False,
        'excluded_wards_found': [],
        'excluded_count': 0,
        'total_count': 0
    }
    
    if df is None or df.empty or '病棟コード' in df.columns is False:
        return excluded_info
    
    excluded_info['total_count'] = len(df)
    
    if EXCLUDED_WARDS:
        ward_codes = df['病棟コード'].astype(str)
        excluded_mask = ward_codes.isin(EXCLUDED_WARDS)
        excluded_info['excluded_count'] = excluded_mask.sum()
        excluded_info['excluded_wards_found'] = ward_codes[excluded_mask].unique().tolist()
        excluded_info['has_excluded'] = excluded_info['excluded_count'] > 0
    
    return excluded_info

def check_target_data_availability():
    """目標値データの利用可能性をチェック"""
    target_data = st.session_state.get('target_data')
    target_info = {
        'available': False,
        'record_count': 0,
        'columns': [],
        'sample_data': None,
        'dept_codes': []
    }
    
    if target_data is not None and not target_data.empty:
        target_info['available'] = True
        target_info['record_count'] = len(target_data)
        target_info['columns'] = list(target_data.columns)
        target_info['sample_data'] = target_data.head(3).to_dict('records')
        
        if '部門コード' in target_data.columns:
            target_info['dept_codes'] = target_data['部門コード'].astype(str).unique().tolist()
    
    return target_info

def create_pdf_output_tab():
    """
    PDF出力タブを表示する関数 (一括PDF出力のみ)
    """
    st.header("📦 一括PDF出力")

    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ入力」タブでデータを読み込んでください。")
        return

    original_df = st.session_state.get('df')
    if original_df is None or original_df.empty:
        st.error("分析対象のデータフレームが読み込まれていません。")
        return

    target_data = st.session_state.get('target_data')

    if batch_generate_pdfs_full_optimized is None:
        st.error("一括PDF生成機能が利用できません。batch_processor.pyを確認してください。")
        return

    # === デバッグ情報セクション ===
    with st.expander("🔍 データ・設定確認", expanded=False):
        st.subheader("除外病棟設定")
        if EXCLUDED_WARDS:
            st.info(f"📋 除外病棟: {', '.join(EXCLUDED_WARDS)}")
            
            # 元データでの除外病棟チェック
            excluded_info = check_excluded_wards_in_data(original_df)
            if excluded_info['has_excluded']:
                st.warning(f"⚠️ 元データに除外病棟が含まれています:")
                st.write(f"- 除外対象: {excluded_info['excluded_wards_found']}")
                st.write(f"- 除外レコード数: {excluded_info['excluded_count']:,}件")
                st.write(f"- 総レコード数: {excluded_info['total_count']:,}件")
            else:
                st.success("✅ 元データに除外病棟は含まれていません")
        else:
            st.info("📋 除外病棟は設定されていません")
        
        st.subheader("目標値データ")
        target_info = check_target_data_availability()
        if target_info['available']:
            st.success(f"✅ 目標値データあり: {target_info['record_count']}行")
            st.write(f"📊 列: {', '.join(target_info['columns'])}")
            if target_info['dept_codes']:
                st.write(f"🏥 部門コード: {', '.join(target_info['dept_codes'][:10])}{'...' if len(target_info['dept_codes']) > 10 else ''}")
            
            # サンプルデータ表示
            if st.checkbox("サンプルデータを表示", key="show_target_sample"):
                st.dataframe(pd.DataFrame(target_info['sample_data']), use_container_width=True)
        else:
            st.warning("⚠️ 目標値データが設定されていません")

    # 一括PDF出力セクション
    create_batch_pdf_section(original_df, target_data)

def create_batch_pdf_section(original_df, target_data):
    """一括PDF出力セクション"""
    
    # データ範囲設定セクション
    st.subheader("📊 出力データ設定")
    
    with st.expander("データ範囲設定", expanded=True):
        col_filter1, col_filter2 = st.columns(2)
        
        with col_filter1:
            apply_filters = st.checkbox(
                "現在のフィルター設定を適用",
                value=False,
                help="チェックを入れると、サイドバーの分析フィルター（期間・部門等）が適用されます",
                key="pdf_apply_filters_checkbox"
            )
        
        with col_filter2:
            try:
                from unified_filters import get_unified_filter_summary
                filter_summary = get_unified_filter_summary()
                if apply_filters:
                    st.info(f"📌 適用中フィルター: {filter_summary}")
                else:
                    st.info("📌 フィルター: 適用なし（全期間）")
            except ImportError:
                st.info("📌 フィルター情報を取得できません")
    
    # データ取得
    df_for_pdf = get_pdf_output_data(apply_current_filters=apply_filters)
    
    if df_for_pdf.empty:
        st.error("PDF出力用のデータがありません。フィルター設定を確認してください。")
        return
    
    # === 除外病棟フィルタリング後の状況確認 ===
    if EXCLUDED_WARDS:
        excluded_info_filtered = check_excluded_wards_in_data(df_for_pdf)
        if excluded_info_filtered['has_excluded']:
            st.warning(f"⚠️ フィルタ適用後データに除外病棟が残存しています:")
            st.write(f"除外対象: {excluded_info_filtered['excluded_wards_found']}")
            
            # 除外病棟を手動で除去
            if '病棟コード' in df_for_pdf.columns:
                original_count = len(df_for_pdf)
                df_for_pdf = df_for_pdf[~df_for_pdf['病棟コード'].astype(str).isin(EXCLUDED_WARDS)]
                removed_count = original_count - len(df_for_pdf)
                if removed_count > 0:
                    st.success(f"✅ 除外病棟を手動で除去: {removed_count}件削除")
    
    # データ期間とレコード数の表示
    if '日付' in df_for_pdf.columns and not df_for_pdf['日付'].empty:
        min_date = df_for_pdf['日付'].min().strftime('%Y/%m/%d')
        max_date = df_for_pdf['日付'].max().strftime('%Y/%m/%d')
        record_count = len(df_for_pdf)
        date_range_days = (df_for_pdf['日付'].max() - df_for_pdf['日付'].min()).days + 1
        
        col_info1, col_info2, col_info3 = st.columns(3)
        with col_info1:
            st.metric("データ期間", f"{date_range_days}日間", f"{min_date} ～ {max_date}")
        with col_info2:
            st.metric("レコード数", f"{record_count:,}件")
        with col_info3:
            if apply_filters:
                st.metric("データ範囲", "フィルター適用", "🔍")
            else:
                st.metric("データ範囲", "全期間", "📊")
    
    # PDF出力設定セクション
    st.subheader("⚙️ PDF出力設定")
    
    with st.expander("PDF出力設定", expanded=True):
        col1_options, col2_options = st.columns(2)

        with col1_options:
            batch_pdf_mode_ui = st.radio(
                "出力対象を選択:",
                [
                    "すべて（全体+診療科別+病棟別）", 
                    "診療科別のみ", 
                    "病棟別のみ", 
                    "全体のみ"
                ],
                key="batch_pdf_mode_ui_selector_main",
                horizontal=False,
                index=0
            )

            pdf_orientation_landscape_ui = st.checkbox(
                "横向きPDFで出力",
                value=False,
                key="batch_pdf_orientation_ui_selector_main"
            )

        with col2_options:
            use_parallel_processing_ui = st.checkbox(
                "並列処理を使用する",
                value=True,
                help="複数のCPUコアを使用して処理を高速化します。",
                key="batch_pdf_parallel_ui_selector_main"
            )

            num_cpu_cores = multiprocessing.cpu_count()
            default_workers = min(2, multiprocessing.cpu_count() - 1)

            if use_parallel_processing_ui:
                max_pdf_workers_ui = st.slider(
                    "最大ワーカー数（並列処理時）:",
                    min_value=1,
                    max_value=max(1, num_cpu_cores),
                    value=default_workers,
                    help=f"推奨: {default_workers} (システムコア数: {num_cpu_cores})",
                    key="batch_pdf_max_workers_ui_selector_main"
                )
            else:
                max_pdf_workers_ui = 1

            fast_mode_enabled_ui = st.checkbox(
                "高速処理モード（グラフ期間を90日のみに短縮）",
                value=True,
                help="生成時間を短縮します。",
                key="batch_pdf_fast_mode_ui_selector_main"
            )

        # 出力件数と推定時間の表示
        if not df_for_pdf.empty:
            num_depts_batch = df_for_pdf['診療科名'].nunique() if '診療科名' in df_for_pdf.columns else 0
            num_wards_batch = df_for_pdf['病棟コード'].nunique() if '病棟コード' in df_for_pdf.columns else 0
            
            # 除外病棟を考慮した病棟数計算
            if EXCLUDED_WARDS and '病棟コード' in df_for_pdf.columns:
                ward_codes = df_for_pdf['病棟コード'].astype(str).unique()
                filtered_wards = [ward for ward in ward_codes if ward not in EXCLUDED_WARDS]
                num_wards_batch = len(filtered_wards)
        else:
            num_depts_batch = 0
            num_wards_batch = 0

        if batch_pdf_mode_ui == "すべて（全体+診療科別+病棟別）":
            reports_to_generate = 1 + num_depts_batch + num_wards_batch
            mode_arg_for_batch = "all"
        elif batch_pdf_mode_ui == "診療科別のみ":
            reports_to_generate = num_depts_batch
            mode_arg_for_batch = "dept"
        elif batch_pdf_mode_ui == "病棟別のみ":
            reports_to_generate = num_wards_batch
            mode_arg_for_batch = "ward"
        elif batch_pdf_mode_ui == "全体のみ":
            reports_to_generate = 1
            mode_arg_for_batch = "all_only_filter"
        else:
            reports_to_generate = 0
            mode_arg_for_batch = "none"

        time_per_report_sec = 2.5 if fast_mode_enabled_ui else 5
        if use_parallel_processing_ui and max_pdf_workers_ui > 0 and reports_to_generate > 0:
            estimated_total_time_sec = (reports_to_generate * time_per_report_sec) / (max_pdf_workers_ui * 0.8)
        else:
            estimated_total_time_sec = reports_to_generate * time_per_report_sec

        # 統計情報表示
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            st.metric("出力予定レポート数", f"{reports_to_generate}件")
        with col_stat2:
            st.metric("推定処理時間", f"{estimated_total_time_sec:.1f}秒")
        with col_stat3:
            if num_depts_batch > 0 or num_wards_batch > 0:
                excluded_note = f" (除外: {len(EXCLUDED_WARDS)})" if EXCLUDED_WARDS else ""
                st.metric("対象部門数", f"診療科:{num_depts_batch} 病棟:{num_wards_batch}{excluded_note}")
            else:
                st.metric("対象部門数", "全体のみ")

    # PDF生成実行ボタン
    st.subheader("🚀 PDF生成実行")
    
    if reports_to_generate == 0:
        st.warning("出力対象が選択されていないか、対象データがありません。")
        st.button("📦 一括PDF出力実行", disabled=True, use_container_width=True)
    else:
        # 実行前の最終確認情報
        with st.container():
            info_text = (
                f"📋 **実行内容確認**\n\n"
                f"• 出力対象: {batch_pdf_mode_ui}\n"
                f"• レポート数: {reports_to_generate}件\n"
                f"• データ期間: {min_date} ～ {max_date} ({date_range_days}日間)\n"
                f"• レコード数: {record_count:,}件\n"
                f"• PDF向き: {'横向き' if pdf_orientation_landscape_ui else '縦向き'}\n"
                f"• 処理方式: {'並列処理' if use_parallel_processing_ui else '順次処理'}\n"
                f"• 推定時間: {estimated_total_time_sec:.1f}秒"
            )
            if EXCLUDED_WARDS:
                info_text += f"\n• 除外病棟: {', '.join(EXCLUDED_WARDS)}"
            if target_data is not None and not target_data.empty:
                info_text += f"\n• 目標値データ: 利用あり ({len(target_data)}行)"
            else:
                info_text += f"\n• 目標値データ: なし"
            
            st.info(info_text)
        
        if st.button("📦 一括PDF出力実行", key="execute_batch_pdf_button_final", use_container_width=True, type="primary"):
            execute_batch_pdf_generation(
                df_for_pdf, target_data, batch_pdf_mode_ui, pdf_orientation_landscape_ui,
                use_parallel_processing_ui, max_pdf_workers_ui, fast_mode_enabled_ui,
                mode_arg_for_batch, reports_to_generate
            )

def execute_batch_pdf_generation(df_for_batch, target_data, batch_pdf_mode_ui, pdf_orientation_landscape_ui,
                                use_parallel_processing_ui, max_pdf_workers_ui, fast_mode_enabled_ui,
                                mode_arg_for_batch, reports_to_generate):
    """一括PDF生成の実行"""
    
    if reports_to_generate == 0:
        st.warning("出力対象が選択されていないか、対象データがありません。")
        return

    if df_for_batch.empty:
        st.warning("対象データが0件です。空のPDFが出力される可能性があります。")

    progress_bar_placeholder = st.empty()
    status_text_placeholder = st.empty()

    def ui_progress_callback(value, text):
        try:
            progress_bar_placeholder.progress(value, text=text)
        except Exception:
            pass

    try:
        # 実行情報の表示
        excluded_info = ""
        if EXCLUDED_WARDS:
            excluded_info = f" (除外病棟: {', '.join(EXCLUDED_WARDS)})"
        
        execution_info = (
            f"📦 **一括PDF生成開始**\n\n"
            f"• 出力対象: {batch_pdf_mode_ui}\n"
            f"• PDF向き: {'横向き' if pdf_orientation_landscape_ui else '縦向き'}\n"
            f"• 並列処理: {'有効' if use_parallel_processing_ui else '無効'} "
            f"(ワーカー: {max_pdf_workers_ui})\n"
            f"• 高速モード: {'有効' if fast_mode_enabled_ui else '無効'}\n"
            f"• データ件数: {len(df_for_batch):,}件{excluded_info}\n"
            f"• 目標値データ: {'あり' if target_data is not None and not target_data.empty else 'なし'}"
        )
        status_text_placeholder.info(execution_info)
        
        overall_start_time = time.time()

        # 一括PDF生成の実行
        zip_file_bytes_io = batch_generate_pdfs_full_optimized(
            df=df_for_batch.copy(),
            mode=mode_arg_for_batch,
            landscape=pdf_orientation_landscape_ui,
            target_data=target_data.copy() if target_data is not None else None,
            progress_callback=ui_progress_callback,
            use_parallel=use_parallel_processing_ui,
            max_workers=max_pdf_workers_ui if use_parallel_processing_ui else 1,
            fast_mode=fast_mode_enabled_ui
        )

        overall_end_time = time.time()
        duration_sec = overall_end_time - overall_start_time
        
        # プログレスバーとステータスをクリア
        progress_bar_placeholder.empty()
        status_text_placeholder.empty()

        # 結果の処理
        if zip_file_bytes_io and zip_file_bytes_io.getbuffer().nbytes > 22:
            # ファイル名の生成
            timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
            orientation_suffix = '_横' if pdf_orientation_landscape_ui else '_縦'
            excluded_suffix = '_除外病棟適用' if EXCLUDED_WARDS else ''
            zip_filename = f"入院患者数予測_一括_{timestamp}{orientation_suffix}{excluded_suffix}.zip"
            
            # 成功時の表示
            st.success(f"🎉 一括PDF生成が完了しました！")
            
            # 結果の統計情報
            col_result1, col_result2, col_result3 = st.columns(3)
            with col_result1:
                st.metric("処理時間", f"{duration_sec:.1f}秒")
            with col_result2:
                file_size_mb = zip_file_bytes_io.getbuffer().nbytes / (1024*1024)
                st.metric("ファイルサイズ", f"{file_size_mb:.2f} MB")
            with col_result3:
                st.metric("出力レポート数", f"{reports_to_generate}件")
            
            # 除外病棟の情報表示
            if EXCLUDED_WARDS:
                st.info(f"📋 除外病棟適用済み: {', '.join(EXCLUDED_WARDS)}")
            
            # ダウンロードボタン
            st.download_button(
                label="📥 ZIPファイルをダウンロード",
                data=zip_file_bytes_io.getvalue(),
                file_name=zip_filename,
                mime="application/zip",
                key="download_batch_zip_final_button_main",
                use_container_width=True,
                type="primary"
            )
            
            # ファイル情報
            st.info(f"📁 ファイル名: `{zip_filename}`")
            
            # メモリ解放
            del zip_file_bytes_io
            gc.collect()
            
        else:
            st.error("❌ PDFファイルの生成に失敗しました")
            st.error("ZIPファイルが空か無効です。除外病棟設定により全ての対象が除外された可能性があります。")

    except Exception as ex:
        st.error(f"❌ 一括PDF生成でエラーが発生しました: {ex}")
        st.error("詳細なエラー情報:")
        st.code(traceback.format_exc())
        
        # プログレスバーとステータスをクリア
        if progress_bar_placeholder:
            progress_bar_placeholder.empty()
        if status_text_placeholder:
            status_text_placeholder.empty()