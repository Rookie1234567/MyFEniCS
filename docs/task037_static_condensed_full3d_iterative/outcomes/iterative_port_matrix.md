# Task37 Stage 0：iterative port matrix

## 目的与边界

本表把已经有证据的 direct/iterative 入口放在同一张地图上。静态凝聚的
直观含义是：先消去单元内部只在本单元使用的未知量，再求较小的界面系统，
最后恢复完整有限元场。它减少全局行数和矩阵非零元，但会增加局部消元、
界面稠密化和场恢复成本。迭代路径还必须避免把 direct factor 重新放回
内存，因此不能仅凭“行数变少”宣布成功。

本阶段只冻结继承关系与 F0 direct authority；不实现 operator、preconditioner
或 iterative candidate。

## 入口与能力矩阵

| 入口/证据 | 当前用途 | 可复用的边界 | 不能据此宣称 | 下一阶段必须补的 Gate |
|---|---|---|---|---|
| benchmarks/run_task033_full3d_watchdog.py + src/solvers/dtn_port_3d.py | Case096 p6/h10 Full3D direct；assembly_time_static_condensed | 几何、p6/h10、Floquet/DtN、静态凝聚恢复、true residual、R/T/A、12 通道与 process-tree telemetry | 不能把 direct factor 或 direct-only memory 变成 iterative 证据 | F0 current-source direct 一次性 authority |
| benchmarks/run_workstation_iterative.py + src/solvers/physical_slab_two_level.py | Task27/30 opt-in 右预条件 FGMRES；物理层与 75D Floquet coarse 研究 | FGMRES 选择、物理 slab 分块、owner-computes Schwarz、coarse 设计的研究经验 | 不能证明 p6/h10 Full3D condensed operator 已可迭代求解 | Task37 operator action、PC 线性/非线性审计、full explicit true residual |
| Task30 compact opt-in path | assembled-F retained、较低阶 workstation memory study | 右 FGMRES 与 fixed iteration budget 的历史语义 | 不能作为 p6/h10、MPI8 或 production default | 同一 p6/h10 source SHA 上的独立 candidate |
| benchmarks/run_task031_memory_forensics.py + src/solvers/mpc_form_action.py | Task31 public MPC form-action memory study | assembled-F-free 的 opt-in 形式作用、资源语义与 swap=0 记录 | 当前不是低层 element-kernel matrix-free，也没有 p6/h10 authority | 若采用，必须先证明 action 与直接 reduced operator 的等价性 |
| Task036 V8 Full3D repairs | 已资格化 direct correctness/telemetry/lifecycle | 复用现有 residual、recovery、R/T/A、watchdog 和 row semantics | strong/exact trace、Hybrid-P/low-rank direct Hybrid、capacity/POD/96-RHS 未生产资格化 | 不得绕过 Task036 blacklists |
| Task037 F1+ iterative candidate | 本阶段 not_run | 仅可从上面明确标注的接口组合，不新增 registry/framework | 不得提前实现或运行 F1--F6 | 由主对话框审查后逐阶段授权 |

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

## Stage 0 结论

目前只有入口地图和 Case100 F0 contract 被冻结。没有写入新的 solver、
operator、PC、runner framework、registry 或通用 telemetry/export 模块；
F1--F6 均未运行。
