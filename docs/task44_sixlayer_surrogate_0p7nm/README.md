# Task44：0.7 nm 六层结构的少样本代理可行性

**当前状态：首A已完成装配/符号分析，在numeric前资源预测拒绝；软件与材料前置通过，尚无合格六层有限元标签或代理精度结论。**

首A及普通修复见[统一结果](outcomes/summary.md)、[预算和检查点](memory_and_checkpoint_policy.md)。

目标是在六个独立层厚都可变化时，用尽可能少的可信电磁样本判断高斯过程能否预测总反射、总透射和零级反射。144 个六面体、p6 是首个待资格化离散模型，不能先当作已网格收敛的真值。

- 原始完整任务书：[task.md](task.md)，保持上传原文。
- 最新用户覆盖：[execution_override.md](execution_override.md)。48 小时窗口至 **2026-11-01 11:29:46 UTC**；资源安全、物理精度及盲测诚信不变。
- 独立审查：[review_report_v1.md](review_report_v1.md)。审查文件由 reviewer 独占维护。
- 材料：[materials.md](materials.md)，[材料独立核验](material_independent_review_v1.json)。SiGe 和 SiO₂ 使用可重算测试材料模型，不称薄膜实测光学常数。
- 代理软件与冻结设计：[outcomes/surrogate_software.md](outcomes/surrogate_software.md)、[18 点设计](outcomes/surrogate_design_v1.json)、[独立软件核验](surrogate_independent_review_v1.json)。软件测试不含 FE 标签。

## 模型与入口

固定 0.7 nm、周期 2.5×2.5 nm，中心柱截面 0.85×1.0 nm；底部 Si 为 −0.5≤z≤0。六层从下到上为 Si/SiGe/Si/SiGe/Si/SiO₂，各层厚度独立在 0.5–1 nm。柱外为空气，顶部随总柱高 H 移动至 H+0.5 nm。入射角 theta=89°、phi=90°、S 偏振，入射波的相位原点固定，不随顶部移动。

通用入口（正式运行需独立 owner 的已资格化 runtime、compiler policy 和监督）：

```bash
python scripts/run_case.py input/task44_sixlayer/A.dat --dry-run
python scripts/run_case.py input/task44_sixlayer/A.dat
```

A/B/C/D 是四个预声明代表点；其他点也使用同一个严格 `.dat` schema。源代码在 `src/`，不把数值核心写进任务 runner。大输出只进入 ignored `benchmarks/artifacts/task44/`。

## 数值与资源流程

1. 独立解析体积与实际网格比对：144 个贴体六面体、八类实体区域、正 Jacobian、两周期面对面节点一致。
2. 原双周期 Nédélec/Floquet MPC 和 air/Si 完整模式列表按本 case 生成。原始 FE 行、约束、材料、模式、源码均绑定自己的身份，不借旧 grating 的资格。
3. 单元内部自由度先作精确局部消元，保留全局界面和端口未知量；这是代数缩小待分解矩阵，不降低 p6 或改变方程。
4. MUMPS 先只做符号分析，以真实 INFOG 估计构造后续内存预算，再决定是否数值分解。INFOG(16)已含MUMPS的ICNTL(14)余量；新策略以实际headroom为内部workspace设置上限，另计PETSc转换、外部开销与独立安全余量。估计不是严格RSS上界；进程树、系统余量和零swap门始终有效。
5. 恢复完整场后，重新组装原始 UFL 作用与未截断原 C/D 端口函数，计算 **全部原 FE+aux 方程** 的显式残差。不得用凝聚系统、内部投影残差或 KSP 估计替代。此门通过后才产生正式 R/T。
6. 七个有材料区域分别计算体吸收并核体积/非空；再核 R00 分量、能量闭合、实际 Floquet 约束相位与误差。
7. 外部监督正常结束与物理/离散稳定性资格齐备后，才能将样本标为训练标签。单个 `NUMERICAL_GATES_PASS_PENDING...` 不等于最终标签合格。

端口采用 boundary-plane 幅度：同一边界物理场在边界平面直接表示，避免高倏逝模式经过全局 z 原点出现极端指数缩放；C、D、辅助未知量和 incident 投影同时改变坐标，物理边界和功率定义不变。功率在真实顶部/底部平面计算；Si 半空间的域外吸收不重复计入显式体吸收。

资源目标 tree RSS≤8×10⁹ B、合同硬限10×10⁹ B，同时受实时可用内存减安全余量的更严门限制；每阶段另留至少512 MiB，系统可用内存至少1 GiB，零 swap、MPI1、单线程、一次一个正式 PDE。当前无可用 cgroup，应用采样门不是操作系统绝对配额。源、JIT、失败修复和监督的时间都计成本，不因普通修复重置48小时。

## 源码兼容边界

执行分支接续 `task40extra_dot_parallel_cloud` 的 `a2f489ad0972279e5dd6ff15d41517c6e13fe79e`。用户指定的母任务参照为 `db790f92a186988c5147f1828d15c07034e7c430`；没有整体 merge/reset 或复制其大型研究路线。

本实现最小启用重复 cell kernel 求和、局部严格检查及精确宽度缓存。对当前分区常数材料、无 PML、轴对齐 affine hex 的体积 curl/mass 积分，平移不改变解析积分；该缓存是本次实现变体，而非母任务 actual-coordinate 缓存的逐 bit 资格继承。源材料变化、非 affine 或空间变系数不在此解释内。incident、端口和独立全残差使用实际坐标；最终仍以本次全残差和离散/物理稳定性为准。

## 最小样本策略与边界

首批计划8训练（含A–D）、4开发、6预封存盲点；不是必须完成所有点的承诺。只凭 train CV/dev 的有理由结果决定是否每批增加4训练点。最终模型/策略冻结前不消费盲标签；看过的点不能再称盲点。6个盲点只能支持有限 pilot 结论，不保证整个六维域精度。

当前没有证明新结构可计算、144hex足够精确或代理已可用。正式观测与普通失败将继续写同一任务 outcomes 和仓库模型总账；不以软件/材料成功替代科学成功。
