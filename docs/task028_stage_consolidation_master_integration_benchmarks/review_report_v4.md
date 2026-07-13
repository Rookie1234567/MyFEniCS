# REVIEW REPORT V4：Task028 最终验收、轻量元数据加固与后续路线

## 1. 审查对象

```text
repository = Rookie1234567/MyFEniCS
branch = codex/20260712-task28-stage-consolidation
reviewed_head = bdfa7dc56de9b3cb0c7057d50ef65ebe25c8dfa2
base = master@0465b5f0e79046bcd82741d7396ba1c87f5a2606
review_chain = review_report_v1 -> response_v1 -> review_report_v2 -> response_v2 -> review_report_v3 -> response_v3 -> review_report_v4
```

本轮复核重点：

```text
- Response V3 对十五项 P0 和三项 P1 的回应；
- Case002 explicit / auxiliary 完整双求解；
- Case003 TM / TE complex absorption canonical records；
- demo / target preset 身份；
- PyCharm direct 与 MPI4 iterative 使用流程；
- Quick Start、Code Walkthrough、Theory 深度与准确性；
- case-contained Benchmark 合同；
- automatic checker、metadata、SHA reference 与 ordinary default；
- Task028 是否已经具备进入 master 的阶段版本质量。
```

Task026/Task027 已通过的 exact condensation、matrix-free condensed operator、physical-slab two-level PC 与 h=5/3/2 canonical 结果未被本轮否定。

---

# 2. 最终审查结论

```text
review_status = pass_with_minor_qualifications

Task026_Task027_core_solver = pass
existing_3d_canonical_results = pass
selective_integration = pass
ordinary_default = pass
repository_work_principles = pass
main_preset_dispatch = pass
main_demo_target_identity = pass
pycharm_direct_workflow = pass
pycharm_mpi4_workflow = pass
quick_start = pass
code_walkthrough = pass
code_walkthrough_accuracy = pass
theory_docs = pass
case_contained_benchmarks = pass
case002_explicit_auxiliary = pass
case003_lossy_tm_te = pass
benchmark_checker = pass
benchmark_metadata = pass_with_minor_hardening
environment = pass_with_qualification

heavy_3d_rerun_required = no
new_solver_research_required = no
master_merge = yes_after_minor_hardening_and_user_approval
```

准确结论是：

> Task028 已完成从 Task000–Task027 研究项目到可阅读、可运行、可审计阶段版本的收口。核心代码、主要数值证据、用户入口、理论、代码导览和 Benchmark 体系均达到合并标准。当前只剩三项不改变数值结果的 metadata/runner 加固；完成后，在用户明确许可下可合并 Task028 integration branch 到 master。

本报告不要求重跑 h=2 direct 或 iterative，不要求修改 Task27 预条件器，也不启动新的求解器研究。

---

# PART I：已正式接受的成果

## 3. 阶段整合与能力边界

以下内容通过：

```text
- Task000–Task027 的结构化进度、成功结果、失败路线和替代关系已经归档；
- Task26 exact condensation 与 Task27 successful physical-slab 路线被选择性抽取；
- sampled-Schur、cached-Q、failed spectral/GenEO/HPDDM 等路线没有被包装为 production；
- ordinary direct 默认未改变；
- MPI4 workstation iterative 仍为显式 opt-in；
- 工作原则在 README、docs 和自动测试中受保护。
```

Task028 integration branch 从 clean master 建立，因此最终允许合并的是 Task028 分支，而不是任何历史大型 research branch。

## 4. 3D direct / iterative 结果

现有 target 结果继续有效：

| h (nm) | FE DoF | iterative iterations | full true residual | peak total RSS |
|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,201 | `9.839e-7` | 约 1.99 GB |
| 3 | 198,438 | 993 | `9.933e-7` | 约 5.08 GB |
| 2 | 615,108 | 1,804 | `9.997e-7` | 约 13.08 GB |

```text
iteration ratio = 1804 / 993 = 1.8167 < 2
```

h=5/h=3 与 direct reference 的 official R/T/A 一致；h=2 direct 保留为已审查的 resource-heavy historical reference。

这些结果证明：

```text
- 同一冻结 target 离散系统可被准确求解；
- MPI4 workstation profile 在测试范围内满足工程 mesh-robust Gate；
- 不证明 R/T/A 已完成物理网格收敛；
- 不证明任意角度、波长、材料和几何都具有相同迭代性能。
```

## 5. Case002：2D explicit 与 auxiliary DtN

Case002 已完成同网格、同物理、同 RHS 的两次完整求解：

