# Task037b Review Report V7：选择性合入 master、远程推送与 Task37c 分支交接

## 0. 审阅身份与授权边界

```text
review                               = Task037b Review Report V7
reviewed_branch                       = codex/20260807-task37b-hybrid-iterative-development
reviewed_final_response               = docs/task037b_hybrid_fem_modal_iterative/response_v8.md
reviewed_successful_solver_source      = ea132d8a31e5ccd6c45fb90bbb9b5f676cd78b0e
reviewed_memory_closeout_head          = b291f3dfdf5f0064ff243038f6809172f811d7aa
reviewed_master_merge_base             = 454df04358bd4e1670ec14c5b0276b430249cd37
branch_compare_at_review               = ahead 63 / behind 0 before this V7 commit
ordinary_default                       = unchanged
whole_branch_merge                     = forbidden
bulk_cherry_pick_of_task37b_history    = forbidden
selective_master_integration           = authorized subject to all Gates
push_origin_master                     = authorized subject to all Gates
Task37c_local_branch_creation          = authorized only after master push
Task37c_remote_branch_push             = authorized only after master push
Task37c_task_md                        = forbidden in this handoff
Task37c_code_or_PDE                    = forbidden in this handoff
master_force_push                      = forbidden
Task37c_force_push                     = forbidden
```

本报告是 Task037b 的最终主审与交接文件。Task037b 的算法研究到此停止；不得继续 M11/M12
微优化，不得重新打开 LOR/HX、p-multigrid、局部参数扫描或新的 PC family。

最终科学分类为：

```text
TASK037B_ACCEPTED_FOR_SELECTIVE_MASTER_INTEGRATION
```

对应的冻结能力分类为：

```text
DOUBLE_APPROXIMATE_MPI8_TIGHT_LINEAR_AND_PHYSICS_PASS_WITH_MPI8_RESOURCE_POSITIVE
```

这里的“accepted”仅针对已经实测的冻结范围，不等于 production 默认、不等于所有角度鲁棒，
也不等于 0.7 nm 已资格化。

---

# 1. 最终科学结论

## 1.1 已通过的冻结方法

本轮成功方法为：

```text
exact monolithic Hybrid matrix-free operator
+ right FGMRES
+ action-consistent block-LDU preconditioner
+ bottom whole-endcap shifted ILU(0) one apply
+ top whole-endcap shifted ILU(0) one apply
+ bottom/top 40-mode Matrix-free DtN Woodbury correction
+ 240 x 240 approximate modal Schur
+ multimetric true-residual convergence
+ post-solve recovery / physics / authority comparison
```

两侧固定近似逆为：

```math
\widetilde A_s^{-1}r
=
B_s^{-1}r
+
W_sK_s^{-1}D_sB_s^{-1}r,
\qquad s\in\{b,t\},
```

其中：

```math
W_s=B_s^{-1}C_s,
\qquad
K_s=H_s-D_sW_s.
```

与 online action 一致的 modal Schur 为：

```math
\widetilde S_m
=
G
-
P_b\widetilde A_b^{-1}T_b
-
P_t\widetilde A_t^{-1}T_t.
```

外层 exact Hybrid 方程没有被近似；近似只存在于右预条件器。

## 1.2 最终 M10 数值、物理与资源结果

冻结身份：

```text
wavelength                  = 13.5 nm
polarization                = S
incident grazing angle      = 10 deg
endcap/modal discretization = p6 / h10
bottom/top interfaces       = 10 / 110 nm
internal modes              = M120 per direction / 240 amplitudes
external DtN modes          = 40 per endcap
MPI                         = 8
outer                       = right FGMRES, restart 90
qualification tolerance     = 5e-9 on all five residuals
```

最终结果：

