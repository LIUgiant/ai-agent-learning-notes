# Task 4 · 第 4 章 工具（MCP 与五类工具）实验

**课程范围**：第 4 章（工具的分类与通用设计原则、MCP 与 Skill Hub、工具太多怎么办、感知/执行/协作三类工具）。

目标：把第 4 章可跑的核心实验以学习版规模真实跑通并逐函数读懂课程源码。模型层换成本机可用凭据
（DeepSeek `deepseek-flash` 与 DashScope `qwen3.7-plus` / `qwen-vl-max`），书方历史验收记录不冒认为本人运行结果。
所有"缺凭据/缺依赖"的门禁一律如实记为 blocked，不用 mock 顶替。

## 这次怎样学

1. [概念：五类工具、四条通用原则与"一次看见多少"](concepts.md)：把六个实验放进"能力怎么表达—怎么描述—怎么传参—怎么披露"这张图里。

每个实验一对页面：**实验说明**（回答什么问题、怎么设计、结果怎么看）+ **源码精读**（逐函数读课程代码，每步附动手验证）。

已完成：

1. [主动工具发现](tool-discovery.md)（4-1）：50K 全量 schema 注入 vs 三工具 + 按需检索注入，强模型下还差多少。
   - [源码精读](tool-discovery-code.md)：1219 行 runner 逐函数拆，含哈希链轨迹、槽位判分与 12 条门禁。
2. [感知工具 MCP](perception-mcp.md)（4-2）：真 MCP 服务器 127 个工具、五类 28 个真实案例。
   - [源码精读](perception-mcp-code.md)：夹具构造、逐案例实质判定、逃逸探针、11 条门禁。
3. [多模态三范式](multimodal.md)（4-3）：同一张图表交给原生多模态 / 提取为文本 / 工具化分析。
   - [源码精读](multimodal-code.md)：12 行矩阵、三臂提示词差异、检查点式收据与外部评审。
4. [执行工具与安全门](execution-tools.md)（4-4）：linter 自动验证、逃逸拒绝、超时、LLM 危险审查、Docker 断网沙盒、长输出持久化。
   - [源码精读](execution-tools-code.md)：20 次调用对应的 15 条门禁，以及 stdio 通道被一行 print 污染的坑。
5. [协作工具](collaboration.md)（4-5）：子 Agent 同步/异步生命周期、两种上下文传递、HITL 待批与保守超时。
   - [源码精读](collaboration-code.md)：子 Agent 循环、状态机、迟到应答拒绝。
6. [工具选型三策略](tool-selection.md)：全量注入 / 一次性检索 / MCP-Zero 式主动发现，离线与在线两套指标。
   - [源码精读](tool-selection-code.md)：三臂循环差异与 token 计量口径。

[运行证据与复现](evidence.md)：全部实测数字、环境限制、命令与已知坑。

## 与书中实验的对应关系

| 书中编号 | 主题 | 本次状态 |
| --- | --- | --- |
| 4-1 | 主动工具发现（qwen3:4b + 127 工具） | ✅ 127 真 schema × 2 臂 × 3 任务（模型换 DeepSeek）+ 源码精读；三次运行含 GitHub 限流留证 |
| 4-2 | 感知工具 MCP 服务器 | ✅ 真 MCP 28 案例（search/filesystem 通过、视觉 qwen-vl 通过、缺依赖与限流项如实记录）+ 源码精读 |
| 4-3 | 多模态三范式 | ✅ 12 行矩阵 9/9 门禁 + 源码精读 |
| 4-4 | 执行工具 MCP 服务器 | ✅ 20 次真实调用、10 条 core 门禁全过、5 条外部门禁 blocked + 源码精读 |
| 4-5 | 协作工具 MCP 服务器 | ✅ 9 条门禁过 5 条（投递与真实人工决定缺凭据）+ 源码精读 |
| — | 主动工具选型（active-tool-selection） | ✅ 离线确定性对照 + DeepSeek 在线三臂 + 源码精读 |
| — | `docker-compose.yml` 容器化部署 | 未执行（本机用进程级部署） |
| 4-4 补充 | 虚拟桌面（Xvfb）/ Android 虚拟手机（KVM） | 未执行（macOS 无 X11、无 Android 容器，按课程规则 blocked） |
| 4-4 补充 | 真实日历 / GitHub PR / 邮件变更 | 未执行（无 Google 凭据、无 GitHub token、课程把邮件门禁硬编码为 False） |

## 教学约定

- 4-1/4-2/4-3/工具选型在 `.venv`（mcp 2.x）下运行；4-4/4-5 在 `.venv-ch4v1`（mcp 1.x）下运行——课程这两个项目的 MCP API 在 2.x 已被移除，见 [证据页](evidence.md#mcp-sdk-版本分叉)；
- 危险操作审查、子 Agent、评审一律走 DashScope 国内端点（本机 key 只在该端点有效）；正文模型走 DeepSeek，且**关闭 thinking**；
- 课程各项目 `validation/latest.json` 的写入已重定向到学习运行目录；书方五个 canonical manifest 的 SHA-256 在离线审计里逐个复核，确认未被触碰；
- 外部限流（Yahoo/MediaWiki/DuckDuckGo/GitHub 未认证 API）会导致同一实验多次运行结果不同，全部留存并在正文里标注。
