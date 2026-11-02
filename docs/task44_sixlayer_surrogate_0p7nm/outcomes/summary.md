# Task44 outcomes summary（12/12 资格尝试已结清；y/空气稳定性未通过，历史 DtN 截断稳定性未证明）

## 当前状态

截至 2026-10-31，旧版冻结厚度点 A–D 均已用 P6、144 个贴体六面体、装配期静态凝聚和 MUMPS exact 完成正式三维计算。四场都通过完整离散算子相对真残差门（≤ `1e-6`）和体吸收能量闭合门（≤ `1e-5`），并保存了全级 DtN 端口 R/T 与场数据。它们是当前有限网格上的正式离散样本，不代表连续解精度；旧版 A–D 基于 y 与顶部空气稳定性核查的资格未通过。此历史结论不改变后续冻结 v2 设计中各样本独立取得的标签。历史 DtN 倏逝壳层尝试的真残差失败，导致截断稳定性未获证明；用户已取消继续扩展该壳层，这不是待执行的必要复算。

用户允许 Task44 与 Task40 同时运行；Task44 只监控自身 service 与资源，不停止或修改 Task40。四项精度对照由 Task44 一次运行一个。传播方向 y 加密第一次启动因 service 子进程身份未稳定而受控终止，没有进入矩阵组装或求解，保留为 `MONITORING_FAILED / not_run`；retry 的残差与能量闭合通过，但相对 B 的三个主输出变化均超过 `2e-4`，所以旧版配置的 y 方向稳定性门失败。材料内部 z 加密的残差与能量闭合通过，三项主输出相对 B 的变化约 `1e-10`，z 方向门通过；这不证明 y 方向或连续解已收敛。DtN 倏逝模态扩展的 full explicit 相对残差为 `1.623574709e11`，远超 `1e-6` 门限，official R/T/A 跳过，因此该次尝试没有证明截断稳定性。用户已取消继续扩展 DtN 壳层，不把这项历史负结果列为待重跑要求。顶部空气间距对照已完成：full true residual `6.752756601e-10` 和端口/体积能量闭合 `-7.221615528e-10` 均通过，但相对 B 的 `R_total`、`T_total`、`R00_total` 变化绝对值分别为 `2.34999e-4`、`2.28409e-4`、`2.35003e-4`，均略高于 `2e-4`，旧版配置的空气间距稳定性门失败。y 与空气间距两个历史精度门未通过，因此旧版 A–D 的历史资格字段仍为 `gp_eligible=false`；这不覆盖独立的 v2 样本标签。


## v2 固定离散 GP 训练样本更新

以下 v2 样本与旧版 A–D 的空间稳定性资格是不同问题：train_005、train_006、train_008、train_009 和 train_011 取得了**冻结 v2 离散模型的训练标签**；train_007 没有完成官方数值结果而不进入训练集，train_010 虽写出完整数值结果但外层监控失败、外层结果记录未完成，仍保持 held。train_008 只计一个样本：r1 监控失败且无标签，r2 数值门通过并经主控批准登记；冻结设计仍保持 `planned_not_run`。train_009 的完整数值结果和独立模态重算通过，但外层 watchdog 在 manifest 结束 `0.256415 s` 后将 zombie wrapper 归为 `MONITORING_FAILED`；标签表保留数值 worker 与外层监控这两个状态，不覆盖原始失败分类。原始数值输出记录 `validation_role=numerical_sanity_only`、`physical_benchmark_candidate=false`；独立 post-completion receipt 的 `generic_flags_preserved` 子对象则为 `null`，receipt 保持原样，详细来源见[训练结果表](training_results_v2.md)。通用 runner 的这些字段不决定该固定离散标签。v2 设计中的 D 目前仍 held，原因是生命周期证据缺口，不是旧版 y/空气稳定性结论。所有标签仅绑定各自记录的 P6 离散模型，不代表连续解精度、整个厚度参数范围准确度或最终 GP 盲测通过。冻结设计文件未修改。

| 样本 | Task44 v2 标签结论 | 实测结果与边界 | 证据 |
|---|---|---|---|
| `train_005` | `qualified_v2_training_label` | 固定离散数值门通过；不外推连续解误差。 | [训练结果与身份核验](training_results_v2.md) |
| `train_006` | `qualified_v2_training_label` | 固定离散数值门通过；不外推连续解误差。 | [训练结果与身份核验](training_results_v2.md) |
| `train_007` | 无标签，`MONITORING_FAILED / not_run` | 求解后监控停止，未产生 full residual 与 official R/T/A。 | [训练结果与身份核验](training_results_v2.md) |
| `train_008` | `qualified_v2_training_label`（r2）；r1 保留 `MONITORING_FAILED / not_run` | r2 worker `COMPLETED`、official result true；`R_total/T_total=0.09760520879370416/0.8799314234420694`，`R00_s/p/total=0.09760480197859493/9.268408819992147e-23/0.09760480197859493`，`A_volume=0.022463367826854663`；full true relative residual `1.7907571605784237e-9≤1e-6`，闭合误差绝对值 `6.262834695291986e-11≤1e-5`。r2 service `4863.370 s`、worker `4799.974 s`；cgroup peak `13,886,492,672 B`，swap `0 B`，后代清空。历史 child identity coverage 仍 incomplete：37 个 live child identity 中 36 个出现在 members，唯一差集 `(499189,352129672)` 角色未知、无该 PID RSS 读数；标签依据与差集收据见[训练结果](training_results_v2.md)。 | [训练结果与身份核验](training_results_v2.md)、[r2 identity receipt](../../../benchmarks/artifacts/task44_owned_member_gap_review_20261102/train008_r2_identity_coverage_difference_20261102.json)、[r1 终态审计](../../../benchmarks/artifacts/task44_owned_member_gap_review_20261102/terminal_audit_008.json) |
| `train_009` | `qualified_v2_training_label_with_post_completion_monitor_failure` | `R_total/T_total=0.09564773048929644/0.8820422054769134`；`R00_s/p/total=0.09564729022865914/3.1914084860114788e-22/0.09564729022865914`；`A_volume=0.02231006403550309`；真残差 `8.566954013563746e-10`，闭合误差 `1.7128520823916915e-12`。数值 worker exit 0，监控在输出完成后失败；service wall `5351.293956477661 s`、cgroup peak `13,871,992,832 B`、swap 0、后代清空。 | [训练结果与身份核验](training_results_v2.md)、[完成后独立审计](../../../benchmarks/artifacts/task44_owned_member_gap_review_20261102/postcompletion_review_009.json) |
| `train_010` | held，无训练标签；`MONITORING_FAILED` | worker 写出 `R_total/T_total=0.10014744277467244/0.881888710462282`、`A_volume=0.01796384676247524`；完整真残差 `1.0163064670925226e-9`、闭合误差绝对值 `5.703215677499429e-13` 均通过。但外层记录仍为 `launching`，monitor identity gate 失败并 SIGKILL worker wrapper，不能据此登记标签。service `5873.109 s`；cgroup peak `13,877,776,384 B`，swap `0 B`，后代清空。 | [训练结果与身份核验](training_results_v2.md)、[010/011 终态审计](../../../benchmarks/artifacts/task44_owned_member_gap_review_20261102/terminal_audit_010_011.json) |
| `train_011` | `qualified_v2_training_label` | `R_total/T_total=0.09539431746138823/0.8818471128925663`；`R00_s/p/total=0.09539398436285274/1.9023763956054786e-21/0.09539398436285274`；`A_volume=0.022758569590891644`；完整真残差 `9.99492471986335e-10`，闭合误差绝对值 `5.515377043963099e-11`。service/worker `5865.956/5795.536 s`；RSS/cgroup peak `13,142,904,832/13,865,336,832 B`，swap `0 B`，自然 exit `0`、后代清空。历史身份覆盖仍 incomplete：37 个 observed child identity 中只有 36 个进入成员采样；唯一差集 `(480380, 351446618)` 角色未知、无 per-PID RSS 证据。 | [训练结果与身份核验](training_results_v2.md)、[身份差集收据](../../../benchmarks/artifacts/task44_owned_member_gap_review_20261102/train011_identity_coverage_difference_20261102.json) |

train_011 的派生身份对账保留原 `process_tree_identity_coverage=incomplete_or_not_sampled` 与 `observed_child_identity_coverage=incomplete`。1,071 条资源快照各自身份完整且状态可读；唯一未配对身份只出现在 elapsed `5789.447126599029 s` 的 live/unreaped PID 列表，未出现在 members，角色 unknown、未测得该 PID 的 RSS。进程树 RSS 仅作采样峰值报告，不能解释为该短暂 PID 的 RSS 已测。

