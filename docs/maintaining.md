# 网站维护与发布

## 日常更新

1. 在 `docs/taskN/` 编辑 Markdown。
2. 图片放在 `docs/assets/`，使用相对链接引用。
3. 在 `mkdocs.yml` 添加左侧导航。
4. 本地构建，确认没有断链与构建警告。
5. 提交并推送到 `main`，GitHub Actions 自动发布。

## 本地预览

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdocs serve --dev-addr 127.0.0.1:8766
```

## 发布前检查

```sh
mkdocs build --strict
```

GitHub 仓库的 **Settings → Pages → Source** 使用 **GitHub Actions**。工作流是 `.github/workflows/pages.yml`。

## 文件范围

本站只保存整理后的学习文档、代码摘录、流程图和实验图片。API 密钥、`.env`、本地环境与原始请求日志不属于发布内容。完整实验记录仍保存在本地课程项目。

## 内容来源

课程来自 [AI Agent Book](https://github.com/bojieli/ai-agent-book)，采用 Apache-2.0 许可。代码摘录保留来源说明，实验结论来自个人运行记录；本站不是课程官方站点。
