# Phase F：固定结构 p–h 收敛结论

## 结论

固定物理结构、S polarization、MPI8 的 uniform 主矩阵已经得到 measured decision。
p2 的 h5/h3/h2、p3 的 h7.5/h5/h3、p4 的 h10/h7.5/h5 均有成功
Full3D 与 Hybrid M160 同阶闭合。p3/h10 Full3D 成功，但 Hybrid M160 保留
`formal_not_pass`，没有从表中删除，也没有改写为通过。

| p | 三个成功 h (nm) | 12 分量相邻差是否全部下降 | 正式结论 |
|---:|---|---|---|
| 2 | 5, 3, 2 | yes | measured sequence decision |
| 3 | 7.5, 5, 3 | yes | measured sequence decision；p3/h10 Hybrid negative 保留 |
| 4 | 10, 7.5, 5 | yes | measured sequence decision |

尽管三组的 12 分量相邻离散差均下降，本任务没有独立 continuum reference，也没有
证明已经进入 asymptotic regime，因此三组统一记录：

```text
observed_convergence_order_status = convergence_order_not_established
grid_convergence_proven = false
continuum_reference = false
```

## 共同 h=5 nm 的 p 趋势

以 p4/h5 为当前最佳离散参考，p2/h5 → p3/h5 → p4/h5 的 official R/T/A、五平面
E/H、接口 E/H 与 significant-order complex amplitude 的误差向量明显缩小。p4/h5
相对 p3/h3 的 12 分量工程精度优势也已在 Case092 记录中通过。这里不把这种离散趋势
升级为连续解收敛证明。

## 用户新增点

p2/h1、p3/h2、p4/h3 均按 staged Gate 执行：Full3D 在 assembly 后由保守
factorization 资源上界受控停止；p3/h2 与 p4/h3 的 Hybrid M160 shard 通过，p2/h1
Hybrid 在 field recovery 超时并保留 negative。它们不进入成功 uniform 三点序列。

完整数值见 `fixed_geometry_ph_convergence.csv`；机器可重算记录见
`benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/convergence_summary.json`。
