# 工作站 FGMRES runtime

## 两层 facade

`stage4_runtime.target_stage4_config` 冻结 50 x 25 x 140 nm、17 x 25 x 120 nm Si block、13.5 nm、80 度 s 偏振、p2、DtN auto orders。`assemble_target_stage4_system` 只组装并返回 `RuntimeStage4System`，不直接求解。

`benchmarks/run_workstation_iterative.py` 是显式 opt-in 生产 runner：

```text
load JSON -> qualification deviations -> parameter/progress JSON
-> assemble RuntimeStage4System -> extract/condense
-> build 75 coarse -> shifted F -> 16 slabs -> two-level PC
-> right FGMRES -> three residuals -> auxiliary backsub
-> official RTA -> record -> destroy
```

## 关键函数

| 函数 | 责任 |
|---|---|
| `_qualification_deviations` | h/角度/波长/MPI/PC 参数白名单 |
| `_memory_fields` | MPI rank current/peak RSS 求和 |
| `_complete_physical_slabs` | cell -> global DOF subdomains |
| `_fixed_floquet_hat_basis` | 25x3 coarse 候选、正交、压缩 |
| `_shifted_matrix/_shifted_action` | 局部吸收位移近似 |
| `_linear_residual` | 显式 true residual |
| `_official_rta` | 恢复 FE Function 后调用 port+volume |
| `run` | 完整生命周期和 record |

## monitor

每 50 步 `buildSolution`，用原 condensed operator 重算 true residual，并写 elapsed/current/peak RSS。monitor 自身有成本，但让 reported norm 与真实 action 可持续比较。

## record 身份

`_runtime_metadata` 记录 commit/branch/dirty/command/time/image/digest/host；result 记录 benchmark_id、resolved_config、physical_model、artifact root、qualification、DoF、PC、residual、RTA 和 RSS。checker 不依赖重型 artifact 即可验 Gate。

## 不能复用的方式

不要把 `run()` import 到普通 main 后单进程调用；不要用未知 MPI 数运行后仍写 qualified；不要覆盖 canonical record 做参数扫描；不要在 full residual 未过阈值时强制 RTA。
