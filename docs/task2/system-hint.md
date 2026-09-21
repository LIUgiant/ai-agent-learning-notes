# System-Hint 实验 · 状态栏信息值几轮对话？

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](system-hint-code.md)：正式战役 run_experiment_2_8.py 的 20 个函数逐个讲 + 教学 Agent 的精选函数。

[完整证据与复现](evidence.md#system-hint) · [学习运行脚本](../assets/task2/run_system_hint.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/system-hint)

## 这个实验回答什么问题

Agent 的"糊涂失败"——忘记时间、重复重试、漏做组件、看不懂错误、认错环境——有多少能用**状态栏信息**（system hints）解决？五种 hint（时间戳、工具计数、TODO 列表、详细错误、系统状态）逐个开/关、再全部叠加，在冻结的对照战役里比任务完成率。

## 设计

六套件各考一种 hint，每套件取冻结协议前 3 案例（书方 5），同案例的 enabled/disabled 臂共享**完全相同**的沙箱与用户提示词，臂序按案例奇偶交替（消除位置效应）：

```text
timestamps    两份带时间戳的记录选更晚的（raw 只给数据 / guided 另给用法指引，三臂）
tool_counter  主资源永远失败，需计数提醒后转 fallback（重试 ≤3 次才算过）
todo_list     交付 N 个规定文件名的 artifact，内容恰为规定 token
detailed_errors 读被改名的文档，须从结构化错误恢复出真文件
system_state  在伪造主机信息上选对包管理器安装
combined      以上五组件拼成一个事故处理流程
```

评分**不看模型自述**：从工具事件序列 + 沙箱终态客观判定（文件逐个打开比对内容、submit_result 的参数、重试次数上限）。

**与课程原版的差异**：Kimi K3（temperature 1.0）→ DeepSeek（`deepseek-flash`、0.3 降方差、thinking 关闭）；每套件 3 案例（65 run → 39 run）；其余零改动。

## 看结果前先想清楚

1. 五种 hint 有三种注入通道（任务前缀/工具结果/末尾状态消息），为什么不全放系统提示词里？（联想 [KV Cache 实验](kv-cache.md)）
2. 单组件任务 vs 五组件复合任务，hint 的价值在哪种里更明显？
3. "任务全做对但没调 submit_result"算 complete 吗？算 objective_pass 吗？

## 运行结果

39 run，145,596 tokens。课程验收门槛 8/9 过（唯一失败项见下，且失败本身是发现）：

| 对照 | enabled | control | 轮数（enabled vs control） | supported |
| --- | ---: | ---: | --- | --- |
| timestamps_raw | 3/3 | 2/3 | 2.0 vs 2.7 | None（预注册无方向） |
| timestamps_guided | 3/3 | 2/3 | 2.0 vs 2.7 | True |
| tool_counter | 3/3 | 3/3 | 3.0 vs 3.0 | False |
| todo_list | 3/3 | 3/3 | 5.3 vs 2.0 | False |
| detailed_errors | 3/3 | 3/3 | 3.0 vs 4.0 | False |
| system_state | 3/3 | 3/3 | 3.0 vs 3.0 | False |
| **combined** | **3/3** | **0/3** | **4.7 vs 8.0** | **True** |

`campaign_complete=False` 的唯一原因：3 个 **disabled×combined** 格烧完 8 轮预算也没调用 submit_result（`all_preregistered_runs_complete=False`）。

## 分析

- **combined 是唯一的大效应**：开全部 hint 时 3/3 通过、约 5 轮完成；关掉时 3 个案例全部 8 轮耗尽仍未提交。翻 `combined__all-01__disabled` 的轨迹末尾：模型在 `inspect_system` 之后把**记录名（oak/pine）当文档名**去 `read_document`——五组件之间的混淆正是 TODO 列表要防的失败模式。这三个 incomplete 格本身就是"无 hint 完不成复合任务"的直接证据，不是实验缺陷；
- **单组件套件全部 3/3 vs 3/3**：任务太简单时 hint 没有发挥空间（3 个案例也分辨不出小差异）。hint 的价值密度随任务组件数上升——和 [Agentic RAG](../task3/agentic-rag.md) 里"迭代检索的价值随复杂度上升"是同一条曲线；
- **todo_list 的预注册判据如实判 False**：通过数相同（3/3）但 enabled 臂轮数更多（5.3 vs 2.0——建 TODO 本身花轮数）。判据"通过更多**且**轮数不升"没满足就不支持，哪怕直觉上 TODO 帮了忙——**预注册口径防止事后放宽**；
- timestamps_guided 3/3 vs 2/3：小样本下与 raw 分不出差；书稿的历史声明（时间感 19→49 分）在冻结协议里被明确标注"不可直接复现"；
- 与书方 Kimi K3 战役（65 run 全 complete）结构不同：**不同模型在同套件下的完成度不同**——K3 无 hint 也能在预算内提交，DeepSeek 不能。这是观察不是缺陷。

**边界**：3 案例/套件无统计功效；单组件差异需要更难案例（如 fallback 也间歇失败）才能显现，本次未扩展。
