# Task41extra Response V12：两单元保存数组复核完成，数值资格未改变

V12 指定的两单元候选重放与保存数组复核已完成：attempt03 用既有 metadata 和 donor 输入建立必要原网格 mesh/space，生成 cells 360、446 的候选张量与 LU 并完成重放；attempt06 只读重算 184 项保存数组并精确复现。**保存证据可复现，不代表候选通过科学门。** attempt06 的 candidate_passed=null、scientific_qualified=false、official_result=false；原 V9 全域 action 门仍失败。attempt03 限于两格局部 producer 路径，没有运行全域 PDE；attempt06 本身没有 FE 装配、因子分解或新候选生成。

目标 active row 87567 映射到 original row 250113，完整 incident cells 为 360、446；对应 local trace indices 为 375、75，保存的周期系数均为 1+0j。该行只占 V9 两列误差平方和的约 0.00627258% / 0.00664272%，是局部机制探针，不能代表全域。

attempt03 producer 源码 SHA 为 196aedecbef5d129588c629fc091682d7a2900f4，consumer contract SHA 为 94e31c40be1796b690d0184f8b7c61de753c15447e02d417758bb0fb333df355；attempt06 checker 源码 SHA 为 9a6ccdcefc12119275f1ce1082f154af5a881241，consumer contract SHA 为 8b6b23fb53cb5c3545f007aeaffbeb51836c9a7a536c25914ddeb23a314fe4bc。两者源码身份不同。attempt03 保存 198 项 producer evidence arrays，共 76,009,104 B；其两格 replay report/manifest 快照为 outcomes/v12_closeout/attempt03_candidate_replay_report.json，SHA-256 2463e322ea72160bfcca7f3345d149ab20e5b017982f1f9ed55010df0afa9876；报告绑定的 donor manifest SHA-256 为 f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465。attempt03 checker 曾因 donor/current-consumer 身份绑定失败；attempt06 在冻结的 V12 consumer 合同下独立复核：data_integrity=true、exact_reproduction_status=EXACT；184 项数组精确复现 producer 的 V9 y/g、j0/j3 y/g 和存储 T 输出。bi/ri/GETRS 记账为 4/8/12，构建与审核分开。candidate_passed=null，scientific_qualified=false，official_result=false。

attempt06 receipt 指向的历史 donor numerical_output 子目录当前不存在。但 V12 走的是合同规定的 saved-only 输入：receipt、producer summary 与合同身份通过，checker 成功完成。缺失该目录不是本次 saved-only 审核失败；没有创建目录。

## Equation1：四行 LHS、RHS 与差值

数值为复数 [实部, 虚部]，difference=lhs−rhs。四行均为 DIAGNOSTIC_ONLY。

| 列 / 状态 | LHS | RHS | difference | gamma 上界 |
|---|---|---|---|---:|
| col0 / j0 | [-4.762050682443149e-9, -1.5346790916144636e-11] | [-4.773028194904327e-9, 2.9103830456733704e-11] | [1.097751246117848e-11, -4.445062137287834e-11] | 3.122697437864631e-5 |
| col0 / j3 | [-4.717884850704184e-9, 4.1289143402356195e-11] | [-4.802132025361061e-9, 1.3096723705530167e-10] | [8.424717465687713e-11, -8.967809365294547e-11] | 3.122697437864631e-5 |
| col1 / j0 | [3.5338961117953668e-9, -9.422673857713023e-9] | [3.550667315721512e-9, -9.720679372549057e-9] | [-1.6771203926145057e-11, 2.9800551483603405e-10] | 6.535864676812025e-5 |
| col1 / j3 | [3.546455671684482e-9, -9.468455636995897e-9] | [3.6961864680051804e-9, -9.720679372549057e-9] | [-1.4973079632069847e-10, 2.5222373555316047e-10] | 6.535864676812024e-5 |

attempt06 确认保存的 producer equation1 数组能精确复现；但上界远大于差值，不能据此称为精确闭合，也不能说“只是舍入误差”。这些数值只提供诊断记录。

全局 native action 行 n_t 只从两格局部和中减一次。下表列出 producer 已保存的四组行级汇总，避免把 n_t 重复分配给每个 cell。

