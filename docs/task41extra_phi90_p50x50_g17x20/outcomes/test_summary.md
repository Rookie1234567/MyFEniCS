# V17 两单元收口与既有测试记录

| 项目 | 结果 | 说明 |
|---|---|---|
| V17实现阶段定向回归 | 47 passed in 15.72 s；主控冻结快照独立回归48 passed in 15.74 s | qualified activation；第二批包含一项V15合同兼容回归。两批是各自独立运行，不合并统计 |
| native ABI preflight | PASS：PETSc complex128/int32、native Linux ABI paths、MPI1；ABI receipt SHA-256 `1c4277c83a0ac6daf02197086264b9e5b337caee1b33d7cc1dd22a7dfcefe57d` | 真实工作站native环境身份，详见V17 service receipt |
| attempt04 producer与attempt05–07 saved-only checker | attempt04执行有界两单元producer；attempt05/06/07复用producer报告，attempt07为`LOCAL_REPLAY_COMPLETED`，`check_completed=true`、`data_integrity=true`、`errors=[]`；110个NPY / 75,253,856 B | 真实read-only checker收口，attempt07不是pytest，也不代表global action pass |
| 本轮文档收口 | 没有重跑测试 | 只编辑文档和轻量JSON证据；未运行全仓pytest、未声称CI通过 |

主控后续最小回归（分别在各自冻结前完成，不能累加为一套测试；原工具记录未另存日志，日志hash为UNKNOWN）：

| 冻结源码 | 直接修改范围 | 独立结果 |
|---|---|---|
| `56ff5a60` | live resource callable调用链 | 1 passed，0.08 s |
| `436bb69e` | producer/consumer checker授权及loader链 | 2 passed，0.15 s；另2 passed，0.15 s |
| `adf3483d` | Decimal J/scatter及真实callback→checker | 3 passed，18.19 s |
| `17df17b3` | 保存initial/final有符号变化 | 1 passed，19.90 s；先前fixture把数值零的字符串`0.0`与`0`比较导致失败，改数值比较后通过 |

详细命令和数值边界见[response_v17](../response_v17.md)、[compact](v17_closeout/v17_two_cell_compact.json)及[attempt index](v17_closeout/attempt_index.json)。以下测试条目均为各自历史source/环境的独立记录，不可累加成单一套件结果。

---

## V16定向验证与真实保存服务（2026-10-27）

- 最终分析源码：`086c884121575c8a9662cd0f500a5287a36a79b8`。执行者在对应未提交补丁上运行资格化WSL测试：`source scripts/activate_myfenics_wsl.sh; PYTHONDONTWRITEBYTECODE=1 python -m pytest -q --tb=short -p no:cacheprovider src/test/test_task41_p0_v16_saved_vectors.py`，**20 passed in 1.10s**；随后主控审核三行diff并冻结，没有再改源码。原独立测试输出未归档为文件，日志hash为UNKNOWN，结果依据执行者工具记录。
- 直接范围：V9二维/V15一维layout与hash污染拒绝；互斥MPC能量；旧producer/新consumer窗口；V3 basename的两条真实caller；完整10-cell库存中精确2-cell incident；保存correction污染拒绝；j0/j3绑定、固定最终z宽算术诊断；replay complete字段。
- service-selector最终改动在`2de17690039cc856d0e5f00df3eaf657c7d3886f`前后定向7项通过（3.75s）；后续仅checker/fixture变化。没有运行全仓pytest、MPI2/4、旧完整审核或PDE；未声称CI通过。
- 实际工作站attempt12的现有service→watchdog→saved checker全链完成；源码`086c884…`，ABI收据SHA`1c4277c83a0ac6daf02197086264b9e5b337caee1b33d7cc1dd22a7dfcefe57d`，complex128/int32、MPI1/math1。data_integrity=true、errors=[]、COMPLETED_DIAGNOSTIC_ONLY、official_result=false。
- attempts01–11全部原始错误和费用保留在[attempt_index](v16_closeout/attempt_index.json)；第11次已正确重放但缺complete字段，第12次仅重读已保存B产品，A/meta复用。Ruff未安装（NOT_AVAILABLE），未为此安装工具；最终diff/JSON/hash/link检查单列收口结果。

## V15最终收口定向测试（2026-10-27）

- 科学source：3b8e7f5327ce1905deae658bd0bbb0fa94dba5ad；终态审核修复source：c14dcdb4f3df5e1f488de6747008edf6d58c0c3f。
- qualified WSL complex128/int32，11 passed, 95 deselected in 1.54s。仅终态调用链、artifact摘要/污染拒绝和新回执CLI/保存路径相关测试。
- 命令：`python -m pytest -q src/test/test_task41_p0_contract.py src/test/test_task41_v4_volume_only_audit.py -k 'prepared_contract_authorizes_actual_terminal_watchdog or outer_worker_propagates or v15_terminal_sufficient_producer or v15_prepared_contract_compact_terminal_run_chain or v15_terminal_rejects_corrupt or v15_cli_and_persistence_accept_registered_recheck'`。
- 工作站实际只读checker完成：数据完整、两列action FAIL、recovery NOT_RUN。测试通过不替代数值门。
- 原hash口径错误、两次recheck入口失败及旧测试fixture错误保留；未运行全仓pytest或新增PDE。

# Task41 P0 定向验证

## V14 最终冻结源码定向回归

| 项目 | 记录 |
|---|---|
| 最终源码身份 | HEAD `eb57f88f26fb3cbbe0d7c34ebb725f9a6b310fe1`；相关15个源/测试文件补丁 SHA-256 `e64a266cec40bc054652623bb1bf320e2b312c3ba5eca288c614598c63ab2af2` |
| 环境与命令结果 | 资格化工作站环境；7 passed in 9.15 s；测试日志 SHA-256 `54397e91fa48c6889c4b2b969c5d91d14258c864cc9464b12e4c40f32006ebb3` |
| 覆盖范围 | prebuilt owner 绑定 live strategy、实际 K 与 LU identity；P6 最终 z、Di、recovery 与 borrower 清理；V14 saved candidate/star-extension 回归 |
| 具体新增 owner 节点 | `src/test/test_task40_v10_p6_yorbit.py::test_fixed_two_prebuilt_owner_binds_live_strategy_and_actual_k_lu_identity` |
| 结果边界 | 验证窄生产接线和回归；没有运行全域 action/recovery、official terminal checker、FE/PDE、200q、factor、KSP/FGMRES、完整场或 R/T/A |

前一轮 snapshot 结果为 **16 passed in 10.27 s**，源码 `d311d20cf9d9ea1bafe3aefe9d6446d2570335a8`、补丁 SHA-256 `06b8e3b16cb834fc152ffa9d8a756ceb248eb63f11928fcd1bec1cd19c5e303b`，日志 SHA-256 `fb1385482a4bcad7311a35ff19625734f1139a5f913eda3a83e9aabefbbc7d31`；它与最终 eb57 冻结后的7项复核分开记录，不把两批测试合并计数。未运行全仓 pytest，未声称 CI 通过。

V14 服务候选 / wide checker / Decimal 补充复核不是 pytest 结果，分别记录在 [V14 response](../response_v14.md) 与 [closeout evidence index](v14_closeout/evidence_index.json)。

## 历史定向验证

本页记录正式计算前的输入、数值接口和监督接线检查。它们用于避免在昂贵求解后才发现入口错误，**不代表13.5 nm完整场、A1/A2对照或0.7 nm计算通过**。

