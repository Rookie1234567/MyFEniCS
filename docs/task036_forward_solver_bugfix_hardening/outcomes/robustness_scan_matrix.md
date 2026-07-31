# Task036 V2 robustness scan matrix

## 1. 冻结身份

本文件是 Review V2 的执行入口。扫描不是“把参数随便组合后全部扔给求解器”，而是：
先覆盖中心几何的完整角域，再检查几何边界、16 个离网格点和少量 p6 压力点。这样既能
找到连续区域中的失败簇，也能避免只修好规则网格上的少数样本。

| 项目 | 值 |
|---|---|
| review authority | `review_report_v2.md` |
| branch baseline | `1eab6393525d25ebbf0e7d5068f446c6d5afde1f` |
| V2 numerical source | `6d5e9781bcb1458ecac7a77af22fa2d420f0cd55` |
| frozen table | `benchmarks/task036_robustness_scan_points.csv` |
| table SHA-256 | `01701c580355b8870c3865a6cb631d4db53f12a1a8fc3a2eaba3da59a26812d4` |
| configurations | `226` |
| polarizations | 每个物理点均有独立 `S` 和 `P` |
| ordinary default | unchanged |
| numerical runs at this checkpoint | `10`（5 个 Full3D authority + 5 个 Hybrid M120） |
| dispatcher | `benchmarks/run_task036_robustness_scan.py` |
| dispatcher concurrency | `1–5` independent MPI8 jobs; default `1` |

“配置”包含几何、角度、偏振和 polynomial degree。每个配置首先运行 same-p Full3D
authority；Full3D 通过后才运行 Hybrid M120。因此无失败和无 M 漏斗时，主表最多对应
`452` 个初始 PDE。

## 2. Round 计数

| Round | physical tuples | S/P configurations | degree | 用途 |
|---|---:|---:|---:|---|
| A | 58 | 116 | p5 | 中心几何完整角域与 54.5° 敏感带 |
| B | 32 | 64 | p5 | 四个高度/宽度角点上的八个角度哨兵 |
| C | 16 | 32 | p5 | 固定 scrambled Sobol 离网格验证 |
| D | 7 | 14 | p6 | 高阶 reciprocal、近简并与 mode classification 压力 |
| total | 113 | 226 | p5/p6 | 冻结主表 |

### 2.1 Round A

中心几何固定为 `height=120 nm, width=17 nm`。

- 基础角域：`grazing=[0.5,1,2,4,6,8,10]°` 与
  `azimuth=[0,15,30,45,60,75,90]°` 的 49 个组合；
- 敏感带：`grazing=[0.5,4.538499870338,10]°` 与
  `azimuth=[54.25,54.50,54.75]°` 的 9 个组合。

### 2.2 Round B

几何角点为：

```text
(115,16), (115,18), (125,16), (125,18) nm
```

每个角点使用：

```text
(0.5,0), (0.5,45), (0.5,90), (2,45),
(4.538499870338,54.420819282532),
(10,0), (10,45), (10,90)
```

`(115,17), (125,17), (120,16), (120,18)` 不是预先排入的扫描网格。只有结果显示某个
失败在高度或宽度上单调变化时，才在该失败角度添加相应边中点；新增点必须另行追加并
保留触发根因，不能修改本冻结表。

### 2.3 Round C

Round C 使用：

```text
scipy.stats.qmc.Sobol(d=4, scramble=True, seed=3601)
random_base2(m=4)
```

列顺序为 `height_nm, width_x_nm, grazing_deg, azimuth_deg`：

