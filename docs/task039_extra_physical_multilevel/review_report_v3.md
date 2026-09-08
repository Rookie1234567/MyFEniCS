# Task39extra Review V3：跨方法的难误差档案与不收敛原因定位

## 0. 身份、裁决与本轮要消除的 blocker

```text
repository          = Rookie1234567/MyFEniCS
branch              = task39extra
review_date         = 2026-09-08
reviewed_HEAD       = 67c2e6c7954bca5d32cee465fc581921d02b358b
formal_F3_source    = 60b8df2a24cbcd96e49e018be22fb64f06eeae3f
original_task_base  = 2dc2e7305f10dc391a13970c6f0f0340cb87b6ee
previous_documents = review_report_v2.md / response_v3.md
new_work            = CROSS_METHOD_FAILURE_DIAGNOSIS
execution           = D0 -> D1 -> conditional D2 -> D3 -> conditional D4 -> D5
response_required   = response_v4.md
new_PC_full_solve   = NOT_AUTHORIZED
master_merge        = NOT_APPROVED
```

**本轮消除的是“没有分清难误差、表示空间、修正作用和实现成本，因而反复凭方法名称选择 PC”的 blocker。不是再优化 S6，也不是已经认定 p4 色散或子域人工反射为唯一原因。**

最终目标仍为约 2 TB 整机内存内，0.7 nm、complex128、Nedelec H(curl)、双 Floquet、Fourier-DtN、周期单胞内任意非可分三维结构。此次仅在约 16 GB 本机的原始 13.5 nm 模型上作有界诊断，不运行 5 nm/0.7 nm，也不把准二维或可分离模型替代最终问题。

接受 Response V3 对历史负结果的限定解释；原始完整求解仍未资格化。本轮用户明确同意将下一步改为原因定位，因此在同一分支授权下述连续诊断批次。V2 的新 PC 搜索停止决定保持：不续跑旧 F3，不调权重、restart、p5、shift，不重开 PML/Robin/GenEO/75D，不将静态凝聚重新设为生产 fine-space 主线。未授权 merge 或新分支。

ChatGPT 本次核对了远程任务、review、response、outcomes、紧凑记录及已有相关实现信息，没有重跑 PDE 或读取全部 ignored raw。Codex 必须从原始文件独立复算本轮诊断。任务书和旧 review 的 blob 未改变；本文件只补充新范围，不改写其历史 Gate。

## 1. 最新结果的准确含义

来源为 [Response V3](response_v3.md)、[中心报告](outcomes/packed_and_joint_mr_v2.md) 和 [紧凑记录](outcomes/records/packed_and_joint_mr_v2.json)。下表均为历史 measured/derived；s 为秒，B 为十进制字节。

| 对象 | 已发生的结果 | 本轮如何使用 |
|---|---|---|
| 完整 S6 packing | 配对中位比 0.938459 > 0.75；作用等价、速度不足 | 关闭继续 packing 调优，不再补一个版本 |
| F3 联合 LIGHT | 476 次完整 PC；最终原 A6 相对残差 0.10535820013809101 > 1e-6 | 原始问题未算通，不外推一天后必收敛 |
| p4 参考逆 | 476 次，原 A4 残差最大 7.870604378195616e-11 | 当前有限尺寸的内层准确性已成立 |
| 联合选权 | 476 次 rank3、fallback0；joint/seq 残差比中位 0.9794794387 | 局部约 2.05% 收益，不等于完整外层更快 |
| 同第 448 步 | F3 0.107133269005；旧 LIGHT 0.098145911603 | 未形成一致的外层改善；各自 Krylov 输入不同 |
| 完整 PC | 中位 11.460344589 s；extra A6 累计 694.874210 s，QR 累计 5.928539 s | 时间账与修正效果分开，不继续优化小 QR |
| RSS / swap | 采样峰 3351887872 B，cap 8525078528 B；swap0、清场完成 | 此次不是内存触顶；不能把整体 RSS 当 p4 factor 大小 |
| 停止分类 | 用户要求停止；worker CONTROLLED_STOP，wrapper WORKER_FAILED/exit4 | 保留 raw 与派生分类；不是自动停滞或 7200s Gate 触发 |
| 时间限制 | workflow monotonic 7588.369777 s / UTC 8363.831318 s | 相差 775.461541 s，不能宣称全部 wall 预算通过或可靠速度比例 |
| solve 到请求 | monotonic 6791.466003 s / UTC 7478.995420 s | UTC 区间超过 7200s；原因未唯一确定 |
| 场与后续结构 | official E/H、R/T/A、体吸收、非可分挑战未运行 | 未收敛场只能作诊断；不提升为物理资格 |

