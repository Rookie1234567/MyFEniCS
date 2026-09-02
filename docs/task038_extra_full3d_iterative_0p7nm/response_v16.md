# Task038-extra Review V16 response：Q1 source-authority 受控停止

| 阶段 | 结果 |
|---|---|
| Q0 | PASS；reference commit 12252290c3d9ec51713094f08c335f24ce172a5b |
| Q1 | CONTROLLED_STOP_PREMEASUREMENT_PROVENANCE / NOT_QUALIFIED |
| Q2–Q6 | not_run |
| W0–W4 | not_run_by_trigger_not_met |

Q1 core 已在 clean core commit 6edf5f5c1255185052a2a5d5fb8dd422f3238f04 实现，但没有启动 formal。V16 固定的
r3_long_tail_derived 需要 p6/h50 source，而唯一旧 R3 authority 是 p6/h10。
当前 F1 p3/h50 只有 mesh=[4,4,3]、rows=4641、active dual packets=4176、
slaves=465；旧 T2 p3/h50 为另一几何、rows=3018；p6/h50 canonical inventory
不存在。

旧 R3 compact SHA 为 4c3f9f23f22bc9e20cef8992d99db86f8eda159951b78b016685214bbc274b68，
source SHA 为 2c8fca90c7300b85b30021081868b699c0b306d2，MPI1 residual manifest SHA
为 62c7824e1032b1a14078d158b0e403b9087dc862bf00386fdce08535e4d76dce；它是
p6/h10、degree6、rows=173802、active dual packets=164592、excluded slaves=9210。

当前源码的 canonical dual reconstruction 对 wrong role、duplicate、missing 和
MPI1 extra key fail closed，但没有跨 mesh 映射。same-mesh P63/P63^H、LOR transfer、
PETSc row 重排或重新 hash source 都不构成 h10→h50 authority。

## Review V16 §19 逐项回答

| # | 问题 | 当前状态 |
|---:|---|---|
| 1 | A3 identity | not_run |
| 2 | small inner solve | not_run |
| 3 | Q2 rho_ref/rho3 | not_run |
| 4 | I20/I100 | not_selected / not_run |
| 5 | short screen | not_run |
| 6 | fresh physical residual/RSS/swap | not_run |
| 7 | release-before-recovery + RSS下降 + official来源 | not_run |
| 8 | direct authority arrays | not_reached / not_run |
| 9 | W与旧路线差异 | not_run_by_trigger_not_met |
| 10 | W local-only/two-level contraction | not_run_by_trigger_not_met |
| 11 | measured/derived/predicted/failed/controlled_stop/not_run 分类 | 见下方证据口径表 |
| 12 | 已消除与仍存 blocker | Q0/核心缺口已消除；p6/h50 R3 authority仍阻塞 |

| 证据口径 | 本轮事实 |
|---|---|
| measured | 没有 Q1 数值或资源测量 |
| derived/read-only | 旧 R3 与当前 F1 identity facts |
| predicted | Q0 central=1714887192 B；hard=1889004056 B；major_unknown=[] |
| failed | 无真实数值或资源 Gate |
| controlled_stop | source-authority mismatch |

既有 [Q0 preflight](outcomes/physical_pcoarse_preflight_v16.md)、
[Q1 oracle](outcomes/physical_pcoarse_oracle_v16.md) 和
[Q1 compact](outcomes/records/physical_pcoarse_q1_authority_v16.json) 已给出证据入口。
第 12 项结论是：Q0 公式/容量预审和 Q1 核心实现缺口已消除，但合法 p6/h50
R3 source 定义/映射仍阻塞，因此 A3 identity 及后续均未资格化。

## 用户明确的次数边界

用户明确允许真实 checkpoint/数值测量之前唯一定位的 path/cache/marker/import/
provenance bug，在保留旧证据、窄修、focused test、review、commit 后用新 SHA/root
唯一重试；这类修复不计正式数值次数。真实 identity、numerical、span、2 GB、
swap、nonfinite Gate 不得重跑。本次是缺少 h50 source 定义的数学合同问题，不是
局部代码 bug，故不能套用 execution-fix retry。V13 positive、V14 J5、V15 F1/F2/F3
和全部历史 negative 原样保留。

## 决定与下一步

固定六 probe formal 不可合法启动；Q2–Q6、W0–W4、official physics 均未运行。
按 V16 文字，W0 只在 Q 被真实数学、数值或资源 Gate 关闭后触发，本次未发生
这类 Gate，因此 W0 未触发。

下一步需主线程明确二选一：提供绑定 p6/h50 mesh、mode、source identity 的合法
R3 source 定义/映射后继续 Q1；或明确授权将 source-authority blocker 视为 Q 关闭
并进入 W0。本 response 不替 Review 做选择。
