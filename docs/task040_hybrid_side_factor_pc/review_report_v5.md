# Task040 Review Report V5：接受 V4 身份停止，恢复 canonical packet authority

## 0. 审阅身份与正式裁决

```text
review                                      = Task040 Review Report V5
reviewed_branch                             = codex/20260822-task40-hybrid-side-factor-pc
reviewed_branch_head                        = 12b57a917295197e25f37addc61836f59c0fd054
reviewed_response                           = response_v5.md
reviewed_compact_record                     = task040_v4_1_exact_authority_compatibility_v1.json
reviewed_compact_sha256                     = 5ededd4bb9acfb9e4e3a403a410cecb37fb1490e7bf6056ca4644c7bfda7c36a
reviewed_formal_source_sha                  = 9f3d6e39cb607125a773b35d9a2a9f7459c7f2dc
reviewed_checker_source_sha                 = 4b70adfb6707464aaed4309ece5bca179dd60b57
reviewed_checker_artifact_sha256            = 71ab1274b3b236679ff19b403875b0109f6f3e3c1bb1f02e2642ee69d44f97d8
review_status                               = PASS_WITH_CONTROLLED_IDENTITY_NEGATIVE
V4_1_evidence                               = ACCEPTED
V4_1_gate                                   = FAIL_IDENTITY_AS_DESIGNED
V4_1_classification                         = EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F
V4_1_unique_failure                         = canonical_source_binding
bare_F_numerical_compatibility              = NOT_EVALUATED
trace_dual_projection_lift                  = NOT_RUN_BY_GATE
V4_2_through_V4_10                          = NOT_RUN_BY_GATE
ordinary_production_default_change          = false
merge_approval                              = NO
same_branch_continuation                    = required
new_execution_branch                        = forbidden
master_or_Task039_write                     = forbidden
next_primary_action                         = LEGACY_SOURCE_CANONICAL_PACKET_BRIDGE
response_required                           = response_v6.md
```

V4-1 的证据成立。它证明的是：冻结 exact spool 的文件、哈希、生产者和五个
exact-output identity 都能核对，但保存格式没有把旧 PETSc row 绑定到稳定的 H(curl)
物理自由度。因此旧数组不能直接按 global row 搬进当前布局。

这不是 bare-`F` residual 失败，也不是 exact vector、trace、dual、lift 或 side-PC 的数值
失败。正式流程在 system、`F`、interface mass、PETSc Vec、factor、QEP 和 PDE 之前停止，
所以这些量没有数值结论。

---

## 1. V4-1 正式证据裁决

### 1.1 身份 Gate

11 项 identity check 中，以下 10 项通过：

```text
input_sha256
physical_model_sha256
frozen_branch
freeze_source
selected_manifest
resolved_config
packet_manifest
spool_catalog
spool_producer_source
exact_output_metadata
```

唯一失败项：

```text
canonical_source_binding = false
failure_code             = CANONICAL_SOURCE_ROW_BINDING_UNAVAILABLE
```

缺失项恰为五个冻结 label 的 RHS 与 exact output，共 10 项：

```text
modal_traction_positive:rhs
modal_traction_positive:exact_output
modal_traction_negative:rhs
modal_traction_negative:exact_output
external_dtn_coupling:rhs
external_dtn_coupling:exact_output
fixed_random_repeat_0:rhs
fixed_random_repeat_0:exact_output
fixed_random_repeat_1:rhs
fixed_random_repeat_1:exact_output
```

### 1.2 数值与生命周期边界

```text
reports_count                         = 0
bare_F_residual                       = not_run_by_identity_gate
A_side_explanatory_residual           = not_run_by_identity_gate
system_created                        = false
explicit_bare_F_created               = false
interface_masses_built                = false
rhs_vectors_loaded                    = 0
exact_output_vectors_loaded           = 0
factor_objects_created                = 0
full_side_exact_factor_count          = 0
global_direct_factor_count            = 0
cross_section_group_factor_count      = 0
reduced_dense_factor_count            = 0
qep_calls                             = 0
pde_solve                             = not_run
```

