# Task037-extra Review Report V8：H2A 资源硬停审阅与低于 2 GB PDE 分阶段快速恢复

## 0. 审阅身份与最终决定

```text
review                              = Task037-extra Review Report V8
working_branch                      = codex/20260806-task37-iterative-extra-development
reviewed_handoff                    = docs/task37_extra_development/response_v7.md
reviewed_outcome                    = docs/task37_extra_development/outcomes/h2_block_class_inventory.md
reviewed_H2A_raw_source             = 26bc171b35cce60b3b9197027e808f0af4d628d0
reviewed_H2A_checker_source         = d65fcfb5b55c92682c74376dbe1fbefe22766f52
H1R3_action_layer                   = ACCEPTED_AND_FROZEN_PASS
H2A_measurement                     = ACCEPTED_RESOURCE_STOP_EVIDENCE
H2A_scientific_classification       = NOT_QUALIFIED_NOT_ALGORITHM_FAIL
current_H2A_execution_path          = REJECTED_DUE_TO_LIFECYCLE_ORDERING
new_authorized_lane                 = H2A-R staged class/factor recovery
H2B                                 = CONDITIONALLY_AUTHORIZED_AFTER_H2A-R_PASS
H2C_coercive_global_solve           = CONDITIONALLY_AUTHORIZED_AFTER_H2B_PASS
H2D_fullspace_matrix_free_DtN       = CONDITIONALLY_AUTHORIZED_AFTER_H2C_PASS
H4_time_harmonic_PDE                = CONDITIONALLY_AUTHORIZED_AFTER_H2C_AND_H2D_PASS
full_PDE_memory_hard_target         = process-tree RSS < 2,000,000,000 B
swap                                = strictly_zero
outer_space                         = uncondensed_fullspace_only
static_condensed_fallback           = forbidden
bounded_codex_autonomy              = AUTHORIZED_AND_EXPANDED
create_new_branch                   = forbidden
pull_request                        = forbidden
merge_to_master                     = permanently_not_planned
ordinary_default_change             = forbidden
```

本审阅接受最新 H2A 的资源负证据，但不接受把它解释为局部 block smoother 或 full-space
PDE 路线的科学失败。H2A 在完成 mesh、p6 full-space、Floquet MPC 后，停在两个 p6
双线性 form 的 FFCx/GCC JIT；尚未进行 class key discovery、局部 tensor tabulation、LU、
smoother contraction 或 PDE。因此当前只能得出：

> **现有 runner 把生产 mesh/space/MPC 与高内存 p6 bilinear JIT 放在同一进程、同一阶段，
> 且在零成本的 class discovery 之前先编译 form，导致 1.1 GB preflight Gate 被触发。**

这是一项执行顺序和生命周期设计问题。它不推翻 H1R3 已证明的 full-space rank-one action，
也没有重复静态凝聚 B2/B4。后续必须继续使用未静态凝聚的完整 p6 Nédélec 空间。

为尽快得到第一条 `<2 GB` PDE，本审阅授权 Codex 在冻结物理和内存上限内自行处理 JIT
staging、cache、class key、MPC patch、factor 文件、runner、watchdog、MPI、KSP 和对象
生命周期问题；不再要求每遇到一个可定位执行缺陷就等待新审阅。但每一阶段必须保留
raw 失败证据，并遵守本报告的顺序 Gate 和有界候选集合。

---

# 1. 最新 H2A 结果审阅

## 1.1 正式结果

| 项目 | 最新 H2A v5 实测 |
|---|---:|
| scope | p6/h10、MPI1、full-space、coercive proxy inventory |
| cells / global rows | `252 / 173802` |
| mesh build | 完成 |
| function space | 完成 |
| Floquet MPC | 完成 |
| 最后 marker | `form_compile_started` |
| form compile ready | 未出现 |
| class discovery | 未运行 |
| class/factor count | unavailable |
| factor payload | unavailable |
| smoother/PDE | 未运行 |
| process-tree peak | `1,153,503,232 B` |
| H2A 原 Gate | `1,100,000,000 B` |
| swap | `0 B` |
| elapsed | `26.986158804968 s` |
| classification | `GATE_FAILED_RESOURCE / NOT_QUALIFIED` |