| 项目 | M10 权威值 | 结论 |
|---|---:|---|
| iterations / reason | `792 / 2` | `CONVERGED_RTOL` |
| reported residual | `3.578062165607276e-9` | pass |
| global true residual | `3.578062144715876e-9` | pass |
| bottom block residual | `4.921856578759462e-9` | pass |
| top block residual | `2.6635965562403923e-9` | pass |
| modal block residual | `1.4561321294580367e-15` | pass |
| exact traction bottom/top | `4.820141813913522e-9 / 2.6635965562403923e-9` | pass |
| recovery / own physics / canonical / lifecycle | `true / true / true / true` | pass |
| R | `0.0007628816277266691` | pass |
| T | `0.6027016338728337` | pass |
| A | `0.39653548449943965` | pass |
| A_volume | `0.39653548508184505` | pass |
| energy closure | `5.82405457194568e-10` | pass |
| process-tree RSS | `6018.57421875 MiB = 5.877513885498047 GiB` | `< 6 GiB` pass |
| swap | observed qualified zero-swap evidence | pass in final closeout |

离线 authority checker 还通过：

- external q bottom/top；
- 80/80 diffraction-order key/finite coverage；
- 12/12 significant powers；
- 12/12 significant complex amplitudes；
- canonical bottom/top active/full 四角色；
- selected interface/middle E/H；
- iterative Hybrid 对冻结 Full3D；
- direct Hybrid 对冻结 Full3D。

raw modal coefficient 逐项 L2 差异不具独立 QEP gauge 不变性，因此只保留为诊断；物理 E/H、
modal magnitude、通道和 R/T/A 才是资格权威。不得在 master 文档中删除该真实诊断，也不得
把它错误表述为逐项 modal coefficient pass。

## 1.3 成功边界

允许声明：

> 对冻结的 13.5 nm、p6/h10、10° 掠射、S 偏振、M120、MPI8 案例，双侧 fixed
> whole-endcap ILU(0) + Matrix-free DtN Woodbury 的 Hybrid block-LDU 迭代法通过了
> tight linear residual、exact traction、场恢复、R/T/A、显著衍射通道、Full3D/direct
> Hybrid 比较和 6 GiB process-tree RSS Gate。

禁止声明：

```text
all-angle robustness
all-polarization robustness
M120 mode-count convergence for every case
continuum or mesh convergence
0.7 nm qualification
MPI1 minimum-memory success
production default readiness
```

这些问题属于后续 Task37c 或更后续任务。

---

# 2. 选择性合入总原则

## 2.1 禁止整体合入历史分支

禁止执行：

```bash
git merge codex/20260807-task37b-hybrid-iterative-development
```

也禁止：

```text
cherry-pick Task37b 的全部 63+ commits
先整体复制分支再删除大部分文件
将两套大型通用 runner 的全部 Task37b campaign 代码原样搬入 master
```

Task37b 分支包含：

- H5 standalone local-solver 负结果；
- V1 R2/R3/R5 诊断；
- V2 单侧 screen；
- V3/V4/V5/V6 多代 qualification campaign；
- M1--M10 内存实验阶梯；
- 多个只服务于历史证据的 parser、watchdog、record schema 与 stop contract。

这些历史必须继续保留在远程 Task37b 分支，但不应全部进入 master 的长期维护表面。

## 2.2 推荐的本地集成方式

Codex 可以使用一个**仅本地、永不推送**的临时 integration branch/worktree，从最新
`origin/master` 开始手工移植；通过全部 Gate 后，将本地 `master` fast-forward 到该集成
HEAD，再推送 `origin/master`。

允许的本地临时分支示例：

```text
local-only/task37b-selective-integration
```

该分支不得推送远程，最终也不得保留为远程 ref。

无论采用本地临时分支还是直接在本地 master 工作，最终 master 历史必须是职责清晰的线性
提交，不能包含 whole-branch merge commit。

## 2.3 Ordinary default 继续不变

合入后必须满足：

```text
direct Hybrid ordinary default              = unchanged
new iterative Hybrid profile                 = explicit opt-in
Task37b frozen qualification profile         = explicit opt-in
unsupported geometry / angle / mode settings = fail closed
```

不得在本次合入中自动把 iterative Hybrid 设为所有 Hybrid case 的默认求解器。

---

# 3. M0：必须合入的文档与项目合同

## 3.1 Markdown 数学标准

必须选择性合入：