本次结果削弱了“只要重新组合这三个方向就够了”的假设，但没有证明 p4 全空间完全无用、所有多层/子域法无效，或矩阵根本无解。完整三列独立与包含全部难误差不是一回事。

## 2. 不是只诊断 S6-p4-S6：三个层次的可复用性

通俗地说，先保存“哪些误差难以消除”的共同样本，再问每种 PC 如何处理这些样本。换一种 PC 不需要重建全部物理档案，但必须检查它自己的新作用，不能把旧结论自动当作新方法的原因。

| 层次 | 要回答的问题 | 换方法时的复用规则 |
|---|---|---|
| 问题层 A、b、空间与数据 | 真实误差/残差在哪里，涉及何种空间尺度、材料界面、端口和传播分支；计量是否可信 | 同一离散问题可复用，不重复建立参考和基础映射 |
| 表示/机制层 | 粗空间是否表达得了；实际粗修正是否接近其能力；细层剩余误差是否可处理；投影是否稳定 | 相同空间/算子结论可继承，新空间只补相应检查 |
| 具体 PC/实现层 | 局部逆精度、顺序/权重、子域接口、重叠、restart 与成本 | 新方法必须补查，但不重跑无关历史路线 |

一组失败 PC 留下的误差不等于 A 的完整困难子空间；样本有来源偏差。本轮使用来自三个历史组合的实际快照，并保留一个预先定义的三维已知误差作为独立控制。以后新 PC 若暴露新的慢方向，只增补一至两个有身份的样本，不从零开始，也不无限累计基底。

结论必须带 `model/input/operator/space/norm/PC/source` 身份和适用范围。同一 A 换 b 时算子档案可复用，但新解误差不能冒用旧 b 的参考；换波长、材料、网格、Floquet、DtN 或 fine 离散后，框架可复用，数值结论需重新验证。换机器仅保留数学结论的资格边界，性能与资源重测。

## 3. 批次结构与数量边界

| 阶段 | 内容 | 未满足时如何继续 |
|---|---|---|
| D0 | 核验已有快照、源码、时钟和数据；形成最小共同样本清单 | 非关键旧快照缺失就标缺，不重跑旧求解；共同 A 不可信则停止 |
| D1 | 原始模型的跨方法问题档案、误差计量与实际端口库存 | 没有真实参考时先做残差/已知误差诊断，不把它们冒充真实解误差 |
| D2，条件 | 优先复用匹配参考；否则最多一次当前原始 p6 的有界独立直接参考 | 容量/时间不安全就记录缺口，走无参考分支，不能无限优化 reference |
| D3 | 最佳表示、实际粗修正、细层互补与三种已有 PC 的同输入检查 | 求解/投影精度不够则该结论 unresolved，不包装成空间失败 |
| D4，条件 | 仅在证据指向传播响应失配时，做极小的 p6/p4 色散控制 | 不能建成或不能可靠匹配分支就 unresolved，不展开新本征求解项目 |
| D5 | 形成跨方法原因矩阵、可复用诊断包，以及一个有依据的后续设计建议 | 集中提交 response_v4.md；本 review 不自动实现或运行新 PC |

D0-D5 连续执行，不在每张表、每个小测试后等审阅。最多一次原始 fine 独立参考构建/求解；不重复旧 A2R/R3/F3 长跑；最多 36 次完整 PC 诊断调用，另有至多 18 次独立 H6/S6 互补检查；不为填满预算运行无用样本。无新增非可分 full solve、h5、MPI 扫描或短波 PDE。

参考求解允许采用已有静态凝聚 direct，只为取得同一完整 p6 解；此处的消元不能成为新生产架构，也不得把凝聚 residual 直接当 full residual。局部齐次 cell 的 D4 是传播诊断，不是准二维求解替代。

## 4. D0：冻结已有失败快照，不把 residual 当 field

原始物理与任务书 §3 一致：13.5nm、1°、s、p6/h10、完整三维单胞、双 Floquet 与 80 DtN modes。独立 p6 rows164592，存储 rows173802；两者不可互换。

