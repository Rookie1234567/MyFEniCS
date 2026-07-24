# Task035b outcomes summary

## 最终状态

```text
status = PARTIAL_WITH_CONTROLLED_NEGATIVES
geometry = Task034 fixed rectangular block grating only
formal_MPI = 8
ordinary_default_changed = false
irregular_geometry = out_of_scope_by_user / not_run / not_a_completion_gate
hybrid_eligible_candidate_count = 0
master_merge = not_authorized
```

Task035b 完成了同网格 p4/p5/p6 资格化、entity DoF 分解、exact
assembly-time cell condensation、MUMPS 生命周期与 exact preallocation
优化、multi-goal DWR、252-cell physical smoothness signal、classifier v3、
真实 regionwise physical row reduction 和 tetra h-vs-p 顺序竞争。

工程主线取得明确正结果：消除完整高阶矩阵、inactive rows、重复 tensor、
preallocation 浪费和 factor 生命周期后，rows、NNZ、factor、peak memory
与时间全部下降。科学主线没有得到完整 same-error positive candidate：
最强的两个 h15 候选均只在 significant diffraction channel Gate 失败，因此
按合同未接入 Hybrid，也没有发布成功的 0.7 nm resource model v3。

## 权威基线

h10 structured hexa 为 `(6,3,14)`、252 cells。最新 MPI8
exact-preallocation/projection record：

| degree | FE DoF | active rows | matrix/factor NNZ | build/setup/solve | R00 / R / T / Aclosure | residual |
|---:|---:|---:|---:|---:|---:|---:|
| p4 | 53,084 | 21,824 | 8,184,464 / 40,151,936 | 35.64 / 13.36 / — s | 0.001872161 / 0.001882317 / 0.596619520 / 0.401498163 | `2.35e-11` |
| p5 | 101,815 | 35,000 | 20,140,928 / 101,062,900 | 24.72 / 36.48 / 0.077 s | 0.000785714 / 0.000794886 / 0.602483954 / 0.396721160 | `1.25e-11` |
| p6 | 173,802 | 51,272 | 41,989,040 / 202,441,352 | 102.32 / 102.54 / 0.167 s | 0.000753761 / 0.000762881 / 0.602701634 / 0.396535485 | `1.26e-11` |

p6/h10 是 best available global-p discrete reference，不是 continuum
reference。COMSOL independent direct-solver trend center 为
`R00≈0.000752895 / R≈0.000762014 / T≈0.6027075 /
Aclosure≈0.3965305`，只用于跨软件趋势核验。

## 高阶内存与装配

| path | active rows | matrix NNZ | factor NNZ | peak | conclusion |
|---|---:|---:|---:|---:|---|
| historical full p6/h10 | 173,882 | 210,353,120 | 386,625,292 | 35.024 GiB | full-matrix control |
| post-assembly p6 Schur | 60,482 | 52,058,162 | 243,270,308 | 29.212 GiB | numerical pass；生命周期重叠 |
| assembly-time Schur + factor retain | 51,272 | 41,989,040 | 205,445,192 | 16.998 GiB | engineering positive |
| release without heap trim | 51,272 | 41,989,040 | 202,763,336 | 16.351 GiB | engineering positive |
| release + heap trim | 51,272 | 41,989,040 | 211,651,232 | 15.964 GiB | isolated resource authority |
| latest dedup/preallocated projection pair p6 | 51,272 | 41,989,040 | 202,441,352 | pair 19.977 GiB | build 102.32 s |

post-assembly prototype 降 rows 但仍保留 full matrix 和高 Schur fill，因此
memory 只下降 16.6%。最终 assembly-time path 不再分配完整矩阵；factor
release + `malloc_trim` 使 MUMPS 峰值不再与后处理叠加。latest projection
pair 相对旧 assembly-time pair 从 1202.85 s 降到 324.78 s，核心收益来自
tensor reuse 与 exact preallocation，而非放宽数值 Gate。

ordinary default 始终未修改；这些均为 opt-in research path。

## 规则几何压缩候选

| candidate | DoF / rows | matrix/factor NNZ | peak | scalar/vector + field | significant power/amplitude | decision |
|---|---:|---:|---:|---|---|---|
| global p6/h15 | 84,492 / 24,704 | 19,207,136 / 59,616,320 | 12.000 GiB pair | pass | 6/12；8/12 | controlled negative |
| fixed p5-trace/p6-interior h15 | 74,890 / 16,880 | 9,195,812 / 27,916,600 | 5.803 GiB | pass | 6/12；7/12 | controlled negative |
| p4-trace p4/p6-interior h10 | 88,994 / 21,824 | 8,184,464 / 42,888,832 | 6.072 GiB | fail | 0/12；0/12 | valid exact-sequence accuracy negative |
| p5-trace p4/p6 N62 h10 | 89,755 / 35,000 | 20,140,928 / 101,062,900 | 9.271 GiB | fail | 0/12；0/12 | non-exact-sequence negative |

