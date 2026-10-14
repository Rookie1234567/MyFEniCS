# W0.7 V13 consistent fixed BAL_H modal surrogate：实现与分阶段资格记录

**当前状态：V15注册 tiny 真实 FE 的 240 步预算已用尽，但原 A 残差门未通过。240/240 次 V15 modal-row 检查通过，attempt 序号连续8–247，最大独立重算 `eta_inf=7.753508102198664e-14`；RIGHT FGMRES reason=`-3`、240/240，独立原 A relative=`3.189718552739508e-7`，高于原 `5e-9` 门约63.794倍。因此只能判为本预算内未收敛，不能称为V15行门失败、脚手架错误、停滞或已证实PC缺陷。240步报告的PETSc rnorm按30步间隔持续下降，但不是逐步独立真残差。test347毁后快照断言未执行；V15新一场正式M400及五项最终残差/recovery/EH/official RTA/physics均`not_run`；V14真实M400已完成S_B 800/800列及owner LU，随后原modal-row PC门失败，根因仍`UNCONFIRMED`。剩余1/2大型额度保留此前条件式授权但未满足tiny完整收敛和生产内存合同前提，当前不启动。**

| V15记录 | 结果与边界 |
|---|---|
| 240步真实FE | [completion JSON](../../../results/task041_v15_tiny_fe_fgmres240_serial_attempt_20261014T125426Z/serial/pytest_basetemp/test_task041_v13_real_fe_conde0/v15-modal-evidence/tiny_fgmres_completion.json)、[轻量machine record](records/task041_v15_tiny_fe_fgmres240_terminal_20261014.json)、[Response V17](../response_v17.md)。原A分子=`0.29822161297582517`，RHS范数=`934946.4789603328`，输入RHS未变。PC attempt/success/记录各240；240条本次行门全部通过，但这不是完整方程收敛。 |
| KSP曲线与设置 | 真实A尺寸2172×2172；FGMRES、RIGHT、restart请求/源码setter为30、max_it=240、rtol=`5e-9`、atol=0、零初猜。PETSc rnorm在30/60/90/120/150/180/210/240步为144.8159/30.86116/13.89476/5.71560/2.76555/1.20295/0.606899/0.298222，持续下降；restart getter unsupported，不能写成实测getter值。 |
| 技术裁决边界 | 60步旧尝试是独立失败样本，relative=`3.300847332920077e-5`；本次60步报告值与其终点相同不合并曲线。V14首场M400 outer PC失败原因仍`UNCONFIRMED`。下阶段只待ChatGPT裁决是否另批同tiny、更高的有限预算，以及是否先审restart30与固定B/S_B的外层收敛效率；本轮不改PC/门限、不启动M400。 |

下方V14内容为历史快照，保留原始分类和证据，不代表当前终态。

## 历史：V14本批首场正式warm终态与技术边界（2026-10-14）

