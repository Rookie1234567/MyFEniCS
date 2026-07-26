# Task035b Review V3：Hybrid 局部静态凝聚 H0/H1-A

## 结论

```text
source = 148729c28c3f9aefec8e5646cc644c5c4e2332da
formal_MPI = 8
H0_static_condensation_implementation = qualified
H1_A = controlled_negative
H1_B = not_run_by_review_prerequisite
H1_C = not_run_after_h1a_numerical_gate
H1_D = not_run_after_h1a_numerical_gate
adaptive_Hybrid_A1_to_A4 = not_run_after_h1a_numerical_gate
ordinary_default_changed = false
```

H0 已把 assembly-time cell-interior 静态凝聚接入 Task032/033 Hybrid。
消元只作用于上下局部三维 FEM 端区；外部 DtN 辅助量、内部 QEP 模态振幅
和 Hybrid 接口切向 trace 均保留。被消去的 interior 对 external/internal
modal coupling、右端项和求解后完整场恢复的贡献通过局部 Schur 精确回填，
没有先组装完整局部 p2 矩阵再置零。

H1-A 的代数结果是正面的：standard 与 static 的 Full3D、Hybrid
都达到 12/12 功率和 12/12 复振幅等价，恢复后 interior residual 也通过。
但是，同一 p2/h5 离散上的 static Full3D 与 static Hybrid 只达到
Task033 相对 `1e-3` 口径的 **3/12 powers + 2/12 amplitudes**；按
Task035b reference-v1 冻结 absolute audit 则为 **2/12 + 2/12**。
M120 增至 M160 后结果几乎不变，因此不能归因于 M 截断。Review V3
规定 H1-B 只有在 H1-A 全部通过后才运行，故本批次在真实 numerical Gate
处停止，不启动 p2/h3、高阶点或 h13 adaptive Hybrid。

## H0 算法边界

```text
local 3D cell matrix
  -> exact eliminate cell-interior DoFs
  -> retain periodic-independent exterior/interface trace
  -> retain external DtN auxiliary rows
  -> apply left/right Schur corrections to modal coupling
  -> solve modal-Schur or augmented Hybrid system
  -> stream recovered trace and cell-interior field
  -> full explicit residual and eliminated-equation audit
```

| 项目 | 实际实现 | 边界 |
|---|---|---|
| local 3D FEM | bottom/top 分别 assembly-time static condensed | 只支持已资格化 axis-aligned affine hexa |
| external coupling | 对保留 trace 与被消去 interior 同时做 Schur 修正 | DtN auxiliary rows 不消去 |
| internal modal coupling | 对 matching trace 两侧做 left/right condensation | modal amplitudes 不作为 cell interior |
| primary system | augmented 与 memory-minimal modal-Schur 保持代数 identity | 不改变 QEP、M 或 matching-trace 定义 |
| recovery | streaming 恢复完整局部场 | 不保留 full global matrix 或 `N_FE × M` payload |
| residual | full operator 与 eliminated interior equation 均复核 | 低 reduced residual 不能替代 |
| public behavior | opt-in `assembly_time_static_condensed` | ordinary default 仍为 `standard_full` |

实现与资格化提交：

- `e3122b4424d2d32b1668f7044e7e2991a4d33f8f`：Hybrid 局部静态凝聚；
- `4c4acc795959f99ae936c7f3a847572e079b9902`：H1 resource shard；
- `148729c28c3f9aefec8e5646cc644c5c4e2332da`：fresh static Full3D anchor Gate。

## H1-A 四路身份

| 路径 | backend | FE/rows | matrix NNZ | factor NNZ | peak | residual | R / T / Aclosure |
|---|---|---:|---:|---:|---:|---:|---|
| Full3D standard | `standard_full` | 44,698 / 44,778 | 4,896,156 | 31,053,132 | 2.960 GiB | `9.73e-12` historical anchor | `0.0890216029363 / 0.442588278657 / 0.468390118407` |
| Full3D static | `assembly_time_static_condensed` | 44,698 / 30,800 | 3,229,040 | 26,995,728 | 2.763 GiB | `8.21e-12` | `0.0890216029363 / 0.442588278657 / 0.468390118407` |
| Hybrid standard M160 | local FE 6,826/side | 14,052 total | 1,454,248 pair | 6,390,216 pair | 3.285 GiB | `2.55e-12` historical anchor | `0.0890210691 / 0.4425867427 / 0.4683921882` |
| Hybrid static M160 | local full FE 6,826/side；4,800 active trace/side | 10,000 total | 976,400 pair | 5,986,184 pair | 3.308 GiB | `3.45e-12` | `0.0890210691063 / 0.442586742743 / 0.468392188151` |

