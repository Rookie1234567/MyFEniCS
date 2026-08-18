# V5-S：当前生命周期 p6/h5 Hybrid direct sidecar

V5-S 只测一个问题：在 5 nm、1°、S、p6/h5、M480、MPI8 下，当前已经接入 shared packet 和
“先释放 direct factor、再恢复/后处理”的 Hybrid-direct 流程实际占用多少资源。它是
nonblocking sidecar，不改变 V4 h4 主线，也不是网格收敛实验。

## 1. 身份与 packet

| 项目 | measured / derived result |
|---|---|
| 源码 | `57184ea97775f623c1b8c04b144546e99712a9c9`，clean；profile=`v5-h5` |
| 物理/离散 | 5 nm、1°、phi=0、S、p6/h5、MPI8、M480；ordinary defaults unchanged |
| packet | `results/task039_v5_h5_m480_shared_packet_57184ea9`；scope=`task039_v5_h5_m480` |
| manifest | SHA256 `31c26876eef22fb3673152f504e636e1486379f5e54190f8954111ceec122d76` |
| canonical identity | SHA256 `176a3ada097136a77da7cb390b7eb4b5cdc3c8736f383e1d4c1a943a5a770c89`；source SHA命中当前提交 |
| packet layout | 8 ranks、global size 6685、4×8=32 个 owner-row mode-major complex128 shard；逐文件 hash/shape 通过 |
| external inventory | 动态 600 keys，hash=`ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a` |
| consumer QEP | `qep_calls=0`、`consumer_qep_required=false`；没有重跑 QEP |

packet producer 只运行一次，状态为 `controlled_stop_packet_written`，exit 0；全过程
process-tree RSS peak=`9098.5625 MiB`，elapsed=`1111.204334 s`，packet write
`0.768952062 s`，swap=0。PSS/USS 未测。

## 2. Direct consumer 结果

consumer 的 reuse/consumer-only wall=`2636.955775 s`，worker numerical total=`2633.759742 s`，
process-tree RSS peak=`51564.7890625 MiB = 50.3562393188 GiB`，swap=0；PSS/USS 为
`not_measured`。warning=170 GiB、critical checkpoint=195 GiB、absolute hard
`224000000000 B` 均未触发，exit status 为 2，worker status 为
`physical_integration_failed`。这是严格数值 Gate 的 controlled-negative，不是资源
停止，也不是 MPI/packet 接线失败。

| Gate | 实际值 | 限值/解释 | 结论 |
|---|---:|---:|---|
| monolithic true residual | `8.826952439936801e-10` | `<=1e-9` | pass |
| condensed full-operator residual，bottom | `1.4055939377955027e-11` | `<=1e-9` | pass |
| condensed full-operator residual，top | `1.0501690969564719e-9` | `<=1e-9` | **fail，borderline** |
| interface electric projection，bottom/top/combined | `4.87765e-12 / 1.67522e-11 / 1.67093e-11` | `<=1e-8` | pass |
| exact variational conormal traction，bottom/top | `1.16960e-11 / 8.20353e-10` | `<=1e-8` | pass |
| sampled traction-density proxy，bottom/top | `0.0346819 / 0.00465894` | `<=1e-2`；diagnostic-only | bottom fail；不替代 exact dual |
| R/T/A balance | `0.7397405131 / 0.0002157492 / 0.2600437378` | finite | pass |
| A_volume / closure | `0.2600443739 / 6.36106101e-7` | closure `<=1e-5` | pass |
| canonical exports | bottom/top × active-trace/full-FE 四项均 pass | raw manifest/hash 保留 | pass |
| selected E/H | direct payload `results/task039_v5_h5_hybrid_direct_sidecar_mpi8_57184ea9/numerical_output/task039_direct_payload.npz`，SHA `de518fc1c3194f52d712e179051b8ab3fd86e47d6188bc63c6c2b94febf7446e`；E/H shape `[5,20,40,3]`、complex128、finite，E/H SHA `66740359b705f22a939bb4136e644d857296e1f7f372fcb4ec8ad5c00f576e72` / `7b780cc1a9b5e5aca9826896bd78bff9605a2ce6cf07e386fbb8703a21c01b43`；h diagnostic native/curlE E/H 亦为 `[7,20,40,3]`、finite | measured/persisted |
| lifecycle/swap | factor/system release before postprocess；cleanup collective；swap=0 | V5 contract | pass |

