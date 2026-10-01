# 全分支复用审查与同一次工作站启动准备

状态：四专题只读审计收口；本轮没有新数值运行，后续实验仍需单独准入。审查快照为 2026-10-01 11:17 UTC；下列结论不代表之后未发布的本机结果。

## 共同目标与责任

与本机 MyFEniCSx_task37_extra 准备同一次大规模验证，在 2026-10-04 10:07:14 UTC 前形成可交接的工作站启动材料，由用户执行大运行。最终对象保持原始三维物理尺寸、0.7nm 与完整场/端口约束；缩放模型和固定离散组件通过不能直接授予 2TB/48h 资格。

main task40extra_0p7nm_engineering 固定于 c786e87d03976a52f57d1e7f69a3c63f992afe90，已发表 Review V2；我们自主只读检查此分支新推送并读取增量结果，不依赖用户手动转述。HEAD 未变不能说明本机闲置；出现新 commit 也不能自动认定轮次完成或待审，须有正式收口证据。

这里的“背景逆”先准确求解一个结构较规则的三维参考系统，再用它帮助原始三维系统收敛；它不把最终场换成二维。凝聚是在求解前精确消去单元内部未知量、事后恢复；更少全局行数仍可能产生巨大因子。

## 复用现有成果

- 当前主线 G0/G1 严格原方程通过，G0 same-discrete direct 匹配通过。复用已冻结 source/input/operator 身份和记录，不重新启动已有直接参考。
- 精确局部恢复、p6 affine metric/reference tensor、完整端口与原方程 checker 都有已有实现。我们的张量组件结果直接对应主线 P2，应交换代码和证据，再由主线完成生产集成与 G1 回归。
- FEINN 的完整 Nédélec 矩映射、复伴随、独立物理审计，以及 learned-PC 的无私有 CSR 借用作用可复用。Task42extra 的小模型 p5 准确参考也是可用参考资产。
- solution-only rank-shard checkpoint 已存在于 fullspace_memory_first_krylov.py，绑定 source/input/operator/physical/MPI/ownership/hash；恢复需重建 setup 和 Krylov，不包含 LU 因子、残差或 Krylov 基。工作站启动前仍需实际中断/恢复验证。
- p4 凝聚已成熟：Task39 V18–31 的单元凝聚、完整内部 RHS/Bi/Di/端口恢复、原 A4 验算、内核和生命周期改进应直接复用。工作站 ccd3578 冻结快照早已使用 4,586,288 行准确 p4 凝聚；used 916.713GB、前缀树峰 1,154.356GB。问题不再是“尚未做凝聚”。
- Task040 S2c/S2d 已有准确离散全谐波背景逆，tiny serial/MPI2 原算子残差约 1.60e-14/2.14e-14。旧入口限制两横向轴均匀、4 个零阶端口、每块≤1024、稠密 LU/逐列提取。y-only、异质非均匀 x-z、全部 532 端口别名与 sparse setup 才是待资格的扩展。
- DtN fullspace 已有逐模式对角 H；待补的是 retained p6 的 dense-H/Hhat 表示接线。Task35b a810a13 已实现边界平面 evanescent gauge、历史幅值恢复与伴随链式法则；340-mode 原残差 3.112e-12，但功率/幅值仍仅6/12、7/12，因此只能复用缩放实现，不能宣布物理精度恢复。
- modal 专题确认：旧 corrected full-spectrum 的人工接口 analytic TE/TM sweep 负结果，与后来 S2d exact-discrete tiny 正结果属于不同候选。S3 的 off-block 0.1241–0.2308 和后续 shape/token/layer 实施失败，也不能解释成所有背景逆数值失败。

## 不重复已有研究

- Task42 原 p4 替代逆路线已标 CLOSED_RESEARCH_NEGATIVE：固定 rank128 的线性/神经及局部块，15/15 非零 RHS 在既定预算失败；后续真实几何重叠与平衡空间也未过关。不能将“NN 换 p4 逆”再次列为未经研究的新方案。
- Task42 V18 的 0.7nm micro 全 trace 补校正/LSQR/GMRES，8 个冻结状态完整资格为 0/8。后期已经允许完整补空间；不能误述为始终被固定低维神经表示卡住。
- FEINN 已尝试完整三维场、平面波相位、FREE-FE 对照、冻结末层最优投影、Adam/L-BFGS 与全参数 GN。V9 仍未合格；无标签方案包含全局 H(curl) Gram 的 CHOLMOD 因子，不能把“无 Maxwell LU”当无全局因子。
- learned local-PC 曾仅省 0.813% 迭代却增约 2.89 倍总时间；审核 CSR、collective 审计和 fallback 成本必须保留。局部 inverse 质量改善不自动等于全求解更快。
- p4 宏块准确 Schur 已更占内存（2.826→4.267GB）；full p4 BLR tau=1e-5 质量筛选通过但仅省约3% RSS，condensed BLR 反增1.416% RSS。不重开同结构/容差扫描。全35-head源码低精度关键词只找到测试合同/fixture，未找到 complex64 求解实施；这只是检索结论，低精度路线继续 hold。
- 端口 streaming 旧 L4 在真实 p6 fixture 只省1.785MB owner存储、apply慢65.48%，三操作合计慢3.129%；Hybrid V6 在22GiB gate停止，V7仅完成512列 producer，consumer/outer未运行。不要把 producer 完成或端口闭合当全方程求准。106GB alias-inclusive库存也不能当独立RSS/可释放量。
- 早期 FE-only AMS、低秩 coarse、长 restart、positive pMG、PML 编译停止各有不同限制。只在同对象/预算下承接其结论，不把某候选失败扩大成整个方法族不可能。

