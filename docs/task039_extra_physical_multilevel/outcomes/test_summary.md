# V12 O0–O4 测试、raw 记录与静态收口

本节是 V12 source/evidence closeout；不重新启动 PDE、MPI、factor 或 O2/O3。正式 source SHA 为 `e8c3c82bab2687a811a11f0798a2879c725532b5`，review base SHA 为 `96e5d5fcfc3e801ef33d4a2d241ea7571937f734`。测试使用仓库规定的 qualified activation；没有 full repository pytest 或 CI 通过声明。

| 检查 | 结果与边界 |
|---|---|
| changed-source focused regression | `27 passed in 0.72 s`；覆盖 `test_260_task038_input_schema.py`、`test_365_light_pc_monitor.py`、`test_410_physical_macro_dd4.py`；[stdout](records/v12_final_root_focused.stdout.log) SHA `06fb627be4f8eb56eda298be72080c1a3e41a61c9046274bcd8b6b9bd0c666dc`；[stderr](records/v12_final_root_focused.stderr.log) SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| supervisor stop smoke | 3 个 `PASS`：monitor-at-10 保留 safe iteration10；external-at-50 保留 iteration48；真实 `FloatingPointError` 原样传播；[stdout](records/v12_stop_smoke.stdout.log) SHA `de2906176ec9a4a43537dff33021072d4edb1ad4a50b0a6b19d354bf38230b29`；[stderr](records/v12_stop_smoke.stderr.log) SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| V12 dat dry-run | 9/9 public dry-run exit `0`，PDE 未启动，old profile caps unchanged；[stdout](records/v12_dat_dry_run.stdout.log) SHA `ac6ea60956a6830a867c246cdfe00e62d8a0f8f433c907d81e041647fbcc6772`；[stderr](records/v12_dat_dry_run.stderr.log) SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| ABI preflight | qualified Linux stack；PETSc scalar `complex128`、integer `int32`、MPI1/线程1；V12 formal identity 与 preflight 文档绑定；没有 Windows ABI 污染 |
| Python/static | qualified `compileall` exit 0；显式 Git dir/worktree 下 `git diff --check` exit 0 |
| changed-file Ruff | parent 保存的 Ruff 0.11.13 changed-file F821/F822/F823 检查通过；这不是 full-repository Ruff pass，历史 diagnostics 未改写 |
| Markdown/registry contract | `test_183_development_model_registry_markdown.py` + `test_26_documentation_contract.py`: `20 passed in 0.05 s`；只验证文档/登记合同，不是 PDE 或 full repository pytest |
| additional registry audit | `test_development_model_registry_contract.py` 批次为 `20 passed / 1 failed in 0.09 s`；唯一失败是历史缺失 `docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_small_v2_checker.json`，该路径在 review base 的既有 registry 引用中已缺失，本轮不修旧 Task038、不伪造 checker；[stdout](records/v12_final_root_docs.stdout.log) SHA `a32d9b6d463456db04c45d997fa2b4d8dc58ff446cf14d1be316caa32309db1c`；[stderr](records/v12_final_root_docs.stderr.log) SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；[baseline audit](records/v12_final_root_doc_audit.json) SHA `464bae144d1058295f4d16a620d807aa19f3f74e6a05f3e066c7123410d1efd2` |
| V12 JSON/evidence | compact、terminal/budget、inventory、p4/resource audit、lossless raw JSON evidence 可解析；原始 raw JSON SHA `0ff0246b6c1212b5d1c2706cd1954884626b828192697d1a7d0c9e99d06e6710`，tracked normalized copy SHA `329ed513c351896c3db09ea5899389a060b71ff36805daf456132e304fdd1580`；两者解析后的 JSON 值相同 |
| formal stage audit | O0/O1/O4 terminal hashes、42-block inventory、88-check p4 arithmetic audit、resource audit 均已写入 [V12 compact](records/physical_macro_v12_compact.json) 及其 records |
| full repository pytest / CI | `not_run`；没有 CI 通过声明 |

V12 的 `p4` 数值记录只说明有限 4-step I4/B4 控制及其真实 residual/field error；O1 shared budget stop 后没有新 PDE。大型 raw/matrix/factor/field/cache/timeline 保持 ignored，tracked raw 只保存轻量可审阅日志和 hash-bound JSON evidence。

---

# 历史：V11 N5 compact、文档合同与静态检查

本节登记 Review V11 的 docs/evidence closeout，不重新启动 PDE、MPI、factor 或 N3/N4。37 项 source-focused regression 已绑定正式 source SHA 并保持不变；本轮只验证新增 compact、逐块汇编、Markdown 链接/登记合同和源码语法。

