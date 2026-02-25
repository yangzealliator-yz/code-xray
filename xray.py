#!/usr/bin/env python3
"""
xray.py — Code X-Ray CLI entry point (thin wrapper).

Usage:
    python xray.py [path]              # Scan and generate dashboard
    python xray.py . -o report.html    # Custom output path
    python xray.py . --json            # Also output JSON data
    python xray.py . --no-git          # Skip git analysis
    python -m xray [path]              # Module invocation
    xray [path]                        # After pip install
"""

import sys
from xray.cli import main

if __name__ == "__main__":
    sys.exit(main())