因此不能把本 run 分类为 `TASK039_V5_H5_CURRENT_DIRECT_RESOURCE_SIDECAR_MEASURED`，也不能
把 exact traction 的通过扩大成 top condensed full-operator 通过。该负结果的直观原因是：
线性 solve 的主 residual 已在限值内，但 top 侧恢复后的 condensed full-operator 检查略超
`1e-9`；另一个 sampled traction-density 只是诊断代理，bottom 超过 `1e-2`，而正式的
variational conormal dual 仍通过。按合同不放宽阈值、不重跑。

本 run 的串行 cold-start 总时间为 packet producer `1111.204334 s` 加上
consumer-only `2636.955775 s`，即 `3748.160109 s`；严格串行的 cold peak 取两个阶段
的最大值，不相加。相对旧 h5 direct 的整体 wall `3773.471512437 s`，cold-start
只派生降低 `0.6707723473%`。`30.1185721%` 仅是 consumer-only 相对旧整体流程的
非同口径补充，不能作为主 wall 结论。

## 3. 生命周期与比较边界

| 证据 | 结果 |
|---|---|
| packet basis | 先 detach/destroy；`qep_calls=0`、mmap/reference released；factor 建立前 modes 已释放 |
| MUMPS | `INFOG(1)=0`、`INFOG(2)=0`；ICNTL(14) requested/observed/verified=`100/100/true` |
| matrix/factor | matrix rows=`105240`、matrix nnz=`697946744`、raw `INFOG(9)=697949552`；factor corrected field未单独提供 |
| release | factor/system 在 postprocess 前释放；第二次同一 manifest/identity rehydrate；recovery 在 release 后；collective cleanup pass |
| 旧当前 h5 direct | RSS=`87064.125 MiB`、整体 wall=`3773.471512437 s`；source=`5bfab734…`；只作 lifecycle implementation comparison |
| 当前 sidecar 相对旧 h5 | RSS 派生降低 `40.7737813%`；cold-start 串行 wall 派生降低 `0.6707723473%`；consumer-only wall `2636.955775 s` 相对旧整体的 `30.1185721%` 仅为非同口径补充；不是网格收敛 |
| h4 current Hybrid direct | RSS=`95618.0546875 MiB`；h5 低 `46.0721208%` 仅作 same-architecture capacity comparison，不是 h5/h4 收敛结论 |
| DQ1 | `49.8236122131 GiB` 是旧 exact-side iterative precedent，不能替代当前 h5 direct，也不能解释本 run |

这些比较严格区分了 measured process-tree RSS 与单 rank/对象容量；不把 packet 的
`205363200` array payload bytes 当作 RSS，不把 h4/h5 差异写成网格收敛。

## 4. 分类与后续边界

compact record 为
[`task039_v5_h5_current_hybrid_direct_sidecar_v1.json`](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_h5_current_hybrid_direct_sidecar_v1.json)。
producer/direct 的 raw 仍在 ignored results，入口和 SHA 均绑定在 record 中。

最终分类：

```text
TASK039_V5_H5_CURRENT_DIRECT_BORDERLINE_CONTROLLED_NEGATIVE
```

V5-S 是 nonblocking sidecar；它不阻断 h4 主线，不授权第二次 h5 producer/consumer，不授权
V5-1，也不改变 ordinary/default 路径。Full3D heavy 仍 deferred；本阶段未运行 full pytest。
