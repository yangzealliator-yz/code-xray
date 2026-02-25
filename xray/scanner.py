"""
scanner.py — Universal project scanner for Code X-Ray.

Walks a directory tree, classifies files by language and category,
counts lines, and returns a structured ProjectScan result.

Zero external dependencies — Python 3.8+ stdlib only.
Works on Windows, macOS, and Linux.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Language map: extension → canonical language name
# ---------------------------------------------------------------------------

LANG_MAP: Dict[str, str] = {
    # Python ecosystem
    ".py":      "python",
    ".pyw":     "python",
    # JavaScript / TypeScript
    ".js":      "javascript",
    ".mjs":     "javascript",
    ".cjs":     "javascript",
    ".ts":      "typescript",
    ".mts":     "typescript",
    # JSX / TSX
    ".jsx":     "jsx",
    ".tsx":     "tsx",
    # C# / .NET
    ".cs":      "csharp",
    # GDScript (Godot)
    ".gd":      "gdscript",
    # Go
    ".go":      "go",
    # Rust
    ".rs":      "rust",
    # Java
    ".java":    "java",
    # C / C++
    ".c":       "c",
    ".h":       "c",
    ".cpp":     "cpp",
    ".cc":      "cpp",
    ".cxx":     "cpp",
    ".hpp":     "cpp",
    ".hh":      "cpp",
    # Ruby
    ".rb":      "ruby",
    # PHP
    ".php":     "php",
    # Swift
    ".swift":   "swift",
    # Kotlin
    ".kt":      "kotlin",
    ".kts":     "kotlin",
    # Vue
    ".vue":     "vue",
    # Svelte
    ".svelte":  "svelte",
    # Lua
    ".lua":     "lua",
    # Shell / Bash
    ".sh":      "shell",
    ".bash":    "shell",
    ".zsh":     "shell",
    # PowerShell
    ".ps1":     "powershell",
    ".psm1":    "powershell",
    ".psd1":    "powershell",
    # R
    ".r":       "r",
    ".R":       "r",
    # Scala
    ".scala":   "scala",
    # Dart
    ".dart":    "dart",
    # Elixir
    ".ex":      "elixir",
    ".exs":     "elixir",
    # Zig
    ".zig":     "zig",
    # Nim
    ".nim":     "nim",
    # SQL
    ".sql":     "sql",
    # Web: HTML / CSS
    ".html":    "html",
    ".htm":     "html",
    ".css":     "css",
    ".scss":    "scss",
    ".sass":    "scss",
    ".less":    "less",
}

# ---------------------------------------------------------------------------
# Default directories to exclude from scanning
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDES: Set[str] = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "vendor",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "Temp",
    "Library",
    "obj",
    "bin",
    ".idea",
    ".vscode",
    ".gradle",
    "target",
}

# Extensions whose content we classify as "asset" (binary; skip line counting)
_ASSET_EXTS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp",
    ".svg", ".ico",
    ".wav", ".mp3", ".ogg", ".flac", ".aac",
    ".ttf", ".woff", ".woff2", ".eot", ".otf",
    ".mp4", ".mov", ".avi", ".webm",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".exe", ".dll", ".so", ".dylib",
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".pyc", ".pyo", ".class",
}

# Extensions whose content we classify as "config"
_CONFIG_EXTS: Set[str] = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".env", ".properties", ".conf", ".config",
    ".lock", ".editorconfig", ".gitattributes",
}

# Extensions whose content we classify as "doc"
_DOC_EXTS: Set[str] = {
    ".md", ".rst", ".txt", ".adoc", ".asciidoc",
    ".tex", ".man",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FileInfo:
    """Metadata for a single scanned file."""

    path: str        # Relative path from the project root (forward slashes)
    language: str    # Language name from LANG_MAP, or "unknown"
    line_count: int  # Number of text lines; 0 for binary/asset files
    size_bytes: int  # File size in bytes
    category: str    # One of: source | config | doc | test | asset | script


@dataclass
class ProjectScan:
    """Aggregated result of scanning a project directory."""

    root: str                    # Absolute path to the scanned root
    files: List[FileInfo]        # All FileInfo entries collected
    summary: Dict               # Aggregated statistics (see _build_summary)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_rel(root: str, abs_path: str) -> str:
    """Return a relative path from root to abs_path using forward slashes."""
    rel = os.path.relpath(abs_path, root)
    return rel.replace(os.sep, "/")


def _detect_category(rel_path: str, ext: str) -> str:
    """
    Classify a file into one of six categories based on path and extension.

    Priority order:
        1. test   — path contains /test/ segment, or matches test_* / *_test / *_spec
        2. asset  — binary/media extensions
        3. doc    — documentation extensions
        4. config — configuration extensions
        5. script — shell / powershell (source-like but not application code)
        6. source — everything else recognised by LANG_MAP
    """
    # Normalise to lowercase for case-insensitive matching
    lower = rel_path.lower()
    parts = lower.replace("\\", "/").split("/")
    stem = Path(rel_path).stem.lower()

    # --- test ---
    if "test" in parts or "tests" in parts or "spec" in parts or "specs" in parts:
        return "test"
    if (
        stem.startswith("test_")
        or stem.endswith("_test")
        or stem.endswith("_spec")
        or stem.endswith(".test")  # e.g. foo.test.ts (stem is "foo.test")
        or stem.endswith(".spec")
    ):
        return "test"

    # --- asset ---
    if ext in _ASSET_EXTS:
        return "asset"

    # --- doc ---
    if ext in _DOC_EXTS:
        return "doc"

    # --- config ---
    if ext in _CONFIG_EXTS:
        return "config"

    # --- script (shell / powershell treated separately from "source") ---
    lang = LANG_MAP.get(ext, "")
    if lang in ("shell", "powershell"):
        return "script"

    # --- source (any other recognised code file) ---
    return "source"


def _count_lines(abs_path: str) -> int:
    """
    Count newline-terminated lines in a text file.

    Returns 0 if the file appears to be binary or cannot be read.
    Uses UTF-8 with errors='ignore' to handle mixed encodings safely.
    """
    try:
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def _is_binary_path(ext: str) -> bool:
    """Return True when the extension reliably indicates binary content."""
    return ext in _ASSET_EXTS


def _build_summary(files: List[FileInfo]) -> Dict:
    """
    Build the summary dict from a list of FileInfo objects.

    Returns:
        {
            "total_files":   int,
            "total_lines":   int,
            "total_size":    int,          # bytes
            "language_counts":  {lang: count, ...},
            "category_counts":  {category: count, ...},
        }
    """
    lang_counts: Dict[str, int] = {}
    cat_counts: Dict[str, int] = {}
    total_lines = 0
    total_size = 0

    for fi in files:
        lang_counts[fi.language] = lang_counts.get(fi.language, 0) + 1
        cat_counts[fi.category] = cat_counts.get(fi.category, 0) + 1
        total_lines += fi.line_count
        total_size += fi.size_bytes

    return {
        "total_files": len(files),
        "total_lines": total_lines,
        "total_size": total_size,
        "language_counts": dict(sorted(lang_counts.items(), key=lambda x: -x[1])),
        "category_counts": dict(sorted(cat_counts.items(), key=lambda x: -x[1])),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_xrayrc(project_root: str) -> Dict:
    """
    Load .xrayrc JSON configuration, with fallback chain:

        1. <project_root>/.xrayrc
        2. ~/.xrayrc
        3. Empty dict (no config found)

    Recognised keys (all optional):
        exclude_dirs      list[str]   — additional directory names to skip
        exclude_patterns  list[str]   — glob-style filename patterns to skip (not yet applied here)
        max_depth         int         — maximum directory depth to descend
        max_files         int         — stop after this many files
        custom_categories dict        — extension → category overrides

    Returns a dict (possibly empty) with the merged settings.
    """
    candidates = [
        Path(project_root) / ".xrayrc",
        Path.home() / ".xrayrc",
    ]

    for candidate in candidates:
        if candidate.is_file():
            try:
                with open(str(candidate), "r", encoding="utf-8", errors="ignore") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError):
                # Corrupt or unreadable config → try next candidate
                pass

    return {}


def scan_project(
    root: str,
    exclude_dirs: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    max_files: Optional[int] = None,
) -> ProjectScan:
    """
    Walk *root* recursively and return a ProjectScan.

    Parameters
    ----------
    root:
        Absolute (or relative) path to the project directory.
    exclude_dirs:
        Additional directory names (not full paths) to skip on top of
        DEFAULT_EXCLUDES.  E.g. ["dist", "coverage"].
    max_depth:
        Maximum recursion depth.  0 means only the root directory itself;
        None means unlimited.
    max_files:
        Stop collecting FileInfo entries after this many files (the walk
        itself stops early to avoid wasted I/O).  None means unlimited.

    Returns
    -------
    ProjectScan with all FileInfo entries and a pre-built summary dict.
    """
    root = os.path.abspath(root)

    # Merge exclude sets
    excluded: Set[str] = DEFAULT_EXCLUDES.copy()
    if exclude_dirs:
        excluded.update(exclude_dirs)

    files: List[FileInfo] = []
    visited_realpaths: Set[str] = set()   # guard against symlink loops
    file_count = 0

    # Pre-compute root depth for max_depth enforcement
    root_depth = root.rstrip(os.sep).count(os.sep)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        # --- symlink loop detection ---
        real_dir = os.path.realpath(dirpath)
        if real_dir in visited_realpaths:
            dirnames.clear()
            continue
        visited_realpaths.add(real_dir)

        # --- max_depth enforcement ---
        if max_depth is not None:
            current_depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
            if current_depth >= max_depth:
                dirnames.clear()  # Do not recurse deeper

        # --- prune excluded directories in-place (modifies os.walk traversal) ---
        dirnames[:] = [
            d for d in dirnames
            if d not in excluded and not d.startswith(".")
            # Hidden directories (starting with ".") are excluded by default
            # EXCEPT we must allow the root itself if it happens to start with "."
            # The root has already been added to visited; only sub-dirs are pruned.
            or (d.startswith(".") and dirpath == root and d not in excluded)
        ]
        # Re-apply: always drop excluded regardless of dot-prefix
        dirnames[:] = [d for d in dirnames if d not in excluded]

        # --- process files in this directory ---
        for filename in filenames:
            if max_files is not None and file_count >= max_files:
                # Signal os.walk to stop descending further
                dirnames.clear()
                break

            abs_path = os.path.join(dirpath, filename)

            # Skip Windows device paths (NUL, CON, AUX, etc.) that break relpath
            try:
                rel_path = _normalise_rel(root, abs_path)
            except ValueError:
                continue

            # Resolve extension (lower-case for matching)
            _, raw_ext = os.path.splitext(filename)
            ext = raw_ext.lower()

            language = LANG_MAP.get(ext, "unknown")
            category = _detect_category(rel_path, ext)

            # File size
            try:
                size_bytes = os.path.getsize(abs_path)
            except OSError:
                size_bytes = 0

            # Line count — skip for assets and truly binary files
            if _is_binary_path(ext):
                line_count = 0
            else:
                line_count = _count_lines(abs_path)

            files.append(
                FileInfo(
                    path=rel_path,
                    language=language,
                    line_count=line_count,
                    size_bytes=size_bytes,
                    category=category,
                )
            )

            file_count += 1

            # Progress heartbeat every 500 files
            if file_count % 500 == 0:
                print(
                    f"[xray] scanned {file_count} files … (at {rel_path})",
                    file=sys.stderr,
                    flush=True,
                )

    summary = _build_summary(files)
    return ProjectScan(root=root, files=files, summary=summary)
