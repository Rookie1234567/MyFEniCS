# Task036 最终结项摘要

## 1. 一句话结论

Task036 没有得到一个既低维、又能在小掠射角和 P 偏振下还原 Full3D 全部通道、
同时显著节省整作业内存的 direct Hybrid 生产端口，因此主目标以
`controlled_negative / closed` 结项。但任务同时证明：Maxwell 域分解本身是正确的，
完整 FE trace-chain 可以与 Full3D 对齐，M120 长程模态传播核心在其已选空间内也基本正确；
失败集中在“低维端口没有覆盖完整界面 Cauchy 信息”，不能解释成 Full3D 物理解不存在。

## 2. 冻结身份

| 项目 | 冻结值 | 说明 |
|---|---|---|
| Task036 起始 master | `007298261681014efbe6508ac91c6c3ae9a6a44a` | 任务研究分支的原始基线 |
| Task036 最终研究 SHA | `7a0334008dc9bbdeefe55dd0ffa535cc756e661c` | 完整历史、重型 evidence 与研究代码的权威来源 |
| selective Group 1 | `7735a2617d18fe5f869331a90d47ec16632fd8d3` | Full3D correctness、遥测与生命周期修复 |
| selective Group 2 | `a741ad1b5cfb579e2667600bcc6497ec5c4f23d9` | Hybrid 接口安全、exact dual、beta 与 fail-closed 修复 |
| selective Group 3 | `4c9e1b9cedd4b04d65824698202c9fff96f3a0dc` | strong-trace 与 exact-trace research oracle |
| ordinary solver default | unchanged | 没有把 research-only 路径设为默认 |
| Task037 | `branch prepared / task not defined` | `codex/20260803-task37-matrix-free-iterative-development` 已从已推送 master `b615a130d7c34060a3445c352c1f683bbf3aa23f` 创建并推送；创建时 upstream 正确、ahead/behind=`0/0`、worktree clean；本次结项文档追加后保持与最终 master 快进同步 |

## 3. 方法与最终状态

Hybrid 的通俗含义是：上下复杂区域仍用三维有限元，规则的中间长段改用二维模态传播，
希望减少直接法需要分解的矩阵规模。Task036 发现，传播少量模态并不等于已经保留完整的
界面信息；界面同时需要切向电场与弱形式磁牵引，这里合称 joint-Cauchy 信息。

| 能力或路线 | 实际证据 | 最终状态 | 不能误读成什么 |
|---|---|---|---|
| Full3D 小掠射角/P 物理与通用修复 | Full3D-P、切向 DtN 投影、Ny alias、MUMPS 计数、内存与 DoF 语义均有通过或确定性拒绝证据 | `pass`，选择性保留 | Hybrid-P 已通过 |
| 原始 physical-QEP M120/M240 完整端口 | M120/M240 没有闭合完整界面和全部衍射通道；增加 M 没有形成生产解 | `controlled_negative / closed` | Maxwell 域分解或 P 物理不可解 |
| M120 长程模态核心 | 40/60/100 nm 的 selected-space exact FE 对照约为 `1.59e-11–1.95e-11` | `retained` | M120 已覆盖完整端点 trace |
| strong-trace M120 | 切向 E jump 降至 `4.588e-15`；但 energy closure `1.531666e-5 > 1e-5`，固定通道仅 `77/96` | `research_only / controlled_negative` | production Hybrid 或全通道闭合 |
| exact FE trace-chain | one-cell Schur、endpoint Cauchy balance 与完整 FE trace-chain 能作为 Full3D 域分解正确性对照 | `research_only correctness oracle` | 可扩展生产 solver |
| complete M120/M240 global port | 完整 joint-Cauchy/全通道合同未满足 | `not production-qualified` | 可用于 0.7 nm 正式预测 |
| B1 discrete-Bloch `d<=360` | 低维端口容量审计未达到 production contract | `controlled_negative / closed` | 应继续扩大同一 direct campaign |
| C1b/C1c teacher、POD 与 actual compressed candidate | 用户撤销授权，未运行 live 96-RHS teacher | `cancelled / not_run` | 失败的数值实验 |
| 0.7 nm、最多 2 TiB | Task036 没有建立满足精度和资源合同的 solver | `not solved` | 1–2 TiB 已证明可行 |

## 4. 选择性整合边界

