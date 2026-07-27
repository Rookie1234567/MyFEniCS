# Task001 M0 接收、仓库、环境与只读实现审计

## 结论

`PASS_WITH_IMPLEMENTATION_REQUIREMENTS`。Task000 环境与薄适配器最小回归通过；
当前仓库、分支、upstream、native WSL complex ABI 和本机资源满足 Task001 M1
开发前提。本阶段没有启动 PDE、没有进入 Docker、没有生成训练数据。

现有 Hybrid runner 不能直接承担 Task001 参数面：它没有 height、width 或 phi
入口，且 h10 auto mesh 在高度变化时不能保持固定 cell counts。M1/M2 必须增加
薄配置入口，并冻结显式 axis counts；不得复制或改写 Hybrid 数值核心。

## Git 与任务身份（修改前快照）

| 字段 | 值 |
|---|---|
| repository root | `/home/shenjh/Projects/MyFEniCS-Surrogate` |
| git dir | `/home/shenjh/Projects/MyFEniCS-Surrogate/.git` |
| origin | `https://github.com/Rookie1234567/MyFEniCS.git` |
| branch | `codex/only-one-13p5nm-surrogate-inversion` |
| upstream | `origin/codex/only-one-13p5nm-surrogate-inversion` |
| HEAD | `f6dde841e6e2785cacaa769fb9fc0c534cc5584a` |
| HEAD...upstream | `0 0` |
| status | clean（`git status --short` 无输出） |

Task000 review SHA-256 为
`50d21d1f8f787ce4abe2b518bab9f8bfedff45afaa4dbb0db44507d6274c3460`。
Task000 outcomes 的 SHA-256：

| outcome | SHA-256 |
|---|---|
| `environment_inventory.md` | `3397d2ee9965d91f011b195db2daedf6e7720a3b0df1ddedbcdcf13e356e6273` |
| `environment_qualification.md` | `f6a8df5448f6fef9a7e30a28d4502bdd4566262e76078f1d03d91efc466d9edf` |
| `p6h10_feasibility.md` | `5ab53451b0f2516fce1efb48963b1ebc0ecf4a0c9d703d5051798d1a982e9067` |
| `packaging_feasibility.md` | `f1ec03bb486b3c4e8c2e9a12808b66d6ad7466f83d7371fdee02f0b9d1e672f5` |
| `summary.md` | `6ad6ddd3d2a5a8f90ba2e73b6d01fdd698cd6dc8fd95807d88ab5cf7ef9ceef2` |
| `test_summary.md` | `b9ec438fb0bfc72929ed7034cb3f7fd1a0684cb5fe40d298df6d577870fb1d7e` |

## Windows、WSL 与资源

| 字段 | 实测 |
|---|---|
| Windows | Windows 11 Home，10.0.26200，build 26200 |
| Windows physical memory | 16,733,323,264 bytes |
| WSL | 2.7.3.0；default `Ubuntu-24.04` / WSL2 |
| kernel | `6.6.114.1-microsoft-standard-WSL2` |
| Ubuntu | 24.04.4 LTS |
| CPU | Intel i7-13620H，8 cores / 16 logical CPUs |
| WSL MemTotal | 14,654,963,712 bytes（13.65 GiB） |
| WSL MemAvailable at audit | 13,818,482,688 bytes（12.87 GiB） |
| swap | 42,949,672,960 bytes total，0 used |
| filesystem | `/dev/sdd` ext4 |
| repository filesystem free | 1,021,303,623,680 bytes（约 951 GiB） |
| Docker WSL distribution | `docker-desktop` stopped；未调用、未进入 |

按 Task001 规则，后续 hard ceiling 为
`min(10.5 GiB, 0.77 * MemTotal) = 10.5 GiB`，launch projection ceiling 为
`9.45 GiB`。swap 仅被观察，不得作为可用容量。

## Qualified ABI 与最小回归

activation：`scripts/activate_myfenics_surrogate_wsl.sh`，它复用仓库权威
`scripts/activate_myfenics_wsl.sh`。现场 identity：

| component | identity |
|---|---|
| Python | project `.venv`，3.12.3 |
| PETSc / petsc4py | complex128 / int32；petsc4py 3.19.6 |
| MPI | OpenMPI 4.1.6；mpi4py 3.1.5 |
| DOLFINx | 0.10.0.post2 |
| Basix / UFL / FFCx | 0.10.0 / 2025.2.1 / 0.10.1.post0 |
| dolfinx_mpc | project-local `.venv` package and qualified complex library |

