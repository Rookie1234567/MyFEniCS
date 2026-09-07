# Task39extra 历史报告：历次 Maxwell 求解尝试、成功条件与失败边界

日期：2026-09-07。新分支：`task39extra`。任务基线：`2dc2e7305f10dc391a13970c6f0f0340cb87b6ee`。

## 1. 范围、快照与阅读方式

本报告按照仓库项目总账覆盖 Task000–038、Task038-extra 各主要研究阶段，并加入 Task039/Task040 的相关分支证据。它是跨任务的因果总结，不声称逐行重审全部历史代码，也没有重新执行 ignored raw 中的 PDE。表中数字是历史记录报告的 measured/derived，不是本次新测量。

| 来源 | 固定快照 | 本报告使用范围 |
|---|---|---|
| Task038-extra 执行分支 | `2dc2e7305f10dc391a13970c6f0f0340cb87b6ee` | 新任务直接继承基线；最新 review/response 为 V19 |
| Task039 Hybrid/5 nm 分支 | `9dc9ac58e05e5422498dade503046f9ae87d13d9` | 分支身份已核；5 nm Full3D 负结果另固定到下述历史结果文件 |
| Task039 5 nm Full3D 原始结果 | `f4073adabb91bffe5c3954b8ae8b63270efa3e15` | T3/T4 固定网格 direct/iterative 对照，不冒充全分支最新网格结果 |
| Task040 side-factor 分支 | `50897c0c62d1f35abed5b196ae17997b2e7521cc` | summary 的 V9/Response V10 已发生结果；Review V10 的新工作是授权，不是已完成结果 |
| Task041 | Task040 review 中仅见后续容量任务引用 | 未在本报告审计其结果，不猜测其状态 |

“所有尝试”按完整路线和阶段记录，而不是把每次小改动都叫一种新算法。不同波长、入射角、p/h、凝聚表示、环境和 RSS 口径不可直接横向排名。任务设计以本轮用户明确要求为准：本机16 GB先做13.5 nm真实三维，再迁移工作站推进0.7 nm。

## 2. 总体判断

项目已经有可信的物理基础、直接参考、输入身份和低内存算子；也存在真正完成 full residual 与 R/T/A 的迭代成功。问题不是“迭代法不存在”，而是还没有完成对复杂三维和更短波长有效、且成本受控的全局近似逆。

最强成功经验是：**完整物理局部区域 + 全局波动修正 + 合法的 flexible 外层 + 正确的共轭/约束/恢复**。最强反复负经验是：**辅助问题通过、局部动作通过、粗矩阵解得准，都不足以保证完整 Maxwell 收敛**。

因此不再以“本周换一种 Robin/PML/ILU 名称”组织任务，也不把过往同名方法的失败推广为所有物理多层或所有区域分解的否定。

## 3. Task000–014a：物理基础与黑盒迭代

证据入口为基线中的 `docs/development_progress.md`、`docs/task012_literature_review_maxwell_preconditioners/outcomes/summary.md` 及各任务目录。

| Task | 实际工作 | 历史结果和教训 |
|---|---|---|
| 000–004 | 代码/功率一致性、小单胞与MPI回归、端口和吸收基础 | 先排除物理和并行错误，不能用能量恒等式替代场正确性 |
| 005–008 | 目标几何、网格规模、直接法和官方DtN/RTA参考 | p2/h2形成best-available reference；更细direct触及资源，不等于没有解 |
| 009 | GMRES/FGMRES/BiCGStab，Jacobi、ASM/ILU/local-LU、通用AMG等筛选 | 没有现成黑盒组合形成通用成功；明确采用norm(b-Ax)/norm(b) |
| 010 | MUMPS-BLR及shifted A/P接口 | h2的BLR参考有残差与RTA成功，仍是近似直接法；小shift+普通ASM并未解决问题 |
| 011 | real FE-only AMS、complex AMS、matrix-free action | FE-only正信号和action等价成立；当时complex build崩溃是实现/ABI问题，不是AMS理论失败 |
| 012 | 第一次系统文献调研 | 已讨论AMS/HX、shift、DD、sweeping和modal deflation；今天不能只重列名称 |
| 013 | real/imag block、same-H1辅助数据 | real split代数等价、FE-only可收敛；没有完整DtN散射资格 |
| 014a | 含FE/aux耦合的reduced Stage4 | 1000步真实残差约2.15e-2；FE-only成功没有自动迁移 |

