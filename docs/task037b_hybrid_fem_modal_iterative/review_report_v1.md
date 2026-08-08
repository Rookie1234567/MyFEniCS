# Task037b Review Report V1：H5 负结果复核与 DtN-aware whole-endcap inverse

## 0. 审阅身份与授权边界

```text
review                         = Task037b Review Report V1
reviewed_branch                = codex/20260807-task37b-hybrid-iterative-development
reviewed_response              = docs/task037b_hybrid_fem_modal_iterative/response_v1.md
reviewed_H5_source             = 216437c6f13b3a3bf46e74451f63779189453c6f
ordinary_default               = unchanged
merge_to_master                = not_authorized
H5_original_classification     = LOCAL_INVERSE_FAMILY_NEGATIVE
narrow_followup_authorized     = true
new_general_PC_campaign        = forbidden
```

本报告接受 H5b 的受控负结果，但不接受将其解释为 Hybrid 方程、Matrix-free DtN、
静态凝聚或 block-LDU 计算错误。

本轮只批准一个证据驱动的窄修复族：

```text
whole-endcap ILU(0) base inverse
+ exact 40-mode Matrix-free DtN Woodbury correction
```

禁止重新打开 p2/p4、modal coarse、strong trace、exact trace、AMS/HX、RCWA、M 扫描、
角度扫描、overlap/shift 扫描或新的 Krylov 家族。

---

# 1. 审阅结论

## 1.1 已通过的部分

现有证据已经形成完整的正确性链：

| 阶段 | 结果 | 结论 |
|---|---|---|
| H1 | direct Hybrid true residual 约 `1.45e-12`，12/12+12/12、场与 R/T/A 通过 | Hybrid 物理与当前 direct authority 正确 |
| H2a | assembled Hybrid block action identity 通过 | block mapping 与 coupling 正确 |
| H2b | Matrix-free local endcap action identity 约 `1e-16` | local Schur + external DtN action 正确 |
| H3 | exact block-LDU，outer=1，global true residual 约 `2.89e-12` | block-LDU 代数正确 |
| H4a | exact modal Schur，outer=1 | modal Schur 公式正确 |
| H5a | bottom/top exact local inverse 各 11/11，残差约 `2e-12` | local action 与 RHS 接线正确 |

因此，当前不能写成：

```text
Hybrid iterative calculation is wrong
```

准确结论是：

```text
current H5b approximate local inverse is numerically ineffective
```

## 1.2 H5b 的失败强度

H5b 的冻结配置为：

```text
x-axis 6 slabs
0.125 overlap
partition-of-unity ASM
shifted ILU(0)
one ASM apply per PC apply
right FGMRES restart 30 / max_it 300
```

其结果为：

- bottom 非零 RHS：`0/10` 通过；
- top RHS：`0/11` 通过；
- random RHS 最终 true residual 约 `0.93–0.94`；
- modal RHS 最终 true residual 约 `0.02–0.037`；
- stationary correction 多次施加后可把残差放大到数百至数千倍。

这不是增加 max iteration 或 restart 就能可靠修复的轻微收敛不足。

---

# 2. 最可能的根因

## 2.1 预条件器近似的是 fine FE Schur，而外层求解的是含 DtN 的 endcap operator

每侧精确 local endcap operator 为：

```math
A_s
=
F_s-C_sH_s^{-1}D_s,
\qquad s\in\{b,t\}.
```

H5b 的局部 factors 从 `static_condensation.condensed` 的 cell-Schur contributions 构造，
主要近似 $F_s$；外层 KSP 的 MatPython operator 则是完整的 $A_s$。

因此当前实际是：

```text
PC approximates F_s^{-1}
operator requires (F_s - C_s H_s^{-1} D_s)^{-1}
```

每侧只有 40 个外部 DtN 模态，但该反馈在短 endcap 上相对显著，不能仅凭“rank 小”而忽略。

## 2.2 六个横向 slab 可能破坏短 endcap 的主要耦合

每侧只有约 8424 个 active rows，却有约 16.48M 个 source/factor NNZ。完全静态凝聚后，
单元 trace block 很宽。把短 endcap 再沿周期横向 $x$ 切成 6 块，会切断：

- 高阶 trace 的宽耦合；
- 材料横截面的全局耦合；
- Floquet 周期首尾耦合；
- external DtN 产生的非局部边界反馈。

Task037 的 M3a 还包含 coarse correction 和更完整的两层动作；H5b 只有一次 bare ASM，
不能把两者视为同一个预条件器。

## 2.3 本轮修复目标

下一步不是继续微调六个 slab，而是回答两个确定问题：

