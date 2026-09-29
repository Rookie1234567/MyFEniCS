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