2026-11-01 的 B6 `boundary_plane` 参考面对照是第 6/12 次资格尝试。它在 CPU11 邻核 Gate 于 851.931 s 报出新窄 affinity claim 后受控停止；service wall 为 868.733 s，任务 RSS/cgroup 峰值分别为 5,052,604,416 B 和 5,277,028,352 B，swap 为 0。无真残差或官方功率输出，局部凝聚内部停止位置未知，不能分类为数值失败。Task44 与 Task40 并行已获用户明确授权；Task44 自身仍一次运行一个正式算例。完整首因和证据 hash 见 [B6 terminal receipt](b6_boundary_plane_controlled_stop_20261101.md)。
2026-11-01 的 B7 `boundary_plane` 参考面对照是第 7/12 次资格尝试。watchdog 在 elapsed 1125.154 s 因 CPU17 邻核 Gate 首次发现 PID 201653（parent 201652，start ticks 342958624，affinity `[17]`）而受控停止；service wall 1143.095 s，systemd CPU time 18 min 49.771 s，同时进程树 RSS 峰值 5,056,647,168 B、cgroup memory peak 5,282,217,984 B、cgroup swap 0。没有 residual 或 official R/T/A，不能分类为数值失败。主控之后观察到同一 PID/start 的 affinity 变为宽 mask；这不反证 stop sample，也不证明任务归属。详见 [B7 terminal receipt](b7_boundary_plane_controlled_stop_20261101.md)。
2026-11-01 的 B8 `boundary_plane` 对照是第 8/12 次资格尝试。elapsed 1171.672 s 首次在 CPU22 发现 PID 222707（parent 222706，start ticks 343385335、`recovery_diagnosis.py`、affinity `[22]`）的稳定窄核 claim；15 秒复核在 deadline 后约 1.273 s 才被采样判为 timeout，worker 子树的首个 SIGKILL 在首次冲突后 16.297 s。service wall 1206.285 s、systemd CPU 1194.324 s、进程树 RSS/cgroup peak 4,901,117,952 / 5,288,030,208 B、任务 swap 0。运行期 grace/release 记录显示 `performance_not_isolated=true`，启动回执 false 只代表启动时尚无冲突。没有 residual、official R/T/A 或数值结果文件；B8 是受控监控停止，不是数值失败。首个 PID/start identity 后来以宽 affinity 再现，不反证先前的窄核样本。详见 [B8 terminal receipt](b8_boundary_plane_monitor_grace_timeout_20261101.md)。

另有一次不计入精度资格复算预算的 `global_z` phase-gauge selector 诊断（fresh5）。它完成 27 格网格、P6 基函数和 420 个端口模态的矩阵组装、MUMPS 因子分解与线性系统求解；随后 worker 在写出可审计数值结果前，被 CPU 邻居监控的进程身份 Gate 受控停止。候选 `cc1` 的 `/proc/51758/stat` 读取返回 `ENOENT`；旧 Gate 后续虽调用 `Path.exists()`，但没有保留该检查结果或 errno，因此“编译子进程刚好退出”只是可能解释，未由当时证据确认。没有完整真残差、official R/T/A 或 `result.json`；这不是求解器数值失败，也不是内存门停止。fresh5 当时的正式 attempt 为 `5/12`，且不计入后续计数；当前 `12/12` 由 B9–B12 执行段结清。完整紧凑记录和原始文件 SHA 见 [`fresh5 controlled-stop record`](fresh5_controlled_stop_20261031.json)；原始目录保留在 `/tmp/task44-phase-gauge-global-fresh5-20261031`。

### 2026-11-01 B9–B12 boundary-plane 执行与额度结清

批准的监控修复（`9fc3728f`、`95087dae`）规定：运行期外部 claimant 以 PID/start ticks 作为身份键；PPID、comm 变化及外部生命周期信息缺失作为性能隔离诊断，记录 `performance_not_isolated=true` 后继续。运行期全用户 `list-units` inventory 失败可在精确 owned unit 身份仍通过时容忍；启动期 inventory 仍须严格成功。Task44 自身 unit/Invocation、主 PID/start ticks、cgroup、affinity、内存与 swap 硬门失败仍停止。此规则覆盖 B6–B8 的“发现 claim 即停”与 15 秒复核行为。B9–B11 保留为旧监控器产生的监控受控停止，不能改写为数值负结果或成功结果。

| Attempt | 运行与资源实测 | 结果分类与具体边界 |
|---|---|---|
| B9 | service wall `3688.507526768837 s`；进程树 RSS / cgroup peak `7,955,501,056 / 8,586,076,160 B`；swap 0 | `MONITORING_FAILED / not_run`。CPU9 上两次外层 owned-member 快照均含同一 PID/start 的 `cc1`，但内层 membership 结果为 false，旧监控器据此拒绝 claim。内层 listing/syscall 时序没有保存，具体竞态机制未证实。无 residual 或 official R/T/A。证据：`benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b9-r1-20261101.service/` 与 [run summary](../../../results/task44_boundary_plane_attempt9/task44_sixlayer_0p7nm/sample_B_boundary_plane_20261101_attempt9__full3d_direct__mpi1__Mna/20261101T074434.221630Z/run_summary.json)。 |
| B10 | service wall `922.6288379072212 s`；进程树 RSS / cgroup peak `5,034,360,832 / 5,278,961,664 B`；swap 0 | `MONITORING_FAILED / not_run`。候选 PID 的 PID/start、cgroup 和 affinity 稳定，PPID 变化触发旧 frozen-parent 检查；不属于 generic unknown identity。无 residual 或 official R/T/A。证据：`benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b10-r1-20261101.service/` 与 [run summary](../../../results/task44_boundary_plane_attempt10/task44_sixlayer_0p7nm/sample_B_boundary_plane_20261101_attempt10__full3d_direct__mpi1__Mna/20261101T090718.653646Z/run_summary.json)。 |
| B11 | service wall `619.4444286893122 s`；进程树 RSS / cgroup peak `4,894,605,312 / 5,288,202,240 B`；swap 0 | `MONITORING_FAILED / not_run`。首次触发是一次 `systemctl list-units` 错误；之后独立的 `systemctl show` 也报错。不是两次 `list-units` 错误。最终清理回执确认子树已清空。无 residual 或 official R/T/A；属于监控/服务查询失败，不是数值失败。证据：`benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b11-r1-20261101.service/` 与 [run summary](../../../results/task44_boundary_plane_attempt11/task44_sixlayer_0p7nm/sample_B_boundary_plane_20261101_attempt11__full3d_direct__mpi1__Mna/20261101T093652.424155Z/run_summary.json)。 |
| B12 | service wall `2806.5004601851106 s`；worker `2727.062757624779 s`；进程树 RSS / cgroup peak `7,891,423,232 / 8,588,120,064 B`；swap 0 | `official_result=true`；完整真残差与能量门通过。B12 是 12/12。详细数据见下表。 |

B12 的正式 run 身份为 source SHA `dab67e47cc1feb7da1bc1018cae66e1d18b93ff5`、input SHA-256 `7c96752bd34cba4c33562e761b93854e92b989fd63952a3fa5c1c33d84e6a643`、physical-model SHA-256 `d97fe809c536ba0c73439cef4da855c636dc41b8fc3805a95a9e81d21678b131`、resolved-config SHA-256 `2a0e38709530ecb584f7b6510de1f3967a8c66e9702b6695e64a2272ac4b098c`。样本目录：`results/task44_boundary_plane_attempt12/task44_sixlayer_0p7nm/sample_B_boundary_plane_20261101_attempt12__full3d_direct__mpi1__Mna/20261101T110836.357672Z/`。网格为 P6 `[3,6,8]`、144 hex；全 FE DoF `99,894`、active trace rows `29,808`、DtN auxiliary rows `160`、矩阵 NNZ `24,315,568`；每侧 80 个 DtN 模态。

| 正式量 | B12 measured | Gate / 解释 |
|---|---:|---|
| full explicit true residual（relative） | `8.169724140477284e-10` | `≤1e-6`，pass |
| `R_total` / `T_total` | `0.09521909449777169` / `0.8831311299149318` | 完整传播 DtN 端口功率 |
| `R00_s` / `R00_p` / `R00_total` | `0.09521864873059795` / `1.0432294028174373e-23` / `0.09521864873059795` | `R00_total=R00_s+R00_p` |
| `A_balance` / `A_volume_total` | `0.021649775587296527` / `0.021649774816315158` | 端口吸收与材料体积吸收 |
| `R+T+A_volume−1` | `−7.709813898415518e-10` | `abs(·)≤1e-5`，pass |

