# REVIEW REPORT V2：Task032 最终复审与选择性合并结论

## 0. 最终状态

```text
review = Task032 review_report_v2
branch = codex/20260714-task32-hybrid-fem-modal-direct-baseline
reviewed_head = 71e3b3047a5a5363f59f420a75a562c2fcf18283
base_master = dae03170b0cdd87f2d72769aea7ce04e32acce2b
review_status = PASS_WITH_QUALIFICATIONS
physical_numerical_result = PASS
13p5nm_classification = hybrid_direct_engineering_success
h2 = not_run_by_gate / accepted
current_direct_0p7nm = not_resource_feasible / accepted
future_hybrid_architecture = retained
ordinary_default_changed = false
formal_h5_h3_rerun = not_required
selective_merge_to_master = APPROVED
whole_research_branch_merge = NOT_RECOMMENDED
Task033_start = APPROVED_AFTER_SELECTIVE_MERGE
```

Task032 Review V1 与 Addendum 的 P0 项已经实质关闭。没有发现新的物理公式错误、接口符号错误、矩阵装配错误、official R/T/A 资格错误或对象生命周期回归。

最终结论是：

1. 当前 13.5 nm、规则 Case080、h5/h3、M160 的 Hybrid FEM–Modal 实现通过；
2. h2 因两套预测均未通过 4/5 GiB Gate 而不运行，属于正确的 fail-closed 决策；
3. 当前 direct Hybrid 不可直接放大到 0.7 nm；
4. 未来仍保留“上下复杂三维 Nédélec FEM + 中间通用 `epsilon(x,y)` 模态区”；
5. 本分支可按 `selective_merge_manifest.csv` 选择性合入 master；
6. ordinary default 不改变。

---

# 1. 本轮复审范围

复审覆盖：

- `response_v1_review_followup.md`；
- 重写后的 table-first `outcomes/summary.md`；
- `task032_0p7nm_scalability_assessment.md`；
- 确定性 non-PDE projection 脚本、JSON 与 test41；
- `selective_merge_manifest.csv`；
- compact record size inventory；
- 仓库工作原则、阶段回顾标准与保护测试；
- capability、roadmap、development progress、Case080 和 benchmark 索引；
- Review 后 Python 改动的身份；
- 最新测试与 checker 记录；
- 分支相对 master 的 Git 状态。

当前分支相对 master 为 pure ahead：

```text
ahead_by = 27
behind_by = 0
```

Review Addendum 之后只有一个收口提交。核心 Hybrid 物理求解代码没有行为性修改；四个核心模块只增加 current-scale / 0.7 nm scalability warning docstring。新增可执行行为仅为 `run_task032_scalability_projection.py` 及其确定性测试。

---

# 2. Review V1 / Addendum 关闭情况

| P0 | 要求 | 复审结果 | 状态 |
|---|---|---|---|
| A | summary 以表格为主重新组织 | 16 节结构，关键数据均进入独立表格 | closed |
| B | table-first 规则写入长期治理并测试 | 三个 protected files、standard、tests 已同步 | closed |
| C | 0.7 nm scalability assessment | measured / derived / predicted / not_run 已区分 | closed |
| D | 确定性资源投影脚本和 JSON | non-PDE、非 solver pass、输入 fail-closed | closed |
| E | 选择性合并清单 | 代码、证据、warning、heavy exclusion 已分类 | closed |
| F | compact record 大小审计 | 22 JSON，总约 1.34 MiB，最大约 0.27 MiB | closed |
| G | 项目文档/API 边界同步 | README、capability、roadmap、benchmark 等已同步 | closed |
| H/I | Addendum 覆盖 y-invariant / pure-modal-first | 已明确撤回 mandatory 主线 | closed |
| J | 明确 M 的定义 | M=每方向保留内部截面模；M160=320 amplitudes | closed |
| K | full3D/Hybrid DoF、rows、NNZ 对照 | h5/h3 表格完整 | closed |
| L | 1 TiB DoF 与 bytes/DoF 预算 | 设计区间和非实测身份明确 | closed |
| M | 保留上下复杂 3D FEM | 已成为未来架构硬边界 | closed |
| N | Task033–036 路线同步 | 主线已改为 h/p→modal core→iterative→continuation | closed_with_qualification |

---

# 3. Table-first summary 验收

重写后的 summary 已达到长期回顾要求，包含：

