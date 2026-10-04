# Task39extra_para Review V6：当前容量边界

本文记录F5正式场、P2限域pilot和R48纯元数据规划的边界。p4准确粗修正是先在每个单元内消去内部未知数，再组装全局凝聚增广矩阵，并只建立一次准确MUMPS因子供QA与外层步骤复用。该矩阵的行数、输入矩阵存储条目、MUMPS因子填充/内存、数组载荷和进程树RSS必须分别报告。

| 阶段 | 当前结果 | 可得结论 | 不得外推 |
|---|---|---|---|
| F5，5 nm Si、p6/h4 q4 | 主审接受完整场、A6/FE/EH/600 modes、物理量、244个p4返回和资源清场 | `F5_FULL_REGRESSION_ACCEPTED`，仅资格化该离散模型和配置 | 不是连续体收敛证明；不替代P2或0.7 nm结果 |
| P2，2 nm Si、p6/h1.5 q4 | 主审28/28检查接受setup+16步限域pilot；A6第16步`0.35320202729663724` | `PILOT_COMPLETED_NOT_SOLVER_QUALIFICATION`；p4的34个返回通过原A4 Gate | 不收敛、不具备solver/physics qualification；RTA及checker未运行；不续算、不估收敛步数 |
| R48，0.7 nm/h0.5 nm候选 | 纯planner与完整动态外部模式清单：100×50×280个轴向单元、1,400,000 cells、32,060 modes | `TARGET_0P7NM_48H_NOT_ESTABLISHED` | 未建FE网格、全局矩阵、MUMPS因子或PDE；不代表内存准入、精度或48小时达标 |

R48复用已接受P2 resolved配置作为基底，只在内存中改波长、目标间距和动态外部模式策略。轴数、模式inventory和哈希见[容量compact](records/v6_0p7nm_48h_capacity_plan.json)；完整10,774,375字节模式清单留在ignored路径并由该记录绑定。候选cell数是planner实际轴计数结果；`54332×27`没有被当成测量。

## 周期识别后的场行数与P2控制

对x/y两个方向作Floquet周期识别、z方向保持开放的规则六面体网格，周期边/面实体数按以下整数公式计算。Nédélec H(curl)空间把电场未知量放在网格边、面和单元内部；周期约束将相对两侧重复的边/面未知量识别为同一个独立未知量。p6外层求解空间和p4粗因子空间都逐单元消去内部未知量、保留周期骨架行，再加DtN端口变量；但完整原A6作用、显式残差及局部恢复仍需要单元内部工作。完整周期独立场行数另外列出，不能只看未约束skeleton行。

```math
C=N_xN_yN_z,\qquad E=N_xN_y(3N_z+2),\qquad F=N_xN_y(3N_z+1)
```

```math
S_p=pE+2p(p-1)F,\qquad I_p=3p(p-1)^2C
```

```math
N_{\mathrm{periodic\ field}}=S_p+I_p,\qquad
N_{\mathrm{retained+ports}}=S_p+N_{\mathrm{external\ modes}}
```

这些是从规则网格拓扑和元素自由度数推得的独立整数计数，不是R48有限元空间或矩阵。P2公式控制与当前运行实数行数相符：

| 控制或候选 | 阶数 | 周期边/面实体 | 周期独立骨架行 `S_p` | 单元内部行 `I_p` | 周期独立场行 | 保留骨架+端口 | P2运行或planner的约束前场行 |
|---|---:|---:|---:|---:|---:|---:|---:|
| P2 34×17×94，54332 cells，3904 modes | p6 | E=164152；F=163574 | 10799352 | 24449400 | 35248752 | 10803256 | 实测约束前场行35594790 |
| P2 34×17×94，54332 cells，3904 modes | p4 | E=164152；F=163574 | 4582384 | 5867856 | 10450240 | 4586288 | 实测约束前场行10604228 |
| R48 100×50×280，1400000 cells，32060 modes | p6 | E=4210000；F=4205000 | 277560000 | 630000000 | 907560000 | 277592060 | planner约束前场行910586580 |
| R48 100×50×280，1400000 cells，32060 modes | p4 | E=4210000；F=4205000 | 117760000 | 151200000 | 268960000 | 117792060 | planner约束前场行270305720 |

