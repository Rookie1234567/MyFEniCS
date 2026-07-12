# Task028 审查回应 V2

## 总体结论

本轮已完成 `review_report_v2.md` 要求的文档体系、PyCharm 入口、功能 benchmark 和 metadata contract 重构，并在审计复折射率路径时额外修复了 2D 有耗端口功率计算错误。没有启动新预条件器研究，没有重跑资源昂贵的 h=2 direct/iterative 案例，也没有修改 `task.md` 或任何 `review_report_v*.md`。

| 项目 | 当前状态 | 证据 |
|---|---|---|
| 核心求解器整合 | 通过 | 既有 h5/h3/h2 canonical records 与 87 项 Gate |
| 文档与学习体系 | 已重构 | 5 层职责、交叉链接和文档 contract 测试 |
| PyCharm 普通入口 | 通过 | 15 个命名 preset，默认 Stage1 轻量 direct |
| 复折射率 CLI/功率 | 通过 | complex parser、有耗传播模和实际端口面功率修复 |
| Benchmark catalog | 通过 | 13 个 case，每个覆盖 22 项信息契约 |
| 自动验证 | 通过 | 105 项测试、10 项跳过、MPI4 每 rank 14 项、87/87 Gate |
| 环境 | 限定通过 | `qualified_local_image`，保留 digest-pinned reference |
| 合并 master | 未执行 | 等待最终审查和用户许可 |

## 1. 文档体系

文档按用途拆为五层，避免把教程、理论推导和数值证据混在同一篇长文中：

| 层级 | 回答的问题 | 入口 |
|---|---|---|
| Capability / Progress | 当前支持什么、开发到哪里 | `docs/capability_matrix.md`、`docs/development_progress.md` |
| Quick Start | 怎样在 PyCharm 或 CLI 配置并运行 | `notes/quick_start/README.md` |
| Code Walkthrough | 配置如何流入网格、弱式、边界、求解器和后处理 | `notes/reference/code_walkthrough.md` |
| Theory | 方程、边界算子、功率和线性代数为何成立 | `notes/theory/README.md` |
| Benchmark | 哪个冻结问题证明哪项能力，以及没有证明什么 | `benchmarks/cases/README.md` |

`docs/capability_matrix.md` 已把每项能力映射到 Quick Start、Theory 和 Benchmark；`test_26_documentation_contract.py` 自动检查索引、文件、相对链接和 benchmark 模板字段。

## 2. `main.py` 命名 preset

`src/main.py` 已改为安全的命名 preset facade。它只负责把用户选择翻译为真实 runner CLI，不复制求解器实现。

| 维度 | preset |
|---|---|
| 2D | `2d_tm_pml_floquet_smoke`、`2d_tm_dtn_auxiliary_smoke`、`2d_tm_dtn_explicit_smoke`、`2d_te_port_smoke`、`2d_complex_absorption`、`2d_euv_grating_direct` |
| 3D 基础 | `3d_stage1_airbox_smoke`、`3d_stage2a_floquet_smoke`、`3d_stage2b_pml_smoke`、`3d_stage2c_fresnel_smoke` |
| 3D Stage4 | `3d_stage4a_flat_layer_direct`、`3d_stage4b_grating_direct_h5`、`3d_stage4b_grating_direct_h3`、`3d_stage4b_grating_mumps_ooc`、`3d_stage4b_grating_mumps_blr` |

完成的安全修正：

1. 默认 preset 改为 10 x 10 x 10 nm、p=1、h=5 nm 的 `3d_stage1_airbox_smoke`。
2. 删除虚构的 `stage2_all`、`stage4_all` 和 `case=both` 描述。
3. `--list-presets` 可列出全部入口，`--preset NAME` 可显式选择。
4. `test_27_main_preset_contract.py` 将每个 preset 送入真实 runner parser，防止文档和 CLI 再次漂移。
5. workstation iterative 始终保持 MPI4 显式入口，普通单进程 Run 不会静默启动或冒充 qualified 运行。

## 3. PyCharm 工作流

`notes/quick_start/00_environment_and_pycharm.md` 和 `01_main_py_parameter_map.md` 现在从解释器、Docker volume、Working directory 开始，说明如何修改 `ACTIVE_PYCHARM_PRESET`，以及参数的物理对象、单位、合法值和 qualification 边界。

2D 入口已补齐：

