# Task034：WSL 工作站迁移、高内存参考、自适应压缩与资源重校准

## 0. 任务身份

```text
Task ID = Task034
recommended execution branch = codex/20260717-task34-workstation-wsl-adaptive-scalability
base = 含本任务书的最新 clean origin/master
execution host = 256 GiB 级工作站上的 WSL2 Ubuntu
container policy = native WSL execution；本任务不以 Docker 作为正式运行环境
ordinary default = unchanged
primary wavelength = 13.5 nm
primary material = 当前已验证 Si 复折射率
primary solver family = Hybrid FEM–Modal + staged full3D direct references
heavy-run policy = one heavy case at a time
0.7 nm PDE = prohibited in Task034
```

Task034 承接 Task033 Review V6 明确移交的 fixed-p conforming graded-h / adaptive、实测压缩率和更新后的 0.7 nm 资源评估；同时利用新工作站完成 WSL 原生环境资格化、合并后硬化、p3/h3 更细离散参考和 p4/h5 受控计算。

Task034 不是把 14 GiB 机器上的资源 Gate 简单放宽到 256 GiB，也不是用更大内存掩盖当前模态核心的扩展性问题。任何重型运行都必须先完成环境、源码、内存、swap、磁盘和候选级预测 Gate。

开始前必须阅读：

```text
docs/repository_work_principles.md
docs/markdown_rendering_standard.md
docs/task_retrospective_standard.md

docs/task033_high_order_floquet_hybrid_hp_adaptivity/task.md
docs/task033_high_order_floquet_hybrid_hp_adaptivity/review_report_v6.md
docs/task033_high_order_floquet_hybrid_hp_adaptivity/response_v7.md
docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/summary.md
docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/task33_completion_matrix.md
docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/test_summary.md
docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/memory_prediction_and_launch_decisions.md
docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/reduced_equal_accuracy_phaseD.md

benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/README.md
benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/task033_reduced_scope_completion.json
benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage5_equal_accuracy/reduced_equal_accuracy_summary.json

docs/project_service_requirements_and_forward_model_roadmap.md
notes/theory/high_order_hcurl_floquet_and_hp_adaptivity.md
notes/theory/hybrid_fem_modal_domain_decomposition.md
```

Codex 不得删除、覆盖或改写本 `task.md`。对任务书的解释、实现偏差或补充必须写入新的 `response_vN.md`。

---

# 1. 从最新 master 建立执行分支

ChatGPT 只把任务书放入 `master`，不创建执行分支。Codex 必须在工作站 WSL Ubuntu 中执行以下流程：

```bash
git remote -v
git fetch origin --prune
git switch master
git pull --ff-only origin master
git status --short --untracked-files=all
git rev-parse HEAD
git rev-parse origin/master
```

只有在以下条件全部满足时才能创建分支：

```text
HEAD == origin/master
tracked worktree clean
不存在 nonignored untracked file
本 task.md 可读
Task033 Review V6、response_v7 和 completion record 可读
```

然后由 Codex 创建并推送：

```bash
git switch -c codex/20260717-task34-workstation-wsl-adaptive-scalability
git push -u origin codex/20260717-task34-workstation-wsl-adaptive-scalability
```

不得直接在 `master` 上开发。不得从 Task033 research branch 继续提交，也不得整体 cherry-pick Task033 中被 Review V6 排除的 adaptive、graded mesh、1 TiB 或 full campaign 实现。

Codex 必须在：

```text
docs/task034_workstation_wsl_adaptive_scalability/outcomes/environment_and_base.md
```

记录：

- Task033 selective-merge commit；
- Task034 branch base SHA；
- `origin/master` SHA；
- 当前分支名；
- worktree clean attestation；
- WSL、Ubuntu、kernel、CPU、NUMA、内存、swap 和文件系统；
- Python、MPI、PETSc、SLEPc、MUMPS、DOLFINx、Basix、UFL、petsc4py、slepc4py 版本；
- PETSc complex128 状态；
- 原生 WSL 环境的安装来源与可复现命令；
- 未使用 Docker 的明确身份。

---

# 2. 已接受基线与本任务不得改写的结论

Task033 已选择性合入 `master`。以下结论是 Task034 的输入，不得在没有新证据时改写。