| 指标 | explicit | auxiliary |
|---|---:|---:|
| FE DoF | 139 | 139 |
| auxiliary DoF | 0 | 2 |
| matrix rows | 139 | 141 |
| matrix nnz | 727 | 673 |
| true residual | `2.168e-15` | `1.867e-15` |
| R | `4.77654763895058e-4` | `4.77654763895046e-4` |
| T | `0.9995223452361045` | `0.9995223452361033` |

```text
full FE field relative difference = 2.7711962846232144e-15
maximum absolute R/T/A difference = 1.2212453270876722e-15
```

该证据同时保护：

```text
matrix assembly
RHS
Floquet reduction
explicit low-rank DtN
auxiliary augmented DtN
FE solution
official modal power
lossless energy closure
```

Case002 可以作为 2D DtN 两种离散实现的 canonical lightweight algebra/physics reference。

## 6. Case003：2D TM/TE complex absorption

TM 与 TE 已形成独立 canonical records：

| 指标 | TM auxiliary DtN | TE scalar DtN |
|---|---:|---:|
| true residual | `3.323e-14` | `1.486e-15` |
| R | `3.6625e-6` | `8.7456e-5` |
| T | `0.8821724521` | `0.9903457798` |
| A_balance | `0.1178238854` | `0.0095667639` |
| A_volume | `0.1178238854` | `0.0095667639` |
| official closure | 机器精度 | 机器精度 |

接受以下 2D 有损端口修复：

```text
- complex beta 不再用 Im(beta)==0 判定传播；
- 用 Re(beta) 和 dispersion real part 区分有损传播阶与截止阶；
- 功率使用实际 port plane coefficient；
- phase-normalized reference-plane amplitude 只用于报告；
- probe 继续标记为 diagnostic_only；
- A_volume 使用 total field 并排除 PML。
```

该修复仅影响 2D lossy power 路径，没有改动 3D Task27 official RTA。

## 7. `main.py` 与 PyCharm

接受以下设计：

```text
- 无参数 Run 默认进入轻量 3D Stage1；
- 17 个 preset 全部通过真实 runner parser；
- `--list-presets --verbose` 显示 geometry/discretization/resource/status；
- demo 与 target Stage4 名称严格分开；
- target h5/h3 direct preset 复用唯一 target_stage4_config；
- ordinary main 不静默启动 MPI4 iterative；
- MPI4 使用 PyCharm External Tool 或显式 MPI wrapper。
```

接受的 target preset：

```text
3d_target_grating_direct_h5
3d_target_grating_direct_h3
```

接受的 demo/fallback preset：

```text
3d_stage4b_demo_direct_h5
3d_stage4b_demo_direct_h3
3d_stage4b_demo_mumps_ooc
3d_stage4b_demo_mumps_blr
```

## 8. 文档体系

以下五层职责划分通过：

| 层 | 职责 |
|---|---|
| Capability / Development Progress | 项目具备什么、开发到哪里 |
| Quick Start | 用户如何在 PyCharm/CLI 中运行和修改参数 |
| Code Walkthrough | 代码对象、调用链、尺寸、ownership、公式映射 |
| Theory | 数学和物理推导 |
| Benchmark | 哪个冻结问题证明什么能力 |

Quick Start、Walkthrough 和 Theory 已不再是文件名列表或命令摘要；当前深度足以让用户沿文档进入源码和结果字段。

已发现的 Walkthrough 错误均已修正：

```text
- SparseCoarseVector 无 global_size 字段；
- two-level apply 是 smoother -> residual -> coarse -> optional post-smooth；
- SmallDenseInverse 当前使用 np.linalg.inv；
- explicit PETSc condensation 当前仅验证 H=I；
- 非单位 H 会抛 NotImplementedError；
- 3D DtN 已从 mode 追踪到 C/D/H、RHS、aux amplitude 与 official R/T。
```

## 9. Benchmark 体系

13 个编号 case 均具备明确合同：

```text
README
config/fixture
expected
run/test command
records（若属于 recorded case）
status / limitations
```

Recorded cases：

```text
002 2D explicit/auxiliary DtN
003 2D TM/TE complex absorption
010 3D Stage1
021 3D target direct
031 3D workstation iterative
```

Test-backed / experimental cases保持诚实身份，特别是：

```text
Stage2B PML = experimental accuracy
Stage2C Fresnel = experimental accuracy
MUMPS OOC/BLR = experimental direct fallback
```

## 10. 自动验证

接受当前自动验证体系：