| ID | height | width | grazing | azimuth |
|---|---:|---:|---:|---:|
| C001 | 120.062468554825 | 16.373318573460 | 6.264104325790 | 43.214247599244 |
| C002 | 117.265311283991 | 17.944835575297 | 4.094700383488 | 89.549943096936 |
| C003 | 117.963093677536 | 16.652463832870 | 8.833654146176 | 22.124828360975 |
| C004 | 124.521252624691 | 17.036967186257 | 1.506029737648 | 65.650423765182 |
| C005 | 123.580174585804 | 16.879133589566 | 3.238411392085 | 54.436560999602 |
| C006 | 118.897035885602 | 17.310540612787 | 7.115752362646 | 10.728999841958 |
| C007 | 115.698930397630 | 16.099990297109 | 2.356808023527 | 78.335390333086 |
| C008 | 121.621107952669 | 17.718407034874 | 7.978234905750 | 31.819109078497 |
| C009 | 121.909682042897 | 16.609238360077 | 2.050468704198 | 5.583297181875 |
| C010 | 115.333232665434 | 17.209083274007 | 8.303697474767 | 49.111992549151 |
| C011 | 119.790153680369 | 16.388200484216 | 3.543810763862 | 26.681388672441 |
| C012 | 122.608083020896 | 17.801031809300 | 6.791234306525 | 73.024983946234 |
| C013 | 124.174369694665 | 16.146120304242 | 9.828243133612 | 84.327598996460 |
| C014 | 118.231460601091 | 17.543355179951 | 0.530559434555 | 37.813026979566 |
| C015 | 116.274211797863 | 16.867160027847 | 5.272774621844 | 60.413917601109 |
| C016 | 120.975681459531 | 17.451404796913 | 5.066906837747 | 16.715625487268 |

该集合覆盖：

- grazing `0.53056–9.82824°` 的低、中、高区；
- 距 45° 最近 `1.78575°`；
- 距 54.5° 最近 `0.06344°`；
- 高度 `115.333–124.521 nm`；
- 宽度 `16.100–17.945 nm`。

### 2.4 Round D

中心几何的 p6 压力角为：

```text
(0.5,0), (0.5,45), (0.5,90),
(4.538499870338,54.420819282532),
(10,0), (10,45), (10,90)
```

每个角度均有 S/P，且仍要求先运行 p6 Full3D authority，再运行 p6 Hybrid。

## 3. 执行与并发合同

用户授权最多同时运行五个 MPI8 PDE，即最多占用 40 个计算核。并发只改变调度，不改变
每个配置的依赖：

1. 同一配置必须先完成 Full3D；
2. Full3D 通过后，该配置的 Hybrid M120 才可入队；
3. 每个 run 使用唯一 output、TMP/TEMP、XDG cache 和 MUMPS scratch；
4. 启动每批前按可用内存和既有峰值自动降低并发数；
5. 任一点出现新的未知失败后，停止投放新点；已运行点可自然结束；
6. 先分类或修复失败，再恢复冻结队列；
7. M240/M480/full-rank 只对失败簇运行，不对通过点盲扫。

## 4. 冻结 Gate

任何通过点必须同时满足：

```text
true relative residual <= 1e-9
interface E residual <= 1e-8
exact traction dual <= 1e-8
full biorthogonality row norm <= 1e-6
direct tangential projection difference <= 1e-10
abs(R + T + A_volume - 1) <= 1e-5
same-p Full3D max(|Delta R|,|Delta T|,|Delta A|) <= 1e-4
zero swap
```

此外仍按固定衍射级 identity 比较 outgoing S/P complex amplitude 与 power。总 R/T/A
通过不能掩盖 cross-polarization 或弱衍射级错误。

## 5. 当前进度

```text
full_repository_traceback = closed
scan_table = frozen
hybrid_p5_dynamic_input_port = pass
same_input_full3d_identity_gate = pass
connected_component_near_degenerate_repair = implemented_unit_tested
driver = pass
analyzer = pass
Round_A = controlled_stop_after_repeated_common_root
Round_B = not_run
Round_C = not_run
Round_D = one_p6_pressure_pair_completed
M240_M480_M492 = not_run_by_root_evidence
next_architecture = DEFERRED_ARCHITECTURE_REQUIRED
```

driver 会拒绝 dirty worktree 或与 `--verified-clean-sha` 不一致的 HEAD。它按 point
使用独立 `run_dir`、TMP/TEMP、XDG cache 与 MUMPS scratch，并且 Hybrid 命令只能从
该 point 已完成的 Full3D watchdog record 取得 hash-bound authority。

## 6. V2 首批同源结果

首批点不是完整域的统计抽样，而是为了尽快覆盖低掠射、方位角、S/P control、角域远端
和 p6 压力。每一行均先运行同输入 Full3D，再运行 Hybrid M120。所有 Full3D 均通过；
五个 Hybrid 均完整结束且 zero swap，但没有一个通过完整 observable Gate。