| 项目 | V14实测 | 边界 |
|---|---|---|
| source与运行 | unit task041-v14-main-warm-20261014t004907z.service；Invocation 686efe6ec9324b5bbe75a796a758d545；source HEAD f969d413bde02339b673a9636f42582a1879f657；MPI8 map [0,1,13,14,15,16,17,18]；default/unbound；producer reused、QEP未重算 | 本场真实调用链越过此前callback/SUP两个启动错误；旧失败raw保持 |
| fresh authority | 初始aggregate MemFree 863,557,566,464 B，node1 539,427,512,320 B；outer workspace八rank有效、10 external gates全真；B+delta+W=55,613,354,496 B < cap 85,899,345,920 B | 资源/authority实际通过，不是容量拒绝 |
| 固定B与构造 | S_B 800/800列、owner LU ready；same_B_objects_for_all_LDU_terms_and_modal_Schur=true；owner rank7 Schur RHS residual `[1.9662845717117538e-13,1.9662845717117538e-13]`通过；factorization 1次、repeat LU solve 2次、residual check 2次 | modal/side solver 0计数只来自`modal_schur_ready`快照；失败时调用计数和失败次owner残差未保存。nested KSP对象数不能代替调用数 |
| outer数值 | iteration 1 global/top/bottom/modal true relative为0.8561826616833743 / 0.8560583887032607 / 0.8662175033712339 / 7.603007007147926e-14；仍ITERATING。随后PC输出原modal-row relative=1.039223e+00 > 1e-10 | iteration 1 residual不是最终解；失败apply行的rhs/residual/scale/terms/zero标记/apply序号未保存；destroy后snapshot异常是次生诊断错误 |
| 结果与后续 | consumer运行分类IMPLEMENTATION_FAILURE，服务唯一wall 12,811.423691891 s；没有最终五残差、recovery、E/H、R/T/A、A_volume、衍射或physics | 第2场大型构造、M600、h细化不自动启动；50×25 nm、2 TB与48 h未资格化 |
| V5 | 旧276 entry前缀不变，当前278条，charged_seconds 634,900.2474392491 s，SHA dbf7d2211ec476dd11d7fd622dbf6d014c4d0df9da9f58f63157258a52917b94 | warm按Invocation唯一记账；tiny pytest父wall4.235037796199322 s另计；ledger累计不是模型wall |

V14的test350 tiny真实PC/owner-LU/RIGHT FGMRES诊断捕获两次apply：精确零RHS使用组成项scale并通过；第二次RHS为2.646487008256017e-15，严格走非零相对分支，relative为0.20023834354730255并被原1e-10门拒绝。pytest 1 passed表示捕获测试成功，不表示PC数值门通过。tiny near-zero敏感性不能回推M400失败的绝对量或根因。非零分母、精确零判定和阈值没有修改，也未获准修改。

| 时间/内存口径 | 实测 |
|---|---:|
| 旧producer mode-prep wall | 1,460.4700798629783 s；QEP正/负向max-rank solve 316.8529016729444 / 317.0268020199146 s |
| 本次consumer / public phase / service parent / V5唯一service wall | 12,806.358500467148 / 12,809.970051602926 / 12,810.20820791 / 12,811.423691891 s；为不同嵌套scope，不相加 |
| 服务process-tree authority峰 / 专属cgroup memory.peak | 46,615,474,176 / 43,826,028,544 B；均低于80 GiB hard、72 GiB warning，job swap为0 |
| producer mode-prep + 本次失败warm小计 | 14,271.893771753977 s；不是完整cold成功耗时，未发生的后续检查仍未知 |

细节见[Response V16](../response_v16.md)、[V14轻量记录](records/task041_v14_modal_row_terminal_20261014.json)、[失败字段诊断](../../../results/task041_v14_modal_row_failure_closeout_20261014T050244Z/diagnosis_zh.md)和[tiny捕获JSON](../../../results/task041_v14_modal_row_fgmres_serial_diag_attempt_20261014T052616Z/TASK041_V14_MODAL_ROW_DIAGNOSTIC.json)。下一步等待ChatGPT技术裁决现行门与失败行证据保存；未批准前不改生产数学或启动第二场大型构造。

## V12基线与当前资源门

V12唯一Invocation `62c3763e266345e0b094a4f3ba3ae19c`的modal末次solve为32步、reason `-3`、relative residual `0.47290220837766356`，大于`rtol=0.001`；该值也超过近似PC拒绝线`0.1`，所以本次明确拒绝。`budget_exhausted=false`。真实状态、outer停点、46条side记录和嵌套wall口径见[summary](summary.md)。V12当时的node0 floor和单节点读数是历史资源合同。后续用户授权测试改用node0+node1合计384 GiB reserve并取消显式内存节点绑定；当前node1至少80 GiB仅是资源可用性门，不是N1页放置资格。V12负结果和原resource raw均保持原样。

## 首场V13正式warm与callback接线回归（2026-10-13）

