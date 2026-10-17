# Task41 P0 定向验证

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