1. 六-slab H5b 是否连 $F_s$ 本身都无法预条件？
2. 若使用整个 endcap 的 ILU(0)，再显式补回 40-mode DtN 低秩反馈，是否能得到可靠局部逆？

---

# 3. V1-R0：冻结证据与组件身份

开始修改前，Codex 必须：

1. fast-forward 到本 review commit；
2. 确认 branch/upstream/clean status；
3. 保留 H5b 原始负结果，不覆盖 `response_v1.md`；
4. 新建后续回应 `response_v2.md`；
5. 不修改 H1–H5 已有记录中的实测值。

所有新建或修改 Markdown 的独立公式继续使用 fenced `math` block。

---

# 4. V1-R1：先做 operator 分解 identity

在真实 p6/h10 endcap 上，必须显式暴露但不物化全局矩阵的四个 action：

```text
F_s action
C_s action
D_s action
H_s solve
```

验证：

```math
A_sx
=
F_sx-C_sH_s^{-1}D_sx.
```

至少对：

```text
3 deterministic random probes
physical RHS
2 fixed modal-traction probes
```

验证 bottom/top：

```text
relative action error <= 1e-11
repeat error          <= 1e-12
all values finite     = true
```

必须使用 live `PetscCondensedBlocks` / Matrix-free C/D action 的真实符号约定；
禁止根据文档手工改变 C、D 的正负号或共轭约定。

若 identity 失败，分类为：

```text
DTN_COMPONENT_DECOMPOSITION_IMPLEMENTATION_FAILED
```

只允许修复同一实现，不能进入下列预条件器试验。

---

# 5. V1-R2：六-slab F-only 诊断

这一阶段只用于定位根因，不是生产候选。

保持 H5b 完全相同的：

```text
6 slabs
0.125 overlap
partition weights
inherited shift sign and magnitude
ILU(0)
restart 30
max_it 300
same 11 RHS per side
```

唯一变化：外层 local KSP operator 暂时改为 $F_s$，不含 external DtN correction。

记录每个 RHS 的：

```text
reason / iterations
reported residual
explicit F-only true residual
1/2/4/8 stationary corrections
repeat error
```

诊断解释：

| 结果 | 解释 |
|---|---|
| F-only 全部或绝大多数通过，而完整 $A_s$ 失败 | missing DtN feedback 是主要根因 |
| F-only random/modal 仍接近 H5b 平台 | 六-slab decomposition 本身不够强 |
| F-only 仅 modal 通过、random 失败 | 当前 PC 只覆盖特定接口载荷，不是通用 local inverse |

该阶段不得据结果调整 slab、overlap、shift、restart 或 max_it。

---

# 6. V1-R3：whole-endcap ILU(0) 基线

## 6.1 唯一冻结配置

每侧改为一个完整 endcap subdomain：

```text
num_subdomains = 1
rows           = all active endcap rows
overlap        = 0
factor         = ILU(0), factor-only
shift          = exactly the inherited H5 shift; no scan
```

这不是 MUMPS/SuperLU direct LU。它仍然只保留原稀疏模式上的 ILU(0)，不允许 fill-level 扫描。

必须复用现有 owner-local assembly/factor lifecycle，不创建第二套通用 Schwarz framework。

## 6.2 两个诊断

对同一 11 RHS/side，依次运行：

```text
R3-F = whole-endcap ILU(0) preconditioning F_s
R3-A = whole-endcap ILU(0) preconditioning complete A_s, without Woodbury
```

两侧顺序执行并及时释放 factor，避免诊断阶段 bottom/top factors 不必要地同时驻留。

报告：

```text
rows / matrix NNZ / factor NNZ
factor payload estimate
setup/apply/solve wall
RSS/PSS/USS/process-tree peak
reason/iterations/true residual per RHS
```

此处不设新的参数分支；结果只用于量化：

- 去掉人工 6-slab 切分的收益；
- external DtN 对 local convergence 的额外影响。

---

# 7. V1-R4：exact DtN Woodbury oracle

## 7.1 数学身份

对：

```math
A_s
=
F_s-C_sH_s^{-1}D_s,
```

若 $F_s^{-1}$ 精确，则：

```math
A_s^{-1}
=
F_s^{-1}
+
F_s^{-1}C_s
\left(H_s-D_sF_s^{-1}C_s\right)^{-1}
D_sF_s^{-1}.
```

定义：

```math
W_s
=
F_s^{-1}C_s,
```

```math
K_s
=
H_s-D_sW_s.
```

则对 RHS $r$：

```math
z
=
F_s^{-1}r,
```

