# Case091：Hybrid fixed-p 等精度与 h/p 自适应可行性

> 2026-07-17 Review V5 更新：D0、D1、D2 已完成。`p3/h10` 为等精度负结果，
> 条件 `p3/h7.5` 为带资格的工程正结果；native cellwise variable-p H(curl)
> 未资格化。p2 h-adaptive、buffer 和 1 TiB 更新仍未启动。
>
> 2026-07-17 Phase B 更新：p2 MPI1 与 p3/p4 MPI1/MPI4 matching-trace 最小矩阵已
> 独立聚合通过，见
> [`records/stage2_matched_trace/phaseB_summary.json`](records/stage2_matched_trace/phaseB_summary.json)；
> Phase C p3/h5 已按 review v3 执行：full3D 为 `not_run_by_memory_gate`，
> Hybrid M80/M120/M160 与 augmented M160 通过，见
> [`records/stage3_p3_h5/phaseC_summary.json`](records/stage3_p3_h5/phaseC_summary.json)。
>
> 当前主入口是
> [`records/stage5_equal_accuracy/reduced_equal_accuracy_summary.json`](records/stage5_equal_accuracy/reduced_equal_accuracy_summary.json)
> 和
> [`records/variable_p_capability_audit.json`](records/variable_p_capability_audit.json)。

## 当前身份

```text
Task033 stage1 high-order evidence = completed
Task033 Phase B matched trace = p3/p4 accepted
Task033 Phase C p3/h5 = same-degree Hybrid/full3D closure accepted with qualifications
Task033 Phase D1 = p3/h10 negative; p3/h7.5 equal-accuracy engineering positive with qualification
Task033 Phase D2 = native variable-p not qualified; no hp target prototype
adaptive compression measurement = not run; waits for new review
interface buffer = deferred until defect geometry
0.7 nm feasibility claim = false
ordinary default changed = false
```

Case091 原先冻结 Task033 的 20 项 p/h 资源矩阵、两中心内存预测和 fail-closed
启动规则。Review V5 已把当前决策矩阵减缩为复用 p2/h5、p2/h3、p3/h5，运行
p3/h10 和条件 p3/h7.5，并保留 p4 resource negative。原 20 项不是已完成矩阵，
也不应再自动运行。

## 物理问题

目标模型仍是 13.5 nm、50 nm × 25 nm 双周期 Hybrid FEM–Modal 问题：
上下端保留复杂三维 Nédélec FEM，中段目标为通用 `epsilon(x,y)` 的模态传播，
主求解路径为 `modal-schur-memory-minimal`。Phase C 已在 p3/h5、10/110 nm、
M80/M120/M160 上运行；Phase D1 又在 p3/h10、p3/h7.5 上执行 direct 与
M120/M160。资源矩阵和 C0 只提供逐候选准入，最终判定由实测物理误差和资源记录共同决定。

## 参数说明

| 序号 | 参数 | 值 / 规则 | 数据身份 |
|---:|---|---|---|
| 1. | wavelength | 13.5 nm | task input |
| 2. | period x | 50 nm | task input |
| 3. | period y | 25 nm | task input |
| 4. | degree | p1–p4 history；当前 D1 只新增 p3 | scoped |
| 5. | h | 当前 D1：10、7.5 nm；p3/h5 reference | measured/reused |
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

原 20 项默认记录只有预测/决策身份。当前 Review V5 结果另行跟踪：

- p3/h10 direct 1.980 GiB，物理等精度失败；
- p3/h7.5 direct 3.667 GiB，Hybrid M160 2.008 GiB，全部等精度和闭合 Gate 通过；
- p4/h5 direct assembly 12.616 GiB 受控停止，Hybrid 上界 42.594 GiB；
- variable-p audit `not_qualified_fail_closed`。

重型 mesh、field、matrix、factor、timeline 和 raw log 已生成于
gitignored `benchmarks/artifacts/`；tracked descriptors/summary 保存 SHA256 和关键数值。

## 结果解释

`planning_eligible_by_resource_prediction` 只说明预测和矩阵策略允许进入下一道
Gate，不等于可以立刻运行。`launch_eligible` 还必须满足现场四项运行合同和适用的
p3/p4 资格 Gate。`reuse_task032_clean_anchor` 表示引用已有实测，不是 Task033
重新运行。

h/p 同误差 local DoF 压缩按 `<1.3x`、`1.3x–<2x`、`2x–<3x`、`>=3x`、
`>=5x` 分级。fixed-p p3/h7.5 的 FE-only DoF 为 2.571x、含外部 aux 的
local-system rows 为 2.567x，均为 `clear_success`；factor
inventory NNZ 为 3.557x `engineering_target`。固定 p2 h-adaptive 的 3x 仍只是
stretch；该阶段尚未产生 measured compression。

## 限制

- 两中心都只由 Task032 p2/h5-h3 两个实测点校准，外推不等于 PDE 实测。
- 预测 assembled NNZ 和 factor fill 是保守 planning 模型，不是装配结果。
- 默认 Docker 上限是 Phase-0 快照；正式运行前必须刷新并可注入更小值。
- clean/no-swap/watchdog/one-large-case 默认 unknown，不能靠脚本默认值冒充通过。
- 新候选必须通过独立高阶和 candidate-specific C0 Gate。
- conditional/locked 候选仍需前序 clean 记录或独立解锁证据。
- 不得依靠 swap、OOM 后补写或手工覆盖 Gate 完成矩阵。
- p3/h5 是 provisional discrete reference，不是 continuum/grid-converged reference。
- 本 Case 不证明 p2 自适应压缩、1 TiB 路线或 0.7 nm 可行性。

轻量记录保存在本目录；后续重型产物只能写入 gitignored 的
`benchmarks/artifacts/cases/091/`。