与已有 B `global_z` 基线相比，B12 的 `ΔR_total=+2.42119e-12`、`ΔT_total=+7.654e-12`、`ΔR00_total=+2.42085e-12`。这是一项 B 点、当前模型与网格上的实测锚点；不能从它推断其他厚度或网格的全源码数值等价。y 和空气距稳定性失败仍有效；历史 DtN residual 失败代表截断稳定性未获证明，但继续扩展已由用户取消；z 单向通过不代表整体精度通过。该结论仅保留旧版 A–D 的历史资格字段 `gp_eligible=false`，不适用于后续 v2 训练样本。

### B12 输出文件离线核验

`airbox_fields_3d_scientific.npz` 能由 NumPy 读取，size `685,195 B`，SHA-256 `cbb0f0acaf8d22bce73a698e146a166de45508a7670c048fa874fef328c2b494`。坐标为 `(3888,3)`，点和单元数组尺寸与 144 hex 对应；`E_total_code`、`E_total_V_per_m`、`H_curl_A_per_m` 为 `(3888,3) complex128`，Poynting 为 `(3888,3) float64`，其余标签、类型、mask 和入射 E 数组均符合记录维度，数值数组全为有限值。NPZ 不自带 source/input SHA；本次绑定依赖唯一 RUN 目录内的 `run_manifest.json`、`run_summary.json`、输入/配置身份与 NPZ 文件 SHA，并且 NPZ 元数据中的 `boundary_plane`、参考面 `[-0.5,5.0] nm`、MPI1、144 cells、3888 points 与该 RUN 相符。

E `.bp` 目录存在且成员已逐个 hash：tree SHA-256 `efc9e6cae3b02684d64ea0cdcd8bb632d84513d7c272c4d99b3fa9eed3b2ca89`，`data.0` SHA-256 `a260a90fdc12df68e5874137628f1ead43c3814bbb87969b64d14b85871ad01a`。H `.bp` tree SHA-256 `20e823ff63e4b564c36b97fdc8315e062d52d5e13fb2ef69e74c7648cb32bde8`，`data.0` SHA-256 `372060bfc65f8b0387ed0dbc463d2829e9cbce1c89cf49a3f3a835a503557e9f`。当前环境没有可用的 ADIOS2 Python reader 或 `bpls`；本机 C++ 读者编译又缺少 `ADIOSConfig.h`。因此这些 BP 只证明文件存在且 hash 固定，E/H 数组解码、维度和有限性状态是 `pending`，不得写成回读通过；不安装包、不增加读取框架。

### 运行期 CPU 共享政策与额度

当前政策是：启动仍须通过 fresh CPU/邻任务/ABI/资源准入；正式运行期间外部 claimant 以 PID/start ticks 为身份键。PPID/comm 变化和外部 lifecycle 元数据不可读记为诊断，允许继续并记录 `performance_not_isolated=true`。运行期 `list-units` inventory 错误可在精确 owned unit 仍可核验时容忍；启动期 inventory 严格检查。Task44 自身 unit/Invocation、主 PID/start ticks、cgroup、affinity、内存/祖先余量和 swap 硬门仍须通过；OOM 仍停止。此规则覆盖 B6–B8 的旧“立即停止/15 秒复核”行为。

B9、B10、B11 的 service-summary SHA-256 依次为 `5e3a4efd491b52e8b76c1dbfe2c00f58803ef847fddc26b8491c4d3adeee5d66`、`1bd1d65be2fae519653d1eb39d1318bcdf3fb974dbdf57fdfca1d1eef0e64122`、`f0209038d799aac64f03e1c551deacfb435ee23276f09a0f92d4bb75dda1336e`。B12 service 为 `task44-sample-boundary-plane-b12-r3-20261101.service`，Invocation `7f7b6407725d44188e3068d53b64cedf`，完成且退出 0，进程清理通过。B12 的 pre-admission r1 因 CPU selector 读取 PID 298254 失败且后续进程已消失，未启动 service；r2 未找到 busy fraction 严格小于 20% 的核，也未启动 service。两次都没有 PDE 计算或结果目录，不计入额度。原始 admission receipt `/tmp/task44_b12_admission_failures_20261101.json` 的 SHA-256 为 `7cd601366509671c088e260b6913dcb59fb6973b0ad6d3d96ae713c2c4cf62aa`。至此 B9–B12 完成预算中的第 9 至第 12 次，原额度 `12/12` 已结清。

固定 seed `440731` 的首轮 v1 设计已冻结为 20 training / 10 development / 10 blind test，见 [`sample_design_v1.json`](../sample_design_v1.json)。该旧版训练候选含 A–D 和 16 个六维分层覆盖点；旧版 A–D 字段为 `gp_eligible=false`，不代表后续 v2 样本的标签。40 个几何输入字节、解析物理模型和离散签名哈希已登记，未求解候选的结果保持 `null`。开发和盲测几何均不与训练重合；盲测样本没有标签字段。GP 软件已通过 9 项定向测试和 40 点设计校验；有限元训练、模型选择、开发评估、盲测和标准尺寸仍为 `not_run`。

## 阶段与负结果

