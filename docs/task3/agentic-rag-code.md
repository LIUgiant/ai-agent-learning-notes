# Agentic RAG 源码精读 · campaign.py 逐函数通读

[实验说明](agentic-rag.md) · [实测结果](evidence.md#agentic-rag) · [学习运行脚本](../assets/task3/run_agentic_rag.py)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>本页按源码顺序把 agentic-rag/campaign.py 的每个函数过一遍——工具函数、两臂实现、聚合、验收与假设，一个不漏。读完你应该能复述整个文件。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号（chapter3/agentic-rag/campaign.py）；**学习运行脚本原文**来自 `run_agentic_rag.py`；**教学示意**仅用于理解数据形状。

**主文件**：[chapter3/agentic-rag/campaign.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/agentic-rag/campaign.py)（379 行）。docstring 第一句就是实验设计："corpus、cases、BM25、检索深度、答题模型、独立评审全部固定，唯一变量是答题者拿一次检索还是能 ReAct 迭代检索"。检索本体在 `offline_retriever.py`（本地法条 BM25，战役只调用它的 `search(query, top_k)`——本页不展开，跑通它不需要知道 BM25 内部）。

---

## 0. 函数清单（一个不漏）

| # | 函数/常量 | 行号 | 一句话作用 | 谁调用它 |
| --- | --- | --- | --- | --- |
| — | `HERE` / `CHAPTER` + sys.path | L25–28 | 路径与导入 | 全文件 |
| — | `ARK_ENDPOINT` / `MOONSHOT_ENDPOINT` | L34–35 | 答题/评审默认端点 | `main` |
| — | `ARTICLE_RE` | L36 | 中文法条号正则（如"第二百三十四条"） | `article_hits` |
| 1 | `parse_json` | L39–45 | 从模型回复抠 JSON（容忍围栏） | `run_case` ×2 |
| 2 | `article_hits` | L48–51 | 金标法条是否字面出现在检索结果里 | `run_case` |
| 3 | `context` | L53–57 | 检索结果列表 → `[chunk_id] 标题\n正文` 文本 | `answer_once`、`judge_prompt` |
| 4 | `citations` | L60–68 | 从答案里数 `[chunk_id]` 引用，判有效性 | `run_case` |
| 5 | `usage` | L71–77 | 回执列表 → token 合计 | `main` |
| 6 | `judge_prompt` | L80–106 | 评审请求（独享检索证据 + 答案） | `run_case` |
| 7 | `Campaign.__init__` | L109–118 | 检索器 + 答题/评审两个客户端 | `main` |
| 8 | `Campaign.search` | L120–121 | BM25 检索的薄封装 | `answer_agentic`（基线直接调 retriever） |
| 9 | `Campaign.answer_once` | L123–141 | **基线臂**：一次检索 → 接地作答 | `run_case` |
| 10 | `Campaign.answer_agentic` | L143–228 | **Agentic 臂**：ReAct 循环 + 预算 + 强制收尾 | `run_case` |
| 11 | `Campaign.run_case` | L230–278 | 一案例两臂编排 + 评审 + 指标 | `main`（线程池） |
| 12 | `aggregate` | L281–290 | 按 臂×难度组 聚合五指标 | `main` |
| 13 | `main` | L293–374 | 并发执行 → 验收门槛 → 假设检验 → 落证据 | 入口 |

---

## 1. `parse_json`（L39–45）

```python linenums="39"
def parse_json(text: str) -> Dict[str, Any]:
    value = (text or "").strip()
    if "```" in value:
        value = value.split("```", 2)[1]
        if value.lstrip().startswith("json"):
            value = value.lstrip()[4:]
    return json.loads(value.strip())
```

与 3-1/2 的 `parse_json` 同款（本仓各战役共享这一模式而非共享代码）：剥 \`\`\` 围栏再 `json.loads`。这里只服务评审回复（两臂的答案都是自由文本）。

---

## 2. `article_hits`（L48–51）：证据召回，不经过任何模型

```python linenums="48"
def article_hits(results: Iterable[Dict[str, Any]], gold: Iterable[str]) -> List[str]:
    combined = "\n".join(str(row.get("text", "")) for row in results)
    return [article for article in gold if article in combined]
```

把检索结果的正文拼成一坨文本，金标法条号（来自数据集的 `gold_articles`）**逐个做子串查找**。返回命中的法条列表，`len(hits)/len(gold)` 就是 recall。"第二百三十四条"这个字符串在不在检索回来的法条正文里——就这么直接。为什么不用 `ARTICLE_RE`？那个正则用于别处抽取法条号；这里金标已经是精确字符串，`in` 足够。

---

## 3. `context`（L53–57）：证据的统一文本格式

```python linenums="53"
def context(results: List[Dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[{row['chunk_id']}] {row['metadata']['title']}\n{row['text']}"
        for row in results
    )
```

每个 chunk 渲染成 `[chunk_id] 标题
正文`。**chunk_id 出现在证据文本里**、答题 system 又要求"每个实质结论后用 [chunk_id] 引用"——引用闭环的物理学：模型只能引用它看得见的 id。这个函数被答题和评审共用，保证两边看到的证据**逐字符相同**。

---

## 4. `citations`（L60–68）：引用的文本级审计

```python linenums="60"
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

正则 `\[(...\_chunk\_\d+)\]` 从答案里抠出全部引用标记（`_chunk_数字` 的形状由分块器保证）。`valid_ids` 是**本次实际返回的** chunk id 集合——引用了没给过的材料，`invalid_count` +1。这抓的是接地性的文本证据："模型引用了一个不存在的证据"比"模型说错了"更根本。

---

## 5. `usage`（L71–77）

回执列表 → prompt/completion/total 三项合计。与 3-1/2 的 `token_totals` 逐字相同——各战役复制了这个小工具而不是共享 import。

---

## 6. `judge_prompt`（L80–106）：评审只见证据与答案

```python linenums="80"
def judge_prompt(case: Dict[str, Any], arm: str, answer: str, retrieved: List[Dict[str, Any]]):
    return [
        {
            "role": "system",
            "content": (
                "你是独立的中文法律问答评审。只根据给出的法条证据评分，不要使用外部知识。"
                "检查结论是否被证据支持、是否覆盖问题的全部法律问题、引用是否真实。"
                "这不是正式法律意见。只返回 JSON。"
            ),
        },
        {
            "role": "user",
            "content": f"""问题：{case['question']}
金标准法条：{json.dumps(case['gold_articles'], ensure_ascii=False)}
实验臂：{arm}
检索证据：
{context(retrieved)}

回答：
{answer}

返回：{{"correctness":1,"completeness":1,"groundedness":1,"citation_quality":1,
"unsupported_claim":false,"reasoning":"..."}}
每项 1-4 分；4=完全正确，3=核心正确但有轻微缺陷，2=有重大遗漏，1=错误。
若存在实质性无证据结论，unsupported_claim=true。""",
        },
    ]
```

注意评审拿到的是**该臂自己的检索证据**（`retrieved` 参数传入），不是两臂的并集——评的是"基于你手上的证据答得怎么样"。`arm` 字段告知实验臂但不引导偏向。四维 + `unsupported_claim` 布尔，与 3-1/2 的评审契约同构（不同实验、同一评审纪律）。

---

## 7. `Campaign.__init__`（L109–118）

```python linenums="109"
class Campaign:
    def __init__(self, args: argparse.Namespace):
        ark_key = os.getenv("ARK_API_KEY")
        judge_key = os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")
        if not ark_key or not judge_key:
            raise RuntimeError("ARK_API_KEY and MOONSHOT_API_KEY/KIMI_API_KEY are required")
        self.args = args
        self.retriever = OfflineRetriever(str(HERE / "laws"))
        self.answer_client = OpenAI(api_key=ark_key, base_url=args.answer_endpoint, timeout=args.timeout, max_retries=3)
        self.judge_client = OpenAI(api_key=judge_key, base_url=args.judge_endpoint, timeout=args.timeout, max_retries=3)
```

三个成员：本地 BM25 检索器（读 `HERE/laws` 下 100+ 份法条 md——**HERE 既是数据根也是输出根**，学习版重定向时要复制 laws/）、答题客户端、评审客户端。端点/模型全走 CLI——同 3-1/2，"代码只要求两把钥匙，不问钥匙是谁的"。

---

## 8. `Campaign.search`（L120–121）

```python linenums="120"
    def search(self, query: str) -> List[Dict[str, Any]]:
        return self.retriever.search(query, top_k=self.args.top_k)
```

两行：给 BM25 检索加个 top_k 默认值的薄封装。基线臂在 `run_case` 里直接调 `self.search(原问题)`；Agentic 臂在循环里反复调它（模型生成的查询）。

---

## 9. `Campaign.answer_once`（L123–141）：基线臂

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

**检索已经在外面做完**（`run_case` 传入 `retrieved`），这里只做一次接地生成。system 四连：只依据所给法条 / 每个实质结论带 `[chunk_id]` / 证据不足必须说明 / 免责声明。`temperature=0 + seed` 固定随机性。这一臂的全部智能空间：**把给定的 5 个 chunk 用好**。

---

## 10. `Campaign.answer_agentic`（L143–228）：Agentic 臂，本文件最长

按三段拆开。

**工具定义与开场（L143–171）**

```python linenums="143"
    def answer_agentic(self, recorder: ChatRecorder, case: Dict[str, Any]):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_law",
                    "description": "Search the authoritative local Chinese statute corpus with BM25.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string", "description": "Focused Chinese legal search query"}},
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            }
        ]
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是 ReAct 法律检索 Agent，只能依据 search_law 返回的本地法条。先分解问题并搜索；"
                    "复杂问题应对每个独立法律问题迭代搜索。确认法条齐全后回答，每个结论用 [chunk_id] 引用。"
                    "不得引用未返回的材料。结尾注明：本回答仅供一般法律信息参考，不构成正式法律意见。"
                ),
            },
            {"role": "user", "content": case["question"]},
        ]
        trajectory = []
        union: Dict[str, Dict[str, Any]] = {}
        final = ""
```

一个工具（`search_law`，只收一个 `query` 参数）、一个系统提示（分解问题→迭代搜索→确认齐全→带引用作答）、两个累积器：`trajectory` 记每轮的思考和搜索（证据保留），`union` 按 chunk_id 去重合并所有轮的检索结果（**Agentic 臂的证据集 = 各次搜索的并集**）。

**ReAct 循环（L173–217）**

```python linenums="173"
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
            response = recorder.create(
                purpose=f"3-8 agentic react {case['id']} iteration {iteration}",
                **request,
            )
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
            for tool_call in message.tool_calls:
                if len([q for row in trajectory for q in row["searches"]]) + len(step["searches"]) >= self.args.max_searches:
                    tool_result = {"error": "search budget exhausted"}
                else:
                    try:
                        query = str(json.loads(tool_call.function.arguments).get("query", "")).strip()
                    except Exception:
                        query = ""
                    rows = self.search(query) if query else []
                    for row in rows:
                        union[row["chunk_id"]] = row
                    tool_result = {"query": query, "results": rows}
                    step["searches"].append(tool_result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )
            trajectory.append(step)
```

逐行要点：`tool_choice="required"` **只在第 1 轮**——强制先动手搜索，不许凭参数知识作答（保证两臂都至少检索过一次，变量收窄到"能否继续搜"）；之后 `auto`，模型自己决定"够了，作答"（无工具调用的回复即 `final`，break）。预算检查在工具执行**之前**：已搜次数（跨轮累计，从 trajectory 数出来）≥ `max_searches`（默认 4）时不再执行，返回 `{"error": "search budget exhausted"}`——预算耗尽是**可观察的工具结果**而非异常，模型下一轮看得见并据此收尾。工具参数 `json.loads` 包了 try——坏 JSON 变空查询、空查询返回空结果，循环不死。检索结果同时进 `messages`（模型可见）和 `union`（最终证据集）。

**强制收尾（L218–228）**

```python linenums="218"
        if not final:
            response = recorder.create(
                purpose=f"3-8 agentic forced final {case['id']}",
                model=self.args.answer_model,
                messages=messages + [{"role": "system", "content": "搜索预算已用完。现在仅根据已返回证据给出带引用的最终回答。"}],
                max_tokens=900,
            )
            final = response.choices[0].message.content or ""
        return final, list(union.values()), trajectory
```

循环上限是 `max_searches + 2` 轮；若模型到最后一轮还在要搜索（没产生 `final`），追加一条 system 强制它基于已有证据作答。**预算烧光 ≠ 失败**——已检索的证据都在 messages 里，只是不许再搜。这与 [task2 system-hint](../task2/system-hint-code.md) 的"submit_result 才算 complete"同款纪律：资源上限与规范终止分开。

---

## 11. `Campaign.run_case`（L230–278）：两臂编排 + 评审 + 指标

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

        arms = {}
        for name, answer, rows, latency, searches in (
            ("baseline", baseline_answer, baseline_results, baseline_ms, 1),
            ("agentic", agent_answer, agent_results, agent_ms, sum(len(s["searches"]) for s in trajectory)),
        ):
            response = judge_recorder.create(
                purpose=f"3-8 independent judge {case['id']} {name}",
                model=self.args.judge_model,
                messages=judge_prompt(case, name, answer, rows),
                temperature=0,
                seed=self.args.seed,
                max_tokens=700,
                response_format={"type": "json_object"},
            )
            judged = parse_json(response.choices[0].message.content or "{}")
            hits = article_hits(rows, case["gold_articles"])
            arms[name] = {
                "answer": answer,
                "retrieved_chunks": rows,
                "evidence": {"gold_articles": case["gold_articles"], "hit_articles": hits,
                             "recall": len(hits) / len(case["gold_articles"])},
                "citations": citations(answer, [row["chunk_id"] for row in rows]),
                "search_count": searches,
                "latency_ms": round(latency, 3),
                "judge": judged,
            }
        return {
            "case": {**case, "complexity": "simple" if case.get("difficulty") == "easy" else "complex"},
            "arms": arms,
            "agentic_trajectory": trajectory,
            "receipts": answer_recorder.calls + judge_recorder.calls,
        }
```

时间测量有个细节：基线的延迟**包含检索时间**（`baseline_search_ms` 加进去了），Agentic 的延迟天然包含循环内所有搜索——两臂的口径对齐（"用户视角的总耗时"）。每个案例独立建 recorder，回执随 case 返回（main 层汇合）。`complexity` 字段在返回前把数据集的 `easy/hard` 翻译成 `simple/complex`——聚合的分组键。

---

## 12. `aggregate`（L281–290）：五指标按组聚合

```python linenums="281"
def aggregate(rows: List[Dict[str, Any]], arm: str, group: str | None = None) -> Dict[str, Any]:
    selected = [row for row in rows if group is None or row["case"]["complexity"] == group]
    return {
        "n": len(selected),
        "evidence_recall": statistics.mean(row["arms"][arm]["evidence"]["recall"] for row in selected),
        "judge_correctness": statistics.mean(float(row["arms"][arm]["judge"].get("correctness", 1)) for row in selected),
        "citation_valid_rate": statistics.mean(1.0 if row["arms"][arm]["citations"]["has_valid_citation"] else 0.0 for row in selected),
        "mean_search_count": statistics.mean(row["arms"][arm]["search_count"] for row in selected),
        "mean_latency_ms": statistics.mean(row["arms"][arm]["latency_ms"] for row in selected),
    }
```

按臂 + 可选的难度组过滤，取五个均值：证据召回（客观）、评审正确性（语义）、引用有效率（文本）、搜索数（成本）、延迟（成本）。`judge.get("correctness", 1)` 缺字段按 1 分（最差）——评审输出缺失不会被当成满分漏过。

---

## 13. `main`（L293–374）：验收门槛与预注册假设

执行部分与 3-1/2 的 main 同构（线程池 + 错误隔离 + 排序），直接看两个课程特有的部分。

**验收门槛（L334–346）**：

```python linenums="334"
    agent_queries = [
        search["query"] for row in rows for step in row["agentic_trajectory"] for search in step["searches"]
    ]
    corpus_files = sorted((HERE / "laws").rglob("*.md"))
    corpus_manifest = [{"path": str(path.relative_to(HERE)), "sha256": sha256_file(path), "bytes": path.stat().st_size} for path in corpus_files]
    acceptance = {
        "real_law_corpus": len(corpus_files) >= 100,
        "labeled_simple_and_complex": set(groups) == {"simple", "complex"},
        "identical_cases_and_corpus": len(rows) == len(cases),
        "one_shot_baseline": all(row["arms"]["baseline"]["search_count"] == 1 for row in rows),
        "live_agent_generated_searches": bool(agent_queries) and all(query.strip() for query in agent_queries),
        ...
    }
```

值得背的三条：`real_law_corpus`（语料 ≥100 份真实法条，不是玩具集）；`one_shot_baseline`（基线真的只搜了一次——从结果反查，不是从代码相信）；`live_agent_generated_searches`（Agentic 的搜索词非空——从 trajectory 里抽出来检查）。**门槛全部从产出反查，不从代码意图相信**。

**预注册假设（L348–353）**：

```python linenums="348"
    hypothesis = {}
    if summary:
        hypothesis = {
            "simple_roughly_ties": abs(summary["agentic"]["simple"]["judge_correctness"] - summary["baseline"]["simple"]["judge_correctness"]) <= 0.5,
            "complex_quality_improves": summary["agentic"]["complex"]["judge_correctness"] > summary["baseline"]["complex"]["judge_correctness"],
            "agentic_adds_latency": summary["agentic"]["overall"]["mean_latency_ms"] > summary["baseline"]["overall"]["mean_latency_ms"],
        }
```

三条假设是书稿结论的方向：简单题打平（≤0.5 分，**不是赢**）、复杂题提升、**必然更慢**。第三条把代价写进假设——只报收益不报成本的实验在这套代码里过不了自己的关。

---

## 完整执行回放（学习版 easy_1 案例）

```text
main
 ├─ 读 evaluation/offline_qa.json → 7 案例
 ├─ Campaign(args) → retriever(laws/) + deepseek 答题客户端 + dashscope 评审客户端
 └─ ThreadPool(3) → run_case(easy_1)
      ├─ 基线: search("故意伤害致人重伤的，如何处罚？") → 5 chunks（含刑法234条）
      │        answer_once → 答案（带 [刑法_chunk_N] 引用）
      ├─ Agentic: 迭代1 (tool_choice=required) → search_law("故意伤害 重伤 量刑")
      │           迭代2 (auto) → 无工具调用 → final
      ├─ 评审 ×2（各自看自己臂的证据） → correctness/completeness/groundedness/citation_quality
      ├─ article_hits → recall 1.0（金标"第二百三十四条"在检索文本里）
      └─ citations → has_valid_citation=True
 → aggregate → baseline{simple,complex,overall} × agentic{...} 五指标
 → 验收门槛（9 条全过）→ hypothesis（3 条全 True）→ write_campaign_evidence
```

实测（[evidence](evidence.md#agentic-rag)）：复杂题召回 0.58→0.92、正确性 3.50→4.00、延迟 1710ms→3725ms——三条预注册假设全部成立。

## 动手验证

1. **把 `--max-searches` 改成 1**：Agentic 臂退化成"强制首搜 + 立即作答"，与基线的差异只剩首轮查询词是模型写的而非原问题——你能单独观察"查询改写"这一项的收益。
2. **把 `tool_choice` 全程改成 "auto"**：模型可能跳过搜索直接作答——对照 2-3 的教训，接地实验最怕的就是这个逃逸口。
3. **读一遍 evidence 里 hard_4 的 `agentic_trajectory`**：看模型怎么把一个多跳问题拆成三次不同查询——那是本实验全部结论的微观机制。
