# 测试与 Benchmark 契约

## 自动测试层

| 编号 | 主题 |
|---|---|
| 00-03 | 单位、平面波、PML tensor、Fresnel |
| 04-10 | 3D Stage1/2 PDE、Floquet、PML、Fresnel 组合 |
| 11-17 | diffraction、orientation、entrypoint、DtN、mesh、2D EUV、p2 trace |
| 18-19 | direct profiles 与 OOC cleanup |
| 20 | 2D lossy DtN 传播级与实际端口平面功率 |
| 22 | exact condensation |
| 23 | physical slab two-level/MPI/sm2 |
| 24 | 仓库工作原则 |
| 25 | benchmark manifest/record/Gate 基础契约 |
| 26 | 文档索引、链接、case 结构契约 |
| 27 | main preset/parser/default/iterative 隔离契约 |
| 28 | Task029 memory snapshot、stage marker、matrix inventory、candidate parser/record、cleanup、prediction 与 h2 G1–G10 guard |
| 29 | Task030 baseline pin、active DoF、nonmatching H(curl) transfer/cache、condensed Galerkin、low-rank adapter 与 compact slab action |
| 30 | Task031 Case070/outcomes 合同、public MPC form action、fine lifecycle、PC certificate、factor fingerprint 与 ordinary-default 隔离 |
| 31 | Task032 full-3D reference grid、64 MiB guard、单侧接口取迹和默认关闭合同 |
| 32 | Task032 matching cross-section、双 Floquet orientation、distributed QEP、解析/有损 beta、±配对、L2 范数和 MPI ownership |
| 33 | Task032 Poynting/衰减分类、adjoint QEP、Q' 双正交、近简并 block、正反 identity、tracking 和 principal angles |

测试号 21 仍为空缺，是历史任务清理结果；不为连续编号而塞入无意义测试。

## Benchmark 三层

| Level | 内容 | 成本 |
|---|---|---|
| 1 | compile、unit、2D zero contrast、3D Stage1 MPI2 | 轻量 |
| 2 | condensation、physical slab MPI4、checker | 轻量/中等 |
| 3 | target direct 与 workstation iterative | 重型 |

## case 文档契约

每个 `benchmarks/cases/NNN_*/README.md` 冻结：证明/不证明、物理、几何、材料、波长/角度/偏振、边界、FE/mesh、preset、参数表、精确命令、调用链、理论、solver、RTA、输出、Gate、结果、record、artifact、限制。

## checker

`check_benchmarks.evaluate` 从 manifest 载入 records 和 expected gates，检查身份、canonical config、物理模型、residual、KSP、coarse、RTA、direct/iterative 差、RSS、环境和 ordinary default。`--no-write` 不改变 report；普通写模式刷新 summary/report，此时 checkout dirty 只表示 checker 输出已被改写，不等于源 record 运行时 dirty。

## 运行策略

代码改动先 compile + focused tests，再 full unit/MPI，最后按风险决定 Level3。文档/metadata Task28 V2 不要求重跑 h=2；历史 record 可补 provenance/physical model，但不得篡改数值。

## Task029 外部采样链

`benchmarks.run_direct_memory_forensics` 由单个父进程启动 MPI worker，读取 worker 进程树与 `/sys/fs/cgroup`，并从 `progress_3d.jsonl` 获取 rank0 stage marker。`max_simultaneous_total_rss_mb` 是同一采样时刻 MPI worker 当前 RSS 之和；`sum_rank_historical_peaks_mb_upper_bound` 是各 rank 历史高水位之和，两者必须分开。worker 仍调用 `target_stage4_config` 和原 Stage4 solver，遥测默认不改变物理或 direct profile。

`test_28_direct_memory_telemetry` 还验证 h2 缺少 gate record 必须阻塞、G1–G10 任一 false 必须阻塞、两点幂律预测输入合同、`DirectSolveFailure.cleanup()` 幂等性，以及 h5/h3 selected candidate record 的完整求解/数值字段。Task29 final decision 中 G3/G5/G7/G9 为 false，因此未实现或声称 active h2 watchdog，也没有启动 h2。

## Task030 contract

`test_29_hcurl_multilevel` 检查 Case031 hash pin 和 iteration100 fail-closed、active/master map、nonmatching transfer 无零列、Hermitian adjoint/cache round-trip、exact condensed Galerkin action、Python-PC adapter 与 ModalWoodbury 生命周期。`test_23_physical_slab_two_level` 追加 local diagonal shift 和 factor-only storage 的 serial/MPI2 action 等价。

