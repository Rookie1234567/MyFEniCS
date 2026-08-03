# Task37 Stage 0：iterative port matrix

## 目的与边界

本表把已经有证据的 direct/iterative 入口放在同一张地图上。静态凝聚的
直观含义是：先消去单元内部只在本单元使用的未知量，再求较小的界面系统，
最后恢复完整有限元场。它减少全局行数和矩阵非零元，但会增加局部消元、
界面稠密化和场恢复成本。迭代路径还必须避免把 direct factor 重新放回
内存，因此不能仅凭“行数变少”宣布成功。

本轮只完成 F1-0 架构 Gate：冻结已有对象的边界，比较 A/B 两条实现路线，
不实现 operator、preconditioner、runner 或 iterative candidate。

## F1-0 强制端口矩阵

`p2 iterative current implementation` 是已有 workstation 研究路径，`p6 static
direct current implementation` 是 current-source direct authority；“可复用”不等于
已经具备 p6 no-global-factor 资格。

| component | p2 iterative current implementation | p6 static direct current implementation | can_reuse_directly | required adapter/change | risk | unit/MPI/PDE test | future hp impact |
|---|---|---|---|---|---|---|---|
| Stage4 system construction | `run_workstation_iterative.py::run` 调 `stage4_runtime.assemble_target_stage4_system(degree=2)`；该函数建 mesh/V/MPC/forms 后立即调用 `solve_stage4_dtn_port_total_field`。 | `run_task033_full3d_watchdog.py` worker 进入 `common_3d_case_flow.run_prepared_3d_case_flow`，再调 `solve_stage4_dtn_port_total_field`；`assembly_time_static_condensed` 先形成 `A_aug/b_aug`。 | mesh、forms、MPC 和 DtN 配置可复用；两个现有入口都不能原样作为 no-global-factor 入口。 | A：在 `dtn_port_3d.py::_solve_augmented_system` 调用边界接入一个 default-off、collective 的单一 callable linear-solver port；`None` 保持 ordinary direct body 不变。 | 入口名 `assemble` 会掩盖已发生的 direct factor；MPI ranks 若 hook presence 不一致会破坏 collective。 | unit：hook 未启用仍走 direct；MPI2/4：presence 一致且无 global factor；p6/h10 PDE：首次 no-global-factor authority。 | hook 位于已准备的系统与恢复之间，不绑定 p/h 固定行数；hp 只在后续明确授权时扩展。 |
| F/C/D/H/f/g block identity | direct 系统返回后才由 `extract_petsc_condensed_blocks` 切块；`n_fe/n_aux` 来自 `RuntimeStage4System`。 | direct path 直接在 `A_aug/b_aug` 上求解；assembly-time p6 的 active trace + auxiliary rows 是现有身份，但没有作为 F1 block port 的独立入口。 | `condensed_dtn.py::extract_petsc_condensed_blocks` 可直接复用；不要在 runner 重写切块。 | port 接收已装配 `A_aug/b_aug`，按现有 `n_fe/n_aux` 形成 F、C、D、H、f、g，并保留 PETSc ownership；只增加一致性/生命周期所需的最小传递。 | FE trace 与 auxiliary offset、分布式 submatrix ownership 错位会使 action 和恢复同时错误。 | tiny p2：block identity；MPI2/4：每块尺寸/ownership；p6/h10 PDE：rows 与 direct authority 对齐。 | 不写死 51,192/80；未来 hp 只提供运行时 block sizes。 |
| exact condensed action/RHS | `condensed_rhs`、`create_matrix_free_condensed_operator` 已实现 `F-CH^{-1}D` 和 `f-CH^{-1}g`，随后由 FGMRES 使用；当前仍先承受 direct construction。 | p6 direct 不需要该 shell action，`_solve_augmented_system` 对已选 `solve_A/solve_b` 做 global direct KSP setup/solve。 | `SmallDenseInverse`、exact shell action、`condensed_rhs` 可直接复用。 | port 内以现有 assembled F 为 fine operator，调用既有 shell/RHS；不引入 F5 matrix-free kernel，也不复制 algebra。 | H 的精确小块求解、collective shell apply 和 PETSc object lifetime 必须一致。 | tiny p2：shell vs explicit；MPI2/4：action identity；p6/h10 PDE：condensed true residual。 | assembled-F 公式保持不变；hp kernel/PC 不在本 F1-0 设计中。 |
| auxiliary recovery | `recover_petsc_auxiliary` 从 condensed u 解恢复 a，`_combined_augmented_vector` 再拼回 augmented vector。 | `_gather_auxiliary_values` 从 `x_aug` 收集 a，随后 `_port_power_metrics` 使用其 outgoing amplitudes。 | `condensed_dtn.py::recover_petsc_auxiliary` 与 dtn_port 现有 gather/port path 可复用。 | port 返回完整 ownership 正确的 `x_aug`；外围继续走已有 a 收集和 channel/RTA 输入，不在 runner 复制恢复。 | `n_fe` 前缀、aux offset、PETSc ownership 或 cleanup 错误会污染 R/T/A。 | unit：exact H recovery；MPI2/4：aux ownership/gather；p6/h10 PDE：12 channel amplitudes。 | 只依赖 runtime n_aux；未来 hp 的 mode count 仍由 DtN config 冻结。 |
| active-trace/full-FE recovery | workstation path 用 `_assign_fe_solution_from_augmented`；`_official_rta` 由 augmented solution 重新生成 FE field。 | assembly-time p6 用既有 assembly-time recovery；其余 direct static path 由 `recover_full_solution`/`_assign_fe_solution_from_augmented` 恢复，最终调用 hcurl condensation recovery。 | `dtn_port_3d.py` 与 `hcurl_assembly_time_condensation.py` 现有 recovery 可直接复用；禁止 runner 复制。 | port 只交付 x/a 与 solver telemetry；恢复、ownership、destroy 顺序留在现有 dtn 生命周期。 | 过早 destroy F/C/D/H、returned x 或 recovery map 会使 full FE vector 和 residual失效。 | unit：recovered vector identity；MPI2/4：ownership/cleanup；p6/h10 PDE：full FE SHA 与 field recovery。 | `TraceConstraintMap`/cell recovery map 继续承担 hp 差异，不在接口中写死 p2/p6。 |
| reported/condensed/full-augmented/full-FE residual | monitor/report KSP residual；`_linear_residual(operator, rhs, solution)` 和 `_full_augmented_residual` 已在 workstation path；full FE/RTA 由后处理继续判定。 | `_solve_augmented_system` 给 direct KSP telemetry；`_assembly_time_full_operator_residual` 或现有 full active residual 在恢复后计算，最终由 common flow 汇总。 | dtn_port/hcurl 现有 explicit residual 路径直接复用；不能只复用 reported KSP residual。 | port 返回 reported + condensed true residual所需 telemetry；外围继续计算 full augmented/full FE residual，并以同一 recovery/operator 作为 Gate。 | 未收敛或 full residual 未通过时若仍进入 official RTA，会把诊断数值写成结果。 | tiny：四类 residual identity；MPI2/4：collective norms；p6/h10 PDE：full true residual Gate。 | residual 定义保持 exact operator；hp 只改变离散，不降低 Gate。 |
| official RTA fail-closed | `run_workstation_iterative.py` 仅在 `full_residual <= rta_threshold` 后调用 `_official_rta`；否则不写 official result。 | common flow 在 solver/energy balance 与 volume absorption 后写 official RTA；dtn port 先产出 port metrics。 | 现有 dtn/common flow official RTA、volume absorption、12-channel gates 可直接复用。 | solver port 失败/未收敛/full residual 未通过时只返回 not_run/diagnostic state；不在 port 内重算 RTA，不 fallback direct。 | stale R/T/A 或部分 channel 输出被误标 pass 是唯一需要保护的物理边界。 | unit：未收敛 => official RTA `not_run`；MPI2/4：一致状态；p6/h10 PDE：R/T/A 与 energy closure。 | official observable 和 fail-closed 语义不随 hp 变化。 |
| solver/factor lifecycle | direct augmented KSP 后释放 A，再构造 condensed shell、FGMRES、PC；已有 compact lifecycle 记录对象账本。 | `_solve_augmented_system` 内 `KSPSetUp/KSPSolve` 建立 global direct factor；随后 dtn recovery/residual/port 使用返回对象。 | cleanup/telemetry 语义可复用；global direct factor 生命周期不能复用到 F1。 | A port 自己拥有 FGMRES/shell/PC 与局部对象，返回现有 x/solver telemetry；ordinary direct `None` 路径逐字保持，不加自动 fallback。 | 名称或默认 options 误导性地创建 MUMPS/global factor；factor、shell、KSP 的 destroy 顺序错误。 | unit：no-global-factor inventory；MPI2/4：factor absent/cleanup；p6/h10 PDE：simultaneous memory。 | 只允许后续明确授权的 local/coarse factor；不为 hp 预留 registry。 |
| external telemetry | workstation progress/checkpoints 记录 KSP/PC 过程和本地 memory fields，但不是 p6 authority。 | Task033/Task035c watchdog、progress events、memory timeline 记录 process-tree RSS/PSS/USS/swap 与 TERM/grace/KILL 语义。 | 既有 watchdog/telemetry 直接复用；不新增 exporter、scheduler 或 evidence framework。 | 只新增 iterative/direct lane 的最小 stage labels 和 source identity；direct cap 与 iterative cap 分开，swap 必须仍为 0。 | 将单 rank或累计对象体积误称 simultaneous peak；把 direct 32/48 GiB 与 iterative 10/14 GiB混用。 | unit：record field contract；MPI2/4：rank aggregation；p6/h10 PDE：external simultaneous telemetry。 | hp 只增加规模，不改变 telemetry 口径。 |

