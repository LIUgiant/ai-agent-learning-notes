# 9-1 代码精读：从回复到可核验的轨迹

[实验结果与反例](verifier.md)

## 1 先找到主线，不从每个文件第一行读

```text
run_original.py 9-1                    我们的 DeepSeek 适配与隔离运行
  → customer_service_env.run_case()    生成真实模型轨迹
    → CustomerServiceSandbox.execute() 执行本地订单工具
  → TrajectoryVerifier.evaluate()     三层验证
  → calibration_report()              与样例预设标签对照
  → build_evidence()                  保存记录和验收条件
```

课程版本固定在 `cf7f7a8`。我们把原版 Python 与样例复制到独立学习目录，新增 DeepSeek 提供商配置，不改课程的验证规则。原版历史报告也没有覆盖。

## 2 第一个设计问题：模型一句话不够，轨迹需要什么

以下是**教学数据结构示意**，值缩短了：

```python
trajectory = {
    "messages": [{"role": "assistant", "turn": 4, "content": "已退款"}],
    "tool_calls": [{"turn": 3, "name": "refund_order",
                    "result": {"success": True}}],
    "expected_outcome": {"order_status": "refunded"},
    "final_state": {"order_status": "refunded"},
    "claims": [{"turn": 4, "text": "已退款", "supported_by": "refund_order"}],
    "promises": [{"turn": 4, "required_tool": "refund_order"}],
}
```

`messages` 是列表，其中每个 `message` 是字典。`tool_calls` 是另一张事实列表，不能靠模型在聊天里自报来生成。`final_state` 是沙箱的真实状态快照；`expected_outcome` 是测试事先约定的目标。

**为什么分开存？** 用户能看到的对话与机器真实做过的事可能不一致。分开后才有条件交叉核对。

源码：`customer_service_env.py::run_case`（214 行），`CustomerServiceSandbox`（124 行）。

## 3 第二个问题：谁真的把订单改成已退款

课程沙箱在工具分发处先检查身份，再处理退款。下面是**原代码分支的教学缩写**：

```python
if name in {"refund_order", "change_flight"} and not self.identity_verified:
    result = {"success": False, "error": "identity_not_verified"}
elif name == "refund_order":
    if self.case["fare_type"] == "nonrefundable":
        result = {"success": False, "error": "fare_nonrefundable"}
    else:
        self.state.update(order_status="refunded",
                          refund_amount=self.case["refund_amount"])
        result = {"success": True, "refund_amount": self.case["refund_amount"]}
```

模型只是请求 `refund_order`；Python 才能改 `self.state`。这也是权限门禁适合放的位置：任何措辞都不能让 `identity_verified=False` 变成 True。

教学沙箱仍有边界：例如改签分支没有完整模拟所有可选日期约束，不能直接拿去处理真实订单。

## 4 第三个问题：任务成功为什么先比状态

原版 `ResultVerifier.evaluate()` 的核心：

```python
mismatches = [
    f"{key}: expected={value!r}, actual={final_state.get(key)!r}"
    for key, value in expected.items()
    if final_state.get(key) != value
]
```

逐项比较 `expected_outcome` 和 `final_state`。假设预期 refunded，实际 confirmed，就记录一条 mismatch。列表非空则失败。没有预期字段时，代码给 `uncertain`，避免“没要求所以全对”。

注意：它只检查预先列出的字段，不会自动理解完整业务。忘了写金额验收，就不能据此声称金额也正确。

## 5 第四个问题：工具成功还要先于承诺

课程 `_precedes()` 要求：

```python
call_turn < promise_turn
```

例如 assistant 在 turn 1 说退款成功，工具在 turn 3 才成功，不能拿后面的成功给前面的错误承诺补证明。调用与宣称处在同一轮也不满足严格先后关系。

更关键的是上游 `_derive_claims_and_promises()` 必须先正确识别“有没有作出成功声明”。本次否定句反例就发生在这里：下游时序代码正确，不代表上游语义提取正确。

## 6 第五个问题：为什么既有分数又有一票否决

原版 `TrajectoryVerifier.evaluate()` 将三层返回值拼成列表：

```python
dimensions = [
    *self.result_verifier.evaluate(trajectory),
    *self.process_verifier.evaluate(trajectory),
    *self.quality_judge.evaluate(trajectory),
]
```

每项是 `DimensionResult`：维度名、层、pass/fail/uncertain、分数、证据、置信度。平均数用于观察总体质量，`critical_failures` 决定是否拒绝，`review.required` 决定是否送复核。

不要把 `review_or_accept` 理解成生产发布已经批准；它只是这个验证器的建议枚举。`eligible_as_automatic_learning_signal` 也只受本地复核规则约束，不是完整的训练数据治理系统。

## 7 怎样继续自己写

按这个顺序做一个最小版本：

1. 手写一条轨迹，只有 expected 和 final_state，实现结果核对。
2. 加 tool_calls 与 turn，检查承诺之前是否执行成功。
3. 加敏感值列表，验证明确的泄露。
4. 最后加表达质量模型裁判，保留它的证据与不确定性。
5. 给验证器写反例：否定句、缺字段、后置工具调用、被模型拒绝的攻击。

这样每增加一层，你都知道它解决哪个已发现的问题。

## 源码索引

- [订单沙箱与轨迹构建](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter9/trajectory-verifier/customer_service_env.py#L124)
- [三层验证器](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter9/trajectory-verifier/verifier.py#L266)
- [标签校准](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter9/trajectory-verifier/calibration.py#L10)
- [本地运行与下载](evidence.md)
