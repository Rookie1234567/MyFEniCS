# Case090 干净源码 PDE core runner

这个补充 runner 只生成真实 PDE 证据，不用测试夹具伪造正式结果。它直接调用
Stage-2A 空气盒与 Stage-4A 平层求解路径；正式运行必须从同一个已提交、无 tracked
改动的 40 位 SHA 开始，并把所有运行产物放在 `benchmarks/artifacts/` 等 git-ignore
目录中。

## 固定用例矩阵

每个 MPI shard 恰好包含 48 个算例：

- Fixture A：10° 掠射，`p1–p4 × h5/h2.5 × S/P`，16 个；
- Fixture B 主矩阵：10° 掠射，`p1–p4 × h5/h2.5 × S/P`，16 个；
- Fixture B smoke：1°/5° 掠射，`h5 × p1–p4 × S/P`，16 个。

因此三个 shard 分别固定为 MPI1、MPI2、MPI4。1°/5° smoke 只有 h5，聚合时会明确
记为 `not_applicable_smoke_h5_only`，不会虚构 h2.5 对照。

## 物理与代数证据

Fixture A 保留求解器自带解析解的相对 E/H 最大误差。Fixture B 不能只证明场值
finite：每个 rank 独立读取自己的 VTU shard，用平层 Fresnel 解析场重新计算 E/H
相对最大误差，然后只对四个标量做 MPI reduction，不 gather 场或边界向量。

Fixture B 还读取官方 `port_power.json` 的 `(m,n)=(0,0)`、同名 S/P 模式
`outgoing_amplitude_at_boundary`，并与 `flat_layer_reference.json` 中解析 Fresnel
复数 r/t 比较。解析界面振幅乘以 `incident_amplitude` 与该端口行记录的
`boundary_phase` 后，才与数值边界振幅比较；记录复数值、绝对误差、相对误差和
相位误差。若求解器没有这组可辩护的复振幅或必要 VTU 数组，物理资格直接失败，
不会补造数值。

有限但巨大的误差不能通过。当前宽松的 sanity 上限为：相对 E/H 误差不超过 10，
0 阶复振幅绝对误差不超过 2。这些只是排除失真结果的硬上限，不代表宣称达到工程
精度；真正的精度判断还包括逐 fixture/角度/极化/degree/MPI 的 h5→h2.5 非增检查
（5% 相对容差和 `1e-10` 绝对容差）以及逐 h/MPI 的 p 趋势比较。p4 对 p3 没有至少
1% 收益时保留 `negative_no_clear_p4_benefit`；超过 5% 回退才作为失败。

每个 degree 还有一个真实稀疏代数 probe：

- 比较 Basix entity transform round trip 和解析 Bloch trace；
- 独立构造稀疏约束嵌入 C；
- 比较已装配 MPC 算子 `A_red q` 与 `C^H A_full C q`；
- `A_full` 是真实装配的 3D H(curl) curl-curl-plus-mass coercive 算子；
- 输入自由 DoF 为确定性非零值、slave DoF 为零；
- 在相同 mesh/function space 改变入射角，再次构造约束必须 cache hit，topology
  build time、topology communication 都必须为零。重建 topology、dense boundary
  square 或 full-boundary gather 均直接失败。

PDE 行完整记录 periodic DoF/slave/master/NNZ、cache hit/miss、topology/phase/
setup/total 时间和通信字节。聚合器计算 p4 setup 占总时间比例以及相对 p2 的
per-constrained-DoF setup 成本；超过 20% 或 5 倍会形成 warning/analysis 字段，但
warning 本身不冒充代数失败。

## 用外部 watchdog 运行 shard

watchdog 必须作为 shard 的父进程运行，不能在 solver 内部用历史 peak RSS 代替。
下面命令应在同一个 DOLFINx Docker 容器内执行；路径示例均位于已 ignore 的
`benchmarks/artifacts/case090/`：