| 检查 | 结果及边界 |
|---|---|
| 资格化本机 ABI | complex128/int32、MPI1；沿用既有独立运行库，本机测试并非工作站正式计算 |
| G13新物理/DAT | 方位90°、掠角1°、S、完整居中矩形；非平凡y Floquet；真实轴计划10×10×14；正式网格仍待生成核验 |
| 极小真实MUMPS调用链 | 2×2 complex矩阵验证symbolic、numeric、控制读回和因子释放；小矩阵INFOG舍入0MB，测试专用1MB资源样本与原读回分列，生产门未改变 |
| 新合同和窗口 | 精确纳秒、窗口初始source与运行source分列；失败保留T0，新source合同不覆盖旧合同 |
| 无FE监督调用链 | 真实launcher和service分派，实际closeout授权函数；worker、资源和activation/preflight用测试替身；不声称实际工作站service已启动 |
| 最终定向pytest | `src/test/test_task41_p0_contract.py`、`src/test/test_task41_g13_direct_input.py`：**15 passed in 0.65s** |
| compileall、wrapper bash -n、git diff --check | 通过；只检查修改相关文件 |
| Ruff | NOT_RUN：资格化runtime未安装；未为此修改环境 |
| 正式FE/service/独立物理场 | NOT_RUN；冻结源码后依现场准入启动 |

已有负记录保留：早期轴计数检查误读fallback mesh_cells；新增控制链fixture最初缺少模拟资源回执的launch_envelope字段，定向修正后通过。未发生为这些字段问题重跑正式PDE。

最终测试工具回执：`benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_controller/final_targeted_tool_receipt.json`（ignored原始工件），工具ID `exec-de1bd6eb-a8ff-4b71-8f65-d4e9d8ee2c6b`。测试发生于任务书提交 `a3f431f519eb5a461a6dd85ffab7f2acde934cec` 上的本次实现工作树；主控随后统一冻结相同源码。未运行全仓测试，无CI通过声明。

正式入口由 `python -m src.runners.task41_p0_contract --prepare --runtime-prefix ... --abi-receipt ... --jit-cache ...` 输出。正式prepare只由主控在源码冻结、现场资源及共享工作站排他检查后执行；时间窗172800秒（数值171600、收口1200），本轮测试没有登记正式窗口。

## A1 启动修复与实际结果

service 环境删除继承的 V29 factor-only 标记；回归显式注入旧标记并核对 Task41 contract/window 仍正确传递。修正后的定向测试 `test_task41_launcher_and_service_pass_real_window_resources_and_checker_authority`：1 passed（0.16 s）；原始工具 `exec-d46d0a4a-d3e3-4693-821d-dab6751ab1a9`。此前缺少显式注入的测试回执保留为不充分证据，不用其证明本 bug 已覆盖。

正式 A1 source `4e46e524f1a5ebbc83218e615631c2477698347a` 的实际完整场及 required checker 已通过，详见 [summary.md](summary.md)。A2 本地未提交改动的测试不代表 A2 正式场通过。

## A2 冻结前定向验证

A2 接通同物理 G13、168 模式、10 q / 5 sector、全部准确因子驻留与六类完整参考检查。q1/q2 虽无端口仍保留 FE 分块。与 A1 的比较使用保存总场、完整独立自由度上的 E / scaled-curl 体积范数、物理边界坐标复振幅及全模式功率；不拟合相位，不把 sampled witness 当全体积误差。

- 资格化环境：既有独立 `local_w0_wsl/runtime_prefix`，PETSc 3.25.6 / complex128 / int32、MUMPS 5.8.2；MPI1、数学线程1。测试不是正式工作站 A2 场。
- 最终命令：`python -m pytest -q --tb=short src/test/test_task41_p0_reference_audit.py src/test/test_task41_p0_contract.py src/test/test_task41_g13_direct_input.py src/test/test_task40_v10_p6_yorbit.py src/test/test_task40_v10_p6_mumps.py -k task41`。
- 结果：**27 passed, 57 deselected in 1.94 s**；工具回执 `exec-dd618e6d-910c-4f79-b5d6-36d31cf3e6ab`。包含真实小矩阵十 q MUMPS 两 RHS、生产持久化格式独立回读、弱模式入射尺度、完整 independent rows 及 A1/A2 watchdog 路径。
- 最终相关 `py_compile` 与 `git diff --check` 通过。未运行全仓测试；未安装或更换运行库。
- 负记录保留：旧 `.venv` 路径断言及整个 PATH 字串检查曾误拒绝正常环境；均发生在数值测试之前。修正为读取本轮指定运行库与实际模块来源，没有改变科学门限。A2 summary 路径错配在正式运行前修复；A1 raw 不修改、不重跑。

测试基于 `38acbfec3868a744df85c6c8a73e478c937fc948` 上的最终未提交实现，主控随后冻结同一源码；正式 A2 结果另由实际 run/source/checker 记录，不能由本页测试数宣称通过。用户已明确允许资源合格时与邻项目并行，仍保留独立 cgroup、动态准入、至少64 GiB宿主余量、任务swap0；不停止或修改邻项目。

## A2 dispatcher 定向修复

真实 A2 DAT 经 resolver 与 dispatcher，只有数值 worker 使用替身：两个明确的旧授权键仅在值为 `False` 时允许，`True` 及其他 Task40 路由均拒绝。主控复核 1 passed in 0.41 s，工具 `bdb0ea`；源码提交 `432672a0b13a6863176e550267cdb67aa3c1010a`。随后真实启动发现独立的 runtime 资源/窗口接线问题，保留该负结果，不用此单测宣称正式计算已通过。

## A2 runtime 与固定窗口接线修复

新增 Task41 专用只读窗口分支：worker 读取同一合同/窗口/服务资源字段，保持固定 cap、64 GiB 宿主余量、strict cgroup 与任务零 swap，不落入旧 Task40/V14 账本。真实 A2 DAT、实际 `_V14Runtime` 和候选合同在一条轻量 fixture 中联通；Git/旧 A1 artifact 仅用局部替身，不启动 FE。定向测试 **1 passed in 0.24 s**，工具 `exec-847d577e-8805-4e72-9a29-3263d4041ce8`；相关编译与 diff check 通过。旧 PATH 字串预检误报保留为工程记录，实际 Linux runtime/ABI 正确，未修改环境。新正式 attempt 的实际结果另行记录。

## A2 ABI 分派修复

Task41 strict A2 通过本场合同绑定 native_linux receipt；拒绝 WSL receipt 或 V30/V31 混用，共用原实际模块、版本、complex128/int32、MPI1/math1 检查。局部 fixture `test_task41_a2_abi_uses_native_contract_route_and_rejects_local_receipt`：1 passed in 0.27 s；含真实本机 WSL ABI 回归，但不是工作站 native 正向通过声明。相关 compileall/diff check 通过；主控冻结后另做工作站 imports-only 正向核验。


## A2 attempt4 递归故障修复与 q0/q5 复用回归

attempt4 在 q0、q5 的完整 CSR/native 检查通过后、外层迭代开始前停止。旧 stage 记录把可变记录表直接嵌入 sector-ready 审计，再由持久化回调写回当前记录，形成 JSON 序列化递归；这是工程日志故障，不是数值或资源门失败。提交 a1470688c2d0eb297abebce17d8ed4af0d661aa6 改为保存浅快照，不改变数值动作、阈值或算子。q0/q5 的旧生产者资格原样保留，由 952bb2a9fa414d85de0b223bdbd569744fd252c5 增加窄范围 hash-bound 导入，其他 q 仍按当前合同计算。

正确 Task41 C1 activation 下运行四文件完整定向回归，未筛选、未排除：

    source scripts/task40_fresh_c1/activate_local_wsl_complex.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit
    python -m pytest -q src/test/test_task41_a2_q_csr_reuse.py src/test/test_task41_p0_reference_audit.py src/test/test_task40_v30_qualified_q_csr.py src/test/test_task41_p0_contract.py

结果：**22 passed in 1.22 s**；git diff --check 通过。此前 generic activation 下三个 Task41 fixture 因没有使用本任务 C1 runtime/fixture 前提而失败；以上 C1 命令无筛选地复核全部 22 项，三个 fixture 均通过，按环境选择不匹配关闭，不触发环境重装或源码扩修。

