# 上下文压缩源码精读 · compression_strategies.py 逐函数通读

[实验说明](context-compression.md) · [实测结果](evidence.md#context-compression) · [学习运行脚本](../assets/task2/run_context_compression.py)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>主文件 compression_strategies.py（694 行）的十四个函数按源码顺序逐个讲——六个压缩策略一个不漏；配套 run_all_strategies.py（战役入口）与 agent.py（溢出判定/老化压缩）跟在后面。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号（均在 chapter2/context-compression/）；**学习运行脚本原文**来自 `run_context_compression.py`；**教学示意**仅用于理解数据形状。task1 的 [上下文精读](../task1/context-code.md) 走过三条策略的请求细节，本页补全六策略与 Agent 侧机制。

---

## 0. 函数清单（一个不漏）

**主文件**：[compression_strategies.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/compression_strategies.py)（694 行，14 项）

| # | 函数/类 | 行号 | 一句话作用 |
| --- | --- | --- | --- |
| 1 | `_reasoning_safe_temperature` | L16–21 | 推理模型强制 temp=1（同前几章） |
| 2 | `_reasoning_safe_max_tokens` | L24–34 | 推理模型补推理预算（+2048） |
| — | `CompressionStrategy` | L41–48 | 六策略枚举 |
| — | `CompressedContent` | L51–59 | 压缩结果（原始/压缩长度、内容、引用） |
| 3 | `ContextCompressor.__init__` | L65–90 | 解析 provider + tiktoken 分词器 |
| 4 | `count_tokens` | L92–98 | tiktoken 计数（失败退字符估算） |
| 5 | `compress_search_results` | L100–131 | ★策略分发入口 |
| 6 | `compress_for_history` | L133–228 | ★windowed 专用：历史工具输出的摘要 |
| 7 | `_no_compression` | L230–258 | 策略 1：格式化全文 |
| 8 | `_non_context_aware_individual_summary` | L260–346 | 策略 2A：逐页摘要 |
| 9 | `_non_context_aware_combined_summary` | L348–452 | 策略 2B：合并摘要 |
| 10 | `_context_aware_summary` | L454–557 | 策略 3：按 query 聚焦摘要 |
| 11 | `_context_aware_with_citations` | L559–681 | 策略 4：带内联引用 |
| 12 | `estimate_tokens` | L683–694 | 粗估（字符/4） |

**配套**：[run_all_strategies.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/run_all_strategies.py)（458 行，战役入口）+ [agent.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression/agent.py)（675 行，溢出判定与老化压缩）+ config.py

---

## 1–2. 兼容层（L16–34）

与 2-3 的同款函数多了一个参数：`_reasoning_safe_max_tokens(model, requested, reasoning_budget=2048)` 用**加法**（`requested + 2048`）而不是 `max(requested, 4096)`——摘要预算只有 300–500 时，加法保证推理模型还有完整预算留给正文。

## 3. `ContextCompressor.__init__`（L65–90）

```python linenums="77"
        resolved_key, resolved_base_url, resolved_model = Config.resolve_llm()
        self.client = OpenAI(api_key=resolved_key, base_url=resolved_base_url)
        self.model = resolved_model
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-4")
        except Exception:
            self.encoding = tiktoken.get_encoding("cl100k_base")
```

`Config.resolve_llm()`（config.py L82–96）走 agentbook 注册表——**这是 task1 和本实验学习版的注入点**（打补丁指向 DeepSeek；.env 的 `LLM_PROVIDER=deepseek` 会让 `MODEL_NAME` 默认错配 kimi-k3，须显式覆写）。tiktoken 的 cl100k 是 **GPT-4 的分词器**——对 DeepSeek 的 token 数只是估算，报表里要当"估计值"读。

## 4. `count_tokens`（L92–98）

tiktoken 编码取长度，异常退 `len(text)//4`（字符/4 的粗估）——**计数失败不炸摘要流程**。

## 5. `compress_search_results`（L100–131）—— 策略分发

```python linenums="117"
        if self.strategy == CompressionStrategy.NO_COMPRESSION:
            return self._no_compression(search_results)
        elif self.strategy == CompressionStrategy.NON_CONTEXT_AWARE_INDIVIDUAL:
            return self._non_context_aware_individual_summary(search_results)
        ...
        elif self.strategy == CompressionStrategy.WINDOWED_CONTEXT:
            # For windowed context, return full content (compression happens later)
            return self._no_compression(search_results)
```

纯分发，但 **windowed 走 `_no_compression`**（L127–129 注释 "compression happens later"）——它对搜索结果不压缩，压缩发生在历史老化时（agent.py 第 22 节）。一个入口、两个压缩时机：**立即压缩**（策略 2–4，工具返回瞬间）与**老化压缩**（windowed，上下文满了才动历史）。

## 6. `compress_for_history`（L133–228）—— windowed 的摘要器

```python linenums="155"
            prompt = f"""Compress the following {tool_name} results into a concise summary that preserves key information.
Focus on information relevant to: {query}

Original content:
{content[:10000]}

Requirements:
1. Keep all important facts, names, dates, and affiliations
2. Remove redundant information
3. Maintain clarity and coherence
{"4. Include [Source: URL] citations for important facts" if preserve_citations else ""}
5. Maximum length: {Config.SUMMARY_MAX_TOKENS} tokens

Provide a focused summary:"""
```

```python linenums="219"
        except Exception as e:
            logger.error(f"Error compressing for history: {str(e)}")
            # Fallback to truncation
            truncated = content[:2000] + "\n\n[Content truncated for history...]"
            return CompressedContent(..., content=truncated, strategy=CompressionStrategy.WINDOWED_CONTEXT)
```

输入截 10000 字符、按**触发时的 query** 聚焦（agent.py 会按 tool_call_id 找回当初的查询）、失败回退"前 2000 字符 + 截断标记"（降级仍有内容）。流式分支里 L191–194 的注释记录了一个命名教训：增量变量若叫 `content` 会**遮蔽**传入参数、让截断回退拿错对象——所以改叫 `delta_text`。

## 7. `_no_compression`（L230–258）

把每条结果格式化成 `===== Search Result =====\nTitle/URL/Snippet/Full Content` 的分节文本。注意 `original_length` 累计的是**裸 content**、`compressed_length` 是**格式化后全文**——所以 no_compression 的"压缩比"是 1.10（格式化包装比原文还长 10%），这不是 bug 是口径：**这个策略本来就什么都没压**。

## 8. `_non_context_aware_individual_summary`（L260–346）—— 策略 2A

每页独立摘要：prompt 只要"2-3 段"（L276–L284，**不提 query**），每页输入截 5000 字符、输出预算 300 tok。摘要后拼上 `Source/URL/Summary` 头。跨页事实（"A 和 B 都投了 C"）它拼不出来——每页只见自己。异常回退：该页的 snippet 顶上（L330–L337）。

## 9. `_non_context_aware_combined_summary`（L348–452）—— 策略 2B

全部页拼接（每页仍截 5000 字符）后**一次**摘要，预算 `SUMMARY_MAX_TOKENS`（500 tok）——一次见全量但 500 tok 装不下多页细节。回退：全部 snippet 拼接（L440–452）。与 2A 的对照是"多次小摘要 vs 一次大摘要"，各有各的丢失方式。

## 10. `_context_aware_summary`（L454–557）—— 策略 3

```python linenums="486"
            prompt = f"""Given the search query: "{query}"
{f"Current context: {current_context[:1000]}" if current_context else ""}

Analyze the following search results and provide a focused summary that directly addresses the query.
Focus on extracting information most relevant to answering: {query}
...
Requirements:
1. Focus only on information relevant to the query
2. Prioritize current/recent information
3. Include specific names, dates, and affiliations
4. Maximum length: {Config.SUMMARY_MAX_TOKENS} tokens
```

三个 prompt 变量齐了：**query**（当前在问什么）、**current_context**（agent.py 传入的"最近 3 个搜索 query"——轻量的"我之前查过什么"信号，避免摘要器重复保留已知信息）、**聚焦要求**。四个摘要 prompt 的差异一张表看完：

| | 提 query？ | 给当前上下文？ | 特别要求 |
| --- | --- | --- | --- |
| individual | 否 | 否 | "2-3 段" |
| combined | 否 | 否 | "覆盖每一页" |
| context_aware | **是** | **是** | "只保留相关" |
| citations | 是 | 是 | "每个事实带 [1][2]" |

## 11. `_context_aware_with_citations`（L559–681）—— 策略 4

在策略 3 基础上两处增强：每页带 `[i]` 编号进输入（L589–592）；要求**内联引用**（"Include inline citations using [1], [2]"）。摘要尾部追加来源清单（L653–658）：

```python linenums="653"
            source_list = "\n\nSources:\n"
            for source in sources:
                source_list += f"{source['id']} {source['title']} - {source['url']}\n"
            final_content = summary + source_list
```

`citations` 字段同时存进 CompressedContent 供程序读取。实测它拿下了**最低压缩比 0.42**——引用约束附带压紧了摘要长度。

## 12. `estimate_tokens`（L683–694）

`len(text)//4` 的粗估——与 count_tokens 的回退路径同一公式。两个函数并存提醒你：**token 数有三个口径**（tiktoken 精确 / 字符估算 / 服务端 usage），报表里别混用。

---

## 13–21. 配套一：run_all_strategies.py（战役入口）

| # | 函数 | 行号 | 作用 |
| --- | --- | --- | --- |
| 13 | `STRATEGY_CHOICES` | L25–32 | CLI 别名 → 六策略 |
| 14 | `StrategyRunner.__init__` | L39–52 | 日志文件 + JSON 文件路径 |
| 15 | `setup_logging` | L60–86 | 文件(DEBUG)+控制台(INFO)双 handler |
| 16 | `log_banner` | L89–94 | 分隔线打印 |
| 17 | `run_strategy` | L96–255 | ★单策略执行（StreamCapture + 指标） |
| 18 | `run_all_strategies` | L257–286 | 六策略顺序跑（间隔 2 秒） |
| 19 | `generate_summary` | L288–340 | 汇总表打印（最佳压缩/最快/最多最少 token） |
| 20 | `save_json_results` | L342–358 | 结果落盘（含配置快照） |
| 21 | `build_parser`/`main` | L361–458 | CLI（--strategy/--model/--log-dir/--list-strategies） |

**`run_strategy`（L96–255）** 两个教学点：**StreamCapture**（L132–173）是个替换 `sys.stdout` 的过滤器——按行扫描 Agent 的控制台输出，含 📝/🎯/📚/✂️ 等关键字的行升 INFO 进日志（压缩过程可复盘）、其余降 DEBUG——**不侵入 Agent 代码的日志采集**；**指标抽取**（L204–240）从 trajectory 汇总执行时间/工具数/溢出数/token，再从每个 `ToolCall.compressed_result` 累计原始与压缩字符——压缩比 `compressed/original` **只统计有 compressed_result 的调用**：no_compression 和 windowed（落地时未压）不产生压缩统计，windowed 的老化压缩走 `compress_for_history`、不经过这个字段，所以它的真实压缩量要看 agent_output 里的 `[COMPRESSED]` 行。

**学习版的注入**（运行脚本）：`Config.resolve_llm` 补丁 + `MODEL_NAME` 覆写 + `CONTEXT_WINDOW_SIZE` 128000→16000 + `ResearchAgent.__init__` 强制 `enable_streaming=False`（记录层需要完整 usage）+ `WebTools.search_web/fetch_webpage` 换合成语料（课程无 SERPER key 时本就回退 mock，学习版只是把 mock 加大到足以呈现压缩对照）。

---

## 22–27. 配套二：agent.py 的六个精选

全函数清单：`_reasoning_safe_temperature`(L22)、`ToolCall`(L34–45，**带 provider 侧 id** 供老化压缩找回 query)、`AgentTrajectory`(L48–63)、`ResearchAgent.__init__`(L71–109)、`_init_system_prompt`(L111–143)、`_get_tools_description`(L145–187)、`_execute_tool`(L189–235)、`_get_current_context_summary`(L237–249)、`_handle_windowed_compression`(L251–351)、`_stream_response`(L353–448)、`_non_streaming_response`(L450–509)、`execute_research`(L511–668)、`reset`(L670–675)。挑六个：

**`AgentTrajectory` 的两个计数器（L52–59）**：

```python linenums="55"
    # Prompt tokens of the most recent API call = the current context size.
    # prompt_tokens_used above is a cumulative COST counter (each call's
    # prompt re-counts the shared prefix), so it must not be compared
    # against the per-request context window.
    last_prompt_tokens: int = 0
```

`prompt_tokens_used` 是**钱**的口径（累计，重复计共享前缀）、`last_prompt_tokens` 是**窗口**的口径（单次请求）——注释明文"must not be compared"。累计值会二次方级夸大：第 k 轮请求含全部历史，累计是 1+2+…+k 量级。

**`execute_research` 的溢出判定（L547–563）**：

```python linenums="553"
                    if self.trajectory.last_prompt_tokens > Config.CONTEXT_WINDOW_SIZE * 0.8:
                        logger.warning(...)
                        self.trajectory.context_overflows += 1
                        if self.compression_strategy == CompressionStrategy.NO_COMPRESSION:
                            print("\n⚠️ Context overflow detected! This demonstrates the limitation of no compression.")
                            return {"error": f"Context window exceeded - ..."}
```

只有 NO_COMPRESSION 在 80% 阈值**直接死亡**（返回 error），其他策略只计数继续——压缩策略的假设是"摘要能把上下文拉回来"。实测 combined 两次越阈被拉回、windowed 一次越阈触发老化后完成，假设成立。

**`_handle_windowed_compression`（L251–351）** 三个机制：

```python linenums="278"
        COMPRESSION_MARKER = "[COMPRESSED]"
        ...
                if original_content.startswith(COMPRESSION_MARKER):
                    already_compressed_count += 1
                else:
                    tool_messages_to_compress.append((i, msg))
```

```python linenums="316"
                tool_call_id = msg.get("tool_call_id")
                query = "Information search"  # Default
                for call in self.trajectory.tool_calls:
                    if call.id is not None and call.id == tool_call_id:
                        query = call.arguments.get('query', query)
                        break
```

**标记防重压**（前缀 `[COMPRESSED]`，下轮触发时跳过这些）；**按 tool_call_id 找回当初的 query**（`ToolCall.id` 字段的用途——事后压缩也知道为什么查）；**消息形状不变**（`{**msg, 'content': 压缩文本}`——role/id 原样，配对天然保持）。触发条件与溢出判定同一个阈值——**同一个 80% 既是 windowed 的扳机也是 no_compression 的丧钟**。

**`_execute_tool`（L189–235）**：search_web 走 `compress_search_results`（立即压缩策略在此生效）；fetch_webpage 返回 `result, None` **永不压缩**（L232 注释 "used for follow-ups"——追补阅读保持原文，压缩风险的三道防线之一）。

**`execute_research` 的工具结果落地（L622–640）**：

```python linenums="622"
                        if compressed and self.compression_strategy != CompressionStrategy.NO_COMPRESSION:
                            tool_content = compressed.content
                            print(f"   ✂️ Compressed: {compressed.original_length:,} → {compressed.compressed_length:,} chars")
                        else:
                            if function_name == "search_web":
                                tool_content = json.dumps(result, indent=2)
```

立即压缩策略下模型**永远看不到原文**；no_compression/windowed 全文 JSON 落地。`✂️` 行就是 StreamCapture 升 INFO 的那些行。

**坏 JSON 容错（L580–603）**：`bytes/bytearray` 解码、dict 直收、str 解析、其他 str() 再试，全败才 `{}` 继续——流式拼出的 tool_call 参数什么形状都可能有。

config.py（121 行）：`resolve_llm`（L82–96，agentbook 注册表三元组）、`CONTEXT_WINDOW_SIZE = 128000`（L51，注释注明"K3 支持到 1M，实验用 128K 预算"——学习版覆写的就是这个）、`SUMMARY_MAX_TOKENS = 500`、`MODEL_NAME` 的默认陷阱（provider=deepseek 时仍默认 kimi-k3）。

---

## 完整执行回放（学习版 no_compression 一次真实运行）

```text
run_context_compression.py
 ├─ Config 补丁 → DeepSeek；CONTEXT_WINDOW_SIZE=16000；MAX_ITERATIONS=20
 ├─ WebTools 换合成语料（每查询 1-2 页 × ~4.6K 字符）
 └─ StrategyRunner.run_all_strategies（六策略顺序）
      策略 no_compression:
       ├─ 轮1: [system][用户任务] → search_web("OpenAI co-founders")
       │       → json.dumps(result)（~2.5K tok）→ messages.append
       ├─ 轮2-5: 逐人搜索，每轮 prompt 累加 ~2.5K
       ├─ 轮6: last_prompt_tokens=13,914 > 12,800(80%×16K)
       │       → context_overflows += 1
       │       → NO_COMPRESSION → return error（死亡分支）
       └─ metrics: 21 次工具调用、溢出 1、无 final_answer
      （后续五策略各自完成，见实验说明的结果表）
 → strategy_results_<ts>.json → 学习版 evidence + 密钥扫描
```

## 动手验证

1. **把窗口改成 4K 而语料不缩**：第一次 search（~2.5K）就逼近 3.2K 阈值、第二轮溢出——no_compression 两轮死掉，对照失去意义。体会"缩尺的约束是保持'几轮积累→溢出'的节奏可观察"。
2. **给 `compress_for_history` 的输入截断从 10000 改成 2000**：老化压缩丢的信息变多——windowed 臂的最终答案还能保住六位创始人吗？（token 省了，信息丢在哪一层？）
3. **把 `_handle_windowed_compression` 的 `[COMPRESSED]` 检查删掉**：每轮触发都把已压缩的消息再压一遍——**摘要的摘要**，信息滚雪球式丢失。那个前缀标记是 windowed 正确性的静默守卫。
