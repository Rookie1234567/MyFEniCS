# Task037-extra Consolidated Response V1：G0--G2 权威、负结果与停止边界

## 0. 文档身份

```text
document                      = consolidated response_v1
working_branch                 = codex/20260806-task37-iterative-extra-development
covered_stages                 = G0, G1, G2.2--G2.6
supersedes_content_of          = historical response_v1--response_v5
review_authority               = review_report_v1.md
G2_final_classification        = G2_FAIL
G3_status                      = not_started_and_prohibited_by_G2_FAIL
production_promotion           = no
merge_to_master                = no
ordinary_default_change        = no
```

本文件把此前按阶段拆分的五份 response 合并为一个当前权威。历史阶段文件在 Git
历史中保留；工作树中的 `response_v2.md`--`response_v5.md` 仅保留归档指针，不再作为
数值结论来源。

Review V1 已核对 G2.6 正式运行、raw/compact evidence、测试和派生 Gate，接受实现与
负结果证据，裁决 `G2_FAIL`。这里的“证据通过审阅”不表示 LOR-HX 性能通过。

---

## 1. 总结

Task037-extra 已得到以下确定结论：

1. 同机 M3a MPI1 full authority 成功复现：352 iterations、4.7673 GiB、全部残差、
   R/T/A、体吸收和 12+12 通道通过。
2. residual snapshot 与逐 slab contraction 诊断可以按 canonical active-row identity 输出；
   但单个 stationary contraction 不能替代完整 FGMRES 收敛判断。
3. exact factor reuse 在当前 PETSc factor object 上无法完整验证 ordering/value identity，
   因而未共享任何 factor。
4. 当前 PETSc global scalar ABI 固定为 complex128，不能仅把局部 PETSc ILU factor
   安全存为 complex64。
5. slab full-space 与 trace Schur 的代数等价关系通过约 `1e-15` 的 action identity。
6. plain full-space p6 ILU 的 retained payload 是当前 trace ILU 的 5.3166 倍，局部
   correction 也更差，路线关闭。
7. p6-to-LOR transfer 的拓扑、Floquet、orientation、determinism 和 adjoint identity 通过。
8. 当前 slab LOR-HX hierarchy 的 retained payload 为 2.913 GiB，是一个 trace ILU 的
   25.636 倍；memory signal 失败。
9. LOR-HX 1V/2V 在三个 residual source 上将 exact shifted Schur residual 放大约
   `1e6--1e16`；minimum、strong 与 apply-time overall Gate 全部失败。
10. G2 整体正式分类为 `G2_FAIL`；不得进入 16-slab additive LOR-HX，也不得用 sweep、
    shift 或更多 cycle 对该失败实现做参数性补救。

---

# 2. G0：同机 M3a 权威与真实残差

## 2.1 两条互补运行

| 证据 | source | solver | official/RTA | process-tree RSS |
|---|---|---|---|---:|
| opt-in screen20 | `568f1ac189f98227541722b1de66cd7804e0cc80` | 20 步 `DIVERGED_MAX_IT(-3)` | false / 未产生 | 6.25998 GiB |
| ordinary MPI1 full | `77d39cbe461204f9e095fb6596ad5b617279d302` | 352 步 `CONVERGED_RTOL` | true / true | 4.76731 GiB |

screen20 的峰值包含 opt-in residual/contraction diagnostics，不是普通 full 的性能回归。
后续内存百分比的同机分母为：

```math
M_{M3a}=4.767307281494141\ \mathrm{GiB}.
```

## 2.2 ordinary full 数值权威

| 指标 | 值 |
|---|---:|
| iterations / wall | `352 / 829.6772821329068 s` |
| reported relative residual | `9.97361250944977e-07` |
| condensed true residual | `9.973612508154941e-07` |
| full augmented true residual | `9.973612508154941e-07` |
| explicit full-FE true residual | `9.973612808764094e-07` |
| R / T / A | `0.0007628808460340567 / 0.6027016359436813 / 0.39653548321028464` |
| A_volume | `0.39653548322357507` |
| R+T+A_volume | `1.0000000000132905` |
| closure error | `1.3290479827787749e-11` |
| factor rows / stored factor NNZ | `127656 / 91415952` |
| worker RSS/PSS/USS | `4687.421875 / 4636.3837890625 / 4592.12890625 MB` |
| swap | `0` |

全局 `A/F` 和 global direct factor 均未物化。canonical active-trace/full-FE manifest
SHA256 分别为：

```text
6fd0c8db99649189f409f52851e4a43de28ea19e473de4aa0d3d31705a9d44e9
dcac07477a863ac1a56051f930cb09f32759dd1596b0e46bbb5a9e03adca7a10
```