attempt5 已用 source `952bb2a9fa414d85de0b223bdbd569744fd252c5` 在原 A2 固定窗口启动，并于 **2026-10-17 01:02:57 UTC** 失败退出（service `myfenics-case-20261017T004743-1655297.service`，worker exit 4）。q0/q5 已导入并保留原资格；q1/q6 sector `[1,6]` 在 q1 数值填充阶段失败，触发 `ValueError: selected q map needs nonempty trace and port columns`。live trace 列为28,440，q1映射共28,440列、端口列为0；行数检查绑定 live `action.reduced_size`，profile派生期望为182,880，但失败运行没有单独保存该映射的完整shape。异常发生在 operator identity 比较之前，属于构造守卫错误；外层迭代没有开始，不是FE收敛或资源门结果。进程树已清理；峰值进程树RSS为3,481,264,128 B，专用任务cgroup内存峰值2,955,980,800 B；两种内存口径分别记录，进程树和cgroup swap峰值均为0。完整compact记录见 ignored `benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a2_controller/a2_attempts_compact.json`，run_index保留原固定窗口和失败状态。


### q1/q2 零端口映射修复与回归

修复将保存映射、native qualification 和成对 native route 的条件改为“trace列必须为正，端口列允许为零”。q1的空端口split仍保留完整向量长度和trace分量；CSR/native动作、组件重组、双向配对泄漏与checker的 `1e-11` 门限未变。q1零参考输出仍必须与零native输出一致，测试也确认非零误差继续被拒绝。checker fixture现在包含q1零端口、q6非零端口，且保持q0/q5 saved import路径。

Task41 C1 activation 下最终定向测试：**3 passed in 1.07s**，覆盖实际G13本地维数（182,880 reduced rows、126,000 active rows、56,880 appended rows、28,440 trace列）上的 q1 pattern/numeric build、0×0 direct-H项、q1与q6两个方向的native分量/配对/qualification，以及checker独立重算。命令为：

```bash
source scripts/task40_fresh_c1/activate_local_wsl_complex.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit
python -m pytest -q src/test/test_task41_a2_q_csr_reuse.py::test_task41_a2_zero_port_q1_build_and_native_pair_with_q6 src/test/test_task41_a2_q_csr_reuse.py::test_task41_a2_saved_q_binding_rejects_changed_authorization src/test/test_task41_p0_reference_audit.py::test_task41_a2_reference_checker_reapplies_real_ten_q_packets
```

三个修改过的Python文件通过 `py_compile`，`git diff --check` 通过。本次定向验证未运行PDE、全仓测试或Ruff。主控复验同三项：3 passed in 1.02s；此次源码冻结后沿原A2窗口续作。attempt5负结果及资源事实保持原样，不用单测替代正式A2运行。


## A2 attempt6：V15 profile 准入失败与修复验证

attempt6（2026-10-17 01:21:51 UTC，source ec22d658e03df3648d5628fa82c9dba4026a803b）在十个 q 的 MUMPS numeric、第二 RHS 严格残差和 CSR/native 资格通过后，于 V15 candidate profile admission 失败；worker exit 4、official_result=false，外层迭代未开始。错误为 V15 只接受 Task40 登记 profile。该工程负结果保留在 run_index；未形成完整场、独立 A6 残差或 official R/T/A。

随后源码增加 Task41 精确 profile capability、全十 q 保存 CSR/native 导入及逐 q 新 consumer 授权；旧 v1 q0/q5 twist-zero 只读核验保留，v2 要求 q0..9 全部齐备，缺失即拒绝。Task40 shared selector 与 V13 四-q逻辑未改，未重跑 producer/native，也未启动 FE/PDE。

C1 qualified runtime preflight 为 PETSc complex128/int32、MPI1、SLEPc 3.25.2、DOLFINx 0.10.0。定向命令（2.25 s，67 passed）：
source scripts/task40_fresh_c1/activate_local_wsl_complex.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit
python -m pytest -q --tb=short src/test/test_task41_a2_q_csr_reuse.py src/test/test_task41_p0_reference_audit.py src/test/test_task41_p0_contract.py src/test/test_task41_g13_direct_input.py src/test/test_task41_v15_reference_capability.py src/test/test_task40_augmented_reference_correction.py

相关文件 compileall 与 git diff --check 通过；Ruff 未安装。主控在 C1 下独立复核 profile capability 两项、真实 V15 candidate 链一项、q_csr_reuse 全文件及 reference_audit 全文件，共 11 passed in 2.49 s。另一次额外 Task40 route 批次命令为 python -m pytest -q --tb=short src/test/test_task40_v16_routes.py src/test/test_task40_v17_row_tile_routes.py src/test/test_task40_v20_routes.py src/test/test_task40_v18_ny8_operator_reuse.py，结果 73 failed、76 passed、1 skipped。该批未诊断；代表栈为 src/test/test_task40_v16_routes.py:39 经 src/io/input_validation.py:532 报 solver.initial_guess: missing required field，失败发生在 profile inventory 前。原始输出未另存文件，位置为本次 Codex 任务 exec session 82727 的工具输出；未将全部失败归因于该代表栈，也不与 Task41 定向结果混并。

## A2 attempt7 保存场续作修复（尚未正式续作）

原 attempt7 已完成 6 次外层迭代，原 A6 为 7.381572880480822e-08；随后在 A1 保存场自检阶段以 WORKER_FAILED 退出。A1 保存向量是 slave-zero 存储，正式输出使用 MPC 恢复后的物理场；修复在比较时恢复约束值，旧向量、source 和失败记录不改写。当前新增受既有 service/watchdog 监督的保存场续作，仅重建必要 FE/MPC/指标及检查，不重新装配 q、分解或 KSP。

诊断衍射表的 289 个空间级、578 个偏振条目与 168 个正式 DtN 端口分开验证。续作沿原 A2 窗口和资源合同，旧生产者与新 consumer 源码分别绑定。checker 输入保存为不可变快照，原输出硬链接在处理后按完整文件名、字节、hash、设备/inode 再核验。

最终 C1 定向测试：`python -m pytest -q src/test/test_task41_p0_contract.py src/test/test_task41_p0_saved_output_continuation.py src/test/test_task41_p0_reference_audit.py`，20 passed in 1.34s。修改文件 py_compile、启动脚本 bash -n、git diff --check 通过。初次临时 ABI 检查误断言 .venv 前缀而失败；实际 C1 runtime_prefix/bin/python、complex128/int32、MPI1 及原包版本读回正常，未修改环境。Ruff 在当前环境不可用。

该测试结果不是 A2 最终验收；完整同离散比较和 required checker 待保存场续作完成。

保存场续作首次 service 在启动 worker 前因错误属性 `FixedCampaignWindow.numeric_seconds` 退出；正确 API 为 `cutoff_seconds`。旧 unit `task41-p0-a2-saved-output-attempt7.service`、失败收据及 2.372285548131913 s 保留，未运行 FE/因子/KSP。一行修复后，fixture 改用真实 FixedCampaignWindow，验证 numeric cutoff、closeout reserve 与原 window/hash；仅该回归 1 passed in 0.25s，相关 py_compile 与 diff 检查通过。重试使用独立输出目录和 unit，T0 不刷新。


## A2 保存场 checker schema 修复定向验证

冻结 source `4c0af8c1e73a47337b497f3a5ccda64933d04591` 的 checker 将审计实际字段 `q_indices` 与生产者输出结构对齐；fixture也改为真实 producer-shaped 审计对象。Task41 C1 资格化 activation 下运行 `test_task41_a2_reference_checker_reapplies_real_ten_q_packets`：**1 passed in 1.49 s**；相关 `compileall` 与 `git diff --check` 通过。没有重跑测试集或 FE/PDE；随后工作站 checker-only retry3 对 hash-bound 保存输入得到 `PASS`。该 checker 重算保存动作代数，但没有重新组装 FE 算子。A出口现已通过；完整服务与证据身份见 [a2_saved_output_checker_retry3.json](a2_saved_output_checker_retry3.json)。

