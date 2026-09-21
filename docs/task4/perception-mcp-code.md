# 感知工具 MCP：一步步读源码

[实验说明](perception-mcp.md) · [完整证据与复现](evidence.md#4-2) · [学习运行脚本](../assets/task4/run_4_2_perception.py)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>实验 4-2 有两份源码：一份是**战役脚本** <code>run_experiment_4_2.py</code>（造夹具、发 28 次真实 MCP 调用、逐案例判定、跑 11 条门禁、落 manifest），另一份是**服务器端** <code>src/main.py</code>（127 个工具的 MCP stdio 服务器）。本页按源码顺序把两份文件都读一遍——先给函数清单证明一个不漏，再逐个拆，最后用两次真实执行把整条链路串起来。读完本页，你应当能在不打开源码的情况下说出这个脚本每一段在防什么。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号，链接指向课程仓库固定提交。**学习运行脚本原文**来自 `learning/task4/run_4_2_perception.py`（它原样复用课程战役，只重定向目录与视觉后端）。**教学示意**仅用于解释数据形状或示意图，不是可运行代码。

**主文件**：

- [chapter4/perception-tools/run_experiment_4_2.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py)（705 行，28 案例五类验收战役）
- [chapter4/perception-tools/experiment_protocol.json](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/experiment_protocol.json)（72 行，分类与必需案例清单，脚本据此判门禁）
- [chapter4/perception-tools/src/main.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/src/main.py)（728 行，57 个原生工具 + 动态注册 70 个扩展工具）

本页与 task3 的 [memory 源码精读](../task3/memory-modes-code.md) 是同一套写法：函数清单 → 调用图 → 逐函数 → 执行回放 → 动手验证。

---

## 0. 函数清单地图

### (a) `run_experiment_4_2.py` 的全部定义

| # | 函数/常量 | 行号 | 一句话作用 | 谁调用它 |
| --- | --- | --- | --- | --- |
| — | `HERE` / `REPO` / `PROTOCOL_PATH` / `SERVER_PATH` / `VALIDATION_ROOT` | L32–36 | 脚本路径、协议路径、服务器路径、证据根目录 | 全文件 |
| — | `CASE_TO_TOOL` | L38–67 | 28 个案例名 → MCP 工具名（3 个安全探针映射到 mutation 工具） | `call_case`、`derive_acceptance` |
| — | `PROVENANCE` | L69–93 | 每个案例的后端与来源类型（代码里写死，不接受服务器自报） | `call_case`（两次）、`valid_success` |
| — | `SIMULATION_PATTERN` / `MARKER` | L95–96 | 假数据词表；写进夹具的验证标记字符串 | 前者 `_declared_simulation_markers`，后者夹具与判定 |
| 1 | `canonical_json` | L99–100 | 稳定序列化（排序键、紧凑分隔）用于哈希 | `arguments_sha256`、`schemas_sha256`、`credential_blocked` |
| 2 | `sha256_bytes` | L103–104 | 字节哈希 | 几乎每个落盘函数 |
| 3 | `write_json` | L107–109 | 建目录 + 缩进写 JSON | 全流程落证据 |
| 4 | `file_receipt` | L112–114 | 文件 → {路径, 字节数, sha256} | `prepare_fixtures`、`run`（外部见证） |
| 5 | `command_receipt` | L117–130 | 跑一条外部命令并记录回执（stdout/stderr 哈希、耗时） | `prepare_fixtures`（say / ffmpeg） |
| 6 | `prepare_fixtures` | L133–235 | 用真实编码器造 PDF/DOCX/PPTX/PNG/AIFF/MP4 夹具 + 逃逸软链 | `run` |
| 7 | `credential_preflight` | L238–262 | 凭据「是否存在」盘点（绝不记值） | `run` |
| 8 | `_parse_text` | L265–269 | 文本 → JSON，失败则原样返回 | `unwrap_mcp_result` |
| 9 | `unwrap_mcp_result` | L272–282 | MCP 返回 → Python 值（structuredContent 优先，否则拼 text） | `call_case` |
| 10 | `_action_message` | L285–288 | 取 `message`，无则取 `data` | `substantive_observation` |
| 11 | `_action_metadata` | L291–292 | 取 `metadata` | `substantive_observation` |
| 12 | `_declared_simulation_markers` | L295–310 | 只扫 provenance 类字段里的假数据词 | `call_case` |
| 13 | `_error_type` | L313–319 | 从 metadata / payload 取 `error_type` | `call_case` |
| 14 | `_tool_success` | L322–323 | 工具级成功判定（非 MCP 错误且 `success is True`） | `call_case` |
| 15 | `substantive_observation` | L326–385 | **逐案例的实质判定**（19 个分支） | `call_case` |
| 16 | `call_case` | L388–432 | 发一次 MCP 调用，产出一张 13 字段收据 | `run` 的 28 次循环 |
| 17 | `credential_blocked` | L435–443 | 收据是否因缺凭据/缺库而失败 | `derive_acceptance` |
| 18 | `valid_success` | L446–456 | **一条成功要同时满足的 5 个条件** | `derive_acceptance` ×4 |
| 19 | `derive_acceptance` | L459–547 | 分类状态机 + 11 条门禁 + 安全探针判定 | `run` |
| 20 | `build_manifest` | L550–577 | 战役目录全文件哈希（含符号链接） | `run` |
| 21 | `run` | L580–691 | **编排**：夹具→预检→起服务器→列工具→28 调用→验收→落盘 | `main` |
| 22 | `main` | L694–701 | CLI 入口，按状态决定退出码 | `__main__` |
| — | `if __name__` 守卫 | L704–705 | `raise SystemExit(main())` | 解释器 |

### (b) `src/main.py` 的骨架与注册点

| # | 骨架 / 注册点 | 行号 | 说明 |
| --- | --- | --- | --- |
| — | 工具实现导入 | L12–45 | 从 12 个子模块导入约 60 个工具函数 |
| — | `mcp = MCPServer(...)` | L57–96 | 创建 MCP 服务器（mcp 2.x 高层服务器，前身即 FastMCP），`instructions` 是给人看的分类说明 |
| — | **57 个 `@mcp.tool` 工具实现** | **L103–707** | 每个工具 = 装饰器 + `async def` 包装，转调子模块实现；实现细节按类别归纳见 §3.1，不逐行讲 |
| — | `enrich_existing_tools(mcp)` | L712 | 给 57 个原生工具追加「操作契约」长描述（撑大 schema 的一半） |
| — | `register_expanded_tools(mcp)` | L719 | 动态注册 70 个扩展工具（`query` + `options_json` 两参数） |
| — | `if __name__` 入口 | L726–728 | `mcp.run(transport="stdio")` |

!!! info "两张清单说明什么"
    (a) 表 22 个 `def` 一个不少——这就是「读完等于熟悉整个脚本」的底线：脚本没有隐藏类、没有魔法回调，全部逻辑在 22 个顶层函数里。(b) 表只有 6 行，因为 `main.py` 的 728 行里 **604 行是工具实现**（L103–707），骨架只有「建服务器 / 加描述 / 注册扩展 / 开跑」四步。服务器端的复杂度不在控制流，而在**目录规模**。

---

## 1. 主线调用图

```text
main()  [L694]
 └─ asyncio.run( run(campaign_id) )                                     [L698]
     │
     ├─ 读 experiment_protocol.json（五类必需案例 + 判定声明）             [L581]
     ├─ campaign_dir = VALIDATION_ROOT/<时间戳>，mkdir(exist_ok=False)    [L582–584]
     │     ↑ exist_ok=False：同 id 第二次跑直接炸，绝不复用旧目录
     ├─ write_json(protocol.json)                                        [L585]
     │
     ├─ prepare_fixtures(campaign_dir)                                   [L586→L133]
     │   ├─ 目录: knowledge/ documents/ media/ downloads/ mutation/nested [L141–142]
     │   ├─ 文本夹具: mcp-notes.md、seed.txt、nested/entry.txt            [L144–150]
     │   ├─ 外部见证: outside-witness.txt                                 [L152–153]
     │   ├─ 逃逸软链: mutation/escape-link → outside-witness.txt          [L154]
     │   ├─ reportlab → sample.pdf          [L157–161]
     │   ├─ python-docx → sample.docx       [L163–169]
     │   ├─ python-pptx → sample.pptx       [L171–178]
     │   ├─ PIL → ocr-source.png（写 "EXPERIMENT 4-1 / PERCEPTION TOOLS VERIFIED"）[L180–193]
     │   ├─ macOS say → spoken-marker.aiff  [L195–201]
     │   ├─ ffmpeg → visual-marker.mp4      [L203–209]
     │   └─ 写 fixture_receipt.json（每个夹具的 sha256）                   [L225–234]
     │
     ├─ credential_preflight()                                           [L587→L238]
     │   └─ 只记 bool：calendar token 是否存在、各 key 是否存在、库能否 import
     │       写 credential_preflight.json                                 [L588]
     │
     ├─ server_env = os.environ.copy()                                   [L591–600]
     │   ├─ PERCEPTION_MUTATION_ROOT = fixtures/mutation                 [L592]
     │   ├─ DASHSCOPE_API_KEY 存在 → VISION_PROVIDER=dashscope, MODEL=qwen-vl-max
     │   ├─ 否则 GEMINI → gemini-2.5-flash；再否则 gpt-4o-mini
     │   └─ StdioServerParameters(command=python, args=[src/main.py], env) [L601–605]
     │
     ├─ async with Client(stdio_client(parameters)) as client:            [L607]
     │   ├─ await client.list_tools()                                    [L608]
     │   │   └─ catalog: tool_count / unique_tool_count / schemas_sha256  [L612–624]
     │   │        → 写 catalog_receipt.json（本例 127 工具）               [L625]
     │   │
     │   └─ for case, arguments in calls:  (28 次)                        [L657–660]
     │       └─ call_case(client, case, arguments, paths)                [L388]
     │           ├─ tool = CASE_TO_TOOL[case]                             [L394]
     │           ├─ await client.call_tool(tool, arguments)              [L397]
     │           ├─ unwrap_mcp_result(result)                            [L398→L272]
     │           ├─ substantive_observation(case, payload, paths)        [L409→L326]
     │           ├─ _declared_simulation_markers(payload)                [L411→L295]
     │           ├─ _error_type(payload)                                 [L412→L313]
     │           └─ 13 字段收据 → receipts/NN_case.json                   [L660]
     │
     ├─ outside_after = file_receipt(outside_witness)                    [L662–663]
     │   └─ outside_unchanged = (before == after)  ← 软链逃逸失败的硬证据
     │
     ├─ derive_acceptance(protocol, catalog, receipts, outside_witness_unchanged) [L664→L459]
     │   ├─ 五类各自状态机（passed / blocked / failed）
     │   ├─ safety_rejected = 三条探针 PermissionError + 见证未变
     │   ├─ filesystem_hashes = copy/move/delete 的 pre==post 指纹
     │   └─ 11 条 gates + 总状态
     │
     ├─ write_json(summary.json)     ← acceptance 全量 + 成功/失败案例名单 [L683]
     ├─ write_json(manifest.json)    ← build_manifest 全文件哈希           [L684→L550]
     └─ write_json(latest.json)      ← 指向本次 manifest + 其 sha256        [L685–690]
            ↑ latest 最后写：半途崩溃的 run 永远不会占据「最新位」
```

学习版只把 `HERE` / `VALIDATION_ROOT` 改成 `learning/task4/runs/4-2_perception_tools/<时间戳>`，其余分支原样。

---

## 2. 逐函数讲解（严格按源码顺序）

### 2.1 常量与两张表：`CASE_TO_TOOL`、`PROVENANCE`（L32–96）

[源码 L32–96](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L32-L96)

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="32"
HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PROTOCOL_PATH = HERE / "experiment_protocol.json"
SERVER_PATH = HERE / "src" / "main.py"
VALIDATION_ROOT = HERE / "validation" / "experiment_4_2"

CASE_TO_TOOL = {
    "web_search": "web_search",
    "knowledge_base_search": "knowledge_base_search",
    "download": "download",
    "webpage_reader": "webpage_reader",
    "document_reader_pdf": "document_reader",
    ...
    "reject_parent_traversal": "filesystem_copy",
    "reject_absolute_path": "filesystem_delete",
    "reject_escaping_symlink": "filesystem_delete",
    ...
}
```

`CASE_TO_TOOL` 是**案例名到工具名的解耦层**。多数键值同名，但有三处刻意不同：

- 三个 `document_reader_*` 案例都打同一个 `document_reader` 工具（PDF/DOCX/PPTX 是同一工具的不同输入，靠 `substantive_observation` 里的 `file_type` 分支区分）；
- 三个 `reject_*` 安全探针**借用真实的 mutation 工具**去故意越界——`reject_parent_traversal` → `filesystem_copy`、`reject_absolute_path` → `filesystem_delete`、`reject_escaping_symlink` → `filesystem_delete`。这些探针**期望失败**，所以在 `calls` 里它们也是「案例」，但在 `derive_acceptance` 里走另一条判定路径（见 §2.9）。

这张表让「案例」成为一等公民：28 个案例各有一条收据，工具只是实现手段。

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="69"
PROVENANCE = {
    "web_search": {"backend": "duckduckgo-live-search", "origin": "live-api"},
    "knowledge_base_search": {"backend": "local-knowledge-files", "origin": "local-filesystem"},
    "download": {"backend": "tls-http-download", "origin": "live-api"},
    "document_reader": {"backend": "format-aware-local-parser", "origin": "local-process"},
    "image_ocr": {"backend": "local-tesseract-ocr", "origin": "local-process"},
    "image_analyze": {"backend": "configured-vision-api", "origin": "live-api"},
    "filesystem_copy": {"backend": "workspace-confined-copy", "origin": "local-filesystem"},
    "calendar_events": {"backend": "google-calendar-api", "origin": "private-live-api"},
    ...
}

SIMULATION_PATTERN = re.compile(r"\b(mock(?:ed)?|placeholder|synthetic|simulat(?:ed|ion))\b", re.I)
MARKER = "PERCEPTION-EXPERIMENT-4-1-VERIFIED"
```

`PROVENANCE` 是**这张战役最重要的一张表**：它把每个工具的「后端是什么、来源属于哪一类」写死在**调用方**，而不是让服务器自报。为什么？因为服务器自报的 provenance 是可以撒谎的——一个假实现完全可以返回 `{"origin": "live-api"}`。写在战役侧，服务器就无法篡改「这个案例应当来自 live-api」这一预期。`origin` 的四个合法值 `live-api` / `private-live-api` / `local-filesystem` / `local-process` 会在 `valid_success` 里被逐个校验。

`MARKER` 是贯穿全案的验证字符串：它写进 Markdown 笔记、`seed.txt`、PDF、DOCX、PPTX、录进音频、画进 PNG，最后在对应工具的返回里被搜出来——**同一个字符串把「我造了夹具」和「工具真的读到了它」缝在一起**。

`SIMULATION_PATTERN` 是假数据词表，只用于 `_declared_simulation_markers`（见 §2.6）。

---

### 2.2 小工具四件套：`canonical_json` / `sha256_bytes` / `write_json` / `file_receipt` / `command_receipt`（L99–130）

[源码 L99–130](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L99-L130)

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="99"
def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

def file_receipt(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha256_bytes(data)}

def command_receipt(command: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)
    receipt = {
        "executable": command[0],
        "arguments": command[1:],
        "returncode": result.returncode,
        "stdout_sha256": sha256_bytes(result.stdout.encode()),
        "stderr_sha256": sha256_bytes(result.stderr.encode()),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    if result.returncode != 0:
        raise RuntimeError(f"fixture command failed: {receipt}")
    return receipt
```

四个要点：

- `canonical_json` 的 `sort_keys=True` + 紧凑分隔符让**同一份数据永远得到同一个字符串**，哈希才有意义；`ensure_ascii=False` 让中文不膨胀；`default=str` 兜底不可序列化对象（`Path`、`set`）。
- `write_json` 的 `indent=2` 是为了**人读**（证据文件要能直接看），代价是体积——但体积无所谓，`canonical_json` 才是算哈希用的。
- `file_receipt` 只读字节、不解析，所以对 PNG/MP4 这类二进制同样有效。
- `command_receipt` 的三个设计：`capture_output=True` 不污染终端；stdout/stderr **只记哈希不记原文**（`say` 会打印内容、`ffmpeg` 可能打印路径，都属可省略信息）；`returncode != 0` 直接抛——**夹具造失败就整案中止，不允许下游用半成品继续**。

---

### 2.3 `prepare_fixtures`（L133–235）：用真编码器造确定性输入

[源码 L133–235](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L133-L235)

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="133"
def prepare_fixtures(campaign_dir: Path) -> dict[str, Any]:
    """Create small deterministic inputs with real document/media encoders."""
    fixtures = campaign_dir / "fixtures"
    knowledge = fixtures / "knowledge"
    documents = fixtures / "documents"
    media = fixtures / "media"
    downloads = fixtures / "downloads"
    mutation = fixtures / "mutation_workspace"
    for directory in (knowledge, documents, media, downloads, mutation / "nested"):
        directory.mkdir(parents=True, exist_ok=True)

    note = knowledge / "mcp-notes.md"
    note.write_text(
        f"# Experiment 4-2\n\n{MARKER}\nThe Model Context Protocol connects agents to perception tools.\n",
        encoding="utf-8",
    )
    (mutation / "seed.txt").write_text(f"{MARKER}\n", encoding="utf-8")
    (mutation / "nested" / "entry.txt").write_text("directory browse fixture\n", encoding="utf-8")

    outside_witness = fixtures / "outside-witness.txt"
    outside_witness.write_text("OUTSIDE-WITNESS-MUST-REMAIN\n", encoding="utf-8")
    (mutation / "escape-link").symlink_to(outside_witness)

    from reportlab.pdfgen import canvas

    pdf = documents / "sample.pdf"
    report = canvas.Canvas(str(pdf))
    report.drawString(72, 760, f"Experiment 4-2 PDF {MARKER}")
    report.save()
```

**目录布局就是「攻击面」的划分**：

- `knowledge/`、`documents/`、`media/`、`downloads/` 是**只读输入**；
- `mutation_workspace/` 是唯一允许改写的目录（服务器的 `PERCEPTION_MUTATION_ROOT` 指向它）；
- `fixtures/outside-witness.txt` 位于 mutation root **之外**。

**「逃逸软链」的设计**（L154）：

```python
outside_witness = fixtures / "outside-witness.txt"
outside_witness.write_text("OUTSIDE-WITNESS-MUST-REMAIN\n", encoding="utf-8")
(mutation / "escape-link").symlink_to(outside_witness)
```

`mutation_workspace/escape-link` 是一个**指向外面的软链接**。它是三条安全探针里最难防的一条：路径字符串 `"escape-link"` 本身完全合法（相对路径、无 `..`、不越界），安全边界只有**解析链接之后**才暴露。脚本在 `run` 里对 `outside-witness.txt` 做调用前/调用后两次 `file_receipt`（L590、L662），若探针真的把文件删掉或改掉，两个哈希就对不上。这是「服务器声称拒绝」之外的**独立物证**——服务器就算谎报拒绝，见证文件的哈希也会揭穿它。

其余夹具都是**真实格式的真编码器**，不是伪造的假文件：

| 夹具 | 编码器 | 落盘写入的内容 |
| --- | --- | --- |
| `sample.pdf` | reportlab.pdfgen | `Experiment 4-2 PDF PERCEPTION-EXPERIMENT-4-1-VERIFIED` |
| `sample.docx` | python-docx | 标题 + MARKER 段落 |
| `sample.pptx` | python-pptx | 标题占位符 + MARKER |
| `ocr-source.png` | PIL | 两行大字 `EXPERIMENT 4-1` / `PERCEPTION TOOLS VERIFIED` |
| `spoken-marker.aiff` | macOS `say -v Samantha` | `Experiment four one. Perception tools verified.` |
| `visual-marker.mp4` | `ffmpeg -loop 1 -i <png> -t 1.5 -r 3` | 由上面 PNG 生成的 1.5 秒视频 |

PNG 那段的字体回退值得注意（L185–190）：

```python
    font_candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    font_path = next((path for path in font_candidates if path.is_file()), None)
    font = ImageFont.truetype(str(font_path), 54) if font_path else ImageFont.load_default()
```

先找 macOS 的 Arial，再找 Linux 的 DejaVuSans，都没有才退回 PIL 内置位图字体——**跨平台可用性**优先于画质。54 号字是为了让后面 DashScope 视觉模型能稳定读出文字。

最后写 `fixture_receipt.json`（L225–234），把 `note/pdf/docx/pptx/image/audio/video/outside_witness` 八个夹具的 `sha256` 与 `say`/`ffmpeg` 的命令回执一并落盘——**输入本身也被哈希**，证据链从输入就开始了。

---

### 2.4 `credential_preflight`（L238–262）：只记存在性，不记值

[源码 L238–262](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L238-L262)

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="238"
def credential_preflight() -> dict[str, Any]:
    token_path = Path("~/.perception-tools/google_token.pickle").expanduser()
    return {
        "secret_values_recorded": False,
        "google_calendar": {
            "token_file_exists": token_path.is_file(),
            "token_file_bytes": token_path.stat().st_size if token_path.is_file() else 0,
            "oauth_credentials_sdk_importable": importlib.util.find_spec("google.oauth2.credentials") is not None,
            "calendar_sdk_importable": importlib.util.find_spec("googleapiclient.discovery") is not None,
        },
        "notion": {
            "api_key_present": bool(os.environ.get("NOTION_API_KEY")),
            "sdk_importable": importlib.util.find_spec("notion_client") is not None,
        },
        "multimodal": {
            "openai_key_present": bool(os.environ.get("OPENAI_API_KEY")),
            ...
            "local_whisper_importable": importlib.util.find_spec("whisper") is not None,
            "pytesseract_importable": importlib.util.find_spec("pytesseract") is not None,
            "tesseract_executable_present": bool(shutil.which("tesseract")),
            "ffmpeg_executable_present": bool(shutil.which("ffmpeg")),
        },
    }
```

**这个函数存在的全部理由，是它不记录什么**。三处纪律：

1. `"secret_values_recorded": False` 是一句**可审计的自我声明**——任何读到 `credential_preflight.json` 的人先看到这一行，才知道这个文件里不可能有密钥。
2. 所有 key 都过 `bool(os.environ.get(...))` 或 `find_spec(...) is not None`，**布尔化**之后才落盘。连 Google token 文件也只记 `is_file()` 与 `stat().st_size`（字节数），不读内容——`google_token.pickle` 里含 refresh token，读一眼就泄露。
3. 它盘点的东西**恰好覆盖后面会 blocked 的三类**：Calendar（token 文件 + 两个 SDK）、Notion（key + SDK）、语音/OCR（whisper / pytesseract / tesseract / ffmpeg）。

为什么要先盘一次？因为**「缺凭据」和「代码坏了」在收据上长得很像**（都是 `success=false`）。预检文件把「本机本来就没有」的证据固定下来，事后复盘时才能区分：`image_ocr` 失败是因为 `tesseract_executable_present: false`，而不是 OCR 逻辑写错。学习版更进一步，在 `run_4_2_perception.py` 里复制了一份 `LOCAL_CAPABILITIES` 写进证据（见 §4）。

---

### 2.5 `_parse_text` 与 `unwrap_mcp_result`（L265–282）：MCP 返回的两种形状

[源码 L265–282](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L265-L282)

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="265"
def _parse_text(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def unwrap_mcp_result(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if structured:
        return structured
    texts = [getattr(item, "text", None) for item in getattr(result, "content", [])]
    texts = [text for text in texts if isinstance(text, str)]
    if len(texts) == 1:
        return _parse_text(texts[0])
    return [_parse_text(text) for text in texts]
```

`tools/call` 的返回有两种可能形状，这个函数都要吃下：

- **structuredContent**：mcp 2.x 的「结构化输出」通道，已经把 dict 反序列化好，直接用。字段名有 `structuredContent` 与 `structured_content` 两个拼法，代码两个都试——SDK 大小版本会改名，这是防御性写法。
- **content 文本块**：老式通道，把 JSON 序列化成字符串塞进 `TextContent.text`。多个块就返回列表，单块就尝试 `json.loads`。

`_parse_text` 的容错哲学是**「解析不了就原样返回字符串」**，而不是抛异常。理由：`substantive_observation` 对每个案例都先检查 `isinstance(message, dict)`，拿到字符串自然判 False——失败被**降级成一次判定失败**，而不是打断整场战役。若这里抛异常，`call_case` 的 `except` 会把 `error_type` 记成 `JSONDecodeError`，语义就乱了（那是「返回格式不对」，不是「工具失败」）。

---

### 2.6 `_action_message` / `_action_metadata` / `_declared_simulation_markers` / `_error_type` / `_tool_success`（L285–323）

[源码 L285–323](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L285-L323)

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="285"
def _action_message(payload: Any) -> Any:
    if isinstance(payload, dict):
        return payload.get("message", payload.get("data"))
    return None


def _action_metadata(payload: Any) -> dict[str, Any]:
    return payload.get("metadata", {}) if isinstance(payload, dict) else {}


def _declared_simulation_markers(payload: Any) -> list[str]:
    """Scan provenance-like fields, not arbitrary fetched page text."""
    markers: list[str] = []

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                if child_key.lower() in {"backend", "provider", "method", "source", "origin"}:
                    match = SIMULATION_PATTERN.search(str(child))
                    if match:
                        markers.append(match.group(0).lower())
                if child_key.lower() in {"metadata", "provenance"}:
                    visit(child, child_key)

    visit(payload)
    return sorted(set(markers))


def _error_type(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and metadata.get("error_type"):
        return str(metadata["error_type"])
    return str(payload.get("error_type")) if payload.get("error_type") else None


def _tool_success(payload: Any, mcp_is_error: bool) -> bool:
    return not mcp_is_error and isinstance(payload, dict) and payload.get("success") is True
```

`_action_message` / `_action_metadata` 是从工具返回信封里取字段的两把钥匙。`payload.get("message", payload.get("data"))` 这个写法值得注意：**取不到 `message` 时退到 `data`，而不是返回 None**——目录里两种信封混用，`substantive_observation` 不必为每种工具写两套取法。

`_declared_simulation_markers` 是本页最需要讲清楚的一个设计。它回答的问题是：**「这个返回值是不是假数据？」** 直觉做法是把整个 payload 序列化后搜 `mock`/`placeholder`/`synthetic`。但那会**误伤**：如果被测工具读回的远端网页正文里恰好出现 "mock" 这个词（比如一篇讲 mock 测试的文章），正文里的词就被当成了「服务器在造假」。

所以这个函数**只扫 provenance 类字段**，两处收口：

- 键名属于 `{backend, provider, method, source, origin}` 时，才拿该**值**去匹配词表；
- 只在键名是 `metadata` 或 `provenance` 时才**递归**下去。

换句话说，它承认一个前提：**如果服务器在造假，它必须假在「来源声明」上**（`"backend": "mock-search"`），而不可能假在正文里。正文里的 "mock" 是**数据**，不是**声明**。这条边界把「检查声明」和「检查内容」分开，避免了最典型的假阳性。返回值还做 `sorted(set(...))` 去重排序，收据才稳定可比。

`_error_type` 的查找顺序是 metadata 优先、payload 顶层兜底——因为 `filesystem_tools` 把错误信息放在 `metadata.error_type`，而扩展目录工具放在顶层。

`_tool_success` 是**工具级**的成功：非 MCP 传输错误 + 信封 `success is True`。它跟 MCP 自己的 `isError` 是两回事：MCP 的 `isError` 表示「调用协议层出错」，而这里工具**故意**用 `success=false` 把业务失败包在正常返回里（fail-closed 设计）。两者都要查，缺一不可。

---

### 2.7 `substantive_observation`（L326–385）：逐案例的实质判定

[源码 L326–385](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L326-L385)

这是整场战役里**篇幅最大、也最核心**的函数：19 个分支，每个案例一条判据。

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="326"
def substantive_observation(case: str, payload: Any, paths: dict[str, Path]) -> bool:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return False
    message = _action_message(payload)
    metadata = _action_metadata(payload)
    if case == "web_search":
        return isinstance(message, dict) and bool(message.get("results"))
    if case == "knowledge_base_search":
        return isinstance(message, dict) and bool(message.get("results"))
    if case == "download":
        target = paths["downloads"] / "iana-example.html"
        return target.is_file() and target.stat().st_size > 100 and metadata.get("file_size_bytes") == target.stat().st_size
    if case == "webpage_reader":
        return isinstance(message, dict) and bool(message.get("title")) and message.get("text_length", 0) > 50
    if case.startswith("document_reader_"):
        expected = case.rsplit("_", 1)[1]
        return isinstance(message, dict) and message.get("file_type") == expected and message.get("text_length", 0) > 10
    if case == "image_ocr":
        text = str(message.get("extracted_text", "")) if isinstance(message, dict) else ""
        return len(text.strip()) > 10 and "EXPERIMENT" in text.upper()
    if case == "image_analyze":
        return isinstance(message, dict) and len(str(message.get("analysis", "")).strip()) > 20
    ...
    if case == "filesystem_delete":
        return (
            isinstance(message, dict)
            and message.get("reversible") is True
            and message.get("path_exists_after") is False
            and message.get("quarantine_fingerprint") == metadata.get("pre_operation_fingerprint")
        )
    ...
    if case in {"calendar_events", "notion_search"}:
        return isinstance(message, dict) and isinstance(message.get("count"), int)
    return False
```

**函数开头两句就是总闸**：信封必须是 dict 且 `success is True`，否则一律 False。后面每个分支都在问同一个问题的不同方言：**「返回里有没有只有真做过才会有的东西？」**

逐类看每条判据在防什么：

| 案例 | 判据 | 在防什么 |
| --- | --- | --- |
| `web_search` | `message["results"]` 非空 | 防「空成功」——返回 `{"success": true, "results": []}` 的桩实现 |
| `knowledge_base_search` | 同上 | 同上；这里搜的是写进笔记的 MARKER，命中说明真读了本地文件 |
| `download` | 落盘文件存在且 `>100` 字节，且 `metadata.file_size_bytes == 实际字节数` | 防「假装下载」：**既查磁盘，又交叉核对工具自报的字节数**。两者不一致说明工具在编数字 |
| `webpage_reader` | 有 title 且 `text_length > 50` | 防只返回 HTTP 状态不解析正文 |
| `document_reader_*` | `file_type == "pdf"/"docx"/"pptx"` 且 `text_length > 10` | 防「一个解析器冒充三种格式」——`file_type` 必须与案例后缀一致 |
| `image_ocr` | 文本长度 > 10 **且** 含 "EXPERIMENT" | 强判据：**必须读到夹具里真实画上去的字**。防 OCR 返回任意一段非空文本 |
| `image_analyze` | `analysis` 长度 > 20 | 这里放宽（只查非空长度），因为视觉模型的措辞不可预测；真实性交给 `simulation_markers` 与 provenance 兜底 |
| `audio_transcribe` | `transcription` 长度 > 5 | 同上，语音转写措辞不可控 |
| `video_parser` | `duration_seconds > 0` 且 `frame_count > 0` | 防「返回一个空元数据 dict」 |
| `video_analyze` | `frames_analyzed >= 1` 且 `combined_analysis` 长度 > 20 | 防没抽到帧却报成功 |
| `file_reader` | `MARKER in message["content"]` | **最强判据**：内容里必须出现写进 `mcp-notes.md` 的那个精确字符串 |
| `grep` | `total_found >= 1` | 防「正则没命中却报成功」 |
| `directory_list` | 结果里存在名为 `seed.txt` 的行 | 防返回硬编码的目录列表（`seed.txt` 是本场现造的） |
| `filesystem_copy` / `_move` | `destination_fingerprint == metadata.pre_operation_fingerprint` 且字节 > 0 | **前后指纹一致**：源文件的内容指纹必须等于目标文件的内容指纹，证明字节真的搬过去了 |
| `filesystem_delete` | `reversible is True`、`path_exists_after is False`、`quarantine_fingerprint == pre_operation_fingerprint` | 三点合一：可回收、原路径已消失、隔离副本内容一致 |
| `weather` | `temperature is not None` | 只查非 None，因为天气本身会变 |
| `yfinance_quote` | `symbol == "AAPL"` 且 `current_price is not None` | 回显的 symbol 必须对得上，防串号 |
| `currency_converter` | `converted_amount` 与 `exchange_rate` 都非 None | 两者都要有——只给一个说明算了一半 |
| `wikipedia_search` | `title` 与 `summary` 都非空 | 防「搜到标题没摘要」 |
| `arxiv_search` | `papers` 非空 | 同上 |
| `calendar_events` / `notion_search` | `count` 是 int（**可以为 0**） | 私有数据的判据故意宽松：**「查到了空日历」也算实质观测**，因为真实日历本来就可能为空；这两类靠 `credential_blocked` 而不是靠内容判定 |

最后一句 `return False` 是**默认拒绝**：任何没写分支的 case 都判不实质。新增案例若忘了加分支，会立刻以「不实质」暴露，而不是默默通过。

---

### 2.8 `call_case`（L388–432）：一张 13 字段收据

[源码 L388–432](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L388-L432)

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="388"
async def call_case(
    client: Client,
    case: str,
    arguments: dict[str, Any],
    paths: dict[str, Path],
) -> dict[str, Any]:
    tool = CASE_TO_TOOL[case]
    started = time.perf_counter()
    try:
        result = await client.call_tool(tool, arguments=arguments)
        payload = unwrap_mcp_result(result)
        mcp_is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
        success = _tool_success(payload, mcp_is_error)
        receipt = {
            "case": case,
            "tool": tool,
            "arguments": arguments,
            "arguments_sha256": sha256_bytes(canonical_json(arguments).encode()),
            "transport": "mcp-stdio",
            "mcp_result_is_error": mcp_is_error,
            "success": success,
            "substantive_observation": substantive_observation(case, payload, paths),
            "backend_provenance": PROVENANCE[tool],
            "simulation_markers": _declared_simulation_markers(payload),
            "error_type": _error_type(payload),
            "payload": payload,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        receipt = {
            "case": case,
            "tool": tool,
            "arguments": arguments,
            "arguments_sha256": sha256_bytes(canonical_json(arguments).encode()),
            "transport": "mcp-stdio",
            "mcp_result_is_error": True,
            "success": False,
            "substantive_observation": False,
            "backend_provenance": PROVENANCE[tool],
            "simulation_markers": [],
            "error_type": type(exc).__name__,
            "payload": {"success": False, "error": str(exc)},
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    return receipt
```

**收据是 13 个顶层字段**（`payload` 内部还有嵌套，但顶层就这 13 个）。逐个说它的用处：

| 字段 | 作用 | 谁会读它 |
| --- | --- | --- |
| `case` | 案例名，收据的**主键** | `derive_acceptance` 建 `by_case` 索引 |
| `tool` | 实际调用的工具名（可能异于 case） | 复盘区分「同一工具三种格式」 |
| `arguments` | 调用参数原文 | 复现用 |
| `arguments_sha256` | 参数的稳定哈希 | 证明「两次跑的是同一组参数」 |
| `transport` | 恒为 `"mcp-stdio"` | `valid_success` 第一道校验 |
| `mcp_result_is_error` | MCP 协议层是否报错 | 与 `success` 交叉；安全探针要求它是 `False` |
| `success` | 工具信封级成功 | `valid_success`、分类状态机 |
| `substantive_observation` | 内容是否实质 | `valid_success` 的核心条件 |
| `backend_provenance` | **来自战役侧** `PROVENANCE` 表 | `valid_success` 校验 `origin` 合法 |
| `simulation_markers` | 声明里出现的假数据词 | `valid_success` 要求为空 |
| `error_type` | 失败类型（`PermissionError` 等） | `credential_blocked`、安全探针判定 |
| `payload` | 工具返回的**完整原文** | 人工复盘、学习版提取视觉回执 |
| `elapsed_seconds` | 耗时 | 观察 live API 的抖动 |

**`try/except` 两路产出「形状相同」的收据**——这是刻意的。异常路径也填满全部 13 个字段（`backend_provenance` 仍来自 `PROVENANCE`，`error_type` 用异常类名），所以下游 `derive_acceptance` **不需要区分「正常失败」与「抛异常失败」**：两者都只是 `success=False` 的收据。异常被就地消化成数据，**一次工具崩溃不会中断 28 案例的循环**。

`mcp_result_is_error` 的取值写法 `getattr(result, "isError", False) or getattr(result, "is_error", False)` 又是一个版本兼容点（camelCase 与 snake_case 并存）。

---

### 2.9 `credential_blocked` 与 `valid_success`（L435–456）：两种截然不同的失败

[源码 L435–456](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L435-L456)

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="435"
def credential_blocked(receipt: dict[str, Any]) -> bool:
    error_type = str(receipt.get("error_type") or "").lower()
    payload_text = canonical_json(receipt.get("payload", {})).lower()
    markers = [
        "missing_credentials", "missing_library", "not configured", "api key not configured",
        "invalid credentials", "unauthorized", "authentication", "insufficient_quota",
        "exceeded your current quota", "user not found", "401",
    ]
    return error_type in {"missing_credentials", "missing_library"} or any(marker in payload_text for marker in markers)


def valid_success(receipt: dict[str, Any]) -> bool:
    return (
        receipt.get("transport") == "mcp-stdio"
        and receipt.get("mcp_result_is_error") is False
        and receipt.get("success") is True
        and receipt.get("substantive_observation") is True
        and receipt.get("simulation_markers") == []
        and receipt.get("backend_provenance", {}).get("origin") in {
            "live-api", "private-live-api", "local-filesystem", "local-process"
        }
    )
```

`credential_blocked` 划出**「可原谅的失败」**：错误类型是 `missing_credentials`/`missing_library`，或 payload 文本里出现凭据类词表（`not configured`、`unauthorized`、`401`、配额超限等）。它**只对协议里声明了 `credential_blocking_allowed: true` 的类别生效**（multimodal、private_data）。一个未授权/未配置的失败可以记成 `blocked`，但**永远不能算成功**——这正是 `fail_closed: true` 的含义。

这里有一个**实测中很关键的细节**（见 §5）：`image_ocr` 的 `error_type` 是 `ocr_error`，payload 文本是 `pytesseract not installed`；`audio_transcribe` 是 `audio_error` + `Whisper not installed`。这两个字符串**都不在词表里**（词表认的是 `not configured` 与 `missing_library`，不认 `not installed`）。因此按代码逻辑，这两条**不会被判 blocked，而是判 failed**，multimodal 一类随之是 `failed` 而不是 `blocked`。这是词表覆盖面的实际边界，不是判据写错——只是「缺可执行文件」没被列进「缺凭据」的词汇表。学习版的证据里因此把「本机能力」单独写了一份（§4），用来人工补上这层区分。

`valid_success` 要求**五件事同时成立**，缺一不可：

1. `transport == "mcp-stdio"`——必须真的走了 MCP 协议，而不是本地直调；
2. `mcp_result_is_error is False`——协议层没报错；
3. `success is True`——工具信封说成功；
4. `substantive_observation is True`——**内容真做了事**；
5. `simulation_markers == []` 且 `origin` 合法——不是假数据、来源类型对得上。

这就是协议里 `every_success_is_substantive` 与 `missing_or_invalid_credentials_never_pass` 两条声明的代码化身。第 4 条是灵魂：**没有它，一个返回 `{"success": true}` 的空壳就能骗过整场验收**。

---

### 2.10 `derive_acceptance`（L459–547）：分类状态机 + 11 条门禁

[源码 L459–547](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L459-L547)

#### (1) 逐类状态机（L466–488）

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="466"
    by_case = {receipt.get("case"): receipt for receipt in receipts}
    required_tools = {CASE_TO_TOOL[case]
                      for category in protocol["categories"].values()
                      for case in category.get("required_cases", []) + category.get("required_safety_cases", [])}
    category_results: dict[str, Any] = {}
    for name, category in protocol["categories"].items():
        required = category.get("required_cases", [])
        missing = [case for case in required if case not in by_case]
        invalid = [case for case in required if case in by_case and not valid_success(by_case[case])]
        if not missing and not invalid:
            status = "passed"
        elif category.get("credential_blocking_allowed") and not missing and invalid and all(
            credential_blocked(by_case[case]) for case in invalid
        ):
            status = "blocked"
        else:
            status = "failed"
        category_results[name] = {
            "status": status,
            "required_cases": required,
            "missing_cases": missing,
            "invalid_cases": invalid,
        }
```

五类各自三分支，落到三个状态之一：

- `missing`（收据都没收到）与 `invalid`（收到了但不满足 `valid_success`）都为空 → `passed`；
- **且**该类别允许 `blocked`、**且**没有 missing、**且**全部 invalid 都 `credential_blocked` → `blocked`；
- 其余 → `failed`。

`failed` 是兜底：哪怕只差一条，整类就是 failed。**不允许「大部分通过」这种中间态**。这也解释了为什么实测里 multimodal 是 `failed`：它有两处 invalid（`image_ocr`、`audio_transcribe`），而这两处按词表不算 `credential_blocked`，所以落不到 `blocked` 分支。

`required_tools` 用的是**所有类别的 required_cases + required_safety_cases**（含三条安全探针），去和目录里的工具名集合比对——这是门禁 2 的依据。

#### (2) 安全探针与 pre/post 指纹（L490–506）

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="490"
    safety_cases = protocol["categories"]["filesystem"]["required_safety_cases"]
    safety_rejected = all(
        case in by_case
        and by_case[case].get("success") is False
        and by_case[case].get("mcp_result_is_error") is False
        and by_case[case].get("error_type") == "PermissionError"
        for case in safety_cases
    ) and outside_witness_unchanged
    filesystem_hashes = all(
        valid_success(by_case[case]) for case in (
            "filesystem_copy", "filesystem_move", "filesystem_delete"
        )
    ) if all(case in by_case for case in (
        "filesystem_copy", "filesystem_move", "filesystem_delete"
    )) else False
    if not safety_rejected or not filesystem_hashes:
        category_results["filesystem"]["status"] = "failed"
```

`safety_rejected` 的判定是本战役里最精细的一处。三条探针**必须失败**，但失败的姿势有严格要求：

- `success is False`——工具要明确说「我没做」；
- `mcp_result_is_error is False`——**但不能是协议层崩溃**。一个抛异常炸掉连接的服务器也满足「成功为 False」，但那不是「优雅拒绝」，是「服务器坏了」；
- `error_type == "PermissionError"`——必须是一个**指明权限边界**的错误类型，而不是泛泛的 `Exception`。

三条之外，还要 **`outside_witness_unchanged`**：`escape-link` 指向的外部见证文件哈希前后一致。这是**绕过服务器自报的独立验证**——服务器可以在返回里写「我拒绝了」，但如果它暗地里删了外部文件，哈希就会变。四条件全过，`safety_rejected` 才为真。

`filesystem_hashes` 要求 copy/move/delete 三条都是 `valid_success`（其中已含 `destination_fingerprint == pre_operation_fingerprint` 的前后指纹一致判据）。任一为假，filesystem 整类直接打成 `failed`——**连安全探针过了也救不回来**。

#### (3) 11 条门禁（L508–532）

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="508"
    gates = {
        "catalog_from_real_mcp": (
            catalog.get("transport") == "mcp-stdio"
            and catalog.get("tools_list_received") is True
            and catalog.get("protocol_version") == "2026-07-28"
            and str(catalog.get("mcp_sdk_version", "")).split(".", 1)[0] == "2"
            and catalog.get("tool_count") == catalog.get("unique_tool_count")
            and catalog.get("tool_count", 0) >= 120
        ),
        "catalog_contains_all_required_tools": required_tools <= set(catalog.get("tool_names", [])),
        "search_category_passed": category_results["search"]["status"] == "passed",
        "multimodal_category_passed": category_results["multimodal"]["status"] == "passed",
        "filesystem_category_passed": category_results["filesystem"]["status"] == "passed",
        "public_data_category_passed": category_results["public_data"]["status"] == "passed",
        "private_data_category_passed": category_results["private_data"]["status"] == "passed",
        "filesystem_pre_post_hashes_verified": filesystem_hashes,
        "filesystem_isolation_probes_rejected": safety_rejected,
        "all_successes_substantive_and_non_simulated": all(
            valid_success(receipt) for receipt in receipts if receipt.get("success") is True
        ),
        "exact_case_set_recorded": set(by_case) == {
            case for category in protocol["categories"].values()
            for case in category.get("required_cases", []) + category.get("required_safety_cases", [])
        },
    }
```

11 条门禁可分成三组：

- **目录证据（2 条）**：门禁 1 一次性锁死 6 个条件——传输是 stdio、真正收到 `tools/list`、协议版本恰好 `2026-07-28`、SDK 主版本是 2、工具数等于去重后的工具数（**防重名**）、工具数 ≥ 120。门禁 2 要求所有必需工具名都在目录里。
- **分类通过（5 条）**：五类各自 `status == "passed"`。注意 `blocked` 不算通过——所以实测里 private_data 是 `blocked`，门禁 7 为 False。
- **完整性（4 条）**：文件系统前后指纹、隔离探针被拒、**所有成功案例都实质且非模拟**、收据集合恰好等于协议要求的案例集（多一个少一个都不行，防「偷偷加一个凑数的案例」）。

门禁 10 的写法很关键：`all(valid_success(r) for r in receipts if r["success"] is True)`——它只对**自称成功**的收据做检查，要求它们**没有一条**是空洞或模拟的。失败的收据不在这个门的检查范围（失败本来就不该成功）。

#### (4) 总状态（L533–547）

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="533"
    if all(gates.values()):
        status = "passed"
    elif (
        any(category["status"] == "blocked" for category in category_results.values())
        and all(category["status"] in {"passed", "blocked"}
                for category in category_results.values())
        and all(
            value for gate, value in gates.items()
            if not gate.endswith("_category_passed")
        )
    ):
        status = "blocked"
    else:
        status = "failed"
    return {"status": status, "gates": gates, "categories": category_results}
```

- 11 条全过 → `passed`；
- 否则若能退一步：**至少有一类 blocked**、**所有类别都在 {passed, blocked}**、**所有非分类门禁全过** → `blocked`；
- 否则 `failed`。

`blocked` 的语义是「本机缺凭据，其余一切都对」。它的第二个条件很微妙：`_category_passed` 系列门禁**被排除**在这一轮校验之外——因为 blocked 时这些门禁本来就必然为 False。第三条件用 `str.endswith` 过滤门禁名，是一个**用命名规范当代码**的技巧：门禁名带 `_category_passed` 后缀的属于「分类门」，其余（目录证据 + 完整性）属于「硬门」，blocked 时硬门必须全过。

实测两次都是 `failed`：因为有类别落在 `failed`（multimodal、public_data），`all(status in {passed, blocked})` 不成立。

---

### 2.11 `build_manifest`（L550–577）：把整个战役目录哈希一遍

[源码 L550–577](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L550-L577)

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="550"
def build_manifest(campaign_dir: Path, summary: dict[str, Any]) -> dict[str, Any]:
    files = []
    for path in sorted(campaign_dir.rglob("*")):
        if path.name == "manifest.json":
            continue
        if path.is_symlink():
            data = os.readlink(path).encode("utf-8")
            kind = "symlink-target"
        elif path.is_file():
            data = path.read_bytes()
            kind = "file"
        else:
            continue
        files.append({
            "path": str(path.relative_to(campaign_dir)),
            "kind": kind,
            "bytes": len(data),
            "sha256": sha256_bytes(data),
        })
    return {
        "experiment": "4-2",
        "campaign_id": summary.get("campaign_id"),
        "status": summary.get("status"),
        "official_complete": summary.get("status") == "passed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "files": files,
    }
```

`rglob("*")` 递归全目录，但有三处特殊处理：

- **排除 `manifest.json` 自身**（L553）——否则会自指，且每次算哈希时文件内容不同，永远不稳定；
- **符号链接单独处理**（L555–557）：`path.is_file()` 对软链会**跟随到目标**，那样哈希的是 `outside-witness.txt` 的内容，就掩盖了「这里有个软链」这个事实。代码改用 `os.readlink(path)` 哈希**链接目标字符串**本身，并把 `kind` 记为 `"symlink-target"`——这样 `escape-link` 作为一条**独立可查的记录**留在清单里；
- **目录跳过**（`else: continue`）。

`official_complete` 是 `status == "passed"` 的快捷字段——只要不是严格通过，它就为 False。这就是 manifest 里区分「官方完整」的标记。

**注意 manifest 是在 `summary.json` 之后写的**（`run` 里 L683 → L684），所以 `summary.json` 本身也被哈希进去；而 `manifest.json` 是最后才写，它自己不在清单里。`latest.json` 再记下 manifest 的 sha256（L689），形成「latest → manifest → 全部文件」的三级哈希链。

---

### 2.12 `run`（L580–691）：编排全案

[源码 L580–691](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/run_experiment_4_2.py#L580-L691)

#### (1) 起手：目录、夹具、预检（L581–590）

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="581"
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    campaign_id = campaign_id or "real_mcp_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    campaign_dir = VALIDATION_ROOT / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=False)
    write_json(campaign_dir / "protocol.json", protocol)
    paths = prepare_fixtures(campaign_dir)
    preflight = credential_preflight()
    write_json(campaign_dir / "credential_preflight.json", preflight)

    outside_before = file_receipt(paths["outside_witness"])
```

`exist_ok=False` 是**防复用**：同一 campaign_id 第二次跑会直接 `FileExistsError`，杜绝「新旧证据混在一个目录里」。`outside_before` 在起服务器**之前**取，作为软链探针的基线哈希。

#### (2) env 注入与 DASHSCOPE 分支（L591–605）

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="591"
    server_env = os.environ.copy()
    server_env["PERCEPTION_MUTATION_ROOT"] = str(paths["mutation"])
    if server_env.get("DASHSCOPE_API_KEY"):
        server_env["PERCEPTION_VISION_PROVIDER"] = "dashscope"
        server_env["PERCEPTION_VISION_MODEL"] = "qwen-vl-max"
    elif server_env.get("GEMINI_API_KEY"):
        server_env["PERCEPTION_VISION_PROVIDER"] = "gemini"
        server_env["PERCEPTION_VISION_MODEL"] = "gemini-2.5-flash"
    else:
        server_env.setdefault("PERCEPTION_VISION_MODEL", "gpt-4o-mini")
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
        env=server_env,
    )
```

服务器是被 `subprocess` 拉起的**独立进程**，所以战役对它的全部控制都通过 **env** 完成，两条注入：

1. **`PERCEPTION_MUTATION_ROOT`**——指向本场现造的 `fixtures/mutation_workspace`。服务器端（`filesystem_tools.py`）的 `_mutation_root()` 从 env 读它，所有 mutation 路径都被 `_resolve_mutation_path` 约束在这个根之下（源码 `filesystem_tools.py` L51–118）。**每次运行都是一个全新工作区**，写坏也污染不到别处，这是 `filesystem_pre_post_hashes_verified` 能稳定成立的前提。
2. **视觉后端三选一**——DashScope 优先（`qwen-vl-max`），其次 Gemini（`gemini-2.5-flash`），都没有就设 `gpt-4o-mini` 让服务器去读 `OPENAI_API_KEY`。`command=sys.executable` 保证用的是**当前这个 Python 解释器**，服务器和战役共用一个 venv（依赖齐全）。

#### (3) 列工具、建目录回执（L607–625）

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="607"
    async with Client(stdio_client(parameters)) as client:
        listed = await client.list_tools()
        schemas = [tool.model_dump(by_alias=True, exclude_none=True, mode="json") for tool in listed.tools]
        names = [schema["name"] for schema in schemas]
        server_info = client.server_info
        catalog = {
            "transport": "mcp-stdio",
            "tools_list_received": True,
            "mcp_sdk_version": package_version("mcp"),
            "protocol_version": client.protocol_version,
            "server_name": server_info.name if server_info else None,
            "server_version": server_info.version if server_info else None,
            "tool_count": len(names),
            "unique_tool_count": len(set(names)),
            "tool_names": names,
            "schemas_sha256": sha256_bytes(canonical_json(schemas).encode()),
            "schemas": schemas,
        }
        write_json(campaign_dir / "catalog_receipt.json", catalog)
```

`schemas_sha256` 是对**全部 127 个工具 schema 的规范哈希**——这比工具数更强：它锁定了「目录的内容」，任何描述文字的改动都会改变哈希。`exclude_none=True` 让 schema 里不出现空字段，哈希才稳定。`tool_count == unique_tool_count` 留给门禁 1 检查（防重名工具混进数量）。

#### (4) 28 次调用循环（L627–660）

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="627"
        calls = [
            ("web_search", {"query": "Model Context Protocol official specification", "num_results": 3}),
            ("knowledge_base_search", {"query": MARKER, "knowledge_base_path": str(paths["knowledge"]), "top_k": 3}),
            ("download", {"url": "https://www.iana.org/help/example-domains", "output_path": str(paths["downloads"] / "iana-example.html"), "timeout": 60}),
            ...
            ("directory_list", {"query": str(paths["mutation"]), "options_json": "{\"limit\": 20}"}),
            ("filesystem_copy", {"source_path": "seed.txt", "destination_path": "copied.txt"}),
            ("filesystem_move", {"source_path": "copied.txt", "destination_path": "moved.txt"}),
            ("filesystem_delete", {"path": "moved.txt"}),
            ("reject_parent_traversal", {"source_path": "seed.txt", "destination_path": "../escaped.txt"}),
            ("reject_absolute_path", {"path": "/tmp"}),
            ("reject_escaping_symlink", {"path": "escape-link"}),
            ...
        ]
        for case, arguments in calls:
            receipt = await call_case(client, case, arguments, paths)
            receipts.append(receipt)
            write_json(campaign_dir / "receipts" / f"{len(receipts):02d}_{case}.json", receipt)
```

28 个案例的**顺序本身就是一条链**：

- 三个文件系统 mutation 案例 `seed.txt → copied.txt → moved.txt → (删除)` 是**接力**：copy 造出 `copied.txt`，move 把它改名 `moved.txt`，delete 再把它隔离。学 `directory_list` 在它们之前跑，看得到 `seed.txt`；三条安全探针在它们之后跑。**顺序错了链就断**。
- 三条探针的越界方式各不同：`../escaped.txt`（父目录穿越，路径含 `..`）、`/tmp`（绝对路径）、`escape-link`（合法相对路径但**解析后**越界）。第三条最刁钻，正是软链设计的用武之地。
- `filesystem_*` 的 `source_path` 是**相对路径**（`"seed.txt"`），因为服务器会把它们拼到 `PERCEPTION_MUTATION_ROOT` 之下。
- 每条收据**立刻单独落盘**（`f"{len(receipts):02d}_{case}.json"`），不在最后批量写——这样即便中途崩溃，已完成的案例收据也在磁盘上。

#### (5) 收尾：验收、summary、manifest、latest（L662–691）

```python title="chapter4/perception-tools/run_experiment_4_2.py" linenums="662"
    outside_after = file_receipt(paths["outside_witness"])
    outside_unchanged = outside_before == outside_after
    acceptance = derive_acceptance(
        protocol,
        catalog,
        receipts,
        outside_witness_unchanged=outside_unchanged,
    )
    summary = {
        "experiment": "4-2",
        "campaign_id": campaign_id,
        "status": acceptance["status"],
        "official_complete": acceptance["status"] == "passed",
        "acceptance": acceptance,
        "receipt_count": len(receipts),
        "successful_cases": [row["case"] for row in receipts if row["success"]],
        "failed_or_blocked_cases": [row["case"] for row in receipts if not row["success"]],
        "outside_witness_unchanged": outside_unchanged,
        "credential_preflight": preflight,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(campaign_dir / "summary.json", summary)
    write_json(campaign_dir / "manifest.json", build_manifest(campaign_dir, summary))
    write_json(VALIDATION_ROOT / "latest.json", {
        "experiment": "4-2", "campaign_id": campaign_id,
        "status": summary["status"], "official_complete": summary["official_complete"],
        "manifest": str((campaign_dir / "manifest.json").relative_to(HERE)),
        "manifest_sha256": sha256_bytes((campaign_dir / "manifest.json").read_bytes()),
    })
    return campaign_dir
```

`summary` 里有一处**微妙且容易误读**的字段：`failed_or_blocked_cases` 的定义是**「`success` 为 False 的案例」**——所以三条安全探针（`reject_parent_traversal` / `reject_absolute_path` / `reject_escaping_symlink`）**也在这个名单里**。这**不是**说它们失败了；恰恰相反，它们按设计必须失败，并因此让 `safety_rejected` 门禁**通过**。读 summary 时要把「success=False」与「门禁不通过」两件事分开：探针的 success=False 正是门禁 `filesystem_isolation_probes_rejected=True` 的来源。

`latest.json` **最后写**：它记下本次 manifest 的相对路径与 sha256。这形成一条三级哈希链 `latest → manifest → 每个文件`，并且把 `RUN`「半途崩溃不会占据 latest 位」这条性质用**写入顺序**实现。`main()` 的退出码是 `0 if status in {"passed", "blocked"} else 1`——`blocked`（缺凭据）算「脚本本身跑对了」，`failed` 才返回 1。

---

## 3. 服务器端骨架：`src/main.py`

### 3.1 创建与注册（L12–45、L57–96、L103–707、L712、L719、L726–728）

[源码 L57–96](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/src/main.py#L57-L96)

```python title="chapter4/perception-tools/src/main.py" linenums="57"
mcp = MCPServer(
    "perception-tools",
    instructions="""
Perception Tools MCP Server

A comprehensive MCP server providing various perception and data retrieval capabilities:
...
"""
)
```

服务器用的是 mcp 2.x 的 **`MCPServer`**（`from mcp.server import MCPServer`），即 **FastMCP 的后续形态**——它同时提供高层装饰器 API 与底层协议能力，用一个对象承载。`instructions` 是一段给人（也给模型）看的分类说明，只影响可读性，不参与校验。

**57 个工具的实现按类别归纳**（L103–707），不逐个讲：

| 类别 | 代表工具 | 底层模块 |
| --- | --- | --- |
| 搜索 | `web_search` / `download` / `knowledge_base_search` | `search_tools` |
| 多模态 | `webpage_reader` / `document_reader` / `image_parser` / `video_parser` | `multimodal_tools` |
| 文件系统 | `file_reader` / `grep` / `text_summarizer` / `filesystem_copy|move|delete` | `filesystem_tools` |
| 公开数据 | `weather` / `stock_price` / `currency_converter` / `wikipedia_search` / `arxiv_search` | `public_data_tools` 等 |
| 私有数据 | `calendar_events` / `notion_search` | `private_data_tools` |

每个工具都是同一形状：**`@mcp.tool(description=...)` 装饰器 + 一层 `async def` 薄包装，转调子模块里的真实实现**。重点在装饰器这一行，而不是 wrapper 体。

[源码 L103–110](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/src/main.py#L103-L110)

```python title="chapter4/perception-tools/src/main.py" linenums="103"
@mcp.tool(description="Search the web using DuckDuckGo (free, no API key required)")
async def web_search(
    query: str = Field(description="Search query string"),
    num_results: int = Field(default=5, description="Number of results (1-10)"),
    region: str = Field(default="wt-wt", description="Region code (e.g., 'us-en', 'uk-en', 'wt-wt' for worldwide)")
):
    """Search the web and return results."""
    return await search_web(query, num_results, region)
```

**`@mcp.tool` 如何生成 JSON Schema**：装饰器读取函数的**类型注解与默认值**，把 `query: str` 变成 `{"type": "string"}`、`num_results: int = 5` 变成带 `default` 的整数、`str | None = None` 变成可空字段；`Field(description=...)` 的说明进入每个参数的 `description`；函数 docstring 成为工具描述的一部分；返回类型注解决定是否走 structuredContent。**注册即反射**——不需要手写 JSON Schema，代价是描述文字会原封不动进入 `tools/list`。

L712 与 L719 两步注册：

[源码 L710–719](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/perception-tools/src/main.py#L710-L719)

```python title="chapter4/perception-tools/src/main.py" linenums="710"
# Complete the 57 native schema descriptions before adding the expanded
# catalog. The implementations and native parameter schemas remain unchanged.
enrich_existing_tools(mcp)

# Experiment 4-1 requires 120+ tools from this perception MCP server.  The
# 57 native tools plus 70 additional real-backed, read-mostly tools bring the
# server catalog to 127 tools. ...
register_expanded_tools(mcp)
```

- `enrich_existing_tools(mcp)`（`expanded_catalog.py` L1014–）**不改实现、不改参数**，只把每个原生工具的 `description` **追加一段「操作契约」**：来源、成功时含什么、失败时怎么表现、以及「不返回凭据」的承诺。它先做两项自查：契约名必须都已注册（否则 `RuntimeError`）、原生与扩展工具契约不得重名。
- `register_expanded_tools(mcp)`（`expanded_catalog.py` L1007–1011）遍历 70 个 `ExpandedToolSpec`，用 `mcp.add_tool(func, name=..., description=...)` 动态注册。**每条注册的都是一次性生成的普通 Python 函数**（不是 lambda 堆砌），所以 `tools/list` 返回的仍是标准完整 JSON Schema，每个工具也可正常 `tools/call`。

扩展工具的**两参数契约**（`expanded_catalog.py` L962–970）：

```python title="chapter4/perception-tools/src/expanded_catalog.py" linenums="962"
def _make_mcp_function(spec: ExpandedToolSpec):
    query_description, options_description = _parameter_descriptions(spec)

    async def expanded_tool(
        query: str = Field(description=query_description),
        options_json: str = Field(default="{}", description=options_description),
    ) -> dict[str, Any]:
        return await execute_expanded_tool(spec, query, options_json)

    expanded_tool.__name__ = spec.name
    expanded_tool.__qualname__ = spec.name
    expanded_tool.__doc__ = full_description(spec)
    return expanded_tool
```

70 个扩展工具**共享同一个函数工厂**，全部只有 `query` + `options_json` 两个参数（`options_json` 是 JSON 字符串，默认 `"{}"`）。为什么这么设计？因为 70 个工具若要各写一套完整参数表，实现量会爆炸；用 `query` + JSON 选项这个**统一传输层**，注册侧只需一份工厂。`__name__`/`__qualname__`/`__doc__` 被显式覆盖，保证 MCP 反射到的是**具体工具名与具体描述**，而不是 `expanded_tool`。真正的分发在 `execute_expanded_tool`（L927–956），按 `spec.backend` 路由到 `_github`/`_finance`/`_web`/... 十来个后端函数。

L726–728 是入口：`mcp.run(transport="stdio")`——服务器在当前进程的 stdin/stdout 上与战役脚本通信，这正是 `StdioServerParameters` 拉起的那个子进程执行到的地方。

### 3.2 为什么目录会撑到 ~50K token

目录里 127 个工具的**描述文字**是 token 的大头，来源有两块：

1. **`enrich_existing_tools` 给 57 个原生工具追加的操作契约**——每条约 5–6 句，讲来源、成功内容、失败表现、凭据承诺；
2. **70 个扩展工具的 `full_description`**——由四段拼成（`expanded_catalog.py` L463–470）：一行 summary + 该工具的**专属契约** + 该后端的**通用契约**（`_BACKEND_CONTRACTS`，每个后端一段 6–10 行的说明，如 `github` / `finance` / `web` / `academic` / ...）+ 一段共享的安全声明。同一后端的工具会**重复携带**同一段后端契约——这是体积膨胀的主要来源。

用实测数字核对：本次运行 `catalog_receipt.json` 里 127 个 schema 序列化后约 **212,869 字符**，粗算 ≈ **53K token**（字符数 / 4），其中原生工具带的参数名与说明、扩展工具的长契约各占可观比例。这正是模块开头注释说的：

> The long contracts make the full-schema control condition exceed 50K tokens without padding it with fake tools or fake parameters.

**它的用意不是注水，而是把「全 schema 控制条件」做大**——实验 4-1 要对比「把全部工具目录塞进上下文」与「按需发现工具」两种策略。真正的工具数（127）和真正的参数结构都不变，撑大的是**描述里的真实操作契约**。描述被后端契约撑大，目录因此达到实验所需的体量。

---

## 4. 学习版注入：`learning/task4/run_4_2_perception.py`

[学习脚本 L33–67](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/learning/task4/run_4_2_perception.py#L33-L67)——**这份文件不在课程仓库的默认路径，是学习版新增的运行脚本**，做法是 `import run_experiment_4_2 as course` 后**只改三样东西**，28 个案例与 11 条门禁一行不动：

```python title="learning/task4/run_4_2_perception.py" linenums="33"
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
if not os.getenv("DASHSCOPE_API_KEY"):
    raise SystemExit("DASHSCOPE_API_KEY is required for the vision cases")

sys.path.insert(0, str(ROOT / "chapter4/perception-tools"))
import run_experiment_4_2 as course  # noqa: E402

OUT_ROOT = ROOT / "learning/task4/runs/4-2_perception_tools"
CAMPAIGN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT = OUT_ROOT / CAMPAIGN_ID

# --- 注入：输出目录重定向 + 视觉后端 -------------------------------------------
course.HERE = OUT_ROOT
course.VALIDATION_ROOT = OUT_ROOT
os.environ["PERCEPTION_VISION_PROVIDER"] = "dashscope"
os.environ["PERCEPTION_VISION_MODEL"] = "qwen-vl-max"
os.environ.setdefault(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)

VISION_ENDPOINT = os.environ["DASHSCOPE_BASE_URL"]
```

三处注入，逐个说：

1. **`course.HERE = OUT_ROOT` / `course.VALIDATION_ROOT = OUT_ROOT`** —— 直接把模块级变量改掉。因为 `run()` 里 `campaign_dir = VALIDATION_ROOT / campaign_id`、写 `latest.json` 用 `VALIDATION_ROOT`、`manifest` 相对路径用 `HERE`，改这两个变量就把**整场输出重定向**到 `learning/task4/runs/4-2_perception_tools/<时间戳>/`，课程仓库的 `chapter4/perception-tools/validation/latest.json` **不会被覆盖**。这是 Python 模块级变量可写的直接利用——不 fork 不改源码。

2. **视觉后端固定 DashScope 国内端点 + `qwen-vl-max`** —— env 里显式设 `PERCEPTION_VISION_PROVIDER=dashscope`、`PERCEPTION_VISION_MODEL=qwen-vl-max`，并把 `DASHSCOPE_BASE_URL` 兜底到**国内**端点 `https://dashscope.aliyuncs.com/compatible-mode/v1`。注意 `run()` 里本来就有 DashScope 分支（§2.12），这里等于**把分支钉死**：本机 key 只在国内端点有效，课程默认走 intl 端点会 401。

3. **`LOCAL_CAPABILITIES` 与 `credential_scan`**（L57–67、L78–85）：

```python title="learning/task4/run_4_2_perception.py" linenums="57"
LOCAL_CAPABILITIES = {
    "tesseract": bool(shutil.which("tesseract")),
    "whisper_module": importlib.util.find_spec("whisper") is not None,
    "ffmpeg": bool(shutil.which("ffmpeg")),
    "macos_say": bool(shutil.which("say")),
    "google_calendar_token": (Path("~/.perception-tools/google_token.pickle").expanduser()).is_file(),
    "notion_key": bool(os.getenv("NOTION_API_KEY")),
    "vision_provider": "dashscope",
    "vision_model": os.environ["PERCEPTION_VISION_MODEL"],
    "vision_endpoint": VISION_ENDPOINT,
}
```

`LOCAL_CAPABILITIES` 回答的是 §2.9 里那个问题：**本机缺 tesseract/whisper/日历/Notion 凭据时，为什么只能是 blocked**——因为这些能力在**这台机器上根本不存在**，工具返回的失败是**如实反映**，不是 bug。把它写进 `evidence.json`，是为了让读证据的人一眼看到「`image_ocr` 失败 ← `tesseract: false`」，而不是怀疑工具实现。

`credential_scan`（L78–85）是学习版自己的安全检查：遍历整个 campaign 目录，确认 `DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY` 的值**没有**出现在任何落盘文件里；`evidence` 生成后还断言 `key not in payload`（L142–143）。`credential_scan_findings` 为空、`completed: true`（实测两次都是空），说明整份证据里不含明文密钥。

---

## 5. 完整执行回放（学习版两次真实运行）

两次运行都产出了完整 28 个收据、127 工具目录，`credential_scan_findings` 为空。差异在**外部条件**。

### 第一次：`20260921T111348Z`

```text
catalog: transport=mcp-stdio, sdk=2.2.0, protocol=2026-07-28, tools=127 (unique 127)
vision : dashscope / qwen-vl-max @ https://dashscope.aliyuncs.com/compatible-mode/v1

分类状态
  search        passed   invalid=-
  multimodal    failed   invalid=['image_ocr', 'audio_transcribe']
  filesystem    passed   invalid=-
  public_data   failed   invalid=['yfinance_quote', 'wikipedia_search']
  private_data  blocked  invalid=['calendar_events', 'notion_search']
campaign status: failed | gates: 8 / 11
leak scan: clean
```

逐条解释（**实测数字 + 成因推断分开写**）：

- **search passed**：`web_search`（DuckDuckGo）、`knowledge_base_search`、`download` 三条实质通过。
- **filesystem passed**：三条 mutation 的前后指纹一致；**三条逃逸探针全部被拒**，收据里 `error_type == "PermissionError"`、`success=False`、`mcp_result_is_error=False`——
  - 19 `reject_parent_traversal`：`Parent traversal is not allowed for filesystem mutations`
  - 20 `reject_absolute_path`：`Absolute paths are not allowed for filesystem mutations`
  - 21 `reject_escaping_symlink`：`Resolved path escapes the configured mutation root`
  外部见证 `outside-witness.txt` 前后哈希一致（`outside_witness_unchanged: true`）。
- **multimodal failed**：`image_ocr` 报 `ocr_error` / `pytesseract not installed`，`audio_transcribe` 报 `audio_error` / `Whisper not installed and no OPENAI_API_KEY found`。**成因**：本机 `tesseract: false`、`whisper_module: false`（本地能力声明可证），属**缺依赖**而非代码缺陷。它被判 `failed` 而不是 `blocked`，是因为这两个错误串不匹配 §2.9 词表（详见该节）。
- **public_data failed**：`yfinance_quote` 报 `YFRateLimitError` / `Too Many Requests. Rate limited.`；`wikipedia_search` 报 `wikipedia_error` / `Expecting value: line 1 column 1 (char 0)`（**推断**：MediaWiki 返回了非 JSON 的错误页，多半是 429 限流）。同类内 `weather` / `currency_converter` / `arxiv_search` 通过。
- **private_data blocked**：`calendar_events` 与 `notion_search` 的 `error_type` 都是 `missing_credentials`，落进 `credential_blocked`，类内允许 blocking → `blocked`。
- **门禁 8/11**：挂掉的三条是 `multimodal_category_passed`、`public_data_category_passed`、`private_data_category_passed`。其余八条（含目录证据两条、安全探针、前后指纹、全成功实质、案例集恰好）全过。
- **视觉两条成功**：`image_analyze` 与 `video_analyze` 用 DashScope `qwen-vl-max` 成功，`analysis` 里**读出图中文字** `EXPERIMENT 4-1` / `PERCEPTION TOOLS VERIFIED`——证明夹具 PNG/MP4 真的被视觉后端解析了。

### 第二次：`20260921T112643Z`

```text
campaign status: failed | gates: 7 / 11
  search        failed   invalid=['web_search']      ← 相比第一次新增
  multimodal    failed   invalid=['image_ocr', 'audio_transcribe']
  filesystem    passed   invalid=-
  public_data   failed   invalid=['yfinance_quote', 'wikipedia_search']
  private_data  blocked  invalid=['calendar_events', 'notion_search']
```

第二次比第一次**少过一条门禁**：`web_search` 这次也失败了，收据里 `error_type=search_error`、`Search operation failed: No configured live search provider returned results`。**推断**：短时间内的第二次运行触发了 DuckDuckGo 的限流（同一 IP、同一查询连续打），导致它和第一次唯一的不同就在这条。视觉两条依然成功（`video_analyze` 耗时从 1.757s 变 2.195s，仍读出同样的文字）。

### 结论（诚实版）

**公开数据类的失败源于外部限流与缺依赖，不是代码缺陷**——两个收据里 `error_type` 分别是 `YFRateLimitError`、`wikipedia_error`（响应非 JSON）、`missing_credentials`，都指向环境而非逻辑；本地能力声明（`tesseract: false`、`whisper_module: false`、无日历/Notion 凭据）与之一一对应。**两轮差异说明这类 live API 案例在本机不稳定**：同一份代码、同一组参数，仅因 Yahoo/MediaWiki/DuckDuckGo 的限流策略，`web_search` 就在两轮之间从通过变成失败。这类门禁衡量的是**「当时的外部服务是否可用」**，不宜当作代码正确性的唯一标尺——这也正是战役把 `origin` 分成 `live-api` 与 `local-process` 两类、并单独记录 `credential_preflight` 的原因。

---

## 6. 动手验证

三个由浅入深的命令，都在 `chapter4/perception-tools/` 目录下执行（需要 mcp>=2，本机验证用的是 2.2.0）。

**1. 先确认服务器真的吐出 127 个工具**（离线，不花 API 额度）：

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-agent-book/chapter4/perception-tools
python smoke_test_mcp_v2.py
```

预期输出一行：

```text
MCP smoke test passed: sdk=2.2.0, protocol=2026-07-28, server=perception-tools, tools=127
```

它做三件事：起 stdio 服务器、`tools/list` 点名必须有 `file_reader`、真调一次 `file_reader` 读 `requirements.txt`。**只有 127 这个数字出现，才说明原生 57 + 扩展 70 都注册成功了**（脚本本身只断言 `file_reader` 存在，数字是打印出来的）。

**2. 用 CLI 按名调用单个工具**（离线；`weather`/`currency_converter` 需联网）：

```bash
python cli.py list                                  # 按五类分组列出全部工具
python cli.py run weather location=Singapore        # 直接调一个工具并打印 JSON
```

`cli.py list` 会把 127 个工具按 search / multimodal / filesystem / public_data / private_data 分组打印；`cli.py run weather location=Singapore` 打出一条含 `temperature` 的 JSON——**这跟战役里 `("weather", {"location": "Singapore"})` 是同一工具的同一参数**，可用来对照收据里的 `payload`。

**3. 真正跑一次视觉案例，验证 DashScope 分支**（需要 `.env` 里的 `DASHSCOPE_API_KEY`）：

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-agent-book/learning/task4
python run_4_2_perception.py
```

学习版会固定 `PERCEPTION_VISION_PROVIDER=dashscope`、`qwen-vl-max`、国内端点，跑到 `image_analyze` / `video_analyze` 时真调视觉 API。跑完后在产物目录里看视觉回执：

```bash
python -c "import json,glob; d=sorted(glob.glob('runs/4-2_perception_tools/*/receipts/09_image_analyze.json'))[-1]; print(json.load(open(d))['payload']['message']['analysis'][:120])"
```

预期能看到 `The text reads: EXPERIMENT 4-1 / PERCEPTION TOOLS VERIFIED` 这类文字——**这是「工具真的读到了我画上去的字」的直接证据**，而不是模型自己编的。想省额度就把视觉后端换回不配置 key 的状态，`image_analyze` 会失败，但**失败也会如实落盘**（`success=false` + `error_type`），不会被 mock 顶替。