隔离编译同一 `54,429,950 B` C 文件时，`-O0 -g0` 的编译器最大 RSS 为
`674,521,088 B`，耗时约 `7.91 s`。该诊断不能替代正式 H2A，但它支持一个明确的
工程判断：主要额外峰值来自编译器与已存活 Python/DOLFINx/MPC 对象的同时常驻，而不是
已经形成了 400 MB block factors。

## 1.2 当前 runner 的错误顺序

当前正式路径是：

```text
mesh
-> full-space p6 function space
-> Floquet MPC
-> compile curl bilinear form
-> compile mass bilinear form
-> class key discovery
-> representative tensors
-> factors
```

其中 class key discovery 不需要 curl/mass form，也不需要 dense local tensor，却被放在
最昂贵的 JIT 之后。因此 H2A 在尚不知道“到底有多少 class、是否值得构建 factors”之前，
已经承担了最大编译峰值。

V8 冻结的新顺序为：

```text
mesh
-> full-space p6 function space
-> Floquet MPC
-> class key discovery only
-> class/factor memory upper-bound decision
-> isolated form JIT staging and process exit
-> fresh factor/inventory process using JIT cache
```

## 1.3 1.153 GB 不等于最终 PDE 失败

最终硬目标仍为：

```math
M_{PDE,peak} < 2,000,000,000\ \mathrm{B}.
```

本次 1.153 GB 是冷 JIT setup 的 process-tree peak，仍低于最终 2 GB ceiling。失败来自
此前人为设置的 `1.1e9 B` H2A preflight，而不是 2 GB 目标。不能简单把 H2A Gate 改成
2 GB 后在同一进程继续堆叠所有对象；正确做法是把编译与在线 solve 分阶段，使编译器退出
后再建立和加载 factors。

因此 V8 对资源口径作如下区分：

```text
offline/staging subprocess formal peak < 1,800,000,000 B
online PDE predicted live set         <= 1,700,000,000 B
online PDE warning                    = 1,750,000,000 B
online PDE controlled termination     = 1,950,000,000 B
online PDE formal completed peak      < 2,000,000,000 B
all stages swap                       = 0
```

离线编译和 factor 生成可以更慢，但不得与 online KSP 同时常驻，也不得借磁盘反复流式读取
hot factors。factor 文件只允许在 solve 开始前加载一次并在 RAM 中重复使用。

---

# 2. Full-space 身份必须永久冻结

后续 H2/H4 不得退回原 Task37 的 condensed trace 系统。每份 worker summary、compact
record 和 checker 必须显式验证：

```text
fine_space                         = uncondensed_fullspace
fullspace_global_rows_h10          = 173802
condensation                       = false
global_condensed_schur_materialized = false
cell_schur_matrix_nnz              = 0
slab_matrix_nnz                    = 0
static_condensed_operator_used     = false
trace_slab_pc_used                 = false
B2_B4_local_krylov_used            = false
fullspace_patch_pc_used            = true
interior_recovery_required         = false
```

当前全局 exact operator 的 volume 部分继续使用已资格化的 rank-one full-space action：

```math
A_{vol}u
=
K_{curl}u-k_0^2M_{\epsilon}u.
```

局部 factors 只是 full-space element/patch smoother 的有界辅助数据，不能成为 trace Schur
或 16-slab ILU 的新包装。

---

# 3. H2A-R0：先做无 form 的 exact class discovery

## 3.1 固定工作

重排 `run_task037_extra_h2.py`，在 `_proxy_forms()` 前调用现有 class discovery。第一轮
只运行：

```text
p6/h10 MPI1
mesh + function space + Floquet MPC + class key discovery
no form JIT
no tensor tabulation
no factorization
```

必须输出：

- exact topological/class key count；
- 每个 class 的 cell 数、material、width、orientation、constraint pattern hash；
- constrained patch 的 unique reduced-row count；
- raw 882×882 factor 的无 dedup 上界；
- transformed constrained patch factor 的上界；
- class key 是否包含 absolute global row/owner 等错误成分；
- p6/h10 process-tree peak 与 swap。

随后在同一代码版本上运行轻量 refinement identity：

```text
p2/h10
p2/h5
```

这两个 case 只做 key discovery，不编译 p6 form，不构建 factor。

## 3.2 Gate

```text
class keys deterministic
no absolute global/local row or owner in class key
p6 topological exact class count <= 64
predicted one-factor-per-class upper bound reported
p2 h10->h5 class growth strictly sublinear to cell growth
process-tree peak < 1,000,000,000 B
swap = 0
```

