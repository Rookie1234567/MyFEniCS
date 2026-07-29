# Path A cycle 0：single-cell p-up actual diagnostic

## 结论

本轮严格只验证一个动作：

```text
cell:r42:l1:i1:j0:k0 : p4 -> p5
```

数值 worker 固定在
`f1ba5627f163da54fa383b43be58fd38c0da7bc9`。cycle 0 current、完整
p-shadow、完整 h-shadow 和 sealed reference 均未重跑，也没有加入其他 cell、
selected-h 或任何 closure cell。

candidate 的 residual、energy、Floquet、hanging、MPI8、11 GiB 与 zero-swap
Gate 全部通过，但既有单-cell signed DWR contribution 相对 actual
candidate-current 为：

```text
factor-two-or-neutral = 0 / 59
opposite sign = 30 / 59
formal diffraction + total opposite sign = 24 / 53
decision = rejected
cycle 0 current = retained
cycle_advanced = false
```

因此这个 single-cell candidate 不得成为 cycle 1 current。四-cell grouped
action 的失败不能再解释为 cell 之间的非线性交互：即使只升一个 cell，当前
cellwise partition 仍不能定量预测实际 action。当前
`cellwise-p quantitative predictor` 正式关闭；其已有 partition 最多保留为
ranking signal，不能再提供 action-level accuracy credit。

完整 59-goal 行、raw 文件 SHA、transition、结构增量和 Gate 位于
[`path_a_cycle0_single_cell_p_actual_checkpoint_v1.json`](../../../benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/path_a_cycle0_single_cell_p_actual_checkpoint_v1.json)。
该 compact 不读取或包含 hidden reference。

## Transition 与真实结构增量

transition action 的文件 SHA-256 为
`a081612333102e2bcaa3d7a16f2c12768199a5f51f7a1872fddab94da367c89a`，
candidate plan 文件 SHA-256 为
`3c1d22df95da45560f9c251ac9f8bac1ce83ab8778b7d734a82c64f49c4501dc`。
leaf catalog、forest geometry、periodic/material/2:1 closure 均不变，leaves
保持 160，p4/p5/p6 cell 数由 `24/136/0` 变为 `23/137/0`。

运行时 exact-sequence entity audit 给出的增量为：

| 项目 | cycle 0 current | candidate | candidate-current |
|---|---:|---:|---:|
| cell-interior modes | 35,232 | 35,364 | +132 |
| edge modes | 3,704 | 3,704 | 0 |
| face modes | 22,224 | 22,240 | +16 |
| Full3D-equivalent active FE DoF | 59,264 | 59,412 | +148 |
| raw active rows | 61,160 | 61,308 | +148 |
| independent trace rows | 20,122 | 20,138 | +16 |
| augmented rows，含固定 80 DtN rows | 20,202 | 20,218 | +16 |
| matrix NNZ | 10,798,392 | 10,810,712 | +12,320 |
| factor NNZ | 41,217,460 | 41,157,452 | -60,008 |
| factor fill | 3.817000 | 3.807099 | -0.009901 |

唯一新增 trace entity 是一个 p4→p5 face，因此增加 16 个 face modes；没有
edge orbit 被提升。factor NNZ 的小幅下降是本次 MUMPS 实测结果，不把它改写为
“新增负成本”，也不由此推断任意后续 action 都会降低 factor。

## Candidate 数值与资源 Gate

| 项目 | candidate | Gate |
|---|---:|---|
| full explicit true residual | `2.707608e-12` | `<=1e-9` pass |
| eliminated interior max residual | 0 | pass |
| R00 / R / T | 0.0863527953 / 0.0948725837 / 0.3774527359 | official |
| Aclosure / Avolume | 0.5276746804 / 0.5276746804 | pass |
| energy closure error | `-1.441069e-13` | pass |
| whole-job memory authority | 7.560097 GiB | `<=11 GiB` pass |
| process-tree RSS | 7,741.539 MiB | measured |
| simultaneous worker PSS / USS | 6,361.860 / 6,249.074 MiB | measured |
| swap / pswpin / pswpout | 0 MiB / 0 / 0 pages | pass |
| MPI / PETSc | MPI8 / complex128 / int32 | pass |

主要 raw component timing 为：

| phase | seconds |
|---|---:|
| mesh / function space / Floquet | 0.206 / 2.022 / 3.974 |
| base matrix assembly | 119.225 |
| raw tensor + condensed build | 44.705 |
| DtN modal loop | 18.052 |
| MUMPS setup / solve | 12.900 / 0.056 |
| full residual / postprocess | 1.487 / 4.732 |
| worker elapsed | 191.195 |

这些 component 有调用层级重叠，不相加冒充总时间。本轮从 launch 到 compact
只产生这一条 heavy PDE。

## 59-goal 失败形态

五个正式总量已经显示数量级与符号问题：

| goal | cellwise signed DWR | actual candidate-current | effectivity |
|---|---:|---:|---:|
| R00_total | -0.0047134402 | -0.0001450486 | +32.4956 |
| R_total | -0.0043750183 | -0.0001009077 | +43.3567 |
| T_total | -0.0104331147 | +0.0000491945 | -212.0790 |
| A_closure | +0.0148081330 | +0.0000517132 | +286.3512 |
| A_volume | -0.0118998851 | +0.0000517132 | -230.1132 |

59 项没有任何一项进入 `0.5 <= abs(effectivity) <= 2.0`，30 项符号相反。
正式 48 个逐衍射级坐标与 5 个总量坐标中有 24 项符号相反，且同时覆盖
top、bottom、T 与 A，因此是系统性失败，不是单一弱通道的 near-zero 噪声。

## 冻结状态

```text
Path A cycle 0:
    current = pass, retained
    p-shadow = pass, not rerun
    h-shadow = pass, not rerun
    cellwise_partition = ranking-only
    grouped selected-p = rejected
    single-cell selected-p = numerical/resource pass, effectivity rejected
    cellwise-p quantitative predictor = closed
    selected-h = not_run
    cycle_advanced = false

Path B = no new run
cycle 1 shadow = not_run
p7 / level-3 / hidden audit / Hybrid = not_run
```

后续只允许先完成
[cellwise-p estimator repair design](cellwise_p_estimator_repair_design.md)；
未通过既有 raw actual candidates 的离线回放前，不得授权新 action。
