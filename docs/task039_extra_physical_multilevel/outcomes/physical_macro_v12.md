# Task39extra V12 中心结果：O0–O4 物理宏块 PC 收口

## 结论

V12 在新的 `physical_macro_dd4_v12`、2.5 GiB 局部库存预算下，确实完成了 42 个真实三维物理宏块的数值构建、局部回代审计、代表 native witness、cached/native A4 桥接和 C_U/传递接线，并持久化了 4 组真实 p4 控制记录。随后 O1 因共享 O0/O1 保守预算耗尽而受控停止，未完成完整的共享 q 框架比较，也没有进入 restart、p6 outer、original/notch 或 official physical output。

因此本轮的准确分类是：

`PARTIAL_PHYSICAL_CONTROLS_WITH_PERFORMANCE_CONTROLLED_STOP`

这不是 system OOM、MUMPS numeric error、Maxwell convergence failure，也不是 production solver qualification。`ordinary default` 未改变，`master merge` 仍 `NOT_APPROVED`。

## 1. 方法和冻结身份

本方法把 p4 的 48,960 个独立未知量按真实材料、DtN 支撑和 Floquet 主从关系分成 42 个小物理块；每个块先分解一次，后续只回代。这样可以观察局部逆是否真的由物理离散组成，但局部小残差并不自动等于全 p4 逆或 p6 外层已经收敛。四步 I4 是有限的 FGMRES 内部近似：每次从零初值最多做 4 次真实 `B4` 作用，达到内部目标才提前返回，否则也可合法近似返回并记录真实残差。

C_U 复用已有的全局粗修正，负责把局部块之间的跨块误差重新带回 p4 粗层，并补回单元内部响应；代价是额外常驻 C_U 内部因子、S/p2 底层对象和重复回代工作。它不是一次新的全局 p4 直接分解，也不能由局部块 residual 代替跨块误差的 outer 检验。

| 身份 | 值 |
|---|---|
| formal source | `e8c3c82bab2687a811a11f0798a2879c725532b5` |
| profile / memory policy | `physical_macro_dd4_v12` / `SYMBOLIC_SIZED_LOCAL_MUMPS_V11` |
| physical / ordered mode SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` / `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| model | 13.5 nm、Full3D、p6/h10、252 hex、80 DtN modes、MPI1、线程1、complex128 |
| geometry / illumination | 50×25 nm、z=`-10..130 nm`、grazing=`1°`、azimuth=`0°`、s polarization |
| p6 / p4 size | p6 independent/storage=`164592/173802`；p4 independent/storage=`48960/53084` |
| caps kept | V12 local inventory=`2684354560 B`；old V10/V11=`2147483648 B`；local factor=`536870912 B`；temporary reserve=`1073741824 B` |

## 2. O0–O4 状态

| 阶段 | 结果 | 实测/派生证据与边界 |
|---|---|---|
| O0 precheck | `O0_PRECHECK_COMPLETED` | 2.0600177589932294 s；tree RSS peak 147095552 B；swap 0；9 samples；descendants cleared |
| O1 full physical controls | `PERFORMANCE_CONTROLLED_STOP`，未完成 | 保守阶段计费 376.259674047942 s；tree RSS/PSS peak 2574671872/2539922432 B；swap 0；1338 samples；cap-exceeded samples 0；SIGTERM 清除整个 child tree |
| O2 restart32/64 | `not_run` | O1 未完成，且没有完成 ONE/BAL framework selection |
| O3 original/notch | `not_run` | O2 prerequisite 未满足；没有新的 p6 outer |
| O4 finalize | `O4_FINALIZED` | 2.0538921670007735 s；没有新的 reference factor/solve；RSS peak 144691200 B；swap 0；descendants cleared |

O1 停止原因是共享 O0/O1 保守账本达到边界，而不是内存资源 Gate：账本中的 `o0_o1_charged_seconds=7201.319691806935`，名义上限为 7200 s，超过 1.319691806935 s。实现活动登记为 6823.0 s；其余 O0/O1 阶段费用包含在同一账本，不能把这条 1.32 s 差异抹去。账本总计到 O4 为 7203.373583973936 s / 43200 s 总上限；实现结束到 O0 开始的 65.459151 s，以及 O0/O1、O1/O4 之间未单独计时的间隔，均按记录列为 uncharged gaps，不宣称 gapless total。

## 3. 42 块物理覆盖和局部质量