Task010的一个h2 BLR结果约4次迭代达到2.09e-8，说明更强近似逆确实可以改善收敛；但它以较重因子为代价。它不能成为“只要加BLR就解决0.7nm”的论据。

## 4. Task015–025：端口、响应与Schur的连续探索

| Task | 机制与结果 | 可以保留的结论 | 不允许的推广 |
|---|---|---|---|
| 015 | 剩余残差集中于top、零级、s/y方向 | 慢方向涉及FE与端口耦合 | 残差在某mode上，不等于解误差只由该mode的一个lift修正 |
| 016 | dominant zero-order右lift与小粗修正，最好改善约1.000045倍 | 便宜的lift质量不足 | 不是所有端口感知PC都失败 |
| 017 | Petrov/adjoint及true-FE sampled response | 部分response出现约5.82倍改善；直接塞入PC仍可能变差 | one-shot improvement不是full solver |
| 018 | FE-AMS段与有限最小残差响应修正交替 | p1最好约1.662e-3，约12.91倍改善 | 未到1e-6，也未证明p2可迁移 |
| 019 | p2/h5验证 | baseline约1.6386e-2，指定修正约1.6357e-2 | p1小模型成功不应再被当p2依据 |
| 020 | 默认沙盒的DD/sweep/coarse/action比较 | diagonal sweep等无益；部分adaptive方向仅有窄正信号 | 沙盒不是最终目标几何 |
| 021 | 目标p2/h5的FE response与coupled Schur | serial原型出现约9.87e-7、2.43e-7；exact FE-block参考约8.16e-12 | 强response有用，但serial高fill不是低内存生产PC |
| 022 | p2/h2预审 | 615108 FE DoF；高fill SPILU容量约27.8GB，低fill质量/时间不足 | failure是近似inverse成本，而不是mode selector一定错 |
| 023 | PETSc/MPI FE-response、回填与官方RTA | h5闭环成功；h2普通ASM/ILU不足，local LU昂贵 | h5 success不代表h2或短波成功 |
| 024 | 手写FGMRES、CSR、real-split与复共轭加固 | 复现/代数基础改善，指定算法仍约0.1586残差 | 基础设施通过不是算法通过 |
| 025 | full80-aux cached Q、small Schur、多层原型 | h2外层100步约0.1185；response residual约0.286–0.541 | 小Schur精确不能抵消Q质量不足；粗层未完整实现不能判死整类MG |

这一阶段最重要的因果链是：

```text
观察到端口残差集中
→ 简单少模lift无效
→ 更真实的FE响应改善
→ FE响应的低内存求解成为瓶颈
→ 不再显式保存大Q，转向精确端口消元
```

如果今天再次构造一个低维Z，只因为“这些是显著外部模态”，就可能重演Task016/019。必须说明Z代表的全局物理响应，以及构造与应用成本。

## 5. Task026–031：确实成功过的完整迭代结构

### 5.1 端口消元不等于单元静态凝聚

Task026将增广系统中的小端口块精确消去：

```math
\begin{bmatrix}F&C\\D&H\end{bmatrix}
\begin{bmatrix}u\\a\end{bmatrix}
=\begin{bmatrix}b_F\\b_H\end{bmatrix},
\qquad
(F-CH^{-1}D)u=b_F-CH^{-1}b_H.
```

这是端口辅助未知量的消元。后来高阶单元内部DoF的assembly-time static condensation是另一层操作。新任务必须明确自己继承了哪种表示，不能只说“condensed”便混用向量。

Task026还修正了当时复dot共轭语义；项目总账记录该修正使某200步残差从约0.259降至约0.00105。数学结构再好，错误的复内积也可能将其破坏。

### 5.2 Task027的成功不是“谱粗空间成功”

已接受组合：exact condensed physical action、16个完整物理slab、owner-computes、shifted local ILU1、两步平滑、75维no-RHS Floquet z-hat粗空间、right FGMRES100。

| h / p / 模型 | iterations | true residual | 历史RSS口径 | 状态 |
|---|---:|---:|---:|---|
| 5 nm / p2 / 13.5 nm、10° grazing | 1201 | 9.8395e-7 | 约1.957 GB | 该离散full pass |
| 3 nm / 同配置 | 993 | 9.9326e-7 | 约5.070 GB | 该离散full pass |
| 2 nm / 同配置 | 1804 | 9.9974e-7 | 约12.958 GB | 该离散full pass |