## B0 profile capability 与 checker 接线

B0 的 V15 参考预条件器需要完整 200 个 q 分支、100 个两胞 sector 的维数；若 checker 只信 worker 摘要里的计数，就无法确认运行文件是否仍与源摘要一致。本轮把72.6 MB模式manifest与q分配文件的身份、字节数、SHA-256、q/sector计数复核集中在 `recheck_task41_b0_mode_inventory`，worker、B0数值checker和独立输出checker复用该入口，再从核验后的 capability 重建动态 profile。模式/分支文件在本轮测试中用 fixture 复核；没有重新生成先前清点的模式，也没有启动FE网格、service、factor或PDE。

另修正 required-checker 授权记录：B0 迭代checker不再被标为A1的full-A6 checker；service与watchdog现在按同一个case映射使用 `task41_p0_b0_independent_iterative_checker`。定向合同测试覆盖B0从执行合同到watchdog closeout授权的完整只读路径。

资格化环境为本机C1 runtime，Python位于 `local_w0_wsl/runtime_prefix`，PETSc为complex128/int32、MPI1；ABI preflight及相关模块 `compileall` 通过。最终命令：

```bash
source scripts/task40_fresh_c1/activate_local_wsl_complex.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit
python -m pytest -q --tb=line src/test/test_task41_b0_dispatch.py src/test/test_task41_p0_contract.py src/test/test_task40_augmented_reference_correction.py src/test/test_task40_v10_output_checker.py
```

结果为 **85 passed, 5 failed in 8.98 s**；失败的5项全部是Task40 V19生命周期fixture，不是B0测试：两种注册profile的V19 dispatch fixture、`test_v19_output_checker_accepts_repeated_one_slot_refactors_and_disjoint_counts`、`test_v19_output_checker_rejects_missing_q_coverage_live_slot_or_counter_overlap[<lambda>-disjoint MatSolve counters]`、`test_v19_output_checker_binds_exact_input_and_requires_lifecycle_audit`。它们都在未改动的 `_verify_v19_one_q_factor_lifecycle` 因 MatSolve counter categories 错误/不完整而失败；`_v19_one_q_lifecycle_audit` fixture遗漏 `reference_correction_rhs_mat_solve_count`，其中“disjoint MatSolve counters”用例因此先收到更早的类别校验错误。该失败不触及B0 200-q V15路径，也未修改这些历史V19测试。修改相关文件的 `git diff --check` 通过；没有运行全仓测试或CI。

源码仍由主控冻结与部署；本轮没有生成正式合同/窗口、没有执行 `prepare`、service、FE或PDE。当前本机唯一已找到的C1 ABI receipt标记为 `local_wsl2_authorized`，而正式Task41 `prepare`和service入口要求 `native_linux`；正式prepare须在主控部署的冻结源码及相符native receipt上执行，不能拿本机WSL receipt替代。

## Task41 P0 冻结前 B0 入口与输出核验

本轮关闭四项启动前工程阻塞，没有改数值门限、固定窗口或资源 cap：严格 ABI 路由现按精确 profile 将 A2/B0 绑定到各自的 case/run id，仍要求合同绑定的 `native_linux` receipt、当前源码身份和干净源码；共用入口 fixture 以真实 DAT 经解析器、`_V14Runtime` 到 `_candidate_contract`，覆盖 B0 固定 T0/bootstrap、172800 s 窗口、零 swap、资源包和 dispatcher binding，全程不建FE网格。

B0 的诊断衍射表按实际 DAT 配置生成的完整 `(m,n,polarization)` 键集合核验，当前是17×17×2=578项；正式 DtN 表单独从哈希固定的模式 manifest 逐侧核验所有 `(side,m,n,polarization)`，允许冻结库存的 top=32062、bottom=32058，不再把两种表的条数混为一谈。轻量 fixture 覆盖上下端口条数不等并拒绝缺失模式；旧 Task40 等侧默认检查仍通过。

carrier 资源审计是**依据实际 FE face dofmap 的派生上界，不是实测峰值**：单个模态功能保留 coupling 与 projection 两对 `(index,value)` 数组，因此按2×(8+16)=48 B/row/mode估计；全局 MPC slave rows 单独计入。组件装配还保留基于 owned+ghost 全空间向量、扫描/索引/采集临时数组的64 B/row上界、sorting workspace与原512 MiB下限。端口支持由 z 面 Basix entity-closure 和保z的x/y Floquet映射推导；这不表示内域场为零，也不按全局rows×64120预留稠密对象。实际生成行和在线watchdog仍负责最终资源裁决，现有cap和停止门不变。

Task41 C1 activation ABI preflight：complex128/int32、MPI1、DOLFINx 0.10.0。最终窄回归命令如下，结果 **8 passed in 0.54 s**：

```bash
source scripts/task40_fresh_c1/activate_local_wsl_complex.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit
python -m pytest -q --tb=short src/test/test_task40_v10_abi.py::test_task41_case_abi_uses_native_contract_route_and_rejects_local_receipt src/test/test_task41_p0_contract.py::test_task41_worker_runtime_uses_service_window_and_strict_resource_view src/test/test_task41_b0_dispatch.py::test_task41_b0_diagnostic_grid_keys_are_separate_from_official_port_count src/test/test_task41_b0_dispatch.py::test_task41_b0_carrier_upper_bound_counts_two_pairs_slave_rows_and_full_vector src/test/test_task40_v10_output_checker.py::test_task41_b0_port_table_matches_unequal_frozen_side_keys_and_rejects_omission src/test/test_task40_v10_output_checker.py::test_v10_dtn_port_mode_table_requires_paired_top_and_bottom_rows
```

没有重跑先前含V19失败的宽批次、全仓测试或PDE；也没有提交或推送。源码仍待主控在 native Linux 上冻结后再做正式 prepare/service。

## B0 边界紧凑积分接线

工作站原资格化native ABI下：`python -m pytest -q src/test/test_task41_b0_native_surface.py src/test/test_task40_v22_operator_probe.py::test_compact_component_matches_full_vector_bitwise_with_mpc_and_cutoff_rows` 得到7 passed in 1.00s。覆盖真实方向库存拒绝非规范几何、代表模式、MPC筛选、完整functional比较、PETSc DtN作用与模态RHS公式。最终仅纠正D_projection/B_coupling两个计时键后，pairing fixture再测1 passed in 1.09s。相关py_compile和git diff --check通过；ruff模块缺失，未安装或声明通过。没有全仓测试，也没有将fixture作为真实B0 FE资格。

对照维持Bα=coupling×α、D_raw x=projection dot x、DtN=coupling×D_raw/H；不得把H乘入B或D。正式路径仍需真实六模式比较后才能使用新内核；没有降低原数值门。停止与测试原始轻量记录见b0_controlled_stop_native_surface_preparation.json。

## B0 support差异判定与原始稀疏证据定向回归

Task41 §4.107/§6.153只要求实际核验B/D支持条件，以及完整CSR/native作用误差≤1e-11；它们没有规定不同积分实现的阈值后支持行必须完全相同。本地修正将行集对称差保留为诊断，仍在行集合并集上计算全值差并以reference-L2≤1e-11裁决；H≤1e-14、实际行域与排序、MPC/相位和两阶段1e-13筛选不变。显著漏项或错误符号/相位仍由完整误差门拒绝。

每个代表模式现在会在失败异常之前原子保存component、D projection、B coupling双方的稀疏rows/values和D_raw稀疏输入，另写包含模式、门限与运行身份的JSON索引；索引记录NPZ SHA-256。没有保存完整稠密场。旧`20261017T095825.478498Z`失败不回溯改判；没有运行FE/PDE、正式service或全场。

