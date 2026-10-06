# Task40 V11 综合工程报告：保存场物理复核、组件规模检查与 Gx560 资源受控停止

## 执行结论

V11 已完成 S0–S6 文档收口。最强的正结果来自两类相互独立的工作：同一份已保存 B0 解的端口平面功率重检通过；dot 提供的完整 882 行 B/D 分块动作在上下两个代表面、全部 32,060 个有序模式上通过独立 checker。两个原尺寸局部 p6 恢复块也通过局部方程与已知场 Gate。

本轮主数值里程碑没有完成。Gx560 的四个 q 只达到符号分析，all-q numeric 准入因 live memory pressure 受控停止；没有 numeric factor、KSP、场或 official R/T/A。Gx784 因前置条件未满足未运行。50×25×140 nm、0.7 nm、完整三维目标仍为 `NO_GO / NOT_QUALIFIED`。这不是数学不可能性结论，也不是“所有数值主交付成功”。

## 读者需要知道的计算对象

本任务研究 0.7 nm 波长下的三维电磁场计算。有限元把连续空间切成小单元，用每个单元上的未知场组成大规模线性方程；边界模态描述波如何进出计算域。B0 是 80 个单元、包含真实三维两单元缺口的有限模型。Gx560 是 560 个单元的工程网格。原尺寸目标为 50×25×140 nm，要求完整三维 Maxwell、保留任意非可分缺口，并同时达到十进制 2 TB、无 swap、从冷准备到独立检查不超过 48 小时。

`q` 是 y 周期方向的四种相位分支。p6 参考逆先对规则背景的各 q 矩阵做 LU 因子化；迭代时用这些因子给真实目标方程提供修正方向。它改变的是预条件步骤，不替换目标物理算子、真实缺口或 RHS。B0 上三步求解的 true residual 通过，但不代表 Gx560 的 fill、因子占用或成本会按单元数线性外推。Gx560 实测在数值因子化前遇到资源 Gate，因此不支持外推原尺寸 2 TB/48 h。

## S0–S6 结果矩阵

| 阶段 | 对象与目的 | 结果 | 资源/证据边界 |
|---|---|---|---|
| S0 冻结 V10 | B0 p6 解、旧物理负结果、原 q 因子审计 | true residual `1.6089774392e-8` 通过；旧能量差 `6.5819164363e-5` 失败记录保留 | before-destroy 四 q 因子同时 live；与 RSS/cgroup 分开 |
| S1 gauge-aware 保存场输出 | 核查端口平面坐标、532 模态功率与体吸收 | `SAVED_FIELD_PHYSICS_REVALIDATED`；新能量差 `8.2879259e-11` | saved field postprocess only，无新 PDE/factor |
| S2 原尺寸局部恢复 | 两个 p6 局部块的已知场恢复和端口/trace 方程 | 两面前向误差约 `5.1–5.4e-14`，局部原方程低于 `7e-16` | 两块候选；q60 全行重检和全目标 MPC 未运行 |
| S3 B0 direct reference | 为 B0 提供不同于旧 p4 control 的同离散参照 | `NOT_RUN_AUTHORITY_LIMITED_OPTIONAL_REFERENCE` | G0 map/witness 与 B0 gauge/RHS 合同不匹配；不是容量、ABI 或用户授权失败 |
| S4 Gx560/Gx784 | 560-cell p6 q4 reference route 和条件扩展 | Gx560 `RESOURCE_CONTROLLED_STOP_BEFORE_NUMERIC`；Gx784 `NOT_RUN_CONDITION_NOT_MET` | 四 q symbolic 后停；numeric/KSP/field 均 absent |
| S5 882 行组件 | 两代表面的 32,060 模态 Bα/Dx 分块动作 | full checker PASS；84 行替代尚未资格化，本轮主线未重跑压缩 | 非全边界/全域 MPC/算子范数/PDE |
| S6 资源与移交 | 判断后续架构路线与原尺寸边界 | 原尺寸 `NO_GO / NOT_QUALIFIED`；不继续原样重跑 Gx560 | V11 最终 policy snapshot 留给主控单一写入者 |

## S0：冻结的 B0 基线与 before-destroy 因子库存

