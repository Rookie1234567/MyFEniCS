# V42：横向Bloch包络FTT的核心求解与隐藏学习消融

本次先从网络输出中分离已知的横向传播振荡，再让三个小网络表示剩余包络。这样网络无需重新学习入射波的横向相位，但其余衍射、界面变化及三维散射仍由原完整有限元方程约束。它只改变函数表示，不另组包络PDE，不把H按包络计算，也不免除全场和原算子成本。

原M5保持5nm、8×6×8=384hex、h1.25nm、Nédélec p3、31968独立复FE、完整40端口，原Si/air三维缺口、材料、背景、双Floquet/DtN不变。r=(1,8,8,1)，三轴两层sin NN共9072实参数；Cheb T0..T18控制共9120实系数。体/DtN q15、网络完整矩q30、独立旧逐点q60。

chi使用实际cfg未折叠kx=1.2564456695248023 nm^-1、ky=0、kz=0和原盒中心(0,0,3.75)nm，正号exp(+ik·x)。x方向胞内约两个周期，不能因周期缝相位接近1就折叠kx。相位在边/面/内部物理积分点、Piola和完整矩之前乘入；MPC只展开一次。实际H来自最终FE场的curl。单位模相位本身没有证明一维特征条件数改善。

## 1. 相位和原方程

```math
\chi=\exp\{i[k_x(x-x_c)+k_y(y-y_c)]\},\quad c=I_h^{\mathrm{curl}}(\chi F_xF_yF_z),\quad L=\frac{(Ac-f)^*(Ac-f)}{2f^*f}.
```

开始现场为V41已完成、HEAD8e187eae48551812a5cd335a3c0dfbce9236239c、clean、numerical.lock FREE、无本任务活跃run。精确fetch/ff-only取得Review V41发布7c9b3e69b16f6cdd1fb1504e50203d3740305dae；canonical与common Git分别是/home/fenics/Projects/NN-Lab-V2和/home/fenics/Projects/Maxwell3D-Lab/task-repository.git。base fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。共享fetch配置未改，显式tracking ref为核对权威；字面upstream与解析结果分别报告，旧解析128不冒称通过。

新opt-in实现先clean提交c1c82474d9a26675f1829db5a219efdc04a60f59，再启动资格和真实路线。每阶段的实际source/input/design/native/moments/phase/buffers由run manifest与checkpoint绑定；后续文档HEAD不是运行源码。原V1同p3参考SHA2560c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7只由独立评分读取，没有重新MUMPS求解。

新增相位不是只接入forward：活动核心替换、K/K*、B/B*、隐藏VJP、缓存、保存及独立export都接通同一相位。独立对照明确调用未改的旧FTT点值后再乘chi，避免两个同时漏相位的实现互相证明。phase=0的c、原作用、VJP、三轴K/K*回归为零差；边3744、面14400、内部13824三个独立矩族均通过。实际M5 ky=0，两个非单位周期缝和角点资格另由合成fixture覆盖，不冒称真实M5的第二非单位相位。

真实三轴非零复数、纯虚、bias、全部分量、K/B复伴随及隐藏三个非零FD方向通过。q30/q60原作用、batch1/8、参数与相位缓存失效、接受/拒绝和完整恢复通过；错号、错单位、折叠kx与重复MPC均被独立路径检出。原skew/不支持几何的准确逐点后备保留，真实J、orientation、owner及微小非零未删。每模型三次短完整工作含实际写回c/r和存盘，资格状态没有用于正式初值。

## 2. 顺序条件求解、真实隐藏更新及标量分流

核心线性求解是在固定隐藏层和另两轴后，让当前轴输出系数满足原方程。B=AK/||f||、b=(f-Ac)/||f||，用matrix-free LSMR求增量，damp0、atol/btol1e-8、conlim1e12、maxiter300、增量零初值。返回后独立核对原线性及伴随残差，再真实写回模型、完整矩生成c并复算Ac-f；线性配对≤1e-10且loss不增才提交。迭代达限但有效下降的方向可以接受，停止码不授PDE资格。

