# 流式恢复源码精读 · 历史、缓冲区、提交状态

[实验与结果](stream.md) · [学习运行脚本](../assets/task5/run_stream.py)

## 1. 先保存“已完成的事实”

**问题：** 重试时如果把整个对话重来，已经执行的工具可能被重复调用；如果把半截参数当作完成事实，又会污染后续历史。

**设计：** `pre_state` 预置一份已经提交的 Trace。正文断点时四个价格工具结果都在；参数断点时只保存机票结果。它们是实验夹具，不是先让模型自由跑出来的完整前序轨迹。

```python
# 教学示意
committed = [user_request, assistant_flight_call, flight_result]
buffer = {"text": "", "tool_args": ""}
```

Trace 是课程中立结构，render 再把它变成 API messages。学习版用 KIMI 分支产生兼容格式，但实际发往 DeepSeek；不能将这理解为运行了 Moonshot 实验。

## 2. Partial 里到底存什么

**课程源码原文**：[ `Partial` · L22–32](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/streaming.py#L22)

```python linenums="22"
class Partial(dict):
    """流被切断时手上攒到的东西。"""

    @classmethod
    def new(cls) -> "Partial":
        return cls(reasoning="", text="", tool_name=None, tool_args="", tool_index=None,
                   tool_args_closed=False, truncated=False, finished=False)

    @property
    def has_partial_args(self) -> bool:
        return bool(self.get("tool_name")) and not self.get("tool_args_closed")
```


`text` 和 `reasoning` 是字符串；tool_name 标识当前工具，tool_args 是未完成的 JSON 文本；tool_index 使接收器只追踪一个调用。`truncated` 表示本次故障注入是否生效；`finished` 与 `tool_args_closed` 表示不同层的结束。

不要用 `if tool_args` 判断可执行，只能说明收到过字符。`has_partial_args` 也只是状态提示，不是 schema 校验。

## 3. `_absorb` 为什么只做积累

课程 KIMI 分支读取 `choices[0].delta`，追加 content 和 reasoning_content；遍历 delta.tool_calls，把第一个调用的 index 记住，只追加这个 index 的 arguments。

```python
# 教学示意：单个工具的三段返回
state = {"tool_args": ""}
for fragment in ['{"city', '":"东', '京"}']:
    state["tool_args"] += fragment
```

这里不能尝试“每收到一段就执行”：第一段不能解析，第二段即使能修补成 JSON，也不知道是不是原来的意图。

**源码对照：** `_absorb` 负责解释不同厂商协议，`_cut_here` 负责决定何时截断，两者分开。这样改变阈值不需要改解析器。

## 4. `_cut_here` 为什么检查 closed

**课程源码原文**：[ `_cut_here` · L35–43](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/streaming.py#L35)

```python linenums="35"
def _cut_here(state: Partial, where: str, limits: dict) -> bool:
    if where == REASONING:
        return len(state.get("reasoning") or "") >= limits[REASONING]
    if where == TEXT:
        return len(state.get("text") or "") >= limits[TEXT]
    if state.get("tool_args_closed"):
        # 参数整块到达，流里根本没出现过“半截”，这个断点在这家厂商上不可复现。
        return False
    return bool(state.get("tool_name")) and len(state.get("tool_args") or "") >= limits[TOOL_ARGS]
```


课程某些协议分支一次给完整 functionCall，并标记 tool_args_closed；这时不假装观察到“半截原生参数”。学习版兼容分支使用字符裁切，所以记录里额外保留 `received_before_character_cut` 和原始 events，让你看清是收到的形态还是实验人为裁切。

**注意原实现边界：** `_read_stream_once` 在迭代自然结束时设置 finished=True，不足以区分协议正常完成与某些异常 EOF。生产实现还需看结束标记或 finish_reason。这也是为什么本次不宣称已经实现完整网络恢复框架。

## 5. 两种恢复请求有什么不同

```python
# 教学示意：两条臂都从 committed 历史出发
resend_messages = committed.copy()
meta_messages = committed.copy() + [{
    "role": "user",
    "content": "上次在「半截内容」处中断，请继续，不要重复。",
}]
```

resend 是当前轮重发，已经完成的机票工具结果不会丢；meta 是普通消息指令，它不保证模型按字符精确续接，也可能生成新的工具调用。

课程还有 prefill 分支，通过厂商特定前缀接口续写。DeepSeek 学习版没有移植或运行该分支；本次也关闭 thinking，所以不做思考断点。不要把“看过课程代码”和“在当前模型上实测成功”混在一起。

## 6. 为什么语法检查之外还要检查值

```python
# 教学示意：两份 JSON 都合法，只有第一份满足任务
json.loads('{"city":"东京"}') == {"city": "东京"}  # True
json.loads('{"city":"大阪"}') == {"city": "东京"}  # False
```

课程 `judging.judge` 给出 `recovered`、`json_valid`、`args_correct` 三个字段，含义不同。参数分支的 recovered 只说明得到参数对象；本次学习版另外计算 strict_correct，必须匹配期望值与工具名。

正文的答案函数仅查找允许误差内的数值，不能验证推导过程、是否出现相互矛盾的总额。以后可以把结果固定成结构化 total_cny 再独立算账，但这是进一步完善评测，不是本次已有验证。

## 7. 重复调用检测为何不等于防重复执行

**课程源码原文**：[ `ToolCall.fingerprint` · L46–48](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/neutral_trace.py#L46)

```python linenums="46"
    def fingerprint(self) -> str:
        """“工具名 + 参数”指纹，用来数切换之后有没有把已经做过的事重做一遍。"""
        return f"{self.name}({json.dumps(self.arguments, sort_keys=True, ensure_ascii=False)})"
```


把工具名与规范化参数拼成指纹，可以发现恢复结果是否再次提出相同调用。`sort_keys=True` 避免键顺序不同被当成两次不同意图。

但这只能检测日志中的“同名同参”，没有阻止执行、没有业务事务，也不能区分两次合法的同参数查询。本次恢复结果没有真正执行新工具，重复字段只是重复提议计数。

迁移到有副作用的接口时，更可靠的设计是业务 operation_id + 服务端去重。对话 request_id、工具 call_id、业务 operation_id 各有用途，不宜用同一个标识代替全部。

## 8. 如果要接实时对话，先画取消状态机

**设计建议，未在本次音频系统实测：** 每轮生成持有 turn_id；新输入到来后标记旧 turn 失效。旧文本、旧 TTS 音频帧返回时先检查 turn_id；已提交的业务动作另外查询真实状态，不能因取消播放就假设取消了动作。

“停止生成”“停止播放”“撤销已完成操作”是三条不同路径。先建立这三个概念，再扩展流式恢复，能避免把旧答案继续念给用户。

## 源码导航：读完后回到这些函数

按职责定位，先读主路径，再补适配器。下面的行号来自本次固定版本。

| 文件 / 函数 | 行号 |
| --- | --- |
| `streaming.py::Partial.new` | [L26](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/streaming.py#L26) |
| `streaming.py::Partial.has_partial_args` | [L31](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/streaming.py#L31) |
| `streaming.py::_cut_here` | [L35](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/streaming.py#L35) |
| `streaming.py::stream_until` | [L46](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/streaming.py#L46) |
| `streaming.py::_read_stream` | [L56](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/streaming.py#L56) |
| `streaming.py::_read_stream_once` | [L68](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/streaming.py#L68) |
| `streaming.py::_stream_request` | [L99](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/streaming.py#L99) |
| `streaming.py::_absorb` | [L116](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/streaming.py#L116) |
| `run_continuation.py::pre_state` | [L33](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/run_continuation.py#L33) |
| `run_continuation.py::_base_payload` | [L53](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/run_continuation.py#L53) |
| `run_continuation.py::_append_assistant_prefix` | [L58](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/run_continuation.py#L58) |
| `run_continuation.py::_append_user` | [L71](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/run_continuation.py#L71) |
| `run_continuation.py::_with_hint` | [L86](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/run_continuation.py#L86) |
| `run_continuation.py::_text_of` | [L103](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/run_continuation.py#L103) |
| `run_continuation.py::_calls_of` | [L108](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/run_continuation.py#L108) |
| `run_continuation.py::recover` | [L112](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/run_continuation.py#L112) |
| `run_continuation.py::main` | [L147](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/run_continuation.py#L147) |
| `judging.py::judge` | [L19](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/judging.py#L19) |
| `judging.py::_answer_ok` | [L67](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/judging.py#L67) |
| `neutral_trace.py::Reasoning.portable_text` | [L35](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/neutral_trace.py#L35) |
| `neutral_trace.py::ToolCall.fingerprint` | [L46](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/neutral_trace.py#L46) |
| `neutral_trace.py::Trace.add` | [L69](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/neutral_trace.py#L69) |
| `neutral_trace.py::Trace.user` | [L73](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/neutral_trace.py#L73) |
| `neutral_trace.py::Trace.tool_result` | [L76](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/neutral_trace.py#L76) |
| `neutral_trace.py::Trace.called_fingerprints` | [L79](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/neutral_trace.py#L79) |
| `neutral_trace.py::Trace.repair_orphans` | [L82](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/neutral_trace.py#L82) |
| `neutral_trace.py::Trace.to_json` | [L100](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/provider-failover/neutral_trace.py#L100) |
