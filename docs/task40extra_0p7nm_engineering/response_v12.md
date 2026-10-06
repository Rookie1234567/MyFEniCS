# Response V12：共享变换进入 Gx560，参考逆门失败后受控收口

本轮在冻结源码 `6d2c54389fe885ecf24d474a8782166ff31f9154` 上完成 V12 的 R0–R6 收口。p6 内部单元变换 bank 已接入并在 Gx560 实际建立；B0 保存场问题已用修正后的输出范围独立复核。Gx560 完成四个 q 分支的 symbolic、numeric 与探针，但完整参考逆见证有三项严格数值门失败，因此没有进入 Full3D FGMRES、最终 A6/物理输出或 Gx784。失败是数值 Gate 结果，不是资源或时间停止，也没有证据证明是源码 bug。

## B0：fresh 求解和保存场复核分层记录

B0 fresh worker 绑定 source `c08c135f0e60198475525cd1c761cb0ba686d948`，输入 `b0_p6_y_orbit_reference_v12.dat`（SHA256 `d4d72a4288aa0313432f7bea668543c60a2716144ce9c8333b2c271367d8f73e`），80 cells、p6、532 个有序端口模式、四 q 和原两单元缺口。完整求解及 true-residual Gate 通过，A6 residual 为 `1.6089774391665316e-8`；worker 在物理输出门以 exit 4 结束，原始分类 `B0_CANDIDATE_PHYSICAL_OUTPUT_GATE_FAIL`、`official_result=false` 保留。fresh workflow monotonic 为 `1068.5331719600363 s`，watchdog 为 `1068.4872141820379 s`，KSP-only 为 `4.583265167 s`，solver 终态快照时钟为 `6.211585616 s`；这些时间口径不相加。process-tree RSS peak 为 `2,796,560,384 B`，cgroup peak 为 `3,199,516,672 B`，swap peak为0，PSS按profile禁用。这个 exit 4 没有被后续离线复核改写。

随后 source `6d2c543` 的输出范围修正与独立 checker 对已保存数组复核通过。它验证 532 个通道（每侧266）、残差代数、物理功率与 V10/V11 同离散保存场；没有重新组装有限元、建因子或重跑 PDE。保存的完整 FE 系数和 MPC 身份与同离散 V10/V11 原件 byte-equal；由相同系数得到的 E/H/curl 零差是代数推论，本轮没有新做体积分或场积分。输出门修复的定向 suite 为 `26 passed in 0.65 s`。重算得到 `R=0.9842736080926772`、`T=0.014240518143988908`、`A_balance=0.001485873763333926`、`A_volume=0.00148587384621333`，能量闭合误差 `8.287925901129256e-11`。因此 B0 的保存场物理结论可复核，但不能把它登记为原 worker 的 official pass。

在该 fresh run 前还有一次 B0 worker 启动失败：source `696383d39b60143a2881b753f19659c05bf6769d`，run 目录 `20261006T120744.861717Z`，因 NameError 在数值求解前退出。worker workflow monotonic `1107.2371964480262 s` 与 watchdog policy 计时 `1207.4370952185634 s` 属于不同范围；process-tree RSS `2,749,452,288 B`、cgroup peak `3,135,488,000 B`、swap 0，后代已清理。对应修复测试为 `8 passed in 0.43 s`；这些启动尝试不与后续 B0 fresh solve 时钟相加。

## Gx560：完成因子探针，严格参考逆门未通过

Gx560 使用 `nonseparable_gx560_p6_y_orbit_v12.dat`，10×4×14 网格、560 cells、p6、340 个端口模式、原非可分缺口，MPI1/数学线程1，complex128；source 在启动时干净且绑定 SHA `6d2c54389fe885ecf24d474a8782166ff31f9154`。独立对保存的 `generic_full_independent` witness 数组按原定义重算后，三项失败及支持性通过项均复现：

| Gate | 重算值 | 限值 | 结果与含义 |
|---|---:|---:|---|
| 完整原参考方程 residual | `2.0058682739535859e-10` | `1e-10` | fail；独立重算与 worker 标量一致 |
| 两个局部原方程合并 residual | `1.4183642641040464e-10` | `1e-10` | fail；twist 0 为 `2.8394442214050333e-10`，twist 1 为 `9.563779087957973e-12` |
| global alpha / port closure | `1.1770163447864681e-11` | `1e-11` | fail |
| 四 q true residual 最大值 | `1.3734523400657947e-11` | `1e-10` | pass；两类不同 RHS 的 q 探针分别复核 |
| 两扇区 native action 一致性 | `2.344333284555255e-12` | `1e-11` | pass |
| 全部内部恢复 | `8.84512666346208e-17` | `1e-11` | pass |
| 340 个端口方程 | `5.043931812872039e-13` | `1e-8` | pass |
| native-action recovery identity | `7.121611304446662e-12` | `1e-10` | pass |
| Schur-port recovery identity | `3.7941182659338744e-18` | `1e-10` | pass |

