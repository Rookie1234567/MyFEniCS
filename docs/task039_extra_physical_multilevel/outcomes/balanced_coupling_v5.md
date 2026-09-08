# Task39extra V5：粗细耦合平衡完整验证

| 结论 | 证据及边界 |
|---|---|
| 原始与唯一 notch | BAL_H 从零初值完整求解；full explicit true residual≤1e-6；匹配离散参考与独立物理 Gate 通过 |
| 资源 | 两次迭代和原始恢复 global swap Δ=0；条件参考 sampled tree swap=0，但 global pswpout 增加448页，归因 UNRESOLVED |
| 时限 | 原始 solve6102.614s、含恢复workflow6997.531s，分别小于7200/10800s |
| 范围 | 13.5nm、p6/h10、Full3D、MPI1、线程1、80模式；没有p/h/M/MPI扫描或Hybrid比较 |
| 未运行 | BAL_S、PROJ_K6 heavy：not_run_goal_met；没有第四路线 |
| 交付状态 | E5 docs/compact随本次提交交付；最终HEAD/同步状态见任务末Git回报；等待集中review，无merge approval |

## 模型、方法与判定

原始模型为13.5nm、1°掠入射、方位0°的s偏振电磁散射。唯一notch在相同252单元网格上实际改变8个材料单元，形成y/z不可分材料分布，用于检查方法是否依赖原始几何的可分性。两者均有173802存储自由度、164592独立自由度。参考是同一离散方程的高精度解，不能称连续真解或网格收敛。

粗层修正C把细网格残差投影到p4空间求解，再送回p6空间，写作 `C=P A4^-1 PH`。细层平滑可以消除局部误差，但也会重新破坏粗层已满足的方程；BAL_H在细层平滑后再减去C作用于其方程响应的反馈，以恢复粗细平衡。收益是解决旧真实难误差的耦合失衡；代价是每次外层修正需要两次p4求解，仍依赖全局LU及其内存。BAL_S使用已资格化的另一细层平滑；PROJ_K6在保持粗方程约束的空间中做最多六步内层迭代，需要更多向量和算子作用。三者均为研究路径，未提升为production default。

FGMRES用连续外层迭代组合这些修正，restart32、max2048。成功以重新计算原始完整方程的 `||b-Ax||/||b||≤1e-6` 为准，不能用内部估计或单次修正效果代替。R/T是反射/透射功率除以入射功率，A=1−R−T；A_volume由材料内部耗散独立积分，是能量一致性的另一检查。

## 统一正式结果

| 模型 | 迭代 | 完整真残差 | R | T | A | A_volume |
|---|---|---|---|---|---|---|
| 原始 | 564 | 9.93228922e-07 | 0.365625791 | 0.0129906323 | 0.621383577 | 0.621383575 |
| 非可分缺口 | 576 | 9.35170552e-07 | 0.337120585 | 0.0162886742 | 0.646590741 | 0.646590748 |

| 模型 | R00_s | R00_p | R00_total | L2相对参考差 | scaled curl相对差 | 80复振幅相对差 |
|---|---|---|---|---|---|---|
| 原始 | 0.365589113 | 4.5889126e-25 | 0.365589113 | 1.36698742e-08 | 4.35333721e-09 | 4.23335991e-09 |
| 非可分缺口 | 0.337079617 | 6.43835225e-27 | 0.337079617 | 1.39878303e-08 | 9.48441599e-09 | 1.00161454e-08 |

零级反射分别列出两个偏振及其和。L2衡量整个场的差异，scaled curl衡量按既定尺度归一化的场旋度差异。80个边界复振幅保留相位，比较未做相位拟合；全部模式原值在[compact记录](records/balanced_coupling_v5.json)中。模式功率最大绝对差原始1.853892706e-9、notch4.458047653e-9，均小于1e-6；复振幅限值1e-4、总量差限值1e-5均通过。独立体耗散差原始2.078905936e-9、notch7.680656222e-9。

