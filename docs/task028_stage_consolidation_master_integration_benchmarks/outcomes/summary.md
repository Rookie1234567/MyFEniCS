# Outcome Summary

## 任务

Task028 从 `master@0465b5f` 选择性整合 Task021-Task027 的稳定代码和证据。Response V2 进一步把仓库整理为“能力索引 -> Quick Start -> Code Walkthrough -> Theory -> Benchmark”的完整学习与验证体系，并补齐安全 PyCharm 入口、benchmark provenance contract 和复折射率端口功率闭合。

## 分支

| 项目 | 值 |
|---|---|
| branch | `codex/20260712-task28-stage-consolidation` |
| review baseline | `review_report_v2.md` |
| whole research branch merge | 否 |
| ordinary solver default changed | 否 |
| `master` merge | 未执行，等待最终审查和用户许可 |

## Response V2 完成情况

| 审查主题 | 结果 | 主要证据 |
|---|---|---|
| 五层文档架构 | pass | capability、Quick Start、walkthrough、theory、benchmark 职责与交叉链接 |
| `main.py` presets | pass | 6 个 2D + 9 个 3D 命名 preset，默认 Stage1 轻量 direct |
| PyCharm workflow | pass | 参数物理意义、单位、合法值、qualification 边界和 CLI 等价命令 |
| Quick Start | pass | 17 个 canonical 文件；8 个旧文件保留迁移提示 |
| Code Walkthrough | pass | 索引 + 15 篇逐模块说明，覆盖全部当前源码路径 |
| Theory | pass | 从 Maxwell 强式/弱式到 Floquet、PML、DtN、RTA、direct/iterative |
| Feature benchmarks | pass | 13 个 case，每个 22 项信息契约 |
| RTA audit | pass | official/diagnostic 统一身份；修复有耗传播模与实际端口面功率 |
| Metadata/checker | pass | 实际来源与 canonical rerun 分离；87/87 Gate |
| Contract tests | pass | 文档、链接、preset/parser、benchmark metadata 自动检查 |

逐项技术回应见 `../response_v2.md`。

## 主要代码改动

| 模块 | 修改 |
|---|---|
| `src/main.py` | 安全命名 preset facade、Stage1 默认、`--list-presets` |
| `src/runners/run_cases.py` | 复折射率字符串 parser |
| `src/common/config_3d.py` | direct profile 公共配置 |
| `src/runners/run_3d_cases.py` | `default` / `mumps_ooc` / `mumps_blr` CLI |
| `src/solvers/common_3d_solve.py` | MUMPS OOC/BLR PETSc options |
| `src/solvers/stage4_runtime.py` | canonical Stage4 physical model metadata |
| `src/solvers/solve_port_maxwell.py` | 有耗传播模不再按 `Im(beta)=0` 误判 |
| `src/postprocessing/power_metrics.py` | 使用实际端口面系数计算有耗 modal power |
| `benchmarks/check_benchmarks.py` | provenance、物理模型、solver 和 qualification Gate |

## 文档规模

| 文档层 | 本轮 canonical 结构 | 说明 |
|---|---:|---|
| Quick Start | 17 文件 | 另保留 8 个旧指南作为迁移入口 |
| Code Walkthrough | 1 个总索引 + 15 篇 | 文件、符号、数据流、生命周期、理论与测试 |
| Theory | 1 个索引 + 9 篇主文档 | 从强式到求解器和研究边界 |
| Benchmark cases | 13 个 | 每个 22 项字段，区分 verified/test-backed/experimental |

## 物理模型

### Canonical Stage4B workstation

| 参数 | 值 |
|---|---|
| domain | 50 x 25 x 140 nm |
| grating | 17 x 25 x 120 nm |
| wavelength | 13.5 nm |
| incidence | `theta_from_z=80 deg`，`phi=0 deg` |
| polarization | s |
| element | N1curl p=2 |
| materials | complex Si refractive index |
| official output | DtN modal R/T + volume absorption |

### Response V2 有耗 2D smoke

复折射率导致半空间纵向波数 `beta` 为复数。传播性现在由 `Re(beta)>0`、`Re(beta^2)` 和 Rayleigh 容差共同判定；功率使用实际端口面模态系数，参考面归一化振幅只用于报告。