`64` 是 metadata/class-key 上限，不是 factor 上限。进入 factor stage 后仍要求：

```text
unique retained numeric factor count <= 32
factor values+pivots+metadata <= 400,000,000 B
```

若 key count 大于 64，先检查 key 是否错误包含 cell ID、global row、owner、absolute
coordinate 或重复 phase。只允许修复这种由证据证明的过度区分；禁止近似合并不同物理类。

---

# 4. H2A-R1：隔离 JIT 预热和 cache 身份

## 4.1 单独编译进程

使用一个独立 worker，仅执行：

```text
production p6 element/form identity
compile curl form
compile mass form
write cache/artifact identity
exit process
```

优先在构建 Floquet MPC 之前完成。编译使用与正式 factor builder 完全相同的 UFL、element、
quadrature、scalar ABI、FFCx 和 compiler flags。必须记录：

- UFL/FFCx signature；
- generated C/object/shared-library SHA；
- cache path；
- compile child PID 和 process-tree peak；
- source SHA、Python/PETSc/FFCx/Basix/compiler 版本；
- compile ready marker；
- worker 退出后 OS 已回收编译器和 mesh/space 内存。

资源 Gate：

```text
completion <= 3600 s
process-tree peak < 1,800,000,000 B
swap = 0
source clean/stable
```

## 4.2 正式 factor worker 必须命中 cache

新的 inventory/factor worker 在 fresh process 中重建 mesh/space/MPC，先读 R0 class
manifest，然后加载已编译 kernel。必须证明：

```text
form JIT cache hit = true
compiler child process count = 0
C source regeneration = false
cache signature/SHA matches R1 manifest
```

若发生 cache miss，不得继续 factorization；Codex可以自行修复 cache key、stage order、
环境变量或 cache manifest，再重跑本阶段。

---

# 5. H2A-R2：逐 class factor 构建、精确 dedup 与冷文件

## 5.1 主路径：缓存后的 bilinear cell tensor

对每个 representative class 顺序执行：

```text
load cached curl/mass kernels
-> tabulate one representative local tensor
-> apply Basix/DOLFINx orientation
-> build constrained patch matrix
-> exact numeric hash/dedup
-> pivoted complex128 LU
-> release original curl/mass/proxy tensors
-> serialize retained LU+pivots+class map
```

同一时刻最多保留：

- 已接受的 unique factors；
- 当前一个 class 的 curl、mass、proxy 和 LU workspace；
- class/cell metadata。

禁止同时保留所有 class 的原始 curl/mass tensors。

## 5.2 约束后的局部块必须正确

对没有 Floquet slave 的 interior cell，局部块为普通 full-space proxy：

```math
B_c=R_cB_0R_c^T.
```

对有 Floquet 约束的 cell，不能直接把未经约束的 `882×882` factor 用在 reduced residual。
必须构造局部 expansion/restriction `C_c`，并 factor：

```math
\widetilde B_c
=
C_c^H B_c C_c.
```

这里 `C_c` 的列集合必须包含该 cell 物理 DoF 所依赖的 unique independent/master rows；
phase、orientation 和 corner constraint 只能施加一次。必须先在 p2/p3 fixture 验证：

```math
\frac{\|\widetilde B_c v-C_c^HB_cC_cv\|_2}
{\|C_c^HB_cC_cv\|_2}
\le10^{-11}.
```

并在 p6 至少验证一个 interior class、一个 x/y periodic class 和一个 corner class。若当前
cache 仍只 factor raw unconstrained tensor，则 H2A inventory 可以保留为诊断，但不得进入
H2B smoother。

## 5.3 factor manifest

factor artifact 可以放在 ignored 目录，tracked compact manifest 必须记录：

```text
class key SHA
numeric matrix SHA
factor values SHA
pivot SHA
shape/dtype/bytes
source/config/form/cache identity
constraint-pattern identity
factorization residual
finite/deterministic
```

online solver 加载时必须逐项验证。禁止 pickle 任意 Python object；只允许明确 schema 的
NumPy 数组和 JSON manifest。

## 5.4 Gate

```text
unique numeric factor count <= 32
retained factor+metadata <= 400,000,000 B
no per-cell factor
no slab factor
factorization/apply finite and deterministic
representative solve residual <= 1e-10
fresh factor-worker peak < 1,750,000,000 B
swap = 0
```

