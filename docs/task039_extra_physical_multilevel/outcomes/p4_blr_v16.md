# p4 BLR V16：三 RHS 控制与内存收益边界

## 1. 当前状态

直接求解会保存消元产生的矩阵块；BLR（block low-rank，块低秩）用较少数据近似其中一部分，尝试节省因子内存，但代价是回代误差需要逐项检查。它仍保留全局消元树和增长型 front，不等于无因子的迭代预条件器。本报告只评价一个固定 `physical_p4_blr_bal_h_v16` 配置：宿主模型是 p6/h10，但正式批只分解并回代 p4 的 `53164` 行增广矩阵，没有 p6 outer solve，因此不把 p4 控制通过提升为完整 p6 solver。

| 项目 | 正式结论 | 数据身份 / 证据 |
|---|---|---|
| S2 control | `S2_BLR_CONTROL_PASS` | measured；独立 checker 从 raw packet/resources/factor fields 重算 |
| 三 RHS 质量 | 3/3 通过本轮质量筛选 | measured；每个 RHS 一次 MatSolve，无 refinement |
| 内存收益 | `STRONG_BUT_INSUFFICIENT_MEMORY_GAIN` | measured；`R_peak=R_live=0.9700174654134085`，未达 S3 线 |
| S3 original / S4 notch | `not_run` | 条件未触发，不能写成失败或通过 |
| official Full3D fields/power | `not_run` | 没有 p6 outer true residual、E/H、R/T/A、`A_volume`、80-mode或守恒结果 |
| ordinary default / master | unchanged / not approved | opt-in research evidence only |

## 2. 统一身份

| 项目 | 值 |
|---|---|
| source / base | `24bd767e6b0d158ac20deb360a135f10c0611ede` / `972393f41e1cc14af87022d2997ddc5936c0f4e4` |
| model | 13.5 nm fixed、Full3D、p6/h10、252 cells、MPI1、80 DtN modes、complex128/int32；正式批只做 p4 `53164` 行增广控制，无 p6 outer solve |
| matrix | p4 FE rows `53084`，port rows `80`，augmented rows `53164`，allocated/preallocated NNZ `24730144` |
| formal run | `results/euv_grazing1_phi0/task39extra_v16_s2_blr_control__full3d_iterative__mpi1__Mna/20260913T163912.716491Z` |
| physical / mode SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` / `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| MUMPS | linked library/header/package/manual identify 5.6.2；no ABI upgrade |

S2 的三个 reviewed RHS 是 `A2R160_BAL_H_p4_01`、`A2R160_BAL_H_p4_02`、`LIGHT448_BAL_H_p4_09`。输入、reference、g-array、packet NPZ 与 summary 均有 hash binding；raw evidence 的绝对路径和 SHA 由 compact 记录。

## 3. S5 四问表

| 问题 | 实测回答 | 解释 |
|---|---|---|
| 实际压缩 | native entries `INFOG9/35=53040280`，exact `INFOG29=53417584`；派生比 `0.992936707882558`，约少 `0.706%` | `INFOG36/37=1405 MB` 是 symbolic BLR字段；可选 wrapper 字段为 `null`，但原生条目比已实测，不能从默认 `ICNTL(38)=600`推断 |
| 因子/工作区 | allocated upper `1693000000` 对 `2343000000 B`；used upper `1420000000` 对 `1382000000 B`；workspace 两边 `17825792 B` | allocated 降低约27.7%，但 used 增加；对象账与 process-tree 仍需独立看 |
| 完整内存 | BLR RSS peak `2741243904 B`，exact `2825973760 B`；`R_peak=R_live=0.9700174654134085` | 只有约3.0%完整峰值下降，不满足 `R_peak<=0.90` 或 `R_live<=0.80 and R_peak<=1.05` |
| 有用纠错 | rho=`0.012747787228447355/0.0007166869050548434/0.01767784455927856`；L2=`0.0004689413782647275/0.0006381970572039616/0.0005184603039686529`；curl=`0.00046501472893071427/0.000633006283574765/0.0005142289126743576` | 三 RHS 全过质量线；只说明裸 p4 回代方向有用，不说明 p6 PC 能收敛 |
| 完整三维 | original、notch、非可分均 `not_run` | 未触发 S3，不启动后续 PDE |

## 4. 三 RHS 和控制证据

| RHS | native identity relative | one-solve | controls after solve | field gates |
|---|---:|---:|---|---|
| 01 | `8.297931175453582e-17` | `1` | `ICNTL(10)=0`, `ICNTL(35)=2`, `CNTL(7)=1e-5` | pass |
| 02 | `2.7398496982251096e-18` | `1` | same | pass |
| 09 | `9.818805809041391e-17` | `1` | same | pass |

请求控制在 symbolic 前设置并读回：`ICNTL(35)=2`、`CNTL(7)=1e-5`、`ICNTL(10)=0`、`ICNTL(37)=0`，并保持 `ICNTL(22/31/32)=0`。post-symbolic/numeric 还读回排序/缩放/主元字段 `ICNTL(6/7/8/14/18/28/29)=7/7/77/20/0/1/0`、`CNTL(1/3/4)=0.01/0/-1`；`ICNTL(23)=3127 MB` 是 symbolic sizing 后按 `max(1558,1558,1405,1405)` MB 加 padding、沿用 V11/Q1 配额设置的后端上限。默认 `ICNTL(36)=0`、`ICNTL(38)=600` 被记录；`ICNTL(39)` 与 `ICNTL(49)` 的 public getter unsupported，TRACE bundle 没有展开新的 49 调查，也未改变 49 策略。MUMPS 5.6.2 没有本批可用的 adaptive precision storage control，故保留 `complex128`。native residual identity 的报告方向是 `g-A4*c=e_top-B*H^{-1}*e_port`，不是后端 projected residual。