| 路径 | 已接受结果 | 数据身份 | Task034 用途 |
|---|---:|---|---|
| p3/h5 full3D | 145,863 Nédélec DoF；7.781 GiB；103.59 s；真残差 `5.442e-12` | measured | 旧环境 finer discrete anchor |
| p3/h5 Hybrid M160 | local rows 21,847 × 2；2.618 GiB；111.94 s；真残差 `2.343e-12` | measured | 同阶 closure anchor |
| p3/h5 Hybrid-full3D | max R/T/A delta `1.214e-7`；五平面 E/H 最大相对 L2 `1.100e-5 / 1.098e-4` | measured | WSL portability 与 closure Gate |
| p3/h10 | 资源安全但 12 项物理比较全部劣于 p2/h3 | measured negative | 不再作为等精度候选 |
| p3/h7.5 | fixed-p equal-accuracy clear success with qualifications | measured positive | 新 reference 下重新排名 |
| p4/h5 full3D | assembly 339,892 DoF、155,205,040 NNZ；12.616 GiB 后受控停止 | measured resource negative | 新工作站 staged restart 输入 |
| p4/h5 Hybrid M160 | 旧预测中心/上界 37.038/42.594 GiB | predicted negative on old host | 新工作站重新测量，旧模型不作权威 |
| variable-p H(curl) | native capability fail closed | audited negative | Task034 不自行发明 unequal-p 约束 |
| adaptive / 1 TiB update | transferred | not run | Task034 正式承接 |

Task034 的新环境和新硬件可能改变内存与 wall time，但不能仅因机器更大就声称连续解收敛、0.7 nm 可行或 scalable modal core 已完成。

---

# 3. 总目标

Task034 必须完成或形成明确 fail-closed 结论的目标为：

1. 证明代码可在不依赖 Docker 的 WSL Ubuntu 原生环境中稳定运行；
2. 修复 Task033 selective merge 后识别出的缓存、诊断通信、共享主机 swap、源码洁净度和 evidence-to-master 绑定问题；
3. 在当前 master 数值路径上复现 p3/h5 与 p3/h7.5 关键锚点；
4. 分阶段尝试 p3/h3 full3D 与 Hybrid，建立比 p3/h5 更细的独立离散参考；
5. 分阶段尝试 p4/h5 Hybrid 与 full3D，不允许无 Gate 直接因子化；
6. 从 clean master 重新实现 fixed-p conforming graded-h / adaptive mechanism；
7. 测量 p2 与 p3 自适应在相同物理误差下的 local FE 压缩率；
8. 用实测结果重校准 256 GiB、1 TiB、2 TiB 和 0.7 nm 的分组件资源模型；
9. 明确区分 local 3D FEM 可行性与现有 replicated modal core 可行性；
10. 形成下一 scalable modal core 任务的输入，但本任务不实施完整替代架构。

---

# 4. 非目标与禁止项

Task034 不做：

- 0.7 nm 正式 Maxwell PDE；
- p4/h3 或更细 p4 目标计算，除非新的 ChatGPT review 明确解锁；
- arbitrary cellwise variable-p H(curl)；
- hanging-node H(curl) 自定义约束；
- 非匹配 mortar；
- 最终 distributed spectrum slicing / streamed modal core 的完整实现；
- 最终 matrix-free Hybrid 迭代求解器；
- 没有 defect 或 nonuniform end geometry 时的 interface-buffer 工程优化；
- 以 WSL 原生环境为理由降低 true residual、R/T/A、场、接口或 source identity Gate；
- 自动并发运行多个重型案例；
- 把 Windows pagefile、Linux swap、MUMPS OOC scratch 混写为同一种资源；
- 把预测写成 measured；
- 将受控资源负结果包装为数值方法失败；
- 在最终 review 前修改 ordinary solver default。

Task033 中 interface buffer 继续等待 defect/nonuniform-end geometry；variable-p 继续 fail closed。这两个边界不属于“未完成所以必须强行运行”，而是经过审查保留的适用性约束。

---

# 5. Phase A：WSL Ubuntu 原生环境资格化

## 5.1 环境审计

Codex 必须先审计现有 WSL 环境，不得第一步就重装全部依赖。至少记录：

```bash
uname -a
cat /etc/os-release
python --version
which python
which mpiexec
mpiexec --version
lscpu
numactl --hardware || true
free -h
cat /proc/meminfo
cat /proc/swaps
ulimit -a
df -hT
df -ih
mount
```

并通过 Python 实际导入并记录：

```text
mpi4py
petsc4py
slepc4py
dolfinx
basix
ufl
gmsh
numpy
scipy
```

必须程序化验证：

```text
PETSc.ScalarType == complex128
PETSc.IntType 位宽已记录
SLEPc PEP 可创建
MUMPS factor solver 可选择
MPI1/MPI2/MPI4 能启动
每个 rank 的 Python 与库路径一致
不存在混用 Windows Python、WSL Python 或多个 MPI ABI
```

如环境缺包或 ABI 冲突，Codex可以修复 WSL 用户环境，但必须：

- 记录原状态；
- 记录每条安装或修复命令；
- 不静默删除用户已有环境；
- 不用 Docker 作为“原生环境通过”的替代；
- 修复后重新生成完整版本清单。

## 5.2 原生 smoke 与回归层级

按以下顺序执行：

