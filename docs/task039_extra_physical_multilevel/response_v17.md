# Task39extra Response V17：p4 BLR 单配置收口

## S5 首屏结论

本轮验证了一个显式 opt-in 的 `physical_p4_blr_bal_h_v16` 配置：直接求解会保存消元产生的矩阵块；BLR（块低秩压缩）用较少数据近似其中一部分，尝试节省因子内存，但代价是回代误差需要逐项检查。它仍然是全局消元因子，不是 factor-free 的迭代预条件器。形式上沿用 p6/h10 的物理宿主模型，但本批只分解并回代 p4 的 `53164` 行增广矩阵，没有执行 p6 outer solve。

| 必答问题 | 正式结论 | 证据与边界 |
|---|---|---|
| 实际压缩了什么、减少多少 | 后端条目从 `53417584` 降到 `53040280`，约 `0.706%`；完整树 RSS `R_peak=0.9700174654134085`，factor-live `R_live=0.9700174654134085`，约降 `3.0%` | BLR/旧 Q1 均为完整 parent process-tree 口径；独立 checker 与 parent resource stream 一致。 |
| 其他内存口径 | allocated upper `2343000000 -> 1693000000 B`，降 `27.7%`；used upper `1382000000 -> 1420000000 B`，反而增 `38000000 B`；常驻 inventory `2906619390 -> 2256619390 B`；workspace 两边均 `17825792 B` | allocated/used 是后端工作数组 upper 口径，inventory 是对象账；RSS/PSS 是进程树驻留口径，不能互换，也不能用 allocated 的下降替代 RSS Gate。原生条目已实测，`53040280/53417584=0.992936707882558`，即约少 `0.706%`；只有可选 wrapper 字段未填，不从 `ICNTL(38)=600` 推断。 |
| 是否保住有用的全局纠错 | 三个裸 BLR 回代均通过本轮筛选线：`rho<=0.5`、field L2/scaled-curl `<=0.25`；native A4 identity 误差约 `1e-17` | 这是 p4 三 RHS control 的质量通过，不是完整 p6 PC 或 Maxwell solver 通过。没有 refinement、第二次 solve 或参考解进入 BLR 回代。 |
| 完整 p6 与非可分三维是否通过 | `S3 original=not_run`、`S4 notch=not_run`；完整 p6、非可分、E/H、R/T/A、`A_volume`、80 模式和守恒均 `not_run` | `R_peak/R_live=0.9700174654134085` 同时不满足 `R_peak<=0.90` 或 `R_live<=0.80 and R_peak<=1.05`，故没有 S3/S4 准入。 |
| 下一步保留什么 | 关闭这个固定 BLR 配置，保留其 hash-bound p4 control 作为研究证据 | 不试新 epsilon、不自动进入 p6；TRACE bundle 的 `ICNTL(49)` public getter unsupported，本轮不展开新的 49 调查、不改变策略、不升级 ABI、不启动 5 nm/0.7 nm。BLR 类方法并未被一次配置否定，但本配置没有足够内存收益。 |

因此最终状态是 `STRONG_BUT_INSUFFICIENT_MEMORY_GAIN`：`quality_pass=true`，但 `admit_s3=false`。`S2_BLR_CONTROL_PASS` 与 `DISCRETE_SOLVER_OUTPUT_PASS` 只描述这场 p4 控制输出，不能改写为“有效完整 PC”。

## 1. 身份、模型与正式运行

