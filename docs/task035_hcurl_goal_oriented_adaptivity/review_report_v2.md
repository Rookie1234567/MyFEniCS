# Task035 Review V2：WSL 执行收口与正式 estimator fixture 边界

## 1. 审查结论

```text
review_status = PHASE_B_CONTINUE_FORMAL_FIXTURES_REQUIRED
branch_exists_remote = true
phase_a = accepted
phase_b_algebraic_precursor = accepted_with_renaming
phase_b_formal_hcurl_fixture = not_yet_passed
phase_c_unlocked = false
heavy_p4_authorized = false
wsl_environment_failure = false
numerical_core_failure = false
additional_review_before_phase_b_continuation = false
phase_c_auto_unlock = conditional_on_all_review_v2_gates
```

本轮审查对象为：

```text
codex/20260721-task35-hcurl-goal-oriented-adaptivity
```

Task035 `response_v2.md` 已正确关闭 Case094 staging contract，并在正确 complex activation 下完成 full regression。Phase A 环境、ABI、MPI1/2/4/8、MUMPS、SLEPc PEP、Task034 baseline 和必要 artifact binding 继续接受。

本轮没有证据表明 WSL、PETSc、SLEPc、DOLFINx、MPI、MUMPS 或 Maxwell 数值核心发生故障。首次 Phase B full pytest 的大量 real/complex 错误，直接原因是使用：

```bash
.venv/bin/python -m pytest -q
```

而未在同一 shell 中执行资格化 activation。正确执行：

```bash
source .venv/bin/activate-myfenics
pytest -q
```

后得到 `506 passed, 18 skipped`。该恢复结果接受；首次错误启动记录必须继续保留。

但是，当前 Phase B 中被标为 `fixture_pass` 的内容主要是 NumPy 小向量、手工误差值和代数 surrogate，并未完成任务书要求的真实 H(curl) analytic/manufactured finite-element fixtures。因此目前不能进入 Phase C estimator bake-off。Codex 可以立即继续 Phase B，不需要先等待额外 review；完成本报告规定的真实低成本 fixture Gate 后，方可自动解锁 Phase C。

---

## 2. 已接受内容

以下内容接受，不要求重复执行：

1. Task035 分支从 `master@5002636852ffb67b4711443da70eb536c303e34e` 创建；
2. WSL Ubuntu、complex PETSc/SLEPc/DOLFINx、project-local complex `dolfinx_mpc`；
3. MPI1/2/4/8、MUMPS 与 PEP microfixture；
4. Task034 Case093 compact baseline 与六份必要 artifact hash binding；
5. Case094 formal/staging lifecycle 修正；
6. Case001–Case093 原有正式合同未放宽；
7. Case094 staging scaffold 和 hermetic Phase A checker；
8. Phase A 最终 full regression：`494 passed, 18 skipped`；
9. Phase B 正确 activation 后 full regression：`506 passed, 18 skipped`；
10. 首次 Case094 contract failure 和首次错误 Python launcher failure 均原样保留；
11. 当前没有启动真实目标光栅 adaptive、p4 heavy 或 Task034 重型 PDE。

除非 source SHA、环境 ID、ABI、baseline descriptor 或 artifact hash 发生变化，不得重复环境安装、MPI 资格化、六份 artifact 全量验证或 Task034 重型计算。

---

## 3. 仓库级执行规则已更新

根目录 `AGENTS.md` 已在当前 Task035 分支更新，新增长期规则：

- WSL 任务必须由 WSL 内的 Codex、Linux Git/Python/MPI 运行；
- 禁止 Windows Codex/PowerShell 通过嵌套 `wsl.exe` 驱动长测试和 PDE；
- 每个环境敏感命令必须在同一 shell 中完成 `cd + activation + ABI probe + command`；
- 禁止直接以 `.venv/bin/python`、系统 Python 或裸 pytest 替代 qualification activation；
- 密码、SSH passphrase、sudo 和 Git 凭据必须由用户在 WSL 终端人工准备，Codex不得静默等待；
- 可能交互的命令先做非交互探针；
- 禁止给 full pytest/MPI/PDE 设置任意 5 秒或 30 秒短 timeout；
- 使用测试金字塔，full repository pytest 只在阶段收口运行一次；
- 无关文档或 metadata 修改不得触发环境重装、全量 artifact 验证或重型 PDE。

Codex 拉取本 review 后必须重新读取根 `AGENTS.md` 并遵守新增规则。

---

## 4. Response V2 的环境与“卡住”分析

### 4.1 当前证据不能证明 Codex 本体一定运行在 Windows

远程记录能证明：实际测试在 WSL 环境中运行，并且正确 activation 后完整通过。它不能直接证明 Codex 可执行文件是在 Windows 还是 WSL。

Codex 下一次启动时必须记录：

```bash
uname -r
pwd -P
command -v codex
command -v python
command -v git
command -v mpiexec
file "$(command -v codex)"
```

如果 `codex`、`python`、`git` 或 `mpiexec` 位于 `/mnt/c`、`/mnt/d`、Windows `AppData`，或以 `.exe` 结尾，立即停止；用户应在 WSL Ubuntu 内启动 Linux Codex CLI。

