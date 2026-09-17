# 原生迁移与容量任务：本轮执行结果

## 最新状态：2026-09-18 按实测内存重启

| 项目 | 当前事实 |
|---|---|
| 2 nm h1.5 PORD64 run `20260915T210201.504107Z` | symbolic成功；预测峰2716.777 GB超过原门限1537.541 GB而停止；实测采样峰277.716 GB，swap0；没有numeric/outer/RTA |
| 用户新授权 | 一次新h1.5运行，以整个任务实测RSS达到1537.5十进制GB作为停止条件；预测只记录；系统reserve、swap和监控检查保留 |
| 实现 | 独立measured输入/profile；新profile不设置预测扣减的ICNTL(23)上限；旧profile保持原行为 |
| 资格和运行身份 | [Response V3](../response_v3.md)、[本轮compact](records/2nm_h1p5_measured_retry_v1.json)；提交时尚未启动，实际启动身份见ignored `benchmarks/artifacts/native_capacity/measured_retry_20260918/launch_check.json` |
| 后续监督 | 独立watchdog持续执行；按用户要求停止主动查询/通知，由用户按需询问 |

以下为历史记录；不以旧文档的“待启动”状态覆盖上述终态和本次授权。


| 范围 / 阶段 | 状态 | 主要证据 |
|---|---|---|
| R0 native环境与隔离 | NATIVE_ENVIRONMENT_PASS | [环境与硬件](environment_and_migration.md)、[ABI](records/native_abi.json) |
| R1 attempt1，13.5 nm Si p6/h10，MPI1 | 身份检查失败，未outer | [原始负结果](records/r1_attempt1.json) |
| R1 retry1，同一模型 | PERFORMANCE_CONTROLLED_STOP；筛选未通过 | [复现/阶段资源](reproduction_13p5nm.md)、[完整compact](records/r1_attempt2.json) |
| R1 attempt3，13.5 nm Si p6/h10，550步 | own数值 Gate 通过；`BALANCED_OUTPUT_AUTHORITY_LIMITED` | [attempt3 compact](records/r1_attempt3.json) |
| R1 native direct matched reference | NATIVE_OWN_PASS_MATCHED_REFERENCE_WSL_ARRAYS_PARTIAL | [reference compact](records/r1_native_reference.json)、[80通道](records/r1_native_reference_80_channels.json) |
| R2 notch、条件native reference | `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED`；已清场，待审 | [R2负结果 compact](records/r2_notch_attempt1.json) |
| 5 nm formal p6/h4 | own数值/物理 Gate 通过；`REFERENCE_AUTHORITY_LIMITED`；资源连续资格不追认 | [5 nm compact](records/5nm_formal_attempt1.json)、[600通道CSV](records/5nm_dtn_600_channels.csv)、[tracked checker](records/5nm_checker_recheck.json)、[资源记录](records/5nm_resource_coverage.json) |
| 2 nm Si h1.5 formal attempts 1–2 | attempt1 affine geometry失败；attempt2完成P2前装配后 PORD/MUMPS `INFOG(1)=-9999, INFOG(2)=4`，未numeric；同一PORD64组件小资格通过，正式retry待本轮审核 | [失败/阶段compact](records/2nm_h1p5_formal_failure_compact_v1.json)、[PORD64记录](records/2nm_h1p5_pord64_qualification_v1.json) |
| S5 / S3 / S2 / G | R2独立未决负结果；5 nm own已完成但资源连续资格不追认；2 nm h1.5 formal仍未通过、PORD64组件已资格化；3 nm/G未解锁 | [运行总账](records/run_index.json) |
| 性能/检查修复 | 性能修复后13.5 nm R1与native reference通过；5 nm checker修复后独立recheck通过，R2归因仍未决 | `f124679e75915758076d9240bd4bef2f5c772752`；checker `d64398cb1fecd90867071688dca94e501235cf7a`；[测试](test_summary.md) |

## 2 nm Si h1.5 formal attempt 1：setup affine Gate 负结果