1. pure Python / documentation / schema tests；
2. DOLFINx import 与小型 serial tests；
3. MPI2/MPI4 高阶 Floquet microfixture；
4. p1/p2 legacy anchor；
5. p3/p4 Case090 小型 fixture；
6. matching trace MPI2/MPI4；
7. 小型 QEP/PEP + MUMPS；
8. 小型 Hybrid algebraic closure。

在 Phase A 和 Phase B 完成前，不得运行 p3/h5、p3/h3 或 p4/h5 重型案例。

## 5.3 WSL 环境通过标准

必须同时满足：

- 所有必需 import 成功；
- complex128；
- MPI1/2/4 行为一致；
- MUMPS 与 SLEPc PEP 可用；
- p1/p2 ordinary anchor 不回归；
- p3/p4 microfixture 的解析、Floquet、orientation、cache 和 MPI Gate 通过；
- 没有 Docker runtime 参与；
- WSL 原生测试命令可由一份脚本或 Make/CLI 入口重复执行。

输出：

```text
outcomes/wsl_environment_qualification.md
outcomes/wsl_environment_qualification.json
```

若 Phase A 失败，停止所有大算例，先提交环境负结果和修复建议。

---

# 6. Phase B：合并后硬化与重大风险修复

## 6.1 高阶 Floquet topology cache 生命周期

当前模块级 `_TOPOLOGY_CACHE` 最多保留 8 个 `FloquetTraceTopology`，而 topology 保存 `mesh_reference` 与 `space_reference` 强引用。Task034 必须消除跨案例长期保留大 mesh/function-space 的风险。

允许方案：

- solver/context 局部 cache；
- weak-reference-aware cache；
- 不保存 mesh/space 强引用的稳定身份；
- 明确的 `clear_floquet_topology_cache()` + 生命周期管理。

必须同时保留：

- 同一 mesh/function space 仅改变 Bloch phase 时 cache hit；
- topology 与 phase 分离；
- MPI 所有 rank cache identity 一致；
- 不因对象 `id` 重用命中旧 topology；
- ordinary p1-p4 结果不变。

测试至少包括：

1. 同网格多角度 cache hit；
2. 不同网格不得误命中；
3. 清理后 cache empty；
4. 缓存不再阻止旧 mesh/space 被释放；
5. 连续多案例子进程 RSS 不呈现由 cache 强引用导致的阶梯式增长；
6. MPI2/MPI4 cache hit/miss 一致。

## 6.2 去除 active-column 统计中的全局 Python allgather

当前 `_global_active_column_count()` 会把所有 rank 的 active column ID 复制到所有 rank。Task034 必须改成真正分布式计数，不得为了诊断统计形成全局 Python `set`。

可选实现：

- distributed PETSc marker Vec；
- 按 column ownership 的本地唯一计数 + owner reduction；
- 稀疏矩阵转置后的 owned-row 非空计数。

验收：

- 结果与旧小 fixture 完全一致；
- 测试中 monkeypatch/拦截 Python object `allgather` 后仍通过；
- 不 gather 全部 column IDs；
- 记录通信量和额外内存复杂度；
- 对百万级 synthetic interface 的统计内存保持随本地 ownership 增长。

## 6.3 WSL/共享主机 watchdog 的内存与 swap 权威

Task033 full3D watchdog 把宿主全局 `pswpin/pswpout` 也作为 formal no-swap 硬 Gate。共享主机或 WSL VM 中，其他进程的换页会造成误判。

Task034 必须定义三层身份：

```text
job/process-tree authority
job cgroup authority（若存在专用 cgroup）
WSL VM / host-global diagnostic
```

formal no-swap 必须优先由本 job 决定：

- 进程树所有 worker 的 `VmSwap` 或可辩护等价量为零；
- 若存在专用 cgroup，则该 cgroup `memory.swap.current` 为零；
- host/WSL 全局 `pswpin/pswpout` 仅作 diagnostic，不得因其他任务活动单独判本 job 失败。

不得把：

```text
MUMPS OOC scratch
Linux swap
Windows pagefile
```

混为同一指标。MUMPS OOC 可以作为显式 profile 使用，但必须记录 scratch 路径、峰值、剩余空间和清理状态。

## 6.4 完整 source-clean 语义

所有 formal runner 和 watchdog 必须统一检查：

```bash
git status --short --untracked-files=all
```

或语义等价实现。

要求：

- tracked 修改导致 fail；
- nonignored untracked 文件导致 fail；
- ignored `results/`、`benchmarks/artifacts/` 和合法 scratch 不导致 fail；
- run 前后 HEAD、tracked 状态和 nonignored untracked 状态一致；
- 不允许内层 runner 使用 `--untracked-files=no` 后仍声称完整 clean。

## 6.5 evidence-to-current-master numerical blob checker

Task033 completion record 绑定 evidence 和 merge manifest，但未直接证明当前 checkout 的全部物理数值 kernel blob 与正式 evidence source 一致。

Task034 必须新增 fail-closed checker，至少覆盖：

