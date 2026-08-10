# Case101：Task037b frozen M10 Hybrid iterative research capability

Case101 是 Review V7 选择性整合后的冻结 M10 正向能力入口。它把一个完整的
Hybrid FEM–Modal 迭代流程固定在可审阅的参数、源码和 compact evidence 上：有限元
细网格的作用由 matrix-free action 完成，端点辅助量用 DtN 模态表示，求解后再恢复
物理场并导出 canonical 数据。该能力是 `research_only`、必须显式 opt-in 的研究入口，
不是 ordinary solver 默认值，也不是 production qualification。

## 冻结模型与算法

| 项目 | 冻结值与含义 |
|---|---|
| 物理域 | p6/h10；modal p6/h10；13.5 nm；S 偏振；10° grazing；bottom/top interface 10/110 nm |
| 模态规模 | requested M=120、candidate M=240；每个端点 40 个 DtN modes |
| 线性算子 | exact monolithic Hybrid operator；action-consistent modal Schur；right FGMRES，restart 90，max-it 1000，rtol `5e-9`，zero initial |
| 预条件器 | 两侧各一次 fixed whole-endcap ILU(0) + 40-mode DtN Woodbury；不构造第二套 direct global factor |
| 生命周期 | setup → solve/postsolve → bottom/top recovery → own physics/grid → canonical active/full streaming 与逐侧 cleanup → record |
| 默认边界 | `ordinary direct Hybrid` 默认不变；参数、MPI 数、模式数或物理改变后必须重新资格化 |

“固定 whole-endcap”表示每个端点只保留一个不重叠的局部 ILU(0) 因子；Woodbury
动作只修正 40 模态的端点耦合。它减少求解阶段的驻留对象，但代价是固定参数域、较长
迭代时间以及必须独立检查恢复、物理量和 canonical packet。

## M10 正式证据摘要

M10 MPI8 单次 formal 的历史值如下；RSS 是 simultaneous process-tree authority，
不是 PSS/USS 或对象字节数：

| 指标 | 值 |
|---|---:|
| iterations / reason | `792 / 2` |
| reported / global / bottom / top / modal residual | `3.578062165607276e-09` / `3.578062144715876e-09` / `4.921856578759462e-09` / `2.6635965562403923e-09` / `1.4561321294580367e-15` |
| exact traction bottom / top | `4.820141813913522e-09` / `2.6635965562403923e-09` |
| external orders | `80/80`；order audit 与 canonical lifecycle 通过 |
| significant channels | iterative/direct 与 Full3D authority 的 `12+12` 比较通过 |
| process-tree RSS / swap | `6018.57421875 MiB`（约 `5.8775 GiB`）/ `0` |

数值、traction、recovery、own physics、canonical、lifecycle 和独立 checker 均通过。
上述结果只证明冻结的 p6/h10、13.5 nm、S、10°、M120/240、MPI8 候选；不证明
0.7 nm、连续体收敛、任意角度/材料/网格或 production 使用。

## 可审阅入口与边界

- 冻结正向 runner：[`run_task037b_hybrid_iterative.py`](../../../benchmarks/run_task037b_hybrid_iterative.py)
- process-tree watchdog：[`run_task037b_hybrid_iterative_watchdog.py`](../../../benchmarks/run_task037b_hybrid_iterative_watchdog.py)
- 独立只读 checker：[`task037b_hybrid_iterative_checker.py`](../../../benchmarks/task037b_hybrid_iterative_checker.py)
- M10 正向 compact：[`task037b_v6_mpi8_traction_aligned_full_qualification_v1.json`](records/task037b_v6_mpi8_traction_aligned_full_qualification_v1.json)
- M1–M11 memory closeout compact：[`task037b_v6_memory_optimization_closeout_v1.json`](records/task037b_v6_memory_optimization_closeout_v1.json)

大场、timeline、stdout、canonical shard、NPZ 和 checker 输出保留在
`benchmarks/artifacts/` 的 ignored raw artifact 中，不进入 Git。改变任何冻结参数、
solver/PC、物理条件、MPI 数或输出合同，都必须新建 source/hash-bound evidence 并重新
运行数值、资源和 offline qualification；不得通过参数扫描或 fallback 代替资格化。
