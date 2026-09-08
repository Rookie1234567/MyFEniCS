# 不收敛诊断 V3：D0 盘点与待审执行设计

当前状态：D0 文件身份盘点、双时钟 tiny 验证、D1-D3 最小数值接口和参考容量预审完成；原始尺寸 canonical/Floquet 重建、原 A 作用、参考求解、投影和 PC 诊断均为 `not_run`。本页不代表 D0-D5 已完成。源码 HEAD 为 `97e82eeb08b6c2faef6457356cdc643832a75eb8`，当前改动未提交，正式诊断需使用随后审阅的 clean source。

## 已读取的证据

| 样本 | 角色 | 历史显式真残差（无量纲） | 本次文件核验 |
|---|---|---:|---|
| A2R160 | 默认 S6 路线 checkpoint | 0.18250767622880507 | 通过 |
| LIGHT448 | 默认顺序 LIGHT checkpoint | 0.09814591160304939 | 通过 |
| JOINT448 | 默认联合接受 checkpoint | 0.10713326900483655 | 通过 |
| LIGHT576 | 仅离线终点补充 | 0.0791360407785889 | 通过 |
| JOINT476 | 仅离线终点补充 | 0.10535820013809101 | 通过 |

“通过”仅指读取实际 solution、manifest、dat、resolved_config 和 source 文件后核对 SHA256、大小、shape、complex128、finite、MPI1、solution-only 角色及物理身份。表中残差为旧记录，本轮未重算。五个向量均为 173802 个系数；历史 setup 标记其中 9210 个为 Floquet 从属行、164592 个为独立行。对应文件完整路径与 hash 见 [结构化盘点](records/nonconvergence_diagnosis_v3.json)。

共同物理 SHA 为 `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`，setup 中 mode SHA 均为 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。已对 T3 v2 实存 mode_manifest 文件计算 hash 并匹配五份 setup；尚未重建当前模式。三个来源源码不同，operator hash 的定义包含 source SHA、physical、modes 和 volume quadrature；不能仅由 hash 不同判物理算子不同。

原 checkpoint 未附 canonical 映射，不能仅凭向量长度直接宣称映射资格通过。下一块须用原网格/同 ABI 重建独立行、orientation 与 Floquet 关系，核对实际系数排序和原积分，再重算 `r=b-Ax`。共享数值文件的源码比较是线索，不代替作用验证；不匹配的样本隔离。x 是电场的有限元系数（primal），r 是方程残差（dual）；本轮没有把 r 当电场能量。

## 参考解盘点与安全路线

| 搜索对象 | 实际发现 | 结论 |
|---|---|---|
| results 与 benchmark artifact 的非 test/tmp run_manifest | 11 份，已逐份保存索引和 hash | 未发现可复用的合格同模型 full-p6 已解场 |
| Task038 T3 formal v1/v2、p6-h10 MPI1 record | 同物理、80 modes；保存 source/action/reference_action/recovery | reference_action 是算子对比结果，不是物理解 |
| Task038 T5 authority | 保存 RHS/canonical 对比且有旧 dual extractor 不合格记录 | 不能提升为已解参考或直接借用旧 dual 映射 |

盘点结论为 `NO_MATCHED_SOLVED_FINE_REFERENCE_IN_INSPECTED_INDEXES`。随后的容量预审见下表；不声称 16GB 上普遍无法求参考。

| 容量依据 | 数值与口径 | 对本轮的含义 |
|---|---|---|
| Task37 direct authority v2 | p6/h10，252 cells，10°、MPI8，51272 augmented rows | 阶次/网格规模相同，但角度、MPI、源码不同，不是当前场参考 |
| 原始同期 process-tree RSS | 15.059223175 GiB | 高于当前 cap；不能除以8当作 MPI1峰值 |
| 历史 factor NNZ | 209772680；仅 complex128 数值负载推导3356362880 B | 不含索引、工作区和分解临时峰值，不是 factor RSS 上界 |
| 历史 allocated matrix NNZ | 42625520；int32/complex128 CSR 推导852715492 B | 不含 PETSc/allocator 额外存活对象 |
| 本次只读 memory envelope | MemAvailable12735438848 B，reserve4294967296 B，cap8440471552 B | 启动时仍须重读动态值 |
| 安全结论 | MPI1 fill/pivoting、assembly/recovery 生命周期和额外工作区无可信峰值上界 | `REFERENCE_UNAVAILABLE_ON_16GB`，仅指本轮所审路径在该安全合同下不可资格化；不启动 assembly/symbolic/numeric |