```text
physical_model_sha256 = 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f
mode_manifest_sha256  = dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2
```

首选三个快照：A2R 的 step160、旧 LIGHT 的 step448、本次 JOINT 的 step448。三者覆盖完整 S6、LIGHT、联合接受；相同 step 只用于公平读曲线，不假设误差相同。F3 terminal476、旧 LIGHT terminal576只额外作离线空间/曲线核验，不增加默认 PC 调用。若首选文件缺失，使用同次运行已验证的最近安全快照并明确 step，不重跑生产它。

逐项验证 checkpoint manifest、solution hash、实际 dat、physical/mode、canonical numbering、Floquet、source 和数组 finite。用当前未改变的原 A6 重算 `r=b-Ax`；先核对 operator/source 等价，不把 source SHA 相同或不同本身当数学身份。存在 mismatch 就隔离，不强行复用。

`x` 是 primal FE 系数；`r` 是 dual 方程残差。禁止把 r 直接当电场画 L2 能量图。需要场样式的 residual 图时应明确经过了哪个 Riesz 映射；没有映射只能报告 coefficient residual，注明基函数尺度依赖。实体归属跨 cell 时用分区权重防止重复计数。

所有数组进入 ignored `diagnostic_packet`，Git只保留索引/hash/小统计。schema至少写入向量角色、原始尺度、归一化尺度、单位、canonical identity、误差来源等级和 metric SHA。临时稠密向量可流式读写，不保存全局 N×N、全长 AP 基底或跨 PC 的不断增长的方向库。

## 5. D1：与 PC 名称无关的问题档案

### 5.1 A 仍是所有检查的共同裁判

```math
A=K_{\rm curl}-k_0^2M_\epsilon+T_{\rm DtN},\qquad r=b-Ax.
```

full-space 是未知量表示，matrix-free 是作用实现；A不仅计算最终残差，也用于全部真实方向作用。保留已有 component identity；仅对新诊断用到的接口补查输入不变、复共轭、约束和 zero/finite，不重复全部旧四源资格化。

基于既有 component action记录 `Kx`、`-k0²Mεx`、`Tx` 的范数与交叉内积，区分大项抵消与数值 action 错误。比值很大只提示相消敏感，不等于已经测得条件数或证明不定性是唯一根因。禁止从三个随机向量或一次 Ritz 值宣称完整谱、最小奇异值或伪谱。

### 5.2 统一 field metric，不改变外层验收

对合法 primal 场采用未加损耗的实际 FE L2 质量矩阵 M0：

```math
\|e\|_{M_0}^2=e^H M_0 e=\int_\Omega |E_e|^2\,dV.
```

另报告 `k0^-2 * integral(abs(curl E_e)^2)` 及材料分区/单元能量。M0在独立约束空间上正定；slave identity rows不加入场能量。它只用于诊断，不替换 A 或正式 Euclidean true residual 的1e-6门槛。不把这个正质量诊断称为新的 positive-PC campaign。

按 cell、材料、z 区间、x/y 变化与真实上下端口整理误差；不先按某个 DD 分区划图，避免档案被一种子域划分绑死。curl 小不等于已证明纯梯度误差；若没有相容离散梯度和相应投影，不强行给 Helmholtz 分解标签。

### 5.3 实际外部传播库存

读取完整 mode keys、横向波数和按出射支选取的 kz；列出入射分支及最接近截止的至多三个不同分支。其余模式仍保留在完整库存，不作 PC mode 截断。

```math
k_{z,mn}^2=k_0^2\epsilon_{\rm ext}\mu_{\rm ext}-|k_{\parallel,mn}|^2.
```

实际有损 exterior 使用现有复数分支定义；公式中的模记号仅适用于实横向波数。空气入射分支在1°下 `kz²/k0²=sin²(1°)` 的小量关系是敏感性背景，不是 coarse 已错的测量。物理界面真实反射不能归罪于人工子域边界。

## 6. D2：真实误差参考与不依赖参考的退路

### 6.1 优先复用，缺失才允许一次有界 reference

先核查已有匹配 full p6 raw。10° M3a、Hybrid、不同 mode/geometry、只有 R/T 标量的旧包均不能作当前1°的完整 x_ref。不能让用户重新收集仓库已存在的材料。

