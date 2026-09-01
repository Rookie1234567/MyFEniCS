# Task038-extra Review Report V16：same-mesh physical p-coarse 与条件 wave-aware DD

## 0. 审阅身份与最终决定

```text
review                                  = Task038-extra Review Report V16
repository                              = Rookie1234567/MyFEniCS
reviewed_branch                         = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD                           = 31d201881d1540f68eed5fe6025eb355bc90fa07
base_master_SHA                         = 438caf150439343ee7c4c58ad7e02a3da812a23c
branch_vs_master_at_review              = ahead 243 / behind 0
reviewed_review                         = docs/task038_extra_full3d_iterative_0p7nm/review_report_v15.md
reviewed_response                       = docs/task038_extra_full3d_iterative_0p7nm/response_v15.md
reviewed_summary                        = docs/task038_extra_full3d_iterative_0p7nm/outcomes/summary.md
reviewed_next_candidate                 = docs/task038_extra_full3d_iterative_0p7nm/outcomes/next_wave_aware_dd_after_v15.md
working_branch_continues                = yes; same branch only
new_branch_or_worktree                  = forbidden
whole_branch_merge_to_master            = forbidden
ordinary_default_change                 = forbidden
selected_positive_hierarchy             = same_mesh_hcurl_pmg_v1_requalified
standalone_physical_status              = NOT_QUALIFIED
V15_fixed_rank32_floquet_correction      = CLOSED_BY_SPAN_GATE
primary_objective                       = final correctness under bounded memory
iteration_count_and_wall_time           = secondary
fine_physical_operator                  = exact split matrix-free Maxwell volume + streaming Fourier-DtN
production_outer_Krylov                 = right-preconditioned FGMRES
production_outer_restart                = 20, fixed
physical_outer_max_it                   = 20000, fixed
process_tree_hard_limit                 = 2000000000 B
process_tree_warning                    = 1800000000 B
swap_gate                               = 0 B
full_0p7nm_PDE                          = forbidden
response_required                       = response_v16.md
continuous_authorized_batch             = Q0 through Q6, then conditional W0 through W4, then Z0 through Z2
mandatory_stop                          = after Z2 or any earlier terminal hard stop
```

本 Review 继续服从唯一长期目标：

> 在单节点约 2 TiB 物理内存内，以自主 FEniCS/DOLFINx、complex128、Nédélec `H(curl)`、双 Floquet 和 Fourier-DtN，最终求解 0.7 nm 周期单胞内任意非可分三维 Maxwell 散射问题。

本轮直接消除的 blocker 是：

> 已资格化的正定 same-mesh p-multigrid 不能看见真实 Maxwell 的负质量项、复材料、DtN 与全局波相位，导致 p6/h10 真实物理残差在约 `0.484` 附近形成平台。

V16 不重新寻找 fine operator，也不重新扫描普通正定 PC。它先测试一个比完整 domain decomposition 更小、更直接的物理增强：让 same-mesh p3 coarse level 本身使用真实 Maxwell 算子。只有该机制经真实 checkpoint 残差证伪后，才进入预先做数学和容量否决的 wave-aware DD。

---

# 1. 对 V13–V15 结果的审阅

## 1.1 必须永久保留的事实

| 对象 | 冻结状态 | V16 解释边界 |
|---|---|---|
| V13 C1 positive | `C1_P6_POSITIVE_PASS_MPI1` | p6/h10 四类正定辅助源在 180–220 步达到约 `1e-8`；不是 physical Maxwell PASS |
| V13 P0 | `FAILED_RESOURCE_HARD_STOP` | cold setup 达到 `2,024,108,032 B`；后续由 V14 staging 解决，但旧负结果不得重分类 |
| V14 J5 | `CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED` | checkpoint-500/1000 为 `0.48387099430079733 / 0.4837947981092168`；不是 fixed-cap 20000-step failure |
| V14 staged memory | measured positive to controlled stop | 到用户停止点 process-tree peak `1,450,262,528 B`、swap `0 B`；不是 complete workflow PASS |
| V15 F2 | identity/algebra PASS | checkpoint-1000 residual 以 relative `6.884466486395685e-16` 重现 |
| V15 F3 | `FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE` | 固定 rank32 仅捕获 `0.002179823642496248` 残差能量；不得重跑或改 rank/mode/window |
| official E/H/R/T/A/channels | `not_run` | 不得由 auxiliary vectors 或 projection diagnostic 冒充 |
| full 0.7 nm PDE | `not_run` | 本轮仍禁止 |

