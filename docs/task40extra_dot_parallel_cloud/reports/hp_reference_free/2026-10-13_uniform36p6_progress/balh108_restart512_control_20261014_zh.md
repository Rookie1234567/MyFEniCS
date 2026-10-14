# BAL H 在 108 单元上的 restart512 受限对照

日期：2026-10-14 UTC。已绑定独立终审与项目成本账。

## 1 结论

扩大 restart 到 512 **没有通过本次科学验收，也没有在相同 512 步终点优于旧 restart128**。本轮 native 真相对残差在已记录的每 64 步标量检查点中，先从初始 0.020168106449264755 降至第 384 步的 0.00103816171254934，随后第 448 步回升至 0.0036958864723017908，512 步结束为 **0.005062465528204434**。旧 restart128 在同 512 步为 **0.003849530625293467**。

终点 KSP 递推报告值除原 native RHS 范数只有 **0.0005644500414216214**，真残差范数约为它的 **8.96884605669 倍**。本轮出现明显的晚段真残差与递推报告值偏离；不能只看递推曲线持续下降。KSP reason=−3，native 1e−11 与原 saved 1e−9 门都失败，child exit 1 后已清场。无被接受物理解或 hp 收敛结论。

## 2 固定对照和预算

使用相同 108 单元、原 checkpoint6656、原 p4 coarse、H3 和 BAL_H，并非 trace4/interior6 候选。实际 KSP view 确认：24,056 行，右预条件 FGMRES，restart=512、max_it=512、非零初猜、UNPRECONDITIONED norm、原 classical unmodified Gram-Schmidt 且 iterative refinement=never；没有 setFromOptions 覆盖。native A、b 独立构建，saved A、b 仅用于验证。

旧累计 10,000 步已经耗尽且 remaining=0，账没有清零。本轮另行批准的独立诊断消耗 512 步，自己的 remaining=0；重放计入本诊断。起点不是旧 restart128 的最终解，也没有复用旧 Krylov basis、因子或 accepted solution。PC setup 与 outer 计数分开；无自动续跑。

初始 native 真相对残差 0.020168106449264755，saved 0.020168106798117626；native/saved 原 RHS 分母分别为 0.68914155431206 和 0.6891415543120595。下表均用这些物理 RHS 分母，不混用之前像空间诊断的单位 q 指标。

## 3 每 64 步真残差与旧对照

| segment 步数 | 旧128 native 真值 | 新512 native 真值 | 新512 saved 真值 | 新512 KSP报告除 RHS |
|---|---:|---:|---:|---:|
| 64 | 0.0114169343661 | 0.0114169343661 | 0.0114169343743 | 0.011416934366 |
| 128 | 0.00713245767021 | 0.00713245767021 | 0.00713245753499 | 0.0071324576704 |
| 192 | 0.00667707575819 | 0.00457940654583 | 0.00457940620901 | 0.00457940654493 |
| 256 | 0.00514417672304 | 0.00257250181319 | 0.00257250142323 | 0.00257250185589 |
| 320 | 0.0049908713244 | 0.00154729292398 | 0.00154729274821 | 0.00154723723956 |
| 384 | 0.00434845334964 | 0.00103816171255 | 0.00103816158731 | 0.00104370098803 |
| 448 | 0.00425307145537 | 0.0036958864723 | 0.00369588649087 | 0.000722465541327 |
| 512 | 0.00384953062529 | 0.0050624655282 | 0.00506246555652 | 0.000564450041422 |

同一初始及第 64、128 步成对真残差与旧128的对应数据精确一致。不能扩大为整条递推历史逐值相等：前 129 个递推记录的最大绝对差 1.2828019896327092e−13、最大相对差 2.609828586914753e−11。

在第 192、256、320、384 步，新512的真残差小于旧128；但晚段发生退化。512 步终值为旧128同点的 1.31508644065 倍，约高 31.51%。第 384 步只是现有每64步检查点中的最小值，不是全程512个迭代点的最小值证书。384 向量 payload 已被 latest512 覆盖，只剩现场 typed SHA 和成对 Ax 标量；事后独审只能对现存512向量做 stream saved Ax，不能宣称独立复算了384点。

旧128后来共走了 1,116 个 segment 步，native 终值 0.0024270252847531574、saved 0.0024270249098316773，reason=−3，历史累计达到10,000；这仍是验收失败。旧1,116步终点与新512步终点不是相同 outer 步数比较，不能直接据此判断 restart 的效果。即使同为512个outer步，restart改变正交化开销，也不意味着墙钟或FLOPs相等。

