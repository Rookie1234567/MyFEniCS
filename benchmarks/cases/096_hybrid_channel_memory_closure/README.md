# Case096：Hybrid 逐通道精度与静态凝聚内存闭合

## 这个 case 在解决什么问题

Full3D 会把整个三维结构一次性离散成大矩阵。Hybrid 则只在上下两个复杂局部
区域使用三维有限元，把中间均匀层改写成少量传播模态，因此能明显减少未知量。
但 Task035b 暴露了两个问题：两种方法的总反射和透射接近时，12 个显著衍射级
中的弱通道仍可能相位错误；Hybrid 再使用静态凝聚后，矩阵虽变小，峰值内存却
未必随之下降。

静态凝聚的通俗含义是：先在每个单元内部消去不会与相邻单元直接共享的未知量，
全局只求界面未知量，最后再恢复完整场。它减少全局矩阵的行和非零元，但会使
界面矩阵更稠密，并增加局部消元和恢复成本。因此本 case 同时检查物理结果、
矩阵规模、MUMPS factor、峰值内存和时间，而不只看 DoF。

## 固定范围

- 几何：Task034 fixed rectangular block grating；
- 诊断模型：`p2/h5`；
- 正式高阶 authority：`p6/h10`；
- 正式进程数：MPI8；
- 高阶六路：
  - Full3D standard/static；
  - Hybrid standard M120/M160；
  - Hybrid static M120/M160；
- `p3/h7.5 = out_of_scope_by_user / not_run / not_a_completion_gate`；
- ordinary default 仍是 `standard_full`。

本 case 没有运行或提升 irregular geometry、h13 adaptive Hybrid、
production selective trace、tetra/mixed static condensation 或 condensed
iterative profile。

## p2/h5 根因

旧 Hybrid 在中间均匀层直接使用连续传播因子 `exp(i beta L)` 和连续端点
traction。Full3D 实际上在 z 方向使用 scalar CG(p) 有限元链，因此传播相位和
端点导数都是离散符号。只修正传播相位的隔离点仍只有
`4/12 power + 4/12 complex amplitude`；同时使用
`full3d_uniform_cg` 传播和 `scalar_cg_discrete_derivative` traction 后，
M120、M160 均达到 `12/12 + 12/12`。

普通默认没有改变；这两个模型仍是 fixed-rectangular、均匀 z 网格下的显式
opt-in 路径。

## p6/h10 正式结果

六条 MPI8 路径都绑定同一数值源码：

```text
244b62e1fb4f299a468363cf90a2dd548dc34ff6
```

逐通道比较使用 DtN port 物理边界面上的复振幅
`outgoing_amplitude_at_boundary`。这样功率和相位采用同一个 reference
plane，不会把纯传播相位误认为 Hybrid 误差。

| 模型 | rows | matrix NNZ | factor NNZ | 峰值 GiB | 总时间 s |
|---|---:|---:|---:|---:|---:|
| Full3D standard | 173,882 | 210,353,168 | 438,050,956 | 34.041 | 2,581.55 |
| Full3D static | 51,272 | 41,989,040 | 212,343,992 | 14.722 | 260.74 |
| Hybrid standard M120 | 52,292 | 60,434,236 | 141,010,528 | 11.077 | 942.03 |
| Hybrid static M120 | 17,168 | 12,313,232 | 45,293,792 | 7.544 | 322.78 |
| Hybrid standard M160 | 52,372 | 60,434,236 | 141,010,528 | 11.247 | 1,014.71 |
| Hybrid static M160 | 17,248 | 12,313,232 | 45,293,792 | 7.929 | 393.84 |

所有要求的同离散比较、M120→M160 比较以及 frozen
significant-channel-reference-v1 独立绝对审计均通过
`12/12 powers + 12/12 complex amplitudes`。

### static Hybrid 资源收益

| 比较 | rows 减少 | matrix NNZ 减少 | factor NNZ 减少 | 总峰值减少 | coupling 阶段峰值减少 | static/standard 总时间 |
|---|---:|---:|---:|---:|---:|---:|
| M120 | 67.17% | 79.63% | 67.88% | 31.89% | 21.91% | 0.343 |
| M160 | 67.07% | 79.63% | 67.88% | 29.50% | 17.35% | 0.388 |

Task035c 的强制 `>=15%` 和优选 `>=25%` 峰值内存 Gate 均通过，总时间也
通过 `<=1.35x` Gate。用户希望的 `>=50%` static-Hybrid 峰值下降没有达到，
所以文档不能把约 30% 写成最终理想内存下限。尤其 modal-coupling 阶段只降低
约 17–22%，说明后续若继续压内存，应优先缩短 QEP eigenvector、projection、
local factor 和场恢复对象的共存期，而不是只继续减 rows。

M120 的50%目标要求 `<=5.538446 GiB`，但 static coupling stage 已为
`5.756237 GiB`，factor/Schur stage又达到约`6.817 GiB`。因此只在
postprocess/record前增加简单释放不能达到目标；需要 coupling分块与上下local
factor错峰的资源算法重构，并在新同一源码上重跑六路径authority。

用户已取消 modal-coupling `1.25x` 硬限制。本 case 仍报告该时间：
M120/M160 的 static/standard 比为 `1.076/1.076`，用于后续优化但不参与
通过判定。

## rank study 的证据边界

- MPI1 Full3D static 通过；Hybrid static M120 的 positive-QEP
  biorthogonality identity error 为 `1.1975997613347697e-6`，超过
  `1e-6`，是数值 Gate 负结果，不能作为最低内存 authority。
- MPI2 Full3D static 通过；Hybrid static M120 数值链通过，但 worker 退出
  时 resource sampler 出现 terminal-drain race，导致 live RSS/swap
  readability 不完整。因此 `3.142 GiB` 只能作为 diagnostic，不能写成正式
  资源下限。
- MPI8 重试记录同时通过数值和资源遥测 Gate，是本轮正式 authority。

这些负结果保留在
[`records/p6_h10_static_rank_study_v1.json`](records/p6_h10_static_rank_study_v1.json)
中，没有被后来的成功记录覆盖。

## compact evidence

- [`records/p2_h5_root_cause_v1.json`](records/p2_h5_root_cause_v1.json)：
  p2 根因、修复后闭合与 phase-only controlled negative；
- [`records/p6_h10_mpi8_six_path_v1.json`](records/p6_h10_mpi8_six_path_v1.json)：
  六路高阶结果、12 通道和资源对照；
- [`records/p6_h10_static_rank_study_v1.json`](records/p6_h10_static_rank_study_v1.json)：
  MPI1/2/8 与 authority 边界；
- [`records/dependency_failures_v1.json`](records/dependency_failures_v1.json)：
  p5/p6 Floquet 约束、scale-aware trace audit 和 sampler race 的历史失败；
- [`records/execution_ledger_v1.json`](records/execution_ledger_v1.json)：
  完成、负结果和未运行范围总账；
- [`records/compact_authority_v1.json`](records/compact_authority_v1.json)：
  以上记录的 SHA-256 manifest。

compact 数值不是手工摘录。仓库中保留的生成器会读取 ignored raw watchdog、
solver record 和 DtN orders，逐项验证 SHA 后重新计算。拥有本机 raw artifact
时可运行：

```bash
source scripts/activate_myfenics_wsl.sh
python benchmarks/cases/096_hybrid_channel_memory_closure/generate_compact_records.py --check
```

不依赖 ignored artifact 的 hermetic contract test 为：

```bash
source scripts/activate_myfenics_wsl.sh
python -m pytest -q src/test/test_case096_compact_evidence_contract.py
```
