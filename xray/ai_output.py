"""
ai_output.py — LLM-friendly output generation for Code X-Ray.

Provides tiered depth levels of project structure data optimized for
large language model consumption.
"""

import json
import os
import re
from typing import Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Config file extensions to extract keys from (L1)
CONFIG_EXTENSIONS = {
    "package.json", "tsconfig.json", "pyproject.toml", "setup.cfg",
    "Cargo.toml", "go.mod", "composer.json", "Gemfile",
    ".eslintrc.json", ".prettierrc", "jest.config.js",
}
CONFIG_EXT_PATTERNS = {".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"}

# Sensitive files to never read content from
SENSITIVE_PATTERNS = {".env", "credentials", "secret", "key.pem", ".pem"}

# AI config files (L3) - exact name matches
AI_CONFIG_EXACT = {
    "CLAUDE.md", ".cursorrules", ".windsurfrules", "SKILLS.md", "SKILL.md",
}

# AI config directory prefixes
AI_CONFIG_DIRS = {".claude/", ".cursor/", ".github/"}

# AI config glob patterns
AI_CONFIG_GLOBS = {
    ".claude/commands/", ".claude/settings", ".github/copilot-",
}

# Content signal words for AI config detection (L3)
AI_SIGNAL_WORDS = {
    "you are", "# system prompt", "## rules", "hooks", "tool_choice",
    "slash command", "mcp server", "assistant behavior", "code style",
}

# Signature extraction patterns (L2)
_SIGNATURE_PATTERNS = {
    "python": re.compile(r"^\s*(def|class|async def)\s+\w+.*?[:(]"),
    "javascript": re.compile(r"^\s*(function|class|const\s+\w+\s*=\s*(?:async\s+)?\(|export\s+(?:default\s+)?(?:function|class))\s*\w*"),
    "typescript": re.compile(r"^\s*(function|class|interface|type|const\s+\w+\s*=\s*(?:async\s+)?\(|export\s+(?:default\s+)?(?:function|class|interface|type))\s*\w*"),
    "csharp": re.compile(r"^\s*(public|private|protected|internal|static|abstract|virtual|override|async)?\s*(class|interface|struct|enum|void|int|string|bool|float|Task)\s+\w+"),
    "go": re.compile(r"^\s*(func|type)\s+\w+"),
    "rust": re.compile(r"^\s*(pub\s+)?(fn|struct|enum|trait|impl|type)\s+\w+"),
}


def _is_sensitive(path: str) -> bool:
    """Check if a file path matches sensitive patterns."""
    lower = path.lower()
    base = os.path.basename(lower)
    for pat in SENSITIVE_PATTERNS:
        if pat in base:
            return True
    return False


def _extract_keys(filepath: str, max_depth: int = 3) -> List[str]:
    """Extract JSON/TOML config keys (without values) from a file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(50000)  # 50KB limit
    except OSError:
        return []

    if filepath.endswith(".json"):
        try:
            data = json.loads(content)
            return _flatten_keys(data, max_depth=max_depth)
        except json.JSONDecodeError:
            return []

    # For YAML/TOML/INI, extract key-like patterns
    keys = []
    for line in content.splitlines()[:200]:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        match = re.match(r'^[\["]?([a-zA-Z_][\w.\-]*)', line)
        if match:
            keys.append(match.group(1))
    return keys[:100]


def _flatten_keys(obj, prefix: str = "", max_depth: int = 3, depth: int = 0) -> List[str]:
    """Flatten nested dict/list keys."""
    if depth >= max_depth:
        if isinstance(obj, dict):
            return [f"{prefix}.*{len(obj)}"]
        return []

    keys = []
    if isinstance(obj, dict):
        for k in obj:
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(obj[k], dict):
                keys.extend(_flatten_keys(obj[k], full_key, max_depth, depth + 1))
            elif isinstance(obj[k], list):
                keys.append(f"{full_key}[{len(obj[k])}]")
            else:
                keys.append(full_key)
    return keys


def _extract_signatures(filepath: str, language: str) -> List[str]:
    """Extract function/class signatures from a source file."""
    pattern = _SIGNATURE_PATTERNS.get(language.lower())
    if not pattern:
        return []

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return []

    sigs = []
    for line in lines:
        if pattern.match(line):
            sig = line.rstrip()
            # Trim trailing '{' or ':' for cleaner output
            sig = re.sub(r'\s*[{:]\s*$', '', sig).strip()
            if sig:
                sigs.append(sig)
    return sigs


def _is_ai_config(filepath: str, rel_path: str) -> bool:
    """Check if a file is an AI configuration file."""
    basename = os.path.basename(filepath)

    # Exact name match
    if basename in AI_CONFIG_EXACT:
        return True

    # Directory match
    rel_lower = rel_path.replace("\\", "/").lower()
    for d in AI_CONFIG_DIRS:
        if rel_lower.startswith(d):
            return True

    return False


def _detect_ai_config_by_content(filepath: str) -> bool:
    """Detect AI config files by reading first 20 lines for signal words."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            head = ""
            for i, line in enumerate(f):
                if i >= 20:
                    break
                head += line
    except OSError:
        return False

    head_lower = head.lower()
    hits = sum(1 for w in AI_SIGNAL_WORDS if w in head_lower)
    return hits >= 2  # At least 2 signal words


