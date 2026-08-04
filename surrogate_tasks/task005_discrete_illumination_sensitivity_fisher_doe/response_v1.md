# Task005 Response V1

## 结论

Task005 M0–M4 已完成。16 个冻结 nominal 角度均在不可变 Task004
`train112` 中恰好出现一次；M1 coarse/half 审计和 M2 16-angle
central-difference 数据集均通过独立 checker；Fisher 单角度、双角度、
三角度和四角度组合均已按 M0/M1/M2 合同计算；推荐三角度在三个
off-centre 几何上通过局部恢复 Gate。最终 DOE lock 已建立，当前状态为
review pending。

## 固定身份

```text
implementation_sha = d24395b377259da129a81384f88d8a4ad74602d2
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
model_id = S_PROD_FULL3D_STATIC_P5_H10_NY4
solver_route_id = full3d_static_uniform_n1curl_p5_h10_ny4
observable = task002.fixed-n0-orders.v3
MUMPS ICNTL(14) = 40; MPI2; thread1
```

Task004 保持 `closed_controlled_negative`。其 train112 只读复用；Task004
blind24 未运行且未访问。

## M0/M1/M2

- Case131：16/16 tuple、source/config、扰动域和 nominal reuse 全部通过。
- M1：A00、A07、A09、A14、A15 的 coarse/half 共 40 个 fresh-process
  Full3D 状态全部 `measured_pass`。在 M0 aggregate 与 M1 order-total、h/w
  两参数上，5/5 角度均满足 N1 的 cosine、relative-L2、top-SNR sign 和
  A14/A15 约束；h 与 w 均锁定 half step（1.25 nm、0.25 nm）。
- M2：16 角度四状态共 64 个 production state，其中 20 个 exact reuse，
  新增 44 个；Case132 从 raw arrays 重建 M0/M1/M2 中央差分并通过 hash
  checker。没有混入 Ny3、p4、Hybrid、P 偏振或 validation response。

## Fisher 与恢复

穷举规模为 16 singles、120 pairs、560 triples、1820 quads。按 M0/M1
在 N1/N2 下的 full-rank、worst-case minimum eigenvalue、logdet、condition
顺序，冻结推荐组合：

```text
A05 = (grazing=2°, azimuth=0°)
A07 = (grazing=2°, azimuth=90°)
A09 = (grazing=4°, azimuth=60°)
```

Task001 基准 A14+A15 仍被保留并单独比较，未被删除或重命名。

对 G1 `(118.75,16.75) nm`、G2 `(121.25,17.25) nm`、G3
`(118.75,17.25) nm`，使用冻结 nominal Jacobian 的 M1/N1 order-total
线性恢复均通过 `|Δh|≤0.5 nm`、`|Δw|≤0.1 nm`。最大观测误差为
`0.0361 nm`（高度）和 `0.00121 nm`（宽度）。

## 预算与边界

```text
new FEM = 40 (M1) + 44 (M2) + 9 (M4) = 93 <= 96
formal inversion = not performed
continuous/arbitrary-angle surrogate = not started
Bayesian inversion = not started
```

完整证据见 `outcomes/summary.md`、各阶段 JSON、Case131/Case132 checker、
`FISHER_COMBINATION_RANKING.md`、`OFF_CENTRE_RECOVERY.md` 和最终 DOE lock。
现按任务合同停止，等待审阅。
