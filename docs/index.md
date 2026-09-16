# AI 学习手记

<div class="home-intro"><span class="eyeline">LEARN · EXPERIMENT · BUILD</span><p>从实验现象出发，<br><strong>把 Agent 的设计读懂、写出来。</strong></p><div>记录每一次学习、真实运行与代码复盘。保留失败，也保留判断的依据。</div></div>

## 从这里开始

<div class="grid cards" markdown>

-   **Task 0 · Agent 基础**

    ---

    环境准备、基础概念与第一章实验。把模型、上下文和工具放回完整循环里理解。

    [进入学习导读 →](task0/index.md)

-   **上下文消融 · 五组对照**

    ---

    同一任务保留完整上下文，或分别移除历史、reasoning、工具定义、工具结果。

    [看实验结果 →](task0/ablation.md)

-   **逐组读代码**

    ---

    先看 SVG 流程，再看教学代码、字段说明与真实源码。

    [开始代码阅读 →](task0/source.md)

-   **搜索、计算与生成**

    ---

    从托管搜索到代码执行，再到五组图片对照。重点分清执行成功与任务成功。

    [查看后续实验 →](task0/search.md)

</div>

## 当前学习进度

| 范围 | 实际状态 |
| --- | --- |
| 环境与离线验证 | 已完成所选验证，保留上游文档检查失败记录 |
| 1-1 上下文消融 | 五组运行完成；完整组与移除历史 reasoning 组答对 |
| 1-2 多轮搜索 | 完成百炼学习变体，原版 Kimi 路线未验收 |
| 1-3 搜索与计算 | 执行结束；距离复核通过，行情来源审计失败 |
| 1-4 生图工作流 | 完成 10 张图片；学习变体，指定海报文案未满足 |
| 后续 Task | 按课程安排持续添加 |

## 关于这份笔记

本站是个人学习与实验记录，参考 [《深入理解 AI Agent》](https://bojieli.github.io/ai-agent-book/) 学习，采用同样的 Material for MkDocs 文档形式。课程原文、个人理解和实测结论分别标注。

每个 Task 使用独立目录；笔记以 Markdown 保存，代码块、图片和流程图进入 Git 版本管理。更新推送后由 GitHub Actions 构建并发布。

## Task 1 · 上下文工程与 Memory / RAG

已记录上下文压缩、长期记忆、BM25 与 RAG 的真实运行及参数对照。[进入 Task 1](task1/index.md)。