任何新结果必须使用新 source SHA、新 schema 或明确版本号及全新 artifact root。所有旧 checkpoint、raw timeline、compact record、negative 和 controlled stop 必须保留。

## 1.2 重大进展仍然有效

当前已经建立：

```text
p6 exact matrix-free volume action                    = qualified
streaming Fourier-DtN                                 = qualified
cold JIT staging                                      = qualified to solver entry
restart20 fixed-memory lifecycle                      = qualified
same-mesh p6→p3→p1 transfer                           = qualified
p6/h10 positive random/gradient/curl/checkerboard     = qualified
p6/h10 true physical A/b checkpoint identity          = qualified
```

V15 的负结果只关闭“32 个外部 Floquet 波模直接形成全局低秩 correction”。它不否定包含 `23,073` 个 p3 体积 `H(curl)` unknowns 的 full-domain physical coarse space，也不否定局部传播后形成的接口响应空间。

## 1.3 对 `next_wave_aware_dd_after_v15.md` 的新审阅边界

V15 outcome 把 wave-aware DD 写成唯一未授权候选。用户本轮明确要求继续主线并授权新的 review。V16 在不删除该 outcome 的前提下补充一个优先级更高的窄候选：

```text
same_mesh_physical_pcoarse_v1
```

它不是与现有 selected hierarchy 无关的第五个 PC family，而是把已经资格化的 `p6→p3→p1` hierarchy 中 p3 coarse operator 从正定辅助算子替换为同一物理模型的 p3 Maxwell action。若该最小增强失败，才进入 V15 已提出的 wave-aware DD。

---

# 2. 为什么先测试 physical p-coarse

## 2.1 它解决什么问题

当前正定 hierarchy 使用类似：

```math
B_p
=
K_{\mathrm{curl},p}
+
k_0^2 M_{|\epsilon|,p}.
```

真实物理算子为：

```math
A_p
=
K_{\mathrm{curl},p}
-
k_0^2 M_{\epsilon,p}
+
T_{\mathrm{DtN},p}.
```

`B_p` 能高效处理局部高频和梯度误差，但没有真实负质量项、复损耗与 DtN 波相位。V16 在 p3 coarse level 引入 `A_3`，使 coarse correction 第一次包含完整单胞内部传播，而不是只包含边界上的 32 个外部波模。

## 2.2 它改变计算流程的哪一步

原 selected PC：

```text
p6 positive pre-smoother
→ restrict to p3
→ solve positive p3→p1 V-cycle
→ prolongate to p6
→ p6 positive post-smoother
```

V16 候选：

```text
p6 positive pre-smoother
→ restrict physical residual to p3
→ approximately solve p3 physical Maxwell
   with existing p3→p1 positive V-cycle as inner PC
→ prolongate physical p3 correction to p6
→ p6 positive post-smoother
```

fine operator `A_6`、物理 RHS、材料、Floquet、DtN 和后处理均不改变。

## 2.3 为什么比直接进入 DD 更合理

| 依据 | physical p-coarse 的优势 |
|---|---|
| 已资格化组件 | 复用 same-mesh `P_{63}/P_{63}^H`、p3→p1 positive cycle、cold staging 和 exact `A_6` |
| 空间表达能力 | p3 coarse 是全三维体积场，不是 32 个边界方向 |
| 内存 | p3 vector 约 `23,073 × 16 = 369,168 B`；restart20 级别的 p3 Krylov 向量仅为 MB 量级 |
| 任意三维 | 不要求内部材料可分离或接口均匀 |
| 可证伪性 | 可直接用冻结 checkpoint-1000 测一个 coarse correction 对真实平台残差的收缩 |
| 代价 | nested inner solve 增加时间；因此 outer 必须使用 FGMRES，并先做短 screen |

上述向量字节是 derived estimate，不是完整 live-set。Q0 必须重新闭合实际 p3 physical action、inner KSP、outer FGMRES 和 recovery 的 simultaneous memory。

## 2.4 适用边界

即使 V16 physical p-coarse 通过，它也只先证明：

```text
13.5 nm
p6/h10
MPI1
固定 rectangular-grating authority case
```

