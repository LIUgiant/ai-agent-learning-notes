# Task 0 离线实验与验证报告

执行日期：2026-09-15。源提交：`cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c`。

## 结论

环境搭建、基础学习和所选离线实验已完成。第 1 章相关自动化测试 **139 passed，0 failed，0 skipped**；额外文档回归为 **7 passed，1 failed**，失败来自上游实验数量断言与当前 README 不一致。多语言结构检查、依赖检查、编译与学习脚本静态检查通过。不能将本报告称为“全仓库测试全部通过”。

本次只通过 uv 下载 Python 依赖，没有调用模型 API、没有消耗模型额度、没有启动 Ollama、没有下载模型权重。对凭据只记录环境变量是否存在，没有读取 `.env` 或密钥值。

## 环境建立

从仓库根目录执行：

```bash
uv sync --locked --python 3.12 --extra ch1 --extra dev
```

使用 CPython 3.12.13 创建 `.venv`，安装 67 个包。uv 报告锁内解析 611 个包，这是通用锁的范围，不代表安装了全部 611 个包。`ch1` 只选择当前章的 CPU 友好可视化与文档依赖，`dev` 提供 pytest、Markdown 和 Ruff 等验证工具。Google 原生生图 SDK 不在本次最小安装中，但生图离线测试使用解析/证据逻辑的惰性导入路径，已实际通过，不必为此安装整个 providers extra。

完整安装版本见 `dependencies.txt`；例如 OpenAI SDK 2.48.0、NumPy 1.26.4、pytest 9.1.1、Ruff 0.16.0。SDK 安装成功只表示依赖就绪，不表示任何账号、模型或托管工具可用。

## 目标测试

全部测试由 `self_check.py` 在隔离的子进程中执行。每个实验使用自己的工作目录和模块路径；涉及模型响应的测试使用既有 mocks/fixtures。`context/tests/test_code_interpreter.py` 会按密钥存在情况选择分支，本次子进程没有密钥，执行的是本地工具分支。

| 测试范围 | 结果 | 输出 |
| --- | --- | --- |
| `chapter1/context/tests` + 根部 3 个消融/grounding/返回语义测试文件 | 38 passed | `reports/tests-context.txt` |
| `chapter1/web-search-agent/tests` | 42 passed | `reports/tests-web-search-agent.txt` |
| `chapter1/search-codegen/test_responses_agent.py` + `test_config_and_usage.py` | 12 passed | `reports/tests-search-codegen.txt` |
| `chapter1/image-gen-workflow/tests` | 25 passed | `reports/tests-image-gen-workflow.txt` |
| `chapter1/learning-from-experience/tests` + `test_experiment_8_2_evidence.py` | 16 passed | `reports/tests-learning-from-experience.txt` |
| 根测试 `test_ch1_learning_agents_empty_eval_windows.py` | 2 passed | `reports/test_ch1_learning_agents_empty_eval_windows.txt` |
| 根测试 `test_ch1_search_codegen_null_response.py` | 4 passed | `reports/test_ch1_search_codegen_null_response.txt` |
| **第 1 章相关合计** | **139 passed** | — |

根目录名称含 `ch1_ch2` 的 system-hint 测试实际导入第 2 章模块，不属于本次第 1 章范围，未纳入。没有运行全仓库 pytest，也没有运行需要真实凭据的 `tests/manual/check_*.py`。

## 离线实践与认识

### A. Context 本地工具：真实执行，不调用模型

学习脚本 `offline_tools.py` 直接调用上游 `ToolRegistry`，并对结果断言：

| 输入/操作 | 本次结果 |
| --- | --- |
| `2500 * 0.15` | 375 |
| 375 USD 转 EUR | 345 EUR；使用实验内固定汇率 0.92，并非实时汇率 |
| Python 求 `[120, 80, 50]` 的和再乘 0.88 | 220，代码执行返回 `success=true` |
| 解析已有 `simple_expense_report.pdf` | 1 页，提取 539 字符 |
| 不支持的币种 `UNKNOWN` | 结构化 error，未假装换算成功 |

证据：`reports/context-tools.json` 和 `.txt`。工具确实执行，但调用顺序来自学习脚本，因此这里只验证工具和输入输出接口，不验证 LLM 规划。已有 `test_code_interpreter` 的无密钥分支主要打印结果，学习脚本补充了明确数值断言。

### B. Web Search：固定 ReAct 轨迹回放

执行 `main.py --provider offline-demo --output ...`，结果保存在 `reports/web-offline.json`。轨迹顺序是：

```text
thought → action → observation → thought → action → observation → answer
```

这说明第二轮能接收第一轮的观察；总共 2 条 action、2 条 observation、1 个最终 answer。数据来自仓库内置样例，没有发起实际搜索，不能据此评价 Kimi 的自主搜索、事实正确率或延迟。

### C. Search Codegen：Responses 请求 dry-run

执行 `main.py --backend openai --dry-run --request ... --reasoning max --verbosity high`，打印待发送的请求体，没有发送请求。结果包含托管 `web_search` 和 `code_interpreter` 工具声明、澄清优先提示与模型参数。

认识：声明 `tools` 不等于服务端真的执行工具；真实验收要检查返回的 typed tool call、引用和继续会话关系。本次只做 dry-run 和模拟响应的协议测试，未计算真实东盟距离、未检索市场数据。证据：`reports/responses-dry-run.txt`。

