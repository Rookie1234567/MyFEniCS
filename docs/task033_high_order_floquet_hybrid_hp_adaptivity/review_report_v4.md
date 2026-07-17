# REVIEW REPORT V4：Task033 p3/h5 Phase C 审阅与 full3D 参考闭环路线

## 0. 审阅身份与决定

```text
review = Task033 review_report_v4
branch = codex/20260715-task33-high-order-floquet-hybrid-hp
reviewed_head = cdb1bb0db915c231d51706a04f6ff59c3abf19be
phaseC_numerical_source = b636444b693a932988b6d5d69f7e44e6a8cddb38
phaseC_status = HYBRID_COMPONENT_ACCEPTED_FULL3D_REFERENCE_OPEN
p3_h5_schur_minimal_funnel = PASS
p3_h5_augmented_vs_schur_minimal = PASS
p3_h5_full3d_direct = ACCEPTED_NOT_RUN_BY_MEMORY_GATE
same_degree_p3_hybrid_full3d_equivalence = NOT_PROVEN
whole_phaseC = NOT_PASSED
phaseC1_full3d_calibration = APPROVED
phaseC1_full3d_solve = CONDITIONAL
p3_h3 = NOT_APPROVED
p4_target_hybrid = NOT_APPROVED
h_adaptivity = DEFERRED_TO_FINAL_PHASE
ordinary_default_changed = false
whole_branch_merge = NOT_YET_APPROVED
```

Phase C 正确执行了候选级 C0：p3/h5 full3D direct、Schur-minimal M80/M120/M160 和 augmented M160 分别接受内存 Gate，而不是用 Hybrid 的低内存反向覆盖 full3D 的否决。full3D 的第二预测中心与保守上界超过现场 Gate，因此没有强跑；其余四个 Hybrid 候选在同一 clean source 上完成。

本报告接受以下结论：

1. p3/h5 Hybrid 的 QEP、模式传播、局部 FEM、内部耦合、Schur-minimal 求解、物理后处理和 augmented 对照已经形成可信的组件级闭环；
2. M80/M120/M160 截断漏斗已强收敛，不需要 M240；
3. augmented 与 Schur-minimal 在当前离散上等价；
4. full3D 的 `not_run_by_memory_gate` 是正确的安全决策；
5. 没有同阶 full3D 时，不得声明 p3 Hybrid/full3D 等价、连续解收敛或完整 Phase C 通过。

---

# 1. C0 与资源决定

## 1.1 现场 Gate

Phase C0 使用运行时读取的 container、host available、cgroup 和 swap 数据。现场有效上限及缩放 Gate 为：

| 项目 | 数值 |
|---|---:|
| effective live ceiling | 12.8433 GiB |
| two-center limit | 10.5498 GiB |
| conservative-upper limit | 11.7424 GiB |
| warning | 10.5498 GiB |
| controlled termination | 11.9259 GiB |
| swap | 0 |

完整 nonignored worktree 在正式运行前后均 clean；四个重型 Hybrid case 顺序执行，没有并发叠加。

## 1.2 p3/h5 full3D direct

两个中心为：

| 预测链 | 中心 / 上界 |
|---|---:|
| effective p/h RSS 幂律 | 6.4446 GiB |
| target p2 NNZ + Case090 p3/p2 比 + fill + factor payload | 15.0313 GiB |
| conservative upper | 18.0375 GiB |

第二条链预测：

```text
rows = 130,504
assembled NNZ = 34,085,833
factor NNZ = 513,746,598
factor payload = 11.4913 GiB
```

factor payload 已接近全部现场可用内存，尚未计入 assembled matrix、索引、MUMPS 工作区、向量、MPI 和 Python/PETSc 开销。因此 full3D 不启动是正确决定。

### 证据边界

`not_run_by_memory_gate` 是基于实测锚点和现场资源的派生启动决定，不是 p3/h5 full3D 的实测内存结果。第二预测链较保守，但在当前 14 GiB hard budget 下不能为了取得参考解而忽略它。

