# Task39extra 最终报告：双层单元凝聚路线、实测成本与继承边界

> 状态：**CLOSED_WITH_QUALIFICATIONS（笔记本研究阶段收口）**。这不是整个0.7 nm项目完成，也不是批准把研究分支整体合入master。

## 1. 给其他任务先读的结论

**当前建议采用：p6/p4双层装配时单元凝聚＋p6 trace/端口空间FGMRES＋BAL_H＋准确p4凝聚MUMPS因子。**最终解始终属于p6；p4只提供纠错。保留快速A6融合、快速完整A4验算、blocked Gram局部矩阵生成、正确的H6对角与自然序作用，以及低扰动RSS监督。

这条路线是本任务中速度、内存与可靠性较平衡的实用方案。不是“内存绝对最少”：同网格p3粗层曾将整树峰值降到约4.03 GB，但耗时约117.77分钟。不是“已经证明最快”：V29是分项和同离散对照较完整的速度基线，V31是最新完整求解的推荐继承实现，V31补跑没有完成受控端到端性能对照。两者都应保留，不能拼接各轮最好分项制造不存在的结果。[E1–E5]

| 选择 | 适用目标 | 实测依据及限制 |
|---|---|---|
| **V31准确p4双凝聚，推荐继承实现** | 在已覆盖的几何/材料/环境内兼顾速度和内存，供新任务开发 | 126步；worker workflow 2313.526 s；RSS 7.331 GB；原A6和功率一致性通过。完整参考E/H对照及部分运行时身份仍有缺口 |
| **V29准确p4双凝聚，冻结比较基线** | 性能分账、同离散完整场比较和回归分母 | workflow 2422.426 s、setup 533.755 s、pure KSP 1837.175 s；126步；RSS 7.326 GB |
| **历史p3双凝聚，内存优先备选** | 内存不足以承担p4，而能够接受更多迭代 | 361步、7065.949 s、RSS 4.032 GB；采用较早内核，不是最新V31下的p3性能 |
| p2、42宏块Schur、旧低内存弱逆、BLR及未采用内核 | 历史研究证据 | 不作为推荐生产路径；不能从特定负结果推出所有类似方法不可能 |

时间均为各记录注明的monotonic口径；RSS统一十进制GB。V31的2313.526 s是记录为worker workflow的字段，V29的2422.426 s为父流程workflow，不能将二者直接当严格配对计算收益百分比。

## 2. 收口身份、权限和未消除的blocker

```text
repository              = Rookie1234567/MyFEniCS
closed_execution_branch = task39extra
reviewed_HEAD           = e09bd1612c4f6ca5fb5cf3572835748ad5c16207
latest_response         = response_v33.md
latest_execution_review = review_report_v29.md
latest_formal_source    = d9b545e824296fce1b489c32a5d96e5e9303ff3c
V29_reference_source    = 780f58918b0e5a9868cd2ea3de26d451bc6b5d86
closeout_date           = 2026-09-29
ordinary_default_change = NOT_APPROVED
master_merge            = NOT_APPROVED
workstation_migration   = NOT_EXECUTED_BY_THIS_CLOSEOUT
```

用户本轮明确要求：先将笔记本Task39extra收口，留下其他任务可直接阅读的最终报告，再以该路线建立新的Task40extra分支。本报告接受**固定离散问题求解与输出一致性的阶段性成果**，停止本分支常规性能试验；新研究在新任务中开展。不改写旧task、review、失败、误停、账本和`NOT_ATTEMPTED`。

已消除的障碍：本机高阶全场求解的部分无效存储、重复局部积分/系数转换、凝聚恢复与粗精化的不一致，以及重型PSS诊断的可避免调用。未消除的障碍：全局p4因子随规模增长、短波长的总迭代工作、一般几何下的独立单元缓存、高通道端口库存、完整离散误差资格和分布式实现。

## 3. 物理与离散身份

