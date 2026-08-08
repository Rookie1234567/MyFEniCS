# Task037b Review Report V2：R5 固定作用的 Hybrid block-level 最终验证

## 0. 审阅身份与授权边界

```text
review                         = Task037b Review Report V2
reviewed_branch                = codex/20260807-task37b-hybrid-iterative-development
reviewed_response              = docs/task037b_hybrid_fem_modal_iterative/response_v2.md
reviewed_R5_source             = 2a2ef3d37514e4ab30d50209065af84c1dafd59b
reviewed_Task37_extra_source   = 30e179799b8eb6dee1be1bb976002550424bb40d
ordinary_default               = unchanged
merge_to_master                = not_authorized
new_general_PC_family          = forbidden
LOR_HX_reopen                  = forbidden
bounded_block_level_test       = authorized
```

本报告接受 Review V1 的 R1–R5 证据链，也接受 R5 的正式分类：

```text
WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE
```

该分类说明 R5 不能作为一个独立 local solver 在 300 步内把全部冻结 RHS 解到
`1e-8`，但它还没有回答另一个不同问题：

> 一次固定、线性的 R5 Woodbury action，作为完整 Hybrid block-LDU
> preconditioner 中的近似 endcap inverse，能否使外层 Hybrid FGMRES 的真实残差下降？

V2 只批准对这个问题做一次严格有界的验证。它不是放宽 R5 local-solver Gate，也不是重新
开发 LOR、AMS/HX、p-multigrid、Schwarz sweep 或新的 Krylov 家族。

---

# 1. 已接受的科学结论

## 1.1 Hybrid 与 block-LDU 代数正确

现有证据已经证明：

| 阶段 | 结果 | 结论 |
|---|---|---|
| H1 | direct Hybrid true residual 约 `1.45e-12`，12/12 powers、12/12 amplitudes、场与 R/T/A 通过 | 当前冻结 Hybrid authority 正确 |
| H2a | assembled Hybrid block action identity 通过 | block layout 与 coupling 正确 |
| H2b | Matrix-free local endcap action identity 约 `1e-16` | local Schur + external DtN action 正确 |
| H3 | exact block-LDU，outer FGMRES 1 步，true residual 约 `2.89e-12` | monolithic iterative algebra 正确 |
| H4a | exact modal Schur，outer 1 步 | modal Schur 公式正确 |
| H5a | bottom/top exact local inverse 各 11/11 | local action 与 RHS 接线正确 |

因此 V2 不允许把新的负结果解释为 Hybrid 物理方程、Matrix-free DtN 或 block-LDU
符号错误，除非 exact identity regression 明确失败。

## 1.2 R1–R5 已定位到主体 fine-space inverse

每侧完整 endcap operator 为：

```math
A_s
=
F_s-C_sH_s^{-1}D_s,
\qquad s\in\{b,t\}.
```

R1 证明上述 action 分解正确；R4 证明 exact `F_s^{-1}` 加 40-mode Woodbury 能恢复
exact `A_s^{-1}`。R2 证明原六-slab 即使只求 `F_s` 也失败，R3 证明 whole-endcap
ILU(0) 比六-slab 强但仍不足，R5 证明加入 exact 40-mode DtN correction 后仍不能达到
standalone `1e-8` Gate。

所以当前剩余瓶颈是：

```math
B_s^{-1}
\approx
F_s^{-1}
```

的质量，而不是 Woodbury 小矩阵、DtN mode count、符号或 ownership。

## 1.3 LOR/HX 不得重新开启

Codex 在开始 V2 前必须读取另一研究分支的以下权威文件：

```text
git show origin/codex/20260806-task37-iterative-extra-development:docs/task37_extra_development/review_report_v1.md
git show origin/codex/20260806-task37-iterative-extra-development:docs/task37_extra_development/response_v5.md
git show origin/codex/20260806-task37-iterative-extra-development:docs/task37_extra_development/outcomes/g2_one_slab_fullspace_lor_hx.md
```

必须在 `response_v3.md` 中明确继承：

```text
LOR transfer/algebra             = pass only
LOR-HX retained payload          = about 2.913 GiB for one slab
LOR-HX 1V contraction            = about 1e6–1e8 residual amplification
LOR-HX 2V contraction            = about 1e15–1e16 residual amplification
Task37-extra G2                  = G2_FAIL
Task37-extra G3                  = prohibited by G2_FAIL
```

因此 V2 禁止：