## Numerical Settings

| 参数 | Workstation profile |
|---|---|
| operator | exact matrix-free `F-C H^-1 D` |
| outer | right FGMRES，restart=100，rtol=1e-6 |
| coarse | 24 z intervals，25 nodes x 3 components = 75D |
| local PC | 16 complete physical z slabs，overlap=0.25 |
| factor | shifted-F ILU1 |
| smoothing | sm2，即每次两步固定内层 GMRES |
| MPI | 4 |

## Key Results

### 既有 canonical workstation records

| h/nm | FE DoF | iterations | full residual | total peak RSS | total time |
|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,201 | 9.83949e-7 | 1.991 GB | 130.8 s |
| 3 | 198,438 | 993 | 9.93265e-7 | 5.082 GB | 411.8 s |
| 2 | 615,108 | 1,804 | 9.99738e-7 | 13.080 GB | 2,538.8 s |

本轮只审计并规范化这些 records，没有因文档重构重跑 h=2。

### Response V2 新增轻量实跑

| 案例 | DoF | residual | R | T | A_volume | closure |
|---|---:|---:|---:|---:|---:|---:|
| 3D Stage1 默认 | 98 | 1.436e-16 | - | - | - | 场方向余弦=1 |
| 2D TM complex absorption | 14,452 + 30 aux | 3.323e-14 | 3.663e-6 | 0.8821724521 | 0.1178238854 | 3.33e-15 |
| 2D TE complex absorption | 56 | 1.486e-15 | 8.746e-5 | 0.9903457798 | 0.0095667639 | -5.50e-16 |

## Energy Check

| h/nm | R | T | A_volume | R+T+A | closure |
|---:|---:|---:|---:|---:|---:|
| 5 | 0.0890216032 | 0.4425882752 | 0.4683901190 | 0.9999999974 | -2.55e-9 |
| 3 | 0.00461303245 | 0.5836533646 | 0.4117336036 | 1.0000000006 | 6.18e-10 |
| 2 | 0.00134293630 | 0.5992132418 | 0.3994438284 | 1.0000000066 | 6.58e-9 |

3D official source 为 `dtn_port_modal_amplitudes`；2D DtN official source 为 auxiliary modal amplitudes，并由 boundary trace cross-check。Probe 和 sampled flux 仍只作 diagnostic。

## Mesh / DoF / Solver Cost

| 案例 | 规模 | 内存/资源结论 |
|---|---:|---|
| Stage1 默认 smoke | 48 cells / 98 DoF | total RSS 274.4 MB |
| h5 iterative | 44,698 DoF | 1.991 GB |
| h3 iterative | 198,438 DoF | 5.082 GB |
| h2 iterative | 615,108 DoF | 13.080 GB，低于 14 GB Gate |
| h2 direct reviewed reference | 615,188 DoF | 约 20.533 GB，本轮未重跑 |

## Validation

| 检查 | 结果 |
|---|---|
| compileall | pass |
| Ruff check / format | 16 个改动 Python 文件 pass |
| full unit suite | 105 passed，10 skipped |
| focused MPI4 | 每个 rank 14 passed |
| documentation/local links | pass |
| 15 preset / runner parser contract | pass |
| benchmark checker | 87/87 passed |
| clean artifact policy | pass；大型结果仍 gitignored |

## Known Issues

1. Stage2B PML 与 Stage2C Fresnel 仍是 experimental/not_verified_accuracy。
2. workstation profile 只对冻结的 p=2、h5/h3/h2 模型 qualified，不代表参数域普适。
3. h=1.5、near-Rayleigh、角度/波长/材料鲁棒性和物理网格收敛仍未完成。
4. complex MPC 基础镜像缺少公开 pull source，环境只能标为 `qualified_local_image`。
5. 2D probe closure 在有耗案例中仍可偏离 official modal closure，因此继续是 diagnostic_only。

## Next Questions for Review

1. 五层文档与 13 个 benchmark 是否已达到可学习、可运行、可追溯要求？
2. 有耗端口实际平面功率定义和 official/diagnostic 身份是否可接受？
3. 87 项 provenance/physical model Gate 是否足以保护 canonical records？
4. 审查通过后，是否由用户许可将该分支合并到 `master`？
