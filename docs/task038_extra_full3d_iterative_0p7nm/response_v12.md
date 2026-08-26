# Task038-extra Review V12：R12 response

## 结论先行

截至 R12，V12 没有选出可进入正式 p6/h10 求解的 hierarchy。Route A 的局部谱事实通过但 global adjoint Gate 失败；Route B v2 的结构与 setup 事实通过，但 positive random 在 7000 步由用户受控停止；C1 的跨 MPI physical-canonical identity 失败；C2 的唯一 MPI1 nested smoke 在 `h3star→h1star` work Gate 失败。因此：

| 项目 | 最终状态 | 含义 |
|---|---|---|
| `selected_hierarchy` | `NONE` | 没有路线获得 V12 正式求解资格 |
| `nested_lor_edge_hmg_v1` | `CLOSED` | C2 hard Gate 失败，停止该多层 PC 数值实现 |
| p6 positive 四源 | `not_run_by_gate`；random 另有受控停止证据 | 没有完整四源 true-residual qualification |
| p6 physical / official physics | `not_run_by_gate` | 没有 E/H、R/T/A、`A_volume` 或 channel 结果 |
| 0.7 nm / 2 TiB | `not_run_by_gate` | 没有可用于容量外推的 selected hierarchy |

旧负结果和通过结果均保持原分类：V11 S5 的 6→3 exact-energy negative、V10 Q0 500-step negative、foundation-E 3020-step PASS、old SLEPc nonconvergence、HX/PCGAMG closure，以及 ba40358 invalid-probe archive 均未修改或重分类。

## 身份与证据边界

本 response 对应的执行分支为 `codex/20260820-task38-extra-full3d-iterative-0p7nm`，C2.1c 实际执行 SHA 为 `f7d0ac41678b2d18be6c05c1eebfde87adcf9521`。C2 只做 `p6-h50`、MPI1 的小型 owner/topology diagnostic，不是 p6/h10 formal；没有启动 MPI2、KSP、V-cycle、PDE 或 official physics。

主要证据入口：

- [路线选择与阶段边界](outcomes/interlevel_route_selection_v1.md)
- [C2 MPI1 compact diagnostic](outcomes/records/nested_lor_edge_hmg_c2_mpi1_diagnostic_v1.json)，SHA256 `62a7bbce12dceb77254bae2ead9c8b3ddf8f9dc0d48b5349b5147f7434ecdf79`
- [下一 PC 架构比较](outcomes/next_pc_architecture_after_v12.md)
- [p6 positive 未运行边界](outcomes/p6_positive_selected_hierarchy_v1.md)
- [p6 physical 未运行边界](outcomes/p6_physical_selected_hierarchy_v1.md)
- [p6 MPI2 未运行边界](outcomes/p6_mpi2_selected_hierarchy_v1.md)
- [0.7 nm / 2 TiB 未运行边界](outcomes/feasibility_0p7nm_2tib_v4.md)

两份临时 capture 仍在 `/tmp/task038_c2_1c.UVCkSF/`，仅覆盖第一对和 MPI1，不能作为跨 MPI authority：`primal_mpi1.json` 为 9,278,943 B、SHA256 `bd26e754e68872f36e6e22bffcb523fe17e88e6b9d30672da94318016046d8ec`；`dual_mpi1.json` 为 1,059,538 B、SHA256 `060b097322d0e7d5c8b9d4c5f9eea4a8ba72ec140e2b909d1a5f68c68652c114`。原始 stdout 没有单独持久化，这是本次诊断的证据限制。

## 1. Route A 的各材料 class spectrum

Route A 使用正式 source SHA `083869115abe398288360b034bb9762c90838437`，有 10 个 exact material/geometry classes。第一次 checker 的 shape-contract invalid 原样保留；修正 shape authority 后的 checker 结论是 `CLOSED_BY_INTERLEVEL_SPECTRAL_GATE`。

每个 class 的局部谱事实如下；`class_digest` 只列前 12 个字符，完整身份保存在不可变 raw checker 中：

| class | role/tag | lambda min | lambda max | condition |
|---|---|---:|---:|---:|
| `2307efcf1d76` | air/1 | 0.4966032124443659 | 2.734092780434856 | 5.5055881877549355 |
| `252de3492a11` | grating/3 | 0.49658579468299535 | 2.734093577663523 | 5.505782901842534 |
| `2e4ca5dfea36` | air/1 | 0.4966032124443668 | 2.7340927804348563 | 5.505588187754927 |
| `39ce19a3720d` | grating/3 | 0.4965857946829977 | 2.73409357766352 | 5.505782901842502 |
| `652795fe37f1` | air/1 | 0.496582162486177 | 2.7340937353036567 | 5.505823490749658 |
| `7543fac90749` | substrate/2 | 0.4965857946829977 | 2.73409357766352 | 5.505782901842502 |
| `7fedc6f37710` | substrate/2 | 0.4966067778985919 | 2.7340926254004687 | 5.505548347466928 |
| `9ffe997ef47c` | air/1 | 0.49658216248617776 | 2.7340937353036554 | 5.505823490749647 |
| `a3ba80a678f0` | substrate/2 | 0.4966067778985908 | 2.734092625400468 | 5.505548347466939 |
| `a9e1a4133aaf` | substrate/2 | 0.49658579468299535 | 2.734093577663523 | 5.505782901842534 |

