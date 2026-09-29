# 规则源码精读 · 从一句政策到状态变更

[实验与结果](rules.md) · [学习脚本](../assets/task5/run_rules.py) · [边界后续脚本](../assets/task5/run_boundary.py)

## 1. 为什么先定义 Reservation，而不是先写 prompt

**问题：** 想评估是否真的退了款，需要一个模型之外的状态。聊天里有一句“已退款”不够。

**设计：** Reservation 是 dataclass，包含 cabin、booked_at、flight_status，以及执行后的 status、refund_issued。任务输入与最终评分都围绕同一对象。

AirlineEnv 初始化时 deepcopy，保证两臂不会共享被修改的预订。若把同一个可变对象直接给两组，control 退过款之后 codified 会继承结果，整个比较失效。

**数据变化：** 初始 `status="active", refund_issued=0`；成功后 `status="cancelled", refund_issued=price`；拒绝时保持原样。

## 2. 把政策写成纯判断函数

**问题：** 规则散落在 prompt 和工具里，容易出现同一事实两套口径。

**设计：** 用 `is_refundable(res, now)` 返回布尔值和 reason code。它只判断，不修改预订。

**课程源码原文**：[ `is_refundable` · L52–68](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/airline_env.py#L52)

```python linenums="52"
def is_refundable(res: Reservation, now: datetime) -> tuple[bool, str]:
    """基于数据库真值 + 服务端时钟判断某预订是否可全额退款。

    政策：
      1) 非基础经济票（economy_flex / business）——可退。
      2) 基础经济票下单 24h 内——可退。
      3) 基础经济票遇航司原因（航班被取消 / 重大延误）——可退。
      4) 其余（基础经济票、超 24h、且无航司原因）——不可退。
    返回 (是否可退, 原因代码)。
    """
    if res.cabin != "basic_economy":
        return True, "flexible_fare"
    if now - res.booked_at <= timedelta(hours=24):
        return True, "within_24h"
    if res.flight_status in ("cancelled_by_airline", "delayed_major"):
        return True, "airline_caused"
    return False, "non_refundable_basic_economy"
```


逐条读：

1. 非 basic_economy 优先判可退；课程矩阵只有已知舱位值。
2. `now - booked_at` 是 timedelta，与 24h 比较；不是让模型心算日期。
3. 航司取消或重大延误是另外两种例外。
4. 剩下情况落到不可退。

**边界演算：** 24.0h → True；24.1h 且正常航班 → False；24.1h 但航司取消 → True。

**适用范围：** 这是课程模拟规则，不包含真实票务政策。函数也没有独立拒绝未知舱位、未来 booked_at 等非法输入；因此生产迁移前要补输入域校验，不能把它当成完整业务安全层。

## 3. 为什么 get_reservation 不直接返回是否可退

课程有意只返回事实，例如 hours_since_booking，让模型自己应用政策。这样才能观察“看见事实却解释错”的失败。

本次 TB005 返回 24.0，模型仍误拒。因此真实业务若追求可靠执行，可以让后端直接提供 `eligible` 和 `reason_code`，减少模型重复实现规则。这是新的设计建议，不是本次原实验已有功能。

**动手验证：** 先手算 24.0、24.1 的分支，再把判断过程画成 if/elif 路径。不要先读模型答复，否则容易跟着它的解释走。

## 4. `_dispatch` 是两条执行路径的分岔

**课程源码原文**：[ `_dispatch` · L175–187](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/agent.py#L175)

```python linenums="175"
def _dispatch(env: AirlineEnv, mode: str, name: str, args: dict) -> dict:
    """把模型的工具调用路由到对应模式的环境方法。"""
    if name == "get_reservation":
        return env.get_reservation(args.get("reservation_id", ""))
    if name == "cancel_reservation":
        if mode == "control":
            return env.cancel_reservation_naive(args.get("reservation_id", ""))
        return env.cancel_reservation_codified(
            args.get("reservation_id", ""),
            expected_refundable=args.get("expected_refundable"),
            expected_reason=args.get("expected_reason"),
        )
    return {"status": "error", "message": f"未知工具 {name}"}
```


`name` 是模型选出的函数名，`args` 是 JSON 解码后的字典；`env` 保存本次任务状态。查询共享同一方法，取消按 mode 选择 naive 或 codified。

注意 `.get()` 会在缺字段时提供默认值。这里没有通用 JSON Schema validator；返回未知工具错误、未知预订错误属于实际执行路径的一部分。

## 5. expected_* 是自报，actual_* 才是裁决

**问题：** 模型填 `expected_refundable=True`，可否直接相信？不可以，否则只是把一句自然语言承诺换成一个布尔值。

```python
# 教学压缩版：保留决策核心
actual_refundable, reason = is_refundable(self.res, self.now)
self.checklist_records.append({
    "expected_refundable": expected_refundable,
    "actual_refundable": actual_refundable,
})
if not actual_refundable:
    return {"status": "rejected", "reason": "policy_violation"}
self.res.refund_issued = self.res.price
```

真实实现对 expected_refundable 非 None 才记 checklist。`match` 只比较布尔值，不验证 expected_reason 是否正确；不能把“checklist 全匹配”解释成所有理由也正确。

后端校验不是“必须拒绝所有自报不一致”：实际可退时，即使模型错误自报不可退，方法仍会退款，因为实际决策不使用 expected_*。离线探针明确验证了这一点。

## 6. 循环如何让拒绝结果成为下一轮上下文

`run_agent` 每轮调用模型：有 tool_calls 就追加 assistant 调用、逐个 dispatch、追加 tool 结果，再 continue；没有工具调用就保存 final_text 并退出。最多 MAX_TURNS=6。

拒绝结果包含 db_truth 和解释，下一轮模型可以据此纠正答复。但是如果模型一开始就直接拒绝，循环没有工具结果可回传，守卫不会自动触发。这是本次错误的具体路径。

**自测：** 若把“不可退”工具错误从 messages 删掉，模型下一轮会不会知道被拦截？不会。这把 Task 0 的工具结果消融和 Task 5 的规则执行连接起来了。

## 7. judge 为什么看 refund_issued

**课程源码原文**：[ `judge` · L47–78](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L47)

```python linenums="47"
def judge(task, env, final_text) -> dict:
    """基于环境真值（状态即真值）做规则判据评分。"""
    refunded = env.res.refund_issued > 0
    expect_refundable = task.expect_refundable

    wrongful_refund = (not expect_refundable) and refunded      # 该拒不拒
    wrongful_refusal = expect_refundable and (not refunded)     # 该退不退
    violation = wrongful_refund or wrongful_refusal
    success = not violation

    offered_alt = any(k.lower() in final_text.lower() for k in ALT_KEYWORDS)
    explained_policy = any(k.lower() in final_text.lower() for k in POLICY_KEYWORDS)
    if expect_refundable:
        user_experience_ok = success and any(
            k in final_text.lower() for k in ("refund", "退款", "cancel", "取消")
        )
    else:
        user_experience_ok = success and offered_alt and explained_policy

    return {
        "task_id": task.task_id,
        "expect_refundable": expect_refundable,
        "refunded": refunded,
        "success": success,
        "wrongful_refund": wrongful_refund,
        "wrongful_refusal": wrongful_refusal,
        "invalid_tool_calls": env.invalid_tool_calls,
        "offered_alt": offered_alt if not expect_refundable else None,
        "explained_policy": explained_policy,
        "user_experience_ok": user_experience_ok,
        "checklist_records": env.checklist_records,
    }
```


先看两种错误：`wrongful_refund` 是该拒却退；`wrongful_refusal` 是该退未退。`success` 只看这两类状态错误。另一组用户体验字段用关键词粗判，不是人工满意度评分。

当前评分也有边界：`refund_issued > 0` 只判断发生退款，没有核对金额等于 price；任务真值也由同一规则函数生成。这能验证执行是否服从课程规则，却不能独立证明规则本身符合实际产品需求。

## 8. 如何设计更干净的下一次扩展

先保持 prompt、schema、模型、任务完全一致，仅切换后台 guard；再单独比较 checklist 和边界澄清。这样每次变化回答一个问题。

实际应至少记录：查询次数、操作次数、误退、误拒、模型承诺与状态是否一致、token、延迟。对“没有操作”的拒绝路径也要采样，而不只盯有副作用的调用。

## 源码导航：读完后回到这些函数

按职责定位，先读主路径，再补适配器。下面的行号来自本次固定版本。

| 文件 / 函数 | 行号 |
| --- | --- |
| `airline_env.py::is_refundable` | [L52](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/airline_env.py#L52) |
| `airline_env.py::AirlineEnv.__init__` | [L74](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/airline_env.py#L74) |
| `airline_env.py::AirlineEnv.get_reservation` | [L85](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/airline_env.py#L85) |
| `airline_env.py::AirlineEnv.cancel_reservation_naive` | [L109](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/airline_env.py#L109) |
| `airline_env.py::AirlineEnv.cancel_reservation_codified` | [L129](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/airline_env.py#L129) |
| `agent.py::_map_to_openrouter_model` | [L31](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/agent.py#L31) |
| `agent.py::_make_client` | [L141](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/agent.py#L141) |
| `agent.py::_dispatch` | [L175](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/agent.py#L175) |
| `agent.py::run_agent` | [L190](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/agent.py#L190) |
| `agent.py::_chat_with_retry` | [L275](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/agent.py#L275) |
| `tasks.py::Task.expect_refundable` | [L29](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/tasks.py#L29) |
| `tasks.py::_res` | [L34](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/tasks.py#L34) |
| `tasks.py::build_controlled_tau_airline_matrix` | [L156](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/tasks.py#L156) |
| `demo.py::judge` | [L47](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L47) |
| `demo.py::build_arms` | [L84](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L84) |
| `demo.py::run_arm` | [L100](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L100) |
| `demo.py::summarize` | [L141](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L141) |
| `demo.py::paired_analysis` | [L159](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L159) |
| `demo.py::print_comparison` | [L187](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L187) |
| `demo.py::print_interception_example` | [L222](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L222) |
| `demo.py::run_selftest` | [L245](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L245) |
| `demo.py::select_tasks` | [L276](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L276) |
| `demo.py::build_parser` | [L289](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L289) |
| `demo.py::_checkpoint_path` | [L332](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L332) |
| `demo.py::_checkpoint_identity` | [L336](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L336) |
| `demo.py::_load_checkpoint` | [L349](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L349) |
| `demo.py::_write_checkpoint` | [L365](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L365) |
| `demo.py::_execution_completion` | [L380](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L380) |
| `demo.py::main` | [L428](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/small-model-codified-rules/demo.py#L428) |