若不存在，允许一次 `python scripts/run_case.py <新显式reference.dat>` 的现成 Full3D direct control，必须相同物理、fine FE/quadrature、RHS、mode与独立约束。只采用已有受控装配/凝聚能力，不为 reference 新写大型求解器。装配、symbolic、numeric分级受§10安全线；预测显示不安全就不numeric，不改p/h、材料或预算。

参考需恢复 full p6 x_ref，用原 matrix-free A 检查相对残差<=1e-10；核对映射和至少三个合法向量的参考/原 action 等价。可在同一 factor上做至多一次残差修正，比较修正前后 field norm与选定样点，检查参考稳定性；不得重复调direct参数。

reference residual小不是严格 field error界。仅当修正稳定、身份完整、参考不确定性明显小于本轮待诊断误差时，才把 `x_ref-x_checkpoint`标为`REFERENCE_ESTIMATED_ERROR`。小差别不能解释为已证因果；近奇异/参考不稳则保留限制。没有连续精度检查，不称 continuum truth。

```math
e=x_{\rm ref}-x,\qquad Ae-r=Ax_{\rm ref}-b.
```

最后这个一致性必须测量：参考不精确时 Ae与r不是严格相等，不可将其差隐藏。release direct factor和装配矩阵后再构造多层诊断栈，避免峰值重叠。若产生物理输出，参考自身通过对应物理Gate才标official；旧未收敛场仍不得标official。

### 6.2 放不下 reference 不等于整个诊断停止

无参考时保留 `REFERENCE_UNAVAILABLE_ON_16GB`，继续D1和已知误差试验，但不能把两个未收敛解之差当真实误差。实际迭代增量可标`OBSERVED_UPDATE_DIRECTION`，只用于不同方法的可重复应答，不代表遗漏误差的全集。

预先固定一个非可分三维已知场作为独立控制：以横向 Floquet 因子乘两个不同的 x/y 周期谐波及 z 窗口，三个分量均非零；通过当前合法 Nedelec 插值与约束得到 e_test，保存解析recipe、FE向量hash。不得根据PC结果挑选更容易的控制向量。用真实全模型 `q=A e_test`，答案已知为该离散 e_test。

这是原始三维 A 上的 manufactured error equation，不是原始入射散射求解通过，也不是在非可分材料模型上通过。真实 geometry仍按原模型；之后实际非可分结构需要自己的A与误差档案。

有参考也保留这一控制，用于避免全部分析只适配旧PC留下的误差。本轮主样本最多三份参考误差加一份预定义控制，逐个处理，不建庞大训练集。

## 7. D3：表示能力、实际修正与细层互补分开测

### 7.1 p4“能表示多少”，不是“某次p4解得多准”

对每个有可信 e 的主样本，计算 M0 最佳表示的数值估计：

```math
c_* = \arg\min_c\|e-Pc\|_{M_0},\qquad
(P^HM_0P)c_*=P^HM_0e.
```

```math
e_\parallel=Pc_*,\qquad e_\perp=e-e_\parallel,\qquad
\eta_{\rm space}=\frac{\|e_\perp\|_{M_0}}{\|e\|_{M_0}}.
```

P为现有p4到p6相容传递。优先 matrix-free p4质量方程CG+固定对角，relative residual1e-10、最多256步；每样本最多一次，所有投影合计不超过1800s。不为投影重新开发通用MG或global dense基底。投影不收敛便记`PROJECTION_UNRESOLVED`，继续其他可以解释的检查。

报告方程残差、正交条件、Pythagorean缺陷、尺度、条件/数值精度限制；新代码的代数小测试覆盖复共轭和已知range(P)向量。未经精度闭合的投影误差只是某个近似的上界，**大上界不能证明空间能力不足**。即使投影数值通过，也不把其结果称严格误差界；原因判断需留足远大于数值不确定性的差距。

同时输出L2和缩放curl误差，避免单一系数范数支配解释。不能用P^H r的范数或某个MR系数替代η_space。

### 7.2 相同样本上的实际 coarse correction

```math
d_G=P A_4^{-1}P^H A e,\qquad
\eta_G=\frac{\|e-d_G\|_{M_0}}{\|e\|_{M_0}}.
```

使用已有准确p4 reference及原A4 true residual<=1e-10；不提高其精度，也不再运行36步shifted inner。比较未经MR的d_G、原MR接受后的方向、最佳表示e_parallel的差距和成本。固定单位步长仅作诊断，不强制用于完整求解。

