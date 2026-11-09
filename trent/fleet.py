"""Japanese car names → English Toyota/Lexus nameplates.

The API returns ``carName`` in Japanese (e.g. ``アルファードHEV('23.6～)``).
Phonetic transliteration gets these wrong (アルファード → "Arufado", not
"Alphard"), so the nameplates are a curated map covering the rental fleet
exposed by ``getAppMaster``. Latin names (RX, MIRAI, bZ4X, GR86…) pass through.
Year windows, hybrid/PHEV markers and common variant words are rendered too.
"""

from __future__ import annotations

import re

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# Nameplates, longest Japanese key first so compounds win (カローラクロス before
# カローラ). Latin-only names are absent on purpose — they pass through as-is.
_MODELS = (
    ("ランドクルーザープラド", "Land Cruiser Prado"),
    ("ハイエースグランドキャビン", "Hiace Grand Cabin"),
    ("ハイエースコミューター", "Hiace Commuter"),
    ("クラウンクロスオーバー", "Crown Crossover"),
    ("カローラフィールダー", "Corolla Fielder"),
    ("カローラツーリング", "Corolla Touring"),
    ("カローラアクシオ", "Corolla Axio"),
    ("カローラスポーツ", "Corolla Sport"),
    ("ダイナ・トヨエース", "Dyna / Toyoace"),
    ("ランドクルーザー", "Land Cruiser"),
    ("レジアスエースバン", "Regiusace Van"),
    ("ハイエースバン", "Hiace Van"),
    ("カローラクロス", "Corolla Cross"),
    ("レジアスエース", "Regiusace"),
    ("ヤリスクロス", "Yaris Cross"),
    ("ヴェルファイア", "Vellfire"),
    ("アルファード", "Alphard"),
    ("エスクァイア", "Esquire"),
    ("エスティマ", "Estima"),
    ("プロボックス", "Probox"),
    ("カローラ", "Corolla"),
    ("ハイエース", "Hiace"),
    ("クラウン", "Crown"),
    ("ヴォクシー", "Voxy"),
    ("ハリアー", "Harrier"),
    ("ラクティス", "Ractis"),
    ("サクシード", "Succeed"),
    ("アルミバン", "Aluminum Van"),
    ("GRヤリス", "GR Yaris"),
    ("マークX", "Mark X"),
    ("プリウス", "Prius"),
    ("シエンタ", "Sienta"),
    ("コースター", "Coaster"),
    ("アイシス", "Isis"),
    ("アリオン", "Allion"),
    ("プレミオ", "Premio"),
    ("ヴィッツ", "Vitz"),
    ("ヤリス", "Yaris"),
    ("スペイド", "Spade"),
    ("ルーミー", "Roomy"),
    ("パッソ", "Passo"),
    ("ポルテ", "Porte"),
    ("カムリ", "Camry"),
    ("ライズ", "Raize"),
    ("アクア", "Aqua"),
    ("タンク", "Tank"),
    ("ノア", "Noah"),
)

# Variant and body-spec words that remain after the nameplate is swapped out.
# Truck/van body terms carry a leading space so concatenated specs separate
# (e.g. ワイドキャブロングデッキ → "Wide Cab Long Deck").
_VARIANTS = (
    ("クロスオーバー", "Crossover"),
    ("スポーツ", "Sport"),
    ("地域限定", "select areas"),
    ("ワイドキャブ", " Wide Cab"),
    ("ロングデッキ", " Long Deck"),
    ("ワイド", " Wide"),
    ("キャブ", " Cab"),
    ("ロング", " Long"),
    ("デッキ", " Deck"),
    ("標準", " Standard"),
    ("未満", " under"),
    ("以上", " and up"),
    ("・", " / "),
)

_KATAKANA = re.compile(r"[゠-ヿ぀-ゟ一-鿿]")
_YEAR_PAREN = re.compile(r"[(（]([^)）]*['’´](\d{2})\.(\d{1,2})[^)）]*)[)）]")
_HYBRID_TOKEN = re.compile(r"\s*(?:PHEV|PHV|HEV|HV)\b")


def _year_note(name: str) -> tuple[str, str]:
    """Return (name without the year paren, ' (from/until Mon YYYY)')."""
    match = _YEAR_PAREN.search(name)
    if not match:
        return name, ""
    inner, year, month = match.group(1), match.group(2), int(match.group(3))
    when = f"{_MONTHS[month - 1]} 20{year}" if 1 <= month <= 12 else match.group(0)
    apost = re.search(r"['’´]\d{2}\.\d{1,2}", inner)
    until = apost is not None and any(t in inner[: apost.start()] for t in "～~")
    stripped = name[: match.start()] + name[match.end():]
    return stripped, f" (until {when})" if until else f" (from {when})"


def english_model(name: str) -> str:
    """English nameplate for an API ``carName``. Latin names pass through."""
    text = (name or "").strip()
    if not text:
        return ""
    if re.search(r"PHE?V", text):
        suffix = " Plug-in Hybrid"
    elif _HYBRID_TOKEN.search(text) or "ハイブリッド" in text:
        suffix = " Hybrid"
    else:
        suffix = ""
    text = _HYBRID_TOKEN.sub("", text).replace("ハイブリッド", "")
    text, note = _year_note(text)
    for ja, en in _MODELS:
        if ja in text:
            # Trailing space keeps the nameplate off a glued suffix/number,
            # e.g. プリウス2.0 → "Prius 2.0", クラウン(スポーツ) → "Crown (Sport)".
            text = text.replace(ja, en + " ")
            break
    for ja, en in _VARIANTS:
        text = text.replace(ja, en)
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("( ", "(").replace(" )", ")")
    return f"{text}{suffix}{note}".strip()


def car_label(car: dict) -> str:
    """Display label for a car row (``{'carName': ...}``)."""
    return english_model(car.get("carName") or "")


def model_matches(query: str, car_name: str) -> bool:
    """True if ``query`` matches the car's Japanese name or its English model."""
    query = (query or "").strip()
    if not query:
        return True
    if query in (car_name or ""):
        return True
    return query.casefold() in english_model(car_name).casefold()


def _demo() -> None:
    cases = {
        "アルファード": "Alphard",
        "ヴェルファイアHEV": "Vellfire Hybrid",
        "ノア": "Noah",
        "プリウスPHV(～’23.2)": "Prius Plug-in Hybrid (until Feb 2023)",
        "カローラフィールダーHEV(’17.10～)": "Corolla Fielder Hybrid (from Oct 2017)",
        "クラウン(スポーツ)": "Crown (Sport)",
        "MIRAI(’20.12～)": "MIRAI (from Dec 2020)",
        "ランドクルーザープラド": "Land Cruiser Prado",
        "ハイエースグランドキャビン": "Hiace Grand Cabin",
        "ヤリスクロス": "Yaris Cross",
        "RX HV": "RX Hybrid",
        "bZ4X": "bZ4X",
    }
    for raw, want in cases.items():
        got = english_model(raw)
        assert got == want, f"{raw!r}: got {got!r}, want {want!r}"
    assert model_matches("Alphard", "アルファードHEV('23.6～)")
    assert not model_matches("Noah", "アルファード")
    print(f"fleet: {len(cases)} cases OK")


if __name__ == "__main__":
    _demo()