| 项目 | 值 |
|---|---|
| 分支 / base / formal source | `task39extra` / `972393f41e1cc14af87022d2997ddc5936c0f4e4` / `24bd767e6b0d158ac20deb360a135f10c0611ede` |
| 模型 | 13.5 nm、原始 Full3D、p6/h10、252 cells、80 DtN modes、MPI1、线程1；形式模型为 p6/h10，本批正式矩阵范围是 p4 `53164` 行增广控制，未做 p6 outer solve |
| ABI | PETSc scalar `complex128`、integer `int32`；DOLFINx `0.10.0.post2`、PETSc/petsc4py `3.19.6`、SLEPc `3.19.2`、Basix `0.10.0`、mpi4py `3.1.5` |
| MUMPS身份 | linked `/usr/lib/x86_64-linux-gnu/libzmumps-5.6.1.so`，strings/header/package/manual 均为 5.6.2 身份；没有 ABI 升级 |
| physical / mode SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` / `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| S2 input | `input/task39extra/v16_s2_blr_control.dat`；input SHA `80773699be0a210d67f074661be48b78526bf3257c0c57299e9b28371d552cf9` |
| run directory | `results/euv_grazing1_phi0/task39extra_v16_s2_blr_control__full3d_iterative__mpi1__Mna/20260913T163912.716491Z` |
| output status | `physical_p4_blr_v16_summary.json.status=S2_BLR_CONTROL_PASS`；`official_result=false` |

三个右端保持 Review V16 的固定顺序：`A2R160_BAL_H_p4_01`、`A2R160_BAL_H_p4_02`、`LIGHT448_BAL_H_p4_09`。每个 packet 都绑定 input/reference/g/mode/physical hash；三次均 `factor_solve_call_delta=1`，没有隐藏的 setup solve 或 refinement。

S0 修复保留了 map guard：只排除档案描述等元数据，继续核对实际几何、自由度及 MPC 数组的形状、dtype、字节哈希和主从关系。存档 p4/p6 map 与复数原映射/共轭转置对偶测试通过；本场 p4 映射再次核验。没有重跑旧接口 PC，也没有叠加旧 I4、C_U/S-p2 或 recycling。

S1 复用的原 Q1 来源为 `6a8b273c383d5bd9da37d6630a48bd24d6a90cce`，没有补跑未压缩因子：

| 固定 RHS | 原 Q1 的原 A4 相对残差（限 `1e-10`） | 场 L2 / scaled-curl（各限 `1e-8`） | MatSolve 次数 |
|---|---:|---:|---:|
| 01 | `4.2425248271538786e-11` | `0 / 0` | `1` |
| 02 | `1.5748080059992652e-12` | `0 / 0` | `1` |
| 09 | `6.55690292958073e-11` | `0 / 0` | `1` |

零场差表示复现了已存的同离散参考向量，不是连续物理误差为零。Q1 在三次回代后统一评价，S2 逐次评价并立即保存；两者使用相同公共内核、矩阵和三个输入，矩阵与因子均保留至第三份场评价完成。比较窗口分别有 `75 / 66` 个连续 parent 样本，临时数组和保存成本计入各自全流程。

## 2. 控制是否真正生效

本机公开 PETSc–MUMPS 接口在 symbolic 前读回并设置了 `ICNTL(35)=2`、`CNTL(7)=1e-5`、`ICNTL(10)=0`、`ICNTL(37)=0`，并保持 `ICNTL(22/31/32)=0`。numeric 后和每个 solve 后都读回 `ICNTL(35)=2`、`ICNTL(10)=0`、`CNTL(7)=1e-5`。这证明控制落到了本场使用的后端接口，但不把 CNTL(7) 当成 A4 残差容差或场误差保证。

| 控制/字段 | 实测读回与解释 |
|---|---|
| `ICNTL(35)` | symbolic 前设置并保持 `2`；BLR 存储路径实际启用 |
| `CNTL(7)` | symbolic 前设置并保持 `1e-5`；仅是 MUMPS BLR 块压缩阈值 |
| `ICNTL(10)` | `0`；每个 RHS 只有一次后端 MatSolve，不允许隐藏迭代改进 |
| `ICNTL(37)` | `0`；没有再叠加另一种贡献块压缩策略 |
| 默认 `ICNTL(36/38)` | post-symbolic public readback 为 `0/600`，只作本机默认记录 |
| `ICNTL(39)` | public getter 返回 error 62 / unavailable；手册值 `500` 只作文档边界，不冒充 runtime readback |
| `ICNTL(49)` | TRACE bundle 记录 public getter unsupported；本轮未展开新的 49 调查，也未改变 49 策略；MUMPS 5.6.2 公开控制没有可用的 adaptive precision storage control，因此保留 `complex128` |
| native BLR字段 | `INFOG9/35=53040280`、`INFOG29=53417584`、`INFOG36/37=1405 MB`；原生条目比 `0.992936707882558` 是从实测字段派生，不由 `ICNTL(38)` 推断；可选 wrapper `compression_ratio` 字段为 `null` |

