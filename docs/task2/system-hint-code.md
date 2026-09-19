# System-Hint 源码精读 · 状态栏信息怎样改变 Agent 行为

[实验说明](system-hint.md) · [实测结果](evidence.md#system-hint) · [学习运行脚本](../assets/task2/run_system_hint.py)

<div class="design-lead"><span>逐步搭建 / READ THE CODE</span><p>先看五种状态栏信息各自插在上下文的哪个位置，再读教学 Agent 的工具与循环，最后看正式战役如何把"hint 有没有用"变成客观可评分的对照实验。</p></div>

!!! note "先分清两种代码"
    **课程源码原文**附文件与行号（agent.py / config.py 是教学 Agent，run_experiment_2_8.py 是正式战役）；**学习运行脚本原文**来自本次实验的 `run_system_hint.py`；**教学示意**仅用于理解数据形状。

## 本页阅读路线

五种 hint → 配置开关 → 教学系统提示词 → hint 的注入位置 → 工具实现亮点 → 主循环与终止条件 → 战役设计（沙箱/评分/对照） → 检查点纪律 → 方向性假设与验收 → 学习版结果解读。

---

## 1. 五种状态栏信息：各解决什么失败模式

**遇到的问题**

Agent 循环里有一类"糊涂失败"：不知道现在几点（时间感缺失）、不知道自己已经重试了多少次（死循环）、忘记多步任务还剩什么（遗漏组件）、看不懂错误就放弃（恢复失败）、不知道自己在哪台机器上（环境误判）。它们不是模型能力问题，是**上下文里缺信息**。

**设计思路**

把五种信息做成五个独立开关，作为"状态栏"（system hint）注入上下文——每种都能单独开/关，才能归因。

**关键代码**

**课程源码原文** · [agent.py · L70–L81](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/agent.py#L70)：

```python linenums="70"
@dataclass
class SystemHintConfig:
    """Configuration for system hints"""
    enable_timestamps: bool = True       # 时间戳：任务前缀 + 工具结果元数据
    enable_tool_counter: bool = True     # 工具计数："Tool call #3" 防重复循环
    enable_todo_list: bool = True        # TODO 列表：多步任务的进度追踪
    enable_detailed_errors: bool = True  # 详细错误：类型+参数+修复建议
    enable_system_state: bool = True     # 系统状态：目录/OS/shell/python
    timestamp_format: str = "%Y-%m-%d %H:%M:%S"
    simulate_time_delay: bool = False    # demo 用：模拟时间流逝
    save_trajectory: bool = True
    trajectory_file: str = "trajectory.json"
```

**执行过程：看数据怎样变**

| hint | 注入位置 | 针对的失败模式 |
| --- | --- | --- |
| timestamps | 任务消息前缀 `[2026-09-19 09:00:00]` + 工具结果前缀 | "两天前说不支持改签，今天还能改吗"这类时间敏感决策 |
| tool_counter | 工具结果尾部 `[Tool call #4 for 'read_file']` | 同一文件反复读、同一命令反复失败 |
| todo_list | 每轮末尾 `=== CURRENT TASKS ===` 块 + 两个 TODO 工具 | 五件事只做三件就宣布完成 |
| detailed_errors | 工具抛异常时的结构化错误 | "Error" 一个词，模型不知道哪里错、怎么改 |
| system_state | 每轮末尾 `=== SYSTEM STATE ===` 块 | 在 Linux 机器上跑 `brew install` |

**接回真实源码**

五个开关在 `config.py` 的 [AgentConfig · L16–L38](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/config.py#L16) 有一份带 `from_env()` 的镜像（环境变量逐项开关），`PRESETS`（L80–L111）预置 full/minimal/debug/demo 四档。

**动手验证**

时间戳和 TODO 列表，哪个更像"给模型的指令"，哪个更像"给模型的数据"？

??? tip "先预测，再展开对照"
    TODO 列表两者都像：既是事实（做完了什么）也是计划（接下来做什么）——正因如此它由**工具**维护（rewrite/update），模型只能通过调工具改变它，状态就不会凭空漂移。时间戳是纯事实。这个区别在第 8 节的战役设计里被推到极致：正式战役连 TODO 工具的 schema 都进了"干预可见性"验收。

---

## 2. 教学系统提示词：hint 要"教模型怎么用"

**遇到的问题**

把状态信息塞进上下文，模型未必知道**该拿它做什么**。时间戳不会自动变成"判断记录先后"的动作。

**设计思路**

系统提示词里写明每种 hint 的用法，而不是只给数据。

**关键代码**

**课程源码原文** · [agent.py · L167–L178](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/agent.py#L167)（节选）：

```python linenums="167"
## Key Behaviors:
1. ALWAYS start complex tasks by creating a TODO list
2. Pay attention to timestamps to understand the timeline of events
3. Notice tool call numbers (e.g., "Tool call #3") to avoid repetitive loops - if you see high numbers, change strategy
4. Learn from detailed error messages to fix issues and adapt your approach
5. Be aware of your current directory and system environment shown in system state
```

**执行过程：看数据怎样变**

这正是战役里 `timestamps_raw` 与 `timestamps_guided` 两臂的区分：**raw** 只给时间戳数据；**guided** 额外给"把时间戳当作决策证据来比较"的指引（[run_experiment_2_8.py · L269–L273](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/run_experiment_2_8.py#L269)）。数据与用法是两个可分离的干预。

**接回真实源码**

`_init_system_prompt()`（L151–L188）全文还包括 TODO 管理规则（一次只能有一个 in_progress、立即标记完成）和 `FINAL ANSWER:` 终止标记的约定。

**动手验证**

只给数据（raw）和给数据+用法（guided），你预测哪个效果大？差多少？

??? tip "先预测，再展开对照"
    本次 DeepSeek 学习版：raw 3/3 vs 对照 2/3，guided 3/3 vs 2/3——小样本下两者都全对，分不出差。书稿的历史声明（时间感 19→49 分）在冻结协议里被明确标注"不可直接复现"，方向性结论留给大战役。单靠 3 个案例别过度解读。

---

## 3. hint 的注入位置：每轮末尾，不入历史

**遇到的问题**

状态栏内容**每轮都在变**（时间在走、计数在涨、TODO 在更新）。如果像系统提示词一样放在上下文开头，就是 KV Cache 实验（2-3）里 dynamic_system 的翻车现场。

**设计思路**

hint 作为**最后一条 user 消息**临时附加，发完即弃，不写进会话历史。

**关键代码**

**课程源码原文** · [agent.py · L858–L865](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/agent.py#L858)：

```python linenums="858"
# Prepare messages for the model - add system hint as last user message
messages_to_send = self.conversation_history.copy()
system_hint = self._get_system_hint()
if system_hint:
    messages_to_send.append({"role": "user", "content": system_hint})

# Store the messages being sent to LLM for trajectory logging
self.last_llm_messages = messages_to_send
```

**执行过程：看数据怎样变**

- `conversation_history` 只含 system/用户消息/assistant/工具结果——**稳定前缀**；
- `messages_to_send = history.copy() + [hint]`——每轮变化的部分在**末尾追加**；
- 对照 2-3 的结论：前缀缓存的失效从第一个差异点开始。hint 放末尾，前面的缓存全保住。**同样每轮变化，放对位置就几乎不付缓存代价**——两个实验互为注脚。

`_get_system_hint()`（[L301–L320](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/agent.py#L301)）在两个开关都关、或 TODO 列表为空时返回 `None`——禁用状态不产生空消息。

**动手验证**

`enable_system_state=False, enable_todo_list=True` 但模型还没建 TODO 时，请求里有几条 hint 消息？

??? tip "先预测，再展开对照"
    0 条。`_get_system_hint` 的条件：system_state 关且（todo_list 关**或**列表为空）→ 返回 None。注意 timestamps 和 tool_counter 根本不走这条消息——它们分别注入在任务前缀和工具结果里。五路 hint、三种注入通道（任务消息 / 工具结果 / 末尾状态消息）。

---

## 4. 工具实现的三个亮点

**遇到的问题**

通用文件/命令工具看似简单，各有一个隐蔽的坑：二进制误判、exec 作用域、`cd` 与复合命令。

**关键代码**

**课程源码原文** · [agent.py · L581–L593](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/agent.py#L581)（增量解码判二进制）：

```python linenums="581"
# Also check if it's valid UTF-8. Decode incrementally with
# final=False so a multi-byte character split by the
# 1024-byte read boundary is not mistaken for binary content
# (every CJK character is 3 bytes, so this is common).
try:
    codecs.getincrementaldecoder('utf-8')().decode(chunk, False)
except UnicodeDecodeError:
    return {..."error": "File is not a valid text file (encoding error)."...}
```

**课程源码原文** · [agent.py · L702–L708](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/agent.py#L702)（exec 显式命名空间）：

```python linenums="702"
# Run with an explicit namespace: with bare exec(code), top-level
# assignments land in this method's locals while functions defined
# in the snippet resolve free variables via module globals, so
# "x = 5; def f(): return x; f()" raises NameError.
exec_ns = {}
with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
    exec(code, exec_ns)
```

**课程源码原文** · [agent.py · L731–L743](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/agent.py#L731)（纯 cd 拦截）：

```python linenums="731"
# Update current directory if the command is a PURE 'cd'.
# Compound commands like `cd proj && make` must fall through to
# the subprocess below (which runs with cwd=working_dir) —
# intercepting them here would treat "proj && make" as the
# directory name and fail with "Directory not found".
stripped = command.strip()
if stripped.startswith('cd ') and not any(t in stripped for t in ('&&', ';', '|')):
    new_dir = stripped[3:].strip()
    ...
    if os.path.isdir(new_dir):
        self.current_directory = os.path.abspath(new_dir)
```

**执行过程：看数据怎样变**

- **增量解码**：只读前 1024 字节判断二进制。中文文本每个字 3 字节，1024 不是 3 的倍数——一个汉字正好被切断。`decode(chunk, False)`（final=False）告诉解码器"后面可能还有"，切半的字符不报错；`decode(chunk)` 会把它当非法序列。注释里的 "every CJK character is 3 bytes, so this is common" 是真实踩坑后的修复；
- **exec 作用域**：裸 `exec(code)` 里顶层赋值进局部命名空间、函数体内的自由变量却去全局找——`x = 5; def f(): return x; f()` 直接 NameError。显式 `exec_ns` 统一两个作用域；
- **纯 cd 拦截**：`cd` 必须更新 Agent 的 `current_directory` 状态（subprocess 的 cwd 改不了父进程的），但 `cd proj && make` 里的 "proj && make" 不是目录名——必须落穿给 subprocess。`startswith('cd ') and not any(t in ... ('&&', ';', '|'))` 一行完成这个区分。

**动手验证**

模型执行 `cd .. && ls` 之后，`self.current_directory` 变了吗？

??? tip "先预测，再展开对照"
    没变。这条命令含 `&&`，落穿给 subprocess：`ls` 在 `cwd=working_dir`（上级目录）里执行，输出正确，但父进程的 current_directory 保持原值。下一轮模型执行相对路径命令时基准目录没动——"看起来 cd 成功了但状态没跟上"的经典缝隙。纯 `cd ..` 才会真正更新状态。

---

## 5. 主循环与终止条件：从"只认标记"到"文本即终止"

**遇到的问题**

教学 Agent 早期版本只在回复里出现 `FINAL ANSWER:` 标记时终止。模型回了句普通的"你好"（无标记无工具调用），循环会把同样的消息重发 20 轮。

**设计思路**

终止条件放宽为"无工具调用的文本回复即终止"，同时保留标记解析与一个边缘情况。

**关键代码**

**课程源码原文** · [agent.py · L880–L896](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/agent.py#L880)：

```python linenums="880"
# Terminal path: a text reply with no tool calls ends the loop,
# even without the FINAL ANSWER: marker (e.g. a plain "hi"
# reply). Previously only "FINAL ANSWER:" broke the loop, so
# plain replies were re-sent for up to max_iterations.
if not has_tool_calls:
    self.conversation_history.append(message.model_dump())
    content = (message.content or "").strip()
    if content:
        final_answer = (content.split("FINAL ANSWER:", 1)[1].strip()
                        if "FINAL ANSWER:" in content else content)
        logger.info(f"Terminal text response (no tool calls); final answer: {final_answer[:100]}...")
    else:
        logger.warning("Empty model response with no tool calls; "
                       "stopping to avoid burning remaining iterations")
    self._save_trajectory(iteration, final_answer)
    break
```

**执行过程：看数据怎样变**

三条终止/容错路径：① 纯文本回复 → 结束（有标记就截取标记后的部分，没有就整段当答案）；② 空回复 → 也结束（避免空转烧预算）；③ 工具参数 JSON 解析失败（L905–L924）→ **不终止**，把解析错误包成工具结果回传，模型下一轮能看见自己的坏 JSON。另有边缘情况：带工具调用**同时**带 `FINAL ANSWER:` 的回合（L1013–L1019）会把工具结果记完再停。

工具结果的元数据注入在 L994–L1004：`[时间戳] [Tool call #N for 'X']
{结果}` 两个前缀按开关拼装——timestamp 和 tool_counter 的注入通道。

**接回真实源码**

`_save_trajectory()`（L226–L281）每轮把完整会话、工具调用、TODO、配置写盘（覆盖式），`last_llm_messages` 字段存的是**实际发给 LLM 的消息**（含临时 hint），与会话历史分开——调试时能看见"模型真正看到了什么"。

**动手验证**

为什么"坏 JSON 不终止"而"空回复终止"？

??? tip "先预测，再展开对照"
    坏 JSON 是**可恢复**的：错误信息回传后模型下一轮大概率修正——终止会把一个本可成功的任务判死。空回复是**不可恢复**的：同样的上下文再发一遍，大概率还是空——继续只会烧预算。终止策略跟着"重试有没有用"走，这正是第 1 章 Harness"纠正职责"的循环层版本。

---

## 6. 战役设计：为什么正式实验不用这个 Agent

**遇到的问题**

教学 Agent 用真实文件系统和 shell——评分只能看模型自述或人工读轨迹；沙箱不可复位；工具行为不可控（`read_file` 的错误格式一旦改文案，所有历史证据不可比）。

**设计思路**

`run_experiment_2_8.py` 是自成一体的战役：专用确定性沙箱工具、客观评分、每 run 独立沙箱、冻结协议。教学 Agent 保留给人玩，正式实验用它自己的循环。

**关键代码**

**课程源码原文** · [run_experiment_2_8.py · L62–L76](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/run_experiment_2_8.py#L62)（臂序交替）：

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

**执行过程：看数据怎样变**

六个套件各考一种 hint（timestamps 考三臂），每套件 5 个案例（学习版取前 3 个）。**同一案例的 enabled/disabled 臂共享完全相同的初始沙箱与用户提示词**，唯一差别是 hint 注入；臂的先后按案例序号奇偶交替——消除"先跑的臂碰巧占了便宜"的位置效应。

沙箱是确定性工具的世界：`read_record` 返回带时间戳的记录、`probe_resource` 对主资源永远报"temporarily unavailable"（逼模型走 fallback、考 tool_counter 的"重复失败换策略"）、`read_document` 对改名的文档报错（考 detailed_errors 的恢复）、`inspect_system` 返回伪造的主机信息（考 system_state 的包管理器选择）、`write_artifact` 只接受规定文件名（考 todo_list 的逐件交付）。

**接回真实源码**

`initialize_sandbox()`（L121–L157）按套件从案例参数建目录/文件/initial_state.json；`tools_for()`（L180–L264）按套件与 feature 生成工具表——**TODO 工具只在 todo_list feature 开启时才出现在 tools 里**（L198–L210），对照组连工具都见不到。

**动手验证**

`probe_resource` 为什么要把主资源设计成"永远不可用"？

??? tip "先预测，再展开对照"
    tool_counter 的价值只在"重复失败"时才显现：计数器告诉模型"你已经试了 4 次 gateway-a"。主资源永远失败制造了一个必须放弃它、转向 fallback 的决策点——评分标准 `primary_count <= 3`（[L400–L404](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/run_experiment_2_8.py#L400)）同时要求拿到 fallback 载荷且主资源重试不超过 3 次。没有"必然失败"，这个组件就没有可观察的对照差异。

---

## 7. 客观评分：从工具事件与沙箱状态判定，不听模型自述

**遇到的问题**

"模型说做完了"不等于做完了。评分必须独立于模型的自述。

**关键代码**

**课程源码原文** · [run_experiment_2_8.py · L390–L429](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/run_experiment_2_8.py#L390)（节选）：

```python linenums="390"
def component_scores(suite: str, case: dict, events: list[dict], root: Path) -> dict[str, bool]:
    calls = [(event["name"], event["arguments"], event["ok"]) for event in events]
    submissions = [args for name, args, _ in calls if name == "submit_result"]
    submitted = submissions[-1] if submissions else {}
    scores: dict[str, bool] = {}
    if suite in {"todo_list", "combined"}:
        exact_files = all(
            (root / "artifacts" / filename).is_file()
            and (root / "artifacts" / filename).read_text(encoding="utf-8").strip() == case["token"]
            for filename in case["artifacts"]
        )
        scores["todo_list"] = exact_files and set(submitted.get("artifacts", [])) == set(case["artifacts"])
```

**执行过程：看数据怎样变**

每个组件的判定材料：**工具事件序列**（谁、什么参数、成功与否）+ **沙箱最终状态**（文件是否存在、内容是否恰为规定 token）+ **最后一次 submit_result 的参数**。三重证据交叉——模型可以嘴上说"四个文件都写好了"，但 `exact_files` 逐个打开文件比对内容。`submissions[-1]` 取最后一次提交（模型可以先交一次错的再改）。

`validate_tool_protocol()`（L432–L442）另有一道独立校验：assistant 的 tool_calls 与后续 tool 消息必须严格按 ID 配对、无悬挂——证据里的消息序列本身必须合法。

**接回真实源码**

run_one 循环里还有一个反"提前收工"机制（L604–L614）：模型回了纯文本（没调 submit_result）时，追加一条催促消息 *"The audited task is not complete until you call submit_result..."* 再给机会；终止分类记为 `assistant_without_tool_call_reprompted`。而 `termination == "submit_result"` 才算 complete（L666–L669）——本次学习版 3 个 incomplete 格全部卡在这条上（见第 10 节）。

**动手验证**

模型没调过 submit_result 但把五个组件全做对了，component_scores 全 True、objective_pass 也 True。这个 run 的 complete 是 True 还是 False？

??? tip "先预测，再展开对照"
    False。complete = 回执有效 AND 工具协议合法 AND **termination == "submit_result"**。objective_pass 只看组件成绩，complete 还要求规范终止。"做对了但没交卷"和"交了卷"在验收口径里是两回事——评分与协议完成度分离，正是"验收独立于假设"的又一处体现。

---

## 8. 检查点纪律：每条消息后落盘、恢复前验哈希

**遇到的问题**

一个 65 run 的战役跑几十分钟，中途断网/崩溃怎么办？从零重跑既浪费又引入不可比性。

**设计思路**

每接受一条响应、每执行一个工具，都把证据原子写盘；恢复时校验协议哈希与沙箱哈希，任何不一致拒绝恢复。

**关键代码**

**课程源码原文** · [run_experiment_2_8.py · L598–L602 / L635–L636](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/run_experiment_2_8.py#L598)（节选）：

```python linenums="598"
evidence["api_calls"].append(receipt)
assistant = choice.message.model_dump(mode="json", exclude_none=True)
evidence["messages"].append(assistant)
evidence["current_sandbox_sha256"] = sandbox_hash(root)
atomic_json(evidence_path, evidence)
...
evidence["current_sandbox_sha256"] = sandbox_hash(root)
atomic_json(evidence_path, evidence)
```

**执行过程：看数据怎样变**

- `atomic_json`：写 `.tmp` 再 `replace`——读方永远看到完整文件，不会读到半截 JSON；
- `sandbox_hash`（L50–L59）对沙箱内全部文件的路径+sha256+大小做规范序列化再哈希；恢复路径（L510–L513）发现磁盘沙箱与检查点记录不一致即 `RuntimeError("sandbox changed")`——防"悄悄改了世界再续跑"；
- 初始哈希只算**非 artifacts** 的文件（L486–L488）：artifacts 是任务本身要写的产物，算进初始哈希会把"做对了任务"误判成"动了沙箱"。

**接回真实源码**

`validate_completed_evidence()`（L451–L465）恢复已完成的 run 前做五连校验：complete 标记、协议哈希、初始沙箱哈希、当前沙箱哈希、全部回执有效 + 工具协议合法。**证据一旦落盘就是只读的**。

**动手验证**

为什么恢复校验要比对 protocol_sha256，直接重读协议文件不行吗？

??? tip "先预测，再展开对照"
    协议文件本身可能被改（比如把案例参数改简单）。恢复时用**检查点里存的**旧协议哈希比对**当前**协议哈希，两者不一致说明中途换过协议——同一个战役里混了两套规则的证据不可比。冻结的含义就是哈希锁死。

---

## 9. 方向性假设与"对照组必须干净"

**遇到的问题**

hint 实验最容易出两个造假口子：干预根本没送达（开关开了但内容没进上下文）；对照组被污染（disabled 臂里混进了 hint 痕迹）。还有一个统计口子：把"无方向"的结果讲成"赢"。

**设计思路**

summarize 对每个对照给**方向性判据**，其中 timestamps_raw 明确无方向；验收门槛里加"干预可见"与"对照干净"两条正则/子串检查。

**关键代码**

**课程源码原文** · [run_experiment_2_8.py · L708–L722](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/run_experiment_2_8.py#L708)（方向性判据，节选）：

```python linenums="708"
if feature == "timestamps_raw":
    supported = None
    qualification = "nondirectional caveat; report the observed delta rather than a win/loss"
elif feature == "tool_counter":
    supported = enabled_passes > control_passes or enabled_primary < control_primary
    qualification = "higher pass count or fewer primary retries"
elif feature == "todo_list":
    supported = enabled_passes > control_passes and enabled_turns <= control_turns
    qualification = "higher complete-artifact count and no greater mean LLM turns"
```

**课程源码原文** · [run_experiment_2_8.py · L791–L803](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint/run_experiment_2_8.py#L791)（对照组干净性）：

```python linenums="791"
def disabled_is_clean(row: dict) -> bool:
    if row["condition"] != "disabled":
        return True
    raw_requests = json.dumps(
        [call.get("request", {}) for call in row["api_calls"]], ensure_ascii=False
    )
    raw_events = json.dumps(row["tool_events"], ensure_ascii=False)
    forbidden = (
        "<agent_status>", "TIME GUIDANCE:", "TOOL COUNTS:", "TODO LIST:",
        "SYSTEM STATE:", "Tool call #", "FileNotFoundError", "rewrite_todo_list",
        "update_todo_status",
    )
    return not any(item in raw_requests + raw_events for item in forbidden)
```

**执行过程：看数据怎样变**

- timestamps_raw 为什么无方向：书稿历史数据里"只给原始时间戳"既可能帮（提供依据）也可能害（噪音），先验方向不明确——把它预注册为**报告观察差值而非胜负**，防止事后挑说法（HARKing）；
- todo_list 的判据带**成本约束**：通过数更高**且**平均轮数不更多——hint 若要靠三倍轮数换来一点通过率，工程上是亏的；
- 对照组干净性检查 8 个禁止串——disabled 臂的原始请求和工具事件里**任何一个**都不许出现。与 2-5 的"干预可见性"门槛互为镜像：一组证明"开了的真送达"，一组证明"关的真没漏"。

**接回真实源码**

detailed_errors 的可见性判据（L774–L786）有一段注释记录的修复：详细错误由**工具**在失败时发出，证据在 tool-event 通道而非请求里——早期版本要求它出现在请求中，把真实合法的 run 误判为不合格。**验收代码自己也会踩"通道理解错"的坑**。

**动手验证**

todo_list 判据要求"通过更多且轮数不更多"。如果 enabled 臂通过率 100% 但平均 10 轮，disabled 臂 60% 但只要 2 轮，supported 是什么？

??? tip "先预测，再展开对照"
    False。轮数翻五倍换通过率——按预注册判据不支持。你可以**另外**报告"质量换效率"的取舍，但不能改口径说它 supported。预注册的意义就是防止事后放宽标准。

---

## 10. 学习版结果：combined 3/3 vs 0/3 与三个"没交卷"的格子

**遇到的问题**

DeepSeek 学习版（39 run，前 3 案例/套件）的对照表怎么读？campaign_complete=False 是失败吗？

**执行过程：看数据怎样变**

| 对照 | enabled | control | 轮数（enabled vs control） | supported |
| --- | --- | --- | --- | --- |
| timestamps_raw | 3/3 | 2/3 | 2.0 vs 2.7 | None（无方向） |
| timestamps_guided | 3/3 | 2/3 | 2.0 vs 2.7 | True |
| tool_counter | 3/3 | 3/3 | 3.0 vs 3.0 | False |
| todo_list | 3/3 | 3/3 | 5.3 vs 2.0 | False |
| detailed_errors | 3/3 | 3/3 | 3.0 vs 4.0 | False |
| system_state | 3/3 | 3/3 | 3.0 vs 3.0 | False |
| **combined** | **3/3** | **0/3** | **4.7 vs 8.0** | **True** |

- **combined（五组件复合任务）是唯一的大效应**：开全部 hint 时 3/3 通过、约 5 轮完成；关掉时 3 个案例全部烧完 8 轮预算也没提交 submit_result。翻看 `combined__all-01__disabled` 的轨迹末尾：模型在 `inspect_system` 之后把记录名（oak/pine）当成文档名去 `read_document`——**组件之间的混淆**正是 TODO 列表要防的失败模式；
- 单组件套件全 3/3 vs 3/3：任务太简单时 hint 没有发挥空间（3 个案例的样本量也分辨不出小差异）；
- **campaign_complete=False 的唯一原因**：`all_preregistered_runs_complete=False`——那 3 个 disabled combined 格没在预算内规范终止。这**不是实验失败**：3 个 incomplete 格恰恰是"没 hint 完不成任务"的直接证据，complete 门槛忠实记录了它。对照书方 Kimi K3 战役（65 run 全 complete、其 ledger 明确历史数值不复现）——不同模型在同套件下的表现结构不同，这是观察不是缺陷；
- todo_list 对照组轮数 2.0 < enabled 5.3：简单任务里建 TODO 本身要花轮数，判据"通过不降**且**轮数不升"判为 False——预注册口径如实执行。

**接回真实源码**

学习版运行器与 2-5 同构：自拼 DeepSeek 协议（model 用往返一致的 `deepseek-flash`）、每套件取冻结协议前 3 案例、`run_one`/`summarize`/`condition_order` 课程原代码、thinking 由 litellm 外的客户端包装关闭。唯一绕开的是课程 `main()` 的 Moonshot 凭据硬编码。

**动手验证**

想把 tool_counter 的对照做出差异，应该改战役的哪个部分？

??? tip "先预测，再展开对照"
    不是加 hint，是**加任务的重复失败压力**——比如把 fallback 也设成前两次失败、或把案例换成需要更多次探测的。对照差异 = 任务难度 × hint 相关性；3 个简单案例里两者都小。这属于扩展实验，本次未做。

---

## 最后回到项目

学习脚本协议拼装 → 课程 `run_one` 沙箱循环 → 工具事件与 component_scores → 方向性假设与验收 → [看真实实验结果](evidence.md#system-hint)。