| 模型 | 衍射级(m,n) | R（双偏振和） | T（双偏振和） |
|---|---|---|---|
| 原始 | (0,0) | 0.365589113 | 0.0129597438 |
| 原始 | (-1,0) | 3.08944303e-05 | 2.42113455e-05 |
| 原始 | (-2,0) | 2.53864249e-06 | 3.66365438e-06 |
| 原始 | (-4,0) | 5.04239925e-07 | 7.59998182e-07 |
| 原始 | (-5,0) | 5.31659544e-07 | 3.40953013e-07 |
| 原始 | (-7,0) | 2.19402325e-06 | 1.89811753e-06 |
| 非可分缺口 | (0,0) | 0.337079617 | 0.0162544259 |
| 非可分缺口 | (-1,0) | 2.53606369e-05 | 1.99929807e-05 |
| 非可分缺口 | (-2,0) | 2.7472985e-06 | 6.21459278e-06 |
| 非可分缺口 | (-4,0) | 4.10843819e-07 | 6.32646358e-07 |
| 非可分缺口 | (-5,0) | 4.23930023e-07 | 3.1080297e-07 |
| 非可分缺口 | (-7,0) | 3.53186894e-06 | 1.76172242e-06 |

## E1有限作用与反馈

E1对三份真实难误差、旧已知误差和range输入各测试三种修正，共15次完整PC。表内L2/curl是修正后与输入场范数之比；真残差比是单次作用的方程残差比，不是完整求解判定。真实输入的真残差比仍可大于1（约4.75–26.17），与场误差下降不矛盾；不能把E1误写为PDE通过。coarse balance相对量限值1e-8。

| 输入/路线 | L2比 | curl比 | 真残差比 | 粗平衡 | C次数 | 耗时s | 内层状态 |
|---|---|---|---|---|---|---|---|
| A2R160/BAL_H | 0.387035993 | 0.387481465 | 10.8154285 | 4.44185611e-11 | 2 | 16.378475 | BALANCED_ACTION_COMPLETED |
| A2R160/BAL_S | 0.350888378 | 0.351284454 | 9.88097188 | 4.53810341e-11 | 2 | 19.1468889 | BALANCED_ACTION_COMPLETED |
| A2R160/PROJ_K6 | 0.150749384 | 0.15108564 | 4.75188151 | 4.98857485e-11 | 4 | 35.2959718 | INNER_TARGET_REACHED |
| LIGHT448/BAL_H | 0.382173998 | 0.382623672 | 22.653392 | 5.83713197e-11 | 2 | 15.7060584 | BALANCED_ACTION_COMPLETED |
| LIGHT448/BAL_S | 0.346393726 | 0.346793117 | 20.7988289 | 6.03446421e-11 | 2 | 18.937631 | BALANCED_ACTION_COMPLETED |
| LIGHT448/PROJ_K6 | 0.14295302 | 0.143262407 | 10.4166224 | 6.4973261e-11 | 4 | 35.137116 | INNER_TARGET_REACHED |
| JOINT448/BAL_H | 0.379978542 | 0.380407158 | 26.1700243 | 5.42052652e-11 | 2 | 15.8437803 | BALANCED_ACTION_COMPLETED |
| JOINT448/BAL_S | 0.344347666 | 0.344726988 | 23.9211179 | 5.69169068e-11 | 2 | 18.5174739 | BALANCED_ACTION_COMPLETED |
| JOINT448/PROJ_K6 | 0.143537415 | 0.143846237 | 12.0991131 | 6.28540571e-11 | 4 | 35.4110666 | INNER_TARGET_REACHED |
| V4_KNOWN/BAL_H | 0.0826823738 | 0.102662606 | 0.218956424 | 3.61981032e-13 | 2 | 16.0086361 | BALANCED_ACTION_COMPLETED |
| V4_KNOWN/BAL_S | 0.0806877407 | 0.0865729679 | 0.158236734 | 3.61964428e-13 | 2 | 18.5195279 | BALANCED_ACTION_COMPLETED |
| V4_KNOWN/PROJ_K6 | 0.0756849678 | 0.0583780047 | 0.117876756 | 3.61158401e-13 | 7 | 62.7588223 | INNER_TARGET_NOT_REACHED |
| RANGE/BAL_H | 2.86965589e-12 | 2.86665623e-12 | 2.04546655e-12 | 2.19099914e-12 | 2 | 16.3833496 | BALANCED_ACTION_COMPLETED |
| RANGE/BAL_S | 3.00987103e-12 | 3.00637356e-12 | 2.00197342e-12 | 2.19105585e-12 | 2 | 19.1929943 | BALANCED_ACTION_COMPLETED |
| RANGE/PROJ_K6 | 3.48564367e-12 | 3.48078076e-12 | 1.79253199e-12 | 2.1900448e-12 | 7 | 65.637096 | INNER_TARGET_NOT_REACHED |