factor builder 可以耗时较长；只要每个 class 有进度 marker、RSS 在上限内并持续推进，
不以短 timeout 否定路线。

---

# 6. 唯一允许的 H2A backend fallback：rank-one column reconstruction

若 R1 cache 无法稳定复用，或缓存后的 bilinear form加载仍使 fresh factor worker超过
`1.75e9 B`，允许一次且仅一次替代 backend：复用已资格化的 direct rank-one action，在
single-cell canonical fixture 上逐列生成局部块。

对 local basis vector `e_j`：

```math
B_c[:,j]=\operatorname{Action}_c(e_j),
\qquad j=1,\ldots,n_c.
```

该路径可以更慢，但不得生成 p6 bilinear `882×882` FFCx tensor kernel。必须：

- p2/p3 与 dense cell authority 误差 `<=1e-11`；
- p6 interior representative 与缓存 bilinear authority（若可用）或 H1R 单元 authority闭合；
- 一次只保留最终 local block和 rank-one workspace；
- 每个 class独立完成、factor并释放；
- 仍然构造 `C_c^H B_c C_c`；
- factor/payload Gate不变。

这是最终有界 fallback，不允许继续开发第三、第四个 local-block backend。

---

# 7. H2B：full-space constrained block smoother

仅在 H2A-R 正式通过后进入。

## 7.1 Primary smoother

固定使用：

```text
exact-class-reused constrained cell blocks
+ multiplicity/partition-of-unity weights
+ deterministic cell coloring
+ one forward multiplicative sweep
+ one backward multiplicative sweep
```

每次 block correction 后用 exact full-space matrix-free coercive action更新 residual。禁止：

- 每个 cell 一份 factor；
- 16 个 trace slab factors；
- B2/B4 的 2--90 步 local Krylov；
- static-condensed Schur；
- 根据结果无界扫描 coloring、sweep 数或 damping。

coercive proxy 冻结为：

```math
B_0
=
K_{curl}+k_0^2M_{|\epsilon|}.
```

## 7.2 residual sources

至少测量：

```text
gradient-dominated
curl-dominated
mixed
checkerboard/high-frequency
one physical-RHS-like source
```

定义：

```math
\rho_s(r)
=
\frac{\|r-B_0M_s^{-1}r\|_2}{\|r\|_2}.
```

Gate：

```text
all results finite/deterministic
checkerboard/high-frequency rho <= 0.70
mixed rho <= 0.85
gradient/curl/physical each rho <= 1.00
smoother retained factors+work <= 500,000,000 B
one forward+backward smoother apply <= 30 * one volume action wall
completed peak < 1,450,000,000 B
swap = 0
```

## 7.3 单一 patch fallback

若 cell smoother finite 且 high-frequency/mixed 的 rho 落在 `(Gate, 1.20]`，说明有局部
正信号但跨 cell coupling不足，Codex可自行尝试一次 **two-cell face-pair patch**：

- 只跨共享 face配对两个相邻 cells；
- exact class reuse；
- constrained patch `C_p^HB_pC_p`；
- 总 factor+metadata `<=550,000,000 B`；
- 仍只一 forward+backward sweep。

若 primary 出现 nonfinite、rho `>1.20`，或 face-pair fallback仍未通过 Gate，停止本 fast
track，不再扩展 edge-star、vertex-star 或更多 patch类型；提交结果供后续 geometric MG审阅。

---

# 8. H2C：75D full-space wave coarse 与 coercive global solve

只在 H2B 通过后进入。

## 8.1 coarse basis

构造固定 `75D` full-space wave basis `Z`。它必须直接位于未凝聚 p6 Nédélec空间，不得
先构造 trace basis再静态恢复。检查：

```text
full-space rows = 173802
basis rank = 75
MPC/Floquet identity closed
finite/deterministic
retained Z <= 240,000,000 B
retained AZ = 0 B after setup
```

coarse matrix逐列构造：

```math
E=Z^HB_0Z.
```

每一列 `B_0z_j` 用完即释放，只保留 `Z`、`E` 和小 factor。报告 condition estimate；
若 numerical rank小于75，禁止用零列或随机列补齐。

## 8.2 two-level correction

固定顺序：

```text
block pre-sweep
-> exact residual
-> 75D coarse correction
-> exact residual
-> block post-sweep
```

