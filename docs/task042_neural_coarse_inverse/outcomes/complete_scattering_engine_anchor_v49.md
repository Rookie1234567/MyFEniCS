# V49：完整有限散射执行链、同离散资格和离散精度负结果

| 工作包 | 实际完成 | 结论与边界 |
|---|---|---|
| P0 | 冻结物理输入；最小文件级复用公开数值闭包；八个真实 one-run 入口 | 不依赖不可取的旧运行 SHA 或旧 ignored 科学包 |
| P1 | REGULAR/NOTCH 各一次完整 p4 直接参考，真实入射、内部恢复、双周期和全部 532 端口 | 两例原方程、恢复及能量通过 |
| P2 | 两例独立零初值、全部四 q 的结构利用引擎 | 1/3 次外迭代；与同 p4 参考完整观测量吻合 |
| P3 | 独立未凝聚原体作用、全部 DtN、E/H/curl、selected 场、532 复通道及功率 | 两例 COMPLETE_FINITE_EQUATION_PASS / FINITE_OBSERVABLE_PASS |
| P4 | NOTCH 唯一同网格 p5 直接参考和独立审核；完整费用与生命周期 | p4/p5 差异大，P_INCREMENT_CHECK 已运行但精度未收敛 |
| 最终目标 | 本轮没有训练 NN，也未构造原尺寸模型 | TARGET_NOT_QUALIFIED；NN_NOT_TRAINED_THIS_BATCH；NN20 未证明 |

本轮回应[Review V47](../review_report_v47.md)。有限元把连续电磁场写成边、面和单元内的系数；本轮把物理输入真正接到原三维 Maxwell 方程、开放边界、求解、恢复和独立输出审核。它补齐神经研究所需的完整传统基线，而不是把小矩阵接口通过冒充完整计算，也不是本轮授权之外的新网络训练。

## 1. 物理、材料与源码身份

| 描述 | 本轮冻结值 |
|---|---|
| family / 输入 | V49_COMPLETE_SCATTERING_ENGINE_ANCHOR；[八入口及共同配置](../../../input/task042_neural_coarse_inverse/scattering_anchor_v49.json) |
| 波长与材料 | 0.7 nm；[canonical 用户表](../../../input/materials/si_optical_constants_v1.json)，SHA256 `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2` |
| 复数约定 | exp(−iωt)，Si n=0.999885140474+4.32477054e−6i；epsilon=n*n=0.9997702941220071+8.648547597811433e−6i；air n=1、mu=1 |
| 尺度 | s=7/135；x=s×(0,16.5,25,33.5,50)，y=s×(0,6.25,12.5,18.75,25)，z=s×(−10,0,40,80,120,130)，单位 nm |
| 入射 | grazing 1° / azimuth 5° / s / 幅值 1；真实背景散射 RHS，不是制造 RHS |
| REGULAR 标签 | air/substrate/Si block=40/16/24 cell |
| NOTCH 标签 | 42/16/22；只将原 Si 的两个 cell 改为空气，未沿 y 复制缺口 |
| 缺口实际 native cell | 38/52；中心 (1.5166666667,0.4861111111,3.1111111111)、(1.5166666667,0.8101851852,3.1111111111) nm |
| p4 | 80 hex；native17204 / 独立15872 / trace7232 / 内部8640 / 端口532 / 凝聚7764 行 |
| p5 | 同 80 hex；native32865 / 独立30800 / trace11600 / 内部19200 / 端口532 / 凝聚12132 行 |
| 求积 | 原 UFL 自动体求积；surface p4=23 / p5=25，来自发布公式；不是旧 p6/q15 |
| 完整 DtN | manual m=−9..9、n=−3..3，top/bottom×s/p；266+266=532；mode SHA `9206da3bcf687c4cbf9dbfad48a22456f4a75f5cf3c537331fcdf71a9f79b5a2` |
| 环境 | NN-Lab 资格 activation；本地 complex128 PETSc 3.19.6/int64、DOLFINx/Basix 0.10；MPI1、数学1、GPU0、Loader0 |

原材料标签 `0.699999988` 只通过明确 alias 对应 nominal `0.7`，原值不插值、不联网替换。Si 结构、基底、背景和下端口一致。[实际几何与每 case 身份](records/physical_identity_bindings_v49.json)绑定 cell 中心、标签、网格和科学数组成员；[最初物理库存](records/physical_cases_v49.json)保留。

