# Task40 Review V2 campaign 收口

## 阶段结论

| 阶段 | 对象与方法 | 结果 | 含义 |
|---|---|---|---|
| P1 | Review V2原M0 G0/G1保存场公共子单元体积与独立curl(E)比较 | 工程场/curl门失败：散射E约2.6113%，散射H及scaled curl约2.7498%>1%；official power h gate通过 | P1是M0体积/curl负结果；不能被旧R5固定样本通过覆盖 |
| P2 | 复用六个真实参考curl/质量张量，再按单元精确几何组合；F1做G1 M0同离散集成 | F1同离散Gate通过并用于剩余campaign；G0原paired artifact仍为NOT_QUALIFIED | 不改变方程，不改写G0历史失败 |
| P3 | 固定G0网格比较DtN模式M1到M2 | 在披露为事后固定的显著性规则下，有限比较稳定，选择M2；M3未运行 | 不等于真实连续边界的截断误差已被界定 |
| P4 | G0 F3与G1 F5用共同340个M2 key比较 | 显著模式振幅1.55561%>1%；固定样本最大2.74361%>1%；体积scaled curl最大2.75037%>1%；官方功率gate通过 | 跨网格同M2场/导数工程Gate失败 |
| P5 | 固定0.7 nm波长，扩大几何电尺寸 | E1残差通过，分类为电尺寸增长诊断；E2原worker在输出sample检查失败，v3保存场离线恢复完成 | 离线输出恢复不追认原worker成功 |
| P6 | 三种真实材料tag的G0 p6局部单元；M=80/340/3904合成重采样动作 | 局部块与非零RHS恢复闭合通过；固定16列批次的双遍动作闭合通过 | 3904仅为通道向量压力测试，没有完整高M物理模型或全局因子 |
| P7 | 下一阶段方案 | 冻结一个波传播感知的有界子域与递归matrix-free接口粗校正设计 | 只设计；没有新求解器、PDE或因子 |

P1与P4都使用共同子单元体积/curl方法，但截断集合不同：P1是原M0，P4是F3/F5同M2。P1散射E约2.6113%、散射H及独立scaled-curl约2.7498%超过1%；P4散射E约2.6119%、散射H及scaled-curl最大约2.7504%超过1%。旧R5 `h_agreement_v1.json`只是固定坐标采样，曾以`H_AGREEMENT_PASS_ENGINEERING_ONLY`通过约0.4%的工程样本门；它不替代P1公共体积/curl负结果。P1与P4官方功率差都小于0.001，但这不能宣称局部场和导数稳定。

## 模型总账与身份

run_id是稳定配置名；目录中的UTC时间戳只是运行目录名。表内official R/T取DtN port modal amplitudes，`A_volume`取材料区域体积分吸收。`power_metrics_3d.json`标记为`diagnostic_eh_fourier_probe`，不用于替代正式DtN R/T。F3源码SHA为`a43f7f76a0df0f4440b77834846973b2de7ea3a8`；F5/E1/E2为`63dd2a7378153f2ab5094eb5e7a98d05758a39bf`；F1为`1d7d790088d6ea0f30aed2ef1073fb1b86e68155`；F2最终尝试为`37635226002787beb26a24baba3a8da333027239`。完整source/input/physical/native ordered-mode SHA及每个raw字段的路径和文件SHA见`records/run_index.json`、`records/resource_components_v2.json`、`records/electrical_size_v2.json`。

