# V3-1 联合接口代数审计

## legacy packet 首次审计状态

当前 V3-1 最终结论为 augmented packet PASS，详见文末“augmented 补强结果”；以下正文
保留 immutable V2 packet 的首次审计历史。

V3-1 的 pure-Numpy tiny oracle 已通过；但 immutable V2 packet 的矩阵语义不是 Review
要求的三个 local-group Schur。因此本次 packet 结论为
`COUPLED_PACKET_INFORMATION_INCOMPLETE`，不是数值 Gate 失败。没有组装 PDE、
PETSc/MUMPS factor 或 QEP；V3-2 在该信息缺口按 Review 决策树闭合前不进入。

输入绑定：packet manifest SHA256
`19de50f3cdb32766bf6f13fc55c9ac498b21a9a00ddc261768d7d55b7c9da8b0`，producer source
`942c43881e4162085348c48b09c79fbbdac18cd9`。独立结果保存在 ignored artifact
`results/task040_v3_1_coupled_interface_checker.json`，其 SHA256 为
`d108bf40ae6bed5cb9508e620ce858b9595a68356453cc841701ed2ffaa7095a`；该文件保留为
首次错误语义判定的证据，未覆盖或改写 raw。以下语义纠偏以源码调用链和同一 immutable
packet 只读重算为准。

本次 corrected checker source 为 `0713073cbaca8cf43423d7c92ed2408d3f6b586a`，新的
只读输出为
`results/task040_v3_1_coupled_interface_checker_corrected_0713073c.json`，SHA256
`fa1626edfb959eb700b3fd5954a53ebd2d57a8e1ecae046ca5a55175297b4e4e`，rc=2 仅表示上述
information-incomplete 分类；首次错误 artifact `d108...` 仍只作为保留证据。Compact record
为 `benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v3_1_coupled_interface_packet_audit_v1.json`。

## 固定 ordering 与输入

仅使用已完成 V2-A1 packet 中的三个 group small matrices：

| group | interface span | ordering |
|---|---:|---|
| group0 | 296 | lower |
| group1 | 776 | lower 296 后 upper 480 |
| group2 | 480 | upper |

## 旧 V2 矩阵与 Review V3 目标的语义映射

V1/V2 runner 在构造 Petrov action 时把 `exact_apply` 绑定到
`oracle.apply_directed_neighbor`；只有 middle-cross 采样显式调用
`oracle.apply_group(1)`。因此旧 packet 的三个矩阵实际是：

| 旧矩阵 | 实际响应 | 不是 |
|---|---|---|
| `projected_exact_group0` | `Y0^H R_{1→0} Z0`，middle `S1` 的 lower restriction | `Y0^H S0 Z0` |
| `projected_exact_group1` | `Y1^H blockdiag(S0,S2) Z1`，incoming neighbor map | `Y1^H S1 Z1` |
| `projected_exact_group2` | `Y2^H R_{1→2} Z2`，middle `S1` 的 upper restriction | `Y2^H S2 Z2` |

源码中的 `_neighbor_block_apply` 对 group1 明确分别调用 group0/group2，再把两个结果
相加；对 group0/group2 则调用 middle group1 后只提取同侧行，cross 输出不进入旧矩阵。
相反，已有 middle-cross reports 的 `apply_group(1)` 响应测得 lower→upper 最大
`0.6677254509073904`、upper→lower 最大 `0.14544366781366302`。这证明 cross 响应真实
存在，而旧 group1 矩阵为 block diagonal 不能代表它。

Review V3 需要的是

```math
E_g=Y_g^H S_g Z_g,\qquad
E_{joint}=E_1+\operatorname{blockdiag}(E_0,E_2),
```

其中 `E1` 必须含完整的 `S1_LU` 和 `S1_UL`。当前 packet 没有 full middle-group local
Schur contraction，至少缺少这两个 projected cross blocks，故 `joint_projected_exact`
由旧矩阵拼出的零 LU/UL 只能作为 directed-neighbor structural diagnostic。

旧 packet 的 owner-local factors 也要按其真实含义读取：
`U=delta=(directed_neighbor-scalar)Z`，`V=Y G^-H`。由 `V G^H` 可恢复 `Y`，但一般
不能由 `U` 反解 `Z`。因此若后续 V3-2 需要实际 owner-row `Z_Gamma/Y_Gamma`，`Z` 是
除 middle local Schur 小矩阵之外的第二个信息缺口；不能把 `U` 冒充 `Z`。

每组保留 `G=Y^H Z`、`projected_scalar=Y^H S_scalar Z` 和旧路径的
`projected_exact` 的 shape、rank、singular values、condition 与 SHA256。所有矩阵必须为
finite complex128；不能从 worker status 推断 Gate。这里的旧 `projected_exact` 不能直接
改名为 `Y^H S_group Z`。

本次重算的 rank/condition 摘要如下；`G` 是各 group 的 basis-overlap，不把三组 `G`
相加成没有定义的 `joint_gram`：

