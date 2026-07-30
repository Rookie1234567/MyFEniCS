# Task036 Review Report V1：前向求解器缺陷修补与 Hybrid-P 有界完善方案

## 1. 审阅身份与结论

```text
reviewed_branch = codex/20260730-task36-forward-solver-bugfix-hardening
base_master = 007298261681014efbe6508ac91c6c3ae9a6a44a
reviewed_branch_head_before_report = 98f74a6cdd8181b778d9add36d088058300eac1b
numerical_fix_sha_1 = 393b7c583c40bea17d4ceca6440c140317e0b60c
numerical_fix_sha_2 = 9de46581fa47ea02295d73688d30a55a38c01a91
numerical_fix_sha_3 = bb0e5e3e385586e137d861cf0a53a142e4fe0fe0
review_status = CORE_BUGFIXES_APPROVED_WITH_BLOCKERS_AND_BOUNDED_HYBRID_P_FOLLOWUP
merge_to_master = not_authorized_by_this_review
ordinary_default = unchanged
```

Task036 已经修复了多项真实 correctness / semantics bug，尤其是：

- DtN 直接模态投影的 P 偏振三分量/切向分母不一致；
- reciprocal trace 的真实 degree、surface quadrature 与 canonical identity 不一致；
- sampled traction proxy 与 exact variational conormal dual 混名；
- propagation / traction / reconstruction beta 静默混用；
- Ny=3 的离散 trace alias 未在 solve 前识别；
- MUMPS factor NNZ 的 int32 overflow；
- solver/factor 生命周期与 field output 重叠；
- 内存、MPI identity 和 DoF/row 口径混淆。

这些修复具有明确失败证据、数学依据和代表性 PDE 回归，核心方向正确。

但是，Task036 目前不能写成“全部完成并可直接合并”：

1. `test_summary.md` 仍把 full-repository pytest 记录为
   `IN_PROGRESS_PENDING_FINAL_TRACEBACK`，并在约 72% 时观察到 1 个 failure 标记；
2. Hybrid-P 只完成了正确分类和 fail-closed，尚未完成数值资格化；
3. 通用 near-degenerate block continuation 仍未解决；
4. 本分支若干 runner / telemetry 改动规模明显超过原始“最小 bugfix”，不能整体 merge；
5. 当前 `_hybrid_p_disposition(...)` 调用处把
   `modal_rank_sufficient=False` 固定写死，因此即使未来某个 P 点已经完成 M 收敛，也永远不会被判为 rank-qualified。

本审阅建议：先完成 full-suite traceback 与最小修正；随后允许一个严格时间盒、无新框架的 Hybrid-P 有界完善批次。禁止再扩建 campaign、schema、状态机或大规模防御性代码。

---

## 2. 各 bug 的审阅处置

| ID | Task036 结果 | 审阅结论 | 后续处置 |
|---|---|---|---|
| B01 DtN tangential projection | `FIXED` | **批准**。这是明确 correctness bug；P 的假 discrepancy 已消除 | 保留核心 helper、解析测试和实际 P 回归 |
| B02 high-order reciprocal trace | `FIXED` | **部分批准**。真实 degree / quadrature / canonical relation 应保留；analytic reciprocal basis 仍是 research-only | 核心修复可留；显式 opt-in reciprocal basis 不自动提升 production |
| B03 exact traction dual | `FIXED` | **批准**。formal dual 与 sampled proxy 分离是必须的 | 保留，旧兼容必须继续绑定冻结 SHA |
| B04 beta semantics | `FIXED` | **批准**。E 与 H 的 beta 身份不应静默混用 | 保留 paired traction-beta 输入和 provenance |
| B05 Hybrid-P disposition | `FAIL_CLOSED` | **分类修复批准，功能未完成** | 进入第 6 节的有界 Hybrid-P 补充研究 |
| B06 near-degenerate blocks | bounded repair negative | **检测批准；one-shot repair 仅 research-only** | 可做一次小型 connected-component 扩展；禁止新 continuation framework |
| B07 Ny trace alias | `FIXED` | **批准**。真实 MPC trace overlap preflight 有明确物理依据 | 保持显式 y-invariant/n0 opt-in，不改变 general diffraction 默认 |
| B08 MUMPS NNZ overflow | `FIXED` | **批准** | 保留 raw 与 corrected 两套值，consumer 只用 corrected 值做比率 |
| B09 solver lifecycle | `FIXED` | **批准** | 保留幂等 destroy 和 release-before-field-output；不把释放量写成结构压缩 |
| B10 memory/MPI semantics | `FIXED` | **批准** | 同步 sampler 与 historical upper bound 继续分开 |
| B11 DoF/row semantics | `FIXED` | **批准** | active/carrier/trace/augmented 四类口径继续分开 |