本任务最终主要比较模型为真空波长13.5 nm、grazing 1°、azimuth 0°、s偏振、Si/air、x/y双Floquet周期、z方向Fourier-DtN、complex128 Nédélec H(curl)。`p6/h7.5`中的7.5 nm是网格目标尺寸，不是波长。最终原始模型有990个六面体单元、80个有序端口通道。[E1,E2]

体积及边界弱式离散得到：

```math
A_6x_6=b_6,\qquad A_6=K_{\mathrm{curl},6}-k_0^2M_{\epsilon,6}+T_{\mathrm{DtN},6}.
```

完整p6存储坐标667152，独立trace加端口199340；p4完整存储坐标201520，凝聚trace加端口84680。完整存储坐标包含受约束位置，不能当作全部独立未知量。[E2]

已成功的非可分挑战包括历史notch h10案例：材料分布同时随x/y/z变化，146步、RSS约2.298 GB，原A6和匹配参考检查通过。它属于该次notch离散和源码，**不代表V31已经重新验证所有非可分几何**。当前快速内核/凝聚资格主要覆盖轴对齐仿射六面体、已支持的单元材料和约束；曲面、一般畸变、各向异性和单元内变系数不能默认为已通过。[E6]

## 4. 双层凝聚具体做了什么

### 4.1 同一消元思想，两层不同的全局求解方式

将内部自由度记为i，保留trace/端口坐标记为R：

```math
\begin{bmatrix}A_{ii}&A_{iR}\\A_{Ri}&A_{RR}\end{bmatrix}
\begin{bmatrix}x_i\\y\end{bmatrix}
=\begin{bmatrix}f_i\\f_R\end{bmatrix},
\qquad
S=A_{RR}-A_{Ri}A_{ii}^{-1}A_{iR},
\qquad
\widetilde f_R=f_R-A_{Ri}A_{ii}^{-1}f_i.
```

实际用局部LU和回代实现内部消元，不要求保存显式逆。先组合完整curl/mass物理矩阵，再凝聚；不能分别凝聚两项后相减。

| 层 | 单元矩阵/分块 | 全局组织 |
|---|---|---|
| p4 | 300维，内部108，trace192 | **装配时直接形成全局凝聚稀疏矩阵，并做一次MUMPS LU** |
| p6 | 882维，内部450，trace432 | **不物化全局p6 Schur矩阵，不做p6全局LU**；由局部凝聚数据执行全局作用 |

不是先装完整大矩阵再从中提取Schur，也不是42个宏块的另一种叫法。相同合格类型的局部数据共享；方向、MPC、端口与原始几何身份仍须正确处理。局部块可以稠密，全局p4仍为稀疏矩阵；凝聚不保证对每种图都降低全局factor内存。[E6,E7]

### 4.2 为什么这个组合有效

p6凝聚减少了FGMRES的全局坐标数和搜索向量长度；p4凝聚减少了准确粗解的全局输入规模。它们不改变恢复后的原p6方程，但会改变迭代坐标和实际PC组织，不能保证任何案例迭代次数都相同。

历史h10对照中，从完整p6外层到p6凝聚外层，外层向量173802降至51272，564步降至112步；随后生命周期版本在同一h10原始案例达到约2.832 GB。该历史结果证明这条组合值得继承，不是所有波长/网格的普遍加速定理。[E6]

## 5. 三大阶段与公式

### 5.1 Setup：只建立一次，因子留给全部迭代使用

```text
输入/材料/网格/空间/约束/通道
→ 必要form编译及参考数据
→ p4局部物理矩阵与单元凝聚、全局稀疏装配
→ p4 symbolic/numeric，保留同一份因子及依赖矩阵
→ H6正确对角、规定power10和作用对象
→ p6局部凝聚、恢复数据、trace/端口桥接
→ 同对象启动核验，直接进入KSP
```

