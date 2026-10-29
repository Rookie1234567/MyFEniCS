# Task41extra Response V18：完整 Jz 求值改善，但旧 star 出现末态退化

**结论：V18 受监督 service 与独立 checker 正常完成；候选结果为 LOCAL_MIXED_NOT_QUALIFIED。** 补偿求和使 16 个已保存完整 Jz correction 的复数向量 L2 均更接近对原存储 J、z 的高精度参考；生产顺序 replay 中，V17 主 star 两列和 V14_v11 star 两列最终 d 均改善。但 V14_v8 star 的同一 RHS 列 0 最终 d 从 8.7454666764e-11 增至 1.0008161688e-10。不能挑主 star 报 PASS；候选不获支持，全域、full owner、官方结果仍未资格化。

## 1. 这轮做了什么

计算直接读取三个已有 saved stars，不重新组装有限元算子，也不改变矩阵或保存状态 z。只把完整 432 行的 Jz 乘积求和换成实、虚分量分别收集 binary64 乘积后用 math.fsum 求和，再按生产次序重放原 RHS。fsum 的作用是减少已舍入乘积相加时的抵消损失；它不能撤销乘法本身的舍入，也不保证每个逐分量或下游物理量都改善。

| 实际范围 | 结果 | 不能据此声称 |
|---|---|---|
| 16 个不同完整 Jz 输入：V17 两 cell × 两列的 initial/final 共 8 个，两个 V14 saved stars 的 final 共 8 个 | 16 份 432 行 correction 均保存；candidate 和 production-order replay 后由独立 checker 重读 | 不是新解，也没有全域覆盖 |
| 新工作计数 | 16 个 correction；LU/factorization=0，GETRS=0，积分=0，native FE action=0 | 不包含新的矩阵装配或 PDE 求解 |
| 独立检查 | 432 行均检查；candidate_numerical_conformance=true；16/16 个输入与“先按 binary64 舍入乘积、再按 Decimal 高精度求和”的参考相差不超过 1 ULP | 不等于每个分量都优于旧 BLAS，更不等于物理资格 |
| 候选资格 | candidate_supported=false；global_qualified=false；scientific_qualified=false；official_result=false；full_owner_unlocked=false | 不解锁 full owner、200q、恢复或官方 R/T/A |

对 12 个 final-state 输入，复数 correction 与从原存储 J、z 直接做 80 位 Decimal 乘加的参考之间，聚合 L2 从 2.5466733841e-9 降至 2.0057324742e-10。所有 12 个输入自身的复数向量 L2 都改善；但这不代表每个实/虚分量、每行或最后的 d 都改善。checker 另外记录这 12 个输入共有 605 个行-分量误差比旧值大，单个输入有 33–60 个；误差整体下降与局部分量变差可以同时成立。

| saved star / 状态 | 完整向量数 | 普通 BLAS correction 对 80D 参考的聚合 L2 | V18 fsum correction 对 80D 参考的聚合 L2 |
|---|---:|---:|---:|
| V17 cells 7873/8014，initial（只作诊断） | 4 | 1.596813089e-9 | 1.289291531e-10 |
| V17 cells 7873/8014，final | 4 | 1.732334077e-9 | 1.238777290e-10 |
| V14_v11 cells 360/446，final | 4 | 1.329837547e-9 | 1.174178358e-10 |
| V14_v8 cells 23352/23493，final | 4 | 1.309998500e-9 | 1.053422406e-10 |
| 三个 star 的全部 12 个 final 输入 | 12 | 2.546673384e-9 | 2.005732474e-10 |

表中 L2 汇总的是四份各 432 行 correction 的误差平方和开方，单位是保存向量分量；它不是 full-action relative error。final 12 输入上，独立 80D 参考的候选最大实部/虚部绝对分量误差分别为 1.721090465e-11 和 3.304357231e-11。旧、新 correction 的逐行细节与每份输出 hash 保存在 workstation ignored attempt02 及 checker 报告内；Git 仅收录 compact 与路径/hash。

## 2. 三个 star 的 final d

下表的 d 是按原生产次序、使用候选返回 correction 实际重放的复数值；括号中为其模。V14_v8 的 j0/j3 是相同 RHS 的重复标签，表中只计一次，不能伪装成两份独立证据。

