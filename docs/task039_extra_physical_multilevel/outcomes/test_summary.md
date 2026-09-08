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
