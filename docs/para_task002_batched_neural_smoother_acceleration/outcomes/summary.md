# PARA-Task002 阶段结果总结

## 1. 最终状态

| 项目 | 结果 |
|---|---|
| Task | PARA-Task002 — Batched Low-Overhead Neural Smoother Acceleration |
| 执行分支 | `ChatGPT/20260715-para-task-neural-local-pc` |
| 前置实现 | PARA-Task001 implementation `ee5d248e09aaff3700f22805024ce0abc2e25822` |
| Task002 开始时 HEAD | `0f29454` |
| Task002 首次本地实现 commit | `f34266b` — `feat: evaluate batched linear reduced smoother` |
| 前置审阅 | PARA-Task001 `PASS_WITH_QUALIFICATIONS`，允许同分支继续 PARA-Task002 |
| 最终 classification | `local_microkernel_success_global_signal_insufficient` |
| P1/P2 | pass / pass |
| P3 | shadow 数值与安全语义通过；运行间轨迹不具备位级复现性 |
| P4 | numeric pass，performance signal fail |
| P5 / all-slab | `not_run_by_gate` |
| h3 / h2 | `not_run_by_gate` |
| ordinary default | 未改变 |
| production/global acceleration claim | 不允许 |
| Git 操作边界 | 只做本地 commit；未 pull、push、merge、rebase、切换或新建分支 |

本任务证明了两件不同的事实：

1. Task001 的 Python 行循环 CSR 与逐向量 POD/MLP 确实可以被显著优化；固定线性 reduced correction 在真实 slab-9 数据上也具有稳定的局部数值效果。
2. 即使把微核开销降到 Task001 的约 10%，单个 slab 带来的外层迭代收益仍太小，正式 P4 信号门没有通过，因而没有依据扩展到 16 slabs，更没有依据运行 h3/h2。

---

## 2. 工作目录阅读与一致性审计

执行前按照任务书和用户要求完成了仓库代码/文档一致性阅读。重点阅读对象及其对本任务的约束如下。

| 阅读组 | 主要文件 | 对 Task002 的约束或结论 |
|---|---|---|
| 仓库工作规范 | `docs/repository_work_principles.md`、`docs/task_retrospective_standard.md` | 结果必须可追踪；保留负结果；禁止把局部指标包装成全局成功 |
| 架构与求解器 | `docs/architecture_overview.md`、`docs/solver_guide.md`、`docs/iterative_solver_ports.md` | exact condensed operator、right FGMRES、75D coarse、true residual、official R/T/A 不得弱化 |
| Task001 任务与结果 | Task001 `task.md`、`outcomes/*`、`review_report_v1.md` | Task001 数值正信号成立，但在线实现工程负；Task002 只能从低开销/批量/固定线性路径重开 |
| Task001 Case | `benchmarks/cases/090_neural_local_pc_acceleration/` | 冻结 h5、MPI4、slab 9 数据/模型和历史负候选口径 |
| local backend | `src/solvers/local_slab_solver.py`、`src/solvers/neural_local_pc.py` | 原瓶颈包括 Python DoF row loop、逐向量投影和重复 exact audit |
| owner-computes smoother | `src/solvers/physical_slab_two_level.py` | slab ownership、scatter、weights、two-step smoother 和 ILU action 必须保持一致 |
| 数据/训练/验证 | `benchmarks/neural_pc/data_contract.py`、`petsc_capture.py`、`train_local_pc.py`、`evaluate_local_pc.py` | 继续使用 exact fingerprint、独立 validation、frozen checkpoint、no-online-training |
| 正式 runner | `benchmarks/run_workstation_iterative.py` | 新路径必须显式 opt-in，不得改变普通 solver 默认入口 |

一致性检查的直接结果是：本任务没有重写物理问题、MPC、DtN、coarse space 或外层 Krylov，只新增 local slab 研究后端及其显式 runner 参数。

---

## 3. 任务目标与非目标

### 3.1 目标