---

## 3. 必须先补齐的审阅阻塞项

### 3.1 full-repository pytest 尚未闭合

当前 `test_summary.md` 明确写明 full suite 尚未结束，并且运行中已出现 1 个 failure
标记。Task036 不能在 failure 身份未知时写成最终通过。

要求：

1. 只读取并收口已经启动的同一 full-suite 运行；
2. 保存最终计数和完整 traceback；
3. 若 failure 来自 Task036 修改，做最小修复并只重跑失败测试及必要邻接测试；
4. 若 failure 是环境/ignored artifact 污染，必须用 clean worktree 复现证明；
5. 不得因为文档提交重新运行 PDE；
6. full suite 未通过前，不授权 master integration。

### 3.2 Hybrid-P rank 状态被固定为 false

`benchmarks/run_task032_phase6_augmented.py` 当前调用：

```python
modal_rank_sufficient=False
modal_rank_evidence="not_qualified_no_M_convergence_funnel_in_this_runner"
```

这是安全的 quarantine 实现，但它不是最终功能。它意味着当前代码没有真实的
Hybrid-P modal-rank 判定，也无法在任何 P 点上获得资格化结果。

后续不得继续增加更多状态字段；应直接补一个小型、数值驱动的 M-convergence 判定，见第 6 节。

### 3.3 Task036 改动规模超出“最小 bugfix”预期

与 master 比较，本分支对 `run_task032_phase6_augmented.py`、
`mode_classification.py`、`dtn_port_3d.py` 和 watchdog 增加了较多 task-specific
逻辑。多数逻辑有测试，但不适合整分支直接合并。

后续 integration review 应按“通用 numerical core / task-local runner / research-only
experiment”三层拆分。禁止整体 merge 或整体 cherry-pick。

---

## 4. 建议保留与暂不提升的代码

### 4.1 建议保留的通用 numerical core

以下能力有明确 correctness 价值：

- `src/solvers/dtn_port_3d.py`
  - tangential-only direct mode projection；
  - consistent incident subtraction；
  - MUMPS/Full3D 不相关的通用 P 投影测试；
  - y-invariant trace-overlap helper（保持 opt-in）。
- `src/solvers/hybrid_fem_modal_augmented_direct.py`
  - exact variational conormal dual；
  - sampled proxy 语义隔离；
  - 幂等 solver/system release。
- `src/postprocessing/hybrid_field_reconstruction.py`
  - propagation beta 与 traction/reconstruction beta 显式分离。
- `src/solvers/common_3d_solve.py`
  - MUMPS factor NNZ 的 64-bit-safe interpretation。
- `src/solvers/common_3d_utils.py` / `common_3d_case_flow.py`
  - 生命周期和内存 authority 语义修正。
- static-condensation / resource consumers
  - corrected factor count 和 active/carrier/row semantics。

### 4.2 条件保留、不得直接提升 production 的能力

- analytic scalar-stage4 reciprocal negative basis；
- one-shot near-degenerate joint-left-inverse repair；
- Task036 专用 alias / projection / reference-binding CLI；
- 大段 benchmark record/rendering 逻辑；
- Hybrid-P disposition classifier。

其中 detector、audit 和 fail-closed 可以保留；数值 repair 必须在第 6 节的有限矩阵上
通过后再决定是否抽取成通用 helper。

### 4.3 不应因 Task036 整体进入 master 的内容

- `.codex/environments/environment.toml`；
- Task036 本地 artifact 路径、一次性命令和大段 record renderer；
- 只服务单个历史案例的 defensive wrapper；
- surrogate/dataset/campaign 代码；
- 未资格化的 automatic Hybrid-P routing；
- 任何把 Full3D fallback 写成 Hybrid success 的逻辑。

