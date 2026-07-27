# Task000：本地 WSL 前向环境与数据生成入口初始化

## 当前身份

```text
status = ready_for_local_laptop_initialization
execution_branch = codex/only-one-13p5nm-surrogate-inversion
local_platform = Windows laptop + WSL2 Ubuntu
local_physical_memory = approximately 16 GB
initial_forward_source_sha = 9c2160d41382026352908d692ad479dc4508424d
forward_solver_role = local training-data generator
formal_wavelength = 13.5 nm
max_parallel_forward_solves = 1
workstation_role = later GPU surrogate training and inversion
```

## 目标

本任务不开发正式代理网络和反演算法，也不改变现有有限元物理定义。它只完成本地笔记本上的可复现前向环境和最小可用数据生成入口，使后续工作具备：

1. 在本地 clone 的唯一代理分支上安全工作；
2. 审计并在用户确认后卸载不再使用的 Docker Desktop/旧 Docker WSL 组件；
3. 新建独立 WSL2 Ubuntu，而不是继续依赖 Docker；
4. 在 Linux 文件系统内安装并资格化 complex PETSc/SLEPc/DOLFINx/MPI 环境；
5. 建立项目本地 `.venv`、独立缓存、日志和 artifact；
6. 对现有 13.5 nm FEM 建立参数化薄封装；
7. 形成一条命令输入参数、输出结构化结果的 Linux CLI；
8. 评估 Windows launcher `.exe` 调用 WSL CLI 的方案；
9. 从轻量 smoke 逐级尝试 `p6/h10`，并在 16 GB 资源不足时真实受控停止；
10. 为下一阶段的正式训练数据生成给出明确 go/no-go 结论。

## 执行顺序

Codex 必须完整阅读：

- 根目录 `AGENTS.md`；
- `surrogate_tasks/AGENTS.md`；
- 本目录 `task.md`。

随后严格按 `task.md` 的 M0–M9 执行。任何 destructive Docker/WSL 操作前必须先给出审计结果、保留项和删除项，并等待用户明确确认；不得把卸载 Docker 与删除其他 WSL distributions 混为一谈。

## 主要交付

```text
surrogate_tasks/task000_initialization/
    outcomes/environment_inventory.md
    outcomes/environment_qualification.md
    outcomes/p6h10_feasibility.md
    outcomes/packaging_feasibility.md
    outcomes/summary.md
    outcomes/test_summary.md
    response_v1.md

scripts/
    install_local_wsl_environment.sh
    activate_myfenics_surrogate_wsl.sh
    audit_surrogate_workspace.sh
    run_forward_case.sh

src/forward_data/
    __init__.py
    schema.py
    forward_model.py
    provenance.py
    cli.py

src/test/
    test_surrogate_task000_*.py
```

实际文件名可在不改变职责边界的前提下轻微调整。不得为了打包或通过 smoke 而复制、弱化或绕过现有 FEM 数值核心。

## 完成定义

Task000 只有在以下条件全部满足后才可结束：

- 本地真实 repo root、branch、upstream 和 origin 已审计；
- Docker/WSL 现状已盘点，破坏性卸载只在用户明确确认后执行；
- 新 Ubuntu 可以稳定启动，仓库位于 WSL Linux 文件系统；
- complex ABI preflight 通过；
- 项目本地 `.venv`、缓存、日志和 artifact 隔离通过；
- 现有 FEM 可通过参数 schema 和 `ForwardModel.evaluate(...)` 薄调用；
- Linux CLI 能运行至少一个低资源 13.5 nm development smoke；
- p6/h10 已完成逐级资源预检和一次受控尝试，结果被分类为 `passed`、`controlled_stop` 或 `blocked`，不得伪造成功；
- `.exe` 路径给出实验证据：优先 Windows launcher 调用 WSL，不把 Linux 依赖错误宣称为原生单文件程序；
- 所有改动只提交并推送到本执行分支；
- Codex 给出完整 HEAD、changed paths、测试、环境、资源和数值证据后停止，不开始批量数据生成。
