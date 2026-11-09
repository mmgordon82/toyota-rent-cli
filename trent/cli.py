"""Command-line interface for the Toyota Rent-a-Car client. Read-only.

Stores, dates and classes accept friendly input:
  stores     a code (65301/026), a store name, or a place (Okayama, Shin-Osaka)
  dates      2026-11-10T14:00, 2026-11-10 14:00, or 202611101400
  classes    a class code such as W3 (see `vehicles` with no --class for a list)
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from rich.console import Console
from rich.logging import RichHandler

from trent.api import (
    ApiError,
    fetch_all_stores,
    fetch_classes,
    fetch_places,
    oneway_status,
    selectable,
    shop_id,
    stock_by_class,
    stock_by_group,
)
from trent.render import (
    any_model_price,
    car_bits,
    cars_in_stock,
    cars_table,
    center_line,
    classes_table,
    errors_table,
    format_oneway,
    hits_table,
    prices_table,
    print_json,
    returns_table,
    route_title,
    shop_heading,
    shop_place,
    show,
    stores_table,
    with_note,
)
from trent.search import (
    filter_stores,
    name_miss,
    nearby_stores,
    place_choices,
    resolve_shop,
    store_choices,
)
from trent.translate import show_store

EXAMPLES = """\
examples:
  toyota_rent stores --keyword Okayama
  toyota_rent stores --near Okayama --km 100
  toyota_rent vehicles --shop 65301/026 --class W3 --start 2026-11-10T14:00 --end 2026-11-22T19:30
  toyota_rent route --origin Shin-Osaka --target 63601/046 --class W3 --start 2026-11-10T14:00 --end 2026-11-22T19:30
  toyota_rent availability --near Okayama --km 100 --class W3 --name Alphard --start 2026-11-10T14:00 --end 2026-11-22T19:30
  toyota_rent returns --origin 65301/026 --near 63601/046 --km 15 --class W3 --name Alphard --start 2026-11-11T14:00 --end 2026-11-22T19:30
  toyota_rent prices --origin 65301/026 --target 63601/046 --class W3 --start 2026-11-10T14:00 --end 2026-11-22T19:30
