# Task035 Review V2：Windows Codex 客户端、WSL 后端与 Phase B 快速推进

## 1. 审查结论

```text
review_status = PHASE_B_REAL_FIXTURE_FAST_TRACK
branch_exists_remote = true
phase_a = accepted
phase_b_algebraic_precursor = accepted_with_renaming
phase_b_real_fixture_minimum_gate = B1_plus_B2
phase_c_low_cost_unlocked = false
phase_c_formal_completion = pending_B3_B4
heavy_p4_authorized = false
wsl_environment_failure = false
numerical_core_failure = false
additional_review_before_phase_b_continuation = false
phase_c_low_cost_auto_unlock = conditional_on_B1_B2_gates
```

本轮审查对象为：

```text
codex/20260721-task35-hcurl-goal-oriented-adaptivity
```

Task035 `response_v2.md` 已正确关闭 Case094 staging contract。Phase A 的 WSL Ubuntu、complex PETSc/SLEPc/DOLFINx、project-local complex `dolfinx_mpc`、MPI1/2/4/8、MUMPS、SLEPc PEP、Task034 baseline 和必要 artifact binding 继续接受。

首次 Phase B full pytest 的大量 real/complex 错误来自错误启动：

```bash
.venv/bin/python -m pytest -q
```

该命令没有加载项目的 complex PETSc/SLEPc、`PYTHONPATH`、`LD_LIBRARY_PATH` 和 qualification marker。正确 activation 后：

```bash
source scripts/activate_myfenics_wsl.sh
pytest -q
```

得到：

```text
506 passed, 18 skipped
```

因此当前没有证据表明 WSL、PETSc、SLEPc、DOLFINx、MPI、MUMPS 或 Maxwell 数值核心故障。首次错误启动记录必须继续保留，但不得重复环境重装或 Phase A 资格化。

当前 Phase B 的 NumPy 小向量、小矩阵、手工 residual 和代数 surrogate 具有单元测试价值，但不能称为正式 H(curl) finite-element fixture qualification。它们应保留并改名为：

```text
algebraic_precursor_pass
```

为避免前置阶段继续拖延，本 Review 不再要求 B1–B4 全部完成后才开始任何 estimator 比较。完成 B1+B2 的真实低成本 Gate 后，可立即进入 Phase C-low-cost bake-off；B3/B4 与该低成本 bake-off 并行完成。

---

## 2. 用户交互与执行环境决定

用户将继续使用 **Windows Codex 客户端本身**与 Codex 对话。该方式获得批准。

不得要求用户改用：

- Linux Codex CLI；
- VS Code；
- 浏览器版前端；
- 其他 IDE 或交互工具。

正确的执行架构是：

```text
Windows Codex 客户端负责对话和编排
→ WSL Ubuntu 负责 Git、Python、MPI、PETSc/SLEPc、DOLFINx 和 PDE
```

Windows Codex 客户端本身是 Windows 程序不构成环境混用。真正需要避免的是使用 Windows Python、Windows Git、Windows MPI、Windows 仓库副本或 `/mnt/c`、`/mnt/d` 上的仓库执行本项目。

Codex 可以通过客户端的 WSL 执行能力，或显式调用：

```powershell
wsl.exe -d Ubuntu -- bash -lc 'cd /home/Projects/MyFEniCS && source scripts/activate_myfenics_wsl.sh && <command>'
```

每个环境敏感命令必须在同一个 WSL shell 中完成 `cd + activation + 必要 preflight + command`。不得依赖上一次调用中的 `source`、`cd` 或环境变量自动延续。

Task035 目录中的 `AGENTS.md` 已记录完整规则。Windows Codex 客户端不是 blocker，也不得再要求用户安装 Linux Codex CLI。

---

## 3. 已接受且不得重复的内容

以下内容继续接受：

1. Task035 分支从 `master@5002636852ffb67b4711443da70eb536c303e34e` 创建；
2. WSL Ubuntu 和 complex ABI；
3. MPI1/2/4/8、MUMPS 与 PEP microfixture；
4. Task034 Case093 compact baseline 与六份必要 artifact hash binding；
5. Case094 formal/staging lifecycle 修正；
6. Case001–Case093 原有正式合同未放宽；
7. Case094 staging scaffold 和 hermetic Phase A checker；
8. Phase A 最终 full regression：`494 passed, 18 skipped`；
9. Phase B 正确 activation 后 full regression：`506 passed, 18 skipped`；
10. 首次 Case094 contract failure 和首次错误 Python launcher failure 均原样保留；
11. 当前没有启动真实目标光栅 adaptive、p4 heavy 或 Task034 重型 PDE。

除非 source SHA、环境 ID、activation 脚本、ABI、baseline descriptor 或 artifact hash 发生变化，不得重复：

- 环境安装和完整资格化；
- MPI1/2/4/8、MUMPS/PEP microfixture；
- 六份 Task034 artifact 全量 hash；
- Task034 p3/h3、p4/h5、M funnel 或 MPI matrix；
- Phase A full pytest。

---

