# p4 两 y-cell reference quotient：最小实施与准入计划

本计划只读核验2026-10-01 canonical `ad356715da86ab34fa6b10838cccc8629b3f6e8b`及已保存p4权威，不改source、不导入项目、不做PDE/factor/solve。它继承`read_only_quotient_scalability_v2.md`（SHA256 `f55bacacd803fb1f2cae996151e4d84debab15cdd46ce3a4f4a4d8d01c351f6c`），收敛为下一步可审核的两cell实现范围；尚无数值许可。

## 结论与已资格权威

下一步应直接装配**两层真实三维y单元、两个explicit twist、每个twist的两个branch**，复用原精确消去/恢复；candidate setup不先建立全Ny reference CSR、F或Q。它仍保留所有单元内H(curl)通道和532物理别名，完整80cell原A4/notch outer不作维度替换。没有内部y谱变换或目标2TB/48h资格。

当前p4 authority在`benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p4_phi5_centered_attempt1/`：

- source `ad356715da86ab34fa6b10838cccc8629b3f6e8b`，clean；`probe_report.json` SHA256 `a71c0e177394b436c9b787b62f780db19ebcdce0410a85a346dbcf4fcc42151f`
- `independent_checker.json` SHA256 `bdc161047c8b6ececfa9c0086beedd66c8abc510049ba0b664df887fa848c56a`：148 PASS；provenance `2a6d5915429dda8294b0ec5be59dbf04f0ff5ca322d35007a0c52efe9fb44d1f`
- live receipt `95701a0adde26f5c190be0357614df287f487d5ae6f49d6e6d5668ea845ea4fd`：实际degree4/local300/Gauss23/144facet nodes，532 literal gates；physical generator `4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951`
- 全FE独立15872、storage17204、interior8640、trace7232；四q增广尺寸1884/1960/1960/1960。保存的positive-H q CSR分别436012/454744/454744/455143 entries，总payload36043932 B
- q CSR content hashes依q为`9b4973d558865531bd6c64f973cdf7b5c72360564eace0fb6dbf32e122223755`、`65117a867af8cb1b678a6435f87053581a931db2c2bf6716ca53d9a9f0f33d12`、`9c4905a379341f021d8c2e82817b6523a4261d18e835cb9c6510d2b0643900c8`、`28d66701a29ba83b2fa9b392d1da90ea88568742162dabde9106c7f2ea0047bc`；每个array文件另外绑定report中的file hash
- simultaneous tree peak913350656 B、117.446s、swap0；full原残差regular最大4.224e−12，notch最大7.967e−12。full p4 direct没有运行；这些是小三维degree/architecture控制，非原尺寸精度资格

冻结原x/z axes、所有实际cell metric/material、boundary-plane gauge、phi5、global periods和模式。初始candidate只取原y轴前两cell，实际坐标0/0.32407407407407407/0.6481481481481481 nm；全Ly=1.2962962962962963 nm。局部周期Ly/2仅定义quotient几何，原gamma/beta/kz/极化仍来自全Ly。原bar跨完整y，必须逐cell证明局部x-z材料标签与full reference相同；不能把notch重复成周期reference。

## native primal、dual与两个branch

令N=4=2K，K=2，b=0或1，theta_b=(ky*Ly+2*pi*b)/N，eta_b=exp(i*theta_b)，tau_b=eta_b^2。两个branch是全局q=b和q=b+K，eigenphase分别eta_b和−eta_b；禁止从principal arg(tau)开平方。x-wrap保持原phase_x，局部y-wrap明确为tau_b，corner为phase_x*tau_b。

以完整实体通道的canonical ordering为基准，定义supercell replication E_b：`(E_b u)_{2s+a}=tau_b^s*u_a/sqrt(K)`，s=0..K−1，a=0/1。完整canonical空间中E_b^H E_c=delta_bc I、sum_b E_b E_b^H=I；每个edge/face/interior通道均保留。局部两cell Fourier map为`F2_b=1/sqrt(2)*[[I,I],[eta_b*I,−eta_b*I]]`。直接代入应给`E_b F2_b=F_N[:, q=b,b+K]`，包括原y坐标锚点。

