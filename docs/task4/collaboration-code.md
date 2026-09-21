# 协作工具：一步步读源码

[Task 4 索引](index.md) · [实测证据 JSON](../assets/task4/collaboration-evidence.json) · [学习运行脚本](../assets/task4/run_4_5_collaboration.py)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>实验 4-5 的课程源码是一个「真 MCP 客户端 + 真 MCP stdio 服务器」的组合：runner 通过 stdio 拉起 41 个工具的协作服务器，依次实测子 Agent 同步/异步生命周期、两种上下文传递策略、HITL 待批与保守超时、三渠道投递门禁。本页按源码顺序把 runner 的每个函数过一遍，再拆服务器侧的子 Agent 三范式、HITL 状态机与 provider 解析，最后用一次真实执行把整条链串起来。读完本页，你应该能在不打开源码的情况下说出每一段代码在防什么。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号，链接指向课程仓库固定提交 `cf7f7a8`。**学习运行脚本原文**来自 `learning/task4/run_4_5_collaboration.py`（它对课程 runner 是"原样复用 + 两处注入"，不复制粘贴）。**教学示意**仅用于理解数据形状或状态转移，不是能跑的代码。另外本页把**实测数字**（来自运行目录 `learning/task4/runs/4-5_collaboration/20260921T112238Z/`）与**推断**（我读代码得出的、本次未打印验证的结论）分开标注。

**主体文件**：[chapter4/collaboration-tools/run_experiment_4_5.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py)（515 行，本页主角）。**服务器侧**：`src/subagent_tools.py`（637 行）、`src/hitl_tools.py`（343 行）、`src/llm_fallback.py`（93 行）、`src/main.py`（569 行，只读注册骨架）。

---

## 0. 函数清单地图（一个不漏）

行号用 `grep -n` 在固定提交上核对过，不是凭印象写的。

### (a) `run_experiment_4_5.py`：全部 def 与模块常量

| # | 函数/常量 | 行号 | 一句话作用 | 谁调用它 |
| --- | --- | --- | --- | --- |
| — | `HERE` / `SERVER` / `VALIDATION` | L23–25 | 本目录 / 服务器入口 / 证据根 | 全文件 |
| — | `CREDENTIAL` | L26 | 凭据形状正则（`sk-`、`ghp-` 等） | `write_json` |
| — | `SENSITIVE_ENV_NAMES` | L27–43 | 15 个需要脱敏的环境变量名 | `run` |
| — | `DELIVERY_GATES` | L44–48 | 三条"真实投递"门禁名（永不豁免） | `classify_status` |
| — | `SYNTHETIC_PRIVACY_CANARY` | L49 | 隐私哨兵字符串 | `run`、门禁判定 |
| 1 | `parse_human_decision` | L52–59 | 解析一行 `APPROVE[: notes]` / `REJECT[: notes]` | `run`（交互模式） |
| 2 | `_readline_before_timeout` | L62–80 | 带 deadline 的逐字节读行（同步实现） | `read_human_decision_line` |
| 3 | `read_human_decision_line` | L83–94 | 上面那个的 async 包装 + 超时错误翻译 | `run` |
| 4 | `remaining_before_deadline` | L97–102 | 共享 deadline 的剩余秒数（≤0 即抛） | `run` |
| 5 | `notification_readiness` | L105–118 | 三条投递门禁各自的变量是否齐备 | `run` |
| 6 | `human_decision_accepted` | L121–132 | MCP 是否**为同一个 request 接受了**本次真人决定 | `run`、`publication_is_authorized` |
| 7 | `publication_is_authorized` | L135–143 | 是否明确批准了"对外发布" | `run`（写 summary） |
| 8 | `classify_status` | L146–154 | passed / blocked / failed 三分类 | `run`、`main` |
| 9 | `redact_material` | L157–168 | 递归脱敏任意嵌套结构 | `run`、`retain_human_decision` |
| 10 | `retain_human_decision` | L171–180 | 生成脱敏后的决定留档（不改内存对象） | `run` |
| 11 | `sha` | L183–184 | 文件 SHA-256 | `run`（manifest/latest） |
| 12 | `write_json` | L187–192 | 落盘前做凭据形状检查的 JSON 写 | 全文件 |
| 13 | `parse_value` | L195–206 | 嵌套 JSON 字符串 / Python 字面量的还原 | `unwrap` |
| 14 | `unwrap` | L209–215 | MCP 工具结果 → 纯 Python 值 | `run` 内部的 `call` |
| 15 | `run` | L218–485 | **核心**：整场战役（9 条门禁） | `main` |
| 16 | `main` | L488–511 | CLI 入口 + 退出码 | 入口 |
| — | `run.call`（闭包） | L269–284 | 单次工具调用：计时、unwrap、脱敏、落收据 | `run` ×15 |

### (b) `src/subagent_tools.py`：关键函数（三范式主线，其余归并）

| # | 函数/常量 | 行号 | 一句话作用 |
| --- | --- | --- | --- |
| — | `_subagents` / `_async_tasks` | L44 / L46 | 进程内子 Agent 注册表 / 后台任务表 |
| — | `DEFAULT_MODEL` | L65–67 | 有凭据走 `resolve_llm()`，否则读 `OPENAI_MODEL` |
| — | `_offline()` | L72–74 | 无任何 LLM 凭据 → 确定性离线模式 |
| 1 | `_get_client` | L77–87 | 建 OpenAI 兼容客户端（含 base_url 兜底） |
| 2 | `_record_call` | L90–120 | **原子**追加一条无凭据的原始模型回执 |
| 3 | `_count_tokens` | L123–132 | 移交上下文的 token 计数（tiktoken，退化为 len//4） |
| 4 | `_build_system_prompt` | L139–155 | 子 Agent 系统提示：角色 + 来源标注 + 任务边界 + JSON 输出 |
| 5 | `_prepare_minimal_context` | L173–208 | **策略一**：只传任务 + 手挑切片，**零额外 LLM 调用** |
| 6 | `_prepare_llm_generated_context` | L211–280 | **策略二**：多一次 LLM 提炼 + 隐私过滤，`prep_tokens` 记账 |
| 7 | `_prepare_context` | L283–296 | 策略分发（未知策略直接抛） |
| — | `_SENSITIVE_MARKERS` / `_offline_summarize_context` | L303 / L306–316 | 离线时的规则式隐私过滤替身 |
| 8 | `_run_turn` | L338–358 | 子 Agent 的一个 LLM 回合（阻塞） |
| 9 | `spawn_subagent` | L361–471 | **核心**：建子 Agent，sync 等结果 / async 起后台任务 |
| 10 | `send_message_to_subagent` | L474–503 | 追加 `[FROM_MAIN_AGENT]` 消息再跑一回合 |
| 11 | `cancel_subagent` | L506–526 | 置状态 + 取消后台 task |
| 12 | `get_subagent_status` | L529–544 | 查状态/结果（async 用） |
| 13 | `run_context_strategy_comparison` | L551–633 | 同一任务跑两种策略并打印对比（`main.py subagent compare` 用它） |
| — | `_env_or_default` / `_normalize_parent_context` / `_run_turn_offline` | L49–58 / L162–170 / L319–335 | 辅助函数，正文一带而过 |

### (c) `src/hitl_tools.py`：全部 def

| # | 函数 | 行号 | 一句话作用 |
| --- | --- | --- | --- |
| — | `_pending_requests` | L14 | 进程内待批请求表（模块级 dict） |
| 1 | `request_admin_approval` | L17–73 | 建 `pending` 记录 → 通知 → 等待 |
| 2 | `_notify_admin_of_request` | L76–148 | 四渠道通知 + 可选 webhook（全失败只告警） |
| 3 | `_wait_for_admin_response` | L151–208 | **2 秒轮询**的状态机主循环 + 超时兜底 |
| 4 | `respond_to_request` | L211–270 | 操作员应答；**终态请求上的迟到/重复应答一律拒绝** |
| 5 | `list_pending_requests` | L273–298 | 只列 `pending` 的记录 |
| 6 | `request_admin_input` | L301–343 | 复用 `request_admin_approval`，把 approved 映射成 input |

### (d) `src/llm_fallback.py`：全部 def

| # | 函数 | 行号 | 一句话作用 |
| --- | --- | --- | --- |
| 1 | `map_model_for_openrouter` | L26–41 | 裸模型 id → `provider/model` 形式 |
| 2 | `has_llm` | L44–48 | 五把钥匙里有任意一把就算"有 LLM" |
| 3 | `resolve_llm` | L51–93 | **provider 解析**：dashscope / moonshot 分支 + OpenRouter 兜底 |

### 附：`src/main.py` 的注册骨架（只读骨架，不讲实现）

| 位置 | 内容 |
| --- | --- |
| L92 | `mcp = FastMCP("collaboration-tools")` |
| L99–L531 | **41** 个 `@mcp.tool(description=...)` 装饰的 `mcp_*` 协程（浏览器 5 / 通知 4 / HITL 4 / 定时器 5 / 象棋 9 / Excel 8 / 智能 3 / 子 Agent 4 = 41） |
| L538–551 | `_serve()`：先 `_load_timers()` 再 `run_stdio_async()`，**同一个事件循环**（注释解释了定时器被回收的旧 bug） |

!!! warning "两处与任务书不符，已按源码实测修正"
    任务书说"FastMCP 注册 45 个工具"、并给了 `python main.py list` 看 45 个。实测两处都要修正：

    1. **`src/main.py` 注册的是 41 个工具**——`grep -c "@mcp.tool" src/main.py` = 41，且真连服务器 `list_tools()` 返回 41（见第 3 节）。
    2. **`41` 不是 `python main.py list` 看到的数**：`python main.py list` 走的是**顶层** `main.py`（另一个文件！）的 `COLLAB_TOOLS` 字典，只列**12 个协作工具**（子 Agent 4 + HITL 4 + 通知 4），不列浏览器/象棋/Excel/定时器。两个数是两个口径，都不是 45。

---

## 1. 主线调用图

`run()` 一镜到底的调用顺序（缩进即调用栈）：

```text
main()                                        L488  解析 --campaign-id/--interactive-human/--human-timeout-seconds/--real-notifications
 └─ asyncio.run(run(...))                     L218
     ├─ notification_readiness(env)           L105  三条投递门禁预检（email / telegram / slack）
     ├─ run_dir = VALIDATION / campaign_id    L233  mkdir(exist_ok=False) —— 同 id 重跑直接炸，逼你换 id
     ├─ write_json(protocol.json)             L235  复制 experiment_protocol.json 进 run_dir
     ├─ env.update(...)                       L237  注入 COLLAB_PROVIDER / OPENAI_MODEL / 回执路径 /
     │                                              HITL_TIMEOUT_SECONDS=2 / BROWSER_HEADLESS / TIMER_STORAGE_PATH
     ├─ if not real_notifications: env 清空   L243  把 .env 里的**占位**凭据抹成空串（防误投递）
     ├─ sensitive_values = 15 个非空 env 值   L254  后面脱敏用的"黑名单"
     ├─ StdioServerParameters(cwd=HERE/"src") L257  ★ 子进程 cwd 必须是 src/（裸导入靠它）
     └─ stdio_client(parameters)              L259
         └─ ClientSession.initialize()        L261
             ├─ list_tools() → catalog.json    L262  41 个 schema + schema_sha256
             ├─ call("minimal_sync", mcp_spawn_subagent, minimal, sync)          L294
             ├─ call("llm_generated_sync", mcp_spawn_subagent, llm_generated, sync) L298
             ├─ call("multi_turn_message", mcp_send_message_to_subagent)          L304  追加 "unused" 事实
             ├─ call("async_spawn", mcp_spawn_subagent, async)                   L308
             │   └─ for attempt in range(80):                                     L313
             │        call(f"async_status_{n}", mcp_get_subagent_status) → sleep(0.25)  L314
             │        直到 status ∈ {completed, failed}
             ├─ call("cancel_spawn", mcp_spawn_subagent, async)                  L320
             │   ├─ call("cancel_subagent", mcp_cancel_subagent)                 L324  ★ 先取消再查
             │   └─ call("cancelled_status", mcp_get_subagent_status)            L325
             ├─ approval_task = create_task(call("hitl_approval", mcp_request_admin_approval))  L341
             │   └─ sleep(0.5)                                                   L346  等请求进 pending 表
             ├─ call("hitl_pending", mcp_list_pending_requests) → request_id     L347
             ├─ 非交互: call("hitl_operator_response", mcp_respond_to_request, approved=True) L392
             │  交互:   print HITL_REQUEST= → read_human_decision_line(stdin) → parse → call("hitl_human_response") L388
             ├─ approval = await approval_task                                   L395  ★ 应答在服务端轮询窗口内到达
             ├─ write_json(human_decision.json)  ← 仅交互模式                     L397
             ├─ call("hitl_timeout", mcp_request_admin_approval, timeout_seconds=1) L405  ★ 探针刻意短于 2s 轮询
             ├─ call("email_notification_preflight", mcp_send_email)             L409
             ├─ call("im_notification_preflight", mcp_send_telegram_message)     L419
             └─ call("slack_notification_preflight", mcp_send_slack_message)     L421
     ├─ 合并 llm_receipts.checkpoint.json → llm_receipts.json                     L424
     ├─ gates = { 9 条门禁逐条判定 }                                              L433
     ├─ status = classify_status(gates, interactive_human=...)                    L463
     ├─ write_json(summary.json)                                                  L476
     ├─ files = [每个文件的 bytes + sha256] → write_json(manifest.json)            L477
     └─ write_json(VALIDATION/latest.json)                                        L481  ★ 最后写，半途崩溃不占"最新"位
```

两个"顺序即语义"的点：`cancel_subagent` 一定在 `cancelled_status` 之前（否则查到的还是 `running`）；`latest.json` 一定最后写。

---

## 2. 逐函数讲解（严格按源码顺序）

### 2.1 三条门禁常量与凭据正则（L23–L49）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="23"
HERE = Path(__file__).resolve().parent
SERVER = HERE / "src" / "main.py"
VALIDATION = HERE / "validation" / "experiment_4_5"
CREDENTIAL = re.compile(r"\b(?:sk|gh[opusr])-[A-Za-z0-9_-]{12,}\b")
SENSITIVE_ENV_NAMES = {
    "ANTHROPIC_API_KEY",
    ...
    "HITL_WEBHOOK_URL",
}
DELIVERY_GATES = {
    "real_email_notification",
    "real_im_notification",
    "real_slack_notification",
}
SYNTHETIC_PRIVACY_CANARY = "PRIVATE-MARKER-MUST-BE-FILTERED"
```

**固定提交链接**：[L23–L49](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L23-L49)

三行路径是这套实验的"重力中心"：`HERE` 被学习版重定向（第 2.36 节），`SERVER` 决定起哪个 MCP 入口（`sys.executable` + 绝对路径），`VALIDATION` 决定证据落哪。

`DELIVERY_GATES` 是三元素**集合**（不是 list），成员资格查询是 O(1)，且它是后面"投递门禁永远不豁免"这条规则的唯一数据来源——要加第四条渠道，只改这里一处。

`CREDENTIAL` 只匹配两类前缀：`sk-`（OpenAI/SendGrid 风格）和 `gh[opusr]-`（GitHub token 全系：`ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`）。`[A-Za-z0-9_-]{12,}` 要求后段至少 12 个字符，避免把 `sk-1` 这种误报。**它只是启发式**——DashScope 的 key 形如 `sk-...`，落在这个正则里；而 DeepSeek 的 key 也是 `sk-`。这就是 [学习脚本的注入 3：凭据自检](../assets/task4/run_4_5_collaboration.py) 存在的理由（第 2.36 节）。

`SYNTHETIC_PRIVACY_CANARY` 我单独用一小节讲（第 2.16 节），因为它是整页最聪明的一个设计决定。

---

### 2.2 `parse_human_decision`（L52–59）：真人决定的第一道解析

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="52"
def parse_human_decision(value: str) -> tuple[bool, str]:
    """Parse one explicit APPROVE/REJECT line from a live human operator."""
    match = re.fullmatch(r"\s*(APPROVE|REJECT)(?:\s*:\s*(.*))?\s*", value, re.I)
    if not match:
        raise ValueError("decision must be APPROVE or REJECT, optionally followed by ': notes'")
    approved = match.group(1).upper() == "APPROVE"
    notes = (match.group(2) or "").strip()
    return approved, notes or "No additional notes supplied by the live human operator."
```

**固定提交链接**：[L52–L59](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L52-L59)

四个决定：

- **`re.fullmatch` 而不是 `search`**：`search` 会让 `"maybe APPROVE"` 通过解析（在串里找到了 APPROVE）。全匹配要求整行**就是**一个决定，别的一律 `ValueError`。这是一个"宁可拒绝也不猜"的解析器。
- **`re.I`**：`approve` / `Approve` / `APPROVE` 都收。人手打字不该被大小写惩罚。
- **备注用 `(.*)` 贪婪匹配到行尾**：所以 `APPROVE: 卡号 6222...` 里的冒号后面的**所有内容**（含冒号）都进 notes，不会被 `split(":")` 切碎。
- **`notes or "No additional notes..."`**：没写备注时不留空字符串，而是给一句固定文案。理由在下游：`hitl_tools.respond_to_request` 对 `approved=False` 会把 `admin_notes` 存成 `rejection_reason`，空备注会被写成 `"No reason provided"`；给一句显式的"操作员没写备注"比空值诚实。

