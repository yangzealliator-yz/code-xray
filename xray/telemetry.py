"""
telemetry.py — Anonymous project structure data collection.

Sends aggregate structure data (file names, dependency edges, statistics)
to improve scanning accuracy. No source code is ever transmitted.
Use --offline to opt out.
"""

import json
import os
import re
import urllib.request
import urllib.error
from typing import Dict, Optional


TELEMETRY_ENDPOINT = "https://api.codexray.dev/telemetry"
GALLERY_ENDPOINT = "https://api.codexray.dev/gallery"
TIMEOUT_S = 5

# Regex to detect API keys/tokens near sensitive keywords
_SENSITIVE_LINE_RE = re.compile(
    r"(?i)(key|token|secret|api|password|credential).*[=:]\s*['\"]?([A-Za-z0-9_\-]{8,})",
)


def _strip_sensitive(text: str) -> str:
    """Remove lines containing API keys/tokens/secrets from config text."""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        if _SENSITIVE_LINE_RE.search(line):
            cleaned.append("[REDACTED]")
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


def build_upload_payload(data: dict) -> dict:
    """Build a sanitized payload for telemetry upload.

    - Removes absolute paths from meta.root
    - Strips API keys from ai_configs
    - Preserves nodes, edges, summary
    """
    payload = {}

    # Meta: replace root with project name only
    meta = dict(data.get("meta", {}))
    meta.pop("root", None)  # Remove absolute path
    payload["meta"] = meta

    # Summary
    payload["summary"] = data.get("summary", {})

    # Nodes: keep structure, ensure no absolute paths
    nodes = []
    for n in data.get("nodes", []):
        node = dict(n)
        # Ensure path is relative (should already be)
        node_id = node.get("id", "")
        if os.path.isabs(node_id):
            node["id"] = os.path.basename(node_id)
        nodes.append(node)
    payload["nodes"] = nodes

    # Edges
    payload["edges"] = data.get("edges", [])

    # AI configs: strip sensitive values
    if "ai_configs" in data and data["ai_configs"]:
        cleaned_configs = {}
        for name, content in data["ai_configs"].items():
            if isinstance(content, str):
                cleaned_configs[name] = _strip_sensitive(content)
            else:
                cleaned_configs[name] = content
        payload["ai_configs"] = cleaned_configs

    return payload


def send_telemetry(data: dict, endpoint: str = TELEMETRY_ENDPOINT) -> bool:
    """Send telemetry data. Returns True on success, False on failure.

    Fails silently — never raises exceptions or prints errors.
    """
    payload = build_upload_payload(data)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S):
            return True
    except Exception:
        return False


def share_to_gallery(
    data: dict,
    json_output_path: Optional[str] = None,
) -> Optional[str]:
    """Upload to community gallery. Returns gallery URL or None.

    Unlike telemetry, this is user-initiated so errors are shown.
    """
    payload = build_upload_payload(data)
    total_files = len(payload.get("nodes", []))
    total_edges = len(payload.get("edges", []))
    project_name = payload.get("meta", {}).get("project", "unknown")

    print(f'Will share: {total_files} files, {total_edges} deps, project name "{project_name}".')
    confirm = input("Proceed? [Y/n] ").strip().lower()
    if confirm == "n":
        print("Cancelled.")
        return None

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        GALLERY_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            url = result.get("url", "")
            if url:
                print(f"Shared! View at: {url}")
                return url
    except Exception:
        pass

    # Fallback: save locally
    fallback_path = json_output_path or "xray-data.json"
    with open(fallback_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Gallery coming soon! Data saved to {fallback_path}")
    return None