| 模型 | 网格 / 模式 | full A6与结果分类 | 正式DtN R/T；A_volume | workflow / KSP (s) | process-tree RSS / swap | p4 condensed factor rows / NNZ / INFOG29 |
|---|---|---|---|---:|---|---|
| F1 G1 M0 | 880 cells / M80 | 8.648911990579289e-7；同离散G1 M0资格通过 | 0.07612407122165808 / 0.9057692393459813；0.018106713007727038 | 2252.535 / 1674.835 | 6,891,311,104 B / 0 B | 75,280 / 28,705,330 / 182,769,024 |
| F2 G0 M1 | 336 cells / M180 | 9.572475880327875e-7；worker exit4，authority checker将180个合法模式硬编码成80，official_result=false | official_result=false；raw/offline DtN R/T/A_volume=`0.07565188084569026/0.9062068016471507/0.018141266883419625`，保留并用于P3 | 1123.500 / 809.586 | 3,867,545,600 B / 0 B | 29,172 / 11,033,364 / 55,305,544 |
| F3 G0 M2 | 336 cells / M340 | 7.593610432084708e-7；离散解与一致性通过，authority-limited | 0.0756519019957502 / 0.9062068705222379；0.018141268088495303 | 1174.947 / 823.922 | 4,006,539,264 B / 0 B | 29,332 / 11,293,034 / 56,763,048 |
| F5 G1 M2 | 880 cells / M340 | 8.735322490524255e-7；离散解与一致性通过，authority-limited | 0.07612407127067708 / 0.9057692398169153；0.018106713068250728 | 2448.071 / 1797.975 | 7,754,170,368 B / 0 B | 75,540 / 29,765,186 / 186,881,032 |
| E1 q=1.25 | 760 cells / M588 | 9.781668525522113e-7；电尺寸增长诊断点 | 0.06235653736791684 / 0.9159264755357902；0.021716951725654188 | 4580.375 / 3722.193 | 10,650,341,376 B / 0 B | 65,708 / 26,681,978 / 164,865,416 |
| E2 q=1.5 original | 880 cells / M700 | 9.793073227317083e-7通过残差线；原worker exit4且`official_result=false` | 原run没有official输出；v3保存场恢复值仅作离线恢复：0.05116886160983426 / 0.9239410512847893；`A_volume=0.02489005360260621` | 7692.028 / 6776.587 | 11,349,196,800 B / 0 B | 75,900 / 31,287,060 / 182,925,800 |

F1的p4完整存储空间是180,240行；实际凝聚因子只有75,280行，不能把前者称作factor rows。E2的KSP 6,776.587 s、180步、converged reason 2来自保存的原始阶段事实；E2的v3另重建p6 mesh/space与matrix-free A6动作并做一次A6核验，但没有构造全局AIJ/H6、p4 factor、KSP或solve。E2 `R00_p=7.978116094818559e-19`。E1/E2固定0.7 nm波长而放大几何，属于不同物理模型诊断，不是同一模型的h收敛序列；这些缩小连续介质模型也未验证真实原子尺度硅器件物理。G0/G1网格和有限模式序列不构成连续极限证明。

workflow、独立watchdog、KSP、p6 build、p4 symbolic/numeric及official postprocess是不同计时边界，不得相加。PSS为`null`。E2原postprocess独立边界unknown。分阶段MUMPS内存、Native matrix payload、inventory、workspace、进程树RSS使用不同口径；不得互换。

## 截断与两组跨网格比较

