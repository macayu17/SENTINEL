"""Printable session report: one completed simulation, explained for any reader.

Layout follows the web app: an ink title band with the orange accent, KPI tiles,
annotated charts, plain-language findings, then the detailed record and a glossary.
"""

from io import BytesIO
from math import isfinite
from statistics import median
from typing import Any, Callable
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, PolyLine, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# Palette: the web app's tokens, adapted for white paper.
INK = colors.HexColor("#111114")
FG_ON_INK = colors.HexColor("#f2f0eb")
FG_2_ON_INK = colors.HexColor("#a3a19b")
TEXT = colors.HexColor("#1b1b1f")
MUTED = colors.HexColor("#6b6963")
FAINT = colors.HexColor("#9a978f")
RULE = colors.HexColor("#e4e1da")
TILE = colors.HexColor("#f4f2ed")
ACCENT = colors.HexColor("#ff7a3d")
ACCENT_DEEP = colors.HexColor("#c2410c")
CAUTION = colors.HexColor("#c9a227")
CANDLE_UP = colors.HexColor("#2f7d5b")
CANDLE_DOWN = colors.HexColor("#e2552b")
LEVEL_COLOR = {"caution": CAUTION, "warning": ACCENT, "critical": ACCENT_DEEP}
LEVEL_RANK = {"safe": 0, "caution": 1, "warning": 2, "critical": 3}

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
BAND_H = 64 * mm

TABLE_CELL = ParagraphStyle(name="TableCell", fontName="Helvetica", fontSize=8, leading=10.5, textColor=TEXT)
STYLES = {
    "verdict": ParagraphStyle(name="Verdict", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=TEXT, spaceAfter=4),
    "lede": ParagraphStyle(name="Lede", fontName="Helvetica", fontSize=9.5, leading=14, textColor=MUTED, spaceAfter=10),
    "kicker": ParagraphStyle(name="Kicker", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=ACCENT_DEEP, spaceBefore=16, spaceAfter=2, keepWithNext=True),
    "section": ParagraphStyle(name="Section", fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=TEXT, spaceAfter=3, keepWithNext=True),
    "intro": ParagraphStyle(name="Intro", fontName="Helvetica", fontSize=8.5, leading=12.5, textColor=MUTED, spaceAfter=8),
    "body": ParagraphStyle(name="Body", fontName="Helvetica", fontSize=9, leading=13.5, textColor=TEXT, spaceAfter=5),
    "bullet": ParagraphStyle(name="Bullet", fontName="Helvetica", fontSize=9, leading=13.5, textColor=TEXT, leftIndent=11, bulletIndent=0, spaceAfter=5),
    "small": ParagraphStyle(name="Small", fontName="Helvetica", fontSize=7.5, leading=10.5, textColor=MUTED),
    "tile_label": ParagraphStyle(name="TileLabel", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=MUTED),
    "tile_value": ParagraphStyle(name="TileValue", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=TEXT),
    "tile_note": ParagraphStyle(name="TileNote", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=MUTED),
}

