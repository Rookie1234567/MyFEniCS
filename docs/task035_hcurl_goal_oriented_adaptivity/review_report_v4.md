# Task035 Review V4：Phase C/D 受控结论与 Phase E 最小自适应闭环

## 1. 审查结论

```text
review_status = PHASE_CD_ACCEPTED_PHASE_E_RECOVERY_BATCH_AUTHORIZED
phase_a = accepted
phase_b = accepted_with_scope
phase_c = complete_controlled_negative
phase_d = complete_controlled_negative_with_tetra_control_signal
production_estimator_selected = false
production_backend_selected = false
phase_e = authorized_as_two-part_recovery_batch
phase_f_p4_h5_heavy = not_authorized
review_checkpoint = after_phase_e_recovery_batch
additional_review_inside_phase_e = false
```

本轮审查对象：

```text
branch = codex/20260721-task35-hcurl-goal-oriented-adaptivity
branch_head_at_review = a0488c4f5672c27677fcf01e05ead7cdb163d394
response = docs/task035_hcurl_goal_oriented_adaptivity/response_v4.md
final_phase_cd_record_source = db2d1e7a49f5754de8d0dec6dda3622a9635e6bb
base_master = 5002636852ffb67b4711443da70eb536c303e34e
```

Review V3 授权的 Phase C estimator bake-off 与 Phase D mesh-backend bake-off 已连续执行完成。代码、记录和测试没有显示 WSL、complex ABI、MPI、PETSc/DOLFINx 或既有 Maxwell/Floquet/DtN/QEP/Hybrid production core 回归。

本轮最重要的结论不是“自适应已经成功”，而是把阻塞精确缩小为：

```text
1. sampled strong-residual proxy 不适合作为当前目标问题的 marking 主线；
2. coarse/enriched field-difference R5 proxy 有很强正信号，但还不是 formal two-level FE estimator；
3. Cartesian axis-cut hexa 会产生严重 strip leakage；
4. DOLFINx tetra marked refinement 机制可工作，但尚未与目标周期 Maxwell 求解闭环。
```

因此，Phase C/D 的 `complete_controlled_negative` 接受。下一步不继续堆积更多 sampled proxy，也不直接进入 p4/h5 heavy。Review V4 授权一个连续的 **Phase E recovery batch**：先完成正式 estimator 与周期 tetra backend 接入，再连续完成低成本 p2/p3 adaptive cycles；两个内部部分之间不等待额外审查。

---

## 2. 已接受的 Phase C/D 结果

### 2.1 Phase C target-artifact screen

以下结果接受为低成本方向性证据：

| coarse → enriched | R5 effectivity proxy | R5 Pearson / Spearman | sampled R1 Pearson / Spearman | observable error reduction |
|---|---:|---:|---:|---:|
| p2/h5 → p2/h3 | 0.9086 | 0.9903 / 0.9918 | -0.0356 / -0.0359 | 87.46% |
| p2/h3 → p2/h2 | 0.8106 | 0.9981 / 0.9949 | -0.0768 / -0.0622 | 81.55% |
| p3/h10 → p3/h7.5 | 0.9894 | 0.9892 / 0.9836 | -0.0202 / -0.0361 | 94.00% |

接受的解释是：

- coarse/enriched field difference 与相对 p4/h5 best-available discrete reference 的局部 field difference 高度相关；
- sampled strong Maxwell residual 与该 local-error proxy 基本无相关或轻微负相关；
- R1/R5 Dörfler marked sets overlap 很低，说明两者定位的区域显著不同；
- R5 路线值得进入正式 FE two-level 实现；
- sampled R1 路线应作为负向 diagnostic 保留，不得直接用于 production marking。

### 2.2 B3 material-interface component fixture

B3 接受为 component-level positive：

- actual 3D hexa N1curl p1/p2；
- actual DG0 complex material tags 与 interface facets；
- material-tag fault detection；
- p1/p2 error difference；
- computed directional preference；
- serial/MPI2 compact identity。

它不是目标光栅 corner adaptive qualification，但足以关闭 Phase B 的材料界面 fixture 待办。

### 2.3 B4 Hybrid component fixture