首场正式W0.7 p6/h0.70/M400/MPI8 warm绑定clean HEAD `94361c2e24ca1c24b0bce9c0e3d6b368e1482a69`，复用既有producer、未重算QEP；unit `task041-v13-main-warm-20261013t004546z.service`，Invocation `86a98c566c574e34969f5c8dbc58dece`。唯一service/finalizer wall为`1369.03024578 s`。失败原因是控制流程漏转交一个阶段资源核验函数：factory已有V13 fresh-authority callback，但workflow没有把同一个函数对象交给LDU builder；builder因此在构造`S_B`时拒绝。分类为`IMPLEMENTATION_FAILURE`，不是已测得的原方程或残差失败；没有进入outer，也没有official残差、R/T/A或physics结果。

该warm前的clean-HEAD MPI8 ABI-only fresh检查为8/8 rank通过，见[ABI attempt](../../../results/task041_v13_clean_head_mpi8_abi_attempt_20261013T005504Z/native_abi.attempt.json)；它是运行环境资格，不是数值结果。

| 项目 | 证据与边界 |
|---|---|
| warm终态 | [supervision summary](../../../results/task041_v13_main_warm_supervision_20261013T010533Z/summary.json)、[service parent](../../../results/task041_v13_main_warm_supervision_20261013T010533Z/service_parent_summary.json)、[finalizer](../../../results/task041_v13_main_warm_supervision_20261013T010533Z/finalizer/finalizer_summary.json)。fresh资源门通过、无资源终止；pre-exit成员检查通过，service结束后的unit为inactive/dead、MainPID=0、ControlGroup为空 |
| combined stdout限制 | [public stdout](../../../results/task041_v13_main_warm_supervision_20261013T010533Z/log/public_command_stdout.txt)包含多个rank交错traceback，不能逐rank配对相邻行，也没有证据认定运行时源码与clean HEAD不一致；runtime argument对象`not_persisted` |
| 接线修复 | workflow仅在V13 route把factory已有callback原对象传给LDU builder；V12/None路径不读取该V13属性。唯一serial selector `test_task041_w0p7_interfaces_reach_frozen_setup_boundary`通过，父wall`6.385026524076238 s`。测试复用了真实public/candidate helper，但stage factory为fake；用AST执行生产LDU调用表达式，验证callback身份转交。它没有执行真实fresh-authority函数，也不证明真实service下游或warm通过。见[pytest attempt](../../../results/task041_v13_callback_wiring_serial_final_attempt_20261013T022207Z/serial/pytest.attempt.json) |
| 账目 | warm服务entry `task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot:task041_v13_main_warm_supervision_20261013T010533Z`的`1369.03024578 s`已在此前265条entry快照中唯一存在。新serial pytest entry唯一成为第266条，但原append脚本漏加canonical loader读取的顶层累计值；本次仅将该顶层值从`608018.1187479909`更正为`608024.503774515`，entries完全不变。更正后ledger SHA `eb0c96e93082d89ca3a64f43d5513b7097efc4e16987f5d1f17226e44fdc6e41`，见[V5更正receipt](../../../results/task041_v13_callback_wiring_v5_docs_correction_20261013T023305Z/ledger_correction_receipt.json) |

在该首warm历史段收口时，callback转交修复已有一个限定serial合同测试，但还没有取得warm重试批准。随后主控批准并执行了唯一实现错误重试；它在public子进程启动前因独立dispatch脚手架目录冲突退出，详见下一节。这个serial回归不替代真实warm。

## 唯一实现错误重试：dispatch脚手架失败（2026-10-13）

本次是已批准的唯一callback实现修正重试，且确实建立了systemd Invocation `817bc0e2a56e42feb9a8cce040c9a486`。失败不是CPU/资源门，也不是求解器或物理结果：ignored binder为了写runtime config先创建了supervision root，而生产supervisor要求自己用`mkdir(..., exist_ok=False)`独占创建该目录。两者冲突后，MainPID `554733`以1退出；ExecStopPost PID `554762`以3退出。finalizer结论为`launch_manifest_missing`，唯一service wall `0.445147259 s`。