| 目标 | 要回答的问题 |
|---|---|
| 消除 Python CSR 瓶颈 | compiled SciPy/PETSc local action 能否达到 Python row loop 的 20% mean / 30% p95 以内？ |
| 测试固定线性 reduced map | local inverse 本质为线性时，POD/ridge 是否比 nonlinear MLP 更便宜且仍满足局部质量门？ |
| 提供 batch API | 能否用 `predict_many()` 形成无 DoF Python loop 的 BLAS 路径？ |
| 融合 residual audit | 能否复用 `q=r-Az_ilu`，避免再次计算完整 `A(z_ilu+delta)`？ |
| one-slab shadow/active 验证 | 微核成功能否转换成外层迭代或 wall time 的真实 h5 信号？ |

### 3.2 非目标

| 明确不做 | 原因 |
|---|---|
| 改变 ordinary default | Task002 是 research-only continuation |
| 改物理模型、材料、几何、偏振或 DtN 模式 | 会破坏与 Task001 baseline 的可比性 |
| 用训练 loss 代替 local residual | Gate 要求真实 operator action |
| 在线训练 | 破坏固定预条件器、确定性和可审计性 |
| 把完整 global PETSc vector 送入 GPU | 任务只允许 owner-local reduced coordinates |
| P4 失败后继续 all-slab/h3/h2 | 明确违反停机门 |
| 提交大型 dataset/checkpoint/raw logs | 重型证据必须保持 Git ignored |

---

## 4. 冻结物理、数值配置与运行环境

### 4.1 冻结物理与求解器

| 类别 | 冻结值 |
|---|---|
| wavelength | 13.5 nm |
| material | 当前验证的 complex Si optical constant |
| periodic cell | 50 × 25 × 140 nm |
| Si block | 17 × 25 × 120 nm |
| incidence | theta=80°、phi=0°、S polarization |
| periodicity | x/y double Floquet |
| ports | 80 auxiliary Fourier-DtN unknowns |
| FE | p2 Nédélec hexahedral |
| h5 FE DoF | 44,698 |
| physical slabs | 16，overlap 0.25 |
| selected slab | slab 9，grating/interior representative |
| coarse space | 75D true-action Galerkin |
| outer solver | right FGMRES，restart 90，rtol `1e-6` |
| smoother | two-step physical-slab，ILU0，subdomain-local shift，factor-only storage |
| formal run | MPI4；BLAS/OpenMP threads 固定为 1 |

### 4.2 当前机器与软件

| 资源 | 实测配置 |
|---|---|
| Host/WSL | Windows host；Ubuntu 24.04 WSL2 |
| CPU | Intel Xeon Platinum 8260；48 visible cores |
| WSL memory / swap | 约 228 GiB / 32 GiB |
| GPU | 2× Quadro RTX 8000 |
| FE Python | 3.12.3 |
| NumPy / SciPy | 1.26.4 / 1.11.4 |
| DOLFINx | 0.10.0.post2 |
| PETSc | 3.19.6 complex |
| dolfinx_mpc | 0.10.1 complex user build |
| ML environment | `fenics-ml` |
| PyTorch | 2.7.1+cu118；CUDA 可见 2 卡 |
| GPU construction | rank 候选使用 `cuda:0`；rank64 并行筛选曾使用 `cuda:1` |
| FE wrapper | `/home/fenics/.local/bin/myfenics-python-complex` |
| Docker | 未使用 |

---

## 5. P0：同轮环境、基线与 Task001 负候选

### 5.1 本轮运行结果

| h5 run | iterations | reported / condensed / full residual | solve / total (s) | peak incl. RTA (GiB) |
|---|---:|---|---:|---:|
| original ILU baseline | 849 | `9.988413e-7 / 9.988413e-7 / 9.988413e-7` | 151.343 / 227.120 | 1.595348 |
| Task001 one-slab ILU+NN negative | 847 | `9.885644e-7 / 9.885644e-7 / 9.885644e-7` | 439.848 / 486.811 | 1.650707 |

### 5.2 Task001 负候选的同轮拆解

| 指标 | 同轮值 | 解释 |
|---|---:|---|
| slab-9 calls | 5,082 | 只在一个 internal slab 启用 |
| fallback | 0 | 数值安全检查全部接受 |
| local candidate rho median / p95 | 0.3580 / 0.5121 | 局部修正确实有效 |
| inference accumulated | 39.337 s | 逐向量 POD/MLP |
| residual-check accumulated | 72.222 s | Python CSR exact checks |
| solve ratio vs 同轮 baseline | 2.906× | 工程负结果再次复现 |
| peak increase | 3.47% | 内存不是主要失败原因 |

