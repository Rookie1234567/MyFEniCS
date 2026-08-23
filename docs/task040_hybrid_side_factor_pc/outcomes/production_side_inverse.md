# V3-4 packet-independent production side inverse

## 状态

`pending_conditional_not_run`。只有 V3-3 选出 `rank <=512` 的 bounded coupled coarse 后才允许进入。当前
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
formal root。V3-5 bounded local patch、V3-6 bottom/top/full 和 V3-7 h3 均因此保持
`pending_conditional_not_run`。