后验逐通道 checker 从当前 raw 与冻结 direct authority重新计算，得到：

```text
12/12 significant powers pass
12/12 boundary complex amplitudes pass
status = posthoc_recomputed_12_of_12
```

这不改写成“原 full command 调用了 CLI Gate”，而是当前 raw 的独立后验验证。

## 2.3 residual snapshot 与 slab 诊断

screen20 保存了 iteration 0 和 20 的 active-trace true residual，均为 51,192 rows，
按 ascending global active-row ID 排列。rank ownership 不属于 identity。

| iteration | true relative residual | canonical SHA256 |
|---:|---:|---|
| 0 | `1.0` | `f9440f315522999d87db815b9e619eaa826b5eae052e8403aef9c04bcfc1af7e` |
| 20 | `0.04474243612765` | `cb9fa32dd8c3c26db69a9d5a62577d66225eefb5e39a8bfdf6efb8c76e614ee6` |

iteration 20 的局部诊断中：

| slab | 选择含义 | local residual norm | local ILU rho | local B4 rho | ILU ablation damage |
|---:|---|---:|---:|---:|---:|
| 14 | 最大 local residual，primary | `0.4272314396194324` | `1.2604899530937426` | `0.7558186834062683` | `-0.14960520299020064` |
| 5 | lower-median control | `0.16307530842059187` | `1.247711710628995` | `0.8512896925857695` | — |
| 2 | upper-median comparator | `0.16414059813172402` | `1.1086268146222058` | `0.8675420337186592` | — |
| 13 | 最大正 ablation damage | `0.3575414046731364` | `0.9082591874178787` | `0.7360770299396727` | `+0.038332237714445494` |

slab14 的 residual 最大，但删除其 ILU correction 后一次 global rho 反而改善，因此不得把
“最大 residual”“最大 ablation damage”和“全局最关键 slab”混写成同一个 universal ranking。

一次 stationary apply 中，B4 的 rho 小于固定 ILU，并不表示 B4 完整求解器更好；B4
会针对当前 RHS 做四步局部最小残差，而 M3a 的成功来自 16 slabs、两步 smoother、75D
wave coarse 和 outer FGMRES 的组合。

G0 evidence：

```text
benchmarks/cases/101_task37_extra_development/records/g0_authority.json
benchmarks/cases/101_task37_extra_development/records/g0_m3a_mpi1_full_channels.json
docs/task37_extra_development/outcomes/g0_residual_and_contraction_authority.md
```

---

# 3. G1：factor storage 能力边界

## 3.1 exact factor reuse

16 个 slab 中，shifted local numeric matrix 出现 `7 classes / 9 duplicates`，但这只是
必要条件。绝大多数候选又因 global row identity/order不同被排除，最后仅 slab7/8 保留
必要 prefix 一致。

当前 PETSc factored `Mat` 无法可靠导出：

- actual factor ordering；
- factor CSR/value identity；
- factored matrix row/value fingerprint。

因此没有达到任务要求的 exact factor identity，最终分类：

```text
capability_stop_unverifiable_factor_ordering_and_values
measured_factor_bytes_saved = 0
```

不允许根据相同请求字符串、原 matrix hash 或近似相似性共享 factor。

## 3.2 mixed precision

资格化环境中：

```text
PETSc ScalarType = complex128
PETSc IntType    = int32
```

NumPy complex64 写入 SeqAIJ 后，PETSc CSR values 仍提升为 complex128，ILU factor 继承
同一全局 ABI。因此未实现局部 complex64 factor，分类：

```text
capability_stop_global_petsc_scalar_abi
```

G1 overall：

```text
closed_negative_capability_stop
```

G1 evidence：

```text
benchmarks/cases/101_task37_extra_development/records/g1_factor_storage.json
docs/task37_extra_development/outcomes/g1_factor_storage.md
```

---

# 4. G2.2：slab full-space / trace Schur identity

对 slab14：

| 局部空间 | 行数 |
|---|---:|
| full-space | `32724` |
| cell-interior | `24300` |
| trace | `8424` |

局部 full-space 矩阵写成：

```math
\mathcal A_j=
\begin{bmatrix}
A_{ii}^{(j)} & A_{it}^{(j)}\\
A_{ti}^{(j)} & A_{tt}^{(j)}
\end{bmatrix}.
```

对 trace RHS，可等价求解：

```math
\mathcal A_j
\begin{bmatrix}
z_i\\z_t
\end{bmatrix}
=
\begin{bmatrix}
0\\r_t
\end{bmatrix},
```

并提取 `z_t`。匹配同一 principal restriction、shift、Floquet 和 orientation 时：

```math
S_j^{-1}=R_t\mathcal A_j^{-1}R_t^T.
```

