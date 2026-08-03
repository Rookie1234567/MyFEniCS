# p6/h10 Full3D 与原有 Hybrid M120 四次正式计算对比及 0.7 nm 路线建议

## 1. 先说结论

本轮在同一份干净源码、同一几何、同一 p6/h10 三维六面体离散、同一 MPI8 direct
条件下，选了一个历史上 Hybrid 表现正常的点和一个已知困难点，各运行一次 Full3D 与
原有 M120 Hybrid，共四次 PDE。这里的“原有 Hybrid”是当前仓库已有的
`modal-schur-memory-minimal` 本征模路线，包含已经选定的
`full3d_uniform_cg + scalar_cg_discrete_derivative` 离散传播/traction 修正；它不是本轮新开发
的 port-ROM，也不是更早已知有连续符号错误的原始旧实现。

最终任务处置以 [Task036 Review Report V8](../review_report_v8.md) 为准。本文四次 PDE 均绑定
旧 clean source `ff2227cac8a19bd3a4c66279a413f6a34d730098`，并在 V8 发布前完成；本文现在只作
最终证据归档，不授权新的 Task036 PDE、direct-port basis、P1/P2 actual candidate 或其他
数值开发。V8 已将 Task036 结为 `CLOSED_CONTROLLED_FAILURE_WITH_REUSABLE_POSITIVES`，
`C1b` 为 `cancelled/not_run`；Task037 iterative 虽被 deferred，但 implementation 尚未授权。

结论分为三层：

1. **D005-S（10° 掠射、S 偏振）是很强的正对照。** Full3D 与 Hybrid M120 的
   R/T/A、零级、80 个固定通道都对齐，80/80 复振幅与 80/80 功率通过；按两类 runner
   各自冻结的 live-memory authority 配对比较，Full process-tree peak 为 20.3523 GiB，
   Hybrid simultaneous live-worker sum peak 为 9.7082 GiB，工程配对降幅 52.30%。两者
   采样集合不同，不能改写成同一 process-tree 口径。但它没有相邻 M 收敛证明，正式分类
   仍是 `rank_pending_next_m`，`official_record=false`，不能据此宣布 Hybrid 已具备生产资格。
2. **D001-P（0.5° 掠射、P 偏振）仍然失败，而且失败位置已经很具体。** 80 个通道中
   66 个全通过；14 个 co-P、`n=0`、负 m 通道的复振幅失败，其中 8 个 significant
   通道的功率也失败，另外 6 个 weak 通道只有复振幅失败。Hybrid 的总代数残差、代数
   E 接口残差、exact traction dual、80 模 direct projection 都很小，却在恢复后的物理
   接口 E 场出现 18.22% 相对 L2 偏差。这说明问题不是 direct LU 没解准，也不能仅靠看
   R/T 总量判断；更像是 M120 选择空间遗漏了对困难 P 偏振重要的 trace complement。
3. **如果今后要微调几何，继续为一个固定几何训练单一 global ROM 的意义确实明显下降。**
   M120 仍值得保留为 13.5 nm 回归/诊断基线，但不应再被当成 0.7 nm 生产方案。对
   0.7 nm，首先应判定几何是否严格 y 不变：若严格成立，优先走受限 2.5D/RCWA 或二维
   截面 Maxwell 路线；若是真三维微扰，则走“局部富端部 + 局部/参数化 joint-Cauchy
   port + 分层低秩 direct”路线，并在 13.5→5→2→1→0.7 nm 逐级资格化。当前 direct
   数据布局按 0.7 nm 机械外推约需 1,595.6 TiB 的单个显式对象，远超 2 TiB，不能直接放大。

全量 160 行逐通道数据在：

- [p6_h10_full3d_vs_original_m120_all_channels.csv](p6_h10_full3d_vs_original_m120_all_channels.csv)
- 更完整的 0.7 nm direct-only 分阶段计划见
  [0p7nm_geometry_robust_large_scale_direct_roadmap.md](0p7nm_geometry_robust_large_scale_direct_roadmap.md)。

CSV 是从 hash-bound `full_channel_analysis.json` 与 Full raw orders 机械导出的 tracked 完整
展示表；上游 numerical authority 仍是 analyzer 加四次 raw records。本文表格重点列总量、
零级、所有失败通道和资源/诊断。

## 2. 计算合同与数据身份

### 2.1 两个物理点

| Case | 角色 | 波长 | 掠射角 / 方位角 | 入射偏振 | 周期单元 | 光栅 | Hybrid 分区 |
|---|---|---:|---:|---|---|---|---|
| `D005-S` | 历史成功物理点的严格再验证 | 13.5 nm | 10° / 0° | S | 50 nm × 25 nm | 高 120 nm、x 宽 17 nm、y 宽 25 nm | 下接口 z=10 nm、上接口 z=110 nm，中间均匀模态区 100 nm |
| `D001-P` | 已知失败探针 | 13.5 nm | 0.5° / 0° | P | 同上 | 同上 | 同上 |

两点均使用 air `n=1+0i`、Si `n=0.999002304859+0.00182649365i`，所有区域
`mu_r=1`，物理 z 范围
`[-10,130] nm`。网格实际为 `6×4×14=336` 个轴对齐六面体，x/y 方向为贴合几何而形成的
8.25–8.5 nm / 6.25 nm 单元，z 方向为 10 nm；因此“h10”是该网格族标签，不表示每条边
都恰为 10 nm。有限元阶次为 Nédélec p6。

D005 的“历史成功”只指相同物理入射点。Task035c 原锚点使用 axis `(6,3,14)`/Ny3，正式
审查 12 个 significant channels；本轮为统一 Task036 合同改用 `(6,4,14)`/Ny4，并严格审查
全部 80 个固定通道。因此这是 stronger revalidation，不是把完全相同的旧离散 case 重跑一次。

### 2.2 方法是什么

- **Full3D static condensation**：先在每个三维单元内部精确消去只在单元内部出现的自由度，
  再对剩余 trace 系统做 MUMPS direct LU；消去是代数等价变换，不是近似降阶。
- **Hybrid M120 static condensation**：上下各保留 20 nm 厚的三维局部端部并同样静态凝聚，
  中间 100 nm 均匀区用每个传播方向 120 个本征模表示；内部系统共有 240 个模态未知量，
  最终形成 `240×240` modal Schur 系统。局部系统和 Schur 均使用 direct 路线。
