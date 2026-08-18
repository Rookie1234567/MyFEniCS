# V5-3/V5-4：exact-side state 与 modal/Krylov compaction 阶段说明

这两阶段先减少“同时驻留的对象”：求解器不再为了后续 action 保留已经可以由 PETSc
factor handle 替代的 KSP/PC/原矩阵，也不为一次 modal Schur 的重复检查保留第二份完整矩阵。
它们是显式 Task39 research opt-in；ordinary defaults、数学方程和普通调用路径不变。

## 1. V5-3 factor-only state

实现绑定 commit `61d3b06f38eea3131d3e5f7a7b82577ace5a9f1f`，核心入口是
`ResearchExactFactorInverse`、`ResearchExactSideLuAction` 和
`HybridLocalDtnWoodburyOracle`。

| 生命周期 | 保留/释放语义 | 证据边界 |
|---|---|---|
| factor ready | 从 `PC.getFactorMatrix()` 取得 owned factor Mat；销毁 KSP/PC setup wrapper | factor-only opt-in |
| Woodbury setup | 保留 `D`、`K` 的 LU/pivots 与必要 shape/condition；`F/C/H` 只借用到 construction 完成 | `K=H-D F^{-1}C` 不变 |
| construction cleanup | F/H 原矩阵释放；retained-W 路径保留完整 W；streaming-W 路径释放 W 并转移 C action ownership | C action 是 streaming 例外，不能写成 C 已释放 |
| destroy | factor count 归零；action-owned C 由 action destroy，retained 路径的 C 由 caller destroy；D 按外部生命周期释放 | 无 use-after-free |

V5-3 的 focused Gate 覆盖 factor-only round-trip、重复 apply、linearity、非零 `C/D/H`
Woodbury residual、destroy 顺序和 ordinary default。`test239` 覆盖 exact-side action 与
streaming lifecycle，`test285` 覆盖 V5 setup orchestration 的 release/marker 语义；此前
qualified serial/MPI2/MPI4 小夹具已通过。没有把这个阶段的对象容量自动当作 h4
process-tree peak。

## 2. V5-4 single-build modal Schur 与固定 PC

V5-4 实现绑定 commit `2eab55d70e4bd4f7473c908c88dcfa18e1c94e9b`，冻结 sampled-column
合同见 [sampled-column record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_v4_h4_modal_schur_sampled_columns_v1.json)。

### Modal Schur

显式 opt-in 的 sampled path 只建立一次完整 modal Schur；固定列重构后与对应完整矩阵列
比较，检查 matrix repeat `<=1e-13`、LU repeat `<=1e-13`、列 hash/顺序/角色和
bottom/top action 覆盖。默认未提供 sampled contract 时仍保持原 double-build 行为，未把
sampled 列选择变成运行误差驱动的 selector。

### Krylov 类型

默认 outer KSP 仍为 FGMRES restart90。只有已证明固定线性 PC 的显式 V5 profile 才使用
GMRES restart10；diagnostics 记录实际 PETSc KSP type/restart，而不是只改标签。variable
PC 仍使用 FGMRES，ordinary caller 不变。

相关 focused Gate 包括 `test241` modal Schur single-build/equivalence/hash、固定 PC
linearity，以及 `test245` 的真实 FGMRES90/GMRES10 tiny solve；`test285` 检查 sampled
contract、single-build 和 V5 wiring。该阶段没有重新启动 h4 setup/full solve。

## 3. 与 V5-5 的关系和边界

V5-5 component runner/action 分别绑定 [runner commit `76d374f8`](../../../benchmarks/task039_v5_streaming_woodbury_component.py)
和 [streaming action commit `9ca332bf`](../../../src/solvers/hybrid_local_dtn_woodbury.py)。
四次 MPI1 synthetic fresh-process component 证明了 retained-W 与 batch8/16/32 的 action
等价和 ownership cleanup；它不替代 V5-2 的 h4 setup-only process-tree evidence，也不
形成新的 h4 formal solve。

当前尚无 fresh h4 post-compaction process-tree measurement，因此以下结论仍是
`not_established`：

- factor-only/streaming 在 h4/MPI8 全流程的实际 RSS/PSS/USS 变化；
- h4 outer solve、recovery、R/T/A、field/canonical 和 physics Gate；
- 是否达到 V5 advancement 或 meaningful memory line。

V5-2 的 setup-only 15-marker evidence 仍是 [h4 memory attribution](v5_h4_exact_side_memory_attribution.md)，
V5-5 component raw/record 见 [streaming-W record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_streaming_woodbury_component_v1.json)。
任何 h4 资源改善都必须由新的完整 process-tree run 重新测量，不能用 synthetic
`ru_maxrss` 或对象字节派生为正式 saving。