优先在大因子常驻前编译后续确实需要的form，避免JIT与大工作集叠峰；这是调度建议，**本次未新增cold-JIT重排试验**。缓存复用须身份合格；不能预热后漏记成本。

### 5.2 KSP：FGMRES外层，BAL_H只负责给方向

粗修正定义为：

```math
C_4=P_{64}F_4P_{64}^{H},\qquad F_4g_4\approx A_4^{-1}g_4.
```

F4实际包括限制后的RHS缩减、已有凝聚LU的前代/回代、内部恢复、完整原A4验算和按需精化。每次RHS不同，但因子不重建。

```math
e_4=g_4-A_4c_4,\qquad
c_4\leftarrow c_4+F_4e_4.
```

原A4目标1e-10，每次初解及每次精化后都完整检查；最多两次额外同因子精化。仍未达内部目标但状态有限且完整时，返回已验算的最佳一致状态（FE、端口、A4作用、残差来自同一attempt），继续外层。NaN/Inf、因子或映射损坏仍停止。该软返回不降低最终原A6标准。

一次BAL_H：

```math
z_c=C_4r,\qquad s=H_6(r-A_6z_c),\qquad
z=z_c+s-C_4A_6s,
\qquad
M_6=C_4+(I-C_4A_6)H_6(I-A_6C_4).
```

即两次粗修正、两次A6作用、一次H6。H6是正定辅助问题的短Chebyshev-Jacobi作用，不是准确A6逆，也没有几百步内层Krylov。FGMRES32随后进行Schur作用、正交化和小最小二乘，最终组合搜索方向；不能把PC公式当成外层全部工作。[E1,E2,E8]

### 5.3 恢复/后处理：先保留最小场，再释放无用求解对象

```math
x_i=A_{ii}^{-1}(f_i-A_{iR}y),\qquad
\rho_6=\lVert b_6-A_6x_6\rVert/\lVert b_6\rVert\le10^{-6}.
```

恢复完整p6场、原A6独立终检、释放因子再释放依赖矩阵、释放后复核、正式E/H及模式/功率/体吸收输出。因子不能在仍需C4时提前销毁；也不能在因子存活时擅自删除后端依赖的p4矩阵。

## 6. 可复用的时间账：以V29同一完整场为准

V31补跑未提供同样边界的全部子项，因此下表统一使用V29，不拼入其他轮次更好的数字。单位秒，全部为E2中的实测；父子包含项不可重复相加。

| 大阶段/动作 | 本场时间 | 解释 |
|---|---:|---|
| **完整workflow** | **2422.426** | 40.37分钟；父流程monotonic |
| **setup总计** | **533.755** | 8.90分钟 |
| p4接口栈准备 | 250.099 | 包含局部凝聚与factor |
| 其中p4 symbolic / numeric | 0.637 / 216.394 | 一次分解，不是每次PC成本 |
| p4局部矩阵/凝聚/装配 | 26.588 | 12个raw类，26个定向类 |
| p6局部builder | 34.122 | 包含raw kernel 20.289和局部Schur 11.552 |
| H6对角 / power10 | 4.799 / 39.087 | V29旧合格对角；不是V31的新对角时间 |
| 其余空间/端口/JIT/bridge/QA | 未完整独立计时 | 不把父区间差额随意归因 |
| **pure KSP** | **1837.175** | 30.62分钟、126步 |
| A6累计作用 | 517.156 / 263次 | 每次约1.966；含相应检查调用 |
| H6累计作用 | 525.036 / 131次 | 每次约4.008；与B6子项不相加 |
| p4缩减—回代—恢复 | 243.563 / 267次 | 每次约0.912；复用同一因子 |
| 完整原A4验算 | 159.091 / 267次 | 每次约0.596；不是LU回代 |
| P / PH累计 | 77.895 / 69.326 | 不同计数含准备/检查，非126的简单倍数 |
| 最终native检查 / 释放检查 / 正式物理输出 | 5.751 / 11.461 / 15.164 | 未将其余阶段间差额假定为后处理 |

