# 提示词消融源码精读 · 三个文件逐函数通读

[实验说明](prompt-engineering.md) · [实测结果](evidence.md#prompt-engineering) · [学习运行脚本](../assets/task2/run_prompt_engineering.py)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>按依赖顺序过三个文件：ablation_utils.py（三个消融维度的实现）→ ablation_agent.py（Tau-Bench 上的消融 Agent）→ run_ablation.py（六臂编排与冻结协议）。vendored 的 tau_bench 本体当黑盒，只在用到它的接口处讲。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号（均在 chapter2/prompt-engineering/）；**学习运行脚本原文**来自 `run_prompt_engineering.py`；**教学示意**仅用于理解数据形状。

---

## 0. 函数清单（一个不漏）

**文件一**：[ablation_utils.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/ablation_utils.py)（163 行，6 项）

| # | 函数/常量 | 行号 | 一句话作用 |
| --- | --- | --- | --- |
| A1 | `ToneStyle` + `TONE_INSTRUCTIONS` | L12–58 | 三种语气及指令文本 |
| A2 | `apply_tone_modification` | L61–81 | 语气前置注入（原文不动） |
| A3 | `load_randomized_wiki` | L84–111 | 读预生成的乱序 wiki |
| A4 | `remove_descriptions_recursive` | L114–139 | 递归置空 description |
| A5 | `remove_tool_descriptions` | L142–163 | 工具表深拷贝后逐个去描述 |

**文件二**：[ablation_agent.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/ablation_agent.py)（395 行，3 项）

| # | 函数/类 | 行号 | 一句话作用 |
| --- | --- | --- | --- |
| B1 | `completion_token_limit` | L21–23 | kimi-k3 给 8192 输出预算 |
| B2 | `AblationAgent.__init__` | L31–58 | 存配置（wiki 可能已带消融） |
| B3 | `AblationAgent.solve` | L60–395 | Tau-Bench 上的主循环 |

**文件三**：[run_ablation.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/run_ablation.py)（776 行，5 项）

| # | 函数/常量 | 行号 | 一句话作用 |
| --- | --- | --- | --- |
| C1 | `parse_args` | L41–235 | 全部 CLI 参数（含 OpenRouter 回退逻辑） |
| C2 | `run_with_ablation` | L238–539 | ★一次消融臂的执行（含 resume） |
| C3 | `ABLATION_SUITE` | L544–551 | 六臂定义 |
| C4 | `run_full_suite` | L554–764 | ★六臂循环 + 冻结协议校验 + 汇总 |
| C5 | `main` | L767–772 | 分发（--all → 套件） |

---

# 文件一：ablation_utils.py —— 三个维度的实现

## A1. `ToneStyle` + `TONE_INSTRUCTIONS`（L12–58）

三种枚举（DEFAULT/TRUMP/CASUAL）对应两段指令文本。指令的写法值得抄：不是抽象的"请更夸张"，而是**具体规则 + 改写示例**——TRUMP 版给规则（最高级、重复强调、"folks"）加两条示例（"I'll help you book a flight" → "I'm going to get you the best flight deal ever, believe me..."）；CASUAL 版要求 emoji + 俚语同样带示例。**示例是可执行的规范**。

## A2. `apply_tone_modification`（L61–81）

```python linenums="61"
def apply_tone_modification(text: str, tone_style: ToneStyle) -> str:
    if tone_style == ToneStyle.DEFAULT:
        return text
    tone_instruction = TONE_INSTRUCTIONS[tone_style]
    if text:
        return f"{tone_instruction}\n\n---ORIGINAL INSTRUCTIONS---\n\n{text}"
    else:
        return tone_instruction
```

语气 = **前置指令块**，原文跟在 `---ORIGINAL INSTRUCTIONS---` 分隔符后**一字不动**。只改变"怎么说"的要求、不改变知识内容——这就是语气维度的干净定义。顺带一个 KV Cache 观察：语气块在整个任务期间是固定文本、位于 system 最前部——**完全缓存友好**（对照 [kv-cache 实验](kv-cache-code.md)：固定前缀 + 稳定 wiki = correct 模式的组织方式）。

## A3. `load_randomized_wiki`（L84–111）

```python linenums="100"
    if env == "airline":
        wiki_path = script_dir / "wiki_airline_randomized.md"
    elif env == "retail":
        wiki_path = script_dir / "wiki_retail_randomized.md"
```

乱序 wiki 是**预生成、入库、冻结**的固定文件（同规则集、抹掉标题层次、平铺为无序列表）。为什么不运行时随机打乱？——两次实验的 wiki 就不同了，混淆变量。冻结协议验收门槛专门有一条："randomized wiki contains the same experimental rule material in the frozen pre-generated order"（信息量恒等，只变组织度）。

## A4–A5. `remove_descriptions_recursive` / `remove_tool_descriptions`（L114–163）

```python linenums="114"
def remove_descriptions_recursive(obj: Any) -> Any:
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == "description":
                # Remove description by setting to empty string
                result[key] = ""
            else:
                result[key] = remove_descriptions_recursive(value)
        return result
    elif isinstance(obj, list):
        return [remove_descriptions_recursive(item) for item in obj]
    else:
        return obj
```

**置空而不是删键**——最保守的"内容清零"（某些端点对缺字段的 schema 更挑剔），且递归保证嵌套对象（数组元素类型的描述）也逃不掉。`remove_tool_descriptions` 在外面包一层 `copy.deepcopy`——消融的是发给模型的 tools 参数，环境内部的工具实现不动：**模型看到的接口被消融，世界的物理规则恒定**。

---

# 文件二：ablation_agent.py —— 消融 Agent

## B1. `completion_token_limit`（L21–23）

```python linenums="21"
def completion_token_limit(model: str) -> int:
    """Return enough output budget for reasoning models to emit an action."""
    return 8192 if "kimi-k3" in str(model).lower() else 4096
```

一行，背后是 solve 里 L155–L161 注释记录的事故：Kimi K3 会把大半 4K completion 预算花在隐藏推理上、返回**空消息无工具调用**，让整场 60 格战役在模拟器边界失败。给推理模型留 8192 是那次事故的修复。

## B2. `AblationAgent.__init__`（L31–58）

只存配置不建客户端：`tools_info`（可能已被 `remove_tool_descriptions` 处理）、`wiki`（可能已带语气块或乱序）、model/provider/temperature/seed。**消融发生在这个构造之前**（run_ablation 改好 wiki 和 tools 再传入）——Agent 对自己被消融毫不知情。

## B3. `solve`（L60–395）—— 主循环，四段拆开

**① 初始化（L74–108）**：打印 wiki 前 500 字符（verbose 时人眼可查语气块是否真在）；`env.reset(task_index)` 拿初始观察；`messages = [system(wiki), user(obs)]`。

**② 每步请求（L110–241）**：

```python linenums="163"
                completion_kwargs = {
                    "messages": messages,
                    "model": self.model,
                    "custom_llm_provider": self.provider,
                    "tools": self.tools_info,
                    "temperature": self.temperature,
                    "max_tokens": completion_limit,
                }
                requested_seed = (
                    self.seed + (task_index or 0) * 1000 + step
                    if self.seed is not None else None
                )
                if requested_seed is not None:
                    completion_kwargs["seed"] = requested_seed
                ...
                res = completion(**completion_kwargs)
```

走 **litellm**（`custom_llm_provider` 路由到任意厂商），seed 按任务×步派生（可复现）。逐调用记录完整 request/response/usage/litellm 成本估计进 `api_records`（L184–223）——证据随轨迹走。

**③ 错误处理（L242–272）**：

```python linenums="263"
                failure = {...}
                # Return a scored failure with every accepted receipt retained.
                # Raising here made the outer runner discard the complete
                # in-memory trajectory and all calls made before a late error.
                reward = 0.0
                break
```

API 异常 → reward=0 + 完整 records 返回（**不是 raise**——注释记录旧版 raise 让外层丢掉全部轨迹的教训）。但注意 try 的覆盖范围只到 API 调用段：学习版 baseline task 2 的真实事故是 `message_to_action`（框架层，L303）的无容错 `json.loads` 抛 `Unterminated string`——**穿透**这个 try 到 run_ablation 的兜底。Agent 层防得住自己解析的 JSON，防不住框架层替它解析的。

**④ 动作执行（L274–362）**：

```python linenums="332"
            if action.name != RESPOND_ACTION_NAME:
                # Tool call - limit to first tool call
                next_message["tool_calls"] = next_message["tool_calls"][:1]
                messages.extend([
                    next_message,
                    {"role": "tool",
                     "tool_call_id": next_message["tool_calls"][0]["id"],
                     "name": next_message["tool_calls"][0]["function"]["name"],
                     "content": env_response.observation},
                ])
            else:
                messages.extend([
                    next_message,
                    {"role": "user", "content": env_response.observation},
                ])
```

`message_to_action` 把模型输出转成 Tau-Bench 动作：工具动作 → `env.step` 的 observation 作为 **tool 消息**回传；respond 动作 → observation 是**用户模拟器的新回复**、作为 **user 消息**回传。**单工具截断**（`[:1]`）：多工具调用只执行第一个、被裁的静默消失（模型可能重发多花一轮、也可能以为做过了漏步骤）。`env_response.done` 即结束，reward 由环境终态给出。

---

# 文件三：run_ablation.py —— 编排与协议

## C1. `parse_args`（L41–235）

长函数但结构清晰：范围参数（--num-trials/--env/--task-split/--start-end-index/--task-ids）、模型参数（--model/--model-provider/--user-model/...）、消融参数（--tone-style/--randomize-wiki/--remove-tool-descriptions）、套件参数（--all/--output/--resume-from）。两段值得读的逻辑：provider 默认按模型名含 `/` 判 OpenRouter（L209–214）；L224–233 的 **OpenRouter 回退**——OPENAI key 缺失或 gpt-5 系列时自动改道（gpt-5 直连要组织验证且拒绝函数工具+推理并存）。学习版的坑：`--model-provider` 的 argparse choices **没有 deepseek**——学习脚本在 parse 后手动覆写。

## C2. `run_with_ablation`（L238–539）—— 一次消融臂

**消融应用（L385–415）**：

```python linenums="388"
    modified_wiki = env.wiki
    modified_tools_info = env.tools_info
    if args.randomize_wiki:
        modified_wiki = load_randomized_wiki(config.env)
    if args.tone_style != "default":
        modified_wiki = apply_tone_modification(modified_wiki, ToneStyle[args.tone_style.upper()])
    if args.remove_tool_descriptions:
        modified_tools_info = remove_tool_descriptions(modified_tools_info)
    ...
    agent = AblationAgent(
        tools_info=modified_tools_info,
        wiki=modified_wiki,
        ...
    )
```

顺序固定：乱序 → 语气前置 → 工具去描述——叠加臂三层依次应用。

**resume（L292–365）**：从旧目录按协议哈希 + 逐行回执校验筛选已完成的 (task, trial)，**已接受的任务永不重跑**——验收比首跑还严（model/provider/ablation_config/seed 逐项比对）。

**隔离执行（L441–515）**：

```python linenums="441"
        def _run(idx: int) -> EnvRunResult:
            isolated_env = get_env(
                config.env,
                ...,
                user_seed=config.seed + i * 100000 + idx * 1000,
            )
            # Apply same modifications to isolated env
            if args.randomize_wiki:
                isolated_env.wiki = load_randomized_wiki(config.env)
            ...
```

每个任务一个**全新环境实例**，用户模拟器种子按 `seed + trial*100000 + task*1000` 派生——同任务可复现、跨任务独立抽样（共用种子会让同一"顾客人格"贯穿所有任务，n 个任务就不算 n 次独立观察）。消融对隔离环境**重复应用**（`isolated_env.wiki = ...`）。

**检查点（L505–511）**：`multiprocessing.Lock()` 保护下 append-only 写 JSON——每任务完成立即落盘，崩溃可 resume。

## C3. `ABLATION_SUITE`（L544–551）

```python linenums="544"
ABLATION_SUITE = [
    ("baseline",      {"tone_style": "default", "randomize_wiki": False, "remove_tool_descriptions": False}),
    ("tone_trump",    {"tone_style": "trump",   "randomize_wiki": False, "remove_tool_descriptions": False}),
    ("tone_casual",   {"tone_style": "casual",  "randomize_wiki": False, "remove_tool_descriptions": False}),
    ("wiki_random",   {"tone_style": "default", "randomize_wiki": True,  "remove_tool_descriptions": False}),
    ("no_tool_desc",  {"tone_style": "default", "randomize_wiki": False, "remove_tool_descriptions": True}),
    ("all_ablations", {"tone_style": "casual",  "randomize_wiki": True,  "remove_tool_descriptions": True}),
]
```

六臂 = 基线 + 三维度各一 + 叠加臂（叠加用 casual 而非 trump——书稿的历史选择，冻结在套件定义里）。

## C4. `run_full_suite`（L554–764）—— 套件与冻结协议

**协议校验（L568–585）**：命令行的 task_ids/model/user_model/temperature/seed/trials/max_steps 必须**逐项等于**协议 JSON 的值——协议是权威，CLI 只是传话，任何不一致 `ValueError`。学习版因此**自拼了学习协议**（标 task2-deepseek-learning）而不是篡改冻结协议——同一场实验的边界由协议哈希界定。

**臂循环（L593–614）**：依次设 args 的三个消融开关、跑 `run_with_ablation`、按臂记 artifact 哈希。

**汇总（L627–699）**：从每臂检查点抽 rewards/步数/工具调用/错误/usage/litellm 成本；`arm_complete` 要同时满足任务数齐、无任务错误、无传输错误、回执完整。`campaign_complete` = 全臂 complete + 凭据扫描干净——**与假设成败无关**（`hypothesis_results` 写死 `"historical_percentages_reproduced": False`，历史数值不在当前战役复现）。

## C5. `main`（L767–772）

`--all` → `run_full_suite`，否则单臂。学习脚本构造 sys.argv 后调 `parse_args` → 覆写 provider → `run_full_suite`。

---

## 完整执行回放（学习版 wiki_random 臂 task 0）

```text
run_prompt_engineering.py
 ├─ patch litellm.completion（关 thinking）← 必须在 import tau_bench 之前！
 ├─ 写学习协议 → sys.argv 构造 → parse_args → 覆写 model_provider=deepseek
 └─ run_full_suite
      └─ 臂 wiki_random: run_with_ablation
           ├─ load_randomized_wiki → 乱序平铺版 wiki
           ├─ AblationAgent(wiki=乱序版, tools=完整)
           └─ _run(task=0):
                isolated_env（user_seed 派生）→ isolated_env.wiki = 乱序版
                solve: 循环 ≤30 步
                 ├─ 模型: respond("您好，请问有什么可以帮您？")
                 │    → env.step → 用户模拟器回复 → user 消息
                 ├─ 模型: tool_calls=[get_user] → env.step → 数据库行 → tool 消息
                 └─ ... → 环境终态 → reward 0 或 1 → 检查点落盘
      → 六臂汇总 → usage_and_cost → campaign_complete 判定 → manifest
```

litellm 层的一个关键细节（学习脚本 L36–46）：补丁必须打在 `import tau_bench` **之前**——user.py 和 ablation_agent.py 都在模块级 `from litellm import completion`（绑定当时的函数对象），之后改 `litellm.completion` 对已加载模块无效。

## 动手验证

1. **把 `next_message["tool_calls"][:1]` 的截断去掉**：允许并行工具调用（DeepSeek 支持一次多个）——对照 2-3 的发现（并行 4 个 search_web），看 tau_bench 的环境是否支持一轮多个动作。大概率不支持——这就是截断存在的原因。
2. **给 `run_with_ablation` 的隔离环境漏掉一次消融应用**（比如只改了主 env 的 wiki）：臂内的不同任务用了不同 wiki——对照性无声地坏掉。检查点里的 request messages 是唯一的发现渠道。
3. **把 `ABLATION_SUITE` 的叠加臂换成 trump**：跑一遍看 2/4 那格是否复现——顺便体会"套件定义被冻结"的含义：改动它就不再是同一场实验，得换协议版本号。
