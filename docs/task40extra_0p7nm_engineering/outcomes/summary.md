# Task40extra B 线 N0–N6 结果总结：0.7 nm 非可分三维 Maxwell

## 最终状态

G0 attempt4 已真实建立 p6/q4 空间并进入外层迭代。 这里的恢复/native identity 检查，是把凝聚后求出的未知量恢复成完整场后，核对它代回原始方程的作用是否与凝聚代数一致。第 8 步，原 A6 相对真残差为 0.16667295750232392（要求 ≤1e-6），native recovery identity 为 3.0748104980683956e-10（要求 ≤1e-10）。worker 原始 summary 分类为 V20_RELEASE_GATE_FAIL。根据每 8 步检查的源码规则，这是恢复/native identity Gate 停止；raw KSP status/reason 未保存，因此具体 callback/reason 属于源码推导。它不是资源停止，也不是 max_it=2048 后仍未收敛的结论。

| 阶段 | 状态 | 证据边界 |
|---|---|---|
| N0 | complete | B线执行分支和 canonical worktree 已绑定 |
| N1 | complete | 0.7 nm 材料、有限三维缺口、G0/G1 计划、80-mode 清单已冻结 |
| N2 | diagnostic_pass_only | 60-cell p2 tiny 残差 1.772707454694957e-12；不是 G0/G1 p6 |
| N3 / G0 | V20_RELEASE_GATE_FAIL | 前三次实现异常保留；attempt4 进入8步 outer solve 后停止于 identity Gate |
| N4 / G1 | NOT_RUN | 没有 h-refinement 或跨网格比较 |
| N5 / G0 direct | NOT_RUN | 没有合格 iterative subject，direct reference 未运行 |
| N6 | closed_limited | 保存受限数值结果、成本和边界；没有精度/容量资格通过 |

p6 高阶有限元用较高次多项式表示复杂电磁场；路线先处理每个单元内部未知量以缩小全局问题，再用 q4/p4 操作纠正解。这样能减少外层未知量，但必须检查恢复后的全场是否仍满足原始 A6 方程和恢复恒等式。小型 p2 诊断、mesh audit 与投影检查仅验证各自环节，不能替代 p6 release Gate。

## 实际模型和结果

| 项目 | attempt4 实测 | 解释 |
|---|---:|---|
| 输入 SHA256 | 8e00fb6495845902a8113d982242d39ad0f4999b563c2c8049ecc3750b82ac9c | 冻结 G0 p6/q4 输入 |
| source SHA | de44f5bb4da48cd076df2b295ef6fe08b83d52fa | 实际运行源码身份 |
| physical model SHA256 | 51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661 | runner物理模型身份 |
| G0 mesh / spaces | 336 cells；p6 229,680 rows；q4 69,856 rows；80 modes | 几何 audit 和 native AQ projection setup checks 通过 |
| solver | FGMRES，restart=32，max_it=2048；实际8步 | numerical Gate 提前停止，不是迭代上限 |
| official result | false | diagnostic field/error packet 保存；official R/T/A、A_volume 和能量闭合未生成 |

第 8 步 native identity 公式为 e_FE - B*H_p^-1*e_p。主控对已保存数组离线复核，difference 向量等于 native residual 减 derived native residual；范数 1.0129916171163611e-9 除以 operation scale 3.29448470971699 得 3.0748104980683956e-10。超过门槛约 3.07 倍。本记录不把它先验称作 roundoff，也不能由单次 Gate 单独确定其更深根因。

| 指标 | 实测 | 限值 | 状态 |
|---|---:|---:|---|
| 原 A6 full explicit true residual | 0.16667295750232392 | ≤1e-6 | 未通过 |
| native identity relative | 3.0748104980683956e-10 | ≤1e-10 | 未通过 |
| internal residual relative | 6.4490341352469694e-18 | ≤1e-10 | 通过 |
| port closure relative | 1.4794093427202804e-15 | ≤1e-8 | 通过 |
| Schur-port identity relative | 1.3094474052481446e-29 | ≤1e-10 | 通过 |
| final release packet A6 relative | 0.16667295750232333 | ≤1e-6 | 下游释放检查仍未通过 |

源码在 iteration 8 snapshot 中先检查物理残差，再检查 recovery/native/Schur identity。按保存数值可推导 callback 将其记为 RECOVERY_IDENTITY_GATE_FAIL，并返回 DIVERGED_BREAKDOWN；这两个字段均不是 raw KSP 记录。release packet 原生记录 V20_RELEASE_GATE_FAIL。外层 launcher 另外记 exit 4 / WORKER_FAILED；该 wrapper 状态不表示资源停机。完整证明、源码路径和 artifacts hash 见 [attempt4 compact record](records/g0_attempt4_identity_gate_stop.json)。