历史 Task001 baseline 为 861 iterations、93.312 s solve；本轮 baseline 为 849 iterations、151.343 s。迭代与墙钟存在明显运行间波动，因此 Task002 只使用本轮 P0 数字做正式 P4 比较，历史数字只用于解释 Task001 根因。

---

## 6. 实现与方法

| 方法 | 实现方式 | 目的 | 可信保护 |
|---|---|---|---|
| persistent SciPy CSR | 构造一次 `scipy.sparse.csr_matrix`，提供 `action()` / `action_many()` | 消除逐 DoF Python row loop | complex128 error Gate |
| PETSc owner-local comparator | `COMM_SELF` SeqAIJ + persistent Vec + `Mat.mult` | 比较 native owner MatMult | exact action comparison |
| fixed complex reduced map | `c=U^H q; d=Wc; delta=Vd` | 用线性 BLAS 替代 nonlinear MLP | 无 bias、无 activation |
| CUDA offline construction | complex128 SVD + ridge solve | 利用现有 RTX 8000，避免 CPU 训练 | runtime 无在线训练 |
| batched inference | `predict_many()` 以矩阵乘法处理 samples | 建立 owner batching 接口 | batch/independent Gate |
| fused audit | `candidate residual = q-A delta` | 复用 ILU residual，避免完整候选重算 | exact CSR action |
| shadow adapter | 计算 candidate 和 audit，但写回 baseline ILU | 观察误判与真实开销 | 全局 action 不主动改变 |
| active adapter | 仅 candidate 不劣于 ILU 时写入 `baseline+delta` | one-slab 正式信号验证 | every-call nondegradation |
| frozen checkpoint | arrays + manifest + SHA-256 + operator fingerprint | 可重复加载与 fail closed | mismatch/corruption 拒绝 |

### 6.1 新增 runtime action

固定模型对一个 residual 的数学路径为：

```text
q = r - A z_ilu
c = U^H q
d = W c
delta = V d
candidate residual = q - A delta
z_out = z_ilu                  (shadow)
z_out = z_ilu + delta          (active 且 non-degradation pass)
```

该路径保持线性，不含 per-call checkpoint load、subprocess、文件交换、online update 或 nonlinear activation。

---

## 7. 实验矩阵与 Gate 流程

| 阶段 | 实际运行 | 状态 | 是否允许进入下一阶段 |
|---|---|---|---|
| P0 | environment/import、MPI4 h5 baseline、同轮 Task001 negative、diff check | pass | 是 |
| P1 | slab 0、9、10：Python/SciPy/PETSc action | pass | 是 |
| P2 | rank128/96/64/32 线性候选构造与 validation | rank32 selected；pass | 是 |
| P3 | slab-9 rank32 every-call shadow MPI4 h5 | safety/numeric pass with reproducibility qualification | 是，进行一次受控 P4 |
| P4 | slab-9 rank32 active MPI4 h5 | numeric pass；signal fail | 否 |
| P5 | 16 slabs active | `not_run_by_gate` | 不适用 |
| h3 | formal run | `not_run_by_gate` | 不适用 |
| h2 | formal run | `not_run_by_gate` | 不适用 |
| Lane C nonlinear shared trunk | 未运行 | Lane B 已通过 local Gate，无必要进入 | 否 |
| factor removal | 未运行 | reduced action 仍慢于 ILU local solve，且 P4 signal 失败 | 否 |

---

## 8. P1：真实 local action 微基准

单线程、complex128、200 次重复调用结果如下。SciPy 与 Python 使用同一 portable operator；PETSc 使用 owner-local SeqAIJ。

| slab | 类型 | size | nnz | Python mean / p95 (ms) | SciPy mean / p95 (ms) | SciPy mean / p95 ratio | PETSc mean (ms) |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | boundary | 3,670 | 354,148 | 9.266 / 10.092 | 0.661 / 0.781 | 7.13% / 7.74% | 1.133 |
| 9 | grating/interior | 5,248 | 526,696 | 13.191 / 14.003 | 0.957 / 1.013 | 7.26% / 7.23% | 1.583 |
| 10 | second interior | 5,248 | 526,696 | 13.769 / 16.941 | 1.032 / 1.242 | 7.49% / 7.33% | 1.712 |

