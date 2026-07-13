# 合并建议

## 决策

```text
merge_code = yes_now
merge_docs = yes_now
merge_benchmarks = yes_now
production_default_change = no
merge_research_branches_wholesale = no
environment_status = pass_with_environment_qualification
review_v4_hardening = complete
user_approval = received
master_merge_executed = no
```

## 建议合并内容

| 类别 | 内容 |
|---|---|
| stable solver | exact condensation、fixed sparse coarse、owner-computes physical slabs |
| 2D physics | complex beta propagation、actual port-plane power、lossless/lossy regression |
| ordinary facade | 17 个安全 preset；demo/target 分离；默认 Stage1 direct |
| direct profiles | MUMPS default/OOC/BLR，身份保持 direct |
| tests | 115 passed、10 skipped；MPI4 每 rank 14；V4 文档/runner contract 通过 |
| benchmark | 13 case-contained cases、Case002/003 records、148 automatic Gates |
| docs | 15 篇核心 Quick Start、11 篇核心 Walkthrough、统一 Theory |
| history | Task021-Task027 已选择性整合的核心闭环文档 |

## 不建议合并

历史 research branch 整体、失败 solver runners、raw runs、用户 `papers/`、coarse cache、mesh、VTU/XDMF/HDF5 和 OOC 临时文件。

## 风险判断

frozen target h5/h3/h2 的 residual、R/T/A、RSS、物理模型和 provenance 继续通过；Case002/003 又为 2D explicit/auxiliary 与有损功率提供 machine-readable regression。V3 把 preset 身份、教程深度、源码准确性和 case 文件结构加入自动测试，维护风险显著下降。

剩余风险是参数域推广、Stage2B/2C 精度、h1.5、near-Rayleigh 和基础镜像不可公开拉取，不是当前 frozen case 的回归失败。

Review V4 的 M1–M3 已全部关闭，用户已明确许可合并。本分支现在可通过普通 merge commit 进入 `master`。
