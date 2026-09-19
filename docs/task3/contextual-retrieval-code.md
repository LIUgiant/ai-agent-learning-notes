# 上下文感知检索源码精读 · 前缀生成、双索引与 RRF 混合

[实验说明](contextual-retrieval.md) · [实测结果](evidence.md#contextual-retrieval) · [学习运行脚本](../assets/task3/run_contextual_retrieval.py)

<div class="design-lead"><span>逐步搭建 / READ THE CODE</span><p>先看前缀生成的请求里为什么必须放整份源文档，再读本地 Qwen3-Embedding 的取向量细节，最后看 recall/MRR 怎么从排序里算出来、RRF 怎么把两套排序融成一套。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号（chapter3/contextual-retrieval/campaign.py）；**学习运行脚本原文**来自 `run_contextual_retrieval.py`；**教学示意**仅用于理解数据形状。

## 本页阅读路线

前缀生成 → 双索引对照 → 本地编码器 → 三种排序 → 指标计算 → 验收门槛 → document_store 重建 → 实测解读。

---

## 1. 前缀生成：整份源文档 + 目标块，缺一不可

**遇到的问题**

给文本块写"它是谁"的说明，模型只看块本身会**编造出处**（猜一个文档名）。前缀里的每个事实都必须有依据。

**设计思路**

请求里同时放**完整源文档**和**目标块**，用显式标签包裹；系统提示明文"不得添加源文没有的事实"。

**关键代码**

**课程源码原文** · [campaign.py · L86–L110](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/contextual-retrieval/campaign.py#L86)：

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

**执行过程：看数据怎样变**

- 每块一次独立调用（22 块 = 22 次），`max_tokens=220` 把前缀钉在"简短"上；
- 输出拼成 `contextual = 前缀 + 空行 + 原文`——前缀不是元数据字段，是**和原文一起被索引的文本**；
- 实测样例：宪法 chunk_0 的前缀是"《中华人民共和国宪法》序言（1982年通过，含历次修正案）"——文档名、章节、时期，全是块里没有但检索时决定性的词。

**接回真实源码**

`source_documents()`（L67–L83）从 `agentic-rag/laws` 找到每份 chunk 的**唯一**源文件（`len(candidates) != 1` 直接报错——同名文档会污染出处），整篇读入作为 `<document>`。22 次调用的 token 结构：180,423 prompt tokens（每次都带整份宪法/检察官法原文）对 759 completion tokens——**前缀的成本几乎全在输入侧**。

**动手验证**

为什么不给模型只看"文档标题 + 目标块"（省掉整份文档的输入）？

??? tip "先预测，再展开对照"
    标题说得出文档名，说不出"这一块属于第几章、讲哪个主体"——块在文档里的**位置语境**只有全文能提供。而且课程验收门槛 `full_source_document_and_target_chunk_in_requests` 逐字检查每个请求里同时有 `<document>` 和 `<chunk>` 标签：**截断输入的前缀不算数**。代价就是上面那 18 万 prompt tokens——索引一次、查询零成本，这是典型的"索引期换查询期"。

---

## 2. 双索引对照：同块同查询，唯一变量是索引文本

**关键代码**

**课程源码原文** · [campaign.py · L208–L228](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/contextual-retrieval/campaign.py#L208)：

```python linenums="208"
if len(contextual) == len(chunks) and not errors:
    plain_texts = [row["plain"] for row in contextual]
    contextual_texts = [row["contextual"] for row in contextual]
    plain_bm25 = rankings_bm25(plain_texts, query_texts)
    contextual_bm25 = rankings_bm25(contextual_texts, query_texts)
    encoder = TransformerEncoder(args.embedding_model, args.device)
    ...
    plain_vectors = encoder.encode(plain_texts, query=False)
    contextual_vectors = encoder.encode(contextual_texts, query=False)
    query_vectors = encoder.encode(query_texts, query=True)
    plain_dense = rankings_dense(plain_vectors, query_vectors)
    contextual_dense = rankings_dense(contextual_vectors, query_vectors)
    ranking_sets = {
        "plain_bm25": plain_bm25,
        "contextual_bm25": contextual_bm25,
        "plain_dense": plain_dense,
        "contextual_dense": contextual_dense,
        "plain_hybrid": [rrf(a, b) for a, b in zip(plain_bm25, plain_dense)],
        "contextual_hybrid": [rrf(a, b) for a, b in zip(contextual_bm25, contextual_dense)],
    }
```

**执行过程：看数据怎样变**

六套排序共享**同一个 chunk 列表顺序和同一批查询**——`id_to_pos` 按 chunk_id 建位次映射，六套排序在同一坐标系里比 rank。任何一个前缀生成失败，整场比较直接不做（`len(contextual) == len(chunks)` 守门）——**部分前缀的双索引没有对照意义**。

三 × 二的结构：

```text
        BM25（词面）      稠密（语义）      RRF 混合
plain   排序 A1           排序 A2           fuse(A1, A2)
ctx     排序 B1           排序 B2           fuse(B1, B2)
```

`rrf`（L122–L127）：两套排序里名次换算成分数 `1/(60+rank)` 相加——**不用调权重的融合**，常数 60 是 RRF 论文的默认。名次越靠前贡献越大，两套都认可的块浮到顶。

---

## 3. 本地编码器：last-token 池化 + Instruct 前缀

**关键代码**

**课程源码原文** · [campaign.py · L23–L48](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/contextual-retrieval/campaign.py#L23)：

```python linenums="23"
class TransformerEncoder:
    def __init__(self, model_name: str, device: str):
        import torch
        from transformers import AutoModel, AutoTokenizer
        ...
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="left")
        self.model = AutoModel.from_pretrained(model_name).to(device).eval()
        self.revision = getattr(self.model.config, "_commit_hash", None)

    def encode(self, texts: Sequence[str], *, query: bool, batch_size: int = 8) -> np.ndarray:
        prefix = "Instruct: Retrieve semantically relevant passages.\nQuery:" if query else ""
        ...
            tokens = self.tokenizer(batch, padding=True, truncation=True, max_length=512, return_tensors="pt").to(self.device)
            with self.torch.no_grad():
                output = self.model(**tokens).last_hidden_state[:, -1].float()
            output = self.torch.nn.functional.normalize(output, p=2, dim=1)
```

**执行过程：看数据怎样变**

三处细节都是 Qwen3-Embedding 的**官方用法**，不是通用写法：

- **`padding_side="left"` + `last_hidden_state[:, -1]`**：取**最后一个 token**的隐状态当句向量。左填充保证"最后一个 token"是真实文本的末尾而不是 padding——right-padding 时取 `[:, -1]` 会拿到一堆填充符的表示，向量全废；
- **查询侧加 `Instruct: ... Query:` 前缀、文档侧不加**：Qwen3-Embedding 是指令感知的检索模型，查询前缀告诉它"这是检索意图"；文档保持裸文本；
- **L2 归一化后点积 = 余弦相似度**：`rankings_dense` 里 `query @ vectors.T` 直接矩阵乘。

`self.revision` 记录 HF 模型的 commit 哈希——验收门槛 `real_dense_model` 检查它非空，**"用了真模型"要有版本号背书**，与第 2 章回执校验同一个思路。

**动手验证**

文档块和查询的 `max_length=512` 截断，前缀会不会反而挤掉原文内容？

??? tip "先预测，再展开对照"
    会挤——前缀平均几十 token，长块（本语料 ≤2048 字符）512 token 截断时尾部内容本来就会丢一部分，前缀让窗口更紧。但前缀带来的"文档名/条款号"信号通常比块尾的一小段更值钱；若块很长，正确工程做法是给文档侧单独放宽 max_length。本实验语料块短（均值 ~1000 字符），影响有限——这是缩尺语料的宽容度，长文档场景要重新评估。

---

## 4. 指标：从排序算 recall@k 与 MRR

**关键代码**

**课程源码原文** · [campaign.py · L130–L151](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/contextual-retrieval/campaign.py#L130)：

```python linenums="130"
def metrics(rankings: List[List[int]], queries: List[Dict[str, Any]], id_to_pos: Dict[str, int]) -> Dict[str, Any]:
    per_query = []
    reciprocal = []
    for query, ranking in zip(queries, rankings):
        gold = id_to_pos[query["gold_chunk_id"]]
        rank = ranking.index(gold) + 1 if gold in ranking else None
        reciprocal.append(1.0 / rank if rank else 0.0)
        per_query.append({...})
    return {
        "n": len(queries),
        "recall_at_k": {str(k): statistics.mean(1.0 if row["rank"] and row["rank"] <= k else 0.0 for row in per_query) for k in (1, 3, 5)},
        "mrr": statistics.mean(reciprocal),
        "per_query": per_query,
    }
```

**执行过程：看数据怎样变**

每条查询有一个**金标 chunk**（单目标）：金标排在第 `rank` 位 → recall@k = 金标进前 k 的查询占比；MRR = 平均 `1/rank`。注意这是**单金标**口径——多跳问题（一条查询对应多个正确块）要换成 recall@k over gold set（如 3-8 的法条召回）。`per_query` 保留每条查询的名次和 top-5，失败案例可以逐条复盘。

---

## 5. 验收门槛与 document_store 重建

**执行过程：看数据怎样变**

九道门槛里三道值得细读（L237–L247）：

- `full_source_document_and_target_chunk_in_requests`：把**每个请求** JSON 化后逐字找 `<document>` 和 `<chunk>` 标签——证明前缀是看着全文生成的，不是看了个摘要；
- `live_prefix_for_every_chunk`：每个 chunk 的前缀非空且数量对齐——**手写前缀的结果不被接受**（书稿门槛原文）；
- `real_dense_model`：编码器的 HF revision 非空。

**学习版的 document_store 重建**：课程仓库不带这个文件（原版由需要 localhost:4242 检索服务的索引流水线生成）。书方已通过战役的 evidence.json 保留了全部 22 块的原文与文档标题，学习脚本按 `load_chunks` 的读取形状重组：

**学习运行脚本原文** · [run_contextual_retrieval.py · L52–L58](../assets/task3/run_contextual_retrieval.py)：

```python linenums="52"
store = {}
for c in book_chunks:
    store[c["chunk_id"]] = {
        "content": c["plain"],
        "metadata": {"doc_title": c["doc_title"], "original_text": c["plain"]},
    }
(OUT / "document_store.json").write_text(json.dumps(store, ensure_ascii=False, indent=2))
```

chunk 内容与书方证据**逐字节相同**、与评测集 `gold_chunk_id` 精确对齐；前缀由 DeepSeek 现场生成（live 门槛原样满足）。与 [task1 教学语料](../task1/context-code.md)的区别：这次不是合成数据，是从书方证据无损搬运的真实分块。

---

## 6. 实测：三通道全升，混合追平稠密

**执行过程：看数据怎样变**

DeepSeek 前缀 + 本地 Qwen3-Embedding（CPU），全量 22 块/15 查询：

| 方法 | MRR | R@1 | R@3 | R@5 |
| --- | ---: | ---: | ---: | ---: |
| plain_bm25 | 0.833 | 0.73 | 0.87 | 1.00 |
| contextual_bm25 | 0.872 | 0.80 | 0.93 | 1.00 |
| plain_dense | 0.933 | 0.87 | 1.00 | 1.00 |
| contextual_dense | **0.967** | **0.93** | 1.00 | 1.00 |
| plain_hybrid | 0.889 | 0.80 | 1.00 | 1.00 |
| contextual_hybrid | **0.967** | **0.93** | 1.00 | 1.00 |

- **前缀三通道全部提升**：BM25 +0.039、稠密 +0.034、混合 +0.078（MRR）。R@1 普涨 0.07——前缀把"金标排第一"的查询从 11/15 提到 14/15；
- **BM25 受益的机制最直观**：前缀塞进了块里没有的词（"宪法""序言""1982"），字面匹配多了一条命中路径。稠密通道的提升说明前缀也帮了**语义**定位（孤立的条文片段获得了文档语境）；
- **contextual_hybrid 追平 contextual_dense**（0.967）：稠密通道已经很强时，混合的边际收益趋零——但在 plain 侧 hybrid（0.889）明显不如 dense（0.933），说明混合救的是"某一通道弱"的场景，不是无条件加成；
- **索引成本**：22 次前缀调用共 181K tokens（输入 180K——每次带整份源文档）、5.5 秒（4 并发）；CPU 编码 59 段文本 408 秒。**一次性索引成本，查询零增量**。

**与书方对照**：书方（doubao 前缀 + 同款编码器）MRR：plain_bm25 0.751→ctx 0.856、plain_dense 0.922→0.967、plain_hybrid 0.844→0.913。方向完全一致（三通道全升、稠密最强、混合收敛到稠密水平），数值在同一区间——前缀的收益对前缀模型不敏感，更像**机制性**收益而非模型运气。

**动手验证**

R@5 全部 1.00，说明什么？这个评测集还能分辨更好的检索器吗？

??? tip "先预测，再展开对照"
    金标块都能进前 5——天花板已到，**R@5 失去区分度**，真正拉开差距的是 R@1/MRR（第一名 vs 第五名，在 RAG 里意味着带进上下文的证据排位）。想要更难的评测：加大语料（22 块 → 全量法条库）、查询改写成同义改写（BM25 的死穴）、或者像 3-8 那样多金标。课程用 2 文档小语料是为了"前缀效应可控可观察"，不是检索器的终极考场。

---

## 最后回到项目

学习脚本 document_store 重建 → 课程 prefix_one 生成前缀 → 双索引 × 三排序 → recall/MRR → [看真实实验结果](evidence.md#contextual-retrieval)。
