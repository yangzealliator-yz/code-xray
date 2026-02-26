# Code X-Ray

> One command to X-ray any codebase. Generate a visual dashboard with dependency graphs, file treemaps, git heatmaps, and project statistics.

**Live Demo**: [Flask dashboard](https://yangzealliator-yz.github.io/code-xray/demo-flask.html) | [Self-scan](https://yangzealliator-yz.github.io/code-xray/demo-self.html)

## Installation

### Option 1: pip install (recommended)

```bash
pip install code-xray

# Then use anywhere:
xray /path/to/your/project
```

### Option 2: pip install from GitHub

```bash
pip install git+https://github.com/yangzealliator-yz/code-xray.git
```

### Option 3: pip install from Gitee (China mirror)

```bash
pip install git+https://gitee.com/yangzealliator/code-xray.git
```

### Option 4: Clone and run directly

```bash
# GitHub
git clone https://github.com/yangzealliator-yz/code-xray.git

# Gitee (China mirror / 国内镜像)
git clone https://gitee.com/yangzealliator/code-xray.git

cd code-xray
python xray.py /path/to/your/project
```

No dependencies required — Python 3.8+ only.

> **Note**: `xray` is a **terminal command** — run it in your system shell (cmd / PowerShell / bash), **not** inside the Python `>>>` interpreter. If you see `SyntaxError: invalid syntax`, you're in the wrong place. Type `exit()` to leave Python first.

## Quick Start

```bash
# After pip install:
xray .                          # Scan current directory
xray /path/to/project           # Scan any project
xray . -o my-report.html        # Custom output path

# Or run directly from clone:
python xray.py /path/to/project

# Open the generated dashboard
# → xray-report.html
```

## Features

Code X-Ray generates a single self-contained HTML dashboard with 4 interactive views:

| View | Description |
|------|-------------|
| **Treemap** | File sizes by language, nested by directory |
| **Force Graph** | Dependency relationships between files |
| **Heatmap** | Git activity hotspots (commit frequency) |
| **Stats** | Language breakdown, file counts, line totals |

All visualizations powered by D3.js. Works offline after generation.

## CLI Usage

```
xray [path] [options]

Arguments:
  path                  Project to scan (default: current directory)

Options:
  -o, --output PATH     Output HTML file (default: xray-report.html)
  --json [PATH]         Also output raw JSON data
  --no-git              Skip git history analysis
  --exclude DIR [DIR…]  Additional directories to exclude
  --max-depth N         Limit scan depth
  --max-files N         Limit number of files
  --ai                  Output LLM-friendly JSON instead of HTML
  --deep MODE           Depth for --ai (keys/signatures/ai-config)
  --prompt TYPE         Output a complete prompt for LLM (arch/deps/refactor)
  --version             Show version
```

> After `pip install`, use `xray` or `code-xray` commands. From a git clone, use `python xray.py`.

## Configuration

Create a `.xrayrc` file in your project root (JSON format):

```json
{
    "exclude_dirs": ["vendor", "third_party"],
    "max_depth": 10,
    "max_files": 5000
}
```

CLI arguments override `.xrayrc` settings. See `.xrayrc.example` for all options.

## Supported Languages

Python, JavaScript, TypeScript, C#, Go, Rust, Java, Kotlin, Swift, Dart, C, C++, GDScript, Lua, Ruby, PHP, HTML, CSS, SCSS, Less, Shell, PowerShell, SQL, R, Elixir, Haskell, Scala, Zig, WGSL, GLSL, HLSL, and more (30+ languages).

## How It Works

1. **Scan** — Walks the directory tree, classifying files by language and category
2. **Analyze** — Parses import statements across 6 languages to build a dependency graph
3. **Git Stats** — Reads recent git history for commit frequency and contributor data
4. **Render** — Injects all data into a D3.js template to produce a single HTML file

## FAQ

**Q: I get `SyntaxError: invalid syntax` when running `xray`?**
A: You are typing the command inside the Python interpreter (`>>>` prompt). `xray` is a system terminal command. Exit Python first (`exit()` or Ctrl+Z), then run `xray` in cmd / PowerShell / bash. Alternatively, use `python -m xray /path/to/project` if you prefer the Python module style.

**Q: Does it upload my code anywhere?**
A: No. Everything runs locally. The output HTML is self-contained.

**Q: How fast is it?**
A: Typically < 5 seconds for projects with 1000+ files.

**Q: What about binary files?**
A: Binary files (images, fonts, etc.) are listed but not analyzed for content.

## Limitations

- Import parsing covers 6 languages (Python, JS/TS, C#, GDScript, Go, Rust). Others show in the treemap but without dependency edges.
- Git stats require a git repository. Non-git projects get a degraded heatmap.
- Very large monorepos (100K+ files) may benefit from `--max-files` to limit scope.

## Claude Code Integration

Use Code X-Ray directly inside Claude Code with the `/xray` slash command:

**Install** (one command):
```bash
# Copy the slash command to your Claude Code commands directory
cp -r /path/to/code-xray/.claude/commands/xray.md ~/.claude/commands/
```

**Usage**:
```
/xray                    # Full project scan + AI analysis
/xray --deep signatures  # Include function/class signatures
/xray --deep keys        # Include config file key structures
```

Claude will automatically scan your project and provide architectural insights, dependency analysis, and improvement recommendations — all without leaving your terminal.

### LLM-Friendly Output

Code X-Ray includes AI-optimized output modes for any LLM:

```bash
xray . --ai                      # Compact JSON for LLM context
xray . --ai --deep signatures    # + function signatures
xray . --ai --prompt arch        # Complete prompt + data
xray . --ai --prompt arch | llm  # Pipe directly to any LLM
```

## License

MIT — see [LICENSE](./LICENSE).

---

Inspired by real-world large-scale project analysis practices.
