# V37：未裁剪目标p6边界见证、单mode分面片接口及容量停止

## 目的和改变

边界积分把连续电磁场与每个有限元基函数配对，得到端口耦合系数。旧路径先删掉幅度很小的条目，再比较新旧输出；这种比较只能证明两个裁剪实现一致。V37新增未裁剪native小面片对照：基函数是p6 Nédélec的882个向量基，完整保留方向变换、Piola（把参考单元向量正确映射到真实单元）及周期主从相位。q是求积规则的多项式精确度，不是点数，Fourier指数积分仍须比较不同q。

新TiledPortAction在一个mode内部逐面片处理：先算完整投影的一个复标量，再将同样面片重放，向共享master行相加牵引；伴随对独立C/D取正确共轭。主实现不创建完整目标FE向量再切片。小native向量只作为独立oracle；完整目标行reader／周期分布尚未资格化。O(Nport)元数据与完整输入输出、O(tile)缓存分开，不能仅报tile载荷冒充总内存。

## 实际覆盖和结果

| 内容／身份 | 实际值 | 解释 |
|---|---|---|
| 固定完整模式／材料 | 32060（16030每侧），canonical n=0.999885140474+4.32477054e-6i | V36 metadata只读复用，未删通道 |
| 元数据预选mode | top index0/1/6018/6019/16028/16029；bottom16030/16031/22048/22049/32058/32059 | 含s/p、零级、横向极值、最小非零传播纵向波数；tie-break原index最小，不按结果挑选 |
| min普通面片 | bottom [24,20,0]／[25,20,0]，top同x/y、zindex201；四hex | x=16.5..17.86、y=13.8889..14.5833nm；外表面−10／130nm |
| max普通／x周期缝／xy角点 | 共另16个预登记hex，NOT_RUN_STORAGE_GATE | 计划四类20hex；实际失败重建累计16hex，独立唯一4hex；没有目标mesh |
| q15与q30 | 完整C/D泛函最大相对差 1.32594720615e-05 | 阈值1e-10 FAIL，不能因同q映射正确称q15精确 |
| 同q30 Basix／native | 最大相对差 4.68916382572e-13 | 相同完整局部basis及坐标下PASS |
| q30 native与q60 Basix | 最大相对差 4.69243170483e-13 | PASS；原生q60未完成，保留独立对照边界 |
| forward／adjoint／amplitudes／modal RHS | 2.79308e-13／2.61646e-13／1.59542e-13／3.26371e-13 | 以未裁剪native重算，分子分母及全部mode保存在独立checker |
| 复线性／dual／H／单位功率 | 4.58310e-16／2.45695e-18／0／7.10543e-15 | 前两者operation差，H独立由k/E/面积／参考面算；单位功率绝对门1e-10 |
| 完整物理解／original A或SH／LU／QR／训练 | NOT_RUN／0／0／0／0 | 不把边界作用称体积传播；没有新R/T/A |

[预登记库存／坐标](records/witness_inventory_v37.json)、[原分子／分母／clipping](records/boundary_metrics_v37.json)、[保存数组独立检查](records/component_checker_v37.json)。near-zero和全零按原规则分别记录，未用operand范数覆盖完整非零泛函FAIL。

旧两道阈值仍为max(1e-30,1e-13×global_max)，按独立原native数据重算。q30第一道／第二道分别删除14928／112个分量，最大C/D相对差1.9269e-13，12mode未删空。原q15／q30每mode删除数量、最大幅度、范数、row与是否删空在raw sidecar及其hash索引；本组没有发现超门裁剪，不能证明所有32060mode／周期情形安全。V36旧资格明确LEGACY_CLIPPED_SURFACE_EQUIVALENCE，历史classification不改。

## 生命周期、资源与容量停止