static local system 每侧为 `4,800 trace + 40 external auxiliary = 4,840`
rows；M160 的内部模态为 320 rows，故 H2 的 total-row inventory 是
`2 × 4,840 + 320 = 10,000`。Full3D-equivalent DoF 仍为 44,698；
不能把 active trace rows 冒充原有限元空间 DoF。

## 静态凝聚等价性与 M 漏斗

| 比较 | powers | complex amplitudes | 最大相对差 | 结论 |
|---|---:|---:|---:|---|
| Full3D standard ↔ static | 12/12 | 12/12 | `1.97e-10 / 1.76e-10` | static Full3D exact-equivalence pass |
| Hybrid standard M120 ↔ static M120 | 12/12 | 12/12 | `2.61e-9 / 1.33e-9` | static Hybrid exact-equivalence pass |
| Hybrid standard M160 ↔ static M160 | 12/12 | 12/12 | `1.06e-9 / 6.84e-10` | static Hybrid exact-equivalence pass |
| static Hybrid M120 ↔ M160 | 12/12 | 12/12 | `3.40e-10 / 2.79e-10` | M funnel 已收敛；无 M240 信号 |
| static Full3D ↔ static Hybrid M120 | 3/12 | 2/12 | `0.629 / 0.594` | H1-A fail |
| static Full3D ↔ static Hybrid M160 | 3/12 | 2/12 | `0.629 / 0.594` | H1-A fail；M 增大不修复 |

上表前四行的等价计数使用同一 p/h/M 下的 Task033 相对 `1e-3` 口径。
后两行另外用 Task035b reference-v1 的 unchanged-v0 absolute tolerance
做 strict audit 时为 2/12 powers + 2/12 amplitudes；两个口径都失败，
且都没有放宽。

## M160 的 12 通道实际差值

`ΔP` 为 static Full3D 与 static Hybrid M160 的功率绝对差，
`tol(P)` 为冻结 unchanged-v0 absolute tolerance；`Δa` 是复振幅二维
欧氏差，`tol(a)` 是对应冻结限值。`T(-7,0)` power 在相对 `1e-3`
口径通过，但在 strict absolute audit 失败；只有零级在两种口径都通过。

| channel | Full3D P | Hybrid P | ΔP / tol(P) | Δa / tol(a) | relative `1e-3` P/A |
|---|---:|---:|---:|---:|---|
| T(-7,0) | `6.576075e-6` | `6.573404e-6` | `2.672e-9 / 2.159e-9` | `1.556e-5 / 1.217e-5` | pass / fail |
| T(-5,0) | `7.173940e-8` | `1.667074e-7` | `9.497e-8 / 3.891e-10` | `8.734e-5 / 1.281e-6` | fail / fail |
| T(-4,0) | `5.351330e-7` | `3.172633e-7` | `2.179e-7 / 5.251e-10` | `1.344e-4 / 2.542e-6` | fail / fail |
| T(-2,0) | `1.008643e-6` | `4.723171e-7` | `5.363e-7 / 4.651e-9` | `2.030e-4 / 4.581e-6` | fail / fail |
| T(-1,0) | `3.839972e-6` | `5.146400e-6` | `1.306e-6 / 1.114e-7` | `1.890e-4 / 1.273e-5` | fail / fail |
| T(0,0) | `0.4425762354` | `0.4425740572` | `2.178e-6 / 2.176e-4` | `1.473e-5 / 6.780e-3` | pass / pass |
| R(-7,0) | `2.241059e-6` | `2.232991e-6` | `8.068e-9 / 1.249e-9` | `4.292e-6 / 7.995e-7` | fail / fail |
| R(-5,0) | `1.270116e-7` | `1.984830e-7` | `7.147e-8 / 1.194e-9` | `4.540e-5 / 1.113e-6` | fail / fail |
| R(-4,0) | `2.208844e-7` | `9.446546e-8` | `1.264e-7 / 1.086e-9` | `6.887e-5 / 1.882e-6` | fail / fail |
| R(-2,0) | `1.920773e-7` | `7.121444e-8` | `1.209e-7 / 1.242e-9` | `1.146e-4 / 3.186e-6` | fail / fail |
| R(-1,0) | `5.779799e-6` | `6.647511e-6` | `8.677e-7 / 5.112e-8` | `1.027e-4 / 7.413e-6` | fail / fail |
| R(0,0) | `0.08901303594` | `0.08901181967` | `1.216e-6 / 3.195e-5` | `6.364e-6 / 8.330e-4` | pass / pass |