```text
src/common/config_3d.py
src/common/analytic_fields_3d.py
src/common/high_order_quadrature.py
src/geometry/mesh_builder_3d.py
src/constraints/floquet_3d.py
src/constraints/floquet_3d_high_order.py
src/constraints/high_order_floquet_trace.py
src/constraints/cross_section_floquet.py
src/modes/cross_section_spaces.py
src/modes/quadratic_beta_eigenproblem.py
src/modes/mode_classification.py
src/coupling/hybrid_internal_modes.py
src/coupling/modal_trace_projection.py
src/postprocessing/hybrid_field_reconstruction.py
src/solvers/common_3d_case_flow.py
src/solvers/common_3d_fields.py
src/solvers/common_3d_postprocess.py
src/solvers/dtn_port_3d.py
src/solvers/hybrid_local_dtn.py
src/solvers/hybrid_fem_modal_schur_direct.py
src/solvers/common_3d_solve.py
```

允许 Task034 自己修复的 diagnostic/lifecycle/watchdog 文件发生变化，但必须逐项分类：

```text
numerical kernel unchanged
numerical kernel intentionally changed and requires PDE rerun
diagnostic only
lifecycle only
resource-monitoring only
documentation/test only
```

若任何 Maxwell、Floquet、QEP、Hybrid coupling、physical reconstruction、DtN 或 official postprocess 数值 kernel 改变，则相应 Task33 PDE evidence 不得直接复用，必须在 Phase C 重新运行对应 anchor。

## 6.6 ordinary default 与 API 边界

所有新 cache、watchdog、WSL profile、p3/h3、p4 和 adaptive 路径保持显式 opt-in。Task034 最终审查前不得改变普通 `main` preset、默认 direct profile、默认 mesh 或默认后处理身份。

输出：

```text
outcomes/post_merge_hardening_audit.md
outcomes/numerical_blob_compatibility.json
```

---

# 7. 统一工作站资源 Gate

## 7.1 有效内存上限

工作站标称 256 GiB 不等于求解器可以使用全部内存。默认用户上限为 220 GiB，但必须按现场数据缩紧：

$$
M_{\mathrm{effective}}
=
\min\left(
M_{\mathrm{user}},
0.85 M_{\mathrm{WSL}},
M_{\mathrm{available}}-24\ \mathrm{GiB}
\right).
$$

其中：

```text
M_user default = 220 GiB
M_WSL = WSL Linux 可见 MemTotal
M_available = 每个重型运行前刷新 MemAvailable
```

若任一权威不可读、`M_available <= 24 GiB` 或 effective limit 非正，不得启动。

默认阈值：

$$
M_{\mathrm{warning}}=0.80M_{\mathrm{effective}},
$$

$$
M_{\mathrm{terminate}}=0.95M_{\mathrm{effective}}.
$$

Codex 可以根据工作站管理员限制进一步收紧，不得放宽到占满整机。

## 7.2 运行规则

- 一次只运行一个 heavy case；
- `OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`，除非独立线程资格化；
- MPI rank 数先从 4 开始，随后按 NUMA/内存证据决定 8/16，不能假设更多 rank 自动省内存；
- 每次运行前刷新 MemAvailable、process tree、swap、磁盘空间和 source identity；
- 每次运行中持续采样；
- 达 termination 立即终止完整 process group；
- zero job swap 是 formal positive 的硬 Gate；
- OOM kill 不允许作为正常停止方式；
- controlled resource negative 是合法结论。

## 7.3 因子化与 OOC

大 direct 参考必须分为：

```text
assembly-only
factorization-only / KSPSetUp-only
full solve
```

不得从 assembly-only 直接跳到 full solve。

MUMPS OOC 仅在以下条件满足时允许作为独立 profile：

- in-core 预测未过 Gate或 OOC 有明确研究价值；
- scratch 位于本地高速 Linux 文件系统，不在慢速 Windows `/mnt/c`；
- 可用 scratch 至少为预测上界的 2 倍并额外保留 100 GiB；
- scratch、时间和内存单独记录；
- OOC 成功不等于 in-core 成功；
- 结束后验证 scratch 清理。

---

# 8. Phase C：WSL 原生环境下复现 Task33 锚点

完成 Phase A/B 后，在当前 Task034 clean SHA 上依次运行：

1. p3/h7.5 full3D；
2. p3/h7.5 Hybrid M120/M160；
3. p3/h5 full3D；
4. p3/h5 Hybrid M160；
5. p3/h5 same-degree closure；
6. p3/p4 matched trace MPI2/MPI4；
7. 必要的 QEP/left-right/biorthogonality anchor。

目标不是要求内存和 wall time 与旧 Docker 完全相同，而是验证 WSL native portability 和物理一致性。

最低 Gate：

