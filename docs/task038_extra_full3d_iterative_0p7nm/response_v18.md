# Task038-extra Review V18 response：E1 eventual continuation 收口

## 当前结论

本轮唯一执行的是 E1 fresh-cold artifact-root checkpoint continuation：同一 p6/h10 physical Maxwell operator、
同一 physical RHS、同一 positive pMG、同一 checkpoint-2024，固定
right FGMRES(restart=64)。用户根据真实测得的残差下降速度授权终止，当前 authority 为
`USER_AUTHORIZED_PERFORMANCE_CONTROLLED_STOP`。这不是 numerical Gate fail，也不是
resource Gate fail；它表示完成 `1e-6` 的时间不具实用性。

E2 fresh zero-start 与 E3 release-before-recovery 均 locked/not_run。V17 的
`EXACT_P3_COARSE_SPAN_FAIL`、`UNRESTARTED_KRYLOV_WEAK_SIGNAL`、V18 旧
`V18_RESTART64_NUMERICAL_GATE_FAIL` 及其 raw/checker evidence 均保持不变。

artifact root：

```text
benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/v18_restart64_eventual_v1/284c39514e257a01cda2407e1a8baf0c38099116/e1/mpi1
```

compact evidence：
[restart64_physical_eventual_v18.json](outcomes/records/restart64_physical_eventual_v18.json)

## Review V18 十项回答

1. **checkpoint-2024 authority。** E0 已读取并通过冻结 manifest/shard 的
   schema、solution-only、ownership、dtype、source/model/operator/input identity
   preflight。manifest SHA 为
   `267a933e1f85cd8685efcfc14a2fc8a50b352d6573a19e9781655c19d3f0be31`，solution SHA 为
   `5ab1ec46b588e1a1c38945ceaf5d41b61f066785ff08ccdd493735a01b45ee79`，MPI1、global/local
   size `173802`、ownership `[0,173802]`、`complex128`。冻结起点的已知 explicit true
   residual 是 `0.27299642739429014`。该 E1 root 有
   `003_checkpoint_restored.json` 和 `e0_checkpoint_preflight.json`；但 TERM 发生在
   parent closeout 前，不能把缺失的 worker closeout 伪写成新的独立 checker reproduction。
   E0 还从 `raw/restore/residual.npy` 与 `raw/same_start/rhs.npy` 独立重算：actual
   `0.2729964273942887`，expected `0.27299642739429014`，absolute difference
   `1.4432899320127035e-15`，relative difference `5.286845493872169e-15`，满足
   冻结 `relative <= 1e-11`，所以 checkpoint reproduction 为 `PASS`。对应 raw SHA
   分别为 `b0d5786b6a16ce99bc93ee588f34b705449751845877cfaa37e286ed07078d89` 和
   `02b86d9226303bf9b8ae2ee0d28cfef6ed374b3fdf7e637c29b52efa3c14445a`。同一 authority
   的 template/input/model/operator SHA 依次为
   `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41`、
   `754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f`、
   `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`、
   `bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3`；mode manifest
   SHA 为 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。

2. **E1 步数、最终 residual、曲线。** E1 solver 的内部起点仍是 additional `0`、
   absolute `2024`，证据映射为 `absolute = 1000 + total_additional`。停止前保存的
   最新 solution-only checkpoint 是 absolute `3048`、total-additional `2048`，其
   manifest explicit true residual 为 `0.15346927855972448`。因此可证明至少
   `3048 − 2024 = 1024` 个 E1-local steps；`2048` 只是从 origin absolute `1000`
   计出的累计 total-additional，不是本阶段步数，TERM 的最终 local/absolute iteration
   unknown。这证明 residual 实际下降，但不是 `<=1e-6`。由于用户在 worker 写完周期 ledger 前授权 TERM，完整
   64-step cycle history、最终 solver count 与 final residual 没有合法 raw record，
   因此均标为 unavailable，而不是猜测。

