# 9-3 代码精读：学习循环与业务循环分开

[实验结果](prompt-evolution.md)

## 1 从两个循环理解整个目录

```text
外层：demo.main() 学习实验
  初始评测 → 失败诊断 → 生成补丁 → 候选评测 → 发布门禁 → 人工版对照
                   ↓
内层：airline_env.run_agent() 每一题的业务循环
  请求模型 → 执行工具 → 把结果回传 → 再请求模型 → 得到回复
```

外层修改“以后怎么服务”；内层执行“这一位乘客的请求”。混在一起容易让模型在失败时当场改规则给自己放行，所以代码拆成不同职责。

## 2 evaluate.py：怎样避免“没转人工就算正确”

以下是**原版分支的教学缩写**：

```python
if should_transfer:
    correct = transferred
elif transferred:
    correct = False
else:
    judge = _judge_handled(user, rubric, final_text)
    correct = judge["handled"]
```

先看测试期望是否转接，再看工具记录是否真的转接，最后判断回复是否实质处理问题。三种信息来自不同地方：案例标签、执行日志、模型裁判。

B2 正是最后一支：没有转接，但裁判认为还没有解释改签政策。只统计 transfer 次数会把它误算成功。

局限也写在这里：应转接场景主要检查 transferred，没有完整验证转给谁、是否传递必要摘要或何时响应；生产系统要继续补。

## 3 learning_signal.py：把失败变成能修改的对象

`diagnose_failures()` 遍历每个评测结果，通过 `case_dimensions()` 形成三维诊断，收集失败 ID 与证据，生成一个 dict。

**教学简化示意：**

```python
signal = {
    "scope": "system_prompt.transfer_policy",
    "source_case_ids": ["B1-不可退票要退款", "B2-要求免改签费"],
    "dimensions": {
        "rule_compliance": [],
        "task_resolution": [{"case_id": "B1-不可退票要退款", "evidence": "过度转接"}],
        "compliant_flexibility": [{"case_id": "B1-不可退票要退款", "evidence": "未提供合规替代"}],
    },
}
```

为什么带 `scope`？把“改全篇 Prompt”收窄到“改转接策略”。为什么保留 ID？之后可以追溯是哪几条轨迹支持了这个变更。

**与 9-1 的关系要说准确：** 本实验没有直接读取我们 9-1 的报告；它从自己的航空客服评测派生同名三维学习信号。二者是概念衔接，不是已接通的数据管道。

## 4 coding_agent.py：模型只提 edits，Python 才写文件

Coding Agent 返回工具参数：

```json
{"edits":[{"old_str":"待替换的原文","new_str":"新的规则"}],"rationale":"为什么改"}
```

原版 `_apply_one()` 的核心：

```python
count = content.count(old_str)
if count == 0:
    return content, "old_str 在文件中未找到"
if count > 1:
    return content, "old_str 不唯一"
return content.replace(old_str, new_str, 1), None
```

精确匹配失败就反馈模型重试。它避免改错段落，但**不能证明新规则正确**；语义与回归问题留给后面的评估。

`optimize_prompt()` 保存 before/after、diff、edits、rationale。实际写入隔离运行目录的 `runtime/system_prompt_working.txt`，不写稳定文件。

本次只提交了一次工具编辑调用，但“最小”主要是系统提示要求和审计目标，代码没有强制计算最少字符修改。不要把“小改动”当成形式化保证。

## 5 release_gate.py：模型不能自己说通过就通过

原版 `evaluate_release_gate()` 由 Python 检查：

```python
checks = {
    "patch_is_nonempty": bool(manifest["diff"].strip()),
    "source_cases_are_recorded": bool(manifest["source_case_ids"]),
    "holdout_did_not_regress": holdout_after >= holdout_before,
    "boundary_improved": boundary_after > boundary_before,
    # 另有 edits 的结构检查，见完整源码
}
```

读这段时把数字代入：保留集 5→5，边界集 0→3，来源与补丁均有，得到 canary 建议。它并不调用部署接口。

也应看到源码尚未做的事：没有强制 edits 只改允许的转接段落，没有将来源 ID 与权威案例清单逐项核验，也不是逐案例无回退门槛。本页展示的是教学实现，生产化要补这些约束。

## 6 如果自己从零写，先实现哪五个函数

|顺序|函数|输入 → 输出|先解决的问题|
|---|---|---|---|
|1|evaluate_case|Prompt、案例 → 行为与判分|知道哪里失败|
|2|diagnose_failures|评测结果 → 带 ID 的诊断|知道要改哪一条策略|
|3|optimize_prompt|原文、诊断 → edits|提出可审计修改|
|4|evaluate_prompt|候选、固定测试集 → 新成绩|知道改善有没有代价|
|5|evaluate_release_gate|前后成绩、manifest → 建议|不给模型自批权限|

动手验证：暂时把“明确要求人工也不转接”写入候选，先预测 H4 会怎样，再跑该题。即使普通争议成绩增加，关键升级路径退步也应阻止发布。不要修改稳定版。

## 原版源码入口

- [评测器 evaluate.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter9/prompt-auto-optimization/evaluate.py#L50)
- [学习信号 learning_signal.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter9/prompt-auto-optimization/learning_signal.py#L62)
- [精确编辑 coding_agent.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter9/prompt-auto-optimization/coding_agent.py#L82)
- [发布门槛 release_gate.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter9/prompt-auto-optimization/release_gate.py#L23)