Task41 C1 qualification activation ABI preflight通过：Python位于`local_w0_wsl/runtime_prefix`，PETSc 3.25.6 complex128/int32，DOLFINx/Basix 0.10.0，MPI1/MPICH 5.0.1。相关模块`compileall`通过；最终定向命令与结果：

```bash
source scripts/task40_fresh_c1/activate_local_wsl_complex.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit
python -m pytest -q --tb=short src/test/test_task41_b0_native_surface.py src/test/test_task40_v22_operator_probe.py::test_compact_component_matches_full_vector_bitwise_with_mpc_and_cutoff_rows
```

结果为**10 passed in 1.23 s**；`git diff --check`通过。Ruff在资格化runtime中未安装，未安装或声明通过。测试仅证明比较器与紧凑积分fixture的局部行为；源码仍待主控冻结、native Linux部署与真实代表模式验证。

## 浮点支持差诊断与失败前原始保存

在两个真实top局部几何上得到独立Basix/多项式/FFCx证据后，主控核对Task41任务书并修正本轮额外加入的筛后mask相等hard gate，原完整作用误差门不变。比较仍累计稀疏支持并集上所有值差；支持差字段保留。新fixture用主项1、小项2e-13模拟高于生产cutoff但低于作用误差门的残值；显著漏项和错误相位仍失败，失败前NPZ与hash持久化已核对。

资格化C1环境下，完整B0配对模块及compact cutoff回归为10 passed in 1.23s；最终仅调整上述fixture量级后，相关5项5 passed、4 deselected in 0.48s。相关compileall、ABI preflight及git diff --check通过；Ruff未安装。该测试不等于新的真实六模式资格或完整PDE通过；旧611be2d2配对失败记录不改写。


## B0 资源停止证据收口（仅文档与元数据）

本轮只新增 hash-bound 停止 compact，并更新 run index、结果汇总及交接文档；没有修改源码、重跑 pytest、重跑 FE/PDE 或碰触大 carrier。现有 B0 定向验证记录保持原样，不能视为本次正式运行通过。关闭检查为 compact JSON 可解析、记录字段与小型 run/checkpoint metadata 对齐、git diff --check；没有 CI 结果。2,030,433,193 B 的 watchdog resources log 仅从末尾读取有界片段并对所用原始 JSONL 行单独算 hash，没有全文件扫描/哈希；363,791,051,840 B carrier 仅读文件元数据与其小型 checkpoint JSON，没有读取或哈希 carrier 本体。

主控复核：三条原始资源行按byte offset回读并独立重算SHA、三个原始summary hash及两份停止谓词源码hash均匹配；carrier父阶段原始事件第163行SHA为`5ca968b60f8bfacd105452da292ed795b5f233d50d0471e6a13992a676860f4e`。无科学源码修改，未重跑FE或完整测试。

## Task41 P0 Review V2：测试、正式尝试与失败边界

V2 有三份 consumer source 身份与三次正式尝试，不能用最后一次错误概括前两次：

| source / attempt | 实际检查 | 结果 |
|---|---|---|
| ab9e14dd00b2f1a94acd7ced5949e940caa724e6 / 20261018T090832.301793Z | 真实 P6 cells/MPC map 与两输入 recovery fixture；可复现 original trace row 不属于 independent active row 的错误 | 2 passed in 0.55 s；随后正式 worker 仍以 row classification error 退出。细节见 p0_v2_raw_probe_rowmap_repair.json |
| 6c31c5be468ebe6b50102a9beaaa701f48107b4d / 20261018T104243.408669Z | 非零 B witness alpha、可重用 volume action buffer | 2 passed, 13 deselected in 0.34 s；附加 whole-file 运行 12 passed、3 failed，失败在未改动的 regular-inverse fixtures；没有重跑 baseline，也没有修这些 fixtures。细节见 p0_v2_alpha_probe_field_diagnostic.json |
| 本机最终相关套件，记录的 source-tree HEAD 5e82225427d91d2ec4650169e558b6da29e75a8e | 16 项相关回归；资格化 WSL activation 下 PETSc complex128/int32、MPI1 | 16 passed in 0.88 s；py_compile 与 git diff --check passed。该 HEAD 与第三次正式 service source 53243cd6766b564fed17668753e9fdbb7cab1129 分列记录，不把测试结果跨 source 重署名。完整命令见 p0_local_final_evidence_20261018.json |
| B0 service-contract fixture（1 项尝试） | test_task41_launcher_and_service_pass_real_window_resources_and_checker_authority[B0] | 因 run-local ABI receipt 属于不同 runtime profile/host/boot，在 imports、preflight 与 pytest 前阻塞；不计为 pass。 |
| alpha gate whole-file 批次 | 相关 worker arrays 测试文件 | 12 passed、3 failed；3 项是 unchanged regular-inverse fixtures，未做 baseline rerun，不宣称它们是本次改动造成或修复。 |

三次正式运行的负结果分别为 row-map 错误、B witness alpha 假失败、以及 RHS recovery 数值门失败。第三次 mode 16030 相对误差 2.0454083899234283e-11 超过 1e-11；失败列输入、native RHS 与 recovered arrays 没有落盘，故无法独立重算绝对误差或原因。selected surface receipts 2/2 PASS 不是 full action/recovery PASS。

Ruff 不可用，未安装；未运行全仓测试。表中通过的 fixture 与运行门各自绑定对应 source/attempt。文档修订仅追加结果索引与总结，没有借用这些测试声称第三次运行的数值门通过。机器可读 adoption/action/performance 与三次服务证据见 [V2 compact](p0_v2_adoption_action_performance_20261018.json) 和 [run index](run_index.json)。

主控补充：在最终冻结源码 `53243cd6766b564fed17668753e9fdbb7cab1129` 部署后，使用工作站既有 native complex activation 执行新 B-action 振幅 fixture 与 two-input borrowed-buffer fixture，结果 `2 passed, 13 deselected in 0.56s`，随后才启动 `121210` 正式 attempt。该记录来自主控部署命令回执，不能抹去此前本机旧 ABI receipt 的阻塞记录。科学 source 与本次文档结果 HEAD 分开；最终结果 HEAD 由集中推送后回读提供。


## V3 恢复证据磁盘配额授权修复（2026-10-19）

用户于本轮明确授权仅将 Task41 B0 V3 原始证据磁盘配额从 8 GiB 提升到 16 GiB（17179869184 B）。内存上限、host reserve、task swap0、2 GiB 磁盘剩余空间底线、数值门、原固定窗口均不变。旧合同缺少新 policy 时继续 8 GiB，不修改旧 attempt。
触发实例：20261019T025658.545020Z，source 1366d64b8479139355e70897392f9bfed18347a9；预计累计 11882448300 B，原 8589934592 B，真实 V14ResourceStop；恢复见证未执行，不能记数值通过或失败。

定向测试：原8 GiB拒绝、16 GiB接受11882448300 B、16 GiB自身上限仍拒绝、磁盘free-space floor仍拒绝、跨case覆盖拒绝。首次相关3项为2 PASS/1 FAIL：旧dispatcher fixture缺少既有require-existing donor字段；仅补齐fixture后同3项全部PASS。包括B0 dispatcher和checker原调用链。本机资格化WSL complex128/int32；未重跑PDE或旧科学数据以验证配额字段。

### V3 用户批准的 24 小时续作窗口接线（2026-10-19）

用户明确批准独立 86400 秒续作（数值 85200 秒、收口 1200 秒），保留原窗口与费用。新窗口从已保存授权时钟计入准备成本，启动或源码提交不重置时钟；证据磁盘上限为 16 GiB，其他资源和数学门不变。

定向验证：固定新窗口/旧父窗口不可变、正式 worker 预算、独立 watchdog checker 命令授权、旧窗口跨源码复用，共 4 项通过。首次测试的 watchdog 夹具错误地解析虚拟环境解释器符号链接，导致 `/usr/bin/python` 不存在；仅修正夹具路径后复测通过，未修改 ABI 门或生产数值。未运行全仓测试。
## V3 正式运行与保存证据核验（2026-10-19）

