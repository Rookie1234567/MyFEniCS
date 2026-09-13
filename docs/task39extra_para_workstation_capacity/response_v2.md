# Response V2：用户授权后的性能验证接线

本轮由主控明确授权继续执行原生 Linux native-capacity campaign。此前 `f124679e75915758076d9240bd4bef2f5c772752` 已提交的 p4 按行内核、p4/p6 curl 独立循环合并和 PSS 降频作为唯一性能实现；不新增求解算法、预条件器、子域法或参数扫描。旧的 13.5 nm screen 负结果和首次 mode 失败保留不变，新正式运行必须从零、冷缓存、clean source 开始。

## 生效合同

| case | 材料身份 | screen | solve 上限 / s | workflow 上限 / s | 其他固定项 |
|---|---|---:|---:|---:|---|
| 13.5 nm original | Si，`n=0.999002304859+0.00182649365i` | 128 步、7200 s | 43200 | 64800 | MPI1、线程1、restart32、max2048、zero start |
| 13.5 nm notch | Si，同上 | 不启用，不增加 screen | 43200 | 64800 | 同上 |
| 5 nm formal | Si，`density=2.33`，`delta=0.00603145547`，`beta=0.00435380777`，`n=0.99396854453+0.00435380777i` | 128 步、无时间截止 | None | None | 用户明确覆盖顺序；MPI1、线程1、restart32、max2048、zero start |

5 nm 数值来自用户本轮权威输入；本轮不声称已独立核验数据库来源。它是复折射率 `n`，不是 epsilon；运行时由 `epsilon=n*n` 生成并记录。3 nm/2 nm 材料身份不在本轮自行推断。

## 当前状态

当前 5 nm formal 已在 source `85a681b9bd61104466888546b83df87c27806169` 下终态；checker 的 no-deadline 修复已提交为 `d64398cb1fecd90867071688dca94e501235cf7a`。R2 仍保留为独立 `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED` 负结果；5 nm own 数值/物理 Gate 已完成，但资源监督断档不追认连续 `RESOURCE_PASS`，3/2 nm 与 G 仍未解锁。运行期间的 CPU23/node1 与其他隔离事实只按实际证据记录，不外推共享内存带宽或功耗无竞争。

## Original 13.5 nm native formal retry：own 结果与参考资格边界

用户已明确授权本次性能修复后从零验证，因此本次正式 run 不再受旧 §11 性能停止阻断。run 使用 clean source `9b1e8d4a1b2be9fca5b126a1ec3893e3af295e5e` 和唯一入口 `python scripts/run_case.py input/task39extra_para_workstation_capacity/original_13p5nm_p6h10.dat`，目录和 compact 记录见 [`r1_attempt3.json`](outcomes/records/r1_attempt3.json)。

本次 `iteration=550`、outer `matvec=567`、`PC=550`，terminal true residual=`9.998974191134654e-7`，solve=`11589.4608165932 s`，workflow=`12560.042750451947 s`；`exit=0`、`COMPLETED`、`descendants_cleared=true`。checker 的 `independent_output_gates_passed=true` 且 `gate_failures=[]`，但分类仍为 `BALANCED_OUTPUT_AUTHORITY_LIMITED`。80 通道 relative amplitude difference=`1.339354498931458e-9`，只是部分 modal/own-output 证据。

生命周期口径已按最终 watchdog 与 physical summary 固定：整树最终峰值 RSS=`3631751168 B`、swap=`0`、样本=`36437`；setup 峰值另为 `3404267520 B`，不能冒充最终峰值。释放前后 RSS 都是 `3078565888 B`，因此记录为无观测 RSS 回收，不虚构 allocator 回收。p4 assembly 当前 `491.016220843 s`，旧 `1818.610 s`，约 `3.703767661438x`、降低 `73.000466%`。

own 结果的 `A_balance/R/T/R00/A_volume` 和能量闭合均已保存，但 `matched_reference.full_field=WSL_FULL_FIELD_COMPARISON_PARTIAL`、`reference_authority=REFERENCE_AUTHORITY_LIMITED`。旧 native 62 步负结果与旧 WSL V5 original 564 步/notch 576 步成功历史保持分开；本次不重新运行原始 550 步，不继续寻找旧 WSL 64/128 checkpoint，也未启动 notch。