## 现状 call graph 与监督发现

当前 p2 workstation 研究链为：

```text
run_workstation_iterative.run
  -> stage4_runtime.assemble_target_stage4_system
  -> dtn_port_3d.solve_stage4_dtn_port_total_field
  -> dtn_port_3d._solve_augmented_system  [global direct factor first]
  -> condensed_dtn.extract_petsc_condensed_blocks
  -> condensed_dtn.condensed_rhs / create_matrix_free_condensed_operator
  -> outer FGMRES
  -> recover_petsc_auxiliary / _full_augmented_residual / _official_rta
```

因此 `run_workstation_iterative.py` 的 condensed algebra/FGMRES 经验可复用，
但现有整条链不能证明 F1 no-global-factor。

当前 p6 static direct authority 链为：

```text
run_task033_full3d_watchdog worker
  -> common_3d_case_flow.run_prepared_3d_case_flow
  -> dtn_port_3d.solve_stage4_dtn_port_total_field
  -> dtn_port_3d._solve_augmented_system  [PETSc direct KSP setup/solve]
  -> assembly-time/cell static recovery
  -> _assembly_time_full_operator_residual or existing full residual
  -> _gather_auxiliary_values / _port_power_metrics
  -> common flow official RTA + volume absorption
```

`src/solvers/stage4_runtime.py::assemble_target_stage4_system` 名称虽称
assemble，内部实际调用 `solve_stage4_dtn_port_total_field`，已经先走
`_solve_augmented_system`/global direct factor，不能原样作为 F1 no-global-factor
入口。p6 cell-interior recovery、full operator residual、DtN/RTA 必须继续复用
`dtn_port_3d.py` 与 `hcurl_assembly_time_condensation.py`；不要在 runner 复制。

