# 工作站波长续试 Response V1

状态：**PREPARATION_IN_PROGRESS**。本文件只对应新增的固定几何波长续试，不覆盖旧 cloud PSTDDM pilot 的 PASS_WITH_QUALIFICATIONS 结果。

| 项目 | 当前准备决定 | 证据/边界 |
|---|---|---|
| 执行顺序 | 13.5 nm；通过且共享预算允许后 5 nm；再条件性评估 0.7 nm | 用户本轮覆盖旧 cloud-only/旧顺序；远端写入和正式运行仍需主控现场准入 |
| 几何 | 50×50×140 nm 单胞；居中有限 17×20×120 nm Si 块；Si 基底 10 nm | x/y 均有有限材料边界，双 Floquet 保留 |
| 13.5 nm 网格 | p2、4×4×16=256 hex；z 16 层可切 N=2/4/8 | 同离散算法与资源试验，不是物理精度网格 |
| DtN | 每波长根据当前材料和角度生成传播阶，再加 m/n 各一阶矩形包络 | 旧 836 模式不可复用；冻结前需实际 inventory |
| 材料 | 优先从已归档 CXRO/Henke Si 原始表按目标能量取 bracket，保留来源、符号和 SHA | 不跨波长复用单个 n；材料计算/数据核验不等于样品测量 |
| 局部 PML | 每侧 10 nm、两层、1.25 grading、固定二次 stretch 公式 | 只用于局部问题；原全局 Floquet–DtN A 不变 |
| 数值门 | direct residual≤1e-10；candidate residual≤1e-8；E/H误差≤1e-4/1e-3；已资格化总功率绝对差≤1e-4 | 未资格后处理保留 diagnostic，并说明资格缺口；不跳过已资格门 |
| 预算 | 全波长共享最多10次/6小时；单次30分钟；MPI1/单线程 | 8e9 B 任务树 RSS 与动态 host reserve 取较严者，cgroup swap=0 |

执行者不 commit/push；主控在检查并冻结本轮 source 后集中提交与推送。

本地实现已交主控冻结，相关测试尚待在工作站执行，当前未启动正式 PDE。主控已通过 SSH 在用户授权目录内登记独立执行 worktree，并完成 imports-only ABI 检查；这不是 FE 或 PDE 通过。

执行源码目录为 `/home/fenics/Projects/laptop_share/benchmarks/artifacts/pstddm_workstation/source`，运行和准备证据位于其上级任务目录。原父目录的 Task41 分支及邻项目未切换、停止或修改。复用现有 native Linux runtime，PETSc 3.25.6 complex128/int32、DOLFINx/Basix/FFCx 0.10.0、MPI1/math1；未安装新环境。

实际 ABI 收据为 `benchmarks/artifacts/pstddm_workstation/preparation/abi_imports_20261114.json`，SHA256=`280dbdf428d1e85d2ddf792f2f76afbfec7a88e73e21d2d616d4f2c54277b2b9`。预检服务已经退出；正式服务使用独立新 cgroup。任务限制为 MemoryMax=8,000,000,000 B、MemorySwapMax=0、CPUQuota=100%、Nice=15、IOWeight=10。宿主已有约1.19GB swap，不计作本任务新增 swap；本任务必须以自身 cgroup/进程树记录验证零 swap。

2026-11-14 10:02:31 UTC 只读样本：MemAvailable=503,245,275,136 B，磁盘 available=427,584,544,768 B，邻作业 PID2651881 正常运行。本次采用至少400GiB宿主内存保留线及400,000,000,000 B磁盘底线，正式启动前仍需读实时值。该样本不是正式运行峰值或永久容量保证。
