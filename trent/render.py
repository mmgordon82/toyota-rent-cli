"""Rich console output: English-forward tables, headings and JSON.

All output goes through a single rich ``Console`` — nothing is written to
``sys.stdout`` directly, so ``--json`` is emitted with ``console.print_json``
and reads as plain JSON when piped.
"""

from __future__ import annotations

import json

from rich import box
from rich.console import Console
from rich.table import Table

from trent.api import fetch_master, fmt_stamp, shop_id, stock_count
from trent.fleet import car_label, english_model, model_matches
from trent.translate import (
    PRICE_NAMES,
    SMOKE,
    TIER_NAMES,
    TRANSMISSION,
    VEHICLE_GROUPS,
    show_label,
    show_pref,
    show_store,
)

console = Console(highlight=False)


# --- scalars ----------------------------------------------------------------


def amount(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def yen(value) -> str:
    text = amount(value)
    return text if text == str(value) else f"{text} yen"


def when_span(start: str, end: str) -> str:
    return f"{fmt_stamp(start)} → {fmt_stamp(end)}"


# --- output primitives ------------------------------------------------------


def show(renderable) -> None:
    console.print(renderable)


def print_json(payload) -> None:
    console.print_json(json.dumps(payload, ensure_ascii=False, default=str))


def new_table(title: str | None = None) -> Table:
    return Table(
        title=title,
        title_justify="left",
        caption_justify="left",
        box=box.SIMPLE_HEAD,
        expand=False,
        header_style="bold",
    )


def with_note(table: Table, note: str) -> Table:
    table.caption = f"{note}\n{table.caption}" if table.caption else note
    return table


# --- store / class labels ---------------------------------------------------


def shop_place(store: dict) -> str:
    name = show_store(store)
    pref = show_pref(store.get("prefName") or "")
    if pref and name and pref.lower() not in name.lower():
        return f"{name}, {pref}"
    return name or pref


def center_line(label: str, km: float) -> str:
    return f"{show_label(label)}, within {km:g} km"


def _base_model(english: str) -> str:
    base = english.split(" (")[0]
    return base.replace(" Plug-in Hybrid", "").replace(" Hybrid", "").strip()


def class_summaries() -> dict[str, tuple[str, list[str]]]:
    """Class code → (English category, up to 3 example models). Best effort."""
    try:
        master = fetch_master()
    except Exception:
        return {}
    groups = {
        g.get("topGroupNo"): g.get("topGroupNoName")
        for g in master.get("topGroups") or []
    }
    out: dict[str, tuple[str, list[str]]] = {}
    for cls in master.get("classCodes") or []:
        code = (cls.get("classCode") or "").strip()
        category = VEHICLE_GROUPS.get(groups.get(cls.get("topGroupNo")), "")
        models: list[str] = []
        for car in cls.get("cars") or []:
            if str(car.get("carListFlg")) != "1":
                continue
            base = _base_model(english_model(car.get("carName") or ""))
            if base and base not in models:
                models.append(base)
            if len(models) >= 3:
                break
        out[code] = (category, models)
    return out


def class_label(code: str) -> str:
    """'W3 — Wagon (Alphard, Vellfire)', or just the code if master is down."""
    code = (code or "").strip()
    category, models = class_summaries().get(code, ("", []))
    detail = category
    if models:
        detail = f"{category} ({', '.join(models)})" if category else ", ".join(models)
    return f"{code} — {detail}" if detail else code


def conditions_line(args) -> str:
    bits = [
        SMOKE.get(str(args.smoke), str(args.smoke)),
        TRANSMISSION.get(str(args.transmission), str(args.transmission)),
    ]
    if str(args.drive) == "1":
        bits.append("4WD")
    count = getattr(args, "num", 1)
    bits.append(f"{count} vehicle" + ("" if count == 1 else "s"))
    return " · ".join(bits)


def shop_heading(store, start, end, args=None, class_code=None) -> str:
    bits = [f"{shop_place(store)}  {shop_id(store)}", when_span(start, end)]
    if class_code:
        bits.append(class_label(class_code))
    if args is not None:
        bits.append(conditions_line(args))
    return "   ".join(bits)


def route_title(origin, target, start, end, args=None, class_code=None) -> str:
    bits = [f"{shop_place(origin)} → {shop_place(target)}", when_span(start, end)]
    if class_code:
        bits.append(class_label(class_code))
    if args is not None:
        bits.append(conditions_line(args))
    return "   ".join(bits)


# --- car / price shaping ----------------------------------------------------


def cars_in_stock(data: dict, name: str | None = None) -> list[dict]:
    cars = []
    for car in data.get("carList") or []:
        if stock_count(car) <= 0:
            continue
        if name and not model_matches(name, car.get("carName") or ""):
            continue
        cars.append(car)
    return cars


def car_bits(cars: list[dict]) -> str:
    return ", ".join(f"{car_label(car)} ×{stock_count(car)}" for car in cars)


def _assign_prices(rows: list) -> str:
    return ", ".join(
        f"{yen(row.get('price'))} {PRICE_NAMES.get(row.get('priceName') or '', '')}".strip()
        for row in rows
    )


def price_pair(rows: list) -> tuple[str, str]:
    found = {str(row.get("carAssign")): row.get("price") for row in rows}
    if "0" in found or "1" in found:
        any_price = amount(found["0"]) if "0" in found else ""
        specific = amount(found["1"]) if "1" in found else ""
        return any_price, specific
    return _assign_prices(rows), ""


def any_model_price(data: dict) -> str:
    for row in data.get("general") or []:
        if str(row.get("carAssign")) == "0":
            return amount(row.get("price"))
    return ""


def format_oneway(data: dict) -> str:
    key = str(data.get("key") or "")
    message = data.get("message")
    if key == "SUCCESS" and not message:
        return "One-way allowed"
    if message:
        return f"One-way {key}: {message}".strip()
    if key:
        return f"One-way {key}"
    return "One-way " + json.dumps(data, ensure_ascii=False)


# --- tables -----------------------------------------------------------------


def stores_table(
    stores: list[dict], distances: dict[str, float], title: str | None = None
) -> Table:
    table = new_table(title or "Stores")
    if distances:
        table.add_column("km", justify="right")
    table.add_column("Code")
    table.add_column("Store", overflow="fold")
    table.add_column("Phone")
    for store in stores:
        cells = []
        if distances:
            dist = distances.get(shop_id(store))
            cells.append("" if dist is None else f"{dist:.1f}")
        cells.extend([shop_id(store), shop_place(store), store.get("tel") or ""])
        table.add_row(*cells)
    table.caption = f"{len(stores)} store" + ("" if len(stores) == 1 else "s")
    return table


def cars_table(cars: list[dict], title: str | None = None) -> Table:
    table = new_table(title or "Vehicles")
    table.add_column("Code")
    table.add_column("Model", overflow="fold")
    table.add_column("In stock", justify="right")
    missing = []
    for car in cars:
        count = stock_count(car)
        label = car_label(car)
        if count > 0:
            table.add_row(str(car.get("carCode") or "").strip(), label, str(count))
        elif label and label not in missing:
            missing.append(label)
    if missing:
        table.caption = "Out of stock: " + ", ".join(missing)
    elif table.row_count == 0:
        table.caption = "No vehicles"
    return table


def classes_table(groups: list[dict], title: str | None = None) -> Table:
    # getStock here is a stock check, not a trip total. Totals come from prices.
    summaries = class_summaries()
    table = new_table(title or "Classes")
    table.add_column("Class")
    table.add_column("Category")
    table.add_column("Example models", overflow="fold")
    table.add_column("Stock", justify="right")
    for group in groups:
        for row in group.get("classResult") or []:
            code = str(row.get("classCode") or "")
            category, models = summaries.get(code.strip(), ("", []))
            count = stock_count(row)
            table.add_row(
                code, category, ", ".join(models), str(count) if count else "none"
            )
    if table.row_count == 0:
        table.caption = "No classes"
    return table


def prices_table(data: dict, title: str | None = None) -> Table:
    table = new_table(title or "Prices")
    table.add_column("Rate")
    table.add_column("Any model (yen)", justify="right")
    table.add_column("Chosen model (yen)", justify="right")
    for tier in ("general", "member", "goldMember"):
        rows = data.get(tier) or []
        if not rows:
            continue
        any_price, specific = price_pair(rows)
        table.add_row(TIER_NAMES.get(tier, tier), any_price, specific)
    if table.row_count == 0:
        table.caption = "No prices"
    return table


def hits_table(
    found: list, distances: dict[str, float], title: str | None = None
) -> Table:
    table = new_table(title or "Available")
    if distances:
        table.add_column("km", justify="right")
    table.add_column("Code")
    table.add_column("Store", overflow="fold")
    table.add_column("Available vehicles", overflow="fold")
    table.add_column("From (yen)", justify="right")
    for store, data, cars in found:
        cells = []
        if distances:
            dist = distances.get(shop_id(store))
            cells.append("" if dist is None else f"{dist:.1f}")
        cells.extend(
            [shop_id(store), shop_place(store), car_bits(cars), any_model_price(data)]
        )
        table.add_row(*cells)
    return table


def errors_table(errors: list[tuple[dict, str]]) -> Table:
    table = new_table("Errors")
    table.add_column("Code")
    table.add_column("Store", overflow="fold")
    table.add_column("Problem", overflow="fold")
    for store, err in errors:
        table.add_row(shop_id(store), shop_place(store), err)
    return table


def returns_table(
    rows: list[tuple[dict, dict | None, bool, str | None]],
    distances: dict[str, float],
    title: str | None = None,
) -> Table:
    """One row per candidate return store: one-way status and drop-off price.

    ``rows`` is (store, stock_data_or_None, oneway_allowed, error_or_None).
    """
    table = new_table(title or "Return options")
    if distances:
        table.add_column("km", justify="right")
    table.add_column("Return store", overflow="fold")
    table.add_column("Code")
    table.add_column("One-way")
    table.add_column("From (yen)", justify="right")
    for store, data, allowed, err in rows:
        cells = []
        if distances:
            dist = distances.get(shop_id(store))
            cells.append("" if dist is None else f"{dist:.1f}")
        oneway = "blocked" if err else ("yes" if allowed else "no")
        price = "—" if err or not data else (any_model_price(data) or "—")
        cells.extend([shop_place(store), shop_id(store), oneway, price])
        table.add_row(*cells)
    return table