先测 one-apply contraction，再进行 coercive global solve。

## 8.3 coercive FGMRES

```text
operator = B0
right FGMRES restart = 20
max iterations = 500
relative true residual target = 1e-8
```

Gate：

```text
converged true residual <= 1e-8
reported/true residual agreement
iterations <= 500
no long plateau over final 100 iterations
completed peak < 1,650,000,000 B
swap = 0
```

若 restart 20 收敛但明显受 restart影响，且 predicted live set `<=1.70e9 B`，允许一次
restart 30 对照；不得使用 restart 90。

---

# 9. H2D：full-space matrix-free DtN

只在 coercive global solve通过后进入。DtN 必须作用于 full-space边界 DoFs，不得调用
condensed trace outer operator。固定 80-mode authority，先做 action/recovery identity：

```text
p6/h10 MPI1
p6/h10 MPI2
3 deterministic boundary sources
1 physical source
```

要求：

```text
explicit dense C/D materialized = 0
relative action/recovery error <= 1e-11
MPI2 vs MPI1 canonical identity <= 1e-12
retained DtN arrays/work <= 150,000,000 B
no MatPython getInfo telemetry failure
```

允许 Codex自行修复 MatPython/AIJ stats分流、boundary packing、remote master、mode
ownership和生命周期问题，只要物理 mode set、normalization和80-mode authority不变。

---

# 10. H4：原始时谐 PDE 快速漏斗

H2C 与 H2D 都通过后，Codex可自动进入 H4，无需再次等待审阅。

## 10.1 exact equation

```math
A
=
K_{curl}-k_0^2M_{\epsilon}+A_{DtN}.
```

局部辅助 block使用：

```math
B_{\beta}
=
K_{curl}-k_0^2M_{\epsilon}
+i\beta k_0^2M_{|\epsilon|}.
```

只允许：

```text
beta = 1.0  primary
beta = 0.5  one bounded fallback
```

不得扫描更多 shift。

## 10.2 KSP 与内存

```text
right FGMRES
restart = 20 primary
restart = 30 only if live-set <=1.70e9 B and evidence supports it
predicted simultaneous live set <=1,700,000,000 B
warning = 1,750,000,000 B
controlled termination = 1,950,000,000 B
formal completed peak <2,000,000,000 B
swap = 0
```

任何 screen 前必须列出真实 bytes：action、factors、Z、coarse factor、KSP basis、DtN、
mesh/MPC和work vectors。预测超过1.70 GB则不启动，先释放reference/canonical/setup对象或
降低restart到20；禁止降低p、增大h或减少DtN mode。

## 10.3 20/100/200-step漏斗

最低趋势 Gate：

| iteration | true relative residual |
|---:|---:|
| 20 | `<=0.60` |
| 100 | `<=0.20` |
| 200 | `<=0.08` |

并要求：

```text
iteration 150->200 residual improvement >=15%
reported/true residual agree
all values finite
predicted full iterations <=5000
completed peak <2GB
swap=0
```

最多允许：

1. `beta=1.0` primary；
2. `beta=0.5` fallback；
3. 若 residual 已明显下降但存在单一可辨识慢子空间，增加固定16个 harmonic Ritz vectors。

Ritz augmentation额外 retained payload必须 `<=60,000,000 B`。禁止更多向量数或无界
recycling扫描。

## 10.4 full solve

```text
true residual target = 1e-6
max iterations = 5000
timeout = 12 hours
process-tree peak <2,000,000,000 B
swap = 0
```

只要 residual持续下降、内存安全且预计迭代数不超过5000，允许较长时间运行。正式 full
最多两次：第一次正常运行；第二次仅用于修复有明确 raw 证据的代码/执行缺陷。

求解收敛后必须先销毁：

```text
KSP/FGMRES basis
block/patch factors
wave basis/coarse objects
DtN work vectors
reference/checker-only objects
```

再进入 field/RTA。必要时 solve 和 postprocess采用顺序 subprocess，避免阶段峰值叠加。

## 10.5 physics Gate

最终必须同时通过：

```text
condensed/reduced representation consistency where applicable
full-space explicit true residual <=1e-6
R/T/A and volume absorption closure
12/12 significant channel powers
12/12 boundary complex amplitudes
canonical full field identity
comparison with frozen p6/h10 direct authority
```

