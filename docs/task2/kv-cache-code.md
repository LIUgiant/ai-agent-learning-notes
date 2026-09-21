# KV Cache 源码精读 · agent.py 逐函数通读

[实验说明](kv-cache.md) · [实测结果](evidence.md#kv-cache) · [学习运行脚本](../assets/task2/run_kv_cache.py)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>主文件 agent.py（888 行）的全部 19 个函数按源码顺序逐个讲；配套 main.py（548 行）的 12 个函数跟在后面。读完你应该能对照源码逐行复述整个项目。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号，链接指向课程仓库固定提交；**学习运行脚本原文**来自 `run_kv_cache.py`；**教学示意**仅用于理解数据形状。`agentbook/providers` 注册表在用到它的 `__init__` 处一并讲解。

---

## 0. 函数清单（一个不漏）

**主文件**：[chapter2/kv-cache/agent.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py)

| # | 函数/类 | 行号 | 一句话作用 | 谁调用它 |
| --- | --- | --- | --- | --- |
| 1 | `_is_reasoning_model` | L28–37 | 判断是否推理模型（Kimi K2.5+/GPT-5） | 兼容层 ×2 |
| 2 | `_reasoning_safe_temperature` | L40–44 | 推理模型强制 temperature=1 | `execute_task` |
| 3 | `_reasoning_safe_max_tokens` | L47–51 | 推理模型补足推理预算（≥4096） | `execute_task` |
| — | `KVCacheMode` | L59–66 | 六模式枚举（实验自变量） | 全文件 |
| — | `ToolCall` / `AgentMetrics` | L69–91 | 工具调用记录 / 指标数据类 | `execute_task` |
| 4 | `LocalFileTools.__init__` | L97–99 | 记住工具根目录（绝对路径） | `KVCacheAgent.__init__` |
| 5 | `LocalFileTools.read_file` | L101–179 | 读文件（分页/路径安全/10KB 截断） | 模型工具调用 |
| 6 | `LocalFileTools.find` | L181–255 | 按通配符找文件（os.walk 剪枝） | 模型工具调用 |
| 7 | `LocalFileTools.grep` | L257–349 | 正则搜文件（目录/单文件两模式） | 模型工具调用 |
| 8 | `KVCacheAgent.__init__` | L357–470 | provider 解析 + 工具表 + 状态初始化 | `compare_implementations` |
| 9 | `_get_system_prompt` | L472–491 | 系统提示（dynamic_system 加时间戳） | `_format_messages` |
| 10 | `_get_tools` | L493–501 | 工具表（shuffled_tools 洗牌） | `execute_task` |
| 11 | `_get_user_profile_message` | L503–511 | 画像消息（dynamic_profile 扣 credits） | `_format_messages` |
| 12 | `_format_messages` | L513–585 | ★按模式组装消息列表 | `execute_task` |
| 13 | `_execute_tool` | L587–619 | 工具分发 + 参数过滤 + 异常包装 | `execute_task` |
| 14 | `execute_task` | L622–831 | ★★ReAct 主循环（正确/错误分叉） | `compare_implementations` |
| 15 | `compare_implementations` | L834–888 | 六模式顺序跑 + 汇总日志 | main.py / 学习脚本 |

**配套文件**：[chapter2/kv-cache/main.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/main.py)（12 个函数，第 16–27 节）

---

## 1–3. 兼容层（L28–51）：三个小函数解决"模型脾气"

```python linenums="28"
def _is_reasoning_model(model) -> bool:
    m = str(model or "").lower().replace("/", "-")
    if "gpt-5" in m:
        return True
    return any(tag in m for tag in ("kimi-k2.5", "kimi-k2.6", "kimi-k2.7", "kimi-k3"))

def _reasoning_safe_temperature(model, requested=1.0):
    return 1 if _is_reasoning_model(model) else requested

def _reasoning_safe_max_tokens(model, requested=2000):
    return max(requested, 4096) if _is_reasoning_model(model) else requested
```

推理模型（Kimi K2.5+、GPT-5）有两个脾气：只接受 `temperature=1`；completion 预算先花在隐藏推理上。`_reasoning_safe_max_tokens` 用 `max(requested, 4096)` 保证工具调用不被推理 token 截断——**只放大不缩小**，非推理模型原样通过（DeepSeek 走 0.7/2000 分支）。判断用**家族前缀子串**而不是完整名单——新版本（k2.7、k3.5……）自动覆盖，代价是误伤可能，但方向保守（多发预算），可接受。

---

## 4. `LocalFileTools.__init__`（L97–99）

```python linenums="97"
    def __init__(self, root_dir: str = "."):
        self.root_dir = os.path.abspath(root_dir)
        logger.info(f"File tools initialized with root: {self.root_dir}")
```

两行，但 `abspath` 是后面所有路径安全检查的前提：`realpath` 前缀比较要求两侧都是绝对路径（相对路径比前缀没有意义）。

---

## 5. `read_file`（L101–179）：分页、安全、截断，一肩挑

```python linenums="113"
        try:
            full_path = os.path.join(self.root_dir, file_path)
            # Security check - ensure path is within root_dir
            real_path = os.path.realpath(full_path)
            if not real_path.startswith(self.root_dir):
                return {
                    "error": f"Access denied: Path outside root directory",
                    "success": False
                }
```

```python linenums="144"
            # Determine end line
            if size is None or size < 0:
                # Negative size is a common "read all" sentinel; avoid lines[i:-n].
                end = total_lines
            else:
                end = min(offset + size, total_lines)
```

```python linenums="154"
            # Apply size limit for safety (10KB)
            truncated = False
            if len(content) > 10000:
                content = content[:10000]
                truncated = True
```

四个要点逐个说：**路径安全**（L113–122）用 `realpath` 展开 `..` 和符号链接后做前缀检查——攻击者拿 symlink 绕过的路也被堵上；**负 size 哨兵**（L144–148）的注释解释了为什么不能直接 `lines[i:-n]`——那会"读到最后一行之前"，语义完全跑偏，所以 `size<0` 翻译成"读到底"；**10KB 截断**（L154–158）防单文件撑爆上下文，并打 `truncated` 标让模型知道没读完；所有失败（文件不存在/读错）都返回 `{"error":..., "success": False}` 而不是抛异常——**工具错误是观测结果，不炸循环**。

---

## 6. `find`（L181–255）：os.walk 的剪枝技巧

```python linenums="218"
            matches = []
            for root, dirs, files in os.walk(real_path):
                # Filter hidden directories and __pycache__
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                
                for file in files:
                    if file.startswith('.') or file.endswith('.pyc'):
                        continue
                    if glob_module.fnmatch.fnmatch(file, pattern):
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, self.root_dir)
                        matches.append(rel_path)
```

`dirs[:] = [...]` 是**遍历中剪枝**的惯用法：原地替换 walk 的目录列表，被过滤的目录整个子树不再访问（而不是走完了再筛）。路径安全检查同 read_file；返回的是**相对 root_dir 的路径**（模型后续 read_file 直接可用）；100 条上限 + `truncated` 标。

---

## 7. `grep`（L257–349）：三种入口、层层限流

三种调用形态：`file_path` 搜单文件 / `directory` 搜目录 / 都不给返回错误（L306–310）。目录模式限定文本扩展名（py/txt/md/json/yaml/js/ts...，L301）、最多 50 个文件；`re.compile(pattern, re.IGNORECASE)` 大小写不敏感；行截断 200 字符（L326）、最多 100 条匹配。安全检查对单文件和目录各做一遍（L278/L293）。**每个上限都是独立的**——文件数、匹配数、行宽，防的是"一个 grep 爆掉上下文"。

---

## 8. `KVCacheAgent.__init__`（L357–470）：三件事

**provider 解析（L370–382）**：

```python linenums="370"
        # 默认走 Moonshot/Kimi 官方端点；若传入的是 OpenRouter key（sk-or-…），
        # 则自动回退到 OpenRouter，并把 kimi-* 模型名映射为 moonshotai/kimi-k2。
        from agentbook.providers import is_openrouter_key, resolve_backend

        provider = "openrouter" if is_openrouter_key(api_key) else "kimi"
        backend = resolve_backend(provider, model=model, api_key=api_key)
        self.client = OpenAI(api_key=backend.api_key, base_url=backend.base_url)
        self.model = backend.model
```

注册表两层架构：[registry.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/agentbook/providers/registry.py#L25) 是纯数据（PROVIDERS 字典：每家的 base_url/默认模型/key 环境变量，含 deepseek 条目 L57–65），[resolution.py · resolve_backend](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/agentbook/providers/resolution.py#L127) 是策略链（①gpt-5 有 OpenRouter key 时改道 ②provider 自己的 key 直连 ③OpenRouter 兜底 ④报错）。**DeepSeek 学习版的注入点就在这**：agent 硬编码 kimi/openrouter 二选一，但 `from ... import resolve_backend` 发生在构造时——学习脚本在构造前替换 `agentbook.providers.resolve_backend`，无论传什么都解析成 DeepSeek 后端。零源码改动。

**工具表（L393–468）**：三个工具的 JSON Schema（read_file 带 offset/size 分页、find 带 pattern/directory、grep 带正则）。注意 `self.tool_definitions` 是**实例属性**——后面 `_get_tools` 每次浅拷贝它再（可能）洗牌，原表不被污染。

**状态初始化（L387–389）**：`conversation_history`（会话历史）、`user_credits = 100`（dynamic_profile 的倒计时状态）、`self.metrics`。

---

## 9–11. 三个上下文钩子（L472–511）：每个模式只动自己那一段

```python linenums="486"
        if self.mode == KVCacheMode.DYNAMIC_SYSTEM:
            # Add timestamp to system prompt (breaks KV cache)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            return f"{base_prompt}\n\nCURRENT TIME: {timestamp}"
```

```python linenums="493"
    def _get_tools(self) -> List[Dict]:
        tools = self.tool_definitions.copy()
        if self.mode == KVCacheMode.SHUFFLED_TOOLS:
            random.shuffle(tools)
        return tools
```

```python linenums="503"
    def _get_user_profile_message(self) -> Optional[Dict]:
        if self.mode == KVCacheMode.DYNAMIC_PROFILE:
            self.user_credits -= 1
            return {
                "role": "user",
                "content": f"[User Profile: Premium user with {self.user_credits} credits remaining]"
            }
        return None
```

三个钩子各破坏前缀的一个位置：`%f` 是**微秒**——两次调用间隔再短时间戳也必变，system 段必变、其后全部作废（实测命中率 0% 的元凶）；`copy()` 是列表浅拷贝，shuffle 只重排副本（元素 dict 不被改，顺序在变——足够毁缓存，实测 4 次调用 3 种顺序）；credits 每轮 -1 让**插在 system 之后**的画像消息轮轮变。对照序列化顺序 `[tools][system][profile][历史][task]`：三个钩子分别打第 0、第 1、第 2 位置——**位置越靠前，杀伤半径越大**（shuffled_tools 连 system 一起毁，所以比 dynamic_profile 更糟）。

---

## 12. `_format_messages`（L513–585）：按模式组装，本文件的心脏之一

```python linenums="528"
        if self.mode == KVCacheMode.SLIDING_WINDOW:
            # conversation_history holds assistant/tool messages, so the raw
            # slice could start with a tool message whose paired assistant
            # tool_calls message was trimmed away — the API rejects such a
            # history. Walk the window start back to the owning assistant
            # message so every tool message keeps its pair.
            if self.conversation_history:
                start = max(0, len(self.conversation_history) - 6)
                while start > 0 and self.conversation_history[start].get("role") == "tool":
                    start -= 1
                messages.extend(self.conversation_history[start:])
```

```python linenums="540"
        elif self.mode == KVCacheMode.TEXT_FORMAT:
            if self.conversation_history:
                history_text = "Previous conversation:\n"
                for msg in self.conversation_history:
                    role = msg['role'].upper()
                    if role == "ASSISTANT":
                        if msg.get('content'):
                            history_text += f"{role}: {msg['content']}\n"
                        if msg.get('tool_calls'):
                            history_text += f"{role}: [Making tool calls]\n"
                            for tool_call in msg['tool_calls']:
                                func_name = tool_call.get('function', {}).get('name', 'unknown')
                                func_args = tool_call.get('function', {}).get('arguments', '{}')
                                history_text += f"  - Calling {func_name} with args: {func_args}\n"
                    elif role == "TOOL":
                        history_text += f"TOOL RESPONSE: {msg.get('content', '')}\n"
                    ...
                messages.append({"role": "user", "content": history_text})
        else:
            # 其余模式：全量历史
            messages.extend(self.conversation_history)
```

组装顺序恒定：`[system] [profile?] [历史…] [task]`。SLIDING_WINDOW 的 `while` 回退是本函数最精妙的一行：窗口切 6 条可能把 tool 消息的"主人"（assistant tool_calls 消息）切掉，API 直接 400——所以从窗口起点**向前退到非 tool 消息**，正确性优先于"精确 6 条"。TEXT_FORMAT 把全部历史拍平进**一条** user 消息（assistant 的工具调用展开成文字、tool 结果转 `TOOL RESPONSE:`）——消息数恒为 3，但文本逐轮**只增不改**，这正是它 DeepSeek 命中率 70%（token 级前缀稳定）却总 token 爆炸 1.6 倍的机制。其余模式（含 CORRECT/DYNAMIC_SYSTEM/SHUFFLED_TOOLS/DYNAMIC_PROFILE）全量历史——它们的前缀破坏来自钩子，不来自这里。

---

## 13. `_execute_tool`（L587–619）：幻觉参数的静默防御

```python linenums="598"
        try:
            tool_func = tool_map[tool_name]
            import inspect
            sig = inspect.signature(tool_func)
            valid_args = {}
            for param_name in sig.parameters:
                if param_name in arguments:
                    valid_args[param_name] = arguments[param_name]
            filtered = set(arguments.keys()) - set(valid_args.keys())
            if filtered and self.verbose:
                logger.warning(f"Filtered unexpected arguments for {tool_name}: {filtered}")
            return tool_func(**valid_args)
        except Exception as e:
            error_msg = f"Tool execution error: {str(e)}"
            return {"error": error_msg, "success": False}
```

`inspect.signature` 求出工具函数的**真实形参**，模型给的参数按名过滤——模型幻觉出 `line_number` 参数会被静默丢弃并记 warning，`file_path` 正常通过。外层 except 把一切异常包装成结果——配合工具内部的错误返回，**两层都不让异常逃出循环**。

---

## 14. `execute_task`（L622–831）：主循环，正确与错误的分水岭

**关键分叉（L641–661）**——整个实验的心脏：

```python linenums="654"
            if self.mode == KVCacheMode.CORRECT:
                # Correct mode: Build messages once, then keep using same list
                if iteration == 1:
                    messages = self._format_messages(original_task)
            else:
                # Incorrect modes: Recreate messages from history each iteration
                # This forces cache invalidation due to context changes
                messages = self._format_messages(original_task)
```

CORRECT 只在第 1 轮构建消息列表，之后**一直 append 同一个 list 对象**；错误模式每轮从 history 重建。注意一个精确的理解：**"每轮重建"本身不必然丢缓存**——重建出的内容若逐字节相同，token 前缀依旧稳定；真正毁缓存的是各钩子在重建时注入的变化（时间戳/credits/顺序/窗口/拍平）。实验把"重建"与"变化"绑在同一组对照 CORRECT，观察的是叠加效果。

**请求组装与 TTFT（L664–687）**：`request_data` 无条件带 `tools` 与 `tool_choice="auto"`（注释：TEXT_FORMAT 也要工具才能干活）。`time.time()` 包住整个**非流式**请求——它测的是"整次往返"含全部生成时间，末轮长答案在所有模式都约 6 秒；工具轮（第 1–3 次）延迟才有比较意义。

**缓存检测（L699–730）**：

```python linenums="707"
                    cached = 0
                    if hasattr(usage, 'cached_tokens'):
                        cached = usage.cached_tokens if usage.cached_tokens is not None else 0
                        ...
                    else:
                        if hasattr(usage, 'prompt_tokens_details'):
                            details = usage.prompt_tokens_details
                            if details and hasattr(details, 'cached_tokens'):
                                ...
```

双路径：Kimi 直挂 `usage.cached_tokens`，OpenAI 风格在 `prompt_tokens_details.cached_tokens`。**DeepSeek 两个都不报**（它用 `prompt_cache_hit_tokens` 进 pydantic extra）——所以课程 metrics 对 DeepSeek 恒 0，学习脚本在记录层自抓原始 usage。这是"指标口径要跟 provider 对齐"的直接教训。

**工具调用处理（L742–802）**：assistant 消息 `model_dump()` 后**双写**（`messages` 本轮用 + `conversation_history` 下一轮重建用）；参数 `json.loads` 失败包装成错误结果回传（模型下轮能看见自己的坏 JSON）；每个 tool_call 生成配对的 tool 消息（`tool_call_id` 逐个对应）。

**终止（L804–813）**：无 tool_calls 的回复即最终答案，break。任何 API 异常也 break（L815–817）——教学取舍，生产要加退避重试。

---

## 15. `compare_implementations`（L834–888）

```python linenums="850"
    for mode in KVCacheMode:
        agent = KVCacheAgent(api_key=api_key, mode=mode, model=model, root_dir=root_dir, verbose=True)
        result = agent.execute_task(task)
        results[mode.value] = {
            "success": result["success"],
            "iterations": result["iterations"],
            "tool_calls": result["tool_calls"],
            "metrics": asdict(result["metrics"])
        }
```

六模式顺序跑（`for mode in KVCacheMode` 按枚举定义序：correct → dynamic_system → shuffled_tools → dynamic_profile → sliding_window → text_format），逐模式记日志、留 result。学习脚本没走这个入口——为了注入 DeepSeek 后端和记录层，直接循环六模式构造 `KVCacheAgent`（等价路径）。

---

## 16–27. 配套：main.py 的 12 个函数

| # | 函数 | 行号 | 作用 |
| --- | --- | --- | --- |
| 16 | `_coerce_metrics` | L50–67 | 新旧两版结果文件格式兼容（含受限 eval） |
| 17 | `_avg_ttft` | L70–73 | 平均 TTFT（回退到首次） |
| 18 | `_hit_rate` | L76–78 | 按次数的命中率 |
| 19 | `_billable_tokens` | L81–92 | 成本示意模型（缓存折扣） |
| 20 | `print_comparison_table` | L95–118 | 11 列对比表 |
| 21 | `load_result_files` | L121–144 | 离线读 result_*.json |
| 22 | `run_report` | L147–182 | 离线报表（无需 key） |
| 23 | `create_summary_task` | L185–194 | 默认任务（分析 ch1+ch2 全项目） |
| 24 | `run_single_mode` | L197–317 | 单模式运行 + 结果打印/落盘 |
| 25 | `select_mode_interactive` | L320–369 | 交互菜单 |
| 26 | `run_comparison` | L371–452 | 全模式对比 + 分析打印 |
| 27 | `main` | L455–544 | CLI 分发（--report/--compare/--mode/交互） |

挑四个有教学量的讲，其余是常规胶水：

**`_coerce_metrics`（L50–67）**——旧版单模式文件用 `default=str` 存了 `repr(AgentMetrics(...))` 字符串，这里用"空 builtins + 只暴露 AgentMetrics"的受限 eval 救回来：

```python linenums="60"
    if isinstance(metrics, str) and metrics.startswith("AgentMetrics("):
        # Safe eval: only AgentMetrics is exposed, no builtins.
        try:
            obj = eval(metrics, {"__builtins__": {}}, {"AgentMetrics": AgentMetrics})
            return asdict(obj)
```

约束在"只信自家 dataclass 的 repr"上——比裸 eval 安全，但仍是对持久化数据执行 eval 的少见场景。

**`_billable_tokens`（L81–92）**——透明的成本模型：

```python linenums="81"
def _billable_tokens(m: Dict[str, Any], cache_price_ratio: float) -> float:
    prompt = m.get("prompt_tokens", 0) or 0
    cached = m.get("cached_tokens", 0) or 0
    cached = min(cached, prompt)
    return (prompt - cached) + cached * cache_price_ratio
```

未命中全价 + 命中 × 折扣比（`--cache-price-ratio` 默认 0.1）。**不内置任何厂商价格**——比例由使用者传，报表脚注明"仅为成本示意"。`min(cached, prompt)` 防脏数据。

**`_hit_rate` vs `cache_pct`（print_comparison_table L95–118）**——表格里 `Hit%` 用**次数**口径（cache_hits/总轮次）、`Cache%` 用 **token** 口径（cached/prompt）：一个模式 10 轮 9 轮各命中 64 token 和 2 轮里 1 轮命中 5000 token，两个口径给出完全相反的"哪个好"。分开打印是唯一诚实的做法。

**`run_report`（L147–182）**——离线复盘：聚合 `result_*.json`/`comparison_*.json` 打印与在线版同款表格，**不需要 API key**。复盘历史证据和重新做实验是两条独立路径——CLI 里 `--report` 最先返回。

---

## 完整执行回放（学习版 correct 模式一次真实运行）

```text
run_kv_cache.py（学习脚本）
 ├─ patch agentbook.providers.resolve_backend → DeepSeek 后端
 ├─ patch agent 模块 OpenAI → 记录工厂（抓 prompt_cache_hit_tokens + 消息指纹）
 └─ for mode in KVCacheMode:  ← 等价 compare_implementations
      KVCacheAgent(mode=CORRECT) → resolve_backend(被补丁) → deepseek 客户端
      execute_task("分析这个目录的项目…")
       ├─ 轮1: _format_messages → [system][task] → API（prompt 747，miss 747）
       │        模型回 tool_calls=[find] → _execute_tool → 12 个文件
       │        messages.append(assistant+tool)（同一个 list）
       ├─ 轮2: 请求 [system][task][A1][tool1] → hit 768 / miss 182
       │        模型回 tool_calls=[read_file ×2] → 双写 messages + history
       ├─ 轮3: hit 1024 / miss 3155（整段文件内容是 miss 大头）
       └─ 轮4: 纯文本回复 → final_answer → break
 → 逐模式记录 per_call hit/miss + 消息 SHA 指纹 + 公共前缀 → evidence.json
```

实测六模式表与逐条解读见 [实验说明](kv-cache.md#运行结果)。

## 动手验证

1. **加第七模式**：每轮重建但钩子全关（内容逐字节不变）——验证"重建本身"是否真不损缓存。预判：DeepSeek token 级前缀下命中率应与 correct 相当；若掉了，说明重建路径有隐藏差异。
2. **把 `_format_messages` 里 SLIDING_WINDOW 的 `while` 回退删掉**：构造一个恰好切在 tool 消息上的窗口，看 API 的 400 报错——那行 while 存在的理由立刻可见。
3. **给 `_get_tools` 的 shuffle 固定 `random.seed(1)`**：工具顺序仍每轮不同（seed 在循环外才有这效果——想清楚 seed 应该设在哪），但跨运行可复现；对照 shuffled_tools 的 14% 是否稳定。
