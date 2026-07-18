# PARA-Task006：Zero-Copy / No-Private-CSR Audit Architecture Qualification for All-Slab Learned PC

## 0. 任务身份

```text
task = PARA-Task006
name = Zero-Copy / No-Private-CSR Audit Architecture Qualification for All-Slab Learned PC
status = planned / research-only continuation
execution_branch = ChatGPT/20260715-para-task-neural-local-pc
predecessor = PARA-Task005
predecessor_review = docs/para_task005_comprehensive_all_slab_learned_pc/review_report_v1.md
remote_repository = Rookie1234567/MyFEniCS
reference_wavelength = 13.5 nm
reference_geometry = current validated full-3D periodic Si block grating
reference_discretization = p2 Nedelec hexahedral FEM
reference_parallelism = MPI4 for live h5 shadow
ordinary_default_changed = false
production_claim_allowed = false
new_full16_model_training_allowed = false
reuse_frozen_task005_R4_models = allowed after checksum/fingerprint verification
online_training_allowed = false
h3_allowed = false
h2_allowed = false
branch_management = prohibited by explicit user instruction
master_operations = prohibited by explicit user instruction
```

### 0.1 分支操作禁令

本任务只允许在现有：

```text
ChatGPT/20260715-para-task-neural-local-pc
```

分支中新增或修改 Task006 相关代码、测试、benchmark 和文档。不得：

- 创建、切换、移动、重命名或删除分支；
- merge、rebase、cherry-pick、reset 或同步其他分支；
- pull、push、提交或合并到 `master`；
- 开 PR；
- 因当前分支与其他分支存在差异而主动改变分支历史；
- 修改 ordinary solver default；
- 自动恢复 Task005 P3；
- 自动运行 h3/h2；
- 将本任务解释为 production merge preparation。

若当前分支缺少其他路线的新基础设施，应在 outcomes 中记录限制，不得擅自同步。

---

# 1. 为什么启动本任务

PARA-Task005 已得到：

```text
16/16 raw-RHS LU-teacher datasets = PASS
R4 local low-rank quality = positive screening signal
R4 nonlinear advantage over linear = not proven
R4 owner-batch model-only runtime = positive
P3-P10 = not run
```

决定性早停为：

```text
R4 private exact-audit CSR = 40.458 MiB / owner
smallest admissible heterogeneous linear models = 27.824 MiB / owner
total = 68.282 MiB / owner

memory-neutral limit = 33.670 MiB / owner
speed-first guard = 50.505 MiB / owner
```

因此 Task005 的主要 blocker 不是模型容量或裸 inference，而是：

```text
为了每次计算 exact local residual，
每个 owner 额外保存完整 local complex128 CSR operators。
```

当前 frozen safety contract 要求：

```text
shadow every-call exact audit
active 只有在 strict proxy 通过后才允许 periodic exact audit
true no-hidden-ILU 无 fallback，audit 失败必须 fail closed
```

在没有替代审计架构前，不能静默删除 40.458 MiB private CSR 并声称 storage Gate 通过。

Task006 专门回答：

```text
能否不持久复制完整 local CSR，
而复用 solver 已有 operator action、极小型 deterministic sketches、reduced certificates
和周期性 exact audit，
在冻结问题上建立低存储、可注入故障、可测漏检、可 fail-closed 的 learned-PC 安全架构？
```

本任务不继续扩大 NN，也不训练 16 个新模型。通过后，只是允许后续任务从 Task005 P3 恢复。

---

# 2. 必须读取

执行前必须完整读取：

```text
docs/repository_work_principles.md
docs/task_retrospective_standard.md
docs/solver_guide.md
docs/iterative_solver_ports.md
docs/architecture_overview.md
notes/reference/code_walkthrough/32_physical_slab_two_level_pc.md

docs/para_task004_full_16_slab_exact_oracle/task.md
docs/para_task004_full_16_slab_exact_oracle/review_report_v1.md
docs/para_task004_full_16_slab_exact_oracle/outcomes/summary.md

docs/para_task005_comprehensive_all_slab_learned_pc/task.md
docs/para_task005_comprehensive_all_slab_learned_pc/review_report_v1.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/summary.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/memory_report.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/runtime_backend_report.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/owner_batch_report.md
docs/para_task005_comprehensive_all_slab_learned_pc/outcomes/data_and_teacher_report.md

src/solvers/local_slab_solver.py
src/solvers/physical_slab_two_level.py
src/solvers/lu_teacher_local_solver.py
src/solvers/batched_reduced_smoother.py
src/solvers/condensed_dtn.py
src/solvers/mpc_form_action.py
benchmarks/run_workstation_iterative.py
benchmarks/neural_pc/petsc_capture.py
benchmarks/neural_pc/screen_task005_linear.py
benchmarks/neural_pc/screen_task005_nonlinear.py
benchmarks/neural_pc/benchmark_task005_owner_batch.py
```