同一规则的最大/最小迭代比约1.8167，满足当时tested-range Gate；不等于严格渐近mesh independence。该历史报告存在非零swap字段，不能追溯宣称满足今日zero-swap合同。

同任务的positive-energy spectral、interface harmonic、shifted near-null和PCHPDDM/GenEO没有性能收益。因此必须记成“fixed coarse + physical slab成功”，不能变成“任意谱空间已有效”。

### 5.3 75维到底是什么

它来自25个纵向hat位置、3个分量和已知横向Floquet相位，不是75个任意三维本征模。粗矩阵确实采用真实物理算子：

```math
A_0=Z^HAZ,\qquad Q_0r=Z A_0^{-1}Z^Hr.
```

关键成功是全局纠错作用；具体75这个数字没有随电尺寸增长的保证。固定横向相位无法先验代表所有新衍射方向和复杂三维材料引入的误差。

### 5.4 Task028–031的优化与代价

| Task | 保留成果 | 应记住的代价 |
|---|---|---|
| 028 | 选择性整合、benchmark与明确普通默认 | 研究全分支不应整体推成production |
| 029 | direct内存来源与生命周期诊断 | 生命周期不改变全局factor复杂度 |
| 030 | 保留75D coarse的对称pre/post结构、ILU与factor生命周期优化 | 新p/h coarse虽代数正确，求解更差；不能只按粗维数判断 |
| 031 | assembled-F-free action、overlap0.125、factor-only、FGMRES90、释放后RTA | 内存显著降低，但public form action增加执行成本 |

Task031 p2/h5、h3、h2分别1157、1994、1977步通过。h2同时worker峰值7.897675 GiB，solve约11982.6秒；相对另一历史方案的约5倍时间增长与内存收益并存。sampler不同的历史百分比只能辅助比较。

结论不是“回去原样使用75D”，而是继续保留局部和全局修正的互补分工，同时重新设计波长增长时的表示能力和成本。

## 6. Task032–039：高阶、Hybrid与短波长压力

Task032的Hybrid通过上下三维区域加中间模态传播降低规模；后续Task033–035及字母扩展完善高阶Floquet、网格/误差、静态凝聚、端口traction和E/H一致性。Task036–037b/c进一步加固direct和iterative Hybrid路径。Task038建立one-dat-one-run入口和provenance。

这些成果对新任务的价值是输入、物理验证、内核与资源管理。**中间区域可模态传播不是任意三维的许可；新任务不通过改变物理范围来复用Hybrid的便宜求解。**

### 6.1 Task037-extra的继承边界

Task038-extra的选择性迁移审计已记录：full-space action、DtN action和canonical工具有正证据；W5/W7等真实外层存在负结果；fixed 75/390/530D range、局部882D factors和旧W8–W18路径不作为通用生产PC继承。保留代码和负记录，但不恢复旧runner去试另一组参数。

### 6.2 5 nm失败的准确身份

固定到Task039历史T3/T4的比较：

| 方法 | 物理/离散 | 实际结果 |
|---|---|---|
| Full3D direct | 5 nm、p6/h10、10° grazing、MPI8、604外部channels | residual约3.5128e-11；matched discrete authority |
| Full3D iterative M3a | 同一物理/离散 | 4000步，full residual约0.15526482；official输出未运行 |

这不是今天13.5 nm、1°、full-space positive pMG只改一个波长的严格A/B；它涉及不同历史实现与离散表示。它是必须重视的波长压力负结果，但不能夸称已经否定所有物理多层。

Task039后续固定5 nm Hybrid exact-side结果属于Hybrid方程与指定case；即使内存降低、residual通过，也不构成任意三维Full3D通过。旧0.7 nm组件预算主要面向约256GiB，不能直接作为2TB最终no-go。

## 7. Task038-extra：逐条区分“测试很多”与“完整求解很多”

### 7.1 T1–T5和V1–V3

