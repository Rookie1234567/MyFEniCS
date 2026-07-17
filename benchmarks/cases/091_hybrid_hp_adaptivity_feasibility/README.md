# Case091：Hybrid h/p 自适应可行性

> 2026-07-17 范围调整：本阶段只闭合 p3/p4 高阶能力与 Task032 p2
> Hybrid/full3D 对比；自适应、buffer 和 1 TiB 工作为 `deferred_by_user_scope`。
> 阶段证据见 [`records/stage1_high_order/stage_summary.json`](records/stage1_high_order/stage_summary.json)。

## 当前身份

```text
Task033 stage1 high-order evidence = completed
original h/p adaptivity scope = deferred by user
runtime preflight = unknown by default and fail-closed
adaptive compression measurement = deferred
0.7 nm feasibility claim = false
ordinary default changed = false
```

Case091 原先冻结 Task033 的 20 项 p/h 资源矩阵、两中心内存预测和 fail-closed
启动规则。当前阶段新增 p3/p4 高阶执行摘要，但没有完成 h/p 压缩或 0.7 nm 可行性证明。

## 物理问题

目标模型仍是 13.5 nm、50 nm × 25 nm 双周期 Hybrid FEM–Modal 问题：
上下端保留复杂三维 Nédélec FEM，中段目标为通用 `epsilon(x,y)` 的模态传播，
主求解路径为 `modal-schur-memory-minimal`。本 Case 不改变该物理模型，
也不运行它；资源矩阵仅为后续受控运行提供逐项准入判断。

## 参数说明

| 序号 | 参数 | 值 / 规则 | 数据身份 |
|---:|---|---|---|
| 1. | wavelength | 13.5 nm | task input |
| 2. | period x | 50 nm | task input |
| 3. | period y | 25 nm | task input |
| 4. | degree | p1、p2、p3、p4 | planned |
| 5. | h | 5、3、2.5、2、1.5 nm | planned |
| 6. | M / direction | 160 | Task032 measured anchor |
| 7. | solver path | `modal-schur-memory-minimal` | retained policy |
| 8. | p2/h3 local FE rows | 68,396 | measured anchor |
| 9. | p2/h3 total rows | 68,796 | measured anchor |
| 10. | p2/h3 assembled NNZ | 8,594,673 | measured anchor |
| 11. | p2/h3 simultaneous RSS | 3.224353790283203 GiB | measured anchor |
| 12. | nominal host hard budget | 14 GiB | task policy |
| 13. | default Docker limit | 13.6485 GiB | Phase-0 measured |
| 14. | scaled center limit | 11.211267857142857 GiB | derived |
| 15. | scaled upper limit | 12.478628571428573 GiB | derived |
| 16. | scaled termination | 12.673607142857142 GiB | derived |
| 17. | center A | effective-p/h RSS power law | predicted |
| 18. | center B | assembled NNZ → fill → factor payload → RSS | predicted |
| 19. | clean source | `unknown` by default | not_run preflight |
| 20. | no swap | `unknown` by default | not_run preflight |
| 21. | watchdog | `unknown` by default | not_run preflight |
| 22. | one large case | `unknown` by default | not_run preflight |

预测字段始终保留 `projected_*` 名称。p2/h3 的实测复用值单独放在
`measured_anchor`，不会把预测行/NNZ 或预测内存中心伪装成实测。

## PyCharm

1. 将仓库根目录设为 Working directory。
2. 使用项目已有的 Python/Docker 解释器环境。
3. 建立 Python 配置，模块名填 `benchmarks.run_task033_resource_matrix`。
4. 不传运行前提参数时，只会生成默认 unknown/fail-closed 记录。
5. 测试配置使用模块 `src.test.test_45_task033_resource_gates`。

PyCharm 运行预测器不会启动 MPI 或 PDE，也不会分配大矩阵。正式 PDE 必须由
后续带现场 Git、swap、watchdog、并发和内存探测的 guarded runner 执行。