3. **stagnation、max-it 和停止原因。** 两个完整 4096-local-step block 的
   `q` 判定尚未形成；32768 total-additional cap 也未达到。没有 numerical breakdown、
   max-it 或资源 watchdog stop 的证据。唯一终止原因是用户授权的性能控制停止，独立
   记录在 `user_controlled_stop.json`；最后 timeline sample 的 stage 是 worker，
   runner 的 `e1_complete`/`record_written`/`release_complete` 尚未出现。

4. **资源、KSP 生命周期和 RSS 趋势。** `parent_process.jsonl` 有 350,329 条可读
   样本，SHA 为
   `744ac1407fd9ca097411a7e44eee2d5eac4de5dbae3196620acbeda2959712c7`；process-tree
   peak RSS `1,466,142,720 B`，peak swap `0 B`。这低于严格的 `2,000,000,000 B`
   线。KSP-per-cycle destroy count 与完整 RSS 随总迭代趋势因 worker record 尚未
   写出而 unavailable；不能以部分 timeline 宣称已完成 lifecycle/count Gate。
   TERM 后对已核实的 parent/child process groups 做了两次、间隔 3 秒的空采样，确认
   没有 orphan worker/compiler。timeline 首末 timestamp 差为
   `23,208.841428983 s`，从 `002_case_built.json` 到最后一条 timeline 为
   `17,271.760272149 s`；二者均只是 timestamp-derived observation bounds，不是
   完整 solver wall time。

5. **E2 fresh zero-start。** E2 未运行。E1 没有产生可供 E2 解锁的独立 checker
   PASS/completion authority，且用户已要求锁定后续 heavy；没有把 E1 partial raw
   或用户停止误当作 E2 eligibility。

6. **E3 release/recovery。** E3 未运行。因此没有 E3 release 前后 RSS，也没有
   official complex E/H、near-field、R/T/A、`A_volume`、closure 或同一 `12+12`
   array 的结果。V18 的窄 release evidence 不能代替 official recovery。

7. **direct authority arrays。** 现有 direct scalar packet 仍不能替代缺失的 official
   complex E/H、near-field 和同一 `12+12` complex amplitude/observable arrays。本轮
   没有生成新的 direct authority；状态是 `DIRECT_AUTHORITY_ARRAYS_MISSING`。

8. **未运行、失败和证据路径。** 本轮 E1 的 measured raw 位于上面的 ignored root；
   compact 与 outcome 位于仓库 `outcomes/records/` 和 `outcomes/`。E1 是
   `controlled_stop`，不是 `failed`；`<=1e-6` success Gate 是 not reached；E2、E3、
   official recovery、fresh full PDE、其他 restart/Krylov 和新 PC family 均 not_run。
   因为 parent record 尚未写出，独立 checker 也没有合法输入，故 `checker.json` 不存在；
   这不被重分类为 infrastructure negative，也不伪造 checker PASS。终止审计
   `user_controlled_stop.json` 的当前 SHA 为
   `9e6ed6e5b1b7300a5e4e113cbd6e917281e2020431be786c598344089a7653fa`。

9. **selective merge 边界。** 当前 E1 只留下 evidence/docs，不提升 ordinary
   default，也没有新的 production numerical core。可复用的 fixed-restart64 实现
   仍需把完整 worker record、checker closeout 和 eventual numerical Gate 作为独立
   qualification；本次 partial controlled-stop 不足以 selective-merge 为 physical
   solve capability。所有 V17/V18 历史实现和 evidence 继续按既有审阅边界保留。

