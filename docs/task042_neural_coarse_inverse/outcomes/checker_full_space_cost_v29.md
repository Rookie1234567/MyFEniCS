# V29：审核可信链、全空间补项与神经成本必要条件

**状态：`NOT_RUN_AUXILIARY_CPU_ADMISSION`。** 唯一辅助准入在创建worker前拒绝，随后停止所有测试、合成计算和缓存分析命令，只完成纸面推导、冻结JSON的静态转录和交付。A实现尚未资格化；B没有执行小矩阵fixture；C没有合格完整单解基线。不是新的有限元解，也不重开V27/V28。

| 身份／范围 | 实际记录、单位与边界 |
|---|---|
| 合同／取得状态 | Review V26 `5f78fb831e8b1b243f8d8865286dce54bb0d631f`；安全fetch，同一分支已最新，未回退 |
| canonical worktree／upstream | `/home/fenics/Projects/NN-Lab`；`task42_neural_coarse_inverse`；`origin/task42_neural_coarse_inverse` |
| common／base | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；`ccd357885f7f9be84efe3be07868cc94f13d93fc` |
| clean实现source | `bea514e634a0fde7b1b929535f79a6268856d01b`；该source执行了准入launcher，数值／测试worker source=null |
| 不刷新窗口 | start `2026-10-03T05:29:16.937526Z`；轻量截止06:14:16.937526Z；交付截止06:29:16.937526Z；05:45:04.616694Z提前closed |
| 物理对象／not_run | 原0.7nm、384hex/p3/q15、18144 trace＋40port、canonical材料、背景、MPC、双Floquet不变；未加载真实packet／因子／REF／神经权重 |
| 准入／measured | 05:43:34.475826Z–05:43:35.721686Z，CPU候选空；CPU_SMT=FAIL，MEMORY/DISK/PSI=NOT_CHECKED；不降低5%／SMT门限、不重试 |
| 新真实消费／not_run | actor0、S/SH0、reader0、solve0、新LU/gecon0、真实薄分解0、FE/JIT0、训练0、迭代0 |
| 最终资格 | A `IMPLEMENTED_NOT_QUALIFIED`；B执行 `NOT_RUN`；原场／尺寸／48小时 `NOT_QUALIFIED`；NN20% `NOT_DEMONSTRATED` |

## A：审核器应该证明哪些事实

审核器用保存的向量和原始计数重新判断诊断，而不是相信PASS标签。此次补齐的条件可以防止“计算未完成却写完整”、保存错向量或发布错范数；代价是少量已经算出的证书和审核读取。没有改原有限元算法，也没有为审核额外调用原算子或分解。

| 漏项／实现 | 必需证据和反例 | 本轮验收 |
|---|---|---|
| 完整消费 | S34＋SH2、J4列、外域24列、三角56、端口35次单列、reader7、薄流程2；结果、已settle ledger、manifest一致 | 代码预期，非实测；合成验收未运行 |
| 因子资格 | J与0/1/2/3/4/6各一次；规定seed、原始solve误差／尺度、primal及J adjoint见证、source／行／文件hash、三角pass与RHS库存 | 新必需审核已实现；真实reader和小fixture都未运行 |
| 回流向量 | hash-bound V26 qJ；`q_ret=qJ+d`；w只在外域、feedback只在J；不能只检查其image | 加100的反例已登记，拒绝结果未实测 |
| 残差／恢复／端口 | 实际r范数；trace/port/z拼接；保存的full residual、重闭合port、无内部特解的方向身份 | 数组一致性与finite／阈值已实现，未验收 |
| 抵消／重组／操作尺度 | 必需字段、原始范数／分母；缓存原作用向量；同次已计算的cell bound operands、输入hash及V25旧尺度身份 | 不新增原作用；未实测 |
| 全链fixture | 临时目录中的两名称／父记录／成员hash，通过正式collector直到分类；缺／重／错bundle、失败见证、计数、ledger、parent、member、NaN及缺数组 | 源码已准备，执行0；不冒充通过 |
| 合法负例 | beta=0、已解基线、可信弱结果、零／重复／近零创新；不强制rank10或非零beta | 原100 scope保留在准备队列，当前source未复跑 |

[checker资格记录](records/checker_gate_v29.json)、[source索引](records/source_inventory_v29.json)、[测试记录](records/tests_v29.json)。Review V26的100 passed是旧source的审阅测量，不是当前改动的回归通过。预备复现命令为`python -m benchmarks.task042_v29_light_checks`，本轮未执行，不能在closed窗口自行调用或再次准入。