### 8.1 P1 Gate

| Gate | 要求 | 实测最差值 | 结论 |
|---|---:|---:|---|
| SciPy action error | `<=1e-12` | 0 | pass |
| PETSc action error | `<=1e-12` | `2.568e-16` | pass |
| optimized mean / Python mean | `<=0.20` | 0.0749 | pass |
| optimized p95 / Python p95 | `<=0.30` | 0.0774 | pass |
| repeated-call RSS growth | no continued growth | slab9/10 为 0；boundary 一次性 768 KiB | pass with measurement scope |

SciPy 在当前机器/调用接口下比 PETSc SeqAIJ MatMult 更快，因此成为后续 reduced correction 的正式研究 action backend。该结论只针对 owner-local 单向量/小 batch，不代表全局 PETSc MatMult 的一般性能排序。

---

## 9. P2：固定线性 reduced map

### 9.1 数据合同

| 数据项 | 值 |
|---|---:|
| representative slab | 9 |
| dataset samples | 480 |
| train / validation | 384 / 96 |
| sample kinds | real Krylov RHS 160；ILU residual 160；synthetic error 128；teacher solve 32 |
| ILU-residual train / validation | 128 / 32 |
| validation separation | 独立 generation seed / time segment |
| teacher | SciPy sparse LU |
| operator fingerprint | `0fe7e9f597345f6a10bd924ebc43e15198815e151654173c0659d7dbf0306784` |

### 9.2 rank 筛选

| rank | model storage | rho median / p95 | mean / p95 inference+audit (ms) | mean ratio to Task001 | 结果 |
|---:|---:|---:|---:|---:|---|
| 128 | 21,757,952 B | 0.3521 / 0.4553 | 5.890 / 6.884 | 26.83% | quality pass；mean performance fail |
| 96 | 16,269,312 B | 0.4012 / 0.5222 | 5.207 / 6.430 | 23.72% | pass |
| 64 | 10,813,440 B | 0.4740 / 0.6084 | 5.468 / 9.925 | 24.91% | pass，但 p95 波动更大 |
| 32 | 5,390,336 B | 0.5939 / 0.7457 | 2.281 / 2.490 | 10.39% | selected |

rank32 接近 local quality median 上限，但显著降低运行成本和模型存储，因此按“满足质量后优先最低开销”原则选为 P3/P4 候选，而不是选择 validation rho 最低的 rank128。

### 9.3 rank32 Local Gate

| Gate | 要求 | rank32 实测 | 结论 |
|---|---:|---:|---|
| linearity error | `<=1e-11` | `3.894e-15` | pass |
| determinism error | `<=1e-13` | 0 | pass |
| batch vs independent | `<=1e-12` | 0 | pass |
| all finite | true | true | pass |
| ILU-residual rho median | `<=0.60` | 0.593884 | pass，余量较小 |
| ILU-residual rho p95 | `<=0.85` | 0.745695 | pass |
| mean vs Task001 inference+audit | `<=25%` | 10.39% | pass |
| p95 vs measured Task001 p95 | `<=35%` | 7.54% | pass |

Task001 同数据实测 p95 为 33.031 ms；rank32 p95 为 2.490 ms。作为直接成本参照，validation SciPy `spilu.solve` mean/p95 为 1.596/1.792 ms，因此 reduced correction 加一次 exact audit 仍比单次 ILU local solve 贵。这也是不进入 factor-removal lane 的重要原因。

---

## 10. P3：one-slab shadow integration

### 10.1 Shadow 结果

| 指标 | P3 shadow |
|---|---:|
| enabled slab | 9 only |
| outer iterations | 861 |
| PC / one-level / operator applies | 861 / 5,166 / 2,603 |
| slab-9 shadow calls | 5,166 |
| accepted by exact non-degradation | 5,166 / 5,166 |
| baseline rho median | 0.565748 |
| candidate rho median / p95 | 0.370378 / 0.539424 |
| local adapter elapsed | 40.374 s |
| local adapter mean | 7.815 ms/call |
| solve / total | 140.566 / 216.333 s |
| full true residual | `9.992481e-7` |
| peak incl. RTA | 1.611607 GiB |