10. **下一步 physical PC。** 本轮不选择、不实现新的 PC family。V17 A 的 exact
   p3 coarse span 是 valid FAIL，V17 B 是 valid WEAK signal，旧 V18 restart64 short
   screen 是 numerical FAIL；E1 只是实际性能受控停止。根据当前 physical residual
   曲线、资源和停止位置，四个候选的最小比较如下；它们都只是建议，均未授权、未实现、
   未通过，来源为 [V16 architecture preflight](outcomes/next_pc_architecture_after_v16.md)。

   | 候选 | 针对当前 blocker | 内存风险 | 最小 oracle | 建议优先级 |
   |---|---|---|---|---|
   | intermediate-wavelength / reduced-geometry pilot hierarchy | 先区分长波传播、接口 rank 与 full-scale 资源，不把 E1 的慢曲线直接外推到 0.7 nm | pilot 较低，但会低估完整几何的 rank/通信/工作集 | exact physical interface action 对照、residual、rank/bytes 和生命周期 | 1 |
   | PML / complex-shifted sweeping + compressed interface responses | 用吸收/复移位控制传播接口响应，针对 E1 长程误差与接口耦合 | PML 网格、复数工作量和压缩 response rank 可能同时增长 | 小型物理 local response 与 compressed interface Schur action、误差、RSS | 2 |
   | energy-minimizing H(curl) FETI-DP/BDDC | 用物理 Maxwell 局部算子和能量最小切向 trace 改善子域协调，不假设正 pMG 有效 | saddle-point trace/multiplier 与 coarse solve 增加内存和通信 | 单接口 H(curl) continuity、energy-minimizing constraint 与 local Schur residual | 3 |
   | matrix-free p-h MG + distributed wave coarse solve | 让 coarse problem 承载波动长程误差，直接针对 V17/V18 的 Krylov 弱收缩 | matrix-free 仍保留层级向量、通信 buffer 和 wave-coarse rank | exact physical block action 对照、long-wave contraction、rank/bytes/live set | 4 |

   建议顺序是 `pilot -> PML/complex shift -> physical H(curl) FETI-DP/BDDC -> matrix-free p-h/wave coarse`；这是风险排序，不是资格结论。不得以此启动第五路线，也不能把
   任一候选写成解决了 E1 blocker、通过了 2 GB 线或证明了 `0.7 nm/2 TiB` 可扩展性。

## measured / derived / controlled_stop / not_run

| 类别 | 本轮事实 |
|---|---|
| measured | 7 个 JIT child records、E0/4 个早期 marker、restore/probe/same-start raw、solution-3048 manifest/solution、350,329 条 timeline、RSS peak、swap peak、两次 post-TERM 空采样 |
| derived | E1-local 至少 `3048 − 2024 = 1024` steps；`3048 − 1000 = 2048` 是累计 total-additional，不是 E1 步数；`1,466,142,720 < 2,000,000,000`；checkpoint residual 仍大于 `1e-6`；timeline 边界为 `23,208.841428983 s` / `17,271.760272149 s` |
| controlled_stop | `USER_AUTHORIZED_PERFORMANCE_CONTROLLED_STOP`；用户判断继续到 `1e-6` 预计数日且无实用性 |
| failed | 没有把 E1 标为 numerical/resource failed；success Gate 未完成，不能称 PASS |
| not_run | 完整 E1 closeout/checker、E2、E3、official physics/recovery、0.7 nm/2 TiB solve、其他 PC/restart/campaign |

## 与 V17/V18 既有证据的关系

| lane | measured authority | 当前边界 |
|---|---|---|
| V17 GMRES(20) | `r(500)=0.48362582271206495` | restarted reference |
| V17 unrestarted right FGMRES | `r(500)=0.19374101288500692`，ratio `0.4006010510326989` | `UNRESTARTED_KRYLOV_WEAK_SIGNAL` |
| V18 short restart64 | `r512=0.35604872662297266`、`r1024=0.27299642739429014` | `V18_RESTART64_NUMERICAL_GATE_FAIL` |
| V18 E1 eventual | `r(absolute 3048)=0.15346927855972448` | 用户性能受控停止，未达 `1e-6` |

当前仍没有“正确的 p6/h10 full physical solve”完成证明，没有 official physics，也没有
`0.7 nm/2 TiB` scalability 证明。MPI1 的 2 GB 是硬资源线；本轮 MPI2 未运行。