因此不得引用旧 `a64d33e6` raw-row remap 的 residual，也不得把任何未运行项写成失败。
`1c68da98` 仍是 incomplete/superseded implementation attempt。

### 1.3 checker 与资源

独立 checker 只读取正式 6 个 raw 文件、96 个 spool JSON、resolved config、official input
与 tracked probe manifest，共 105 个文件；它不读取 numeric NPY，不调用 PETSc/solver，也
不相信 run summary 预填 classification。结果为：

```text
checker rc             = 0
checker checks         = 37/37 true
evidence_valid         = true
checker_pass           = true
gate_pass              = false
```

watchdog 记录的是 metadata preflight 进程，而不是 solver Pareto 点：

```text
MPI / threads          = 8 / 1
exit                   = rc0 natural_exit
samples                = 20/20 authoritative
last process sample    = 9.697888669999884 s
process-tree peak      = 1764352000 B = 1.643180847167969 GiB
swap                   = 0
SIGKILL                 = false
```

runner 内部 resource authority 因 identity gate 未进入采样，仍是 sample count 0。

---

## 2. 代码审阅结论

Review V4 新增的是 opt-in 诊断路径，不是 ordinary production default：

| 依赖组 | 文件 | 审阅结论 |
|---|---|---|
| diagnostic helper | `src/solvers/hybrid_exact_authority_compat.py` | fail-closed；缺 descriptor 时构造受控 identity stop；formal 路径不做 raw-row remap |
| runner | `benchmarks/task040_level_a.py` | 新 route 与旧 route 互斥；V4 preflight 在 system builder 前 return |
| watchdog | `benchmarks/task040_level_a_watchdog.py` | 只透传显式 V4 flag；不改变默认 route |
| focused tests | `src/test/test_313_task040_v4_exact_authority.py` | final serial/MPI2/MPI4 通过 |
| independent checker | `benchmarks/check_task040_v4_exact_authority.py` | raw 重算、文件白名单、tamper fail-closed |
| checker tests | `src/test/test_314_task040_v4_exact_authority_checker.py` | final 22 passed |

当前代码保留 `audit_exact_authority_petsc` 作为未来 bare-`F` 诊断 helper，但正式 V4 route
没有进入它。`inspect_canonical_source_authority` 即使看到 descriptor 也不会自行把
`bridge_qualified` 改成 true；V5 必须实现并证明 bridge 内容、哈希、覆盖和 round-trip，
不得只翻转一个布尔字段。

审阅期间发现的 response selective-merge 描述不完整，已由独立提交
`12b57a917295197e25f37addc61836f59c0fd054` 修正。当前没有未解决的 P0/P1 代码问题。

已知仓库合同缺口仍存在：

```text
src/test/test_26_documentation_contract.py
20 passed, 1 failed when combined with test_24
failure = Case104 numbered-case registration gap
```

它不是 V4 数值证据失败，但在任何最终 merge approval 前必须关闭。

---

## 3. 为什么下一步必须是 canonical packet bridge

冻结 NPY 保存了 local values、ownership range、array hash 和 vector identity；旧 MPI8
ownership 开头是 `[0,15582]`、`[15582,32868]`，当前布局开头则是 `[0,17118]`、
`[17118,33948]`。同一个 global size 不等于同一个数学 row。

更重要的是，H(curl) 自由度不是普通标量数组。边、面方向改变时，局部系数可能发生符号或
小块线性变换；Floquet slave/master 还带复相位。因此合格 bridge 不一定是一张一对一行号
置换表。它必须保存或重算：

```text
physical entity geometry key
entity dimension
entity-local basis index
orientation state / block transform
Floquet master identity and coefficient
vector role and source identity
```

旧 exact producer source
`7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f` 已包含：

```text
benchmarks/task039_v3_7_orchestration.py::_load_v5_blr_reference_spool
src/solvers/hcurl_canonical_vector_dolfinx.py::iter_canonical_active_trace_packets
src/solvers/hcurl_canonical_vector_dolfinx.py::reconstruct_canonical_active_trace_vec
```