| 列 / 状态 | 全局 n_t（只减一次） | Σ(projected−Jz_r) | native residual row | replayed y−g |
|---|---|---|---|---|
| col0 / j0 | [-138470.11691112156, -79565.22489061575] | [6.803656129660533e-10, 1.2652217491801383e-9] | [-7.275957614183426e-10, -1.2951204553246498e-9] | [-4.71482053399086e-9, 1.4551915228366852e-11] |
| col0 / j3 | [-138470.1169111223, -79565.22489061701] | [-3.216814717005807e-11, 5.584105863072305e-11] | [2.9103830456733704e-11, -2.9103830456733704e-11] | [-4.71482053399086e-9, 1.4551915228366852e-11] |
| col1 / j0 | [197380.97835960763, -276939.84233321203] | [-3.81000315469223e-9, 7.932297792101286e-10] | [3.725290298461914e-9, -6.984919309616089e-10] | [3.6186089680256828e-9, -9.517411705961543e-9] |
| col1 / j3 | [197380.97835961115, -276939.8423332129] | [-2.758801095383368e-10, -1.2566691377475635e-10] | [2.0372681319713593e-10, 1.7462298274040222e-10] | [3.6186089680256828e-9, -9.517411705961543e-9] |



## Signed terms：按 cell、列与状态

每项为复数 [实部, 虚部]。这里表中大数是每格的 J_ui+L_t 局部贡献；保存数组字段名虽为 delta_t，它尚未扣除一次全局 native n_t，因此不能把它单独称为完整 δt。C_S t、Jw、−Jz_r 也按保存的符号保留。

| 列 | 状态 | cell | J_ui+L_t（局部项） | C_S t | Jw | −Jz_r |
|---|---|---:|---|---|---|---|
| col0 | j0 | 360 | [-129747.88502541377, -73967.63393588594] | [0, 0] | [-2.838024767041728e-10, 1.1634531692125288e-10] | [2.2530881195856497e-11, 5.117902574679962e-10] |
| col0 | j3 | 360 | [-129747.88502541395, -73967.63393588644] | [0, 0] | [-2.777538193008683e-10, 1.7062932924808468e-10] | [5.336440796821195e-13, 3.762340298475204e-11] |
| col0 | j0 | 446 | [-8722.231885707675, -5597.590954729749] | [0, 0] | [-4.585214834284269e-09, -1.4255479529516828e-10] | [6.578347317701968e-10, 7.53431491712142e-10] |
| col0 | j3 | 446 | [-8722.231885708286, -5597.590954730462] | [0, 0] | [-4.5918665023757036e-09, -1.5634390115208423e-10] | [-3.2701791249740193e-11, 1.8217655645971018e-11] |
| col1 | j0 | 360 | [185534.10554292504, -259495.37856179665] | [-1.0396159379550074e-22, -4.547019328414741e-24] | [-2.4531091739326786e-10, -5.568449651146966e-10] | [-2.817022490078727e-10, -5.22439684330265e-10] |
| col1 | j3 | 360 | [185534.10554292522, -259495.37856179642] | [-1.0396159379550074e-22, -4.547019328414741e-24] | [-3.441295276497043e-10, -4.692033981169564e-10] | [-1.6920262842839202e-10, -6.026333127527595e-11] |
| col1 | j0 | 446 | [11846.872816682531, -17444.46377141535] | [0, 0] | [3.8364082312080396e-09, -9.170429668568538e-09] | [-3.5283009056843572e-09, 1.3156694635403936e-09] |
| col1 | j3 | 446 | [11846.872816686198, -17444.463771416573] | [0, 0] | [3.773154222178483e-09, -9.183733004751407e-09] | [-1.0667748110994476e-10, -6.540358249948039e-11] |

J_ui+L_t 局部贡献约为 10^4–10^5，C_S t 为零或约 10^-22，Jw 与 −Jz_r 多在 10^-9。producer 汇总时先合并两格局部项，再将全局 native n_t 只减一次；随后保留 Σ(projected−Jz_r)、native residual 和 replayed y−g。小闭合来自大项抵消；不能把局部 J_ui+L_t 当作完整 δt，也不能仅凭单项大小归因。

## Equation2：局部向量残差

下表给出每格、每列和状态的 infinity norm。difference=lhs−rhs。