```math
q
=
K_s^{-1}D_sz,
```

```math
x
=
z+W_sq.
```

## 7.2 Oracle 实现边界

允许临时：

- 物化 test-only explicit $F_s$；
- 对 $F_s$ 使用一次 local MUMPS direct factor；
- 逐个对 40 个 modal basis vector施加 Matrix-free $C_s$，得到 C columns；
- 使用 Matrix-free $D_s$ 构造 $D_sW_s$；
- 对 $K_s$ 使用 complex128 dense LU/SVD audit。

禁止：

- 在 production candidate 中保留 $F_s$ direct factor；
- 物化 full global Hybrid matrix；
- 将 external auxiliary rows重新放回 Krylov unknown；
- 手工重写端口模式或减少 40-mode set。

## 7.3 Oracle Gate

对 bottom/top 的所有非零冻结 RHS，比较 Woodbury result 与 H5a exact $A_s^{-1}$：

```text
solution relative error     <= 1e-10
complete A_s true residual  <= 1e-10
repeat error                <= 1e-12
K_s rank                    = 40
K_s condition               finite and <= 1e10
normal equations            = false
```

bottom 的零 physical RHS 单独记录，不计入容量通过数量。

若失败，分类为：

```text
DTN_WOODBURY_ORACLE_IMPLEMENTATION_FAILED
```

只允许修复 action、ownership、符号或生命周期，不允许跳过 oracle直接实现近似 candidate。

Oracle 通过后立即释放 explicit $F_s$、MUMPS factor、临时 columns和 exact solution carriers。

---

# 8. V1-R5：唯一的 approximate Woodbury candidate

## 8.1 Base inverse

令 $B_s^{-1}$ 为 R3 的 whole-endcap shifted ILU(0) action。构造：

```math
W_{B,s}
=
B_s^{-1}C_s,
```

```math
K_{B,s}
=
H_s-D_sW_{B,s}.
```

固定预条件器为：

```math
M_s^{-1}r
=
B_s^{-1}r
+
W_{B,s}K_{B,s}^{-1}D_sB_s^{-1}r.
```

这不是 exact inverse；它是一个 DtN-aware、固定线性的近似逆。

每侧额外 dense storage 预期主要是：

```math
8424\times40\times16
\approx
5.14\ \mathrm{MiB}
```

以及一个 $40\times40$ complex128 小矩阵。必须报告实测/实际 `.nbytes`，不得只引用理论值。

## 8.2 固定配置

```text
fine operator  = exact Matrix-free A_s
outer local KSP= right FGMRES
restart        = 30
max_it         = 300
rtol           = 1e-10
atol           = 0
base PC        = one whole-endcap inherited-shift ILU(0)
DtN correction = one fixed 40-mode Woodbury correction
```

禁止扫描：

```text
shift
ILU level
subdomain count
overlap
restart
max_it
Woodbury damping
mode subset
```

## 8.3 Algebra and legality Gate

必须通过：

```text
fixed-PC linearity relative error    <= 1e-11
fixed-PC determinism relative error  <= 1e-12
repeat solution relative error       <= 1e-12
K_B rank                             = 40
K_B condition                        finite and <= 1e10
all arrays finite                    = true
no direct fallback                   = true
```

## 8.4 Standalone local inverse Gate

对 bottom 10 个非零 RHS和 top 11 个 RHS全部要求：

```text
converged reason > 0
iterations       <= 300
explicit complete-A true residual <= 1e-8
swap             = 0
```

bottom 的零 physical RHS只作零方程检查，不得用于增加 pass count。

### Borderline 状态

若全部 physical/modal RHS 达到 `1e-8`，但 random RHS仅达到 `1e-5` 至 `1e-8`，记录：

```text
DTN_WOODBURY_LOCAL_INVERSE_BORDERLINE
```

并停止等待复审；不得自行进入 H6，也不得放宽正式 Gate。

### 负结果

若任一侧多数 random RHS仍高于 `1e-2`，或 modal RHS仍高于 `1e-3`，记录：

```text
WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE
```

关闭本轮 local inverse follow-up，不再调参。

---

# 9. V1-R6：通过后恢复 H6–H10

只有 R5 完整通过，才恢复原 task.md 的 H6–H10 顺序。

## 9.1 H6 单侧替换

依次运行：

```text
bottom Woodbury-iterative / top direct
top Woodbury-iterative / bottom direct
```

继续使用 exact Hybrid operator和 right FGMRES。沿用 task.md 原 20/100/200 funnel，
不修改阈值。

## 9.2 H7 双侧 iterative

