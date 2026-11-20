"""Real places for stays and sightseeing.

Sources (both free, no API key):
- Wikivoyage: curated listings of places to see, things to do and places to
  stay. Stays are already grouped Budget / Mid-range / Splurge and usually
  carry prices and coordinates. Big destinations (Tokyo, Goa, Bali) split
  their listings into district/town pages, so we follow the top few.
- OpenStreetMap Nominatim: geocoding for the map centre.

Results are cached on disk for a week.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import threading
import time
import requests

from backend.config import ROOT

log = logging.getLogger(__name__)

UA = {"User-Agent": "TravelGenie/1.0 (open-source travel planner)", "Accept-Language": "en"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
WIKIVOYAGE = "https://en.wikivoyage.org/w/api.php"
CACHE_DIR = ROOT / "storage" / "places_cache"
CACHE_TTL = 7 * 86400
_nominatim_lock = threading.Lock()
_last_nominatim = 0.0


_key_locks: dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()


def _cached(key: str, fn):
    """Disk cache; concurrent callers for the same key share one fetch."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def fresh():
        return path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL

    if fresh():
        return json.loads(path.read_text())
    with _key_locks_guard:
        lock = _key_locks.setdefault(key, threading.Lock())
    with lock:
        if fresh():
            return json.loads(path.read_text())
        value = fn()
        if value:
            path.write_text(json.dumps(value, ensure_ascii=False))
        return value


# ------------------------------------------------------------------ geocoding
def geocode(place: str) -> dict | None:
    def fetch():
        global _last_nominatim
        with _nominatim_lock:  # Nominatim allows 1 request per second
            wait = 1.1 - (time.time() - _last_nominatim)
            if wait > 0:
                time.sleep(wait)
            _last_nominatim = time.time()
            r = requests.get(NOMINATIM, params={"q": place, "format": "json", "limit": 1,
                                                "accept-language": "en"}, headers=UA, timeout=20)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return None
        return {"name": rows[0]["display_name"], "lat": float(rows[0]["lat"]), "lon": float(rows[0]["lon"])}
    try:
        return _cached(f"geo:{place.lower().strip()}", fetch)
    except requests.RequestException as exc:
        log.warning("geocode failed for %s: %s", place, exc)
        return None


# ------------------------------------------------------------------ wikitext parsing
_LISTING = re.compile(r"\{\{\s*(see|do|sleep|eat|drink|buy|listing|marker)\s*\|", re.I)
_HEADING = re.compile(r"^(={2,4})\s*(.+?)\s*\1\s*$", re.M)


def _template_end(text: str, start: int) -> int:
    """Index just past the }} that closes the template opening at `start`."""
    depth, i = 0, start
    while i < len(text) - 1:
        pair = text[i:i + 2]
        if pair == "{{":
            depth += 1
            i += 2
        elif pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return len(text)


def _split_fields(body: str) -> dict:
    """Split 'a=1|b=[[x|y]]|c={{t|u}}' on top-level pipes only."""
    fields, depth, cur = [], 0, []
    i = 0
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            cur.append(two)
            i += 2
            continue
        if two in ("}}", "]]"):
            depth -= 1
            cur.append(two)
            i += 2
            continue
        if body[i] == "|" and depth == 0:
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(body[i])
        i += 1
    fields.append("".join(cur))
    out = {}
    for f in fields:
        if "=" in f:
            k, v = f.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def _clean(text: str | None, limit: int = 220) -> str:
    if not text:
        return ""
    t = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>|<!--.*?-->", "", text, flags=re.S)
    t = re.sub(r"\[\[(?:File|Image):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", "", t, flags=re.I)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", t)
    t = re.sub(r"'{2,}", "", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit].rsplit(" ", 1)[0] + "…" if len(t) > limit else t


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _sleep_tier(heading: str) -> str | None:
    h = heading.lower()
    if "budget" in h or "cheap" in h or "hostel" in h:
        return "budget"
    if "mid" in h or "moderate" in h:
        return "mid"
    if "splurge" in h or "luxury" in h or "upscale" in h or "high" in h:
        return "luxury"
    return None


