"""
xray/analyzer.py — Cross-language dependency analyzer for Code X-Ray.

Parses import/require/use statements from source files in 6 languages
(Python, JavaScript/TypeScript, C#, GDScript, Go, Rust) and builds a
directed dependency graph of project-internal file relationships.

Zero external dependencies — pure Python 3.8+ stdlib only.
"""

from __future__ import annotations

import os
import re
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class DependencyGraph:
    """
    Holds the full dependency graph for an analyzed project.

    Attributes
    ----------
    nodes:
        One dict per file.  Keys:
          - id        (str)  project-relative POSIX path, e.g. "src/foo.py"
          - language  (str)  detected language label, e.g. "Python"
          - category  (str)  coarse bucket: "source" | "config" | "data" | "other"
          - lines     (int)  line count (0 if unreadable)
          - size      (int)  byte size
          - directory (str)  parent directory of the file, POSIX-relative
    edges:
        One dict per resolved import relationship.  Keys:
          - source  (str)  project-relative POSIX path of the importer
          - target  (str)  project-relative POSIX path of the importee
          - type    (str)  "import" | "require" | "using"
    external_deps:
        Sorted, deduplicated list of external package/module names that
        could not be resolved to a project-internal file.
    """

    nodes: List[Dict] = field(default_factory=list)
    edges: List[Dict] = field(default_factory=list)
    external_deps: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Typing shim — scanner.py is a sibling module; import defensively so that
# this module can also be used standalone (e.g. in tests) with a duck-typed
# scan object.
# ---------------------------------------------------------------------------

try:
    from xray.scanner import ProjectScan  # type: ignore
except ImportError:  # scanner not yet present or running standalone
    ProjectScan = None  # type: ignore


# ---------------------------------------------------------------------------
# Language detection helpers
# ---------------------------------------------------------------------------

_EXT_LANGUAGE: Dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cs": "C#",
    ".gd": "GDScript",
    ".go": "Go",
    ".rs": "Rust",
}

_EXT_CATEGORY: Dict[str, str] = {
    ".py": "source",
    ".js": "source",
    ".jsx": "source",
    ".mjs": "source",
    ".cjs": "source",
    ".ts": "source",
    ".tsx": "source",
    ".mts": "source",
    ".cs": "source",
    ".gd": "source",
    ".go": "source",
    ".rs": "source",
    ".json": "config",
    ".yaml": "config",
    ".yml": "config",
    ".toml": "config",
    ".ini": "config",
    ".cfg": "config",
    ".csv": "data",
    ".sql": "data",
    ".xml": "data",
}


