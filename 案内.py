<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>パフォーマンスダッシュボード - QRコード配布資料</title>
    <style>
        body {
            font-family: 'Noto Sans JP', Meiryo, sans-serif;
            margin: 0;
            padding: 20px;
            background: white;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 20px;
        }
        .header h1 {
            color: #293a27;
            margin-bottom: 10px;
        }
        .header p {
            color: #666;
            font-size: 1.1em;
        }
        .qr-section {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 40px;
            margin: 40px 0;
            padding: 30px;
            background: #f8f9fa;
            border-radius: 12px;
            border: 2px dashed #4CAF50;
        }
        .qr-placeholder {
            width: 200px;
            height: 200px;
            border: 2px solid #ddd;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: white;
            color: #999;
            text-align: center;
            font-size: 14px;
        }
        .qr-info {
            flex: 1;
        }
        .qr-info h2 {
            color: #4CAF50;
            margin-bottom: 15px;
        }
        .url-box {
            background: white;
            padding: 15px;
            border-radius: 6px;
            border: 1px solid #ddd;
            font-family: monospace;
            word-break: break-all;
            margin: 15px 0;
        }
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 40px 0;
        }
        .feature {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }
        .feature-icon {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        .feature h3 {
            color: #293a27;
            margin-bottom: 10px;
        }
        .instructions {
            background: #e8f5e8;
            padding: 25px;
            border-radius: 8px;
            margin: 30px 0;
        }
        .instructions h3 {
            color: #2e7d32;
            margin-bottom: 15px;
        }
        .instructions ol {
            padding-left: 20px;
        }
        .instructions li {
            margin-bottom: 8px;
            line-height: 1.6;
        }
        .dashboards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        .dashboard-card {
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        .dashboard-card h4 {
            color: #4CAF50;
            margin-bottom: 10px;
        }
        .footer {
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #999;
        }
        @media print {
            .container {
                max-width: none;
            }
            .qr-section {
                break-inside: avoid;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏥 病院パフォーマンスダッシュボード</h1>
            <p>スマートフォンでいつでもアクセス可能</p>
        </div>

        <div class="qr-section">
            <div class="qr-placeholder">
                ここにQRコードを貼り付け
                <br><br>
                <small>QRコード生成サイト:<br>
                qr-code-generator.com</small>
            </div>
            <div class="qr-info">
                <h2>📱 アクセス方法</h2>
                <p><strong>方法1:</strong> QRコードをスキャン</p>
                <p><strong>方法2:</strong> 下記URLを直接入力</p>
                <div class="url-box">
                    https://genie-scripts.github.io/Streamlit-Inpatient-Dashboard/
                </div>
                <p><small>📌 ブックマーク保存推奨</small></p>
            </div>
        </div>

        <div class="features">
            <div class="feature">
                <div class="feature-icon">📊</div>
                <h3>リアルタイム指標</h3>
                <p>診療科・病棟別の最新パフォーマンス指標を確認できます</p>
            </div>
            <div class="feature">
                <div class="feature-icon">📱</div>
                <h3>スマホ最適化</h3>
                <p>スマートフォンで見やすいレスポンシブデザイン</p>
            </div>
            <div class="feature">
                <div class="feature-icon">🔄</div>
                <h3>自動更新</h3>
                <p>データは定期的に自動更新されます</p>
            </div>
            <div class="feature">
                <div class="feature-icon">🔒</div>
                <h3>プライバシー保護</h3>
                <p>個人情報は含まれていません</p>
            </div>
        </div>

        <div class="instructions">
            <h3>🔍 使用方法</h3>
            <ol>
                <li><strong>アクセス:</strong> QRコードをスキャンまたはURLを入力</li>
                <li><strong>ダッシュボード選択:</strong> 診療科別・病棟別から選択</li>
                <li><strong>指標切り替え:</strong> 画面上部のボタンで指標を切り替え</li>
                <li><strong>詳細確認:</strong> 各カードで実績・目標・達成率を確認</li>
                <li><strong>ブックマーク:</strong> 頻繁にアクセスする場合は保存推奨</li>
            </ol>
        </div>

        <div class="dashboards">
            <div class="dashboard-card">
                <h4>📊 診療科別パフォーマンス</h4>
                <p>各診療科の入院患者数、新入院患者数、平均在院日数の実績と目標達成率</p>
            </div>
            <div class="dashboard-card">
                <h4>🏨 病棟別パフォーマンス</h4>
                <p>各病棟の入院患者数、新入院患者数、平均在院日数の実績と目標達成率</p>
            </div>
        </div>

        <div class="instructions">
            <h3>📝 確認できる指標</h3>
            <ul>
                <li><strong>日平均在院患者数:</strong> 期間平均・直近週実績・目標・達成率</li>
                <li><strong>週合計新入院患者数:</strong> 期間平均・直近週実績・目標・達成率</li>
                <li><strong>平均在院日数:</strong> 期間平均・直近週実績・目標・達成率</li>
                <li><strong>病床稼働率:</strong> 病棟別パフォーマンスで確認可能</li>
            </ul>
        </div>

        <div style="background: #fff3e0; padding: 20px; border-radius: 8px; margin: 30px 0;">
            <h3 style="color: #f57c00; margin-bottom: 15px;">⚠️ 注意事項</h3>
            <ul>
                <li>このダッシュボードは院内職員専用です</li>
                <li>外部への共有はお控えください</li>
                <li>データは統計情報のみで個人情報は含まれていません</li>
                <li>表示されない場合はネットワーク接続を確認してください</li>
                <li>問題がある場合は情報システム部門にお問い合わせください</li>
            </ul>
        </div>

        <div class="footer">
            <p>🏥 病院パフォーマンス分析システム</p>
            <p>発行日: [日付を記入] | 問い合わせ: 情報システム部門</p>
        </div>
    </div>
</body>
</html>