- 四次计算均未使用或开发迭代法。Hybrid 的**结构化逐方向有限候选池**是 240，最终
  每方向选 120。raw `solver_converged_modes` 是 QEP eigensolver 的实际收敛模数量：D005
  正/负方向分别为 281/280，D001 为 296/296；它与结构化 240 候选池及最终 M120 是三种
  不同计数，不能把 281/280 或 296/296 称为“有限候选池”。

### 2.3 源码、环境与运行包络

| 项目 | 值 |
|---|---|
| 执行分支 | `codex/20260730-task36-forward-solver-bugfix-hardening` |
| 四次 PDE 源码 SHA | `ff2227cac8a19bd3a4c66279a413f6a34d730098` |
| 工作树身份 | 四次运行前后 tracked/nonignored-untracked clean，SHA 未变化 |
| ABI | 仓库资格化 WSL 环境，PETSc `complex128` |
| MPI / direct solver | MPI8；PETSc `preonly+lu+mumps`；Hybrid local factor 为 MUMPS multi-RHS modal Schur |
| CPU 绑定 | 外层 launcher 将 8 rank 绑定 CPU 0–7；timeline 中逐 rank affinity 可见。记录的 inner command 不重复外层 `taskset/env` |
| 线程设置 | `OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=NUMEXPR_NUM_THREADS=1`；MPI/PETSc 运行时仍可有管理线程，不能把它误写成每个 rank 只有一个 OS thread |
| dedicated job cgroup | 四次均为 `false`；本轮不能用 dedicated-cgroup current/peak 统一四个 runner 的内存口径 |
| swap | 四次均为 0；无 OOM、无 timeout、无 resource termination |
| artifact 根目录 | `benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/` |

### 2.4 核心证据 hash

| 证据 | SHA-256 |
|---|---|
| 全通道分析 `full_channel_analysis.json` | `c0b963d952ae7a92fe6cfeb9ea9c1ba74fd6d130995f438e2e57a7e8bec6944e` |
| 聚合 `summary.csv` | `67d0a1268c5cb1d15a3e6b4d98afbf159dbeff0c981650dd623a27702ea05a78` |
| 本报告全通道 CSV（derived/tracked 展示） | `ac01146bd956b57a29ff7c3d39f5c01c2b862048777f7e0caa62c8007ac9a124` |
| D005 Full watchdog / run summary / orders | `b6005c54...e462c97` / `21ce0f91...5840e` / `3745a665...7d4b7` |
| D005 Hybrid sampler / solver record | `da9b85e1...c81b7` / `17b928f7...8d3f` |
| D001 Full watchdog / run summary / orders | `ded92d34...fc144` / `721f1572...b2b82` / `2abd38d7...caf2` |
| D001 Hybrid sampler / solver record | `69a3659a...da16b` / `96498282...f3cf` |

表中缩写 hash 只便于阅读；完整值保存在全通道 analyzer 及本报告末尾证据索引。

## 3. 四模型总览

| Case / 方法 | solver 状态 | 物理资格 | 80 通道 | true residual | runner 冻结 live-memory authority peak | solver-internal total |
|---|---|---|---:|---:|---:|---:|
| D005 Full3D static | `full3d_reference_pass`，return 0 | official Full reference | 80/80 reference coverage | `1.251450e-11` | 20.352249 GiB | 748.447064 s |
| D005 Hybrid M120 static | `measured_shard_pass`，return 0 | `integration_pass=true`；`physical_field_gates_pass=true`；`mode_count_converged=false`；`physical_augmented_direct_pass=false`；`official_record=false` | 80/80 | `6.361293e-12` | 9.708168 GiB | 822.719559 s |
| D001 Full3D static | `full3d_reference_pass`，return 0 | official Full reference | 80/80 reference coverage | `1.730467e-12` | 18.790070 GiB | 872.496244 s |
| D001 Hybrid M120 static | `formal_not_pass`，return 2 | `trace_complement_diagnostic_hold`；`integration_pass=false`；`physical_field_gates_pass=false`；`mode_count_converged=false`；`physical_augmented_direct_pass=false`；`official_record=false` | 66/80 | `4.759399e-13` | 9.569057 GiB | 764.817415 s |

Full3D 数字来自 watchdog `resource_authority.max_process_tree_rss_mb`：D005/D001 为
`20840.703125/19241.03125 MiB`。Hybrid 数字来自 sampler
`resource_authority.simultaneous_live_worker_rss_sum_bytes`：D005/D001 为
`10424066048/10274697216 bytes`。两类 runner 均没有 dedicated job cgroup；所以这张表保留
任务冻结的**配对 authority comparison**，但不宣称 Hybrid 数字是 process-tree 或 whole-job
RSS，也不宣称四个数字来自完全相同的进程集合。

这里的 total 是 solver record 内部总计，不称作完整端到端 wall。内存 timeline 最后一行分别为：

| Case / 方法 | timeline 末端 elapsed | 末端 stage |
|---|---:|---|
| D005 Full3D | 805.550788 s | `final_cleanup/end` |
| D005 Hybrid | 825.353389 s | `record_and_release/unknown` |
| D001 Full3D | 922.549378 s | `final_cleanup/end` |
| D001 Hybrid | 767.525090 s | `record_and_release/unknown` |

timeline 末端包含 watcher 采样、输出和进程排空，不能与 solver-internal total 混用。
D005 Full3D 的 20.352249 GiB 超过该次运行的 20 GiB warning line，故
`warning_triggered=true`；它仍低于 24 GiB termination line，计算正常完成且 swap 为 0。
其余三次 `warning_triggered=false`。

## 4. 总功率、零级与体吸收

### 4.1 四模型总量

`A_balance=1-R-T`；`A_volume` 是材料体积分得到的吸收。二者接近是能量闭合检查。