## A/B 架构结论与最小后续白名单

| 路线 | 结论 |
|---|---|
| A：`_solve_augmented_system` 调用边界的单一 linear-solver port | **首选；当前未发现硬 blocker。** 已准备的 `A_aug/b_aug`、block ownership、u/a 合并、现有 recovery、full residual 与 official RTA 都可以由 port 返回/外围继续持有；default-off 且各 rank hook presence 一致即可保留 ordinary direct 语义。 |
| B：整体拆分约 1300 行 prepare/finalize | 暂不采用。当前证据没有证明 A 无法处理对象 ownership、static recovery、full residual 或 official RTA fail-closed；整体拆分会扩大生命周期和回归面。 |

后续首个代码 slice 的建议白名单为：

| 文件 | 最小职责 | 预计行数 |
|---|---|---:|
| `src/solvers/dtn_port_3d.py` | default-off solver-port contract、direct default 不变、direct setup 未调用、snapshot/lifecycle 交接 | 约 45–65 |
| `src/solvers/common_3d_case_flow.py` | 只线程一个可选 port；保持 collective hook presence、ordinary flow 与未收敛 official RTA `not_run` | 约 20–35 |
| `src/solvers/solve_maxwell_3d_stage_4b_block_grating.py` | 仅绑定已授权 F1 candidate 的 port；不复制 Task033 或 workstation runner | 约 15–20 |
| 一个 focused test module | 只覆盖 hook contract、direct setup 未调用、snapshot/lifecycle、未收敛 RTA `not_run`；不混入 block/action/recovery | 约 60–100 |

