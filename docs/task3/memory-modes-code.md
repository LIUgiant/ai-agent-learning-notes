# 用户记忆源码精读 · run_evaluation.py 逐函数通读

[实验说明](memory-modes.md) · [实测结果](evidence.md#memory-modes) · [学习运行脚本](../assets/task3/run_memory_modes.py)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>本页按源码顺序把 run_evaluation.py 的每个函数过一遍——先给函数清单证明一个不漏，再逐个拆，最后用一次真实执行把整条调用链串起来。读完本页，你应该能在不打开源码的情况下说出这个文件每一部分在干什么。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号，链接指向课程仓库固定提交；配套文件 `chapter3/experiment_utils.py`（全章共享的证据工具）在用到它的位置一并讲解。**学习运行脚本原文**来自 `run_memory_modes.py`；**教学示意**仅用于理解数据形状。

**主文件**：[chapter3/user-memory/run_evaluation.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/user-memory/run_evaluation.py)（558 行，3-1 与 3-2 两个实验共用一个战役）。task1 的 [memory 笔记](../task1/memory-code.md) 走过 NotesMemoryManager 单机版；本文件是它的战役版：多会话、四模式、独立评审、可断点续跑。

---

## 0. 函数清单（一个不漏）

| # | 函数/常量 | 行号 | 一句话作用 | 谁调用它 |
| --- | --- | --- | --- | --- |
| — | `HERE` / `CHAPTER` | L31–32 | 本文件与 chapter3 目录路径 | 全文件 |
| — | `ARK_ENDPOINT` / `MOONSHOT_ENDPOINT` | L37–38 | 写手/评审的默认端点 | `build_parser` |
| — | `MODES` | L39 | 四种记忆模式元组 | `build_parser`、`mode_call_stats` |
| — | `MODE_INSTRUCTIONS` | L41–59 | 四模式的写手指令（实验的自变量） | `memory_prompt` |
| 1 | `parse_json` | L62–69 | 从模型回复里抠出 JSON（容忍 ``` 围栏） | `run_one` ×3 |
| 2 | `load_cases` | L72–91 | 从 YAML 评测集加载案例（smoke/全量/指定 id） | `main` |
| 3 | `format_history` | L94–103 | 会话 dict → 纯文本（写手输入的最后一层） | `memory_prompt`、`judge_prompt` |
| 4 | `initial_memory` | L106–107 | 各模式的初始记忆值（数组或对象） | `run_one` |
| 5 | `memory_prompt` | L110–124 | 写手请求：旧状态 + 新会话 → 替换后状态 | `run_one` |
| 6 | `answer_prompt` | L127–145 | 答题请求：只有最终记忆 + 问题 | `run_one` |
| 7 | `judge_prompt` | L148–176 | 评审请求：全部原文 + 答案 → 四维分 + 幻觉 | `run_one` |
| 8 | `judge_summary` | L179–188 | 评审 JSON → passed/reward（幻觉一票否决） | `run_one` |
| 9 | `Campaign.__init__` | L191–212 | 建两个客户端、检查点目录与签名 | `main` |
| 10 | `Campaign._checkpoint_path` | L214–216 | 检查点文件名（test_id--mode.json） | `run_one` |
| 11 | `Campaign._write_checkpoint` | L218–225 | 原子写检查点（tmp + replace） | `run_one` 内的闭包 |
| 12 | `Campaign._successful_call` | L227–239 | 按 purpose 找"上次成功的调用"（续跑用） | `run_one` ×3 |
| 13 | `Campaign._content_from_call` | L241–243 | 从回执里取回复文本 | `run_one` ×2 |
| 14 | `Campaign.run_one` | L245–379 | **核心**：一个案例 × 一个模式的完整评估 | `main`（线程池） |
| 15 | `aggregate` | L382–404 | 结果按 模式 × 层 聚合（pass/reward/幻觉率） | `main` |
| 16 | `token_totals` | L407–413 | 回执列表 → token 合计 | `mode_call_stats`、`main` |
| 17 | `mode_call_stats` | L416–429 | 每模式的调用数/token/延迟统计 | `main` |
| 18 | `build_parser` | L432–459 | CLI 参数（模型/端点/预算/检查点目录） | `main` |
| 19 | `main` | L462–557 | 编排：加载→并发执行→聚合→落证据 | 入口 |

配套文件 `experiment_utils.py` 的两个类（用到处再细讲）：`ChatRecorder`（L90–131，记回执的客户端包装）、`write_campaign_evidence`（L135–211，证据落盘 + latest.json）。

---

## 1. `parse_json`（L62–69）：模型输出的第一道清洗

```python linenums="62"
def parse_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
```

把模型回复变成字典。两处容错：空文本变成空串再报错（`text or ""` 防 None）；模型无视"JSON only"指令加了 \`\`\`json 围栏时，切出围栏中间那段、剥掉 `json` 语言标记。**注意它不容忍畸形 JSON**——`json.loads` 直接抛，异常会一路传到 `run_one` 之外记为该格错误（学习版 json_cards 的两格就死在这里，见[实测](evidence.md#memory-modes)）。

被调用三次：写手回复、答题（不经过它，直接取 content）、评审回复。

---

## 2. `load_cases`（L72–91）：评测集的三种取法

```python linenums="72"
def load_cases(root: Path, args: argparse.Namespace) -> List[Dict[str, Any]]:
    paths = sorted(root.glob("layer*/*.yaml"))
    cases = []
    wanted = set(args.case or [])
    by_layer: Dict[str, int] = defaultdict(int)
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if wanted and data.get("test_id") not in wanted:
            continue
        layer = data.get("category")
        if not args.all and not wanted and by_layer[layer] >= args.per_layer:
            continue
        data["_path"] = str(path.resolve())
        cases.append(data)
        by_layer[layer] += 1
    if wanted:
        missing = wanted - {c["test_id"] for c in cases}
        if missing:
            raise ValueError(f"Unknown test ids: {sorted(missing)}")
    return cases
```

三种取法互斥：`--case id` 指定单案例（重复实验用）、`--all` 全量 60 案例、默认每层取前 `--per-layer` 个（smoke 模式，学习版走的就是这个：2/层）。两个细节：`sorted(glob)` 保证案例顺序稳定（可复现）；`data["_path"]` 把 YAML 的绝对路径塞进案例 dict——最后 `write_campaign_evidence` 用它把每个案例文件哈希进证据。指定的 id 不存在直接 `ValueError`，不静默跳过。

---

## 3. `format_history`（L94–103）：会话字典 → 写手能读的文本

```python linenums="94"
def format_history(history: Dict[str, Any]) -> str:
    metadata = json.dumps(history.get("metadata") or {}, ensure_ascii=False)
    lines = [
        f"conversation_id={history.get('conversation_id')}",
        f"timestamp={history.get('timestamp')}",
        f"metadata={metadata}",
    ]
    for message in history.get("messages", []):
        lines.append(f"{str(message.get('role', '')).upper()}: {message.get('content', '')}")
    return "\n".join(lines)
```

评测集里每个会话是个 dict（id/时间戳/元数据/消息列表），写手和评审都要读它。格式是"头部三行元数据 + 每条消息一行 `ROLE: 内容`"。**role 大写**是个容易被忽略的选择——`USER:`/`ASSISTANT:` 在纯文本里更醒目，降低模型把角色看漏的概率。这个函数被 `memory_prompt` 和 `judge_prompt` 共用：写手看单个会话，评审看全部会话拼起来的长文本。

---

## 4. `initial_memory`（L106–107）：模式差异的第一处体现

```python linenums="106"
def initial_memory(mode: str) -> Any:
    return [] if mode != "json_cards" else {}
```

一行函数，但它是模式差异的**类型级**体现：json_cards 是层级对象（初始 `{}`），其余三种是数组（初始 `[]`）。后面 `run_one` 里 `json.dumps(memory)` 对两种类型都能序列化，所以类型分歧不会炸——但它提醒你：四模式不止指令不同，连数据结构都不同。

---

## 5. `memory_prompt`（L110–124）：写手的完整请求

```python linenums="110"
def memory_prompt(mode: str, memory: Any, history: Dict[str, Any], session_index: int) -> List[Dict[str, str]]:
    system = (
        "You are a long-term memory writer. Select only facts that may help a future "
        "assistant, but retain exact values, ownership, event status, dates, provenance, "
        "and relationships. Apply updates without losing still-valid facts. Never answer "
        "the conversation. Return JSON only as {\"memory\": ...}. " + MODE_INSTRUCTIONS[mode]
    )
    user = (
        f"MEMORY MODE: {mode}\nSESSION INDEX: {session_index}\n\n"
        "CURRENT MEMORY STATE (the only retained information from older sessions):\n"
        f"{json.dumps(memory, ensure_ascii=False)}\n\n"
        "NEW SESSION (analyze this session, then replace the memory state):\n"
        f"{format_history(history)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
```

system 是**通用约束 + 模式指令**拼接：通用部分管纪律（保留精确值/所有权/状态/日期/来源/关系；更新不丢旧事实；**绝不回答对话**；只返回 `{"memory": ...}`），`MODE_INSTRUCTIONS[mode]` 管形状（这就是实验唯一自变量）。user 部分三段式：模式与轮次 → 当前状态（`json.dumps` 重新序列化）→ 新会话文本。括号里那句 "the only retained information" 是说给模型听的语境说明——旧会话原文**不在这个请求里的任何地方**。

**写手看不到未来问题**——它必须自己猜什么值得记，这是记忆任务的本质难度。

---

## 6. `answer_prompt`（L127–145）：换一个"人生"来答题

```python linenums="127"
def answer_prompt(mode: str, memory: Any, question: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are an assistant in a brand-new session. The supplied long-term memory "
                "is your only source about this user: you cannot access earlier raw dialogue. "
                "Answer accurately, resolve ambiguity, connect sessions, and proactively warn "
                "about material risks. Do not invent facts."
            ),
        },
        {
            "role": "user",
            "content": (
                f"MEMORY MODE: {mode}\nLONG-TERM MEMORY:\n"
                f"{json.dumps(memory, ensure_ascii=False)}\n\nUSER QUESTION:\n{question}"
            ),
        },
    ]