只读 donor 为 `task40extra_dot_parallel_cloud@3f4fb69b20d33d382975bb96db73b44bba583ebd`。[迁移清单](records/engine_source_manifest_v49.json)逐定义绑定文件 blob/hash、理由和本地去向；[实际运行源码](records/source_bindings_v49.json)另核对 1009 组提交×文件字节。没有整体 merge/cherry-pick、从邻任务工作树 import 或修改 dot。历史 `3570347` 不可取，未重建或伪称本次源逐字等同其历史资格源。

| 实际阶段 | clean 运行源码 SHA |
|---|---|
| p4 两直接参考 | `e184c386a7187bd39d485de369071cb80badea55` |
| p4 两结构引擎与独立 VERIFY | `5a21673150dc3cc2b282e6f9f0f319722b51d128` |
| p5 直接参考 | `1bbcffc14ede9e11742e6ad6db89339c6f793923` |
| 最终 p5 原作用审核、跨 p 与费用 | `06d4fe2c40d40c301b9566d6fa4ba198a31ff468` |
| compact checker / 元数据收集 | `81d5f7057efea3c4c22fef43afaec67c55ade323`；最终文档 HEAD 另报 |

早期 e184 manifest 的 physical hash 表示两 case 总库存，并非单 case descriptor；新绑定分别为 REGULAR `7c0e9e5c073faf9fc5bec6fc57e8372d9c86bc40d4457ed784409089f6e2e2fd`、NOTCH `6b6963869d274b4f779626a11b93636a2a4257dd2b2990aa4f59b2686f97ad52`。独立 VERIFY 实际配对了几何、标签、模式、背景和 RHS；旧 manifest 原样保留。这是身份字段勘误，不追溯制造新的 clean 运行。

## 2. 实际方法与独立性

直接参考先在每个单元内消去内部系数，只把共享 trace 和端口交给小规模全局直接分解，再按原局部关系恢复内部场。这称为装配时凝聚；减少全局行数，代价是局部 LU、恢复缓存和有限全局因子。本轮允许精确参考，**FINITE_AUTHORITY_EXACT_FACTOR_PRESENT**，不是重开生产 p4 强逆。实际后端 MUMPS；固定参考 SuperLU/COLAMD 后备未使用；参考精化次数为 0。

结构利用引擎对规则背景使用全部四个离散 y 分支的精确参考逆，作为原完整三维问题的预条件。缺口时外层仍作用真实非可分原算子，跨 q 耦合保留。两例各在新进程从零独立准备，没有读取 P1 场、旧网络/Q/teacher/Krylov 或另一例的因子。外层沿发布实现 FGMRES restart32/max128，实际只需 1/3 步；**ALL4Q_EXACT_FACTORS_PRESENT**，不能称 factor-free。

参考与引擎共享物理弱式、材料和端口规范，属于同离散比较，不是独立软件真解。独立 VERIFY 重新用原未凝聚体作用和完整 C/D/H 检查，并从原 oriented cell tensor 检查内部恢复；没有拿模态分支自身残差自证。P5 用原未凝聚 UFL 作用的内部/trace 分解复核非零内部 RHS，无新因子或参考回传。

先保存原解向量和端口，再审核/派生 JSON。直接参考释放全局 KSP/PC/factor、凝聚矩阵后才输出完整 E/H；必要原作用与局部恢复缓存保留，随后销毁。引擎也先保存合法返回向量，释放四 q 因子后输出；[对象出生/释放记录](records/object_lifetimes_v49.json)区分可见 unique-owner 字节与 opaque PETSc/MPI/LAPACK 工作区，后者 unknown 且纳入采样 RSS，不能把可见数组相加当全过程峰。

## 3. 完整原方程与同 p4 场资格

所有 residual 都重新作用原方程；true/native/增广/端口不能相互替代。严格门为候选各≤1e−6、直接参考内部目标≤1e−10；恢复和恒等式按运算尺度≤1e−10、slave 原零存储规则。[完整标量与独立判定](records/finite_independent_checks_v49.json)不信任保存的 status。

| case / 方法 | true/native | 增广 | 端口 | 恢复聚合 / 最坏 cell | 恒等式 | slave |
|---|---|---|---|---|---|---|
| REGULAR direct p4 | 1.776046e−12 | 1.504653e−12 | 9.976038e−14 | 1.240663e−15 / 3.630378e−15 | 1.531306e−16 | 0 |
| NOTCH direct p4 | 1.567842e−12 | 1.327057e−12 | 1.231510e−13 | 1.230449e−15 / 3.233772e−15 | 1.419294e−16 | 0 |
| REGULAR all4q p4 | 9.112582e−13 | 9.112582e−13 | 4.098042e−18 | 1.331125e−15 / 3.386078e−15 | 5.302356e−17 | 0 |
| NOTCH all4q p4 | 8.038623e−12 | 8.038623e−12 | 1.307517e−16 | 7.123906e−14 / 2.272838e−12 | 5.027489e−17 | 0 |
| NOTCH direct p5 | 2.575903e−12 | 1.838730e−12 | 2.429159e−14 | 1.333833e−15 / 2.132160e−15 | 1.293041e−16 | 0 |