global p6/h15 相对 h10 p6 达到 `2.057x` DoF 压缩。fixed h15 候选处于
65k–75k 优选区间，exact preallocation 将 mallocs 从 13,856 降至 0、
unused NNZ 从 3,498,879 降至 288,768、build 从 231.15 s 降至
61.61 s，peak 从 6.105 GiB 降至 5.803 GiB；used NNZ、factor 和物理
结果不变。两者仍不得越过 diffraction-channel Gate。

p4-trace h10 是结构合格的精度负结果；p5-trace/p4-interior 的 curl
nullity `112` 小于 expected gradient dimension `178`，缺 66 个 gradient
modes，因此 N62 不能作为第二个有效 accuracy negative。N18 共享同一错误
低空间，未运行。

## DWR、smoothness 与 classifier v3

p4/p5 same-mesh DWR 使用三个独立 Hermitian adjoint，DWR effectivity 与 1
的最大差小于 `1.7e-11`。theta=0.5 marker：

| indicator | cells | captured | R5 Jaccard |
|---|---:|---:|---:|
| strict R00 | 84 | 0.5055 | 0.6897 |
| strict R | 84 | 0.5059 | 0.6897 |
| T | 78 | 0.5160 | 0.8077 |
| relative R/T | 81 | 0.5091 | 0.7778 |
| tolerance-normalized R/T | 78 | 0.5126 | 0.8077 |
| R5 | 63 | 0.5115 | — |

normalized marker 保留 strict R00 audit，避免只优化 `R_total`。

latest p5/p6 projection record 在 252/252 cells 上得到：

| signal | min | median | max |
|---|---:|---:|---:|
| hierarchical p6/p5 physical decay | 0.16201 | 0.16289 | 0.16783 |
| coefficient decay，diagnostic only | 0.14644 | 0.14723 | 0.15164 |
| p4 projection defect | 0.03436 | 0.03448 | 0.03848 |
| p5 projection defect | 0.00655 | 0.00657 | 0.00755 |
| p5/p4 defect decay | 0.18988 | 0.19086 | 0.19644 |

classifier v3 在 periodic transitive aggregation 后给出
`p-up=102 / p-keep=150 / h-refine=0 / p-down=0`。它通过 synthetic
smooth/interface/corner/high-frequency、periodic 和 MPI2 collective
fail-fast fixtures，但仍为 `production_qualified=false`：旧 signal record
不含最新 N1E/Piola/roundtrip/hash-scope 字段，且没有独立 target
phase-resolution 与 same-patch actual h-vs-p authority。

## Lane B 与外部 controls

tetra h50 顺序代理：

| endpoint | cells | DoF / rows | NNZ | R/T/Avolume vector error | strict-R error |
|---|---:|---:|---:|---:|---:|
| base p5 | 180 | 15,405 / 15,485 | 3,726,879 | `2.2032e-2` | `1.5130e-3` |
| one-local-h p5 | 1,248 | 101,210 / 101,290 | 23,913,006 | `6.3581e-4` | `4.3764e-4` |
| fixed-mesh p6 | 1,248 | 167,784 / 167,864 | 57,609,056 | `1.0224e-4` | `5.1371e-5` |

local-h 的 vector-error gain/added DoF 较高，p-up 的 strict-R gain/added
DoF 较高；没有单一 winner。final p6 的 vector control pass，但 strict-R
ratio 为 1.421 且 DoF 超过 90k。该记录是 sequential global marginal
proxy，不是 same-patch authority。

structured hexa 没有 conforming hanging-node/transition path；tetra selected
p6 physical-reduction 又未实现。既有 h50/h37.5 refined p5 已为
101k–129k DoF，classifier 也没有 target h-refine signal。因此 Lane B
以 `stopped_by_gate_architecture_and_budget` 结束，不重复 Task035 heavy
cases。

## Hybrid 与 0.7 nm

```text
selected candidate = null
Hybrid closure = not_run_by_selected_candidate_gate
M funnel = not_run
0.7 nm PDE = not_run
predicted simultaneous peak = null
production feasibility = unknown
```

规划敏感性仍保留
`N_local,0.7=N_equiv,13.5*7173.104956*f_H`。90k/75k/70k/65k 与
`f_H=.30/.35/.40` 映射到约 139.9M–258.2M local FE DoF，但没有
accuracy credit。Task034 current Hybrid layout 的 dense multi-RHS 单组件
已远超 2 TiB；Task035b 没有 selected layout，不能把 cumulative component
envelope 冒充 simultaneous peak，也不能宣称 0.7 nm 已可行或已证明不可行。

## Scope 与交付

| item | status |
|---|---|
| fixed rectangular block research | completed with controlled negatives |
| irregular G1/G2/Phase F | `out_of_scope_by_user / not_run / not_a_completion_gate` |
| candidate ledger | 42 行 JSON/CSV，含 controls、failures 和 stopped lanes |
| negative/failure preservation | complete |
| Hybrid/resource bridge | stopped by selected-candidate Gate |
| ordinary default | unchanged |

证据索引见：

- `outcomes/reference_and_resource_target.md`
- `outcomes/high_p_memory_anatomy.md`
- `outcomes/local_hp_capability.md`
- `outcomes/regular_geometry_compression.md`
- `outcomes/negative_results.md`
- `outcomes/resource_projection_0p7nm.md`
- `outcomes/all_candidates.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/`
