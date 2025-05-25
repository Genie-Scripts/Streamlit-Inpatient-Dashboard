# ===== pdf_output_tab.py の修正（印刷機能追加） =====

import streamlit as st
import pandas as pd
import time
import os
import gc
from pathlib import Path
import traceback
import multiprocessing
import base64
from io import BytesIO

def display_batch_pdf_tab():
    """
    一括PDF出力タブを表示する関数（印刷機能付き）
    """
    st.header("📦 一括PDF出力・印刷")

    if not st.session_state.get('data_processed', False):
        st.warning("まず「データ処理」タブでデータを読み込んでください。")
        return

    # データフレームの取得
    try:
        df = st.session_state.get('df')
        if df is None or df.empty:
            st.error("分析対象のデータフレームが読み込まれていません。")
            return
    except Exception as e:
        st.error(f"データフレームの取得中にエラーが発生しました: {e}")
        return

    target_data = st.session_state.get('target_data')

    try:
        from batch_processor import batch_generate_pdfs_full_optimized
        from pdf_generator import create_pdf, create_landscape_pdf
    except ImportError as e:
        st.error(f"PDF生成機能のインポートに失敗しました: {e}")
        return

    # タブ分け：一括出力と個別印刷
    tab1, tab2 = st.tabs(["📦 一括PDF出力", "🖨️ 個別PDF印刷"])
    
    with tab1:
        create_batch_pdf_section(df, target_data)
    
    with tab2:
        create_individual_print_section(df, target_data)

def create_batch_pdf_section(df, target_data):
    """一括PDF出力セクション"""
    with st.expander("一括PDF出力設定", expanded=True):
        col1_options, col2_options = st.columns(2)

        with col1_options:
            batch_pdf_mode_ui = st.radio(
                "出力対象を選択:",
                ["すべて（全体+診療科別+病棟別）", "診療科別のみ", "病棟別のみ", "全体のみ"],
                key="batch_pdf_mode_ui_selector",
                horizontal=False,
                index=0
            )
            
            pdf_orientation_landscape_ui = st.checkbox(
                "横向きPDFで出力", 
                value=False, 
                key="batch_pdf_orientation_ui_selector"
            )

        with col2_options:
            use_parallel_processing_ui = st.checkbox(
                "並列処理を使用する", 
                value=True, 
                help="複数のCPUコアを使用して処理を高速化します。",
                key="batch_pdf_parallel_ui_selector"
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
                    key="batch_pdf_max_workers_ui_selector"
                )
            else:
                max_pdf_workers_ui = 1

            fast_mode_enabled_ui = st.checkbox(
                "高速処理モード（グラフ期間を90日のみに短縮）",
                value=True,
                help="生成時間を短縮します。",
                key="batch_pdf_fast_mode_ui_selector"
            )

        # 出力件数と推定時間の表示
        num_depts = df['診療科名'].nunique() if '診療科名' in df.columns else 0
        num_wards = df['病棟コード'].nunique() if '病棟コード' in df.columns else 0
        
        if batch_pdf_mode_ui == "すべて（全体+診療科別+病棟別）":
            reports_to_generate = 1 + num_depts + num_wards
            mode_arg_for_batch = "all"
        elif batch_pdf_mode_ui == "診療科別のみ":
            reports_to_generate = num_depts
            mode_arg_for_batch = "dept"
        elif batch_pdf_mode_ui == "病棟別のみ":
            reports_to_generate = num_wards
            mode_arg_for_batch = "ward"
        elif batch_pdf_mode_ui == "全体のみ":
            reports_to_generate = 1
            mode_arg_for_batch = "all_only_filter"
        else:
            reports_to_generate = 0

        time_per_report_sec = 2.5 if fast_mode_enabled_ui else 5
        if use_parallel_processing_ui and max_pdf_workers_ui > 0 and reports_to_generate > 0:
            estimated_total_time_sec = (reports_to_generate * time_per_report_sec) / (max_pdf_workers_ui * 0.8)
        else:
            estimated_total_time_sec = reports_to_generate * time_per_report_sec
        
        st.metric("出力予定レポート数", f"{reports_to_generate} 件")
        st.metric("推定処理時間 (目安)", f"{estimated_total_time_sec:.1f} 秒")

    if st.button("📦 一括PDF出力実行", key="execute_batch_pdf_button_main", use_container_width=True):
        execute_batch_pdf_generation(
            df, target_data, batch_pdf_mode_ui, pdf_orientation_landscape_ui,
            use_parallel_processing_ui, max_pdf_workers_ui, fast_mode_enabled_ui,
            mode_arg_for_batch, reports_to_generate
        )