```

答题者和写手用**同一个模型**（都是 `writer_client`），但扮演完全不同的角色。system 里的四个动词就是评分维度的前身：answer accurately（precision）、resolve ambiguity（reasoning）、connect sessions（recall）、**proactively warn**（proactivity——主动预警，layer3 考的就是这个）。"you cannot access earlier raw dialogue" 把信息边界说死：除了记忆你别无所有。

---

## 7. `judge_prompt`（L148–176）：评审独享全部原文

```python linenums="148"
def judge_prompt(case: Dict[str, Any], answer: str) -> List[Dict[str, str]]:
    source = "\n\n".join(format_history(h) for h in case["conversation_histories"])
    system = (
        "You are a strict independent judge of a memory assistant. Use only the authoritative "
        "conversation source. Score precision, recall, reasoning, and proactivity from 1 to 4. "
        "A material unsupported or contradicted factual claim is a hallucination veto. Return "
        "JSON only."
    )
    user = f"""AUTHORITATIVE SOURCE:
{source}

QUESTION: {case['user_question']}
ANSWER: {answer}
EVALUATION CRITERIA: {case['evaluation_criteria']}
EXPECTED BEHAVIOR: {case.get('expected_behavior', '')}

Return exactly:
{{"dimensions": {{"precision": {{"score": 1, "reasoning": "...", "evidence": []}},
...
Scale: 4 fully meets the concrete criterion; 3 meets the core with only a minor
defect; 2 has a material omission; 1 misses/contradicts the core. Asking a
targeted clarification is correct when several entities plausibly match.
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
```

三方信息不对称在这里完成闭环：评审拿到**全部会话原文**（`conversation_histories` 全量 `format_history` 拼接）+ 案例 YAML 里的评分标准（`evaluation_criteria`）和期望行为。两个值得背下来的细节：

- 评分标准**来自数据集**而不是写死在代码里——每个案例可以定义自己"什么算对"，加新案例不用改代码；
- 末尾那句 "Asking a targeted clarification is correct..."——多实体歧义时**追问是正确行为**，宁可问不可猜。

---

## 8. `judge_summary`（L179–188）：JSON → 分数与一票否决

```python linenums="179"
def judge_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    dims = raw.get("dimensions") or {}
    scores = {}
    for name in ("precision", "recall", "reasoning", "proactivity"):
        score = int((dims.get(name) or {}).get("score", 1))
        scores[name] = min(4, max(1, score))
    hallucination = bool((raw.get("hallucination") or {}).get("detected"))
    passed = not hallucination and all(scores[x] >= 3 for x in ("precision", "recall", "reasoning"))
    reward = 0.0 if hallucination else statistics.mean(scores.values()) / 4.0
    return {"scores": scores, "hallucination_veto": hallucination, "passed": passed, "reward": reward}
```

评审输出到战绩的翻译层，三个规则：分数钳制在 [1,4]（评审说 5 或 0 都被夹回量程，聚合不炸）；**幻觉一票否决**（`reward = 0.0`，`passed = False`——四维全 4 分但编了一个日期，全盘作废）；`passed` 只看三维（precision/recall/reasoning ≥ 3），proactivity 只进 reward 不卡 pass——主动预警是加分项不是及格线。

---

## 9–13. `Campaign` 类：客户端、检查点与续跑

### `__init__`（L191–212）

```python linenums="191"
class Campaign:
    def __init__(self, args: argparse.Namespace):
        ark_key = os.getenv("ARK_API_KEY") or os.getenv("DOUBAO_API_KEY")
        moonshot_key = os.getenv("MOONSHOT_API_KEY")
        if not ark_key or not moonshot_key:
            raise RuntimeError("ARK_API_KEY and MOONSHOT_API_KEY are both required")
        self.args = args
        self.writer_client = OpenAI(
            api_key=ark_key, base_url=args.writer_endpoint, timeout=args.timeout, max_retries=3
        )
        self.judge_client = OpenAI(
            api_key=moonshot_key, base_url=args.judge_endpoint, timeout=args.timeout, max_retries=3
        )
        self.checkpoint_dir = args.checkpoint_dir.resolve()
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_signature = {
            "writer_endpoint": args.writer_endpoint,
            "writer_model": args.writer_model,
            "judge_endpoint": args.judge_endpoint,
            "judge_model": args.judge_model,
            "seed": args.seed,
        }
```

两个客户端：写手（记忆更新 + 答题）和评审，端点/模型全部来自 CLI 参数——**代码只规定"要有两把不同的钥匙"，不规定钥匙属于谁**（学习版就是从这里接进 DeepSeek + DashScope 的）。`checkpoint_signature` 把五个影响结果的参数锁进签名：续跑时签名对不上直接拒绝，防止"换模型续旧跑"的混装证据。

### `_checkpoint_path` / `_write_checkpoint`（L214–225）

```python linenums="214"
    def _checkpoint_path(self, test_id: str, mode: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in test_id)
        return self.checkpoint_dir / f"{safe_id}--{mode}.json"

    @staticmethod
    def _write_checkpoint(path: Path, payload: Dict[str, Any]) -> None:
        temporary = path.with_suffix(f".{threading.get_ident()}.tmp")
        temporary.write_text(
            json.dumps(jsonable(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
```

文件名 = 安全化的 test_id + 模式（一个案例 × 一个模式 = 一个独立检查点文件，24 格互不干扰）。原子写的两个要点：临时文件名带**线程 id**（多线程同时写不同检查点不会互相踩 tmp 文件）；`replace` 是原子重命名——读方永远看到完整文件，不会读到半截 JSON。`jsonable`（experiment_utils L46–62）负责把 SDK 响应对象递归转成可序列化的 dict。

### `_successful_call` / `_content_from_call`（L227–243）

```python linenums="227"
    @staticmethod
    def _successful_call(calls: List[Dict[str, Any]], purpose: str) -> Dict[str, Any] | None:
        for call in reversed(calls):
            choices = (call.get("response") or {}).get("choices") or []
            finish_reason = choices[0].get("finish_reason") if choices else None
            if (
                call.get("purpose") == purpose
                and "response" in call
                and "error" not in call
                and finish_reason != "length"
            ):
                return call
        return None

    @staticmethod
    def _content_from_call(call: Dict[str, Any]) -> str:
        return call["response"]["choices"][0]["message"]["content"]
```

续跑的核心查询：给一个 purpose（比如 `"... memory update layer3_01 enhanced_notes session 2"`），在历史回执里**倒序**找最近一次满足三条件的调用——purpose 匹配、有响应、无错误，且 **`finish_reason != "length"`**。最后这条最微妙：被 max_tokens 截断的回复不算成功，续跑时这一步会重新调用（截断的 JSON 解析必炸，重调是唯一出路）。`_content_from_call` 就是从回执 dict 里挖出文本的便捷读法。

---

## 14. `run_one`（L245–379）：一个格子的完整生命

这是最长的函数（135 行），按执行阶段拆开看。

**阶段一：恢复或新建检查点（L245–269）**

```python linenums="245"
    def run_one(self, case: Dict[str, Any], mode: str) -> Dict[str, Any]:
        checkpoint_path = self._checkpoint_path(case["test_id"], mode)
        if checkpoint_path.exists():
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if checkpoint.get("signature") != self.checkpoint_signature:
                raise RuntimeError(
                    f"checkpoint signature mismatch for {case['test_id']} {mode}; "
                    "use a different --checkpoint-dir"
                )
        else:
            checkpoint = {..."status": "running", "memory_states": [], "writer_calls": [], "judge_calls": []...}
        if checkpoint.get("status") == "completed" and checkpoint.get("result"):
            result = dict(checkpoint["result"])
            result["_receipts"] = checkpoint.get("writer_calls", []) + checkpoint.get("judge_calls", [])
            result["_resumed"] = True
            return result
```

已有检查点 → 验签名 → 已完成的直接返回缓存结果（`_resumed=True` 标记，最终打印时区分 live/resumed）。

**阶段二：包装录音客户端（L271–290）**

```python linenums="271"
        def persist_calls() -> None:
            checkpoint["writer_calls"] = writer.calls
            checkpoint["judge_calls"] = judge.calls
            checkpoint["updated_at_epoch"] = time.time()
            self._write_checkpoint(checkpoint_path, checkpoint)

        class JobRecorder(ChatRecorder):
            def create(inner_self, *, purpose: str, **request: Any) -> Any:
                try:
                    return super(JobRecorder, inner_self).create(purpose=purpose, **request)
                finally:
                    persist_calls()

        writer = JobRecorder(self.writer_client, "ark", self.args.writer_endpoint)
        judge = JobRecorder(self.judge_client, "moonshot", self.args.judge_endpoint)
        writer.calls = list(checkpoint.get("writer_calls", []))
        judge.calls = list(checkpoint.get("judge_calls", []))
```

`ChatRecorder`（[experiment_utils.py · L90–L131](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/experiment_utils.py#L90)）是全章共享的回执层：包装任意 OpenAI 兼容客户端，`create(purpose=..., **request)` 转发调用并记录 request/response/usage/latency——**设计上从不序列化凭据**。子类 `JobRecorder` 用 `finally` 保证**每次调用后（无论成败）都把全部回执写回检查点**——崩溃点之前的每一次 API 调用都有据可查。注意 recorder 的 provider 标签是课程硬编码的 `"ark"`/`"moonshot"`，学习版的真实端点在回执的 endpoint 字段里。

**阶段三：会话循环——状态替换（L292–328）**

```python linenums="292"
        states = list(checkpoint.get("memory_states", []))
        memory: Any = states[-1]["memory"] if states else initial_memory(mode)
        for index, history in enumerate(case["conversation_histories"], start=1):
            if index <= len(states):
                continue
            messages = memory_prompt(mode, memory, history, index)
            purpose = f"3-1/3-2 memory update {case['test_id']} {mode} session {index}"
            prior_call = self._successful_call(writer.calls, purpose)
            if prior_call:
                content = self._content_from_call(prior_call)
            else:
                response = writer.create(
                    purpose=purpose,
                    model=self.args.writer_model,
                    messages=messages,
                    temperature=0,
                    seed=self.args.seed,
                    max_tokens=self.args.memory_max_tokens,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
            parsed = parse_json(content)
            memory = parsed.get("memory", parsed)
            states.append(
                {
                    "session_index": index,
                    "conversation_id": history.get("conversation_id"),
                    "memory": memory,
                    "isolation": {
                        "prior_raw_histories_supplied": 0,
                        "current_memory_supplied": True,
                        "new_history_supplied": history.get("conversation_id"),
                    },
                }
            )
            checkpoint["memory_states"] = states
            persist_calls()
```

四步循环：跳过已完成的会话（`index <= len(states)`——断点续跑的粒度到**单个会话**）；优先复用上次成功的调用（`_successful_call`）；否则真调用（`temperature=0, seed, json_object`——把随机性压死）；`parsed.get("memory", parsed)` 容忍模型漏包一层键。每个状态的 `isolation` 字段是**自我声明**：旧原文供给数 0、当前记忆已供给、新会话的 conversation_id——验收时全量核查（`isolation_ok`），"只靠记忆"从口头承诺变成逐状态检查的字段。

**阶段四：答题与评审（L330–372）**

```python linenums="330"
        answer_purpose = f"3-1/3-2 answer {case['test_id']} {mode}"
        answer_call = self._successful_call(writer.calls, answer_purpose)
        if answer_call:
            answer = self._content_from_call(answer_call) or ""
        else:
            answer_response = writer.create(
                purpose=answer_purpose,
                model=self.args.writer_model,
                messages=answer_prompt(mode, memory, case["user_question"]),
                temperature=0,
                seed=self.args.seed,
                max_tokens=self.args.answer_max_tokens,
            )
            answer = answer_response.choices[0].message.content or ""
        checkpoint["answer"] = answer
        persist_calls()

        judge_purpose = f"3-1/3-2 independent judge {case['test_id']} {mode}"
        ...
            judge_response = judge.create(
                purpose=judge_purpose,
                model=self.args.judge_model,
                messages=judge_prompt(case, answer),
                temperature=0,
                seed=self.args.seed,
                max_tokens=self.args.judge_max_tokens,
                response_format={"type": "json_object"},
            )
            judge_content = judge_response.choices[0].message.content
        judge_raw = parse_json(judge_content)
        result = {
            "test_id": case["test_id"],
            "layer": case["category"],
            "title": case["title"],
            "mode": mode,
            "session_count": len(case["conversation_histories"]),
            "memory_states": states,
            "answer": answer,
            "judge": judge_summary(judge_raw),
            "judge_raw": judge_raw,
        }
        checkpoint["status"] = "completed"
        checkpoint["result"] = result
        persist_calls()
        result["_receipts"] = writer.calls + judge.calls
        result["_resumed"] = False
        return result
```

答题（注意**没有** `response_format`——自由文本回答）和评审（有 json_object）各自走一遍"复用或真调"。最后 `status="completed"` 落盘，回执随 result 一起返回给 main 层。**答对的功劳记在谁头上**？写手（状态质量）、答题者（利用状态的能力）、评审（打分）——三者被回执和状态分别记录，复盘时可拆开归因。

---

## 15–17. 聚合与统计：`aggregate` / `token_totals` / `mode_call_stats`

```python linenums="382"
def aggregate(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for result in results:
        groups[result["mode"]][result["layer"]].append(result)
    output: Dict[str, Any] = {}
    for mode, layers in groups.items():
        output[mode] = {}
        all_rows = []
        for layer, rows in sorted(layers.items()):
            all_rows.extend(rows)
            output[mode][layer] = {
                "n": len(rows),
                "pass_rate": sum(r["judge"]["passed"] for r in rows) / len(rows),
                "mean_reward": statistics.mean(r["judge"]["reward"] for r in rows),
                "hallucination_rate": sum(r["judge"]["hallucination_veto"] for r in rows) / len(rows),
            }
        output[mode]["overall"] = {...同上，对 all_rows...}
```

双层 defaultdict 按 模式 → 层 分桶，每桶算三个数：pass 率、平均 reward、幻觉率。`sum(bool)` 是 Python 里数 True 的惯用法。

```python linenums="407"
def token_totals(calls: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for call in calls:
        usage = call.get("usage") or {}
        for key in totals:
            totals[key] += int(usage.get(key) or 0)
    return totals

def mode_call_stats(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    output = {}
    for mode in MODES:
        selected = [call for call in calls if f" {mode}" in str(call.get("purpose", ""))]
        latencies = [float(call.get("latency_ms") or 0) for call in selected]
        output[mode] = {
            "api_calls": len(selected),
            "token_usage": token_totals(selected),
            "latency_ms": {"total": sum(latencies),
                           "mean_per_call": statistics.mean(latencies) if latencies else 0},
        }
    return output
```

`mode_call_stats` 的筛选条件 `f" {mode}" in purpose` 利用了 purpose 命名规范（`... {test_id} {mode} session {n}`）——**按模式统计成本不需要另记账本，purpose 字符串就是账本**。这就是前面所有 `purpose=f"..."` 命名纪律的回报。

---

## 18–19. `build_parser` 与 `main`：编排与证据

`build_parser`（L432–459）的参数分三组：范围（`--all/--case/--per-layer/--mode`）、模型（`--writer-model/--judge-model/--writer-endpoint/--judge-endpoint`，**端点和钥匙解耦**是学习版能换 provider 的全部原因）、预算与检查点（`--memory-max-tokens` 6000 / `--answer-max-tokens` 1200 / `--judge-max-tokens` 1800 / `--checkpoint-dir` / `--workers` 4 / `--seed` 37）。

```python linenums="462"
def main() -> int:
    args = build_parser().parse_args()
    cases = load_cases(args.test_cases_dir.resolve(), args)
    modes = tuple(args.mode or MODES)
    expected_total = len(cases) * len(modes)
    print(f"Running {len(cases)} cases × {len(modes)} modes = {expected_total} evaluations")
    campaign = Campaign(args)
    results = []
    calls: List[Dict[str, Any]] = []
    errors = []
    jobs = [(case, mode) for case in cases for mode in modes]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {pool.submit(campaign.run_one, case, mode): (case["test_id"], mode) for case, mode in jobs}
        for future in concurrent.futures.as_completed(future_map):
            test_id, mode = future_map[future]
            try:
                result = future.result()
                calls.extend(result.pop("_receipts", []))
                resumed = result.pop("_resumed", False)
                results.append(result)
                marker = "resumed" if resumed else "live"
                print(f"[{len(results)}/{expected_total}] {test_id} {mode}: reward={result['judge']['reward']:.3f} ({marker})")
            except Exception as exc:
                errors.append({"test_id": test_id, "mode": mode, "type": type(exc).__name__, "error": str(exc)})
                print(f"[ERROR] {test_id} {mode}: {exc}", file=sys.stderr)
```

`main` 的编排：案例 × 模式展开成 job 列表，4 线程并发 `run_one`；**单格异常不炸全场**——记进 errors，其余格继续（`_receipts`/`_resumed` 这两个下划线字段在这里被 pop 掉，不进最终结果）。收尾处三件事：按 (test_id, mode) 排序保证输出稳定；算 `full_suite`（60 案例 × 4 模式 = 240 且零错误才 passed，否则 partial/blocked）；组装 evidence（status/scope/configuration/acceptance/summary/results）。

最后调用 `write_campaign_evidence(HERE, "3-1-and-3-2", evidence, calls, input_paths=[run_evaluation.py, *案例文件])`——[experiment_utils.py · L135–211](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/experiment_utils.py#L135) 写四个文件：`evidence.json` → `receipts.json` → `manifest.json`（三者哈希 + 输入文件哈希）→ **最后** `latest.json`。写入顺序就是语义：*"latest.json is written last, so a partial campaign can never look current"*——半途崩溃的 run 留在 runs/ 里可查，但不会占据"最新"位。

!!! warning "学习版踩过的坑（复跑必读）"
    `input_paths` 引用 `HERE/run_evaluation.py`。学习脚本重定向 `HERE` 到自己的运行目录后，这个文件**不存在**——全部 API 调用完成后在写证据时崩溃（本任务踩过，回执全丢）。修法：把入口脚本复制进运行目录。同理，检查点目录默认在 `HERE/validation/checkpoints/` 下，**每个新时间戳目录都是空检查点**——想续跑必须 `--checkpoint-dir` 显式指回旧目录。

---

## 完整执行回放（学习版一次真实运行）

把上面所有函数按真实调用顺序串起来（layer3_01 × enhanced_notes 这一格）：

```text
main
 ├─ build_parser → args（writer=deepseek-flash @ deepseek, judge=qwen3.7-plus @ dashscope）
 ├─ load_cases → 6 案例（每层前 2）
 ├─ Campaign(args) → writer_client / judge_client / 检查点签名
 └─ ThreadPool(4) → run_one(layer3_01, enhanced_notes)
      ├─ _checkpoint_path → layer3_01_travel_coordination--enhanced_notes.json（不存在 → 新建）
      ├─ JobRecorder × 2 包装客户端
      ├─ 会话1: memory_prompt(notes→enhanced, 初始[], 会话1)
      │    └─ writer.create(temperature=0, seed=37, json_object) → parse_json → 记忆 S1
      ├─ 会话2: memory_prompt(S1, 会话2) → S2        ← 会话1 原文从此消失
      ├─ 会话3: memory_prompt(S2, 会话3) → S3
      ├─ answer_prompt(S3, "旅行安排有什么要注意的？") → 答案（含"护照最紧急"）
      ├─ judge_prompt(全部3个会话原文 + 答案) → 四维分 + 幻觉判定
      ├─ judge_summary → passed=True, reward=0.969
      └─ _write_checkpoint(completed)
 → aggregate → 四模式×三层表     → mode_call_stats → 每模式成本
 → write_campaign_evidence → evidence/receipts/manifest/latest.json
```

实测数字见 [evidence.md#memory-modes](evidence.md#memory-modes)：enhanced_notes 这一格 6 次调用（3 写手 + 1 答题 + 1 评审 + …），全战役 88 次调用。

## 动手验证

1. **把 `--seed` 从 37 改成别的**：检查点签名变了——所有旧检查点拒绝续跑，全量重跑。签名机制防的就是"半路换条件还当同一场实验"。
2. **删掉 `finish_reason != "length"` 这个条件**：续跑会把截断的半截 JSON 当成功复用，`parse_json` 当场炸——这个条件是续跑正确性的隐性守卫。
3. **给 `run_one` 的会话循环里加一行打印 memory**：你能亲眼看到状态从 `[]` 一步步长成带 Jessica 保单细节的段落——这比任何图表都直观。
