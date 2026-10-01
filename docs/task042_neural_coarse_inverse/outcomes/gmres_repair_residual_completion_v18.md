# V18：GMRES完整链已修复，残差与场继续改善但未合格

本批执行[Review V15](../review_report_v15.md)。先修复端口返回值重复拼接，随后完成两库G64、条件G256，以及从原V17完整递推独立继续的R；最后全部冻结、求解退出后才由一次FE进程读取旧REF7。**8个冻结状态完整资格0/8；没有原方程1e-6通过点，没有official R/T/A，没有神经训练增量或目标0.7nm/48小时资格。**

重启GMRES在一段搜索后保存修正、再从其原方程残差继续，较长周期保存更多搜索方向、增加正交化开销。R是原全空间LSQR连续递推，既有基只辅助部分方向，其余独立有限元系数仍参与修正。二者改变求解过程，不改变Maxwell方程；G更快降低当前残差，R耗时更长但本轮场误差改善更明显，不能把两种收益混称同精度加速。

| 冻结状态／相同0.7nm micro | R逻辑步 | 原Schur≤1e-6 | 原native≤1e-6 | 独立total-native≤1e-6 | 散射E≤1e-4 | 散射curl≤1e-4 | 完整资格 |
|---|---|---|---|---|---|---|---|
| V17-GPOLY | 6347 | 0.000490220469 | 0.000190109352 | 6.59678284e-05 | 0.000265162174 | 0.0002631196 | FAIL |
| GPOLY-G64-FINAL | — | 0.000342957826 | 0.000133000342 | 4.6151037e-05 | 0.000264299472 | 0.000263170384 | FAIL |
| GPOLY-G256-FINAL | — | 0.000119313169 | 4.6270098e-05 | 1.60556956e-05 | 0.000263932632 | 0.000263799296 | FAIL |
| GPOLY-R-FINAL | 12831 | 0.000146307718 | 5.67386864e-05 | 1.96882894e-05 | 8.07999012e-05 | 7.9819259e-05 | FAIL |
| V17-GNN | 6119 | 0.000594477082 | 0.00023054046 | 7.99973983e-05 | 0.000249203787 | 0.000245918456 | FAIL |
| GNN-G64-FINAL | — | 0.000415112408 | 0.000160982162 | 5.58607113e-05 | 0.000247818583 | 0.00024593027 | FAIL |
| GNN-G256-FINAL | — | 0.000146167412 | 5.6684275e-05 | 1.96694086e-05 | 0.0002455494 | 0.000245237444 | FAIL |
| GNN-R-FINAL | 11903 | 0.000199556375 | 7.73887167e-05 | 2.68538372e-05 | 0.000100199131 | 9.87496399e-05 | FAIL |

以上均为measured无量纲值。native和独立total-native的背景/右端归一化不同，不能用后者较小的数代替原native；增广值与原native在舍入内一致，全部仍FAIL。原端口固定完整b归一化约1.3–1.9e-16、operation约4.9–6.8e-17；恢复约4.6–4.8e-13、原Schur/native恒等式约5.3e-13，slave storage=0；相关接口过原门限，不能代替整体方程。保存残差向量、z组成与v+Qc已由独立reader重算，未仅信status。

两个最终选点在读参考前按原rho冻结为GPOLY-G256-FINAL与GNN-G256-FINAL；R后来显示更好的场，也没有据此改选。这不是新的blind test，REF7仅用于offline validation。参考本次独立total-native=1.43744486619e-12，保留非零实际值，无新LU。

## 1. 数据、source与不变物理

工作树`/home/fenics/Projects/NN-Lab`，branch/upstream分别`task42_neural_coarse_inverse`/`origin/task42_neural_coarse_inverse`；origin为`git@github-myfenics:Rookie1234567/MyFEniCS.git`，canonical common Git为`/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`。base `ccd357885f7f9be84efe3be07868cc94f13d93fc`、初始任务锚点 `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7` 与Review V15均为当前分支祖先。未reset/强推/合并或更改其他worktree。

