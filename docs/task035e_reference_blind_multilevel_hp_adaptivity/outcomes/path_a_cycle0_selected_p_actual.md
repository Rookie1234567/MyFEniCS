# Path A cycle 0：selected-p actual candidate

## 结论

本轮只运行了用户授权的一条 MPI8 selected-p actual candidate。候选的
residual、energy、Floquet、hanging、MPI8、11 GiB 和 zero-swap Gate 全部
通过，但**动作级预测 Gate 未通过**：

```text
selected-cellwise DWR prediction vs actual candidate-current
factor-two-or-neutral = 19 / 59
opposite sign = 25 / 59
formal diffraction + total opposite sign = 22 / 53
decision = rejected
cycle_advanced = false
cycle 0 current = retained
```

因此该 candidate 不得成为 cycle 1 current。这个结果保存为
`CONTROLLED_NEGATIVE_ACTION_LEVEL_EFFECTIVITY`，不能被 candidate 自身重新计算
得到的 59/59 live-adjoint closure 覆盖：后者证明 candidate 上的实际伴随计算
闭合，前者才回答“cycle 0 的 cellwise estimator 是否正确预测了这次 action”。

完整 59-goal current、candidate、预测量、actual delta、effectivity、raw 文件
SHA 和资源记录位于
[`path_a_cycle0_selected_p_actual_checkpoint_v1.json`](../../../benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/path_a_cycle0_selected_p_actual_checkpoint_v1.json)。
其中不含 hidden reference 数值。

## 数值与动作身份

数值 worker 来自独立 clean worktree，完整 source SHA 为：

```text
f1ba5627f163da54fa383b43be58fd38c0da7bc9
```

当前执行分支的 `429731e10cd830e7af669d0a8b7f9d42df7168f2`
只作为 documentation/evidence base。current、完整 p-shadow、完整 h-shadow 和
sealed reference 均未重跑。

动作只有以下四个 cell：

| canonical target | degree |
|---|---|
| `cell:r42:l1:i1:j0:k0` | p4 -> p5 |
| `cell:r42:l1:i1:j1:k0` | p4 -> p5 |
| `cell:r37:l0:i0:j0:k0` | p5 -> p6 |
| `cell:r13:l0:i0:j0:k0` | p5 -> p6 |

`action_sha256 =
c054f3b5519a30f2e6e741e992f7842a857f389fad1ef6fe0ff66c00b1c2633c`。
没有其他 cell，没有 periodic/material/2:1 closure，也没有与 selected-h
合并。leaf catalog 和 forest geometry hash 均保持不变，leaves 为 160，
p4/p5/p6 cell 数从 `24/136/0` 变为 `22/136/2`。

第一次 campaign invocation 在 MPI/PDE 前因 clean-worktree Python 路径 Gate
退出：

```text
Task035e formal execution requires the repository .venv Python.
```

它没有 watchdog、run 目录或 candidate，不计作 heavy PDE。保留该 failed
attempt 后，使用同一个已有 `.venv` 的 clean-worktree 仓库内路径启动 attempt
2；没有创建第二个环境，也没有修改 numerical source。attempt 2 是本轮唯一
实际 PDE。

## Candidate Gate

| 项目 | candidate | Gate |
|---|---:|---|
| Full3D-equivalent active FE DoF | 59,997 | `<=90,000` pass |
| condensed FEM rows + DtN rows | 20,171 + 80 = 20,251 | pass |
| matrix NNZ | 10,834,433 | measured |
| factor NNZ / fill | 41,278,819 / 3.80997 | measured |
| full explicit true residual | `2.421043e-12` | `<=1e-9` pass |
| energy closure error | `-2.152722e-13` | pass |
| R00 / R / T | 0.0160886209 / 0.0276394999 / 0.4322933170 | official |
| Aclosure / Avolume | 0.5400671831 / 0.5400671831 | pass |
| whole-job RSS | 7,887.426 MiB = 7.702564 GiB | `<=11 GiB` pass |
| simultaneous worker PSS / USS | 6,458.675 / 6,349.059 MiB | measured |
| swap / pswpin / pswpout | 0 MiB / 0 / 0 pages | pass |
| MPI / PETSc | MPI8 / complex128 | pass |

whole-job RSS 峰值出现在 `final_cleanup`，而 solver-phase process-tree 峰值为
7,346.652 MiB。cgroup 不是 dedicated job cgroup，因此没有把共享 cgroup
数字冒充 job peak。

主要原始计时为：

| phase | seconds |
|---|---:|
| mesh / function space / Floquet | 0.212 / 2.029 / 4.038 |
| base matrix assembly | 133.086 |
| raw tensor + condensed build | 44.027 |
| DtN modal loop | 17.943 |
| MUMPS setup / solve | 14.196 / 0.057 |
| full residual / postprocess | 1.390 / 4.734 |
| worker / progress elapsed | 207.671 / 209.184 |

这些是 raw perf-counter component，存在调用层级重叠，不能相加冒充总时间。

相对 cycle 0 current，candidate 实测增加 733 Full3D-equivalent DoF、49 rows、
36,041 matrix NNZ 和 61,359 factor NNZ；whole-job RSS 反而低 481.562 MiB。
preflight 的局部结构预测为 `+93 DoF / +14 rows / +11,830 matrix NNZ /
+73,681 factor NNZ`，因此成本模型也不能把局部 additive proxy 当作实际
global trace closure 成本。

## 59-goal action-level effectivity

预测量从既有
`p-cellwise-authority.json` 中四个 target 的
`signed_dwr_contribution` 使用 `math.fsum` 逐目标重建，再分别与
`p-goal-marking.json` 和 `p-verification-prediction.json` 闭合：

```text
maximum |reconstructed - prediction| = 0
maximum |marking - prediction| = 0
hidden reference consumed = false
```

五个总量目标已经足以显示问题：

| goal | predicted delta | actual delta | effectivity | classification |
|---|---:|---:|---:|---|
| R00_total | -0.01208525 | -0.07040922 | 0.171643 | outside |
| R_total | -0.01455598 | -0.06733399 | 0.216176 | outside |
| T_total | -0.01669595 | +0.05488978 | -0.304172 | opposite sign |
| A_closure | +0.03125192 | +0.01244422 | 2.511361 | outside |
| A_volume | -0.02204008 | +0.01244422 | -1.771110 | opposite sign |

全部 59 个目标中只有 19 个满足 factor-two，25 个符号相反；在 48 个正式
逐衍射级目标和 5 个正式总量目标中有 22 个符号相反，属于系统性失败。按本轮
明确通过标准，该 action 必须 rejected。

## 冻结状态

```text
Path A cycle 0:
    current = pass, retained
    p-shadow = pass, not rerun
    h-shadow = pass, not rerun
    cellwise_partition = pass, reused
    selected-p transition = pass
    selected-p candidate = numerical/resource pass, effectivity rejected
    selected-h = not_run
    cycle_advanced = false

Path B = no new run
cycle 1 shadow = not_run
p7 / level-3 / hidden audit / Hybrid = not_run
```

下一次 action 前需要 estimator repair 或新的明确 review；本轮不自动进入
selected-h、cycle 1 或其他 lane。