MUMPS身份、手册章节和公开 getter/setter 记录见 [primary identity](../../benchmarks/artifacts/task39extra/p4_blr_v16/root_engineering/mumps_5_6_2_primary_identity.json) 与正式 summary。`INFOG19/22` 是本机后端给出的 decimal-MB upper records，不能和 process-tree RSS 混称。

排序、缩放及主元的实际 post-symbolic 读回为 `ICNTL(6/7/8/14/18/28/29)=7/7/77/20/0/1/0`、`CNTL(1/3/4)=0.01/0/-1`。symbolic 内存估计取 `max(1558,1558,1405,1405) MB`，按原 V11 padding/配额公式设置 `ICNTL(23)=3127 MB`，与 Q1 配额相同；没有按结果调参。

## 3. 三 RHS 质量与原 A4 恒等式

| RHS | native A4 rho | field L2 relative | scaled-curl relative | native identity relative | packet SHA |
|---|---:|---:|---:|---:|---|
| `A2R160_BAL_H_p4_01` | `0.012747787228447355` | `0.0004689413782647275` | `0.00046501472893071427` | `8.297931175453582e-17` | `1e671b5b7d89cda3c71f180c0663bd10da31a8fdb0df7eab3b322ca96671398e` |
| `A2R160_BAL_H_p4_02` | `0.0007166869050548434` | `0.0006381970572039616` | `0.000633006283574765` | `2.7398496982251096e-18` | `bf7fa846d6bae4f712f8a175f119915253387151460c1ef2b4cccc65d1bf2f0c` |
| `LIGHT448_BAL_H_p4_09` | `0.01767784455927856` | `0.0005184603039686529` | `0.0005142289126743576` | `9.818805809041391e-17` | `7c7224354a683a7f3304bb096dc32d4f7be305c9c7e73e4e380f327d31c9134c` |

这里的 `rho` 是一次 BLR 回代产生的原 A4 相对残差，可直观理解为“原方程还剩多少不平衡”相对于输入大小；它不是完整 p6 outer true residual。`field L2` 表示整体电场的相对误差，`scaled-curl` 表示空间变化（旋度）的相对误差，三者都是 `0` 最好。每个 packet 还保存 `g-A4*c = e_top - B*H^{-1}*e_port` 的独立恒等式复核，限值 `1e-10` 通过。`native_evaluation_seconds` 和 field metric 是证据时间，不是把纯 MatSolve 时间冒充总回代时间。

## 4. 内存与时间口径

### 4.1 对照表

| 指标（十进制 B；RSS/PSS=process-tree 驻留，inventory=对象账，INFOG19/22=后端 allocated/used，entries=条目数） | Q1 uncompressed exact | S2 BLR | 变化/解释 |
|---|---:|---:|---|
| full RSS peak | `2825973760` | `2741243904` | `R_peak=0.9700174654134085`，约降 3.0% |
| factor-live RSS peak | `2825973760` | `2741243904` | `R_live=0.9700174654134085`，两边均保留 factor 与矩阵 |
| full PSS peak | `2795549696` | `2710780928` | 同期可读 samples；PSS 不替代 RSS Gate |
| resident inventory peak | `2906619390` | `2256619390` | 派生/对象账少 `650000000 B`；不是 process-tree峰值 |
| shared workspace peak | `17825792` | `17825792` | 没有 workspace 减少 |
| INFOG19 allocated upper | `2343000000` | `1693000000` | BLR upper 少 `650000000 B`，约 27.7% |
| INFOG22 used upper | `1382000000` | `1420000000` | BLR 反而多 `38000000 B`；不能用 allocated 代替 RSS |
| native factor entries | `53417584` | `53040280` (`INFOG9/35`) | 约少 `0.706%`；`INFOG29` 仍为 `53417584` |