- full explicit true residual `<=1e-9`；
- official R/T/A 仅从通过 residual 的场产生；
- p3/h5 Hybrid-full3D 延续 Task33 的 16 项 closure Gate；
- 新旧环境 R/T/A 绝对差不超过 `1e-6`，若超过必须解释并做网格/版本/求解器定位；
- significant diffraction complex amplitudes 的相位和幅值保持在已审查误差量级；
- selected-plane E/H 与接口 E/H 不出现数量级回归；
- QEP beta MPI drift 和 biorthogonality 不回归；
- zero job swap；
- source before/after clean and stable。

如由于 DOLFINx/PETSc/SLEPc 版本变化出现小差异，必须以解析 fixture、同网格 full3D/Hybrid closure 和完整 observable vector 判断，不能只用单个 R/T 值接受。

输出：

```text
outcomes/task033_anchor_reproduction_wsl.md
benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/wsl_anchor_summary.json
```

---

# 9. Phase D：p3/h3 更细独立离散参考

p3/h3 的目标是减少 p3/h7.5 与 p3/h5 同阶相关性造成的 reference bias，并重新判断 p2/h3、p3/h7.5 的等精度结论。它仍不是 continuum reference。

## 9.1 D0：预测与 assembly-only

必须先：

1. 根据 p3/h10、h7.5、h5 的新 WSL 实测重新拟合 rows、NNZ、assembly 和 factor inventory；
2. 生成候选级 center/upper；
3. 运行 p3/h3 assembly-only；
4. 记录 base/augmented/final matrix inventory；
5. 更新 factorization 预测；
6. 决定是否进入 KSPSetUp-only。

旧 Task33 高阶资源模型不得作为单独启动权威。

## 9.2 D1：factorization-only

只有 assembly record、现场 authority、磁盘和预测同时通过才允许启动。

必须在 `KSPSetUp` 完成后、正式 RHS solve 前形成独立记录：

- factor type / MUMPS profile；
- factor inventory；
- peak RSS/PSS；
- OOC scratch（若使用）；
- setup time；
- zero job swap；
- 是否安全解锁 full solve。

如果 factorization 达到 termination，则受控停止并保存 negative，不得继续 full solve。

## 9.3 D2：full solve 与 reference export

通过 D1 后才允许 full solve。必须导出与 Task033 p3/h5 reference 相同的：

- official R/T/A；
- volume absorption；
- significant orders 的 power 与 complex amplitude；
- 五个固定平面 E/H；
- 上下接口切向 E/H；
- full true residual；
- source、环境、memory、swap、time；
- compact reference archive hash。

## 9.4 D3：p3/h3 Hybrid funnel 与同阶闭合

依次运行：

```text
M80
M120
M160
M240 only if M120->M160 fails solely on modal convergence
```

只有每个 M 的代数、QEP、接口、R/T/A、field、volume absorption 和 true residual Gate 通过，才能用于 funnel。

若 p3/h3 full3D reference 存在，必须做 same-degree Hybrid closure。若 full3D 被资源 Gate 阻止，则 p3/h3 Hybrid 可以形成 measured engineering result，但不得声明 same-degree closure。

## 9.5 D4：重新排名

相对 p3/h3 finer discrete reference，重新计算：

- p2/h3；
- p3/h7.5；
- p3/h5；
- p3/h3 Hybrid selected M。

比较向量必须沿用 Task033 D1：

```text
R/T/A
A_volume
五平面 E/H
上下接口切向 E/H
significant-order power max/RMS
significant-order complex amplitude max/RMS
full true residual
```

最终分类必须明确：

```text
p3_h3_reference_available = true/false
p3_h5_to_h3_grid_change = measured/not_run
p3_h7p5_equal_accuracy_under_new_reference = pass/fail/not_run
p2_h3_equal_accuracy_under_new_reference = pass/fail/not_run
grid_convergence_proven = false unless independently justified
continuum_reference = false
```

若 p3/h3 因资源 Gate 不可运行，可以条件运行 p3/h4 assembly 或 reference 作为校准，但不得把 p3/h4 冒充已完成的 p3/h3。

输出：

```text
outcomes/p3_h3_reference_and_reranking.md
benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/p3_h3_reference_summary.json
```

---

# 10. Phase E：p4/h5 工作站受控计算

用户已明确允许在新工作站尝试 p4，但该许可不取消候选级 Gate。

## 10.1 E0：重新 assembly calibration

在 Task034 hardening 后重新运行 p4/h5 assembly-only，不能直接复用旧 12.616 GiB 作为新机器 factorization 许可。

记录：

- Nédélec DoF；
- Floquet constraints；
- base/augmented/final rows 与 NNZ；
- PETSc matrix memory；
- process-tree/cgroup/WSL memory；
- assembly time；
- zero job swap；
- 新 factor prediction。

## 10.2 E1：p4 QEP/Hybrid M funnel