AGENT_NAMES = {  # keyed by the agent type with separators removed
    "marketmaker": "Market makers", "hft": "High-frequency traders", "institutional": "Institutions",
    "retail": "Retail traders", "informed": "Informed traders", "noise": "Noise traders",
    "liquiditytrader": "Liquidity traders", "momentum": "Momentum traders",
    "meanreversion": "Mean-reversion traders", "sentiment": "Sentiment traders", "spoofing": "Spoofers",
}
METRIC_INFO = {
    "spread_mean": ("Average spread", "{:.4f}", "Average gap between best buy and best sell price, in dollars."),
    "spread_max": ("Widest spread", "{:.4f}", "The largest gap seen at any second, in dollars."),
    "trade_rate_per_second_mean": ("Trades per second", "{:.2f}", "How often buyers and sellers were matched."),
    "cancel_to_trade_ratio": ("Cancels per trade", "{:.1f}", "Orders withdrawn for every trade. High values are normal for bots that keep re-quoting."),
    "depth_imbalance_mean": ("Average imbalance", "{:+.3f}", "Average tilt of the book: positive leaned to buyers, negative to sellers."),
    "signed_volume_abs_mean": ("Average net flow", "{:,.0f}", "Typical size of one-way aggressive trading over 10 s windows, in shares."),
    "volatility_mean": ("Average volatility", "{:.1%}", "How much the price moved, annualized like a quoted stock volatility."),
    "impact_bps_mean": ("Price move per second", "{:.2f} bps", "Average absolute price change between seconds, in basis points (0.01%)."),
    "slippage_bps_mean": ("Average slippage", "{:.2f} bps", "How far fills landed from the price when the order was sent."),
}
GLOSSARY = [
    ("Bid / ask", "The best price someone will pay (bid) and the best price someone will sell at (ask)."),
    ("Spread", "Ask minus bid: the cost of trading immediately. Basis points (bps) express it as a share of price; 1 bp = 0.01%."),
    ("Depth", "Shares waiting in the order book across the 10 best price levels on each side. More depth means big orders move the price less."),
    ("Liquidity shock", "A moment when the spread reaches 2.5 times normal or depth falls to 40% of normal."),
    ("Stress score", "The model's probability, 0 to 1, that a liquidity shock starts within the next 60 seconds."),
    ("Warning levels", "safe below 0.20, caution 0.20 to 0.40, warning 0.40 to 0.60, critical above 0.60."),
    ("Large level", "A single visible price level far bigger than the rest of the book, flagged by the large-order detector."),
    ("Imbalance", "Buy depth minus sell depth over the total: -1 is all sellers, +1 all buyers."),
    ("Aggressor", "The side that crossed the spread to trade immediately. It pays the spread; the resting side earns it."),
    ("P&L", "Profit and loss in dollars after fees. Realized is locked in; unrealized marks open positions at the final price."),
    ("Fundamental value", "The hidden fair price the simulation is built around. Informed bots see it early; others 30 seconds late."),
]


# ── Formatting ─────────────────────────────────────────────────────────────


def _number(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return f"{number:.{digits}f}" if isfinite(number) else "N/A"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if isfinite(number) else default


def _label(value: Any) -> str:
    return str(value).replace("_", " ").title()


def _clock(seconds: Any) -> str:
    """Session clock: the simulated session opens at 09:30:00."""
    total = 9 * 3600 + 30 * 60 + int(_float(seconds))
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _duration(seconds: Any) -> str:
    total = int(_float(seconds))
    if total >= 3600:
        return f"{total // 3600} h {total % 3600 // 60:02d} min"
    return f"{total // 60} min {total % 60:02d} s" if total >= 60 else f"{total} s"


def _money(value: float) -> str:
    return f"{'-' if value < 0 else '+'}${abs(value):,.0f}"


def _wrap_table_cell(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 40:
        return Paragraph(escape(value), TABLE_CELL)
    return value


# ── Tables ─────────────────────────────────────────────────────────────────


def _table(rows: list[list[Any]], widths: list[float], header: bool = True, numeric_from: int | None = None) -> Table:
    """Quiet ruled table: muted header, hairlines, right-aligned numeric columns."""
    table = Table([[_wrap_table_cell(v) for v in row] for row in rows], colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands: list[tuple] = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
    ]
    if header:
        commands += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, TEXT),
        ]
    if numeric_from is not None:
        commands.append(("ALIGN", (numeric_from, 0), (-1, -1), "RIGHT"))
    table.setStyle(TableStyle(commands))
    return table


