# Task037b Review Report V6：牵引一致性对齐的高精度线性复核与最终物理闭环

## 0. 审阅身份与授权边界

```text
review                              = Task037b Review Report V6
reviewed_branch                     = codex/20260807-task37b-hybrid-iterative-development
reviewed_response                   = docs/task037b_hybrid_fem_modal_iterative/response_v6.md
reviewed_formal_source              = 892f186b39c0eb89f1912640430fd79599d86318
reviewed_postprocessor_correction   = 11c01d5268f1e0fc8eb307945179b540ccfcb2aa
ordinary_default                    = unchanged
merge_to_master                     = not_authorized
same_PC_candidate                   = retained
same_candidate_tight_requalification= authorized_once
linear_qualification_threshold      = 5e-9
exact_traction_gate                 = unchanged_at_1e-8
outer_restart                       = unchanged_at_90
outer_max_it                        = 1000
full_recovery_and_official_physics  = authorized_after_tight_linear_gate
conditional_direct_authority_export = authorized_after_candidate_own_physics_pass
restart_sweep                       = not_authorized
MPI1_or_MPI4_full                   = not_authorized
resource_optimization               = not_authorized
new_PC_family                       = forbidden
LOR_HX_reopen                       = forbidden
production_qualification            = not_authorized
```

本报告接受 Review V5 的历史结论，不覆盖或改写旧记录：

```text
MULTIMETRIC_LINEAR_PASS_RECOVERY_OR_PHYSICS_FAIL
```

V5 在冻结候选上已经取得以下结果：

| 层次 | V5 结果 |
|---|---|
| 五项线性残差 | `557` 步全部 `<=1e-6` |
| external q recovery | bottom/top identity 均为 `0`，通过 |
| full-FE recovery | bottom/top 通过 |
| sampled interface E | bottom/top 约 `5.1e-7 / 5.4e-7`，通过 |
| energy diagnostic | closure 约 `-1.00e-6`，通过既有诊断 Gate |
| exact traction dual | bottom/top `9.609e-7 / 4.563e-7`，未通过冻结 `1e-8` Gate |
| official physics | 因 traction Gate fail-closed，全部 `not_run` |
| MPI8 process-tree RSS | `7.0496 GiB`，资源负结果 |

V5 不是线性求解失败，也不是 Hybrid 模型、Matrix-free DtN、Woodbury 或 block-LDU 失败。
本轮只回答一个决定性问题：

> 当同一候选的线性误差进一步降低到明显小于 `1e-8` 时，exact variational traction dual
> 是否随之通过冻结的 `1e-8` 物理一致性 Gate？

V6 不允许放宽 traction Gate，不允许改变 PC，也不允许在失败后继续逐轮收紧容差。V6 是
该解释的唯一决定性验证。

---

# 1. V5 的科学解释

## 1.1 线性求解与恢复已经通过

V5 的最终五项残差为：

| residual | V5 final |
|---|---:|
| reported | `6.457740108721289e-7` |
| global true | `6.45774010063497e-7` |
| bottom block true | `9.811891391712585e-7` |
| top block true | `4.5634977013685214e-7` |
| modal block true | `1.3354878193519844e-15` |

KSP reason 为正，history 严格连续为 `0..557`，每步只有一条 exact residual row，postsolve
retained-solution audit 也通过。bottom/top direct factors 为 `0/0`，ILU factors 为 `1/1`，
没有 nested local KSP、direct fallback、global A/F 或显式 external C/D。

因此 V6 不重新讨论算法架构，只改变资格精度。

## 1.2 Traction dual 与局部块残差同阶

V5 的 exact traction dual 与最终 block residual 为：

| side | block true residual | exact traction dual | traction / block |
|---|---:|---:|---:|
| bottom | `9.811891391712585e-7` | `9.609121539153052e-7` | `0.9793342746607653` |
| top | `4.5634977013685214e-7` | `4.5634977013685214e-7` | `1.0` |

这个比例只作为当前冻结案例的经验诊断，不能外推成通用定理；但它明确表明 V5 的
traction failure 与尚存的 algebraic block residual 同阶，而不是出现了独立的
`O(1)` traction discontinuity。

H1 direct Hybrid authority 的对应界面牵引残差约为 `1e-12`，说明当前物理模型和离散公式
本身可以远低于 `1e-8`。因此最小且可证伪的下一步是保持 traction Gate 不变，仅收紧线性
误差。

## 1.3 为什么目标选为 `5e-9`

冻结物理 Gate 为：

```text
exact traction dual <= 1e-8
```

V6 将五项线性资格目标冻结为：

```text
reported/global/bottom/top/modal <= 5e-9
```