完成任务时必须维护：

```text
docs/para_task006_zero_copy_audit_architecture/outcomes/summary.md
docs/para_task006_zero_copy_audit_architecture/outcomes/changed_files.md
docs/para_task006_zero_copy_audit_architecture/outcomes/experiment_matrix.csv
docs/para_task006_zero_copy_audit_architecture/outcomes/borrowed_action_equivalence.md
docs/para_task006_zero_copy_audit_architecture/outcomes/proxy_qualification.csv
docs/para_task006_zero_copy_audit_architecture/outcomes/failure_injection_matrix.csv
docs/para_task006_zero_copy_audit_architecture/outcomes/periodic_audit_report.md
docs/para_task006_zero_copy_audit_architecture/outcomes/runtime_breakdown.csv
docs/para_task006_zero_copy_audit_architecture/outcomes/memory_report.md
docs/para_task006_zero_copy_audit_architecture/outcomes/live_shadow_report.md
docs/para_task006_zero_copy_audit_architecture/outcomes/provenance.md
docs/para_task006_zero_copy_audit_architecture/outcomes/decision.md
docs/development_progress.md
benchmarks/cases/095_zero_copy_learned_pc_audit/
```

重型 artifacts 必须放在：

```text
benchmarks/artifacts/cases/095/
```

并保持 Git ignored。不得提交：

- full local CSR operators；
- checkpoints；
- raw capture streams；
- injected vectors；
- full solver logs；
- profiler dumps；
- field/HDF5/XDMF/VTU；
- large timing timelines。

---

# 3. 冻结物理与求解框架

第一阶段固定：

```text
wavelength = 13.5 nm
material = current validated complex Si
geometry = current 50 x 25 x 140 nm periodic cell
Si block = 17 x 25 x 120 nm
incidence = theta 80 deg, phi 0 deg
primary polarization = S
finite element = p2 Nedelec hexahedral
mesh = h5
periodicity = double Floquet
ports = 80 Fourier-DtN auxiliary unknowns
operator = exact condensed F-C H^-1D
outer = right FGMRES90, rtol 1e-6
physical slabs = 16, overlap 0.25
coarse = fixed 75D true-action Galerkin
smoother = current two-step + post-smooth
formal live shadow = MPI4, one thread per rank
```

不得改变：

- 波长、材料、几何、主角度；
- slab 数、overlap、weights、owner assignment policy；
- two-step smoother；
- post-smooth；
- 75D coarse；
- right FGMRES90；
- official R/T/A；
- ordinary default。

Task004 的 one-step 仍是负证据，不得在本任务重新包装。

---

# 4. 本任务的研究问题

本任务必须回答：

1. local submatrix action 能否通过复用已有 shifted-F/global action 精确重建，而不保存 private CSR？
2. borrowed action 与 Task005 captured CSR action 在 16 个 slabs 上是否 `<=1e-12` 等价？
3. borrowed exact audit 的单次与摊销成本是多少？
4. 能否构造只保存极小 reduced/sketch metadata 的 conservative proxy？
5. proxy 是否能在冻结 qualification corpus 上达到 zero false accept？
6. proxy 是否会因过度保守而大量 false reject？
7. wrong slab routing、scale/phase drift、orthogonal noise、precision loss、NaN/Inf 等故障是否全部能被检测？
8. periodic exact audit 能否在冻结 latency 内发现缓慢 drift？
9. anomaly-triggered exact audit 能否 fail closed？
10. private persistent local CSR bytes 是否真的为 0？
11. model + proxy + buffers 是否回到 33.670 MiB/owner，或至少低于 50.505 MiB speed-first guard？
12. model + proxy + amortized exact audit 是否仍保留 11.514 ms/owner one-level apply 的工程预算？
13. R4 live shadow 是否在 ILU 写回情况下保持原 full residual/RTA，并给出真实 PETSc/MPI overhead？
14. Task005 是否可以在独立后续任务中从 P3 恢复？