run `20260914T013346.036155Z` 在 source `296afa6a6c231b6ab067ad928c9f827ee72f5e98` 下完成 workflow/shared-mesh/H6 setup marker，约 `5175.8977 s` 后 exit4；worker 明确报 `only affine geometry is qualified`，未进入 P2、numeric、outer，无 iterations/residual。watchdog sampled tree RSS peak=`5115244544 B`（约 `5.12 GB`）、swap peak=`0`、global pswp delta=`0`、descendants cleared；`effective_available_bytes_at_launch=2074612776960 B`。该 run 是 `WORKER_FAILED`，不写成 OOM、数值失败或 P2/LU 结论。

实际 h1.5 规则扫描在 `54332` 个 Q1 cell 上使用同一 DG0 `mu=1/mass=2` 的 p6 original/action `ReferenceCellBasis`，两个 audit 相同；默认 NumPy 求和下 raw 绝对坐标误触发 `25432` 个 cell，centered `x-x[0]` 为 `0`，最坏 raw/centered 均用生产逐 cell 表达式复核，det 范围=`2.9761904761904217–3.3088235294118395`。早先 synthetic `1156` 计数不代表正式 kernel 触发；失败日志无 traceback，partial 与 PositiveCellBasis 两候选点保持如实记录。

三处局部修复和 translated-affine/non-affine 回归已完成；用隔离 `.venv/bin/python3 -m pytest` 跑既有 357/362 为 `16 passed, 1 skipped`。独立只读 observer 的无 PDE 自测和实际主控 SELFTEST notify-v2 ACK 也已完成。主控已放行唯一根因 retry；失败目录保留，新 run/新 observer 独立启动，h2 不启动。

## 2 nm Si h1.5 formal attempt 2：PORD/MUMPS组件阻塞与64位资格

run `20260914T061139.551088Z` 在 source `9da01fb0402bc5f7da1cdaf4cc543bb53162deea` 下完成 H6、p4体矩阵和增广装配，随后 symbolic 返回 `INFOG(1)=-9999`、`INFOG(2)=4`、`INFOG(7)=4`，未进入 numeric/solve/outer；exit4，分类 `WORKER_FAILED`。实际体矩阵为 `10604228` 行、`4752199344` NNZ，增广为 `10608132` 行、`4899800920` NNZ。该结果不是 OOM 或数值不收敛；正式图的 `NEDGES8` 未记录，保留“`-51/-2147`边界早退可能被 `NCMPA` 覆盖为 `-9999/4`”的强证据推断，不冒称正式图实测。

对 `watchdog/resources.jsonl` 已完成一次流式归并：330197行、坏行0、不可读样本0；整树RSS峰 `277758349312 B`、swap峰0、global pswp delta 0。资源样本的首末跨度与 `stages.jsonl` 相邻 marker wall 已分开记录；其中 `reference_volume_pattern→reference_volume_complete` 为数值体装配 `88431.120501188096 s`，`reference_volume_complete→reference_augmentation_complete` 为增广构造 `239.752949750982 s`，symbolic调用 `154.872576898895 s`。详见 [`2nm_h1p5_pord64_qualification_v1.json`](records/2nm_h1p5_pord64_qualification_v1.json)。

旧混合PORD边界 probe：`NEDGES8=2147483648` 返回 `INFO(1)=-51, INFO(2)=-2147`，预置 `NCMPA` 未写回；旧查询为32位。独立 `/tmp/task39extra-pord64` 仅以 `-DPORD_INTSIZE64` 重编14个PORD对象和 `mumps_pord.c`，不使用全局 `-DINTSIZE64`，复用旧 `libzmumps.a`/PETSc对象并重链任务专属 `libpetsc.so.3.19.6`。最终 activation [`scripts/activate_task39extra_pord64.sh`](../../../scripts/activate_task39extra_pord64.sh) 明确同步 `PETSC_DIR`、`PYTHONPATH`、`LD_LIBRARY_PATH`，旧 [`activate_task39extra_int64.sh`](../../../scripts/activate_task39extra_int64.sh) 不变；新prefix没有 `.pc` 文件，因此 `PKG_CONFIG_PATH` 明确 unset。完整有效argv、对象参数文件/`petscvariables`哈希、库替换和 cfg 复制步骤见 [`2nm_h1p5_pord64_build_recipe_v1.md`](records/2nm_h1p5_pord64_build_recipe_v1.md)。