完整旧记录路径、hash、未知量与本次 envelope 已写入中心 JSON。没有用存储下界冒充整体预测，没有把旧 MPI8 峰值当当前 MPI1 实测。此预审后优先走无参考路线：三个真实 residual 各调用三个旧 PC 一次，已知误差另作 field-error 诊断，避免容量研究拖延原因定位。

待审路线：从原 dat 派生一次显式 Full3D direct reference 输入，走现有 `scripts/run_case.py`、`src/runners/task038_full3d_direct.py` 与现成凝聚能力。凝聚是先消去单元内部未知量以减少全局分解行数，代价是保存局部恢复数据；不得新造求解器。先读已有同阶资源记录，分列矩阵/局部恢复/因子/工作区的同时存活内存；无可信上界时不进入 numeric。assembly 与 symbolic 分级受 watchdog 约束，symbolic 估计连同当前 RSS、临时量及不确定性必须低于动态 cap，否则停止。预算最多 3600s，系统余量 max(4GiB,15%)、cap≤12e9 B、树 swap=0。此处尚未完成安全资格化或启动 assembly/symbolic/numeric。

若允许一次求解，恢复 full p6 后用原 A 检查残差≤1e-10，并在三个预定合法向量（两种不同周期谐波分量及其和）上比较原/参考作用。至多一次同 factor 残差修正，记录场范数/固定采样点稳定性与 `Ae-r`；只有参考不确定性远小于待测误差才形成三份 `REFERENCE_ESTIMATED_ERROR`。随后释放 direct 矩阵和 factor，再建 PC 栈。不能安全完成时按 review 保留 `REFERENCE_UNAVAILABLE_ON_16GB`，继续已知误差与残差诊断。

## 最小 D1-D3 接口（已实现，原始尺寸尚未运行）

| 接口/复用位置 | 问题、输出与限制 |
|---|---|
| `component_diagnostics(action, x)`；复用 `fullspace_physical_action` | 返回 Kx、负质量项、边界项范数与复内积，查大项抵消；不推断完整条件数或谱 |
| `LosslessFEMetric` / `cell_energies`；`physical_error_metric.py` | 用实际无损 FE L2 质量 M0 测电场大小，以缩放 curl 测变化；独立约束空间和原积分，从属 identity 行不计能量；输出 cell 积分及材料/坐标标签供分区汇总 |
| `project_error(P, M0, e)`；同一小模块 | 仅一次固定对角 CG 解 p4 质量方程，rtol1e-10/max256；输出最佳可表示部分、剩余部分、正交与 Pythagorean 缺陷；不闭合则 `PROJECTION_UNRESOLVED` |
| `coarse_diagnostics`、`evaluate_profiles`、`evaluate_residual_profiles`、`homogeneity_check` | 复用原 transfer、p4 solve 和三个 PC；返回单位 coarse/MR coarse、coarse identity、互补应答、场误差或真实 residual 收缩；无参考时 remaining-field-error 明确 unavailable |
| `DiagnosticActions` / `supervise_diagnosis`；`physical_diagnosis.py` | 借用一个 S6/A6/P64/p4 栈，另建原 LIGHT H6，三个 PC 共享 p4 factor；桥接立即复制借用缓冲；父进程 diagnosis/reference 两路径均显式 `timebase_guard=True` |

