# Task39extra Review V11：symbolic-sized local MUMPS 生命周期与 N0–N5 收口

## 结论

本轮 V11 只验证一个显式 opt-in 的局部策略：把相邻单元的内部未知量组成一个小块，先对该块做局部物理矩阵分解，再保留分解结果供局部回代使用。新的 `SYMBOLIC_SIZED_LOCAL_MUMPS_V11` 策略根据 MUMPS 报告的 symbolic workspace 大小申请 `ICNTL(23)`，避免把已使用内存、最小值或 RSS 当作替代口径；普通默认和 V10 旧策略没有改变。

N1 在两个冻结代表块上通过了策略等价性；N2 在全 42 块流程完成 41 个 numeric/backsolve block 后，于第 42 个块（index 41）进入 numeric 之前被固定的 2 GiB retained-inventory envelope 阻断。阻断量是：已有常驻 inventory `2,132,081,608 B`，加第 42 块当前矩阵 `7,128,340 B` 和一次 `Q=39,000,000 B` 请求，得到 `2,178,209,948 B`，超过 `2,147,483,648 B` 上限 `30,726,300 B`。因此 N5 分类为 `LOCAL_INVENTORY_RESOURCE_BLOCKED`。

这不是系统 OOM 的证明，不是 MUMPS `-9/-19` 工作区错误，也不是 Maxwell 外层收敛失败：第 42 块没有进入 numeric，N2 没有产生 p4 true error、完整场或官方物理输出。N3 restart probe 和 N4 original/notch 均按前置 Gate 保持 `not_run`。

机器可读的紧凑记录为 [V11 lifecycle compact](records/macro_memory_lifecycle_v11.json)，SHA256 为 `14df814fe9b59e8dcdfee89a835837318d936d59ac45d060cc6085113845f5e2`。

## 身份、环境和 N0

| 项目 | 事实 |
|---|---|
| branch / formal source | `task39extra` / `7c936958451bc196f784ecc30db9278c4e5b402f` |
| model | 13.5 nm、p6/h10、Full3D、80 DtN modes、MPI1、线程1、`complex128` |
| V11 profile / policy | `physical_macro_dd4_v11` / `SYMBOLIC_SIZED_LOCAL_MUMPS_V11` |
| N1 input | `original_13p5nm_p6h10_macro_v11_n1.dat`，SHA `e8fe409069970686d4901ddb1d444e37c2305f46f15cb1697ffc65995641fe64` |
| N2 input | `original_13p5nm_p6h10_macro_v11.dat`，SHA `adde8c8c9e17fd8e0a84edb53b524a8c2f0a9e4f78313c9e27872c167abba7ad` |
| physical model | SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| ABI | qualified activation；PETSc `3.19.6`，scalar `numpy.complex128`，integer `numpy.int32`，Open MPI `4.1.6` |
| loaded MUMPS | `/usr/lib/x86_64-linux-gnu/libpetsc_complex.so.3.19.6`、`/usr/lib/x86_64-linux-gnu/libzmumps-5.6.1.so`、`/usr/lib/x86_64-linux-gnu/libmumps_common-5.6.1.so`、`/usr/lib/x86_64-linux-gnu/libmpi.so.40.30.6`；这些是 `/proc` resolved files |
| version distinction | MUMPS library SONAME/file is `5.6.1`，而 Debian package、header and source archive identify MUMPS `5.6.2`; the SONAME/file suffix is not silently relabeled |
| public controls | `MatMumpsGet/SetIcntl`、`GetInfo`、`GetRinfo` 可用；`ICNTL(23)` 可读回；`ICNTL(49)` getter runtime probe 返回 error `62`，PETSc 3.19.6 source 确认 setter 只允许 index `1..38`，未在 getter error 后伪造 setter runtime probe |

N0 同时绑定了 MUMPS 5.6.2 user guide PDF、纯文本摘录和 source archive。其 SHA256 分别为 `32acdd3e09fb69f9fab16c94ae67768d15c61ac9c27abf66eb1e0e6ecd904050`、`28439641e3be02fbcf224e8c120c036b6ac913084b3fd4640784746b060af9c2` 和 `13a2c1aff2bd1aa92fe84b7b35d88f43434019963ca09ef7e8c90821a8f1d59a`。手册语义是：`INFOG(16/17)` 为 symbolic internal-data estimate，`INFOG(18/19)` 为 factorization 后 allocated data，`INFOG(21/22)` 为 used data；`ICNTL(23)` 是每个 working processor 的 decimal-MB workspace cap，`ICNTL(49)` 是 factor-end compact request。

