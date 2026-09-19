# KV Cache 源码精读 · 一条消息列表怎样决定缓存命中

[实验说明](kv-cache.md) · [实测结果](evidence.md#kv-cache) · [学习运行脚本](../assets/task2/run_kv_cache.py)

<div class="design-lead"><span>逐步搭建 / READ THE CODE</span><p>先看 Agent 每轮发出的 prompt 长什么样，再看六种模式分别在前缀的哪个位置动手脚，最后跟着 execute_task 走一遍消息列表的生与死。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号，链接指向课程仓库固定提交；**学习运行脚本原文**来自本次实验的 `run_kv_cache.py`；**教学示意**只用于理解数据形状，不能代替真实模型实验。

## 本页阅读路线

消息列表结构 → 六个模式枚举 → 兼容层 → 数据结构 → 文件工具三件套 → provider 注册表 → 四个上下文钩子 → execute_task 主循环 → 度量与报表 → 实验证据解读。

---

## 1. 一轮 Agent 循环，prompt 到底长什么样

**遇到的问题**

"上下文"这个词太笼统。要理解缓存为什么命中/失效，必须先看清：每一轮发给模型的，**到底是哪些字节**。

**设计思路**

把一次请求拆成三段：`tools` 定义、`messages` 列表、采样参数。服务商把 tools 和 messages 一起序列化成一条 token 序列——**tools 排在最前面**，这是很多"我没改消息为什么缓存还失效"的原因。

**关键代码**

```python
# 教学示意：一轮请求的完整形状（非逐字摘录）
request = {
    "model": "deepseek-flash",
    "messages": [
        {"role": "system",    "content": "You are a helpful ..."},   # ① 系统提示
        {"role": "user",      "content": "分析这个目录的项目 ..."},   # ② 任务
        {"role": "assistant", "tool_calls": [...]},                  # ③ 上轮：模型要调工具
        {"role": "tool", "tool_call_id": "call_x", "content": "..."},# ④ 上轮：工具结果
    ],
    "tools": [ {"type":"function","function":{...read_file...}}, ... ],  # ⑤ 工具定义
    "temperature": 0.7,
    "max_tokens": 2000,
}
```

**执行过程：看数据怎样变**

服务商侧的大致序列化顺序（以 OpenAI 兼容协议为例）：

```text
[ tools 的 JSON 文本 ][ system ][ profile? ][ 历史 1..n ][ 当前 task ]
└── 前缀缓存按 token 块对齐 ───────────────────────────────┘
```

- DeepSeek 的前缀缓存按 **64 token 块**自动对齐：两次请求从头开始逐 token 相同的部分才可能命中；
- 任何一处**靠前**的内容变了（比如 ① 里加了个时间戳，或 ⑤ 的顺序被打乱），它**后面**的所有缓存全部作废——失效是"从第一个差异点开始"的，不是"只丢改过的那句"；
- 反过来，只在**末尾追加**内容，前面的缓存原样可用。这就是本实验全部六个模式的共同原理。

**接回真实源码**

请求组装在 [agent.py · L664–L674](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L664)：`request_data` 先放 model/messages/temperature/max_tokens，再无条件补上 `tools` 与 `tool_choice="auto"`（注释特别说明：TEXT_FORMAT 模式也必须带工具，否则模型没法调用工具，实验做不下去）。

**动手验证**

如果把 `tools` 从请求里删掉，模型还能"读文件"吗？

??? tip "先预测，再展开对照"
    不能。模型看到的只是"有三个函数可调"的说明文字；真正执行在 Harness 里。删掉 tools，模型最多在文本里"假装"调用。这与第 1 章"工具 schema 是模型可见信息、适配器是框架代码"的边界一致。

---

## 2. 六个模式枚举：每种破坏前缀的哪个位置

**遇到的问题**

"错误上下文管理"有很多种，逐个试太散。需要一个最小集合，每种只破坏一个位置，才能把"缓存差"归因到具体行为。

**设计思路**

用枚举把六种消息构造策略变成开关，模式名即自变量。

**关键代码**

**课程源码原文** · [agent.py · L59–L66](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L59)：

```python linenums="59"
class KVCacheMode(Enum):
    """Different KV cache optimization modes"""
    CORRECT = "correct"  # Correct implementation with stable context
    DYNAMIC_SYSTEM = "dynamic_system"  # Changing system prompt with timestamp
    SHUFFLED_TOOLS = "shuffled_tools"  # Shuffling tool order each request
    DYNAMIC_PROFILE = "dynamic_profile"  # Changing user profile with credits
    SLIDING_WINDOW = "sliding_window"  # Only keeping recent 6 messages
    TEXT_FORMAT = "text_format"  # Formatting messages as plain text
```

**执行过程：看数据怎样变**

对照第 1 节的序列化顺序，每个模式的"破坏点"：

| 模式 | 破坏位置 | 每轮实际变化 |
| --- | --- | --- |
| CORRECT | 无 | 消息列表只在末尾追加 |
| DYNAMIC_SYSTEM | ① system | 拼进微秒级时间戳，每次必变 |
| SHUFFLED_TOOLS | ⑤ tools（在最前） | `random.shuffle` 重排三个工具 |
| DYNAMIC_PROFILE | ① 与 ② 之间插入 profile | credits 每轮 -1，消息内容变 |
| SLIDING_WINDOW | ③④ 历史 | 从头部丢弃旧消息，前缀整体"左移" |
| TEXT_FORMAT | ③④ 历史的结构 | 拍平成一条 user 纯文本，结构+体积都变 |

注意 SHUFFLED_TOOLS 的位置最靠前——工具定义排在 system 之前，所以它连 system 的缓存一起毁掉；DYNAMIC_PROFILE 只毁 profile 之后的部分，system+tools 还能命中。本次实测的命中率排序（见 [evidence](evidence.md#kv-cache)）正是这张表的验证。

**接回真实源码**

这六个值在 `_format_messages()`（L513）、`_get_system_prompt()`（L472）、`_get_tools()`（L493）、`_get_user_profile_message()`（L503）四个钩子里被逐一分发——每个钩子只管自己那一段，这是"每个模式只破坏一个位置"能成立的代码基础。

**动手验证**

DYNAMIC_PROFILE 模式下，第 1 轮请求和第 2 轮请求的公共前缀最多到第几条消息？

??? tip "先预测，再展开对照"
    第 1 条（system）。第 2 轮里 profile 消息变成 "...with 99 credits remaining..."，从第 2 条消息起全部不同。实测公共前缀长度确实恒为 1（见 evidence 的 prefix trace `[0, 1, 1, 1]`）。

---

## 3. 兼容层：为什么推理模型只吃 temperature=1

**遇到的问题**

课程默认模型是 Kimi K2.6——一个推理（reasoning）模型。它有两个"脾气"：只接受 `temperature=1`；completion 预算要先花在隐藏推理 token 上。换成 DeepSeek 又没有这些限制。硬编码任何一边都会炸另一边。

**设计思路**

把"这个模型是不是推理模型"做成纯函数判断，温度和 max_tokens 各包一层安全函数。

**关键代码**

**课程源码原文** · [agent.py · L28–L51](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L28)：

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

**执行过程：看数据怎样变**

| 传入 model | temperature 实发 | max_tokens 实发 |
| --- | --- | --- |
| `kimi-k2.6` | 1 | max(2000, 4096) = 4096 |
| `deepseek-flash` | 0.7（原样） | 2000（原样） |

`max(requested, 4096)` 的方向值得注意：只放大不缩小。推理模型的工具调用可能被先花掉的推理 token 截断，所以要保底 4096；非推理模型不需要这份余量。docstring 里写明了原因（L47–L50）。

**接回真实源码**

调用点在 execute_task 的请求组装处（L667–L668）：`"temperature": _reasoning_safe_temperature(self.model, 0.7)`。本次 DeepSeek 实验走的全是"原样"分支。

**动手验证**

为什么判断用子串匹配而不是维护一张完整的模型名单？

??? tip "先预测，再展开对照"
    名单永远追不上新版本（k2.7、k3、k3.5……）。"家族前缀"匹配牺牲一点精确性换取对新版本默认安全。代价是误伤可能：名字里恰好含 `kimi-k2.6` 的别名会被当成推理模型——对本实验这是保守方向的错误（多发预算），可以接受。

---

## 4. 两个数据类：记"次数"还是记"token 数"

**遇到的问题**

"缓存命中率"有两种口径：多少次调用发生了命中；多少个 prompt token 来自缓存。混用一个词会得出矛盾结论。

**设计思路**

AgentMetrics 把两种口径分开存，外加逐轮 TTFT 序列。

**关键代码**

**课程源码原文** · [agent.py · L79–L91](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L79)：

```python linenums="79"
@dataclass
class AgentMetrics:
    ttft: float = 0.0  # Time to first token (first iteration)
    ttft_per_iteration: List[float] = field(default_factory=list)
    total_time: float = 0.0
    iterations: int = 0
    tool_calls: int = 0
    cache_hits: int = 0       # 次数：多少轮发生了命中
    cache_misses: int = 0     # 次数：多少轮完全没有命中
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0    # token 数：累计命中了多少 token
```

`ToolCall`（L69–L76）则记录每次工具调用的名字、参数、结果和时刻——`result` 直接存工具返回的 dict，错误也是结果的一部分。

**执行过程：看数据怎样变**

一次 4 轮的运行里：`cache_hits=3, cache_misses=1`（第 1 轮冷启动必 miss）与 `cached_tokens=6016`（第 2/3/4 轮分别命中 768/1024/4224 个 token）描述的是同一次运行的两面。main.py 的报表两列都打（`Hit%` 用次数、`Cache%` 用 token），见 [main.py · L95–L118](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/main.py#L95)。

**接回真实源码**

`cache_hits/misses` 的累加逻辑藏在 usage 解析分支里（L708–L726）：命中字段 >0 算一次 hit，否则一次 miss。**注意 DeepSeek 的情况**：这两个口径的原始字段它一个都不报（详见第 9 节），所以课程 metrics 对 DeepSeek 全程记 0——学习版因此在自己的记录层重新抓取（见 [evidence](evidence.md#kv-cache) 的口径说明）。

**动手验证**

一个模式 10 轮里 9 轮各命中 64 token、1 轮 miss，另一个模式 2 轮里 1 轮命中 5000 token。哪个"更好"？

??? tip "先预测，再展开对照"
    按次数口径前者 90%，后者 50%；按 token 口径前者约 6%，后者可能 60%+。结论依赖口径——这正是把两个字段分开存的原因。成本上 token 口径才对应钱，延迟上还要看命中比例。

---

## 5. 文件工具三件套：安全、分页与"错误也是观测"

**遇到的问题**

Agent 要用模型读真实文件，三个经典风险：路径逃逸（`../../` 读到根目录）、读超大文件撑爆上下文、工具抛异常炸掉整个循环。

**设计思路**

三个工具（read_file / find / grep）全部返回结构化 dict；所有上限（10KB、100 条匹配、50 个文件）写死；路径先 `realpath` 再校验前缀。

**关键代码**

**课程源码原文** · [agent.py · L113–L122](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L113)（路径安全）：

```python linenums="113"
full_path = os.path.join(self.root_dir, file_path)
# Security check - ensure path is within root_dir
real_path = os.path.realpath(full_path)
if not real_path.startswith(self.root_dir):
    return {
        "error": f"Access denied: Path outside root directory",
        "success": False
    }
```

**课程源码原文** · [agent.py · L144–L148](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L144)（负 size 哨兵）：

```python linenums="144"
if size is None or size < 0:
    # Negative size is a common "read all" sentinel; avoid lines[i:-n].
    end = total_lines
else:
    end = min(offset + size, total_lines)
```

**执行过程：看数据怎样变**

- `realpath` 把符号链接和 `..` 全部展开成绝对路径再做前缀检查——攻击者用 `symlink` 绕过的路也被堵上（前提是 root_dir 本身也是绝对路径，构造函数 L98 里 `os.path.abspath(root_dir)` 保证了这点）；
- `size=-1` 若直接用 `lines[offset:-1]` 会"读到最后一行之前"，语义完全跑偏——哨兵分支把它翻译成"读到底"；
- read_file 超 10KB 截断并打 `truncated` 标（L156–L158）；find 用 `dirs[:] = [...]` 原地修改实现**遍历中剪枝**（L220，跳过隐藏目录和 `__pycache__`）；grep 限定文本扩展名、行截断 200 字符、最多 100 条匹配（L301–L335）。

**接回真实源码**

工具失败的"观测化"在两层落地：工具内部 `except` 一律返回 `{"error":..., "success": False}`（L170–L179 等）；`_execute_tool()` 再包一层（L615–L619）。模型收到的是可读的错误文本，它下一轮可以改参数重试——这正是第 1 章"纠正职责"在工具层的体现。

**动手验证**

模型把 `read_file` 的参数写成 `{"file_path": "x.py", "line_number": 3}`（一个不存在的参数名），会发生什么？

??? tip "先预测，再展开对照"
    不会炸。`_execute_tool()`（L598–L614）用 `inspect.signature` 求出工具函数的真实形参，把模型给的参数**按名过滤**——`line_number` 被丢弃并记一条 warning，`file_path` 正常传入。这是对"模型幻觉参数"的静默防御；更严格的做法是把 schema 校验失败的错误回传给模型让它自我纠正。

---

## 6. Agent 构造：provider 注册表怎样决定"跟谁说话"

**遇到的问题**

同一份 Agent 代码要能对 Kimi 官方、OpenRouter、DeepSeek 等不同端点工作。endpoint/key/模型名三者的映射规则散在各实验里会各自漂移。

**设计思路**

仓库根的 `agentbook.providers` 包把映射集中成两层：`registry.py` 纯数据（谁存在、叫什么），`resolution.py` 纯策略（谁优先、何时兜底）。实验代码只管问一句 `resolve_backend(provider, model, api_key)`。

**关键代码**

**课程源码原文** · [agent.py · L370–L382](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L370)（Agent 侧的接入点）：

```python linenums="370"
# 默认走 Moonshot/Kimi 官方端点；若传入的是 OpenRouter key（sk-or-…），
# 则自动回退到 OpenRouter，并把 kimi-* 模型名映射为 moonshotai/kimi-k2。
provider = "openrouter" if is_openrouter_key(api_key) else "kimi"
backend = resolve_backend(provider, model=model, api_key=api_key)
self.client = OpenAI(
    api_key=backend.api_key,
    base_url=backend.base_url
)
self.model = backend.model
```

**课程源码原文** · [registry.py · L57–L65](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/agentbook/providers/registry.py#L57)（注册表里的 DeepSeek 条目）：

```python linenums="57"
"deepseek": Provider(
    name="deepseek",
    base_url="https://api.deepseek.com",
    default_model="deepseek-v4-flash",
    key_vars=("DEEPSEEK_API_KEY",),
    base_url_var="DEEPSEEK_BASE_URL",
),
```

`resolution.py` 的 [resolve_backend · L127–L216](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/agentbook/providers/resolution.py#L127) 是一条刻意写成人话的优先级链：① gpt-5* 在有 OpenRouter key 时改道（官方直连要组织验证且拒绝函数工具+推理并存）；② provider 自己的 key（或免 key 的本地运行时）直连；③ 都没有则 OpenRouter 兜底；④ 全空才报错，报错信息列出该设的环境变量。

**执行过程：看数据怎样变**

**学习运行脚本原文** · [run_kv_cache.py · L67–L76](../assets/task2/run_kv_cache.py)（本次 DeepSeek 注入点）：

```python linenums="57"
import agentbook.providers as providers

_real_resolve = providers.resolve_backend

def _deepseek_backend(provider, model=None, api_key=None, **kwargs):
    return _real_resolve("deepseek", model=MODEL, api_key=KEY)

providers.resolve_backend = _deepseek_backend
```

课程 Agent 里 `provider` 只会是 `kimi` 或 `openrouter` 二选一，没有 DeepSeek 的口子。但 L374 的 `from agentbook.providers import ... resolve_backend` 发生在**构造时**，从模块属性取值——所以在构造 Agent 之前替换 `agentbook.providers.resolve_backend`，Agent 拿到的就是我们的函数：无论传来 `kimi` 还是别的，都改解析成 DeepSeek 后端。这与 task1 给 `Config.resolve_llm` 打补丁是同一手法：**不动课程源码，只在模块边界注入配置**。

**接回真实源码**

`Backend` 返回的 `model` 有一个额外坑：请求 `deepseek-v4-flash`，响应里 `response.model` 回报的是 `deepseek-flash`。凡是拿"响应模型名 == 请求模型名"做回执校验的代码（如实验 2-5 的 `accepted_receipt`），必须用能往返一致的名字。本次 kv-cache 实验不受影响（它不校验模型名），2-5 的运行脚本因此显式用了 `deepseek-flash`。

**动手验证**

为什么不直接改课程 agent.py 里的 `"kimi"` 为 `"deepseek"`，而要绕道打补丁？

??? tip "先预测，再展开对照"
    补丁保证"仓库里的课程源码零改动"，证据里对源文件的 SHA-256 哈希始终对应上游原样（evidence.json 的 source_hashes）。改源码则无法区分"课程代码的行为"和"我改过的行为"——学习实验的对照性就丢了。

---

## 7. 四个上下文钩子：每个模式只动自己那一段

**遇到的问题**

六个模式如果散在主循环里互相缠绕，就没法保证"每轮只变一个位置"。需要把"上下文怎么构造"从"循环怎么跑"里剥出来。

**设计思路**

四个小钩子各管一段：system 文案、tools 顺序、profile 消息、历史组装。主循环只负责调它们。

**关键代码**

**课程源码原文** · [agent.py · L486–L489](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L486)（DYNAMIC_SYSTEM：时间戳）：

```python linenums="486"
if self.mode == KVCacheMode.DYNAMIC_SYSTEM:
    # Add timestamp to system prompt (breaks KV cache)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    return f"{base_prompt}\n\nCURRENT TIME: {timestamp}"
```

**课程源码原文** · [agent.py · L497–L499](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L497)（SHUFFLED_TOOLS：浅拷贝后洗牌）：

```python linenums="497"
if self.mode == KVCacheMode.SHUFFLED_TOOLS:
    # Shuffle tool order (breaks KV cache)
    random.shuffle(tools)
```

**执行过程：看数据怎样变**

- `%f` 是**微秒**。两次调用间隔哪怕 1 秒，时间戳也必然不同——system 段必变，后面全毁。这是六个模式里"性价比最低"的破坏：为了一个没人用的时钟，付整条前缀重算的钱；
- `_get_tools()` 里 `tools = self.tool_definitions.copy()` 是**列表浅拷贝**：shuffle 只重排副本，`self.tool_definitions` 保持原序——不污染后续模式。浅拷贝够用，因为元素（工具 dict）本身不被修改，只是顺序变；
- `_get_user_profile_message()`（L503–L511）里 `self.user_credits -= 1` 让 profile 文案每轮不同（100 → 99 → 98 …），同时它**插在 system 之后、任务之前**——一个看似无害的"个性化"位置，杀伤半径却是其后的一切。

**接回真实源码**

历史组装钩子 `_format_messages()` 是下一节的主角；它处理 SLIDING_WINDOW 与 TEXT_FORMAT 两个最复杂的模式。

**动手验证**

DYNAMIC_SYSTEM 模式第 2 轮的公共前缀应该是多少条消息？和 DYNAMIC_PROFILE 相比谁更糟？

??? tip "先预测，再展开对照"
    DYNAMIC_SYSTEM 是 0 条（第 1 条就变了）；DYNAMIC_PROFILE 是 1 条（system 保住）。token 层面 DYNAMIC_SYSTEM 全部 miss、DYNAMIC_PROFILE 还能命中 system+tools 段。实测：dynamic_system 命中 0 / 13,930，dynamic_profile 命中 2,432 / 13,643——方向完全一致。

---

## 8. _format_messages：滑动窗口的配对回退与文本拍平

**遇到的问题**

两个"看起来更省"的模式各有一个隐蔽坑：滑动窗口可能切出"孤儿 tool 消息"（它的主人 assistant 消息被裁掉了，API 直接 400）；文本拍平则改变了消息的角色结构。

**设计思路**

组装函数按模式分三路：全量 / 窗口 / 拍平。窗口路先切再**回退**；拍平路把所有历史压进**一条** user 消息。

**关键代码**

**课程源码原文** · [agent.py · L528–L539](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L528)（窗口 + 配对回退）：

```python linenums="528"
if self.mode == KVCacheMode.SLIDING_WINDOW:
    # Keep only the most recent 6 history messages (the window).
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

**课程源码原文** · [agent.py · L540–L573](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L540)（文本拍平，节选）：

```python linenums="540"
elif self.mode == KVCacheMode.TEXT_FORMAT:
    # Format all history as plain text (breaks KV cache)
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
```

**执行过程：看数据怎样变**

同一份 5 条历史的三个模式输出对比（教学示意）：

```text
全量模式:  [system][task][A1][T1][A2][T2]...（结构消息，逐轮追加）
窗口模式:  [system][最近6条(可能回退到配对起点)][task]
拍平模式:  [system][user: "Previous conversation:\nASSISTANT: ...\nTOOL RESPONSE: ..."][task]
```

- 窗口回退的代价：`while start > 0 and role == "tool"` 可能多带回几条本该裁掉的消息——正确性优先于"精确 6 条"；窗口还有一个副作用：**每轮都从头部丢消息，前缀左移**，旧缓存找不到对齐位置；
- 拍平后 `n_messages` 恒为 3（system/巨长 user/task），但那条 user 的内容逐轮**只增不改**——纯 token 前缀其实是稳定的！这是本次实验最反直觉的结果：DeepSeek 按纯 token 前缀缓存，拍平文本照样命中（70%），但它**总 token 爆炸**（约是 CORRECT 的 1.6 倍）且丢失结构语义。缓存命中率高 ≠ 高效。

**接回真实源码**

`_format_messages` 的调用时机是第 9 节主循环的关键分叉——它**不在**每轮工具调用后调用（那轮内直接 append），只在**迭代边界**调用。

**动手验证**

窗口模式下，为什么丢历史反而可能比全量更快失效，但总 miss token 又不多？

??? tip "先预测，再展开对照"
    每轮丢头部 → 前缀永远对不齐 → 命中率低；但窗口同时把上下文压小了 → 需要重算的 token 也少。实测 sliding_window 命中率 53% 低于 CORRECT 的 51% 附近但总 miss 只有 4,892（最少）。"省"和"缓存友好"是两个维度——这正是书里"截断可能适得其反"的量化版本。

---

## 9. execute_task 主循环：一次构建 vs 每轮重建

**遇到的问题**

前缀缓存的前提是"请求内容稳定"。但 Agent 循环天然要追加新消息。如果每轮都把消息列表推倒重来（哪怕内容一样），缓存还能工作吗？——能，只要逐字节相同。真正致命的是"重建时顺手改了内容"。实验要让两类失败清晰对照。

**设计思路**

主循环里用一个 if 把六模式劈成两半：CORRECT 只在第 1 轮构建消息列表，之后**一直 append 同一个 list**；其余模式每轮从 history 重建。配合上一节的钩子，"重建"过程中各模式注入各自的变化。

**关键代码**

**课程源码原文** · [agent.py · L641–L661](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L641)（本实验的心脏）：

```python linenums="641"
while iteration < max_iterations:
    iteration += 1

    # CRITICAL: Message handling for KV cache demonstration
    #
    # CORRECT mode: Build messages once on first iteration, then keep appending
    #   - Maintains stable context → KV cache works efficiently
    #
    # INCORRECT modes: Recreate entire messages list from history each iteration
    #   - Forces complete context reconstruction → KV cache invalidated
    #   - Within an iteration, we still append to messages for proper API flow
    #   - But at the start of each new iteration, we rebuild from scratch

    if self.mode == KVCacheMode.CORRECT:
        # Correct mode: Build messages once, then keep using same list
        if iteration == 1:
            messages = self._format_messages(original_task)
    else:
        # Incorrect modes: Recreate messages from history each iteration
        # This forces cache invalidation due to context changes
        messages = self._format_messages(original_task)
```

**课程源码原文** · [agent.py · L744–L797](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L744)（轮内追加 + 双写）：

```python linenums="744"
if hasattr(message, 'tool_calls') and message.tool_calls:
    # Add the assistant message with tool calls
    # Always append to messages for current iteration
    messages.append(message.model_dump())
    # Also append to history for next iteration
    self.conversation_history.append(message.model_dump())

    for tool_call in message.tool_calls:
        ...
        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result)
        }
        messages.append(tool_message)                  # 本轮请求继续用
        self.conversation_history.append(tool_message) # 下一轮重建时用
```

**执行过程：看数据怎样变**

CORRECT 模式的消息列表时间线（**同一个 list 对象**）：

```text
轮1请求: [S][T]                      → 冷启动 miss
轮1结束: [S][T][A1][tool1]           （append 进同一个 list）
轮2请求: [S][T][A1][tool1]           → 前缀 [S][T][A1] 命中
轮2结束: [S][T][A1][tool1][A2][tool2]
轮3请求: ...                          → 更长的前缀命中
```

错误模式的消息列表时间线（每轮**新 list**，内容由钩子决定）：

```text
轮1请求: [S+t₁][T]                   （dynamic_system：t=时间戳）
轮2请求: [S+t₂][T][A1][tool1]        ← t₂≠t₁，第 1 条就变，后面全作废
```

注意一个容易误读的点：**"每轮重建"本身并不必然丢缓存**。如果重建出的内容逐字节相同，token 前缀依旧稳定。真正毁缓存的是各钩子在重建时注入的变化（时间戳/credits/顺序/窗口/拍平）。实验把"重建"与"变化"绑在同一组里对照 CORRECT，观察的是叠加效果；想单独验证"重建但不变化"，可以加一个不动内容的第七模式（本次未做，见 evidence 的边界说明）。

usage 解析（L699–L730）先找 `usage.cached_tokens`（Kimi 直挂），找不到再找 `usage.prompt_tokens_details.cached_tokens`（OpenAI 风格）。DeepSeek 两个都不提供——它用 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`（进 pydantic 的 extra 字段）。所以课程 metrics 的 cached_tokens 对 DeepSeek 恒 0，**学习运行脚本在记录层抓原始 usage dict**，证据按 DeepSeek 口径统计。

**接回真实源码**

- TTFT 记录（L677–L687）：`time.time()` 包住整个**非流式**请求。它测的其实是"整次往返"，包含全部生成时间——末轮长答案在所有模式都最慢（实测约 6 秒），读数时必须把"工具轮"和"最终答案轮"分开看；
- 参数解析容错（L753–L758）：`json.loads(tool_call.function.arguments)` 失败时 `function_args={}` 并把解析错误包成工具结果回传——模型下一轮能看到自己发坏了 JSON；
- 任何 API 异常直接 `break`（L815–L817），不重试：教学取舍，生产代码要加退避重试。

**动手验证**

CORRECT 模式第 3 轮请求的 prompt 里有 `[S][T][A1][tool1][A2][tool2]`，缓存命中的是哪一段？miss 的又是哪一段？

??? tip "先预测，再展开对照"
    命中的是**上一次请求发出去的全部内容**：`[S][T][A1][tool1×2]`（第 2 轮请求就到 tool1 为止）。miss 的是第 2 轮**响应之后**追加的 `[A2][tool2×3]`——A2 是模型对第 2 轮的回复，tool2 是其执行结果，它们第一次出现在第 3 轮请求里。实测第 3 轮 hit=1024/miss=3155：miss 偏大是因为 tool 结果（整段文件内容）本身很长，且 64-token 块对齐会吃掉边界零头。

---

## 10. compare_implementations 与 main.py：报表、离线复盘与成本模型

**遇到的问题**

跑完六模式得到一堆 dict，怎么一眼看出差别？没配额的日子里怎么复盘旧结果？

**设计思路**

`compare_implementations()`（[agent.py · L834–L888](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/agent.py#L834)）顺序跑六模式、逐模式打印；main.py 提供 `--report` 离线聚合 `result_*.json`，外加一个透明的成本示意。

**关键代码**

**课程源码原文** · [main.py · L81–L92](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/main.py#L81)（成本模型）：

```python linenums="81"
def _billable_tokens(m: Dict[str, Any], cache_price_ratio: float) -> float:
    """Illustrative billable prompt tokens under a prompt-cache discount."""
    prompt = m.get("prompt_tokens", 0) or 0
    cached = m.get("cached_tokens", 0) or 0
    cached = min(cached, prompt)
    return (prompt - cached) + cached * cache_price_ratio
```

**课程源码原文** · [main.py · L60–L67](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/kv-cache/main.py#L60)（旧格式兼容 + 受限 eval）：

```python linenums="60"
if isinstance(metrics, str) and metrics.startswith("AgentMetrics("):
    # Safe eval: only AgentMetrics is exposed, no builtins.
    try:
        obj = eval(metrics, {"__builtins__": {}}, {"AgentMetrics": AgentMetrics})
        return asdict(obj)
```

**执行过程：看数据怎样变**

- `_billable_tokens` 是纯算术：未命中部分全价 + 命中部分 × 折扣比（默认 0.1）。它刻意不内置任何厂商价格——`--cache-price-ratio` 由使用者传，报表脚注写明"仅为成本示意"；
- 旧版单模式文件曾用 `default=str` 把 `repr(AgentMetrics(...))` 存进 JSON；`_coerce_metrics` 用"空 builtins + 只暴露 AgentMetrics"的受限 eval 把它救回来。这是教学代码里少见的 eval 用法，约束在只信自家 dataclass 的 repr 上；
- `run_report()`（L147）从 `result_*.json` / `comparison_*.json` 聚合出与在线版同款的 11 列对比表——**不需要 API key**。复盘历史证据和重新做实验是两条独立路径。

**接回真实源码**

CLI 的模式选择优先级（L511–L544）：`--compare` > `--mode` > 交互式菜单；`--report` 完全离线最先返回。本次学习版没有走 CLI，而是直接构造 `KVCacheAgent` 循环六模式——因为要注入 DeepSeek 后端和记录层（见第 6 节）。

**动手验证**

`--cache-price-ratio 0.1` 下，一个 prompt=10000、cached=6000 的模式，账单 token 是多少？如果缓存不要钱（ratio=0）呢？

??? tip "先预测，再展开对照"
    0.1 时：4000 + 6000×0.1 = 4600；ratio=0 时：4000。省的上限就是 cached 数，缓存折扣只作用于命中部分。换成 DeepSeek 的实际定价（命中输入远低于未命中输入），同样的公式给出真实的账单差异。

---

## 11. 实测证据：prefix trace 怎样把机制"拍在案上"

**遇到的问题**

命中率是结果，怎么证明"命中/失效的原因就是前缀变化"，而不是网络抖动？

**设计思路**

学习运行脚本给每次请求的每条消息算 SHA-256 指纹（内容前 12 位），相邻两次调用求"公共前缀条数"。前缀断了，机制就坐实了。

**关键代码**

**学习运行脚本原文** · [run_kv_cache.py · L82–L106](../assets/task2/run_kv_cache.py)：

```python linenums="69"
def _message_digest(messages):
    rows = []
    for msg in messages:
        content = msg.get("content") or ""
        row = {
            "role": msg.get("role"),
            "chars": len(content) if isinstance(content, str) else -1,
            "sha": hashlib.sha256(content.encode("utf-8", "ignore")).hexdigest()[:12],
        }
        tcs = msg.get("tool_calls") or []
        if tcs:
            row["tool_calls"] = [tc.get("function", {}).get("name", "?") for tc in tcs]
        rows.append(row)
    return rows

def _common_prefix_len(a, b):
    n = 0
    for x, y in zip(a, b):
        if x.get("sha") != y.get("sha") or x.get("role") != y.get("role"):
            break
        n += 1
    return n
```

**执行过程：看数据怎样变**

本次 DeepSeek 六模式实测（完整数据见 [evidence](evidence.md#kv-cache)）：

| 模式 | 相邻调用公共前缀（条） | 命中 token | miss token | 命中率 |
| --- | --- | ---: | ---: | ---: |
| correct | `[0, 2, 5, 11]` | 6,016 | 5,883 | 51% |
| dynamic_system | `[0, 0, 0, 0]` | **0** | 13,930 | **0%** |
| shuffled_tools | `[0, 1, 3, 9]` | 1,536 | 9,710 | 14% |
| dynamic_profile | `[0, 1, 1, 1]` | 2,432 | 11,211 | 18% |
| sliding_window | `[0, 1, 1, 7]` | 5,504 | 4,892 | 53% |
| text_format | `[0, 1, 1, 1, 1, 1]` | 13,568 | 5,789 | 70% |

逐行都能对回第 2 节的"破坏位置"表：dynamic_system 的 trace 全 0（第 1 条就变）；dynamic_profile 恒 1（只剩 system）；correct 单调递增到 11（上一轮的全部消息都在）。

**接回真实源码**

课程自带的 Kimi K2.6 回执（`chapter2/kv-cache/result_*_20260718_kimi_k2_6.json`）是同一实验在另一家厂商的运行：其 dynamic_system 仍有 768 cached tokens。**不能跨厂商比较绝对值**——各家的命中口径、块粒度、tools 段是否单独缓存都不同。机制（前缀稳定 → 命中）是共通的，数值是厂商实现细节。这也解释了课程 README 为什么建议"以命中率/缓存比为稳健信号，TTFT 仅作参考"。

**动手验证**

shuffled_tools 的 trace 是 `[0, 1, 3, 9]`——第 1 条消息（system）明明没变，为什么第 2 次调用的公共前缀是 0？

??? tip "先预测，再展开对照"
    `_common_prefix_len` 只看 messages 列表。system 确实没变（trace 里第 3 次是 3、第 4 次是 9，说明消息对齐过），第 2 次为 0 说明当时消息开头就没对上——但真正的原因在 messages **之外**：tools 顺序变了（4 次调用出现 3 种顺序），而 tools 排在序列化前缀的最前面，token 前缀在第 0 块就分叉。这也是为什么学习脚本把 `tools_order` 每次调用都记录下来——只看 messages 会漏掉这个最靠前的破坏点。

---

## 最后回到项目

学习脚本六模式循环 → 课程 `_format_messages`/钩子 → `execute_task` 的构建/重建分叉 → 记录层指纹与 usage 抓取 → [看真实实验结果](evidence.md#kv-cache)。
