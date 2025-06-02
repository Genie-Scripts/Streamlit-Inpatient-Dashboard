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


def create_batch_pdf_section(df, target_data): # 引数 df, target_data を受け取る
    """一括PDF出力セクション"""
    with st.expander("一括PDF出力設定", expanded=True):
        col1_options, col2_options = st.columns(2)

        with col1_options:
            batch_pdf_mode_ui = st.radio(
                "出力対象を選択:",
                ["すべて（全体+診療科別+病棟別）", "診療科別のみ", "病棟別のみ", "全体のみ（統一フィルター適用結果）"], # 「全体のみ」のラベルを明確化
                key="batch_pdf_mode_ui_selector_main", # キーをよりユニークに
                horizontal=False,
                index=0
            )

            pdf_orientation_landscape_ui = st.checkbox(
                "横向きPDFで出力",
                value=False,
                key="batch_pdf_orientation_ui_selector_main" # キーをよりユニークに
            )

        with col2_options:
            use_parallel_processing_ui = st.checkbox(
                "並列処理を使用する",
                value=True,
                help="複数のCPUコアを使用して処理を高速化します。",
                key="batch_pdf_parallel_ui_selector_main" # キーをよりユニークに
            )

            num_cpu_cores = multiprocessing.cpu_count()
            default_workers = max(1, min(num_cpu_cores - 1 if num_cpu_cores > 1 else 1, 4))

            if use_parallel_processing_ui:
                max_pdf_workers_ui = st.slider(
                    "最大ワーカー数（並列処理時）:",
                    min_value=1,
                    max_value=max(1, num_cpu_cores),
                    value=default_workers,
                    help=f"推奨: {default_workers} (システムコア数: {num_cpu_cores})",
                    key="batch_pdf_max_workers_ui_selector_main" # キーをよりユニークに
                )
            else:
                max_pdf_workers_ui = 1 # 並列処理しない場合はワーカー数1

            fast_mode_enabled_ui = st.checkbox(
                "高速処理モード（グラフ期間を90日のみに短縮）",
                value=True,
                help="生成時間を短縮します。",
                key="batch_pdf_fast_mode_ui_selector_main" # キーをよりユニークに
            )

        # 出力件数と推定時間の表示
        # ★★★ 統一フィルター適用後のdfに基づいて件数を計算 ★★★
        from unified_filters import apply_unified_filters, get_unified_filter_summary # インポート
        
        df_for_counting = df # デフォルトは渡されたDF (app.pyからはオリジナルDFが渡される想定)
        # 統一フィルターが適用されているか確認し、適用されていればその情報を使用
        # pdf_output_tab.py は app.py から呼び出されるため、
        # app.py 側で統一フィルターを適用した結果のdfを渡すか、
        # ここで統一フィルターを適用するか設計による。
        # ここでは、app.py から渡される df が既にフィルター済みであることを期待するか、
        # あるいは、ここで明示的にフィルターを適用する。
        # app.py の現状の実装では、このタブに渡す df はフィルター前のオリジナル。
        # よって、ここで統一フィルターを適用する。
        
        st.info(f"適用中の統一フィルター: {get_unified_filter_summary()}")
        df_filtered_for_batch = apply_unified_filters(df) # 統一フィルターを適用

        if df_filtered_for_batch.empty and batch_pdf_mode_ui != "全体のみ（統一フィルター適用結果）":
             st.warning("統一フィルター適用後のデータが0件のため、一部モードではPDFが生成されません。")
             # 「全体のみ（統一フィルター適用結果）」モードの場合は、空のデータでPDF生成を試みるか、エラー表示。
             # batch_processor 側で空データの場合はNoneを返すので、ここでは件数0とする。
             num_depts_batch = 0
             num_wards_batch = 0
        elif not df_filtered_for_batch.empty:
            num_depts_batch = df_filtered_for_batch['診療科名'].nunique() if '診療科名' in df_filtered_for_batch.columns else 0
            num_wards_batch = df_filtered_for_batch['病棟コード'].nunique() if '病棟コード' in df_filtered_for_batch.columns else 0
        else: # df_filtered_for_batch が空だが「全体のみ」モードの場合
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
            mode_arg_for_batch = "all_only_filter" # batch_processor.py の mode 引数と合わせる
        else:
            reports_to_generate = 0
            mode_arg_for_batch = "none" # 未選択または不正なモード

        time_per_report_sec = 2.5 if fast_mode_enabled_ui else 5
        if use_parallel_processing_ui and max_pdf_workers_ui > 0 and reports_to_generate > 0:
            estimated_total_time_sec = (reports_to_generate * time_per_report_sec) / (max_pdf_workers_ui * 0.8) # 0.8は並列処理のオーバーヘッド等を考慮した係数（仮）
        else:
            estimated_total_time_sec = reports_to_generate * time_per_report_sec

        st.metric("出力予定レポート数", f"{reports_to_generate} 件")
        st.metric("推定処理時間 (目安)", f"{estimated_total_time_sec:.1f} 秒")

    if st.button("📦 一括PDF出力実行", key="execute_batch_pdf_button_final", use_container_width=True): # キー変更
        if reports_to_generate == 0 and batch_pdf_mode_ui != "全体のみ（統一フィルター適用結果）": # 「全体のみ」はデータ0件でも処理試行
            st.warning("出力対象が選択されていないか、フィルター適用後の対象データがありません。")
        else:
            # execute_batch_pdf_generation にはフィルター適用後のdfを渡す
            execute_batch_pdf_generation(
                df_filtered_for_batch, target_data, batch_pdf_mode_ui, pdf_orientation_landscape_ui,
                use_parallel_processing_ui, max_pdf_workers_ui, fast_mode_enabled_ui,
                mode_arg_for_batch, reports_to_generate
            )

