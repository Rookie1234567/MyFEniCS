# Task037b H2a/H2b block action identity

## 范围与边界

H2a 验证 assembled-block algebraic action identity；H2b 进一步验证从构造开始就采用
matrix-free local endcap 的 exact action identity。两条 production 侧都创建 PETSc
MatPython action，不装配或保存 global monolithic AIJ；H2a 的 bottom/top terminal FEM
块仍是 assembled A，H2b 则从 local-Schur action 和 condensed DtN action 开始。
测试侧才创建 `build_hybrid_augmented_direct_system(...).A` 或 explicit-condensed
local oracle。H3 的第一次 outer FGMRES / exact block-LDU iterative oracle 尚未开始。

| 项目 | 事实 |
|---|---|
| code/test commit | `41f692d2a7a8fce81ac49859c0f52cbcfda542e6` |
| production module | `src/solvers/hybrid_fem_modal_iterative.py` |
| focused test | `src/test/test_234_task037b_hybrid_block_operator.py` |
| source branch | `codex/20260807-task37b-hybrid-iterative-development` |
| test worktree HEAD before code commit | `396915270faa140855af2f6cf4289f1f3d8ffb09` |
| ABI | qualified WSL stack；PETSc `complex128/int32` |
| production inventory | `matrix_type=python`、`matrix_free=true`、`global_A_materialized=false` |
| assembled blocks | bottom/top `A` borrowed and assembled；不在 context 中形成 global AIJ |

测试执行时 Git HEAD 是 `396915270faa140855af2f6cf4289f1f3d8ffb09`，两个 H2a 文件是该
worktree 中的 exact untracked content；随后未改变内容地固定为上表 code/test commit
`41f692d2a7a8fce81ac49859c0f52cbcfda542e6`。因此 `396915270...` 是测试基线，不是包含
H2a 代码的 source SHA。

## 数学与生命周期

action 按 direct builder 的同一 block 语义计算 bottom、top 和 modal 输出：terminal
assembled A、四个 traction action、bottom/top projection action，以及已缓存的
forward/backward propagation factors 和 internal modal constraint block。没有改变
符号、共轭、传播方向或 ownership 映射。

context 预分配 bottom/top source/target、四个 traction source/target 和两个
projection target。每次 `mult` 只写入已有 owned slices；modal/projection 的小向量
通过 final-rank broadcast 传递，不 gather FE 大向量。MatPython context 只销毁自己
拥有的 scratch，`destroy()` 可重复调用；borrowed blocks 不由它销毁。

## Probe identity

Gate：每个 global、bottom、top、modal action relative error `<=1e-11`；pack/split
bottom、top、modal relative error `<=1e-13`。

### MPI1

| probe | global | bottom | top | modal |
|---|---:|---:|---:|---:|
| random_0 | 1.1615101607241502e-17 | 1.1416664644165232e-17 | 1.1770350244797584e-17 | 5.382887344262224e-17 |
| random_1 | 1.2587856184900349e-17 | 1.112321704499418e-17 | 1.3821964089130918e-17 | 1.1040403976105248e-16 |
| random_2 | 1.3622226251571338e-17 | 1.524659378228285e-17 | 1.1954613763018091e-17 | 6.848964613273794e-17 |
| physical_packed_rhs | 0 | 0 | 0 | 0 |
| bottom_only | 0 | 0 | 0 | 0 |
| top_only | 0 | 0 | 0 | 0 |
| modal_only | 1.0629276820243919e-16 | 1.0691038791850924e-16 | 1.1769842512387163e-16 | 0 |

### MPI2

| probe | global | bottom | top | modal |
|---|---:|---:|---:|---:|
| random_0 | 1.1140862046575564e-17 | 1.1294005939411417e-17 | 1.0294856915499873e-17 | 3.863046629301385e-16 |
| random_1 | 9.160433353859523e-18 | 9.394198429714546e-18 | 8.299189176622594e-18 | 3.213173714299604e-16 |
| random_2 | 1.1118066583715256e-17 | 8.48682740106558e-18 | 1.2690895280231361e-17 | 1.2822552387928642e-16 |
| physical_packed_rhs | 0 | 0 | 0 | 0 |
| bottom_only | 0 | 0 | 0 | 0 |
| top_only | 0 | 0 | 0 | 0 |
| modal_only | 1.0394973963451826e-16 | 1.0228229395316304e-16 | 1.2433329682466174e-16 | 0 |

### MPI4

| probe | global | bottom | top | modal |
|---|---:|---:|---:|---:|
| random_0 | 8.043890416397432e-18 | 1.0780432593843567e-17 | 4.7909431465208585e-18 | 2.575529612635997e-16 |
| random_1 | 1.2161128529848968e-17 | 1.632599114286945e-17 | 4.220817582154086e-18 | 3.6066255021852484e-16 |
| random_2 | 1.1054952609061286e-17 | 1.4239185273401598e-17 | 6.627303294845335e-18 | 1.7383638865139366e-16 |
| physical_packed_rhs | 0 | 0 | 0 | 0 |
| bottom_only | 0 | 0 | 0 | 0 |
| top_only | 0 | 0 | 0 | 0 |
| modal_only | 8.980682105096831e-17 | 8.511460148708123e-17 | 1.1912902837123744e-16 | 0 |