## V11 内存策略

对每个局部 block，在 numeric 前计算：

```text
E = 1e6 * (1 + max(INFOG16, INFOG17))
Q = 1e6 * ceil(max(32 MiB, 2 E + 8 MiB) / 1e6)
```

随后设置并读回 `ICNTL(23)=Q/1e6`。没有添加用于凑过 Gate 的 used/min/RSS offset，也没有提高 2 GiB、1 GiB 或 512 MiB 上限。运行时 getter 不支持 `ICNTL(49)`，记录为 `COMPACTION_UNSUPPORTED` 并继续其他 Gate；PETSc 3.19.6 source 确认 setter 只允许 `1..38`，未把它描述成已经成功运行的 index-49 setter probe。

## N1：新旧策略等价性通过

| 指标 | 实测结果 | Gate |
|---|---:|---:|
| 冻结代表块 | block 0、1，共 2 个 | 不超过 3 |
| old/new numeric attempts | 2 / 2 | 不超过 6 次 numeric factorization |
| numeric factorizations | 4 | 通过 |
| 最大 solves/factor | 6 | 不超过 16 |
| 最大 local residual | `5.438606648780365e-13` | `≤1e-10`，通过 |
| same-RHS old/new solution difference | absolute/relative 均 `0.0` | `≤1e-10`，通过 |
| matrix identity | 两个 block 的 CSR structure 和 values 均相等 | 通过 |
| build / old / new / total | `153.57479571899967 / 4.3210413769993465 / 4.245329184999719 / 162.24371241399967 s` | N1 预算内 |

局部分解的内存字段另列如下。`*_padded_bytes` 是每 `1,000,000 B` 向上取整的 decimal-MB 字段；allocated 和 used 都保留，不能用 RSS 替代。旧策略的 `ICNTL(23)` 是 block 0/1 的 `490/491 MB`，新策略读回为 `73/71 MB`；used 没有被当作 retained inventory 的组成项。

| block | old allocated (B) | new allocated (B) | old used (B) | new used (B) | old ICNTL23 (MB) | new ICNTL23 (MB) |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 262,000,000 | 53,000,000 | 29,000,000 | 29,000,000 | 490 | 73 |
| 1 | 261,000,000 | 51,000,000 | 28,000,000 | 28,000,000 | 491 | 71 |

关键 symbolic-sized request 与 readback：

| block | INFOG16/17 (MB) | E (B) | Q (B) | ICNTL23 readback (MB) | INFO1 | ICNTL49 |
|---:|---:|---:|---:|---:|---:|---|
| 0 | 31 / 31 | 32,000,000 | 73,000,000 | 73 | 0 | `COMPACTION_UNSUPPORTED` |
| 1 | 30 / 30 | 31,000,000 | 71,000,000 | 71 | 0 | `COMPACTION_UNSUPPORTED` |

N1 的首次 Dw backsolve residual 为 block 0 的 `1.8764473811290233e-15`、`1.5274357739644167e-15`，以及 block 1 的 `2.0002787934351233e-15`、`1.47642155285981e-15`。旧策略释放前/后进程树 RSS 为 `973,463,552 / 972,414,976 B`，新策略为 `979,546,112 / 978,497,536 B`；这些只是生命周期观测，不能宣称新策略节省 RSS，也不能替代 allocated/used 证据。

## N2：全 inventory 的受控资源负结果

N2 使用 fresh process rebuild，未复用 N1 context。它完成 block 0–40 的 41 份 numeric 和 backsolve 记录，保留每个 block 的 symbolic、numeric、backsolve、post-backsolve inventory raw JSON；block 41 只生成了 pre-numeric symbolic gate record。