| 路线 | 真正测到的内容 | 结论 |
|---|---|---|
| T1–T3 | 输入、full-space action、dynamic DtN、MPI身份 | 是可复用基础，不是完整解 |
| T4 | 两slab一阶Robin facet action | 不是PML，也没有外层KSP |
| T5 Candidate A | 真实局部shell、fixed GMRES8/8、双向残差传播 | physical RHS单次rho=0.8145890334，大于0.60；full外层未运行 |
| Candidate B | 混合Si–Si/Si–air内部界面 | 缺合法内部模态authority，NOT_APPLICABLE，不是数值失败 |
| Candidate C | 二阶impedance | 约12.942GB时资源停止，formal数值未知；不是PML |
| old W5 bridge | key相同但RHS系数不一致 | old/current不能简单搬raw vector；合法做法是从primal重算当前残差 |

Candidate A已经有forward/backward和真实局部Maxwell，因此后来不能以“现在改用真实局部求解/双向扫描”为唯一新颖性。

### 7.2 中间的LOR、trace-harmonic、谱空间与transfer研究

Task038-extra的V3–V12并非十二套完整物理求解器。阶段包含adaptive trace-harmonic、局部谱问题、LOR/HX、几何MG、transfer/adjoint、容量与JIT检查。它们暴露了空间身份、内存、局部求解和物理长程修正的不同问题。

必须保留的边界：正定能量下构造的harmonic/spectral vectors不是自动合格的physical Maxwell-harmonic空间；小尺度transfer或adjoint通过不是h/p/波长鲁棒性证明；setup不能完成时，不能写成算法数值失败。具体旧记录按S7中的原始文件索引查询，不在本报告复制大量版本化原始数据。

### 7.3 V13–V18：positive层级成立，真实外层仍然困难

| 试验 | 记录事实 | 正确解释 |
|---|---|---|
| V13 positive p6→p3→p1 | 指定四源资格化通过 | positive auxiliary可用，不等于physical inverse可用 |
| V14 physical长程 | checkpoint500约0.483871；1000约0.483795 | 有真实物理平台证据；后续用户停止不是固定cap完成 |
| V15 rank32 Floquet | captured约0.00217982；rho约0.99890949 | 固定少量全局预选模态没有覆盖该残差 |
| V16 Q1.1 | 同一h50的物理Galerkin action一致 | 只验证算子/传递 |
| V16 Q1.2 | p3/h50指定物理内层残差通过 | 不是p6/h10外层 |
| V16 Q2 | inner10000步约0.774956；fine rho约2.70015 | 当前inner和修正未通过 |
| V17 exact p3 | p3 direct残差3.5516e-12；fine rho20.975739 | 当前一次Galerkin粗修正失败，不是所有真实A多层失败 |
| V17 unrestarted500 | 优于GMRES20但只有weak signal | 多留Krylov信息有益但未形成完整解 |
| V18 restart64短screen | additional1024残差0.272996；完整RSS1.583GB | 旧短程性能Gate失败，资源通过 |
| V18 eventual | checkpoint3048残差0.153469；采样RSS1.466GB | 用户性能受控停止；TERM最终步数/残差未知，未证明最终永不收敛 |

真实p3修正与完整物理多层的关键区别：前者只有一次指定的单位步长coarse correction；后者包含fine pre/post、inner inverse、实际外层组合和完整物理RHS。一次rho大于1不是一般FGMRES无效的充要条件。另一方面，最小残差接受也不能把一个几乎无有效分量的coarse方向变成强PC。

### 7.4 V16 W0并不是已完成的PML失败

W0的接口rank/count和simultaneous bytes没有闭合，所以W1–W4未运行。它是预审阻碍，不是已经实测“interface Schur不能收敛”或“rank超过512”。rank512当时是预算上限，不是实际自由度计数。

### 7.5 V19暴露了具体构建成本

| 项目 | 历史事实及口径 |
|---|---|
| global storage rows | 173802；252 cells；14 z layers |
| 最大PML局部空间 | 124530 storage / 117936 independent rows；180 cells |
| 四局部cell总数 | 576，含重复overlap与人工PML，不是全局物理网格 |
| 最大slab structural pairs | 136361232；不是实测装配NNZ |
| AIJ+转换数组已知小计 | 5999894208 B，derived；不含全部factor/workspace |
| C代码文件 | 409357759 B |
| sampled process-tree RSS | 8609562624 B；Python约3.282GB，cc1约5.275GB |
| 实际watchdog线 | 8585588736 B，来自14.65GB可见RAM扣安全余量 |
| 停止位置 | local mesh完成后的FFCx C编译；AIJ/MUMPS/外层均未到达 |
| evidence限制 | dirty worktree测量；晚到.o不在timeline内；完整peak未知、checker evidence_valid=false |