```text
docs/markdown_rendering_standard.md
README.md 中对应的一行标准链接/表述
docs/README.md
docs/repository_work_principles.md
相关文档合同测试
```

正式标准继续为：

```text
inline math  = $...$
display math = fenced math block
```

独立公式示例：

````text
```math
A x = b.
```
````

禁止在新改正式文档中使用多行 `$$...$$` 或 `\[...\]`。

## 3.2 Task37b master 文档最小集合

建议进入 master：

```text
docs/task037b_hybrid_fem_modal_iterative/task.md
docs/task037b_hybrid_fem_modal_iterative/review_report_v7.md
docs/task037b_hybrid_fem_modal_iterative/response_v8.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/summary.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/full_mpi8_qualification.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/resource_ledger.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/test_summary.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/changed_files.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/block_operator_identity.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/exact_block_ldu_oracle.md
docs/task037b_hybrid_fem_modal_iterative/outcomes/direct_hybrid_authority.md
```

可以保留 `inherited_baseline_audit.md`，若它仍是 checker/provenance 的直接入口。

默认不合入 master：

```text
response_v0.md ... response_v7.md
review_report_v1.md ... review_report_v6.md
one_sided_replacement.md
double_iterative_funnel.md
local_endcap_inverse_matrix.md
```

这些文件的历史价值由 Task37b 分支永久保留；若 Codex 发现最终 summary 中存在必须依赖其
具体表格的链接，可以只提取必要表格到 final summary，而不是把全部历史链复制到 master。

## 3.3 项目总账

选择性合入完成后更新：

```text
docs/development_progress.md
docs/development_model_registry.md
docs/capability_matrix.md
docs/solver_guide.md 或对应 Hybrid 使用指南
docs/README.md
```

登记：

```text
Task37b status = selective-merge qualified research capability
frozen success = p6/h10, 13.5 nm, 10° S, M120, MPI8
solver         = exact action + fixed ILU0/Woodbury block-LDU FGMRES
numerics       = tight linear + traction + physics pass
resource       = 5.8775 GiB process-tree RSS, MPI8 resource positive
ordinary       = explicit opt-in, default unchanged
next branch    = Task37c planned; task not yet written
```

---

# 4. M1：必须选择性合入的正确性修复

## 4.1 Near-degenerate modal grouping

从：

```text
src/modes/mode_classification.py
src/test/test_hybrid_interface_audits.py
```

合入已通过 H1 authority 的窄修复：让 near-degenerate grouping 与最终 partition row-norm
审计使用一致语义，并保持：

```text
same 1e-6 threshold
fail closed
no retry
no mode deletion
no adaptive tolerance
ordinary mode selection unchanged
```

## 4.2 Direct Hybrid / static recovery 兼容修复

逐 hunk 审阅并仅合入成功路径实际需要的：

```text
src/solvers/hybrid_fem_modal_augmented_direct.py
src/solvers/hybrid_fem_modal_schur_direct.py
src/solvers/hybrid_local_static_condensation.py
src/solvers/hybrid_static_field_recovery.py
```

要求：

- direct Hybrid authority 回归不变；
- static-condensation recovery identity 不退化；
- ordinary direct API 不新增 Task37b campaign 参数；
- 不把 exact direct-factor oracle 变成 iterative production dependency。

---

# 5. M2：必须合入的 exact block action 与 Matrix-free endcap/DtN

## 5.1 Exact monolithic Hybrid action

选择性合入：

```text
src/solvers/hybrid_fem_modal_iterative.py
```

保留：

- exact MatPython Hybrid block action；
- bottom/top/modal pack-split；
- ownership 与 mapping closure；
- no-global-Hybrid-A inventory；
- exact action identity probes所需的最小 API。

不得在公共 API 中暴露历史 campaign status、V2/V3 checkpoint 或 benchmark path。

## 5.2 Matrix-free local endcap action

选择性合入：

```text
src/solvers/hybrid_local_dtn_action.py
```

保留：

