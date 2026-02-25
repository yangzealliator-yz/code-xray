"""
git_stats.py — Git history analyzer for Code X-Ray.

Provides file-level commit statistics and age information derived from
``git log`` output.  All functions degrade gracefully: if git is not
installed or the directory is not a git repository every function returns
an empty dict without raising an exception.

Python 3.8+ | Zero external dependencies | Works on Windows, macOS, Linux.
"""

import os
import subprocess
from collections import defaultdict
from typing import Dict, Set


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_path(path: str) -> str:
    """Return *path* with all backslashes replaced by forward slashes.

    Git itself always emits forward-slash paths, but on Windows the working
    tree paths reported by the scanner may use backslashes.  Normalising to
    forward slashes before any comparison keeps the two namespaces consistent.

    Args:
        path: A file path string, possibly containing backslashes.

    Returns:
        The same path with every ``\\`` replaced by ``/``.
    """
    return path.replace("\\", "/")


def _run_git(args: list, cwd: str) -> str:
    """Execute a git command and return its stdout as a string.

    The function swallows *all* exceptions so that callers never have to
    handle git-related errors.

    Args:
        args: List of command tokens, e.g. ``["git", "log", "--oneline"]``.
        cwd:  Working directory in which the command is executed.

    Returns:
        The decoded stdout of the process, or an empty string if the command
        failed for any reason (git not found, not a repo, permission error,
        timeout, etc.).
    """
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout
        return ""
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        # git not installed, cwd does not exist, or command timed out
        return ""
    except Exception:
        # Catch-all to ensure callers always receive a safe return value
        return ""


def _is_git_repo(project_root: str) -> bool:
    """Return True if *project_root* contains a ``.git`` directory or file.

    A ``.git`` *file* (instead of a directory) indicates a git worktree or a
    submodule, which is still a valid git context.

    Args:
        project_root: Absolute or relative path to the project directory.

    Returns:
        ``True`` when a ``.git`` entry is present; ``False`` otherwise.
    """
    git_entry = os.path.join(project_root, ".git")
    return os.path.exists(git_entry)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_git_stats(project_root: str, days: int = 90) -> Dict[str, dict]:
    """Analyse git history for all files modified within the last *days* days.

    Runs ``git log --name-only`` and parses the structured output to build a
    per-file summary that includes commit count, the date of the most recent
    commit, and the set of unique contributors.

    The function is intentionally *read-only* and *side-effect-free*: it never
    writes to disk, modifies repository state, or raises an exception.

    Args:
        project_root:
            Path to the root of the project.  Must point to a directory that
            contains (or is inside) a git repository.
        days:
            How far back in history to look.  Defaults to 90 days.
            Must be a positive integer; non-positive values are clamped to 1.

    Returns:
        A dictionary keyed by normalised file path (forward slashes, relative
        to the repository root).  Each value is a dict with the keys:

        - ``"commits"`` (int): number of commits that touched this file.
        - ``"last_modified"`` (str): ISO-8601 date-time string of the most
          recent commit that touched the file.
        - ``"contributors"`` (list[str]): deduplicated list of author names.

        Returns an empty dict ``{}`` when:

        - *project_root* does not exist or is not a git repository.
        - git is not installed.
        - The git command fails for any other reason.

    Example::

        stats = get_git_stats("/path/to/project", days=30)
        for path, info in stats.items():
            print(path, info["commits"], info["contributors"])
    """
    if not _is_git_repo(project_root):
        return {}

    days = max(1, int(days))

    raw = _run_git(
        [
            "git",
            "log",
            "--name-only",
            "--format=%H|%an|%ai",
            f"--since={days} days ago",
        ],
        cwd=project_root,
    )

    if not raw.strip():
        return {}

    # -----------------------------------------------------------------------
    # Parse the raw output.
    #
    # git log --name-only emits blocks separated by blank lines.  Each block
    # looks like:
    #
    #   <hash>|<author>|<date>      ← header line (matches --format)
    #   <empty line>
    #   path/to/file_a              ← one file per line
    #   path/to/file_b
    #
    # Multiple commits are separated by a blank line before the next header.
    # -----------------------------------------------------------------------

    # Intermediate accumulator using mutable defaults
    file_commits: Dict[str, int] = defaultdict(int)
    file_last_modified: Dict[str, str] = {}
    file_contributors: Dict[str, Set[str]] = defaultdict(set)

    current_author: str = ""
    current_date: str = ""

    for raw_line in raw.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        # Check whether this line is a commit header produced by --format.
        # Headers look like: <40-hex-hash>|<author>|<date>
        if "|" in line:
            parts = line.split("|", 2)
            if len(parts) == 3 and len(parts[0]) == 40:
                _commit_hash, current_author, current_date = parts
                continue

        # Any non-empty, non-header line is a file path
        if current_date:
            norm = _normalize_path(line)

            file_commits[norm] += 1

            # Keep the most recent date encountered for each file.
            # git log emits commits in reverse-chronological order so the
            # *first* date seen for a file is already the most recent.
            if norm not in file_last_modified:
                file_last_modified[norm] = current_date

            if current_author:
                file_contributors[norm].add(current_author)

    # Merge the three intermediate mappings into the final result structure
    result: Dict[str, dict] = {}
    for filepath in file_commits:
        result[filepath] = {
            "commits": file_commits[filepath],
            "last_modified": file_last_modified.get(filepath, ""),
            "contributors": sorted(file_contributors[filepath]),
        }

    return result


def get_file_ages(project_root: str) -> Dict[str, str]:
    """Return the first-commit date for every file tracked by git.

    Uses ``git log --diff-filter=A`` which restricts output to commits in
    which each file was *Added* for the first time.  The result approximates
    the "creation date" of each file within the repository.

    Args:
        project_root:
            Path to the root of the project.  Must point to a directory that
            contains (or is inside) a git repository.

    Returns:
        A dictionary mapping normalised file paths (forward slashes) to their
        first-commit date as an ISO-8601 string.

        Returns an empty dict ``{}`` when:

        - *project_root* does not exist or is not a git repository.
        - git is not installed or the command fails.
        - The repository has no commits.

    Example::

        ages = get_file_ages("/path/to/project")
        oldest = min(ages.items(), key=lambda kv: kv[1], default=None)
        if oldest:
            print(f"Oldest file: {oldest[0]} added on {oldest[1]}")
    """
    if not _is_git_repo(project_root):
        return {}

    raw = _run_git(
        [
            "git",
            "log",
            "--diff-filter=A",
            "--name-only",
            "--format=%ai",
        ],
        cwd=project_root,
    )

    if not raw.strip():
        return {}

    # -----------------------------------------------------------------------
    # Parse the output.
    #
    # With --format="%ai" and --name-only the output looks like:
    #
    #   2023-04-01 12:00:00 +0000   ← date line (header, no | separator)
    #
    #   path/to/newly_added_file    ← file(s) added in that commit
    #
    # Because --diff-filter=A is used, each file appears at most once.
    # -----------------------------------------------------------------------

    result: Dict[str, str] = {}
    current_date: str = ""
    in_file_section: bool = False

    for raw_line in raw.splitlines():
        line = raw_line.strip()

        if not line:
            in_file_section = False
            continue

        # A date line produced by --format="%ai" starts with a 4-digit year
        # and contains spaces but no pipe characters.
        if "|" not in line and len(line) >= 10 and line[:4].isdigit() and not in_file_section:
            current_date = line
            in_file_section = True
            continue

        # File path line
        if in_file_section and current_date:
            norm = _normalize_path(line)
            # Only record the first occurrence (earliest addition)
            if norm not in result:
                result[norm] = current_date

    return result
