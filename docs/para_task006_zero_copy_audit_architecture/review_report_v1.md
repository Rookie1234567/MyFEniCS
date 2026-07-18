# REVIEW REPORT V1：PARA-Task006 No-Private-CSR Audit Architecture 阶段验收与 Proxy 可用性失败结论

## 0. 最终状态

```text
review = PARA-Task006 review_report_v1
branch = ChatGPT/20260715-para-task-neural-local-pc
review_status = PASS_WITH_MAJOR_QUALIFICATIONS
primary_classification = audit_architecture_false_reject_failure
secondary_classification = borrowed_exact_action_feasible_zero_private_CSR

P0_provenance_and_baseline = PASS
P1_borrowed_exact_action = PASS
P1_private_persistent_local_CSR = 0_BYTES_PASS
P1_action_equivalence = MACHINE_PRECISION_PASS
P1_storage_blocker_removed = YES_IN_PRINCIPLE
P1_every_call_all_slab_runtime = NOT_FEASIBLE_AS_CURRENT_SERIAL_COLLECTIVE

P2_proxy_Q0_calibration = FAIL_USABILITY_GATE
P2_zero_false_accept = CALIBRATION_SET_CONSTRUCTION_ONLY
P2_independent_false_accept_qualification = NOT_RUN
P2_nonharmful_acceptance_best = 43.3747_PERCENT
P2_two_seed_nonharmful_acceptance_best = 42.9607_PERCENT
P2_worst_slab_false_reject = 81.8898_PERCENT
P2_proxy_storage = FEASIBLE
P2_proxy_discrimination = INSUFFICIENT

frozen_R4_model = Task005_A_D0_R64
frozen_R4_model_Q0_harmful_samples = 58_OF_1024
frozen_R4_model_safety = INSUFFICIENT_FOR_NO_FALLBACK_RUNTIME

P3_locked_replay = NOT_RUN_BY_GATE
P4_failure_injection = NOT_RUN_BY_GATE
P5_periodic_schedule = NOT_RUN_BY_GATE
P6_lifecycle_and_live_storage = NOT_RUN_BY_GATE
P7_R4_live_shadow = NOT_RUN_BY_GATE
Task005_P3_resume = PROHIBITED

learned_PC_global_numeric_result = NOT_AVAILABLE
learned_PC_acceleration = NOT_PROVEN
memory_neutral_live_shadow = NOT_PROVEN
periodic_audit_safety = NOT_PROVEN
ordinary_default_changed = false
production_claim_allowed = false
h3_allowed = false
h2_allowed = false
branch_management = prohibited
master_operations = prohibited
```

PARA-Task006 的实施、证据保留和按 Gate 停机可以验收。任务成功关闭了 PARA-Task005 最明确的存储技术债：严格 local residual audit 不再需要每个 owner 持久复制完整 complex128 local CSR。`BorrowedLocalExactAuditor` 通过已有 shifted-F/global operator action 与 owner-union scatter，能够以机器精度重建全部 16 个 local submatrix actions，并将 private persistent local CSR storage 降为 0。

但 Task006 没有建立可用于 learned runtime 的 strict proxy。所有 12 个 Q0 proxy families 都只能以极高 false-reject 代价获得 calibration-set observed false accept = 0。最佳 family 仅接受约 43.37% 的 non-harmful outputs；符合最终 two-seed 结构的最佳 family 仅接受约 42.96%，最差 slab false-reject 约 81.89%。因此没有 certificate 被锁定，Q1–Q5、故障注入、periodic schedule 和 live shadow 均正确地没有运行。

当前失败必须准确解释为两个相互关联但不同的事实：

```text
A. current reduced/sketch proxy scores cannot separate harmful and non-harmful outputs
   with the frozen zero-observed-false-accept rule;

B. reused Task005 A_D0_R64 candidate itself is not sufficiently safe on Q0:
   58 / 1024 unmodified outputs are harmful by exact ground truth.
```

因此，本结果不是“无私有 CSR audit 不可行”，也不是“learned local inverse 全局失败”。它证明的是：

```text
borrowed exact audit is feasible;
current rank-64 candidate + current reduced/CountSketch proxy is not usable;
Task005 P3 cannot resume yet.
```

---

# 1. 审阅范围

本轮审阅覆盖：

