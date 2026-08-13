# Task39 0.7 nm 组件级可行性审计

本页只做组件容量和架构审计，不创建网格、不组装矩阵，也不启动完整 0.7 nm PDE。`static condensation`（静态凝聚）先消去单元内部未知量，减少全局系统；它能降低主系统规模，但不能替代材料输入或外部通道存储。`W` 是外部 DtN 通道到有限元迹空间的耦合矩阵，`K` 是通道之间的稠密矩阵；`PSS/USS` 在本审计中没有被伪造为 0.7 nm 实测值。

## 身份与空气侧唯一可运行组件

| 项目 | 结果 |
|---|---|
| 5 nm 输入 | `input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat` |
| 5 nm physical SHA | `db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a` |
| 0.7 nm 材料 | `0P7NM_MATERIAL_INPUT_INCOMPLETE` |
| 空气侧通道 | `16030`；空间 `(m,n)` `8015`；S/P `{'top': {'S': 8015, 'P': 8015}}` |
| key SHA | `28cf61cebf8656b207a5128cc98dda4e0bfcaad4cdb1fe1b784b33bcacd14e4d` |
| Rayleigh warning / near-cutoff / nonpropagating | `0 / not_separately_defined_by_authority / 0` |
| 完整 PDE launch | 禁止；`0P7NM_MATERIAL_INPUT_INCOMPLETE` |

空气侧枚举实际复用了 `task039_air_side_external_mode_inventory`；substrate 侧没有被复制为空气，保持 pending。

## FE 场景

```math
h_{0.7,A} = h_{5,\mathrm{qualified}}\,\frac{0.7}{5.0}.
```

场景 A 为 `not_instantiated/insufficient_fit_points`：T7/T8 未运行，当前没有 5 nm accuracy-qualified 的 h 点，不能用 h10 冒充拟合点。场景 B 只有一个 h10 测点，下面是工程外推，不是收敛结论。

| p6/h1 派生量 | 数值/状态 |
|---|---:|
| cells / full FE DoF | 252000 / 173802000 |
| global active trace | 51192000（h^-3） |
| matrix NNZ | 43283050000（derived） |
| factor NNZ range | 217041864000 – 2170418640000 |
| factor values-only bytes range | 3234.18 – 32341.76 GiB |
| MPI1 / MPI8 process-tree | not_established / not_established |
| matrix-free cache/action | not_established |

```math
N_{FE}\propto h^{-3},\qquad n_{\Gamma,\mathrm{endcap}}\propto h^{-2},\qquad N_{factor,upper}\propto N_{FE}^{4/3}.
```

## External DtN/Woodbury容量

| 组件 | trace rows | 单 air-side W | K | K-LU |
|---|---:|---:|---:|---:|
| Full3D/global hypothetical | 51192000 | 12228.01 GiB | 3.83 GiB | 3.83–7.66 GiB |
| Hybrid per-air-side endcap | 842400 | 201.22 GiB | 3.83 GiB | 3.83–7.66 GiB |

Hybrid 双端 W 的 authority 为 `not_established/pending_substrate_material`。假设 substrate
与 air 相同的 conditional example 为 `432117504000`
bytes（`402.44` GiB）；它不是 authority、无条件
lower bound，也不能替代缺失的 substrate material。16030-channel K factor 相对于
604-channel dense K factor 的 O(N^3) engineering ratio 为
`18,693x`。K factor 的绝对秒数为
`not_established`，原因是 no isolated measured 604-channel K-factor timing baseline; O(N^3) ratio alone cannot determine seconds。

Full3D/global 的 W 是全局 hypothetical capacity，不是 Hybrid endcap authority。已知 top-air endcap 的 W 是 `201.22` GiB；把已定义的 1–2 份 K-LU 计入 resident component 后，known air-side endcap 的 `205.049–208.878` GiB range 与 effective hard stop `205.259` GiB 比较：lower 仅余 `0.210` GiB，upper 已超限。完整 two-endcap status 仍为 `pending_substrate_material`；由于 substrate、indices、pivot、workspace 和其他 solver 对象尚未计入，不能给出低于 hard stop 的保守上界，external redesign 分类成立。K-LU 是 complex128 value-only 组件估计，不含 indices、pivot 或 workspace。

Full3D/global 的 W 超过 256 GiB 仅作为说明；Hybrid external redesign 的判定来自上述 endcap `W + K-LU` resident range，而不是把 global W 冒充 Hybrid 组件。这些仍是组件推导，不是完整 PDE 实测。

## Internal modal / Schur容量

13.5 nm accepted evidence 使用 M120；5 nm 的 `M_robust_h10` 未建立，M960 只是在 canonical trace 失败前得到的未通过下界，不能当作 0.7 nm 预测。以 13.5 nm M120 为起点的两种保守 envelope 如下：

| 锚点/模型 | M estimate | 2M | basis GiB | coupling GiB | dense Schur | dense LU | O(M^3) relative to seed |
|---|---:|---:|---:|---:|---:|---:|---:|
| 13.5 M120 / 1/lambda | 2315 | 4630 | 55.15 | 13.42 | 0.32 GiB | 0.64 GiB | 7180x |
| 13.5 M120 / 1/lambda^2 | 44633 | 89266 | 1063.34 | 258.65 | 118.74 GiB | 237.48 GiB | 51454635x |
| 5 M960 lower bound / 1/lambda | 6858 | 13716 | 163.38 | 39.74 | 2.80 GiB | 5.61 GiB | 365x |
| 5 M960 lower bound / 1/lambda^2 | 48980 | 97960 | 1166.90 | 283.84 | 142.99 GiB | 285.99 GiB | 132814x |

Basis/coupling 列是以 T5 M480/h10 measured per-M bytes 为锚、再乘 M 比例与 h1 surface scale=100 的 engineering estimates，不是 0.7 nm 实测。

这些是 conservative model estimates；当前 augmented direct 路径没有实测 modal Schur condition/LU。quadratic envelope 的 dense LU 已越过 220 GiB，因此按保守模型需要 internal modal Schur redesign。

## 收敛风险与最终边界

13.5 nm accepted iterative M120 的三个 phi case 为 1771–3945 iterations（逐 case 保留在 record）；T4 5 nm Full3D iterative 在 4000 iterations 后 residual 约 0.155，T6 Hybrid iterative 未运行。因此 0.7 nm iteration range 为 `unbounded/not_established`，不能声称已验证。

最终分类：`0P7NM_MATERIAL_INPUT_INCOMPLETE`、`0P7NM_FE_FACTOR_OR_CACHE_EXCEEDS_256GIB_BUDGET`、`0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN`、`0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN`、`0P7NM_CONVERGENCE_RISK_UNRESOLVED`。`CURRENT_ARCHITECTURE_PLAUSIBLE` 不适用；T6–T8 仍 not_run/blocked，T9 为 component-only，不能升级为 production qualification。

证据只绑定 repo-relative compact records；ignored raw、mesh、matrix、factor 和完整 modal/W/K 数组均未读取或提交。