B4 接受为 measured component split：

- accepted target Et/Ht samples；
- external DtN perturbation；
- M80/M120/M160 funnel；
- QEP MPI diagnostic；
- spatial、DtN、internal M 与 QEP residual 分列；
- serial/MPI2 compact identity。

它不构成新的 Hybrid PDE、adjoint 或 adaptive qualification。

### 2.4 Phase D backend screen

接受以下工程结论：

```text
Task034 strip/tensor = controlled_negative
Cartesian axis-cut multi-block hexa = locality blocker signal
tetra marked-refine = research control positive
```

Task034 strip/tensor 已有 actual PDE 证据，但 physical same-error gates 失败；不能继续提升。

DOLFINx tetra control 实际完成 marked refine，并观察到局部尺寸下降和 Nédélec interpolation-error proxy 下降；它证明 simplex refinement/orientation 机制值得进入目标 pipeline qualification。

### 2.5 测试

接受最终测试：

```text
C+D focused test88-test97 = 33 passed
full repository pytest = 527 passed, 18 skipped
serial/MPI2 compact identity = pass
Ruff = pass
compileall = pass
git diff --check = pass
```

Phase A 环境、MUMPS/PEP、Task034 heavy references 和完整 artifact inventory 不得因本 Review 重跑。

---

## 3. 必须保持准确的资格边界

### 3.1 当前 R5 不是 formal hierarchical estimator

当前 R5 是：

```text
accepted coarse field sample - accepted globally enriched field sample
```

它具有很强 correlation/effectivity 信号，但没有完成：

- 当前 solve 上的 enriched FE correction；
- cell/patch local enriched space；
- local correction equation；
- coarse-cell indicator assembly；
- estimator-marked local refinement；
- refinement 后重新 solve 的因果验证。

表中的 81%–94% observable reduction 来自“整个 enriched 离散点相对 coarse 点更接近 p4/h5”，不是“按 R5 marked set 局部细化后得到的下降”。因此不得将其写为 `R5_real_case_screen_pass` 或 production estimator。

### 3.2 sampled R1 negative 不等于 residual estimator 理论失败

当前 R1 通过规则采样数组和 `numpy.gradient` 计算，不是实际 FE mesh 上的：

- cell-integrated volume residual；
- facet jump；
- material/interface contribution；
- periodic/Floquet contribution；
- DtN boundary contribution。

因此准确结论是：

```text
sample_grid_strong_residual_proxy = real_case_negative
formal_cell_face_R1 = not_yet_implemented_on_target_solve
```

下一阶段不应继续调 sampled R1 的归一化来追求相关性，但可以实现一个真实 cell/face R1 作为 R5 的独立 baseline。

### 3.3 当前 hexa blocker 只适用于 Cartesian axis-cut 路线

`multi_block_conforming_hexa` 当前并未生成和求解一个实际 transition-cell multi-block mesh，而是量化 Cartesian axis cuts 贯穿 tensor product 后的 cell leakage。

因此建议把状态准确化为：

```text
cartesian_axis_cut_hexa_locality_blocker
```

不得扩大为“所有 conforming hexa local refinement 不可行”。具有 octree/transition template、prism/pyramid、qualified hanging-node H(curl) constraint 或 nonmatching interface 的路线仍未实现；但这些路线不应继续阻塞当前 Task035 的最小 adaptive MVP。

### 3.4 tetra 的 Jacobian 证据当前不完整

当前 `_cell_volumes` 使用：

```python
abs(det(J)) / 6
```

但输出字段称为：

```text
minimum_signed_volume_proxy
```

取绝对值后不能检测负 Jacobian/反转单元，因此当前只证明：

```text
minimum_absolute_tetra_volume > 0
```

不能声称已经通过 signed/positive Jacobian Gate。

Phase E 前必须：

1. 将现有字段改名为 `minimum_absolute_tetra_volume`；
2. 增加独立 Jacobian determinant/orientation audit；
3. 报告 minimum determinant、nonpositive count 和质量分布；
4. serial/MPI2 一致；
5. 不删除首次 MPI2 topology-to-geometry indexing failure record。