P5 内部+trace 原作用恒等式误差 7.250595e−16，内部 RHS 范数 9.412139e−14，未把特解强置零。[完整科学结果](records/complete_physical_results_v49.json)与[大数组路径/hash](records/array_inventory_v49.json)保存全部原始量；表格舍入仅用于阅读，checker 用全精度。

| 引擎对同 p4 直接参考 | 六类 E/H/curl 最大相对差 | selected 最大差 | 全 outgoing 复向量差 | 参考面复向量差 | 最大单 mode 功率差 | 最大 R/T/A/A_volume 差 |
|---|---|---|---|---|---|---|
| REGULAR | 2.021704e−12 | 1.501024e−12 | 1.739140e−12 | 7.553749e−14 | 1.221245e−15 | 2.139348e−15 |
| NOTCH | 8.052334e−12 | 5.874444e−12 | 3.610349e−12 | 2.607673e−13 | 6.550316e−15 | 6.562676e−15 |
| Gate | 1e−4 | 1e−4 | 1e−4 | 1e−4 | 1e−6 | 1e−5 |

六类为 total/scattered E、H、scaled-curl，真实 FE 积分与原 selected 复数样本都保存。近零使用预登记 floor1e−12 的混合范数；不校相位、不缩放候选。全部 532 aliases 的键、侧、极化、参考面、规范、原复振幅和逐级功率在输出文件与 NPZ 中保留，不只比较传播波或零级。evanescent 辅助幅度可很大，完整向量相对范数与实际参考面幅度分列，不能用巨大未归一化绝对数直接替代 Gate。

H_code=curl(E)/(i*k0*mu)，物理 A/m 再乘 1/eta0；本文功率沿原 code-unit Poynting 规范，体吸收用 Im(epsilon) 而非 Im(n)。top outgoing=a−incident_projection，bottom outgoing=a；下侧损耗相位按真实边界参考面计算，无守恒再归一化。

| 完整输出 | R_total | T_total | A=1−R−T | A_volume | 能量闭合误差 | R00_s | R00_p |
|---|---|---|---|---|---|---|---|
| REGULAR direct p4 | .998869472979 | .00112940303834 | 1.12398294425e−6 | 1.11974396050e−6 | −4.23898371960e−9 | .997695910037 | 9.29226738245e−6 |
| NOTCH direct p4 | .998869476620 | .00112942906850 | 1.09431163852e−6 | 1.09007199611e−6 | −4.23962931428e−9 | .997695958203 | 9.29228700777e−6 |
| REGULAR all4q p4 | 同参考至约2.2e−15 | 同参考 | 同参考 | 同参考 | −4.23898161017e−9 | 同参考 | 同参考 |
| NOTCH all4q p4 | .998869476620 | .00112942906850 | 1.09431163195e−6 | 1.09007199611e−6 | −4.23963586460e−9 | .997695958203 | 9.29228700776e−6 |
| NOTCH direct p5 | .999797452210 | .000171151460236 | 3.13963300935e−5 | 3.13912969322e−5 | −5.03316122114e−9 | .999617831366 | 9.23011641960e−6 |

这里 R00_total=R00_s+R00_p，不混写成含糊的 R(0,0)。两例 p4 同离散完整资格成立；p5 也通过自身代数/恢复/能量门，但这都不能证明真实连续场已算准。

## 4. 唯一 p5 精度对照：真实负结果

P5 先按 12132 凝聚行及矩阵/因子/工作区重叠规划入场；精确预测 6.886467456817627 GiB，实际树采样峰 1,840,844,800B。早先 commentary 的约6.3GiB近似不准确，容量记录未更改。[p 增量记录](records/p_increment_v49.json)包含原参考 hash、新 p5 身份和独立审核数组。