当前 p1 最粗层仍使用小型 MUMPS development oracle。它不能直接被宣称为 0.7 nm production coarse solve；后续 2 TiB 审计必须单独替换或限制该 global direct coarse。

---

# 3. 冻结数学定义

设 same-mesh constrained spaces为 `V6`、`V3`、`V1`。当前已资格化 transfer 定义：

```math
P_{63}:V_3\rightarrow V_6,
\qquad
R_{63}=P_{63}^{H}:V_6'\rightarrow V_3'.
```

fine physical operator继续为：

```math
A_6
=
K_{\mathrm{curl},6}
-
k_0^2 M_{\epsilon,6}
+
T_{\mathrm{DtN},6}.
```

新 p3 physical operator必须在同一 mesh、同一 material tags、同一 incidence、同一 total-field formulation、同一 ordered mode inventory 和同一 Floquet phase convention下构造：

```math
A_3
=
K_{\mathrm{curl},3}
-
k_0^2 M_{\epsilon,3}
+
T_{\mathrm{DtN},3}.
```

由于 `V3` 是 same-mesh p-subspace，必须审计：

```math
A_3 v
\approx
P_{63}^{H}A_6P_{63}v.
```

该 identity 是进入 checkpoint correction 的前置 Gate。`A_3` 必须由 matrix-free split volume action加 streaming DtN实现；禁止组装 global p3 physical AIJ 或 dense DtN。

p3 inner solve使用：

```math
A_3 e_3=r_3,
\qquad
r_3=P_{63}^{H}r_6.
```

inner PC固定为现有 p3→p1 positive V-cycle。outer physical p-cycle固定为：

```math
\begin{aligned}
u_6^{(0)} &= S_6r_6,\\
r_6^{(1)} &= r_6-A_6u_6^{(0)},\\
r_3 &= P_{63}^{H}r_6^{(1)},\\
e_3 &\approx A_3^{-1}r_3,\\
u_6^{(1)} &= u_6^{(0)}+P_{63}e_3,\\
r_6^{(2)} &= r_6-A_6u_6^{(1)},\\
M_{\mathrm{phys-p}}^{-1}r_6
&=
u_6^{(1)}+S_6r_6^{(2)}.
\end{aligned}
```

`S6` 是当前 frozen positive degree-3 Chebyshev/Jacobi smoother。inner solve可能产生变精度 correction，所以 outer Krylov固定为 FGMRES，不允许继续用普通 GMRES 冒充 flexible contract。

---

# 4. 固定参数与禁止项

## 4.1 固定身份

```text
wavelength                         = 13.5 nm
profile                            = grazing1 / theta89 / phi0 / s
fine degree / mesh                 = p6 / h10
coarse degrees                     = p3 / p1
MPI for first physical formal      = 1
input file SHA256                  = 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41
physical model SHA256              = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
ordered mode manifest SHA256       = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
outer Krylov                       = right FGMRES
outer restart                      = 20
outer physical max_it              = 20000
residual replacement               = every 20 outer iterations
solution-only checkpoint           = every 500 outer iterations
final physical true residual       <= 1e-6
process-tree hard RSS              < 2000000000 B
swap                               = 0 B
```

## 4.2 唯一 inner-fidelity ladder

本轮只允许：

```text
reference inner solve:
    right FGMRES
    restart=20
    max_it=10000
    explicit true residual <=1e-6

production fidelity I20:
    exactly 20 inner iterations from zero

single conditional escalation I100:
    exactly 100 inner iterations from zero
```

不得测试 `40/60/80/200`、不同 restart、不同 tolerance、不同 smoother、不同 p-level 或不同 mass shift。I100 只在 reference mechanism通过而 I20 correction未达到 production contraction Gate时运行一次。

## 4.3 明确禁止

```text
重跑或扩展 V15 rank32 Floquet projection
从 checkpoint residual 拟合 coarse basis
Ritz / harmonic-Ritz / residual-derived vectors
增加 outer restart
扫描 inner/outer Krylov、omega、shift 或 Chebyshev degree
组装 p6 global AIJ
组装 dense p3/p6 DtN
建立 p6 或 p3 physical direct factor
恢复 Route A/B/C、HX、普通 GenEO/BDDC、旧 local-spectral 或旧 two-slab production claim
改变物理、quadrature、材料、Floquet、mode inventory 或 ordinary default
```

