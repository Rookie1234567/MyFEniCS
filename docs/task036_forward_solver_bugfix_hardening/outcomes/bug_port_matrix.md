# Task036 bug port matrix

## 1. 用途与源码身份

本表是 Task036 在编码前的只读差异审计。它回答三个问题：旧 surrogate
研究分支究竟发现了什么、最新 `master` 是否已有等价修复，以及本轮允许移植的
最小代码是什么。它不是新的 evidence schema，也不把 surrogate 的 campaign、
dataset、inversion 或 `src/forward_data` 提升到当前仓库。

| 项目 | 值 |
|---|---|
| 起始 `origin/master` | `007298261681014efbe6508ac91c6c3ae9a6a44a` |
| Task036 初始化 HEAD | `e4c7a685f6debaf57f180be354d5b3dc02bab334` |
| 对照分支 | `origin/codex/only-one-13p5nm-surrogate-inversion` |
| surrogate 任务书基线 | `1a55efb4530...`，执行时以远程对象和下列完整 commit 为准 |
| 移植方式 | 只手工移植最小代码块；禁止整体 merge 或 cherry-pick |
| ordinary default | 保持不变；研究诊断与 quarantine 均为显式 opt-in 或 fail-closed |

“切向投影”只比较端口面上的 `E_x/E_y`；“exact variational conormal dual”
直接检查有限元弱式中的界面载荷平衡。前者修复 P 模式被法向 `E_z` 污染的诊断，
后者防止把采样点上的强形式近似误当成严格的 H(curl) 界面条件。

## 2. 逐 bug 移植矩阵