完整 Full3D/Hybrid complex amplitudes、每项相对误差和冻结 tolerance 均保存在
compact JSON，不由功率反推。

## 场、接口和恢复 Gate

| metric | M160 static Hybrid | Gate |
|---|---:|---|
| primary true relative residual | `3.450e-12` | pass |
| bottom/top full-operator residual | `1.782e-12 / 3.868e-12` | pass |
| bottom/top eliminated-interior max residual | `5.350e-14 / 6.920e-14` | pass |
| interface E relative L2 bottom/top | `1.664e-7 / 2.476e-7` | pass |
| interface H relative L2 bottom/top | `7.417e-3 / 6.732e-3` | pass |
| middle-plane E/H relative L2 | `2.880e-4 / 8.792e-4` | pass |

低 residual、总 R/T/A 和场范数通过，仍不能覆盖 9 个显著功率与 10 个
显著复振幅的相对 Gate 失败。这正是 Review V3 要求逐通道 Gate 的原因。

## 资源结果

### Full3D standard → static

| metric | standard | static | change |
|---|---:|---:|---:|
| active rows | 44,778 | 30,800 | -31.22% |
| matrix NNZ | 4,896,156 | 3,229,040 | -34.05% |
| factor NNZ | 31,053,132 | 26,995,728 | -13.07% |
| process-tree peak | 2.960 GiB | 2.763 GiB | -6.65% |

这是低阶 Full3D 上的工程正结果，并再次证明静态凝聚的等价性。

### Hybrid standard → static，M160

| metric | standard | static | change |
|---|---:|---:|---:|
| total rows | 14,052 | 10,000 | -28.84% |
| local matrix NNZ pair | 1,454,248 | 976,400 | -32.86% |
| factor NNZ pair | 6,390,216 | 5,986,184 | -6.32% |
| factor fill | 4.394 | 6.131 | +39.52% |
| process-tree peak | 3.285 GiB | 3.308 GiB | +0.71% |
| total time | 96.28 s | 186.36 s | +93.56% |
| internal modal coupling | 11.72 s | 110.62 s | +843.7% |

因此 H1-A 的 Hybrid 资源信号是 `mixed_negative`：rows 和 assembled NNZ
下降，但 fill 增长，factor 只下降 6.3%，峰值没有下降，总时间接近翻倍。
主瓶颈不是 local FEM assembly 或 MUMPS solve，而是当前 static
left/right modal correction 的 110.6 s internal coupling。该结果不允许
写成“降 DoF 后内存和时间成功”。

## 决策与证据

| item | status | 原因 |
|---|---|---|
| H0 static Hybrid capability | `qualified_opt_in_research_backend` | standard/static 逐通道等价、true residual 和 recovery pass |
| H1-A p2/h5 | `controlled_negative` | static Full3D ↔ Hybrid channel Gate fail |
| H1-B p2/h3 | `not_run_by_review_prerequisite` | Review V3 明确要求 H1-A 全部通过 |
| H1-C p3/h7.5 | `not_run_after_h1a_numerical_gate` | 不用更重模型覆盖低阶闭合失败 |
| H1-D h13 seed | `not_run_after_h1a_numerical_gate` | 不能把 inherited Hybrid error 带入 under-resolved seed |
| A1–A4 adaptive Hybrid | `not_run_after_h1a_numerical_gate` | Gate A 尚未建立 |

权威 compact record：

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/hybrid_static_condensation_h1a_mpi8_v1.json`

raw heavy records 位于 ignored artifact 目录，并以 SHA256 绑定在 compact
record 中；两次只在启动前失败的 source-anchor 探针保持原样，不覆盖、不删
除，也不冒充 PDE negative。