### 3.5 Phase C 的 MPI identity 不是 distributed estimator scalability

target-artifact screen 在每个 rank 读取 compact sample arrays，再按 `global_sample_id % mpi_size` 做标量分区。这足以验证 deterministic compact reduction，但不是实际 distributed mesh/cell ownership 上的 estimator assembly。

Phase E 的正式 estimator record 必须来自实际分布式 mesh ownership，不能用 modulo sample partition 代替。

---

## 4. Phase E recovery batch：总体路线

本 Review 将 Phase E 拆成两个连续内部部分：

```text
Phase E0  formal estimator + periodic tetra backend integration
Phase E1  p2/p3 low-cost adaptive cycles
```

E0 完成后不等待审查，内部 Gate 通过即直接进入 E1。E1 完成后提交 `response_v5.md`，再集中等待 Review V5。

本批次目标是第一次形成真实闭环：

```text
TARGET SOLVE
→ FORMAL ESTIMATE
→ MARK
→ PERIODIC CLOSURE
→ ACTUAL LOCAL REFINE
→ REBUILD TAGS/FLOQUET/DtN
→ TARGET RE-SOLVE
→ OBSERVABLE ERROR AUDIT
```

---

# 5. Phase E0：正式 estimator 接入

## 5.1 优先主线：actual two-level R5

R5 是当前唯一具有强真实方向信号的候选。第一版允许采用比 patch-local solve 更快的全局 two-level 实现，但命名必须准确。

优先级：

### 路线 E0-R5A：same-mesh p-enriched two-level

```text
coarse solve: p2
+
enriched solve: p3 on the same mesh
→ project/compare fields
→ localize correction energy to coarse cells
```

若 p3 same-mesh 资源不适合，可采用：

### 路线 E0-R5B：same-degree uniformly refined two-level

```text
coarse p2 mesh
+
uniformly refined p2 reference mesh
→ transfer/project enriched field
→ localize correction to coarse cells
```

两者都必须明确：

- 是 global two-level estimator，不冒充 patch-local estimator；
- enriched solve 的 residual 和 official observables 通过；
- correction 的 local cell contributions finite/nonnegative；
- global indicator 与 correction norm 闭合；
- cell IDs、marked-set hash 和 MPI ownership canonical；
- 不使用保存的 sample-grid difference作为最终 indicator。

### 后续增强：local patch R5

只有 global two-level MVP 工作后，再考虑：

- edge/cell star patch；
- enriched N1curl space；
- zero tangential correction boundary；
- local defect solve；
- overlap assembly。

不要让 patch infrastructure 阻塞第一版 adaptive closure。

## 5.2 actual cell/face R1 baseline

实现真实 FE baseline，用于对照 R5，不以 sampled R1 为基础。

至少分列：

```text
volume curl-curl residual
interior curl-flux jump
material/interface term
external DtN boundary term
Floquet/periodic consistency diagnostic
```

建议通过 DG0/cellwise accumulator 或可审查 cell kernel 生成每个 owned cell 的平方贡献。不得只输出 global scalar。

R1 可以得到 `real_case_negative`；只要 R5 主线仍工作，不阻塞 E1。

## 5.3 goal-oriented lane

actual DWR adjoint 当前不是 E0 的硬 blocker。优先策略：

```text
R5 closes first adaptive loop
→ G1/G2 actual adjoint remains parallel research lane
```

若实现成本可控，可在 p2 coarse target 上加入一个离散 adjoint：

- goal 选 total R/T/A 中一个，或非平凡 R00/order amplitude；
- 明确 complex adjoint、实值 functional 和 normalization；
- 与 coefficient directional finite difference 比较。

但不得因 G1/G2 未完成而阻塞 R5+tетра MVP。

## 5.4 代码位置

正式候选不得继续只放在 `src/validation/task035_*`。

推荐最小模块：

```text
src/adaptivity/hcurl_cell_residual.py
src/adaptivity/hcurl_two_level.py
src/adaptivity/marking.py
src/adaptivity/adaptive_cycle.py
```

benchmark runner 只负责参数、provenance、watchdog 和 record，不复制 estimator 数值核心。

