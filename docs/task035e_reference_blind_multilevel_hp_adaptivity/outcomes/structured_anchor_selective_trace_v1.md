# Task035e structured anchor 与 selective-trace 收口报告

## 1. 最终结论

用户新增的三网格一致性 Gate 已通过。这里没有重新运行已经完成的重型
reference PDE，而是从三个现有 MPI8 official raw artifact 独立重提取同一份
59-goal inventory：

| p6 endpoint | mesh | 59-goal pass | normalized L2 / RMS / Linf | true residual | process-tree peak | elapsed |
|---|---:|---:|---:|---:|---:|---:|
| h10 | `(6,3,14)`；252 cells | 59/59 | 1.334077 / 0.173682 / 0.504386 | `1.483287e-11` | 14.466988 GiB | 166.392 s |
| h7.5 | `(9,4,20)`；720 cells | 59/59 | 0.0123474 / 0.00160750 / 0.00441636 | `2.076296e-11` | 31.880505 GiB | 825.415 s |
| h5 | `(12,5,28)`；1,680 cells | 59/59 | `3.433380e-13` / `4.469880e-14` / `2.771708e-13` | `1.039818e-10` | 77.945587 GiB | 4,380.997 s |

同一冻结 tolerance 下：

| pair | 59 项落在 tolerance 内 | 最大 `abs(delta)/tau` |
|---|---:|---:|
| p6/h10 ↔ p6/h7.5 | 59/59 | 0.500000 |
| p6/h7.5 ↔ p6/h5 | 59/59 | 0.00441636 |
| p6/h10 ↔ p6/h5 | 59/59 | 0.504386 |

而且对全部 59 项，h7.5→h5 的细网格增量都不大于 h10→h7.5 增量。因此
“三个模型不一致即停止”的条件没有触发，structured anchor 路线继续执行。

但后续路线没有得到合格候选：

- `H10_fixed_p5trace_p6interior` 为 52/59；
- projection 排名选出的唯一 200-orbit selective-face candidate 为 50/59；
- selective candidate whole-job simultaneous process-tree peak 为
  `13.004326 GiB`，超过 `11.0 GiB`；
- selective candidate 相对 M1 的 normalized L2 反而恶化 `6.756208%`。

所以本轮按合同在第一个 actual selective candidate 后停止。没有运行第二个
阈值扩展，也没有恢复 generic isotropic local-h。结果分类是
`REFERENCE_VISIBLE_DEVELOPMENT_DIAGNOSTIC_AND_CONTROLLED_NEGATIVE`，不获得
reference-blind 或 hidden-audit credit。

## 2. 数据与源码身份

| role | full source SHA | MPI / ABI |
|---|---|---|
| p6/h10、h7.5、h5 existing reference | `03ddc8319fa9ee9da6a9ee948b539a067e9c3dd0` | MPI8；PETSc complex128/int32 |
| M1 fixed trace | `f1ba5627f163da54fa383b43be58fd38c0da7bc9` | MPI8；PETSc complex128/int32 |
| actual selective trace | `d9e2c2f8c8edbd91d96a0e642d8f4e1cc0778e6e` | MPI8；PETSc complex128/int32 |

M1、p6/h10 与 selective candidate 使用相同的 boundary-fitted
`(6,3,14)` structured mesh、252 cells、材料平面和几何配置。
selective run 保存的 partition-independent mesh SHA-256 为：

```text
f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857
```

base configuration identity 为：

```text
fee666cc224ca004c142950eb48def671f2156f4151a2d2e39206f1f0c47e32e
```

ordinary default 没有改变。所有新增路径都是显式 opt-in。

## 3. M1：H10 fixed p5 trace + p6 interior

M1 在 p6/h10 的同一实际网格上使用 global p5 trace 和 global p6
cell interior：

| metric | M1 |
|---|---:|
| active FE DoF | 154,735 |
| independent trace rows | 34,920 |
| augmented rows | 35,000 |
| matrix NNZ | 20,140,928 |
| factor NNZ | 101,141,150 |
| factor fill | 5.0217 |
| elapsed | 137.883 s |
| base matrix assembly | 69.161 s |
| MUMPS setup | 44.560 s |
| solve | 0.091 s |
| sum-rank historical peak upper bound | 9,784.469 MiB |
| swap | 0 |

