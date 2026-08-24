# V4-6 packet-independent production side inverse

## V4-0 状态

`planned_conditional_not_run`。V4-0 只完成继承审计；V4-6 必须等待 V4-3/V4-4 形成可重建的
selection rule 和 V4-5 bounded coarse 结果，本页没有 production candidate 或新的数值/资源
证据。原有 V3-4 历史合同保留如下，作为 V4-6 的前置边界而非当前结果。

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
