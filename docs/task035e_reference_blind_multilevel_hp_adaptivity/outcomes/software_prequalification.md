# Task035e software prequalification

## 结论

本记录只覆盖正式 PDE 前的软件、组件和 MPI8 通信资格化。当前分类为：

```text
SOFTWARE_PREQUALIFICATION_PASS
NUMERICAL_CREDIT = false
REFERENCE_CREDIT = false
BLIND_CANDIDATE_CREDIT = false
HIDDEN_AUDIT_CREDIT = false
HYBRID_CREDIT = false
```

正式运行的 source SHA 将由本批软件提交冻结；本文不预填尚未产生的 commit
SHA。所有 PDE record 必须自行绑定运行时完整 SHA、ABI 和 artifact hash。

## 已验证能力

| 组件 | 当前结论 | 信用边界 |
|---|---|---|
| multilevel local-h | level 0/1/2、2:1、periodic、hanging 与 material identity 通过 | component only |
| variable exact-sequence p | production p4/p5/p6，inactive mode 不编号 | component only |
| 59-goal current/DWR | 固定 N=8、两端口、总量与场目标闭合 | component only |
| p/h shadows | selected shadow、cellwise authority、marking 和 transition 可重放 | component only |
| saturation | p7 与 h-level3 均为 shadow-only，不可成为 production action | component only |
| blind campaign | A/B、最多六 cycle、resume、single-heavy lock 与 fail-closed freeze | orchestration only |
| evaluator handoff | blind 退出后独立验证 freeze receipt 与 candidate bundle | no hidden data opened |

## 测试证据

在 `/home/Projects/MyFEniCS` 中通过资格化 activation 执行：

| 批次 | 结果 |
|---|---:|
| Task035e serial/component tests 219–279（271 单列） | 485 passed, 15 skipped |
| p7 saturation bridge test 271（相关源码未再修改） | 3 passed, 1 skipped |
| Task035b/Task035d compatibility tests 178/186/188/189 | 32 passed |
| blind isolation/controller/campaign focused subset | 74 passed |
| hidden auditor + evaluator handoff focused subset | 30 passed |
| MPI8 authority/ownership/DWR/saturation 节点 | 15/15 passed |
| Ruff `benchmarks src` | passed |
| compileall `benchmarks src` | passed |
| Case098 JSON parse、checker 与 diff-check | passed |
| full repository sweep | 1254 passed, 57 skipped, 1 localized documentation-contract gap |
| documentation-contract gap 修复后 targeted closure | 24 passed |

MPI8 首轮中，p7 global fixture 的 correction true relative residual 为
`1.175762076159686e-9`，高于固定 `1e-9` Gate。没有放宽 Gate；根因是小 RHS
下测试 KSP 的 `atol=1e-15` 先于相对阈值停止。将 fixture 的 `atol` 收紧为
`1e-18` 后，同一 MPI8、两种参数均通过。该失败保留为受控软件证据，不是正式
PDE 结果。

全仓 sweep 的唯一失败是新增 Case098 未登记到
`ACTIVE_RESEARCH_CASES`。补入 Case098 的 scaffold 合同并保留“至少一条
controlled diagnostic record”语义后，完整 documentation contract、Case098
checker 与 evaluator handoff 共 24 项通过。该修改只涉及 case 登记和断言，
未触发数值源码变化，因此没有重复 51 分钟的全仓 sweep。

## 明确未获得的结果

- p6/h10、p6/h7.5、p6/h5 reference 尚未在本次干净 SHA 上运行；
- Path A/B blind cycle 尚未运行；
- candidate 尚未冻结，sealed reference 尚未由 hidden auditor 打开；
- Full3D hidden pass 与 Hybrid M120 均不存在；
- 现有 MPI1 h100 diagnostic 仍是 prequalification，不得替代 MPI8 或精度 Gate。