| 表组 | 验收内容 |
|---|---|
| 最终状态和范围 | classification、review、h2、smoke、ordinary default |
| 记号 | M、2M、external auxiliary、local height |
| Phase 0–10 | planned / run / pass / not_run |
| QEP/modes | beta error、残差、双正交、tracking |
| 系统规模 | cells、FE DoF、QEP DoF、rows、NNZ、factor、projection |
| 数值结果 | R/T/A、full residual、接口/平面场、closure |
| 截断漏斗 | M20/40/80/120/160 |
| 内存时间 | augmented / Schur fast / Schur minimal |
| h2 | 两类预测和 not_run |
| parameter smoke | 证明与不证明 |
| 负结果 | 根因、修复、停止边界 |
| 0.7 nm | 实测基线、解析外推、设计预算 |
| records | 数量、大小、heavy exclusion |
| merge | merge / warning / do_not_merge |
| next | Task033–036 与 Gate |

数据身份、单位、baseline 和证据入口均有说明。该 summary 可以成为 Task032 的长期 canonical technical archive。

长期治理条款也已同步为强制要求，并由测试检查 protected files 的一致性。该项接受。

---

# 4. 物理与代数结果最终接受

## 4.1 系统规模

| mesh | 方法 | total rows | assembled NNZ | rows reduction | NNZ reduction |
|---|---|---:|---:|---:|---:|
| h5 | full3D | 44,778 | 4,896,156 | baseline | baseline |
| h5 | Hybrid M160 | 14,052 | 2,000,624 | 68.62% | 59.14% |
| h3 | full3D | 198,518 | 21,317,860 | baseline | baseline |
| h3 | Hybrid M160 | 68,796 | 8,594,673 | 65.35% | 59.68% |

该表准确区分：

- full3D Nédélec DoF；
- 每侧 local FE DoF；
- 外部 80 个 Fourier-DtN unknown；
- 内部 `2M=320` 个 modal amplitudes；
- total matrix rows。

Task032 已经产生真实的代数规模下降，而不是仅在概念上缩短计算域。

## 4.2 h3 主结果

| 指标 | Hybrid h3/M160 | full3D 对照 / Gate |
|---|---:|---|
| true residual | `2.6036e-12` | pass |
| R | `0.0046128199040` | official |
| T | `0.5836509402052` | official |
| A | `0.4117362398908` | official volume/balance |
| max `|ΔR/T/A|` | `2.63e-6` | `<1e-5` |
| interface E error | `2.50e-8` | pass |
| interface H error | `4.82e-4` | pass |
| max selected-plane E/H error | `9.96e-5 / 7.80e-4` | pass |
| volume closure | `3.27e-12` | pass |

M120→M160 的 R/T/A 与显著复振幅变化进入强平台；M20→M40 未达到强终点的负证据继续保留。当前单点的 M160 截断结论接受。

## 4.3 不能扩张的声明

继续禁止把当前结果写成：

- h5/h3 连续网格收敛；
- 1–10° S/P production qualification；
- h2 实测成功；
- 当前 direct solver 的 0.7 nm 可行性；
- mesh-independent 或参数无条件鲁棒性。

---

# 5. 内存、h2 与 0.7 nm 报告验收

## 5.1 当前 direct 内存

| h3 path | simultaneous worker RSS | 相对 augmented |
|---|---:|---:|
| augmented | 3.8526 GiB | baseline |
| Schur fast | 3.9983 GiB | +3.78% |
| Schur memory-minimal | 3.2244 GiB | -16.31% |

准确结论仍是：

```text
Schur algebra alone != lower memory
sequential factor lifecycle = measured h3 memory benefit
```

当前峰值来自 local LU factor 与 all-mode dense multi-RHS，而不是 320×320 modal Schur 本体。

## 5.2 h2

两类预测均未通过启动 Gate，故：

```text
h2 = not_run_by_gate
```

该决定接受，不要求补跑。

## 5.3 0.7 nm analytical projection

投影脚本正确地把输出标记为：

```text
record_type = analytical_resource_projection
is_pde_run = false
is_solver_pass = false
```

脚本的功能是反证“当前显式对象布局机械放大”不可行，不是预测未来优化实现的真实 RSS。报告也明确说明：

- generic mode count 只是传播模几何下界；
- 3.7 倍只是 risk illustration，不是 converged M；
- uniform h0.1 rows 不是 adaptive mesh 预测；
- 1,595.60 TiB 是 all-mode RHS 单对象机械 payload proxy；
- cumulative volume 不是同时峰值；
- factors、mesh、Krylov 和材料色散未计入。

这些限定足够明确，没有将解析外推包装成 solver pass。

---

# 6. 唯一保留资格：Task033 的压缩目标

最新讨论已经进一步明确：Task033 的 `3x` 不应被解释为“固定 p2 h-adaptivity 的最低通过线”，也不应在尚未运行任何自适应实验前成为非黑即白的任务失败条件。

