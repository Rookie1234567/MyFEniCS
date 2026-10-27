# Task41extra Response V15：全域构建完成，RHS校正改善但完整作用仍未过门

**28,000 个 actual-qmetric 局部对象已建成，原两列完整作用均已保存；独立终态审核完成且数据完整，但两列相对差为 5.762574483600798e-11、1.212368464357194e-10，均超过原 1e-11。candidate恢复、200q、准确因子、FGMRES及官方场未运行。** 本轮不是57小时预测导致终止，而是实际完整数值门失败。没有放宽精度或重复全域验收。

本候选在原局部LU解之后，计算原K与RHS的完整残差，再用同一LU最多校正两次，目的是减少局部求解误差。补偿求和 `fsum` 降低求和误差，但增加逐内部行计算成本。V14保存star的局部改善没有保证全域通过；本轮首次验证了这一边界。

## 1. 科学身份及结果

| 项目 | 实际记录 |
|---|---|
| Review / 结果base | `611f3497c4b977b10e783444bcd9c9a8aea9a9c5` / `de2353b9ce46fbbb2c6fd4498ea24139b39d162f` |
| 分支 | `task41extra_phi90_p50x50_g17x20` |
| 科学source / run | `3b8e7f5327ce1905deae658bd0bbb0fa94dba5ad` / `20261026T081134.584306Z` |
| 保存数据审核source | `c14dcdb4f3df5e1f488de6747008edf6d58c0c3f`；不重新署名旧科学产品 |
| 物理 | 0.7nm；50×50×140nm域；居中17×20×120nm Si及原基底，无缺口；方位90°/掠角1°/S；p6、10×200×14、64,120 modes |
| 策略 | `same_lu_rhs_solve`；`same_lu_binary64_products_real_imag_fsum`；最多2次RHS校正 |
| owner | 28,000 classes；5,688,000 active rows、213,024 slave rows；未物化全局矩阵 |
| 完整输出 | 每列5,752,120 complex128；y/g两列共4个NPY，368,136,192 B |
| 最终审核 | `NUMERICAL_FAIL / FULL_ACTION_GATE_FAILED`；audit_completed=true，data_integrity=true，errors=[] |
| 恢复 / official | `NOT_RUN_ACTION_GATE_FAILED` / false；旧donor恢复PASS不转授 |

| 列 | 绝对L2差 | 动态分母相对差 | 冻结分母相对差 | 原门 | 对V9误差改善（派生） |
|---|---:|---:|---:|---:|---:|
| 0 | 1.2824501485040357e-7 | 5.762574483600798e-11 | 5.762574483583106e-11 | 1e-11，FAIL | 4.642倍 |
| 1 | 2.6981026336315675e-7 | 1.212368464357194e-10 | 1.2123684643571926e-10 | 1e-11，FAIL | 4.630倍 |

冻结尺度仍为2225.481253487629 / 2225.4807123031883。本轮y与V9同S/输入的保存y逐元素完全相同，两列 `array_equal=true`、差为0；保存port行保持不变。因此本轮观察到的变化在RHS缩减侧，不是S作用被替换。这个事实没有单独证明剩余误差来自GETRS、矩阵构造或全局累加。最大差行均为active 1622464；本轮未完成该行机制归因，不能直接称为无害舍入。

## 2. 实际成本与57小时预测的边界

| 口径 | 秒 | 说明 |
|---|---:|---|
| 原正式service父段 | 60,758.813495 | 包含run_case、异常下游、清场及原失败checker |
| run_case父段 | 60,704.256561 | 16h51m44；不是成功PDE耗时 |
| fresh owner阶段 | 39,972.508249 | 11h06m12；全部28,000键完成 |
| action列0 / 列1父段 | 3,930.572351 / 3,847.608279 | 包含该列求作用、缩减及保存等；不与service重复相加 |
| 两列RHS核心 | 7,480.509984 | 上述action内子计时 |
| 其中fsum残差 | 6,422.241584 | 112,000次；实际主要RHS成本 |
| 其中GETRS | 533.677784 | 初解56,000次、校正112,000次，共168,000次 |
| 其中完整J乘法 / 更新 | 66.880556 / 4.018585 | 子项，不冒称覆盖所有core开销 |
| 修复后只读审核service / watchdog | 67.921656 / 66.788285 | 独立后续父/子段；0新增数值求解 |
| 全owner kernel/LU/Schur排他分项 | UNKNOWN_NOT_RECORDED | 只有首8键测量，不能外推为全owner实测分账 |

旧失败attempt的57.223小时预测由171,107.654331秒剩余构建、20,496秒四RHS补偿残差情景及14,400秒其他预留相加。它采用首批阶段最大值，不是已运行时长；旧阶段逐样本没有充分保存，无法严谨认定当时CPU竞争或某一内核是原因。异常处理的 `V14ResourceStop` 局部导入遮蔽已修复；用户随后明确批准保留固定截止、把该预测作为观察继续。

最终run首8键kernel均值0.896739秒、最大0.948007秒，LU/R/T均值约0.087970秒；这些仅是prefix校准，不代表全域最终平均。该run预测剩余构建约33,330.888秒，实际owner父段39,972.508秒。最小Gram批处理比较约7%收益未采用，科学S/evaluator保持不变。没有足够子计时把11.10小时owner全部归给kernel或LU。

