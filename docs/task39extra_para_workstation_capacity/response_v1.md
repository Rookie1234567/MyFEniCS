# Response V1：性能受控停止与最小性能修复

原生Linux环境已资格化，但13.5 nm原始模型尚未复现通过。第一次运行在旧mode字节hash检查失败；取得用户提交的完整80通道manifest后，证明12个浮点末位差并按原1e-10合同修复。第一次迁移retry进入outer，62步后首段筛选失败，完整true=0.019433158954790204；当前停止主阶梯，没有R2/5/3/2 nm或G结果。

| 要求 | 本轮回应 |
|---|---|
| 原V5数学与native迁移 | A/b/PC、积分、MPI1/线程1及所有数值物理Gate不变；无新算法/子域法/PC |
| 笔记本对照 | 第32步完整true绝对差3.13e-13，轨迹一致；未取得本机收敛场，不能称完整跨环境复现 |
| 速度问题 | p4按行遍历实测单元3.6倍；p4/p6 curl独立循环合并实测1.4/2倍；PSS低频，RSS安全监督持续；尚无优化后full R1 |
| 资源/生命周期 | 3997.651 s，峰值3.163GiB，swap0；释放前后只回落4MiB，最终全部清场；详见逐阶段表 |
| 容量与精度 | 无native own-pass点，未做短波symbolic/numeric容量结论，无G、无连续极限或精度声明 |
| 隔离 | 独立canonical worktree，worker23/parent9，隔壁8个MPI仍CPU0–7；不互写文件 |
| CPU2降频 | 外部限频及DIMM高温已有证据；硬件问题未被本轮软件优化修复 |
| 分支 | `task39extra_para_workstation_capacity`，upstream `origin/task39extra_para_workstation_capacity`；base `450255f4575792d052c1bac29837d39955ee1039` |
| 源码 | 正式retry1 SHA `b2e132a7b1f1078eb3359c87a336123b3c7dfbdd`；性能修复SHA `f124679e75915758076d9240bd4bef2f5c772752`；文档结项提交是其后续，最终HEAD以Git/交付回复为准 |
| 状态/merge | fail / PERFORMANCE_CONTROLLED_STOP；等待本分支review，无master合并 |

任务书§11明确规定fine未在screen/solve预算内通过时“停止主阶梯，不当bug重新抽签”。因此没有用性能优化擅自再启动formal run，也没有从62步checkpoint继续。若用户明确授权一次额外R1性能验证，可在clean source、原输入、原screen/数值/物理/资源上限下从零验证；这不是已有成功结果。此时应先验证实际阶段提速，再按原Gate决定是否进入R2和短波。

本轮已完成可审阅的修复和局部等价性验证，未把修复方案停留在建议。测试的真实通过、初次失败、修复后复测、历史资料缺项和遗留Ruff均见[测试报告](outcomes/test_summary.md)。完整结果/阶段内存/时间/身份见[summary](outcomes/summary.md)、[reproduction](outcomes/reproduction_13p5nm.md)、[run index](outcomes/records/run_index.json)。正式前后clean source、资源原始hash、PC/p4成本和显式残差均已保存。所有大数组与JIT仍ignored，所有本任务提交仅在执行分支。
