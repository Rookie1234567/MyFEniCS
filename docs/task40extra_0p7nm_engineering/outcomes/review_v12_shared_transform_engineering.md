# Review V12：共享 p6 内部变换后的工程与数值收口

本轮要回答两个问题：逐 cell 重复存储的 p6 单元变换是否真的接入正式 Gx560 路径；该工程网格是否因此安全并且数值正确地完成完整三维求解。第一个问题有实际 bank event 和 owner/view inventory 证据；第二个问题在完整参考逆见证上遇到严格数值 Gate 失败。Gx560没有进入外层 FGMRES，所以不能据此说完整PC或Full3D迭代不收敛。

## 执行范围和阶段状态

| 阶段 | 已执行内容 | 状态 |
|---|---|---|
| R0 | 冻结 source、B0旧worker、saved outputs、窗口和已有 Gx560/V11 记录；保留所有历史失败 | 完成；正式 source 为 `6d2c54389fe885ecf24d474a8782166ff31f9154` |
| R1 | p6 run-local内部变换 bank 真实接入，记录 builder/cache/owner inventory | 共享存储观察通过；不等于整场RSS下降或inverse物化资格 |
| R2 | worker与profile/dat接线在冻结 source 下实测 | 完成，输入身份见formal run manifest |
| R3 | B0 fresh完整求解；随后独立审计原exit4 worker的保存输出和同离散V10/V11参照 | fresh residual pass，worker物理输出门仍exit4；offline saved-output revalidation PASS |
| R4 | Gx560四q symbolic/numeric、每q探针、销毁前同存库存、完整reference inverse witness | worker exit4；三项required inverse gate失败；不是资源或时间停止 |
| R5 | 条件Gx784；冻结输入路径及SHA见移交记录，格式校验通过 | `INPUT_FROZEN_BUT_NOT_RUN`；R4 Gate 未通过，所以没有启动 |
| R6 | 成本分层、target-readiness和下一候选收口 | 本文和移交/compact records完成；原尺寸仍未资格化 |

## B0 结果：新求解与修正保存输出是不同证据层

B0 fresh worker 在 source `c08c135f0e60198475525cd1c761cb0ba686d948` 上完成80-cell、p6、532-mode、4-q参考模型，solver status为`TRUE_RESIDUAL_PASS`，A6显式residual为`1.6089774391665316e-8`。真实fresh workflow是`1068.5331719600363 s` monotonic，KSP-only为`4.583265167 s`，solver终态快照时钟为`6.211585616 s`；不能用旧4.899 s纯KSP数替代这次KSP，也不应把三种时间相加。tree/cgroup峰为`2,796,560,384 / 3,199,516,672 B`，swap为0、PSS禁用。worker仍因原输出范围判断以exit4终止，status为`B0_CANDIDATE_PHYSICAL_OUTPUT_GATE_FAIL`、official=false。

source `6d2c543` 之后对已保存场独立复核，覆盖532个有序模式、每侧266个通道和保存残差。它复算`R/T/A_balance/A_volume = 0.9842736080926772 / 0.014240518143988908 / 0.001485873763333926 / 0.00148587384621333`，能量闭合误差`8.287925901129256e-11`。完整FE系数与MPC identity和V10/V11同离散记录byte-equal；E/H/curl的零差由相同系数和身份代数推出，没有在本次重新积分场或体积吸收。这是saved-output scope PASS，不能改写原fresh worker exit4。

B0四个q参考因子在销毁前同时存在。raw INFOG19/22分别合计497/445 decimal MB；逐项加1 MB解码后的保守上界为501/449 MB。每q输入hash、NNZ、原始INFOG、factor entries、probe residual和进程树采样见[formal results record](records/review_v12_formal_results.json)。完整setup时间没有可直接复用的全流程stage计时，标为`unknown`，不从workflow减KSP反推。

在这个 fresh run 之前，source `696383d39b60143a2881b753f19659c05bf6769d` 的首次 B0 worker 尝试于 `20261006T120744.861717Z` 因 NameError 在数值求解前失败。worker monotonic `1107.2371964480262 s` 和 watchdog policy `1207.4370952185634 s` 是不同范围；process-tree RSS `2,749,452,288 B`，cgroup peak `3,135,488,000 B`，swap 0，进程后代已清理。修复定向测试为8 passed；初次失败和修复后 fresh run 分开记账，不能把初次启动记成 PDE 结果。

## Bank实际共享范围

