# 定向测试与只读审核

## p6 h10 迭代接线组件（2026-11-15，尚非PDE）

为把凝聚后的界面残差正确送入原源转移方法，新增显式对偶提升/限制组件；复相位MPC与多个master不能使用原场展开代替对偶提升。工作站原complex128/int32、MPI1/math1下10项通过，测试父段0.09427119605243206s、RSS105254912B。源文件SHA256 `bfc29fb6e82506ba8d69ec3df40be775050da7a469eb6ef4179dcf47923b6afb`；未建立FE或factor。

显式辅助MUMPS owner按实际CSR nnz在转换前准入，symbolic后冻结并读回有限工作区，记录所有常驻辅助因子而不称无全局因子。4项接口/资源fixture通过；同服务中的真实3×3非Hermitian复矩阵完成symbolic、numeric、probe、第二RHS与销毁。probe残差2.651423303137108e-16，第二RHS完整残差1.1933693396624067e-16；真实因子子段0.4813260920345783s，测试总父段0.596191375516355s，进程RSS峰126951424B。源码SHA256 `78dbe354a0b13555a8e4bb8664a0a3c570bc37ba9e315e130d3e40f7d13e4f12`；两类费用不重复相加。

两个独立测试服务均限2GiB/单CPU/零swap、低优先级。远端证据位于任务专属`preparation/p6_iterative_candidate/test_receipt.json`和`preparation/p6_aux_factor_candidate/test_receipt.json`，相对根为`/home/fenics/Projects/laptop_share/benchmarks/artifacts/pstddm_workstation`。这些是准备资格，不是完整迭代结果；真实入口、端口与完整残差仍须后续核验。旧直接法FAIL及全部费用保留，不重跑旧PDE或全仓测试。

本轮追加的完整FE端口桥验证：复相位MPC、非零内部C/D以及非单位凝聚H的小型真实`PureSourceTransfer→FGMRES`调用链在工作站资格环境通过，13项测试、父段0.30915696267038584秒、进程RSS峰125157376 B，未建立FE或因子。桥源码SHA256为`d82ec28f8e16028af442ffaf648d462a4ce64ca2321239cc45c75238f7b210d6`，测试SHA256为`9a335a9ebd3ae4125be95d88a50c26ecb586bd8f084c6170f47ec79642c60f26`。原始收据为任务专属`preparation/p6_iterative_bridge_chain/test_receipt.json`；独立服务`pstddm-p6-bridge-chain-test-20261115.service`的父时长1.343秒与测试子段不相加。systemd打印的256KiB不代表Python实际峰值；进程峰采用`getrusage`口径，任务swap0。这是接线证据，不是p6整场通过。

## h10正式迭代入口最终检查（2026-11-15）

最终生产候选的定向回归首次21项通过、1项小型夹具失败：3维矩阵在restart=2、max5时残差0.0011182950398320472，没有满足新增的1e-8断言。仅将该夹具restart改为3后，连同新增DAT/失败状态/基线hash/Stage4参数传递检查共7项通过；正式FGMRES30/max100和1e-8门没有改变。首次测试加配置试运行父段0.5888344263657928秒、RSS139059200 B；修正后父段0.26558486092835665秒、RSS131264512 B。既有21项未变检查未机械重跑；两次服务分别1.790秒、1.459秒，父子不重复计费。PDE/factor调用均0，dry-run均退出0。

原始收据分别在`preparation/p6_final_entry_candidate/test_receipt.json`和`preparation/p6_final_entry_candidate2/test_receipt.json`，首次夹具失败保留。最终native接线SHA256 `c2650c487ecebda5f4194814d4ec7693e56340f2e75b346ac840d6486e28928b`，runner `0993964b65c5fb6985207462d2c7181b55726619cc4df88c50bdd13e4377d8ae`，DAT `4f6049fdeb6689f5b11074d00e30faf546876a9d6f6a1cd29491f860dcb3ac83`，新增入口测试 `1de1c827eaadbbbb0a798624b671785f54dad4ff3fcb21f9f10cb5b5b73a222b`。正式运行仍须冻结源码和动态资源准入。当前新入口没有合格JIT donor接线，按实际新编译成本计费，不假称复用旧FE/因子。

## p6 retry1 CSV修复与保存残差补审（2026-11-14）

