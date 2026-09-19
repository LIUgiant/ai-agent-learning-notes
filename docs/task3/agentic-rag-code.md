# Agentic RAG 源码精读 · 一次检索和会迭代的检索差在哪

[实验说明](agentic-rag.md) · [实测结果](evidence.md#agentic-rag) · [学习运行脚本](../assets/task3/run_agentic_rag.py)

<div class="design-lead"><span>逐步搭建 / READ THE CODE</span><p>先看两臂共享什么（语料、BM25、评审），再拆 Agentic 臂的 ReAct 循环与搜索预算，最后看证据召回与引用有效性怎么从答案文本里算出来。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号（chapter3/agentic-rag/campaign.py）；**学习运行脚本原文**来自 `run_agentic_rag.py`；**教学示意**仅用于理解数据形状。

## 本页阅读路线

两臂设计 → 单轮基线 → ReAct 循环 → 搜索预算与强制收尾 → 证据召回与引用检查 → 独立评审 → 假设检验口径 → 学习版结果解读。

---

## 1. 两臂设计：除了"能否再搜"，一切固定

**遇到的问题**

"Agentic RAG 更好"要成立，必须排除其他解释：不是语料不同、不是检索器不同、不是评审偏心——唯一变量是**答题者能不能根据第一轮检索的结果决定再搜什么**。

**设计思路**

docstring 直接写明固定清单：corpus、cases、BM25 实现、检索深度（top_k）、答题模型、独立评审全部固定；改变的因素只有一个——one search of the original question vs plan and iterate through a ReAct tool loop。

**关键代码**

**课程源码原文** · [campaign.py · L230–L247](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/agentic-rag/campaign.py#L230)：

```python linenums="230"
def run_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
    answer_recorder = ChatRecorder(self.answer_client, "ark", self.args.answer_endpoint)
    judge_recorder = ChatRecorder(self.judge_client, "moonshot", self.args.judge_endpoint)
    started = time.perf_counter()
    baseline_results = self.search(case["question"])
    baseline_search_ms = (time.perf_counter() - started) * 1000
    before = time.perf_counter()
    baseline_answer = self.answer_once(answer_recorder, case, baseline_results)
    baseline_ms = (time.perf_counter() - before) * 1000 + baseline_search_ms

    before = time.perf_counter()
    agent_answer, agent_results, trajectory = self.answer_agentic(answer_recorder, case)
    agent_ms = (time.perf_counter() - before) * 1000
```

**执行过程：看数据怎样变**

同一案例、同一模型，两臂先后跑在同一 recorder 上：

- **基线**：用**原问题**做一次 BM25 检索（`self.search(case["question"])`）→ 拿到 top-5 chunk → 一次生成带引用的回答；
- **Agentic**：模型自己分解问题、自己写检索词、最多迭代 4 次搜索；
- 检索器是 `OfflineRetriever`——**本地法条语料的 BM25**（`HERE/laws` 下 100+ 份中国法律 md），零 API、零向量库：这个实验考的是"检索策略"，不是"检索器强弱"。

**接回真实源码**

数据集 [evaluation/offline_qa.json](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/agentic-rag/evaluation/offline_qa.json)（7 案例，全量）：5 个 easy（单法条问题，如"故意伤害致人重伤如何处罚"→ 金标《刑法》第二百三十四条）+ 2 个 hard（多跳，金标 3 个法条）。

**动手验证**

一个复杂问题是"离婚后房产分割和子女抚养分别怎么判"。基线用整句话搜 BM25，会命中什么？

??? tip "先预测，再展开对照"
    BM25 是词频匹配——整句同时包含"房产""子女""离婚""抚养"，两个主题的词互相稀释，两个主题都可能排不进 top-5。这正是复杂题基线证据召回 0.58 的机制：**一个查询装不下两个法律问题**。

---

## 2. 单轮基线：接地生成 + 引用格式

**关键代码**

**课程源码原文** · [campaign.py · L123–L141](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/agentic-rag/campaign.py#L123)：

```python linenums="123"
def answer_once(self, recorder: ChatRecorder, case: Dict[str, Any], retrieved: List[Dict[str, Any]]) -> str:
    response = recorder.create(
        purpose=f"3-8 baseline grounded answer {case['id']}",
        model=self.args.answer_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是法律信息助手。只能依据所给法条回答。每个实质结论后用 [chunk_id] 引用。"
                    "若证据不足必须说明。结尾注明：本回答仅供一般法律信息参考，不构成正式法律意见。"
                ),
            },
            {"role": "user", "content": f"问题：{case['question']}\n\n证据：\n{context(retrieved)}"},
        ],
        temperature=0,
        seed=self.args.seed,
        max_tokens=900,
    )
    return response.choices[0].message.content or ""
```

**执行过程：看数据怎样变**

三条约束刻进 system：只依据所给法条（接地）、每个实质结论带 `[chunk_id]`（可核查）、证据不足必须说明（拒绝而不是编）+ 免责声明（法律场景的固定尾巴）。`context()`（L53–L57）把检索结果格式化成 `[chunk_id] 标题
正文`——chunk_id 出现在证据里、被要求出现在答案里，引用闭环由此建立。

---

## 3. ReAct 循环：第一次必须调工具，之后自由

**关键代码**

**课程源码原文** · [campaign.py · L159–L196](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/agentic-rag/campaign.py#L159)（节选）：

```python linenums="173"
final = ""
for iteration in range(1, self.args.max_searches + 2):
    request: Dict[str, Any] = {
        "model": self.args.answer_model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "required" if iteration == 1 else "auto",
        "temperature": 0,
        "seed": self.args.seed,
        "max_tokens": 900,
    }
    response = recorder.create(purpose=f"3-8 agentic react {case['id']} iteration {iteration}", **request)
    message = response.choices[0].message
    assistant: Dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        assistant["tool_calls"] = [jsonable(tc) for tc in message.tool_calls]
    messages.append(assistant)
    step: Dict[str, Any] = {"iteration": iteration, "assistant": message.content or "", "searches": []}
    if not message.tool_calls:
        final = message.content or ""
        trajectory.append(step)
        break
```

**执行过程：看数据怎样变**

- **`tool_choice="required"` 只在第 1 轮**：强制模型先动手搜索，不许上来就凭空作答；之后改 `auto`，模型自己决定"证据够了，作答"还是"再搜一个子问题"。终止条件 = 不带工具调用的回复；
- 每轮的检索结果**追加**进消息历史（工具消息），下一轮模型看着全部已检索证据决定下一步——这就是"迭代"的全部含义，没有魔法；
- `union` 字典（L171）按 chunk_id 去重合并所有轮的检索结果——Agentic 臂的"证据集"是各次搜索的并集，与基线的单次 top-5 对比。

**动手验证**

为什么第 1 轮强制调工具，而不是让模型自己决定？

??? tip "先预测，再展开对照"
    不强制的话，模型可能直接用参数里的法律知识作答（没有接地），实验就退化成"无检索 vs 有检索"。强制首搜保证两臂**都至少做过一次检索**，差异只剩"能否根据结果继续搜"——变量控制到最窄。

---

## 4. 搜索预算与强制收尾

**关键代码**

**课程源码原文** · [campaign.py · L197–L227](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/agentic-rag/campaign.py#L197)（节选）：

```python linenums="197"
for tool_call in message.tool_calls:
    if len([q for row in trajectory for q in row["searches"]]) + len(step["searches"]) >= self.args.max_searches:
        tool_result = {"error": "search budget exhausted"}
    else:
        ...
        rows = self.search(query) if query else []
        for row in rows:
            union[row["chunk_id"]] = row
        tool_result = {"query": query, "results": rows}
        step["searches"].append(tool_result)
    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(tool_result, ensure_ascii=False)})
...
if not final:
    response = recorder.create(
        purpose=f"3-8 agentic forced final {case['id']}",
        model=self.args.answer_model,
        messages=messages + [{"role": "system", "content": "搜索预算已用完。现在仅根据已返回证据给出带引用的最终回答。"}],
        max_tokens=900,
    )
    final = response.choices[0].message.content or ""
```

**执行过程：看数据怎样变**

- 预算（`--max-searches 4`）按**已执行的搜索数**计（跨轮累计），超限的工具调用收到 `{"error": "search budget exhausted"}`——不是异常而是**可观察的工具结果**，模型下一轮看得见；
- 循环上限 `max_searches + 2` 轮，若模型到最后一轮还在要搜索，**强制收尾**：追加一条 system（"预算已用完，现在基于已有证据作答"）再调一次不带工具的生成。**预算烧光不等于失败**——已检索的证据仍在，只是不许再搜。

这与 [task2 的 system-hint](../task2/system-hint-code.md) 里"submit_result 才算 complete"是同一种纪律：资源上限 + 规范终止，两层分开。

---

## 5. 证据召回与引用有效性：从文本里客观算分

**关键代码**

**课程源码原文** · [campaign.py · L48–L68](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/agentic-rag/campaign.py#L48)：

```python linenums="48"
def article_hits(results: Iterable[Dict[str, Any]], gold: Iterable[str]) -> List[str]:
    combined = "\n".join(str(row.get("text", "")) for row in results)
    return [article for article in gold if article in combined]

def citations(answer: str, valid_ids: Iterable[str]) -> Dict[str, Any]:
    cited = re.findall(r"\[([^\[\]]+_chunk_\d+)\]", answer or "")
    valid = set(valid_ids)
    return {
        "cited_chunk_ids": cited,
        "valid_count": sum(item in valid for item in cited),
        "invalid_count": sum(item not in valid for item in cited),
        "has_valid_citation": any(item in valid for item in cited),
    }
```

**执行过程：看数据怎样变**

两套客观指标都不经过模型：

- **证据召回**：金标法条号（如"第二百三十四条"）是否**字面出现**在检索结果的正文里——`ARTICLE_RE`（L36）预编译了中文法条号的正则。模型答得多漂亮，没检索到金标法条就是 recall 低；
- **引用有效性**：答案里的 `[xxx_chunk_N]` 是否指向**这次实际返回的** chunk。`invalid_count` 抓"引用了没给过的材料"——接地性的文本级证据。评审另有 citation_quality 维度做语义级判断，两者互补。

**动手验证**

模型在答案里写了 `[刑法_chunk_7]` 但本次检索没返回这个 chunk。哪两个指标会变坏？

??? tip "先预测，再展开对照"
    `invalid_count` +1（引用了未提供的材料）。若这是它唯一的引用，`has_valid_citation` 变 False，citation_valid_rate 归零；评审的 citation_quality/groundedness 大概率也扣分。注意证据召回**不受影响**——召回只看检索结果，不看答案。检索质量与引用诚实度是两条独立的轴。

---

## 6. 独立评审与假设口径

**关键代码**

**课程源码原文** · [campaign.py · L348–L353](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/agentic-rag/campaign.py#L348)：

```python linenums="348"
    hypothesis = {}
    if summary:
        hypothesis = {
            "simple_roughly_ties": abs(summary["agentic"]["simple"]["judge_correctness"] - summary["baseline"]["simple"]["judge_correctness"]) <= 0.5,
            "complex_quality_improves": summary["agentic"]["complex"]["judge_correctness"] > summary["baseline"]["complex"]["judge_correctness"],
            "agentic_adds_latency": summary["agentic"]["overall"]["mean_latency_ms"] > summary["baseline"]["overall"]["mean_latency_ms"],
        }
```

**执行过程：看数据怎样变**

三条预注册假设（书稿结论的方向）：简单题**打平**（差 ≤0.5 分，不是"赢"）、复杂题**质量提升**、Agentic **必然更慢**。第三条特别诚实——把成本上升写成假设的一部分，防止只报收益不报代价。

评审（L80–L106）同样只见检索证据 + 答案、不见金标答案之外的外部知识，四维 1–4 分 + `unsupported_claim` 布尔。与 3-1/3-2 的评审同构（跨实验的 judge 契约，3-9/3-11 会复用）。

---

## 7. 学习版实测：三个假设全部成立

**执行过程：看数据怎样变**

DeepSeek 答题 + qwen3.7-plus 评审，全量 7 案例：

| 臂 | 组 | 证据召回 | 评审正确性 | 搜索次数 | 延迟 |
| --- | --- | ---: | ---: | ---: | ---: |
| baseline | simple | 1.00 | 4.00 | 1.0 | 1642ms |
| baseline | complex | 0.58 | 3.50 | 1.0 | 1761ms |
| agentic | simple | 1.00 | 4.00 | 2.0 | 3433ms |
| agentic | complex | **0.92** | **4.00** | 3.0 | 3943ms |

- **simple_roughly_ties：成立**——简单题两臂同为满分召回/满正确分，Agentic 多花一倍延迟没换来质量（天花板效应）；
- **complex_quality_improves：成立**——复杂题召回 0.58→0.92、正确性 3.50→4.00。机制可见于轨迹：模型把多跳问题拆成"房产分割怎么判""子女抚养怎么判"分次检索，union 的证据覆盖了 3 个金标法条；
- **agentic_adds_latency：成立**——均值 1.7s→3.7s（搜索 1→2.6 次）。**收益与代价一起报告**。

课程验收门槛全过（真实法条语料 ≥100 份、单轮基线、活跃生成检索、引用核查、独立评审、回执完整），37 次调用 56K tokens，密钥扫描干净。

**与书方的关系**：书方 Kimi/doubao 战役同为"passed"，方向一致（复杂题改善、延迟增加）；具体数值随模型与案例组合不同，学习版只报方向。

**动手验证**

把 top-k 从 5 提到 20，基线在复杂题上的召回会上去吗？这算不算"解决"了多跳问题？

??? tip "先预测，再展开对照"
    单跳召回会涨（金标法条更可能挤进前 20），但代价是上下文塞入大量无关法条——接地生成长度/成本上升、干扰引用选择，且两个主题的词稀释问题依旧存在（排名靠前的仍是单主题混合结果）。**加大 k 是用钱换召回**，Agentic 是用迭代换召回，机制不同。课程把 top_k 固定在 5 正是为了不让"砸钱"混进变量。

---

## 最后回到项目

学习脚本 HERE 重定向 → 课程 run_case 两臂 → ReAct 循环与预算 → 客观指标与独立评审 → [看真实实验结果](evidence.md#agentic-rag)。
