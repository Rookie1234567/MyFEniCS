# V7 Lane B：streamed bottom Petrov consumer Pareto

这里的“streamed”是一个内存策略：生产好的左右 owner-row 基按 rank 分片保存；在 ownership remap 路径中，consumer 一次装载当前 rank 的全部 512 列 owner rows，再从同一份本地数组切出 `64/128/256/512` prefix，并在下一级前释放校正动作。它减少跨 rank 的全局复制，但不保证校正方向一定能逼近原始 side operator；最终仍由真实 `F` residual 和 coarse `E` 条件数裁决。

## 结论

| 项目 | 结果 | 口径 |
| --- | --- | --- |
| 正式 root | `results/task039_v7_streamed_bottom_petrov_consumer_mpi8_03aa96d8` | source `03aa96d88239c2d6997b6156e80200d25ef9b10d` |
| 进程退出 | `exit=0`，worker finished | 不是崩溃或 telemetry 失败 |
| ownership remap | pass | producer 与 consumer 的 local ownership 不同，但连续全局覆盖和重叠切片校验通过 |
| setup / overall peak | `23.0382080078125 GiB` / `23.0382080078125 GiB` | parent process-tree authority |
| swap | `0` | resource Gate pass |
| resource Gate | component/setup pass | 低于 `84.039305878 GiB` setup hard line；不是完整 workflow 的 direct 资源结论 |
| numerical classification | `NUMERICAL_LIMIT_NOT_REACHED_BY_RANK512` | source-family capacity negative |
| top / outer / recovery / RTA / field | `not_run` | bottom numerical Gate 失败后按 V7 停止 |

这不是 ownership、telemetry 或资源负结果。四个 rank checkpoint 都成功构造了满秩 `E=YᴴFZ`，但五条 mandatory RHS 的 side true residual 均超过阈值；即使 rank512 也没有通过。因此不能进入 top 或 full Petrov，也不能把“内存很低”写成算法通过。

## 身份与输入

| 身份 | 值 |
| --- | --- |
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| selected packet manifest | `results/task039_v4_h4_m480_shared_packet_eaad0f94/manifest.json` |
| selected packet SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| basis manifest | `results/task039_v7_streamed_bottom_basis_producer_mpi8_a33c19e7/numerical_output/streamed_basis_packet/manifest.json` |
| basis manifest SHA256 | `44023b8d8d3932e5cf5d0d42a16711f886e7672570e0318cb0339b44b691c44b` |
| exact-response spool | `results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output`，仅 holdout/oracle |
| MPI / profile | `8 / p6/h4/M480` |

## Rank ladder 与 Gate

同一个 basis packet 依次评估 `64 → 128 → 256 → 512`；没有生成四套独立 campaign。`E` 是 consumer 实际构造的 `YᴴFZ`，不是 producer 阶段的 `YᴴZ`。所有级别 finite、repeat 和 linearity 均通过，`E` 满秩且条件数小于 `1e12`；失败集中在真实 residual。

| rank | E rank / condition | setup s | apply s | holdout s | preferred max | mandatory true residual | checkpoint |
| ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 64 | 64 / `3.219938404e3` | 4.8404 | 10.8347 | 11.3011 | `219.3757739633` | fail（modal+/−、external、random 均超 `1e-2`） | numerical gate failed |
| 128 | 128 / `6.778370040e3` | 10.0348 | 10.9278 | 11.3927 | `210.1809798039` | fail（modal+/−、external、random 均超 `1e-2`） | numerical gate failed |
| 256 | 256 / `5.383690736e4` | 21.5932 | 11.4808 | 11.9527 | `1143.0925334334` | fail（modal+/−、external、random 均超 `1e-2`） | numerical gate failed |
| 512 | 512 / `2.788596049e5` | 51.0698 | 11.5219 | 11.9895 | `1521.8160925296` | fail（modal+/−、external、random 均超 `1e-2`） | final failed checkpoint |

`physical_side_rhs` 在这组冻结输入中是零源，只作 `degenerate_uninformative` 记录；其余五项必须参加 Gate。代表性 residual 如下：

| rank | modal+ | modal− | external | random773 | random779 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 64 | 219.3757739633 | 217.2689440765 | 125.4123354546 | 177.6153349639 | 153.6759680317 |
| 128 | 105.3115700497 | 138.6651987713 | 210.1809798039 | 303.6753512681 | 310.5312967199 |
| 256 | 1143.0925334334 | 862.3979202737 | 963.5457075556 | 604.2424820465 | 829.5233366872 |
| 512 | 1230.8779127949 | 1293.3488779249 | 1521.8160925296 | 1007.8760520986 | 1147.0049515163 |

正式 mandatory true residual 上限为 `1e-2`；modal+/modal−/external 的 preferred 上限为 `1e-3`。这里所有 mandatory 值都远超上限，因而分类是 source-family numerical capacity negative，而不是“再提高内存预算即可通过”。

## 生命周期与资源证据

| 对象/阶段 | measured 结果 |
| --- | --- |
| base | whole-endcap ILU(0)+固定 DtN Woodbury；base factor `1` |
| exact/global direct factor | `0/0` |
| nested KSP | `0` |
| correction action | 每个 checkpoint 销毁；basis 为 borrowed readonly owner-row storage |
| basis ownership | producer ranges 与 consumer ranges 不同；remap 仅读取相交 shard，不 materialize global basis |
| holdout/spool | 在 basis ready 后才打开；结束释放 arrays/Vec |
| setup cleanup | setup destroyed=true，collective cleanup=true，packet mmap released=true |
| top/both/full | `not_run` |

峰值 `23.0382080078125 GiB` 是 bottom component/setup 阶段 parent process-tree 的同时峰值；它不是单 rank 对象大小，也不能与对象 bytes 相加。该 component 峰值低于 V7 setup line，但本轮没有完整 workflow 的 direct 资源比较；完整 workflow 的已资格化正结果仍是 Lane A 的 `80.0258560180664 GiB`。本轮 numerical Gate 失败说明 component 内存节省没有转化为合格 side correction。

## 前一轮 implementation failure（保留，不重写）

旧 root `results/task039_v7_streamed_bottom_petrov_consumer_mpi8_c13cba94` 的 exit=2 是 producer/consumer owner range 假设错误，checkpoint 未进入 numerical ladder。它只作为实现失败历史证据保留；本次 remap 后的 exit=0 结果与该失败分开统计。

## 证据边界

- compact record：[task039_v7_petrov_bottom_consumer_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_petrov_bottom_consumer_v1.json)
- current diagnostic: `results/task039_v7_streamed_bottom_petrov_consumer_mpi8_03aa96d8/numerical_output/v3_v7_diagnostic.json`（ignored local raw）
- current raw hashes are recorded in the compact JSON; `results/`、basis arrays、stdout、markers、samples 和 ledger 不提交。

本结果只关闭 bottom consumer ladder。它不授权 top、both-side、outer/recovery 或 full Petrov；Lane C 的独立 graph-only audit 仍需单独记录，不能用本次 residual 或 packet 结构代替。
