# Review V31 执行回应：q4 完整数值矩阵已保存，独立 native 尚未完成

本轮取得了一个可直接续作的实际成果：**q4 自己的完整数值 CSR 已构建、封存并由主控重新读取三数组核对 hash**。CSR 是把稀疏矩阵的数值、列号和行起点分开保存的格式，后续无需再积分或重做此次 pattern/fill。状态是 `NUMERIC_COMPLETE_NATIVE_PENDING`：数值已填完，但尚未由独立原生 FE 路径验证，不能用于宣称新 q 资格、准确因子或原尺寸目标场通过。

随后建立 twist0 的原生恢复/验证对象时，固定数值截止到达。watchdog 正常终止并清场；没有内存不足、OOM 或数值不收敛的证据。旧 q0 的 V28 CSR/native 和 V29 分解资格不变，V29 因子已销毁。

## 真实交付

| 项目 | 实际结果 | 边界 |
|---|---|---|
| q4 shape / 结构位置 | 777424 × 777424 / 581086528 | q4 自己的映射与结构，没有复制 q0 |
| 非零 / 精确零槽 | 566185131 / 14901397 | 不做阈值压缩，全部槽保留 |
| CSR 数组载荷 | 11624840260 B | 三个 NPY 文件含头合计 11624840644 B；不是进程峰值 |
| 持久化支撑 routes | 1326141440 B SQLite | 已保存，不等于未来 native owner |
| q4 独立 native | 未完成 | 不把 saved replay 或文件 hash 当 native 数值 PASS |
| 新 q1/q5、q2/q6、q3/q7 | NOT_RUN | 新增合格 q 为 0；历史 q0 仍有效 |
| 全八 q live bank / 完整参考 / target pilot | NOT_RUN | 无新 factor、业务 PC、A6 或 R/T/A 成果 |

### 时间与内存（父子时间不可相加）

| 口径 | 实测秒 / 字节 | 解释 |
|---|---:|---|
| q4 保存阶段完整父段 | 17281.822695894 s | 约 4.80 h，含保存身份读取、构建、填充和封存 |
| pattern 子段 | 6066.371507694945 s | 已在上面父段内 |
| numeric fill 子段 | 7262.07835266809 s | 已在上面父段内；其余差额不猜测归因 |
| fill 内贡献生成 / 投影 / 累加 | 2631.449041903019 / 2111.333873125026 / 141.27612544083968 s | 子计时，不代表整个 setup，也不与父段重复收费 |
| watchdog 运行父段 | 33786.45508461888 s | 约 9.39 h，包含 q4 和未完成的 twist0 owner 准备及清场 |
| run_case 父段 | 33786.969049097 s | 包围同次工作，不再与上一项相加 |
| 进程树同时 RSS 峰值 | 16563810304 B | 身份覆盖 complete |
| watchdog 专用 cgroup 峰值 | 24329441280 B | 含文件页等，不能与 RSS 相减归因 |
| systemd MemoryPeak | 24325746688 B | 不同采样口径，原值保留 |
| task tree/cgroup swap | 0 / 0 B | 宿主 pswpin/pswpout 增量均为 0；宿主原存量未删 |
| PSS | null | DISABLED_BY_PROFILE |
| 主控三数组完整 hash 回读 | 26.34986114501953 s | 只读收口费用；无 FE/native/CSR matvec |

完整服务相邻父区间之和、原始时钟和精确工件身份见[主控审计](outcomes/records/review_v31_controller_closeout_audit.json)。数值结束时保守累计 42032.2399471737 s；包含截止后的实际清场费用，**不是**最终文档/推送完成时间。后续收尾费用另列，未取得精确分项的历史准备费用保留 UNKNOWN，不清零。工程连续窗口与必要冷算法流程不同；本窗复用保存贡献，不能据此声称完整冷流程已计齐。

## 固定窗口、停止与 checker

用户已在本会话批准 V31 窗口及指定工作站目录。实际 T0 为 `2026-10-13T09:28:54.340648489Z`，数值截止 `21:08:54.340648489Z`，总截止 `21:28:54.340648489Z`；SHA256 `57133ebfe54c109ca77af4e529df94708c29c2b4c79d301b862b01ee70cf8f56`，未刷新。cap 保持 1649267441664 B、host reserve 68719476736 B；没有使用“适当放宽”的模糊授权自动抬限。

正式 attempt6 是 `20261013T114619.891762Z`，科学源码 `54cf6d367b07355c0ab08c8c10655ecac73cfc6a`。q4 完成后开始 `task40_v31_twist0_owner_prebuild`，未留下完成事件；最后持久化 gate 标签不是完整阶段完成证据。watchdog 在数值截止发 SIGTERM，30 s 宽限后 SIGKILL，`remaining_child_pids=[]`。原分类 `PERFORMANCE_CONTROLLED_STOP` 原样保留，不改成数学 FAIL。

