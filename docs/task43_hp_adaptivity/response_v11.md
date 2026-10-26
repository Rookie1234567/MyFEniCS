# Response V11：P1 有限工程证据，P2 在空间审计中受控停止

V11 没有得到新的科学结论。这里的最终空间 authority 是对实建有限元空间独立未知量总数，以及挂接和周期约束计数的权威审计；该审计没有返回。唯一的 P2 支持运行在 840 秒工作阈值后被 watchdog 按计划发送 SIGTERM，也没有进入 PDE 装配、因子分解或求解。历史 accepted9/R9、R10 拒绝以及五项科学能力状态均保持不变。没有新增正式 dispatch，也没有合并许可。

## 阶段结果和额度

| 阶段 | 实际结果 | 判定边界 |
|---|---|---|
| P0 | 实现、合同和定向测试冻结在本轮源快照 | 静态复核后来发现必要闭包限制错误；源码按停止要求保留，未在消耗 P2 槽后静默修补 |
| P1 首次支持运行 | `7 passed, 1 failed in 3.55s`；whole-watchdog `5.6703435350209475 s` | 单个 sentinel 测试桩没有接收 `_audit_plan(cfg, ...)` 的位置参数，属 fixture 签名错误；这次没有构网或进入 PDE。原失败保留 |
| P1 窄恢复 | 只重跑失败 selector，`1 passed in 3.34s`；whole-watchdog `5.841137452982366 s` | 主控确认签名修复后执行一次。其余七个未变 selector 没有在修复后的测试文件字节下重跑；故不称完整最终字节测试套件通过 |
| P2 空间与保存场前门 | `PERFORMANCE_CONTROLLED_STOP`，唯一尝试已用 | 最后停在 `_audit_plan` / `task43_v11_p2_mesh_authority_begin`；最终空间 authority 未返回。此支持运行不是正式 PDE dispatch |
| P3 A1_q3、P4 R9_H8 求解、P5 联合比较 | `NOT_RUN` | P2 前门未完成，主控关闭所有动态工作；未启动重试 |

P1 两次 whole-watchdog 时间合计 `11.511480988003314 s`，P2 为 `842.2889896910638 s`，支持运行总计 `853.8004706790671 s`。历史正式额度仍为 5/6（A1 2/2、A2 3/3），原末槽继续封存。V11 新增授权的 A1_q3 与 R9_H8 两个正式槽均未消耗，因此扩展包络为 5/8；但这不表示可以继续启动。P1 支持额度 2/2、P2 唯一支持额度 1/1 均已消耗；新增正式 dispatch 为 0。

源码身份分阶段绑定：任务书/分支起点 `70e2cfdcc3e5a7c3be5e8b714076420e3eac1129`；P0 与 P1 首次运行 `c976dda2076ea7ce802c279bb56b3189fa10dced`；P1 窄恢复 `cfe1adae3805c432b0a58349853a70ac47ceed2a`；P2 实际运行 `2d01bfae15a3831683a859673e69f0c992186b85`。P0 冻结静态检查和输入身份清单分别实测3.7900969316251576秒与5.7772636017762125秒；完整手工读审/编辑墙钟没有聚合测量，不能把支持运行总时长当作总人工wall。

## P2 实测终态与尚未取得的数据

| 字段 | 实际值 | 解释 |
|---|---:|---|
| 工作停止阈值 | 840 s | watchdog 的停止阈值 |
| 最后一个仍运行的采样 | 840.6002323981375 s | 取样间隔意味着这不是“恰好 840 秒”停止 |
| whole-watchdog wall | 842.2889896910638 s | 包含停止和回收；全程上限 900 s |
| 终态 / exit | `PERFORMANCE_CONTROLLED_STOP`；worker `-15`，watchdog `2`，launcher `2` | watchdog 对整个子进程树发送 SIGTERM；不归类为自发数值失败 |
| 采样进程树 RSS 峰 | 1,156,853,760 B | 专用 subreaper 加全部后代的同时采样 RSS；不是连续高水位，8 GiB launch cap 未触发 |
| 进程树 swap 峰 / WSL 全局 swap 页差 | 0 B / pswpin 0、pswpout 0 页 | 进程树采样 VmSwap 为零，WSL 全局页计数未增加 |
| 资源采样 | 1,148 行；最低有效可用内存 1,419,287,298,048 B；reserve 324,465,057,792 B | 全部可读，live affinity violation 为 0；PSS 按 profile 禁用 |
| 进程回收 | 完整；剩余 child PIDs 为空 | watchdog、worker、tracer 与观察到的 MPI helper 在退出后均未以同一 PID/start-ticks 存活 |
| trace | 795 条原始行，未知行 0，无成功 affinity setter | 终止时 worker 栈含 Basix `compute_interpolation_operator`；这是一个终止栈快照，不是全程 profile，不能据此把全部耗时归因于 Basix |
| 输入和源码身份 | 50 个 source、38 个 input 检查；前后 hash mismatch 为 0 | P2 源快照 HEAD `2d01bfae15a3831683a859673e69f0c992186b85` |