```text
docs/para_task006_zero_copy_audit_architecture/task.md
docs/para_task006_zero_copy_audit_architecture/outcomes/*
benchmarks/cases/095_zero_copy_learned_pc_audit/*
benchmarks/neural_pc/build_task006_ilu_reference.py
benchmarks/neural_pc/qualify_task006_borrowed_action.py
benchmarks/neural_pc/calibrate_task006_proxy.py
benchmarks/run_workstation_iterative.py
benchmarks/run_task031_memory_forensics.py
src/solvers/borrowed_local_audit.py
src/solvers/low_storage_audit_proxy.py
src/solvers/physical_slab_two_level.py
src/test/test_46_para_task006_contract.py
src/test/test_47_borrowed_local_audit.py
src/test/test_48_low_storage_audit_proxy.py
```

同时审阅了 Task005 的修正回应与 outcomes 更新，包括：

```text
docs/para_task005_comprehensive_all_slab_learned_pc/response_v1.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/validation.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/changed_files.md
```

冻结求解框架保持：

```text
wavelength = 13.5 nm
material = validated complex Si
geometry = 50 x 25 x 140 nm periodic cell
Si block = 17 x 25 x 120 nm
incidence = theta 80 deg, phi 0 deg, S polarization
finite element = p2 Nedelec hexahedral
mesh = h5
periodicity = double Floquet
ports = 80 Fourier-DtN auxiliary unknowns
operator = exact condensed F-C H^-1D
outer = right FGMRES90, rtol 1e-6
physical slabs = 16, overlap 0.25
coarse = fixed 75D true-action Galerkin
smoother = current two-step + post-smooth
formal MPI = 4 ranks, one thread per rank
```

本审阅不执行分支管理、merge、PR、master 或 ordinary-default 操作。

---

# 2. P0 Provenance 与 baseline：接受

P0 在 clean SHA：

```text
9822bc5d84375bf1cd3039aec7ca1e849413c0ed
```

得到：

```text
iterations = 852
solve = 93.347 s
reported / condensed / full residual ≈ 9.98025e-7
R/T/A closure = -1.860e-9
external simultaneous worker peak = 1.608 GiB
swap in/out = 0 / 0
```

完整测试为：

```text
209 passed, 12 skipped
```

Task005 split 身份也已按前次审阅修正：

```text
H = consumed screening split
V = not used for Task005 candidate selection
```

R4 checkpoint 固定为 Task005 `A_D0_R64`，4 个 checkpoint 的 weights SHA、operator fingerprint 和 dataset identity 均核对通过，没有重新训练。

P0 证据可接受。

---

# 3. P1 Borrowed exact local action：强正结果，接受

## 3.1 数学与代码身份

对 slab index set `I_s`，目标 action 为：

```math
A_s z_s = R_s A_{shift} R_s^T z_s.
```

实现执行：

```text
owner local correction
-> owner-union reverse scatter into persistent distributed global vector
-> borrowed shifted-F/global MatMult
-> owner-union forward scatter
-> slab restriction
```

`BorrowedLocalExactAuditor` 不拥有：

```text
action_operator
union_scatter
local CSR
local sparse matrix
ILU factor
```

只持有：

```text
2 distributed PETSc work vectors
2 sequential owner-union work vectors
small slab union-position metadata
```

普通 ILU 路径不会创建 auditor，因此 ordinary profile 不承担该存储。

## 3.2 数值等价

正式 h5/MPI4、16 slabs、每 slab 4 probes：

```text
action relative error max = 6.030e-16
local rho absolute difference max = 3.558e-16
rows = 64 / 64
private persistent local CSR = 0 bytes
```

测试 probes 覆盖：

```text
deterministic complex vector
1e-8 scale + phase
three-point sparse boundary/interior vector
alternating high-frequency vector
```

所有 16 slabs 的 action/rho 对照均在机器精度范围内。

## 3.3 存储

每 rank：

```text
persistent work vectors = 0.753–0.762 MiB
layout metadata ≈ 0.068 MiB
private persistent local CSR = 0
```

P1 为等价性验证临时逐 slab 加载 reference CSR，最大 ephemeral reference 为 12.095 MiB，并立即释放。该 reference 不进入 runtime persistent ledger，符合任务合同。

## 3.4 Full-solve guard

clean implementation：

```text
0b20f2554a9cc0526efa893f941174fb81918472
```

在 qualification 后运行 ordinary ILU full solve：

