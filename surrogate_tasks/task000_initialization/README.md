# Task000：代理模型与反演支线初始化

## 当前身份

```text
status = ready_for_codex_initialization
execution_branch = codex/only-one-13p5nm-surrogate-inversion
repository_root = /home/Projects/MyFEniCS-Surrogate
base_sha = 9c2160d41382026352908d692ad479dc4508424d
forward_solver_role = training-data generator
formal_wavelength = 13.5 nm
max_parallel_forward_solves = 1
master_or_task035d_modification = forbidden
```

## 目标

本任务不开发代理网络和反演算法，也不改变现有有限元物理内核。它只完成支线的安全初始化，使后续工作具备：

1. 唯一工作树、唯一分支和唯一 upstream；
2. 防误提交、防误推送和防误切分支保护；
3. 独立 `.venv`、缓存、临时目录和 artifact 根目录；
4. 与 Task035d 共用的 heavy FEM 非阻塞锁；
5. 一个薄的、参数化的前向模型封装设计；
6. 数据集版本、provenance 和 observable schema 合同；
7. 单个 13.5 nm 小算例的安全 smoke 验证；
8. 不触碰 `/home/Projects/MyFEniCS` 工作树的证据。

## 执行顺序

Codex 必须完整阅读：

- 根目录 `AGENTS.md`；
- `surrogate_tasks/AGENTS.md`；
- 本目录 `task.md`。

随后严格按 `task.md` 的 M0–M7 执行。每个阶段先完成轻量 Gate，再进入下一阶段；任何路径、分支、ABI、锁或资源 Gate 失败时受控停止。

## 主要交付

```text
surrogate_tasks/task000_initialization/
    outcomes/summary.md
    outcomes/test_summary.md
    response_v1.md

scripts/
    activate_myfenics_surrogate_wsl.sh
    audit_surrogate_workspace.sh
    install_surrogate_git_guards.sh
    run_with_myfenics_heavy_lock.sh

src/forward_data/
    __init__.py
    schema.py
    forward_model.py
    provenance.py

src/test/
    test_surrogate_task000_*.py
```

实际文件名可在不改变职责边界的前提下轻微调整，但不得把新数值核心塞进 Task000，也不得改动 Task035d 工作树。

## 完成定义

Task000 只有在以下条件全部满足后才可结束：

- branch/upstream/path guards 生效并有受控负测试；
- 普通 `git push` 只能指向代理分支；
- 支线 activation 与缓存隔离通过；
- heavy lock 的 acquired/busy 两条路径均通过测试；
- 参数、输出、provenance 和 dataset manifest schema 可独立验证；
- 单个小型 13.5 nm FEM smoke 通过 residual/physics Gate，或因已有模型入口不适配而真实记录 blocker；
- 没有运行两个 FEM 并发；
- `/home/Projects/MyFEniCS` 的 HEAD、branch 和 status 未被本任务改变；
- 所有改动只提交并推送到本执行分支；
- Codex 给出完整 HEAD、changed paths、测试与资源证据后停止。