三个轴使用最新状态，z/x/y与y/x/z交替；最多6轮、18核心访问、5400内层迭代或5400s。NN两路线初值逐位相同、x/y非零、z仅末层为零，完整散射初场严格零。learned每轮固定输出并fresh L-BFGS更新912隐藏实参数，lr1/history10/strong-Wolfe/max_iter10、实际调用≤20；这是普通隐藏梯度，不称精确VarPro。没有显式N×d列库、大J、A*A/B*B、全FE完成器、PC、global Maxwell/Gram因子或Gsolve。旧准确40端口小块消元随原A/A*作用完整计费。

第2/4轮由隔离FE进程读取参考并只返回预登记标量、身份及false用途标记；训练器不接收参考向量、误差图或方向。第2轮三项均>0.5即停；第4轮按三项≤0.1或残差两轮减半且E/H≤0.2分流。validation_used_for_stopping、benchmark_previously_seen及design_informed_by_reference_diagnostics=true；不能声称盲测。每个完整核心/隐藏步先原子落盘全部模型/phase buffers、位置、c/r、RNG、作用次数和预算，再发布committed。未保存的LSMR内部双对角化不称可恢复。

## 3. 完整数值结果

| measured；原 M5 / 5nm / 384hex / p3 / N31968 / 40端口 | 相位 NN 学习隐藏层 | 相位 NN 冻结隐藏层 | 相位 Cheb 控制 | 原门与口径 |
|---|---:|---:|---:|---|
| 完整轮次 / 核访问 | 4 / 12 | 4 / 12 | 4 / 12 | 最多6轮/18访问；顺序使用最新模型 |
| LSMR迭代 / 隐藏实际调用 | 3358 / 53 | 3050 / 0 | 3600 / 0 | 核心上限300；调用不是epoch |
| 接受核心 / 接受隐藏更新 | 12 / 4 | 12 / 0 | 12 / 0 | 真实原loss不增并完整落盘 |
| 内层停止码 / 最大真伴随残差比 | {'2': 3, '7': 9} / 0.233345428178 | {'2': 5, '7': 7} / 0.865666164339 | {'7': 12} / 0.534028140977 | 停止码不是PDE PASS；完整线性及伴随残差在内层CSV |
| native / augmented | 0.444550296118 / 0.444550296118 | 0.743141789453 / 0.743141789453 | 0.234159905921 / 0.234159905921 | 各≤1e-6 |
| 独立total原方程 | 0.210584258216 | 0.35202757449 | 0.110921959839 | ≤1e-6 |
| 总E / 散射E | 0.0909492970041 / 0.132626683892 | 0.325736416109 / 0.475004668693 | 0.679276464946 / 0.990553945539 | 各≤1e-4；原参考分母 |
| 总H / 散射H | 0.0908650488725 / 0.132884263175 | 0.325086772322 / 0.475418400627 | 0.677290535238 / 0.990493647966 | 各≤1e-4；原参考分母 |
| 总scaled-curl / 散射scaled-curl | 0.0908650488725 / 0.132884263175 | 0.325086772322 / 0.475418400627 | 0.677290535238 / 0.990493647966 | 各≤1e-4；原参考分母 |
| 六点total/scattered复E/H最大误差 | 0.17134242906 | 0.554634224508 | 1.00503251571 | 六点×三分量全部保留；≤1e-4 |
| 完整total复通道 | 0.0928265863582 | 0.233800809649 | 0.562815812346 | 每类完整40复向量；≤1e-4 |
| 完整scattered复通道 | 0.164804954815 | 0.415091552771 | 0.999227033565 | 每类完整40复向量；≤1e-4 |
| 完整出射复通道 | 0.0445522630451 | 0.112213058568 | 0.270124315687 | 每类完整40复向量；≤1e-4 |
| 边界面出射复通道 | 0.0432244926555 | 0.105060743578 | 0.25965169218 | 每类完整40复向量；≤1e-4 |
| R / T / A_balance / A_volume | 0.813276294638 / 0.0249526217771 / 0.161771083585 / 0.127944086083 | 0.800102956878 / 0.0675803349757 / 0.132316708147 / 0.282875278619 | 0.837743263883 / 0.113209007213 / 0.0490477289034 / 0.460003379637 | 原残差未过，仅diagnostic |
| R / T / A_balance / A_volume绝对差 | 0.000849795580958 / 0.00750977431815 / 0.00665997873719 / 0.0271670187646 | 0.0123235421792 / 0.0351179388804 / 0.0227943967012 / 0.127764173771 | 0.025316764826 / 0.0807466111182 / 0.106063375944 / 0.30489227479 | 对原同p3参考，各≤1e-5 |
| R00_s / R00_p / R00_total | 0.813235818955 / 2.39556103125e-09 / 0.81323582135 | 0.800034342997 / 2.69389902027e-09 / 0.800034345691 | 0.837583457145 / 4.48993844109e-11 / 0.83758345719 | 零级两极化与和分别记录 |
| 能量闭合 / 最大逐级功率差 | 0.0338269975021 / 0.00739067956833 | 0.150558570472 / 0.0352101876096 | 0.410955650733 / 0.0808396368733 | ≤1e-5 / ≤1e-6 |
| 实际模型完整矩重建 | 2.03083041062e-14 | 4.51077485441e-15 | 1.01413918605e-14 | ≤1e-10；独立旧逐点乘chi |
| 网络q30/q60系数 / 原作用漂移 | 7.81019713919e-15 / 1.55480229647e-11 | 4.48891410955e-15 / 3.85148735803e-12 | 4.59758577681e-15 / 1.98173137992e-13 | 各≤1e-8 |
| FE积分q15/q30漂移 | 1.98029768866e-14 | 4.47537250595e-15 | 2.52786905233e-14 | ≤1e-8 |
| MPC / 端口恢复 | 0 / 7.63303769514e-16 | 0 / 1.90738666237e-16 | 0 / 5.48734809989e-17 | 各≤1e-10 |
| 原G场误差 | 0.132877923857 | 0.475408212906 | 0.990495133406 | 仅隔离评分稀疏G乘法；无G逆 |
| 预登记研究强信号 | FAIL | FAIL | FAIL | native/aug≤1e-3且散射E/H/curl≤1e-3；不授production |
| 实际attempt秒 / 同时自身树RSS采样峰B | 2920.6633467 / 910639104 | 2156.6865337 / 832794624 | 2893.55737274 / 825778176 | 含加载、准入、setup、检查及保存 |
| 停止理由 | ROUND4_FIELD_PROGRESS_NOT_QUALIFIED | ROUND4_FIELD_PROGRESS_NOT_QUALIFIED | ROUND4_FIELD_PROGRESS_NOT_QUALIFIED | 科学分流或原硬预算；不重置 |
| actual / producer联合门 | FAIL / FAIL | FAIL / FAIL | FAIL / FAIL | 两份完整评分，不挑有利版本 |

