# Task44：六层 0.7 nm 尺度代理模型

## 执行身份

| 项目 | 当前记录 |
|---|---|
| 执行分支 | `task44_sixlayer_surrogate_0p7nm` |
| 指定起点 / 初始 HEAD | `db790f92a186988c5147f1828d15c07034e7c430` |
| 起点来源 | `origin/task41extra_phi90_p50x50_g17x20` 在开始时核对到相同 SHA |
| canonical worktree | `/home/fenics/Projects/MyFEniCS-task44-sixlayer` |
| upstream | 当前实现验证完成后设置并推送到同名 origin 分支 |
| 仓库任务书 SHA-256 | `af74fccd43cbd6fd9edb216aadd853b01d60fe4c5cd5389c9fdeb65d1d58b837`，与用户附件逐字节相同 |

所有 Task44 的代码、测试、输入、输出和 Git 操作都在指定 worktree 中进行。Task42 checkout 的脏改动、stash、旧结果和共享环境保持原样；不 reset、clean、amend、强推或合并 master。

## 对原任务书的最新执行覆盖

用户明确把本轮执行地点改为 fenics-ws 原生 Ubuntu 工作站。因此，原任务书中的小内存电脑、8,000,000,000 B 目标和 10,000,000,000 B 硬上限不约束本轮；Task41/42 的历史额度、窗口和等待审查状态也不继承。六层物理、材料、数值门、数据分组及样本总数仍按 [`task.md`](task.md) 执行；时间窗口覆盖见下方最新用户澄清。

### 最新用户执行澄清（2026-10-30）

用户明确要求忽略原任务书和先前执行说明中的时间窗口截止，并持续推进到能够判断代理模型可行性。总 12 小时、资格 3 小时、预留 30 分钟收尾，以及单样本运行 30 分钟到点强停规则均不再作为停工门。继续记录真实 wall time、成本、阶段进度和 heartbeat，并据实测成本调整采样规模；耗时较长不等同于代理不可行。该澄清不解除真实资源硬门、动态宿主余量与 384 GiB reserve、邻任务核查、服务失联处置、首样本 cap ≤128 GiB、首样本通过后最多两个并行样本、既有训练/验证/盲测与精度复算数量上限，也不改变六参数范围和冻结物理条件。原始 `task.md` 保留为用户附件历史文本，本段是当前更高优先级执行覆盖。

工作站采用动态资源准入，避免占满整机：

- 首个正式样本单独运行，任务内存 cap 初始不超过 128 GiB，数学线程 1、MPI 1、任务 swap 必须为 0。
- 首样本通过资源与数值资格后，最多同时运行两个独立样本；合计 cap 初始不超过 256 GiB，宿主动态可用内存须扣除至少 384 GiB reserve，且每个任务保留 `max(8 GiB, 该任务 cap 的 5%)` buffer。
- 每次准入还需读取 fresh `MemAvailable`、当前邻任务清单、所有本任务活动 job 的合计 cap 与祖先 cgroup headroom。进程命名空间能见到的进程数不能代替邻任务核查。
- 正式样本须由独立持久服务执行，`Restart=no`，专属 cgroup 禁止 swap；终止时只清理由本任务登记的精确 service/cgroup/PID。
- 按上述最新用户澄清，不再以 12 小时总窗口、3 小时资格窗口、30 分钟收尾窗口或 30 分钟单样本到点强停。持续记录真实运行时间、阶段进度、资源和成本，以成本证据决定后续采样规模；资源硬门、邻任务保护及其余任务上限仍有效。

开始前的只读宿主快照：`MemTotal=2,163,100,385,280 B`、`MemAvailable=2,120,353,783,808 B`、宿主 swap 已用 `955,203,584 B`。这是 `free -b` 的宿主快照，不是任务 cgroup 余量或任务峰值；当前命令进程视图只显示本会话，未证明邻任务为空。正式准入必须重新采集宿主、邻任务和服务 cgroup 数据。Task44 worktree 通过 [`scripts/activate_task44_native.sh`](../../scripts/activate_task44_native.sh) 复用母仓已资格化 ABI venv，并将源码导入路径与 JIT 缓存隔离到本任务；轻量 ABI preflight 已通过：Python 位于母仓 `.venv`，PETSc 3.19.6 `complex128` / `int32`，SLEPc 3.19.2，OpenMPI 4.1.6，MPI size 1；petsc4py、slepc4py、DOLFINx、Basix、mpi4py 与 dolfinx_mpc 均可从同一原生 ABI 导入。该检查仅验证软件栈，不代表 PDE 资格。

## 冻结物理与数值合同

