"""Export a trip plan as PDF, iCalendar (.ics) or Markdown."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

from fpdf import FPDF

from backend.agents.plan import TIER_LABEL, active_tier, money, stay_label, to_markdown



# ------------------------------------------------------------------ markdown
def markdown(plan: dict) -> str:
    return to_markdown(plan)


# ------------------------------------------------------------------ calendar
def _ics_escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines longer than 75 octets are folded."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > 74:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n".join(out)


def _hm(s: str | None) -> tuple[int, int] | None:
    m = re.match(r"(\d{1,2}):(\d{2})", s or "")
    return (int(m.group(1)) % 24, int(m.group(2))) if m else None


def ics(plan: dict, trip_id: str, option_tier: str | None = None) -> str:
    """One calendar event per stop (and travel leg) at its scheduled time."""
    tier = option_tier or active_tier(plan)
    days = (plan.get("schedules") or {}).get(tier) or []
    start = date.fromisoformat(days[0]["date"]) if days and days[0].get("date") else date.today() + timedelta(days=14)
    dest = plan.get("trip", {}).get("destination", "Trip")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TravelGenie//Trip Planner//EN",
             "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{_ics_escape(dest)} trip"]
    for d in days:
        day = start + timedelta(days=d["day"] - 1)
        for i, s in enumerate(d["steps"]):
            begin_hm = _hm(s.get("time"))
            if not begin_hm:
                continue
            begin = datetime(day.year, day.month, day.day, *begin_hm)
            minutes = s.get("minutes") or (20 if s["kind"] in ("start", "end", "depart") else 60)
            desc = s.get("detail") or ""
            if s["kind"] == "travel":
                desc = f"{s.get('distance_km')} km · {s.get('minutes')} min by {s.get('mode')}"
            place = s.get("place") or {}
            if place.get("hours"):
                desc += f"\nHours: {place['hours']}"
            lines += [
                "BEGIN:VEVENT",
                f"UID:{trip_id}-{tier}-{d['day']}-{i}@travelgenie",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{begin:%Y%m%dT%H%M%S}",
                f"DTEND:{begin + timedelta(minutes=minutes):%Y%m%dT%H%M%S}",
                _fold(f"SUMMARY:{_ics_escape(s['title'])}"),
                _fold(f"DESCRIPTION:{_ics_escape(f'Day {d['day']}: {d['title']}. {desc}')}"),
            ]
            if place.get("name"):
                lines.append(_fold(f"LOCATION:{_ics_escape(place['name'] + ', ' + dest)}"))
            if place.get("lat") is not None:
                lines.append(f"GEO:{place['lat']};{place['lon']}")
            lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ------------------------------------------------------------------ PDF
_REPLACE = {"₹": "Rs ", "€": "EUR ", "£": "GBP ", "¥": "JPY ", "—": "-", "–": "-", "‑": "-", "’": "'",
            "‘": "'", "“": '"', "”": '"', "…": "...", "•": "-", "\u202f": " ", "\u00a0": " ", "≈": "~",
            "°": " deg"}


def _latin1(text) -> str:
    """Core PDF fonts are Latin-1: swap symbols, strip accents, drop the rest."""
    text = str(text or "")
    for a, b in _REPLACE.items():
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.encode("latin-1", "ignore").decode("latin-1")


def _fit(doc: FPDF, s: str, width: float) -> str:
    """Trim text with an ellipsis so it fits a table cell."""
    s = _latin1(s)
    if doc.get_string_width(s) <= width:
        return s
    while s and doc.get_string_width(s + "...") > width:
        s = s[:-1]
    return s.rstrip() + "..."


class _PDF(FPDF):
    title_text = ""

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(140, 132, 120)
        self.cell(0, 8, _latin1(f"TravelGenie - {self.title_text} - page {self.page_no()}"), align="C")


ACCENT = (200, 96, 63)
INK = (29, 26, 22)
MUTED = (111, 103, 92)


def pdf(plan: dict, option_tier: str | None = None) -> bytes:
    cur = plan.get("currency", "")
    trip = plan.get("trip", {})
    dest = trip.get("destination", "Trip")
    options = plan.get("options", [])
    chosen = next((o for o in options if o["tier"] == option_tier), None)

    doc = _PDF(format="A4")
    doc.title_text = f"{dest} trip plan"
    doc.set_auto_page_break(True, margin=18)
    doc.set_margins(16, 16, 16)
    doc.add_page()
    w = doc.w - 32

    def text(s, size=10, style="", color=INK, h=5.2):
        doc.set_font("Helvetica", style, size)
        doc.set_text_color(*color)
        doc.set_x(doc.l_margin)
        doc.multi_cell(w, h, _latin1(s), new_x="LMARGIN", new_y="NEXT")

    def heading(s, size=13):
        doc.ln(3)
        text(s, size, "B", INK, 7)
        doc.set_draw_color(*ACCENT)
        doc.set_line_width(0.5)
        doc.line(16, doc.get_y() + 0.5, 16 + 24, doc.get_y() + 0.5)
        doc.ln(3)

    # Title
    text("TRAVELGENIE", 8, "B", ACCENT)
    text(f"{dest}: {len(plan.get('days', []))}-day plan", 22, "B", INK, 10)
    first = plan["days"][0].get("date") if plan.get("days") else None
    sub = [f"{plan.get('travelers', 1)} traveller(s)"]
    if first:
        sub.append(f"from {first}")
    if chosen:
        sub.append(f"{chosen['label']} option")
    text(" - ".join(sub), 10, "", MUTED)
    doc.ln(2)
    if plan.get("answer"):
        text(plan["answer"], 10.5, "B")
        doc.ln(1)
    text(plan.get("summary", ""), 10.5)
    if plan.get("assumptions"):
        doc.ln(1)
        text("Assumptions: " + "; ".join(plan["assumptions"]), 8.5, "I", MUTED, 4.4)

    # Options table
    heading("Options")
    shown = [chosen] if chosen else options
    cols = [w * 0.36, w * 0.15, w * 0.15, w * 0.34]
    doc.set_font("Helvetica", "B", 9)
    doc.set_fill_color(239, 233, 223)
    doc.set_text_color(*INK)
    for label, cw in zip(("Option", "Total", "Per person", "Stay"), cols):
        doc.cell(cw, 7, label, border=0, fill=True)
    doc.ln()
    doc.set_font("Helvetica", "", 9)
    for o in shown:
        picked = plan.get("places", {}).get((plan.get("hotels") or {}).get(o["tier"]) or "")
        row = (_fit(doc, f"{o['label']}: {o['title']}", cols[0] - 2), money(o["total"], cur),
               money(o.get("per_person"), cur), _fit(doc, picked["name"] if picked else stay_label(o, cur), cols[3] - 2))
        for value, cw in zip(row, cols):
            doc.cell(cw, 6.5, _latin1(value))
        doc.ln()
    for o in shown:
        b = o["breakdown"]
        doc.ln(2)
        text(f"{o['label']} - {o['title']}", 10.5, "B")
        text(f"Travel {money(b.get('travel'), cur)} - Stay {money(b['stay'], cur)} - Food {money(b['food'], cur)}"
             f" - Local transport {money(b['transport'], cur)} - Activities {money(b['activities'], cur)}"
             f" - Other {money(b['other'], cur)}", 9, "", MUTED, 4.6)
        gt = o.get("getting_there")
        if gt:
            text(f"Getting there: {gt['mode'].title()} - {gt['detail']}" + (f" ({gt['duration']})" if gt.get("duration") else "")
                 + (f", {money(gt.get('cost'), cur)} return" if gt.get("cost") else ""), 9.5)
        picked = plan.get("places", {}).get((plan.get("hotels") or {}).get(o["tier"]) or "")
        line = f"Stay: {picked['name'] + ', ' + (picked.get('area') or '') if picked else stay_label(o, cur)}"
        if o["stay"].get("why"):
            line += f" - {o['stay']['why']}"
        text(line, 9.5)
        for hl in o.get("highlights", []):
            text(f"- {hl}", 9.5)

    # The chosen option, in detail
    detailed = next((o for o in shown if o.get("details")), None)
    if detailed:
        det = detailed["details"]
        heading(f"Your plan: {detailed['label']}")
        text(det["overview"], 10)
        if det.get("booking_checklist"):
            doc.ln(2)
            text("Booking checklist", 10.5, "B")
            for bk in det["booking_checklist"]:
                text(f"[ ] {bk['item']} - {bk['when']}, via {bk['where']}"
                     + (f" ({money(bk.get('cost'), cur)})" if bk.get("cost") else ""), 9.5)

    # Getting there
    t = plan.get("transport")
    if t and t.get("modes"):
        heading(f"Getting there from {t.get('origin')}")
        text(t.get("summary", ""), 9.5, "", MUTED, 4.8)
        for m in t["modes"]:
            if not m.get("available"):
                continue
            price = (f"{money(m.get('price_min'), t.get('currency'))}-{money(m.get('price_max'), t.get('currency'))} pp one way"
                     if m.get("price_min") is not None else "")
            text(f"{m['mode'].title()}: {m.get('duration') or ''} - {price}", 10, "B", INK, 5.4)
            extra = " - ".join(x for x in (m.get("route"), f"book via {', '.join(m['book_via'])}" if m.get("book_via") else None) if x)
            if extra:
                text(extra, 9, "", MUTED, 4.6)

    # Day by day: the timestamped schedule of the chosen (or matched) option
    tier = option_tier or active_tier(plan)
    heading(f"Day by day ({TIER_LABEL.get(tier, tier)} option)")
    for d in (plan.get("schedules") or {}).get(tier, []):
        when = f"  ({d['date']})" if d.get("date") else ""
        doc.ln(1)
        text(f"Day {d['day']}{when} - {d['title']}", 11.5, "B", ACCENT, 6.5)
        for s in d["steps"]:
            if s["kind"] == "travel":
                how = "walk" if s.get("mode") == "walk" else s.get("mode", "")
                text(f"{s['time']}   {s['title']}  ({s.get('distance_km')} km, {s.get('minutes')} min, {how})", 9, "", MUTED, 4.8)
                continue
            dur = f"  [{s['minutes']} min]" if s.get("minutes") and s["kind"] not in ("start", "end", "depart") else ""
            text(f"{s['time']}   {s['title']}{dur}", 10, "B", INK, 5.4)
            if s.get("detail"):
                text(f"         {s['detail']}", 9, "", MUTED, 4.6)
            place = s.get("place") or {}
            if place.get("hours"):
                text(f"         Hours: {place['hours']}", 8.5, "I", MUTED, 4.4)

    if plan.get("weather_note"):
        heading("Weather")
        text(plan["weather_note"])
    if plan.get("packing"):
        heading("Packing list")
        text("\n".join(f"- {p}" for p in plan["packing"]))
    if plan.get("tips"):
        heading("Tips")
        text("\n".join(f"- {t}" for t in plan["tips"]))
    if plan.get("sources"):
        heading("Sources")
        for s in plan["sources"]:
            text(f"{s['n']}. {s['title']}" + (f" - {s['section']}" if s.get("section") else ""), 8.5, "", MUTED, 4.4)
    doc.ln(4)
    text("Prices are estimates from guides and listings; check with the provider before booking.", 8, "I", MUTED)
    return bytes(doc.output())