### 各轮不能混淆的结果

| 版本 | 完整时间记录 | 迭代 | RSS GB | 裁决 |
|---|---:|---:|---:|---|
| V25 p4 r2 | 3114.284 s，51.90 min | 126 | 约7.391 | 早期准确p4速度锚点 |
| V28 A6融合 | 2936.076 s，48.93 min | 126 | 7.356 | 融合有效；完整回归通过 |
| V29 A4及局部矩阵加速 | 2422.426 s，40.37 min | 126 | 7.326 | 冻结速度/全场对照基线 |
| V30监控与新H6对角 | 2532.759 s，42.21 min | 126 | 8.044 | 数值通过；未获整场性能改善 |
| V31首次 | 中断，不列完整用时 | 日志113、完整检查112 | 7.324（仅前缀） | Codex误停；不是资源或solver失败 |
| V31授权补跑 | worker 2313.526 s，38.56 min；保守结算2534.117 s | 126 | 7.331 | 固定离散求解/输出通过；不是受控性能配对 |
| V25 p3备选 | 7065.949 s，117.77 min | 361 | 4.032 | 更低内存但更慢，较早源码 |

E1–E5、E8提供运行身份和原始路径。时间受不同scope、缓存和运行状态影响；本报告不对混合分母给严格加速比。

## 7. 内存主要放在哪里

以V29对象记录说明数量级；后端allocated/used、数组载荷和整树RSS不是可直接相加的同口径账。

| 对象 | 记录/推导量级 | 属性 |
|---|---:|---|
| MUMPS内部used / allocated | 约4.327 / 4.688 GB | 后端统计，并非同时刻单独因子RSS；不相加 |
| p4凝聚矩阵分配载荷 | 历史同规模约0.908 GB | 矩阵本身仍保留，不是因子的一部分 |
| p6局部数值缓存 | 325.283 MB | V29载荷；按合格类型共享 |
| p4局部数值缓存 | 24.542 MB | V29载荷 |
| p6完整 / trace单向量 | 10.674 / 3.189 MB | 维数乘complex128的16 B，derived |
| FGMRES32主要两组trace向量 | 约207.3 MB | 约65条向量的载荷，不含全部工作区 |
| H6类8条主要向量 | 约85.4 MB | 派生载荷，不是H6总RSS |
| 网格/映射/端口/其他向量、库与分配器 | 未精确逐项闭合 | 不把RSS减used的差額叫作Python或泄漏 |
| V29 / V31完整整树RSS峰值 | 7.326 / 7.331 GB | 两场各自完整采样峰值 |

V30的峰值比V29高717742080 B，已有峰值样本对上：FFCx/gcc/cc1后代719687680 B，数值worker差-1912832 B，parent/launcher差-32768 B，合计恰为差额。这解释的是**两次峰值时刻的进程组成**，不是全部生命周期逐对象账。编译必须计入，不能从正式峰值中删除。[E9]

## 8. 任务过程与最后保留的技术

| 研究阶段 | 结论与保留 | 不允许的误读 |
|---|---|---|
| 物理p4中间层、shift/多层/弱逆试验 | 准确p4对完整纠错非常有用；低内存候选未成为通用强逆 | 不表示所有迭代逆不存在；不继续盲扫ILU |
| 42宏块Schur与BLR等 | 自由度下降不保证因子或总内存下降 | 不把“Schur”三个字等同省内存 |
| p4装配时单元凝聚 | 对局部内部DoF就地消元，避免完整全局矩阵后凝聚 | 不是旧宏块库存方案 |
| p6进一步凝聚 | 外层trace向量变短，h10上迭代显著减少 | 改变表示后不能保证所有案例步数相同 |
| 类型共享、identity与生命周期 | 复用正确局部对象，避免重复序列化和叠峰 | 不能假设任意几何仍只有几种局部类型 |
| h10 notch及h7.5原始模型 | 获得有限三维/网格范围的资格 | 不称所有几何、所有波长鲁棒 |
| p3/p2粗阶对比 | p3是低内存备选，p4是当前速度优先 | 未重测的最新p3速度不能填写 |
| A6融合、A4快速完整验算、blocked Gram | 保留；不减少物理积分和检查 | 不能把单组件倍数乘整个workflow |
| reference-metric H6对角、低扰动RSS | 保留为显式工程实现；heavy阶段PSS可关闭 | PSS=null不是0；RSS监督仍需完整 |
| H6自然序 | 组件有6.24%/18.05%中位改善，补跑完整求解通过 | 固定matmul增量无稳定收益，不采用 |
| 局部多列批处理、端口流式小试 | 保留负结果；不进入速度优先默认 | 小fixture不足以否定全部大规模策略 |

