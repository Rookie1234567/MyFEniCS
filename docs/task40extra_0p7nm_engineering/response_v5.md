# Response V5：Gx784 工程尝试与安全后处理收口

本回执记录 Review V5 唯一 Gx784 尝试。该 worker 在数值预检、有限元装配和场计算前因实现接口错误退出；没有官方场、真残差或 R/T/A。修复已提交并通过定向测试，但 Review 授权的 bug replay 已用完，本回执不启动第二次正式尝试。

## 执行结论

| 项目 | 结果 |
|---|---|
| 正式 Gx784 worker | WORKER_FAILED，源 SHA 24a56962c733b9ae5454000cdae224dae6dda8f0；进入 V20 worker 后因旧 worker 仍要求全程 observe_only，与本模型的新 enforce-time 策略冲突，在数值 runtime preflight sample 和 FE 前退出。父级 run_summary workflow monotonic 为 3.939483341993764 s，watchdog 子进程树监控区间为 3.9084257329814136 s；conservative budget charge 为 3.939768298688392 s。失败时同时树 RSS 峰值 133,492,736 B（16 样本）、task swap 0 B、PSS 为 null/DISABLED_BY_PROFILE，process identity coverage complete，后代已清场。这是 FE 前失败峰值，不代表模型 setup、KSP 或恢复的内存；这三项均 NOT_RUN。此为工程失败，不是数值求解失败。 |
| 数值与物理输出 | full-system 真残差、恢复 Gate、保存场、模式与功率均 NOT_RUN / unavailable；无 official result。缺失残差不能解释为残差超限。 |
| 后处理 | 第一次启动因 watchdog 父进程已有子进程而被专用父进程保护拒绝；0.4904406969435513 s 是 conservative budget charge，不在此处称为实测 elapsed。修复后的安全预检已对旧失败记录执行：solver/recovery Gate 未通过即写入 HELD 对照并结束；未启动 worker、未预留预算、未导入 FE 栈。 |
| 共享预算 | 总上限 172,800 s，账本累计工程扣时 4.619253995631944 s，预算余量 172,795.38074600438 s；active_attempt=null，唯一 bug replay 计数为 1。该值是保守预算记账，不能称作数值求解耗时。 |

旧记录中的另一次启动错误 NameError: CONSERVATIVE_REALTIME not defined 发生在 watchdog、worker 与网格启动前；0.189045 s 是 systemd leader lifetime 由 monotonic 微秒差除以 1e6 得出的上界，并非准备或 PDE 时间。原 receipt SHA256 79acefeef2064ec738ba38f6158e2af9d3d050195068a8e86eb73b1ae7fd1da0，corrected receipt SHA256 11f019b28297520424999816cdb86103e36caf0beae88093c262126456604b49；三项均作为工程问题保留。worker 错误已通过精确模型身份策略修正；后处理改为 stdlib-safe 预检，并保留 subreaper_watchdog 的 dedicated-parent 保护。V20 的 enforce-time 仅适用于确切 Gx784 身份，其他 case 继续 observe-only。后处理先用轻量 checker 重算求解/恢复 Gate；只有 Gate 通过时才核对保存包中的数组路径及 SHA，再进入既有预算和监督流程。单元测试验证这个顺序，不代表 Gx784 已运行。

## Held 对照与证据

从已有失败 run 离线生成的 [gx784_pair_comparisons.json](../../results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_gx784_review_v5_v1__full3d_iterative__mpi1__Mna/20261003T074956.168518Z/postprocess_v5/preflight_held_v1/gx784_pair_comparisons.json) SHA256 2a64edae51d51a62379e4f11c978362d5654dd18d8e7ab81af4d2b377cf57006；独立 checker [gx784_independent_check.json](../../results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_gx784_review_v5_v1__full3d_iterative__mpi1__Mna/20261003T074956.168518Z/postprocess_v5/preflight_held_v1/gx784_independent_check.json) SHA256 f14e52fdc3fae9d5fb955361dc1956972a9a6a0de58ff75ba518fac6ab766ca3。classification 为 solver_or_recovery_gate_not_passed_comparison_held；所需残差/恢复字段没有保存，所以 field check、场恢复、场差和功率比较均未执行。生成过程只调用预检与记录写入辅助函数，没有调用 service 入口、worker、预算 reserve、watchdog 或 FE 模块。