先确认 p4 QEP、four-mode near-degenerate trace 和 matched trace anchors 在 WSL 通过，再运行：

```text
M80
M120
M160
M240 only if formally required
```

旧 42.594 GiB upper 只作历史参考，必须以 WSL watchdog 实测为权威。

## 10.3 E2：full3D factorization-only

只有 E0 预测通过统一工作站 Gate时启动。不得与 p4 Hybrid 或 p3/h3 同时运行。

如 in-core 不安全，可按第 7.3 节单独尝试 OOC；两条 profile 必须分别记录。

## 10.4 E3：full solve 与 same-degree closure

只有 factorization-only 通过才运行 full solve。成功后：

- 生成 p4/h5 full3D reference；
- p4 Hybrid 运行相同 observable closure；
- 比较 p4/h5、p3/h5 和 p3/h3 的精度/资源；
- 判断 p4 是否提供足够工程收益。

允许的最终结论包括：

```text
p4_same_degree_closure_pass
p4_hybrid_pass_full3d_resource_negative
p4_factorization_resource_negative
p4_modal_capacity_negative
p4_no_clear_accuracy_benefit
```

任何负结果都必须保留。不得运行 p4/h3 或更细候选。

输出：

```text
outcomes/p4_h5_workstation_study.md
benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/p4_h5_workstation_summary.json
```

---

# 11. Phase F：fixed-p conforming graded-h 与自适应压缩

## 11.1 从 clean master 重新实现

Task033 research branch 中被排除的：

```text
benchmarks/run_task033_adaptive_mesh.py
src/geometry/task033_periodic_graded_mesh.py
相关未资格化测试和计划
```

不得整体 cherry-pick 或直接提升为 production。可以只读参考其失败经验，但 Task034 必须在当前分支重新设计、实现、测试和记录。

## 11.2 第一层：conforming graded-h mechanism

第一版固定 p，不做 variable-p。必须满足：

- 六面体 conforming mesh；
- 无 hanging nodes；
- x/y 周期配对区域拓扑完全同步；
- 周期 mate cell 同步 refinement；
- 双周期角点、边、面仍可由已资格化 Floquet backend 处理；
- 材料界面精确贴合；
- bottom/top local 3D region 可独立配置但接口 trace 一致；
- ordinary uniform mesh 不改变；
- mesh plan 有可重复 hash；
- 网格质量、尺度分布、element counts 和 periodic pairing diagnostics 被记录。

首先只在 p2/h5 级别验证机制，不以精度压缩成功作为第一步要求。

## 11.3 第二层：p2/h3 measured compression

以 uniform p2/h3 为 baseline，构造至少三档 conforming graded mesh：

```text
conservative
balanced
aggressive
```

每档运行相同 Hybrid M funnel 和物理 Gate，测量：

- local FE DoF；
- local system rows；
- total rows；
- assembled NNZ；
- factor inventory；
- peak memory；
- wall time；
- M requirement；
- R/T/A、A_volume、fields、interfaces 和 orders error vector。

## 11.4 第三层：真实 adaptive loop

在 graded mechanism 通过后，建立 fixed-p adaptive loop。指标至少包含可辩护的 Maxwell 局部残差/界面跳量，并解释 complex lossy H(curl) 问题中的定义和尺度归一化。

不得只按几何距离手工细化后称为“自适应”。几何先验可以作为初始网格或权重，但每轮 refinement 必须由场相关 indicator 驱动并记录。

建议元素指标结构：

$$
\eta_K^2
=
\eta_{K,\mathrm{volume}}^2
+
\eta_{K,\mathrm{curl\ jump}}^2
+
\eta_{K,\mathrm{material/interface}}^2
+
\eta_{K,\mathrm{goal}}^2.
$$

具体形式必须在 theory/outcomes 中推导，并通过 manufactured/analytic fixture、uniform refinement trend 和 observable error reduction验证。若无法为某一项建立可靠离散计算，必须标记 experimental，不得伪装成严格 estimator。

## 11.5 多参数 robust common mesh

自适应最终不能只服务一个 10° S 案例。至少使用：

```text
1° / 5° / 10° grazing
S / P
```

先在低成本轮次生成各参数 indicator，再以：

$$
\eta_K^{\mathrm{robust}}
=
\max_j \eta_K(\boldsymbol\mu_j)
$$

或经审查的等价 aggregate 形成公共网格。公共网格必须再对六个参数点运行验证，不得用各自独立网格冒充 common-mesh 成功。

## 11.6 p3 fixed-p adaptive

p2 mechanism 与 p2/h3 compression 完成后，选择：

```text
p3/h7.5
或 p3/h5
```

作为 p3 fixed-p adaptive baseline。选择依据必须来自 p3/h3 reranking、资源和精度，不得预设 p3 必然更优。

## 11.7 同误差与压缩分类

候选只有在规定的全部物理比较不劣于 baseline tolerance 时才计算压缩倍数。