def _language_for(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return _EXT_LANGUAGE.get(ext, "Other")


def _category_for(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return _EXT_CATEGORY.get(ext, "other")


# ---------------------------------------------------------------------------
# Regex patterns per language
# Compiled once at module load for speed.
# ---------------------------------------------------------------------------

# Python ---------------------------------------------------------------
_PY_IMPORT = re.compile(
    r"""
    ^\s*
    (?:
        import \s+ (?P<mod_plain> [\w][\w.]* )   # import foo | import foo.bar
      |
        from \s+ (?P<mod_from> \.* [\w][\w.]* | \.+ )  # from foo.bar import baz
        \s+ import \s+ .+
    )
    """,
    re.VERBOSE | re.MULTILINE,
)

# JavaScript / TypeScript -----------------------------------------------
_JS_IMPORT_FROM = re.compile(
    r"""
    (?:^|\b)
    (?:import|export) \b .+? \bfrom \s*
    ['"] (?P<path> [^'"]+) ['"]
    """,
    re.VERBOSE | re.MULTILINE,
)

_JS_REQUIRE = re.compile(
    r"""
    \brequire \s* \( \s*
    ['"] (?P<path> [^'"]+) ['"]
    \s* \)
    """,
    re.VERBOSE | re.MULTILINE,
)

_JS_DYNAMIC_IMPORT = re.compile(
    r"""
    \bimport \s* \( \s*
    ['"] (?P<path> [^'"]+) ['"]
    \s* \)
    """,
    re.VERBOSE | re.MULTILINE,
)

# C# -------------------------------------------------------------------
_CS_USING = re.compile(
    r"""
    ^ \s* using \s+
    (?!static\b) (?!var\b)    # skip "using static" and "using var"
    (?P<ns> [\w][\w.]* )
    \s* ;
    """,
    re.VERBOSE | re.MULTILINE,
)

# GDScript -------------------------------------------------------------
_GD_EXTENDS_PATH = re.compile(
    r"""
    ^ \s* extends \s+
    ["'] (?P<path> res:// [^"']+) ["']
    """,
    re.VERBOSE | re.MULTILINE,
)

_GD_EXTENDS_CLASS = re.compile(
    r"""
    ^ \s* extends \s+
    (?P<cls> [A-Z][\w]* )
    \s* $
    """,
    re.VERBOSE | re.MULTILINE,
)

_GD_PRELOAD = re.compile(
    r"""
    \bpreload \s* \( \s*
    ["'] (?P<path> res:// [^"']+) ["']
    \s* \)
    """,
    re.VERBOSE | re.MULTILINE,
)

_GD_LOAD = re.compile(
    r"""
    \bload \s* \( \s*
    ["'] (?P<path> res:// [^"']+) ["']
    \s* \)
    """,
    re.VERBOSE | re.MULTILINE,
)

# Go -------------------------------------------------------------------
_GO_IMPORT_SINGLE = re.compile(
    r"""
    ^ \s* import \s+
    (?P<alias> \w+ \s+ )?
    " (?P<path> [^"]+) "
    """,
    re.VERBOSE | re.MULTILINE,
)

_GO_IMPORT_BLOCK = re.compile(
    r"""
    import \s* \(
    (?P<block> [^)]+)
    \)
    """,
    re.VERBOSE | re.DOTALL,
)

_GO_IMPORT_BLOCK_ENTRY = re.compile(
    r"""
    (?P<alias> \w+ \s+ )?
    " (?P<path> [^"]+) "
    """,
    re.VERBOSE,
)

# Rust -----------------------------------------------------------------
_RUST_USE = re.compile(
    r"""
    ^ \s* (?:pub \s+)? use \s+
    (?P<path> crate :: [\w::]+ | super :: [\w:]+ | self :: [\w:]+ )
    (?:\s*::\s*\{[^}]*\})?
    (?:\s*::\s*\*)?
    \s* ;
    """,
    re.VERBOSE | re.MULTILINE,
)

_RUST_MOD = re.compile(
    r"""
    ^ \s* (?:pub \s+)? mod \s+
    (?P<name> \w+ )
    \s* ;
    """,
    re.VERBOSE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------

def _to_posix(path: str) -> str:
    """Normalise any path to forward-slash POSIX form."""
    return path.replace("\\", "/")


def _rel_posix(abs_path: str, root: str) -> str:
    """Return *abs_path* relative to *root*, using forward slashes."""
    try:
        return _to_posix(os.path.relpath(abs_path, root))
    except ValueError:
        # Different drives on Windows — return as-is
        return _to_posix(abs_path)


def _probe_extensions(base: str, extensions: List[str]) -> Optional[str]:
    """
    Return the first path that exists when each *extension* is appended to
    *base*, or None if nothing matches.
    """
    for ext in extensions:
        candidate = base + ext
        if os.path.isfile(candidate):
            return candidate
    return None


def _resolve_relative(
    source_abs: str,
    ref: str,
    project_root: str,
    js_extensions: Tuple[str, ...] = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"),
) -> Optional[str]:
    """
    Resolve a relative import reference (starting with ./ or ../) from
    *source_abs* to an absolute path, then return project-relative POSIX form.

    Tries bare path, then with each JS/TS extension, then /index.* variants.
    Returns None if no file found.
    """
    source_dir = os.path.dirname(source_abs)
    # Strip query strings and hash fragments sometimes seen in bundler configs
    ref_clean = ref.split("?")[0].split("#")[0]
    target_abs = os.path.normpath(os.path.join(source_dir, ref_clean))

    # 1. Exact file
    if os.path.isfile(target_abs):
        return _rel_posix(target_abs, project_root)

    # 2. With JS/TS extensions
    found = _probe_extensions(target_abs, list(js_extensions))
    if found:
        return _rel_posix(found, project_root)

    # 3. As a directory with index file
    for ext in js_extensions:
        index_path = os.path.join(target_abs, "index" + ext)
        if os.path.isfile(index_path):
            return _rel_posix(index_path, project_root)

    return None


def _resolve_python_import(
    source_abs: str,
    mod_str: str,
    project_root: str,
    is_relative: bool = False,
) -> Tuple[Optional[str], bool]:
    """
    Resolve a Python module string to a project-relative path.

    Returns (resolved_rel_path_or_None, is_external).
    - is_external=True  → package is not in project (treat as external dep)
    - is_external=False → either resolved or simply unresolvable local ref
    """
    # Leading dots indicate a relative import; count them
    leading_dots = len(mod_str) - len(mod_str.lstrip("."))
    mod_clean = mod_str.lstrip(".")

    if leading_dots > 0:
        # Relative import: walk up from source's package directory
        source_dir = os.path.dirname(source_abs)
        base_dir = source_dir
        for _ in range(leading_dots - 1):
            base_dir = os.path.dirname(base_dir)
        search_root = base_dir
    else:
        search_root = project_root

    parts = mod_clean.split(".") if mod_clean else []
    rel_path = os.path.join(*parts) if parts else ""
    base = os.path.join(search_root, rel_path)

    # Try module.py
    if os.path.isfile(base + ".py"):
        return _rel_posix(base + ".py", project_root), False

    # Try package/__init__.py
    init = os.path.join(base, "__init__.py")
    if os.path.isfile(init):
        return _rel_posix(init, project_root), False

    # If there are no dots and no leading dots it could be stdlib or external
    if leading_dots == 0 and mod_clean and "." not in mod_clean:
        return None, True  # likely external / stdlib

    # Dotted and not found — treat top-level as external candidate
    if leading_dots == 0 and mod_clean:
        top = mod_clean.split(".")[0]
        return None, True  # external package

    return None, False


def _resolve_csharp_namespace(
    ns: str,
    all_files: Set[str],
    project_root: str,
) -> List[str]:
    """
    Heuristically map a C# namespace to project files.

    Strategy: The last component of the namespace is likely the class/type
    name.  Search all .cs files whose stem matches that component
    (case-insensitive).
    """
    parts = ns.rstrip(";").split(".")
    class_hint = parts[-1].lower()
    matches = []
    for f in all_files:
        if f.endswith(".cs"):
            stem = os.path.splitext(os.path.basename(f))[0].lower()
            if stem == class_hint:
                matches.append(f)
    return matches


def _resolve_gdscript_res_path(
    res_path: str,
    project_root: str,
) -> Optional[str]:
    """
    Map a Godot res:// path to a project-relative file path.

    Strips the "res://" prefix and resolves against project_root.
    """
    stripped = res_path.replace("res://", "", 1)
    # Normalise slashes
    stripped = _to_posix(stripped)
    abs_path = os.path.join(project_root, stripped)
    abs_path = os.path.normpath(abs_path)
    if os.path.isfile(abs_path):
        return _rel_posix(abs_path, project_root)
    return None


def _resolve_gdscript_class(
    class_name: str,
    all_gd_files: List[str],
    project_root: str,
) -> Optional[str]:
    """
    Find a .gd file whose stem matches *class_name* (case-insensitive).
    Returns project-relative POSIX path or None.
    """
    target = class_name.lower()
    for f in all_gd_files:
        stem = os.path.splitext(os.path.basename(f))[0].lower()
        if stem == target:
            return f
    return None


def _resolve_go_import(
    import_path: str,
    module_name: str,
    project_root: str,
) -> Optional[str]:
    """
    Resolve a Go import path to a project-relative directory/file.

    If the import starts with *module_name* (detected from go.mod), strip that
    prefix and probe for the resulting sub-directory; return the first .go file
    found, or None.

    Import paths with no '.' and no '/' are treated as stdlib — return None.
    """
    # Skip standard library (no dot, no slash usually)
    if "." not in import_path and "/" not in import_path:
        return None
    # Skip well-known stdlib domains that were miscategorised
    if import_path.startswith("golang.org/") or import_path.startswith("google.golang.org/"):
        return None

    # Local package inside this module
    if module_name and import_path.startswith(module_name):
        suffix = import_path[len(module_name):].lstrip("/")
        dir_abs = os.path.normpath(os.path.join(project_root, suffix.replace("/", os.sep)))
        if os.path.isdir(dir_abs):
            # Return first .go file in that directory as representative node
            for entry in sorted(os.listdir(dir_abs)):
                if entry.endswith(".go") and not entry.endswith("_test.go"):
                    return _rel_posix(os.path.join(dir_abs, entry), project_root)
        # Also try it as a direct file
        if os.path.isfile(dir_abs + ".go"):
            return _rel_posix(dir_abs + ".go", project_root)

    return None


def _resolve_rust_use(
    use_path: str,
    source_abs: str,
    project_root: str,
) -> Optional[str]:
    """
    Resolve a Rust `use crate::...` path to a project-relative file.

    crate::a::b  →  try src/a/b.rs then src/a/b/mod.rs
    super::a     →  resolve relative to parent module
    """
    if use_path.startswith("crate::"):
        inner = use_path[len("crate::"):].replace("::", "/")
        src_dir = os.path.join(project_root, "src")
        # Strip trailing type/function name (last segment could be a type)
        # Try both as-is and without last segment
        candidates = [inner, "/".join(inner.split("/")[:-1])] if "/" in inner else [inner]
        for c in candidates:
            if not c:
                continue
            base = os.path.join(src_dir, c.replace("/", os.sep))
            if os.path.isfile(base + ".rs"):
                return _rel_posix(base + ".rs", project_root)
            mod_rs = os.path.join(base, "mod.rs")
            if os.path.isfile(mod_rs):
                return _rel_posix(mod_rs, project_root)
        return None

    if use_path.startswith("super::"):
        inner = use_path[len("super::"):].replace("::", "/")
        parent_dir = os.path.dirname(os.path.dirname(source_abs))
        base = os.path.join(parent_dir, inner.replace("/", os.sep))
        if os.path.isfile(base + ".rs"):
            return _rel_posix(base + ".rs", project_root)
        return None

    if use_path.startswith("self::"):
        inner = use_path[len("self::"):].replace("::", "/")
        source_dir = os.path.dirname(source_abs)
        base = os.path.join(source_dir, inner.replace("/", os.sep))
        if os.path.isfile(base + ".rs"):
            return _rel_posix(base + ".rs", project_root)
        return None

    return None


def _resolve_rust_mod(
    mod_name: str,
    source_abs: str,
    project_root: str,
) -> Optional[str]:
    """
    Resolve a Rust `mod name;` declaration.

    Tries <sibling>/name.rs and <sibling>/name/mod.rs relative to the
    declaring source file's directory.
    """
    source_dir = os.path.dirname(source_abs)
    candidate_rs = os.path.join(source_dir, mod_name + ".rs")
    if os.path.isfile(candidate_rs):
        return _rel_posix(candidate_rs, project_root)
    candidate_mod = os.path.join(source_dir, mod_name, "mod.rs")
    if os.path.isfile(candidate_mod):
        return _rel_posix(candidate_mod, project_root)
    return None


# ---------------------------------------------------------------------------
# Per-language import parsers
# Each returns a list of (raw_ref, edge_type) tuples where raw_ref still
# needs further resolution by the caller.
# ---------------------------------------------------------------------------

def _parse_python(source: str) -> List[Tuple[str, str]]:
    """
    Extract Python import references from *source* text.

    Returns list of (module_string, "import").
    Leading dots are preserved for relative import detection.
    """
    results: List[Tuple[str, str]] = []
    for m in _PY_IMPORT.finditer(source):
        plain = m.group("mod_plain")
        from_mod = m.group("mod_from")
        ref = plain if plain is not None else from_mod
        if ref is not None:
            results.append((ref.strip(), "import"))
    return results


def _parse_javascript(source: str) -> List[Tuple[str, str]]:
    """
    Extract JS/TS import references.

    Relative paths (starting ./ or ../) are kept; bare names (npm packages,
    node built-ins) are returned prefixed with "npm:" so the caller can
    detect externals.
    """
    results: List[Tuple[str, str]] = []
    seen: Set[str] = set()

    def _add(path: str, etype: str) -> None:
        if path not in seen:
            seen.add(path)
            results.append((path, etype))

    for m in _JS_IMPORT_FROM.finditer(source):
        p = m.group("path")
        if p:
            _add(p, "import")

    for m in _JS_REQUIRE.finditer(source):
        p = m.group("path")
        if p:
            _add(p, "require")

    for m in _JS_DYNAMIC_IMPORT.finditer(source):
        p = m.group("path")
        if p:
            _add(p, "import")

    return results


def _parse_csharp(source: str) -> List[Tuple[str, str]]:
    """Extract C# using-namespace statements."""
    results: List[Tuple[str, str]] = []
    for m in _CS_USING.finditer(source):
        ns = m.group("ns")
        if ns:
            results.append((ns.strip(), "using"))
    return results


def _parse_gdscript(source: str) -> List[Tuple[str, str]]:
    """Extract GDScript extends/preload/load references."""
    results: List[Tuple[str, str]] = []

    for m in _GD_EXTENDS_PATH.finditer(source):
        p = m.group("path")
        if p:
            results.append((p, "import"))

    for m in _GD_PRELOAD.finditer(source):
        p = m.group("path")
        if p:
            results.append((p, "import"))

    for m in _GD_LOAD.finditer(source):
        p = m.group("path")
        if p:
            results.append((p, "import"))

    for m in _GD_EXTENDS_CLASS.finditer(source):
        cls = m.group("cls")
        if cls:
            results.append(("class:" + cls, "import"))

    return results


def _parse_go(source: str) -> List[Tuple[str, str]]:
    """Extract Go import paths (single and block forms)."""
    results: List[Tuple[str, str]] = []
    seen: Set[str] = set()

    def _add(path: str) -> None:
        if path and path not in seen:
            seen.add(path)
            results.append((path, "import"))

    # Single import lines
    for m in _GO_IMPORT_SINGLE.finditer(source):
        _add(m.group("path"))

    # Block imports — find block bodies first
    # (block regex intentionally broad; entry regex filters each line)
    block_positions: Set[int] = set()
    for bm in _GO_IMPORT_BLOCK.finditer(source):
        block_positions.add(bm.start())
        for em in _GO_IMPORT_BLOCK_ENTRY.finditer(bm.group("block")):
            _add(em.group("path"))

    return results


def _parse_rust(source: str) -> List[Tuple[str, str]]:
    """Extract Rust use and mod declarations."""
    results: List[Tuple[str, str]] = []

    for m in _RUST_USE.finditer(source):
        path = m.group("path")
        if path:
            results.append((path, "import"))

    for m in _RUST_MOD.finditer(source):
        name = m.group("name")
        if name:
            results.append(("mod:" + name, "import"))

    return results


# ---------------------------------------------------------------------------
# Source text loader (handles common encodings gracefully)
# ---------------------------------------------------------------------------

def _read_source(abs_path: str) -> str:
    """
    Read a source file returning its text content, or "" on failure.

    Tries UTF-8 first (with BOM stripping), falls back to latin-1 which
    never raises a decode error.
    """
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(abs_path, "r", encoding=enc, errors="replace") as fh:
                return fh.read()
        except OSError:
            return ""
    return ""


# ---------------------------------------------------------------------------
# Go module name detection
# ---------------------------------------------------------------------------

def _detect_go_module(project_root: str) -> str:
    """
    Read go.mod in *project_root* and return the module name, or "" if absent.
    """
    go_mod = os.path.join(project_root, "go.mod")
    if not os.path.isfile(go_mod):
        return ""
    try:
        with open(go_mod, "r", encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^\s*module\s+(\S+)", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return ""


# ---------------------------------------------------------------------------
# Node builder
# ---------------------------------------------------------------------------

def _build_node(rel_path: str, abs_path: str) -> Dict:
    """
    Build a graph node dict for one source file.

    *rel_path* must already be POSIX-normalised and project-relative.
    """
    try:
        stat = os.stat(abs_path)
        size = stat.st_size
    except OSError:
        size = 0

    # Count lines without loading entire text into memory for large files
    lines = 0
    try:
        with open(abs_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                lines += chunk.count(b"\n")
    except OSError:
        pass

    directory = _to_posix(posixpath.dirname(rel_path)) or "."

    return {
        "id": rel_path,
        "language": _language_for(rel_path),
        "category": _category_for(rel_path),
        "lines": lines,
        "size": size,
        "directory": directory,
    }


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

def analyze_dependencies(scan: "ProjectScan", project_root: str) -> DependencyGraph:
    """
    Build a :class:`DependencyGraph` from a completed :class:`ProjectScan`.

    Parameters
    ----------
    scan:
        A ``ProjectScan`` object produced by ``xray.scanner``.  Expected to
        expose a ``files`` attribute — a list of file-info dicts with at
        least an ``"abs_path"`` key.  If the scan object instead exposes
        ``files`` as a list of plain path strings, those are handled too.
    project_root:
        Absolute path to the project root directory.  All returned paths are
        relative to this directory, using forward slashes.

    Returns
    -------
    DependencyGraph
        Populated graph with nodes, edges, and external_deps.
    """
    project_root = os.path.normpath(project_root)

    # ------------------------------------------------------------------
    # Step 1: Collect the file list from the scan object.
    # Support both dict-of-info and plain-string layouts.
    # ------------------------------------------------------------------
    raw_files: List[str] = []  # absolute paths
    for entry in getattr(scan, "files", []):
        if isinstance(entry, dict):
            abs_p = entry.get("abs_path") or entry.get("path", "")
            if abs_p:
                raw_files.append(os.path.normpath(abs_p))
        elif isinstance(entry, (str, os.PathLike)):
            raw_files.append(os.path.normpath(str(entry)))
        elif hasattr(entry, "path"):
            # Support dataclass FileInfo with a relative 'path' attribute
            p = str(entry.path)
            if not os.path.isabs(p):
                p = os.path.join(project_root, p)
            raw_files.append(os.path.normpath(p))

    # ------------------------------------------------------------------
    # Step 2: Build node list and file-lookup structures.
    # ------------------------------------------------------------------
    graph = DependencyGraph()

    # Mapping: project-relative POSIX path → absolute path
    file_map: Dict[str, str] = {}
    for abs_path in raw_files:
        rel = _rel_posix(abs_path, project_root)
        # Skip paths that escape the project root (e.g. symlinks)
        if rel.startswith(".."):
            continue
        file_map[rel] = abs_path
        graph.nodes.append(_build_node(rel, abs_path))

    known_files: Set[str] = set(file_map.keys())

    # Quick-access sets per language
    gd_files: List[str] = [p for p in known_files if p.endswith(".gd")]
    cs_files: Set[str] = {p for p in known_files if p.endswith(".cs")}

    # Go module name (may be "" if not a Go project)
    go_module = _detect_go_module(project_root)

    # ------------------------------------------------------------------
    # Step 3: Parse imports and resolve edges.
    # ------------------------------------------------------------------
    external_deps: Set[str] = set()
    edges_set: Set[Tuple[str, str, str]] = set()  # (source, target, type)

    for rel_src, abs_src in file_map.items():
        lang = _language_for(rel_src)
        if lang not in (
            "Python", "JavaScript", "TypeScript", "C#", "GDScript", "Go", "Rust"
        ):
            continue

        source_text = _read_source(abs_src)
        if not source_text:
            continue

        # --- Python ---------------------------------------------------
        if lang == "Python":
            for ref, etype in _parse_python(source_text):
                resolved, is_ext = _resolve_python_import(abs_src, ref, project_root)
                if resolved and resolved in known_files:
                    edges_set.add((rel_src, resolved, etype))
                elif is_ext:
                    top = ref.lstrip(".").split(".")[0]
                    if top:
                        external_deps.add(top)

        # --- JavaScript / TypeScript ----------------------------------
        elif lang in ("JavaScript", "TypeScript"):
            for ref, etype in _parse_javascript(source_text):
                if ref.startswith("./") or ref.startswith("../"):
                    resolved = _resolve_relative(abs_src, ref, project_root)
                    if resolved and resolved in known_files:
                        edges_set.add((rel_src, resolved, etype))
                else:
                    # npm package or bare specifier — external
                    # Strip sub-path (e.g. "lodash/get" → "lodash")
                    pkg = ref.split("/")[0] if not ref.startswith("@") else "/".join(ref.split("/")[:2])
                    if pkg and not pkg.startswith("."):
                        external_deps.add(pkg)

        # --- C# -------------------------------------------------------
        elif lang == "C#":
            for ref, etype in _parse_csharp(source_text):
                targets = _resolve_csharp_namespace(ref, cs_files, project_root)
                for t in targets:
                    if t in known_files and t != rel_src:
                        edges_set.add((rel_src, t, etype))
                if not targets:
                    # Record as external namespace reference
                    top_ns = ref.split(".")[0]
                    # Exclude project-internal namespaces heuristically:
                    # if no file matched, it's likely a framework namespace
                    if top_ns not in {"System", "Microsoft", "Windows", "Newtonsoft"}:
                        external_deps.add(ref)
                    else:
                        external_deps.add(top_ns)

        # --- GDScript -------------------------------------------------
        elif lang == "GDScript":
            for ref, etype in _parse_gdscript(source_text):
                if ref.startswith("res://"):
                    resolved = _resolve_gdscript_res_path(ref, project_root)
                    if resolved and resolved in known_files:
                        edges_set.add((rel_src, resolved, etype))
                elif ref.startswith("class:"):
                    cls_name = ref[len("class:"):]
                    resolved = _resolve_gdscript_class(cls_name, gd_files, project_root)
                    if resolved and resolved in known_files and resolved != rel_src:
                        edges_set.add((rel_src, resolved, etype))

        # --- Go -------------------------------------------------------
        elif lang == "Go":
            for ref, etype in _parse_go(source_text):
                # Skip stdlib / non-local packages
                if "." not in ref and "/" not in ref:
                    continue
                resolved = _resolve_go_import(ref, go_module, project_root)
                if resolved and resolved in known_files and resolved != rel_src:
                    edges_set.add((rel_src, resolved, etype))
                elif not resolved:
                    # External module — record top-level domain/package
                    parts = ref.split("/")
                    if parts:
                        external_deps.add(parts[0] if "." in parts[0] else ref)

        # --- Rust -----------------------------------------------------
        elif lang == "Rust":
            for ref, etype in _parse_rust(source_text):
                if ref.startswith("mod:"):
                    mod_name = ref[len("mod:"):]
                    resolved = _resolve_rust_mod(mod_name, abs_src, project_root)
                    if resolved and resolved in known_files and resolved != rel_src:
                        edges_set.add((rel_src, resolved, etype))
                else:
                    # use crate:: / super:: / self::
                    if (
                        ref.startswith("crate::")
                        or ref.startswith("super::")
                        or ref.startswith("self::")
                    ):
                        resolved = _resolve_rust_use(ref, abs_src, project_root)
                        if resolved and resolved in known_files and resolved != rel_src:
                            edges_set.add((rel_src, resolved, etype))
                    else:
                        # External crate — record crate name
                        crate_name = ref.split("::")[0]
                        external_deps.add(crate_name)

    # ------------------------------------------------------------------
    # Step 4: Materialise edges (deduplication already done via set).
    # ------------------------------------------------------------------
    for src, tgt, etype in sorted(edges_set):
        graph.edges.append({"source": src, "target": tgt, "type": etype})

    # ------------------------------------------------------------------
    # Step 5: Finalise external deps list (sorted, deduplicated).
    # Filter out empty strings from any regex edge-case.
    # ------------------------------------------------------------------
    graph.external_deps = sorted(d for d in external_deps if d)

    return graph