Case060 的 solver 性能结论不由单元测试代替：正式 p/h 候选必须有 20/100 步真残差，最佳方案必须有 h5/h3 full residual 和 official R/T/A；h2 只能在 G1-G10 后运行同一唯一候选。heavy artifacts 不进 Git，轻量 records 保存门槛所需字段。

## Task031 contract

`test_22_condensation` 覆盖 external fine action、`require_f/release_f`、重复 destroy 与 assembled equivalence；`test_23_physical_slab` 覆盖 PC linearity/determinism helper、fixed Richardson、selective slab、exact fingerprint 与 compact factor lifecycle。`test_30_task031_contract` 检查 Case070 JSON/CSV、Task031 summary/development progress、索引、ordinary default 与三份 clean best records。Review V1 后还固定 `iterative_solver_ports.md` 的 interface-vs-qualification 状态、保守 8.0–8.2 GiB 口径、response_v1 和 wrapper 规则：FGMRES 默认不强制 fixed-PC cert，所有非 FGMRES outer KSP 仍自动 certification/fail closed。

Case070 checker 还必须验证 clean full-SHA/image/artifact hash、same 80 modes、FGMRES/matrix-free/compact identity、三残差、fine action、official R/T/A/direct delta、external simultaneous peak、swap、h3 8% Gate、两套 h2 prediction/upper 和 h2 strong classification。单元 action pass 不能替代 h5/h3/h2 full solve。

## Task032 Phase 1 contract

`test_31_full3d_reference_export` 检查普通默认关闭、周期单元中心网格、严格递增 z 平面、接口从中间模态区单侧取迹和冻结样本 payload 边界。实际 complex128 数组、切向 slice、finite 值与三方 SHA 一致性由 clean h5/h3 run 验证，不能只靠 unit test。

Case080 checker 固定 source commit/image、clean provenance、残差、能量闭合、R/T/A、NPZ schema/shape/planes/dtype、接口侧、六个 artifact hash 和 h3 历史一致性。heavy field 不进 Git；h5/h3 的内部 per-rank historical peak sum 不是 simultaneous memory authority。

## Task032 Phase 2 contract

`test_32_task032_cross_section_qep` 覆盖匹配 Stage4 x/y 轴的截面材料、双 Bloch phase、Nédélec orientation probe、无 slave-chain 的 `u=Cq`、air 与 lossy 解析 beta、`+/- beta`、QEP 残差、electric-L2 范数和 MPI ownership。正式 Case080 record 固定 clean SHA、镜像、MPI4、SLEPc PEP/TOAR、六个 case、稀疏约束通信范围和 no-full-vector-gather。

checker 还要求 air h5/h3/h2/h1.5 解析误差严格下降、h2/h1.5 与 lossy h2 分别通过阈值、所有选中模态残差/归一化/orientation 通过、每个 rank 的 local ownership 求和等于全局 shape，并验证需要的 `+/- beta` 配对。当前正式结果为 `277/277 passed`。Phase 2 electric-L2 不是最终 Poynting/双正交归一化，后者必须由 Phase 3 单独证明。

## Task032 Phase 3 contract

`test_33_task032_mode_classification` 覆盖 Poynting 正反方向、lossy complex beta、near-zero flux evanescent/cutoff branch、显式 adjoint QEP 左残差、`Q'(beta)` block 双正交、左右向量 MPI ownership、正反 mode identity、相邻角度 overlap matching、模式数增加时 unmatched 新模和近简并 principal angles。MPI4 固定覆盖正向 distributed basis；重复负向/相邻参数 PEP 留在 serial 合同，避免日常 MPI 回归重复昂贵 factor setup。

`run_task032_phase3_modes` 的完整 MPI4 路径仍覆盖 air 正反 basis、homogeneous lossy、当前 Stage4 `epsilon(x,y)` 和角度 tracking。正式 record 必须固定 clean full SHA/image/MPI4、右/左残差、left-beta conjugate pairing、biorthogonality identity、unit-absolute-Poynting 或 near-zero classification、passive branch、reciprocal pairs、tracking/subspace、ownership 与 no-full-vector-gather。

clean source `72dca66...` 的正式 Phase 3 record 已满足上述合同；checker 新增 identity、case/ownership/condition、residual/biorthogonality/flux、direction/reciprocal、tracking/subspace 五类 Gate，Case080 总计 `282/282 passed`。