反馈范数表是实现记录的系数向量范数，不能直接当成上表有限元场范数。结构A作用用于构建修正，inner true用于独立检查内层残差；它们与外层matvec分开计数。

| 输入/路线 | 反馈前/后系数范数 | 反馈范数 | 结构A/内层真A | 内层步数 | 新增细向量峰值/清理后 |
|---|---|---|---|---|---|
| A2R160/BAL_H | 226.428369/255.236736 | 37.1132538 | 2/0 | 0 | 6/0 |
| A2R160/BAL_S | 226.166334/266.935717 | 51.6689422 | 2/0 | 0 | 6/0 |
| A2R160/PROJ_K6 | 不适用 | 不适用 | 7/3 | 3 | 13/0 |
| LIGHT448/BAL_H | 470.242179/529.917526 | 76.8306926 | 2/0 | 0 | 6/0 |
| LIGHT448/BAL_S | 469.727244/553.8885 | 106.689873 | 2/0 | 0 | 6/0 |
| LIGHT448/PROJ_K6 | 不适用 | 不适用 | 7/3 | 3 | 13/0 |
| JOINT448/BAL_H | 547.639297/615.654383 | 88.3898941 | 2/0 | 0 | 6/0 |
| JOINT448/BAL_S | 547.04685/642.945573 | 122.701712 | 2/0 | 0 | 6/0 |
| JOINT448/PROJ_K6 | 不适用 | 不适用 | 7/3 | 3 | 13/0 |
| V4_KNOWN/BAL_H | 1.09088694/1.09048904 | 0.00755316804 | 2/0 | 0 | 6/0 |
| V4_KNOWN/BAL_S | 1.08849477/1.08961635 | 0.00731683238 | 2/0 | 0 | 6/0 |
| V4_KNOWN/PROJ_K6 | 不适用 | 不适用 | 13/6 | 6 | 19/0 |
| RANGE/BAL_H | 6.59768278/6.59768278 | 2.85418577e-12 | 2/0 | 0 | 6/0 |
| RANGE/BAL_S | 6.59768278/6.59768278 | 4.01201991e-12 | 2/0 | 0 | 6/0 |
| RANGE/PROJ_K6 | 不适用 | 不适用 | 13/6 | 6 | 19/0 |

E1共46个逻辑p4 RHS、46次MatSolve、零精化，最大native p4残差6.556902930e-11。PROJ真实误差用3步，已知/range用6步；有限步未达到内层目标保留其原始状态，不判作完整求解失败。全部rank、奇异值、逐步真残差及range identity已保留compact。E1峰值3571789824 B、耗时1138.473406s，不能与其他阶段峰值相加。

## 完整求解成本与生命周期

| 模型 | solve保守/monotonic s | 外层matvec/PC | C/MatSolve | native p4最大残差 | 新增细向量峰值/释放后 | p4 factor NNZ |
|---|---|---|---|---|---|---|
| 原始 | 6102.61428/5593.68926 | 581/564 | 1128/1128 | 6.06063264e-11 | 6/0 | 53417584 |
| 非可分缺口 | 6261.47113/5684.97689 | 593/576 | 1152/1152 | 6.67971566e-11 | 6/0 | 53417584 |

p4包含53084 FE行和80端口行，增广53164行；notch矩阵分配NNZ24730144。两次完整求解各只有一个KSP、一次solve和一次destroy，零初值；原始128步screen通过后沿同一KSP继续，notch无screen。两者p4精化次数均0。

| 模型 | 阶段边界（包含跨度） | monotonic s | 保守计时器差 s |
|---|---|---|---|
| 原始 | workflow_started→solve_started | 667.726223 | 729.340847 |
| 原始 | solve_started→release_started | 5593.71114 | 6102.61446 |
| 原始 | release_started→recovery_started | 0.225389546 | 0.22538843 |
| 非可分缺口 | workflow_started→solve_started | 671.999563 | 733.577416 |
| 非可分缺口 | solve_started→release_started | 5685.00628 | 6261.47075 |
| 非可分缺口 | release_started→recovery_started | 0.331393412 | 0.331392677 |
| 非可分缺口 | recovery_started→checker_started | 48.1621715 | 55.3582111 |
| 非可分缺口 | checker_started→complete_started | 4.99656868 | 4.99657088 |

| 模型 | PC中C s | PC中平滑 s | PC中结构A s | 内层真A s |
|---|---|---|---|---|
| 原始 | 1811.89272 | 1232.98019 | 1507.58057 | 0 |
| 非可分缺口 | 1844.0518 | 1244.06269 | 1535.09587 | 0 |