| 同 NOTCH、同80网格 p4→p5 | 实际差 | 解释 |
|---|---|---|
| total E / H / scaled-curl | 2.953190 / 2.814719 / 2.814719 | 场明显不稳定，不能宣称离散收敛 |
| scattered E / H / scaled-curl | .1930444 / .2878606 / .2878606 | 每 p 减去其各自 FE 插值背景，含背景表示差；不混当同背景误差 |
| selected total E/H | 2.719729 / 2.958932 | 独立固定点也存在大差 |
| R / T 绝对差 | 9.279756e−4 / 9.582776e−4 | 能量闭合好不代表衍射/透射精度好 |
| A / A_volume 绝对差 | 3.030202e−5 / 3.030122e−5 | 吸收预测有实质变化 |
| 全 outgoing / 参考面复向量 | 1.806806 / .1957796 | 完整模式亦未稳定 |
| 最大单 mode 功率差 | .001921873 | 远大于同离散比较门1e−6 |

跨 p 表并非用候选 Gate 强行判另一 p 失败；它说明一次增阶已经暴露明显离散误差。小代数残差和小能量闭合不能替代网格/阶数/532截断资格。粗 mesh 表示、背景相消和具体物理分量的原因仍未被分离，不宣布唯一根因，不追加第三个 p 或网格扫描。

## 5. 完整冷费用、峰值与失败账

冷N=1定义为新数值进程从实际物理输入准备，不共享上一 case 的数值因子；保留 OS/JIT cache 的命中，不能称清空系统 cache。启动计时从真实 run_case 数值 launcher 起，早于它的 activation/输入解析少量开销 unknown，因此以下为实测完整数值链下界，而不是精确 shell-to-end 全部费用。[冷成本](records/cold_n1_costs_v49.json)把完整准备、求解、恢复、输出、IO/清理及非重复计时逐项保存。

| 路线 | 数值启动至结束下界(s) | 受监督(s) | 树采样峰(B) | 局部/全局因子 | 外步 |
|---|---|---|---|---|---|
| REGULAR direct p4 | 118.672806 | 115.592872 | 852762624 | 29 class LU + 有限 MUMPS1 | direct1 |
| NOTCH direct p4 | 71.547987 | 68.893252 | 814084096 | 30 class LU + 有限 MUMPS1 | direct1 |
| REGULAR all4q p4 | 137.522063 | 134.793253 | 754126848 | 两40-cell载体各20 class LU + 四 q 因子 | FGMRES1 |
| NOTCH all4q p4 | 138.235644 | 135.488804 | 775528448 | 同规格，从新进程独立准备 | FGMRES3 |
| NOTCH direct p5 | 463.065159 | 460.144354 | 1840844800 | 30 class LU + 有限 MUMPS1 | direct1 |

| 排名显著阶段(s，exclusive 不重复累计) | REGULAR direct | NOTCH direct | REGULAR all4q | NOTCH all4q | NOTCH p5 |
|---|---|---|---|---|---|
| 原 JIT/tensor/C/D/H | 22.833945 | 2.914305 | 约2.9 | 2.878257 | 49.576496 |
| 凝聚/局部因子 | 73.159850 | 58.943557 | 111.689554 | 111.226533 | 367.391714 |
| 有限全局直接 factor | 1.804367 | 1.828856 | 无完整80-cell factor | 无完整80-cell factor | 6.580433 |
| 直接 solve+最小恢复 / 外 FGMRES | .091695 | .165462 | .757209 | 1.668252 | .328463 |
| 完整 E/H/curl | 6.344988 | .302149 | 约.3 | .308629 | 16.681569 |
| 532模式/功率/吸收 | 2.966626 | .352876 | 约.17 | .171966 | 5.831886 |

精确全部阶段以 JSON 为准。不同列 cache 和宿主负载不一致，performance 为 shared-workstation / INCONCLUSIVE；不能用准备冷的参考和 cache 命中的引擎推导无争用加速。新结构利用的全过程时间反而更长，较低采样峰也不足20%（约11.6%/4.7%），且不是神经收益。

额外独立 P4 VERIFY 受监督1683.875600s，包含320次 oriented 原 cell tensor 恢复审核；COST 成功98.553537s，失败 COST15.063485s 全计费。不能把旧审核时间相减冒充新的快算法。原完整 A 计数按 journal 保存，volume-only 调用有未独立计数项，不能补造0；`calls.factor` 是因子作用次数，不是新因子构建数。早期 launcher 新factor/volume的0为占位，不是真实零；实际因子库存以上表、事件和新勘误为准。

最终总有载、probe、修复/失败、测试、Git/IO下界/unknown和全部原始版本见[最终资源费用](records/resource_costs_final_v49.json)、[修复 journal](records/repair_journal_v49.jsonl)、[raw 索引](records/raw_archive_index_v49.json)及[settlement补档](records/post_settlement_archive_v49.json)。旧研究已知下界88875.68891642192s继续累计，历史未知成本保留 unknown，不归零。本轮全部 elapsed 在首次02:22:52.968771 UTC冻结的7h窗口内；数值截止08:37:52.968771，交付截止09:22:52.968771 UTC，不刷新。