Compact 哈希与逐项分类见 [review_v5_execution_closeout_v1.json](outcomes/records/review_v5_execution_closeout_v1.json)，运行索引已更新为源 SHA 969b4086320b844d44fb0b67092ffe5af2d760b1。原始清单和 repair 清单均已存在；本次 closeout 复用记录，没有重跑 AUTO。两次旧 inventory 生成耗时没有测量，分别为 unknown，不代表整个 V5 没有生成 inventory。

| 已保存记录 | 路径 | SHA256 |
|---|---|---|
| 原始 target ledger | benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/target_ledger.json | 8dd917dbb7252bfb0abca81213f3d3cba93cd1f35010a55cbf8c27e2f32ecd4a |
| 原始 resource ledger | benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/target_resource_ledger.json | 885edd2fcb42ce1b7bd06782c596d99cec120834523e2284d428fe3fd7019aa4 |
| repair target ledger | benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5_repair/target_ledger.json | 92c6a0f458ffa2d84911744cd8d6138f93414e8b850dfae205093e9618e45ae2 |
| repair resource ledger | benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5_repair/target_resource_ledger.json | 619fe86652d836deb6591eb1ffc59be8346d33a6287adf57178a162aac226fe2 |

两份 AUTO manifest 的 SHA 均为 52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d，ordered-key digest 为 03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec；32,060 是外部端口 AUTO 模式数，不是完整内域资格。

| 资源对象 | 已知的 measured/derived 数字 | 未知与口径 |
|---|---|---|
| 候选网格 | derived 272×4×14=15,232 cells；p6 full/周期独立 rows 10,228,620 / 9,948,672；retained 3,126,332；p4 interface+AUTO 1,346,364 | 只有计数与 payload 推导；未建 FE mesh，未组装 |
| AUTO H | 单个对角 H 512,960 B；一个 dense H 16,445,497,600 B | H/Hhat 所有权及同时存活 unknown |
| 内部 450/432 | 882×882 raw tensor 12,446,784 B；450 LU 形状 payload 3,240,000 B；432 Schur 2,985,984 B；450×432 coupling 与单 recovery map 各 3,110,400 B | 均为单实例 dense-shape 推导；局部类数、稀疏 fill、复用与生命周期重叠 unknown |
| 外层 Krylov | restart 32；Krylov 与 preconditioned 两组各 33 vectors、每组 1,650,703,296 B；另 8 vectors 400,170,496 B；总 74 vectors 3,701,577,088 B；full scratch 4,428,003,200 B | 源码公式 derived payload，不是 simultaneous RSS；生命周期 overlap unknown |
| setup、因子及输出 | — | cold JIT/quadrature、C/D、Di/XiB、projection、所有 q 的实际稀疏 factor/fill/workspace、完整恢复/输出/校验成本均 unknown；PDE not_run |
| 资格合同 | 最大物理内存 2,000,000,000,000 B；swap 0；完整 workflow 172,800 s | 目标容量与时间资格未测；unknown costs are not zero |

目标清单生成耗时分别为 unknown；ledger/hash、完整未知项、known bytes 的来源和当前 machine snapshot 见 compact record。workflow shared ledger [shared_workflow_ledger.json](../../benchmarks/artifacts/task40extra_0p7nm_engineering/task40_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_gx784_review_v5_v1/shared_workflow_ledger.json) SHA256 67c086c9fa975c97a3a6980bfa5ac4fa9cb60c59e2fa2f5ea60f477e86c72c8d。

## 验证及未关闭边界

Source commit 969b4086320b844d44fb0b67092ffe5af2d760b1 的后处理、相关 V4/V5 与 worker-time targeted tests 为 35 passed in 0.33 s；V20 lifecycle tests 为 12 passed in 13.71 s。qualified WSL ABI preflight、compileall 与 git diff --check 通过。之后的文档合同检查记录在 [test_summary.md](outcomes/test_summary.md)。Full repository pytest、MPI4、Ruff 与 CI 未运行。

Dot 仍为 HELD / NOT_RUN：public head 仍是 eb5b0ecc1afe593f626b44a6038f7f26651b3317，raw_artifacts_durable=false、storage_approval_pending=true，云端数值执行结果未知；没有本地 dot run。普通默认未改，未合并 master。V5 的 Gx784 数值对照仍未完成；是否再开正式尝试须由新的审阅/授权决定。