| bug | 失败现象与根因证据 | surrogate commit / 涉及文件 | 最新 master 状态 | 本轮最小修改 | 回归测试与新 PDE | 审计后状态 |
|---|---|---|---|---|---|---|
| B01 DtN tangential projection | `_mode_projection_from_solution` 的分子使用三分量 `E` 与三分量 mode，但分母只用 tangential norm。Case118 修复前 S 差约 `7.7e-14`，P 最大差 `5.252668e-3`；这是 diagnostic bug，不是 P 物理解不存在。 | `2d4b0e2a270f10578eb60ceab3ff0a8ea215ed77`; `src/solvers/dtn_port_3d.py`; synthetic test 原位于禁止移植的 surrogate test。 | **MISSING**：仍为 full-vector numerator，纯 NumPy tangential oracle 和统一 top incident subtraction helper 均不存在。 | 仅把 numerator/reference 改为 `(x,y,0)`；增加 `_sampled_tangential_projection` 与 `_outgoing_projection` 小 helper；不改 auxiliary amplitude 的正式定义。 | 纯测试：oblique S、`E_z != 0` 的 P、lossy-bottom P、top subtraction、非零 order、近零通道绝对误差。PDE：一个 oblique S 和一个 oblique P，必要时同一 P 记录覆盖 lossy bottom；MPI8 独立目录。 | `PORT_REQUIRED` |
| B02 high-order reciprocal trace | 低掠射 F1 中，lifted modal coefficient 曾被当作 degree 0，正负 reciprocal trace 又走独立、病态的坐标恢复。修复前 interior trace residual 约 `6.3e-8`–`7.0e-8`；验证修复约 `2.8e-13`，slave residual `0`，raw reciprocal consistency 约 `3.4e-16`。 | `b16b3ea897cc276da3ebde76b154f5caed2397a9`, `c5f9951508b51cec76436c59e811ae0d72f65180`, `aaab9d11714edc591b19324fe049d9e98dff4a09`; `src/coupling/hybrid_internal_modes.py`, `src/solvers/hcurl_assembly_time_condensation.py`, `src/solvers/hybrid_local_static_condensation.py`, runner telemetry。 | **MISSING/PARTIAL**：真实 FE degree lookup 已有，但 surface policy 仍写 `coefficient_degree=0`；无 canonicalized negative trace、raw consistency Gate 或逐 role reduction audit。 | 用 lifted target-space 的真实 degree 选 quadrature；把 negative traces 表示到已验证的 positive canonical basis；先验证 `surface_gram @ canonical_map` 的 raw relation，再直接使用 canonical coordinates；补 side/role/mode reduction audit。保留现有更严格 tolerance，不移植 right-Galerkin rejected diagnostic 或 Task001 专用开关。 | unit/MPI：p1–p6、S/P、orientation reversal、正负 reciprocal、standard/static、MPI1/2。PDE：F1 S、一个低掠射 P；若相同 run 已覆盖 standard/static，则不重复。Gate 保持 `interior <=1e-10`, `slave=0`, `raw<=1e-12`。 | `PORT_REQUIRED` |
| B03 exact traction dual | 历史 sampled strong-traction density L2 被命名得像 exact dual，并可能进入 formal H Gate。当前 FE row residual 的代数本体是 exact 的，但只返回两个无语义标量；runner 仍用 sampled magnetic continuity 作为正式 H 条件。 | `13aba78c8ef4645a96871ceaf72eeb751b8eb401`; `src/solvers/hybrid_fem_modal_augmented_direct.py`, `src/postprocessing/hybrid_field_reconstruction.py`, `benchmarks/run_task032_phase6_augmented.py`. | **PARTIAL**：exact FE residual 算法存在；详细 dual 口径、operator/RHS/正负载荷尺度、`traction_density_l2_proxy` 与 formal `traction_hcurl_dual` 分离均缺失。 | 增加 `_fe_traction_equilibrium_diagnostics`，保留旧 tuple wrapper；sampled 项明确改名为 diagnostic-only proxy；formal Gate 只读取 exact `traction_hcurl_dual.relative_dual`。 | synthetic exact balance、扰动 modal traction 后 residual 增长、proxy 与 exact 可不同；top/bottom、standard/static、S/P。PDE 与 B02/B04 的代表点复用，不单独扫点。 | `PORT_REQUIRED` |
| B04 propagation / traction / reconstruction beta | E propagation、modal traction 与 H reconstruction 可能使用不同离散 beta。旧 Route A/B 结果说明这不是 p4→p5 跳变主因，但静默混用会让 H 诊断失去物理身份。 | `b16b3ea897cc276da3ebde76b154f5caed2397a9`; `src/postprocessing/hybrid_field_reconstruction.py`, runner。 | **PARTIAL**：coupling 已分别保存 propagation 与 traction beta；E 使用 propagation beta；H reconstruction 仍直接取 `mode.beta`，runner 未把 selected traction beta 传入 reconstructor。 | `ModalFieldReconstructor` 显式接收成对的 positive/negative traction beta，H basis 使用这两个数组；结果同时记录 propagation、traction、reconstruction 的来源和值。 | 纯测试验证 selected traction beta 确实改变 H 而不改变 E，并拒绝单侧/长度错误数组。代表 S/P PDE 与 B02/B03 共用。 | `PORT_REQUIRED` |
| B05 Hybrid-P quarantine | Full3D P 在 F2–F5 residual/energy 通过；Hybrid M40–160 interface E 约 `0.893`，M576 虽 E 约 `1.38e-8`，energy 仍约 `1.7971e-3`。当前 generic status 不能区分物理解存在、modal rank 不足、interface closure 失败和 diagnostic projection bug。 | `fe0e53571491f21e4774d7576d9285f9a09df705`, `97a1df92f19dcd2926536cc37a721e72b2e49963`, `ba50cd36b081637ed5ea97c2dc8e4827d992b940`, `eaf17cd01f9e69eff4575b83ea94490a453e09bb`; surrogate `src/forward_data` 只作证据，禁止移植。 | **MISSING**：通用 gates 存在，但 P 可能只得到泛化的 `physical_integration_*`；无四类状态和显式 `hybrid_p_production_qualified=false`。 | 在现有 runner 增加小型状态分类器；不改变任何数值 Gate。只有显式 Full3D authority 才标记物理解存在；rank、interface/energy、projection bug 分别给 reason；P 始终 quarantine；显式 Full3D fallback 不得伪装成 Hybrid pass。 | 纯 classifier 测试覆盖四种状态、P 永不 production、fallback 身份。PDE：一个 P 代表点和一个原通过 S control；不运行 M 网格。 | `FAIL_CLOSED_REQUIRED` |
| B06 near-degenerate block split | p6/45° 把 `[114,115]` 与 `[116,117]` 分为相邻 blocks；global row-sum identity error `1.7765586e-6 > 1e-6`，worst cross overlap `1.0381412e-6`。right/left QEP residual 均约 `1e-16`，故根因是 block partition，不是 eigensolve 失败。 | evidence `38fdd7f157556db2caec85e00a1d7f07f22cd5d6`; base implementation `72dca66b70515bcf6ccef239005afa43028df72b`; `src/modes/mode_classification.py`. Surrogate 的 `8973e046...` 是 reciprocal-negative diagnostic，不是 B06 修复。 | **MISSING**：`block_rotation_tolerance` 被校验但未实际用于 grouping；逐 block inverse 后没有检查全局 cross-block identity。 | 先实现小型 deterministic partition-split audit，并在 Hybrid solve 前 fail closed。只有能在 90 分钟内用现有 union/joint inverse 局部、安全合并时才修复；否则保留 `DEFERRED_ARCHITECTURE_REQUIRED`，不接新 continuation framework。 | synthetic split detector/可能的 merge；existing tracking/subspace tests。PDE：仅一个 p6/45° anchor；阈值保持 `1e-6`。 | `FAIL_CLOSED_REQUIRED`; numerical merge `CONDITIONAL` |
| B07 Ny trace alias | Ny3 在 `2ky≈3Gy` 把 `n=0` 与 `n=-3` 离散 trace 混合：leakage power `1.231232e-6`，max amplitude `1.014657e-3`，bottom-S overlap `0.3630`；Ny4 overlap 约 `2.68e-16`，leakage `3.278e-25`。q21–63 不改变结果，排除 quadrature。 | diagnostics `0a53c42397a2e67f64e8f6dae2c680bfe3fe4b95`; evidence `4380c1d0231cfc09b78981aa9db160502f0f79d4`; Ny4 surrogate production change `2d4b0e2...`; `src/common/config_3d.py`, `src/solvers/dtn_port_3d.py`. | **PARTIAL**：generic exact axis counts 与 actual resolved counts 已有；缺 planned-vs-actual fail-closed 以及 y-invariant/fixed-n0 的真实 MPC trace overlap preflight。 | 新增 ordinary-default-off 的 y-invariant n=0 声明；校验 planned/actual `(Nx,Ny,Nz)`；复用现有 surface assembler 构造真实 tangential MPC trace，计算 n0 对 relevant n!=0 normalized overlap；冻结 `1e-8` preflight threshold，超限建议 Ny refinement。不得硬编码 Ny4，后验 leakage Gate 不变。 | unit：count mismatch、overlap helper、Ny3 fail/Ny4 pass fixture。PDE：同一物理点 Ny3 controlled rejection 与 Ny4 pass；不跑 bulk/角度扫描。 | `PORT_REQUIRED` |
| B08 MUMPS factor NNZ overflow | p6/h5 的 PETSc raw `-2017967296` 与 MUMPS `INFOG(9)=-2277` 表示实际 `2,277,000,000` entries。当前负值可进入 fill/资源模型。 | Task035e compact/documentation evidence；surrogate 与 master 的 `src/solvers/common_3d_solve.py` 相同，均无修复。 | **MISSING**。 | 增加纯 helper：仅 `factor_solver=mumps` 且 `INFOG(9)<0` 时用 Python `int(abs(v)*1_000_000)`；raw PETSc/INFOG 原样保留；inventory 增加 corrected/source；fill consumers 优先 corrected。 | 纯 mock/unit：真实值、`>2^31`、正 INFOG、非 MUMPS、raw 不变。**不得重跑 p6/h5**。 | `PORT_REQUIRED` |
| B09 solver lifecycle | Full3D 已可在 field recovery、true residual 和必要回代后释放 KSP/MUMPS、A/b/x；Hybrid runner 仍把 factor/system 保留到 physical reconstruction 与 record 尾部。`malloc_trim(0)==0` 只说明本次无页归还，不是数值失败。 | Full3D sources `178326d`, `0f8924a`, integration `06c3e95`; `src/solvers/common_3d_case_flow.py`; Hybrid 当前 runner/solution classes。 | **PARTIAL**：Full3D `VERIFIED_PRESENT`；Hybrid gap；部分旧 Task035d checker 仍把 trim return 0 当资源失败。 | 不改 Full3D 算法；把 trim 的“调用成功”和“实际归还页”分开。Hybrid 在 validation/factor inventory/field recovery 后复制所需标量，再显式释放 factor/system，防 use-after-destroy；记录 release 前后 RSS，不宣称结构压缩。 | 现有 Full3D lifecycle tests；新增 Hybrid idempotent early-release/use-after-release test。PDE 与 Hybrid S/P 代表点复用，比较 release stage 与数值不变。 | `PARTIAL_PORT_REQUIRED` |
| B10 memory/MPI identity semantics | 不同 rank 的历史峰值相加不是同一时刻内存；分区相关 vector bytes/hash 也不是物理 identity。 | 当前 `src/solvers/common_3d_utils.py`, `src/solvers/common_3d_case_flow.py`, `benchmarks/run_task033_full3d_watchdog.py`, `benchmarks/task034_mpi_identity.py`; 禁止移植 surrogate telemetry framework。 | **MOSTLY VERIFIED_PRESENT**：同步 process-tree/cgroup authority 与 historical upper bound 已分开；日志仍把 upper bound 简写为 `total peak RSS`，vector-hash scope 可更明确。 | 只修标签/docstring/identity scope；不建新 telemetry。外部 sampler 优先；无 sampler 保留 `historical_upper_bound`。 | 纯测试日志标签、historical/simultaneous 不混称、MPI identity 不读取 partition-sensitive hash。已有 watchdog 测试复用；无需专门 PDE。 | `LABEL_HARDENING_REQUIRED` |
| B11 DoF semantics | variable-p 同时存在真实 active exact-sequence DoF、p6 storage carrier、independent trace rows 与 augmented matrix rows；旧 `num_nedelec_dofs`/`num_active_condensed_dofs` 名称不足以区分。 | 当前 `src/solvers/hcurl_assembly_time_condensation.py`, `src/solvers/hcurl_variable_p_reduction.py`, `src/solvers/dtn_port_3d.py`, `src/solvers/common_3d_case_flow.py`. Surrogate 不含 Task035d variable-p 源码，不能作为移植来源。 | **PARTIAL**：底层数值已存在，顶层统一四字段契约缺失。 | 保留旧字段兼容，新增 `num_active_exact_sequence_fe_dofs`, `num_storage_carrier_fe_dofs`, `num_independent_trace_rows`, `num_augmented_rows` 与 semantics map；不得用 Full3D-equivalent 替代实际 rows。 | 复用 p5-trace/p6-interior 与 selective-face 小 fixture，检查四字段关系和 matrix row identity；无需新 heavy PDE。 | `PORT_REQUIRED` |