## 4 递推偏离说明什么

512 步末 explicit native 残差绝对范数为 0.0034887553627580272，explicit saved 为 0.0034887553822716337；KSP 报告绝对范数为 0.00038898597887680286。第448步 true/report 比已达 5.11565778696，末点达8.96884605669。

这支持“扩大单个 Krylov 周期后，晚段实际残差与递推估计明显分离”的受限观察。CGS 不重正交是需要进一步检查的机制，但本批没有 late-cycle Arnoldi V Gram，不能直接认定失正交为唯一根因。此前首32步的小 Gram 误差，也不能覆盖本次第384步以后的长周期。报告不把相关性升级成历史平台的完整因果解释。

原 checkpoint raw MISMATCH 和既有 saved/native PC、prediction raw 失败不会因早期下降而被覆盖。无 field recovery 或 accepted solution；只保存 unqualified iterate 不构成续跑授权。新的数值方案另需准入。

## 5 attempt01 的接线失败与窄修

第一次尝试在 inherited builder guard 处抛出 `historical trial requires observe-only wall and10000 iteration policy`：旧 guard 要求 observe-only/max10000，新诊断要求 enforce600/max512。尚未进入 native fine、p4、H3 构建，没有新因子、KSP setup、Krylov basis 或 outer PC，outer=0。

原37个纯测试分别核对旧 builder 字节不变和新策略声明，却漏测真实 caller-policy 组合；负终审已更正此前源码“无阻塞”判断，历史记录不改写。candidate02 仅增加精确 diagnostic512/enforce600 分支，保留历史策略并拒绝混用，48 个纯测试、999 个 source pins、12 个最终清单项通过。旧 p4 raw bridge 在独立 legacy alias 下保持字节不变，真实 native 入口和桥接身份分别核验。该 guard 修正不改 PC 数学，也不能解释此前线性平台。

第一次失败的次级 cache-cleanup 提示和主 RuntimeError 都保留；supervisor 确认无剩余进程。唯一本次命令 SHA-256 为 `d983dba956a58e71b46118d69005f518df9330123ba3305dea4fa29711514550`，父任务记录 actual 启动于22:31:03 UTC。源码 JSON 的写入时间不能替代父任务的实际准入时间线。

## 6 资源和全部已知成本

| 尝试 | 科学终态 | 秒 | 采样 tree 峰值 B | 样本 | outer |
|---|---|---:|---:|---:|---:|
| attempt01 | guard FAIL，已清场 | 6.287231825001072 | 541388800 | 22 | 0 |
| attempt02 | 原真残差门 FAIL，已清场 | 554.6500555199746 | 2638864384 | 2198 | 512 |

两次合计 **560.937287344976 秒**。attempt02 的 BAL_H build 93.23406889897888 秒、KSP setup 0.0007027820101939142 秒、solve 456.3168956449954 秒均已包含在该次墙钟内，不另相加。

终审分别核对512次outer PC和1次builder资格PC，总513次BAL_H调用；另有1次KSP PC setup，不计为outer步。包含builder资格在内共1,026次p4逻辑粗调用、1,522次factor solve，496次额外修正；outer部分为1,024次逻辑调用和1,520次solve。原粗返回门1e−10仍有效，最大返回相对残差9.668078713109324e−11。fresh fine local LU 44、p4 local LU 16、p4 global symbolic/numeric各1；未从旧运行恢复因子。outer PC的435.01925427574315秒在solve内，粗修正223.2327165728202秒也是嵌套计时，不再相加。

原 hard600、6 GiB AS、8 GiB tree、host≥1 GiB、zero swap、disk≥4 GiB 保留；本轮 outer 诊断输出上限为512 MiB。restart512 源码推导 Krylov 预约410,318,496 B，比128多303,538,176 B，没有减其他 owner 或余量，不能把该预约当实测峰值。

supervisor 记录2,198样本无丢失，最大tree RSS 2,638,864,384 B，最低host available 6,782,468,096 B，最低disk free 13,009,715,200 B，host/tree swap与pswpin/pswpout均为0。resource-admission回执记录566次、无拒绝。当前PETSc句柄归零、PC销毁、remaining为空；`BAL_H_cleanup=null`不能冒称完整的逐owner销毁证明，也不能把本次清场推广成旧中断进程的已验证清场。

