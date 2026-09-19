# 提示词消融源码精读 · Tau-Bench 上的三个变量怎样被逐一降解

[实验说明](prompt-engineering.md) · [实测结果](evidence.md#prompt-engineering) · [学习运行脚本](../assets/task2/run_prompt_engineering.py)

<div class="design-lead"><span>逐步搭建 / READ THE CODE</span><p>先看 Tau-Bench 的客观奖励从哪来，再拆三个消融维度各自的实现，最后跟着六臂套件看冻结协议、检查点与汇总怎样把一次提示词实验变成可验收的证据。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号（ablation_agent.py / ablation_utils.py / run_ablation.py 均在 chapter2/prompt-engineering/，Tau-Bench 为课程 vendored 的评测框架）；**学习运行脚本原文**来自 `run_prompt_engineering.py`；**教学示意**仅用于理解数据形状。

## 本页阅读路线

客观奖励 → Agent 主循环 → 语气维度 → 组织维度 → 工具描述维度 → 隔离环境与检查点 → 冻结协议与汇总 → litellm 层 → 学习版结果解读。

---

## 1. Tau-Bench 的"做对了"从哪来

**遇到的问题**

"客服任务完成得更好"怎么客观判定？模型自述、人工打分都不可复现。

**设计思路**

Tau-Bench（课程 vendored 版）提供一个带**确定性环境状态**的模拟世界：工具直接改环境（数据库里的订单、用户），奖励由**环境终态与规则**计算，不由任何模型评分。

**执行过程：看数据怎样变**

AblationAgent 与环境的每一回合（[ablation_agent.py · L303–L353](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/ablation_agent.py#L303)）：

```text
模型输出 → message_to_action() 转成 Action
  ├─ 工具动作：env.step(action) → observation（工具输出）→ 作为 tool 消息回传
  └─ respond 动作：env.step() → observation 是【用户模拟器】的新回复 → 作为 user 消息回传
循环直到 env_response.done → reward ∈ {0, 1}
```

两个关键角色：

- **用户模拟器**（tau_bench/envs/user.py）：也是一次真实 LLM 调用（扮演顾客），非 Kimi 模型用 temperature 0（[user.py · L51–L74](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/tau_bench/envs/user.py#L51)）。它的每次调用也留回执（user_api_records）——**模拟顾客的花销同样算实验成本**；
- **奖励**：任务定义了期望的环境终态（订单改对了没有、退了没有）。`reward == 1` 只属于真实操作序列达成终态的运行。

**接回真实源码**

`message_to_action` 来自 vendored 的 [tau_bench/agents/tool_calling_agent.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/tau_bench/agents/tool_calling_agent.py)：有 tool_calls 就转工具动作，纯文本就转 `RESPOND_ACTION_NAME`。

**动手验证**

模型"态度极好地道歉但没改订单"和"语气生硬但订单改对了"，reward 各是多少？

??? tip "先预测，再展开对照"
    前者 0 后者 1。这正是选 Tau-Bench 做语气消融的原因：**主观体验不进奖励**，语气的影响只能通过"是否导致正确操作"间接显现。如果用 LLM 打分，语气好的道歉组反而可能得分更高。

---

## 2. AblationAgent 主循环：单工具截断与"错误也打分"

**遇到的问题**

接第三方评测框架的 Agent 有两个工程坑：模型一轮想调多个工具（框架只支持一个）；API 晚期报错把整条轨迹作废。

**设计思路**

循环内显式截断到第一个工具调用；API 异常返回**带 0 分的结果**而不是抛出。

**关键代码**

**课程源码原文** · [ablation_agent.py · L332–L345](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/ablation_agent.py#L332)：

```python linenums="332"
if action.name != RESPOND_ACTION_NAME:
    # Tool call - limit to first tool call
    next_message["tool_calls"] = next_message["tool_calls"][:1]
    messages.extend([
        next_message,
        {
            "role": "tool",
            "tool_call_id": next_message["tool_calls"][0]["id"],
            "name": next_message["tool_calls"][0]["function"]["name"],
            "content": env_response.observation,
        },
    ])
```

**课程源码原文** · [ablation_agent.py · L263–L272](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/ablation_agent.py#L263)：

```python linenums="263"
                failure = {
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }
                # Return a scored failure with every accepted receipt retained.
                # Raising here made the outer runner discard the complete
                # in-memory trajectory and all calls made before a late error.
                reward = 0.0
                break
```

**执行过程：看数据怎样变**

- **单工具截断**：多工具并发被裁成一个——被裁掉的第二个调用**静默消失**（不回传错误）。这改变了模型的行动节奏（对比 2-3 kv-cache 的课程实验允许并行工具调用），是本套件的历史约定，六臂一视同仁所以不影响对照；
- **错误也打分**：注释记录了旧实现的教训——`raise` 会让外层 runner 丢掉内存里的完整轨迹和已接受的回执。现在返回 `reward=0` + 完整 records：**传输失败是结果的一部分，不是证据的黑洞**。但注意 try 的覆盖范围只到 API 调用段——本次学习版 baseline 臂 task 2 的实际事故是：模型输出**被截断的工具参数 JSON**，`message_to_action`（tau_bench 框架层，L303 调用、[tool_calling_agent.py · L90](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/tau_bench/agents/tool_calling_agent.py#L90) 处无容错的 `json.loads`）抛出 `Unterminated string`，穿透 AblationAgent 到达 run_ablation 的兜底 except（L477），按 reward=0 + 完整 traceback 落盘。容错有边界：**Agent 层防得住自己解析的 JSON，防不住框架层替它解析的 JSON**。

每步的完整请求/响应（含 requested_seed、elapsed、litellm 成本估计）进 `api_records`（L195–L223），最后挂进 `info["agent_api_records"]`——证据随结果对象一起走。

**接回真实源码**

`completion_token_limit()`（L21–L23）给 kimi-k3 留 8192 输出预算：注释（L155–L161）说明 K3 会把大半 4K 预算花在隐藏推理上、返回空消息导致整场 60 格战役在模拟器边界失败的历史事故。学习版（DeepSeek 关思考）不受影响，走 4096。

**动手验证**

模型一轮输出了两个 tool_calls（先查用户、再改订单），截断后只执行第一个。下一轮模型会知道第二个调用被丢了吗？

??? tip "先预测，再展开对照"
    不会——被截断的调用没有对应的 tool 消息回传，模型只看到第一个调用的结果。它可能重发第二个调用（多花一轮），也可能以为做过了（漏步骤）。单工具协议的代价：**轮数变多 + 靠模型自己察觉遗漏**。这也是 reward 会暴露的失败模式之一。

---

## 3. 语气维度：指令前置，不是改写原文

**遇到的问题**

把系统提示词"翻译成 Trump 风格"有无数种做法，哪种是实验变量？

**设计思路**

语气做成**前置指令块**，原文一字不动地跟在分隔符后——只改变"怎么说"的要求，不改变知识内容。

**关键代码**

**课程源码原文** · [ablation_utils.py · L61–L81](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/ablation_utils.py#L61)：

```python linenums="61"
def apply_tone_modification(text: str, tone_style: ToneStyle) -> str:
    if tone_style == ToneStyle.DEFAULT:
        return text
    tone_instruction = TONE_INSTRUCTIONS[tone_style]
    # Add tone instruction to the beginning of the text
    if text:
        return f"{tone_instruction}\n\n---ORIGINAL INSTRUCTIONS---\n\n{text}"
    else:
        return tone_instruction
```

**执行过程：看数据怎样变**

`TONE_INSTRUCTIONS`（L20–L58）是两段完整的行为规范：Trump 版给了大量具体规则（最高级、重复强调、"folks"）和**改写示例**（"I'll help you book a flight" → "I'm going to get you the best flight deal ever, believe me..."）；casual 版要求 emoji + 俚语。指令带示例是关键——抽象的"请更随意"远不如示例可执行。

**接回真实源码**

注入点在 [run_ablation.py · L393–L397](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/run_ablation.py#L393)：wiki 先（可能）被乱序，再前置语气块。**叠加臂（all_ablations）= casual 语气 + 乱序 wiki + 空描述**，三层修饰依次应用。

**动手验证**

语气块放在 wiki **前面**（system 消息开头）而不是结尾，对 KV Cache 意味着什么？（联想 [2-3 实验](kv-cache-code.md)）

??? tip "先预测，再展开对照"
    每臂的语气块是**固定文本**，整个任务期间不变——它在前缀最前面，反而完全不破坏缓存。真正每轮变化的是对话尾部。前置固定指令块 + 稳定 wiki = 缓存友好的组织方式。提示工程与前缀缓存在这里不冲突。

---

## 4. 组织维度：预生成的乱序 wiki，不是运行时随机

**遇到的问题**

"把规则打乱"如果每次运行随机打乱，两次实验的 wiki 就不同——混淆变量。

**设计思路**

乱序版本**预生成、入库、冻结**：`wiki_airline_randomized.md` 是一个固定文件，内容与原 wiki 相同（同规则集），但去掉标题层次、平铺为无序列表。

**关键代码**

**课程源码原文** · [ablation_utils.py · L84–L111](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/ablation_utils.py#L84)：

```python linenums="84"
def load_randomized_wiki(env: str) -> str:
    """Load pre-generated randomized wiki for the specified environment"""
    if env == "airline":
        wiki_path = script_dir / "wiki_airline_randomized.md"
    elif env == "retail":
        wiki_path = script_dir / "wiki_retail_randomized.md"
    ...
    with open(wiki_path, 'r') as f:
        return f.read()
```

**执行过程：看数据怎样变**

原始 wiki 是分节的规则手册（退票政策、改签政策、 baggage 规则……），6,155 字符。乱序版保留**全部规则文本**但抹掉结构：没有标题导航，规则像洗过的扑克牌平铺。"信息量相同、组织度不同"——这是组织维度的干净定义。冻结协议的验收门槛专门有一条："the randomized wiki contains the same experimental rule material in the frozen pre-generated order"。

**动手验证**

为什么不干脆删掉一半规则来测"信息量"维度？

??? tip "先预测，再展开对照"
    那是另一个变量。组织消融的归因要求**信息量恒等**——删规则测的是"信息不足"，平铺测的是"检索困难"。混在一起就说不清是缺信息还是难检索。单一变量原则在提示工程里同样成立。

---

## 5. 工具描述维度：置空而不是删除

**遇到的问题**

工具 schema 里的 description 字段删掉和置空，对 API 的效果一样吗？

**设计思路**

递归地把**每个** description 置为空字符串——schema 形状（字段、类型、必填项）原样保留，只去掉自然语言说明。

**关键代码**

**课程源码原文** · [ablation_utils.py · L114–L133](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/ablation_utils.py#L114)：

```python linenums="114"
def remove_descriptions_recursive(obj: Any) -> Any:
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == "description":
                # Remove description by setting to empty string
                result[key] = ""
            else:
                # Recursively process nested structures
                result[key] = remove_descriptions_recursive(value)
        return result
    elif isinstance(obj, list):
        return [remove_descriptions_recursive(item) for item in obj]
    else:
        return obj
```

**执行过程：看数据怎样变**

airline 有 14 个工具，每个的 function description、每个参数的 description、嵌套 enum 项的 description 全部变空串。模型还能从**参数名**（`user_id`、`order_id`）和**函数名**（`cancel_order`）猜语义——但猜错率上升。课程冻结协议的假设就是"removing descriptions increases tool errors and reduces success"。

注意是 `""` 不是删键：某些 OpenAI 兼容端点对缺字段的 schema 校验更挑剔，置空是最保守的"内容清零"。递归处理保证**嵌套对象里的** description（比如数组元素类型的描述）也逃不掉。

**接回真实源码**

注入点 [run_ablation.py · L399–L402](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/run_ablation.py#L399)：`modified_tools_info = remove_tool_descriptions(env.tools_info)`——改的是发给模型的 tools 参数，环境内部执行的工具实现不变。**模型看到的接口**被消融，**世界的物理规则**保持恒定。

**动手验证**

置空描述后，模型调用一个参数名拼写错误的工具（`user_id` 写成 `userID`），会发生什么？

??? tip "先预测，再展开对照"
    工具执行层按 schema 校验失败，返回错误 observation（tau-bench 的工具错误），计入 `tool_errors`。没有 description 的世界里，参数名是模型唯一的拼写依据——错误率上升的通道之一就是这里。但注意：模型也可能从错误消息里学到正确拼法（下一轮修正），所以 tool_errors 高不一定 reward 低。

---

## 6. 隔离环境与 append-only 检查点

**遇到的问题**

六臂 × 多任务并发跑，环境状态不能互相污染；中途崩溃不能丢已完成的工作。

**关键代码**

**课程源码原文** · [run_ablation.py · L441–L450](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/run_ablation.py#L441)：

```python linenums="441"
def _run(idx: int) -> EnvRunResult:
    isolated_env = get_env(
        config.env,
        user_strategy=config.user_strategy,
        user_model=config.user_model,
        task_split=config.task_split,
        user_provider=config.user_model_provider,
        task_index=idx,
        user_seed=config.seed + i * 100000 + idx * 1000,
    )
```

**课程源码原文** · [run_ablation.py · L505–L511](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/run_ablation.py#L505)：

```python linenums="505"
with lock:
    data = [row.model_dump() for row in imported_results]
    if os.path.exists(ckpt_path):
        with open(ckpt_path, "r") as f:
            data = json.load(f)
    with open(ckpt_path, "w") as f:
        json.dump(data + [result.model_dump()], f, indent=2)
```

**执行过程：看数据怎样变**

- **每个任务一个全新环境实例**：用户模拟器的种子按 `seed + trial*100000 + task*1000` 派生——同臂同任务可复现，跨任务不相关；
- **检查点是追加式 JSON 列表**：每个任务完成（无论成败）立即落盘。`--resume-from`（L294–L365）按协议哈希 + 回执有效性筛选历史行，**已接受的任务永不重跑**——resume 的验收比首跑还严：model/provider/ablation_config/种子逐项比对。

**接回真实源码**

`--max-concurrency`（默认 1）控制并行度；学习版取 3。并发下检查点由 `multiprocessing.Lock()` 保护——多线程写同一文件必须串行化。

**动手验证**

为什么用户模拟器的种子要和任务索引绑定，而不是全场共用一个？

??? tip "先预测，再展开对照"
    共用种子 → 同一顾客人格贯穿所有任务 → 任务间相关，n 个任务不等于 n 次独立观察。种子绑定任务保证每个任务的模拟顾客独立抽样，统计上才是 matched cases。

---

## 7. 冻结协议与六臂汇总

**遇到的问题**

"跑完六组"和"跑完一次可验收的实验"差在哪？

**关键代码**

**课程源码原文** · [run_ablation.py · L544–L551](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/run_ablation.py#L544)：

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

**执行过程：看数据怎样变**

`run_full_suite`（L554–764）的启动校验（L568–L585）：命令行的 task_ids/model/user_model/temperature/seed/trials/max_steps 必须**逐项等于**协议文件里的值——协议是权威，CLI 只是传话。任何不一致直接 `ValueError`，防止"不小心换了参数还当同一场实验汇报"。

臂级汇总（L627–699）从每个臂的检查点文件里抽：rewards、每任务步数/工具调用/工具错误、全部真实调用的 usage 与 litellm 成本、response id 完整性。`arm_complete` 要同时满足：任务数齐、无任务错误、无传输错误、回执完整。`campaign_complete` = 全臂 complete + 凭据扫描干净——与假设成败无关（`hypothesis_results` 里写死 `"historical_percentages_reproduced": False`，声明历史数值不在当前战役复现）。

**接回真实源码**

冻结协议 [experiment_protocol.json](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/experiment_protocol.json) 里的 `transport_amendment` 记录了一次凭据变更：原定 gpt-4o-mini 双传输（OpenAI 配额不足 + OpenRouter 用户不存在）**零响应**后改道 Moonshot kimi-k3，并注明"这是可用性修正，不是看结果改条件"。

**动手验证**

学习版把 task_ids 从 10 改成 4、temperature 从 1 改成 0.3，还算"同一场实验"吗？

??? tip "先预测，再展开对照"
    不算——所以学习版**自拼了新的协议文件**（protocol_version 标注 task2-deepseek-learning），而不是篡改冻结协议后冒充原版。run_full_suite 的校验对着**学习协议**通过。同一场实验的边界由协议哈希界定；跨协议只能比方向，不能比数值。

---

## 8. litellm 层：一个客户端抽象多家厂商

**遇到的问题**

Tau-Bench 原版绑 OpenAI；课程要在 Kimi/DeepSeek/OpenRouter 间切换。

**关键代码**

**课程源码原文** · [ablation_agent.py · L163–L186](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering/ablation_agent.py#L163)：

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
```

**执行过程：看数据怎样变**

`custom_llm_provider="deepseek"` 让 litellm 把请求路由到 DeepSeek 端点（读 `DEEPSEEK_API_KEY` 环境变量）。seed 逐调用派生（`seed + task*1000 + step`）——同任务同步骤可复现。`res._hidden_params["response_cost"]` 是 litellm 内置的厂商价目估算：本次学习版 624 次调用合计 **$0.17**（litellm 自带 deepseek 价目），这比课程自算的 native_cost 更省事，但仍是"估算"口径。

学习运行脚本的接法不同于此前的实验：litellm 的 `completion` 在**多个模块的 import 时刻**被绑定（ablation_agent 与 tau_bench/envs/user.py 都在模块级 `from litellm import completion`），所以补丁必须打在 **import 之前**：

**学习运行脚本原文** · [run_prompt_engineering.py · L36–L46](../assets/task2/run_prompt_engineering.py)：

```python linenums="36"
import litellm

_real_completion = litellm.completion


def _no_thinking_completion(**kwargs):
    kwargs.setdefault("extra_body", {}).setdefault("thinking", {"type": "disabled"})
    return _real_completion(**kwargs)


litellm.completion = _no_thinking_completion
```

另一个坑：`--model-provider` 的 argparse choices 里没有 `deepseek`（L29 的 provider_list 是历史清单），学习版在 parse 之后手动覆写 `args.model_provider = "deepseek"`。

**动手验证**

为什么 2-3/2-5/2-9 的补丁打在"构造函数之前的模块属性"上就够了，这里却必须动 `litellm.completion`？

??? tip "先预测，再展开对照"
    前三个实验的调用点都在**运行时**做 `from agentbook.providers import resolve_backend`（每次构造重新解析），替换模块属性即可。litellm 的绑定发生在**模块加载时**（`from litellm import completion` 把当时的函数对象拷进每个模块的命名空间）——之后改 litellm.completion 不影响已加载的模块。补丁必须在任何 tau_bench/ablation 模块 import 之前落地。

---

## 9. 学习版结果：n=4 的诚实读法

**执行过程：看数据怎样变**

| 臂 | 任务 0–3 reward | 步数 | 臂完整 |
| --- | --- | --- | --- |
| baseline | 0, 1, 0, 0 | 15/10/–/29 | ❌（task 2 JSON 解析错误，reward 0 落盘） |
| tone_trump | 0, 1, 0, 0 | 11/11/30/21 | ✅ |
| tone_casual | 0, 1, 0, 0 | 11/11/4/16 | ✅ |
| wiki_random | 1, 0, 0, 0 | 27/20/21/21 | ✅ |
| no_tool_desc | 0, 1, 0, 0 | 9/11/30/30 | ✅ |
| all_ablations | 1, 1, 0, 0 | 16/11/30/30 | ✅ |

624 次真实调用（含用户模拟器），3,276,099 tokens，litellm 估算成本 $0.17。

- **任务 2、3 六臂全灭**（多臂打满 30 步）：这两题对 deepseek-flash 太难，是难度的地板效应——天花板（任务 1）人人通过，地板（2/3）人人失败，**有区分度的只剩任务 0**，而它在 wiki_random 和 all_ablations 通过、其余臂失败；
- 语气两臂与 baseline 逐题一致：在 n=4 下**无可见影响**——与书方 Kimi 战役"语气方向影响有限"的观察一致，但样本量不支持更强的说法；
- wiki_random 通过的任务从 1 变成 0：单任务翻转，在 n=4 下是噪声量级，不能解读为"乱序 wiki 改变了能力结构"；
- all_ablations 2/4：同样噪声量级。**没有预注册的方向性判据能在这个样本量下被支持或否定**——书方 10 任务 × 6 臂的战役同样声明"历史 30%/45% 点位未复现、方向有异"，见其 ledger。

**接回真实源码**

`campaign_complete=False` 的原因之一是 baseline 臂 task 2 的 JSON 解析错误（模型输出被截断的工具参数 JSON，tau_bench 框架层 `message_to_action` 无容错的 `json.loads` 抛出 `Unterminated string`，由 run_ablation 兜底捕获按 reward=0 落盘，第 2 节有完整链条）。之二：`native_cost_cny=None`（课程只在 model==kimi-k3 时计算原生成本）。5/6 臂完整。

**动手验证**

想给"组织维度"一个有统计效力的结论，最低限度要改什么？

??? tip "先预测，再展开对照"
    任务数（每臂 n）上去 + 多 trial（协议支持 trials_per_task）。粗略地，单任务通过率 0.25 vs 0.5 的差异在 n=4 下根本不可分辨；n≥30 才开始有意义。这正是书方跑 10 任务也只是"方向观察"的原因——提示词效应的真实战场是大规模评测。

---

## 最后回到项目

学习脚本协议拼装 → 课程 `run_full_suite` 六臂 → `run_with_ablation` 三维度注入 → AblationAgent 循环与 Tau-Bench 奖励 → [看真实实验结果](evidence.md#prompt-engineering)。