**实测（20260921T112238Z）**：本次运行是**非交互**模式，这个函数没被调用（`human_decision = None`）。它的行为来自我按源码逐行推演 + 下面动手验证里的手工调用。

---

### 2.3 `_readline_before_timeout`（L62–80）：为什么必须 `select` 逐字节读

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="62"
def _readline_before_timeout(stream: Any, timeout_seconds: float) -> str:
    """Read one byte stream line while ensuring the worker exits by its deadline."""
    descriptor = stream.fileno()
    encoding = getattr(stream, "encoding", None) or "utf-8"
    deadline = time.monotonic() + timeout_seconds
    data = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        readable, _, _ = select.select([descriptor], [], [], remaining)
        if not readable:
            raise TimeoutError
        chunk = os.read(descriptor, 1)
        if not chunk:
            return data.decode(encoding, errors="replace")
        data.extend(chunk)
        if chunk == b"\n":
            return data.decode(encoding, errors="replace")
```

**固定提交链接**：[L62–L80](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L62-L80)

这是全文件最短但最容易被略过的一个函数。它解决的是一个**会让整个进程挂死**的问题：

**朴素写法为什么不行**。交互模式要"等一行 stdin、超时就放弃"。最容易写的两种写法都坏：

1. `sys.stdin.readline()` 直接调 —— 没有超时。运维没应答，进程永远卡在等行。
2. `asyncio.to_thread(sys.stdin.readline)` 然后 `asyncio.wait_for(...)` —— `wait_for` 超时后**协程**返回了，但那个跑 `readline()` 的**线程**还卡在 `read()` 系统调用里。Python 的默认 executor 线程是**非 daemon** 的，而且它正持有一个内部的 `_threads_queues` 锁；`asyncio.run()` 收尾时要 `shutdown_default_executor()` → 等线程结束 → **等一个永不到来的行** → 整个进程在最后一步挂死。表面症状："超时逻辑明明触发了，程序就是不退出"。

**这个写法为什么行**。`select.select([fd], [], [], remaining)` 在**有数据可读或到点**时返回，然后把 `os.read(fd, 1)` 读**恰好一个字节**。关键在三处：

- **每次循环重算 `deadline`**（`time.monotonic()` 单调钟，不受系统时间调整影响），所以任何一次 `select` 都最多等到总 deadline，超时立刻 `raise TimeoutError`，线程**必然**在 deadline 内退出——没有"卡在 read 里"的窗口。
- **逐字节 + 遇 `\n` 返回**：等价于 `readline()` 但**不会**在"读到一半还没换行"时无限等下去。人手敲的 `APPROVE: 备注` 是短行，逐字节没有性能问题。
- **`if not chunk: return ...`** —— 读到 EOF（管道关闭、Ctrl-D）时返回**已读到的部分**（可能是空串）。空串由调用方 `run()` 判定为"输入在应答前关闭"并报错，不会把空串当合法决定。

`errors="replace"` 是防御性的：stdin 上万一出现非 UTF-8 字节，替换成 `�` 也不抛异常——因为这里已经够多失败路径了。

!!! info "推断（未单独实测）"
    上面"非 daemon 线程 + `shutdown_default_executor` 导致进程挂死"这条链路，我是按 CPython 的 executor 实现读出来的，本次没有专门造一个挂死实验去复现。可验证的**观测**是：本函数用 `select` 而不是 `readline`，且 `run()` 在超时路径上还显式 `approval_task.cancel()` + `gather(return_exceptions=True)`（L366–L370）——两处都在防"进程退不出去"。

---

### 2.4 `read_human_decision_line`（L83–94）：把超时翻译成有信息量的错误

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="83"
async def read_human_decision_line(stream: Any, timeout_seconds: float) -> str:
    """Read a live decision without leaving a permanently blocked stdin worker."""
    try:
        return await asyncio.to_thread(
            _readline_before_timeout,
            stream,
            timeout_seconds,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            f"live human decision input timed out after {timeout_seconds} seconds"
        ) from exc
```

**固定提交链接**：[L83–L94](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L83-L94)

14 行里有三个设计：

- **`asyncio.to_thread` 而不是直接同步调**：此刻 `run()` 里还有一个 `approval_task` 在跑（等服务端轮询）。直接同步读 stdin 会**阻塞整个事件循环**，那个 task 就永远没机会被推进——虽然服务端在**另一个进程**里轮询、不受影响，但本进程内的事件循环被堵住了，`approval_task` 的 I/O 也一起停了。`to_thread` 把阻塞读甩到线程池，事件循环继续转。
- **异常翻译 `TimeoutError → RuntimeError`**：`TimeoutError` 是 `OSError` 的子类，在 asyncio 语境里经常被当成"网络超时"处理。翻成 `RuntimeError` 并带上具体秒数，让 `main()` 的 `except Exception` 打出的错误行自解释。注意 `from exc` 保留了原始调用链。
- **docstring 直说了目的**："without leaving a permanently blocked stdin worker"——这行注释就是 2.3 节那段推理的官方版本。

---

### 2.5 `remaining_before_deadline`（L97–102）：一个 deadline，两个人分

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="97"
def remaining_before_deadline(deadline: float, *, now: float | None = None) -> float:
    """Return a positive remaining duration for a shared approval deadline."""
    remaining = deadline - (time.monotonic() if now is None else now)
    if remaining <= 0:
        raise RuntimeError("live human decision input timed out before presentation")
    return remaining
```

**固定提交链接**：[L97–L102](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L97-L102)

**"共享 deadline"是这个函数存在的全部理由**。看 `run()` 的 L337–L340：

```python
approval_deadline = (
    time.monotonic() + human_timeout_seconds
    if interactive_human else None
)
```

这个 deadline 在**创建 approval_task 之前**就算好了，然后被用在两处：

1. `mcp_request_admin_approval` 的 `timeout_seconds=human_timeout_seconds`——**服务端**最多等这么久；
2. `read_human_decision_line(sys.stdin, remaining_before_deadline(approval_deadline))`——**本地**最多等**剩余**的这么久。

如果本地用了 `human_timeout_seconds` 这个总量，那"服务端已经等了 3 分钟、本地又等 4 小时"，总窗口就是 4 小时 + 3 分钟，服务端会先超时返回，而本地还以为自己在等——最终 `approval["payload"]["timeout"] is True`，真人决定作废。用 `remaining_before_deadline` 保证**两个等待者共享同一个绝对时刻**，谁也不会比谁多等。

`now` 作为关键字参数注入是**为了可测**：单测想验证"已过期"，传一个 `now` 大于 `deadline` 即可，不用真睡。抛错文案 "timed out before presentation" 说明它只在**展示给操作员之前**调用（`run()` L365 把 `remaining_before_deadline(...)` 作为参数传进 `read_human_decision_line`，紧接着的 L355–L360 才是 `print("HITL_REQUEST=" + ...)`）——顺序是先算预算、再打印请求、再等输入。

---

### 2.6 `notification_readiness`（L105–118）：三条投递门禁各自缺什么

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="105"
def notification_readiness(env: dict[str, str]) -> dict[str, bool]:
    """Report whether all inputs for each real notification gate are present."""
    email_service = bool(
        env.get("SENDGRID_API_KEY") and env.get("SMTP_FROM_EMAIL")
    ) or bool(
        env.get("SMTP_USERNAME") and env.get("SMTP_PASSWORD")
    )
    return {
        "email": bool(email_service and env.get("HITL_ADMIN_EMAIL")),
        "telegram": bool(
            env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_DEFAULT_CHAT_ID")
        ),
        "slack": bool(env.get("SLACK_WEBHOOK_URL")),
    }
```

**固定提交链接**：[L105–L118](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L105-L118)

三渠道的门槛**互不相同**，这是这张表最值钱的地方：

| 渠道 | 需要的变量 | 组合逻辑 |
| --- | --- | --- |
| email | `HITL_ADMIN_EMAIL` **加上**（`SENDGRID_API_KEY` + `SMTP_FROM_EMAIL` **或** `SMTP_USERNAME` + `SMTP_PASSWORD`） | 两条发信路径**二选一** |
| telegram | `TELEGRAM_BOT_TOKEN` **且** `TELEGRAM_DEFAULT_CHAT_ID` | 缺 chat_id 就不能发 |
| slack | `SLACK_WEBHOOK_URL` | 一条就够（webhook 自带目标频道） |

email 那行的两段 `or` 对应 `notification_tools.send_email` 的两条实现路径：SendGrid HTTP API（key + from）或 SMTP（用户名 + 密码）。**`HITL_ADMIN_EMAIL` 是共同前置**——没有收件人，两条路径都没意义。

**实测（20260921T112238Z）**：`notification_readiness` = `{"email": false, "telegram": false, "slack": false}`。原因依次是：本机 `.env` 只配了 DeepSeek 与 DashScope，没有 SMTP/SendGrid；没有 Telegram bot token/chat id；没有 Slack webhook。于是 `run()` 走进 L243 的分支把 10 个通知相关变量**全部清空**（含 `HITL_ADMIN_EMAIL`），三条门禁保持 false——这就是最终 `status=blocked` 的来源。三条投递失败的具体报错来自服务器：`No email service configured` / `Telegram bot token not configured` / `Slack webhook URL not configured`。

---

### 2.7 `human_decision_accepted`（L121–132）：三条件的合取

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="121"
def human_decision_accepted(
    human_decision: dict[str, Any] | None,
    mcp_result: dict[str, Any],
) -> bool:
    """Return whether MCP accepted the live decision for the same request."""
    return bool(
        human_decision
        and mcp_result.get("success") is True
        and mcp_result.get("timeout") is not True
        and mcp_result.get("approved") is human_decision.get("approved")
        and mcp_result.get("request_id") == human_decision.get("request_id")
    )
```

**固定提交链接**：[L121–L132](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L121-L132)

任务书说的"同一个 request_id、非 timeout、决定一致"三条件，在这段里落成**四个**子判断（加一个"确实有决定"的前置）：

1. `human_decision` —— 非 None 非空。非交互模式下它是 `None`，整条短路成 False；
2. `mcp_result.get("success") is True` —— 服务端**受理**了；
3. `mcp_result.get("timeout") is not True` —— 服务端**没有**走超时兜底；
4. `mcp_result.get("approved") is human_decision.get("approved")` —— **两边决定一致**。真人说 APPROVE，服务端回 `approved=True`，才算数；
5. `mcp_result.get("request_id") == human_decision.get("request_id")` —— **同一个请求**。这一条防的是"操作员给 A 请求按了 APPROVE，但回执是 B 请求的"这类串号。

**两个"必须 `is` / `is not` 而不是真值判断"的细节**：`is True` 和 `is not True` 把 `None`、`1`、`"true"` 全部排除。服务端是 Python 写的、返回真 bool，所以这里安全；如果哪天服务端改成别的语言、`timeout` 返回 `"false"` 字符串，`is not True` 会让它**失败**（判成"超时"）而不是悄悄放行——失败方向是保守的，这是对的。

**实测（20260921T112238Z）**：`human_decision=None`（非交互），所以这条门禁 = `False`。`gates["real_human_decision"] = false`，进 `blockers` 列表。

---

### 2.8 `publication_is_authorized`（L135–143）：只有明确批准才授权发布

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="135"
def publication_is_authorized(
    human_decision: dict[str, Any] | None,
    mcp_result: dict[str, Any],
) -> bool:
    """Return whether an accepted live decision explicitly approved publication."""
    return bool(
        human_decision_accepted(human_decision, mcp_result)
        and human_decision.get("approved") is True
    )
```

**固定提交链接**：[L135–L143](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L135-L143)

与 `human_decision_accepted` 的差别只有一个词：**`approved is True`**。

- `human_decision_accepted` 回答"这次决定被有效受理了吗"——**REJECT 也算受理**（服务端 `success=True`、`approved=False`、request_id 一致 → accepted 为 True）。
- `publication_is_authorized` 回答"这次决定明确授权发布了吗"——**REJECT 不算**。

为什么分开？因为两件事的语义完全不同：一个 REJECT 是**合法的、有记录的、被受理的**人工决定（它该进 `human_decision.json` 留档，也该让 `real_human_decision` 门禁通过），但它**不授权**把这次运行结果写进对外 PR。把"受理"和"授权"混成一个函数，会导致"REJECT 也算发布许可"这种灾难性语义错误。

`run()` 把它写进 summary 的 `publication_authorized` 字段（L471）。**实测**：`false`（非交互 + 无决定）。

---

### 2.9 `classify_status`（L146–154）：谁可以被豁免

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="146"
def classify_status(gates: dict[str, bool], *, interactive_human: bool) -> str:
    """Classify a run while reserving ``blocked`` for unavailable external gates."""
    if all(gates.values()):
        return "passed"
    exempt_gates = set(DELIVERY_GATES)
    if not interactive_human:
        exempt_gates.add("real_human_decision")
    core_gates = (value for name, value in gates.items() if name not in exempt_gates)
    return "blocked" if all(core_gates) else "failed"
```

**固定提交链接**：[L146–L154](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L146-L154)

三分语义：

| status | 条件 | 含义 |
| --- | --- | --- |
| `passed` | 9 条全 True | 官方完整 |
| `blocked` | 除豁免项外**全 True** | **环境缺凭据**，不是代码问题 |
| `failed` | 有非豁免项 False | 能力坏了，要修 |

**豁免集合的两层构造是整段的核心**：

```text
exempt_gates = DELIVERY_GATES            # 三条投递门禁，任何模式下都豁免
if not interactive_human:
    exempt_gates.add("real_human_decision")   # 只有非交互时才多豁免这一条
```

- **投递门禁永远豁免**：因为"本机没有 SMTP 密码"和"子 Agent 生命周期跑不通"是两类事。前者是**环境事实**，代码无法自证，硬判 failed 等于让所有没配 Slack 的人都看到红灯。`DELIVERY_GATES` 是模块级常量，`classify_status` **只读**它，所以豁免名单不可能被某条门禁的判定逻辑意外改写。
- **`real_human_decision` 只在非交互时豁免**：这是**关键的非对称**。非交互模式下"真人决定"这条门禁物理上不可能为真（没人坐在终端前），把一次 CI 运行判成 failed 是错的，所以豁免它 → blocked。但一旦带上 `--interactive-human`，就是**明确宣称"这次会有真人按键"**——此时这条门禁**不再豁免**，答不上来（超时、空输入）就是 failed。**豁免是给"我没有宣称能拿到真人"的运行的，不是给"我宣称了但没拿到"的运行的。**

!!! note "同一份代码、两种模式的典型结果（推断 + 实测）"
    - 非交互：豁免 4 条 → core 5 条全过 → `blocked`。**实测（20260921T112238Z）**：`status=blocked`，`blockers` 是 `real_human_decision` + 三条投递门禁，与推理一致。
    - 交互模式且真人应答、但无投递凭据：豁免 3 条 → core 6 条全过 → 仍是 `blocked`；`publication_authorized` 变 `true`。这一格本次未跑（需要真人按键），是本页唯一没实测的 status 分支。

---

### 2.10 `redact_material`（L157–168）：递归脱敏

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="157"
def redact_material(value: Any, sensitive_values: tuple[str, ...]) -> Any:
    """Remove credentials and private delivery identifiers from retained evidence."""
    if isinstance(value, dict):
        return {key: redact_material(item, sensitive_values) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_material(item, sensitive_values) for item in value]
    if isinstance(value, str):
        redacted = value
        for sensitive in sensitive_values:
            redacted = redacted.replace(sensitive, "[REDACTED]")
        return redacted
    return value
```

**固定提交链接**：[L157–L168](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L157-L168)

三条规则：

- **只处理三种容器**：dict（逐值递归、**键不动**）、list（逐元素递归）、str（替换）。其他类型原样返回。
- **`redacted.replace(sensitive, "[REDACTED]")` 是子串替换，不是等值替换**。所以 `"to_email": "admin@x.com"` 这种**嵌在里面**的值也会被抹掉（因为 `admin@x.com` 本身是 `sensitive_values` 的一个成员）。代价是可能过度脱敏（某个 key 恰好包含某个 env 值的一段），但方向是安全的。
- **顺序敏感**：多个 sensitive 值**依次**替换。如果一个值是另一个值的子串，先替换长的更彻底——`sensitive_values` 由 `run()` 按 `SENSITIVE_ENV_NAMES` 的**集合迭代顺序**生成，没有按长度排序。**推断**：这是个小瑕疵，实践中不同 env 变量的值互相成子串的概率极低。

**为什么"凭据"和"私有投递标识"要一起脱敏**：`HITL_ADMIN_EMAIL` 是**管理员的真实邮箱**——不是密钥，但把它写进公开的 GitHub 证据文件是隐私泄露。所以 `SENSITIVE_ENV_NAMES` 里既有 `*_API_KEY` 也有 `SMTP_FROM_EMAIL` / `TELEGRAM_DEFAULT_CHAT_ID` / `HITL_ADMIN_EMAIL` / `HITL_WEBHOOK_URL`。**注意 `TELEGRAM_DEFAULT_CHAT_ID` 在名单里，所以只要它非空，聊天室 ID 就不会进证据**。而本次它是空的（非真实投递时被清空），无内容可脱敏。