def _read_ai_config(filepath: str) -> Optional[str]:
    """Read AI config file content (with size limit)."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(100000)  # 100KB limit
    except OSError:
        return None


def extract_ai_output(
    scan,
    deps,
    project_root: str,
    deep: Optional[str] = None,
) -> dict:
    """Generate LLM-friendly output at the specified depth level.

    Args:
        scan: ProjectScan from scanner.
        deps: DependencyGraph from analyzer.
        project_root: Absolute path to the project.
        deep: None for L0, or "keys"/"signatures"/"ai-config" for deeper levels.

    Returns:
        Dict with project structure optimized for LLM consumption.
    """
    project_name = os.path.basename(project_root) or "project"

    # --- L0: Core structure ---
    nodes = []
    for f in scan.files:
        path = getattr(f, "path", str(f))
        nodes.append({
            "path": path,
            "lang": getattr(f, "language", "unknown"),
            "lines": getattr(f, "line_count", 0),
        })

    # Sort by lines descending for LLM prioritization
    nodes.sort(key=lambda n: -n["lines"])

    # Auto-trim for large projects (keep top 500 files)
    if len(nodes) > 500:
        nodes = nodes[:500]

    edges = []
    if deps and hasattr(deps, "edges"):
        for e in deps.edges:
            if isinstance(e, dict):
                edges.append({"src": e.get("source", ""), "tgt": e.get("target", "")})

    # Language summary
    lang_counts: Dict[str, int] = {}
    for n in nodes:
        lang_counts[n["lang"]] = lang_counts.get(n["lang"], 0) + 1
    lang_counts.pop("unknown", None)

    result = {
        "project": project_name,
        "files": len(scan.files),
        "total_lines": sum(getattr(f, "line_count", 0) for f in scan.files),
        "languages": lang_counts,
        "nodes": nodes,
        "edges": edges,
    }

    # --- L1: Config keys ---
    if deep == "keys":
        config_keys: Dict[str, List[str]] = {}
        for f in scan.files:
            path = getattr(f, "path", str(f))
            basename = os.path.basename(path)
            _, ext = os.path.splitext(path)
            if basename in CONFIG_EXTENSIONS or ext in CONFIG_EXT_PATTERNS:
                if _is_sensitive(path):
                    continue
                abs_path = os.path.join(project_root, path)
                keys = _extract_keys(abs_path)
                if keys:
                    config_keys[path] = keys
        result["config_keys"] = config_keys

    # --- L2: Signatures ---
    elif deep == "signatures":
        all_sigs: Dict[str, List[str]] = {}
        for f in scan.files:
            path = getattr(f, "path", str(f))
            lang = getattr(f, "language", "unknown")
            abs_path = os.path.join(project_root, path)
            sigs = _extract_signatures(abs_path, lang)
            if sigs:
                all_sigs[path] = sigs
        result["signatures"] = all_sigs

    # --- L3: AI config files ---
    elif deep == "ai-config":
        ai_configs: Dict[str, str] = {}
        for f in scan.files:
            path = getattr(f, "path", str(f))
            abs_path = os.path.join(project_root, path)
            if _is_sensitive(path):
                continue
            if _is_ai_config(abs_path, path) or _detect_ai_config_by_content(abs_path):
                content = _read_ai_config(abs_path)
                if content:
                    ai_configs[path] = content
        result["ai_configs"] = ai_configs

    return result


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

PROMPTS = {
    "arch": """You are a senior software architect. Analyze this project structure and provide:

1. **Architecture Overview**: What type of project is this? What patterns does it use?
2. **Core Modules**: Which are the most important files/modules and why?
3. **Dependency Hotspots**: Which files have the most connections?
4. **Potential Issues**: Any architectural concerns (circular deps, god objects, etc.)?

Project data:
```json
{data}
```""",

    "deps": """You are a dependency health expert. Analyze these project dependencies:

1. **Circular Dependencies**: Are there any import cycles?
2. **Coupling**: Which modules are too tightly coupled?
3. **Orphans**: Are there files with zero connections?
4. **Recommendations**: Suggest dependency improvements.

Project data:
```json
{data}
```""",

    "refactor": """You are a refactoring advisor. Based on this project structure:

1. **Refactoring Priorities**: Which files need attention most? (by size, complexity, coupling)
2. **Extract Opportunities**: Any large files that should be split?
3. **Dead Code Candidates**: Files with zero incoming dependencies?
4. **Quick Wins**: Simple improvements with high impact.

Project data:
```json
{data}
```""",
}


def build_prompt(name: str, data: dict) -> str:
    """Build a complete prompt with data injected."""
    template = PROMPTS.get(name, PROMPTS["arch"])
    data_str = json.dumps(data, ensure_ascii=False, indent=2)
    return template.replace("{data}", data_str)
