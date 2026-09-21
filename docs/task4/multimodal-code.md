# 多模态三范式：一步步读源码

[实验说明](multimodal.md) · [完整证据与复现](evidence.md#4-3) · [学习运行脚本](../assets/task4/run_4_3_multimodal.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent)

**主文件**：[chapter4/multimodal-agent/campaign.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py)（401 行，实验 4-3 的实拍脚本：12 行对照矩阵、工具定义、判分与评审）；配套 [agent.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/agent.py)（1134 行，三种范式的「产品级」实现）、[create_sample.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/create_sample.py)、[config.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/config.py)。

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>本页按源码顺序把 campaign.py 的每个函数过一遍——先给函数清单证明一个不漏，再逐个拆，最后用一次真实执行把整条调用链串起来。agent.py 只精读与三范式直接相关的那条线；SDK 适配器（Gemini / OpenAI / OpenRouter / 流式）归并成一段。读完本页，你应该能说出「同一份含图表的 PDF，为什么三种范式会给出三种不同的答案」。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号，链接指向课程仓库固定提交。**学习运行脚本原文**来自 `learning/task4/run_4_3_multimodal.py`——它 `import campaign` 直接复用课程函数（`data_url` / `answer_text` / `answer_vision` / `answer_with_tool` / `exact_correct` / `judge_answers` / `QUESTIONS` / `TOOL` / `SEED`），只重写了 `local_extract` / `render_pdf` / recorder / 主循环，所以学习版矩阵与课程逐字一致。**教学示意**仅用于解释数据形状，不是任何一方的原文。

---

## 1. 函数清单地图

### (a) campaign.py 全部 def（`grep -n "^def \|^async def \|^class \|^    def "` 核对）

| # | 函数/常量 | 行号 | 一句话作用 | 谁调用它 |
| --- | --- | --- | --- | --- |
| — | `PROJECT_DIR` / `CHAPTER_DIR` / `sys.path` | L28–32 | 本文件与 chapter4 目录路径，并把 chapter4 挂上 `sys.path` | 全文件 |
| — | `ARK_ENDPOINT` / `MOONSHOT_ENDPOINT` / `SEED` | L34–36 | 视觉作答端点 / 评审端点 / 固定种子 37 | `main`、各 `answer_*` |
| — | `QUESTIONS` | L37–50 | 两个问题 + 标准答案 + 正则判分模式 | `main` |
| — | `TOOL` | L51–62 | `inspect_visual` 的函数 schema（实验的「工具」） | `answer_with_tool` |
| 1 | `CheckpointRecorder`（class） | L65–77 | 带即时落盘的 recorder 基类 | `main` |
| 2 | `CheckpointRecorder.__init__` | L66–69 | 存检查点路径并建父目录 | — |
| 3 | `CheckpointRecorder.create` | L71–77 | 转发调用，**无论成败都立刻把 `self.calls` 写盘** | 所有 `answer_*` / 判定调用 |
| 4 | `data_url` | L80–82 | 文件 → `data:<mime>;base64,...` 数据 URL | `answer_vision` |
| 5 | `local_extract` | L85–96 | 本地把工件转成纯文本（tesseract / pdftotext 两条路径） | `main` |
| 6 | `render_pdf` | L99–106 | `pdftoppm -r 180` 把 PDF 首页栅格化成 PNG | `main` |
| 7 | `answer_text` | L109–120 | 「提取为文本」臂：只喂提取文本，拿不到就说拿不到 | `main` |
| 8 | `answer_vision` | L123–139 | 「原生多模态」臂：图片 + 问题直接问视觉模型 | `main`、`answer_with_tool`（二次调用） |
| 9 | `answer_with_tool` | L142–199 | 「工具化按需分析」臂：决策 → 执行 → 收尾三段 | `main` |
| 10 | `exact_correct` | L202–203 | 答案是否命中全部 `required_patterns`（正则判分） | `main` |
| 11 | `judge_answers` | L206–231 | 外部模型评审（JSON 契约 `{items:[{id,correct,score,reason}]}`） | `main` |
| 12 | `tool_version` | L234–236 | 取本地工具版本首行，写进证据 | `main` |
| 13 | `main` | L239–397 | 编排：建 recorder → 样例 → 栅格化 → 12 行矩阵 → 评审 → 验收 → 落证据 | 入口 |

### (b) agent.py 与三范式相关的函数

| # | 函数/类 | 行号 | 一句话作用 |
| --- | --- | --- | --- |
| 1 | `Message`（含 `to_dict`） | L29–46 | 统一消息格式（role/content/tool_calls/tool_call_id/name） |
| 2 | `MultimodalContent` | L50–88 | 多模态内容容器：`__post_init__` L60–72 补 MIME、`get_bytes` L74–84、`get_base64` L86–88 |
| 3 | `MultimodalTools`（class） | L91–301 | **工具侧的视觉执行器**：把多模态内容送去视觉模型 |
| 4 | `MultimodalTools.__init__` | L94–95 | 反向持有 agent（拿 config / 当前模型） |
| 5 | `MultimodalTools.analyze_image` | L97–109 | 图像问答入口：按 provider 分派 Doubao / OpenAI |
| 6 | `MultimodalTools.analyze_pdf` | L122–131 | PDF 问答入口：走 Gemini |
| 7 | `MultimodalTools._analyze_with_openai` | L133–165 | 拼 `image_url` base64 消息，调 OpenAI 兼容端点 |
| 8 | `MultimodalTools._analyze_with_doubao` | L167–193 | 同上，走豆包 1.6 |
| 9 | `MultimodalAgent.__init__` | L306–328 | 装配 config / 模式 / 工具开关 |
| 10 | `set_multimodal_tools_enabled` | L330–405 | 开关工具，并写出三个工具 schema（`analyze_image/audio/pdf`） |
| 11 | `process_multimodal_content` | L411–423 | **范式分派器**：`native` → `_process_native`，`extract_to_text` → `_extract_to_text` |
| 12 | `_process_native` | L425–444 | 原生臂总入口，再按 provider 分派（L437–444） |
| 13 | `_extract_to_text` | L600–609 | 提取臂：先 `_extract_single_content`，再 `_answer_with_context` |
| 14 | `_extract_single_content` | L611–620 | 按 `content.type` 分派到 pdf / image / audio 三个提取器 |
| 15 | `_extract_pdf_to_text` | L622–674 | PDF → 文本（课程版走 Gemini，带 thinking 打印） |
| 16 | `_extract_image_to_text` | L676–719 | 图像 → 「详细描述」（注意：是让模型描述，不是 OCR） |
| 17 | `_answer_with_context` | L780–841 | 用纯文本上下文回答（OpenAI 兼容路径 L825–841） |
| 18 | `_execute_tool` | L1071–1098 | **工具侧的调度器**：把 tool_call 名字映射到 `MultimodalTools` 方法 |
| 19 | `load_and_extract_content` | L1112–1130 | 提取模式下把文档正文塞进会话历史 |
| 归并 | 其余全部（21 项，一个不漏） | 见右列 | `class MultimodalAgent`（L303–305）；`Message.to_dict`（L37–46）；`MultimodalContent.__post_init__`（L60–72）/`get_bytes`（L74–84）/`get_base64`（L86–88）；`MultimodalTools.analyze_audio`（L111–120）、`_analyze_with_gemini_audio`（L195–246）、`_analyze_with_gemini_pdf`（L248–300）；`MultimodalAgent.add_message`（L407–409）；`_process_native_openrouter`（L446–473）、`_process_native_gemini`（L475–529）、`_process_native_openai`（L531–562）、`_process_native_doubao`（L564–598）；`_extract_audio_to_text`（L721–778）；`chat`（L843–872）、`_stream_response`（L874–885）、`_stream_gemini_response`（L887–991）、`_stream_openai_response`（L993–1069）；`_get_response`（L1100–1105）、`reset_conversation`（L1107–1110）、`get_conversation_history`（L1132–1134）。这一整块是「同一件事在四个厂商 SDK 上各写一遍」的样板代码 + 数据类小工具 + 音频路径，与三范式的差异无关，本页只在必要时点名行号（其中 `_stream_openai_response` 的工具循环在 3.14 第 (5) 点提到） |

### (c) 另外两个文件

| 文件 | 函数 | 行号 | 一句话作用 |
| --- | --- | --- | --- |
| create_sample.py | `create_chart` | L31–58 | 出柱状图 PNG，**数值只标在柱顶**（L39–48） |
| create_sample.py | `create_report_pdf` | L61–98 | 图表 + 定性正文合成 PDF（`RLImage` L95 把 PNG 当栅格图嵌入） |
| create_sample.py | `main` | L101–134 | 离线出样例，`--output-dir` / `--no-pdf` |
| config.py | `ExtractionMode` | L29–32 | **只有两种模式**：`NATIVE` / `EXTRACT_TO_TEXT` |
| config.py | `Provider` / `ModelConfig` / `Config` | L35–186 | 三个厂商枚举、模型配置、key 读取与 OpenRouter 兜底 |

> 一个必须记住的结构事实：`ExtractionMode` 里**没有第三种模式**。「工具化按需分析」在本章落了两处——实验用 campaign.py 自己的 `answer_with_tool`（本页主体），产品代码用 `MultimodalAgent(enable_tools=True)` + `MultimodalTools` + `_execute_tool`（第 (b) 表 3/10/18 条）。两条线共用同一个「把多模态模型封装成工具」的思想，实现不同。

---

## 2. 主线调用图

```text
campaign.main  (L239)
 ├─ 若 test_files/ 无样例 → subprocess python create_sample.py   (L266–267)
 │       └─ sample_chart.png（数值只在图上）+ sample_report.pdf（正文只有定性描述）
 ├─ render_pdf(pdf → 首页 PNG @180dpi)                            (L271)
 │       课程 pdftoppm -singlefile -r 180 / 学习版 PyMuPDF get_pixmap(dpi=180)
 ├─ 逐工件 (png, pdf)，每个工件先提取一次:                          (L278–290)
 │    local_extract(kind, original) → (纯文本, 提取收据)
 │        png → tesseract --psm 6   / pdf → pdftotext -layout
 │    逐问题 (highest, lowest_gap):                                (L291–338)
 │     ├─ answer_vision(visual, q)          → 行 paradigm=native-multimodal
 │     ├─ answer_text(extracted, q)         → 行 paradigm=extract-to-text
 │     └─ answer_with_tool(extracted, visual, q) → 行 paradigm=tool-on-demand
 │          ├─ decision  (tools=[TOOL], tool_choice="auto")        (L160–168)
 │          ├─ 若有 tool_calls: answer_vision(...) ← 二次调用        (L179–185)
 │          │      结果作为 {"role":"tool"} 回灌消息                (L189)
 │          └─ final     (tools=[TOOL], tool_choice="none")        (L190–198)
 │     每行: exact_correct(answer, required_patterns) → 布尔          (L202)
 ├─ judge_answers(评审客户端, rows)                                 (L340)
 │      12 行一次性打包成 JSON 送给外部评审 → 每行 {correct,score,reason}
 ├─ summary: 按范式聚合 exact_accuracy / judge_accuracy / 延迟       (L345–352)
 ├─ acceptance 八条自检                                             (L356–368)
 └─ write_campaign_evidence(...) → evidence/receipts/manifest/latest (L387–393)
```

一句话概括三种范式的信息流差别：

- **native**：`图像 → 模型`（无中间层，视觉信息零损耗）
- **extract-to-text**：`图像 → 本地提取器 → 纯文本 → 模型`（中间层是瓶颈；图上数值在这一步就没了）
- **tool-on-demand**：`图像 → 本地提取器 → 纯文本 → 模型决策 →（需要时）视觉工具 → 模型收尾`（承认提取有损，用一次额外调用补回来）

---

## 3. 逐函数讲解（严格按源码顺序）

### 3.1 `QUESTIONS`（L37–50）：为什么判分要用正则而不是模型

[chapter4/multimodal-agent/campaign.py · L37–L50](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L37-L50)


```python title="chapter4/multimodal-agent/campaign.py" linenums="37"
QUESTIONS = [
    {
        "id": "highest",
        "question": "Which quarter had the highest revenue, and what was the exact value?",
        "expected": "Q4, $180M",
        "required_patterns": [r"\bQ4\b", r"(?:\$\s*)?180\s*M"],
    },
    {
        "id": "lowest_gap",
        "question": "Which quarter had the lowest revenue, what was its value, and by how much did Q4 exceed it?",
        "expected": "Q3, $95M; Q4 exceeded it by $85M",
        "required_patterns": [r"\bQ3\b", r"(?:\$\s*)?95\s*M", r"(?:\$\s*)?85\s*M"],
    },
]
```

两个问题各带三样东西：`question`（发给模型的原文）、`expected`（给人看的参考答案）、`required_patterns`（机器判分用的正则列表）。

关键在 `required_patterns` 的写法：

- `\bQ4\b` 用词边界卡住 Q4，避免被 `Q40` 之类误命中；
- `(?:\$\s*)?180\s*M` 里货币符号是**可选**的、中间允许空格——模型写 `$180M`、`180M`、`$ 180 M` 都算命中。这正是学习版实测里模型回答 `$180 million`（写成单词）时**没有**被 `180\s*M` 命中的原因——正则只认 `M` 后缀。

**为什么不用模型判分**：判分必须独立于生成。如果这 12 行由同一个模型打分，模型对图表的错觉会同时污染答案和评分，实验就失去了刻度。所以 campaign.py 用了**两层**判分：第一层是这里的正则（确定性、零成本、可复现，`exact_correct`），第二层才是外部模型评审（`judge_answers`，只看语义是否等价）。两层结果都进证据，互相印证。

!!! note "判分独立性的底线"
    正则判分有一个已知代价：`$180 million` 这种等价但格式不同的答案会被判错。学习版实测里 native 臂写的是 `$180 million`，`required_patterns` 里的 `180\s*M` 仍能命中（因为同一句里还出现了 `$180M`）；但 `lowest_gap` 那条要求 `85M`，若模型只写 `$85 million` 就会被判错。这是**有意为之的严格**：宁可错杀，不要放过——精确数值任务里「写成单词」本身就是一种信息损失。

### 3.2 `TOOL`（L51–62）：工具 schema 的语义

[chapter4/multimodal-agent/campaign.py · L51–L62](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L51-L62)


```python title="chapter4/multimodal-agent/campaign.py" linenums="51"
TOOL = {
    "type": "function",
    "function": {
        "name": "inspect_visual",
        "description": "Inspect the original chart or PDF page when exact visual, spatial, or numeric evidence is needed.",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
}
```

只有一个工具、一个参数。三个设计点：

1. **工具名与描述一起构成「何时调用」的语义**。描述句里那句 `when exact visual, spatial, or numeric evidence is needed` 就是调用条件——**只在「精确数值或空间关系没有明确建立」时才调用**。这句话不是给人读的，是给决策模型读的：它必须能对照手上的提取文本判断「我现在的信息够不够」。学习版把同一句话在 system prompt 里又说了一遍（见 3.9）。
2. **参数只有 `question`**，没有 `image_path`。学习者可以对比 agent.py 的 `analyze_image` schema（L341–362），那里有 `image_path` + `query` 两个参数——因为产品版是通用工具，模型得自己指定文件；实验版只有一个固定工件，路径由宿主代码闭包带进 `answer_vision`（L179–185），不交给模型填。**把可变量从工具参数里拿掉，是降低工具调用失败率的常用手法**。
3. 没有 `tool_choice="required"`：模型有权不调。`tool_selected` 这个字段（L171）记录的就是模型的真实选择——如果提取文本已经够用，工具臂应该表现为「不调」，这才叫「按需」。

### 3.3 `CheckpointRecorder`（L65–77）：每次调用立即落盘

[chapter4/multimodal-agent/campaign.py · L65–L77](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L65-L77)


```python title="chapter4/multimodal-agent/campaign.py" linenums="65"
class CheckpointRecorder(ChatRecorder):
    def __init__(self, *args: Any, checkpoint: Path, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.checkpoint = checkpoint
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)

    def create(self, *, purpose: str, **request: Any) -> Any:
        try:
            return super().create(purpose=purpose, **request)
        finally:
            self.checkpoint.write_text(
                json.dumps(self.calls, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
```

父类 `ChatRecorder`（[experiment_utils.py · L90–L131](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/experiment_utils.py#L90)）做的事：包装任意 OpenAI 兼容客户端，`create(purpose=..., **request)` 转发调用并记录 request/response/usage/latency——**设计上从不序列化凭据**。

子类只加一件事：`finally` 块里把**全部** `self.calls` 立刻写盘。用 `finally` 而不是 `except` 是关键——成功要写，失败也要写（父类在失败路径里会把 `error` 记进 calls 再 re-raise）。所以：

- 实验跑到第 11 行崩溃，前 10 行的请求/响应/延迟全都在 `validation/checkpoints/<时间戳>-ark.json` 里；
- 崩溃点之后的重跑可以看到「上次失败在第几个 purpose」——**purpose 字符串就是账本**（下一节每个调用都带 `purpose=f"..."`）；
- 写盘是直接覆盖整文件（`write_text`），不是追加。单进程串行调用下没有并发问题；这也是它比 task3 的检查点机制简单的地方——**4-3 是一次性实拍，不做断点续跑，只做「崩了也有据可查」**。

学习版的 `RoutingRecorder`（下节 3.17.1）复刻了这个语义，并且**在失败时也 `raise`**——保持与课程相同的失败可见性。

### 3.4 `data_url`（L80–82）：base64 数据 URL

[chapter4/multimodal-agent/campaign.py · L80–L82](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L80-L82)


```python title="chapter4/multimodal-agent/campaign.py" linenums="80"
def data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
```

OpenAI 兼容的视觉接口接受两种图片地址：http(s) URL 或 **data URL**。这里走后者——把整个文件读进内存、base64 编码，拼成 `data:image/png;base64,iVBORw0KGgo...`。三个要点：

- MIME 只按后缀判两档（`.png` → `image/png`，其余一律 `image/jpeg`）。学习版实测该前缀确实是 `data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA4QAAAJYCAYAAA`（PNG 魔数的 base64 形态），总长 46902 字符；
- 一张 6×4 英寸 150dpi 的柱状图 base64 后约 47KB 字符串，直接塞进请求体——**这就是多模态请求为什么比纯文本贵**：每一行 native 与每一条 `tool-vision` 都携带这份体积；
- `read_bytes()` 每次调用都重新读盘（同一张图被读 4 次：native 2 次 + tool 2 次），不做缓存。对实验规模无所谓，对产品代码就是浪费——agent.py 的 `MultimodalContent.get_base64`（L86–88）同样每次重编码，但至少 `get_bytes`（L74–84）留了 `data` 字段可缓存。

配套看 agent.py 的一个坑与修法（L60–72）：`MultimodalContent.__post_init__` 里注释写着「否则原生 OpenAI / Doubao 图像请求会拼出 `data:None;base64,...` 导致 400 错误」——MIME 缺失时先按文件名猜、再按声明的模态兜底。`data_url` 把 MIME 硬编码在两档上，正是为了不踩这个坑。

### 3.5 `local_extract`（L85–96）：tesseract / pdftotext 两条路径

[chapter4/multimodal-agent/campaign.py · L85–L96](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L85-L96)


```python title="chapter4/multimodal-agent/campaign.py" linenums="85"
def local_extract(kind: str, original: Path) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()
    if kind == "png":
        command = ["tesseract", str(original), "stdout", "--psm", "6"]
    else:
        command = ["pdftotext", "-layout", str(original), "-"]
    proc = subprocess.run(command, text=True, capture_output=True, check=True)
    return proc.stdout.strip(), {
        "command": command,
        "stderr": proc.stderr,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }
```

「提取为文本」臂的全部实现就是这一行外部命令调用。两条路径的适用性完全不同：

| 路径 | 命令 | 操作对象 | 能拿到什么 | 拿不到什么 |
| --- | --- | --- | --- | --- |
| PNG | `tesseract <png> stdout --psm 6` | **像素** | 栅格化后的文字（OCR） | 表格结构、空间关系、OCR 失败即空 |
| PDF | `pdftotext -layout -` | **文本层** | PDF 里排好版的**真文字** | 一切以图片形式存在的内容（本章的图表数值） |

- `--psm 6` 是 page segmentation mode 6：「假定是一整块统一文本」。对柱状图这种稀疏、随机分布的标注文字不是最优 psm（更适合的是 psm 11「稀疏文本」），但能读到柱顶标签；这是 OCR 路径的**不确定性**来源之一。
- `-layout` 让 pdftotext 尽量保留原始排版（多栏对齐），代价是输出里会有大量空格。
- `check=True` + 缺二进制会抛 `FileNotFoundError`——**本机（macOS）没有 tesseract / pdftotext / pdftoppm，课程原版在这里直接崩**（实测：三者均 `FileNotFoundError`）。学习版因此把 `local_extract` 整个换掉（见 3.17.2）。
- 返回的是**二元组**：文本 + 收据。收据里 `command` / `stderr` / `latency_ms` 全部进证据——「用哪条命令、多久、报了什么错」都可复查。这个「文本 + 收据」的形状被学习版逐字继承。

`main` 里每个工件只提取**一次**（L279），三条臂共用同一份 `extracted`（L311 / L326）——这保证了三条臂的差别只来自「怎么用文本」，不来自「文本本身不同」。

### 3.6 `render_pdf`（L99–106）：同一份内容两种呈现的前提

[chapter4/multimodal-agent/campaign.py · L99–L106](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L99-L106)


```python title="chapter4/multimodal-agent/campaign.py" linenums="99"
def render_pdf(pdf: Path, output: Path) -> None:
    prefix = output.with_suffix("")
    subprocess.run(
        ["pdftoppm", "-png", "-singlefile", "-r", "180", str(pdf), str(prefix)],
        check=True,
        capture_output=True,
        text=True,
    )
```

`pdftoppm -png -singlefile -r 180` 把 PDF **第一页**按 180 dpi 栅格化成 PNG。

为什么这一步是整个实验成立的前提：视觉臂要「看」PDF，但 OpenAI 兼容的 `image_url` 只吃图片。把 PDF 首页渲染成图，就等于**让同一个工件有了两种表示**——

- 对视觉模型：`sample_report.pdf` 与它的 180dpi 渲染页是**同一张图**（正文段落 + 嵌入的柱状图都在里面）；
- 对 `pdftotext`：PDF 里只有**正文那 359 个字符**，柱状图是 `RLImage` 嵌进去的栅格图，图上标签是像素不是文字。

于是「pdf 工件」这一侧的三条臂构成了严格的对照：**同一份 PDF，视觉能读到数值，文本提取读不到**。`-singlefile` 让输出名恰好是 `<prefix>.png`；180 dpi 是清晰度与体积的折中（更高 dpi 会让 base64 更大、延迟更高）。工件表（L272–275）把 `("pdf", pdf, rendered_pdf)` 三元组写死，`original` 用于提取、`visual` 用于看图——**注意两边用的不是同一个文件**，这是全实验最容易被忽略的一行。

### 3.7 `answer_text`（L109–120）：文本臂的 system prompt

[chapter4/multimodal-agent/campaign.py · L109–L120](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L109-L120)


```python title="chapter4/multimodal-agent/campaign.py" linenums="109"
def answer_text(recorder: CheckpointRecorder, model: str, context: str, question: str, purpose: str) -> str:
    response = recorder.create(
        purpose=purpose,
        model=model,
        seed=SEED,
        temperature=0,
        messages=[
            {"role": "system", "content": "Answer only from the extracted text. If it lacks the exact visual evidence, say that it is unavailable."},
            {"role": "user", "content": f"Extracted text:\n{context}\n\nQuestion: {question}"},
        ],
    )
    return response.choices[0].message.content or ""
```

三行请求体，每一行都有用意：

- `temperature=0` + `seed=SEED`（37）：把随机性压到最低，实验可复现；但注意**它不能保证跨厂商一致**——学习版视觉走 qwen-vl-max、文本走 deepseek-flash，种子只对同一模型有意义。
- system prompt 只有一句，但**两半都是关键**：`Answer only from the extracted text` 切断了模型的一切外部知识（它不能凭常识猜「Q4 通常最高」）；`If it lacks the exact visual evidence, say that it is unavailable` 是**明确授权的弃权**——「拿不到就说拿不到」。
- 第二句是**实验设计上最容易被质疑的一点，也是它必须先声明的地方**：如果文本臂被允许用世界知识补全，它就变成「猜」，测出来的不是范式的差异而是运气。给了弃权授权之后，`extract-to-text` 拿低分就干净地归因于「提取层丢了信息」，而不是「模型硬编了一个答案」。
- user 部分是 `Extracted text:` + 原文 + 空行 + `Question:`。注意 `context` 对 PNG 工件可能是**空字符串**——`f"...{context}\n\n..."` 照样拼得出合法请求，不会抛异常。学习版实测 PNG 文本臂的答案正是 `The extracted text does not include any revenue data or quarters, so the answer is unavailable.`——弃权按指令执行。
- 没有 `response_format`：答案要的是自然语言，不是 JSON。

### 3.8 `answer_vision`（L123–139）：原生臂

[chapter4/multimodal-agent/campaign.py · L123–L139](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L123-L139)


```python title="chapter4/multimodal-agent/campaign.py" linenums="123"
def answer_vision(recorder: CheckpointRecorder, model: str, image: Path, question: str, purpose: str) -> str:
    response = recorder.create(
        purpose=purpose,
        model=model,
        seed=SEED,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Read the chart carefully. {question} Give exact values and concise supporting visual evidence."},
                    {"type": "image_url", "image_url": {"url": data_url(image)}},
                ],
            }
        ],
    )
    return response.choices[0].message.content or ""
```

与 `answer_text` 的差别是**结构性的**，值得逐条对照：

| | `answer_text` | `answer_vision` |
| --- | --- | --- |
| system | 有（双重约束：只用文本 / 允许弃权） | **无** |
| content | 纯字符串 | **列表**：`text` + `image_url` 两段 |
| 图像 | 不传 | `data_url(image)` 内联 base64 |
| 措辞 | 「拿不到就说拿不到」 | `Read the chart carefully` + `Give exact values and concise supporting visual evidence` |

两处最值得注意的：

1. **视觉臂没有弃权出口**。「Read the chart carefully. ... Give exact values and concise supporting visual evidence.」只提要求、不提退路——视觉模型在这里被当作一定能看到图。这是实验的意图：视觉臂是「上限臂」，它的分数就是这条任务在这套模型下的天花板。学习版实测它 4/4 全对（含 `$85M` 的减法）。
2. **`answer_vision` 被复用两次**：一次是 native 臂（L299），一次是工具臂内部的二次调用（L179–185）。同一个函数、同一个模型、同一份 `visual`，唯一区别是 `purpose` 前缀不同（`native:` vs `tool-vision:`）——所以证据里能靠 purpose 把两类调用分开计数（验收第 4、6 条靠这个）。

### 3.9 `answer_with_tool`（L142–199）：决策 → 执行 → 收尾三段

函数签名把工具臂的全部输入摆开：`extracted`（便宜文本）+ `image`（原图路径）+ `question` + `artifact_id`（用于命名 purpose）。

**第一段：决策（L150–172）**

```python title="chapter4/multimodal-agent/campaign.py" linenums="150"
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are given a cheap text extraction and one visual-inspection tool. "
                "Call inspect_visual whenever exact chart values or spatial associations are not explicitly established by the text."
            ),
        },
        {"role": "user", "content": f"Extracted text:\n{extracted}\n\nQuestion: {question}"},
    ]
    decision = recorder.create(
        purpose=f"tool-decision:{artifact_id}",
        model=model,
        seed=SEED,
        temperature=0,
        messages=messages,
        tools=[TOOL],
        tool_choice="auto",
    )
    message = decision.choices[0].message
    calls = list(message.tool_calls or [])
    trace: dict[str, Any] = {"tool_selected": bool(calls), "decision": jsonable(message), "executions": []}
    if not calls:
        return message.content or "", trace
```

- system prompt 三个词承担全部语义：`cheap text extraction`（告诉模型手上的文本是廉价、可能有损的）、`one visual-inspection tool`（有且只有一个工具）、`Call ... whenever exact chart values or spatial associations are not explicitly established by the text`（调用条件：精确数值或空间关系**没有被文本明确建立**时）。对照 `TOOL` 的 description（3.2），两处说的是同一句话——**工具描述 + system prompt 双写，是提高调用判断准确率的常规做法**。
- `tool_choice="auto"`：模型自己决定调不调。这是「按需」的全部含义。
- `trace` 这个 dict 是**实验的自证材料**：`tool_selected` 记录是否调用，`decision` 存完整决策消息（含模型的原话），`executions` 先置空。三者最后都进 evidence 的每一行——复盘时能看到「模型在什么文本上做了什么判断」。
- **早退分支**（L172–173）：如果模型判断不需要工具，直接返回它的 content。此时工具臂退化成文本臂，这是合法结果；`tool_selected=False` 会被验收第 5 条抓住并要求解释。

**第二段：执行（L175–189）**

```python title="chapter4/multimodal-agent/campaign.py" linenums="175"
    messages.append(message.model_dump(exclude_none=True))
    for call in calls:
        arguments = json.loads(call.function.arguments or "{}")
        tool_question = arguments.get("question") or question
        result = answer_vision(
            recorder,
            model,
            image,
            tool_question,
            f"tool-vision:{artifact_id}:{call.id}",
        )
        trace["executions"].append(
            {"tool_call_id": call.id, "name": call.function.name, "arguments": arguments, "result": result}
        )
        messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
```

- `message.model_dump(exclude_none=True)`：把 assistant 的工具调用消息**原样**追加回消息数组——这是 OpenAI 工具调用协议的要求（assistant 的 tool_calls 必须与后面的 tool 结果成对出现，`tool_call_id` 要对上）。
- `arguments.get("question") or question`：模型可以自己改写提问（学习版实测它确实这么做了——4 次调用里工具的 question 都比原问题更细，例如 `... Please read the chart labels and data values.`）；模型没给就退回原问题。**这是「工具的参数由模型决定」落到实处的唯一一处**。
- `json.loads(... or "{}")`：容忍空 arguments。
- `purpose=f"tool-vision:{artifact_id}:{call.id}"` 带上厂商给的 tool_call id，**同一次运行内可唯一定位**这次二次调用。
- 执行体是 `answer_vision`——**「多模态模型被封装成工具」在实验版里就是这样一行函数复用**；在 agent.py 里对应的是 `_execute_tool`（L1071–1098）→ `MultimodalTools.analyze_image`（L97–109）。
- 这里是**同步串行**：for 循环里逐个执行。多工具并发是产品版的事，实验版要的是可读的执行轨迹。

**第三段：收尾（L190–199）**

```python title="chapter4/multimodal-agent/campaign.py" linenums="190"
    final = recorder.create(
        purpose=f"tool-final:{artifact_id}",
        model=model,
        seed=SEED,
        temperature=0,
        messages=messages,
        tools=[TOOL],
        tool_choice="none",
    )
    return final.choices[0].message.content or "", trace
```

`tool_choice="none"` 是这一段的全部要点：**工具仍然声明在请求里，但被禁止调用**。效果是模型必须基于「提取文本 + 工具返回的视觉描述」写出最终答案，不能继续链式调用（否则可能反复调工具、永不收敛）。这是「有界 agent 循环」最经济的写法——**用一次强制收尾代替 max_iterations 计数**。

`messages` 此时是完整轨迹：system → user(文本+问题) → assistant(tool_calls) → tool(视觉结果)。收尾调用就是在这条轨迹上续写。

!!! note "三段各自的 purpose 前缀"
    `tool-decision:` / `tool-vision:` / `tool-final:` 三个前缀让证据可以按阶段统计调用次数与耗时。学习版实测：每行工具臂 = 1 次 DeepSeek 决策 + 1 次 qwen-vl 视觉 + 1 次 DeepSeek 收尾，即 `tool-on-demand` 平均延迟 7696ms ≈ 文本臂（1136ms）的 6.8 倍——**「按需」的代价被量化了**。

### 3.10 `exact_correct`（L202–203）：确定性判分

[chapter4/multimodal-agent/campaign.py · L202–L203](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L202-L203)


```python title="chapter4/multimodal-agent/campaign.py" linenums="202"
def exact_correct(answer: str, patterns: list[str]) -> bool:
    return all(re.search(pattern, answer, flags=re.IGNORECASE) for pattern in patterns)
```

一行，`all(...)` = 「全部模式命中才算对」。

- `re.IGNORECASE` 让 `q4` / `Q4` 都算命中；
- `re.search` 而不是 `match`：模式可以出现在答案的任何位置，不要求开头；
- 结果写进每行的 `exact_correct` 字段。`main` 里对三条臂分别 `sum(bool)/len` 得到 `exact_accuracy`（L349）。
- 它**不看**答案的其他部分——多余的解释、错误的推理过程都不影响判分。这是有意的：这一层只问「关键数值在不在」。推理质量交给第二层评审。

### 3.11 `judge_answers`（L206–231）：外部评审的 JSON 契约

[chapter4/multimodal-agent/campaign.py · L206–L231](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L206-L231)


```python title="chapter4/multimodal-agent/campaign.py" linenums="206"
def judge_answers(recorder: CheckpointRecorder, model: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = [
        {"id": row["id"], "question": row["question"], "reference": row["expected"], "answer": row["answer"]}
        for row in rows
    ]
    response = recorder.create(
        purpose="external-answer-judge",
        model=model,
        seed=SEED,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Independently judge chart QA answers. Return JSON {items:[{id,correct,score,reason}]}. "
                    "Score 1 only if every requested quarter/value/difference matches the reference; otherwise 0."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    try:
        return json.loads(response.choices[0].message.content)["items"]
    except json.JSONDecodeError:
        return []
```

四个设计点，每个都值得记住：

1. **12 行一次打包送审**。payload 只带四样：`id`（回填用）、`question`、`reference`（参考答案）、`answer`（待评答案）。评审看不到范式名、看不到延迟、看不到工具轨迹——**评审不知道自己在评哪条臂**，这从源头排除了「知道是原生臂就放宽」的偏袒。
2. **JSON 契约是显式的**：system 里把返回形状写成 `{items:[{id,correct,score,reason}]}`，并配 `response_format={"type": "json_object"}` 双重保证。`reason` 字段让每一分都可以被人复核——学习版实测的 reason 例如 `The answer identifies Q4 but fails to provide the exact revenue value of $180M.`
3. **判分标准是一句话**：`Score 1 only if every requested quarter/value/difference matches the reference`——**全部匹配才给 1，否则 0**。二值判分（而不是 1–5 分档）让 `judge_accuracy` 与 `exact_accuracy` 可以直接对比，两条臂的分数差不会被中间档位糊掉。
4. **失败静默**：`except json.JSONDecodeError: return []`。评审返回畸形 JSON 时返回空列表，主循环 `judged[row["id"]]` 会 `KeyError` 崩——**学习版就踩到了这个形状的坑**（见 4.4）：学习版改成跨厂商两次评审，必须用 `by_id.get(row["id"])` 才不炸。课程原版这里依赖「评审一次给全 12 条」，脆弱但简单。

### 3.12 `tool_version`（L234–236）：证据里的环境指纹

[chapter4/multimodal-agent/campaign.py · L234–L236](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/multimodal-agent/campaign.py#L234-L236)


```python title="chapter4/multimodal-agent/campaign.py" linenums="234"
def tool_version(command: list[str]) -> str:
    proc = subprocess.run(command, text=True, capture_output=True)
    return (proc.stdout or proc.stderr).splitlines()[0]
```

取命令输出的第一行。`tesseract --version` 把版本打进 stdout，`pdftotext -v` / `pdftoppm -v` 打进 stderr——所以是 `(proc.stdout or proc.stderr)`。结果写进证据的 `local_tools`（L375–379）。

**它没有 `check=True` 也没有 try**：所以缺二进制时同样抛 `FileNotFoundError`。本机实测三个命令全部 `FileNotFoundError`——**课程原版在这台机器上无论走 `local_extract` 还是走到证据组装，都会崩**。这不是学习版偷懒改写，是环境差异逼出来的（见 4.5 的诚实说明）。

### 3.13 `main`（L239–397）：编排

**（1）参数与客户端（L240–262）**

```python title="chapter4/multimodal-agent/campaign.py" linenums="240"
    parser = argparse.ArgumentParser(description="Experiment 4-3 live multimodal campaign")
    parser.add_argument("--model", default=os.getenv("ARK_MODEL", "doubao-seed-1-6-250615"))
    parser.add_argument("--judge-model", default=os.getenv("MULTIMODAL_JUDGE_MODEL", "moonshot-v1-8k"))
    args = parser.parse_args()
    ark_key = os.getenv("ARK_API_KEY") or os.getenv("DOUBAO_API_KEY")
    moonshot_key = os.getenv("MOONSHOT_API_KEY")
    if not ark_key or not moonshot_key:
        raise RuntimeError("ARK_API_KEY and MOONSHOT_API_KEY are required")
```

只需两把钥匙：`ark`（视觉作答，**三臂共用同一个模型**）和 `moonshot`（评审）。`--model` 与 `--judge-model` 都可被环境变量覆盖。

**这一点是三范式对比的公平性基础**：native / extract / tool 三条臂用的是**同一个模型、同一份 prompt 纪律、同一个 seed**——差别只在信息如何进入模型。如果三臂各用一个模型，测出来的就是模型差异而不是范式差异。学习版打破了这条（视觉走 qwen-vl-max、文本走 deepseek-flash），因为它只有一个视觉 key 和一个文本 key；这一点定性也要如实记在证据里（见 4.5）。

检查点的命名（L249–262）：`validation/checkpoints/<UTC 时间戳>-ark.json` 与 `...-judge.json` 两个文件，作答与评审分开记——**评审调用数（`len(judge.calls)`）与作答调用数都能单独核对**。

**（2）样例与栅格化（L264–275）**

```python title="chapter4/multimodal-agent/campaign.py" linenums="264"
    chart = PROJECT_DIR / "test_files" / "sample_chart.png"
    pdf = PROJECT_DIR / "test_files" / "sample_report.pdf"
    if not chart.exists() or not pdf.exists():
        subprocess.run([sys.executable, str(PROJECT_DIR / "create_sample.py")], cwd=PROJECT_DIR, check=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        rendered_pdf = Path(temp_dir) / "sample_report_page.png"
        render_pdf(pdf, rendered_pdf)
        artifacts = [
            ("png", chart, chart),
            ("pdf", pdf, rendered_pdf),
        ]
```

样例缺失时自动调 `create_sample.py`（用 `sys.executable`，保证同解释器）。渲染页放在 `TemporaryDirectory` 里——一次性工件，跑完即删；但它的 **sha256 仍被算进记录**（L287），所以证据里能证明「当时看的确实是那份渲染页」。

`artifacts` 就是 12 行矩阵的两个维度之一：工件（png / pdf）× 问题（2）= 4，再乘 3 条臂 = 12。注意 png 那一行的 `original` 与 `visual` 是**同一个文件**（原生就是图），pdf 那行不是。

**（3）12 行矩阵（L276–338）**

三层循环的结构：

```text
for kind, original, visual in artifacts:              # 2 个工件
    extracted, extraction_receipt = local_extract(...)  # 每个工件提取一次
    for spec in QUESTIONS:                              # 2 个问题
        native  → rows.append({paradigm: "native-multimodal", ...})
        text    → rows.append({paradigm: "extract-to-text",  ...})
        tool    → rows.append({paradigm: "tool-on-demand",   ...})
```

三点值得单看：

- **提取在里层循环之外**（L279）：同一工件的三臂共用一份 `extracted`，也共用同一份 `extraction_receipt`；
- **延迟的算法有意不公平地诚实**：`extract-to-text` 与 `tool-on-demand` 的行延迟都写成 `extraction_receipt["latency_ms"] + (time.perf_counter() - started) * 1000`（L320 / L334）——**把本地提取时间算进这两条臂**，native 臂则只有 API 时间。因为「提取为文本」的真实成本本来就包含提取这一步；不算进去，对比就虚高了。
- **`exact_correct` 在构造行时就算好**（L307 / L321 / L335），评审结果稍后再回填。两套判分互不依赖——评审挂了，exact 那一栏照样有效。

**（4）评审与聚合（L340–352）**

```python title="chapter4/multimodal-agent/campaign.py" linenums="340"
        judgements = judge_answers(judge, args.judge_model, rows)
        judged = {item["id"]: item for item in judgements}
        for row in rows:
            row["external_judge"] = judged[row["id"]]
        summary: dict[str, Any] = {}
        for paradigm in ("native-multimodal", "extract-to-text", "tool-on-demand"):
            selected = [row for row in rows if row["paradigm"] == paradigm]
            summary[paradigm] = {
                "cases": len(selected),
                "exact_accuracy": sum(row["exact_correct"] for row in selected) / len(selected),
                "judge_accuracy": sum(bool(row["external_judge"]["correct"]) for row in selected) / len(selected),
                "mean_latency_ms": sum(row["latency_ms"] for row in selected) / len(selected),
            }
```

`judged[row["id"]]` 是**无保护的键访问**——评审少返回一条就 `KeyError`（3.11 第 4 点）。聚合的三行 `sum(bool)/len` 是 Python 里数 True 的惯用法。每个范式四个数：`cases` / `exact_accuracy` / `judge_accuracy` / `mean_latency_ms`——**准确率与成本并列**，这是选型实验该有的输出形状。

**（5）acceptance 八条（L356–368）**

这是全文件最该逐条读的一段：它不是一个「测试」，是**作者对「这次实验算不算数」的自我约法**。

| # | 键 | 校验什么 | 为什么必要 |
| --- | --- | --- | --- |
| 1 | `same_two_questions_all_paradigms_and_artifacts` | `len(rows) == 12` | 行数不对，说明循环漏了，任何聚合都无意义 |
| 2 | `png_and_pdf_used` | `{row["artifact"]} == {"png","pdf"}` | 防止只跑了 PNG 却宣称两个工件 |
| 3 | **`chart_answers_absent_from_pdf_body_text`** | PDF 正文里**不含** `$180/180m/$95/95m/$85/85m` | **实验成立的前提**，见下 |
| 4 | `real_native_vision_calls` | purpose 以 `native:` 开头的调用**恰好 4 次** | 防止 native 臂被缓存/模拟糊过去；4 = 2 工件 × 2 问题 |
| 5 | `tool_selected_on_demand` | 每条工具臂 `tool_selected == True` | 工具臂必须真的用了工具，否则它只是文本臂的复制 |
| 6 | `real_tool_vision_calls` | `tool-vision:` 调用 **≥ 4** | 工具臂真的触发了视觉，而不是只做了决策 |
| 7 | `external_moonshot_judge` | `len(judge.calls) == 1` 且评审条数 == 行数 | 评审真的调了一次外部模型，且覆盖全部 12 行 |
| 8 | `all_calls_checkpointed` | 两个检查点文件都存在 | 「崩了也有据可查」的前提 |

**第 3 条为什么是实验成立的前提**：整条对照链的因果是「文本臂拿不到数值 → 所以分数低」。这要求**数值确实只存在于图上**。如果 PDF 的正文文字层里写了 `Q4 营收 $180M`，那么 `pdftotext` 就能拿到数值，文本臂会答对——那测出来的就不是「提取丢信息」，而是「模型不会读文本」。所以必须用一个**可执行的检查**去证明「正文里没有这些数值」，而不是靠作者声明。学习版实测用 PyMuPDF 取出的 359 个字符里，六个模式串全部 `False`（见 4.3）。

注意这一条用的是**六个小写模式串**（`"$180", "180m", "$95", "95m", "$85", "85m"`）而不是 `QUESTIONS` 里的正则——它是粗筛（宁可误报也不漏报），把正文和数值的耦合直接钉死。

`status` 由它派生（L370）：`"passed" if all(acceptance.values()) else "failed"`——**任何一条不满足，整场实验作废**。返回码同理（L397），所以这个脚本可以直接进 CI。

**（6）证据落盘（L369–396）**

```python title="chapter4/multimodal-agent/campaign.py" linenums="387"
        manifest = write_campaign_evidence(
            PROJECT_DIR,
            "4-3",
            evidence,
            receipts=ark.calls + judge.calls,
            input_paths=[__file__, PROJECT_DIR / "create_sample.py", chart, pdf],
        )
```

`write_campaign_evidence`（[experiment_utils.py · L135](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/experiment_utils.py#L135)）与 task3 共用：写 `evidence.json` → `receipts.json` → `manifest.json`（三者哈希 + 输入文件哈希）→ **最后**写 `latest.json`。写入顺序就是语义：半途崩溃的 run 不会占据「最新」位。

`input_paths` 里放了 `__file__`（campaign.py 自己）+ `create_sample.py` + 两个样例——**输入的哈希进 manifest，输出的回执也进 manifest**，任何人拿到证据包都能验证「用这份代码、这份样例、跑出了这些数」。

### 3.14 agent.py 侧：范式怎么落到产品代码

campaign.py 是**实验脚本**（一个矩阵、一次实拍）；agent.py 是**产品实现**（可交互、可切换、多厂商）。三范式在 agent.py 里的落点：

**（1）范式的分派只有两条路（L411–423）**

```python title="chapter4/multimodal-agent/agent.py" linenums="411"
    async def process_multimodal_content(
        self,
        content: MultimodalContent,
        query: Optional[str] = None
    ) -> str:
        """Process multimodal content based on extraction mode"""

        if self.extraction_mode == ExtractionMode.NATIVE:
            return await self._process_native(content, query)
        elif self.extraction_mode == ExtractionMode.EXTRACT_TO_TEXT:
            return await self._extract_to_text(content, query)
        else:
            raise ValueError(f"Unknown extraction mode: {self.extraction_mode}")
```

`config.ExtractionMode`（config.py L29–32）只有 `NATIVE` / `EXTRACT_TO_TEXT` 两个枚举值，分派器就是 if/elif。**第三条范式不在这里**——它通过 `enable_tools` 这个**正交开关**实现（见下）。

**（2）原生臂：`_process_native`（L425–444）再按 provider 分派**

```python title="chapter4/multimodal-agent/agent.py" linenums="425"
    async def _process_native(self, content: MultimodalContent, query: Optional[str]) -> str:
        """Process using native multimodal capabilities"""
        model_config = self.config.get_model_config(self.current_model)
        
        if not model_config.supports_native_multimodal:
            raise ValueError(f"Model {self.current_model} doesn't support native multimodality")

        # Universal OpenRouter fallback: ...
        if self.config.use_openrouter(model_config.provider):
            return await self._process_native_openrouter(model_config, content, query)

        if model_config.provider == Provider.GEMINI:
            return await self._process_native_gemini(content, query)
        elif model_config.provider == Provider.OPENAI:
            return await self._process_native_openai(content, query)
        elif model_config.provider == Provider.DOUBAO:
            return await self._process_native_doubao(content, query)
        else:
            raise ValueError(f"Unknown provider: {model_config.provider}")
```

分派之前先做**能力检查**（`supports_native_multimodal`）——纯文本模型走原生臂直接报错，而不是发出一个注定失败的请求。这就是「产品代码」与「实验脚本」的分工：实验要的是最小可读路径，产品要的是能力协商。

四个 `_process_native_*`（L446–598）是同一件事的四份实现，三处共性值得注意：

- 图像一律走 `{"type": "image_url", "image_url": {"url": f"data:{content.mime_type};base64,{content.get_base64()}"}}`（L458–463、L543–548、L578–584）——与 campaign.py 的 `data_url` 是同一个协议；
- **非图像内容被降级**：`else` 分支调用 `_extract_single_content` 把 PDF/音频转成文本再塞进 `text` 段（L464–466、L549–552、L585–588）。也就是说「原生多模态」在 OpenAI / Doubao / OpenRouter 上**只对图像成立**，PDF 和音频会自动退化成「提取为文本」。这是产品代码里最诚实的一行妥协，也是为什么本章的 PDF 工件必须先栅格化；
- Gemini 是唯一真正原生吃 PDF 和音频的路径（`types.Part.from_bytes`，L494–497、L927–930）。

**（3）提取臂：`_extract_to_text`（L600–609）→ `_extract_single_content`（L611–620）**

```python title="chapter4/multimodal-agent/agent.py" linenums="600"
    async def _extract_to_text(self, content: MultimodalContent, query: Optional[str]) -> str:
        """Extract multimodal content to text first"""
        extracted_text = await self._extract_single_content(content)
        content.extracted_text = extracted_text
        
        # Now process the query with extracted text
        if query:
            return await self._answer_with_context(extracted_text, query)
        else:
            return extracted_text

    async def _extract_single_content(self, content: MultimodalContent) -> str:
        """Extract a single piece of content to text"""
        if content.type == "pdf":
            return await self._extract_pdf_to_text(content)
        elif content.type == "image":
            return await self._extract_image_to_text(content)
        elif content.type == "audio":
            return await self._extract_audio_to_text(content)
        else:
            raise ValueError(f"Unknown content type: {content.type}")
```

两段式：**提取**（`_extract_single_content`）与**作答**（`_answer_with_context` L780–841）被拆成两个函数，所以「提取文本」既可以被用作最终答案（`query` 为空时直接返回），也可以被当作上下文（`_answer_with_context` 里的 `Context:\n{context}\n\nQuestion: {query}` 拼法，L784）。

与 campaign.py 的 `local_extract` 对比，这里暴露了**一个重要的分类差异**：

- campaign.py 的「提取」= **本地命令行工具**（tesseract / pdftotext），与模型无关，可离线、可审计、可复现；
- agent.py 的「提取」= **又一次模型调用**：

```python title="chapter4/multimodal-agent/agent.py" linenums="676"
    async def _extract_image_to_text(self, content: MultimodalContent) -> str:
        """Extract image to text description"""
        # 图像转文本：gpt-5.6-luna（优先 OpenRouter，直连 5.6 需组织实名）/ Doubao / OpenRouter 兜底
        if self.config.openrouter_api_key:
            client = AsyncOpenAI(
                api_key=self.config.openrouter_api_key,
                base_url=self.config.openrouter_base_url
            )
            model = _openrouter_model_id("gpt-5.6-luna")
        ...
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Describe this image in detail, including all text, objects, and contextual information."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{content.mime_type};base64,{content.get_base64()}"
                    }
                }
            ]
        }]
        
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3
        )
```

注意 `temperature=0.3`（不是 0.7 也不是 0）——描述任务允许一点多样性；也注意这段的 prompt 是「Describe this image in detail」——**它仍然是一次视觉调用**。所以 agent.py 的「提取为文本」在图像上是「用视觉模型描述成文字」，而 campaign.py 的是「用 OCR 把像素转成字符」。同一个名字，两种实现，实验里必须说清楚用的是哪一种——**create_sample.py 的注释（L9–13）正是为此写的**：「提取为文本模式若用通用描述器转写图像，往往丢失精确数值与空间关系」。本页 4.2 节的 12 行矩阵实测走的是 campaign.py 的 OCR 路线（且本机无 OCR）。

**（4）工具臂：`set_multimodal_tools_enabled`（L330–405）+ `_execute_tool`（L1071–1098）+ `MultimodalTools`（L91–301）**

这三个东西合起来才是 agent.py 版的第三范式。

`set_multimodal_tools_enabled` 里写出三个工具 schema：`analyze_image` / `analyze_audio` / `analyze_pdf`（L341–405），每个都有 `*_path` + `query` 两个参数。与 campaign.py 的单个 `inspect_visual` 相比：产品版工具集更大、参数更多（模型自己指定文件），并且 `MultimodalAgent.__init__` 的 `enable_tools` 默认是 `False`（L310 `enable_multimodal_tools = False`，注意**参数被忽略**：L315 硬写 `False`，真正生效的是 L328 的 `set_multimodal_tools_enabled(enable_tools)`）——这是个容易看漏的细节，读的时候以 L328 为准。

`_execute_tool`（L1071–1098）是**工具名 → 实现的调度器**：

```python title="chapter4/multimodal-agent/agent.py" linenums="1071"
    async def _execute_tool(self, tool_call: Dict[str, Any]) -> str:
        """Execute a tool call"""
        function_name = tool_call["function"]["name"]
        try:
            arguments = json.loads(tool_call["function"]["arguments"])
        except json.JSONDecodeError:
            return f"Error: invalid JSON arguments for tool '{function_name}'"
        
        if function_name == "analyze_image":
            image_path = arguments.get("image_path")
            query = arguments.get("query")
            if not image_path or not query:
                return "Error: analyze_image requires 'image_path' and 'query' arguments"
            return await self.tools.analyze_image(image_path, query)
```

三个健壮性细节，与 campaign.py 的对应处正好可以对照学：

| 失败模式 | campaign.py | agent.py |
| --- | --- | --- |
| 工具参数 JSON 畸形 | `json.loads(... or "{}")` → 参数全缺 → 退回原问题（L177–178） | 捕获并**返回错误字符串给模型**（L1076–1077） |
| 参数缺字段 | 无此情况（只有一个可选参数） | 返回 `Error: ... requires ...`，让模型自我纠正（L1083） |
| 未知工具名 | 无此情况（只有一个工具） | 返回 `Unknown tool: {name}`（L1098） |

**产品版把错误当作可对话的信息回灌给模型**，实验版则把「能出的错」提前消灭（工具只有一个、路径闭包注入）。这是「有界实验」对「开放产品」的典型取舍。

最后是 `MultimodalTools.analyze_image`（L97–109）——**「多模态模型被封装成工具」真正落地的那几行**：

```python title="chapter4/multimodal-agent/agent.py" linenums="97"
    async def analyze_image(self, image_path: str, query: str) -> str:
        """Analyze an image with a specific query"""
        content = MultimodalContent(
            type="image",
            path=image_path,
            mime_type=mimetypes.guess_type(image_path)[0] or "image/jpeg"
        )
        
        # Use GPT-5 or Doubao for image analysis
        if self.agent.config.get_model_config(self.agent.current_model).provider == Provider.DOUBAO:
            return await self._analyze_with_doubao(content, query)
        else:
            return await self._analyze_with_openai(content, query)
```

签名就是答案：**输入是一个多模态文件 + 一个自然语言问题，返回一段自然语言描述**。这个「图进、文出」的形状正是它能当 function tool 的原因——工具协议（`tool_call` → 字符串结果 → `role: "tool"` 消息）只传文本。三个 `_analyze_with_*` 实现（L133–193 的 OpenAI / Doubao，L195–300 的 Gemini 音频 / PDF）全部遵守这个形状。

**（5）工具调用的循环（L993–1069）**——归并区里唯一值得点名的部分

`_stream_openai_response` 里有一个「工具调用 → 执行 → 递归」的闭环（L1041–1066）：流式收完 tool_calls 后逐个 `_execute_tool`，把结果作为 `role:"tool"` 消息追加，然后**递归调用自己**拿最终回复。对比 campaign.py 的 `answer_with_tool`：产品版是**无界递归**（模型可以一直调工具，直到它自己不再调），实验版用 `tool_choice="none"` 强制收尾一次。**做实验时选有界版本**——不然 12 行的延迟不可控、证据不可比。

### 3.15 create_sample.py：让实验可测的样例设计

**`create_chart`（L31–58）**

```python title="chapter4/multimodal-agent/create_sample.py" linenums="38"
    # 把精确数值标注在柱子顶端——这些信息只存在于图像里
    for bar, value in zip(bars, REVENUE):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 3,
            f"${value}M",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )
```

数据在 L27–28：`QUARTERS = ["Q1","Q2","Q3","Q4"]`，`REVENUE = [120, 150, 95, 180]`（$M）。`ax.text` 把 `$120M` 等标签画在柱顶——**这是「数值只存在于图像里」的实现**：它们是 matplotlib 渲染出的像素，不是文本对象。

`fontsize=11, fontweight="bold"` 是对 OCR 与视觉模型都友好的选择（变大、变粗）；`ha="center", va="bottom"` + `+3` 的偏移让标签不与柱顶重叠。`dpi=150`（L35）与后面渲染 PDF 用的 180dpi 不同——**同一张图在 PNG 工件里是 150dpi 原图，在 PDF 工件里是 180dpi 的页面渲染**，两者的视觉臂输入严格说不是同一张位图，但承载的信息相同。

**`create_report_pdf`（L61–98）**

```python title="chapter4/multimodal-agent/create_sample.py" linenums="80"
    # 正文刻意只给出定性描述，不逐一写出各季度精确数值——数值只在图里
    body_text = (
        "This internal report summarizes Acme Corp's revenue performance in 2024. "
        "Overall the year showed healthy growth, with a mid-year dip followed by a "
        "strong recovery in the final quarter. The chart below breaks down revenue "
        "by quarter; management attributes the fourth-quarter surge to the launch of "
        "the new enterprise product line."
    )
```

这段正文是**实验设计的关键文本**，值得逐句看：

- `a mid-year dip` / `a strong recovery in the final quarter` / `the fourth-quarter surge`——**全是定性词**。它故意让文本臂能「猜到 Q4 最强、Q3 是低谷」，但**拿不到 180 / 95 / 85 任何一个数**。这就是为什么学习版实测里 `pdf:extract:highest` 的答案是 `Based on the extracted text, the fourth quarter had the strongest performance/surge, but the exact revenue value is not provided`——模型推断对了方向，但缺数值，按 `required_patterns` 仍是 0 分。**这个「半对」正是实验最有说服力的一格**：它证明失分不是模型笨，而是提取层丢了信息。
- `RLImage(str(chart_path), width=14*cm, height=9.3*cm)`（L95）：把 PNG 作为**栅格图**嵌入 PDF。所以在 PDF 里，图表的标签依然是像素——`pdftotext` 永远读不到它们。**如果这里改成矢量图或文字表格，整个实验就塌了**。
- `reportlab` 缺失时打提示并 `return None`（L73–75），不抛异常——离线样例生成允许降级。

### 3.16 config.py：只有两种模式

```python title="chapter4/multimodal-agent/config.py" linenums="29"
class ExtractionMode(Enum):
    """Modes for multimodal content extraction"""
    NATIVE = "native"  # Use model's native multimodal capabilities
    EXTRACT_TO_TEXT = "extract_to_text"  # Convert multimodal to text first
```

两行枚举值，字面说明了 agent.py 的范式边界。`Provider`（L35–39）也只有 GEMINI / OPENAI / DOUBAO 三个（没有 DashScope / DeepSeek——所以学习版的 `RoutingRecorder` 必须**绕过 Config**，自建两个 OpenAI 客户端）。

`Config.__init__` 里三个 key 读取都带别名（L67–69）：`GOOGLE_API_KEY or GEMINI_API_KEY`、`DOUBAO_API_KEY or ARK_API_KEY`——和 campaign.py 的 `ARK_API_KEY or DOUBAO_API_KEY`（L244）是同一种兼容写法。

---

### 3.17 学习版注入：改了哪几处，为什么

学习版脚本 `learning/task4/run_4_3_multimodal.py` 的 docstring 把改动列了四类。逐类说明：

#### 3.17.1 `RoutingRecorder`（学习版 L75–133）：按请求内容路由

```python title="learning/task4/run_4_3_multimodal.py" linenums="89"
    @staticmethod
    def _has_image(messages: list[dict[str, Any]]) -> bool:
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                if any(part.get("type") == "image_url" for part in content
                       if isinstance(part, dict)):
                    return True
        return False

    def create(self, *, purpose: str, **request: Any) -> Any:
        is_vision = self._has_image(request.get("messages", []))
        client = self.vision_client if is_vision else self.text_client
        provider = "dashscope" if is_vision else "deepseek"
        endpoint = VISION_ENDPOINT if is_vision else TEXT_ENDPOINT
        request["model"] = VISION_MODEL if is_vision else TEXT_MODEL
```

**为什么需要它**：课程的 `CheckpointRecorder` 包**一个**客户端，三臂共用一个模型（豆包）。学习版只有两个 key（DashScope + DeepSeek），必须在一个 recorder 里同时满足两类请求。

**路由规则**：请求消息里**有没有 `image_url` 段** → 有则 `qwen-vl-max` @ DashScope，无则 `deepseek-flash` @ DeepSeek。而且它**覆盖调用方传入的 `model` 字段**（`request["model"] = ...`）——因为 campaign 的 `answer_text` / `answer_vision` 都会传一个 `model`（学习版传进去的是 `TEXT_MODEL` 或 `VISION_MODEL`，但 `answer_with_tool` 内部的 decision / final 与二次 vision 调用会传同一个 model 名，靠路由纠正）。**这是这套复用能成立的关键一行**。

**它复刻了 CheckpointRecorder 的两个语义**：失败也落盘（L108–116，把 `error` 记进 calls 再 `raise`）；每次调用后立刻写盘（`_checkpoint`，L130–133）。同时多记了三样课程没有的东西：`provider`、`endpoint`（学习版跨厂商，必须记）、`response_id`。

#### 3.17.2 `local_extract`（学习版 L136–158）：PyMuPDF + 无 OCR 的如实记账

```python title="learning/task4/run_4_3_multimodal.py" linenums="140"
    if kind == "pdf":
        with fitz.open(original) as document:
            text = "\n".join(page.get_text() for page in document)
        method = "pymupdf-page-text"
        command: list[str] = []
    else:
        # 本机没有 tesseract：PNG 里只有栅格化的图形与文字，没有可提取的文本层。
        text = ""
        method = "unavailable-no-ocr"
        command = []
    return text.strip(), {
        "method": method,
        "command": command,
        "reason": "" if method == "pymupdf-page-text"
                  else "tesseract not installed and PIL text layer absent",
        "chars": len(text.strip()),
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }
```

- **PDF 路径**：PyMuPDF 的 `page.get_text()` 代替 `pdftotext -layout`。两者都是「读 PDF 文本层」，结果等价（学习版实测 359 字符；正文与课程一致）。差别是 PyMuPDF 是 Python 库、无需外部二进制、返回的换行与 pdftotext -layout 略有不同（不影响本实验，因为判分只关心图上的数值在不在）。
- **PNG 路径**：**直接返回空字符串**，并在收据里写明 `method="unavailable-no-ocr"`、`reason="tesseract not installed and PIL text layer absent"`、`chars=0`。这是本页最该表扬的一处工程判断：**没有 OCR 就诚实记零，而不是偷偷改走视觉调用**。如果这里「聪明地」用 qwen-vl 去描述这张图，文本臂就变成了视觉臂，三范式对比立刻失效（而且会伪装成「文本臂也能拿到数值」）。
- 收据形状从课程的 `{command, stderr, latency_ms}` 变成 `{method, command, reason, chars, latency_ms}`——**结构改了但语义变强了**：`method` 是字符串标签（验收第 9 条 `local_extraction_receipts_recorded` 检查的就是「每个工件都有 method」），`chars` 让人一眼看出 PNG 是 0、PDF 是 359。

#### 3.17.3 `render_pdf`（学习版 L161–168）：PyMuPDF 顶替 pdftoppm

```python title="learning/task4/run_4_3_multimodal.py" linenums="161"
def render_pdf(pdf: Path, output: Path) -> None:
    """课程用 pdftoppm；本机无 poppler，改用 PyMuPDF 以同样的 180 dpi 渲染首页。"""
    import fitz

    with fitz.open(pdf) as document:
        page = document.load_page(0)
        pixmap = page.get_pixmap(dpi=180)
        pixmap.save(output)
```

`load_page(0)` + `get_pixmap(dpi=180)` + `save()` = `pdftoppm -png -singlefile -r 180` 的等价物：**只渲染第一页、180 dpi、PNG 输出**。dpi 保持一致是有意的——同一份代码在两种环境下产出视觉上可比的输入。**这一步不能省**：省略它，PDF 工件的视觉臂就没有图可看，两条视觉相关的臂都会失败。

#### 3.17.4 主循环（学习版 L179–267）：只换了 recorder 与输出目录

矩阵结构原样保留（L202–239 与课程 L278–338 逐行对应）：`artifacts` 二元组、内层 `course.QUESTIONS` 循环、三臂顺序、延迟算法（提取时间计入文本臂与工具臂）、`course.exact_correct` 调用。所有 `answer_*` 都直接 import 课程函数调用——**`campaign.py` 是 import 进去的，不是拷贝的**，所以课程函数一旦被改动，学习版的证据会立刻失效（`evidence.json` 里记了 `source_hashes`，L360–368）。

新增的是 `answer_provider` 字段（每行标明产出厂商，L220 / L227 / L235）——跨厂商实验中这是必需品。

启动时先跑 `create_sample.py` 生成样例（学习版 L186–187），输出目录是 `learning/task4/runs/4-3_multimodal/<UTC 时间戳>/`（L57–58），且 `mkdir(exist_ok=False)`（L182）——**目录已存在直接报错，绝不覆盖上一次的证据**。

#### 3.17.5 跨厂商评审（学习版 L171–176、L243–256）

```python title="learning/task4/run_4_3_multimodal.py" linenums="171"
def judging_plan(rows: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """哪一臂的行交给哪个评审：评审必须与被评答案的产出厂商不同。"""
    vision_rows = [row for row in rows if row["paradigm"] == "native-multimodal"]
    text_rows = [row for row in rows if row["paradigm"] != "native-multimodal"]
    return [("vision-rows-judged-by-deepseek", vision_rows),
            ("text-rows-judged-by-dashscope", text_rows)]
```

规则一句话：**评审必须与被评答案的产出厂商不同**。

- 视觉产出的行（native，4 行）→ DeepSeek `deepseek-flash` 评；
- 文本产出的行（extract + tool，8 行）→ DashScope `qwen3.7-plus` 评。

注意工具臂的行算「文本产出」——它的决策与收尾都是 DeepSeek 写的，视觉只贡献了工具返回结果，**判分口径按最终答案的作者算**。这个分类是可以辩论的（工具臂确实用了 qwen-vl），但脚本把它写进 `judging_plan` 的注释里就能被复核，比含糊着不分好。

评审调用被**拆成两次**（每组一次 `course.judge_answers`），这是学习版对 3.11 第 4 点脆弱性的直接修补：每组只送 4 / 8 行，且用 `by_id.get(row["id"])` 回填（L255）——某一行缺失时记 `None` 而不是 `KeyError`。代价是课程验收第 7 条 `external_moonshot_judge` 要求 `len(judge.calls) == 1` 不再成立，所以学习版把这条改写成 `cross_vendor_judging`（L285–291）：检查 4 行视觉行的 `judge_model` 全是 DeepSeek、8 行文本行的全是 qwen、且 `len(judge_calls) == 2`。

#### 3.17.6 验收九条（学习版 L274–295）

课程八条里保留五条（第 1、2、3、5、8），改名强化两条（第 4、6 条加上 `_on_dashscope` 并检查 `provider`/`model` 字段），重写一条（第 7 条 → `cross_vendor_judging`），新增一条：

| 学习版第 9 条 | 检查什么 | 为什么加 |
| --- | --- | --- |
| `local_extraction_receipts_recorded` | 每个工件的 `extraction["method"]` 都非空 | PNG 提取为空是**预期行为**，但必须留下「为什么空」的记录；没有这条，空的提取结果无法与「脚本 bug 导致没提取」区分 |

八条 → 九条，`acceptance 9/9` 全部为真（见下节）。

---

## 4. 完整执行回放（学习版一次真实运行：20260921T111923Z）

### 4.1 总账

```text
providers:
  vision / native 与 tool-vision  : dashscope qwen-vl-max          @ https://dashscope.aliyuncs.com/compatible-mode/v1
  text   / extract + 工具决策收尾 : deepseek  deepseek-flash        @ https://api.deepseek.com
  judge 视觉产出行                : deepseek  deepseek-flash        （跨厂商）
  judge 文本产出行                : dashscope qwen3.7-plus          （跨厂商）

API 调用：20 次（calls-routed.json）+ 2 次评审（ChatRecorder）= 22 次
  4 native:  / 4 extract-text: / 4 tool-decision: / 4 tool-vision: / 4 tool-final:
```

三范式结果（实测数字，与 `summary.json` 一致）：

| 范式 | cases | exact_accuracy | judge_accuracy | mean_latency_ms |
| --- | --- | --- | --- | --- |
| native-multimodal | 4 | **1.00** | **1.00** | 3519 |
| extract-to-text | 4 | **0.00** | **0.00** | 1136 |
| tool-on-demand | 4 | **1.00** | **1.00** | 7696 |

`acceptance: 9/9`，`status: passed`，`completed: true`，凭据扫描 `clean`（0 处泄露）。

三条臂的准确率与成本关系一句话：**native 是又快又准的上限；extract 是最便宜但拿不到图；tool 用 6.8 倍延迟买到与 native 相同的准确率**（7696 / 1136 ≈ 6.8；对比 native 是 2.2 倍）。

### 4.2 每一条臂到底发生了什么（按 12 行矩阵逐格）

| 行 | exact | 答案要点 | 备注 |
| --- | --- | --- | --- |
| png:native:highest | 1 | `Q4 ... $180 million`，并列出 Q2 $150M / Q1 $120M / Q3 $95M | 一屏读全 |
| png:native:lowest_gap | 1 | `Q3 ... $95M`，`$180M - $95M = $85M` | 减法也做对 |
| pdf:native:highest | 1 | 与 png:native:highest 文本近乎相同 | 同一份渲染页 |
| pdf:native:lowest_gap | 1 | `Q3 $95M`，超出 `$85M` | |
| png:extract:highest | 0 | `The extracted text does not include any revenue data or quarters, so the answer is unavailable.` | 提取为空 → **按 system prompt 弃权** |
| png:extract:lowest_gap | 0 | `The extracted text is unavailable, so I cannot determine...` | 同上 |
| pdf:extract:highest | 0 | `...the fourth quarter had the strongest performance/surge, but the exact revenue value is not provided` | **推断对方向、缺数值**——最有说服力的一格 |
| pdf:extract:lowest_gap | 0 | `It only states that there was a "mid-year dip" and a "strong recovery in the final quarter"...` | 引用正文原词，证明它只看到定性描述 |
| png:tool:highest | 1 | `Q4 ... $180 million` | 工具被调用（1 次执行） |
| png:tool:lowest_gap | 1 | `Q3 $95M`，`$180M − $95M = $85M` | 工具被调用 |
| pdf:tool:highest | 1 | `Q4 ... $180M` | 工具被调用 |
| pdf:tool:lowest_gap | 1 | `Q3 $95M`，超出 `$85M`，并补一句「正文的 mid-year dip 对应图里 Q3 的 $95M 低谷」 | **文本与视觉被合并** |

**`tool_selected_on_demand` 4/4 全为 True**。这是可预期的：这两个问题问的都是精确数值，而提取文本里根本没有数值——决策模型每次都正确地判断出「文本没建立精确数值」，于是调用工具。工具的 `arguments.question` 每次都被模型改写得更细（例如 `... Please read the chart labels and data values.`），说明「让模型自己写工具参数」这一设计确实被用上了。

值得注意的是 **pdf 那一侧的工具臂也全都调用了工具**——尽管 PDF 的提取文本有 359 个字符（包含「第四季度强劲复苏」这样的线索）。模型没有停在定性推断上，而是去把精确值取回来。**这是工具臂能拿满分、文本臂拿零分的分界线**。

### 4.3 实验前提的实测核验

`chart_answers_absent_from_pdf_body_text` = True。独立复核（`fitz` 重新提取，不依赖脚本）：PDF 正文 360 字符（脚本 `.strip()` 后 359），内容为：

```text
Acme Corp 2024 Revenue Report
This internal report summarizes Acme Corp's revenue performance in 2024. Overall the year
showed healthy growth, with a mid-year dip followed by a strong recovery in the final quarter. The
chart below breaks down revenue by quarter; management attributes the fourth-quarter surge to the
launch of the new enterprise product line.
```

逐个模式串检查：`$180` / `180m` / `$95` / `95m` / `$85` / `85m` **全部不在其中**。所以「提取为文本拿不到图上数值」在本机被实测证实，不是假设。

### 4.4 评审

两次评审调用，各自把组内全部行判完：

```text
vision-rows-judged-by-deepseek : model=deepseek-flash  rows=4  returned=4
text-rows-judged-by-dashscope  : model=qwen3.7-plus    rows=8  returned=8
```

评审结果与 `exact_correct` **完全一致**（12/12 行同判）。这是有意义的：两层判分（确定性的正则 + 语义的外部模型）独立运行却给出相同结论，说明 `extract-to-text` 的 0 分不是正则太严导致的假阴性——外部评审也认为「说数据不可用」不算答对。学习版实测的 reason 例如：

- 视觉行：`The answer correctly identifies Q3 as lowest at $95M and states Q4 exceeded it by $85M, matching all requested values.`
- 文本行（pdf:highest）：`The answer identifies Q4 but fails to provide the exact revenue value of $180M.`

**注意评审是被跨厂商分开的**：视觉行的对错由 DeepSeek 判定，文本行的对错由 qwen 判定——避免「谁生成谁评分」。

### 4.5 诚实说明：本机环境使对比变弱的地方

三点必须写清楚，否则读者会高估这份证据：

1. **PNG 工件的文本臂是空提取，不是「提取失败的模式」**。本机无 tesseract（实测 `FileNotFoundError`），所以 `png:extract:*` 两行测的是「完全没有提取物时文本臂会怎样」（答案：正确地弃权），而不是「OCR 提取有损时会怎样」。课程原版在装有 tesseract 的机器上，`--psm 6` 对柱顶的 `$180M` 这类标签**有可能读出一部分**（推断，本机无法验证）；若如此，课程原版的 PNG 文本臂会比本页这份证据强。**本页的 extract-to-text 0.00 分因此主要反映 PDF 那一侧（真实的有损提取），PNG 那一侧是环境缺口的产物**。
2. **缺口是环境造成的，不是脚本选择的结果**——`tesseract` / `pdftotext` / `pdftoppm` 在本机均不存在（三者实测 `FileNotFoundError`）。课程原版脚本在这台机器上会在 `local_extract`（L91 `check=True`）与 `tool_version`（L235 无保护）两处直接崩，所以本页的课程原版数字只能是**推断**，不能与学习版数字并列称「对比」。
3. **本机视觉与文本不是同一个模型**。课程的公平性基础是「三臂共用一个模型」，学习版被迫用 qwen-vl-max（视觉）+ deepseek-flash（文本），所以「extract-to-text 比 native 差」里含有**模型差异**的成分，不能全部归因于范式。真正干净的归因只能看**同一模型内部**的对照：pdf 工件上 native（qwen-vl 直接看图）与 tool（deepseek 决策 + qwen-vl 工具）都拿满分，而 extract（deepseek 读同一份被截断的文本）拿零分——**这三条臂的差别里模型差异被压到最小**，范式差异才是主因。

---

## 5. 动手验证

以下三条命令均为本机可跑（第 3 条需 API Key）。前两条完全离线。

**（1）生成样例，并亲眼确认「数值只在图里」**

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-agent-book/chapter4/multimodal-agent
python create_sample.py --output-dir /tmp/s3
/Users/tal/Documents/Codex/learning-projects/ai-agent-book/.venv/bin/python -c "
import fitz
with fitz.open('/tmp/s3/sample_report.pdf') as d:
    t = '\n'.join(p.get_text() for p in d)
print('CHARS', len(t)); print(t)
for v in ('\$180','180M','\$95','95M','\$85','85M'):
    print(v, 'in text:', v.lower() in t.lower())
"
```

预期现象：打印出 360 字符的正文（标题 + 那段定性描述），**六个模式串全部 `False`**；同时 `/tmp/s3/sample_chart.png` 生成（打开它能看到柱顶的 `$120M/$150M/$95M/$180M`）。这一步就是验收第 3 条的手工版——**如果哪个串变成 True，整个实验的前提就没了**。

**（2）直接调用 `campaign.data_url` 观察 base64 前缀**

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-agent-book/chapter4/multimodal-agent
/Users/tal/Documents/Codex/learning-projects/ai-agent-book/.venv/bin/python -c "
import sys; sys.path.insert(0, '.'); sys.path.insert(0, '../chapter3')
from pathlib import Path
import campaign
print('TOOL name:', campaign.TOOL['function']['name'])
print('patterns:', campaign.QUESTIONS[1]['required_patterns'])
u = campaign.data_url(Path('/tmp/s3/sample_chart.png'))
print('prefix:', u[:60])
print('len   :', len(u))
print('is data url:', u.startswith('data:image/png;base64,'))
"
```

预期现象：`prefix` 为 `data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA4QAAAJYCAYAAA`（**`iVBORw0KGgo` 是 PNG 魔数的 base64 形态**，看到它就说明 MIME 与内容对上了），`len` 约 4.7 万。把 `sample_chart.png` 换成 `.jpg` 再试，前缀会变成 `data:image/jpeg;base64,/9j/`——这正是 `data_url` 里那两档 MIME 判断的效果。同时顺手确认 `QUESTIONS[1]` 的三个正则（`\bQ3\b` / `95\s*M` / `85\s*M`）。

**（3）重跑一次实拍，核对路由与验收**

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-agent-book
.venv/bin/python learning/task4/run_4_3_multimodal.py
```

预期现象：结尾打印三行范式对照（`native exact=1.00 judge=1.00`、`extract exact=0.00`、`tool exact=1.00`），再打印 `acceptance: 9 / 9 | leak scan: clean` 与 `DONE <新时间戳目录>`。想核对「哪次调用走了哪家厂商」，看新目录里的 `calls-routed.json`：

```bash
.venv/bin/python -c "
import json,glob
d=sorted(glob.glob('learning/task4/runs/4-3_multimodal/*/calls-routed.json'))[-1]
for c in json.load(open(d)):
    print(c['purpose'], '->', c['provider'], c['model'])
" | head -20
```

预期现象：`native:*` 与 `tool-vision:*` 全部是 `dashscope qwen-vl-max`，`extract-text:*` / `tool-decision:*` / `tool-final:*` 全部是 `deepseek deepseek-flash`——**`RoutingRecorder` 的路由规则（有 `image_url` 就走视觉后端）在数据里一目了然**。

想看 agent.py 那条产品线的三范式串行输出（**需要 Gemini / OpenAI / Doubao 之一的 key，默认模型是 `gemini-3.5-flash`**），可以跑：

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-agent-book/chapter4/multimodal-agent
python demo.py --generate-sample
python demo.py --file test_files/sample_chart.png \
    --query "Which quarter had the highest revenue, and what was the exact value?" \
    --skip-model-comparison
```

它会依次打印三段标题：`1. NATIVE MULTIMODAL MODE` / `2. EXTRACT TO TEXT MODE` / `3. EXTRACT TO TEXT + MULTIMODAL TOOLS`——注意它的「提取」是**模型描述图像**（agent.py L702），与 campaign.py 的本地 OCR 不是一回事；用同一张图跑，两者的差别正好就是本页 3.14 第 (3) 点讲的那个分类差异。