| 对象 | 模型 / 方法 | 状态与数据身份 | 结果和边界 | 证据 |
|---|---|---|---|---|
| 旧 A 全局 direct | A 厚度，P6，144 hex，`standard_full` | `controlled_stop`；物理结果 `not_run` | 8433.239279829897 s 后按用户要求停止；watchdog exit `-15`，cgroup 清空。旧 `run_summary.json` 保持 `launching / not_run / null`，不算求解器数值失败 | `benchmarks/artifacts/task44_native_services/task44-sample-a-dynamic2.service/user_controlled_stop.json` |
| 首次凝聚 A 缓存启动 | A 厚度，凝聚 direct | `worker_nonzero`；物理结果 `not_run` | 31.9605 s 后共享旧 FFCx C 文件 JIT 编译超时；未装配或求解。原共享缓存和 run 目录保留 | `benchmarks/artifacts/task44_native_services/task44-sample-a-condensed.service/` |
| 正式样本 A–D | 六层缩尺结构，P6、3×6×8、双 Floquet、完整自动传播 DtN、静态凝聚 + `mumps_exact` | `completed`；`official_result=true`；`measured` | 四场均通过真残差、能量闭合、MUMPS 控制读回、零任务 cgroup swap 和清场门。统一结果见下表；精度资格仍未通过，y 加密对照变化超限 | 各输入和 run summary 见下表；service 记录位于 `benchmarks/artifacts/task44_native_services/task44-sample-{a,b,c,d}-condensed-cachefix.service/` |
| y 传播方向加密首次启动 | 以 B 为基线，网格从 `[3,6,8]` 改到 `[3,12,8]` | `MONITORING_FAILED`；数值结果 `not_run` | 21.729 s 后监控观察到 PID 4168233、4168234、4168235 的身份未稳定，整棵子树已清理。worker 建出 3×12×8、288 格网格并选择 MUMPS，但没有矩阵组装、解或 R/T/A。不是数值或容量失败；后续 retry 结果见下一行 | `benchmarks/artifacts/task44_native_services/task44-sample-accuracy-yrefine.service/service_summary.json`、`watchdog/worker.log` |
| y 传播方向加密 retry | 以 B 为基线，`[3,6,8]` → `[3,12,8]`；P6、288 hex、MPI1、CPU8、static condensation + MUMPS | 求解和闭合 `pass`；空间稳定性 `failed` | `R/T/R00` 绝对变化分别为 `9.8002e-4 / 9.2275e-4 / 9.8001e-4`，均超过 `2e-4`。保留 measured 结果，不把 B 的 GP 标签标成 eligible | [run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_propagation_y2_20261031__full3d_direct__mpi1__Mna/20261031T091904.310578Z/numerical_output/run_summary.json)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-yrefine-retry1.service/service_summary.json) |
| 材料内部 z 加密 | 以 B 为基线，`[3,6,8]` → `[3,6,16]`；P6、288 hex、MPI1、CPU29、static condensation + MUMPS | 求解、闭合、z 稳定性 `pass` | 三项主输出相对 B 的绝对变化均约 `1e-10`，远小于 `2e-4`；该比较不证明 y 方向或连续解已收敛 | [run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_layer_z2_20261031__full3d_direct__mpi1__Mna/20261031T102657.088710Z/numerical_output/run_summary.json)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-zrefine1.service/service_summary.json) |
| DtN 倏逝模态扩展 | B 的 P6、[3,6,8] 网格；手动 DtN 上限 m=4、n=8；auxiliary 装配；static condensation + MUMPS exact | 数值失败；official_result=false；R/T/A not_run | 显式相对残差 1.623574709e11，对照限值 1e-6；无可用 R_total、T_total、R00_total，不能判断模态截断稳定性 | [输入](../../../input/task44_accuracy_dtn_evanescent_shell_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_dtn_evanescent_shell_20261031__full3d_direct__mpi1__Mna/20261031T110232.922585Z/numerical_output/run_summary.json)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-dtn-shell1.service/service_summary.json) |
| 顶部空气间距 | 0.5 → 1.0 nm；底面固定 `z=-0.5 nm`，z 网格 `[3,6,8]` → `[3,6,9]`，144 → 162 cells | `abs(ΔR_total)=2.34999e-4`；`abs(ΔT_total)=2.28409e-4`；`abs(ΔR00_total)=2.35003e-4`，目标均 ≤ `2e-4` | full true residual 与能量闭合通过；三项变化均超限，空气间距稳定性失败；A–D 仍不具备 GP 资格 | [输入](../../../input/task44_accuracy_air_gap_1nm_v1.dat)、[response v7](../response_v7.md) |
| fresh5 `global_z` phase-gauge selector 诊断 | 27 hex、P6、19,494 个完整 DoF、1,350 Floquet 约束、420 个端口模态；静态凝聚系统 6,414 行、4,935,930 used NNZ；MUMPS 因子 14,236,514 entries | 矩阵组装、因子分解和线性系统求解已完成；`2026-10-31T15:11:17.933053Z` 因 `/proc/51758/stat` 的身份读取 Gate 受控停止，task cgroup 峰值 `3,584,311,296 B`，swap `0 B` | 仅为 selector/gauge 诊断，不计入 12 次精度 attempt；没有 full true residual、official R/T/A 或 `result.json`；不分类为数值失败 | [紧凑记录与 raw evidence SHA](fresh5_controlled_stop_20261031.json)，原始文件保存在 `/tmp/task44-phase-gauge-global-z-fresh5-20261031` |
| B 参考面相位对照 B6 | B 厚度、P6、`[3,6,8]`、160 DtN 模态、静态凝聚 + MUMPS 不变，仅采用 `boundary_plane` gauge 和新 run/output identity | `controlled_stop / MONITORING_FAILED`；数值结果 `not_run` | 851.931 s 时 CPU 邻核 Gate 发现新窄 affinity claim（PID 189961，parent 189960，CPU11）；stop_event 的 `grace_seconds=10` 字段之后约 27 μs 即对 Task44 子树 SIGKILL。service wall 868.733 s、CPU 855.593 s；RSS 峰值 5,052,604,416 B、cgroup peak 5,277,028,352 B、swap 0；无 residual 或 official R/T/A | [B6 terminal receipt](b6_boundary_plane_controlled_stop_20261101.md)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b6-r1-20261101.service/service_summary.json)、[watchdog resources](../../../benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b6-r1-20261101.service/watchdog/resources.jsonl) |
| B 参考面相位对照 B7 | B 厚度、P6、`[3,6,8]`、160 DtN 模态、静态凝聚 + MUMPS 不变，采用 `boundary_plane` gauge 与新运行身份 | `controlled_stop / MONITORING_FAILED`；数值结果 `not_run` | elapsed 1125.154 s 首次触发 CPU17 邻核 Gate：PID 201653、parent 201652、start ticks 342958624、`run_convergence.py` affinity `[17]`。service 1143.095 s，CPU 18:49.771，RSS/cgroup 峰值 5,056,647,168 / 5,282,217,984 B，swap 0；无 residual、official R/T/A | [B7 receipt](b7_boundary_plane_controlled_stop_20261101.md)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b7-r1-20261101.service/service_summary.json)、[watchdog resources](../../../benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b7-r1-20261101.service/watchdog/resources.jsonl) |
| B 参考面相位对照 B8 | B 厚度、P6、`[3,6,8]`、160 DtN 模态、静态凝聚 + MUMPS 不变，采用 `boundary_plane` gauge 与新运行身份 | `controlled_stop / MONITORING_FAILED`；数值结果 `not_run` | elapsed 1171.672 s 首次触发 CPU22 邻核 Gate：PID 222707、parent 222706、start ticks 343385335、`recovery_diagnosis.py` affinity `[22]`。复核 deadline 为 15 s；timeout 样本在首次发现后约 16.273 s，SIGKILL 在 16.297 s。service wall 1206.285 s、CPU 19:54.324，RSS/cgroup 峰值 4,901,117,952 / 5,288,030,208 B，swap 0；运行期 `performance_not_isolated=true`。无 residual、official R/T/A | [B8 receipt](b8_boundary_plane_monitor_grace_timeout_20261101.md)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b8-r1-20261101.service/service_summary.json)、[watchdog resources](../../../benchmarks/artifacts/task44_native_services/task44-sample-boundary-plane-b8-r1-20261101.service/watchdog/resources.jsonl) |
| GP与样本设计软件 | 20/10/10 固定划分；Matérn 5/2 ARD三输出 GP、均值和线性基线 | 软件 `verified`；有限元 GP `not_run` | 40个几何互不重复；旧版 v1 的 A–D 字段仍待精度资格判定；未求解候选结果为空；开发/盲测没有标签泄漏 | [`sample_design_v1.json`](../sample_design_v1.json)、`src/studies/task44_surrogate.py`、`src/test/test_task44_surrogate.py` |
| 有限元训练扩充 / 开发评估 / 最终盲测 / 标准尺寸 | 原任务后续阶段 | `not_run` | 旧版 A–D 没有通过 y/空气稳定性资格；四个正式 worker 用时约27.6–30.6分钟，先完成有限核查与合法缓存成本证据，再按实测调整批量。该历史结论不覆盖冻结 v2 训练样本的独立标签 | 本 summary 的下一步决策 |

## A–D 统一数值结果

A–D 的六层厚度分别为全 0.5、全 0.75、全 1.0 nm 和交替 0.5/1.0 nm。静态凝聚在每个六面体内部消去不与邻单元共享的自由度，先解较小的全局迹与端口系统，再恢复完整电磁场；这样减少全局系统的行数，但增加局部矩阵处理、场恢复和全算子残差检查的工作。表中 `R_total`、`T_total` 来自全部传播 DtN 模态；`A_balance` 来自端口功率差，`A_volume` 来自材料体积吸收积分。`R00_s/p/total` 是反射零级的 S、P 分量及其和。

| 样本 / 六层厚度 (nm) | `R_total` | `T_total` | `R00_s` | `R00_p` | `R00_total` | `A_balance` | `A_volume` | full true residual | `R+T+A_volume−1` | 数据身份 / 证据 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A / 0.5×6 | 0.10377060655595945 | 0.8800846265279674 | 0.10376987725348902 | 6.570154036905706e-22 | 0.10376987725348902 | 0.01614476691607314 | 0.016144766075562058 | 7.584367086899987e-10 | -8.405111051601466e-10 | `measured`；[输入](../../../input/task44_sample_a_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_A_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T055027.974554Z/numerical_output/run_summary.json) |
| B / 0.75×6 | 0.0952190944953505 | 0.8831311299072778 | 0.0952186487281771 | 5.011182975657206e-24 | 0.0952186487281771 | 0.02164977559737169 | 0.02164977481611931 | 7.333002340121292e-10 | -7.812523961092666e-10 | `measured`；[输入](../../../input/task44_sample_b_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_B_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T063009.557323Z/numerical_output/run_summary.json) |
| C / 1.0×6 | 0.08581651094067945 | 0.8877015737613739 | 0.08581582462769617 | 3.901928348820551e-21 | 0.08581582462769617 | 0.026481915297946634 | 0.026481914592266717 | 6.580098648397804e-10 | -7.05679958912242e-10 | `measured`；[输入](../../../input/task44_sample_c_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_C_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T070135.788196Z/numerical_output/run_summary.json) |
| D / 0.5,1.0,0.5,1.0,0.5,1.0 | 0.09358123207431406 | 0.8803289446256277 | 0.09358070870418612 | 1.213549477479837e-23 | 0.09358070870418612 | 0.026089823300058268 | 0.026089822597639773 | 5.119574895162806e-09 | -7.024184567328007e-10 | `measured`；[输入](../../../input/task44_sample_d_condensed_direct_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/sample_D_condensed_direct_20261031__full3d_direct__mpi1__Mna/20261031T073200.895421Z/numerical_output/run_summary.json) |