**23个正式run的actual source全部`d3e5800ee379168ca33bc3dae595de1c8aa71063`**；后置证据reader源码`eb97b4214d4d0a4969ea4eb0038300f0ab214efa`，最终文档HEAD在提交回执中实际报告，不能冒充run source。[run index](records/run_index_v18.json)绑定每个one-run的原dat、resolved、manifest、环境、输入/source及数组hash；[lineage](records/input_lineage_v18.json)保存V17两起点、完整GK与旧Q/U/R路径/hash。新V18滚动槽/ledger/cache独立；旧V17只读。

保留真空0.7nm、grazing1°/azimuth0/s、384hex/p3/h0.175nm/q15、双Floquet/DtN。FE full34050=trace18144+interior13824+slave2082；canonical trace18144、完整上下40端口（20+20）、z18184。四个实际mask单元数192/8/48/136。没有p/h/M/MPI扫描。

Si继续离线读唯一canonical `input/materials/si_optical_constants_v1.json`，表`SI_OPTICAL_CONSTANTS_USER_20260929_V1`；原字符串source0.699999988明确alias到nominal0.7，n=0.999885140474+4.32477054e-6i，epsilon=n*n，mu=1，air n=1；不插值/联网换值。

| SHA256身份 | 冻结值 |
|---|---|
| material | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |
| physical | 2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de |
| complete modes | 93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262 |
| original action packet | 9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454 |
| REF7 | a0610a5a55e7508196b17277e706595c33e4398ace82b245f70b656e6b9ed355 |
| GPOLY V17起点／逻辑6347 | e4b8495c6cd9fdc1e2f0723b64ecbc0732f911e62cb74c04307f13678e1d8602 |
| GNN V17起点／逻辑6119 | 4006c7946e318f86e5fd785ccdc078fb819b70be5b32b3ef97743eeeabcecd32 |

两库各Q3098=共同随机神经G0的1560+局部补充1538；GNN文件1544只读共同前1538。GPOLY也含神经G0，不能称完全无神经。没有hidden更新/新dataset；GPOLY/GNN之差仅是冻结表示对照，尚无相同严格精度成本或神经独有资格。

## 2. F0修复、保存协议与实际队列

旧caller把`BarAction.close`返回的完整z当port再拼trace；现使用`z=bar.close(t,rhs)`，`port=z[nt:]`，公共语义与旧默认restart64保持。真实dat→stage→GMRES→真正BarAction→保存→原audit的40-port复数非Hermitian小回归覆盖错误重复拼接反例，info0/1、callback、零rhs和失败恢复；不是仅测试correction_cycle。真实F0两个V17固定向量接口均通过，只用10次底层S和2次audit。

GMRES先原子保存proposed trace/实际inner/info，再close完整z/port/residual并标audit_pending，审核后最后commit；返回后close/audit/writer故障均可独立读取补审，不重做Arnoldi。未返回周期不能从标量恢复。R每16完整GK双generation保存递推，每64先保存场再原audit；正常slice继承计数/递推，不能把只含场的快照冒充可续算GK。[逐周期](records/gmres_cycles_v18.json)、[checkpoint](records/checkpoint_inventory_v18.json)、[逐audit](records/iteration_history_v18.csv)、[gap](records/recurrence_gap_v18.csv)。

| 配对路径／measured | GPOLY | GNN | 分流及限制 |
|---|---|---|---|
| G64 | 16周期／1024 Arnoldi | 16周期／1024 Arnoldi | 各先8，原rho下降≥10%才续8；第1周期计入正式smoke |
| G256 | 8周期／2048 Arnoldi | 8周期／2048 Arnoldi | 同一库最后G64开始；先4，下降≥10%再4 |
| R独立原V17 GK | 6347→12831／新6484 | 6119→11903／新5784 | G结束仍不合格，从原V17 GK续算；没有G→R混接 |
| R停止 | R_WALL_BOUNDARY，目标13312未到 | R_WALL_BOUNDARY，目标12288未到 | 各B10000，不转额度；不是已证实停滞 |
| 首次原方程1e-6通过／抛光 | not_run／not_run | not_run／not_run | 没有通过点；不强制内部1e-8变成成功门限 |
| 意外修复／重入／GK校正 | 0／0／0 | 0／0／0 | 计划F0不占意外修复额度，费用仍计入 |