| 列 | 状态 | cell | ‖LHS‖∞ | ‖RHS‖∞ | ‖difference‖∞ | gamma 上界 | difference / 上界 |
|---|---|---:|---:|---:|---:|---:|---:|
| col0 | j0 | 360 | 1.9012559963845843e-9 | 1.9893058914033675e-9 | 6.521154801185275e-10 | 3.1334934647118606e-12 | 208.2 |
| col0 | j3 | 360 | 1.3679745787054283e-9 | 1.4874306902266859e-9 | 8.346086973458854e-10 | 3.1334934647118606e-12 | 266.3 |
| col0 | j0 | 446 | 1.9336136905692177e-9 | 1.9131203216436326e-9 | 1.1403516360615646e-9 | 3.1334934647118606e-12 | 363.9 |
| col0 | j3 | 446 | 2.010453938601569e-9 | 2.2392934260041624e-9 | 1.1274675610647538e-9 | 3.1334934647118606e-12 | 359.8 |
| col1 | j0 | 360 | 3.0416747256727e-9 | 3.423871876925375e-9 | 1.6697222606911659e-9 | 3.1334934647118606e-12 | 532.6 |
| col1 | j3 | 360 | 3.23713778353597e-9 | 3.134575849802426e-9 | 2.149677806942554e-9 | 3.1334934647118606e-12 | 686.1 |
| col1 | j0 | 446 | 3.753030291477094e-9 | 3.534887556612729e-9 | 3.280855501360507e-9 | 3.1334934647118606e-12 | 1047.2 |
| col1 | j3 | 446 | 3.778750263662151e-9 | 4.448223201218713e-9 | 2.2796634990612743e-9 | 3.1334934647118606e-12 | 727.5 |

八个 difference 均超过其 gamma 上界约 208–1047 倍。因此不能用该上界声称“只是舍入误差”；这些局部残差也不是原 full-action 验收门，不能据此归因全域故障。

## 解释边界与后续分析

局部数据包含矩阵重建、LU 求解、矩阵向量乘法以及跨 cell 求和/散射顺序的混合影响。现有分解没有逐项隔离这些来源；**solve、矩阵构造、乘法与累加顺序仍未分清，不能给出唯一根因或称已修复。**

原 V9 全域 action 相对差为 2.6749770637124364e-10 和 5.613598120039757e-10，限值 1e-11，仍为 FAIL。V12 没有重新运行全域 action，也没有更改分母或门限。可供主控评估的下一步是只用既有 Kw、E_R t、δ_i、r_b、r_r、K/J/R 保存数组，按 producer 顺序逐 cell 分解 equation2 向量差；这仍只覆盖两个单元，不包含 FE 重建或全域资格，是否执行由主控决定。

## 六次 attempt、时间窗与资源

attempt01 的 launcher_failure 是 direct inner service 因缺少 strict Task41 marker 而拒绝启动；没有可核验的 service parent 计时，成本为 UNKNOWN_NOT_MEASURED，不是 0。另有一项 preparation 调用把互斥 CLI 参数同时传入而被拒绝，那是独立的准备错误，不记作 attempt01 原因。attempt02–06 service parent 实测合计 510.8661423435005 秒；worker 计时是父 service 的嵌套子阶段，不与父时间相加。

| Attempt | 结果 | 父 service 秒 | worker 秒 / 进程树 RSS 峰值 |
|---|---|---:|---|
| 01 | direct inner service 缺少 strict Task41 marker，启动前拒绝；互斥 prepare 参数问题另属准备错误 | UNKNOWN_NOT_MEASURED | 无 service 采样 |
| 02 | candidate 积分自由度不匹配冻结的 V9 curl/mass form；保留 ValueError | 221.623357508 | 182.010869 / 2,339,008,512 B |
| 03 | 两格候选重放完成；checker 绑定失败，原件保留 | 164.303804870 | 实际 producer worker 148.448733087 s；volume watchdog 子段 152.827745 s、checker 子段 5.166881 s（不是科学 worker 净时）/ 树峰 2,344,722,432 B |
| 04 | checker 错读嵌套 identity schema，错误报告 manifest/summary/contract 不匹配；不能据此认定 donor 真不一致 | 44.125627815 | 9.757220 / 548,532,224 B |
| 05 | checker 读取嵌套状态遇到 NoneType.get 异常；没有数值重放 | 40.833382552 | 35.812023 / 672,522,240 B |
| 06 | saved-array checker 完成，184 项精确复现；attempt06 不做 FE、factorization 或新 candidate | 39.979969599 | watchdog 子段 34.299329 s（不是科学 worker 净时）/ 树峰 670,048,256 B |

attempt03 producer phase detail: 实际 worker elapsed 148.448733087 s；form/evaluator prepare 51.777025161 s、两格 candidate build 3.444857046 s、12 项诊断 GETRS 0.029665038 s。这些阶段与 service parent 及 watchdog 子段分别记账，不相加。
attempt02–06 task swap 均为 0，后代均已清场。attempt06 dedicated job cgroup memory peak 为 504,672,256 B，最终 memory_current 为 126,332,928 B，memory limit 为 1,649,267,441,664 B；PSS 未采集。process-tree RSS 和 cgroup peak 是不同测量范围，不得相减或混称。task cgroup swap 起始、当前、峰值均为 0；host-wide swap 计数仅作宿主诊断，不归因于 task。