其目的不是提高物理要求，而是给 `1e-8` traction Gate 留出约 2 倍余量，避免在阈值附近
因恢复、归一化或浮点扰动产生再次边缘失败。

根据 V5 后期数据：

```text
bottom residual at i500 = 3.4111266901058858e-6
bottom residual at i557 = 9.811891391712585e-7
```

得到经验每步因子约 `0.9784`；使用较短后期窗口得到约 `0.9802`。据此，达到 `5e-9`
预计总迭代约为 `800--825`。因此 `max_it=1000` 是安全余量，不是参数扫描。

## 1.4 V6 的决定性边界

若五项线性残差已经全部 `<=5e-9`，但 exact traction dual 仍有任一侧 `>1e-8`，必须记录：

```text
TIGHT_LINEAR_PASS_EXACT_TRACTION_FAIL
```

并立即停止。此时不得：

- 再把线性目标收紧到 `1e-10`；
- 放宽 traction Gate；
- 改变 traction 定义；
- 改 shift、ILU、overlap、M 或 DtN mode count；
- 发明新的 PC 候选来掩盖 physics Gate。

该结果将说明 traction dual 不能仅由当前 algebraic residual 解释，需要单独研究其离散或
资格定义；但不属于本轮范围。

---

# 2. 唯一允许的求解器变化

## 2.1 完全冻结的物理与算法身份

以下内容必须与 V5 相同：

```text
wavelength                     = 13.5 nm
polarization                   = S
incident grazing angle         = 10 deg
bottom/top interface           = 10 / 110 nm
endcap FE degree / mesh        = p6 / h10
modal FE degree / mesh         = p6 / h10
requested modes                = M120
modal unknowns                 = 240
external DtN modes/endcap      = 40
assembly backend               = assembly_time_static_condensed
internal propagation model     = full3d_uniform_cg
internal traction model        = scalar_cg_discrete_derivative
MPI                            = 8
outer operator                 = exact monolithic Hybrid MatPython action
outer KSP                      = right FGMRES
restart                        = 90
initial guess                  = zero
bottom/top subdomains          = 1 / 1
overlap                        = 0 / 0
ILU level                      = 0
bottom/top direct factor       = 0 / 0
bottom/top approximate action  = one fixed whole-endcap ILU(0) + 40-mode Woodbury apply
nested local KSP               = false
normal equations               = false
ordinary defaults              = unchanged
```

不得改变任何一项。

## 2.2 V6 资格参数

唯一变化为：

```text
multimetric threshold = 5e-9
PETSc rtol metadata   = 5e-9
atol                  = 0
max_it                = 1000
```

自定义 convergence test 只有在以下五项同时通过时才可返回正 reason：

```text
reported <= 5e-9
global   <= 5e-9
bottom   <= 5e-9
top      <= 5e-9
modal    <= 5e-9
```

其中所有值必须 finite 且非负。

若 `iteration < 1000` 且未全部通过，必须继续；若达到 `1000` 仍未通过，返回
`DIVERGED_MAX_IT`。不得因 reported/global 单独通过而提前停止。

## 2.3 不允许 warm start 或 continuation

正式 V6 必须从零初值重新运行。同一候选的 V5 解不能作为初值，也不能从 iteration 557
继续。这样才能证明 V5/V6 唯一数值差异是资格精度，而不是不同初值或隐藏 continuation。

---

# 3. 实施前测试 Gate

## 3.1 纯函数 convergence tests

新增或扩展测试，至少覆盖：

1. 重放 V5 iteration 557 的五项残差，在 V5 `1e-6` Gate 下为 pass，在 V6 `5e-9` Gate 下必须为 `ITERATING`；
2. 五项均为 `4e-9` 时返回正 convergence reason；
3. 任一项为 `6e-9` 时继续迭代；
4. NaN、Inf 或负值返回 fail-closed；
5. iteration `1000` 仍未通过时返回 `DIVERGED_MAX_IT`；
6. custom reason identity 明确记录为 `traction_aligned_multimetric_true_residual_gate`；
7. monitor 与 convergence test 不得对同一步重复施加 exact residual action；
8. KSP 返回后 retained solution 必须独立重算五项 residual，防止 false positive。

## 3.2 Traction-alignment calibration record

在不运行 PDE 的前提下，从 V5 compact/raw evidence 只读重算：

```text
bottom traction/block ratio
top traction/block ratio
V5 final linear values
V5 exact traction values
late-window convergence factors
predicted iteration interval to 5e-9
```

这些字段写入 V6 compact record，角色必须标为：

```text
case-specific calibration diagnostic, not a universal bound
```

不得用预测值代替正式 iteration 数据。

## 3.3 Parent watchdog/evaluator regression

V5 formal 后已经修正 parent 状态合同。正式 V6 前必须测试：