已有R是canonical primal→native independent，不假定unitary。用完整实体几何key、真实Basix物理moment/orientation和cell Tt interior变换，逐实体匹配full与two-cell；定义`P_FE,b=R_N E_b R_2,b_inverse`。primal为P_FE，dual严格为P_FE^H，inverse坐标提取为`R_2,b E_b^H R_N_inverse`。R_inverse不能换成R^H。trace restriction和interior restriction必须结构闭合；所有独立row恰好覆盖一次、slave storage恰为0。实现只流式使用full实体块/向量，不生成R_N、F_N、Q_N全矩阵；小fixture checker可以只读保存的旧full maps作为authority。

最小共享重构是从现`build_y_orbit_layout`提取实体记录迭代器，复用`hcurl_canonical_vector_dolfinx`的实体坐标/physical transform和现cell Tt代码。旧full builder继续消费同一迭代器，旧输出由保存p2/p4 mapping authority核验；不要复制第二套moment/orientation框架。two-cell R/F仅局部，显式输入theta_b/tau_b，不使用修改incidence的cfg推导branch。

物理aliases按原n分组：b=0保留n=−2,0,2（228ports），b=1保留n=−3,−1,1,3（304ports）；局部branch由整数`((n-b)//K)%2`选取。全q端口数为76/152/152/152。每个原ordered key最终恰出现一次，保留独立极化、side、gamma_n、beta和kz；不合并alias或±q。quotient不能在每个twist装配不满足local tau的另一个sector，再把非零量伪造为0。

## C/D/H、完整内部消去和任意RHS

在完整cell-index归一化与原坐标锚点一致时，full-q和two-cell branch的volume相同，C_full=sqrt(K)*C_2，D_full=sqrt(K)*D_2，H_full=K*H_2。这里D已经含原carrier的conjugation；是D*Q的dual/primal作用，不能再共轭D。native basis还须包含上节J/R对应。

完整局部原增广符号保持`[V,C; −D,H]`。内部消去复用原公式：S_V=Vtt−Vti*Vii^-1*Vit，C_hat=Ct−Vti*Vii^-1*Bi，D_hat=Dt−Di*Vii^-1*Vit，H_hat=H+Di*Vii^-1*Bi。branch中的Bi/Di及C_hat/D_hat仍乘sqrt(K)，XiB同样按Bi缩放，H_hat仍乘K；不得把H_hat当diagonal或把真实interior port support设0。当前full p4实际有8cells非零Bi/Di，下一局部支持必须重新测量。

等价bare two-cell auxiliary为beta_2=sqrt(K)*alpha_full；完整增广primal lift为`diag(P_FE,b, I_sector/sqrt(K))`，lower dual load为`r_p,2=r_p,full/sqrt(K)`。positive-H坐标满足`sqrt(H_full)*alpha_full=sqrt(H_2)*beta_2`，因此保存的四个positive-H q block应直接与local positive-H branch相同。normalize必须用original H，而非H_hat；先证明H_full/K=H_2再使用此简化。

对任意full native MPC-dual FE load：先做P_FE,b^H，保留全部interiors，再调用既有reduce_rhs；不能只投影trace。局部reduced FE load为f_t−Vti*Vii^-1*f_i，lower为r_p,2+Di*Vii^-1*f_i。每个q/interior row及所有原port均要有非零制造负载，另保留generic/interior_only/physical/notch_supported四种旧full load。局部完整恢复复用`u_i=Vii^-1*f_i−Vii^-1*Vit*u_t−XiB*beta_2`，再由P_FE流式lift并求和，alpha_full=beta_2/sqrt(K)。全部branch求和后才输出全80cell storage，默认slave-zero；物理后处理显式backsubstitution副本。

任意nonzero port RHS的原native residual应对`b_eff=b_FE−C*H^-1*r_p`，并同时保存两条原增广方程残差；复用`e_native=e_FE−C*H^-1*e_p`，不误把b_FE单独当成消去后的physical RHS。regular恢复使用当前reference alpha；notch final恢复需完整A1 physical alpha，而非PC最后A0 alpha。