| 检查 | 结果 | 解释 |
|---|---:|---|
| physical macro blocks / cells | 42 / 252 | 42 个宏块各有独立 numeric factor record；18 个 `local_classes/local_factors` 是 C_U 元素内部响应的类因子，属于另一层对象 |
| covered p4 rows | 48960；support cells 1656 | 覆盖全部 p4 独立坐标；block max rows 1944；multiplicity 1–4 |
| numeric blocks / witnesses | 42 / 84 recounted | 759 checks、errors=[]；全部块达到记录级 numeric/backsolve inventory |
| max local residual | `2.1772149386553977e-15` | 局部回代质量；不是 p4 true residual 或 p6 residual |
| native witnesses | 6；最大相对残差 `8.243915633632588e-16` | 代表 material-interface、interior-no-DtN、port-DtN 选择；不是 42 块全部 native witness 次数 |
| cached/native A4 bridge | relative `2.787784119354311e-15` < `1e-11` | `source_modified=false`；并列 absolute scale `9.45903599770343e-06` 不与 relative 阈值混用 |
| C_U / W transfer | built and inventory checked | after C_U inventory=`2180383916 B`；after W=`2180380092 B`；C_U closure scalar `not_persisted_not_verified`，不能写成 closure PASS |
| p2 bottom | FE/port/augmented rows=`7246/80/7326`；NNZ=`818100`；allocated/used padded=`270000000/65000000 B`；derived matrix+reported-factor=`341069688 B < 536870912 B` | S/p2 stayed within the 8192-row/512 MiB policy; this is derived policy budget, not RSS |

V12 inventory lifecycle 的 cap 是 2,684,354,560 B；after cached action/C_U/W transfer 的三个 retained values 都在 cap 内。allocated、used、CSR 和 retained inventory 是不同字段：本批汇总为 allocated 1,671,000,000 B、used 888,000,000 B、CSR 450,499,800 B，不能用 used 或 RSS 替换既定库存账。

S/p2 的上述 341,069,688 B policy budget 与 42 个 local macro block inventory 分开，同时存在并已包含在 O1 的 process-tree RSS 观测中；其原始阶段记录为 `stages.jsonl:247`，文件 SHA256 为 `4b1fd995693c14177c028304916b964a21cde7a23f833fd24d7b98ac9ac0ca40`。build/JIT 和其他检查没有独立的终态时钟记录，属于 shared O0/O1 活动的 `unknown/included`，不能从 376.259674047942 s 中减去 p4 小计后伪造 build 实测。

## 4. 四组真实 p4 控制：不足在哪里

四条 record 名称中的 `BAL_H` 来自既有历史 g/reference packet；本轮 O1 对这些输入只执行了 bare B4/I4 内部检查，没有执行完整 BAL_H 或 ONE_C 外层 PC。因此不能把它们称为本轮 BAL_H framework samples。四条均从 I4 zero start 开始，恰好执行 4 次 I4 `B4` call、3 次显式 A4 evaluation，返回 PETSc reason `-3` 的 `INNER_APPROXIMATE_RETURN`。`1e-4` 是内部目标；4 步后没有达到它，所以这些是合法的近似内部结果而不是 I4 pass。表中的 `reference_residual` 约 1e-11 是 reference evaluation 的残差，不能替换左侧 I4 true residual。

| record | bare B4 true residual | I4 true residual | bare field L2 / scaled curl | I4 field L2 / scaled curl | I4 s | A4 identity rel. |
|---|---:|---:|---:|---:|---:|---:|
| `A2R160_BAL_H_p4_01` | 4.568342704547102 | 0.9502310252350668 | 0.8489923330716638 / 0.8488357966287257 | 0.9647147926182198 / 0.964639027200986 | 6.0514075710001105 | 3.1604911627905363e-13 |
| `A2R160_BAL_H_p4_02` | 0.19394917320237565 | 0.1012649488434464 | 0.9146177153493735 / 0.9142807117909154 | 0.8777570760481551 / 0.8773717677729929 | 5.5842256810014685 | 9.517938205625473e-15 |
| `LIGHT448_BAL_H_p4_09` | 5.101960781668161 | 0.9778952412775763 | 0.8581820338128715 / 0.8581222874792352 | 0.9928176043406823 / 0.9928022756707928 | 5.449962579003718 | 4.117471440640116e-13 |
| `LIGHT448_BAL_H_p4_10` | 0.19325317989215776 | 0.10194959659698315 | 0.9154309172609856 / 0.9151104456074007 | 0.8775511199054001 / 0.8771869820432219 | 5.575606445003716 | 9.597488642530234e-15 |

