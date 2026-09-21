# 主动工具发现：一步步读源码

[实验说明](tool-discovery.md) · [完整证据与复现](evidence.md#4-1) · [学习运行脚本](../assets/task4/run_4_1_tool_discovery.py) · [实验协议原文](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/experiment_protocol.json)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>本页按源码顺序把 run_exact_experiment.py 的每一个函数过一遍——先给一张证明"一个不漏"的函数清单，再逐个拆，最后用一次真实运行把整条调用链串起来。原版 1219 行、32 个顶层 def/class。读完本页，你应该能在不打开源码的情况下说出这个文件每一部分在干什么，以及实验 4-1 的两种策略差在哪一行。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附行号，链接指向课程仓库固定提交 `cf7f7a8`。本页讲的是 [chapter4/active-tool-discovery/run_exact_experiment.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py)（1219 行）。**学习运行脚本原文**来自 `learning/task4/run_4_1_tool_discovery.py`（625 行，只换模型不改机制）。**教学示意**只用于说明数据形状，不是任何一边的真实代码。

辅助文件：同目录 [discovery.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/discovery.py)（102 行，旧版工具索引，与本文件无调用关系）与 [experiment_protocol.json](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/experiment_protocol.json)（46 行，验收阈值）。三者是三条独立的线：`run_exact_experiment.py` 是**本次实验**；`discovery.py` 是书里更早的机制演示（对 `tools_library.ALL_TOOLS` 做嵌入，用 OpenAI embeddings 或离线词袋）；`experiment_protocol.json` 只是被 `run()` 读进来当阈值表。

---

## 0. 函数清单地图（一个不漏）

核对命令：`grep -n "^def \|^async def \|^class " run_exact_experiment.py`。**32 条**，下表 32 行。

| # | 函数/类 | 行号 | 一句话作用 | 被谁调用 |
| --- | --- | --- | --- | --- |
| 1 | `canonical_json` | L120–121 | 稳定序列化（排序键、紧凑分隔符），一切哈希的输入格式 | 全文件所有 sha256 处 |
| 2 | `sha256_bytes` | L124–125 | bytes → 十六进制 sha256 | 全文件 |
| 3 | `write_json` | L128–131 | 建父目录 + 原子写 UTF-8 JSON | `run`、`run_group`、`LocalEmbeddingIndex.__init__` |
| 4 | `_server_info` | L134–136 | 兼容 MCP SDK 把 `serverInfo` 改名成 `server_info` | `run` |
| 5 | `schema_dict` | L139–140 | MCP `Tool` 对象 → 纯 dict（by_alias、去 None） | `run` |
| 6 | `render_schemas` | L143–144 | schema 列表 → 缩进 JSON 文本块（喂给模型的那段字） | `run`、`run_agent_task`、`derive_acceptance` |
| 7 | `count_tokens` | L147–148 | tiktoken `o200k_base` 数 token（50K 门禁的尺子） | `append_history`、`run`、`derive_acceptance` |
| 8 | `extract_json` | L151–163 | 从模型输出抠 JSON：去 `<think>`、去围栏、`raw_decode` 逐个候选扫 | `parse_action` |
| 9 | `ollama_chat` | L166–192 | 原版模型调用：POST Ollama `/api/chat`，返回规范化回执 | `run_agent_task`（原版线） |
| 10 | `LocalEmbeddingIndex` | L195–297 | **类**：本地 all-MiniLM-L6-v2 向量索引与 top-k 检索 | `run` 构造，`run_agent_task` 检索（学习版同样调它） |
| 11 | `parse_action` | L300–328 | 模型 JSON → 归一化动作（discover/call_tool/finish） | `run_agent_task` |
| 12 | `grade_plan` | L331–339 | 能力槽位命中率 = 工具选择准确率 | `run_agent_task` |
| 13 | `parse_payload` | L342–354 | MCP `result` → 统一 payload dict | `_call_real_tool` |
| 14 | `simulation_markers` | L357–360 | 只在 control-plane 字段里找 mock/simulated 词 | `mcp_receipt` |
| 15 | `substantive_payload` | L363–392 | 逐工具"有效观测"判据（不只看 success 布尔） | `mcp_receipt` |
| 16 | `mcp_receipt` | L395–436 | 一次工具调用 → 可审计收据（含 `success` 七合一） | `_call_real_tool` |
| 17 | `compact_tool_data` | L439–444 | 观测瘦身（contributors 截前 20 行） | `_call_real_tool` |
| 18 | `arxiv_ids` | L447–458 | 从 search payload 抽 3 个 arXiv ID | `_call_real_tool` |
| 19 | `visualization_code` | L461–482 | 生成一段自包含 SVG 绘图 Python 脚本 | `_call_real_tool` |
| 20 | `_task_artifacts` | L485–506 | 扫描 task_dir：PDF/SVG 的数量、字节、哈希、魔数 | `_finalize_execution` |
| 21 | `_finalize_execution` | L509–522 | receipts + artifacts → `task_complete` | `run_agent_task`（finish 判定与收尾各一次） |
| 22 | `_call_real_tool` | L525–601 | **核心**：通过 MCP 真执行一个动作，并解析依赖参数 | `run_agent_task` |
| 23 | `append_history` | L604–626 | 追加消息 + 一条哈希链事件收据 | `run_agent_task` |
| 24 | `run_agent_task` | L629–788 | **核心**：一个任务 × 一个策略的完整多轮循环 | `run_group` |
| 25 | `run_group` | L791–830 | 一个策略跑完 3 个任务（含续跑与二次尝试） | `run` |
| 26 | `safe_summary` | L833–848 | 两臂汇总（准确率/全槽位/完成数/耗时） | `run` |
| 27 | `_history_chain_valid` | L851–866 | 重算哈希链，证明轨迹未被篡改 | `derive_acceptance` |
| 28 | `_required_receipts_real` | L869–894 | 每个槽位都必须有"真收据"（内含嵌套 `valid`） | `derive_acceptance` |
| 29 | `derive_acceptance` | L897–1046 | **12 条门禁** → `passed`/`failed` | `run` |
| 30 | `build_manifest` | L1049–1057 | 全目录文件 sha256 清单 | `run`（收尾） |
| 31 | `run` | L1060–1200 | 编排：MCP → catalog → 索引 → 两臂 → 门禁 → 落盘 | `main` |
| 32 | `main` | L1203–1219 | CLI 入口（`--campaign-id` / `--resume`） | 进程入口 |

上表 32 行 = `grep -n "^def \|^async def \|^class "` 的 32 条。另有 **7 个缩进在类/函数内部的成员**，上表的命令抓不到，单独列出（随所在条目一起讲）：

- `LocalEmbeddingIndex.__init__`（L203–227）建索引、编码 127 条文本、读写向量缓存
- `LocalEmbeddingIndex.receipt`（L229–241）索引自述收据
- `LocalEmbeddingIndex._text`（L244–246）schema → `"name: 描述首段"`
- `LocalEmbeddingIndex._embed`（L248–260）分批（32）+ 掩码均值池化 + L2 归一化
- `LocalEmbeddingIndex._cosine`（L263–267）手写余弦相似度
- `LocalEmbeddingIndex.search`（L269–277）need → top-k，排除 base 工具
- `_required_receipts_real.valid`（L872–884）嵌套的"真收据"九项判据

**本文件的模块级常量**（不在上表，但改一个数就能改变实验；学习版正是靠改这些常量完成"换模型"）：

- L40–45 路径：`HERE` / `CHAPTER4` / `REPO` / `PROTOCOL_PATH` / `MCP_SERVER` / `VALIDATION_ROOT`
- L47–51 实验开关：`MODEL = "qwen3:4b"`、`OLLAMA_URL`、`OLLAMA_OPTIONS = {"temperature":0,"num_ctx":131072,"num_predict":1400}`、`BASE_TOOL_NAMES = {"web_search","code_interpreter"}`、`DISCOVERY_TOP_K = 5`
- L53–73 工具分类：`TOOL_PROVENANCE`（9 个工具的 backend/origin 白名单）、`SIMULATION_PATTERN`（正则）、`STOCK_TOOLS` / `NEWS_TOOLS` / `ARXIV_SEARCH_TOOLS` / `ARXIV_DOWNLOAD_TOOLS` / `GITHUB_TOOLS` / `CODE_TOOLS`
- L75–91 `TASKS`：三个任务，每个带 `slots`（两个能力集合，这就是准确率的分母）
- L93–105 `DISCOVER_SCHEMA`：元工具 `discover_tools` 自己的 schema
- L107–117 `TREATMENT_GUIDANCE`：实验组系统提示词里那段"别拿 web_search 顶替专家"的话
- L280–297 `_AGENT_PROTOCOL`：单 JSON 动作协议

---

## 1. 主线调用图（一次真实执行）

```text
main()                                       ← L1203
 └─ asyncio.run(run(campaign_id, resume))    ← L1060
     ├─ json.loads(experiment_protocol.json) ──────────→ protocol（阈值表）
     ├─ write_json(campaign_dir/"protocol.json")
     ├─ StdioServerParameters(python, perception-tools/src/main.py)
     ├─ stdio_client(params)  ──→ (read, write)          ← MCP 子进程起在这里
     │   └─ ClientSession(read, write)
     │       ├─ session.initialize() → _server_info()
     │       ├─ session.list_tools() → schema_dict() ×127 → schemas[127]
     │       ├─ canonical_json(schemas) → schema_sha256 / catalog_receipt.json
     │       ├─ catalog.schemas.json.gz（gzip 原样存 127 schema）
     │       ├─ LocalEmbeddingIndex(schemas, campaign_dir/"index")   ← to_thread
     │       │    └─ __init__ → _text ×127 → _embed ×127（384 维）→ 写缓存
     │       │         embedding_receipt.json
     │       ├─ run_group(session, schemas, index, "control")   ← L791
     │       │    └─ for task in TASKS(3):
     │       │        └─ run_agent_task(strategy="control")     ← L629
     │       │             ├─ append_history(system 全量 127 schema)  ← L604
     │       │             ├─ append_history(user: Task + 状态栏)
     │       │             └─ for turn in 1..12:
     │       │                 ├─ ollama_chat(messages)         ← L166
     │       │                 ├─ parse_action(response)        ← L300
     │       │                 ├─ append_history(model_response)
     │       │                 ├─ [_call_real_tool]             ← L525（仅 call_tool 分支）
     │       │                 │    ├─ session.call_tool(name, args)
     │       │                 │    ├─ parse_payload(result)    ← L342
     │       │                 │    └─ mcp_receipt(...)         ← L395
     │       │                 │         ├─ simulation_markers  ← L357
     │       │                 │         └─ substantive_payload ← L363
     │       │                 ├─ append_history(mcp_observation)
     │       │                 └─ [finish 分支] _finalize_execution ← L509
     │       │                       └─ _task_artifacts         ← L485
     │       │        → write_json(control/<task>/receipt.json)
     │       ├─ run_group(..., "treatment")  ← 同一批函数，只差 system prompt 与 discover 分支
     │       │    └─ run_agent_task(treatment):
     │       │         └─ [discover_tools 分支] index.search(need, 5)  ← L269
     │       │              → append_history(schema_injection，user 角色，固定在本轮)
     │       ├─ safe_summary(records)            ← L833  → comparison
     │       ├─ derive_acceptance(...)           ← L897  → 12 条门禁
     │       │    ├─ _history_chain_valid        ← L851
     │       │    └─ _required_receipts_real     ← L869（内嵌 valid）
     │       └─ write_json(summary.json)
     └─ write_json(manifest.json ← build_manifest(campaign_dir))   ← L1049
```

一句话读法：**两支共用同一条流水线**，唯一分叉点是 `run_agent_task` 里 `strategy` 决定的那段 system prompt，以及 `discover_tools` 动作在 treatment 里被允许、在 control 里被回一条拒绝消息。其余（MCP 执行、收据、门禁）完全相同——"变量控制"就落在这一处。

---

## 2. 逐函数讲解（严格按源码顺序）

### 2.1 小工具层：从 `canonical_json` 到 `count_tokens`（L120–148）

这七个函数短到可以一起讲，但它们是整个"可复现证据"体系的承重墙：**所有哈希都先经过 `canonical_json`**，所以"同一批 schema"在任何机器上都得到同一个 sha256。

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="120"
def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8")


def _server_info(initialize):
    """MCP SDK v2 renamed ``serverInfo`` to ``server_info``; accept either."""
    return getattr(initialize, "server_info", None) or initialize.serverInfo


def schema_dict(tool) -> dict[str, Any]:
    return tool.model_dump(by_alias=True, exclude_none=True, mode="json")


def render_schemas(schemas: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(schema, ensure_ascii=False, indent=2) for schema in schemas)


def count_tokens(text: str) -> int:
    return len(tiktoken.get_encoding("o200k_base").encode(text))
```

[固定提交链接 · L120–L148](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L120-L148)

- `canonical_json` 三个参数各有用途：`sort_keys=True` 让 dict 顺序不影响哈希；`separators=(",",":")` 去掉空格，同样的数据在 OOM 与 Mac 上字节完全一致；`default=str` 兜住 Path/datetime 之类的不可序列化对象（`write_json` 也复制了这个兜底）。
- `write_json` 是**非原子**的（直接 `write_text`）——注意与 task3 的 `_write_checkpoint`（tmp + replace）不同。本实验不做并发写，所以够用；但它意味着**进程中途崩掉会留下半截 JSON**。
- `_server_info` 是为兼容两种 MCP SDK 命名而写的兼容层，注释里直说了原因。只有 `run` 用它。
- `schema_dict` 的 `by_alias=True` 很关键：MCP 的 `inputSchema` 字段在 Python 侧叫 `input_schema`，`by_alias` 把它还原成模型能看懂的 `inputSchema`；`exclude_none=True` 去掉空字段，直接减少 token。
- `render_schemas` 是**唯一**决定"schema 长什么样喂给模型"的函数：`"\n".join` + `indent=2`。control 组那份 5 万 token 的 system prompt 就是它拼出来的。
- `count_tokens` 用 `o200k_base` 而不是模型自己的 tokenizer——它只是**尺子**，用来执行 `> 50000` 这条协议阈值（`protocol["minimum_control_schema_tokens"]`）。实测这一把尺子量 127 个 schema 得 **50,597**。

### 2.2 `extract_json`（L151–163）：三层容错抠 JSON

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="151"
def extract_json(text: str) -> Any:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError("model response did not contain valid JSON")
```

[固定提交链接 · L151–L163](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L151-L163)

三层，逐层加宽容忍度：

1. 剥掉 `<think>...</think>` 思考块——qwen3 系列即使关了 thinking 也可能漏出来；学习版 deepseek 关掉 thinking 后这一段基本不触发，但**保留它是无害的**（学习脚本原样复用）。
2. 剥掉 Markdown 围栏。注意正则里 `^...|\s*```$` 中间的 `|` 只覆盖两头，**只有首尾围栏被剥**。
3. `raw_decode` 从**每一个** `{` 或 `[` 开始尝试解析，第一个成功的就返回。所以模型说"我先查股价 {"action":"call_tool",...}" 也能救回来。

三种情况它救不了：完全没有 JSON（抛 `ValueError`）、JSON 语法错到底、以及"合法 JSON 但不含 action 键"——最后一种由 `parse_action` 接住。这是"模型输出 → 可执行动作"的第一道也是唯一一道清洗。

### 2.3 `ollama_chat`（L166–192）：原版模型回执的形状

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="166"
async def ollama_chat(messages: list[dict[str, str]], *, timeout: float = 900.0) -> dict[str, Any]:
    request = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": OLLAMA_OPTIONS,
        "keep_alive": "30m",
    }
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{OLLAMA_URL}/api/chat", json=request)
        response.raise_for_status()
        payload = response.json()
    return {
        "response_model": payload.get("model"),
        "created_at": payload.get("created_at"),
        "done": payload.get("done"),
        "done_reason": payload.get("done_reason"),
        "content": payload.get("message", {}).get("content", ""),
        "thinking": payload.get("message", {}).get("thinking", ""),
        "prompt_eval_count": payload.get("prompt_eval_count"),
        "eval_count": payload.get("eval_count"),
        "total_duration_ns": payload.get("total_duration"),
        "latency_seconds": round(time.perf_counter() - started, 3),
        "request_hash": sha256_bytes(canonical_json(request).encode()),
    }
```

[固定提交链接 · L166–L192](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L166-L192)

请求侧四个要点：`stream: False`（一次拿全，方便存回执）；`think: False`（显式关思考，避免 4B 模型把 token 预算烧在 think 上）；`options` 里 `temperature=0` + `num_ctx=131072`（**必须够大**——control 组一次要吞 5 万 token 的 schema）+ `num_predict=1400`（单次回复上限，学 1.2 节的 `max_tokens` 角色）；`keep_alive: "30m"` 让模型在两次调用之间留在显存里，否则每题都要重新加载。

返回侧是**回执字段白名单**——这正是 `derive_acceptance` 里 `qwen_receipts` 门禁要逐字段检查的东西：`response_model` 必须等于 `MODEL`（证明真的是 qwen3:4b 在答，不是别的模型），`done is True`（没有半途中断），`request_hash` 非空（证明这次调用被哈希固定过），`content` 非空（不是空回复）。`prompt_eval_count` / `eval_count` 是 Ollama 的 token 计数，`total_duration` 是纳秒级总耗时。

**学习版为什么必须换掉它**：Ollama 的 `/api/chat` 不返回 usage 的分项缓存字段，而 DeepSeek 返回 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`——这是本次学习版新增的、原版实验拿不到的一个观测量（control 组 102 万 prompt token 里 101 万命中缓存）。

### 2.4 `LocalEmbeddingIndex`（L195–297）：把 127 个 schema 变成可检索的向量

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="195"
class LocalEmbeddingIndex:
    """Semantic index using the locally cached all-MiniLM-L6-v2 encoder.

    This avoids an external embeddings quota and still uses a real dense
    sentence-embedding model.  ``local_files_only`` makes the campaign fail
    closed rather than silently downloading or switching models.
    """

    def __init__(self, schemas: list[dict[str, Any]], cache_dir: Path):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.schemas = schemas
        self.by_name = {schema["name"]: schema for schema in schemas}
        self.texts = [self._text(schema) for schema in schemas]
        self.model = "sentence-transformers/all-MiniLM-L6-v2"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model, local_files_only=True)
        self.encoder = AutoModel.from_pretrained(self.model, local_files_only=True).to("cpu").eval()
        self.torch = torch
        signature = sha256_bytes(canonical_json(self.texts).encode())[:20]
        self.cache_path = cache_dir / f"embeddings-all-MiniLM-L6-v2-{signature}.json"
        if self.cache_path.exists():
            cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
            self.vectors = cached["vectors"]
        else:
            self.vectors = self._embed(self.texts)
            write_json(self.cache_path, {
                "model": self.model,
                "backend": "local-transformers-mean-pooling",
                "local_files_only": True,
                "signature": signature,
                "texts_sha256": sha256_bytes(canonical_json(self.texts).encode()),
                "vectors": self.vectors,
            })
```

[固定提交链接 · L195–L227](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L195-L227)

**为什么是本地模型**：类 docstring 说得很直白——`local_files_only=True` 是"fail closed"而不是"静默换模型"。它杜绝了两种污染：(a) 外部 embeddings API 的配额和版本漂移；(b) `from_pretrained` 默认会在模型缺失时偷偷联网下载。**代价是它要求你事先把 MiniLM 放进 HuggingFace 缓存**，否则这里直接抛异常而不是降级。

`__init__` 逐段读：

- `torch`/`transformers` 是**函数内 import**——这个文件顶层的 import 列表里没有它们。好处是"不跑嵌入也不报错"，坏处是首次进入这个函数要付几秒导入开销。
- `self.texts = [self._text(schema) for schema in schemas]`——每工具一句话，见 `_text`。
- `signature = sha256_bytes(canonical_json(self.texts).encode())[:20]`：**签名只覆盖文本，不覆盖向量**。含义是：只要 127 条工具文本一字不变，缓存文件名就一样，直接复用旧向量；一旦工具描述改了哪怕一个字符，签名变、缓存文件名变、强制重算。这是"缓存要么全对要么全不算"的设计——比"部分失效"更难出错。
- 缓存命中走 `self.vectors = cached["vectors"]`，**不校验缓存里的 `vectors` 长度**——即缓存本身若被截断，这里不会报错。这是本文件里一处可被指出的薄弱点（推断，不是实测到的失败）。
- `vectors` 是 `list[list[float]]`：外层 127、内层 384（实测），即 127 × 384 的矩阵。1.3 MB 的 JSON 缓存文件里就是这堆浮点数。

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="229"
    def receipt(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "backend": "local-transformers-mean-pooling",
            "device": "cpu",
            "local_files_only": True,
            "catalog_text_count": len(self.texts),
            "texts_sha256": sha256_bytes(canonical_json(self.texts).encode()),
            "cache_path": str(self.cache_path),
            "cache_sha256": sha256_bytes(self.cache_path.read_bytes()),
            "vector_count": len(self.vectors),
            "vector_dimensions": len(self.vectors[0]) if self.vectors else 0,
        }

    @staticmethod
    def _text(schema: dict[str, Any]) -> str:
        summary = (schema.get("description") or "").split("\n\n", 1)[0]
        return f"{schema['name']}: {summary}"
```

[固定提交链接 · L229–L246](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L229-L246)

`receipt()` 不提`success`，只描述"这个索引是什么"：模型名、后端实现（明说是手工均值池化而非 sentence-transformers 的池化层）、`device: cpu`、`catalog_text_count`（应等于工具数 127）、`texts_sha256`、`vector_count`、`vector_dimensions`。门禁 `local_embedding_index_receipted` 就是逐条比对这几个值——**它证明索引是真实的本地模型产物，而不是随手编的随机向量**。

`_text` 是检索质量的第一道瓶颈，值得单独记住：它取 `description` 的**第一个 `\n\n` 之前**那一段。本实验里工具描述的前一段恰好是"这一句话式的领域摘要"（例如 `download: Download a file from a URL to local storage.`、`arxiv_download: Download ArXiv paper PDF.`），后半段才是又长又雷同的 provenance 样板文。这个选择是刻意的——如果把后半段也算进去，所有工具的向量会互相靠近、检索退化。但代价是 `_text` 里**完全没有工具名以外的参数信息**，这也埋下了后面 `download` 战胜 `arxiv_download` 的伏笔（见第 3 节）。

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="248"
    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 32):
            batch = texts[start:start + 32]
            encoded = self.tokenizer(batch, padding=True, truncation=True,
                                     max_length=256, return_tensors="pt")
            with self.torch.no_grad():
                hidden = self.encoder(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
                pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                pooled = self.torch.nn.functional.normalize(pooled, p=2, dim=1)
            vectors.extend(pooled.cpu().tolist())
        return vectors

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        ln = sum(a * a for a in left) ** 0.5
        rn = sum(b * b for b in right) ** 0.5
        return dot / (ln * rn + 1e-12)
```

[固定提交链接 · L248–L267](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L248-L267)

`_embed` 的六个要点，逐行：

1. **批大小 32**，127 条文本走 4 个 batch（32+32+32+31）。
2. `padding=True` 把一个 batch 内补齐到同长；`truncation=True` + `max_length=256` 把超长描述截到 256 token——**超过 256 的部分对检索毫无贡献**，这是又一处"信息丢失"。
3. `with no_grad()` 关梯度：不训练，省内存。
4. `last_hidden_state` 形状是 `[batch, seq_len, 384]`。
5. **均值池化手工实现**：`mask` 把 padding 位置置 0，`(hidden*mask).sum(1)` 是掩码求和，除以 `mask.sum(1)` 得平均——`clamp(min=1e-9)` 防止全 padding 行除零。这就是 `receipt()` 里 `backend: "local-transformers-mean-pooling"` 这个名字的来源：**没有用** `sentence_transformers` 库的 `SentenceTransformer`（那样会多一个依赖），而是自己拿 `AutoModel` + 手写池化搭出来的。
6. `normalize(p=2, dim=1)` 单位化，于是后面的余弦相似度退化成一个内积——`_cosine` 里 `ln`/`rn` 其实恒为 1，但代码仍保留了完整公式（对未归一化的向量也正确）。

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="269"
    def search(self, need: str, top_k: int = DISCOVERY_TOP_K) -> list[dict[str, Any]]:
        query_vector = self._embed([need])[0]
        ranked = sorted(
            ((self._cosine(query_vector, vector), schema)
             for vector, schema in zip(self.vectors, self.schemas)
             if schema["name"] not in BASE_TOOL_NAMES),
            key=lambda pair: pair[0], reverse=True,
        )[:top_k]
        return [{"score": round(score, 6), "schema": schema} for score, schema in ranked]
```

[固定提交链接 · L269–L277](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L269-L277)

`search` 是 treatment 组的**唯一信息入口**。三个细节：

- 查询向量用**同一个** `_embed` 生成——`_embed([need])` 传单元素列表，内部走同样的 tokenizer 与池化。查询与文档用同一编码器是检索能工作的前提。
- `if schema["name"] not in BASE_TOOL_NAMES`：**排除 `web_search` 和 `code_interpreter`**。这两个是 base 工具，已经在 system prompt 里了，模型不需要"发现"它们。排除它们的副作用是：即使某个 need 与 `web_search` 语义最近，也不会浪费 top-5 里的一个名额。
- `top_k` 默认 `DISCOVERY_TOP_K = 5`，而门禁要求 `3 <= top_k <= 5`（见 `derive_acceptance`）——即协议允许实现返回 3 到 5 个，本实现固定 5。
- 返回的是 `{"score": float, "schema": dict}` 列表，**score 保留 6 位小数**——因为 `discovery` 收据要把匹配名与分数一起写进轨迹，这个精度是给审计看的。

### 2.5 `_AGENT_PROTOCOL`（L280–297）：单 JSON 动作协议

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="280"
_AGENT_PROTOCOL = """
Work one step at a time. Every response must be exactly one JSON object with no
markdown. Choose one of these actions:

1. {"action":"discover_tools","need":"one missing capability"}
   Use only when discover_tools is currently available and you lack a suitable
   specialist. Discover one capability at the moment the gap arises; do not
   pre-enumerate all future needs.
2. {"action":"call_tool","tool":"exact_name","query":"primary subject","options":{}}
   Call exactly one currently available tool. Prefer a specialist to generic
   web search. The runtime will return a real observation before your next turn.
3. {"action":"finish","answer":"evidence-grounded answer"}
   Finish only after every requested subtask has a successful observation.

For the arXiv task, one arxiv_download action after arxiv_search downloads the
three returned IDs. For visualization, call github_list_contributors before
code_interpreter. Never invent a result or call an undiscovered tool.
""".strip()
```

[固定提交链接 · L280–L297](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L280-L297)

这是整个实验里**唯一约束模型行为**的东西，也是两支共享的。逐条读：

- **协议是"一次一个动作"**，不是 ReAct 那种"边想边做多步"。理由在注释里：每一步动作之后运行时都会插一条真实观测（`Real MCP observation:`），模型必须基于观测决定下一步。这让轨迹天然可审计（每一轮都有配对的观测），但也把轮数上限卡得很死——**12 轮**（`for turn in range(1, 13)`）。第 3 节的失败案例正是撞上这个上限。
- `action` 三选一。`discover_tools` 的措辞特别强调"gap arises 的那一刻才发现，不要预先列举所有未来需求"——这是实验设计的核心：**测量的是"按需发现"而不是"一次性猜全"**。它同时给出对照组里 `discover_tools` 不可用时的语义（"currently available"）。
- `call_tool` 强调"Prefer a specialist to generic web search"，并承诺"运行时会返回真实观测"。最后一句 `Never invent a result or call an undiscovered tool` 是给"不许幻觉"划的红线。
- 末尾两句是**给两个具体任务的额外提示**（arxiv 下载一次拿三个 ID；可视化先取 contributors 再跑 code_interpreter）。这不是通用协议，而是任务特定的 hint——诚实地说，它降低了"模型自己弄清楚依赖顺序"的难度，属于本实验设计上的已知让步。
- `TREATMENT_GUIDANCE`（L107–117）是**只有 treatment 的 system prompt 里才有**的另一段，它把"web_search 不能顶替专家检索"讲得更狠——因为 treatment 模型一开始只看到三个工具，光靠协议容易用 web_search 蒙混过关。这是本实验的另一个自变量，必须与 `strategy` 一起控制。

### 2.6 `parse_action`（L300–328）：从 JSON 到归一化动作

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="300"
def parse_action(response: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = extract_json(response["content"])
        if not isinstance(parsed, dict):
            raise ValueError("action must be a JSON object")
        kind = parsed.get("action")
        # Tolerate the common ReAct spelling while keeping one-action semantics.
        if not kind and parsed.get("tool"):
            kind = "finish" if parsed["tool"] == "finish" else "call_tool"
        if kind == "discover_tools":
            need = str(parsed.get("need", "")).strip()
            if not need:
                raise ValueError("discover_tools requires a non-empty need")
            return {"action": kind, "need": need}, None
        if kind == "call_tool":
            name = str(parsed.get("tool", "")).strip()
            if not name:
                raise ValueError("call_tool requires tool")
            options = parsed.get("options")
            if not isinstance(options, dict):
                options = parsed.get("arguments") if isinstance(parsed.get("arguments"), dict) else {}
            return {"action": kind, "tool": name,
                    "query": str(parsed.get("query", options.pop("query", ""))),
                    "options": options}, None
        if kind == "finish":
            return {"action": kind, "answer": str(parsed.get("answer", ""))}, None
        raise ValueError(f"unknown action {kind!r}")
    except Exception as exc:
        return None, str(exc)
```

[固定提交链接 · L300–L328](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L300-L328)

返回 `(action, error)` 二元组而不是抛异常——**所有失败都变成一条协议错误消息回灌给模型**（`run_agent_task` 的 `protocol_error` 分支），模型下一轮可以改。这是"多轮自纠"的实现方式。

逐条：

- 整个函数体裹在一个 `try/except Exception` 里，任何异常都变成 `(None, str(exc))`。**没有异常能逃出去**——包括 `response["content"]` 缺键的 `KeyError`。
- `extract_json` 的结果必须是 dict；数组直接拒。
- **兼容 ReAct 拼写**：模型只给了 `{"tool": "..."}` 没给 `action` 时，`tool == "finish"` 判 finish，否则判 `call_tool`。这条容错是为了收住 qwen3 容易滑向的 ReAct 格式。
- 三个分支各自的必填校验：`discover_tools` 要非空 `need`；`call_tool` 要非空 `tool`；`finish` 只要 `answer`（**可以为空串**，`final_answer` 是否非空由 `execution.agent_finished` 单独判）。
- `options` 的兜底很细：`options` 不是 dict 就去试 `arguments`（模型常用的另一个词）；`query` 优先取顶层，**否则从 `options` 里 `pop` 出来**（注意 `pop` 有副作用——它会从 `options` 里删掉 `query`，避免同一个值同时出现在 query 和 options 里）。
- 三种未知情况都会走到最后的 `raise ValueError(f"unknown action {kind!r}")`，也变成协议错误。

被 `run_agent_task` 调用一次/轮，结果与 `parse_error` 一起存进 `interactions` 收据——所以**每一次解析失败都被留档**。

### 2.7 `grade_plan`（L331–339）：准确率 = 槽位命中率

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="331"
def grade_plan(task: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
    names = [action["tool"] for action in actions]
    slot_hits = [sorted(set(names) & slot) for slot in task["slots"]]
    return {
        "selected_tools": names,
        "slot_hits": slot_hits,
        "accuracy": sum(bool(hit) for hit in slot_hits) / len(slot_hits),
        "all_required_capabilities_selected": all(slot_hits),
    }
```

[固定提交链接 · L331–L339](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L331-L339)

这段 9 行代码定义了实验的**主指标**，必须读准：

- `names` 是模型**实际调用过**的工具名序列（由 `run_agent_task` 在 `call_tool` 分支 append 而成）。注意：**包含重复**（一个工具调 10 次就是 10 个名字），也**不包含** `discover_tools`（那个动作不进 `actions`）。
- `task["slots"]` 是能力集合的列表，例如 `apple_stock_news` 是 `[{"yfinance_quote","stock_price","finance_market_summary"}, {"web_search","search_news"}]`。
- `set(names) & slot`：**集合交集**——同一槽位里的三个工具只要命中任意一个就算这一槽位通过（它们互为"同一个能力的三个实现"）。
- `accuracy = 命中槽位数 / 槽位总数`，两槽位任务 → 取值只能是 `0 / 0.5 / 1.0`。三个任务的均值就是 `mean_tool_selection_accuracy`（实测 control 1.00、treatment 0.83）。
- `all_required_capabilities_selected = all(slot_hits)`：所有槽位都非空。这是比 accuracy 更严的布尔版本。

**关键边界**：`grade_plan` 只看"选没选对工具"，**完全不看调用是否成功**。所以存在"准确率 1.0 但任务未完成"的格子——control 组的 github 任务就是（选对了 `github_list_contributors` + `code_interpreter`，但 12 轮耗尽前没跑完）。这个分离是刻意的：**工具选择**是第 4 章要测的能力，**执行完成**由 `_finalize_execution` 另算。

### 2.8 `parse_payload`（L342–354）：MCP 结果 → 统一 payload

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="342"
def parse_payload(result) -> dict[str, Any]:
    texts = [getattr(item, "text", "") for item in result.content]
    if not texts:
        return {"success": False, "error": "MCP result had no text content"}
    try:
        payload = json.loads(texts[0])
        # Static perception tools use ActionResponse(message=...), while the
        # expanded tools use data. Normalize both without changing raw fields.
        if isinstance(payload, dict) and "data" not in payload and "message" in payload:
            payload["data"] = payload["message"]
        return payload
    except json.JSONDecodeError:
        return {"success": False, "error": "MCP result was not JSON", "raw": texts[0][:2000]}
```

[固定提交链接 · L342–L354](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L342-L354)

MCP 的 `CallToolResult.content` 是一个 content block 列表。这里**只取第 0 个 block 的 `text`**，其余忽略——即本实验假定"一个工具一次返回一段 JSON 文本"。

两条分支：
- 有文本但**不是 JSON** → 返回 `{"success": False, "error": "MCP result was not JSON", "raw": 前 2000 字}`。`raw` 截断到 2000 字是为了收据体积可控。第 3 节那个失败案例的收据里，`raw` 就是 pydantic 的校验错误文本。
- 是 JSON 但工具用的是**旧式 `ActionResponse(message=...)`**（静态 perception 工具）而不是新式 `data` → 把 `message` 内容**复制**一份到 `data`（注释明说 "without changing raw fields"，即 `message` 原样保留）。这一行是本文件能同时兼容两代工具的原因。

注意：MCP 的传输层错误（工具抛异常）**不在这里体现**——那由 `result.isError` 在 `mcp_receipt` 里单独看。

### 2.9 `simulation_markers`（L357–360）与 `substantive_payload`（L363–392）：两条"这是真的吗"的判据

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="357"
def simulation_markers(value: Any) -> list[str]:
    """Record suspicious evidence markers instead of assuming results are real."""
    return sorted({match.group(1).lower()
                   for match in SIMULATION_PATTERN.finditer(canonical_json(value))})
```

[固定提交链接 · L357–L360](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L357-L360)

`SIMULATION_PATTERN = re.compile(r"\b(mock(?:ed)?|placeholder|synthetic|simulat(?:ed|ion))\b", re.IGNORECASE)`（L64–66）。这个函数把输入序列化成 JSON 后扫描这些词，返回**去重排序后的小写词表**。用集合去重（同一个词出现 5 次只报一次）、排序（顺序不影响哈希与比较）。注意它是"记录嫌疑"而不是"判定造假"——返回值是给**人**看的证据，判定在 `mcp_receipt` 里做。

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="363"
def substantive_payload(tool_name: str, payload: dict[str, Any]) -> bool:
    """Require task evidence, not merely a backend's success boolean."""
    data = payload.get("data")
    if tool_name in {"yfinance_quote", "stock_price"}:
        return isinstance(data, dict) and data.get("current_price") is not None
    if tool_name == "finance_market_summary":
        return isinstance(data, dict) and bool(data.get("history"))
    if tool_name == "web_search":
        return isinstance(data, dict) and data.get("count", 0) > 0 \
            and bool(data.get("results"))
    if tool_name == "search_news":
        return isinstance(data, list) and bool(data) and all(
            isinstance(row, dict) and row.get("title") and row.get("url") for row in data
        )
    if tool_name == "arxiv_search":
        return isinstance(data, dict) and data.get("count", 0) >= 3 \
            and len(data.get("papers", [])) >= 3
    if tool_name == "arxiv_download":
        if not isinstance(data, dict) or data.get("file_size", 0) <= 1000:
            return False
        path = Path(str(data.get("file_path", "")))
        return path.is_file() and path.read_bytes()[:5] == b"%PDF-"
    if tool_name == "github_list_contributors":
        return isinstance(data, list) and bool(data) and all(
            isinstance(row, dict) and row.get("login")
            and isinstance(row.get("contributions"), int) for row in data
        )
    if tool_name == "code_interpreter":
        return isinstance(data, dict) and data.get("returncode") == 0
    return data is not None
```

[固定提交链接 · L363–L392](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L363-L392)

这是全文件**最容易被跳过、但最能体现实验诚意**的函数。docstring 一句话点题："Require task evidence, not merely a backend's success boolean"——**工具返回 `success: true` 不算数，必须看到这个工具该有的数据形状**。

逐个工具读，注意判据都是"能不能支撑后续推理"，不是"格式对不对"：

- `yfinance_quote` / `stock_price`：必须有 `current_price` 且非 None——**价格本身**。这是任务真正要的数。
- `finance_market_summary`：必须有非空 `history`。
- `web_search`：`count > 0` **且** `results` 非空（两个都要）。
- `search_news`：**逐行**校验——每行都有 `title` 和 `url`。少一个字段就整条判假。
- `arxiv_search`：`count >= 3` **且** `papers` 至少 3 条。这个"3"不是随便写的，它对齐任务的"下载 top three"——如果不返回 3 篇，后面的下载任务根本无从谈起。
- `arxiv_download`：最严——`file_size > 1000` 字节，并且 `file_path` 指向的文件**真实存在**且**前 5 字节是 `%PDF-`**。这是把"真的落了一个 PDF 到磁盘"写进了判据。
- `github_list_contributors`：每行有 `login` 且 `contributions` 是**整数**（`isinstance(..., int)`，排除了字符串 `"12"` 这种）。
- `code_interpreter`：`returncode == 0`——进程真的零退出。
- 兜底 `return data is not None`：未知工具只要给了 data 就算有效。

**副作用**：`arxiv_download` 那一支会做 `path.read_bytes()`——真的读磁盘。所以这个"判据函数"有 I/O 副作用，不是纯函数（推断：这本身无害，但在并发场景下会重复读文件）。

### 2.10 `mcp_receipt`（L395–436）：一次调用的可审计收据

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="395"
def mcp_receipt(tool_name: str, result, payload: dict[str, Any],
                *, arguments: dict[str, Any], latency_seconds: float) -> dict[str, Any]:
    configured = TOOL_PROVENANCE.get(tool_name, {})
    payload_backend = payload.get("backend") if isinstance(payload, dict) else None
    configured_backend = configured.get("backend")
    if tool_name == "web_search":
        engine = str(payload.get("metadata", {}).get("search_engine", "")).lower()
        configured_backend = {
            "duckduckgo": "html-or-lite.duckduckgo.com",
            "serper-google": "google.serper.dev",
            "tavily": "api.tavily.com",
        }.get(engine, configured_backend)
    provenance = {
        "backend": configured_backend or payload_backend,
        "origin": configured.get("origin"),
    }
    is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
    # Remote bodies are untrusted observations and may legitimately discuss a
    # "simulation" or "mock". Inspect only control-plane provenance/error
    # metadata so content cannot falsely invalidate (or validate) the backend.
    markers = simulation_markers({
        "backend": payload.get("backend"),
        "error_type": payload.get("error_type"),
        "error": payload.get("error"),
        "metadata": payload.get("metadata"),
    })
    substantive = substantive_payload(tool_name, payload)
    return {
        "tool": tool_name,
        "arguments": arguments,
        "transport": "mcp-stdio",
        "mcp_result_is_error": is_error,
        "backend_provenance": provenance,
        "simulation_markers": markers,
        "substantive_observation": substantive,
        "latency_seconds": latency_seconds,
        "payload": payload,
        "success": bool(payload.get("success")) and not is_error and not markers and substantive
                    and bool(provenance["backend"]) and provenance["origin"] in {
                        "live-api", "local-process"
                    },
    }
```

[固定提交链接 · L395–L436](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L395-L436)

这是"证据层"的核心。三块逻辑，按顺序：

**(1) 后端归属（provenance）**——"这个结果是谁给的"。

- `TOOL_PROVENANCE`（L53–63）是**代码里写死**的白名单：9 个工具各自的 backend 与 origin（`live-api` 或 `local-process`）。这是"先声明再验证"的模式。
- 唯一的动态分支是 `web_search`：从 payload 的 `metadata.search_engine` 反查真实后端（`duckduckgo` → `html-or-lite.duckduckgo.com`，`serper-google` → `google.serper.dev`，`tavily` → `api.tavily.com`）。查不到就退回白名单里的默认值。这个分支存在的意义是：web_search 可能被配置成不同的搜索引擎，把真实那个记下来，收据才诚实。
- 最终 `backend = configured_backend or payload_backend`，`origin` **只取白名单**——即 payload 自己声称的 origin 不被采信。

**(2) 仿真标记只看 control-plane**。这是全文件**最重要的一句注释**：

> Remote bodies are untrusted observations and may legitimately discuss a "simulation" or "mock". Inspect only control-plane provenance/error metadata so content cannot falsely invalidate (or validate) the backend.

翻译成大白话：远端网页/论文正文是**不可信观测**，它们完全可能正常地讨论"模拟"或"mock"这些词（比如一篇讲 LLM 仿真的论文）。如果整个 payload 拿去扫关键词，一篇正常论文就会把这条收据误判成造假。所以 `simulation_markers` 的输入被**手工限缩成四个 control-plane 字段**：`backend`、`error_type`、`error`、`metadata`——这些是工具执行器自己写的元数据，不是远端内容。**这一行是"内容不能作证"这个安全原则的具体实现**，也是"实测与推断分开"在代码层面的体现。

**(3) `success` 是七项合取**，缺一不可：

```text
payload["success"] is True            ... 工具自己说成了
and not is_error                      ... MCP 层没有报错
and not markers                       ... control-plane 里没有 mock/simulated 词
and substantive                       ... 观测有实质数据（2.9）
and provenance["backend"] 非空        ... 有明确后端归属
and provenance["origin"] in {live-api, local-process}   ... 来源在白名单内
```

——顺带说明一个易混点：收据里同时有 `payload.success`（工具说的）和顶层 `success`（本函数算的）。README 与门禁用的是**顶层那个**；`payload` 原样保留是为了审计时能对比"工具说成了但被我们否了"的情况（第 3 节的失败案例里，顶层 `success=False`、`payload.success=False`，但 `payload.error` 是 "MCP result was not JSON"——一眼能看出是参数校验失败而非网络问题）。

### 2.11 `compact_tool_data`（L439–444）：给模型的观测瘦身

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="439"
def compact_tool_data(tool_name: str, payload: dict[str, Any]) -> Any:
    data = payload.get("data")
    if tool_name == "github_list_contributors" and isinstance(data, list):
        return [{"login": row.get("login"), "contributions": row.get("contributions")}
                for row in data[:20]]
    return data
```

[固定提交链接 · L439–L444](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L439-L444)

只有一个工具被瘦身：contributors 列表截前 20 行、每行只留 `login` 与 `contributions`。原因很直接——GitHub 的原始返回每行有几十个字段，塞进对话历史既贵又噪。**注意这是给模型的观测，不是收据**（收据里的 `payload` 是完整的）。截到 20 行是个取舍：可视化只用前 10 行（见 `visualization_code`），所以 20 行有余量。

### 2.12 `arxiv_ids`（L447–458）：依赖解析第一例

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="447"
def arxiv_ids(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data", {})
    if isinstance(data, dict) and "message" in data:
        data = data["message"]
    papers = data.get("papers", []) if isinstance(data, dict) else []
    ids = []
    for paper in papers:
        raw = str(paper.get("id") or paper.get("entry_id") or paper.get("pdf_url") or "")
        match = re.search(r"(?:abs/|pdf/)?([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", raw)
        if match:
            ids.append(match.group(1))
    return ids[:3]
```

[固定提交链接 · L447–L458](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L447-L458)

- 前四行是双重解包容错：兼容 `data` 直接是论文列表容器、或 `data.message` 再套一层（旧式 `ActionResponse`）。
- `paper.get("id") or paper.get("entry_id") or paper.get("pdf_url")`：**三个字段任一**都能当 ID 源——arXiv 的不同接口给的字段名不一样。
- 正则 `([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)` 抓的是 arXiv 的现代 ID 格式（`2609.22078v1`），前缀 `abs/` 或 `pdf/` 可选。**它只抓这一种格式**，老式 ID（`cs.CL/0601001`）抓不到——这是本函数的已知覆盖边界。
- `ids[:3]`：截前 3，对齐任务的 "top three"。
- **为什么要这个函数**：`arxiv_download` 的 schema 要的是 `paper_id` + `download_dir`，而模型在 `arxiv_search` 里只给了 `query`。**这个函数是编排器替模型做的一步依赖解析**——把上一步的观测翻译成下一步的参数。docstring（L12–16）坦白了这层设计："orchestrator supplies task constants ... and resolves dependent arguments"。

### 2.13 `visualization_code`（L461–482）：依赖解析第二例

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="461"
def visualization_code(contributors: list[dict[str, Any]], output_path: Path) -> str:
    rows = [(str(row.get("login", "unknown")), int(row.get("contributions") or 0))
            for row in contributors[:10]]
    return f"""import html
rows = {rows!r}
width, height, margin = 900, 500, 70
...
open({str(output_path)!r}, 'w', encoding='utf-8').write(''.join(parts))
print({str(output_path)!r})
"""
```

[固定提交链接 · L461–L482](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L461-L482)

（上为节选，中间的 SVG 拼装循环在源码 L472–479。）

- 它是**代码生成器**：把上一步拿到的 contributors 数据**内联进一段 Python 源码字符串**，再交给 `code_interpreter` 执行。`{rows!r}` 用 `repr` 注入列表字面量——这是**安全的**注入方式（`repr` 会正确转义引号，不会像字符串拼接那样被数据里的引号破坏语法）。
- 只取前 10 行。这段生成代码做的事：算最大值为基准、按比例算柱高、拼 SVG 字符串、写文件、`print` 路径。选择生成 SVG（纯文本、可校验 `%<svg` 魔数）而不是 PNG（需要额外依赖），是为了 `_task_artifacts` 能用"前几字节是不是 `<svg`"这种廉价方式验真。
- 生成的脚本**没有任何外部依赖**（只 import `html`），所以 `code_interpreter` 的本机子进程能直接跑通。
- 结尾 `print(output_path)` 很关键：**让执行器有可观测的产物路径**，模型的下一轮观测里能看到这个路径。

### 2.14 `_task_artifacts`（L485–506）：磁盘上到底有没有东西

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="485"
def _task_artifacts(task_dir: Path) -> dict[str, Any]:
    downloaded_paths = sorted((task_dir / "papers").glob("*.pdf")) \
        if (task_dir / "papers").exists() else []
    downloaded = []
    for path in downloaded_paths:
        data = path.read_bytes()
        downloaded.append({
            "path": str(path),
            "bytes": len(data),
            "sha256": sha256_bytes(data),
            "pdf_signature": data.startswith(b"%PDF-"),
        })
    chart = task_dir / "contributors.svg"
    chart_data = chart.read_bytes() if chart.exists() else b""
    return {
        "downloaded_pdfs": downloaded,
        "download_count": len(downloaded),
        "visualization": str(chart) if chart.exists() else None,
        "visualization_bytes": len(chart_data),
        "visualization_sha256": sha256_bytes(chart_data) if chart_data else None,
        "visualization_svg_signature": chart_data.lstrip().startswith(b"<svg") if chart_data else False,
    }
```

[固定提交链接 · L485–L506](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L485-L506)

这是**唯一直接读磁盘**的证据函数，回答"工具说下载成功了，文件真的在吗"。

- PDF 侧：`sorted(glob("*.pdf"))` 保证枚举顺序稳定（不稳定的顺序会让 manifest 哈希漂移）；每个 PDF 记字节数与 sha256，并验 `%PDF-` 魔数。**注意它只 glob `task_dir/papers/*.pdf`**——落在别处的 PDF 不算数（第 3 节 treatment 失败的下载写到了 `/tmp`，就算写成功也不在这个目录里）。
- SVG 侧：`lstrip().startswith(b"<svg")`——先剥前导空白再验魔数，容忍开头有换行。
- `chart_data` 为空时 `sha256` 返回 `None` 而不是空串哈希，语义上区分"没有文件"和"文件是空的"。

### 2.15 `_finalize_execution`（L509–522）：什么算"任务完成"

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="509"
def _finalize_execution(task: dict[str, Any], state: dict[str, Any], task_dir: Path) -> dict[str, Any]:
    artifacts = _task_artifacts(task_dir)
    success_names = {receipt["tool"] for receipt in state["receipts"] if receipt.get("success")}
    completion = all(success_names & slot for slot in task["slots"])
    if task["id"] == "transformer_arxiv_download":
        completion = completion and artifacts["download_count"] == 3 and all(
            row["pdf_signature"] and row["bytes"] > 1000
            for row in artifacts["downloaded_pdfs"]
        )
    if task["id"] == "github_contributors_visualization":
        completion = completion and artifacts["visualization_bytes"] > 100 \
            and artifacts["visualization_svg_signature"]
    return {"receipts": state["receipts"], "artifacts": artifacts,
            "task_complete": bool(completion)}
```

[固定提交链接 · L509–L522](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L509-L522)

三档判据，逐档加严：

1. **通用档**：`success_names` 只收 `receipt["success"] is True` 的工具名（注意是**顶层** success，即通过 2.10 七项合取的那个），然后要求每个槽位都有命中。这与 `grade_plan` 的 looks-right 不同——**这里要求真的成功了**。
2. **arXiv 档**：还要 `download_count == 3` 且每个 PDF 有魔数且 > 1000 字节。三个 ID 三个文件，缺一不可。
3. **可视化档**：还要 SVG 字节数 > 100 且魔数通过。

**这个函数在 `run_agent_task` 里被调用两次**：一次是模型发 `finish` 时的"完成探针"（不完成就回一条 `premature_finish_rejected`），一次是循环结束后的收尾。同一个判据两处用，保证"模型自认为完成"和"系统判定完成"用的是同一把尺子。

### 2.16 `_call_real_tool`（L525–601）：真执行 + 依赖解析

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="525"
async def _call_real_tool(session: ClientSession, task: dict[str, Any], action: dict[str, Any],
                          task_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    """Execute one model-selected capability through MCP and update dependencies."""
    name = action["tool"]
    query = action["query"]
    options = dict(action["options"])
    if name in STOCK_TOOLS:
        query, options = "AAPL", {}
    elif name in NEWS_TOOLS:
        query = "Apple AAPL stock"
        options.update({"num_results": 5, "limit": 5})
    elif name in ARXIV_SEARCH_TOOLS:
        query = "transformer"
        options.update({"max_results": 3, "sort_by": "submittedDate"})
    elif name in GITHUB_TOOLS:
        query, options = "openai/openai-python", {"limit": 10}
    elif name in CODE_TOOLS:
        chart = task_dir / "contributors.svg"
        query = visualization_code(state["contributors"], chart)
        options = {"timeout": 30}
```

[固定提交链接 · L525–L544](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L525-L544)

这段是**任务常量覆盖**：模型说的 `query` 基本被丢弃，换成任务固定的常量（AAPL / Apple AAPL stock / transformer / openai/openai-python）。docstring 那句 "The orchestrator supplies task constants (AAPL, transformer, openai/openai-python)" 就是说这个。**这是一个重要的实验设计让步**——模型只需要"选对工具"，不需要"把参数填对"，从而把测量聚焦在工具选择上。`CODE_TOOLS` 那一支更进一步：`query` 直接是**生成的代码**（2.13）。

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="546"
    if name in ARXIV_DOWNLOAD_TOOLS:
        ids = arxiv_ids(state.get("search_payload") or {})
        if len(ids) != 3:
            receipt = {"tool": name, "success": False,
                       "error": f"expected three arXiv IDs, found {len(ids)}"}
            state["receipts"].append(receipt)
            return receipt
        download_dir = task_dir / "papers"
        download_dir.mkdir(parents=True, exist_ok=True)
        group = []
        for paper_id in ids:
            args = {"paper_id": paper_id, "download_dir": str(download_dir)}
            started = time.perf_counter()
            result = await session.call_tool(name, args)
            payload = parse_payload(result)
            receipt = mcp_receipt(
                name, result, payload, arguments=args,
                latency_seconds=round(time.perf_counter() - started, 3),
            )
            receipt["paper_id"] = paper_id
            state["receipts"].append(receipt)
            group.append(receipt)
        return {"tool": name, "success": all(item["success"] for item in group),
                "downloads": [{"paper_id": item["paper_id"], "success": item["success"]}
                              for item in group]}
```

[固定提交链接 · L546–L570](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L546-L570)

`arxiv_download` 是**唯一一个"一次动作 N 次调用"**的特例：

- 它从 `state["search_payload"]`（上一次 `arxiv_search` 存下来的原始 payload）解析出 3 个 ID。`state.get(...) or {}` 兜住"没搜过就下载"的情况。
- **ID 数不等于 3 就直接判失败**，并把 `{"tool":..,"success":False,"error":"expected three arXiv IDs, found N"}` 放进收据。注意这条收据**没有** `transport` / `backend_provenance` 等字段——所以它天然通不过 `_required_receipts_real`（那个函数要求那些字段存在且合法）。这是"伪造不了"的另一层：**手工构造的失败收据结构上就与真收据不同**。
- 循环里对每个 ID 真调一次 `session.call_tool`，每次调用生成**一条独立收据**（带 `paper_id` 附加字段）。所以一次 `arxiv_download` 动作会产生 3 条收据——门禁 `_required_receipts_real` 正是要求这 3 条都是真的、且 `paper_id` 互不相同。
- 返回的是汇总 `{"tool":.., "success": all(...), "downloads":[...]}`，其中 `downloads` 只留 `paper_id` + `success`——**给模型看的观测是精简的**，完整收据在 `state` 里。

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="572"
    if name == "yfinance_quote":
        args = {"symbol": query}
    elif name == "stock_price":
        args = {"symbol": query}
    elif name == "web_search":
        args = {"query": query, "num_results": int(options.get("num_results", 5)),
                "region": str(options.get("region", "wt-wt"))}
    elif name == "arxiv_search":
        args = {"query": query, "max_results": int(options.get("max_results", 3)),
                "sort_by": str(options.get("sort_by", "submittedDate"))}
    else:
        args = {"query": query, "options_json": json.dumps(options, ensure_ascii=False)}
    started = time.perf_counter()
    result = await session.call_tool(name, args)
    payload = parse_payload(result)
    if name in ARXIV_SEARCH_TOOLS:
        state["search_payload"] = payload
    if name in GITHUB_TOOLS:
        compact = compact_tool_data(name, payload)
        state["contributors"] = compact if isinstance(compact, list) else []
    receipt = mcp_receipt(
        name, result, payload, arguments=args,
        latency_seconds=round(time.perf_counter() - started, 3),
    )
    success = receipt["success"]
    if name in CODE_TOOLS and isinstance(payload.get("data"), dict):
        success = success and payload["data"].get("returncode") == 0
        receipt["success"] = success
    state["receipts"].append(receipt)
    return {"tool": name, "success": success, "data": compact_tool_data(name, payload)}
```

[固定提交链接 · L572–L601](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L572-L601)

**参数映射是一个白名单**：只有 4 个工具（`yfinance_quote`、`stock_price`、`web_search`、`arxiv_search`）有专门分支；**其余一切工具**都落进最后的 `else`：

```python
args = {"query": query, "options_json": json.dumps(options, ensure_ascii=False)}
```

这一行是**第 3 节那个失败案例的机械根因**，必须划重点：`search_news`、`finance_market_summary`、`github_list_contributors`、`arxiv_download`（已被前面的特例拦下）、`code_interpreter` 之所以能用，是因为它们的 schema 恰好接受 `query` + `options_json`（见第 3 节里 `search_news` 的 `props: ['query','options_json']`）。而 `download` 的 schema 是 `props: ['url','output_path','overwrite','timeout']`——**用它接不住 query/options_json，必然 pydantic 校验失败**。**这不是模型参数填错，而是运行时适配器只会这一种装箱方式。**

后面三行是**依赖暂存**：`arxiv_search` 的原始 payload 存进 `state["search_payload"]`（供后面 `arxiv_download` 解析 ID）；`github_list_contributors` 的结果经 `compact_tool_data` 存进 `state["contributors"]`（供后面生成可视化代码）。**`state` 就是这条流水线的"黑板"**——模型只负责按顺序点名工具，跨工具的依赖由编排器在黑板上传。

最后一段给 `code_interpreter` 打**额外补丁**：`mcp_receipt` 的通用判据已经要求 `returncode == 0`（2.9），这里再确认一次并**回写 `receipt["success"]`**。为什么重复？因为 `mcp_receipt` 里 `payload.success` 可能为 True 而 `returncode` 非 0（脚本跑了但报错），这一行把两者绑死。**这是一个"收据被事后修改"的例外**，读代码时要留意它不是纯函数。

### 2.17 `append_history`（L604–626）：哈希链 + 累计 token + 状态栏

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="604"
def append_history(messages: list[dict[str, str]], history: list[dict[str, Any]],
                   role: str, content: str, *, turn: int, event: str,
                   available: set[str] | None = None,
                   extra: dict[str, Any] | None = None) -> None:
    """Append one immutable conversation event and a cumulative hash-chain receipt."""
    messages.append({"role": role, "content": content})
    content_hash = sha256_bytes(content.encode())
    prior = history[-1]["chain_sha256"] if history else "0" * 64
    row = {
        "sequence": len(history),
        "turn": turn,
        "role": role,
        "event": event,
        "content_sha256": content_hash,
        "content_tokens": count_tokens(content),
        "available_tools": sorted(available) if available is not None else None,
        "status_bar_present": "[STATUS BAR: available tools =" in content,
        "chain_sha256": sha256_bytes(
            f"{prior}:{role}:{event}:{turn}:{content_hash}".encode()
        ),
    }
    row.update(extra or {})
    history.append(row)
```

[固定提交链接 · L604–L626](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L604-L626)

**每次往对话里加一条消息，同时往 `history` 里加一条"事件收据"**——两个列表并行增长，`messages` 是发给模型的真实内容，`history` 是它的可审计影子。四个机制：

**(1) 哈希链**。`prior = history[-1]["chain_sha256"]`，第一条的前驱是 `"0"*64`；本条的 `chain_sha256 = sha256(prior + ":" + role + ":" + event + ":" + turn + ":" + content_hash)`。含义：**任何一条历史被改动，它之后的所有链值都会变**。这让 `_history_chain_valid` 能一次性验完全部轨迹（2.20）。注意链值覆盖了 `role/event/turn` 而不只是内容——所以"把一条 user 消息伪装成 system"也会被抓住。

**(2) 累计 token**。`content_tokens = count_tokens(content)` 逐条记，后续通过 `sum(row.get("schema_tokens",0) ...)` 汇总出 `dynamic_schema_injection_tokens`。**这是"动态注入 token 三题分别 1,928 / 3,884 / 2,623"这个数字的唯一来源**——它不靠事后估算，而是每条注入事件落库时的真实测量。

**(3) 状态栏（status bar）**。`status_bar_present` 是一个**布尔证据字段**：检查本条内容里有没有 `"[STATUS BAR: available tools ="` 这个确切子串。而状态栏本身是**每条 user 消息尾部**都拼上的 `[STATUS BAR: available tools = [...]]`（见 `run_agent_task` 里各分支）。对照实验里，control 组的状态栏从第一轮起就是全量 127 个工具，treatment 组则随 `discover_tools` 动态增长——**状态栏是让模型"知道此刻有哪些工具"的唯一渠道**（treatment 的 system prompt 里只有三个 schema）。`available_tools` 字段则在每条事件上留下"当时可见集合的快照"。

**(4) `extra` 透传**。`row.update(extra or {})` 让调用方塞入事件专属字段（`schema_names` / `schema_tokens` / `schemas_sha256` / `missing_capability_slots` 等）。这几个字段后面被门禁逐条比对。

**被谁调用**：`run_agent_task`，共 8 处（初始 system、任务 user、模型回复、协议错误、拒绝 finish、拒绝 control 的 discover、schema 注入、工具不可用、真实观测）。**每一轮至少两条**（模型回复 + 观测）。

### 2.18 `run_agent_task`（L629–788）：一个任务 × 一个策略的完整循环

这是最长的函数（160 行），也是**两支唯一的差异所在**。按阶段拆。

**阶段一：分叉——两套 system prompt**

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="633"
    by_name = {schema["name"]: schema for schema in schemas}
    all_schema_text = render_schemas(schemas)
    if strategy == "control":
        system = (f"You are Qwen3-4B in the full-schema control. The perception MCP server exposed "
                  f"{len(schemas)} complete tools.\n\n{all_schema_text}\n\n{_AGENT_PROTOCOL}")
        available = set(by_name)
    else:
        base_schemas = [by_name[name] for name in sorted(BASE_TOOL_NAMES)]
        system = ("You are Qwen3-4B in the active-discovery treatment. Initially only the three "
                  "schemas below exist. Discover a specialist only when you encounter that capability "
                  "gap. Previously discovered schema blocks stay at their original history position.\n\n" +
                  TREATMENT_GUIDANCE + "\n\n" +
                  render_schemas(base_schemas + [DISCOVER_SCHEMA]) + "\n\n" + _AGENT_PROTOCOL)
        available = set(BASE_TOOL_NAMES)
    initial_schema_names = sorted(available | ({"discover_tools"} if strategy == "treatment" else set()))
```

[固定提交链接 · L633–L647](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L633-L647)

**这就是整个实验的自变量。**三行差异：

- control：`system` = 横幅 + **全部 127 个 schema 原文**（`all_schema_text`）+ 协议。实测这个 system prompt 是 **50,825 token**（比 schema 本身 50,597 多 228，就是横幅与协议的字节）。`available = set(by_name)`，127 个全可见。
- treatment：`system` = 横幅 + `TREATMENT_GUIDANCE` + **只有 3 个 schema**（`web_search`、`code_interpreter`、`discover_tools`）+ 协议。实测 **1,247 token**。`available = {web_search, code_interpreter}`（注意 `discover_tools` **不在 `available` 里**——它不是一个可以被 `call_tool` 调用的工具，而是一个被特殊处理的协议动作；它只出现在 `initial_schema_names` 与 system prompt 的 schema 块里）。

treatment 横幅里那句 "Previously discovered schema blocks stay at their original history position" 是**对模型的行为约束**，对应代码里"注入消息一旦追加就永不移动"的实现（2.18 阶段四）。

**阶段二：开局两条历史**

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="648"
    messages: list[dict[str, str]] = []
    history: list[dict[str, Any]] = []
    append_history(messages, history, "system", system, turn=0,
                   event="initial_system_prompt", available=available,
                   extra={"schema_names": initial_schema_names})
    append_history(
        messages, history, "user",
        f"Task: {task['prompt']}\n[STATUS BAR: available tools = {sorted(available)}]",
        turn=0, event="task_prompt", available=available,
    )
    state: dict[str, Any] = {"receipts": [], "search_payload": None, "contributors": []}
```

[固定提交链接 · L648–L658](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L648-L658)

`turn=0` 的两条：system（含 schema）+ user（任务 + 状态栏）。`state` 初始化三键：`receipts`（本任务所有工具调用收据）、`search_payload`（arxiv 依赖）、`contributors`（可视化依赖）。**`state` 是 per-task 的，不跨任务复用**——所以三个任务互不污染。

**阶段三：12 轮主循环的开头**

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="664"
    started = time.perf_counter()
    for turn in range(1, 13):
        response = await ollama_chat(messages)
        action, parse_error = parse_action(response)
        interactions.append({"turn": turn, "response": response,
                             "action": action, "parse_error": parse_error})
        append_history(messages, history, "assistant", response["content"], turn=turn,
                       event="model_response", available=available)
        if parse_error or action is None:
            parse_errors.append(parse_error or "unknown parse error")
            append_history(
                messages, history, "user",
                f"Protocol error: {parse_error}. Return exactly one valid JSON action. "
                f"[STATUS BAR: available tools = {sorted(available)}]",
                turn=turn, event="protocol_error", available=available,
            )
            continue
```

[固定提交链接 · L664–L680](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L664-L680)

- `range(1, 13)` = **最多 12 轮**（实测有三格撞到上限：control 与 treatment 分别各有一格恰好跑满 12 轮）。
- `interactions` 存**完整回执**（含 usage/hash/latency）——这是 `derive_acceptance` 里 `qwen_receipts` 门禁的数据源。
- 解析失败 → 记 `parse_errors` → 回一条 `protocol_error` 消息 + 状态栏 → `continue`。**失败不消耗动作，但消耗轮数**。

**阶段四：finish 分支与"提前完成被拒"**

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="681"
        if action["action"] == "finish":
            completion_probe = _finalize_execution(task, state, task_dir)
            if not completion_probe["task_complete"]:
                successful = {
                    receipt.get("tool")
                    for receipt in state["receipts"]
                    if receipt.get("success") is True
                }
                missing_count = sum(
                    not bool(successful & slot) for slot in task["slots"]
                )
                append_history(
                    messages, history, "user",
                    "Finish rejected: one or more requested subtasks still lack "
                    f"a successful specialist observation or required artifact "
                    f"(missing capability slots: {missing_count}). "
                    "Use discover_tools for each remaining capability gap, then "
                    "execute the discovered specialist before finishing. "
                    f"[STATUS BAR: available tools = {sorted(available)}]",
                    turn=turn,
                    event="premature_finish_rejected",
                    available=available,
                    extra={"missing_capability_slots": missing_count},
                )
                continue
            final_answer = action["answer"]
            break
```

[固定提交链接 · L681–L709](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L681-L709)

**"finish 被拒"逻辑**：模型说完成时，不轻信——先跑 `_finalize_execution` 探针。没完成就回一条消息，内容包括：(a) 失败原因（缺成功观测或缺工件）；(b) **缺几个槽位**（`missing_capability_slots`，一个整数）；(c) 明确指示"用 discover_tools 补能力，然后执行它，再 finish"；(d) 状态栏。然后 `continue`，**不消耗动作但消耗轮数**。

`missing_count` 的算法值得一读：`sum(not bool(successful & slot) for slot in slots)`——数"哪几个槽位还没成功过"。注意对照 control 组，这条消息会让模型去"从全量目录里挑一个还没用过的工具"；treatment 组则会去 discover——**提示语本身是两支通用的**（不说 discover 专属于谁），因为对 control 模型提到 discover_tools 也无害（它调了会被拒，见下）。

`break` 只发生在探针通过时，`final_answer = action["answer"]` 落盘。

**阶段五：discover_tools 分支（treatment 的核心）**

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="710"
        if action["action"] == "discover_tools":
            if strategy != "treatment":
                append_history(
                    messages, history, "user",
                    "discover_tools is unavailable in the control; choose a listed tool.",
                    turn=turn, event="control_discovery_error", available=available,
                )
                continue
            hits = index.search(action["need"], DISCOVERY_TOP_K)
            hit_schemas = [hit["schema"] for hit in hits]
            block = render_schemas(hit_schemas)
            names = [schema["name"] for schema in hit_schemas]
            available.update(names)
            discovery = {"turn": turn, "need": action["need"], "top_k": len(hits),
                         "matches": [{"name": hit["schema"]["name"], "score": hit["score"]}
                                     for hit in hits],
                         "schemas_sha256": sha256_bytes(block.encode()),
                         "schema_tokens": count_tokens(block)}
            discoveries.append(discovery)
            # This user-history item remains at this exact turn for all later requests.
            append_history(
                messages, history, "user",
                f"discover_tools returned these {len(hits)} complete MCP schemas:\n{block}\n\n"
                f"[STATUS BAR: available tools = {sorted(available)}]",
                turn=turn, event="schema_injection", available=available,
                extra={"schema_names": names, "schema_count": len(hit_schemas),
                       "schemas_sha256": discovery["schemas_sha256"],
                       "schema_tokens": discovery["schema_tokens"]},
            )
            continue
```

[固定提交链接 · L710–L739](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L710-L739)

六步，逐行：

1. **对照组拒绝**：control 里模型若试 `discover_tools`，回一句"control 里不可用，请从列表里挑"，并记一条 `control_discovery_error` 事件。**这条事件的存在本身就是证据**——它能证明 control 组真的没有获得动态注入（门禁没直接查它，但轨迹里可见）。
2. `index.search(need, 5)`：**嵌入检索发生在这一刻**，`need` 是模型自己写的自然语言（实测三条 need 分别是"authoritative real-time stock market quote..."、"search arXiv for academic papers..."、"GitHub repository contributor statistics..."）。
3. `available.update(names)`：**工具可见集合动态增长**——这是 treatment 组"发现"的机制实现。
4. `discovery` 收据：记 `turn`、原始 `need`、`top_k`、每个匹配的 `{name, score}`、注入块的 `schemas_sha256` 与 `schema_tokens`。**这些是门禁逐条比对的字段**——`derive_acceptance` 会用同样的 `render_schemas` + `count_tokens` 重算一遍注入块，与收据比对，证明"注入的内容就是检索到的 schema 原文，没被改过"。
5. **注入消息的角色是 `user`**（不是 system）——这是关键设计：它作为一个**用户消息**留在历史里。协议原文 `experiment_protocol.json` 里也写死了 `"schema_injection_role": "user"`。
6. 注释 `# This user-history item remains at this exact turn for all later requests.`：**注入消息一旦追加就永不移动、永不删除**。这意味着后续每轮请求都会带着它——**注入的 schema 会一直占据上下文，token 成本是"一直付"而不是"付一次"**。这正是 treatment 用"少注入"换"长期占用"的代价来源，也是 `dynamic_schema_injection_tokens` 要单独记账的原因。

**阶段六：call_tool 分支（含不可用与真执行）**

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="740"
        name = action["tool"]
        actions.append(action)
        if name not in available:
            state["receipts"].append({"tool": name, "success": False,
                                      "error": "tool was not available at this turn"})
            hint = ("Call discover_tools for this missing capability first."
                    if strategy == "treatment" else "Choose an exact name from the full catalog.")
            append_history(
                messages, history, "user",
                f"Tool error: {name} is unavailable. {hint} "
                f"[STATUS BAR: available tools = {sorted(available)}]",
                turn=turn, event="unavailable_tool", available=available,
            )
            continue
        observation = await _call_real_tool(session, task, action, task_dir, state)
        append_history(
            messages, history, "user",
            "Real MCP observation:\n" +
            json.dumps(observation, ensure_ascii=False, default=str)[:50000] +
            f"\n[STATUS BAR: available tools = {sorted(available)}]",
            turn=turn, event="mcp_observation", available=available,
            extra={"tool": name, "success": bool(observation.get("success"))},
        )
```

[固定提交链接 · L740–L762](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L740-L762)

- `actions.append(action)` 在**可用性检查之前**——所以一个"不可用"的调用也会进 `actions`，从而可能贡献 `grade_plan` 的槽位命中。**这是准确率口径的一处宽松**：点名了但调不动，也算"选对"。第 3 节的失败案例里 `download` 就是这样进 `actions` 的（但它不在任何槽位里，所以不影响准确率）。
- 不可用分支：记一条**结构上假的收据**（只有 `tool/success/error` 三键）→ 回一条带 `hint` 的消息。hint 随 strategy 变化：treatment 说"先 discover"，control 说"从全量目录里挑个准确名字"。
- 真执行分支：`_call_real_tool` → 把观测 `json.dumps` **截到 50,000 字符**后作为 user 消息回灌。这个 50K 上限防止一次巨型观测（比如完整新闻正文）把上下文撑爆。
- `extra={"tool":..., "success":...}` 落进事件收据——门禁可据此核对"每一轮观测事件对应的工具与成功与否"。

**阶段七：收尾**

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="763"
    grade = grade_plan(task, actions)
    execution = _finalize_execution(task, state, task_dir)
    execution["agent_finished"] = bool(final_answer.strip())
    execution["task_complete"] = execution["task_complete"] and execution["agent_finished"]
    return {
        "task": task["id"], "strategy": strategy, "model": MODEL,
        "prompt": task["prompt"], "actions": actions, "parse_errors": parse_errors,
        "discoveries": discoveries, "grade": grade, "execution": execution,
        "final_answer": final_answer, "interactions": interactions,
        "history_receipt": {
            "events": history,
            "event_count": len(history),
            "final_chain_sha256": history[-1]["chain_sha256"],
            "dynamic_schema_injection_tokens": sum(
                row.get("schema_tokens", 0) for row in history
                if row["event"] == "schema_injection"
            ),
        },
        "initial_schema_names": initial_schema_names,
        "catalog_sha256": sha256_bytes(canonical_json(schemas).encode()),
        "runtime": {"name": "ollama", "model": MODEL,
                    "url": OLLAMA_URL, "options": OLLAMA_OPTIONS},
        "system_prompt_sha256": sha256_bytes(system.encode()),
        "system_prompt_tokens": count_tokens(system),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
```

[固定提交链接 · L763–L788](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L763-L788)

- **两处 completion 收口**：`agent_finished = bool(final_answer.strip())`（模型真的给了非空答案），`task_complete = task_complete and agent_finished`。**12 轮耗尽而没 finish 的格子，`agent_finished` 为 False，整格判未完成**——即使工件齐全。这就是第 3 节 treatment arxiv 与 control github 两格未完成的原因。
- `dynamic_schema_injection_tokens` 是 `history` 里所有 `schema_injection` 事件的 `schema_tokens` 之和——三题 1,928 / 3,884 / 2,623 就是这里出来的。
- 剩下的字段是"这一格的元数据"：`catalog_sha256`（证明六格用的是同一份 127 schema）、`runtime`（证明六格同一个模型同一个 URL 同一套 options）、`system_prompt_sha256` 与 `system_prompt_tokens`（control 50,825 / treatment 1,247）。
- **注意返回的 record 里没有 `discoveries` 之外的 schema 明细**，但 `history_receipt.events` 里有每一条注入的 `schemas_sha256`——门禁靠它重建。

### 2.19 `run_group`（L791–830）：一个策略的三个任务

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="791"
async def run_group(session: ClientSession, schemas: list[dict[str, Any]],
                    index: LocalEmbeddingIndex, strategy: str,
                    campaign_dir: Path, *, resume: bool = False) -> list[dict[str, Any]]:
    records = []
    for task in TASKS:
        task_dir = campaign_dir / strategy / task["id"]
        task_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = task_dir / "receipt.json"
        if resume and receipt_path.exists():
            record = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (
                record.get("strategy") != strategy
                or record.get("task") != task["id"]
                or record.get("model") != MODEL
            ):
                raise RuntimeError(f"incompatible completed task receipt: {receipt_path}")
            if record.get("execution", {}).get("task_complete") is True:
                records.append(record)
                continue
            ...
        record = await run_agent_task(session, schemas, index, strategy, task, task_dir)
        write_json(receipt_path, record)
        records.append(record)
    return records
```

[固定提交链接 · L791–L830](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L791-L830)

（省略的是 L811–826 的"一次有界重试"段落。）

- **顺序执行**：`for task in TASKS` 串行，不是并发。这是必须的——三个任务共享同一个 MCP `session`，而 MCP 的 stdio 会话一次只处理一个请求。
- 每任务一个目录 `campaign_dir/<strategy>/<task_id>/`，输出 `receipt.json`。**目录结构本身把"策略 × 任务"编码进了路径**。
- **续跑（resume）**：已有 receipt 时先验"策略/任务/模型"三字段是否匹配（不匹配直接 `RuntimeError`，防止混装证据）；已完成的复用；未完成的走"有界重试"——把整个 task_dir 归档到 `failed_attempts/attempt-1/`，**清空后重跑一次**；如果 `attempt-1` 已存在（即已经试过两次仍未完成），抛 `RuntimeError("maximum two real attempts exhausted")`。**"最多两次真实尝试"是硬约束，不允许无限循环烧钱**。
- 注意：**归档时把部分产物也一起搬走**（`for child in task_dir.iterdir(): child.replace(...)`），除了 `failed_attempts` 自己。所以二次尝试是"干净目录重跑"，而第一次的 PDF/SVG 半成品被保留在 `attempt-1` 里可查——**失败证据不被销毁**。

### 2.20 `safe_summary`（L833–848）：两臂汇总

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="833"
def safe_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_strategy = {}
    for strategy in ("control", "treatment"):
        rows = [record for record in records if record["strategy"] == strategy]
        by_strategy[strategy] = {
            "tasks": len(rows),
            "mean_tool_selection_accuracy": (
                sum(row["grade"]["accuracy"] for row in rows) / len(rows) if rows else 0
            ),
            "tasks_with_all_required_capabilities": sum(
                bool(row["grade"]["all_required_capabilities_selected"]) for row in rows
            ),
            "tasks_completed": sum(bool(row["execution"]["task_complete"]) for row in rows),
            "elapsed_seconds": round(sum(row["elapsed_seconds"] for row in rows), 3),
        }
    return by_strategy
```

[固定提交链接 · L833–L848](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L833-L848)

四行指标 + 耗时，按 strategy 分桶。`sum(bool(...))` 是 Python 里"数 True"的惯用法。`elapsed_seconds` 是**三个任务耗时之和**——本节下面的"约 46 秒 / 约 47 秒"就是这个数。

注意它**不统计 token**——token 汇总在**学习版**的 `run()` 里（`token_usage` 字段），原版没有。原版只关心准确率/完成数/耗时。

### 2.21 `_history_chain_valid`（L851–866）：重算哈希链

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="851"
def _history_chain_valid(record: dict[str, Any]) -> bool:
    events = record.get("history_receipt", {}).get("events", [])
    prior = "0" * 64
    for sequence, row in enumerate(events):
        if row.get("sequence") != sequence:
            return False
        expected = sha256_bytes(
            f"{prior}:{row.get('role')}:{row.get('event')}:{row.get('turn')}:"
            f"{row.get('content_sha256')}".encode()
        )
        if row.get("chain_sha256") != expected:
            return False
        prior = expected
    return bool(events) and record.get("history_receipt", {}).get(
        "final_chain_sha256"
    ) == prior
```

[固定提交链接 · L851–L866](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L851-L866)

`append_history` 的镜像校验器，三件事：

1. **序号必须是 0,1,2,...**（`row["sequence"] != sequence` 即拒）——不允许缺号或乱序。
2. **每条链值必须等于用同样的公式重算的结果**。公式与 `append_history` 里**逐字符一致**（`prior:role:event:turn:content_hash`）。这是"两条独立代码路径算出同一个值"的交叉验证——一旦有人手工改过 `history` 里任何一条，链就断。
3. **最后一条的链值必须等于 `final_chain_sha256`**——这条把"收尾时记录的终值"也钉住。

`bool(events)` 保证空历史直接判 False。**注意它只验链，不验内容与 `messages` 是否一致**——即它证明"history 没被改"，但不证明"history 忠实反映了发给模型的内容"（后者靠 `content_sha256` 在生成时算出来，无法事后对比，属于设计边界）。

**被 `derive_acceptance` 调用**：treatment 的每一格都要过这一关，`treatment_discovery` 门禁才可能为真。

### 2.22 `_required_receipts_real`（L869–894）：每个槽位都要有"真收据"

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="869"
def _required_receipts_real(record: dict[str, Any], task: dict[str, Any]) -> bool:
    receipts = record.get("execution", {}).get("receipts", [])

    def valid(receipt: dict[str, Any]) -> bool:
        provenance = receipt.get("backend_provenance", {})
        return (
            receipt.get("success") is True
            and receipt.get("transport") == "mcp-stdio"
            and receipt.get("mcp_result_is_error") is False
            and bool(provenance.get("backend"))
            and provenance.get("origin") in {"live-api", "local-process"}
            and receipt.get("simulation_markers") == []
            and receipt.get("substantive_observation") is True
            and isinstance(receipt.get("payload"), dict)
            and receipt["payload"].get("success") is True
        )

    for slot in task["slots"]:
        if not any(receipt.get("tool") in slot and valid(receipt) for receipt in receipts):
            return False
    if task["id"] == "transformer_arxiv_download":
        downloads = [receipt for receipt in receipts
                     if receipt.get("tool") == "arxiv_download" and valid(receipt)]
        if len(downloads) != 3 or len({row.get("paper_id") for row in downloads}) != 3:
            return False
    return True
```

[固定提交链接 · L869–L894](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L869-L894)

内部的嵌套 `valid()`（L872–884）是**"真收据"的九项定义**，比 `mcp_receipt` 里的七项合取还多两项（`transport` 必须是 `mcp-stdio`、`payload` 必须是 dict 且 `payload.success` 为 True）：

```text
success is True                     ... 顶层真
transport == "mcp-stdio"            ... 走的是 MCP，不是别的通道
mcp_result_is_error is False        ... MCP 层没报错
provenance.backend 非空             ... 有后端
provenance.origin ∈ {live-api, local-process}   ... 来源合法
simulation_markers == []            ... 无 mock 嫌疑
substantive_observation is True     ... 有实质数据
payload 是 dict                     ... 结构完整
payload.success is True             ... 工具自己也说成了
```

注意 `receipt.get("success") is True` 用的是 **`is True`**（不是真值判断）——`1` 或 `"true"` 都不算，必须是 Python 的 `True`。这是刻意的严格。

外层逻辑：**每个槽位都必须存在至少一条"工具名属于该槽位且收据为真"的记录**；arXiv 任务额外要求 3 条 `arxiv_download` 真收据且 `paper_id` **互不相同**（`len({...}) != 3` 就是在查重）。这最后一条堵死了"同一个 PDF 下载三次冒充三个"的路径。

**它是 `derive_acceptance` 里 `real_execution` 门禁的实现**，也是"不夸大、不用 mock 顶替"这条主张的代码化。

### 2.23 `derive_acceptance`（L897–1046）：12 条门禁

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="1017"
    gates = {
        "exact_model_with_qwen_response_receipts": qwen_receipts,
        "catalog_from_mcp_and_hash_matches": (...),
        "tool_count_at_least_120": len(schemas) >= protocol["minimum_mcp_tools"],
        "control_over_50k_complete_schema_tokens": (
            catalog.get("schema_tokens_o200k", 0)
            > protocol["minimum_control_schema_tokens"] and full_control_catalog
        ),
        "three_tasks_each_group": exact_six,
        "real_mcp_execution_only": real_execution,
        "all_tasks_completed_with_required_artifacts": completed_with_artifacts,
        "treatment_discovery_history_and_status_verified": treatment_discovery,
        "identical_tasks_model_runtime_and_catalog": identical_runtime,
        "local_embedding_index_receipted": embedding_real,
        "dynamic_schema_injection_tokens_recorded": (
            len(dynamic_token_totals) == 3 and all(value > 0 for value in dynamic_token_totals)
        ),
        "comparison_metrics_present_for_both_arms": comparison_present,
    }
    return {"status": "passed" if all(gates.values()) else "failed", "gates": gates}
```

[固定提交链接 · L1017–L1046](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L1017-L1046)

`status` 是 `all(gates)`——**12 条全真才 passed，一条假就 failed**。逐条解释（后面括号里是实测/预期）：

| # | 门禁 | 含义 |
| --- | --- | --- |
| 1 | `exact_model_with_qwen_response_receipts` | 每一格的 `model`、`runtime.name/model` 都是 ollama/qwen3:4b，且每次调用的 `response_model == MODEL`、`done is True`、有 `request_hash`、内容非空（L911–924）。**证明答案真出自指定模型** |
| 2 | `catalog_from_mcp_and_hash_matches` | MCP transport、`tools_list_received`、`schema_sha256` 与当前重算一致、`tool_count == len(schemas)`、无重名、7 个必需工具齐全、gzip 字节数 > 0、gzip 哈希 64 位、gzip 解压内容哈希 == schema 哈希（L1019–1029）。**证明目录是真的从 MCP 拿的、且没被事后改过** |
| 3 | `tool_count_at_least_120` | `len(schemas) >= protocol.minimum_mcp_tools`（120） |
| 4 | `control_over_50k_complete_schema_tokens` | 目录 token > 50,000 **且** control 三格的 `initial_schema_names` 等于全部工具名、`system_prompt_tokens > 50000`（L986–990, L1031–1034）。**这一条同时证明"control 确实吞了全量 schema"** |
| 5 | `three_tasks_each_group` | 6 格恰好是 2 策略 × 3 任务，无重复（`exact_six`） |
| 6 | `real_mcp_execution_only` | 每格都过 `_required_receipts_real`（2.22）。**禁 mock** |
| 7 | `all_tasks_completed_with_required_artifacts` | 每格 `task_complete`、`agent_finished`、`final_answer` 非空（L931–936） |
| 8 | `treatment_discovery_history_and_status_verified` | treatment 三格：discoveries 与 schema_injection 事件一一对应、哈希链有效、初始工具名恰为三个、每次注入的 `top_k ∈[3,5]`、事件角色是 user、turn 对齐、`schema_names/count/sha256/tokens` 与重算一致、状态栏存在、`available_tools` 等于累计集合、动态 token 和等于各次之和（L938–983）。**这是最长的一条，等于把"注入过程"整体重演一遍** |
| 9 | `identical_tasks_model_runtime_and_catalog` | 六格同一 `catalog_sha256`、同一 `runtime`、同一 `model`、`prompt` 与任务定义逐字一致（L991–999）。**变量控制的证明** |
| 10 | `local_embedding_index_receipted` | 索引收据：模型名、后端名、`local_files_only`、`catalog_text_count == len(schemas)`、`vector_count == len(schemas)`、`vector_dimensions > 0`、有 texts 与 cache 哈希（L1007–1016）。**实测 127 向量 × 384 维通过** |
| 11 | `dynamic_schema_injection_tokens_recorded` | treatment 三格的动态注入 token 都 > 0（L1041–1043） |
| 12 | `comparison_metrics_present_for_both_arms` | `comparison` 恰好两臂、每臂含五个必需指标、`tasks == 3`（L1000–1006） |

**学习版把第 1 条换成了 `exact_model_with_deepseek_response_receipts`**（见第 4 节），其余 11 条原样复用。这就是"换模型"在门禁层的最小改动面。

**怎么读这张表**：门禁 2/3/4/10 管"实验材料是真的"，5/9 管"对照有效"，6/7 管"没造假"，8/11 管"treatment 机制真的跑了"，12 管"结果可比"。**没有一条门禁在管"结果好不好看"**——准确率高还是低都不影响 passed。这是这套验收设计最值得学的一点。

### 2.24 `build_manifest`（L1049–1057）：全目录哈希清单

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="1049"
def build_manifest(campaign_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(campaign_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        data = path.read_bytes()
        files.append({"path": str(path.relative_to(campaign_dir)), "bytes": len(data),
                      "sha256": sha256_bytes(data)})
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "files": files}
```

[固定提交链接 · L1049–L1057](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L1049-L1057)

递归哈希整个 campaign 目录的每个文件，**排除 `manifest.json` 自己**（否则自指：写 manifest 会改变 manifest 的哈希）。`sorted(rglob)` 保证顺序稳定。路径用 `relative_to(campaign_dir)` 存相对路径——**换机器后哈希仍可复算**（不用绝对路径，否则路径里的用户名会让清单不可移植）。

`generated_at` 用 UTC ISO 时间戳。这个文件是**整场战役的封条**：事后只要重跑 `build_manifest` 对比，就能知道有没有人动过任何一份收据、任何一张图、任何一个 PDF。

### 2.25 `run`（L1060–1200）：编排

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="1060"
async def run(campaign_id: str | None = None, *, resume: bool = False) -> Path:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    campaign_id = campaign_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    campaign_dir = VALIDATION_ROOT / campaign_id
    ...
    params = StdioServerParameters(command=sys.executable, args=[str(MCP_SERVER)], env=os.environ.copy())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialize = await session.initialize()
            listed = await session.list_tools()
            schemas = [schema_dict(tool) for tool in listed.tools]
```

[固定提交链接 · L1060–L1100](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L1060-L1100)

四个阶段的第一个：**起 MCP、拿目录**。

- `campaign_id` 默认是 UTC 时间戳——**每次跑一个新目录，不覆盖旧证据**。
- `StdioServerParameters(command=sys.executable, ...)`：用**当前 Python 解释器**拉起 `chapter4/perception-tools/src/main.py`，`env=os.environ.copy()` 把环境变量（API key 等）传给子进程。`stdio_client` 是 MCP 的**子进程传输**：通过 stdin/stdout 说 JSON-RPC。`async with` 保证退出时杀掉子进程。
- `session.initialize()` 拿 server 身份（`_server_info` 的两字段）；`session.list_tools()` 是**唯一一次目录获取**——127 个工具一次拿全（实测）。
- 接着 `catalog` 收据（L1103–1116）记 transport、server 路径、server 名与版本、`tool_count`、`unique_tool_count`、`schema_tokens_o200k`、`schema_bytes`、`schema_sha256`、7 个必需工具的存在表。

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="1117"
            if catalog["tool_count"] < protocol["minimum_mcp_tools"]:
                raise RuntimeError(f"MCP catalog too small: {catalog['tool_count']}")
            if catalog["schema_tokens_o200k"] <= protocol["minimum_control_schema_tokens"]:
                raise RuntimeError(f"control schema prompt too small: {catalog['schema_tokens_o200k']}")
            if not all(catalog["required_tools_present"].values()):
                raise RuntimeError("required task tools missing from MCP catalog")
```

[固定提交链接 · L1117–L1122](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L1117-L1122)

**三条前置断言，fail fast**：工具数不够 120、schema token 不够 50K、必需工具缺一个——任一不满足就**在花任何模型调用之前**直接崩。注意 `<=` 与 `> 50000` 的配合：`schema_tokens_o200k <= 50000` 才报错，即**必须严格大于 50,000**。学习版实测 50,597，刚过线。

中段（L1123–1173）：**gzip 存原始 schema + 索引收据**。`catalog.schemas.json.gz` 是 127 个 schema 原文的压缩包（保留原始目录，供事后复核）；resume 时会解压、重算哈希、与 preserved 收据逐字段比对，**任何一项不一致都拒绝续跑**。`LocalEmbeddingIndex` 用 `asyncio.to_thread` 跑——原因是它内部是同步的、CPU 密集的（要编码 127 条文本），丢到线程里才不会把事件循环卡死（MCP 会话还在同一循环上）。

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="1174"
            control = await run_group(
                session, schemas, index, "control", campaign_dir, resume=resume
            )
            treatment = await run_group(
                session, schemas, index, "treatment", campaign_dir, resume=resume
            )
            records = control + treatment
            comparison = safe_summary(records)
            acceptance = derive_acceptance(
                records, schemas, catalog, protocol, comparison, embedding_receipt
            )
            summary = {
                "experiment": "4-1", "campaign_id": campaign_id,
                ...
                "acceptance": acceptance,
                "status": acceptance["status"],
            }
            write_json(campaign_dir / "summary.json", summary)
    write_json(campaign_dir / "manifest.json", build_manifest(campaign_dir))
    return campaign_dir
```

[固定提交链接 · L1174–L1200](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L1174-L1200)

- 先 control 后 treatment，**串行**（共用 session）。
- `summary.json` 装：experiment/campaign_id/generated_at/model/catalog/embedding/comparison/`dynamic_schema_injection_tokens`（逐任务）/acceptance/status。
- **`manifest.json` 在 `with` 块之外写**——这是个易被忽略的细节：它的位置保证"manifest 是最后落盘的东西"，而且此时 MCP 子进程已经关闭（`async with` 已退出）。所以 manifest 覆盖的文件集是**封闭的**，不会有"manifest 写完后 MCP 又写了东西"的窗口。
- 返回 `campaign_dir` 给 `main` 打印。

### 2.26 `main`（L1203–1219）：入口

```python title="chapter4/active-tool-discovery/run_exact_experiment.py" linenums="1203"
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted campaign after validating all preserved setup receipts.",
    )
    args = parser.parse_args()
    if args.resume and not args.campaign_id:
        parser.error("--resume requires --campaign-id")
    path = asyncio.run(run(args.campaign_id, resume=args.resume))
    print(path)
```

[固定提交链接 · L1203–L1219](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-discovery/run_exact_experiment.py#L1203-L1219)

只有两个参数：`--campaign-id`（目录名）与 `--resume`。**`--resume` 必须配 `--campaign-id`**（否则你不知道续哪场），这条由 `parser.error` 强制。`description=__doc__` 让 `-h` 显示文件顶部那段 docstring（4-1 的契约说明）。`asyncio.run` 是唯一的事件循环入口，最后 `print(path)` 输出 campaign 目录。

---

## 3. 学习版注入了什么：`run_4_1_tool_discovery.py`

学习脚本 [run_4_1_tool_discovery.py](../assets/task4/run_4_1_tool_discovery.py)（约 625 行，与 `ai-agent-book/learning/task4/run_4_1_tool_discovery.py` 同一份）的设计原则写在 docstring 里：**import 课程模块，零改动复用 26 个函数**（L9–14 逐个列名），只重写四件事（L16–21）。下面逐条对照。

**(1) 聊天后端：`ollama_chat` → `deepseek_chat`（L93–127）**

```python title="learning/task4/run_4_1_tool_discovery.py" linenums="93"
async def deepseek_chat(messages: list[dict[str, str]], *, timeout: float = 900.0) -> dict:
    """课程 ollama_chat 的 DeepSeek 等价物：同样的返回形状，外加 usage 与缓存命中。"""
    request = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": RUNTIME["max_tokens"],
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    started = time.perf_counter()
    response = await _get_client().chat.completions.create(**request, timeout=timeout)
    latency = round(time.perf_counter() - started, 3)
    choice = response.choices[0]
    usage = response.usage
    extra = getattr(usage, "model_extra", None) or {}
    return {
        "response_model": response.model,
        "created_at": str(response.created),
        "done": choice.finish_reason is not None,
        "done_reason": choice.finish_reason,
        "content": choice.message.content or "",
        "thinking": "",
        "prompt_eval_count": getattr(usage, "prompt_tokens", None),
        "eval_count": getattr(usage, "completion_tokens", None),
        "total_duration_ns": int(latency * 1e9),
        "latency_seconds": latency,
        "request_hash": course.sha256_bytes(course.canonical_json(request).encode()),
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "prompt_cache_hit_tokens": extra.get("prompt_cache_hit_tokens"),
            "prompt_cache_miss_tokens": extra.get("prompt_cache_miss_tokens"),
        },
    }
```

[学习脚本原文 · L93–L127](../assets/task4/run_4_1_tool_discovery.py)（学习版脚本不在课程仓库里，指向本站随附的同一份副本）

要点：

- **协议字段全部对齐 `ollama_chat`**：`response_model` / `done` / `done_reason` / `content` / `prompt_eval_count` / `eval_count` / `total_duration_ns` / `request_hash` 一个不少。这样课程的门禁检查项可以照抄。
- `done = choice.finish_reason is not None`：OpenAI 兼容接口没有 `done` 布尔，用 `finish_reason` 是否为空来等价转换。注意 `finish_reason == "length"`（被 `max_tokens=1400` 截断）**也算 done=True**——这一点与课程原本的 `payload.done` 语义略有差别，属于学习版的一处近似。
- **`extra_body={"thinking": {"type": "disabled"}}`**：DeepSeek 的思考开关走请求体的额外字段，不在标准 OpenAI 参数里，所以必须用 `extra_body` 透传。`thinking` 字段在返回里被固定成空串 `""`（DeepSeek 关掉思考后不回思考内容）。
- **新增 `usage` 子字典**：`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` 从 `usage.model_extra` 里取（OpenAI SDK 把非标准字段塞进 `model_extra`）。这两个字段原版拿不到，是学习版能报告"102 万 prompt token 里 101 万命中缓存"的原因。
- `_get_client()`（L86–90）用一个模块级单例 `AsyncOpenAI`——**避免每次调用重建 HTTP 连接池**，这是 46 秒跑完 6 个任务的基础。
- `deepseek_chat` 签名与 `ollama_chat` 完全一致（`messages` + 关键字 `timeout`），所以 `run_agent_task` 里换掉调用点即可，其余逻辑一字不改。

**(2) 系统提示词横幅：`Qwen3-4B` → `DeepSeek`（L133–145）**

`run_agent_task` 被重写为同构版本，两处横幅从 `"You are Qwen3-4B in the full-schema control."` 改成 `f"You are {LEARNING_BANNER} in the..."`（`LEARNING_BANNER = "DeepSeek"`，L69）。**对照组/实验组的横幅同步改写**，保持"唯一差异是策略"这一约束。除此之外，`run_agent_task` 的循环体（12 轮、finish 被拒、discover 注入、`_call_real_tool`）与课程**逐行同构**——学习版把它整个复制过来而不是猴子补丁，为的是让 diff 一眼可读。

**(3) 门禁：qwen → deepseek（L310–324, L414）**

```python title="learning/task4/run_4_1_tool_discovery.py" linenums="310"
    deepseek_receipts = bool(records) and all(
        row.get("model") == MODEL
        and row.get("runtime", {}).get("name") == RUNTIME["name"]
        and row.get("runtime", {}).get("model") == MODEL
        and bool(row.get("interactions"))
        and all(
            interaction.get("response", {}).get("response_model") == MODEL
            and interaction.get("response", {}).get("done") is True
            and bool(interaction.get("response", {}).get("request_hash"))
            and bool(interaction.get("response", {}).get("content", "").strip())
            and (interaction.get("response", {}).get("usage") or {}).get("prompt_tokens")
            for interaction in row.get("interactions", [])
        )
        for row in records
    )
```

[学习脚本原文 · L310–L324](../assets/task4/run_4_1_tool_discovery.py)

与课程版本的差别只有三处：`MODEL` 常量变成 `"deepseek-flash"`；`runtime.name` 从 `"ollama"` 换成 `"deepseek-openai-compatible"`；**多了一项 `usage.prompt_tokens` 必须非空**（最后一行）——这一条把"回执里必须带 usage"变成了硬门禁，堵住"后端不返回 usage 也能过"的路。门禁键名相应改为 `exact_model_with_deepseek_response_receipts`（L414）。**其余 11 条门禁的代码在 L415–441 与课程逐字相同**。

**(4) `VALIDATION_ROOT` 重定向（L79–80）**

```python
OUT_ROOT = ROOT / "learning/task4/runs/4-1_active_tool_discovery"
OUT = OUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
```

学习版**完全不复用** `course.VALIDATION_ROOT`，`run()` 被重写成直接用 `OUT`（L448–449 的 `OUT.mkdir(parents=True, exist_ok=False)`），所以 `chapter4/.../validation/` 里的课程原始证据**一行都不被触碰**。同时学习版**去掉了 resume 逻辑**（`run_group` 与 `run` 都没有 `--resume`），因为每次都是新时间戳目录、没有续跑需求。这是"机制复用、证据隔离"的落地方式。

**(5) `TIKTOKEN_CACHE_DIR` 为什么必须固定（L59–61）**

```python title="learning/task4/run_4_1_tool_discovery.py" linenums="59"
# 课程用 tiktoken o200k_base 统计 schema token；该编码首次使用要从境外拉 3.6MB BPE 文件
# （本机实测 151 秒，看起来像卡死）。先把缓存固定到仓库内，避免每次重跑都重新下载。
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(Path(__file__).resolve().parent / ".cache/tiktoken"))
```

这是**本任务踩过的最实际的一个坑**，值得理解机理而不只是抄结论：

- `count_tokens` 用 `tiktoken.get_encoding("o200k_base")`。tiktoken 的编码数据**不随包分发**，首次调用时会去 `openaipublic.blob.core.windows.net` 下载一个约 **3.6 MB** 的 BPE 词表文件（"151 秒"这个数字来自学习脚本 L60 的注释，是作者在本机的记录，我未重新计时）。
- 默认缓存位置由 tiktoken 自己决定（通常是系统临时目录）。如果**每次运行都在一个新环境**，或者系统清理了临时目录，这笔 3.6 MB / 151 秒的下载就会**每次重付**。更糟的是它发生在 `run()` 的早期（`count_tokens(schema_text)` 计算 catalog 时），看起来像**程序卡死**而不是"在下载"——没有进度条、没有日志。
- `TIKTOKEN_CACHE_DIR` 是 tiktoken 认的官方环境变量。把它固定到 `<repo>/learning/task4/.cache/tiktoken` 后，**首次之后所有运行都命中本地缓存**，`count_tokens` 变成纯本地 CPU 操作。
- 必须放在 `import run_exact_experiment` **之前**（L61 在 L65 之前）——因为 `count_tokens` 是模块级函数的第一次真正调用在 `run()` 里，但环境变量必须在 tiktoken 首次实际 `get_encoding` 前设置才生效。用 `setdefault` 而不是直接赋值，是为了让已有外部配置仍能覆盖它。
- 实测这个缓存目录里有两个文件（`9b5ad71b...`、`fb374d41...`，各约 1–4 MB）——o200k_base 的词表与正则数据。

**(6) 额外的证据层 `write_evidence()`（L557–602）**：学习版多写两个文件 `evidence.json` / `evidence.sha256`，内容包括运行目录、源文件哈希（`run_exact_experiment.py`、`experiment_protocol.json`、`perception-tools/src/main.py`、学习脚本自身）、credential 扫描结果（确认 API key 没漏进任何落盘文件，L560–563），以及 `completed = status == "passed" and not leak`。`assert DEEPSEEK_KEY not in payload`（L598）是最后一道自检。这是学习版对"证据链"的加强，课程原版没有。

---

## 4. 完整执行回放（学习版一次真实运行）

以下数字全部来自实测运行 `learning/task4/runs/4-1_active_tool_discovery/20260921T112402Z/`（本机运行目录，未随站点发布）（`summary.json` 与六个 `receipt.json`）。**标注 [实测] 的是文件里的值，[推断] 的是我读代码得出的解释。**

```text
main() → asyncio.run(run())
 ├─ catalog: MCP tools/list 返回 127 个工具（57 原生 + 70 扩展）      [实测]
 │    └─ count_tokens(render_schemas) = 50,597（o200k_base），208,614 字节  [实测]
 ├─ 断言通过（127 ≥ 120，50,597 > 50,000，7 个必需工具齐全）        [实测]
 ├─ catalog.schemas.json.gz + catalog_receipt.json 落盘
 ├─ LocalEmbeddingIndex: 127 向量 × 384 维（all-MiniLM-L6-v2，cpu）  [实测]
 │    └─ embedding_receipt.json 落盘（cache_sha256 入收据）
 ├─ run_group("control")  ← 串行 3 题
 │    ├─ 每题 system prompt = 50,825 token（全量 127 schema）        [实测]
 │    ├─ apple_stock_news:                  3 轮  准确率 1.0  完成  [实测]
 │    │    选 stock_price + search_news
 │    ├─ transformer_arxiv_download:        3 轮  准确率 1.0  完成  [实测]
 │    │    选 arxiv_search + arxiv_download（3 个 PDF 全落盘）
 │    └─ github_contributors_visualization: 12 轮 准确率 1.0  未完成 [实测]
 │         槽位选对（github_list_contributors + code_interpreter），
 │         但 api.github.com 全程 403 rate limit exceeded（未认证 60 次/小时），
 │         于是不断换 github_* 工具重试 → 12 轮耗尽、无 finish
 │         → agent_finished=False（环境限流，非模型问题）
 ├─ run_group("treatment")  ← 串行 3 题
 │    ├─ 每题 system prompt = 1,247 token（只有 3 个工具）           [实测]
 │    ├─ apple_stock_news:                  12 轮 准确率 1.0  完成  [实测]
 │    │    discover("authoritative real-time stock market quote…")
 │    │      → top5: yfinance_quote(0.496) finance_market_index(0.489)
 │    │             finance_market_summary(0.476) stock_price(0.403)
 │    │             yfinance_historical(0.388)          ← 命中 yfinance_quote
 │    ├─ transformer_arxiv_download:        12 轮 准确率 0.5  未完成 [实测]
 │    │    discover("search arXiv for academic papers…") → arxiv_search ✓
 │    │    discover("download a PDF file from a URL to local storage")
 │    │      → top5: download(0.760) pdf_metadata(0.360)
 │    │             pdf_page_text(0.324) document_reader(0.320)
 │    │             pdf_extract(0.313)   ← 没有 arxiv_download，失败起点
 │    │    随后 6 次调用 download 全部校验失败，轮数耗尽
 │    └─ github_contributors_visualization: 7 轮  准确率 1.0  完成  [实测]
 │         discover("GitHub repository contributor statistics…")
 │           → github_list_contributors(0.636) ✓（一轮就中）
 ├─ safe_summary → comparison                                    [实测]
 │    control:   accuracy 1.00  all_caps 3/3  complete 2/3   45.6s
 │    treatment: accuracy 0.83  all_caps 2/3  complete 2/3   46.7s
 ├─ derive_acceptance → 12 条门禁：10 真 2 假 → status "failed"   [实测]
 │    ✗ real_mcp_execution_only            （treatment arxiv 缺 arxiv_download 真收据）
 │    ✗ all_tasks_completed_with_required_artifacts（两格未完成）
 ├─ 动态注入 token：1,928 / 3,884 / 2,623                            [实测]
 ├─ token 用量                                                     [实测]
 │    control:   prompt 1,021,060（缓存命中 1,011,072）+ completion 1,273
 │    treatment: prompt   169,869（缓存命中   161,020）+ completion 3,590
 └─ summary.json + manifest.json 落盘
```

### 4.1 两臂的数字对比

| 指标 | control（全量注入） | treatment（主动发现） | 比值 |
| --- | --- | --- | --- |
| system prompt token | 50,825 | 1,247 | 40.8 倍 |
| 工具选择准确率 | 1.00 | 0.83 | — |
| 全槽位命中任务数 | 3/3 | 2/3 | — |
| 完成任务数 | 2/3 | 2/3 | — |
| 三题总耗时 | 45.6 s | 46.7 s | 1.02 倍 |
| 累计 prompt token | 1,021,060 | 169,869 | **6.0 倍** |
| 其中缓存命中 | 1,011,072 | 161,020 | 6.3 倍 |
| 缓存命中率 | 99.0% | 94.8% | — |
| 单题最多轮数 | 12（github 题） | 12（arxiv 题） | — |

**这张表最重要的一行是 prompt token 的 6 倍差，而不是准确率。**对 deepseek-flash 这个量级的模型，50K 全量 schema 与 1.2K 精简 schema **都不足以让它的工具选择退化到 0.83 以下**——control 组甚至因为"一次看全目录"而在准确率上略占优（1.00 vs 0.83）。主动发现的收益体现在**上下文成本**：每轮少发 4.9 万 token。而 99% 的缓存命中率说明：在**重复多轮**的 agent 循环里，全量 schema 的边际成本被 prompt 缓存大幅摊薄——这是"全量注入"在工程上真实存在、不能只算峰值 token 的原因。

**必须诚实说明的两条边界**（都会影响上面这张表的读法）：

**边界一：`control 完成 2/3` 不是模型能力问题，而是 GitHub API 限流。** control 组的 `github_contributors_visualization` 12 轮里调用的每一个 github 工具都返回 [实测]：

```json
{"success": false, "backend": "github", "error_type": "HTTPStatusError",
 "error": "Client error '403 rate limit exceeded' for url 'https://api.github.com/repos/openai/openai-python/contributors..."}
```

未认证的 `api.github.com` 限额是 **60 次/小时**，而三个任务串行跑、每格都可能多次重试，配额很容易被打光。模型的行为其实**完全正确**：`github_list_contributors` 选对了、失败了就换 `github_get_repository` / `github_list_commits` / `github_get_languages` / `github_list_pull_requests` / `github_get_releases` / `github_get_topics` / `github_search_repositories` 一路试过去（这些都在同一个槽位集合里），最后还试了 `webpage_reader` 与 `code_interpreter`——**它是在同一个能力槽位内做穷举重试**，不是乱选。但 `_finalize_execution` 要求"有一条 `success is True` 的收据"，403 下一条都拿不到，所以 finish 永远被拒，直到轮数耗尽。**这一格应当读作"环境限流导致的未完成"，而不是"模型选错了工具"**（它的准确率的确是 1.0）。

**边界二：学习版只跑了一次，且三次留证运行里限流的影响是不对称的。** 站点证据页 ([evidence.md#4-1](evidence.md#4-1)) 保留了三次 4-1 运行，各自的完成数并不一致 [实测]：

| 运行 | control 完成 | treatment 完成 | 备注 |
| --- | ---: | ---: | --- |
| `20260921T111856Z` | 2/3 | 1/3 | 首轮：两臂 GitHub 题均 403 |
| `20260921T112134Z` | 2/3 | 2/3 | 次轮：treatment GitHub 题仍 403，arXiv 题检索错配 |
| `20260921T112402Z` | 2/3 | 2/3 | 第三轮：treatment GitHub 题拿到配额完成，control 仍 403 |

三格里 **control 全部是 2/3、且都是同一格（GitHub）失败**——这是限流稳定命中 control 的直接证据。所以本页第 4.1 节那张表应读作**一次运行的观测值**，而"0.83 vs 1.00 差 1/3 个槽位"**不构成任何统计结论**：样本是 1，且失败原因里混着环境限流与检索错配两种不同性质的因素。[推断]

同理 `status` 是 `failed`（门禁 6 `real_mcp_execution_only`、7 `all_tasks_completed_with_required_artifacts` 未过）——**这是一场"机制验证通过、任务完成度未达标"的运行**：12 条门禁里管"材料是真的"（2/3/4/10）、"对照有效"（5/9）、"treatment 机制真的跑了"（8/11）的 10 条全真，说明机制本身工作正常；未过的两条都指向"有格子没完成"，而没完成的原因已如上拆开。用它来说明机制成立是可靠的，用它来比较两种策略的优劣则样本严重不足。

### 4.2 treatment 的真实失败模式：检索质量决定上限

这是本节最值得记住的部分。treatment 组 `transformer_arxiv_download` 的 12 轮轨迹 [实测]：

```text
turn  1  discover_tools need="search arXiv for academic papers by topic and
                            retrieve paper metadata such as titles, authors, and IDs"
         → arxiv_search, arxiv_paper_details, crossref_search,
           academic_citation_search, academic_latest_papers        ← 命中，arxiv_search 可用
turn  2  call_tool arxiv_search （max_results=5）                 ← 成功
turn  3  call_tool arxiv_search  （换了 query）
turn  4  call_tool arxiv_search  （又换 query）                   ← 三次搜索，凭经验在重试
turn  5  discover_tools need="download a PDF file from a URL to local storage"
         → download, pdf_metadata, pdf_page_text,
           document_reader, pdf_extract                          ← arxiv_download 不在 top-5
turn  6  call_tool download  {output_path:"/tmp/arxiv_2609.22078v1.pdf"}
turn  7  call_tool download  {url:..., output_path:"/tmp/..."}   ← 补上 url 再试
turn  8  call_tool download  {url:..., output_path:"arxiv_...pdf"} ← 换相对路径再试
turn  9  call_tool download  {url:..., output_path:"/tmp/..."}   ← 再试
turn 10  call_tool download  {url:".../2609.22078"}              ← 去掉 v1 再试
turn 11  call_tool download  {url:...}                           ← 再试
turn 12  call_tool document_reader {file_path:"https://..."}      ← 换工具，同样校验失败，轮数到此为止
         （无 finish → final_answer="" → agent_finished=False → 未完成）
```

三层原因，从表到里：

**第一层（表层）：模型选错了工具。** `need` 的措辞是 "download a PDF file from a URL to local storage"——通用下载语义。检索结果 top-1 是 `download`（见下方实测），而 `arxiv_download` **根本没进 top-5**。

我在本机对该 need 复算了完整排序 [实测]：

```text
rank  1  download          score 0.760466
rank  4  document_reader   score 0.319947
rank  5  pdf_extract       score 0.312827
rank 16  webpage_reader    score 0.256944
rank 22  arxiv_download    score 0.197894      ← 125 个里的第 22 位
```

而如果 `need` 里出现 "arxiv" 这个词，结果立刻反转 [实测]：

```text
"download arxiv paper PDF"        → arxiv_download 0.895773 排第 1
"download the top three arXiv PDFs" → arxiv_download 0.773745 排第 1
"arxiv download paper pdf file"   → arxiv_download 0.812331 排第 1
```

**根因在 `LocalEmbeddingIndex._text`**（2.4）：索引文本是 `"name: 描述首段"`，即 `download: Download a file from a URL to local storage.` 与 `arxiv_download: Download ArXiv paper PDF.`。前者是"从 URL 下载文件"的**教科书式表述**，正是模型写出那句话的原型；后者短、且"ArXiv"这个区分词在句子里的权重不足以拉住一个不含 arxiv 的 query。**这是嵌入检索的固有性质，不是 bug**——但它说明了主动发现的**上限由检索质量决定**：模型必须"猜中检索器认的词"才能拿到对的工具。

**第二层（机制层）：`_call_real_tool` 无法给 `download` 传参。** `download` 的 schema 是 `props: ['url','output_path','overwrite','timeout']`——**顶层参数**。而 `_call_real_tool` 的分支白名单只覆盖 4 个工具，`download` 落进最后的 `else`，被装箱成 `{"query": url, "options_json": "{...}"}`（2.16）。收据 [实测]：

```json
{"success": false,
 "payload": {"success": false,
             "error": "MCP result was not JSON",
             "raw": "Error executing tool download: 2 validation errors for downloadArguments\nurl\n  Field required ...\noutput_path\n  Field required ..."}}
```

**所以模型把 `url` 和 `output_path` 放进 `options` 里是完全正确的直觉，但运行时把它们塞进了 `options_json`，永远到不了 `url`/`output_path` 这两个顶层字段。**这 6 次调用**在结构上不可能成功**——与模型的参数填法无关。这是本实验里一个**编排器适配能力**的限制，而不是模型能力的失败（**这是[推断]，依据是收据里的 pydantic 字段名与 `_call_real_tool` 的 `else` 分支装箱方式完全对应**）。读源码到这里应当得出这个区分，否则会把责任错误地记在模型头上。

同一题的最后一轮还提供了一个**同款证据**：turn 12 模型换成 `document_reader`（它的 schema 是 `props: ['file_path','extract_images']`），也同样落进 `else` 分支被装箱成 `{"query":..., "options_json":...}`，收据 [实测] 是同一种 pydantic 错误——`document_readerArguments\nfile_path\n  Field required`。**两个不同工具、同一个失败签名**，把根因唯一地指向适配器的装箱方式（`_call_real_tool` 只特判了 4 个工具），而不是模型的参数选择。这也解释了为什么这个失败模式**不可自愈**：模型无论怎么改 `options` 里的键，运行时都不会把它们提升为顶层参数。

**第三层（轮数层）：12 轮上限放大了代价。** 6 次失败调用 + 3 次 arxiv 搜索重试 + 2 次 discover = 11 轮，第 12 轮才想到换 `document_reader`，然后循环结束。**没有任何一轮被用于"退回去重新 discover"**——这既因为协议没提示"工具连续失败时应当重新表述 need"，也因为轮数不够。对照组同一题只用了 3 轮 [实测]，因为它一眼就看到了 `arxiv_download`。

**这三点合起来就是"主动发现的上限由检索质量决定"的直接证据**：模型足够强（同一模型在另两题都拿到 1.0），机制也真的在跑（discover 调用、注入、门禁 8 全过），但**一次检索把通用工具排在专家工具之前，就足以让一整题失败**。这也解释了为什么 treatment 组 `github_contributors_visualization` 只用了 7 轮就完成 [实测]——那个 need 里的 "GitHub repository contributor statistics" 恰好与 `github_list_contributors` 的描述高度重合，检索一次命中。

### 4.3 与课程原版 qwen3:4b 的对照（课程仓库留存的实测数字）

课程仓库里保留了三个 qwen3:4b 战役。**这不是本学习版跑出来的**，列在这里只作参照，避免读者以为原版也是这些数 [实测，来自 `chapter4/active-tool-discovery/validation/experiment_4_1/`]：

| 战役 | 工具数 | schema token | control 准确率/完成/耗时 | treatment 准确率/完成/耗时 | status |
| --- | --- | --- | --- | --- | --- |
| `qwen3_4b_exact_20260730T061700Z` | 126 | 50,120 | 1.00 / 3/3 / 2383 s | 0.67 / 1/3 / 814 s | failed |
| `qwen3_4b_exact_v2_20260730T130600Z` | 126 | 50,120 | 1.00 / 3/3 / 2591 s | 1.00 / 3/3 / 809 s | passed |
| `rerun_20260825` | 127 | 50,597 | 1.00 / 3/3 / 3056 s | 1.00 / 3/3 / 783 s | passed |

两点诚实观察：

1. **两场通过的原版战役里，treatment 的准确率也是 1.00。**所以"50K 全量 schema 让小模型指令遵循退化"这一说法，在仓库留存的 v2 与 rerun 里**并没有表现为准确率下降**；真实差异是**耗时**——control 2383–3056 s vs treatment 783–814 s（**约 3–4 倍**）。第一个战役（061700Z）treatment 只有 0.67 且动态注入 token 有两题为 0（`apple_stock_news` 与 `github_contributors_visualization` 都是 0）——即那一场 treatment 压根没正常调用 discover，门禁 `treatment_discovery_history_and_status_verified` 判假。**第一个战役是一次失败的运行，不是"小模型退化"的证据。**
2. **工具数从 126 变成 127**（`rerun_20260825` 起）。本学习版用的是 127——即与 rerun 同批的 perception MCP。

因此本页只把教材的原始主张记为"教材陈述"，把上表的数字记为"仓库留存实测"。**两者在通过的那两场里并不吻合**，读者引用时应注意区分。[推断：可能教材描述的退化体现在更早的、未入库的战役里，或体现在非准确率指标（如耗时、轮数）上；仓库留存的证据不足以支持"准确率退化"这一表述。]

---

## 5. 动手验证（三个离线小实验）

以下命令都在仓库根目录 `/Users/tal/Documents/Codex/learning-projects/ai-agent-book` 下执行，用的是本仓库已有的 `.venv`。三个实验**全部离线**，不花任何 API 额度。

**实验一：复算 50,597 这个门禁数字**

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-agent-book
TIKTOKEN_CACHE_DIR=learning/task4/.cache/tiktoken .venv/bin/python - <<'PY'
import gzip, json, sys
sys.path.insert(0, "chapter4/active-tool-discovery")
import run_exact_experiment as c
schemas = json.load(gzip.open(
    "learning/task4/runs/4-1_active_tool_discovery/20260921T112402Z/catalog.schemas.json.gz", "rt"))
print("tools =", len(schemas))
print("schema_tokens_o200k =", c.count_tokens(c.render_schemas(schemas)))
print("names unique =", len({s["name"] for s in schemas}))
PY
```

预期输出 [实测]：

```text
tools = 127
schema_tokens_o200k = 50597
names unique = 127
```

`50,597 > 50,000`——门禁 `control_over_50k_complete_schema_tokens` 只过线 597 个 token。**注意 `TIKTOKEN_CACHE_DIR`**：不设它的话你会先在 `get_encoding` 那里等约 151 秒下载 3.6 MB 词表（第 3 节第 5 点）。**这个实验不需要 torch/transformers，是三个里最快的一个**（用了缓存后 1 秒内出结果）。

**实验二：复现"通用 download 击败 arxiv_download"的检索事故**

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-agent-book
TIKTOKEN_CACHE_DIR=learning/task4/.cache/tiktoken .venv/bin/python - <<'PY'
import gzip, json, sys
from pathlib import Path
sys.path.insert(0, "chapter4/active-tool-discovery")
import run_exact_experiment as c

run = Path("learning/task4/runs/4-1_active_tool_discovery/20260921T112402Z")
schemas = json.load(gzip.open(run / "catalog.schemas.json.gz", "rt"))
index = c.LocalEmbeddingIndex(schemas, run / "index")   # 命中已有向量缓存，不重算

print("向量数 × 维度 =", len(index.vectors), "×", len(index.vectors[0]))

for need in ["download a PDF file from a URL to local storage",   # 模型真实用过的措辞
             "download arxiv paper PDF",                          # 补上 arxiv 一词
             "download the top three arXiv PDFs"]:
    hits = index.search(need, 5)
    print(f"\nneed = {need!r}")
    for rank, hit in enumerate(hits, 1):
        print(f"  {rank}. {hit['schema']['name']:<26} {hit['score']:.6f}")

# 单独看 arxiv_download 的真实名次
need = "download a PDF file from a URL to local storage"
q = index._embed([need])[0]
ranked = sorted(((index._cosine(q, v), s["name"])
                 for v, s in zip(index.vectors, index.schemas)
                 if s["name"] not in c.BASE_TOOL_NAMES), reverse=True)
for rank, (score, name) in enumerate(ranked, 1):
    if name in ("download", "arxiv_download"):
        print(f"\n全排序: {name} 第 {rank} 位 / 共 {len(ranked)} 个，score {score:.6f}")
PY
```

预期输出 [实测]（节选）：

```text
向量数 × 维度 = 127 × 384

need = 'download a PDF file from a URL to local storage'
  1. download                   0.760466
  2. pdf_metadata               0.360096
  3. pdf_page_text              0.323576
  ...
  （arxiv_download 不在前 5）

need = 'download arxiv paper PDF'
  1. arxiv_download             0.895773
  ...

全排序: download 第 1 位 / 共 125 个，score 0.760466
全排序: arxiv_download 第 22 位 / 共 125 个，score 0.197894
```

**这个实验是全部三个里信息量最大的**：同一份索引、同一个 need 措辞，只因为加了一个词 "arxiv"，top-1 就从 `download` 变成 `arxiv_download`。它把 4.2 节的结论从"读代码推断"变成"可亲手复现的现象"。

首次运行会打印 `Loading weights: 100%`（加载 MiniLM，约 1 秒，从本机 HF 缓存读）；**如果它开始下载模型，说明你的 HuggingFace 缓存里没有 MiniLM**——那会中断本实验，因为 `local_files_only=True` 不会静默下载（这正是它的设计意图）。

**实验三：跑书籍自带的离线机制演示**

```bash
cd /Users/tal/Documents/Codex/learning-projects/ai-agent-book
.venv/bin/python chapter4/active-tool-discovery/demo.py --offline --tool-set-size 20
```

预期输出末尾的汇总表 [实测]：

```text
============================================================================================
汇总对比（『精确选对』= 覆盖全部能力槽位 且 未错选通用兜底工具）
============================================================================================
策略                  精确选对      任务完成       平均注入token      总注入token     平均延迟(s)
--------------------------------------------------------------------------------------------
全量注入               8/8       8/8            2808         22464       0.002
检索预筛选              6/8       6/8            1074          8589       0.002
主动发现               8/8       8/8             980          7842       0.003
--------------------------------------------------------------------------------------------
注入 token：全量注入 22464 vs 主动发现 7842，平均每任务精简约 2.9 倍。
```

**必须分清它与本页主体的关系**（否则会得出错误结论）：

- `demo.py` 是**另一个程序**，不是 `run_exact_experiment.py`。它**不连真实 MCP**、不判真实执行，用的是 `offline_backend.py` 里的 `LocalEmbedder`（本地哈希词袋）与 `MockChatClient`（按关键词匹配的假模型）。
- 它的三种策略多了一个"检索预筛选"（预先把 top-10 塞进 system prompt）——本页实验只有两种。
- 它的 8 个任务里有**诱导性题库**（输出里 "academic(诱导)" 那一题就是），"检索预筛选"策略在这题上漏掉了 `arxiv_search` 而得 0/1——这与 4.2 节 `download` 的事故是**同一类现象**（通用检索把专家工具挤掉），但发生在完全不同的代码里。
- 所以：**demo.py 能让你 5 秒内亲眼看到"检索质量决定发现上限"这个模式，但它给出的 token 数字（22464 vs 7842）与真实实验无关，不能与第 4 节的 1,021,060 / 169,869 混用。**

---

## 一页速记

- **两支唯一的差异**在 `run_agent_task` 的 `strategy` 分支：system prompt 是 127 个 schema（50,825 token）还是 3 个 schema（1,247 token）。
- **treatment 的"发现"只有一条路径**：`parse_action` → `LocalEmbeddingIndex.search` → `append_history(role="user", event="schema_injection")` → `available.update(names)`。注入消息**永不移动、永不删除**，所以 token 成本是长期的。
- **收据体系三层自证**：`mcp_receipt`（单次调用七项合取）→ `append_history` 哈希链（轨迹不可改）→ `derive_acceptance` 12 条门禁（材料/对照/机制/可比性各管一摊），最后 `build_manifest` 给整目录封条。
- **"内容不可作证"** 落在 `mcp_receipt` 那四行注释上：远端正文可能正常讨论 mock/simulated，所以只扫 control-plane 字段。
- **上限由检索决定**：模型很强（另两题准确率 1.0）也会因为一次检索把 `download` 排在 `arxiv_download` 之前而整题失败——而且 `_call_real_tool` 的通用装箱（`query` + `options_json`）让 `download` 的调用**结构上不可能成功**。
- **学习版的四件事**：换 `deepseek_chat`（`extra_body` 关 thinking、回执带 usage/缓存字段）、横幅改 DeepSeek、门禁第 1 条换名字并加 usage 检查、`VALIDATION_ROOT` 重定向到 `learning/task4/runs/`。外加一个必须记住的运维细节：`TIKTOKEN_CACHE_DIR` 固定，否则首次白等 151 秒。