## 当前接口缺口和最小改动位置

1. **显式wrap，不改变physical ky。** `FloquetTraceTopology.materialize(phase_x,phase_y)`现成支持corner product；`build_high_order_constraint_data`及public `build_double_floquet_mpc`仍从cfg读phase。加research-only显式phase参数贯穿现phase materialization/finalize/metadata，默认不变；复用原distributed pairing和非零master筛选，不在finalize后改coefficients。局部mesh Ny2满足现min2guard。重复slave、自master、corner一致性、slave-chain/最终master展开、完整覆盖、实际max expansion width都必须检查；不能按higher-order单master估算。
2. **global generator/local assembly分离。** `build_same_mesh_physical_action(mode_inventory=...)`现仍调用carrier按所给cfg重建manifest并检查相等，不能直接接受local cfg+global modes。最小opt-in接口同时接收冻结global physical inventory/config和local assembly cfg/explicit wrap/sector indices；原模式objects由full physical generator产生一次，局部不得调用outgoing_port_modes_3d。full physical manifest在full cfg核验，C/D surface、positive H面积和MPC/Gauss在local cfg核验，media/mu/k0/zplanes/traction参数须相同。
3. **沿用边界身份字段。** 顶层bundle.mode_sha256和carrier.physical_generator_manifest_sha256保持完整532 generator hash；sector carrier只含228或304 actual entries，另绑定原index/key/row，不能声称其entry count为532。FullspaceDtnCarrier要求local mode_index按0..M−1连续，因此保留该合同并添加显式local→original index映射。carrier.mode_manifest_sha256为新的sector/local gauge assembly；assembly_context_sha256绑定local mesh/area/explicit tau/theta/Basix/MPC/Gauss/source/ABI及global inventory/sector map。现`build_gauge_assembly_context`需加明确quotient context，不能伪造旧context/hash。
4. **action-only精确消去。** 直接复用`build_unconstrained_assembly_time_condensation(materialize_global_matrix=False, retain_local_schur_for_matrix_free=True, preserve_exact_geometry=True, share_identity_cache=True, strict_local_checks=True, sum_duplicate_cell_integrals=True)`。现`P4CellCondensedInverse`/`assemble_condensed_ports`要求matrix存在，不为满足它们建立full Ny S。复用`build_p6_cell_condensed_action_from_carrier`/P6CellCondensedAction的完整Bi/Di、reduce_rhs/recover_storage/native residual；实现维数从system读，新p4用途必须独立资格。constructor cached/streamed模式均已有；初始40cell可以选择cached小sector H，记录完整复制，未来target尚未资格。
5. **最小block接口。** 在现P6CellCondensedAction上增加只读local condensed contribution iterator，复用其已计算S_V/recovery/Bhat/Dhat/XiB/H修正和direct active segments，不重新tensor/LU消去。volume直接复用`iter_owned_constrained_schur_contributions`。流式投影每个cell contribution到local F2 branch，只materialize一个q CSR；不能逐列apply整个global reduced action作为目标scale默认装配。再将现SparseAllQFactor的“完整audit后、逐q factor/solve_repeated/partial cleanup”抽成接收block provider的窄入口；旧完整matrix入口/default不变。没有第二套solver/cache/恢复框架。
6. **单一research glue。** 新`src/solvers/y_orbit_two_cell_quotient.py`负责cfg分离、sector/映射、local bundle ownership及provider；benchmark runner/checker复用现watchdog/provenance/array writers和独立原残差逻辑。boundary live helper的40cell profile应显式接收sector index/context，保留全部literal coefficient/H/rank-one/five-state/RHS/output/lifecycle/failure gates；跨两个bundle合计核验532，不能把当前固定532/80cell helper直接说成现已支持。新增targeted contract tests针对branch parity/phase/cfg split/dual signs/cast overflow/missing branch/mask差异/source binding/cleanup。

