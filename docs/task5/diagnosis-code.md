# 日志诊断源码精读 · 一条诊断如何变成回归测试

[实验与结果](diagnosis.md) · [学习适配脚本](../assets/task5/run_diagnosis.py)

## 1. 从真实 HTTP 返回开始，而不是手写“成功日志”

**问题：** 如果测试只读固定 JSON，很容易把“描述了请求”误当成“请求真的执行了”。

**设计：** `_http_call` 构造 urllib Request，用 perf_counter 计时，实际访问本机服务；成功记录 status、http_status、response、latency_ms，异常也落成结构化返回。

**数据形状：**

```python
# 教学示意
turn = {
    "index": 2,
    "tool": "check_stock",
    "status": "error",
    "latency_ms": 351.3,
    "error": "TimeoutError: timed out",
}
```

错误不应从日志中消失。它既是模型诊断的依据，也是后续重放的对照。

## 2. `_trajectory` 为什么把缺陷作为显式开关

**问题：** 想证明测试能发现错误，需要能稳定重现一个有缺陷版本，再比较正确版本。

**设计：** inject_regressions=True 时跳过退款检查，库存使用较长超时且不降级；False 时查询资格、检查资格结果，再退款；库存使用较短源站预算并缓存回退。

```python
# 教学压缩版
if inject_regressions:
    process_refund(order_id)
else:
    eligibility = verify_refund_eligibility(order_id)
    if eligibility["eligible"]:
        process_refund(order_id)
```

本次是同一课程编排函数的两个分支，不是模型写了两个版本。每次调用生成一条新 trajectory，不能拿修改前的旧日志冒充修复后结果。

## 3. 诊断为什么必须引用 ID 和轮次

**问题：** 模型能写出“可能是网络抖动”这种合理但无依据的解释。

**设计：** `_validate_diagnosis` 检查 problems 非空、引用存在的 source_trajectory_id、focus_turn 在范围内，以及 R1/R2 覆盖。

**课程源码原文**：[ `_validate_diagnosis` · L324–350](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L324)

```python linenums="324"
def _validate_diagnosis(payload: dict[str, Any], sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    problems = payload.get("problems")
    if not isinstance(problems, list) or len(problems) < 2:
        raise ValueError("diagnosis must contain at least two evidence-backed problems")
    refs: set[str] = set()
    for problem in problems:
        if not isinstance(problem, dict):
            raise ValueError("problem is not an object")
        refs.add(str(problem.get("prd_ref")))
        tids = problem.get("trajectory_ids")
        turns = problem.get("focus_turns")
        if not isinstance(tids, list) or not tids or not all(tid in sources for tid in tids):
            raise ValueError(
                "problem contains an unknown trajectory reference; trajectory_ids must use only "
                + json.dumps(sorted(sources))
                + " (the source_trajectory_id values, without the ::buggy suffix)"
            )
        if not isinstance(turns, list) or not turns or not all(isinstance(value, int) for value in turns):
            raise ValueError("problem lacks concrete focus turns")
        if not all(
            any(0 <= value < len(sources[tid]["turns"]) for tid in tids)
            for value in turns
        ):
            raise ValueError("problem focus_turns contain indexes absent from every cited trajectory")
    if not {"R1", "R2"}.issubset(refs):
        raise ValueError(f"diagnosis did not cover both observed PRD violations: {sorted(refs)}")
    return problems
```


注意日志里有 `HTTP-RF-001::buggy` 和 `source_trajectory_id=HTTP-RF-001` 两种 ID。前者包含实现版本，后者用于把同一个任务在 buggy/fixed 中对齐；模型测试应引用后者。

结构校验只能防不存在的引用，不能自动证明每句诊断描述正确。还需人工阅读、独立规则或更强验证。本次只声称发现并验证了预置的两类缺陷。

## 4. 为什么让模型输出 DSL，而不是直接执行它写的 Python

**问题：** 任意生成代码难以限定能力，也难统一统计结果。

**设计：** 测试写成字典：type 决定算子，params 给参数。框架仅支持 step_present、latency_under、final_status_is。

```python
# 教学示意：这是数据，不是立即执行的代码
test = {
    "trajectory_id": "HTTP-INV-001",
    "focus_turn": 2,
    "assertion": {
        "type": "latency_under",
        "params": {"tool": "check_stock", "threshold_ms": 250},
    },
}
```

`_validate_tests` 检查测试引用、断言类型和覆盖；它不是完整的业务验证器。随后必须真的执行 `_evaluate`。

## 5. `_evaluate` 怎样把字典变成判断

**课程源码原文**：[ `_evaluate` · L303–321](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L303)

