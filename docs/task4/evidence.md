# 运行证据与复现（Task 4）

本页汇总第 4 章六个实验的学习版实测数字、环境限制与复现方式。**书方历史验收记录不冒认为本人运行结果**：
文中的数字全部来自本机 `learning/task4/runs/` 的运行目录，逐条带 SHA-256；课程 `validation/` 下的
书方证据未被触碰（见文末"证据纪律"）。

- 事实依据：本地仓库提交 `cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c`
- 运行时间：2026-09-21
- 文本模型：DeepSeek `deepseek-flash`（thinking 关闭、temperature 0）
- 视觉 / 评审 / 子 Agent / 危险审查：DashScope `qwen-vl-max`、`qwen3.7-plus`（国内端点）
- 离线审计：`learning/task4/audit_learning.py` → **59/59 通过**（不联网、不调用模型）

## 4-1

| 项 | 值 |
| --- | --- |
| 运行目录（canonical） | `learning/task4/runs/4-1_active_tool_discovery/20260921T112402Z/` |
| evidence.json SHA-256 | 见 [assets 里的 evidence.sha256](../assets/task4/tool-discovery-evidence.sha256) |
| MCP 目录 | 127 工具（`perception-tools`，57 原生 + 70 扩展），50,597 schema token（tiktoken o200k），208,614 字节 |
| 嵌入索引 | `sentence-transformers/all-MiniLM-L6-v2`，127 向量 × 384 维，本地 `local_files_only` |
| control | 准确率 1.00（3/3 槽位）、完成 2/3、46s；prompt token 1,021,060（缓存命中 1,011,072）、completion 1,273；system prompt 50,825 token |
| treatment | 准确率 0.83、完成 2/3、47s；prompt token 169,869（命中 161,020）、completion 3,590 |
| 动态注入 token | 1,928（股价）/ 3,884（arXiv）/ 2,623（GitHub） |
| 门禁 | 10/12（两项因 GitHub 403 与 arXiv 任务未完成而 false） |

**留证的三次运行**（GitHub 未认证 API 限流 60 次/小时，两臂受影响不对称）：

| 运行 | control 完成 | treatment 完成 | 备注 |
| --- | ---: | ---: | --- |
| `20260921T111856Z` | 2/3 | 1/3 | 首轮：两臂 GitHub 题均 403 |
| `20260921T112134Z` | 2/3 | 2/3 | 次轮：treatment 的 GitHub 题仍 403，arXiv 题检索错配 |
| `20260921T112402Z` | 2/3 | 2/3 | 第三轮：treatment 的 GitHub 题拿到配额完成，control 仍 403 |

复现：`.venv/bin/python learning/task4/run_4_1_tool_discovery.py`（约 1.5 分钟；首次运行需要联网下载
MiniLM 权重与 tiktoken 的 o200k BPE）。

## 4-2

| 项 | 值 |
| --- | --- |
| 运行目录 | `.../4-2_perception_tools/20260921T111348Z/`（首轮）、`20260921T112643Z/`（次轮） |
| 目录 | 127 工具（`server_version` 为空字符串，`mcp_sdk_version` 2.2.0） |
| 首轮门禁 | 8/11；search ✅、filesystem ✅（3 条逃逸探针全部 PermissionError）、multimodal 7/9、public_data 3/5、private_data blocked |
| 次轮门禁 | 7/11；`web_search` 也被 DuckDuckGo 限流 |
| 视觉实测 | `image_analyze` 4.2s、`video_analyze` 1.8s（qwen-vl-max，读出夹具里的文字） |
| 未过项归类 | 缺本地依赖：`image_ocr`（tesseract 未装）、`audio_transcribe`（whisper 未装）；外部限流：`yfinance_quote`（YFRateLimitError）、`wikipedia_search`（MediaWiki 429/非 JSON）；无凭据：`calendar_events`、`notion_search` |

注意一个**分类边界**：课程的 `credential_blocked()` 靠错误串词表（`missing_credentials`、
`missing_library`、`not configured`…）判定"这是缺凭据"，而 `pytesseract` 与 whisper 的报错文本是
`not installed`，不在词表里——所以这两项被记为 **failed** 而不是 **blocked**。这是词表覆盖面的问题，
不是工具本身的缺陷，读 `summary.json` 时要留意。

复现：`.venv/bin/python learning/task4/run_4_2_perception.py`（约 1 分钟）。需要 macOS 的 `say`
与 `ffmpeg` 造夹具；`DASHSCOPE_BASE_URL` 必须是本机 key 有效的那个区域端点。

## 4-3

