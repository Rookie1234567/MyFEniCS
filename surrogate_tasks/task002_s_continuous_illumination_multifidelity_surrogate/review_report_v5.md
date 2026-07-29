# Task002 Review Report V5

## 1. 审阅结论

```text
review_status = M4_authorized_after_P0_campaign_preflight
reviewed_branch = codex/only-one-13p5nm-surrogate-inversion
M3R_evidence = approved_and_retain
observable_schema_v3 = approved
actual_runtime_topology_identity = approved
p5_only_production_schema = approved
frozen_training_validation_design = approved_and_point_table_frozen
production_route = Full3D_static_uniform_N1curl_p5_h10_single_fidelity
M4_implementation_preflight = authorized
M4_bulk_generation = conditionally_authorized_after_canary
M5_dataset_transfer = not_authorized
M6_surrogate_training = not_authorized
angle_DOE = not_authorized
production_inversion = not_authorized
required_next_action = M4P_campaign_hardening_then_M4_data_generation
```

Case116/M3R 已完成 Review V4 的核心要求。Task002 已从求解器选择阶段进入正式数据生成准备阶段：

- production route 仅允许 `Full3D static uniform N1curl p5/h10/MPI2/thread1`；
- p4/h10、p4/h7.5 与全部 Hybrid 路线均被隔离为 diagnostic-only；
- observable schema 已升级为 `task002.fixed-n0-orders.v3`；
- actual runtime mesh/function-space/Floquet identity 已从真实运行对象读取；
- training、validation、candidate 与 discretization-audit 点表已冻结并 hash-bound。

因此，不再要求额外的大范围 solver-domain qualification，也不要求重新运行 Case114/115 的 80-angle 图。

但是，**不能按当前 campaign 代码直接启动 112 个 production solve**。开始 M4 前必须完成第 4 节的 P0 工程修正。修正后先运行 16 个四维角点 canary；若全部通过原始 numerical Gate 和新增 production Gate，可在同一轮任务中自动继续完成剩余 training 与 frozen validation，无需在 canary 后再次等待 ChatGPT。

M4 完成后必须停止等待 Review V6，不得自行开始代理训练、主动学习、角度 DOE 或反演。

---

## 2. 已接受并冻结的 M3R 证据

### 2.1 p5-only production identity

接受：

```text
model_id = S_PROD_FULL3D_STATIC_P5_H10
solver_route_id = full3d_static_uniform_n1curl_p5_h10
element = uniform N1curl p5
logical mesh family = (6,3,14), boundary-fitted fixed topology
backend = assembly-time static condensation
MPI = 2
threads/rank = 1
fidelity semantics = best_available_operational_high_fidelity
```

p4/h10、p4/h7.5 和 Hybrid 不得进入 production campaign 或 compact production dataset。

### 2.2 Observable v3

接受稳定 mother-response 轴：

```text
schema = task002.fixed-n0-orders.v3
n = 0
m = -7,-6,-5,-4,-3,-2,-1,0,+1,+2,+3
ports = reflection, transmission
components = outgoing S, outgoing P
```

Case116 对 206 个既有 raw order artifact 的 re-extraction 全部通过，没有发现 v3 之外携带功率的 `n=0` order。

需要更正 Review V4 中的一项推断：按照当前 solver 的衍射级符号约定和完整解析审计，正式角域内观测到的 `n=0` propagating union 是 `m=-7..0`，不是 `+2,+3`。保留 `+1,+2,+3` 仍然合理，因为它为完整角域提供稳定、保守、可扩展的 structural-null identity；但不得再表述为“+2/+3 已被证明在当前约定下传播”。

### 2.3 Actual runtime topology

接受 Case116 的 actual runtime observer。它从真实 solved runtime objects 读取：

- distributed mesh cell geometry；
- actual cell/facet tags；
- actual Basix H(curl) element 与 global DoF count；
- actual Floquet constraint objects/entity blocks；
- actual coordinate axes。