def parse_listings(wikitext: str, area: str) -> list[dict]:
    headings = [(m.start(), len(m.group(1)), m.group(2)) for m in _HEADING.finditer(wikitext)]
    out = []
    for m in _LISTING.finditer(wikitext):
        end = _template_end(wikitext, m.start())
        fields = _split_fields(wikitext[m.end():end - 2])
        name = _clean(fields.get("name"), 90)
        if not name:
            continue
        # Section context: nearest level-2 heading (Sleep/See/...) and level-3 sub-heading (Budget...).
        level2 = level3 = ""
        for pos, lvl, title in headings:
            if pos > m.start():
                break
            if lvl == 2:
                level2, level3 = title, ""
            else:
                level3 = title
        section_kind = {"see": "see", "do": "do", "sleep": "sleep"}.get(level2.strip().lower())
        kind = m.group(1).lower()
        if kind in ("listing", "marker"):
            # Generic listings: trust the section, not the template (avoids embassies, hospitals...).
            kind = section_kind or ""
        if kind not in ("see", "do", "sleep") or (section_kind is None and level2.strip().lower() not in ("", "understand")
                                                    and kind != m.group(1).lower()):
            continue
        item = {
            "name": name,
            "kind": kind,
            "area": area,
            "lat": _float(fields.get("lat")),
            "lon": _float(fields.get("long") or fields.get("lon")),
            "price": _clean(fields.get("price"), 90) or None,
            "hours": _clean(fields.get("hours"), 70) or None,
            "url": (fields.get("url") or "").strip() or None,
            "description": _clean(fields.get("content") or fields.get("description")),
        }
        if kind == "sleep":
            item["tier"] = _sleep_tier(level3) or _sleep_tier(level2)  # None → decided later
        out.append(item)
    return out


_LUXURY_WORDS = re.compile(r"\b(luxury|villa|resort|marriott|hyatt|hilton|ritz|conrad|taj|"
                           r"four seasons|sheraton|westin|intercontinental|leela|oberoi|mandarin|peninsula|"
                           r"regis|kempinski|shangri|aman)\b", re.I)
_BUDGET_WORDS = re.compile(r"\b(hostel|backpack\w*|dorm\w*|bunk|capsule|youth|zostel|homestay|guest ?house)\b", re.I)


def _price_value(price: str | None) -> float | None:
    """First number in a price string ('₹1,200-2,000' → 1200)."""
    if not price:
        return None
    m = re.search(r"\d[\d,.]*", price)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "").rstrip("."))
    except ValueError:
        return None


