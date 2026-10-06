# V12 移交与原尺寸就绪判断

这份说明为下一轮提供可核对的源代码边界、运行依赖、实际模型输入和唯一建议实验。当前冻结源码为完整 Git source `6d2c54389fe885ecf24d474a8782166ff31f9154`；接收方应取得这个完整 source tree，不应只拷贝某几个 `.py` 文件。所有模型均是显式 Task40 工程研究 profile，ordinary solver default 没有改变。

## 方法模块与状态

| 模块/接口 | 作用 | V12 实际证据与限制 | 移交分类 |
|---|---|---|---|
| `src/solvers/y_orbit_transform_bank.py`、`src/solvers/task40_v10_p6_yorbit.py` | 将 p6 单元内部坐标变换的相同矩阵集中到 run-local backing owner，实体记录只保留视图/索引，避免每个 cell 都持有一份完整 450×450 matrix | Gx560 bank-ready 事件实测到一个 3,240,000-byte matrix backing、1,121 个共享视图；作用仅到 cell-interior，edge/face仍走legacy。它证明本场发生了共享存储，不证明整场RSS下降了3.6288 GB | 显式研究候选；Gx560完整参考逆 Gate 未通过，不能作为生产默认 |
| `src/solvers/p6_cell_condensed_action.py`、`src/solvers/task40_v10_p6_yorbit.py` | 每个局部单元先消去内部自由度，求解时再用局部方程恢复内部场；这缩小全局系统，但需额外保留/应用局部块 | Gx560内部恢复 `8.8451e-17`，两个扇区 native-action一致性 `2.3443e-12`；局部原方程合并 `1.4184e-10` 超过 `1e-10` | 研究候选；局部内部恢复通过不能替代原局部方程门 |
| `src/solvers/fullspace_dtn_action.py`、`src/solvers/dtn_port_3d.py` | 用全模式端口动作施加开放边界条件并恢复端口辅助振幅，避免把端口方程误当作普通体内行 | Gx560覆盖340个端口方程且残差 `5.0439e-13`；global alpha/port closure `1.1770e-11` 超过 `1e-11` | 全模式研究路径；本轮未完成外层Full3D求解 |
| `src/solvers/dtn_boundary_phase_gauge.py`、`src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py`、`src/runners/task40_v10_saved_output_recovery.py` | 明确 solver 坐标与端口参考面的相位换算，使保存场功率使用同一 gauge；修复B0保存输出范围后重新核对功率 | B0保存场离线 Gate 通过；fresh worker 的原始 exit 4 与 `official_result=false` 原样保留，离线重算不晋升原worker分类 | 可复用的显式输出/后处理路径；仍需按目标输入独立资格化 |
| `src/solvers/task40_v10_p6_mumps.py`、`src/runners/task40_v10_worker.py` | 构造四个 q 的 p6 参考因子，执行 numeric probe，再进入受控完整场 worker | Gx560四q factor probe均通过，但 generic reference inverse 的原方程、两局部原方程、alpha closure三项不通过；FGMRES未启动 | 研究候选；不是完整通过的PC或求解器 |

上述文件共同依赖同一仓库 source SHA 和 Task40 run profile。对应的 focused tests 定义在 `src/test/test_task40_v12_p6_transform_bank.py`、`src/test/test_task40_v12_transform_bank_algebra.py`、`src/test/test_task40_v11_p6_grid_contract.py`；测试结果以 V12 测试摘要中有原始回执的条目为准。

## 输入模型和真实运行范围

| 模型/输入 | 真实身份 | 状态 |
|---|---|---|
| B0 fresh reference | `input/task40extra_0p7nm_engineering/b0_p6_y_orbit_reference_v12.dat`；SHA256 `d4d72a4288aa0313432f7bea668543c60a2716144ce9c8333b2c271367d8f73e`；physical SHA256 `250c26f25d85c0ff68abb0454a6c7640bf8d3af3e6f96bbf599a8cf7c925ae73e`；80 cells、p6、532 modes、4 q、原两单元缺口 | fresh完整求解和 residual 通过；producer source `c08c135` 在输出门 exit4。source `6d2c543` 对保存数组的输出范围/功率复核 PASS，但保留 `official_result=false` |
| Gx560 engineering target | `input/task40extra_0p7nm_engineering/nonseparable_gx560_p6_y_orbit_v12.dat`；SHA256 `50c8691446cbc24533ee31ae945c75806c29a0a06d002287723f814372ba44a9`；physical SHA256 `d1ba222b0fe8989f6f8758f4f7a776506691e393f596f41ed02d25d0a9781d98`；560 cells、p6、340 modes、4 q、10×4×14网格 | fresh formal attempt 到达四q numeric及generic reference inverse witness；三个严格 Gate 失败；KSP/物理输出未到达 |
| Gx784 conditional engineering target | 14×4×14、784 cells、p6、340 modes；冻结输入 `input/task40extra_0p7nm_engineering/nonseparable_gx784_p6_y_orbit_v12.dat`，SHA256 `56d9b05bf157a213d608da93e42fdd1dad6377aa9fad96cdd962d3f6086abdd5`，已完成输入格式校验 | `INPUT_FROZEN_BUT_NOT_RUN`。Gx560 Gate 失败后没有启动 Gx784；输入存在且已冻结，不得描述为缺失或未创建 |

