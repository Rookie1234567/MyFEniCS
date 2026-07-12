# 合并建议

## 决策

```text
merge_code = yes_after_review
merge_docs = yes
merge_benchmarks = yes
production_default_change = no
merge_task027_whole_branch = no
```

## 建议合并内容

| 类别 | 内容 |
|---|---|
| stable solver | exact condensation、fixed sparse coarse、owner-computes physical slabs |
| runtime | 目标Stage4只装配接口 |
| telemetry | ordinary 3D total peak MPI RSS |
| tests | condensed与physical-slab MPI回归 |
| benchmark | 独立configs/scripts/gates/records |
| docs | Task000-027审计与用户文档重建 |
| history | Task021-027核心闭环文档 |

## 不建议合并

Task027 whole branch、spectral/GenEO/HPDDM代码、Task020-Task025研究runner、raw_runs、coarse cache、mesh、VTU/XDMF/HDF5和OOC文件。

## 风险判断

h5/h3/h2 clean branch 的迭代数与Task027完全一致，h2 residual与RTA闭环通过，新增代码测试覆盖MPI owner、empty owner和cache certification。剩余风险主要是参数域外推广，而不是当前目标case复现。