## 4. 当前 algebraic precursor 的准确边界

### 4.1 homogeneous periodic precursor

当前实现使用手工 complex 向量和手工 residual 分量，并以 `cell_id % mpi_size` 模拟分区。

它可以验证：

- Hermitian norm；
- phase/orientation 小向量差；
- scalar allreduce 基本调用；
- schema 和异常处理。

它不能验证：

- DOLFINx Nédélec 空间；
- 实际 UFL/cell quadrature residual；
- interior facet curl-flux jump；
- 高阶 edge/face orientation；
- 实际 Floquet DOF mapping；
- 真实 MPI mesh partition 和 canonical global cell identity。

### 4.2 flat lossy layer precursor

当前所谓 refinement trend 是手写递减数组，不是实际网格加密后的实测误差。当前 R/T/A derivative 也是任意线性 goal vector，而不是项目 official R/T/A、R00 或 diffraction-order functional。

因此只可称为：

```text
linear_goal_and_complex_conjugation_unit_test
```

### 4.3 material-interface、Hybrid 和 R4 precursor

当前 material-interface、Hybrid 和 R4 内容仍是小向量差、手工 error split 和局部 2×2 SPD solve。它们没有实际 material tags、H(curl) trace、QEP mode、Hybrid projection、真实 M/DtN perturbation 或 constrained equilibrated patch。

这些代码保留，但状态必须准确。

---

## 5. 状态修正

当前以下状态过度：

```text
R1/R2/R3/R5/G1/G2/B1/M1 = fixture_pass
phase_b_gate_pass
phase_c_unlocked = true
```

必须改为：

```text
R1/R3/R5/G1/G2/B1/M1 = algebraic_precursor_pass
R2 = resolution_diagnostic_pass
R4 = formula_defined
phase_b_algebraic_precursor = pass
phase_b_real_fixture_minimum_gate = in_progress
phase_c_low_cost_unlocked = false
phase_c_formal_completion = pending_B3_B4
```

现有 precursor 代码、测试、首次失败和 recovery records 全部保留，不删除、不改写为正式 FE qualification。

---

## 6. R2 frequency 边界

当前未经推导的：

```text
eta_R2 = eta_R1 / sqrt(1 + chi^2)
chi = |k|h/p
```

会使 `chi` 越大、越未解析的单元反而得到更小 indicator，存在错误降权风险。

本阶段 R2 只允许记录：

```text
chi = |k|h/p
resolved / pre-asymptotic diagnostic
```

不得使用未经证明的 frequency scaling 修改 R1 marking 权重。只有给出与当前 Maxwell/DtN/复材料问题相容的推导和真实 fixture 证据后，才可升级为 formal frequency-scaled estimator。

---

## 7. Phase B 最小真实 fixture Gate

### B1. real periodic Nédélec/H(curl) fixture

使用低成本小网格，不运行目标光栅或 p4 heavy。至少完成：

- 小型 3D mesh；
- Nédélec p1，条件允许时增加 p2；
- analytic plane wave 或严格 manufactured field；
- 实际 UFL/cell quadrature residual 或可审查 defect；
- 实际 Floquet pair residual；
- orientation/phase fault injection；
- serial/MPI2 identity；
- scalar reduction 与真实 distributed cell identity 一致。

MPI4 可在必要时补充，但不作为 Phase C-low-cost 的强制前置。

### B2. real flat lossy layer / official-goal fixture

至少完成：

- piecewise complex material；
- analytic Fresnel/modal solution 或严格 manufactured solution；
- 至少三个实际 h/p 离散点；
- 实测 field error、observable error 和 estimator trend；
- 一个 external DtN perturbation；
- 一个 official R/T/A、R00 或明确 order functional 的 directional derivative/adjoint check；
- serial/MPI2 identity。

不得再使用手写递减数组冒充 refinement trend，也不得用任意 NumPy goal vector冒充 official functional。

### B1+B2 自动解锁条件

当以下条件全部满足：

```text
B1 real FE fixture = pass
B2 real FE/official-goal fixture = pass
serial/MPI2 identity = pass
Task035 focused suite = pass
R2 = diagnostic only
states are accurately renamed
Ruff/compileall/diff-check = pass
```

Codex 可设置：

```text
phase_b_real_fixture_minimum_gate = pass
phase_c_low_cost_unlocked = true
```

并直接进入 Phase C-low-cost estimator bake-off，无需等待新的 ChatGPT review，也不要求此时立即运行 full repository pytest。

---

## 8. 与 Phase C-low-cost 并行完成的正式项

以下内容不再阻塞 Phase C-low-cost，但必须在正式选择 Phase D mesh backend 或运行任何 p4/h5 adaptive heavy case前完成或形成明确 controlled-negative 决定。

### B3. material-interface/corner FE fixture

至少完成：

- 实际 material tags 和 coefficient jump；
- interface term 由 FE field/trace 计算；
- 故意破坏 tag 或 coefficient 时能定位；
- reference error 或 local enriched solve 与 indicator 排名具有可审查相关性；
- anisotropic preference 来自 directional defect/candidate solve，而非硬编码 axis。

