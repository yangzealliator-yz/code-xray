"""Allow running as `python -m xray`."""
import sys
from xray.cli import main

if __name__ == "__main__":
    sys.exit(main())