---

# 5. 安全术语边界

## 5.1 “strict proxy”的含义

本任务中的 strict proxy 指：

```text
在冻结 operator、冻结模型 family、冻结 qualification corpus、冻结阈值和故障集合上，
使用 conservative acceptance rule，
达到 zero observed false accept，
并由 periodic exact audit 和 fail-closed runtime补充。
```

它不等于：

```text
对所有可能未知向量、任意未来模型和任意参数都具有数学上绝对零漏检证明。
```

最终文档必须使用：

```text
zero observed false accept on the frozen qualification corpus
```

不得使用未经证明的：

```text
mathematically impossible to miss any harmful output
```

## 5.2 Exact audit 仍是权威

Proxy 只能减少 exact audit 频率。以下仍必须 exact：

- final reported residual；
- condensed true residual；
- full augmented residual；
- official R/T/A；
- periodic/anomaly-triggered selected local audit。

---

# 6. Lane A：Borrowed / Zero-Copy Exact Local Action

## 6.1 数学身份

对 slab `s` 的 index restriction `R_s`，局部矩阵 action 为：

```math
A_s z_s = R_s A_{shift} R_s^T z_s.
```

允许的优先实现：

```text
local z_s
-> lift into persistent global zero vector on slab indices
-> apply the same shifted-F action used by the inner smoother
-> restrict result back to slab indices
```

当外部自由度设为零时，restrict-lift-action 与 local submatrix action 应等价。

## 6.2 实现合同

建议新增稳定接口，名称可以调整：

```python
class BorrowedLocalExactAuditor:
    def audit(self, slab_id, rhs_local, correction_local) -> AuditResult: ...
    def destroy(self) -> None: ...
```

必须：

- 复用已有 `action_operator`；
- 复用 slab global indices/scatter；
- 使用 persistent PETSc work vectors；
- 不保存 local CSR `indptr/indices/values`；
- 不复制 assembled global matrix；
- 不构造 ILU；
- 不启动 subprocess；
- 不做文件交换；
- destroy 后不可调用。

## 6.3 可选 fallback research backend

若 parent assembled/shifted matrix 在当前 profile 中合法常驻，可比较：

```text
ephemeral local submatrix exact audit
```

流程：

```text
create submatrix on audit event
-> apply
-> destroy immediately
```

但不得将其持久保存。若 parent matrix 在 compact profile 已释放，则记录不适用，不得因此恢复完整矩阵常驻。

## 6.4 Equivalence Gate

对所有 16 slabs，使用：

- deterministic random vectors；
- Task005 real RHS；
- learned candidate outputs；
- scale/phase variants。

要求：

```text
relative action error <= 1e-12
relative local rho error <= 1e-12
all finite
same shifted diagonal convention
same operator fingerprint identity
```

任一 slab失败，Lane A fail closed。

---

# 7. Lane B：Low-Storage Proxy Families

Proxy 必须只保存小型 metadata，不得保存完整 `A_s`。

## 7.1 必选基本 guards

每次 learned output 必须先检查：

```text
finite
checkpoint SHA
operator fingerprint
slab routing identity
input norm range
output norm range
correction/input norm ratio
normalization scale consistency
```

## 7.2 Reduced equation certificate

对 learned model 的 basis `U_s,V_s`，允许预计算：

```math
B_s = U_s^H A_s V_s.
```

运行时计算：

```math
c_s = U_s^H r_s,
\quad d_s = learned\ reduced\ output,
\quad \rho_{red}=\frac{\|c_s-B_s d_s\|}{\|c_s\|}.
```

`B_s` 为小型 `rank x rank` 矩阵。必须计入存储。

Reduced certificate 单独不能视为安全通过，因为它可能漏掉 basis 外残差。

## 7.3 Deterministic procedural sketches

至少比较：

```text
CountSketch / sparse JL
q = 64 / 128 / 256
one seed / two independent seeds
```

