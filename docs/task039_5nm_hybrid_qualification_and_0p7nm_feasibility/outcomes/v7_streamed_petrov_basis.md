# V7 Lane B：streamed bottom basis producer

这个阶段只生产 Petrov 校正所需的左右 owner-row 基，尚未运行 consumer。它的内存策略很直观：每次只读取一个 mode pair，立即把临时 source 向量释放；8 个 MPI rank 各自保存自己的行区间，不把完整全局基复制到每个 rank。因此它测量的是“能否低内存地生产可复用基”，不是完整电磁求解结果。

## 结论

| 项目 | 结论 | 说明 |
| --- | --- | --- |
| `fb915a7a` 前一轮 | `TELEMETRY_IMPLEMENTATION_FAILURE` | inventory 证据字段缺失；不是数值或资源负结果 |
| `a33c19e7` producer | `PRODUCER_COMPLETED` | exit 0，512 列 basis packet 完整写出 |
| resource Gate | `PASS_MINIMUM_AND_ROBUST` | peak `11.630760192 GiB`，低于 `93.377006531` 与 `88.708156204 GiB` |
| basis packet | `HASH_BOUND_AND_READABLE` | 8 shards、连续 ownership、4 个嵌套 prefix |
| `YᴴZ` conditioning | `WARNING_ONLY` | 这是 producer 诊断，不是 consumer 的 coarse-E Gate |
| consumer `E=YᴴFZ` | `NOT_RUN` | 未启动 consumer、六组 holdout probe 或 top/outer |

## 两次正式尝试

### 旧 root：telemetry implementation failure

`results/task039_v7_streamed_bottom_basis_producer_mpi8_fb915a7a` 使用 source
`fb915a7a2fe42b4036b3356ea18764b9c3156656`。该轮在 `setup_begin` 后未完成，峰值为
`9,903,783,936 B = 9.223617553710938 GiB`，swap=0。V7 producer metadata 没有明确写出
`direct_reference_payload_loaded=false`，导致 evidence contract 失败；因此不能把它写成
producer 数值失败、资源失败或 Lane B 负结果。该 root 的 raw 仍原样保留。

### 新 root：telemetry 修复后的正式 producer

`results/task039_v7_streamed_bottom_basis_producer_mpi8_a33c19e7` 绑定完整 source
SHA `a33c19e7416460b11ceb61c2a7e32ab41fe1c1e7`，由 parent watchdog 以 MPI8、6 小时默认
上限、poll `0.25 s`、effective hard stop `100262797312 B`、swap=0 启动。输入和 packet
身份为冻结合同：

| 身份 | 值 |
| --- | --- |
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| selected packet manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| route | `--v7-h4-streamed-bottom-producer` |
| status / exit | `finished` / `0` |
| worker / parent elapsed | `413.2611265759915 s` / `415.60005551797803 s` |
| process-tree peak | `12,488,433,664 B = 11.630760192 GiB` |
| swap | `0 B` |
| resource classification | minimum 与 robust 两条线均 pass |

## 同一嵌套 basis packet

producer 只写一个最终 packet，consumer（本阶段未运行）应从同一 packet 读取
`64/128/256/512` prefix，而不是生成四套 packet。

| 字段 | measured/derived |
| --- | --- |
| packet schema | `task039.v7.streamed_owner_row_basis.v2` |
| packet manifest SHA256 | `44023b8d8d3932e5cf5d0d42a16711f886e7672570e0318cb0339b44b691c44b` |
| rank shards / array artifacts | `8 / 16`（每 rank 一组 Y/Z） |
| global rows / dtype | `132300 / complex128` |
| schedule | `512`，batch `1`，SHA256 `6ac80cc56096244f49999c85c0bb8fd3a5543e3efd83f51cd0e0a62e396c6d1d` |
| ownership | `[0,132300)` 连续完整覆盖，无 gap/overlap |
| prefix/hash/shape | 四个 prefix hash 均存在；8 个 shard 的 shape/dtype/path 均通过核对 |
| holdout/exact spool/QEP | `false / false / 0` |
| global basis/source columns | `false / false` |

