# PARA-Task005 Review V1 Response

## 处置

接受审阅分类与限定：

```text
primary = learned_pc_memory_budget_failure
secondary = R4 fixed-operator local-quality and model-only runtime positive
root cause = private exact-audit operator storage
P3-P10 = not_run_by_gate
```

该负结果不是 NN approximation capability failure、NN inference speed failure、
all-slab/global failure 或 learned-PC 总体不可行结论。Task005 没有形成 neural
acceleration、memory saving、active replacement 或 production claim。

## 数据身份修正

| 审阅项 | 修正后的身份 |
|---|---|
| T1/T2/V/H | execution-independent but distribution-correlated |
| 相关性来源 | 相同固定物理、确定性 RHS 与 Krylov trajectory distribution |
| V | 当前未用于候选选择、early stopping 或 model choice |
| H | 已用于 Lane A/B candidate screening，故为 consumed screening split |
| future final | 若恢复 full16/global 资格化，必须新建未接触 final split/run |
| capture schedule | 仅 stride/offset 互斥；没有 phase、norm bucket、outer-iteration metadata |

因此，四次 clean capture 的独立执行和 apply-index 无重叠仍成立，但不再表述为跨
trajectory/physics 的统计独立性，也不再把 H 称为 untouched final holdout。

## D1 结论边界

D1 的负结果只说明当前五类 **index-space structured synthetic recipe** 在 R4、
固定 operator 和 consumed screening split 上没有优于 D0。它不能外推为
physics-aware augmentation、跨参数 structured data 或所有结构化增强均无效。

## Storage 根因

最小 admissible model/basis 本身落在工程预算附近；硬失败来自 owner 上为 strict
exact audit 持久保留的 per-slab private CSR operator copy。完整最小 owner storage
为 68.282 MiB，超过 33.670 MiB memory-neutral budget 和 50.505 MiB speed-first
guard。Task005 保留这一失败，不修改冻结 Gate，也不重跑 P0/P1/P2 heavy evidence。

## 验证与 tracked diff

完整 42-file Task005 tracked diff 与审阅响应追加文件见
`outcomes/changed_files.md`。绑定 clean SHA 的全量、ML、MPI2、Ruff、compileall、
diff-check 和 ignore audit 见 `outcomes/validation.md`。

## 后续治理

P3-P10 不运行。继续工作只通过独立 PARA-Task006，先资格化 borrowed assembled
action、低存储 proxy、periodic exact audit、failure injection 与 lifecycle；
在其 Gate 通过前不得恢复 full16 training 或 active learned-PC。