### 10.2 Shadow 解释与限定

代码语义上，shadow 每次都执行：原 ILU → 线性 candidate → exact baseline/candidate audit，但最终无条件把原 ILU 写入 global correction。因此 candidate 不会主动改变全局输出。

然而 P0 baseline 为 849 iterations，P3 shadow 为 861 iterations；这与 Task001 历史 baseline 861 相同，说明不同独立运行之间仍有装配顺序、浮点归约或 Krylov 轨迹变化。P3 的 solve 时间还比 P0 低，不能据此声称 shadow “零开销”或更快。可作出的结论仅为：

| 可支持结论 | 不可支持结论 |
|---|---|
| shadow adapter 保持写回 ILU 的代码语义 | P0 与 P3 位级相同 |
| 所有在线候选通过 exact non-degradation | shadow 带来 7.12% 加速 |
| final residual/RTA/closure 通过 | 由一次 noisy wall time 推导稳定 overhead |
| peak 增加约 1.02% | 已完成跨 run deterministic performance qualification |

由于整体 wall time 没有显示 `>10%` 恶化，且 local quality/acceptance 明确为正，任务继续进行一次严格受控的 P4 active one-slab A/B；该决定不等同于 P3 已获得正式加速资格。

---

## 11. P4：one-slab active h5 A/B

### 11.1 全局结果

百分比均以同轮 P0 original ILU baseline 为分母。

| 指标 | P0 baseline | P4 active rank32 slab9 | 变化 | P4 Gate |
|---|---:|---:|---:|---|
| iterations | 849 | 847 | -2 / -0.24% | 不满足至少 5% reduction |
| solve | 151.343 s | 137.261 s | -14.082 s / -9.30% | 不满足独立 10% reduction |
| total | 227.120 s | 191.938 s | -35.182 s / -15.49% | 仅诊断；不是任务独立 signal 条件 |
| full true residual | `9.988413e-7` | `9.985467e-7` | 均通过 `1e-6` | pass |
| peak incl. RTA | 1.595348 GiB | 1.618153 GiB | +0.022804 GiB / +1.43% | pass，低于 +10% |
| one-level applies | 5,094 | 5,082 | -12 | 与 2 次 outer iteration 差一致 |
| operator applies | 2,567 | 2,561 | -6 | 无结构性 action reduction |

### 11.2 slab-9 active diagnostics

| 指标 | 实测 |
|---|---:|
| calls | 5,082 |
| accepted | 5,082 |
| fallback/non-accepted | 0 |
| baseline rho median | 0.533488 |
| candidate rho median / p95 | 0.379118 / 0.531194 |
| adapter accumulated elapsed | 39.349 s |
| adapter mean | 7.743 ms/call |
| checkpoint storage | 5,390,336 B |
| checkpoint SHA-256 | `53314b6939dd9baed3bd60e730e11d1f8a8460b5b36176d8bbe73e9f5cd26a77` |

### 11.3 P4 信号判定

任务书允许两条互斥的成功路径：

| 路径 | 要求 | 实测 | 判定 |
|---|---|---|---|
| A | solve `<=1.05× baseline` 且 iterations reduction `>=5%` | solve 0.907×；iterations reduction 0.24% | fail |
| B | solve reduction `>=10%` | 9.30% | fail，差 0.70 percentage point |

因此 P4 是 `numeric_pass_performance_signal_fail`。9.30% 的单次 solve 下降是弱正信号，但任务书门槛明确，不允许四舍五入成 10%，也不允许使用 total 的 15.49% 下降替代 solve Gate。

---

## 12. 数值正确性、R/T/A 与可信链

### 12.1 四个正式 h5 运行