Q1 的三次 apply 时间 `1.894626224/1.856757703/1.827990820 s` 是旧记录中的全 RHS 调用口径，包含 MatSolve 与 original/augmented residual checks，但不包含 field error/field metric evaluation；不能与 BLR 的纯 `MatSolve=0.078368/0.086713/0.078177 s` 直接形成加速倍数。BLR 本轮按字段分列如下：

| RHS | MatSolve | native evaluation | field metric | packet save | full RHS elapsed |
|---|---:|---:|---:|---:|---:|
| 01 | `0.078368256` | `0.906254950` | `4.770232204` | `0.034260709` | `5.799002369` |
| 02 | `0.086713411` | `0.914416743` | `4.698059601` | `0.027822220` | `5.728811806` |
| 09 | `0.078177036` | `0.909364238` | `4.703726286` | `0.027090146` | `5.719995665` |

phase audit 从 parent 记录的 monotonic 边界派生，不能称每个函数的独立实测 timer：

| 阶段 | monotonic seconds | 身份 |
|---|---:|---|
| parent bootstrap / worker entry | `0.694845430` | phase boundary derived |
| preflight | `0.216627209` | phase boundary derived |
| setup | `37.088510941` | phase boundary derived |
| assembly / compile / pattern / augmentation | `494.414024999` | phase boundary derived |
| symbolic + numeric factor | `20.378098889` | phase boundary derived；native factor fields另列 |
| three solve phases | `0.996417107 + 1.002442592 + 0.988750383` | phase boundary derived |
| three evaluation phases | `4.812948142 + 4.737177278 + 4.771000766` | phase boundary derived |
| cleanup | `1.382956234` | 含 worker cleanup 与 parent reap |
| full workflow monotonic | `571.514731005` | run summary |
| conservative settled | `625.736658980` | V16 batch ledger；observe-only，不作性能拒绝 |

为避免只报单段时间，Q1 与 S2 的配对成本同时记录如下；`RINFOG3` 是 BLR 后端报告的理论 flop 总量，`RINFOG14` 是实际 flop 总量，二者不是同一个指标：

| 成本字段 | Q1 exact | S2 BLR |
|---|---:|---:|
| symbolic | `0.2683213069976773 s` | `0.33692986499954714 s` |
| numeric | `18.488779414998135 s` | `19.946495771997434 s` |
| full monotonic | `536.4680422439997 s` | `571.5147310050015 s` |
| conservative settled | `584.7709557270404 s` | `625.736658980034 s` |
| factor flop total | — | theoretical `RINFOG3=39449025878.0`；actual `RINFOG14=41079564559.0` |

UTC/保守时钟比 monotonic 多约 `54.221193 s`，两者不能相减后再重复计费。完整 `run_summary` 的 monotonic/UTC/boottime 与保守区间、以及 phase audit 的边界说明均保留在 raw evidence。

### 4.2 账本与工程时间

V16 使用独立 `review_v16_p4_blr` ledger；本场 settled `625.736658980034 s`，reserved `14400 s`，`unique_bug_replay_count=0`，active attempt 已清空。旧 V14 ledger SHA `1e3b9c01745fef72f7a794b23e5077508fd65b3951485131d8b639043bd4ecb3` 及历史 `600 s` policy debit 保持只读引用；它不可返还、不可冒作新实测，新 batch ledger 单列该引用关系，不改写旧账。未知旧耗时仍保持 unknown。

S0 工程 checkpoint 的 app-reported `1761.112 s` 与最终 preflight 的 engineering elapsed `5235.60104560852 s` 是重叠的编辑/测试/监督窗口，不是 PDE workflow；不能相加，也不并入上述 formal ledger。