因此V19不能称为“PML再次收敛失败”。但它同样没有提供继续投入该PC的收敛依据。最大局部空间约为global存储行数的71.7%，说明“四个子域”不是四个四分之一成本的独立问题。

## 8. Task040补充审计：不能把另一分支做过的工作说成空白

在`50897c0…`读取的summary保留以下历史结果。对象是Hybrid side/bare-F等特定方程，与Task038-extra fullspace全局问题不同。

| Task040路线 | 记录结论 | 对新任务的影响 |
|---|---|---|
| corrected moving-PML MPI8 | 约21601.76s、RSS40560816128B；首个source checkpoint未形成，SIGNAL_UNAVAILABLE | PML不是从未尝试；资源阻碍不等于数学失败 |
| corrected full-spectrum Floquet | FULL_SPECTRUM_SWEEP_NO_SIGNAL；RSS37884526592B，swap0 | 不回到预定背景全谱修正试另一组参数 |
| 630×160经济粗集合 | natural coarse DoF100800；一阶段projection130502065136B而measured19786649600B | 大粗空间也可能成本失控；prediction不能当实测 |
| C0 explicit coarse | rho=6.7787735520；raw peak86960574464B，并有terminal metadata gap | 多放候选方向并不自动有效 |
| physical bare-F + fixed LOR | 256步约0.7349227023；wrapper adjudication缺口 | positive工具不能被提升为全物理inverse |
| Review V10 | 允许后续physical p-coarse决策，Response V11尚不由已读summary证明 | 授权不是已执行成功；不得照抄作新任务结果 |

Task040的物理局部/经济粗空间与Li–Hu论文启发之间有相近关键词；**不能仅凭文献新或名字不同便断言“仓库从未试过物理粗空间”**。真正区别必须落到局部算子、选择准则、传递、coarse solve和外层方程。

## 9. 十二条可执行经验

1. **始终用完整真实A和b裁决。** 正定、bare-F、局部PML、凝聚trace、Hybrid方程必须分开。
2. **保留局部与全局修正的互补。** 不能用更好的人工边界自动替代全局纠错。
3. **空间身份比数组长度更重要。** 相同keys不保证同RHS，primal/dual不能混淆。
4. **physical coarse不是positive coarse换名。** 材料、负质量与DtN必须真实，稳定性和相位解析能力另查。
5. **不要把单次rho作为整类Krylov方法的死刑。** 同时不要用有限最小残差的单调性伪装成快速收敛。
6. **小测试只防错误，不证明可用。** 第一批就接原始模型与一个非可分三维结构。
7. **运行级故障与数学失败分列。** resource、ABI、source、nonfinite、budget和numerical有不同下一步。
8. **先量同时存活对象。** 单rank、warm、事后cache、derived bytes不能替代完整冷构建RSS。
9. **max-it不是解法。** 无界增加inner/outer/restart只会掩盖失效和成本。
10. **参考与生产实现分开，但参考也要有预算。** 不能花很多轮先优化一个尚未知有效的巨大reference。
11. **场、能量、衍射级与精度资格同步。** A=1-R-T恒等式不够；最终解必须落盘，未收敛不生成official输出。
12. **已有负结果限制具体路线，不建立方法名黑名单。** 新组合必须说明差异，不准换名重复；也不准把一个失败推广为所有MG/DD不可能。

## 10. 本任务应继承与不应继承的内容

| 组件 | 处理 | 理由 |
|---|---|---|
| one-dat-one-run、physical/input/source身份 | 复用 | 防止模型/参数隐式漂移 |
| exact split Maxwell、streaming DtN | 复用并做新增路径必要一致性检查 | 外层物理基线 |
| same-mesh H(curl) transfer与positive层级 | 可复用底层，不继续positive-only campaign | 是辅助工具，不是完整解 |
| fixed-restart、checkpoint、release/recovery | 最小加固后复用 | 防丢最终解及对象重叠 |
| 旧p3 direct oracle | 仅复用通用装配/身份模式 | 不能重跑旧一次修正当新工作 |
| 旧75D、V15 rank32、Task040全谱 | 归档，不作为初始PC | 已有明确范围负证据/可扩展缺口 |
| V19 PML giant form与R0 runner | 不继续heavy开发 | 本task不再沿该路线累积构建成本 |
| Hybrid/QEP | 不迁入物理主线 | 不符合任意非可分三维目标 |
| 根目录/历史review/旧outcomes | 不修改 | 新任务仅新增范围，不追溯改判 |