变换矩阵用于把有限元单元方向/几何坐标下的局部系数换入内部凝聚块坐标。旧路径可能为相同450×450矩阵在许多实体记录中存放副本；run-local bank把一块只读矩阵作为共同backing owner，让多个记录引用同一视图。工程收益是减少这类重复模板的命名分配；代价是要维护key/basis映射、视图生命周期和后续inverse工作区。该优化只针对cell-interior p6块，edge/face仍走legacy路径。

Gx560正式event `task40_v12_transform_bank_ready`发生在symbolic之前，记录6个实际状态、1个basis、1个matrix template、6次builder调用、1,120次请求、1,114次cache hit以及`0.06642541708424687 s` builder时间。450×450 complex128 matrix大小为3,240,000 B；1,121个矩阵视图指向同一owner。整个named-allocation inventory中logical views含别名为3,843,915,904 B，unique backing owners为215,115,904 B，算术差为3,628,800,000 B。这个差值是登记视图与底层owner字节差，不是进程RSS差，也不是单独的“银行表”大小。

事件owner总数15,047涵盖global/local矩阵、edge/face、索引等更广的对象；不能把它称作15,047个大矩阵模板。bank-ready时inverse build/request计数都为0；这只是预symbolic检查点，不能推断完整attempt的inverse物化数量。future inverse reserve仅是准备预算，不是已分配memory。所有bank字段和范围在[transform bank compact record](records/review_v12_transform_bank.json)中。

实现沿革绑定到 dot 冻结 source `15713d3e09b63f65511c7b7f61fa043fdb23dca5`、blob `ff40105bd9139a856b09987596c961458f84ab0e`、原文件 SHA256 `9ece954f962dc6bab18a02f6b48b53998219fba3f611647a44404757f219b66f`。这是 p4 bank source 适配 p6 cell-interior 的来源说明，不是84-row压缩的资格证据，也不表示本轮访问或修改 dot。

## Gx560：四 q 因子通过探针，完整 reference inverse 有三个负门

正式输入为10×4×14、560 cells、p6、340 modes、四q及原解析缺口。source `6d2c54389fe885ecf24d474a8782166ff31f9154` 在启动时干净。每个q矩阵CSR输入hash在symbolic和numeric阶段保持一致，详细rows、NNZ、CSR SHA和完整raw INFOG均在formal results record中。

| q | rows / NNZ | raw INFOG19/22 decimal MB | decoded conservative allocated/used upper (B) | raw INFOG9 factor entries | symbolic / numeric (s) | factor probe residual |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 28,508 / 15,451,743 | 1,157 / 1,016 | 1,158,000,000 / 1,017,000,000 | 41,320,088 | 0.266416 / 4.443395 | `3.986719e-11` |
| 1 | 28,508 / 15,479,361 | 1,150 / 1,010 | 1,151,000,000 / 1,011,000,000 | 41,253,248 | 0.223935 / 4.242171 | `1.591873e-12` |
| 2 | 28,576 / 15,581,290 | 1,169 / 1,027 | 1,170,000,000 / 1,028,000,000 | 41,789,336 | 0.251091 / 4.501317 | `8.624700e-13` |
| 3 | 28,508 / 15,479,361 | 1,165 / 1,023 | 1,166,000,000 / 1,024,000,000 | 41,269,544 | 0.250979 / 4.910098 | `2.813498e-12` |

表中raw INFOG19/22是原生decimal-MB读数，右列是每个MB桶加1 MB后解码的保守upper bound；INFOG9是条目数，不是字节数。销毁前inventory表明四因子同时live，allocated/used的raw累计为4,641/4,076 MB，保守上界为4.645/4.080 GB；该检查点tree RSS为10,021,572,608 B。q阶段内存、全程tree/cgroup峰是不同生命周期观测，不能相加。q因子探针和完整inverse witness的RHS不同，因此分别与同一`1e-10`门限比较，不要求两类数值相等。

读取已保存generic full-independent witness NPZ并用原分母独立重算，得到：

| 检查项 | 实测/重算 | 限值 | 结果 |
|---|---:|---:|---|
| 完整原参考方程 | `2.0058682739535859e-10` | `1e-10` | fail |
| 两个局部原方程合并 | `1.4183642641040464e-10` | `1e-10` | fail |
| global alpha/port closure | `1.1770163447864681e-11` | `1e-11` | fail |
| 四q generic inverse真残差最大值 | `1.3734523400657947e-11` | `1e-10` | pass |
| 两扇区native action一致性 | `2.344333284555255e-12` | `1e-11` | pass |
| 全部内部恢复 | `8.84512666346208e-17` | `1e-11` | pass |
| 全部端口方程 | `5.043931812872039e-13` | `1e-8` | pass |

