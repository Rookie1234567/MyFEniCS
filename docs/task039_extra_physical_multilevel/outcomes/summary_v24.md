# Task39extra V24 增量总结：V23 original-B fresh 与登记 bug replay 完成但保留 A4 负结果

本轮完成一次 V23 fresh 运行及一次登记的 hash-bound implementation-bug replay；计算结束后仅整理证据，未追加 PDE。本文件不改写旧 V21/V22 结论，也不把 B 的完整求解包装为总体 checker PASS。

## 结果矩阵

| 模型 | 状态 | 关键数值 | 资源/边界 |
|---|---|---|---|
| O10 historical original | `PASS` | 112 步；A6 `9.730817853580463e-7` | monotonic `1479.1772295139963 s`；RSS `2831749120 B` |
| A Z2 notch h10 | `MATCHED_REFERENCE_PASS` | 146 步；independent A6 `9.756517234802322e-7` | RSS/PSS `2297982976/2267706368 B`；只读历史 |
| B V23 replay | 求解完成，checker `58/59` | 126 步；A6 before/after `9.2831649554582e-7` | RSS `7387607040 B`；唯一失败是 online p4 A4 |
| C Z4 notch h7.5 | `NOT_RUN_BY_SCOPE` | — | 不自动启动 |

## B 的可核对数值与物理量

| 量 | measured 值/状态 |
|---|---:|
| official port `R/T/A/A_volume` | `0.3650975537006217 / 0.013016803347759965 / 0.6218856429516183 / 0.6218856421339087` |
| `R00_s/p/total` | `0.3650608628870448 / 3.427344920479581e-25 / 0.3650608628870448` |
| 80 channel packet | `80/80`，finite、outgoing match、passive |
| energy closure | `A_port_balance-A_volume=+8.177095667250001e-10`；raw `R+T+A_volume-1=-8.177096777473025e-10`，absolute=`8.177096777473025e-10` |
| field/curl | E/H/auxiliary/power finite；curl postprocess true；`max_abs_E=0.8303744002152752`、`max_abs_H=0.0022039468031068983` |
| native original-A6 RHS/MPC | `native_rhs_norm=1.4293543003082507`；`rhs_is_mpc_dual=true`；本场 internal RHS norm 未单独记录；slave rows/links `22392/22392`；full rows `667152`；appended ports `80` |
| KSP/PC lifecycle | one KSP create/solve/destroy；`127` BAL_H、`127` H6、`254` p4 native A4 |

独立 checker 使用原 `rho<=1e-10` 判据。254 次 p4 调用中 253 次通过；PC2 第一次调用 `rhs_norm=0.800839353350057`、absolute residual `2.3120761610371854e-10`、`rho=2.8870661155266027e-10`，因此 checker 为 `V23_FULL_PHYSICAL_CHECK_FAIL`。这是真实数值 Gate 负结果，不是 checker 字段错误。

## 生命周期 identity 与资源

before-factor、after-factor、before-release lifecycle identity 的 CSR/mapping/values hash 分别保持：

`857bc8bb5f04b28a55283fb960a2b695e1078983e55ff151687780de5dab8ee0`、`bed2794532a40630632e06637cfda5a7bb52a06a7209824d5344085b6fa2cb1d`、`cf081185f6950ebb2c704e0426e02bb0687ef7ae47faf34115d729c8eb832b34`。

native numeric facts 的 fresh after hash 字段仍为 `pending_post_factor_hash`，与生命周期 packet 的一致性结论分列保存。

| 资源对象 | 数值与范围 |
|---|---:|
| native allocated / conservative upper | `INFOG(19)=4687 MB` / `4688000000 B` (`4688 MB`) |
| native used / conservative upper | `INFOG(22)=4326 MB` / `4327000000 B` (`4327 MB`) |
| p6 cache payload | `450893192 B`，不等同 RSS |
| process-tree RSS/PSS peak | `7387607040/7355427840 B` |
| swap/cleanup | `0 B`；descendants cleared true |