这些操作时间是嵌套的monotonic测量，不再叠加到工作流预算。保守时钟保留UTC与monotonic差异，使用更保守口径；不能用较短monotonic替换正式时限。

正式PC成本按各次pc_applies标量账本求和如下；外层matvec不包含PC内部结构A、PH审计或H6内部positive矩阵作用，外层显式残差A也单列。H6调用由每次PC的smoother次数求和；smoother_facts.apply_count是累计计数，不能再求和，matrix_mult_count则是每调用增量。

| 模型 | PC结构A | PH审计 | H6调用 | H6内部positive matmult | PC内层真A | 外层matvec | 外层explicit A |
|---|---|---|---|---|---|---|---|
| 原始 | 1128 | 1128 | 564 | 1128 | 0 | 581 | 72 |
| 非可分缺口 | 1152 | 1152 | 576 | 1152 | 0 | 593 | 73 |

## 资源、参考与原始负结果

| 阶段/口径 | 样本 | RSS峰值 B | 最低系统可用 B | 采样swap B | global swap out页 |
|---|---|---|---|---|---|
| 原始全进程树 | 24023 | 3466235904 | 9440563200 | 0 | 0 |
| 原始恢复全树 | 418 | 1749610496 | 11181752320 | 0 | 0 |
| notch全树 | 24407 | 3600924672 | 9376018432 | 0 | 0 |
| 条件参考子树（不含等待祖先） | 2109 | 7189639168 | 5625581568 | 0 | 448 |
| 条件参考中途开始的补充全树 | 1150 | 7231651840 | 5651398656 | 0 | 同一参考窗口，不能重复计数 |

所有采样的系统可用内存均超过4GiB，未观察到进程树VmSwap；参考补充全树距启动动态上限最小979685376 B。参考子树有245个warning样本，均可读；补充采样没有warning字段，不能记为0。补充之前以子树峰值4399329280 B加等待父进程历史VmHWM37466112 B得到4436795392 B，这是派生上界，不是同步实测峰值。补充采样从中途开始，不能声称覆盖整个参考窗口。全部已知父/子/采样进程已退出。

**条件参考全系统pswpout增加448页，pswpin增加0，job swap attribution为UNRESOLVED_global_activity_cannot_be_attributed。** 采样进程树swap=0不能排除采样间活动，也不能归因全系统活动。参考数值/物理通过与此资源限制分别报告；不得写整个campaign全系统swap0，也不将其伪装为OOM或数值失败。未取得2GB内存资格。

原始worker在已经完成564步后以WORKER_FAILED退出：`Top diffraction probe z=110 nm must be above the block top z=120 nm.` 原top110/bottom10输出平面不合法。审阅后的恢复仅将外部输出探针设为127.5/−7.5nm，内部参考平面不变，使用同一564步solution-only checkpoint；原始A作用和RHS差精确为0，没有重解原始PDE，也没有新PC/KSP/factor。原始raw失败和241个绑定文件保持不变。恢复耗时119.384361s。

notch原checker的BALANCED_OUTPUT_AUTHORITY_LIMITED保持原样；后续条件参考赋予MATCHED_REFERENCE_PASS，不能倒改原记录。条件参考native完整残差1.702800154e-11≤1e-10，一次symbolic/一次numeric、两次solve、一次固定修正，factor在编译/输出前释放。最终reference_summary有权威，早期reference_numeric快照不是终态。参考子进程630.050543s已包含于父阶段651.747857s，不重复收费。

## 预算与证据身份

| 预算项 | 状态 | 计入秒数 |
|---|---|---|
| policy_reserve | RESERVED_POLICY_NOT_MEASURED | 600 |
| E1 | COMPLETED | 1138.47341 |
| E2_targeted_tests | COMPLETED | 5.77885064 |
| original | WORKER_FAILED | 6878.14671 |
| E2_recovery_focused_validation | COMPLETED | 6.08050594 |
| E2_recovery_final_review_tests | COMPLETED | 1.51911977 |
| E2_recovery_chain_review_tests | COMPLETED | 1.89791035 |
| original_recovery | COMPLETED | 119.384361 |
| notch | worker_exit0 | 7058.74236 |
| notch_reference | COMPLETED | 651.747857 |
| E2_E4_terminal_audit | COMPLETED | 48.2169961 |