| run | reported / condensed / full residual | R | T | A_volume | closure error |
|---|---|---:|---:|---:|---:|
| P0 baseline | `9.988413e-7 / 9.988413e-7 / 9.988413e-7` | 0.089021604 | 0.442588273 | 0.468390121 | `-2.182e-9` |
| P0 Task001 negative | `9.885644e-7 / 9.885644e-7 / 9.885644e-7` | 0.089021603 | 0.442588275 | 0.468390119 | `-3.727e-9` |
| P3 shadow | `9.992481e-7 / 9.992481e-7 / 9.992481e-7` | 0.089021604 | 0.442588271 | 0.468390123 | `-1.808e-9` |
| P4 active | `9.985467e-7 / 9.985467e-7 / 9.985467e-7` | 0.089021604 | 0.442588274 | 0.468390120 | `-1.824e-9` |

全部运行保持 reported、condensed true 和 full augmented true residual 一致，official R/T/A 总和在约 `2e-9` 范围内闭合。candidate 没有替代 final global residual 或 official R/T/A 验证。

### 12.2 安全合同

| 保护项 | 状态 |
|---|---|
| exact operator fingerprint | required；mismatch fail closed |
| weights SHA-256 | required；corruption fail closed |
| finite output | every call |
| linearity/determinism | independent validation certified |
| batch consistency | independent validation certified |
| baseline/candidate exact rho | P3/P4 every call |
| non-degradation | P3 recorded；P4 acceptance condition |
| global true residual | every formal h5 run |
| official R/T/A + volume absorption | every formal h5 run |
| periodic/proxy-only audit | 未启用；证据不足，不降低 exact audit 频率 |

---

## 13. 性能与内存根因解释

### 13.1 哪些假设被支持

| 假设 | 结论 | 证据 |
|---|---|---|
| H1：Python CSR row loop 是可消除成本 | 支持 | SciPy mean 仅为 Python 的 7.13%-7.49% |
| H2：固定线性 map 比 nonlinear MLP 更适合 | 支持 local engineering | rank32 通过质量门，mean 仅为 Task001 的 10.39% |
| H3：batch API 可降低调度开销 | API/微基准层支持，owner full batching 未被 P4 解锁 | `predict_many()` batch error=0；只启用一个 slab，未形成多 slab owner batch |
| H4：correction 必须替代昂贵步骤 | 未充分实现/支持 | 当前 P4 仍保留 ILU，并额外做两次 exact action；外层收益只有 2 iterations |

### 13.2 为什么微核成功没有变成全局成功

| 机制 | 影响 |
|---|---|
| 单 slab 收益太弱 | candidate local rho 明显改善，但只减少 2 次 outer iterations |
| 原 ILU 仍保留 | reduced correction 是额外工作，不是 factor/solve replacement |
| every-call exact audit | 每次需要构造 `q` 并计算 `A delta`；安全但仍有成本 |
| two-step smoother 保留 | 没有移除一个完整 inner step 或 Maxwell action |
| owner-rank imbalance/MPI waiting | slab-9 owner 的额外工作会传播为同步等待 |
| full-run noise | 849/861 的轨迹变化和墙钟差异使 9.30% 弱信号不足以成为稳健结论 |

这意味着 Task001 的主要 Python 实现瓶颈已经被消除，但更深层的瓶颈变成了“算法收益幅度不足”：修正一个 slab 的 local residual，不足以显著改变整个 16-slab two-level preconditioner 的谱或外层工作量。

### 13.3 内存

| run / component | peak or storage | vs baseline |
|---|---:|---:|
| P0 baseline peak | 1.595348 GiB | reference |
| Task001 negative peak | 1.650707 GiB | +3.47% |
| P3 shadow peak | 1.611607 GiB | +1.02% |
| P4 active peak | 1.618153 GiB | +1.43% |
| rank32 map | 5.14 MiB | persistent model |
| slab-9 SciPy CSR duplicate | 10.07 MiB | persistent action copy |

内存 guard 通过，但本任务没有销毁 ILU factor，因此不能声称 factor-memory saving。P1 RSS 只提供 repeated-call stability，不是逐 allocation profiler。

---

## 14. 成功路线、失败路线与未运行项