自动 required checker 因 `V30 partial checker paths are not bound to current run evidence` 未启动，原 `partial_checker_result` 缺失。收口窄修只允许同 run/source/window、真实 enforced cutoff、退出码和任务清场/零 swap 证据绑定的缺输出情况进入**只读** checker；不造 footer，不授予科学 PASS。该修复源码 `c9c7f4af19917cbd2c0e4ecd5c0b167cab6752f5`，与运行科学源码分列。补检终态以追加的只读收据为准；原失败不覆盖。

之前五次 service/入口失败及费用保留：服务命名、selector、profile 导入、ABI/合同传递，以及缺失 V26 收据依次修复。28,800 B 的旧收据经用户明确批准原样传到指定目录并 hash 核验；没有重跑 q0 producer/native。

## 直接交接与下一步

保存位置为 `fenics-ws:/home/fenics/Projects/laptop_share/benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_native/source_54cf6d367b07355c0ab08c8c10655ecac73cfc6a/factor_bank/selected_q/q4_twist0/`。

- `task40_v30_q4_twist0_numeric_pending.json`：SHA256 `1938828321a57ee6eaaea0def485f73daddbd13432cc6ef8823d19bcc44640ad`。
- 完整 data/indices/indptr 精确路径、bytes/hash、旧 producer 身份均在[主控审计](outcomes/records/review_v31_controller_closeout_audit.json)中；主控回读全部匹配。
- 下一授权窗口应导入这个 pending，**跳过 pattern/fill**，继续必要 twist0 原生 owner 和缺失 q4 独立见证。尚未获得可分解资格，不绕过 native 门。
- q4 合格后依次推进另外三个 twist 的成对 q，全部资格闭合才进入 ALL_Q_RESIDENT；保持同一 live bank 做参考逆与条件 target，不先全部销毁再重建。
- 需要先利用本轮阶段边界定位 twist0 owner 准备的实际工作；其未完成费用不能简单归给 numeric 或 CSR 累加。没有新窗口则不自动重启。

原尺寸 pilot 的网格/mode 精度、全八 q 因子共驻、完整原生参考逆、原尺寸场与全部冷流程尚未闭合。**十进制 2 TB / 48 h 与最终精度仍未资格化**。未修改 master、普通默认或其他工作站项目。

## 验证和历史

P0 最小相关回归 67 passed in 4.43 s；之后各入口 bug 按受影响 fixture 定向复测。最新 cutoff 绑定 fixture 为 1 passed in 0.23 s，complex128/int32/MPI1 资格化环境；它只证明接线，不是数值资格。没有声称全仓测试、MPI2/4、CI 或 target PDE 通过。以下保留最初 P0 回应，里面的 PENDING/NOT_RUN 是当时快照，当前状态以上文为准。

---

## 历史 P0 原回应

# Review V31 P0 执行回应：入口就绪，数值窗口仍待批准

本轮没有新增 q 的矩阵、因子、完整参考或目标场。旧 q0 资格按原 source/window 保留；V31 的新 q 数值覆盖仍为 **0/8，NOT_RUN**，完整参考、目标 PDE、R/T/A 与 2 TB/48 h 仍未资格化。完成的是重型窗口前的 P0：把失败后重试固定 T0、生成批准合同和执行命令的路径接通并用临时 fixture 验证，随后完成定向回归。新重型窗口仍为 **PENDING**。

## P0 结果

