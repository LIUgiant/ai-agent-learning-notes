# 工具选型三策略：一步步读源码

[实验说明](tool-selection.md) · [运行证据与复现](evidence.md#tool-selection) · [学习运行脚本](../assets/task4/run_tool_selection.py) · [课程项目目录](https://github.com/bojieli/ai-agent-book/tree/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection)

<div class="design-lead"><span>逐函数通读 / READ EVERY FUNCTION</span><p>本页按源码顺序把三个文件过一遍：<code>benchmark.py</code>（10 个金标任务、干扰工具目录、零 API 的 recall/token 评测）、<code>agent.py</code>（三条臂 Passive / Retrieval / Active，含 token 计量）、<code>semantic_router.py</code>（TF-IDF 两层路由与结构化请求解析）。先用三张表证明函数一个不漏，再用两张调用图把离线与在线两条主线连起来，然后逐个函数拆，最后用一次真实执行把整条链路串起来。读完本页，你应当能在不打开源码的情况下说出每个函数在算什么、又在骗你什么。</p></div>

!!! note "先分清三种代码"
    **课程源码原文**附文件与行号，链接指向课程仓库固定提交 `cf7f7a8`。**学习运行脚本原文**来自 `learning/task4/run_tool_selection.py`（它原样复用课程三臂与课程检索，只在进程内换 LLM 端点与温度）。**教学示意**仅用于解释数据形状或记账口径，不是可运行代码。

!!! warning "实测与推断分开读"
    本页所有带「实测」的行都来自一次真实运行（`20260921T112429Z`，DeepSeek `deepseek-flash`，课程目录 35 工具，`top_k=5`），数字可在 `learning/task4/runs/tool_selection/20260921T112429Z/evidence.json` 里逐项核对；带「推断」的行是从源码结构推出的机制解释，没有独立实验验证。离线表是确定性的——你自己跑一次会得到一模一样的数字；在线表受模型采样影响，只能当一次观测。

**三个主文件**：

- [chapter4/active-tool-selection/benchmark.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/benchmark.py)（203 行）：金标任务 + 干扰目录 + 离线评测，**零 API**。
- [chapter4/active-tool-selection/agent.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py)（541 行）：三条臂的全部实现。
- [chapter4/active-tool-selection/semantic_router.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/semantic_router.py)（292 行）：TF-IDF 路由 + 结构化请求解析。

辅助文件只在解释计量口径与调用链时引用：[tool_knowledge_base.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/tool_knowledge_base.py)（624 行，8 个 server / 35 个工具 + token 近似器）、[config.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/config.py)（56 行，导入期读环境变量）、[demo_comparison.py](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/demo_comparison.py)（535 行，两条主线的编排者与 CLI）。

---

## 1. 函数清单地图

行号用 `grep -n "^\s*\(def \|class \|    def \)"` 逐文件核对，与固定提交一致（`git diff cf7f7a8 -- chapter4/active-tool-selection/` 输出为空）。

### 1.1 `benchmark.py`（203 行）

| # | 函数/常量 | 行号 | 一句话作用 | 谁调用它 |
| --- | --- | --- | --- | --- |
| — | `BENCHMARK_TASKS` | L34–85 | 10 个任务 + 每个任务的 `gold_tools`（金标） | `evaluate_offline`（默认参数）、`run_offline_benchmark`、`run_online_benchmark`、学习脚本（只取 `len`） |
| 1 | `make_distractor_servers` | L88–130 | 合成 `svcN_opM` 干扰工具，把目录吹大 | `build_catalog` |
| 2 | `build_catalog` | L133–146 | 真实目录，可选补齐到 N 个工具 | `demo_comparison.main`、`run_offline_benchmark`（缩放循环）、学习脚本 |
| 3 | `evaluate_offline` | L149–203 | **离线核心**：算 all-tools 与 retrieval 的 recall@k 与 schema token | `run_offline_benchmark`、学习脚本（经它调用） |

### 1.2 `agent.py`（541 行）

| # | 类 / 方法 | 行号 | 一句话作用 | 谁调用它 |
| --- | --- | --- | --- | --- |
| 1 | `ActiveToolAgent` | L16 | MCP-Zero 式主动发现臂 | `_build_agent`、`run_single_query` |
| 2 | `ActiveToolAgent.__init__` | L26–50 | 建客户端、目录、路由器、metrics 骨架 | `_build_agent` |
| 3 | `ActiveToolAgent.execute_task` | L52–109 | **请求 → 检索 → 注入 → 再决策的迭代循环**（上限 `MAX_TOOL_REQUESTS`） | `run_online_benchmark`、`run_single_query` |
| 4 | `ActiveToolAgent._create_system_message` | L111–135 | 教模型用 `<tool_request>` 声明能力缺口 | `execute_task` |
| 5 | `ActiveToolAgent._call_llm` | L137–165 | 带当前已加载工具调一次；记 token；遇 tool_calls 转 `_handle_tool_calls` | `execute_task`、`_handle_tool_calls`（递归） |
| 6 | `ActiveToolAgent._handle_tool_request` | L167–212 | 把请求文本交给路由器，把新工具追加进上下文并回灌反馈 | `execute_task` |
| 7 | `ActiveToolAgent._handle_tool_calls` | L214–256 | 模拟执行工具、记 `tools_called`、把结果塞回历史再调一次 | `_call_llm` |
| 8 | `ActiveToolAgent.reset` | L258–269 | 清空历史/已加载工具/全部 metrics | `run_online_benchmark`（每任务前） |
| 9 | `RetrievalToolAgent` | L272 | 一次性检索臂（RAG 式中庸路线） | `_build_agent`、`run_single_query` |
| 10 | `RetrievalToolAgent.__init__` | L287–306 | 同前，多一个 `top_k`（默认 `config.TOP_K_TOOLS`） | `_build_agent` |
| 11 | `RetrievalToolAgent.execute_task` | L308–337 | **一次检索 + 一次决策**，没有发现回合 | `run_online_benchmark`、`run_single_query` |
| 12 | `RetrievalToolAgent._call_llm` | L339–360 | 只注入 top-k 工具 | `execute_task`、`_handle_tool_calls` |
| 13 | `RetrievalToolAgent._handle_tool_calls` | L362–392 | 模拟执行并递归取最终答复 | `_call_llm` |
| 14 | `RetrievalToolAgent.reset` | L394–403 | 清空（不含 `top_k`/路由器） | `run_online_benchmark` |
| 15 | `PassiveToolAgent` | L406 | 全量注入基线臂 | `_build_agent`、`run_single_query` |
| 16 | `PassiveToolAgent.__init__` | L416–436 | 把目录里**所有**工具摊平进 `self.all_tools` | `_build_agent` |
| 17 | `PassiveToolAgent.execute_task` | L438–466 | **一个 system + 一个 user + 一次调用**，没有循环 | `run_online_benchmark`、`run_single_query` |
| 18 | `PassiveToolAgent._call_llm` | L468–492 | 每次调用都带全部工具 schema | `execute_task`、`_handle_tool_calls` |
| 19 | `PassiveToolAgent._handle_tool_calls` | L494–531 | 同 Retrieval，模拟串文案略不同（L501） | `_call_llm` |
| 20 | `PassiveToolAgent.reset` | L533–541 | 清空（`tools_loaded` 重新记为目录总量） | `run_online_benchmark` |

三条臂的 `_handle_tool_calls` / `_call_llm` / `reset` 是**三份近乎逐字重复的实现**（不是继承）——这是本文件最值得吐槽的结构，也是逐函数读时必须对照着看的原因。

### 1.3 `semantic_router.py`（292 行）

| # | 类 / 方法 | 行号 | 一句话作用 | 谁调用它 |
| --- | --- | --- | --- | --- |
| 1 | `SemanticRouter` | L20 | 两层 TF-IDF 语义路由 | `benchmark.evaluate_offline`（L166）、`agent` 的两个 Agent（L36、L297）、`examples`、`demo_semantic_routing` |
| 2 | `SemanticRouter.__init__` | L23–32 | 建 server 级向量器 + 每 server 一个 tool 级向量器，并**预计算**全部嵌入 | 上面各处 |
| 3 | `SemanticRouter._build_server_index` | L34–43 | 对 `name + description` 做一次全局 TF-IDF | `__init__` |
| 4 | `SemanticRouter._build_tool_indices` | L45–65 | 每个 server 内部单独 fit 一个 TF-IDF，嵌入挂在 `server._tool_embeddings` | `__init__` |
| 5 | `SemanticRouter.route_request` | L67–106 | **两层**路由（server top-3 → 每 server top-5 → 合并排序 → **阈值过滤**） | `ActiveToolAgent._handle_tool_request`（L179）、`examples` |
| 6 | `SemanticRouter.retrieve` | L108–134 | **平坦** top-k（扫全部 server 打分，**不设阈值**） | `evaluate_offline`（L174）、`RetrievalToolAgent.execute_task`（L313） |
| 7 | `SemanticRouter._route_to_servers` | L136–159 | 第 1 层：query 与 server 描述求余弦，取 top-k | `route_request`、`retrieve`、`get_routing_details` |
| 8 | `SemanticRouter._route_to_tools` | L161–193 | 第 2 层：在指定 server 内求余弦；query 词表不命中则直接返回空 | 同上三者 |
| 9 | `SemanticRouter.get_routing_details` | L195–246 | 返回两层中间分数，只用于调试/演示 | `demo_semantic_routing` |
| 10 | `StructuredRequestParser` | L249 | 解析/生成 MCP-Zero 式请求块 | `ActiveToolAgent.execute_task`（L89） |
| 11 | `StructuredRequestParser.parse_request` | L261–284 | `<tool_request>` 文本 → `{'server','tool'}` 字典 | `execute_task` |
| 12 | `StructuredRequestParser.format_request` | L287–292 | 反向：两段描述 → 请求块字符串 | **运行时无调用点**；唯一使用者是 `tests/test_basic.py` L94 的格式断言 |

### 1.4 辅助文件（只列主线与计量口径里出现的；非穷举）

`demo_comparison.py` 另有 4 个只在 `--legacy-demos` 下运行的叙事演示（`run_comparison_demo` L26、`demo_active_discovery_process` L124、`demo_semantic_routing` L161、`demo_iterative_capability_extension` L196）与两个小工具（`print_section` L19、`_has_api_key` L469），它们不在本页两条主线上，只在前两处被引用时点名。

| 符号 | 位置 | 作用 | 被谁调用 |
| --- | --- | --- | --- |
| `ToolDefinition.to_schema` | tool_knowledge_base L21–30 | 工具对象 → OpenAI function schema dict | 三条臂的 `_call_llm`、`count_tokens_in_schema` |
| `count_tokens_in_schema` | L612–616 | `len(json.dumps(schema)) // 4` | `calculate_total_tokens` |
| `calculate_total_tokens` | L619–624 | 一批工具的 schema token 合计 | `benchmark.evaluate_offline`、`demo_comparison`、`quickstart` |
| `get_all_tools` | L604–609 | server 列表 → 扁平工具列表 | `evaluate_offline`、`build_catalog` |
| `create_tool_knowledge_base` | L49–601 | 硬编码 8 个 server / 35 个工具（528 行全是字面量） | 三条臂的 `__init__`、`build_catalog` |
| `STRATEGY_AGENTS` | demo_comparison L310–314 | 策略名 → (标签, 类) 查表 | `_build_agent`、`run_online_benchmark`、`run_single_query` |
| `run_offline_benchmark` | L227–307 | 打印离线表 + 逐任务明细 + 缩放表 | `main`、学习脚本 |
| `_build_agent` | L317–322 | 按策略名实例化（retrieval 额外传 `top_k`） | `run_online_benchmark`、`run_single_query` |
| `run_online_benchmark` | L325–383 | **在线核心**：逐任务执行、命中判定、token/延迟聚合 | `main`、学习脚本 |
| `run_single_query` | L386–406 | 单条查询过三臂（手工排查用） | `main --query` |
| `build_parser` / `main` | L409–466 / L473–531 | CLI 与编排 | 入口 |

清单合计：`benchmark.py` 4 条（1 常量 + 3 函数）、`agent.py` 20 条（3 类 + 17 方法）、`semantic_router.py` 12 条（2 类 + 10 方法），共 **36 条**；辅助 11 条。

---

## 2. 主线调用图

### 2.1 离线主线（零 API，确定性）

```text
demo_comparison.main()                                     [L473]
 |
 |-- servers = benchmark.build_catalog(args.num_tools)     [L484]
 |     |
 |     |-- create_tool_knowledge_base()        -> 8 servers / 35 tools   [kb L49]
 |     |-- get_all_tools(servers)              -> 35                     [kb L604]
 |     '-- [只有 num_tools > 35 时]
 |           make_distractor_servers(需要补齐的个数)  -> svcN_opM        [L88]
 |               '-- ToolDefinition(name=f"svc{i}_op{j}", ...) 每 5 个一组 [L107]
 |
 '-- run_offline_benchmark(servers, top_k, scaling=True)   [L498 -> L227]
       |
       |-- benchmark.evaluate_offline(servers, top_k)      [L238 -> bench L149]
       |     |
       |     |-- router = SemanticRouter(servers)          [bench L166 -> sr L23]
       |     |     |-- _build_server_index()  server 级 TF-IDF(name+desc)  [sr L34]
       |     |     '-- _build_tool_indices()  每 server 一个 TF-IDF       [sr L45]
       |     |
       |     |-- all_tools = get_all_tools(servers)                      [bench L167]
       |     |-- all_tools_tokens = calculate_total_tokens(all_tools)    [bench L168]
       |     |     '-- count_tokens_in_schema: len(json.dumps(schema))//4 [kb L612]
       |     |
       |     '-- for t in BENCHMARK_TASKS:                              [bench L173]
       |           retrieved = router.retrieve(t["task"], top_k)         [sr L108]
       |              |-- _route_to_servers(query, len(all_servers))     [sr L136]
       |              '-- for 每个 server: _route_to_tools(server, query, len(server.tools))
       |           hit = any(g in retrieved_names for g in t["gold_tools"])  [L176]
       |           retrieval_tokens_sum += calculate_total_tokens(retrieved) [L178]
       |
       '-- for size in [num_tools, 50, 100, 200, 400]:                  [L283]
             padded = benchmark.build_catalog(size)                     [L289]
             r = benchmark.evaluate_offline(padded, top_k)              [L290]
             -> 缩放表（all-tools token 线性涨 / retrieval 基本不动）
```

### 2.2 在线主线（需要 API）

```text
run_online_benchmark(servers, ["all","retrieval","active"], top_k, model)  [L325]
 |
 |-- _build_agent(st, servers, top_k, model)        [L337 -> L317]
 |     '-- STRATEGY_AGENTS[st]  查表                [L310]
 |           '-- "all"       -> PassiveToolAgent(servers=..., model=...)    全量注入
 |               "retrieval" -> RetrievalToolAgent(servers=..., model=..., top_k=...)
 |               "active"    -> ActiveToolAgent(servers=..., model=...)
 |
 '-- for t in BENCHMARK_TASKS:                     [L350]
       agent.reset()                               [L351]  <- 每任务清零 metrics/历史
       start = time.time()
       res = agent.execute_task(t["task"])         [L353]  <- 三臂各自的循环（下）
       elapsed = time.time() - start
       called  = res['metrics'].get('tools_called', [])   [L356]
       hit     = any(g in called for g in t["gold_tools"]) [L357]  <- 命中金标判定
       tokens_sum  += res['metrics']['tokens_used']        [L359]
       tools_ctx_sum += res['metrics']['tools_loaded']     [L361]
       '-- per_task 记 {task, gold, called, hit, tokens, latency}  [L362]

三个 execute_task 的循环差异（同一张图，三条路径）：

 PassiveToolAgent.execute_task  [L438]         RetrievalToolAgent.execute_task  [L308]
   system: "你有 35 个工具"                       available = router.retrieve(task, top_k)  [L313]
   user:   task                                  system: "检索系统预选了这 k 个工具" + 工具清单
   _call_llm()  <-- tools = 全部 35 个 schema     _call_llm()  <-- tools = 只有 k 个 schema
     '-- 有 tool_calls? -> _handle_tool_calls      '-- 有 tool_calls? -> _handle_tool_calls
           记 tools_called / 回灌结果 / 再 _call_llm        同上
   返回（无循环，1 次决策）                        返回（无循环，1 次检索 + 1 次决策）

 ActiveToolAgent.execute_task  [L52]
   system: 教它用 <tool_request> 声明缺口（"Current available tools: None"）
   user:   task
   for iteration in range(config.MAX_TOOL_REQUESTS):        [L83]
     response = self._call_llm()                            [L85]  <- 第 0 轮不带任何 tools 参数
     metrics['api_calls'] += 1                              [L86]
     tool_request = StructuredRequestParser.parse_request(response)  [L89]
     if tool_request:                                       [L91]
        _handle_tool_request(...)                           [L93]
          |-- query = server描述 + tool描述                   [L176]
          |-- router.route_request(query)  <-- 阈值 0.15 + top3 server x top5 tool  [L179]
          |-- 新工具去重后 available_tools.append，metrics['tools_loaded'] += 1      [L193-195]
          '-- 反馈 "Tools discovered and loaded (n new tools)" + 工具清单 回灌历史     [L198-212]
        tool_request_count += 1 / metrics['tool_requests'] += 1     [L94-95]
     else:
        assistant 内容入历史，break                           [L98-102]
   return {response, metrics, tools_loaded, conversation}    [L104]
```

!!! note "读图要点"
    离线主线**不碰模型**，所以它的数字可以当基线反复复现；在线主线里唯一的判定量是 `metrics['tools_called']`，而它只可能包含被注入过 schema 的名字——这一点决定了离线 recall 与在线命中不是同一个指标（见 3.5）。

---

## 3. 逐函数讲解

### 3.1 `benchmark.py`

#### `BENCHMARK_TASKS`（L34–85）：10 个任务，每个一个金标

[chapter4/active-tool-selection/benchmark.py · L31–L49](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/benchmark.py#L31-L49)

```python title="chapter4/active-tool-selection/benchmark.py" linenums="31"
# Labeled benchmark: each task has one (or a few acceptable) ground-truth tool(s).
# Queries are in English to match the English tool descriptions used by the
# TF-IDF router (see tool_knowledge_base.py).
BENCHMARK_TASKS: List[Dict] = [
    {
        "name": "GitHub repo search",
        "task": "Search GitHub for popular Python machine learning repositories with more than 10000 stars",
        "gold_tools": ["github_search_repos"],
    },
    {
        "name": "Read config file",
        "task": "Read the contents of the local configuration file at /etc/app/config.json",
        "gold_tools": ["fs_read_file"],
    },
    {
        "name": "List directory",
        "task": "List all files and subdirectories under the /var/log directory",
        "gold_tools": ["fs_list_directory"],
    },
```

三个字段各司其职：`name` 只用于打印，`task` 是**喂给模型和检索器的同一段自然语言**，`gold_tools` 是唯一的裁判标准。十个任务与其金标（对照 `tool_knowledge_base.py` 的 8 个 server）：

| # | name | 任务在问什么 | gold_tools | 所属 server |
| --- | --- | --- | --- | --- |
| 1 | GitHub repo search | GitHub 上找万星 Python ML 仓库 | `github_search_repos` | github |
| 2 | Read config file | 读本地 `/etc/app/config.json` | `fs_read_file` | filesystem |
| 3 | List directory | 列 `/var/log` 下的文件 | `fs_list_directory` | filesystem |
| 4 | Summary statistics | 算上季度销售的均值/中位数/标准差 | `analytics_summarize` | analytics |
| 5 | Send email | 把季度总结邮件发给团队 | `comm_send_email` | communication |
| 6 | Deploy to production | 把 2.3.0 部署到生产 | `devops_deploy` | devops |
| 7 | SQL query | 查各地区活跃用户数的 SQL | `db_query` | database |
| 8 | Upload to cloud | 把报告文件传到云存储桶 | `cloud_upload_storage` | cloud |
| 9 | Scrape prices | 抓取网页上所有商品价格 | `web_scrape` | web |
| 10 | Monitor service | 取 staging 服务的 CPU/内存指标 | `devops_monitor` | devops |

四个设计要点：

1. **每个任务专打一个"域"**，且金标工具在该域内是**唯一正确**的那个。所以这个基准测的是「选域 + 选具体工具」，不是多步编排——这是它最大的能力边界（见第 4 节的诚实解读）。
2. **任务是英文**，且刻意带上与工具描述重叠的词（`repository` / `configuration file` / `directory` / `statistics` / `email` / `Deploy` / `SQL query` / `cloud storage` / `Scrape` / `monitoring metrics`）。这不是巧合：TF-IDF 只认词面重叠（3.3 节细讲），中文任务在英文目录上会直接退化成随机。
3. **`gold_tools` 是列表而非字符串**——它允许一个任务有多个可接受答案。当前 10 个任务各只有一个金标，所以列表形式在这个数据集里没被用上；`run_online_benchmark` 的判定 `any(g in called for g in t["gold_tools"])`（L357）与 `evaluate_offline` 的判定（L176）都按"命中任一即算对"写，换成多金标任务不用改代码。
4. 任务**不含工具名**（没有一处出现 `fs_read_file` 这样的字符串）。否则检索会变成字符串匹配，实验就没有意义了。这是设计金标任务时最容易犯的错。

#### `make_distractor_servers`（L88–130）：怎么造噪音

[chapter4/active-tool-selection/benchmark.py · L88–L130](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/benchmark.py#L88-L130)

```python title="chapter4/active-tool-selection/benchmark.py" linenums="88"
def make_distractor_servers(num_tools: int, start_index: int = 1,
                            tools_per_server: int = 5) -> List[ServerDefinition]:
    """
    Generate synthetic *distractor* servers/tools to inflate the catalog size.

    These are deliberately generic "internal service" operations. They add real
    schema tokens and act as retrieval noise, so we can study how each strategy
    scales as the ecosystem grows to hundreds of tools — without hand-writing
    hundreds of realistic tools. They are clearly named ``svcN_opM`` so nobody
    mistakes them for the real catalog.
    """
    servers: List[ServerDefinition] = []
    created = 0
    server_idx = start_index
    while created < num_tools:
        n = min(tools_per_server, num_tools - created)
        tools = []
        for j in range(1, n + 1):
            op = created + j
            tools.append(ToolDefinition(
                name=f"svc{server_idx}_op{j}",
                description=(
                    f"Auxiliary internal-service operation {op} for background "
                    f"housekeeping on internal resource group {server_idx}"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "resource_id": {"type": "string", "description": "Internal resource identifier"},
                        "options": {"type": "object", "description": "Operation options"},
                    },
                    "required": ["resource_id"],
                },
                server=f"internal_service_{server_idx}",
            ))
        servers.append(ServerDefinition(
            name=f"internal_service_{server_idx}",
            description=f"Internal auxiliary service {server_idx} for background housekeeping operations",
            tools=tools,
        ))
        created += n
        server_idx += 1
    return servers
```

"造噪音"的三个具体决定：

- **命名自曝家门**：`svc1_op1`、`internal_service_1`。名字里就写着"我是假的"，任何人在日志里看到 `svc7_op3` 都不会误以为它是真实工具。这防止了"拿干扰项当结论"的事故。
- **每 5 个工具配一个 server**（`tools_per_server=5`）：让 server 数也随规模增长，模拟真实 MCP 生态"多域、每域几个工具"的形状。注意 `while created < num_tools` 循环里 `n = min(tools_per_server, 剩余)`，所以**最后一个 server 可能只有 1–4 个工具**——`--num-tools 36` 会产生 8 个真实 server + 1 个只有 1 个工具的 `internal_service_1`。
- **schema 形状刻意比真实工具小**：只有 `resource_id`（必填）+ `options` 两个字段。这带来一个必须知道的口径偏差：放大到同一规模时，**干扰工具的每工具 token 成本低于真实工具**（真实工具平均 110 token/个，干扰工具约 82 token/个），所以缩放表里 all-tools 的 token 增长（35→400 时 3,857→40,258）**略低于**"目录全由真实工具组成"时应有的增长。趋势（线性）不变，绝对值偏保守。

`description` 里那句 `background housekeeping` 是刻意的：它是"通用的、无区分度的"业务描述，跟任何基准任务的 query 都不共享有意义的词——所以它不会意外抢走金标的排名。这是造干扰项时最难的一步：**噪音必须真的像噪音**，否则你测的是"检索器能不能排除高仿",而不是"目录变大后的成本"。

#### `build_catalog`（L133–146）：只加不减

[chapter4/active-tool-selection/benchmark.py · L133–L146](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/benchmark.py#L133-L146)

```python title="chapter4/active-tool-selection/benchmark.py" linenums="133"
def build_catalog(num_tools: int = 0) -> List[ServerDefinition]:
    """
    Build the tool catalog, optionally padded with distractor tools.

    Args:
        num_tools: Target total number of tools. 0 (default) keeps the real
            catalog untouched. Values below the real catalog size are ignored
            (we never drop real tools); larger values pad with distractors.
    """
    servers = create_tool_knowledge_base()
    real_count = len(get_all_tools(servers))
    if num_tools and num_tools > real_count:
        servers = servers + make_distractor_servers(num_tools - real_count)
    return servers
```

短函数，两个不变量：

- `num_tools=0`（默认）→ **真实目录原样**，35 个工具 8 个 server。学习脚本用的就是 `build_catalog(0)`。
- **真实工具永远不会被丢掉**：`num_tools < 35` 时 `if` 不成立，静默返回 35 个；`num_tools > 35` 只补差量。所以"目录规模"这条自变量是单调的、可复现的，缩放表里的 35/50/100/200/400 都从同一批真实工具起步。
- `servers + make_distractor_servers(...)` 是**列表拼接**，把干扰 server 放在真实 server **之后**。这影响 `retrieve` 里的排序稳定性：分数相同时 `np.argsort` 的次序由数组位置决定，干扰项排在后面 → 平局时金标优先被保留。这是个隐性的有利偏差，写结论时要知道它存在。

#### `evaluate_offline`（L149–203）：本实验的确定性心脏

[chapter4/active-tool-selection/benchmark.py · L165–L203](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/benchmark.py#L165-L203)

```python title="chapter4/active-tool-selection/benchmark.py" linenums="165"
    tasks = tasks or BENCHMARK_TASKS
    router = SemanticRouter(servers)
    all_tools = get_all_tools(servers)
    all_tools_tokens = calculate_total_tokens(all_tools)

    per_task = []
    retrieval_hits = 0
    retrieval_tokens_sum = 0
    for t in tasks:
        retrieved = router.retrieve(t["task"], top_k)
        retrieved_names = [tool.name for tool in retrieved]
        hit = any(g in retrieved_names for g in t["gold_tools"])
        retrieval_hits += int(hit)
        retrieval_tokens_sum += calculate_total_tokens(retrieved)
        per_task.append({
            "name": t["name"],
            "gold_tools": t["gold_tools"],
            "retrieved": retrieved_names,
            "hit": hit,
        })

    n = len(tasks)
    return {
        "num_tools": len(all_tools),
        "top_k": top_k,
        "per_task": per_task,
        "strategies": {
            "all-tools": {
                "tools_in_context": len(all_tools),
                "avg_schema_tokens": all_tools_tokens,
                "recall": 1.0,
            },
            "retrieval": {
                "tools_in_context": top_k,
                "avg_schema_tokens": retrieval_tokens_sum / n,
                "recall": retrieval_hits / n,
            },
        },
    }
```

函数体只有 39 行，但"为什么这两个数字可以放在一张表里比"值得单独说清：

**（a）两条口径用的是同一个计量器。** all-tools 侧 `calculate_total_tokens(all_tools)` 与 retrieval 侧 `calculate_total_tokens(retrieved)` 是同一个函数，输入是同一批 `tool.to_schema()` dict。所以两列的单位完全一致，比值有意义。这是"可比"的**唯一**理由——不是因为字段名都叫 token。

**（b）但两列的统计含义不同，字段名在撒谎。** `all-tools` 的 `avg_schema_tokens` 里那个 `avg` 是名义上的：所有任务看到的是同一批 35 个 schema，它就是一个**目录常量**（单次注入成本），不是平均。`retrieval` 的 `avg_schema_tokens` 才是真的逐任务均值（`retrieval_tokens_sum / n`，10 个任务各自注入不同的一批工具）。把两者并列并不产生口径错位，因为"每个任务注入多少"这件事本身就是策略差异——但如果有人拿这两列去做 t 检验之类的事，就会把常数当成样本。

**（c）`tools_in_context` 那一列不能当实测值读。** `all-tools` 写的是真实的 `len(all_tools)`（35/200/400）；`retrieval` 直接写常量 `top_k`（=5）。而实测（本页复跑核对）10 个任务里 3 个只注入了 4 个工具（`Summary statistics`、`Deploy to production`、`Monitor service`），平均 4.7 个。原因是 `retrieve` 对每个 server 调 `_route_to_tools`，而**某些 server 的工具词表与 query 无交集时直接返回空**（`_route_to_tools` L184 的 `getnnz() == 0` 短路），于是全局候选池不足 top_k。所以"5"是名义上界，"516.6"是真实均值；同一行里一行是名义值一行是实测值，是本页最需要提防的读表陷阱。

**（d）`"recall": 1.0` 对 all-tools 是构造性成立的**：金标工具必然在"全部工具"里，所以恒等于 1。它不是一条测量结果，是恒等式。这条恒等式的价值只在于给 retrieval 的 1.00 提供一个"上界参照"——真正的问题是 retrieval 花了多少 token 换到这个 1.00（实测：86.6% 的削减）。

**（e）`active` 臂为什么不在离线表里**：它需要模型在环里声明能力缺口（见 docstring 与 3.4），没有模型就没有 `tool_request`，离线无从计算。所以离线表只有两行不是遗漏，是设计。

#### 辅助：`len(json)//4` 这个 token 近似器（tool_knowledge_base L612–624）

[chapter4/active-tool-selection/tool_knowledge_base.py · L604–L624](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/tool_knowledge_base.py#L604-L624)

```python title="chapter4/active-tool-selection/tool_knowledge_base.py" linenums="604"
def get_all_tools(servers: List[ServerDefinition]) -> List[ToolDefinition]:
    """Get flat list of all tools from all servers."""
    all_tools = []
    for server in servers:
        all_tools.extend(server.tools)
    return all_tools


def count_tokens_in_schema(schema: Dict[str, Any]) -> int:
    """Rough estimation of tokens in a tool schema (approximately 1 token per 4 characters)."""
    import json
    schema_str = json.dumps(schema)
    return len(schema_str) // 4


def calculate_total_tokens(tools: List[ToolDefinition]) -> int:
    """Calculate total tokens required to inject all tool schemas."""
    total = 0
    for tool in tools:
        total += count_tokens_in_schema(tool.to_schema())
    return total
```

这四行是整个离线结论的度量衡，所以它的误差就是结论的误差。三个必须知道的局限：

1. **它是"字符数 / 4"，不是 tokenizer**。经典经验值（英文≈4 字符/token）对**散文**成立，对 **JSON schema** 偏差更大：schema 里全是 `{"type": "string", "description": …}` 这类短词 + 密集标点，token 密度高于散文。本页复跑用 tiktoken 交叉核对过这个目录：35 个 schema 估 **3,857**，`cl100k_base` 实测 **4,070**、`o200k_base` **4,076** —— 即**低估约 5%**（比率 0.948）。所以在全英文目录上这个近似好到"结论不受影响"（86.6% vs 真实的 ~87.3%），但它终究是近似。
2. **`json.dumps` 默认 `ensure_ascii=True`，中文会被转义成 `\uXXXX`**。一个中文字符在 `dumps` 后变成 6 个 ASCII 字符，于是 `//4` 会把中文 schema 的 token 数**虚高约 1.5–6 倍**（视内容而定）。本目录全英文，恰好绕开了这个坑；**一旦给工具描述加中文，这个计量器就不可用了**，而且它会同时污染 all-tools 和 retrieval 两侧——比值可能还是"看起来合理"的，绝对值全错。
3. **逐工具 `//4` 再求和 ≠ 整体 `//4`**。`calculate_total_tokens` 对每个 schema 单独取整再累加（35 次向下取整），把所有 schema 拼成一个大字符串再 `//4` 会得到不同结果（本页核对：逐工具 3,857 vs 整体 3,887，差 30）。在线真实 prompt 里 schema 是作为一个 JSON 数组序列化的，所以严格说两侧都有 1% 级别的口径误差。**这不影响 any 结论**，但说明"精确到个位数的 token 对比"是伪精度。

一句话结论：**这个近似器足够支撑"全量注入随规模线性膨胀、检索式基本恒定"这个量级级结论，不足以支撑"省了 3,340 个 token"这种个位级陈述。**

### 3.2 `agent.py` · 第一臂：`ActiveToolAgent`（MCP-Zero 式主动发现）

#### `__init__`（L26–50）：客户端、目录、metrics 骨架

[chapter4/active-tool-selection/agent.py · L26–L50](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L26-L50)

```python title="chapter4/active-tool-selection/agent.py" linenums="26"
    def __init__(self, servers: Optional[List[ServerDefinition]] = None,
                 model: Optional[str] = None):
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL
        )
        self.model = model or config.OPENAI_MODEL

        # Initialize tool knowledge base (callers may inject a padded/custom catalog)
        self.servers = servers if servers is not None else create_tool_knowledge_base()
        self.router = SemanticRouter(self.servers)

        # Agent state
        self.conversation_history = []
        self.available_tools: List[ToolDefinition] = []  # Currently loaded tools
        self.tool_request_count = 0

        # Metrics
        self.metrics = {
            'tokens_used': 0,
            'tool_requests': 0,
            'tools_loaded': 0,
            'api_calls': 0,
            'tools_called': []  # Names of tools the model actually invoked
        }
```

三个关键点：

- **`OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)`**：端点和钥匙全部来自 `config`，而 `config` 在**导入期**读环境变量（见 3.4）。这里没有硬编码任何厂商——这是学习版能整体换到 DeepSeek 的结构前提。
- **`servers if servers is not None else create_tool_knowledge_base()`**：允许调用方注入放大后的目录。`_build_agent` 传的就是 `benchmark.build_catalog(num_tools)` 的结果，所以 `--num-tools 200` 时三条臂看到的是同一个 200 工具的目录。注意 `is not None`（不是 `or`）——传空列表会被当作有效目录，而不是回退到默认目录。
- **`available_tools` 初始为空**，`metrics['tokens_used']=0`。对比 `PassiveToolAgent.__init__`（L433 直接把 `tools_loaded` 设为 35）——**同一字段名在三臂里含义不同**，这张对照表见 3.5。

#### `execute_task`（L52–109）：整个实验最核心的 58 行

[chapter4/active-tool-selection/agent.py · L64–L109](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L64-L109)

```python title="chapter4/active-tool-selection/agent.py" linenums="64"
        self.conversation_history = []
        self.available_tools = []
        self.tool_request_count = 0
        
        # Initial system message explaining active tool discovery
        system_message = self._create_system_message()
        self.conversation_history.append({
            "role": "system",
            "content": system_message
        })
        
        # Add user task
        self.conversation_history.append({
            "role": "user",
            "content": task
        })
        
        # Iterative tool discovery and execution
        max_iterations = config.MAX_TOOL_REQUESTS
        for iteration in range(max_iterations):
            # Get agent response
            response = self._call_llm()
            self.metrics['api_calls'] += 1
            
            # Check if agent is requesting tools
            tool_request = StructuredRequestParser.parse_request(response)
            
            if tool_request:
                # Agent is requesting tools - discover and provide them
                self._handle_tool_request(tool_request, response)
                self.tool_request_count += 1
                self.metrics['tool_requests'] += 1
            else:
                # Agent has what it needs and is responding
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response
                })
                break
        
        return {
            'response': response,
            'metrics': self.metrics,
            'tools_loaded': [t.name for t in self.available_tools],
            'conversation': self.conversation_history
        }
```

逐行看这个循环（这是三条臂里唯一有循环的）：

- **L64–66 清了会话状态，但没清 `metrics`**。`self.metrics` 只在 `reset()`（L258）里重建。后果：如果调用方连调两次 `execute_task` 而不 `reset()`，`tokens_used` 与 `tools_called` 会**跨任务累加**，`tools_loaded` 也继续往上加。课程在线评测在每任务前显式调 `agent.reset()`（demo_comparison L351），所以数据干净；但你自己写脚本时必须记得这一步。学习脚本走的是课程 `run_online_benchmark`，所以它是对的。
- **L83 `for iteration in range(max_iterations)`，`max_iterations = config.MAX_TOOL_REQUESTS = 5`**（config.py L51）。这是硬上限：最多 5 轮"发言"。
- **L85 第 0 轮调用时 `available_tools` 为空** → `_call_llm` 里的 `if self.available_tools:` 不成立 → **不传 `tools` 参数、不传 `tool_choice`**。也就是说第一轮模型手里一个工具 schema 都没有，只能靠 system 提示里教的格式声明需求。这正是 MCP-Zero 的形态：上下文里零 schema。
- **L89 用 `parse_request` 判断这一轮是"请求工具"还是"最终答复"**，判据只有一个：回复里有没有合法的 `<tool_request>` 块（见 3.3 的 `parse_request`）。
- **L91–95 请求分支**：`_handle_tool_request` 负责检索 + 注入 + 回灌反馈，然后**计数器加一**。`tool_request_count`（实例字段）与 `metrics['tool_requests']` 同时加，两者永远相等——是历史遗留的重复记账，读数时任选一个。
- **L96–102 答复分支**：把模型这轮的输出当最终答复入历史并 `break`。
- **`break` 只在答复分支里**。如果 5 轮全部是工具请求（模型一直在要工具，从没给结论），循环自然结束，**返回的 `response` 是第 5 轮那段 `<tool_request>` 文本**，而不是任务结论。而且第 5 轮的反馈（"Tools discovered and loaded"）刚被 append 进历史，**再没有下一次调用去消费它**——模型永远看不到"你要的工具已经给你了"。这是"上限到了"时的真实失败形态：不是报错，是**安静地返回一段请求**。
- `metrics['api_calls'] += 1` 在循环里，所以它数的是**循环轮数**，不是 HTTP 调用数（`_handle_tool_calls` 内部的递归调用不计，见 3.5）。

#### `_create_system_message`（L111–135）：把"要工具"变成一种协议

[chapter4/active-tool-selection/agent.py · L113–L135](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L113-L135)

```python title="chapter4/active-tool-selection/agent.py" linenums="113"
        return """You are an autonomous AI agent with active tool discovery capabilities.

Instead of having all possible tools available upfront, you can actively request tools as you need them. This allows you to:
1. Maintain a minimal context footprint
2. Focus on relevant capabilities for the current task
3. Iteratively build your toolchain as your understanding evolves

When you identify a capability gap, request tools using this format:

<tool_request>
server: [describe the platform/domain you need, e.g., "GitHub for repository operations" or "filesystem for local file access"]
tool: [describe the specific operation you need, e.g., "search repositories" or "read file contents"]
</tool_request>

After requesting tools, they will be provided to you. You can then use them to accomplish the task.

Process:
1. Analyze the task and identify what capabilities you need
2. Request specific tools if you don't have them yet
3. Once you have the necessary tools, use them to complete the task
4. Respond with your findings or results

Current available tools: None (request tools as needed)"""
```

这段提示词定义了三件事，每一件都直接决定实测结果：

1. **协议**：`<tool_request>` + `server:` + `tool:` 两行。这是 `parse_request` 要解析的唯一合法格式——没有这个块，这一轮就被当成最终答复。
2. **示例措辞**：`"GitHub for repository operations"`、`"filesystem for local file access"`。这些例子是**英文域描述**，直接决定了模型会产出什么样的 query 去做 TF-IDF 检索。**推断**：这也是 active 臂在实测中跑偏的根源之一——模型按模板写出 `"filesystem for local file access"`，而被检索的 server 描述是 `"Local filesystem operations for reading, writing, and managing files"`，词面重叠只有 `filesystem`/`file`；一旦 query 落到词表无交集的 server 上，`_route_to_tools` 直接返回空（L184），这一轮就等于白问。
3. **`Current available tools: None (request tools as needed)`**：字面告诉模型"你现在什么都没有"。所以模型第 0 轮**必须**发请求（否则它没有任何工具可用），这保证了 MCP-Zero 的"先声明、后获得"节奏一定被触发。

另外注意 system 里**只有这段文字，没有任何工具清单**——对比 `RetrievalToolAgent.execute_task` 会把 top-k 工具的"名字 + 描述"纯文本列进 system（L316–324），`PassiveToolAgent` 则连清单都不列（只说"你有 35 个工具"），工具全部走 API 的 `tools` 参数。三臂"模型能看到什么"其实差得很细，读在线数据时必须记住这点。

#### `_call_llm`（L137–165）：token 记账就在这三行

[chapter4/active-tool-selection/agent.py · L137–L165](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L137-L165)

```python title="chapter4/active-tool-selection/agent.py" linenums="137"
    def _call_llm(self) -> str:
        """Call LLM with current context and available tools."""
        kwargs = {
            "model": self.model,
            "messages": self.conversation_history,
            "temperature": config.AGENT_TEMPERATURE
        }

        # Add tools if available
        if self.available_tools:
            kwargs["tools"] = [tool.to_schema() for tool in self.available_tools]
            kwargs["tool_choice"] = "auto"
        
        response = self.client.chat.completions.create(**kwargs)
        
        # Track token usage
        # response.usage is Optional in the OpenAI SDK: the attribute always
        # exists, but is None when the provider omits token accounting.
        if getattr(response, 'usage', None):
            self.metrics['tokens_used'] += response.usage.total_tokens
        
        # Extract response content
        message = response.choices[0].message
        
        # Handle tool calls if present
        if message.tool_calls:
            return self._handle_tool_calls(message)
        
        return message.content or ""
```

- **`temperature: config.AGENT_TEMPERATURE` 是"调用时"读模块属性**，不是导入时快照。这行是学习版能把温度归零的依据（3.4）。
- **`if self.available_tools:` 决定了 schema 何时进上下文**。active 臂第一次真的把 schema 放进请求，是**第二次**调用（第一次请求被检索满足之后）。这解释了为什么 active 臂的 token 不是"0"而是几千——它仍要把检索到的 schema 完整注入。
- **`getattr(response, 'usage', None)` 这个防御**（注释里写得很明确）针对的是"某些 provider 不返回 token 计量"。`usage` 属性一定存在但可能是 `None`，直接 `.total_tokens` 会 `AttributeError`。DeepSeek 返回 usage，所以这个分支在实测里一直是真。`tests/test_usage_none.py` 就是为它写的回归测试——文件开头的 docstring 点名了旧写法 `hasattr(response, 'usage')` **无效**（属性永远存在，`hasattr` 恒真），必须用 `getattr(...) is not None` 才能挡住。**读源码时这类"注释解释了为什么"的位置，通常都对应一条血泪测试。**
- **`total_tokens` 是 prompt + completion 之和**——不是"上下文 token"，它包含模型输出。所以"active 臂 4,956 token"里有一部分是模型啰嗦的解释文本，不能全算到 schema 上。这是拿在线 token 数字跟离线 schema token（3,857）直接比时的最大陷阱：**两者根本不是同一个量**。
- 附带一个测试钩子：三臂都把客户端存在 `self.client`，`test_usage_none.py` 直接把它换成 `SimpleNamespace` 假客户端就完成了"零 API 单测"。所以要验证你对记账逻辑的理解，不需要花任何 API 费。
- **`if message.tool_calls: return self._handle_tool_calls(message)`**：递归，没有深度上限。模型连续 8 轮发 tool_calls 就递归 8 层（active 臂实测 `Deploy to production` 那格共记了 11 次工具调用）。每次递归都走一遍 `usage` 累加，所以 token 是准的；但 `api_calls` 不动（见 3.5）。
- `return message.content or ""`：`content` 可能是 `None`（纯 tool_calls 的响应），转成空串。**空串会让 `parse_request` 返回 `None`**，于是 active 的循环把这一轮当成"最终答复"并 break——`response` 就成了空字符串。这是"模型只发工具调用、不说话"时的静默终止路径。

#### `_handle_tool_request`（L167–212）：检索 → 注入 → 回灌

[chapter4/active-tool-selection/agent.py · L175–L202](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L175-L202)

```python title="chapter4/active-tool-selection/agent.py" linenums="175"
        # Combine server and tool descriptions for routing
        query = f"{tool_request['server']} {tool_request['tool']}"
        
        # Use semantic router to find relevant tools
        discovered_tools = self.router.route_request(query)
        
        if not discovered_tools:
            # No tools found
            feedback = f"""No tools found matching your request. Please refine your request or proceed without additional tools.

Your request was:
- Server: {tool_request['server']}
- Tool: {tool_request['tool']}"""
        else:
            # Add discovered tools to available tools
            new_tools = []
            for tool in discovered_tools:
                if tool not in self.available_tools:
                    self.available_tools.append(tool)
                    new_tools.append(tool)
                    self.metrics['tools_loaded'] += 1
            
            tool_list = "\n".join([f"- {t.name}: {t.description}" for t in new_tools])
            feedback = f"""Tools discovered and loaded ({len(new_tools)} new tools):

{tool_list}

You can now use these tools to complete the task. Please proceed."""
        
        # Add agent's request and system's response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": full_response
        })
        self.conversation_history.append({
            "role": "user",
            "content": feedback
        })
```

- **L176 把两段描述拼成一个 query**：`"filesystem for local file access read file contents"`。这是整个 active 臂的唯一检索输入——模型自己写的字面句子，没有改写、没有扩展。**推断**：这是 active 臂最脆的一环（见 3.3 的 TF-IDF 词表限制）。
- **L179 `route_request(query)` 用默认参数** → `top_k_servers=config.TOP_K_SERVERS=3`、`top_k_tools=config.TOP_K_TOOLS=5`，且**带 0.15 相似度阈值**。所以一次请求最多塞进 15 个工具（`3 × 5`，见 3.3 的 `route_request` 返回值）。**这与离线/retrieval 臂的 `retrieve` 完全不同**：`retrieve` 无阈值、只取全局 top-k。**两条臂的检索行为不一样**，这是本实验最容易读漏的一处不对称。
- **L181–187 空结果分支**：返回"没找到，请改述或不用工具继续"。这不是异常，是正常返回——实测里 active 臂两次任务（Send email / Scrape prices）最终 `tools_called` 为空，很可能就停在这条路径上。
- **L191–195 去重靠 `tool not in self.available_tools`，即对象身份比较**（`ToolDefinition` 没定义 `__eq__`）。因为路由器返回的就是 `self.servers` 里的**同一批对象**，身份比较成立且高效。但这也意味着：如果你给 agent 传一份目录、给 router 传另一份**内容相同但对象不同**的目录，去重会失效、同一个工具会被加载两次、`tools_loaded` 会虚高。
- **`metrics['tools_loaded'] += 1` 只在新增时加** → active 臂的 `tools_loaded` 是"整个任务累计去重加载数"，不是"当前上下文里的工具数"（后者才是 `len(available_tools)`，但没被单独记账）。而 `execute_task` 返回的 `tools_loaded` 字段（L107）是**名字列表** `[t.name for t in self.available_tools]`，与 metrics 里那个整数**同名不同物**。读在线表时 `Avg tools in ctx` 用的是 `metrics['tools_loaded']`（demo_comparison L361）——对 active 臂来说它其实偏大（累计 vs 当前）。

#### `_handle_tool_calls`（L214–256）：模拟执行与 `tools_called`

[chapter4/active-tool-selection/agent.py · L218–L228](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L218-L228)

```python title="chapter4/active-tool-selection/agent.py" linenums="218"
        tool_results = []
        
        for tool_call in message.tool_calls:
            func_name = tool_call.function.name
            self.metrics['tools_called'].append(func_name)

            # Simulate tool execution
            result = f"[Simulated] Tool '{func_name}' executed successfully with result: Success"
            tool_results.append({
                "tool_call_id": tool_call.id,
                "output": result
            })
```

**这个实验里没有工具真的被执行。** `result` 是一段固定字符串，`tools_called` 只是把模型发出的调用名记下来。这对结论的影响必须说清：

- 判定"命中金标"只看**名字**（demo_comparison L357），不看参数对不对、不看结果——所以在线准确率是"**选对了工具**"的指标，不是"**任务完成**"的指标。按这个基准的任务（如"部署 2.3.0 到生产"），一个只调对工具但参数乱填的模型也算命中。**诚实边界：本页所有"命中率"都应读成"选对率"。**
- 因为执行是模拟的，模型拿到 `Success` 后通常会再补一段总结文本，那第二轮调用的 token 也算进 `tokens_used`。所以各臂 token 里包含"拿到假结果后的废话"。

结构上剩下两件事（L230–253 把 assistant 的 tool_calls 与 tool 结果按 OpenAI 协议格式回灌历史；L256 **递归** `return self._call_llm()` 取最终答复）。回灌的 dict 是手写的（`content: None` + `tool_calls` 数组），而不是直接把 SDK 的 `message` 对象塞回去——**`None` 是必须的**，OpenAI 兼容协议要求带 `tool_calls` 的消息 `content` 为 `null`；很多自建 agent 在这里传 `""` 而被后端拒绝。

#### `reset`（L258–269）

[chapter4/active-tool-selection/agent.py · L258–L269](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L258-L269)

```python title="chapter4/active-tool-selection/agent.py" linenums="258"
    def reset(self):
        """Reset agent state."""
        self.conversation_history = []
        self.available_tools = []
        self.tool_request_count = 0
        self.metrics = {
            'tokens_used': 0,
            'tool_requests': 0,
            'tools_loaded': 0,
            'api_calls': 0,
            'tools_called': []
        }
```

重建整个 metrics 字典（不是逐字段归零）——这样最容易看清"一次任务 = 一份全新账本"。**`reset()` 不重建 `client` 和 `router`**：路由器的 TF-IDF 嵌入是 `__init__` 里预计算好的一次性成本，换任务复用，正是它能"零 API 成本检索"的原因。在线评测在每任务前调它（L351），这是三臂数据可比的前提。

### 3.3 `agent.py` · 第二臂与第三臂：`RetrievalToolAgent` / `PassiveToolAgent`

#### `RetrievalToolAgent.__init__`（L287–306）：多一个 `top_k`

[chapter4/active-tool-selection/agent.py · L294–L306](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L294-L306)

```python title="chapter4/active-tool-selection/agent.py" linenums="294"
        self.top_k = top_k if top_k is not None else config.TOP_K_TOOLS

        self.servers = servers if servers is not None else create_tool_knowledge_base()
        self.router = SemanticRouter(self.servers)

        self.conversation_history = []
        self.available_tools: List[ToolDefinition] = []
        self.metrics = {
            'tokens_used': 0,
            'tools_loaded': 0,
            'api_calls': 0,
            'tools_called': []
        }
```

- **`top_k if top_k is not None else config.TOP_K_TOOLS`**：同样是 `is not None` 而非 `or`，所以 `top_k=0` 是合法输入（会检索出 0 个工具，退化成"无工具纯聊天"），不会被静默替换成 5。
- **metrics 少一项**：没有 `tool_requests`（这条臂不请求），其余三项与 active 同名。
- **`self.router = SemanticRouter(self.servers)` 在 `__init__` 里就建好**：TF-IDF 预计算只做一次，之后每个任务检索都是纯矩阵运算，零网络成本。这是"检索式省 token 不省时间"里"省"的那一半。

#### `RetrievalToolAgent.execute_task`（L308–337）：一次检索 + 一次决策

[chapter4/active-tool-selection/agent.py · L308–L337](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L308-L337)

```python title="chapter4/active-tool-selection/agent.py" linenums="308"
    def execute_task(self, task: str) -> Dict[str, Any]:
        """Retrieve top-k relevant tools for the task, then execute in one shot."""
        self.conversation_history = []

        # Retrieval step (no LLM call): pick the top-k most relevant tools.
        self.available_tools = self.router.retrieve(task, self.top_k)
        self.metrics['tools_loaded'] = len(self.available_tools)

        tool_list = "\n".join(
            f"- {t.name}: {t.description}" for t in self.available_tools
        )
        system_message = f"""You are an AI agent. A retrieval system has pre-selected the \
{len(self.available_tools)} tools below as most relevant to the user's task.

{tool_list}

Analyze the task and call the appropriate tool(s) to complete it."""

        self.conversation_history.append({"role": "system", "content": system_message})
        self.conversation_history.append({"role": "user", "content": task})

        response = self._call_llm()
        self.metrics['api_calls'] += 1

        return {
            'response': response,
            'metrics': self.metrics,
            'tools_loaded': [t.name for t in self.available_tools],
            'conversation': self.conversation_history
        }
```

这条臂的全部机制就是这 30 行，对比另外两条：

- **检索用的是 `retrieve`（全局平坦 top-k，无阈值）**，与离线表用的是**同一个函数、同一套参数**（`top_k` 同值）。所以离线 `retrieval` 行报的 recall 与在线 retrieval 臂看到的东西是严格对应的——这是本实验里唯一一处"离线预测在线"的合法对齐点。
- **`metrics['tools_loaded'] = len(...)` 用赋值而非累加**：每次任务重设，所以这个数字是"本轮注入数"（实测 4–5）。三臂里它最干净。
- **system 里额外用纯文本列了一遍工具名 + 描述**（L316–322）。这意味着检索到的工具被**说了两遍**：一次在 system 文本里、一次在 API 的 `tools` 参数里。所以 retrieval 臂的真实 prompt token 会比离线估的 `516.6` 高一些（实测单次调用约 983 token 总量，含任务、清单、输出）。**这是离线 token 与在线 token 不可直接相减的第二个原因**（第一个见 3.2 的 `total_tokens` 口径）。
- **没有循环、没有第二轮**：`response = self._call_llm()` 之后直接返回。如果模型没调工具（实测 `Upload to cloud` 那格 `called=[]`），就没有任何补救机会——**"一次性检索"的失败是不可恢复的**。这是它相对 active 臂的结构性缺点，也是它在小目录上仍然最快最省的原因。
- `tools_loaded` 返回值同样是名字列表（L335），与 metrics 里的整数同名不同物——三臂都这样。

#### `RetrievalToolAgent._call_llm` / `_handle_tool_calls` / `reset`（L339–L403）

[chapter4/active-tool-selection/agent.py · L346–L360](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L346-L360)

```python title="chapter4/active-tool-selection/agent.py" linenums="346"
        if self.available_tools:
            kwargs["tools"] = [tool.to_schema() for tool in self.available_tools]
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)

        # response.usage is Optional in the OpenAI SDK: the attribute always
        # exists, but is None when the provider omits token accounting.
        if getattr(response, 'usage', None):
            self.metrics['tokens_used'] += response.usage.total_tokens

        message = response.choices[0].message
        if message.tool_calls:
            return self._handle_tool_calls(message)
        return message.content or ""
```

与 Active 的 `_call_llm` **逐字相同**（只有注释与所在类不同）——三份拷贝的第一份。`_handle_tool_calls`（L362–392）也一样，只有模拟结果文案短了一截：`"[Simulated] Tool '{func_name}' executed successfully"`（无 `with result: Success`）。这个差别对结论没有影响，但它证明了两段代码是从同一份粘出来的。`reset`（L394–403）与 Active 的差别是没有 `tool_requests` 键。

#### `PassiveToolAgent.__init__`（L416–436）：全量摊平

[chapter4/active-tool-selection/agent.py · L426–L436](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L426-L436)

```python title="chapter4/active-tool-selection/agent.py" linenums="426"
        self.all_tools = []
        for server in self.servers:
            self.all_tools.extend(server.tools)

        self.conversation_history = []
        self.metrics = {
            'tokens_used': 0,
            'tools_loaded': len(self.all_tools),
            'api_calls': 0,
            'tools_called': []
        }
```

- **`self.all_tools` 是 `get_all_tools` 的手写版**（同样的两行循环，见 tool_knowledge_base L604–609）。这条臂**不建 router**——它不需要检索，这也是它唯一比另两臂省掉的东西。
- **`tools_loaded` 在 `__init__` 里就固定为目录总量**（35/200/400），且任务间不变。所以在线表里 all 臂的 `Avg tools in ctx` 恒等于目录规模，它测的是"全量注入"这个常量本身。
- 没有 `available_tools` 字段（三条臂的字段名不统一：`all_tools` vs `available_tools`），`reset`（L533–541）里也只重设 `tools_loaded = len(self.all_tools)`。

#### `PassiveToolAgent.execute_task`（L438–466）：没有循环的基线

[chapter4/active-tool-selection/agent.py · L438–L466](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/agent.py#L438-L466)

```python title="chapter4/active-tool-selection/agent.py" linenums="438"
    def execute_task(self, task: str) -> Dict[str, Any]:
        """Execute task with all tools pre-loaded."""
        self.conversation_history = []
        
        # System message
        system_message = f"""You are an AI agent with access to {len(self.all_tools)} tools across multiple domains.

All available tools have been pre-loaded. Analyze the task and use the appropriate tools to complete it."""
        
        self.conversation_history.append({
            "role": "system",
            "content": system_message
        })
        
        self.conversation_history.append({
            "role": "user",
            "content": task
        })
        
        # Call LLM with ALL tools
        response = self._call_llm()
        self.metrics['api_calls'] += 1
        
        return {
            'response': response,
            'metrics': self.metrics,
            'tools_loaded': [t.name for t in self.all_tools],
            'conversation': self.conversation_history
        }
```

最短的一条臂：**system 里只说"你有 35 个工具"（工具名和描述都不进文本），schema 全部走 `tools` 参数**。这跟 retrieval 臂"文本里也列一遍"形成对照——意味着 all 臂的 prompt 里工具信息只出现一次，而 retrieval 臂出现两次。如果要比"同样的工具数、同样的注入方式"，这个差异是个瑕疵（**推断**：它会让 retrieval 臂的绝对 token 略高于"纯 schema 注入"应有的值，但由于它只注入 5 个工具，量级上无关紧要）。

`_call_llm`（L468–492）与前两臂唯一的结构差别是 `tools` 参数**无条件**传（`"tools": [tool.to_schema() for tool in self.all_tools]`），没有 `if`。这是"全量注入"在代码里的字面体现：`PassiveToolAgent._call_llm` 是这个文件里唯一一处必然把整目录 schema 发给模型的调用点。

### 3.4 `semantic_router.py`：TF-IDF 到底在做什么

#### `SemanticRouter.__init__`（L23–32）：一次预计算

[chapter4/active-tool-selection/semantic_router.py · L23–L32](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/semantic_router.py#L23-L32)

```python title="chapter4/active-tool-selection/semantic_router.py" linenums="23"
    def __init__(self, servers: List[ServerDefinition]):
        self.servers = servers
        self.server_vectorizer = TfidfVectorizer(stop_words='english')
        self.tool_vectorizers: Dict[str, TfidfVectorizer] = {}
        
        # Precompute server embeddings
        self._build_server_index()
        
        # Precompute tool embeddings for each server
        self._build_tool_indices()
```

**"semantic" 是名不副实的**：这里没有 embedding 模型、没有神经网络，只有 sklearn 的 TF-IDF 词袋 + 余弦相似度。`tfidf` 也只能靠**词面重叠**匹配——`Deploy version 2.3.0` 能匹配上 `devops_deploy`，是因为二者共享 `deploy`；如果把任务改成"上线新版本"，它会全线崩溃。**推断**：这解释了为什么基准任务必须写成英文且刻意复用语料词（`BENCHMARK_TASKS` 的注释也承认了这一点）。

`stop_words='english'` 去掉 `the/a/for/of` 等高频词。**关键细节**：整个类有 **1 + N 个独立的向量器**（1 个 server 级 + 每个 server 一个 tool 级），每个都有自己的词表和 IDF。所以"server 相似度"和"tool 相似度"是两个不同向量空间里的数，却按 0.3/0.7 线性加权（L95/L130）——**推断**：这是个工程启发式，不是有概率意义的融合；它的合理性仅在于两个都是 [0,1] 的余弦值，尺度可比。

#### `_build_server_index`（L34–43）与 `_build_tool_indices`（L45–65）

[chapter4/active-tool-selection/semantic_router.py · L34–L65](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/semantic_router.py#L34-L65)

```python title="chapter4/active-tool-selection/semantic_router.py" linenums="34"
    def _build_server_index(self):
        """Build TF-IDF index for servers."""
        if not self.servers:
            self.server_embeddings = None
            return
        server_descriptions = [f"{s.name} {s.description}" for s in self.servers]
        try:
            self.server_embeddings = self.server_vectorizer.fit_transform(server_descriptions)
        except ValueError:
            self.server_embeddings = None
    
    def _build_tool_indices(self):
        """Build TF-IDF indices for tools within each server."""
        for server in self.servers:
            if not server.tools:
                continue
            
            tool_descriptions = [
                f"{tool.name} {tool.description}"
                for tool in server.tools
            ]
            
            vectorizer = TfidfVectorizer(stop_words='english')
            try:
                embeddings = vectorizer.fit_transform(tool_descriptions)
            except ValueError:
                embeddings = None
            
            self.tool_vectorizers[server.name] = vectorizer
            
            # Store embeddings on server for later use
            server._tool_embeddings = embeddings
```

三个必须记住的实现细节：

1. **被向量化的文本是 `name + " " + description`**（L39、L52）。所以工具名里的 `github_search_repos` 会以下划线切分成 `github`/`search`/`repos` 参与打分（sklearn 默认 `token_pattern=r"(?u)\b\w\w+\b"`，下划线算词内字符，实际切出 `github_search_repos` 整体作为 token）。这既是金标能被命中的原因（`fs_read_file` 与 task 里的 `file` 不一定重叠，但描述里的 `file` 会），也是不可能跨语言的原因。
2. **`fit_transform` 的 `ValueError` 被吞掉**（L42–43、L59–60）：空词表（例如某 server 的描述全是停用词）会让 sklearn 抛 `ValueError`，代码把它转成 `embeddings=None`，随后 `_route_to_tools` 的 `getattr(server, "_tool_embeddings", None) is None` 检查（L174）兜住。**没有日志、没有告警**——目录里如果有 server 静默失效，你只会看到"检索结果莫名变少"。
3. **嵌入直接挂在 `server._tool_embeddings` 上**（L65）：给数据对象动态加私有属性，而不是在 router 里维护 `Dict[name, emb]`。后果：**同一个 `servers` 列表被两个 `SemanticRouter` 实例使用时，后建的会覆盖先建的嵌入**（同一个 `ToolDefinition` 对象上只留一份）。三臂都是单 router，所以实测无碍；但这是并行/复用场景下的隐患。

#### `retrieve`（L108–134）：retrieval 臂与离线表用的就是这个

[chapter4/active-tool-selection/semantic_router.py · L124–L134](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/semantic_router.py#L124-L134)

```python title="chapter4/active-tool-selection/semantic_router.py" linenums="124"
        # Score against every server so no candidate tool is filtered out prematurely.
        relevant_servers = self._route_to_servers(query, len(self.servers))

        scored_tools = []
        for server, server_score in relevant_servers:
            for tool, tool_score in self._route_to_tools(server, query, len(server.tools)):
                combined_score = 0.3 * server_score + 0.7 * tool_score
                scored_tools.append((tool, combined_score))

        scored_tools.sort(key=lambda x: x[1], reverse=True)
        return [tool for tool, _ in scored_tools[:top_k]]
```

- **`_route_to_servers(query, len(self.servers))`**：把 top-k 设成 server 总数 → **不过滤 server**，每个 server 都参与。这是它跟 `route_request` 的第一处不同。
- **`_route_to_tools(server, query, len(server.tools))`**：top-k 设成该 server 的工具数 → **不过滤工具**。第二处不同。
- **合并分 `0.3 * server_score + 0.7 * tool_score`**：域分数占三成、工具分数占七成。工具的分数权重更高，是因为同一域内还要在 5 个工具里挑对那一个——但注意 `tool_score` 来自该 server 自己的小词表，一个常见词（`file`）在小词表里 IDF 更低、绝对分数更不稳定。**推断**：换目录后 0.3/0.7 未必最优，但本实验没做这组消融。
- **`scored_tools[:top_k]` 没有阈值过滤**。所以 `retrieve` **总是**返回 min(top_k, 候选池) 个工具，哪怕最高分只有 0.01。这是 retrieval 臂离线 recall 1.00 的直接原因，也是它跟 active 臂（`route_request` 带 0.15 阈值）最本质的行为差异。**同一个类的两个方法，一个敢给"最不相关的前 5 名"，一个宁可返回空**——三臂的实测差异有一半出自这里。
- 排序用 Python 的 `list.sort`（稳定排序），平局保持 `scored_tools` 的插入顺序，也就是 server 遍历顺序 × 工具顺序。这就是 3.1 提到的"真实工具在平局时优先"的机制。

#### `route_request`（L67–106）：active 臂用的那条路

[chapter4/active-tool-selection/semantic_router.py · L80–L106](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/semantic_router.py#L80-L106)

```python title="chapter4/active-tool-selection/semantic_router.py" linenums="80"
        if top_k_servers is None:
            top_k_servers = config.TOP_K_SERVERS
        if top_k_tools is None:
            top_k_tools = config.TOP_K_TOOLS
        
        # Stage 1: Server-level routing
        relevant_servers = self._route_to_servers(tool_request, top_k_servers)
        
        # Stage 2: Tool-level routing within selected servers
        relevant_tools = []
        for server, server_score in relevant_servers:
            tools_with_scores = self._route_to_tools(server, tool_request, top_k_tools)
            
            # Combine server and tool scores
            for tool, tool_score in tools_with_scores:
                combined_score = 0.3 * server_score + 0.7 * tool_score
                relevant_tools.append((tool, combined_score))
        
        # Sort by combined score and filter by threshold
        relevant_tools.sort(key=lambda x: x[1], reverse=True)
        relevant_tools = [
            (tool, score) for tool, score in relevant_tools 
            if score >= config.SIMILARITY_THRESHOLD
        ]
        
        # Return top tools
        return [tool for tool, _ in relevant_tools[:top_k_tools * top_k_servers]]
```

与 `retrieve` 的三处差异，逐条都影响 active 臂的实测：

1. **默认 `top_k_servers=3`（config L55）**：先在 8 个 server 里挑 3 个，**只有这 3 个 server 的工具进入候选池**。如果模型请求的域被排到第 4 名，正确答案直接出局——这是"两层路由降低搜索复杂度"的代价，也是 MCP-Zero 论文里"层级路由"的核心权衡。
2. **`score >= config.SIMILARITY_THRESHOLD`（0.15，config L54）**：这是一个**绝对**阈值，而 TF-IDF 余弦分数量纲依赖词表大小与 IDF，并不跨目录可比。目录换成 200 工具后，同一个 query 的分数分布会整体变化，但 0.15 是不变的。**推断**：这是 active 臂在放大目录时最可能失效的地方（本页的缩放测试只跑了离线两臂，没测 active，所以这条是推断）。
3. **返回上限是 `top_k_tools * top_k_servers = 5 × 3 = 15`**：一次请求最多 15 个工具。**推断**：这解释了 active 臂在线 token 为什么居中（4,956）——比 retrieval 的一次 5 个多得多（因为可能一次塞 15 个），但比 all 的一次 35 个少。

#### `_route_to_servers`（L136–159）与 `_route_to_tools`（L161–193）：两层打分

[chapter4/active-tool-selection/semantic_router.py · L147–L159](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/semantic_router.py#L147-L159)

```python title="chapter4/active-tool-selection/semantic_router.py" linenums="147"
        if not self.servers:
            return []
        if self.server_embeddings is None:
            return [(server, 0.0) for server in self.servers[:top_k]]
        # Vectorize the request
        request_vector = self.server_vectorizer.transform([request])
        # Calculate similarities with all servers
        similarities = cosine_similarity(request_vector, self.server_embeddings)[0]
        
        # Get top-k servers
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        return [(self.servers[idx], similarities[idx]) for idx in top_indices]
```

- **`server_embeddings is None` 的降级路径**（L149–150）：向量器失效时不做检索，直接返回前 `top_k` 个 server 并给 0 分。**注意此时分数是 0.0**，到 `route_request` 的阈值过滤那一关会被全部砍掉（0.0 < 0.15）→ 返回空。所以"索引构建失败"的最终表现是"检索永远返回空"，而不是"报错"。**这是本文件最危险的静默失败路径**：一条 `except ValueError` 吞掉的异常，最后表现为 agent 说"我要工具"— "没找到工具"— 反复 5 轮。
- **`np.argsort(similarities)[::-1][:top_k]`** 是标准的"降序取 top-k"（先升序 argsort 再反转）。`np.argsort` 默认不稳定（quicksort），**理论上平局次序不确定**——但因为本例所有分数极少完全相等，实测输出是逐次可复现的（本页两次复跑，per-task 明细完全一致）。

[chapter4/active-tool-selection/semantic_router.py · L174–L193](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/semantic_router.py#L174-L193)

```python title="chapter4/active-tool-selection/semantic_router.py" linenums="174"
        if server.name not in self.tool_vectorizers or getattr(server, "_tool_embeddings", None) is None:
            return []
        
        vectorizer = self.tool_vectorizers[server.name]
        tool_embeddings = server._tool_embeddings
        if tool_embeddings is None:
            return []
        
        # Vectorize the request
        request_vector = vectorizer.transform([request])
        if request_vector.getnnz() == 0:
            return []
        
        # Calculate similarities with all tools in this server
        similarities = cosine_similarity(request_vector, tool_embeddings)[0]
        
        # Get top-k tools
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        return [(server.tools[idx], similarities[idx]) for idx in top_indices]
```

**L184 的 `getnnz() == 0` 短路是理解离线表"5 vs 4.7"的钥匙**：`transform` 出来的 query 向量，如果它的每个词都不在该 server 的词表里，就是全零向量。全零向量的余弦相似度是 0（sklearn 会照算不误，不会报错），但代码选择**直接返回空**——省掉一次无意义计算，同时把"这个词表不匹配"和"匹配但分数为 0"两种情况合并了。后果就是实际注入的工具数可能少于 top_k（本页实测 10 个任务里 3 个只拿到 4 个），而离线表 `tools_in_context` 那列仍写 `top_k`（见 3.1 的 (c)）。

#### `get_routing_details`（L195–246）：调试窗口

[chapter4/active-tool-selection/semantic_router.py · L230–L246](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/semantic_router.py#L230-L246)

```python title="chapter4/active-tool-selection/semantic_router.py" linenums="230"
        # Sort and filter
        all_tools.sort(key=lambda x: x[1], reverse=True)
        final_tools = [
            {'name': tool.name, 'server': server, 'score': score}
            for tool, score, server in all_tools[:top_k_tools * top_k_servers]
            if score >= config.SIMILARITY_THRESHOLD
        ]
        
        return {
            'request': tool_request,
            'stage1_servers': [
                {'name': s.name, 'score': score} 
                for s, score in relevant_servers
            ],
            'stage2_tools': stage2_results,
            'final_tools': final_tools
        }
```

逻辑与 `route_request` 基本重复（同样的 0.3/0.7、同样的阈值、同样的 `top_k_tools * top_k_servers` 上限），区别只在于**把两层分数原样交出来**，供 `demo_semantic_routing`（demo_comparison L161–193）打印。**学习价值**：这是理解 active 臂为什么选错域的唯一现成工具——把模型的 `<tool_request>` 原文喂进这个方法，你能一眼看到 stage1 里正确 server 排第几。本页没跑它（它需要 API 才能拿到真实的模型请求文本），但它是排查 active 臂的首选手段。

#### `StructuredRequestParser.parse_request`（L261–284）：自然语言 → 结构化查询

[chapter4/active-tool-selection/semantic_router.py · L267–L284](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/semantic_router.py#L267-L284)

```python title="chapter4/active-tool-selection/semantic_router.py" linenums="267"
        if '<tool_request>' not in text:
            return None
        
        start = text.find('<tool_request>')
        end = text.find('</tool_request>', start + len('<tool_request>'))
        if end == -1:
            return None
        request_text = text[start + len('<tool_request>'):end].strip()
        
        result = {}
        for line in request_text.split('\n'):
            line = line.strip()
            if line.startswith('server:'):
                result['server'] = line[7:].strip()
            elif line.startswith('tool:'):
                result['tool'] = line[5:].strip()
        
        return result if 'server' in result and 'tool' in result else None
```

这是 MCP-Zero 协议里"模型说什么"到"系统怎么查"的翻译层。五个设计决定：

1. **返回 `dict` 或 `None`，二值判定**。`None` 不只是"解析失败"，它就是 active 循环的**终止信号**（`execute_task` L96 的 else 分支）。所以这个函数的误判方向很重要：**把合法请求误判成 `None` 会让 agent 提前收工**；把普通回答误判成请求会让它多跑一轮（浪费 token，但不会错）。
2. **`'<tool_request>' in text` 的先决检查**（L267）：绝大多数回复（纯文本答复）在第一个字符判断处就返回 `None`，这是热路径。
3. **`</tool_request>` 从 `start + len('<tool_request>')` 之后开始找**（L271）。这不是可有可无的保险：如果从 0 开始找，**正文里先提到一次 `</tool_request>`**（比如模型在解释格式："不要只写 `</tool_request>`"）就会让 `end` 落在开标签之前，切出来的 `request_text` 变成垃圾或空串，`server:`/`tool:` 都解析不到，请求被误判成最终答复。`tests/test_parse_request_closing_tag.py` 就是为这条逻辑写的回归测试，测试文本的第一行正是 `"Note: Do not format as </tool_request> without an opening tag."`——**每个看起来多余的防御，背后都有一段具体输入**。
4. **缺收尾标签 → `None`**（L272–273）：模型忘了写 `</tool_request>` 的常见毛病不会被容忍，这一轮被当成"最终答复"提前结束。**推断**：这可能是实测里 active 臂某几格失败的原因之一（`Scrape prices`/`Send email` 两次零工具调用、且只有 1.7K token，像是第一轮就退出了）。
5. **必须同时有 `server:` 和 `tool:` 两行**（L284）：只写一行返回 `None`。行内前缀匹配用 `startswith('server:')`（冒号后可有空格），值再 `strip()` —— **冒号后面紧跟中文全角冒号或没有空格都能容忍，但前缀必须是小写英文**。模型若写 `Server:` 就解析不到。

#### `StructuredRequestParser.format_request`（L287–292）

[chapter4/active-tool-selection/semantic_router.py · L287–L292](https://github.com/bojieli/ai-agent-book/blob/cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c/chapter4/active-tool-selection/semantic_router.py#L287-L292)

```python title="chapter4/active-tool-selection/semantic_router.py" linenums="287"
    @staticmethod
    def format_request(server_desc: str, tool_desc: str) -> str:
        """Format a structured tool request."""
        return f"""<tool_request>
server: {server_desc}
tool: {tool_desc}
</tool_request>"""
```

`parse_request` 的逆函数。**在三臂的实际链路里没有任何调用点**——全局 grep `format_request` 只命中两个地方：这里是定义，另一处是 `tests/test_basic.py` L94 的格式断言（检查生成结果里四个要素齐全）。所以它是"给人和测试用的格式来源"，不是运行时路径上的函数。读到这里不要以为漏了调用：**生产路径上它确实没接线**，而这恰好说明 `_create_system_message` 才是"告诉模型怎么写请求"的唯一权威——如果哪天有人改了 system 提示里的格式而忘了同步这里，测试也拦不住，因为两侧没有共享常量。

### 3.5 三臂 metrics 的记账口径对照

这张表是本页最该背下来的东西。三臂的 `metrics` 字段同名，但**统计的是三种不同的东西**（依据：agent.py L44–50 / L301–306 / L431–436 的初始化差异，以及各处 += 的位置）。

| 字段 | PassiveToolAgent | RetrievalToolAgent | ActiveToolAgent | 口径警告 |
| --- | --- | --- | --- | --- |
| `tools_loaded` | `__init__` 设为目录总量（35），任务间不变 | 每次任务**赋值**为 `len(retrieve(...))`（4–5） | 每次**新增工具时 +1**，全程累计去重（可超 35） | 同一个名字 = 目录总量 / 本轮注入数 / 累计加载数。在线表 `Avg tools in ctx` 直接用了它 |
| `tokens_used` | 每次 HTTP 响应累加 `usage.total_tokens`（L484） | 同左（L355） | 同左（L156） | 是 prompt + completion 的总和，跨全部轮次；**不是"schema token"**，不能与离线 3,857 直接比 |
| `api_calls` | 每次 `execute_task` 的循环体 +1（一次） | 同（一次） | 每轮循环 +1（≤5） | **数的是轮数不是 HTTP 次数**：`_handle_tool_calls` 里的递归 `_call_llm` 不计。所以 `tokens_used / api_calls` 不是单次调用成本 |
| `tools_called` | `_handle_tool_calls` 里逐个 append（L500） | 同（L367） | 同（L221） | **唯一用于在线命中判定的字段**；`execute_task` 不重置它，只靠 `reset()` |
| `tool_requests` | 无此键 | 无此键 | 有：每轮请求 +1（L95） | active 专有；与实例字段 `tool_request_count` 恒等 |
| `reset()` 覆盖范围 | 全部五项 | 四项 | 全部五项 | 三臂都在 `__init__` 建一次字典，`reset()` 重建；`execute_task` 不重建 |

三条从这张表推出来的读表纪律（**教学示意**，是口径说明不是代码）：

```text
1. 在线 token 与离线 schema token 不可相减
   离线 3,857 = count_tokens_in_schema(35 个 schema)
   在线 9,813 = 该任务全部 HTTP 调用的 (prompt + completion)
   后者包含 system 文本、工具清单文本、模型输出、以及（被动臂）模型看到假结果后的总结

2. api_calls 不能用来分摊 token
   若一任务 1 轮循环但触发了 2 次 tool_calls 递归 -> api_calls = 1，HTTP = 3

3. tools_loaded 仅在三臂内部可比趋势，不可跨臂当绝对值比
   它既是 35（常量）、又是 4.7（本轮注入）、又是累计数（active）
```

#### 为什么「模型是否调用金标工具」比「检索是否命中」更严格

这是本实验的核心方法论差异，两个指标都不是随便挑的：

**离线 `evaluate_offline` 的 `hit`**（benchmark L176）：`any(g in retrieved_names for g in t["gold_tools"])` —— 问的是"**金标工具在不在被注入的那批 schema 里**"。

- 它是**必要条件**：工具不进上下文，模型就不可能选它。
- 它**与模型无关**：换模型、换温度、换提示词都不影响这个数。所以它是确定性的、可复现的（本页两次复跑，10 个任务逐条一致）。
- 它对 `all-tools` 是**恒真**的（35 个全在），所以 all-tools 的 1.00 不含信息量，只是参照上界。

**在线 `run_online_benchmark` 的 `hit`**（demo_comparison L357）：`any(g in called for g in t["gold_tools"])` —— 问的是"**模型在这一轮里有没有真的把金标工具作为 tool_call 发出来**"。

- 它比离线多了一整步："模型从**可见集合**里挑对"。同一批任务、同一批金标，retrieval 臂离线 recall **1.00**、在线命中 **7/10**——这 0.3 的差距就是纯粹的"**可见 ≠ 被选中**"，是本实验最有价值的一个数：**它量化了模型的工具选择误差**。
- 反方向不成立：上下文里没有的工具**几乎不可能**被调用（模型只能从 API 给的 schema 里选名字）。所以离线 recall 低必然导致在线命中低，而离线 recall 高不保证在线命中高——**单向蕴含**，这正是它更严格的形式化表述。
- 但它本身也偏宽松：判定是"整条任务里任一时刻命中即可"。active 臂 `Deploy to production` 那格一共记了 **11 次**工具调用（fs/cloud 各若干），全都没命中 `devops_deploy`，仍只算一次 miss；反过来说，一个任务里调 3 次只中 1 次也算 hit。**它不检查调用参数是否正确**（3.2 已说明工具是模拟执行的）。所以正确的说法是：**"选对率"，比离线严格、比"任务完成率"宽松。**

### 3.6 学习版注入：三条改动，每一处为什么必须

学习脚本 `learning/task4/run_tool_selection.py` 一共只做三件事，但顺序和位置都不能错。**这一节与源码同源——引用的行号见 [assets/task4/run_tool_selection.py](../assets/task4/run_tool_selection.py)**。

#### 注入 1：环境变量必须在 `import` 之前（L44–51）

[learning/task4/run_tool_selection.py · L43–L55](../assets/task4/run_tool_selection.py)（该文件未随课程仓库提交，链接指向学习站内的副本）

```python title="learning/task4/run_tool_selection.py" linenums="43"
# --- 注入 1：在 import 项目模块之前把端点指向 DeepSeek -------------------------
os.environ["LLM_PROVIDER"] = "openai"
os.environ["OPENAI_API_KEY"] = DEEPSEEK_KEY
os.environ["OPENAI_BASE_URL"] = ENDPOINT
os.environ["OPENAI_MODEL"] = MODEL
os.environ.pop("OPENROUTER_API_KEY", None)

TOOLSEL_DIR = ROOT / "chapter4/active-tool-selection"
sys.path.insert(0, str(TOOLSEL_DIR))
import agent as agent_module  # noqa: E402
import benchmark as bench_module  # noqa: E402
import config as config_module  # noqa: E402
import demo_comparison as demo  # noqa: E402
```

**为什么顺序是硬的**：`config.py` 在**模块顶层**读环境变量——`load_dotenv()`（L5）→ `os.getenv("LLM_PROVIDER"...)`（L8）→ 分支里读 `OPENAI_API_KEY/BASE_URL/MODEL`（L11–19）→ 最后还有一个 OpenRouter 兜底块（L42–47）也在导入期执行。`config` 一旦被导入，`OPENAI_API_KEY` 等常量就**定死**了。而三个 Agent 的 `__init__` 立刻读 `config.OPENAI_API_KEY/OPENAI_BASE_URL/OPENAI_MODEL`（agent.py L28–32）——所以顺序错一步，请求会直接打到 `https://api.openai.com/v1`。

四个变量各自的作用：

| 变量 | 为什么必须设 | 不设会怎样 |
| --- | --- | --- |
| `LLM_PROVIDER=openai` | config L8–9 默认 `openai`，但 `qwen`/`bailian` 会被映射成 `dashscope`（L9），走进读 `DASHSCOPE_API_KEY` 的分支（L10–15） | 若环境里残留 `LLM_PROVIDER=qwen`，会拿到 `None` 的 key |
| `OPENAI_API_KEY=DEEPSEEK_KEY` | 三臂的 `OpenAI(api_key=...)` 直接用它 | 401 |
| `OPENAI_BASE_URL` | 指向 `https://api.deepseek.com`（学习脚本 L40 从 `DEEPSEEK_BASE_URL` 取，默认官方域名） | 打到 OpenAI 官方端点 |
| `OPENAI_MODEL=deepseek-flash` | `self.model = model or config.OPENAI_MODEL` 的兜底值；`run_online_benchmark` 也从参数传同名模型 | 会试 `gpt-5.6-luna` 之类的默认名 |
| 额外 `pop("OPENROUTER_API_KEY")` | config L43 的条件是 `_OR_KEY and (not OPENAI_API_KEY or OPENAI_MODEL.lower().startswith("gpt-5"))`——**已设 key 且模型不是 gpt-5 开头时它不会触发**，所以这一步在当前配置下是防御性的 | 若 `.env` 里有 `OPENROUTER_API_KEY` 而将来又换回 `gpt-5` 系模型，会被静默改道 |

`sys.path.insert(0, TOOLSEL_DIR)` 是因为课程文件的 import 是**扁平**的（`from tool_knowledge_base import ...`、`import config`），必须以该目录为根。

#### 注入 2：把 `OpenAI` 换成 provider 感知包装 + 温度归零（L57–78）

[learning/task4/run_tool_selection.py · L57–L78](../assets/task4/run_tool_selection.py)

```python title="learning/task4/run_tool_selection.py" linenums="57"
# --- 注入 2：thinking 关闭 + 温度归零（与其余学习实验一致）--------------------
_real_openai = OpenAI


class _NoThinkingCompletions:
    def __init__(self, inner):
        self._inner = inner

    def create(self, **request):
        request.setdefault("extra_body", {})["thinking"] = {"type": "disabled"}
        request.setdefault("temperature", 0)
        return self._inner.create(**request)


class _NoThinkingOpenAI:
    def __init__(self, **kwargs):
        inner = _real_openai(**kwargs)
        self.chat = SimpleNamespace(completions=_NoThinkingCompletions(inner.chat.completions))


agent_module.OpenAI = _NoThinkingOpenAI
config_module.AGENT_TEMPERATURE = 0
```

两处**为什么可行**、一处**为什么必须单独做**：

1. **`agent_module.OpenAI = _NoThinkingOpenAI` 能生效**，因为三个 Agent 的 `__init__` 里写的是裸名字 `OpenAI(...)`（agent.py L28、L289、L418），Python 在**调用时**到模块全局里找这个名字——所以替换模块属性就换了实现。这是"在进程内改第三方库行为"的标准手法，代价是它只影响 `agent` 模块，`benchmark` / `semantic_router` 不受影响（它们本来也不建客户端）。
2. **`extra_body={"thinking": {"type": "disabled"}}` 是 DeepSeek 专有字段**：注入 `extra_body` 后，请求体里会多出 `thinking: {type: disabled}`。理由有两条：一是本实验比的是**工具选择**，模型的思维链对结论没有贡献；二是**思考内容会计入 `completion_tokens`**，若三个臂的思考量不同，`tokens_used` 的对比就失去了意义（它本来就已经混了 prompt 与 completion，见 3.5）。
3. **`config_module.AGENT_TEMPERATURE = 0` 为什么不能省**：三臂每次调用都是**显式传参** `"temperature": config.AGENT_TEMPERATURE`（agent.py L142 / L344 / L473）。而包装里的 `request.setdefault("temperature", 0)` 只在**请求里没有这个键**时才补——键已存在（值 0.7），`setdefault` 不会覆盖。所以**只靠包装，温度仍是 0.7**，采样噪声会让三臂的 token/延迟不可比。改 `config_module.AGENT_TEMPERATURE` 之所以有效，是因为 `_call_llm` 读的是**调用时的模块属性**（不是导入期快照）。这条是本页最容易被想错的一处：**看起来冗余的一行，其实是唯一真正起作用的归零**。

#### 注入 3：检索侧零改动

`benchmark.py`、`semantic_router.py`、`tool_knowledge_base.py` 全部是本地 sklearn/numpy + 字面量数据，**没有网络调用、没有模型依赖**，所以它们一行都不用改。用 git 核对（本页写作时执行）：

```text
$ git diff --stat cf7f7a8e16b234ac303034e4ec8f75bf2d61ac2c -- chapter4/active-tool-selection/
（无输出：整个目录相对固定提交零改动）
```

学习版的所有改动都发生在**进程内**（环境变量 + 模块属性），磁盘上一个字节都没动。

!!! warning "这条证据链上的一个小缺口"
    学习脚本落盘的 `evidence.json` 里 `source_hashes` 只哈希了 **5 个文件**（`benchmark.py`、`demo_comparison.py`、`agent.py`、`config.py`、运行脚本本身），**没有哈希 `semantic_router.py` 与 `tool_knowledge_base.py`**。所以"检索侧零改动"这个断言在证据文件里**不是**靠哈希支撑的，而是靠上面那条 `git diff` 空输出。要把它变成可审计的断言，应该把那两个文件也加进 `source_hashes`。本页如实标注，不当作已验证。

**推断**：正因为检索侧完全没动，离线三张表与课程应当逐位一致。本页复跑核对的结果（3,857 / 517 / 1.00 与课程默认 top_k=5 完全吻合）与这个推断相符——但这只能证明"离线部分一致"，不能证明"课程原版在别的 provider 上也得到同样的在线数字"（在线数字依赖模型）。

---

## 4. 完整执行回放

!!! info "本次运行的固定条件"
    运行 ID `20260921T112429Z`；在线模型 DeepSeek `deepseek-flash` @ `https://api.deepseek.com`（thinking disabled，temperature 0）；目录 = 课程真实目录 **8 个 server / 35 个工具**；`top_k=5`；基准任务 10 个；三臂各跑 10 个任务。证据文件：`learning/task4/runs/tool_selection/20260921T112429Z/evidence.json`。

### 4.1 离线（确定性，实测，可复跑）

```text
Benchmark tasks: 10   Catalog size: 35 tools   Retrieval top-k: 5

+-----------------------------+--------------------+-----------------+---------------------------+
| Strategy                    |   Tools in context |   Schema tokens | Recall (gold reachable)   |
+=============================+====================+=================+===========================+
| all-tools (dump everything) |                 35 |           3,857 | 100%                      |
+-----------------------------+--------------------+-----------------+---------------------------+
| retrieval (top-5)           |                  5 |             517 | 100%                      |
+-----------------------------+--------------------+-----------------+---------------------------+

=> Retrieval keeps 100% recall while cutting tool-schema tokens by 86.6% (3,857 -> 517).
```

**缩放（目录吹大后，同一个脚本同一批任务）**：

| 目录工具数 | all-tools schema token | retrieval(top-5) schema token | retrieval recall |
| ---: | ---: | ---: | ---: |
| 35（真实） | 3,857 | 517 | 100% |
| 50 | 5,342 | 522 | 100% |
| 100 | 10,292 | 522 | 100% |
| 200 | 20,258 | 522 | 100% |
| 400 | 40,258 | 522 | 100% |

这张表把本章的核心主张量化了出来，三个观察：

1. **all-tools 几乎完全线性**（每工具 ≈ 101 token：3,857/35、20,258/200、40,258/400 都在同一斜率上）。所以"工具生态长大"对全量注入是**线性成本**，不是对数或饱和——这与"上下文被吃掉几万 token"的直觉一致。
2. **retrieval 基本恒定**（517→522，涨了 1%）。35→400 目录涨了 11.4 倍，检索侧的 schema 成本只动了 5 个 token。**这份"恒定"不是省出来的，是结构决定的**：`retrieve` 永远只返回 top_k 个工具的 schema，注入量与原目录规模无关。
3. **recall 在 400 工具时仍是 100%**，包括干扰项开始混进 top-5 之后（200 工具时 `Monitor service` 的第 2–5 名已经全是 `svc*_op*`）。**这不代表检索很强，只代表这 10 个任务的 query 与金标工具的词面重叠足够大**（3.4 已说明 TF-IDF 只认字面）。把任务改写成不含语料词的换喻说法（"上线新版本"），这张表的 recall 会立刻掉下来——**这不是本次实测，是推断，但它是这套检索方案的已知边界**。

### 4.2 在线（一次观测，实测）

| 策略 | 命中金标 | 平均 token | 平均延迟 | 平均上下文工具数 |
| --- | ---: | ---: | ---: | ---: |
| all-tools（PassiveToolAgent） | **5/10** | 9,813 | 2.92 s | 35.0（常量） |
| retrieval（RetrievalToolAgent） | **7/10** | 1,927 | 1.97 s | 4.7 |
| active（ActiveToolAgent, MCP-Zero） | **5/10** | 4,956 | 5.07 s | — |

逐任务明细（`called` 是模型实际发出的工具名序列，`hit` 只看是否命中金标）：

| 任务 | 金标 | all-tools | retrieval | active |
| --- | --- | --- | --- | --- |
| GitHub repo search | `github_search_repos` | ✓ `github_search_repos` | ✓ `github_search_repos` | ✓ `github_search_repos` |
| Read config file | `fs_read_file` | ✓ `fs_read_file` | ✓ `fs_read_file` | ✓ 3 次（fs 组） |
| List directory | `fs_list_directory` | ✓ `fs_list_directory` | ✓ `fs_list_directory` | ✓ 2 次 |
| Summary statistics | `analytics_summarize` | ✗ `db_schema, fs_list_directory, db_query, fs_search_files` | ✓ `analytics_summarize` | ✗ 6 次全在 fs 组 |
| Send email | `comm_send_email` | ✗ `comm_read_email, fs_list_directory` | ✗ `comm_read_email` | ✗ **0 次调用** |
| Deploy to production | `devops_deploy` | ✗ `devops_monitor, devops_logs` | ✓ `devops_deploy` | ✗ **11 次**（fs/cloud 组） |
| SQL query | `db_query` | ✓ `db_query` ×3 | ✓ `db_query` | ✓ `db_query` ×3 |
| Upload to cloud | `cloud_upload_storage` | ✗ `fs_search_files, fs_list_directory` | ✗ **0 次调用** | ✗ `fs_list_directory, cloud_list_resources` |
| Scrape prices | `web_scrape` | ✗ **0 次调用** | ✗ `web_get` | ✗ **0 次调用** |
| Monitor service | `devops_monitor` | ✓ `devops_monitor` | ✓ `devops_monitor` | ✓ `devops_monitor` ×3 |

### 4.3 诚实解读：这个目录上，一次性检索赢了

**实测结论（可以直接引用）**：

- 在**只有 35 个工具、8 个 server，且离线 recall 已经是 100%** 的小目录上，**一次性检索（retrieval）三个指标全胜**：最准（7/10 vs 5/10）、最省（1,927 vs 9,813 token，省 80%）、最快（1.97 s vs 2.92 s）。
- **主动发现（active）多花的钱没有换到准确率**：它比 retrieval 多花 **2.6 倍 token**（4,956 vs 1,927）、慢 **2.6 倍**（5.07 s vs 1.97 s），命中数与全量注入的 all-tools 打平（都是 5/10）。在本次运行里，MCP-Zero 式迭代的价值是**负的**。
- **全量注入的失败是"看花眼"，不是"看不见"**：all-tools 5/10 的失败格子里，模型调用的都是**同域内相邻的工具**（要 `devops_deploy` 却调了 `devops_monitor`/`devops_logs`；要 `analytics_summarize` 却调了 `db_query`），一次都没有"调了个不存在的工具"。这正是书里说的"长上下文里选择错误"——**工具都在，选不对**。
- **retrieval 的 3 次失败也是选择错误，不是检索错误**：离线 recall 1.00，说明金标**每次都被注入了**；但 `Send email` 那格模型在 5 个候选里挑了 `comm_read_email`（读邮件）而不是 `comm_send_email`（发邮件），`Scrape prices` 挑了 `web_get` 而不是 `web_scrape`，`Upload to cloud` 干脆一次工具都没调。**所以 retrieval 的瓶颈也在模型侧**——它把工具选择从"35 选 1"缩小到"5 选 1"，但没让模型变得更会选。

**推断（从源码结构推出来的机制，未单独做实验验证）**：

- **active 臂为什么费钱**：`route_request` 每轮最多返回 `3 × 5 = 15` 个工具（3.4），而且**要跑满多轮**（每轮一次调用 + 一次递归取答复）。它花钱买的是"模型自己声明的需求"，而模型按 system 示例写出的请求（`"filesystem for local file access"`）落在哪个 server 上由 TF-IDF 词面决定——本次实测里 active 臂的工具调用**大量落在 fs 组**（Summary statistics 6 次、Deploy 11 次里的大半都是 fs 类），像是请求被路由到了 filesystem server 上。若把 `get_routing_details` 拿来打印模型的请求原文，就能证实这一点（本页没做，留作动手项）。
- **active 臂的两次零调用**（Send email / Scrape prices）：可能是 `parse_request` 的收尾标签检查（3.4 的第 4 点）把它第一轮的请求判成了"最终答复"，也可能是路由返回空后模型放弃了。两种机制都在源码里存在，本次运行的分数据不足以区分——**需要打印 `conversation` 才能定论**。
- **active 的价值场所在别处**：它的设计前提是"**检索一开始就猜不到需要什么**"——多步任务里第 3 步才浮现的能力缺口（先搜仓库、再读文件、再画图、最后发邮件）。本实验的 10 个任务全是**单步、单域、任务文本就是全部线索**，恰好是 active 最吃亏的场景。要在本实验里看到主动发现的价值，得换成 demo_comparison 里那个叙事式多步任务（"搜仓库 → 下载 → 分析 → 可视化 → 发邮件"），或者把任务描述写得更含糊。**这条是设计层面的推断，不是本次实测的结论。**

**一句话总结**：这次运行**没有复现**"主动发现优于全量注入"的叙事，而是复现了一个更朴素的事实——**在目录不大、任务单一的场景里，把工具选择问题变成一次检索就够好了**；主动发现要等到"检索的一次性假设失效"（多步、跨域、需求中途变化）才有它自己的位置。而"全量注入的上限"这张表（4.1 的线性增长）依然成立，那才是本章真正被这次运行支持的部分。

---

## 5. 动手验证

三条命令都能在**不花一分钱 API 费**的前提下独立跑通（前两条完全离线）。工作目录：`ai-agent-book/chapter4/active-tool-selection/`。

### 命令 1：零 API 复现离线表（含缩放）

```bash
cd chapter4/active-tool-selection
python demo_comparison.py --offline
```

**预期现象**：先打印 ASCII 横幅，然后是 `Benchmark tasks: 10   Catalog size: 35 tools   Retrieval top-k: 5` 与「Offline Strategy Comparison」表（all-tools 35 / 3,857 / 100%；retrieval top-5 / 517 / 100%）、一行 `cutting tool-schema tokens by 86.6%`、**10 行逐任务明细**（能看到 `github_search_repos` 排第一、`analytics_summarize` 排第二这类细节）、「Scaling」表（35/50/100/200/400 五行，all-tools 线性上涨、retrieval 稳定在 522），最后 `[offline mode] 跳过所有需要 API 的评测。` 与 Takeaway 段。（横幅与表格来自 `print_section` L19–23 和 `tabulate`，需要装 `tabulate` 依赖；只有带 `--legacy-demos` 时才会额外打印知识库统计那几行。）

**要看的东西**：明细表里 `Summary statistics`、`Deploy to production`、`Monitor service` 三行的 retrieved 只有 **4 个**工具而不是 5 —— 这就是 3.1(c) 说的"`top_k` 是名义值"，也是 `_route_to_tools` 的 `getnnz()==0` 短路在下游留下的指纹。**如果你跑出来这三行是 5 个，说明目录或 sklearn 版本与本次不同，先别引用本页的 4.7。**

注意：`--offline` 时 `main` 在检测 API key **之前**就跳过了在线部分（demo_comparison L501），所以**没配任何 key 也能跑完**。（若 `python` 不在 PATH，用 `python3`；脚本自己把所在目录放进 `sys.path`，从任何 cwd 调用都可以。）

### 命令 2：把目录吹到 200 个工具，看缩放

```bash
python demo_comparison.py --offline --num-tools 200
```

**预期现象**：`Catalog size: 200 tools`；all-tools 一行变成 **200 / 20,258 / 100%**，retrieval 仍是 **5 / 522 / 100%**，削减率跳到 **97.4%**；缩放表只剩 200 与 400 两行（因为 `sizes = [50,100,200,400]` 里大于等于当前目录的才留，再补上当前值本身——见 demo_comparison L283–285）；逐任务明细里 `Monitor service` 的 retrieved 开始出现 **`svc1_op1, svc2_op1, ...`** 干扰项，但金标 `devops_monitor` 仍排第一。

**要看的东西**：`Monitor service` 那一行是"干扰项已经进入 top-5、金标仍第一"的活标本——它同时说明了两件事：干扰工具确实在参与打分（不是摆设），以及这批任务的 query 词面优势足够大（换 3.4 说的换喻表达就会翻车）。另外把 200 换成 36，你会看到干扰 server 只造出 1 个工具（`make_distractor_servers` 的 `min(tools_per_server, 剩余)`）。

### 命令 3：绕开 CLI，直接调 `evaluate_offline` 拿字典

```bash
python -c "
import json, benchmark
servers = benchmark.build_catalog(0)
r = benchmark.evaluate_offline(servers, 5)
print(json.dumps(r['strategies'], indent=2, ensure_ascii=False))
print('num_tools', r['num_tools'], 'top_k', r['top_k'], 'per_task rows', len(r['per_task']))
"
```

**预期现象**：

```text
{
  "all-tools": {
    "tools_in_context": 35,
    "avg_schema_tokens": 3857,
    "recall": 1.0
  },
  "retrieval": {
    "tools_in_context": 5,
    "avg_schema_tokens": 516.6,
    "recall": 1.0
  }
}
num_tools 35 top_k 5 per_task rows 10
```

**要看的东西**：`516.6` 这个小数值就是 3.1(c) 的证据——它是 10 次真实注入的均值（`retrieval_tokens_sum / n`），不是 `top_k` 那列的名义 5 乘出来的。你也可以顺手把 `benchmark.BENCHMARK_TASKS` 的第一个任务改一个词（比如把 `GitHub` 换成 `Git`），跑一遍看 recall 是否还满——这是最快领会"TF-IDF 只认字面"的方式。

**进阶（需要 API key）**：本页第 4 节那张在线表不是用 CLI 跑的，而是走学习脚本 `learning/task4/run_tool_selection.py`（它在进程内换端点到 DeepSeek，再调 `demo.run_offline_benchmark` 与 `demo.run_online_benchmark`，最后落证据）。要用 CLI 试单臂：`python demo_comparison.py --strategy retrieval`；要过三臂单查询：`python demo_comparison.py --query "部署到生产环境" --strategy compare`。**注意中文 query 在英文目录上的预期表现**：TF-IDF 词表无交集 → `retrieve` 可能返回空候选、`route_request` 一定返回空。这个"中文必挂"的现象本身就是 3.4 那句"semantic 名不副实"的最直接验证。
