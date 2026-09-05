# Review V19 R4：PML 双向扫描真实结构收口

## 当前结论

本轮 R0 的最终结论是 'REAL_ANCHOR_REFERENCE_RESOURCE_BLOCKED'。PML 是放在局部
子域边界外的人工吸收层，用来让局部逆更像开放边界；local inverse 则近似局部
物理问题的作用。它的代价是额外网格、系数和编译工作集，可能在全局求解开始前
就达到内存上限。候选的 p6/h10 PML 双向扫描在真实 local mesh 完成后进入
FFCx C 编译阶段并触发保守资源停止；form 构建已发生，但编译完成、AIJ、MUMPS
symbolic、numeric 或 solve 均未完成。它不是 PML 数值失效，也不是完整物理求解
通过。

原始 parent record 保留的分类是
'R0_P6_SYMBOLIC_RESOURCE_CONTROLLED_STOP'；独立 checker 的最终保留副本为
'checker_timeline_checked.json'，其分类是 'R0_P6_SYMBOLIC_EVIDENCE_FAIL'。后一个
FAIL 只表示 worker 终止后编译器晚写入的 .o 不在受控 timeline 内，导致当前 cache
尾部和完整同期峰值无法资格化；它没有推翻 timeline 中已经观测到的资源停止。

## 身份与范围

| 项目 | authority |
|---|---|
| measurement baseline HEAD SHA | afa0aa066de67557cddaa80901c3cf7710833abe；measurement 时 worktree_dirty=true |
| branch | codex/20260820-task38-extra-full3d-iterative-0p7nm |
| input | input/templates/full3d_iterative_example.dat，SHA 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41 |
| physical model SHA | 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f |
| MPI/ABI | MPI1，Open MPI 4.1.6，PETSc complex128/int32，qualified activation=1，threads=1 |
| R0 profile | p6/h10，4 个 z quartile core，1 个 h10-cell overlap，2 个人工 PML layer |

R0 只验证结构、映射和资源可行性；它没有启动 R1 的原始 p6/h10 零初值外层
FGMRES。因此没有产生可用于 official E/H、near-field、R/T/A 或 recovery 的场。

## 已测的 p2 结构锚点

这是 host-qualified 的真实 p2/MPI1 focused fixture，不是完整 p6 PDE qualification。
同一 PML 局部 Maxwell action、PML 映射、PoU 与 MUMPS 小矩阵生命周期均通过：

| 事实 | measured value |
|---|---:|
| stretch-one local Maxwell relative | 1.2094044854723367e-15 |
| stretch-one original Maxwell relative | 1.2203238080131893e-15 |
| local action relative | 1.440782276734707e-15 |
| repeated local action relative | 0.0 |
| dual/primal map relative | 0.0 |
| Hermitian pairing relative | 0.0 |
| PoU max error | 0.0 |
| MUMPS explicit residual relative | 1.7250761895437276e-13 |
| MUMPS INFOG(16) | 50 |
| post-analysis RSS | 180830208 B |
| p2 predicted peak | 230830208 B |
| owned slave count / max | 758 / 0.0 |

这些值绑定于旧 trace record
benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/v19_r0_p6_trace_inventory_v2/afa0aa066de67557cddaa80901c3cf7710833abe/mpi1/raw/p6_trace_inventory.json
（SHA d987b40c45569c6b498dbec13fe75c13399e461568fff6bf3c01fdd792bd5d07），并标注为
test-derived measured fixture；它们不替代 p6/h10 的 full-physics evidence。

## p6/h10 真实结构

此前保留的 p6 inventory 给出 173802 个全局行、14 个 z layer、252 个 cell、4 个
core，三个内部 interface 的实际 z 坐标为 20、60、90 nm。interface raw storage
trace rows 为 1350、1350、1350；剔除 MPC slave storage 后分别为 1296、1296、
1296；MPC row replacement 为 9210。global AIJ support-union count 为 190855440；
它不是已装配 global AIJ 的 NNZ，matrix_assembled=false。
slab1 的 structural pair 数为 136361232。PoU 最大误差为 0，global transfer
matrix 和 numeric allgather 均为 false。

四个 core 的结构摘要如下：

| subdomain | storage rows | independent rows | physical rows | PML rows | cells | structural pairs |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 75258 | 71280 | 47952 | 23328 | 108 | 81867024 |
| 1 | 124530 | 117936 | 71280 | 46656 | 180 | 136361232 |
| 2 | 112212 | 106272 | 59616 | 46656 | 162 | 122737680 |
| 3 | 87576 | 82944 | 59616 | 23328 | 126 | 95490576 |

这就是本候选的真实结构：global physical action 仍为 split volume Maxwell
operator 加 streaming DtN；PML 只存在于 local subdomain 的辅助边界延拓；双向
sweep 顺序固定为 0,1,2,3,3,2,1,0。global matrix、numeric allgather 和旧
transmission 项均没有被作为已测完成项声称。

## p6 symbolic v4 的实际停止

worker 已完成 local mesh，并在 FFCx C 编译阶段被停止；没有写出
local_form_compiled、local_aij_assembled 或 symbolic_complete。因此：

- local PML form 的构建已发生，但 C 编译完成未发生；
- local AIJ 未完成；
- MUMPS INFOG/RINFOG 未产生；
- MUMPS symbolic、numeric、solve 均未运行；
- 没有 R1/R2/R3 外层 residual；
- 没有 official complex field 或 output packet。