- local static-Schur action；
- external Matrix-free DtN action；
- `F/C/D/H` 分解 action；
- condensed RHS；
- external q recovery；
- no materialized local/global `A/F/C/D` inventory；
- deterministic ownership/lifecycle contracts。

不得合入只服务于 R1/R2/R3 campaign 的序列化、screen status 或 runner-specific wrappers。

---

# 6. M3：必须合入的 fixed whole-endcap Woodbury 与 block-LDU

## 6.1 Whole-endcap fixed smoother

从：

```text
src/solvers/hybrid_local_iterative_inverse.py
src/solvers/physical_slab_two_level.py
```

只保留成功最终方法需要的：

```text
one whole-endcap subdomain
zero overlap
shifted ILU(0)
factor-only lifecycle
one fixed smoother apply
factor rows/NNZ/payload telemetry
deterministic linear action
```

明确排除或隔离到 research-only：

```text
six-slab H5 family
standalone 300-step local FGMRES qualification
random/modal RHS campaign matrix
local solver success/failure disposition
parameter-scan helpers
```

建议将最终 fixed smoother 提取为职责清晰的小型公共对象；不要让 production import必须加载
H5 negative campaign逻辑。

## 6.2 DtN Woodbury fixed action

从：

```text
src/solvers/hybrid_local_dtn_woodbury.py
```

保留：

- exact Woodbury algebra identity；
- `HybridLocalDtnWoodburyOracle` 或等价的通用 fixed action；
- `HybridLocalDtnWoodburyFixedAction`；
- distributed `W`、small `K/LU`；
- rank/condition/linearity/determinism diagnostics；
- lifecycle与no-direct-fallback合同。

禁止进入普通公共路径：

```text
HybridLocalDtnWoodburyLocalInverse.solve(...)
standalone nested local FGMRES/KSP
R5 21-RHS qualification runner
R5 negative status machinery
```

若现有模块无法在不保留大量 research-only 类的前提下干净合入，应在集成过程中拆成：

```text
hybrid_local_dtn_woodbury.py              # public fixed action
studies/hybrid_local_dtn_woodbury_r5.py   # research history，留在 Task37b branch
```

master 不需要复制第二个研究文件。

## 6.3 Action-consistent block-LDU

从：

```text
src/solvers/hybrid_fem_modal_block_ldu.py
```

保留：

- `HybridActionModalSchurSystem`；
- same-action modal Schur construction；
- block-LDU PC apply；
- exact outer FGMRES solve；
- five-residual evaluation；
- multimetric convergence decision；
- retained-solution snapshot；
- solver/PC/factor/W/K/Schur release ordering；
- post-release recovery authority；
- final inventory and timing。

建议将下列内容迁移到 tests/studies 或不合入：

```text
H3 direct-factor exact oracle implementation
G-only bounded diagnostic
V2 one-sided screen policy
V3 20/60/100/200 progressive campaign policy
V4/V5 historical disposition strings
benchmark-specific checkpoint callbacks and artifact paths
```

可以保留一个小型 exact block-LDU oracle测试，但不应让最终 public solver模块承担所有历史
campaign职责。

最终 public solver应至少提供一个清晰显式入口，例如：

```text
solve_hybrid_block_ldu_iterative(...)
```

其 profile参数应来自一个不可变配置对象，并默认不被普通 Hybrid入口选中。

---

# 7. M4：必须合入的 M10 生命周期与 canonical 内存优化

M10 成功不是改变方程，而是缩短对象生命周期和避免大临时对象重叠。逐 hunk 合入：

```text
src/solvers/hcurl_canonical_vector_dolfinx.py
benchmarks/canonical_vector_artifacts.py
src/test/test_227_task037_canonical_vector_artifacts.py
```

以及 runner/recovery路径中真正实现以下功能的最小代码：

```text
QEP/recovery前 collective heap cleanup
recovery两侧之间的安全 cleanup
canonical packet audited streaming
bounded one-cell trace expansion
entity-position DoF mask
own-physics heap 在 canonical 前释放
solution/recovery/canonical 生命周期审计
```

禁止把 M1--M9 每一个中间实验 profile 都提升为 master API。Master只需要最终 M10 路径和
能够证明其数值等价、无数据丢失、释放后依然可比较的测试。