上述为需要审核的接口设计，不是已经存在的API；每项先做staging/source review再integration。geometry/condensation/local LU数学core不改。引用Task040 S2只能说明既有exact all-harmonic背景概念：其both-x/y-uniform、aux0或4、旧dense小block不能直接承接这里y-only异质xz/532aliases。

## raw-before-mask与mask后的same-discrete资格

cutoff不与folding默认交换：当前component在MPC之后用max(1e−30,1e−13*global_max)；组合C/D再进行同阈值stage。因此同Gauss raw identity通过仍不足以宣称与旧masked p4相同。

- 用现surface assembler的assemble_raw_mpc_vector及literal Basix/Gauss oracle，在实际p4 degree23/144nodes上核验local raw→full folded C/D与H面积；同时核验volume/material/MPC native J。不从已masked carrier反推raw，也不改变阈值。
- 逐532原mode记录full和local两次mask的threshold、retained/lost support、norm和每mode rank-one loss bound。将local masked fold与旧masked authority的C/D/rank-one及最终S比较；raw roundoff、原cutoff损失、quotient先mask后fold额外损失分别保存。任何不存在的old raw数组必须由同source/default original raw live路径补证，不能从旧stored数组猜测。
- 正式same-discrete资格要求四q complete-column CSR差异/operator和全部cross-branch leakage≤1e−11；permode coefficient/rank-one/field/output沿用1e−10原门。若mask非交换差异超过门，stop保存negative，单独提出保持原mask语义的方案。即使低于门也报告实际差异，不声称byte/hash相同。

## 派生大小、resource admission与生命周期

以下是derived payload/upper，不是新测量。每个local mesh4×2×5=40cells；p4 storage=207edges×4+158faces×24+40×108=8940，independent7936、slaves1004、interiors4320、trace3616。局部reduced b0/b1为3844/3920；每branch trace1808，完整FE3968=1808+2160。local facet slab storage2012、独立FE1792、active trace928；实际port支持另测，不能采用ideal bubble零支持。

设i=np.dtype(PETSc.IntType).itemsize，scalar16B；CSR upper=(rows+1)*i+nnz*(16+i)，范围在任何PETSc/SciPy/SuperLU narrowing前检查。public SuperLU signed int32兼容门仍须执行，即便PETSc是int64。局部cell索引int32与global PETSc索引分别记账。

| 对象 | 派生准入 |
|---|---|
| local full entity R/R_inverse/F2粗上界 | map nnz≤7936×108=857088；当前int32 payload34696204 B，Python workspace191987712 B；int64使用同公式重算。仅一个local bundle/map在构造 |
| action-only cache保守40raw/40oriented classes | 现capacity公式retained57710592 B、workspace145143216 B（int32、shared108² real identity）；实际class count先测，不继承full16/29的数值 |
| local S volume graph | ≤40×192²×W_MPC²+3616；W从finalized public coefficients/masters/offsets取得；未知/非法即stop |
| sector C+D trace graph和Hhat | ≤2*M*928及M²；局部增广CSR粗上界W1：b0 int32 39081940 B / int64 46910632 B；b1 int32 42712004 B / int64 51266952 B。provider路线不同时常驻这两个local S |
| local carrier C+D slab upper | 2*M*2012*(16+i)，b1 int32=24465920 B，另计component cache/staging/retained/identity重叠，不当RSS |
| local original H每份dense | b0 831744 B、b1 1478656 B；现action constructor input/Hp/Hhat复制重叠逐项计量，避免访问返回copy的Hhat property做统计 |
| all-q input CSR | 旧测量36043932 B作比较authority；candidate NNZ/byte必须实测，新roundoff pattern不保证相同 |
| 5state local FE oracle array | 8940×5×16=715200 B/份；每mode流式复用，caller-owned raw Vec及时destroy |