- scattered PML 的 top/bottom thickness 与 alpha；
- `1.45`、`0.999+0.002j`、`0.999+0.002i` 三种折射率输入；
- TM/TE、PML/Robin/DtN、explicit/auxiliary 分支；
- official modal power、volume absorption 与 diagnostic probe/flux 身份。

3D Stage4 入口已暴露 `default`、`mumps_ooc`、`mumps_blr` 三个 direct profile。BLR 被准确描述为压缩 direct/inexact factorization，不再称为独立迭代法。

## 4. Quick Start 迁移

新增 17 个 canonical Quick Start 文件，覆盖环境、参数、结果、2D 全部边界路径、3D Stage1/2A/2B/2C/4A/4B、direct OOC/BLR、workstation iterative 和参数扫描。每篇按统一结构写明：

1. 功能目的和前提；
2. PyCharm preset 与 CLI 等价命令；
3. 参数含义和可安全修改范围；
4. 输出文件、成功判据和常见错误；
5. 对应 Theory、Code Walkthrough 和 Benchmark。

原有 8 篇长期使用说明没有删除；仍有效内容已迁入新结构，旧文件顶部增加历史/迁移提示并链接 canonical 文档。

## 5. Code Walkthrough 拆分

`notes/reference/code_walkthrough.md` 现在是阅读索引，目录下 15 篇模块文档覆盖：入口与 runner、2D 配置/网格/材料、2D 弱式与 DtN/RTA、3D staged 架构、Floquet/PML/DtN/RTA、direct profiles、exact condensation、physical-slab PC、workstation runtime、输出 schema 和测试契约。

每篇均给出主要文件、关键类或函数、输入输出、调用者、PETSc/DOLFINx 对象生命周期、理论公式对应关系、official/diagnostic/research-only 身份以及覆盖测试。`src/solvers/_old/` 被明确标记为弃用历史，不进入当前调用链。

## 6. Theory 更新

新增理论索引和 9 篇主文档，从强形式开始串联完整推导：

| 主题 | 核心内容 |
|---|---|
| Maxwell 与 FEM | 时谐约定、强式、分部积分、弱式、Nedelec H(curl)、TE/TM 降维 |
| Floquet | Bloch 相位、双周期配对、波矢与衍射阶 |
| PML / Robin | 复坐标拉伸、本构张量、scattered-field、局部开放边界限制 |
| DtN | modal admittance、explicit `Q^H Y Q`、auxiliary augmented system |
| R/T/A | Poynting、modal power、volume absorption、official/diagnostic 判定 |
| 3D stages | Stage1、2A、2B、2C、4A、4B 各自增加和验证的物理对象 |
| Direct | MUMPS、OOC、BLR 的作用、资源和边界 |
| Iterative | exact condensation、right FGMRES、slab Schwarz、75D coarse、sm2 |
| 研究边界 | 负结果、适用域和后续研究路线 |

DtN 文档完整给出

\[
\begin{bmatrix}F&C\\D&H\end{bmatrix}
\begin{bmatrix}u\\a\end{bmatrix}
=\begin{bmatrix}b_F\\b_H\end{bmatrix},
\qquad
A_c=F-CH^{-1}D,
\]

并解释 matrix-free action、转置/共轭转置、回代恢复 modal amplitude，以及这些公式在 `condensed_dtn.py` 中的实现位置。

## 7. Feature Benchmark cases

建立 13 个 case-contained 目录：001、002、003、010、011、012、013、020、021、022、030、031、040。每个 `README.md` 都包含审查要求的 22 项：问题、几何、材料、入射、边界、网格、preset、CLI、调用链、理论、求解器、RTA 身份、输出、Gate、record、artifact 和限制。

| 类别 | Benchmark | 当前证据级别 |
|---|---|---|
| 2D | 001 PML、002 DtN 等价、003 TE/TM complex absorption | smoke / test-backed；有耗 RTA 有真实补充运行 |
| 3D staged | 010 Stage1、011 Stage2A、012 Stage2B、013 Stage2C | Stage1/2A 验证；2B/2C 明确为 experimental/not_verified_accuracy |
| 3D power | 020 Stage4A、021 Stage4B direct | canonical records 与既有数值证据 |
| 代数与资源 | 022 condensation、030 OOC/BLR、031 workstation iterative、040 MPI/p regression | test-backed 或 canonical records，边界逐项声明 |

没有 record 的 case 明确标注 `test-backed` 或 `experimental`，没有用目录存在性冒充物理精度验证。大型 mesh/field 仍只写入 gitignored artifact root。