P2运行的p6保留空间大小为10,803,256行，p4凝聚增广矩阵实际为4,586,288行；分别与P2公式控制相符。p4矩阵的输入存储条目为2,070,391,064个`owned-row getRow`条目。它不是MUMPS因子L/U填充量。P2 raw backend字段另记：INFOG一基键16–19均为1,091,654，键22为916,713 MB；键3、9、20、29的原值均为−54,415，属backend原始编码，单位/语义unknown，不是派生负NNZ。RINFOG一基键17/18为879,471.61023 / 1,058,655.467209。保留backend报告值，不自行换算字节或解码factor NNZ；准确因子symbolic/numeric/MatSolve次数为1/1/49。R48没有生成候选p4矩阵或因子。

仅作敏感度情景：若把916.713 GB的P2 backend报告容量值假设为随cell数线性增长，乘实际cell比例25.767503497后约为23.621 TB。这不是实测、下界、预测或容量资格，且不意味着backend字段已被解码成准确因子大小。

## 向量载荷、缓存与容量情景

FGMRES32若按约65个`complex128`数组、每个长度等于p6周期保留行加端口变量作载荷核算，每个复数16字节：P2控制为11,235,386,240字节（11.235 GB / 10.464 GiB），R48候选为288,695,742,400字节（288.696 GB / 268.869 GiB）。这是给定数组数与向量长度下的派生payload，不是当前运行已分配值或RSS；它不含其他同时存在的向量、预条件器、因子、矩阵、运行库或分配器开销。

P2的p6 buffer inventory如下。代码以Python ndarray对象id去重并累加`nbytes`；不同view可能仍共用底层buffer，因此不保证底层分配唯一。三类汇总存在交叠，禁止相加或当成整树RSS。

| P2 inventory项 | 字节 | 口径和限制 |
|---|---:|---|
| `unique_cache_bytes` | 108004276088 | object-id去重的数组载荷；与下面两项重叠 |
| `unique_port_cache_bytes` | 106341066752 | 包含每cell的Bi/Bt/Di/Dt/Bhat/Dhat/XiB/Hlocal及全局Hp/Hhat；可能混有mode一次项、平方项和共享底层buffer |
| `local_carrier_cell_payload_bytes` | 91060468992 | 按cell累加指定局部端口数组；内部shape不是统一尺度 |
| 实测process-tree RSS峰 | 1150080622592 | watchdog同时整树RSS实测；与数组payload/NNZ/factor估算分列 |
| 实测task swap峰 / global pswp增量 | 0 B / pswpin +24页、pswpout +0页 | 全局增量归因unknown；不能把global activity说成零 |

当前没有`Hlocal`、全局`Hp/Hhat`及其他端口数组的shape拆分，不能把所有数组统一乘cell比例或mode比例。只可把以下作为条件敏感度例子；它们不是上界、下界、RSS预测，也不能把重叠类别求和：

| 条件假设 | 仅供敏感度检查的算术 | 证据边界 |
|---|---:|---|
| `local_carrier_cell_payload_bytes`每cell字节完全不变 | 91060468992×25.7675≈2.346 TB | payload里含端口数组，因此每cell字节保持不变未经验证 |
| 整个`unique_port_cache_bytes`都只按模式数一次方增长 | 106341066752×8.2121≈0.873 TB | 混合项没有shape拆分；这不是预测 |
| 整个`unique_port_cache_bytes`都按模式数平方增长 | 106341066752×67.4384≈7.171 TB | 极端灵敏度例子，不是上界；实际只有未知子项可能平方增长 |
| 单个32060×32060 `complex128`稠密数组 | 16,445,497,600 B | 方阵载荷尺度示例；未证明某个具体对象就是此shape |
| stored NNZ/cell若维持P2水平 | 2070391064×24×25.7675≈1.280 TB | 24 B/条仅为complex128值+int64索引；假设未验证，不是矩阵、下界或内存预测 |