Factor fill/workspace仍unknown，没有SuperLU symbolic estimator、无L/U复制估计、无按Ny简单除历史global-factor RAM。初始严格上限min(1.5GiB,freshdynamiccap)、600s total、zero global/tree swap、MPI1/maththreads1、一个heavy job。每一步actual whole-tree admission先于分配；在首factor前要求fresh R0+512MiB factor allowance+128MiB reserve严格小于effectivecap（nominal时R0<939524096 B）。已经常驻factor计入R0，仅预留剩余allowance，不能反复加完整512MiB或假定del立即返RSS。

生命周期：先双twist所有branch结构/raw/masked/operator审计，factor数始终0；audit receipts/hash保存在ignored artifact。之后parent另行go，逐b/q重新生成并核对audited block，CSR→CSC→public SuperLU，保留全部4factor。一个sector local bundle/cache在pass内持有；若outer apply需要两sector recovery状态，明确选择两份小map/cache常驻或共享readonly类缓存的已测试ownership，不重复FFCx/JIT或因子化；以最坏两份记账后再准入。cleanup先关borrowedfactor callback，再destroy own carrier/Vec/matrix/action-only系统和local setup，partial factor失败也清全；assembler raw Vec独立销毁。原volume_action.apply返回borrowed reusable Vec，不destroy它。

## 资格顺序和停止门

1. **Q0 source/provenance。** clean新HEAD、文件hash/ABI/source freeze，原ad356715 report/checker/artifact及每array hash绑定；所有derived counts/cfg/global physics/actual local mesh widths/tags/period/eta/tau/sector索引/actual MPC inventory完整。
2. **Q1 maps/raw，no factor。** x/y/corner/topology self/chain/closure完整；local R/inverse、E/F2/full saved Q列关系≤1e−12。四q原FE/trace/interior坐标complete；两twist/两branch/532keys全覆盖。fresh p4 raw Gauss/Basix literal组件以及area/normalization/全部BiDi消去资格，阶段失败原样保存。
3. **Q2 same-discrete四block，no factor。** oneq-at-a-time provider CSR与旧四positive-H matrices逐列/CSR Frobenius比较≤1e−11；全部local cross-branch及跨b的full原action coupling同门。不为比较生成candidate全Ny reference CSR/F/Q。mask两阶段差异必须有完整permode/cumulative证书；不只验证q0或只验体积。
4. **Q3 independently gated numeric。** parent看Q1/Q2实际RSS/NNZ后才准许全部fourfactor；保持当前随机增广load真实残差/重复/线性原门和nonfinite stop。不能复用±q factors。当前constructor把audit+factor合在一起，新provider入口必须真的分阶段，而非只有文档写分开。
5. **Q4 full original recovery。** full generic/interior_only/physical/notch_supported及每q任意interior+port manufactured loads，恢复全部17204 storage；逐原A4 matrix-free评估≤1e−10、slave0、augmented residual identity、solution/field对旧权威≤1e−9、532 outputs≤1e−10。验证实际nonzero wrap。full original matrix不materialize；完整旧authority矩阵只读用于小checker，不作为candidate setup依赖。
6. **Q5 outer replacement。** 通过Q4后才把新inverse接现完整80cell A1/notch FGMRES；正确A1 alpha与field/output复核。比较旧3/4steps、peak/setup/apply时间，step数不是物理精度或target-scale保证。随后更大xz/Ny的capacity研究另准入，不隐藏原尺寸32060自动propagating库存（它本身也未做截断精度资格）。

任何missing branch、illegal master/overflow/NaN、mode/context mismatch、map非闭合、raw/mask/operator/原残差失败、headroom不足、swap或超时均stop，保存negative，不改物理inventory/tolerances/cutoff来通过。

## source bridge与审核归属

旧ad356715及全部p2/p4 receipts保持不可变。新explicit phase/context/sector/provider必须形成新的HEAD和local assembly hash，不能说same source。先review source diff/default调用/contract tests；把default full physical generator/原basis/forms/cutoff/condensation仍相同的证据单列，并用原saved p4 q CSR+original loads/actions/recovery构成显式old authority→new candidate bridge。source/path/ABI/oracle身份及独立checker实现进入新provenance。无需自动重跑已资格densep2，也不得用旧p4 live receipt替代新local context/components。若default operator数学发生改变，旧bridge不能继续用“unchanged”口径，协调方重新决定控制。

