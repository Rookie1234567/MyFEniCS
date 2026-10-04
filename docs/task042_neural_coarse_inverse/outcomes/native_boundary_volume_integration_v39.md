# V39：native边界／有限体积接口集成，部分通过和真实失败

把边界积分用到体积求解，需要先把体积有限元系数准确读到边界，再把边界力加回去。`E`与其共轭转置`Eᴴ`完成这一步；稀疏实体变换代替全表面拟合。局部内部恢复还要把右端非零载荷的特解加回来，不能只检查零载荷。本轮前一部分通过，后一部分在真实运行中遭遇软件错误，有限修复与准入拒绝均保留。

| Review V36阶段 | 已执行证据 | 分类／未完成原因 |
|---|---|---|
| 5.1 数据合同和checker | V38最终全32060输出的对应48项，literal独立复算，输入／缓存不可变与容量拒绝 | PASS；旧oracle独立保存，无继承或monkeypatch |
| 5.2 native抽取／散布 | 四类完整原882基、20hex，12固定mode；同实体一次owner、T_apply方向、Floquet主从、共轭对偶 | 四类见证资格；完整目标native编号仍unknown |
| 5.2 存储语义／内部支持 | 20独立存储／物理展开副本、六面完整Basix原基及原native C/D | 保存数组重算通过；未删内部浮点残项 |
| 5.3 有限体积setup | q15原体积kernel、4类450行内部LU、单个8hex native sparse oracle实际尝试 | actor失败，精确setup差值和缓存payload未保存；PARTIAL |
| 5.3 非零f_i/g、压缩RHS、恢复及独立native恒等式 | 接线已最小修复，合成小矩阵／实际公共carrier回归通过 | 真实native检查NOT_RUN_AFTER_IMPLEMENTATION_FAILURE；完整重放未准入 |
| 5.4 可调用部署／目标矩阵 | 冻结参数／模式／几何，真实boundary接口，隐式Hp及合法volume callback，生命周期与容量表 | 边界可消费；零volume演示不是物理体积资格 |
| 完整0.7nm前向解／2TB／48h／NN20% | 无完整mesh、冷求解、场／功率、h/p与外部截断验收 | NOT_QUALIFIED／NOT_DEMONSTRATED，不从组件继承 |

## 实际数据与独立判定

原目标period50×25nm，z−10..130nm，Si块17×25×120nm，0.7nm、1°grazing、s、双Floquet／DtN；材料为canonical `SI_OPTICAL_CONSTANTS_USER_20260929_V1`。source标签0.699999988只对nominal0.7显式alias，n实虚为0.999885140474／0.00000432477054，epsilon=n*n，air n=1、mu=1。p6 Legendre variant，边界q30与原位相／参考面不变。四类见证沿用目标宽度与周期相位，人工内切面没有真实边界条件，不能称局部物理解。

| 片段 | native storage行 | 内部行 | MPC slave行 | 紧凑边界行 | E非零项 |
|---|---:|---:|---:|---:|---:|
| min_ordinary | 3360 | 1800 | 0 | 324 | 3798 |
| max_ordinary | 3360 | 1800 | 0 | 324 | 3798 |
| x_seam | 3528 | 1800 | 168 | 324 | 324 |
| xy_corner | 7056 | 3600 | 660 | 624 | 624 |

`E`从DOLFINx实体／cell permutation和MPC literal重建；同边／面完整高阶矩不拆，corner不重复。新adapter无需小线性solve，最大实体变换60行；已有边界多项式变换含7×7有界solve，单列区别，不称全流程无任何线性解。生产映射与checker分别实现literal方程，破坏排列、相位、mode库存、数组shape、非有限、unit norm和callback dual slave的反例均拒绝。

常规forward／adjoint／modal／振幅／dual最差相对差1.3623018728143374e-12，门1e-10。两路径比较保存完整向量、分子与分母，见component_checker；一般输入没有被当成求解收敛。精确零输入输出精确零。旧未归一化纯内部输入absolute L2为6.423614109330073e-12，超过1e-12，FAIL仍在原source和raw；新unit-L2输入在运行前登记，相同1e-12门下最大2.31700717997397e-13。没有提高门、裁剪C/D或改物理方程，checker另核对原输入范数。

六面q30保留882列原Basix数组后才按拓扑选450内部列；实际Piola宽度缩放后切向最大4.898176645237146e-13。native C内部残项最大1.3012535225303092e-11、D最大6.101591248222376e-14，在1e-10系数审核门内，不把浮点值硬设0。20对计算存储与物理副本另存：计算slave0，物理展开保留复周期系数；恢复误差必须用F(e)−F(0)，小测试含非零内部特解和port RHS，但真正native非零RHS恢复尚缺。

## 体积失败、修复与为什么不完整重放

`COUPLED`实际运行912.5918812180171s，在原kernel／局部4class建立后，构造`P6CellCondensedAction`时抛出`ValueError: direct B carrier contains an MPC slave or unknown trace row`。driver把所有非内部storage行都当独立trace，其中含660个MPC slave；原公共API正确要求`owned_active_original_dofs`。最小修复只改Task042接线并严格拒绝遗漏行上的非零载荷，保留公共语义。真实公共方法正例／旧坏行反例及非Hermitian40port小测试通过。

