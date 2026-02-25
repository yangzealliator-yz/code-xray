# Code X-Ray

> One command to X-ray any codebase. Generate a visual dashboard with dependency graphs, file treemaps, git heatmaps, and project statistics.

## Quick Start

```bash
# Clone and run
git clone https://github.com/user/code-xray.git
cd code-xray

# Scan any project
python xray.py /path/to/your/project

# Open the generated dashboard
# → xray-report.html
```

No dependencies required — Python 3.8+ only.

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
python xray.py [path] [options]

Arguments:
  path                  Project to scan (default: current directory)

Options:
  -o, --output PATH     Output HTML file (default: xray-report.html)
  --json [PATH]         Also output raw JSON data
  --no-git              Skip git history analysis
  --exclude DIR [DIR…]  Additional directories to exclude
  --max-depth N         Limit scan depth
  --max-files N         Limit number of files
  --version             Show version
```

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
python xray.py . --ai                      # Compact JSON for LLM context
python xray.py . --ai --deep signatures    # + function signatures
python xray.py . --ai --prompt arch        # Complete prompt + data
python xray.py . --ai --prompt arch | llm  # Pipe directly to any LLM
```

## License

MIT — see [LICENSE](./LICENSE).

---

Inspired by real-world large-scale project analysis practices.