# --- execute_batch_pdf_generation 関数 (変更なし、ただし呼び出し元から渡されるdfがフィルター済みになる) ---
def execute_batch_pdf_generation(df_for_batch, target_data, batch_pdf_mode_ui, pdf_orientation_landscape_ui,
                                use_parallel_processing_ui, max_pdf_workers_ui, fast_mode_enabled_ui,
                                mode_arg_for_batch, reports_to_generate):
    """一括PDF生成の実行 (df_for_batch はフィルター適用済みを期待)"""
    if reports_to_generate == 0 and mode_arg_for_batch != "all_only_filter": # df_for_batchが空でもall_only_filterなら実行
        st.warning("出力対象が選択されていないか、対象データがありません。")
        return

    # all_only_filter モードで df_for_batch が空の場合のハンドリング
    if mode_arg_for_batch == "all_only_filter" and df_for_batch.empty:
        st.warning("「全体のみ（統一フィルター適用結果）」モードですが、フィルター適用後のデータが0件です。空のPDF（またはエラー）が出力される可能性があります。")
        # この場合でも batch_generate_pdfs_full_optimized を呼び出すか、ここで処理を止めるか。
        # batch_processor側で空のdfを扱えるようにしてある想定。

    progress_bar_placeholder = st.empty()
    status_text_placeholder = st.empty()

    def ui_progress_callback(value, text):
        try:
            progress_bar_placeholder.progress(value, text=text)
        except Exception:
            pass

    try:
        from batch_processor import batch_generate_pdfs_full_optimized # このインポートは関数の先頭でも良い

        status_text_placeholder.info(
            f"一括PDF生成を開始します... 対象: {batch_pdf_mode_ui}, "
            f"向き: {'横' if pdf_orientation_landscape_ui else '縦'}, "
            f"並列処理: {'有効' if use_parallel_processing_ui else '無効'} (ワーカー: {max_pdf_workers_ui}), "
            f"高速モード: {'有効' if fast_mode_enabled_ui else '無効'}"
        )
        overall_start_time = time.time()

        zip_file_bytes_io = batch_generate_pdfs_full_optimized(
            df=df_for_batch.copy(), # フィルター済みdfを使用
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
        progress_bar_placeholder.empty()
        status_text_placeholder.empty()

        if zip_file_bytes_io and zip_file_bytes_io.getbuffer().nbytes > 22: # ZIPファイルが空でないかチェック
            zip_filename = f"入院患者数予測_一括_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}{'_横' if pdf_orientation_landscape_ui else '_縦'}.zip"
            col_dl_btn, col_dl_info = st.columns([1, 2])
            with col_dl_btn:
                st.download_button(
                    label="📥 ZIPファイルをダウンロード",
                    data=zip_file_bytes_io.getvalue(),
                    file_name=zip_filename,
                    mime="application/zip",
                    key="download_batch_zip_final_button_main", # キー変更
                    use_container_width=True
                )
            with col_dl_info:
                st.success(f"一括PDF生成完了！ (処理時間: {duration_sec:.1f}秒)")
                st.caption(f"ファイル名: {zip_filename}")
                st.caption(f"サイズ: {zip_file_bytes_io.getbuffer().nbytes / (1024*1024):.2f} MB")
            del zip_file_bytes_io
            gc.collect()
        else:
            st.error("PDFファイルの生成に失敗しました (ZIPファイルが空か無効です)。フィルター条件やデータを確認してください。")

    except Exception as ex:
        st.error(f"一括PDF生成でエラーが発生しました: {ex}")
        st.error(traceback.format_exc())
        if progress_bar_placeholder: progress_bar_placeholder.empty()
        if status_text_placeholder: status_text_placeholder.empty()


# --- 個別PDF印刷セクションと関連関数 (create_individual_print_section, generate_and_preview_pdf, generate_and_print_pdf, generate_single_pdf) は削除 ---

# create_print_preview_interface 関数も不要なので削除
# def create_print_preview_interface(): ...

# create_pdf_output_tab は display_batch_pdf_tab が改名されたもの
# display_batch_pdf_tab が直接呼び出されるので、実質このファイルがタブのコンテンツとなる