四个 `R_total/T_total/R00_total/A_volume` 都是非负有限值；端口吸收与体积分吸收相符，闭合误差绝对值都小于 `1e-9`，远低于 `1e-5` 门限。full true residual 使用恢复后的完整场：对迹/DtN 部分显式作用，并对被消去的单元内部空间用 matrix-free UFL 作用，连同完整 RHS 一并计算；没有把 MUMPS 内部状态或 `solver_residual_norm=0` 当作 true residual。

### B 的 y 加密结果：内部求解通过，空间稳定性未通过

这项计算只把传播方向 y 的单元数从 6 增至 12，其余物理模型、P6、DtN 模态、MPI1、静态凝聚和 MUMPS 设置沿用 B。网格由 144 增至 288 个贴体六面体。求解器将完整场的显式相对真残差控制在 `1.275136723e-9`，低于 `1e-6`；端口功率与材料体吸收的闭合误差为 `-3.946687421e-11`，低于 `1e-5`。但与 B 相比，三个主输出变化都超出 `2e-4`，说明当前离散选择还没有在 y 方向达到任务要求的稳定程度。这个差异不能归因于残差或能量不守恒，也不能据此宣称更细的网格已收敛。

| 对照 | `R_total` | `T_total` | `R00_s / R00_p / R00_total` | `A_balance / A_volume` | 相对 B 的有符号差值 | 判定 |
|---|---:|---:|---|---|---|---|
| B，`[3,6,8]` | 0.0952190944953505 | 0.8831311299072778 | 0.0952186487281771 / 5.011182975657206e-24 / 0.0952186487281771 | 0.02164977559737169 / 0.02164977481611931 | 基线 | measured；基线 solve/closure pass |
| B 的 y 加密，`[3,12,8]` | 0.09619911407616114 | 0.8822083809416161 | 0.09619866247638499 / 1.0699952159268371e-21 / 0.09619866247638499 | 0.02159250498222276 / 0.021592504942755907 | `ΔR=+9.800195808e-4`；`ΔT=-9.227489657e-4`；`ΔR00=+9.800137482e-4` | 三项绝对变化均大于 `2e-4`；空间稳定性失败，不能据此将 B 标签标为 `gp_eligible` |

R/T 和 `R00` 取自完整 DtN 端口模态主结果；场上的 Fourier 和采样通量只作诊断，不代替主功率。加密 run 的输入 SHA-256 为 `272312c4e0b997fbf40649c4d3be678a9cd38efe229f3b3d61fddc5fa0656269`，物理模型 SHA-256 为 `b16f8d783eb85069c530194e246ea88c691d011411892771f93a0c6111224886`，source SHA 为 `5a89ca1652fbe721f4d0ecf8cef9fc7ea276d92a`。完整自由度数为 `197,994`；独立迹行 `59,616`，加上 160 个 DtN auxiliary 行后，实际求解系统为 `59,776` 行。该 run summary 未记录凝聚矩阵的最终 NNZ，故不估算或补写 NNZ。

### B 的 z 加密结果：求解与 z 稳定性通过

该对照只把材料内部的 z 网格段数从 8 增至 16，其他材料、几何、端口条件、P6、静态凝聚和 MUMPS 设置沿用 B。单元数从 144 增至 288；完整 DtN 端口模态仍作为 R/T 主结果。输入配置比较确认，唯一的物理数值设置变化是 z 网格段数。该试验检查材料层厚度方向的离散敏感性，不是连续解精度证明。

| 数值量 | B：`[3,6,8]` | z 加密：`[3,6,16]` | z−B 有符号变化 | 判定 |
|---|---:|---:|---:|---|
| `R_total` | 0.0952190944953505 | 0.0952190943990193 | -9.633120690e-11 | `abs(Δ)≤2e-4` |
| `T_total` | 0.8831311299072778 | 0.8831311298228821 | -8.439571264e-11 | `abs(Δ)≤2e-4` |
| `R00_total` | 0.0952186487281771 | 0.09521864862777846 | -1.003986477e-10 | `abs(Δ)≤2e-4` |
| `R00_s / R00_p`（z 加密） | — | 0.09521864862777846 / 9.543330210210267e-23 | — | `R00_total=R00_s+R00_p` |
| `A_balance / A_volume`（z 加密） | — | 0.021649775778098568 / 0.02164977501620309 | — | 端口吸收与体积分吸收闭合 |
| 全显式算子相对真残差 | — | 4.64908820597943e-10 | — | `≤1e-6`，pass |
| `R+T+A_volume−1` | — | -7.61895435630322e-10 | — | `≤1e-5`，pass |

三项功率变化均远小于任务门限，表示 z 向加密对这三个输出没有可见影响。它不能解释旧版 y 对照的大变化，也不能据此更改旧版 A–D 的历史 `gp_eligible=false` 字段；该历史资格结论不覆盖后续 v2 样本标签。

| 身份 / 成本项 | 记录 |
|---|---|
| Run / service / Invocation | `task44_accuracy_layer_z2_20261031` / `task44-sample-accuracy-zrefine1.service` / `2328dc0df7f94e16a4305010eaccb054` |
| CPU / service cap / 输入 SHA-256 / 物理模型 SHA-256 / source SHA | CPU 29 / 137,438,953,472 B（128 GiB）/ `6c55c599439fee0963f529025873549c9418fd08884767d4a14109d920660c0e` / `21f035163b3f875f916f9560bdfc778f871c56f0b2875023a8211825ac085f19` / `a10ece015bb311489d0dc4a977a197e1da2df90f` |
| 网格 / 自由度 / 实际系统 | 288 hex，P6；198,438 个完整 Nédélec DoF；58,320 个迹行 + 160 个 DtN auxiliary 行 = 58,480 行 |
| 矩阵 NNZ | 48,157,036 used NNZ（run summary 记录） |
| numerical run summary / service 全生命周期 | 1,651.694 s / 1,716.819 s；worker wall 未单独记录 |
| Stage 4 / DtN build / direct solve / full residual | 1,620.108 s / 1,262.984 s / 0.862 s / 114.007 s |
| process-tree RSS 峰值 / cgroup memory 峰值 | 10,121,396,224 B / 10,965,905,408 B；分别为同时进程树 RSS 采样与内核 cgroup peak |
| swap / 监控 / 清场 | cgroup 与进程树 swap 峰值均为 0；resource authority 4,670 次采样且无 warning；1,346 次身份采样完整；`descendants_cleared=true` |
| 关键证据 SHA-256 | numerical run summary `a37e4b03cba2e9752e3146c320e21b0520d7e56f865c0f1b6cddb89314caada8`；DtN power metrics `1e66d971db95cb15740c2874859c9fce14c26d229a962ddb7e76c146eb159c0c`；service summary `a1cf9cde125a0b680f8b46af493544bbac85729538f0c65842091aae9a643696` |

此任务运行标记 `official_result=true` 表示 worker 的完整离散求解和数值门结果可用；同时 `physical_benchmark_candidate=false`、`validation_role=numerical_sanity_only`，所以不把 z 对照当作新训练标签。MUMPS 控制读回与 service completion receipt 通过。详情见 [`response_v5.md`](../response_v5.md)、[run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_layer_z2_20261031__full3d_direct__mpi1__Mna/20261031T102657.088710Z/numerical_output/run_summary.json) 和 [service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-zrefine1.service/service_summary.json)。

### B 的 DtN 倏逝模态扩展：显式真残差门失败

DtN 端口用边界上的模态关系表示空气和基底半空间中的出射场。倏逝模态不把功率带到远处，但会影响结构附近的场；扩大模态范围，是为了检验把有限边界替代半空间时是否漏掉重要近场分量。本次在 B 的 P6、[3,6,8] 网格上增加手动阶次壳层 m=4、n=8，使用 auxiliary 装配。输入中的 diffraction_order_max_n 从 7 改到 8、diffraction_sample_count_y 从 15 改到 17，是输出报告采样设置变化。

这次求解器返回了向量，但恢复完整空间中的显式系统残差极大，因而没有得到可采信的物理功率结果。B 基线的 R_total、T_total、R00_total 分别为 0.0952190944953505、0.8831311299072778、0.0952186487281771；DtN 对照没有对应的 official 数值，不能计算三项变化，也不能据此判定 DtN 模态范围是否稳定。

