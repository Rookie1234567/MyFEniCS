# Case060：Task030 H(curl) 基础设施与 compact physical-slab 低内存实验配置

## 当前状态

Case060 当前为 `workstation_success_experimental_opt_in`。五类真正 p/h 候选在 h5 100 步均为明确负结果；最终有效候选是 Task27-derived physical-slab + 75D Floquet z-hat wave coarse 架构，并使用 symmetric pre/post ILU0、subdomain-local shift、factor-only storage 和 FGMRES restart90。h5/h3/h2 full solve 均已通过；h2 为 1873 步、真残差 `9.972228e-7`、含 R/T/A 峰值 9.374729 GB。

## 合同

| 项目 | 值 |
|---|---|
| 1. ID | `060_multilevel_hcurl_iterative_solver` |
| 2. 证明 | H(curl) transfer/Galerkin 研究基础设施正确性与 compact physical-slab low-memory profile 的 h5/h3/h2 工程证据 |
| 3. 不证明 | 任意参数鲁棒、严格 mesh-independent 或已成功的 production p/h GMG |
| 4. 物理配置来源 | `benchmarks/configs/workstation_p2.json` / Case031 frozen target |
| 5. 几何 | 50×25×140 nm cell；17×25×120 nm block |
| 6. 材料 | 13.5 nm complex Si |
| 7. 入射 | theta=80°、phi=0°、s polarization |
| 8. 边界 | double Floquet + auxiliary Fourier-DtN |
| 9. FE/mesh | fine p2 Nédélec；h5/h3/h2 target |
| 10. MPI | 4 ranks |
| 11. outer operator | exact matrix-free `F-C H^-1D` |
| 12. propagating modes | 80，禁止减少或替换 |
| 13. h5 funnel | 20-step smoke + 100-step explicit true residual |
| 14. hierarchy | active-column nonmatching p2/p1 transfer + exact `P^HAP` |
| 15. final coarse | fixed 75D Floquet z-hat wave coarse |
| 16. final smoother | 16 slabs、overlap0.25、ILU0、sm2 symmetric pre/post |
| 17. storage | subdomain-local shift + factor-only |
| 18. Krylov | right FGMRES restart90、rtol `1e-6` |
| 19. numeric Gate | reported/condensed/full true residual + official R/T/A |
| 20. heavy artifacts | `benchmarks/artifacts/cases/060/`，不提交 |
| 21. records | 只提交轻量 hierarchy/transfer/screen/h5/h3/h2 摘要；正式 best records 含 provenance 与 artifact SHA-256 |
| 22. ordinary default | 不改变；全部新路径显式 opt-in |

## 物理问题

物理模型与 Case031 完全一致：3D p2 Nédélec、双 Floquet、80 个 `auto_propagating` modal unknowns、auxiliary Stage4 assembly 和 exact condensed outer action。求解器研究不得改变材料、角度、波长、模式集合、R/T/A 定义或 full residual 定义。

## 参数说明

`config.json` 同时记录统一 h5 funnel、失败 p/h hierarchy 和最终 compact candidate。`expected.json` 提供标准 case 状态与顶层 Gate；详细阈值位于 `expected/gates.json`。`records/h5_baseline.json` 通过 SHA-256 指向 Case031 canonical h5 record，筛选器运行时读取 iteration100 residual，禁止手写替代。

## PyCharm

在 PyCharm 中使用 Docker 解释器或 External Tool，working directory 指向仓库根目录。研究层级模块设为 `benchmarks.run_task030_multilevel_hcurl`；最终候选模块设为 `benchmarks.run_workstation_iterative`。普通 Windows Python 缺少 complex PETSc/DOLFINx，不能作为数值资格环境。

## CLI 或测试

研究 hierarchy 和统一候选筛选：

```bash
mpiexec -n 4 python -m benchmarks.run_task030_multilevel_hcurl hierarchy --build-transfer
mpiexec -n 4 python -m benchmarks.run_task030_multilevel_hcurl screen \
  --candidate jacobi_ph --max-it 100 --record /tmp/jacobi.json
```

