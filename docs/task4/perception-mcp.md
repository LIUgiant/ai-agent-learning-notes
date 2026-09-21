# 感知工具 MCP · 127 个工具与 28 个真实案例的验收长什么样

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](perception-mcp-code.md)：从夹具构造到 11 条门禁，逐函数拆。

[完整证据与复现](evidence.md#4-2) · [学习运行脚本](../assets/task4/run_4_2_perception.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools)

## 这个实验回答什么问题

感知工具是 Agent 的眼睛和耳朵。书里给它的设计重点很具体：**控制输出信息量**（分页、offset/limit、
显式截断），并指出只读性带来的工程红利——**结果可缓存、调用可并行**。

但"设计原则"要落到一个能验收的东西上：一套真 MCP 服务器，把搜索、多模态、文件系统、公开数据源、
私有数据源五类感知能力都装进去，然后用一批**真实调用**去证明每个子能力真的能用。本实验就是这套验收
（书里的 4-2 实验）。

## 设计

课程 `run_experiment_4_2.py` 是一个 fail-closed 的 campaign：先造夹具（自己写 Markdown/PDF/DOCX/PPTX/PNG，
用 macOS `say` 录语音、用 ffmpeg 合成 1.5 秒视频），再用 stdio 连上真 MCP 服务器，跑 28 个案例：

```text
search(3)      web_search / knowledge_base_search / download
multimodal(9)  webpage_reader / document_reader × (pdf,docx,pptx) / image_ocr / image_analyze
               / audio_transcribe / video_parser / video_analyze
filesystem(9)  file_reader / grep / directory_list / copy / move / delete
               + 三条逃逸探针（../、绝对路径、指向外部的软链）——它们**必须被拒绝**
public_data(5) weather(Open-Meteo) / yfinance_quote / currency_converter / wikipedia / arxiv
private_data(2) calendar_events / notion_search —— 无凭据时只允许 blocked，绝不允许"通过"
```

每个案例都要过"实质观测"判定（`substantive_observation`）：不是看工具返回 `success: true`，而是看
**这个案例该有的东西在不在**——股价案例必须有 `current_price`、下载案例必须有落盘文件且字节数吻合、
OCR 案例文本里必须出现夹具里的关键字、文件删除案例必须 `reversible=True` 且路径确实消失。

同时有三层反作弊：`provenance` 只允许 `live-api / local-process / local-filesystem`；仿真标记只扫
控制面字段（远端正文里出现 "mock" 不算数）；文件系统操作前后对**目录外的见证文件**取哈希，必须不变。

**与课程原版的差异**：视觉后端从课程默认的 `dashscope-intl` 换成**国内端点**（本机 key 只在该端点有效），
模型同为 `qwen-vl-max`；其余（28 个案例、夹具、判定、门禁）零改动。本机没有 tesseract、没有
本地 whisper、没有日历/Notion 凭据——这三种缺失按课程规则只能是 blocked/failed。

## 看结果前先想清楚

1. 五类里哪一类**最不可能**在普通笔记本上全过？提示：不是代码问题。
2. 文件系统的三条逃逸探针，工具应该返回 `success=false` 还是抛异常？课程的门禁要求 `success=False`
   且 `error_type == "PermissionError"`，为什么要把这两件事分开记？
3. 一个案例"返回了结果"和"返回了**这个任务需要的结果**"差在哪？举一个本实验里的具体案例。

## 运行结果

两轮真实运行（同样的代码，只隔了几分钟）：

| 类别 | 首轮 `20260921T111348Z` | 次轮 `20260921T112643Z` |
| --- | --- | --- |
| search (3) | ✅ 全过 | ❌ `web_search` 失败（DuckDuckGo 限流） |
| multimodal (9) | ⚠️ 7 过，`image_ocr`（缺 tesseract）、`audio_transcribe`（缺 whisper）失败 | 同左 |
| filesystem (9) | ✅ 6 个操作全过 + **3 条逃逸探针全部被拒** | 同左 |
| public_data (5) | ⚠️ 3 过，`yfinance_quote`（Yahoo 429）、`wikipedia_search`（MediaWiki 429）失败 | 同左 |
| private_data (2) | 🚫 blocked（无 Google/Notion 凭据） | 同左 |
| 门禁 | 8/11 | 7/11 |

成立的能力（实测）：

- **视觉两条路真的通了**：`image_analyze`（4.2s）读出图中文字并描述画面，`video_analyze`（1.8s）
  从 1.5 秒视频关键帧里读出同一段文字——两者都走 `qwen-vl-max`；
- **文件系统确认在笼子里**：`directory_list`、`copy → move → delete` 全部带前后指纹，删除是可回滚的
  隔离删除；三条逃逸探针（`../escaped.txt`、绝对路径 `/tmp`、指向目录外见证文件的软链）全部
  `PermissionError` 拒绝，且见证文件哈希未变；
- **公开数据源大多是免费 API**：天气（Open-Meteo 3.3s）、汇率、arXiv 检索都直接可用。

## 分析

- **"真 MCP 服务器"这件事本身是可验收的**：目录 127 个工具（57 个 `@mcp.tool` + 70 个动态注册的
  扩展工具），每个都有 JSON Schema；28 个案例逐个落盘收据（调用参数哈希、后端来源、实质判定、
  脱敏后的 payload）。**验收的对象不是"工具存在"，而是"工具在这个环境里真的做成了事"。**
- **失败分三类，责任完全不同**：
  1. **缺本地依赖**（`image_ocr` 缺 tesseract、`audio_transcribe` 缺 whisper）——代码没错，
     是环境没装。学习版选择如实记录而不临时安装，因为这两个门禁正好演示了"多模态感知"的三条路径里
     OCR/转写这一层对**系统依赖**的强耦合。顺带一个分类边界：课程的 `credential_blocked()` 靠
     错误串词表判断"这是缺凭据"，而这两个库的报错是 `not installed`，不在词表里——所以它们被判为
     **failed** 而不是 **blocked**。读 `summary.json` 时不要把它误读成"工具坏了"；
  2. **外部限流**（Yahoo 429/403、MediaWiki 429、DuckDuckGo）——同一份代码，首轮 `web_search` 通过、
     次轮失败，说明这类"免费公开 API"案例在真实网络里**不稳定**。这也是书里说"公开数据源大多无需
     注册即可使用"时没有展开的一面：免费不等于可靠；
  3. **无凭据**（日历、Notion）——课程把这类设计成 `credential_blocking_allowed`，只允许整体
     判为 blocked，**明确禁止**用 mock 结果冒充通过。
- **"实质观测"判定是这套验收的关键设计**：如果只看 `success` 字段，`image_ocr` 返回
  `success: false` 和一个错误串也算"跑过了"；如果没有 `substantive_observation`，
  一个把空字符串当结果返回的桩函数也能蒙混过关。**判据写在案例里（要有 `current_price`、
  要有 OCR 命中夹具关键字、要 `reversible=True`），而不是写在工具里**——这是本实验最值得抄的一条工程习惯。
- **只读性的两个红利在本实验里看得见**：文件读取与公开数据查询可以并发（本 campaign 是串行发的，
  但代码里没有任何互斥约束）；而三条逃逸探针恰恰说明**写操作必须有笼子**，哪怕它与读操作打包在
  同一个 MCP 服务器里。

**边界**：本机没有 tesseract/whisper，也没有日历/Notion 凭据，因此"多模态"与"私有数据"两类
**不构成对课程能力的完整复现**；公开数据两条的失败是外部限流而不是代码缺陷；两轮差异说明
live API 类案例在本机不稳定，单次运行的成功/失败不足以判断工具本身的好坏。