| 检查项 | 判据 / 含义 | 实测结果 | 判定 |
|---|---|---|---|
| 完整线性系统相对真残差 | 不超过 1e-6 | 残差范数 209779683028.43216；RHS 范数 1.2920851858750981；两者相除重算为 162357470948.29 | failed；约为限值的 1.62e17 倍 |
| PETSc KSP 状态 | 只作求解器诊断 | preonly 报告 CONVERGED_ITS、1 次迭代、内部 residual norm 为 0；显式全系统残差仍为 1.62e11 | 显式 Gate 失败，不能按内部状态记为 solver pass |
| official R/T/A 与闭合 | 仅从通过真残差门的场计算 | postprocess_skipped=true；没有有限 R_total、T_total、A_volume_total；能量闭合未计算 | not_run；没有 R/T/R00 对照差值 |
| 离散规模 | 完整 H(curl) DoF 与凝聚后系统分开报告 | 99,894 个完整 Nédélec DoF；29,808 个迹行 + 612 个 DtN auxiliary 行 = 30,420 行；25,143,076 used NNZ | measured |

数值摘要将该计算分类为 failed_stage4_true_residual_gate，official_result=false，physical_benchmark_candidate=false。异常大的残差说明该线性系统解不满足任务规定的精度门；当前证据没有定位产生该残差的具体原因，因此本轮不作根因判断，也不把这些数据作为代理标签。

| 身份 / 资源项 | 记录 |
|---|---|
| Run / service / Invocation | task44_accuracy_dtn_evanescent_shell_20261031 / task44-sample-accuracy-dtn-shell1.service / 4f142c76cd4041eea9755bdbb762e288 |
| 输入 / 物理模型 / source SHA | f9b05549ca72a0f99bba1083f7fefb62b61ea057c0c77a4c1a7d6f31b3554c99 / 324e2d311fb41127bccd4ba32058507cd874911ec75cfe965732f9c97fe9d006 / b390bc11e3df855c24b7fbcebfab9459c8923ad8 |
| 资源准入 | CPU 8；128 GiB cgroup cap、零 swap；启动时 MemAvailable 2,102,490,845,184 B，扣除 412,316,860,416 B reserve 后余 1,544,145,096,704 B |
| 耗时 | numerical run summary 1,891.633 s；Stage 4 端口装配与求解 1,884.331 s，其中 KSP setup 42.850 s、直接求解 0.699 s；service 全生命周期 1,912.940 s。worker wall 未单独记录 |
| 内存 / swap | watchdog 同时进程树 RSS 峰值 8,085,782,528 B；专属 cgroup memory peak 8,921,956,352 B；进程树和 cgroup swap peak 均为 0 B |
| 监控 / 清场 | resource authority 5,125 次采样、无 warning；进程身份 1,481 次完整采样；cgroup swap 353 次采样且通过；service 为 WORKER_FAILED，descendants_cleared=true，剩余子 PID 为空 |
| 证据 SHA-256 | numerical run summary 83a011943ab0920142cc796c2cd22061b286e1efbeeaadedb7b6faf00de91e65；外层 run summary 875d8c14a54323180c816b81db658d418b236d80d12f152ca070944e930368d9；service summary ec739e568a2d4c3dae78b87c11de68cbf3d19737a814346024c6212a2365529f；watchdog summary 7bae79c89608a91924f6feeed3876b8f8fd1024a18fd210969a7c22871bfdb30 |

完整证据见 [numerical run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_dtn_evanescent_shell_20261031__full3d_direct__mpi1__Mna/20261031T110232.922585Z/numerical_output/run_summary.json)、[外层 run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_dtn_evanescent_shell_20261031__full3d_direct__mpi1__Mna/20261031T110232.922585Z/run_summary.json)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-dtn-shell1.service/service_summary.json)、[watchdog summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-dtn-shell1.service/watchdog/summary.json)、[progress log](../../../results/task44_sixlayer_0p7nm/task44_accuracy_dtn_evanescent_shell_20261031__full3d_direct__mpi1__Mna/20261031T110232.922585Z/numerical_output/progress_3d.jsonl)、[worker output](../../../results/task44_sixlayer_0p7nm/task44_accuracy_dtn_evanescent_shell_20261031__full3d_direct__mpi1__Mna/20261031T110232.922585Z/worker_stdout.txt) 和 [输入](../../../input/task44_accuracy_dtn_evanescent_shell_v1.dat)。

截至 B8 收口时，精度资格最多 12 次额外 attempt，已登记 8 次、剩余 4 次。该历史快照包括两次 y attempt（一次监控失败、一次稳定性超限）、一次 z 通过、一次 DtN 真残差失败、一次空气间距稳定性超限，以及 B6–B8 三次 boundary-plane 监控停止。B8 的 15 秒复核与当时“不自动进入 B9”安排已被后续运行期 CPU 共享政策覆盖；B9–B12 的最终计数和首因见本 summary 前面的更新执行段。y、空气稳定性负结果仍有效；历史 DtN 尝试没有证明截断稳定性，用户已取消继续扩展；z 单方向通过不构成总精度通过。

GP 的 Matérn 5/2 ARD 核把相近的六层厚度组合视为更可能产生相近功率结果，并为六个厚度分别拟合影响范围；这样可以表达某一层厚度比另一层更敏感的情况。代价是要从有限训练点估计多个尺度参数，预测标准差仍只是模型内部的不确定度，不是真实误差上界。输入使用冻结的 `[0.5,1.0] nm` 范围归一化；输出均值和尺度只从训练数据取得。实现同时保留训练均值和线性拟合基线，并把误差还原到原始功率比单位。

统一离散规模为 144 个 P6 六面体、99,894 个 Nédélec DoF、29,808 个独立迹行和 160 个 DtN auxiliary 行，共 29,968 个增广求解行。上下端口各 80 个模式，A–D 当前均为传播模式；使用矩阵 `NNZ` 为 A/B/D 的 24,315,568，C 的 24,315,748。MUMPS `preonly / lu / mumps` 的 ICNTL 读回在四个样本均通过。

### 时间、内存与 swap

| 样本 | worker wall (s) | run summary elapsed (s) | service summary elapsed (s) | stage4 端口装配与求解 (s) | DtN/base build (s) | 进程树 RSS 峰值 (B) | cgroup memory 峰值 (B) | cgroup / 进程树 swap 峰值 (B) | 清场 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A | 1653.708 | — | 1740.104 | 1613.084 | 1161.224 | 7,550,930,944 | 8,337,240,064 | 0 / 0 | `descendants_cleared=true` |
| B | 1738.079 | — | 1803.805 | 1708.840 | 1381.071 | 7,677,751,296 | 8,568,664,064 | 0 / 0 | `descendants_cleared=true` |
| C | 1679.951 | — | 1749.664 | 1647.064 | 1317.490 | 7,799,111,680 | 8,586,145,792 | 0 / 0 | `descendants_cleared=true` |
| D | 1836.503 | — | 1911.111 | 1802.634 | 1424.319 | 7,827,030,016 | 8,556,298,240 | 0 / 0 | `descendants_cleared=true` |
| B 的 y 加密 | — | 3347.793 | 3417.755 | 3313.561 | 2851.534 | 12,487,163,904 | 13,289,373,696 | 0 / 0 | `COMPLETED`；9,262 次 watchdog 采样，子树清理 |
| B 的 z 加密 | — | 1651.694 | 1716.819 | 1620.108 | 1262.984 | 10,121,396,224 | 10,965,905,408 | 0 / 0 | `COMPLETED`；1,346 次身份采样，子树清理 |
| B 的 DtN 倏逝模态扩展 | — | 1891.633 | 1912.940 | 1884.331 | 未单独记录；包含在 Stage 4 | 8,085,782,528 | 8,921,956,352 | 0 / 0 | WORKER_FAILED；descendants_cleared=true |

worker wall、run summary elapsed 与 systemd service 全生命周期是不同口径，不相加。y 的 `3347.793 s` 与 z 的 `1651.694 s` 来自各自 numerical `run_summary`；`3417.755 s` 和 `1716.819 s` 是对应 service 全生命周期，不能把前者记作 worker wall。进程树 RSS 是 watchdog 在活动 PID 上采样的 RSS 总和；cgroup memory peak 是内核 cgroup 计数，二者不混称。`run_summary.json` 的 `total_peak_rss_mb` 是单 rank 历史峰值上界，不是同时峰值；PSS 在本 profile 中关闭。四个 A–D、y、z 和 DtN 的任务 cgroup 与进程树 swap peak 均为 0；y/z 子树正常清理，DtN 的 worker 因真残差门失败而非资源门退出，service 仍确认 descendants_cleared=true。C 的主机全局 swap 活动无法归因给 Task44，因此 `job_swap_activity` 标为 `UNRESOLVED`；但 C 的专属 cgroup 与进程树 swap 采样仍为 0，任务 swap Gate 通过。

