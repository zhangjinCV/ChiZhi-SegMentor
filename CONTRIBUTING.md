# Contributing

感谢参与炽智 SegMentor。提交前请确认：

1. **保持模型契约不变**：6 通道输入、PIL 右/下开 bbox、`net(x)[4]`、概率回原图后阈值。任何相关改动必须通过 `scripts/parity_check.py`。
2. **跑测试**：`python -m pytest -q`，并至少跑一次真实模型 API 冒烟 `scripts/smoke_api.py`。
3. **前端构建**：`npm run build:web` 必须通过 TypeScript 检查。
4. **标注格式**：新增格式请实现 `backend/boxmask/annotations/` 适配器，并在 `backend/tests/test_annotations.py` 加测试。
5. **UI**：保持三栏单图/三步批量的信息架构；新增文案优先中文，后续接入 i18n。
6. **品牌**：保留 README 顶部与界面中的炽智实验室 logo/名称；logo 不在 Apache-2.0 范围内，规则见 `docs/assets/README.md`。
7. **提交信息**：说明动机、改动和验证方式；不要提交模型权重、日志、临时数据或绝对路径。

## 开发命令

见 [docs/development.md](docs/development.md)。

## Issue

请使用 GitHub Issue 模板，附上：

- 操作系统 / CPU/GPU / 版本
- 复现步骤
- 日志（`%APPDATA%/ChizhiSegMentor/logs/`）
- 若涉及标注格式，提供最小脱敏样例

## License

代码提交默认按 Apache-2.0 授权；logo/实验室名称除外。