```text
iterations = 852
solve = 95.026 s
three residuals ≈ 9.980248e-7
R/T/A closure = -1.860e-9
external peak = 1.613209 GiB
peak ratio vs P0 = 1.00309
swap = 0
```

说明基础设施没有改变普通求解数值结果。

## 3.5 重要限定：这不是字面意义的 zero-copy

该路径消除了 private CSR duplication，但仍发生：

```text
owner-union reverse scatter
one distributed MatMult
owner-union forward scatter
```

因此建议后续正式术语优先使用：

```text
no-private-CSR borrowed exact action
```

而不是容易被理解成“没有数据移动”的字面 `zero-copy`。

## 3.6 运行成本限定

单个 collective slab audit 的实测均值：

```text
6.207 ms
```

这已经接近 Task005 未来完整 four-slab owner path 的 11.514 ms 预算。若按当前接口逐 slab、逐 collective 审计：

```text
R4 four slabs every-call exact audit ≈ 4 × 6.207 ms ≈ 24.8 ms
all 16 slabs every-call exact audit ≈ 16 × 6.207 ms ≈ 99.3 ms
```

上述乘法是根据单次实测作出的近似推断，不是正式 live benchmark；但足以说明当前 serial slab-by-slab every-call exact audit 不能直接成为最终速度路径。Periodic audit、grouped audit 或其他摊销机制仍然必要。

P1 最终身份：

```text
borrowed exact local action = ACCEPTED
private CSR blocker = REMOVED IN PRINCIPLE
full runtime audit architecture = NOT YET QUALIFIED
```

---

# 4. P2 Proxy calibration：完整负结果，停机正确

## 4.1 冻结候选与 corpus

P2 只访问：

```text
Q0 = Task005 V validation split
```

未访问 Q1–Q5，符合数据隔离合同。

模型固定为：

```text
Task005 A_D0_R64
slabs = {0, 5, 9, 15}
no retraining
```

比较：

```text
q = 64 / 128 / 256 / 512 / 1024 / 2048
seed_count = 1 / 2
```

共 12 个 family。

## 4.2 Proxy 组成

每个 family 使用：

```text
reduced equation residual
+ one or two procedural CountSketch residuals
+ finite/norm/identity guards in certificate
```

certificate 只保存：

```text
small reduced operator
sketch A*V products
procedural seed/hash metadata
normalization ranges
thresholds
```

没有持久 local CSR。

## 4.3 Harmful ground truth

对 learned correction：

```text
harmful if rho_learned >= 1.0
or rho_learned > 1.05 * rho_ILU
```

Q0 上未修改模型已有：

```text
58 / 1024 harmful outputs
slab 0 = 2
slab 5 = 31
slab 9 = 23
slab 15 = 2
```

即 harmful fraction：

```text
5.664%
```

这一结果非常重要。它说明 Task005 在 H screening split 上通过最低 admissibility 的 rank-64 模型，并没有在新的 V/Q0 trajectory samples 上保持 per-sample non-degradation。问题明显集中在较大的内部 slabs 5 和 9。

因此，即使存在一个完美 proxy：

- 若 true no-fallback runtime 对任何 proxy reject 都 fail closed，当前模型会频繁中止；
- 若允许继续使用被判 harmful 的 output，则违反安全合同；
- 若加入 ILU fallback，则不再是最终 no-hidden-ILU replacement。

当前候选质量本身已不足以进入最终 no-fallback runtime。

## 4.4 “Q0 false accept = 0”的证据身份

校准代码将 acceptance thresholds 设置为：

```text
strictly below the minimum harmful score on Q0
```

因此 Q0 上 observed false accept = 0 是阈值构造目标，不是独立安全验证结果。

准确身份为：

```text
zero false accept on calibration corpus by construction
```

而不是：

```text
proxy safety qualified
```

独立的 safety evidence 本应来自 locked Q1–Q5 replay、failure injection 和 live shadow；这些阶段均未解锁。

## 4.5 False-reject / usability 失败

12 个 family 的结果：

```text
false accept on Q0 = 0 for all families
best non-harmful acceptance = 43.3747%
best final-compatible two-seed acceptance = 42.9607%
worst slab false-reject = 81.8898%
```

任务 Gate 要求：

```text
non-harmful / admissible acceptance >= 99%
overall false reject <= 5%
no slab false reject > 10%
```

实际结果远低于门槛。

