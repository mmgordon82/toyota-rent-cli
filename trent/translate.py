"""Japanese place names and labels → English, for the client-side rendering.

Prefectures and cities resolve through ``jp-prefecture``; store names are
romanized with ``pykakasi`` plus a table of common name pieces. The label
tables (tiers, conditions, vehicle groups) mirror ``getAppMaster`` so the CLI
can show the app's own categories in English.
"""

from __future__ import annotations

import re
from functools import lru_cache

import jp_prefecture
import pykakasi

_KAKASI = pykakasi.kakasi()
_CITIES = None


# --- English label tables (verified against getAppMaster) -------------------

TIER_NAMES = {"general": "Standard", "member": "Member", "goldMember": "Gold"}

PRICE_NAMES = {
    "車種おまかせ": "Any model in the class",
    "車種指定": "Specific model",
}

SMOKE = {"1": "Non-smoking", "2": "Smoking"}
TRANSMISSION = {"0": "Any gearbox", "1": "Automatic", "2": "Manual"}
DRIVE = {"0": "Any drivetrain", "1": "4WD"}

# topGroupNoName (getAppMaster.topGroups) → English vehicle category.
VEHICLE_GROUPS = {
    "コンパクト": "Compact",
    "乗用車": "Sedan",
    "ワゴン": "Wagon",
    "SUV": "SUV",
    "スペシャリティ": "Specialty",
    "バン・トラック": "Van / Truck",
}


# --- prefecture / city lookup -----------------------------------------------


def cities():
    global _CITIES
    if _CITIES is None:
        from jp_prefecture.jp_cities import JpCity

        _CITIES = JpCity()
    return _CITIES


def _latin_query(text: str) -> bool:
    return any(ch.isascii() and ch.isalpha() for ch in text)


def prefecture_jp(query: str) -> str | None:
    """Japanese prefecture name for an English or Japanese query."""
    if not query or query.isdigit():
        return None
    finder = jp_prefecture.jp_prefectures
    for candidate in (query, query.title()):
        try:
            code = finder.name2code(candidate)
        except (KeyError, TypeError, ValueError):
            code = None
        if code:
            return finder.code2name(int(code))
    return None


def city_jp(query: str) -> str | None:
    """Japanese city name. A bare English name also tries the -shi form."""
    if not query or query.isdigit():
        return None
    finder = cities()
    trials = [query, query.title()]
    if _latin_query(query) and "-" not in query and " " not in query:
        trials.append(f"{query.title()}-shi")
    seen = set()
    for trial in trials:
        if not trial or trial in seen:
            continue
        seen.add(trial)
        try:
            code = finder.cityname2code(trial, ignore_case=True)
        except (KeyError, TypeError, ValueError):
            code = None
        if code:
            name = finder.citycode2name(code)
            if name:
                return str(name)
    return None


def japanese_place(query: str) -> str | None:
    if not _latin_query(query):
        return None
    return prefecture_jp(query) or city_jp(query)


def english_prefecture(name: str) -> str | None:
    if not name:
        return None
    try:
        english = jp_prefecture.jp_prefectures.name2normalize(name, ascii=True)
    except (KeyError, TypeError, ValueError):
        return None
    return str(english) if english else None


# --- romaji folding and matching primitives ---------------------------------


