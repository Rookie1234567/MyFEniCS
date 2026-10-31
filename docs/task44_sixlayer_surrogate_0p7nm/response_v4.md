# Task44 执行响应 v4：GP 软件验证与 y 加密结果

## 本轮结论

A–D 四个代表点仍通过各自的 full explicit true residual 和能量闭合门。以 B 为基线的 y 向加密求解也通过这两项内部求解检查，但三个主功率量对网格加密的变化都超过 `2e-4`，因此 y 方向的空间稳定性门失败。它是有效的数值对照负结果，不是线性系统未收敛；在全部精度对照完成并选定离散前，A–D 继续保持 `gp_eligible=false`。

这一对照把传播方向 y 的网格段数从 6 增至 12，其余物理配置、材料、边界、求解方法和端口条件不变。对两个 `resolved_config.json` 做字段比较，唯一的数值配置差异是 `discretization.mesh_axis_cell_counts` 从 `[3,6,8]` 改为 `[3,12,8]`。所以这里测到的是当前离散对 y 网格加密的响应，不能把结果差值归因于材料或边界配置变化。

## y 加密对照结果

| 数值量 | B：`[3,6,8]` | y 加密：`[3,12,8]` | 有符号变化 | 判定 |
|---|---:|---:|---:|---|
| `R_total` | 0.0952190944953505 | 0.09619911407616114 | +0.0009800195808106343 | `abs(Δ)>2e-4` |
| `T_total` | 0.8831311299072778 | 0.8822083809416161 | -0.0009227489656616905 | `abs(Δ)>2e-4` |
| `R00_total` | 0.0952186487281771 | 0.09619866247638499 | +0.0009800137482078863 | `abs(Δ)>2e-4` |
| `R00_s / R00_p`（y 加密） | — | 0.09619866247638499 / 1.0699952159268371e-21 | — | `R00_total=R00_s+R00_p` |
| `A_balance / A_volume`（y 加密） | — | 0.02159250498222276 / 0.021592504942755907 | — | absorption closure agrees |
| full true relative residual（y 加密） | — | 1.2751367232278894e-9 | — | `≤1e-6`，pass |
| `R+T+A_volume−1`（y 加密） | — | -3.946687421318984e-11 | — | `≤1e-5`，pass |

`R_total`、`T_total` 和 `R00_total` 都来自完整 DtN 端口模态；probe Fourier 和采样净通量只是诊断字段。内部残差与能量闭合通过表示该离散系统被准确求解且功率账目闭合，并不能抵消不同网格间约 `9.2–9.8e-4` 的输出变化。因此本次对照没有证明 B 网格稳定，也没有证明更细的 `[3,12,8]` 网格已收敛到连续解。

## 运行身份与资源

| 项目 | 记录 |
|---|---|
| Run / service | `task44_accuracy_propagation_y2_20261031` / `task44-sample-accuracy-yrefine-retry1.service` |
| InvocationID / CPU | `27c2f1ed195943a8a494bd87c788c70f` / CPU 8 |
| 输入 SHA-256 | `272312c4e0b997fbf40649c4d3be678a9cd38efe229f3b3d61fddc5fa0656269` |
| 物理配置 SHA-256 | `b16f8d783eb85069c530194e246ea88c691d011411892771f93a0c6111224886` |
| PDE source SHA | `5a89ca1652fbe721f4d0ecf8cef9fc7ea276d92a`；与 B 的 `03cc11c452f4f7a5cdfb800a84c87fdd4872410b` 不同，但两者之间没有数值 solver/source 文件改动 |
| 运行结果 | `worker_exit0`；validation role 为 `numerical_sanity_only`，不是物理 benchmark |
| 数值 summary elapsed / service 全生命周期 | 3347.793 s / 3417.755 s；这是两个不同时间口径 |
| Stage 4 assembly + solve / DtN build / direct solve / full residual | 3313.561 s / 2851.534 s / 102.725 s / 125.519 s |
| 网格、阶数、自由度 | 288 个 hex，P6，197,994 个完整 Nédélec DoF；59,616 个迹行 + 160 个 DtN 行 = 59,776 个实际求解行 |
| 矩阵 NNZ | run summary 未记录，未估算 |
| 内存和 swap | process-tree peak RSS 12,487,163,904 B；service cgroup memory peak 13,289,373,696 B；cgroup 与进程树 swap 均为 0 |
| watchdog / 清场 | 9,262 次采样、无 warning；进程身份完整，service 结束后无子进程残留 |

证据入口：[numerical run summary](../../../results/task44_sixlayer_0p7nm/task44_accuracy_propagation_y2_20261031__full3d_direct__mpi1__Mna/20261031T091904.310578Z/numerical_output/run_summary.json)、[run manifest](../../../results/task44_sixlayer_0p7nm/task44_accuracy_propagation_y2_20261031__full3d_direct__mpi1__Mna/20261031T091904.310578Z/run_manifest.json)、[service summary](../../../benchmarks/artifacts/task44_native_services/task44-sample-accuracy-yrefine-retry1.service/service_summary.json)。

第一次 y-refinement attempt 因短命 compiler child 身份尚未稳定，在矩阵组装前由监控门受控终止；该负结果与本次实际求解的精度负结果分别保留，不能合并成数值失败。两次 attempt 共占用既定 12 次复算预算中的两次，其中只有 retry 产生数值场和功率结果。

## GP 软件与样本资格

GP/design 实现提交 `c439f48aee6ca6e508bba82ecdca40358bc98da9` 已推送到执行分支。改动提供固定 20/10/10 几何设计、三输出 Matérn 5/2 ARD GP、基线、开发集学习曲线和每输出优化器 fit receipt。学习曲线拒绝重复训练/开发几何；非收敛但可计算的后验明确标作 `diagnostic_only_optimizer_not_converged`。盲测学习曲线不在该接口范围内。

验证结果：ABI preflight 通过；scoped Ruff、compileall 通过；surrogate 测试 `9 passed`；`sample_design_v1.json` 的 40 个候选身份校验通过。当前只是软件和采样设计验证，尚无任何有限元 GP 训练、模型选择、开发误差或盲测误差。A–D 与其余候选的正式资格标签没有在本轮改变。

## 下一步

Task44 与 Task40 并行运行已获用户授权；不干预 Task40。Task44 保持一次只运行一个重型 comparison，并在每次启动前执行 fresh CPU、ABI、内存、cgroup、swap 和邻任务准入。依次运行 B 基线上的 z 加密、DtN 倏逝模态壳层和顶部空气间距对照。它们用于定位误差来源，不能自动把当前样本标为 `gp_eligible`。三项结束后再按实测误差组合提出统一离散候选和进一步 y 收敛方案；继续遵守额外科学复算最多 12 次、P6 和冻结物理条件，不启动未资格的大规模训练库。
