"""Photos skill: real photos for sights, restaurants and stays, free and attributed.

Order of preference for each place:
  1. the Wikivoyage listing's own image, or its Wikidata item's photo (P18): exact
  2. the Wikipedia article about that place (matched by name near its coordinates)
  3. a Wikimedia Commons photo taken within ~250 m: labelled as an *area* photo
Results (including "no photo") are cached in the database for 30 days.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

from backend import db
from backend.skills import register

log = logging.getLogger(__name__)

UA = {"User-Agent": "TravelGenie/1.0 (open-source travel planner)"}
WIKIDATA = "https://www.wikidata.org/w/api.php"
WIKIPEDIA = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
CACHE_TTL = 30 * 86400
_lock = threading.Lock()
_last = 0.0
_SKIP = re.compile(r"(map|logo|locator|flag|icon|seal|coat.of.arms|diagram|plan|portrait|selfie|\bin (?:19|20)\d\d\b|\.svg|\.tif|\.pdf)", re.I)


def _get(url: str, params: dict) -> dict:
    global _last
    with _lock:
        wait = 0.25 - (time.time() - _last)   # stay well inside Wikimedia's rate limits
        if wait > 0:
            time.sleep(wait)
        _last = time.time()
    r = requests.get(url, params={**params, "format": "json"}, headers=UA, timeout=15)
    r.raise_for_status()
    return r.json()


def _photo(filename: str, kind: str) -> dict | None:
    filename = filename.replace("File:", "").strip()
    if not filename or _SKIP.search(filename):
        return None
    safe = quote(filename.replace(" ", "_"))
    return {
        "url": f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width=800",
        "thumb": f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe}?width=400",
        "page": f"https://commons.wikimedia.org/wiki/File:{safe}",
        "credit": "Wikimedia Commons",
        "kind": kind,   # "place" = this exact place; "area" = taken nearby
    }


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2 and w not in {"the", "and", "church", "temple", "beach"}}


def _wikidata_images(qids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(qids), 50):
        try:
            data = _get(WIKIDATA, {"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]), "props": "claims"})
        except (requests.RequestException, ValueError) as exc:
            log.warning("wikidata unavailable: %s", exc)
            continue
        for qid, ent in (data.get("entities") or {}).items():
            claims = (ent.get("claims") or {}).get("P18") or []
            if claims:
                out[qid] = claims[0]["mainsnak"]["datavalue"]["value"]
    return out


def _wikipedia_image(name: str, lat: float, lon: float) -> str | None:
    """The image of a Wikipedia article near (lat, lon) whose title matches the name."""
    near = _get(WIKIPEDIA, {"action": "query", "list": "geosearch", "gscoord": f"{lat}|{lon}",
                            "gsradius": 600, "gslimit": 10})
    want = _words(name)
    best = None
    for hit in near.get("query", {}).get("geosearch", []):
        got = _words(hit["title"])
        if want and len(want & got) / len(want) >= 0.5:
            best = hit["title"]
            break
    if not best:
        return None
    pages = _get(WIKIPEDIA, {"action": "query", "titles": best, "prop": "pageimages", "piprop": "name"})
    for page in pages.get("query", {}).get("pages", {}).values():
        if page.get("pageimage"):
            return page["pageimage"]
    return None


def _commons_nearby(lat: float, lon: float, radius: int = 250, must_mention: set[str] | None = None) -> str | None:
    """A photo taken near (lat, lon); with `must_mention`, only one whose title names the place/area.
    Network errors propagate so they are not cached as 'no photo'."""
    data = _get(COMMONS, {"action": "query", "list": "geosearch", "gscoord": f"{lat}|{lon}",
                          "gsradius": radius, "gsnamespace": 6, "gslimit": 30})
    for hit in data.get("query", {}).get("geosearch", []):
        title = hit["title"]
        if not re.search(r"\.(jpe?g|png|webp)$", title, re.I) or _SKIP.search(title):
            continue
        if must_mention and not (must_mention & set(re.findall(r"[a-z]+", title.lower()))):
            continue
        return title
    return None


def _key(p: dict) -> str:
    return f"photo:{p.get('name', '').lower()}|{p.get('lat') or 0:.4f},{p.get('lon') or 0:.4f}"


@register("find_photos", "Real, credited photos for places (exact when possible, otherwise of the area).",
          "Wikidata · Wikipedia · Wikimedia Commons")
def find_photos(items: list[dict], limit: int = 30) -> None:
    """Adds a `photo` field ({url, thumb, page, credit, kind} or None) to each item, in place."""
    todo = []
    for p in items[:limit]:
        try:
            hit = db.cache_get(_key(p), CACHE_TTL)
        except Exception:
            hit = None
        if hit is not None:
            p["photo"] = hit.get("photo")
        else:
            todo.append(p)
    if not todo:
        return

    # 1. Listing images and Wikidata photos, in one batched request.
    qids = [p["wikidata"] for p in todo if p.get("wikidata") and re.fullmatch(r"Q\d+", p["wikidata"])]
    wd = _wikidata_images(qids) if qids else {}

    def resolve(p: dict) -> tuple[dict | None, bool]:
        try:
            return _resolve(p), True
        except (requests.RequestException, ValueError) as exc:
            log.info("photo lookup failed for %s: %s", p.get("name"), exc)
            return None, False      # temporary failure: try again next time

    def _resolve(p: dict) -> dict | None:
        if p.get("image"):
            return _photo(p["image"], "place")
        if p.get("wikidata") in wd:
            return _photo(wd[p["wikidata"]], "place")
        if p.get("lat") is None or p.get("lon") is None:
            return None
        name = _wikipedia_image(p["name"], p["lat"], p["lon"])
        if name:
            return _photo(name, "place")
        near = _commons_nearby(p["lat"], p["lon"])
        return _photo(near, "area") if near else None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(resolve, todo))
    for p, (photo, ok) in zip(todo, results):
        p["photo"] = photo
        if ok:
            try:
                db.cache_set(_key(p), {"photo": photo})
            except Exception:
                pass


@register("area_photo", "A real photo of a neighbourhood (for stays without their own photo).",
          "OpenStreetMap Nominatim · Wikimedia Commons")
def area_photo(area: str, destination: str = "", near: tuple[float, float] | None = None) -> dict | None:
    """A photo taken within ~1 km of `near` (e.g. a hotel), else of the named area."""
    key = (f"photo-area:{near[0]:.3f},{near[1]:.3f}" if near else f"photo-area:{area.lower()}|{destination.lower()}")
    try:
        hit = db.cache_get(key, CACHE_TTL)
    except Exception:
        hit = None
    if hit is not None:
        return hit.get("photo")
    from backend.skills.geo import geocode
    pt = near or geocode(area, destination or None)
    if not pt:
        return None
    try:
        # Only photos that name the area or city, so it's recognisably the place (not a random object).
        words = {w for w in re.findall(r"[a-z]+", f"{area} {destination}".lower()) if len(w) > 3}
        name = _commons_nearby(pt[0], pt[1], radius=1500, must_mention=words or None)
    except (requests.RequestException, ValueError):
        return None
    photo = _photo(name, "area") if name else None
    try:
        db.cache_set(key, {"photo": photo})
    except Exception:
        pass
    return photo