attempt06 unit 为 myfenics-case-task41-p0-v12-attempt06-20261024T011456Z.service。receipt/watchdog 记录 exit 0 和后代清场；后续 systemd 读回为 LoadState=not-found、inactive/dead、Result=success、ExecMainStatus=0、MainPID=0，表示一次性 unit 已清理卸载，不是计算失败。

固定窗口 SHA-256 为 4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6，T0 为 2026-10-23T23:12:47.000000000Z；总/数值/收口额度为 21,600/20,400/1,200 秒。attempt06 watchdog 最后保存采样的累计收费为 7,429.282588 秒，当时数值/总窗口余额分别为 12,970.717412/14,170.717412 秒。**这是最后持久化的监督快照，不是已扣除随后文档审阅时间的实时余额。**

资源合同保持：单次新证据最多 512 MiB、累计 raw artifact 不超过 16 GiB、可用空间底线 2 GiB、task 内存上限 1.5 TiB、host reserve 64 GiB、MPI/math threads 各 1、task swap 0。没有放宽数值门、刷新 T0 或重跑正式计算。

## 验证与证据入口

attempt06 使用的 consumer contract SHA-256 为 8b6b23fb53cb5c3545f007aeaffbeb51836c9a7a536c25914ddeb23a314fe4bc，启动 wrapper SHA-256 为 f75f3d2d5ca4d1607b31a912435ed7ded1b103f4f86add970d34523472f4530f。C1 native Linux ABI preflight 通过：项目 runtime Python、PETSc 3.25.6 complex128/int32、SLEPc 3.25.2、DOLFINx 0.10、mpi4py 4.1.2、MPI1。最终源码相关定向复验由主控记录为 3 passed、59 deselected、1.82 s，checker source 为 9a6ccdcefc12119275f1ce1082f154af5a881241。纯 fixture 测试 test_saved_diagnostics_prepare_binds_scope_and_reuses_entry_source_window 为 1 passed in 0.21 s；它检查 scope、entry source 与 window 绑定，不是科学计算测试。

attempt04–06 已运行并保留正式 saved-array checker attempts；本次文档收口没有追加 checker。没有运行全仓 pytest、Ruff 或 PDE；除 attempt03 的必要原网格 mesh/space和两格张量与 LU producer 工作外，没有追加 FE 计算，也没有 CI 通过声明。全域两列复核、200q reference/factor、KSP/FGMRES、完整 0.7 nm 场、A6、R/T/A、最终精度及 2 TB/48 h 目标仍未运行或未资格化。所有 attempt 失败及负证据保留。

- [V12 compact ledger](outcomes/b0_v12_saved_array_checker_closeout_20261024.json)\n- [tracked attempt03 producer report](outcomes/v12_closeout/attempt03_candidate_replay_report.json)\n- [tracked attempt06 checker report](outcomes/v12_closeout/attempt06_saved_array_check.json)\n- [tracked attempt06 service receipt](outcomes/v12_closeout/attempt06_service_receipt.json)
- [attempt03 候选重放报告](../../results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt03/task41_p0_v11_selected_trace_candidate_replay.json)
- [attempt03 checker 失败报告](../../results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt03/task41_p0_v11_candidate_replay_saved_array_check.json)
- [attempt06 checker 成功报告](../../results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt06/task41_p0_v11_candidate_replay_saved_array_check.json)
- [attempt06 service receipt](../../results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt06.service/task41_p0_service_receipt.json)
- [V12 fixed window](../../benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller/execution_window_saved_diagnostics_v12_two_cell_candidate_replay_6h.json)

attempt03 producer report / 两格 manifest 入口 SHA-256：2463e322ea72160bfcca7f3345d149ab20e5b017982f1f9ed55010df0afa9876；report 中 donor manifest SHA-256 为 f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465，198 项 producer evidence 共 76,009,104 B。attempt06 checker report SHA-256：cdbd2a0a8d6ae62b61ad1a45b8bd4f62dae4c69ebb1f0f7923205ac85e4c3739；service receipt SHA-256：0b28a0f2b57aa17d515627097978a5470c7787ca9c61b15c07a0d25b14ae217f。watchdog 与 worker 原始日志的 hash 收录于 compact ledger。