重算读取了一份已保存的 102,193,354-byte NPZ，校验 SHA256 `99bcd1010b9fbea28cf759217f5dec4dea50422beb47a83b6940056785f0358c`，并按保存的 RNG seed 恢复 generic RHS；没有 FE、因子、KSP 或 PDE 操作。因子数值探针与完整逆见证使用不同 RHS，各自按同一限值判断，不要求 residual 标量相等。现有数组能区分 q 解、局部内部恢复、两扇区动作与 alpha 闭合的 Gate 表现，但不足以证明单一实现根因；源码和容差均未修改。

| q | rows / NNZ | raw INFOG19/22 (decimal MB) → 保守解码上界 (decimal MB) | raw INFOG9 entries | symbolic / numeric (s) | 因子探针 residual / 完整逆见证 residual | numeric-checkpoint tree RSS (B) |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 28,508 / 15,451,743 | `1157/1016 → 1158/1017` | 41,320,088 | 0.266416 / 4.443395 | `3.986719e-11 / 1.373452e-11` | 7,467,511,808 |
| 1 | 28,508 / 15,479,361 | `1150/1010 → 1151/1011` | 41,253,248 | 0.223935 / 4.242171 | `1.591873e-12 / 6.568782e-13` | 8,210,989,056 |
| 2 | 28,576 / 15,581,290 | `1169/1027 → 1170/1028` | 41,789,336 | 0.251091 / 4.501317 | `8.624700e-13 / 2.505050e-13` | 8,961,937,408 |
| 3 | 28,508 / 15,479,361 | `1165/1023 → 1166/1024` | 41,269,544 | 0.250979 / 4.910098 | `2.813498e-12 / 1.051518e-12` | 9,696,276,480 |

INFOG19/22 的原始数分别是 allocated/used decimal MB；表中右侧上界对每个原始 MB 解码值加1 MB后换算为 bytes。四个 numeric factor 在销毁前同一快照中同时存活：raw INFOG 累计为 `4,641 / 4,076 decimal MB`，保守解码上界合计 `4,645,000,000 / 4,080,000,000 B`；同一快照的 process-tree RSS 为 `10,021,572,608 B`。INFOG 数值是 MUMPS 因子内部统计，不是 RSS；逐 q 的 matrix rows/NNZ/hash、完整 raw INFOG 和 factor inventory 见 compact record。q checkpoint 的进程树 RSS 是当时 worker 整树读数，也不能当作该 q 因子独占内存。

整个 Gx560 workflow monotonic 为 `2089.322796093067 s`，watchdog elapsed 为 `2088.7774883890525 s`，conservative-realtime time-gate observation 为 `2320.81170631922 s`；三种时钟范围保持分开。完整基础准备、全局/sector 实体、物理局部张量构建的独立总计时为 `unknown`。`29.169038816937245 s` 是 MUMPS reference-PC builder 构造器的局部 perf-counter，输入矩阵已存在后计入 CSR、四 q factor builder 与其探针；不覆盖前述对象构建，也不代表整个 setup。四 q symbolic 合计约 `0.992421 s`、numeric 合计约 `18.0970 s`，属于内部阶段计时，不与该构造器或全 workflow 相加。共享 bank builder 计时 `0.06642541708424687 s`；与 MUMPS 构造器计时的包含关系没有独立收据。完整逆见证的局部 FFCx recovery action 为两次、累计 `3.1918007329804823 s`；KSP、外层求解、最终场恢复/输出均未运行。

### 共享变换和整场内存口径

bank 只覆盖 p6 单元内部 450×450 blocks；edge/face 保持 legacy 路径。在 `all_spaces_collected_pre_symbolic` 事件中，记录了6个实际状态、1个 basis、1个 matrix template、6次 builder 调用、1,120次 matrix 请求与1,114次 cache hit。唯一 450×450 complex128 matrix backing 为 `3,240,000 B`，1,121 个相关视图共享该 backing。整个 named-allocation inventory 的逻辑视图字节数（含别名）为 `3,843,915,904 B`，unique backing owner 字节数为 `215,115,904 B`；两者差额 `3,628,800,000 B` 是 inventory 字节差，不是测得的进程 RSS 节省。整体 owner 数涵盖变换以外的全局/局部矩阵、索引及 edge/face 对象，不能解释为 bank 模板个数。bank-ready 时 inverse builds/requests 均为0；这只说明该时间点，不能据此推断整场后续逆物化数量。未来 inverse reserve 是预算字段，不是已分配内存。