形式 N1/N2 仍绑定 source `7c936958451bc196f784ecc30db9278c4e5b402f`。随后仅为新 N1 helper 修复一处 Ruff E731（`save=lambda` 改为等价 `def`），不改变数值语义、策略或 formal artifact identity；因此不重跑 PDE。

| 检查 | 结果与边界 |
|---|---|
| formal source-focused regression | `37 passed in 0.57 s` on formal source `7c936958...`；raw stdout/stderr 已复制到 [stdout](records/v11_focused_tests_supervisor.stdout.log) / [stderr](records/v11_focused_tests_supervisor.stderr.log)，SHA `cd8d0d4e20acef2c052a88cb70631a96cf93d4a5e3e701b2835ab51a54bb8455` / `ccb5f758e2b7c490417fb1ecef34a3227cb64cbcbacfcd6d6f4cf92c24db24c4` |
| final callback-only regression | E731 等价格式修复后 `37 passed in 0.71 s`；raw stdout/stderr 已复制到 [stdout](records/v11_final_focused_tests.stdout.log) / [stderr](records/v11_final_focused_tests.stderr.log)，SHA `70f7b5369ab6599352433826bd9eb3c162011d199701b60923565d6a480e81f0` / `c1c1c3e72eb6feb8cada736d2101da1094b27f850d26e2064c1a8407818a719b`；ABI 摘要见 [ABI](records/v11_final_abi.stdout.log)，SHA `31d16f39e8363f4c5555de06139d80c166ff8e6adb77f345faa17f5fbbec9f6a` |
| real MUMPS probes | `test_355 -k actual_mumps`: 2 passed；`test_373 -k real_mumps`: 1 passed；另有 backend snapshot 成功；不等于 N2 full inventory |
| V11 macro contract | `test_410`: 9 passed；`test_260`: 3 passed；`test_355` non-real subset: 13 passed, 2 deselected |
| documentation/model-registry contract | `test_26_documentation_contract.py` + `test_183_development_model_registry_markdown.py`: `20 passed in 0.05 s`; raw stdout/stderr 已复制到 [stdout](records/v11_n5_docchecks.stdout.log) / [stderr](records/v11_n5_docchecks.stderr.log)，SHA `88d00f8cc25efd895f76b07d9fb811f1782b4872206c18eea2a70638637b1c0a` / `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Python syntax | qualified activation 下针对 V11 changed runners、input validation 和 focused tests 执行 `python -m py_compile`，通过 |
| Ruff | 使用官方 Ruff 0.11.13 archive（SHA `01aa32d29d00876b8d1429c617ed63a00b1fc81abfa4183bb05c9cb647fbc3d0`）；13 文件 baseline `85`、current `84`、new `0`，移除的唯一新增诊断是 N1 helper 的 E731；全文件命令仍因历史 diagnostics exit 1，不能写成 Ruff 全通过。raw [delta](records/v11_ruff_delta.json) SHA `7713164d593b24a70dfc4de49cc074adc4bb91f155f44766b58e37e6b2ae82c3`、[baseline](records/v11_ruff_baseline.json) SHA `31c072312e88808ab4d59f3a783b15660e3ea1ddffdfdedfa54f785e39871f62`、[current](records/v11_ruff_current.json) SHA `bddb1fe4a2c543330c67594517adaa5ef41e8a218e7fa7eec5fba98648d6db93`、[check output](records/v11_ruff_check.stdout.log) SHA `c8bb7fad3c1f7bc5c4e13f941cc21142532115f54d1567f0cce1ab155bd4f487`；[before-fix](records/v11_ruff_before_fix.json) SHA `dff3d03e8ff26391eeee839438d04807cd0131c6d66314c33eb790f963de2264` |
| JSON/static | compact、per-block compact、copied audit、ledger 可 `jq empty`；`git diff --check` 在显式 Git dir/worktree 下执行 |
| full repository pytest / CI | `not_run`；没有 CI 通过声明 |

证据中心见 [V11 lifecycle](macro_memory_lifecycle_v11.md)、[compact](records/macro_memory_lifecycle_v11.json) 和 [per-block compact](records/macro_memory_lifecycle_v11_blocks.json)。N2 的资源负结果仍为 `LOCAL_INVENTORY_RESOURCE_BLOCKED`，N3/N4 和 official outputs 不因本节静态检查而改变。

---

# V10 M4 compact evidence与文档检查

本节是当前 V10 文档/证据收口。V10 不再启动 PDE、MPI、factor 或 M2/M3；静态检查只验证 compact、run index、链接、哈希和文档合同，不把局部小测试冒作 M1 controls 或 physics PASS。

| 检查 | 结果与边界 |
|---|---|
| V10 compact JSON | `jq empty` 通过；14 个 persisted local backsolve checks 和 6 个 native witness checks 可从 `difference_norm/rhs_norm` 或 `difference_norm/operation_scale` 独立重算；block 7 pre-factor/numeric INFOG raw fields 已保存；compact SHA=`1615eda5143a351a694b45b180e39a4fa1b728a03d882c513b87864fa7a334cc` |
| V10 run index | `jq empty` 通过；V5–V9 历史条目保留，V10 source/input/physical/ledger/compact hash 与 `not_run` 边界已登记 |
| V10 focused regression | test361/test379/test410 合计 `55 passed in 1.81 s`；这是 task-focused regression，不是 full repository pytest |
| V10 macro suite | `9 passed in 0.52 s`；覆盖局部 macro witness/selection/contract，不等于 M1 controls 完成 |
| 静态代码检查 | macro solver/test Ruff 通过；changed macro modules `py_compile` 通过 |
| 测试日志 | [v10_m4_test_run.log](records/v10_m4_test_run.log)，SHA `f484c96d8231de6b56052f162457010d8a2bba8d1af6b3992dfc8d950090cc97`；source `b0df7457c0c4b33c66abda16862926da3426bb7d`；手工编译摘录，不是 raw stdout；轻量 task-focused/static only |
| 文档链接/哈希 | 当前 V10 sections 的 8 份文档、26 个本地 Markdown 链接 resolve 通过；`jq empty`、hash 对照和 `git diff --check` 通过；大型 raw/matrix/factor/cache 仍在 ignored artifact |
| full repository pytest | `not_run` |
| CI | `not_run`；没有 CI 通过声明 |

本节不改变第二次 M1 的 `RESOURCE_BLOCKED` 结论：system RSS peak=`1107648512 B`、job swap=`0 B`，停止原因是保守 allocated policy 超过 2 GiB，而不是系统 OOM。完整边界见 [V10 中心结果](physical_macro_inverse_v10.md) 和 [V10 compact](records/physical_macro_inverse_v10.json)。

---

# 历史：V9 compact evidence与文档检查

本节是当前 V9 的 L4 收口记录。V9 的 L0 prototype 与 L2 正式 PDE 已在此前完成；本节只补充 compact evidence 和文档索引，不再改代码、不再运行 PDE、MPI、factor、正式 checker 或 full repository pytest。旧 V8/V7/V6/V5 测试记录继续保留在下文，不能被本节的 docs-only 检查冒作新的数值资格。

| 检查 | 结果与边界 |
|---|---|
| L1 compact schema/字段 | 12 个 sequence I4 + 4 个 complete-control I4 分开登记；`total_i4_calls=16`、`total_B4_applies=256`，RESET/CARRY residual、q、累计时间和 raw SHA 已写入 [V9 compact](records/equal_work_recycled_p4_v9.json) |
| L2 compact schema/字段 | `A4_matvec=1292`、`explicit_A4=168`、最大 I4 elapsed、native exit relative spot、pool/closure audit、monitor residual curve 和 76 行逐 I4 标量表已写入 [V9 compact](records/equal_work_recycled_p4_v9.json) |
| L0 clean-SHA prototype tests | source `55b7325cae8477ded7b04cfab42181f18e035a0f`；test391 的 `v8_k1_fake_runner`/`v8_k1_real_engine`/`v9` 合计 `10 passed / 0.22 s`；test386 指定 4 项 `4 passed / 0.21 s` |
| historical prototype/checker tests | V8 focused/checker-only 测试在下方历史段保留；本轮 L4 不重跑 |
| JSON/static validation | qualified activation 下解析 V9 compact/run index，核对计数、绝对/相对路径、raw SHA 与 L1/L2 scalar；结果为通过 |
| hash/link/diff | 核对 V9 compact 声明的 raw SHA、中心报告链接和 `git diff --check`；结果为通过 |
| PDE/solver regression | 未运行；不声称新的 pytest、MPI、formal checker、CI 或 full repository 通过 |

L2 的 `TIME_PROGRESS_SCREEN_STOP`、full explicit residual `0.1292009191903606`、资源峰值和 preparation partial ledger 语义见 [V9 中心结果](equal_work_recycled_p4_v9.md)。这些文档检查不改变 `EQUAL_WORK_RECYCLE_BOUNDED_NEGATIVE`，也不把固定新工作量或内部计数改写为完整求解 speedup。

---

# 历史：V8 K4 compact evidence与文档检查

本节是历史 K4 收口记录。K4 只补充可审阅的 compact evidence 和文档索引；没有新建或重跑 PDE、MPI、factor、正式 checker 或 full repository pytest。旧 V7/V6/V5 测试记录继续保留在下文，不能被本节的 docs-only 检查冒作新数值资格。

| 检查 | 结果与边界 |
|---|---|
| K1 compact schema/字段 | RESET/CARRY per-input native residual、`eps`、pool、B4/A4，以及两次完整 control 的 PC 秒数、g2 recompute 和 eps closure 已写入 [V8 outer compact](records/recycled_p4_outer_v8.json) |
| K2 compact schema/字段 | `A4_matvec=1098`、`explicit_A4=260`、最大 I4 elapsed、native spot、pool closure/orthogonality、terminal eps audit 和 118 行逐 I4 标量表已写入 [V8 outer compact](records/recycled_p4_outer_v8.json) 与 [per-I4 rows](records/recycled_p4_i4_rows_v8.json) |
| K1 prototype focused tests | 已完成 `31` 项 focused tests，绑定 prototype/run source `09c1b3a6f3c21d4d0e99feb36a97972819971fb3`；当时 K4 不重跑 |
| K1 checker-only tests | checker-only 新增 `1` 项、旧项复核 `4` 项均已完成，绑定 checker-fix source `49ddad7f4b196e45e449c1044d90b17d6ee6300c`；当时 K4 不重跑，pre-fix 与 post-fix checker hash 均保留在 compact |
| JSON/static validation | qualified activation 下解析新增/更新 JSON，核对 118 行、关键计数、相对路径和逐 I4 compact SHA；结果为通过 |
| hash/link/diff | 核对 compact record 声明的逐 I4 SHA、相对文档链接和 `git diff --check`；结果为通过 |
| PDE/solver regression | 当时未运行；不声称新的 pytest、MPI、formal checker、CI 或 full repository 通过 |

K2 的 `NORMAL_SCREEN_STOP`、full explicit residual `0.09114277170870674`、资源峰值和 reserve/actual ledger 语义见 [K4 中心结果](recycled_p4_outer_v8.md)。这些历史文档检查不改变 `RECYCLE_BOUNDED_NEGATIVE`，也不把内部 B4 减少改写为完整求解 speedup。

---

# V7 J5本地测试与文档检查

本节是当前 J5 收口记录。以下 V6、V5 及更早验证均为历史批次，原测试结果和失败原因保留，不冒作本轮重跑。

| 检查 | 结果与边界 |
|---|---|
| source targeted regression | `8 passed in 0.22 s`，覆盖 `test_390_projected_seq2.py` 与 `test_388_bounded_checker.py` 的相关排除项；source `355322e8be0716cdc3dd70df2665b8c74ff76583` |
| B finite raw recheck | `recompute_bounded_i4` 通过；4 I4、2 complete PC、实际 H6 2；`recompute_projected_trace_costs` 通过 |
| finite checker distinction | generic `bounded_costs` 对旧的 2-row audit expectation 返回 false；实际合法 audit lifecycle 为 4，原因和 `checker_recheck.json` 已 hash-bound 记录 |
| B formal outer checker | 原始 checker 的 bounded I4、screen、cost、projected trace 通过；fine residual 和 official-output gates 未通过 |
| compact/document contract | 本轮只做 JSON、raw hash、相对链接、历史保留和 diff 检查；不运行 PDE、MPI、factor、正式 checker 或 full pytest |
| CI/full repository | 未运行；不声称 CI 或 full repository pytest 通过 |

J5 追加命令费用按共享账本的实际记录计入，不把模型等待时间重复收费。A compact [bounded_inexact_outer_a_original_v7.json](records/bounded_inexact_outer_a_original_v7.json) 保持原字节不变；新增 [B finite compact](records/bounded_inexact_outer_b_controls_v7.json) 与 [B original compact](records/bounded_inexact_outer_b_original_v7.json) 分别绑定 source、input、raw root 和关键 artifact SHA。

---

# 历史：V6本地测试与文档检查

G1/G2已完成，旧新C真实负结果保留；用户补充授权继续有依据的p4/p2诊断，G5与response_v8尚未最终收口。该授权超出V6原停止分流，不改变物理、精度或安全线；不复跑G1/G2。

| 批次 | 结果 / 失败原因 |
|---|---|
| focused_v1 | 6failed/18passed/2deselected；PETSc3.19枚举DIVERGED_ITS不可用，改为DIVERGED_MAX_IT；原失败保留 |
| focused_v2 | 8passed/4deselected；有界I4、finite cap/饱和、tiny6/4/2通过 |
| focused_v3 | 2failed/5passed/8deselected；稀疏fixture向1NNZ矩阵插入密集行导致分配错误，非PDE方法失败 |
| focused_v4 | 2failed/5passed/11deselected；替身接口缺apply_into，局部fixture修正 |
| focused_v5 | 2passed/16deselected；精化fixture通过 |
| focused_v6 | 9passed/9deselected；input unchanged/slave-zero和失败成本证据补齐 |
| focused_v7 | 1passed/17deselected；非有限attempted/completed计数局部检查 |
| g2_focused_v1 | 16passed/0.94s；无FE组装，含旧V5 launcher兼容 |
| g2_focused_v2 | 最终17passed/3.79s；新增冻结RHS/映射桥fixture；parent收费5.265852279s |
| G1正式 | 首次JIT遗留cache失败0I4/0PC，唯一冷cache重试完成六+三；0/6 LO target，非数值通过 |
| G2正式 | screen数值负结果；独立checker通过账本/闭合验证，未通过fine残差与official输出 |
| 当前阶段文档 | compact JSON、相对链接及diff局部检查；G5未最终收口，记录见ignored p4_stage_docs_check.json |

初始新测试18种通过分布于各focused批次，不能写成一次30passed；未重跑昂贵G1/tiny/完整pytest，未声称CI。全部监督测试树swap0/globalΔ0且清场；所有失败计费和raw日志均由[compact](records/coarse_inverse_replacement_v6.json)绑定。没有新增测试框架。


以下完整保留历史正文；“当前/下一步”仅指当时阶段，以本节为最新状态。

---

# V5完整链与E5文档检查

| 验证 | 结果与口径 |
|---|---|
| 已提交恢复实现 | 本地47 passed /1.62s；source094204b7281fe867744fe334e8753d2faebaf89b；本E5未重跑数值测试 |
| 完整求解 | 原始564/notch576步，完整残差≤1e-6，匹配参考及物理Gate通过 |
| 资源 | sampled tree swap0；条件参考global out448页归因UNRESOLVED，不能视为全系统swap0 |
| raw证据 | 主线程独立637文件hash通过；本E5不重复全面校验 |
| E5最小检查 | 结果写入ignored e5_docs_check.json；仅JSON/绑定hash/链接/历史保留/diff，不运行PDE |

详细结果见[balanced_coupling_v5.md](balanced_coupling_v5.md)。以下为保留的历史验证记录。

---

# 补充授权真实误差定位：分阶段验证与最终文档检查

| 检查 | 结果 |
|---|---|
| 参考实现最小批 | 32 passed /1.47s；历史日志保留，未冒作本次重跑 |
| incident quadrature窄修 | 9 passed /1.57s；普通默认不变，匹配native degree25 |
| actual-error接线最小批 | 10 passed、1 FE项deselected /0.40s；含真实3snapshot/reference/9PC纯读load smoke，无FE |
| 独立ABI/静态 | qualified Linux complex128/int32、MPI1/线程1；ABI子进程退出后启parent；compileall/diff通过 |
| matched reference | 原A6≤1e-10、canonical/map/RHS/audit93hash资格；旧reference failure保留 |
| actual-errors saved-only | 224 raw/cache哈希；3投影、6平滑、0new fullPC、4p4 RHS/4MatSolve/0refinement；原A4残差独立重算≤1e-10 |
| 补充代数审计 | Gram相位无关相关、g两部分cross/相消、MR alpha、能量分解及owned-cell材料/高度归一化通过；M0仍是正式runtime实测，不称重装配FE验证 |
| 资源/清场 | 全5302样本违规0、swap0、global delta0，所有观测PID清场；双时钟原值保留并保守计费 |
| docs-only收口 | 仅JSON/hash/link/历史保护/diff检查；报告benchmarks/artifacts/task39extra/fine_reference_followup/docs_v5_static_checks.json |

中心JSON索引日志、源码及两份可审阅saved-only脚本。最终文档没有重跑FE/PDE/factor/PC/pytest/full suite，没有Ruff安装或CI通过声明。

## 历史V4及此前验证（原文当前仅指当时）

# Review V4 / C5验证：诊断完成，未新增完整PDE资格

| 验证 | 结果与证据 |
|---|---|
| 一批C0 focused | 23通过、5失败、2 deselected；5失败同因decision packet重复policy字段，属于写包bug |
| 定向修复复测 | 7通过、8 deselected；覆盖全部5失败及拆分的atomic/旧artifact审计，旧artifact缺失时该审计明确skip |
| 其他静态/ABI | compileall、git diff --check通过；独立ABI子进程完全退出后启动child-free watchdog；complex128/int32/同Linux ABI/线程1 |
| 正式C1–C3 | 8PC/4互补/10逻辑p4/12MatSolve；C2先于C3；投影110步残差9.27038e-11，原p4重建门槛未放宽，2个真实输入各精化一次 |
| raw checker | 保存的g/A4y重算r4、增广残差差向量及范数；最后10个p4输入≤1e-10；2新真实PC的q/Az残差比重算；哈希绑定全部raw |
| 资源/清场 | 3936样本无违规，RSS峰3540959232 B、swap0；parent987127/MPI987185/worker987188均清场 |
| C5最终检查 | 只做JSON/hash/文档链接/历史保护/diff检查；不重复FE/PDE或pytest，不安装Ruff，不声称CI/full repository通过 |

C0原始失败与修复日志位于`benchmarks/artifacts/task39extra/v4_c0/`；正式独立审计位于`benchmarks/artifacts/task39extra/v4_completion/b127546f172e46d0b217680338b4e0ea7aa39f12/completion_audit.json`。完整命令、哈希和新批时间账见[中心JSON](records/diagnostic_completion_v4.json)。诊断成功只证明这些控制与记录通过，不生成official R/T/A或真实散射参考。

## 历史V3验证（原文当前仅指当时）

# D5最终验证：工程政策通过，正式诊断发生数值拒绝

| 对象 | 最终证据与边界 |
|---|---|
| conservative_realtime接线 | 19 passed / 5.50 s；ABI与编译通过；source bf8e0c1d16c9c86677e866cdf29fd5491f076e32 |
| 日志 | benchmarks/artifacts/task39extra/v3_clock_policy/focused_tests.log；SHA256 14e7553168ff8fdb3a0a171b2b947df16151f4c9f378c18ddf32bdc9f32d3c73 |
| Windows独立对照 | Interop socket失败，未启动35秒对照；没有安装/系统修改，不冒作计时资格PASS |
| 正式数据复核 | 3 identities从b/x/Ax/r/分项/Gram复算，7 PC从q/Az复算；8 started/7 completed；失败p4向量未保存，只有代码/标量核对 |
| 数值拒绝 | JOINT448→LIGHT原A4残差1.0086968840613509e-10>1e-10；不因19测试通过提升为formal PASS |
| 资源/时间 | 3324样本RSS峰3777171456 B、swap0、资源违规0；watchdog保守945.519547 s、outer952.495115 s独立核对，清场完成 |
| D5最后一批 | 仅JSON/证据hash/链接/表格/历史保护及diff检查；报告benchmarks/artifacts/task39extra/v3_d5_numerical_closeout/static_checks.json；无新pytest/代码/PDE/CI声明 |

详见[最新中心记录](records/nonconvergence_diagnosis_v3.json)。原TIMEBASE停止和MPI预检导致的launch false-start均保留；旧V2的181测试不冒作本轮数学资格。

## 历史验证（以下当前均指当时）

# Task39extra：Review V3 / D5 验证边界

| 验证 | 实际结果 |
|---|---|
| V3小批次 | tiny 6 passed；诊断7→8→8 passed；后续bridge/mode窄修1 passed、raw能量字段2 passed；各日志/命令/hash见中心JSON |
| ABI/编译 | 资格化activation，仓库.venv，complex128/int32、Linux统一栈、MPI1/线程1；源码24b3dbb的compile/diff已通过 |
| 唯一原尺寸诊断 | TIMEBASE_INCONSISTENCY受控停止；完整PC/互补/投影均0；不是数学测试通过 |
| D5 | 仅JSON解析、相对链接、关键artifact/hash、文档与git diff检查；不新增pytest、PDE、环境调查或系统改动 |
| 未声明 | 无full repository/MPI sweep、无新Ruff或CI通过；旧181批次只属V2，不冒作V3原尺寸资格 |

短检查累计预算13.183744896 s，正式前准备/失败一并按保守外部4936 s扣账，不能只扣pytest。D5静态检查结果保存于`benchmarks/artifacts/task39extra/v3_d5_closeout/static_checks.json`。详见[中心JSON](records/nonconvergence_diagnosis_v3.json)。

## 历史V2及此前验证

# Task39extra：F5 最终验证

F3正式只读审计通过：476PC/476原p4检查、14完整周期+28尾段、checkpoint/hash/零初值、reported/explicit差、资源/清场核对。属于证据一致性通过，原A6残差0.10535820013809101>1e-6，solver未通过。双时钟差异单列，不以测试通过掩盖UTC solve超7200。

最终一次task-focused回归：**181 passed、1 skipped**（test362的MPI2专用fixture）；覆盖test352/354/355/356/358/359/360/361/362/363/365/366/367/368。ABI preflight和compileall通过，源码仍为60b8df2a24cbcd96e49e018be22fb64f06eeae3f，只改文档。不跑full repository/PDE，不安装Ruff，无CI通过声明。F1最终85 passed、F3实现63 passed及失败fixture均保留，见[中心记录](records/packed_and_joint_mr_v2.json)。

| F5最终测试口径 | 记录 |
|---|---|
| pytest报告 | 117.19 s |
| 外层monotonic / UTC-derived | 109.88929661700968 / 118.71753764152527 s；双时钟原值保留，不混为一个wall |
| 日志 | `benchmarks/artifacts/task39extra/v2_f5_closeout/checks_15.log`；SHA256 `5ad4ca130192568295f721b1730212302f6fdcbbcfeac0964126d6418b9566d1` |
| 完整命令及身份 | `benchmarks/artifacts/task39extra/v2_f5_closeout/test_record.json`；SHA256 `c0b7fbc682ccafb37801006c27411c40bf22d2673e7d57faaf1c03e2f0ae3243` |
| 预算 | V2原monotonic账本16项，累计8820.53636143892 s，余27179.46363856108 s；余额不授权新PDE |

最终静态核对JSON、相对链接、Markdown表格列数、关键artifact/hash及旧task/review/response不变；结果保存在`benchmarks/artifacts/task39extra/v2_f5_closeout/static_checks.json`。不宣称GitHub网页渲染通过。

## 历史 Review V1 / R6及此前测试


## Review v1 / R6 验证（当前）

| 对象 | 结果与源码边界 |
|---|---|
| R3接线、packed原作用、safe monitor | 104 passed、1 skipped；MPI2专用项未运行；日志 `benchmarks/artifacts/task39extra/r3_checks/checks_26.log`，正式source `cbf56e87e515ab0c3fc5756cb6cf52feb047f610` |
| LIGHT停止路由修复 | 23 passed、0 deselected，26.60 s pytest；日志 `benchmarks/artifacts/task39extra/r3_stop_lifecycle/checks_39.log`，SHA256 `35abeaa4014e4a14bff12233963997fde030426ddbd6ca22ae36c621263ac7ee`；代码 `597546311feea60d61acb2a9999b706dd895dcf0` |
| MPI1停止五路径 | 旧整树SIGTERM复现、只请求应用一次并安全退出、不合作到宽限整树硬停、资源立即硬停、陈旧start ticks拒绝；各fixture结束清场 |
| 监控数值不变 | 真实PETSc3.19零初值None及非零初值FGMRES轨迹逐位一致、64次PC不增调用；安全点保留当前cycle初值，不重复加解 |
| 停止fixture隔离 | `checks_32.log`的5 failed/15 passed/3 deselected保留；C层继承OMPI/PMIX环境导致子MPI过早失败，测试改为显式传递环境后通过；生产未清洗环境 |
| R3正式结果 | 原A6 last_safe576残差0.0791360407785889>1e-6；p4最大7.058163970105702e-11≤1e-10；资源安全、数值未资格化；normal checker not_run |
| 最终R6 task-focused | **153 passed、1 skipped**（MPI2专用）；源码HEAD `597546311feea60d61acb2a9999b706dd895dcf0`，仅文档dirty；pytest报告120.69 s，外层monotonic实测107.97184431797359 s，分别保留；ABI preflight与compileall通过 |
| R6日志 | `benchmarks/artifacts/task39extra/r6_closeout/checks_41.log`；SHA256 `8d258ba4c8e5f487cf84e50a9078d6ca9ed47e9f0f5aef66340d4e36a93bd522`；完整命令及预算绑定见[紧凑JSON](records/cost_and_contribution_v1.json) |

fixture宽限为3 s便于验证，生产LIGHT宽限仍为60 s。停止修复没有改变原A6/PC数学作用，没有重跑R3；小fixture通过不等于正式R3安全收口通过。此前局部失败、负运行与旧计数证据均保留。Ruff未安装，不安装或声称通过；不运行full repository，无CI通过声明。旧章节均作为历史快照解释。

最终回归覆盖test352/354/355/356/358/359/360/361/362/363/365/366，在同一shell资格化activation并先执行ABI preflight；显式MPI1小fixture是测试的一部分，未运行新的MPI2或原尺寸PDE。JSON解析、相对链接、四份audit及20份关键raw的hash、完整PC计数、残差阈值、历史task/review/response_v1不变和diff-check均独立核验；静态报告在 `benchmarks/artifacts/task39extra/r6_closeout/static_checks.json`，不声称网页可视渲染或CI通过。

## 历史 A5 与此前实现验证

最终交付的计数窄修提交为 `adc448814c3022fdf6d1a688da69a28238e7db9c`，正式 A2R 运行源码仍为 `54ab46cf4c8378a9b27650ca6963cadb34013a2f`。窄修只把 S6/S3 生命周期序号按实际调用计一次，并提供旧 raw 的独立只读重算；未修改方程、PC 作用或求解过程。

| 最终补充检查 | 结果 |
|---|---|
| public 登记遗漏修复 test359 | 3 passed / 0.07 s；真实两份 dat 的 plan/public dry-run/worker 路由可用，ordinary/未知 profile 仍不可用 |
| 计数独立重算及未来 ledger test360 | 3 passed / 0.07 s；跨两个周期、生命周期序号不中断、逐次计数字段保留、输入不改；缺失序号拒绝 |
| 最后相关轻量回归 test356 + test359 + test360 | 19 passed / 0.85 s；ABI preflight、compileall、diff-check 通过 |
| 正式 A2R 审计 | 5 周期 reported/explicit 对照通过；163 个原 A4 残差均 ≤1e-10；外层 160 步残差 0.18250767622880507 >1e-6，性能停止，不是 solver PASS |

最后回归使用同一 shell activation/ABI preflight 后执行 `python -m pytest -q src/test/test_356_physical_intermediate_wiring.py src/test/test_359_physical_reference_public_entry.py src/test/test_360_physical_cost_recount.py`。没有因计数或文档变更重跑已绑定 FE/正式 PDE，也未运行 full repository pytest；无 CI 通过声明。对应源码 hash、完整命令、28 份正式 raw hash 由 [运行索引](records/run_index.json) 绑定。

以下为此前实现阶段记录，保留原测试快照边界；原尺寸最终结果以上述正式性能停止记录为准。

| 验证对象 | 实际结果 | 证据与边界 |
|---|---|---|
| S6 精确对角 | 三个原 p6 单元与旧 dense oracle 相对误差约 2.2–2.6e-15；p3 serial/MPI2 约 2.3e-15；最终 callback 回归 17 passed | [既有组件记录](records/setup_diagonal_optimization.json)；曾发生的 MPI2 reference 布局测试错误及修复日志保留 |
| A2R focused_v1 | 15 passed；覆盖 tiny p4、旧 A2 FE、接线及 real p3 h50 oracle | 此前实现快照，不冒称最终源码重新运行 |
| A2R focused_v2 | 17 passed；reference/原 profile 接线、ledger、释放、负路径 | 此前实现快照 |
| 最终 focused_v3 | 38 passed：test358、test352、test355 | 同 RHS repeat 相对差 0.0 ≤1e-12；增广/native action 1.8225937969296386e-15；原 A4 残差每次 ≤1e-10；错误 action 拒绝 |
| 最终组件资源 | RSS peak 640000000 B，swap 0，清场通过 | watchdog 原始 elapsed 61.57664551300695 s；pytest 原始 67.21 s，分别保留 |
| 静态检查 | compileall、git diff --check 通过 | 未运行 full repository pytest；不声称 CI 通过 |

A2R 代码提交为 `920cf08eedf99610e5eee90ec1fe8ce317e14591`。测试运行时为基于 `2bed3d4248a465a9cf2224c575fc8b64357fd020` 的 development worktree；经逐文件核验，最终 14 文件内容集合 hash 为 `2f61cf5c65a18dfcb71e700ac3a21ca1280e76d2516687627ccd7f05a44b5177`，与代码提交内容一致。较早回归没有因无关文档变更重跑。

全部 Python 测试先在同一 WSL shell 中 `source scripts/activate_myfenics_wsl.sh`，ABI preflight 确认 marker=1、链接的仓库 venv、PETSc complex128/int32、Linux OpenMPI、同 Linux ABI 库、线程数 1。实际命令：

```bash
python -m benchmarks.subreaper_watchdog --directory benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/focused_v3 --wall-seconds 180 -- python -m pytest -q -s src/test/test_358_physical_p4_reference.py src/test/test_352_task039_extra_physical_multilevel.py src/test/test_355_bounded_p1_factor.py
```

180 秒仅为该组件测试预算，正式 workflow/solve 仍为 7200/3600 秒。完整命令、源码 hash 和 9 份 raw 测试文件 hash 见 [implementation_manifest](../../../benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/implementation_manifest.json) 与 [实现报告](../../../benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/implementation_report.md)。这些小型测试当时不构成原尺寸 A2R 或主候选资格；后续正式结果见本文件开头及总账。