## 5. 资源与时间

| 指标 | exact Q1 baseline | BLR S2 | 备注 |
|---|---:|---:|---|
| full RSS peak | `2825973760 B` | `2741243904 B` | complete parent tree |
| factor-live RSS peak | `2825973760 B` | `2741243904 B` | matrix/factor retained |
| full PSS peak | `2795549696 B` | `2710780928 B` | all samples readable |
| resident inventory peak | `2906619390 B` | `2256619390 B` | independent object accounting |
| workspace peak | `17825792 B` | `17825792 B` | no reduction |
| job swap / global delta | `0 B` / `0,0 pages` | `0 B` / `0,0 pages` | process-tree scope; descendants cleared |

旧 Q1 的三 RHS elapsed 是包含 MatSolve 与 original/augmented residual checks、但不包含 field error/field metric evaluation 的 full-call 口径；BLR 纯 MatSolve `0.078368256/0.086713411/0.078177036 s` 不能单独与它形成加速倍数。BLR 每 RHS 完整 elapsed 为 `5.799002369/5.728811806/5.719995665 s`，其中 field metric 约4.7 s，另列 native evaluation 与 packet save。`rho` 是原方程剩余不平衡相对输入大小的比例，field L2 是整体电场相对误差，scaled-curl 是空间变化相对误差，三者均为 `0` 最好。

phase audit 从 parent monotonic phase boundary 派生：setup `37.088510941 s`、assembly/compile/pattern/augmentation `494.414024999 s`、factor `20.378098889 s`、三个 solve 合计 `2.987610083 s`、三个 evaluation 合计 `14.321126185 s`、cleanup `1.382956234 s`。phase-derived sum 与 supervised monotonic `571.483797368 s` 一致；完整 workflow monotonic `571.514731005 s`，conservative settled `625.736658980034 s`。这些时钟不相加、不互相改写。

Q1/S2 的配对成本和 BLR 因子 flop 事实如下：

| 成本字段 | Q1 exact | S2 BLR |
|---|---:|---:|
| symbolic | `0.2683213069976773 s` | `0.33692986499954714 s` |
| numeric | `18.488779414998135 s` | `19.946495771997434 s` |
| full monotonic | `536.4680422439997 s` | `571.5147310050015 s` |
| conservative settled | `584.7709557270404 s` | `625.736658980034 s` |
| factor flop total | — | theoretical `RINFOG3=39449025878.0`；actual `RINFOG14=41079564559.0` |

## 6. 质量/资源 Gate 与限制

独立 checker 的 `comparison_gates`、`control_gates`、`BLR_resources.gates` 全部为 true，包括 matrix/physical/source identity、one-factor/one-solve、RSS/PSS readable、tree/inventory/workspace cap、host reserve、zero swap、descendant cleanup。这个“全过”是本阶段证据闭合，不是 S3 admission；memory decision 单独由 `R_peak/R_live` 判定。

工程资格化记录 `s0_final_preflight.json` 报告 directly-related tests `128 passed`、compileall/diff/input validate/dry-run PASS；Ruff unavailable，full repository pytest not_run，CI not_claimed。sandbox 的 OpenMPI/PMIx 权限和 process-view false negative 已由实际宿主复核纠正，不是 PDE failure 或 replay；没有因此新增 PDE 或 route。S0 app-reported `1761.112 s` 与最终 preflight engineering elapsed `5235.60104560852 s` 有重叠，只作工程时间，不进入 PDE ledger。

## 7. 收口

本固定配置结论为 `STRONG_BUT_INSUFFICIENT_MEMORY_GAIN`，不是 `BLR_ACTION_UNQUALIFIED`：质量方向存在，但收益不足。由于质量 Gate 通过而 memory Gate 不通过，Review V16 规定直接 S5，不试 `epsilon`、不补 BLR 变体、不启 p6。保留三 RHS packet、native fields、factor/inventory/RSS 对照和独立 checker，未来若有不同架构必须重新绑定输入、source、factor与资源口径。

结果不证明所有 BLR、所有 p4 或所有 0.7 nm 路线失败；它只关闭当前固定配置的适用边界：一个全局 p4 BLR 因子在此 13.5 nm 单元上的质量足够，但没有形成足够的完整峰值内存收益，也没有完整 Full3D 资格。

证据入口：[response V17](../response_v17.md)、[compact](records/p4_blr_v16_compact.json)、[decision](records/p4_blr_v16_decision.json)、[independent checker](../../../benchmarks/artifacts/task39extra/p4_blr_v16/root_engineering/s2_independent_check.json)、[formal summary](../../../results/euv_grazing1_phi0/task39extra_v16_s2_blr_control__full3d_iterative__mpi1__Mna/20260913T163912.716491Z/physical_p4_blr_v16_summary.json)、[run index](records/run_index.json)。
