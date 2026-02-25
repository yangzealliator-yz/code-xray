"""Allow running as `python -m xray`."""
import sys
import os
import importlib.util

# Load root xray.py (avoiding package name conflict)
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("_xray_cli", os.path.join(_root, "xray.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.exit(_mod.main())
