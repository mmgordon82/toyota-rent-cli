"""Read-only client for Toyota Rent-a-Car's app API, in English.

The app API (``/TrentApp/app/api/v1/``) is Japanese-only, so this package
renders store names, car models, and labels into English on the client. See
``fleet`` and ``translate`` for how that mapping works.
"""

__all__ = ["main"]


def main(argv=None):
    from trent.cli import main as _main

    return _main(argv)