---

## 5. Hybrid-P 现在到底还能不能做

### 5.1 物理和数学上：可以

现有证据不支持“Hybrid 方法天生不能处理 P 偏振”：

- F2–F5 的 Full3D-P residual 和能量均通过，说明 P 物理解存在；
- Task036 修正后的 direct tangential projection 在 F2/F5 P 点达到约
  `1e-11`–`1e-14`；
- exact traction dual 在 P 点约为 `1e-13`；
- propagation / traction / H-reconstruction beta 已显式统一。

这些结果说明 external DtN、Full3D P、端口切向投影和 selected-mode algebraic
traction coupling并没有根本性错误。

### 5.2 当前工程实现：尚不可用作 production

当前主要问题有两层：

1. **modal-space capacity**：M120 对 P 的切向/interface trace 明显不足；历史低掠射
   P 需要接近 M576 才把 interface-E 降到 `O(1e-8)`；
2. **whole-domain closure**：历史高 M 下 energy closure 仍未通过，而这些高-M
   结果是在本轮 tangential projection、exact dual 和 beta semantics 修复之前获得的，
   因此不能直接当作最终否定，也不能直接当作已修复。

低掠射 P 往往需要大量 evanescent/internal modes，Hybrid 的降维优势可能很小。
所以应区分：

```text
functional correctness
```

与：

```text
useful reduced-order production route
```

如果只在接近完整 trace rank 时通过，Hybrid-P 可以被证明“数值上可工作”，但不应
被宣传为低成本生产方法；此时 production 应继续使用 Full3D-P。

---

## 6. 批准的 Hybrid-P 有界完善批次

本批次允许适当开发，但必须保持小而直接。目标不是建立新架构，而是用修正后的代码
回答：P 在哪些角度和 M 范围内可准确工作，以及剩余 blocker 是 rank、近简并还是
energy ledger。

### 6.1 硬边界

```text
new package/framework/state machine = forbidden
new campaign/schema/receipt/watchdog = forbidden
surrogate/inversion/iterative/hp = out_of_scope
ordinary default change = forbidden
new production auto-router = forbidden
maximum new task-local helper files = 1
recommended net new numerical code <= 250 lines
maximum representative P points = 2
maximum new heavy Hybrid PDE = 8
one heavy PDE at a time
```

不得为了填满数量运行无判别价值的模型。

### 6.2 两个固定 P 点

只使用已经有 same-p Full3D authority 的：

```text
P-low  = F2: grazing 0.5°, azimuth 0°,  P
P-high = F5: grazing 10°,  azimuth 90°, P
```

后端优先 static；只在一个点做一次 standard/static equivalence，不做全矩阵重复。

### 6.3 M 收敛漏斗

对每个点按顺序使用：

```text
M = 120 -> 240 -> 384/480 -> maximum finite/full trace rank
```

若某一级已经满足全部 Gate，停止该点后续 M。若资源 preflight 明确超过 Full3D 且没有
信息增益，也停止。

每个 M 只记录现有量：

- interface-E algebraic residual；
- exact traction dual；
- true residual；
- global biorthogonality row norm / max cross-block overlap；
- R/T/A 与同阶 Full3D 的差；
- `A_balance`、`A_volume` 和 whole-domain energy closure；
- bottom/top local ledger、middle modal loss、external port power；
- wall time、rows、matrix/factor、同步内存（已有 sampler 时）。

禁止新增大型 evidence wrapper。

### 6.4 用实际收敛替换 hard-coded rank false

只增加一个小型纯函数，根据同一点相邻 M 结果判定：

```text
modal_rank_sufficient =
    interface_E <= 1e-8
    and exact_traction_dual <= 1e-8
    and max(|Delta R|, |Delta T|, |Delta A|)_M_to_next <= 1e-4
    and global_biorthogonality_row_norm <= 1e-6
```

最后一个 M 若没有 next 值，只能在达到 maximum finite/full trace rank、并与 Full3D
直接比较时判定。不得用“requested M 很大”或“selected mode count 达标”替代收敛证据。