native `INFOG(1)=0`、`INFOG(9)=INFOG(29)=221594144`；`ICNTL(23)=4687 MB` 且 readback=`4687 MB`。V23 resource policy 以真实 RSS、MemAvailable/cgroup 压力和 zero-swap/清场证据裁决，仅保留 `128 MiB` watchdog/write 证据余量，不沿用旧 V22 固定 6/8 GiB 或 3.857 GB 续算上限；详见 [user_authorization_v23_physical_memory.md](../user_authorization_v23_physical_memory.md)。

watchdog phase 聚合使用 `worker_phase.phase_started_clock.monotonic`：setup `42.23196291399654 s`、assembly `28.53227231799974 s`、factor `674.3087902290063 s`、iteration/solve `4810.633934284 s`、evaluation `16.41873642199789 s`、cleanup `4.046380408999539 s`。factor 包含 numeric 后 H6/p6 setup；numeric 独立事件为 `222.35688313900027 s`。iteration watchdog 起点 `36022.142617438` 包含 setup PC，正式 solve 起点为 `36064.707110545`，KSP 报告 `4737.310983555995 s`。cleanup duration basis 是最后 watchdog sample 的 `parent_clock.monotonic=40853.102622218`，含退出清场。

本场 JIT 为 `11 hit/0 miss`，compiler descendant samples 为 0；O10 historical 对照本身包含 p6 target cache miss/compile peak；旧 V22 冷场另为 `0 hit/11 miss`、编译 elapsed `101.78435976599758 s`。JIT 时间嵌套于各自 full workflow，不能与总时长相加，也不把 payload 当 RSS。

O10/B 对照：O10 KSP=`1151.635034 s`、`112` 步，B KSP=`4737.310983555995 s`、`126` 步；单步约 `10.28246 → 37.597706 s`，RSS 比约 `2.60885`。O10 的 p6 miss/compile 峰与 V23 全命中口径分开，不能只用旧 V22 cold 解释，也不归因 CPU。

## 成本与负结果保留

| 成本 | 时间/状态 |
|---|---:|
| V21 ledger | `1884.4679552510706 s` |
| V22 ledger | `538.0163161130178 s`，旧 `RESOURCE_BLOCKED` 保留 |
| V21+V22 known ledger | `2422.4842713640884 s` |
| V23 首场 bug 实测 / policy ledger | `379.43654483499995 / 414.7711851870877 s` |
| V23 replay monotonic / policy / settled ledger | `5581.178597819002 / 6079.400587860001 / 6079.411901537711 s` |
| 工程修复与审阅时间 | `unknown` |

implementation-bug 修复为平移不变 affine Jacobian helper，相关几何测试 `16 passed`；资源/runtime/launcher/callback 定向测试 `33 passed`。保存数据 checker 为 `58/59`；本次文档收口没有新增测试、旧资格重跑或追加 PDE，C、notch 和 checker 修改均未发生。

正式 source=`d3596ac31bdabc2bb9233963adea3e91ddc2f220`，checker code 也绑定该 source（本轮未改 checker）；raw checker result SHA=`a875ba4e494b517e542c7f49690d814de610f7fc369887072dbff84697076f71`；base=`8700e65c68b57455586df41f37484d37397dda92`。metadata JSON 的 commit SHA 为 `null`，身份由 containing git commit 识别，不制造自指提交。当前状态 `AWAITING_CHATGPT_REVIEW`，总体 `NOT_FULL_PASS`，不合 master。

证据导航：

- [V23 compact](records/dual_condensed_physical_memory_v23_compact.json)
- [V23 decision](records/dual_condensed_physical_memory_v23_decision.json)
- [V23 checker](records/dual_condensed_physical_memory_v23_checker.json)
- [V23 response](../response_v24.md)
- raw run root：`results/euv_grazing1_phi0/task39extra_v23_b_physical_memory_original_h7p5__full3d_iterative__mpi1__Mna/20260920T004707.275665Z`
