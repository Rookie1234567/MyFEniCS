# Task039 Review V9：阶段响应与结项边界

## 先给结论

本轮 V9-2 正式 bottom component 已完成三组固定 two-layer supernode factor 的构造、两种
候选 action 的顺序评估和完整释放。construction resource 与 lifecycle 释放通过，retained 明确为
`not_run`；但 `SN2-J` 与 `SN2-SGS` 对五个非退化
frozen source 都产生非有限输出：SN2-J 为 `Inf`，SN2-SGS 为 `NaN`。因此本轮是
`V9_2_FIXED_TWO_LAYER_SUPERNODE_CONTROLLED_NUMERICAL_INSTABILITY`，不是资源停止，
也不是已证明的通用 MUMPS/factor API bug。

`physical_side_rhs` 的输入范数为 `0`，因此 relative residual 本身退化、`mandatory=false`，
不进入最坏值或 Gate pass；但这不代表 action 输出正常：SN2-J 同样输出 `Inf`，SN2-SGS
输出 `NaN`，两者均为 `finite=false`。

worker 的 `exit_status=3` / parent `worker_nonzero` 只是数值 Gate 失败后的受控 transport
分类；raw worker status 是 `component_stability_failed`，parent `termination=null`、
`warning=false`。V9-3、V9-4、top、both-side、full formal、0.7 nm PDE 均保持
`not_run`，不是把未运行阶段写成失败。

| 阶段 | 状态 | 关键证据 |
|---|---|---|
| V9-0 inherited audit | completed | 继承 V8 正/负结果与禁止项 |
| V9-1 bare-F/full-side J1/F1 | controlled numerical negative | [V9-1 outcome](outcomes/v9_bare_f_vs_full_side.md) |
| V9-2 SN2-J/SN2-SGS | controlled numerical negative | [V9-2 outcome](outcomes/v9_supernode_side_preconditioner.md)、[compact record](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v9_supernode_side_preconditioner_v1.json) |
| V9-3 direct full-side FGMRES | not_run | V9-2 没有稳定 preferred action |
| V9-4 ranks 16/32/64 | not_run | 没有进入 compressibility 阶段 |
| top / both-side / full formal | not_run | bottom stable-action Gate 未通过 |
| 0.7 nm PDE | not_run | 不具备合法的 bottom solver 入口 |

## Review §13 的十个问题

### 1. bare `F` 与完整 `A_side` 的误差来自哪里？

V9-1 已把两种真实 operator action 分开计算。J1 的 mandatory worst `r_F=50.7689715097`、
`r_A=50.2410648372`，比值约 `0.970–0.990`；F1 的 worst `r_F=367.2128685567`、
`r_A=141.0763808200`，比值约 `0.354–0.430`。因此主要问题在 single-layer sweep 对
bare `F` 的近似本身；DtN/Woodbury 没有放大 J1，反而缓和 F1，但仍远高于 `1e-2`。

V9-2 的 two-layer action 更早暴露为非有限输出，故不再伪造 `r_F` 数值。它说明固定三组
supernode 在本次 h4 代数下不稳定，而不是推翻 V9-1 的 operator 分离。

### 2. 三个 two-layer supernode 是否显著改善 J1/F1？

没有得到“改善”的证据。三个 factor 均构造成功，但 SN2-J 的五个 mandatory output 为
`Inf`，SN2-SGS 的五个 mandatory output 为 `NaN`；finite、repeat、linearity 和 residual
均无法通过。SN2-J/SN2-SGS 的稳定 preferred 均为 `null`，不能拿它们与 J1/F1 的有限
但很差的 residual 做性能排序。

### 3. 是否已有通过的 full-side FGMRES budget？

没有。V9-3 direct full-side FGMRES 没有运行；V9-2 没有产生可供 inner solve 使用的唯一
稳定 action，不能预先声称有 `J1/F1` 或 supernode 的 FGMRES budget。

### 4. 当前 bottom component 的最低内存、残差和时间是什么？