- **P3模式截断（同一G0离散）**：M0→M1是手动扩展模式包络：保留原有80个传播通道，并加入扩展包络的其余模式；同时跨越已经采用的P2 reference-metric配置，因此是组合诊断，不能把全部变化只归因于M。下列体积场/curl数值来自两个完整保存场在公共物理子域的比较，不是“80模式内部场/curl误差”；80个共同传播通道只限定通道向量比较的匹配集合。体积场/curl最大变化为`E_total=4.08153e-6`、`E_scattered=2.77346e-5`、`H_total=1.43769e-5`、`H_scattered=9.76909e-5`，固定样本最大`6.04965e-6`，显著模式最大`6.07756e-5`。官方`|ΔR|/|ΔT|/|ΔA_balance|/|ΔA_volume|`为`8.36515e-8/5.47961e-8/1.38448e-7/9.83171e-9`。
- **P3 M1→M2（同一G0离散）**：最大六场变化为`E_scattered=1.62008e-6`、`H_scattered`与独立scaled curl为`5.91111e-6`；固定样本最大`2.52206e-7`，显著模式最大`9.47063e-5`；官方四项差为`2.11501e-8/6.88751e-8/9.00251e-8/1.20508e-9`。这些有限比较低于适用门限。all-80探索差异先被查看，之后才固定M0 `power_ratio≥1e-8`显著规则；报告保留事后确定的说明，不称作预注册。按此有限规则选M2，M3未触发。该结果不证明M0原80模式充分，也未界定真实连续边界截断误差。
- **P1原M0公共子单元体积/curl比较**：原样compact为`records/p1_m0_volume_h_agreement_v2.json`，SHA256 `9d72efd7f21771c7fd0cc779b7cfb0f9272734fe9cbe1757a014d127e4422925`。它比较旧G0/G1 M0保存场，共1344个共同子单元；物理域总场E/H相对差`0.375014%/0.394900%`，低于1%；散射E为`2.611273%`，散射H和独立scaled-curl散射量均为`2.749777%`，超过1%。offline checker耗时`436.5178109759581 s`、自身RSS峰`620851200 B`；无新PDE/operator/factor/KSP。official power差`ΔR=0.00047209757074695435`、`ΔT=0.00043763587092637835`、`ΔA_volume=0.00003454432192872073`，均通过0.001门。
- **R5历史固定坐标样本（与P1/P4体积记录分开）**：`records/h_agreement_v1.json` SHA256 `27cc385f28cedf565687ca80f88e7f5123e2ec58d87eb5f0fd4cfd25de4fe158`；状态`H_AGREEMENT_PASS_ENGINEERING_ONLY`，固定样本总场/curl最大约0.4%。这只证明所存坐标样本的有限比较通过，不代表公共子单元体积/curl或连续收敛。
- **P4本轮M2跨网格比较**：F3/F5使用完全一致的340个有序M2 key。显著传播模式最大振幅变化`1.555605%>1%`；固定4000样本的六场最大`2.743612%>1%`；精确共同子单元体积比较的direct `curl(E_FE)`/scaled-curl最大`2.750374%>1%`。P4总场E/H变化约`0.375102%/0.394986%`，两者都通过1%；散射E为`2.611883%`，散射H及其独立scaled-curl最大`2.750374%`，后二者失败。散射H/curl峰值还分别见物理域`2.750374%`、void box `2.789004%`、grating `2.787459%`、substrate `2.759137%`。因此不应写成“总场E/H失败”或“所有curl量失败”。
- P4正式DtN功率来自`numerical_output/dtn_port_power_metrics_3d.json`，SHA分别为F3 `71ccab07b6c9c563f26b5d397cc109aee5b88b5ece203e79890cf5b5180bd3a3`、F5 `e6c3618fbd1415c50e8b38a1eac4a5ca36e121a2072d5d9eff5ca65e62e42c9b`；A_volume由正式worker volume字段提供。F3→F5的绝对`ΔR=0.0004721692749268813`、`ΔT=0.0004376307053226558`、`ΔA_volume=0.00003455502024457546`，均低于0.001。`power_metrics_3d.json`是diagnostic_eh_fourier_probe，不是正式DtN R/T。P4只是保存场离线后处理，未启动新PDE、operator、factor或KSP。
- P1原M0公共子单元体积/curl场门失败；通过的旧证据只有R5固定坐标样本门。P4是另一组F3/F5同M2跨网格场/curl比较，也有独立失败项。M0→M1→M2的有限模式包络诊断与G0/G1同M2的网格场Gate回答不同问题，不能互相替代。G0 M2 direct exact-reference缺失；F1是G1 M0同离散reference，不可冒充该项。

## E2原失败和v3恢复

