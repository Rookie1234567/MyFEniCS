# Task038-extra Review V19 response

## 结论先行

本轮最终结论为 REAL_ANCHOR_REFERENCE_RESOURCE_BLOCKED。PML 是局部边界外的人工
吸收层，用于模拟波离开局部子域；local inverse 则近似局部物理问题的作用。
它会增加局部网格、系数和编译工作集，因此可能在全局求解前先消耗大量内存。
R0 在真实 p6/h10 local mesh 完成后的 FFCx C 编译阶段触发了本机保守
process-tree RSS cap；form 构建已发生，但编译完成、AIJ assembly、MUMPS symbolic、
numeric、solve 或外层 Krylov 均未到达。因此这不是一个 PML 数值失败，也不是
full physical solve 通过。

当前 PML/core/dat 只构成 research-only 的 R0 原型：R1 adapter、可资格化的
production local inverse 和完整 recovery 尚未实现，不建议将其作为 production
默认路径合入。局部 assembled/LU 的进一步 refinement 扩展风险也没有资格化；
本轮只能把它作为结构与资源研究证据。

R0 parent 的原始分类永久保留为 R0_P6_SYMBOLIC_RESOURCE_CONTROLLED_STOP。独立
checker 的保留输出为 checker_timeline_checked.json，其 status=FAIL、
evidence_valid=false，原因仅是终止后晚写入的 object file 未被 timeline 观察到，
使 cache tail 与完整同期峰值不能闭合。R0 已观察到的 RSS watchdog stop 仍是真实、
可复核的资源事件。v1/v2/v3/v4 以及所有 V16–V18 旧 evidence 均未删除、覆盖或
重分类。

## 1. 身份、历史和首场问题

| 项目 | 本轮 authority |
|---|---|
| branch | codex/20260820-task38-extra-full3d-iterative-0p7nm |
| measurement baseline HEAD SHA | afa0aa066de67557cddaa80901c3cf7710833abe |
| measurement worktree | dirty=true；该 SHA 是当时 Git HEAD，不冒充包含 dirty 实现的 commit |
| input | /home/shenjh/Projects/MyFEniCSx_task37_extra/input/templates/full3d_iterative_example.dat |
| input SHA | 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41 |
| physical model SHA | 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f |
| ABI | Open MPI 4.1.6；PETSc complex128/int32；qualified activation=1；threads=1 |
| R0 p6 root | .../v19_r0_p6_mumps_symbolic_v4/afa0aa066de67557cddaa80901c3cf7710833abe/mpi1 |

Review V19 要求在 R0 后把第一场外层求解直接放到原始 p6/h10、1°、真实 RHS、
零初值上。本轮没有达到这个阶段：p6 R0 是结构与资源预检，R1 的 zero-start
PML double sweep 从未启动。此前的真实 p2/MPI1 test351 是小型局部结构和
MUMPS fixture，不是 full PDE，也不是“第一场” p6/h10 外层解。

## 2. R0 实际验证的对象

候选保留 exact split physical action：体内 curl-curl 减 k0² mass，加 streaming
DtN；PML 只用于局部子域的人工边界延拓和局部逆，不能替代全局物理算子。四个
z quartile core 使用一个 h10-cell overlap，两个人工 PML layers；三个内部
interface 的实际网格平面为 20、60、90 nm。双向扫描顺序固定为
0,1,2,3,3,2,1,0，global transfer matrix 和 numeric allgather 都为 false。

此前 p6 inventory 的 measured/derived structural facts 为：

| 量 | 值 |
|---|---:|
| global rows | 173802 |
| z layers / cells | 14 / 252 |
| core row counts | 38304, 50622, 38304, 50622 |
| interface raw trace rows | 1350, 1350, 1350 |
| interface non-slave rows | 1296, 1296, 1296 |
| MPC row replacements | 9210 |
| global AIJ support-union count（非已装配 NNZ） | 190855440 |
| slab1 structural pairs | 136361232 |
| PoU maximum error | 0 |
| PML layer count | 2 |

