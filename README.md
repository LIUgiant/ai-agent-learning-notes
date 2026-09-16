# AI 学习手记

个人 AI Agent 学习、实验与代码阅读文档站。基于 MkDocs Material，发布到 GitHub Pages。

## 本地运行

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdocs serve --dev-addr 127.0.0.1:8766
```

## 添加 Task

在 `docs/taskN/` 添加 Markdown，并更新 `mkdocs.yml` 的导航。模板见 `docs/template.md`。

`main` 分支推送后由 `.github/workflows/pages.yml` 构建与发布。Pages 来源设置为 GitHub Actions。

迁移脚本 `tools/import_notes.py` 只用于初次导入，另需 BeautifulSoup4 和原学习目录。日常编辑和 CI 构建不依赖原项目，直接修改 docs 即可。

课程来源：https://github.com/bojieli/ai-agent-book（Apache-2.0）。代码摘录按原许可保留归属。本站为个人学习记录。