def _tiles(items: list[tuple[str, str, str, bool]], columns: int = 3) -> Table:
    """KPI tiles: label, big value, note. The last flag tints the value orange."""
    width = CONTENT_W / columns
    cells = []
    for label, value, note, alert in items:
        value_style = ParagraphStyle(name="v", parent=STYLES["tile_value"], textColor=ACCENT_DEEP if alert else TEXT)
        cells.append([Paragraph(escape(label), STYLES["tile_label"]), Paragraph(escape(value), value_style), Paragraph(escape(note), STYLES["tile_note"])])
    rows = [cells[i:i + columns] for i in range(0, len(cells), columns)]
    rows[-1] += [""] * (columns - len(rows[-1]))
    table = Table(rows, colWidths=[width] * columns, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TILE),
        ("INNERGRID", (0, 0), (-1, -1), 5, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return table


def _pnl_bar(value: float, peak: float) -> Drawing:
    """Diverging bar: gains right of centre in ink, losses left in orange."""
    width, height = 44 * mm, 3.4 * mm
    drawing = Drawing(width, height)
    centre = width / 2
    drawing.add(Rect(0, height / 2 - 0.3, width, 0.6, fillColor=RULE, strokeColor=None))
    drawing.add(Line(centre, 0, centre, height, strokeColor=FAINT, strokeWidth=0.5))
    length = (abs(value) / peak) * (width / 2 - 1) if peak else 0
    if length > 0:
        x = centre if value >= 0 else centre - length
        drawing.add(Rect(x, 0.4, length, height - 0.8, fillColor=TEXT if value >= 0 else ACCENT, strokeColor=None))
    return drawing


# ── Charts ─────────────────────────────────────────────────────────────────


def _axis_label(drawing: Drawing, x: float, y: float, text: str, anchor: str = "start") -> None:
    drawing.add(String(x, y, text, fontName="Helvetica", fontSize=6.5, fillColor=MUTED, textAnchor=anchor))


def _time_axis(drawing: Drawing, x0: float, width: float, y: float, t0: float, t1: float) -> None:
    for i in range(5):
        frac = i / 4
        _axis_label(drawing, x0 + width * frac, y, _clock(t0 + (t1 - t0) * frac), "start" if i == 0 else "end" if i == 4 else "middle")


def _price_chart(path: list[dict[str, Any]], warnings: list[dict[str, Any]] | None = None) -> Drawing:
    """5-second OHLC candles, the opening price as a dashed reference, and warning markers."""
    drawing = Drawing(CONTENT_W, 74 * mm)
    points = [
        (float(item.get("timestamp", 0)), float(item.get("price", 0)))
        for item in path
        if isinstance(item.get("price"), (int, float))
    ]
    if len(points) < 2:
        drawing.add(String(0, 35 * mm, "No price path recorded", fontName="Helvetica", fontSize=9, fillColor=MUTED))
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
    if len(candles) > 90:  # merge neighbours so each candle stays readable
        size = (len(candles) + 89) // 90
        merged = []
        for i in range(0, len(candles), size):
            group = candles[i:i + size]
            merged.append({"time": group[0]["time"], "open": group[0]["open"], "close": group[-1]["close"],
                           "high": max(c["high"] for c in group), "low": min(c["low"] for c in group)})
        candles = merged

    x0, y0 = 14 * mm, 8 * mm
    width, height = CONTENT_W - x0, 56 * mm
    low = min(c["low"] for c in candles)
    high = max(c["high"] for c in candles)
    pad = max((high - low) * 0.1, 0.01)
    low, high = low - pad, high + pad
    y = lambda value: y0 + (value - low) / (high - low) * height
    step = width / max(len(candles), 20)

    for i in range(5):
        level = low + (high - low) * i / 4
        gy = y(level)
        drawing.add(Line(x0, gy, x0 + width, gy, strokeColor=RULE, strokeWidth=0.4))
        _axis_label(drawing, x0 - 2, gy - 2, f"{level:.2f}", "end")
    opening = points[0][1]
    drawing.add(Line(x0, y(opening), x0 + width, y(opening), strokeColor=FAINT, strokeWidth=0.6, strokeDashArray=[2, 2]))
    _axis_label(drawing, x0 + width, y(opening) + 2, f"open {opening:.2f}", "end")

    for index, candle in enumerate(candles):
        x = x0 + step * (index + 0.5)
        color = CANDLE_UP if candle["close"] >= candle["open"] else CANDLE_DOWN
        bottom, top = y(min(candle["open"], candle["close"])), y(max(candle["open"], candle["close"]))
        body = max(0.8 * mm, min(2.6 * mm, step * 0.64))
        drawing.add(Line(x, y(candle["low"]), x, y(candle["high"]), strokeColor=color, strokeWidth=0.6))
        drawing.add(Rect(x - body / 2, bottom, body, max(0.6, top - bottom), fillColor=color, strokeColor=color, strokeWidth=0))

    t0, t1 = points[0][0], points[-1][0]
    for warning in warnings or []:
        level = warning.get("warning_level")
        if warning.get("detector") != "liquidity_stress" or level not in LEVEL_COLOR or t1 <= t0:
            continue
        wx = x0 + (float(warning.get("timestamp", t0)) - t0) / (t1 - t0) * width
        top = y0 + height + 2.2 * mm
        drawing.add(Polygon([wx - 1.4 * mm, top + 2.2 * mm, wx + 1.4 * mm, top + 2.2 * mm, wx, top], fillColor=LEVEL_COLOR[level], strokeColor=None))
    _time_axis(drawing, x0, width, 2 * mm, t0, t1)
    return drawing


def _series_chart(path: list[dict[str, Any]], value: Callable[[dict[str, Any]], float], *, title: str, unit: str, color: Any, fill: bool,
                  keep: Callable[[list[float]], float] = max, height_mm: float = 34) -> Drawing:
    """A line (or filled area) over session time with its median dashed and labelled."""
    drawing = Drawing(CONTENT_W, height_mm * mm)
    series = [(float(p.get("timestamp", 0)), value(p)) for p in path]
    series = [(t, v) for t, v in series if isfinite(v)]
    drawing.add(String(0, (height_mm - 3.5) * mm, title, fontName="Helvetica-Bold", fontSize=7.5, fillColor=TEXT))
    if len(series) < 2:
        _axis_label(drawing, 0, (height_mm - 12) * mm, "Not enough data recorded")
        return drawing
    if len(series) > 600:  # thin for print, keeping each bucket's extreme so spikes survive
        size = (len(series) + 599) // 600
        series = [(series[i][0], keep([v for _, v in series[i:i + size]])) for i in range(0, len(series), size)]
    x0, y0 = 14 * mm, 7 * mm
    width, height = CONTENT_W - x0, (height_mm - 13) * mm
    values = [v for _, v in series]
    low, high = (0.0 if fill else min(values)), max(values)
    high = high if high > low else low + 1
    t0, t1 = series[0][0], series[-1][0]
    sx = lambda t: x0 + (t - t0) / ((t1 - t0) or 1) * width
    sy = lambda v: y0 + (v - low) / (high - low) * height
    for i in range(3):
        level = low + (high - low) * i / 2
        drawing.add(Line(x0, sy(level), x0 + width, sy(level), strokeColor=RULE, strokeWidth=0.4))
        _axis_label(drawing, x0 - 2, sy(level) - 2, f"{level:,.0f}" if high >= 100 else f"{level:.1f}", "end")
    coords = [c for t, v in series for c in (sx(t), sy(v))]
    if fill:
        drawing.add(Polygon([x0, y0, *coords, x0 + width, y0], fillColor=colors.Color(color.red, color.green, color.blue, alpha=0.18), strokeColor=None))
    drawing.add(PolyLine(coords, strokeColor=color, strokeWidth=0.8))
    mid = median(values)
    drawing.add(Line(x0, sy(mid), x0 + width, sy(mid), strokeColor=TEXT, strokeWidth=0.5, strokeDashArray=[2, 2]))
    tag = f"median {mid:,.1f} {unit}"
    drawing.add(Rect(x0 + width - len(tag) * 3.3 - 4, sy(mid) + 1, len(tag) * 3.3 + 4, 9, fillColor=colors.white, strokeColor=None))
    _axis_label(drawing, x0 + width - 2, sy(mid) + 3.5, tag, "end")
    _time_axis(drawing, x0, width, 1.5 * mm, t0, t1)
    return drawing


# ── Page furniture ─────────────────────────────────────────────────────────


def _make_canvas(subtitle: str) -> type:
    """Canvas that defers footers until the end, so every page can say "page x of y"."""

    class NumberedCanvas(Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._saved: list[dict] = []

        def showPage(self) -> None:  # noqa: N802 (reportlab API)
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            for state in self._saved:
                self.__dict__.update(state)
                self.setStrokeColor(RULE)
                self.setLineWidth(0.4)
                self.line(MARGIN, 12 * mm, PAGE_W - MARGIN, 12 * mm)
                self.setFillColor(MUTED)
                self.setFont("Helvetica", 7)
                self.drawString(MARGIN, 8 * mm, f"Sentinel  ·  Session report  ·  {subtitle}")
                self.drawRightString(PAGE_W - MARGIN, 8 * mm, f"Page {self._pageNumber} of {len(self._saved)}")
                super().showPage()
            super().save()

    return NumberedCanvas


def _first_page(title_line: str, meta_line: str, generated: str) -> Callable[[Any, Any], None]:
    def draw(canvas: Any, document: Any) -> None:
        canvas.saveState()
        top = PAGE_H
        canvas.setFillColor(INK)
        canvas.rect(0, top - BAND_H, PAGE_W, BAND_H, stroke=0, fill=1)
        canvas.setFillColor(FG_ON_INK)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(MARGIN, top - 15 * mm, "sentinel")
        canvas.setFillColor(FG_2_ON_INK)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(PAGE_W - MARGIN, top - 15 * mm, f"Generated {generated}")
        canvas.setFillColor(FG_ON_INK)
        canvas.setFont("Helvetica-Bold", 30)
        canvas.drawString(MARGIN, top - 35 * mm, "Session report")
        canvas.setFont("Helvetica", 11)
        canvas.drawString(MARGIN, top - 44 * mm, title_line)
        canvas.setFillColor(FG_2_ON_INK)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(MARGIN, top - 51 * mm, meta_line)
        canvas.setFillColor(ACCENT)
        canvas.rect(MARGIN, top - BAND_H + 7 * mm, 28 * mm, 1.6 * mm, stroke=0, fill=1)
        canvas.restoreState()

    return draw


def _later_page(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFillColor(TEXT)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(MARGIN, PAGE_H - 11 * mm, "sentinel")
    canvas.setFillColor(ACCENT)
    canvas.rect(MARGIN, PAGE_H - 13.5 * mm, 9 * mm, 0.9 * mm, stroke=0, fill=1)
    canvas.restoreState()


def _section(kicker: str, title: str, intro: str | None = None) -> list[Any]:
    parts: list[Any] = [CondPageBreak(60 * mm), Paragraph(kicker.upper(), STYLES["kicker"]), Paragraph(escape(title), STYLES["section"])]
    if intro:
        parts.append(Paragraph(intro, STYLES["intro"]))
    return parts


# ── Report ─────────────────────────────────────────────────────────────────


def build_simulation_pdf(report: dict[str, Any]) -> bytes:
    config = report.get("run_config", {})
    path = report.get("price_path", []) or []
    flow = report.get("order_flow", {})
    summary = flow.get("summary", {})
    metrics = report.get("validation_metrics", {})
    agent_metrics = report.get("agent_metrics", {})
    warnings = report.get("warning_timeline", []) or []
    events = report.get("events", []) or []
    orders = report.get("recent_orders", []) or []
    trades = flow.get("trades", []) or []

    scenario = _label(config.get("scenario", "unknown"))
    preset = _label(config.get("preset", "unknown"))
    seed = config.get("seed")
    elapsed = config.get("elapsed_seconds", 0)

    # Headline numbers.
    first = _float(path[0].get("price"), _float(config.get("initial_price"), 0)) if path else _float(config.get("initial_price"), 0)
    last = _float(path[-1].get("price"), first) if path else first
    change = (last - first) / first * 100 if first else 0.0
    spread_bps = [_float(p.get("spread")) / _float(p.get("price"), 1) * 1e4 for p in path if _float(p.get("price"))]
    depths = [_float(p.get("depth")) for p in path]
    median_depth = median(depths) if depths else 0
    thinnest = min(depths) / median_depth if depths and median_depth else 1.0
    median_spread = median(spread_bps) if spread_bps else 0
    widest = max(spread_bps, default=0)
    stress_warnings = [w for w in warnings if w.get("detector") == "liquidity_stress"]
    large_flags = [w for w in warnings if w.get("detector") == "visible_liquidity"]
    peak_level = max((w.get("warning_level", "safe") for w in stress_warnings), key=lambda lv: LEVEL_RANK.get(lv, 0), default="safe")
    match_rate = _float(summary.get("match_rate"))

    if LEVEL_RANK.get(peak_level, 0) >= 2:
        verdict = f"Liquidity came under real strain: the detector reached {peak_level}."
    elif peak_level == "caution":
        verdict = "Mostly orderly, with brief moments of caution."
    else:
        verdict = "A calm session: liquidity held up throughout."
    lede = (
        f"The price moved {change:+.2f}% over {_duration(elapsed)} of simulated trading. "
        f"The spread was usually {median_spread:.1f} bps and peaked at {widest:.1f} bps; "
        f"at its thinnest the book held {thinnest:.0%} of its usual depth. "
        f"{len(trades):,} trades went through and the stress detector raised {len(stress_warnings):,} warning{'s' if len(stress_warnings) != 1 else ''}."
    )

    title_line = f"{scenario} scenario  ·  {preset} preset"
    meta_line = "  ·  ".join([
        f"Seed {seed if seed is not None else 'random'}",
        f"{_duration(elapsed)} simulated",
        f"{config.get('agent_count', 'N/A')} bots",
        f"latency {_label(config.get('latency_mode', 'n/a')).lower()}",
        f"informed access {'on' if config.get('informed_access') else 'off'}",
    ])

    buffer = BytesIO()
    document = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=20 * mm, bottomMargin=18 * mm,
        title=f"Sentinel session report: {scenario}", author="Sentinel", subject="Simulation session report",
    )
    document.addPageTemplates([
        PageTemplate(id="first", frames=[Frame(MARGIN, 18 * mm, CONTENT_W, PAGE_H - BAND_H - 8 * mm - 18 * mm, id="f1", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
                     onPage=_first_page(title_line, meta_line, str(report.get("generated_at", "")).replace("T", " "))),
        PageTemplate(id="later", frames=[Frame(MARGIN, 18 * mm, CONTENT_W, PAGE_H - 20 * mm - 18 * mm, id="f2", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
                     onPage=_later_page),
    ])

    story: list[Any] = [
        NextPageTemplate("later"),
        Paragraph(escape(verdict), STYLES["verdict"]),
        Paragraph(escape(lede), STYLES["lede"]),
        _tiles([
            ("Price change", f"{change:+.2f}%", f"{first:.2f} to {last:.2f}", change < -1),
            ("Widest spread", f"{widest:.1f} bps", f"usually {median_spread:.1f} bps", median_spread > 0 and widest > 2.5 * median_spread),
            ("Thinnest book", f"{thinnest:.0%}", "of usual depth", thinnest < 0.4),
            ("Trades", f"{len(trades):,}", f"{match_rate:.0f}% of orders matched", False),
            ("Highest warning", peak_level.capitalize(), f"{len(stress_warnings)} stress · {len(large_flags)} large-order flags", LEVEL_RANK.get(peak_level, 0) >= 2),
            ("Session length", _duration(elapsed), f"{int(_float(config.get('steps'))):,} one-second steps", False),
        ]),
    ]

    # Price.
    story += _section("1  ·  Price", "How the price moved",
                      "Each candle covers a few seconds of trading: green when the price ended higher than it started, orange when lower. "
                      "The dashed line is the opening price. Triangles along the top mark when the stress detector raised a warning "
                      "(<font color='#c9a227'>caution</font>, <font color='#ff7a3d'>warning</font>, <font color='#c2410c'>critical</font>).")
    story.append(_price_chart(path, warnings))

    # Liquidity.
    story += _section("2  ·  Liquidity", "How easy it was to trade",
                      "The spread is the cost of trading immediately; lower is better. Depth is how many shares were waiting to trade; higher is better. "
                      "A liquidity shock shows up as the spread jumping while the depth drops.")
    story.append(_series_chart(path, lambda p: _float(p.get("spread")) / max(_float(p.get("price"), 1), 1e-9) * 1e4,
                               title="Spread, basis points", unit="bps", color=ACCENT, fill=False))
    story.append(Spacer(1, 3 * mm))
    story.append(_series_chart(path, lambda p: _float(p.get("depth")), title="Visible depth, shares (10 levels a side)",
                               unit="shares", color=TEXT, fill=True, keep=min))

    # Findings.
    buy, sell = _float(summary.get("buy_volume")), _float(summary.get("sell_volume"))
    aggressor = buy + sell
    findings = [
        ("Price.", f"Opened at {first:.2f} and finished at {last:.2f} ({change:+.2f}%)."),
        ("Cost of trading.", f"The spread was usually {median_spread:.1f} bps and never wider than {widest:.1f} bps."),
        ("Liquidity.", f"Typically {median_depth:,.0f} shares were waiting; the lowest point was {thinnest:.0%} of that."),
        ("Activity.", f"{int(_float(flow.get('submitted_orders'))):,} orders were sent, {len(trades):,} trades matched and "
                      f"{int(_float(flow.get('accepted_cancels'))):,} orders were cancelled."),
    ]
    if aggressor:
        side = "buyers" if buy >= sell else "sellers"
        findings.append(("Who pushed.", f"Aggressive {side} did {max(buy, sell) / aggressor:.0%} of the trading that crossed the spread."))
    findings.append(("Warnings.", f"The stress detector raised {len(stress_warnings):,} warning{'s' if len(stress_warnings) != 1 else ''} (highest: {peak_level}) "
                                  f"and the large-order detector flagged {len(large_flags):,} outsized level{'s' if len(large_flags) != 1 else ''}."))
    story += _section("3  ·  Summary", "What happened, in plain words")
    story += [Paragraph(f"<b>{escape(lead)}</b> {escape(text)}", STYLES["bullet"], bulletText="•") for lead, text in findings]

    # Participants.
    grouped: dict[str, dict[str, float]] = {}
    for agent in agent_metrics.values():
        row = grouped.setdefault(str(agent.get("agent_type", "unknown")), {"count": 0, "trades": 0, "position": 0, "pnl": 0})
        row["count"] += 1
        row["trades"] += _float(agent.get("num_trades"))
        row["position"] += _float(agent.get("position"))
        row["pnl"] += _float(agent.get("total_pnl"))
    ranked = sorted(grouped.items(), key=lambda item: -item[1]["pnl"])
    peak = max((abs(r["pnl"]) for _, r in ranked), default=0)
    agent_rows: list[list[Any]] = [["Bot type", "Bots", "Trades", "Net position", "Total P&L", ""]]
    for name, row in ranked:
        agent_rows.append([AGENT_NAMES.get(name.lower().replace("_", ""), _label(name)), int(row["count"]), f"{int(row['trades']):,}",
                           f"{row['position']:+,.0f}", _money(row["pnl"]), _pnl_bar(row["pnl"], peak)])
    if len(agent_rows) == 1:
        agent_rows.append(["No bots recorded", "", "", "", "", ""])
    participants = _table(agent_rows, [48 * mm, 14 * mm, 20 * mm, 24 * mm, 24 * mm, 48 * mm], numeric_from=1)
    participants.setStyle(TableStyle([("ALIGN", (5, 0), (5, -1), "LEFT"), ("LEFTPADDING", (5, 0), (5, -1), 6)]))
    for index, (_, row) in enumerate(ranked, start=1):
        if row["pnl"] < 0:
            participants.setStyle(TableStyle([("TEXTCOLOR", (4, index), (4, index), ACCENT_DEEP)]))
    story += _section("4  ·  Participants", "Who made and lost money",
                      "Every bot follows fixed rules. Profit and loss is in dollars after fees, with open positions valued at the final price. "
                      "Market makers and fast traders earn the spread; traders who must trade immediately usually pay it.")
    story.append(participants)

    # Warnings.
    story += _section("5  ·  Detectors", "Warnings raised",
                      "A row appears each time the stress detector moved to a new level, not for every second it stayed there. "
                      "Health is one minus the stress score. Times use the simulated session clock, which opens at 09:30.")
    if stress_warnings:
        shown = stress_warnings[:40]
        warning_table = _table(
            [["Time", "Level", "Stress score", "Health"]] + [
                [_clock(w.get("timestamp")), _label(w.get("warning_level", "")), _number(w.get("stress_score"), 2), _number(_float(w.get("health_score")) / 100, 2)]
                for w in shown
            ],
            [30 * mm, 40 * mm, 40 * mm, 40 * mm], numeric_from=2,
        )
        for index, item in enumerate(shown, start=1):
            level = item.get("warning_level")
            if level in LEVEL_COLOR:
                warning_table.setStyle(TableStyle([("TEXTCOLOR", (1, index), (1, index), LEVEL_COLOR[level]), ("FONTNAME", (1, index), (1, index), "Helvetica-Bold")]))
        story.append(warning_table)
        if len(stress_warnings) > len(shown):
            story.append(Paragraph(f"Showing the first {len(shown)} of {len(stress_warnings):,} stress transitions; the JSON download has all of them.", STYLES["small"]))
    else:
        story.append(Paragraph("The liquidity-stress detector stayed at safe for the whole run.", STYLES["body"]))
    if large_flags:
        buys = sum(1 for w in large_flags if str(w.get("side", "")).lower() == "buy")
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(
            f"<b>Large orders.</b> The detector flagged {len(large_flags):,} outsized price levels: {buys:,} on the buy side and "
            f"{len(large_flags) - buys:,} on the sell side. The five largest:", STYLES["body"]))
        biggest = sorted(large_flags, key=lambda w: -_float(w.get("estimated_size")))[:5]
        story.append(_table(
            [["Time", "Side", "Shares", "Confidence"]] + [
                [_clock(w.get("timestamp")), str(w.get("side", "")).upper(), f"{int(_float(w.get('estimated_size'))):,}", _number(w.get("confidence"), 2)]
                for w in biggest
            ],
            [30 * mm, 40 * mm, 40 * mm, 40 * mm], numeric_from=2,
        ))

    # Market quality.
    quality_rows: list[list[Any]] = [["Measure", "Value", "What it means"]]
    for key, value in metrics.items():
        name, fmt, meaning = METRIC_INFO.get(key, (_label(key), "{:.4f}", ""))
        try:
            shown = fmt.format(float(value))
        except (TypeError, ValueError):
            shown = "N/A"
        quality_rows.append([name, shown, Paragraph(escape(meaning), TABLE_CELL) if meaning else ""])
    story += _section("6  ·  Market quality", "Measurements from the recorded run",
                      "Calculated from every recorded second and every order. Useful for comparing runs with different scenarios or seeds.")
    story.append(_table(quality_rows, [42 * mm, 26 * mm, 110 * mm]))

    # Execution and coverage, side by side.
    half = (CONTENT_W - 8 * mm) / 2
    execution = _table([
        ["Order flow", "Count"],
        ["Orders sent", f"{int(_float(flow.get('submitted_orders'))):,}"],
        ["Trades matched", f"{len(trades):,}"],
        ["Cancel requests", f"{int(_float(flow.get('cancel_requests'))):,}"],
        ["Cancels accepted", f"{int(_float(flow.get('accepted_cancels'))):,}"],
        ["Orders expired", f"{int(_float(flow.get('terminal_cancels'))):,}"],
        ["Aggressive buy volume", f"{int(buy):,}"],
        ["Aggressive sell volume", f"{int(sell):,}"],
        ["Value of orders sent", f"${_float(summary.get('submitted_notional')):,.0f}"],
    ], [half * 0.66, half * 0.34], numeric_from=1)
    event_counts: dict[str, int] = {}
    for event in events:
        event_counts[str(event.get("type", "unknown"))] = event_counts.get(str(event.get("type", "unknown")), 0) + 1
    coverage = _table([
        ["Recorded evidence", "Count"],
        ["Seconds recorded", f"{len(path):,}"],
        ["Trades", f"{len(trades):,}"],
        ["Bots", f"{len(agent_metrics):,}"],
        ["Detector transitions", f"{len(warnings):,}"],
        ["Exchange events kept", f"{len(events):,}"],
        ["Recent orders kept", f"{len(orders):,}"],
        *[[f"  {_label(name)} events", f"{count:,}"] for name, count in sorted(event_counts.items(), key=lambda kv: -kv[1])[:4]],
    ], [half * 0.66, half * 0.34], numeric_from=1)
    pair = Table([[execution, coverage]], colWidths=[half + 8 * mm, half], hAlign="LEFT")
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 8 * mm), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    story += _section("7  ·  Record", "Execution and data coverage",
                      "How much evidence stands behind this report. Short runs give rough estimates; repeat with other seeds before drawing conclusions.")
    story.append(pair)

    # Glossary and method.
    story += _section("8  ·  Reference", "Glossary")
    story.append(_table([["Term", "Meaning"], *[[term, Paragraph(escape(meaning), TABLE_CELL)] for term, meaning in GLOSSARY]], [34 * mm, 144 * mm]))
    story.append(KeepTogether([
        Paragraph("METHOD AND LIMITS", STYLES["kicker"]),
        Paragraph(
            "This is one synthetic run under the seed, scenario, bot population and latency settings listed on the first page. "
            "Prices, liquidity, fills and profits come from Sentinel's simulator, not from a real exchange, so the report is not evidence of "
            "real-market profitability or a forecast of future prices. The same seed reproduces the run exactly. "
            "The JSON download holds the full raw record of states, orders, trades and events for your own analysis.",
            STYLES["body"]),
    ]))

    document.build(story, canvasmaker=_make_canvas(f"{scenario} · seed {seed if seed is not None else 'random'}"))
    return buffer.getvalue()