| 范式 | 精确判分 | 外部评审 | 平均延迟 |
| --- | ---: | ---: | ---: |
| native-multimodal（qwen-vl-max） | 1.00 | 1.00 | 3,519 ms |
| extract-to-text（deepseek-flash） | 0.00 | 0.00 | 1,136 ms |
| tool-on-demand（deepseek 决策 + qwen-vl 看） | 1.00 | 1.00 | 7,696 ms |

- 运行目录：`.../4-3_multimodal/20260921T111923Z/`，门禁 **9/9**；
- 12 行矩阵（2 工件 × 2 问题 × 3 范式），工具化臂 4 行全部调用工具，每次 1 次；
- PDF 正文提取 359 字符，**不含** `$180/$95/$85`（硬门禁 `chart_answers_absent_from_pdf_body_text`）；
- PNG 提取为空（`unavailable-no-ocr`：本机没有 tesseract），提取为文本臂在 PNG 上的 0.00 被环境放大；
- 跨厂商评审：视觉产出的行由 DeepSeek 评、文本产出的行由 DashScope `qwen3.7-plus` 评。

复现：`.venv/bin/python learning/task4/run_4_3_multimodal.py`（约 1 分钟）。

## 4-4

运行目录：`.../4-4_execution_tools/20260921T112329Z/`，**status = blocked**，core 10 条门禁全过。

| 证据 | 实测 |
| --- | --- |
| MCP 目录 + 收据 | 12 个工具（`server.py` 的 `types.Tool(` 注册点与实连 `list_tools()` 均为 12）、20 条收据 |
| Docker 沙盒 | `kind=docker`、`image=python:3.11-slim`、`network=none`、`read-only`、`memory=256m`、`cpus=1`、`pids_limit=64` |
| 断网探针 | 沙盒内访问 example.com → `URLError` |
| 危险审查 | 2 次真实 LLM 调用（`rm -rf`、代码执行审批），token 1,634 / 1,228 |
| 长输出 | 260 行被截断（上下文里带省略提示），全量 2,340 字节另存文件 |
| Excel | xlsx 5,078 字节 → LibreOffice 转 PDF → PyMuPDF 渲染截图 |
| Webhook | postman-echo 回显 `{"experiment":"4-4","marker":"REAL-WEBHOOK-RECEIPT"}` |
| 浏览器 | Playwright headless，example.com status 200、title `Example Domain`、截图落盘 |
| blocked ×5 | 日历（无凭据）、GitHub PR（无 token）、邮件（课程硬编码 False）、虚拟桌面（macOS 无 X11）、虚拟手机（无 Android 容器） |

留证的两次失败运行：`20260921T111959Z`（用 mcp 2.x 起服务，装饰器 API 已被移除）、
`20260921T112147Z`（两个字面原因：审查 provider 被课程硬编码覆盖成 openrouter 导致危险审查失败、
以及 **PyMuPDF ≥1.26 的 `import fitz` 往 stdout 打印弃用提示污染 MCP 流**——该次运行的日志里残留
`ValidationError ... input_value='warning: The \`fitz\` API is deprecated...'`，是直接证据）。

复现：`.venv-ch4v1/bin/python learning/task4/run_4_4_execution_tools.py`（约 3 分钟；需要 Docker
守护进程运行、`python:3.11-slim` 镜像已拉取、LibreOffice 已安装）。

## 4-5

运行目录：`.../4-5_collaboration/20260921T112238Z/`，**status = blocked**，9 条门禁过 5 条。

| 门禁 | 结果 | 实测 |
| --- | --- | --- |
| 目录含 9 个协作原语 | PASS | 服务器注册 41 个工具（`list_tools()` 实测） |
| 两种上下文策略 | PASS | minimal `prep_tokens=0`；llm_generated `prep_tokens=642`（多一次 LLM 调用，5.25s） |
| 原始 usage/延迟收据 | PASS | 5 次真实调用，逐条带 token 与延迟 |
| 同步/异步/消息/取消/状态 | PASS | 异步轮询到 `completed`；取消后 `cancelled`；补充消息送达 |
| HITL 待批 + 保守超时 | PASS | 待批请求被列出并应答；超时探针 `timeout=true` / `approved=false` |
| 隐私哨兵 | PASS | `PRIVATE-MARKER-MUST-BE-FILTERED` 未出现在移交上下文 |
| 真实人工决定 | blocked | 非交互模式由自动化操作员应答，不计为真人决定 |
| 邮件 / IM / Slack | blocked ×3 | 无 SMTP/SendGrid、Telegram、Slack 凭据 |

复现：`.venv-ch4v1/bin/python learning/task4/run_4_5_collaboration.py`（约 1 分钟；加
`--interactive-human` 可让真人从 stdin 输入 APPROVE/REJECT）。