```python linenums="303"
def _evaluate(assertion: dict[str, Any], trajectory: dict[str, Any]) -> tuple[bool, str]:
    kind = assertion.get("type")
    params = assertion.get("params") or {}
    if kind == "step_present":
        tool = str(params.get("tool") or "")
        count = len(_tool_turns(trajectory, tool))
        return count > 0, f"{tool} calls={count}"
    if kind == "latency_under":
        tool = str(params.get("tool") or "")
        threshold = float(params.get("threshold_ms"))
        calls = _tool_turns(trajectory, tool)
        # A timed-out attempt is part of the operation and therefore counts.
        worst = max((float(turn["latency_ms"]) for turn in calls), default=float("inf"))
        return worst < threshold, f"{tool} max_latency_ms={worst:.3f}, threshold_ms={threshold:.3f}"
    if kind == "final_status_is":
        wanted = str(params.get("value") or "")
        actual = str(trajectory.get("final_status") or "")
        return actual == wanted, f"final_status={actual}, expected={wanted}"
    return False, f"unsupported assertion type: {kind}"
```


逐个看：

- step_present：筛出同名工具并计数，只要 count > 0。
- latency_under：取同名工具的最大 latency_ms，与阈值比较。
- final_status_is：字符串比较结束状态。

这些函数的简单性是优点：读者能直接审查评分口径。也正因如此，不能给它们附加没有实现的语义。例如存在性不含顺序，最大单次时延不含端到端时间。

## 6. 双版本重放为什么比“修复后通过”更有力

```python
# 教学示意
buggy = run_task(task, inject_regressions=True)
fixed = run_task(task, inject_regressions=False)
assert not evaluate(test, buggy)
assert evaluate(test, fixed)
```

一个永远 True 的测试，在正确版本上也会通过；必须看它在错误版本是否失败。一个永远 False 的测试能抓到错误，却也会把正确实现判错；所以两端都要测。

本次三条测试全部满足这两个条件。但错误样本仍有限，顺序反转负例能进一步暴露测试太弱。这就是为什么“测试全绿”需要附带测试覆盖范围。

## 7. 反馈循环放在哪里

学习脚本保留最多三次的诊断校验与测试生成尝试。错误会变成下一次 user 消息里的反馈，而不是静默改掉模型结果。

```python
# 教学示意
for attempt in range(3):
    candidate = generate_tests(prompt, feedback)
    records = replay_on_both_versions(candidate)
    if every_test_distinguishes_versions(records):
        break
    feedback = summarize_failures(records)
```

本次没有触发第二次尝试。脚本能重试，不等于本次实际发生了重试；日志里应按 attempt 数说话。

## 8. 如何为客服与实时对话定义自己的断言

以下是后续设计例子，不是你现有系统的已验证规则：

| 场景 | 只检查这一项不够 | 还需要检查 |
| --- | --- | --- |
| 客服操作 | 工具出现过 | 同一订单、权限通过、校验在前、结果成功 |
| 宣称成功 | 回答包含“成功” | 相同 operation_id 的真实成功回执 |
| 实时对话 | 旧请求返回了内容 | 返回时 turn_id 是否仍有效 |
| 超时降级 | cache 工具被调用 | 是否在总预算内、是否明确告知数据时效 |

先从一个已知故障写出反例，再决定断言的数据字段。不要先收集海量日志，最后才发现关键 ID 和状态没有记录。

## 源码导航：读完后回到这些函数

按职责定位，先读主路径，再补适配器。下面的行号来自本次固定版本。

| 文件 / 函数 | 行号 |
| --- | --- |
| `campaign.py::_utc` | [L49](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L49) |
| `campaign.py::_write_json` | [L53](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L53) |
| `campaign.py::_sha` | [L61](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L61) |
| `campaign.py::_free_port` | [L65](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L65) |
| `campaign.py::_backend` | [L80](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L80) |
| `campaign.py::_json_object` | [L103](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L103) |
| `campaign.py::_llm_call` | [L113](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L113) |
| `campaign.py::_http_call` | [L168](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L168) |
| `campaign.py::_trajectory` | [L209](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L209) |
| `campaign.py::_tool_turns` | [L299](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L299) |
| `campaign.py::_evaluate` | [L303](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L303) |
| `campaign.py::_validate_diagnosis` | [L324](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L324) |
| `campaign.py::_validate_tests` | [L353](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L353) |
| `campaign.py::_mcp_create_issue` | [L373](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L373) |
| `campaign.py::run` | [L415](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L415) |
| `campaign.py::main` | [L650](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/campaign.py#L650) |
| `http_service.py::Handler.log_message` | [L21](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/http_service.py#L21) |
| `http_service.py::Handler._json` | [L34](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/http_service.py#L34) |
| `http_service.py::Handler._body` | [L46](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/http_service.py#L46) |
| `http_service.py::Handler.do_GET` | [L53](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/http_service.py#L53) |
| `http_service.py::Handler.do_POST` | [L74](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/http_service.py#L74) |
| `http_service.py::main` | [L88](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter5/log-diagnosis/http_service.py#L88) |