| Case / 方法 | R_total | R00_s | R00_p | R00_total | T_total | A_balance | A_volume | R+T+A_volume |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| D005 Full3D | 0.000762881475143 | 0.000753761220078 | 8.540224e-26 | 0.000753761220078 | 0.602701633982657 | 0.396535484542200 | 0.396535484541613 | 0.999999999999413 |
| D005 Hybrid M120 | 0.000762881475148 | 0.000753761220084 | 4.090335e-27 | 0.000753761220084 | 0.602701633983217 | 0.396535484541635 | 0.396535484558948 | 1.000000000017313 |
| D001 Full3D | 0.621286165125328 | 3.632442e-24 | 0.621274561310692 | 0.621274561310692 | 0.006244227206617 | 0.372469607668055 | 0.372469607671513 | 1.000000000003458 |
| D001 Hybrid M120 | 0.621360889010226 | 1.919155e-24 | 0.621349403232170 | 0.621349403232170 | 0.006241265970413 | 0.372397845019361 | 0.372384777771148 | 0.999986932751786 |

### 4.2 Hybrid 相对 Full3D 的总量差

| Case | ΔR | ΔT | ΔA_volume | signed closure error | 总量 Gate | 逐通道 Gate |
|---|---:|---:|---:|---:|---|---|
| D005-S | `+5.496471e-15` | `+5.596634e-13` | `+1.733486e-11` | `+1.731326e-11` | pass | 80/80 pass |
| D001-P | `+7.472388e-05` | `-2.961236e-06` | `-8.482990e-05` | `-1.306725e-05` | analyzer 的 1e-4 total-delta Gate pass；closure Gate fail | 66/80 pass |

D001 的总量差可部分互相抵消，所以“总量 Gate 通过”不代表通道正确。这里正是为什么必须保留
复振幅、功率、极化与衍射级的完整向量。

### 4.3 吸收分区

Full3D 的 grating/substrate 来自正式 volume-integral 字段。Hybrid 的 substrate 是下端局部
substrate 吸收；grating 是上下局部 grating 加中间模态区吸收后除以 incident power，属于从
原始分区功率**派生**的同口径值。

| Case / 方法 | A_grating | A_substrate | A_total | Hybrid−Full Δgrating | Hybrid−Full Δsubstrate |
|---|---:|---:|---:|---:|---:|
| D005 Full3D | 0.332476666681045 | 0.064058817860569 | 0.396535484541613 | — | — |
| D005 Hybrid M120 | 0.332476666698324 | 0.064058817860624 | 0.396535484558948 | `+1.727963e-11` | `+5.526135e-14` |
| D001 Full3D | 0.368303266271359 | 0.004166341400155 | 0.372469607671513 | — | — |
| D001 Hybrid M120 | 0.368220269848918 | 0.004164507922230 | 0.372384777771148 | `-8.299642e-05` | `-1.833478e-06` |

## 5. 全通道对比

### 5.1 覆盖与通过数

每点固定 80 行：40 top/反射端、40 bottom/透射端；40 s、40 p。Ny=4 的非目标 y-alias
通道也在完整覆盖中，并没有只看 `n=0`。analyzer 的 `significant` 定义是
`max_abs_power_across_full3d_and_all_complete_hybrid_M`：对同一通道取 Full3D 与所有完整
Hybrid M 记录中的最大绝对功率，再与 `1e-8` power floor 比较。因此它不是独立的
held-out/frozen-reference 标签。本四次 bundle 中该集合恰好与仅按 Full3D 分类的集合一致：
D001 为 10 个、D005 为 12 个，`hybrid-only significant=0`；但不能把这种本轮巧合改写成
定义本身。

通道阈值沿用 Task033 funnel：上述 comparison significance power floor `1e-8` 以上按
significant relative tolerance `1e-3`；更弱通道按 absolute tolerance `1e-8`。总量
absolute tolerance 是 `1e-4`。因此 significant/weak 与 relative/absolute Gate 必须成对解释。

| Case | 复振幅 pass | 功率 pass | 两者同时 pass | 失败聚类 |
|---|---:|---:|---:|---|
| D005-S | 80/80 | 80/80 | 80/80 | 无 |
| D001-P | 66/80 | 72/80 | 66/80 | 14 个 co-P、`n=0`、负 m 复振幅失败；其中 8 个 significant 功率失败，6 个 weak 功率仍 pass |

### 5.2 零级四极化/端口

复振幅写作 `Re+Im i`。极弱 cross-pol 的相对误差可很大，但绝对误差和功率仍低于冻结阈值；
因此必须同时看 absolute/relative Gate。

| Case | side | pol | Full3D amplitude | Hybrid amplitude | abs(Δamp) | Full power ratio | Hybrid power ratio | abs(Δpower) | pass |
|---|---|---|---|---|---:|---:|---:|---:|---|
| D005-S | bottom | p | `4.441620577e-14+3.339186925e-13i` | `-5.067292438e-14+6.915736549e-14i` | 2.813192e-13 | 1.098802051291e-25 | 7.117660919210e-27 | 1.027625e-25 | pass |
| D005-S | bottom | s | `6.313787033e-01+4.730209810e-01i` | `6.313787033e-01+4.730209810e-01i` | 1.713002e-12 | 6.026738723435e-01 | 6.026738723441e-01 | 5.605516e-13 | pass |
| D005-S | top | p | `7.514268120e-14+2.824107291e-13i` | `-2.503933023e-14-5.885037420e-14i` | 3.556622e-13 | 8.540224242817e-26 | 4.090334601985e-27 | 8.131191e-26 | pass |
| D005-S | top | s | `-2.525230435e-02+1.077415170e-02i` | `-2.525230435e-02+1.077415170e-02i` | 2.934965e-13 | 7.537612200779e-04 | 7.537612200844e-04 | 6.509116e-15 | pass |
| D001-P | bottom | p | `4.035336568e-02-3.291496446e-03i` | `4.034396340e-02-3.297493055e-03i` | 1.115179e-05 | 6.233989874011e-03 | 6.231254647941e-03 | 2.735226e-06 | pass |
| D001-P | bottom | s | `-3.635970982e-14+2.779150127e-13i` | `-7.679664117e-14-7.145209412e-14i` | 3.516995e-13 | 2.987593154466e-25 | 4.184492466056e-26 | 2.569144e-25 | pass |
| D001-P | top | p | `-7.875198013e-01+3.297156139e-02i` | `-7.875663695e-01+3.299419385e-02i` | 5.177670e-05 | 6.212745613107e-01 | 6.213494032322e-01 | 7.484192e-05 | pass |
| D001-P | top | s | `1.788193701e-12+6.593979235e-13i` | `-1.141468989e-12+7.849860954e-13i` | 2.932353e-12 | 3.632442335441e-24 | 1.919154623776e-24 | 1.713288e-24 | pass |