所以 V5 允许在旧布局中先按原 ownership 合法加载冻结向量，再把它们转换成 canonical
packets，最后在当前布局重构。仍然禁止建立 full-side exact factor，也禁止把 raw global row
直接搬运。

---

# 4. V5 连续执行顺序

```text
V5-0  Case104 repository contract closure
V5-1  canonical bridge implementation + tiny/MPI qualification
V5-2  legacy-source replay and ten-vector canonical packet export
V5-3  current-layout reconstruction + bare-F compatibility Gate
V5-4  checker/evidence/response_v6 closeout
```

本 Review 覆盖到重新裁决 bare-`F` compatibility 为止。即使 V5-3 通过，也先停止等待下一次
审阅；不得自动进入原 V4-2 至 V4-10。

---

## 5. V5-0：关闭 Case104 repository contract gap

在任何新 formal run 前，先把 Case104 变成 case-contained active research contract：

```text
benchmarks/cases/104_5nm_hybrid_side_factor_pc/README.md
benchmarks/cases/104_5nm_hybrid_side_factor_pc/config.json
benchmarks/cases/104_5nm_hybrid_side_factor_pc/schema.json
benchmarks/cases/104_5nm_hybrid_side_factor_pc/expected.json
benchmarks/cases/104_5nm_hybrid_side_factor_pc/test_command.txt
```

允许最小修改 `src/test/test_26_documentation_contract.py`，为 Case104 建立独立、通用的
active-research contract；不得把 Case104 塞入硬编码 Task039 phase 语义，也不得改弱其他 case
的既有检查。至少绑定：

```text
status                    = active_research_controlled_identity_negative
canonical                 = false
production_qualified      = false
ordinary_default_changed  = false
pde_run_in_v4             = false
formal V4 compact record and SHA
V4-2 through V4-10        = not_run_by_v4_1_identity_gate
```

Gate：

```text
test_26_documentation_contract.py + test_24_repository_work_principles.py = all pass
JSON schema/config/expected parse and cross-reference = pass
test_command contains no heavy PDE command = true
```

第一提交建议：

```text
docs(task040): register Case104 active research contract
```

提交并推送后停止，等待监督审查。

---

## 6. V5-1：bridge 实现与 tiny/MPI 资格

数值核心必须进入 `src/`；benchmark 只能做参数化 orchestration。建议依赖组：

```text
src/solvers/hybrid_exact_authority_bridge.py
benchmarks/task040_v5_legacy_canonical_bridge.py
benchmarks/task040_v5_legacy_canonical_bridge_watchdog.py
src/test/test_315_task040_v5_legacy_canonical_bridge.py
```

具体文件名可做最小调整，但不得把 canonical transform、packet schema、round-trip 或重构核心
只堆在 task-numbered runner 中。

### 6.1 packet 合同

每个 packet 至少绑定：

```text
legacy base source SHA
current harness source SHA
input / physical / selected / resolved / spool hashes
label and role = five labels x {rhs, exact_output}
canonical key and canonical complex value
orientation/Floquet transform authority
source ownership and active-row count
packet key-set SHA256
packet value SHA256
shard payload SHA256 and manifest SHA256
```

大 packet 进入 ignored artifact；Git 只提交 compact manifest/record。

### 6.2 tiny 与 MPI Gate

必须覆盖：

```text
edge reversal and face permutation
complex Floquet phase
one-to-many constraint expansion if present
old-layout -> canonical -> same-layout round-trip <=1e-12
old-layout -> canonical -> different ownership -> canonical <=1e-12
missing/duplicate/extra key rejection
wrong source/module/manifest/hash rejection
nonfinite value rejection
raw-row remap rejection
MPI2 and MPI4 collective failure consistency
```

第二提交建议：

```text
feat(task040): add legacy canonical packet bridge
```

