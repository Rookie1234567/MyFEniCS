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