D001 bottom `(0,0,p)` 在 Full raw order 中 `propagating=false`，但有耗基底内仍有
`power_ratio=0.006233989874011`。CSV 和本表使用 analyzer 的 `power_ratio`，没有使用 raw
辅助字段 `T=0`。`propagating` 与 `power_carrying` 也是不同概念：CSV 对 Full 与 Hybrid
分别保存 `reference_power_carrying`、`hybrid_power_carrying`；analyzer 没有报告 Hybrid
`right_power_carrying` 时保留为空，不用传播分类替它推断。

### 5.3 D001 的全部 14 个失败通道

| side | m | n | pol | analyzer comparison class | abs(Δamp) | rel Δamp | Full power | Hybrid power | abs(Δpower) | power Gate |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| bottom | -7 | 0 | p | significant | 5.520972e-06 | 4.096688e-02 | 9.442774e-07 | 9.420584e-07 | 2.219044e-09 | fail |
| bottom | -6 | 0 | p | weak | 5.832641e-06 | 9.986770e-01 | 2.655955e-09 | 3.061732e-09 | 4.057772e-10 | pass |
| bottom | -5 | 0 | p | significant | 5.344068e-06 | 2.575167e-01 | 2.646343e-08 | 4.617577e-08 | 1.971235e-08 | fail |
| bottom | -4 | 0 | p | weak | 4.539123e-06 | 6.567183e-01 | 1.918343e-09 | 5.451450e-09 | 3.533107e-09 | pass |
| bottom | -3 | 0 | p | weak | 2.549285e-06 | 8.822486e-01 | 2.736383e-10 | 9.383878e-10 | 6.647494e-10 | pass |
| bottom | -2 | 0 | p | significant | 5.286933e-06 | 7.307369e-02 | 5.319575e-07 | 4.794837e-07 | 5.247374e-08 | fail |
| bottom | -1 | 0 | p | significant | 5.182902e-06 | 1.550786e-02 | 8.729786e-06 | 8.534153e-06 | 1.956333e-07 | fail |
| top | -7 | 0 | p | significant | 5.580474e-06 | 3.633820e-02 | 1.146579e-06 | 1.232054e-06 | 8.547562e-08 | fail |
| top | -6 | 0 | p | weak | 4.552714e-06 | 8.605946e-01 | 2.516138e-09 | 1.131875e-10 | 2.402950e-09 | pass |
| top | -5 | 0 | p | significant | 5.397084e-06 | 2.609981e-01 | 4.590063e-08 | 2.668546e-08 | 1.921517e-08 | fail |
| top | -4 | 0 | p | weak | 5.548494e-06 | 9.976692e-01 | 3.532969e-09 | 4.613352e-10 | 3.071633e-09 | pass |
| top | -3 | 0 | p | weak | 2.294943e-06 | 1.149373e+00 | 7.628711e-11 | 4.485379e-10 | 3.722508e-10 | pass |
| top | -2 | 0 | p | significant | 5.356195e-06 | 9.375193e-02 | 3.321188e-07 | 3.253678e-07 | 6.750934e-09 | fail |
| top | -1 | 0 | p | significant | 5.149402e-06 | 1.435886e-02 | 1.007309e-05 | 9.900647e-06 | 1.724438e-07 | fail |

失败的 8 个 significant 通道是上下端各 `m=-7,-5,-2,-1`；6 个 weak 通道是上下端各
`m=-6,-4,-3`。所有 cross-pol 通道均通过。这种成簇结构比“随机数值噪声”更像一个对 P
偏振负衍射级有选择性的空间遗漏。

### 5.4 CSV 字段和派生口径

CSV 共 161 行（1 行表头 + 160 行数据），固定排序为 D005→D001、top→bottom、m/n 升序、
s→p。字段 `analyzer_comparison_significance` 保存 §5.1 所述 analyzer 联合比较分类，而不是
独立 Full3D reference 标签。CSV 还包含：case/端口/衍射级/极化、co/cross、propagating、
Full/Hybrid 各自的 power-carrying、reference 复 beta、reference Rayleigh warning、
Full/Hybrid 复振幅实虚部、模和相位、振幅误差、功率及各 Gate。

- `reference_beta_*` 与 `reference_rayleigh_warning` 来自 Full3D raw order，并按
  `(side,m,n,pol)` 与 analyzer 联表；Full/Hybrid propagating 与 power-carrying 使用各自
  analyzer 字段，缺失的 Hybrid power-carrying 保留空值；
- amplitude 是相同 physical-boundary outgoing complex-amplitude convention；power ratio
  均按各自记录的 incident power 归一化；
- 振幅 phase 是从对应复振幅用 `atan2(Im,Re)` **派生**，不是 raw `boundary_phase`；
- Full/Hybrid power 均取 analyzer 对比行的 `power_ratio`；
- 极弱通道的 relative error 不能脱离 absolute threshold 单独解读。

## 6. 为什么 D001 会在“残差很小”时仍然错

### 6.1 代数 Gate 与恢复物理场

| 指标 | 限值/语义 | D005 Hybrid | D001 Hybrid | 判读 |
|---|---|---:|---:|---|
| full true relative residual | `<=1e-9` | `6.361293e-12` | `4.759399e-13` | 两者 direct 线性系统均解准 |
| algebraic interface E residual | `<=1e-8` | `2.254826e-12` | `1.716419e-11` | 两者选定代数接口空间内都通过 |
| exact traction relative dual | `<=1e-8` | `5.632571e-12` | `4.328793e-13` | 两者通过 |
| 80-mode direct projection difference | `<=1e-10` | `9.813927e-14` | `2.978822e-12` | 两者通过 |
| sampled recovered physical E_t max relative L2 | screening `<=5e-3` | `1.639492e-07` | `1.822196e-01` | D001 明显失败；这是物理 trace-complement root locator |
| signed R+T+A_volume−1 | `abs(.)<=1e-5` | `+1.731326e-11` | `-1.306725e-05` | D001 略超限 |
| abs(A_volume−Full) | `<=1e-5` | `1.733486e-11` | `8.482990e-05` | D001 失败 |