| 量 | 值 | 说明 |
|---|---:|---|
| 目标 block 数 | 42 | 完整 macro stack |
| 已完成 numeric/backsolve | 41 | block 0–40 |
| 失败 block | index 41 | 第 42 块，numeric 前 |
| block 40 后 retained inventory | `2,132,081,608 B` | `allocated 1,643,000,000 + CSR 443,371,460 + base/shared 45,710,148`；三项相加得到该值 |
| used parallel report | `874,000,000 B` | 与 retained inventory 并列报告，**不**加入上述求和 |
| block 41 当前矩阵 | `7,128,340 B` | 已包含在 `resident_before_factor` |
| block 41 symbolic-sized Q | `39,000,000 B` | 只加一次 |
| resident before factor | `2,139,209,948 B` | inventory + 当前矩阵 |
| conservative request envelope | `2,178,209,948 B` | resident + Q |
| fixed cap | `2,147,483,648 B` | 2 GiB |
| excess | `30,726,300 B` | 超过 cap |
| measured process-tree RSS peak | `1,918,558,208 B` | watchdog peak；另有阶段 sample `1,918,562,304 B`，两者均保留；不替代 frozen inventory Gate |
| swap / cleanup | `0 B` / descendants cleared | 资源停止清场正常 |

独立 audit 已重算 block 0–40 的 82 次 Dw backsolve，最大相对残差为 `2.1772149386553977e-15`；41 份 post-backsolve allocated/used 与 numeric records 一致。逐块 hash-bound compact 见 [per-block compact](records/macro_memory_lifecycle_v11_blocks.json)，SHA256 `445cf3c09bc3bdcd0468c8132f90a5d7ac743d59baac482d212f7c2c26266ccd`；N2 audit 的可推送副本见 [N2 supervisor audit](records/v11_n2_supervisor_audit.json)，SHA256 `c5aae42630316be9a6c1d47037393ab50e8361a81f5b359c9a65f17c84f32737`。审计确认 block 41 当前矩阵没有被重复计入，且没有用 E、used 或 RSS 替换 Q。N2 runner 的 `MemoryError` 是本地策略 Gate 的内部分类；它不是 MUMPS numeric failure，因为第 42 块没有 numeric factorization。

## 四条不可混淆的证据边界

| 证据轴 | 本轮实际测量 | 尚未测量/不能推出 |
|---|---|---|
| 内部质量 | 局部 Dw backsolve、固定 seed 和 N1 old/new solution difference；N2 41 个 block 的 raw-norm audit | 真实 p4 error 和 full true residual；I4/B4 尝试数与完成数均为 `0`，不是 solver failure |
| 框架耦合 | 未触达完整 framework controls | `BAL_H`、`ONE_C`、cached-native/map 和 p4 framework correction 均 `not_run` |
| restart | 未启动 restart workflow | restart32/64 未触达；本轮没有新 restart 选择 |
| 总成本 | 独立 V11 ledger、N1→N2 无重叠 handoff 和 N5 单独 delivery-cutoff 口径 | N5 未独立计时的剩余文档/等待时间保持 `unknown`，不回填 N0–N2 |

因此原 A6 `1e-6`、L2/curl `1e-4`、R/T/A 与 `A_volume`/守恒 `1e-5`、80 复模式 `1e-4` 及逐通道功率 `1e-6` 均未验证，不能发布 official output。V5 原始/notch 离散参考和其 448 页系统换出归因限制仍按历史保留；本轮没有重建参考，也没有触碰 5 nm。

## N3、N4 和 N5 分流

由于 N2 未完成 42-block inventory，以下项目全部保持未运行，不得从 N1/N2 局部残差推断：

- N3 restart32/64；
- N2 规定的 true p4 error、cached-native map、BAL_H、ONE_C 和完整 framework controls；
- N4 original/notch、outer Krylov、E/H、R/T/A、`A_volume`、显著衍射级和 official outputs。

N5 固定结论为 `LOCAL_INVENTORY_RESOURCE_BLOCKED`。下一步只有将同一分支提交审阅本轮资源负结果及实现；本轮不重跑、不调参、不扩 MPI、不擅自提高 cap 或改变分块，也不把 N2 改写成数学失败或物理失败。若审阅后范围发生变化，必须另建 review、独立预算和新的 source/input identity。

## 成本和证据入口

