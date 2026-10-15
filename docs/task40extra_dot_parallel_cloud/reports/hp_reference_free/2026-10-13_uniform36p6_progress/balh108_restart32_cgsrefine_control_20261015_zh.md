# BAL_H 原 restart32 重正交同起点对照

日期：2026-10-15 UTC。已绑定独立终审、四点 saved Ax 复核及最终费用账v84。

## 1 结论与读法

本轮回到原 checkpoint6656，保留 restart32，只把 CGS refinement 从 never 改为 always。200 步后 native 真相对残差为 0.020024030230521024，saved 真相对残差为 0.020024030553639136，仍未通过原 native 1e−11 / saved 1e−9 精度门。64/128/192 的两空间真残差与旧 no-refine 曲线近乎重合。64/128/192的新旧真残差比在约1±4.4e−12内；200步native真残差相对原起点只降低约0.7144%。此受限对照不支持“仅加重正交就能修复原 restart32 平台”。

CGS 是构建迭代搜索方向时剔除重复方向的方法；refinement=always 表示再做一遍正交修正，目的是减轻舍入误差积累，代价是额外向量运算。restart32 则每 32 步重新开始一组搜索方向。这两项作用不同，本轮保留原重启长度，避免把长周期得到的改善归到重正交本身。

真相对残差用原算子实际计算 b−Ax，再除原 RHS 范数；native 与 saved 是两种坐标表示，须各自判断。KSP 递推报告来自求解过程的内部更新，不能替代真残差。200 步 reason=−3 是用完本轮上限，不单凭该码宣称数值发散；child exit1 源于原验收门失败。

## 2 同起点与范围

108 单元、fine p6、24,056 维、原 native A、p4、H3、BAL_H、右 FGMRES、CGS 及原残差门保持。对照两边均从原6656的同一 saved 向量起步，没有改用长 restart512 改善后的7296或7660向量，没有复用 Krylov 基或因子，也没有新缩放或归一化。saved 文件/typed身份与映射后的native身份分开。本次实际映回native的typed SHA与producer一致，旧restart32和本轮初始paired Ax相同；这是核验结果，不能一般性假设往返映射恒等。native起点真相对残差0.020168106449264755，saved为0.020168106798117626。producer曾记载0.020168106798117612的残差；与本轮native差异保留为观察，不新增匹配验收门，也不把saved/native哈希互换。

唯一命令 SHA-256：`7f654003a2e98fc5b2d9f7c05b002d81c43a5aae474fed04587929545b408266`。源码独审通过63项纯测试及实际完整launcher科学入口前检查；科学导入、实际AS安装和运行准入不能由该预检冒充。终审另核验实际KSP view为right FGMRES、UNPRECONDITIONED、非零初猜、restart32/max200及refinement=always，限定前缀选项确已消费且options数据库恢复；1,040个source pins与31项最终描述重新核验。

本次新独立预算为200 outer / hard600秒。仍使用6 GiB AS、8 GiB tree RSS、host available≥1 GiB、disk free≥4 GiB、zero swap、输出512 MiB。没有 V/Gram 采集，不提供跨restart正交性测量。64、128、192和terminal200保存paired true Ax及独立命名的未合格saved迭代向量。

## 3 原 restart32 逐点对照

下表是现场保存的paired Ax记录，数值越小越好；native/saved分母分别为0.68914155431206和0.6891415543120595。旧64/128/192向量已未保留，表中的旧真残差是当时记录，不声称本轮事后重算了旧向量。

| 本段步数 | 旧 never native真相对残差 | 新 always native真相对残差 | 旧 never saved真相对残差 | 新 always saved真相对残差 |
|---|---:|---:|---:|---:|
| 64 | 0.020114848902987346 | 0.02011484890294945 | 0.02011484924413727 | 0.020114849244089024 |
| 128 | 0.020070101796872672 | 0.020070101796902166 | 0.020070102135122884 | 0.020070102135142032 |
| 192 | 0.02002740403819845 | 0.020027404038285797 | 0.020027404374277698 | 0.020027404374276008 |
| 200 | 未测 | 0.020024030230521024 | 未测 | 0.020024030553639136 |

旧200只有native递推绝对范数0.013799391316643032；新200相应递推绝对范数0.013799391316697367，相差约5.43e−14。旧200没有paired真Ax，也没有可供复核的saved向量，因此不能把旧200递推值改名为独立真残差，更不能据它声称两次200步的真残差完全相等。

四点saved独审共享一次原CSR流，对每个向量分别计算原saved Ax，文件/payload/typed身份、有限性及读取前后稳定性均已核验，四点均与现场记录一致。latest200与独立terminal200副本payload一致。该审计没有重做native Ax、FE、factor或solve，也未重算V/Gram；“复核一致”与“精度合格”是两个不同判断。

| 本段步数 | 独立重算saved真相对残差 | 判定 |
|---|---:|---|
| 64 | 0.020114849244149306 | 一致；原1e−9门失败 |
| 128 | 0.020070102135173098 | 一致；原1e−9门失败 |
| 192 | 0.020027404374299566 | 一致；原1e−9门失败 |
| 200 | 0.020024030553658922 | 一致；原1e−9门失败 |

末native真残差绝对范数0.013799391316652936，与本轮递推报告的绝对范数差为4.443147239019396e−14，真范数/递推范数=0.9999999999967801。这是同一native空间的范数比较，不是残差向量差，也不是跨坐标等价证明。128和192步记录STAGNATION_FLAG；128步观察窗两空间改善均不足1%，只标记而不硬停。未触发增长/递推gap硬停，条件性paired重核次数0。

## 4 费用与清场

