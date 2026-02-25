# /xray — Project X-Ray Analysis

Scan the current project and provide architectural insights.

## Usage

```
/xray                    # Full scan with AI analysis
/xray --deep signatures  # Include function signatures
/xray --deep keys        # Include config key structures
/xray --no-git           # Skip git history
```

## Instructions

Run Code X-Ray on the current project and analyze the results:

```bash
python "$REPO_ROOT/xray.py" $ARGUMENTS --ai --no-git
```

Based on the JSON output above, provide:

1. **Architecture Overview**: Project type, patterns, and structure
2. **Core Modules**: Most important files by size, connections, and centrality
3. **Dependency Analysis**: Import relationships, coupling, potential cycles
4. **Recommendations**: Top 3 actionable improvements

Keep the analysis concise and actionable. Reference specific files and line counts.