独立 V11 N0–N2 ledger 为 `../../../benchmarks/artifacts/task39extra/v11_n0_n2/v11_n0_n2_budget.json`。N1 watchdog `clock_end.utc_ns=1789108639276785985` 到 N2 watchdog `clock_start.utc_ns=1789108844160681955` 的无重叠 handoff interval 为 `204.883895970 s`；它替代此前仅覆盖到 handoff cutoff 的 `130 s` 估计，不与 N1 parent 或 N2 worker 重复计费。总限额 `7200 s`，build `3600 s`，controls `1200 s`，N1 calibration `900 s`；完成该 handoff reconciliation 后 N0–N2 ledger charged 为 `4857.702833182024 s`，remaining 为 `2342.297166817976 s`。准备 envelope `3746.0 s`、N1 parent charge `177.4409457569965 s`、N2 charge `179.5419945970131 s` 均只计一次。N5 从 N2 结束 `1789109023702560780 ns` 到固定 cutoff `2026-09-11T07:32:05.459997954Z` 的 derived activity envelope 为 `2901.757437174 s`；该区间包含文档、监督、测试和工具下载等待，不是 CPU 时间，也不回填 N0–N2 ledger。cutoff 后以及早期未独立计时部分保持 `unknown`，不伪造 CPU 成本。

形式运行的 compact/raw 证据均在 ignored artifact root，未把大矩阵、factor、field、cache 或 timeline 加入 Git；N1 supervisor audit 和逐块 compact audit 已复制为小型 tracked records：

- N1 `run_summary.json`：SHA `01c9fbabbda84cb0e7bbaed05620f897671df33c53e9074d1141e7500923b03c`；`run_manifest.json`：SHA `5722708f32dfd84106d310799dd95a2aa7377ce68a6c2723789e1cd0840826e6`；terminal/watchdog summary：SHA `1a01e0d16fa21eff418efd5396727a40c39c384cf89758cb6189b3ecd5f97597`。
- N2 `m1_summary.json`：SHA `8415056089e3568f3cce6cd52f0413b437e80f919cc564ec1cf1c2c248750f70`；`run_summary.json`：SHA `e7b78aa0fe87249b4b4394379913939d6f7254e6ffbda5bb7fed06f47cb1c3ca`；`run_manifest.json`：SHA `d0933796596533e96c07d4646c9cd18cc290806d5e076f0261c168b2d95c3e75`；terminal：SHA `cbdba9fb8a87b1f75b48486f9b587b9e2f6cdcc36edbfaa76db75a494240207d`；stages：SHA `c70367872bb6e97591a2f7bb32b8fca7bc3b8e5b1f048f771093eee2ccd1ab16`。
- N2 independent audit `/tmp/task39extra-v11-n2-supervisor-audit.json`：SHA `c5aae42630316be9a6c1d47037393ab50e8361a81f5b359c9a65f17c84f32737`。
- N1 supervisor audit [copy](records/v11_n1_supervisor_audit.json)：SHA `7c58950950c79fa121ed3c81a9e2eb320884339a0170cfbe44ae40bd0246ba5d`；逐块 compact audit [copy](records/v11_per_block_compact_audit.json)：SHA `a915a42b683d8d1d661ee3a163f9fad5e1969af33332fe5b9416cc710a819280`。
- focused test raw stdout/stderr 已复制为 [stdout](records/v11_focused_tests_supervisor.stdout.log) / [stderr](records/v11_focused_tests_supervisor.stderr.log)，SHA 分别为 `cd8d0d4e20acef2c052a88cb70631a96cf93d4a5e3e701b2835ab51a54bb8455` / `ccb5f758e2b7c490417fb1ecef34a3227cb64cbcbacfcd6d6f4cf92c24db24c4`。
- N5 只修复新 N1 helper 的 callback 风格（lambda→等价 def），当前代码回归为 `37 passed in 0.71 s`；[final stdout](records/v11_final_focused_tests.stdout.log) / [stderr](records/v11_final_focused_tests.stderr.log) SHA 为 `70f7b5369ab6599352433826bd9eb3c162011d199701b60923565d6a480e81f0` / `c1c1c3e72eb6feb8cada736d2101da1094b27f850d26e2064c1a8407818a719b`。Ruff 0.11.13 对 13 个文件的 baseline/current/new 为 `85/84/0`；全文件命令仍因历史 diagnostics exit 1，不能宣称 Ruff 全通过，完整差异记录见 [Ruff delta](records/v11_ruff_delta.json)。

测试收口见 [V11 test summary](test_summary.md)、模型登记见 [development model registry](../../../docs/development_model_registry.md)、工作站边界见 [workstation handoff](workstation_handoff.md)。V11 的依赖组边界见 [selective merge manifest V11](selective_merge_manifest_v11.md)；唯一下一步是把同一分支提交给审阅本轮资源负结果及实现；当前没有 `master` merge approval。