`unwrap` 拿到的 payload 和 `call()` 记录的 arguments 都过这个函数（L278、L280）。

---

### 2.11 `retain_human_decision`（L171–180）：留档，但不改内存

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="171"
def retain_human_decision(
    human_decision: dict[str, Any],
    mcp_result: dict[str, Any],
    sensitive_values: tuple[str, ...],
) -> dict[str, Any]:
    """Build a redacted decision record without changing the in-memory decision."""
    return redact_material(
        {**human_decision, "mcp_result": mcp_result},
        sensitive_values,
    )
```

**固定提交链接**：[L171–L180](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L171-L180)

**`{**human_decision, "mcp_result": mcp_result}` 是浅拷贝新建 dict**，`redact_material` 又逐层建新 dict/list，所以：

- 原 `human_decision` **不被修改**——它还要在内存里参与 `human_decision_accepted` 判定（L456）和 `publication_is_authorized`（L471）。如果脱敏就地改了原对象的邮箱或备注，可能让判定结果漂移。
- **落盘的是脱敏副本**，`human_decision.json` 里永远不含凭据形状的串，也不含 `SENSITIVE_ENV_NAMES` 里那些非空值。

docstring 那句 "without changing the in-memory decision" 就是这个意思——**留档与判定分离**。这也是为什么 `run()` 只在**写出**的时候调用它（L399），判定用的是原始的 `human_decision`（L456/L471）。

---

### 2.12 `sha`（L183–184）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="183"
def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

**固定提交链接**：[L183–L184](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L183-L184)

两行，但它是**哈希链的基石**：`manifest.json` 里每个文件一行 `{path, bytes, sha256}`（L477–L478），`latest.json` 里再存 `manifest.json` 自己的 sha256（L484）。链是 `latest → manifest → 每个证据文件`。**没法自证的是 manifest 自己**——所以 `latest.json` 的 sha 与 学习脚本独立算的 `manifest_sha256` 互为交叉校验（第 3 节）。读文件用 `read_bytes()`，**不指定编码**——哈希的是字节，编码问题不该影响哈希值。

---

### 2.13 `write_json`（L187–192）：凭据形状的最后一道门

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="187"
def write_json(path: Path, value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
    if CREDENTIAL.search(text):
        raise ValueError(f"credential-shaped value in {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
```

**固定提交链接**：[L187–L192](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L187-L192)

**顺序就是全部**：先序列化 → **再扫凭据** → 再建目录 → 再写。

- `CREDENTIAL.search(text)` 扫的是**序列化后、写盘前**的完整文本。任何 `sk-` / `ghp-` 形状的串都会**当场抛 `ValueError`**，文件根本不落地。这是"宁可证据缺一个文件，也不落一个密钥"。
- 注意它**只扫形状**，不比对具体值——所以它拦得住"漏进了一个新 key"，但拦不住"漏进了一个不像 key 的隐私串"。后者靠 `redact_material` 的**按值精确匹配**兜。两道防线，各管一半：`redact_material` 管**已知**的敏感值，`CREDENTIAL` 管**未知但长得像凭据**的串。
- `default=str` 让不能序列化的对象（datetime、Path、异常）退化成字符串而不是抛 `TypeError`——证据落盘不应该因为一个自定义对象而整场崩掉。
- 抛错的时机在写之前，所以**不会留下半截文件**。对比：如果先 `write_text` 再扫，就得处理"删掉刚写的文件"。

**实测**：本次 35 个证据文件全部落盘、没有触发这条异常，且学习脚本的独立凭据扫描（第 2.36 节）`credential_scan_findings = []`——**两道防线各自独立确认没漏**。

---

### 2.14 `parse_value`（L195–206）：嵌套 JSON 字符串的还原

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="195"
def parse_value(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"result"}:
            return parse_value(value["result"])
        return value
    if isinstance(value, str):
        for parser in (json.loads, ast.literal_eval):
            try:
                return parse_value(parser(value))
            except Exception:
                pass
    return value
```

**固定提交链接**：[L195–L206](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034ce4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L195-L206)

MCP 工具返回的东西**层层套娃**，这个函数负责剥。三个机制：

1. **单键 `{"result": ...}` 解包**：`set(value) == {"result"}` 要求 dict **恰好只有 result 一个键**。FastMCP 常把工具返回值包成 `{"result": <真值>}`，这一层剥掉。如果同时还有别的键，就原样返回——**不猜**。
2. **两级解析器按序尝试**：`json.loads` 先试（双引号、规范 JSON），失败再试 `ast.literal_eval`（**能解析 Python 字面量：单引号、`True`/`None`**）。为什么必须两级？因为 `src/main.py` 里每个 `mcp_*` 工具都是 `return str(result)`（见第 2.35 节）——`str(dict)` 产出的是**单引号**形式 `{'success': True, ...}`，`json.loads` 直接失败，而 `ast.literal_eval` 正好能读。这就是两级解析器的存在理由。
3. **递归**：解析出来的**结果再进 `parse_value`**。所以 `"{\"result\": \"{\\\"status\\\": ...}\"}"` 这种多层嵌套会被一次性剥到最里层。第一层的 `{"result": ...}` 解包也走递归，同理。

`except Exception: pass` 吞掉所有解析异常（`JSONDecodeError`、`ValueError`、`SyntaxError`）——**这是对的**，因为"字符串不是 JSON"是正常情况（比如子 Agent 的自然语言回复），不该报错，直接当字符串用。

---

### 2.15 `unwrap`（L209–215）：MCP 结果的统一出口

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="209"
def unwrap(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if structured:
        return parse_value(structured)
    texts = [getattr(item, "text", None) for item in getattr(result, "content", [])]
    texts = [item for item in texts if item]
    return parse_value(texts[0]) if len(texts) == 1 else [parse_value(item) for item in texts]
```

**固定提交链接**：[L209–L215](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L209-L215)

**两条路径，优先级明确**：

1. **首选 `structuredContent`**：MCP 新规范里工具可以返回结构化的 `structuredContent`。这里用两次 `getattr` 同时兼容**驼峰**（Python 对象的 `structuredContent`）与**下划线**（dict 风格的 `structured_content`）——因为 MCP SDK 在不同版本/不同序列化路径下的属性名不一致。这是一个"我知道你会变"的防御。
2. **退回 `content` 文本块**：`content` 是个 list（每个元素有 `.text`），先把 `None` 过滤掉，然后：
   - **恰好 1 个文本块** → `parse_value(该文本)`，返回**值本身**（不是 list）。这是最常见的情况，也是为什么 `run()` 里到处写 `payload.get("success")` 而不是 `payload[0].get(...)`。
   - **0 个或多个** → 返回**列表**（每个元素各自 `parse_value`）。0 个时返回 `[]`，多块时返回多元素列表。

这个"1 个就解包、不是 1 个就列表"的设计**让调用方不得不防**：`run()` 里所有 `payload` 访问都写成 `x["payload"].get(...)`（dict 假设）。**推断**：如果某个工具返回 2 个文本块，`payload` 会变成 list，`.get` 会 `AttributeError` → 被 `call()` 的 `except Exception` 兜住，记成 `{"success": False, "error": "AttributeError: ..."}`，门禁判 False。**不会崩场，但会静默降级**——本次 41 个工具的实现都是单块返回，没触发。

---

### 2.16 `run()`（L218–485）：分五段读

这是 268 行的核心。按执行阶段切。

#### 段一：前置检查与 run_dir（L218–256）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="218"
async def run(
    campaign_id: str,
    *,
    interactive_human: bool = False,
    human_timeout_seconds: int = 14_400,
    real_notifications: bool = False,
) -> Path:
    if interactive_human and human_timeout_seconds <= 0:
        raise ValueError("human_timeout_seconds must be positive")
    env = os.environ.copy()
    readiness = notification_readiness(env)
    if real_notifications and not all(readiness.values()):
        missing = ", ".join(name for name, ready in readiness.items() if not ready)
        raise RuntimeError(f"real notification configuration is incomplete: {missing}")

    run_dir = VALIDATION / campaign_id
    run_dir.mkdir(parents=True, exist_ok=False)
```

**固定提交链接**：[L218–L256](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L218-L256)

- **要交互就必须给正超时**（`human_timeout_seconds <= 0` 直接 ValueError）：交互模式的整个安全模型建立在"最多等 N 秒"上，N=0 或不给会让"等真人"变成"等到天荒地老"。
- **`real_notifications` 是"承诺"而不是"开关"**：一旦为 True，三条投递门禁的凭据必须**现在**齐备，否则立刻 `RuntimeError` 并列出缺哪几个。这个设计把"我打算真发通知"变成**前置契约**，而不是跑到最后才发现发不出去。
- **`mkdir(exist_ok=False)`**：campaign_id 撞车**当场炸**。证据是不可覆盖的——要么用新时间戳，要么换 id。
- `env = os.environ.copy()` 之后所有注入都改这份**副本**，父进程环境不受影响。

#### 段二：env 注入 + 通知凭据清空 + 敏感值（L237–256）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="237"
    env.update({
        "COLLAB_PROVIDER": "moonshot", "OPENAI_MODEL": "kimi-k3",
        "COLLAB_LLM_RECEIPT_PATH": str(run_dir / "llm_receipts.checkpoint.json"),
        "HITL_TIMEOUT_SECONDS": "2", "BROWSER_HEADLESS": "true",
        "TIMER_STORAGE_PATH": str(run_dir / "timers.json"),
    })
    if not real_notifications:
        # Prevent placeholder values in the checked-in development .env from
        # being mistaken for configured notification credentials or causing
        # accidental delivery during the default credential-free campaign.
        env.update({
            "SENDGRID_API_KEY": "", "SMTP_USERNAME": "", "SMTP_PASSWORD": "",
            "SMTP_FROM_EMAIL": "", "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_DEFAULT_CHAT_ID": "", "SLACK_WEBHOOK_URL": "",
            "DISCORD_WEBHOOK_URL": "", "HITL_ADMIN_EMAIL": "",
            "HITL_WEBHOOK_URL": "",
        })
    sensitive_values = tuple(
        value for name in SENSITIVE_ENV_NAMES if (value := env.get(name))
    )
```

**固定提交链接**：[L237–L256](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L237-L256)

**注入的 6 个变量，每个都有明确用途**：

| 变量 | 值 | 谁读它 |
| --- | --- | --- |
| `COLLAB_PROVIDER` | `moonshot` | `llm_fallback.resolve_llm` 的 provider 分支 |
| `OPENAI_MODEL` | `kimi-k3` | 同上（provider 分支里的模型默认） |
| `COLLAB_LLM_RECEIPT_PATH` | `run_dir/llm_receipts.checkpoint.json` | `subagent_tools._record_call` 的落盘目标 |
| `HITL_TIMEOUT_SECONDS` | `2` | `config.HITLConfig.timeout_seconds` 的**默认值** |
| `BROWSER_HEADLESS` | `true` | `config.BrowserConfig.headless`（本实验不用浏览器，但保持一致） |
| `TIMER_STORAGE_PATH` | `run_dir/timers.json` | `timer_tools` 的定时器存储 |

**这里藏着一个反直觉点，下一节要展开**：`HITL_TIMEOUT_SECONDS=2` 只是**配置默认值**。`run()` 每次真正调用 `mcp_request_admin_approval` 时都**显式传了** `timeout_seconds`（8 / 1 / `human_timeout_seconds`），所以这个 2 **在本次运行的 HITL 调用里完全没被用到**。它的作用是当某个调用**不传** timeout 时的兜底。

**清空通知凭据那段是防"占位符事故"**：`.env` 里常放 `SMTP_PASSWORD=changeme` 这类占位值。如果不清，`notification_readiness` 会判 True（以为配好了）→ 跑到 `mcp_send_email` 真的连 SMTP → **卡在网络上或真的发出去**。清空保证了默认战役**物理上不可能**误投递。

**`sensitive_values` 在海象运算符里生成**（`(value := env.get(name))`）：只收**非空**值。空串不可能是敏感信息，但**逐值替换时空串会匹配每一个位置**——如果不滤，`redact_material` 会把所有字符串**每个字符之间**都插入 `[REDACTED]`，证据直接报废。这是个必须过滤的坑。

#### 段三：启动服务器 + 目录清单（L257–267）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="257"
    parameters = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env, cwd=str(HERE / "src"))
    receipts: list[dict[str, Any]] = []
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            listed = await session.list_tools()
            schemas = [tool.model_dump(by_alias=True, exclude_none=True, mode="json") for tool in listed.tools]
            write_json(run_dir / "catalog.json", {
                "transport": "mcp-stdio", "server_name": initialized.serverInfo.name,
                "server_version": initialized.serverInfo.version, "schemas": schemas,
                "schema_sha256": hashlib.sha256(json.dumps(schemas, sort_keys=True).encode()).hexdigest()})
```

**固定提交链接**：[L257–L267](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L257-L267)

- **`command=sys.executable`**：用**当前解释器**起服务器，不依赖 `python` 在 PATH 里。学习版用的是 `.venv-ch4v1` 的解释器，服务器也就跑在同一个 venv 里——**这是 mcp<2 能生效的关键**（系统的 `python3` 上是 mcp 2.2.0，`mcp.server.fastmcp` 已被删除，服务器根本起不来）。
- **`cwd=str(HERE / "src")`**：**这是全文件最容易被忽略、也最容易踩的一条**。服务器代码里全是**裸导入**（`from subagent_tools import ...`、`from config import config`），只有把 cwd 设成 `src/` 才能 import 到。而且 `config.py` 的 `load_dotenv()` 按 cwd 找 `.env`——cwd 不对，配置读不到。**学习版重定向 `HERE` 之后，这一行就成了地雷**（第 2.36 节详述）。
- **`schemas` 的 `model_dump(by_alias=True, exclude_none=True, mode="json")`**：把 SDK 的工具对象转成纯 JSON 可序列化的 dict。`by_alias=True` 让 `inputSchema` 这类字段用 MCP 协议的原始别名（而不是 Python 风格名）；`exclude_none=True` 去掉 None 字段——**两者一起保证 `schema_sha256` 在跨 SDK 版本时稳定**（否则 None 字段的增删会让哈希漂移）。`sort_keys=True` 同理。
- 这份 `catalog.json` 是**第 1 条门禁的证据**，也是"真 MCP 目录"的物证：不是读源码数装饰器，而是**真连上去问了一遍**。

#### 段四：`call()` 闭包与两种上下文策略（L269–L306）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="269"
            async def call(case: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
                started = time.perf_counter()
                try:
                    result = await session.call_tool(tool, arguments=arguments)
                    payload = unwrap(result)
                    is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
                except Exception as exc:
                    payload, is_error = {"success": False, "error": f"{type(exc).__name__}: {exc}"}, True
                row = {"case": case, "tool": tool,
                       "arguments": redact_material(arguments, sensitive_values),
                       "transport": "mcp-stdio", "mcp_result_is_error": is_error,
                       "payload": redact_material(payload, sensitive_values),
                       "latency_seconds": round(time.perf_counter() - started, 3)}
                receipts.append(row)
                write_json(run_dir / "receipts" / f"{len(receipts):02d}_{case}.json", row)
                return row
```

**固定提交链接**：[L269–L284](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L269-L284)

**"永不抛异常"的单次调用层，三个关键决定**：

- **异常被吞成本地 payload**：`session.call_tool` 抛的任何东西（连接断、协议错、超时）都变成 `{"success": False, "error": "TypeError: ..."}`，`is_error=True`。**门禁判定因此永远不会因为异常而跳过**——判 False 而不是崩场。这让"某一条门禁失败"与"整场崩了"彻底分开。
- **`isError` 双属性名兜底**：同一行里同时 `getattr(result, "isError", ...)` 和 `getattr(result, "is_error", ...)`，与 `unwrap` 里 `structuredContent` 的双名同理。
- **文件名带序号**：`f"{len(receipts):02d}_{case}.json"` → `01_minimal_sync.json`、`02_llm_generated_sync.json`……**序号即调用顺序**。所以 `ls receipts/` 就是一条时间线；`len(receipts)` 同时是"第几次调用"。这也是 `tool_call_count` 的来源。
- `latency_seconds` 用 `time.perf_counter()`（单调、高精度）测**整次调用**含 unwrap。注意它是**客户端看到的墙钟时间**，包含了 MCP 序列化与子进程调度开销——不是服务器内部耗时。

紧接着的两种策略调用在同一任务上跑，**只差一个参数**：

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="286"
            parent_context = {
                "customer": "Ada", "request": "Refund an item bought 3 days ago for SGD 80",
                "policy": "Refunds within 7 days and below SGD 100 may be approved",
                "irrelevant_history": ["weather chat", "shipping FAQ", "newsletter"],
                # This is a non-secret canary retained in the input receipt so
                # the filtered handoff can be checked independently.
                "private_note": SYNTHETIC_PRIVACY_CANARY,
            }
            minimal = await call("minimal_sync", "mcp_spawn_subagent", {
                "task": "Decide whether the refund meets the supplied policy and explain.",
                "context_strategy": "minimal", "mode": "sync", "parent_context": parent_context,
                "role": "refund policy specialist", "minimal_slice": ["policy"]})
            generated = await call("llm_generated_sync", "mcp_spawn_subagent", {
                "task": "Decide whether the refund meets the supplied policy and explain.",
                "context_strategy": "llm_generated", "mode": "sync", "parent_context": parent_context,
                "role": "refund policy specialist",
                "business_rules": "Keep customer, request, and policy. Exclude private_note and irrelevant history."})