真实 CPU 逐阶段选空闲物理核避忙 SMT，MPI1/math1/自身swap0。采样整树 hard16/warn12GiB，计划≤8GiB，独立watchdog/自有锁/低优先级/缓存；没有可写 cgroup，不能声称连续内核硬限制。0.5s是配置频率，实际全样本最大间隔与峰值在最终费用记录，不能拿旧快照代替最终集合。宿主其他任务的可比阶段指标不可得；没有观察到准入或持续压力触线，但不能宣称绝对零干扰。未修改邻任务或全机配置。

## 6. 最多一个后续学习对象与明确未运行项

可考虑的独立对象仅为：由部署物理输入预测完整 FE+DtN 场系数，跳过实际占主耗时的凝聚/因子，再经原独立审核和必要校正。它不同于已关闭的固定A小误差修正、删trace或codec；不是现在自动启动训练。最强传统控制必须包括精确几何/tensor/cache共享，当前共享优化改善量未实测。

```math
T_B=C+V,\qquad fV-H\ge0.2T_B,\qquad 0\le f\le1.
```

| 必要机会（乐观，不是已实现） | REGULAR | NOTCH |
|---|---|---|
| 只删末端factor+solve占完整下界 | 1.598% | 2.787% |
| 因而 warm-start/便宜尾部逆在 H=0 时 | 也达不到20% | 也达不到20% |
| 连凝聚一起完全替代的 V(s) | 75.055912 | 60.937874 |
| 所有冷data/teacher/训练/推理/额外纠错 H 上限(s) | 51.321350 | 46.628277 |
| 同 case 完整teacher下界(s) | 118.672806 | 71.547987 |
| 仅teacher已超过 H 允许量 | 是 | 是 |
| 相对最佳观察到的非NN树峰所需 NN 上限(B) | 603301478.4 | 620422758.4 |

费用界使用已观察到较快直接传统路线；峰值界另用较低树峰的结构路线，不混成一个不存在的基线。teacher/训练/model/activations/额外审核新同时峰 unknown；满足算术必要界远不是 NN20资格。[机会决策](records/opportunity_decision_v49.json)保留 unknown 和 load/cache 不可比限制。

唯一下一建议：围绕这一完整物理基线集中审阅 p4/p5 大差及准备成本剖面，先确定代表性准确离散与最强精确共享控制，再决定上述唯一学习对象是否还有可核算20%空间。不安排 tail-only NN，不自动扩大模型或再做小组件轮次。

| 未运行项 | 原因 |
|---|---|
| 新网络/旧codec训练、旧固定A微调 | 本合同未授权；历史关闭保持 |
| 原尺寸32060通道、2TB/48h计算 | 有限模型不授目标资格，本轮未授权 |
| 第三 p、网格/截断/PC参数扫描 | 单次 p5 已完成，预算和范围禁止扩展 |
| 参考 SuperLU/COLAMD fallback | MUMPS 有效，无须触发 |
| 直接参考额外精化 | 内部原残差已≤1e−10；固定最多2次不是必须使用 |
| GPU/重装ABI/其他分支/merge | 禁止；subagents、重置卡均未使用 |

## 7. 测试、证据与交付

最终 targeted 17项 pure/复数/非互伴40端口/全532映射/原恢复/实际入口/独立checker测试通过；编译、Ruff致命规则、八dat的真实schema/stage验证和自有deadline后代清场试验通过。[测试](records/tests_v49.json)保留全部失败与最终source。最终15项文档合同、表格/链接/fenced公式、旧导航尾部不改及实际交付字节 hash见[文档检查](records/documentation_checks_v49.json)。本地通过不是CI；精确GitHub Review页 Cache miss，没有视觉证据，NOT_VERIFIED。

[run index](records/run_index_v49.json) · [交付索引](records/delivery_index_v49.json) · [源清单](records/engine_source_manifest_v49.json) · [实际源码](records/source_bindings_v49.json) · [changed files/selective merge](records/changed_files_v49.json)。大场/矩阵/日志在ignored artifact，紧凑记录入Git。数值核在src/solvers，普通默认不变；有限研究资格不升级production。原task/review/response/raw和全部失败保留，base不变，只push指定分支，最终closed、active null、清场/释放锁后一次原队列交回并停止。
