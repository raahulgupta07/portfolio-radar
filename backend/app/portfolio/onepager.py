"""PDF one-pagers (PRD FR-16): one project, or the whole portfolio for the
Steering Committee. Built from the same data the screens show (project_detail
and overview), in the design system's colours and font. One A4 page each;
long lists are cut with "and N more" so nothing runs onto a second page.
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

FONTS = Path(__file__).parent / "fonts"
C = {k: HexColor(v) for k, v in {
    "bg": "#E7F0EA", "surface": "#FFFFFF", "surface2": "#F1F5F2", "line": "#DDE5DF", "ink": "#111111",
    "ink2": "#2A302C", "muted": "#5B635D", "mint": "#7FD69A", "black2": "#161616",
    "jira": "#CFE3FB", "jira_bar": "#7FB2EC", "openproject": "#FBE6A9", "openproject_bar": "#EAC45A",
    "multica": "#F8CDD0", "multica_bar": "#EE9AA0",
    "on_track_bg": "#E2F2E7", "on_track": "#2E8B57", "at_risk_bg": "#FBE6A9", "at_risk": "#B98300",
    "off_track_bg": "#F8CDD0", "off_track": "#C23B3B", "done_bg": "#CFE3FB", "done": "#111111",
}.items()}
LABEL = {"on_track": "On track", "at_risk": "At risk", "off_track": "Off track", "done": "Done"}
_fonts_ready = False


def _fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    for name, file in (("PJS", "Regular"), ("PJS-Semi", "SemiBold"), ("PJS-Bold", "Bold"), ("PJS-XBold", "ExtraBold")):
        pdfmetrics.registerFont(TTFont(name, str(FONTS / f"PlusJakartaSans-{file}.ttf")))
    _fonts_ready = True


def _d(v: str | None, fmt: str = "%d %b %Y") -> str:
    return date.fromisoformat(v[:10]).strftime(fmt).lstrip("0") if v else "No date"


class Page:
    """A canvas with the few drawing helpers the one-pagers need. y grows downwards from the top margin."""

    def __init__(self, size: tuple[float, float], title: str, author: str) -> None:
        _fonts()
        self.buf = BytesIO()
        self.w, self.h = size
        self.c = Canvas(self.buf, pagesize=size, pageCompression=1)
        self.c.setTitle(title)
        self.c.setAuthor(author)
        self.c.setCreator("Portfolio Radar")
        self.m = 32  # margin

    def Y(self, y: float) -> float:
        return self.h - y

    def box(self, x: float, y: float, w: float, h: float, fill: Any, r: float = 14, stroke: Any = None) -> None:
        self.c.setFillColor(fill)
        if stroke is not None:
            self.c.setStrokeColor(stroke)
            self.c.setLineWidth(0.8)
        self.c.roundRect(x, self.Y(y + h), w, h, r, stroke=1 if stroke is not None else 0, fill=1)

    def text(self, x: float, y: float, s: str, size: float = 9, font: str = "PJS", color: Any = None,
             right: bool = False) -> None:
        self.c.setFont(font, size)
        self.c.setFillColor(color or C["ink"])
        (self.c.drawRightString if right else self.c.drawString)(x, self.Y(y + size * 0.8), s)

    def para(self, x: float, y: float, w: float, html: str, size: float = 9, font: str = "PJS", color: Any = None,
             leading: float | None = None, lines: int | None = None) -> float:
        """Wrapped text; returns its height. Cut to `lines` lines with an ellipsis if needed."""
        leading = leading or size * 1.35
        style = ParagraphStyle("p", fontName=font, fontSize=size, leading=leading, textColor=color or C["ink"])
        max_h = lines * leading + 0.5 if lines else None
        p = Paragraph(html, style)
        _, h = p.wrap(w, 10_000)
        if max_h is not None and h > max_h:
            words = html.split(" ")
            while words and h > max_h:
                words = words[:-max(1, len(words) // 8)]
                p = Paragraph(" ".join(words) + " …", style)
                _, h = p.wrap(w, 10_000)
        p.drawOn(self.c, x, self.Y(y + h))
        return h

    def pill(self, x: float, y: float, health: str | None, size: float = 9, right: bool = False) -> float:
        label = LABEL.get(health or "", "Unknown")
        tw = pdfmetrics.stringWidth(label, "PJS-Bold", size)
        w, h = tw + 20, size + 9
        if right:
            x -= w
        self.box(x, y, w, h, C.get(f"{health}_bg", C["surface2"]), r=h / 2)
        self.c.setFillColor(C.get(health or "", C["ink"]))
        self.c.circle(x + 9, self.Y(y + h / 2), 2.6, stroke=0, fill=1)
        self.text(x + 15, y + 4.5, label, size, "PJS-Bold", C["ink"] if health == "done" else C.get(health or ""))
        return w

    def bar(self, x: float, y: float, w: float, pct: int | None, color: Any, h: float = 7) -> None:
        self.box(x, y, w, h, C["surface2"], r=h / 2)
        if pct:
            self.box(x, y, max(h, w * min(100, pct) / 100), h, color, r=h / 2)

    def label(self, x: float, y: float, s: str) -> None:
        self.text(x, y, s.upper(), 7, "PJS-Bold", C["muted"])

    def footer(self, left: str) -> None:
        y = self.h - self.m - 6
        self.c.setStrokeColor(C["line"])
        self.c.setLineWidth(0.6)
        self.c.line(self.m, self.Y(y - 8), self.w - self.m, self.Y(y - 8))
        self.text(self.m, y, left, 7, "PJS", C["muted"])
        self.text(self.m, y + 10, "Portfolio Radar · a read-only copy: change project data in its source tool", 7,
                  "PJS", C["muted"])

    def pdf(self) -> bytes:
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()


def _more(items: list[Any], n: int) -> tuple[list[Any], int]:
    return items[:n], max(0, len(items) - n)


# -- project --------------------------------------------------------------------------

def project_pdf(p: dict[str, Any], generated_at: datetime, generated_by: str) -> bytes:
    pg = Page(A4, f"{p['code']} {p['name']} · one-pager", generated_by)
    m, W = pg.m, pg.w - 2 * pg.m
    src = p.get("source") or ""
    pg.c.setFillColor(C["bg"])
    pg.c.rect(0, 0, pg.w, pg.h, stroke=0, fill=1)

    # Header
    pg.label(m, m, f"Project one-pager · {generated_at:%d %b %Y}".replace(" 0", " "))
    pg.text(m, m + 14, p["code"], 10, "PJS-Bold", C["muted"])
    h = pg.para(m, m + 28, W - 110, escape(p["name"]), 22, "PJS-XBold", leading=25, lines=2)
    pg.pill(pg.w - m, m + 12, p.get("health"), 10, right=True)
    meta = " · ".join(x for x in [p.get("team"), f"Owner: {p.get('owner') or 'not set'}",
                                  f"{p.get('source_name', src)}: {p.get('status_raw') or p.get('status')}",
                                  f"Strategy: {p.get('strategy') or 'not tagged'}"] if x)
    y = m + 32 + h
    pg.para(m, y, W, escape(meta), 9, color=C["ink2"])
    y += 22

    # Four stat cards
    cw, gap, ch = (W - 3 * 10) / 4, 10, 74
    cards = [
        ("Health", None), ("Done", None), ("Next milestone", None), ("Time left", None)]
    for i, (lab, _) in enumerate(cards):
        x = m + i * (cw + gap)
        pg.box(x, y, cw, ch, C["surface"])
        pg.label(x + 12, y + 12, lab)
    x0 = m
    pg.pill(x0 + 12, y + 28, p.get("health"), 10)
    last = p.get("health_last_week")
    pg.text(x0 + 12, y + 54, f"Last week: {LABEL.get(last, 'no data')}" if last != p.get("health") else "Same as last week",
            8, color=C["muted"])
    x1 = m + cw + gap
    pg.text(x1 + 12, y + 26, f"{p.get('percent_done') if p.get('percent_done') is not None else '–'}%", 20, "PJS-XBold")
    pg.bar(x1 + 12, y + 52, cw - 24, p.get("percent_done"), C.get(f"{src}_bar", C["mint"]))
    x2 = m + 2 * (cw + gap)
    nm = next((ms for ms in p.get("milestones", []) if ms.get("next")), None)
    if nm:
        pg.para(x2 + 12, y + 26, cw - 24, escape(nm["name"]), 9.5, "PJS-Bold", lines=2)
        pg.text(x2 + 12, y + 54, _d(nm["due_date"]) + (" · overdue" if nm.get("overdue") else ""), 8,
                "PJS-Semi" if nm.get("overdue") else "PJS", C["off_track"] if nm.get("overdue") else C["muted"])
    else:
        pg.text(x2 + 12, y + 28, "None open", 10, "PJS-Bold")
    x3 = m + 3 * (cw + gap)
    dl = p.get("days_left")
    pg.text(x3 + 12, y + 26, "–" if dl is None else (f"{dl} days" if dl >= 0 else f"{-dl} days over"), 16, "PJS-XBold",
            C["off_track"] if dl is not None and dl < 0 else None)
    pg.text(x3 + 12, y + 54, f"{_d(p.get('start_date'))} – {_d(p.get('end_date'))}", 8, color=C["muted"])
    y += ch + 10

    # Radar note and health reasons
    reasons = p.get("health_reasons") or []
    note = p.get("radar_note")
    if note or reasons:
        body = escape(note) if note else "No open finding."
        if reasons:
            body += "<br/><font color='#9AA39C'>Health rule: " + escape("; ".join(reasons)) + "</font>"
        tmp = Paragraph(body, ParagraphStyle("r", fontName="PJS", fontSize=9.5, leading=13, textColor=C["surface"]))
        _, nh = tmp.wrap(W - 90, 10_000)
        nh = min(nh, 70)
        pg.box(m, y, W, nh + 24, C["black2"])
        pg.c.setFillColor(C["mint"])
        pg.c.circle(m + 24, pg.Y(y + 22), 9, stroke=0, fill=1)
        pg.text(m + 19.5, y + 17.5, "R", 9, "PJS-XBold", C["black2"])
        pg.text(m + 42, y + 12, "RADAR", 7, "PJS-Bold", C["mint"])
        pg.para(m + 42, y + 24 - 4, W - 60, body, 9.5, color=C["surface"], leading=13, lines=5)
        y += nh + 34
    # Two columns
    col = (W - 10) / 2
    top = y

    def section(x: float, y: float, title: str, rows: list[tuple[str, str, Any]], empty: str, limit: int) -> float:
        shown, more = _more(rows, limit)
        hh = 30 + max(1, len(shown)) * 19 + (14 if more else 0)
        pg.box(x, y, col, hh, C["surface"])
        pg.text(x + 14, y + 12, title, 11, "PJS-Bold")
        yy = y + 32
        if not shown:
            pg.text(x + 14, yy, empty, 8.5, color=C["muted"])
        for left, right, color in shown:
            pg.para(x + 14, yy - 1, col - 120, escape(left), 8.5, lines=1)
            pg.text(x + col - 14, yy, right, 8, "PJS-Semi", color or C["muted"], right=True)
            yy += 19
        if more:
            pg.text(x + 14, yy, f"and {more} more", 8, color=C["muted"])
        return hh

    ms_rows = [(ms["name"], ("Done" if ms["status"] == "done" else _d(ms["due_date"]) + (" · overdue" if ms.get("overdue") else "")),
                C["on_track"] if ms["status"] == "done" else C["off_track"] if ms.get("overdue") else None)
               for ms in p.get("milestones", [])]
    lh = section(m, top, f"Milestones · {p.get('milestones_done', 0)} of {len(ms_rows)} done", ms_rows, "No milestones in the tracker", 7)
    risk_rows = [(r["title"], f"{r['likelihood']} × {r['impact']}",
                  C["off_track"] if r["likelihood"] == "High" and r["impact"] == "High" else None) for r in p.get("risks", [])]
    lh2 = section(m, top + lh + 10, "Risks", risk_rows, "No risks recorded", 4)
    left_bottom = top + lh + 10 + lh2

    # Right column: sprint + tasks, trend, changes, dependencies
    x = m + col + 10
    sp = p.get("sprint")
    t = p.get("tasks")
    hh = 96
    pg.box(x, top, col, hh, C["surface"])
    pg.text(x + 14, top + 12, "Sprint and tasks", 11, "PJS-Bold")
    if sp:
        pg.text(x + 14, top + 32, f"{sp['name']} · ends {_d(sp.get('end_date'), '%d %b')}", 8.5, "PJS-Semi")
        pg.para(x + 14, top + 45, col - 28, escape(sp.get("goal") or "No sprint goal set"), 8.5, color=C["muted"], lines=1)
    else:
        pg.text(x + 14, top + 32, "No active sprint", 8.5, color=C["muted"])
    if t and t.get("total"):
        bx, bw, by = x + 14, col - 28, top + 66
        acc = 0.0
        for k, color in (("done", C["on_track"]), ("in_progress", C.get(f"{src}_bar", C["mint"])), ("todo", C["line"])):
            seg = bw * t[k] / t["total"]
            if seg > 0:
                pg.c.setFillColor(color)
                pg.c.rect(bx + acc, pg.Y(by + 7), seg, 7, stroke=0, fill=1)
            acc += seg
        pg.text(bx, by + 13, f"{t['done']} done · {t['in_progress']} in progress · {t['todo']} to do", 7.5, color=C["muted"])
    y2 = top + hh + 10

    trend = p.get("trend") or []
    th = 92
    pg.box(x, y2, col, th, C["surface"])
    pg.text(x + 14, y2 + 12, "Progress, last 6 weeks", 11, "PJS-Bold")
    if trend:
        n = len(trend)
        slot = (col - 28) / max(n, 1)
        for i, pt in enumerate(trend):
            v = pt.get("percent_done") or 0
            bh = 44 * v / 100
            bx = x + 14 + i * slot + slot * 0.2
            pg.c.setFillColor(C.get(f"{src}_bar", C["mint"]) if i == n - 1 else C["line"])
            pg.c.roundRect(bx, pg.Y(y2 + 76), slot * 0.6, max(bh, 1.5), 2, stroke=0, fill=1)
            pg.text(bx + slot * 0.3, y2 + 78, _d(pt["date"], "%d %b"), 6.5, color=C["muted"], right=False)
            pg.text(bx, y2 + 76 - bh - 10, f"{v}%", 6.5, "PJS-Semi")
    else:
        pg.text(x + 14, y2 + 34, "No history yet", 8.5, color=C["muted"])
    y3 = y2 + th + 10

    changes, more = _more(p.get("changes") or [], 5)
    chh = 30 + len(changes) * 14 + (12 if more else 0)
    pg.box(x, y3, col, chh, C["surface"])
    pg.text(x + 14, y3 + 12, "What changed this week", 11, "PJS-Bold")
    yy = y3 + 31
    for ch_ in changes:
        pg.para(x + 14, yy, col - 28, "• " + escape(ch_), 8.5, lines=1)
        yy += 14
    y4 = y3 + chh + 10

    deps = [(f"Waits for {d['short']} {d['name']}", LABEL.get(d.get("health") or "", ""), C.get(d.get("health") or ""))
            for d in p.get("waits_for", [])]
    deps += [(f"Blocks {d['short']} {d['name']}", LABEL.get(d.get("health") or "", ""), C.get(d.get("health") or ""))
             for d in p.get("blocks", [])]
    dh = 30 + max(1, min(4, len(deps))) * 16
    pg.box(x, y4, col, dh, C["surface"])
    pg.text(x + 14, y4 + 12, "Dependencies", 11, "PJS-Bold")
    yy = y4 + 32
    if not deps:
        pg.text(x + 14, yy, "None recorded", 8.5, color=C["muted"])
    for left, right, color in deps[:4]:
        pg.para(x + 14, yy - 1, col - 100, escape(left), 8.5, lines=1)
        pg.text(x + col - 14, yy, right, 8, "PJS-Semi", color, right=True)
        yy += 16
    _ = left_bottom

    si = p.get("source_info") or {}
    synced = si.get("last_good_sync_at") or p.get("synced_at")
    stale = " · STALE: last sync failed" if si.get("stale") else ""
    pg.footer(f"Data from {p.get('source_name', src)} ({p.get('source_key', '')}), synced "
              f"{datetime.fromisoformat(synced):%d %b %Y %H:%M}{stale} · made {generated_at:%d %b %Y %H:%M} for {generated_by}"
              if synced else f"Made {generated_at:%d %b %Y %H:%M} for {generated_by}")
    return pg.pdf()


# -- portfolio -------------------------------------------------------------------------

def overview_pdf(o: dict[str, Any], generated_at: datetime, generated_by: str) -> bytes:
    pg = Page(landscape(A4), f"Digital portfolio · {o['today']}", generated_by)
    m, W = pg.m, pg.w - 2 * pg.m
    pg.c.setFillColor(C["bg"])
    pg.c.rect(0, 0, pg.w, pg.h, stroke=0, fill=1)

    pg.label(m, m, "Steering Committee one-pager")
    pg.text(m, m + 13, f"Digital portfolio · {_d(o['today'], '%d %B %Y')}", 22, "PJS-XBold")
    sync = o.get("last_sync_at")
    pg.text(pg.w - m, m + 4, f"{o['total']} projects", 12, "PJS-Bold", right=True)
    pg.text(pg.w - m, m + 22, f"Last sync {datetime.fromisoformat(sync):%d %b %H:%M}" if sync else "Not synced yet",
            8, color=C["muted"], right=True)
    y = m + 50

    # Health tiles
    tw, gap, th = (W - 3 * 10) / 4, 10, 74
    for i, t in enumerate(o.get("tiles", [])):
        x = m + i * (tw + gap)
        pg.box(x, y, tw, th, C.get(f"{t['health']}_bg", C["surface"]))
        pg.text(x + 14, y + 12, t["label"], 9.5, "PJS-Bold", C["ink2"])
        pg.text(x + 14, y + 27, str(t["count"]), 24, "PJS-XBold")
        ch = t.get("change")
        if ch:
            pg.text(x + tw - 14, y + 14, f"{ch:+d}", 10, "PJS-Bold",
                    C["off_track"] if (ch > 0) == (t["health"] in ("off_track", "at_risk")) else C["on_track"], right=True)
        pg.para(x + 14, y + 55, tw - 28, escape(t.get("note") or ""), 7, color=C["ink2"], lines=1)
    y += th + 10

    colw = (W - 20) / 3
    # Column 1: sources + trend
    x = m
    pg.box(x, y, colw, 118, C["surface"])
    pg.text(x + 14, y + 12, "Sources", 11, "PJS-Bold")
    yy = y + 34
    for s in o.get("sources", []):
        pg.c.setFillColor(C.get(s["id"], C["surface2"]))
        pg.c.roundRect(x + 14, pg.Y(yy + 12), 12, 12, 3, stroke=0, fill=1)
        pg.text(x + 32, yy + 1, f"{s['name']} · {s['projects']} projects", 8.5, "PJS-Semi")
        state = "stale: last sync failed" if s.get("stale") else f"avg {s.get('avg_percent_done') or 0}% done"
        pg.text(x + colw - 14, yy + 1, state, 8, "PJS-Semi" if s.get("stale") else "PJS",
                C["off_track"] if s.get("stale") else C["muted"], right=True)
        yy += 24
    ty = y + 128
    trend = o.get("trend") or []
    pg.box(x, ty, colw, 128, C["surface"])
    pg.text(x + 14, ty + 12, "Average % done, 6 weeks", 11, "PJS-Bold")
    if trend:
        slot = (colw - 28) / len(trend)
        for i, pt in enumerate(trend):
            v = pt["avg_percent_done"]
            bh = 60 * v / 100
            bx = x + 14 + i * slot + slot * 0.2
            pg.c.setFillColor(C["mint"] if i == len(trend) - 1 else C["line"])
            pg.c.roundRect(bx, pg.Y(ty + 108), slot * 0.6, max(bh, 1.5), 2, stroke=0, fill=1)
            pg.text(bx, ty + 108 - bh - 10, f"{v}%", 7, "PJS-Semi")
            pg.text(bx, ty + 111, _d(pt["date"], "%d %b"), 6.5, color=C["muted"])
    else:
        pg.text(x + 14, ty + 40, "No history yet", 8.5, color=C["muted"])

    # Column 2: needs attention (off track then at risk)
    x = m + colw + 10
    hh = 256
    pg.box(x, y, colw, hh, C["surface"])
    pg.text(x + 14, y + 12, "Needs attention", 11, "PJS-Bold")
    rank = {"off_track": 0, "at_risk": 1}
    hot = sorted([r for r in o.get("projects", []) if r.get("health") in rank],
                 key=lambda r: (rank[r["health"]], -(len(r.get("health_reasons") or [])), r["code"]))
    shown, more = _more(hot, 8)
    yy = y + 34
    for r in shown:
        pg.c.setFillColor(C[r["health"]])
        pg.c.circle(x + 18, pg.Y(yy + 5), 3, stroke=0, fill=1)
        pg.para(x + 26, yy - 1, colw - 40, f"<b>{escape(r['short'])}</b> {escape(r['name'])}", 8.5, lines=1)
        why = "; ".join(r.get("health_reasons") or []) or LABEL.get(r["health"], "")
        pg.para(x + 26, yy + 11, colw - 40, escape(why), 7.2, color=C["muted"], lines=1)
        yy += 26
    if not shown:
        pg.text(x + 14, yy, "Nothing off track or at risk", 8.5, color=C["muted"])
    if more:
        pg.text(x + 14, y + hh - 18, f"and {more} more in the app", 8, color=C["muted"])

    # Column 3: next milestones + Radar
    x = m + 2 * (colw + 10)
    ms, _ = _more(o.get("next_milestones") or [], 6)
    mh = 32 + max(1, len(ms)) * 18
    pg.box(x, y, colw, mh, C["surface"])
    pg.text(x + 14, y + 12, "Next milestones", 11, "PJS-Bold")
    yy = y + 32
    for n in ms:
        pg.para(x + 14, yy - 1, colw - 110, f"<b>{escape(n['short'])}</b> {escape(n['name'])}", 8.2, lines=1)
        pg.text(x + colw - 14, yy, n["note"] if n.get("overdue") else _d(n["date"], "%d %b"), 7.8,
                "PJS-Semi" if n.get("overdue") else "PJS", C["off_track"] if n.get("overdue") else C["muted"], right=True)
        yy += 18
    if not ms:
        pg.text(x + 14, yy, "None in the trackers", 8.5, color=C["muted"])
    ry = y + mh + 10
    rh = 256 - mh - 10
    pg.box(x, ry, colw, rh, C["black2"])
    pg.c.setFillColor(C["mint"])
    pg.c.circle(x + 22, pg.Y(ry + 20), 8, stroke=0, fill=1)
    pg.text(x + 18, ry + 16, "R", 8, "PJS-XBold", C["black2"])
    radar = o.get("radar") or {}
    pg.text(x + 36, ry + 13, f"RADAR · {radar.get('count', 0)} open findings", 7.5, "PJS-Bold", C["mint"])
    yy = ry + 36
    items = radar.get("items") or []
    drawn = 0
    for it in items:
        if yy > ry + rh - 40:
            break
        yy += pg.para(x + 14, yy, colw - 28, "• " + escape(it["text"]), 7.8, color=C["surface"], lines=2) + 5
        drawn += 1
    if drawn < len(items):
        pg.text(x + 14, ry + rh - 20, f"and {len(items) - drawn} more in the app", 7.8, color=C["mint"])
    if not items:
        pg.text(x + 14, yy, "Nothing found in the last check", 8.5, color=C["surface"])

    pg.footer(f"Made {generated_at:%d %b %Y %H:%M} for {generated_by} · health is the rule-based RAG; "
              "Radar's notes are checks, not decisions")
    return pg.pdf()