```

**固定提交链接**：[L286–L302](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L286-L302)

**这就是 `SYNTHETIC_PRIVACY_CANARY` 的全部设计**——本页最值得学的一个手法：

`parent_context` 里有五样东西：真该传的（customer / request / policy）、**不该传的**（`irrelevant_history` 三条寒暄、`private_note` 哨兵）。哨兵值是字面量 `"PRIVATE-MARKER-MUST-BE-FILTERED"`——**内容本身不是隐私**（它是编的），但它的字符串**可被搜索**。

于是第 2 条门禁可以写：

```python
SYNTHETIC_PRIVACY_CANARY not in by_case["llm_generated_sync"].get("prepared_context", "")
```

**为什么用哨兵而不是用"真的隐私数据"**：

1. **可验证**——隐私过滤的效果本来很难证（"没泄露"是无法直接观察的）。塞一个**唯一的、可精确搜索的串**，"没泄露"就变成一次子串查询。
2. **零风险**——哨兵不是真凭据，即使过滤失败漏进证据文件也无损失。用真卡号做测试反而制造了真实泄露。
3. **留在输入收据里可独立复核**——注释说得很清楚："retained in the input receipt so the filtered handoff can be checked independently"。`receipts/02_llm_generated_sync.json` 的 **`arguments.parent_context.private_note` 里有哨兵**，而同一个 receipt 的 **`payload.prepared_context` 里没有**。**同一份证据文件内自证**：输入有、输出无 → 过滤生效。审阅者不需要信任何人，读一个 JSON 就够了。
4. **它是"必须被过滤"的断言，不是"看起来像隐私"的暗示**。字符串字面量就是需求文档。

**实测（20260921T112238Z）**：`minimal_sync` 与 `llm_generated_sync` 的 `prepared_context` **都不含哨兵**（`canary_leaked: false`），且 `llm_generated_sync` 的 `prep_tokens = 642 > 0`——第 2 条门禁的全部子条件成立。

两条调用的差异：

| 参数 | minimal | llm_generated |
| --- | --- | --- |
| `minimal_slice` | `["policy"]` | 不传 |
| `business_rules` | 不传 | "Keep customer, request, and policy. Exclude private_note and irrelevant history." |

**`minimal_slice=["policy"]` 让"手挑"变成一次按键名提取**，服务器那边 `{k: parent_context.get(k) for k in minimal_slice if k in parent_context}` 直接取出 `{"policy": "..."}`。而 `business_rules` 那句英文就是**给 LLM 的过滤指令**——注意它**点名了 `private_note`**，所以这同时也是"在被明确告知的情况下能否守住"的测试。

#### 段五：生命周期四连（L304–L325）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="304"
            await call("multi_turn_message", "mcp_send_message_to_subagent", {
                "subagent_id": minimal_id,
                "message": "Additional fact: the item is unused. Re-evaluate using only supplied facts."})

            asynchronous = await call("async_spawn", "mcp_spawn_subagent", {
                "task": "Return a JSON summary of the number 17 and whether it is prime.",
                "context_strategy": "minimal", "mode": "async", "role": "math specialist"})
            async_id = asynchronous["payload"].get("subagent_id")
            async_status = None
            for attempt in range(80):
                async_status = await call(f"async_status_{attempt + 1}", "mcp_get_subagent_status",
                                          {"subagent_id": async_id})
                if async_status["payload"].get("status") in {"completed", "failed"}:
                    break
                await asyncio.sleep(0.25)

            cancel_spawn = await call("cancel_spawn", "mcp_spawn_subagent", {
                "task": "Write a detailed taxonomy with one thousand entries.",
                "context_strategy": "minimal", "mode": "async", "role": "taxonomy specialist"})
            cancel_id = cancel_spawn["payload"].get("subagent_id")
            await call("cancel_subagent", "mcp_cancel_subagent", {"subagent_id": cancel_id})
            await call("cancelled_status", "mcp_get_subagent_status", {"subagent_id": cancel_id})
```

**固定提交链接**：[L304–L325](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L304-L325)

四件事，每件都在测一条不同的语义：

1. **`multi_turn_message` 用 `minimal_id`（同步子 Agent 的 id）**：同步子 Agent 已完成，往它身上**再发一条消息**应该能再跑一回合。这就是"多轮子 Agent"语义。消息内容刻意是**只给事实不给指令**（"the item is unused. Re-evaluate using **only supplied facts**"）——后半句是防提示注入的测试：追加信息不能变成"重写你的规则"。
2. **`async_spawn` + 轮询**：`mode="async"` 立刻返回 `running`，然后最多**80 次**、每次间隔 `0.25s`（上限 20 秒）查状态，直到 `completed` 或 `failed`。**上界存在的意义**：异步任务卡住时这场战役不会无限挂起——80 次后循环自然结束，`async_status` 保持最后的值（非 completed），第 4 条门禁判 False。**注意 `{"completed", "failed"}` 是终止集合，`cancelled` 不在里面**——这个循环等的是"异步任务自己跑完"，不等取消（取消由下面独立的用例测）。
3. **取消用例刻意用一个"跑不完的任务"**：`"Write a detailed taxonomy with one thousand entries."`——1000 条的分类体系，`max_tokens=800` 根本写不完。所以它**几乎必然还在 running**，此时取消才有意义。如果任务是"1+1=?"，任务可能在取消到达前就完成了，那就测不出取消语义。
4. **先 `cancel_subagent` 再 `cancelled_status`**：这个顺序**必须**如此。如果先查状态，看到的是 `running`；取消之后查，才会看到 `cancelled`。第 4 条门禁同时断言 `cancel_subagent.success is True` **且** `cancelled_status.status == "cancelled"`——**两条一起才证明"取消生效了"**，单看任一条都不够（取消返回成功但状态没变，是典型的假成功）。

**实测（20260921T112238Z）**：
- `multi_turn_message`：`success=True`，`latency 9.269s`，子 Agent 回复 `{"status": "need_info", ...}`——它认为信息不足（这正是我们想要的：给了新事实但它仍要求更多，没有臆造）。
- `async_spawn`：`status="running"`、`task_id` 非空。
- 轮询：**16 次**（`async_status_1` … `async_status_16`），第 16 次 `status="completed"`，`result` 是 `{"status": "done", "result": "The number 17 is a prime number.", ...}`。16 次 × 0.25s ≈ 4 秒，与 `subagent_turn` 的 latency 量级一致。
- `cancel_spawn`：`status="running"`；`cancel_subagent`：`previous_status="running"` → `status="cancelled"`；`cancelled_status`：`status="cancelled"`、`result=None`。**`result` 是 None 而不是半截字符串**，说明那个 `max_tokens=800` 的回合确实被掐断了。
- **26 次收据里，async 用例占了 17 条**（1 次 spawn + 16 次轮询）——这就是 `tool_call_count: 30` 的主要构成。

#### 段六：HITL 并发段（L327–L403）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="331"
            approval_message = "Approve publishing the Experiment 4-5 result?"
            approval_context = {
                "risk": "low",
                "artifact": "validation-only",
                "consequence": "An approval authorizes publishing this run in a GitHub pull request; a rejection keeps it local.",
            }
            approval_deadline = (
                time.monotonic() + human_timeout_seconds
                if interactive_human else None
            )
            approval_task = asyncio.create_task(call("hitl_approval", "mcp_request_admin_approval", {
                "request_message": approval_message,
                "context": approval_context,
                "timeout_seconds": human_timeout_seconds if interactive_human else 8,
                "urgent": False}))
            await asyncio.sleep(0.5)
            pending = await call("hitl_pending", "mcp_list_pending_requests", {})
            pending_rows = pending["payload"].get("requests", [])
            request_id = pending_rows[0].get("request_id") if pending_rows else None
```

**固定提交链接**：[L331–L349](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L331-L349)

**这段的结构是"并发三件套"，顺序不能变**：

```text
create_task(请求批准)  →  sleep(0.5)  →  list_pending_requests  →  应答  →  await approval_task
     ↑ 立刻返回              ↑ 让请求                   ↑ 读出 request_id      ↑ 不同模式，下面分叉   ↑ 最后才 await
```

- **为什么 `create_task` 而不是 `await`**：`mcp_request_admin_approval` 是个**会阻塞到超时或应答**的调用（服务端 `_wait_for_admin_response` 在轮询）。如果直接 `await`，runner 就卡在这里，**没办法扮演操作员去应答**——自己等自己，必然超时。必须让它跑在后台，runner 好腾出手来应答。
- **`sleep(0.5)` 是"让请求先落地"**：`create_task` 只把协程排进事件循环，真正发到服务器、服务器写入 `_pending_requests`、再返回，都需要时间。虽然这里 list 的是**服务器**的 pending 表，而 `call` 是串行 await 的（list 请求必然在 spawn 请求之后被处理），0.5 秒主要是保证**服务端已经把请求登记进表**。**实测**：`hitl_pending` 的 `latency 0.003s`、`count=1`——0.5 秒足够，且列表**非空**，所以 `request_id` 拿到了。
- **`pending_rows[0]`**：只取第一个。这个实验的设计里**同一时刻只有一个待批请求**（前一个 HITL 调用还没结束就不会有下一个）。选 `[0]` 简单且够用；若要更严谨会按 `created_at` 排序或校验 `message` 匹配。
- **`timeout_seconds` 的两套值**：交互模式 = `human_timeout_seconds`（默认 14400 = 4 小时）；非交互 = **`8`**。为什么非交互是 8 秒？因为非交互的"操作员"是**下一个 `call()`**——应答到达只需毫秒级，但服务端的**轮询粒度是 2 秒**（第 2.31 节），所以必须给足至少 2 个轮询周期，8 秒 = 4 个周期，很稳。**实测**：非交互下 `hitl_approval` 的 latency 正好 `2.003s`——一个轮询周期。
- **`approval_context` 里写明了后果**（"An approval authorizes publishing this run in a GitHub pull request"）——这是给**真人**看的决策依据，不是给程序的。HITL 的"人在回路"要有人能做判断的信息。

然后应答分两条路（L351–L394）：

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="351"
            if request_id:
                if interactive_human:
                    assert approval_deadline is not None
                    presented_at = datetime.now(timezone.utc).isoformat()
                    print("HITL_REQUEST=" + json.dumps({...}, ensure_ascii=False), flush=True)
                    try:
                        raw_decision = await read_human_decision_line(
                            sys.stdin,
                            remaining_before_deadline(approval_deadline),
                        )
                    except RuntimeError:
                        if not approval_task.done():
                            approval_task.cancel()
                        await asyncio.gather(approval_task, return_exceptions=True)
                        raise
                    ...
                    await call("hitl_human_response", "mcp_respond_to_request", {
                        "request_id": request_id, "approved": approved,
                        "admin_notes": notes})
                else:
                    await call("hitl_operator_response", "mcp_respond_to_request", {
                        "request_id": request_id, "approved": True,
                        "admin_notes": "Approved by the automated validation operator; not a claimed human judgment."})
```

**固定提交链接**：[L351–L394](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L351-L394)

**非交互分支的关键在备注文案**：`"Approved by the automated validation operator; **not a claimed human judgment**."` —— 自动化操作员批准了，但备注**明说这不是人类判断**。这个字符串是谁都能读到的**自我否认**：它让 `hitl_approval` 这条门禁（"待批 → 应答"）可以过，但**不能**让 `real_human_decision` 门禁过，因为那条门禁看的是 `human_decision`（本地变量），非交互时它就是 `None`。**两种"批准"在数据上被彻底分开**，一个字符串备注和一扇关闭的门禁共同保证：CI 跑不出"有真人批准"的记录。

**交互分支的异常处理值得单独看**：

```python
except RuntimeError:
    if not approval_task.done():
        approval_task.cancel()
    await asyncio.gather(approval_task, return_exceptions=True)
    raise
```

读输入超时（`read_human_decision_line` 抛 `RuntimeError`）时，**先把后台的 `approval_task` 取消掉、并等它真正结束**，然后**再抛**。为什么必须 `gather(..., return_exceptions=True)`：`cancel()` 只是**请求**取消，协程还要一个事件循环的调度才真正退出；如果不 await 就 `raise`，这个 task 会变成"未被取回结果的待决任务"。而 `return_exceptions=True` 保证**取消引发的 `CancelledError` 不会被当成新异常抛出**——我们本来就是要抛超时那个错，不想被取消的副作用盖掉。**这三行的写法是"退出前把自己的后台工作收干净"的标准姿势。**

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="395"
            approval = await approval_task
            if human_decision is not None:
                write_json(
                    run_dir / "human_decision.json",
                    retain_human_decision(
                        human_decision,
                        approval["payload"],
                        sensitive_values,
                    ),
                )
            timeout = await call("hitl_timeout", "mcp_request_admin_approval", {
                "request_message": "No operator will answer this timeout probe.",
                "context": {"probe": True}, "timeout_seconds": 1, "urgent": False})
```

**固定提交链接**：[L395–L407](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L395-L407)

- **`approval = await approval_task` 放在应答之后**。这个顺序是**唯一的正确解**：应答的 `call()` 已经 await 完成了（服务器那边状态变成 approved），此时再 await 那个后台任务，服务端的轮询循环在下一次 tick 就会看到 approved 并返回。如果反过来（先 await 再应答）→ **死锁**：runner 在等服务器，服务器在等一个永远不来的应答。
- **`human_decision.json` 只在 `human_decision is not None` 时写**。非交互模式下这个文件**不存在**——这是"没拿到真人决定"的**物理物证**。审阅者 `ls run_dir` 就知道这次是不是真人模式，不用读任何字段。
- **超时探针的 `timeout_seconds=1`**：这是**刻意的、必然超时**的探针，理由完全依赖第 2.31 节的轮询粒度——服务端 `_wait_for_admin_response` 每 **2 秒**才检查一次状态，而这里的窗口只有 **1 秒**：

  ```text
  t=0.0  进循环，第一次检查 status == "pending"
  t=0.0  await asyncio.sleep(2)          ← 要睡到 t=2.0
  t=1.0  while 条件 1.0 < 1 为假 → 退出循环 → 标记 timeout
  ```
  第一次检查之后直接睡 2 秒，而 2 秒后循环条件已经过期——**根本不存在第二次检查的机会**。所以只要传 `timeout_seconds=1`（小于 2 秒的轮询间隔），超时是**由构造保证的**，不依赖任何时序运气。这就是"保守超时"的可复现测法：**探针必须比轮询粒度短**，否则测的就不是"超时"而是"恰好赶上"。同时它验证了超时返回的语义：`approved=False`（**保守默认是不批准**，不是默认批准）。

  **实测（20260921T112238Z）**：`hitl_timeout` 的 `timeout=True`、`approved=False`、`latency 2.003s`。2 秒是因为它睡完了那一次 `sleep(2)` 才退出循环——与推演完全一致。

#### 段七：三渠道投递预检（L409–L422）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="409"
            email = await call("email_notification_preflight", "mcp_send_email", {
                "to_email": env.get("HITL_ADMIN_EMAIL") if real_notifications else "nobody@example.invalid",
                "subject": "Experiment 4-5",
                "body": "Real Experiment 4-5 notification" if real_notifications else "Credential preflight only"})
            telegram_arguments = {
                "message": "Real Experiment 4-5 notification" if real_notifications else "Experiment 4-5 credential preflight",
                "parse_mode": "HTML",
            }
            if not real_notifications:
                telegram_arguments["chat_id"] = "0"
            telegram = await call("im_notification_preflight", "mcp_send_telegram_message",
                                  telegram_arguments)
            slack = await call("slack_notification_preflight", "mcp_send_slack_message", {
                "message": "Real Experiment 4-5 notification" if real_notifications else "Experiment 4-5 credential preflight"})
```

**固定提交链接**：[L409–L422](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L409-L422)

**三条预检都在"仍然真调一次工具"**，只是参数指向一个**不可能送达的目标**：

| 渠道 | 非真实投递时的参数 | 为什么不可能送达 |
| --- | --- | --- |
| email | `to_email="nobody@example.invalid"` | `.invalid` 是 RFC 2606 保留的**永不解析**顶级域 |
| telegram | `chat_id="0"` | 不是合法 chat |
| slack | 无地址参数（webhook 自带） | 环境变量已被清空 → 工具自己报"未配置" |

**这套设计的好处**：三条门禁的判定逻辑用的是**同一个** `payload.get("success") is True`（L459–461）——真实投递和预检走**完全相同的代码路径**。区别只在参数。所以"换成真凭据后能不能过"是**可外推**的：跑通的就是同一段逻辑，不是另一段模拟。`.invalid` 与 `chat_id="0"` 保证**即使有人误把占位凭据填上，也送不出去**。

