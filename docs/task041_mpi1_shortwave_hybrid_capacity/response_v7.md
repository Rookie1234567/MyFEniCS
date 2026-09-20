# Task041 Response V7：D2a 2nm D1e 运行进展与 producer packet 边界

## 先给结论

本例是钨（W）、2nm、p6/h1.5、M1200、MPI8×1。Schur 在这里是供外层迭代使用的模态耦合预条件矩阵；当前重复样本计划是在两侧各取 8 列、每列算两遍，共 32 次，用来观察可重复性，而不是 32 路并行。当前只看到 21/32 个样本，正式 Schur 响应仍为 0/4800。

这场 D1e 运行仍在进行：producer 的 QEP 已完整写入磁盘，consumer 已进入候选 modal/Schur 阶段，但还没有完成全场求解，因此没有 RTA，也不能称为数值通过或容量通过。`systemd Result=success` 只表示当前服务没有被 systemd 判为失败，不等于 solver PASS。

本报告冻结于 2026-09-20 01:17–01:25 UTC（09:17–09:25 CST）的现场窗口；具体 host snapshot 取 01:19:51.480911341Z。后续增长中的日志不被追成新的“最终峰值”。小 RHS 文件和 memory 原始 tail 行均保留自己的 as-of/hash 绑定。

通俗地说，当前慢的主要原因不是 QEP 没有完成，而是 consumer 正在对两侧大量 modal correction 逐批建立/使用 Schur 作用：每条小 RHS 都包含求解、传递、A6/H6 与其它诊断的嵌套成本；`batch_size=32` 是分批处理以限制常驻内存，不是 32 个独立求解同时并行。固定样本显示，继续完成约 2400 个模态项/侧会产生很长的工作量，但这个外推不是可靠 ETA。

## 身份与冻结窗口

| 项目 | 现场值 |
|---|---|
| canonical source | `/home/fenics/Projects/MyFEniCS`，branch `codex/20260902-task41-mpi1-shortwave-hybrid-capacity` |
| 运行 source SHA | `bde0686891af10bb489e4b1cb14500791cb50351` |
| 报告 worktree | `/tmp/task041-d2a-doc-review-20260920`，detached at running source；报告文件不是运行 source |
| unit / invocation | `task041-d1e-2nm-p6h1p5-m1200-mpi8.service` / `1cf5e34338754dbfa80df487b322c72c` |
| MainPID / starttime | `571560` / `183510226` ticks（local start `Fri Sep 18 17:55:45 2026`） |
| service state | `active/running`；worker group 未消失；finalizer 尚未运行 |
| service cgroup | `/user.slice/user-1000.slice/user@1000.service/app.slice/task041-d1e-2nm-p6h1p5-m1200-mpi8.service` |
| CPU / 数学线程 | parent/ranks 绑定 CPU1–8；每 rank 数学线程控制为 1 |
| public runroot | [`20260918T095546.139183Z`](../../results/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8/task041_2nm_p6h1p5_m1200_mpi8_balh__hybrid_iterative__mpi8__M1200/20260918T095546.139183Z/) |
| D2a record | [`task041_d2a_progress_20260920.json`](outcomes/records/task041_d2a_progress_20260920.json) |
| D1e evidence index | [`d1e_evidence_index.json`](../../results/task041_side_balh_component_audit/d1e_preparation_20260918_8ad30732/d1e_evidence_index.json) |
| 独立 compute ledger | [`task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8_compute_wall_ledger.json`](../../results/task041_side_balh_component_audit/d1c_preparation_20260917_8d47747d/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8_compute_wall_ledger.json)，沿用原记录，D2a 未写入 |

受保护的邻近 Full3D 不是 Task41 运行：当前现场 PID 为 parent `402109`（CPU9）、mpiexec `402153`（CPU23）、worker `402163`（CPU23），guard `1549434`（CPU9），均只读核验，未发送 signal、未改 affinity。

