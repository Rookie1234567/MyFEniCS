# Task033 Phase D2：variable-p / hp capability 与 zoning 设计

## 审计结论

```text
native cellwise variable-p H(curl) = not qualified
disposition = fail_closed_no_hp_zoning_prototype
target-scale variable-p PDE = not approved and not run
small p2/p3 microfixture = not triggered
```

正式运行时环境为 DOLFINx `0.10.0.post2`、Basix `0.10.0`、UFL
`2025.2.0.post0`。审计直接导入运行时并检查公开符号，同时逐项区分“API 存在”和
“已经证明 variable-p H(curl) 语义”。

| 公开能力 | 观察 | 能否证明 cellwise variable-p H(curl) |
|---|---|---|
| `basix.ufl.element(..., degree)` | 存在 | 否；只说明单个 element 可选 degree |
| `basix.ufl.mixed_element` / UFL mixed space | 存在 | 否；混合 field 不等于同一 H(curl) 场逐 cell 变阶 |
| `dolfinx.mesh.create_submesh` | 存在 | 否；submesh API 不证明跨区切向共形 |
| `dolfinx.fem.mixed_topology_form` | 存在 | 否；跨 cell topology 装配不等于 unequal-p 约束 |
| `dolfinx.fem.functionspace` | 存在 | 否；未观察到原生 cellwise degree map |

缺失的是可运行、稀疏、可维护且有证据的完整语义链：

1. unequal-p 相邻 Nédélec cell 的切向连续；
2. edge/face orientation 与高阶自由度变换；
3. 周期配对面上的 p 同步；
4. 高阶 matching trace；
5. MPI ownership 与跨分区约束；
6. submesh/multimesh 方案的可维护耦合。

因此 Review V5 的条件 microfixture 没有被触发。强行做一个自定义 mortar 或任意
unequal-p constraint 小例子，只能证明 bespoke 原型“能跑”，不能证明上述原生路线，
反而会越过审阅范围并引入新的正确性风险。

## 当前允许的 fixed-p zoning 设计

这是一份设计报告，不是已实现的 hp solver。可维护的后续路线应优先保持每个
conforming 子域内部 fixed p：

```text
complex 3D end region A: conforming fixed p3 or refined p2
middle modal region: existing QEP/modal representation
complex 3D end region B: conforming fixed p3 or refined p2
periodic paired faces: identical mesh and identical p within each end region
end-to-middle coupling: existing qualified matching trace
```

这样的“zoning”复用现有 domain decomposition 边界，不在相邻体单元内部制造
unequal-p 共形问题。它可作为未来多子域 fixed-p 研究方向，但不能被称为原生
cellwise hp；区域间的物理一致性、负载均衡和 MPI 伸缩仍需单独资格化。

若未来 DOLFINx/Basix 提供或项目引入明确可维护的原生路线，最小重启顺序是：

1. 先冻结公开 API、degree map 和约束语义；
2. 建立两区 p2/p3 周期 microfixture，预测中心 `<1.5 GiB`、上界 `<2.0 GiB`；
3. 验证切向连续、orientation、周期同步、稀疏存储及 MPI1/MPI4 identity；
4. 只有 microfixture 全过后才讨论 target-scale hp，且仍不使用 p4 zoning。

## 与后续阶段的关系

- fixed-p `p3/h7.5` 等精度正结果不依赖 variable-p；
- p2 conforming graded-h / h-adaptive 已移交下一独立任务，在新任务中重新建立 Gate；
- interface buffer 等待 defect/nonuniform-end geometry，不应在当前规则光栅上机械跑矩阵；
- 1 TiB / 0.7 nm 投影移交 adaptive/scalability task，等待实测压缩和高阶模型重校准；
- 本审计不证明未来版本永远不支持 variable-p，只证明当前冻结环境没有合格证据。

正式记录：
`benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/variable_p_capability_audit.json`。
