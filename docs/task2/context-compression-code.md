# 上下文压缩源码精读 · 六种策略与一条会爆的上下文

[实验说明](context-compression.md) · [实测结果](evidence.md#context-compression) · [学习运行脚本](../assets/task2/run_context_compression.py)

<div class="design-lead"><span>逐步搭建 / READ THE CODE</span><p>先分清"立即压缩"与"老化压缩"两类策略，再读每个摘要 prompt 的差别，最后看溢出判定为什么必须用最后一次请求的 prompt 数而不是累计值。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号（compression_strategies.py / agent.py / config.py / run_all_strategies.py 均在 chapter2/context-compression/）；**学习运行脚本原文**来自 `run_context_compression.py`；**教学示意**仅用于理解数据形状。task1 的 [上下文源码精读](../task1/context-code.md) 已走过其中三条策略的请求细节，本页聚焦六策略全景与 Agent 侧机制。

## 本页阅读路线

六策略地图 → 两类压缩时机 → 摘要 prompt 逐个拆 → 压缩器构造与计数 → 溢出判定的口径 → windowed 的标记与恢复 → 主循环 → 战役入口与指标 → 学习版缩尺设计 → 实测解读。

---

## 1. 六策略地图：每个策略压缩"什么、何时"

**遇到的问题**

"上下文压缩"是个大词。压什么（搜索结果/历史工具输出）、何时压（进入历史前/满了才压）、按什么压（通用/按问题/带引用），是三个独立的设计轴。

**关键代码**

**课程源码原文** · [compression_strategies.py · L41–L48](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/compression_strategies.py#L41)：

```python linenums="41"
class CompressionStrategy(Enum):
    NO_COMPRESSION = "no_compression"
    NON_CONTEXT_AWARE_INDIVIDUAL = "non_context_aware_individual_summary"  # 逐页摘要再拼接
    NON_CONTEXT_AWARE_COMBINED = "non_context_aware_combined_summary"     # 全部拼接一次摘要
    CONTEXT_AWARE = "context_aware_summary"
    CONTEXT_AWARE_CITATIONS = "context_aware_with_citations"
    WINDOWED_CONTEXT = "windowed_context"
```

**执行过程：看数据怎样变**

| 策略 | 压什么 | 何时 | 摘要看不看问题 |
| --- | --- | --- | --- |
| no_compression | 不压 | — | — |
| individual | 每页各摘要一次（300 tok/页） | 工具返回**立即** | 否 |
| combined | 全部页拼接后摘要一次 | 立即 | 否 |
| context_aware | 拼接后按 query 聚焦摘要 | 立即 | 是 |
| citations | 按 query 摘要 + [1][2] 内联引用 | 立即 | 是 |
| windowed | **历史里的旧工具输出** | 上下文超 80% 阈值**才**压 | 按触发时的 query |

两类的本质区别：**立即压缩**牺牲"当场信息的完整度"换"历史永久瘦身"；**老化压缩（windowed）**让最近的信息保持原样、旧信息降级——和人整理笔记的方式一致。

**接回真实源码**

分发入口 `compress_search_results()`（[L100–L131](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/compression_strategies.py#L100)）里有个容易漏看的分支：windowed 在这里**返回全文**（L127–L129 注释 "compression happens later"）——它对搜索结果的"压缩"发生在历史老化时。

**动手验证**

同样 5 页搜索结果，individual 和 combined 各发几次摘要请求？tokens 花在哪边？

??? tip "先预测，再展开对照"
    individual 发 5 次（每页一次，每次 300 tok 预算）；combined 发 1 次（预算 SUMMARY_MAX_TOKENS=500）。individual 总摘要预算更大（5×300）但每次只见单页——跨页事实（"A 公司和 B 公司都投了 C"）它拼不出来；combined 一次见全量但 500 tok 装不下 5 页细节。各有各的丢失方式。

---

## 2. 摘要 prompt 逐个拆：一字之差改变保留什么

**遇到的问题**

所有摘要策略共用"调一次 LLM"的骨架，实验变量全在 prompt 里。要读懂结果，必须逐字看这些 prompt。

**关键代码**

**课程源码原文** · [compression_strategies.py · L486–L501](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/compression_strategies.py#L486)（context_aware 的 prompt，节选）：

```python linenums="486"
prompt = f"""Given the search query: "{query}"
{f"Current context: {current_context[:1000]}" if current_context else ""}

Analyze the following search results and provide a focused summary that directly addresses the query.
Focus on extracting information most relevant to answering: {query}

Search Results:
{combined_content}

Requirements:
1. Focus only on information relevant to the query
2. Prioritize current/recent information
3. Include specific names, dates, and affiliations
4. Maximum length: {Config.SUMMARY_MAX_TOKENS} tokens

Provide a query-focused summary:"""
```

**执行过程：看数据怎样变**

四个摘要 prompt 的差异点：

| | 提到 query？ | 给当前上下文？ | 特别要求 |
| --- | --- | --- | --- |
| individual（L276–L284） | 否 | 否 | "2-3 段" |
| combined（L383–L393） | 否 | 否 | "覆盖每一页的关键信息" |
| context_aware（L486–L501） | **是** | **是**（最近 3 次搜索的 query，见 agent.py `_get_current_context_summary`） | "只保留与问题相关的" |
| citations（L598–L613） | 是 | 是 | "每个事实带 [1][2] 内联引用" |

`current_context` 不是对话全文，是**最近 3 个搜索 query 拼的摘要行**（[agent.py · L237–L249](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/agent.py#L237)）——轻量的"我之前在查什么"信号，避免摘要器重复保留已知信息。

每页输入有 5000 字符截断（L355/L466/L572 的 `max_chars_per_page`）；citations 策略额外把带 `[1]` 编号的来源清单**追加在摘要尾部**（L653–L658），citations 字段也存进 CompressedContent 供程序读取。

**接回真实源码**

所有策略的异常回退都是**拼接 snippet**（如 L548–L557）——摘要失败 ≠ 没有内容，降级到搜索摘要行。证据上要区分"策略成功了"和"回退了"：看 `compress_search_results` 是否真的产生过模型调用。

**动手验证**

context_aware 摘要丢掉"与问题无关但可能之后有用"的信息，这个风险怎么缓解？

??? tip "先预测，再展开对照"
    三道防线：`current_context` 让摘要器知道你之前问过什么（但只回看 3 步）；windowed 策略干脆不提前压（保真优先）；fetch_webpage 工具完全不压（agent.py L232 注释 "used for follow-ups"——追补信息保持原文）。没有策略能两全，这是压缩的本质取舍。

---

## 3. 溢出判定的口径：最后一次请求 vs 累计值

**遇到的问题**

"上下文快满了"有两种算法：把每轮 prompt tokens 加总（累计成本），或看**最近一次请求**的 prompt 大小（当前上下文）。两者差一个量级。

**关键代码**

**课程源码原文** · [agent.py · L52–L59](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/agent.py#L52)：

```python linenums="52"
    total_tokens_used: int = 0
    prompt_tokens_used: int = 0
    completion_tokens_used: int = 0
    # Prompt tokens of the most recent API call = the current context size.
    # prompt_tokens_used above is a cumulative COST counter (each call's
    # prompt re-counts the shared prefix), so it must not be compared
    # against the per-request context window.
    last_prompt_tokens: int = 0
    context_overflows: int = 0
```

**课程源码原文** · [agent.py · L547–L563](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/agent.py#L547)：

```python linenums="547"
if self.trajectory.total_tokens_used > 0:  # Only check after first call
    # Compression demo uses a 128k context budget. Compare the
    # LAST call's prompt size (the actual context) against the
    # window — the cumulative counter re-counts the shared
    # prefix every call and overstates usage quadratically.
    if self.trajectory.last_prompt_tokens > Config.CONTEXT_WINDOW_SIZE * 0.8:
        logger.warning(f"Approaching context limit: {self.trajectory.last_prompt_tokens:,} prompt tokens in last request")
        self.trajectory.context_overflows += 1

        if self.compression_strategy == CompressionStrategy.NO_COMPRESSION:
            print("\n⚠️ Context overflow detected! This demonstrates the limitation of no compression.")
            return {
                "error": f"Context window exceeded - {self.trajectory.last_prompt_tokens:,} tokens in last request (limit: {Config.CONTEXT_WINDOW_SIZE})",
                ...
            }
```

**执行过程：看数据怎样变**

为什么累计值会"二次方级夸大"：第 k 轮请求的 prompt 包含全部 k-1 轮的内容，累计 = 1+2+…+k 量级。而窗口约束的是**单次请求**的 prompt 长度。同一个 AgentTrajectory 里 `prompt_tokens_used` 是**钱**的口径、`last_prompt_tokens` 是**窗口**的口径——注释专门写了"must not be compared against the per-request context window"。

溢出行为本身也是实验现象：只有 NO_COMPRESSION 遇到 80% 阈值直接**报错终止**（返回 error），其他策略只是计数 + 继续（压缩策略的假设是压缩能把上下文拉回来；windowed 则在同样阈值触发压缩）。

**动手验证**

第 5 轮请求的 prompt 是 10K tokens，前 4 轮分别是 2/4/6/8K。累计 prompt_tokens_used 和 last_prompt_tokens 各是多少？哪个该和 12.8K 阈值比？

??? tip "先预测，再展开对照"
    累计 = 2+4+6+8+10 = 30K（超阈值！）；last = 10K（未超）。该比的是 10K。若误用累计值，第 3 轮（累计 12K）就会误报"快满了"——这正是注释里防的 bug。

---

## 4. windowed：标记、按 ID 找回 query、只压一次

**遇到的问题**

老化压缩要改写**历史里**的工具消息。三个坑：怎么知道哪条压过？压缩时用什么 query？assistant 的 tool_calls 和 tool 消息的配对不能断。

**关键代码**

**课程源码原文** · [agent.py · L277–L290](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/agent.py#L277)：

```python linenums="277"
# Compression marker to identify already-compressed messages
COMPRESSION_MARKER = "[COMPRESSED]"

for i, msg in enumerate(messages):
    if msg.get('role') == 'tool':
        original_content = msg.get('content', '')
        if original_content.startswith(COMPRESSION_MARKER):
            already_compressed_count += 1
        else:
            tool_messages_to_compress.append((i, msg))
```

**课程源码原文** · [agent.py · L316–L332](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/agent.py#L316)：

```python linenums="316"
# Find the corresponding tool call to get context
tool_call_id = msg.get('tool_call_id')
query = "Information search"  # Default

# Try to find the query from the tool call
for call in self.trajectory.tool_calls:
    if call.id is not None and call.id == tool_call_id:
        query = call.arguments.get('query', query)
        break
...
compressed = self.compressor.compress_for_history(
    original_content, 'search_web', query, preserve_citations=True
)
```

**执行过程：看数据怎样变**

- **标记防重压**：压缩后的内容前缀 `[COMPRESSED] [Original: 12,345 chars → Compressed: 800 chars]`。下一轮再触发时跳过这些——只压"新长出来的"；
- **按 tool_call_id 找回 query**：ToolCall 数据类专门存了 provider 侧的调用 id（[agent.py · L42–L45](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/agent.py#L42) 的注释说明用途）。压旧内容时摘要 prompt 里"Focus on information relevant to: {query}"用的是**当时**的查询——事后压缩也知道当初为什么查；
- **消息形状不变**：`{**msg, 'content': compressed_content}`——只换 content，role/tool_call_id 原样。assistant 的 tool_calls 消息不动，配对天然保持。

`compress_for_history`（[compression_strategies.py · L133–L228](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/compression_strategies.py#L133)）的输入截到 10000 字符、失败回退到"前 2000 字符 + 截断标记"。它内部还有个命名教训（L191–L194 注释）：流式分支里若把增量变量命名为 `content`，会**遮蔽**传入的 `content` 参数、让截断回退拿错对象——所以改叫 `delta_text`。

**动手验证**

windowed 触发时把**所有**未压缩的 tool 消息一次压完，而不是只压最旧的一条。为什么？

??? tip "先预测，再展开对照"
    阈值触发说明整体超预算，压一条省几百 token 解决不了问题；一次压完把上下文直接拉回低位，避免接下来每轮都在阈值边缘反复触发（每次触发都是 N 次 LLM 摘要调用）。代价是一次性摘要调用风暴——上下文里 8 条未压消息就是 8 次调用。

---

## 5. 主循环：压缩发生在工具结果落地时

**关键代码**

**课程源码原文** · [agent.py · L609–L640](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/agent.py#L609)：

```python linenums="609"
# Execute the tool
result, compressed = self._execute_tool(function_name, function_args)
...
# Determine what content to add to messages
if compressed and self.compression_strategy != CompressionStrategy.NO_COMPRESSION:
    # Use compressed content
    tool_content = compressed.content
    print(f"   ✂️ Compressed: {compressed.original_length:,} → {compressed.compressed_length:,} chars")
else:
    # Use original content (for no compression or last message in windowed)
    if function_name == "search_web":
        tool_content = json.dumps(result, indent=2)
    else:
        tool_content = json.dumps(result)

# Add tool result to messages
tool_msg = {
    "role": "tool",
    "tool_call_id": tool_call['id'],
    "content": tool_content
}
messages.append(tool_msg)
```

**执行过程：看数据怎样变**

- 立即压缩策略：模型**永远看不到原文**——`compressed.content` 直接进历史。`✂️` 日志行是压缩发生的人类可读证据；
- no_compression / windowed：`json.dumps(result, indent=2)` 全文进历史（windowed 等老化时再压）；
- `fetch_webpage` 永远不压（`_execute_tool` L232 返回 `result, None`）——追补阅读保持原文。

坏 JSON 的容错（L580–L603）比其他实验更宽：`bytes/bytearray` 解码、dict 直收、str 解析、其他类型 str() 后再试，全部失败才用 `{}` 继续——流式拼出来的 tool_call 参数什么形状都可能有。

**接回真实源码**

流式分支（`_stream_response` L353–L448）手工拼装 tool_calls 增量：`delta.tool_calls` 按 index 累积 id/name/arguments 片段（L400–L417）——流式协议里函数参数是**分片到达**的，这是所有流式 Agent 都要处理的原语级细节。usage 靠 `stream_options={"include_usage": True}` 从最后一个 chunk 拿。

**动手验证**

模型一轮并行调了 4 个 search_web（学习版实测出现过）。individual 策略下这一轮要发多少次摘要请求？

??? tip "先预测，再展开对照"
    4 次工具执行 × 每次对语料里的每页各摘要一次（本学习语料每查询 1–2 页）≈ 4–8 次摘要调用，外加 1 次主模型调用。**并行工具调用会放大立即压缩的调用数**——省 token 的策略在请求数上反而更贵，这是压缩实验里容易被忽略的一笔账。

---

## 6. 战役入口：StrategyRunner 的指标与日志

**关键代码**

**课程源码原文** · [run_all_strategies.py · L204–L240](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/run_all_strategies.py#L204)：

```python linenums="204"
if trajectory:
    result['metrics'] = {
        'execution_time': execution_time,
        'tool_calls': len(trajectory.tool_calls),
        'context_overflows': trajectory.context_overflows,
        'total_tokens': trajectory.total_tokens_used,
        'prompt_tokens': trajectory.prompt_tokens_used,
        'completion_tokens': trajectory.completion_tokens_used
    }
    # Calculate compression statistics
    total_original = 0
    total_compressed = 0
    for call in trajectory.tool_calls:
        if call.compressed_result:
            total_original += call.compressed_result.original_length
            total_compressed += call.compressed_result.compressed_length
    if total_original > 0:
        compression_ratio = total_compressed / total_original
```

**执行过程：看数据怎样变**

六策略顺序跑（策略间 sleep 2 秒），每策略产出：成功/失败、指标（tokens/工具数/溢出数/压缩比）、`agent_output`（StreamCapture 捕获的全程控制台输出——含每个 `✂️ Compressed` 行，是逐轮复盘的原始材料）。汇总表打印 Strategy × Success × Time × Tokens × Compression × Overflows。

注意 `compression_ratio` 只统计**有 compressed_result 的**工具调用——no_compression 和 windowed（落地时未压）不产生压缩统计；windowed 的老化压缩走 `compress_for_history`，不经过 ToolCall.compressed_result，所以它的"压缩量"要看 agent_output 里的 `[COMPRESSED]` 行而不是这个比率。

**接回真实源码**

另一个入口 `experiment.py`（ExperimentRunner）是同一件事的无日志版（`enable_streaming=False` 默认、tqdm 进度条）；`run_all_strategies` 的 docstring 自己说明分工："本脚本侧重可复盘的详细日志"。书方 ledger 的六臂证据（`results/kimi_k3_real_20260718.json`）不在本仓库快照中，学习版无法与其逐数值对照，只能对照 ledger 的定性结论（无压缩臂溢出、五压缩臂完成）。

---

## 7. 学习版缩尺设计：为什么 128K → 16K 是合法的 {#7}

**遇到的问题**

书方的溢出演示靠真实网页把上下文堆到 128K 的 80%（>100K tokens）——一次学习跑要消耗百万级 token 才能看到现象。没有 SERPER_API_KEY 的情况下课程本来就回退到几百字符的 mock 语料，永远堆不满。

**设计思路**

两个变量同时缩放，机制保真：

1. **语料放大**：合成语料保留课程 mock 的 2024 事实快照，每页加约 4K 字符的中性噪声（task1 同款手法）——单次 search 的 tool 输出从 ~500 字符升到 ~9K 字符（JSON 化后约 2.5K tokens）；
2. **窗口缩小**：`Config.CONTEXT_WINDOW_SIZE` 128000 → 16000。溢出判定、80% 阈值、windowed 触发、NO_COMPRESSION 的死亡分支全部原样，只是"满"的定义缩小了 8 倍。

**学习运行脚本原文** · [run_context_compression.py · L60–L64](../assets/task2/run_context_compression.py)：

```python linenums="60"
cfg = load("config", "chapter2/context-compression/config.py")
cfg.Config.resolve_llm = classmethod(lambda cls: (KEY, os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), MODEL))
cfg.Config.MODEL_NAME = MODEL
cfg.Config.CONTEXT_WINDOW_SIZE = WINDOW
cfg.Config.MAX_ITERATIONS = 20
```

这样做的合法性论证：上下文窗口在课程代码里只出现在**阈值比较**（`last_prompt_tokens > WINDOW * 0.8`）和错误消息里，不影响任何压缩逻辑本身。DeepSeek 真实窗口 128K 远大于 16K，缩尺不会触碰真实 API 限制。不变量是"工具输出的增长速率 vs 窗口大小"的比值——缩尺后每轮 ~2.5K tokens 对 16K 窗口，与书方真实网页对 128K 的相对速率同量级。

其余注入与前四个实验同构：`resolve_llm` 指向 DeepSeek（config 的 `LLM_PROVIDER=deepseek` 会让 MODEL_NAME 错配 kimi-k3，故显式覆写）、`ResearchAgent.__init__` 强制非流式（记录层需要完整 usage）、`WebTools.search_web/fetch_webpage` 换合成语料。

**动手验证**

如果把窗口缩到 4K 而语料不缩，会发生什么？

??? tip "先预测，再展开对照"
    第一次 search（~2.5K）就逼近 3.2K 阈值，第二次就溢出——no_compression 两轮死掉，模型连"co-founders 列表"都没查完，压缩策略的对照也失去意义（还没来得及展示多轮积累）。**缩尺的约束是让"几轮积累→溢出"的节奏保持可观察**，不是越小越好。

---

## 8. 实测解读

结果与逐策略解读见 [evidence.md#context-compression](evidence.md#context-compression)。

---

## 最后回到项目

学习脚本缩尺注入 → 课程 StrategyRunner 六策略 → ResearchAgent 主循环（立即压缩/老化压缩/溢出死亡）→ CompressedContent 与指标 → [看真实实验结果](evidence.md#context-compression)。