## 历史边界与本次状态

- 5nm BAL_H 曾有约 `191662.819902868 s`（约 53.24 h）的 candidate/数值证据，但 public supervisor/resource 证据不完整，不能当完整容量资格。
- C2 common-layout 的 8 对/16 response 同布局诊断耗时由 `1981.6339287383016 s` 降至 `1454.4546840919647 s`，约 26.6033%；这是组件诊断边界，不是完整 consumer 的冷启动或 RTA 提速。
- D1c（source `54252cc9`）的首次正式入口在 `outer_mpi_identity` 失败：新注册 2nm 没有旧 V2 高层 profile，却落入旧外层 MPI 分支；这不是数值或容量失败。入口修复后的 `0ede1df5` 使 D1d 进入计算，但 top 侧又触发 affine geometry 误判；`8ad30732` 修复了平移浮点抵消问题，之后 D1e 绑定文档/运行 source `bde06868`。因此不能把 D1d 简化为只有入口失败。
- 本次 D1e 是实际运行，不是 `not_run`：producer/QEP 已完成并释放 producer scope，consumer 仍在运行；full consumer、outer solver、RTA 尚未完成。

## 阶段与成本：probe、modal、outer 分开

| 阶段 | 事实 | 口径 |
|---|---:|---|
| producer QEP | max-rank total `29500.000315021956 s`；mode-prep wall `29501.598348574014 s` | QEP 已写盘；每方向请求/候选/选取 `1200/2400/1200`；正式 consumer QEP calls `0` |
| fixed cost probes | 8 条（bottom 4、top 4），7 条非零、1 条精确零 | 候选 setup 诊断，不是 formal 4800 response |
| 小 RHS raw audit | 29 行（bottom17、top12） | 其中 `phase=modal_schur` 的 21 行才用于下表；其余 8 行是 cost probe |
| controller snapshot | bottom13、top8，共 21/32 个 modal 样本 | 与 raw audit 的 21 modal 行交叉核对；raw 文件另含 8 条 probe，不把样本写成 formal 进度 |
| formal Schur responses | `0/4800` | 两侧正式 modal/Schur 响应，尚未开始完整 formal consumer |
| outer FGMRES | `not_started`；outer response `0`，分母不适用 | 不把 service outer wall 或 parent wall写成 outer solver 成本 |
| RTA / full result | `not_run` | 当前没有全场解、R/T/A 或 official qualification |

### 21 个 modal 样本的程序化聚合

下表从小 RHS JSONL 中只读取 `phase=modal_schur` 行，按 `side` 聚合；`Q/A6/H6` 是每条 rank0 audit 的 `per_rank_accumulated_seconds` 累计，不能与 elapsed 或其它 MAX 值相加成 critical path。范围是样本范围，不是全 2400 项的界限。

| side | modal count | iteration sum / range | elapsed sum s | elapsed mean s | elapsed range s | rank0 Q sum s | rank0 A6 sum s | rank0 H6 sum s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bottom | 13 | 273 / 9–51 | 27977.90938461572 | 2152.1468757396706 | 899.4712390978821–5227.512858337024 | 15991.318321351893 | 8700.545055122348 | 2183.074874829501 |
| top | 8 | 197 / 11–56 | 21253.56579890987 | 2656.6957248637336 | 1155.1779964989983–6149.74191578012 | 12403.696700270288 | 6339.517980669392 | 1763.2767441337928 |

21 条 modal audit 全部 `reason=2`、`explicit_true_target_reached=true`；由原始 `relative_residual` 重算的最大值为 `0.009981656767193032 <= 0.01`。这是小 RHS/modal audit 的逐项数值检查，不是最终全局残差，也不是 full consumer qualification。

因此固定样本算术为：

`(27977.90938461572 / 13 + 21253.56579890987 / 8) × 2400 = 11541222.24144817 s = 133.57896112787233 days`。