| group | G rank/condition | scalar rank/condition | exact rank/condition |
|---|---:|---:|---:|
| group0 | 296 / 187.9352369709664 | 296 / 485.6835752939591 | 296 / 2574.21018122354 |
| group1 | 776 / 1075856.58741676 | 776 / 24161239.65736498 | 776 / 68955135.07396042 |
| group2 | 480 / 113913.61949721041 | 480 / 2973370.637320133 | 480 / 349369.0475535463 |

## 联合矩阵

以下联合切分仍保留，作为旧 directed-neighbor 矩阵的结构诊断；它不是本次 V3 的
`E_joint` 资格结论。三组矩阵按相同的 left/right dual 和 coefficient convention 组合：

```math
E_{joint}=E_1+\operatorname{blockdiag}(E_0,E_2).
```

从 group1 的 lower-then-upper 矩阵切出四个明确 block：

```math
E_{joint}=\begin{bmatrix}
E_{LL} & E_{LU}\\
E_{UL} & E_{UU}
\end{bmatrix}.
```

`E_LU` 与 `E_UL` 不得默认置零。V3-1 必须同时报告四个 block 的 Frobenius norm、相对
norm、rank 和 hash，并保留 incoming/block-diagonal map 与 middle cross-interface response
的语义区别。

旧矩阵拼出的 structural `joint_projected_exact` 为 776×776、rank 776、condition
`80081760.2949406`；四 block 为：

| block | shape | Frobenius norm | relative norm | rank | SHA256 |
|---|---:|---:|---:|---:|---|
| LL | 296×296 | 1053759.949377419 | 0.999981218749935 | 296 | `a74495e8ba75e6dc05966fcaba0c5277569c4b6979211d0384db9907c8a48b75` |
| LU | 296×480 | 0.0 | 0.0 | 0 | `0d72237d289ccc4f4a6eb3e78b5c20e7f50da39b0856192100901993d2ce8e11` |
| UL | 480×296 | 0.0 | 0.0 | 0 | `0d72237d289ccc4f4a6eb3e78b5c20e7f50da39b0856192100901993d2ce8e11` |
| UU | 480×480 | 6458.401699644151 | 0.0061287966074270355 | 480 | `2c6b26d74c27eb27319d89fcf7824c24ab4dc2c58562c10ff4e55199fd5f6548` |

LU/UL 的零值是 packet 中实际重算出的 incoming projected-exact 结构诊断，不是 core
主动把 cross block 清零；但它也不能冒充 full middle Schur 的 cross block。独立
middle-Schur sampled response 另有非零 cross energy：lower→upper 最大
`0.6677254509073904`，upper→lower 最大 `0.14544366781366302`。二者不能互相冒充。

求解允许使用 complex SVD、rank-revealing QR 或直接 Petrov solve；禁止 normal equations。
不得创建 FE-sized dense interface matrix，也不得 allgather FE numeric 或复制完整 basis。

## 独立 tiny oracle 与 failure decomposition

focused fixture 必须是 complex、non-Hermitian、三分区 block-tridiagonal 系统，独立比较：

- 直接消去 interior 得到的 full interface Schur；
- `E_1 + blockdiag(E_0,E_2)` 的联合组装；
- 联合 reduced solve 后的 full residual；
- 省略 `LU/UL` cross block 的明确 negative control。

matrix/action relative error 与 full residual 目标均为 `<=1e-12`。另按 physical、modal、
complement、middle lower-to-upper、middle upper-to-lower 分组汇总 scalar-exact、
projected-exact、in-span、complement orthogonality 和 cross-interface energy ratio。
独立 tiny authority 实测 matrix、action、solution 和 full residual 的相对误差均 `<=1e-12`；
删除 LU/UL 的 negative control 明确失败。

本次分解（最大值）为：

| evidence group | count | scalar-exact | projected-exact / in-span | complement orthogonality | cross energy |
|---|---:|---:|---:|---:|---:|
| physical | 15 | 1.0221912938677724 | 1.020350476820021 | — | — |
| modal combination | 4 | 1.0349183911337543 | 2.4890293803065003e-08 |  — | — |
| complement | 4 | 1.0281892054707482 | 1.0281892054707484 | 5.446980708086963e-13 | — |
| middle lower→upper | 4 | not serialized | not serialized | — | 0.6677254509073904 |
| middle upper→lower | 4 | not serialized | not serialized | — | 0.14544366781366302 |

## V3-1 Gate 与停止条件

已通过的只是 packet identity/hash、三组 shape/rank/condition、旧 structural matrix 的
finite/shape/rank/hash、lower-then-upper ordering 以及 tiny independent oracle。scalar
joint 仍保留 finite/rank/condition 诊断，但不作为独立数值停止 Gate；`<=1e12` 的正式
condition Gate必须施加在真正的 projected-exact `E_joint` 上。由于
`local_middle_schur_evidence=false`，整体不是 V3-1 algebra evidence valid，而是
`COUPLED_PACKET_INFORMATION_INCOMPLETE`，不能分类为数值失败。