独审重算最大projected AS为6,026,239,144 B、最大projected tree为6,156,860,616 B，保持各自原门；二者不是实测RSS。终态普通文件合计23,291,653 B，低于512 MiB。

项目成本账：已知终态科学时长 **21792.928676909112 秒**；含中断下界 **29706.920959752097 秒**。已绑定 v76；账本不是精确总墙钟；准备、源码审、独核与等待未完整测量，不能记零。既有子段不重复计费，峰值内存不相加，原历史10,000步不归零。

另列只读复核费用：stream Ax 8.432055347977439秒、峰值24,641,536 B，单次流读353,991,780 B；标量审计0.2148979199992027秒、峰值63,533,056 B。stream CPU测量8.463529秒不是额外墙钟。它们不加入科学stage之和，也没有因此产生新outer、native Ax或factor。

## 7 独立复核与止点

独审已重核999个source pins、12项最终描述、2,198个资源样本、566次预约和3,134个事件。原p4实际CSR内容身份、H3阶数/窗口/对角哈希一致；运行专属的p4身份哈希并不相同，报告未将它们混称相等。

独审对现存512向量及原saved CSR/RHS进行单次有界标准库stream Ax，核验输入与向量的文件、payload和typed哈希、有限性与读取前后稳定性。重算saved真相对残差0.005062465556512935，绝对残差0.0034887553822665848；与现场PETSc相对值之差约−7.32e−15，二者都失败。不同归约顺序不宣称逐位相同。独审没有重新执行native Ax、FE构建、factor或solve，也没有复算已被覆盖的384向量。本文发布整理本身未读大数组。

本轮止于512步、reason−3和两道原真残差门失败；不继续外步，不因曲线前期下降接受物理解。报告只归档这次已授权对照的有限结论，不声称一般 BAL_H 修复、108 单元或 hp 收敛。

## 8 固定证据

路径相对 `hp_resume_20261013`；只上传中文报告和小JSON，代码、checkpoint、矩阵、因子和数组均不上传。

- `phase4_balh108_restart512_control_attempt01_terminal_review.json`：8893 B，SHA-256 `caa3a327e8e0d8688b75f06c1a1c38963d70da363d953a25489681fec4fcb084`。
- `phase4_balh108_restart512_control_candidate02_source_review.json`：23617 B，SHA-256 `4671f6b3a03e329cebc1b4c45f93a04b60b623534414ba1d5c2a9ce014d31a43`。
- `phase4_balh108_restart128_control_attempt01/linear_terminal_before_gate.json`：269250 B，SHA-256 `a3a527a2c6369f814401e3c79ef2de742dc76338dfb3356358e4b484721a4f0a`。
- `phase4_restart512_control_attempt02_terminal_review.json`：42818 B，SHA-256 `5bb7a0c35dff47a45d28cbde2a048080f290a75b37eb5ffffbafca92a5c41fc0`。
- `phase4_restart512_final_ax_stream_review.json`：8289 B，SHA-256 `d3de2a88fb59019a61f8b089e241bc964c44e9b893bb3842eb79ceebe9cd4aac`。
- `phase4_execution_ledger_v76.json`：57021 B，SHA-256 `e4a3d9c004724877895c6efb77899230db90594bc9d92123e6eb052dbd4df9b6`。
- `phase4_balh108_restart512_control_attempt02/summary.json`：2214 B，SHA-256 `d15a563b98e5c5e385e352f8e3a17f6b6853f1cea1ca12c308cc58274fc3d4a0`。
- `phase4_balh108_restart512_control_attempt02/failure.json`：145 B，SHA-256 `c301265dc24731f1547141600917c68b021613f615af182d4dbfb7bacc3b4c1a`。
- `phase4_balh108_restart512_control_attempt02/linear_terminal_before_gate.json`：222568 B，SHA-256 `158de1fe07459c1213c115b6b7cc104ebffa4d61666e13d1a42ff7a5ca764d24`。
- `phase4_balh108_restart512_control_attempt02/linear_cleanup.json`：432 B，SHA-256 `8ceee51875abec64fd5b326fd4ed3ed3b7a1aa47644e48843fdfa9b1d1b2b57f`。
- `phase4_balh108_restart512_control_attempt02/resource_admissions.json`：321655 B，SHA-256 `8433d0937604a29915c8c6533f64af38f03c2d87ef0d7339f96bb127a8dd8111`。
