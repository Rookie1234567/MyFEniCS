# Git、FE/ML和受控共享资源隔离

| 项目 | 实际核验 / 行为 | 证据与限制 |
|---|---|---|
| linked worktree | NN-Lab本身为canonical登记工作树；branch逐字符`task42_neural_coarse_inverse`；无嵌套clone | [初次准备](records/git_preparation.json)、[本轮核验](records/git_preparation_v2.json) |
| canonical / origin | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；`git@github-myfenics:Rookie1234567/MyFEniCS.git` | URL未改；只追加用户授权Task042 fetch refspec并设upstream，原Task39映射保留 |
| 历史 | base`ccd357885f7f9be84efe3be07868cc94f13d93fc`、初始任务锚点`f8c51c8e614edc806cf72120ac2cfd14ae8b62f7`均祖先 | 未reset/force/stash/clean/merge/rebase/amend；未改旧工作树HEAD/index/源码 |
| FE环境 | 新NN-Lab`.venv` Python3.12.3，NumPy1.26.4/SciPy1.11.4；complex128/int64、PETSc3.19.6、DOLFINx/Basix0.10.0、FFCx0.10.1.post0、UFL2025.2.1、MPC0.10.1、mpi4py3.1.5/OpenMPI4.1.6 | [原import资格](records/environment_fe.json)、[本轮数值记录](records/run_index_v2.json)；system-site包只读 |
| 原生prefix | `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/tmp/task39extra_v5_abi_restore_20260923/base`，PETSc为pord64-overlay | 只读复用已资格ABI；不修改旧venv/prefix/BLAS alternatives/CUDA/驱动 |
| 隔离ML | 独立无system-site`.venv-ml`，Torch2.7.1+cpu、NumPy1.26.4；训练显式float64、intra/inter-op1、DataLoader0 | [实际300epoch模型记录](records/training_complete_v2.json)；CPU-only，未向FE导入Torch |
| 缓存与结果 | results/task042、benchmarks/artifacts/task042、tmp/task042内独立TMP/JIT/bytecode/Torch/HF/Matplotlib/PyVista/POOCH/XDG/pip等 | activation逐项realpath核验，src从NN-Lab导入，无旧大结果/factor/cache复制 |
| 资源强制范围 | launcher、worker、compiler/JIT及全部后代同时RSS采样和专用subreaper清理，RSS16GiB/12GiB、own swap0 | 无可写独立cgroup委派；0.5s采样停止是实际实现，不冒充内核cgroup连续硬上限 |
| 保护邻任务 | 不发邻信号、不改其亲和性/优先级/监督器/锁，Task042自身nice10/idle I/O | 所有负载顺序、own nonblocking flock；没有后台自动等待/无限轮询 |

## Git现场及非交互认证

初次NN-Lab宿主目录为空、非symlink、未登记，沙箱的空保护占位经只读现场核实后才登记。没有删除/覆盖未知内容，未另建独立clone。原origin.fetch仅映射Task39，标准upstream首次被拒绝；用户明确授权仅追加Task042映射，已保留原URL/refspec完成上游设置。初始远程实际为任务锚点，不是强行匹配旧SHA；本轮启动再次实读local/remote为`a76e0435a40139dd6d2a31f0726fb229c7adaff8`，没有新review或后续合同。

网络使用`GIT_TERMINAL_PROMPT=0`及SSH BatchMode，不输入/索取/回显secret；fetch仅Task042、无tags、禁用auto-maintenance/gc、不运行gc/prune/repack。只推送`HEAD:refs/heads/task42_neural_coarse_inverse`。最终交付完整HEAD以实际push后核验回报为准，不能拿文档HEAD替换表中各clean运行source。

## 现场选核和线程限制

每个新正式负载前保存两次短CPU样本、全拓扑、neighbor PID/start_ticks、worker/监督器/loader及线程亲和性、memory/cgroup/disk/GPU基线。本轮实际选CPU0；48逻辑核对应48物理核，两socket，无SMT同胞共享；CPU0不是永久保留核。原worker341839/start_ticks17197130在CPU24，监督器341799在CPU9、observer341987在CPU10；另CPU workers527820–527827为1–8，两GPU worker509439/509440及其parent亲和性25–32。宽亲和性的低CPU控制器完整记录，仅排除现场实际PSR，它们可迁移，因此不能保证零干扰。