### B4. Hybrid Et/Ht、M/DtN microfixture

优先复用已有最小 matching-trace/QEP/Hybrid analytic fixture，不运行目标 p4。至少完成：

- 实际 Et/Ht trace/projection；
- spatial、external DtN 和 internal M 分项 perturbation；
- 至少两个低成本 M 值；
- QEP eigen residual 保持 diagnostic；
- MPI1/2 或 MPI1/4 identity。

### B5. DWR 最低资格

G1/G2 至少需要在 B2 或另一个低成本真实 FE system 上：

- 从实际离散 residual 和 adjoint构造；
- 对 official R/T/A、R00 或明确 order amplitude functional；
- 与有限差分 directional derivative 比较；
- 明确复共轭、实值 functional 和 normalization。

任意线性 NumPy goal vector 只能作为 algebraic unit test。

---

## 9. 测试节奏

### 每个小改动

```text
对应 pure-Python unit test
+ 单个真实 fixture serial test
```

### 一个真实 fixture 收口

```text
serial + MPI2
必要时 MPI4
```

### B1+B2 / Phase C-low-cost 解锁

```text
Task035 focused suite
+ record/document checker
+ scoped Ruff
+ compileall
+ git diff --check
```

此处不要求重复 full repository pytest。

### Phase B formal completion 或阶段交付

```text
B3/B4 measured decision
+ Task035 focused suite
+ 正确 activation 下 full pytest 一次
+ Ruff / compileall / git diff --check
```

full repository pytest 每个 Phase 最多一次。文档、schema、README、record 或 lint 的局部修复不得触发环境重装、artifact 全量校验或重复 full pytest。

所有环境敏感命令通过 Windows Codex 客户端调用 WSL，并在同一个 WSL shell 中运行，例如：

```powershell
wsl.exe -d Ubuntu -- bash -lc 'cd /home/Projects/MyFEniCS && source scripts/activate_myfenics_wsl.sh && python -m pytest -q <target>'
```

---

## 10. 卡住、密码与局部错误处理

Codex 不得因 Windows Codex 客户端本身位于 Windows 而停止。

可能等待密码的操作前先运行非交互探针。探针失败时，给用户一条可复制到 Ubuntu 终端的人工命令，不得静默等待。

以下问题可以在当前阶段直接修复并 targeted rerun，不必长期停止整个 Task：

- README、schema、index 或 staging scaffold 缺项；
- 明确局部的 record/metadata 问题；
- lint、格式、链接；
- 单个测试夹具的无歧义实现错误。

以下问题必须停止受影响 lane 并报告：

- WSL complex ABI、source SHA 或 baseline hash 不一致；
- MPI identity、true residual 或正式物理 Gate 失败；
- estimator 数学定义存在不明确问题；
- 需要启动 p4/h5 heavy case；
- 需要改变 ordinary default、任务范围或核心数值架构；
- 内存、swap、磁盘或进程终止 Gate 触发。

长命令无输出时先检查 prompt、CPU、进程树、MPI 子进程和日志，不得用短 timeout 反复重启。

---

## 11. 文档与 response 修正

Codex 下一次提交应：

1. 更新 Task035 README，取消当前过早的 `phase_b_gate_pass_phase_c_unlocked`；
2. 更新 `estimator_definitions.md`、fixture matrix/summary 的状态语义；
3. 保留全部 precursor 和首次失败/recovery records；
4. 修复 `outcomes/test_summary.md` 中句子中断的问题；
5. 在后续 response 中记录：
   - 精确 branch HEAD；
   - Windows Codex 客户端 + WSL execution backend；
   - canonical WSL activation command；
   - formal FE fixture 与 algebraic precursor 的区别；
   - B1/B2 和 Phase C-low-cost 解锁状态；
   - B3/B4 的并行进度。

Task035 的执行规则只维护在本目录 `AGENTS.md`，本轮审查要求只维护在本 `review_report_v2.md`。不要再为普通澄清创建新的 addendum 或平行执行权威。

---

## 12. 继续执行授权

Codex拉取本 Review V2 和最新 `AGENTS.md` 后，可立即继续真实 B1/B2 fixture 开发。

不得：

- 重做 Phase A；
- 要求用户改用 Linux Codex CLI、VS Code 或其他前端；
- 因局部文档/metadata 错误长期停止；
- 把 NumPy surrogate 冒充真实 H(curl) fixture；
- 使用未经推导的 R2 scaling 驱动 marking；
- 跳过 B1/B2 进入 Phase C-low-cost；
- 在 B3/B4 未决前进入 Phase D production backend 或 p4/h5 heavy；
- 使用未 activation 的 Python；
- 给正常数分钟测试设置短 timeout。

完成 B1+B2 最小 Gate 后，可直接进入 Phase C-low-cost，无需新的 review。B3/B4 与 Phase C-low-cost 并行完成；它们在 Phase D 或任何 p4/h5 heavy run 前必须通过或形成明确 controlled-negative 决定。