actual由原未改FTT逐点输出后显式乘chi，再经原完整矩生成；producer来自保存训练状态。两者分别审核，不挑有利版本。全E/H/curl、六点复E/H、四类全部40复向量、原材料/界面区域、逐级功率和原方程均从实际字段重算；不拟合整体相位、不改分母或近零尺度。H_code=curl(E)/(i*k0*mu_r)，scaled-curl=curl(E)/k0，原nm单位不变。

四类通道依次为含背景/入射的total、仿射散射恢复、从total扣除顶部入射但尚未施参考平面相位的outgoing，以及乘原参考面相位后的boundary_outgoing；功率按最后者计算。CSV每行保留物理key/极化/side、候选及参考real/imag、完整向量误差分子/实际分母和逐级功率，不能混用total与outgoing分母。

[相位与资格](records/conditional_operator_qualification_v42.json)、[三路线/初态](records/conditional_core_routes_v42.json)、[内层逐次CSV](records/conditional_inner_solver_v42.csv)、[隐藏及轮次](records/hidden_updates_and_rounds_v42.json)、[隔离标量分流](records/isolated_scalar_continuation_v42.json)、[完整Gate/分母/区域](records/full_numerical_gates_v42.json)、[四类40复通道](records/full_40_complex_channels_v42.csv)、[六点复场](records/six_point_complex_fields_v42.csv)、[功率](records/power_and_energy_v42.csv)、[通道/范数定义](records/channel_and_norm_definitions_v42.json)、[run/source/hash](records/run_index_v42.json)、[资源](records/resource_costs_v42.json)、[tests](records/tests_v42.json)、[修复](records/repair_log_v42.json)。[端到端用途与保存态复读](records/end_to_end_research_use_v42.json)。大数组和完整检查点留ignored，均hash-bound。

