# BAL H 长周期 CGS 重正交受限对照

日期：2026-10-14 UTC。已绑定独审和最终费用账。

## 1 本轮结论

在同一 checkpoint6656、原 p4/H3/BAL_H 和 restart512 下，将 CGS refinement 从 never 改为 always，本次已记录的晚段真残差与递推报告值不再出现上一轮约9倍的偏离。末 native 真相对残差为 **0.0006937698325460939**，saved 为 **0.0006937697999576397**；native 真残差绝对范数0.0004781056207356328，KSP报告0.000478105620829126，二者范数之差绝对值约 **9.35e−14**。

相同512个outer步，前一轮 no-refine 的 native 真值为0.005062465528204434，本轮为其 0.137041887729，约降低86.30%。但 **512步、reason=−3，native 1e−11和saved 1e−9原门仍失败**。这个对照支持长周期重正交对本轮数值稳定性的作用，不能因此宣布原restart32平台根因解决、一般BAL_H修复、物理解接受或hp收敛。

## 2 唯一数学控制变化及实际配置

保持原108单元fine p6、24,056个retained未知量、同一checkpoint6656、native A/b、原p4 coarse、H3、BAL_H、右FGMRES、restart512及最多512步。数学配置只把CGS refinement从never改为always，未改PC返回、算子、物理、coarse空间或原验收门；另加入被动V观测和8点独立命名的checkpoint存档。被动观测有时间和内存成本，因此两轮墙钟差不能全部归因于refinement。

采用唯一隔离前缀选项 `ksp_gmres_cgs_refinement_type=refine_always`，setFromOptions只调用一次，确认选项确被消费并恢复原options数据库，前后KSP/PC/算子控制保持。前置options回执中的view_pending不是最终结论：后续actual KSP view已在solve前确认 classical Gram-Schmidt with one step of iterative refinement、right PC、UNPRECONDITIONED norm、非零初猜、restart/max512和24,056维。

源码独审63个纯测试通过（提供51、独立12），绑定1,011个source pins和22项最终描述。唯一命令SHA-256为 `20d71045a61980f60040446393c487bfff4de01e8af62063f256825b54eb1a6f`。源码审本身不是数值准入或科学结果。

## 3 每64步成对真残差

native/saved原RHS分母分别为0.68914155431206与0.6891415543120595。表中报告值也除以原native RHS范数；不混用单位q像空间指标。

| segment步数 | no-refine native真值 | always native真值 | always saved真值 | always KSP报告除RHS |
|---|---:|---:|---:|---:|
| 64 | 0.0114169343661 | 0.0114169342223 | 0.0114169342307 | 0.0114169342223 |
| 128 | 0.00713245767021 | 0.0071324571248 | 0.00713245698953 | 0.00713245712484 |
| 192 | 0.00457940654583 | 0.00457944378056 | 0.00457944344376 | 0.00457944378059 |
| 256 | 0.00257250181319 | 0.00257250180622 | 0.00257250141616 | 0.00257250180624 |
| 320 | 0.00154729292398 | 0.001547292535 | 0.0015472923593 | 0.00154729253511 |
| 384 | 0.00103816171255 | 0.00103308245449 | 0.00103308233686 | 0.00103308245454 |
| 448 | 0.0036958864723 | 0.000835235197267 | 0.000835235119336 | 0.000835235197325 |
| 512 | 0.0050624655282 | 0.000693769832546 | 0.000693769799958 | 0.000693769832682 |

本轮8个检查点的native真残差单调下降，最大已记录真/报告范数绝对差为9.349319278831314e−14。这里说的是残差范数差，不是两个残差向量的差范数，也不是全程每步都重新做了Ax。旧no-refine在384之后真值回升的事实保留。

比较按相同outer步数进行，不代表相同FLOPs或墙钟。前128步也不冒称逐值相同：开启refinement后允许浮点轨迹有所变化。最终native/saved残差映射相对差仍为1.0379202380575455e−5，既有raw失配不能被较小的范数差覆盖。