### Ownership and pack/split

| MPI | mapping missing | mapping extra | duplicate mappings | pack bottom | pack top | pack modal |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | 0 | 0 | 0 | 0 | 0 | 0 |

以上 action、block component、ownership 和 pack/split 项逐项通过。它们是 H2a 的
algebraic identity evidence，不是 H3 的第一次 outer FGMRES / exact block-LDU iterative
oracle、内存资格化或 solver convergence 证明。

## 测试与静态 Gate

| Gate | 结果 |
|---|---|
| MPI1 focused H2a | 3 passed，5.59 s |
| MPI2 focused H2a | 每 rank 3 passed，3.18 s |
| MPI4 focused H2a | 每 rank 3 passed，4.91 s |
| existing direct minimal regression | 1 passed，4.17 s |
| qualified import/ABI | pass；`/home/Projects/MyFEniCS/.venv/bin/python`，complex128/int32 |
| Ruff check | pass |
| Ruff format-check | pass |
| compileall | pass |
| git diff --check | pass |

测试命令均为本地 qualified 结果；没有运行 full pytest、H3 或 PDE authority。

## H2b Matrix-free local endcap exact action identity

H2b 的 production 路径从构造开始即使用
`materialize_global_matrix=False`、`retain_local_schur_for_matrix_free=True` 和
`matrix_free_dtn=True`：先形成 fine local-Schur action，再形成
`F_s-C_ext H_ext^{-1}D_ext` 的 condensed action 与 RHS。test-only oracle 才从 direct
系统提取或建立 explicit-condensed local matrices；production candidate 不先装配再删除
local augmented A/F/C/D。

| H2b inventory | 实际合同 |
|---|---|
| global monolithic A | `false` |
| bottom/top global F | `false / false` |
| explicit external C/D | `0 / 0` |
| p6 direct factor count | `0` |
| external modes | 保留 `external_mode_count` 供恢复；不是 Krylov unknown |
| external auxiliary rows in Krylov | `0` |
| small H | 可显式保存；不冒充 p6 FE direct factor |

carrier 的销毁顺序为 condensed A、RHS、fine action、C/D/H blocks、full-FE RHS，最后
是 static-condensation owner；MatPython mult 复用已分配 scratch，不为每次 action 创建
FE 大 Vec。H2a 的 assembled bottom/top A 仍保留其原有 assembled inventory。

### H2b-L：单侧 local action

在同一 tiny p2/h10 fixture 上，direct assembled side 只作为 test-only oracle；bottom/top
各覆盖三个 deterministic active-vector probes、physical condensed RHS 和 recovered
external auxiliary。

| side | 3 probes action 最大 relative error | recovery 最大 relative error | RHS relative error | Gate |
|---|---:|---:|---:|---:|
| bottom | `3.058e-16` | `4.352e-16` | `0` | `<=1e-11` |
| top | `3.730e-16` | `4.297e-16` | `6.993e-17` | `<=1e-11` |

H2b-L 的显式 MPI1 focused test 为 `1 passed`。

### H2b-G：global coupling action

candidate bottom/top 使用 H2b action-only carriers；oracle 只替换为 test-only
explicit-condensed local A/b，并复用同一个实际 coupling。七个 probes 包括三个
deterministic random、physical packed RHS、bottom-only、top-only、modal-only；physical
RHS 的 modal 部分来自 `internal_modal_rhs_correction`。

| MPI | max over global/bottom/top/modal | Gate |
|---:|---:|---:|
| 1 | `2.942e-16` | `<=1e-11` |
| 2 | `2.988e-16` | `<=1e-11` |
| 4 | `3.539e-16` | `<=1e-11` |

每个 MPI 行的最大值均覆盖该 MPI 的七个 probes 和 global、bottom、top、modal 四个
输出块；四块逐项都不超过该行总体最大值。

| MPI | pack/split bottom/top/modal | mapping missing/extra/duplicates | 结果 |
|---:|---:|---:|---|
| 1 | `0 / 0 / 0` | `0 / 0 / 0` | pass |
| 2 | `0 / 0 / 0` | `0 / 0 / 0` | pass |
| 4 | `0 / 0 / 0` | `0 / 0 / 0` | pass |

### H2b 测试与边界

| Gate | 结果 |
|---|---|
| H2b-L MPI1 | `1 passed`，2.94 s |
| H2a+H2b MPI1 | `5 passed`，6.04 s |
| H2a+H2b MPI2 | 每 rank `5 passed`，4.52 s |
| H2a+H2b MPI4 | 每 rank `5 passed`，9.11 s |
| test224/test230/test231 | `5 passed / 1 skipped`，5.89 s |
| import、Ruff check/format-check、compileall、git diff --check | 全部 pass |

H2b 证明的是 local endcap action 与 explicit-condensed local oracle 在 MPI1/2/4 上的
代数恒等性、ownership 和生命周期路径；它不是第一次 outer FGMRES/solver convergence、
资源资格化或 H3 完成的证明。H3 是下一阶段，尚未运行。