## 3. Surrogate 根因证据身份

下表只绑定旧分支上的轻量审计入口；不把这些 records 复制进 Task036。

| bug | 历史文件 | SHA-256 | 用途 |
|---|---|---|---|
| B05 | `benchmarks/cases/111_task001_illumination_robustness/records/diagnostic_matrix.json` | `91443bb8095761959033a530a63e03e9a7e49d12142c7891149803bc05be0590` | Hybrid-P rank/interface/energy 分离 |
| B05 | `benchmarks/cases/111_task001_illumination_robustness/records/direct_references.json` | `fd67131e6acdc00f566c8e50b5c39835032d59f26e0a81c6230db4a726118d32` | Full3D P 物理解存在 |
| B05 | Case115 quarantine compact | `7e3cda2cd8be397c3b879539f3600f19f0f8bbe1133fe0332e0ae399238b4ffe` | production quarantine |
| B06 | Case114 `mode_continuation.json` | `3af0c41fdde1c1a41310c3d4c367184772d604bc6a2494958dfb2950aa4473f1` | p6/45° block split；原文件约 4.8 MB，不复制 |
| B07 | Case118 `y_cell_convergence.json` | `17d218a902259c5e515d23264f4816b8abe80fb7444cec2e0b3d9a4c89569364` | Ny3/Ny4 PDE 对照 |
| B07 | Case118 `port_vector_gram_condition.json` | `31c3b88469e406ad210ff4e5a3fadedfbc73bba6ab7d90b45f795fb44ccb9629` | 实际 trace overlap |
| B07 | Case118 `solver_route_decision.json` | `92f96efbb7cafd2e69b1cff0f376c0443d9625a691498aa1957845073d1f4188` | quadrature 排除与 Ny refinement 决策 |