## 5. 测试、资源与数据身份

| 检查 | 结果 | 边界 |
|---|---|---|
| S0 qualified ABI / clean source preflight | `PASS` | source `24bd...1ede`；complex128/int32、MPI1、线程1；formal PDE 启动前 clean |
| directly related targeted tests | `128 passed` | V16、控制/代数/接口/schema/launcher/dispatch、real tiny MUMPS 和 saved Q1；原始范围见 `s0_final_preflight.json` |
| compileall / diff-check | `PASS` | 本批最终源码提交后完成；文档更新不改数值源码 |
| input validate / dry-run | `PASS` | 正式 input 与 resolved config 通过；不是 PDE 结果 |
| Ruff | `unavailable` | 当前资格化环境未安装，不补装 |
| full repository pytest / CI | `not_run` / `not_claimed` | 不把局部测试写成全仓或 CI 通过 |
| S2 resource gate | `PASS` | zero job swap、global delta `0/0`、all samples readable、descendants cleared、clean source after |

实际限制仍为总常驻对象账 `6 GiB = 6442450944 B`、共享临时工作区 `1 GiB = 1073741824 B`、进程树至多 `8 GiB = 8589934592 B`；整机 reserve 为 `max(4 GiB, 0.15×有效总内存)`。本机实际 reserve 为 `4294967296 B`，global swap 页计数全程保持 `39/149`，增量 `0/0`。存量系统 swap 不冒充本任务换页。
| sandbox process view / MPI permission record | engineering-only false negative，已由实际宿主复核纠正 | OpenMPI/PMIx singleton 权限与 sandbox PID 视图不计为 PDE failure 或 bug replay；本轮没有因此重跑 PDE 或增加 route |

独立 checker `s2_independent_check.json` 从 raw vectors、parent resources、factor fields、controls、input/reference hashes 重新计算上述状态；它不是 solver 的第二次运行。大型 matrix/factor/field/timeline 保留在 ignored results/artifacts，不写入 Git。

## 6. 最终决策与选择性合并边界

本轮只关闭 `physical_p4_blr_bal_h_v16` 这一固定配置。它的质量和控制读取证据可作为后续研究的全局 p4 reference-visible input，但没有完整 p6 outer residual、非可分 case、official field/power 或波长/网格扩展证据。S3/S4 不运行不是数值失败；它是因为本轮明确的 memory-admission Gate 未满足。

选择性合并边界见 [selective merge manifest V17](outcomes/selective_merge_manifest_v17.md)。在最终 review approval 和用户授权前，不合并 master；ordinary solver default 不变。保留原 V14/V15 负结果、旧 ledger、历史 unknown 和本轮 `STRONG_BUT_INSUFFICIENT_MEMORY_GAIN`，不把 allocated-only 改善包装成 RSS success。

## 7. 证据入口

- [S2 independent checker](../../benchmarks/artifacts/task39extra/p4_blr_v16/root_engineering/s2_independent_check.json)
- [formal BLR summary](../../results/euv_grazing1_phi0/task39extra_v16_s2_blr_control__full3d_iterative__mpi1__Mna/20260913T163912.716491Z/physical_p4_blr_v16_summary.json)
- [run summary](../../results/euv_grazing1_phi0/task39extra_v16_s2_blr_control__full3d_iterative__mpi1__Mna/20260913T163912.716491Z/run_summary.json)
- [S0 preflight](../../benchmarks/artifacts/task39extra/p4_blr_v16/root_engineering/s0_final_preflight.json)
- [MUMPS identity](../../benchmarks/artifacts/task39extra/p4_blr_v16/root_engineering/mumps_5_6_2_primary_identity.json)
- [compact](outcomes/records/p4_blr_v16_compact.json)；[decision](outcomes/records/p4_blr_v16_decision.json)；[run index](outcomes/records/run_index.json)
