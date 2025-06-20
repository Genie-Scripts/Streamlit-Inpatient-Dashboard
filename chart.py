import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import base64

def create_interactive_patient_chart(
    data, title="入院患者数推移", days=90, 
    target_line=None, target_zone=None
):
    if not isinstance(data, pd.DataFrame) or data.empty:
        return go.Figure()
    if "日付" not in data.columns or "入院患者数（在院）" not in data.columns:
        return go.Figure()
    df = data.copy()
    df = df.dropna(subset=["日付"])
    df["日付"] = pd.to_datetime(df["日付"], errors='coerce')
    df = df.sort_values("日付")
    if days > 0 and len(df) > days:
        df = df.tail(days)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["日付"], y=df["入院患者数（在院）"],
        mode="lines+markers", name="入院患者数",
        line=dict(color="#3498db", width=2), marker=dict(size=5)
    ))
    if len(df) >= 7:
        df["7日移動平均"] = df["入院患者数（在院）"].rolling(window=7, min_periods=1).mean()
        fig.add_trace(go.Scatter(
            x=df["日付"], y=df["7日移動平均"],
            mode="lines", name="7日移動平均",
            line=dict(color="#2ecc71", dash="dash", width=2)
        ))
    if target_line is not None:
        fig.add_hline(
            y=target_line, line_dash="dash", line_color="#e74c3c",
            annotation_text="目標", annotation_position="top right", opacity=0.8
        )
    if target_zone and isinstance(target_zone, (list, tuple)) and len(target_zone) == 2:
        y0, y1 = sorted(target_zone)
        fig.add_shape(
            type="rect", x0=df["日付"].min(), x1=df["日付"].max(),
            y0=y0, y1=y1, fillcolor="rgba(39, 174, 96, 0.15)", line_width=0, layer="below"
        )
    fig.update_layout(
        title=title, margin=dict(l=10, r=10, t=40, b=10),
        xaxis_title="日付", yaxis_title="患者数",
        height=350, template="plotly_white", legend=dict(font=dict(size=12))
    )
    fig.update_xaxes(tickformat="%m/%d", tickangle=30)
    return fig

def create_interactive_dual_axis_chart(
    data, title="入院患者数と患者移動の推移", days=90, 
    left_col="入院患者数（在院）", right_col="新入院患者数"
):
    if not isinstance(data, pd.DataFrame) or data.empty:
        return go.Figure()
    if "日付" not in data.columns or left_col not in data.columns or right_col not in data.columns:
        return go.Figure()
    df = data.copy()
    df = df.dropna(subset=["日付"])
    df["日付"] = pd.to_datetime(df["日付"], errors='coerce')
    df = df.sort_values("日付")
    if days > 0 and len(df) > days:
        df = df.tail(days)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["日付"], y=df[right_col], name=right_col,
        marker_color="#e67e22", opacity=0.5, yaxis="y2"
    ))
    fig.add_trace(go.Scatter(
        x=df["日付"], y=df[left_col], mode="lines+markers", name=left_col,
        line=dict(color="#3498db", width=2), marker=dict(size=5), yaxis="y1"
    ))
    fig.update_layout(
        title=title,
        xaxis=dict(title="日付", tickformat="%m/%d", tickangle=30),
        yaxis=dict(title=left_col, side="left"),
        yaxis2=dict(title=right_col, overlaying="y", side="right", showgrid=False),
        height=350, template="plotly_white", legend=dict(font=dict(size=12))
    )
    return fig

def create_interactive_alos_chart(
    data, title="平均在院日数推移", days=90, 
    los_col="平均在院日数", census_col="平均在院患者数"
):
    if not isinstance(data, pd.DataFrame) or data.empty:
        return go.Figure()
    if "日付" not in data.columns or los_col not in data.columns or census_col not in data.columns:
        return go.Figure()
    df = data.copy()
    df = df.dropna(subset=["日付"])
    df["日付"] = pd.to_datetime(df["日付"], errors='coerce')
    df = df.sort_values("日付")
    if days > 0 and len(df) > days:
        df = df.tail(days)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["日付"], y=df[los_col], mode="lines+markers", name="平均在院日数",
        line=dict(color="#2980b9", width=2), marker=dict(size=5), yaxis="y1"
    ))
    fig.add_trace(go.Scatter(
        x=df["日付"], y=df[census_col], mode="lines", name="平均在院患者数",
        line=dict(color="#e74c3c", dash="dot", width=2), yaxis="y2"
    ))
    fig.update_layout(
        title=title,
        xaxis=dict(title="日付", tickformat="%m/%d", tickangle=30),
        yaxis=dict(title="平均在院日数", side="left"),
        yaxis2=dict(title="平均在院患者数", overlaying="y", side="right", showgrid=False),
        height=350, template="plotly_white", legend=dict(font=dict(size=12))
    )
    return fig

def plotly_fig_to_base64_img(fig, width=900, height=350):
    img_bytes = pio.to_image(fig, format='png', width=width, height=height, scale=2)
    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
    return f'<img src="data:image/png;base64,{img_base64}" style="width:100%;max-width:900px;" alt="グラフ">'