最终显式候选：

```bash
mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
  --h-nm 5 --post-smooth --subdomain-local-shift --factor-only-storage \
  --num-slabs 16 --overlap-layers 0.25 --ilu-levels 0 --restart 90 \
  --max-it 1200 --record /tmp/task030_h5.json
```

## 代码路径与理论

研究路径：`run_task030_multilevel_hcurl -> hcurl_multilevel -> stage4_runtime -> condensed_dtn`。最终路径：`run_workstation_iterative -> physical_slab_two_level -> condensed_dtn -> official RTA`。理论见 `notes/theory/iterative_solver_and_preconditioner.md`，对象与生命周期见 walkthrough 32/33/50。

## 当前证据

MPI4 transfer 为 `44698×792`、145,998 nnz，无零列；adjoint error `1.586e-15`、fresh/cache action error `6.410e-15`。五个正式 p/h 候选 100 步 residual 为 `0.375–0.680`，相对 Task027 基线为 146–264 倍，全部 negative。

最终 compact physical-slab candidate：h5 855 步、`9.924905e-7`、1.696136 GB；h3 962 步、`9.903890e-7`、3.807503 GB。两者 R/T/A 对 direct 最大差小于 `5.44e-9`。h3 略高于 3.8 GB 绝对目标，凭相对 canonical 5.082275 GB 降低 25.08% 的替代 Gate 通过；h3/h5 iteration ratio 1.1251。

h2 attempt1 峰值 9.342113 GB，1800 步 true residual `1.461130e-6`，严格未通过且没有 official R/T/A。随后仅对同一候选把 `max_it` 延到 2100：1873 步收敛，full true residual `9.972228e-7`，含 R/T/A 峰值 9.374729 GB，较 Task27 降低 28.33%；R/T/A 对 direct 的最大差为 `6.561e-9`。它通过 workstation Gate，但未达到 `iterations <=1200` 的工程偏好。

## 结果解释

transfer/Galerkin 的 algebra pass 与 solver negative 必须分开。当前 792D p1 coarse 没有覆盖 Maxwell 近核/梯度和 grazing-wave 慢误差；真正的正反馈来自 75D wave coarse 与对称平滑。local shift、factor-only 和 restart90 在保持该收敛机制时压缩存储。

正式 h5/h3/h2 records 的 source commit 为 `bfb6586e`，重型运行时 tracked source 为 dirty；因此 provenance 据实标记为 `working_tree_source_artifact_recovered_without_rerun`，并固定各自 artifact SHA-256。checker 用 203 项 Gate 核验 provenance、80 modes、三残差、official R/T/A、能量闭合、direct delta、内存与分类，manifest 可重复生成 summary。

Task27 ILU1 与 Task30 ILU0 的 `global_slab_factor_nnz` 记录相同，当前统计不能证明 ILU0 factor-nnz compression。内存下降主要归因于 factor-only 生命周期、local shift、释放 source submatrix/KSP/PC wrapper 与 restart90。factor-only 仅在 PETSc 3.24.0 complex build 验证，跨版本需要 action/lifecycle 回归。

## 数值 Gate

- h5/h3 full true residual `<=1e-6`；
- h5 R/T/A 对 direct 最大差 `<=1e-6`；
- h3 peak `<=3.8 GB` 或较 Task027 至少降低 25%；
- h3/h5 iteration ratio `<=2`；
- h2 peak `<=10 GB`、full true residual `<=1e-6`、同一 80 modes；
- 未收敛场不得输出 official R/T/A。

## 限制

Case060 不是 ordinary profile。`workstation_success` 只覆盖冻结 target、MPI4、80 modes 和显式 opt-in 参数；真正 commuting multigrid、AMS/HX、参数域外鲁棒和 h<2 均未实现或未验证。`strong_workstation_success` 未达到，ordinary default 仍未改变。

heavy transfer cache、matrix、history、field 和 solver log 只保留在 ignored artifacts；用户本地 papers 与其他任务 raw runs 不属于本 Case。
