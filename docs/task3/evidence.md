# Task 3 运行证据与结果

## 本次运行信息

- 实验日期：2026-09-19；课程仓库提交 `cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c`。
- 写手/答题模型 `deepseek-flash`（thinking 关闭）；独立评审 `qwen3.7-plus`（DashScope，跨厂商）；检索/编码用本地 Qwen3-Embedding-0.6B（CPU）。
- 运行目录：`learning/task3/runs/<实验>/<UTC 时间戳>/`（课程侧 validation/latest.json 已重定向至学习目录，书方规范证据未触碰）。
- 每条件规模为学习版（详见各节），结论只适用于本次观察；书方历史验收不冒认为本人结果。
- [记忆四模式证据](../assets/task3/memory-modes-evidence.json) · [Agentic RAG 证据](../assets/task3/agentic-rag-evidence.json) · [上下文检索证据](../assets/task3/contextual-retrieval-evidence.json)（各含 SHA-256 同名 .sha256 文件）

## 记忆四模式 {#memory-modes}

课程 `run_evaluation.py` 原代码（3-1/3-2 合并战役），每层前 2 案例 × 4 模式 = 24 评估，写手/答题 DeepSeek、评审 qwen3.7-plus。**22/24 完成**（course status=partial）。

| 模式 | layer1 | layer2 | layer3 | 总体 pass | mean reward | 幻觉率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| notes | 1.0 | 0.5 | 0.5（幻觉 0.5） | 0.67 | 0.760 | 0.17 |
| enhanced_notes | 1.0 | 1.0 | 1.0 | **1.00** | **0.969** | **0.00** |
| json_cards | 0.5（幻觉 0.5） | 2 格写手失败 | 1.0 | 0.75* | 0.734 | 0.25 |
| advanced_json_cards | 0.5（幻觉 0.5） | 1.0 | 1.0 | 0.83 | 0.812 | 0.17 |

\* json_cards 的 layer2 两格缺失（见下）。88 次真实调用。

**逐条解读**：

- **layer3（跨会话协调）是分水岭**：原子化 notes 在这里幻觉率 50%——事实各自正确但跨会话连接丢失，答题者选择编造衔接；enhanced_notes 的段落自带"人物/时间/状态/关联"，满分通过；
- **layer1 反转**：单实体简单案例上两种 JSON 卡片模式反而各幻觉一例——为填满 card 字段（backstory/status）而脑补，结构化开销在简单场景是负资产；
- **json_cards 双重失败**：写手在 layer2 多实体案例产出畸形长 JSON（`finish_reason=stop`、非截断；错误点在 4.7–5.3K 字符处的语法滑丝，json_object 响应格式未兜住）。这是 DeepSeek 写手的长 JSON 可靠性边界，非课程代码问题（书方写手 doubao 同格通过）。16 次调用全部留下回执；
- **成本**（tokens/均延迟每模式）：enhanced_notes 78.8K/5.3s（最省）、notes 91.3K/5.7s、json_cards 63.8K/5.9s（少两格）、advanced_json_cards 108.1K/6.9s（最贵）。enhanced_notes 同时拿下最高分与最低成本；
- 样例：layer3 enhanced_notes 的最终记忆含"Jessica 10-05 来电确认副卡持有人……护照 2025-03-02 到期"，答题者主动给出"护照是最紧急的一项"——proactivity 维度的直接来源。

**未验证的边界**：每模式仅 6 案例（layer2 的 json_cards 实为 4），单格翻转 ±50%；书方 60×4 全量战役中 advanced_json_cards 总体领先，本次 0.83 次于 enhanced_notes——差异在样本量内，只报方向不排名。

## Agentic vs 单轮 RAG {#agentic-rag}

课程 `campaign.py` 原代码，**全量 7 案例**（5 简单 + 2 复杂多跳），本地法条 BM25 检索器零改动，答题 DeepSeek、评审 qwen3.7-plus。37 次调用、56,337 tokens，课程验收门槛全过。

| 臂 | 组 | 证据召回 | 评审正确性 | 搜索次数 | 延迟 |
| --- | --- | ---: | ---: | ---: | ---: |
| baseline | simple | 1.00 | 4.00 | 1.0 | 1642ms |
| baseline | complex | 0.58 | 3.50 | 1.0 | 1761ms |
| agentic | simple | 1.00 | 4.00 | 2.0 | 3433ms |
| agentic | complex | **0.92** | **4.00** | 3.0 | 3943ms |

