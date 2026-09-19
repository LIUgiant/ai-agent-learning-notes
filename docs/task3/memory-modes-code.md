# 用户记忆源码精读 · 一个状态字段怎样跨会话存活

[实验说明](memory-modes.md) · [实测结果](evidence.md#memory-modes) · [学习运行脚本](../assets/task3/run_memory_modes.py)

<div class="design-lead"><span>逐步搭建 / READ THE CODE</span><p>先看一个"只有记忆没有历史"的会话循环怎样被拼出来，再逐个拆四种记忆模式的指令差异，最后看评审的一票否决与检查点的续跑语义。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号（chapter3/user-memory/run_evaluation.py 与 chapter3/experiment_utils.py）；**学习运行脚本原文**来自 `run_memory_modes.py`；**教学示意**仅用于理解数据形状。task1 的 [memory 笔记](../task1/memory-code.md) 走过 NotesMemoryManager 的单机持久化，本页是它的上一层：**多会话、四模式、外部评审**的完整战役。

## 本页阅读路线

生命周期 → 四模式指令 → 记忆写手 prompt → 隔离证明 → 问答与评审 → 一票否决口径 → 检查点续跑 → 证据落盘 → 学习版结果解读。

---

## 1. 生命周期：会话流进，状态流出，历史蒸发

**遇到的问题**

"长期记忆"要证明的不是"能存"，而是**旧会话的原文可以丢**——从第二个会话起，写手只拿得到上一轮的*记忆状态*和*新会话*。如果记忆没把关键事实带过去，它就永远丢了。

**设计思路**

把每个案例做成多个会话（conversation_histories），逐个喂给写手；每轮的输入里**刻意不含**旧会话原文，并把这件事记录进证据。

**关键代码**

**课程源码原文** · [run_evaluation.py · L292–L328](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/user-memory/run_evaluation.py#L292)：

```python linenums="292"
states = list(checkpoint.get("memory_states", []))
memory: Any = states[-1]["memory"] if states else initial_memory(mode)
for index, history in enumerate(case["conversation_histories"], start=1):
    if index <= len(states):
        continue
    messages = memory_prompt(mode, memory, history, index)
    purpose = f"3-1/3-2 memory update {case['test_id']} {mode} session {index}"
    ...
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
```

**执行过程：看数据怎样变**

一个 3 会话案例的流转（教学示意）：

```text
会话1 → 写手(旧记忆=空, 会话1) → 记忆状态 S1
会话2 → 写手(旧记忆=S1,  会话2) → 记忆状态 S2   ← 会话1 的原文从此不可见
会话3 → 写手(旧记忆=S2,  会话3) → 记忆状态 S3
新会话 → 答题者(只有 S3, 用户问题) → 答案
评审(全部会话原文 + 答案) → 四维分数 + 幻觉否决
```

`isolation.prior_raw_histories_supplied: 0` 是每轮落盘的**自我声明**，验收时全量核查（`isolation_ok`，L496–L500）——"只靠记忆"不是口头承诺，是逐状态检查的字段。

**接回真实源码**

注意评审反而拿到**全部会话原文**（`judge_prompt` 里 `case["conversation_histories"]` 全量格式化，L149）——评审是"事后审计者"，可以看一切；被评的人不行。这是模拟器和考官的信息不对称设计。

**动手验证**

如果写手在第 2 轮不小心把会话 1 的原文整段塞进记忆，`isolation` 字段能发现吗？

??? tip "先预测，再展开对照"
    发现不了——isolation 只记录**请求里带了什么**（由课程代码构造，必然合规），不检查记忆**内容**是否泄漏原文。会话原文若被复制进记忆，效果上等于绕过了"只靠记忆"的约束。课程把构造权收在代码里（模型只产 JSON），所以这条通道实际堵死了；但若自己实现，"记忆里抄原文"是要单独设防的（例如长度/重叠率检查）。

---

## 2. 四模式：指令即 schema

**遇到的问题**

"记忆用数组还是对象、一条记多细"没有唯一答案。与其实现四套存储引擎，不如让**同一段写手逻辑**配四种指令，比的就是数据形状本身。

**关键代码**

**课程源码原文** · [run_evaluation.py · L41–L59](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/user-memory/run_evaluation.py#L41)：

```python linenums="41"
MODE_INSTRUCTIONS = {
    "notes": (
        "Store memory as an array of minimal standalone factual notes. Split a "
        "complex statement into atomic facts; keep exact names, identifiers and dates."
    ),
    "enhanced_notes": (
        "Store memory as an array of contextual paragraphs. Each paragraph must retain "
        "the entity, event, time, status, and relationships needed to interpret it."
    ),
    "json_cards": (
        "Store memory as a hierarchical JSON object using category/subcategory/key/value "
        "organization. Preserve multi-entity distinctions and historical status."
    ),
    "advanced_json_cards": (
        "Store memory as an array of cards. Every card must include category, card_key, "
        "backstory, person, relationship, timestamp, status, and a facts object. Keep "
        "conflicting instructions as ordered versions rather than silently merging them."
    ),
}
```

**执行过程：看数据怎样变**

同一句话"10 月 5 日 Jessica 打电话给 Chase 把副卡持有人换成她妹妹"在四种模式里的形状：

| 模式 | 形状 | 保留了什么 | 丢了什么 |
| --- | --- | --- | --- |
| notes | `["Jessica 的 Chase 副卡持有人于 10-05 换为其妹"]` | 原子事实、精确值 | 事件间关系、状态演变 |
| enhanced_notes | 一段含人物/时间/动作/状态/关联的段落 | 上下文完整 | ——（体积大） |
| json_cards | `{finance: {credit_card: {authorized_user: ...}}}` 层级 | 分类结构 | 跨类别的关联 |
| advanced_json_cards | 卡片对象数组（含 backstory/status/facts） | 演变史（冲突保序） | ——（体积最大） |

`initial_memory`（L106–L107）还有一个易漏的细节：json_cards 的初始状态是**对象** `{}`，其余是**数组** `[]`——模式的差别连初始类型都不同。

**接回真实源码**

写手 system prompt（L111–L116）在指令后追加统一的硬约束：`"Apply updates without losing still-valid facts. Never answer the conversation. Return JSON only as {\"memory\": ...}"`——更新不丢旧事实、**绝不回答对话**（写手只做记忆，答题是另一个角色）。

**动手验证**

"用户上周说用工资卡还款，这周改用新办的储蓄卡"——哪种模式最不可能把旧卡号弄丢或错误覆盖？

??? tip "先预测，再展开对照"
    advanced_json_cards（`Keep conflicting instructions as ordered versions`——冲突保序，新旧并存）。notes 只会各存一条原子事实，关系靠答题者自己拼；enhanced_notes 靠段落叙述保留演变。这正是它在 layer2/3 复杂案例上不输的原因——代价是体积与写手出错的表面积（见第 9 节）。

---

## 3. 记忆写手的请求：状态替换语义

**关键代码**

**课程源码原文** · [run_evaluation.py · L110–L124](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/user-memory/run_evaluation.py#L110)：

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

**执行过程：看数据怎样变**

- **"replace the memory state"** 是替换语义不是追加语义：写手返回的 JSON 整体成为新状态。做对了，更新天然生效；做错了（漏抄旧事实），**丢失无法恢复**——记忆系统没有"回收站"；
- 请求里 `json.dumps(memory)` 每轮重新序列化当前状态——第 k 轮请求的体积 ≈ 状态k-1 + 会话k。对比 [2-3 KV Cache](../task2/kv-cache-code.md)：这是**追加式重建**，前缀（system + 旧状态）逐轮变化，缓存命中率天然不高——记忆压缩（让状态别膨胀）在这里同时也是缓存优化；
- 写手调用参数（L303–L311）：`temperature=0, seed=args.seed, response_format={"type":"json_object"}, max_tokens=6000`——零温 + 固定种子 + JSON 强制格式，把随机性压到最低。

**动手验证**

第 3 轮写手请求的 prompt 里，会话 1 的内容以什么形式存在？

??? tip "先预测，再展开对照"
    只以"写手当时选择保留进 S1 的那些事实"存在。如果写手第 1 轮漏记了某个事实，第 3 轮**不可能**再见到它——错误会随轮次单调放大。这也是评审四维里单独设 recall（漏没漏）的原因。

---

## 4. 问答与评审：信息不对称的对局

**关键代码**

**课程源码原文** · [run_evaluation.py · L127–L145](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/user-memory/run_evaluation.py#L127)（答题）：

```python linenums="127"
{
    "role": "system",
    "content": (
        "You are an assistant in a brand-new session. The supplied long-term memory "
        "is your only source about this user: you cannot access earlier raw dialogue. "
        "Answer accurately, resolve ambiguity, connect sessions, and proactively warn "
        "about material risks. Do not invent facts."
    ),
},
```

**课程源码原文** · [run_evaluation.py · L179–L188](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/user-memory/run_evaluation.py#L179)（评分口径）：

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
```

**执行过程：看数据怎样变**

三方信息结构：

```text
写手   : 看到 旧状态 + 新会话        （看不到未来问题！）
答题者 : 看到 最终状态 + 用户问题    （看不到任何原文）
评审   : 看到 全部会话原文 + 答案    （独享 ground truth）
```

注意**写手看不到未来会问什么**——它必须猜测"什么值得记"。而 proactivity（主动性）维度考的是答题者能否利用记忆里的时间敏感信息**主动预警**（比如护照下周到期）。

评分口径两个细节：

- **幻觉一票否决**：`reward = 0.0 if hallucination`——四维全 4 分但编造一个事实，reward 归零。`passed` 同样要求无幻觉且 precision/recall/reasoning ≥ 3（proactivity 不影响 pass，只影响 reward）；
- 分数被 `min(4, max(1, ...))` 钳制——评审 JSON 里超界的分数（0 或 5）不会炸聚合，只会被夹回量程。

**接回真实源码**

学习版的评审是 DashScope 的 qwen3.7-plus、写手/答题是 DeepSeek——**跨厂商**满足"independent judge"门槛（课程配置块记 `judge_is_external_to_writer: True`）。评审 prompt 只允许依据给出的法条式证据源，不允许外部知识。

**动手验证**

答题者反问澄清（"您说的是 2020 年的护照还是 2024 年新办的？"）而不是直接作答，会得低分吗？

??? tip "先预测，再展开对照"
    不会。judge prompt 明文：`Asking a targeted clarification is correct when several entities plausibly match`——**在多实体歧义时，澄清是正确行为**。宁可问清，不可猜编。这是记忆系统"知道自己不知道"的评分激励。

---

## 5. 检查点：purpose 命名与"长度截断不算成功"

**遇到的问题**

24 个评估并发跑，中途任何一格崩溃怎么办？重跑谁、跳过谁，判据必须精确到**单次调用**。

**关键代码**

**课程源码原文** · [run_evaluation.py · L227–L239](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/user-memory/run_evaluation.py#L227)：

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
```

**执行过程：看数据怎样变**

- 每次调用带唯一 `purpose` 字符串（`"3-1/3-2 memory update <test_id> <mode> session <n>"`）——恢复时按 purpose 精确找回"这一步"的响应，**倒序**取最近一次成功；
- `finish_reason != "length"`：**被 max_tokens 截断的响应不算成功**，恢复时会重新调用。截断的记忆状态 JSON 解析必炸，重调是唯一出路；
- `JobRecorder`（L280–L285）在**每次调用后**（finally）把 calls 写回检查点文件——崩溃点之前的工作全部保住；
- 检查点签名（L206–L212）锁端点/模型/种子：换模型后旧检查点拒绝复用（`checkpoint signature mismatch`）。

学习版踩过的坑值得记录：检查点目录默认 `HERE/validation/checkpoints/...`，HERE 重定向后**每个新时间戳目录都是空检查点**——想续跑必须显式 `--checkpoint-dir` 指回旧目录，否则等于全量重跑。

**动手验证**

一个记忆更新调用成功了但返回的 JSON 缺 `memory` 键，`parsed.get("memory", parsed)` 会怎么处理？

??? tip "先预测，再展开对照"
    回退到整个解析结果当状态（模型可能直接返回了数组）。**成功调用 + 异常形状**静默通过——这是宽容解析的代价：状态形状从"包一层"变"裸数组"后，下一轮 `json.dumps(memory)` 仍能工作，模式间形状漂移不会被发现。要更严就校验形状再接受。

---

## 6. 证据落盘：latest.json 最后写，partial 冒充不了 current

**关键代码**

**课程源码原文** · [experiment_utils.py · L204–L211](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/experiment_utils.py#L204)：

```python linenums="204"
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(...)
    manifest["artifacts"]["manifest.json"] = sha256_file(manifest_path)

    latest_path = project_dir / "validation" / "latest.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
```

**执行过程：看数据怎样变**

写入顺序：`evidence.json` → `receipts.json`（全部原始调用，无凭据）→ `manifest.json`（三者哈希 + 声明输入的哈希）→ **最后** `latest.json`（指向本次 run 的指针）。docstring 写明用意：*"latest.json is written last, so a partial campaign can never look current"*——半途崩溃的 run 留在 `runs/<id>/` 里可查，但不会占据"最新"位。

`ChatRecorder`（[experiment_utils.py · L90–L131](https://github.com/bojeli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/experiment_utils.py#L90)）是全章共享的回执层：包装任意 OpenAI 兼容客户端，逐调用记 request/response/usage/latency，**设计上从不序列化凭据**——学习版的密钥扫描因此总是干净。

**接回真实源码**

学习版注入与此的关系：`write_campaign_evidence(HERE, ...)` 的 HERE 是课程项目目录（会把 latest.json 写进课程仓库覆盖书方证据！）——所以学习脚本第一件事就是 `run_eval.HERE = OUT` 重定向，并把 `input_paths` 引用到的入口脚本复制到运行目录（`run_evaluation.py` 的哈希与课程原文一致）。

---

## 7. 学习版实测：layer3 是分水岭，json_cards 双重翻车

**执行过程：看数据怎样变**

DeepSeek 写手/答题 + qwen3.7-plus 评审，每层 2 案例 × 4 模式 = 24 评估（书方为 60×4）：

| 模式 \ 层 | layer1 单实体 | layer2 多实体 | layer3 跨会话协调 | 总体 pass | 幻觉率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| notes | 1.0 | 0.5 | 0.5（幻觉 0.5） | 0.67 | 0.17 |
| enhanced_notes | 1.0 | 1.0 | 1.0 | **1.00** | **0.00** |
| json_cards | 0.5（幻觉 0.5） | 2 格写手 JSON 失败 | 1.0 | 0.75* | 0.25 |
| advanced_json_cards | 0.5（幻觉 0.5） | 1.0 | 1.0 | 0.83 | 0.17 |

\* json_cards 的 layer2 两格因写手故障缺失（22/24 完成，status=partial）。

逐条解读（完整数据见 [evidence](evidence.md#memory-modes)）：

- **layer3 是照妖镜**：跨会话协调（护照到期预警、医保衔接）要求把"会话 1 的事实"和"会话 3 的事实"连起来。原子化 notes 在这里幻觉率 50%——**事实都对但连接丢了，模型选择编一个**。enhanced_notes 的段落自带关联，满分通过；
- **layer1 反转**：单实体简单案例上，两种 JSON 卡片模式反而各幻觉一例——结构化开销在简单场景是负资产（为了填满 card 字段而脑补 backstory）；
- **json_cards 的双重失败**：写手在 layer2 多实体案例上产出**畸形长 JSON**（finish_reason=stop、非截断——json_object 模式没兜住 4.7K 字符处的语法滑丝）。这不是课程代码问题，是写手模型的长 JSON 可靠性边界；书方写手（doubao）在同一格通过；
- **成本**（每模式 tokens/均延迟）：enhanced_notes 78.8K/5.3s 最省，advanced_json_cards 108K/6.9s 最贵——高分不是免费的，但 enhanced_notes 同时拿走了最低成本和最高分；
- 答案质量示例：layer3 enhanced_notes 的记忆里存着"Jessica 10-05 来电确认副卡持有人……护照 2025-03-02 到期"，答题者主动给出"护照是最紧急的一项"——proactivity 维度正来自这种可操作的时间上下文。

**动手验证**

把 notes 模式的指令改成"每个原子事实后附 3 句背景"，它会在 layer3 追上 enhanced_notes 吗？

??? tip "先预测，再展开对照"
    形状上会趋同，但那等于把 notes 重定义成 enhanced_notes——实验变量就没了。更干净的做法是保留两模式、把评测集 layer3 加厚（本次每层只有 2 案例，单格翻转就是 ±50%）。四模式排序在 n=6/模式下只能报方向：**带上下文的记忆赢在跨会话连接**，这与书方 60 案例战役的结论方向一致（书方 advanced_json_cards 总体领先；本次它 0.83 次于 enhanced_notes——样本量差异内）。

---

## 最后回到项目

学习脚本 HERE 重定向 → 课程 run_one 会话循环 → 写手/答题/评审三方 prompt → 检查点与 latest.json → [看真实实验结果](evidence.md#memory-modes)。
