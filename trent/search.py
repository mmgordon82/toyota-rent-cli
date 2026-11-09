"""Resolving user input to stores and map centers: code, name, or place.

Shop codes (``65301/026``) match exactly; everything else matches Japanese or
romaji against store names, cities, and prefectures, with fuzzy suggestions
when nothing lands. Geo helpers find stores within a radius of a resolved
center.
"""

from __future__ import annotations

import math

import jp_prefecture
from rapidfuzz import fuzz

from trent.api import (
    ApiError,
    SHOP_CODE,
    fetch_places,
    shop_id,
    store_point,
)
from trent.translate import (
    _latin_query,
    cities,
    english_prefecture,
    english_text,
    fold_latin,
    japanese_place,
    latin_keys,
    name_equal,
    prefecture_jp,
    prefer_english,
    show_pref,
    show_store,
    text_hit,
)


# --- matching ---------------------------------------------------------------


def matching_stores(spec: str, stores: list[dict]) -> list[dict]:
    spec = spec.strip()
    match = SHOP_CODE.fullmatch(spec)
    if match:
        r_code, code = match.group(1), match.group(2)
        return [
            s
            for s in stores
            if s.get("storeRCode") == r_code and s.get("storeCode") == code
        ]
    return [
        s
        for s in stores
        if text_hit(spec, s.get("storeName") or "", s.get("storeNameKana") or "")
    ]


def pref_hit(query: str, store: dict) -> bool:
    name = store.get("prefName") or ""
    if query == str(store.get("prefCode")) or text_hit(query, name):
        return True
    official = prefecture_jp(query)
    return bool(official) and official == name


def filter_stores(stores: list[dict], keyword: str | None, pref: str | None) -> list[dict]:
    out = []
    for store in stores:
        if keyword and not text_hit(
            keyword, store.get("storeName") or "", store.get("storeNameKana") or ""
        ):
            continue
        if pref and not pref_hit(pref, store):
            continue
        out.append(store)
    return out


# --- fuzzy suggestions ------------------------------------------------------


def fuzzy_labels(
    query: str, choices: list[tuple[str, tuple[str, ...]]], limit: int = 5
) -> list[str]:
    folded = fold_latin(query) if _latin_query(query) else ""
    scored = []
    for label, forms in choices:
        best = 0.0
        for form in forms:
            if not form:
                continue
            best = max(best, float(fuzz.WRatio(query, form)))
            if folded:
                best = max(best, float(fuzz.WRatio(folded, fold_latin(form))))
        scored.append((best, label))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [label for score, label in scored if score >= 65][:limit]


def name_miss(query: str, choices: list[tuple[str, tuple[str, ...]]]) -> ApiError:
    lines = fuzzy_labels(query, choices)
    message = f"No match for {query!r}."
    if lines:
        message += "\nClosest names:\n" + "\n".join(f"  {line}" for line in lines)
    return ApiError(message)


def store_choices(stores: list[dict]) -> list[tuple[str, tuple[str, ...]]]:
    choices = []
    for store in stores:
        name = store.get("storeName") or ""
        kana = store.get("storeNameKana") or ""
        forms = (name, kana, *latin_keys(name), *latin_keys(kana))
        choices.append((f"{shop_id(store)}  {show_store(store)}", forms))
    return choices


def place_choices(places: list[dict]) -> list[tuple[str, tuple[str, ...]]]:
    choices = []
    seen = set()
    finder = jp_prefecture.jp_prefectures
    for place in places:
        name = place.get("name") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        forms = [name, place_stem(name), *latin_keys(name)]
        label = prefer_english(name, english_text(name))
        if place.get("kind") == "prefecture":
            try:
                alphabet = finder.name2normalize(name, ascii=True)
            except (KeyError, TypeError, ValueError):
                alphabet = None
            if alphabet:
                forms.append(str(alphabet))
                label = str(alphabet)
        choices.append((label, tuple(forms)))
    table = cities().cities
    for city_name, alphabet in zip(table.cityName, table.cityAlphabet):
        city_name, alphabet = str(city_name), str(alphabet)
        if city_name in seen:
            continue
        seen.add(city_name)
        bare = alphabet.split("-")[0]
        label = prefer_english(city_name, english_text(city_name) or bare)
        choices.append((label, (city_name, alphabet, bare)))
    return choices


# --- place-name stems -------------------------------------------------------