其 true residual 为 `1.150501e-11`，Floquet 三项 mismatch 均为 0，
`R+T+A_volume-1 = 7.460699e-13`。数值求解与能量 Gate 通过，但固定
59-goal Gate 只有 52/59。

失败目标为：

```text
top:m0:n0:power
top:m0:n0:co_amp_imag
top:m-1:n0:power
bottom:m-1:n0:power
bottom:m-7:n0:co_amp_imag
scalar/R00_total
scalar/R_total
```

因此 M1 是低内存同网格基础模型，不是 accuracy anchor。

## 4. p6→p5 physical trace projection audit

offline audit 从 existing p6/h10 八个 VTU shard 重建 252 个 p6
N1curl 单元场。采用：

- degree-6 tensor Lagrange field reconstruction；
- covariant pullback 与 Basix N1curl interpolation；
- physical tangential L2 p6→p5 exact nested projection；
- shared entity incidence median；
- x/y periodic physical orbit mean。

最大重建绝对误差为 `2.839582e-12`，最大相对误差为
`2.763185e-12`。

| entity | physical count | periodic orbit count | p6→p5 missing energy fraction |
|---|---:|---:|---:|
| edge | 1,067 | 792 | `3.748638e-25` |
| face interior | 900 | 774 | 1.0 |

edge contribution 在此投影量下可忽略，因此没有新增 selected-edge-orbit
接口，复用已有 selective-face 路径。排序使用每个 periodic physical face
orbit 的 projection missing energy / 20 added independent rows。

前 200/774 个 face orbits：

- 捕获 `79.191773%` 的 face projection loss；
- 对应 233 个 geometry face keys；
- 其中 33 个 orbit 含 periodic paired copy；
- exact preview 为新增 4,000 independent rows。

重要限制：existing p6/h10 artifact 没有保留 59 个 fine-space adjoint
vectors，所以这里不能计算任务书所说的 actual 59-goal weighted surplus。
本地 projection 只作为 ranking signal，没有被写成 DWR。最终 accept/reject
完全由 actual MPI8 candidate 的 59-goal endpoint 决定。

## 5. Actual selective-face candidate

实际 candidate 严格使用上述一次性 200-orbit batch；没有选 edge，没有
local-h cell，也没有第二次扩大阈值：

| metric | M1 fixed trace | selective 200 orbits | global p6/h10 |
|---|---:|---:|---:|
| active FE DoF | 154,735 | 159,395 | 173,802 |
| rows | 35,000 | 39,000 | 51,272 |
| matrix NNZ | 20,140,928 | 24,696,176 | 41,989,040 |
| factor NNZ | 101,141,150 | 116,348,600 | 202,441,352 |
| 59-goal pass | 52/59 | 50/59 | 59/59 |
| normalized L2 | 5.397523 | 5.762190 | 1.334077 |
| Linf | 2.054809 | 1.972418 | 0.504386 |
| whole-job/process-tree peak | `<9,784.469 MiB` upper-bound口径 | 13,316.430 MiB | 14,814.195 MiB |
| elapsed | 137.883 s | 531.939 s | 166.392 s |

M1→selective 的实测增量：

| quantity | delta |
|---|---:|
| active FE DoF | +4,660 |
| independent rows | +4,000 |
| matrix NNZ | +4,555,248 |
| factor NNZ | +15,207,450 |
| 59-goal pass count | -2 |
| normalized L2 | +6.756208% |
| process-tree peak | 至少 +3,531.961 MiB |

与 global p6/h10 相比，selective candidate 已减少：

- rows `23.935091%`；
- matrix NNZ `41.184233%`；
- factor NNZ `42.527256%`；

但 process-tree peak 只下降 `10.110341%`，仍为 `13.004326 GiB`。这再次
说明本路径的 whole-job peak 不能只用 factor NNZ 推断。

### 5.1 数值 Gate

candidate：

- full active exact-sequence residual：`2.478629e-11`；
- KSP/MUMPS：pass；
- Floquet x/y/corner mismatch：全部 0；
- hanging patch：0；
- `R+T+A_volume = 0.9999999999992539`；
- zero swap。

但 59-goal 只有 50/59，失败目标为：

```text
top:m0:n0:power
top:m0:n0:co_amp_imag
top:m-1:n0:power
top:m-6:n0:co_amp_real
bottom:m-1:n0:power
bottom:m-4:n0:power
bottom:m-7:n0:co_amp_imag
scalar/R00_total
scalar/R_total
```

