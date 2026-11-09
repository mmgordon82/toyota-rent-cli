<p align="center">
  <img src="https://rent.toyota.co.jp/global/common/fb_img.png" alt="Toyota Rent a Car" width="150">
</p>

<h1 align="center">Toyota Rent CLI</h1>

<p align="center"><em>Unofficial client — not affiliated with or endorsed by Toyota.</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/output-Rich-FFD43B?logo=windowsterminal&logoColor=black" alt="Rich output">
  <img src="https://img.shields.io/badge/booking-never-c70715" alt="No booking">
  <img src="https://img.shields.io/badge/status-unofficial-8957e5" alt="Unofficial">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License">
</p>

Toyota's rental app and its API only speak Japanese. This command-line client reads the same JSON API and prints stores, car models, classes, and prices in English, so you can check availability and one-way pricing without parsing kanji. It never logs in and never books — every command is a read.

```console
$ python toyota_rent.py returns --origin 65301/026 --near 63601/046 --km 15 --class W3 --name Alphard \
    --start 2026-11-11T14:00 --end 2026-11-22T19:30

Pickup Shin-Osaka Shinkansen Exit  65301/026   2026-11-11 14:00 → 2026-11-22 19:30   W3 — Wagon (Alphard, Vellfire)
63601/046 Haneda Airport (Domestic), within 15 km

   km   Return store                      Code        One-way   From (yen)
  0.0   Haneda Airport (Domestic), Tokyo  63601/046   yes          232,320
  0.3   Haneda Airport (International)     63601/06V   yes          232,320
  5.2   Kawasaki, Kanagawa                63701/002   yes          232,320
  7.4   Tsurumi Station, Kanagawa         63701/012   no           232,320
 ...
23 of 29 stores accept the one-way
Class W3 stock at Shin-Osaka Shinkansen Exit: Alphard (from Jun 2023) ×4, Alphard (until May 2023) ×2
```

## What it does

- Finds stores by English name, romaji, or Japanese, and by distance from a city, prefecture, or another store.
- Shows what a given class has in stock at one store, or scans one class across every store near a place.
- Lists the one-way return stores that will accept a car from a fixed pickup, with the drop-off price for each.
- Prints standard, member, and gold prices for a class on a route.
- Renders car models in English (`アルファード` → `Alphard`), labels bare class codes (`W3` → `Wagon (Alphard, Vellfire)`), and formats money as yen.
- Adds `--json` to every command, clean on stdout for piping to `jq` (logs and errors go to stderr).

## How the English works

The API has no English locale — it sends `Content-Language: jp` on every request (confirmed in the decompiled app), so the translation happens on the client:

- **Places** resolve through [`jp-prefecture`](https://pypi.org/project/jp-prefecture/); store names are romanized with [`pykakasi`](https://pypi.org/project/pykakasi/) plus a small table of recurring name pieces (`駅` → Station, `空港` → Airport, `新幹線口` → Shinkansen Exit).
- **Car models** use a hand-checked Japanese→English nameplate map, because phonetic transliteration gets them wrong: `アルファード` comes out as "Arufado", not "Alphard". The map covers the full rental fleet exposed by the app's master data; Latin names like `MIRAI` and `RAV4` pass through.
- **Classes and conditions** (`W3`, non-smoking, automatic, 4WD) are labelled from the app's own `getAppMaster` tables.

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/mmgordon82/toyota-rent-cli
cd toyota-rent-cli
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python toyota_rent.py --help
```

`python -m trent` runs the same CLI.

## Commands

| Command | Purpose |
| --- | --- |
| `stores` | find rental stores by name, or near a city / prefecture / store |
| `vehicles` | what one class has in stock at a single store (pickup = return) |
| `route` | a one-way trip between two stores, with stock and prices |
| `availability` | scan one class across many stores at once |
| `returns` | where a one-way car from a fixed pickup can be dropped off |
| `prices` | standard, member, and gold prices for one class on a route |

### Input formats

- **Stores** accept a code (`65301/026`), a store name, or a place name, in English, romaji, or Japanese (`Okayama`, `Shin-Osaka`, `岡山`).
- **Dates** accept `2026-11-10T14:00`, `2026-11-10 14:00`, or `202611101400`.
- **Classes** are codes such as `W3`. Run `vehicles` with no `--class` to list them with their English categories.
- **Conditions** apply to any stock query: `--smoke` (1 non-smoking, 2 smoking), `--transmission` (1 automatic, 2 manual), `--drive` (0 any, 1 four-wheel drive), `--num` (vehicles).

## Examples

Every command takes `--json` for machine-readable output. The examples below show the default Rich tables, trimmed where long.

### `stores` — find a store

By name, in English, romaji, or Japanese (`--keyword 岡山` returns the same six):

```bash
python toyota_rent.py stores --keyword Okayama
```

```console
  Code        Store                             Phone
  66302/003   Okayamakume                       0120-07-6633
  66301/002   Okayama Airport                   086-294-2100
  66302/001   Okayama Station                   0120-09-6633
  66301/010   Okayama Station West Exit         086-254-0100
  66301/020   Okayama Station West Exit Plaza   0120-55-6600
  66302/004   Higashi Okayama                   0120-48-6633
6 stores
```

Within a radius of a point, nearest first. The center can be a store code (shown here), a city, or a prefecture:

```bash
python toyota_rent.py stores --near 63601/046 --km 4
```

```console
63601/046 Haneda Airport (Domestic), within 4 km
   km   Code        Store                                  Phone
  0.0   63601/046   Haneda Airport (Domestic), Tokyo       03-3744-0100
  0.3   63601/06V   Haneda Airport (International), Tokyo   03-5737-8100
2 stores
```

Everything in a prefecture (`--pref 33` selects the same one by code):

```bash
python toyota_rent.py stores --pref Okayama
```

```console
  Code        Store                 Phone
  66302/003   Okayamakume           0120-07-6633
  66301/002   Okayama Airport       086-294-2100
  66302/001   Okayama Station       0120-09-6633
  ...
```

As JSON — the raw rows keep the Japanese names, which is what the API returns:

```bash
python toyota_rent.py stores --keyword Haneda --json | jq -r '.[] | "\(.storeRCode)/\(.storeCode)  \(.storeName)"'
```

```console
63601/06V  羽田空港（国際線）
63601/046  羽田空港（国内線）
```

### `vehicles` — stock at one store

Omit `--class` to list every class with its English category, example models, and current stock. Useful when you know the store but not which class you want:

```bash
python toyota_rent.py vehicles --shop 65301/026 \
  --start 2026-11-11T14:00 --end 2026-11-22T19:30
```

```console
Shin-Osaka Shinkansen Exit  65301/026   2026-11-11 14:00 → 2026-11-22 19:30   Non-smoking · Automatic · 1 vehicle
  Class   Category      Example models                            Stock
  C1      Compact       Yaris, Vitz, Passo                          277
  C3      Sedan         Corolla, Corolla Touring, Corolla Sport      45
  C5      Sedan         Crown, Crown Crossover                        2
  W1      Wagon         Sienta, Prius α                              18
  W2      Wagon         Esquire, Noah, Voxy                           2
  W3      Wagon         Alphard, Vellfire                            10
  SUV1    SUV           Raize, Yaris Cross                            3
  SUV3    SUV           Harrier, RAV4                                 5
  SUV4    SUV           Land Cruiser "250", Land Cruiser Prado        1
  SP1     Specialty     86, GR86, GR Yaris                            3
  ...
```

Add `--class` to see the individual models in stock and the trip price:

```bash
python toyota_rent.py vehicles --shop 65301/026 --class W3 \
  --start 2026-11-11T14:00 --end 2026-11-22T19:30
```

```console
  Code   Model                             In stock
  CE     Alphard (from Jun 2023)                  5
  L2     Alphard (until May 2023)                 4
  L3     Alphard Hybrid (until May 2023)          1
Out of stock: Vellfire (from Jun 2023), Vellfire (until May 2023), Alphard Hybrid (from Jan 2025), ...

  Rate       Any model (yen)   Chosen model (yen)
  Standard           232,320              238,920
  Member             209,088              215,688
  Gold               185,856              192,456
```

A manual compact instead, at an airport store: `--class C1 --transmission 2`.

### `route` — a one-way trip

One class between two stores, with the one-way verdict under the stock table:

```bash
python toyota_rent.py route --origin Shin-Osaka --target 63601/046 --class W3 \
  --start 2026-11-11T14:00 --end 2026-11-22T19:30
```

```console
Shin-Osaka Shinkansen Exit → Haneda Airport (Domestic), Tokyo   2026-11-11 14:00 → 2026-11-22 19:30   W3 — Wagon (Alphard, Vellfire)
  Code   Model                      In stock
  CE     Alphard (from Jun 2023)           4
  L2     Alphard (until May 2023)          2
One-way allowed
```

Omit `--class` to see which classes have anything for the trip at all:

```bash
python toyota_rent.py route --origin 65301/026 --target 63601/046 \
  --start 2026-11-11T14:00 --end 2026-11-22T19:30
```

```console
  Class   Category   Example models                            Stock
  C1      Compact    Yaris, Vitz, Passo                          236
  C3      Sedan      Corolla, Corolla Touring, Corolla Sport      32
  W3      Wagon      Alphard, Vellfire                             6
  SUV3    SUV        Harrier, RAV4                                 1
  ...
```

### `availability` — scan a class across stores

Find every store near a place that has a specific model for your dates. Here, Alphards within 10 km of Haneda (pickup and return at each store):

```bash
python toyota_rent.py availability --near 63601/046 --km 10 --class W3 --name Alphard \
  --start 2026-11-11T14:00 --end 2026-11-22T19:30
```

```console
63601/046 Haneda Airport (Domestic), within 10 km
    km   Code        Store                   Available vehicles                          From (yen)
   4.6   63702/008   Kawasakishinkawabashi   Alphard (until May 2023) ×2, Alphard …         232,320
   4.9   63702/025   Kawasaki Endo Town      Alphard (until May 2023) ×2, Alphard …         232,320
   7.5   63702/039   Tsurumimikado           Alphard (until May 2023) ×1                     232,320
 ...
```

With `--target`, hold the return store fixed and scan many pickups instead — "which store near Shin-Osaka can start a one-way to Haneda?":

```bash
python toyota_rent.py availability --near 65301/026 --km 6 --class W3 --target 63601/046 \
  --start 2026-11-11T14:00 --end 2026-11-22T19:30
```

```console
Checking 24 stores → 63601/046 Haneda Airport (Domestic)
65301/026 Shin-Osaka Shinkansen Exit, within 6 km
   km   Code        Store                   Available vehicles                          From (yen)
  0.0   65301/026   Shin-Osaka Shinkansen   Alphard (from Jun 2023) ×4, Alphard …          232,320
  0.5   65301/059   Shin-Osaka Station      Alphard (from Jun 2023) ×3, Alphard …          232,320
  0.8   65301/011   Shinosaka               Alphard (from Jun 2023) ×3, Alphard …          232,320
 ...
```

### `returns` — where a one-way car can go

The inverse of `availability`: fix the pickup, scan return stores, and report whether each accepts the one-way and at what drop-off price. Stock comes from the pickup store, so what changes per row is the one-way verdict and the price.

Around an airport, filtered to one model:

```bash
python toyota_rent.py returns --origin 65301/026 --near 63601/046 --km 15 --class W3 --name Alphard \
  --start 2026-11-11T14:00 --end 2026-11-22T19:30
```

```console
Pickup Shin-Osaka Shinkansen Exit  65301/026   ...   W3 — Wagon (Alphard, Vellfire)
63601/046 Haneda Airport (Domestic), within 15 km
   km   Return store                      Code        One-way   From (yen)
  0.0   Haneda Airport (Domestic), Tokyo  63601/046   yes          232,320
  5.2   Kawasaki, Kanagawa                63701/002   yes          232,320
  7.4   Tsurumi Station, Kanagawa         63701/012   no           232,320
 ...
23 of 29 stores accept the one-way
Class W3 stock at Shin-Osaka Shinkansen Exit: Alphard (from Jun 2023) ×4, Alphard (until May 2023) ×2
```

Or by name instead of a radius — every return store whose name matches `Yokohama`:

```bash
python toyota_rent.py returns --origin 65301/026 --keyword Yokohama --class W3 \
  --start 2026-11-11T14:00 --end 2026-11-22T19:30
```

```console
  Return store                                Code        One-way   From (yen)
  Yokohamaeki Chuo West Exit, Kanagawa        63701/027   yes          232,320
  Yokohamaminatomirai, Kanagawa               63701/072   yes          232,320
  Shinyokohama Shinkansen Exit, Kanagawa      63702/035   yes          232,320
 ...
5 of 5 stores accept the one-way
```

### `prices` — standard / member / gold

The three price tiers for one class on a route, each with the "any model in the class" rate and the "pick a specific model" rate:

```bash
python toyota_rent.py prices --origin 65301/026 --target 63601/046 --class W3 \
  --start 2026-11-11T14:00 --end 2026-11-22T19:30
```

```console
  Rate       Any model (yen)   Chosen model (yen)
  Standard           232,320              238,920
  Member             209,088              215,688
  Gold               185,856              192,456
```

The same numbers as JSON, for a spreadsheet or a script:

```bash
python toyota_rent.py prices --origin 65301/026 --target 63601/046 --class W3 \
  --start 2026-11-11T14:00 --end 2026-11-22T19:30 --json | jq '.general'
```

```console
[
  { "carAssign": "0", "priceName": "車種おまかせ", "price": "232320", ... },
  { "carAssign": "1", "priceName": "車種指定",     "price": "238920", ... }
]
```

## Layout

```
toyota_rent.py       launcher (python toyota_rent.py …)
trent/
  api.py             HTTP, endpoints, caching
  fleet.py           Japanese → English car nameplates (+ self-check)
  translate.py       place names and labels → English
  search.py          store/place resolution, fuzzy matching, geo
  render.py          Rich tables, headings, JSON output
  cli.py             argument parsing and commands
```

Run the fleet self-check with `python -m trent.fleet`.

## Notes

- **Read-only.** The client calls store, master, and stock endpoints only. There is no login or booking path.
- **Unofficial**, and not affiliated with or endorsed by Toyota. The logo above is Toyota's, linked from their site to identify the service this tool talks to. The API key in `trent/api.py` is the client key shipped inside the public Android app, not an account credential.
- English for names without an explicit mapping is best-effort romanization, so an unusual store name can come out approximate.

## License

MIT — see [LICENSE](LICENSE).