| 同误差 local FE DoF 压缩 | 分类 |
|---:|---|
| `<1.3x` | weak signal |
| `1.3–2x` | useful engineering positive |
| `2–3x` | clear success |
| `>=3x` | strong engineering success |
| `>=5x` | preferred strong target |

必须同时报告 rows、NNZ、factor、memory、time 和模式数；不能只报告 mesh elements 或 local FE DoF。

## 11.8 自适应停止条件

出现任一情况时停止当前 lane：

- periodic topology 不同步；
- hanging node 或未经资格化约束出现；
- mesh quality 低于预设 Gate；
- true residual 不通过；
- official R/T/A 不可生成；
- 任一关键 observable 超过等精度容差；
- refinement 后 error 不降且成本持续上升；
- 内存/磁盘/swap 达 termination；
- common mesh 对代表参数失效。

负结果仍需保存，不得通过放宽阈值制造压缩成功。

输出：

```text
outcomes/adaptive_mechanism.md
outcomes/adaptive_compression.csv
outcomes/adaptive_compression.json
benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/adaptive_summary.json
```

---

# 12. Phase G：资源模型重校准与 0.7 nm 更新

Task034 必须废止把 Task33 旧 launch guard 直接外推到 1 TiB/0.7 nm 的做法。

新模型必须分组件：

```text
local 3D FE assembly
local 3D factorization / iterative state
QEP coefficient matrices
shift-invert factorization
right/left mode vectors
full/reduced mode duplication
interface projection O(N_interface M)
replicated dense modal arrays O(M^2)
Hybrid Schur/dense multi-RHS
field reconstruction
MPI/process overhead
```

至少使用以下实测校准点：

- p2/h5、p2/h3；
- p3/h10、p3/h7.5、p3/h5；
- p3/h3（若运行）；
- p4/h5 assembly/Hybrid/full3D（按实际可得）；
- p2/p3 adaptive candidates；
- M80/M120/M160/M240 中实际运行项。

对以下波长生成分组件预测：

```text
13.5 nm
5 nm
2 nm
1 nm
0.7 nm
```

并分别给出：

```text
256 GiB
1 TiB
2 TiB
```

的 candidate classification。

必须明确：

1. local FEM 在自适应和低存储目标下是否可能进入预算；
2. 现有 modal core 是否因 retained mode vectors、shift-invert 或 replicated M² 先失效；
3. 哪个组件首先越过预算；
4. 需要多少自适应压缩与 modal-core 压缩才能进入预算；
5. 哪些是 measured、derived、predicted 和 unknown；
6. 该预测不等于 0.7 nm PDE 已通过。

若 predicted mode count 使单个 complex128 `M×M` 对象接近或超过预算，必须直接标记 current replicated modal layout infeasible，不得通过省略其他对象制造可行性。

输出：

```text
outcomes/resource_model_v2.md
outcomes/resource_model_v2.csv
outcomes/resource_model_v2.json
outcomes/0p7nm_workstation_and_tib_assessment.md
```

---

# 13. Formal evidence 与 benchmark 目录

新 case：

```text
benchmarks/cases/092_workstation_wsl_adaptive_scalability/
```

Git 中只允许轻量：

- JSON/CSV summary；
- source/environment identity；
- compact residual history；
- hash-bound descriptors；
- test records；
- launch/stop decision；
- resource model。

重型内容必须保存在 ignored 路径：

```text
benchmarks/artifacts/cases/092/
results/
```

不得提交：

- mesh；
- VTU/XDMF/HDF5；
- full field arrays；
- matrices/factors；
- OOC scratch；
- raw PEP cache；
- 完整 memory timeline；
- 大型 stdout/log。

每个正式 record 必须绑定：

- clean source SHA；
- source before/after；
- WSL environment ID；
- Python/MPI/PETSc/SLEPc/DOLFINx versions；
- command；
- MPI ranks 和 thread counts；
- process-tree/cgroup/WSL memory authority；
- job swap；
- artifact hash；
- true residual；
- official-result identity；
- negative/positive classification。

---

# 14. 测试要求

至少新增或更新测试覆盖：

1. WSL native environment probe schema；
2. cache 不保留旧 mesh/space 强引用；
3. cache clear 与同网格 phase-only hit；
4. 对象 `id` 重用不得误命中；
5. active-column count 不使用 Python object allgather；
6. shared-host global swap 变化不单独否决 clean job；
7. job process-tree swap 非零必须否决；
8. tracked 或 nonignored untracked source 必须否决 formal run；
9. evidence-to-current numerical blob mismatch 必须 fail closed；
10. ordinary p1/p2/p3/p4 Floquet 回归；
11. p3/h3 staged launch gates；
12. p4 assembly/factor/full-solve gates；
13. periodic synchronized graded mesh；
14. 故意破坏一侧 periodic refinement 必须失败；
15. adaptive indicator finite、nonnegative、MPI consistent；
16. common robust mesh identity；
17. equal-accuracy aggregate 不得漏掉任一 observable；
18. resource model measured/derived/predicted identity；
19. 0.7 nm record不得声称 PDE pass；
20. 文档公式和表格渲染合同。