直观地说，线性方程在“Hybrid 允许表示的空间”里解得非常准确，但这个空间没有完整包含
D001 所需的接口场方向。于是 algebraic E/traction 和 LU residual 都可以很小，重建回物理场
时却暴露 18.22% 的 E_t 缺口，并投影到特定负 m、co-P 通道。

### 6.2 alias、biorthogonality 与 Gram 诊断的边界

| 指标 | D005 | D001 | 身份 |
|---|---:|---:|---|
| Hybrid bottom/top alias maximum normalized overlap | `3.364349e-16 / 3.014175e-16` | `3.307648e-16 / 2.551239e-16` | structured `hybrid_system.dtn_trace_alias_preflight`，两者 pass |
| positive/negative biorth row max | `9.954348e-7 / 9.954348e-7` | `1.809416e-7 / 1.809416e-7` | structured Gate，限值 `1e-6` |
| positive cross-entry max | `6.886922e-7` | `1.019726e-7` | structured diagnostic |
| D005 positive repair | initial row/entry `7.872790e-6 / 5.025306e-6` → final row `9.954348e-7` | 无实质修复，初末同量级 | D005 只比 `1e-6` 阈值低约 0.46%，不能说“远低于阈值”或“机器精度” |

Full3D watchdog 虽写有 alias evidence 预期路径，但 fresh root 中对应 payload/hash 均为空，文件
不存在；所以 Full3D alias 数值在本报告中标为 `unavailable`，不从 Hybrid 字段反推。

Hybrid worker stdout 还打印了 internal coupling Gram condition：D005 bottom/top
`5.197383e3/5.197356e3`，D001 `2.447314e6/2.447297e6`，以及 canonical mapping condition 1。
它们仅是 `worker_stdout.txt:1004` 的 diagnostic，不在 fresh structured formal Gate 中，不能扩写成
“四模型 Gram 证据”或单独作为失败定因。它只提示 D001 coupling 坐标可能更病态，值得后续
局部 port 实验观察。

## 7. 规模、内存与耗时

### 7.1 rows、NNZ 与 factor inventory

| Case / 方法 | 原始/局部 FE DoF | static 后系统 rows | matrix NNZ | factor inventory NNZ | 内部/外部 port |
|---|---|---|---:|---:|---|
| D005 Full3D | 229,680 raw Nédélec | 68,256 independent trace + 80 auxiliary = 68,336 | 55,985,168 | 344,304,152 | 80 external DtN，40 top+40 bottom |
| D005 Hybrid | 每端 11,232 FE、48 cells | bottom/top 各 11,272；另 240 internal | bottom/top 各 8,208,712 | 31,014,592 + 31,710,472 | M120/方向；Schur 240×240；80 external |
| D001 Full3D | 229,680 raw Nédélec | 68,256 + 80 = 68,336 | 55,984,880 | 317,841,392 | 同上；78 propagating + 2 lossy/evanescent-classified slots |
| D001 Hybrid | 每端 11,232 FE、48 cells | bottom/top 各 11,272；另 240 internal | bottom/top 各 8,208,568 | 30,897,448 + 31,804,648 | 同上 |

Hybrid 两侧 matrix/factor 数字是对象 inventory。两侧 factor NNZ 的算术和仅用于对象规模比较，
不是同步存在的内存峰值，不能乘 16 bytes 后冒充 RSS。

### 7.2 各 runner 冻结的 live-memory authority

| Case | Full process-tree authority / PSS / USS | Hybrid live-worker-sum authority / PSS / USS | Hybrid/Full 配对 authority | authority 工程降幅 | PSS/USS 诊断降幅 |
|---|---:|---:|---:|---:|---:|
| D005-S | 20.352249 / 18.054338 / 17.830769 GiB | 9.708168 / 7.165758 / 6.902802 GiB | 0.477007 | 52.2993% | 60.3100% / 61.2871% |
| D001-P | 18.790070 / 16.491210 / 16.267761 GiB | 9.569057 / 7.023274 / 6.764519 GiB | 0.509261 | 49.0739% | 57.4120% / 58.4176% |

Full3D authority 是 live MPI process-tree RSS；Hybrid authority 是 simultaneous live MPI
worker RSS sum，并不包含与 Full watchdog 完全相同的 process-tree 采样集合。表中的
Hybrid/Full 与降幅是任务预先冻结的 paired engineering comparison，不能改称统一
process-tree/whole-job 比值。PSS/USS 只使用各 runner 中 8 个 rank 同时可读的 smaps 样本，
属于共享页/私有页配对诊断，不替代各自 authority。任何 per-rank historical peak 求和、
非 dedicated 的 container `/init.scope` 历史峰值或 factor inventory 都没有混入 authority。
四次 swap 均为 0。

### 7.3 时间

Hybrid/Full solver-internal total 比值：D005 为 1.09924，即 Hybrid **慢 9.92%**；D001 为
0.87659，即 Hybrid **快 12.34%**。内存下降并不保证每个点都更快，D005 的两端 local FEM、
QEP/基与物理重建开销超过了 Full3D 本轮静态凝聚的优势。

Full3D 关键阶段：

| 阶段 | D005 (s) | D001 (s) |
|---|---:|---:|
| static trace build | 118.483586 | 115.437083 |
| base matrix assembly | 244.807683 | 239.493675 |
| incident source + modal loop | 12.448893 | 12.310352 |
| MUMPS KSP setup | 272.066395 | 360.055410 |
| KSP solve | 0.297024 | 0.367751 |
| matrix-free full residual | 115.095748 | 142.785302 |
| 80-mode direct projection audit | 10.296660 | 13.413259 |
| diffraction / volume-absorption postprocess | 35.877306 / 17.997586 | 31.726989 / 15.738165 |
| solver-internal total | **748.447064** | **872.496244** |

Hybrid 关键阶段：

| 阶段 | D005 (s) | D001 (s) |
|---|---:|---:|
| cross-section + QEP assembly | 3.038487 | 2.964827 |
| positive/negative biorth bases | 77.509170 | 79.956907 |
| two local FEM/DtN systems | 361.465763 | 328.572052 |
| internal modal coupling | 81.335370 | 82.122350 |
| primary system build/direct work | 39.769699 | 41.329667 |
| candidate direct projection audit | 12.280191 | 9.965595 |
| physical field reconstruction | 65.778995 | 63.072690 |
| solver-internal total | **822.719559** | **764.817415** |