按 Review §8.5 的最小合法补强，优先在 producer 仍持有 oracle 与 basis 时，对 group1
全部 776 列计算并保存一个明确命名的
`projected_middle_group_schur = Y1^H S1 Z1` 小矩阵；不得重命名旧三个矩阵。它的 LL/UU
可与旧 group0/group2 directed-neighbor 矩阵做身份交叉核对，随后才可构造
`projected_middle_group_schur + old projected_exact_group1` 的联合代数。若 V3-2 还要求
consumer 直接持有 `Z`，则还需按冻结 lower/selected-upper authority、QEP=0 重建 `Z`，或
新增 owner-row Z shard；这属于第二个信息补强，当前不擅自改 schema、不重跑 producer。

## 验证

qualified activation 下：serial `test_308_task040_coupled_interface.py` 为 4 passed；
MPI2 与 MPI4 同一文件各 rank 均为 3 passed、1 skipped（immutable packet 只在 serial
读取）。既有 packet/consumer 回归为 20 passed。Ruff、format、compileall、Markdown
合同与 `git diff --check` 均通过。

V3-2 尚未启动，状态为 `pending_conditional_not_run`；augmented V3-1 通过后按 Review
决策树可连续进入，但本轮不写入 V3-2 代码或正式结果。

## augmented 补强结果

V3-1 按 Review §8.5 对 producer 做了唯一一次最小补强：只增加
`projected_middle_group_schur = Y1^H [oracle.apply_group(1)] Z1`，没有重命名或改变旧的
`projected_exact_group*` 语义。它补上了 middle local Schur 的 LU/UL 信息；以下 PASS
只属于 augmented packet，不回写旧 packet 的首次审计结论。

| 项目 | augmented 实测证据 |
|---|---|
| producer / checker source | `fa1720d8f137de81023cd45d6a43262d386e6521` / `9e79443ccf808372feb24160d89c13eb9f0ac4eb` |
| formal root / exit | `results/task040_v3_1_middle_schur_producer_mpi8_fa1720d8` / natural exit, rc=0 |
| 三个 formal SHA | manifest `f480189663ef293ec4f809818e322186d75a205f725a3aa35dc12c2d24aad209`；run `b44700081d48c96f4380e3111cd5f25ff57dfc64f0fab24afbd7a8a710f2bc7a`；watchdog `cb61e59830443c2169bd388af7710de2af95d5e2ec59d128c207c1bbd05dbf03` |
| checker artifact | `checker_recomputed_augmented_9e79443c.json`，SHA `ddace4647e2dddefc72fc92cb2af4cf3f1a7c22b3cc258f064bf6d17b3860267`，JSON 可序列化，rc=0 |
| wall / RSS / swap | `1344.65377977991 s` / `30,522,519,552 B = 28.426311493 GiB` / `0 B` |
| factor lifecycle | ready/projected `3`（同一组三个 group factors 的两种视图）→ cleanup `0`；simultaneous max `3` |
| packet flags | `basis_global_replicated=false`、`fe_numeric_allgather=false`、exact/full/global/nested `0`、QEP `0`、PDE `not_run` |
| augmented matrix | shape `776×776`，rank `776`，condition `205176529.82325`，σmax `251698.74850828125`，σmin `0.0012267423994601525`；content SHA `f6f2712e7ed4c8c8fb0fd1764076f7218c1548bf62020abfc6f8a6ddd8998f52`；file SHA `201d69133ab9004454ddb522903695a87d4f939bc75c8a3453c1cb98766bb2a4` |
| true joint exact | `projected_middle_group_schur + projected_exact_group1`；rank `776`，condition `72530856.63880321`，σmax `282171.4484566674`，σmin `0.0038903642054285183`，hash `ed7c973c92ff4704a687c9d61032930bb458076e552892c988990cf893e6e035` |
| LL / LU / UL / UU | shapes `296×296 / 296×480 / 480×296 / 480×480`；ranks `296 / 296 / 296 / 480`；Frobenius norms `1052857.3530587784 / 36531.317719106126 / 9728.7850526928 / 6371.749206867203`；relative norms `0.999337702197316 / 0.03467432981456654 / 0.00923424400417028 / 0.006047855574042572` |
| block hashes | LL `4be30638ca6ca7e6d6980ef45fa53250755d76961b336b60360f4b06a187dbe0`；LU `1033fcc0d2d5ff2b0a3a018870f839b6e131d39a01de4d205fd3d496fc97db9e`；UL `969e15b2d61f185bb276bab40904235343f118ef0a4d1aef2a6b05c61c048972`；UU `3935fc7fbd064d333dfdc53fb738076a0273b9c2529274d648e11777369c6d09` |
| LL / UU identity | `3.690489479705948e-14` / `8.947677926466937e-15` |
| middle cross sampled | 8 reports；lower→upper `0.6677254509073904`，upper→lower `0.14544366781366302` |
| independent classification | `COUPLED_INTERFACE_ALGEBRA_EVIDENCE_VALID`；全部 augmented checker checks 为真 |

最终验证：serial `test_308_task040_coupled_interface.py` 为 `6 passed`；MPI2、MPI4
分别为 `3 passed, 3 skipped`；Ruff、format、compileall、`git diff --check` 均通过。