预定已知误差的解析式已在 JSON 冻结：令 u、v、t 为 x、y、z 的归一化坐标，用横向 Floquet 因子乘 `sin(pi*t)`，内部为向量 a 乘 `(u+v)` 谐波，加向量 b 乘 `sin(2*pi*t)` 与 `(2u-v)` 谐波；a=(1,i,1+i)，b=(1-i,2,-i)。两组不同横向谐波和 z 依赖使其不是单个可分乘积，三个分量均非零。经合法 p6 Nedelec 插值和约束后得到 e_test，使用真实全模型 q=Ae_test；按 norm(q) 同比缩放 e、q，冻结后不根据 PC 结果选更容易的样本。此控制不等于非可分材料 full solve。

| 调用计划 | 默认数/最大数 | 时间约束 |
|---|---|---|
| 样本 | 有参考时三份实际误差+一份已知误差；无参考仍测三份实际 dual residual，仅已知误差解释 remaining-field-error | D1/D3 合计≤7200s |
| 三完整 PC | 每样本各一次；最多4×3=12；已知误差同比缩放复查再3次 | 默认最多15，硬上限36；不为用完预算追加 |
| H6/S6 互补 | 本次无参考路线仅已知误差：各一次+同比各一次 | 默认4，投影不闭合则跳过；不补满硬上限18 |
| M0 投影 | 本次仅已知误差一次 | 累计≤1800s，计入 D3 |
| 可选 fine reference | 一次 | workflow≤3600s |
| D4（本块不做） | 仅原因证据需要时≤4个小特征问题 | ≤900s |

p4 backward residual≤1e-10 不自动证明 forward correction 精确。投影闭合且 dG 属于 range(P) 时，复用已有向量计算 `norm(e-dG)^2 ≈ norm(e_perp)^2 + norm(e_parallel-dG)^2`（均为 M0 范数），不增加 p4 solve。这把空间无法表示的部分与粗修正偏离最佳表示的部分分开。再用 coarse identity control 检查实现/近似逆；通过后也不能立即把误差归因于色散或共振。

最终四类原因分别处理：①粗空间表示能力；②实际粗响应/传递与求逆；③细层对互补误差的作用；④实现成本、时钟与 restart 证据。每类允许 `SUPPORTED`、`NOT_SUPPORTED_ON_TESTED_SAMPLES`、`UNRESOLVED` 或 `MIXED`。没有 Hessenberg/正交性记录时，曲线拐点不能证明 restart 因果。最多提出一个由证据支持的后续改动，不在本轮执行新 PC。

## 本块验证与边界

新增时钟 helper 和 parent/worker 接线，保持默认关闭；启用后同边界保存 monotonic、BOOTTIME、UTC、clock_info。预算用两种单调时钟较大值；未知差异超过 max(5s,1% interval) 保存 `TIMEBASE_INCONSISTENCY` 并停止，用户停止与资源硬门仍优先。没有改写旧 raw 或解释旧差异原因。

轻量 ABI preflight 通过；6 个 focused tests 通过，pytest 4.37s，外层双时钟预算 4.544520168s，UTC 间隔 4.544520362s。覆盖容差、缺少 BOOTTIME、倒退、worker 写入后报错、父进程两种停止与清场及旧生命周期相关路径。日志位于 `benchmarks/artifacts/task39extra/v3_d0_clock/tiny_tests.log`；未运行 181/全仓/MPI sweep/PDE。

D0 metadata 脚本第一次直接从 /tmp 执行因 `src` 不在模块路径而失败（0.237s 命令记录），未加载模型；改为仓库入口后读取成功（脚本双时钟 0.122330350s）。该失败保留，不作为环境或算法失败。V3 上限14400s，当前已测 tests+D0 成功部分约4.667s，另保守计该失败1s；尚不把它称全阶段完整 wall。后续正式执行必须连续扣账，包含失败/构建/释放。

第二块实际测试：先7 passed（2.00s，双时钟2.276431524s）；追加预定已知误差插值/同比检查和投影累计预算接线后，最终8 passed（1.15s，双时钟1.720125310s），无失败。测试只包含新代数/18-cell p2 FE及两项 finally 时钟分类回归；没有原始 p6/h10 PDE。日志为同目录 `diagnostic_tests_1.log`、`diagnostic_tests_2.log`；中心 JSON 保存命令、clock、hash 和当前实现文件 hash。编译/diff 检查通过。