### 审阅决定

```text
current-host p3/h5 in-core full3D = do not run
forced run / swap / OOM-then-document = forbidden
```

---

# 2. p3/h5 Hybrid 组件结果

## 2.1 Schur-minimal M 漏斗

| M / direction | R | T | A(balance) | true residual | memory authority | total time |
|---:|---:|---:|---:|---:|---:|---:|
| 80 | 0.001090095685818 | 0.600622368233025 | 0.398287536081157 | `1.905e-12` | 2.278 GiB | 63.66 s |
| 120 | 0.001090095685267 | 0.600622368221082 | 0.398287536093651 | `2.631e-12` | 2.492 GiB | 85.10 s |
| 160 | 0.001090095685264 | 0.600622368221012 | 0.398287536093723 | `2.277e-12` | 2.641 GiB | 106.98 s |

截断差异：

| pair | max abs R/T/A delta | significant-order power relative delta | significant complex-amplitude relative delta |
|---|---:|---:|---:|
| M80 → M120 | `1.249e-11` | `5.563e-9` | `4.914e-9` |
| M120 → M160 | `7.216e-14` | `3.676e-10` | `1.925e-10` |

两个连续层级均通过 mandatory 和 strong Gate。M240 不需要运行。

### M 的处置

```text
M160 = canonical verification/reference record
M120 = cost-optimized production candidate for this frozen parameter point
M80 = fast candidate/diagnostic; parameter范围扩大后需重新确认
```

M120 相对 M160 将时间从 106.98 s 降至 85.10 s，而结果差异远低于当前 Gate。现有正式记录仍以最高的 M160 作为保守 canonical reference，不要求重跑或改写原 funnel。

## 2.2 M160 物理结果

| 指标 | 数值 |
|---|---:|
| R | 0.001090095685264 |
| T | 0.600622368221012 |
| A(balance) | 0.398287536093723 |
| A_volume | 0.398287536095597 |
| volume closure error | `1.874e-12` |
| full true residual | `2.277e-12` |
| bottom/top sampled E_t relative L2 | `1.913e-8 / 2.061e-8` |
| bottom/top sampled H_t relative L2 | `6.914e-4 / 6.175e-4` |
| QEP full/reduced shape | `1723 / 1620` |
| local rows bottom/top | `21,847 / 21,847` |
| local assembled NNZ bottom/top | `5,156,503 / 5,156,503` |

需要区分两类接口指标：

1. 变分/代数层的 interface-E projection 与 FE-modal traction equilibrium Gate；
2. 选定采样点上的 E/H relative L2 diagnostic。

运行记录声明第一类 Gate 按 `1e-8` 通过；第二类中 H 约为 `6e-4`，低于 `1e-2` Gate，但显著高于 E。该 H 值不构成失败，与 Task032 p2/h3 的采样 H 误差数量级接近；仍必须在未来同阶 full3D 对照中复核。

## 2.3 augmented 与 Schur-minimal

| 指标 | augmented vs minimal M160 |
|---|---:|
| modal coefficient relative error | `2.801e-13` |
| bottom local solution relative error | `1.680e-13` |
| top local solution relative error | `2.279e-13` |
| interface-E projection residual delta | `2.123e-13` |
| max abs R/T/A delta | `3.131e-14` |
| augmented memory authority | 4.148 GiB |
| augmented total time | 114.05 s |

两条路径共享同一 QEP、模式基和 FEM-modal 耦合，但使用不同的全局代数消元路径。结果证明当前离散下 augmented 与 Schur-minimal 的实现一致，并支持继续以 Schur-minimal 作为主路径。

该锚点不是独立物理参考，不能替代 full3D。

---

# 3. 物理合理性与当前边界

Task032 的已跟踪 p2 结果为：

```text
p2/h5: R/T/A = 0.0890216 / 0.4425883 / 0.4683901
p2/h3: R/T/A = 0.0046130 / 0.5836534 / 0.4117336
```

