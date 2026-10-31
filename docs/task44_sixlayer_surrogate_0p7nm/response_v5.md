# Task44 执行响应 v5：材料内部 z 加密结果

## 本轮结论

以 B 为基线的材料内部 z 加密已完成。z 网格段数从 8 增至 16 后，`R_total`、`T_total`、`R00_total` 的绝对变化分别约 `9.6e-11`、`8.4e-11`、`1.0e-10`，均远小于 `2e-4`。全显式算子真残差和能量闭合也通过。这说明这三个输出在当前设置下对 z 向加密不敏感。

该结论只覆盖 z 方向这一次离散对照。此前 y 加密的三个输出变化仍超过门限，因此 z 通过不能推出总精度合格，A–D 的 `gp_eligible=false` 不变。DtN 倏逝模态和顶部空气间距对照仍须完成。

## 对照设置与结果

z 对照使用 `[3,6,16]`、288 个贴体六面体、P6、MPI1、静态凝聚和 MUMPS exact。对输入配置作逐字段比较，唯一的物理数值设置差别是网格段数 `[3,6,8]` → `[3,6,16]`；运行标签及 comparison group 是本次对照的元数据。与 B 结果相比，源码 SHA 不同，但从 B 的源码身份到本次源码的 `src/` 文件差异仅涉及 GP 研究辅助模块和测试，没有有限元 solver 源文件变更。

| 数值量 | B：`[3,6,8]` | z 加密：`[3,6,16]` | z−B 有符号变化 | 判定 |
|---|---:|---:|---:|---|
| `R_total` | 0.0952190944953505 | 0.0952190943990193 | -9.633120690e-11 | `abs(Δ)≤2e-4` |
| `T_total` | 0.8831311299072778 | 0.8831311298228821 | -8.439571264e-11 | `abs(Δ)≤2e-4` |
| `R00_total` | 0.0952186487281771 | 0.09521864862777846 | -1.003986477e-10 | `abs(Δ)≤2e-4` |
| `R00_s / R00_p`（z 加密） | — | 0.09521864862777846 / 9.543330210210267e-23 | — | 两分量相加等于 `R00_total` |
| `A_balance / A_volume`（z 加密） | — | 0.021649775778098568 / 0.02164977501620309 | — | 端口与材料体吸收闭合 |
| 全显式算子相对真残差 | — | 4.64908820597943e-10 | — | `≤1e-6`，pass |
| `R+T+A_volume−1` | — | -7.61895435630322e-10 | — | `≤1e-5`，pass |

`R_total`、`T_total` 和 `R00_total` 取自完整 DtN 端口模态；R/T/A 没有用诊断 Fourier 或采样通量替代。`R00_total=R00_s+R00_p`。真残差通过恢复完整场，对迹与 DtN 部分显式作用，并对凝聚消去的单元内部自由度使用 matrix-free 全算子作用计算；不是 MUMPS 内部状态的代称。

## 运行身份、资源与复核

| 项目 | 记录 |
|---|---|
| Run / service / Invocation | `task44_accuracy_layer_z2_20261031` / `task44-sample-accuracy-zrefine1.service` / `2328dc0df7f94e16a4305010eaccb054` |
| 准入 | Task44/Task40 并行期间通过 fresh resource preflight；选择 CPU29，`performance_not_isolated=false`，没有窄 affinity 冲突；初始 host MemAvailable `2,093,123,276,800 B`，扣除 `412,316,860,416 B` reserve 后仍有 `1,534,777,528,320 B` 余量 |
| 输入 / 物理模型 / 源码 SHA-256 | `6c55c599439fee0963f529025873549c9418fd08884767d4a14109d920660c0e` / `21f035163b3f875f916f9560bdfc778f871c56f0b2875023a8211825ac085f19` / `a10ece015bb311489d0dc4a977a197e1da2df90f` |
| 求解规模 | 288 hex；198,438 个完整 Nédélec DoF；58,320 个迹行 + 160 个 DtN auxiliary 行 = 58,480 个求解行；48,157,036 used NNZ |
| 耗时 | numerical run summary `1,651.694 s`；service 全生命周期 `1,716.819 s`；Stage 4 `1,620.108 s`；DtN build `1,262.984 s`；direct solve `0.862 s`；全显式残差 `114.007 s`。worker wall 未单独记录 |
| 内存 / swap | 专属 service cap `137,438,953,472 B`（128 GiB）；同时进程树 RSS 峰值 `10,121,396,224 B`；内核 cgroup memory peak `10,965,905,408 B`；进程树和专属 cgroup swap 峰值均 `0 B` |
| 监控 / 清场 | resource authority 4,670 次采样、无 warning；进程树身份 1,346 次完整采样；service 分类 `COMPLETED`，`descendants_cleared=true`，无剩余子 PID |
| 数值身份状态 | `official_result=true` 是求解记录状态；`physical_benchmark_candidate=false`、`validation_role=numerical_sanity_only`，所以该 accuracy comparison 不作为新的物理训练标签；MUMPS 控制读回通过 |

结果文件 SHA-256：numerical `run_summary.json` 为 `a37e4b03cba2e9752e3146c320e21b0520d7e56f865c0f1b6cddb89314caada8`；`dtn_port_power_metrics_3d.json` 为 `1e66d971db95cb15740c2874859c9fce14c26d229a962ddb7e76c146eb159c0c`；service `service_summary.json` 为 `a1cf9cde125a0b680f8b46af493544bbac85729538f0c65842091aae9a643696`。

详细证据：[numerical run summary](../../results/task44_sixlayer_0p7nm/task44_accuracy_layer_z2_20261031__full3d_direct__mpi1__Mna/20261031T102657.088710Z/numerical_output/run_summary.json)、[run manifest](../../results/task44_sixlayer_0p7nm/task44_accuracy_layer_z2_20261031__full3d_direct__mpi1__Mna/20261031T102657.088710Z/run_manifest.json)、[service summary](../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-zrefine1.service/service_summary.json)、[input](../../input/task44_accuracy_layer_z2_v1.dat)。

## 当前状态与下一步

y refinement 有两次保留记录：第一次在组装前因监控子进程身份未稳定而 `MONITORING_FAILED / not_run`；retry 的求解与闭合通过，但三个网格差值超限。z refinement 的三个差值均通过。当前 12 次额外科学复算预算已登记 3 次 attempt（其中两次数值求解）；接下来依次执行 DtN 倏逝壳层和顶部空气间距对照，每次启动前重新做 ABI、CPU/邻居、内存、cgroup、swap 和 service 身份准入。之后综合四项精度证据；不能因为 z 的单方向通过就训练、解锁 A–D 或宣称连续解精度。