三个 deterministic vectors 与真实 iter20 residual direction 的 action relative error
均约为 `1.8e-15--3.0e-15`。因此 full-space/trace 代数接口正确；后续负结果不能归因于
这一恒等式错误。

Evidence：

```text
benchmarks/cases/101_task37_extra_development/records/g2_slab14_fullspace_identity.json
```

---

# 5. G2.3：plain full-space p6 ILU 路线关闭

| inventory | trace ILU | full-space p6 ILU(0)/RCM |
|---|---:|---:|
| rows | `8424` | `32724` |
| matrix/factor NNZ | `6086016` | `32378616` |
| retained payload lower bound | `116.3708 MiB` | `618.6966 MiB` |
| iter20 one-apply rho | `1.2604899530937386` | `1.806246468352144` |

full/trace retained ratio：

```math
\frac{M_{full\ ILU}}{M_{trace\ ILU}}
=5.316598197391147.
```

即 full-space ILU retained payload 增加约 431.66%，且相同 residual 下 correction 更差。
因此：

```text
plain full-space ILU route = closed
```

该 inventory run 的 process-tree peak 约 7.468 GiB，但当时原有 16 个 trace factors仍在，
故不能把它解释成一个独立 full-space solver 的峰值。

Evidence：

```text
benchmarks/cases/101_task37_extra_development/records/g2_slab14_fullspace_factor_inventory.json
```

---

# 6. G2.4：p6-to-LOR transfer 代数通过

slab14 的 LOR edge space：

| 字段 | 数值 |
|---|---:|
| physical edges | `38304` |
| active edges | `36288` |
| periodic slave edges | `2016` |
| periodic relations | `2016` |
| unique parent transfer stencils | `2` |
| retained transfer payload | `18735740 B`，约 17.87 MiB |

通过的合同包括：

- p2/p3 parent topology；
- high-order orientation；
- constant/affine/curl-compatible fields；
- multi-parent child-edge deduplication；
- Floquet periodic identity；
- owner-local packing 与 MPI partition invariance；
- `T/T^H` adjoint identity。

关键误差：

```text
shared trace reconstruction max       = 1.7200665360018798e-15
complete-C reconstruction max         = 9.56091885020216e-16
T/T^H adjoint relative error          = 1.5008209190777043e-14
```

结论仅为：

```text
pass_transfer_build_and_algebra_only
```

它不证明 V-cycle、预条件器或外层求解有效。

Evidence：

```text
benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_transfer.json
```

---

# 7. G2.5：LOR-HX build 可构造，但内存失败

当前 hierarchy 使用 affine volume proxy：

```text
curl coefficient          = 1
material mass coefficients = complex by tag
DtN surface proxy          = absent
literal p6 Galerkin        = false
fixed diagonal complex shift
```

硬性 factor inventory满足：

```text
fine p6 trace factor count      = 0
fine p6 full factor count       = 0
fine/intermediate large factor  = 0
coarsest factor count           = 2
```

但 retained payload 为：

| 对象 | bytes |
|---|---:|
| LOR transfer | `18,735,740` |
| D2c/H1 hierarchy | `3,109,473,612` |
| total | `3,128,209,352` = `2.91337 GiB` |

一个 slab 的 trace-ILU baseline 为：

```text
122,023,588 B = 116.3708 MiB
```

因此：

```math
\frac{M_{LOR-HX}}{M_{trace\ ILU}}
=25.63610366874313.
```

任务规定的 0.60 memory threshold 为 73,214,152.8 B，当前 hierarchy 约为该阈值的
42.73 倍。memory signal 明确失败。

构建时间：

```text
transfer build = about 52 s
HX build       = about 607 s
```

Evidence：

```text
benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_hx_build.json
```

---

# 8. G2.6：LOR-HX contraction 正式失败

定义：

```math
\rho(M,r)
=
\frac{\|r-S_jM^{-1}r\|_2}{\|r\|_2}.
```

`rho<1` 表示该一次局部 correction缩小对应 residual；`rho>1` 表示放大。该指标是局部
stationary oracle，不等同于完整 outer FGMRES 收敛率。

正式比较：

| source | trace ILU | B4 GMRES(4) | LOR-HX 1V | LOR-HX 2V |
|---|---:|---:|---:|---:|
| real M3a iter0 | `2.422027189163481` | `0.9440411915945912` | `5.611759e6` | `4.885392e15` |
| real M3a iter20 | `1.2604899530937386` | `0.755818683406265` | `3.465824e6` | `1.651097e15` |
| manufactured mixed/high | `4.455510654442446` | `0.8584226047142137` | `6.173855e7` | `1.408426e16` |

所有 correction/post-action 使用 exact shifted full-space slab Schur，记录明确：