```text
compileall
Ruff check/format
full src/test
MPI4 condensation/PC tests
documentation contract
preset/parser contract
benchmark checker
SHA-pinned case references
local Markdown links
git diff --check
```

Response V3 报告：

```text
115 passed, 10 skipped
MPI4: each rank 14 passed
documentation contract: 11 passed
benchmark checker: 143/143 passed
```

跳过项属于既有环境/可选后端条件，不等于测试失败。

---

# PART II：合并前的三项轻量加固

## 11. M1：Canonical lightweight record 必须验证 tracked source clean

当前 Case002/003 records 同时记录：

```text
git_dirty = true
tracked_source_dirty = false
```

这是允许的：ignored benchmark artifact 会令工作区整体 dirty，但受 Git 跟踪的源码仍然可以是 clean。

Checker 应为 provenance：

```text
canonical_lightweight_rerun_from_frozen_case_contract
```

增加强制 Gate：

```text
metadata.tracked_source_dirty == false
```

目的：禁止在尚未提交的源码修改上生成 canonical record，同时允许 ignored artifacts 存在。

## 12. M2：Candidate runner 不得默认伪造 image digest

当前 Case002/003 `run.sh` 允许默认：

```text
IMAGE_DIGEST=sha256:qualified-local-image
```

由于默认输出为 ignored candidate records，它没有污染现有 canonical records，但环境身份不应使用占位 digest。

应改为：

```sh
: "${IMAGE_DIGEST:?Set IMAGE_DIGEST to the tested image digest}"
```

`SOURCE_COMMIT` 已经强制提供，`IMAGE_DIGEST` 应采用同样规则。

## 13. M3：在最终响应提交后重新运行 clean checker

当前保存的 Gate report 对应 Response V3 source commit，且报告生成本身会使 checkout dirty。完成 M1/M2 后，Codex 应在最终提交状态执行：

```text
python benchmarks/check_benchmarks.py --no-write
python -m unittest src.test.test_26_documentation_contract
python -m unittest src.test.test_27_main_preset_contract
```

并在 `response_v4.md` 中记录：

```text
final HEAD
checker passed_count / total_count
tracked source clean
no canonical record overwritten
no h2 rerun
```

无需刷新或覆盖 Case002/003/3D canonical records，除非数值代码又被修改。

---

# PART III：Response V4 要求

## 14. 回应文件