supervisor在`src/runners/task041_supervisor.py:2326`创建目录；随后才写launch manifest（约2338–2342行），再到`_run_phase`运行public child（约2453行）。本次错误发生在第一个动作，因此没有launch manifest、public child、worker/MPI rank、producer/QEP、`S_B`、outer、官方残差、恢复、physics或R/T/A数据。配置中虽指定复用producer，但该producer没有被调用。这个结论来自异常栈与生产调用顺序，不是单凭缺少rank日志作推断。

| 收口项 | 实际结果 | 证据与限制 |
|---|---|---|
| systemd与清场 | Invocation `817bc0e2a56e42feb9a8cce040c9a486`失败；终态记录`MainPID=0`、`ControlGroup`为空、ExecStopPost退出3。postrun host collector未见活动Task041 unit/job/process、重复任务或邻任务冲突 | 最终unit-journal查询为`-- No entries --`；启动/退出由dispatch结果、service stderr及systemd属性快照记录。[systemd/host原始收据及候选脚本diff](../../../results/task041_v13_warm_dispatch_scaffold_failure_review_20261013T092853Z/README.md)。短寿命MainPID/ExecStopPost的`start_ticks`、PGID、SID没有持久化；后续PID缺席不等于同starttime身份证明 |
| V5唯一收费 | 旧270条entry前缀不变；新增该Invocation一次`0.445147259 s`。当前271条，顶层累计`608046.3500231376 s`，SHA `f3a1cd6fe50c5e61eff95830519f1d481ca7b0c7de411becfd75236f9e6fe8d4` | [attempt ID与前缀核对](../../../results/task041_v13_warm_dispatch_scaffold_failure_review_20261013T092853Z/v5_attempt_id_exact_check.json)；由service finalizer写入，不另加ABI或preflight费用 |
| 修复候选 | ignored副本只改两点：binder只创建OUT并要求SUP不存在；final guard检查OUT已含配置且SUP仍不存在。生产supervisor独占目录语义保持 | 候选在[review包](../../../results/task041_v13_warm_dispatch_scaffold_failure_review_20261013T092853Z/proposed/minimal.patch)，没有应用到生产或旧失败raw，也没有再次dispatch |

Review V13限定的一场主warm和一场明确实现错误重试现已分别真实运行。此次重试额度已使用；再次dispatch需要新的例外授权。本次没有完成正式W0.7数值计算，也没有证明模型不可计算。

## 已实现合同

策略ID：`task041_v13_consistent_fixed_balh_modal_surrogate`。实现使用同一固定平衡作用处理LDU各块；8个预定列直接进入最终Schur矩阵，其余列每列只构造一次。owner LU之后检查小系统`S_B a-g`，完整PC输出后再由原全局A modal row检查`L z_side+C a-r_modal`。两者是独立门，不以内部求解替代原方程检查。详细实现对应文件见下方。

