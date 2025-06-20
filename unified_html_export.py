import json
from chart import create_interactive_patient_chart, plotly_fig_to_base64_img

def generate_unified_html_export(kpis_data, period_desc, dashboard_type="department"):
    """
    各部門/病棟ごとに目標ライン・達成ゾーンを含むグラフをBase64画像でHTMLに埋め込むエクスポート
    Parameters:
    - kpis_data: 各部門/病棟のKPIデータ(dict、'chart_data'含む)
    - period_desc: 期間の説明
    - dashboard_type: "department" または "ward"
    """
    # 指標の定義（例として日平均在院患者数のみ）
    metric_config = {
        "daily_census": {
            "title": "日平均在院患者数",
            "unit": "人",
            "data_key": "chart_data",      # 部門/病棟ごとのグラフ用DataFrame
            "target_key": "daily_census_target", # 目標値
            "zone_key": "target_zone",     # 達成ゾーン(例: [min, max])
        }
        # 必要に応じて他指標も追加可
    }

    dashboard_title = "診療科別" if dashboard_type == "department" else "病棟別"

    # HTMLヘッダ
    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{dashboard_title}パフォーマンスダッシュボード - {period_desc}</title>
    <style>
        body {{
            background: #f5f7fa;
            font-family: 'Noto Sans JP', Meiryo, sans-serif;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1 {{
            text-align: center;
            color: #293a27;
            margin-bottom: 20px;
            font-size: 1.8em;
        }}
        .kpi-section {{
            margin-bottom: 40px;
            background: #fff;
            border-radius: 12px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.07);
            padding: 24px 24px 10px 24px;
        }}
        .kpi-section h2 {{
            color: #333;
            margin-bottom: 10px;
            font-size: 1.1em;
        }}
        .kpi-graph {{
            text-align: center;
            margin-bottom: 10px;
        }}
        .kpi-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        .kpi-table th, .kpi-table td {{
            border: 1px solid #ccc;
            padding: 6px 10px;
            text-align: center;
            font-size: 1em;
        }}
        .kpi-table th {{
            background: #e0f2f1;
            color: #333;
        }}
        @media (max-width: 768px) {{
            .container {{
                max-width: 98vw;
                padding: 0;
            }}
            .kpi-section {{
                padding: 14px 3vw 4px 3vw;
            }}
        }}
    </style>
</head>
<body>
<div class="container">
    <h1>{dashboard_title}パフォーマンスダッシュボード <span style="font-size:0.8em;">{period_desc}</span></h1>
"""

    # 各部門/病棟ごとにセクションを出力
    for kpi in kpis_data:
        name = kpi.get('dept_name' if dashboard_type == 'department' else 'ward_name', '不明')
        html_content += f'<div class="kpi-section">\n'
        html_content += f'  <h2>{name}</h2>\n'

        # グラフ出力
        for metric_key, conf in metric_config.items():
            chart_data = kpi.get(conf["data_key"])
            target_value = kpi.get(conf["target_key"])
            zone = kpi.get(conf.get("zone_key")) if conf.get("zone_key") else None

            if chart_data is not None:
                fig = create_interactive_patient_chart(
                    chart_data,
                    title=f"{name} {conf['title']}推移",
                    target_line=target_value,
                    target_zone=zone
                )
                img_tag = plotly_fig_to_base64_img(fig)
                html_content += f'  <div class="kpi-graph">{img_tag}</div>\n'

        # KPIテーブル（例示、実際のKPI内容に応じてカスタマイズ可）
        html_content += '<table class="kpi-table"><tr>'
        html_content += '<th>指標</th><th>値</th><th>目標</th><th>達成率</th>'
        html_content += '</tr>'
        # サンプルとして日平均在院患者数
        val = kpi.get('daily_avg_census', '')
        tgt = kpi.get('daily_census_target', '')
        ach = kpi.get('daily_census_achievement', '')
        html_content += f'<tr><td>日平均在院患者数</td><td>{val}</td><td>{tgt}</td><td>{ach}</td></tr>'
        html_content += '</table>\n'

        html_content += '</div>\n'

    html_content += """
</div>
</body>
</html>
"""
    return html_content