最终正式 attempt 使用 source afbe91e5947ed18fb74d7105097e129c1b8b4cc7，目录 20261019T053402.514018Z，service myfenics-case-20261019T053359-2096871.service。16 GiB disk admission 通过；run 结束于 full-action gate failure，分类 WORKER_FAILED，数值分类 NUMERICAL_GATE_FAILED_ROOT_CAUSE_UNRESOLVED，official result=false。

| 核验 | 结果 | 范围 |
|---|---|---|
| 16 GiB policy 定向测试 | 原 8 GiB 预测拒绝；16 GiB 允许 11,882,448,300 B；自身上限、2 GiB floor 和跨 case 保护仍拒绝越界；修正 fixture 后该批次全部 PASS | 资格化 WSL complex128/int32；未重跑 PDE |
| 原始运行 disk admission | projected cumulative 11,886,541,965 B / cap 17,179,869,184 B；准入 PASS | 当前正式 run；floor 仍 2,147,483,648 B |
| 保存向量清单 | 141 个 .npy、9,379,882,344 B；路径集合、文件大小和逐文件 SHA-256 全部匹配 manifest | 当前 run 根目录 .npy，不扫描 external donor 或 watchdog JSONL |
| full-action 比较重算 | NumPy 对保存 p6/native RHS 重算相对误差 3.0421186782950535e-10、6.3918938782065652e-10 | 两列都超过原 1e-11；只复核运行已保存的比较 |
| offline recovery checker | INCONCLUSIVE_SIGSEGV；PETSc signal 11、MPI_Abort 59，没有报告写出 | 不算 PASS；两次初始调用配置存在偏差；修正为冻结 native activation 后定向复验仍崩溃 |
| PDE / 项目测试 | 本收口未运行新 PDE 或新项目测试 | 不把此前 cap 定向测试移作数值通过证据 |

本机记录的 cap fixture 定向测试结果见本文件 V3 配额段；测试是对 contract/dispatcher/checker 接线的校验，不证明 FE 数值门。当前 V3 结果、run summary、candidate summary、recovery manifest、event log 和 hash index 的完整身份见 [V3 closeout compact](b0_v3_full_action_failure_20261019.json)。全仓 pytest、Ruff、q/factor、KSP/FGMRES、完整场与 official observables 均未运行。

文档收口后的最终定向验证：资格化 WSL activation preflight 确认 Python 来自当前仓库 .venv、PETSc complex128/int32，petsc4py、slepc4py、dolfinx 和 mpi4py 属于同一 Linux complex ABI 栈；模型登记表与文档合同测试共 20 passed in 0.09 s。另有 run-index/compact/hash-index JSON 解析检查、表格列数与 git diff --check 通过。未运行全仓测试。

主控最终文档修正后仅运行 `src/test/test_26_documentation_contract.py`、`src/test/test_183_development_model_registry_markdown.py`、`src/test/test_development_model_registry_contract.py`：21 passed in 0.08s。checker正确native调用仍崩溃，三次调用证据见 `b0_v3_offline_checker_invocation_failures.json`，不算通过。

## Review V4 volume-only 归因与保存数据复核（2026-10-20）

| 验证 | source / 输入 | 结果 | 解释 |
|---|---|---|---|
| 受监督 geometry-pair service | `02523b3d5a49d30d71caa8e7f8a9b9405a78fa33`；selected cells 26762、26897 | service `Result=success`、`ExecMainStatus=0`；required saved-evidence checker 报 `audit_completed=true`、`data_integrity=true`、`recovery_passed=true`、`joint_action_passed=false` | 证明这个保存审核流程完成并保留原 full-action FAIL；不等于源码单测或 PDE qualification。report SHA `427af9ffb5f41a129250a513eaa908c13efe79ac10d2bbf5468d1a69fa0113b8` |
| volume-only extraction | `d883c1f3381b4f3d6100022097d615846564673c`；donor source `afbe91e5947ed18fb74d7105097e129c1b8b4cc7` | `COMPLETED`；3 canonical classes、28,000 owned cells、1,299,043,104 B persisted | 只提取 volume blocks/maps；没有 surface scan、global q factor 或 PDE。report SHA `09e96eb8c9d52b4cf0c29570fd8df3c1f820bc208104d91edd102978dfc9c4d5` |
| selected geometry-pair probe | V4 consumer contract SHA `8e041fc0fae6da0bab5855043e9ebe5678facad6bb319d0e0bc3ac5c08c89453` | 42 arrays、49,929,712 B；worker 235.811 s / service 父 306.000 s；task swap peak 0 B，后代清场 | 只支持这对 cell 和一个 selected row；父子时间不得相加 |
| corrected saved-only local elimination | script SHA `a57b8f10251d5e921ab2bc41e0a584aca5e6f18c3c797e606690f3cd503e1110` | output SHA `27eb82d1e51fd62b2b80e74fe5129f7be0512c35f95d092c967aeca6f90216ae`；5.046 s | `b_t` 只扣一次；无 RSS 采样，无 mesh/carrier rebuild、端口遍历或 global q factor |
| 初始错误 diagnostic | 保留的初版 JSON | SHA `b9dd5bf9b5dd906fa3dcd7485e11190101067fe2f552caed92f9e96f5046a955`；排除 | 初版把已全局组装的 `b_t` 在 cell loop 内重复扣除；不纳入任何科学结论，修正版结果单独保存 |
| V4 production source tests | source `02523b3d5a49d30d71caa8e7f8a9b9405a78fa33`；主控使用资格化本机 WSL `.venv` / complex128-int32 preflight | `26 passed in 1.20 s` | 本机 small fixtures；不代表工作站实际 ABI 或新增数值资格 |
| V4 documentation contracts | 收口后的 summary/README/two-level ledgers/run_index | `21 passed in 0.08 s` | 文档与索引结构检查，不构成数值资格 |
| full-action qualification | V3 saved arrays，原分母和原 `1e-11` gate | `FAIL`：`3.042118678294192e-10`、`6.391893878204816e-10` | V4 的 local row 结果不覆盖全部 5,752,120 joint rows；200q 与后续求解仍未运行 |

V4 implementation focused command（主控在本机资格化 WSL `.venv` / complex128-int32 ABI preflight 后执行）：

```text
python -m pytest -q src/test/test_task41_v4_volume_only_audit.py src/test/test_task41_v4_selected_volume_audit_cells.py src/test/test_task41_p0_saved_output_continuation.py
```

结果 `26 passed in 1.20 s`，exit 0。该结果只覆盖本机小 fixture，不构成工作站 ABI 或新的数值资格。固定窗口余额快照见 V4 compact；当时数值截止和总截止都未到，依赖未闭合 full-action gate 停止下游。

文档合同命令：`python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_183_development_model_registry_markdown.py src/test/test_development_model_registry_contract.py`，结果 `21 passed in 0.08 s`。另外 compact JSON/ratio/source/window assertions、Markdown table widths 与 `git diff --check` 均通过。

两个独立 service 父段为 `1,638.8259056420065 s` 和 `305.99965768121183 s`，可相加；worker/checker 子阶段不重复相加。volume-only worker tree RSS/cgroup peaks 为 `13,237,129,216 B` / `8,655,577,088 B`；checker tree RSS 为 `3,948,949,504 B`。geometry-pair 与 checker tree RSS 为 `1,513,431,040 B` / `3,949,363,200 B`，共享该服务 cgroup 峰 `1,411,362,816 B`。各自 task tree/cgroup swap peaks 为 0 B，后代已清场；volume-only worker期间工作站宿主全局 swapin +5页不能归因给任务。三份 saved-only diagnostics 用时 `11.880770959891379 s`、`2.6438243738375604 s`、`5.046073629986495 s`，均无 RSS 采样。上述计时只是有回执片段，不是完整V4工程或固定窗口成本。