## 8. 可复现命令

下面是四个 formal summary 记录的 inner commands。外层资格化 activation、CPU0–7 affinity、
线程环境和 resource sampler 由 launcher 包裹，未重复写进 inner command 字符串。

### 8.1 D005-S Full3D

```text
mpiexec -n 8 /home/Projects/MyFEniCS/.venv/bin/python -m benchmarks.run_task033_full3d_watchdog --worker --degree 6 --h-nm 10.0 --polarization-kind s --run-kind full-solve --mpi-size 8 --profile default --stage4-full3d-assembly-backend assembly_time_static_condensed --incident-grazing-deg 10.0 --incident-phi-deg 0.0 --run-dir /home/Projects/MyFEniCS/benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/D005-S/full3d --task036-forward-robustness-gate --verified-clean-sha ff2227cac8a19bd3a4c66279a413f6a34d730098 --grating-height-nm 120.0 --grating-width-x-nm 17.0 --task036-mesh-axis-cell-counts 6 4 14 --task036-y-invariant-n0-alias-preflight --task036-dtn-direct-projection-audit --parent-launch-descriptor /home/Projects/MyFEniCS/benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/D005-S/full3d/parent_launch_descriptor.json --parent-launch-descriptor-sha256 a1165ff0d7f145160568d8e582b64749774300a388fc68a3b9750a134726d855
```

### 8.2 D005-S Hybrid M120

```text
mpiexec -n 8 /home/Projects/MyFEniCS/.venv/bin/python -m benchmarks.run_task032_phase6_augmented --degree 6 --h-nm 10.0 --bottom-interface-nm 10.0 --top-interface-nm 110.0 --incident-grazing-deg 10.0 --incident-phi-deg 0.0 --grating-height-nm 120.0 --grating-width-x-nm 17.0 --polarization-kind s --requested-modes 120 --candidate-modes 240 --solver-path modal-schur-memory-minimal --stage4-full3d-assembly-backend assembly_time_static_condensed --comparison-solver-path fast --verified-clean-sha ff2227cac8a19bd3a4c66279a413f6a34d730098 --output /home/Projects/MyFEniCS/benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/D005-S/hybrid_m120/solver_record.json --memory-stages /home/Projects/MyFEniCS/benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/D005-S/hybrid_m120/memory_stages.jsonl --container-image myfenics-stage4:task28 --container-digest sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d --host-environment-id WSL2-Ubuntu-24.04 --modal-h-nm 10.0 --modal-degree 6 --internal-propagation-model full3d_uniform_cg --internal-traction-model scalar_cg_discrete_derivative --full3d-reference /home/Projects/MyFEniCS/benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/D005-S/full3d/watchdog_summary.json --full3d-reference-sha256 b6005c54eb4cc54b13dd6ba7b92ee193251d4c36bece86f8e135b8d29e462c97 --task036-domain-robustness-gate --task036-mesh-axis-cell-counts 6 4 14 --task036-y-invariant-n0-alias-preflight --task036-dtn-direct-projection-audit --task036-scalar-stage4-reciprocal-basis
```

### 8.3 D001-P Full3D

```text
mpiexec -n 8 /home/Projects/MyFEniCS/.venv/bin/python -m benchmarks.run_task033_full3d_watchdog --worker --degree 6 --h-nm 10.0 --polarization-kind p --run-kind full-solve --mpi-size 8 --profile default --stage4-full3d-assembly-backend assembly_time_static_condensed --incident-grazing-deg 0.5 --incident-phi-deg 0.0 --run-dir /home/Projects/MyFEniCS/benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/D001-P/full3d --task036-forward-robustness-gate --verified-clean-sha ff2227cac8a19bd3a4c66279a413f6a34d730098 --grating-height-nm 120.0 --grating-width-x-nm 17.0 --task036-mesh-axis-cell-counts 6 4 14 --task036-y-invariant-n0-alias-preflight --task036-dtn-direct-projection-audit --parent-launch-descriptor /home/Projects/MyFEniCS/benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/D001-P/full3d/parent_launch_descriptor.json --parent-launch-descriptor-sha256 190527ce789370ddf3a4cf128b990dcfd369c8dda8b42d6e4b89852c1640eb03
```

### 8.4 D001-P Hybrid M120

```text
mpiexec -n 8 /home/Projects/MyFEniCS/.venv/bin/python -m benchmarks.run_task032_phase6_augmented --degree 6 --h-nm 10.0 --bottom-interface-nm 10.0 --top-interface-nm 110.0 --incident-grazing-deg 0.5 --incident-phi-deg 0.0 --grating-height-nm 120.0 --grating-width-x-nm 17.0 --polarization-kind p --requested-modes 120 --candidate-modes 240 --solver-path modal-schur-memory-minimal --stage4-full3d-assembly-backend assembly_time_static_condensed --comparison-solver-path fast --verified-clean-sha ff2227cac8a19bd3a4c66279a413f6a34d730098 --output /home/Projects/MyFEniCS/benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/D001-P/hybrid_m120/solver_record.json --memory-stages /home/Projects/MyFEniCS/benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/D001-P/hybrid_m120/memory_stages.jsonl --container-image myfenics-stage4:task28 --container-digest sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d --host-environment-id WSL2-Ubuntu-24.04 --modal-h-nm 10.0 --modal-degree 6 --internal-propagation-model full3d_uniform_cg --internal-traction-model scalar_cg_discrete_derivative --full3d-reference /home/Projects/MyFEniCS/benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/D001-P/full3d/watchdog_summary.json --full3d-reference-sha256 ded92d34a550e6ff50deba4696280666de47e66978e46a6fd8b67c7a2fefc144 --task036-domain-robustness-gate --task036-mesh-axis-cell-counts 6 4 14 --task036-y-invariant-n0-alias-preflight --task036-dtn-direct-projection-audit --task036-scalar-stage4-reciprocal-basis
```

## 9. 这组结果对“还要不要继续 Hybrid”意味着什么

