# Task39extra Review V11 response：N0–N5 收口

## 结论

Review V11 的 N0、N1 已完成；N2 到达 42-block 全 inventory 的第 42 块前置 Gate 后受控停止。N5 最终分类为 `LOCAL_INVENTORY_RESOURCE_BLOCKED`。N3 restart32/64、N4 original/notch 和所有 official physical outputs 均 `not_run`。本轮不把受控资源负结果写成系统 OOM、MUMPS numeric failure 或 Maxwell 数值失败。

中心结果：[macro memory lifecycle V11](outcomes/macro_memory_lifecycle_v11.md)；机器记录：[V11 compact](outcomes/records/macro_memory_lifecycle_v11.json)，SHA256 `14df814fe9b59e8dcdfee89a835837318d936d59ac45d060cc6085113845f5e2`。

## 执行结果

| 阶段 | 结果 | 证据边界 |
|---|---|---|
| N0 | ABI、MUMPS 5.6.2 手册语义和 PETSc public MUMPS controls 通过 | resolved `/usr/lib/x86_64-linux-gnu/libpetsc_complex.so.3.19.6`、`libzmumps-5.6.1.so`、`libmumps_common-5.6.1.so`、`libmpi.so.40.30.6`；getter runtime error 62；setter source verified，未伪造 setter runtime probe |
| N1 | `N1_CALIBRATION_COMPLETED` | block 0/1；old/new numeric 各 2；共 4 factorization；最大 local residual `5.438606648780365e-13`；同 RHS solution difference `0.0` |
| N2 | `CONTROLLED_RESOURCE_NEGATIVE` | block 0–40 共 41 numeric/backsolve；block 41 只到 pre-numeric symbolic gate；p4 true error、cached-native/map、BAL_H/ONE_C 均未触达 |
| N3 | `not_run_by_N2_gate` | 仅 restart32/64 未运行 |
| N4 | `not_run_by_N2_gate` | original/notch、E/H、R/T/A、`A_volume` 和 official outputs 未测 |
| N5 | `LOCAL_INVENTORY_RESOURCE_BLOCKED` | 固定 retained inventory policy 阻断；不修改 cap，不重跑 |

## N1 policy equivalence

V11 对每个局部块使用：

```text
E = 1e6 * (1 + max(INFOG16, INFOG17))
Q = 1e6 * ceil(max(32 MiB, 2 E + 8 MiB) / 1e6)
```

numeric 前设置并读回 `ICNTL(23)=Q/1e6`；不使用 used/min/RSS offset。block 0 的 `E=32,000,000 B`、`Q=73,000,000 B`、readback `73 MB`，block 1 为 `E=31,000,000 B`、`Q=71,000,000 B`、readback `71 MB`；两块 `INFO1=0`。公开 getter 对 `ICNTL(49)` 返回 error 62，PETSc 3.19.6 source 确认 setter 只允许 index 1..38，因此两块均记录 `COMPACTION_UNSUPPORTED`，但其他 Gate 继续执行。

N1 的 raw allocated/used 对照为：block 0 old/new `262,000,000/53,000,000 B`、used `29,000,000/29,000,000 B`，old/new `ICNTL(23)=490/73 MB`；block 1 old/new `261,000,000/51,000,000 B`、used `28,000,000/28,000,000 B`，old/new `ICNTL(23)=491/71 MB`。这些是 decimal `1,000,000 B` padded fields，used 不加入 retained inventory。

两个冻结代表块的 old/new CSR identity 相同，local residual 和 solution-difference Gate 通过；N1 总阶段时间 `162.24371241399967 s`，在 `900 s` calibration 预算内。该结果只证明新内存控制策略在代表块上与旧策略等价，不证明全 42-block macro stack 或完整物理外层。

## N2 resource negative

N2 使用新进程重建 context。block 40 完成后 retained inventory 为 `2,132,081,608 B`。在 block 41 numeric 前，当前矩阵 `7,128,340 B` 已包含在 `resident_before_factor=2,139,209,948 B`；symbolic-sized `Q=39,000,000 B` 只再加一次，得到 `2,178,209,948 B`，超过固定 `2,147,483,648 B` cap `30,726,300 B`。

这一路径未进入 numeric，因此不能称为 MUMPS `-9/-19`，也没有 full residual 或 physical result。独立 audit 确认没有重复计算 block 41 矩阵；block 0–40 的 82 次 Dw backsolve 最大相对残差 `2.1772149386553977e-15`。watchdog 采样峰 RSS `1,918,558,208 B`，阶段 sample RSS `1,918,562,304 B`，swap `0 B`；两者均只作为资源观测，不能替代冻结 inventory Gate。

