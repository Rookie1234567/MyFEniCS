# Task000 总结

## 状态

`task000_complete_no_bulk_generation`。原生 WSL complex FEM 环境、Git 防护、
薄前向入口、单个 development smoke、p6/h10 资源决策和封装评估均已完成。
Task000 到此停止；没有开始批量数据生成、代理训练或反演。

## M0–M3：本机环境

| 项目 | 结论 |
|---|---|
| Windows / WSL | Windows 11；WSL 2.7.3；`Ubuntu-24.04` / WSL2 |
| repository | `/home/shenjh/Projects/MyFEniCS-Surrogate`，WSL ext4 |
| Docker | Desktop 4.76.0、`docker-desktop` 和约 17.86 GiB data VHDX 全部保留；M1 `skipped_by_user` |
| Docker runtime | Task000 未启动、未进入、未调用 |
| M2 | 复用现有 Ubuntu，不新建、不注销 distribution |
| Python | project `.venv` / Python 3.12.3 |
| FEM ABI | complex PETSc 3.19 / SLEPc 3.19 / DOLFINx 0.10 / MPC 0.10.1 / OpenMPI 4.1.6 |
| visualization | PyVista 0.44.1 / VTK 9.1.0 system packages |
| M3 Gate | serial/MPI2 imports、linkage、MUMPS、PEP、FFCx JIT 全部 PASS |

安装分为用户执行的 root `--system` 阶段和普通用户 `--user` 阶段；固定版本的
MPC source commit 为 `a444aa3006fdf492091443cc8c885c1eec006c2f`。activation
将 temp/cache/log/artifact 隔离到 repository 内，并固定所有线程为 1。

## M4：Git 防护

- local config：`push.default=simple`、`pull.ff=only`、
  `remote.origin.push=HEAD:refs/heads/codex/only-one-13p5nm-surrogate-inversion`；
- pre-commit 验证 branch/origin/upstream；
- pre-push 只允许当前 HEAD 到唯一代理 remote ref，拒绝 branch deletion、错误
  ref、非 fast-forward/force push；
- 受控测试：合法 commit/HEAD ref 返回 0；三类禁止操作均返回 1；
- workspace audit 报告 root、Git、ABI、memory、swap、disk、cache/artifact。

## M5–M6：薄前向入口

`src.forward_data` 只映射到 tracked `src/main.py` preset，不复制 Maxwell、网格、
DtN、装配、MUMPS 或后处理核心。v1 支持两个真实 13.5 nm preset identity：

- `euv_2d_complex_absorption_v1`：低资源 development smoke；
- `euv_3d_target_grating_v1`：tracked p2/h5 target 入口。

v1 没有臆造任何可反演范围，所有参数均固定；因此它是数据合同与入口初始化，
不是已经可批量采样的参数空间。每次调用验证 branch/source/ABI/resource，创建唯一
run directory，写 `raw_record.json`、`compact_record.json`、`manifest.json`，并
记录 source/schema/config hash、UTC 时间、命令、结果、summary hashes、child peak
RSS 与 swap delta。formal run 在 dirty source 上 fail closed；dataset validator 拒绝
混合 source SHA 或 schema。

Linux one-command entry：

```bash
scripts/run_forward_case.sh --config <json> --output <repository-local-directory>
```

## M7：验证与 p6/h10

单个串行 13.5 nm development smoke：

| 指标 | 实测 |
|---|---:|
| cells / Nedelec DoF | 1,785 / 14,452 |
| rows / NNZ | 14,482 / 247,181 |
| true residual | `2.977956804883729e-14` |
| authoritative R | `3.6625211715002372e-6` |
| authoritative T | `0.882172452104589` |
| A_balance / A_volume | `0.11782388537423949 / 0.11782388537423974` |
| solver / end-to-end wall | 2.065 s / 4.41 s |
| peak RSS / swaps | 341,716 KiB / 0 |

p6/h10 分类为 `blocked`，未启动 PDE。Case095/096 hermetic contracts 全部通过，
但历史 six-path source `244b62e...` 与当前 Task000 source 不同；Full3D static
历史峰值 14.722 GiB 又高于当前 WSL 13.65 GiB 总内存。40 GiB swap 不用于
伪造可行性。

## M8：封装

- Linux CLI：`supported`，数值权威入口；
- Windows PowerShell launcher：`prototype_ready`，验证 distribution、转换路径、
  在 Linux filesystem staging 后导出并透传退出码；PowerShell parser PASS；
- 原生单文件 Windows FEM exe：`not_supported`，不会删减 Linux FEM/JIT/MPI 依赖。

## Changed paths

- `.githooks/task000/{pre-commit,pre-push}`
- `scripts/{install_local_wsl_environment,activate_myfenics_surrogate_wsl,install_surrogate_git_guards,audit_surrogate_workspace,run_forward_case}.sh`
- `scripts/run_forward_case_windows.ps1`
- `src/main.py`（仅 runner 延迟导入，避免 2D 无条件加载 3D stack）
- `src/forward_data/{__init__,schema,forward_model,provenance,cli}.py`
- `src/test/test_surrogate_task000_{environment_scripts,forward_data}.py`
- `surrogate_tasks/task000_initialization/sample_{2d_development,3d_target_h5}.json`
- `surrogate_tasks/task000_initialization/outcomes/*.md`
- `surrogate_tasks/task000_initialization/response_v1.md`

## 下一阶段 go/no-go

`NO-GO for bulk generation`。开始正式训练数据生成之前，必须另行冻结至少一个真实
可反演参数及有物理依据的范围，选择与 13.65 GiB 预算兼容且具有同-source 数值
reference 的离散，提交 clean source，再用 formal single-sample 验证 dataset
contract。Task000 不执行这些后续工作。
