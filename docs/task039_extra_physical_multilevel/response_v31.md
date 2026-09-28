# Response V31：Review V28 / V30 工作站引导型笔记本验证收口

## 结论

获准的 V30 笔记本 original p6/h7.5 完整场仅运行一次，126 步完成。独立重算的最终和释放后显式真残差均为 9.283162411158622e-7，低于 1e-6。分类为 DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED_WITH_LEGACY_CHECKER_INCOMPATIBILITY：本离散场的求解与一致性检查通过；没有连续极限或工作站可迁移性结论。

与 V29 同离散保存结果的离线比较通过：全有限元 L2 / scaled-curl 相对差为 1.4028635388466484e-14 / 3.3312391899680165e-14；同坐标 E/H 和界面切向 E/H 相对差均小于 1.5e-13；80 个有序模态的复振幅相对差为 1.9013904912668762e-14。这些由独立离线工具对已保存场计算，worker 的五个 field-reference checkpoint 仍如实保持 NOT_ATTEMPTED / MATCHED_REFERENCE_NOT_AVAILABLE。

V30 全流程 monotonic 时间为 2532.759 s，比 V29 慢 110.333 s（4.55%）；setup 慢 17.46%，纯 KSP 慢 0.95%。单场比较不能证明因果，但没有端到端加速证据，V30 只保留为显式 profile，不改 ordinary default。没有触碰工作站树或 master，也没有取得迁移或合并批准。

## Review V28 的 L1–L6 回答

1. **L1 监控。** 快速进程树 RSS/status、身份、swap 观察和后代清场链继续工作；heavy profile 的 PSS 明确为 disabled_by_profile，峰值为 null/unknown。正式运行 RSS 峰值是 8,044,191,744 B，9,955 次采样；观察到 swap 峰值为 0，但该策略是 observe_only，不称作强制零 swap 资格。小工作集控制流试验为 3 组启用/3 组关闭 PSS；只验证 provider 调用和采样流程，不推断 TB 工作集性能。
2. **L2 几何和对角。** 采用的参考能量对角使用真实 affine metric、实际方向和既有积分点/权重；相对 V29 对角差 7.13e-16，H6 apply 差 8.11e-16，power10 历史最大相对差 9.34e-16。990-cell 几何候选诊断用时 6.64 s；84 个 Jacobian 字节模式、124 个 Jacobian+permutation 键只是浮点缓存身份数，不是物理形状数。首次角点朝向假设错误的 instrumentation failure 保留在原记录中；不再追加几何分类。H6 pre-move 因缺少已资格化的唯一 owner 移交/清理路径而未采用。
3. **L3 局部批处理。** 六单元重复类 fixture 在相同全局 MUMPS 因子和 RHS、complex MPC、非零 Bi/Di/Bt/Dt、非 Hermitian 端口下通过代数闭合，最大差为 0；局部 LU 次数从每次 reduce/recover 的 6 降到 3。真实 24-cell、p4、80-mode 配对的候选在三组 CPU 与 wall 样本均慢，median 慢约 14.66%。因此正式 batch_size=1 仍走 legacy 路径；没有构造新数值全局因子，完整 C 性能为 UNKNOWN_NOT_MEASURED，约 600 行 full-C probe 已移除。
4. **L4 端口载荷。** 真实 80-mode 小载体与 synthetic 非 Hermitian 闭合检查通过，但 streamed apply 慢 65.48%，三操作总时间慢 3.129%；少持有的唯一端口 payload 为 1,784,832 B。保留 cached route；streamed route 仅 research，不进入正式组合。
5. **L5 正式场。** V30 一场通过独立残差、同离散离线场/模态/物理比较及 watchdog 退出检查。计时、资源和官方结果详见 [V30 outcome](outcomes/workstation_guided_local_v30.md)。旧 V25 dynamic checker 对 V30 返回 DYNAMIC_FAIL，失败项仅为静态 backend_identity；raw BAL_H/p4、真残差、native A4 和 first-Arnoldi 子门通过。保留 checker 原结果，不将其改写为 PASS；独立 V30 checker 的结论是 PASS_WITH_AUTHORITY_LIMITATION。
6. **L6 交接与推送。** [选择性交接清单](outcomes/selective_workstation_handoff_v30.md)区分 V26–V29 已有工作、V30 新且本机合格内容、未采用内容，并记录目标工作站 ABI/端口/几何字段仍须从其权威清单逐项复核。该清单不授权迁移。V30 的源、输入、场几何和有序模式身份见 outcome/compact record。

## 验证与边界

正式 PDE：1 场；新增完整 PDE：0。已有 targeted source suite 为 5 passed in 6.78 s，compileall 对变更 runner/solver/目标测试通过。L2/L3/L4 的小型工程诊断单独记录，不计入 PDE 通过数。本次文档收口不重跑 pytest；V30 JSON/run_index 解析、selection 所引 compact/component/checker/monitor SHA、三份新报告的本地链接和 staged git diff --check 均通过。full repository pytest、Ruff、MPI2/4、GitHub CI 均未运行/未声称通过。

正式 source SHA=254f0cf78f950246655dc86af9409139b9a97680；input SHA=ba2c0745221a017d71f606325c20e98a3a57611887929fe55c18180f308f544b；physical-model SHA=0875aaf070d88732b09ead8c55a7d4c28dd75f9b329e90f35fea984a0b7464e6。分支仍为 task39extra。此次交付记录按同一执行分支提交/推送，等待主控 review；没有 master merge、默认提升或工作站迁移授权。