三份记录代表参考 anchor、主要工程阶梯和条件阶梯。它们不能相互替代；Gx784 的输入已经冻结并通过格式校验，但 Gx560 Gate 失败后没有运行，因此状态是 `INPUT_FROZEN_BUT_NOT_RUN`，不是缺少输入。

## 必需环境与 ABI

使用记录中经过资格化的 Task40 local WSL Linux runtime，由 `scripts/task40_fresh_c1/activate_local_wsl_complex.sh` 按 runtime prefix、ABI receipt和JIT目录激活。数值身份要求 `PETSc.ScalarType=complex128`、`PETSc.IntType=int32`、MPI1、数学线程1；Python/petsc4py/PETSc、slepc4py/SLEPc、DOLFINx、Basix、FFCx/UFL、mpi4py和MUMPS必须来自该同一 Linux ABI 栈。Windows Python/MPI不参与正式执行。准确包路径和 receipt 以 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w12_wsl/b0_v12_abi_preflight.json` 与各 run manifest 为准；本移交不从当前 compact 记录猜测未列出的包版本。

## 原尺寸 2 TB / 48 h 判断

当前结论为 `NO_GO / NOT_QUALIFIED`，不是已证明在其他硬件或算法下数学上不可解。V12 Gx560 的四因子销毁前 allocated/used 保守上界为 `4.645/4.080 GB`，同一 live inventory 的 process-tree RSS 为 `10.022 GB`，全程 tree/cgroup峰为 `10.182/10.709 GB`。这些是560-cell、340-mode参考构造与失败见证的实测，不包含外层迭代、完整场恢复、官方物理输出或32,060-mode AUTO目标。

旧实现以 2N 份 450×450 complex128 内部变换矩阵推导的 `98,703,360,000 B` 是重复矩阵载荷模型；bank 的 logical-view与unique-backing字节差是命名分配账，不是进程RSS的配对测量。当前还缺：15232-cell/32,060-mode目标的全部 q factor和fill、所有因子同时存活时的峰值、目标级JIT冷启动/复用时钟、完整PC apply和外层迭代次数、目标精度、所有q及场/输出阶段的生命周期证据。不能用单一的cells线性倍率填补这些未知，也不能据此宣称2 TB或48 h足够。

| 条件情景 | 需要满足的条件 | 当前可作出的判断 |
|---|---|---|
| 乐观条件 | 完整 AUTO 路径避免显式物化所有模式两两耦合的 mode² 矩阵；全部 q 的实际 factor fill 与同时常驻受限；冷 JIT 和恢复/输出阶段受控；完整预条件器通过精度门，且真实外层迭代数可控。 | 这些条件若逐项由目标级证据证实，才可能建立 2 TB / 48 h 路线；目前目标级内存、时间和精度上界仍为 `unknown`，尚未资格化。 |
| 保守条件 | 若全部 q 的 factor fill、物理缓存/端口工作区或严格 residual correction 调用成本随目标规模增长。 | 当前小场结果无法给出安全的目标内存或时间上界，结论继续为 `NO_GO / NOT_QUALIFIED`。 |

共享 bank 的代码来源为 dot 冻结源 `15713d3e09b63f65511c7b7f61fa043fdb23dca5`、blob `ff40105bd9139a856b09987596c961458f84ab0e`，原文件 SHA256 `9ece954f962dc6bab18a02f6b48b53998219fba3f611647a44404757f219b66f`；它是 p4 bank source 对 p6 cell-interior 的适配记录，不是 84-row 压缩资格，也不表示本轮访问或修改 dot。该来源只解释设计沿革，不证明主线 p6 数值门。84-row 压缩路径未资格化；两个代表面32,060-mode动作不能替代全局AUTO算子。ordinary default、master和跨机器源均未改变。

## 下一唯一建议实验（尚未授权或执行）

若下一 review 明确批准，优先评估同一四q参考增广算子上的一次完整 residual correction。令 `x=(u, alpha)` 同时包含全部 FE 未知量和 alpha/port 振幅，`e=b-A_ref_aug x`，用已冻结的参考增广动作算 `delta=M_ref_aug e`，再更新 `x1=x+delta`；这里 `A_ref_aug` 是 gap-filled reference augmented action，target `A6` 保持原样，不假设 `D=B^H`。四个 q 一次校正合计最多增加四次 q `MatSolve`。随后仍按原定义、原门限独立核验完整原方程、两个局部原方程和 global alpha/port closure；一次后即停，不反复迭代到过门、不降低门限、不丢弃 q/模式或调整分母。执行前应预注册完整 source/input 身份、一次校正上限、额外 solve/workspace 计数方式和原有16-GiB/零swap/resource watchdog。

每 q 至多一次 `MatSolve` 是建议中的额外工作上限；实际总 solve 次数、work time、临时 vector/workspace 峰值和 FE/PC 是否重建均为 `unknown`，没有通过本轮测量。已知的29.169 s只覆盖输入矩阵已存在后的 MUMPS builder构造器局部计时，不能代表完整准备。本条是路线建议，不自动启动Gx560 replay、Gx784、原尺寸PDE或工作站迁移。
