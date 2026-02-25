"""
renderer.py — Aggregate scan data and inject into dashboard HTML template.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _build_xray_data(
    scan,
    deps,
    git_stats: Dict[str, dict],
    project_name: str,
) -> dict:
    """Build the XRAY_DATA JSON structure from scan/analyzer/git_stats outputs."""
    # --- summary ---
    lang_counts: Dict[str, int] = {}
    cat_counts: Dict[str, int] = {}
    total_lines = 0
    for f in scan.files:
        lang = getattr(f, "language", "unknown")
        cat = getattr(f, "category", "source")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        total_lines += getattr(f, "line_count", 0)

    # Remove 'unknown' from language summary if present
    lang_counts.pop("unknown", None)

    summary = {
        "total_files": len(scan.files),
        "total_lines": total_lines,
        "languages": dict(sorted(lang_counts.items(), key=lambda x: -x[1])),
        "categories": dict(sorted(cat_counts.items(), key=lambda x: -x[1])),
    }

    # --- nodes ---
    nodes: List[dict] = []
    for f in scan.files:
        path = getattr(f, "path", str(f))
        git_info = git_stats.get(path, {})
        directory = os.path.dirname(path).replace("\\", "/") if os.path.dirname(path) else ""
        nodes.append({
            "id": path,
            "language": getattr(f, "language", "unknown"),
            "category": getattr(f, "category", "source"),
            "lines": getattr(f, "line_count", 0),
            "size": getattr(f, "size_bytes", 0),
            "directory": directory,
            "git_commits": git_info.get("commits", 0),
            "git_last_modified": git_info.get("last_modified", ""),
        })

    # --- edges ---
    edges: List[dict] = []
    if deps and hasattr(deps, "edges"):
        for e in deps.edges:
            if isinstance(e, dict):
                edges.append({
                    "source": e.get("source", ""),
                    "target": e.get("target", ""),
                    "type": e.get("type", "import"),
                })
            elif hasattr(e, "source"):
                edges.append({
                    "source": e.source,
                    "target": e.target,
                    "type": getattr(e, "type", "import"),
                })

    # --- meta ---
    meta = {
        "project": project_name,
        "scan_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "1.0.0",
    }

    return {
        "meta": meta,
        "summary": summary,
        "nodes": nodes,
        "edges": edges,
    }


def render_html(
    scan,
    deps,
    git_stats: Dict[str, dict],
    template_path: str,
    output_path: str,
    project_name: Optional[str] = None,
    json_output_path: Optional[str] = None,
) -> str:
    """Render the final dashboard HTML by injecting scan data into the template.

    Args:
        scan: ProjectScan object from scanner.
        deps: DependencyGraph object from analyzer.
        git_stats: Dict from get_git_stats().
        template_path: Path to dashboard.html template.
        output_path: Where to write the final HTML.
        project_name: Display name for the project.
        json_output_path: If set, also write xray-data.json.

    Returns:
        The output_path written to.
    """
    if project_name is None:
        project_name = os.path.basename(os.path.dirname(output_path)) or "project"

    data = _build_xray_data(scan, deps, git_stats, project_name)
    json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    # Read template
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # Replace the data placeholder
    pattern = r"/\*__XRAY_DATA__\*/.*?/\*__END__\*/"
    replacement = f"/*__XRAY_DATA__*/{json_str}/*__END__*/"
    html = re.sub(pattern, replacement, template, count=1, flags=re.DOTALL)

    # Write output HTML
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Optional JSON output
    if json_output_path:
        with open(json_output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return output_path