Sketch matrix不得显式保存为 `q x n` dense array。必须由冻结 seed、hash 和 sign 规则程序化生成。

允许预计算：

```math
G_s = S_s A_s V_s,
```

运行时：

```math
s_r=S_s r_s,
\quad s_z=G_s d_s,
\quad \rho_{sketch}=\frac{\|s_r-s_z\|}{\|s_r\|}.
```

存储仅允许：

- seed/hash metadata；
- `G_s`；
- small normalization/calibration statistics。

## 7.4 Composite proxy

最终候选应组合：

```text
finite/norm guards
+ reduced equation certificate
+ two independent procedural sketches
+ calibrated conservative margin
```

示例形式：

```text
proxy_score = max(alpha_red * rho_red,
                  alpha_s1 * rho_sketch_1,
                  alpha_s2 * rho_sketch_2)
              + margin
```

阈值与 margin 必须在 qualification corpus 上冻结，不能在 live shadow 后事后调成有利结果。

---

# 8. Qualification Corpus 与数据身份修正

## 8.1 Task005 split 重新标记

Task005 已使用 H 选择候选，因此：

```text
H = consumed screening set
```

不得继续称为 untouched final holdout。

Task005 V 未用于正式候选筛选，可作为 proxy calibration 的一部分，但必须明确其与 T1/T2/H 来自同一确定性物理 RHS 轨迹的错位抽样，不能称为独立物理分布。

## 8.2 Proxy corpus

至少包含：

```text
Q0 = Task005 V real-Krylov samples, calibration only
Q1 = Task005 consumed H, locked replay test
Q2 = fresh same-operator S capture with new non-overlapping schedule
Q3 = same-operator P-polarization capture, only if all 16 fingerprints exactly match
Q4 = fixed complex S/P linear-combination capture, only if fingerprints match
Q5 = deterministic injected candidate-output perturbations
```

Q2/Q3/Q4 必须来自 clean records。若 P 或组合改变 operator fingerprint，该 lane 立即标记 `not_same_operator`，不得强行复用。

## 8.3 Capture metadata 修正

Fresh capture 至少应记录：

```text
rhs
slab_id
apply_index
outer_iteration if available
pre/post-smooth phase if available
restart window if available
rhs norm
source RHS identity
source run SHA
```

若当前代码无法可靠记录 outer/phase metadata，必须在 outcomes 中明确，而不能宣称已分层覆盖。

---

# 9. Harmful Ground Truth 与 False-Accept 定义

对每个 candidate output `z`，borrowed exact audit 给出：

```math
\rho_{exact}=\frac{\|A_s z-r_s\|}{\|r_s\|}.
```

至少将以下定义为 harmful：

```text
NaN/Inf
rho_exact >= 1.0
rho_exact > 1.05 * rho_ILU
abnormal output norm
wrong checkpoint/operator/slab identity
```

定义：

```text
false accept = proxy accepts output, but exact ground truth says harmful
false reject = proxy rejects output, but exact ground truth says non-harmful
```

主安全 Gate：

```text
false accept = 0 on Q0-Q5
all catastrophic injections detected
```

可用性 Gate：

```text
unmodified admissible learned outputs accepted >= 99%
overall false reject <= 5%
no slab false reject > 10%
```

若只能通过拒绝全部输出达到 zero false accept，则视为 proxy 不可用。

---

# 10. Failure Injection Matrix

必须在冻结 seed 下测试至少以下故障。

## 10.1 数值损坏

```text
NaN
+Inf / -Inf
single-coordinate spike
random bit/precision truncation simulation
complex64 rounding stress
zero output
```

## 10.2 幅值与相位

```text
scale = 0.25 / 0.5 / 1.5 / 2 / 4
phase rotation = pi/8 / pi/4 / pi/2 / pi
amplitude drift over apply index
phase drift over apply index
```

## 10.3 空间方向

```text
in-basis worst reduced direction
basis-orthogonal random noise
high-frequency component
boundary-localized component
interface-localized component
wrong slab output routed to current slab
stale model/checkpoint
```

## 10.4 Drift

```text
slow linear drift
step change
periodic corruption
one-rank-only corruption
one-slab-only corruption
late-iteration-only corruption
```

每种故障必须记录：