- cherry-pick Task37-extra 的 LOR/HX solver code；
- 新建 LOR、AMS/HX、p6→p4→p2、p6→p2 或 full-space ILU candidate；
- 以“另一种理论 LOR 也许有效”为理由扩展本任务；
- 重新扫描 shift、overlap、ILU level、cycle 数或 H1 层级。

---

# 2. V2 真正验证的问题

R5 standalone qualification 使用的是：

```text
complete endcap operator A_s
+ right FGMRES restart30
+ max_it 300
+ fixed whole-endcap ILU(0) + 40-mode Woodbury PC
```

并要求每一个 local RHS 独立达到 `1e-8`。

V2 不再调用这 300 步 local KSP。V2 定义固定、线性的单次近似逆：

```math
M_s^{-1}r
=
B_s^{-1}r
+
W_sK_s^{-1}D_sB_s^{-1}r,
```

其中：

```math
W_s
=
B_s^{-1}C_s,
```

```math
K_s
=
H_s-D_sW_s.
```

`B_s^{-1}` 必须是 R5 已冻结的 whole-endcap ILU(0) smoother 的**一次作用**。

V2 的核心问题是：

```math
M_s^{-1}
```

虽然不能独立把任意 local RHS 解到 `1e-8`，但它是否仍然能作为完整 Hybrid
block preconditioner 的一个有用近似块。

---

# 3. 精确 Hybrid operator 与近似 block-LDU

冻结的 monolithic Hybrid operator 为：

```math
\mathcal K
=
\begin{bmatrix}
A_b & 0   & T_b\\
0   & A_t & T_t\\
P_b & P_t & G
\end{bmatrix}.
```

所有 V2 外层 MatMult 必须继续使用 exact monolithic operator；任何近似只允许进入 PC。

对给定 bottom/top 近似逆 `M_b^{-1}`、`M_t^{-1}`，构造一致的 modal Schur：

```math
\widetilde S_m
=
G
-P_bM_b^{-1}T_b
-P_tM_t^{-1}T_t.
```

右预条件 block-LDU 的一次作用按 H3 已验证的符号和块顺序实现：

```math
z_b=M_b^{-1}r_b,
\qquad
z_t=M_t^{-1}r_t,
```

```math
\widehat r_m
=
r_m-P_bz_b-P_tz_t,
```

```math
z_m
=
\widetilde S_m^{-1}\widehat r_m,
```

```math
z_b
\leftarrow
z_b-M_b^{-1}T_bz_m,
```

```math
z_t
\leftarrow
z_t-M_t^{-1}T_tz_m.
```

重要：

- 不得根据本报告手工重写新的符号体系；
- 必须复用 H3/H4 exact block-LDU 的 coupling、pack/split 和 sign convention；
- 只替换 local inverse callback 和由它构造的 modal Schur；
- `\widetilde S_m` 必须使用与 online PC 完全相同的固定 local action构造；
- 不得用 exact local inverse 构造 `\widetilde S_m`，再在 online 阶段换成 R5 action。

---

# 4. V2-0：继承、源码与文档 Gate

开始前必须：

1. fast-forward 当前 Task37b 分支，确认工作树干净；
2. 阅读 `task.md`、`review_report_v1.md`、`response_v2.md`；
3. 按 §1.3 阅读 Task37-extra 的 LOR/HX 最终证据；
4. 保留全部 H5/R1–R5 历史，不覆盖任何旧 response 或 outcome；
5. 新建 `response_v3.md` 回应 V2；
6. 所有新增独立公式使用 fenced `math` block；不得使用多行 `$$` 或 `\[...\]`。

本轮冻结不变：

```text
physics                       = 13.5 nm / S / 10° grazing
endcap interfaces             = 10 nm / 110 nm
discretization                = p6 / h10
internal modes                = M120 forward + M120 backward
modal unknowns                = 240
external modes                = 40 per endcap
outer operator                = exact monolithic Hybrid MatPython
direct Hybrid authority       = unchanged
ordinary defaults             = unchanged
```

---

# 5. V2-1：固定 R5 action 适配与代数资格化

## 5.1 禁止 nested local KSP

V2 block PC 中禁止调用：

```text
HybridLocalDtnWoodburyLocalInverse.solve(...)
```

因为该方法启动 restart30/max_it300 的 local FGMRES。

V2 必须直接复用已经建立的固定 action：

```text
HybridLocalDtnWoodburyOracle.apply(source, target)
```

或一个数值完全等价、职责更清晰的薄适配器。每次 local inverse callback 只能：