P2 保存了候选 `v11_r9_h8` 的计划文件，SHA256 为 `0f5885976b000a24e2f21b5aa5f4d0ea97fdd142cac9208e25d4c6e615d1ac23`。它记录的只是 plan-generation `expected_forest`：180 个根单元、194 个叶单元、user closure 1、material closure 1、balance closure 0、periodic closure 0，以及 9 个 hanging patches。它不等于最终网格与约束 authority，也不是实测 FE 数。

| 科学字段 | 结果 |
|---|---|
| 最终 mesh / constraint authority 与实际闭包 | `NOT_RETURNED` / `NOT_MEASURED` |
| 独立 trace、interior、FE、condensed rows、NNZ、factorization | `NOT_MEASURED` / `NOT_REACHED` |
| A6、condensed 与 normal 原向量、完整残差 | `NOT_REACHED` |
| 旧 A2 saved-primary 数值复核 | `NOT_REACHED` |
| A1_q3 完整 q 响应；R9_H8 求解与 endpoint | `NOT_RUN` |
| 公共 q8/q10 三场比较、R/T/A、A_volume、完整 612 模式 | `NOT_RUN` / `NOT_MEASURED` |
| h 的精度收益、每新增 DoF 收益与同精度全过程成本 | `NOT_ESTABLISHED` |

因此，plan 文件证明输入 seed 和计划 forest 已落盘；它没有证明完整空间 audit 通过，更没有给出 h 数值结果。由于没有传入 `--cache-path`，`cache_metadata_stable=true` 的空 metadata stamp 不构成共享 JIT/global cache 审计。P0四项已测静态动作分别为3.7900969316251576秒（冻结检查）、5.7772636017762125秒（输入清单）、0.044360832311213017秒（R9谱系补读）及0.0016497471369802952秒（恢复输入补读）；它们不覆盖全部手工读审和编辑，后两者总wall及editor wall仍为 `NOT_MEASURED`。支持运行的853.8004706790671秒不是总人工wall。

## 保留的实现和审查缺陷

静态审查发现 [round1_candidates.py](../../benchmarks/task43_hp_adaptivity/round1_candidates.py#L1688) 的 V11 gate 错误要求 `forced_closure_root_ids` 为空，和任务书要求保留、记录必要闭包相冲突。保存的 expected forest 显示 material closure 为 1；P2 在 `_audit_plan` 中被停止，未执行到该 gate，所以此缺陷不是本次 `PERFORMANCE_CONTROLLED_STOP` 的原因，也不是 h 科学负结果。缺陷来自实现遗漏，P0/P1 静态预审没有识别它。

P1 也有一项明确覆盖缺口：`test_fixed_seed8_plan_rejects_nonroot_and_alternate_seed` 将 `_build_next_round_plan` stub 成最小 provenance，真实 main sentinel 又在 `_audit_plan` 前截断。因此 selector 的通过不能证明系统接受非空必要闭包；不把 P1 概括为所有授权边界均已通过。停止后源码没有更改，相关运行字节保持可审。

主控的 P2 终态记录注明，读取 worker log 时曾使用错误父路径，后改为 `watchdog/worker.log`，没有因此重跑；该手工错误没有单独保存原始 stdout，属于 tool-history observed。经 sandbox 执行 `git add` 因 canonical common Git dir 只读而失败，随后空暂存区 commit 被拒；之后获准使用真实 host 完成 add 和 commit。这些是流程记录，不计作数值结果，也不补造耗时。

P2 与 P1 的机器记录及轻量原件：

- [V11 结果机器记录](outcomes/records/v11_scientific_results_v1.json)
- [P2 主控终态记录](outcomes/records/v11_p2_closeout.json)
- [P2 轻量原件归档](outcomes/records/v11_scientific_sources/P2_space_and_saved_primary_attempt1/)
- [P1 主控收口](outcomes/records/v11_p1_closeout.json)及[首次失败记录](outcomes/records/v11_p1_attempt1_closeout.json)
- [P1 恢复原件](outcomes/records/v11_scientific_sources/P1_focused_recovery1/)

本轮最终科学状态仍为：空间 `PARTIAL`、选择 `PARTIAL`、精度 `NOT_PASSED`、同精度全过程成本 `NOT_ESTABLISHED`、迭代 `NOT_RUN / NOT_QUALIFIED`。working parent 仍为 accepted9/R9，R10 仍为拒绝；没有 transition10、READY、生产资格或 merge approval。不得自动重跑 P2 或启动 P3–P5；任何恢复都需先正式审阅并授权新的具体运行范围。