5 个 p5 smoke 的 planned-vs-actual、residual、energy、zero-swap 和 cleanup Gate 全部通过。该机制必须保留在每一个 M4 production sample 中，不能为了节约少量时间关闭。

### 2.4 Frozen designs

以下点表冻结：

```text
training = 96 points, seed 20260729
frozen validation = 16 points, seed 20260730
candidate pool = 4096 points, seed 20260731
discretization audit = 8 diagnostic points
```

生产 split 的 exact tuple intersection 均为空。冻结点的四元组 `(h,w,grazing,azimuth)` 不得修改、替换、重抽样或因为后续模型效果不理想而重建。

Case115 旧的 9-angle pilot 已正确降级为 qualification diagnostic：其中 6/9 与 80-angle map 重叠，不能作为正式 frozen validation。该 addendum 接受。

---

## 3. 进入 M4 的数值依据

当前 p5 route 已具备逐点数据生成条件：

```text
center geometry 80-angle map = 80/80 pass
new-point wall range ≈ 61.55--85.27 s
maximum observed RSS ≈ 4.42 GB
peak swap = 0
runtime-topology smoke = 5/5 pass
```

所以 M4 的主要风险不再是单点内存或角域不可解，而是：

1. 112 点 campaign 是否能够可靠断点续跑；
2. 每个 run 是否严格属于冻结 design/split；
3. `n!=0` 数值泄漏是否在几何变化后仍受控；
4. 是否会为每个样本写出无必要的完整 3D 场，造成磁盘和后处理风险；
5. 数据集是否能从 formal record 无歧义地生成并独立验证。

这些必须在 bulk 前解决。

---

## 4. P0：M4 前必须完成的生产加固

### P0-1：campaign 必须真正 resume-safe，并与冻结 design 绑定

当前 campaign 在启动前写入 `reserved`。若进程、终端或机器在求解完成前中断，下一次看到已有 `reserved` 记录会直接返回，样本无法自动恢复。这不满足 112 点长 campaign 的要求。

建立 campaign v3 或等价实现，至少支持：

```text
run-design --design <training_design.json|frozen_validation_design.json>
resume-design
status
```

要求：

1. 读取并验证 design file 的：
   - design id；
   - point tuple hash；
   - source SHA；
   - observable schema；
   - production model/route；
2. 每个 manifest row 保存：
   - design id；
   - design index；
   - split (`train` or `frozen_validation`)；
   - point tuple；
   - point hash；
   - attempt number；
   - run directory；
   - status；
3. 只允许冻结 design 中的点进入 production manifest；任意手工 in-domain 点不得静默加入；
4. 状态机至少区分：
   ```text
   reserved
   running
   measured_pass
   failed_numerical_gate
   controlled_stop_resource
   interrupted_retryable
   ```
5. `measured_pass` 不可变；
6. stale `reserved/running` 必须能经 artifact audit 后：
   - 恢复已完成 record；或
   - 创建新 attempt 目录重试；
   不得要求人工编辑 manifest；
7. manifest 使用原子写入；
8. 每完成一个样本立即 checkpoint；
9. 遇到第一个未解释 numerical Gate failure 时停止后续队列并保留 evidence，不得跳过失败点继续凑数据。

### P0-2：冻结 p5 production 的 `n!=0` 泄漏 Gate 与功率账本

几何与材料沿 y 不变，production response 应位于 `n=0` block。Case114/115 的 p5 角度证据显示 `n!=0` power 很小，但当前 formal record 只记录 leakage，没有把它作为 production Gate。

在现有 p5 80-angle raw evidence 上先独立计算并 track：

```text
max n!=0 reflection power sum
max n!=0 transmission power sum
max n!=0 total power
max n!=0 absolute amplitude
argmax angle/order/component
```

冻结以下 production hard Gate：

```text
n_nonzero_reflection_power_sum + n_nonzero_transmission_power_sum <= 1e-7
n_nonzero_max_abs_amplitude <= 1e-4
```

这两个阈值相对于当前 p5 证据保留了明确裕量，同时足够小，不会把 y 向非物理散射当作可测通道。若 p5-only authority 重算不支持该 Gate，必须 controlled stop 并提交证据，不得临时提高阈值。

