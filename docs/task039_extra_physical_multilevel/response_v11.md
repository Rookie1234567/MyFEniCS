# Response V11：V10 macro inverse M4 收口

## 当前结论

V10 的 M0 输入/ABI 注册和 M1 局部 macro 构建已经完成可审阅的部分证据，但 M1 未完成。第二次 M1 在 block 7 的局部 factorization 后触发冻结的 2 GiB 保守 resident policy；因此本轮状态为：

`PARTIAL_WITH_CONTROLLED_NEGATIVES`，并带有 `LOCAL_INVERSE_UNQUALIFIED`、`RESOURCE_BLOCKED`、`FRAMEWORK_COMPARISON_LIMITED` 和 `RESTART_DIAGNOSIS_LIMITED`。

这不是系统 OOM、不是数学 PDE 失败，也不是 solver/physics PASS。M2、M3、original、notch 和 official output 均保持 `not_run`。

## 本轮实际实现

M1 的实现入口已接入单一 `.dat` 配置：`src/io/input_schema.py`、`src/io/input_validation.py`、`src/io/physical_intermediate_profile.py` 和 `src/io/physical_recursive_profile.py` 注册并验证 `physical_macro_dd4_v10`；`scripts/run_case.py` 根据该 profile 自动进入 M1 runner。局部矩阵与分解逻辑位于 `src/solvers/physical_macro_dd4.py`，M1 控制编排位于 `src/runners/physical_macro_controls.py`，公共 worker/身份和 ledger 接线位于 `src/runners/physical_recursive_entry.py`。代表块选择的窄修只改用非零 DtN 支持和当前材料标签，不改变 Maxwell 离散或 M1 的资源合同。

通俗地说，多单元局部逆把相邻单元的内部未知量组成小块，先解这些小块，再把局部响应作为全系统纠错的一部分；它的目标是避免直接分解整个 p4/p6 全局矩阵。局部回代残差很小，只能说明这些小块对测试右端的解答自洽，并不能说明局部响应与完整全局 Maxwell 算子配合得好，更不能代替外层真残差、场误差或 R/T/A Gate。

## M1 两次尝试

| 尝试 | source | 实际阶段 | 结果 | I4/B4 |
|---|---|---|---|---:|
| engineering repair | `99428016a73fdbb29f6531974ed1ee4756d96bbc` | native DtN 已构建，local volume 后代表块选择 | `ValueError: no canonical interior_single_material macro block in current metadata`；分类为 `REPRESENTATIVE_SELECTOR_FAILURE_BEFORE_LOCAL_FACTORIZATION`，随后已按活动 DtN 行和实际材料标签修正 | `0/0` |
| final M1 candidate | `b0df7457c0c4b33c66abda16862926da3426bb7d` | block 0–7 矩阵/数值分解，block 7 factorization 后 | `MemoryError: macro retained resident policy exceeded after block factorization`；保守累计 policy=`2,243,365,908 B`，超过 cap=`2,147,483,648 B` `95,882,260 B` | `0/0` |

`resident_before_factor=1,982,365,908 B` 已包含 block 7 当前矩阵和全部 block 的 indices/support；numeric 后只新增 block 7 allocated factor `261,000,000 B`，没有重复加 matrix。

MUMPS INFOG18/19 与 INFOG21/22 分别是分解期间 allocated 与 effectively used 的后端量，不是分解后 factor-only 常驻测量。因此报告只称“allocated 量驱动的保守累计预审停止”。同期 process-tree RSS 峰为 `1,107,648,512 B`，job swap 峰为 `0 B`，所有 descendants 已清场。

## 四条证据轴

- 内部质量轴：保存的 block 0–6 共 14 次回代最大相对残差 `2.0002787934351233e-15`；两个代表块的 6 次 native witness 最大 `8.243915633632588e-16`。block 7 回代残差未持久化，且 p4 true error/residual、`build_w_transfer`、cached action、cached/native A4 bridge 均未完成；局部 witness 不等于 p4 true error。
- 框架耦合轴：recursive map verification、6 个 g calibration 和 BAL_H/ONE_C 框架对照均为 `not_run`，不能比较框架反馈。
- restart 轴：restart32/restart64 未运行，不能从旧 ENTITY16/g1 历史数据推导 V10 restart 结论。
- 总成本轴：账本已记录 preparation（截至 `2026-09-10T12:14:07.163Z`）`1281.5 s` 与两次 M1 终态 `380.27739690501534 s`，合计 `1661.7773969050152 s`，nominal remaining=`3738.222603094985 s`。12:14 之后的其他 repair、测试和 M4 文档费用未完整纳入，complete total cost=`UNKNOWN`。

完整证据、逐 block allocation/audit、状态边界和 artifact hash 见 [V10 中心结果](outcomes/physical_macro_inverse_v10.md) 与 [V10 compact](outcomes/records/physical_macro_inverse_v10.json)。

## 账本、测试和交付边界

V10 ledger 已记录 preparation（截至 `2026-09-10T12:14:07.163Z`）`1281.5 s` 与两次 M1 终态 `380.27739690501534 s`，合计 charged `1661.7773969050152 s`，nominal remaining `3738.222603094985 s`；12:14 之后的其他 repair、测试和 M4 文档费用未完整纳入，complete total cost=`UNKNOWN`。准备 envelope 是保守记录，不是完整准备实测。M4 收口检查为 task-focused `55 passed in 1.81 s`、macro suite `9 passed in 0.52 s`、Ruff/py_compile 通过；手工编译的轻量日志为 [v10_m4_test_run.log](outcomes/records/v10_m4_test_run.log)，不是 raw stdout，SHA `f484c96d8231de6b56052f162457010d8a2bba8d1af6b3992dfc8d950090cc97`；full repository pytest 与 CI 均 `not_run`。

M4 阶段完成了中心结果、compact、summary、run index、test summary、development registry/progress、workstation handoff 和依赖组 selective manifest；不上传 raw matrix/factor/cache，不修改历史成功或负结果，不授权 master merge。远端 push 仍需用户在 WSL 配置 HTTPS/`gh` 凭据后执行。