`src/solvers/stage4_runtime.py`、`benchmarks/run_workstation_iterative.py` 和
`benchmarks/run_task033_full3d_watchdog.py` 在首 slice 保持只读历史证据；实际
condensed algebra 与 thin Task37 runner 后移到 F1b，不进入首 slice。production
预算为约 80–120 行、tests 约 60–100 行；若超过预算先拆片，不转向 B，也不新增
registry/plugin/framework。本 F1-0 轮只修改本表，不写上述代码或测试。

## 行与对象的语义

Case096 direct static authority 的当前参考身份如下；这些是运行时必须重新
记录的字段，不是用历史记录替代 current-source evidence：

| 对象 | Case096 p6/h10 参考值 | 含义 |
|---|---:|---|
| active exact-sequence FE DoFs | 173802 | 消去前的实际 conforming Nédélec FE 空间 |
| storage carrier FE DoFs | 173802 | DOLFINx carrier space；本固定 p/h case 没有额外 variable-p storage-only rows |
| full trace rows | 60402 | 静态凝聚前的全 trace 行 |
| independent active trace rows | 51192 | 消除 cell interior 与 Floquet slave 后的 FE trace 行 |
| auxiliary rows | 80 | DtN/Floquet auxiliary rows |
| augmented solved rows | 51272 | independent trace + auxiliary rows，实际 direct matrix rows |
| condensed matrix NNZ | 41989040 | Case096 full static direct reference |
| factor NNZ | 212343992 | Case096 MUMPS factor reference |

F0 还要分别保存 active trace vector 的 canonical identity 与 recovered full
FE vector 的 canonical identity。两者不是同一个向量，不能用历史 direct
vector 或 R/T/A 数值替代。

## solver/PC 与内存边界

- Direct F0 watchdog 使用 Task033/Task035c 已资格化语义：poll=0.25 s、
  warning=32 GiB、termination=48 GiB、timeout=7200 s、swap 必须为 0，
  终止为完整 process group 的 TERM -> 5 s grace -> KILL。
- Task37 第 8 节 iterative candidate 的 warning=10 GiB 与
  controlled termination=14 GiB 只适用于后续 iterative candidates；本表
  不把它们提升为 direct cap，也不提高它们。
- 迭代成功必须同时回答三个问题：矩阵作用是否等于目标 condensed
  operator、preconditioner 是否在 FGMRES 允许的语义内、恢复后的完整 FE
  场是否通过 explicit true residual 与 12 通道物理 Gate。
- ordinary defaults 保持现状；strong/exact trace、Hybrid-P/low-rank
  direct Hybrid 和 Task036 capacity/POD 路径仍是 research-only、controlled
  negative 或 do-not-merge 边界。

## 当前结论

F1a contract/helper 已完成；runtime port wiring、no-global-factor PDE 与 F1 其余内容待 F1b。
