# Task032 Phase 6e 真实 QEP Hybrid runner

## 1. 当前结论

`benchmarks/run_task032_phase6_augmented.py` 已把真实 Stage4 截面 QEP、正反向伴随双正交基、
稳定传播、上下局部 FEM-DtN、单体增广 AIJ、MUMPS 和外端口 R/T/A 串成一条 MPI4 路径。

h5 的 M=2/4/6 研究漏斗已跑通；M4 到 M6 的 R/T/A 变化约 `1e-12`。这证明当前截面在该
单点上已达到强模式截断稳定，但本阶段仍保留
`physical_integration_pass_mode_convergence_pending`：尚未验证 pointwise H jump、体吸收和
中间选面 E/H 重建，也未完成 h3 Hybrid。

## 2. 调用链和对象所有权

runner 的顺序固定为：

```text
matching stage4_xy cross-section
-> distributed quadratic beta operators
-> +beta / -beta right QEP
-> adjoint QEP and biorthogonal bases
-> bottom/top one-sided FEM-DtN
-> internal modal projection/traction/P+/P-
-> rank-major monolithic AIJ
-> MUMPS direct solve
-> interface algebra + external Fourier-DtN R/T/A
```

`HybridAugmentedDirectSolution` 只拥有单体 `x/KSP` 和拆出的 bottom/top 向量；
`HybridAugmentedDirectSystem` 只拥有单体 `A/b`。局部系统、coupling、mode basis 和 QEP operators
由 runner 反向释放，因此没有 double destroy。

## 3. QEP mode-count 合同

SLEPc 的 `nev=M` 可能返回多于 M 个已收敛本征对。M=4 时实际 `nconv` 为正向 5、负向 6；
M=6 时两侧均为 8。`solve_quadratic_beta_modes` 现在仍在 report 中保留原始 `converged_modes`，
但只向下游交付按 `abs(beta-target)` 排序后的前 M 个，并立即销毁超额 PETSc vectors。

这样同时保留了收敛诊断和精确 `M/M` coupling shape；如果实际收敛数少于 M，则不会伪造模式，
下游仍会 fail closed。

## 4. 共享 Poynting evaluator

正向 basis 正常后，第二次创建负向 `PoyntingFluxEvaluator` 曾让 MPI4 在重复 JIT/collective 路径
持续占满 CPU。`build_biorthogonal_mode_basis` 因此接受可选的已编译 evaluator；Phase 6 runner
让正负基共享一个 evaluator。默认参数仍为 `None`，不改变 Phase 3 既有调用和正式记录。

runner 的细粒度日志覆盖：adjoint PEP 返回、left/right assignment、Poynting 输入、flux
normalization、block normalization 和 classified record。它把“高 CPU 仍在算”与 MPI 死锁分开。

## 5. Nedelec target-cell 路由

二维 Nédélec 场在单元边界只有切向连续，法向分量可能双值。旧路由仅按 `(x,y)` 坐标统一选择
一个二维 source cell；M=6 新增模式在 bottom 的第 5/6 列因此产生 `0.00285/0.01239` 相对误差。

`_ReusableInterfaceLifter` 现在为每个三维 target cell 的每个插值点附带匹配的二维 source-cell
key。cell-major/point-major 顺序用 target cell bounds 自动验证，不靠猜测。修复后同两列在
bottom/top 都约为 `2e-14`，两个 surface Gram 条件数也完全一致。

通信范围没有扩大：仍只 allgather 结构化 cell-owner metadata，并用 alltoall 交换接口点和两个
复切向分量；没有 gather 完整 field/mode。

## 6. 近简并 block normalization

M=6 包含三个完整近简并对。中间一对的 beta 相对 spread 为 `1.86e-7`；若仍使用 Phase 3 默认
`block_rotation_tolerance=1e-8`，它会退回逐模对角缩放并留下约 `1.8e-5` 的块内交叉项。

Phase 6 runner 显式设置：

```text
near_degenerate_tolerance = 1e-6
block_rotation_tolerance = 1e-6
```

三个组因此统一使用 `(G^-1)^H` left-basis block transform。正/负整体双正交误差降到
`1.8161e-11 / 6.8695e-11`，同时左右 QEP residual 仍低于 `1e-8` Gate。Phase 3 的全局默认值
没有被修改。

## 7. h5 研究结果

| M/方向 | matrix size | nnz | R | T | A balance |
|---:|---:|---:|---:|---:|---:|
| 2 | 13736 | 1459184 | 0.0890250247 | 0.4425697298 | 0.4684052455 |
| 4 | 13740 | 1465012 | 0.0890167705 | 0.4425771168 | 0.4684061127 |
| 6 | 13744 | 1470406 | 0.0890167705 | 0.4425771168 | 0.4684061127 |

M2 到 M4 的 `|delta R/T/A|` 为
`8.25e-6 / 7.39e-6 / 8.67e-7`；M4 到 M6 为
`8.33e-14 / 9.82e-13 / 1.07e-12`。M6 真相对残差为 `4.6392e-12`，接口 E 投影残差
`6.8809e-14`，bottom/top FE-modal traction equilibrium 为
`3.2035e-12 / 4.1597e-12`。

与 frozen full-3D h5 的 R/T/A 差为
`-4.8325e-6 / -1.1162e-5 / 1.5994e-5`。这个参考自身没有 h5--h3 网格收敛资格，因此这些差值
只作同网格诊断，不能替代后续 h3 和场重建 Gate。

## 8. provenance 卡顿边界

Windows CRLF bind mount 下，Linux 容器内 `git status` 曾单独扫描数分钟，其余 MPI rank 在
broadcast 前等待。`--allow-dirty-research` 现在只读取 HEAD，并明确记录
`dirty_research_opt_in_status_scan_skipped`；它不声称 clean。

正式路径仍必须传 `--verified-clean-sha <40-char SHA>`。这条路径比较 mounted HEAD 与宿主 clean
attestation，不运行容器内昂贵且会误报的 status scan。

clean source `5c1f12e610dd8c6040389c44c31584ab7fba66cd` 的 MPI4 h5/M6
集成记录已写入 `records/hybrid_phase6_m6.json`。其 10 个 runner Gate 和 Case080
`294/294` checker 均通过；metadata 固定 command、UTC time、image digest、host、
complex128 和 clean attestation。`official_record` 仍为 false，因为下面的场 Gate 尚未完成。

## 9. 当前 Gate 与下一步

runner 当前同时检查：精确 mode count、方向/被动分支、reciprocal pairing、双正交、左右 QEP
residual、无 growing propagation、单体真残差、接口 E 投影、FE-modal traction equilibrium 和
外端口 R/T/A finite。

`fe_modal_traction_equilibrium` 是变分行平衡，不冒充 pointwise H jump。下一小步必须重建接口
两侧 H 并直接报告 jump；随后重建 lossy volume absorption 和 z=30/60/90 nm selected planes。