四条证据边界保持分列：

- 内部质量只有局部 Dw/seed 和 N1 old/new difference；Review V11 规定的 I4 上限仍为 `4` 个新 PC，本轮 I4/B4 尝试与完成均为 `0`，真实 p4 error/full residual 未运行。
- 框架轴的 `BAL_H`、`ONE_C`、cached-native/map 未触达；不能以局部残差替代全系统耦合质量。
- restart32/64 未触达，也没有新的 restart 选择；N3 只表示这一条未运行轴。
- 总成本以冻结 ledger、精确 N1→N2 handoff 和 N5 独立 delivery-cutoff 为边界，未计时的 N5 剩余时间为 `unknown`。

原 A6 `1e-6`、L2/curl `1e-4`、R/T/A/`A_volume`/守恒 `1e-5`、80 复模式 `1e-4`、逐通道功率 `1e-6` 均未验证，不能发布 official output。旧 V5 original/notch 参考与 448 页系统换出归因限制保留；没有重建参考，也没有触碰 5 nm。

## Ledger、测试和交付边界

独立 ledger：`benchmarks/artifacts/task39extra/v11_n0_n2/v11_n0_n2_budget.json`。N1 watchdog `clock_end.utc_ns=1789108639276785985` 到 N2 watchdog `clock_start.utc_ns=1789108844160681955` 的无重叠 handoff 为 `204.883895970 s`；V11 N0–N2 最终 charged `4857.702833182024 s`，remaining `2342.297166817976 s`，总限额 `7200 s`。ledger 的 preparation 是一次性 `3746.0 s` activity envelope；N1 parent charge `177.4409457569965 s`，N2 charge `179.5419945970131 s`。N5 从 N2 结束 `1789109023702560780 ns` 到固定 cutoff `2026-09-11T07:32:05.459997954Z` 的 derived activity envelope 为 `2901.757437174 s`；它包含文档、监督、测试和工具下载等待，不是 CPU 时间，也不回填 N0–N2 ledger。cutoff 后和未独立计时部分保持 `unknown`。

正式 source-focused 回归为 `37 passed in 0.57 s`；N5 仅做 callback 等价风格修复后，当前代码再次得到 `37 passed in 0.71 s`。最终 raw stdout/stderr 已复制到 `outcomes/records/v11_final_focused_tests.stdout.log` / `.stderr.log`，SHA 为 `70f7b5369ab6599352433826bd9eb3c162011d199701b60923565d6a480e81f0` / `c1c1c3e72eb6feb8cada736d2101da1094b27f850d26e2064c1a8407818a719b`；ABI 摘要 `v11_final_abi.stdout.log` SHA 为 `31d16f39e8363f4c5555de06139d80c166ff8e6adb77f345faa17f5fbbec9f6a`。real MUMPS 小测试为 `test_355 actual_mumps: 2 passed`、`test_373 real_mumps: 1 passed`；V11 macro contract 还包括 `test_410: 9 passed` 和 `test_260: 3 passed`。full repository pytest 和 CI 均 `not_run`，没有作相应声明。

Ruff 0.11.13 的 13 文件独立差异核对为 baseline `85`、current `84`、new `0`；本轮只移除 N1 helper 的 E731，剩余为历史 diagnostics。全文件 Ruff 命令仍 exit 1，因此不能写成 Ruff 全通过；delta、baseline、current、check output 和 before-fix JSON 均已复制到 `outcomes/records/v11_ruff_*.{json,stdout.log}` 对应文件并 hash-bound。

正式运行 source SHA 为 `7c936958451bc196f784ecc30db9278c4e5b402f`，运行时工作树 clean；之后的 docs/compact 收口另行提交。向 `origin/task39extra` 的 push 曾被平台以 unverified remote/privacy risk 拒绝，按要求没有重试；没有执行 master merge，也没有 merge approval。

## 后续决定

V11 在 N5 停止。不得从 N1 局部通过推断 N3/N4 或完整 Maxwell 资格。下一步是将同一分支提交审阅本轮资源负结果及实现；V10 旧 default、旧 negative 和历史 evidence 保持不变。任何后续范围变化都须先取得新的 review、独立预算和新的 source/input identity，不在本轮擅自提高 cap 或改变分块。