MPI2 import/hello 现场复核通过：两个 rank 均使用同一 project Python、
complex128 PETSc、DOLFINx 0.10.0.post2 和 project-local MPC。

最小 environment/adapter/Case095/096 contract tests：

```text
17 passed in 0.05s
```

命令只运行 pure-Python/compact contracts，没有启动 FEM。

## Case095 / Case096 authority

- frozen significant-channel reference：
  `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json`，
  SHA-256
  `83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3`；
  它是 12-channel best-available same-code numerical band，不是 continuum truth。
- p6/h10 six-path authority：
  `benchmarks/cases/096_hybrid_channel_memory_closure/records/p6_h10_mpi8_six_path_v1.json`，
  SHA-256
  `7e7474fa5b67d65ae255c198982010acc5d6d4d5087f793eb7c2de76c5bbee0a`；
  numerical source `244b62e1fb4f299a468363cf90a2dd548dc34ff6`。
- static Hybrid M120 p6/h10 authority：17,168 rows、12,313,232 matrix NNZ、
  45,293,792 factor NNZ、7.544262 GiB simultaneous peak、322.781788 s、
  no swap；12/12 significant powers 与 amplitudes 通过。
- M160 更慢且峰值更高，M120 是当前 nominal point。历史 SHA 与 Task001
  baseline 不同，因此只能用于预测和合同设计，不能冒充 Task001 formal sample。

## Hybrid runner 只读审计

`benchmarks.run_task032_phase6_augmented` 直接从 `target_stage4_config` 建立
local/modal config，并调用现有 cross-section QEP、local FEM、Hybrid coupling、
memory-minimal modal Schur、static recovery 与 postprocessing 实现。

已存在的关键入口/合同：

- `--degree`、`--h-nm`、独立 `--modal-degree/--modal-h-nm`；
- `--incident-grazing-deg` 与 S/P；当前没有 phi、height、width 参数；
- explicit `assembly_time_static_condensed` backend；
- `modal-schur-memory-minimal` standalone lifecycle；
- M120/M160 通过 `--requested-modes`，candidate pool 固定 2M；
- clean source `--verified-clean-sha`、authority paths/hashes 与 p6/h10
  fail-closed Gate；
- MPI identity、threads、config、axis plan、rows/NNZ/factor inventory、residual、
  R/T/A、raw diffraction orders、selected fields、stage timings 和 source identity
  已进入 runner record。

现有 p6 Gate 只接受固定 p6/h10、80/0/S、M120/M160 authority 身份，不能直接
用于 Task001 新几何/照明。M1 只能增加新的 Task001 scope Gate 和薄 config
overrides，不得放宽旧 Task035c Gate。

## 9 点 topology 只读审计

对 height `{115,120,125}` nm、width `{16,17,18}` nm，在 MPI8 plan 语义下调用
现有 `stage4_axis_plan`，所有点材料面对齐且正向生成，但结果为：

| fidelity plan | auto axis cell counts | 结论 |
|---|---|---|
| h10, height 115 | `(6,3,15)` | 与中心不一致 |
| h10, height 120 | `(6,3,14)` | historical nominal |
| h10, height 125 | `(6,3,15)` | 与中心不一致 |
| h7.5, all 9 points | `(9,4,20)` | counts 一致 |

width 会移动 fitted x 坐标但不改变 counts；height 会移动顶部材料面。每个几何点
的坐标 hash 合理不同，不能把 coordinate hash 当作 topology hash。

M1/M2 要求：h10 显式冻结 `(6,3,14)`，h7.5 显式冻结 `(9,4,20)`；分别以
cell adjacency/connectivity、材料 cell-count pattern、Floquet pairing、element
identity 和 Jacobian/aspect-ratio Gate 验证，而不是依赖 auto target-size rounding。

## M0 Gate

- environment regression：PASS；
- repository/branch/upstream：PASS；
- native WSL complex ABI：PASS；
- Case095/096 authority identified：PASS；
- current runner reusable as numerical core：PASS；
- direct Task001 parameter support：FAIL，需要 M1 thin adapter；
- h10 auto fixed topology：FAIL，需要 explicit-count plan；
- formal PDE authorization：NOT YET，必须先完成 M1/M2 tests、提交并推送 clean
  Task001 implementation baseline。