## 4. 完整成本、有限修复及投入决定

唯一28800s窗未重开，每条新增上限5400s；资格、实现、成功60s准入、修复、计算、等待、保存和验收都计研究墙钟。首段精确准备时间未保留，首个保留观测前120s作保守截止锚点，明确不是实测起点；未保留准备精确成本UNKNOWN。采集时正式attempt合计9203.93392882s，互斥阶段与嵌套A/K计时分开，不重复相加；发布尾账另补。

串行自身同时树RSS采样峰最大910639104B，不是整机峰或峰值总和。numeric warn12/hard16GiB、临时规划12GiB、新cache/AD≤1GiB、轻2GiB、自身swap/OOC0、CPU-only/MPI1/math/Torch1，保留原CPU/SMT、PSI及系统和384GiB邻增长门。正式ABI核对Torch intra/inter-op均1；初始轻测试inter-op独立记录未保留，不补写历史PASS，最终受影响测试显式核对。

loaded-packet路线实测、可复用准备、研发历史和冷N=1分开。必需网格/native/moments准备不能免费，完整冷N=1及项目精确历史累计仍UNKNOWN。旧10186.178641493432s波库训练和V41失败不是本新从零FTT单场必需前缀，但研发费用永久保留。新Maxwell/Gram因子、Gsolve、全FE Krylov与参考重求全部0，验收G只有稀疏matvec。

普通接线错误已同批最小修复：实际cfg.kx为实值complex，改为先验证虚部严格零后取real；新的相位身份buffer原为整数，触发既有全FP64映射守卫，改为可精确表示的FP64非训练buffer，不改变相位数学。原15项失败记录保留，后续62/64项受影响测试及最终新相位20项通过，Ruff/compileall通过；无full pytest、安装或CI声明。后续若有修复，以完整repair记录为准，不删除初始失败。

用途限制贯穿raw/manifest/checkpoint/compare/seal/reopen，production_initialization_allowed=false、official_candidate_results=false及pde_only_solver_qualified=false。原残差失败时R/T/A全部diagnostic；reference_used_for_training=false、features_reference_exposed=false，但参考标量参与继续判断已明确披露。健康旧算子、准确参考和上游产物未因文档、序列化或网页错误重算。

相位与无相位已有结果分别：BLOCH_FTTNN_CORE_LEARNED 的native 0.938986749611→0.444550296118，散射E 0.999900336902→0.132626683892；BLOCH_FTTNN_CORE_FROZEN 的native 0.939413868293→0.743141789453，散射E 0.999911279035→0.475004668693；BLOCH_CHEBTT_CORE_CONTROL 的native 0.19086785578→0.234159905921，散射E 0.990621722409→0.990553945539。已有中间改善保留；不同批次、分流和现场硬件成本不能直接等同同成本算法优势，未重跑第四条无相位基线。