## tool-selection

运行目录：`.../tool_selection/20260921T112429Z/`。

| 目录规模 | all-tools token | retrieval token | retrieval recall |
| ---: | ---: | ---: | ---: |
| 35 | 3,857 | 517 | 1.00 |
| 50 | 5,342 | 522 | 1.00 |
| 100 | 10,292 | 522 | 1.00 |
| 200 | 20,258 | 522 | 1.00 |
| 400 | 40,258 | 522 | 1.00 |

在线（10 任务 × 3 策略）：all-tools 5/10、9,813 token、2.92s；retrieval 7/10、1,927 token、1.97s；
active 5/10、4,956 token、5.07s。

复现：`.venv/bin/python learning/task4/run_tool_selection.py`（约 1 分钟；离线部分零 API 调用）。

## 环境限制（为什么有些门禁只能是 blocked）

| 缺失 | 影响 |
| --- | --- |
| 无 Ollama / 本地模型 | 4-1 原版的 `qwen3:4b` 无法复现，改用 DeepSeek 得到的是**不同问题**的答案 |
| 无 tesseract | 4-2 的 `image_ocr`、4-3 的 PNG 提取 |
| 无本地 whisper | 4-2 的 `audio_transcribe` |
| 无 Google 日历 / Notion / GitHub token / SMTP / Telegram / Slack | 4-2、4-4、4-5 的对应门禁 |
| macOS 无 X11、无 Android/KVM | 4-4 的虚拟桌面与虚拟手机 |
| 外部 API 限流 | Yahoo Finance、MediaWiki、DuckDuckGo、GitHub 未认证 API——同一实验多次运行结果不同 |

## 已知坑（复跑前先读）

1. **tiktoken 首次使用会联网下载 o200k BPE（约 3.6MB）**，本机实测 151 秒，表现为"卡死"。
   学习版用 `TIKTOKEN_CACHE_DIR` 固定到 `learning/task4/.cache/tiktoken/`。
2. **PyMuPDF ≥1.26 的 `import fitz` 会往 stdout 打印弃用提示**。MCP stdio 服务器把 stdout 当
   JSON-RPC 通道，一行多余输出就能让整条流解析失败（4-4 的第二次运行即因此失败）。
   `.venv-ch4v1` 钉在 `PyMuPDF<1.26`。
3. **课程 runner 硬编码审查 provider**：4-4 写死 kimi/openrouter、4-5 写死 moonshot/kimi-k3。
   学习版在 `StdioServerParameters` 构造处改写 env 而不改课程文件。
4. **HERE 重定向的连带效应**：4-5 的子进程 cwd 取自 `HERE/src`，重定向后必须显式指回课程源码目录。
5. **Excel 门禁需要 `soffice`**：LibreOffice 安装目录要前置到 PATH。
6. **Docker 沙盒首次运行要拉镜像**，30 秒超时会误判为失败——先 `docker pull python:3.11-slim`。

## MCP SDK 版本分叉

| 环境 | 用于 | 原因 |
| --- | --- | --- |
| `.venv`（mcp 2.2.0） | 4-1、4-2、4-3、tool-selection | `perception-tools` 要求 `mcp>=2,<3`（v2 协议、`mcp.Client`） |
| `.venv-ch4v1`（mcp 1.30.0） | 4-4、4-5 | `execution-tools` 用 `@server.list_tools()` 装饰器；`collaboration-tools` 用 `mcp.server.fastmcp.FastMCP`——两者都在 mcp 2.x 被移除 |

## 证据纪律

- 每个实验的运行目录含 `evidence.json` + `evidence.sha256`；`evidence.json` 里记录源文件 SHA-256、
  课程证据摘要、以及**密钥不泄漏扫描结果**（扫描到就判 `completed=false`）；
- `learning/task4/audit_learning.py` 做 59 项离线核对：证据存在性与哈希、每个实验的结构性断言
  （4-1 六条轨迹 / 4-2 二十八个案例 / 4-3 十二行 / 4-4 二十次调用 / 4-5 生命周期与超时门禁 /
  工具选型三策略十任务）、密钥不泄漏、以及**书方五个 canonical manifest 的 SHA-256 是否仍与
  `chapter4/EXPERIMENT_LEDGER.md` 一致**（确认学习版没有覆盖书方证据）；
- 失败运行全部保留在 `runs/` 下（三次 4-1、两次 4-2、三次 4-4），文件名即 UTC 时间戳；
- 本页与各实验页给出的数字，均可在对应运行目录的 `summary.json` / `evidence.json` / `receipts/` 中核对。
