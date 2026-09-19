# System-Hint 实验 · 状态栏信息值几轮对话？

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](system-hint-code.md)：五种 hint 的注入位置、教学 Agent 的工具亮点、战役的客观评分与检查点纪律。

[本次结果](evidence.md#system-hint) · [学习运行脚本](../assets/task2/run_system_hint.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint)

## 这个实验回答什么问题

Agent 的"糊涂失败"——忘记时间、重复重试、漏做组件、看不懂错误、认错环境——有多少能用**状态栏信息**（system hints）解决？五种 hint（时间戳、工具计数、TODO 列表、详细错误、系统状态）逐个开/关、再全部叠加，在冻结的对照战役里比任务完成率。

## 两层代码：教学 Agent 与正式战役

- **agent.py（教学）**：带真实文件/shell/代码执行工具的 SystemHintAgent，五个开关可玩，`main.py` 提供 preview/interactive/demo 模式。hint 作为**每轮末尾的临时 user 消息**注入（不进历史，不毁前缀缓存——与 [KV Cache 实验](kv-cache.md)的 dynamic_system 反面互为注脚）；
- **run_experiment_2_8.py（正式）**：自成一体的冻结战役——确定性沙箱工具、从工具事件与文件状态客观评分、每 run 独立沙箱、臂序交替、逐消息检查点。书方 Kimi K3 战役 65 run 全预注册。

## 六个套件各考一种 hint

```text
timestamps    两份带时间戳的记录，选时间更晚的（raw 只给数据 / guided 另给用法指引）
tool_counter  主资源永远失败，需计数提醒后转 fallback（重试 ≤3 次才算过）
todo_list     交付 N 个规定文件名的 artifact，内容恰为规定 token
detailed_errors 读一份被改名的文档，须从详细错误恢复出真文件
system_state  在伪造主机信息（OS/包管理器）上选对安装方式
combined      以上五组件拼成一个事故处理流程
```

## 与课程原版的差异

- **模型**：Kimi K3 → DeepSeek（`deepseek-flash`，thinking 关闭；书方 temperature 1.0 是推理模型被迫取值，学习版取 0.3 降方差）；
- **规模**：每套件前 3 个案例（65 run → 39 run），案例内容与沙箱与书方完全相同；
- **其余零改动**：`run_one`/`summarize`/`condition_order`/评分/验收全是课程原代码。

## 先想清楚再去看数字

1. 五种 hint 有三种注入通道（任务前缀 / 工具结果 / 末尾状态消息），为什么不全放系统提示词里？
2. 单组件任务 vs 五组件复合任务，hint 的价值在哪种里更明显？
3. "任务全做对但没调 submit_result"算 complete 吗？算 objective_pass 吗？（提示：评分与协议完成度是两个口径）