1. **一致的固定B对象。** 对bottom/top各自创建并固定一个`FixedPhysicalBalancedActiveTraceAction`；同一对象同时用于`HybridBlockLduPreconditioner.apply`的first与delta，以及近似Schur `S_B=C-LBG`列构造/独立动作核验。B是固定BAL_H近似作用，不是`D^{-1}`。不得只在modal项使用B，而在其他LDU项继续走自适应`SideBalancedInverse.apply`。正式候选的实际side/modal KSP solve计数都必须为0；P4 owner LU调用单独记录，不混成KSP。
2. **8列只构造一次。** 保留旧`build_hybrid_action_modal_schur`默认重复构建行为。V13用独立显式分支或小helper：从sealed采样合同选定8个正/负列，直接写入最终`S_B`；剩余列各执行一次B作用后写入同一矩阵。禁止先构造sample后丢弃再构建；独立action-vs-stored-matrix验证放在单独scope计费，逐项记录列构造和验证作用次数、wall与临时存储。奇异小矩阵、错误符号和正负通道错序都必须拒绝，不允许伪逆、shift或删模态。
3. **两道不同的残差门。** owner LU求得`a`后，先检查小矩阵方程`S_B a-g`，这是LU求解门，不是完整PC门。完整PC计算出`z_side`后，另用原全局A的modal块检查`L z_side+C a-r_modal`；不得用前一门替代后一门。若`r_modal`非零按其原RHS尺度归一；若`r_modal`严格为零，使用原组成项尺度`||L z_side||+||C a||`计算后向误差，尺度也为零时仅精确零残差通过，不得用`max(norm,1)`。两门各自要求有限且误差`<=1e-10`。
4. **owner新增存储限额。** 256 MiB是指定owner上的新增模态存储预算上限，不是实测LU峰或RSS估值。分项计算最终模态矩阵、LU副本、factorization/验证临时数组、FE向量、ghost与通信buffer；来源未知或非有限的必要数组拒绝，不把矩阵/LU复制漏掉或重复计入同一项。进程树/cgroup仍按80/72/8 GiB和node0+node1合计384 GiB资源门独立准入，不预扣将来释放或把payload当RSS。
5. **outer最多一次安全重启。** 不能在活跃outer KSP或PC回调内销毁/替换KSP。只有一次完整restart32/32步窗口返回后，基于原始全局真残差证明确有restart损失，才可在外层`solve`已返回的安全边界最多切换到restart64；用可信当前`x`、同一个原始`f`及PETSc非零初值续解，保留累计iteration/wall/MatMult/side账。没有窗口证据不触发。有限停机另按两个连续16步窗口的最佳global残差及每个仍未过门的block残差判断；每项改善都必须不足10%才可收口，不复用V12的8步门。异常快照仅在iterate可信、输入完整且位于安全边界时写入，其他情况明确拒绝保存。
6. **唯一公开请求。** 复用现有`--task041-modal-solver-policy`单selector传入V13 policy，统一绑定sealed config、public argv、launch manifest、service/supervisor expected policy、worker candidate、consumer actual method与finalizer核验。普通fixed-H6/default与V12 policy不变；不新增第二个方法CLI或按W0.7身份隐式切换。

## 最小文件与调用触点

| 文件 | 触点与职责 |
|---|---|
| `src/solvers/hybrid_fem_modal_block_ldu.py` | `HybridBlockLduPreconditioner.apply`统一各LDU项使用的B；独立V13 builder按“8列最终保留+其余列一次作用”组装；owner LU后检查原Schur残差，完整PC后检查原全局modal row；outer窗口记录、安全restart与有限停止状态 |
| `benchmarks/task041_exact_side_workflow.py` | 在已注册W0.7 staged candidate建立并共享B对象，传递列缓存/owner gate/实际计数；为consumer summary保存request、candidate/setup、actual method、owner LU与原modal-row证据；不得从consumer请求自证期望 |
| `benchmarks/task041_balh_workflow.py`、`scripts/run_case.py` | 让现有单一modal solver policy selector承载V13值，default仍为原路径；config与argv一致 |
| `src/runners/task038_launcher.py`、`src/runners/task041_service.py`、`src/runners/task041_supervisor.py` | 封存request与实际worker/consumer方法比较；按launch manifest唯一runroot核summary引用，不扫描任意latest目录；missing/hash错/identity错为unknown或reject |
| `src/test/test_350_task041_balh_block_ldu.py` | tiny代数/单位列构造一次/各LDU项使用同B/side-modal KSP=0/owner LU额度/原modal row残差及零分母/一次restart保留x、f、累计账 |
| `src/test/test_351_task041_balh_public_workflow.py` | 单selector、default兼容、sealed请求至worker与consumer actual method贯通；缺失和错scope拒绝 |
| `src/test/test_352_task041_service_boundary.py` | finalizer沿manifest→唯一public summary→supervisor summary路径/SHA→consumer summary路径/SHA核验请求与实际结果；漏字段/错hash拒绝，不从consumer自报请求反推expected |