G为原barS、M=None，restart仅64或256，每调用maxiter1、callback_type pr_norm、rtol/tol0、atol=1e-8*原完整b范数；所有实际info1表示周期用尽，不是接口bug；全部周期保存并原audit。SciPy现场1.11.4 tol/rtol适配保留，无升级。R每个batch的原S/SH均按实际单向量计数，[配额/分流](records/quota_dispatch_v18.json)保存各准入与停止原因。

## 3. 完整场、通道与功率

| 状态 | total E L2 | total scaled-curl | selected复E | selected复H | 完整40复通道 |
|---|---|---|---|---|---|
| V17-GPOLY | 2.7747849e-05 | 2.75346267e-05 | 2.67202648e-05 | 2.83746106e-05 | 2.96105882e-06 |
| GPOLY-G64-FINAL | 2.76575717e-05 | 2.75399412e-05 | 2.67099476e-05 | 2.83432662e-05 | 2.95674751e-06 |
| GPOLY-G256-FINAL | 2.76191839e-05 | 2.76057548e-05 | 2.67378895e-05 | 2.84802298e-05 | 2.84948931e-06 |
| GPOLY-R-FINAL | 8.45529144e-06 | 8.35283083e-06 | 9.40360981e-06 | 7.16586311e-06 | 3.8974272e-06 |
| V17-GNN | 2.60778864e-05 | 2.57345819e-05 | 2.79327158e-05 | 2.31805253e-05 | 2.03777237e-05 |
| GNN-G64-FINAL | 2.5932932e-05 | 2.57358182e-05 | 2.79726742e-05 | 2.32273978e-05 | 2.04021617e-05 |
| GNN-G256-FINAL | 2.56954738e-05 | 2.56633162e-05 | 2.78780069e-05 | 2.30559692e-05 | 2.00102164e-05 |
| GNN-R-FINAL | 1.04853204e-05 | 1.03338348e-05 | 1.17717219e-05 | 8.7797112e-06 | 6.57195853e-06 |

表中各相对误差限1e-4；E是FE积分L2，curl是同量纲scaled-curl，不是系数欧氏范数。均匀mu=1下H的全域L2相对误差与scaled-curl相对误差相同（derived）；selected复H另由实际场值验算。各状态total场、selected复场、完整40复通道均达到1e-4，但原方程仍FAIL；多数散射场未过门限，不能用大背景total场掩盖。

| 状态（diagnostic） | R00_s | R00_p | R00_total | R | T | A_balance | A_volume | 最大通道功率差≤1e-6 | 能量缺陷≤1e-5 |
|---|---|---|---|---|---|---|---|---|---|
| V17-GPOLY | 0.117644261 | 3.76130948e-12 | 0.117644261 | 0.117645317 | 0.877048618 | 0.00530606522 | 0.00530639731 | 8.34499776e-07 | 3.3208135e-07 |
| GPOLY-G64-FINAL | 0.117644174 | 3.57313742e-12 | 0.117644174 | 0.11764523 | 0.877048562 | 0.00530620781 | 0.00530639728 | 7.7838678e-07 | 1.89469795e-07 |
| GPOLY-G256-FINAL | 0.117643994 | 3.5397038e-12 | 0.117643994 | 0.117645052 | 0.877047877 | 0.00530707083 | 0.00530639687 | 7.68506489e-07 | 6.73961167e-07 |
| GPOLY-R-FINAL | 0.117644803 | 1.12739383e-12 | 0.117644803 | 0.11764586 | 0.877049371 | 0.00530476828 | 0.00530640587 | 1.58806403e-06 | 1.6375927e-06 |
| V17-GNN | 0.117630551 | 2.59842648e-11 | 0.117630551 | 0.117631607 | 0.877026814 | 0.00534157923 | 0.00530625995 | 2.09682808e-05 | 3.53192755e-05 |
| GNN-G64-FINAL | 0.117630523 | 2.62151616e-11 | 0.117630523 | 0.117631579 | 0.877026754 | 0.0053416669 | 0.00530626004 | 2.10282416e-05 | 3.54068629e-05 |
| GNN-G256-FINAL | 0.117630743 | 2.52937055e-11 | 0.117630743 | 0.117631798 | 0.877027052 | 0.00534115017 | 0.00530626193 | 2.07303416e-05 | 3.48882432e-05 |
| GNN-R-FINAL | 0.117640301 | 5.3707221e-13 | 0.117640301 | 0.117641358 | 0.877041477 | 0.00531716529 | 0.0053063559 | 6.3061223e-06 | 1.08093903e-05 |