## 三次实现错误与第四次 Gate

| 运行 | 结果 | 含义 |
|---|---|---|
| attempt1 | parent ledger batch identity 不一致；3.896 s | 数值工作未开始，implementation bug |
| attempt2 | same-mesh wrapper 缺 rectangular_air_void_audit；87.897 s | 实际建成336-cell mesh并通过 native projection 检查，随后 cleanup 实现失败；未进入 outer KSP |
| attempt3 | 新 worktree 缺 Task39 相对 JIT cache 源路径 | FileNotFoundError；单次耗时未独立持久化，implementation bug |
| attempt4 | V20_RELEASE_GATE_FAIL | 进入真实迭代后因恢复/native identity Gate 受控停步；不是前三次 bug 的重分类 |

attempt3 的独立 elapsed 和必要人工修复工时都是 unknown，不能由共享 ledger 的时间差倒推。全部四次 worker、source、artifact SHA 与 ledger 在 [run index](records/run_index.json)。

## Setup、KSP 与资源成本

| 统计 | 值 | 口径 |
|---|---:|---|
| p6 / p4 condensation cold JIT | 58.575 / 18.047 s | 各自compiler event |
| compiler events | 11 | 包含多角色及缓存命中/未命中；不是单一setup时长 |
| qualified JIT hardlinks | 104 files / 1,400,533,851 B | 缓存文件字节，不是驻留内存 |
| p6 build audit | 15.216 s | 原记录 build timer |
| x1 setup-check | 22.907 s | setup-check timer，不表示完整全流程装配 |
| retained outer clock through terminal snapshot | 54.222 s | 保存的 outer elapsed；KSP-only elapsed 未持久化 |
| outer iterations | 8 matvec / 8 PC apply | KSP外层动作计数 |
| setup-inclusive inventory | bridge 13 / p4 26；terminal native 6 / Schur 11 / Hp solve 44 | 原字段各有范围，不能折算成8次outer PC |
| launcher workflow monotonic | 356.929 s | monotonic时间 |
| conservative realtime workflow | 392.257 s | 与monotonic差35.330 s |
| shared ledger | 本次 debit 392.262 s；累计 530.887 s | 账本口径，不是KSP-only时间 |
| process-tree RSS peak | 2,954,866,688 B | watchdog sampled simultaneous process-tree peak |
| swap / PSS | 0 B / disabled | 没有资源 Gate stop；PSS按profile禁用 |
| process cleanup | descendants cleared；identity coverage complete | watchdog 1,397 samples |

共享 ledger、conservative realtime 与 monotonic 是不同观测范围，不相减推造 KSP 或工程工时。cgroup memory peak 未在本次 compact run 记录中报告；不补值。

## 精度、网格与容量边界

| 问题 | 当前结论 |
|---|---|
| official R/T/A、A_volume、energy closure | NOT_RUN；A6及identity release Gate 未通过 |
| G0–G1 h agreement | NOT_RUN；G1 未运行 |
| G0 same-discrete direct authority | NOT_RUN；direct preflight/factor/solve 未运行 |
| 80-mode channel truncation | CHANNEL_TRUNCATION_UNQUALIFIED |
| 2 TB target feasibility | unknown；一次 G0 RSS 不能外推目标规模 |
| 主导容量对象 | unknown；缺少通过 accuracy Gate 后的容量闭环 |
| Phase II PC | none selected；本批没有候选获得精度/有效性资格 |

没有 best-available discrete reference，也没有工程网格或连续极限结论。N2 tiny 诊断结果不作为 G0 的替代。N6 收口保存失败值和缺失值，不再运行 G1、direct 或其他 PDE。

## 选择性合并建议

| 依赖组 | 代表内容 | 当前建议 |
|---|---|---|
| production numerical/core | Task40 config、geometry、solver/runner profile | 数值 Gate 未通过；不升级 ordinary default |
| reusable runner/watchdog | run_case、JIT staging、watchdog | 保留工作流证据；不是 solver pass |
| checker/benchmark | N1 inventory、geometry fixtures、N2 diagnostic | 只支持各自范围 |
| compact evidence/docs | attempt4 record、run index、summary、response、测试摘要、模型总账 | 可随分支审阅 |
| research-only | 显式 Task40 p6/q4 双凝聚 profile | 保持研究用途，未资格化 |
| do-not-merge | 整体分支、master、ordinary default 切换 | 等待 review/merge approval |

## 证据入口

- [attempt4 compact record](records/g0_attempt4_identity_gate_stop.json)
- [运行索引](records/run_index.json)
- [阶段状态](records/phase_I_results.json)
- [精度与容量](accuracy_and_capacity.md)
- [测试摘要](test_summary.md)
- ignored raw attempt4 artifacts 位于 run index 所列 results 路径。
