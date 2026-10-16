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