---

# 5. 总执行顺序与分支

```text
Q0  physical p-coarse 数学/容量预审
Q1  p3 physical action identity 与 small MPI oracle
Q2  checkpoint-1000 reference p3 physical correction
Q3  I20 / 条件 I100 production correction资格
Q4  checkpoint-1000 outer short screen
Q5  条件 fresh full physical MPI1 + recovery
Q6  条件 MPI2、h5 setup-only和0.7 nm/2 TiB更新

若 Q0–Q5 任一真实 Gate关闭 physical p-coarse：

W0  wave-aware DD 数学/容量否决预审
W1  small local/interface oracle
W2  checkpoint-1000 local + interface correction诊断
W3  条件 p6 setup与2000步 short screen
W4  条件 fresh full physical MPI1 + recovery

Z0  成功或全部失败后的架构结论
Z1  outcomes / summary / development_progress / response_v16.md
Z2  tests、commit、push、停止等待审阅
```

执行中不需要在每个阶段等待审阅，但任何 terminal Gate触发后必须按本报告的固定分支推进或停止，不得自行增加第三种候选。

---

# 6. Q0：physical p-coarse 数学与容量预审

Q0 必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/physical_pcoarse_preflight_v16.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/physical_pcoarse_preflight_v16.json
```

## 6.1 必须在代码前冻结的实现图

文档必须逐对象说明：

```text
p6 exact physical action ownership
p3 exact physical action ownership
p6/p3 DtN carrier和surface assembler的复用/销毁关系
P63 / P63^H primal-dual convention
p3 positive inner PC ownership
outer FGMRES和inner FGMRES work vectors
cold precompile group顺序
checkpoint reader与identity binding
release-before-recovery顺序
```

若不能给出唯一的 `A3`、`P63/P63^H` 与 inner/outer apply公式，Q0关闭并进入 W0，不得边写代码边猜。

## 6.2 容量 Gate

必须从 V14 measured anchor出发，列出 simultaneous live set，而不是累计字节：

```text
V14 measured pass-to-stop peak
p3 physical volume action
p3 streaming DtN carrier/action
p3 inner restart20 vectors
outer FGMRES extra flexible basis vectors
I20和I100共用workspace
checkpoint/recovery reserve
allocator与JIT uncertainty
```

prospective Gate：

```text
central complete live-set prediction < 1,750,000,000 B
hard-upper prediction                < 1,900,000,000 B
major unknown object                 = none
p3 physical action retained estimate 需有 measured或公式来源
```

无法闭合则进入 W0，不运行 formal p6。

---

# 7. Q1：p3 physical action identity 与 small oracle

## 7.1 小型 action identity

在同一 p6/h50 mesh上构造 p6 与 p3 physical actions，MPI1后MPI2。固定 probes：

```text
random
gradient
curl
checkerboard
physical_component_derived
r3_long_tail_derived
```

逐 probe 比较：

```math
A_3v
\quad\text{和}\quad
P_{63}^{H}A_6P_{63}v.
```

Gate：

```text
canonical key sets / mode inventory      = exact
P/P^H work identity                      <=1e-11
physical action Galerkin relative        <=1e-9
repeat / linearity / input unchanged     <=1e-12
owned slave max                          = 0
finite / phase exactly once              = pass
MPI1/MPI2 canonical action relative      <=1e-10
no global physical AIJ/dense DtN/factor  = pass
```

## 7.2 small p3 physical inner solve

在 p3/h50、MPI1/MPI2上运行：

```text
physical_rhs
random
```

固定 inner solver为 right FGMRES/restart20/max_it5000，inner PC为当前 p3→p1 positive cycle。每案必须：

```text
final explicit true residual <=1e-6
process-tree peak <500,000,000 B per MPI1 case
MPI2 peak <900,000,000 B
swap=0
finite/repeat/provenance=pass
```

若 action identity失败，只有唯一定位到 orientation、phase、surface quadrature或owner reduction的单一代码 bug时，允许一次窄修；旧证据保留，新 SHA/root重跑。若数学 identity或small physical solve真实失败，关闭 Q候选并进入 W0。

---

# 8. Q2：checkpoint-1000 reference p3 physical correction

Q1通过后，使用 V14 checkpoint-1000：

```text
manifest SHA256 = 7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139
solution SHA256 = 00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b
stored residual = 0.4837947981092168
```

在一个 fresh cold-staged parent下：

1. 重建同一 `A6/b`；
2. 恢复 `x1000`；
3. 重算 `r6=b-A6*x1000`；
4. 形成 `r3=P63^H*r6`；
5. 用 reference inner solve求 `A3*e3=r3`；
6. 形成 `e6=P63*e3`；
7. 计算 `r6_new=r6-A6*e6`。

定义：

```math
\rho_{\mathrm{ref}}
=
\frac{\lVert r_{6,\mathrm{new}}\rVert_2}
{\lVert r_6\rVert_2}.
```

同时记录 coarse residual removal：

```math
\rho_{3}
=
\frac{\lVert P_{63}^{H}r_{6,\mathrm{new}}\rVert_2}
{\lVert P_{63}^{H}r_6\rVert_2}.
```

Q2 Gate：

```text
checkpoint residual reproduction relative <=1e-11
reference inner true residual              <=1e-6
rho_ref                                     <=0.70
rho_3                                       <=0.10
complete process-tree peak                  <2,000,000,000 B
swap                                        =0
finite/input unchanged/slave-zero           =pass
```

Q2 是 mechanism authority。若 reference p3 correction都不能消除至少30%的平台残差，physical p-coarse正式关闭，进入 W0；不得继续增加 inner max_it、改变 p-level 或拟合 residual。

---

# 9. Q3：生产可用 inner fidelity

只有 Q2通过后，才在同一 checkpoint residual上测试完整 physical p-cycle。

## 9.1 I20

```text
inner iterations = exactly 20
inner restart    = 20
zero initial guess
p3 positive PC frozen
p6 positive pre/post smoother frozen
```

计算一次完整 `M_phys-p^{-1} r6` 后，用 exact `A6` 重算 residual。若：

```text
rho_I20 <=0.70
```

则选择 I20，不运行 I100。

## 9.2 唯一 I100 escalation

若 Q2 reference通过但 I20 `rho>0.70`，只允许一次 I100：

```text
inner iterations = exactly 100
其余完全不变
```

I100必须：

```text
rho_I100 <=0.70
```

否则 physical p-coarse关闭并进入 W0。

I20/I100均须满足：

```text
repeat <=1e-12
input unchanged
finite
slave-zero
complete peak <2GB
swap=0
无 per-apply RSS accumulation
```

选中的 inner fidelity成为 Q4/Q5唯一身份，不得再测试其他数值。

---

# 10. Q4：checkpoint outer short screen

从冻结 `x1000` 作为初值，使用新 physical p-cycle：

```text
outer right FGMRES
restart=20
max additional iterations=2000
residual replacement every20
checkpoint every250
```

Q4 不执行 recovery或official physics。其目的只是确认新 coarse mechanism真正打破 `0.484` 平台。

Gate：

```text
initial recomputed residual               =0.4837947981092168 within1e-11 relative
final residual after <=2000 additional it <=0.04837947981092168
至少下降一个完整十进制数量级
complete process-tree peak                <2GB
swap                                      =0
finite/checkpoint/provenance/no RSS growth=pass
```

若未达到一数量级下降，Q候选关闭并进入 W0。不得把“仍缓慢下降”作为增加到5000或10000的理由。

---

# 11. Q5：fresh full physical Maxwell MPI1

Q4通过后，使用新 source SHA、全新空 cache和零初值运行：

```text
13.5 nm
p6/h10
MPI1
exact split matrix-free Maxwell volume
streaming Fourier-DtN
selected same_mesh_physical_pcoarse_v1
outer right FGMRES
restart=20
max_it=20000
replacement20
checkpoint500
```

数值和资源 Gate：

```text
final explicit true residual <=1e-6
complete process-tree peak   <2,000,000,000 B
process-tree/rank swap       =0
natural or qualified solver exit
no orphan / no RSS accumulation
```

通过后严格执行：

```text
保存minimum recovery packet
→ 销毁outer FGMRES与全部Krylov basis
→ 销毁p3 physical inner KSP
→ 销毁p1 development direct factor与p3/p1 solver stack
→ 确认RSS下降
→ recover complex E/H和near-field
→ official R/T/A
→ A_volume与energy closure
→ 同一12个significant identities的12 power + 12 complex amplitudes
```

完整 recovery后的全过程峰值仍必须低于2GB。数值通过但 recovery超过2GB，分类为 `NUMERICAL_PASS_RESOURCE_FAIL`，不能冒充完整通过。

## 11.1 authority packet

当前 tracked direct authority只有 scalar `R/T/A/A_volume`。因此：

1. 先用现有 scalar authority完成可用比较；
2. E/H和12+12 arrays缺失必须标记为 `blocked_by_authority_arrays_missing`；
3. 只有 iterative Q5数值与self-physics均通过时，才允许一次独立 direct authority generation；
4. direct authority运行与 iterative `<2GB` Gate分开记录，不得把 direct内存混入 iterative峰值；
5. 无 authority arrays时不得虚构 channel/field comparison PASS。

Q5通过只能先分类为：

```text
P6_H10_FIXED_CASE_PHYSICAL_PASS_WITH_DEVELOPMENT_P1_ORACLE
```

它不是0.7 nm production qualification。

---

# 12. Q6：条件 MPI2、h5 与 0.7 nm / 2 TiB 更新

只有 Q5数值、资源和可获得的official physics通过后，才允许：

```text
MPI2 same physical workflow
p6/h5 setup-only与最多一个20-step screen
更新feasibility_0p7nm_2tib_v5.md
```

Q6必须区分：

```text
measured  = h10 MPI1/MPI2、条件h5 setup/20-step
scaled    = 由h10→h5实测得到的component scaling
predicted = 0.7 nm optimistic/central/conservative
not_run   = full 0.7 nm PDE
```

新的容量审计必须特别列出：

```text
p6/p3/p1 rows和NNZ
p3 physical action与inner KSP
outer FGMRES restart20
p1 global direct oracle替换成本
DtN channel增长
MPI复制
checkpoint/recovery
系统余量
```

---

# 13. W0：wave-aware DD 合理性与容量否决预审

仅在 Q候选被真实 Gate关闭后进入。W0首先是 docs/read-only preflight；未通过前禁止数值实现。

必须创建：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/wave_aware_dd_preflight_v16.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/wave_aware_dd_preflight_v16.json
```

