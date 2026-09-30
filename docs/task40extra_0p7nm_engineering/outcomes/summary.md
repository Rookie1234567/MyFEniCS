# Task40extra B 线 N0–N6 结果总结：0.7 nm 非可分三维 Maxwell

## 当前结果（R5，2026-09-30）

N0–N6 的当前阶段状态是：strict identity 修复后 G0、G1 正式离散解通过；G0 same-discrete direct comparison 通过；G0–G1 fixed-sample/power engineering agreement 通过。N2 与 attempts 1–4 仍按原范围和原分类保留。

| 正式对象 | 方法、模型规模 | Gate / official output | watchdog 资源与时间 |
|---|---|---|---|
| G0 review_v1 | 336 cells；p6 完整场 229,680 rows、active trace 68,256；p6 trace+port 68,336 rows；q4 凝聚因子 29,072 rows / 10,912,592 NNZ；80 modes；FGMRES 152步 | A6 9.798664008005796e-7；identity 1.520588963522625e-11；R/T/A_balance/A_volume=0.0756519645/0.9062068564/0.0181411791/0.0181412571 | simultaneous tree RSS 3,776,098,304 B；swap 0；workflow/KSP 1204.018/787.135 s |
| G1 review_v1 | 880 cells；p6 完整场 595,512 rows、active trace 177,120；p6 trace+port 177,200 rows；q4 凝聚因子 75,280 rows / 28,705,330 NNZ；80 modes；FGMRES 127步 | A6 9.901397191660007e-7；identity 3.2542694546811876e-11；R/T/A_balance/A_volume=0.0761240621/0.9057692206/0.0181067174/0.0181067127 | simultaneous tree RSS 6,855,741,440 B；swap 0；workflow/KSP 4097.994/3135.913 s |
| G0 direct reference | 同 G0 几何/物理；MUMPS 因子作用于 p6 trace+port 的 68,336 rows；229,680 rows 是恢复完整场的存储维数；80 appended modes | direct residual 5.055376131651821e-11；MATCHED_REFERENCE_PASS；R/T/A_balance/A_volume=0.0756519637/0.9062067814/0.0181412550/0.0181412550 | simultaneous tree RSS 11,505,573,888 B；swap 0；watchdog/charged 1647.527/1801.467 s；PSS disabled |

### 零级 s/p 通道与能量闭合

| 模型 | R00_s | R00_p | R00_total | T00_s | T00_p | T00_total | A_volume grating / substrate | R+T+A_volume−1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| G0 iterative | 0.07565149041679828 | 2.7428991838613296e-18 | 0.07565149041679828 | 0.9062066000865279 | 1.4515667553444104e-18 | 0.9062066000865279 | 0.013925879883210604 / 0.004215377168498715 | 7.799209567060927e-8 |
| G1 iterative | 0.07612358848843093 | 7.987426377936068e-16 | 0.07612358848843173 | 0.9057689645333413 | 4.2210952517070463e-16 | 0.9057689645333417 | 0.013893418210626729 / 0.0042132945191538694 | -4.630012484518886e-9 |
| G0 direct reference | 0.07565148957274329 | 2.5940427852720315e-23 | 0.07565148957274329 | 0.9062065250155358 | 3.476815891411563e-23 | 0.9062065250155358 | 0.013925878172457823 / 0.004215376818162912 | 1.6774137634456565e-11 |

各s/p数值是端口模态功率比。G0–G1变化最大的衍射通道为 top (0,0,s) 的 R 增加 0.0004720981 与 bottom (0,0,s) 的 T 减少 0.0004376359；其余被比较的80-mode功率变化小于 3.0e-10。完整排序与所有模式见 [h-agreement record](records/h_agreement_v1.json)。

正式 G0/G1 source SHA=b8a20bd24848a83f2f4fa50b1ccaaa4ec9be9672；inputs 分别为 6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e / 989a351fb27fe5320942ca2392d0e7e872909f0354509e5d59c8c25e43061c86。direct source SHA=393e5c0dddb933848945ab2e18edb73cf69cc224，direct input SHA=c80c921834cb268a9251459795fbda5acf4e9f25347d16ee24dec3b9d85c6c56。direct 规范化 physical sections SHA 与 G0 的 51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661 一致；原始 identity 差异只有 assembly backend。mode SHA=c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a。