### 缓存复用的范围

| 样本 | raw tensor 材料/几何类 | cell use | 同类重复复用 | 派生 kernel invocation | 独立 FFCx JIT cache root |
|---|---:|---:|---:|---:|---|
| A | 14 | 144 | 130 | 14 | `task44-sample-a-condensed-cachefix` |
| B | 17 | 144 | 127 | 17 | `task44-sample-b-condensed-cachefix` |
| C | 17 | 144 | 127 | 17 | `task44-sample-c-condensed-cachefix` |
| D | 17 | 144 | 127 | 17 | `task44-sample-d-condensed-cachefix` |

每场都使用自己的 `/tmp/myfenics-task44-native-cache-1000/<service-unit>/` 根，FFCx 子目录也由该 service 明确绑定；因此不能把 B/C/D 描述成复用了前一场的 warm JIT。raw tensor、局部 LU 和场恢复缓存只在本场建立与复用；没有跨样本复用数值矩阵、因子或端口相位。cell-form kernel invocation 数由“编译核 × 唯一材料/几何类”映射派生，不是动态 profiler 计数。每场还报告一个只读、按单元内部形状共享的 identity cache class。

#### 跨样本编译缓存的只读核查

FFCx 把变分形式和编译选项组合成模块名；同名缓存命中时会导入已生成的 Python 扩展模块。该身份键包含 FFCx 表单选项、C 编译参数和 Python ABI，但自身不含完整 Task44 源码 SHA。因此，为跨样本复用还需额外绑定源码及完整软件栈，并验证缓存文件完整，不能只凭文件名认定安全。A–D 当前都是每 service 独立缓存，没有使用跨样本 warm JIT。

| 缓存对 | 记录到相同模块名 | `.o` / `.so` 完全相同 | `.c` 完全相同 | 结论 |
|---|---:|---:|---:|---|
| B → C | 30 个模块 | 30/30，合计约 603.15 MB | 2/30 | 存在部分可复用的二进制，但不能从模块名或 C 源文件推断整库等价；未复制或启动复用 |
| C → D | 30 个模块 | 10/30，合计 337,440 B | 需进一步证据 | 仅有少量相同二进制，尚无可据此宣称的端到端加速 |

B/C/D 记录的源码 SHA 相同，preflight 的 Python 路径、complex128、PETSc int32、MPI1/OpenMPI4.1.6、DOLFINx/Basix/PETSc/SLEPc 模块路径一致。`.cached` sidecar 含原绝对 cache 路径，内容在不同 service 间不同；当前实现没有经资格化的 sidecar 迁移流程。后续只考虑以源 SHA、ABI、FFCx/UFL/Basix版本、编译器/flags和文件内容哈希共同建身份的只读种子路径，并继续为每个样本保存独立结果与服务回执。矩阵、MUMPS 因子、数值端口相位等几何相关对象不跨样本复用。

### 精度对照状态

| 对照 | B 基线与唯一改变量 | 目标输出变化门 | 当前状态 | 证据 / 下一步 |
|---|---|---|---|---|
| 传播方向 y 加密 | `[3,6,8]` → `[3,12,8]`；网格 144 → 288 cells | B 为基线：`abs(ΔR_total)=9.8002e-4`、`abs(ΔT_total)=9.2275e-4`、`abs(ΔR00_total)=9.8001e-4`；三项阈值均 `2e-4` | 求解 residual 与能量闭合 pass；三个空间差值均超限，判 `accuracy_gate_failed`，不更新 GP 标签 | 首次 attempt 的监控失败保留；retry unit `task44-sample-accuracy-yrefine-retry1.service`、Invocation `27c2f1ed195943a8a494bd87c788c70f`；[run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_propagation_y2_20261031__full3d_direct__mpi1__Mna/20261031T091904.310578Z/numerical_output/run_summary.json) |
| 材料内部 z 加密 | `[3,6,8]` → `[3,6,16]`；网格 144 → 288 cells | `abs(ΔR_total)=9.6331e-11`、`abs(ΔT_total)=8.4396e-11`、`abs(ΔR00_total)=1.0040e-10`，均 ≤ `2e-4` | full true residual 与能量闭合 pass；本项 z 对照 pass。y 门失败仍有效，样本资格不改变 | [输入](../../../input/task44_accuracy_layer_z2_v1.dat)、[run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_layer_z2_20261031__full3d_direct__mpi1__Mna/20261031T102657.088710Z/numerical_output/run_summary.json) |
| DtN 倏逝模态扩展 | B 基线增加手动倏逝壳层 m=4、n=8 | R_total、T_total、R00_total 各自变化目标 ≤ 2e-4；本次差值无法计算 | 求解完成但真残差门失败；official R/T/A 未运行，DtN 稳定性未判定 | [输入](../../../input/task44_accuracy_dtn_evanescent_shell_v1.dat)、[数值摘要](../../../results/task44_sixlayer_0p7nm/task44_accuracy_dtn_evanescent_shell_20261031__full3d_direct__mpi1__Mna/20261031T110232.922585Z/numerical_output/run_summary.json)、[响应 v6](../response_v6.md) |
| 顶部空气间距 | 空气高度 0.5 → 1.0 nm，基底底面固定 `z=-0.5 nm`；为延伸顶部空气区域，z 网格由 8 段增至 9 段 | `R_total`：0.0952190944953505 → 0.0949840957114875，`Δ=-2.349987839e-4`；`T_total`：0.8831311299072778 → 0.8833595386823099，`Δ=+2.284087750e-4`；`R00_total`：0.0952186487281771 → 0.09498364561553266，`Δ=-2.350031126e-4` | 解与能量门通过；三项 `abs(Δ)>2e-4`，判 `accuracy_gate_failed` | [输入](../../../input/task44_accuracy_air_gap_1nm_v1.dat)、[数值摘要](../../../results/task44_sixlayer_0p7nm/task44_accuracy_air_gap_1nm_20261031__full3d_direct__mpi1__Mna/20261031T114301.012893Z/numerical_output/run_summary.json)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-airgap1.service/service_summary.json)、[response v7](../response_v7.md) |

该 `2e-4` 门只说明已对照离散之间的工程稳定性，不是连续解误差保证。以下仍是截至 B8 的历史 attempt 账：两次 y attempt（一次未进入求解的 monitor failure、一次空间稳定性失败）、一次 z 求解通过、一次 DtN full explicit residual 失败、一次空气间距对照（解与闭合通过但稳定性变化超限），以及 B6–B8 三次 B boundary-plane 监控停止。B8 的 deadline 与延后细节见 [B8 terminal receipt](b8_boundary_plane_monitor_grace_timeout_20261101.md)；它们不再代表当前 CPU 共享政策。B9–B12 使累计额度达到 `12/12`，详见本 summary 的更新执行段。历史 DtN 尝试因没有 official R/T/A 而未证明模态截断稳定性，且用户已取消继续扩展；y 和空气间距稳定性失败仍有效；不能把 z 单方向通过扩大解释为总精度通过。

## A 的材料吸收分布与主功率诊断补充

静态凝聚先在每个六面体内部消去不与邻单元共享的自由度，再组装较小的全局系统；解出后恢复完整 H(curl) 场。它减少全局矩阵规模，但增加局部凝聚、恢复与矩阵自由残差计算。DtN 端口的 auxiliary 模态作为额外未知量表示上下端口的出射波，因此 29,808 个独立迹行外还附加 160 行。

