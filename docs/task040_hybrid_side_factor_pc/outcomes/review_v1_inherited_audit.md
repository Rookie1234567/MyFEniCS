# Task40 Review V1 inherited audit

本页是 V1-0 的只读继承审计。它把已完成的 T40-3 固定标量阻抗结果与 Review V1 的后续决策树分开；V1-1 至 V1-8 在本页生成时均未运行。

## 身份与可复核边界

| 项目 | 绑定值 |
|---|---|
| branch | `codex/20260822-task40-hybrid-side-factor-pc` |
| audit HEAD / upstream | `fe93e0165a9bdce3412812e5b0044f54a198c142` / same |
| ahead/behind | `0/0` |
| worktree | clean；无本轮 tracked 修改、无 nonignored artifact |
| Review V1 commit | `fe93e0165a9bdce3412812e5b0044f54a198c142` |
| Review V1 file SHA256 | `76b9695e0f11f4608c53f8f2e05c1b2c735cfe9b2ef92704439c90d403afa65d` |
| reviewed numerical source SHA | `483275dcdfa65fbc578bbee510878f2d065e2429` |
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected packet manifest | `results/task039_v4_h4_m480_shared_packet_eaad0f94/manifest.json` |
| selected packet manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| external mode keys | count `600`; SHA256 `ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a` |
| exact-response spool catalog | `results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output`; SHA256 `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| T40-3 raw root | `results/task040_level_a_bare_f_mpi8_483275dc` |
| T40-3 compact record SHA256 | `0dad8a259709efa3c147cb7248e5436013fb62d54ba31e6449612e90bc10bdce` |
| raw watchdog summary SHA256 | `6fd00ae71871f8eaf0db98376607cb0d67c48067a8533bd555e687f0c6b9d43e` |
| raw worker summary SHA256 | `3753a64043cc105e947f9f5b756276f00b383e75602fe5c636811a809aa368bc` |
| raw marker SHA256 | `a56985fa156964d80ae1bf669a7f805799f15b2d1509123bd663cf75703148ae` |
| raw memory-stage SHA256 | `d46d9bc3ec323c3ad6eb97e09e6e1e8357ad9cfc3817cb3d2405dd4c2e8bf8d2` |
| raw process-sample SHA256 | `94d08cc3633a293f4ab28e1ed8e0e6fa65f6e8bccf7489b26d6e5712af3fc72d` |

冻结模型为 5 nm、1° grazing、phi=0、S、p6h4、M480、MPI8、threads=1、complex128；QEP、M、DtN、global action 和 physical parameters 均未改变。

## 继承的标量阻抗身份

T40-3 使用已有 `src.solvers.dtn_port_3d::_zero_order_local_robin_forms` 的约定：

```math
\beta = k_0\,n_{substrate},\qquad q=-i\beta.
```

raw 中实测 `beta=[1.2490577109579148, 0.005471156202149664]`，`q=[0.005471156202149664, -1.2490577109579148]`。两个 bottom 人工界面位于 `z=-3.333333333333333` 与 `z=4.0`；T40-3 两侧都使用同一个 substrate-side scalar `q`，outward normal signs 为 `[+1,-1]`，法向只进入 traction/coupling。这里不是后续 top route 的 `n_air` 身份。

旧结果的唯一正式分类是：

`FIXED_NORMAL_INCIDENCE_SCALAR_IMPEDANCE_TRANSMISSION_FAIL`

五个非零 source 的 rho 为 `16.512689191540417`、`14.24201480051629`、`22.945123935386228`、`28.316064601533686`、`25.70701839061571`，worst 为 `28.316064601533686`，mandatory `<1` 失败。physical zero source 仍为 zero-map。实现、identity、finite、linearity、repeat、RP、interface mass/support、factor inventory 和 cleanup 均通过；三个 cross-section oracle factors 为 `3 -> 0`，full-side/global/nested 均为 `0`，swap 为 `0`。

峰值为 `30422945792 B = 28.333576202392578 GiB`，只代表 T40-3 bottom bare-F component；完整 workflow 继承基线仍为 direct `93.377006531 GiB`、exact-side iterative `80.025856018 GiB`。该 component 峰值不能声明新的完整 workflow saving tier。

## V1 阶段状态

| 阶段 | 状态 | 继承/下一步 |
|---|---|---|
| V1-0 | completed, docs-only | 本页及三个相邻 planned pages |
| V1-1 | controlled_numerical_negative | 固定 scalar screen 已完成；五个 `r16 >= 0.9`，32 not run |
| V1-2 | resource_stop_before_qualification | exact oracle `3 -> 0`；45 GiB hard stop，probe 未序列化 |
| V1-3 | setup_started_but_not_ready | projected-exact setup started; no ready/checkpoint; numerical capacity `NOT_EVALUATED` |
| V1-4 | not_run | analytic mode-aware transmission |
| V1-5 | not_run | conditional bounded-patch Level B |
| V1-6 | not_run | conditional bottom/top/both/full Hybrid |
| V1-7 | not_run | conditional h3/p6 scaling probe |
| V1-8 | prepared_pending_review | outcomes、独立 evidence record、`response_v2.md` 已生成 |

T40-3 的负结果不能外推为所有 impedance Schwarz、FGMRES、mode-aware transmission、bounded patch、coarse information 或 0.7 nm infeasible。V1-1 已实际完成但为 directional negative；V1-2 随后因 resource hard stop 未完成 numerical qualification，后续依赖阶段因此保持未运行。

## 禁止路线

本继承审计及 V1 扩展均禁止：beta/sign/damping、mode count、sweep/order/partition、restart、ILU/BLR/drop 扫描；second-order/rational impedance；自动 coarse；dynamic DtN、QEP/M/global operator 或 ordinary default 改动；direct/exact-side producer 重跑；Task39 response packet 重跑；Full3D、0.7 nm PDE、并发 heavy；以及把未通过 scalar transmission 的结果直接升级为 bounded patch、top、full Hybrid 或生产 PC 资格。

所有后续阶段必须保持一个 heavy、qualified ABI、MPI8、threads=1、swap=0、6 小时上限；任何 identity/ABI/resource/nonfinite 或阶段 Gate 失败都保留 raw 并停止依赖链，不翻符号、不调参、不重跑。

## V1-8 收口修正

V1-2 在冻结 MPI8 路线上正式尝试一次。运行到达 exact-oracle ready/release
（`factor_count=3` 后为 `0`），随后 watchdog 在 `48,380,153,856 B = 45.05752944946289 GiB`
停止进程组；没有 V1-2 probe serialization 或 V1-3 checkpoint。V1-2 为
`not_qualified_due_resource_stop`，不是数值负结果。V1-3 setup 已开始但未到 ready，状态为
`setup_started_but_not_ready`、numerical capacity 为 `NOT_EVALUATED`，不能归类为
`THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT`。V1-4 至 V1-7、Level B、top 和 full
Hybrid 为 `not_run_by_gate`。前两个 root 仍保留为实现失败，未被覆盖。