更合理的长期判定是：

| 同误差 local DoF 压缩 | 建议身份 |
|---:|---|
| `<1.3x` | weak signal |
| `1.3–2x` | useful engineering positive |
| `2–3x` | clear success |
| `>=3x` | engineering target |
| `>=5x` | strong / preferred target |

其中：

```text
p2 h-adaptive alone: 3x is stretch
h + p3/hp zoning + interface budget: 3x engineering target
5x: strong target, not promised outcome
```

当前 response、summary、assessment 和 roadmap 仍把 `>=3x` 写成硬 Gate。该措辞需要在正式 Task033 task.md 中被上述分级规则取代。

这不是 Task032 的代码或证据 bug，也不影响 Task032 的物理/数值验收，因此不阻塞本次选择性合并。Task033 任务书必须以本 Review V2 为准，不得机械继承旧的“<3x 即停止全部 h/p 路线”措辞。

---

# 7. 选择性合并决定

`selective_merge_manifest.csv` 已覆盖主要文件和模块身份。批准从 clean master 按清单选择性合并：

## 7.1 批准的基础设施

- mixed cross-section spaces；
- double-Floquet sparse reduction；
- generic QEP infrastructure；
- mode classification、adjoint QEP、biorthogonality 和 tracking；
- stable two-sided propagation；
- matched modal trace projection；
- hybrid local mesh 与 one-sided local DtN；
- physical E/H、absorption 和 field reconstruction；
- full3D reference exporter；
- memory sampler 和 benchmark gates。

## 7.2 批准作为 current-scale reference

- augmented Hybrid direct；
- fast / memory-minimal Modal-Schur direct；
- Case080 h5/h3 M120/M160 records；
- 现有 current-scale QEP/Schur runner。

必须保留 warning：

```text
not 0.7 nm production scalable
explicit opt-in
ordinary default unchanged
```

## 7.3 不得提升

- last-rank modal ownership；
- replicated dense M² arrays；
- all-mode `Nlocal x (2M+1)` dense RHS；
- all-modes MUMPS shift-invert QEP；
- local direct LU 作为 0.7 nm 主线；
- parameter smoke 作为 production qualification。

## 7.4 不得合入 Git/master

- heavy fields、meshes、eigenvectors；
- matrices、factors、PEP cache；
- raw memory timelines；
- Docker/Windows 临时日志；
- dirty 或未资格化 records。

由于仓库治理明确禁止整体合并大型 research branch，本报告批准的是**选择性合并**，不是无条件 merge commit 整个分支。

---

# 8. 验证接受

接受 follow-up 中记录的最终验证：

```text
governance/docs/projection = 22/22 passed
Task032 focused serial = 49/49 passed
selected MPI2 = each rank 28 passed, 2 skipped
selected MPI4 = each rank 28 passed, 2 skipped
projection final recheck = 4/4 passed
Case080 checker = 302/302 passed
Ruff = pass
compileall = pass
JSON/CSV/Markdown contracts = pass
git diff --check = pass
```

Review closeout 没有修改核心物理数值路径，因此不要求 formal h5/h3 重跑。h2 和 0.7 nm 仍不得运行。

GitHub combined-status API 在本次复审中不可读取，因此没有独立的远程 status-check 结论；本报告依据 clean provenance records、测试摘要、checker 和 branch diff 作出判断。

---

# 9. 下一步

Task032 选择性合并完成后，允许启动 Task033。正式顺序保持：

```text
Task033: local 3D h/p feasibility and interface-budget optimization
Task034: scalable generic 2D modal core
Task035: final Hybrid iterative solver
Task036: wavelength continuation 13.5 -> 5 -> 2 -> 1 -> 0.7 nm
```

Task033 应先：

1. 用固定 p2 的 h-adaptive 重现 uniform h5，验证机制；
2. 用 adaptive p2 重现 uniform h3，测量压缩率；
3. 做 p3 fixed-order 等精度效率扫描；
4. 再研究 p2/p3 hp zoning；
5. 联合比较接口位置、local DoF 与所需 M；
6. 采用本报告第 6 节的分级压缩判定，不预设 p2 h-adaptive 必须达到 3x。

---

# 10. 最终处置

```text
Task032 disposition = ACCEPTED_WITH_QUALIFICATIONS
13.5 nm physical/numerical implementation = ACCEPTED
h2 not-run decision = ACCEPTED
0.7 nm current-direct rejection = ACCEPTED
future complex-ends Hybrid architecture = ACCEPTED
selective merge = APPROVED
whole branch merge = NOT RECOMMENDED
ordinary default = UNCHANGED
Task033 = APPROVED AFTER SELECTIVE MERGE
```
