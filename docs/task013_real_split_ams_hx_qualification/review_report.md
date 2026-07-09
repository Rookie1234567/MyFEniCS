# REVIEW REPORT 20260708：Task013 real-split AMS/HX qualification

## 1. 审查对象

审查分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task013_real_split_ams_hx_qualification/
```

重点审查文件：

```text
docs/task013_real_split_ams_hx_qualification/outcomes/summary.md
docs/task013_real_split_ams_hx_qualification/outcomes/real_split_equivalence.csv
docs/task013_real_split_ams_hx_qualification/outcomes/fe_only_real_split_ams_summary.csv
docs/task013_real_split_ams_hx_qualification/outcomes/fe_only_real_split_ams_memory.csv
docs/task013_real_split_ams_hx_qualification/outcomes/p_coarsened_auxiliary_summary.csv
docs/task013_real_split_ams_hx_qualification/outcomes/ams_memory_breakdown.md
docs/task013_real_split_ams_hx_qualification/outcomes/solver_profile_ranking.md
docs/task013_real_split_ams_hx_qualification/outcomes/merge_recommendation.md
docs/task013_real_split_ams_hx_qualification/outcomes/next_decision.md
src/studies/run_real_split_ams_qualification.py
```

本轮是 qualification / go-no-go 审查，不把 isolated research runner 当作正式 Stage 4 solver 审查。

---

## 2. 总体结论

Task013 通过，但结论等级应定为 B 档：

```text
FE-only real-split AMS/HX + same-H1 auxiliary 有明确正信号，值得进入 reduced Stage 4 integration；
但它还不是 production Stage 4 solver，不建议把 solver 代码直接合并进 master。
```

本轮最重要的成果是证明：

```text
1. complex Maxwell FE-only block 可以安全写成 real split block；
2. real PETSc/hypre AMS 可以绕开 task011 中 complex AMS 的 crash 路径；
3. same-H1 auxiliary 明显降低 AMS hierarchy 内存；
4. p=2 h=5 FE-only same-H1 AMS 能达到 true residual <= 1e-6。
```

本轮尚未证明：

```text
1. 该 PC 能处理 Floquet MPC 后的 Stage 4 系统；
2. 该 PC 能处理 DtN modal auxiliary unknowns；
3. full Stage 4 p=2 h=2 能收敛并复现 R/T/A；
4. full Stage 4 p=2 h=1.5 能突破 direct/BLR 内存瓶颈。
```

因此建议：

```text
merge_code: no
merge_docs_only: yes / optional
next_task: Task014a reduced Stage 4 real-split FE/aux block PC integration
```

---

## 3. 关键结果核对

### 3.1 real split 等价性

`real_split_equivalence.csv` 显示所有测试 case 的 matvec error 都在 `1e-16` 量级：

| case | p | h/nm | n real | nnz real | relative matvec error |
|---|---:|---:|---:|---:|---:|
| p1 h10 standard | 1 | 10 | 1,812 | 90,360 | 1.346e-16 |
| p1 h5 standard | 1 | 5 | 10,366 | 580,892 | 1.404e-16 |
| p2 h10 standard | 2 | 10 | 12,200 | 2,166,080 | 1.606e-16 |
| p2 h5 standard | 2 | 5 | 74,892 | 14,233,968 | 1.659e-16 |
| p2 h5 same | 2 | 5 | 74,892 | 14,233,968 | 1.659e-16 |
| p2 h4 same | 2 | 4 | 165,756 | 32,230,224 | 1.671e-16 |

审查判断：通过。real block 组装公式与 complex operator 的实虚部作用一致。

### 3.2 FE-only AMS/HX qualification

最关键数据来自 `fe_only_real_split_ams_summary.csv`：

| case | profile | auxiliary | status | iterations | true residual | RSS |
|---|---|---|---|---:|---:|---:|
| p2 h10 | Jacobi | none | not converged | 1000 | 5.846e-3 | 0.301 GB |
| p2 h10 | AMS | standard | converged | 219 | 9.918e-7 | 0.888 GB |
| p2 h5 | Jacobi | none | not converged | 150 | 7.605e-6 | 1.080 GB |
| p2 h5 | AMS | standard | not converged | 150 | 8.004e-6 | 6.306 GB |
| p2 h5 | AMS | same | converged | 310 | 9.964e-7 | 1.323 GB |
| p2 h5 | AMS | linear | not converged | 50 | 7.764e-5 | 1.322 GB |

审查判断：

```text
same-H1 auxiliary 是本轮唯一值得继续的路线。
standard H1=p+1 内存高且 p2 h5 150 步表现不如预期。
linear H1=1 太弱，不建议继续。
Jacobi 可作为 baseline，但不是可靠 solver。
```

---

## 4. 主要风险与限制

### 4.1 FE-only 与 Stage 4 仍有结构差距

当前 runner 构造的是 FE-only Maxwell block，不含：

```text
Floquet MPC；
DtN modal auxiliary unknowns；
Stage 4 official R/T/A 后处理；
真实 solver 主线中的矩阵分块与约束消元。
```

因此不能把 FE-only 收敛直接外推到 full Stage 4。

### 4.2 same-H1 auxiliary 需要进一步解释

same-H1 能显著降内存，但它改变了 auxiliary H1 空间阶数选择。它目前是工程上有效的经验选择，需要在下一轮记录：

```text
它和 hypre AMS 的离散梯度要求是否一致；
MPC 后 G 的构造是否仍稳定；
p=2 h=4/p=2 h=5 的 setup memory 是否保持可控。
```

这不阻止继续，但阻止把它直接升级为正式 production profile。

### 4.3 p=2 h=4 只是 assembly audit

`p=2 h=4 same-H1` 当前只做了 real split equivalence / memory audit，未运行 AMS setup/solve。因此不能说 p=2 h=4 已经通过。

### 4.4 Python PC 和 serial explicit block 不应直接进主线

`src/studies/run_real_split_ams_qualification.py` 明确是 serial isolated runner，且使用 Python PC callback。它适合研究验证，但不应成为长期正式求解器接口。

---

## 5. 合并建议

建议采用文档优先合并策略：

```text
merge_code: no
merge_docs_only: yes / optional
```

可以合并或保留的内容：

```text
docs/task013_real_split_ams_hx_qualification/outcomes/*
docs/task013_real_split_ams_hx_qualification/review_report.md
docs/README.md 中 task013 结论
notes/reference/current_version_boundaries.md 中必要边界说明
```

不建议直接合并为 production 的内容：

```text
src/studies/run_real_split_ams_qualification.py
```

如果下一轮 Task014a 要继续用这个 runner，可留在当前研究分支上，不急着合入 master。

---

## 6. 下一步建议

下一轮不要直接跑 full Stage 4 p=2 h=2，更不要直接跑 p=2 h=1.5。

建议任务：

```text
Task014a：reduced Stage 4 real-split FE/aux block PC integration
```

下一轮目标应是：

```text
1. 在 Stage 4 assemble-only 层面验证 complex residual 与 real split residual 一致；
2. 把 Stage 4 unknowns 分为 FE block 和 DtN auxiliary block；
3. same-H1 AMS 只作用在 FE block；
4. auxiliary modal block 先用 identity 或 exact small solve；
5. reduced Stage 4 p=1 h=5 与 Jacobi 做 true residual 对比。
```

只有 reduced Stage 4 通过后，再考虑 full Stage 4 p=2 h=2。只有 h=2 收敛且内存显著低于 BLR/direct 后，才考虑 h=1.5 breakthrough。

---

## 7. 最终结论

```text
Task013 通过；
结论为 B 档正结果；
real-split AMS/HX + same-H1 auxiliary 值得继续；
当前代码不建议作为 production solver 合并；
下一轮应在现有分支继续做 Task014a reduced Stage 4 FE/aux block PC integration。
```
