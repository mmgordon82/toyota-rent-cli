<p align="center">
  <img src="docs/logo.svg" alt="Toyota Rent CLI" width="780">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/output-Rich-FFD43B?logo=windowsterminal&logoColor=black" alt="Rich output">
  <img src="https://img.shields.io/badge/mode-read--only-2ea44f" alt="Read-only">
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

## Examples

Stores within 5 km of Shin-Osaka:

```bash
python toyota_rent.py stores --near Shin-Osaka --km 5
```

What a store has in the W3 (Alphard) class for a date range:

```bash
python toyota_rent.py vehicles --shop 65301/026 --class W3 \
  --start 2026-11-10T14:00 --end 2026-11-22T19:30
```

```console
  Code   Model                      In stock
  CE     Alphard (from Jun 2023)           4
  L2     Alphard (until May 2023)          2

  Rate       Any model (yen)   Chosen model (yen)
  Standard           251,020              257,620
  Member             225,918              232,518
  Gold               200,816              207,416
```

Scan one class across stores near a place, keeping only one model:

```bash
python toyota_rent.py availability --near Okayama --km 100 --class W3 --name Alphard \
  --start 2026-11-10T14:00 --end 2026-11-22T19:30
```

A one-way trip, with prices and whether one-way is allowed:

```bash
python toyota_rent.py route --origin Shin-Osaka --target 63601/046 --class W3 \
  --start 2026-11-10T14:00 --end 2026-11-22T19:30
```

Pipe JSON to `jq`:

```bash
python toyota_rent.py prices --origin 65301/026 --target 63601/046 --class W3 \
  --start 2026-11-10T14:00 --end 2026-11-22T19:30 --json | jq '.general'
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
- **Unofficial**, and not affiliated with or endorsed by Toyota. The API key in `trent/api.py` is the client key shipped inside the public Android app, not an account credential.
- English for names without an explicit mapping is best-effort romanization, so an unusual store name can come out approximate.

## License

MIT — see [LICENSE](LICENSE).