def fold_latin(text: str) -> str:
    """Loose romaji key. Tokyo, Toukyou, and Tōkyō collapse together."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    previous = None
    while text != previous:
        previous = text
        text = text.replace("ou", "o").replace("oo", "o").replace("uu", "u")
    return text


@lru_cache(maxsize=4096)
def latin_keys(text: str) -> frozenset[str]:
    if not text:
        return frozenset()
    buckets = {key: [] for key in ("hepburn", "passport", "kunrei")}
    for item in _KAKASI.convert(text):
        for key in buckets:
            buckets[key].append(item.get(key) or "")
    return frozenset(
        fold_latin("".join(parts)) for parts in buckets.values() if any(parts)
    )


def text_hit(query: str, *texts: str) -> bool:
    if any(query in (text or "") for text in texts):
        return True
    if not _latin_query(query):
        return False
    folded = fold_latin(query)
    if not folded:
        return False
    return any(folded in key for text in texts for key in latin_keys(text or ""))


def name_equal(query: str, name: str) -> bool:
    if not name:
        return False
    if query == name:
        return True
    if not _latin_query(query):
        return False
    return fold_latin(query) in latin_keys(name)


# --- store / place name romanization ----------------------------------------

# Longer shop-name pieces first; leftover kanji is romanized.
_NAME_WORDS = (
    ("新幹線口", "Shinkansen Exit"),
    ("駅北口", "Station North Exit"),
    ("駅南口", "Station South Exit"),
    ("駅西口", "Station West Exit"),
    ("駅東口", "Station East Exit"),
    ("正面口", "Front Exit"),
    ("広場前", "Plaza"),
    ("広場", "Plaza"),
    ("国内線", "Domestic"),
    ("国際線", "International"),
    ("カウンター", "Counter"),
    ("美観地区", "Bikan District"),
    ("砂丘", "Dunes"),
    ("サンポート", "Sunport"),
    ("コナン", "Conan"),
    ("北口", "North Exit"),
    ("南口", "South Exit"),
    ("西口", "West Exit"),
    ("東口", "East Exit"),
    ("駅前", "Station"),
    ("空港", "Airport"),
    ("北区", "Kita Ward"),
    ("中区", "Naka Ward"),
    ("東区", "Higashi Ward"),
    ("南区", "Minami Ward"),
    ("西区", "Nishi Ward"),
    ("ＪＲ", "JR"),
    ("JR", "JR"),
    ("市", "City"),
    ("区", "Ward"),
    ("町", "Town"),
    ("村", "Village"),
    ("県", "Prefecture"),
    ("府", "Prefecture"),
    ("都", "Prefecture"),
)

_DIRECTIONS = {"東": "Higashi", "西": "Nishi", "南": "Minami", "北": "Kita"}


def _soften_reading(word: str) -> str:
    word = word.replace("'", "").replace("’", "")
    previous = None
    while word != previous:
        previous = word
        word = word.replace("ou", "o").replace("oo", "o").replace("uu", "u")
    return word


def _title_reading(word: str) -> str:
    word = _soften_reading(word)
    if not word:
        return ""
    if word in {"(", ")", "（", "）"}:
        return "(" if word in {"(", "（"} else ")"
    if word.isascii() and word.isupper():
        return word
    return word[:1].upper() + word[1:].lower()


def _romaji_chunk(chunk: str) -> str:
    chunk = chunk.strip(" 　")
    if not chunk:
        return ""
    if all(ch in "（）() " for ch in chunk):
        return "(" if "（" in chunk or "(" in chunk else ")"
    if chunk.startswith("新") and len(chunk) > 1:
        official = prefecture_jp(chunk[1:])
        if official:
            en = english_prefecture(official)
            if en:
                return f"Shin-{en}"
    words = []
    for item in _KAKASI.convert(chunk):
        raw = item.get("passport") or item.get("hepburn") or ""
        if raw:
            words.append(_title_reading(raw))
    return " ".join(word for word in words if word)


def english_text(name: str) -> str | None:
    """English or romanized reading. None when the text is already Latin."""
    if not name or not any(
        "぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in name
    ):
        return None
    official = english_prefecture(name)
    if official:
        return official
    parts = []
    i = 0
    while i < len(name):
        for ja, en in _NAME_WORDS:
            if name.startswith(ja, i):
                parts.append(en)
                i += len(ja)
                break
        else:
            j = i + 1
            while j < len(name) and not any(
                name.startswith(ja, j) for ja, _ in _NAME_WORDS
            ):
                j += 1
            parts.append(_romaji_chunk(name[i:j]))
            i = j
    english = re.sub(r"\s+", " ", " ".join(parts)).strip()
    english = english.replace("( ", "(").replace(" )", ")")
    return english or None


def english_store(store: dict) -> str | None:
    name = store.get("storeName") or ""
    kana = store.get("storeNameKana") or ""
    if any(ja in name for ja, _ in _NAME_WORDS):
        return english_text(name)
    if len(name) > 1 and name[0] in _DIRECTIONS:
        rest = english_text(name[1:])
        if rest:
            return f"{_DIRECTIONS[name[0]]} {rest}"
    if kana:
        return english_text(kana) or _romaji_chunk(kana)
    return english_text(name)


# --- display helpers --------------------------------------------------------


def prefer_english(text: str, english: str | None) -> str:
    if english:
        english = " ".join(str(english).split())
        if english:
            return english
    return text or ""


def show_store(store: dict) -> str:
    return prefer_english(store.get("storeName") or "", english_store(store))


def show_pref(name: str) -> str:
    return prefer_english(name or "", english_prefecture(name or ""))


def show_label(label: str) -> str:
    if not label:
        return ""
    base, sep, extra = label.partition(" (")
    english = prefer_english(base, english_text(base))
    return f"{english} ({extra}" if sep else english
