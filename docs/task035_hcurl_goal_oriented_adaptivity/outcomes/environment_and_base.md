# Task035 Phase A：环境、基线与 artifact 资格化

## 结论

```text
phase_a_environment_base_subgates_pass
phase_a_full_regression_gate_fail
environment_gate_pass
source_and_abi_gate_pass
baseline_binding_gate_pass
required_artifact_gate_pass
task035_pde_started = false
heavy_p4_started = false
thresholds_relaxed = false
```

Phase A 只授权后续解析 fixture 与 estimator 基础工作；不授权 Task035 正式 PDE 或重型 p4。

## Git 与分支身份

| 字段 | 值 |
|---|---|
| Task034 final master / Task035 base | `5002636852ffb67b4711443da70eb536c303e34e` |
| 分支 | `codex/20260721-task35-hcurl-goal-oriented-adaptivity` |
| 建分支前 | `HEAD == origin/master`，完整 status 为空 |
| 环境 probe 前后 | HEAD 稳定且完整 status 为空 |
| ordinary default | 未改变 |

## WSL、环境与 ABI

资格化工具只执行环境审计与微型代数问题，不组装或求解 Task035 PDE。

| 项目 | 实测值 | Gate |
|---|---|---|
| WSL / kernel | Ubuntu 24.04；`6.18.33.2-microsoft-standard-WSL2` | pass |
| Python / MPI | project `.venv` 3.12.3 / OpenMPI 4.1.6 | pass |
| PETSc | 3.19.6；`complex128`；32-bit Int | pass |
| SLEPc / DOLFINx / Basix / UFL | 3.19.2 / 0.10.0.post2 / 0.10.0 / 2025.2.1 | pass |
| `dolfinx_mpc` | project-local complex ABI | pass |
| MPI | 1/2/4/8；每 rank 1 thread；单一 ABI | pass |
| MPI8 microfixture | distributed MUMPS solve + SLEPc PEP | pass |
| CPU | 48 个物理核；MPI8 无 oversubscription | pass |
| NUMA / memory / swap | 原始 audit 已记录；`numactl` 为 optional diagnostic | recorded |

| gitignored 原始证据 | SHA-256 |
|---|---|
| `benchmarks/artifacts/task035/phase_a/5002636/wsl_environment_qualification.json` | `f47801cdb48af7d5958aa4ecc9c25cf3ccbc0c0d1816bf35db115ff806aa87fe` |
| `benchmarks/artifacts/task035/phase_a/5002636/wsl_environment_qualification.md` | `23ce84aeede055ccbec7a747696f485372b8075b037c1b009fbb74407542ad35` |

## Task034 compact baseline binding

| tracked record | SHA-256 |
|---|---|
| `canonical_benchmark_manifest.json` | `6ae9f4fa15d776d80c16c4d21d8723a966f7c24393574bcb7896f49a2743c85d` |
| `convergence_summary.json` | `f5bad15f40ade652f6b4398e46852292ed323e3e5494b9fdb969c40bc6283111` |
| `mpi_identity_summary.json` | `88a085bc6424892142e63aa4b8a8a65bdc1a86410b7cd9baae5fb3d9390c6111` |

冻结参考是 best available discrete references，不是 continuum truth：

| 身份 | 方法 | residual | R | T | A_volume | modes | peak GiB |
|---|---|---:|---:|---:|---:|---:|---:|
| replacement p4/h5 | Full3D | `2.401474e-11` | 0.000766313377 | 0.602677530503 | 0.396556156120 | 80 auxiliary rows | 28.8885 |
| replacement p4/h5 | Hybrid M160 | `4.082573e-12` | 0.000766313235 | 0.602677529589 | 0.396556157180 | 160/direction | 9.2059 |
| direction p3/h3 | Full3D | `8.489277e-11` | 0.000789467957 | 0.602514984138 | 0.396695547904 | 80 auxiliary rows | 44.0687 |
| direction p3/h3 | Hybrid M160 | `6.718449e-12` | 0.000789467334 | 0.602514978699 | 0.396695553970 | 160/direction | 14.2716 |

same-degree closure 与 M funnel 均由 Case093 compact record 绑定；没有重跑已接受矩阵。

## 必需 artifact inventory

| role | materialization | SHA-256 |
|---|---|---|
| p4/h5 Full3D | `materialized_hash_match` | `879816e0c7c9f345deeb23435607560be9af7ad431142f8b2e3ea4f9a8022cab` |
| p4/h5 Hybrid M160 | `materialized_hash_match` | `0d6d65dd514695562c7ab4c20d71d90b3fae18ec1c5ecb74d3c6ec81b4c85deb` |
| p4/h5 M funnel | `materialized_hash_match` | `18c09f43ac786f2db51070ff136a270b1af731575bc1560089f44ada145212b4` |
| p3/h3 Full3D | `materialized_hash_match` | `2c1ec18a3877a4452f7ac52cd411df0a4785204b811dc52e466e1f7c91ea393a` |
| p3/h3 Hybrid M160 | `materialized_hash_match` | `10d179b586ec4fb863b20e0e878d5919975652097cb8005f2ed0bf37ab96fae9` |
| p3/h3 M funnel | `materialized_hash_match` | `615ff2e9e3541f4a45583608aa712462cbf0f896d9f63939d694327847c7cd08` |

普通 checker 不读取 ignored 文件；显式 formal verification 才检查实体。clean checkout 缺失时报告
`artifact_not_materialized`，不得静默替换。本 inventory 仅覆盖 Phase A 必需 baseline records。

## 材料、几何、配置与理论身份

| role | tracked path | SHA-256 |
|---|---|---|
| physical config | `benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/config.json` | `ce83b99946d2fbd6542948e6af5fcebf74ec67ace48d1d59b9f32eaeeeada654` |
| material | `src/common/materials.py` | `2eaf2679f12e698b049fec22e271f1b68a6105f9b13c3afb6e01e3433169f4c5` |
| config | `src/common/config.py` | `4e8b01b4c5a4217912e4ec5b02b0ee4fdfaa17d4139f20a679445e505daea905` |
| geometry | `src/geometry/mesh_builder_3d.py` | `357f393b2778d0b2db41954018cba92a81abf82f7f9445fec9e65f0b8039b123` |
| Task035 theory | `notes/theory/hcurl_adaptive_error_estimators_and_hp_strategy.md` | `610c6bef05d1b6aaf6779b6e40cb922459bc5d912dda7d4c73d9c40887701985` |

机器可读总绑定位于
`benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/base_manifest.json`。

## 研究边界与 Phase 决策

- Task034 research-only graded mesh、adaptive runner 与 compression 工具没有恢复或提升。
- 未运行 Task035 PDE、p4 重型求解、adaptive cycle 或 Task034 重型矩阵。
- Phase A 完整回归 Gate 失败；按用户指令停止，Phase B 未解锁。
- 本轮先提交、推送并等待 review，不因 Phase A 通过而跳到重型阶段。