def _assign_tiers(stays: list[dict]) -> None:
    """Fill missing tiers: price terciles first, then name/description keywords."""
    priced = sorted(v for s in stays if (v := _price_value(s.get("price"))))
    lo = priced[len(priced) // 3] if len(priced) >= 3 else None
    hi = priced[(2 * len(priced)) // 3] if len(priced) >= 3 else None
    for s in stays:
        if s.get("tier"):
            continue
        text = f"{s['name']} {s.get('description') or ''}"
        value = _price_value(s.get("price"))
        if _BUDGET_WORDS.search(s["name"]):
            s["tier"] = "budget"
        elif _LUXURY_WORDS.search(s["name"]):
            s["tier"] = "luxury"
        elif value is not None and lo is not None:
            s["tier"] = "budget" if value <= lo else "luxury" if value > hi else "mid"
        elif _BUDGET_WORDS.search(text):
            s["tier"] = "budget"
        elif _LUXURY_WORDS.search(text):
            s["tier"] = "luxury"
        else:
            s["tier"] = "mid"


# ------------------------------------------------------------------ fetching
_wv_lock = threading.Lock()
_wv_last = 0.0


def _wv_get(params: dict) -> requests.Response:
    """Wikimedia API call, serialised and spaced out so we don't get rate-limited."""
    global _wv_last
    with _wv_lock:
        wait = 1.0 - (time.time() - _wv_last)
        if wait > 0:
            time.sleep(wait)
        try:
            return requests.get(WIKIVOYAGE, params=params, headers=UA, timeout=20)
        finally:
            _wv_last = time.time()


def _wikitext(page: str) -> tuple[str, str] | None:
    def fetch():
        for attempt in range(3):
            r = _wv_get({"action": "parse", "page": page, "prop": "wikitext",
                         "format": "json", "formatversion": 2, "redirects": 1})
            if r.status_code == 429 or not r.headers.get("content-type", "").startswith("application/json"):
                time.sleep(2.0 * (attempt + 1))  # rate limited: back off and retry
                continue
            data = r.json()
            if "parse" not in data:
                return None
            return {"title": data["parse"]["title"], "wikitext": data["parse"]["wikitext"]}
        raise requests.RequestException(f"Wikivoyage kept rate-limiting {page}")
    try:
        res = _cached(f"wv:{page}", fetch)
    except (requests.RequestException, ValueError) as exc:
        log.warning("wikivoyage fetch failed for %s: %s", page, exc)
        return None
    return (res["title"], res["wikitext"]) if res else None


def _child_pages(wikitext: str, limit: int, title: str = "") -> list[str]:
    """Linked districts / cities / regions, in the order the guide lists them."""
    priority = ["districts", "cities", "towns", "other destinations", "regions"]
    found: dict[str, list[str]] = {}
    for m in _HEADING.finditer(wikitext):
        heading = m.group(2).strip().lower()
        if heading not in priority:
            continue
        # The section runs until the next heading of the same or higher level,
        # so links under its sub-headings (=== Central ===) are included.
        level = len(m.group(1))
        end = len(wikitext)
        for nxt in _HEADING.finditer(wikitext, m.end()):
            if len(nxt.group(1)) <= level:
                end = nxt.start()
                break
        section = wikitext[m.end():end]
        links = re.findall(r"\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]", section)
        # Region-list templates name pages as regionNname=[[X]] or plain regionNname=X.
        links += re.findall(r"region\d+name\s*=\s*\[?\[?([^|\]\n]+)", section)
        found.setdefault(heading, []).extend(l.strip() for l in links)
    pages: list[str] = []
    for heading in priority:
        for link in found.get(heading, []):
            if link and ":" not in link and link not in pages and not link.startswith(f"{title} ("):
                pages.append(link)
    # The page's own district subpages (Tokyo/Shinjuku) beat other places the
    # intro text happens to mention (Yokohama, Chiba).
    own = [p for p in pages if title and p.startswith(f"{title}/")]
    return (own + [p for p in pages if p not in own])[:limit]


def _search_page(destination: str) -> str | None:
    """Best-matching Wikivoyage page title for a free-text destination."""
    try:
        r = _wv_get({"action": "query", "list": "search", "srsearch": destination, "srlimit": 1, "format": "json"})
        hits = r.json().get("query", {}).get("search", [])
        return hits[0]["title"] if hits else None
    except (requests.RequestException, ValueError):
        return None


def _root_page(destination: str) -> tuple[str, str] | None:
    name = destination.split(",")[0].strip()
    root = _wikitext(name)
    if root:
        return root
    title = _search_page(destination)
    return _wikitext(title) if title else None


def _section_text(wikitext: str, heading: str) -> dict[str, str]:
    """A level-2 section, split into its sub-sections ('By plane', 'By train'…)."""
    out: dict[str, str] = {}
    matches = list(_HEADING.finditer(wikitext))
    for i, m in enumerate(matches):
        if len(m.group(1)) != 2 or m.group(2).strip().lower() != heading.lower():
            continue
        end = next((n.start() for n in matches[i + 1:] if len(n.group(1)) <= 2), len(wikitext))
        body = wikitext[m.end():end]
        parts = re.split(r"^={3,4}\s*(.+?)\s*={3,4}\s*$", body, flags=re.M)
        intro = _clean(_strip_listings(parts[0]), 700)
        if intro:
            out["_intro"] = intro
        for j in range(1, len(parts) - 1, 2):
            text = _clean(_strip_listings(parts[j + 1]), 900)
            name = parts[j].strip().strip("=").strip()
            if text and name:
                out[name] = (out.get(name, "") + " " + text).strip()[:900]
        break
    return out


def _strip_listings(text: str) -> str:
    """Turn listing templates into 'Name: description' so prose sections stay readable."""
    def repl(m: re.Match) -> str:
        end = _template_end(text, m.start())
        f = _split_fields(text[m.end():end - 2])
        return f" {f.get('name', '')}: {f.get('content', '')} "
    out, pos = [], 0
    for m in _LISTING.finditer(text):
        if m.start() < pos:
            continue
        out.append(text[pos:m.start()])
        end = _template_end(text, m.start())
        out.append(repl(m))
        pos = end
    out.append(text[pos:])
    return "".join(out)


def get_guide(destination: str) -> dict:
    """Prose sections from the destination's Wikivoyage page, with a link."""
    def build():
        root = _root_page(destination)
        if not root:
            return None
        title, text = root
        return {
            "title": title,
            "url": f"https://en.wikivoyage.org/wiki/{title.replace(' ', '_')}",
            "sections": {h: _section_text(text, h) for h in
                         ("Understand", "Get in", "Get around", "Stay safe", "Respect", "Climate", "Cope")},
        }
    return _cached(f"guide:{destination.lower().strip()}", build) or {}


def get_places(destination: str, max_pages: int = 5) -> dict:
    """Stays (by tier) and sights for a destination, plus a map centre."""
    def build():
        name = destination.split(",")[0].strip()
        root = _wikitext(name) or (_wikitext(t) if (t := _search_page(destination)) else None)
        listings: list[dict] = []
        pages_used: list[str] = []
        if root:
            title, text = root
            pages_used.append(title)
            listings += parse_listings(text, title.split("/")[-1])

            def thin() -> bool:
                return (sum(x["kind"] == "sleep" for x in listings) < 12
                        or sum(x["kind"] in ("see", "do") for x in listings) < 15)

            # Region or huge-city page: follow its districts/towns until we have enough.
            if thin():
                for child in _child_pages(text, max_pages * 2, title):
                    if len(pages_used) > max_pages or not thin():
                        break
                    res = _wikitext(child)
                    if not res:
                        continue
                    found = parse_listings(res[1], res[0].split("/")[-1])
                    if found:
                        pages_used.append(res[0])
                        listings += found
        _assign_tiers([x for x in listings if x["kind"] == "sleep"])
        return {"pages": pages_used, "listings": listings}

    data = _cached(f"places:{destination.lower().strip()}", build) or {"pages": [], "listings": []}
    geo = geocode(destination)

    stays = [x for x in data["listings"] if x["kind"] == "sleep"]
    sights = [x for x in data["listings"] if x["kind"] in ("see", "do")]

    def rank(x: dict) -> float:
        return (2 if x.get("lat") else 0) + (1 if x.get("price") else 0) + min(len(x.get("description") or ""), 200) / 100

    by_tier = {t: sorted((s for s in stays if s["tier"] == t), key=rank, reverse=True)[:8]
               for t in ("budget", "mid", "luxury")}
    sights = sorted(sights, key=rank, reverse=True)[:30]
    for i, x in enumerate([*by_tier["budget"], *by_tier["mid"], *by_tier["luxury"], *sights]):
        x["id"] = f"p{i + 1}"
    return {
        "center": geo,
        "stays": [*by_tier["budget"], *by_tier["mid"], *by_tier["luxury"]],
        "sights": sights,
        "pages": data["pages"],
        "error": None if data["listings"] else "No Wikivoyage listings found for this destination",
    }