- 正常 worker natural exit 和 terminal zero-worker drain 不被误判为 authority unreadable；
- observed all-live rows 的 zero-swap audit 与 immutable parent summary 分开记录；
- physics fail 时 energy diagnostic 不得冒充 official physics；
- physics pass 时 official lane 可以按 dependency 顺序启动；
- record/evaluator disposition一致；
- 不允许 parent exit code 与 solver numerical/physics status互相覆盖。

## 3.4 既有 action/lifecycle tests

继续覆盖：

- fixed action identity、linearity、determinism；
- 每次 callback恰好一次 Woodbury apply；
- `K` rank/condition；
- approximate modal Schur 与 online action一致；
- outer-ready 时 direct factor `0/0`；
- postsolve residual audit；
- solver/PC释放后 recovery authority仍可用；
- snapshots最终销毁。

完成：

```text
ruff check
ruff format --check
python -m compileall
git diff --check
```

本轮不要求 full repository pytest；若未运行，必须明确记录 `not_run`。

---

# 4. 正式运行规则

## 4.1 运行次数

轻量测试全部通过后，只允许一次正式 MPI8 V6 run。

若在进入 outer KSP 前因纯 launch/path/schema/telemetry wiring 错误停止，可以保留证据后做一次
窄修复；一旦 outer KSP 开始数值迭代，不得为改变结果自动重跑。

## 4.2 Checkpoints

至少记录：

```text
0, 1, 2, 5, 10, 20, 60, 100, 200,
500, 534, 557, 600, 630, 700, 750, 800,
850, 900, 950, 1000, actual convergence iteration
```

每个 checkpoint 至少包含：

```text
reported
global true
bottom true
top true
modal true
multimetric max
KSP reason / custom decision
PC apply count
bottom/top action apply count
elapsed time
```

不得补写未达到的 checkpoint预测值。

## 4.3 线性通过后的对象顺序

五项 `5e-9` Gate 通过后：

1. 保存完整 Hybrid solution；
2. 保存 bottom/top active trace snapshots；
3. 保存 240 个 modal amplitudes；
4. 独立重算最终五项 residual；
5. 销毁 KSP 与 Krylov basis；
6. 释放 bottom/top ILU factors；
7. 释放 bottom/top Woodbury `W/K/LU`；
8. 释放 approximate modal Schur；
9. 保留 exact action、static-condensation recovery authority和已复制的解；
10. 再进行 recovery、traction、field和postprocess。

必须记录每个对象的 before/after inventory，不得只依赖进程退出。

---

# 5. 资格 Gate 顺序

## 5.1 Tight linear Gate

全部必须满足：

```text
KSP converged reason              > 0
iterations                        <= 1000
reported relative residual        <= 5e-9
Hybrid global true residual       <= 5e-9
bottom block true residual        <= 5e-9
top block true residual           <= 5e-9
modal block true residual         <= 5e-9
postsolve explicit audit          = pass
all residuals finite              = true
no direct fallback                = true
```

若未通过，recovery/physics/official输出全部 `not_run_dependency_gate`。

## 5.2 Recovery Gate

保持 exact recovery 公式和既有 identity，不修改实现。至少要求：

```text
bottom/top external q identity relative residual <= 1e-10
mode count/key/uniqueness                         = exact pass
bottom/top full-FE linear residual                <= 1e-8
bottom/top cell-interior relative residual        <= 1e-10
bottom/top cell-interior max absolute residual    <= 1e-10
full global matrix allocated                      = false
```

V6 的 tighter recovery thresholds只用于本轮高精度资格，不改 ordinary defaults。

## 5.3 Own physics Gate

按顺序检查：

1. sampled interface tangential E；
2. exact variational traction dual；
3. energy diagnostic；
4. external orders finite/unique。

exact traction Gate保持：

```text
bottom exact traction dual <= 1e-8
top exact traction dual    <= 1e-8
```

不得改成相对线性残差倍数 Gate，也不得把 sampled magnetic proxy替代 exact dual。

若 tight linear 与 recovery通过而 traction失败，记录
`TIGHT_LINEAR_PASS_EXACT_TRACTION_FAIL` 并停止，不进入 official lane。

## 5.4 Candidate own official physics

只有 own physics全部通过，才允许生成 candidate自身的：

```text
official field
R / T / A_balance
A_volume by material
energy closure
external diffraction orders
12 significant powers
12 significant complex boundary amplitudes
canonical active/full vectors
240 modal amplitudes
selected interface and middle-plane E/H arrays
```

所有阈值沿用 H1、Task035c 和 Case095 冻结接受标准，不创建 V6 特设宽松阈值。

## 5.5 Direct Hybrid authority export

