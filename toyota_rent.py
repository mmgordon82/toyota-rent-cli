#!/usr/bin/env python3
"""Launcher for the Toyota Rent-a-Car client. Logic lives in the trent/ package.

    python toyota_rent.py stores --keyword Okayama
    python -m trent        stores --keyword Okayama   # same thing
"""

from trent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