局部 twist 0 原方程 residual为`2.8394442214050333e-10`，twist 1为`9.563779087957973e-12`。原生/sector action consistency与内部恢复通过，但这只能定位失败表现，不能证明一个共同源码根因。独立数组复核已把三项失败以原门限精确重现；不调整阈值、不改reference分母、不重放同一case。

## 内存、时间和停止分类

| 量 | 数值 | 口径 |
|---|---:|---|
| Gx560全程process-tree RSS peak | 10,181,664,768 B | worker、watcher及进程树口径 |
| 四q同时live销毁前tree RSS | 10,021,572,608 B | live inventory的同一检查点 |
| Gx560 cgroup memory peak | 10,708,639,744 B | cgroup口径，与tree不相加 |
| 清理后cgroup current | 884,416,512 B | 子进程已清除后读数，不是因子前内存 |
| PSS / task swap / cgroup swap | disabled / 0 / 0 B | profile与任务cgroup口径；不声明不可见Windows主机全机零swap |
| workflow monotonic / watchdog / conservative time-gate observation | 2,089.323 / 2,088.777 / 2,320.812 s | 三个不同clock scope，不能互换或相加 |
| MUMPS reference-PC builder constructor | 29.169 s | 输入矩阵已经存在后的CSR、四q factor-builder和probe计时；不含全局/sector实体和物理局部张量构建 |
| 四q symbolic / numeric timers | 0.992421 / 18.096982 s | per-q timers的派生和，不是完整setup或workflow |
| transform bank builder | 0.066425 s | readiness event；与MUMPS constructor timer的包含关系unknown |
| reference inverse见证局部FFCx恢复动作 | 2次 / 3.191801 s | witness内部已测子步骤，不是完整求解阶段 |

基础准备及全局/sector实体构建完整时钟、MUMPS构造器外完整setup、KSP、完整场恢复/输出、清理单独耗时和R6文档/数组复核的新增ledger debit没有可用独立计时，均保留`unknown/NOT_RUN`。主控 R6 precommit observation 为累计 campaign charge `17395.54872271069 s`、numerical remaining `68404.4512772893 s`，记录和 SHA 见 [cost and repairs](records/review_v12_cost_and_repairs.json)；该观察不是终端结算，文档/Git尾段仍须由主控在同一窗口记账。不从2090秒workflow里减掉KSP或局部计时来制造setup估算。

旧V11 Gx560在numeric前因保守投影gate受控停止；新V12直到四q numeric和inverse witness才停止。本轮worker `WORKER_FAILED` / exit4，派生为`REGULAR_P6_INVERSE_GATE_FAILED`；资源/time Gate都通过，故不记为resource stop。Gx784输入已经冻结并校验，但状态为 `INPUT_FROZEN_BUT_NOT_RUN`；Full3D FGMRES、最终A6、official R/T/A及匹配p4场比较均`NOT_RUN`。

## 下一步与证据边界

唯一建议评估同一四q参考增广算子上的一次完整 residual correction。令 `x=(u, alpha)`，`e=b-A_ref_aug x`，`delta=M_ref_aug e`，`x1=x+delta`，其中 `A_ref_aug` 是 gap-filled reference augmented action，target `A6`保持不变，且不假设 `D=B^H`。全部FE未知量与alpha/port分量一起更新，每q至多增加一次 `MatSolve`，四q总计最多四次；随后按原定义和原门限重新核验完整原方程、两局部原方程和alpha/port closure。该候选没有效果、时间或workspace峰证据，必须由后续review另行授权；不自动发起重放。

原尺寸约15,232 cells / 32,060 full-AUTO modes的全部q factor共存、fill、冷JIT、outer iteration、完整场输出、目标精度和48 h/2 TB路线仍`NO_GO / NOT_QUALIFIED`。旧重复矩阵98.70336 GB推导和V12 bank alias accounting都不是目标RSS预测。不得据本轮Gx560局部因子或两个代表面动作外推全尺寸结论。

紧凑证据： [formal results](records/review_v12_formal_results.json)、[memory lifecycle](records/review_v12_memory_lifecycle.json)、[transform bank](records/review_v12_transform_bank.json)、[cost and repairs](records/review_v12_cost_and_repairs.json)、[target readiness handoff](v12_transfer_and_target_readiness.md)。窗口由watchdog记账；本执行者未修改source或账本，也不执行commit/push。