直观上，四步内部纠错把两个约 0.19 的 bare residual 降到约 0.10，但仍远高于 `1e-4`；另外两组降到约 0.95–0.98。A2R160_02 与 LIGHT448_10 的 field L2/scaled-curl 同时改善；但 A2R160_01 的 field error 从 0.8489923330716638/0.8488357966287257 变为 0.9647147926182198/0.964639027200986，LIGHT448_09 从 0.8581820338128715/0.8581222874792352 变为 0.9928176043406823/0.9928022756707928：残差改善不等于场误差改善。此时不能凭 A4 identity 小或 local residual 小宣称 PC 强：`ONE_C`、共享 q framework comparison、BAL/ONE selection 和 physical outer 都没有完成。

四条记录的可审计下界为：4 个 p4 records、4 个 I4、至少 20 个 B4 calls、至少 840 个 `M_D` local solves；I4 时间和 22.661202276009014 s，范围 5.449962579003718–6.0514075710001105 s；bare B4 合计 4.245582314004423 s；evaluation 合计 21.554720083000575 s。停止时的 in-flight work 不计入这些下界。

独立保存记录算术审计有 88 checks、`errors=[]`、`SAVED_RECORDS_CONSISTENT`；它重算向量和 cell-energy 字段，不声称重新施加 FE 算子或产生 outer-PC PASS。

## 5. official 结果和负结果边界

以下内容在 V12 没有运行，原因是 O1 shared budget stop 使 O1 未完成，随后 O2/O3 prerequisite 不满足：

- restart32、restart64 共同节点/同时间比较；
- p6 original 与条件 notch；
- full explicit true residual、E/H field archive、near field、R/T/A、`A_volume`、modal amplitudes、衍射级；
- official result、守恒和同结构参考对照。

所以本轮没有新的 official R/T/A，p6 原方程 `norm(b-A6x)/norm(b) <= 1e-6` 门槛也没有被检验，更没有通过；不能把 V5 历史成功 baseline 复制到 V12。V5 原始/notch 的历史成功仍保留，但其条件参考 workflow 的 448 页 global `pswpout` 归因仍为 `UNRESOLVED`，不能被本轮 job/global swap 零增量改写。旧 V10/V11 的受控负结果保持原分类；V12 的 2.5 GiB cap 只属于新 profile，不改判旧 2 GiB 结果。

## 6. 证据入口

主机记录和 compact：

- [V12 response](../response_v13.md)
- [V12 compact](records/physical_macro_v12_compact.json)
- [V12 terminal/budget index](records/v12_terminal_budget.json)
- [42-block inventory audit](records/v12_inventory_supervisor_audit.json)
- [p4 arithmetic audit](records/v12_p4_supervisor_audit.json)
- [resource audit](records/v12_resource_supervisor_audit.json)
- [lossless raw JSON evidence](records/v12_raw_json_evidence.json)，原始 `/tmp` SHA256 `0ff0246b6c1212b5d1c2706cd1954884626b828192697d1a7d0c9e99d06e6710`；tracked normalized copy SHA256 `329ed513c351896c3db09ea5899389a060b71ff36805daf456132e304fdd1580`
- [preflight](macro_pc_v12_preflight.md)

轻量可读 raw：

- [focused test stdout](records/v12_final_root_focused.stdout.log)，SHA256 `06fb627be4f8eb56eda298be72080c1a3e41a61c9046274bcd8b6b9bd0c666dc`
- [focused test stderr](records/v12_final_root_focused.stderr.log)，SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- [stop smoke stdout](records/v12_stop_smoke.stdout.log)，SHA256 `de2906176ec9a4a43537dff33021072d4edb1ad4a50b0a6b19d354bf38230b29`
- [stop smoke stderr](records/v12_stop_smoke.stderr.log)，SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

上述大型 matrix/factor/field/cache/timeline 仍只在 ignored artifact root 由 hash 指向；tracked 记录只保存审阅所需的小型字段和 raw 摘录。

## 7. 当前交付决定

V12 代码与证据可供同一分支 review，但不能合入 `master`，不能提升 `physical_macro_dd4_v12` 为 ordinary default，也不能据此声称 0.7 nm、2 TB、任意非可分三维结构或连续收敛已经资格化。若要继续，必须由新 review 重新授予 O1/O2/O3 预算和 identity；本轮不会自动升 cap、延长内层、改成 ONE_C、扩 MPI 或启动 workstation heavy case。