`M6 compact full-field lookup`、`M9 cell-major streaming` 等没有形成明确收益的历史实验不应
作为独立 production option进入 master。

---

# 8. M5：Runner、watchdog 与 checker 的合入方式

## 8.1 禁止整体复制两个超大型通用 runner

下列文件在 Task37b 分支累计混入大量历史 campaign逻辑：

```text
benchmarks/run_task032_phase6_augmented.py
benchmarks/run_task033_memory_watchdog.py
```

禁止把分支版本整文件覆盖到 master。

优先方案：从成功 M10 路径提取职责明确的专用入口：

```text
benchmarks/run_task037b_hybrid_iterative.py
benchmarks/run_task037b_hybrid_iterative_watchdog.py
```

专用入口只需要支持：

```text
frozen/explicit opt-in profile construction
source/authority hash binding
MPI launch
multimetric convergence
post-solve release/recovery/physics
process-tree RSS/PSS/USS/swap timeline
final compact record
```

不得支持 H5、V1、V2、V3、V4、V5、M1--M9 的全部历史参数矩阵。

若复用现有通用 runner确实更安全，则只允许逐 hunk 合入共享的、可复用的纯函数，并将
Task37b-specific CLI/parser保持在单独命名空间。无论采用哪种方式，普通 Task032/Task033
现有行为必须通过完整回归。

## 8.2 Offline checker

选择性合入并可重命名为更稳定名称：

```text
benchmarks/task037b_v4_full_qualification_checker.py
```

保留最终需要的：

- immutable online evidence校验；
- M10 compact-record/hash校验；
- q/orders/12+12；
- canonical与selected E/H；
- direct Hybrid/Full3D authority比较；
- independent-QEP gauge边界；
- offline资源不计入online峰值。

移除只服务于旧 V4/V5 controlled-negative schema的兼容分支，除非最终 record checker仍需要
读取历史证据。若保留兼容分支，必须有单元测试且不得影响 final pass语义。

---

# 9. M6：Tests 与 compact authority

## 9.1 建议合入的正向核心测试

至少保留或重构覆盖：

```text
src/test/test_234_task037b_hybrid_block_operator.py
src/test/test_235_task037b_hybrid_local_dtn_action.py
src/test/test_236_task037b_hybrid_block_ldu.py
src/test/test_239_task037b_hybrid_local_dtn_woodbury.py
src/test/test_241_task037b_hybrid_action_modal_schur.py
src/test/test_244_task037b_v5_multimetric_convergence.py
src/test/test_245_task037b_v6_traction_aligned_convergence.py
src/test/test_246_task037b_h1_authority_export.py
src/test/test_227_task037_canonical_vector_artifacts.py
src/test/test_hybrid_interface_audits.py
```

若文件名继续带历史阶段编号可以接受，但测试内容应聚焦公共不变量，而不是 campaign runner
状态字符串。

## 9.2 研究负路线测试的处理

默认不合入：

```text
test_237_task037b_hybrid_local_iterative_inverse.py 的 standalone local-solver campaign部分
test_238_task037b_h5_fixture_helpers.py 的大规模 RHS campaign部分
test_240_task037b_hybrid_local_dtn_woodbury_local_inverse.py
test_242_task037b_v2_block_screen_runner.py
test_243_task037b_v4_full_qualification.py 中只服务旧 negative disposition的部分
```

其中对 fixed action、factor lifecycle、fail-closed真正有公共价值的断言，应提取到更小的正向
测试，而不是整文件复制。

## 9.3 最终 compact records

Master建议只保留：

```text
benchmarks/cases/101_hybrid_iterative_block_solver/README.md
benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_mpi8_traction_aligned_full_qualification_v1.json
benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_memory_optimization_closeout_v1.json
```

中间 V1--V5 records继续留在Task37b远程分支，不复制到master。

不得提交：

```text
ignored raw artifacts
solver_record/timeline/stdout大文件
绝对工作站路径依赖文件
未hash绑定的NPZ/HDF5/XDMF
```

