# Task000 运行封装可行性

## 结论

| 方案 | 结论 | 角色 |
|---|---|---|
| A. Linux CLI | `supported` | 唯一数值权威入口 |
| B. Windows launcher | `prototype_ready` | 调用 WSL CLI 的便利入口，不隐藏依赖 |
| C. 原生单文件 Windows FEM exe | `not_supported` | Task000 不实施 |

## A. Linux CLI

正式入口为：

```bash
scripts/run_forward_case.sh \
  --config surrogate_tasks/task000_initialization/sample_2d_development.json \
  --output benchmarks/artifacts/task000/runs
```

wrapper 自动进入仓库、激活项目 `.venv` 和 complex ABI，再调用
`python -m src.forward_data.cli run`。入口检查 root/branch/upstream、项目 Python、
complex128 PETSc、项目 MPC、Linux-only PATH、内存和磁盘；一个进程、一个线程。
稳定退出码为 0（通过）、2（preflight/config）、3（solver/timeout）或
4（独立 residual/physics Gate，由 CLI 映射为非零）。

## B. Windows launcher prototype

`scripts/run_forward_case_windows.ps1` 接收 Windows config/output path，验证
`Ubuntu-24.04`，用 `wslpath` 转换路径，然后以独立参数传给 `bash -lc`。FEM 先写
repository 内的 Linux staging directory，成功后才复制到用户给出的 Windows export
目录。它不保存密码，透传 Linux CLI 退出码，并显示 distribution/path/solver 错误。

示例：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_forward_case_windows.ps1 `
  -ConfigPath C:\work\sample.json `
  -OutputPath C:\work\forward-output `
  -DryRun
```

正式 FEM artifact 始终先写到 WSL Linux filesystem；Windows 路径只是成功后的
export destination。`.venv`、JIT cache 和正式 FEM 工作目录不会迁移到 `/mnt/c`。

若未来必须提供 `.exe`，建议用一个很小的 .NET launcher 封装相同参数传递逻辑；
`.exe` 仍须明确要求 WSL2、Ubuntu-24.04 和本仓库环境存在。

## C. 原生单文件 Windows FEM

`not_supported`。当前数值栈依赖 Linux complex PETSc/SLEPc、OpenMPI、DOLFINx、
project-built dolfinx_mpc、MUMPS、FFCx C JIT、共享库 RPATH、mesh/VTK/ADIOS2 数据
文件以及 MPI 进程语义。PyInstaller 或复制 Python 文件无法把这些依赖可靠转换为
数值等价的原生单文件程序。Task000 不复制、删减或弱化 solver 来伪造支持。