| saved star / 列 | 原 BLAS final d | V18 fsum final d | 模：原值 → V18 |
|---|---|---|---|
| V17 cells 7873/8014，列 0 | 8.3127815742e-10 + 1.5461409930e-11i | 3.5470293369e-10 + 1.8189894035e-12i | 8.3142193272e-10 → 3.5470759774e-10，改善 |
| V17 cells 7873/8014，列 1 | 2.0190782379e-10 + 1.6625563148e-9i | 2.5102053769e-10 + 7.0940586738e-10i | 1.6747717066e-9 → 7.5250780396e-10，改善 |
| V14_v11 cells 360/446，列 0 | 2.0372681320e-10 + 7.2759576142e-12i | 1.6370904632e-10 + 5.6388671510e-11i | 2.0385669961e-10 → 1.7314830095e-10，改善 |
| V14_v11 cells 360/446，列 1 | 3.8808378733e-10 − 2.6239362072e-10i | 1.0614042978e-10 − 1.9691000219e-10i | 4.6846498074e-10 → 2.2369474691e-10，改善 |
| V14_v8 cells 23352/23493，列 0 | 4.0017766878e-11 + 7.7761797002e-11i | −1.0004441720e-10 − 2.7284841053e-12i | 8.7454666764e-11 → 1.0008161688e-10，退化 1.2626950116e-11 |
| V14_v8 cells 23352/23493，列 1 | −1.3398282483e-10 + 2.4693602718e-10i | 6.9743988362e-11 + 2.5019319949e-11i | 2.8094269677e-10 → 7.4095818259e-11，改善 |

旧 V14_v8 的列 0 final d 退化是实际独立 checker 的否决项。虽然它在 j0/j3 两个标签下重复出现，底层是同一 RHS，只是一项退化，不是两项。

## 3. 主 star 的有符号分解与剩余误差

对 V17 主 star 的两列，t=0 是本次读取并核对的保存事实，因此 S·t 项为 0；不能把此简化套到另外两个 star。分解显示候选主要改变 J 求值项，local/native 与固定 z 项没有改变：

| 列 | D_local/native | D_fixed solve | D_J evaluation：原 BLAS → V18 fsum |
|---:|---|---|---|
| 0 | 2.7547004972e-10 − 4.0738840592e-11i | 8.8815522703e-11 + 4.4136582225e-11i | 4.6699258500e-10 + 1.2063668297e-11i → −9.5826387267e-12 − 1.5787522295e-12i |
| 1 | 2.3831640960e-10 + 5.5094009943e-10i | 5.9372627613e-13 + 1.7763104541e-10i | −3.7002312081e-11 + 9.3398517000e-10i → 1.2110401814e-11 − 1.9165277453e-11i |

本次保存报告中的 epsilon_B_RHS 为 0；独立 checker 将本次重放的 scatter/末次相减 Decimal 余项记录为 `0E-39`（数值为 0）。但同一 cell 的独立 native rank-1 贡献和原 scatter 顺序/舍入来源证据仍标为 NOT_SAVED。V18 显著减小了本候选的 Jz 求值误差，但未消除乘积及求和误差，不足以说明 native/local 余差已经解释。精确缺项是 cells 7873/8014、同一已知输入和原 kernel/积分/坐标下的独立 native rank-1 局部项及原 scatter 顺序核算，用于区分存储 J/z 与 native RHS/组装/散射差异；V18 没有新增该积分或作用。

## 4. 窗口、资源、来源和失败历史

