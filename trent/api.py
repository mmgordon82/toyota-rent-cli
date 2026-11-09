"""HTTP access to the Toyota Rent-a-Car app API. Read-only: no login, no booking.

The client key below ships inside the Android app; it is not an account
credential. Every request is sent with ``Content-Language: jp`` because the API
only speaks Japanese — English is produced on the client (see ``translate`` and
``fleet``).
"""

from __future__ import annotations

import re
from functools import lru_cache

import requests

BASE = "https://rent.toyota.co.jp/TrentApp/app/api/v1/"
API_KEY = "oxhbengie6gd37tg"
TIMEOUT = 90
SHOP_CODE = re.compile(r"^(\d{5})/([0-9A-Za-z]{2,4})$")
PRICE_TIERS = ("general", "member", "goldMember")


class ApiError(Exception):
    """Any failure talking to the API, or a business error it returned."""


SESSION = requests.Session()
SESSION.headers.update(
    {
        "X-TRent-Api-Key": API_KEY,
        "Content-Language": "jp",
        "User-Agent": "ToyoRenta/1.6.12",
    }
)


# --- store-dict shape helpers (the API's row shape, used everywhere) ---------


def shop_id(store: dict) -> str:
    return f"{store.get('storeRCode')}/{store.get('storeCode')}"


def store_point(store: dict) -> tuple[float, float] | None:
    try:
        return float(store["latitude"]), float(store["longitude"])
    except (KeyError, TypeError, ValueError):
        return None


def stock_count(row: dict) -> int:
    try:
        return int(row.get("stock") or 0)
    except (TypeError, ValueError):
        return 0


def selectable(store: dict) -> bool:
    return str(store.get("noSelectFlg") or "0") != "1"


# --- request plumbing -------------------------------------------------------


def fmt_stamp(value: str | None) -> str:
    """12-digit YYYYMMDDHHMM → 'YYYY-MM-DD HH:MM'; anything else unchanged."""
    text = str(value or "")
    if len(text) != 12 or not text.isdigit():
        return text
    return f"{text[0:4]}-{text[4:6]}-{text[6:8]} {text[8:10]}:{text[10:12]}"


def api_error_text(path: str, body: dict, fields: dict | None) -> str:
    kind = str(body.get("type") or "")
    if kind == "CLOSED_OUT":
        names = [
            item.get("name")
            for item in (body.get("invalid_params") or [])
            if isinstance(item, dict)
        ]
        fields = fields or {}
        if "returnDateTime" in names and "startDateTime" not in names:
            what, stamp = "return", fmt_stamp(fields.get("returnDateTime"))
        else:
            what, stamp = "departure", fmt_stamp(fields.get("startDateTime"))
        when = f" {stamp}" if stamp else ""
        return (
            f"Reservations for this {what}{when} are closed. "
            "The store has passed its booking cutoff — try a different time."
        )
    status = body.get("status")
    if kind:
        return f"{path} rejected the request ({kind}, status {status})."
    message = body.get("message")
    return f"{path} status {status}: {message or body}"


def post(path: str, fields: dict | None = None) -> dict:
    data = {k: v for k, v in (fields or {}).items() if v is not None}
    try:
        resp = SESSION.post(BASE + path, data=data, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ApiError(f"{path}: {exc}") from exc
    if resp.status_code not in (200, 400):
        raise ApiError(f"{path} HTTP {resp.status_code}: {resp.text[:300]!r}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise ApiError(f"{path}: not JSON ({resp.text[:200]!r})") from exc
    if str(body.get("status")) != "1":
        raise ApiError(api_error_text(path, body, data))
    return body


# --- endpoints --------------------------------------------------------------


def fetch_all_stores(mode: str = "1") -> list[dict]:
    """Every store from store/getAllStore."""
    stores = post("store/getAllStore", {"mode": mode}).get("data", {}).get("stores")
    if not isinstance(stores, list):
        raise ApiError("getAllStore returned no stores list")
    return stores


@lru_cache(maxsize=1)
def fetch_master() -> dict:
    """App master data (classes, areas, label tables). Cached per run."""
    data = post("common/getAppMaster").get("data")
    if not isinstance(data, dict):
        raise ApiError("getAppMaster returned no data")
    return data


def fetch_classes() -> list[dict]:
    classes = fetch_master().get("classCodes")
    if not isinstance(classes, list):
        raise ApiError("getAppMaster returned no classCodes")
    return classes


def fetch_places() -> list[dict]:
    """Prefecture and town pins from getAppMaster areaList."""
    places = []
    for area in fetch_master().get("areaList") or []:
        places.append(
            {
                "name": area.get("perfName") or "",
                "kind": "prefecture",
                "code": area.get("prefCode"),
                "latitude": area.get("latitude"),
                "longitude": area.get("longitude"),
            }
        )
        for town in area.get("localTowns") or []:
            places.append(
                {
                    "name": town.get("name") or "",
                    "kind": "town",
                    "code": town.get("code"),
                    "latitude": town.get("latitude"),
                    "longitude": town.get("longitude"),
                    "pref": area.get("perfName") or "",
                }
            )
    return places


# --- stock / availability ---------------------------------------------------


def stock_fields(origin: dict, target: dict, start: str, end: str, args) -> dict:
    # smoke 1 is 禁煙 (non-smoking); it reproduced the website's non-smoking quote.
    return {
        "startDateTime": start,
        "startRStore": origin["storeRCode"],
        "startStore": origin["storeCode"],
        "returnDateTime": end,
        "returnRStore": target["storeRCode"],
        "returnStore": target["storeCode"],
        "smoke": args.smoke,
        "transmission": args.transmission,
        "drive": args.drive,
        "carConditionStudLess": "0",
        "num": str(args.num),
    }


def stock_by_class(origin, target, start, end, class_code: str, args) -> dict:
    fields = stock_fields(origin, target, start, end, args)
    fields["classCode"] = class_code
    fields["welcabType"] = "0"
    return post("reserve/getStockByClass", fields).get("data") or {}


def stock_by_group(origin, target, start, end, group_no: str, args) -> dict:
    fields = stock_fields(origin, target, start, end, args)
    fields["groupNo"] = group_no
    return post("reserve/getStock", fields).get("data") or {}


def oneway_status(origin, target, start, end) -> dict:
    return (
        post(
            "reserve/getOnewayStatus",
            {
                "startRStore": origin["storeRCode"],
                "startStore": origin["storeCode"],
                "returnRStore": target["storeRCode"],
                "returnStore": target["storeCode"],
                "startDateTime": start,
                "returnDateTime": end,
            },
        ).get("data")
        or {}
    )