**实测（20260921T112238Z）**：
- `email_notification_preflight` → `success=False`，`error="No email service configured"`（服务器在缺凭据时不尝试发送）
- `im_notification_preflight` → `success=False`，`error="Telegram bot token not configured"`
- `slack_notification_preflight` → `success=False`，`error="Slack webhook URL not configured"`

三者都**没有抛异常**——服务器把"未配置"做成了**正常的失败返回值**，这正是门禁能判 False（而不是崩场）的前提。三条 `latency` 都是 `0.002s`，确认**没有发生任何网络尝试**。

#### 段八：门禁判定（L424–L462）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="427"
    by_case = {row["case"]: row["payload"] for row in receipts}
    required_tools = {"mcp_spawn_subagent", "mcp_send_message_to_subagent",
                      "mcp_cancel_subagent", "mcp_get_subagent_status",
                      "mcp_request_admin_approval", "mcp_request_admin_input",
                      "mcp_send_email", "mcp_send_telegram_message", "mcp_send_slack_message"}
    tool_names = {schema["name"] for schema in schemas}
    gates = {
        "real_mcp_catalog_has_required_primitives": required_tools <= tool_names,
        "two_real_context_strategies_compared": (
            by_case["minimal_sync"].get("success") is True
            and by_case["llm_generated_sync"].get("success") is True
            and by_case["minimal_sync"].get("context_strategy") == "minimal"
            and by_case["llm_generated_sync"].get("context_strategy") == "llm_generated"
            and by_case["llm_generated_sync"].get("prep_tokens", 0) > 0
            and SYNTHETIC_PRIVACY_CANARY not in
                by_case["llm_generated_sync"].get("prepared_context", "")),
        "raw_model_usage_latency_receipts": bool(llm_receipts) and all(
            row.get("response", {}).get("id") and row.get("usage", {}).get("total_tokens") is not None
            and row.get("latency_seconds") is not None for row in llm_receipts),
        "sync_async_message_cancel_status_lifecycle": (
            by_case["multi_turn_message"].get("success") is True
            and async_status is not None and async_status["payload"].get("status") == "completed"
            and by_case["cancel_subagent"].get("success") is True
            and by_case["cancelled_status"].get("status") == "cancelled"),
        "hitl_pending_response_and_conservative_timeout": (
            bool(request_id) and approval["payload"].get("success") is True
            and approval["payload"].get("timeout") is not True
            and timeout["payload"].get("timeout") is True
            and timeout["payload"].get("approved") is False),
        "real_human_decision": human_decision_accepted(
            human_decision, approval["payload"]
        ),
        "real_email_notification": email["payload"].get("success") is True,
        "real_im_notification": telegram["payload"].get("success") is True,
        "real_slack_notification": slack["payload"].get("success") is True,
    }
```

**固定提交链接**：[L427–L462](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L427-L462)

**`by_case` 是按 case 名重排收据**——门禁判定不去索引 `receipts[3]` 这种位置，而是按**语义名**取（`by_case["minimal_sync"]`）。这让"加一条调用"不会让所有门禁错位。

九条门禁各自的**判定本质**：

| # | 门禁 | 判定什么 | 本次 |
| --- | --- | --- | --- |
| 1 | `real_mcp_catalog_has_required_primitives` | **9 个**协作原语是 `list_tools()` 实际返回的**子集**（`<=`） | ✅ |
| 2 | `two_real_context_strategies_compared` | 两条都成功 + strategy 名各自对 + `prep_tokens > 0` + **哨兵没漏** | ✅ |
| 3 | `raw_model_usage_latency_receipts` | 每条模型回执都有 `response.id`、`usage.total_tokens`、`latency_seconds` | ✅ |
| 4 | `sync_async_message_cancel_status_lifecycle` | 消息成功 + 异步跑到 completed + 取消失败 **+ 取消后状态是 cancelled** | ✅ |
| 5 | `hitl_pending_response_and_conservative_timeout` | pending 非空 + 批准成功非超时 + 探针**是**超时 + 探针**不**批准 | ✅ |
| 6 | `real_human_decision` | `human_decision_accepted(...)` | ❌ 非交互 |
| 7–9 | 三条投递 | `payload.success is True` | ❌ 无凭据 |

三个值得注意的**判定技法**：

- **门禁 1 用 `<=` 而不是 `==`**：要求**至少**含这 9 个，多出来的工具（浏览器/象棋/Excel 那 32 个）不影响。实验协议只关心协作原语在不在。
- **门禁 2 的"策略名"是双查**：不仅要求各自 `success`，还要求返回的 `context_strategy` **字符串等于请求的那个**。防的是"服务器把两种策略都当 minimal 处理、但都返回成功"——那样两个调用都会成功，只有名字对不上。**这是"两条路真的走了两条路"的证明**（配合 `prep_tokens`：minimal 必须是 0，llm_generated 必须 > 0，两者不同才算真的不同）。
- **门禁 3 要求 `response.id` 非空**：`id` 是模型服务商为每次调用生成的**请求标识**，只在**真调用**时存在。离线/模拟路径**拿不到 id**，所以这条门禁**物理上无法伪造**。这是"原始使用量凭证"的核心——`usage.total_tokens` 和 `latency_seconds` 都可以编，`response.id` 编不出来。
- **门禁 5 把"超时"要求成 `is True`**：注意这条门禁要求探针**必须超时**。它不是"能超时就行"，而是"**超时必须表现为 timeout=True 且 approved=False**"。即"保守默认"是被**断言**的行为，不是观察到的现象。

**实测（20260921T112238Z）**：5 条 ✅、4 条 ❌，与上表一致。`tool_call_count=30`（含 16 次轮询）、`model_call_count=5`。

#### 段九：summary / manifest / latest（L463–485）

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="463"
    status = classify_status(gates, interactive_human=interactive_human)
    summary = {"experiment": "4-5", "campaign_id": campaign_id,
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "status": status, "official_complete": status == "passed", "gates": gates,
               "blockers": [name for name, value in gates.items() if not value],
               "tool_call_count": len(receipts), "model_call_count": len(llm_receipts),
               "interactive_human": interactive_human,
               "human_timeout_seconds": human_timeout_seconds if interactive_human else None,
               "publication_authorized": publication_is_authorized(
                   human_decision, approval["payload"]
               ),
               "real_notifications_enabled": real_notifications,
               "notification_readiness": readiness}
    write_json(run_dir / "summary.json", summary)
    files = [{"path": str(path.relative_to(run_dir)), "bytes": path.stat().st_size, "sha256": sha(path)}
             for path in sorted(run_dir.rglob("*")) if path.is_file() and path.name != "manifest.json"]
    write_json(run_dir / "manifest.json", {"experiment": "4-5", "campaign_id": campaign_id,
               "status": status, "official_complete": status == "passed", "files": files})
    write_json(VALIDATION / "latest.json", {"experiment": "4-5", "campaign_id": campaign_id,
               "status": status, "official_complete": status == "passed",
               "manifest": str((run_dir / "manifest.json").relative_to(HERE)),
               "manifest_sha256": sha(run_dir / "manifest.json")})
    return run_dir
```

**固定提交链接**：[L463–L485](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L463-L485)

- **`blockers` 就是 `gates` 里为 False 的名字列表**——不需要单独维护"哪里失败了"的账本，门禁表本身就是账本。
- **`official_complete` 严格等于 `status == "passed"`**：`blocked` **不算**官方完整。这条很关键——`blocked` 是"环境缺凭据"的**如实记录**，不是通过。
- **`notification_readiness` 被原样写进 summary**：不只记"门禁没过"，还记"**哪些变量缺失**"（三个 false）。复盘时能区分"没配"和"配了但发失败"。
- **`files` 的生成有个精确的排除条件**：`path.name != "manifest.json"`——manifest 不能把自己列进去（否则自指哈希不可能算）。`rglob("*")` 递归收 `receipts/` 子目录，`sorted()` 保证顺序稳定。**`manifest.json` 是在 `files` 算完之后才写的**，所以它列的是"除自己之外的全部文件"。
- **`latest.json` 最后写**（L481）：这是**写入顺序即语义**——如果这次运行在写 manifest 之前崩了，`latest.json` 还指向上一次成功的运行，**"最新"这个位置永远指向一个完整的结果**。半途而废的运行留在 `runs/` 里可查，但不占据 `latest`。学习脚本运行目录下只有两份 `latest` 相关文件（`../latest.json` 与 `experiment_protocol.json`），说明学习版把这个 `VALIDATION` 也重定向到了自己的输出根（第 2.36 节）。
- **`human_timeout_seconds` 在非交互时写 `None`**：不写那个没用上的默认值 14400，避免让人误以为"这次等了 4 小时"。

---

### 2.17 `main`（L488–511）：退出码的三分

```python title="chapter4/collaboration-tools/run_experiment_4_5.py" linenums="488"
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", default=datetime.now(timezone.utc).strftime("real_mcp_%Y%m%dT%H%M%SZ"))
    parser.add_argument(
        "--interactive-human", action="store_true",
        help="wait for a live APPROVE/REJECT line on stdin and retain it as the human decision",
    )
    parser.add_argument(
        "--human-timeout-seconds", type=int, default=14_400,
        help="maximum live-response window for --interactive-human (default: 14400)",
    )
    parser.add_argument(
        "--real-notifications", action="store_true",
        help="use configured email, Telegram, and Slack delivery instead of credential-free preflights",
    )
    args = parser.parse_args()
    path = asyncio.run(run(
        args.campaign_id,
        interactive_human=args.interactive_human,
        human_timeout_seconds=args.human_timeout_seconds,
        real_notifications=args.real_notifications,
    ))
    print(path)
    return 0 if json.loads((path / "summary.json").read_text(encoding="utf-8"))["status"] in {"passed", "blocked"} else 1
```