p3/h5 相对 p2/h3 的最大 R/T/A 绝对差约为 `1.697e-2`，明显比相对 p2/h5 的 `1.580e-1` 更小。这是“高阶粗网格结果向较细 p2 结果移动”的合理趋势，但差异仍远高于正式等价 Gate。

因此：

```text
p3/h5 physical trend = plausible positive diagnostic
p3/h5 equal-accuracy vs p2/h3 = not proven
p3/h5 same-degree Hybrid/full3D = not proven
```

没有 same-degree full3D 时，以下共同错误仍不能完全排除：

- FEM-modal 界面弱式的共享符号或缩放错误；
- 入射/外端口与内部模式归一化之间的共享系统误差；
- QEP 模态空间和接口算子共同继承的实现错误；
- 中间选面重构虽自洽，但相对真实 full3D 场存在偏差。

Phase A、Phase B、真残差、能量闭合和双路径等价已显著降低这些风险，但不能数学上消除它们。

---

# 4. 代码与证据合同审阅

## 4.1 Phase C 聚合器状态检查过宽

`build_phasec_summary_from_paths(...)` 的 `all_hybrid_watchdogs_measured` 当前接受：

```text
status in {measured_shard_pass, formal_not_pass}
```

当前三条 Schur 记录实际都是 `measured_shard_pass`，且 funnel 聚合器会严格检查单项物理 Gate，因此本次结果没有被该问题污染。

但 Phase C 的 `component_pass` 不应在自己的聚合层接受一般性的 `formal_not_pass`。在后续选择性合并前必须修改为以下之一：

1. component-pass 路径只接受 `measured_shard_pass`；或
2. 将 controlled negative 与 component pass 明确拆成不同状态，并证明 selected terminal record 必须是正向 pass。

必须新增负向测试：任意 M80/M120/M160 被替换为普通 `formal_not_pass` 时，Phase C summary 不能返回 component pass。

该修改不需要重跑 PDE，只需重新生成轻量 summary。

## 4.2 tracked 摘要缺少关键代数接口数值

当前 tracked `phaseC_summary.json` 和 `p3_h5_phaseC.md` 保存了 sampled E/H 数值，但没有直接列出：

- interface-E projection combined residual 的实际值；
- bottom/top FE-modal traction equilibrium residual 的实际值；
- 最大 right/left QEP polynomial residual；
- 最大 biorthogonality identity error；
- forward/backward 有限有效模态数量与 numerical-infinity 过滤统计。

原始 ignored evidence 中存在这些量，文档也声明 Gate 通过。为了让远程仓库可独立审阅，必须将上述关键最大值提升到 tracked lightweight summary。

该补充不需要重跑 PDE，应从现有 hash-bound raw records 提取并重新生成 summary。

## 4.3 source reuse

Case090 复用范围已正确收窄为 `case090_pure3d_floquet_core`。`modal_trace_projection.py` 被显式记录为 Hybrid 数值组件改动，不再被描述成“全仓 numerical source unchanged”。当前处理接受。

---

# 5. 下一阶段：Phase C1 full3D reference calibration

当前 Hybrid 不应重复运行。下一步应只降低 full3D 资源预测的不确定性。

## 5.1 首选：真实 assembly-only 记录

批准在 p3/h5、相同目标光栅、相同物理参数上建立 full3D assembly-only 记录：

```text
mesh + p3 Nedelec space
Floquet constraints
full operator assembly
external DtN assembly
no numerical factorization
no solve
```

必须实测：

- exact rows；
- exact assembled NNZ；
- matrix payload 与 PETSc memory；
- assembly simultaneous RSS / cgroup；
- Floquet constraint rows、NNZ、setup time；
- source clean identity；
- no swap；
- 是否形成任何 dense boundary object。

assembly-only 不是 PDE 解，不能成为 full3D reference；它的目的只是用目标真实矩阵替换 Case090 的 p3/p2 NNZ 外推。

