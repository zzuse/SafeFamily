#!/usr/bin/env python
"""Convenience script to run URL analyzer.

e.g.: python -m safe_family.cli.analyze --range last_5min
"""

import sys

from src.safe_family.cli.analyze import main

if __name__ == "__main__":
    sys.exit(main())
