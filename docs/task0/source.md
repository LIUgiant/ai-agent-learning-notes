# 1-1 · 为什么把“留存历史”和“发给模型”分开？

[实验结果](ablation.md) · [代码来源约定](code-guide.md)

<div class="design-lead"><span>设计问题 / CONTEXT</span><p>要测出一类上下文的作用，就必须控制模型看见什么，同时留下足够的证据解释它做了什么。</p></div>

!!! note "怎样读这一页"
    先理解为什么需要这些模块，再跟随例子进入函数。标为“教学推演”的数据仅帮助理解，不是实验日志；代码块注明来源。完整摘录放在页末的备查链接中。

## 1. 从最简单的实现推到现在的设计

假设只写一个循环：把问题发给模型，执行工具，把结果拼回下一次请求。这能跑，但还不能做可信的消融实验。若直接把历史清空，实验结束后也难以复盘；若为五组复制五份循环，修复一组时容易漏掉另一组，差别就不再只是上下文。

源码因此保留**同一个执行循环**，把差异放在三个边界：发送请求之前、保存 assistant 消息时、写回工具结果时。实验运行器为每一组创建新的 Agent，避免上一组历史混进下一组。

先记住一个限制：这里的留存也不是完整原始消息的永不修改副本。`no_reasoning` 会在保存 assistant 字典时删字段，`no_tool_results` 会在对话中存空结果；完整工具执行记录另有轨迹。不同记录承担不同责任。

## 2. 谁拥有哪份数据？

| 实际变量 / 记录 | 谁使用它 | 设计理由 |
| --- | --- | --- |
| `self.conversation_history` | Agent 保存对话；局部 `messages` 指向它 | 执行循环持续追加 assistant 和 tool 消息 |
| `api_messages` | 当前模型请求 | 可以只选一部分历史，而不清空本地列表 |
| `tools` 请求字段 | 模型 | 描述可调用的名字、参数，不是 Python 实现 |
| `_execute_tool` 的工具映射 | 本地执行器 | 把模型提出的名字映射到真实函数 |
| 工具调用轨迹、`api_turns` | 实验评估与复盘 | 分别追踪执行行为和每轮实际请求 |

![design-context 的状态与责任](../assets/code-flow/design-context.svg)

## 3. 跟一条消息走两轮

**教学推演**：用户要求“计算 2 + 3”。用 S 表示 system，U 表示 user，A₁ 表示第一轮的工具调用，T₁ 表示返回结果 5。工具名与参数形状在此省略，避免把推演误认成原始请求。

| 时刻 | 本地历史 | full 发给模型 | no_history 发给模型 |
| --- | --- | --- | --- |
| 第一轮开始 | `[S, U]` | `[S, U]` | `[S, U]` |
| 执行工具后 | `[S, U, A₁, T₁]` | 尚未发送下一轮 | 尚未发送下一轮 |
| 第二轮开始 | `[S, U, A₁, T₁]` | 知道已经算出 5 | 仍只有 `[S, U]`，看不到上轮动作与结果 |

由此可以先预测：`no_history` 可能反复执行同样工具。它并不是工具没运行，而是下一轮缺少“已经运行”的信息。预测不是必然规律，实际次数要看日志。

### 设计落点：在请求边界选择，不在循环中删除