**固定提交链接**：[L488–L511](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/run_experiment_4_5.py#L488-L511)

- **默认 `campaign_id` 是 UTC 时间戳**（`real_mcp_20260921T112238Z` 形状）——**默认就不可能撞车**，与 `mkdir(exist_ok=False)` 配套。学习版另用了自己的时间戳（`20260921T112238Z`）。
- **四个参数全部映射到一个布尔或整数**：三个布尔开关（`--interactive-human` / `--real-notifications`）+ 一个超时。**没有 `--model` 之类的参数**——provider 是**写死在 `run()` 里**注入的（L238），这正是学习版必须打补丁的原因（第 2.36 节）。
- **退出码三分**：`passed` 或 **`blocked`** → `0`；其他（`failed` 或抛异常）→ `1`。**"环境缺凭据"返回成功码**。这是刻意的：CI 里"这台机器没配 Slack"不该让构建变红。但**判定依据是从 `summary.json` 重新读的**，不是内存里的 `status` 变量——**读回自己刚写的文件**，等于**再验证一次"证据确实落地了"**。如果 `write_json` 静默失败，这里会 `FileNotFoundError` 而不是假装成功。
- `print(path)` 把运行目录打到 stdout，便于脚本捕获（学习版自己打印 `DONE <run_dir>`）。

---

### 2.18 `src/subagent_tools.py`：两种上下文策略的实现差异

服务器侧的入口是 `spawn_subagent`（L361），但**真正决定"两种策略长什么样"的是 `_prepare_minimal_context` 与 `_prepare_llm_generated_context`**。

#### 策略一 `_prepare_minimal_context`（L173–208）

```python title="chapter4/collaboration-tools/src/subagent_tools.py" linenums="173"
def _prepare_minimal_context(
    task: str,
    parent_context: Optional[Union[str, Dict[str, Any]]],
    minimal_slice: Optional[Union[str, Dict[str, Any], List[str]]],
) -> Dict[str, Any]:
    """最小化传递: only the task, plus an optional hand-picked slice.
    ...
    """
    picked = ""
    if minimal_slice is not None:
        if isinstance(minimal_slice, list) and isinstance(parent_context, dict):
            picked = json.dumps(
                {k: parent_context.get(k) for k in minimal_slice if k in parent_context},
                ensure_ascii=False,
            )
        elif isinstance(minimal_slice, (dict, list)):
            picked = json.dumps(minimal_slice, ensure_ascii=False)
        else:
            picked = str(minimal_slice)

    parts = [f"[FROM_MAIN_AGENT] 子任务：{task}"]
    if picked:
        parts.append(f"[FROM_MAIN_AGENT] 手动挑选的必要信息：{picked}")
    context_text = "\n".join(parts)
    return {
        "strategy": "minimal",
        "context_text": context_text,
        "context_tokens": _count_tokens(context_text),
        "prep_tokens": 0,  # no extra LLM call
        "notes": "只传任务参数与手动挑选的最小切片，不转发主 Agent 完整轨迹",
    }
```

**固定提交链接**：[L173–L208](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/subagent_tools.py#L173-L208)

**这个函数里没有一次 `client.chat.completions.create`**——`prep_tokens` 硬编码为 `0` 并附注释 `# no extra LLM call`。**这就是"最小化"的全部成本特征：零额外调用、零额外 token、零延迟**。

`minimal_slice` 的三种形态分支（`minimal_slice` 的 docstring 也列了）：

| 类型 | 行为 |
| --- | --- |
| **list + parent_context 是 dict** | 按键名提取——`{k: parent_context.get(k) for k in slice if k in parent_context}`。**`if k in parent_context` 是关键**：不存在的键被静默跳过，不会塞 `None` 进来 |
| dict 或 list（parent_context 不是 dict） | 整个 `json.dumps` 出去（当作直接给定的切片） |
| 其他（字符串） | `str(...)` 原样附加 |

**"零额外调用"的代价也在这里**：`minimal` 完全不做隐私过滤——它**只是不传**。所以如果 `minimal_slice=["policy", "card_number"]`，卡号照传。**minimal 的隐私安全性来自"主 Agent 手挑时没挑敏感字段"，不是来自任何自动机制**。这与 `llm_generated` 形成对照：那边是**主动让 LLM 按规则丢弃**。

**实测（20260921T112238Z）**：`minimal_sync` 的 `prepared_context` 只有两行（任务 + `{"policy": "Refunds within 7 days and below SGD 100 may be approved"}`），`context_tokens=56`、`prep_tokens=0`。**"手动挑选的必要信息"里只有 policy 一个键**——`irrelevant_history` 和 `private_note` 压根没被挑，所以哨兵不可能出现（`canary_leaked: false`）。

#### 策略二 `_prepare_llm_generated_context`（L211–280）

```python title="chapter4/collaboration-tools/src/subagent_tools.py" linenums="211"
def _prepare_llm_generated_context(
    task: str,
    parent_context: Optional[Union[str, Dict[str, Any]]],
    business_rules: Optional[str],
) -> Dict[str, Any]:
    """LLM 生成上下文: one extra LLM call summarizes/selects relevant context.
    ...
    """
    full_context = _normalize_parent_context(parent_context)
    rules = business_rules or (
        "1) 不要传递支付卡号、密码、令牌等敏感隐私信息；"
        "2) 只保留与子任务直接相关的事实，压缩无关寒暄；"
        "3) 保留关键约束、用户身份要点与相关工具结果。"
    )
    if _offline():
        ...
    client = _get_client()
    prompt = f"""你是主协调 Agent 的上下文准备助手。请阅读主 Agent 的完整轨迹，
按照业务规则，为下面的子任务生成一份**精炼、结构化**的移交上下文，供子 Agent 使用。

业务规则：
{rules}

子任务：{task}

主 Agent 完整轨迹：
{full_context}

只输出移交上下文正文本身（不要解释、不要 JSON、不要包含被规则排除的隐私字段）。"""
```

**固定提交链接**：[L211–L262](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/subagent_tools.py#L211-L262)

```python title="chapter4/collaboration-tools/src/subagent_tools.py" linenums="264"
    started = time.perf_counter()
    response = client.chat.completions.create(**request)
    _record_call("llm_generated_context", request, response, time.perf_counter() - started)
    generated = (response.choices[0].message.content or "").strip()
    prep_tokens = response.usage.total_tokens if response.usage else 0

    context_text = (
        f"[FROM_MAIN_AGENT] 子任务：{task}\n"
        f"[FROM_MAIN_AGENT] 由 LLM 依据业务规则生成的移交上下文：\n{generated}"
    )
    return {
        "strategy": "llm_generated",
        "context_text": context_text,
        "context_tokens": _count_tokens(context_text),
        "prep_tokens": prep_tokens,  # cost of the extra summarization call
        "notes": "额外调用一次 LLM，依据业务规则从主 Agent 轨迹中生成隐私安全、压缩后的上下文",
    }
```

**固定提交链接**：[L264–L280](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/subagent_tools.py#L264-L280)

**与 minimal 逐项对照**：

| 维度 | minimal | llm_generated |
| --- | --- | --- |
| LLM 调用次数 | 0 | **1**（在子 Agent 那一次之前） |
| `prep_tokens` | 硬编码 `0` | `response.usage.total_tokens`（**实测 642**） |
| 输入 | task + 手挑切片 | task + **完整 parent_context** + business_rules |
| 隐私保障 | 靠主 Agent"没挑" | **靠 LLM 按规则丢弃**（+ 默认规则兜底） |
| 输出形状 | 机械拼接 | LLM 自由组织（结构化、压缩） |
| 额外延迟 | 0 | **实测 5.246s**（一次完整 LLM 调用） |
| 记账 | 无 | 走 `_record_call("llm_generated_context", ...)` → 进 llm_receipts |

**四个关键设计**：

- **`rules = business_rules or (默认三条规则)`**：调用方不给规则时，**默认规则本身就是隐私优先的**（"不要传递支付卡号、密码、令牌"）。所以"忘了传规则"不会退化成"不过滤"。
- **`full_context = _normalize_parent_context(parent_context)`**：dict 会被 `json.dumps(indent=2)` 展开成结构清晰的多行文本再进 prompt。这一步让 LLM 能看见**键名**（`private_note`、`irrelevant_history`），才可能按规则丢弃。
- **prompt 的最后一句是"负向指令"**："只输出移交上下文正文本身（**不要解释、不要 JSON、不要包含被规则排除的隐私字段**）"。三个"不要"对应三个失败模式——解释了额外 token 白花、JSON 包一层还得剥、以及隐私直接泄漏。**但指令不是保证**，所以门禁用哨兵来**实测**它有没有守住。
- **`prep_tokens` 的记账位置**：取的是**提炼调用**的 `usage.total_tokens`（**实测 642**），不是子 Agent 那一次的。所以 `prep_tokens > 0` 这个条件能**区分**两条路：minimal 恒为 0，llm_generated 若真调 LLM 必 > 0。**这就是"两条策略真的不同"的算术证据**——不是看名字，是看账单。
- **离线分支显式否认**（L227–240）：`_offline()` 时改走 `_offline_summarize_context`（规则式剔除含 `_SENSITIVE_MARKERS` 的行 + 截断 800 字），返回 `prep_tokens: 0` 且 `notes` 明写"**未调用 LLM**"。**它不冒充模型输出**——这与整章的诚实纪律一致。

**实测（20260921T112238Z）**：`llm_generated_sync` 的 `prep_tokens=642`、`context_tokens=82`（比 minimal 的 56 大但很紧凑）、`latency 13.072s`（约 = 提炼 5.2s + 子 Agent 6s + 开销）。**`prepared_context` 里只有 Customer / Request / Policy 三条**——`irrelevant_history` 和 `private_note` 都被丢掉了，哨兵当然不在。

#### `spawn_subagent`（L361–471）：sync 与 async 的分岔

```python title="chapter4/collaboration-tools/src/subagent_tools.py" linenums="387"
    try:
        if mode not in ("sync", "async"):
            return {"success": False, "error": f"未知 mode: {mode!r}，应为 'sync' 或 'async'"}

        prepared = _prepare_context(
            task, context_strategy, parent_context, minimal_slice, business_rules
        )

        subagent_id = str(uuid.uuid4())
        system_prompt = _build_system_prompt(role, task)
        record: Dict[str, Any] = {
            "subagent_id": subagent_id,
            ...
            "status": "running",
            "prepared_context": prepared["context_text"],
            "context_tokens": prepared["context_tokens"],
            "prep_tokens": prepared["prep_tokens"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prepared["context_text"]},
            ],
            "result": None,
            "run_total_tokens": 0,
        }
        _subagents[subagent_id] = record
```

**固定提交链接**：[L387–L416](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/subagent_tools.py#L387-L416)

```python title="chapter4/collaboration-tools/src/subagent_tools.py" linenums="418"
        if mode == "sync":
            turn = await asyncio.to_thread(_run_turn, record)
            record["status"] = "completed"
            record["result"] = turn["reply"]
            return {
                "success": True,
                "subagent_id": subagent_id,
                "mode": "sync",
                "status": "completed",
                "context_strategy": context_strategy,
                "context_tokens": prepared["context_tokens"],
                "prep_tokens": prepared["prep_tokens"],
                "prompt_tokens": turn["prompt_tokens"],
                "prepared_context": prepared["context_text"],
                "context_notes": prepared["notes"],
                "result": turn["reply"],
            }

        # async: start background task, return immediately with a task_id.
        task_id = str(uuid.uuid4())
        record["task_id"] = task_id

        async def _runner() -> None:
            try:
                turn = await asyncio.to_thread(_run_turn, record)
                if record["status"] != "cancelled":
                    record["status"] = "completed"
                    record["result"] = turn["reply"]
            except asyncio.CancelledError:
                record["status"] = "cancelled"
                raise
            except Exception as exc:  # noqa: BLE001
                record["status"] = "failed"
                record["result"] = f"error: {exc}"
                logger.error("Async sub-agent %s failed: %s", subagent_id, exc)

        _async_tasks[subagent_id] = asyncio.create_task(_runner())
        return {
            "success": True,
            "subagent_id": subagent_id,
            "task_id": task_id,
            "mode": "async",
            "status": "running",
            ...
            "message": "子 Agent 已在后台启动，完成后可用 get_subagent_status 查询结果",
        }
```

**固定提交链接**：[L418–L467](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/subagent_tools.py#L418-L467)

**sync / async 的三处实质差异**：

| 维度 | sync | async |
| --- | --- | --- |
| 返回时机 | 等 LLM 回合跑完 | **立刻**（`status="running"`） |
| 返回值 | `status="completed"` + `result` + `prompt_tokens` | `status="running"` + **`task_id`** + `message` |
| 后台登记 | 无 | `_async_tasks[subagent_id] = asyncio.create_task(_runner())` |
| 谁设终态 | `spawn_subagent` 自己（L420–421） | **`_runner` 闭包** |

**`task_id` 与 `subagent_id` 是两个不同的 UUID**：`subagent_id` 是**记录**的键（`_subagents`），`task_id` 是**这次后台执行**的标识。一个子 Agent 理论上可以对应多次执行（消息追加后再跑），所以两者分开。**注意 `_async_tasks` 的键是 `subagent_id` 而不是 `task_id`**——取消是按子 Agent 取消的（`cancel_subagent` 只收 `subagent_id`）。

**`_runner` 里那个 `if record["status"] != "cancelled"` 是竞态修复**：

```text
线程池里 _run_turn 还在跑
        ↓
cancel_subagent 到达 → record["status"] = "cancelled" + task.cancel()
        ↓
_run_turn 正常返回（没被打断，因为它在另一个线程里）
        ↓
回到 _runner：如果没有这个判断 → 状态被改成 "completed"，取消白做了
```

`asyncio.Task.cancel()` **只能取消 await 点**，打不断正在 `asyncio.to_thread` 里执行的**线程**。所以"取消"和"线程自然完成"可能**同时发生**，`if` 判断保证**取消优先**——先设的状态不被覆盖。**这一行是 async 取消语义的正确性关键。**

**`asyncio.CancelledError` 的分支**：`task.cancel()` 真正生效时（`to_thread` 的 await 还没进去或已结束），`CancelledError` 被捕获 → 设 `cancelled` → **`raise` 重新抛出**。为什么不吞掉？因为 `CancelledError` 在 asyncio 里是**控制流信号**，吞掉它会破坏调用方的取消传播（`asyncio.gather` 等的语义）。设完状态就重新抛，是对的。

**`except Exception` 那个 `# noqa: BLE001`**：裸 `except Exception` 通常被 linter 禁止，这里显式豁免——因为**后台任务的异常没有别的出口**，必须转成 `status="failed"` + `result="error: ..."` 存进记录，否则异常会静默消失（没人 await 这个 task）。

**`_run_turn`（L338–358）为什么走 `asyncio.to_thread`**：`client.chat.completions.create` 是**同步阻塞**的 OpenAI SDK 调用。MCP 服务器是单事件循环的；直接在协程里调它会**堵住整个服务器**（其他工具的调用全部排队）。`to_thread` 把它甩到线程池。**代价是取消打不断线程**——上面那个 `if` 判断就是在补偿这个代价。

#### `cancel_subagent`（L506–526）与状态查询（L529–544）

```python title="chapter4/collaboration-tools/src/subagent_tools.py" linenums="509"
        record = _subagents.get(subagent_id)
        if record is None:
            return {"success": False, "error": f"子 Agent 不存在: {subagent_id}"}

        prev_status = record["status"]
        record["status"] = "cancelled"
        task = _async_tasks.get(subagent_id)
        if task is not None and not task.done():
            task.cancel()
        return {
            "success": True,
            "subagent_id": subagent_id,
            "previous_status": prev_status,
            "status": "cancelled",
        }
```

**固定提交链接**：[L509–L523](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/subagent_tools.py#L509-L523)

**先置状态、再 cancel task，顺序不能换**：

1. `record["status"] = "cancelled"` **先写** → 保证无论 `_runner` 在哪个时刻醒来，它看到的都是 `cancelled`，那个 `if` 判断就会生效；
2. `task.cancel()` **后调** → 只对**还在跑**的 async 任务有意义。

**`not task.done()` 的判断**：如果任务已经结束，`cancel()` 是空操作（返回 False），不报错。但显式判断更清楚，也避免对已完成任务触发无谓的取消路径。**返回值带 `previous_status`** —— 调用方能知道"取消之前它是 running 还是 completed"。**实测**：`previous_status="running"`（那个 1000 条 taxonomy 任务确实还在跑）。

**注意取消是"幂等 + 无条件成功"**：对**已完成**的子 Agent 调 `cancel_subagent` 也会返回 `success=True`、`previous_status="completed"`、`status="cancelled"`——**状态会被逆着改回去**。**推断**：这是一个可疑点（把已完成的子 Agent 标记成 cancelled，语义上有点怪），但本次运行的取消用例打的是 running 的任务，没有实测这个边界。

**状态查询（L529–544）** 是个纯读函数，返回 8 个字段（`status` / `mode` / `context_strategy` / `context_tokens` / `prep_tokens` / `result` / `created_at`）。注意它**把 `context_tokens` 和 `prep_tokens` 也暴露出来**——这两个数在 async 路径上是**唯一**的上下文成本证据（因为 async 不返回 result 之外的收据），查询接口必须带上。**实测**：`cancelled_status` 的 `status="cancelled"`、`result=None`、`prep_tokens=0`、`context_strategy="minimal"`。

---

### 2.19 `src/hitl_tools.py`：pending → approved/rejected/timeout 状态机

状态机只有四个状态，**三个是终态**：

```text
              ┌──────────────┐
   create ───►│   pending    │
              └──┬─────┬───┬─┘
     respond_to_request(True)  │     │   │  respond_to_request(False)
                 │     │   │
                 ▼     │   ▼
           ┌─────────┐│ ┌──────────┐
           │ approved││ │ rejected │
           └─────────┘│ └──────────┘
                      │  _wait_for_admin_response 超时
                      ▼
                 ┌─────────┐
                 │ timeout │
                 └─────────┘
```

**只有 `pending` 可转移**；`approved` / `rejected` / `timeout` 是终态，**任何来自它们的"转移"都被拒绝**。

#### 状态转移的唯一入口（L234–248）

```python title="chapter4/collaboration-tools/src/hitl_tools.py" linenums="234"
        request = _pending_requests[request_id]
        if request.get("status") != "pending":
            current_status = request.get("status", "unknown")
            return {
                "success": False,
                "approved": False,
                "request_id": request_id,
                "current_status": current_status,
                "error": "Request is no longer pending",
                "message": (
                    f"Request {request_id} is already {current_status}; "
                    "late or duplicate responses cannot change a terminal decision"
                ),
            }
        request["status"] = "approved" if approved else "rejected"
```

**固定提交链接**：[L234–L248](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/hitl_tools.py#L234-L248)

**`if request.get("status") != "pending"` 这一道守卫，是课程从一次真实失败中补的修复。** 这个结论不是我从代码推的——**代码自己说了**：错误文案里写着 "late or duplicate responses cannot change a terminal decision"（迟到或重复的应答不能改变终态决定）。这种**把设计意图直接写进运行时错误信息**的做法，是"补了一个 bug、并且要防止它再犯"的典型痕迹：修复者知道未来会有人（或某个 agent）在超时后重试一次应答，所以让**错误消息本身就是文档**。

**它防的三种具体场景**：

1. **重复应答**：操作员手抖点了两次批准，或者网络重试导致 `respond_to_request` 被投递两次。没有守卫 → 第二次会覆盖第一次（把"批准"改成"拒绝"）。
2. **迟到应答**：`_wait_for_admin_response` 已经超时返回 `timeout=True`、调用方已经按"保守默认 = 不批准"继续走了，这时操作员才点进来。没有守卫 → 状态从 `timeout` 变成 `approved`，**而那个决定永远送不到任何地方**（等待方早就返回了），却留在表里冒充"已批准"。
3. **超时后的追认**：最坏的一种——审计时看到 `approved`，以为批准是在有效期内发生的。

**返回值的设计也有信息量**：`success: False`（明确失败，不是静默忽略）+ `current_status`（**告诉调用方现在是什么终态**）+ 完全没变的 `request`。调用方因此能区分"这人来晚了"（`current_status="timeout"`）和"这请求根本不存在"（`success: False` + `error: "Request not found"`，L228–232）。

**实测（20260921T112238Z）**：本次运行的 HITL 序列里**没有**触发这条守卫（`hitl_operator_response` 一次性成功）。我在[动手验证](#3-动手验证)里手工构造了重复应答，拿到了完整的拒绝消息——见第 4 节第 2 条。

#### 2 秒轮询与保守超时（L151–199）

```python title="chapter4/collaboration-tools/src/hitl_tools.py" linenums="153"
        start_time = datetime.now()
        timeout = timedelta(seconds=timeout_seconds)

        while datetime.now() - start_time < timeout:
            request = _pending_requests.get(request_id)

            if not request:
                return {"success": False, "approved": False, "error": "Request not found", ...}

            if request["status"] == "approved":
                return {"success": True, "approved": True, "request_id": request_id,
                        "admin_notes": request.get("admin_notes"),
                        "message": "Request approved by administrator"}

            elif request["status"] == "rejected":
                return {"success": True, "approved": False, "request_id": request_id,
                        "admin_notes": request.get("admin_notes"),
                        "reason": request.get("rejection_reason", "No reason provided"),
                        "message": "Request rejected by administrator"}

            # Wait a bit before checking again
            await asyncio.sleep(2)

        # Timeout reached
        _pending_requests[request_id]["status"] = "timeout"

        return {
            "success": True,
            "approved": False,
            "request_id": request_id,
            "timeout": True,
            "message": f"Admin response timeout after {timeout_seconds} seconds"
        }
```

**固定提交链接**：[L153–L199](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/hitl_tools.py#L153-L199)

**四个要点**：

1. **轮询间隔固定 2 秒**（`await asyncio.sleep(2)` 是唯一的等待）。所以**响应延迟的下界是 0（第一次检查就命中）到 2 秒**。**实测**：`hitl_approval` 与 `hitl_timeout` 的 latency 都是 `2.003s`——都是"睡完一轮才返回"。
2. **超时返回 `success=True`**（不是 False）。超时**不是错误**，是**一种明确的结果**：`timeout=True` + `approved=False`。这个区分很重要——`success=False` 意味着"调用失败、结果未知"，而超时是"**结果已知：没有批准**"。门禁判定也正是这么写的（`timeout["payload"].get("timeout") is True and ... .get("approved") is False`）。
3. **保守默认是"不批准"**（`approved: False`）。注意这不是 `pub` 层的默认，而是**这里的硬编码**——超时路径**没有**任何"默认批准"的选项。对比 `notification_dispatcher.py` 里的 `FallbackAction.AUTO_APPROVE / AUTO_REJECT / ESCALATE`（L15–21）：**那个模块有可配置的超时兜底策略，这个模块没有**。本实验走的 HITL 工具是"超时即不批准"这一种。**推断**：这是课程有意选的保守实现；`notification_dispatcher` 是更完整的策略层，但 `run_experiment_4_5.py` 没走它。
4. **默认超时 3600 秒来自 `config`**：`timeout = timeout_seconds or config.hitl.timeout_seconds`（L61），而 `config.HITLConfig.timeout_seconds` 默认 `3600`（`src/config.py` L57），可被 `HITL_TIMEOUT_SECONDS` 覆盖——`run()` 注入的是 `2`。**但本次运行 4 次 HITL 调用全都显式传了 `timeout_seconds`**（8 / 1 / `human_timeout_seconds`），所以 `3600` 和注入的 `2` **都没被用到**。这条"配置默认值 + 显式参数覆盖"的链路很容易看错，值得单独记一笔。

!!! warning "一个可复现的边界竞态（实测）"
    超时分支里的 `_pending_requests[request_id]["status"] = "timeout"` 是**无条件**执行的——它不看当前状态。于是存在一个窗口：应答在**最后一轮检查之后、while 条件失效之前**到达，`respond_to_request` 会成功把状态设成 `approved`，紧接着这个分支**又把它改写成 `timeout`**。

    **这不是我臆测的**：我用 `timeout_seconds=2`（恰好等于轮询间隔）+ 1 秒后自动应答做了一次——

    ```text
    respond_to_request 返回 {"success": true, "approved": true}   ← 应答被成功受理
    最终 request_admin_approval 返回 {"timeout": true, "approved": false}  ← 被改写
    ```

    两次都发生了。根因是 `while datetime.now() - start_time < timeout` 用的是**严格小于**：`timeout_seconds=2` 时，第一轮检查在 t≈0 看到 `pending`，然后睡到 t=2.0，此时 `2.0 < 2` 为假 → 直接退出循环 → 标记 timeout。**整个窗口里只有一次检查机会。**

    **对实验的影响**：`run_experiment_4_5.py` 因此**永久避开了这个窗口**——它的超时探针传 `1`（必然超时，不指望被应答），它的应答用例传 `8`（4 个轮询周期，足够宽）。**推断**：这个竞态在"时间正好卡在轮询边界"时才会显形，课程的两组参数都刻意远离边界。手工验证时若想看到"批准成功"，`timeout` 必须 **> 2 秒**。

---

### 2.20 `src/llm_fallback.py`：provider 解析（含 dashscope 分支）

```python title="chapter4/collaboration-tools/src/llm_fallback.py" linenums="44"
def has_llm() -> bool:
    """True when at least one usable LLM credential is configured."""
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
                or os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")
                or os.getenv("DASHSCOPE_API_KEY"))


def resolve_llm(default_model: str = "gpt-5.6-luna") -> Tuple[str, Optional[str], str]:
    """Resolve (api_key, base_url, model), applying the OpenRouter fallback.
    ...
    """
    model = os.getenv("OPENAI_MODEL", default_model)

    provider = os.getenv("COLLAB_PROVIDER", "").lower()
    if provider in {"dashscope", "qwen", "bailian"}:
        dashscope_key = os.getenv("DASHSCOPE_API_KEY")
        if not dashscope_key:
            raise RuntimeError("COLLAB_PROVIDER=dashscope requires DASHSCOPE_API_KEY")
        return (
            dashscope_key,
            os.getenv(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            os.getenv("OPENAI_MODEL", "qwen3.7-plus"),
        )
    if provider == "moonshot":
        moonshot_key = os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")
        if not moonshot_key:
            raise RuntimeError("COLLAB_PROVIDER=moonshot requires MOONSHOT_API_KEY or KIMI_API_KEY")
        return moonshot_key, "https://api.moonshot.cn/v1", os.getenv("OPENAI_MODEL", "kimi-k3")
```

**固定提交链接**：[L44–L75](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/llm_fallback.py#L44-L75)

**`resolve_llm` 的解析优先级（自上而下，先命中先返回）**：

| 序 | 条件 | api_key | base_url | model |
| --- | --- | --- | --- | --- |
| 1 | `COLLAB_PROVIDER ∈ {dashscope, qwen, bailian}` | `DASHSCOPE_API_KEY` | `DASHSCOPE_BASE_URL`（默认阿里云兼容模式） | `OPENAI_MODEL`（默认 `qwen3.7-plus`） |
| 2 | `COLLAB_PROVIDER == moonshot` | `MOONSHOT_API_KEY` 或 `KIMI_API_KEY` | `https://api.moonshot.cn/v1`（**写死**） | `OPENAI_MODEL`（默认 `kimi-k3`） |
| 3 | 有 `OPENROUTER_API_KEY` **且** model 以 `gpt-5` 开头 | OpenRouter key | `https://openrouter.ai/api/v1` | 映射后的 `provider/model` |
| 4 | 有 `OPENAI_API_KEY` | OpenAI key | `OPENAI_BASE_URL`（可空） | `model` |
| 5 | 有 `OPENROUTER_API_KEY`（其他模型） | OpenRouter key | 同上 | 映射后 |
| 6 | 都没有 | — | — | **抛 RuntimeError** |

**dashscope 分支就是学习版能"零代码改动换模型"的全部原因**：它**排在 moonshot 之前**，所以只要把 `COLLAB_PROVIDER` 设成 `dashscope`，课程 `run()` 注入的 `COLLAB_PROVIDER=moonshot` 就被覆盖，解析走进这条路。注意它**用 `OSError not set` 就显式抛错**（`if not dashscope_key: raise`）——配置不一致时**立刻大声失败**，不静默退回别的 provider。moonshot 分支同样。

**`base_url` 的三个来源各不相同**：dashscope 是**环境变量可覆盖 + 阿里云默认**；moonshot 是**写死**；OpenAI 是 `OPENAI_BASE_URL`（可空 → SDK 用官方地址）。这个差异是历史遗留——moonshot 分支是后加的。

**`map_model_for_openrouter`（L26–41）的映射规则**（第 3、5 条用到）：

```text
含 "/"        → 原样返回（已经是 provider/model 形式）
gpt- /o1- /o3- /o4-  → "openai/" + model
claude-       → "anthropic/claude-opus-4.8"
kimi          → "moonshotai/kimi-k2.6"
其他          → 原样返回
```

**`claude-*` 被映射到一个固定的完整模型名**（`claude-opus-4.8`）而不是 `anthropic/<原名>`——**推断**：这是为了把"实验里用的任何 claude 别名"统一到一个具体的 OpenRouter 模型 id（OpenRouter 上的 id 与 Anthropic 官方名不一定同名）。

**`has_llm`（L44–48）与 `_offline` 的关系**：`subagent_tools._offline()` 就是 `not has_llm()`。五把钥匙只要有**任意一把**，`_offline()` 就是 False，子 Agent 走真 LLM 路径。**注意 `DASHSCOPE_API_KEY` 在名单里**——这是学习版能跑真模型的前提。

**实测（20260921T112238Z）**：学习版注入 `COLLAB_PROVIDER=dashscope` / `OPENAI_MODEL=qwen3.7-plus` / `DASHSCOPE_BASE_URL=阿里云兼容模式`，5 条模型回执的 `response.model` 全是 `qwen3.7-plus`，`purpose` 分别是 `subagent_turn` ×4 与 `llm_generated_context` ×1——**说明 dashscope 分支被走到，且两种用途共用同一个 provider**。回执里 `provider` 字段是 `null`：`subagent_tools._record_call` **不记 provider**（只记 request/response/usage/latency/`called_at`），provider 信息只能从 `response.model` 反推。

---

### 2.21 `src/main.py`：注册骨架（41 个工具怎么挂上去）

```python title="chapter4/collaboration-tools/src/main.py" linenums="92"
mcp = FastMCP("collaboration-tools")
```

**固定提交链接**：[L92](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/main.py#L92)

每个工具都是**同一种薄包装**：

```python title="chapter4/collaboration-tools/src/main.py" linenums="489"
@mcp.tool(description="Spawn a sub-agent to handle a delegated task. Supports sync (waits and returns result) and async (returns a task_id immediately) modes, and two context-passing strategies: 'minimal' or 'llm_generated'.")
async def mcp_spawn_subagent(
    task: str = Field(description="The sub-task to delegate to the sub-agent"),
    context_strategy: str = Field(default="minimal", description="Context-passing strategy: 'minimal' (task + hand-picked slice only) or 'llm_generated' (extra LLM call synthesizes privacy-filtered context)"),
    mode: str = Field(default="sync", description="'sync' waits and returns the result; 'async' starts in background and returns a task_id"),
    parent_context: Optional[Dict[str, Any]] = Field(default=None, description="Parent agent trajectory/state to prepare per the chosen strategy"),
    role: Optional[str] = Field(default=None, description="Optional explicit role for the sub-agent's system prompt"),
    minimal_slice: Optional[Any] = Field(default=None, description="For 'minimal' strategy: hand-picked slice (string, dict, or list of keys into parent_context)"),
    business_rules: Optional[str] = Field(default=None, description="For 'llm_generated' strategy: privacy/compression rules")
) -> str:
    """Spawn a sub-agent (sync or async) with a chosen context-passing strategy."""
    result = await spawn_subagent(
        task, context_strategy, mode, parent_context, role, minimal_slice, business_rules
    )
    return str(result)
```

**固定提交链接**：[L489–L503](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/main.py#L489-L503)

三个统一约定，每个都影响 runner：

1. **参数描述用 `Field(description=...)`**——这是 MCP 的 **schema 来源**。runner `list_tools()` 拿到的 `inputSchema` 里，每个参数的 description 就从这里来。**所以"给 agent 的说明书"和"给人看的文档"是同一份文本**（L264 落的 `catalog.json` 就是为了留证：这条路径真的产出了 41 份 schema）。
2. **每个工具都 `return str(result)`**——把 dict 转成 Python `str`（单引号）。**这正是 `parse_value` 需要 `ast.literal_eval` 兜底的原因**（第 2.14 节）。如果这里改成 `json.dumps`，runner 就只需要 `json.loads` 了。这是一个"两端各自合理、合起来别扭"的接口——理解它能省掉一次困惑。
3. **工具名统一 `mcp_` 前缀**，与 `src/` 里的实现函数名同名去前缀（`mcp_spawn_subagent` ↔ `spawn_subagent`）。runner 的 `required_tools` 集合和门禁 1 都用这个前缀名。

**`_serve()`（L538–551）** 与实验无关但与"服务器能不能正常起"有关：

```python title="chapter4/collaboration-tools/src/main.py" linenums="538"
async def _serve() -> None:
    """Restore saved timers and serve requests on the SAME event loop.

    `asyncio.run(_load_timers())` used to run in a throwaway loop: closing it
    cancelled every `_run_timer` task that had just been restored, and the
    CancelledError handler then marked those timers "cancelled" and re-saved,
    which drops them from storage. Restored timers therefore never fired and
    were lost from memory *and* disk.

    `FastMCP.run(transport="stdio")` is itself just `anyio.run(run_stdio_async)`,
    so awaiting `run_stdio_async()` here is the same server entry point.
    """
    await _load_timers()
    await mcp.run_stdio_async()
```

**固定提交链接**：[L538–L551](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/collaboration-tools/src/main.py#L538-L551)

一样是"从真实 bug 里学到的"注释：`asyncio.run(_load_timers())` 会**建一个临时事件循环再关掉**，关掉时把刚恢复的定时器任务全取消 → 那些任务的 `CancelledError` 处理把它们标成 `cancelled` 并**写回存储** → **恢复的定时器既不在内存也不在磁盘**。修法是"同一个事件循环里先加载再服务"。**本实验不从磁盘加载定时器**（`TIMER_STORAGE_PATH` 指向 run_dir 下的空文件），但这段代码每次启动都会跑——**这是"启动了但看不到任何效果"的一段**，不知道的话会以为它在做实验相关的事。

---

### 2.22 学习版注入了什么（三处改写）

```python title="learning/task4/run_4_5_collaboration.py" linenums="52"
# --- 注入 1：输出目录重定向（协议文件需在同一目录下）-----------------------------
course.HERE = OUT_ROOT
course.VALIDATION = OUT_ROOT
OUT_ROOT.mkdir(parents=True, exist_ok=True)
shutil.copy2(COURSE_DIR / "experiment_protocol.json", OUT_ROOT / "experiment_protocol.json")

# --- 注入 2：把课程硬编码的 moonshot/kimi-k3 换成 DashScope ---------------------
# 课程用 HERE / "src" 作为子进程 cwd；HERE 被重定向后必须显式指回课程源码目录。
_real_params = course.StdioServerParameters


def _provider_params(**kwargs):
    env = dict(kwargs.get("env") or {})
    env["COLLAB_PROVIDER"] = PROVIDER["name"]
    env["OPENAI_MODEL"] = PROVIDER["model"]
    env["DASHSCOPE_BASE_URL"] = PROVIDER["endpoint"]
    env["DASHSCOPE_API_KEY"] = os.environ["DASHSCOPE_API_KEY"]
    kwargs["env"] = env
    kwargs["cwd"] = str(COURSE_DIR / "src")
    return _real_params(**kwargs)


course.StdioServerParameters = _provider_params
```

**固定提交链接**（学习脚本在笔记仓库，不在课程仓库）：[run_4_5_collaboration.py · L52–L74](../assets/task4/run_4_5_collaboration.py)

**三处改写的动机逐个说**：

**注入 1：重定向 `HERE` 与 `VALIDATION`，且必须复制协议文件。** 课程 `run()` L235–236 读的是 `HERE / "experiment_protocol.json"`——`HERE` 是**模块级常量**（L23），它**只在 import 时算一次**。学习版把 `course.HERE` 改成自己的输出根之后，同一个表达式会去找 `OUT_ROOT/experiment_protocol.json`——**课程目录下根本没有这个文件**。所以 `shutil.copy2` 把协议文件**先复制过去**，`run()` 才能读到。**这是"改常量"和"改常量指向的目录内容"是两件事**——只改常量不做复制，会在 `run()` 的第 6 行崩掉。

`VALIDATION` 同样被重定向（L233 的 `run_dir = VALIDATION / campaign_id`，L481 的 `latest.json`）。所以**课程的 `validation/` 目录完全不被触碰**，学习版的所有证据都在 `learning/task4/runs/4-5_collaboration/` 下。**实测**：运行目录的兄弟层有 `experiment_protocol.json` 与 `latest.json` 两个文件——正是 `HERE=OUT_ROOT` 与 `VALIDATION=OUT_ROOT` 的产物。

**注入 2：替换 `StdioServerParameters` 这个类名本身。** 为什么必须**改写类**而不是改环境变量？因为 provider 是**写死的**：

```python
# 课程 run() L237–238
env.update({
    "COLLAB_PROVIDER": "moonshot", "OPENAI_MODEL": "kimi-k3",
    ...
```

`env.update` 在 `os.environ.copy()` 的基础上**硬编码覆盖**，从外部设 `COLLAB_PROVIDER=dashscope` **会被这里再覆盖回 moonshot**。这是**代码里写死的决策**，外部环境变量改不动它。唯一的入口是**在构造 `StdioServerParameters` 的那一刻**改（课程 L257）。学习版的做法是：把模块级的 `StdioServerParameters` 名字**换成自己的工厂函数**，于是课程 L257 的 `StdioServerParameters(command=..., args=..., env=env, cwd=...)` 实际调到 `_provider_params`：

```text
课程 L237: env 里放了 COLLAB_PROVIDER=moonshot / OPENAI_MODEL=kimi-k3
            ↓
课程 L257: StdioServerParameters(command, args, env, cwd=HERE/"src")
            ↓  实际调到 _provider_params
_provider_params: env 里覆盖成 dashscope / qwen3.7-plus / DASHSCOPE_BASE_URL / DASHSCOPE_API_KEY
                  cwd 覆盖成 COURSE_DIR/"src"     ← 关键
            ↓
真实 StdioServerParameters(command, args, 覆盖后的 env, 覆盖后的 cwd)
```

**这就是"零代码改动换 provider"的实现**：`llm_fallback.py` 的 dashscope 分支是**课程自带的**（不是学习版加的），所以只要 env 走到那条分支，服务器行为就正确。**学分在课程的多 provider 支持上，学习版只负责把 env 正确送进去。**

**为什么 `kwargs["cwd"] = str(COURSE_DIR / "src")` 是必须的。** 课程传的是 `cwd=str(HERE / "src")`。`HERE` 被重定向到 `learning/task4/runs/4-5_collaboration/` 之后，这个表达式变成 `<学习输出根>/src`——**这个目录不存在**（输出根下只有 `experiment_protocol.json` / `latest.json` / 各次战役目录）。`stdio_client` 用不存在的 cwd 起子进程会直接 `FileNotFoundError`，**服务器根本起不来**。

学习脚本自己的注释写得很直白：`# 课程用 HERE / "src" 作为子进程 cwd；HERE 被重定向后必须显式指回课程源码目录。`

**这里有个更隐蔽的后果**：`src/config.py` 与 `src/llm_fallback.py` 都会 `load_dotenv()`，而它们**按 cwd 找 `.env`**。cwd 在 `src/` 下时找不到 `.env`（`.env` 在仓库根），所以 `DASHSCOPE_API_KEY` 能传进去**完全依赖 `_provider_params` 显式把它塞进 env**（L68）。**如果只修 cwd 不塞 key**，服务器会因为 `resolve_llm` 抛 `RuntimeError` 而起不来——`subagent_tools.py` L65–67 的模块级 `DEFAULT_MODEL = resolve_llm()[2] if has_llm() else ...` 在 **import 时**就会执行。**实测**：不用 `.venv-ch4v1` 的解释器而是系统的 `python3`（mcp 2.2.0）时，服务器在 `from mcp.server.fastmcp import FastMCP`（L14）就崩了，报 "mcp 2.x ... FastMCP was renamed to MCPServer ... or pin 'mcp<2'"——**这是另一个独立的启动前提：解释器必须是 mcp<2 的环境**。

**注入 3（在 `main()` 里）：凭据自检。** 学习脚本在写 evidence 之前，把 `DEEPSEEK_API_KEY` 与 `DASHSCOPE_API_KEY` 的**实际值**拿去搜整个 run_dir 的每个文件：

```python
leaked = []
for key_name in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
    key = os.getenv(key_name, "")
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and key in path.read_bytes().decode("utf-8", "ignore"):
            leaked.append(f"{key_name}:{path.relative_to(run_dir)}")
```

**为什么课程已经有 `redact_material` 和 `write_json` 两道防线，学习版还要加第三道？** 因为前两道防线**各自都只覆盖一半**，而学习版引入了**课程不存在的风险**：DashScope 的 key 是 `sk-...` 形状（`CREDENTIAL` 正则能抓），但**它是通过 `env` 传进子进程的**——子进程可能在**它自己的**输出（比如报错文本、`llm_receipts` 的 request body）里带上它。**课程的 canonical run 用 moonshot，moonshot 的 key 也是 `sk-`**，所以这个风险课程其实也有；但学习版把凭据自检做成了**独立的实测**而不是依赖正则。

三层的分工：

| 层 | 机制 | 覆盖 | 失败方式 |
| --- | --- | --- | --- |
| 1 | `redact_material` | **已知**的 15 个 env 值的精确子串 | 替换成 `[REDACTED]` |
| 2 | `write_json` 的 `CREDENTIAL` 正则 | **未知但形状像凭据**的串（`sk-` / `gh?-`） | **抛 ValueError，文件不落** |
| 3 | 学习版凭据自检 | **具体这两个 key 的实际值** | 记进 `credential_scan_findings`，`completed=False` |

第 3 层是**事后审计**而不是拦截（文件已经写了），但它能抓到前两层**都可能漏掉**的情况：如果某个 key 的形状不匹配 `CREDENTIAL`（比如被截断、被 JSON 转义成 `sk--...`）。**实测**：`credential_scan_findings: []`、`completed: true`。**三道防线都报"干净"。**

**通知凭据缺失如何如实记为 blocked。** 学习脚本**没有**做任何"假装有凭据"的事：

- 它**不**设 `--real-notifications`（`main()` 的 `course.run(...)` 调用只传 `interactive_human` 和 `human_timeout_seconds`，见 L91–93），所以 `real_notifications` 默认 False → 课程的"清空 10 个通知变量"分支生效 → 三条预检必然失败；
- 它在 `BLOCKED_GATE_REASONS` 里**手工写下三条缺失原因**（`BLOCKED_GATE_REASONS` 字典），并只对**真的在 blockers 里**的三条填理由：`for name in summary["blockers"] if name in BLOCKED_GATE_REASONS`；
- 它把 `subagent_llm` 写成 `{"name": "dashscope", "model": "qwen3.7-plus", "endpoint": ...}`，**明确记录这次跑的是哪个模型**——不冒充书方记录。

这三件事合起来就是"如实记为 blocked"的具体含义：**门禁状态从课程代码里来（不篡改）、缺失原因用文字补齐、替换的模型明写**。

---

## 3. 完整执行回放（学习版一次真实运行）

引用实测数字（campaign `20260921T112238Z`，`status=blocked`，`tool_call_count=30`，`model_call_count=5`，manifest 35 个文件）。把上面的函数按真实顺序串起来：

```text
main()
 ├─ load_dotenv(ROOT/.env) → DASHSCOPE_API_KEY 就位
 ├─ course.HERE = course.VALIDATION = learning/task4/runs/4-5_collaboration/
 ├─ copy experiment_protocol.json → 输出根（run() 之后要读它）
 ├─ course.StdioServerParameters := _provider_params  （provider 换成 dashscope/qwen3.7-plus）
 └─ asyncio.run(course.run("20260921T112238Z", interactive_human=False, human_timeout_seconds=1800))
     ├─ notification_readiness(env) → {email:false, telegram:false, slack:false}
     │    （无 SMTP/SendGrid、无 Telegram、无 Slack）
     ├─ run_dir = VALIDATION/20260921T112238Z   mkdir(exist_ok=False)
     ├─ write_json(protocol.json)
     ├─ env: COLLAB_PROVIDER=moonshot → 被 _provider_params 改成 dashscope
     │        OPENAI_MODEL=kimi-k3 → 改成 qwen3.7-plus
     │        HITL_TIMEOUT_SECONDS=2（本次全部调用都显式传 timeout，未用到）
     │        COLLAB_LLM_RECEIPT_PATH=run_dir/llm_receipts.checkpoint.json
     │        清空 10 个通知变量
     ├─ sensitive_values = (DASHSCOPE_API_KEY, ...非空值)
     ├─ StdioServerParameters(cwd=<课程>/src)  ★ 学习版指回课程源码
     └─ stdio_client → ClientSession.initialize()
         ├─ list_tools() → 41 个 schema → catalog.json
         │    ✓ 门禁 1: 9 个协作原语 ⊆ 41 个工具名
         ├─ [01] minimal_sync       sync  + minimal       → completed, ctx_tok 56,  prep 0
         ├─ [02] llm_generated_sync sync  + llm_generated → completed, ctx_tok 82,  prep 642
         │    ✓ 门禁 2: 两条都成功 + 策略名各自对 + prep_tokens 642>0 + 哨兵未漏
         │    （receipts/02 的 arguments.parent_context.private_note 含哨兵；payload.prepared_context 不含）
         ├─ [03] multi_turn_message 追加 "the item is unused" → {"status":"need_info"}  (9.269s)
         ├─ [04] async_spawn        math specialist         → running, task_id 非空
         ├─ [05..20] async_status ×16 轮询（0.25s 间隔）→ 第 16 次 completed
         │    result = {"status":"done","result":"The number 17 is a prime number."}
         ├─ [21] cancel_spawn       1000 条 taxonomy       → running
         ├─ [22] cancel_subagent    → previous_status=running, status=cancelled
         ├─ [23] cancelled_status   → status=cancelled, result=None   ★ result 为 None 证明回合被掐断
         │    ✓ 门禁 4: 消息成功 + async completed + 取消成功 + 取消后状态 cancelled
         ├─ approval_task = create_task([26] mcp_request_admin_approval, timeout_seconds=8)
         ├─ sleep(0.5)
         ├─ [24] hitl_pending → count=1 → request_id=15fbe932-...
         ├─ [25] hitl_operator_response（非交互）→ approved=True（备注明写"not a claimed human judgment"）
         ├─ [26] await approval_task → success=True, approved=True, NOT timeout   (2.003s)
         ├─ human_decision = None → 不写 human_decision.json ✗ 门禁 6 real_human_decision
         ├─ [27] hitl_timeout  timeout_seconds=1 → timeout=True, approved=False   (2.003s)
         │    ✓ 门禁 5: pending 非空 + 批准非超时 + 探针超时 + 探针不批准
         ├─ [28] email_preflight    → success=False "No email service configured"     ✗ 门禁 7
         ├─ [29] im_preflight       → success=False "Telegram bot token not configured" ✗ 门禁 8
         └─ [30] slack_preflight    → success=False "Slack webhook URL not configured"  ✗ 门禁 9
     ├─ llm_receipts.checkpoint.json → llm_receipts.json（5 条：subagent_turn ×4 + llm_generated_context ×1）
     │    ✓ 门禁 3: 5 条都含 response.id + usage.total_tokens + latency_seconds
     │    （qwen3.7-plus；总 token 608/642/878/1092/446；延迟 6.033/5.246/7.807/9.261/3.773 秒）
     ├─ gates: 5 True / 4 False
     ├─ classify_status(非交互) → 豁免 3 投递 + real_human_decision → core 5 条全过 → "blocked"
     ├─ write_json(summary.json)    official_complete=false; publication_authorized=false
     ├─ write_json(manifest.json)   35 个文件的 bytes+sha256
     └─ write_json(VALIDATION/latest.json)   manifest_sha256=f46162a9...
 → 学习脚本自检: credential_scan_findings=[] → completed=true
 → evidence.json + evidence.sha256 写入 run_dir
 → 打印 5 PASS / 4 FAIL, status: blocked
```

**9 条门禁里 5 条通过**：

| # | 门禁 | 结果 | 决定性证据 |
| --- | --- | --- | --- |
| 1 | `real_mcp_catalog_has_required_primitives` | ✅ | 真连服务器拿到 **41** 个 schema，9 个协作原语全在 |
| 2 | `two_real_context_strategies_compared` | ✅ | minimal → `prep_tokens=0`；llm_generated → `prep_tokens=642>0`，且哨兵 `PRIVATE-MARKER-MUST-BE-FILTERED` 未出现在 `prepared_context` |
| 3 | `raw_model_usage_latency_receipts` | ✅ | 5 条回执全有 `response.id` + `usage.total_tokens` + `latency_seconds` |
| 4 | `sync_async_message_cancel_status_lifecycle` | ✅ | 消息成功、异步 16 轮询后 completed、取消成功且状态变 cancelled |
| 5 | `hitl_pending_response_and_conservative_timeout` | ✅ | pending count=1 → 应答 approved=True 非超时；探针 `timeout=true` / `approved=false` |
| 6 | `real_human_decision` | ❌ | 非交互模式，由**自动化操作员**应答（`human_decision=None`），未计入真实人工决定 |
| 7 | `real_email_notification` | ❌ | 无 SMTP/SendGrid 凭据 → `No email service configured` |
| 8 | `real_im_notification` | ❌ | 无 Telegram bot token / chat id → `Telegram bot token not configured` |
| 9 | `real_slack_notification` | ❌ | 无 Slack webhook URL → `Slack webhook URL not configured` |

**总体 `status=blocked`**（四条的豁免规则见 2.9）。**6-9 这四条全部是"环境缺凭据"或"没有真人在场"，不是代码缺陷**——这也是 `classify_status` 把它们归入豁免集合的设计意图。

**子 Agent 的 LLM 是 DashScope `qwen3.7-plus`**（endpoint `https://dashscope.aliyuncs.com/compatible-mode/v1`）。5 条回执的 `response.model` 全是 `qwen3.7-plus`，`usage.total_tokens` 合计 3666，单次延迟 3.773–9.261 秒。

**与课程 canonical run 同型**：学习脚本的 docstring 预期"core 6 条门禁全过、3 条投递门禁缺失 → `blocked`"。**实测是 core 5 条 + `real_human_decision` 也不计入（非交互）**——因为学习版**没有**跑 `--interactive-human`。也就是说：学习版的实测结果与预期**在 status 上一致（blocked）、在 blocker 列表上多了 `real_human_decision` 一条**（预期说"core 6 条全过"是按交互模式算的）。这条差异本身是**如实记录**的一部分：本次没让真人按键，就不宣称有真人决定。

---

## 4. 动手验证

三个命令都实测过，环境前提先说明：

!!! note "运行前提（实测踩过）"
    1. **解释器**：必须用 **mcp 1.x** 的环境。仓库根有 `.venv-ch4v1`（`mcp==1.30.0`），而 `.venv` 是 `mcp 2.2.0`——后者会在 `from mcp.server.fastmcp import FastMCP` 处报 "FastMCP was renamed to MCPServer ... or pin 'mcp<2'"。命令里的 `$PY` 指 `.venv-ch4v1/bin/python`。
    2. **env**：子 Agent 的工具在 **import 时**就解析 provider（`subagent_tools.py` L65–67），所以 `DASHSCOPE_API_KEY` 必须**先导出**，否则 import 就抛 `RuntimeError: No LLM key configured`。`src/config.py` 的 `load_dotenv()` 按 cwd 找 `.env`，而 cwd 是 `src/`——**`.env` 不在那里**，所以必须显式 `set -a; . <仓库根>/.env; set +a`。
    3. 命令都在 `chapter4/collaboration-tools/` 下执行。
    4. **连 `main.py list` 也需要第 2 条**——顶层 `main.py` 第 37 行 `import subagent_tools` 是模块级导入，provider 在 import 时就解析。**实测**：不导出 `DASHSCOPE_API_KEY` 直接跑 `list`，会在 `import` 阶段抛 `RuntimeError: No LLM key configured`，**根本走不到打印清单那一步**。

```bash
PY=/Users/tal/.../ai-agent-book/.venv-ch4v1/bin/python
cd chapter4/collaboration-tools
set -a && . /Users/tal/.../ai-agent-book/.env && set +a
export COLLAB_PROVIDER=dashscope OPENAI_MODEL=qwen3.7-plus
```

**1. 列出工具（分清两个口径）—— 不需要 API 调用**

```bash
# 口径 A：课程自带的 CLI，列 12 个"协作工具"
$PY main.py list

# 口径 B：真连 MCP 服务器数 schema，得到 41
$PY -c "
import asyncio, sys, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def m():
    p = StdioServerParameters(command=sys.executable,
        args=[os.path.abspath('src/main.py')], cwd=os.path.abspath('src'), env=dict(os.environ))
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print('FOUND', len((await s.list_tools()).tools))
asyncio.run(m())
"
```

**预期现象**：口径 A 打出 `【子 Agent 管理】4 个 / 【人类协作 (HITL)】4 个 / 【多渠道通知】4 个`，合计 **12** 行 `  - <name>`，末尾提示 `python main.py <子命令> -h`。口径 B 打出 `FOUND 41`，并在 stderr 里看到 `Processing request of type ListToolsRequest` 与 `Server shutdown complete`。

**为什么值得跑**：这是**唯一**能一眼看出"41 vs 12 是两个口径"的方法。任务书里"45 个工具"的说法在这里被实测否掉。

**2. HITL 状态机 —— 不需要 API 调用**

```bash
# 2a. 批准路径：timeout 必须 > 2 秒，否则会被轮询粒度吞掉
$PY main.py hitl approve --message "删除 1000 条记录？" --timeout 8 --auto-approve

# 2b. 超时探针：timeout 必须 <= 2 秒，才能必然超时
$PY main.py hitl approve --message "无人应答的探针" --timeout 2 --auto-approve
```

**预期现象（实测）**：

- 2a → `{"success": true, "approved": true, "admin_notes": "自动模拟批准", "message": "Request approved by administrator"}`，**约 2 秒后返回**（一个轮询周期）。
- 2b → `{"success": true, "approved": false, "timeout": true, "message": "Admin response timeout after 2 seconds"}`，**同样约 2 秒**。
- 两次都会在 stderr 看到 `Failed to send admin notification`（没配通知渠道，工具只告警不抛错）。

**2b 是这一组里最有价值的**：`--auto-approve` 的模拟操作员在 **1 秒后**就批准了，但因为轮询间隔是 2 秒、`timeout=2` 时循环只检查一次，**批准被超时覆盖**——正好复现 2.19 节那个边界竞态。想亲眼看这个竞态，可以再跑一次 2b 并在末尾加 `-h` 之外的变体：把 `--timeout 8` 与 `--timeout 2` 的输出并排对比。**注意 2b 结束时那个请求在内存里的状态是 `timeout`**——进程退出后内存消失，不留痕迹。

**3. 两种上下文策略对比 —— 需要 DashScope 凭据（3 次 LLM 调用）**

```bash
$PY main.py subagent compare
```

**预期现象（实测，本次跑出来）**：末段"对比小结"打出

```text
  minimal        上下文    86 tok | 额外准备     0 tok | 泄漏隐私: False
  llm_generated  上下文   159 tok | 额外准备  1224 tok | 泄漏隐私: False
```

并且在 llm_generated 那一段能看到**打印出来的移交上下文**里只有用户信息 / 订单信息 / 业务规则，**`6222-0000-1111-2222`（卡号）没出现**，紧接着一行 `是否泄漏支付卡号: 否`。子 Agent 的结论是"可以自动批准"（gold 会员 + 299 < 500 + 7 天内）。

**注意数字会变**（`prep_tokens` 实测在 **960–1224** 之间浮动，因为 LLM 生成的摘要长度不固定），但两个不变量**每次都成立**：

- **minimal 的 `额外准备` 恒为 0**——这是结构的必然（2.18 节的硬编码）；
- **`泄漏隐私` 恒为 False**——这是纪律的产物，也是 `run_context_strategy_comparison` 里那行 `leaked = "6222-0000-1111-2222" in res["prepared_context"]` 在与 `run_experiment_4_5.py` 的哨兵做**同一件事**：用一个可搜索的串把"过滤生效"变成可观测的事实。

**想进一步验证取消与重复应答**（各几行，不需凭据）：

```bash
$PY -c "
import asyncio, sys; sys.path.insert(0,'src')
import hitl_tools as h
async def m():
    t = asyncio.create_task(h.request_admin_approval('probe', {}, timeout_seconds=8))
    await asyncio.sleep(0.3)
    rid = (await h.list_pending_requests())['requests'][0]['request_id']
    print('1st :', (await h.respond_to_request(rid, True, 'ok'))['success'])
    print('2nd :', (await h.respond_to_request(rid, False, 'late'))['message'])
    print('final:', {k: v for k, v in (await t).items() if k in ('approved', 'timeout')})
asyncio.run(m())
"
```

**预期现象（实测）**：`1st : True` / `2nd : Request <id> is already approved; late or duplicate responses cannot change a terminal decision` / `final: {'approved': True}`。**第二条输出就是 2.19 节那道"迟到/重复应答拒绝"守卫的运行时原话**。

---

**全页范围**：`run_experiment_4_5.py` 的 16 个顶层 def 逐个讲到；`subagent_tools.py` 按"两种策略 / sync-async / cancel-状态"三条主线精读（辅助函数归并）；`hitl_tools.py` 的 6 个 def 全讲，重点是状态机与那条终态守卫；`llm_fallback.py` 的 3 个 def 全讲；`main.py` 只读注册骨架。所有实测数字来自 `20260921T112238Z`，与[实测证据 JSON](../assets/task4/collaboration-evidence.json) 同源（`manifest_sha256 = f46162a9feb15683c5c032bcc4a44cb2f12f326ad16919334b1adc41995997b2`）。