R/T 来自 DtN 端口模态功率，A_volume 来自材料区域体积分吸收。q4 行数和 NNZ 是预条件器的独立 q4 凝聚因子规模，不是 p6 外层维数。direct reference 的完整场 residual 用保存的 b 与 Ax 独立复算，记录值完全一致；详细字段、输入/source 与 artifacts hash 见 [identity recovery compact](records/identity_recovery_v1_results.json)。

同离散比较的 FE L2 / scaled-curl 相对误差为 1.0644e-7 / 1.0590e-7；固定坐标场与界面迹最大相对差 4.9591e-7；80-mode outgoing amplitude 向量整体相对差 1.3374e-7；每模功率最大绝对差 7.5071e-8；R/T/A/A_volume 最大总量差 7.5915e-8。所有 applicable Gate 通过。

G0 到 G1 的共同坐标总场变化约 0.374%（E）与 0.393%（H），总功率各绝对差低于 0.000473，过本任务 1% / 0.001 工程 Gate。这仅表示两张网格在固定样本和当前输出上相符，不是连续极限证明；80-mode channel cutoff 仍未资格化。约 2 TB 目标容量仍 UNKNOWN。

| 其他阶段成本 | 实测 / 近似时间 | 解释 |
|---|---:|---|
| R1 full p6 operator diagnosis | 14,039.107309384039 s | 没有全局 p4 factor；诊断阶段 |
| v1 builder 主动停止 | 约101 s | 近似；审查修正后停止，原分类保留 |
| v2 exact-geometry replay | 198.79226663301233 s | 保存向量的离线复核，无 fresh PDE/KSP |
| attempt1–4 shared ledger累计 | 530.8867869906425 s | 历史 ledger scope，与后续 review_v1 分开 |

### Setup、求解和后处理时间

| 模型 | setup | outer adapter | KSP-only | final native / release checks | official postprocess | 主内存对象记录 |
|---|---:|---:|---:|---:|---:|---|
| G0 | 373.096 s | 798.552 s | 787.135 s | 2.045 / 8.730 s | 11.707 s | worker inventory peak 4,429,493,610 B；workspace peak 1,731,541,832 B；Krylov workspace upper 80,909,824 B；同时树RSS峰 3,776,098,304 B |
| G1 | 908.009 s | 3150.090 s | 3135.913 s | 4.890 / 15.448 s | 14.035 s | worker inventory peak 6,627,841,642 B；workspace peak 1,970,721,416 B；Krylov workspace upper 209,804,800 B；同时树RSS峰 6,855,741,440 B |
| G0 direct | setup/factor阶段无可独立确认的 wall-time 切分 | 不适用 | 不适用 | recovery 0.632 s；其余检查独立阶段时间 unknown | 包含在总 charged 时间内，未独立计时 | PETSc 输入矩阵 MatInfo nz_allocated/nz_used=56,834,000/55,984,880 项；MUMPS INFOG16/17=7,932/7,932 decimal MB、INFOG18/19=8,277/8,277 decimal MB、INFOG22=6,798 decimal MB、INFOG29=346,831,808因子项；同时树RSS峰 11,505,573,888 B，峰值worker stage fine_reference_residual_completed |

outer adapter 已包含 KSP-only；这些时长不能相加当作独立阶段总耗时。direct 计时只报告 watchdog elapsed 1647.527 s 与 launch charged 1801.467 s，不从二者差值分配 symbolic、numeric 或 solve 阶段耗时。NNZ 是矩阵非零项数，不是字节；7,932 MB 是准入估计，不是 RSS 峰值。

direct reference 启动时未使用要求的 user-service wrapper，观察到 cgroup /init.scope。发现偏差后未重启或迁移这唯一运行；独立 subreaper watchdog 完成了后代身份跟踪与清场。该流程偏差在 [execution-context 记录](records/r5_execution_context.json) 中单独保留。

下轮唯一建议候选是任务书 §8.1 的有界局部问题加多层全局波动纠错，重点是新传播/接口/粗空间机制与有界总因子预算；不是重做旧 42 宏块 complete-PC。需在下一 review 冻结机制和准确 p4 对照顺序后再决定是否实施。R5 未执行 Phase II；没有新增 PDE。

## 先前 N6 快照（review_v1 正式运行前）

以下 N0–N6 表和 attempt4 指标是 R4 运行前的历史快照。其当时将 G0/G1/direct 标为未运行，不能解释为当前状态；attempt4 的失败数值与分类仍有效并完整保留。

## attempt4 当时的 N6 状态

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

## attempt4 历史模型与结果

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

## attempt4 当时的精度、网格与容量边界

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