def create_individual_print_section(df, target_data):
    """個別PDF印刷セクション"""
    st.subheader("🖨️ 個別PDF印刷")
    
    with st.expander("印刷設定", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            print_target = st.selectbox(
                "印刷対象を選択",
                ["全体", "診療科別", "病棟別"],
                key="print_target_selector"
            )
            
            if print_target == "診療科別":
                available_depts = sorted(df['診療科名'].unique()) if '診療科名' in df.columns else []
                selected_dept = st.selectbox(
                    "診療科を選択",
                    available_depts,
                    key="print_dept_selector"
                )
                target_code = selected_dept
                target_name = selected_dept
            elif print_target == "病棟別":
                available_wards = sorted(df['病棟コード'].unique()) if '病棟コード' in df.columns else []
                selected_ward = st.selectbox(
                    "病棟を選択",
                    available_wards,
                    key="print_ward_selector"
                )
                target_code = selected_ward
                target_name = f"病棟{selected_ward}"
            else:
                target_code = "全体"
                target_name = "全体"
        
        with col2:
            print_orientation = st.radio(
                "印刷向き",
                ["縦向き", "横向き"],
                key="print_orientation_selector"
            )
            
            print_copies = st.number_input(
                "印刷部数",
                min_value=1,
                max_value=10,
                value=1,
                key="print_copies_selector"
            )
    
    # PDF生成・印刷ボタン
    col_preview, col_print = st.columns(2)
    
    with col_preview:
        if st.button("📄 PDFプレビュー", key="pdf_preview_button", use_container_width=True):
            generate_and_preview_pdf(df, target_data, print_target, target_code, target_name, print_orientation)
    
    with col_print:
        if st.button("🖨️ PDF印刷", key="pdf_print_button", use_container_width=True):
            generate_and_print_pdf(df, target_data, print_target, target_code, target_name, print_orientation, print_copies)

def execute_batch_pdf_generation(df, target_data, batch_pdf_mode_ui, pdf_orientation_landscape_ui,
                                use_parallel_processing_ui, max_pdf_workers_ui, fast_mode_enabled_ui,
                                mode_arg_for_batch, reports_to_generate):
    if reports_to_generate == 0:
        st.warning("出力対象が選択されていないか、対象データがありません。")
        return

    progress_bar_placeholder = st.empty()
    status_text_placeholder = st.empty()

    def ui_progress_callback(value, text):
        try:
            progress_bar_placeholder.progress(min(100, int(value)), text=text) # valueが100を超えないように
        except Exception as e_ui:
            # UI更新のエラーは無視するか、軽いログに留める
            # logger.debug(f"UI progress update error: {e_ui}")
            pass


    try:
        from batch_processor import batch_generate_pdfs_full_optimized
        # from pdf_generator import register_fonts # batch_processor に移動または app.py で一度だけ呼ぶ
        # register_fonts() # アプリ起動時に一度だけ呼ぶのが望ましい

        status_text_placeholder.info(
            f"一括PDF生成を開始します... 対象: {batch_pdf_mode_ui}, "
            f"向き: {'横' if pdf_orientation_landscape_ui else '縦'}, "
            f"並列処理: {'有効' if use_parallel_processing_ui else '無効'} (ワーカー: {max_pdf_workers_ui}), "
            f"高速モード: {'有効' if fast_mode_enabled_ui else '無効'}"
        )

        overall_start_time = time.time()

        # zip_file_bytes_io, failed_pdf_info = batch_generate_pdfs_full_optimized(...) # failed_pdf_info を受け取る
        zip_file_bytes_io, failed_pdf_details = batch_generate_pdfs_full_optimized( # 変数名を統一
            df=df.copy(), # メインのdfはコピーして渡す
            mode=mode_arg_for_batch,
            landscape=pdf_orientation_landscape_ui,
            target_data=target_data.copy() if target_data is not None else None, # target_dataもコピー
            progress_callback=ui_progress_callback,
            use_parallel=use_parallel_processing_ui,
            max_workers=max_pdf_workers_ui if use_parallel_processing_ui else 1,
            fast_mode=fast_mode_enabled_ui
        )

        overall_end_time = time.time()
        duration_sec = overall_end_time - overall_start_time

        progress_bar_placeholder.empty() # プログレスバーをクリア
        status_text_placeholder.empty() # ステータステキストをクリア

        # 成功したPDFの数を計算 (ZIPファイルが空でないかで判断)
        # より正確には batch_generate_pdfs_mp_optimized から成功数を返す
        # ここでは、失敗情報がなければ全て成功とみなすか、ZIPの内容で判断
        num_successful_pdfs = reports_to_generate - len(failed_pdf_details)

        if zip_file_bytes_io and zip_file_bytes_io.getbuffer().nbytes > 22: # ZIPファイルが空でないことを確認 (空のZIPは約22バイト)
            zip_filename = f"入院患者数予測_一括_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}{'_横' if pdf_orientation_landscape_ui else '_縦'}.zip"

            col_dl_btn, col_dl_info = st.columns([1, 2])
            with col_dl_btn:
                st.download_button(
                    label="📥 ZIPファイルをダウンロード",
                    data=zip_file_bytes_io.getvalue(),
                    file_name=zip_filename,
                    mime="application/zip",
                    key="download_batch_zip_final_button_v2", # キーを更新
                    use_container_width=True
                )
            with col_dl_info:
                st.success(f"{num_successful_pdfs}件のPDF生成に成功しました。(処理時間: {duration_sec:.1f}秒)")
                st.caption(f"ファイル名: {zip_filename}")
                st.caption(f"ZIPサイズ: {zip_file_bytes_io.getbuffer().nbytes / (1024*1024):.2f} MB")

            del zip_file_bytes_io # メモリ解放
            gc.collect()
        elif num_successful_pdfs > 0 : # ZIPが空でも一部成功している場合（個別保存など別の方法で対応する場合）
             st.info(f"{num_successful_pdfs}件のPDFは内部的に生成されましたが、ZIPファイルの作成に問題があった可能性があります。")
        else: # 全て失敗した場合
            st.error("PDFファイルの生成に失敗しました。詳細はログを確認してください。")


        # 失敗したPDFの情報があれば表示
        if failed_pdf_details:
            st.warning(f"{len(failed_pdf_details)}件のPDF生成に失敗しました。")
            with st.expander("失敗したPDFリストと理由"):
                for item in failed_pdf_details:
                    st.markdown(f"- **{item['name']}**: `{item['reason']}`")
        elif num_successful_pdfs == reports_to_generate and num_successful_pdfs > 0 :
             st.success("全ての一括PDF生成が完了しました！")


    except Exception as ex:
        # メインの呼び出し側でもエラーをキャッチ
        logger.error(f"一括PDF生成の実行中に予期せぬエラー: {ex}", exc_info=True)
        st.error(f"一括PDF生成で予期せぬエラーが発生しました: {ex}")
        # st.error(traceback.format_exc()) # これはデバッグ時のみ
        if progress_bar_placeholder: progress_bar_placeholder.empty()
        if status_text_placeholder: status_text_placeholder.empty()

def generate_and_preview_pdf(df, target_data, print_target, target_code, target_name, print_orientation):
    """PDF生成とプレビュー"""
    try:
        with st.spinner(f"{target_name}のPDFを生成しています..."):
            pdf_buffer = generate_single_pdf(df, target_data, target_code, target_name, print_orientation == "横向き")
            
            if pdf_buffer:
                st.success(f"{target_name}のPDFが生成されました！")
                
                # PDFプレビュー用のbase64エンコード
                pdf_base64 = base64.b64encode(pdf_buffer.getvalue()).decode('utf-8')
                
                # PDFビューアの埋め込み
                pdf_display = f"""
                <iframe src="data:application/pdf;base64,{pdf_base64}" 
                        width="100%" height="800px" type="application/pdf">
                </iframe>
                """
                st.markdown(pdf_display, unsafe_allow_html=True)
                
                # ダウンロードボタン
                filename = f"入院患者数予測_{target_name}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                st.download_button(
                    label="📥 PDFをダウンロード",
                    data=pdf_buffer.getvalue(),
                    file_name=filename,
                    mime="application/pdf",
                    key=f"download_preview_{target_code}"
                )
            else:
                st.error("PDFの生成に失敗しました。")
                
    except Exception as e:
        st.error(f"PDFプレビュー中にエラーが発生しました: {e}")