先只读检查旧 H1 raw payload。若 modal/canonical/selected-field数值数组仍缺失，且 candidate own
numerical/recovery/physics/official全部通过，则允许单独运行一次 direct-Hybrid authority-export。

要求：

```text
独立进程
不与 candidate objects 同时驻留
同一 p6/h10、M120、10° S 物理身份
只补齐比较所需 numeric arrays/manifests
不改变 direct solver或 ordinary defaults
不计入 candidate online RSS authority
```

若 export因基础设施失败，可保留 candidate own pass并分类 authority incomplete；不得重跑
candidate PDE。

## 5.6 Independent comparisons

候选进程退出后，由独立只读 checker完成：

- candidate vs direct Hybrid modal amplitudes；
- canonical active/full vectors；
- interface E/H；
- middle-plane E/H；
- 12/12 powers；
- 12/12 complex amplitudes；
- R/T/A/A_volume/closure；
- candidate/direct Hybrid vs pinned Full3D authority。

checker memory不计入 candidate online peak，但其 wall/RSS须单独记录。

---

# 6. 资源与性能口径

V6 仍不是资源优化轮。记录：

```text
process-tree RSS authority
worker simultaneous RSS/PSS/USS
all-live zero-swap readability
stage peaks
ILU factor NNZ/payload
W/K/LU bytes
modal Schur bytes
restart basis estimate
setup / outer / recovery / postprocess / export / checker wall
```

分类保持：

```text
MPI8 resource-positive     <= 6.0 GiB
MPI8 engineering-positive  <= 5.0 GiB
MPI8 stretch-positive      <= 3.77 GiB
```

更长迭代数不改变 restart90 的向量上限，因此不得把迭代增加本身误写成必然增加 Krylov
retained memory。最终以内存实测为准。

即使数值与物理全部通过，但 RSS仍高于6 GiB，也必须写：

```text
numerical and physics pass / MPI8 resource negative
```

---

# 7. 最终分类

## 7.1 完整成功

```text
DOUBLE_APPROXIMATE_MPI8_TIGHT_LINEAR_AND_PHYSICS_PASS
```

要求：

- 五项 `5e-9` 线性 Gate通过；
- recovery通过；
- exact traction双侧 `<=1e-8`；
- candidate own official物理通过；
- direct/Full3D comparison通过；
- 生命周期与证据完整。

资源另行分类。

## 7.2 线性未在1000步内达到

```text
TIGHT_LINEAR_GATE_NOT_REACHED_BY_1000
```

停止，不自动增加max_it。

## 7.3 Tight linear通过但traction仍失败

```text
TIGHT_LINEAR_PASS_EXACT_TRACTION_FAIL
```

这是决定性负结果；不得继续收紧或放宽Gate。

## 7.4 Own physics通过但authority payload无法补齐

```text
TIGHT_LINEAR_AND_OWN_PHYSICS_PASS_AUTHORITY_PAYLOAD_INCOMPLETE
```

保留candidate自身成功，不伪造跨authority comparison。

## 7.5 Custom convergence假阳性

```text
TIGHT_CUSTOM_CONVERGENCE_FALSE_POSITIVE
```

KSP返回正reason，但postsolve五项重算有任一项未通过时使用。

## 7.6 恢复失败

```text
TIGHT_LINEAR_PASS_RECOVERY_FAIL
```

停止，不输出official physics。

---

# 8. 禁止事项与停止边界

本轮禁止：

- restart sweep；
- MPI1/MPI4 full；
- shift、overlap、ILU fill或subdomain扫描；
- M、DtN mode、角度、偏振、p/h扫描；
- LOR、AMS/HX、p-multigrid、full-space ILU；
- 新modal coarse、sampled-Schur或Krylov family；
- 0.7 nm PDE；
- master merge或production promotion；
- traction Gate放宽；
- V6失败后的自动第二次tightening run。

V6完成后必须写：

```text
docs/task037b_hybrid_fem_modal_iterative/response_v7.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/full_mpi8_qualification.md
benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_mpi8_traction_aligned_full_qualification_v1.json
```

并停止等待下一轮审阅。

---

# 9. Codex 最终回报格式

只报告：

```text
implementation source SHA
formal numerical source SHA
formal run count / retry / warm-start / continuation
V6 threshold / restart / max_it
convergence iteration and five final residuals
postsolve five-residual audit
recovery metrics
bottom/top exact traction dual
candidate own official R/T/A/A_volume/closure
12+12 result
canonical/modal/selected-field result
direct authority export status and SHA
Full3D comparison status
process-tree RSS and worker RSS/PSS/USS
zero-swap authority status
stage timings
final numerical / physics / resource disposition
tests and explicit full-pytest boundary
```

不得把 evidence-integrity pass、parent exit code或offline checker exit code冒充完整资格化通过。
