# ICLayout-Bench

用于集成电路版图 Agent 的评测框架。Python 源码在 GitHub 维护；题目、参考解和
官方选题集合在独立 Dataset 仓库维护，不随 Python 包分发。

安装 wheel 后，通过 `--dataset` 指定 HF Dataset ID，或显式指定本地 Dataset
工作副本。HF 仓库尚未发布时使用本地路径；不假设已有公开仓库 ID。

工具镜像支持直接从 Docker Hub 拉取，也可以修改 Dockerfile 自行构建；
配置与命令见[镜像指南](docs/tools.md#prebuilt-images-and-local-builds)。

```bash
python -m benchmarking.engine.preview --dataset /path/to/ICLayout-Bench-Dataset \
  run --case NAND2_X1 --image iclayout-bench-tools:local --output build/reference-check
python -m benchmarking.run --config experiment.toml \
  --dataset /path/to/ICLayout-Bench-Dataset --output results/new-experiment
```

HF 管理题目下载缓存；库自动加载 PDK 和派生资源，不需要 prepared 目录。
参考评测不调用模型；参评命令会启动真实 Agent。仅声明的题目输入进入求解环境。
远程参评使用 `--endpoint`，无需本地 EDA 环境。

详细说明见 [英文入口](README.md)、[运行指南](docs/running.md)、
[资源指南](docs/tools.md) 和 [架构](docs/architecture.md)。框架采用 MIT；题目和
上游资源遵循 Dataset 仓库中分别声明的许可证。