## 13.1 与旧失败路线的差异必须先证明

新候选固定名称：

```text
wave_aware_interface_schur_dd_v1
```

它不得只是旧路线换名。必须逐项证明：

| 旧路线 | 旧 blocker | 新候选必须不同的机制 |
|---|---|---|
| T4/T5 two-slab Robin sweep | physical RHS contraction弱；旧局部实现内存高 | 4个geometry-only z子域；local solve复用低内存 same-mesh pMG；Robin只作局部闭合，不是唯一全局机制 |
| V15 rank32 global projection | 只捕获0.218%残差能量 | 使用完整低阶接口trace并经局部physical harmonic extension，不是32个全局边界向量 |
| 普通正定 GenEO/HX | 不看真实不定波传播 | local operator和harmonic extension使用真实physical Maxwell |
| 旧trace-harmonic/local-spectral | Z/AZ或factor内存失控 | 不持久保存FE-sized global Z/AZ；接口列streaming/recomputable、owner-distributed |

若无法给出这些差异的唯一矩阵公式，W0关闭，不写solver。

## 13.2 固定几何和接口策略

```text
subdomains                    = 4 z-slabs from geometry-only z quartiles
material separability         = not assumed
artificial-interface overlap  = one h10 cell layer
local artificial closure      = one frozen first-order impedance from existing T4 formula
local direct factors          = forbidden
local iterative inverse       = same-mesh physical p-coarse if Q mechanism部分有效；否则same-mesh positive pMG
local inner restart/max_it     = 20 / 100 fixed
```

