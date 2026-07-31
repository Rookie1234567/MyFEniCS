# Hybrid production readiness assessment 整改报告

## 1. 整改结论

本轮确认原文档存在：

[`hybrid_production_readiness_assessment.md`](hybrid_production_readiness_assessment.md)

原文的大方向仍然正确：Hybrid 对未来 0.7 nm 真正三维问题是必要路线，strong-trace 数学
结构和 scalar-CG selected core 应保留，而 replicated `M²`、all-mode dense RHS、local
direct LU 等 current direct 实现不能机械扩展到目标规模。

需要整改的不是这套长期架构，而是文档仍停留在 Review V4，尚未吸收 Review V5 的接口内移
actual negatives 和最新 exact Cauchy / port-operator audit。整改后，下一步从“继续验证
30/90 接口”改为唯一冻结的 `transfer_optimal_port_modes` fixture；在 fixture 真正通过前
不运行 PDE、不宣称数值修复成功。

```text
scope = documentation_only
production_code_modified = no
new_PDE = not_run
ordinary_default = unchanged
master_merge = not_authorized
evidence_base_head = 7ea6c043dd32732f675a60da36fba31862639e15
latest_numerical_source = c8725e9eedc8a558719008f8762bc79eca48fbb7
```

## 2. 整改前状态

| 项目 | 值 |
|---|---|
| HEAD 版本文档 SHA-256 | `29ece3e125d88f604d875a06cca602313bb2b6af99cab1edbf23e9931f1a1a3f` |
| 整改前工作副本差异 | 只有 `mode/plane` 行一个尾随空格，无实质内容修改 |
| 整改前工作副本 SHA-256 | `2495c3ed4554cb5d134dcd919f36e97644702254502190b76749c8c63dd203c4` |
| 整改后文档 SHA-256 | `22967f2b8e818cc9731a47f2bcf07199c3d5365bc20a1a8a6d094a7865afa80b` |

未跟踪的 `code_audit_and_0p7nm_roadmap_report.md` 来源未在本轮确认，故没有打开修改、暂存或
合并；本整改报告使用独立、明确的 outcomes 路径。

## 3. 必要整改逐项映射

| ID | 原表述或缺口 | 整改后 | 直接证据 | 为什么是最小改动 |
|---|---|---|---|---|
| R01 | 身份仍写 Review V4 时的单一 reviewed HEAD | 保留原审阅 HEAD，并增加 rectified evidence HEAD 与 latest numerical source | 当前分支与 exact audit identity | 只补 provenance，不改历史身份 |
| R02 | 把端点问题主要表述为 E-trace / interface placement | 改为 endpoint joint electric/traction Cauchy incomplete | traction aggregate `2.364065e-5`，electric `1.099844e-6` | 只纠正被新测量细化的根因 |
| R03 | `30/90 nm` 仍被写成下一 actual candidate | 记录 I1/I2 均为 79/96，并关闭继续移动接口 | I1 78.59% Full3D peak；I2 94.79%；16 通道持续失败 | 已运行点不能继续写成未运行计划 |
| R04 | E projection `<=1e-8` 被当作 port 预选主 Gate | 改为 joint E/traction Cauchy、transfer tail、实际 channel/59-goal 联合 Gate | E-only 在 30/90、40/80 很好但 actual 仍失败 | 不增加新 Gate 框架，只修正已有表格语义 |
| R05 | 暂定剩余误差可能来自 core propagation | 明确 selected M120 core qualified | 40/60/100 nm exact FE vs modal 为 `1.59e-11–1.95e-11` | 删除已被 exact operator 对照推翻的推断 |
| R06 | full-interface Bloch 与 transfer optimal 两种路线并列 | 只冻结 `transfer_optimal_port_modes` | 16-channel sensitivity 的 95% rank 为 16；Review V5 后续审计决定 | 避免同时扩展三种算法 |
| R07 | production P0 仍要求 30/90 actual | P0 改为纯 offline optimal-port fixture，P1 才允许唯一 A004-S actual | exact audit 完成但 candidate 未实现 | 防止把诊断修正误当 PDE 修复 |
| R08 | 关闭路线未列接口内移、E-only buffer和逐通道 adjoint modes | 将三者加入 controlled-negative / not-selected 表 | I1/I2、joint Cauchy、rank-16 sensitivity | 只补已有负证据，不发明新实验 |
| R09 | `mode/plane` 行有尾随空格 | 删除尾随空格 | `git diff --check` | 纯格式修复 |