```text
python -m benchmarks.run_task033_case090_watchdog --mpi-size 1 --raw-output benchmarks/artifacts/case090/mpi1/watchdog_raw.jsonl --summary-output benchmarks/artifacts/case090/mpi1/watchdog_summary.json --sample-interval 1 --wall-timeout-seconds 86400 -- mpiexec -n 1 python -m benchmarks.run_task033_case090_pde_core shard --work-dir benchmarks/artifacts/case090/mpi1/work --output benchmarks/artifacts/case090/mpi1/shard.json

python -m benchmarks.run_task033_case090_watchdog --mpi-size 2 --raw-output benchmarks/artifacts/case090/mpi2/watchdog_raw.jsonl --summary-output benchmarks/artifacts/case090/mpi2/watchdog_summary.json --sample-interval 1 --wall-timeout-seconds 86400 -- mpiexec -n 2 python -m benchmarks.run_task033_case090_pde_core shard --work-dir benchmarks/artifacts/case090/mpi2/work --output benchmarks/artifacts/case090/mpi2/shard.json

python -m benchmarks.run_task033_case090_watchdog --mpi-size 4 --raw-output benchmarks/artifacts/case090/mpi4/watchdog_raw.jsonl --summary-output benchmarks/artifacts/case090/mpi4/watchdog_summary.json --sample-interval 1 --wall-timeout-seconds 86400 -- mpiexec -n 4 python -m benchmarks.run_task033_case090_pde_core shard --work-dir benchmarks/artifacts/case090/mpi4/work --output benchmarks/artifacts/case090/mpi4/shard.json
```

每次采样同时记录 live worker process tree RSS 总和、cgroup `memory.current`、swap
current、容器 limit 和 host available memory；正式 observed memory 定义为每个采样
点的 `max(worker RSS sum, cgroup current)`。原始 JSONL 连续落盘，轻量 summary
保存峰值、swap 初/末/峰值与控制触发信息。preflight 必须读到 finite container
limit、host available、cgroup current，且 swap current 必须为 0；`memory.max=max`
会明确记为 unbounded 并拒绝，不能拿 host available 冒充容器上限。正式 effective
authority 为 `min(container limit, preflight host available, 14 GiB)`，warning 与
controlled-termination 阈值分别按 `11.5/14`、`13/14` 线性缩放。循环中每个样本都
要求所有 authority 可读且 swap current 恰为 0；达到 warning 立即输出，达到终止
阈值、出现非零 swap、authority 丢失或 wall timeout 时立即终止完整 worker process
group，宽限后仍存活则 kill。任何 controlled termination/timeout、少于两个采样、
worker 非零退出、输出未被 git ignore 或源码不干净/变化，均不能取得 memory
qualification。Docker 正式启动还必须显式设置 finite `--memory`，并用相同
`--memory-swap` 禁用 swap。

## 聚合

聚合器只接受同一 clean SHA 的三个 shard 与对应的三个合格外部 memory summary：

```text
python -m benchmarks.run_task033_case090_pde_core aggregate benchmarks/artifacts/case090/mpi1/shard.json benchmarks/artifacts/case090/mpi2/shard.json benchmarks/artifacts/case090/mpi4/shard.json --memory-summaries benchmarks/artifacts/case090/mpi1/watchdog_summary.json benchmarks/artifacts/case090/mpi2/watchdog_summary.json benchmarks/artifacts/case090/mpi4/watchdog_summary.json --output benchmarks/artifacts/case090/case090_core.json --require-pass
```

聚合会复核 SHA、证据哈希、精确覆盖、MPI 数值一致性、物理误差与趋势、稀疏/
no-gather/no-dense veto、cache reuse、性能分析和 watchdog 资格。输出保持
`task033.case090.core-gates.v1`，供现有 Case090 planner 消费；补充 JSON Schema 为
`pde_core_schema.json`。正式运行之前不要把 provisional 数据写进 tracked
`records/`。