当时的下一 Gate 是沿既有路径完成一次 native direct matched reference；该 Gate 已在下节以 clean SHA、symbolic→numeric admission、整树 watchdog 和场比较完成。此前没有启动 notch，也没有开发新 direct 算法、PC 或防御框架。

## Native direct matched reference：R1 资格完成

容量接线修复提交为 `125c383f9ec7027bd9c6528b4cafc669dd16ea6f`：native 资源样本显式传入 `numeric_planning_cap_bytes=25769803776`（24 GiB），`numeric_allowance` 对 hard `34359738368`（32 GiB）与 planning 取最小后再扣 baseline/future/reserve；旧缺字段路径保持原行为。旧代码加载的 run `20260909T174245.158312Z` 通过 watchdog 受控停止并保留负记录，未进入 numeric；修复后只进行一次 retry。

retry run：`20260909T175256.839514Z`，source/input/physical SHA 见 [`r1_native_reference.json`](outcomes/records/r1_native_reference.json)。`REFERENCE_PASS` residual=`1.4427687662062765e-11`，pre-numeric RHS=`3.260906215866404e-14`，A6/RHS/repeated-A6 identity checks 全为 `0`；`MATCHED_REFERENCE_PASS` 的 full-field L2=`1.335826588236277e-8`、scaled-curl=`5.5945316967861595e-9`，selected E/H=`4.08219975785664e-8`/`8.908964399790286e-9`，80 模式复振幅=`5.171739887720538e-9`，逐通道功率最大绝对差=`2.206432703211192e-9`，无相位拟合。完整 80 项必要小证据见 [`r1_native_reference_80_channels.json`](outcomes/records/r1_native_reference_80_channels.json)。

阶段 wall 使用 `stages.jsonl` 相邻单调 marker 相减，不把累计 wall 当子阶段相加；workflow=`3624.8300013281405 s`，整树 RSS 峰=`7304724480 B`、swap=`0`、`COMPLETED`/`descendants_cleared=true`。资格标签是 `NATIVE_OWN_PASS_MATCHED_REFERENCE_WSL_ARRAYS_PARTIAL`：这是允许的 native direct matched reference，不声称已经取得完整 WSL 全场复现。R1 已关闭；R2 attempt1 的独立负结果见下节；此处“5 nm仍锁定”是当时状态，后续用户覆盖顺序后已执行5 nm。

## R2 notch attempt1：全局 swap 归因未决，禁止过度归因

原 V5 notch run `20260909T191201.621471Z` 使用 clean source `f21a33914765a10adfa43735fb2e1ac3013ff905`、input SHA=`b7ba606a5bf056d06e13065c6500c99301c7e6e4a0ec8eec1ad20797c28185c3`、physical SHA=`7a4d2a797a274fd4a02955647e91288908dd6a457c37984535fa2db9bfec06ec`。它按 `cell_notch=positive_x_middle_y_z40_80` 的8-cell recipe启动，无 screen，solve/workflow=`43200/64800 s`，zero/restart32/max2048；在 iteration3、outer matvec/PC=3 时被既有 watchdog 分类 `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED` 并清场。全局诊断仅见 `pswpout delta=2` 页，own sampled `VmSwap peak=0`；leader=`-9`、`descendants_cleared=true`、remaining children为空、RSS peak=`3406852096 B`。这不是 OOM、数值失败或邻居归因，且不自动重跑。

早期同字段 `monitor_residuals.solve_seconds` 为 step0=`39.64952567401153 s`、step1=`186.31658401115436 s`、step3=`448.83664549236175 s`，step1→3平均=`131.2600307406037 s`；p4/refinement/native-kernel与R1差分见 [`r2_notch_attempt1.json`](outcomes/records/r2_notch_attempt1.json)。R2资格关闭；此处“5 nm继续锁定”是当时状态，等待主控审核最小归因方案，后续用户已明确覆盖顺序。

