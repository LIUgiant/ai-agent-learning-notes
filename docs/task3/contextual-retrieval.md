# 上下文感知检索实验 · 给每个文本块发一张"身份证"

!!! tip "先跑实验，再跟着代码走一遍"
    [进入本实验的逐步源码教程](contextual-retrieval-code.md)：前缀生成 prompt、双索引对照、本地 Qwen3-Embedding 编码、RRF 混合、六方法指标。

[本次结果](evidence.md#contextual-retrieval) · [学习运行脚本](../assets/task3/run_contextual_retrieval.py) · [课程项目](https://github.com/bojeli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter3/contextual-retrieval)

## 这个实验回答什么问题

把文档切块后，每一块都成了"孤儿"——《宪法》序言里的一句"本宪法以法律的形式确认了中国各族人民奋斗的成果"，单看这句话既不知道自己来自哪份文档、属于哪一章，BM25 和向量检索都容易把它和别的"法律成果"混在一起。**Anthropic 的 Contextual Retrieval** 方案：给每个块用 LLM 生成一段"上下文前缀"（来自哪份文档、哪一条、讲什么），前缀 + 原文一起进索引。

问题：前缀对 BM25、稠密向量、混合检索分别有多少提升？索引成本增加多少？

## 六方法对照

```text
            plain（原文索引）      contextual（前缀+原文索引）
BM25        plain_bm25            contextual_bm25
稠密向量    plain_dense           contextual_dense    （本地 Qwen3-Embedding-0.6B）
混合(RRF)   plain_hybrid          contextual_hybrid
```

指标 recall@1/3/5 与 MRR，15 条标注查询（金标 chunk 已知）。**同一批 chunk、同一批查询**，唯一变量是索引文本有没有前缀。

## 一个前置事实：document_store 的来源

课程仓库不带 document_store.json（原版由需要检索服务的索引流水线生成）。书方已通过战役的 evidence.json 保留了全部 22 个 chunk 的**原文与文档标题**，学习版据此无损重建（chunk 内容与书方证据逐字节相同、与评测集金标 ID 精确一致）。前缀**全部由 DeepSeek 现场生成**——"手写前缀的结果不算数"的课程门槛因此原样满足。

## 与课程原版的差异

- **前缀模型**：doubao → DeepSeek（`deepseek-flash`）；语料（宪法 + 检察官法）、chunking、查询集、BM25/稠密/混合全部课程原样；
- **稠密检索**：与书方同款本地模型 Qwen/Qwen3-Embedding-0.6B（CPU）；
- **规模**：书方全量（2 文档 22 chunk 15 查询），学习版同规模不抽样；
- pricing 置零（未配置 DeepSeek 价格；索引成本以 token 用量原样记录）。

## 先想清楚再去看数字

1. 前缀对 **BM25** 和**稠密向量**哪个帮助更大？（提示：BM25 靠字面词，前缀塞进了"宪法""序言"这些原本不在块里的词）
2. 索引阶段 22 次 LLM 调用（每块一次），检索阶段零 LLM——这笔成本什么时候回本？
3. RRF 混合把两个排序融合，前缀的收益会被混合"平均"掉还是叠加？