细节修正：finally 在 workflow 超时或已有 stop_signal 时不再覆盖 `TIMEBASE_INCONSISTENCY`。`DiagnosticActions.project` 将固定对角构建及每样本唯一 CG 纳入共同1800s；用尽即 `PROJECTION_UNRESOLVED`，不启动另一种投影。粗误差分解复用 dG 与已有投影向量，不为分解新增 p4 solve。

固定薄入口现已实现：`python -m src.runners.physical_diagnosis`。在一个 clean-SHA MPI1 worker 内读取中心样本、按原 dat 构造同 mesh/ABI/order，保存 p6/p4 native constraint map、canonical mesh witness与metric hash；核对原 operator hash、三个历史残差和 component sum 后，逐次落盘真实 r 的9个PC结果，再执行已知误差3个PC与3个同比检查。投影和粗作用仅作用于已知误差；先测一次原始 p6/p4 M0 Galerkin关系。投影超时/不闭合只锁定相关结论，三个实际残差探测已先完成。共享一次S6/p4栈，独立互补默认4次；无长外层FGMRES或新PC。

入口固定 `timebase_guard=True`，工作流≤7200s、树swap0和动态cap。D2因安全预审不通过不启动。既有cache可通过 `--cache-path` 复用，启动/结束记录逐文件hash和本次ABI；没有新增cache平台。每个完成probe立即保存ignored JSON/NPZ、hash、时钟成本和完成计数。首调用实测输入不变及输出slave-zero，不通过就停止；不是先丢弃slave再宣布合法。所有已有 z/Az、normalized q/e 与尺度、原误差/单位剩余/MR剩余 M0 能量均保存，可离线复算ratio；同比probe保存已有scaled correction，无新增A作用。

端口接线已按真实内存类型修正：`beta` 为 complex，排序直接取其模。一次无网格的原始配置读取得到80 modes且hash匹配；选定incident之外的三个branch为bottom(0,0)、bottom(-1,-1)、bottom(-1,1)。完整mode manifest按原编码保存，packet中也保留复数k分量，不用绝对值替代物理定义。

最后验证：入口整合后同一8项小批次通过（1.52s），复数packet/hash读回通过；beta修复与bridge首调用检查后，仅复验1个tiny FE检查（0.90s）及80-mode配置读取；最后raw能量/Az字段只复验2个原有代数检查（0.12s）。未扩展回归集合。日志分别为 `diagnostic_tests_3.log`、`bridge_mode_check.log`、`raw_evidence_check.log`。移除了不必要的库路径前缀断言，保留activation、repo解释器、complex128/int32、MPI/线程资格与真实模块路径/version记录。最终编译/diff检查通过。

待主任务提交并批准完整源码SHA后，精确调用模板如下；该命令本块尚未执行，artifact目录必须尚不存在：

```bash
source scripts/activate_myfenics_wsl.sh
export GIT_DIR="$PWD/.git-codex" GIT_WORK_TREE="$PWD"
python -m src.runners.physical_diagnosis \
  --input input/task39extra/original_13p5nm_p6h10_p4_reference.dat \
  --inventory docs/task039_extra_physical_multilevel/outcomes/records/nonconvergence_diagnosis_v3.json \
  --directory benchmarks/artifacts/task39extra/v3_d1d3_no_reference \
  --cache-path "$PWD/results/euv_grazing1_phi0/original_13p5nm_p6h10_light_p4ref_jointmr3_v2__full3d_iterative__mpi1__Mna/20260908T034629.980337Z/jit_cache" \
  --expected-sha APPROVED_FULL_40_CHARACTER_SHA \
  --remaining-seconds 7200
```

上面的7200还须与本轮14400s批次剩余额度取小；不借用V2余额。诊断完成后再只读形成原因矩阵，D4保持条件项。本轮tiny结果不等于原始模型资格。

本块未 commit/push。按主任务要求暂不原始尺寸 action/reference/PC；等待其读取 diff 后进入 clean-source 测量，不启动或续跑旧 R3/F3。