旧 first-order Robin standalone contraction negative永久保留。V16只允许它使局部子问题可解；全局传播必须由接口 Schur/coarse correction承担。

## 13.3 固定接口空间

每个内部接口使用：

```text
full owner-distributed p1 tangential H(curl) trace basis
+ its exact gradient-trace subspace identity
→ two-sided local physical harmonic extension
```

V15的32个外部Floquet modes只用于报告它们在该p1 trace空间中的projection error，不作为新增可调basis，也不允许残差拟合。

pilot hard limits：

```text
internal interfaces                 =3
accepted total independent trace rank <=512
persistent FE-sized Z/AZ            =forbidden
coarse/interface dense oracle        =仅checkpoint诊断允许，rank<=512
full physical production coarse      =必须owner-distributed iterative apply/solve
```

## 13.4 容量 Gate

W0必须列出 simultaneous live set：

```text
base cold-staged physical bundle
4 local restriction/prolongation maps
一次只存活一个local physical workset
interface trace metadata
streamed harmonic-extension work
coarse matrix/factor oracle
outer restart20 reserve
recovery reserve
```

prospective Gate：

```text
central prediction                  <1,750,000,000 B
hard upper                         <1,900,000,000 B
persistent interface metadata       <=100,000,000 B
local simultaneous work             <=250,000,000 B
coarse oracle matrix+factor          <=32,000,000 B
major unknown                       =none
```

