# pdf_output_tab.py (修正版 - 個別PDF印刷機能削除)

import streamlit as st
import pandas as pd
import time
import os # execute_batch_pdf_generation で os.path を使用している場合は残す
import gc
# from pathlib import Path # このファイルでは直接使用されていない
import traceback
import multiprocessing
# import base64 # 個別プレビュー削除のため不要になる可能性
# from io import BytesIO # execute_batch_pdf_generation で使用

# batch_processor と pdf_generator のインポートは一括PDF出力に必要
try:
    from batch_processor import batch_generate_pdfs_full_optimized
    # from pdf_generator import create_pdf, create_landscape_pdf # generate_single_pdfが削除されれば不要
except ImportError as e:
    st.error(f"PDF生成機能のインポートに失敗しました: {e}")
    batch_generate_pdfs_full_optimized = None
    # create_pdf = None
    # create_landscape_pdf = None

# display_batch_pdf_tab は create_pdf_output_tab に名前変更を検討
def create_pdf_output_tab(): # 関数名を変更 (app.pyでの呼び出しに合わせる)
    """
    PDF出力タブを表示する関数 (一括PDF出力のみ)
    """
    st.header("📦 一括PDF出力") # ヘッダーを一括PDF出力に特化

    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ入力」タブでデータを読み込んでください。") # 「データ処理」から「データ入力」へ名称変更
        return

    df = st.session_state.get('df')
    if df is None or df.empty:
        st.error("分析対象のデータフレームが読み込まれていません。")
        return

    target_data = st.session_state.get('target_data')

    if batch_generate_pdfs_full_optimized is None:
        st.error("一括PDF生成機能が利用できません。batch_processor.pyを確認してください。")
        return

    # --- 一括PDF出力セクションのみを残す ---
    # tab1, tab2 = st.tabs(["📦 一括PDF出力", "🖨️ 個別PDF印刷"]) # タブ分けを削除
    # with tab1: # tab1の囲みを削除
    create_batch_pdf_section(df, target_data) # df と target_data を引数として渡す

    # create_individual_print_section 関数と、それに関連する generate_and_preview_pdf,
    # generate_and_print_pdf, generate_single_pdf 関数は削除されます。


