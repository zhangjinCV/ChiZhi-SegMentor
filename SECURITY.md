# Security

## 设计

- 应用默认只监听 `127.0.0.1`，不暴露到局域网/公网。
- Python sidecar 绑定端口 0，端口与随机 token 通过 `ready.json` 交给 Electron。
- `/api/*` 需要 Bearer token；静态 assets 与 `/api/health` 例外。
- 图片/结果文件通过 1 小时 HMAC 签名 URL 提供（`<img>` 无法带 header）。
- Electron renderer 开启 `contextIsolation`、关闭 `nodeIntegration`；文件导入经原生对话框或后端。
- 无遥测、无云端上传；只有用户主动下载模型时才访问 GitHub Release。

## 报告

如果你发现安全问题，请不要公开利用细节；通过实验室公开邮箱/仓库 Security 页面联系维护者（正式开源前补充具体联系方式）。

## 已知边界

- 本应用面向单机本地使用，不是多用户服务器；不要把 sidecar 端口反向代理到公网。
- 不要加载来源不明的 `.pth` 权重（PyTorch checkpoint 可能包含代码执行风险；本项目使用 `weights_only=True`，但仍建议只使用可信权重）。
- 项目/任务目录可能包含敏感图片与 mask，请自行管理磁盘权限。