若 interface rank、local action或streaming coarse apply不能闭合，W路线在W0关闭，不进入代码。

---

# 14. W1：small local/interface oracle

W0通过后，只在 p2/p3、MPI1/MPI2 运行：

```text
R_i / R_i^H work identity
partition-of-unity identity
artificial impedance action identity
local physical action vs restricted exact action
p1 tangential trace rank和orientation
local harmonic extension residual
interface P/P^H adjoint
MPI canonical owner identity
Floquet phase exactly once
finite/input unchanged/slave-zero
```

Gate：

```text
work/adjoint/commuting relative <=1e-10
local physical residual         <=1e-6
MPI canonical relative          <=1e-10
small process-tree peak         <900,000,000 B for MPI2
swap                            =0
```

唯一代码 bug可窄修一次；真实 algebra或local-solve失败则关闭 W。

---

# 15. W2：checkpoint-1000 contraction diagnostic

W1通过后，使用同一冻结 `r1000`。不启动长 outer KSP，依次测：

```text
local-only four-slab correction
local + streamed interface Schur/coarse correction
```

正式 Gate：

| 指标 | local-only | two-level interface |
|---|---:|---:|
| fine residual contraction | `rho <=0.90` | `rho <=0.60` |
| repeat | `<=1e-12` | `<=1e-12` |
| process-tree peak | `<2GB` | `<2GB` |
| swap | `0` | `0` |

若 local-only无任何正信号，或 two-level不能至少消除40%平台残差，W路线关闭。不得扫描 slab数、overlap、Robin参数、trace degree或rank。

---

# 16. W3/W4：条件 short screen与full physical

W2通过后：

## W3 checkpoint short screen

```text
initial guess = x1000
outer right FGMRES
restart=20
max additional iterations=2000
replacement20
checkpoint250
```

要求 final residual不高于 `0.04837947981092168`、peak `<2GB`、swap `0`。失败即关闭 W。

## W4 fresh full physical

W3通过后，使用零初值、fresh cold cache、max_it20000，执行与 Q5相同的 residual、资源、release、recovery和official physics Gate。

若 W4通过，classification必须说明：

```text
P6_H10_FIXED_CASE_WAVE_AWARE_DD_PASS
```

仍不是完整0.7 nm或任意三维 production pass。

---

# 17. 失败与继续规则

| 事件 | 固定动作 |
|---|---|
| pre-measurement path/cache/marker/import/provenance bug | 保留旧root；唯一定位后窄修一次；新SHA/root重试 |
| Q1 action identity真实失败 | 关闭physical p-coarse，进入W0 |
| Q2 reference contraction失败 | 关闭physical p-coarse，进入W0 |
| Q3 I20和I100均失败 | 关闭physical p-coarse，进入W0 |
| Q4 short screen失败 | 关闭physical p-coarse，进入W0 |
| Q5 fixed-cap数值或资源失败 | 保留Q正信号边界，进入W0 |
| W0容量/公式失败 | 不写DD solver，进入Z0 |
| W1 algebra失败 | 关闭W，进入Z0 |
| W2 contraction失败 | 关闭W，进入Z0 |
| W3/W4失败 | 关闭W，进入Z0 |
| 任一Q或W full physical通过 | 跳过其他候选，进入Q6/Z1 |

