"""Print-friendly, one-page landscape A4 team commentary sheets."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

SKATER_COLUMNS = [("Jersey", "#"), ("Player", "Player"), ("GP", "GP"), ("G", "G"), ("A", "A"), ("PTS", "Pts"), ("+/-", "+/-"), ("PPG", "PPG"), ("SHG", "SHG"), ("S%", "S%"), ("FO%", "FO%"), ("TOI/Game", "TOI/G")]
GOALIE_COLUMNS = [("Jersey", "#"), ("Player", "Player Name"), ("W", "W"), ("L", "L"), ("SO", "SO"), ("MIN", "MIN"), ("SA", "SA"), ("GA", "GA"), ("GAA", "GAA"), ("SV%", "SV%"), ("GSAA", "GSAA"), ("GSAA/60", "GSAA/60")]


def display(value, column):
    if pd.isna(value):
        return "-"
    if column in ("Player", "TOI/Game"):
        return str(value)
    try:
        value = float(value)
    except (ValueError, TypeError):
        return str(value)
    if column in ("S%", "FO%", "GAA", "SV%"):
        return f"{value:.2f}"
    if column in ("GSAA", "GSAA/60"):
        return f"{value:+.2f}"
    if column == "MIN":
        return f"{value:.1f}"
    if column == "+/-":
        return f"{value:+.0f}" if value else "0"
    return f"{value:.0f}"


def team_rows(frame, team):
    if frame.empty or "Team" not in frame:
        return frame.iloc[:0].copy()
    frame = frame[frame.Team == team].copy()
    if "Jersey" in frame:
        frame = frame.assign(_shirt=pd.to_numeric(frame.Jersey, errors="coerce")).sort_values(["_shirt", "Player"], na_position="last").drop(columns="_shirt")
    return frame


def make_table(frame, columns, width, font_size):
    # A wide name column; every requested statistic retains its own column.
    weights = [27, 176] + [43] * 10
    widths = [width * w / sum(weights) for w in weights]
    styles = {"body": ParagraphStyle("body", fontName="Desk", fontSize=font_size, leading=font_size + 1.5, alignment=TA_CENTER),
              "name": ParagraphStyle("name", fontName="Desk", fontSize=font_size, leading=font_size + 1.5, alignment=TA_LEFT),
              "head": ParagraphStyle("head", fontName="DeskBold", fontSize=font_size, leading=font_size + 1.5, textColor=colors.white, alignment=TA_CENTER)}
    cells = [[Paragraph(escape(label), styles["head"]) for _, label in columns]]
    for _, row in frame.iterrows():
        cells.append([Paragraph(escape(display(row.get(key, float("nan")), key)), styles["name" if key == "Player" else "body"]) for key, _ in columns])
    if frame.empty:
        cells.append([Paragraph("No published player data", styles["name"])] + [""] * (len(columns) - 1))
    table = Table(cells, colWidths=widths)
    padding = 2 if font_size >= 9 else 1
    commands = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18334E")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F3F6")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), padding), ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
                ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.HexColor("#BCC8D3"))]
    if frame.empty:
        commands.append(("SPAN", (0, 1), (-1, 1)))
    table.setStyle(TableStyle(commands))
    return table


def build_team_pdf(bundle, team, match_label=""):
    """Return PDF bytes; full team roster, independent of on-screen search filters."""
    font_root = Path(reportlab.__file__).parent / "fonts"
    if "Desk" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Desk", str(font_root / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("DeskBold", str(font_root / "VeraBd.ttf")))
    skaters = team_rows(bundle["skaters"], team)
    goalies = team_rows(bundle["goalies"], team)
    page_width, page_height = landscape(A4)
    margin = 25
    width = page_width - margin * 2
    available = page_height - 143
    for font_size in (9, 8.5, 8, 7.5, 7, 6.5):
        sk_table = make_table(skaters, SKATER_COLUMNS, width, font_size)
        gl_table = make_table(goalies, GOALIE_COLUMNS, width, font_size)
        _, sk_height = sk_table.wrap(width, available)
        _, gl_height = gl_table.wrap(width, available)
        if sk_height + gl_height <= available:
            break
    else:
        raise ValueError("This roster is too large for a legible one-page A4 sheet. Select a narrower competition/stage.")
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    pdf.setTitle(f"{team} - Commentary Desk")
    pdf.setAuthor("Commentary Desk")
    pdf.setFillColor(colors.HexColor("#18334E"))
    pdf.setFont("DeskBold", 19)
    pdf.drawString(margin, page_height - 35, team)
    pdf.setFont("Desk", 9)
    pdf.drawRightString(page_width - margin, page_height - 32, "COMMENTARY DESK")
    context = " | ".join(str(v) for v in [bundle.get("season_label", f"Season {bundle.get('season', '')}"), bundle.get("stage_label", ""), match_label] if v)
    # Wrap rather than clip unusually long competition or match labels.
    header = Paragraph(escape(context), ParagraphStyle("context", fontName="Desk", fontSize=8, leading=10))
    _, header_height = header.wrap(width, 24)
    if header_height > 24:
        raise ValueError("The match label is too long for a one-page sheet; shorten it before exporting.")
    header.drawOn(pdf, margin, page_height - 43 - header_height)
    top = page_height - 83
    pdf.setFont("DeskBold", 10)
    pdf.drawString(margin, top + 7, f"SKATERS ({len(skaters)})")
    sk_table.drawOn(pdf, margin, top - sk_height)
    goalie_top = top - sk_height - 25
    pdf.setFont("DeskBold", 10)
    pdf.drawString(margin, goalie_top + 7, f"GOALIES ({len(goalies)})")
    gl_table.drawOn(pdf, margin, goalie_top - gl_height)
    pdf.setFont("Desk", 6.5)
    pdf.setFillColor(colors.HexColor("#526172"))
    pdf.drawString(margin, 28, "Source: eliteleague.co.uk | Fetched: " + str(bundle.get("fetched_at", "Unknown")))
    pdf.drawString(margin, 17, "Percentages are on a 0-100 scale. MIN is minutes (decimal). GSAA uses the selected competition average. '-' = unavailable.")
    if bundle.get("errors"):
        pdf.setFillColor(colors.HexColor("#9E3F15"))
        pdf.drawRightString(page_width - margin, 28, "INCOMPLETE SOURCE DATA")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