### D. Image Workflow：结构测试

执行 README 推荐的离线 pytest，验证改写输出解析、需求集合、配置变量名、manifest 结构及证据校验。没有运行默认 `main.py`，没有生成图片。因此无法从本次结果得出“哪条路线画得更好”的结论。

### E. Q-learning：纯本地训练与评估

执行现有 README 的离线路径，并显式固定评估数量和输出位置：

```bash
python experiment.py --mode qlearning --rl-episodes 10000 \
  --eval-episodes 100 --seed 42 --output <Task0工作目录>
```

环境使用默认确定性游戏；学习率 0.2、折扣 0.99、epsilon 从 1.0 按 0.9995 衰减到最低 0.1；训练后以贪婪策略评估。

| 指标 | 本次实测 |
| --- | --- |
| 训练局数 | 10,000 |
| 训练总胜利 | 4,510（45.10%） |
| 训练结束 Q 表 | 142 个状态 |
| 贪婪评估 | 100 / 100 成功 |
| 评估平均步数 | 12 |
| 评估平均奖励 | 243 |

训练早期大多数局失败；最近 1,000 局的胜率从第 5,000 局处的 0.1%，升到第 6,000 局的 55.9%、第 7,000 局的 97.0%，到第 10,000 局窗口为 98.1%。训练总体胜率包含早期探索失败，不能与训练后贪婪评估胜率混为一谈。

这个结果仅适用于本次 seed 与确定性游戏，不证明跨环境泛化，也没有统计置信度或多随机种子分析。未执行 LLM 对照臂，不能推算 LLM 的样本效率、成本或胜率优势。

`reports/qlearning.txt` 保留完整控制台学习曲线；`reports/qlearning-summary.json` 保留轻量指标、曲线、随机种子和原始 JSON 的 SHA-256。每局奖励/步数数组与 Q 表 pickle 留在被忽略的 `work/qlearning/`，不作为需版本管理的学习文件。

## 仓库验证与已知问题

| 验证 | 实际结果 |
| --- | --- |
| `uv lock --check --offline` | 通过，锁文件可按当前项目配置使用 |
| `uv sync --locked --offline --dry-run --python 3.12 --extra ch1 --extra dev` | 通过，67 个包无需变动 |
| `uv pip check --python .venv/bin/python` | 通过，安装依赖兼容 |
| `python -m compileall -q chapter1 learning/task0` | 通过；仅编译，不执行手工/API 脚本 |
| `ruff check learning/task0 --exclude work` | 通过；只检查新增学习脚本，未宣称所有上游代码 lint 通过 |
| `python scripts/check_i18n_consistency.py` | 通过，脚本发现的 13 个语言入口结构一致 |
| 章节编号与实验状态链接测试 | 7 passed，1 failed，见下述原因 |
| `git diff --check` | 通过；另检查新增文本文件的空白问题 |
| Git 状态与输入文件哈希 | 仅新增 `learning/task0/`；上游受跟踪文件及 8 个输入文件未改变 |

**保留的上游失败。** `tests/test_chapter_numbering_consistency.py:65` 要求 README 包含 `**108 个配套实验**`，而当前根 README 已包含 `**109 个配套实验**`。本次未改动两者，故这是当前源版本已有的不一致，不是 Python/依赖兼容问题。该测试在这一断言处停止，不能断言其后所有检查都已执行或通过。失败输出见 `reports/docs-tests.txt`（仅规范行尾空白；原始输出在 `work/logs/docs-tests.txt`）。

多语言脚本统计的是章节表中的项目行（含补充/历史项目），与正文实验编号数量口径不同：13 个被发现的入口、119 行项目不是 README“15 种语言、109 个实验”的同一指标。脚本通过只代表它实际覆盖的结构规则通过，不代表所有自然语言叙述均无矛盾。

**已修复的学习脚本问题。** 首轮 Ruff 提示 import 顺序、无用 noqa、可执行位及 subprocess 显式 `check` 参数；全部仅在 `learning/task0/` 修复。未修改上游实验实现或测试断言。

自检不会忽略或 xfail 上述文档失败，所以在该源版本上整体退出码预期为 **1**。应阅读分项记录，不能因退出码非零而误判离线环境未搭建成功，也不能将其描述为“所有检查通过”。

## 未执行门槛

| 路径 | 未执行原因 |
| --- | --- |
| 实验 1-1 五臂真实模型消融 | 需要支持的提供商凭据与真实模型调用授权；本次限定不消耗外部模型额度 |
| 实验 1-2 Kimi Formula 搜索 | 需要 Moonshot 凭据及托管搜索服务；离线轨迹不是其替代验收 |
| 实验 1-3 真实 hosted search/code | 需要提供 Responses 托管工具的 API 账号与额度；dry-run 不能证明服务可用 |
| 实验 1-4 改写/生图质量对照 | 需要相应 Kimi、DashScope、Gemini/OpenAI 凭据、图像 SDK 和模型调用；未生成图像 |
| RL vs LLM 游戏对照 | 仅运行 Q-learning；LLM 臂会调用模型 API |

上述路径是后续在线实验的前提，不阻塞本次 Task 0 的离线范围。仓库历史证据中的成功、额度不足或模型状态均未被当作本次账号的实测结果。



!!! note "历史记录"
    本页记录 2026-09-15 的离线阶段。后续真实 API 实验见左侧独立页面。完整原始日志保存在本地课程项目。