Codex 应继续在同一 Task28 分支提交：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/response_v4.md
```

## 15. Response V4 只需回应三项

```text
M1 tracked_source_dirty Gate
M2 required IMAGE_DIGEST
M3 final-head lightweight validation
```

每项写明：

```text
files changed
exact behavior
command/test
evidence
remaining limitation
```

禁止借本轮继续新增物理功能、求解器 profile 或重型 benchmark。

---

# PART IV：合并建议

## 16. Task028 合并结论

完成 M1–M3 后：

```text
Task028 practical integration objective = ACCEPTED
Task028 documentation objective = ACCEPTED
Task028 benchmark objective = ACCEPTED
Task028 master merge = APPROVED WITH ENVIRONMENT QUALIFICATION
```

仍需用户明确许可后才执行 merge。

允许合并的是：

```text
codex/20260712-task28-stage-consolidation
```

不允许直接合并：

```text
Task021–Task027 historical research branches
failed sampled-Schur / cached-Q / spectral / HPDDM runners
raw runs
mesh/VTU/HDF5/cache/OOC factors
```

建议通过普通 PR merge/merge commit 保留 Task028 的审查与响应历史。若选择 squash，也必须确保所有 task/review/response/outcomes 文档仍进入 master。

## 17. 合并后阶段检查

在 master 上执行轻量 release check：

```text
compileall
full unit tests（条件允许时）
MPI focused suite
benchmark checker --no-write
README / Quick Start link check
ordinary default Stage1 smoke
```

随后可考虑创建阶段 tag，例如：

```text
stage4-workstation-v1
```

Tag 只代表：

```text
- 当前文档化和 benchmark 化的阶段能力；
- 冻结 target 的 direct/iterative reference；
- 不代表物理网格已完全收敛；
- 不代表参数空间普适。
```

---

# PART V：下一阶段建议

## 18. 下一步不应立即继续新预条件器研究

当前最重要的未解决问题不是“离散系统能否被求解”，而是：

```text
R/T/A 是否已经随空间离散收敛到可信物理解。
```

现有 h=5、h=3、h=2 虽然各自残差和能量闭合很好，但 R，特别是小反射率，随网格仍变化明显。

因此下一项任务建议不是继续 spectral/GenEO，也不是盲目跑 h=1.5，而是物理收敛与 reference qualification。

## 19. 推荐 Task029

建议名称：

```text
Task029: 3D target grating physical convergence and reference qualification
```

中文：

```text
Task029：3D 目标周期光栅的物理网格收敛与参考解资格化
```

### 19.1 核心目标

```text
1. 区分“线性系统求解准确”与“物理离散收敛”；
2. 为 R/T/A、near field 和主要衍射级建立可信 reference；
3. 判断当前误差主要来自 h、p、局部尖角/界面还是端口截断；
4. 给出工程使用所需的误差范围和推荐网格；
5. 为后续反演和参数扫描建立可信 forward baseline。
```

### 19.2 建议工作包

#### A. 冻结物理问题

继续使用当前 canonical target：

```text
period = 50 x 25 nm
block = 17 x 25 x 120 nm
cell height = 140 nm
lambda = 13.5 nm
theta = 80 deg
phi = 0 deg
s polarization
complex Si
p = 2
Floquet + auxiliary DtN
```

本任务原则上不改变物理模型和 solver profile。

#### B. 整理现有 h5/h3/h2 数据

统一比较：

```text
R_total
T_total
A_volume
per-order R_m/T_m
near-field integrals
selected field probes
energy closure
full residual
DoF / time / RSS
```

不能只比较总能量闭合。

#### C. 设计更细参考但先做资源 preflight

候选路线按优先级：

```text
1. local_refined / boundary-fitted mesh，在材料界面、光栅边缘和高场区域加密；
2. p-order comparison（在可比网格上）；
3. h=1.5 只在资源预估和分区加密仍不足时考虑；
4. 不直接在 14 GB 环境盲跑全局 uniform h=1.5。
```

#### D. 可信外部交叉验证

至少选择一种独立路径：

```text
COMSOL periodic-port model
RCWA（适用于该规则结构时）
更高资源 direct reference
解析/半解析 flat-layer 或 zero-contrast 子问题
```

外部模型必须严格统一：

```text
geometry
material convention
angle definition
polarization
port plane
R/T normalization
loss convention
```

#### E. 建立 convergence Gate

在 Task029 任务书中预先定义，而不是结果出来后再选阈值：

```text
- 每个离散系统 full true residual 通过；
- R/T/A 与 reference 的绝对/相对差；
- 主要衍射级差异；
- near-field quantity 差异；
- 能量闭合；
- 网格序列趋势是否稳定；
- resource envelope。
```

具体数值阈值应根据工程反演所需精度与 R 的量级决定，不能仅沿用 `R+T+A≈1`。

### 19.3 Task029 不应做的事

```text
- 不重新扫描 failed spectral coarse；
- 不在物理误差不清楚时扩大角度/波长参数扫描；
- 不把新的局部加密结果直接覆盖 Task28 canonical solver records；
- 不修改 ordinary default；
- 不把 h=1.5 成功与否当作唯一收敛判断。
```

## 20. Task029 之后的路线

### Task030：参数鲁棒性与 production qualification

物理 reference 建立后，再检查：

```text
angles: 75 / 80 / 85 deg
wavelength around 13.5 nm
material loss perturbations
near-Rayleigh cases
selected geometry perturbations
```

建议先 h=3 筛选，再用已资格化参考网格确认关键点。

### Task031：参数扫描吞吐量与复用

在物理可信度确定后优化：

```text
warm start
coarse basis reuse
factor/cache lifecycle reuse
parameter continuation
parallel case scheduling
record/candidate separation
```

### 更长期：真正多层 H(curl) 可扩展求解器

只有当更细网格或更大几何再次成为主要阻塞时，再研究：

```text
low-order refined H(curl) multigrid
multilevel physical Schwarz
parallel slab local solves
strong-scaling replacement for owner-computes sequential ILU
```

这属于后续研究任务，不应阻塞 Task028 合并。

---

# 21. 最终决定

```text
Task028 core code = ACCEPTED
Task028 documentation = ACCEPTED
Task028 benchmark suite = ACCEPTED
Task028 2D lossy fix = ACCEPTED
Task028 existing 3D results = ACCEPTED
Task028 environment = ACCEPTED WITH QUALIFICATION
Task028 remaining work = THREE MINOR METADATA/RUNNER HARDENING ITEMS
Task028 heavy rerun required = NO
Task028 may merge after response_v4 and user approval = YES

Recommended next task = Task029 physical convergence and reference qualification
```
