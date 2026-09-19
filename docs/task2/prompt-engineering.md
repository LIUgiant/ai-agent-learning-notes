# 提示词消融实验 · 语气、组织、工具描述各值几分？

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](prompt-engineering-code.md)：Tau-Bench 客观奖励、三个维度的注入实现、冻结协议与检查点、litellm 多厂商层。

[本次结果](evidence.md#prompt-engineering) · [学习运行脚本](../assets/task2/run_prompt_engineering.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/prompt-engineering)

## 这个实验回答什么问题

系统提示词的三个要素——**语气风格**、**信息组织**、**工具描述**——对 Agent 任务完成率的影响分别有多大？把每个要素单独"降解"，在客观评测基准上看成功率掉不掉。

## 基准：Tau-Bench 航空客服

课程 vendored 了 Tau-Bench：Agent 扮演航空客服，工具直接操作模拟环境（订单/用户数据库），**奖励由环境终态计算**（订单改对了没有），不由模型自述或 LLM 打分判定。对话的"顾客"侧也是真实 LLM 调用（用户模拟器）。

## 六个臂

```text
baseline      专业中立语气 + 结构化规则手册 + 完整工具描述
tone_trump    Trump 夸张风格（前置指令块，原文不动）
tone_casual   大量 emoji/俚语的休闲风格
wiki_random   同一套规则、预生成的乱序平铺版（无标题层次）
no_tool_desc  工具 schema 保留但全部 description 置空
all_ablations casual + 乱序 + 空描述 三层叠加
```

三个维度都是**单一变量**：语气只加前置块不改知识、乱序 wiki 信息量恒等、空描述保留参数名与类型。

## 与课程原版的差异

- **模型**：书方 Kimi K3（temperature 1.0，推理模型）→ DeepSeek（`deepseek-flash`，thinking 关闭，temperature 0.3 降方差）；**用户模拟器也换成 DeepSeek**（课程对非 Kimi 用户模拟器自动用 temperature 0）；
- **规模**：任务 10 → 4（airline test split 前 4 题），六臂不变；
- **传输层**：课程经 litellm（`custom_llm_provider`）；学习版沿用 litellm 并在其上打 thinking 关闭补丁；
- **协议**：自拼学习协议（协议校验按学习协议通过），冻结协议里 gpt-4o-mini → kimi-k3 的凭据修正记录见其 `transport_amendment`。

## 先想清楚再去看数字

1. 语气好的道歉但没改订单，reward 是多少？（客观奖励为什么适合测语气）
2. 乱序 wiki 和删一半规则，为什么是两个不同的变量？
3. n=4 的任务量，能支撑"某维度有效/无效"的结论吗？看结果时要先看哪两道题？