即使 q 从 64 增加到 2048，或从 one seed 增至 two seeds，也没有产生可用分离。这说明当前问题不是简单地“sketch 太小”，而是：

```text
current reduced/sketch score distributions for harmful and non-harmful outputs overlap strongly
under the strict absolute + relative-to-ILU harmful definition.
```

## 4.6 Proxy 存储不是本轮 blocker

以 Task005 R4 models 27.824 MiB/owner，加 borrowed work vectors约 0.762 MiB：

```text
q64 two-seed   total ≈ 29.336 MiB
q256 two-seed  total ≈ 30.836 MiB
q512 two-seed  total ≈ 32.837 MiB
q1024 two-seed total ≈ 36.836 MiB
q2048 two-seed total ≈ 44.836 MiB
```

因此：

```text
q64–512 satisfy preferred 33.670 MiB storage line;
q1024–2048 remain below 50.505 MiB speed-first guard.
```

Task005 的 private CSR storage blocker确实已被 P1/P2 architecture 消除。P2 失败来自判别可用性，而不是 storage。

P2 最终身份：

```text
proxy storage feasibility = PASS IN PRINCIPLE
proxy zero-independent-false-accept = NOT TESTED
proxy usability = FAIL
proxy family selected = NONE
```

---

# 5. P3–P7 停机：正确

由于 P2 没有 usable locked two-seed proxy：

```text
P3 locked Q1/Q2 replay = not_run_by_gate
P4 failure injection = not_run_by_gate
P5 K=4/8/16/32 schedule = not_run_by_gate
P6 lifecycle/external memory = not_run_by_gate
P7 R4 live shadow = not_run_by_gate
```

这是正确的停机行为。继续执行以下任一项都会绕过冻结 Gate：

- 在 Q1–Q5 上继续调整阈值；
- 用更频繁 exact audit 掩盖 proxy 高 false-reject；
- 在 live solver 中接入未锁定 certificate；
- 把未运行 failure injection 写成通过；
- 因 private CSR 已消除就直接恢复 Task005 P3。

outcomes 对未运行阶段均使用 `not_run_by_gate`，没有把缺失证据写成 pass，处理正确。

---

# 6. Provenance 与验证：接受

接受的 provenance：

```text
P0 clean SHA = 9822bc5d84375bf1cd3039aec7ca1e849413c0ed
P1 clean SHA = 0b20f2554a9cc0526efa893f941174fb81918472
P2 clean SHA = ac039bd...
branch = ChatGPT/20260715-para-task-neural-local-pc
branch/pull/push/merge = none
heavy artifacts = ignored
```

最终验证：

```text
complete src/test = 218 passed, 12 skipped
MPI2 = 3 passed per rank
MPI4 = 3 passed per rank
Ruff = pass
compileall = pass
git diff --check = pass
artifact-ignore audit = pass
```

P2 worker 以“没有 usable family”的显式非零返回码结束，并完整写出 calibration record。这是预期 Gate failure，不是崩溃、OOM、死锁或卡住。

---

# 7. 必须保留的限定

## 7.1 本任务没有资格化 periodic audit

只有单个 borrowed exact audit 的成本实测：

```text
6.207 ms / collective slab audit
```

没有：

```text
K=4/8/16/32 runtime
slow-drift detection latency
anomaly audit overhead
owner rotation correctness
```

因此不得声称 periodic exact audit 已安全或满足预算。

## 7.2 本任务没有运行 failure injection

NaN/Inf、scale/phase、wrong routing、basis-orthogonal noise、precision loss、slow drift 等均未运行。不能从 Q0 calibration 推断这些故障会被检测。

## 7.3 本任务没有 live shadow

没有实测：

```text
learned output + proxy + periodic audit in PETSc/MPI solve
ILU writeback equivalence in shadow
live proxy false accept
live harmful distribution
live MPI wait
paired external peak
```

P1 full solve只是 infrastructure guard，不是 P7 live shadow。

## 7.4 本任务没有证明所有 low-storage proxy 都失败

当前负结果只覆盖：

```text
A_D0_R64 frozen candidate
R4 slabs
Q0 V trajectory samples
reduced residual + procedural CountSketch families
q <= 2048
one/two seeds
current harmful definition
```

它不否定：

- 更安全或更高质量的 learned candidate；
- rank-96/heterogeneous speed-first candidate；
- 训练时加入 per-sample non-degradation 约束；
- graph-certified grouped borrowed exact audits；
- different certified residual estimators；
- revised accept/abort contract；
- shared parent-operator action batching。