同一8-cell、1944行、701496-NNZ p4/MPC fixture 在同一新prefix下通过：`petsc_int=int64`、`complex128`、query=64、唯一新PETSc map，临时 `PETSc.Options()["mat_mumps_icntl_7"]=4` 后 `INFOG(7)=4`、`INFOG(1)=0`，symbolic/numeric/solve各1次，原矩阵相对真残差 `2.922259846318588e-11`。最终 activation 另做了 imports/query/maps 轻检；组件资格不等于整张h1.5 symbolic/numeric通过，也不改变正式默认排序或主求解器。

独立 [`scripts/task39extra_2nm_h1p5_pord64_launch.py`](../../../scripts/task39extra_2nm_h1p5_pord64_launch.py) 已准备为 `CPU9 + stdin=DEVNULL + start_new_session + 单一run_case入口`，但尚未执行；h1.5正式retry与h2均保持未启动，等待本次diff/记录审核。

## 5 nm formal attempt 1（用户授权跳过未通过 R2）

用户明确覆盖执行顺序后，按原正式入口完成同一 5 nm Si p6/h4 离散解；这不把 R2 写成通过，也不解锁 3/2 nm 或 G。run 为 `20260911T065955.813489Z`，source `85a681b9bd61104466888546b83df87c27806169`，zero start、restart32、max2048、screen128，时间模式为显式 `none`。

数值结果：iteration `698`，full explicit true residual=`9.986638454029182e-7`，screen128 通过；p4 为 `1396` RHS、`1419` MatSolve、`23` refinement，terminal p4 relative residual max=`9.989282114125241e-11`。official DtN 共 `600` 个 channel，复振幅/功率与 E/H 均有限；R=`0.7331834812424759`、T=`0.00022243948430485038`、A_balance=`0.26659407927321926`、A_volume=`0.26659407694262094`，独立能量误差=`2.33059826992843e-9`。

独立 recheck 的 tracked 副本：[5nm_checker_recheck.json](records/5nm_checker_recheck.json)（来源仍为 ignored `recheck/checker.json`）具有 `independent_output_gates_passed=true`、`gate_failures=[]`、分类为 `BALANCED_OUTPUT_AUTHORITY_LIMITED`。完整 600 条 mode key/复振幅/边界振幅/逐通道功率字段已进入 [5nm_dtn_600_channels.csv](records/5nm_dtn_600_channels.csv)，并保留来源 SHA。`REFERENCE_AUTHORITY_LIMITED` 仅表示没有 5 nm matched fine/continuum 精度参考；`official_result.diffraction_channel_count=150` 是 diagnostic Fourier 计数，不替代或削减 DtN 的 600 channel。

资源与生命周期单列：[资源记录](records/5nm_resource_coverage.json)。原 parent watchdog 有监督断档，旧 wait 退出码 `UNAVAILABLE`；不能追认连续 `RESOURCE_PASS`。原始失败/launching summary、V2 recovery、原始 checker 均保留。观测整树 RSS 峰为 `50161172480 B`、swap peak=`0`；这只是外置采样可观测峰值，不填补断档。

## 最新正式 original run（attempt3）

本次是用户授权后的 clean-SHA、zero-start formal retry；旧 attempt1/attempt2 仍作为历史失败保留，未被覆盖。run compact：[records/r1_attempt3.json](records/r1_attempt3.json)。

| 项目 | measured 结果 |
|---|---|
| source / run | `9b1e8d4a1b2be9fca5b126a1ec3893e3af295e5e` / `20260909T130326.291096Z` |
| lifecycle | `exit=0`、`COMPLETED`、`descendants_cleared=true`、workflow `12560.042750451947 s` |
| numerical Gate | iteration `550`，true `9.998974191134654e-7`，solve `11589.4608165932 s`，outer `567` matvec / `550` PC |
| checker | `independent_output_gates_passed=true`，`gate_failures=[]` |
| authority | `BALANCED_OUTPUT_AUTHORITY_LIMITED`; `WSL_FULL_FIELD_COMPARISON_PARTIAL`，不是完整 R1 |
| field/modal evidence | 80 通道 relative amplitude difference `1.339354498931458e-9`；own R/T/A 与能量记录已保存 |
| p4 assembly | `491.016220843 s` vs old `1818.610 s`，`3.703767661438x`，降低 `73.000466%` |
| final enclosing-tree resources | RSS peak `3631751168 B`，swap peak `0`，watchdog samples `36437` |
| release lifecycle | RSS before=`3078565888 B`，after=`3078565888 B`，delta `0 B`；不声称发生 OS/allocator 回收 |