同时在 mother response 中增加并验证：

```text
fixed_n0_reflection_power_sum
fixed_n0_transmission_power_sum
raw_R - fixed_n0_R - n_nonzero_R
raw_T - fixed_n0_T - n_nonzero_T
```

账本误差应满足与现有 raw-port identity 相同量级的容差。dataset writer 必须拒绝 leakage Gate 或功率账本不通过的样本。

### P0-3：为 bulk 建立 compact-output profile

当前普通 Full3D flow 会为每个 MPI solve：

- 将场插值到 DG；
- 构造 E/H ParaView arrays；
- 写每 rank VTU 和 PVD；
- 计算大量仅用于场可视化的指标。

这些不是 surrogate bulk 所需的生产数据。对 112 个样本重复写完整 3D 场会增加磁盘、I/O、PyVista 和长 campaign 稳定性风险。

新增明确的 production compact-output profile，例如：

```text
task002_output_profile = compact_surrogate_record
```

compact profile 必须保留：

- formal linear solve；
- true residual；
- R/T/A 与 volume absorption；
- raw DtN order table；
- observable v3 mother response；
- actual runtime topology identity；
- numerical/resource/provenance hashes；
- progress/watchdog records。

默认不写：

- rank-local VTU/PVD/VTX；
-完整体场；
- 与 surrogate 无关的高成本 field visualization arrays。

在两个代表点上做 ordinary-output vs compact-output A/B：

```text
0.5° / 45°, center geometry
10° / 45°, one geometry perturbation
```

要求 residual、R/T/A、volume、raw orders 和 mother response 在既定数值容差内一致。完整场只对少数 diagnostic anchors、最终 blind checks 或 Task003 回代点保留。

### P0-4：建立新的 M4 clean baseline，并重绑定设计元数据

M3R 点表绑定 `eaf17cd...`。完成 P0-1--P0-3 后 source HEAD 必然变化，而 formal preflight 要求 baseline SHA 等于当前 clean HEAD。

因此必须：

1. 完成实现和 targeted tests；
2. 提交一个新的 clean M4 implementation baseline SHA；
3. 使用**完全相同的冻结四元组点表**重新生成 design metadata；
4. 断言旧/new：
   ```text
   training point tuple hash unchanged
   validation point tuple hash unchanged
   candidate point tuple hash unchanged
   audit point tuple hash unchanged
   ```
5. 只更新 source/version/combined design hash；
6. 所有 M4 production solve 绑定新 SHA；
7. Case114/115/116 的旧 PDE 可继续作 diagnostic evidence，但不得与新 M4 production dataset 混源。

### P0-5：formal record 到 compact dataset 的设计绑定适配器

在大批量求解前实现并测试一个确定性的 adapter，将 formal record 转为 production sample record，至少包含：

```text
sample_id
design_id
design_index
split
inputs
aggregates
mother_response
status
source_sha
solver_route_id
parameter/config/topology/artifact hashes
numerical/resource gates
```

独立 dataset checker 必须确认：

- 96 个 training point 每个恰好一个 measured_pass；
- 16 个 validation point 每个恰好一个 measured_pass；
- 无额外点；
- exact tuple 和 design index 一致；
- train/validation 无交集；
- 同一 clean source SHA；
- p5-only route；
- observable v3；
- runtime topology Gate；
- leakage/power-ledger Gate；
- file hashes、array shape/dtype/mask/split 完整。

---

## 5. M4 执行授权与顺序

完成 P0 实现、测试、clean baseline 和 design rebind 后，M4 按以下顺序执行。

### M4-0：16-point canary

先运行 training design 中的 16 个四维 domain corners。

每点必须通过：

```text
completed direct solve
true residual <= 1e-9
abs(R+T+A_volume-1) <= 1e-7
observable v3 complete
no uncovered n=0 power
n!=0 leakage Gate
fixed/raw power ledger
actual runtime topology matches plan
uniform N1curl p5 identity
zero swap
cleanup complete
compact-output identity
```