### 9.1 值得保留的部分

- static-condensed Hybrid 在本轮冻结的配对 live-memory authority 比较中大致减半；这不是
  同一 process-tree 采样口径。D005 还证明在一个成功点上，80 个完整通道可以达到近
  Full3D 精度。
- scalar-CG selected propagation、exact traction dual、strong algebraic interface 与 direct
  projection 本身没有在 D001 暴露错误，说明中间传播核心不是首要嫌疑。
- D001 的失败聚类给后续 port 方法提供了非常具体的回归靶标：必须先恢复上下端
  `m=-7,-5,-2,-1` 的 significant co-P 通道，不能只优化 R/T 总量。

### 9.2 不应再继续投入的部分

- 不应把固定 M120、固定全局本征基直接外推到 0.7 nm；0.7 nm 的 generic propagating-mode
  floor 已约 16,029/方向，M120 在物理容量上不成立。
- 不应为当前单一几何继续堆叠一个越来越大的 global ROM，然后期待它能无代价适应几何微调。
  几何变化会改变局部 Schur/port operator；固定基即使在训练点成功，也还要对 held-out 几何
  重新证明。
- 不应继续用增大 M、扫接口位置、放宽 weak-channel 阈值或新增 fallback 来“制造通过”。这会
  增加防御性代码，却不解决 D001 的 trace complement 缺失。

因此，原有 M120 路线的定位应从“候选生产求解器”降为“13.5 nm 回归与机理诊断器”。后续若
继续 Hybrid，应换成局部、operator-aware、可随几何更新的 port 表示，而不是修修补补固定 global
ROM。

## 10. 0.7 nm、最多 2 TiB 时的推荐路线

### 10.1 为什么当前实现不能直接放大

对 `Lx=50 nm, Ly=25 nm, λ=0.7 nm`，generic 三维传播模数量的几何估算为
`2πLxLy/λ² = 16,028.53`，即至少约 **16,029 modes/direction**，还未包括 evanescent buffer。
59,306/方向只是把旧的 3.7× retention 机械搬过去的风险说明，不是收敛 M 预测。

| 机械投影量 | 数值 | 身份/限制 |
|---|---:|---|
| generic propagation floor | 16,029 modes/direction | derived floor；未含 evanescent |
| local FE rows | 923,346,000 | predicted；由当前 mesh/波长机械缩放 |
| local-system row proxy | 924,426,000 | predicted payload proxy |
| 最大单个 all-mode dense multi-RHS 对象 | 1,595.60 TiB | predicted layout；不含 factor、mesh、Krylov |
| 多个显式对象累计体积 | 1,611.30 TiB | cumulative，不是 simultaneous RSS |

所以 2 TiB 不是“再优化一点”就能容纳当前 layout；需要改变表示与数据生命周期。预算必须明确：
按本报告路线使用 **1.5 TiB whole-job design line**、**2 TiB hard stop**、zero swap。若用户说的是
十进制 2 TB，它只有 1,862.65 GiB，不等于 2 TiB=2,048 GiB，正式机器预算前必须锁定单位。

### 10.2 P0：先做严格 y-invariance 资格分流

如果未来“微调几何”仍保证材料、边界、入射和几何在 y 方向严格不变，那么完整三维问题可按
受限模型类分解为二维截面/2.5D，优先考虑 RCWA/Fourier modal、二维高阶 FEM 或二者耦合。
这条路消掉一个空间维度，收益远大于在 generic 3D 上挤几个百分点内存。

但 P0 是**资格 Gate，不是默认假设**：

1. 从 CAD/材料标签证明 y-extrusion，而不是靠图片目测；
2. 证明 source/Floquet 只激发允许的 y harmonic；
3. 用本轮 Ny=4 全通道 alias/非零 n 通道作为受控检查；
4. 选 D005 与 D001 各做一个小网格 2.5D-vs-Full3D 通道向量对照；
5. 任一真实 y 扰动、非零 n 物理耦合或通道 Gate 失败，立即 fail closed 回 generic 3D。

这与旧文档“未来 generic 3D 不得假设 2.5D”不冲突：只有严格通过 P0 的受限几何进入 2.5D
lane，通用服务和三维缺陷仍按 3D 预算。

### 10.3 P1：局部富端部 + localized operator-optimal joint-Cauchy ports

对于真正三维微调，建议保留靠近几何变化处的高保真 3D endcap，不再从一个全局本征模集合里
截 M120，而是在每个局部接口上近似“这个端部实际向外传递哪些 E/traction 组合”。joint-Cauchy
表示同时照顾切向电场和 traction，正针对 D001 的“代数选定空间通过、恢复物理 E_t 失败”。

最小实验只做一个 short-buffer operator fixture，不启动大 PDE：

- 对 D005、D001 及 2–3 个微调几何，构造局部 endcap Schur/transfer action；
- 测 joint E/traction 的奇异值尾、所需秩、held-out geometry error；
- 用 D001 14 个失败通道作 goal vector，而不是只用总 R/T；
- 禁止形成 full dense trace square，记录 simultaneous RSS 预测。

停止条件：所需秩接近 full trace、held-out 几何误差不能通过、D001 significant 通道不改善，或
预测 whole-job peak 超过 1.5 TiB。若通过，再做唯一一个 D001 p6/h10 direct actual；不要先建
大框架、状态机或多个 fallback。

### 10.4 P2：HSS/H-matrix/directional direct 压缩

即使 port 秩可控，0.7 nm 的局部 Schur 与 direct factor 仍可能主导内存。可研究 HSS、
H-matrix、H² 或 directional low-rank multifrontal/direct solver：它们把远距离耦合块用低秩表示，
但近场块保持精确。该路线仍是 direct，不是在本阶段偷渡迭代法。

最小 rank audit：

- 在 13.5、5、2 nm 的小/中 p/h 上抽取真实 Schur/interface blocks；
- 按几何距离和传播方向分块，测 tolerance 下 numerical rank 随波长、p、h 的增长；
- 用实测 rank 拟合 factor memory，不先承诺某个库一定可扩展。

停止条件：rank 近线性随 block size 增长、压缩后预测仍超过 1.5 TiB，或压缩误差破坏 residual/
80-channel Gate。没有 rank 证据前，不值得投入完整 H-matrix solver 集成。