阶段资源峰值也已在 compact 中逐项保存：setup `3404267520 B`、solve `3085901824 B`、recovery/final peak `3631751168 B`、checker `3558637568 B`、complete `3202437120 B`，均 swap `0`。绑核证据只说明 CPU23/CPU9 affinity，不推出共享内存带宽或功耗无竞争。

因此旧 own run 的 authority 仍单独标为 limited；native direct matched reference 已完成全部本机 R1 比较资格，但不改写“完整 WSL 全场未提供”的边界。R1 不重跑 550 步；R2 attempt1 已因全局 swap 归因未决清场，暂不重跑或进入5 nm。（这是顺序覆盖前的历史状态；后续用户明确授权后执行5 nm，见上。）

## R2 notch attempt1（独立负结果）

原 V5 notch 输入以 clean source `f21a33914765a10adfa43735fb2e1ac3013ff905` 启动，input SHA=`b7ba606a5bf056d06e13065c6500c99301c7e6e4a0ec8eec1ad20797c28185c3`、notch physical SHA=`7a4d2a797a274fd4a02955647e91288908dd6a457c37984535fa2db9bfec06ec`。run `20260909T191201.621471Z` 在 iteration3、outer matvec/PC=3 时由既有 watchdog 因 `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED` 受控停止：全局诊断 `pswpout delta=2` 页，进程树采样 `VmSwap peak=0`；leader=`-9`、`descendants_cleared=true`、remaining children 为空，RSS peak=`3406852096 B`。该结果不称 OOM、数值失败或邻居归因，且没有自动 retry。

早期 solve 计时与 p4/PC 证据见 [R2 compact](records/r2_notch_attempt1.json)；R2 未取得数值资格，5 nm 继续锁定。（后续用户明确覆盖顺序后已执行5 nm，见上。）

## R1 native direct matched reference（最新 Gate）

run `20260909T175256.839514Z` 在 clean source `125c383f9ec7027bd9c6528b4cafc669dd16ea6f` 下经唯一 `run_case.py` 入口完成。hard32 GiB/planning24 GiB admission 实测使用 `dynamic_cap_bytes=25769803776`、ICNTL23=`22646 MB`、symbolic estimate=`4858 MB`；symbolic 1 次、numeric 1 次、solve 2 次、factor release 通过。阶段边界与逐阶段 RSS 峰见 [compact](records/r1_native_reference.json)，80 项复振幅/逐通道功率见 [80-channel carrier record](records/r1_native_reference_80_channels.json)。

R1 资格结果：`REFERENCE_PASS` residual=`1.4427687662062765e-11`；`MATCHED_REFERENCE_PASS`，L2=`1.335826588236277e-8`、scaled-curl=`5.5945316967861595e-9`、selected E/H=`4.08219975785664e-8`/`8.908964399790286e-9`、80 模式=`5.171739887720538e-9`、功率 max absolute=`2.206432703211192e-9`，R/T/A/A_volume 差均在合同限值内，无相位拟合。watchdog `COMPLETED`、清场、swap=`0`、RSS peak=`7304724480 B`。标签保持 `NATIVE_OWN_PASS_MATCHED_REFERENCE_WSL_ARRAYS_PARTIAL`，不宣称完整 WSL 场复现。

本轮仍使用原V5 BAL_H + accurate global p4 LU，没有新迭代算法、子域法或预条件器。worker独占逻辑CPU23、监督器CPU9，隔壁CPU0–7进程未修改；缓存、venv、Git、结果全部属于独立worktree。共享socket的缓存/带宽不可能仅凭绑核证明完全零影响，未作这类承诺。

## 正式结果（measured；GiB=2^30 B）

| 模型 / attempt | p6 storage / independent | p4增广rows / NNZ / factor NNZ | outer / fine true | p4 worst true | workflow / s | 同期RSS峰值 / GiB | swap |
|---|---|---|---|---|---:|---:|---:|
| 13.5 nm Si p6h10 / 1 | 173802 / 164592 | 53164 / 24730144 / 53417584 | 未运行 | 未运行 | 2731.775 | 2.787 | 0 |
| 13.5 nm Si p6h10 / 2 | 173802 / 164592 | 53164 / 24730144 / 53417584 | 62 / 0.019433158954790204 | 4.893382586118271e-11，124次，修正0 | 3997.651 | 3.163 | 0 |

