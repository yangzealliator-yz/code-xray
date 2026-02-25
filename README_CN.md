# Code X-Ray

> 一行命令透视任何代码库。生成包含依赖图、文件树图、Git 热力图和项目统计的可视化看板。

## 安装

### 方式一：pip 安装（推荐）

```bash
pip install code-xray

# 然后随处使用：
xray /path/to/your/project
```

### 方式二：从 GitHub 安装

```bash
pip install git+https://github.com/yangzealliator-yz/code-xray.git
```

### 方式三：从 Gitee 安装（国内镜像，无需 VPN）

```bash
pip install git+https://gitee.com/yangzealliator/code-xray.git
```

### 方式四：克隆源码直接运行

```bash
# GitHub
git clone https://github.com/yangzealliator-yz/code-xray.git

# Gitee（国内镜像）
git clone https://gitee.com/yangzealliator/code-xray.git

cd code-xray
python xray.py /path/to/your/project
```

零外部依赖 — 仅需 Python 3.8+。

## 快速开始

```bash
# pip 安装后：
xray .                          # 扫描当前目录
xray /path/to/project           # 扫描任意项目
xray . -o my-report.html        # 自定义输出路径

# 或从源码直接运行：
python xray.py /path/to/project

# 打开生成的看板
# → xray-report.html
```

## 功能特性

Code X-Ray 生成单个自包含 HTML 看板，包含 4 个交互式视图：

| 视图 | 说明 |
|------|------|
| **树图 (Treemap)** | 按语言分色的文件大小树图，按目录嵌套 |
| **力导图 (Force Graph)** | 文件间的依赖关系可视化 |
| **热力图 (Heatmap)** | Git 活动热点（提交频率） |
| **统计 (Stats)** | 语言分布、文件数量、代码行数汇总 |

所有可视化基于 D3.js。生成后可离线查看。

## CLI 用法

```
xray [路径] [选项]

参数:
  路径                   要扫描的项目（默认：当前目录）

选项:
  -o, --output 路径      输出 HTML 文件（默认：xray-report.html）
  --json [路径]          同时输出 JSON 原始数据
  --no-git               跳过 Git 历史分析
  --exclude 目录 [目录…]  额外排除的目录
  --max-depth N          限制扫描深度
  --max-files N          限制文件数量
  --ai                   输出 LLM 友好 JSON（替代 HTML）
  --deep 模式            --ai 深度（keys/signatures/ai-config）
  --prompt 类型          输出完整 LLM 分析 prompt（arch/deps/refactor）
  --version              显示版本号
```

> `pip install` 后使用 `xray` 或 `code-xray` 命令。从源码克隆则使用 `python xray.py`。

## 配置文件

在项目根目录创建 `.xrayrc` 文件（JSON 格式）：

```json
{
    "exclude_dirs": ["vendor", "third_party"],
    "max_depth": 10,
    "max_files": 5000
}
```

CLI 参数优先于 `.xrayrc` 配置。详见 `.xrayrc.example`。

## 支持的语言

Python、JavaScript、TypeScript、C#、Go、Rust、Java、Kotlin、Swift、Dart、C、C++、GDScript、Lua、Ruby、PHP、HTML、CSS、SCSS、Less、Shell、PowerShell、SQL、R、Elixir、Haskell、Scala、Zig、WGSL、GLSL、HLSL 等（30+ 种语言）。

## 工作原理

1. **扫描** — 遍历目录树，按语言和类型分类文件
2. **分析** — 解析 6 种语言的 import 语句，构建依赖图
3. **Git 统计** — 读取近期 Git 历史，获取提交频率和贡献者数据
4. **渲染** — 将所有数据注入 D3.js 模板，生成单个 HTML 文件

## 常见问题

**Q: 会上传我的代码吗？**
A: 不会。所有处理在本地完成，输出 HTML 完全自包含。

**Q: 速度如何？**
A: 1000+ 文件的项目通常 < 5 秒。

**Q: 二进制文件怎么处理？**
A: 二进制文件（图片、字体等）会被列出但不分析内容。

## 局限性

- Import 解析覆盖 6 种语言（Python、JS/TS、C#、GDScript、Go、Rust）。其他语言在树图中显示但无依赖边。
- Git 统计需要 Git 仓库。非 Git 项目热力图会降级。
- 超大型 monorepo（10万+ 文件）建议使用 `--max-files` 限制范围。

## Claude Code 集成

在 Claude Code 中直接使用 `/xray` 斜杠命令：

**安装**（一行命令）：
```bash
cp -r /path/to/code-xray/.claude/commands/xray.md ~/.claude/commands/
```

**使用**：
```
/xray                    # 全项目扫描 + AI 分析
/xray --deep signatures  # 包含函数/类签名
/xray --deep keys        # 包含配置文件 key 结构
```

### LLM 友好输出

```bash
xray . --ai                      # 紧凑 JSON 适合 LLM 上下文
xray . --ai --deep signatures    # + 函数签名
xray . --ai --prompt arch        # 完整 prompt + 数据
xray . --ai --prompt arch | llm  # 直接管道到任何 LLM
```

## 许可证

MIT — 详见 [LICENSE](./LICENSE)。

---

灵感来源于大规模项目分析实践经验。
