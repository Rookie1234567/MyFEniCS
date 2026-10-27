# Task41extra V16-C：active row 1,622,464 的最小补证方案

## 结论

Stage A 已把 V15 两列全域差分定位到当前误差最大的 active row `1,622,464`（原始编号 `5,218,672`），并证明该行只占列0/列1总误差能量的 `0.004203%/0.003853%`。这个行属于主导 group 1，但该组有 3,646,632 行、承载全域能量的 `71.0718%/71.1085%`；当前元数据已知的 incident cells 7,873/8,014 正是该行所需的两个单元，而它们的同候选数值块/因子尚缺。此前 V14 attempt01/04 两个完整 star 位于 group 40，该组只含全域能量的 `1.8547%/1.8279%`，不能代表 group 1。**最小可执行候选是 row 1,622,464 的两-cell 完整 incident star；它只检验主导签名中的一个实际行，不能代表或关闭整个 71% 组。**

本方案是建议，不是本轮已执行工作。当前授权覆盖保存数据分析；若复用索引找不到完全匹配的旧数值包，新的积分或因子化需要另行明确批准。

## 已有、可直接复用的行身份

来源为 `task41_p0_v16_max_row_probe_metadata.json`，SHA-256 `35720a498334c463f660f9179315eb20d5dbed5d6111fcf7201f7de0c9344665`。记录标明 `metadata_only_no_fe_operator_or_factor=true`，不是有限元算子或因子产物。

| cell | local position | tag / permutation | 坐标范围（配置单位） | coordinate SHA-256 | 行投影 |
|---:|---:|---|---|---|---|
| 7,873 | 376 | 1 / 0 | x 33.5–39；y 13.75–14；z 40–50 | `de118e5efd5a260cd4f362a9acb5c9444531371d7bbc7da3d9f9b8a4eecf5378` | 系数 `+1`；trace E active id 1,622,464，local dof/trace position 376 |
| 8,014 | 76 | 1 / 0 | x 33.5–39；y 13.75–14；z 50–60 | `ff063f2c63bd6c7e3255827d9be399920bdaf1a5c6e9b2780c27784730f749ab` | 系数 `+1`；trace E active id 1,622,464，local dof/trace position 76 |

行属于 mutually-exclusive group code 1：两个 incident cells、无非平凡 MPC、不是 periodic-slave E 展开项。元数据保留每 cell 的全部 8 个 actual-coordinate keys、active ids 和投影记录；执行时应按原文件/hash读取，不从坐标范围重造键。

行上已保存的复数值本身也应作为核对目标，而不能作为局部贡献：

| 列 | `d9` | `d15` | `Δy` | `Δg` |
|---:|---|---|---|---|
| 0 | `4.5292836148291826e-10 + 1.0277290130034089e-10i` | `8.312781574204564e-10 + 1.546140993013978e-11i` | 0 | `−3.7834979593753815e-10 + 8.731149137020111e-11i` |
| 1 | `8.549250196665525e-11 + 9.058567229658365e-10i` | `2.0190782379359007e-10 + 1.6625563148409128e-9i` | 0 | `−1.1641532182693481e-10 − 7.566995918750763e-10i` |

这里 `d=y−g`、`Δg=g15−g9`，所以 `d15=d9−Δg`。这两个全域行值不包含各 cell 的独立有符号贡献。

## 一个最小、完整的 candidate star

先只读查找 producer/source/run/input/window 一致的历史保存 package。若已有 package 同时含下列所有字段且 hash 完全匹配，直接只读重放并报告；不得为了齐字段拼接其它 candidate 或 donor 的对象。

若找不到，申请一个由 cell 7,873 和 8,014 构成的**完整两 cell star**，按 V15 的原生产顺序恢复该 active row 的两侧贡献。只取这两个 incident cells，不加其它探针：

| 缺项 | 最小所需字段 | 作用 |
|---|---|---|
| 候选算子身份 | 同 run/source/input/physics/mesh/qmetric identity；cell actual keys、dof/trace maps、tag/permutation、E 投影 | 排除从 V14 或 donor 借用不同候选块；证明两个 incident 贡献无遗漏 |
| 局部数值算子 | 对这两个 cell 实际使用的 K/G/J/L、S/R/T 或等价分块，并保存 shape、dtype、值摘要、矩阵与 RHS 组合顺序 | 将内部/trace action 与 Schur 及局部消元项分开检查 |
| 消元与终态 | 若原流程有保存则复用其 LU/pivots 和 identity；否则对所需局部矩阵的因子/求解必须单列授权和计数；保存与本列对应的初解、最终 `z_f`、实际 correction | 形成 `r_f=b_i−Kz_f`，识别残差求值与局部解误差；不把其它状态或列混接 |
| 右端与投影 | 原 `b_i`、trace RHS、`Bα`、MPC/active expansion、局部 E 作用及最终 y/g 分量 | 分别重现 y 与 g 的有符号局部贡献，确保 `Bα` 只计一次 |
| 重放结果 | 对两列各存 y、g、d 的局部贡献，生产顺序的闭合余差及完整 row 复值；必要时固定 `z_f` 的 fsum/matmul/clongdouble 残差和既有 lambda 投影 | 直接对照上表同一 V15 行，回答局部机制是否确实覆盖这条最大行 |

验收必须先分别验证两 cell 的 y 和 g，再将两者按生产 E/MPC 映射聚合到 row 1,622,464；实部/虚部均报。不能只使 `d` 接近，不能从全域差反算两个 cell 的贡献，不能对行值归零。没有完全同身份lambda就不求新伴随。未来获准重建的矩阵/LU必须标记RECONSTRUCTED_SELECTED_CELL；没有旧数值hash不能宣称旧内存逐位拷贝，先分别重现保存y15/g15才能将新块用于解释旧失败。

## 资源估算与停止条件

p6 local row space 为 450 internal + 432 trace = 882。shape-only payload 基准（complex128，16 B/项）为：每个 `882×882` dense block `12,446,784 B`、`450×450` block `3,240,000 B`、`432×432` block `2,985,984 B`、`450×432` coupling `3,110,400 B`。两cell的一个882² block副本合计`24,893,568B`。若每cell保留raw+oriented各一份、K/G/J/L只作它们的视图，另保留R/T/S/LU和int32 pivots，两cell基准载荷为`74,684,304B`；这是明确布局的派生数，不含状态/maps/运行时/临时量，也不是峰值准入。这些是单数组形状载荷；实际所需块数、q数量、因子/临时副本及存活重叠必须从精确 inventory 得到，不能简单相加为实测峰值。

执行前必须有一份 exact expected-file/bytes 清单，并按届时新包明确批准的证据限额及现场累计16GiB余量检查；不得复活本轮V16窗口或把本次128MiB限额自动当作未来授权。现有包没有候选局部块，故积分、因子和运行时间均为 UNKNOWN；不得从全域 owner 的旧计时按 cell 数线性折算。若任何准入余量不满足，停止在只读库存，不创建部分 star、不把已生成的部分称为完整证据。

当前方案不请求或执行 28,000-key owner、surface/carrier、200q、全域矩阵/因子、FGMRES、目标场或新官方结果。即使完整两 cell star 重放成功，它也只解释/排除该 row 上的局部机制；由于该行只占不到 0.005% 的总误差能量，后续若需解释全域 FAIL，必须由互斥组实际能量覆盖决定下一项并另行授权，不能把本方案扩成更多 cell。
