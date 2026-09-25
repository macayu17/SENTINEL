"""Generate a printable research report from a completed simulation snapshot."""

from io import BytesIO
from math import isfinite
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


INK = colors.HexColor("#242824")
MUTED = colors.HexColor("#687068")
RULE = colors.HexColor("#d4d6d0")
ACCENT = colors.HexColor("#896d37")
CANDLE_UP = colors.HexColor("#34785a")
CANDLE_DOWN = colors.HexColor("#b33d35")
TABLE_CELL = ParagraphStyle(
    name="TableCell",
    fontName="Helvetica",
    fontSize=8,
    leading=10.5,
    textColor=INK,
)


def _page_footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.35)
    canvas.line(18 * mm, 11 * mm, 192 * mm, 11 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(18 * mm, 7 * mm, "SENTINEL / SIMULATION RESEARCH RECORD")
    canvas.drawRightString(192 * mm, 7 * mm, f"PAGE {document.page}")
    canvas.restoreState()


def _number(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return f"{number:.{digits}f}" if isfinite(number) else "N/A"


def _label(value: Any) -> str:
    return str(value).replace("_", " ").title()


def _wrap_table_cell(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 40:
        return Paragraph(escape(value), TABLE_CELL)
    return value


def _table(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
    wrapped_rows = [[_wrap_table_cell(value) for value in row] for row in rows]
    table = Table(wrapped_rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, RULE),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
    ]
    if header:
        commands.extend([
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
        ])
    table.setStyle(TableStyle(commands))
    return table


def _price_chart(path: list[dict[str, Any]]) -> Drawing:
    drawing = Drawing(170 * mm, 58 * mm)
    points = [
        (float(item.get("timestamp", 0)), float(item.get("price", 0)))
        for item in path
        if isinstance(item.get("price"), (int, float))
    ]
    if len(points) < 2:
        drawing.add(String(0, 25 * mm, "No price path recorded", fontName="Helvetica", fontSize=9, fillColor=MUTED))
        return drawing

    candles: list[dict[str, float]] = []
    for timestamp, price in points:
        bucket = int(timestamp // 5) * 5
        if candles and candles[-1]["time"] == bucket:
            candles[-1]["high"] = max(candles[-1]["high"], price)
            candles[-1]["low"] = min(candles[-1]["low"], price)
            candles[-1]["close"] = price
        else:
            candles.append({"time": bucket, "open": price, "high": price, "low": price, "close": price})
    if len(candles) > 72:
        stride = (len(candles) + 71) // 72
        candles = candles[::stride]

    chart_x, chart_y = 12 * mm, 8 * mm
    chart_width, chart_height = 145 * mm, 40 * mm
    low = min(candle["low"] for candle in candles)
    high = max(candle["high"] for candle in candles)
    padding = max((high - low) * 0.12, 0.005)
    low, high = low - padding, high + padding
    y = lambda value: chart_y + (value - low) / (high - low) * chart_height
    step = chart_width / max(len(candles), 16)

    for index in range(5):
        grid_y = chart_y + chart_height * index / 4
        drawing.add(Line(chart_x, grid_y, chart_x + chart_width, grid_y, strokeColor=RULE, strokeWidth=0.35))
    for index, candle in enumerate(candles):
        x = chart_x + step * (index + 0.5)
        color = CANDLE_UP if candle["close"] >= candle["open"] else CANDLE_DOWN
        body_bottom = y(min(candle["open"], candle["close"]))
        body_top = y(max(candle["open"], candle["close"]))
        body_width = max(1.2 * mm, min(3 * mm, step * 0.62))
        drawing.add(Line(x, y(candle["low"]), x, y(candle["high"]), strokeColor=color, strokeWidth=0.7))
        drawing.add(Rect(x - body_width / 2, body_bottom, body_width, max(0.7, body_top - body_bottom), fillColor=color, strokeColor=color, strokeWidth=0))
    drawing.add(String(12 * mm, 54 * mm, "SIMULATED MID-PRICE / 5-SECOND OHLC", fontName="Helvetica-Bold", fontSize=8, fillColor=MUTED))
    return drawing


def build_simulation_pdf(report: dict[str, Any]) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Sentinel simulation session report",
        author="Sentinel",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Times-Bold", fontSize=24, leading=29, textColor=INK, alignment=TA_LEFT, spaceAfter=6))
    styles.add(ParagraphStyle(name="ReportSubtitle", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=15, textColor=MUTED, spaceAfter=12))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Times-Bold", fontSize=14, leading=18, textColor=INK, spaceBefore=15, spaceAfter=7, keepWithNext=True))
    styles.add(ParagraphStyle(name="Kicker", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=ACCENT, spaceAfter=4))
    styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=INK, spaceAfter=6))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED))

    config = report.get("run_config", {})
    path = report.get("price_path", [])
    flow = report.get("order_flow", {})
    summary = flow.get("summary", {})
    metrics = report.get("validation_metrics", {})
    agent_metrics = report.get("agent_metrics", {})
    warnings = report.get("warning_timeline", [])
    events = report.get("events", [])
    orders = report.get("recent_orders", [])

    story: list[Any] = [
        Paragraph("SENTINEL / NASDAQ MARKET MICROSTRUCTURE", styles["Kicker"]),
        Paragraph("Simulation session report", styles["ReportTitle"]),
        Paragraph("Observed market quality, execution activity, and participant outcomes from one completed synthetic session.", styles["ReportSubtitle"]),
        HRFlowable(width="100%", thickness=0.6, color=RULE, spaceAfter=10),
    ]

    metadata = [
        ["Scenario", _label(config.get("scenario", "N/A")), "Preset", _label(config.get("preset", "N/A")), "Seed", config.get("seed", "Unseeded")],
        ["Venue", config.get("venue", "N/A"), "Simulated seconds", _number(config.get("elapsed_seconds"), 1), "Steps", f"{int(config.get('steps', 0)):,}"],
        ["Starting price", _number(config.get("initial_price"), 2), "Playback speed", f"{_number(config.get('speed'), 1)}x", "Latency", _label(config.get("latency_mode", "N/A"))],
        ["Agents", config.get("agent_count", "N/A"), "Informed access", "On" if config.get("informed_access") else "Off", "Generated", str(report.get("generated_at", "N/A"))],
    ]
    metadata_table = _table(metadata, [28 * mm, 43 * mm, 32 * mm, 38 * mm, 28 * mm, 30 * mm], header=False)
    metadata_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), MUTED),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTNAME", (4, 0), (4, -1), "Helvetica-Bold"),
    ]))
    story.extend([metadata_table, Paragraph("This report describes the selected simulator configuration. It is not evidence of live-market profitability or a forecast of future prices.", styles["Small"])])

    first = path[0].get("price", config.get("initial_price", 0)) if path else config.get("initial_price", 0)
    last = path[-1].get("price", first) if path else first
    spread_values = [float(point.get("spread", 0) or 0) for point in path]
    depth_values = [float(point.get("depth", 0) or 0) for point in path]
    headline = [
        ["Result", "Value", "Interpretation"],
        ["Final price", f"${_number(last, 2)}", f"{((float(last) - float(first)) / float(first) * 100) if float(first) else 0:+.2f}% from start"],
        ["Peak spread", _number(max(spread_values, default=0), 4), f"Mean {_number(metrics.get('spread_mean'), 4)}"],
        ["Minimum depth", f"{int(min(depth_values, default=0)):,}", f"{len(path):,} observations"],
        ["Trades", f"{len(flow.get('trades', [])):,}", f"{_number(summary.get('match_rate'), 2)}% matched"],
        ["Warnings", f"{len(warnings):,}", "Detector transitions"],
    ]
    story.extend([Paragraph("Executive summary", styles["Section"]), _table(headline, [38 * mm, 35 * mm, 93 * mm]), Spacer(1, 5), _price_chart(path)])

    findings = [
        f"The simulated price moved {((float(last) - float(first)) / float(first) * 100) if float(first) else 0:+.2f}% from {_number(first, 2)} to {_number(last, 2)}.",
        f"Displayed depth reached {int(min(depth_values, default=0)):,}; the widest spread was {_number(max(spread_values, default=0), 4)}.",
        f"{len(flow.get('trades', [])):,} trades followed {int(flow.get('submitted_orders', 0)):,} submitted orders.",
        f"The run recorded {len(warnings):,} detector transitions and {len(events):,} retained events.",
    ]
    story.extend([Paragraph("Run findings", styles["Section"]), *[Paragraph(f"{index}. {finding}", styles["Body"]) for index, finding in enumerate(findings, 1)]])

    validation_rows = [["Measurement", "Value"]] + [[_label(key), _number(value, 6)] for key, value in metrics.items()]
    story.extend([Paragraph("Validation measurements", styles["Section"]), Paragraph("These values are calculated from the recorded state path and execution counters.", styles["Small"]), _table(validation_rows, [110 * mm, 55 * mm])])

    grouped: dict[str, dict[str, float]] = {}
    for agent in agent_metrics.values():
        row = grouped.setdefault(str(agent.get("agent_type", "unknown")), {"count": 0, "trades": 0, "position": 0, "pnl": 0})
        row["count"] += 1
        row["trades"] += float(agent.get("num_trades", 0) or 0)
        row["position"] += float(agent.get("position", 0) or 0)
        row["pnl"] += float(agent.get("total_pnl", 0) or 0)
    agent_rows = [["Agent type", "Count", "Trades", "Net position", "Total P&L"]] + [[_label(name), int(row["count"]), int(row["trades"]), _number(row["position"], 0), _number(row["pnl"], 2)] for name, row in sorted(grouped.items())]
    story.extend([Paragraph("Participant outcomes", styles["Section"]), Paragraph("Agents are rule-based simulated participants. Results are grouped by configured behavior.", styles["Small"]), _table(agent_rows, [50 * mm, 22 * mm, 25 * mm, 35 * mm, 33 * mm])])

    execution_rows = [["Execution result", "Value"], ["Order submissions", flow.get("submitted_orders", 0)], ["Cancel requests", flow.get("cancel_requests", 0)], ["Accepted cancels", flow.get("accepted_cancels", 0)], ["Terminal cancels", flow.get("terminal_cancels", 0)], ["Buy volume", summary.get("buy_volume", 0)], ["Sell volume", summary.get("sell_volume", 0)], ["Submitted notional", _number(summary.get("submitted_notional"), 4)], ["Retained recent orders", len(orders)]]
    story.extend([Paragraph("Execution accounting", styles["Section"]), _table(execution_rows, [110 * mm, 55 * mm])])

    coverage_rows = [
        ["Recorded evidence", "Count"],
        ["Price observations", len(path)],
        ["Retained events", len(events)],
        ["Recent order records", len(orders)],
        ["Matched trades", len(flow.get("trades", []))],
        ["Simulated agents", len(agent_metrics)],
        ["Warning transitions", len(warnings)],
    ]
    story.extend([
        Paragraph("Data coverage", styles["Section"]),
        Paragraph("Coverage identifies how much recorded evidence supports this summary. Short runs should not be treated as stable estimates.", styles["Small"]),
        _table(coverage_rows, [110 * mm, 55 * mm]),
    ])

    event_counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("type", "unknown"))
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
    event_rows = [["Event type", "Count"]] + [[_label(name), count] for name, count in sorted(event_counts.items(), key=lambda item: (-item[1], item[0]))]
    warning_rows = [["Time", "Detector", "Level"]] + [[f"{_number(item.get('timestamp'), 1)}s", _label(item.get("detector", "warning")), _label(item.get("warning_level", item.get("pattern", "detected")))] for item in warnings]
    story.extend([Paragraph("Detector and event record", styles["Section"]), _table(warning_rows if warnings else [["Detector record"], ["No detector state crossed a warning threshold."]], [35 * mm, 65 * mm, 65 * mm]), Spacer(1, 8), _table(event_rows if len(event_rows) > 1 else [["Event type", "Count"], ["No retained events", 0]], [110 * mm, 55 * mm])])

    definitions = [
        ["Term", "Meaning in this report"],
        ["Spread", "Ask price minus bid price; a wider value indicates more simulated trading friction."],
        ["Depth", "Quantity resting in the simulated order book."],
        ["Imbalance", "Relative difference between displayed buy and sell quantity; it describes pressure, not a prediction."],
        ["Market impact", "Absolute price movement between consecutive simulated states, expressed in basis points."],
        ["Slippage", "Difference between an execution reference and the simulated fill price."],
        ["Match rate", "Matched orders as a percentage of submitted orders for this run."],
        ["P&L", "Simulated profit and loss. Realized P&L uses closed trades; unrealized P&L marks open positions to the final simulated price."],
        ["Warning", "A configured detector threshold transition, not investment advice or a verified real-market forecast."],
    ]
    story.extend([Paragraph("Terms and interpretation", styles["Section"]), _table(definitions, [38 * mm, 127 * mm]), Spacer(1, 8), Paragraph("Method and limitations", styles["Section"]), Paragraph("This is one synthetic run under the listed seed, scenario, population, and latency assumptions. Simulated prices, depth, liquidity, fills, and P&L are generated by Sentinel. The downloadable JSON contains the retained raw state, order, trade, and event records for external analysis.", styles["Body"])])

    document.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buffer.getvalue()