| 项目 | 固定条件 |
|---|---|
| 周期单胞 | x/y 均为 `[0, 2.5] nm`，双 Floquet |
| 基底与柱 | 基底 Si 为 `z∈[-0.5,0] nm`；柱截面 `0.85×1.0 nm`，居中，x=`[0.825,1.675]`、y=`[0.75,1.75]` |
| 六层顺序 | 自下而上 Si / Si₀.₇Ge₀.₃ / Si / Si₀.₇Ge₀.₃ / Si / SiO₂ |
| 厚度 | 六个独立参数 `tᵢ∈[0.5,1.0] nm`；总高为 3–6 nm，不固定总高、不补齐末层 |
| 空气与端口 | 柱顶上方空气 0.5 nm，动态 `z_top=H+0.5 nm`；底部观察面固定 `z=-0.5 nm`；上方空气与下方 Si 半空间均用完整 Fourier-DtN |
| 波与离散 | λ₀=0.7 nm，掠角 1°，`incident_theta_deg=89`，方位角 90°，S 偏振，三维 Nédélec H(curl) p6，complex128 |
| 首个网格候选 | x 3 段 × y 6 段 × z 8 段 = 144 个贴体六面体；这是起步候选，须读回标签、体积、周期匹配、正 Jacobian 与实际自由度，不代表精度已通过 |
| 每场结果 | `R_total`、`T_total`、`R00_s`、`R00_p`、`R00_total`、`A_balance`、`A_volume`、full explicit true residual、网格/DoF、完整 DtN 模态清单、全流程与分阶段耗时、进程树峰值内存、任务 swap |

六个层位使用三种独立材料模型：Si 出现三次、Si₀.₇Ge₀.₃ 出现两次、SiO₂ 出现一次；网格仍保留六个互不相同的 tag，便于逐层核对吸收。Si 使用 Task41/Task40 已冻结且有公开来源的 0.7 nm 值，不借用 Task39para 的不同值。SiGe 中 30% Ge 是原子/摩尔分数；SiO₂ 第一版使用非晶 silica、密度 2.2 g/cm³。材料来源、密度、组成、混合公式、符号约定及复折射率/介电常数均已写入 [`materials.md`](materials.md) 和 [`source_receipt.json`](source_receipt.json)；它们是公开原子表与成分/密度假设计算出的 `derived` 输入，不是样品的 `measured` 值。

数值 Gate：full explicit true residual ≤ `1e-6`；`|R_total + T_total + A_volume - 1| ≤ 1e-5`；代表点经网格、DtN 倏逝模态和上方空气间距对照后，`R_total/T_total/R00_total` 变化均 ≤ `2e-4`。这些是所检查离散间的稳定性门，不是连续解误差保证。首批代表点 A–D 为 `(0.5,…,0.5)`、`(0.75,…,0.75)`、`(1,…,1)`、`(0.5,1,0.5,1,0.5,1)` nm；合格原始样本计入训练且不重复计算。

有限元资格通过后才训练代理：固定种子，训练点最多按 20→40→80 扩展；另留 10 个开发验证点与 10 个最终盲测点，总计不超过 100 个独立几何。GP 主模型为归一化输入上的 Matérn 5/2 ARD，输出为 `R_total/T_total/R00_total`；同时报告均值和线性基线、原单位平均与最大绝对误差、学习曲线及盲测逐输出误差。模型/超参数/采样策略冻结后才打开最终盲测；盲测目标 max-absolute error ≤ `1e-3`。若响应变化接近数值噪声，结论应为证据不足，不能宣传 GP 成功。

## 实现与验证顺序

1. 只读核验材料与现有 `SimulationConfig3D`、结构化网格、材料 tag、体积分、吸收后处理和 `.dat` input whitelist；明确所有受影响调用点及现有回归。
2. 在可复用 `src/` 中实现参数化六层材料栈、贴体分层网格和材料相关输出；沿公共 `python scripts/run_case.py input/path/to/case.dat`，扩展现有 schema/validation 和配置适配，不复制 solver 或 runner 框架。
3. 运行 ABI preflight，通过后做最小 pure-Python/material/mesh fixture 定向测试，再做最小有限元组件验证。首批正式输入固定走 `standard_full`，保留完整原始矩阵以检查 full explicit true residual。Task44 A 的实际组合物理形式经 FFCx 编译后，每个分层 tag 显示一个积分核；针对“每个 tag 至少两个核”的测试断言没有得到支持，记录为凝聚路径未资格、后移，不代表 PDE 失败。详细观察见 [`condensation_kernel_observation_v1.json`](condensation_kernel_observation_v1.json)。
4. 每场正式 PDE 前冻结输入、源码 SHA、材料表、网格/DtN 精度对照、单样本初始 128 GiB cap、service/cgroup 与资源硬门；运行期间按真实进度和资源情况继续，不使用原 30 分钟到点强停。
5. 完成代表点与精度资格后，根据实测单样本成本、已有独立样本上限和数值证据推进训练点、GP、开发验证与盲测；数据/GP 资格分别判定，不受原 12 小时窗口约束。

当前阶段：材料 receipt、六层输入、Task44 启动器和针对性修复已在执行分支实现。凝聚 kernel 数量假设已撤回，相关测试观察保留为未资格记录；standard_full 的层吸收、A–D 网格检查、超时边界和 subreaper 停止/清理测试继续执行。定向测试和原生 systemd 服务 smoke 通过并提交后，再从实际 Ubuntu 主机读取新鲜的 CPU、邻任务、内存及 cgroup 状态，绑定单个经核验的 CPU 与 128 GiB / 零 swap 的专属服务，启动首个正式样本 A。smoke 只执行公共 runner 的 `--dry-run`，不组装或求解有限元系统。正式运行采用共享 subreaper watchdog 的 `observe_only` 时间策略：继续记录运行时间，但不因时钟停止 PDE；动态内存、祖先 cgroup、零 swap 和精确服务身份仍由硬门控制。