## 7.5 Task005 P3 仍不得恢复

当前缺少：

```text
16/16 model admissibility
usable locked proxy
injection evidence
periodic schedule
live shadow
true no-hidden-ILU learned replacement
```

因此：

```text
Task005_P3_resume = prohibited
```

---

# 8. 后续研究建议

下一步不应简单扩大 MLP 或直接训练 16 个模型。应先解决“candidate safety + exact audit cost”协同问题。

## 8.1 优先方向 A：更安全的 learned candidate

当前 rank-64 模型在 Q0 有 5.664% harmful outputs。下一任务应先在 fresh calibration/final corpus 上比较：

```text
rank-64 vs rank-96 heterogeneous candidates
linear low-rank vs safety-constrained linear map
training loss with per-sample equation residual tail penalty
p95/worst-sample non-degradation objective
explicit rho_learned / rho_ILU margin on calibration data
```

必须使用新的未消费 final corpus；不能继续用 Q0/Q1 调到有利结果。

目标应是先让未修改 candidate 本身满足：

```text
harmful fraction approximately zero on calibration and locked replay
no concentration on slabs 5/9
```

否则 proxy只能频繁拒绝或触发 fail-closed。

## 8.2 优先方向 B：Graph-certified grouped borrowed exact audit

当前 auditor 每个 slab调用一次 collective MatMult，成本约 6.207 ms。建议研究能否根据 global sparse coupling/DoF support 构造互不耦合的 slab groups：

```text
for slabs i,j in same audit group:
A[I_i, I_j] = 0 and A[I_j, I_i] = 0
```

若该条件可由真实 operator graph严格认证，则可以：

```text
pack multiple slab corrections into one global vector
-> one borrowed MatMult
-> restrict independent local actions
```

必须逐 group 与独立 slab CSR action做 `<=1e-12` 等价验证，不能仅凭几何距离或 two-color 名称假定无耦合。

若 R4 或 16 slabs 可以用少量 graph colors完成 grouped exact audit，可能无需高拒绝率 proxy，或只需非常轻量 anomaly guards。

## 8.3 方向 C：修改安全合同但保持诚实

可研究两类不同目标，不能混用：

### Fail-closed research profile

```text
proxy reject -> abort solve
```

要求 candidate 本身几乎不产生 harmful/reject；适合最终 no-fallback qualification。

### Diagnostic fallback profile

```text
proxy reject -> ILU fallback
```

可用于收集 hard examples，但不能声称 factor removal、memory saving或最终 learned replacement。

不得通过放宽 harmful 定义或隐藏 fallback 使当前 proxy看似通过。

## 8.4 数据身份

下一轮必须生成新的：

```text
calibration split
locked replay split
untouched final split
```

并记录 outer iteration、pre/post phase、restart window和 RHS norm。Task005 H、Task005 V/Q0 已被消费，不应继续作为最终泛化证据。

---

# 9. 最终验收结论

```text
PARA-Task006 disposition = ACCEPTED_WITH_MAJOR_QUALIFICATIONS
P0 provenance/baseline = ACCEPTED
P1 borrowed exact action = STRONG TECHNICAL SUCCESS
P1 private CSR elimination = ACCEPTED
P2 current strict proxy = REJECTED_FOR_FALSE_REJECT_USABILITY
P2 storage architecture = FEASIBLE IN PRINCIPLE
Q0 zero false accept = CALIBRATION-ONLY, NOT INDEPENDENT QUALIFICATION
frozen rank-64 candidate safety = INSUFFICIENT ON Q0
P3-P7 stop = CORRECT
periodic audit = NOT QUALIFIED
failure injection = NOT RUN
live shadow = NOT RUN
Task005 P3 resume = NOT ALLOWED
ordinary default = UNCHANGED
production claim = NOT ALLOWED
```

Task006 已经得到一个重要且可保留的工程成果：

```text
strict exact local residual can be computed without persistent private local CSR.
```

但它也揭示了比存储更深的一层问题：

```text
the current learned candidate is not per-sample safe enough,
and the current reduced/sketch proxy cannot distinguish harmful outputs
without rejecting most useful outputs.
```

因此，下一步应转向安全候选与 grouped borrowed exact audit 的协同设计，而不是直接恢复 16-model global integration。