这只是把当前两侧均值各外推到 2400 个项的 derived arithmetic；它忽略 setup、outer、恢复、采样偏差、收敛变化和正式全 consumer 生命周期，不能称 ETA。旧 8-probe 的 derived central `9950673.628227763 s`（约 115.17 天）另列，不与 21-sample 结果混用，也不是可靠 ETA。

8 条 probe 的小表如下，供审阅 rank0 audit 的局部口径；Q/A6/H6 保持 nested/component 语义，不相加成 wall：

| side | elapsed s | iters | residual | Q s | A6 s | H6 s |
|---|---:|---:|---:|---:|---:|---:|
| bottom | 943.028173829 | 9 | 0.00965979807368 | 545.914052459 | 295.374230720 | 72.477915005 |
| bottom | 935.795627322 | 9 | 0.00965979811362 | 536.572679305 | 297.847867928 | 73.060816418 |
| bottom | 0.915819157 | 0 | exact zero | 0 | 0 | 0 |
| bottom | 2180.014534508 | 21 | 0.00872422106858 | 1227.557367700 | 715.272891908 | 166.791020448 |
| top | 1589.774584774 | 15 | 0.00745800541757 | 888.949216752 | 538.730288464 | 113.669830531 |
| top | 1515.847482107 | 15 | 0.00745800755093 | 876.843435479 | 484.756308253 | 108.491403824 |
| top | 5805.580264907 | 54 | 0.00966101564438 | 3406.692656219 | 1819.133883619 | 413.681531516 |
| top | 2151.638432964 | 20 | 0.00990569530614 | 1240.686867773 | 691.997740352 | 153.226757497 |

## QEP 与 producer packet：已落盘，但还不是公共 consumer-only 重启资格

producer packet 的文件身份已一次性流式核验，未加载 FE 数组：manifest 声明 8 ranks、32 个 shard entries；实际 packet 33 个文件、`4842723531 B`，其中声明 shard 合计 `4841245696 B`。32 个声明文件的缺失、字节和 SHA mismatch 均为 0。

| 对象 | SHA256 / 数值 |
|---|---|
| selected mode manifest | `7ef2ecc5587f79a123e44cacfe347356d13b36336948ade1672787c6430163d2` |
| manifest bytes / shards | `1477835 B` / `32` |
| selected-mode manifest artifact | `4bb930587c4b1fbe37d3061520beb7281030c5d28e28974a17529d68b2672b86` |
| packet identity | `171ef1ca91ce72d3ca2a7ca61d7ab2f5be4759934656e7730afd757d3ab49d17` |
| mode prep summary | `5810f19d2834c122e16c178ad1346c10e8288aa3ade565bf26ea73006c252be2` |
| producer summary | `138db58ad98f0f32910a31788dd510852aee5d63a4f7a81c1446c46d353bcb26` |
| input / physical / resolved | `0edd17344454939cb2cd439b5221f6d08f03c42b9f36b083469e63f667e75e57` / `537056f184c8be19a4688c7e4cc1fef883141b9dbab7380c1df2efc5a3b465fc` / `10835c84bc3c6f6fdbb5630a48a84a538fa87bd621346f068942cb5cdcc9f6b4` |

`mode_prep_summary` 的分类为 `TASK041_MODE_PREP_PACKET_READY`，`producer_scope_released=true`；保存的是 selected mode packet，不是全部 QEP 中间 workspace（`qep_workspace_persisted=false`）。QEP 已保存这一事实与“公共 consumer-only 可无条件重启”是两件事。公共入口实际参数是 `--producer-packet-root`。现有 `validate_balh_producer_packet(..., require_public_supervisor_summary=True)` 还要求 producer root 的 public `supervisor_summary.json`，而该文件在当前 parent 尚存活的窗口内不存在。因此当前状态是 `not_qualified_missing_public_supervisor_summary`，不能伪造 summary、source 或把任意强杀当成可复用终态。