四个 local subdomain 的 storage rows、independent rows、physical rows、PML rows
和结构 pair 分别为：

| subdomain | storage | independent | physical | PML | pairs |
|---:|---:|---:|---:|---:|---:|
| 0 | 75258 | 71280 | 47952 | 23328 | 81867024 |
| 1 | 124530 | 117936 | 71280 | 46656 | 136361232 |
| 2 | 112212 | 106272 | 59616 | 46656 | 122737680 |
| 3 | 87576 | 82944 | 59616 | 23328 | 95490576 |

这些数字说明“要构造什么”，不等于已完成的 local matrix 或 MUMPS factor
内存测量。R0 worker 完成 local mesh 后进入 FFCx C 编译，只到
slab1_local_mesh_built，没有 local_form_compiled、local_aij_assembled 或
symbolic_complete marker。

## 3. 小型 p2 真实结构锚点

真实 host-qualified p2/MPI1 focused fixture 用于检查映射和 MUMPS 生命周期，事实
如下；所有输入保持不变且 finite：

| 检查 | measured |
|---|---:|
| stretch=1 local Maxwell relative | 1.2094044854723367e-15 |
| stretch=1 original Maxwell relative | 1.2203238080131893e-15 |
| local action relative | 1.440782276734707e-15 |
| repeated action relative | 0 |
| dual/primal map relative | 0 |
| Hermitian map pairing relative | 0 |
| PoU error | 0 |
| MUMPS explicit residual relative | 1.7250761895437276e-13 |
| MUMPS INFOG(16) | 50 |
| post-analysis RSS | 180830208 B |
| predicted peak | 230830208 B |
| owned slave count/max | 758 / 0 |

这证明小型真实路径中 stretch-one 恢复、owner map、PoU 和同一 MUMPS factor 的
symbolic→numeric→solve 可以闭合；它不证明 p6/h10 local PML 的容量、外层
contraction 或 official physical output。

## 4. p6 资源与生命周期

preflight 固定使用：

launch_cap = min(12000000000, MemAvailable - max(4GiB, 0.1*MemTotal))

实际 MemAvailable 为 12880556032 B，MemTotal 为 14654980096 B，reserve 为
4294967296 B，故 launch cap 为 8585588736 B。已知 slab1 preassembly 小计为
5999894208 B；它明确不含 PETSc row-pointer、allocator overhead 和 MUMPS
workspace，所以不是完整 peak 预测。

| 资源事实 | 值/状态 |
|---|---:|
| launch/watchdog cap | 8585588736 B |
| sampled process-tree RSS peak | 8609562624 B |
| Review hard limit | 12000000000 B；已观察样本未触及，尾段未知 |
| warning | 10000000000 B；已观察样本未触及，尾段未知 |
| sampled peak PSS | 8580238336 B |
| swap | 0 B |
| process samples | parent 3111；worker 3110 |
| contemporaneous status readable | true |
| derived observation span | 220.865540352 s |

峰值成员包括 Python 3281952768 B、cc1 5275271168 B、parent 34979840 B、
mpiexec 14524416 B 和 gcc driver 2834432 B，合计 8609562624 B。worker 返回
-9，signals 为 SIGTERM/SIGKILL，stop reason 为 process_tree_rss_watchdog。
因此本次可判定“本机安全 cap 被触发”，不能判定“MUMPS factor 超过 12 GB”：
factor 尚未运行。

R0 parent markers 为 paths_ready → abi_ready → worker_complete →
record_written → release_complete。worker 有截至 slab1 local mesh 的 marker；
其 record 没有落盘。事后相关 process group 已消失，但这不等于完整同期
closeout 已被观察。

## 5. cache 和 checker 边界

记录的 cache snapshot 为：

| 时点 | artifact count | manifest SHA |
|---|---:|---|
| initial | 0 | ac581a250c845909e3a3fd625f71908caab372c69c8e6b120652ac8041c232ce |
| recorded after worker | 1 | bb7793dcc6a631b4ab27cb90dd67c53f77ef2795d6d4c0c61dc19501705d1599 |
| current after late compiler tail | 2 | ed88e7fad0d365a080e8dee0a8e3a04980456d89590e0af2bb7c337778c8bf7a |