- exact harmful status；
- proxy decision；
- periodic audit detection apply；
- anomaly-triggered exact audit；
- detection latency；
- false accept/reject；
- fail-closed outcome。

---

# 11. Periodic Exact Audit Schedule

## 11.1 必须比较的周期

至少比较：

```text
K = 4 / 8 / 16 / 32 global one-level applies
```

推荐 schedule：

```text
first N applies: audit all enabled slabs
then every K applies: audit one rotating slab per owner
anomaly: audit all owner slabs immediately
restart boundary: optional exact audit
```

在 4 slabs/owner 时，每个 slab 的最大正常审计间隔为约 `4K` one-level applies，必须明确记录。

## 11.2 Latency Gate

冻结最终 schedule 前要求：

```text
all step-change/catastrophic drift detected immediately by proxy or next anomaly audit
all slow drift detected within one full owner rotation
no injected drift survives to the end of qualification replay
```

## 11.3 Runtime Gate

必须拆分：

```text
proxy every-call time
borrowed exact audit time
amortized exact audit time
anomaly audit time
PETSc vector/scatter time
operator action time
MPI wait
```

规划要求：

```text
model + proxy + amortized exact audit <= 7.2 ms / four-slab owner batch preferred
and projected end-to-end owner path <= 11.514 ms
```

若只使用 CUDA 模型才能满足预算，必须额外完成同进程 PETSc/CUDA 生命周期和同步审计；不得用 subprocess。

---

# 12. Storage 与生命周期 Gate

## 12.1 Persistent storage ledger

必须逐项记录：

```text
model parameters
input/output bases
reduced map / MLP
reduced operator certificate
sketch AV products
sketch seeds/metadata
normalization statistics
persistent PETSc work vectors
GPU persistent buffers
proxy state
private local CSR
```

硬条件：

```text
private persistent local CSR bytes = 0
```

## 12.2 Memory Gate

Preferred：

```text
model + proxy + persistent buffers <= 33.670 MiB / owner
```

Speed-first exploratory：

```text
<= 50.505 MiB / owner
and live external worker peak <= 1.10 * paired baseline
```

只有 Preferred 可称为 memory-neutral audit architecture。

## 12.3 生命周期

必须验证：

- repeated apply 无 RSS 持续增长；
- borrowed work vectors只创建一次；
- exact audit不留下 ephemeral matrices；
- GPU buffers可销毁；
- destroy 幂等；
- destroy 后 audit/model 不可调用；
- ordinary ILU path无额外 storage。

---

# 13. R4 Live Shadow Qualification

## 13.1 模型身份

允许复用 Task005 frozen R4 checkpoints：

```text
R4 = {0,5,9,15}
preferred first model = smallest admissible D0 linear low-rank policy
optional comparison = accepted nonlinear rank-64 GELU skip
```

复用前必须验证：

- checkpoint SHA；
- operator fingerprint；
- model configuration；
- Task005 provenance；
- no retraining。

## 13.2 Shadow 配置

```text
learned output computed on R4
proxy every call
periodic borrowed exact audit
ILU still writes back for all slabs
global solver remains baseline action
```

因此 shadow 的作用是测试 runtime/safety/storage，不是 learned acceleration。

## 13.3 Live Shadow Gate

必须：

```text
full reported/condensed/augmented residual <= 1e-6
R/T/A and closure pass
ILU writeback exactly preserved
zero observed false accept on audited live calls
all anomaly injections fail closed in controlled replay
no persistent private CSR
no swap
external peak <= 1.10 * paired baseline
projected Task005 owner path remains within budget
```

Live shadow中无 harmful 不能写成全 16 learned profile 安全；只能资格化 R4 audit architecture。

---

# 14. 实施阶段

## P0：冻结基线、证据与身份修正

1. 记录 branch、HEAD、remote、dirty status；
2. 不执行分支操作；
3. 读取 Task005 review；
4. 将 H 标记为 consumed screening set；
5. 校验 R4 checkpoints 和 datasets checksum；
6. 运行 clean h5 baseline；
7. 完整测试和 diff check。

P0 失败不得继续。

## P1：Borrowed exact action