## 主线拥有的 P0–P7

- P0：冻结 G0/G1 基线与成本；P1：保存场的体积和独立 curl、非零 RHS 回归
- P2：精确 metric 模板生产集成；云端交付组件证据，不平行重造
- P3：M0–M3 真正 DtN 截断 PDE 比较；P4：G1 在选定 M* 下求解
- P5：真实电尺寸 q=1.25，满足条件后 q=1.5 的增长验证
- P6：统一端口、局部缓存、因子与运行内存账；云端提供可核验的分项证据
- P7：下一架构选择；云端全三维 y-cell-orbit reference inverse 是候选组件，当前缩放 p2 通过不替代主线高阶/目标尺度资格

## 云端真正缺失的资格与交接

在已存在组件上补证据，不另建竞争流程：scaled p2 的真实非零 y Bloch phi5 已通过（phase_y=0.5285127306+0.8489253758i，notch 原残差1.2852e-13/7.1414e-12）；剩余为高阶 p4/p6、跨ABI和目标尺度的候选作用/端口一致性；固定离散比较与 PDE 截断/h 收敛分开；真实目标资源组成及 workspace、临时副本、因子峰值；source/ABI 身份绑定；中断恢复与工作站可执行入口。端口专题对4,456个代码/说明blob专门查询，未发现已完成的同production Gauss、Basix canonical全DOF tensor face-Fourier DtN；命中为QEP scalar tracking。该候选及 retained对角H接线仍需真实全DOF/MPC/非零内部RHS与完整原A验证。旧gauge的tiny测试为unconstrained p2，不能替代现代MPC等价性。modal 复核建议沿已有 S2d 家族扩展：先 sparse/condensed p2 对已保存 dense authority，再真实 p4 原 A4/all-interior/all-q/port closure；顺序构造仍须合计所有 retained factors。真实 notch-supported RHS 与 sampled right-PC defect 可防止弱对比、小电尺寸易源掩盖问题。不得依据小型 checker 或对象字节直接承诺 2TB/48h。

## 文档权威与阅读覆盖

main 同一 c786e87d 中 development_progress.md L1–21 为过时 attempt4 总结，L12 仍称 G1/direct NOT_RUN；development_model_registry.md L8–11 已登记通过。以当前 task、最新 review/response 和 hash-bound 记录处理冲突，旧总览只作导航。Task42extra 相对 Task42 分叉（ahead60/behind78），继承的旧 Task042 文档不能代表当前 neural 分支。

35 个当前分支递归树全部索引，无截断；128034 个 tree entries、8713 个去重 blob、383532344B。代码/脚本/config 与 prose 共4773个 blob、104291461B，全部取回、逐 Git blob SHA/字节数核验、所有行完成十类关键词检索，缺失0。这是自动检索覆盖，不能称全部全文精读。

精读/章节读：项目指引、当前主任务合同与关键登记、四专题的选定实现和结果。具体 SHA/path/范围见配套 [覆盖索引](records/repository_audit_coverage_v1.json)；未实质阅读的历史数字 JSON/日志、全部旧原始证据、权重/场文件、所有历史 commits 保持“仅索引/未读”。没有重新计算仓库历史结果。

专题权威来源：Task42 @5b489b7264b75a9461577303ff0f6bc8907c19dd 的 Review V16/Response V18；Task42extra @47317bb648d5e2237657f8b6c75c239ab5bf55c5 的 Review V9/Response V9；neural local-PC @d91652dd2d611d6d6bedd10e677c3f7030c07d4f。这些固定快照中计划的下一轮不能记成已执行或失败。

## 最小启动准备清单

1. 与主线当前轮次对齐后冻结 code SHA/tree、几何/离散/有序 modes 分层身份与 source/compact/checker hashes
2. 先完成云端获准的小型 bridge/原方程资格；完整 p4 direct 若不满足资源准入则明确 NOT_RUN，不能偷换成已有 oracle
3. 工作站实际 MPI/IntType/thread/PETSc header/public API 需独立核验；旧 private MatFactorInfo ctypes 的3.19/3.25布局不相容风险保持阻断，不能借本机小型通过放行
4. 给用户一条带阶段 Gate 的启动命令、factor/local/port/Krylov 同时库存、完整进程树 watchdog、field落盘与真实中断恢复步骤；由用户执行大运行

本审查仅形成决策与证据索引，没有启动新实验。外部未资格的 p4 adapter 草稿不随审计整合。全量104MB检索正文不进入Git；配套JSON仅记录35个HEAD、检索口径、专题来源摘要与精读/章节读SHA/path。