## 4 被动V512及Gram观测

仅在真实solve期间复制前512个成功返回的公共PC输入，作为实际V列。setup资格探针不计入，未捕获V513，没有复制Z或调用额外PC/Mat；原PC目的向量赋值和返回路径不变。V512占197,066,752 B，连同Gram工作区及额外安全量共预约279,619,328 B，未缩减原Krylov、factor、ELF或安全余量。

对G=VᴴV，每64列记录一次标量。最终512列的最大非对角绝对值 **2.9838656131567886e−16**，最大对角缺陷 **1.2434497875801753e−14**，`||G−I||_F`为 **9.424776282699452e−14**。没有新增Gram质量验收门，没有全谱或SVD计算。

V和完整Gram只在运行内存中，未持久化，也未上传；这些是绑定源码与现场回执支持的标量观测，事后独审不能重算未保存的完整V。旧no-refine长周期没有对应late-V Gram，不能从本轮小Gram直接反算旧V的失正交量，更不能推广到原restart32平台。

Gram累计计数3,251,601,408个复multiply-add，按每个8个real FLOPs的约定上界26,012,811,264；这是运算计数约定，不是实测吞吐。V复制0.17515215030289255秒、Gram 1.0289350479433779秒均嵌入本轮solve/墙钟，不重复相加。

## 5 八份本地checkpoint和独审范围

64、128、192、256、320、384、448、512步各保存独立命名的original-saved坐标NPY与metadata，单向量385,024 B，八份共3,080,192 B。它们均是未通过资格的迭代向量，未接受为物理解，不授权自动续跑；这次384向量仍保留，与上一轮被latest512覆盖的情况不同。

独审已用单次共享原CSR流分别重算8个saved Ax，核验向量/输入的文件、payload、typed哈希、有限性及读取前后稳定性。8点均与现场PETSc回执一致，也全部仍高于原saved 1e−9门；“重算一致”不表示“残差门通过”。384步独立saved真值0.001033082336868911，512步0.0006937697999606329，末点与现场相对值之差约2.99e−15。

复核对象是8份immutable向量；latest512 metadata与immutable512一致，但latest那一份payload没有另作第9次重算。没有独立重做native Ax或完整V/Gram。本文发布整理仅读小JSON，不读向量或大矩阵。

## 6 资源费用和历史计数

本轮563.2893764459877秒、采样tree峰值2,636,075,008 B、2,231个样本；child exit1后cleanup=true，remaining为空。回执记录575次预约、3,129个事件、无拒绝。最低host available6,780,862,464 B、最低disk free12,979,310,592 B，host/tree swap和pswpin/pswpout均为0。

原hard600、6 GiB AS、8 GiB tree、host≥1 GiB、disk≥4 GiB、zero swap、输出512 MiB保持。终审已核1,011个source pins、22项最终描述、全部2,231样本/575预约/3,129事件。最大projected AS为6,305,866,664 B，相对原6 GiB门尚余136,584,280 B；最大projected tree为6,436,930,504 B。二者是准入投影，不是实测RSS，也不把源码参考余量代替实际准入。终态普通文件27,017,095 B，低于512 MiB。当前PETSc句柄归零、PC销毁和supervisor清场不等于所有隐藏owner的显式销毁证明，也不补写旧中断运行的清场状态。

实际512次outer PC另有1次setup资格PC，总513次BAL_H；共1,026次逻辑粗调用、1,517次factor solve，其中491次额外修正。原粗返回门1e−10保留，最大返回相对残差9.649763651344908e−11。outer PC耗时437.942696810147秒已在solve中，不能与solve再相加。

旧历史累计10,000步仍耗尽，remaining=0；前一轮独立no-refine诊断512步保留，本轮另计512步，自己的remaining=0。没有归零历史、预算抵扣或自动超时续跑。