1. 实现 borrowed local exact auditor；
2. persistent global/local work vectors；
3. 16-slab CSR equivalence；
4. local rho equivalence；
5. MPI2/MPI4 owner test；
6. destroy/lifecycle；
7. no-private-CSR ledger。

P1 Gate：16/16 equivalence `<=1e-12`。

## P2：Proxy family screen

1. basic guards；
2. reduced certificate；
3. q=64/128/256 sketches；
4. one/two seeds；
5. composite proxy；
6. Q0 calibration；
7. 阈值冻结。

P2 只能用 Q0 校准，不能看 Q1-Q5 后再调阈值。

## P3：Locked replay qualification

1. Q1/Q2；
2. 条件性 Q3/Q4；
3. unmodified model outputs；
4. false accept/reject；
5. per-slab acceptance；
6. storage/runtime。

P3 Gate：zero false accept，且 proxy非“拒绝全部”。

## P4：Failure injection

执行第10节完整矩阵。任何 catastrophic false accept立即停止该 proxy。

允许最多一次在**预先冻结 proxy family内部**收紧 margin；不得更换 family后反复寻找正结果。收紧后必须重跑全部 Q1-Q5。

## P5：Periodic audit schedule

1. K=4/8/16/32；
2. rotating owner schedule；
3. anomaly audit；
4. drift detection；
5. latency/runtime；
6. 选择最终 frozen schedule。

## P6：Storage/lifecycle qualification

1. persistent ledger；
2. private CSR = 0；
3. owner/global storage；
4. external RSS；
5. repeated apply；
6. destroy；
7. ordinary path equivalence。

## P7：R4 live h5 shadow

1. clean paired baseline/shadow；
2. ILU写回；
3. learned + proxy + periodic exact audit；
4. full residual/RTA；
5. MPI wait/runtime；
6. external memory；
7. zero false accept on audited live calls。

## P8：决策与审阅包

整理 outcomes，选择最终 classification。不得自动训练 full16 models，不得自动进入 Task005 P3。

---

# 15. 测试要求

至少新增或更新：

1. borrowed action vs CSR 16-slab equivalence；
2. shifted diagonal convention equivalence；
3. lift/restrict index correctness；
4. overlap slab exact action；
5. MPI2/MPI4 owner borrowed audit；
6. no persistent CSR contract；
7. persistent work-vector reuse；
8. reduced certificate correctness；
9. procedural sketch deterministic hash/sign；
10. sketch generated without dense matrix；
11. sketch batch/independent equality；
12. composite proxy frozen-threshold contract；
13. Q0 calibration cannot read Q1-Q5；
14. false-accept accounting；
15. false-reject accounting；
16. NaN/Inf injection；
17. scale/phase injection；
18. basis-orthogonal injection；
19. wrong slab routing；
20. checkpoint/fingerprint mismatch；
21. precision truncation；
22. slow drift detection；
23. anomaly-triggered exact audit；
24. periodic schedule determinism；
25. maximum detection latency；
26. fail-closed rank exception；
27. proxy storage ledger；
28. repeated apply no RSS growth；
29. destroy idempotence；
30. R4 live shadow writeback equals ILU；
31. h5 full residual/RTA shadow integration；
32. ordinary ILU path unchanged；
33. Case095 contract checker；
34. complete existing test suite；
35. Ruff/compileall；
36. `git diff --check`；
37. heavy artifact ignore audit。

随机过程必须固定 seed。性能测试必须记录 warm-up、同步、线程、affinity 和 device。

---

# 16. 禁止事项

本任务不得：

- 执行任何分支管理或 `master` 操作；
- 修改 ordinary default；
- 训练 16 个新模型；
- 扩大 NN hidden/rank 来绕过 audit blocker；
- 运行 learned-active no-hidden-ILU global candidate；
- 运行 h3/h2；
- 使用 private persistent local CSR；
- 恢复完整 assembled matrix 常驻只为审计；
- 每次 audit 创建无法及时释放的大对象；
- 用 subprocess/file exchange 调用模型；
- 使用 Q1-Q5 调 proxy 阈值后再称为独立测试；
- 通过拒绝所有输出制造 zero false accept；
- 把 zero observed false accept写成普适数学证明；
- 删除 final global true residual/RTA；
- 在 true no-fallback 语义下偷偷构造 ILU；
- 用 microbenchmark替代 live shadow；
- 把 R4 audit qualification外推为16-slab learned-PC成功；
- 提交 heavy artifacts。