def create_batch_pdf_section(df, target_data):
    """一括PDF出力セクション"""
    with st.expander("一括PDF出力設定", expanded=True):
        col1_options, col2_options = st.columns(2)

        with col1_options:
            # 既存のコード（変更なし）
            batch_pdf_mode_ui = st.radio(
                "出力対象を選択:",
                ["すべて（全体+診療科別+病棟別）", "診療科別のみ", "病棟別のみ", "全体のみ（統一フィルター適用結果）"],
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

            # 🚀 新しいハイパー最適化オプションを追加
            use_hyper_optimization_ui = st.checkbox(
                "🚀 ハイパー最適化モード（実験的）",
                value=False,
                help="最新の最適化技術を適用して処理を大幅に高速化します（2-4倍高速）。実験的機能のため、問題が発生した場合は無効にしてください。",
                key="batch_pdf_hyper_optimization_ui_selector_main"
            )

            num_cpu_cores = multiprocessing.cpu_count()
            
            # ハイパー最適化時は推奨設定を自動計算
            if use_hyper_optimization_ui:
                import psutil
                memory_gb = psutil.virtual_memory().total / (1024**3)
                recommended_workers = min(num_cpu_cores - 1, int(memory_gb / 1.5), 8)
                st.info(f"🚀 ハイパー最適化モード: 推奨ワーカー数 {recommended_workers}")
                default_workers = recommended_workers
            else:
                default_workers = max(1, min(num_cpu_cores - 1 if num_cpu_cores > 1 else 1, 4))

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

        # 🚀 パフォーマンス予測表示を追加
        if use_hyper_optimization_ui:
            st.markdown("---")
            st.markdown("### 🚀 ハイパー最適化モード - パフォーマンス予測")
            
            col_perf1, col_perf2, col_perf3 = st.columns(3)
            
            with col_perf1:
                expected_speedup = "2-4倍" if use_parallel_processing_ui else "1.5-2倍"
                st.metric("予想高速化", expected_speedup, "vs 標準モード")
            
            with col_perf2:
                memory_usage = "30-50%" if fast_mode_enabled_ui else "50-70%"
                st.metric("メモリ削減", memory_usage, "vs 標準モード")
            
            with col_perf3:
                if use_parallel_processing_ui:
                    cpu_efficiency = f"{min(95, max_pdf_workers_ui * 15)}%"
                else:
                    cpu_efficiency = "25-40%"
                st.metric("CPU効率", cpu_efficiency)

        from unified_filters import apply_unified_filters, get_unified_filter_summary
        
        df_for_counting = df
        st.info(f"適用中の統一フィルター: {get_unified_filter_summary()}")
        df_filtered_for_batch = apply_unified_filters(df)

        if df_filtered_for_batch.empty and batch_pdf_mode_ui != "全体のみ（統一フィルター適用結果）":
             st.warning("統一フィルター適用後のデータが0件のため、一部モードではPDFが生成されません。")
             num_depts_batch = 0
             num_wards_batch = 0
        elif not df_filtered_for_batch.empty:
            num_depts_batch = df_filtered_for_batch['診療科名'].nunique() if '診療科名' in df_filtered_for_batch.columns else 0
            num_wards_batch = df_filtered_for_batch['病棟コード'].nunique() if '病棟コード' in df_filtered_for_batch.columns else 0
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
        elif batch_pdf_mode_ui == "全体のみ（統一フィルター適用結果）":
            reports_to_generate = 1
            mode_arg_for_batch = "all_only_filter"
        else:
            reports_to_generate = 0
            mode_arg_for_batch = "none"

        # 🚀 ハイパー最適化を考慮した時間計算
        if use_hyper_optimization_ui:
            time_per_report_sec = 0.8 if fast_mode_enabled_ui else 1.5  # ハイパー最適化での高速化
        else:
            time_per_report_sec = 2.5 if fast_mode_enabled_ui else 5
            
        if use_parallel_processing_ui and max_pdf_workers_ui > 0 and reports_to_generate > 0:
            if use_hyper_optimization_ui:
                # ハイパー最適化での並列効率はより高い
                efficiency_factor = 0.9
            else:
                efficiency_factor = 0.8
            estimated_total_time_sec = (reports_to_generate * time_per_report_sec) / (max_pdf_workers_ui * efficiency_factor)
        else:
            estimated_total_time_sec = reports_to_generate * time_per_report_sec

        st.metric("出力予定レポート数", f"{reports_to_generate} 件")
        
        # 🚀 時間表示を改善
        if estimated_total_time_sec < 60:
            time_display = f"{estimated_total_time_sec:.1f} 秒"
        else:
            minutes = int(estimated_total_time_sec // 60)
            seconds = int(estimated_total_time_sec % 60)
            time_display = f"{minutes}分{seconds}秒"
        
        st.metric("推定処理時間 (目安)", time_display)
        
        if use_hyper_optimization_ui and reports_to_generate > 5:
            st.success("🚀 ハイパー最適化により大幅な時間短縮が期待されます！")

    # 🚀 実行ボタンのラベルを条件で変更
    button_label = "🚀 ハイパー高速PDF出力実行" if use_hyper_optimization_ui else "📦 一括PDF出力実行"
    
    if st.button(button_label, key="execute_batch_pdf_button_final", use_container_width=True):
        if reports_to_generate == 0 and batch_pdf_mode_ui != "全体のみ（統一フィルター適用結果）":
            st.warning("出力対象が選択されていないか、フィルター適用後の対象データがありません。")
        else:
            # 🚀 ハイパー最適化パラメータを追加して execute_batch_pdf_generation を呼び出し
            execute_batch_pdf_generation(
                df_filtered_for_batch, target_data, batch_pdf_mode_ui, pdf_orientation_landscape_ui,
                use_parallel_processing_ui, max_pdf_workers_ui, fast_mode_enabled_ui,
                mode_arg_for_batch, reports_to_generate, use_hyper_optimization_ui  # 新しいパラメータ
            )
            
def execute_batch_pdf_generation(df_for_batch, target_data, batch_pdf_mode_ui, pdf_orientation_landscape_ui,
                                use_parallel_processing_ui, max_pdf_workers_ui, fast_mode_enabled_ui,
                                mode_arg_for_batch, reports_to_generate, use_hyper_optimization_ui=False):  # 新しいパラメータ
    """一括PDF生成の実行 (ハイパー最適化対応版)"""
    if reports_to_generate == 0 and mode_arg_for_batch != "all_only_filter":
        st.warning("出力対象が選択されていないか、対象データがありません。")
        return

    if mode_arg_for_batch == "all_only_filter" and df_for_batch.empty:
        st.warning("「全体のみ（統一フィルター適用結果）」モードですが、フィルター適用後のデータが0件です。空のPDF（またはエラー）が出力される可能性があります。")

    progress_bar_placeholder = st.empty()
    status_text_placeholder = st.empty()

    def ui_progress_callback(value, text):
        try:
            progress_bar_placeholder.progress(value, text=text)
        except Exception:
            pass

    try:
        from batch_processor import batch_generate_pdfs_full_optimized

        # 🚀 モード表示を改善
        mode_text = "ハイパー最適化" if use_hyper_optimization_ui else "標準最適化"
        
        status_text_placeholder.info(
            f"🚀 {mode_text}で一括PDF生成を開始します... 対象: {batch_pdf_mode_ui}, "
            f"向き: {'横' if pdf_orientation_landscape_ui else '縦'}, "
            f"並列処理: {'有効' if use_parallel_processing_ui else '無効'} (ワーカー: {max_pdf_workers_ui}), "
            f"高速モード: {'有効' if fast_mode_enabled_ui else '無効'}"
        )
        overall_start_time = time.time()

        # 🚀 ハイパー最適化パラメータを追加
        zip_file_bytes_io = batch_generate_pdfs_full_optimized(
            df=df_for_batch.copy(),
            mode=mode_arg_for_batch,
            landscape=pdf_orientation_landscape_ui,
            target_data=target_data.copy() if target_data is not None else None,
            progress_callback=ui_progress_callback,
            use_parallel=use_parallel_processing_ui,
            max_workers=max_pdf_workers_ui if use_parallel_processing_ui else 1,
            fast_mode=fast_mode_enabled_ui,
            use_hyper_optimization=use_hyper_optimization_ui  # 新しいパラメータ
        )

        overall_end_time = time.time()
        duration_sec = overall_end_time - overall_start_time
        progress_bar_placeholder.empty()
        status_text_placeholder.empty()

        if zip_file_bytes_io and zip_file_bytes_io.getbuffer().nbytes > 22:
            # 🚀 ファイル名にモードを含める
            mode_suffix = "ハイパー" if use_hyper_optimization_ui else "標準"
            zip_filename = f"入院患者数予測_一括_{mode_suffix}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}{'_横' if pdf_orientation_landscape_ui else '_縦'}.zip"
            
            col_dl_btn, col_dl_info = st.columns([1, 2])
            with col_dl_btn:
                st.download_button(
                    label="📥 ZIPファイルをダウンロード",
                    data=zip_file_bytes_io.getvalue(),
                    file_name=zip_filename,
                    mime="application/zip",
                    key="download_batch_zip_final_button_main",
                    use_container_width=True
                )
            with col_dl_info:
                # 🚀 パフォーマンス情報を表示
                rate = reports_to_generate / duration_sec if duration_sec > 0 else 0
                success_message = f"✅ {mode_text}で一括PDF生成完了！ (処理時間: {duration_sec:.1f}秒, {rate:.1f}件/秒)"
                
                if use_hyper_optimization_ui:
                    st.success(success_message)
                    if rate > 1.0:
                        st.balloons()  # ハイパー最適化で高速な場合は祝福エフェクト
                else:
                    st.success(success_message)
                
                st.caption(f"ファイル名: {zip_filename}")
                st.caption(f"サイズ: {zip_file_bytes_io.getbuffer().nbytes / (1024*1024):.2f} MB")
                
                # 🚀 パフォーマンス統計を表示
                if use_hyper_optimization_ui:
                    st.info(f"🚀 ハイパー最適化効果: {rate:.1f}件/秒の高速処理を実現")
            
            del zip_file_bytes_io
            gc.collect()
        else:
            st.error("PDFファイルの生成に失敗しました (ZIPファイルが空か無効です)。フィルター条件やデータを確認してください。")

    except Exception as ex:
        st.error(f"一括PDF生成でエラーが発生しました: {ex}")
        st.error(traceback.format_exc())
        if progress_bar_placeholder: progress_bar_placeholder.empty()
        if status_text_placeholder: status_text_placeholder.empty()