bank source provenance 为 dot 冻结 source `15713d3e09b63f65511c7b7f61fa043fdb23dca5`、blob `ff40105bd9139a856b09987596c961458f84ab0e`、原文件 SHA256 `9ece954f962dc6bab18a02f6b48b53998219fba3f611647a44404757f219b66f`；它只表示 p4 bank source 曾适配到 p6 cell-interior，不代表本轮访问 dot，也不资格化 84-row 压缩。

Gx560 全场 process-tree RSS peak 为 `10,181,664,768 B`，cgroup memory peak 为 `10,708,639,744 B`，两种口径不相加；PSS 按 profile 禁用。task/cgroup swap peak 为0，宿主换页计数增量为0 pages；不扩展为不可见 Windows 宿主的全机 zero-swap 资格。清理后 cgroup current 为 `884,416,512 B`，后代进程已清除。资源与时间 gate 均通过，所以本次不是 controlled resource stop。V11 的旧 Gx560 记录在进入 numeric 前因 projected gate 停止；阶段不同，RSS 差异不能归因于共享 bank。

## 运行状态、目标尺度与下一唯一候选

Gx560 worker 原始分类为 `WORKER_FAILED`、exit 4；派生状态为 `REGULAR_P6_INVERSE_GATE_FAILED`。Full3D FGMRES、最终 Full A6、官方 R/T/A和同离散 p4 场比较均 `NOT_RUN`。Gx784 的冻结输入为 `input/task40extra_0p7nm_engineering/nonseparable_gx784_p6_y_orbit_v12.dat`，SHA256 `56d9b05bf157a213d608da93e42fdd1dad6377aa9fad96cdd962d3f6086abdd5`，已完成格式校验，但因 Gx560 Gate 未通过而没有运行，状态是 `INPUT_FROZEN_BUT_NOT_RUN`。不把参考逆见证的局部失败扩大成外层迭代不收敛或整个预条件器失败。

本轮下一唯一候选是**评估一次使用同一四 q 因子的完整参考残差修正**：保留全部四 q 的 FE 与 alpha 分量，按原分母做一次受限 correction，再分别核验完整原方程、两个局部原方程和 alpha/port closure。目标是判断现有 Gate 缺口能否由有限精度修正消除；这只是建议，没有效果证据，也不保证收敛。若未来 review 授权，应只做一次有界实验，保持现有阈值，不将多次 correction 累积成隐式容差放宽。新增 RHS solve/correction 的时间与临时内存没有实测值，记 `unknown`；当前记录中的 setup、四 q 因子与全过程峰值只能作为实验规划输入。

下一候选的精确定义是一次 correction：令 `x=(u, alpha)` 同时包含全部 FE 未知量和 alpha/port 振幅，`e=b-A_ref_aug x`，`delta=M_ref_aug e`，更新 `x1=x+delta`。`A_ref_aug` 是 gap-filled reference augmented action，target `A6` 保持不变，不假设 `D=B^H`。四个 q 各至多一次 `MatSolve`，额外 q solve 总数不超过4；之后按原定义与原门限独立重核完整原方程、两局部原方程和 alpha/port closure。时间、总 solve 次数、临时向量/workspace峰以及 FE/alpha 是否需要重建均为 `unknown`。该建议须由后续 review 授权，不代表预期 Gate 通过。

50×25×140 nm 原尺寸、约15,232 cells、32,060/full-AUTO 模态路线仍为 `NO_GO / NOT_QUALIFIED`：没有目标规模全部 q factor/fill 共存、冷 JIT 与完整输出、Full3D 迭代、目标精度或 48 h/2 TB 的实测资格。旧实现按2N份450×450 complex128 得到的 `98,703,360,000 B` 是未共享矩阵载荷推导，不是新实现的 RSS 预测。dot 的 p4 共享思想只作只读参考；84-row 端口压缩未资格化。本轮不操作 dot、工作站或 master。

V12 的正式结果、成本、repair、共享 bank 与交接边界见 [工程收口报告](outcomes/review_v12_shared_transform_engineering.md)、[目标就绪移交](outcomes/v12_transfer_and_target_readiness.md) 与 `outcomes/records/review_v12_*.json`。测试只报告 test summary 中有原始回执的范围；不声称 full repository pytest、MPI4、Ruff 或 CI 通过。执行者没有 Git 写操作；主控负责最终审阅与集中提交/推送。