## Task41extra Review V5 定向验证

- source 69ae04a4 冻结前，几何/生产作用/路由定向子集：10 passed in 0.74 s。
- source 0985d129 的 V4 checker elapsed 字段修复后，定向子集：11 passed in 0.72 s。source 179cf736 的 shutil 导入修复后，仅新增 disk-usage fixture：1 passed in 0.10 s。资格化 WSL ABI preflight 与 git diff --check 通过；Ruff F821 为 NOT_RUN（运行环境没有 Ruff），未安装环境。
- 正式工作站 attempt3 完成合同/资源 preflight，但 full mesh_actual_exact candidate 因固定窗口时间 deficit 1,489,566.259 s 被拒绝；这是 CANDIDATE_NOT_ADMITTED，不是 pytest 或数值门失败。详细结果见 response_v5.md 与 b0_v5_mesh_actual_exact_not_admitted_20261020.json。
- 补充 wider validation：volume-only audit 全模块与三份文档合同共 32 passed、3 failed in 1.35 s。失败为 test_volume_only_owner_avoids_surface_and_persists_each_class_once、test_volume_only_owner_rejects_fresh_numbering_mismatch_before_persist（测试替身缺 cfg.tags）及 test_volume_identity_replays_production_volume_and_two_state_residuals（TinyOwner 缺 build_audit）。随后经主控审查，仅修 fixture 并复验原失败项（见下一条）；生产源码未改。原始 pytest 输出保存在 benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/v5_attempt3_179cf736/verification/combined_pytest_output.txt，SHA-256 e2d1a3b4f98159bab57203be4372e1e77a2645b5b8a40793abab3839826deb79。
- 主控审阅后的 fixture-only followup：将真实 config tags/material/physics、TinyOwner.build_audit 与 geometry_policy 参数补入三个测试替身；仅重跑原三项，3 passed in 0.90 s。仅修改 src/test/test_task41_v4_volume_only_audit.py，production source 未修改。修复前 wider validation 的32/3负结果保留；差异摘要 SHA-256 见 V5 compact。

主控最终文档校正后只重跑三份受影响文档合同：`21 passed in 0.06 s`（工具输出 `7fc294`），命令为 `python -m pytest -q --tb=short src/test/test_26_documentation_contract.py src/test/test_183_development_model_registry_markdown.py src/test/test_development_model_registry_contract.py`。不构成新增科学资格，也未重新运行 FE。


## V6 checker identity 修复与 saved-only audit

候选 scientific build 和 saved-data numerical checker 是两项不同证据。候选 source `210fbbf271faa14c62ac30153b80332d0e645982` 完成八个局部代表键和 28,000 键构建，随后原完整 action 两列真实数值未过 `1e-11`；这不是 pytest 结果。required checker 起初分别遇到冻结常量名错误、入口误传 DAT、以及 evaluator identity 在生产 report 父/子层级与 checker 假设不同的问题。三次失败原始 receipts/logs 均保留，见 [V6 hash index](b0_v6_actual_qmetric_hash_index_20261021.json)。

第二处 checker 修复按已验证的父 `identity_audit` identity/cache identity 读取生产者实际布局；若嵌套字段存在但不匹配，仍拒绝。source `89e1e42114870ba1db752dfaf6d893ad13f923d6` 下的定向回归在资格化 native complex activation（PETSc complex128/int32、MPI1）执行：

```bash
source scripts/task40_fresh_c1/activate_native_complex.sh \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/abi_receipt_v29_attempt2.json \
  benchmarks/artifacts/task40extra_0p7nm_engineering/local_v29_wsl/jit_cache native_linux
python -m py_compile src/runners/task41_p0_checker.py src/test/test_task41_p0_saved_output_continuation.py
python -m pytest -q src/test/test_task41_p0_saved_output_continuation.py -k 'v6_global_attribution_uses_parent_identity_metadata or v6_candidate_recheck_checks_frozen_row_denominator_before_identity or v6_candidate_checker_binds_cache_identity_to_evaluator_source or v6_saved_report_binds_producer_contract_separately or b0_saved_evidence_audit_uses_supervised_service_route'
```

结果 **14 passed, 22 deselected in 1.12 s**；当时 `git diff --check` 通过，修复随后冻结为 source `89e1e421...`。这组测试验证 checker 的身份读取与失败关闭行为，不是 PDE 或候选 action 的数值 PASS。

最终 attempt4 通过既有受监督 service 对保存证据执行 saved-only readback：checker `COMPLETE`、data integrity true；service 对全部 174 条数组记录内容重算 SHA，checker 只重开并重算 action/recovery/attribution 所需数组。candidate numerical status 仍为 `ACTUAL_COORDINATES_INSUFFICIENT`。service 180.8804526119493 s，watchdog 131.0202877856791 s；没有重建 FE、LU、候选张量或重新运行 PDE。顶层 `recovery_passed=true` 属于旧 V3 donor replay；同一报告中的 V6 candidate recovery 子节点为 false。

V6 文档合同回归（主控提供的本机记录）：资格化 activation 已确认 PETSc complex128/int32；命令 `python -m pytest -q --tb=short src/test/test_26_documentation_contract.py src/test/test_183_development_model_registry_markdown.py src/test/test_development_model_registry_contract.py`，结果 **21 passed in 0.09 s**。该检查覆盖文档结构与模型登记合同，不是科学源代码测试或 PDE 资格；本任务执行者没有重跑这些测试。

本次执行者文档收口另做 JSON 解析、原始文件哈希/字节/数组清单对照、V6 新增相对链接检查及 `git diff --check`；未重跑科学源代码测试、全仓 pytest、Ruff 或 PDE。没有 GitHub CI 结果声明。

## Task41extra Review V7：定向测试记录（2026-10-21）

执行者首轮终端记录：**10 passed, 48 deselected, 0.94 s**；该首轮没有另存raw log。主控同source的最终定向复验与日志hash见下。文档收口另完成compact JSON解析、证据字节/SHA核对、链接检查和git diff --check；没有重跑昂贵科学数据、全仓pytest、Ruff或PDE。

V7主控最终同source定向复验：10 passed / 48 deselected / 1.13 s，qualified WSL complex128/int32。命令及原始日志绑定见 V7 compact tests；SHA-256 `3b36563d720a44cfdf0571940f63900a595adc5d5a7fb795cf52b5e799a88b6b`。无全仓/PDE/CI声明。

## Task41extra Review V8 checker 修正与保存审计（2026-10-21）

V8有三组定向回归。表中SHA是补丁测试后冻结的source身份；测试在对应提交前工作树执行，并非声称测试时HEAD已是该SHA。日志hash未单独保存时标为`NOT_RECORDED`。