| 组别 | 进入 master 的内容 | 明确不进入 master 的内容 |
|---|---|---|
| Group 1 | Full3D/通用 correctness、alias fail-closed、MUMPS/内存/DoF 遥测与生命周期修复 | Task036 综合 robustness runner |
| Group 2 | reciprocal 通用一致性、exact conormal dual、propagation/traction beta 身份、near-degenerate detector、Hybrid-P status contract | scalar reciprocal production 路径、bounded repair、自动 retry/fallback |
| Group 3 | strong-trace 最小 research core、exact FE trace-chain oracle、endpoint trace metric 和 focused tests | mode-pool、capacity、POD、96-RHS teacher、7679 行综合研究 runner |
| 文档 | `task.md`、V8、`fix_report`、`test_summary`、本摘要与 `response_v8` | V1–V7、reply、round-by-round 大历史和重型 artifacts |

Task036 远程分支仍是完整研究历史的权威来源；master 只保存可复用、可测试且不会改变
ordinary default 的最小能力。

## 5. 测试口径

历史 Task036 分支的完整测试与 PDE 证据原样保存在
[`test_summary.md`](test_summary.md)。本次 selective integration 的测试必须单独解释，
不能用历史分支结果冒充当前 master 已重跑。

| 检查 | 当前结果 | 数据身份 / 解释 |
|---|---|---|
| ABI preflight | pass：qualified activation、PETSc `complex128 / int32` | 当前 WSL 资格化环境 |
| Group 1 targeted | `39 passed in 2.18 s`；另组 `15 passed in 3.11 s` | DtN/alias、watchdog、identity、MUMPS、生命周期与资源语义；两组不相加冒充唯一总数 |
| Group 2 focused contract | 最终新测试 `10 passed in 1.81 s`；default/record 组合 `20 passed in 1.88 s` | 两组有重叠，分别保留命令级证据 |
| Group 2 小型真实离散 | reconstruction `1 passed in 6.30 s`；exact conormal direct `1 passed in 5.61 s`；static Hybrid equivalence `1 passed in 4.40 s` | p2 小 fixture；验证 reciprocal trace、beta 身份、exact dual 和 static/standard observable 对齐 |
| Group 3 oracle | serial `7 passed in 3.26 s`；MPI2 recursion 每 rank `1 passed in 1.61 s` | strong-trace fixture、one-cell Schur/Cauchy、full-FE trace-chain、稀疏 metric |
| 最终 compact targeted | `24 passed in 1.91 s`；DtN/alias `14 passed in 2.20 s` | mode fail-closed、非重型 test53 reference、native Full3D identity、ordinary defaults 和 synthetic alias 正/负例 |
| p2 Full3D PDE smoke | ordinary direct `1 passed in 2.74 s`；static-condensed direct `1 passed in 2.50 s` | 每项 802 FE DoF；真实 residual、R/T、row 与 lifecycle Gate |
| 小型 static algebra | `2 passed in 1.83 s` | 两单元 Schur/内部恢复与 exact Floquet-slave reduction |
| Ruff、format、compileall、`git diff --check` | pass | 当前已整合代码与文档的最终静态检查 |
| 文档/数据合同 | docs targeted `7 passed`；tracked JSON `928` files parse pass | registry、Markdown table、local links 与 JSON syntax |
| combined pytest | `41 passed in 107.99 s` 后由用户要求中断；exit `2` / `KeyboardInterrupt` | `interrupted_by_user`；不是 PASS，也不是代码 failure |
| 小时级 full repository pytest | `cancelled / not_run` | 用户最新明确取消；不得沿用历史 803/41/3 写成当前通过 |
| Ny3/Ny4 actual PDE pair | `not_run_by_user_cost_override` | synthetic alias controlled negative/positive 已通过；V8 将 actual Ny3/Ny4 写为“若成本允许”，本轮不扩成新 PDE campaign |

中断没有产生失败 assertion；因此它只表示“这次完整 suite 没有跑完”。本轮随后完成了上表
focused targeted tests 与两项轻量 Full3D PDE smoke；没有删除测试、放宽 Gate，也没有把
未运行项写 PASS。

## 6. 后续边界

Task036 数值开发到此停止。Task037 空分支已准备，但任务仍未定义；没有创建 Task037
`task.md`、实现 solver 或运行新 PDE。在用户和新的任务书明确授权前，不开始 iterative
solver、0.7 nm PDE、POD/capacity campaign 或新的 direct-port basis 开发。
