# H2A exact-class block inventory：资源硬停与未资格化证据

## 结论

**H2A = `GATE_FAILED_RESOURCE / NOT_QUALIFIED`。** 本轮没有证明局部因子、平滑器或 PDE 数值算法失败，也没有证明它们通过；正式运行在高阶形式编译阶段因进程树 RSS 超过 H2A 的 1,100,000,000 B 上限而受控终止。H2B、DtN、H4 和 PDE 均未运行并保持锁定。

H2A 的任务是给每种“完全相同的局部问题”建立一个代表性局部块清单：几何、材料、方向和 Floquet 局部约束都相同的 cell 共享一个 exact class。之后理论上可以每类只保存一个 LU 因子，避免每个 cell 各存一份大矩阵。这个阶段只是 inventory/factor preflight，不是已经实现的约束逆或 smoother。

本轮实际停在 p6/h10 的 FFCx/GCC form JIT。它已经完成 mesh、有限元空间和 Floquet MPC，但还没有进入 key discovery 或 factorization，因此不能把缺失的 class、factor、payload 和 materialization 字段补成 0 或 false。

## 固定范围与资格 Gate

| 项目 | 冻结值 / 资格要求 |
|---|---|
| operator | `B0 = K_curl + k0^2 M_abs_epsilon`，仅作 coercive proxy |
| 正式范围 | p6/h10、MPI1 singleton、固定 production geometry/material/Floquet path |
| launch | direct qualified singleton；旧 mpiexec 仅属于 v1/v2 launch-only 尝试 |
| form JIT policy | v5 为 `cffi_extra_compile_args=["-O0","-g0"]` |
| timeout | 1800 s |
| H2A RSS Gate | `<=1,100,000,000 B` |
| swap | `0 B` |
| class Gate | unique exact classes `<=32` |
| factor + metadata Gate | `<=400,000,000 B` |
| refinement Gate | class growth strictly sublinear于 cell growth |
| source | 每次正式尝试起止 clean 且 SHA 稳定 |

“payload”是程序长期保留的数值数组字节数；“process-tree RSS”是整个 worker 进程树在运行时占用的常驻内存。两者不是同一口径，且本轮没有 worker summary，所以只有 RSS 观测可用。

## 全部尝试

| 尝试 | source SHA | 启动/阶段 | 实际结果 | 分类 |
|---|---|---|---|---|
| [v1 raw](../../../benchmarks/artifacts/task037_extra_h2a_641474d) | `641474d1d8a4d1fde905c680ce99ba97dfd3b1d3` | `mpiexec -n 1`；PMIx sandbox listener failure | `0.2682856109458953 s`，`4,673,536 B`，swap 0；无 worker | launch-only，numeric formal attempt `0` |
| [v2 raw](../../../benchmarks/artifacts/task037_extra_h2a_641474d_v2) | `641474d1d8a4d1fde905c680ce99ba97dfd3b1d3` | 同一 mpiexec/PMIx sandbox launch failure | `0.2621486659627408 s`，`0 B`，swap 0；无 worker | launch-only，numeric formal attempt `0` |
| [v3 raw](../../../benchmarks/artifacts/task037_extra_h2a_36272cb_v3) | `36272cb11e74390fdd17fa14f9e406a58fa36be4` | direct singleton；完成 MPC 后进入 form compile | `1,107,120,128 B`，超限 `7,120,128 B`；swap 0；`25.49026272399351 s` | 真实 setup/form-JIT 失败，未到 inventory |
| [v4 raw](../../../benchmarks/artifacts/task037_extra_h2a_fdda595_v4) | `fdda595a70b066dd9a181ec7dd287a2d6896322a` | default-kernel 等价布局修复后进入 form compile | `1,118,916,608 B`，超限 `18,916,608 B`；swap 0；`25.201660085935146 s` | 真实 setup/form-JIT 失败，未到 inventory |
| [v5 raw](../../../benchmarks/artifacts/task037_extra_h2a_26bc171_v5) | `26bc171b35cce60b3b9197027e808f0af4d628d0` | 固定 O0/g0；完成 MPC 后进入 form compile | `1,153,503,232 B`，超限 `53,503,232 B`；swap 0；`26.986158804968 s` | 最后一次授权 heavy，`GATE_FAILED_RESOURCE` |

v4 的 default-kernel 修复没有降低 p6 C 文件体积：仍为 `54,429,950 B`。小型 p2 数值回归保持等价，误差 `<=1e-11`；这不改变 p6 process-tree RSS 结论。v5 的 O0 隔离编译诊断也不能改写正式 process-tree Gate。

## v5 实际阶段边界

| marker / 事实 | 实测状态 |
|---|---|
| `mesh_build_ready` | 已完成，252 cells |
| `function_space_ready` | 已完成，global rows `173802` |
| `floquet_mpc_ready` | 已出现；Floquet MPC 已完成 |
| 最后 marker | `form_compile_started` |
| `form_compile_ready` | 未出现 |
| key discovery / class inventory | `not_run` |
| factorization / LU | `not_run` |
| p2/h10、p2/h5 refinement cases | `not_run` |
| constraint count | `unavailable`；summary/marker 未写入 |
| finite/deterministic/materialization audit | `unavailable`；worker summary 缺失 |

因此，252 cells 和 173802 rows 是 marker 直接测得的值；不能把冻结预期的 `9210` constraints 写成 actual。也不能据此声称“没有 per-cell factor、没有 slab factor 或没有 global matrix”已经通过 Gate；这些 audit 尚未产生。

## 失败 Gate 与根因边界

