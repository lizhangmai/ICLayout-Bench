# ICLayout-Bench

本仓库提供公开任务、官方 harness、HTTP 客户端、通用评测引擎和本地评测服务。
用户可以先在本地跑公开题、检查 DRC/LVS 和后仿真结果，定位问题后，再通过同一套
客户端参加运营方统一评测。本地和正式流程复用评测实现，但本地结果仅为开发证据。

## 开始使用

Python 3.12+ 和 uv 用于安装。运行本地评测还需要 Linux x86-64、Docker 和对应
工具及 PDK 资源；仅参加远程评测不需要本地 EDA 或 Private 源码。

[英文 README](README.md#quick-start) 提供本地准备、参考检查、启动服务及运行
Agent 的完整命令。[运行指南](docs/running.md) 说明如何直接检查自己的 GDS，
以及切换到运营方端点。已有兼容镜像时可以跳过构建。

Public 的安装包包含 `benchmarking`、`layout_eval` 和 `layout_service`。
任务目录和上游资源由公开源码目录提供；wheel 用户可通过 `--public-root` 显式
指定该目录。准备完成后，本地服务只需要安装包、准备好的资源与 Docker。
标准求解工作区不会挂载参考解，模型凭据留在本机 harness。

Private 的 `layout_operator` 复用 Public 引擎，负责隐藏题准入、冻结复测和正式
结果发布。依赖方向保持 Private → Public。UserTrial 独立验证本地自测和远程参评。

[架构与协议](docs/architecture.md) · [任务与评分](docs/tasks.md) ·
[工具环境](docs/tools.md) · [贡献与验证](CONTRIBUTING.md)