最终 compact record中的绝对路径若只用于历史说明，可以保留为非可执行 evidence 字段；master
运行入口不得依赖该绝对路径。

---

# 10. 建议的 master 提交计划

建议在最新 `origin/master` 上形成下列职责清晰的提交；允许根据依赖适度合并，但禁止一个
超大型 commit：

```text
docs: standardize fenced math rendering

fix(hybrid): align modal grouping and static recovery contracts

feat(hybrid): add matrix-free endcap and fixed DtN Woodbury actions

feat(hybrid): add action-consistent block-LDU iterative solve

perf(hybrid): integrate bounded canonical streaming and lifecycle release

bench(task037b): add frozen MPI8 anchor and independent checker

test(hybrid): add focused iterative and recovery coverage

docs(task037b): record successful qualification and Task37c handoff
```

每个提交必须：

- 有单一职责；
- 不改变 ordinary default；
- 不引入 raw artifact；
- 通过 `git diff --check`；
- 在提交说明中标明 explicit opt-in / frozen qualification边界。

---

# 11. 合入前静态与单元测试 Gate

## 11.1 静态检查

对所有 touched Python files运行：

```bash
ruff check <touched-python-files>
ruff format --check <touched-python-files>
python -m compileall <touched-python-roots>
git diff --check
```

不得通过大范围自动格式化掩盖数值 diff。

## 11.2 Focused serial tests

至少覆盖：

```text
near-degenerate grouping / interface audits
Hybrid block action pack-split and identity
Matrix-free endcap F/C/D/H action and q recovery
fixed Woodbury linearity/determinism/rank/condition
same-action modal Schur
block-LDU PC application
multimetric convergence
traction-aligned convergence
full-FE recovery
canonical streaming and M10 lifecycle
independent authority checker
ordinary direct Hybrid regression
ordinary Full3D/Task032/Task033 runner regression affected by touched hunks
```

不得删除断言、增加 xfail或放宽数值阈值来获得通过。

## 11.3 Focused MPI tests

至少运行：

```text
MPI2: block action + endcap action + Woodbury + modal Schur + lifecycle
MPI4: block action + endcap action + Woodbury + modal Schur + lifecycle
MPI2/MPI4: canonical packet/streaming identity
MPI2: near-degenerate/modal trace identity
```

每个 rank都必须通过；不得只读取 rank0 exit。

## 11.4 Full repository pytest

在 focused Gate全部通过后，必须运行一次无 deselect的完整 repository pytest。

允许的最终状态只有：

```text
PASS: zero failures
```

若出现失败：

- touched-code相关失败：停止并修复；
- 看似历史失败：在clean `origin/master`上重现并记录；
- 即使确认是既有失败，也不得自动推送master，必须停下等待用户复审。

本次明确不接受“full pytest未运行但继续推master”。

---

# 12. Integrated-master 冻结 PDE Gate

## 12.1 运行身份

完成选择性提交、full pytest通过后，在**拟推送的本地master HEAD**上运行一次冻结M10
MPI8 anchor：

```text
p6/h10
13.5 nm
S polarization
10° grazing
M120 / 240 amplitudes
40 external DtN modes per endcap
bottom/top fixed whole-endcap ILU(0) + Woodbury
right FGMRES restart90
five-residual threshold 5e-9
zero initial guess
MPI8
```

必须从clean source运行，不得引用Task37b工作树中的未提交代码。

## 12.2 数值与物理 Gate

至少满足：

```text
KSP reason                         > 0
iterations                         <= 1000
reported/global/bottom/top/modal   <= 5e-9
exact traction bottom/top          <= 1e-8
external q recovery                pass
full-FE recovery                   pass
canonical                          pass
selected interface/middle E/H      pass
R/T/A and A_volume                 pass
energy closure                     pass
80/80 orders                       pass
12/12 powers                       pass
12/12 complex amplitudes           pass
iterative vs frozen Full3D         pass
direct Hybrid vs frozen Full3D     pass
```

迭代数不要求逐位等于792，但若超过900，必须记录并停止推送等待审阅，因为这可能表示集成后
出现性能回归。