这 10 个 class 的 rank、Hermitian/SPD、endpoint residual 和 class-local facts 均通过其局部合同；全局 probe 的唯一失败是 gradient adjoint `2.8964367576123248e-11 > 1e-12`。因此局部 class spectrum 通过不等于 Route A 整体通过。六个 global probe 的 `q` 范围为 `1.0609675384150175–1.9199258121202312`，但这不能覆盖 global adjoint Gate。

## 2. 是否进入 Route B，以及 6→2 结果

进入了 Route B。R3 v2 的 candidate 是 `lor_edge_geometric_mg_6_2_1_nested_v1`，levels 为 `6→2→1`，source SHA `91e27ebb4bdcf9de302c12cc5a19ae8eaa78b8c1`，独立 checker 为 `STRUCTURALLY_QUALIFIED`。

| 事实 | 结果 |
|---|---:|
| exact material classes | 10/10；rank=54；覆盖 air/substrate/grating |
| lambda min / max | `0.9999999999999957–0.9999999999999972` / `1.0000000000000022–1.0000000000000036` |
| condition | `1.0000000000000056–1.000000000000007` |
| endpoint residual 最大值 | `3.899736900063366e-15` |
| nested energy relative | `3.432582537434375e-16–4.326247611440155e-16` |
| 6→2 local map | edge `882×54`, NNZ `2178`；node `343×27`，NNZ `1331` |
| 2→1 local map | edge `54×12`，NNZ `96`；node `27×8`，NNZ `216` |
| 六 probe q | `0.9999999999999725–1.000000000000014` |
| 六 probe 最大 adjoint / energy | `2.1526744277731597e-13` / `2.7628585938262692e-14` |
| owner probe adjoint / linearity / repeat | `2.625232868301171e-18` / `1.2732475304017576e-16` / `0` |

因此 Route B 通过的是 structural/interlevel setup 边界，不是 positive solver pass。R4.2 setup 的 process-tree peak 为 `1,005,158,400 B`，R4.3 random 到 7000 步受控停止；这些事实没有被改写成完整 positive 结论。

## 3. Route C、C1 与 C2 的关闭范围

Route C 的两个实际信号不同：

| 路线 | 正信号 | 负信号与结论 |
|---|---|---|
| C1 same-mesh H(curl) | local transfer、owner/MPC algebra 通过 | physical-canonical MPI1/MPI2 coefficient relative 为 `0.10049859821442367`（primal）和 `0.004662851981572301`（dual），均大于 `1e-11`；`CLOSED_BY_MPI_CANONICAL_IDENTITY_GATE` |
| C2 nested LOR-edge HMG | C2.0 local `h6→h3star→h1star` transfer、各 level bridge、`h6→h3star` work 通过 | `h3star→h1star` owned-packet work `0.018392534459166617 > 1e-11`，raw PETSc work `0.048176780898148176`；`CLOSED` |

C2.1c 的三个 level bridge 为：

| level | primal owner roundtrip | dual roundtrip | raw/owner work |
|---|---:|---:|---:|
| h6 | 0 | 0 | `3.54641052899015e-16` |
| h3star | 0 | 0 | `4.096217945654923e-15` |
| h1star | 0 | 0 | `2.671632823616697e-16` |

第一对 `h6→h3star` 的 owned-packet/raw PETSc work 分别为 `2.176782822433302e-15` 和 `6.2401107576421675e-15`；第二对才是首个失败子映射。现有事实不能唯一判定 failure 属于 incidence、orientation、phase、ordering 或 dual-route 中某一条 production 公式，因此没有猜修或放宽阈值。`h1star` raw primal representation 的 `0.19459042014393269` 只反映 constrained slave storage 表示差异；owner packet roundtrip 为 0，不能把它误报成另一个 Gate。

## 4. 最终 selected hierarchy

`selected_hierarchy=NONE`。Route B v2 的 `STRUCTURALLY_QUALIFIED` 只授权后续 setup/positive 审核；random 未完成，C1/C2 已关闭，所以没有 hierarchy 可进入 p6 physical 或 official physics。

## 5. p6 positive 四类 source 的 true-residual history

只有 Route-B `random` 实际进入了 positive worker；它在 checkpoint 7000 后由用户受控停止，不是自然退出，也不是 10000-step numerical Gate failure：