## CLI 或测试

生成仓库内默认轻量记录：

```bash
python -m benchmarks.run_task033_resource_matrix \
  --output-json benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/resource_matrix.json \
  --output-csv benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/resource_matrix.csv
python -m unittest -v src.test.test_45_task033_resource_gates
```

若现场重新测得更小的数值容器上限，可传入：

```bash
python -m benchmarks.run_task033_resource_matrix --container-limit-gib 12
```

只有现场确实完成验证时，才可显式加入
`--source-clean-verified --no-swap-verified --watchdog-enabled-verified
--one-large-case-verified`。p3/p4 还分别需要 `--p3-qualified` 或
`--p4-qualified`；参数只是调用者 attestation，预测器本身不替代现场测量。

## 代码路径与理论

- `benchmarks/task033_resource_gates.py`：矩阵策略、预测器、门限和决策。
- `benchmarks/run_task033_resource_matrix.py`：确定性 JSON/CSV 生成器。
- `src/test/test_45_task033_resource_gates.py`：轻量合同和一致性测试。
- `config.json`：Case091 冻结输入与默认身份。
- `expected.json`：默认决策数量、禁止声明和记录合同。

第二中心不再从 center A 的 effective-p/h 标量间接得到 payload。它对每个候选
使用自身 `projected_assembled_nnz`，根据 Task032 h5/h3 的实测 factor inventory
外推 fill，再得到 factor NNZ、payload 和 RSS 中心。因此 p4/h5 与 p2/h2.5
不可能因 effective resolution 偶然相同而得到同一 factor payload。

CSV 对每个 JSON entry 的所有叶字段做 lossless flatten；列名是点分路径，
每个非空 cell 是 canonical JSON。测试逐字段反序列化并与 JSON 精确比较。

## 当前证据

默认 13.6485 GiB 记录得到：8 项仅在资源层面 planning eligible、1 项复用
Task032 p2/h3 clean anchor、11 项 `not_run_by_memory_gate`。因为运行前提默认均为
unknown，7 个普通低阶 planning 候选仍不是 launch eligible；p3/h5 还被高阶
资格 Gate 拦截。p4/h5 的独立 factor-NNZ/fill 中心超过门限，保持 fail-closed。

这 20 项只有预测与决策身份。正式 PDE、mesh、field、matrix、factor、timeline
和 raw log 均尚未生成。

## 结果解释

`planning_eligible_by_resource_prediction` 只说明预测和矩阵策略允许进入下一道
Gate，不等于可以立刻运行。`launch_eligible` 还必须满足现场四项运行合同和适用的
p3/p4 资格 Gate。`reuse_task032_clean_anchor` 表示引用已有实测，不是 Task033
重新运行。

h/p 同误差 local DoF 压缩按 `<1.3x`、`1.3x–<2x`、`2x–<3x`、`>=3x`、
`>=5x` 分级。固定 p2 h-adaptive 的 3x 是 stretch；在产生同误差实测曲线前，
所有压缩分类均为 `not_run`。

## 限制

- 两中心都只由 Task032 p2/h5-h3 两个实测点校准，外推不等于 PDE 实测。
- 预测 assembled NNZ 和 factor fill 是保守 planning 模型，不是装配结果。
- 默认 Docker 上限是 Phase-0 快照；正式运行前必须刷新并可注入更小值。
- clean/no-swap/watchdog/one-large-case 默认 unknown，不能靠脚本默认值冒充通过。
- p3/p4 未通过独立高阶 Gate 前一律不能启动 Hybrid 大算例。
- conditional/locked 候选仍需前序 clean 记录或独立解锁证据。
- 不得依靠 swap、OOM 后补写或手工覆盖 Gate 完成矩阵。
- 本 Case 不证明自适应压缩、1 TiB 路线或 0.7 nm 可行性。

轻量记录保存在本目录；后续重型产物只能写入 gitignored 的
`benchmarks/artifacts/cases/091/`。
