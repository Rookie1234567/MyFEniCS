# Response V33：Review V29 / V31 completion rerun 收口

## 状态

首次 V31 尝试 USER_CONTROLLED_STOP 原分类和误停说明均保留。用户随后明确授权且只授权了一场 completion rerun；该运行已经完成，当前结果为 DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED。没有申请或启动第三场 PDE。

## R1–R5 对应

| 阶段 | 事实 | 状态 |
|---|---|---|
| R1 资源复审 | 首次 8 GiB cgroup 误停照实保存；新 run 由 physical-memory-pressure watchdog 完成并清理后代，process-tree RSS 峰值 7,331,401,728 B | 新 run COMPLETED；PSS disabled/null，swap observe-only |
| R2 版本化 checker | 修正 V31 H6 flag 和 A6 scope 从原始 nested audit 的读取路径；增加 V31 raw residual/modal/energy checker | targeted suite 19 passed；首次 attempt 原 checker not_run 的历史不覆盖 |
| R3 候选 | H6 自然序保留在显式 V31 profile；固定形状 projection matmul 继续关闭 | 组件六组配对原结论保留；未新增端到端性能对照 |
| R4 完整场 | user-authorized input，Full3D original p6/h7.5、coarse p4、990 cells、80 modes、MPI1；source=d9b545e824296fce1b489c32a5d96e5e9303ff3c | 126 步；final/release 后残差通过 1e-6 |
| R5 独立审计 | dynamic checker 从 raw boundary、layout、AQ、residual 和监控记录重算；output checker 从 vector、mode orders、功率和体吸收重算 | DYNAMIC_PASS_EVIDENCE_LIMITED 与 PASS_WITH_AUTHORITY_LIMITATION；详细 hash 见机器记录 |

## 数值、时间与预算

| 项目 | 本次测量或复算 |
|---|---:|
| Final / post-release explicit residual | 两者均为 9.283162411158934e-7，限值 1e-6 |
| R/T/A_balance/A_volume | 0.36509755369518077 / 0.013016803348172736 / 0.6218856429566464 / 0.6218856421420169 |
| R00_s / R00_p / R00_total | 0.365060862881605 / 4.812903003419231e-23 / 0.365060862881605 |
| Energy closure / A_balance−A_volume | 约 8.15e-10 / 8.15e-10，均低于 1e-5 |
| Workflow monotonic / conservative realtime settled | 2313.526 / 2534.117 s |
| Watchdog tree RSS / PSS / observed swap | 7,331,401,728 B / null disabled / 0 B observe-only |
| Shared ledger | ceiling 43,200 s；cumulative measured 4,832.519 s；remaining 38,367.481 s；bug replay 0；budget extension 0 |

completion rerun 的时间用于完成记录；授权并未包含性能比较，因此不将它与首次中断时间作快慢结论，也不宣称端到端加速。

## 资格边界

80 个有序 DtN 模态的功率和与官方 R/T 合计一致，体吸收与端口 A 闭合通过。没有匹配参考场，五个 field-reference checkpoints 均为 NOT_ATTEMPTED；FE L2/scaled-curl、同坐标 E/H 与模式相对误差没有测量。因此只报告当前离散问题的求解与输出一致性，不宣称连续极限收敛或跨机器资格。

通用 physical_intermediate_checker.py 曾返回 EVIDENCE_INCOMPLETE，因为它要求本 V31 worker schema 不生成的 physical_intermediate_summary.json。V31 专用 raw checker 已直接读取真实 artifacts 并通过；通用 checker 结果原样记录，不记作 V31 gate。

V31 profile 仍显式 opt-in，ordinary default 未改，工作站未迁移，master 未合并。完整授权、预算、结果、resource、checker 和 artifact SHA 在 [authorized rerun record](outcomes/records/projection_layout_v31_authorized_rerun.json)；首次误停证据在 [首场 compact/checker](outcomes/records/projection_layout_v31_compact.json)。
