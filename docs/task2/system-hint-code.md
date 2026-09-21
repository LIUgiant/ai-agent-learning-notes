# System-Hint 源码精读 · run_experiment_2_8.py 逐函数通读

[实验说明](system-hint.md) · [实测结果](evidence.md#system-hint) · [学习运行脚本](../assets/task2/run_system_hint.py)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>主文件是正式战役 run_experiment_2_8.py（929 行）——20 个函数按源码顺序逐个讲；配套的教学 Agent（agent.py 1061 行）给全函数清单并深讲六个最有料的部分。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号（chapter2/system-hint/）；**学习运行脚本原文**来自 `run_system_hint.py`；**教学示意**仅用于理解数据形状。

---

## 0. 函数清单（一个不漏）

**主文件**：[run_experiment_2_8.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/run_experiment_2_8.py)（929 行，20 项）

| # | 函数 | 行号 | 一句话作用 |
| --- | --- | --- | --- |
| 1 | `canonical_json` | L27–28 | 规范序列化（排序+紧凑，哈希的前提） |
| 2 | `sha256_bytes`/`sha256_file` | L31–36 | 哈希 |
| 3 | `utc_now`/`atomic_json` | L39–47 | 时间戳 / 原子写 |
| 4 | `sandbox_hash` | L50–59 | 沙箱全部文件 → 一个哈希 |
| 5 | `condition_order` | L62–76 | 臂序交替（位置效应控制） |
| 6 | `case_prompt` | L79–118 | 每套件的用户提示词 |
| 7 | `initialize_sandbox` | L121–157 | 按案例建沙箱（文件/状态） |
| 8 | `load_state` | L160–161 | 读沙箱状态 |
| 9 | `function_tool` | L164–177 | 工具 schema 构造器 |
| 10 | `tools_for` | L180–264 | 按套件+feature 生成工具表 |
| 11 | `status_message` | L267–291 | ★`<agent_status>` 状态栏消息 |
| 12 | `timestamp_wrap` | L294–295 | 时间戳包装（feature 开才包） |
| 13 | `execute_tool` | L298–387 | ★确定性沙箱工具（含 D 级增强） |
| 14 | `component_scores` | L390–429 | ★从工具事件+沙箱终态客观评分 |
| 15 | `validate_tool_protocol` | L432–442 | assistant/tool 配对校验 |
| 16 | `accepted_receipt` | L445–448 | 回执有效性 |
| 17 | `validate_completed_evidence` | L451–465 | 恢复已完成 run 的五连校验 |
| 18 | `run_one` | L468–672 | ★★一格的完整执行（检查点/循环/催促） |
| 19 | `summarize` | L675–855 | 对照聚合 + 方向性假设 + 验收门槛 |
| 20 | `main` | L858–925 | 并发编排（Kimi 专用，学习版绕过） |

**配套**：agent.py（教学 Agent，32 项全清单见第 28 节，深讲 6 个）+ config.py（五开关 + PRESETS）

---

## 1–3. 基建五件套（L27–47）

`canonical_json`（排序键 + 紧凑分隔符）保证**同一数据只有一种序列化**——哈希比较才可靠（缩进/键序差异都会让 sha256 变）。`atomic_json` 的 tmp+replace 同 [3-1/2 的 `_write_checkpoint`](../task3/memory-modes-code.md)：读方永远看到完整文件。

## 4. `sandbox_hash`（L50–59）

```python linenums="50"
def sandbox_hash(root: Path) -> str:
    entries = []
    if root.exists():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            entries.append({
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            })
    return sha256_bytes(canonical_json(entries))
```

沙箱内全部文件的"指纹的指纹"：路径排序（顺序稳定）→ 每文件哈希 → 整体再哈希成一个字符串。run_one 每写一次证据都记一次 `current_sandbox_sha256`——**磁盘世界的变化被持续追踪**，恢复时的篡改检测靠它。

## 5. `condition_order`（L62–76）

```python linenums="62"
def condition_order(suite: str, index: int) -> list[str]:
    if suite == "timestamps":
        return (
            ["timestamps_guided", "timestamps_raw", "disabled"]
            if index % 2 == 0
            else ["disabled", "timestamps_raw", "timestamps_guided"]
        )
    enabled = {...}[suite]
    return [enabled, "disabled"] if index % 2 == 0 else ["disabled", enabled]
```

案例序号偶数 → enabled 臂先跑；奇数 → disabled 先跑。**臂的执行顺序被均衡**——如果先跑的臂碰巧占便宜（比如沙箱残留、模型状态），位置效应被抵消而不是污染全部案例。timestamps 套件三臂同理反转。

## 6. `case_prompt`（L79–118）

每套件一段固定的用户提示词（五段 if/elif + combined 的五合一长句）。两个值得注意的措辞：`"Do not guess if a tool can provide evidence"`（timestamps 套件——不许猜，必须用工具验证）；`"Use tools for every factual claim and do not omit a component"`（combined——每个事实主张都要工具背书）。**提示词本身就是实验设计的一部分**（它决定了"不用 hint 时模型有多容易迷路"）。

## 7. `initialize_sandbox`（L121–157）

按套件从案例参数建目录：records/（带时间戳的两份记录）、resources/（只放 fallback——primary 永远缺席）、artifacts/（空目录待交付）、documents/（只放改名后的真文档）、initial_state.json（含伪造的 system 信息）。`root.exists()` 就抛——**拒绝覆盖已有沙箱**，防串场。initial_state 的内容就是"世界的真相"，execute_tool 按它判对错。

## 8–9. `load_state` / `function_tool`（L160–177）

`load_state` 一行读 initial_state.json。`function_tool` 是工具 schema 的构造器——统一塞 `additionalProperties: False`（比 2-3 的工具表更严：模型多给参数直接被 schema 拒绝）。

## 10. `tools_for`（L180–264）

按套件生成工具表，两个设计点：**submit_result 的 schema 按套件定制**（timestamps 要 `selected_record`、combined 要七个字段——提交的形状就是答案的形状）；**TODO 工具只在 `todo_list` feature 开启时出现**（L198–210）——对照组连工具都看不见，干预差异从工具层就开始。

## 11. `status_message`（L267–291）—— 状态栏本体

```python linenums="267"
def status_message(features: set[str], state: dict, counters: dict, todos: dict) -> str | None:
    sections = []
    if "timestamp_guidance" in features:
        sections.append(
            "TIME GUIDANCE: Treat explicit timestamps as decision evidence. Compare them directly; "
            "raw readings do not help unless you translate them into an action."
        )
    if "tool_counter" in features:
        rendered = ", ".join(f"{key}={value}" for key, value in sorted(counters.items())) or "none"
        sections.append(
            "TOOL COUNTS: " + rendered + ". After repeated failure, diagnose and switch to a viable fallback."
        )
    if "todo_list" in features:
        rendered = "; ".join(f"{name}: {status}" for name, status in todos.items()) or "not created"
        sections.append("TODO LIST: " + rendered + ". Keep every required deliverable visible until verified.")
    if "system_state" in features:
        system = state.get("system", {})
        sections.append(
            "SYSTEM STATE: " + ", ".join(f"{key}={system.get(key)}" for key in (
                "os", "shell", "python", "cwd", "manager"
            ))
        )
    if not sections:
        return None
    return "<agent_status>\n" + "\n".join(sections) + "\n</agent_status>"
```

四个 feature 各拼一段，包进 `<agent_status>` 标签，**没有 feature 就返回 None**（不产生空消息）。注意 `timestamp_guidance` 给的不是数据而是**用法**（"把时间戳当决策证据来比较"）——这正是 raw 与 guided 两臂的分界。对照 [task2 的 KV Cache](kv-cache-code.md)：这条消息每轮都变（计数在涨、TODO 在更新），但它在 run_one 里被**追加在消息列表末尾**——前缀缓存不受损。动态信息放尾部 = 信息新鲜 + 缓存友好。

## 12. `timestamp_wrap`（L294–295）

`"[%s] %s" if "timestamps" in features else 原文`——read_record 工具的返回值按 feature 决定带不带时间戳前缀。raw 臂的"数据"通道。

## 13. `execute_tool`（L298–387）—— 确定性世界

每个工具一段 if，全部**确定性**（无随机、无网络）。挑四个有讲头的：

```python linenums="318"
    elif name == "probe_resource":
        resource = str(arguments.get("name", ""))
        if resource == state.get("primary"):
            ok, content = False, "Error: primary resource is temporarily unavailable"
        elif resource == state.get("fallback"):
            content = (root / "resources" / f"{resource}.txt").read_text(encoding="utf-8").strip()
        else:
            ok, content = False, "Error: unknown resource"
```

`probe_resource` 对 primary **永远失败**——制造"必须放弃主资源转向 fallback"的决策点，tool_counter 的价值（"你已经试了 N 次"）只在这里显现。评分标准同时要求 `primary_count <= 3`（重试不超限）。

```python linenums="346"
    elif name == "read_document":
        filename = Path(str(arguments.get("file", ""))).name
        path = root / "documents" / filename
        if not path.is_file():
            ok = False
            if "detailed_errors" in features:
                available = sorted(item.name for item in (root / "documents").iterdir())
                content = json.dumps({
                    "error_type": "FileNotFoundError",
                    "description": f"Document {filename!r} does not exist",
                    "arguments": arguments,
                    "stack": "sandbox.read_document -> open",
                    "suggestion": "List the directory and try the renamed file",
                    "available_documents": available,
                })
            else:
                content = "Error: document not found"
```

同一个"文件不存在"，D 关时返回一句 `Error: document not found`，D 开时返回**结构化错误**——类型、描述、参数、调用栈、建议、**现有文档清单**。模型拿到 `available_documents` 几乎必然能一步恢复——detailed_errors 的收益机制就在这一行。

```python linenums="365"
    elif name == "list_documents":
        if counters.get("read_document", 0) == 0:
            ok, content = False, "Error: first attempt the user-requested document path"
        else:
            content = json.dumps(sorted(item.name for item in (root / "documents").iterdir()))
```

`list_documents` 有个守卫：**必须先试过用户指定的路径**才能列目录——防止模型跳过"合理尝试"直接拿答案，逼错误恢复路径真实发生。

```python linenums="385"
    if "tool_counter" in features:
        content += f"\nTool call #{counters[name]} for '{name}'."
```

函数末尾统一追加计数后缀（feature 开时）——工具结果的第二个增强通道。

## 14. `component_scores`（L390–429）—— 客观评分

```python linenums="390"
def component_scores(suite: str, case: dict, events: list[dict], root: Path) -> dict[str, bool]:
    calls = [(event["name"], event["arguments"], event["ok"]) for event in events]
    submissions = [args for name, args, _ in calls if name == "submit_result"]
    submitted = submissions[-1] if submissions else {}
    scores: dict[str, bool] = {}
    ...
    if suite in {"todo_list", "combined"}:
        exact_files = all(
            (root / "artifacts" / filename).is_file()
            and (root / "artifacts" / filename).read_text(encoding="utf-8").strip() == case["token"]
            for filename in case["artifacts"]
        )
        scores["todo_list"] = exact_files and set(submitted.get("artifacts", [])) == set(case["artifacts"])
```

判定材料三层：**工具事件序列**（谁/什么参数/成功与否）、**沙箱终态**（todo_list 组件逐个打开文件比对内容 == 规定 token）、**最后一次 submit_result 的参数**（`submissions[-1]`——允许先交错再改）。模型嘴上说得再好，文件内容不对就是不过。

## 15–17. 协议与恢复校验（L432–465）

`validate_tool_protocol`：扫描消息序列，assistant 的 tool_calls 必须与紧随其后的 tool 消息**按 id 严格配对**、无悬挂——证据里的消息序列本身必须合法。`accepted_receipt` 同 2-5（id/model/usage）。`validate_completed_evidence` 是恢复路径的五连校验：complete 标记、协议哈希、初始沙箱哈希、当前沙箱哈希（磁盘没被改过）、回执+协议合法——**证据一旦落盘就是只读的**。

## 18. `run_one`（L468–672）—— 一格的完整生命

四段拆开：

**① 沙箱与初始哈希（L481–489）**：沙箱不存在则 `initialize_sandbox`；`initial_files` 只算**非 artifacts** 的文件——artifacts 是任务要写的产物，算进初始哈希会把"做对了任务"误判成"动了沙箱"。

**② 检查点恢复（L490–513）**：已有 evidence 且 complete → 五连校验后直接返回；不 complete → 协议/初始/当前三重哈希一致才续跑，否则 `RuntimeError("resume refused")`。

**③ 催促机制（L553–565 + L604–614）**——本文件最有性格的设计：

```python linenums="556"
        evidence["messages"].append({
            "role": "user",
            "content": (
                "The audited task is not complete until you call submit_result. "
                "Use the available evidence, perform any missing verification, and submit now."
            ),
        })
        evidence["termination"] = "assistant_without_tool_call_reprompted"
```

模型回了纯文本（没调 submit_result）时，追加一条催促消息再给机会——**不交卷不给过**。终止分类记录为 `reprompted`，而 `termination == "submit_result"` 才算 complete（L666–669）。

**④ 主循环（L566–640）**：`while 已成功调用数 < max_turns(8)`：`request_messages = deepcopy(evidence["messages"]) + [status_message]`（状态栏是**末尾的临时消息**，不进历史）；每次 API 调用后立刻 `atomic_json` 落盘（证据=检查点，逐消息级）；工具执行后同样落盘。`submitted = submitted or name == "submit_result"`，提交即 break。

## 19. `summarize`（L675–855）—— 假设与验收

**方向性判据（L708–722）**：

```python linenums="708"
        if feature == "timestamps_raw":
            supported = None
            qualification = "nondirectional caveat; report the observed delta rather than a win/loss"
        elif feature == "tool_counter":
            supported = enabled_passes > control_passes or enabled_primary < control_primary
        elif feature == "todo_list":
            supported = enabled_passes > control_passes and enabled_turns <= control_turns
```

timestamps_raw 预注册为**无方向**（历史数据里既可能帮也可能害，先验不明——防 HARKing）；tool_counter 允许"通过更多**或**主资源重试更少"两条路；todo_list 带成本约束（轮数不升）。**预注册的意义：不许事后挑说法**。

**对照组干净性（L791–803）**：

```python linenums="791"
    def disabled_is_clean(row: dict) -> bool:
        if row["condition"] != "disabled":
            return True
        ...
        forbidden = (
            "<agent_status>", "TIME GUIDANCE:", "TOOL COUNTS:", "TODO LIST:",
            "SYSTEM STATE:", "Tool call #", "FileNotFoundError", "rewrite_todo_list",
            "update_todo_status",
        )
        return not any(item in raw_requests + raw_events for item in forbidden)
```

disabled 臂的请求与工具事件里，八个禁止串**任何一个都不许出现**——与"干预可见性"门槛（D 开的真送达）互为镜像：开的是真开了，关的是真没漏。

`detailed_errors` 的可见性判据（L774–786）带一段注释记录的真实修复：详细错误由**工具在失败时**发出，证据在 tool-event 通道而非请求里——早期版本要求它出现在请求中，把真实合法的 run 误判为不合格。

## 20. `main`（L858–925）

Kimi 专用（MOONSHOT key + 冻结协议端点）——学习版绕过，直接 `run_one`/`summarize` + 自拼 DeepSeek 协议（每套件前 3 案例 → 39 run）。

---

## 21–27. 配套：agent.py 教学 Agent 的六个精选

教学 Agent（1061 行，32 个函数）不在正式战役里，但它是"hint 长什么样"的日常版。全函数清单：`_reasoning_safe_temperature`(L28)、四个数据类(L40–81)、`SystemHintAgent.__init__`(L89)、`_init_system_prompt`(L151)、`_get_system_state`(L190)、`_get_timestamp`/`_advance_simulated_time`(L214–224)、`_save_trajectory`(L226)、`_format_todo_list`(L283)、`_get_system_hint`(L301)、`_get_tools_description`(L322)、`_execute_tool`(L470)、`_get_detailed_error`(L510)、`_get_error_suggestions`(L529)、六个 `_tool_*`(L556–823)、`execute_task`(L825)、`reset`(L1051)。挑六个：

**`_init_system_prompt`（L167–178）**：系统提示里明写五种 hint 的**用法**（"Notice tool call numbers... if you see high numbers, change strategy"）——hint 要"教模型怎么用"，这正是战役里 raw 与 guided 的分界在日常版的体现。

**`_get_system_hint`（L301–320）**：教学版状态栏 = SYSTEM STATE + CURRENT TASKS 两段，**作为最后一条 user 消息临时附加、发完即弃**（不入会话历史）——与战役的 `status_message` 同一位置哲学：动态内容放尾部，前缀缓存无损。

**`_tool_read_file`（L581–593）**：判二进制用 `codecs.getincrementaldecoder('utf-8')().decode(chunk, False)`——**final=False** 告诉解码器"后面可能还有"，1024 字节边界上被切半的汉字不报错（每个 CJK 字符 3 字节，1024 不是 3 的倍数，这是真实踩坑后的修复）。

**`_tool_code_interpreter`（L702–708）**：`exec_ns = {}` + `exec(code, exec_ns)`——显式命名空间。注释解释了为什么不能用裸 exec：顶层赋值进局部命名空间、函数体自由变量却查全局——`x = 5; def f(): return x; f()` 直接 NameError。

**`_tool_execute_command`（L731–743）**：纯 `cd` 拦截（`startswith('cd ') and not any(t in stripped for t in ('&&', ';', '|'))`）——`cd` 必须更新 Agent 的 `current_directory` 状态，但 `cd proj && make` 里的 "proj && make" 不是目录名，必须落穿给 subprocess。一行条件完成这个区分。

**`execute_task` 的终止路径（L880–896）**：注释记录了历史 bug——旧版只认 `FINAL ANSWER:` 标记，模型回了句普通的"你好"（无标记无工具调用），循环把同样消息重发 20 轮。现在**无工具调用的文本回复即终止**、空回复也终止（避免空转烧预算）；坏 JSON 工具参数**不终止**（错误回传，模型下轮可修正）——终止策略跟着"重试有没有用"走。

config.py（130 行）：`AgentConfig` 五开关 + `from_env`（环境变量逐项开关）+ 四个 PRESET（full/minimal/debug/demo）——注意 `validate()` 只放行 kimi/moonshot/dashscope 三家，DeepSeek 走学习版的注入路径而非这个 CLI。

---

## 完整执行回放（学习版 combined × disabled × all-01 一格）

```text
run_system_hint.py → 自拼协议 → ThreadPool(4)
 run_one(suite=combined, case=all-01, condition=disabled)
  ├─ initialize_sandbox（records/resources/artifacts/documents/state）
  ├─ 轮1: 消息=[system][用户提示]（无状态栏，disabled）
  │        模型: read_record(oak) ✓ → read_record(pine) ✓（时间戳组件完成）
  ├─ 轮2-4: probe_resource(core-a) ✗✗ → mirror-a ✓（无计数提醒）
  ├─ 轮5: write_artifact ×3 ✓ → read_document(config.txt) ✗（plain 错误）
  │        模型迷路：read_document(oak) ✗ read_document(pine) ✗ ← 把记录名当文档名
  ├─ 轮6-8: 继续打转，无 submit_result
  └─ 8 轮耗尽 → termination=None → complete=False
 → component_scores 全 False → objective_pass=False
 → 汇总：combined 3/3 vs 0/3，supported=True
```

## 动手验证

1. **把 `status_message` 的 `<agent_status>` 块改放到消息列表开头**：对照 KV Cache 实验——状态栏每轮都变，放头部就是 dynamic_system 翻车现场（命中率归零），放尾部前缀无损。跑一遍看证据里的消息顺序。
2. **给 `list_documents` 的守卫删掉 `counters` 检查**：模型可以直接列目录拿真文件名，detailed_errors 套件的对照组（plain 错误）也变容易——一个守卫维系的是"错误恢复路径必须真实发生"。
3. **把 `condition_order` 改成永远 enabled 先跑**：想一个会因此偏倚结果的具体场景（提示：共享账号的模型侧缓存、或沙箱文件系统的时间戳残留）。