| point | p / pol. | grazing / azimuth | Full3D peak GiB | Hybrid peak GiB | memory reduction | Hybrid true residual | algebraic interface E | recovered physical E jump | energy closure | max totals delta | fixed channels pass |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A001-P | p5 / P | 0.5° / 0° | 10.092 | 7.212 | 28.5% | `1.837e-12` | `1.936e-11` | `1.709e-1` | `7.606e-5` | `1.642e-4` | 66/80 |
| A004-P | p5 / P | 0.5° / 45° | 10.516 | 7.450 | 29.2% | `1.109e-12` | `8.184e-12` | `4.375e-2` | `1.491e-5` | `9.668e-6` | 48/96 |
| A004-S | p5 / S | 0.5° / 45° | 10.549 | 7.464 | 29.2% | `2.856e-11` | `4.345e-12` | `9.272e-5` | `1.533e-5` | `1.211e-5` | 77/96 |
| A049-P | p5 / P | 10° / 90° | 10.228 | 7.131 | 30.3% | `1.841e-12` | `3.709e-13` | `8.284e-3` | `1.092e-6` | `4.740e-7` | 32/80 |
| D001-P | p6 / P | 0.5° / 0° | 18.572 | 11.222 | 39.6% | `3.103e-13` | `1.417e-11` | `1.822e-1` | `1.307e-5` | `8.483e-5` | 66/80 |

Hybrid 的 exact traction dual 为 `4.565e-13–2.169e-11`，完整 biorthogonality row norm
为 `1.034e-7–4.376e-7`，也全部通过相应 Gate。换言之，线性系统、模态投影约束、
traction 和左右模态归一化都不是首要失败点；失败集中在恢复后的物理界面、能量及固定
衍射通道。

artifact 根目录为：

```text
benchmarks/artifacts/task036/
  6d5e9781bcb1458ecac7a77af22fa2d420f0cd55/v2_robustness/
```

其中 `scan_results.jsonl` 有 10 条调度记录；每个 point 的 `full3d/` 与
`hybrid_m120/` 分别保存 authority 和 candidate。大型 raw artifact 按仓库规则 ignored，
本文件不把它们复制进 Git。

## 7. 为什么停止其余 221 个配置

五个 Hybrid 在不同偏振、角度和 degree 上重复出现同一结构性特征，因此按照 Review V2
“遇到重复根因先修通用算法”的规则停止继续投放。当前耦合只满足：

```text
D_bottom u_bottom = L_bottom a
D_top    u_top    = L_top    a
```

这里 `D` 只把有限元界面场投影成 M 个模态坐标。界面场仍可包含 `D` 看不见的补空间
分量，所以“120 个坐标相等”并不等于“整个物理切向场相等”。历史 A049-P 漏斗又证明
M120、M240、M480 到 M492 的物理跳跃几乎不变，而峰值从约 7.263 GiB 增至
19.405 GiB；对应 Full3D 仅约 10.161 GiB。M492 因而是
`HYBRID_FUNCTIONAL_NO_REDUCTION_ADVANTAGE`，不能作为修复路线。

本批次后续合同固定为：

```text
formal Hybrid M hard cap = 120
M240/M480/M492 = closed for this repeated root
remaining frozen scan points = not_run
reason = repeated trace-complement architecture blocker
disposition = DEFERRED_ARCHITECTURE_REQUIRED
```

这不是宣称 M120 已经通过，而是保证实现不靠提高 M 消耗掉 Hybrid 的内存优势；新架构
若在 M120 下不能通过，必须 fail closed。

## 8. 并发绑定修正

本批次首次使用五个 MPI8 job 时，外层 `taskset` 虽给了互斥 CPU lease，但 OpenMPI 的
`core/slot` 默认映射又把五组 rank 绑定回同一组 CPU0–7。进程存活且数值与内存记录
有效，但 Full3D wall time 受调度污染，不能作为正式速度 authority；Hybrid 在发现后约
15 秒内被实时重绑，时间仅作参考。

driver 现改为同时向 OpenMPI 传入每个 lease 的显式 CPU list，并使用：

```text
OMPI_MCA_hwloc_base_cpu_list=<the eight leased CPUs>
OMPI_MCA_hwloc_base_binding_policy=cpu-list:ordered
```

独立 MPI8 probe 已确认一个 lease 中 rank 0–7 各自只绑定一个不同 CPU。此修正只影响
调度，不改变已经完成 PDE 的数值 kernel，因此没有重跑上述十条 PDE。
