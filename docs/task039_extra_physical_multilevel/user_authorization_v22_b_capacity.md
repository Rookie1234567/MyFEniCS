# Review V21 用户补充授权：B 模型单次受控实际容量试验

本文件逐字保存用户于 2026-09-19 在主控 task 发出的补充授权。旧 Review V21 已由 `response_v22.md` 正式回应，因此新增本文件保留历史；不改写旧 review、旧 B 结果或 V11 策略。执行分支为 `task39extra`，本批 base 为 `644423fb0901579e89675610789bf4d5aad93761`，新结果统一写入 `response_v23.md` 和独立 outcomes。

## 用户授权原文

本条作为Review V21的用户补充授权：允许对同一个990-cell、p6/h7.5原始B模型做一次显式、受控的实际容量试验。旧B停在symbolic之后、numeric之前；保留其全部记录和RESOURCE_BLOCKED分类，不当作实现bug重放，不重跑已通过的A。

只为新试验增加独立profile/输入与资源策略：保留原INFOG16/17=5060 MB及V11派生10131 MB请求作为预测记录，但不再让“固定2倍symbolic请求”单独否决本次numeric。不能只删Gate后仍把10131 MB传给MUMPS，也不能全局修改旧V11规则。

numeric前，依据现场有效RAM/cgroup、当前非factor对象、临时缓冲和后续H6/p6/Krylov需求，冻结一个安全且有限的ICNTL(23)额度并读回；额度必须纳入对象账和真实进程树预算，不能等同于整机内存。原整树硬上限、动态系统余量、zero-swap、临时空间检查和独立watchdog全部保留，不以OS OOM作为正常停止方式。现场安全额度不足时保存明确原因，不强跑。

若numeric成功，立即保存原生allocated/used、factor条目、实际RSS及矩阵身份；检查后续对象容量，通过后在同一进程、同一份factor上继续H6/p6缓存、完整B求解与物理输出，不为了测量再重复分解。后端额度不足、实际资源超限或监督异常就停止并清场，不自动扩大额度、换排序、降p、减mode、改网格或启用BLR/OOC。

保持990单元共同网格、原80通道、双层凝聚、BAL_H/H6、准确p4一次回代、FGMRES32/max2048、原A6<=1e-6及observe_only不变。复用身份合格的JIT与已有输入证据，不重复已有诊断，不另建容量平台。先只补B，不自动启动C；新source/input、补充授权、全部成本和实测结果写入新response/outcomes，保留旧历史，推送同一task39extra分支后统一审阅，不合并master。

## 执行身份与证据边界

本试验仅改变给 p4 稀疏直接分解器的有限内存额度。symbolic 是先分析稀疏连接并估算容量，numeric 才实际计算因子；旧 B 只做到了前者，因此本次旨在测得真实分配及后续完整求解能力，不能提前宣称一定装得下。

- 原 B：`Z3_ORIGINAL_H7P5`，source `f8d0fbf3da48fd3cbe5cc3a226dbff3feb1d9b48`；保留 `H7P5_RESOURCE_BLOCKED_ON_LAPTOP` 和父层/worker 原始分类。
- 原 B 根：`results/euv_grazing1_phi0/task39extra_v21_z3_original_h7p5__full3d_iterative__mpi1__Mna/20260915T065308.474983Z`。
- 共同网格计划：`outcomes/records/v21_frozen_geometry_mesh_plan.json`；SHA256 `b5bab6aae4668be60aacbb49265b4c875def42e2620256cd168d8c26207dc157`，轴向单元数 `9 × 5 × 22 = 990`。
- 原 A 的通过结果只读复用，C 保持未运行。新试验不得占用旧批次的 bug replay 名额，也不得修改旧费用。
- 原安全线不变：对象库存 6 GiB、临时池 1 GiB、整树硬上限 8 GiB，并继续受现场有效 RAM/cgroup 与系统 reserve 约束。所有额度只是政策预算，分别报告原生 allocated/used 与实测进程树 RSS。
- 本机试验不触碰工作站、5 nm 任务或 master；最终集中推送后等待审核。
