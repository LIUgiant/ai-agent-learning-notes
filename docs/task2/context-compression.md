# 上下文压缩实验 · 不压缩会怎样，压多少才够？

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](context-compression-code.md)：六策略地图、摘要 prompt 逐个拆、溢出判定口径、windowed 的标记与找回、缩尺设计论证。

[本次结果](evidence.md#context-compression) · [学习运行脚本](../assets/task2/run_context_compression.py) · [课程项目](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter2/context-compression)

## 这个实验回答什么问题

Agent 做研究任务要反复搜索，工具结果不断堆进历史。**不压缩**终会撑爆上下文窗口；那**怎么压**——逐页摘要、合并摘要、按问题聚焦、带引用、还是满了才压旧的？六种策略跑同一个任务，比谁能活下来、花多少 token、丢不丢关键信息。

## 任务与策略

任务（书方同款）：研究 OpenAI 全部联合创始人的**现任职务**——先搜全名单，再逐人搜索，最后汇总报告。这个任务天然多轮、天然堆上下文。

```text
no_compression   原文直接进历史（对照组，预期爆窗）
individual       每页立即摘要（300 tok/页）再拼接
combined         全部页拼接后一次摘要
context_aware    按当前 query 聚焦摘要（还带最近 3 次搜索的上下文）
citations        按 query 摘要 + [1][2] 内联引用 + 来源清单
windowed         原文进历史；上下文超 80% 阈值时把旧工具消息批量摘要（[COMPRESSED] 标记防重压）
```

## 学习缩尺：128K → 16K

书方的溢出演示靠真实网页堆到 128K 预算的 80%（百万级 token 一次跑）。学习版两个变量同步缩放：合成语料（课程 mock 的 2024 事实快照 + 每页 4K 字符噪声，单次搜索约 2.5K tokens）配 16K 预算——"几轮积累→溢出"的节奏与书方同量级，**阈值比较、80% 触发、no_compression 死亡分支全部是课程原逻辑**。合法性论证见[源码精读第 7 节](context-compression-code.md#7)。

## 先想清楚再去看数字

1. no_compression 死掉时它的**总 token 反而可能最少**（死得早）——比较成本时该看哪一列？
2. combined 两次越过 80% 阈值为什么没死？（告警和死亡分支分别是给谁的）
3. windowed 的"压缩比"指标显示 1.10（没压缩？）——它的真实压缩量去哪了看？
