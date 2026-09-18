# ICLayout-Bench

本仓库提供公开任务、独立观测层、HTTP 客户端、通用评测引擎和本地评测服务。
用户可以先在本地跑公开题、检查 DRC/LVS 和后仿真结果，定位问题后，再通过同一套
客户端参加运营方统一评测。本地和正式流程复用评测实现，但本地结果仅为开发证据。

当前任务采用 `layout-v2`：以前仿作为电气性能的 100 分基准，面积采用冻结的紧凑版图基准；分数可以超过 100。详见[评分与任务设计](docs/tasks.md#task-scoring)。历史结果保留原评分版本。

## 许可范围

框架采用 [MIT 许可](LICENSE)，任务材料、参考版图、PDK 和 EDA 工具分别保留各自许可；
整个仓库并非统一采用 MIT。两个 analog-db 集合的电路材料和参考版图适用
**PolyForm Noncommercial 1.0.0 非商业许可**，并保留其他上游组件条款。
公开可下载或通过 case 验证不代表获得商业使用授权。使用或分发任务材料前，
请查阅[许可与分发说明](LICENSING.md)及对应集合的原始声明。

## 开始使用

Python 3.12+ 和 uv 用于安装。运行本地评测还需要 Linux x86-64、Docker 和对应
工具及 PDK 资源；仅参加远程评测不需要本地 EDA 或 Private 源码。

[英文 README](README.md#quick-start) 提供本地准备、参考检查、启动服务及运行
Agent 的完整命令。[运行指南](docs/running.md) 说明如何直接检查自己的 GDS，
以及切换到运营方端点。已有兼容镜像时可以跳过构建。

Public 源码统一位于 `benchmarking/`，其中 `engine/` 负责评测与执行，
`service/` 负责 HTTP 服务。安装包只使用 `benchmarking` 顶层命名空间。
任务目录和上游资源由公开源码目录提供；wheel 用户可通过 `--public-root` 显式
指定该目录。准备完成后，本地服务只需要安装包、准备好的资源与 Docker。
标准求解工作区不会挂载参考解，模型凭据留在本机 harness。

Private 的 `iclayout_bench_private` 复用 Public 引擎，负责隐藏题准入、冻结复测和正式
结果发布。依赖方向保持 Private → Public。UserTrial 独立验证本地自测和远程参评。

[架构与协议](docs/architecture.md) · [任务与评分](docs/tasks.md) ·
[工具环境](docs/tools.md) · [贡献与验证](CONTRIBUTING.md)

Codex、Claude Code、DSH 等参评 harness 自行控制推理与工具循环；ICLayout-Bench
提供环境、观察操作过程、执行约束并独立评分。服务端记录与参评端轨迹分别标注来源。