E2正式worker完成求解后发现输出采样配置24×24不满足至少25×7的diffraction sample合同，exit code为4，official_result=false。A6 pre/post=9.7930732e-7虽通过1e-6残差线，也不能替代完整worker输出Gate。v3使用输出恢复输入SHA `4c3b70a237d19325a46825526a85ea045e6d3f665a5a6ad4d43781e082461828`，只把保存输出x采样数从24改为25，y仍为24；它复用同一物理模型和已保存场，完成15项authority checks、一次native A6 action及R/T/A_volume恢复，A_volume相对原存储差为0；`R00_p=7.978116094818559e-19`。v3重建p6 mesh/space，执行一次native matrix-free A6 action和streaming DtN核验；没有创建global AIJ/H6、p4 factor、KSP或solve。没有新PDE。原worker失败保持不变。v1/v2失败均保留在repair ledger，恢复不追认原worker成功。

## 两级资源账

| 一级campaign账 | 同时进程树RSS峰 | inventory ledger峰 | workspace峰 | 口径说明 |
|---|---:|---:|---:|---|
| F3 | 4,006,539,264 B | 4,893,944,084 B | 1,753,175,672 B | RSS、对象库存和workspace分别记录，不相加 |
| F5 | 7,754,170,368 B | 7,875,636,436 B | 1,992,355,256 B | 三种口径不相加 |
| E1 | 10,650,341,376 B | 10,428,890,376 B | 6,030,542,648 B | inventory不是进程树RSS |
| E2原run | 11,349,196,800 B | 11,544,260,760 B | 6,091,623,992 B | 原worker失败仍保留 |

二级资源组成记录见resource_components_v2.json。全局p4/MUMPS因子仍是主要规模风险：F3为29,332行、11,293,034 NNZ、INFOG29 56,763,048项；F5为75,540行、29,765,186 NNZ、186,881,032项；E1为65,708行、26,681,978 NNZ、164,865,416项；E2为75,900行、31,287,060 NNZ、INFOG29 182,925,800项。

P6抽取三种tag各一个真实单元。每单元p6 tensor为882×882，其中内部450、trace432；三次非零RHS恢复closure为1.43e-11至2.35e-11，低于1e-10。M3904每tag双遍动作约3.739至3.773秒；已知numpy backing下界38,432,904 B，显式数组情景上界40,542,856 B。动作按16列批次流过，未建M×M块；显式上界不含opaque BLAS/LAPACK workspace。P6自身RUSAGE RSS峰455,610,368 B，任务swap未独立采样，不能把两次VmSwap=0采样写成峰值0。

本轮没有从小模型外推约2 TB容量，也没改变工作站cap。全局p4稀疏factor仍是目标尺寸的主要已知风险。

## P7唯一下一阶段设计：波传播感知的有界子域与递归matrix-free接口校正

通俗说，先在尺寸封顶的小块里准确处理局部场，再让小块边界上的切向电场和旋度通量交换；跨层粗校正显式携带真实Floquet传播方向和近截止波，使长距离传播与反射能穿过多个小块。它只拟改变未来预条件器的接口处理阶段，不改Maxwell方程、离散、材料或原端口定义。以下是可审查的提案边界；没有实现、资格化或运行。

### 精确接口算子与一次PC动作

对第`ℓ`层patch `j`，局部内部消去后的Schur作用为

`S_{ℓj}=A_{tt}−A_{ti}A_{ii}^{−1}A_{it}`。

原增广物理方程中的端口/左右耦合块记作`H_p`及其独立左右块（例如`B`与`D`）；它们按现有精确MPC dual/Floquet复相位语义保留。将这些原始左右端口贡献经过原有消去与trace映射后，嵌入到与`S_ℓ`同尺寸的增广接口+port坐标，所得整体贡献记为`Ĥ_ℓ`。`Ĥ_ℓ`包含全部左、右端口贡献，不只是port-port角块；`H_p`与`Ĥ_ℓ`处于不同层次/坐标时不得直接相加，也不得把端口贡献计数两次。