本次只执行两个直接相关回归：真实保存JSON中“首行无Fourier字段、后续行有12个字段”的导出；旧`passed=true`但残差`3e-7`必须按本任务`1e-10`判FAIL，并拒绝被修改的向量archive。原资格化complex128/int32、MPI1/math1环境中2项通过。真实全部306行JSON经同一生产helper重导出，逐字段读回一致，原三个输入文件hash前后不变。

只读补审逐成员核验原16.41MB向量包的hash、shape、dtype和有限性，重算原残差仍为`3.2085634887236534e-7`，结论`audit_completed=true / numerical_pass=false / official=false`；没有重施原算子、FE构建或factor。子进程含测试/审核/CSV回放0.7906959671527147s，峰值RSS149344256 B；整个受限user-service父段1.482s，父子不相加。任务swap0、退出0。systemd打印的508KiB内存峰与Python RSS不一致，不将其用作实测Python峰值。

远端命令由`preparation/p6_csv_review.sh`执行资格化activation和`python -I -B preparation/pstddm_csv_review_run.py`（均为绝对专用根路径）；单位`pstddm-p6-csv-review-20261114.service`，2GiB/单CPU/零swap。候选文件hash、原始文件hash及结果见`reviews/p6_h10_direct_13p5_retry1_csv_residual/audit.json`，SHA256 `1b7009c36435ab9a96070a56a4887f4ecd44c5b3a003ef5fcbd474d1eb711552`。候选科学数值未改，正式PDE仍绑定旧源码`e7eba2645b58acb8a0871a5f619e69ad61faad2b`。未运行全仓测试或CI，不把补审成功转成PDE通过。

以下是已经执行的检查，不是未来计划。测试经工作站既有 native complex activation 和受限 user service 执行；没有运行全仓 pytest、MPI2/4 或 GitHub CI。

| source | 检查 | 结果与费用 |
|---|---|---|
| `f1ad2aa51e27aa7ae014cf3a6257da8c1338dffd` | `python -m pytest -q src/test/test_pstddm_workstation_profile.py src/test/test_pstddm_source_transfer.py` | 11 passed、4 subtests passed，pytest 0.87 s；服务父段约2.466 s，不能再与子时间相加。 |
| 同上 | native activation、输入 dry-run、监督器/checker帮助入口 | 完成；服务父段约2.029 s。未将这些视作PDE通过。 |
| `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` | `python -m pytest -q src/test/test_pstddm_workstation_profile.py -k n2_local_review` | 3 passed、4 deselected，pytest 0.36 s。覆盖缺失历史数组、合格数组与错误数组拒绝。 |
| 同上 | 六场保存数组独立审核 | 各场结果、精确审核进程时间和RSS见 compact；13.5nm N2局部矩阵复算不可用，其余已保存项目仍审核。 |
| 最终文档 | 六组取回manifest/summary/supervision内容hash与原artifact清单一致；JSON可读；文档数值来源核对；`git diff --check` | 完成；未重跑任何PDE。 |

最初13.5nm direct审核的两次activation路径/参数错误，以及N2缺少原pair数组造成的审核失败均留在原attempt JSON。它们不计作PDE重放，不伪补缺失数组。20712b4只增加未来局部数组及计数保存，并让审核对缺失历史证据明确报告限制，未改数值作用。

11项初始测试与后续3项定向测试不是14个全新测试：后续3项在新增审核分支上执行。13.5nm N2定向测试与其审核位于同一约3.085s服务父段，禁止重复计费。其他checker的内部时间不能代替完整service启动成本；无法从现存记录分离的历史准备成本为UNKNOWN。

ABI进口收据SHA256为`280dbdf428d1e85d2ddf792f2f76afbfec7a88e73e21d2d616d4f2c54277b2b9`，实际native Linux、complex128/int32、MPI1/math1；真实路径见[compact](records/compact_v1.json)。不借用Windows/WSL解释器执行正式计算。

## p6 h10编译器接线修复（2026-11-14）

旧失败在已完成凝聚增广装配后、MUMPS symbolic前发生；原`sysconfig.CC`仍含搬迁前WSL路径。修复只为公开PETSc/MUMPS C桥接提供当前资格化prefix内编译器和sysroot，保留旧默认守卫，不改FFCx编译配置、积分、求解控制或资源门。正式runner在FE前加载/核验同一桥接，独立retry保持原h10数学输入。