表中列出的是V13实际实现/测试触点。tiny测试证明所覆盖的代数、路由与小网格合同；不能把它外推成M400完整列成本、正式MPI8环境或整场物理资格。实现没有增加独立runner/policy框架，也没有改旧默认或W2路线。

test350的PETSc/代数fixture验证小矩阵、列构造和solver控制合同，不能单独称真实FE。另有test347 registered entity-closure tiny FE selector：degree-6、`2×2×2` cell-condensed几何，每侧6个解析模式（共12模态）；固定B/LDU、原modal row、P4 residual与借用对象生命周期的完整C断言已serial通过一次、MPI2通过一次。该fixture不是QEP模态，也不是M400/800模态或正式W0.7容量样本；MPI2合并stdout没有rank标签，所以保留为1 selector/2 rank-cases，rank-to-summary仍`not_persisted`。

## 分阶段测试与源码身份

| 组 | 范围与结果 | 环境及证据边界 |
|---|---|---|
| A | 23 selectors/45参数，跨attempt累计43 passed、2个MPI2-only serial skip | [071636Z封存的A覆盖表](../../../results/task041_v13_A_B_mpi2_review_prep_20261012T071636Z/A_serial_selector_coverage.md)及[JSON](../../../results/task041_v13_A_B_mpi2_review_prep_20261012T071636Z/A_serial_selector_coverage.json)记录当时的分批覆盖；后续B/C和源码变化按各自receipt核对，旧表不改写。不是最终19路径map一次整组通过 |
| B | 8 selectors/14参数每rank，分批覆盖 | 28 rank-cases是14个参数在两rank的执行，不是28个独立测试定义；部分合并stdout的rank归属未持久化 |
| C serial | registered entity-closure tiny FE完整selector通过一次 | 历史attempt使用CPU14，显式`membind=1` |
| C MPI2 | 同selector、`rc=0`、1 selector/2 rank-cases，父wall`153.515994687099 s` | 最新用户批准的default/unbound策略；两rank ABI和全组清理门通过，但summary行没有rank标签 |
| V13 serial清场/服务合同 | 两attempt共30个节点通过：首段3项，修复test351 fixture关键字后的remaining 27项 | 首attempt的setup-boundary fixture失败和原raw保留；这些mock合同不是OS/MPI8清场资格。父wall`6.377355428179726 s`与`10.62438608892262 s`各唯一计账 |
| 早期dirty-map MPI8 ABI-only | production rank qualification/native ABI 8/8通过；parent wall`2.1766278869472444 s`，不入V5 | CPU `[10,11,14,15,16,17,18,19]`，default/unbound、有效节点`[0,1]`及six-thread/native ABI checks通过；无pytest/数值worker |

最终C MPI2执行当时的V5账目为262项、SHA `64fd8d5ffc3a62aa4e49a8058e81e5701aa0a1107269c35bcae50cf1d2396ec4`；该attempt唯一费用153.515994687099秒，ABI和资源门不计账。C输出78项的SHA清单为`f9bcdc0045418fd60f21b938493a5c12bb5828375fefe851b881e61f1b1ba779`。后续serial合同阶段曾使live V5增至264项、SHA `17376a6343ac65f359f059ad632e9a305ce28a60c683164f6a16539ee6e767ce`；这是历史阶段快照。MPI8 ABI-only不计入V5。callback回归收口时为历史266项快照，顶层更正receipt见[历史V5更正](../../../results/task041_v13_callback_wiring_v5_docs_correction_20261013T023305Z/ledger_correction_receipt.json)。此后唯一实现错误重试增加`0.445147259 s`，当前271项、顶层`608046.3500231376 s`，SHA `f3a1cd6fe50c5e61eff95830519f1d481ca7b0c7de411becfd75236f9e6fe8d4`；精确entry与旧270项prefix核验见[当前账目审阅包](../../../results/task041_v13_warm_dispatch_scaffold_failure_review_20261013T092853Z/v5_attempt_id_exact_check.json)。