"""

log = logging.getLogger("toyota_rent")


def configure_logging() -> None:
    # Logs and errors go to stderr so --json on stdout stays clean for piping.
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=Console(stderr=True),
                show_path=False,
                markup=False,
                rich_tracebacks=False,
            )
        ],
    )


def parse_when(text: str) -> str:
    text = text.strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y%m%d%H%M")
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"use a date like 2026-11-10T14:00 or 202611101400, got {text!r}"
    )


# --- commands ---------------------------------------------------------------


def cmd_stores(args) -> None:
    stores = fetch_all_stores()
    distances: dict[str, float] = {}
    label = lat = lon = None
    if args.near:
        label, lat, lon, hits = nearby_stores(args, stores)
        stores = [store for store, _ in hits]
        distances = {shop_id(store): dist for store, dist in hits}
        title = center_line(label, args.km)
    else:
        title = "Stores"
    pool = stores
    stores = filter_stores(stores, args.keyword, args.pref)
    if not stores and args.keyword:
        raise name_miss(args.keyword, store_choices(pool))
    if not stores and args.pref:
        raise name_miss(args.pref, place_choices(fetch_places()))
    if args.near:
        stores.sort(key=lambda store: distances[shop_id(store)])
    if args.json:
        if args.near:
            rows = []
            for store in stores:
                row = dict(store)
                row["distanceKm"] = round(distances[shop_id(store)], 1)
                rows.append(row)
            print_json(
                {
                    "center": {"label": label, "latitude": lat, "longitude": lon},
                    "radiusKm": args.km,
                    "stores": rows,
                }
            )
        else:
            print_json(stores)
        return
    show(stores_table(stores, distances if args.near else {}, title))


def cmd_vehicles(args) -> None:
    stores = fetch_all_stores()
    shop = resolve_shop(args.shop, stores)
    if args.class_code:
        data = stock_by_class(shop, shop, args.start, args.end, args.class_code, args)
        if args.json:
            print_json({"shop": shop, "stock": data})
            return
        show(shop_heading(shop, args.start, args.end, args, args.class_code))
        show(cars_table(data.get("carList") or []))
        show(prices_table(data))
        return
    groups = sorted({c.get("topGroupNo") for c in fetch_classes() if c.get("topGroupNo")})
    results = [stock_by_group(shop, shop, args.start, args.end, g, args) for g in groups]
    if args.json:
        print_json({"shop": shop, "groups": results})
        return
    show(shop_heading(shop, args.start, args.end, args))
    show(classes_table(results))


def cmd_route(args) -> None:
    stores = fetch_all_stores()
    origin = resolve_shop(args.origin, stores)
    target = resolve_shop(args.target, stores)
    oneway = oneway_status(origin, target, args.start, args.end)
    if args.class_code:
        data = stock_by_class(origin, target, args.start, args.end, args.class_code, args)
        if args.json:
            print_json({"origin": origin, "target": target, "oneway": oneway, "stock": data})
            return
        show(route_title(origin, target, args.start, args.end, args, args.class_code))
        show(with_note(cars_table(data.get("carList") or []), format_oneway(oneway)))
        show(prices_table(data))
        return
    groups = sorted({c.get("topGroupNo") for c in fetch_classes() if c.get("topGroupNo")})
    results = [stock_by_group(origin, target, args.start, args.end, g, args) for g in groups]
    if args.json:
        print_json({"origin": origin, "target": target, "oneway": oneway, "groups": results})
        return
    show(route_title(origin, target, args.start, args.end, args))
    show(with_note(classes_table(results), format_oneway(oneway)))


def cmd_prices(args) -> None:
    stores = fetch_all_stores()
    origin = resolve_shop(args.origin, stores)
    target = resolve_shop(args.target, stores)
    data = stock_by_class(origin, target, args.start, args.end, args.class_code, args)
    if args.json:
        print_json({tier: data.get(tier) for tier in ("general", "member", "goldMember")})
        return
    show(route_title(origin, target, args.start, args.end, args, args.class_code))
    show(prices_table(data))


def _scan_one(store, target, args):
    dest = target if target is not None else store
    try:
        data = stock_by_class(store, dest, args.start, args.end, args.class_code, args)
        return store, data, None
    except ApiError as exc:
        return store, None, str(exc)


def cmd_availability(args) -> None:
    if not args.near and not args.target:
        raise ApiError("--target is required unless --near is set")
    all_stores = fetch_all_stores()
    stores = all_stores
    distances: dict[str, float] = {}
    title = "Available"
    if args.near:
        label, lat, lon, hits = nearby_stores(args, all_stores)
        distances = {shop_id(store): dist for store, dist in hits}
        stores = [store for store, _ in hits]
        title = center_line(label, args.km)
    target = resolve_shop(args.target, all_stores) if args.target else None
    origins = [s for s in filter_stores(stores, args.keyword, args.pref) if selectable(s)]
    if args.near:
        origins.sort(key=lambda store: distances[shop_id(store)])
    if not origins:
        if args.keyword:
            raise name_miss(args.keyword, store_choices(all_stores))
        if args.pref:
            raise name_miss(args.pref, place_choices(fetch_places()))
        raise ApiError("no stores match that filter")
    found = []
    empty = 0
    errors = []
    workers = min(max(args.workers, 1), len(origins))
    where = f"{shop_id(target)} {show_store(target)}" if target is not None else "the same store"
    log.info("Checking %s stores → %s", len(origins), where)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_scan_one, store, target, args) for store in origins]
        for done in as_completed(futures):
            store, data, err = done.result()
            if err:
                errors.append((store, err))
                continue
            cars = cars_in_stock(data, args.name)
            if cars:
                found.append((store, data, cars))
            else:
                empty += 1
    if args.near:
        found.sort(key=lambda item: distances[shop_id(item[0])])
    else:
        found.sort(key=lambda item: (item[0].get("prefName") or "", item[0].get("storeName") or ""))
    if args.json:
        print_json(
            {
                "center": title if args.near else None,
                "results": [
                    {
                        "shop": store,
                        "distanceKm": round(distances[shop_id(store)], 1)
                        if shop_id(store) in distances
                        else None,
                        "cars": cars,
                        "prices": {tier: data.get(tier) for tier in ("general", "member", "goldMember")},
                    }
                    for store, data, cars in found
                ],
            }
        )
        return
    summary = f"{len(found)} with stock, {empty} empty, {len(errors)} errors, {len(origins)} checked"
    if found:
        show(with_note(hits_table(found, distances, title), summary))
    else:
        show(title)
        show(summary)
    if errors:
        show(errors_table(errors))


# --- parser -----------------------------------------------------------------


def _scan_return(origin, target, args):
    try:
        data = stock_by_class(origin, target, args.start, args.end, args.class_code, args)
        allowed = (
            str(oneway_status(origin, target, args.start, args.end).get("key") or "")
            == "SUCCESS"
        )
        return target, data, allowed, None
    except ApiError as exc:
        return target, None, False, str(exc)


def cmd_returns(args) -> None:
    if not (args.near or args.keyword or args.pref):
        raise ApiError("choose return stores with --near (+ --km), --keyword, or --pref")
    all_stores = fetch_all_stores()
    origin = resolve_shop(args.origin, all_stores)
    stores = all_stores
    distances: dict[str, float] = {}
    title = "Return options"
    if args.near:
        label, lat, lon, hits = nearby_stores(args, all_stores)
        distances = {shop_id(store): dist for store, dist in hits}
        stores = [store for store, _ in hits]
        title = center_line(label, args.km)
    targets = [
        s
        for s in filter_stores(stores, args.keyword, args.pref)
        if selectable(s) and shop_id(s) != shop_id(origin)
    ]
    if args.near:
        targets.sort(key=lambda store: distances[shop_id(store)])
    if not targets:
        if args.keyword:
            raise name_miss(args.keyword, store_choices(all_stores))
        if args.pref:
            raise name_miss(args.pref, place_choices(fetch_places()))
        raise ApiError("no return stores match that filter")
    workers = min(max(args.workers, 1), len(targets))
    log.info("Checking %s return stores ← %s %s", len(targets), shop_id(origin), show_store(origin))
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_scan_return, origin, t, args) for t in targets]
        for done in as_completed(futures):
            target, data, allowed, err = done.result()
            results[shop_id(target)] = (target, data, allowed, err)
    rows = [results[shop_id(t)] for t in targets]  # keep the distance/name ordering
    origin_cars = next(
        (cars_in_stock(data, args.name) for _, data, _, err in rows if data and not err),
        [],
    )
    accepted = sum(1 for _, _, allowed, err in rows if allowed and not err)
    if args.json:
        print_json(
            {
                "origin": origin,
                "center": title if args.near else None,
                "classCode": args.class_code,
                "returns": [
                    {
                        "shop": store,
                        "distanceKm": round(distances[shop_id(store)], 1)
                        if shop_id(store) in distances
                        else None,
                        "oneway": allowed and not err,
                        "blocked": bool(err),
                        "price": None if err or not data else (any_model_price(data) or None),
                    }
                    for store, data, allowed, err in rows
                ],
            }
        )
        return
    note = f"{accepted} of {len(rows)} stores accept the one-way"
    show("Pickup " + shop_heading(origin, args.start, args.end, args, args.class_code))
    show(with_note(returns_table(rows, distances, title), note))
    stock = car_bits(origin_cars) if origin_cars else "none"
    show(f"Class {args.class_code} stock at {shop_place(origin)}: {stock}")


def add_when(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", required=True, type=parse_when, metavar="WHEN",
                        help="pick-up, e.g. 2026-11-10T14:00")
    parser.add_argument("--end", required=True, type=parse_when, metavar="WHEN",
                        help="return, e.g. 2026-11-22T19:30")


def add_conditions(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--smoke", default="1", choices=("1", "2"),
                        help="1 non-smoking (default), 2 smoking")
    parser.add_argument("--transmission", default="1", choices=("1", "2"),
                        help="1 automatic (default), 2 manual")
    parser.add_argument("--drive", default="0", choices=("0", "1"),
                        help="0 any (default), 1 four-wheel drive")
    parser.add_argument("--num", type=int, default=1, help="number of vehicles (default 1)")
    parser.add_argument("--json", action="store_true", help="print raw JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toyota_rent",
        description="Toyota Rent-a-Car stock and prices, in English. Read-only.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EXAMPLES,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    stores = sub.add_parser("stores", help="find rental stores")
    stores.add_argument("--keyword", help="store name, Japanese or romaji (e.g. Okayama, Shin-Osaka)")
    stores.add_argument("--pref", help="prefecture name, romaji, or prefecture code")
    stores.add_argument("--near", help="city, prefecture, or store to search around")
    stores.add_argument("--km", type=float, help="search radius in km (required with --near)")
    stores.add_argument("--json", action="store_true", help="print raw JSON")
    stores.set_defaults(func=cmd_stores)

    vehicles = sub.add_parser("vehicles", help="vehicles available at one store (pick-up = return)")
    vehicles.add_argument("--shop", required=True, help="store code or name")
    vehicles.add_argument("--class", dest="class_code", metavar="CODE",
                          help="class code, e.g. W3. Omit to list every class.")
    add_when(vehicles)
    add_conditions(vehicles)
    vehicles.set_defaults(func=cmd_vehicles)

    route = sub.add_parser("route", help="vehicles for a one-way trip (different return store)")
    route.add_argument("--origin", required=True, help="pick-up store code or name")
    route.add_argument("--target", required=True, help="return store code or name")
    route.add_argument("--class", dest="class_code", metavar="CODE", help="class code, e.g. W3")
    add_when(route)
    add_conditions(route)
    route.set_defaults(func=cmd_route)

    availability = sub.add_parser(
        "availability",
        help="scan one class across many stores (--target defaults to the same store with --near)",
    )
    availability.add_argument("--class", dest="class_code", required=True, metavar="CODE",
                              help="class code to scan, e.g. W3")
    availability.add_argument("--target", help="return store. Omit with --near to return to each store.")
    availability.add_argument("--near", help="city, prefecture, or store to search around")
    availability.add_argument("--km", type=float, help="search radius in km (required with --near)")
    availability.add_argument("--name", help="keep only this model, e.g. Alphard")
    availability.add_argument("--keyword", help="limit to stores matching this name")
    availability.add_argument("--pref", help="limit to this prefecture (name or code)")
    availability.add_argument("--workers", type=int, default=6, help="parallel requests (default 6)")
    add_when(availability)
    add_conditions(availability)
    availability.set_defaults(func=cmd_availability)

    returns = sub.add_parser(
        "returns",
        help="where a one-way car can be dropped off: scan return stores near a place",
    )
    returns.add_argument("--origin", required=True, help="pick-up store code or name")
    returns.add_argument("--class", dest="class_code", required=True, metavar="CODE",
                         help="class code, e.g. W3")
    returns.add_argument("--near", help="city, prefecture, or store to scan return stores around")
    returns.add_argument("--km", type=float, help="search radius in km (required with --near)")
    returns.add_argument("--name", help="require this model in stock at pick-up, e.g. Alphard")
    returns.add_argument("--keyword", help="limit return stores matching this name")
    returns.add_argument("--pref", help="limit return stores to this prefecture (name or code)")
    returns.add_argument("--workers", type=int, default=6, help="parallel requests (default 6)")
    add_when(returns)
    add_conditions(returns)
    returns.set_defaults(func=cmd_returns)

    prices = sub.add_parser("prices", help="standard, member, and gold prices for one class")
    prices.add_argument("--origin", required=True, help="pick-up store code or name")
    prices.add_argument("--target", required=True, help="return store code or name")
    prices.add_argument("--class", dest="class_code", required=True, metavar="CODE",
                        help="class code, e.g. W3")
    add_when(prices)
    add_conditions(prices)
    prices.set_defaults(func=cmd_prices)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except ApiError as exc:
        log.error("%s", exc)
        return 1
    return 0