- 固定 V18 window SHA-256：3d4158d70782f9789a997ecadac073f9ea2e7be104dc789e66c0758d45aee113；authorization SHA-256：ab05005def1d1222f3189549d315a6b78a13efb77e807b7c9a15c329e51f2c0c；contract SHA-256：fca6cb2ad0c6d8591b1087cff50ff0d11e8bcb025b82cd5fdea17b83bb12f380。
- 固定 T0 `2026-10-29T00:50:15.000000000Z`；数值截止 `2026-10-29T06:30:15.000000000Z`，总截止 `2026-10-29T06:50:15.000000000Z`；总计21,600 s（数值20,400 s，收口1,200 s）。没有重置或延长 T0。service结束快照为序号60、累计1,266.601198 s。主控文档收口于2026-10-29T01:38:22.994122585Z追加序号61，累计2,887.994186 s（含准备、失败修复、等待及截至采样的文档成本）；该时点总/数值余额分别18,712.005814 / 17,512.005814 s。此后本地文档核验及Git发布不包含在此快照，不作为完整冷流程测量。余额不构成下一范围授权；本包在 mixed 结果后停止，没有再执行候选。
- attempt02 官方 service `myfenics-case-20261029T011017-3693849.service` / invocation `26fda6e33e864af2bcd4ff2a0e85eda6` 以 exit 0 完成。campaign service-entry 到最后 watchdog-end 的父段为62.540324 s；systemd 报CPU 71.259 s。嵌套 worker watchdog 5.924485 s、checker watchdog 55.059161 s，二者属于父服务内部阶段，不与父段或彼此重复累加。
- 16次普通BLAS Jz合计0.003146933 s，16次V18 `fsum`核心合计1.291472651 s；本批约410.4倍耗时（仅为16个保存输入的聚合计时之比）。输入hash/load及完整J提取0.656927743 s，receipt load/hash 0.051307218 s，replay S action hash/load 0.009106160 s，production-order scatter 0.204321304 s，candidate数组/报告保存0.023218051 s，replay报告保存0.001317012 s（来自写出后的worker stdout；保存JSON中的预写入0不代表实测零成本）。该候选显著慢于BLAS，不外推全域。
- worker 和 checker 分阶段进程树 RSS 峰值分别326,643,712 B、263,819,264 B；同一 service cgroup 峰值207,638,528 B；task swap 两阶段均0 B，PSS 按profile未采样，两个 watchdog 均报告后代已清场。不同RSS/cgroup口径分列，不相加。
- 计划工作集722,276,872 B，小于4 GiB；attempt02 当前 invocation 证据树13,671,489 B，小于16 MiB；累计 raw 为15,603,033,504 B；加上V17旧窗口保守目录77,977,883 B与本次新输出13,671,489 B，保守总量15,694,682,876 B，小于16 GiB；工作站可用磁盘1,975,435,960,320 B，高于2 GiB底线。worker核验98个唯一绑定 raw 文件，共75,190,216 B；这些数字按 service receipt 各自口径记录，不将来源库存、输出树与进程内存混加。
- frozen source `ff22c0a78099e7e48e0c11127ce01e06ae1ac8cf`，分支 `task41extra_phi90_p50x50_g17x20`；工作站 native ABI 为 PETSc 3.25.6 complex128/int32、SLEPc 3.25.2、DOLFINx 0.10.0、MPI1/MPICH 5.0.1。window、auth、contract、source、原始三个 star 的 producer/hash均保留。
- 前三次启动失败均发生在候选 worker 前，未产生数值输出：attempt01 第一次遇到 contract 变量未绑定（UnboundLocalError；source 880fea，systemd记录CPU4.129 s）；第二次因 V14 refinement strategy 常量缺失（NameError；source 5784dc，CPU6.252 s）；第三次因 attempt01.service 已存在而 FileExistsError（source ff22，CPU6.139 s，保留空的既存目录）。wrapper日志和错误哈希见 [attempt index](outcomes/v18_closeout/attempt_index.json)。没有删除或覆盖这些痕迹。attempt02切换到全新的输出路径后成功完成。

## 5. 下一步边界与证据入口

V18候选不获支持；本包不追加运行。下一项若要查明仍缺的数值来源，应先另行定义和批准只针对上述同 cell native rank-1/scatter 的窄证据，不自动切换至全域 owner、200q、完整参考、target、FGMRES、A6 或官方 R/T/A。旧 V17/V14 结果、所有失败启动、原输出数据和固定账本均保留。

- [V18 compact](outcomes/v18_closeout/v18_saved_jz_compact.json)：科学量与状态的紧凑摘要。
- [V18 evidence index](outcomes/v18_closeout/evidence_index.json)：忽略目录产物的路径、大小、hash和旧输入引用；大型 checker JSON 不复制入Git。
- [V18 attempt index](outcomes/v18_closeout/attempt_index.json)：三次失败与一次完成的service/成本记录。
- [V18 resource compact](outcomes/v18_closeout/resource_compact.json) 与 [窗口快照](outcomes/v18_closeout/window_snapshot.json)：资源、窗口和余额口径。
- [结果总表](outcomes/summary.md)、[运行索引](outcomes/run_index.json)、[测试摘要](outcomes/test_summary.md)。

执行者未自行 commit/push。科学源码已由主控冻结并推送；本结果文档由主控集中提交，完整远端交付HEAD在最终回执给出。原全域action两列仍为5.7625744836e-11、1.2123684644e-10，均超过1e-11；本轮没有重算或改判。