MPI1，OMP/OpenBLAS/MKL/NumExpr/BLIS/VECLIB/GOTO等数学线程1；OMP_THREAD_LIMIT、编译MAKEFLAGS=-j1/CMAKE/MAX_JOBS/RAYON、VTK等亦1。每FE worker实际ctypes查询OpenBLAS库均threads1、affinity[0]、nice10；ML actual torch intra/inter1、Loader workers0、default dtype float64、device cpu/cuda_build null。`CUDA_VISIBLE_DEVICES=''`；两Quadro RTX8000持续100%邻训练，直接CPU，未等待GPU、安装CUDA或修改MPS/MIG/compute mode/功率/驱动/reset。

## 真实监督和内存余量

effective总内存2163100385280B，原reserve=max(128GiB,10%)为216310038528B，另加邻任务增长规划allowance137438953472B，再保留Task042 17179869184B预算。增长allowance是保护规划量，不是已预测邻任务未来峰；运行持续核查effective available，余量不足只停止Task042。每run基线原始数值、cgroup祖先memory.max/current/high/swap.max和最后快照hash见[运行账](records/run_index_v2.json)、[最后资源快照](records/shared_workstation_snapshot_v2.json)。没有修改共享父cgroup或邻组。

无委派cgroup权限，实际采用0.5s整树RSS/own swap/status采样和停止，包含专用监督root；5s低开销SharedHealth查PSI、磁盘>=50GiB、artifacts<=20GiB，以及固定邻PID身份/CPU时间及已存在<=64KiB阶段JSON。PSI some avg10>=1%或full>=0.1%连续3样本撤负载；任何监督失效/own swap/资源门停止本树并记录。没有PSS/smaps/numa_maps或邻巨大资源日志扫描。

启动前做有界监督验证：子进程另起session并分配180MiB，128MiB测试门触线时grandchild亦清理、无关sibling存活；仅对测试自身后代发信号。各正式阶段正常结束或实现失败后均descendants_cleared、own swap0。采样可漏过亚采样瞬时峰，不声称16GiB连续内核限制；实际观察峰远低于12GiB warning。Task042 stage/aux进程树同时RSS和包含共享库多进程计数，不是PSS；不同阶段峰不相加。

## 对已有程序的影响及结论边界

运行自己的健康记录中PSI平均压力未触持续停止条件，own swap0，磁盘/artifact余量合规；固定邻worker、supervisor与loader身份保留，CPU ticks持续推进。现有短阶段JSON的更新时间较旧，缺少相同阶段的实时可比吞吐/耗时，因此没有证据证明绝对零干扰或量化性能退化。不能把自然阶段变化判为干扰；本轮也没有观测到需要撤掉Task042的持续资源压力。

每个正式组件/训练/测试成本标`shared-workstation`。邻负载、缓存和完整p6/p4-only生命周期不同，性能Gate为`inconclusive`；数值残差仍可判定。新共享profile只落实[用户授权](shared_authorization_v2.md)，不修改Task39/其他合同，也不是F0正式review通过。原F0 WAITING记录在response_v1及无后缀JSON保留为历史；本轮按数值Gate实际停止。

数值与final FE/pure回归完成后，一次保守进程/线程审计未给出spare，未启动处理负载。只读1秒逐CPU计数与既有worker/宽监督器PSR核验显示CPU0 busy fraction0、26候选核心，随后仅用CPU0完成有界stdlib文档提取；不修改数值准入或邻亲和性。[该轻量审计](records/documentation_cpu_audit_v2.json)保留实际准入差异，不能宣称整机独占。


## V3 最新有限诊断（原V2正文保留）

V3资源准入/执行详见[运行账](records/run_index_v3.json)。明确纠正V2全CPU0概括：oracle实际33、F4-B0实际45，worker affinity/source_state一致；V3每个阶段实际核见账，不把旧核永久保留。无cgroup委派，整树RSS16GiB/warning12GiB、swap0、math1、own lock及只清理本树保持。宽休眠线程旧PSR误排全部核的问题仅V3用活动样本修正。全部shared-workstation，无可比邻性能记录，不能声称零干扰；未修改邻任务/锁/环境。
