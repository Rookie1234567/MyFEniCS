# Task029 强制补充：COMSOL 内存参考的使用边界

## 1. 生效范围

本文件是以下任务书的**强制补充**，Codex 执行 Task029 时必须同时阅读：

```text
docs/task029_stage4_direct_memory_forensics/task.md
docs/task029_stage4_direct_memory_forensics/task_comsol_reference_addendum.md
```

参考报告：

```text
docs/task029_stage4_direct_memory_forensics/references/comsol_3d_direct_iterative_memory_report.md
```

本补充只调整 Task029 的比较口径、优先级和输出要求，不改变以下既有约束：

```text
- Task028 必须先合并 master；
- Task029 必须从更新后的干净 master 创建独立分支；
- h=5/h=3 必跑；
- h=2 条件解锁；
- Task28 canonical records 只读；
- ordinary default 不静默改变；
- full true residual 与 official R/T/A 必须保留。
```

---

# 2. COMSOL 报告的已知条件

COMSOL 数据来自**另一台电脑**，不能与当前 FEniCS/WSL2 运行做未经控制的逐秒或逐 GB 等价比较。

已知 COMSOL 条件：

```text
COMSOL = 6.4.0.293, Windows
machine = 1 socket, 10 cores, available memory 32.38 GB
mesh = FreeTet，自由四面体
volume elements = 182,393 tetrahedra
recorded DoF = 1,178,238
field element = curl-conforming Nédélec / edge-vector
field order = COMSOL component default，报告判断为二阶 curl element
geometry mapping = quadratic Lagrange geometry mapping
period = 50 x 25 nm
block = 16 x 25 x 120 nm
wavelength = 13.5 nm
incidence angle = 80 deg
polarization = P
ports = two periodic ports
additional diffraction orders = disabled
reported R/T = zero-order only
```

COMSOL 直接法主要参考：

```text
solver = MUMPS
peak process memory high-water = 22.989 GB
physical / virtual memory in logged run = 19.79 / 22.99 GB
DoF = 1,178,238
```

COMSOL 成功迭代路线的内存范围：

```text
right GMRES + GMG, restart 300  -> 13.376 GB
right GMRES + GMG, restart 100  -> 11.699 GB
right GMRES + GMG, restart 50   -> 10.547 GB
right TFQMR + GMG               -> 8.992–9.010 GB
```

这些数值只能作为“商业软件在另一套离散、机器和端口设置下达到的内存量级”参考。

---

# 3. 与 FEniCS Task029 target 的关键差异

Task029 必须在输出中明确列出以下差异，不得把两套模型描述为完全相同。

| 项目 | COMSOL 报告 | FEniCS Task029 |
|---|---|---|
| 运行机器 | 另一台 Windows 工作站，32.38 GB 可用内存 | 当前 Docker/WSL2/个人电脑环境，记录实际 cgroup/host 配额 |
| 网格拓扑 | FreeTet 自由四面体 | 当前 target 的 boundary-fitted/matched hexahedral 路线 |
| DoF | 1,178,238 | h5/h3/h2 分别约 44,698 / 198,438 / 615,108 FE DoF |
| 光栅宽度 | 16 nm | 17 nm |
| 偏振 | P | s |
| 端口衍射级 | 仅 `(0,0)`，未添加其他衍射级 | `auto_propagating`，保留全部传播级 |
| 端口未知量 | COMSOL 周期端口/S 参数变量 | FEniCS auxiliary Fourier-DtN modal unknowns |
| 求解器并行模型 | COMSOL 多线程/内部实现 | PETSc + MUMPS，当前 baseline MPI4 |
| 内存口径 | 日志提取的进程内存高水位 | rank RSS、同时总 RSS、cgroup peak、swap 等明确拆分 |
| 时间口径 | 另一机器的 COMSOL batch time | 当前机器的 FEniCS wall time |

因此禁止直接得出：