原volume形式是curl-curl减complex mass，轴对齐仿射且cell内常材料。p6分量在参考轴上的最高多项式次数≤6，两基相乘最高单轴≤12，curl不提高次数，故体积q15足够积分这些多项式项；这与含Fourier指数的边界q15负结果不同。driver在失败前已进入q15/q17比较之后的接线，但未原子保存比较标量或tensor，**只作为control-flow事实，不授予独立数值PASS**。唯一8hex小CSR曾临时装配，未因子化／未保存，完整目标fine矩阵没有构造。

失败安全记录实际4个内部LU class，write-ahead上界8，累计构造36hex；局部LU／恢复／Schur规划112548672B<256MiB，实际payload因失败未保存，unknown。原C/o/so实际合计196161322B，小于1.5GiB新JIT限额；峰值包含编译和局部对象，不只主进程。

重放准入时native累计964.9699936029501s/1200s，余235.03000639704987s。同路径kernel生成后至class建成的文件时间戳跨度311.419277446s已大于余量；它是derived观测跨度，不是精确保存的setup子计时，也不是一般不可计算证明。剩余慢oracle预算不足以可靠完成同一构造及后续验证，故记录`COUPLED_REPLAY_NOT_ADMITTED_TIME_MODEL`。后来只对已有数组／同Basix做7.907852472s六面检查，native最终累计972.8778460749891s，仍不刷新上限。日历窗口没有用尽，不需要为跑满预算继续重建。

没有保存真实f_i/g恢复向量、local内部平衡、压缩RHS和两路径`r_native=r_FE-B*r_port`；全部标缺失。CHECK在缺body时仍独立审核adapter，状态是`BOUNDARY_ADAPTER_SAVED_ARRAYS_QUALIFIED_BODY_PARTIAL`。DEPLOY明确用零体积callback，仅验接口，不隐含求解或装载任何旧全局因子。源码修复与小测试不能替代本native资格。

## 可调用接口、作用约定与生命周期

```math
A_{native}x=V_{native}x+E^H B D E x,\qquad
\begin{bmatrix}V&B\\-D&I\end{bmatrix}
\begin{bmatrix}u\\\alpha\end{bmatrix}
=\begin{bmatrix}f\\g\end{bmatrix}.
```

这里D已除以projection denominator，B对应原modal traction；未归一化D需要另写对角换算。Hp=I用`hp_apply`隐式表达；projection H、未凝聚Hp、凝聚Hhat不同。不会为32060端口生成16,445,497,600B稠密单位矩阵。

| 接口／输入 | 输出／约束 | 验收范围 |
|---|---|---|
| NativeBoundaryAdapter.extract(x) | 冻结compact primal，complex128 finite；native independent slave必须0 | 四类MPI1见证 |
| NativeBoundaryAdapter.scatter(w) | 共轭MPC对偶回写，slave0；无重复owner | 四类MPI1见证 |
| DirectionalBoundaryAction.apply／recover／modal_rhs | 原q30边界forward／adjoint／归一化振幅／牵引 | V38全库存＋V39有限native接线 |
| CoupledNativeBoundaryAction.apply(x,adjoint=...) | callback体积作用＋边界作用；体积输出shape/dtype/finite/dual slave检查 | callable通过，实际native体积组合PARTIAL |
| hp_apply(alpha) | 按输入返回单位作用，不生成稠密Hp | demo12mode；API支持完整32060 |
| 原reduce_rhs／recover_storage | 有内部特解的压缩RHS和恢复 | 小测试通过，真实native未完成 |

部署输入几何／ordered mode与数组采用不可变深快照；q、几何、模式、orientation或MPC身份变更必须新建对象，旧cache不能静默沿用。构造前容量拒绝；actor退出释放volume callback、adapter、Fourier cache。demo保存数组读取／hash/setup3.368227040s，完整forward含extract/scatter0.054396651s，adjoint0.070874979s，modal/amplitude/隐式Hp0.105054677s，pack/hash/IO0.007968498s。另保存demo三次extract累计0.001154014s、三次scatter累计0.006550499s及边界project/scatter子计时；这些嵌套时间不再次加入监督总wall，不能从含IO的patch总时长反推其他阶段成本。

四类成功adapter各6次extract／36次scatter，合计24／144，包含构造12mode C/D列的调用。boundary cache1,462,728B、共享full layout10,596,096B、稀疏E及EH55,688B、一个compact boundary向量6,054,912B；不是完整体积solver峰。MPI2/4只做合成共同失败fixture，真实native仅MPI1，不能宣称分布式ownership合格。

## 全过程资源与原尺寸剩余成本