## 8. Official / diagnostic RTA 审计与有耗端口修复

统一身份表位于 `notes/theory/official_and_diagnostic_rta_methods.md`。当前规则是：

| 方法 | 身份 | 用途 |
|---|---|---|
| DtN auxiliary modal amplitudes | official/recommended | 2D/3D 主 R/T |
| explicit trace/modal projection | reference/cross-check | 检查 auxiliary 等价性 |
| volume `Im(epsilon)|E|^2` | official absorption | 有耗材料 A |
| E/H Fourier probe | diagnostic_only | 场与模态拟合诊断 |
| sampled net flux / Poynting | diagnostic_only/consistency | 采样和能流检查 |

审计中发现两个互相关联的问题：

1. 有耗半空间的 `beta` 本来就是复数，旧逻辑要求其虚部接近零，因而把真实传播的透射模当成倏逝模。
2. 报告振幅会相位归一化回参考面；旧功率路径错误地也使用该归一化振幅，等价于撤销有限有耗层中的真实衰减。

修正后，传播判定使用 `Re(beta)>0` 与 `Re(beta^2)` 的色散信息，并排除 Rayleigh 邻域；功率始终使用实际端口面系数

\[
P_m=L_x\,\frac{\operatorname{Re}Y_m}{2}\,|a_m(y_{port})|^2,
\]

相位归一化振幅只保留为报告字段。

| 真实 smoke | FE DoF | residual | R | T | A_volume | `1-R-T-A` |
|---|---:|---:|---:|---:|---:|---:|
| 2D TM complex absorption | 14,452 | 3.323e-14 | 3.663e-6 | 0.8821724521 | 0.1178238854 | 3.33e-15 |
| 2D TE complex absorption | 56 | 1.486e-15 | 8.746e-5 | 0.9903457798 | 0.0095667639 | -5.50e-16 |

TM 的 official auxiliary、boundary trace 和 volume absorption 一致到约 `3.3e-15`；probe closure 仍约 `2.13e-2`，因此继续诚实保留为 diagnostic，而不是为了表面闭合替换 official 结果。

## 9. Metadata 与 checker 修正

h3/h2 历史 record 已拆分实际来源和未来 canonical 重跑信息：

- `actual_source_command` / `actual_source_artifact_root`；
- `canonical_rerun_command` / `canonical_artifact_root`；
- `resolved_config`、`physical_model`、`artifact_directory`、`record_path`；
- `qualified_profile`、`deviations`、`git_dirty` 和 provenance。

checker 新增 benchmark ID、metadata 完整性、commit relation、真实/规范路径一致性、clean source、qualified profile、`ksp_reason>0`、coarse condition、完整物理模型和 checkout dirty 解释等 Gate。当前结果为 `87/87`，自动报告中 `checkout_dirty=true` 被明确解释为“在尚未提交的候选工作区生成报告”，不是伪装成 clean rerun。

`benchmarks/environment.json` 同时保留观察到的基础镜像 tag、digest 和 digest-pinned reference；由于基础 complex MPC 镜像没有公开 pull source，状态继续是 `qualified_local_image`。

## 10. 测试与剩余限制

| 验证 | 结果 |
|---|---|
| `compileall` | 通过 |
| 完整 `src/test` | 105 通过，10 跳过 |
| MPI4 focused suite | 4 个 rank 各 14 通过 |
| preset/parser contract | 15 个 preset 全部通过真实 parser |
| documentation contract | 索引、相对链接、13 cases/22 fields 通过 |
| benchmark checker | 87/87 |
| 默认 Stage1 实跑 | 98 DoF，residual 1.436e-16，RSS 274.4 MB |

本轮保留的限制：

1. h=2 direct 仍引用已审查的约 20.533 GB 历史 reference；本轮未重跑。
2. h=2 iterative 也没有因文档重构重复运行；Gate 审计原有 13.080 GB canonical record。
3. Stage2B PML 与 Stage2C Fresnel 仍是 path smoke / experimental，未宣称精度收敛。
4. workstation profile 只对冻结的 p=2、h5/h3/h2 目标模型 qualified，不代表角度、波长、材料或几何普适。
5. h=1.5、near-Rayleigh、参数扫描鲁棒性和公开可重建基础镜像仍待后续任务。

## 最终建议

Task028 Response V2 的代码、文档、benchmark 和自动 Gate 已完成，可提交同一分支供最终审查。是否合并到 `master` 仍由用户在审查通过后决定；本轮不自行合并，也不启动 Task029。