```text
- COMSOL 每 DoF 必然比 FEniCS 更省多少百分比；
- 两者的 factor fill 应完全相同；
- 两者 R/T/A 应数值相等；
- COMSOL 时间更快或更慢；
- FEniCS 只要达到相同 DoF 就应达到相同内存。
```

---

# 4. Task029 的主要比较目标

Task029 的主 Gate 仍然是 FEniCS 自身的前后对比：

```text
same FEniCS physical model
same hexahedral mesh
same p=2 Nédélec discretization
same double Floquet constraints
same auto_propagating diffraction-order set
same auxiliary DtN formulation
same official R/T/A definition
same MPI baseline unless rank-count experiment explicitly stated
```

主比较：

```text
Task28 FEniCS direct baseline
vs
Task29 FEniCS optimized direct candidate
```

COMSOL 报告只承担三个作用：

```text
1. 说明 100 万级 Nédélec 系统在成熟实现中可以保持约 20–23 GB 直接法内存量级；
2. 提供 MUMPS ordering/OOC/内存策略的调查线索；
3. 说明后续多层迭代法仍有进一步降内存空间。
```

COMSOL 数据不得替代 Task28 direct records，也不得作为 Task029 数值正确性的 reference solution。

---

# 5. FEniCS 必须保留完整传播衍射级

COMSOL 报告为零级衍射口径，但 Task029 的 FEniCS 优化**不得退化为零级端口**。

必须继续使用：

```text
stage4_boundary_model = dtn_port
stage4_dtn_order_policy = auto_propagating
stage4_dtn_assembly = auxiliary
```

每个 baseline/candidate record 必须保存：

```text
- top/bottom diffraction order list；
- polarization list；
- n_aux；
- each mode m/n/polarization/propagation classification；
- Task28 reference order-set identity；
- auxiliary amplitudes 或其稳定摘要；
- official per-order and total R/T；
- A_volume 与 energy closure。
```

强制 Gate：

```text
candidate modal order set == Task28 baseline modal order set
candidate n_aux == Task28 baseline n_aux
```

禁止以下“优化”：

```text
- 改为 zero_order；
- 手工减小 m/n 范围而漏掉传播级；
- 删除 auxiliary modes；
- 关闭 per-order/official RTA；
- 用 COMSOL 的 AddDiffractionOrders=0 为理由减少 FEniCS 模态。
```

如果衍射级本身造成可测内存开销，应单独记录，但它属于必须保留的物理成本，而不是可以删除的浪费。

---

# 6. 时间不是本任务的主优化指标

由于 COMSOL 在另一台机器上运行，Task029 不进行 COMSOL/FEniCS 时间横向排名。

Task029 仍应记录 FEniCS 各阶段时间，以便：

```text
- 判断 factorization 是否持续推进；
- 识别 swap/thrashing；
- 量化 OOC/BLR 的代价；
- 防止某个内存候选出现数量级性能退化；
- 解释生命周期优化是否只移动了峰值。
```

但候选排名的主指标是：

```text
1. 数值 Gate；
2. max simultaneous total RSS；
3. factorization-stage memory；
4. matrix/factor inventory；
5. swap/OOC 行为。
```

时间只能作为异常或工程代价说明，不得因为 COMSOL 报告中的时间不同而淘汰/选择 FEniCS profile。

原 Task029 中以下淘汰描述应按本补充解释：

```text
“峰值内存不降且时间显著增加”
```

表示：候选既无内存收益，又引入明显工程退化；不是要求与 COMSOL 时间竞争。

---

# 7. 从 COMSOL 直接法配置提取的调查线索

COMSOL MUMPS 记录提供以下可调查线索：

```text
mumpsreorder = auto
preorder = nested dissection
mumpsalloc = 1.2
ooc = auto
incore = auto
memfracooc = 0.99
usetotmemory = 0.8
pivot threshold = 0.01
pivot perturbation = 1e-8
BLR = off
reuse pattern = on
reuse reorder = on
iterative refinement = on
```

Task029 应将这些视为**假设来源**，而不是照抄配置。

只允许使用当前 PETSc/MUMPS 构建真实支持、并能从日志/INFO 字段确认生效的选项。对每个候选必须记录：