详细过程不在本报告重新复制全部review，沿E6、E7、E10和原review链追溯。

## 9. 继承实现、输入和验证入口

| 依赖组 | 阅读入口 | 继承要求 |
|---|---|---|
| 正式输入/调用 | `scripts/run_case.py`、`src/io/physical_intermediate_profile.py` | 一个dat对应一次明确计算；新任务另建显式profile |
| 双凝聚与恢复 | `src/runners/physical_dual_cell_condensed_lowmem_v20.py`、`src/solvers/hcurl_assembly_time_condensation.py` | 不复制大型runner；最小参数化通用路径 |
| A6/A4/B6快速作用 | `src/solvers/fullspace_n1e_sum_factor.py`、`src/solvers/fullspace_partial_assembly.py` | 保留各项积分规则、复材料、方向与MPC身份 |
| H6/准备 | `src/solvers/physical_light_setup.py` | 正确约束对角、power10、H6-only自然序 |
| 准确p4与BAL_H接线 | `src/runners/physical_p4_schur_v14.py`及其已绑定依赖 | 完整A4检查/最佳一致状态返回；原因子与矩阵生命周期不变 |
| 检查器 | `benchmarks/task39extra_v25_dynamic_checker.py`、`benchmarks/task39extra_v31_output_checker.py` | 用实际schema；旧PASS/FAIL原样保存；新任务避免硬编码旧run_id |
| 已有输入示例 | `input/task39extra/v31_projection_layout_original_h7p5.dat` | 仅示例；不得直接把波长改成0.7而保留旧材料和通道 |

上表是e09bd161快照中的入口索引，不是授权整体合并研究分支。跨分支/环境需按数值核心、输入/监督、checker和证据分组迁移，验证实际ABI与原Aq关系；不能只抄若干函数名。[E1,E8]

## 10. 尚存证据限制及不重跑的收口办法

V31补跑的独立原A6/功率/体吸收检查通过，但完整FE L2、scaled-curl、同坐标E/H与V29/V30的离线对照本场未执行；部分线程环境字段缺失。新任务第一步可以只读已有artifact补比对，并记录可恢复的旧身份；缺失则写unknown，不用当前shell反填，不为补账重跑Task39extra。

本次阶段收口接受以上限制并明确移交，不把它们变成“没有最终结果”，也不把它们改写成“全部PASS”。只有同离散对照补齐后，才能声明对应源码之间的完整场等价；连续误差仍需要独立h/p资格。

历史`USER_CONTROLLED_STOP`为Codex执行误停，不是用户要求停，也不是算法负结果。8 GiB或旧7.326 GB成绩不是当前硬线；每场必须把资源规则、口径、实际系统/cgroup额度和比较目标分别记清，保留系统余量与清场保护。

## 11. 为什么不能直接放大到0.7 nm、2 TB

工作站冻结快照2026-09-28、分支`task39extra_para_workstation_capacity@ccd357885f7f9be84efe3be07868cc94f13d93fc`：2 nm/h1.5已有双凝聚；p4因子4586288行、MUMPS used约916.713 GB；p6端口相关数组库存约106.341 GB；前缀RSS峰约1154.356 GB；64步独立A6残差0.0223587，尚非最终资格。它尚未包含笔记本全部后续加速，既不是本机结果，也不是当前实时进度。[E11]

