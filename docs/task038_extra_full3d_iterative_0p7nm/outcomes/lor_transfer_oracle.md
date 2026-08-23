# L1：LOR/HX transfer 与周期身份 oracle

## 结论

L1 验证的是高阶 H(curl) 局部自由度与 p-refined lowest-order LOR（低阶 refined edge 辅助空间）之间的转移：它检查边方向、单元排列、MPC slave/master、Floquet phase 一次处理，以及 MPI1/MPI2 的 canonical owner packet 是否一致。换句话说，它验证“同一份边上的数值在不同分区和转移路径中仍然是同一份数值”。

这不是 PDE 求解、不是收缩率计算，也不是 p6/h10 全网格 setup。p6 只运行了冻结的 single-cell transfer oracle；p2/p3 运行了 h50 periodic positive-action identity oracle。

L1 aggregate 已通过：五个固定 case 全部 individual checker 通过，aggregate `passed=true`、`errors=0`。因此 L2 有资格；L2、L3、L4、L5 尚未运行。

| 项目 | 事实 |
|---|---|
| source SHA | `08df08ab61a364b933d2d3d6e79a394d7ee1dd4e` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| aggregate | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_transfer_oracle_v1.json` |
| aggregate SHA256 | `3ba0a3e4d9feca725d426913b4b0d1ffb580d57b16334180c6d272ec3aabbd39` |
| aggregate 状态 | `passed=true`, `errors=[]` |
| ignored raw 根目录 | `benchmarks/artifacts/task038_extra_full3d_lor_hx_l1_v1/08df08a/` |

## 五个 case 的结果

相对误差均按独立 checker 从 raw 数组重算。`source→mapped` 是 full-space primal source 的转移闭合；`action→mapped` 是 full-space dual action 的转移闭合；`repeat` 是同一 action 的重复调用一致性。p6 的 periodic canonical packet 按冻结规则为 N/A。

| case | canonical source→mapped | canonical action→mapped | action repeat | de Rham gradient | curl-transferred gradient | spectral condition | record SHA256 |
|---|---:|---:|---:|---:|---:|---:|---|
| p2-mpi1 | 3.01911547972717e-16 | 7.274022664081299e-16 | 0 | 2.5158483883389295e-16 | 3.4134447350340107e-16 | 9.454227208854832 | `87271837640c22cf0e4975734b9f89c418b7371eed812eabad00b7c6ef9cba6b` |
| p2-mpi2 | 3.0270411663823476e-16 | 6.233354840807895e-16 | 0 | 2.5158483883389295e-16 | 3.4134447350340107e-16 | 9.454227208854832 | `d7681d058da95ff5c847311ed91df434cda2d8ba599ce1afb1891cb00611aa99` |
| p3-mpi1 | 1.3120174102790627e-15 | 3.676811001859452e-15 | 0 | 6.196084909502993e-16 | 6.642378881607409e-16 | 10.740847884857926 | `71207b423897d2386bedbdff8a3059b153a81d5ccdfc01e0952ce234597e24e0` |
| p3-mpi2 | 1.9222477242579387e-15 | 8.268602626757753e-15 | 0 | 6.196084909502993e-16 | 6.642378881607409e-16 | 10.740847884857926 | `cf710cb85653aceab073e9e1319dabb6c81cb4a19cb694bc383b15a1d86ae803` |
| p6-mpi1 | N/A（冻结 single-cell） | N/A（冻结 single-cell） | N/A | 1.3681393701214231e-15 | 2.3652274254542337e-15 | 15.133589067492856 | `2dd66500436a1b08643c03ab9691978d19f4402980bce192d20e98b9a169b3da` |

p2/p3 的 owner-LOR canonical packet count 分别为 768 和 2538；canonical full-space packet count 分别为 988 和 3018。每个 MPI case 都通过了 local transfer、source/action/repeat 和 forbidden-object 审核。

## 跨 MPI 与跨 degree Gate

p2/p3 的六项跨 MPI 指标均使用同 degree 的 MPI1/MPI2 raw packet 对齐比较。source、mapped source、action、mapped action、repeat 与 owner-LOR (`lor`) 的限值均为 `1e-12`，repeat 另有 `1e-13` 限值。

| degree | source | mapped source | action | mapped action | repeat | owner-LOR | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| p2 | 1.2775953296163372e-15 | 1.3179929748388957e-15 | 1.2381584949985523e-15 | 1.420968062856959e-15 | 1.420968062856959e-15 | 1.6891442874942672e-15 | PASS |
| p3 | 1.1785326786247781e-15 | 2.613278193317918e-15 | 1.4672752358543023e-15 | 7.601778810911733e-15 | 7.601778810911733e-15 | 2.051785134336476e-15 | PASS |

跨 degree spectral Gate 为

```text
2 * max(p2_condition, p3_condition)
= 2 * max(9.454227208854832, 10.740847884857926)
= 21.481695769715852
```

p6 的 `15.133589067492856 <= 21.481695769715852`，通过该 Gate。p6 的 retained reference-factor numeric tensor 为 `8,297,856 B`；这是该 single-cell oracle 的 retained payload，不是 p6/h10 全网格内存测量。

## production 边界与 ABI

正式 record 和 checker 闭合的四个 production 边界是：

| 边界 | 值 | 含义 |
|---|---|---|
| `global_transfer_matrix` | `false` | 不保留全局 transfer matrix |
| `local_tensor_action` | `true` | production transfer 使用 axis/reference-factor tensor action |
| `owner_local_maps` | `true` | LOR map 按 canonical owner-local packed map 保存 |
| `numeric_allgather` | `false` | production 路径不做 FE-sized numeric allgather |

p2/p3 的 root gather 只用于 evidence-only oracle；production route 使用 typed owner-local packets。周期 phase 只对整条位于 upper slave plane 的边在 canonical owner route 中执行一次，MPC slave/master 使用 finalized homogenize/backsubstitution，边方向使用 DOLFINx cell permutation 的 `Tt`/`T` 语义。

所有 case 的 qualified activation 为 `1`，PETSc scalar/int 为 `complex128`/`int32`，线程设置为 `OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`。记录的 ABI 为 Python 3.12.3、DOLFINx 0.10.0.post2、Basix 0.10.0、petsc4py 3.19.6、slepc4py 3.19.2、SciPy 1.11.4；MPI1 使用 qualified direct Python，MPI2 使用 qualified `mpiexec -n 2`。

## 失败与修复链

以下 raw 证据均保留，不能被最终通过记录覆盖：

| source / root | 观察 | 分类边界 |
|---|---|---|
| `433da87079b9745ad425dfd0ff71b4a36e91c44e` / `.../433da87/p2-mpi1` 与 `.../p2-mpi1_attempt2` | 两次 direct MPI1 启动发生 PETSc `VecSet` SIGSEGV，未写 record | runner lifecycle failure；无 L1 数学 Gate 结果 |
| `5ba6567ea3102d9bb6822b75cf67e3358a1fc0de` / `.../5ba6567/p2-mpi1` | marker 到 `global_roundtrip_built` 后失败；runner 销毁了 `FullspaceMpcFormAction.apply()` 返回的借用 output Vec | borrowed-vector lifecycle failure；不是 L1 数学 Gate |
| `5cb0e5437a5af99813b29d2d7546982deb1da62b` / `.../5cb0e54/p2-mpi1` | worker 已完成，但旧 checker 对已重建的 `high_gradient_edge` 又做了一次 inverse，报告了 `1.160...` 与 `1.579...` 假负 | checker double-inverse failure；raw 中正确值为 `2.5158483883389295e-16` 与 `3.4134447350340107e-16`，不是 L1 数学 Gate |
| `08df08ab61a364b933d2d3d6e79a394d7ee1dd4e` | checker 修复后五案完成并 aggregate 通过 | 最终 L1 evidence PASS |

因此，旧 partial raw 不覆盖、不重分类；最终 PASS 只绑定 `08df08a` 的五个新 case 和 aggregate record。

## 资源口径与阶段边界

本文不把未由 process-tree authority 记录绑定的 RSS 写成正式 L1 Gate。p6 命令的 `/usr/bin/time -v` auxiliary console observation 为最大 RSS `363324 KB`、swap `0`，仅用于说明 single-cell 运行事实，不是 Review 的完整 p6/h10 resource qualification，也不是 PDE 内存结论。

L1 不运行 outer PDE、contraction、p6/h10 full setup、L2 coarse 或后续 physics stages。后续 L2/L3/L4/L5 当前均为 `not_run`。
