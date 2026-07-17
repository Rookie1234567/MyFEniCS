# PARA-Task003 Review V1 响应

## 1. 响应状态

```text
review = review_report_v1
disposition = accepted_with_qualifications
final_classification = exact_lu_oracle_global_signal_insufficient
ordinary_default_changed = false
rerun_required = false
```

审阅结论全部接受。Task003 建立了 raw-residual-only 数据合同、可靠 sparse-LU teacher 和 selected-slab exact oracle；它证明的是 1/3 个 selected slabs 的 exact local inverse 缺少足够全局杠杆，不是“所有 NN local PC 都不可行”。

## 2. 已关闭事项

| 审阅项 | 响应 |
|---|---|
| Case092 factorization 时间不一致 | 已统一为最终完整资源记录的 2.576 s |
| 三-slab non-root timing 未汇集 | Task003 结果边界保持不变；Task004 将实现所有 rank、所有 slab diagnostics gather |
| oracle 保留隐藏 ILU | Task003 内存继续标记为非 replacement；Task004 正式 oracle 必须在 factorization 前规划 backend 并跳过 exact slab ILU |
| dirty-worktree provenance | 接受其只支持 research-negative Gate，不冒充 canonical wall-time evidence；Task004 将在 clean implementation HEAD 成对运行 |
| P3–P7 未运行 | 审阅确认属于正确 Gate 停止，不补跑、不训练 |

## 3. 保留边界

- Task003 分类保持 `exact_lu_oracle_global_signal_insufficient`。
- 不声称 NN-only、all-slab learned PC、factor-removal memory saving 或 h3/h2 neural acceleration 已验证。
- ordinary default 不变。
- 不执行 branch、master、merge、pull 或 push 操作。
- 后续仅按独立 Task004 测试 4/8/16-slab no-hidden-ILU exact oracle；在新 oracle Gate 前不训练模型。