| 口径 | measured或derived值 | 限制／解释 |
|---|---|---|
| 正式组件含失败 | 992.2815476800315s | ≤5400s；属于总有载内，不重复相加 |
| 新native／慢oracle含六面辅助 | 972.8778460749891s | ≤1200s；失败/JIT/local LU全部计费 |
| 同时整树采样峰／own swap | 2073407488B／0 | 0.5s watchdog；FEwarn6/hard8GiB，auxwarn1/hard2GiB；无可写独立cgroup |
| native累计／局部LU class | 36hex／实际4，上界8/16 | 不把失败重建清零；最大内部行450 |
| 新native JIT | 196161322B | C/o/so/缓存标志，不重启旧q60；无压缩副本删除科学证据 |
| 全部监督、probe、bootstrap、交付 | resource_costs_v39.json | 独立结算，不双加上述子计时；未监督实现／一般元数据unknown |
| 历史实测已知下界 | 78517.88650908363s＋本轮监督实测 | 完整历史unknown，保留原口径；保守probe/bootstrap费用不伪造为历史实测 |

现场每次选空闲核并避开忙SMT，实际CPU0/2/7/9等见各准入回执；没有沿用固定CPU14。所有成本shared-workstation，数学／BLAS getter1，GPU不用。整树及PSI监督未观察持续full压力，未改邻任务；没有可比邻任务阶段记录，性能影响INCONCLUSIVE，不承诺绝对零干扰。最终storage与所有准入／resource原始记录归档，新增≤2GiB、Task artifacts≤20GiB、free≥50GiB、证据余量≥256MiB均单列。

完整目标条件规模是530856cell、105298704canonical trace、238885200interior、345771066storage行；完整native mesh尚未建立，不能把boundary公式行号当DOLFINx row IDs。一份完整complex128向量5532337056B。若逐cell同时存LU／恢复／Schur，条件载荷4956275464704B>2TB；体积class共享或矩阵自由实现是否消除此增长仍unknown，四片段class不能代替完整库存。solver同时向量数、K、体积／PC作用、全setup/recovery/audit/IO仍缺，不能将0.08s边界成本外推为完整48h解。

```math
T_{total}=T_{setup}+K\,(T_{volume}+T_{boundary}+T_{adapter}+T_{PC})
+T_{recovery}+T_{audit}+T_{IO},\qquad
K\le\frac{172800-T_{setup}-T_{recovery}-T_{audit}-T_{IO}}
{T_{volume}+T_{boundary}+T_{adapter}+T_{PC}}.
```

右式只是条件预算关系，不是测得的迭代次数。NN没有运行，合格完整非NN基线也没有，因此同正确性下完整耗时或同时峰至少20%改善且另一项合规的神经门仍NOT_DEMONSTRATED。传统积分／坐标接线收益不能写成神经收益；原尺寸完整残差≤1e-6、场／振幅≤1e-4、R/T/A/A_volume≤1e-5、单通道功率≤1e-6、能量≤1e-5没有被本组件通过替代。

## 原尺寸就绪与证据入口

| 必要层 | 当前资格 | 剩余缺口 |
|---|---|---|
| 完整32060 q30边界 | QUALIFIED_MPI1（V38复用） | h/p与mode截断不继承 |
| native片段adapter／MPC存储 | QUALIFIED_ON_FOUR_WITNESSES | 完整目标native rows与distributed ownership |
| 同物理有限volume tensor／仿射恢复 | PARTIAL／NOT_QUALIFIED | carrier修复后的真实非零f_i/g恢复、增广／native独立恒等式及class缓存 |
| 同物理完整体积引擎 | NOT_QUALIFIED | source／物理／mesh／basis／MPC hash、forward／adjoint、class库存与生命周期 |
| 完整冷求解／场与功率 | NOT_RUN | 原残差、E/H/curl、40旧micro≠32060目标、全复通道与能量 |
| 2TB／48h／NN20% | NOT_QUALIFIED／NOT_DEMONSTRATED | 全对象共存与完整总耗时／公平NN对照 |

dot只读发布身份仍077ec9c8386c976da232093779279fb9d1a93033，材料n差2.991716531811656e-8、缩小notch／532mode、canonical／恢复／runtime／raw缺口见原consumer_v37；未修改dot、调用其solver或factor，也未把缺包设为自身adapter前置。目标下一步是匹配体积引擎的真正集成，不继续追加相同边界轮次。

[run与真实source](records/run_index_v39.json) · [数组／成员hash](records/array_inventory_v39.json) · [全部raw](records/raw_evidence_index_v39.json) · [checker](records/component_checker_v39.json) · [内部trace](records/internal_trace_checker_v39.json) · [storage副本](records/storage_copy_checker_v39.json) · [成本](records/resource_costs_v39.json) · [准入／停止](records/gate_decisions_v39.json) · [消费包](records/deployment_package_v39.json) · [完整就绪矩阵](records/integration_readiness_v39.json) · [测试](records/tests_v39.json) · [变更](records/changed_files_v39.json) · [分组](records/selective_merge_manifest_v39.json)。

唯一下一建议：补齐匹配体积引擎的有限非零RHS native组合与恢复资格，先保存class/局部oracle及原始子计时再推进原尺寸容量。全部旧task/review/response/raw保留，V24–V38不重开；本轮集中交付closed、清场、clean/upstream0/0后交回审阅，不扩模、不merge。
