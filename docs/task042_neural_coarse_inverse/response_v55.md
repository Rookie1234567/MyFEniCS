# Response V55：旧解补审完成，新 H7 系数保存；准确性比较仍缺项

已补齐 V54 的 R6/R7/C 独立原式、恢复与完整模式功率审核，并实际得到 320hex/p7、828 模式的 H7 完整解。H7 原 true/native 残差 4.20391286913e-11，直接目标 1e-10 达到；独立保存数组重算通过。主 actor 在后处理时触及预登记 wall 上限，补消费又遇残留 JIT 标记及 CPU/SMT 准入拒绝。两次资源观察额度用尽后收口：新进程 H7 q63 审核、体吸收/能量、R7→H7 与 R6→H7 的完整场增量均 **not_run**，不授完整 NOTCH 准确性。本批没有 NN 训练或 NN 收益。

| 实际阶段 | 完成的对象与证据 | 未完成项/具体原因 |
| --- | --- | --- |
| Q0，旧三解补审 | q63 新进程原未凝聚式、内部恢复、真实 basis、所有模式功率；原旧场只读，factor/solve 0 | 旧 3.41% 跨 p 场差保持 FAIL |
| SETUP | H7/T6 实际 mesh/MPC、raw 类、64GiB 规划及 100000 行接线通过 | 不把预测当 numeric 准入 |
| H7，Z4/p7/828 | 完整 u/port/κ/mesh/MPC 已保存；1 次完整 solve、1 次固定精化；全局 factor 随后释放 | 原 dat PERFORMANCE_CONTROLLED_STOP；完整返回不是完整后处理完成 |
| 保存解补消费 | 无 factor/solve；恢复、320 cell-center E/H/curl、828 复振幅/功率已保存 | A_volume 的 FFCx 编译遇原中断留下的 0B marker；保存并移走该 marker 后重入仍被 CPU/SMT 门拒绝 |
| 独立数组 checker | 重算已存 q47 原体作用与独立已存 q63 carrier，恢复误差 1.66744658543e-15 | 不是 fresh FE VERIFY，也不是共同网格准确性比较 |
| T6 / 新 FE VERIFY | not_run | 按旧每类中位时长预测，T6 原始核准备约3024.55s，已超过剩余完整-case预算；新 FE 重入额度耗尽 |

按最新合同只细化空间分辨，材料、三维缺口、入射、κ、完整 Cκ、全部内部及双周期/828 端口未变。H7：独立 FE330848、trace88928、内部241920、原生346724、凝聚89756行；MUMPS 底层 symbolic/numeric 合法准入，存在有限全局精确因子，不能称 factor-free。规划64/warn80/采样 stop96GiB仅限本批；numeric 实际 RSS13,385,756,672B＋2×13,052 decimal MB＋2GiB=41,637,240,320B（约38.78GiB）低于64GiB。最大同时整树采样峰 22.8337974548GiB，swap/OOC0。

**关于“又做凝聚/重复别支工作”：** 凝聚是在单元内先消去内部未知量、减小全局系统，再按原方程完整恢复。直接复用既有实现，原凝聚及 raw-provider 核心未改。只读核对工程冻结、dot 可访问冻结/最新组件、5nm学习分支任务记录；读到的对象几何/p/模式不同，没有找到当前 H7 的完全匹配生产包。工程最新对象本机不可取，因此不宣称穷尽所有分支。H7 的38类未舍入几何体张量无法命中旧Z2类，约 12393.2724637s；局部 Schur 消元约 52.7429328552s。全部新原张量已原子保存并重开校验；以后补审这份解不应重新生成或分解。

本轮研究收费下界超过 **15400s**，精确最终金额与逐项 lower/unknown 见[最终费用](outcomes/records/resource_costs_final_v55.json)。H7 原 dat 链下界 13627.0547106s，Q0 下界 1333.09409157s；缓存补消费费用及两次观察共320.322s分列，失败和拒绝未抹去。raw 生成、凝聚、numeric、solve 的父子 inclusive 时间不叠加；新/旧准备、冷 N=1、研究总费用不混称。所有性能为 shared-workstation，未建立无争用加速比较。历史已知下界139828.48144973788s保留，历史缺段及完整冷费用 unknown。

科学 source `5e61f1acf569bf43b33bceeebcc949e1b0f1efc9`，保存解消费 `2bab0aa16901f6c4ed28a83f90cd78284e304b6e`，最后独立数组 checker/接线 source `b7753e35150d83eb45dec28ebe1fb4e91736ae6d`；正式文档 HEAD 另见交付/最终 Git receipt，不能替代运行 source。Review `e3b46656fd13b31a465a628f7fdeb863e32f38ed`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc`，canonical/唯一分支一直保持。8项 focused 回归、相关 Ruff/compile、8个dat validate通过；15项文档合同与最终表格/链接结果见[文档检查](outcomes/records/documentation_checks_v55.json)，不声称 CI。GitHub视觉 NOT_VERIFIED。

唯一下一建议：新合同只消费现有 H7 完整系数，补 A_volume/能量、fresh q63 原式及 R7/H7、R6/H7 共同物理场比较；先完成这条保存链再判断是否需要新空间，**不重 factor/solve**。当前未证明 H7 更准确，也未取得连续收敛、原尺寸0.7nm、2TB/48h或同正确性 NN20%。

[完整物理/费用结果](outcomes/spatial_resolution_audit_v55.md) · [门分类](outcomes/records/gate_verdict_v55.json) · [父独立审核](outcomes/records/prior_audit_completion_v55.json) · [H7保存检查](outcomes/records/partial_saved_checks_v55.json) · [run index](outcomes/records/run_index_v55.json) · [原始版本](outcomes/records/raw_archive_index_final_v55.json) · [运行源码](outcomes/records/source_bindings_v55.json) · [修复/拒绝](outcomes/records/repairs_v55.json) · [最终关闭](outcomes/records/campaign_closed_v55.json)

旧 task/review/response/raw 保持；本轮不通知隔壁、不 merge、不自动打开下一窗口。精确最终 HEAD/upstream/clean/清场/锁释放及交付时刻见最终 Git receipt。