最终至少运行：

```text
focused pure-Python tests
DOLFINx native WSL tests
MPI2 tests
MPI4 tests
Task032 anchors
Task033 anchors
Task034 new tests
Ruff
compileall
git diff --check
git status --short --untracked-files=all
```

测试命令和结果写入：

```text
outcomes/test_summary.md
```

---

# 15. 阶段执行与自动停止顺序

Codex 可在 Gate 通过后自动进入下一阶段，无需每个小步骤询问用户；但必须遵守以下顺序：

```text
Phase A WSL environment
-> Phase B hardening
-> Phase C Task33 anchor reproduction
-> Phase D p3/h3
-> Phase E p4/h5
-> Phase F adaptive
-> Phase G resource recalibration
```

独立 lane 失败时：

- 保存 negative；
- 停止该 lane 后续重型步骤；
- 不删除失败证据；
- 可以继续不依赖该 lane 的安全工作；
- 不得越级运行被失败 Gate 锁定的候选。

例如：

- p3/h3 factorization 失败，不阻止完成 p2 adaptive mechanism；
- p4 full3D 失败，不阻止 p4 Hybrid measured study；
- WSL environment 或 source-clean 失败，阻止所有 formal PDE；
- periodic adaptive mechanism 失败，阻止 measured adaptive compression；
- current modal core 0.7 nm 预测失败，不得改写为 local FEM 也失败，反之亦然。

---

# 16. 必交付文件

任务结束时至少包含：

```text
docs/task034_workstation_wsl_adaptive_scalability/outcomes/environment_and_base.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/wsl_environment_qualification.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/post_merge_hardening_audit.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/task033_anchor_reproduction_wsl.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/p3_h3_reference_and_reranking.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/p4_h5_workstation_study.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/adaptive_mechanism.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/adaptive_compression.csv
docs/task034_workstation_wsl_adaptive_scalability/outcomes/resource_model_v2.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/0p7nm_workstation_and_tib_assessment.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/test_summary.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/changed_files.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/selective_merge_manifest.csv
docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md
docs/task034_workstation_wsl_adaptive_scalability/response_v1.md
```

并更新：

```text
docs/development_progress.md
docs/capability_matrix.md
docs/project_service_requirements_and_forward_model_roadmap.md
notes/reference/code_walkthrough.md
notes/theory/README.md
```

`outcomes/summary.md` 必须表格优先，至少含：

- final status/scope；
- WSL environment matrix；
- hardening issue matrix；
- Task33 reproduction matrix；
- p3/h3 staged results；
- p4 staged results；
- adaptive experiment matrix；
- equal-accuracy and compression results；
- resource model；
- failures/not-run；
- merge decision；
- next task recommendation。

每个数值表必须标出单位、baseline、数据身份和 evidence path。

---

# 17. 完成判定

Task034 不是要求每个大算例都必须正向通过。任务成功要求流程、证据和边界完整。

最低完成条件：

```text
WSL native environment qualified
post-merge hardening issues closed with tests
Task33 key anchors reproduced on WSL
p3/h3 received a staged measured decision
p4/h5 received a staged measured decision
fixed-p conforming graded-h mechanism measured
adaptive compression received a measured decision
resource model recalibrated from new measurements
0.7 nm assessment separates local FEM and modal-core limits
ordinary default unchanged
all official positives pass full explicit true residual
all resource failures controlled and preserved
```

允许最终状态：

```text
PASS
PASS_WITH_QUALIFICATIONS
PARTIAL_WITH_CONTROLLED_RESOURCE_NEGATIVES
FAIL
```

不允许：

```text
complete because code exists
0.7 nm feasible because 256 GiB is larger
p4 pass because assembly succeeded
adaptive pass because mesh elements decreased
clean source while nonignored untracked files exist
no swap based only on host-global counters
```

---

# 18. 分支、审查与合并

Codex 完成后必须：

1. 推送 `codex/20260717-task34-workstation-wsl-adaptive-scalability`；
2. 提交 `response_v1.md`；
3. 给出 branch HEAD、base SHA、测试和重型记录索引；
4. 停止并等待 ChatGPT review；
5. 不自行合并 `master`。

ChatGPT 将在同一任务目录提交 `review_report_v1.md`。如需修正，Codex 在同一分支继续并新增 `response_v2.md`；不得覆盖任务书或审查文件。

最终仍采用 file-level selective merge。未通过的 solver、adaptive、p4 或资源研究代码默认留在 Task034 research branch；只有经过审查的最小稳定组件、测试、轻量 evidence 和文档才允许进入 `master`。