| 路线 | 状态 | 最终处理 |
|---|---|---|
| persistent SciPy CSR | success | 保留为 research local action 基础设施 |
| PETSc owner SeqAIJ comparator | correct but slower here | 保留 benchmark 对照，不选作本候选后端 |
| rank128 linear map | quality positive，performance mean fail | superseded by lower ranks |
| rank96 | local pass | 未选；rank32 更低开销 |
| rank64 | local pass，p95 较抖 | 未选 |
| rank32 | local pass，selected | 用于 P3/P4 |
| P3 every-call shadow | safety positive with run-to-run qualification | 保留诊断，不作加速声明 |
| P4 active slab9 | numeric positive，signal negative | 停止扩大 |
| nonlinear shared trunk Lane C | not run | 线性 Lane B 已过 local Gate，无必要增加复杂度 |
| periodic/proxy audit | not run | every-call exact audit 的证据尚不足以降级 |
| factor removal | not run | reduced action 未快于 ILU，P4 signal fail |
| P5/all-slab | not run by Gate | 禁止 |
| h3/h2 | not run by Gate | 禁止 |

---

## 15. 代码、测试、文档与 artifacts

### 15.1 代码变化

| 文件 | 变化 |
|---|---|
| `src/solvers/local_slab_solver.py` | 新增 persistent SciPy CSR `action` / `action_many` |
| `src/solvers/batched_reduced_smoother.py` | frozen map、checkpoint、batch、fused audit、shadow/active adapter |
| `benchmarks/neural_pc/benchmark_local_action.py` | Python/SciPy/PETSc 真实 slab benchmark |
| `benchmarks/neural_pc/fit_linear_reduced_map.py` | CUDA complex128 POD/ridge offline construction |
| `benchmarks/neural_pc/evaluate_batched_reduced_smoother.py` | local quality/performance Gate 与 Task001 p95 对照 |
| `benchmarks/run_workstation_iterative.py` | 显式 `--linear-reduced-*` research flags |
| `src/test/test_34_para_task002_linear_reduced.py` | compiled action、batch、checkpoint、shadow 合同测试 |
| `src/test/test_26_documentation_contract.py` | 注册 Case091 |

### 15.2 验证

| 检查 | 结果 |
|---|---|
| complete pytest suite | 179 passed，11 skipped |
| final targeted tests | 13 passed |
| Ruff | pass |
| compileall | pass |
| `git diff --check` | pass |
| Case091 JSON parse | pass |

### 15.3 重型 artifacts

| 路径 | 内容 | Git 状态 |
|---|---|---|
| `benchmarks/artifacts/cases/090/h5_datasets/slab_009/` | Task001 dataset/operator | ignored |
| `benchmarks/artifacts/cases/090/h5_checkpoints_v3/slab_009/` | Task001 negative checkpoint | ignored |
| `benchmarks/artifacts/cases/091/checkpoints_rank*/` | rank128/96/64/32 candidates | ignored |
| `benchmarks/artifacts/cases/091/p1_local_action.json` | P1 raw microbenchmark | ignored |
| `benchmarks/artifacts/cases/091/p2_rank*.json` | P2 raw evaluations | ignored |
| `benchmarks/artifacts/cases/091/p0_*.json` | same-round baseline/negative | ignored |
| `benchmarks/artifacts/cases/091/p3_*.json`、`p4_*.json` | formal shadow/active records | ignored |

---

## 16. Provenance 限定

本任务的重型 h5 JSON 均记录了正确分支名，但 metadata 中 `git_commit=null` 且 `git_dirty=true`。P3/P4 运行时实现尚在工作树，之后才在本地提交为 `f34266b`。因此：

| 可用于 | 不可用于 |
|---|---|
| 本分支 research Gate 和停止决策 | clean-final-HEAD performance qualification |
| 证明 P1/P2 局部实现可行 | production canonical record |
| 证明 P4 未达到任务书信号门 | 跨机器或跨 commit 精确性能声明 |
| 指导后续是否值得继续 | 宣称正式 9.30% 可复现加速 |

由于 P4 已失败且 P5 被禁止，没有为追求正面结果而额外重跑或挑选更有利样本。如果未来 review 要求将这些结果升级为 canonical evidence，必须从 clean final implementation HEAD 重新成对运行 baseline/candidate，并保留明确 commit SHA、host attestation 和同 sampler 记录。

---

## 17. 最终决策与保留边界

