# 合并建议

## 决策

```text
merge_code = yes_after_final_review_and_user_approval
merge_docs = yes_after_final_review_and_user_approval
merge_benchmarks = yes_after_final_review_and_user_approval
production_default_change = no
merge_task027_whole_branch = no
environment_status = pass_with_environment_qualification
master_merge_executed = no
```

## 建议合并内容

| 类别 | 内容 |
|---|---|
| stable solver | exact condensation、fixed sparse coarse、owner-computes physical slabs |
| 2D physics fix | complex `beta` 传播判定与实际端口面 modal power |
| ordinary facade | 15 个安全 preset，默认 Stage1 direct |
| direct profiles | MUMPS default、OOC、BLR |
| tests | 105 项完整 suite、MPI4、文档/preset contracts |
| benchmark | 13 cases、configs、records、87 项 checker Gates |
| docs | 五层文档体系、强式到求解器理论、逐模块代码导读 |
| history | Task021-Task027 核心闭环文档 |

## 不建议合并

Task027 整个研究分支、spectral/GenEO/HPDDM 研究代码、Task020-Task025 失败 runner、raw runs、coarse cache、mesh、VTU/XDMF/HDF5 和 OOC 临时文件。

## 风险判断

当前目标 p=2、h5/h3/h2 workstation records 的 residual、R/T/A、RSS、物理模型和 provenance 均通过自动 Gate；2D 有耗 RTA 又有 TM/TE 实跑闭合。剩余风险集中在参数域推广、Stage2B/2C 精度、h=1.5 和基础 complex MPC 镜像不可公开拉取，不是当前冻结案例的回归失败。

因此建议把本分支提交给最终审查。只有审查通过且用户明确许可后才合并 `master`。