当前 full-space solve本身包含 interior DoFs，不允许再出现 `trace solve -> interior recovery`
作为主路径。只有MPC展开、field export和后处理，不做静态凝聚恢复。

---

# 11. Codex 受控自主权

Codex可在不等待新审阅的情况下自行：

- 重排 class discovery/JIT/factor阶段；
- 创建并验证独立 JIT cache worker；
- 修复 cache key、FFCx options和cache hit；
- 实现 rank-one column fallback；
- 修复 constrained patch `C_c`、MPC remote master和phase；
- 做 exact numeric dedup、factor序列化和manifest验证；
- 修复coloring、weights、Vec/KSP/MatPython生命周期；
- 修复DtN action、telemetry和MPI identity；
- 在本报告允许的cell/face-pair、beta、restart和Ritz集合内选择；
- 延长setup/factor wall time，只要内存、进度和总上限不变；
- 修复runner/schema/checker/path/hash和明确的单一代码缺陷；
- Gate通过后自动进入下一顺序阶段。

不得自行：

- 新建分支或PR；
- 合并/修改master或ordinary default；
- 改p、h、geometry、material、incidence、polarization、DtN mode set或tolerance；
- 放宽2GB、swap或数值Gate；
- 恢复global assembled matrix、static condensation或16-slab factors；
- 重开LOR-HX；
- 开发第三种以上block backend或第二种以上patch fallback；
- 无界扫描shift、restart、patch、coarse dimension或Ritz数量；
- 未收敛时生成official R/T/A。

## 11.1 formal run预算

launch-only/fixture不计入 heavy。正式 heavy上限：

```text
H2A-R0 key discovery              <=2
H2A-R1 JIT staging                <=2
H2A-R2 factor inventory           <=3 including rank-one fallback
H2B smoother                      <=3 including face-pair fallback
H2C coercive global solve         <=2
H2D DtN identity                  <=2
H4 PDE screens                    <=3
H4 full                           <=2
```

每次失败必须保留raw并说明唯一修复根因；禁止原样重跑。

---

# 12. Required outputs

实际执行到的阶段写入：

```text
docs/task37_extra_development/outcomes/h2a_class_discovery.md
docs/task37_extra_development/outcomes/h2a_staged_factor_cache.md
docs/task37_extra_development/outcomes/h2b_block_smoother.md
docs/task37_extra_development/outcomes/h2c_coercive_global_solve.md
docs/task37_extra_development/outcomes/h2d_fullspace_dtn.md
docs/task37_extra_development/outcomes/h4_time_harmonic_pde.md
```

tracked compact records：

```text
benchmarks/cases/101_task37_extra_development/records/h2a_class_discovery.json
benchmarks/cases/101_task37_extra_development/records/h2a_staged_factor_cache.json
benchmarks/cases/101_task37_extra_development/records/h2b_block_smoother.json
benchmarks/cases/101_task37_extra_development/records/h2c_coercive_global_solve.json
benchmarks/cases/101_task37_extra_development/records/h2d_fullspace_dtn.json
benchmarks/cases/101_task37_extra_development/records/h4_time_harmonic_pde.json
```

只创建实际运行的文件；后续阶段因Gate未运行时，不创建空假record。

consolidated handoff：

```text
docs/task37_extra_development/response_v8.md
```

`response_v7.md`和原H2A负证据保持不变，不覆盖、不删除。

---

# 13. 最终裁决

最新H2A没有给出“full-space block PC失败”的证据，只证明现有冷JIT生命周期不满足旧的
1.1GB preflight。鉴于：

- full-space action已在h10/h5、MPI1/MPI2通过；
- H2A实际峰值1.153GB仍低于最终2GB；
- form compile发生在class discovery之前；
- 编译器可以独立staging并退出；
- 用户接受较长setup时间，但坚持低内存；

V8决定继续full-space路线，不退回condensed factor-free，也不立即转向更重的geometric
multigrid。下一步是先取得class count和真实factor bytes，再用分阶段factor cache进入
constrained block smoother。

只有当H2A-R/H2B证明局部block本身无收缩能力，或在线live-set无法低于2GB时，才关闭
本PDE fast track并重新审阅geometric multigrid。当前最短可信路径仍是：

```text
class discovery first
-> staged factor cache
-> constrained block smoother
-> 75D full-space wave coarse
-> coercive global solve
-> full-space matrix-free DtN
-> time-harmonic PDE screen/full
```