所有R/T/A为**UNQUALIFIED_DIAGNOSTIC**；[候选CSV](records/candidate_comparison_v18.csv)保存原值与最大差，[完整40复通道](records/channel_observables_v18.csv)逐项保留原键/极化/参考面及复误差。R00_s、R00_p及二者之和明确分列，R表示全部反射通道；A_balance=1-R-T，A_volume来自原体吸收积分，能量缺陷比较二者，不能只凭R+T+A_balance=1自证。

GPOLY-R散射E=8.07999012193e-5、curl=7.98192590218e-5，单项PASS，但原Schur=1.46307718165e-4/native=5.67386863796e-5，最大通道功率差=1.58806402928e-6（限1e-6）FAIL。GNN-R散射E=1.00199130834e-4，不能四舍五入为PASS；A_balance差1.07675454910e-5、能量1.08093903212e-5、通道功率差6.30612229691e-6亦FAIL。GPOLY-G256功率单项虽通过，散射E/curl约2.64e-4和方程仍未合格。

相对V17，GPOLY/GNN的G256原rho下降75.6613%/75.4124%，散射E只下降0.4637%/1.4664%；R原rho下降70.1547%/66.4316%，散射E下降69.5281%/59.7923%。因此残差和散射误差并非同一指标；没有证据宣布唯一困难方向或condition number。

## 4. 全过程费用、资源及比较边界

新增正式one-run监督wall **19905.129134s**（5.529203h）；V6起formal下界 **57413.555143s**。旧辅助unknown保持。同时整树采样峰 **2576646144B（2.399689GiB）**，own swap/VRAM **0B**，全部成本为shared-workstation。

| 正式阶段／shared-workstation | one-run数 | 监督wall s | 真实底层S+SH | 原audit | 阶段同时树峰B |
|---|---|---|---|---|---|
| F0真实接口 | 1 | 3.92732691 | 10 | 2 | 437211136 |
| 两库G64 | 4 | 144.323214 | 2240 | 32 | 498663424 |
| 两库G256 | 4 | 273.427515 | 4192 | 16 | 519000064 |
| 两库R独立续算 | 13 | 19447.1921 | 25566 | 206 | 2496294912 |
| 冻结后唯一VERIFY | 1 | 36.2589721 | 9 | 9 | 667324416 |

有界辅助测试/读取监督wall **77.755331s**，包含首轮夹具失败及两个collector；实现、文档、Git和其他控制开销由不可刷新整批elapsed另计，不加到formal中；更新cutoff后续低负载费用随delivery receipt列。新增持久logical regular **819761584B**，allocated regular **823402496B**；全Task artifact logical **10619202903B**，均在原限额内。

正式launch合计19938.609872s与上表监督wall是不同口径；solve外层树监督19904.077209s、VERIFY外层39.899524s与内层one-run嵌套，不能再相加。R加载旧Q/U/R共98.511371s；原action、bar/投影/三角、audit及I/O有嵌套计时，详见[费用](records/resource_costs_v18.json)，不能重复相加或把历史构建当作免费。新P/A/imageQR均0，历史完整建基/训练成本继续保留37508.426009s的formal下界及旧辅助unknown；新路线费用不是最终模型单次求解证明。

B在数值队列开始前统一冻结为10000s/库；G合计上限1800s/库，GPOLY/GNN实际G收费214.851938/215.844722s，全部库wall9948.695334/9947.008413s。全批真实S+SH32017（S19749、SH12268）、audit265、field8；新GK6484/5784、Arnoldi3072/库，均在原上限内；失败/拒绝/加载/重复audit未减账。新增持久字节（artifact+tmp+results）及全Task artifact量由费用表现场核对，均低于3GiB和20GiB；不删除历史负结果。

从00:39:23Z（08:39:23+08）接手，heavy stop07:09:23Z、deadline07:39:23Z不可刷新；实际求解退出06:47:45Z，VERIFY随后约06:49Z结束，最后只做有界pure reader/tests/文档。交付实际耗时以最终delivery receipt记，不用写文档时的HEAD/时间猜填。