两次均无official R/T/A/A_volume、R00_s/R00_p/R00_total、80通道复幅值或selected E/H。它们是“未取得”，不是零。第二次完整true尚未达到1e-6；screen同时未满足0.01或足够完整周期趋势，不能因曲线继续下降而越过筛选。第32步native/WSL完整残差绝对差3.13e-13支持当前迭代轨迹一致，但不替代场/能量Gate。

## 已查明的性能问题与解决范围

| 问题 | 已实现处理 / measured效果 | 尚未证明 |
|---|---|---|
| 初次parent与worker抢CPU8 | parent9、worker23分离 | 与隔壁零共享带宽影响 |
| p4生成内核跨行访问、寄存器spill | 独立元素改按行访问；真实单元CSR装配6.935→1.929 s，逐位一致 | 完整252单元正式装配时长；约8.2分钟只是预测 |
| curl内核重复扫描独立系数 | 合并12个独立循环，原生成C单元p6约2倍、p4约1.4倍；真实FE逐位一致 | 完整外迭代加速倍数及R1通过 |
| PSS逐次读取增加开销 | RSS安全采样保留、PSS降频；单次采样约0.09→0.034 s | 大容量case监督开销 |
| 释放后RSS未显著下降 | 完整记录释放前后3.0787/3.0745 GB和最终清场 | 未证明allocator具体滞留或回收改进 |

物理矩阵、载荷、积分、复数精度及Gate均未改变。CPU23实测约3.6GHz；CPU2的外部限频/内存90°C是另一个已记录硬件异常，本轮没有解决它，也没有绕过热保护。变慢的可修复内核和监督开销已有实证；不能把诊断提速当正式求解成功。

## 身份、边界与下一步

base为`450255f4575792d052c1bac29837d39955ee1039`；R1 retry1运行SHA为`b2e132a7b1f1078eb3359c87a336123b3c7dfbdd`，input SHA为`eb18ecd70d49cccb1564c8c3a93d8f89d25b8734ff448b16929de5d65fd273b9`，physical SHA为`9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`。运行前后clean source与全部hash见compact。历史移交提交`72a0f58899dc5d98aa4c170edffb573ed50067c7`只读使用，没有向task39extra/task41/master写入本任务结果。

任务书§11要求screen/solve性能失败后停止主阶梯，不能把该负结果当迁移bug重复抽签。本轮交付状态为fail / PERFORMANCE_CONTROLLED_STOP；性能修复作为可审阅的显式native实现保留，额外formal retry须有明确例外授权。当前没有最短own-pass波长、没有精度资格或G网格一致性结论。具体后续blocker是单核生成内核成本与原screen预算之间的矛盾，不是开发新PC的授权。

两次formal累计wall约6729.43 s；先前准备、测试及诊断另有分项日志。尚未构造覆盖整个会话每条命令的完整campaign计费总表，不声称已完成该项完整记账；所有已知计算远低于864000 s总上限。性能诊断是同机单核小测试，不把人工等待或并行诊断父子时间重复叠加为formal wall。

## Selective merge建议

| 依赖组 | 内容 | 建议 |
|---|---|---|
| production core / numerical | native模式身份桥、严格浮点FFCx调度模块和显式接线 | 数学等价小测试通过；完整R1未重新资格化，暂不提升普通默认或合入master |
| reusable runner/watchdog | native隔离、RSS/PSS降频、身份异常分类 | 定向进程/MPI测试通过；与profile一起审阅 |
| checker/benchmark | native比较器、性能/模式/监督测试 | 依赖对应实现；不从compact状态直接推导成功 |
| compact evidence/docs | 本目录outcomes、response、总账和progress | 可独立审查正负证据，保留旧失败 |
| research-only | 本次native容量profile、CPU硬件/内核诊断 | 未资格化完整PDE；保持显式opt-in |
| do-not-merge | results、benchmarks/artifacts、tmp、venv、JIT/C/SO/矩阵/场 | ignored；只提交必要hash索引 |

未获merge approval，不合并master。证据入口：[response](../response_v1.md)、[运行索引](records/run_index.json)、[测试](test_summary.md)。