### 4.2 本轮已确认的实际问题是 shell activation 不持久

`source` 只影响当前 shell。若 Codex每次工具调用都启动新的 shell，则前一次 activation 不会自动延续。今后所有环境敏感命令统一使用同一 shell，例如：

```bash
bash -lc 'cd /home/Projects/MyFEniCS && source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_88_task035_estimator_fixtures.py'
```

不得先在一个调用中 `source`，再在下一调用中直接运行 Python。

### 4.3 短 timeout 不是有效测试

`phase_b_regression_failure.json` 中存在一次 5 秒外层 timeout。full pytest 正常需要约 248 秒，因此这种 timeout 只能产生 `launcher_timeout_no_test_conclusion`，不得触发重复环境资格化或科学负结论。

今后若长命令无输出，应先检查 prompt、进程树、CPU、MPI 子进程和日志，再决定是否终止。

---

## 5. Blocking Finding 1：当前 Phase B 是代数 precursor，不是真实 H(curl) fixture

### 5.1 homogeneous periodic fixture

当前实现使用几个手工 complex 向量，并把 residual 分量直接设为 `1e-15` 量级；所谓 MPI partition 是按：

```python
cell_id % mpi_size
```

分配四个硬编码 ID。

它可以验证：

- Hermitian norm；
- phase/orientation 小向量差；
- scalar allreduce 的基本调用。

但不能验证：

- DOLFINx Nédélec 空间；
- 实际 cell volume curl-curl residual；
- interior facet jump；
- 高阶 edge/face orientation；
- 双周期 Floquet DOF mapping；
- 真实 MPI mesh partition 和 canonical global cell identity。

因此不能称 `homogeneous periodic analytic H(curl) fixture pass`。

### 5.2 flat lossy layer fixture

当前所谓 uniform refinement trend 是直接生成：

```python
[0.2 * 0.5**level for level in range(5)]
```

该序列必然单调下降，不是网格加密后的实测 estimator/error trend。

当前 R/T/A derivative 使用任意线性向量作为 goal surrogate，并非项目 official R/T/A、R00 或 diffraction-order functional 的导数。

因此当前结果只能证明线性实值 functional 的有限差分代码正确，不能证明 DWR 对真实功率目标正确。

### 5.3 material-interface 与 Hybrid fixture

当前 material-interface 和 Hybrid fixture 仍是小向量差、手工 error split 和局部 2×2 SPD solve；没有：

- 实际 mesh/material tag；
- piecewise complex coefficient；
- H(curl) interface trace；
- local enriched FE space；
- QEP mode；
- Hybrid matching trace/projection；
- 真实 M 或 DtN truncation funnel。

这些可作为公式和 API precursor，但不能升级为正式 fixture pass。

---

## 6. Blocking Finding 2：R2 frequency scaling 尚无可辩护定义

当前实现：

```text
eta_R2 = eta_R1 / sqrt(1 + chi^2)
chi = |k| h / p
```

会在 `chi` 越大、单元越未解析时主动减小 indicator。理论笔记只要求记录 `kh/p` 并将过大值标记为 pre-asymptotic diagnostic，并未推导上述缩放。

该定义存在把最未解析单元降权、从而引导错误 marking 的风险。

修正要求二选一：

1. 暂时只把 `chi` 作为 resolution flag，不改变 R1 indicator；状态记为 `resolution_diagnostic_pass`；
2. 给出与当前 Maxwell/DtN/复材料问题相容的推导和 fixture 证据后，再定义 frequency-scaled estimator。

在此之前，R2 不得标为 formal `fixture_pass`，更不得进入真实 marking 主线。

---

## 7. Blocking Finding 3：状态命名过度

当前：

```text
R1/R2/R3/R5/G1/G2/B1/M1 = fixture_pass
phase_b_gate_pass
phase_c_unlocked = true
```

与实际 `pde_run=false`、无 DOLFINx/UFL residual、无真实 refinement 和无真实 R/T/A adjoint 不匹配。

必须改为：

```text
R1/R3/R5/G1/G2/B1/M1 = algebraic_precursor_pass
R2 = resolution_diagnostic_pass 或 formula_defined
R4 = formula_defined
phase_b_algebraic_precursor = pass
phase_b_formal_hcurl_fixture = in_progress
phase_c_unlocked = false
```

现有 precursor 代码、测试和负向扰动全部保留，不需要删除；只需准确降级其能力声明。

---

## 8. Phase B 正式低成本 fixture 要求

不得直接进入 p4 或目标光栅。只需要小网格、低成本、可审查的真实 DOLFINx/H(curl) fixtures。

### B1. 真实 homogeneous periodic H(curl) fixture

至少完成：

- 小型 3D mesh，Nédélec p1/p2；
- 可解析 plane wave 或 manufactured E；
- 真实 UFL/cell quadrature 的 volume residual；
- interior facet curl-flux jump；
- 实际 Floquet pair residual；
- orientation/phase fault injection；
- MPI1/2/4 真实 mesh partition；
- scalar reduction 与 canonical global cell ID 一致。