V10 B0 使用 4×4×5=80 cells、p6、真实两单元 void、y 方向四个 q，全部 532 个端口通道（top 266、bottom 266）。分量级逆算子见证、regular reference 方程抽样和 3 步 B0 线性求解保留为历史正结果。原始输出的能量闭合 `6.581916436299018e-5` 高于 `1e-5`，因此原输出 packet 不作为有效物理通过；p4 control 2048 步、reason `-3`、A6 `0.966131083707469` 为独立历史负结果。

因子销毁前的 `factor_audit_before_destroy` 显示四个 numeric factor 同时保留、同一时刻 live count=4，且四个因子的 true residual 检查通过。该审计 raw source 为 Git source `c439ed40768de4745131b43fc0312bb8be8d9d50` 下的 candidate summary，文件 SHA-256 `8bb525f4773fc0e21263816273a0d216cd186a15ff23169ece8895ced463fa0e`。下表按 q 给出原记录字段；MUMPS INFOG19/22 是各 q MUMPS 内部数据的 allocated/used MB，INFOG29 是 factor matrix entries。不同 q 的内存字段和 watchdog RSS/cgroup 不可混为同一测量。

| q | 方程行数 | PETSc 输入 NNZ | INFOG16/17 symbolic estimate (MB) | INFOG19 allocated (MB) | INFOG22 used (MB) | INFOG29 factor entries | 数值因子时间 (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 4,324 | 2,270,108 | 123 / 123 | 123 | 110 | 3,625,232 | 0.255844 |
| 1 | 4,400 | 2,327,293 | 125 / 125 | 125 | 112 | 3,676,320 | 0.261343 |
| 2 | 4,400 | 2,304,310 | 124 / 124 | 124 | 111 | 3,655,050 | 0.251807 |
| 3 | 4,400 | 2,325,342 | 125 / 125 | 125 | 112 | 3,674,096 | 0.265645 |

INFOG16/17 代表因子化内部数据的符号估计（最大值/跨进程和）；INFOG19/22 是因子化时 MUMPS 内部数据的分配/使用读数；INFOG29 是项数。审计中的 `factor_fill_bytes` 和 `factor_fill_prediction` 都是 null，process-tree RSS 单 q 字段也为 null。不能把 factor entry count 换算成字节，也不能用释放后 inventory 的 0 代替销毁前快照。

## S1：B0 已保存场的 gauge-aware 物理复核

原代码路径把 boundary-plane 系数交给仍按 global-z 坐标解释的功率接口，存在重复乘传播相位的接线问题。V11 的在线输出与保存场恢复都使用显式 gauge-aware 功率路径；top incident subtraction 只执行一次，bottom 无入射扣除。legacy global-z 默认行为不变，boundary-plane 行为显式 opt-in。恢复可重建所需 mesh/space/operator 准备；本次未重解 PDE、未新建数值因子/KSP。科学 E/H/curl/模式输出与可选 PyVista 可视化分开，绘图依赖不决定科学输出是否写出。独立检查器重新比较 532 个模式的物理振幅、逐模态 Poynting 功率、分组功率和材料体吸收。结果：

| 量 | 保存场复核值 | 解释 |
|---|---:|---|
| R / T | `0.9842736080926772 / 0.014240518143988908` | 独立单模和分组功率一致 |
| A_balance / A_volume | `0.001485873763333926 / 0.00148587384621333` | 差 `8.287940407754324e-11` |
| energy closure | `8.287925901129256e-11` | 低于 `1e-5` |
| sum-factorized residual | `1.6089774391665316e-8` | 低于 `1e-6` |
| native full-A6 witness | `1.6089791915820923e-8` | 低于 `1e-6` |

这一步恢复了同一解的可用物理输出链。workflow wall `11.256015081 s`，process-tree RSS peak `716091392 B`，cgroup swap `0 B`。旧 energy-fail raw evidence保持原样。

## S2：局部 p6 恢复候选

从既有保存数组分别复核 top/bottom 局部块。已知场 forward relative 为 `5.3524732442130614e-14` / `5.143310794873929e-14`，Gate `1e-11`；raw local equation relative 为 `4.771522785641244e-16` / `6.413893640082291e-16`，Gate `1e-10`。原始及重算的 trace/port equations均通过，故保留为局部 repair candidate。

S2 并不证明整个 A 链通过：q60 全 882 行复检为 `NOT_RUN`（既有 q60 witness 保留）；全目标 volume MPC 为 `NOT_RUN_AUTHORITY_LIMITED`。wall `33.174783403 s`，CPU `36.778499242 s`，单 Python 进程 `ru_maxrss=634454016 B`。这是单进程资源记录，不能和任何进程树或共享 cgroup 峰值作横向相加。

## S3：可选 B0 direct reference 的边界

状态 `NOT_RUN_AUTHORITY_LIMITED_OPTIONAL_REFERENCE`。现存 direct chain 固定于 G0 witness/map，不能证明它与 B0 boundary-plane operator、RHS、输出坐标语义完全相同；本轮没有 B0 专用的整体 map witness。直接挪用会跨越 witness loader、direct assembly/native-action gauge 及 saved-output comparison，故留待具备匹配输入和身份绑定的后续窗口。该决策不是 capacity denial，不是 ABI failure，也不是缺少用户授权。

## S4：Gx560 四 q symbolic 后的资源 Gate

实际 attempt source `9977284c47c8028751de4dbecd12b95d1912a580`，run id `task40extra_0p7nm_nonseparable_gx560_p6_y_orbit_v11_v1`，input SHA-256 `7f20aa9719c91c6be4d6a4b4cd00ec8b7a7610fdf53c889f88a42ece03f17d1f`、physical model SHA-256 `d1ba222b0fe8989f6f8758f4f7a776506691e393f596f41ed02d25d0a9781d98`。网格为 10×4×14=560 cells，p6、340 modes、四个 y 周期 q；target保留真实三维 air void，所有 q 都需要。

行数是固定 case/sector shape 合同值；final all-q receipt保留 INFOG16/17/20，但没有保留 q matrix NNZ 与单独 symbolic stage time，故这两项是 `unknown`，不从 profile、矩阵占用或相邻总时长倒推。

| q | rows（合同/sector shape） | NNZ | INFOG16/17 (MB) | INFOG20 symbolic factor-entry estimate |
|---|---:|---|---:|---:|
| 0 | 28,508 | unknown | 1,157 / 1,157 | 41,320,088 |
| 1 | 28,508 | unknown | 1,150 / 1,150 | 41,253,248 |
| 2 | 28,576 | unknown | 1,169 / 1,169 | 41,789,336 |
| 3 | 28,508 | unknown | 1,165 / 1,165 | 41,269,544 |

INFOG16/17 是符号分析的内部数据内存估计，INFOG20 是满秩因子化所估计的因子项数；INFOG20 不是已存 numeric fill。见 [MUMPS 5.8.2 Users’ Guide](https://mumps-solver.org/doc/userguide_5.8.2.pdf)。最终准入事件 `all_q_symbolic_before_any_numeric` 的重点数值：

| Gate 字段 | 数值 | 类型 |
|---|---:|---|
| current process-tree RSS | `10,295,283,712 B` | Gate 当时采样 |
| all-q native symbolic estimate | `4,776,443,200 B` | MUMPS估算 |
| projected process-tree RSS | `15,205,944,640 B` | 准入预测 |
| effective finite cap | `13,462,286,336 B` | 本任务准入上限 |
| stop-time available physical memory | `3,301,220,352 B` | 系统当时样本 |
| stop-time physical launch cap | `3,167,002,624 B` | available减`134,217,728 B`写证据余量 |
| watchdog process-tree RSS peak | `10,418,892,800 B` | 全程 simultaneous tree peak |
| dedicated cgroup memory peak / limit | `10,930,950,144 / 17,179,869,184 B` | cgroup高水位/限值 |
| task/cgroup swap peak | `0 / 0 B` | Gate通过 |

结论 `RESOURCE_CONTROLLED_STOP_BEFORE_NUMERIC`。数值因子 allocated/used/fill均 `null / NOT_RUN`；KSP、field、residual、R/T/A也均 `NOT_RUN`。不得把 symbolic INFOG20误写成实际填充库存。进程身份覆盖完整、状态可读、leader exit 4、后代清理完成；这不是 OOM kill，也不是数值失败。

watchdog monotonic elapsed `2041.652704 s`，service wrapper monotonic workflow `2041.826505 s`，conservative UTC policy charge `2244.797416 s`。UTC与monotonic总差约 `203.143 s`，分别保留；该 charge 不等于 solve time。原始 `shared_budget.remaining_numerical_seconds_at_worker_entry` 为 `73181.66253952701 s`；watchdog `time_reference_seconds=73182.01969292195 s` 是父级入口参考，两个来源不混。Gx784因为Gx560没有通过而为 `NOT_RUN_CONDITION_NOT_MET`。

同一阶段有一个早期启动 guard拒绝未受监督的启动：`gx560_v11_console.log` 109 bytes，SHA-256 `80fcf085a1177e7700e68c7f25309d083c52b88e5e093eb55832c02705d64d1c`；该失败没有数值工作，准确耗时/成本 unknown。实际 attempt 后由 service dispatch回执转入固定 V11窗口。

## S5：完整 882 行边界动作

这一步把原本限于少数模式的 dot 支持组件扩展到两个冻结代表面上的全部 32,060 个有序模态。它解决的是“逐模式应用完整边界矩阵，结果是否与保存的 q60/reference 动作一致”；它不建立全边界 global MPC，也不运行 Maxwell PDE。

运行合同为 top/bottom 各 16,030 模态、每面882个 native rows、q60共961个采样点、mode batch 16、point chunk 64。没有分配 32,060² 矩阵，也没有保留 mode×882 全量映射。full checker误差如下：

| 面 | full Bα相对差 | full Dx相对差 | 独立 checker |
|---|---:|---:|---|
| top | `1.1308675126224078e-13` | `3.861920061984271e-14` | PASS |
| bottom | `1.0414255157250765e-14` | `3.908206118402893e-15` | PASS |

trace adapter只选择84个表面行做 extract/scatter一致性诊断；这84行不是 B/D压缩。84行替代尚未资格化，本轮主线没有重跑压缩，因此不对其压缩效果或证书结果作结论；本次完整动作使用882行。

每面 helper内部wall约 `0.902 s`、CPU约 `1.003 s`。所有四个阶段由同一 systemd service串行托管：

| 阶段 | wall (s) | process-tree RSS peak (B) | swap (B) |
|---|---:|---:|---:|
| small_action | 3.905585 | 455,847,936 | 0 |
| small_checker | 3.135299 | 495,640,576 | 0 |
| full_inventory_action | 4.934123 | 457,056,256 | 0 |
| full_inventory_checker | 2.868228 | 381,509,632 | 0 |

共享 service wall `15.182 s`、CPU `11.481 s`，同一 cgroup 的 `memory.peak=546,459,648 B`，swap peak 0；PSS被 profile关闭，记录为 null。共享 cgroup高水位不是每阶段的 memory peak；各阶段process-tree RSS是独立树采样，也不能相加。Helper自有数组理论上界 `7,313,968 B` 不是 RSS。

三次修复尝试保留为工程事件：两次启动前分别因 `ModuleNotFoundError: No module named benchmarks` 与旧 campaign time参数 `ValueError` 退出，未做数值动作；一次 worker 因 `NameError: construction is not defined` 停在 trace extract/scatter 后，Bα/Dx输出未落盘，tree RSS peak `453,398,528 B`、swap0、后代清理完成。早期 service memory 字段先前被存为 `1,258,291 B`，但这是对约`1.2M`舍入显示的换算，不是精确cgroup bytes；精确值unknown。修复后的四阶段全部通过。

## 阶段成本与计时范围

| 阶段 | wall / elapsed | 计时范围 | 能否与相邻项相加 |
|---|---:|---|---|
| B0 p6 full worker | `1051.699122267 s` | 完整 worker 生命周期 | 包含其内部子阶段，不与 setup/KSP 子项相加 |
| B0 reference factory/setup | `2.376073938 s` | setup 子阶段 | 已嵌套在 full worker 范围 |
| B0 pure KSP | `4.899454752 s` | 纯 KSP 子阶段；parent solve `6.441171838 s` | 不是独立追加时间；parent 包含子阶段 |
| V10 saved-output recovery | `33.431334133 s` | 独立保存结果后处理 | 单独记录，不并入 B0 worker |
| V11 S1 saved-field recheck | `11.256015081 s` | 独立保存场复核 | 单独记录，不并入 PDE worker |
| Gx560 service workflow | `2041.826505 s` | 服务工作流直到数值阶段前受控停止 | 未完成 solve；不与 policy charge 相加 |

这些数字属于不同 source 和不同测量范围。尤其 Gx560 的 watchdog `2041.652704 s`、service workflow `2041.826505 s` 与 UTC policy charge `2244.797416 s` 是同一 attempt 的三种口径，不能相加或互换。

## S6：资源判断、预算、下一步与 selective handoff

固定预算窗口SHA-256 `1014f9ff536344d0829c1e58f1a1f25373be7b18f11bddd132e15a23558a0bd1`，deadline `2026-10-07T01:17:35.732545140Z`，closeout reserve 600秒。历史 seq 8089 观察在 UTC `2026-10-06T07:59:59.678778633Z`：累计 policy charge `24167.947039851726 s`、derived numerical remaining `61632.05296014827 s`，原样保留。其后主控单一写入者已记录交付观察 seq 8090，在 UTC `2026-10-06T09:14:00.836725318Z`：累计 policy charge `28609.104986536724 s`、derived numerical remaining `57190.895013463276 s`，`window_refreshed=false`、`final_settlement=false`。最终 Git/测试尾段由主控在同一账本后续计入；执行者不写账本，也不从 worker wall 推算余额。

| 依赖组 | 当前证据与建议移交 |
|---|---|
| production numerical/core | gauge-aware saved-field输出接口在B0已保存场上及独立Poynting检查通过；保留显式gauge/opt-in语义，ordinary default不变。最终production迁移仍须review判断依赖与回归范围 |
| reusable runner/watchdog | 继续复用现有统一 runner/watchdog；本轮不新增通用runner，也不改普通入口 |
| checker/benchmark | S5 full882 action/checker仅资格化两个代表面；保留原始checker与限定范围，不提升84行压缩或全局MPC资格 |
| compact evidence/docs | 本回应、综合报告、summary、test summary、development progress、model registry及五个V11 compact records可随review审查 |
| research-only | B0四q p6 reference inverse及Gx560四q symbolic受控停止；保留因子和资源证据，不设为production default |
| do-not-merge | 未运行的Gx784、完整15,232-cell/原尺寸自动路径、全域global MPC、未资格化目标资源预测；不得登记为通过 |

### Review §8 组件依赖与后续审阅入口

以下是供后续 review 读取的依赖与证据索引，不是工作站迁移授权。V11 的 ABI receipt SHA-256 为 `ac3a1120d8061fc91c818150177977e619de2fccb27fed1262cea45d90268426`：PETSc `complex128/int32`，PETSc 3.25.6、MUMPS 5.8.2、MPICH 5.0.1，MPI1、数学线程1。该组合只证明当前本地小模型运行环境；原尺寸 CSR/NNZ/offset 是否仍在 int32 范围内尚未资格化。S2 residual accumulator 实测 `numpy.clongdouble` 为 complex256、real mantissa 63 bits、itemsize 32 bytes；其他平台必须重新检查该 dtype 的精度和布局。

| 组件 | 主线源模块 | 已有测试 / 输入入口 | 当前资格与拒用范围 |
|---|---|---|---|
| gauge-aware port power | `src/solvers/dtn_port_3d.py`、`src/solvers/dtn_boundary_phase_gauge.py`、`src/runners/task40_v10_saved_output_recovery.py` | `src/test/test_task40_v11_boundary_plane_port_power.py`、`src/test/test_task40_v11_scientific_field_export.py`、`src/test/test_task40_v10_saved_output_recovery.py`；B0 saved field source `c439ed40768de4745131b43fc0312bb8be8d9d50`，输入 `input/task40extra_0p7nm_engineering/b0_p6_y_orbit_reference_v10.dat`；结果见 [gauge-power compact](records/review_v11_gauge_power.json) | 532-mode saved field physics recheck；boundary-plane 为显式 opt-in，legacy global-z ordinary default 不变；非新 PDE 或目标规模资格 |
| S2 local p6 recovery | `src/solvers/task40_w1_local_probe.py` | `src/test/test_task40_w1_local_recovery.py`；运行父 HEAD `9977284c47c8028751de4dbecd12b95d1912a580`，该源/测试文件 SHA 与 26 项结果见 [local-recovery compact](records/review_v11_local_recovery.json)；输入为 compact 所列两面 saved arrays | 两个局部块的候选恢复与端口方程通过；完整 q60 行重检和全目标体积 MPC 未运行，不提升为完整边界链 |
| p6 y-orbit / MUMPS reference | `src/solvers/task40_v10_p6_yorbit.py`、`src/solvers/task40_v10_p6_mumps.py` | `src/test/test_task40_v10_p6_yorbit.py`、`src/test/test_task40_v10_p6_mumps.py`、`src/test/test_task40_v11_p6_grid_contract.py`；B0 输入 `b0_p6_y_orbit_reference_v10.dat`，Gx560 输入 `nonseparable_gx560_p6_y_orbit_v11.dat` | B0 four-q candidate retained; Gx560 stopped before numeric factors. Research-only; no ordinary-default promotion or original-size extrapolation |
| full-882 chunked boundary action | `src/solvers/task40_v11_chunked_boundary_action.py` | `src/test/test_task40_v11_chunked_boundary_action.py`；S5 saved local arrays, 32,060-mode manifest and two-face checker in [engineering-results compact](records/review_v11_engineering_results.json) | Mainline helper has its own source-bound action/checker results for two faces only. Dot commit `15713d3e09b63f65511c7b7f61fa043fdb23dca5` was read-only reference; no file-by-file migration, and no dot PASS is inherited as mainline qualification. Not full-boundary MPC/operator norm/PDE |

所有这些结果都受限于上表所列模型、数组和测试入口。不得据此迁移到 workstation、创建原尺寸全局 factor，或宣称 index width/资源/精度门已通过。

下一项唯一优先工作是查明 Gx560 在 numeric 前 `10,295,283,712 B` live process-tree RSS 工作集的对象所有权与生命周期。来源类别当前仍为 unknown；不能归因给 Python heap、有限元装配或 numeric factors（数值因子尚未建立），也不先启动新的预条件器实验。相同资源状态不原样重跑；若后续扩展，需新窗口重新绑定输入/源码身份、观察物理可用内存并分阶段准入。可复用的正面部分仍是已保存场的 gauge-aware 输出、S2 局部方程候选及 S5 双面全模态 882 行动作与 checker。Gx784 依赖 Gx560 通过，当前未运行；没有据此推断 2 TB/48 h 通过。

## 测试、代码身份和证据入口

当前文档与实现冻结HEAD为 `223f602b84761eb99631e7a61a784c3d6c857c04`。S2 定向测试 `26 passed` 的执行父 HEAD 为 `9977284c47c8028751de4dbecd12b95d1912a580`；当时源码/测试文件 SHA-256 分别为 `3c8bd3bef250a590e433247ac287cc43b9e134dfa48d7a09183cc98ad90b4ff6` / `be4575083a17df3af6f1bd51e35e49ba0d70be4eaf8a0ab44641a89c9baeb21e`，随后实现冻结在 `a1c5c6040cc3674418bbebd877790b1882ac010f`。S5 helper tests 为 5 passed（冻结 HEAD `223f602b…`）；artifact-local runner `py_compile`通过。S1与S5另有独立结果checker。最终文档合同检查列在 [test summary](test_summary.md)；full repository pytest、MPI4、Ruff、CI均 `NOT_RUN`。

| 证据 | 路径 |
|---|---|
| 统一执行回应 | [response_v11.md](../response_v11.md) |
| S1 gauge-power compact | [review_v11_gauge_power.json](records/review_v11_gauge_power.json) |
| S2 local recovery compact | [review_v11_local_recovery.json](records/review_v11_local_recovery.json) |
| S4/S5 engineering results compact | [review_v11_engineering_results.json](records/review_v11_engineering_results.json) |
| 成本与保留修复 compact | [review_v11_cost_and_repairs.json](records/review_v11_cost_and_repairs.json) |
| 窗口/身份 manifest | [review_v11_manifest.json](records/review_v11_manifest.json) |
| 结构化运行索引 | [run_index.json](records/run_index.json) |

本报告只归纳存在身份和证据边界的结果；MUMPS measured inventory、符号估计、单进程RSS、进程树RSS、共享cgroup peak与campaign policy charge均分别保留口径。未完成项仍是 `NOT_RUN`、`unknown`、`RESOURCE_CONTROLLED_STOP` 或 `NO_GO`，不改写为通过。