producer 与 consumer 的源码身份可以分别记录；当前运行两者绑定的运行 source 是 `bde068...`，但未来复用并不要求两者 SHA 文本相同，必须分别通过 source、物理/布局、输入和 ABI identity binding。

已核对的代码路径只释放内存所有权：selected packet 的 `destroy()` 清理 owned vectors，consume 路径释放内存引用；没有看到删除磁盘 producer packet 的 `unlink/rmtree`。但这不表示 factor/native workspace 可接续：当前内存中的因子、KSP、workspace 不在 QEP packet 中，受控结束后只能依赖完整生命周期与公共 summary 重新验证，不能把现有内存状态当成可恢复 checkpoint。

以后若需要受控结束并保留复用资格，最小前置条件是：让既有 supervisor/finalizer 完成 public `supervisor_summary` 和 resource/lifecycle 证据；保留 runroot；核对 source/input/physical/resolved/model/MPI identity、manifest 和 32 shard hashes；确认自有 process group 清理；再用原 `scripts/run_case.py <dat> --producer-packet-root <producer_root>` 和 validator。此处只给步骤，不执行，不承诺任意中断都满足这些条件。

## 内存、资源与时间边界

| 口径 | as-of 值 |
|---|---:|
| process-tree RSS | `642483105792 B`（12 PID，latest bracket） |
| dedicated cgroup current | `647585968128 B` |
| dedicated cgroup kernel peak | `647695921152 B` |
| global swap | `8192 B` 既有基线；新增 delta `0`，pswpin/pswpout delta `0` |
| job/cgroup swap | `0` |
| host MemAvailable | `1018492968960 B` at bound sample |
| runtime reserve contract | `412316860416 B` |
| warning / hard RSS contract | `1539316278886 / 1759218604442 B` |
| PSS / USS | 当前该 authority 行为 `null`，不冒称测得 |

这里的 `sample_elapsed_seconds=142181.0448487869` 是 memory sampler 自己的 elapsed 字段，不是 01:19 报告瞬间。对应原始 `memory_stages.jsonl` 单行（byte offset `1257553500`、3535 bytes）SHA256 为 `7e96bb667fbff3e391540a3f066a65e412c436cad6f8c3daad33fe72d690e619`；绑定字段为 process-tree RSS、cgroup current/peak、swap、global swap、MemAvailable 和 phase。此为 marker 前后括号/单行绑定，不是整段内存日志的最终 hash，也不是完整运行峰值。

小 RHS 原始文件 [`balh_side_rhs_audits.jsonl`](../../results/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8/task041_2nm_p6h1p5_m1200_mpi8_balh__hybrid_iterative__mpi8__M1200/20260918T095546.139183Z/consumer/numerical_output/balh_side_rhs_audits.jsonl) 在冻结窗口为 63,009 bytes、29 行，SHA256 `6ad01110ab9335f953c1064903e846fa3298d6ca7090a1f5341998dd13b2179c`；21 个 modal 行的聚合来自该文件，增长日志不被冒充为最终 hash。

## 未验证的备选算法

近似 p4 Schur 只作为风险候选，不切换、不开发：约 1.7 天只是“4800 个 Q 修正”的算术假设，不含 setup、outer、recovery，也没有收敛/物理等价证据，不能称确定收益。M、complex 精度、物理定义和原检查均不因时间压力改变。需要主控/ChatGPT 审阅的是可接受总耗时与替代路线，不是现在启动新算法。

## 当前决策状态

`D1e_RUNNING_PRODUCER_PACKET_SAVED_CONSUMER_IN_PROGRESS`。当前没有 full consumer、outer FGMRES、RTA、official qualification；也没有在 D2a 发送 signal、启动测试/PDE/QEP 或启动近似 Schur。本报告经主控审核后仅推送文档/轻量证据到原远程分支，canonical 运行 HEAD 保持不变；本阶段无新算法执行。