| 项目 | A 结果 | 判据 / 解释 |
|---|---:|---|
| 全算子相对真残差 | `7.584367086899987e-10` | ≤ `1e-6`，pass；残差范数 `9.79964835722215e-10`，RHS 范数 `1.2920851858750988` |
| 残差计算 | 显式迹/DtN 矩阵作用 + 对所有被消去单元内部测试空间执行 matrix-free UFL 作用，包含凝聚后的完整 RHS | `full_global_matrix_allocated_for_residual=false`；这不是只读 MUMPS 的内部收敛标志 |
| 主反射 `R_total` | `0.10377060655595945` | 主功率源 `dtn_port_modal_amplitudes` |
| 零级反射 | `R00_s=0.10376987725348902`；`R00_p=6.570154036905706e-22`；`R00_total=0.10376987725348902` | `R00_total=R00_s+R00_p`，从保存值重算一致 |
| 主透射 `T_total` | `0.8800846265279674` | 主功率源 `dtn_port_modal_amplitudes` |
| 端口功率平衡 `A_balance` | `0.01614476691607314` | 由端口模态的 R/T 得到 |
| 材料体吸收 `A_volume_total` | `0.016144766075562058` | 按材料虚部与电场强度平方，在六层与 Si 基底上积分；每层及基底状态均为 `ok` |
| 能量闭合 `R+T+A_volume−1` | `-8.405111051601466e-10` | 绝对值 ≤ `1e-5`，pass；端口 A 与体积分 A 差 `8.405110808740179e-10` |
| KSP/PC/MUMPS | `preonly` / `lu` / `mumps`；`CONVERGED_ITS`，1 iteration | `mumps_control_readback.pass=true`，六项 ICNTL 的读回与要求一致 |

| 材料区域 | `A_volume` |
|---|---:|
| 第 1 层 Si | `0.0005378736956743745` |
| 第 2 层 Si₀.₇Ge₀.₃ | `0.004907296097588378` |
| 第 3 层 Si | `0.0005303344631520798` |
| 第 4 层 Si₀.₇Ge₀.₃ | `0.004767875461961016` |
| 第 5 层 Si | `0.0005076530103900762` |
| 第 6 层非晶 SiO₂ | `0.0009462386109519906` |
| Si 基底 | `0.0039474947358441445` |

场文件 `airbox_fields_3d_scientific.npz` 含 3,888 个 owned points、144 个 cells；E、H、坐标、Poynting 和 tag 等全部数值数组有限，保存文件 SHA-256 为 `1ed94284404da165b1829fbdfe2cf2cca20fceab87064a668ef7f67d3ea38a15`。最大场值为 `|E|=1.345827044339094 V/m`、`|H|=0.003573012615621154 A/m`。

### 网格、凝聚和直接因子规模

| 指标 | A 读回值 |
|---|---:|
| 网格 | `3×6×8=144` 个贴体六面体；P6；所有 z 层边界与材料对齐 |
| 物理 Nédélec 自由度 | `99,894` |
| 被消去的 cell-interior modes | `64,800` |
| 独立迹行 / 凝聚后 FE 行 | `29,808` |
| DtN auxiliary 行 | `160`（上下各 `80`） |
| 全局求解系统 | `29,968` rows，`24,315,568` used nnz |
| MUMPS 因子 nnz | `108,289,136` |
| cell kernel 结构计数 | `14` 个唯一原始材料/几何类对应的派生核调用，覆盖 144 cell；该数字由 compiled-kernel 映射推导，不是动态 profiler 计数 |

### 成本与诊断差异

| 资源 / 输出 | 实测 | 口径 |
|---|---:|---|
| Worker elapsed | `1653.708 s` | 公共 runner 从启动到写完结果 |
| Service elapsed | `1740.104 s` | systemd service 全生命周期 |
| Stage-4 组装与求解 | `1613.084 s` | worker 分阶段计时；子阶段存在嵌套，不应相加成总时间 |
| MUMPS factorization / solve | `41.037 s` / `0.860 s` | MUMPS 日志中的 driver 时间 |
| Matrix-free full residual | `181.518 s` | 恢复完整场后对全算子的显式作用检查 |
| service watchdog 进程树 RSS 采样峰值 | `7,550,930,944 B` | service summary 中活动进程树 RSS 总和；PSS profile 关闭 |
| 专属 cgroup memory peak | `8,337,240,064 B` | 内核 service cgroup memory 计数；不与 RSS 混称 |
| worker historical RSS 字段 | `4,484.82 MB` | `sum_rank_historical_peaks_upper_bound_not_simultaneous`，不是同时进程树峰值 |
| 任务 swap | `0 B` | 零 swap Gate 通过；service 结束后精确 PID 与 cgroup 均清空 |

端口模态是本样本的主 R/T/A 来源，且其 R/T 与 `A_volume` 闭合。两种额外采样算法仅是诊断：probe-EH Fourier 给出 `R=0.1195200182, T=0.7818715805, A=0.0986084013`（`A_probe−A_volume=0.0824636352`）；采样净通量给出 `R=0.2077451311, T=0.7789153558, A=0.0133395130`（`A_flux−A_volume=-0.0028052530`）。它们不是主要端口模态结果；当前证据没有把这两个差异归因到单一原因，后续精度检查仍须保留并解释这一边界。

## 启动器与证据身份

首个 condensed service 错误地继承共享默认 XDG 缓存，遇到旧 FFCx C 源编译超时；它在 PDE 装配前退出。最小修复为每个 service 绑定完整 unit 名称专属缓存根，将 `MYFENICS_TASK44_CACHE_ROOT` 显式传入 ABI preflight、正式 systemd unit 与 watchdog worker，并在 supervisor 中 fail-closed 验证 `XDG_CACHE_HOME` 和 FFCx 子目录。`task44-sample-cache-probe2.service` 的现有 smoke (`--dry-run`) 通过；没有修改 user-manager 全局环境，也没有清除旧缓存。修复提交为 `41867b8c0c64b8febe8a3cb230ccd84f00360af8`、`03ee03a51f9f7057376975fd43fd9d059dd9cd2b`。

A 的正式 service 为 `task44-sample-a-condensed-cachefix.service`，Invocation ID `6a2fb5670a684354b10a520e1021d94d`，MainPID/start ticks `4131351/335082125`，CPU affinity `[12]`，源码 SHA `03ee03a51f9f7057376975fd43fd9d059dd9cd2b`，输入 SHA-256 `8b320f279242f5dfa7183d2330647f5181c89343c4e01c5971e0ca06f1390f26`。专属 FFCx cache 根为 `/tmp/myfenics-task44-native-cache-1000/task44-sample-a-condensed-cachefix`。完整路径、逐文件 SHA 与 gate 复核见 ignored artifact [`official_A_review_v1.json`](../../../benchmarks/artifacts/task44_condensed_direct_validation_20261031/official_A_review_v1.json) 及 [`official_A_artifact_hashes_v1.json`](../../../benchmarks/artifacts/task44_condensed_direct_validation_20261031/official_A_artifact_hashes_v1.json)。

## 下一步

1. Task44 与 Task40 并行已获用户明确授权。Task44 只观测自己的 service 和资源，不发送信号或修改 Task40；Task44 的重型对照仍一次运行一个。
2. 四项历史精度对照均已完成：旧版 y 与顶部空气间距的稳定性变化超限；z 对照通过；历史 DtN 倏逝壳层运行的真残差失败，截断稳定性没有得到证明。用户已取消继续扩展 DtN 壳层，不列为待重跑项。若获准进行其他复算，须保留现有正负结果，并先核对 ABI、邻任务、CPU、宿主/祖先 cgroup、内存、swap 和 service 身份，再按完整残差、能量闭合、R/T/R00 与进程清场逐项判定。
3. 以 B 为基线，旧版 y 与空气距稳定性门失败，所以旧版 A–D 的历史资格字段仍为 `gp_eligible=false`；这不覆盖 v2 设计中已独立合格的 train_005、train_006、train_009，也不改变因生命周期证据缺口而 held 的 v2 D。原始精度额度已用完 `12/12`。B9–B11 是监控受控停止，B12 是单点参考面数值锚点；保留所有正负结果。固定 160 个 DtN 模态；即使所测方向通过，也只形成 B 单点、y12 候选配置的工程稳定性证据，不自动将旧版粗网格 A/C/D 改标，也不证明 DtN 模态截断收敛。未来代理范围须明确披露固定 160 模态。
4. A–D worker 实测为 1653.708–1836.503 s（27.6–30.6 min）；空气间距 worker 为 1877.662 s，服务全生命周期为 1944.634 s。该服务同时进程树 RSS 峰值为 8,538,501,120 B，专属 cgroup memory peak 为 9,228,845,056 B，swap 峰值为 0 B。不预设批量性能已达到目标，也不因单样本较慢直接判断 GP 不可行；GP 训练、开发评估、盲测和标准尺寸仍为 `not_run`。
5. 当前 execution branch 保持显式凝聚 direct 研究路线，不改 ordinary solver default，不合并 `master`；结果与未运行范围进入下一轮 review。