在e_parallel上作一个合法coarse identity control，帮助区分传递/求逆错误与实际表示不足。若p4很病态导致forward error较大而backward residual小，要报告不能单凭backward residual宣称近似逆作用精确。

关键分支：η_space很小而η_G很大，提示实际粗响应/投影问题；η_space本身很大且投影精度可信，提示该空间遗漏重要误差。两者可能并存，不预设必须二选一。

### 7.3 细层是否处理得了 coarse 留下的误差

```math
q_\perp=A e_\perp,\qquad
\eta_C=\frac{\|e_\perp-C(q_\perp)\|_{M_0}}{\|e_\perp\|_{M_0}}.
```

C分别取已有H6和已有S6，保留原degree/window/对角，不调参。检查原始修正和现有MR接受后的修正，报告作用次数/成本。非线性PC的输入与参考误差必须同比归一化，并验证该profile的相关齐次性；不能只缩放q而不缩放对应e。

相同原始q还要调用既有完整S6-p4-S6、顺序LIGHT、JOINT各一次，返回相同角色的fullspace修正z；对比field error和true residual。共享合理setup，复用一次p4 factor，但所有同时存活内存计入。不得在每个样本重建factor，也不因为一次profile昂贵而悄悄改它。

必要时只对最新F3样本按原顺序保存pre/middle/post后的field error，区别“单步残差下降”与“场误差是否更接近”。全部为诊断apply，不更新成新的长程求解，不据单次stationary contraction给所有FGMRES下死刑。

### 7.4 restart与实现的边界

只读旧周期曲线、已有small Hessenberg/orthogonality数据和monitor记录，检查reported/explicit差异、周期内外的趋势。若未保存足够Krylov数据，标`RESTART_CAUSALITY_UNRESOLVED`，不能从曲线拐点宣称restart是原因，也不加大restart再跑。

非线性PC不能通过几个probe拼成固定矩阵再解释其谱。两个不同checkpoint误差的M0归一化相关性可帮助检查共同慢方向，但不是全局谱诊断，也不是给最终物理场拟合任意相位。

## 8. D4：有条件的传播响应核查，不预设“1°就是答案”

只在D3显示p4表示不差、但实际粗修正明显失配，或D1明确指向近截止/相消敏感时开展。若主要证据已指向不同原因，可跳过并说明。旧聊天的1°敏感性推导只是优先假设，不能当作已测root cause。

允许一个极小的齐次空气单元/周期cell控制，使用原网格一个实际仿射尺寸类、同族p6/p4、同积分和orientation；不得把整个结构平均成空气或改真实A。选类规则在看新结果前固定：原网格中k0乘最大边长最大的空气类；并列按canonical key排序。

可构造该cell的周期Bloch体算子，在1°与10°两个固定方向比较p6/p4的传播分支，共最多四个small generalized eigenproblems，每个不超过1024独立rows，dense工作<=256MiB、累计900s。分支必须按已知横向极化/连续分支重叠识别，排除离散梯度零模；不能只挑最接近目标的某个特征值。若现有代码不能在预算内形成可靠映射，停止这个子项，不新开本征/QEP平台。

```math
K_p(k) a_p=\lambda_p(k)M_p(k)a_p,\qquad
\delta_{46}=\frac{|\lambda_4(k)-\lambda_6(k)|}{k_0^2}.
```

同一k的两种离散响应差δ46以及与sin²(1°)的量级对照，只是局部体色散敏感性证据；它不是直接测出的完整模型kz误差，更不能单凭它宣称真实传播变成倏逝。完整模型有损、材料界面和DtN反馈都没有被这个齐次控制包含。

只有当局部差异与实际失败误差、D3表示/响应差距相互支持，才能标`PHASE_MISMATCH_SUPPORTED_ON_TESTED_COMPONENT`。不能据此修改quadrature、材料、入射角或替换粗算子；如何改是下一review决策。

## 9. 将来换子域法，哪些工作不重复，哪些必须补查

本轮输出通用诊断接口：接收有身份的原A、primal误差或dual残差，以及`PC.apply(q)`；返回z、原A z、输入/输出field与残差范数、分阶段成本和全部source信息。数值函数进通用src模块，runner仅组织实验，不造庞大框架。

