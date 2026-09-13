# Review V14 阶段合入边界

当前为 `NOT_APPROVED_FOR_MASTER_MERGE`。Review base 为 `25c90229410ca4f75406307ff55ea1ebad343b7b`；工程代码为 `5d239140d3931364bc16d35c45458189cd957808`，正式 Q0 仍绑定旧 source `efea244159d63a7c9db67ca091e29a9c19f9ce88`。本表划分依赖组，不能解释为批准合并。

| 依赖组 | 文件与作用 | 数值行为/依赖 | 测试和 fresh PDE | 合入建议 |
|---|---|---|---|---|
| production numerical/core | `physical_interface_schur.py`、`physical_interface_balanced.py`、`fullspace_p4_reference.py`、`fullspace_v17_p3_oracle.py` | 内部消元、物理接口 SVD/P/Q、固定周期和 BAL_H 适配；依赖现有 PETSc/MUMPS、transfer、metric；改变新显式 profile 的数值路径 | 小型代数与生命周期测试通过；新完整候选无 fresh PDE 资格 | 目前保留 research-only；正式资格后才考虑生产组，不能单独迁移适配器而漏掉核心 |
| reusable runner/watchdog | `physical_p4_schur_v14.py`、`physical_balanced_fgmres.py`、`task038_launcher.py`、`subreaper_watchdog.py` | Q1–Q6 调度、同 KSP 进展、全 PC 时间边界、账本和资源；新策略显式启用，旧默认保持 | 有限 KSP、旧策略与 watchdog 测试；没有新正式账本运行 | 依赖核心和输入配置整体审阅，不把记录读取路径作为数值成功 |
| checker/benchmark | `input_schema.py`、`input_validation.py`、`physical_intermediate_profile.py`、`task038_full3d_iterative.py`、`physical_recursive_controls.py`、七份 `input/task39extra/v14_*.dat`、相关 tests | 固定物理/资源 profile，准入和 Q6 共用原始证据检查；不重做数值求解来检查状态 | 联合测试 104 passed；准确 p4 三 RHS 配对仍缺失 | 核心→profile/dispatch→benchmark/检查，保留 explicit opt-in |
| compact evidence/docs | `response_v15.md`、V14 compact/comparison、run index、summary/test summary、开发登记和本表 | 无数值变化；保留 Q0 EIO、未结算费用及所有历史负结果 | raw hash、JSON、链接与文档检查；无 fresh PDE 声明 | 可以独立审阅；推送仍受自动批准审查阻断 |
| research-only | 本批所有新准确/近似 Schur profiles 与未资格化候选 | 仅本固定模型的机制研究，不能推广到 5 nm 或大尺度 | Q1/Q2/Q3/Q4/Q5 正式完整结果不可用 | 不提升为 production default，不以小型 PASS 代替完整物理 Gate |
| do-not-merge | ignored `results/`、`benchmarks/artifacts/` 内的 field/matrix/factor/timeline、临时环境、未结算账本及任何凭据 | 大型或机器相关运行状态 | 紧凑记录只引用路径/hash，不搬运大产物 | 不提交；不重写原账本、Review、master 或 5 nm 工作线 |

文档和工程测试的精确身份见 [response_v15](../response_v15.md) 与 [engineering evidence](records/p4_schur_v14_engineering.json)。正式结果恢复后应增量更新本表，不能追溯改判旧停止。