def generate_and_print_pdf(df, target_data, print_target, target_code, target_name, print_orientation, print_copies):
    """PDF生成と印刷"""
    try:
        with st.spinner(f"{target_name}のPDFを生成・印刷準備中..."):
            pdf_buffer = generate_single_pdf(df, target_data, target_code, target_name, print_orientation == "横向き")
            
            if pdf_buffer:
                # JavaScript印刷コードの生成
                pdf_base64 = base64.b64encode(pdf_buffer.getvalue()).decode('utf-8')
                
                print_js = f"""
                <script>
                function printPDF() {{
                    var printWindow = window.open('', '_blank');
                    printWindow.document.write(`
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <title>印刷 - {target_name}</title>
                            <style>
                                body {{ margin: 0; padding: 0; }}
                                iframe {{ width: 100%; height: 100vh; border: none; }}
                            </style>
                        </head>
                        <body>
                            <iframe src="data:application/pdf;base64,{pdf_base64}" onload="setTimeout(function(){{window.print();}}, 1000);"></iframe>
                        </body>
                        </html>
                    `);
                    printWindow.document.close();
                }}
                
                // 自動実行
                printPDF();
                </script>
                """
                
                # 印刷実行
                st.markdown(print_js, unsafe_allow_html=True)
                
                # 成功メッセージ
                st.success(f"✅ {target_name}のPDF印刷ダイアログを開きました！")
                st.info(f"印刷部数: {print_copies}部（印刷ダイアログで設定してください）")
                
                # バックアップダウンロード
                filename = f"入院患者数予測_{target_name}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                st.download_button(
                    label="📥 バックアップ：PDFをダウンロード",
                    data=pdf_buffer.getvalue(),
                    file_name=filename,
                    mime="application/pdf",
                    key=f"download_backup_{target_code}"
                )
                
                # 印刷のヒント
                with st.expander("💡 印刷のヒント", expanded=False):
                    st.markdown("""
                    **印刷がうまくいかない場合：**
                    1. ブラウザのポップアップブロッカーを無効にしてください
                    2. 印刷ダイアログで用紙サイズを確認してください（A4推奨）
                    3. 「バックアップ：PDFをダウンロード」からファイルを保存して、通常のPDFビューアで印刷することもできます
                    
                    **推奨印刷設定：**
                    - 用紙サイズ: A4
                    - 向き: """ + ("横向き" if print_orientation == "横向き" else "縦向き") + """
                    - 倍率: 実際のサイズ（100%）
                    """)
                
            else:
                st.error("PDFの生成に失敗しました。")
                
    except Exception as e:
        st.error(f"PDF印刷中にエラーが発生しました: {e}")
        st.error(traceback.format_exc())