1. 做一次 whole-endcap ILU(0) smoother apply；
2. 做一次 40-mode `D` action；
3. 解一次 40×40 `K`；
4. 加一次 `W q` correction。

不得在 callback 内启动 inner GMRES、循环到 local tolerance、自动 fallback 或根据当前 residual
改变 action。

## 5.2 固定线性与重复性 Gate

bottom/top 各执行 deterministic probes，要求：

```text
linearity relative error        <= 1e-12
determinism relative error      <= 1e-14
repeat action hash              identical
K rank                          = 40
K condition                     finite and <= 1e10
all arrays                      finite
base factor count               = 1 per approximate side
local direct factor             = 0
```

还必须比较：

```text
new block callback action
vs
R5 woodbury.apply action
```

相对误差 `<=1e-13`。

## 5.3 Local one-apply 只作诊断

对原 21 个非零 local RHS 记录一次 `M_s^{-1}` correction 后：

```math
\rho_s
=
\frac{\lVert r_s-A_sM_s^{-1}r_s\rVert_2}
{\lVert r_s\rVert_2}.
```

这些值只用于解释，不再要求 `<=1e-8`，也不得用它们代替 block-level true residual。
若出现 NaN、Inf 或不可重复 action，属于 implementation failure，停止。

---

# 6. V2-2：两个单侧 20-step block screen

必须运行两条且各只运行一次：

```text
V2-B = bottom approximate R5 action / top exact direct inverse
V2-T = bottom exact direct inverse / top approximate R5 action
```

对应 modal Schur 必须分别为：

```math
\widetilde S_m^{(B)}
=
G-P_bM_b^{-1}T_b-P_tA_t^{-1}T_t,
```

```math
\widetilde S_m^{(T)}
=
G-P_bA_b^{-1}T_b-P_tM_t^{-1}T_t.
```

## 6.1 外层设置

```text
solver                    = right FGMRES
restart                   = 90
maximum iterations        = 20
initial guess             = zero
operator                  = exact monolithic Hybrid
residual authority        = explicitly recomputed Hybrid true residual
```

至少保存 iteration：

```text
0, 1, 2, 5, 10, 15, 20
```

的：

- global Hybrid true residual；
- bottom block residual；
- top block residual；
- modal equation residual；
- reported residual；
- PC apply count；
- exact-side solve count；
- approximate-side one-apply count。

## 6.2 单侧 Gate

每条单侧 screen 必须满足：

```text
all residuals finite                 = true
outer iterations                     = 20 boundary or earlier convergence
true Hybrid residual at 20           < 0.35
minimum true residual through 20     < 0.35
last 5 sampled steps net decrease    = true
no global direct fallback            = true
ordinary default                     = unchanged
swap                                 = 0
```

不要求单调逐步下降，但最后阶段必须有净下降，不能在 1 附近停滞或数量级放大。

## 6.3 单侧运行边界

- 若第一条只是数值负结果而非 NaN/资源终止，仍允许运行另一条，目的是获得 side-specific evidence；
- 若第一条发生 implementation identity failure、NaN/Inf、内存安全终止或遗留进程，修复同一实现后只能重跑该条，不得改算法；
- 两条完成后不得立即调参数。

分类：

| V2-B | V2-T | 分类 | 后续 |
|---|---|---|---|
| pass | pass | `ONE_SIDED_BLOCK_CAPACITY_PASS` | 进入 V2-3 |
| pass | fail | `TOP_APPROXIMATE_SIDE_NEGATIVE` | 停止等待 review |
| fail | pass | `BOTTOM_APPROXIMATE_SIDE_NEGATIVE` | 停止等待 review |
| fail | fail | `R5_BLOCK_PC_FAMILY_CLOSED_ONE_SIDED` | Task37b 数值研究收口 |

不得因为一侧失败就扫描 shift、ILU level、restart、Woodbury damping 或 modal count。

---

# 7. V2-3：双侧 20/100/200-step 漏斗

只有 V2-B 与 V2-T 都通过，才允许双侧：

```text
bottom inverse = one fixed R5 action
 top inverse   = one fixed R5 action
```

双侧 modal Schur 为：

```math
\widetilde S_m
=
G-P_bM_b^{-1}T_b-P_tM_t^{-1}T_t.
```

## 7.1 运行顺序

严格按：

```text
20 steps
→ Gate
100 steps
→ Gate
200 steps
→ Gate
stop for review
```