### 10.5 其他可组合压缩手段

| 手段 | 能解决什么 | 不能单独解决什么 | 推荐最小验证 |
|---|---|---|---|
| 多层 static condensation / nested dissection | 精确消去 cell、patch、subdomain interior，降低显式 global rows | 不会自动降低接口物理秩或 LU fill | 小/中网格测 separator rows、factor NNZ 和 RSS 标度 |
| anisotropic hp mesh | 只在材料界面、尖角、短 skin-depth 区域加密，避免全域按 λ 等比例细化 | 不能跳过独立误差/通道收敛；p6h10 对 0.7 nm 不能直接沿用 | 每个波长做 p/h 双轴 anchor，以 full observable vector 冻结精度 |
| 参数化 local ports | 基随局部几何参数更新或从局部字典选取，适应微调 | 固定训练集不保证外推 | train/held-out 几何分离，测端口残差和 D001 失败通道 |
| background 2.5D + local 3D defect | 大部分严格挤出区域用便宜背景，局部缺陷保留 3D | 需要严格的界面/辐射耦合证明 | 一个局部缺陷小模型与 Full3D 对照 |
| streaming / distributed mode ownership | 消灭 replicated `M²`、all-mode dense RHS 的单对象灾难 | 不会减少物理必须保留的模式数 | 先做 synthetic layout memory audit，不跑 0.7 nm PDE |
| material-aware coordinate/Fourier factorization | 对层状/周期界面提高 RCWA 收敛 | 不适用于任意三维粗糙缺陷 | 在 P0 合格几何上对照 2D FEM |

多层凝聚很有用，但只是“把内部变量整理掉”；它不是 port-rank 压缩的替代品。参数化 port 也应
局部更新，不应重新包装成一个跨所有几何/波长的固定 global ROM。

### 10.6 仅供未来新任务重新授权的波长 continuation 与资源 Gate

以下内容不是当前 Task036 的执行计划。只有用户以后为新的任务重新授权 0.7 nm direct 研究时，
才可考虑固定阶梯 `13.5 → 5 → 2 → 1 → 0.7 nm`；每一级都应重新锁定材料光学常数、几何、
p/h、传播通道、port rank 和资源预测，不把上一波长的 M 或误差信用直接沿用。

若未来获得上述新授权，每级备选顺序为：

1. 小网格 Full3D/static reference 或受限 2.5D reference；
2. p/h 离散收敛，检查所有 observable vector；
3. P1 port rank/tail 与 held-out geometry；
4. P2 block-rank/factor memory 预测；
5. preflight 预测 `<=1.5 TiB` 才允许 direct full solve；2 TiB hard stop、zero swap；
6. true residual、R/T/A、A_volume、significant/weak 全通道、接口 E/traction、资源全部过 Gate才下一级。

在 0.7 nm 之前失败就停在当前波长保存 controlled negative，而不是等 24 小时后只得到 OOM。
当前 Task036 不得执行这里的 P1/P2 fixture、rank audit、actual candidate 或 full solve；V8 已
明确撤销 `C1b` 96-RHS teacher 授权并将其记为 `cancelled/not_run`。矩阵自由 iterative/
预条件器已 deferred 到 Task037，但 `Task037 implementation = not authorized yet`；若将来获得
用户授权，应在新任务中独立定义，不能借本文重开 Task036。

## 11. V8 后的归档决策与未来备选

当前正式处置为：

1. **冻结本轮四模型为最终证据归档。** D005 保留成功点回归价值；D001 的
   14 amplitude/8 power failure 保留为未来方法的靶标，但原有 M120 不升级 production。
2. **Task036 到此关闭。** 不再运行新 PDE，不再执行 C1b、P1/P2 fixture、rank audit、actual
   candidate 或 full solve；`C1b=cancelled/not_run`。
3. **P0/P1/P2 只作未来新任务备选。** 若用户以后重新授权，可先判定几何是否严格 y 挤出；
   generic 3D 则从一个小型 P1 rank fixture 开始，只有确有秩余量才考虑 P2。本文自身不构成授权。
4. **Task037 目前只有方向，没有实现授权。** matrix-free iterative 已 deferred 到 Task037，
   但 `Task037 implementation=not authorized yet`；必须等待用户另行定义和批准后才能开发或运行。

## 12. 证据索引与边界

主要 ignored raw evidence：

以下各 `.../` 均相对于完整 artifact root
`benchmarks/artifacts/task036/ff2227cac8a19bd3a4c66279a413f6a34d730098/p6h10_original_success_vs_failure_v1/`：

- `.../D005-S/full3d/watchdog_summary.json`，完整 SHA
  `b6005c54eb4cc54b13dd6ba7b92ee193251d4c36bece86f8e135b8d29e462c97`；
- `.../D005-S/hybrid_m120/memory_sampler_summary.json`，完整 SHA
  `da9b85e1ae2116a4d8e44830506b310569aa35fc6807fd78a1bdbd3fd50c81b7`；
- `.../D005-S/hybrid_m120/solver_record.json`，完整 SHA
  `17b928f75980576589d1a08e15f54580f6dc447545b5e4150714fa7801998d3f`；
- `.../D001-P/full3d/watchdog_summary.json`，完整 SHA
  `ded92d34a550e6ff50deba4696280666de47e66978e46a6fd8b67c7a2fefc144`；
- `.../D001-P/hybrid_m120/memory_sampler_summary.json`，完整 SHA
  `69a3659a209ba6bf5d03c5b84f35a33b5fcbc6a469ba4f0a48c6d6c6e86da16b`；
- `.../D001-P/hybrid_m120/solver_record.json`，完整 SHA
  `9649828223491961b5b90449641ffef4d8f68fd67d5bc3cd469f5b53ce8ef3cf`。

本报告证明的是这两个 13.5 nm、p6/h10 **离散模型**上的 direct 对照，不是连续解收敛证明，
也不是 0.7 nm 可解性证明。没有运行 M160/M240 相邻-M 漏斗、角度扫描、新 port PDE 或任何
0.7 nm PDE。D005 的正结果不能外推到 P 偏振小掠射角；D001 的负结果也不等于所有 Hybrid
思想都不可行，它只否定当前固定 M120 选择空间在该点的完整性。