三条预注册假设**全部成立**：简单题打平（差 0 ≤0.5）、复杂题质量提升（召回 0.58→0.92、正确性 3.50→4.00）、Agentic 必然更慢（均值 1.7s→3.7s）。机制可见于轨迹：复杂题被拆成"房产分割""子女抚养"分次检索，union 证据覆盖 3 个金标法条——整句检索时两主题词互相稀释正是基线 0.58 的原因。

**未验证的边界**：7 案例无统计功效，只验证方向；书方战役（不同模型）方向一致。

## 上下文感知检索 {#contextual-retrieval}

课程 `campaign.py` 原代码，**全量 2 文档/22 chunk/15 查询**（与书方同规模）；document_store.json 由书方已通过战役的证据无损重建（chunk 内容逐字节相同）；前缀由 DeepSeek 现场生成（live 门槛满足）；稠密检索本地 Qwen3-Embedding-0.6B。课程验收门槛全过、泄漏扫描干净。

| 方法 | MRR | R@1 | R@3 | R@5 |
| --- | ---: | ---: | ---: | ---: |
| plain_bm25 | 0.833 | 0.73 | 0.87 | 1.00 |
| contextual_bm25 | 0.872 | 0.80 | 0.93 | 1.00 |
| plain_dense | 0.933 | 0.87 | 1.00 | 1.00 |
| contextual_dense | **0.967** | **0.93** | 1.00 | 1.00 |
| plain_hybrid | 0.889 | 0.80 | 1.00 | 1.00 |
| contextual_hybrid | **0.967** | **0.93** | 1.00 | 1.00 |

- **前缀三通道全部提升**（MRR：BM25 +0.039、稠密 +0.034、混合 +0.078）；R@1 从 0.73/0.87 → 0.80/0.93；
- contextual_hybrid 追平 contextual_dense：稠密通道足够强时混合边际趋零；plain 侧 hybrid 仍落后 dense 0.044——混合救的是"某通道弱"的场景；
- **索引成本一次性**：22 次前缀调用 181K tokens（输入 180K——每块请求携带整份源文档）、5.5s；CPU 编码 59 段 408s。查询阶段零增量；
- 与书方（doubao 前缀）对照：MRR plain_bm25 0.751→0.856、plain_dense 0.922→0.967、plain_hybrid 0.844→0.913——方向与数值区间一致，前缀收益更像机制性收益而非模型运气。

**未验证的边界**：小语料（22 块）R@5 已触顶、无区分度；单金标口径；同义改写查询（BM25 死穴）未测。

## 3-4 dense-embedding：待跑 {#dense-embedding}

**未完成**。基础设施记录：本机复现书方环境的已知缺陷——macOS ARM 的 annoy 轮子查询只返回第 0 项（原生库实测同病），课程 benchmark 自带健康检查与 Docker 回退（Linux 容器跑真 Spotify ANNOY）。首次运行完成 embedding 阶段后在 Docker 阶段失败（守护进程被退出）。**重跑需 Docker Desktop 在运行**，`learning/task3/run_dense_embedding.py` 约 3–5 分钟；ANNOY/HNSW 的增量行为对照（ANNOY 全量重建 vs HNSW 原位增删）源码已读，待实测后补本页。

## 源码与复现

```bash
# 课程仓库根目录
.venv/bin/python learning/task3/run_memory_modes.py        # 3-1/3-2 四模式，约 6 分钟
.venv/bin/python learning/task3/run_agentic_rag.py         # 3-8 全量 7 案例，约 4 分钟
.venv/bin/python learning/task3/run_contextual_retrieval.py # 3-10 全量，首次含 1.2GB 模型下载 + 7 分钟 CPU 编码
# 3-4：先确保 Docker Desktop 运行，再
.venv/bin/python learning/task3/run_dense_embedding.py     # 待跑
```

- 学习脚本：[run_memory_modes.py](../assets/task3/run_memory_modes.py) · [run_agentic_rag.py](../assets/task3/run_agentic_rag.py) · [run_contextual_retrieval.py](../assets/task3/run_contextual_retrieval.py)
- 已知坑（复跑必读）：课程 `write_campaign_evidence` 的 `input_paths` 引用 `HERE` 下的入口脚本——HERE 重定向时必须把入口 .py 一并复制进运行目录，否则全部 API 调用完成后写证据时崩溃（本任务踩过两次）；
- 未执行：3-2 的 mem0/Memobase 框架对照、3-3 日志脱敏、3-6 混合检索流水线、3-7 RAPTOR/GraphRAG、3-9/3-11（依赖 3-1 套件）、3-12 知识抽取。