```text
requested option
actual supported option
actual ordering
actual in-core/OOC state
actual BLR state
factor memory estimate/measurement
true residual
R/T/A delta
```

如果 PETSc 接口与 COMSOL 参数不存在一一对应关系，应明确写 `not_directly_mappable`。

---

# 8. COMSOL GMG 结果在 Task029 中的作用

COMSOL 的 GMRES/TFQMR + GMG 结果说明：

```text
- 商业实现可以用多层方法把约 117.8 万 DoF 的内存降到约 9–13 GB；
- 成功不是裸 Krylov，而是完整 GMG + block smoother + coarse direct solve；
- 后续 FEniCS 迭代法仍值得继续研究真正的 multilevel/H(curl) 路线。
```

但 Task029 是**直接法内存任务**，因此不得在本任务内：

```text
- 实现 COMSOL GMG；
- 新建 TFQMR/GMRES 多重网格求解器；
- 修改 Task27 迭代 profile；
- 把 COMSOL GMG 时间或迭代数作为 Task029 direct Gate。
```

Task029 outcomes 应把 GMG 结论写入 `next_decision.md`，作为后续迭代法任务的研究依据。

---

# 9. 新增强制输出

原任务书中的：

```text
comsol_comparison_notes.md（可选）
```

由本补充改为**必需输出**：

```text
docs/task029_stage4_direct_memory_forensics/outcomes/comsol_reference_comparability.md
```

至少包含：

```text
1. COMSOL 报告文件与来源日期；
2. 两台机器与内存口径差异；
3. tetra vs hexa；
4. DoF、element order、geometry mapping；
5. P vs s polarization；
6. 16 nm vs 17 nm block；
7. zero-order vs auto-propagating diffraction orders；
8. MUMPS/direct configuration clues；
9. COMSOL GMG 的后续研究启示；
10. 哪些量可作定性参考，哪些量禁止直接比较。
```

同时在以下文件中链接 COMSOL 报告：

```text
outcomes/README.md
outcomes/summary.md
outcomes/parameters.json
outcomes/next_decision.md
benchmarks/cases/050_stage4_direct_memory_forensics/README.md
```

`parameters.json` 建议加入：

```json
{
  "external_memory_reference": {
    "path": "docs/task029_stage4_direct_memory_forensics/references/comsol_3d_direct_iterative_memory_report.md",
    "same_machine": false,
    "mesh_topology": "free_tetrahedron",
    "dof": 1178238,
    "diffraction_scope": "zero_order_only",
    "allowed_use": "qualitative_memory_architecture_reference",
    "forbidden_use": [
      "runtime_comparison",
      "RTA_reference",
      "per_dof_efficiency_claim_without_matrix_data"
    ]
  }
}
```

---

# 10. Task029 成功判断的修订

Task029 仍以自身 FEniCS baseline 为主，因此成功分类保持：

```text
diagnostic_success
engineering_success
strong_engineering_success
h2_workstation_success
```

新增要求：

```text
- 不得以 COMSOL 22.989 GB 作为 FEniCS h=2 的硬目标；
- 不得以 COMSOL 8.99–13.38 GB 作为 Task029 direct 的成功 Gate；
- 可以把 COMSOL 量级写成 future architecture reference；
- Task029 direct 候选仍按 FEniCS h5/h3 相对 Task28 baseline 的降幅判定；
- h2 解锁仍使用 Task029 原任务书的 20% 降幅、无 swap 和 13.5 GB 安全预测上限；
- FEniCS 所有候选必须保留全部传播衍射级。
```

---

# 11. Codex 执行前检查

Task029 开始时，Codex 必须在 `run_log.txt` 首段确认已阅读：

```text
[ ] task.md
[ ] task_comsol_reference_addendum.md
[ ] references/comsol_3d_direct_iterative_memory_report.md
[ ] Task028 final review/response/outcomes
```

若只读取 `task.md` 而忽略本补充，则 Task029 不得开始计算。