| 项目 | 状态与解释 |
|---|---|
| 重试时间锚 | 两次模拟准备失败后，第三次成功准备沿用第一次写下的三时钟 T0、campaign window 字节和 SHA；没有重新调用 T0 时钟采样。fixture 使用临时目录及伪造批准收据，不代表真实用户授权，也没有留下可启动的真实窗口。 |
| 获批包 | 真实 `prepare_v31_pending_package` 从 canonical DAT 和小型 q0 selector fixture 生成 pending 路由；真实 `prepare_v31_approved_package` 生成 approved contract、selector、registration 与命令。随后真实 `require_v31_execution_contract`、`v31_launcher_values` 和 campaign 校验器接受产物。该 fixture 仅证明准备入口与身份合同，不重复资格化 q0 数值。 |
| q4 保存优先 | worker 先从已保存 q4 contribution 构建并持久化自己的数值 CSR pending，再进入完整 reference builder；native 失败时不把 pending 冒充 COMPLETE/PASS。 |
| 恢复与跨窗导入 | numeric-pending 重开不重复 pattern/fill；COMPLETE consumer 按原始身份导入；跨窗消费要求明确 source/window/producer 收据。旧 q0 PASS 不重写。 |
| owner 与真实 callback | twist0 owner 交给 reference callback 后由统一 cleanup 释放；销毁失败会使 worker/checker 结果失效。q1/q5 callback 使用实际 twist1 builder 输入，覆盖非 q4 执行顺序。 |
| 分阶段准入 | reference-only、target build、target ready 分开检查；target 未构建时 actual 保持 null，planned 值不代替实测资源或身份。 |
| closeout 与费用分类 | 窄修 service、watchdog 启动/采样和 checker 的 cutoff/closeout 合同；strict 与 V15 reference 层分别记录，AllQ RHS MatSolve 按类别、q 和嵌套阶段计数。 |
| 执行链 | V31 launcher/service 参数、同窗 campaign window 路由、partial checker 与 official checker 命令由代码生成并在成功 fixture 中核对。没有运行正式 q factor、FE、JIT、PDE、完整大数组扫描、pattern/fill/native。五文件单测包含小型精确 MUMPS API fixture；它不是 Task40 数值资格。 |
| 新数值结果 | 未运行。q4、q1–q7 的新矩阵与 native 资格、八 q live factor bank、完整参考逆和条件原尺寸 pilot 均为 NOT_RUN。 |
| 固定窗口 | 旧 V30 T0/cutoff/deadline 原样保留且已结束。V31 T0、cutoff、deadline、window JSON 和真实批准收据都不存在；不得从测试 fixture 推断为已批准。 |

## 验证

Task40 资格化本地环境的轻量 ABI preflight 通过：`_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`，解释器与 PETSc/SLEPc、DOLFINx、Basix、mpi4py 均来自本仓库配置的 Linux runtime；PETSc scalar 为 `complex128`、integer 为 `int32`。

最终定向回归覆盖五个修改相关测试文件：

```bash
python -m pytest -q \
  src/test/test_task40_v10_p6_mumps.py \
  src/test/test_task40_v30_qualified_q_csr.py \
  src/test/test_task40_v30_selected_q_csr.py \
  src/test/test_task40_v31_admission.py \
  src/test/test_task40_v31_closeout.py
```

结果为 **67 passed in 4.43 s**。原始日志位于 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_preparation/test_final_targeted_20261013.log`，SHA-256 为 `a70135c082be352369ff51d0f9df41e7626d602527e52ef89290428a173af5f6`。新增失败重入及成功准备路径的小 fixture 单独为 2 passed；五文件回归已包含这两个测试。

第一次五文件回归发现一个旧 fixture 未提供新的 `q` 分类索引，第二次发现其 audit fixture 缺少按 q 计数的三个小映射；均为测试夹具接线问题，已修正后以最终五文件回归通过。第二次失败原始日志保留在 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v31_preparation/test_final_targeted_after_fixture_fix_20261013.log`。第一次失败发生在复用同名日志路径之前，原始日志文件随后被最终通过日志覆盖；主控从执行记录另存了 `controller_recovered_failure_transcripts.json`，其中逐项标明这是 `recovered_from_tool_transcript` 的回执副本，并非原始日志字节，不声称原始 SHA-256。

本次不是全仓 pytest、MPI2/4、Ruff、CI 或数值资格运行；没有据此声称 CI、PDE 或最终精度通过。

## 源码与成本身份

生成测试和本回应记录时，分支为 `task40extra_0p7nm_engineering`，工作树含未提交 P0 修改，`HEAD=d7ffbfea952bc160742b18739369f2e3f656ee8e` 是 Review V31 基线，不是冻结源码。每个修改源码/测试文件的 SHA-256、测试原始日志、ABI 收据和工作包时钟观察列在 [V31 P0 evidence index](outcomes/records/review_v31_p0_evidence_index.json)。主控将集中审核、冻结、提交推送并回读最终 SHA；该 SHA 应与 compact 中绑定的文件内容对应。

工程成本以连续 P0 锚点和观测值保留，包含会话间空闲时间，不能解释为纯编码工时。新数值窗口的 T0 仍为 null；P0 花费不会从后续完整冷流程账中删除。

下一步由主控先审核/冻结当前源码，再集中提交与推送；只有之后用户明确批准新的 12 小时固定窗口，才能在真实审批收据验证后第一次采样 T0 并进入批准流程。旧 V30 窗口、失败与 `NO_PARTIAL_FOOTER` 证据均不改写。可执行交接见 [handoff V31](outcomes/handoff_v31.md)；项目汇总与 run index 仅追加本轮 P0 状态。
