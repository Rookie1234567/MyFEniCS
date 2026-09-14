# V20 selective边界：分组审阅，未批准合并

单元凝聚先在单元内解掉内部未知量，再迭代边界/端口并恢复完整场。本固定original的新路径完整通过，时间少79.54%、全过程RSS高56.84%；保留时间—内存取舍，不提升ordinary default，也不授权后续notch。

| 依赖组 | 内容与依赖 | 数值变化/验证 | 建议次序 |
|---|---|---|---|
| production numerical/core | 无默认PC/profile切换 | 仅固定original有资格，MPI扩展/非可分/0.7nm未验证 | 不合入默认 |
| reusable numerical/core | `src/solvers/p6_cell_condensed_action.py`、`physical_retained_fgmres.py`，已有`hcurl_assembly_time_condensation.py`的action-only tensor身份增量 | 完整物理张量凝聚、非零RHS/MPC/Bi/Di/Hhat与增广逆桥；依赖原cell核/carrier/BAL_H；82项focused及fresh X1/X2支持 | 1 |
| reusable runner/watchdog | `physical_retained_outer_adapter.py`、`physical_dual_cell_condensed_v19.py`；V14共用外层的显式adapter接点，既有用户服务薄入口未改 | 数值核心在solver，runner只接线/资源/证据；同根X1→X2、先保存y后评价、因子最后释放；小服务＋完整服务均已通过 | 2，依赖1 |
| checker/benchmark | `benchmarks/check_dual_cell_condensed_v19.py`，V18 resource checker新增prefix但旧默认不变；新dat/schema/profile/ledger/dispatcher和6个V19测试文件 | 从原数组重算Gate，冻结FGMRES32/observe_only，formal一场+最多一次真bug重放；本场未使用重放 | 3，依赖1/2 |
| compact evidence/docs | response_v20、outcome、compact/decision、残差比较图、run_index增量、summary/test_summary、development两表 | 精确source、raw hash、完整original物理与资源、负结果/unknown；可独立先审 | 4 |
| research-only | 唯一`physical_p6_trace_p4_condensed_balh_v19`显式路径 | p6仅MPI1、当前共享类依赖axis-aligned affine hex；全局p4trace LU仍增长；建议后续审阅候选，不代表production资格 | 不提升普通默认 |
| do-not-merge | ignored大场/向量/因子/JIT/资源timeline、一次性工程与文档生成脚本、自动计算/默认变更 | raw保留本机并以compact hash绑定；不混入旧失败PC、BLR、notch或master | 排除 |

正式source为`8eff068b06f4713cc6d1281c92ed82d370060403`，base为`3c7b6ecfd7aede2651dd973052a097dbed601d03`；[完整response](../response_v20.md)和[compact](records/dual_cell_condensed_v19_compact.json)绑定测试、fresh PDE与边界。只在task39extra等待审核，不合并master。