current cache 中的 C artifact 为 409357759 bytes，SHA
91e0f5257e0655e208524b3d808744823c4f8606498b28d949c5478b30d3b50c；晚到的
106037984-byte object file SHA 为
7e658e39cd9fd989918dedd93daf5b218717dfa0edf3b6f0cf5861d947b06845。object
file 的 mtime/ctime 比 timeline 最后样本晚约 45.768436 s。因而 timeline 之后
的 RSS、PSS、swap 和 cache 状态都未知；timeline 内的 swap 只能报告为 0。故：

- sampled peak 8609562624 B 是已观察下界；
- full process-tree peak 必须记为 unknown；
- checker 不能把 current cache 当作 recorded-after cache；
- checker FAIL/evidence_valid=false 是证据闭合失败，不是把资源 stop
  重分类为数学失败。

R0 没有输出 MUMPS INFOG/RINFOG、AIJ、factor、solve、residual、rho 或 official
field。因而不能推导 R1 的数值表现。

## 6. R1、R2、R3 和 official physics

| 阶段 | 状态 | 原因 |
|---|---|---|
| R0 p2 implementation anchor | measured | 小型真实 action/map/PoU/MUMPS fixture |
| R0 p6 trace inventory | measured | p6 分区、trace、结构容量计数 |
| R0 p6 symbolic v4 | measured controlled stop / partial evidence | local PML mesh/form 阶段触发 cap |
| R1 p6/h10 zero-start PML double sweep | not_run | 没有进入 full outer solve |
| R2 low-memory replacement | not_run | 只有 R1 必要时才触发，本轮未触发 |
| R3 nonseparable notch recipe | not_run | R1/R2 条件未满足 |
| official E/H、near-field、R/T/A、recovery | not_run | 没有合格 full-physics field |

R2 的 low-memory replacement 不是本轮的隐含 fallback；R3 也没有被用来绕过
R0。没有任何新的 PC、Robin、Schwarz、sweep 变体或另一个 restart 被运行。

## 7. blocker 和边界

已消除的 blocker 是小型路径工程问题：p2 fixture 现在能在 qualified complex
PETSc/MUMPS 栈上证明局部映射和同一 factor 生命周期。尚未消除的 blocker 是
p6/h10 local PML form/AIJ 过程树的真实内存占用，以及因此无法得到的 local
inverse 精度和外层 residual。

本机 R0 使用的安全 cap 低于 Review 的 12 GB hard limit；这不是放宽 hard Gate。
由于 cache tail 在最后 timeline 后写入，不能用事后目录大小推断完整 peak。当前
结果也不说明 0.7 nm/2 TiB 可扩展，更不说明完整 official physics 已完成。

## 8. 证据路径

compact record：
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/pml_double_sweep_real_structure_v19.json

R0 outcome：
docs/task038_extra_full3d_iterative_0p7nm/outcomes/pml_double_sweep_real_structure_v19.md

主记录 SHA：

| evidence | SHA256 |
|---|---|
| parent_record.json | db5b0887256d07e88715019180d120175991ed0e3fcc1ba42c1b873c35dd5966 |
| p6_symbolic_preflight.json | 4f8e4a0d10722c9532a523773d7203409a4a04885b073377f1180eb0d7b9f054 |
| parent_process.jsonl | a2a71b624a47974a216cac4b47f16528c7c8d42733683931f361715739baab1f |
| retained checker_timeline_checked.json | be3eca37d211dd1385a5d713784fcdb272cb1427e3a8eecce9ad66f7e732a9eb |
| p6_trace_inventory.json | d987b40c45569c6b498dbec13fe75c13399e461568fff6bf3c01fdd792bd5d07 |

本 response 和 R4 outcome 只报告 measured、derived、controlled_stop、partial
evidence 和 not_run；没有把 small p2 test 或结构算术提升为 full PDE authority。