精确接口operator为

`S_ℓ = Σ_j T_j^H S_{ℓj} T_j + Ĥ_ℓ`。

`T_j`是global-to-patch trace gather，`T_j^H`是使用原MPC/Floquet复共轭相位的dual scatter；局部凝聚项按零扩展进入同一增广接口+port坐标，因此它与`Ĥ_ℓ`维数相同后才相加。物理左右耦合块满足`D`可独立于`B^H`；这是原非对称物理块的关系，与下面粗层的限制/延拓选择是两个不同概念。公式定义原算子，任何PC权重都不能改变它。

近似PC的局部加性组合另用patch weights `W_j`：`z_loc=Σ_j T_j^H W_j B_j^{-1}T_j r`。其中`B_j`是patch内有界局部问题，最多64,000个未知数，使用局部内部精确LU形成局部Schur响应；一次PC对每个活动patch最多一次局部solve/sweep。`Σ_j T_j^H W_j T_j=I`只用于重叠patch correction的partition-of-unity组合，不用于重写或加权原`S_ℓ`。`W_j`具体构造和local interface solve的成本仍须在下一阶段小G0资格化。

### 粗层映射、波迹和有限迭代

本设计明确选用Galerkin配对`R_ℓ=P_ℓ^H`：`P_ℓ`把粗系数延拓到细接口坐标，`R_ℓ`使用该坐标下的复共轭转置限制残差，`S_{ℓ+1}=P_ℓ^H S_ℓ P_ℓ`。在canonical MPC/Floquet接口坐标中执行准确复相位映射。`S_ℓ`即使非Hermitian，Galerkin粗算子仍可非Hermitian；选择`R=P^H`不要求`D=B^H`，也不把物理左耦合块强行改成右耦合块的共轭转置。

`P_ℓ`的波迹列由冻结完整port inventory中的全部传播Floquet模式及两个切向极化产生：用现有端口模态到边界切向场/旋度迹的映射生成迹列，再通过精确MPC/Floquet owner/phase映射放入接口坐标；不得按P3事后显著性删除冻结的传播端口。另加入衰减长度不短于patch直径的近截止倏逝波迹，以及每个patch、每层最多32个局部广义接口特征向量。后者最多用64步block-Arnoldi生成，block width≤16；每层粗向量总rank≤20,000。若冻结物理迹与这些硬上限不能同时满足，受控停止，不删减物理端口。

一次PC先计算`z_loc`，通过精确且包含全部端口项的`S_ℓ`求`r₁=r−S_ℓz_loc`，再取`r_c=P_ℓ^H r₁`，递归求一个粗修正`e_c`并返回`z=z_loc+P_ℓe_c`。每层最多一次局部solve/sweep和一次递归粗校正；总层数≤4。终层系统维数≤20,000，终层迭代最多200步；外层FGMRES `max_it≤2048`。这些是拟冻结的有限工作量上限，不代表已测收敛或容量。

### 资源封顶和正确性对照

| 提案项 | hard cap（均待下一阶段现场资格化） |
|---|---:|
| 局部patch未知数 | ≤64,000 |
| 同时活动局部因子 | ≤8个；每个≤32 GiB |
| 所有局部factor+workspace bucket | ≤0.75 TiB；但`8×32 GiB=256 GiB`是更严格的并发子上限 |
| 接口/port/Krylov同时内存 | ≤0.5 TiB |
| geometry/JIT/output/其他同时内存 | ≤0.25 TiB |
| 求解进程树RSS | ≤1.5 TiB |
| 层数 / 每patch局部向量 / Arnoldi步数 / block width | ≤4 / ≤32 / ≤64 / ≤16 |
| 终层维数 / 终层步数 / 外层步数 | ≤20,000 / ≤200 / ≤2,048 |
| 约2 TiB设计主机系统余量 | ≥0.5 TiB |

