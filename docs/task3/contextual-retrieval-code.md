# 上下文感知检索源码精读 · campaign.py 逐函数通读

[实验说明](contextual-retrieval.md) · [实测结果](evidence.md#contextual-retrieval) · [学习运行脚本](../assets/task3/run_contextual_retrieval.py)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>本页按源码顺序把 contextual-retrieval/campaign.py 的每个函数过一遍——本地编码器、语料装载、前缀生成、三种排序、指标、验收与 main 的编排，一个不漏。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号（chapter3/contextual-retrieval/campaign.py）；**学习运行脚本原文**来自 `run_contextual_retrieval.py`；**教学示意**仅用于理解数据形状。

**主文件**：[chapter3/contextual-retrieval/campaign.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/contextual-retrieval/campaign.py)（284 行）。依赖两个外部件：`experiment_utils`（全章共享的 ChatRecorder/证据落盘，见[记忆实验的讲解](memory-modes-code.md)第 14/19 节）和同目录 `compare_retrieval.tokenize`（BM25 的中文分词，本页只当黑盒用）。

---

## 0. 函数清单（一个不漏）

| # | 函数/常量 | 行号 | 一句话作用 | 谁调用它 |
| --- | --- | --- | --- | --- |
| — | `HERE` / `CHAPTER` | L20–21 | 本目录 / chapter3 根 | 全文件 |
| — | `ARK_ENDPOINT` | L29 | 前缀 LLM 默认端点 | `main` |
| 1 | `TransformerEncoder.__init__` | L33–42 | 装载本地 HF 编码模型，记 revision | `main` |
| 2 | `TransformerEncoder.encode` | L44–55 | 文本 → 归一化句向量（query 侧加指令前缀） | `main` ×3 |
| 3 | `load_chunks` | L57–72 | document_store.json → chunk 列表 | `main` |
| 4 | `source_documents` | L74–84 | 每个 chunk 找到唯一源文档全文 | `main` |
| 5 | `prefix_one` | L86–111 | 一个 chunk 的 LLM 前缀生成（整份文档 + 目标块） | 线程池（main） |
| 6 | `rankings_bm25` | L113–116 | BM25 排序（每个查询对全部文本） | `main` |
| 7 | `rankings_dense` | L118–120 | 向量点积排序 | `main` |
| 8 | `rrf` | L122–128 | 两套排序的倒数排名融合 | `main` |
| 9 | `metrics` | L130–152 | 排序 → recall@1/3/5 + MRR | `main` |
| 10 | `token_usage` | L154–161 | 回执 → token 合计 | `main` |
| 11 | `main` | L163–284 | 编排：装载→并发前缀→六套排序→验收→落证据 | 入口 |

---

## 1–2. `TransformerEncoder`（L32–55）：本地编码器

```python linenums="33"
class TransformerEncoder:
    def __init__(self, model_name: str, device: str):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.model_name = model_name
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="left")
        self.model = AutoModel.from_pretrained(model_name).to(device).eval()
        self.revision = getattr(self.model.config, "_commit_hash", None)

    def encode(self, texts: Sequence[str], *, query: bool, batch_size: int = 8) -> np.ndarray:
        prefix = "Instruct: Retrieve semantically relevant passages.\nQuery:" if query else ""
        vectors = []
        for start in range(0, len(texts), batch_size):
            batch = [prefix + text for text in texts[start : start + batch_size]]
            tokens = self.tokenizer(batch, padding=True, truncation=True, max_length=512, return_tensors="pt").to(self.device)
            with self.torch.no_grad():
                output = self.model(**tokens).last_hidden_state[:, -1].float()
            output = self.torch.nn.functional.normalize(output, p=2, dim=1)
            vectors.append(output.cpu().numpy())
        return np.concatenate(vectors).astype("float32")
```

`import torch` 放在 `__init__` 里而不是文件头——**torch 是可选依赖**：只用 BM25 的场景不必装 2GB 的栈。四个细节全是 Qwen3-Embedding 的官方用法，不是通用写法：

- `padding_side="left"`（左填充）配合 `last_hidden_state[:, -1]`（取最后一个 token）：保证"最后一个 token"是真实文本末尾而非填充符。右填充时取 `[:, -1]` 拿到的是 padding 的表示，向量全废；
- `query=True` 时加 `Instruct: ... Query:` 前缀、文档侧裸文本：Qwen3-Embedding 是指令感知检索模型；
- `normalize(p=2)` 后点积 = 余弦相似度——`rankings_dense` 里直接矩阵乘的前提；
- `self.revision` 记录 HF 模型 commit 哈希，验收门槛 `real_dense_model` 检查它非空——"用了真模型"要有版本号背书（与 [task2 回执校验](../task2/kv-cache-code.md)同一思路）。

本实验三次调用：plain 文档 22 段、contextual 文档 22 段、查询 15 条（学习版 CPU 实测共 408 秒）。

---

## 3. `load_chunks`（L57–72）：语料入口

```python linenums="57"
def load_chunks(path: Path) -> List[Dict[str, Any]]:
    store = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for chunk_id, entry in store.items():
        if "_chunk_" not in chunk_id:
            continue
        meta = entry.get("metadata") or {}
        rows.append(
            {
                "chunk_id": chunk_id,
                "doc_title": meta.get("doc_title") or chunk_id.split("_chunk_")[0],
                "plain": meta.get("original_text") or entry.get("content", ""),
            }
        )
    return sorted(rows, key=lambda row: row["chunk_id"])
```

document_store.json 是 `{chunk_id: {content, metadata}}` 的字典。两处防御：键里没有 `_chunk_` 的条目跳过（store 可能混有文档级条目）；`doc_title`/`plain` 都有**回退链**（metadata 没有就从 chunk_id 切、original_text 没有就用 content）——装载器对容器形状的容忍。返回按 chunk_id 排序——**顺序稳定**是后面所有指标可比的前提（plain 和 contextual 的向量矩阵必须同序）。

!!! info "学习版的前置：document_store 从哪来"
    课程仓库不带这个文件（原版由需 localhost:4242 检索服务的索引流水线生成）。学习版从**书方已通过战役的 evidence.json**（`chunks` 字段保留了 22 块原文与标题）无损重建，chunk 内容与评测集 `gold_chunk_id` 精确对齐——见 [run_contextual_retrieval.py](../assets/task3/run_contextual_retrieval.py) L52–58。

---

## 4. `source_documents`（L74–84）：给每块找全文

```python linenums="74"
def source_documents(chunks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    laws = CHAPTER / "agentic-rag" / "laws"
    output = {}
    for title in sorted({row["doc_title"] for row in chunks}):
        candidates = [path for path in laws.rglob("*.md") if path.stem == title]
        if len(candidates) != 1:
            raise RuntimeError(f"expected one official bundled source for {title!r}, found {len(candidates)}")
        path = candidates[0]
        output[title] = {"path": path, "text": path.read_text(encoding="utf-8")}
    return output
```

从 chunk 集合提取**去重的文档标题**，到 `agentic-rag/laws`（复用 3-8 的法条库）里按文件名找源文件。`len(candidates) != 1` 就抛——找到 0 个或 2 个同名文件都算数据错误，**宁可不跑也不猜出处**。本实验命中两份：《宪法》《检察官法》。

---

## 5. `prefix_one`（L86–111）：前缀生成的最小单元

```python linenums="86"
def prefix_one(args: argparse.Namespace, chunk: Dict[str, Any], source: Dict[str, Any]):
    client = OpenAI(api_key=os.environ["ARK_API_KEY"], base_url=args.endpoint, timeout=args.timeout, max_retries=3)
    recorder = ChatRecorder(client, "ark", args.endpoint)
    response = recorder.create(
        purpose=f"3-10 live contextual prefix {chunk['chunk_id']}",
        model=args.context_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "为目标文本块生成简短的中文检索前缀。前缀必须说明该块来自哪份文档、所属章节/条款、"
                    "主体与主题，使孤立文本能被准确检索。不得添加源文没有的事实。只输出前缀，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": f"完整源文档：\n<document>\n{source['text']}\n</document>\n\n目标文本块：\n<chunk>\n{chunk['plain']}\n</chunk>",
            },
        ],
        temperature=0,
        seed=args.seed,
        max_tokens=220,
    )
    prefix = (response.choices[0].message.content or "").strip()
    return {**chunk, "prefix": prefix, "contextual": f"{prefix}\n\n{chunk['plain']}"}, recorder.calls
```

一个 chunk 一次独立调用，天然可并发（main 里 4 线程）。三个设计点：

- 请求里**整份源文档 + 目标块**，用 `<document>`/`<chunk>` 标签包裹——模型看得到块在文档里的位置语境，"不得添加源文没有的事实"才有依据。验收门槛逐字检查这两个标签出现在每个请求里；
- `max_tokens=220` 把前缀钉在"简短"；system 里的三连要求（来自哪/哪一节/讲什么）就是前缀的信息规格；
- 返回值把 chunk 扩展成 `{..., prefix, contextual}`——**contextual = 前缀 + 空行 + 原文**，前缀不是旁路元数据，是直接进索引的文本。

实测样例：宪法 chunk_0 的前缀"《中华人民共和国宪法》序言（1982年通过，含历次修正案）"——文档名、章节、时期，全是块里没有但检索决定性的词。22 次调用共 181K tokens，其中输入 180K（每次都带整份文档）——**前缀的成本几乎全在输入侧，一次性付清**。

---

## 6–8. 三种排序：`rankings_bm25` / `rankings_dense` / `rrf`

```python linenums="113"
def rankings_bm25(texts: List[str], queries: List[str]) -> List[List[int]]:
    index = BM25Okapi([tokenize(text) for text in texts])
    return [np.argsort(-index.get_scores(tokenize(query))).tolist() for query in queries]

def rankings_dense(vectors: np.ndarray, query_vectors: np.ndarray) -> List[List[int]]:
    return [np.argsort(-(query @ vectors.T)).tolist() for query in query_vectors]

def rrf(a: List[int], b: List[int], constant: int = 60) -> List[int]:
    scores: Dict[int, float] = {}
    for ranking in (a, b):
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (constant + rank)
    return sorted(scores, key=lambda item: scores[item], reverse=True)
```

三个函数同构：输入文本/向量 + 查询，输出"每个查询对全部文本的**完整排序**"（不是只取 top-k——`metrics` 要算任意名次）。BM25 用 `rank_bm25` 库 + 课程自己的 `tokenize` 分词；稠密就是归一化向量矩阵乘（`query @ vectors.T` 一个查询一行）；`np.argsort(-分数)` 统一做降序。`rrf` 是倒数排名融合：两套排序里第 r 名得 `1/(60+r)` 分、同 item 累加——**无权重、无调参**的融合，常数 60 来自 RRF 论文默认。注意它对**全长排序**求和（不只 top-k），两个通道都认可的块浮到顶。

---

## 9. `metrics`（L130–152）：排序 → 指标

```python linenums="130"
def metrics(rankings: List[List[int]], queries: List[Dict[str, Any]], id_to_pos: Dict[str, int]) -> Dict[str, Any]:
    per_query = []
    reciprocal = []
    for query, ranking in zip(queries, rankings):
        gold = id_to_pos[query["gold_chunk_id"]]
        rank = ranking.index(gold) + 1 if gold in ranking else None
        reciprocal.append(1.0 / rank if rank else 0.0)
        per_query.append(
            {
                "id": query["id"],
                "query": query["query"],
                "gold_chunk_id": query["gold_chunk_id"],
                "rank": rank,
                "top5_chunk_ids": ranking[:5],
            }
        )
    return {
        "n": len(queries),
        "recall_at_k": {str(k): statistics.mean(1.0 if row["rank"] and row["rank"] <= k else 0.0 for row in per_query) for k in (1, 3, 5)},
        "mrr": statistics.mean(reciprocal),
        "per_query": per_query,
    }
```

单金标口径：每条查询有一个 `gold_chunk_id`，在排序里找它的名次（`ranking.index(gold) + 1`；找不到记 None，MRR 贡献 0）。recall@k = 金标进前 k 的查询占比；MRR = 平均倒数名次。`per_query` 全量保留——哪个查询掉队、掉到第几名，复盘时逐条可查（main 里还会把 `top5_chunk_ids` 从位置换算回 chunk_id）。

---

## 10. `token_usage`（L154–161）

回执 → 三项 token 合计，与 3-8 的 `usage` 同款小工具。

---

## 11. `main`（L163–284）：编排与验收

按执行顺序拆四段。

**装载（L164–204）**：解析参数（`--context-model` 前缀 LLM、`--embedding-model` 默认 `Qwen/Qwen3-Embedding-0.6B`、`--device`、`--endpoint`、两个价格参数）；`load_chunks` + `source_documents`；然后是**前缀生成池**：

```python linenums="186"
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(prefix_one, args, chunk, docs[chunk["doc_title"]]): chunk["chunk_id"] for chunk in chunks}
        for future in concurrent.futures.as_completed(futures):
            chunk_id = futures[future]
            try:
                row, calls = future.result()
                contextual.append(row)
                receipts.extend(calls)
                print(f"prefix {chunk_id} ({len(contextual)}/{len(chunks)})", flush=True)
            except Exception as exc:
                errors.append({"chunk_id": chunk_id, "type": type(exc).__name__, "error": str(exc)})
    prefix_ms = (time.perf_counter() - prefix_start) * 1000
    contextual.sort(key=lambda row: row["chunk_id"])
```

22 个 chunk 并发生成前缀，单块失败记 errors 不炸全场。完成后**按 chunk_id 重排**——`as_completed` 的完成顺序是乱的，必须重排回与 `load_chunks` 相同的顺序，plain/contextual 两套向量才能逐位对齐。

**六套排序（L205–233）**：守门条件 `len(contextual) == len(chunks) and not errors`——**任何一块前缀缺失，整场比较不做**（部分前缀的双索引没有对照意义）。然后三步：BM25 两套（plain 文本 / contextual 文本）→ 编码器三批向量（plain 22 段、contextual 22 段、查询 15 条）→ 稠密两套 + RRF 两套，全部走 `metrics`。

**验收门槛（L237–247）**，三条最值得读：

```python linenums="238"
    acceptance = {
        "live_prefix_for_every_chunk": len(contextual) == len(chunks) and all(row["prefix"] for row in contextual),
        "full_source_document_and_target_chunk_in_requests": len(receipts) == len(chunks) and all("<document>" in json.dumps(call.get("request", {}), ensure_ascii=False) and "<chunk>" in json.dumps(call.get("request", {}), ensure_ascii=False) for call in receipts),
        ...
        "real_dense_model": bool(encoder and encoder.revision),
```

`live_prefix_for_every_chunk`：手写前缀的结果**不被接受**（书稿门槛原文）；`full_source...`：每个请求 JSON 化后逐字找两个标签——截断输入的前缀不算数；`real_dense_model`：HF revision 非空。

**落证据（L249–276）**：evidence 里除了配置/验收/汇总，还带 `source_documents`（每份源文档的路径 + sha256）、`chunks`（22 块的 plain/prefix/contextual 全文——这正是学习版日后重建 document_store 的材料源，证据自闭环）、`results`（六方法逐查询名次）。最后 `write_campaign_evidence(HERE, "3-10", ...)`——HERE 重定向 + 入口脚本复制的坑同前两个实验。

---

## 完整执行回放（学习版一次真实运行）

```text
main
 ├─ load_chunks(OUT/document_store.json) → 22 块（按 chunk_id 排序）
 ├─ source_documents → 宪法.md / 检察官法（2019-04-23）.md 全文
 ├─ ThreadPool(4) × prefix_one × 22 → 前缀全部 live 生成（deepseek-flash，181K tokens，5.5s）
 │    └─ contextual.sort(chunk_id) → 与 plain 同序
 ├─ rankings_bm25(plain 文本) / rankings_bm25(前缀+原文)
 ├─ TransformerEncoder(Qwen3-Embedding-0.6B, cpu)
 │    ├─ encode(plain 22 段) ├─ encode(contextual 22 段) └─ encode(15 查询, query=True)
 ├─ rankings_dense ×2 → rrf ×2 → 六套排序
 ├─ metrics ×6 → recall@1/3/5 + MRR（+per_query 名次）
 └─ 验收（9 门槛全过）→ write_campaign_evidence
```

实测（[evidence](evidence.md#contextual-retrieval)）：MRR plain_bm25 0.833→contextual 0.872、plain_dense 0.933→0.967、plain_hybrid 0.889→contextual_hybrid 0.967——前缀三通道全升，方向与书方 doubao 前缀完全一致。

## 动手验证

1. **把 `prefix_one` 的 `max_tokens` 从 220 改成 2000**：前缀会变长（更详细），但 BM25 通道的收益未必涨——前缀越长，"前缀词稀释原文词"的反作用越强。这把"简短"从风格要求变成实验变量。
2. **把 `encode` 的 `query=True` 前缀删掉**：Qwen3-Embedding 的查询/文档不对称用法被破坏，dense 通道的 MRR 会掉多少？这是检验"官方用法不是玄学"的直接办法。
3. **只保留 rrf 的 top-50 再融合**：`rrf` 现在对全长排序求和——截断到 top-50 后结果几乎不变（长尾贡献 1/(60+r) 微小），但省计算。想想什么场景下这个省法会出错（提示：某通道的金标排在 50 名以外）。
