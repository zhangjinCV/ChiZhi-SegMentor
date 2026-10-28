# 模型权重

权重文件不入 git。

本地开发把冻结的 checkpoint 放在：

```text
models/boxmask_repvit_best_snapshot.pth
```

SHA256：

```text
17b8f2d5fc0e65b1d6ec1b0c8ec123452fba02e4ba4dc784c95d4ed288f82d4c
```

校验：

```bash
python scripts/verify_model.py
```

也可以从 Release 下载并校验：

```bash
python scripts/verify_model.py --url <release-asset-url>
```

正式开源时，将该文件作为 GitHub Release 附件分发；应用首次启动可以引导用户选择本地文件，或在后续版本加入带 sha256 校验的下载器。模型细节、输入输出契约与限制见 [MODEL_CARD.md](MODEL_CARD.md)。