每一级必须是同一参数、同一 operator、同一 PC identity。允许从前一级 checkpoint
继续，但必须证明 continuation 与 clean replay 在共同 monitor 点一致；否则每级 clean run。

## 7.2 冻结设置

```text
outer                     = right FGMRES
restart                   = 90
rtol                      = 1e-6
maximum for this review   = 200
local inverse             = one fixed R5 action per call
modal Schur               = fixed 240×240 complex128 LU
global direct factor      = 0
bottom/top direct factor  = 0/0
```

## 7.3 漏斗 Gate

| 阶段 | Hybrid true residual Gate | 额外条件 |
|---:|---:|---|
| 20 | `< 0.35` | finite，明显净下降 |
| 100 | `<= 0.12` | 最近 40 步净下降 |
| 200 | `<= 0.05` | 最近 40 步净下降，预测总迭代 `<=3000` |

200 步还必须报告：

```text
predicted full iterations
predicted full wall
residual slope over last 40
restart basis bytes
PC setup/apply bytes and wall
```

本审阅**不授权** 200 步之后自动运行 full solve。即使 200-step 全部通过，也要写入
`BLOCK_LEVEL_200_STEP_PASS_AWAITING_FULL_REVIEW` 并停止，等待下一次审阅决定是否进入 H8。

---

# 8. Modal Schur 的构造与审计

## 8.1 同一 action 合同

构造 `\widetilde S_m` 时，对每个 240 modal basis column：

1. 施加对应 `T_s`；
2. 调用与 online block PC 同一 fixed local action；
3. 施加 `P_s`；
4. 写入 240×240 dense matrix。

不得：

- 用 R5 的 300-step local solution构造列；
- 用 exact local direct solve 构造双侧 approximate Schur；
- 根据 direct solution 调整列；
- 删除不利模态；
- 低秩截断或 regularization sweep。

## 8.2 Modal Schur Gate

每条 one-sided/double profile 都报告：

```text
shape                         = 240 x 240
rank                          = 240
condition                     finite and <= 1e12
all entries                   finite
repeat matrix relative error  <= 1e-13
LU repeat solve error         <= 1e-13
build apply count             exact expected count
```

若 full rank 失败，先检查实现和 ownership；不得通过删除 modes 或加经验正则化继续。

---

# 9. 资源与生命周期

## 9.1 必须分开报告的对象

每个 profile至少记录：

```text
bottom/top action-only static Schur caches
bottom/top external DtN C/D/H action states
bottom/top whole-endcap ILU(0) factor
bottom/top W arrays
bottom/top 40x40 K/LU
240x240 approximate modal Schur/LU
T/P coupling blocks
outer FGMRES vectors
exact-side direct factor for one-sided runs
field/recovery objects if any
MPI/PETSc/Python runtime
```

## 9.2 因子身份

预期：

| profile | bottom direct | top direct | bottom ILU0 | top ILU0 |
|---|---:|---:|---:|---:|
| V2-B | 0 | 1 | 1 | 0 |
| V2-T | 1 | 0 | 0 | 1 |
| V2-double | 0 | 0 | 1 | 1 |

必须用 lifecycle inventory证明，不得只根据代码路径推断。

## 9.3 安全阈值与资格边界

本轮 numerical screen 的内存不作为提前否定数值的硬 Gate，但 watchdog 必须：

```text
warning threshold       = 10 GiB
termination threshold   = 14 GiB
timeout one-sided       = 3600 s each
timeout double 20       = 3600 s
timeout double 100/200  = 7200 s each
swap                    = 0
no orphan process       = true
```

同时使用以下解释边界：

```text
MPI8 <= 6.0 GiB    = resource-positive signal
MPI8 <= 5.0 GiB    = engineering-positive signal
MPI8 > 6.0 GiB     = numerical result仍可保留，但不是 resource-qualified
```

R5 standalone 的约 6.28 GiB 只能作背景，不能当作完整 block profile 的预测或分母。

---

# 10. 测试 Gate

## 10.1 新增 focused tests

至少覆盖：

1. fixed R5 callback 与 `woodbury.apply` identity；
2. callback 不调用 nested KSP；
3. callback 线性、确定性、apply count；
4. one-sided approximate modal Schur 与手工 tiny dense oracle；
5. double approximate modal Schur 与手工 tiny dense oracle；
6. exact H3 block-LDU regression仍为 1-step pass；
7. pack/split、ownership、MPI1/2 action identity；
8. factor lifecycle 与 destroy 后 fail-closed；
9. runner flags explicit opt-in，ordinary default unchanged；
10. stop-rule serialization 与 no-official-RTA boundary。