提交、推送、focused test、Ruff、compileall 后停止。未经监督批准不得创建 legacy worktree，
不得运行正式 MPI8。

---

## 7. V5-2：legacy-source replay 与十向量 packet export

### 7.1 临时 legacy source view

在 V5-1 审查通过后，允许创建唯一一个 detached、只读的临时 source view：

```text
legacy HEAD = 7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f
location    = /tmp/task040_v5_legacy_7e5d9b57
branch      = detached; no branch creation
commit/push = forbidden
task docs   = forbidden in temporary view
```

它只是历史源码输入，不是任务执行分支权威。正式实现、compact evidence 和文档仍只提交到
`codex/20260822-task40-hybrid-side-factor-pc`。不得在 legacy view 打补丁后把 dirty tree
冒充 `7e5d...`；若 harness 需要当前代码，必须作为当前分支已提交文件从外部调用，并记录
composite identity。

正式启动前记录：

```text
legacy git status / exact HEAD
current execution HEAD
harness SHA256
all imported legacy module absolute paths and SHA256
sys.path order
qualified activation and ABI
PETSc complex128 / IntType
MPI8 / threads1
```

任一 imported module 来自非声明树、legacy tree dirty、HEAD 不符或 ABI 不符，停止：

```text
LEGACY_SOURCE_REPLAY_NOT_QUALIFIED
```

### 7.2 先做 layout canary

先只构造 legacy bottom layout/condensation/Floquet identity，不读 frozen NPY。禁止 QEP、PDE、
factor。用确定性 complex canary 验证：

```text
legacy active rows = 132300
legacy ownership ranges = frozen eight ranges exactly
canonical key uniqueness and coverage = pass
legacy -> packet -> legacy round-trip <=1e-12
packet -> current-layout -> packet round-trip <=1e-12
Floquet/orientation audit = pass
```

若 old ownership 不能逐项复现，停止：

```text
LEGACY_SOURCE_REPLAY_LAYOUT_MISMATCH
```

### 7.3 导出十个冻结向量

只处理 Review V4 的五个 label × RHS/exact output。`physical_side_rhs` 不属于本轮 authority。
legacy loader 必须按原 ownership 校验 80 个 rank-vector shard 的 metadata self-hash、array
SHA、dtype、global/local size 与 producer identity，然后 owner-local packetize。

禁止：

```text
full-side exact factor
cross-section factor
QEP/PDE
FE-sized numeric allgather
per-rank full-vector replica
raw global-row remap
修改 frozen NPY/JSON
```

资源 Gate：

```text
one heavy process at a time
MPI8 / threads1
process-tree peak <45 GiB
swap =0
natural exit or qualified watchdog termination
```

若 packet 的 key 集、覆盖、round-trip 或 source identity 不成立，停止：

```text
LEGACY_CANONICAL_PACKET_BRIDGE_NOT_ESTABLISHED
```

---

## 8. V5-3：当前布局重构与 bare-F compatibility Gate

只有 V5-2 全部通过后，才在当前执行 SHA 的 fresh MPI8 进程中：

1. 构造当前 bottom system 与 explicit bare `F`；
2. 从 canonical packets 重构五个 RHS 与五个 exact-output Vec；
3. 再导出 canonical packets，逐项比较 key/value round-trip；
4. 计算五个 full explicit bare-`F` true residual；
5. 可报告 `A_side=(F-C H^{-1}D)` residual，但它只作解释，不能替代 bare `F`。

必须报告：

```text
source/current canonical key-set equality
ten-vector canonical round-trip relative error
five RHS and five exact-output vector identities
bare-F matrix hash before/after
five bare-F true residuals
five A-side explanatory residuals if run
factor inventory and lifecycle
resource timeline/hash
```

Gate：

```text
source/current key sets                  = exact match
all ten canonical round-trips            <=1e-12
all five bare-F true residuals            <=1e-9
finite/repeat                             = pass
bare-F hash unchanged                     = true
full-side/cross-section/global factors    = 0/0/0
QEP/PDE                                   = 0/not_run
peak                                      <45 GiB
swap                                      =0
```