现场supervisor科学墙钟275.7723769709992秒，采样整树峰值2,633,207,808 B、1,091个样本，child exit1，cleanup_verified=true，remaining为空。本段清场不能回填历史中断段的未知清场。当前显式句柄清零与PC销毁也不等于全部隐藏native owner释放证明。

历史10,000步不变，先前三项独立诊断收费1,536步，本轮200步新增独立收费；本组独立收费1,736步，连所列历史账的选定链小计为11,736步。此数不是整个项目的总步数；p5、recycling等其他独立实验仍各自记录在完整ledger内。先前1,536内含旧中断的一步已知在途调用，不能写成全部完成。原中断后遗失的20步没有返还，重放没有预算抵扣。路径标签6856只是本次向量来源，不能作为累计收费。新预算剩余0，不自动续跑。

本轮200次outer PC与1次setup资格PC分开，合计201次BAL_H、402次逻辑粗调用、602次factor solve，其中200次额外修正；最大返回native粗相对残差1.0144038751009637e−11，原1e−10粗门保持。build91.55565269500948秒、KSP setup0.00030276700272224844秒、solve179.14004117698641秒已含在275.7723769709992秒科学墙钟内；outer PC的172.30212118304917秒也在solve内，不再叠加。

独立终审核对1,091个资源样本、249次内部准入、1,588个事件，最低host available6,781,259,776 B、disk free12,894,638,080 B、swap0。最大projected AS5,648,602,280 B、projected tree5,780,088,008 B；这些是准入投影，不是实测峰值。full32 Krylov预约32,370,336 B，V/Gram预约0，原true-Ax scratch保留12,237,568 B；输出普通文件21,180,806 B，原限制均通过。

最终费用账v84的项目已知终态科学墙钟合计23,062.092474517078秒；加入既有中断下界后至少31,197.525687890084秒，仍不含未知准备/等待且不宣称精确端到端时长。四点saved Ax独审另用21.761706291988958秒、单进程峰值41,803,776 B；标量终审0.15211727999849245秒、单进程峰值40,939,520 B。这两项不计入科学stage合计，也不与整树峰值相加。

费用口径保持：build/setup/solve等若已经在科学墙钟内，不重复相加；独立复核单列；历史中断保留下界而非精确墙钟，准备/等待不完整而非零，内存峰值不相加。

## 5 已解决与仍未解决

[上一份restart512恢复报告](https://github.com/Rookie1234567/MyFEniCS/blob/caa67ed41a1086e0d6cc3a75f4e0386baf54071c/docs/task40extra_dot_parallel_cloud/reports/hp_reference_free/2026-10-13_uniform36p6_progress/balh108_restart512_recovery_20261014_zh.md)保留了长restart512下的重正交改善，以及native真残差与递推范数偏离被抑制的证据。本轮原restart32负对照不推翻该结论；它说明该修复不足以解释并消除原短周期平台。

尚不能仅据此认定唯一根因，也不能排除所有其他实现错误。既有raw失配、saved/native PC及prediction raw失败、非零port压力资格失败仍保留。未取得原精度合格场，不做场恢复或official物理量，不宣称hp收敛或目标规模资格。

本报告只记录此次200步对照，不授权额外outer、改参数或自动续跑。下一方向仅为静态设计如何保留历史长周期的有效校正方向（augmentation），相应实现与数值执行均未获授权，本文不承诺将执行。仅将中文报告与小JSON发布到指定分支；代码、数组、CSR、NPY、ELF、基向量和大日志均不上传。发布途径为connector文档提交，不冒充本地canonical worktree、CI或GitHub rendered view验收。

## 6 固定证据

证据路径相对 hp_resume_20261013；完整科学数据留在本地，以下仅列摘要身份。

- `restart32_refinement_independent_review/independent_source_review.json`：31206 B，SHA-256 `d1a570f27fe4db66bc740e7844c399da07cf7cf176128185c03b3673a23d1c6a`。
- `phase4_balh108_restart32_cgsrefine_candidate01/restart32_comparison_reference.json`：10357 B，SHA-256 `1012aa2b22caf61e191fc641f11af1144727df3b40a66ec4afe6d9cd68124d05`。
- `phase4_native_cached02_incomplete_review.json`：5748 B，SHA-256 `552384520086ec48a9a7e4578a2af99773d3c4543f93bd8d7d833620fa5d66cf`。
- `phase4_balh108_restart32_cgsrefine_attempt01/summary.json`：2215 B，SHA-256 `ee02db9e4e33de495c54296f5b59c4f1c583fb7a97d4f11a43c6577bbbb965d8`。
- `phase4_balh108_restart32_cgsrefine_attempt01/linear_cleanup.json`：432 B，SHA-256 `2b810a4a45fc29d41abc363e3d66813a1bc91c03fa644eee7279e1310eb4d874`。
- `phase4_restart32_refinement_terminal_review.json`：91791 B，SHA-256 `ad8622ba1fbeaa780fd760ed24b31e792990fb8a6d27af35f3aa2e5daf44c905`。
- `phase4_restart32_refinement_checkpoint_ax_review.json`：15009 B，SHA-256 `ca7322873c18ba9a40b7fa77910cb1f77bad6bb23c677779daf0e2b5df939934`。
- `phase4_execution_ledger_v84.json`：72959 B，SHA-256 `1a04781eac170d32f4e81a4d98a27e13176506e994f7b7ce1b1ea3a932d7eeb9`。
- `phase4_balh108_restart32_cgsrefine_attempt01/linear_terminal_before_gate.json`：209439 B，SHA-256 `65b988cc39997f8fe8a6c5ca1818ccaca0fa11b52e5c7858680f60683616d1a7`。