| 已知科学尝试 | 秒 |
|---|---:|
| restart512 attempt01 guard失败，0outer | 6.287231825001072 |
| restart512 no-refine512步 | 554.6500555199746 |
| 本轮refine-always512步 | 563.2893764459877 |
| 上述三次合计 | 1124.226663790963 |

本轮build91.1533550809836秒、KSP setup0.0005880389944650233秒、solve466.98463358997833秒都已在563.289秒内。项目ledger已知终态科学时长为 **22356.2180533551 秒**，含中断下界 **30270.210336198084 秒**；已绑定v78。账本不是精确总墙钟，准备、独审和等待未完整计时，不能记零；峰值内存不相加。

单独记录只读独审：8点stream Ax耗时36.68823532402166秒，峰值63,062,016 B，单次流读356,686,948 B；CPU36.704471000000005秒不是另加墙钟。标量审计0.17714740399969742秒、峰值56,254,464 B。复核没有新native solve、factor或FE，不加入科学stage之和。

## 7 止点与保留失败

本轮确认always配置实际生效，并观察到本次512周期的晚段norm gap消失；线性原门仍未过。保留旧no-refine失败、guard接线失败及源码漏测、checkpoint raw MISMATCH、saved/native PC及prediction raw失败、非零port压力资格失败。不接受field/solution，不报告hp空间收敛或原平台根因已经解决。

没有自动续跑；同配置接续当前512的后续设想仅为静态准备，未授权、未运行。任何后续数值另需具体方案和准入。本次只发布中文报告及小JSON，原报告不改，代码、checkpoint、V、Gram和大数组均不上传。

## 8 固定证据

路径相对 `hp_resume_20261013`。

- `restart512_refinement_independent_review/independent_source_review.json`：8076 B，SHA-256 `baab0b3dd520b9d642ce0961b2958861fb59088c585298646982f9c09031721b`。
- `phase4_balh108_restart512_cgsrefine_attempt01/summary.json`：2220 B，SHA-256 `fac1ba942c71920a558665feec581f04b5c415ced36c180945cfca1e29b7afdd`。
- `phase4_balh108_restart512_cgsrefine_attempt01/failure.json`：145 B，SHA-256 `c301265dc24731f1547141600917c68b021613f615af182d4dbfb7bacc3b4c1a`。
- `phase4_balh108_restart512_cgsrefine_attempt01/linear_terminal_before_gate.json`：232406 B，SHA-256 `d3b9ffe6c2077d994740e297afc2b22967a8f7deef2d728cdcb68503b63acb3c`。
- `phase4_balh108_restart512_cgsrefine_attempt01/actual_V512_observation.json`：4536 B，SHA-256 `7d9f5581a97d29edc46c5092a1d6196e872c3a28397ed4537370f89e339dbd47`。
- `phase4_balh108_restart512_cgsrefine_attempt01/linear_cleanup.json`：432 B，SHA-256 `8ceee51875abec64fd5b326fd4ed3ed3b7a1aa47644e48843fdfa9b1d1b2b57f`。
- `phase4_balh108_restart512_control_attempt02/linear_terminal_before_gate.json`：222568 B，SHA-256 `158de1fe07459c1213c115b6b7cc104ebffa4d61666e13d1a42ff7a5ca764d24`。
- `phase4_restart512_refinement_terminal_review.json`：196199 B，SHA-256 `7ec0e536458bdc2b0cd121c75d2e96a369809068b05ee467dcbb5562de6598ad`。
- `phase4_restart512_refinement_checkpoint_ax_review.json`：23041 B，SHA-256 `ff70e9fdb8d22b891e54ad5f215ea751f78bc5f104fab776dbe3ceebe8a5cca9`。
- `phase4_execution_ledger_v78.json`：61507 B，SHA-256 `dc633a17562b81ad59dcd33ea14d004f312ae5e835d371c6e8379dac1b835d62`。