工作站原ABI下实际2×2 complex128测试完成symbolic、numeric、完整残差及普通KSP对照：残差`2.1593801109342874e-16`，与普通KSP解差0，清理通过，probe内部0.38676974922418594 s；这是API小测试，不是PDE通过。原始`preparation/p6_api_probe/actual_api_result/result.json`。相关7项测试通过（0.102 s），覆盖显式编译器上下文、旧默认、独立retry身份、JIT缓存同数学/ABI/hash与污染拒绝；另实际执行retry dry配置和FE前桥接加载，见`preparation/p6_repair_targeted.log`。不重复全仓测试。失败产生的1048.3153135273606 s费用和原输出保持不变。

## p6入射积分、内部direct入口与缓存资格（2026-11-15）

最终源码afd415d3f5eae03e30d223d1d794008812891cd5。原生complex128/int32、MPI1/math1环境下15个相关测试通过，pytest0.50s、测试父段0.7355273421853781s、RSS峰219766784B；service父段2.777s，父子不相加。真实p6 public wrapper经真实DtN impl走过guard，以装配前log哨兵退出；variable-p反例仅隔离更早的degree-plan资格门，真实resolver及待测guard保留。另验nonassembled/action-only拒绝及精确cache旧/新hash对；无PDE/factor。

首轮2失败/21通过保留：variable-p夹具先触发degree-plan门而非待测guard；临时候选目录名意外命中-k筛选，使旧p2路径测试在临时位置找不到输入。修正夹具和明确选择后仅运行相关测试，不为包装错误启动PDE。更早5项wrapper及1项CSV-cache回归的source/hash/费用亦在compact中分列，不把这些当新PDE资格。

主控对retry2/3/4原始artifact清单逐项核验小收据hash；独立重算retry4 workspace公式、原始INFOG与候选ICNTL23关系，确认numeric_calls=0、595样本任务swap0和后代清空。审核完成不转授数值PASS。测试及原负回执见[compact](records/p6_h10_diagnosis_retry4.json)。未运行全仓测试、MPI2/4或CI。

## 用户授权的380GiB宿主保留线（retry5准备）

仅`workstation-p6`从400GiB改为380GiB（408021893120 B），supervisor初始门、运行采样、收据和worker/MUMPS观察共用p6常量；旧p2仍400GiB，64GiB任务cap、零swap、380GB磁盘线及原费用/精度门均不变。原生ABI下3项定向测试通过，pytest0.08s、测试父段0.1452377438545227s、RSS峰108085248 B；整个受限服务1.173s，task swap0。测试包括真实admission callback字段传递及future+margin不足拒绝、profile隔离，以及用原retry4观测值重算预算。后者在新保留线下预测工作区35009MB可满足22457MB，但不代表新现场或数值通过。

测试没有FE装配、factor或PDE；实际启动仍须新run的动态资源准入。候选文件hash与费用见[准备收据](records/p6_reserve380_preparation.json)。旧400GiB停止记录不改写，不把新授权清零旧账。

最终测试文件仅去除EOF多余空白后，同三项再次通过：pytest0.10s，测试父段0.20055988058447838s，RSS106561536 B，服务父段1.269s；两次收据均保留，不计成6个不同测试。最终生产文件hash与首次一致。

## p6 显式端口接线和诊断输出（迭代准备）

工作站资格化 ABI 中，新类型入口与原 Stage4 外部求解接口的定向回归通过（exit 0），测试父段2.5747447507455945秒、进程RSS峰214220800 B，PDE和factor调用均0。新路径保留同一次装配中所有非零原C/D和原H，以及实际凝聚C/D/H；诊断结果即使不具备官方资格也保存各模式功率、体吸收和必要场对照，显式标注official=false。完整残差仍须正式运行后的独立原生核验，不以夹具通过代替。

对应文件SHA256：`pstddm_stage4_hook.py=99f1f7291ad2f04c1d404b5ba4857886c88f656c7603eb6e5021e96770ef1b7a`；`dtn_port_3d.py=a6c8621f4a40259d11a549a4e459ba335d646b43fe181ba73b8f24e6b8b1bacd`；`common_3d_case_flow.py=d8cc48a7395cee8fe76c7975e428d2bb6ea474c829d677d945c5300da70743d7`；测试文件`b4cb1d476d4ba20b526a605f5d26a45918d3ae2c76aef5a3823a3092fec49f74`。原始收据位于任务专属`preparation/p6_stage4_hook_candidate/test_receipt.json`，独立服务`pstddm-p6-stage4-hook-test-20261115.service`，2GiB/单CPU/零swap。完整迭代PDE尚未启动。