preflight 的保守计算为：

launch_cap = min(12000000000, MemAvailable - max(4GiB, 0.1*MemTotal))

实际输入为 MemAvailable 12880556032 B、MemTotal 14654980096 B、reserve
4294967296 B，得到 launch cap 8585588736 B。该值低于 Review 的 12 GB hard
limit，是本机可用内存扣除保守 reserve 后的受控 launch cap，不是把 hard limit
放宽。已知 slab1 preassembly 小计为 5999894208 B，但它明确不含 PETSc row
pointer、allocator overhead 和 MUMPS workspace，不能把小计当成完整预测。

| resource fact | measured / derived |
|---|---:|
| watchdog / launch cap | 8585588736 B |
| sampled process-tree peak RSS | 8609562624 B |
| hard limit | 12000000000 B；已观察样本未触及，尾段未知 |
| warning | 10000000000 B；已观察样本未触及，尾段未知 |
| sampled peak PSS | 8580238336 B |
| max swap | 0 B |
| samples | 3111 parent / 3110 worker |
| all contemporaneous status readable | true |
| derived observation span | 220.865540352 s |

采样峰值的成员细分为 Python 3281952768 B、cc1 5275271168 B、parent
34979840 B、mpiexec 14524416 B、gcc driver 2834432 B，合计 8609562624 B。
因此可以确定本次本机资源 cap 被触发，不能把它写成 MUMPS factor 超过 12 GB；
MUMPS factor 根本尚未开始。

## 生命周期与 cache 边界

parent marker 顺序为 paths_ready → abi_ready → worker_complete →
record_written → release_complete。worker 已记录到 slab1_local_mesh_built；
worker 返回 -9，stop reason 为 process_tree_rss_watchdog，signals 为
SIGTERM/SIGKILL，process group gone 为 true，swap 为 0。事后复核时相关
parent/worker/mpiexec/compiler 进程均已消失，但不能把事后清场冒充完整的同期
closeout。

记录的 cache 是空 cache 到一个 C artifact：

| snapshot | count | manifest SHA |
|---|---:|---|
| initial | 0 | ac581a250c845909e3a3fd625f71908caab372c69c8e6b120652ac8041c232ce |
| recorded after worker | 1 | bb7793dcc6a631b4ab27cb90dd67c53f77ef2795d6d4c0c61dc19501705d1599 |
| current after late compiler tail | 2 | ed88e7fad0d365a080e8dee0a8e3a04980456d89590e0af2bb7c337778c8bf7a |

当前 C 文件为 libffcx_forms_f0b8ffc91aaf96e52be1bc8da46c28e853b01c20.c，
409357759 bytes，SHA
91e0f5257e0655e208524b3d808744823c4f8606498b28d949c5478b30d3b50c；晚到的
.o 为 106037984 bytes，SHA
7e658e39cd9fd989918dedd93daf5b218717dfa0edf3b6f0cf5861d947b06845。该 .o 的
mtime/ctime 比 timeline 最后样本晚约 45.768436 s。故 full_peak 必须写
unknown，sampled_peak 只能写 8609562624 B；checker 的 evidence-valid 为
false 是正确的保守结论。

## 阶段结论

| 阶段 | 状态 | 具体含义 |
|---|---|---|
| R0 p2 structural fixture | measured PASS | 真实小矩阵/映射/PoU/MUMPS 结构锚点 |
| R0 p6 trace inventory | measured PASS | 真实 p6 分区、trace 与结构计数 |
| R0 p6 symbolic v4 | measured resource controlled stop | local mesh 完成后进入 FFCx C 编译并触发本机 cap |
| R1 p6/h10 zero-start PML double sweep | not_run | 没有进入 full outer solve |
| R2 low-memory model replacement | not_run | R0 尚未完成，未触发条件 |
| R3 nonseparable notch recipe | not_run | 未触发条件 |
| official E/H, near-field, R/T/A, recovery | not_run | 没有合格 full-physics field |

因此没有 numerical residual、local inverse accuracy、sweep contraction 或
official energy closure 可报告。R0 小型 p2 PASS 只能说明实现的基础映射与
MUMPS 生命周期在小问题上可工作；p6/h10 的主要 blocker 是真实 local form/
AIJ 的过程树内存，而不是已测出的 PML 数值错误。

## 证据索引

| 文件 | SHA256 |
|---|---|
| parent_record.json | db5b0887256d07e88715019180d120175991ed0e3fcc1ba42c1b873c35dd5966 |
| raw/p6_symbolic_preflight.json | 4f8e4a0d10722c9532a523773d7203409a4a04885b073377f1180eb0d7b9f054 |
| parent_process.jsonl | a2a71b624a47974a216cac4b47f16528c7c8d42733683931f361715739baab1f |
| checker_timeline_checked.json | be3eca37d211dd1385a5d713784fcdb272cb1427e3a8eecce9ad66f7e732a9eb |
| raw/p6_trace_inventory.json | d987b40c45569c6b498dbec13fe75c13399e461568fff6bf3c01fdd792bd5d07 |

所有 V16、V17、V18 旧 negative、V17 Oracle A/B 相关历史证据以及本 V19 v1/v2/v3
R0 证据均保留，未删除、覆盖或重分类。由于 R0 受控阻塞，Review V19 的 R1、
R2、R3 和 official physics 保持 not_run。