| 对象／过程 | measured或derived容量／费用 | 未证明的内容 |
|---|---|---|
| tile cache／上限 | 42336B实测；独立128KiB门；mode cache门64MiB/max64 | 完整target support、periodic map扩张仍unknown，分配前门不能代替全量证明 |
| q30／q60 creatorworkspace | 上界22127616／81821376B；persistent geometry/map81024B | 算术数组载荷上界，非实测RSS；tabulation等嵌套时钟分别记录 |
| 完整分块作用集合 | 1.810418537s inclusive，192tile loads，96passes，5visits | creator1.628519290s、hash0.041459786s已包含；无匹配独立旧/新总成本速度比 |
| JIT停止 | 原始C/o/so总1559383311B，无损archive254668906B；单q60 form三件359797483B | 旧仅阶段边界guard导致越512MiB；明确软件监督缺口，未伪称门内停止 |
| 同时树采样峰／swap | 3387654144B／0 | 0.5s launcher＋全部后代采样，非连续cgroup峰；FE warn6/hard8GiB，aux2GiB |
| 所有监督、probe、bootstrap | 446.204937213＋25.657178592＋3＝474.862115805s | 包含失败／重放／JIT／测试／归档／checker，非完整N=1；未监督实现和元数据时间unknown |
| 保存新数据／Task042总artifact | 477669342／14963754484B | 最终门内不能抹掉历史新存储越界；科学数组及旧raw只读保留 |

当q60编译中生成的多个C/o/so副本超过存储门，先核实只属本任务的worker和临时JIT cwd，再SIGTERM完整自有组，watchdog确认后代清除。未暂停或终止邻Task042extra；native q60、max普通和periodic扩大不再启动。只对完成q15／q30数组，独立重新计算手工q30／q60及分块接口；容量分析不是冒称failed PATCH恢复或完整native q60成功。新live新存储guard已接线，专门负例测试通过。归档每个文件先解压核对原hash／长度，再回收相同原生成副本。失败分类和全部费用仍在ledger与raw。

数学线程／实际BLAS1，MPI1真实FE；MPI2／4为小合成共享rows、空owner与全体拒绝fixture。activation／复杂ABI及真实命令见run index，Torch/GPU未加载，缓存全部在NN-Lab。每次CPU门实际重新核查物理核和SMT，不依赖固定CPU编号。shared-workstation的性能影响缺可比阶段证据，INCONCLUSIVE；无绝对零干扰或无争用加速声明。

## 目标级排除式与消费包

理想单mode成对支撑9082376B有支撑假设；当前旧creator安全声明111259016B会越64MiB而拒绝。分面片改变了这个单对象门，但真实全量support、target canonical面片reader及periodic展开仍需证据。目标单complex128向量5532337056B；输入输出至少11064674112B载荷；条件GMRES256向量组434673050112B。端口元数据、内部恢复、全局solver／因子、MPI／IO的同时峰unknown，不把不同阶段及共享数组相加成伪峰。

假定每face一个tile，一个完整端口作用的双遍历面片访问量为2×32060×2628=168507360。实测普通tile生成单价约0.00848s只是本次调用集合均值；冷JIT、重复几何复用、所有mode分布、通信与迭代次数unknown，不线性外推48h承诺。最能决定后续可行性的校准是完整同尺寸端口面片creator的原生高q存储峰、周期覆盖及可复用几何成本，尚未运行。

只读contract/provider/验收模块分别为solver_consumer_contract、TiledPortAction和check_boundary_witness；精确source／hash和依赖在[部署包](records/deployment_package_v37.json)。完整32060metadata有序sourcehash继续沿用。consumer逐字段区分几何、材料、lambda、入射、背景、mode、参考面、复Floquet、p、canonical rows及内部恢复。dot只读SHA077ec9c...的恢复source没有合格runtime/scientific raw；几何尺寸／缺口、材料差2.9917165e-8及缺失的全量mode／row／恢复不能静默匹配。默认TARGET_SOLVE_NOT_AUTHORIZED_OR_NOT_QUALIFIED；没有启动其volume solver或消费factor。

## 交付边界与下一步

本轮是普通面片有限组件正结果＋q15和JIT存储负结果；非完整目标边界资格、micro PDE pass或神经增量。完整原尺寸原方程、E/H/curl、功率、生产h/p/q、外部截断、2TB/48h均未资格化。历史已记77349.71922726494s下界及unknown保留，V24–V36closed，没有新的teacher/dataset/model训练。本轮没有可比完整正确N=1非神经基线，所以NN20% NOT_DEMONSTRATED。

唯一下一建议：取得一次可预估JIT峰存储的未裁剪原生q60周期缝／角点边界见证，补齐精度与MPC覆盖。不自动实施，也不继续FFT／低秩／NN替代扫描。本轮closed，全部自有actor清除，精确最终Git HEAD在推送回执；不merge。GitHub视觉NOT_VERIFIED，本地结构检查与raw hash核验分别记录。