## 4. 明确不移植与 deferred 边界

| 内容 | 处理 |
|---|---|
| `src/forward_data`, surrogate campaign/dataset/inversion | `DO_NOT_PORT` |
| Task001 right-Galerkin trace-test diagnostic | rejected diagnostic，`DO_NOT_PORT` |
| Task001/002 专用 M9、M2A/M2B/M4D runner gates | 不进入公共源码；只复用根因与最小数学修复 |
| Hybrid-P 新模态架构 | `DEFERRED_ARCHITECTURE_REQUIRED`；Task036 只 quarantine/fail closed |
| 跨角连续 mode identity 新框架 | 不开发；现有 overlap/subspace API 仅作检测依据 |
| `_active_trace_values_from_augmented` 全局 allgather、replicated `M^2`、iterative solver | 技术债；不属于 Task036 |
| p6/h5 factor telemetry | 只离线/单元修正，不重跑 PDE |

## 5. 回归调度边界

用户已明确允许 Task036 为独立 bug 回归同时运行最多五个 MPI8 模型。该授权覆盖
任务书原来的“一次一个 PDE”调度限制，但不放宽任何数值 Gate，也不授权 bulk
campaign。正式运行前仍要做可用内存、swap、磁盘和 CPU oversubscription 预检；
若五个模型的保守内存和超过安全余量，则自动降低并发数。

每个并发模型必须有唯一的：

- case/run ID 与完整 command；
- output、stdout/stderr、TMP/TEMP 和 MUMPS OOC 目录；
- 完整 source SHA、ABI、MPI/线程身份；
- watchdog/process-tree authority 与 cleanup 状态；
- 独立结果文件和 Gate 判定。

任何文件路径冲突、共享 scratch、source drift 或结果 identity 不完整都会在启动
前 fail closed。并发只用于互不依赖的回归点；同一个候选的阶段、重试和上下游
依赖仍串行执行。
