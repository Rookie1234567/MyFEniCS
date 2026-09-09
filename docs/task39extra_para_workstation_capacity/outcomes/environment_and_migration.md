# 原生环境与迁移记录

| 项目 | measured 事实 / 执行决定 |
|---|---|
| 冻结 base / 任务提交 | `450255f4575792d052c1bac29837d39955ee1039` / `8d41877f9b233209b534b27648ecc657e40a1573`；祖先关系已核实 |
| 独立 canonical | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；从指定远端分支克隆；本地对象只读借用后 dissociate，无 alternates 依赖 |
| worktree / upstream | `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity` / `origin/task39extra_para_workstation_capacity` |
| 用户后续授权 | 两项目完全独立、不互写文件；本项目建立自己的 canonical clone，覆盖任务书要求使用旧 canonical 的安排；允许与隔壁现有 heavy case 同时计算 |
| CPU 隔离 | 隔壁当时8个 worker 位于逻辑CPU0–7，本项目 MPI1/线程1固定逻辑CPU24（socket1/NUMA1）；OpenMPI 禁止重新绑定，继承CPU24 |
| 内存 / swap | MemTotal=2163100413952 B；初次 MemAvailable=2094982422528 B；可读 cgroup 祖先无更小上限；正式启动重新采样，swap使用及增量仍要求0 |
| ABI | Python3.12、DOLFINx0.10.0.post2、Basix0.10、FFCx0.10.1.post0、PETSc3.19.6 complex128/int32、SLEPc3.19.2、OpenMPI4.1.6、MUMPS5.6.1 |
| 环境隔离 | 本 worktree 新建 `.venv --system-site-packages`；系统库只读；本机已安装MPC/绘图/JIT依赖复制到本项目，无共享可写包、缓存或结果目录 |
| activation | 新增 `scripts/activate_myfenics_linux.sh`；真实 native marker，不伪造WSL；临时、Python bytecode、JIT、Matplotlib 缓存均位于本项目 ignored目录 |
| 修复范围 | native activation/marker和显式容量profile接线；保留V5 A/b/PC、精化策略与全部数值物理限值；不修改历史任务材料 |
| 初始测试限制 | 一项旧真实误差诊断测试依赖未随Git提供的ignored数组，保留缺项；不把它冒充已通过。本轮通过新的微型物理作用测试和条件native匹配reference补本轮资格 |

ABI路径、版本及实际已加载动态库见[环境记录](records/native_abi.json)。MPC动态库实际加载位置为本worktree；未向隔壁写入Git元数据、Python缓存或结果，未操作其进程。并行授权不代表实测性能无共享硬件影响，运行时间不作为相对笔记本的严格算法加速证据。

环境准备中的失败保留在 `benchmarks/artifacts/native_capacity/`：首次测试文件名错误未启动测试；缺pyvista/platformdirs/setuptools均为独立venv依赖缺项，补齐后只重跑失败的微型FE测试。沙箱禁止socket导致的MPI初始化失败通过在宿主机运行本项目MPI解决，未改系统MPI。