### B2. 真实 flat lossy layer fixture

至少完成：

- 解析 Fresnel/modal solution 或严格 manufactured solution；
- piecewise complex material；
- 至少三个实际 h/p 离散点；
- 实测 field error、observable error 和 estimator trend；
- external DtN truncation 的实际 perturbation；
- official R/T/A 或等价正式功率 functional 的 directional derivative/adjoint check。

不得再使用手写递减数组冒充 refinement trend。

### B3. 真实 material interface / corner fixture

至少完成：

- 实际 material tags 和 coefficient jump；
- interface term 由 FE field/trace 计算；
- 故意破坏 tag 或 coefficient 时能定位；
- reference error 或 local enriched solve 与 indicator 排名有可审查相关性；
- anisotropic preference 由 directional defect/candidate solve 得出，而不是硬编码 axis。

### B4. 真实 Hybrid interface microfixture

优先复用已有最小 matching-trace/QEP/Hybrid analytic fixture，不运行目标 p4：

- 实际 Et/Ht trace/projection；
- spatial discretization、external DtN 和 internal M 逐项 perturbation；
- 至少两个低成本 M 值；
- QEP eigen residual 保持 diagnostic，不静默混入 spatial estimator；
- MPI1/2 或 MPI1/4 identity。

### B5. DWR 最低资格

G1/G2 至少需要在 flat-layer 或另一个低成本真实 FE system 上：

- 从实际离散 residual 和 adjoint构造；
- 对 official R/T/A、R00 或明确的 order amplitude functional；
- 与有限差分 directional derivative 比较；
- 明确复共轭、实值 functional 和 normalization。

任意线性 NumPy goal vector 只能作为 algebraic unit test。

---

## 9. 测试策略与自动推进授权

### 9.1 不重复的内容

本轮不得重复：

- WSL 环境安装和完整资格化；
- MPI8 MUMPS/PEP microfixture；
- 六份 Task034 artifact 全量 hash；
- Task034 p3/h3、p4/h5、M funnel、MPI matrix；
- Phase A full pytest。

### 9.2 Phase B 测试金字塔

每个 fixture 小改动：

```text
对应 pure-Python unit test
+ 单个 DOLFINx fixture serial test
```

每个 fixture 收口：

```text
serial + MPI2/4 component test
```

Phase B 全部收口：

```text
Task035 Phase B focused suite
+ documentation/record checker
+ 正确 activation 下 full pytest 一次
+ Ruff / compileall / git diff --check
```

所有环境敏感命令必须使用：

```bash
bash -lc 'cd /home/Projects/MyFEniCS && source scripts/activate_myfenics_wsl.sh && <command>'
```

### 9.3 自动推进

当且仅当：

```text
all required real FE fixtures receive measured decisions
no formal method is mislabeled
R2 is downgraded or theoretically justified
serial/MPI2/MPI4 identity passes
Phase B focused suite passes
one correctly activated full pytest passes
Ruff/compileall/diff-check pass
worktree is clean
```

Codex 可设置：

```text
phase_b_formal_hcurl_fixture = pass
phase_c_unlocked = true
```

并直接进入 Phase C 的低成本 estimator bake-off，无需等待额外 ChatGPT review。

若某一个 estimator lane 失败，应保存 `fixture_negative` 并停止该 lane；只要至少 residual 主线和 goal/two-level 主线各有一个 formal fixture positive，可继续 Phase C 比较。不得为了一个研究方法失败而停止整个 Task035。

---

## 10. 文档与 response 修正

Codex 在下一次提交中应：

1. 更新 Task035 README，取消当前 `phase_b_gate_pass_phase_c_unlocked`；
2. 更新 `estimator_definitions.md`、fixture matrix/summary 的状态语义；
3. 保留所有 precursor 和首次失败/recovery records；
4. 修复 `outcomes/test_summary.md` 中“当时按”后句子中断的问题；
5. 在后续 response 中记录：
   - 精确 branch HEAD；
   - 使用的 WSL-native Codex/Python/Git/MPI paths；
   - canonical activation command；
   - formal fixture 与 precursor 的区别；
   - Phase C 是否真正解锁。

---

## 11. 继续执行指令

Codex 拉取本 Review V2 和最新 `AGENTS.md` 后，可立即继续 Phase B。

不得：

- 重做 Phase A；
- 因局部文档/metadata 错误长期停止；
- 把当前 NumPy surrogate 冒充真实 H(curl) fixture；
- 跳过真实 fixture 进入 Phase C；
- 运行 p4 heavy 或真实 adaptive；
- 使用未 activation 的 Python；
- 由 Windows 外层以短 timeout 驱动 WSL 长命令。

若出现 environment/ABI、source/hash、MPI identity、真实 residual/physics、资源或数学定义不明确的失败，保存证据并停止受影响 lane；其他局部 scaffold、文档、schema、lint 问题可按 `AGENTS.md` 直接修正并 targeted rerun。