def generate_single_pdf(df, target_data, target_code, target_name, is_landscape=False):
    """単一PDF生成"""
    try:
        from pdf_generator import create_pdf, create_landscape_pdf
        from forecast import generate_filtered_summaries
        
        # データの準備
        if target_code == "全体":
            filtered_df = df.copy()
            filter_code = "全体"
        else:
            if target_code in df['診療科名'].values:
                filtered_df = df[df['診療科名'] == target_code].copy()
                filter_code = target_code
            elif target_code in df['病棟コード'].values:
                filtered_df = df[df['病棟コード'] == target_code].copy()
                filter_code = target_code
            else:
                filtered_df = df.copy()
                filter_code = "全体"
        
        if filtered_df.empty:
            return None
        
        # 予測データの生成
        try:
            forecast_df, df_weekday, df_holiday, df_all_avg = generate_filtered_summaries(filtered_df)
        except Exception as e:
            print(f"予測データ生成エラー: {e}")
            # フォールバックデータの作成
            forecast_df = pd.DataFrame()
            df_weekday = pd.DataFrame()
            df_holiday = pd.DataFrame()
            df_all_avg = pd.DataFrame()
        
        # 最新日付の取得
        latest_date = filtered_df['日付'].max() if '日付' in filtered_df.columns else pd.Timestamp.now()
        
        # PDF生成
        if is_landscape:
            pdf_buffer = create_landscape_pdf(
                forecast_df=forecast_df,
                df_weekday=df_weekday,
                df_holiday=df_holiday,
                df_all_avg=df_all_avg,
                chart_data=filtered_df,
                title_prefix=target_name,
                latest_date=latest_date,
                target_data=target_data,
                filter_code=filter_code,
                graph_days=[90, 180]
            )
        else:
            pdf_buffer = create_pdf(
                forecast_df=forecast_df,
                df_weekday=df_weekday,
                df_holiday=df_holiday,
                df_all_avg=df_all_avg,
                chart_data=filtered_df,
                title_prefix=target_name,
                latest_date=latest_date,
                target_data=target_data,
                filter_code=filter_code,
                graph_days=[90, 180]
            )
        
        return pdf_buffer
        
    except Exception as e:
        print(f"PDF生成エラー: {e}")
        return None

