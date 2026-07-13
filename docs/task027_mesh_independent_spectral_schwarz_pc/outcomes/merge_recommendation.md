# 合并建议

## 建议结论

```text
建议审查后合并 owner-computes physical-slab Schwarz、MPI 回归和完整证据；
保持为显式 workstation profile，不修改 ordinary production default。
```

## 建议保留

1. `DistributedPhysicalSlabSmoother`：完整物理 slab 全局只因子化一次，owner rank 负责局部解。
2. complete reduced-DoF slab 收集、确定性负载均衡和 VecScatter 汇总。
3. 两步 matrix-free shifted-F 全局平滑与固定真 Galerkin coarse correction。
4. MPI1/MPI2 dense-reference、repeatability 和空 owner rank 回归。
5. profile 参数、RSS/swap/真残差/RTA 诊断与 Task027 raw evidence。
6. 既有精确 condensed adjoint、coarse cache 真 action 认证和 rank-local basis cache。

## 不建议设为默认

1. 当前 energy spectral、interface harmonic、shifted near-null 和 PCHPDDM/GenEO 配置。
2. HPDDM 跨 solve recycling；它出现严重 projected residual 假收敛。
3. 将 `distributed_slab` 或 `max_it=3000` 静默改成普通入口默认值。
4. 把固定 75 维粗空间的成功命名为 operator-adaptive spectral coarse 成功。

## 合并前检查

- 全套目标测试通过；
- `git diff --check` 通过；
- 不提交 `Results/` 与用户的 `papers/`；
- 不纳入 Task023 无关的本地 `system_metadata.json` 变化；
- 审查者确认 `solver mesh-robust` 与 `R/T/A mesh-converged` 没有混写；
- 审查者确认最终严格比值使用实际迭代数 `1804/993=1.8167`。