2 TiB只是下一阶段设计场景，不是容量预测，也不改变本轮笔记本已资格化资源线或工作站cap。各内存项按真实生命周期并发核验；不同阶段历史峰值不能相加代替同时RSS。mesh/type数量、patch并发与重叠、实际高M耦合稀疏度、不透明库workspace和目标尺寸p4因子仍未知。

A6原方程相对残差每8步记录/检查一次；允许中间值高于门限，只有最终和post-release残差必须≤`1e-6`。接口闭合门≤`1e-8`；精确映射、operator、Schur和场恢复identity≤`1e-10`。随机向量用于核对精确映射、operator动作和Schur身份；不要求近似PC在随机向量上复现准确全局p4逆作用到`1e-10`，因为那会把候选变成同一个昂贵精确逆问题。随后在同一小G0离散上，与准确p4对照完整求解的full A6、恢复场、官方observable vector和工作量。F1只是一场G1 M0 reference；G0 M2 exact-reference目前`unavailable`，不能混用F1顶替。所有冻结物理门限保持不变。

旧42个完整宏块/强逆方向不改名重做：完整宏块精确解把跨块传播留给外层迭代。Task39 V12记录中，64步后full A6=`0.7666389832389989`；node32/64场相对差=`0.9384007607744688/0.9488237463600627`，均明显大于`1e-4`；128次p4 I4作用中0次达到`1e-4`，旧strong-inverse扫描所有strong actions均未通过。精确入口为[`physical_macro_v12.md`](../../task039_extra_physical_multilevel/outcomes/physical_macro_v12.md)和[`physical_macro_v12_compact.json`](../../task039_extra_physical_multilevel/outcomes/records/physical_macro_v12_compact.json)。候选机制保留准确局部响应，但新增真实传播粗空间与有界递归matrix-free全局接口修正；差异只是研究假设，尚无有效性声明。

## 选择性合并manifest（覆盖整个Review V2分支范围）

P4/P6/P7本轮closeout主要落在compact evidence/docs；但Review V2前段确实修改了numerical/core、runner、watchdog与checker。下表覆盖从review base `6bef3fdb8d7d70ac70db444086a2efd15c7cd80d`以来的完整V2依赖，不把“本轮收尾未改src”误写成“整个V2没改src”。