不得因候选失败自动增加第三种 numerical PC。若 Q与W均失败，Z0只写：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/next_pc_architecture_after_v16.md
```

比较以下未来方向但不实施：

```text
PML/complex-shifted sweeping with compressed interface responses
energy-minimizing H(curl) FETI-DP/BDDC on physical local operators
matrix-free p-h multigrid with distributed wave coarse solve
intermediate-wavelength/reduced-geometry pilot hierarchy
```

---

# 18. 测试、证据和代码边界

## 18.1 代码位置

数值核心必须进入通用 `src/solvers/`：

```text
p3 physical action
physical p-cycle
wave-aware DD local/interface action（仅条件进入）
```

`benchmarks/` 只保留薄 runner、cold parent、watchdog、checker和evidence orchestration。不得继续把核心算法堆入一个新的 task-numbered巨型runner。

## 18.2 checker

checker必须：

```text
只读原始record/NPZ/compact
独立重算residual、rho、identity和Gate
不得导入runner/solver/PETSc/MPI/DOLFINx
不得只信任record中的status
```

## 18.3 必需测试

至少包括：

```text
physical A3 vs P^H A6 P identity
p3 DtN mode/order/normalization identity
inner I20/I100 fixed-count contract
outer FGMRES flexible-PC contract
checkpoint identity and residual reproduction
release/destroy idempotence
cold cache stage order and no recompile
wave-aware R/P/PoU/interface tests（仅条件进入）
Markdown rendering and repository principles
ruff / compileall / focused pytest / MPI focused tests
```

正式重型运行前后必须记录：

```text
branch/HEAD/upstream/worktree
Python/MPI/PETSc/DOLFINx/Basix ABI
complex128/int type/threads
input/physical/mode/source SHA
MemAvailable/swap/disk/watchdog
complete command and artifact hashes
```

---

# 19. 必需 outcomes 与 response

Codex必须按实际触达阶段创建，不得创建未运行阶段的伪 outcome：

```text
outcomes/physical_pcoarse_preflight_v16.md
outcomes/physical_pcoarse_oracle_v16.md
outcomes/physical_pcoarse_checkpoint_v16.md
outcomes/physical_pcoarse_screen_v16.md
outcomes/p6_physical_v16.md                    # 条件
outcomes/wave_aware_dd_preflight_v16.md         # 条件
outcomes/wave_aware_dd_oracle_v16.md            # 条件
outcomes/wave_aware_dd_checkpoint_v16.md        # 条件
outcomes/feasibility_0p7nm_2tib_v5.md           # 条件
response_v16.md
```

同时更新：

```text
outcomes/summary.md
docs/development_progress.md
outcomes/test_summary.md
```

`response_v16.md` 至少逐项回答：

1. `A3` 是否与 `P63^H A6 P63`闭合，最坏 probe/MPI误差是多少？
2. p3 physical inner solve在small MPI1/MPI2是否最终通过？
3. checkpoint-1000 reference `rho_ref/rho3`是多少？
4. I20或I100哪个被选中，为什么没有形成参数扫描？
5. checkpoint short screen是否打破 `0.484` 平台？
6. fresh physical是否达到 `1e-6`，全过程RSS/swap是多少？
7. release-before-recovery是否使RSS下降，official输出来自哪个通过场？
8. direct authority哪些arrays存在、缺失或条件生成？
9. 若进入W，wave-aware DD与旧two-slab/rank32/GenEO具体差异是什么？
10. W local-only和two-level checkpoint contraction分别是多少？
11. 哪些项是 measured、derived、predicted、failed、controlled_stop或not_run？
12. 当前结果消除了0.7 nm/2 TiB主线的哪个blocker，仍剩哪些blocker？

---

# 20. 最终停止与合并边界

本轮完成 Q0→Q6 或条件 W0→W4 后，Codex必须：

```text
更新outcomes/summary.md和development_progress.md
创建response_v16.md
运行最终focused tests与文档Gate
提交并push同一执行分支
报告完整HEAD、source SHA、测试、worktree和evidence index
停止等待ChatGPT审阅
```

本 Review 不授权：

```text
完整0.7 nm PDE
ordinary default改变
master merge/rebase
增大restart
无界迭代上限
新的第四候选
删除或弱化负结果
把p1 direct oracle写成production scalable coarse solve
```

核心决策为：

> 先用 full-volume p3 physical coarse 对 checkpoint-1000 做一次直接、可证伪的波动 correction；它通过才恢复真实 Maxwell。只有这个最小机制失败，才投入经过公式和容量预审的 wave-aware interface DD。这样既利用当前最大正信号，也避免未经筛选地开发昂贵新路线。