还要确认：

- campaign resume/retry synthetic interruption test 通过；
- per-sample disk payload 符合 compact profile；
- manifest 与 design index 一致。

若 16/16 通过，可自动继续 M4-1，无需再次等待 Review。

### M4-1：完成 96-point training

- 以 16 点为一个报告批次；
- 每点单独求解，MPI2/thread1；
- 每完成一点原子 checkpoint；
- 每 16 点生成一次 compact campaign summary；
- 任一未解释 failure 立即停止剩余队列。

### M4-2：生成 16-point frozen validation

training 全部完成并通过 dataset pre-check 后，再计算冻结 validation 16 点。

validation record 必须独立标记 `split=frozen_validation`。M4 阶段只生成和封存数据；不得读取其 response 来选择：

- feature map；
- output transform；
- kernel；
- hyperparameters；
- model family；
- acquisition points。

### M4-3：compact dataset 与独立 checker

输出 p5-only dataset v2，并运行完整 checker。建议同时输出：

```text
campaign_manifest.json
negative_or_interrupted_inventory.json
per_batch_resource_summary.json
compact_dataset/
dataset_card_pretraining.md
```

### M4-4：discretization audit

8 个 audit point 不属于 production dataset。可在 production 112 点完成后单独执行 p4/h7.5 diagnostic side，以扩展 `Sigma_discretization`；其结果必须保存在独立 diagnostic package，不能写入 train/validation arrays。

---

## 6. M4 完成后的停止边界

M4 完成后允许：

- dataset checker；
- hash freeze；
- 数据完整性/资源统计；
- training-only 的纯数据分布检查；
- compact package 准备。

M4 完成后不允许：

```text
PCE fit
GP fit
feature-map selection
power transform selection
hyperparameter search
frozen validation evaluation
adaptive acquisition
angle Fisher ranking
synthetic inversion
Task003
```

这些等待 Review V6 和后续工作站训练阶段授权。

---

## 7. 测试要求

P0/M4 至少新增或更新：

1. campaign design membership 与 hash validation；
2. stale reservation recovery；
3. interrupted attempt retry；
4. measured-pass immutability；
5. failed sample cannot enter dataset；
6. p4/Hybrid/手工点 production rejection；
7. compact vs ordinary output A/B；
8. p5 `n!=0` leakage authority 与 Gate；
9. fixed/raw reflection/transmission power ledger；
10. formal-record-to-sample adapter；
11. dataset exact design coverage；
12. training/validation split isolation；
13. source SHA rebind with unchanged point-tuple hashes；
14. actual runtime topology on compact profile；
15. compileall 和 `git diff --check`。

Ruff 仅在资格化环境已存在时运行；不得为 lint 改动 FEM ABI。

---

## 8. 建议交付物

建议建立：

```text
benchmarks/cases/117_task002_p5_bulk_campaign/
  config.json
  expected.json
  records/campaign_preflight.json
  records/p5_leakage_authority.json
  records/compact_output_equivalence.json
  records/design_rebind.json
  records/canary_16.json
  records/training_96.json
  records/frozen_validation_16.json
  records/dataset_verification.json
  records/resource_summary.json

surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
  outcomes/m4_p5_data_generation.md
  outcomes/m4_dataset_report.md
  response_v6.md
```

完成后仅提交并推送当前代理分支，然后停止等待 Review V6。

---

## 9. 最终判断

```text
Can Task002 enter the next stage?  YES.
Next stage = hardened p5-only M4 data generation.
Can current code start bulk immediately?  NO, first complete P0-1..P0-5.
Can it continue automatically after a 16-point canary?  YES, if 16/16 Gates pass.
Can surrogate training start after M4 without review?  NO.
```

M3R 已经把物理求解路线、输出身份、拓扑和点表冻结清楚。现在应一次性把 campaign 与 dataset 的生产工程做好，然后完成 p5 单保真训练/验证数据，而不是再回到 Hybrid 或 p4 多保真路线。