```text
proxy_self_score             = false
global_matrix_materialized   = false
finite/deterministic         = true
```

正式 Gate：

| Gate | 结果 |
|---|---|
| minimum：iter20、mixed/high 相对 B4 | `false / false` |
| strong：iter0、iter20 相对 trace ILU | `false / false` |
| apply-time overall | `false` |

mixed/high 的必要条件单独已经明确失败，因此无需、也不得为了改变 hard-stop 分类而补跑
缺失的 B4 i200/long-tail raw。

G2.6 whole-run process-tree authority：

```text
8.137821197509766 GiB
swap = 0
```

Evidence：

```text
benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_hx_contraction.json
docs/task37_extra_development/outcomes/g2_one_slab_fullspace_lor_hx.md
```

---

# 9. Review V1 最终裁决

Review V1 的正式裁决为：

```text
D3c implementation/tests/evidence = accepted
G2.4 transfer                     = algebra-only pass
G2.5 build                        = build-only pass, memory fail
G2.6 measurement                  = qualified, performance fail
G2 overall                        = G2_FAIL
G3                                = prohibited
production promotion              = no
merge to master                   = no
```

G2_FAIL 没有 rooted local repair 额度。禁止：

- 继续扫描 shift；
- 增加 V-cycle 数；
- 改 Jacobi 权重或 H1 层数；
- 扩展到 16-slab LOR-HX；
- 用 z-sweep补救失败局部 inverse；
- 将 build/measurement qualification写成求解器性能通过。

---

# 10. 从 G0--G2 得到的可复用结论

## 10.1 正结果

- M3a MPI1 full baseline 可复现且物理/通道闭合；
- canonical residual snapshot基础设施有效；
- full-space/trace Schur identity正确；
- p6-to-LOR transfer、Floquet、orientation 与 adjoint代数正确；
- raw measurement与独立 checker可以区分“证据合格”和“算法失败”。

## 10.2 负结果

- full-space 不是天然低内存空间；普通 full-space ILU更大；
- 当前 PETSc ABI不能直接提供局部 complex64 factor；
- 当前 PETSc factor对象不足以安全证明 exact factor reuse；
- 当前显式 LOR-HX hierarchy不具备内存优势；
- 当前 LOR-HX proxy/V-cycle不是目标 Schur的稳定近似逆。

## 10.3 仍未被证明的命题

以下命题既没有被证明成功，也不能从 G2 负结果直接判定为永远失败：

- 从一开始就在完整 H(curl) fine space中构造精确 matrix-free operator；
- 不依赖 G2 scalar/vector H1 hierarchy的几何 multigrid；
- 对 coercive full-space Maxwell proxy使用class-reused小 block smoother；
- full-space two-grid机制能否处理 refinement误差。

这些命题只能由新的、严格隔离的 component oracle 判定，不能直接启动完整时谐 PDE。

---

# 11. 下一阶段授权

后续唯一新授权见：

```text
docs/task37_extra_development/review_report_v2.md
```

Review V2 只允许 Candidate H 的第一轮：

```text
H0 full-space MG capability audit
H1 exact full-space matrix-free action
H2 coercive class-reused element-block smoother oracle
```

当前不授权：

```text
exact time-harmonic full solve
H4 shifted-PC screen
new branch
PR
master merge
G2/G3/G4-old reopen
```

新实验应从 `response_v2.md` 继续；本 consolidated `response_v1.md` 固定为 G0--G2
历史权威，不再随 Candidate H 的小阶段反复重写。

---

# 12. Evidence index

```text
Task / Reviews
  docs/task37_extra_development/task.md
  docs/task37_extra_development/review_report_v1.md
  docs/task37_extra_development/review_report_v2.md

Consolidated response
  docs/task37_extra_development/response_v1.md

Outcomes
  docs/task37_extra_development/outcomes/g0_inherited_baseline_audit.md
  docs/task37_extra_development/outcomes/g0_residual_and_contraction_authority.md
  docs/task37_extra_development/outcomes/g1_factor_storage.md
  docs/task37_extra_development/outcomes/g2_one_slab_fullspace_lor_hx.md

Compact records
  benchmarks/cases/101_task37_extra_development/records/g0_authority.json
  benchmarks/cases/101_task37_extra_development/records/g0_m3a_mpi1_full_channels.json
  benchmarks/cases/101_task37_extra_development/records/g1_factor_storage.json
  benchmarks/cases/101_task37_extra_development/records/g2_slab14_fullspace_identity.json
  benchmarks/cases/101_task37_extra_development/records/g2_slab14_fullspace_factor_inventory.json
  benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_transfer.json
  benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_hx_build.json
  benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_hx_contraction.json
```
