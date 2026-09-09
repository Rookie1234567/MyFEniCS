# 原生环境与迁移记录

| 项目 | measured 事实 / 执行决定 |
|---|---|
| 冻结 base / 任务提交 | `450255f4575792d052c1bac29837d39955ee1039` / `8d41877f9b233209b534b27648ecc657e40a1573`；祖先关系已核实 |
| 独立 canonical | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；从指定远端分支克隆；本地对象只读借用后 dissociate，无 alternates 依赖 |
| worktree / upstream | `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity` / `origin/task39extra_para_workstation_capacity` |
| 用户后续授权 | 两项目完全独立、不互写文件；本项目建立自己的 canonical clone，覆盖任务书要求使用旧 canonical 的安排；允许与隔壁现有 heavy case 同时计算 |
| CPU 隔离 | 隔壁当时8个 worker 位于逻辑CPU0–7，初始测试使用CPU24，发现满载仍为1GHz后改用CPU8（socket0空闲核心）；本项目MPI1/线程1，OpenMPI禁止重新绑定，继承CPU8 |
| 内存 / swap | MemTotal=2163100413952 B；初次 MemAvailable=2094982422528 B；可读 cgroup 祖先无更小上限；正式启动重新采样，swap使用及增量仍要求0 |
| ABI | Python3.12、DOLFINx0.10.0.post2、Basix0.10、FFCx0.10.1.post0、PETSc3.19.6 complex128/int32、SLEPc3.19.2、OpenMPI4.1.6、MUMPS5.6.1 |
| 环境隔离 | 本 worktree 新建 `.venv --system-site-packages`；系统库只读；本机已安装MPC/绘图/JIT依赖复制到本项目，无共享可写包、缓存或结果目录 |
| activation | 新增 `scripts/activate_myfenics_linux.sh`；真实 native marker，不伪造WSL；临时、Python bytecode、JIT、Matplotlib 缓存均位于本项目 ignored目录 |
| 修复范围 | native activation/marker和显式容量profile接线；保留V5 A/b/PC、精化策略与全部数值物理限值；不修改历史任务材料 |
| 初始测试限制 | 一项旧真实误差诊断测试依赖未随Git提供的ignored数组，保留缺项；不把它冒充已通过。本轮通过新的微型物理作用测试和条件native匹配reference补本轮资格 |

ABI路径、版本及实际已加载动态库见[环境记录](records/native_abi.json)。MPC动态库实际加载位置为本worktree；未向隔壁写入Git元数据、Python缓存或结果，未操作其进程。并行授权不代表实测性能无共享硬件影响，运行时间不作为相对笔记本的严格算法加速证据。

环境准备中的失败保留在 `benchmarks/artifacts/native_capacity/`：首次测试文件名错误未启动测试；缺pyvista/platformdirs/setuptools均为独立venv依赖缺项，补齐后只重跑失败的微型FE测试。沙箱禁止socket导致的MPI初始化失败通过在宿主机运行本项目MPI解决，未改系统MPI。

## CPU2 低频调查

原生R0测试最初固定逻辑CPU24（物理socket1，即界面CPU2）。忙核频率连续约1GHz，而隔壁socket0忙核约3.6GHz。CPU2 package温度56°C，CPU1约74°C；两边core/package thermal throttle计数均为0。两边驱动intel_cpufreq、governor=schedutil、范围1–3.9GHz，turbo开启，RAPL长期/短期功率限制同为165/198W。以上未指向热节流或显式软件频率上限；实际功耗和硬件limit-reason尚未取得，根因未确定。

独立2秒Python标量循环（非有限元、未碰隔壁CPU0–7）：CPU9约2024万次，中位3.6GHz；CPU24约562万次、CPU25约564万次，中位均1GHz。该探测仅说明当前负载下CPU2确实慢，不是算法加速测量。只迁移本worktree的pytest进程到CPU8后，其核心立即升到3.6GHz。未改变全局governor、功率、BIOS或任何隔壁进程。MSR读取权限不足，非交互sudo不可用，未输入密码或修改权限。正式运行固定CPU8以绕开低频，不能称为已修复CPU2。

R0真实18cell有限元作用测试通过（1 passed，387.14s，CPU24低频）；聚焦回归70 passed、1 deselected，774.76s，前段CPU24、后段CPU8，因此此回归耗时不作为性能基准。缺失的历史ignored误差数组测试明确跳过，未改写为通过。CPU短探测记录见[频率证据](records/cpu_frequency_probe.json)。

### 用户执行只读root硬件探测后的更新

[寄存器紧凑证据](records/cpu_hardware_limits.json)表明CPU24忙时IA32_PERF_CTL=0x2700（请求倍率39），IA32_PERF_STATUS低频倍率10；APERF/MPERF差分得到1000.001MHz，同期CPU0为3598.637MHz。CPU2的IA32_THERM_STATUS bit2连续置位（外部平台PROCHOT/FORCEPR事件），bit0为0（CPU内部热传感器未触发高温保护）。这比仅看thermal_throttle计数更直接：已确认平台外部限频，不能再归因为操作系统未请求升频。CPU2同期RAPL封装功率约34.38W，CPU1约117.81W；不代表整机或电源输出功率。

[Intel寄存器定义](https://cdrdv2-public.intel.com/868136/252046-081-sdm-change-document.pdf)说明bit2由平台其他agent触发。具体信号来源仍待查。主板实测Supermicro X11DAi-N、BIOS3.3（2020-02-26）。[厂家同型号FAQ34600](https://www.supermicro.com/support/faqs/faq.cfm?faq=34600)曾报告低温限频由电源电压不稳定引起；这是优先调查供电的依据，不是本机电源损坏的证明。未关闭PROCHOT保护、未清日志、未改MSR、governor或BIOS，隔壁持续计算。下一步只读BMC电源库存、传感器和事件，必要的物理供电检查须等待停机窗口。
