# 运行证据与结果

## 本次运行信息

- 运行目录：`learning/task1/runs/20260916T154639Z`（UTC 时间戳）。
- 模型：`deepseek-v4-flash`；实际请求关闭 thinking；15 次真实调用，总 usage 为 **4109 tokens**。
- 数据：人工客服 / 实时对话案例 + 课程自带英文检索语料，没有使用私人业务资料。
- 每个模型条件仅一次；结论只适用于本次观察，不报告普遍成功率。
- [完整请求与响应证据](../assets/task1/evidence.json) · [SHA-256](../assets/task1/evidence.sha256) · [独立审计](../assets/task1/audit.json)

## 上下文对照 {#context}

| 条件 | 上下文估计 tokens | 正确字段 / 3 | 观察 |
| --- | ---: | ---: | --- |
| 完整 | 664 | 3/3 | 三项保留 |
| 末尾 500 字符 | 78 | 1/3 | 退款与升级码缺失，返回 null |
| 通用摘要 | 90 | 3/3 | 三项保留 |
| 问题相关摘要 | 129 | 3/3 | 三项保留 |

估计使用 cl100k 分词，不等于 DeepSeek 精确 token 数。长度基线是课程格式化后的 full 文本；通用摘要 90、问题摘要 129，二者都没有丢失三项事实。本次不能得出“问题相关摘要一定更好”。

**压缩短，不代表单次调用更省**：完整组回答消耗 748 tokens；通用摘要先消耗 814，再回答 170，共 984；问题摘要先消耗 942，再回答 220，共 1162。摘要复用多轮时才可能摊薄这笔额外成本，本次未测复用收益。

本例没有触及模型真实窗口上限，验证的是组织与信息保留，不是最大窗口或 KV Cache 性能。

## 长期记忆对照 {#memory}

| 条件 | 模型结果 | 判断 |
| --- | --- | --- |
| 宽泛提取 prompt | Chinese / code-first / 临时位置 null | 本例已正确遵守不保存临时位置 |
| 严格长期偏好 prompt | 同上 | 未观察到优于宽泛组的差别 |
| 新会话不加载记忆 | language、style 都为 null | 正确承认缺失，但无法个性化 |
| 新实例从文件加载记忆 | Chinese / code-first | 恢复已保存偏好 |
| 按同一 ID 更新后重载 | Chinese / diagram-first | 新偏好生效，无重复记录 |

存储检查：记录 ID 可重载、更新后只有一条记录、临时工位 B7 未写入长期记忆。模型提取后有固定夹具准入检查，写入与纠正由学习脚本控制；不等于已验证自主后台记忆系统。

## BM25 检索参数 {#retrieval}

5 条课程标注查询，10 篇课程文档。下表为默认 k1=1.5、b=0.75：

| top-k | 平均 Recall@k | 平均 Precision@k |
| --- | ---: | ---: |
| 1 | 0.70 | 0.80 |
| 3 | 0.80 | 0.33 |
| 5 | 0.80 | 0.20 |

另外分别只改 k1=0.7（b 不动）、只改 b=0（k1 不动），指标未变。原始运行中还保留了一组同时修改 k1/b 的探索结果；正式解释使用审计中的单变量对照。

`cat` 原查询无命中；人工扩展 `cat kitten feline` 后命中 doc_7、doc_8。这是词面覆盖改善，不能当作向量语义检索效果。

## RAG：事实、格式、引用分别看

| 条件 | 三项已知事实 | 缺失电话 | JSON 格式 | 引用检查 |
| --- | --- | --- | --- | --- |
| 不检索 + 严格 prompt | 0/3，全部 null | null | 通过 | 空引用，不算证据覆盖成功 |
| top-1 + 严格 prompt | 1/3，仅重连次数 | null | 通过 | 错引 T42 工单 ID |
| top-3 + 严格 prompt | 3/3 | null | 通过 | 带方括号的文档 ID；原样匹配失败，去括号后匹配通过 |
| top-3 + 宽泛 prompt | 人工复核 3/3 | 文字说明未提供 | **未按 JSON 返回** | 文字来源描述，没有规范 ID 列表 |

最后一组的原始机器字段检查全为 false，是因为没有解析到 JSON，**不是事实全错或发生幻觉**。独立审计记录了这一差异。去括号规则也单独记录，保留原始严格结果，没有悄悄改评分。

结论：检索足够的相关文档有助于覆盖答案；生成端仍可能违反结构或引用约定。不能把“请求成功”当作完整任务成功。

## 怎样复现 {#source}

[下载运行脚本](../assets/task1/run_learning.py) · [下载审计脚本](../assets/task1/audit_learning.py)

将它们放进课程仓库的 `learning/task1/`，使用已安装 `openai`、`python-dotenv`、`tiktoken` 的项目虚拟环境，根目录 `.env` 配置 DeepSeek。真实重跑会产生 API 费用；审计只运行本地检索与结果复核。

```bash
.venv/bin/python learning/task1/run_learning.py
# 用上一步打印的实际目录替换 <run-dir>
.venv/bin/python learning/task1/audit_learning.py <run-dir>
```

每次新建 UTC 时间戳目录，不覆盖之前的证据。课程组件的 SHA-256 已记录在 evidence.json；压缩实验只通过适配层设置 DeepSeek 配置与请求记录，不修改课程源文件。

| 阅读入口 | 设计职责 |
| --- | --- |
| `run_learning.py` context 段 | 生成四组上下文，固定问题和逐字段评分 |
| `compression_strategies.py::compress_search_results` | 选择压缩策略并调用对应摘要方法 |
| `run_learning.py` memory 段 | 提取对照、准入、持久化、重新加载与纠正 |
| `memory_manager.py::NotesMemoryManager` | 管理记忆 ID、文件和上下文格式 |
| `cli.py::build_engine` | 组装语料、倒排索引和 BM25 参数 |
| `bm25_engine.py::SparseSearchEngine.search` | 检索并输出文档 ID、分数与文本 |
| `audit_learning.py` | 单变量检索复核，分离 JSON / 引用 / 事实判断 |

## 下一步，而不是本次已完成项

扩大测试问题数量；增加中文分词与知识库过滤；运行稠密/混合检索；把记忆提取接入后台生命周期；用真实任务测量上下文窗口与摘要复用成本。当前记录只覆盖 Task 1 的三条核心学习主线。

## 本地验证

课程 BM25 `test_engine.py` 全部通过；网站严格构建通过。实验原始证据与独立审计分别保存，审计文件记录原始证据哈希。
