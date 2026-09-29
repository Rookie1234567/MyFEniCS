# V31 投影布局：组件候选成立，正式场未完成

## 结论

V31 把 H6 局部计算中积分点的内部排列改为固定的自然顺序，目标是让相同数学操作更连续地读写内存；矩阵、积分点、权重和物理方程均未改变。小规模组件配对支持该候选：H6 两个已保存向量的中位 wall/CPU 时间分别改善 6.24%/6.25% 和 18.05%/18.05%，六组配对均更快。额外固定形状矩阵乘法没有稳定增益且需要更多临时空间，因此关闭。

唯一的 V31 正式运行在 i112 完整残差检查后被人工停止；普通迭代日志还记录到 i113。停止前最后一条完整显式原方程相对残差为 `2.713995416229632e-6`，仍高于 `1e-6` 判据；没有最终释放后残差、最终场或 R/T/A。该结果是 **`USER_CONTROLLED_STOP`，数值结论未完成**：既不是求解失败，也不是通过。

停止由我误把 cgroup `memory.current` 的 8 GiB 数值当作硬终止线触发。Review V29 明确说明 V29/V30 的 RSS 数字不是停止线；本次实际启动 cap 为 `13,358,809,088 B`，watchdog 测得的整棵进程树 RSS 峰值为 `7,324,389,376 B`，没有达到该 cap。停止时最后观察到的 cgroup `memory.current/peak` 为 `8,602,890,240/8,603,148,288 B`，但这不是本轮 watchdog 的 process-tree RSS 口径；当时 `memory.events` 的 high/max/oom 均为 0。这个判断错误已保留在记录中，不能改写成资源门控停止。Review V29 只授权一次正式场；本次尝试已消耗该额度，不会自行重跑。

## 模型与运行身份

| 项目 | 实际记录 |
|---|---|
| 模型 | Full3D；original；p6/h7.5；粗 p4；990 个单元；80 个端口模态；MPI1、数学线程1 |
| 数值环境 | WSL Linux qualified activation；PETSc `complex128/int32`；运行输入 profile=`physical_p6_trace_projection_layout_v31` |
| 源码 SHA | `baeb0b3a7e74e3b77705e70918772d1dcacb9639` |
| 输入 SHA | `b19bf2d6a0a5f7a45a9910e3d3f25b1e3a896daa2205e78327be8f169cc9c7d0` |
| 物理模型 SHA | `0875aaf070d88732b09ead8c55a7d4c28dd75f9b329e90f35fea984a0b7464e6` |
| 运行目录 | `results/euv_grazing1_phi0/task39extra_v31_projection_layout_original_h7p5_v1__full3d_iterative__mpi1__Mna/20260929T022451.109239Z/` |
| 服务 | `myfenics-case-20260929T022450-1134512.service`；结束分类=`USER_CONTROLLED_STOP`；后代清理完成 |

## 停止前数值记录

显式真残差是原始 A6 方程误差相对右端项的比例；越小表示当前迭代解越接近满足原方程。下表仅列完整检查点，不代表收敛终态。

| 迭代步 | 显式原 A6 相对残差 | 端口闭合相对误差 | 原生恒等式相对误差 |
|---:|---:|---:|---:|
| 0 | 1.000000 | 1.000000 | `7.96e-27` |
| 16 | `4.1437223e-3` | `8.38e-16` | `1.13e-11` |
| 32 | `3.3529180e-4` | `1.92e-15` | `1.13e-11` |
| 48 | `1.9419221e-4` | `6.52e-16` | `1.13e-11` |
| 64 | `3.0233523e-5` | `1.22e-15` | `1.13e-11` |
| 80 | `1.7609468e-5` | `1.48e-15` | `1.13e-11` |
| 96 | `3.7766999e-6` | `6.87e-16` | `1.13e-11` |
| 112 | `2.7139954e-6` | `9.56e-16` | `1.13e-11` |

第 112 步保存了 667,152 个复数自由度的原 A6 残差向量。离线以该向量范数除以保存的 RHS 范数，并对端口闭合、内部残差和两个恒等式向量重算范数；五项都与 JSON 中的标量完全一致（差值均为 0）。这是停止前 checkpoint 的独立数值核对，不是最终残差资格。

## 阶段、计时与资源边界

MUMPS p4 数值因子、p6 局部设置和两个 X1 向量检查均完成，随后 FGMRES 正常推进；完整残差检查到 i112，普通迭代日志记录到 i113。第 112 步累计 `solve_seconds=1681.666031 s`，外层矩阵作用计数为 115、PC 计数为 112。正式 worker 没有写出终态 summary；setup 子阶段时间、释放计时、后处理计时和整场可比总时间均记为未知，不从残差记录推算。

| 口径 | 结果 | 说明 |
|---|---:|---|
| watchdog 单调时钟 elapsed | `2107.048 s` | 服务全流程到停止；不是完整成功场时间 |
| conservative realtime budget | `2298.397 s` | 与 monotonic 相差 `191.283 s`，超过本记录的容差；两者分列，不归因 |
| 任务时间限制 | 43,200 s，未到限 | time policy=`observe_only`，时间没有触发停止 |
| watchdog 整树同时 RSS 峰值 | `7,324,389,376 B`，8,279 个样本 | 含服务树采样；这是正式记录的 RSS 口径 |
| 实际启动 cap | `13,358,809,088 B` | 启动时 physical-memory-pressure 动态余量 cap；RSS 峰值未触及 |
| PSS | `null` | `DISABLED_BY_PROFILE`，不是零 |
| 进程树 swap | `0 B` | observe-only；不能称作强制 zero-swap Gate |
| 停止时临时 cgroup 读数 | current `8,602,890,240 B`，peak `8,603,148,288 B` | 操作过程中的 cgroup 采样，不等同整树 RSS；它触发了误停 |

worker 的 field-reference 检查在第 32、64、96 步均记为 `NOT_ATTEMPTED`，指标为空；没有正式场、通道或物理结果。V31 dynamic checker 需要最终 worker summary，而本次中止运行没有该文件，因此完整动态 checker 未运行，不能写为 PASS 或 FAIL。现存第 112 步 residual packet 的范数核对结果见 [checker record](records/projection_layout_v31_checker.json)。

## 候选裁决与边界

自然序布局仍只属于显式 V31 profile，ordinary default 未变。组件等价和短操作计时支持候选进入本机正式验证，但本次完整场没有走完，不能据此宣称端到端提速、物理等价或工作站可迁移。固定矩阵乘法、局部批处理和流式端口路线仍未采用。新完整 PDE 需要新的正式授权。

机器可读总账见 [compact record](records/projection_layout_v31_compact.json)、[checker record](records/projection_layout_v31_checker.json)、[selection record](records/projection_layout_v31_selection.json) 和 [run index](records/run_index.json)。前置 R1/R2/R3 证据及保留的 V30 对照见 [V30 re-audit](records/projection_layout_v31_v30_reaudit.json)、[components](records/projection_layout_v31_components.json) 和 [Review V29](../review_report_v29.md)。