每个 rank 的 ownership 半开区间为 `[0,16872)`、`[16872,34098)`、`[34098,49560)`、
`[49560,67134)`、`[67134,83976)`、`[83976,99870)`、`[99870,116766)`、
`[116766,132300)`。这证明 packet 可以按当前 owner-row 分区被 consumer 读取。

## Prefix 诊断

Z/Y 正交误差和 worker-authoritative `YᴴZ` condition 如下。64/128/256 的 singular
min/max 没有写入 worker raw，因此表中只列 mmap 分块重算的 derived 值；512 同时列出
worker raw 值。derived 审计的最小奇异值接近舍入噪声，归约顺序不同会造成很大相对变化，
不能覆盖 worker raw。

| prefix | 构造列/基 rank | Z orth | Y orth | worker `YᴴZ` condition | derived smin / smax / condition | derived numerical rank |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 64 / 64 | 5.2627e-15 | 4.8349e-15 | 7.7253e17 | 1.4798e-18 / 1.0000 / 6.7579e17 | 48 |
| 128 | 128 / 128 | 7.9867e-15 | 6.7323e-15 | 3.8879e18 | 1.4259e-19 / 1.0000 / 7.0129e18 | 96 |
| 256 | 256 / 256 | 1.1550e-14 | 1.0948e-14 | 7.0763e17 | 8.0659e-19 / 1.0000 / 1.2398e18 | 192 |
| 512 | 512 / 512 | 1.8641e-14 | 1.7994e-14 | 4.9906e19 | `worker: 2.0038e-20 / 1.0000 / 4.9906e19` | 384 derived |

`YᴴZ` 的数值病态只说明左右 source 子空间的交叉矩阵很不适合用作稳定性替代指标；它
不是 `E=YᴴFZ`。Review V7 的正式 consumer Gate 是实际构造 `E` 后检查其 condition
`<=1e12`，并按 `64 -> 128 -> 256 -> 512` 依次评估。因此本 warning 不改变 frozen
consumer ladder 的顺序，也不能被写成 consumer 已通过。

## 生命周期与资源口径

| 对象/事件 | 证据 |
| --- | --- |
| packet context before/after | 4 mmap、arrays retained=true → 0 mmap、arrays retained=false、released=true |
| temporary sources | source columns retained=false；mode Vec/full vectors=0 |
| factors / nested KSP | base/exact/global=`0/0/0`；nested KSP=`0` |
| finalizer | `v7_streamed_bottom_producer_side_setup_cleanup`；bottom destroyed=true；collective cleanup=true |
| factor count after cleanup | raw marker 为 `null/not_available`，不从其他字段推断为 0 |
| resource authority | parent process-tree sample；peak `11.630760192 GiB`；swap=0 |

“streamed”节省内存的原因是把大矩阵/大向量的同时驻留改成一次一列、按 rank 行区间
处理；它并不代表 producer 已完成物理求解。`YᴴZ` warning 也不等于最终 solver 失败，
因为真正决定 correction 是否可用的是带 side operator `F` 的 coarse matrix `E`。

## 边界与证据路径

- compact record：[task039_v7_streamed_bottom_basis_producer_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_streamed_bottom_basis_producer_v1.json)
- producer diagnostic: `results/task039_v7_streamed_bottom_basis_producer_mpi8_a33c19e7/numerical_output/v3_v7_diagnostic.json`（ignored local raw）
- basis manifest: `results/task039_v7_streamed_bottom_basis_producer_mpi8_a33c19e7/numerical_output/streamed_basis_packet/manifest.json`（ignored local raw）

所有 `results/`、`.npy`、stdout、marker、sample 和 ledger 均为 ignored raw artifact，未纳入
本次提交。完整 raw SHA256、两次 attempt 分类、consumer/E Gate 的 `not_run` 状态均保存在
compact JSON；本阶段不提交 raw，也不启动 consumer。