V9-2 同一 MPI8 consumer process 的 parent process-tree peak 为
`24494911488 B = 22.812664031982422 GiB`，construction/overall resource `<=45 GiB`，
swap=`0`。总 parent wall 约 `473.941922 s`；SN2-J 与 SN2-SGS 的 worker marker interval
分别为 `6.183576241 s` 与 `23.778006799 s`。但两个候选五个 mandatory probe 都非有限，
所以这是“低内存但数值不稳定”的 component 负结果，不是完整 workflow 正结果。

### 5. 960 个 sampled modal columns 的成本是否可接受？

没有在 V9-2 运行 10 modal samples，也没有进入新的 sampled-column campaign。V7/V8/V9-1
的既有 sampled/modal 证据继续保留，但不能把它们移作 V9-2 的新结论。

### 6. Schur update 是否能压到 rank 64？

没有运行 V9-4 的 ranks `16/32/64` compressibility audit，故没有新的 rank-64 结论。旧 V7
modal-Schur rank960 证据只属于 Lane A full formal，不证明本 V9 supernode 路线的压缩性。

### 7. 当前最佳完整 workflow 是否仍为 `80.025856018 GiB`？

是。V7 Lane A exact-side full formal 仍是唯一完整 workflow 的正式低于 matched direct
结果：peak `80.025856018 GiB`，matched direct `93.377006531 GiB`，节省 `14.298113646%`，
1 outer iteration，recovery/physics/checker 通过。V9-1/V9-2 都是 bottom component，不能
改写这一完整 workflow authority。

### 8. 达到 20%/50% saving 的主要 blocker 是什么？

第一层 blocker 是算法稳定性：V9-1 的 single-layer sweep 对 bare `F` 的 residual 已远超
`1e-2`，V9-2 的固定 two-layer action 又产生 `Inf/NaN`。第二层是完整 side factors 和
生命周期仍需满足 45/30 GiB 的分阶段证据；V9-2 只完成 construction，retained 未运行。
因此不能从 22.812 GiB component RSS 推导 20% 或 50% full-workflow saving，更不能宣称
0.7 nm 可行。

### 9. 哪些代码可进入 production，哪些只能 research-only？

V8 layer graph/block action、V9 tiny exact Schur/supernode algebra及 focused tests可以作为
受审的 research infrastructure 保留；V9-1/V9-2 的正式 h4 routes 是 research-only evidence。
由于 V9-2 没有稳定 action，不应提升为 ordinary/default solver、full-side production PC 或
新的 FGMRES 默认路径。普通 defaults 未改变，master 未修改。

### 10. top/both/full/0.7 nm 是否运行？

均未运行：V9-3 bottom/top direct full-side FGMRES、V9-4 ranks16/32/64、top、both-side、
full formal、10 modal samples、recovery/RTA/field export 和 0.7 nm PDE 都是 `not_run`。
停止原因是 V9-2 没有唯一稳定 preferred action；这不是这些阶段已经数值失败。

## 资源、生命周期和身份

三组 supernode row coverage 为 `49140/41580/41580`，完整覆盖 `132300` rows；cross lower/upper
各为 `2`。同一组三 factors 在 `SN2-J → SN2-SGS` 间复用，factor ready=`3`，最终 cleanup=`0`，
full-side/global/nested factor=`0/0/0`。selected packet=`false`，QEP=`0`，exact holdout spool
只在 setup 后读取并释放。由于没有 preferred method，retained state 为 `not_run/not_available`，
不是 `30 GiB` resource failure。

本次 raw evidence 位于 ignored local path：

```text
results/task039_v9_h4_layer_supernode_bottom_mpi8_266a1acc/
```

source SHA 为 `266a1acc0eb7a4515815e34414f89e183c15e9ef`；compact record 绑定 13 个 raw 文件
hash、输入/physical/config identity 以及 inherited exact-bottom holdout catalog。详见
[V9-2 compact record](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v9_supernode_side_preconditioner_v1.json)。

## 检查边界与 selective merge

本 closeout turn 只改 compact evidence/docs，不改 Python，不重跑 PDE/heavy；full repository
pytest 和 CI 均 `not_run`。建议 selective merge 时将 V9-2 compact record/outcome 归入
`compact evidence/docs`，tiny exact Schur/supernode 实现归入 `research-only`；不把 formal
V9-2 route 提升为 production default。V5/V6/V7/V8 负结果、首次 implementation failures
和所有 raw roots 均保留。