---

# 17. 建议代码职责

名称可以调整，但职责必须分离。建议：

```text
src/solvers/borrowed_local_audit.py
src/solvers/learned_proxy_audit.py
src/solvers/audit_schedule.py
src/solvers/local_slab_solver.py
src/solvers/physical_slab_two_level.py

benchmarks/neural_pc/build_task006_proxy_corpus.py
benchmarks/neural_pc/qualify_task006_proxy.py
benchmarks/neural_pc/inject_task006_failures.py
benchmarks/neural_pc/benchmark_task006_audit_runtime.py
benchmarks/run_task006_r4_shadow.py

benchmarks/cases/095_zero_copy_learned_pc_audit/

src/test/test_46_borrowed_local_audit.py
src/test/test_47_learned_proxy_audit.py
src/test/test_48_periodic_audit_schedule.py
src/test/test_49_task006_r4_shadow.py
src/test/test_50_para_task006_contract.py
```

不得将 exact action、proxy、failure injection、live shadow 和文档全部堆在一个脚本中。

---

# 18. 成功 Gate

## 18.1 Safety Gate

```text
borrowed action equivalence 16/16 <= 1e-12
proxy false accept = 0 on frozen Q1-Q5
all catastrophic injections detected
all drift detected within frozen latency
anomaly audit fail closed
```

## 18.2 Usability Gate

```text
unmodified admissible output acceptance >= 99%
overall false reject <= 5%
no slab false reject > 10%
```

## 18.3 Storage Gate

Preferred：

```text
private CSR = 0
model + proxy + buffers <= 33.670 MiB / owner
```

Speed-first：

```text
private CSR = 0
model + proxy + buffers <= 50.505 MiB / owner
external shadow peak <= 1.10 * paired baseline
```

## 18.4 Runtime Gate

```text
model + proxy + amortized exact audit <= 7.2 ms / four-slab owner batch preferred
projected end-to-end owner path <= 11.514 ms
```

## 18.5 Live Shadow Gate

```text
numeric/RTA pass
ILU writeback unchanged
zero observed false accept on audited calls
no swap
no persistent private CSR
memory and runtime Gate pass
```

---

# 19. 最终分类

最终 classification 必须从以下选择：

```text
audit_architecture_qualified_memory_neutral
audit_architecture_qualified_speed_first
audit_architecture_safety_failure
audit_architecture_false_reject_failure
audit_architecture_runtime_failure
audit_architecture_storage_failure
borrowed_exact_action_infeasible
periodic_audit_latency_failure
live_shadow_numeric_failure
infrastructure_incomplete
```

可同时记录 secondary findings，但不得自造含义重叠的名称。

---

# 20. Task005 恢复条件

只有 Task006 最终为：

```text
audit_architecture_qualified_memory_neutral
```

或：

```text
audit_architecture_qualified_speed_first
```

且 ChatGPT review 接受后，才可建议新的独立任务从 Task005 P3 恢复：

```text
train/select 16 independent models
-> all-slab shadow
-> diagnostic fallback
-> true no-hidden-ILU
-> three paired A/B
```

Task006 不自动执行恢复，也不自动创建后续任务。

---

# 21. 任务完成标准

本任务不能以“private CSR 删除了”或“proxy 看起来相关”结束。至少必须回答：

1. borrowed exact action 是否与 local CSR 对所有 16 slabs 等价？
2. exact audit 单次和摊销成本是多少？
3. 哪种 reduced/sketch proxy 被选择，为什么？
4. calibration 与 locked test 是否严格隔离？
5. false accept 是否为 0？
6. false reject 是否可接受？
7. 哪些注入最难检测？
8. periodic schedule 的最大检测延迟是多少？
9. anomaly-triggered audit 是否可靠？
10. private persistent CSR 是否真正为 0？
11. model、proxy、work vectors、GPU buffers各占多少？
12. owner/global memory是否通过冻结预算？
13. model+audit是否仍满足未来Task005 runtime预算？
14. R4 live shadow是否通过full residual/RTA和external memory？
15. ordinary ILU path是否完全不变？
16. 是否允许后续从Task005 P3恢复？