独立保存态核对：两NN初始模型及buffers逐位相同、初始完整c严格零；冻结隐藏逐位不变，学习终态隐藏参数与零态差范数0.00151493634857。相位buffers全部不变；学习的是隐藏函数，已知kx/ky没有被训练。

三路线均NUMERICAL_GATE_NOT_REACHED；学习相对同相位冻结原残差差值0.298591493335，相对改善40.1796127701%。隐藏层实际调用53次，是否比强控制更准以表中原场和完整成本判定，不能把线性求解或固定相位贡献全算成隐藏学习收益。三路线同严格精度都未通过，资源收益20%无资格；小权重或低RSS不证明战胜传统FE。

学习隐藏层与同相位冻结网络的散射E误差分别为0.132626683892和0.475004668693；这是真实场精度变化，不能抹去，也未达到1e-4门。Cheb强控制的散射E误差为0.990553945539；它的原残差与场精度要分别读，较低loss不自动意味着较准的场。隐藏学习产生的研究变化与合格单场NN资源净收益是两项独立裁决。

关闭当前固定横向相位/r8/native-EUC/LSMR300/最多六轮配置的自动续算；不是证明所有FTT或神经网络无解。保持NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE、FEINN_MAIN_SOLVER_ON_HOLD、NO_VERIFIED_NN_INCREMENT及FULL_TARGET_NOT_QUALIFIED。本批未开监督fit/oracle、rank/seed/loss/载波扫描，也未重复V41无相位第四基线。V41历史对照只作已有实测，不宣称同时硬件隔离或同成本优势。

0.7nm长度×0.14真实三维pilot因learned M5联合门未通过而NOT_RUN，未注册空stage。原50×25×140nm、Si17/120nm、lambda0.7完整3D FE、decimal2e12B整机、ownswap/OOC0和172800s完整冷流程及原门仍未达到；还缺合格神经求解、同精度端到端成本和原尺寸全链容量/精度证据。本支不向其他支线派活，不恢复W0/W1、传统PC、全口面或主线接入。旧M3600较好、Mfinal退化、D0成本否决/D1未运行、FAIL/UNKNOWN及全部费用保留。
保留v42_bloch_fttnn_learned的第2/4轮散射E 0.471857766118→0.132626683892；参考不回传向量，最终结果不按较好场误差挑选。

保留v42_bloch_fttnn_frozen的第2/4轮散射E 0.474484936662→0.475004668693；参考不回传向量，最终结果不按较好场误差挑选。

保留v42_bloch_chebtt_control的第2/4轮散射E 0.997264327626→0.990553945539；参考不回传向量，最终结果不按较好场误差挑选。

<!-- V42_FINAL_PUBLICATION_TAIL -->

有限实际页面检查结果：NOT_VERIFIED_GITHUB_SERVICE_ERROR：三个固定提交页均实际目视到GitHub服务错误页，未显示任务正文、公式或表格；有限检查到此停止；具体可见范围、失败和未覆盖页尾见呈现记录。本地完整文本解析与浏览器目视分开，截图产生不授全页PASS。初始结果发布为ff797df38b9da8a35b1b7621e4b121a70264398f；此尾段只补费用和呈现，不改变已冻结数值源码或原数组。

正式attempt合计9203.933928824961s保持；numeric自身同时树采样峰910639104B；包含轻检查/浏览器后串行各阶段峰最大910639104B，两种口径不混称。自身swap/OOC0，成功60s准入、解析、修复和发布都计入原唯一28800s窗。未保留的精确准备时间、项目历史精确累计和完整冷N=1仍UNKNOWN。最终准确Git、锁/自身清场及最后窗口观察保存在ignored delivery_receipt.json和最终答复，不为自引用SHA重开窗口。

[实际页面范围](records/render_check_v42.json)、[发布尾账](records/publication_tail_v42.json)。