| Gate | 实际 / 限值 | 判定 |
|---|---:|---|
| process-tree RSS | `1,153,503,232 B / 1,100,000,000 B` | FAIL，触发受控终止 |
| swap | `0 B` | 观测为 0，但不足以挽救整体资格 |
| completion | `26.986158804968 s` | 在 timeout 内，但 RSS 已先失败 |
| worker summary / qualification | 缺失 | fail-closed |
| class `<=32` | unavailable | 未资格化 |
| factor + metadata `<=400,000,000 B` | unavailable | 未资格化 |
| p6 rows / constraints | `173802 / unavailable` | 部分可观测，不构成 identity Gate |
| refinement sublinear | unavailable | 未运行 |

可支持的根因边界是：已存活的 mesh、有限元空间、Floquet MPC 与 p6 FFCx/GCC form JIT 进程树叠加后超过 1.1e9 B。现有证据不能把峰值精确归因到某一个对象，也不能断言单个 C 编译对象的独立占用就是该差值。

### 隔离编译诊断（仅 diagnostic）

对同一 `54,429,950 B` C 文件进行一次固定 O0 编译：

| 项目 | 值 |
|---|---|
| C 文件 SHA256 | `556489845e2e85cd8166cc8cb8e259b062a97508f139d86abdcee11105c2aa08` |
| compiler flags | `-O0 -g0 -fPIC` |
| exit | `0` |
| elapsed | `7.91 s` |
| maximum RSS | `674,521,088 B` |
| object | `43,713,432 B` |

这是隔离 `/usr/bin/cc` 诊断，不是 H2A process-tree 测量，也没有把它当作正式 Gate 改善。

## 未验证的后续建议

若要继续，只能由新的 review 授权一个窄方向：让相同 form JIT 在 MPC 建立前或独立 staging process 中完成并退出，再加载 cache，同时保持物理定义和全部 H2A Gate。这个方向本轮没有实现、没有运行；H2A rerun 预算已经耗尽，不应在本轮再启动 heavy。

## Raw evidence 索引

| 尝试 | watchdog summary SHA256 | timeline SHA256 | raw 路径 |
|---|---|---|---|
| v1 launch-only | `4f137cf4f9899f84f41f796940fd1050906ae1033ba6fdee764da27a2f05dc6f` | `52b7ea96c9d70b5b5952a24e18d68f78af193537f0de54d36a27be47e766c326` | [641474d](../../../benchmarks/artifacts/task037_extra_h2a_641474d) |
| v2 launch-only | `6eb85703306a82fd3aad302cc7ce458a2946e1b90760183b0de433088ab6eedc` | `1b44154b802c6bbbb680921d8125d29689c60672d674666c598ea648c0f42834` | [641474d_v2](../../../benchmarks/artifacts/task037_extra_h2a_641474d_v2) |
| v3 | `57eaba88c120e6fbd9b6c094f1d63f95344a61dd96dde383fab30d439723a7fc` | `b2b425cffc354deac50ec97a66de5d3dce1128cc91ffe1cd1b35474d4ddecc21` | [36272cb_v3](../../../benchmarks/artifacts/task037_extra_h2a_36272cb_v3) |
| v4 | `99f109c8f4ad57787c41f45eeecae11f904145236a45feee7ba05f08513a57a8` | `d1fa8cb88034f54efab523c1bff914a09b005da0b007cc60ab7588cf5045d609` | [fdda595_v4](../../../benchmarks/artifacts/task037_extra_h2a_fdda595_v4) |
| v5 | `34894f3973858065bb8c4d5c188f8217ac5318b6a44a3d3f8d9909d5aa1c9e55` | `4ae7ccc87a8fc4920efffc4b28cc44e009e66176d6a04ae0e20ef3a798343764` | [26bc171_v5](../../../benchmarks/artifacts/task037_extra_h2a_26bc171_v5) |

v5 worker stdout/progress SHA256 为 `5262a0d2d1596816286deb81e6bf2161788bdf315e1ed11f82d42b8040e069d1`，root PID 文件 SHA256 为 `dd3f527d0e8d7dc7fd9ba82f0be87b6b893b4b0357b521dffb9e5ee8dcfa18af`。v5 没有 `run_summary.json`。

## Compact record、验证与合并边界

| 项目 | 值 |
|---|---|
| compact record | [`h2_block_class_inventory.json`](../../../benchmarks/cases/101_task37_extra_development/records/h2_block_class_inventory.json) |
| compact file SHA256 | `bbc4ed0f5568accf3b301dd5af3c8f85744dd1595a0d89390d36cf3c2dcf28d2` |
| embedded evidence SHA256 | `51c2f113a60560761fb38f0c1ca4f7c9f59ee0fadf16098c68b91fd64e1d4594` |
| raw source SHA | `26bc171b35cce60b3b9197027e808f0af4d628d0` |
| checker source SHA | `d65fcfb5b55c92682c74376dbe1fbefe22766f52` |
| checker result | exit `1`，`gate_failed` |

修复后 checker 的 focused test288 为 `30 passed`，tests 286--288 为 `37 passed`；compileall 和 `git diff --check` 通过，Ruff unavailable。这些是本地测试，不是 CI，也不替代 H2A formal Gate。

本轮代码设计和实际进入的阶段仍未产生 global matrix、constraint matrix、Schur、slab factor 或 per-cell factor 的资格化 audit；不能把“未生成 summary”改写成这些对象已通过禁止项。ordinary default 未改变。H2A cache/runner 在当前结果下属于 research-only、not qualified；compact record 与本文保留负证据，不能提升为 production default。