---

# 6. Phase E0：周期 tetra backend 接入

## 6.1 当前主 backend 决定

Phase E research MVP 采用：

```text
DOLFINx tetra marked refinement
```

身份为：

```text
research adaptive backend
not production default
```

Cartesian hexa axis-cut 路线本批次停止继续投入。未来 transition-cell/hexa route 另行决定，不阻塞 tetra MVP。

## 6.2 目标几何 tetra 初始网格

建立 Task034 fixed geometry 的 tetra mesh，至少保持：

- x/y 周期面几何一致；
- grating/substrate/air material tags；
- top/bottom DtN 面 tags；
- target physical dimensions；
- deterministic mesh hash；
- MPI repartition/ghost consistency。

第一步可以使用低成本 coarse target-shaped mesh 做 pipeline smoke；正式 E1 起点再使用可审查的 p2 coarse/h5-like mesh。

## 6.3 periodic marker closure

Dörfler marking 后，refine 前必须扩展 marked entities，保证：

```text
master periodic boundary refinement
↔ slave periodic boundary refinement
```

至少完成：

- x-periodic mate closure；
- y-periodic mate closure；
- x/y periodic corner and edge closure；
- translated boundary facet signature identity；
- refined boundary trace isomorphism；
- deterministic closure hash。

不得先单边 refine，再依赖 coordinate tolerance 强行配对不匹配 trace。

## 6.4 tag rebuild 与 Floquet requalification

每轮 refinement 后：

- rebuild/transfer cell material tags；
- rebuild exterior and interface facet tags；
- rebuild Floquet constraints；
- check slave/master DoF count and phase/orientation；
- check top/bottom DtN trace；
- serial/MPI2，必要时 MPI4 identity。

若当前 high-order tetra Floquet 路径不支持 p2，先完成 p1 topology smoke，再实现/资格化 p2；但 E1 的正式物理序列仍以 p2 为目标。

## 6.5 mesh quality

每轮至少记录：

```text
cells
vertices
minimum/quantile absolute volume
minimum Jacobian determinant
nonpositive Jacobian count
radius ratio or equivalent quality
marked-region vs outside size
partition imbalance
periodic boundary signature hash
```

任何 nonpositive Jacobian、周期 trace 非同构或未资格化 hanging node 都禁止作为正结果继续求解。

## 6.6 field transfer

优先每轮重新从物理参数组装并求解；若使用前一轮解作 initial guess，应有可审查的 H(curl) transfer/projection，并且 transfer error 单独记录，不能混入 estimator error。

---

# 7. Phase E1：低成本实际 adaptive cycles

## 7.1 首个闭环：Full3D p2 target

第一条正式序列：

```text
13.5 nm
10 deg grazing
S polarization
Task034 fixed geometry
Full3D
p2
research tetra backend
R5 global two-level marking
Dörfler theta = 0.5
```

先完成至少 3 个 cycle；满足明确终止条件可在第 2 个 cycle 后受控停止，最多不超过 4 个 cycle。本批次不遍历大量 theta。

每轮：

```text
SOLVE
→ R5 ESTIMATE
→ R1 BASELINE ESTIMATE
→ MARK
→ PERIODIC CLOSURE
→ REFINE
→ REBUILD TAGS/FLOQUET/DtN
→ SOLVE
→ COMPARE
```

## 7.2 reference 与对照

reference 必须明确为 best-available discrete reference，不称 continuum truth。

至少同时做两个对照：

1. Task034 accepted p4/h5 or p3/h3 observables/field samples；
2. 相近 DoF/rows 的 uniform tetra refinement control。

不能只证明 adaptive cycle 比自己的 coarse mesh 好；还要判断相同成本下是否优于 uniform refinement。

## 7.3 每轮必须输出

```text
mesh/closure/tag hashes
cells, DoF, rows, NNZ
estimator total and components
R5 effectivity/proxy
R1/R5 correlation and marked overlap
marked-set hash and periodic-closure expansion ratio
full explicit true residual
R/T/A/A_volume
R00 and significant diffraction orders
selected-plane E/H
interface Et/Ht when available
energy closure
memory and stage time
mesh quality and partition imbalance
```