共享CPU每次实际检查核心/邻进程亲和性与拓扑，所有正式run最终选CPU0（不是永久空闲假设）；MPI1、BLAS/OpenMP/Torch1、Loader0、GPU不用，Task自身nice10/I/O idle；独立activation、complex128/int64/同ABI、NN-Lab缓存。原生Ubuntu不要求WSL marker。启动原systemreserve216310038528B+邻增长137438953472B+本任务16GiB=353748992000B；正式最小MemAvailable946886889472B仍超过余量。

计划常驻7.6e9B≤8GiB，整树warn12/hard16GiB、自身swap0、.5秒完整后代监督/独立deadline与自有锁有效。无cgroup委派，执行的是采样触线终止，不宣称连续内核上限；deadline/kill/orphan/邻进程不受影响回归沿复用套件通过。所有正式PSI full avg10最大0，未触原0.1连续3×5s；不放宽百分数规则，无冷却重入。旧generic summary中“WSL-global”是字段遗留名称，本机native Linux，全机swap活动单独诊断不归因自身。

每次只驻留一套大基；G不加载Q/U/R，只原action+40Hhat与Arnoldi向量（derived m64约18.0MiB、m256约71.2MiB，不是RSS）。R复用固定基与image、不存完整Krylov基；数组/投影/三角workspace均含于同时树峰。candidate没有新global S/normal equations/global p4 LU/ILU/Riesz/fallback；只原局部内部恢复与40维Hhat小factor。独立native VERIFY仍复用FE装配审核，不能称全流程“无装配”。source标志、数组所有权及既有基hash见[生命周期](records/resource_lifecycle_v18.json)。

共享负载变化导致部分GK秒数明显变化，不能凭绑核或MemAvailable声称绝对零干扰。未观察到PSI持续压力或可归因的邻任务退化；无可比的独占对照，影响/性能INCONCLUSIVE，没有改邻任务PID/锁/环境/亲和性/优先级/watchdog或系统ABI/BLAS/CUDA。所有[同工作量曲线](records/same_work_curves_v18.csv)与[视图](records/same_work_comparison_v18.json)只使用持久原审核及真实作用/wall；边界缺口明确，不插值，GK与Arnoldi更新不混称同迭代，没有同严格精度加速资格。

## 5. 测试、历史保护与收口

最小F0测试首轮43 passed/2 fixture failures，定位并修正计划内夹具后45 passed；最终数值实现后的Task-focused serial45 passed。证据reader15 passed（包含错误hash/重复z/伪残差/预算非有限反例），raw reader EVIDENCE_CONSISTENT、0/8重算；8个真实dat schema/stage注册和validate-only/定向compileall通过。[测试](records/test_records_v18.json)、[资格](records/qualification_and_dispatch_v18.json)。未因文档/metadata再跑昂贵FE，未做全仓full pytest/MPI2/MPI4/CI；Ruff环境不可用未安装，不声称CI或其通过。

所有旧task/review/response/raw与旧records保留；导航/summary/tests/changed_files和项目进展/模型总账仅新增V18，旧正文byte exact保留。未运行首次pass抛光、新p4参考、旧teacher/heldout seed420620、hidden训练、GPU、p6/F5、最大模型或merge，理由是本批合同/没有原方程资格。GitHub精确Review15页曾两次Cache miss，未取得真实像素；公式围栏/表格/链接本地静态检查与网页视觉资格分别记PASS/NOT_VERIFIED，未改写review。

具体原因：接线与恢复可信；G64/G256合法运行到固定周期上限而未达1e-6；R仍有原残差和场进展，但耗尽本库wall，不能写成停滞；微型模型误差与成本仍不支持最终目标，未确定如何在目标规模满足离散误差、channel/storage与48小时。只降残差不足以证明散射正确，本批不强行宣告唯一根因。

唯一下一建议：仅建议下一份review授权后，对本轮已冻结的GPOLY-R-FINAL做一次固定G256原方程校正，并冻结前后状态、独立比较场与通道功率。它检验R的场改善能否在进一步压低原残差时保留；不新增基、PC、训练、参考或restart扫描，本批不实施，也不保证通过。

分组selective merge manifest见[依赖组](records/selective_merge_manifest_v18.json)；research opt-in不得提升production default。只推送本执行分支，清场后等待review。