## 11. 为什么Task39extra仍然值得做，以及怎样让它可证伪

新任务不宣称某个p4空间必定成功。其有限假设是：将真实物理中间方程、复移位内部层级、已有positive平滑和有限残差接受组合起来，在原始模型上是否比standalone positive pMG有效。

它必须同时给出：真实外层曲线、每次中间求解误差、pre/coarse/post分别贡献、全部action与PC成本、全过程RSS。中间层解不准时允许一次受控的高精度同算子对照；若解准仍无效，就停止该表示/组合，而不是再调几十组inner参数。

原始模型通过后，立刻用同配置跑同尺度非可分结构；不把“任意三维”留到项目最后。然后在同一连续几何上补一个网格压力点，资源不足则标出迁移阻碍，不退回准二维。

2 GB不再作为本任务首场真实求解的硬入口，但0.7nm/2TB的内存增长问题仍必须建立账本。允许本机16GB安全预算内的研究，不等于允许全局fine direct或无界coarse factor。

## 12. 固定证据入口

以下同分支相对链接随`task39extra`继承基线可读取；跨分支文件使用不可变SHA链接。

| 编号 | 入口 | 用途 |
|---|---|---|
| S1 | [项目总账](../development_progress.md) | Task000起阶段、因果链与历史数字 |
| S2 | [Task012调研](../task012_literature_review_maxwell_preconditioners/outcomes/summary.md) | 防止重新列方法名冒充新路线 |
| S3 | [Task027](../task027_mesh_independent_spectral_schwarz_pc/outcomes/summary.md) | 16-slab/75D成功与谱路线失败 |
| S4 | [Task031](../task031_compact_physical_slab_memory_optimization/outcomes/summary.md) | 低内存真实通过及时间代价 |
| S5 | [迭代器理论说明](../../notes/theory/iterative_solver_and_preconditioner.md) | coarse、owner、shifted-F与历史限定 |
| S6 | [Task038-extra任务](../task038_extra_full3d_iterative_0p7nm/task.md) | 物理身份和旧授权范围 |
| S7 | [Task038-extra汇总](../task038_extra_full3d_iterative_0p7nm/outcomes/summary.md) | 中间路线索引和V13–V19证据 |
| S8 | [p3精确粗修正](../task038_extra_full3d_iterative_0p7nm/outcomes/exact_p3_coarse_span_v17.md) | 一次修正失败的准确范围 |
| S9 | [旧传输收口](../task038_extra_full3d_iterative_0p7nm/outcomes/transmission_family_closeout.md) | A/B/C分类 |
| S10 | [Task037-extra继承审计](../task038_extra_full3d_iterative_0p7nm/outcomes/task37_extra_selective_migration.md) | 旧研究分支重用边界 |
| S11 | [V19回应](../task038_extra_full3d_iterative_0p7nm/response_v19.md) | compiler资源stop、dirty源码与cache-tail |
| S12 | [direct参考缺口](../task038_extra_full3d_iterative_0p7nm/outcomes/direct_authority_packet_audit_v1.md) | 不得冒充完整E/H authority |
| S13 | [Task039历史T3/T4](https://github.com/Rookie1234567/MyFEniCS/blob/f4073adabb91bffe5c3954b8ae8b63270efa3e15/docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/fixed_grid_full3d_reference.md) | 5nm、p6h10、10°压力负结果 |
| S14 | [Task040汇总](https://github.com/Rookie1234567/MyFEniCS/blob/50897c0c62d1f35abed5b196ae17997b2e7521cc/docs/task040_hybrid_side_factor_pc/outcomes/summary.md) | moving-PML、全谱、经济coarse与LOR |
| S15 | [Task040 Review V10](https://github.com/Rookie1234567/MyFEniCS/blob/50897c0c62d1f35abed5b196ae17997b2e7521cc/docs/task040_hybrid_side_factor_pc/review_report_v10.md) | 分清后续授权与已测结果 |

本报告不改变任何旧Task的最终分类，也不授权合并历史research branch。它的用途是让新任务一次性继承经验，不再要求用户或Codex重复重述全部历史。