def place_stem(name: str) -> str:
    if name == "北海道":
        return name
    for suffix in ("都", "府", "県", "市", "区", "町", "村"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def _stem_equal(query: str, name: str) -> bool:
    stem = place_stem(name)
    if not stem or stem == name:
        return False
    return name_equal(query, stem)


def _name_prefix(query: str, name: str) -> bool:
    if name.startswith(query):
        return True
    if not _latin_query(query):
        return False
    folded = fold_latin(query)
    return any(key.startswith(folded) for key in latin_keys(name))


# --- geo --------------------------------------------------------------------


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def stores_within(
    stores: list[dict], lat: float, lon: float, radius_km: float
) -> list[tuple[dict, float]]:
    """Stores whose coordinates fall inside radius_km, nearest first."""
    hits = []
    for store in stores:
        point = store_point(store)
        if point is None:
            continue
        dist = distance_km(lat, lon, point[0], point[1])
        if dist <= radius_km:
            hits.append((store, dist))
    hits.sort(key=lambda item: item[1])
    return hits


def _place_point(place: dict) -> tuple[float, float]:
    try:
        return float(place["latitude"]), float(place["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(f"place {place.get('name')!r} has no coordinates") from exc


# --- resolution -------------------------------------------------------------


def resolve_shop(spec: str, stores: list[dict]) -> dict:
    hits = matching_stores(spec, stores)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise name_miss(spec, store_choices(stores))
    raise ApiError(_store_matches(spec, hits))


def _store_matches(spec: str, hits: list[dict]) -> str:
    lines = [
        f"  {shop_id(s)}  {show_store(s)}  {show_pref(s.get('prefName') or '')}"
        for s in hits[:30]
    ]
    extra = f"\n  … {len(hits) - 30} more" if len(hits) > 30 else ""
    return f"{len(hits)} stores match {spec!r}:\n" + "\n".join(lines) + extra


def _place_choices(spec: str, places: list[dict]) -> str:
    lines = []
    for place in places[:30]:
        name = prefer_english(
            place.get("name") or "",
            english_prefecture(place.get("name") or "")
            or english_text(place.get("name") or ""),
        )
        pref = show_pref(place.get("pref") or "")
        if pref and pref.lower() not in name.lower():
            name = f"{name}, {pref}"
        lines.append(f"  {name}")
    extra = f"\n  … {len(places) - 30} more" if len(places) > 30 else ""
    return f"{len(places)} places match {spec!r}:\n" + "\n".join(lines) + extra


def resolve_center(
    spec: str, stores: list[dict], places: list[dict]
) -> tuple[float, float, str]:
    """Center for a shop code, a store name, or a city/prefecture name."""
    spec = spec.strip()
    if SHOP_CODE.fullmatch(spec):
        shop = resolve_shop(spec, stores)
        point = store_point(shop)
        if point is None:
            raise ApiError(f"{spec} has no coordinates")
        return point[0], point[1], f"{shop_id(shop)} {show_store(shop)}"

    lookup = japanese_place(spec) or spec
    exact = [p for p in places if name_equal(lookup, p.get("name") or "")]
    stemmed = [
        p
        for p in places
        if p not in exact and _stem_equal(lookup, p.get("name") or "")
    ]
    if len(exact) == 1:
        lat, lon = _place_point(exact[0])
        return lat, lon, exact[0]["name"]
    if len(exact) > 1:
        raise ApiError(_place_choices(spec, exact))
    pref = [p for p in stemmed if p.get("kind") == "prefecture"]
    if len(pref) == 1:
        lat, lon = _place_point(pref[0])
        return lat, lon, pref[0]["name"]
    if len(stemmed) == 1:
        lat, lon = _place_point(stemmed[0])
        return lat, lon, stemmed[0]["name"]
    if len(stemmed) > 1:
        raise ApiError(_place_choices(spec, stemmed))

    prefixed = [p for p in places if _name_prefix(lookup, p.get("name") or "")]
    if len(prefixed) > 1 and lookup.endswith("市"):
        points = [_place_point(p) for p in prefixed]
        lat = sum(p[0] for p in points) / len(points)
        lon = sum(p[1] for p in points) / len(points)
        return lat, lon, f"{lookup} ({len(prefixed)} towns)"

    hits = matching_stores(spec, stores)
    if len(hits) == 1:
        point = store_point(hits[0])
        if point is None:
            raise ApiError(f"{spec} has no coordinates")
        return point[0], point[1], f"{shop_id(hits[0])} {show_store(hits[0])}"
    if len(hits) > 1:
        raise ApiError(_store_matches(spec, hits))
    if len(prefixed) == 1:
        lat, lon = _place_point(prefixed[0])
        return lat, lon, prefixed[0]["name"]
    if prefixed:
        raise ApiError(_place_choices(lookup, prefixed))
    raise name_miss(spec, place_choices(places) + store_choices(stores))


def nearby_stores(
    args, stores: list[dict]
) -> tuple[str, float, float, list[tuple[dict, float]]]:
    if args.km is None:
        raise ApiError("--km is required with --near")
    if args.km <= 0:
        raise ApiError("--km must be greater than 0")
    lat, lon, label = resolve_center(args.near, stores, fetch_places())
    hits = stores_within(stores, lat, lon, args.km)
    return label, lat, lon, hits