# ===== 追加のヘルパー関数 =====

def create_print_preview_interface():
    """印刷プレビューインターフェースの作成"""
    st.markdown("""
    <style>
    .print-preview {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin: 10px 0;
        background-color: #f9f9f9;
    }
    .print-settings {
        background-color: #e8f4f8;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

def create_pdf_output_tab():
    """メインのPDF出力タブ作成関数（app.pyから呼び出される）"""
    try:
        display_batch_pdf_tab()
    except Exception as e:
        st.error(f"PDF出力タブの表示中にエラーが発生しました: {e}")
        st.error("必要なモジュールが正しくインストールされているか確認してください。")

# ===== 使用例とドキュメント =====
"""
使用方法:

1. app.py で以下のようにインポート・呼び出し:
   ```python
   from pdf_output_tab import create_pdf_output_tab
   
   with tab5:  # 出力・予測タブ
       create_pdf_output_tab()
   ```

2. 必要な依存モジュール:
   - pdf_generator.py
   - batch_processor.py
   - forecast.py

3. フォント設定:
   - fonts/NotoSansJP-Regular.ttf が必要

主な機能:
- 一括PDF出力（ZIP形式）
- 個別PDF印刷プレビュー
- ブラウザ経由での直接印刷
- 印刷設定（部数、向きなど）
- エラーハンドリング
"""