| 依赖组 / 顺序 | 文件与依赖 | 数值行为/资格证据 | 相关测试 | fresh PDE证据与边界 | 建议 |
|---|---|---|---|---|---|
| production numerical/core；先单独review | V2改动涉及`src/common/config_3d.py`、`src/common/modes_3d.py`、`src/geometry/task40_nonseparable_plan.py`、`src/io/input_schema.py`、`src/io/input_validation.py`、`src/io/physical_intermediate_profile.py`、`src/postprocessing/diffraction_3d.py`、`src/runners/physical_dual_cell_condensed_lowmem_v20.py`、`src/runners/physical_p4_schur_v14.py`、`src/runners/physical_retained_outer_adapter.py`、`src/runners/task038_full3d_iterative.py`、`src/runners/task038_launcher.py`、`src/solvers/dtn_port_3d.py`、`src/solvers/p6_cell_condensed_action.py`、新增`src/solvers/task40extra_p6_reference_metric.py` | 包含reference-metric候选、Task40显式profile/输入参数化和small-cutoff/identity相关修复；可能影响数值动作/结果，不代表都等价于普通生产默认 | `src/test/test_task40_first_direction_hp_metric.py`、`test_task40_m1_authority_channel_count.py`、`test_task40_m1_offline_recheck.py`、`test_task40_nonseparable_geometry.py`、`test_task40_p1_saved_field_postprocess.py`、`test_task40_p3_mode_staircase.py`、`test_task40_p6_local_growth_v2.py`及相关solver tests | F1只资格化特定G1 M0配置；F2 M1 official被checker挡下；P1/P4场curl存在负结果。不能把F1外推到G0 M2或所有网格/模式 | 按具体修复逐组迁移，并一并带对应测试；Task40 profile/reference metric保持显式opt-in，不能改ordinary default |
| reusable runner/watchdog；第二顺序 | `benchmarks/run_task39extra_v29_p6_tensor_pair.py`、`benchmarks/subreaper_watchdog.py`；E2恢复入口`benchmarks/task40_e2_saved_field_recovery_v1/{launch.sh,recover.py,supervise.py}` | runner/watchdog生命周期可能改变资源与退出判断；E2入口只做保存场输出恢复，不是通用求解器 | `src/test/test_task40_e2_recovery_supervisor.py`及对应watchdog/runner tests | E1/F3/F5为qualified watchdog runs；E2 v3是offline recovery、一次A6核验、无PDE/KSP/factor | 只迁移经过独立审查且保持用户service/subreaper语义的通用部分；Task40恢复程序留在任务范围 |
| checker/benchmark；第三顺序 | 新增`benchmarks/check_task40_first_arnoldi_hp_gate_v1.py`、`check_task40_g0_m1_offline_v1.py`、`diagnose_task40_p6_local_growth_v2.py`、`postprocess_task40_p1_saved_fields_common_subcells.py`、`postprocess_task40_p3_mode_staircase.py`、`review_task40_p2_saved_closure.py`；修改`benchmarks/run_task39extra_v29_p6_tensor_pair.py` | checker读取原始记录/保存场，不重做solver；P3规则须附事后确定披露，P1与P4采用不同截断身份 | `src/test/test_task40_diffraction_sampling_preflight.py`、`test_task40_m1_authority_channel_count.py`、`test_task40_m1_offline_recheck.py`、`test_task40_p1_saved_field_postprocess.py`、`test_task40_p3_mode_staircase.py` | P1 M0和P4 M2 offline结论均有hash-bound记录；不启动PDE/operator/factor/KSP | checker应与输入schema和独立fixture一并选择性迁移；绝不把P1/P4负Gate改为pass |
| compact evidence/docs；第四顺序 | `docs/task40extra_0p7nm_engineering/outcomes/records/*_v2.json`、`p1_m0_volume_h_agreement_v2.json`、`review_v2_campaign.md`、`outcomes/summary.md`、`outcomes/test_summary.md`、`response_v3.md`、`README.md`，以及根级progress/registry条目 | 不改数值行为；完整保留positive、negative、controlled stop、unknown与repair history | JSON/doc contract、链接/hash、`git diff --check`；既有serial/MPI2 targeted tests见test_summary | F1/F2/F3/F5/E1/E2身份与运行状态按raw SHA绑定；compact record不带大型raw arrays | 与相应source变更同一执行分支作为审阅证据保留；按manifest审核 |
| research-only；最后且默认不迁移 | P6 bounded local-block和synthetic resampled-mode诊断；P7波传播粗空间提案；Task40 task-specific profiles | 只支持三个真实局部tag、M=80/340/3904合成动作和待验证设计；未资格化高M物理全局解或2 TiB容量 | `src/test/test_task40_p6_local_growth_v2.py`及P7未来新增的针对性测试（尚无） | 无完整高M物理模型、无新增全局factor/PDE、P7未实现 | 保留research-only，未来需新review和fresh authority |
| do-not-merge | e174b91的`/dev/null`hook绕过行为；任何降低已冻结Gate、隐藏P1/P4负结果、将E2原worker改为成功、把experimental profile设为默认的改动 | 治理/数值语义不合规 | 对照repair ledger与本manifest | e174b91历史不改写；该提交后以Task40专用hooks的提交保留 | 禁止迁移绕行或放宽Gate的内容；本轮不merge master |

建议合并次序只表示依赖关系，不构成本轮合并批准。P7没有production实现；ordinary default不变；没有进行master merge。