这会替换当前固定的 `modal_rank_sufficient=False`，但不会自动令
`hybrid_p_production_qualified=true`；energy 与 same-p Full3D Gate仍必须通过。

### 6.5 near-degenerate block 的唯一允许小改动

当前一次 repair 后，worst component 会移动到另一对相邻 blocks。允许把现有
“只修最坏一对”改为：

1. 基于 beta distance、方向和 cross-overlap 建立 group graph；
2. 只合并互不重叠的 connected components；
3. 每个 component 大小不超过 8；
4. 仅 joint-normalize left basis，right modes 和 beta 不变；
5. 每个 component 只处理一次；
6. condition 超限或最终完整 row norm 仍大于 `1e-6`，立即 fail closed。

不得开发 mode continuation、跨角度跟踪框架或新 QEP solver。实现优先复用现有
`_joint_left_basis_inverse`，净新增应很小。

### 6.6 若 energy 仍失败，只允许一次定向 ledger 检查

若某点已经满足：

```text
interface E pass
exact traction dual pass
biorthogonality pass
R/T close to Full3D
```

但 whole-domain energy 仍失败，则只做一次现有 ledger 的逐项对照：

```text
bottom local FEM flux/loss
+ middle modal Poynting loss / volume loss
+ top local FEM flux/loss
+ external R/T
```

只在发现明确 sign、phase-location、double-counting 或 omitted-region bug 时修改代码。
若所有局部 identity 自洽、剩余误差来自 modal truncation或近完整 rank conditioning，
停止，不得再新增能量“修正项”。

---

## 7. Hybrid-P 验收与最终分类

### 7.1 数值正确性 Gate

每个资格化点必须同时满足：

```text
true relative residual <= 1e-9
interface E residual <= 1e-8
exact traction dual <= 1e-8
full biorthogonality row norm <= 1e-6
direct tangential projection difference <= 1e-10
abs(R + T + A_volume - 1) <= 1e-5
same-p Full3D max(|Delta R|, |Delta T|, |Delta A|) <= 1e-4
zero swap
```

### 7.2 功能分类

#### A. `HYBRID_P_BOUNDED_SCOPE_PASS`

两个固定点均通过，且至少 high-grazing 点在明显少于 full trace rank 时通过。可以在
显式 opt-in 的 bounded scope 中开放 Hybrid-P；ordinary default 仍不改变。

#### B. `HYBRID_P_FUNCTIONAL_BUT_NO_REDUCTION_ADVANTAGE`

只有接近 full trace rank 才通过，且资源/时间不优于 Full3D。说明 Hybrid-P 数值实现可
工作，但 production 继续路由 Full3D-P。

#### C. `HYBRID_P_LOW_GRAZING_DEFERRED`

high-grazing P 通过，low-grazing P 只有近 full rank 或仍失败。允许限定高掠射 P scope；
低掠射继续 Full3D fallback，并明确不是 Hybrid success。

#### D. `HYBRID_P_ARCHITECTURE_REQUIRED`

在 maximum finite/full trace rank、bounded component normalization和修正后的 beta/dual
语义下仍不能闭合。此时停止 Task036，不再调 M、Gate 或 energy公式。

---

## 8. 最终审阅要求

Codex 下一轮只能：

1. 收口当前 full-suite traceback；
2. 修复确证的测试回归；
3. 执行第 6 节 Hybrid-P bounded follow-up；
4. 更新 `fix_report.md`、`test_summary.md` 和本 review 的 disposition；
5. 推送同一 Task036 分支并停止。

禁止：

- 创建新框架或大段 defensive code；
- 扩展到连续角域或几何 campaign；
- 自动提高所有 P case 的 M；
- 把 Full3D fallback 写成 Hybrid pass；
- 放宽 `1e-6 / 1e-8 / 1e-5` Gate；
- 在本审阅后自行 merge master。

当前结论：**Task036 的通用 bugfix 核心大部分有效，但 full-suite 尚未闭合；Hybrid-P
不是物理上不可行，而是尚缺一个小型 M-convergence + bounded near-degenerate
component normalization 的资格化步骤。允许适当完善，但必须严格限定为上述两个 P 点和
既有数值路径。**
