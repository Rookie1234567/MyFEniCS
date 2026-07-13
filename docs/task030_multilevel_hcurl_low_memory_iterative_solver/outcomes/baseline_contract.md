# 基线合同

- 唯一 h5 基线入口：`benchmarks/cases/031_workstation_iterative/records/h5_reference.json`。
- 该入口固定 `benchmarks/records/workstation_p2_h5_mpi4.json` 及 SHA-256；runner 必须先校验 hash。
- 100-step 对照值从 canonical `history` 中查找 `iteration == 100`，当前为 `2.5737371765314062e-3`。
- h5 canonical：44,698 FE DoF、80 auxiliary DoF、1201 iterations、full true residual `9.839489937056112e-7`、包含 RTA 的 canonical 峰值 `1.9911727905273438 GB`。
- 物理模型、精确 condensed action、MPI4、FGMRES restart100、真残差定义及 official modal R/T/A 不得改变。
- Task030 候选是显式 opt-in；普通默认和 Case031 profile 不变。

在实现筛选器后，本合同还需由测试覆盖：丢失 iteration=100、hash 漂移、字段漂移或 reported/true 残差缺失都必须 fail closed。