**课程源码原文** · `chapter1/context/agent.py` L680–694 · [定位源码](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter1/context/agent.py#L680)

```python linenums="680"
messages = self.conversation_history
if self.context_mode != ContextMode.NO_HISTORY:
    return messages

# System prompt(s) are always kept as the static prefix.
windowed = [m for m in messages if m.get("role") == "system"]

# Anchor on the latest user task. Nothing after it is retained: those
# messages are precisely the previous-round history being ablated.
user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
if not user_indices:
    return windowed
last_user_idx = user_indices[-1]
windowed.append(messages[last_user_idx])
return windowed
```

这里 `windowed` 是新列表；`append` 选入最后一个 user。它不是“最近 N 轮”，也不是“保留当前工具往返”：**最新 user 后的 assistant / tool 都不选入**。源码调用处的概括性注释不如这段选择逻辑精确。

普通模式直接返回 `messages`，没有复制列表。阅读调用处时，要区分 `messages`（留存列表的别名）与 `api_messages`（实际传给 API 的选择结果）。如果把这里改成 `self.conversation_history.clear()`，就同时改变了留存状态，不能再用同样方式解释实验。

## 4. 另外三种删除，为什么放在不同位置？ {#context-flow}

| 模式 | 处理位置 | 改了什么 | 仍然保留什么 |
| --- | --- | --- | --- |
| `no_reasoning` | assistant 消息入历史前 | 移除 `reasoning_content` | 工具调用、正常消息；当前轮 thinking 配置仍开启 |
| `no_tool_calls` | API 参数组装时 | 不发送 `tools`、`tool_choice` | 本地工具函数仍存在，但没有正常的结构化工具接口声明 |
| `no_tool_results` | 工具执行后 | 正常结果分支的 tool `content` 替换为空串 | 工具已执行，调用 ID、角色与执行轨迹仍存在 |

三个位置对应三种不同问题：模型是否能继承历史 reasoning？是否知道工具接口？是否能获得执行反馈？只说“删上下文”无法指导你该改哪段代码。

### 为什么 SDK 消息先转成字典？

SDK 的 `message` 是对象，后续逻辑却需要统一用键来删字段、存入历史。转换发生在 `_prepare_assistant_message` 内；这是程序的数据边界。

**课程源码原文** · `chapter1/context/agent.py` L547–553 · [定位源码](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter1/context/agent.py#L547)

```python linenums="547"
msg_dict = message.dict() if hasattr(message, 'dict') else message.model_dump()

# Remove reasoning_content if in NO_REASONING mode
if self.context_mode == ContextMode.NO_REASONING and 'reasoning_content' in msg_dict:
    msg_dict.pop('reasoning_content')

return msg_dict
```

`# 教学简化：先把 SDK 响应转换为消息字典` 是旧笔记写的注释，**不是原注释**。上面是课程原文。输入是 `response.choices[0].message`，不是整个 `response`；外层还有用量等数据，不能混为一谈。

### 为什么空结果还要留一条 tool 消息？

模型先给出调用 ID，返回消息用 `tool_call_id` 对上它。隐藏结果时保留这层配对，就能尽量把“没有结果内容”与“调用协议被破坏”区分开。注意源码的参数 JSON 解析错误走单独分支，会写回错误；不能声称该模式所有 tool 内容都绝对为空。

[切换五组完整 SVG 流程图](source-reference.md#context-flow)

## 5. 从实现推出实验的验收方式

首先检查**实际 API 请求**是否遵守该组规则，然后再检查行动和答案。只检查 `context_mode` 字符串，证明不了请求真的删掉了对应内容。

本次 full 用 3 轮、4 次工具得到正确答案；no_history 达到 5 轮上限，15 次工具里有 12 次重复。这个结果与上面的信息缺失推演相符。但每组只跑一次，不能据此宣称普遍成功率。`completed` 只说明产生终止文本，不代表计算正确；评分必须独立。

## 6. 现在打开源码，按什么顺序读？

1. `run_experiment_1_1.py::main` 附近的模式循环（L645 起）：确认每组新的实例与相同任务。
2. `agent.py::execute_task`（L703 起）：只先标出请求、保存、执行、回写、终止五个位置。
3. `_prepare_messages_for_api`（L663 起）：解释第二轮模型究竟能看到什么。
4. `_prepare_assistant_message` 与 `_execute_tool`：理解数据转换与动作执行的职责。
5. 运行器 `evaluate_context_contract`：对照实验声明和实际请求。

**自检题**：如果想测“只保留最近一次工具往返”，应该改工具执行器还是消息选择器？

??? tip "思路对照"
    改消息选择器，并保留 assistant 调用与其全部 tool 结果的配对。它是新的实验条件，不等同于当前 `no_history`。还应添加请求层的契约检查，确认你真正发出了计划中的窗口。

[继续：逐段源码备查](source-reference.md) · [下一课：搜索循环由谁执行？](search-code.md)