| 对象 | 决定 | 原因 |
|---|---|---|
| SciPy local action infrastructure | 保留在当前研究分支 | 正确且显著加速，可复用 |
| frozen linear map/checkpoint contract | 保留在当前研究分支 | 固定线性、可审计、local Gate 通过 |
| batch API/fused audit telemetry | 保留 | 为未来真正 owner batching 提供基础 |
| rank32 checkpoint | 仅保留 ignored artifact | 绑定当前 slab/operator，不提交大型文件 |
| P4 active profile | 不提升 ordinary default | performance signal fail |
| all-slab rollout | 拒绝/未运行 | P4 Gate 禁止 |
| h3/h2 | 保持锁定 | 没有 h5 全局加速资格 |
| master/remote 操作 | 不执行 | 用户明确只允许本地 commit |

最终 classification 保持：

```text
local_microkernel_success_global_signal_insufficient
```

这不是“线性 reduced map 完全失败”，也不是“h5 加速成功”。准确含义是：局部算法与微核研究取得可复用成功，但它尚未改变全局求解器的工程结论。

---

## 18. 局限与尚未回答的问题

| 局限 | 影响 |
|---|---|
| 单一物理 RHS | 不能推断多入射角、多波长、多几何泛化 |
| 只主动启用 slab 9 | 不能推断多 slab interaction |
| 当前 MPI4 partition | operator fingerprint/owner ordering 改变时模型不可直接复用 |
| PETSc 3.19.6 complex ABI | 不能外推 PETSc 3.24 或其他 sparse backend 性能 |
| 每次 exact audit | 保守但仍昂贵；proxy audit 尚未资格化 |
| ILU 未被替代 | 没有 factor memory/solve removal 收益 |
| full-run wall-time noise | 9.30% 弱信号不稳健 |
| dirty runtime metadata | 不能作为 clean-final-HEAD canonical performance evidence |
| 未实现真正多 slab owner batch | `predict_many()` API 已有，但 P4 停机门阻止进一步集成 |

尚未回答的核心问题不是“能否继续把 rank 调得更低”，而是“能否用一次 reduced action 真正替代一个昂贵 ILU/inner smoother/Maxwell action，同时保持足够谱改善”。本任务现有数据不能肯定回答。

---

## 19. 下一步决定及因果依据

1. **当前任务停止。** P4 两条 performance signal 均失败，不能运行 P5、h3、h2。
2. **不继续堆叠 nonlinear network。** 固定线性 Lane B 已通过 local Gate，说明非线性不是当前首要缺口；首要缺口是全局迭代收益。
3. **若未来重开，先设计“替代”而非“叠加”。** 候选必须移除一个真实昂贵步骤，例如 second local/inner correction 或 selected ILU factor，而不是继续保留 ILU、two-step smoother 和 every-call extra correction。
4. **重开前先做 clean paired h5。** 必须从 clean final HEAD 成对复跑 baseline/candidate，消除当前 dirty provenance 和运行间噪声限定。
5. **只有新 one-slab h5 重新通过信号门，才允许 owner multi-slab batch。** 不能因 `predict_many()` API 已存在就跳过全局 Gate。

---

## 20. 证据索引

| 类型 | 入口 |
|---|---|
| Task002 任务书 | `../task.md` |
| Task001 审阅 | `../../para_task001_neural_local_pc_acceleration/review_report_v1.md` |
| 最终决策 | `decision.md` |
| 实验矩阵 | `experiment_matrix.csv` |
| P1 微核摘要 | `microkernel_breakdown.csv` |
| runtime 拆解 | `runtime_breakdown.csv` |
| 内存 | `memory_report.md` |
| dataset/model provenance | `model_and_dataset_provenance.md` |
| changed files | `changed_files.md` |
| Case091 | `../../../benchmarks/cases/091_batched_neural_smoother_acceleration/README.md` |
| heavy evidence | `../../../benchmarks/artifacts/cases/091/`（Git ignored） |
| core implementation | `../../../src/solvers/batched_reduced_smoother.py` |
| local action | `../../../src/solvers/local_slab_solver.py` |
| formal runner | `../../../benchmarks/run_workstation_iterative.py` |