| iteration | explicit true residual |
|---:|---:|
| 500 | 0.07563116734336381 |
| 1000 | 0.04385139771562173 |
| 1500 | 0.02947787626179562 |
| 2000 | 0.022688540727309393 |
| 2500 | 0.018703685886528456 |
| 3000 | 0.015877743518052306 |
| 3500 | 0.013920666485138304 |
| 4000 | 0.012445206849355522 |
| 4500 | 0.011272012163803188 |
| 5000 | 0.010397067842914887 |
| 5500 | 0.009664959033694237 |
| 6000 | 0.009046801573164462 |
| 6500 | 0.008556474837834631 |
| 7000 | 0.00814181052296021 |

该案 classification 是 `USER_DIRECTED_CONTROLLED_STOP_AT_7000 / performance trend rejected`，10000-step Gate 为 `incomplete_not_evaluated`。gradient、curl、checkerboard 没有运行，因而没有 residual history，状态为 `not_run_by_gate`。

## 6. p6 physical 与 bounded Floquet correction

p6/h10 physical Maxwell 没有运行，状态为 `not_run_by_gate`。因此没有使用 bounded Floquet correction，也没有产生 physical residual、recovery field 或 official physics。C2 的 `h3star` smoke 也不是 physical workflow。

## 7. complete workflow 的峰值、swap、release 与 recovery

没有 complete selected workflow。已测但范围不同的资源事实如下：

| 阶段 | 资源事实 | 生命周期边界 |
|---|---:|---|
| R4.2 setup | process-tree peak `1,005,158,400 B`；retained 同值；swap `0 B` | 10 次 apply、factor setup/solve 闭合；不是 solver/PDE |
| R4.3 random | process-tree peak `1,005,531,136 B`；swap `0 B`；103379 samples | 用户在 7000 步终止；不是 natural exit，未到 release/record closeout |
| C2.1c diagnostic | rank-worker max RSS `486,473,728 B`；rank swap `0 B` | 仅 MPI1 test scope，不是完整 process-tree qualification |

S1/S2/S4/S5 的阶段性资源事实继续保存在原 evidence。由于没有 selected positive/physical workflow，没有完整 release、recovery 或 R10–R12 solver lifecycle 可报告；C2 R12 只做证据 closeout。

## 8. official E/H、R/T/A、A_volume 与 12+12 channels

均为 `not_run_by_gate`。本 V12 没有生成 p6 physical Maxwell 的 E/H、R/T/A、`A_volume` 或 12+12 channel observables；不能用 foundation-E、S4 small oracle、Route B setup 或 C2 local smoke 冒充这些物理结果。

## 9. 当前最粗层与 development direct oracle

没有当前 selected hierarchy，因此不存在“当前最粗层”的 production coarse solver。R4.2 setup 中的 level-1 exact sparse MUMPS factor 是 development/setup oracle，用来审计 factor setup、solve count 和资源组成；它不等于 production coarse solver，也没有被接入 ordinary default。C2 在进入该边界前已关闭。

## 10. 0.7 nm / 2 TiB 还剩的明确 blocker

| blocker | 当前证据 |
|---|---|
| 没有 qualified selected hierarchy | Route A、C1、C2 已分别关闭；Route B 只有 structural/setup 资格 |
| nested owner algebra 尚未闭合 | `h3star→h1star` owned-packet work `0.018392534459166617 > 1e-11` |
| positive convergence 尚未完成 | random 仅到 7000 步，explicit residual `0.00814181052296021`；另外三源未运行 |
| physical/global-wave 与 official physics 未验证 | p6 physical、recovery、R/T/A、channels 均未运行 |
| h5 与 2 TiB 资源口径未建立 | 没有 selected hierarchy 和 p6 physical 前置事实，不能外推 DoF、NNZ、peak 或 capacity |

下一步若继续，只能先从 [C2 之后的架构比较](outcomes/next_pc_architecture_after_v12.md)中选择一条新的、可审计的 H(curl) coarse architecture，再从小型 local/MPI true-residual evidence 开始。该文只比较 BDDC/FETI-DP、GenEO/adaptive domain decomposition 和 matrix-free p-h 加分布式 algebraic coarse correction，不代表任何路线已实现或已通过。

## 历史与 selective-merge 边界

V12 保留以下历史边界：V11 S5 的 `6→3 energy relative = 0.04115402900674629 > 1e-9`；C1 的 cross-MPI identity negative；C2 的 MPI1 second-pair negative；以及所有此前 accepted structural/setup/oracle facts。C2 local transfer core只作为 `research-only retained local oracle/infrastructure`；C2 owner runtime/test 和本 compact diagnostic 属于 `research-only / do-not-merge candidate evidence`。`ordinary default`、`master` 和生产多层 PC 均未改变。

本次 R12 轻量检查范围为严格 JSON/有限数解析、Markdown 链接与空白检查、test324+test325 focused、test326 默认 skip、compileall 和 diff-check；没有运行 full pytest、MPI 数据采集、p6/h10 formal、KSP、PDE 或 official physics。