由同一个固定 $M_b^{-1}$、$M_t^{-1}$ 构造：

```math
\widetilde S_m
=
G-P_bM_b^{-1}T_b-P_tM_t^{-1}T_t.
```

只构造一次 $240\times240$ complex128 modal Schur；不得使用 direct local factor或根据
当前 residual重构。

## 9.3 H8–H10

若 H7 200-step通过，再按原任务书执行：

- MPI8 full numerical qualification；
- restart 90→60→40→20；
- MPI4/MPI1 resource runs；
- 一个已冻结的 Task036 model-error separation case。

原数值、场、12+12、R/T/A和内存 Gate全部保持不变。

---

# 10. 资源与生命周期 Gate

R3–R5 必须分阶段记录：

```text
retained local Schur cache
whole-endcap ILU factor NNZ/payload
W_B storage
K_B storage/factor
FGMRES vectors
external DtN state
field/recovery cache
MPI/PETSc runtime
```

必须同时报告：

```text
process-tree RSS
worker RSS/PSS/USS
cgroup current/peak if available
swap
stage timestamps
```

R5 standalone local qualification的资源不是最终 H9 whole-Hybrid资源结论，但必须满足：

```text
swap = 0
no memory termination
no timeout termination
```

若 R5 MPI8 process-tree peak 超过 `7.0 GiB`，即使数值通过也先记录：

```text
NUMERICAL_PASS_RESOURCE_REVIEW_REQUIRED
```

不得自动进入 H6，等待复审。该阈值不是 production claim，而是防止新 candidate 比失败的
H5b（约 6.763 GiB）显著更重。

---

# 11. 测试要求

## 11.1 轻量代数测试

至少新增或整理：

```text
Matrix-free A = F - C H^-1 D identity
exact Woodbury dense/sparse fixture
MPI ownership for C/D columns and W
whole-endcap one-subdomain assembly/factor lifecycle
approximate Woodbury linearity/determinism
K/K_B rank and condition audit
```

使用职责清晰的 Task037b test文件；不得把所有逻辑继续堆入 runner contract test。

## 11.2 MPI

至少运行：

```text
serial tiny oracle
MPI2 action/ownership
MPI4 action/ownership
```

正式 R2–R5 使用 MPI8 frozen p6/h10。

## 11.3 静态检查

所有 touched Python files：

```text
ruff check
ruff format --check
python -m compileall
git diff --check
```

不得自动放宽测试阈值或增加 xfail。

---

# 12. 文档与证据

完成后更新：

```text
docs/task037b_hybrid_fem_modal_iterative/outcomes/local_endcap_inverse_matrix.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/resource_ledger.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/test_summary.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/changed_files.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/summary.md
docs/development_progress.md
```

新增：

```text
docs/task037b_hybrid_fem_modal_iterative/response_v2.md
```

建议将 R1–R5 的 compact record放在：

```text
benchmarks/cases/101_hybrid_iterative_block_solver/records/
```

但只有 R5 数值通过后，才把 Case101 标成 active candidate；否则保持 research closeout record。
重型 matrix、factor、timeline、fields仍留在 `benchmarks/artifacts/task037b/`，不得提交 Git。

---

# 13. 最终停止规则

| 停止点 | 分类 | 后续 |
|---|---|---|
| R1 identity失败 | implementation failure | 只修同一 action decomposition |
| R2 F-only失败 | six-slab decomposition negative | 仍允许唯一 R3 whole-endcap test |
| R4 exact Woodbury失败 | implementation failure | 只修同一 formula/ownership |
| R5正式 Gate通过 | local inverse pass | 恢复 H6–H10 |
| R5 borderline | review required | 不进入 H6 |
| R5数值失败 | Woodbury local inverse negative | 关闭，不调参 |
| R5数值通过但 peak>7 GiB | resource review required | 不进入 H6 |

禁止在 response 中自动增加：

```text
second shift
second overlap
second ILU level
second subdomain count
p2/p4/AMS/coarse family
new external mode count
new wavelength/angle/polarization
```

---

# 14. 本轮最终主审判断

```text
Hybrid/direct/block algebra            = accepted
Matrix-free local endcap action         = accepted
H5 exact local reference                = accepted
H5 six-slab bare ASM local inverse      = accepted controlled negative
root cause                              = PC/operator mismatch plus artificial decomposition, not proven solver algebra error
narrow follow-up                        = authorized
follow-up candidate                     = whole-endcap ILU(0) + 40-mode DtN Woodbury
parameter sweep                         = forbidden
H6-H10                                  = conditional on R5 full pass
master merge                            = not authorized
ordinary default                        = unchanged
```