R/T/A和场必须与Task37b final authority在原冻结阈值内一致；不得只凭summary status判断。

## 12.3 资源 Gate

集成后的正式anchor必须满足：

```text
process-tree RSS <= 6144 MiB
swap             = 0
worker/process group exits cleanly
no orphan
no timeout
```

若数值/物理通过但RSS超过6144 MiB，记录resource regression并停止推送master；不得改成PSS/USS
作为替代authority。

## 12.4 Offline checker

在candidate进程退出后运行独立checker：

```text
exit 0
pass = true
failures = []
evidence integrity = true
authority bindings = true
online RSS excluded = true
```

---

# 13. Master 推送 Gate

只有以下全部成立，才允许：

```bash
git push origin master
```

条件：

- local integration基于最新 `origin/master`；
- 在开始推送前再次 `git fetch origin`；
- `origin/master`在集成期间若前进，必须rebase/重做并重跑受影响Gate；
- 没有whole-branch merge；
- 没有bulk cherry-pick历史提交；
- diff只包含V7白名单；
- ordinary defaults unchanged；
- research-only历史lane未进入master；
- focused serial/MPI通过；
- full repository pytest零失败；
- integrated-master M10 anchor通过数值、物理和6 GiB资源Gate；
- offline checker通过；
- local master工作树clean；
- local master相对origin/master只领先预期的选择性提交、落后0；
- 使用普通fast-forward push，不使用force。

推送后必须再次执行：

```text
local master SHA == origin/master SHA
master worktree  == clean
```

任一Gate失败时停止，不创建Task37c分支。

---

# 14. Task37c 本地与远程分支交接

## 14.1 分支名称

Master成功推送并确认后，Codex从更新后的远程master创建：

```text
codex/20260810-task37c-hybrid-iterative-robustness
```

## 14.2 创建和推送要求

建议命令语义：

```bash
git fetch origin
git switch --create codex/20260810-task37c-hybrid-iterative-robustness origin/master
git push -u origin codex/20260810-task37c-hybrid-iterative-robustness
```

最终必须满足：

```text
local Task37c SHA  == origin/master SHA
remote Task37c SHA == origin/master SHA
upstream           == origin/codex/20260810-task37c-hybrid-iterative-robustness
ahead/behind       == 0/0
worktree           == clean
```

此时禁止：

```text
创建 Task37c task.md
创建 Task37c docs目录
修改任何代码
产生Task37c新提交
运行PDE
开始角度/偏振/M扫描
```

远程Task37c分支只作为下一轮任务书的可写起点。

若同名本地或远程分支已经存在：

- 禁止删除；
- 禁止强制移动；
- 禁止force push；
- 停止并报告local/remote SHA、相对origin/master ahead/behind和是否可安全复用。

---

# 15. Codex 最终回报格式

完成后只报告：

```text
Task37b reviewed branch HEAD
Review V7 commit SHA
origin/master starting SHA
selective master commit list and one-line purpose
whole-branch merge = false
excluded research families/files summary
focused serial summary
focused MPI2/MPI4 summary
full pytest summary
integrated-master M10 anchor numerical/physics/resource summary
integrated-master offline checker summary
pushed master SHA
origin/master SHA after push
Task37c local branch name/SHA
Task37c remote branch name/SHA
Task37c upstream
ahead/behind
worktree status
Task37c task/code/PDE created = false
```

若流程在任一Gate停止，必须明确报告停止点和未执行项，不能把部分完成写成成功合入。

---

# 16. 最终主审决定

```text
Task37b scientific development          = closed
Task37b frozen numerical/physics result = accepted
Task37b MPI8 <= 6 GiB result            = accepted
whole branch merge                      = forbidden
selective master integration            = authorized after all Gates
origin/master push                      = authorized after all Gates
ordinary default                        = unchanged
research-only historical lanes          = remain on Task37b branch
Task37c branch creation                 = authorized after master push
Task37c remote push                     = authorized after master push
Task37c task.md / implementation        = not authorized in this handoff
```