分类：

```text
EXACT_AUTHORITY_COMPATIBLE_WITH_CURRENT_BARE_F
    bridge、round-trip与五个bare-F residual全部通过

EXACT_AUTHORITY_CANONICALLY_RECONSTRUCTED_BUT_BARE_F_RESIDUAL_FAIL
    canonical bridge成立，但任一bare-F residual >1e-9

LEGACY_CANONICAL_PACKET_BRIDGE_NOT_ESTABLISHED
    key/coverage/orientation/Floquet/round-trip任一失败

LEGACY_SOURCE_REPLAY_NOT_QUALIFIED
    source、ABI、module或layout identity不成立
```

这些都是正式停止 Gate。不得通过改阈值、重建 exact factor、切换 operator、改变 mesh/M480
或重做 QEP 来追逐通过。

---

## 9. independent checker

正式 run 后新增独立 checker 与 synthetic tamper tests。checker 不得 import runner/solver，
不得调用 PETSc/PDE；允许流式读取 canonical packet artifacts并独立重算：

```text
manifest/shard/content hashes
source/current identity
legacy module hashes and import paths
80 frozen shard hashes
canonical key uniqueness/coverage
source/current key-set equality
round-trip summaries from raw packet values
five residual fields and thresholds
factor/QEP/PDE inventory
watchdog timeline, peak, swap and termination
not_run_by_gate map
```

合法 positive 或 controlled-negative evidence 都可 `checker_pass=true`；数值 Gate 单独记录。
证据损坏、缺 shard、预填 status 篡改、raw-row remap 或 source identity 不符必须是
`implementation_failure` 与非零 CLI。

checker 提交并推送后，先由监督审查，再运行 immutable checker 写入 formal root。

---

## 10. 测试与提交节奏

每一阶段只做对应 focused test；禁止因为 Markdown/JSON 修改重跑 heavy。

最低测试：

```text
test_26 + test_24 all pass after V5-0
test313 and test314 regression
new bridge tests serial/MPI2/MPI4
new checker tamper tests
Ruff
compileall
git diff --check
```

full repository pytest 只在最终 closeout 且时间/环境允许时运行；若未运行必须如实写
`not_run`，不得声称 CI。

每次提交都必须先停下等待监督批准。不得 amend、force-push、rebase 或 merge master。

---

## 11. V5-4 证据与 response_v6

至少创建或更新：

```text
outcomes/legacy_canonical_packet_bridge.md
outcomes/exact_trace_representability.md
outcomes/group_lift_identity.md
outcomes/memory_residual_time_pareto.md
outcomes/test_summary.md
outcomes/summary.md
response_v6.md
```

提交一个 compact record，绑定 source、legacy replay、packet、round-trip、residual、resource、
lifecycle、checker 与 `not_run_by_gate`。大 canonical packet、NPY、timeline 和 system artifact
继续保留在 ignored `results/`。

无论 V5-3 正负，本轮都不得运行 V4-2 至 V4-10；`response_v6.md` 完成后停止等待审阅。

---

## 12. 本轮最终判断

```text
V4 controlled identity negative       = ACCEPTED
V4 formal numerical conclusion        = NONE
raw global-row remap                   = REJECTED
canonical packet recovery feasibility = AUTHORIZED_WITH_GATES
full-side exact factor rebuild         = FORBIDDEN
V4-2 through V4-10                     = NOT AUTHORIZED IN V5
production side inverse                = NOT QUALIFIED
0.7 nm conclusion                      = NOT AVAILABLE
merge approval                         = NO
```

通俗地说：旧文件里的数值还在，但“每个系数代表哪条边、哪个面、哪个局部基函数，以及经过了
什么方向和 Floquet 相位变换”没有一起保存。V5 只允许把这层身份重新建立并核验 bare-`F`
residual；在这一步通过以前，不继续讨论 trace、lift、coarse、完整 Hybrid 或 0.7 nm。