冻结CPU表是已有准入决定的逐核静态转录：包括socket/core/SMT、busy分数及排除PID/TID/start identity和规则。没有调用CPU策略重算或再采样；此前独立重算见Review V26证据，当前新replay验收为NOT_RUN。

| 冻结快照 | 保存的允许CPU数／候选 | 逐核表与口径 |
|---|---|---|
| V28成功03:50:41Z | 48；`[11,22,26]` | [JSON](records/cpu_reason_table_accepted_v29.json)／[CSV](records/cpu_reason_table_accepted_v29.csv)，保存决策转录 |
| V28拒绝03:52:00Z | 48；`[]` | [JSON](records/cpu_reason_table_rejected_v29.json)／[CSV](records/cpu_reason_table_rejected_v29.csv)，保存决策转录 |

忙率、窄affinity及活跃宽线程分别列出，SMT同胞的原因传到该物理核。桌面与Codex线程排除集合重叠，不能简单相加，也不能据此称48核持续满载。没有忽略桌面线程、改邻任务或放宽资源规则。

## B：外域直接入口的纸面推导

旧回流只读取J内的残差，外域输入在J为零时被完全忽略。补项让J先解、外域解剩余，再由J补偿外域带回的耦合；它是传统顺序块校正，不是神经方法。收益是保留全空间代数方向，代价是每次J两解、六外块各一解和两次原A传播，最后残差及端口审核另外计费。

```math
B_{\rm ret}=B_J-(I-B_JA)L_OAB_J,\qquad
B_{\rm full}=B_J+(I-B_JA)L_O(I-AB_J),
```

```math
B_{\rm full}-B_{\rm ret}=(I-B_JA)L_O.
```

按J、外域O排列，令J主矩阵为K，外域六主块组成块对角矩阵D；原A的非对角块为C、F，不假定互为共轭。补项按顺序给出：

```math
q_J^{(1)}=K^{-1}r_J,\quad
u_O=D^{-1}(r_O-Fq_J^{(1)}),\quad
q_J=q_J^{(1)}-K^{-1}Cu_O,\quad q_O=u_O.
```

```math
B_{\rm full}=
\begin{bmatrix}I&-K^{-1}C\\0&I\end{bmatrix}
\begin{bmatrix}K^{-1}&0\\0&D^{-1}\end{bmatrix}
\begin{bmatrix}I&0\\-FK^{-1}&I\end{bmatrix}.
```

因此J及六外块均可逆、且覆盖全部trace时，这个乘积可逆，行列式为det(K)的倒数乘det(D)的倒数。旧Bret右端含BJ，rank至多3888；全空间补项没有这个结构性秩上限。这里没有要求全A正定、Hermitian或残差收缩，不能据可逆性授予迭代资格。

纸面反例按合同固定：A=[[1,2],[3,1]]，J第一行、外域第二行。Bfull=[[7,-2],[-3,1]]，输入r=[0,1]时Bret r=[0,0]，Bfull r=[-2,1]，Aq=[0,-5]，真实剩余r-Aq=[0,6]。局部精确且补齐方向，残差仍增长六倍。这不是本轮计算输出，也不外推Maxwell必发散。

| 预登记小fixture | 设计／预算 | 实际执行 |
|---|---|---|
| NON_HERMITIAN_8 | n8、complex128、seed422901、J2行＋六单行外块；差式／输入顺序／支持／复线性／三角分解 | NOT_RUN |
| NON_CONTRACTION_2 | 合同固定2×2反例；残差不收缩 | NOT_RUN；上述为纸面算术 |
| SINGULAR_LOCAL_2 | A=[[0,1],[1,2]]，J零主块须显式拒绝；不调shift／分区 | NOT_RUN |

[隔离fixture入口](../../../benchmarks/task042_full_block_algebra.py)与[记录](records/full_space_algebra_v29.json)。没有注册PC或dat，没有接入真实求解器；数值等式≤1e-12的验收未执行。

## C：成本必要条件，不能把局部快当完整快

完整单解成本从算子准备到合格场及审核结束。已有记录允许列出研发和嵌套timer，却缺少成功、完整、同精度的N=1对照。以下时间都是历史shared-workstation测量，未知部分不补造；嵌套timer不加到actor总时间。