相对044347Z冻结的19路径map，C MPI2 attempt运行时包括6个批准delta：`task041_service.py`=`c7670e4030c92ff98a2302d1725736e2141f283e374bf4facac3f3aaab31985d`、test347=`2c77d6d0e058723e54182ce7affc1cc19061e7a70e05c9c8a0ad6023d72c82a1`、test349=`c298046ec4165c4c23505384cd945d4e1158a590b1b12da048f01dd238e5585a`、test350=`070db620498aae86c9373ce3a25350141084c6aa9eaaa061df37455c88d07cca`、test351=`6654c10200a67d52d4a92a905b3b6d4d9c5eacc5e6ca75c6ad038b2e31771973`、test352=`9f87a77c487fc33e715d81a6bdd6498a5765c1d960dc865af34fbf5839667bdb`；其余13项在该运行时map相对baseline一致。A/B跨阶段有更早的test350/351/352、service和test349身份，必须引用各attempt map，不可用这组六项hash替代。本文档和其他三份文档在该运行之后更新；其文档SHA变化不等于数值源码变化，也不修改旧source receipt。

## Service/finalizer证据链与V12缺证边界

V13 service/supervisor链现由实际helper、public route和test352 finalizer合同测试覆盖：sealed `launch_manifest` → 唯一public runroot/外层summary → 被明确引用的`supervisor_summary`路径及SHA → supervisor引用的`consumer_summary`路径及SHA → source/request/candidate/setup/actual-method证据。旧V12外层`summary.json`的`task041.supervised_public_command.v1`只含command、phase result与launch manifest，不含consumer setup；V12缺setup/candidate字段按unknown/false保留，不能从请求推断实际候选。这些service/finalizer正反例由A组test351/test352提供；C组test347只覆盖固定B/LDU的小型FE、原modal row/P4残差与借用生命周期合同，不证明service链，也不替代正式pilot consumer evidence。

## 正式pilot仍需独立资格化

CPU-map参数化后的clean HEAD `f30240b6aa982953a98d4c403d4b3b57db1703b2`上MPI8 ABI-only按显式请求map 8/8通过；这只确认rank/runtime合同。首场warm因callback接线实现错误停止，唯一获准重试则因dispatch scaffold提前失败；两者都没有完成正式W0.7数值计算。callback修复的serial测试复用了fake stage factory并以AST执行生产调用表达式，不代表真实fresh-authority；rank-map serial也不代表MPI8。要取得正式pilot结论仍需成功进入public consumer，并通过：

- 封存配置、public argv、launch/producer identity到真实consumer的路径与实际method证据；
- M400正式模态规模下的完整S_B列构造、owner LU新增存储与实际outer工作量；
- outer原A真残差及五项既定门、必要恢复、完整E/H和物理后处理；
- R/T/A、A_volume、衍射、physics和finalizer实际证据；
- 与正式profile匹配的fresh host/资源/CPU map、MPI8 native ABI、默认内存策略和清理身份。

首场warm和重试的summary、service、finalizer及错误栈分别见前文和[dispatch审阅包](../../../results/task041_v13_warm_dispatch_scaffold_failure_review_20261013T092853Z/README.md)。producer复用已配置，但本次没有实际调用或重算QEP。再次dispatch不在现有Review额度内，需新的例外授权。node1至少80 GiB只属于资源准入，不表示页绑定。W5延期、W2不启动；C serial/MPI2 tiny不改写任何warm失败，也不证明完整模型数值不可计算。