official R/T/A 只能来自 residual Gate 通过的场。

## 7.4 成功 Gate

至少需要两个连续 estimator-marked cycle 满足：

- target observable error 实际下降；
- field/interface error 不隐藏恶化；
- residual/energy gates 通过；
- periodic/Floquet and tag rebuild 通过；
- estimator global/local consistency 通过；
- adaptive sequence 在相近成本下不劣于 uniform tetra control。

若只有第一个 cycle positive、第二个反弹，不能宣称 adaptive mainline 通过。

## 7.5 p3 smoke

只有 p2 至少两个 cycle positive 后，继续一个低成本 p3 smoke：

- 同一 backend/marking policy；
- 至少一个 marked refinement；
- 检查高阶 orientation、MPI identity 和 observable trend。

p3 smoke 失败只关闭 p3 lane，不取消已通过的 p2 controlled result。

---

# 8. Phase E 内部停止规则

Codex 不得因以下情况停止整个 batch：

- actual R1 lane 失败；
- G1/G2 adjoint 未完成；
- p3 smoke 失败；
- 一个 theta candidate 为负；
- 一个局部 test、README、schema、record 或 lint 问题；
- Cartesian hexa 路线保持 blocker；
- 单个 cycle 可解释地 negative。

处理方式：

```text
局部修复并 targeted rerun
或
关闭该 lane、保存 controlled negative、继续 R5+tетра 主线
```

只有以下情况停止整个 Phase E batch：

1. WSL complex ABI、source SHA 或 baseline hash 不一致；
2. production/accepted numerical core 被意外改变且旧证据失效；
3. periodic boundary trace 无法形成同构配对；
4. nonpositive Jacobian 或不合格 mesh 被用于正式 solve；
5. full true residual 或 official physical observables 系统性失败；
6. MPI identity 出现无法局部解释的系统性偏差；
7. 内存、swap、磁盘或进程资源 Gate；
8. 工作准备越过本 Review 进入 p4/h5 heavy adaptive 或 ordinary-default change。

---

# 9. 测试与运行节奏

继续使用 Windows Codex 客户端编排、WSL Ubuntu 后端执行。

不得重复：

- Phase A 环境完整资格化；
- MPI1/2/4/8 MUMPS/PEP matrix；
- Task034 六份 artifact 全量 hash；
- Task034 p3/p4/M heavy matrix；
- 每次小改动后的 full pytest。

测试金字塔：

```text
每个 estimator/backend 小步：targeted unit/fixture test
周期 tetra pipeline 收口：serial + MPI2 topology tests
每个 adaptive cycle：cycle-specific physics/evidence checker
E0 收口：Task035 E0 focused suite
E1 收口：Task035 Phase E focused suite
整个 Phase E batch 结束：正确 activation 下 full pytest 一次
```

正式 measured records 优先在 clean committed source SHA 上运行。低成本 cycle 若在提交前运行，最终必须在 clean commit 上重跑 accepted records。

---

# 10. Phase E 后交付

完成 E0+E1 后新增：

```text
docs/task035_hcurl_goal_oriented_adaptivity/response_v5.md
```

不要创建额外 addendum 或平行 review 文件。

Response V5 至少包含：

- exact base、implementation 和 final branch HEAD；
- actual R5 数学定义和实现身份；
- actual cell/face R1 decision；
- tetra periodic closure/Floquet/tag/Jacobian qualification；
- 每个 adaptive cycle 的完整表；
- uniform tetra cost-matched control；
- p2 sequence decision；
- p3 smoke decision；
- all controlled negatives；
- memory/time and MPI identity；
- focused/full tests；
- 是否满足进入 Phase F 的前置条件；
- evidence index 和 clean worktree status。

完成后停止等待 Review V5。

本 Review **不授权**：

```text
Phase F p4/h5 heavy adaptive
Phase G Hybrid adaptive campaign
production estimator/backend promotion
ordinary-default change
master merge
```

只有 Phase E 形成至少一个真实 estimator-marked、周期闭合、物理误差持续下降的 p2/p3 sequence 后，才讨论 Phase F。