只读速度证据显示，R2 已记录的3次 PC 中 `A_structure/C/smoother` 平均为 `67.3023/17.8440/1.0281 s`，R1 前32次同字段为 `9.27665/8.66633/1.46391 s`；总 PC 操作约 `4.44x`，R2 step1→3 平均约 `5.13x` R1 前32平均 outer-step。p4 日志为 `native=6`、refinement=`0`、BAL_H，mode bridge=`FIELDWISE_MODE_IDENTITY_PASS`，支持已走 qualified native 路径但不能单独确定根因。终止后8秒只读基线为CPU23 `1.0 GHz`、热区约`67–68/53–54°C`、运行线程`0/19`，不代表运行期频率或热限；不据此归因、不自动重跑。拓扑现场读取为 CPU23 `physical_package_id=0, node0`、CPU24 `physical_package_id=1, node1`，即 CPU0–23/socket0 与 CPU24–47/socket1；CPU24 历史 PROCHOT 证据不用于本轮 CPU23 归因。运行期 watchdog 差分为墙钟 `1924.572334 s`、CPU23 worker `1299.96 s`（比 `0.67545`）、CPU9 parent `866.17 s`（比 `0.45006`）。当前 node0/node1 的 `MemFree`（空闲页，不等于 `MemAvailable`/可回收余量）约为 `3695.82/423487.26 MiB`（源值以 `kB/1024` 换算），主机预存 swap 仍为 `2页/8KiB`；turbostat 的 CPU23 MSR 与 perf APERF/MPERF/thermal-margin 仍因权限不可得，未改权限或硬件保护。`configured_stop_grace_seconds=60` 仅为配置值，实际 stop→watchdog end 为约 `2.387028219 s`。

本次只读调查的最多三项后续方案：保持 R2 关闭并将现有 2 页预存 swap 作为再次压力运行的环境阻塞；若要做硬件归因，另行取得 CPU23/socket0 的特权只读 MSR/perf 当前与 sticky 数据；仅在清洁基线和单独批准后复用既有日志做一次有界频率/温度/线程及 p4/PC 采样，不改源、不改全局 swap/硬件保护、不自动重跑。R1 仍为已通过的 native matched-reference，R2 停止；5 nm 后续已按用户覆盖授权完成，当前结论见下节。

## 5 nm formal：own 数值/物理 Gate 完成，参考与资源资格分列

用户随后明确授权跳过尚未通过的 R2 后续、直接执行 5 nm；这不改写 R2 负结果。run `20260911T065955.813489Z` 使用 source `85a681b9bd61104466888546b83df87c27806169`、5 nm Si 用户权威复折射率 `n=0.99396854453+0.00435380777i`、p6/h4、600 modes、zero start、restart32、max2048，时间模式显式 `none`。solve 在 iteration `698` 自然结束，full explicit true residual=`9.986638454029182e-7`，screen128 通过；p4 为 `1396` RHS、`1419` MatSolve、`23` refinement，terminal p4 relative residual max=`9.989282114125241e-11`。

official DtN port 的完整 600-channel 载体与复振幅均有限；`R=0.7331834812424759`、`T=0.00022243948430485038`、`A_balance=0.26659407927321926`、`A_volume=0.26659407694262094`，独立能量误差=`2.33059826992843e-9`，吸收差=`2.3305983254395812e-9`。`diffraction_channel_count=150` 属于 diagnostic Fourier，不是 DtN channel 缺项。E/H archive shape=`[5,20,40,3]`，复数与坐标全有限。

checker 修复提交为 `d64398cb1fecd90867071688dca94e501235cf7a`，只让显式 `None` 时间门限跳过比较并保留 iteration Gate；4 项 focused tests 通过。独立纯读盘 recheck 见 [`recheck/checker.json`](../../results/euv_grazing1_phi0/original_5nm_si_p6h4_balanced_h6_p4_native__full3d_iterative__mpi1__Mna/20260911T065955.813489Z/recheck/checker.json)，结果 `independent_output_gates_passed=true`、`gate_failures=[]`、`BALANCED_OUTPUT_AUTHORITY_LIMITED`。`REFERENCE_AUTHORITY_LIMITED` 仅表示没有短波 matched fine/continuum 精度参考，不是缺少必需的 A4 数值求解。

资源资格仍独立标记 `NOT_CONTINUOUS_RESOURCE_PASS`：原 parent watchdog 断档，父 wait 退出码 `UNAVAILABLE`；旧 watchdog 末样本至首个 recovery sampler 约 `30843.729885301 s`（约8小时34分）无连续覆盖。流式汇总见 [`5nm_resource_coverage.json`](outcomes/records/5nm_resource_coverage.json)，观测整树 RSS 峰=`50161172480 B`、swap peak=`0`。原始 `checker.json`、launching summary、manifest 和 recovery 负/断档记录均保留。5 nm own 结果不填补资源连续资格，也不解锁 3/2 nm 或 G。