固定几何、固定阶次且假设h与波长同比缩小时，2/0.7的立方约23.32，只能用作情景计数，不能替代精度合格网格。全局p4因子增长不能线性外推；局部缓存也不能忽略：450×450 complex128内部LU每独立单元约3.24 MB，若约127万单元全部独立，仅此数值载荷约4.1 TB。该极端情景不是当前实测，但说明类型共享不能成为任意几何的唯一容量保障。

后续必要主线：真实0.7 nm材料和非可分缩小PDE → h/p与通道误差资格 → 多尺度电尺寸成本 → 有界局部求解、多层全局纠错、分布式trace/mode与有界缓存。准确p4留作小中规模reference/过渡；最终生产候选不能依赖覆盖全域的无限增长直接因子。Hybrid只在内部可模态传播时作为加速器，不替代一般Full3D。

## 12. 正式收口裁决

| 事项 | 裁决 |
|---|---|
| Task39extra笔记本阶段 | **CLOSED_WITH_QUALIFICATIONS / pass_with_qualifications** |
| 推荐路线 | **准确p4双层装配时凝聚＋matrix-free p6 trace外层＋BAL_H＋合格快速内核** |
| 低内存备选 | 历史p3双凝聚，时间代价明确，最新内核复用需再资格化 |
| 继续旧分支常规PDE/调参 | 不新增；用户明确再授权的资料补充另记 |
| 研究继续 | 新Task40extra分支，以本次收口提交为base |
| master/default/工作站迁移 | 未批准；不改变当前工作站运行 |
| 0.7 nm目标规模通过 | **未建立**；不以本报告或新分支名称代替实测 |

## 13. 证据索引（固定于reviewed_HEAD，除E11）

- E1：[Response V33](response_v33.md)；[补跑机器记录](outcomes/records/projection_layout_v31_authorized_rerun.json)。
- E2：[V29完整compact](outcomes/records/a4_tensor_h6_v29_compact.json)；[Response V30](response_v30.md)。
- E3：[V30完整compact](outcomes/records/workstation_guided_local_v30_compact.json)；[Response V31](response_v31.md)。
- E4：[V31组件与选择](outcomes/records/projection_layout_v31_selection.json)；[首次误停compact](outcomes/records/projection_layout_v31_compact.json)。
- E5：[历史p3完整记录](outcomes/records/a6_h6_coarse_degree_v25_q3.json)；[r2完整记录](outcomes/records/v25_q4_ac_swap_observe_r2_result.json)。
- E6：[全阶段summary](outcomes/summary.md)；[双凝聚h10](outcomes/dual_condensed_memory_v20.md)；[非可分验证](outcomes/dual_condensed_robustness_v21.md)。
- E7：[Review V18](review_report_v18.md)、[V19](review_report_v19.md)、[V20](review_report_v20.md)。
- E8：[最后执行Review V29](review_report_v29.md)；[V31补跑授权](outcomes/records/v31_user_authorized_completion_rerun_20260929.json)。
- E9：[V30资源重审](outcomes/records/projection_layout_v31_resource_reaudit.json)。
- E10：[历史经验](prior_attempts_retrospective.md)；[文献与方法边界](literature_review.md)。
- E11：[工作站冻结交接](https://github.com/Rookie1234567/MyFEniCS/blob/ccd357885f7f9be84efe3be07868cc94f13d93fc/docs/task39extra_para_workstation_capacity/outcomes/f2_running_handoff_20260928.md)。

本报告由ChatGPT基于远程只读证据编写；未在本会话重放PDE、完整场数组或性能测试。文档结构检查与远程回读另随交付记录，未完成的视觉/数值检查不得声称通过。
