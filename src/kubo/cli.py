"""Compatibility entry point for ``python -m kubo.cli``."""

from __future__ import annotations

import sys

from .cli_v3 import main, parser


__all__ = ["main", "parser"]


if __name__ == "__main__":
    sys.exit(main())
