# 原生环境与隔离

本任务在工作站原生 Linux 的 `/home/fenics/Projects/NN-Lab-V2` 计算。新目录已登记为现场核对过的 bare canonical 库 `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` 的 linked worktree。未建立第二个 clone，未改变共享 origin、全局 Git 配置或其他工作树。分支 upstream 的 remote/merge 分别为 `origin` / `refs/heads/task42extra_feinn_5nm`；共享 fetch 映射未包含新支线，检查 tracking ref 时只使用命令级映射。

| 项目 | 隔离方式 | 观测/限制 |
|---|---|---|
| FE Python | 新 `.venv`，新 activation，既有合格 FE prefix 只读接线 | Python 3.12；PETSc complex128/int64；MPI1 |
| ML Python | 新 `.venv-ml`，不加载 DOLFINx/PETSc/MPI | Torch 2.7.1+cpu，FP64，intra/inter-op=1 |
| 既有安装 | 仅只读加载已安装库，不在旧 NN-Lab checkout/install/run | 独立解释器、源码首路径与写缓存均在新目录 |
| 线程/设备 | activation 与运行期核验 | 数学线程1；CPU-only；不改全机配置 |
| 轻测试 | 独立数值锁及完整子树 watchdog | 1个现场空闲物理核，hard 2 GiB，自身 swap=0 |
| 正式阶段 | 一个阶段一个新进程，锁和0.5 s同时 RSS 采样 | MPI1，warn12/hard16 GiB，自身 swap=0 |
| 系统/邻任务余量 | max(128 GiB,系统有效内存10%) +384 GiB 邻增长预留 +本任务预算 | 每次启动和运行期核验；不足只停止自身 |
| 已有三项目 | 只读 proc/stat/status、亲和性、固定资源合同 | 不读取 smaps/PSS，不发信号，不改环境、锁或 watchdog |
| cgroup | 读取自身层级限制，不修改共享 cgroup | 共享 current 仅诊断；新增负载权威为本任务同时整树 RSS |
| 输出 | `results/task42extra/`、`benchmarks/artifacts/task42extra/`、`tmp/task42extra/` | 大数据忽略，紧凑记录 hash 绑定 |

CPU12只是现场候选中的优先项，每个阶段重新核验。邻项目 Task39 已处于 solve、上限约1.3 TB；Task041固定49.566 GiB合同且已驻留约40 GiB；Metrology有两名 GPU worker。384 GiB 是保守规划预留，包含 Task39 剩余增长、Task041余量、Metrology额外128 GiB和其他控制16 GiB；不冒称已知其他任务未来的严格上界。

ABI 原始记录位于新目录 `tmp/task42extra/setup/{fe_abi,ml_abi}.json`；完整轻测试日志位于 `tmp/task42extra/checks/`。未安装系统包。scikit-sparse首次打包因缺少 Cython 失败，未改旧环境；改用系统已有 SuiteSparse 的薄 C ABI，并通过复数 SPD 与符号阻止 numeric 的轻测试。该因子明确是研究辅助 Gram 因子，不是 Maxwell 训练 fallback。


## 本轮实际核验与观测边界

| 对象 | 原始身份/实际记录 | 观测范围 |
| --- | --- | --- |
| native Linux | Ubuntu、Python3.12；48个physical CPU且本机未发现SMT；2163100385280 B物理RAM（约2014.54 GiB） | 不是笔记本/WSL；ABI原始记录hash在run manifest |
| canonical Git | 现场核对owner/path/commonGit/worktree登记；SSH origin身份与指定repo一致 | 本根linked worktree；无竞争clone/共享origin改写 |
| FE ABI | DOLFINx0.10.0、Basix0.10.0、PETSc complex128/int64、OpenMPI4.1.6/mpi4py3.1.5；MPC来自合格独立prefix（模块API未暴露版本） | 既有合格prefix只读加载；环境和cache独立 |
| ML ABI | Torch2.7.1+cpu、NumPy1.26.4、SciPy1.11.4；intra/inter1/BLAS1 | ML进程无FE/MPI库；CPU-only |
| 邻项目 | Task39 solve、Task041 MPI8、Metrology两个GPU worker | PID/starttime/affinity/线程/RSS只读低扰动；未接管或调整 |
| 资源准入 | max128GiB/10%系统余量+384GiB邻增长+本任务16GiB | 每个stage fresh核验；自身RSS/swap/PSI/disk由watchdog记录 |
| 实际阶段树峰 | 见resource_costs_v1.json每stage同时peak | 不加各阶段峰，不把payload当RSS |
| cgroup | 未取得独立内核memory.max委派 | 目标0.5swhole-tree采样；自身VmSwap0仅为样本观测 |
| 邻影响/性能 | inconclusive | 没有零干扰反事实；不宣称共享环境20%加速 |

所有正式stage的原生启动基线、PID/starttime、选核、系统余量与采样树记录均留在独立results/tmp，compact hash入口见[run index](records/run_index_v1.json)。旧raw通用watchdog的 `WSL-global diagnostic` 是继承的字段标签；本任务通过native核验，不以该标签冒充WSL环境。RSS采样和本任务swap、系统global swap分别报告。

没有读取或回显password/token/private key；SSH现有凭据可用，没有人工凭据步骤。未改变共享remote、全局Git配置、旧NN-Lab环境、邻项目亲和性/锁/watchdog或全机swap/BLAS/CUDA。最终Git clean和remote/upstream以交付报告为准。
