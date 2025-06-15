import json

def generate_unified_html_export(kpis_data, period_desc, dashboard_type="department"):
    """
    全ての指標を含む統合HTMLファイルを生成
    
    Parameters:
    - kpis_data: 各部門/病棟のKPIデータのリスト
    - period_desc: 期間の説明文字列
    - dashboard_type: "department" または "ward"
    """
    
    # 各指標の設定
    metrics_config = {
        "daily_census": {
            "title": "日平均在院患者数",
            "unit": "人",
            "fields": {
                "avg": "daily_avg_census",
                "recent": "recent_week_daily_census", 
                "target": "daily_census_target",
                "achievement": "daily_census_achievement"
            }
        },
        "weekly_admissions": {
            "title": "週合計新入院患者数",
            "unit": "件",
            "fields": {
                "avg": "weekly_avg_admissions",
                "recent": "recent_week_admissions",
                "target": "weekly_admissions_target", 
                "achievement": "weekly_admissions_achievement"
            }
        },
        "avg_los": {
            "title": "平均在院日数",
            "unit": "日",
            "fields": {
                "avg": "avg_length_of_stay",
                "recent": "recent_week_avg_los",
                "target": "avg_los_target",
                "achievement": "avg_los_achievement"
            }
        }
    }
    
    # 各指標ごとのデータを整形
    all_metrics_data = {}
    for metric_key, metric_config in metrics_config.items():
        metric_data = []
        fields = metric_config["fields"]
        
        for kpi in kpis_data:
            # 名前フィールドの決定
            name_field = "dept_name" if dashboard_type == "department" else "ward_name"
            
            data_item = {
                "name": kpi.get(name_field, "不明"),
                "avg": kpi.get(fields["avg"], 0),
                "recent": kpi.get(fields["recent"], 0),
                "target": kpi.get(fields["target"], None),
                "achievement": kpi.get(fields["achievement"], 0)
            }
            
            # 病棟の場合、病床情報も追加
            if dashboard_type == "ward" and metric_key == "daily_census":
                data_item["bed_count"] = kpi.get("bed_count", None)
                data_item["bed_occupancy_rate"] = kpi.get("bed_occupancy_rate", None)
            
            metric_data.append(data_item)
        
        # ソート（平均在院日数は昇順、その他は降順）
        reverse = metric_key != "avg_los"
        metric_data.sort(key=lambda x: x["achievement"], reverse=reverse)
        
        all_metrics_data[metric_key] = metric_data
    
    # HTML生成
    dashboard_title = "診療科別" if dashboard_type == "department" else "病棟別"
    
    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{dashboard_title}パフォーマンスダッシュボード - {period_desc}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            background: #f5f7fa;
            font-family: 'Noto Sans JP', Meiryo, sans-serif;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1920px;
            margin: 0 auto;
        }}
        
        h1 {{
            text-align: center;
            color: #293a27;
            margin-bottom: 20px;
            font-size: 1.8em;
        }}
        
        .controls {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }}
        
        .metric-selector {{
            display: flex;
            gap: 10px;
            background: white;
            padding: 5px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .metric-btn {{
            padding: 10px 20px;
            border: none;
            background: #e0e0e0;
            color: #666;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.3s ease;
        }}
        
        .metric-btn:hover {{
            background: #d0d0d0;
        }}
        
        .metric-btn.active {{
            background: #4CAF50;
            color: white;
        }}
        
        .period-info {{
            background: white;
            padding: 10px 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            font-weight: 600;
            color: #333;
        }}
        
        .grid-container {{
            display: grid;
            gap: 20px;
            margin-top: 20px;
        }}
        
        /* レスポンシブグリッド */
        @media (min-width: 1600px) {{
            .grid-container {{ grid-template-columns: repeat(5, 1fr); }}
        }}
        
        @media (min-width: 1200px) and (max-width: 1599px) {{
            .grid-container {{ grid-template-columns: repeat(4, 1fr); }}
        }}
        
        @media (min-width: 900px) and (max-width: 1199px) {{
            .grid-container {{ grid-template-columns: repeat(3, 1fr); }}
        }}
        
        @media (min-width: 600px) and (max-width: 899px) {{
            .grid-container {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        
        @media (max-width: 599px) {{
            .grid-container {{ grid-template-columns: 1fr; }}
        }}
        
        .metric-card {{
            background: white;
            border-radius: 11px;
            border-left: 6px solid #ccc;
            padding: 16px;
            transition: all 0.3s ease;
            height: 100%;
        }}
        
        .metric-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        
        .card-title {{
            font-size: 1.13em;
            font-weight: 700;
            margin-bottom: 10px;
            color: #293a27;
        }}
        
        .card-content {{
            display: flex;
            flex-direction: column;
            gap: 5px;
        }}
        
        .metric-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .metric-label {{
            font-size: 0.93em;
            color: #7b8a7a;
        }}
        
        .metric-value {{
            font-size: 1.07em;
            font-weight: 700;
            color: #2e3532;
        }}
        
        .achievement-row {{
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .achievement-label {{
            font-weight: 700;
            font-size: 1.03em;
        }}
        
        .achievement-value {{
            font-weight: 700;
            font-size: 1.20em;
        }}
        
        .bed-info {{
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid #e0e0e0;
        }}
        
        .bed-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 3px;
        }}
        
        .bed-label {{
            font-size: 0.85em;
            color: #999;
        }}
        
        .bed-value {{
            font-size: 0.9em;
            color: #666;
            font-weight: 600;
        }}
        
        /* 達成率による色分け */
        .achievement-high {{ color: #7fb069; }}
        .achievement-medium {{ color: #f5d76e; }}
        .achievement-low {{ color: #e08283; }}
        
        .border-high {{ border-left-color: #7fb069; }}
        .border-medium {{ border-left-color: #f5d76e; }}
        .border-low {{ border-left-color: #e08283; }}
        
        @media print {{
            body {{ padding: 10px; }}
            .controls {{ display: none; }}
            .grid-container {{ 
                grid-template-columns: repeat(5, 1fr);
                gap: 15px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{dashboard_title}パフォーマンスダッシュボード</h1>
        
        <div class="controls">
            <div class="metric-selector">
                <button class="metric-btn active" onclick="showMetric('daily_census')">日平均在院患者数</button>
                <button class="metric-btn" onclick="showMetric('weekly_admissions')">週合計新入院患者数</button>
                <button class="metric-btn" onclick="showMetric('avg_los')">平均在院日数</button>
            </div>
            <div class="period-info">期間: {period_desc}</div>
        </div>
        
        <div id="grid-container" class="grid-container"></div>
    </div>
    
    <script>
        // 全ての指標データ
        const metricsData = {json.dumps(all_metrics_data, ensure_ascii=False)};
        
        // 指標の設定
        const metricsConfig = {json.dumps(metrics_config, ensure_ascii=False)};
        
        // 現在表示中の指標
        let currentMetric = 'daily_census';
        
        // 達成率による色クラスを取得
        function getColorClass(achievement) {{
            if (achievement >= 100) return 'high';
            if (achievement >= 80) return 'medium';
            return 'low';
        }}
        
        // 数値のフォーマット
        function formatValue(value, decimals = 1) {{
            if (value === null || value === undefined) return '--';
            return value.toFixed(decimals);
        }}
        
        // カードのHTMLを生成
        function createCard(item, metric) {{
            const colorClass = getColorClass(item.achievement);
            const config = metricsConfig[metric];
            const unit = config.unit;
            
            let bedInfoHtml = '';
            if (metric === 'daily_census' && item.bed_count) {{
                const occupancyStr = item.bed_occupancy_rate !== null ? 
                    formatValue(item.bed_occupancy_rate) + '%' : '--';
                bedInfoHtml = `
                    <div class="bed-info">
                        <div class="bed-row">
                            <span class="bed-label">病床数:</span>
                            <span class="bed-value">${{item.bed_count}}床</span>
                        </div>
                        <div class="bed-row">
                            <span class="bed-label">稼働率:</span>
                            <span class="bed-value">${{occupancyStr}}</span>
                        </div>
                    </div>
                `;
            }}
            
            return `
                <div class="metric-card border-${{colorClass}}">
                    <div class="card-title">${{item.name}}</div>
                    <div class="card-content">
                        <div class="metric-row">
                            <span class="metric-label">期間平均:</span>
                            <span class="metric-value">${{formatValue(item.avg)}} ${{unit}}</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">直近週実績:</span>
                            <span class="metric-value">${{formatValue(item.recent)}} ${{unit}}</span>
                        </div>
                        <div class="metric-row">
                            <span class="metric-label">目標:</span>
                            <span class="metric-value">${{item.target ? formatValue(item.target) : '--'}} ${{unit}}</span>
                        </div>
                    </div>
                    <div class="achievement-row">
                        <span class="achievement-label achievement-${{colorClass}}">達成率:</span>
                        <span class="achievement-value achievement-${{colorClass}}">${{formatValue(item.achievement)}}%</span>
                    </div>
                    ${{bedInfoHtml}}
                </div>
            `;
        }}
        
        // 指標を表示
        function showMetric(metric) {{
            currentMetric = metric;
            
            // ボタンのアクティブ状態を更新
            document.querySelectorAll('.metric-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            event.target.classList.add('active');
            
            // グリッドをクリアして再描画
            const container = document.getElementById('grid-container');
            container.innerHTML = '';
            
            const data = metricsData[metric];
            data.forEach(item => {{
                container.innerHTML += createCard(item, metric);
            }});
        }}
        
        // 初期表示
        document.addEventListener('DOMContentLoaded', function() {{
            const container = document.getElementById('grid-container');
            const data = metricsData[currentMetric];
            data.forEach(item => {{
                container.innerHTML += createCard(item, currentMetric);
            }});
        }});
    </script>
</body>
</html>
"""
    
    return html_content