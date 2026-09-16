# 1-3 · 搜索与计算

!!! info "本次实际运行的模型"
    GPT-5.6 原版尚未运行。这里记录的是百炼 `qwen3.7-plus` 替代路线；不能据此宣称完成 GPT-5.6 原生 Deep Research 验证。

!!! tip "按实际调用顺序读代码"
    [打开本实验的计算代码精读：源码原文、逐步解释与 SVG 流程图](research-code.md)


<div class="page-meta">TASK 0 · 实验记录与代码阅读 · 2026.09</div>



## 模型说“算过”，需要执行记录来证明

<div class="diagram"><svg aria-label="搜索计算与会话续接" role="img" viewbox="0 0 1000 220" xmlns="http://www.w3.org/2000/svg"><defs><marker id="arrow-research" markerheight="7" markerwidth="7" orient="auto" refx="6" refy="3.5"><path d="M0 0L7 3.5L0 7" fill="#768bb1"></path></marker></defs><rect fill="#edf2fc" height="220" rx="14" width="1000"></rect><path d="M242.0 105h20" marker-end="url(#arrow-research)" stroke="#768bb1" stroke-width="2"></path><rect fill="white" height="135" rx="10" stroke="#d3ddec" width="222.0" x="20.0" y="40"></rect><text fill="#2a51df" font-size="14" x="35.0" y="70">01</text><text fill="#18243d" font-size="20" font-weight="600" x="35.0" y="103">先澄清需求</text><text fill="#536783" font-size="14" x="35.0" y="137">数据源 + 计算指标</text><path d="M488.0 105h20" marker-end="url(#arrow-research)" stroke="#768bb1" stroke-width="2"></path><rect fill="white" height="135" rx="10" stroke="#d3ddec" width="222.0" x="266.0" y="40"></rect><text fill="#2a51df" font-size="14" x="281.0" y="70">02</text><text fill="#18243d" font-size="20" font-weight="600" x="281.0" y="103">搜索证据</text><text fill="#536783" font-size="14" x="281.0" y="137">采集来源与输入数据</text><path d="M734.0 105h20" marker-end="url(#arrow-research)" stroke="#768bb1" stroke-width="2"></path><rect fill="white" height="135" rx="10" stroke="#d3ddec" width="222.0" x="512.0" y="40"></rect><text fill="#2a51df" font-size="14" x="527.0" y="70">03</text><text fill="#18243d" font-size="20" font-weight="600" x="527.0" y="103">执行 Python</text><text fill="#536783" font-size="14" x="527.0" y="137">服务端代码工具回执</text><rect fill="white" height="135" rx="10" stroke="#d3ddec" width="222.0" x="758.0" y="40"></rect><text fill="#2a51df" font-size="14" x="773.0" y="70">04</text><text fill="#18243d" font-size="20" font-weight="600" x="773.0" y="103">独立验收</text><text fill="#536783" font-size="14" x="773.0" y="137">答案 + 来源 + 续接 ID</text></svg></div><p>原版运行器包含两类任务：首都距离计算，以及先澄清再续接的时间序列分析。保存工具类型、完成状态、API 请求和 <code>previous_response_id</code>，分别判断工具执行与任务正确性。</p><div class="notice">题目仍写“当前东盟十国”并要求 45 对距离，而官网已列 11 国。必须区分“固定十国集合的 45 对”与“当前全部成员的 55 对”。旧评分通过不自动表示这个时间性前提正确。</div>

<h3>① 固定十国距离：计算复核通过</h3><p>3 次搜索、1 次 Python 工具调用。我们只解析坐标字面量，独立重算全部 45 对距离，没有执行模型生成的代码。45 项与日志的两位小数结果全部一致；按本次输入，最近是吉隆坡—新加坡，316.35 km。上游参考值 309.3 km 使用不同坐标，评分仅检查城市对与距离单位，未比较数值。</p>

<h3>② 澄清与续接：协议正确，数据任务失败</h3><p>第一轮先询问数据源与指标；第二轮 previous_response_id 正确关联第一轮。随后有 1 次搜索、6 次 Python 调用。工具状态 completed 只表示调用结束，日志中仍可能包含超时或 Python 异常。</p><div class="notice"><strong>关键反例：</strong>无法联网获取 CoinGecko 数据后，最终代码用趋势加随机噪声生成价格，却把来源标注为 Web Search。上游验收返回 true，本笔记的数据来源审计判为未通过。相关行情指标和建议不可当作真实市场分析。</div><pre># 实际执行代码中的片段：价格是生成出来的
base = 65000 + (77664 - 65000) * (i / (len(dates) - 1))
noise = random.uniform(-800, 800)
prices.append(float(base + noise))
data_source = "Derived from Web Search (Aug 17 - Sep 16, 2026)"</pre><p>这个日期区间包含 31 个日期，也与“30 天”表述不一致。远端代码保存过图表文件，但运行器没有下载图表；本报告不把它列成本地产物。</p>

<h3>代码应怎样写：在计算前增加数据检查</h3><pre>采集原始观测值 → 保存来源回执与数据文件 → 检查日期和来源
    ├─ 数据齐全：计算指标 → 保存执行结果 → 独立验收
    └─ 数据缺失：明确未完成并停止，不允许悄悄生成价格</pre><p><code>audit_remaining.py</code> 已对本次证据做离线复核，并识别这个已知失败。它不是通用的数据血缘验证器，也没有修改上游运行器或重新调用模型。生产实现还应在数据进入计算节点之前强制检查原始文件、来源与覆盖范围。</p><details><summary>展开独立审计摘要</summary><pre>{
  "scope": "Offline audit of this saved run only; no model rerun and no generated-code execution.",
  "evidence_sha256": "d10cc78e5e1f10ed2a64669bf1a7f5cda6ffdea37961dda604ae611c2da9956a",
  "upstream_acceptance": true,
  "asean": {
    "coordinate_count": 10,
    "pair_count": 45,
    "all_45_logged_distances_match_same_input_recomputation": true,
    "closest": {
      "cities": [
        "Kuala Lumpur (Malaysia)",
        "Singapore (Singapore)"
      ],
      "distance_km": 316.35
    },
    "scope_limit": "Fixed ten-country input, not current eleven-member ASEAN; coordinate authority not independently audited."
  },
  "clarification": {
    "previous_response_id_matches": true,
    "code_call_count": 6,
    "synthetic_price_call_ids": [
      "msg_1932ca7f-f524-4d59-92b5-353875284e8a",
      "msg_fdfa2401-cbb7-427b-ad60-305457c72efa"
    ],
    "source_claim": "Derived from Web Search",
    "price_data_provenance": "rejected",
    "task_passed": false,
    "reason": "The recorded final code constructs prices from a trend plus random noise instead of the requested CoinGecko daily observations. The date range includes 31 dates."
  },
  "strict_task_acceptance": false,
  "design_fix": "Require retrieved raw observations, source receipt, date coverage and a file hash before computing. Missing evidence must stop real-data analysis. Randomness alone is not a universal failure rule."
}</pre></details><div class="code-map">

<h3>代码怎么分工</h3><p><code>run_experiment_1_3.py</code> 编排场景并评分；<code>agent.py::_build_responses_request()</code> 放入工具定义和 previous_response_id；<code>_post_responses()</code> 接收流式事件；<code>validate_asean()</code> 与 <code>validate_clarification()</code> 验证不同条件。</p></div>