旧入口失败（10.608686秒）、JIT/identity失败（834.519224秒）、8键后时间准入异常（已有回执751.769998秒，含checker子段）及工程检查全部保留于[v15_preparation](outcomes/v15_preparation/)。工程总成本没有完整父钟，保持UNKNOWN，不把服务时间之和称为整个固定窗口费用。

## 3. 资源与失败后的错误下游

| 口径 | 实测 / 限制 |
|---|---:|
| 同时process-tree RSS峰值 | 555,498,606,592 B |
| task cgroup memory峰值 | 556,689,793,024 B |
| task swap峰值 | 0 B |
| RHS审核process-tree峰值 | 2,345,844,736 B |
| 固定task cap / host reserve | 1,649,267,441,664 / 68,719,476,736 B |
| 局部K/J/LU/R/T/S载荷情景 | 526,373,172,000 B，derived；不是独立owner/RSS测量 |
| 新K / J载荷情景 | 90,720,000,000 / 87,091,200,000 B，不能与总量重复相加 |
| PSS | null，未采样 |

28,000类的K/LU generation identity通过；独立unique backing库存终值未记录，不能把载荷公式说成实测已释放内存。宿主全局swap计数增加5页swap-in、0页swap-out；来源不可归属本任务，保留诊断。任务cgroup与进程树swap均为0。当前owner已随进程结束，不假称仍live。

科学action于2026-10-26 21:50:29 UTC判FAIL，内部helper已返回终态，但外层忽略其返回值，错误进入global physical/surface与carrier构建。错误surface JIT记录670.998592秒，错误carrier最后checkpoint为64/64,120 modes、364,738,048 B、elapsed8163.528219秒；这是前缀，不是完整carrier。所有错误成本仍在正式service父段内。

主控发现后先TERM，未退出再按PID/start identity定向升级清理worker、MPI proxy/launcher；最终所有后代清空。原run仍保留 `WORKER_FAILED / exit -9`，不能改成正常producer成功清理；独立checker中producer_cleanup_passed=false，与watchdog的最终descendants_cleared=true分开报告。不是OOM、时间截止或真实资源不足。此控制流错误已修复并用实际外层调用的最小fixture验证终态返回/异常及finally清理，**没有为验证修复重跑owner**。

## 4. 只读审核修复和所有旧失败

原required checker运行后报 `TERMINAL_EVIDENCE_INVALID`：producer数组digest含shape/dtype头，checker对同一数组误用raw bytes摘要。文件SHA、shape及dtype没有损坏证据。修复仅对artifact digest使用原生产定义，旧recovery-state raw digest保持原口径。

随后只读recheck attempt01因薄入口缺5个window/resource环境绑定被拒；attempt02越过该门，但CLI外层仍仅接受旧固定输出名，未进入数组审核。两次父段分别为5.061229秒、7.421696秒，日志原样保留，attempt02 wrapper的COMPLETED仅表示supervise返回，其嵌套WORKER_FAILED不改写为PASS。修复CLI和原子保存路由后，attempt03在相同固定窗口、相同科学文件上完成真正审核，结果是**审核完成且数值失败**。

最终新审核文件SHA-256：`927d05cfcb568bebda30fc69b712a8ab30e18db0eda1bdbe43f412de58536540`。原checker文件与原service receipt不覆盖。最终checker source为`c14dcdb4f3df5e1f488de6747008edf6d58c0c3f`；11项相关测试通过（1.54秒，资格化本地complex128/int32），未跑全仓测试或新增PDE。终态返回、真实artifact hash/corruption拒绝、新回执名称/脏源码/覆盖拒绝均覆盖。

## 5. 固定窗口、产物与下一步

T0 `2026-10-25T14:39:21.578055399Z`，数值截止 `2026-10-27T02:19:21.578055399Z`，总截止 `2026-10-27T02:39:21.578055399Z`；没有刷新。window SHA `db4674af35db8595f022f6ad909783c61f6c717c12b8f8f0990ecb047161609e`。原累计账、授权追加构建及用户要求预测观察继续均保留，未以新attempt名清零额度。已知互不重叠service/recheck父段合计62436.11598379787秒，不含未计量开发/等待；不是窗口总费用。[窗口快照](outcomes/v15_closeout/window_observation.json)保留末次真实ledger样本，样本后的发布成本仍UNKNOWN。

原始数值根：
`fenics-ws:/home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261026T081134.584306Z`。

四个y/g数组、terminal checkpoint及全部source/input/ABI/window/hash入口在[证据索引](outcomes/v15_closeout/evidence_index.json)。[operator/resource compact](outcomes/v15_closeout/operator_resource_compact.json)汇总真实误差、计数和峰值；[原始阶段摘录](outcomes/v15_closeout/selected_events.json)保留完整timeline路径及hash；[运行索引](outcomes/run_index.json)保留旧run及补审。大NPY留ignored artifacts，Git只收轻量证据。

建议下一review先使用新旧保存y/g、原known/native RHS与maps，分解RHS侧剩余差及误差能量分布，确认是否集中于少数方向/材料/关联单元；不重跑producer/carrier或全域owner。最大行1622464仅是定位入口，不能代表全域原因。本轮没有确认保存该行全部局部K/J/LU等可重开包，旧owner已释放；缺项须先盘点，不能声称可完全离线局部重放，更不能未经新决策再次构建28,000键。当前没有证据支持第二数值方案或降低门限。

全域恢复、200q、因子、参考逆、FGMRES、目标A6/官方R/T/A、网格/mode最终精度与完整冷流程2TB/48h均未通过；不合并master。