| 费用／单位s | 已有值与数据身份 | 审阅边界 |
|---|---|---|
| V24所有formal运行／辅助 | 1977.711696077／62.584019216，measured | 包含失败、setup、求解、审核；不是合格单解耗时 |
| V25 actor／辅助 | 25.665227009／26.429975512，measured | 三残差方向诊断，不是部署性能 |
| V26 actor／辅助 | 33.262622487／27.636738837，measured | 同一诊断范围，嵌套明细另列 |
| V26装配／joint factor／gecon | 1.592389774／3.324998309／0.537647051，measured nested | 包含原固定联合块准备；不与actor相加 |
| V26 readonly hash＋reload／J solve | 5.835275504／0.967400231，measured nested | J历史9次solve，不是Bfull每apply成本 |
| V26两薄分解 | 0.008964091074，measured nested | actor中约0.027%；免费替代也达不到该诊断口径20% |
| V27／V28受监督辅助 | 12.366657368／8.797189402，measured | 真实actor均0；不能当0耗时求解 |
| 上游packet、global image基及完整warm lineage | unknown | 不能抹去准备、神经、LSQR和循环路线的历史费用 |
| 独立exclusive审核／IO／成功完整N=1 | unknown | 现有nested记录不足以重建无重计的完整分账 |

[静态完整成本库存](records/static_complete_cost_inventory_v29.json)绑定V24–V28原JSON hash，保留逐块setup／factor及S/SH／端口明细。它只转录已有值，没有运行新benchmark或读取真实载荷。

部署每次Bfull需要8次局部LU solve、16次显式三角pass、2次原A传播；原A自身端口链也有成本。最终true residual、闭合port、恢复／审核和IO另列。资格阶段的七套因子source/hash/row/reload witnesses、primal／adjoint／端口检查不能按每次部署重复收费，也不能从完整冷启动删掉。

七套A＋LU载荷为1,591,420,032 B，纯LU部分下界795,710,016 B；这是历史对象体积，不是RSS。冷准备包含六旧外块和J联合因子；每apply重新hash／mmap与一次加载后驻留复用有不同生命周期，目前两种部署时间和同时峰都unknown。共享因子算一次，pivot私有副本、hash缓冲、页驻留、端口、库和workspace按同时存在计费，不能把累计文件字节当峰。

```math
T_{\rm new}=T_{\rm base}-T_{\rm removed}+T_{\rm added},\qquad
T_{\rm removed}-T_{\rm added}\ge0.20T_{\rm base}.
```

Tadded必须含数据生成、训练、模型准备／加载、推理、额外精确修正及审核；本合同N=1不假定多RHS摊销。峰内存条件为同口径同时峰Mnew≤0.80Mbase，另一项资源指标仍须合规；不能以删除字节除累计体积替代它。

| 后续价值判断 | 当前证据／结论 |
|---|---|
| 仅提速九／十方向薄LS | 在V26诊断口径即使免费也远少于20%；不值得用系数网络替代该小步骤来追求此门槛 |
| 同八／九方向内学系数 | 不能超同空间精确最小残差的消除能力；不构成新的表示收益 |
| 替代主要因子准备／存储、重复求解或原作用 | 可能触及大费用，但正确性、学习新增成本和完整N=1收益均unknown；须另有证据／合同 |
| 新的可资格化作用或传播方向 | 可以改变消除能力；本轮只有纸面必要条件，没有真实作用收益或神经训练 |
| 最佳合格非神经完整Tbase／Mbase | 不存在已资格化的配对，保持unknown；不能给神经20%通过结论 |

## 资源停止、未运行项与唯一下一建议

[准入原始快照与stderr](records/admission_stop_v29.json)保存拒绝前后的实际记录。launcher在准入前使用pure activation／数学线程1的请求配置；未到worker资格检查，BLAS getter、CPU绑核、2GiB/1GiB的0.5s整树监督都未创建。RSS／own-swap峰是unknown，不填0；无GPU/OOC、无真实数值后代。监督未运行不是监督失败，CPU Gate是先发生的真实停止条件。

新受监督有载0s；V27＋V28的21.163846769952215s保持，Review自己的8.577899s仍单列。准入探针约1.245876s计本批elapsed，launcher完整启动时间及实现／读取／交付exclusive费用unknown。旧formal研发下界77,161.557139s保留。[资源账](records/resource_costs_v29.json)及[原始索引](records/run_index_v29.json)绑定closed窗口、旧ledger hash和空运行库存。

A的focused/端到端／原100回归、B三fixture、C缓存分析入口、CPU tick独立重算及doc pytest均因同一个准入拒绝NOT_RUN；没有为凑表补跑。当地静态文档检查与GitHub视觉检查分列，精确review页Cache miss，视觉NOT_VERIFIED；旧review不改。

唯一下一建议：由下一review在可审计的空闲条件下，仅重新授权这份已准备的A/B轻量验收；先关闭checker可信链，再决定是否值得授权真实回流或全空间补项。本批不授予该许可、不后台等待或重入。旧V24完整0/5、V23 0/6、所有历史负结果保持，无merge approval。