| 补丁随后冻结的source SHA | 定向命令 | 结果 | 边界 |
|---|---|---|---|
| `6021691906a8d4db48a0261140c6601027ad49a8` | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q --tb=short src/test/test_task41_p0_saved_output_continuation.py src/test/test_task41_v8_selected_trace_star.py -k 'test_b0_saved_evidence_audit_uses_supervised_service_route or test_v8_legacy_missing_checker_field_is_exact_hash_and_identity_bound'` | 首轮10 passed/38 deselected，0.59 s；最终复验10 passed/38 deselected，0.62 s | saved-only service路由与legacy字段身份约束；日志SHA `NOT_RECORDED` |
| `23ba24414a02d9e4e8e921ff97d48d5d1d9d1fe0` | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q --tb=short src/test/test_task41_v8_selected_trace_star.py -k 'v8_checker_replays_saved_complex_local_vectors_and_reports_defects_only or v8_selected_scalar_replay_matches_p3_producer_schema or v8_rhs_counterfactual_uses_original_full_storage_row_once'` | 首轮3 passed/8 deselected，0.44 s；最终3 passed/8 deselected，0.41 s；`git diff --check`通过 | 保存复数向量、P3 schema和full-storage row mapping；日志SHA `NOT_RECORDED` |
| `3ce1a158e3e0b6556a2e094755adf9b5bd18ae08` | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q --tb=short src/test/test_task41_v8_selected_trace_star.py::test_v8_ordered_summary_keeps_grouped_left_distinct_from_closure` | 1 passed in 0.51 s | V7 grouped-left与closure字段映射；不是科学门/PDE通过 |

前两组是在相应源码冻结前执行的定向测试，最终组对应checker映射修正。qualified activation preflight为PETSc complex128/int32，同一Linux ABI栈。V8收口未运行全仓pytest、GitHub CI或PDE。曾尝试`python -m ruff`，返回`No module named ruff`，因此Ruff检查未完成；没有安装依赖，原错误保留。保存审计成功不等于V6 candidate full-action通过。


## Review V9 准备阶段定向回归（2026-10-21）

同 LU RHS 路径、保存 d 判别、J 共享释放、新窗口合同和 service/watchdog 路由先完成 26 项定向组合（1.04 s）。主控审查后，针对旧 V8/缓存/authority 兼容与有符号诊断独立性补修；最后受影响 10 节点由执行者通过（0.54 s），主控同工作树复验 **10 passed in 0.51 s**。节点、工作树文件 SHA、命令与原始日志见 [V9 preparation receipt](v9_preparation.json)。`bash -n`、相关 compileall、`git diff --check` 通过。

ABI 是本机 qualified WSL complex128/int32；不是工作站正式 service 资格。Ruff 不可用，未安装。历史 fixed-window 三项失败仍保留，未刷新旧时间门；诊断偏置 fixture 曾 9 passed/1 failed，修正其预期后通过。没有重跑全仓测试或科学数据，没有 V9 局部/全域数值 PASS、CI PASS 或新窗口批准。

## Review V10 对 V9 准备的窄修验证（2026-10-22）

在本机资格化 activation（complex128/int32）下，最终 **14 passed in 0.61 s**。覆盖 correction 返回量污染、j0/j3 trace/RHS 混配、复 MPC 强相消的真实 action 调用、较宽算术的保守诊断、错误释放顺序后重试，以及旧 V8/default/authority 兼容。四个变更 Python 文件 compileall 与 git diff --check 通过；主控审查实际数据流并回读源码、ABI、测试日志 hash，未重复全仓或科学计算。具体 argv、原始日志 SHA 和文件内容身份见 [v9_preparation.json](v9_preparation.json) 的 `review_v10_local_fixes`。

旧 V8 helper 字节未改；正式保存包筛选、全域 action/recovery 与新窗口仍分别为 NOT_RUN / PENDING_USER_APPROVAL。没有 response_v9、工作站运行或新增数值 PASS。历史失败及旧准备费用保留，本轮完整准备父时长未连续计量，仍为 UNKNOWN。

## Task41extra Review V10 后：V9 B0 正式 run 收口（2026-10-22/23）

| 验证对象 | 结果 | 范围与边界 |
|---|---|---|
| Review V10 实现定向 fixtures | 14 passed in 0.61 s（准备记录） | 准备实现的小型回归；发生在正式 run 前，不证明全域数值资格 |
| V9 compact independent checker | FAIL，passed=false | 读取已保存 compact volume audit；两列 action 门未通过 |
| 正式 service required terminal checker | NOT_RUN | service receipt 中 run_case_returncode=3，ValueError: Task41 numerical-output directory is missing；没有 checker authority/result |
| Full workflow | WORKER_FAILED，exit_status=4；full-workflow time exceeded=false | 真实正式尝试，科学 full-action gate 失败；不是 pytest 结果，也非资源/时间门停止 |
| 本收口验证 | JSON 解析通过；git diff --check 通过；没有运行 pytest | 只验证所更新的小型索引与文档差异；不声称 CI 或全仓测试通过 |

独立 compact checker 的数值 FAIL 与正式 service terminal checker 的 NOT_RUN 分列记录。run summary、service receipt、compact audit/check 与资源口径见 response_v9.md、run_index.json 和两级账；未重跑 FE、recovery 或任何 checker。


## V11窄续作（2026-10-23）

最终科学source f1697498699d9b4c2c4c4919b97e4a1e2bba22f5。末次真实metadata账本path回归：主控在qualified WSL complex128/int32下执行 `python -m pytest -q --tb=short --show-capture=no src/test/test_task41_p0_v11_metadata_identity.py`，1 passed/0.06s；执行者同项1 passed/0.15s。`git diff --check`通过。此前selected-row累加、覆盖拒绝、诊断边界、真实service envelope和失败补审路由5项定向测试1.13s通过（source2b085de8冻结前），相关源码末次只变path检查。未运行全仓/MPI多进程/PDE，不声明CI；ruff未安装，不声明lint通过。

实际工作站监督运行与fixture分开：补审确认旧action FAIL；y/g全域分解完成；metadata完整；selected attempt03身份路径bug，attempt04时间未准入。没有新局部数值PASS。详见[response_v11](../response_v11.md)和[原件](v11_closeout/evidence_index.json)。

收口数据检查（不启动FE）：24份复制JSON原件字节/SHA与工作站索引一致；全部新增JSON可读；保存比较的Δy两列为0、Δg端口两列为0；response内相对证据链接均存在；最终`git diff --check`通过。轻量原件目录865524B（包含索引），原NPY与资源timeline仍在ignored artifacts。


## Task41extra Review V12：saved-array checker 与文档收口（2026-10-24）

attempt06受监督saved-array checker完成，184项数组重算为EXACT，data integrity=true；这是保存证据复核，不是FE、solver或科学资格测试。V12 attempt03另有局部producer工作：建立两格mesh/space并生成候选张量与LU，不能把整个V12概括成无FE工作。C1 native Linux ABI preflight通过：项目runtime Python、PETSc 3.25.6 complex128/int32、SLEPc 3.25.2、DOLFINx 0.10、mpi4py 4.1.2、MPI1。最终源码相关定向复验由主控记录为3 passed、59 deselected、1.82 s，运行在checker source 9a6ccdcefc12119275f1ce1082f154af5a881241；另有纯fixture定向测试test_saved_diagnostics_prepare_binds_scope_and_reuses_entry_source_window为1 passed in 0.21s，检查scope、entry source与window绑定，不代表数值通过。

本次文档收口只做Markdown/JSON与链接结构核验及git diff --check；attempt04–06的saved-array checker正式attempt均已运行并保留；本次文档收口未追加checker。没有运行全仓pytest、Ruff或PDE，没有CI通过声明。attempt03/06源码与服务身份、数值结论和证据hash见[V12 response](../response_v12.md)及[V12 compact](b0_v12_saved_array_checker_closeout_20261024.json)。

## Task41extra Review V13 定向测试与文档收口

- 资格化 native activation 下，最终窄 fixture 子集为 2 passed / 42 deselected / 1.78 s：test_v13_cell_g_terms_unwrap_cell_tuple_and_separate_legacy_serialization_defect 与 test_v13_actual_independent_closeout_command_and_authorization_keep_exact_scope。测试时完整 source SHA 和原始日志 hash 未单独保留；之后冻结的运行合同绑定 HEAD af953ef38ba2f95a2e443e131dece20c17af8c1e。该测试证明 checker/fixture 行为，不证明 action 或科学门通过。
- 纯文档收口只检查已保存 JSON、报告/receipt/ledger 哈希与差异格式；未重新运行 pytest、Ruff、PDE 或 CI。行政文档处理位于固定总截止之后，时间成本 UNKNOWN_NOT_MEASURED。
- attempt10 的 8.958905 s watchdog 是 17.004897 s service parent 的子阶段，不另加。窗口账本 sequence 427 的累计 charged 为 21,255.405 s；该读数是 attempt10 结束时快照，不是当前余额。