| 未来变化 | 直接继承 | 最少新增检查 |
|---|---|---|
| 同A换DD/Schwarz PC | x_ref、难误差包、metric、端口库存、相消与空间分布 | 新PC在冻结q上的响应；局部逆、拼接/重叠和全局粗修正的贡献 |
| DD内部换Robin/PML | 同上，保留真实反射信息 | 区分局部方程没解准、人工传输近似失配、缺少远程纠错；不能把场中的所有反射归因于切面 |
| 同A换coarse/transfer | A与误差档案 | 只重做新空间的最佳表示、投影稳定性和成本 |
| 改fine网格/材料/波长 | 通用程序、诊断公式、旧边界 | 新A/映射/材料/通道与参考/误差，旧向量只能明确转移后作控制，不直接当新解 |
| 换硬件/MPI | 已证数学关系的适用范围 | owner/ABI/数值等价及资源/时间，不复用旧速度数字 |

对新DD，局部`L_j z_j≈R_j q`残差小仍不足；必须将修正通过实际权重/映射送回全局，比较`q-Az`及有参考时的场误差，单独记录局部与全局作用。若局部逆成为疑点，仅在已授权、可负担的代表块上作高精度对照，不把全域精确逆当PC，也不自动为所有子域构造LU。

**本轮不实现新DD，不重跑旧16 slab/75D、Task040或旧PML。**历史10°凝聚M3a不能直接接受当前1°full-space向量；没有合法映射和同一A，标`NOT_COMPARABLE`。上述接口是未来复用合同，不是旧方法跨模型通过的许可。

将来新PC的失败方向可能不同。旧包只提供共同对照，正式新运行出现新慢误差时必须追加一至两个样本检验，不承诺“诊断一次，所有方法永远不用再诊断”。新增检查是增量验证，不是重写整部历史。

## 10. 资源、时间与范围控制

沿用16GB本机安全线：有效物理/cgroup内存与available扣`max(4GiB,15%有效总RAM)`，cap不超过12,000,000,000B，warning=0.85cap；每次启动重新计算。zero-swap、一个heavy、完整parent/MPI/compiler后代RSS、释放后采样与hash均保留。参考factor与PC栈分阶段释放；不能借工作站的2TB绕过当前可见上限。

| 计算 | 本轮上限 |
|---|---:|
| 唯一可选原始fine独立reference | workflow<=3600s；安全预审不支持则不numeric |
| D1/D3的原始模型诊断构建与作用 | 合计<=7200s；完整PC<=36，额外独立H6/S6<=18 |
| 投影 | 包含于D3；总<=1800s，每主样本一次、max256 |
| D4局部传播控制 | <=900s；至多四个受限小问题 |
| 全批次，包括测试和失败 | <=14400s，不借V2余量，不追加长跑 |

计时最小修复必须先于新heavy：同步记录parent/worker的monotonic、可用的CLOCK_BOOTTIME、UTC和clock_info，保留一致stage边界。预算至少同时检查已验证的monotonic与boottime，任一到限请求安全收口；UTC不替换raw时钟。若同一区间的时钟差异超过`max(5s,1%区间)`且无法由已记录的时钟事件解释，标`TIMEBASE_INCONSISTENCY`并结束受影响heavy，不能继续声称wall通过。该保守停止不是numerical fail。

CLOCK_BOOTTIME可计入Linux suspend时间，但不保证解释所有WSL/虚拟化时钟差异。禁止将旧差异直接归咎于CPU节流、暂停或clock bug。新增时钟修复只做一个合并tiny测试批次，不为复现两小时差异另跑PDE，不重写旧历史。

数值/安全共享错误立即停止；单项reference/投影/色散能力不足允许跳过后继续可解释项。用户停止优先。没有必要时不升级库、调线程、改BLAS或迁移机器。所有恢复/可视化从已保存数据进行，不重跑以获得更漂亮曲线。

## 11. D5交付：原因矩阵，不是另一个含糊的PASS

只新增一份中心报告`outcomes/nonconvergence_diagnosis_v3.md`及小JSON`outcomes/records/nonconvergence_diagnosis_v3.json`；ignored诊断包保存可复用向量/metric/manifest。同步summary、run_index、test_summary、两个项目总账及response_v4，不为每个子步骤增加平行综述。