建议phase/context改动由modal/port负责人单一canonical writer集成；condensation math不改，窄contribution iterator和streamed native maps仍须独立review。本文件只是外部计划；implementation staging、canonical integration和任何bounded command均需root后续明确许可及source freeze。

## 复用源码与阅读边界

本轮读相关实际函数/范围，不声称整个大文件全文语义审计；已读完整static_local_schur_action及旧v2合同。以下SHA256取自冻结ad356715的当前相同文件：

| 路径/直接复用 | SHA256 |
|---|---|
| src/constraints/high_order_floquet_trace.py：FloquetTraceTopology.materialize | 518442c9217253dd4e69309939c64a10ce3ff6ee64d0533ce3126b31d7acf0bb |
| src/constraints/floquet_3d_high_order.py：原phase-independent pairing/materialization | 9e441f562cb9acd449a8aa1e8d69a4909e4c1e09b5a9d6590c24e66bf9fc751d |
| src/constraints/floquet_3d.py：public finalize/metadata | b013ce397b6bdc4a7a27ae8088a20718d8c6f195adc03f9f3dd21a0a965aacd4 |
| src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py：physical/assembly当前入口 | 2000062b8b2e09c12166d9b5f7dde97623d188a96895e96a182cf585ee4afc62 |
| src/solvers/fullspace_dtn_action.py：carrier/ordered manifest/local-index合同 | 777d7ea10d598a7f5abba652b0de896f7040782fe7e421522c8b0e41d3f73c55 |
| src/solvers/dtn_boundary_phase_gauge.py：context/area/gauge转换 | a009e13b83e1a484452deef1b7f35396b38e84c2d9f9fcf98207f7f2d629a343 |
| src/solvers/dtn_port_3d.py：surface raw MPC/Gauss/two cutoffs | fc1992068c8c3fdab770e8ff601b0fdd4a3506384be59bba418daa80e08ec780 |
| src/solvers/hcurl_assembly_time_condensation.py：action-only cache/capacity/完整消去 | 0edd5478ef5c08649c95c0d1ade16436b4833e169f4cc6835731bdf1bc0f1e26 |
| src/solvers/static_local_schur_action.py：既有constrained贡献iterator | 149d3c2710412172a3ff9d99fcdc87d41a9b34e1fbb51ed0b29e70e46b32c0c8 |
| src/solvers/p6_cell_condensed_action.py：实际action-only/ports/任意RHS/恢复合同 | b98b44dd810ac1efed6ef9b85863713cd9d8416b049f9c86d5c3ae1c030d3576 |
| src/solvers/p4_cell_condensed_inverse.py：materialized matrix要求，不能冒用action-only | 678eb3103e57505a42c996ee2818c0e9e757189c0a2f871c90f3f911faf210e7 |
| src/solvers/task40extra_y_orbit_reference.py：完整实体R/dual/F/currenttheta | 6a6baecf6a0f9aee76f40aac1dc67f9b68753e89e7bb09cacafc230d272d6749 |
| src/solvers/y_orbit_condensed_adapter.py：trace closure/original residual/precast admission | 156a30713eec6618a28db3baacca4fcd1a150f479fefd9b69e892f98c71c9a44 |
| src/solvers/y_orbit_sparse_reference.py：原positive H/完整audit/factors/cleanup | 863884e978b21facc93e16b4ed19befeee59da23ec187e12b552a3e5193ca86f |
| src/solvers/dtn_boundary_plane_qualification.py：degree4 literal live gates | 6b9a432da910e4a3c1ec9cc011974b6938c58a8230d571c575f5d4338dbc9fd1 |

当前ABI hash `007a5f794c3b1f4f7431917f15700cd1cfef5606f3601b07c429135ec5270e96`，serial complex128/PETSc int32；新run仍须fresh activation证明。只使用public PETSc/DOLFINx/MPC/SciPy路径，不触碰旧private MUMPS FFI或soname aliases。