## 10.2 静态检查

```text
ruff check touched files
ruff format --check touched files
python -m compileall touched modules/tests
git diff --check
```

## 10.3 MPI tests

正式 MPI8 screen 前至少运行：

```text
MPI1 tiny block identity
MPI2 fixed callback + modal Schur identity
MPI4 pack/split and lifecycle smoke
```

不得以旧 H3/H4 测试替代新增 approximate-action 测试。

---

# 11. Official physics 与结果边界

V2 只做最多 200 步的 block-level screen，因此：

```text
official Hybrid field       = not_run
official R/T/A              = not_run
official 12+12 comparison   = not_run
Full3D physical comparison  = not_run
```

即使 screen residual明显下降，也不得从未收敛场计算 official R/T/A。

只有未来 full Hybrid true residual `<=1e-6`，且 bottom/top/modal/full-FE residual 与
12+12/场 Gate 全部通过后，才能恢复 official physics。

---

# 12. 严格停止规则

| 停止点 | 分类 | 后续 |
|---|---|---|
| fixed callback identity失败 | implementation failure | 只修同一实现 |
| Task37-extra继承未记录 | review contract failure | 不运行 PDE |
| 任一 modal Schur rank < 240 | implementation/space failure | 停止，不删 mode |
| 两条 one-sided均失败 | R5 block PC family closed | Task37b 收口 |
| 单侧一正一负 | side-specific negative | 停止等待 review |
| double 20失败 | double block PC negative | 不运行100 |
| double 100失败 | double block PC negative | 不运行200 |
| double 200失败 | block PC long-tail negative | 不运行full |
| double 200通过 | bounded positive | 停止等待 full-solve review |
| memory/timeout安全终止 | resource boundary | 保存证据，停止 |

禁止自动追加：

```text
LOR / AMS / HX
p2 / p4 / p-multigrid
new modal coarse
new sampled Schur family
new Schwarz partition
shift / overlap / ILU fill sweep
restart sweep
M sweep
angle or polarization sweep
0.7 nm PDE
```

---

# 13. 必须交付的记录

更新：

```text
docs/task037b_hybrid_fem_modal_iterative/outcomes/one_sided_replacement.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/double_iterative_funnel.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/resource_ledger.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/summary.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/test_summary.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/changed_files.md
docs/development_progress.md
```

新增：

```text
docs/task037b_hybrid_fem_modal_iterative/response_v3.md
benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v2_block_pc_screen_v1.json
```

compact record 必须包含：

- source SHA；
- exact branch/physics/discretization identity；
- Task37-extra LOR/HX inherited closure；
- fixed callback certificate；
- modal Schur rank/condition/hash；
- one-sided完整 residual histories；
- double 20/100/200 status；
- factor inventory/lifecycle；
- RSS/PSS/USS/swap/wall；
- raw artifact相对路径和 SHA256；
- explicit stop classification；
- official physics全部 `not_run`。

---

# 14. 合入边界

本审阅不授权 merge 到 master。

无论结果正负：

- ordinary direct Hybrid default保持不变；
- R5 standalone negative和V2 block screen都保留在 research branch；
- 不得把未完成 full solve 的 block PC称为 production solver；
- 不得整体 merge Task37b 分支；
- 后续是否选择性保留 block operator、Matrix-free endcap action或Woodbury基础设施，等待最终 review。

---

# 15. 最终执行顺序

```text
V2-0  读取本 review、response_v2 和 Task37-extra 最终 LOR/HX 负证据
V2-1  建立 one-apply fixed R5 callback；完成线性/确定性/action identity
V2-2  构造并运行 V2-B 单侧 20-step
V2-2  构造并运行 V2-T 单侧 20-step
       若不是双侧都 pass，写 response_v3 并停止
V2-3  双侧 fixed R5 block PC：20-step
       pass 后 100-step
       pass 后 200-step
       无论 200 pass/fail，写 response_v3 并停止
```

本轮唯一允许回答的问题是：

> R5 固定 action 作为完整 Hybrid block-LDU 的近似局部逆，是否具有真实的 block-level
> FGMRES 容量？

若答案仍是否定的，Task37b 应接受以下结论并收口：

```text
exact Hybrid matrix-free block operator = pass
exact block-LDU                         = pass
DtN Woodbury algebra                    = pass
low-memory approximate endcap inverse   = not demonstrated
```
