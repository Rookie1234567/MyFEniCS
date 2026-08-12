# Task39 T0：资源预算与停止合同

本账本只定义运行前可以审计的资源边界和证据口径。历史 Task37/Task37b 的
GiB 数字是各自记录中的 measured evidence，不能在本任务中当作 5 nm 的预算
实测，也不能反推 0.7 nm 可运行。

## 1. 主机与硬停止

| 项目 | 合同值 | 解释 |
| --- | --- | --- |
| physical memory | `256 GiB` | 主机物理内存上限的任务书身份；不是单个 worker RSS |
| warning | `180 GiB` | process-tree/cgroup 进入预警后记录 telemetry，不自动改变 solver 参数 |
| hard stop | `min(220 GiB, 0.9 × 实际可用内存上限)` | 终止边界由运行前测得的 available-memory 计算；不能把 220 GiB 当永远可用 |
| swap | `0` | 作业 authority 要求零 swap；global WSL/pagefile 诊断与 dedicated job swap 分开记录 |
| concurrency | 一次只跑一个 heavy case | 不并行启动另一份 MPI/PDE 来“填满”机器或比较资源 |

```math
\mathrm{hard\_stop\_GiB}
= \min\left(220,
0.9 \times \mathrm{available\_memory\_GiB}\right)
```

当采样不可读、作业 cgroup 不是 dedicated，或只有 WSL global swap 信息时，不能
把缺失值写成 zero-swap pass。process-tree `VmRSS`/`VmSwap` 是作业的基础样本；
dedicated cgroup 的 current swap 只在明确属于本作业时参与，并按现有 authority
口径取二者的较大值而非相加。

## 2. 证据分类

| 标签 | 允许的含义 | 禁止的写法 |
| --- | --- | --- |
| `estimated` | 运行前根据 mesh、M、MPI 和已知生命周期得到的预算 | 不写成实际峰值或通过 Gate |
| `measured` | 运行期间 process-tree/cgroup 样本得到的 peak、sample count、wall | 不把单 rank `ru_maxrss` 当 simultaneous job peak |
| `derived` | 由已测字段计算的值，例如硬停止阈值、能量闭合或比例 | 不把派生结果替代原始 authority |
| `not_run` | 该阶段尚未启动 | 不写成 pass、fail 或预测结果 |
| `failed` | 明确超过合同或发生真实运行错误 | 必须保留实际数值、限值和 raw evidence |
| `controlled_stop` | 按用户/任务书规则停止，或在 Gate 前受控终止 | 不改写成数值失败，也不伪装成完成 |

每次 formal run 还应记录 source/input/physical/resolved hash、MPI size、sample
count、process-tree RSS peak、swap、warning/termination reason、wall 和退出分类。
资源终止不等于 Maxwell 或 Hybrid 数学失败；反之，数值通过也不自动满足资源偏好。

## 3. 已有 telemetry 与最小接线

当前 [Task034 resource authority](../../../benchmarks/task034_wsl_resources.py)、
[process-group control](../../../benchmarks/watchdog_process_control.py) 和 Task38
launcher 已提供：

1. process-tree 的 RSS/Swap 样本和 peak；
2. dedicated cgroup 的 memory/swap 信息及 WSL global swap 的诊断字段；
3. warning、timeout、memory、swap policy 和 worker termination 分类；
4. stdout、manifest、summary、resolved config 与 source hash 的运行目录绑定。

Task39 只应复用这些既有生命周期和记录接口。不要创建第二套 watchdog、后台采样
服务、retry/fallback 或把资源控制放进 solver。若启动前 ABI、source clean、MPI
rank identity 或 memory budget 不满足，分类为 Gate blocker 并保留证据，不能先跑
正式 PDE 再解释环境。

## 4. T1 缺口与 Phase 边界

| 缺口/阶段 | 最小边界 |
| --- | --- |
| public iterative entry | 当前 public methods 缺 `full3d_iterative`；只接入 Task39 审定的有限 profile，不开放任意 degree、M、物理或 campaign 扫描 |
| inherited Hybrid profile | Task38 Hybrid profiles/checkers 绑定旧 13.5 nm、1°、M120 等身份；必须用 resolved Task39 material/geometry/angle/source 重新绑定，不能只改标签 |
| material provenance | `delta/beta/n/epsilon_r/wavelength/labels` 要进入 resolved and manifest identity；缺失时停止，不用旧材料常数补齐 |
| M3a runner | 历史 Full3D static-condensed、matrix-free exact-action、physical-slab/two-level coarse right-FGMRES runner 绑定旧 config；Task39 需要薄的 config/argv seam 复用既有核心，不复制 Hybrid block-LDU、DtN 或 recovery 数学 |
| Phase A | p6/h10、5 nm wavelength 的 algorithmic stress anchor；`h/lambda=2` 只说明压力测试尺度，不是最终 5 nm 精度答案 |
| Phase B | 只有 Phase A、材料 provenance、residual/physics、source/hash 和资源 Gate 满足后才条件进入 |
| 0.7 nm | 材料常数不完整时仅允许 component-only feasibility，并固定 `0P7NM_MATERIAL_INPUT_INCOMPLETE`；禁止完整 PDE、Hybrid qualification 和 production claim |

M120 的通俗含义是 Hybrid 中部 QEP/内部模态每个传播方向的显式保留数：它决定
该中部模态问题的规模，但不代表任意材料都需要 120，也不代表模式数已经收敛。
external DtN enumerator 必须根据波长、材料、Floquet shift、传播性和零级保留逐次
给出 outgoing order inventory；significant channel 只在后处理报告中形成集合。