一般条件模型应先取得互不重叠的分量大小再使用：`B_R48 = 25.768*B_cell_constant + 8.212*B_global_mode_linear + 67.438*B_global_mode_squared + 1737.720*B_cell_mode_squared`。这些`B`基准目前unknown。Hlocal和Hp/Hhat可能含mode平方尺寸；不将一个模式倍率当作全部端口数组的统一倍率。准确p4因子、矩阵stored NNZ、数组载荷和process RSS保持分列。

## 材料与48小时目标

0.7 nm对应约1771.2028 eV。材料准备使用Henke表中1756.82和1785.24 eV的硅`f1/f2`行线性插值，并结合Si密度2.33 g/cm³及CODATA常数，按项目约定得到派生复折射率`0.9998851259969171 + i 4.325285938225562e-6`。该材料值是容量规划输入准备，不是直接CXRO calculator结果；插值点均低于约1839 eV的Si K边。来源：[Henke Si表](https://henke.lbl.gov/optical_constants/sf/si.nff)、[NIST质量衰减表](https://physics.nist.gov/PhysRefData/XrayMassCoef/tab1.html)、[NIST硅原子量](https://physics.nist.gov/PhysRefData/Handbook/Tables/silicontable1.htm)、[CODATA常数](https://physics.nist.gov/cuu/Constants/Table/allascii.txt)、[LBL X-ray Data Booklet](https://xdb.lbl.gov/xdb.pdf)。没有0.7 nm精度PDE、误差收敛或连续体资格。

48小时端到端目标分配setup 43200 s、solve 115200 s、恢复/检查/输出/清场14400 s。若分别假定256/512/1024个完整外层步，则solve预算要求每步平均不超过450/225/112.5 s；这只是预算条件。P2在16步的A6仍为0.35320202729663724，不能推断所需总步数或R48总时长。R48/Z没有启动新FE、全局矩阵、symbolic/numeric factorization、PDE或低内存p4逆实验。

## 历史native R1/R2 frontier（2026-09；保留历史分类）

以下是Review V6前的13.5 nm native attempt3记录，不再表示当前V6状态。attempt3的own-solve与independent output gates已通过，但`BALANCED_OUTPUT_AUTHORITY_LIMITED`和`WSL_FULL_FIELD_COMPARISON_PARTIAL`仍关闭完整R1资格；不能改写成完整native场资格。R2仍因global swap归因未决而关闭。旧WSL V5资格仍限于其自身环境，不能替代工作站资格。

| 对象 | 历史状态 | 当时可得结论 |
|---|---|---|
| native R1 13.5 nm Si / p6h10 | attempt3 own-solve和independent output gates通过；完整R1关闭 | `BALANCED_OUTPUT_AUTHORITY_LIMITED`与`WSL_FULL_FIELD_COMPARISON_PARTIAL`；32 GiB小案例cap内完成p4 LU与62步，仍不称完整复现通过 |
| native R1 matched reference | `NATIVE_OWN_PASS_MATCHED_REFERENCE_WSL_ARRAYS_PARTIAL` | 24 GiB planning admission、80通道/功率/场比较通过；不称完整WSL全场复现 |
| R2 13.5 nm notch与匹配native reference | `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED`，attempt1已清场 | 到iteration3；没有own资格、E/H、完整80复幅值或能量比较资格 |
| S5 W / p6h4；S3 W / p6h2.5；S2 W / p6h1.5；G | `NOT_RUN_BY_PREVIOUS_GATE` | 无当时的短波计数、symbolic/numeric上界；不能从2 TiB总容量推出安全或精度 |

历史阶段与原V1结果见[复现报告](reproduction_13p5nm.md)。它不覆盖上述F5、P2和R48的新scope结果。