累计计入16509.988080s，43200s总预算剩余26690.011920s；其中600s是非measured政策预留，覆盖未单独计时的轻量准备与主线程只读审阅，不虚构精确耗时。原始含恢复6997.531075s，notch工作流7058.742359s。文档整理与等待不冒作formal PDE。

| 身份 | 完整SHA |
|---|---|
| base | 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee |
| E1 | c4e86cfe1e6ba88ca5d26df82942e82f190e7eda |
| 原始求解 | 2bb6770ad00b35881558c576e7296e250656e571 |
| 恢复/notch/参考 | 094204b7281fe867744fe334e8753d2faebaf89b |

物理模型hash、模式hash、原始命令/环境入口、所有80模式、残差曲线、操作计数和生命周期见compact及其绑定raw索引。Linux资格化complex128/int32 ABI、MPI1/线程1；没有CI声明。

| 证据 | SHA256 |
|---|---|
| `benchmarks/artifacts/task39extra/v5_balanced/balanced_chain_terminal.json` | 1377a03e63e13f2f1506719a683bf65a2884a68cd9e47668ee8d4e73dbdc1c34 |
| `benchmarks/artifacts/task39extra/v5_balanced/balanced_chain_raw_index.json` | be9c1e8651639b3fa95d28cbaaf515bf427292bfa48d3bda6d46a6eeef93020f |
| `benchmarks/artifacts/task39extra/v5_balanced/recovery_chain_review_tests.json` | f3c32acf3f63bac24d2cec6123fe94898830a97b8203563fac3428939e6a34a4 |
| `benchmarks/artifacts/task39extra/v5_balanced/recovery_review.json` | c0875a0a765b2a73081cbd2c60e5370b6fc02acd94e61513c3bdb6ccc3c5245e |
| `benchmarks/artifacts/task39extra/v5_balanced/recovery_commit.json` | 96428a04f9162dc0395052ed72263f45e7135ccae85def8d398808b836dfe5a4 |

主线程独立核对raw_index全部637文件通过；本E5只检查索引绑定及文档，不重复全面raw hash。原始/E1历史独立审计继续保留。

## Selective merge依赖组与唯一下一对象

| 组/顺序 | 内容及数值影响 | 依赖/验证/建议 |
|---|---|---|
| production numerical/core（1） | `src/solvers/physical_balanced_coupling.py`、`physical_balanced_runtime.py`、`physical_balanced_fgmres.py`；改变PC行为 | 依赖既有p4/H6；E1与两个fresh完整anchor；仅研究opt-in，不设生产默认 |
| reusable runner/watchdog（2） | `src/runners/physical_balanced_budget.py`、`physical_balanced_controls.py`、`physical_balanced_recovery.py`、`physical_balanced_output.py`；预算/恢复 | 依赖核心；47项既有本地测试及实际退出/恢复证据 |
| checker/benchmark（3） | `benchmarks/physical_intermediate_checker.py`；`src/test/test_375_balanced_coupling.py`、`test_376_balanced_public.py`、`test_377_balanced_recovery.py` | 依赖输出约定；两模型80模式与完整残差验证 |
| compact evidence/docs（4） | 本次8文件收口，无数值行为改变 | 依赖已绑定raw；最小JSON/hash/link/history/diff检查 |
| research-only | BAL_S/PROJ_K6有限作用、负结果 | 保留E1；没有heavy资格，后续审阅决定 |
| do-not-merge | ignored mesh/field/factor/raw大型artifact | 只保留hash及路径；无master合并授权 |

唯一下一对象是以有界内存或分布式物理近似C替代全局p4 LU，同时保持本次实测的粗细平衡。近似误差应依据耦合放大、原方程完整真残差、场范数与80复振幅共同校准，并计入内存和算子成本。当前仅提出对象，没有实施第四路线；不宣称0.7nm稳健、连续收敛或生产2GB资格。

下一轮严格只替换C接口，沿冻结难误差及本次two-model anchor检验粗细平衡、完整A残差、场范数及80通道。旧57–59倍是特定样本的耦合放大，不是全局条件数或容差定理。当前p4 factor NNZ53417584乘complex128的16字节，数值载荷下界854681344 B（约0.855 GB），这不是RSS，还需A4矩阵、索引和工作区。不能把现有全局LU直接扩容到5/0.7nm；扩大前须取消不受控全局存储，并提交总live-set及每调用工作上界。此处只提出方案和账本要求，没有实现第四路线，也不推断波长鲁棒性。