它没有把 M1 的 7 个失败目标补齐，反而新增了两个失败目标。

### 5.2 内存生命周期

| phase | simultaneous process-tree RSS peak |
|---|---:|
| variable-p/static-condensed assembly | 8,868.504 MiB |
| after base matrix assembly | 9,743.230 MiB |
| after DtN insertion | 10,159.836 MiB |
| MUMPS setup | 12,557.012 MiB |
| solver objects retained for postprocess | 13,009.645 MiB |
| after field output | **13,316.430 MiB** |

峰值出现在 field output 之后，而不是 factorization 内部。worker 的
rank-history sum `13,039.539 MiB` 不是 simultaneous authority；正式判定使用
外层 process-tree sampler 的 `13,316.430 MiB`。临时 sampler 未可靠识别
八个 rank 的 smaps，因此本条没有伪造 PSS/USS，RSS process-tree 为唯一正式
口径。

## 6. 为 exact structured anchor 暴露并修复的软件问题

现有 Task035d API 原本把 local-h plan 的非空 marked-cell 和 90,000 DoF
都作为硬条件，不能表达“保持 exact structured mesh，只选择 trace orbit”的
Task035e opt-in 模型。本轮做了三个局部修复：

1. `73da8e9b6e0e010b171ed3c5dd4eb251693b67b9`：
   只在确有 selected physical face 时允许 zero-h plan；ordinary empty
   local-h 继续 fail closed。
2. `97c9c48683e5895c6c975512a97c08279d1f41df`：
   mesh/reduction authority 中把 Task035e zero-h selective anchor 的
   90,000 DoF 改为 advisory；Task035d ordinary path 仍是 hard Gate。
3. `d9e2c2f8c8edbd91d96a0e642d8f4e1cc0778e6e`：
   修复 solver reduction builder 内第二处重复的 90,000-DoF hard Gate。

在 `97c9c48...` 上启动过的一次 attempt 在 assembly/factorization 前被第二处
软件 Gate 拒绝；return code 1、峰值 4,726.598 MiB、zero swap。它保留为
software controlled negative，不是物理结果，也没有被删除或重写为通过。

ordinary Task035d Gate、ordinary default 和其他 backend 均未放宽。

## 7. 测试

最终源码上的结果：

```text
python -m pytest -q \
  src/test/test_203_task035d_stage4_local_h.py \
  src/test/test_242_task035e_variable_p_setup_anatomy.py

16 passed, 3 skipped in 94.62 s
```

```text
mpiexec -n 8 python -m pytest -q \
  src/test/test_203_task035d_stage4_local_h.py::\
test_selective_trace_only_plan_preserves_the_root_mesh

1 passed on each of 8 ranks
```

四个变更文件的 Ruff 与 compileall 均通过。

## 8. 停止决策

本轮不运行第二个 selective threshold，原因不是 PDE 数量限制，而是第一个
有判别力的 actual batch 已同时给出两个负信号：

1. 59-goal 从 52/59 退到 50/59，normalized L2 恶化；
2. whole-job peak 已超过 11 GiB，扩大 batch 只会继续增加 active
   rows、NNZ 与内存。

因此当前路线冻结为：

```text
p6 h10/h7.5/h5 consistency = pass
H10 fixed p5 trace + p6 interior = accuracy fail, resource pass
projection-selected 200 face orbits = accuracy fail, resource fail
threshold expansion = not_run
structured selective-trace lane = stopped after permitted candidate
```

没有运行 p6 reference 重算、generic isotropic local-h、Path B、Hybrid、
p7、level-3 或 exact selected-action Schur。下一步等待集中审阅。

## 9. Compact evidence

完整 59-goal 行、三组 p6 pairwise delta、M1/selective 全部目标、
774 个 face-orbit score/cost ranking、raw artifact 路径/大小/SHA-256、
资源 phase peaks、软件失败和测试结果位于：

```text
benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/
structured_anchor_selective_trace_v1.json
```

actual plan：

```text
benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/
h10_projection_selective_face_budget80_plan_v1.json
```

失败软件 attempt 的原计划：

```text
benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records/
h10_projection_selective_face_budget80_preflight_failed_97c9c48_plan_v1.json
```