## 5.2 可选：symbolic-analysis-only

若 PETSc/MUMPS 当前接口能以可审计、fail-closed 的方式只运行 symbolic analysis，而不进入 numerical factorization，可记录：

- predicted factor NNZ；
- MUMPS estimated memory；
- symbolic analysis RSS；
- ordering 与 MPI 参数。

若无法明确保证“不进入 numeric factorization”，不得在当前 host 尝试。

## 5.3 重新计算 C0

使用 exact assembled NNZ 和可选 symbolic estimate 重新构造两个独立中心。不得手工覆盖原 veto。

结果分支：

```text
new Gate pass on current host
→ permit p3/h5 full3D direct only

new Gate still fails
→ keep current-host veto
→ run on independently approved larger-memory host
```

基于当前保守上界，larger-memory host 应至少提供约 24 GiB 的真实可用内存，优先使用 32 GiB 或更高有效预算，并重新计算现场 Gate。

---

# 6. full3D 运行后的最小闭环

如果 Phase C1 允许生成 p3/h5 full3D：

1. 运行一条 p3/h5 full3D reference；
2. 在同一 numerical source 上运行或通过严格 descendant audit 复用一条 Schur-minimal M160；
3. 不重复 M80/M120 漏斗；
4. 不重复 augmented anchor，除非耦合/求解代码发生变化；
5. 比较 R/T/A、显著逐阶复振幅、A_volume、接口 E/H 和 selected-plane E/H；
6. 全部通过后才可关闭 whole Phase C。

full3D 比较 Gate 至少保持：

```text
full true residual <= 1e-9
max abs R/T/A delta <= 1e-5
significant-order relative delta <= declared Task032/Task033 gate
sampled interface E/H <= declared gate
selected-plane E/H <= declared gate
volume absorption delta <= 1e-5
```

---

# 7. 其他阶段处置

## p3/h3

仍不批准。p3/h5 尚未取得同阶 full3D reference，直接进入 p3/h3 会扩大未闭合的物理不确定性和内存风险。

## p4

Phase B 只闭合了两模态基础迹组件。进入 p4 target Hybrid 前仍需之前要求的四模态近简并块 matched-trace 小测试。该小组件可以在 Phase C1 期间作为独立轻量任务完成，但不得启动 p4 目标 full3D/Hybrid。

## buffer 与 h 自适应

继续延期。当前最优先缺口是 p3/h5 独立 full3D reference，而不是扩大参数矩阵。

---

# 8. 当前最终处置

```text
Task033 Stage1 high-order Floquet = ACCEPTED
Task033 Phase A QEP/tracking = ACCEPTED_WITH_QUALIFICATIONS
Task033 Phase B p3 matched trace = ACCEPTED
Task033 Phase B p4 basic matched trace = ACCEPTED_WITH_SCOPE_LIMIT
Task033 Phase C p3/h5 Hybrid component = ACCEPTED_WITH_EVIDENCE_FIXES
p3/h5 M funnel = ACCEPTED; no M240
p3/h5 augmented/minimal equivalence = ACCEPTED
p3/h5 full3D direct = VALID NOT_RUN_BY_MEMORY_GATE
same-degree p3 Hybrid/full3D equivalence = OPEN
whole Phase C = NOT PASSED
Phase C1 assembly/symbolic calibration = APPROVED
p3/h3 = NOT APPROVED
p4 target Hybrid = NOT APPROVED
h adaptivity = FINAL PHASE
whole branch merge = NOT YET APPROVED
```

Codex 下一步应先完成两项无需重算的证据修复：

1. 收紧 Phase C aggregator 的 `formal_not_pass` 处理并重生成 tracked summary；
2. 将实际 interface projection/traction、QEP residual 和模态容量最大值提升到 tracked summary。

随后执行 Phase C1 p3/h5 full3D assembly-only 资源校准。完成 Phase C1 summary 后再次停止复审，不得自动启动 full3D factorization、p3/h3、p4 target 或自适应。
