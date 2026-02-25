#!/usr/bin/env python3
"""
xray.py — Code X-Ray CLI entry point.

Usage:
    python xray.py [path]              # Scan and generate dashboard
    python xray.py . -o report.html    # Custom output path
    python xray.py . --json            # Also output JSON data
    python xray.py . --no-git          # Skip git analysis
    python -m xray [path]              # Module invocation
"""

import argparse
import json
import os
import sys
import time


def _template_path() -> str:
    """Locate the dashboard.html template relative to this file."""
    here = os.path.dirname(os.path.abspath(__file__))
    # Check both: running from repo root (xray.py) and package (xray/__main__.py)
    candidates = [
        os.path.join(here, "templates", "dashboard.html"),
        os.path.join(here, "..", "templates", "dashboard.html"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return candidates[0]  # Will fail with a clear error


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="xray",
        description="Code X-Ray — Generate a visual dashboard for any codebase.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory to scan (default: current directory)",
    )
    parser.add_argument(
        "-o", "--output",
        default="xray-report.html",
        help="Output HTML path (default: xray-report.html)",
    )
    parser.add_argument(
        "--json",
        nargs="?",
        const="xray-data.json",
        default=None,
        metavar="PATH",
        help="Also output JSON data (default: xray-data.json)",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Skip git history analysis",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Embed D3.js inline (not implemented in v1)",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=None,
        help="Additional directories to exclude",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum directory recursion depth",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Maximum number of files to scan",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Upload dashboard data to community gallery",
    )
    parser.add_argument(
        "--ai",
        action="store_true",
        help="Output LLM-friendly JSON instead of HTML dashboard",
    )
    parser.add_argument(
        "--deep",
        choices=["keys", "signatures", "ai-config"],
        default=None,
        help="Depth level for --ai output (keys/signatures/ai-config)",
    )
    parser.add_argument(
        "--prompt",
        choices=["arch", "deps", "refactor"],
        default=None,
        help="Output a complete prompt with data for LLM analysis",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="xray 1.0.0",
    )

    args = parser.parse_args(argv)
    project_root = os.path.abspath(args.path)

    if not os.path.isdir(project_root):
        print(f"Error: '{args.path}' is not a directory.", file=sys.stderr)
        return 1

    project_name = os.path.basename(project_root) or "project"

    # --- Load .xrayrc (CLI args override config) ---
    from xray.scanner import scan_project, load_xrayrc
    from xray.analyzer import analyze_dependencies
    from xray.git_stats import get_git_stats

    # Use stderr for progress when --ai outputs to stdout
    _log = (lambda msg: print(msg, file=sys.stderr)) if (args.ai or args.prompt) else print

    rc = load_xrayrc(project_root)
    if rc:
        _log(f"[xray] Loaded .xrayrc config")
    # Merge: CLI args > .xrayrc > defaults
    if args.exclude is None and "exclude_dirs" in rc:
        args.exclude = rc["exclude_dirs"]
    if args.max_depth is None and "max_depth" in rc:
        args.max_depth = rc["max_depth"]
    if args.max_files is None and "max_files" in rc:
        args.max_files = rc["max_files"]
    from xray.renderer import render_html

    t0 = time.time()

    # Step 1: Scan
    _log(f"[xray] Scanning {project_root} ...")
    scan = scan_project(
        project_root,
        exclude_dirs=args.exclude,
        max_depth=args.max_depth,
        max_files=args.max_files,
    )
    total_files = len(scan.files)
    total_lines = sum(getattr(f, "line_count", 0) for f in scan.files)

    # Step 2: Analyze dependencies
    _log(f"[xray] Analyzing dependencies ({total_files} files) ...")
    deps = analyze_dependencies(scan, project_root)

    # Step 3: Git stats
    if args.no_git:
        _log("[xray] Skipping git analysis (--no-git)")
        git_stats = {}
    else:
        _log("[xray] Reading git history ...")
        git_stats = get_git_stats(project_root)

    # Step 4a: AI output mode (--ai)
    if args.ai or args.prompt:
        from xray.ai_output import extract_ai_output, build_prompt
        ai_data = extract_ai_output(scan, deps, project_root, deep=args.deep)
        if args.prompt:
            print(build_prompt(args.prompt, ai_data))
        else:
            print(json.dumps(ai_data, ensure_ascii=False, indent=2))
        return 0

    # Step 4: Render
    template = _template_path()
    if not os.path.isfile(template):
        print(f"Error: Template not found at {template}", file=sys.stderr)
        return 1

    _log("[xray] Generating dashboard ...")
    render_html(
        scan=scan,
        deps=deps,
        git_stats=git_stats,
        template_path=template,
        output_path=args.output,
        project_name=project_name,
        json_output_path=args.json,
    )

    dt = time.time() - t0
    lines_str = f"{total_lines/1000:.0f}K" if total_lines >= 1000 else str(total_lines)
    print(f"Done! Dashboard: {args.output} ({total_files} files, {lines_str} lines) [{dt:.1f}s]")

    if args.json:
        print(f"      JSON data: {args.json}")

    # Step 5: Telemetry (default on, --offline disables)
    if not args.offline:
        from xray.telemetry import send_telemetry
        from xray.renderer import _build_xray_data
        telemetry_data = _build_xray_data(scan, deps, git_stats, project_name)
        send_telemetry(telemetry_data)  # silent, no output

    # Step 6: Gallery (--share)
    if args.share:
        from xray.telemetry import share_to_gallery
        from xray.renderer import _build_xray_data
        gallery_data = _build_xray_data(scan, deps, git_stats, project_name)
        share_to_gallery(gallery_data, json_output_path=args.json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
