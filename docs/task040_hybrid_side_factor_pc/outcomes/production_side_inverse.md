# V4-6 packet-independent production side inverse

## V4-0 状态

`not_run_by_v4_1_identity_gate`。V4-1 在 canonical source-row bridge 资格化前停止；
V4-6 没有获得进入 production candidate 的授权，也没有新的数值/资源证据。原有 V3-4
历史合同保留如下，作为后续前置边界而非当前结果。

## 状态

`not_run_by_v3_2_numerical_gate`。只有 V3-3 选出 `rank <=512` 的 bounded coupled coarse 后才允许进入；
V3-2 数值 Gate 未通过，当前
没有生产 candidate、没有 full-side replacement、没有新的资源或数值结果。

## 生产重构合同

fresh 进程必须使用冻结的 lower Fourier/Floquet modes、upper M480 QEP modes、V3-3 选出的
linear-combination coefficients 和显式 bare-F action，重建同一 bounded coarse basis 与
coarse matrix。V2 exact packet 只能作为 oracle 对照，不能读取 exact U/V owner-row 值作为
生产输入；不得构造 exact-interface oracle。

必须独立证明：

- mode-key、coefficient 和 basis identity exact；
- oracle-vs-production basis principal-angle sine max `<=1e-8`；
- oracle-vs-production coarse action relative error `<=1e-8`；
- one-apply/FGMRES Gate 通过；
- exact-interface、full-side、global factor 均为 0，且无 FE numeric allgather/full basis replica。

若无法达到上述重构或数值 Gate，分类：

```text
EXACT_ORACLE_DEPENDENCE_NOT_REMOVED
```

并停止，不得把 packet-dependent fixed-case 结果提升为可扩展 side inverse。

## 当前边界

V3-4 尚未运行；没有 production basis、coarse action、residual、RSS、factor inventory 或
formal root。V3-5 bounded local patch、V3-6 bottom/top/full 和 V3-7 h3 均因此为
`not_run_by_v3_2_numerical_gate`。

## Review V4-1 当前收口

V4-6 fresh packet-independent reconstruction 未运行。没有 selection rule、production
basis、coarse action、one-apply/FGMRES residual、factor、DoF、RSS 或 wall；原因是冻结
exact spool 没有可资格化的 source-row/key bridge，无法证明 fresh process 能重建相同数学
对象。这不是 production side inverse 已失败的证据，也不是对 0.7 nm 的判断。V4-6 及其后
V4-7/V4-8/V4-9/V4-10 均为 `not_run_by_v4_1_identity_gate`。
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。