## 4. 明确保留、没有必要修改的内容

| 内容 | 决定 | 原因 |
|---|---|---|
| 未来结构统一按真正 3D 处理 | 保留 | 用户已明确禁止把目标简化为2.5D |
| Hybrid 是0.7 nm主要降维路线 | 保留 | Full3D全域在目标尺度不现实 |
| strong trace `g_s = R_s L_s a` | 保留 | 代数、identity、Petrov residual和资源证据已通过 |
| scalar-CG diagonal selected propagation | 保留并增强证据 | exact FE selected operator进一步确认其正确性 |
| Full3D static-condensed iterative 的局部角色 | 保留 | 可作为reference、endcap kernel和block-PC组件，但不是最终全域路线 |
| 禁止 replicated global `M²` | 保留 | generic 3D mode floor 下复制对象必然失控 |
| distributed mode ownership / streaming | 保留 | 是0.7 nm modal core的必要复杂度整改 |
| matrix-free strong-trace Hybrid FGMRES | 保留为后续阶段 | 当前 Task036 不启动迭代开发 |
| local exact-sequence h/p与static condensation | 保留为后续阶段 | 端部3D体积仍需压缩，但当前不恢复blind controller |
| 完整 residual、R/T/A、59-goal、channel和资源 Gate | 保留 | production资格不能通过放宽Gate获得 |
| 0.7 nm不允许固定M120 | 保留 | M120只是当前13.5 nm core，不是generic 3D物理下限 |

## 5. 整改后的唯一决策链

```text
existing exact Cauchy + one-cell Schur evidence
→ one transfer-optimal joint-Cauchy port fixture
→ fixture passes orientation / residual / no-dense-square / resource preflight
→ one A004-S p5/h10 M120 MPI8 actual at 10/110 nm
→ only after 96/96 and all numerical/resource Gates: A049-P, A001-P, p6/59-goal
→ distributed/streamed modal core
→ matrix-free Hybrid iterative
→ local exact-sequence h/p
→ wavelength continuation to 0.7 nm
```

如果 fixture 或唯一 A004-S actual 失败，保存 controlled negative 并停止 direct port
enrichment；不得再扫接口、global M、模式数、阈值或 ranking 公式。

## 6. 文件级改动与最小性

| 文件 | 对应整改 | 改动性质 | 为什么最小 |
|---|---|---|---|
| `outcomes/hybrid_production_readiness_assessment.md` | R01–R09 | 更新过时证据、决策表和下一步；清理一个尾随空格 | 没有改生产代码、测试、schema或runner |
| `outcomes/hybrid_production_readiness_assessment_rectification_report.md` | 本报告 | 新增可独立审阅的整改映射 | 满足用户要求，不另建review/task/framework |

本轮没有修改 `src/`、`benchmarks/`、ordinary default 或数值 artifact。也没有增加 validator、
状态机、包装层、fallback、兼容分支、重复 try/except 或任何防御性代码。

## 7. 验证

最终提交前已执行：

- Markdown 相对链接检查：pass；
- Markdown 表格列数检查：pass；
- trailing whitespace / `git diff --check`：pass；
- Task036 文档关键词与 closed-lane 一致性检查：pass；
- 最终文件清单确认不含生产代码：pass。

本轮没有运行 PDE、全仓库数值测试或生产源码测试；原因是实际变更严格限定为 Markdown，
不会改变任何数值 kernel、ABI、solver、Gate 或 ordinary default。