| 必答原因类别 | 必须给的证据 | 不足时的状态 |
|---|---|---|
| 输入/作用/尺度或参考错误 | 独立身份、残差复现、primal/dual、参考一致性 | IMPLEMENTATION_OR_AUTHORITY_UNRESOLVED |
| 空间表示不足 | 可信误差上的合格最佳表示估计及不确定性 | SPACE_CAPACITY_UNRESOLVED |
| 粗响应/投影失配 | η_space与η_G的差距、局部传播/相消证据 | COARSE_RESPONSE_UNRESOLVED |
| fine互补处理不足 | e_perp上的H6/S6作用与完整组合对照 | COMPLEMENT_UNRESOLVED |
| 局部逆/全局耦合不足 | 当前p4证据与未来DD局部/全局接口定义 | 不把未实现DD写成已诊断 |
| restart/非正规影响 | 已有合法Krylov/orthogonality数据及范围 | KRYLOV_CAUSALITY_UNRESOLVED |
| 实现成本/容量 | 可解释的分阶段时间、时钟限制、同时存储模型 | COST_OR_CLOCK_UNRESOLVED |

每条结论使用`SUPPORTED`、`NOT_SUPPORTED_ON_TESTED_SAMPLES`、`UNRESOLVED`或`MIXED`，列出支持与反证、适用样本和置信边界；允许多个因素，不强行选唯一root cause。不能靠一条经验百分比把新方法整体判死，不能将“无参考”掩盖成完整原因已查清。

最后只提出一个优先的后续改动对象，说明它处理哪些已识别误差、与旧失败路线的实际区别、怎样避免增长型global LU、成本如何随h/波长/复杂材料变化；给出直接进入原始与非可分三维验证的最小方案。**本轮不执行该新PC**；若证据仍不足，明确剩余唯一关键缺口及最小补证，不罗列十个方法或再推荐一次无依据p5/PML。

无论以后用多层还是DD，最终仍必须通过原始真实残差、E/H、R/T/A/A_volume、衍射级、精度与资源Gate。此次诊断不能授予0.7nm、任意三维或production资格。新的参考/控制若成功，只按其实际范围记录。

## 12. 提交和可复现证据

沿用根与docs AGENTS、repository_work_principles及Markdown标准。建议普通提交顺序：通用诊断/时钟最小接线 -> 冻结样本与唯一reference（条件） -> 原始模型有界分析 -> 原因矩阵与response_v4。正式计算前clean commit，记录完整SHA、ABI、MPI/线程和input/physical/operator/metric/source hashes。不amend、强推、改旧raw或跨分支写入。

新增reference必须用单dat入口保存input_original、resolved_config、run_manifest、input/physical/source SHA、run_summary和资源/artifact hash。只读分析也有唯一manifest，逐项标measured/derived/not_run，不假装分析时运行了旧PDE。代码变化只跑必要focused tests；收口一次task-focused回归，不跑全仓测试代替原因定位。

数学核心复用现有fullspace_physical_action、transfer、physical_intermediate、p4参考和canonical工具。新metric/projection与probe评价函数保持通用、小而独立；旧三个PC参数/行为不可变。数值数组不入Git，诊断cache按A/space/metric身份复用但不隐藏冷构建和内存。

## 13. 理论与工具依据的范围

以下来源用于方法说明，不替本项目给出根因。投影、误差方程与一致性公式为本报告在所列假设下的线性代数推导。

| 入口 | 本报告使用的内容 | 不推导的结论 |
|---|---|---|
| [PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/) | flexible外层允许非线性PC；原A与PC区分 | 不能以固定PC谱自动解释非线性MR组合 |
| [PETSc FAQ](https://petsc.org/release/faq/) | 多种不收敛来源需分开，包括PC、尺度、非线性和正交化 | 不照抄参数建议重开本仓库已关闭扫描 |
| [Ainsworth 2004 原作者机构条目](https://strathprints.strath.ac.uk/64/) | Nedelec阶次/网格影响数值色散 | 不证明当前p4的具体色散数值或唯一失败原因 |
| [Python time 官方文档](https://docs.python.org/3/library/time.html) | monotonic/boottime/realtime含义与差别 | 不凭API说明断言旧WSL差异的实际来源 |

本轮是在同一个原始真实问题上建立可以跨PC复用的证据，不是把所有历史方法再跑一遍。定位的目的，是让下一次完整算法改动有可核验的依据，而不是承诺任何一种方法必然成功。
