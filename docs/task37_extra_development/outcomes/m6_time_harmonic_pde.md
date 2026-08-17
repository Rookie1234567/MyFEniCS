# M6A 全空间无矩阵 DtN 与后续时谐/PDE边界

## 当前状态

M6A 的作用是验证冻结的 80 模式端口 DtN（Dirichlet-to-Neumann，给定端口场后计算端口通量）在真实 p6/h10 全空间上可执行，并与独立的流式 direct modal-sum 对照一致。它只验证端口 action/恢复的数值和架构合同，不等于时谐 PDE 求解或最终物理结果。

| 路线 | 状态 | 边界 |
| --- | --- | --- |
| M6A matrix-free full-space DtN | `PASS / QUALIFIED` | 仅 action/DtN authority；checker 15/15，通过 MPI1/MPI2 对照 |
| W14A–W18A action-only diagnostics | `completed / negative where stated` | 只完成 action、数值和资源 Gate；不是 PDE/RTA |
| full time-harmonic PDE / RTA / field recovery | `not_run_yet` | 未运行 |
| 最终 PDE `<2,000,000,000 B` process-tree 目标 | `not_run_yet` | 未测量，不能由 M6A peak 代替 |

## 固定模型与数值结果

| 项目 | 实测/合同 |
| --- | --- |
| source | `2a9dabaa13365373864814d7146ee9399395ed51` |
| mesh/space | p6、h=10.0、252 cells、173,802 global rows、9,210 constraints、local nloc=882 |
| port modes | 80；mode manifest SHA `8d7c396b5251365c6865b2fafefd37e1559794fe39f445ef8bccc3b8ff29cac5` |
| physical layout | `fine_space=uncondensed_fullspace` |

MPI1 与 MPI2 的 candidate action、独立 direct action、physical RHS、recovery 和 repeat 五项误差均为 `0.0`，且 finite。checker 的 cross-MPI source/action/RHS/recovery 与 mode-manifest checks 全部为 `true`；cross-MPI recovery relative error 为 `0.0`。

| 阶段 | peak RSS | swap | elapsed | compiler descendants | cleanup |
| --- | ---: | ---: | ---: | --- | --- |
| isolated stage | `527,859,712 B` | `0` | `13.230624606 s` | 有，属于隔离 JIT stage | `true` |
| MPI1 online | `388,956,160 B` | `0` | `21.308124773 s` | `[]` | `true` |
| MPI2 online | `693,411,840 B` | `0` | `14.421220687 s` | `[]` | `true` |

retained+work 为 MPI1 `16,673,350 B`，MPI2 每 rank `8,378,950 B`、global sum `16,757,900 B`，均低于 `150,000,000 B`。在线 cache 的 20 个文件满足 `stage == before == after == final`；online 未产生 compiler descendant。

## 架构边界

candidate 与 direct oracle 都不物化 PETSc C/D、global、augmented 或 Schur/trace matrix；explicit C/D count 均为 0，采用两个流式 direct assembly pass 和每次一个 80-complex modal Allreduce。无 static condensation、trace-slab PC、DtN retained matrix、FE-sized numeric allgather；输出/载荷使用 owner-local dual 语义，source 保持 primal 语义。M6A 仍不是 PDE、RTA 或 official physics qualification。

## 早期负证据

M6A run1 的 online-JIT/cache lifecycle negative 与 run2 的 watchdog JSON serialization negative 都是 execution failures，分别保留在原 raw/check 路径中；不把它们改写为算法 FAIL，也不把它们当作 PASS。run3 是修复后的唯一 positive authority，本 outcome 不覆盖 run1/run2/run3 raw 或外部 checker。

## 证据索引

| 证据 | 路径 / SHA |
| --- | --- |
| run3 raw | `benchmarks/artifacts/task037_extra_development/m6a_2a9daba_run3`；raw tree digest `665f3a02a13f73c0a949e817c3b2bc7fc915166c10f61dc844c09a242f7cff52`（82 files） |
| watchdog summary | `.../m6a_watchdog_summary.json`；`2a275b43f756a54e8285d0bc16d57947e6731d1615d91ecc37d2295182ffccd6` |
| stage summary | `.../m6a_stage_summary.json`；`a1f157314a5b3651090e61d9bc58523c15aaf6ace9f77fa1c15e992bb11046bd` |
| MPI1 worker summary | `.../mpi1_worker_summary.json`；`65bcb6cad5bf6cc856867f474fbeb8114f7da4509b58df667a728ba470f31341` |
| MPI2 worker summary | `.../mpi2_worker_summary.json`；`ad92cb53a6256b6a3c5081bccabd9c8d9a0d663a53aad2daca963cb48c3c1646` |
| external checker | `benchmarks/artifacts/task037_extra_development/m6a_2a9daba_run3_check.json`；`d121f19553576e1fcce947325edc35c1ef16ecbf370cab9b7ad1477fe16b0c2a` |
| checker embedded evidence | `9a412106a6428c1555b58945eeda6a5b1294bd0e1e85bc763c6c46a7314f30a4` |
| tracked compact | `benchmarks/cases/101_task37_extra_development/records/m6a_fullspace_matrix_free_dtn.json`；byte-for-byte copy of external checker |

M6A 的 action peak 不能当作 PDE peak；W5 time-harmonic screen 已正式运行，但 full PDE、field/RTA、direct-authority physics comparison 和最终 PDE RSS 仍等待后续阶段。

## W5 disk-backed time-harmonic screen（正式负结果）

W5 将 Krylov 基向量放到外部 scratch 文件，减少常驻进程内存；这解决的是内存生命周期问题，不会自动改善算子谱性质或迭代收敛速度。W5 的资源和证据检查通过，但真实残差数值 Gate 未通过，因此不能作为 PDE 或 RTA 结果。

| 项目 | 结果 |
| --- | --- |
| source / checker | producer `41cbbd454eb8336d9ea5378ed618447acfc60aac`；checker `9317e19e924e5b15297c168ea4f2271ae42172eb` |
| classification | `NUMERIC_FAIL`；`execution_evidence_ok=true`；`resource_evidence_ok=true` |
| peak / swap | `1,607,802,880 B` / `0` |
| true residual 20/100/150/200 | `0.3237575899853163 / 0.18105272614044404 / 0.15403613391023072 / 0.12750559935416836` |
| 150→200 improvement | `0.17223578573793497`，通过 `>=0.15` |
| 数值 Gate | 20、100 和改善率通过；200 要求 `<=0.08`，实际 `0.12750559935416836`，失败 |

W5 compact checker 为 RC1 的预期负结果，记录在
`benchmarks/cases/101_task37_extra_development/records/m6b_w5_disk_fgmres_screen.json`。full time-harmonic PDE、official RTA、direct-authority physics comparison 和最终 PDE `<2,000,000,000 B` 目标本轮均未运行。用户已授权继续针对具体收敛问题研究，但没有放宽 2GB、swap=0、true residual 或物理一致性 Gate；冻结的 W5 raw/watchdog 和更早负结果均保持不变。

## W6B-S0 固定多阶基的离线诊断

W6B-S0 只读取 W6A 的 390 列 `AZ` 磁盘 scratch 和四个冻结 W5 residual，比较旧 75 列与固定追加的 `n=0, m=-7..-1` 列集合。它没有重新生成 FE 函数、调用 physical/DtN action、运行 KSP 或 PDE；因此这里只能说明残差与已生成列空间的关系，不能称为 formal W6A Gate 或 PDE 结果。

| 项目 | W6B-S0 结果 |
| --- | --- |
| classification | `DIAGNOSTIC_ONLY` |
| full390 rho（20/100/150/200） | `0.9703655744743773 / 0.9818418639331844 / 0.980066335096579 / 0.9764446942793938` |
| iter200 相对 legacy75 改善 | `0.0235440355720149`，低于 `0.15` |
| 进程树峰值 / swap | `196,874,240 B / 0`（离线诊断实测） |
| AZ scratch | `1,084,524,480 B`，磁盘占用，不计作 RSS |
| formal / PDE / official RTA | `false / false / false` |

W6A 正式数值 Gate 已经给出 `rho390@200=0.9764446942793935`、相对改善 `0.023544035572015565` 的负结果；W6B-S0 在约 `4.6e-15` 内重算复现。iter200 的 component=1 追加组是主要信号（`rho=0.9767683658573292`），component=0 和 component=2 的收益很小；按固定阶次累计，完整 `m=-7..-1` 仍只达到约 `2.35%` 的改善。因此现有数据不足以支持“仅继续加入 n=±1 就能达到 0.70”这一假设，本轮不启动新的大规模 builder 或外层 screen。

compact 证据为
`benchmarks/cases/101_task37_extra_development/records/m6b_w6b_s0_5c34906_spectral_diagnostic.json`，file SHA `1a4e34e4f50d633986ef68c88222edab3a4f3bb1d247033a3389e98cc4be2a90`，embedded evidence `333d2dfb0822b21d24fc97ec0b7dc63325179051d14a7c977a674944acecf280`。W6B raw 和 watchdog 只读绑定，旧 W5/W6A 负结果保持不变；full PDE、field/RTA、direct comparison 和最终 PDE 内存目标仍未运行。

## W7-S1 固定重启 continuation：正式数值负结果

W7-S1 从冻结 W5 iter200 的解开始，把它作为新的初始猜测，然后重新建立一个最多 200 步的 disk-backed right FGMRES cycle；它不是把旧 Krylov 基扩展到 400 维。固定 local checkpoint 20/100/150/200 分别对应累计 identity 220/300/350/400。

| local / cumulative | true relative residual | 结论 |
| ---: | ---: | --- |
| 20 / 220 | `0.12661146396748116` | 记录 |
| 100 / 300 | `0.1253957238823895` | 记录 |
| 150 / 350 | `0.12438973880901087` | 记录 |
| 200 / 400 | `0.12141751388827249` | `<=0.08` 失败 |
| 350→400 improvement | `0.023894454230681927`（约 2.389%） | 诊断项，低于 15% |

独立 checker 分类为 `NUMERIC_FAIL`，但 `execution_evidence_ok=true`、`resource_evidence_ok=true`；唯一 hard numeric problem 是 cumulative400 residual。进程树峰值 `1,611,878,400 B`、swap `0`、进程已清理。预测 live set `1,666,871,296 B` 是 derived/not measured；外存 Krylov scratch 是磁盘占用，不能当作 RSS 或 PDE 通过。

W7-S1 compact：`benchmarks/cases/101_task37_extra_development/records/m6b_w7_s1_restart_disk_fgmres_screen.json`，file SHA `3fcabe2dbc753017158b7f587f025a73a4e5f2eb5b7539d264cd3984846a192d`，embedded evidence `6c92da32f39e4a82ab8cffc851a437e5adb804fa62ebffc13d4068d3c83b9f6b`。producer source 为 `7febc1e3aeb52613d098fd2aadede3b288c69b5b`，checker source 为 `5e72e45673b05dac3c2c15c7c7e1b7fb4dfdee39`；旧 W5/W6 负结果及 W7 run1/run2 受控失败保持不变。

本轮仍未运行 full PDE、official RTA、field/direct-authority physics comparison 或最终 PDE `<2,000,000,000 B` Gate；没有放宽 residual、swap、内存或物理一致性要求。

## W8–W12 研究收口

这一组路线都围绕同一个问题：在不改变 p6/h10 全空间物理算子、matrix-free DtN 和 residual Gate 的前提下，能否从已有残差或 Krylov 方向中找到足够强的低内存修正。结果均保持研究性和负结论，不能当作 PDE/RTA 通过。

| 阶段 | 方法的通俗含义 | 关键实测 | 状态 |
|---|---|---|---|
| W8A/W8B | 在冻结 W6A 390 列上加入固定 140 个 z-bubble 列，再离线比较 530 列对残差的投影 | W7 cumulative400：`rho390=0.977537441982527`，`rho530=0.9280021437706651`，改善 `0.050673555901245226` | `W8B_NUMERIC_OR_AUTHORITY_FAIL`；不进入 W8C |
| W9A | 用 W5 四个 checkpoint 的解增量构造固定 4D 修正空间 | target rho `0.9982181470553635`，captured energy `0.0035605308893762767` | target Gate `rho<=0.90` 失败 |
| W10A | 把 W5 完整 201 列 Arnoldi V 空间当作“最好可能”的回收上限 | target optimistic rho `0.9793601827912443` | 即使乐观上限也失败；旧空间 mapping 路线关闭 |
| W11A | 用一个新 preimage 方向尝试直接消除 persistent residual | Q1 100 步 B0 residual `2.8285584503326906e-06`；q/target rho `0.9261490705957542/0.9390855969756224` | `W11A_PERSISTENT_DIRECTION_FAIL` |
| W11B | 固定 200 步 B0 FGMRES 后只做一个 exact-proxy 方向 | B0 residual `4.233006159940796e-09`；q/target rho `0.8914688323899443/0.9101959562746206` | `W11B_PROJECTION_FAIL` |
| W12 | 保留同一固定 200 步 B0 轨迹的四个解，形成 4D range 修正 | B0 residual `4.233006159940796e-09`；q rho `0.8857084974811911`、target rho `0.9050305821821468`；peak `1,116,065,792 B`、swap `0` | `W12_TRAJECTORY_RANGE_FAIL`；数值失败，不是执行/资源失败 |

W12 的四个 checkpoint 是 `20/100/150/200`，physical action count 为 4；实际生命周期为 B0 构造、释放后才构造 physical action，再释放 physical action。两个投影阈值分别为 q `<=0.70` 和 target `<=0.90`，实际值均超限，所以没有写出 candidate `dX/dAX` 文件。它没有运行 full PDE、official field/RTA 或 direct-authority physics comparison；预测 live set 仍标为 derived/predicted，不能用来替代 process-tree 峰值。

W8–W12 的 consolidated hash-bound evidence 见 [`m6b_w8_w12_consolidated_closeout.json`](../../benchmarks/cases/101_task37_extra_development/records/m6b_w8_w12_consolidated_closeout.json)，旧 raw、watchdog、临时 JSON 和既有 compact 均保持只读。完整 W8C、新 W9B、新 W10 mapping、后续 physical FGMRES 和最终 PDE `<2,000,000,000 B` 目标均为 `not_run`。

## W13A：固定 ProjectedRangePC 组合的 beta 诊断

ProjectedRangePC 的作用可以简单理解为：先用局部 shifted PC 处理残差，再把结果放入冻结的 75D range 做一次范围修正。W13A 只比较当前 W5 组合的 beta=1.0 和 beta=0.5，严格按 beta=1.0 → 释放 store → beta=0.5 的顺序运行；旧的 bare beta=0.5 失败路线没有重开。它是 action-only diagnostic，不是 KSP、PDE、DtN、field 或 RTA。

run1 在结果序列化时遇到 `numpy.bool_`，beta=0.5 未启动；run2 的 beta=1.0 完成后，beta=0.5 被旧 beta=1 guard 拦截。两次都保留为 execution boundary evidence。run3 是修复后的完整 W13A diagnostic：process-tree peak `1,717,895,168 B`，`/usr/bin/time` MaxRSS `1,695,490,048 B`，swap `0`，termination 为 `null`，drain gone，compiler descendants 为空。运行前 prediction `1,726,081,915 B` 是 derived，不是 measured，也不是最终 PDE peak。

W13B 的固定资格门是 beta=0.5 的 projected rho 必须不超过 beta=1.0 的 `95%`，即至少改善 `5%`。这个门用于判断是否值得再投入一次固定 200 步 screen；它不是 PDE 通过条件。run3 raw 的两组测量和独立重算为：

| residual | beta=1.0 projected rho | beta=0.5 projected rho | beta05/beta1 | 相对改善 | 5% 资格门 |
|---|---:|---:|---:|---:|---|
| W5 iter200 | `0.9995565651228495` | `0.9940090684868385` | `0.9944500423191865` | `0.005549957680813455`（0.5550%） | fail |
| W7 cumulative400 | `0.9999083283541277` | `0.9937069526556399` | `0.9937980557590761` | `0.006201944240923907`（0.6202%） | fail |

两组 beta 的 range-only rho 差都是 `0.0`，通过 `<=1e-12` 的 cross-beta identity；child 的 finite、repeat、closure 和计数也通过。但两组 residual 的改善都只有约千分之五到千分之六，远低于预声明的 5% 门，因此 W13B_FIXED_200_STEP_SCREEN 锁定，不应继续花费一次 200 步 screen。W13A 的 action-only 峰值不能冒充 full PDE 资源证据；full time-harmonic PDE、official field/RTA、direct-authority physics comparison 和最终 `<2,000,000,000 B` PDE 测量仍为 `not_run`。

W13A 的独立 compact 证据为 [`m6b_w13a_projected_range_composition.json`](../../benchmarks/cases/101_task37_extra_development/records/m6b_w13a_projected_range_composition.json)，保留旧 raw/watchdog 只读并逐文件绑定 SHA。

## W14A–W18A：统一 action-only 收口

W14A–W18A 都是“先构造一个候选修正方向，再用物理 action 检查它是否真正降低冻结残差”的诊断。它们没有求解完整时谐方程：没有 physical KSP、没有 PDE、没有场恢复，也没有 official R/T/A。辅助内层 residual 小，只能说明辅助方程近似解得较好；最终是否有用仍由 physical `rho` 和预声明 Gate 决定。

| 路线 | 方法与关键实测 | 状态和边界 |
|---|---|---|
| W14A | 两次 global coercive B0 inner-PC；physical rho `0.8943645606070599`；prediction `1,281,057,286 B`；peak `1,158,553,600 B`；swap `0` | action/resource closeout 通过；不是 PDE/RTA |
| W14B | fixed4 rho `0.8943645606070647 → 0.869374076266045 → 0.8681485457234316`；inner4 residual `0.01751006766159766 > 0.01`；peak `1,185,300,480 B`；swap `0` | `W14B_FIXED4_CORRECTION_FAIL`；W14C locked |
| W15A | inner residual `0.00499608724120203`；local/cumulative rho `0.9993168124994211 / 0.8937535419182971`；peak `1,162,047,488 B`；swap `0` | `W15A_RESTART1_NUMERIC_FAIL`；W15B locked |
| W16A | shifted volume-only beta=1 inner residual `0.061153888358888554 > 0.01`；physical rho `0.8806019129260008`；peak `1,395,236,864 B`；swap `0` | inner Gate 失败；W16B 只作为后续候选 |
| W16R | fixed restart20+20；两次 inner residual `0.008234328428613968`；physical rho `0.8814092210776835`；peak `1,398,456,320 B`；swap `0` | action-only 通过，解锁 W16B screen；不是 PDE |
| W16B | 两次 outer-2 screen；rho1 `0.8814092210776882`，rho2 `0.8796856414991869`；inner final `0.008234328428613734 / 0.003015056986064362`；peak `1,557,839,872 B`；swap `0` | rho1 anchor 通过，但 rho2 `>0.8660254037844386`，数值 Gate 失败 |
| W17A | beta=1 shifted volume + 同一 matrix-free DtN80；两次 fixed40 重复；physical action 两次 | cycle20 `0.21437006185665625`；cycle40 `0.12567225369307264`；physical rho `0.8917790380896942`；peak `1,524,117,504 B`；swap `0` | `W17A_GLOBAL_PHYSICAL_SHIFTED_NUMERIC_FAIL`；W17B locked |
| W18A | `B=S(beta1)+T` 的 nested auxiliary outer-2；每个 PC 为 fixed40；physical `A=beta0+T` | inner finals `0.008234328428613734 / 0.012917460577236278`；outer residuals `0.09956749409891383 / 0.03857856488992854`；rho `0.8814092210776835 / 0.8918283239976347`；peak `1,546,248,192 B`；swap `0` | `W18A_NESTED_AUXILIARY_NUMERIC_FAIL`；physical screen locked |

W16B 的唯一正式 run 自然完成，repeat identity 通过，资源侧 peak 和 swap 也通过；但历史 v1 compact 的正式分类仍原样为 `W16B_EXECUTION_OR_EVIDENCE_FAIL`。原因是旧 checker 对 W16B 错误期待 `observer_count=1`，而 raw 中四个 cycle 的真实值都是 `0`。当前窄修复只是让共享 fixed-20 audit 接受显式的 `expected_observer_count`：W16A/W16R 保持默认 `1`，W16B 传 `0`；没有改变数值路径，也没有重写 compact v1。compact 当前 file SHA 为 `1f59bdca7abc09ce6385f25b145f97a41f2b3e995b377855267d326bac37056d`。这个 checker 分类问题不能掩盖 rho2 的明确失败，因此 W16C 和 outer4 都不运行。正式 raw/compact 的 W16B rho `0.8796856414991869` 与本轮 dense-vdot 离线重算 `0.8796856414991874` 的绝对差小于 `1e-15`，是浮点累加/运算顺序差异，不是两次实验。

W16B raw 的离线几何为 `||r0||/||r1||/||r2|| = 1.6023954272 / 1.4123661053 / 1.4096042493`。第一步下降约 `11.8591%`，第二步仅下降 `0.19555%`，`r1/r2` alignment 为 `0.9980445183`。若要求 outer4 达到 `rho4<=0.75`，后两步的累计 reduction factor 必须 `<=0.8525772897`，等效每步至少下降 `7.6649%`；按当前第二步趋势，rho4 约为 `0.8762485870`。因此不盲跑 outer4；这只是读取已保存 NPY 的离线几何诊断，没有生成新的物理 action。

W17A 的唯一正式运行自然完成，worker RC1、checker RC1，均不是 timeout、RSS stop 或资源失败；所有 formal checks 除 `worker_action_gate` 通过，worker checks 仅 `inner_residual` 和 `measurements` 失败。两次 z/p hash exact，relative difference 为 `0`，closure 为 `0`，orthogonality 为 `6.533554203970653e-17`；action 计数为 `86/86/80/80/166/86/2/2/88`（global auxiliary/global shifted/local PC/local exact/shifted total/auxiliary DtN/physical volume/physical DtN/total DtN）。本轮唯一结构变化及对照支持的主要根因边界/推断是：auxiliary 加入 DtN80，而 local PC 仍为 shifted volume-only，二者的边界/modal 子空间处理存在失配；这不是尚未完成 modal decomposition 的数学证明，不通过增加步数掩盖。

W17A 的 raw summary SHA 为 `7cfe7e7f176b3332b9a4fb52e62d58ba71b75eca04c990d558c4819f3b32f9bb`，watchdog SHA 为 `57221408de7e0673e7865833f83c85b3cf11ddc4e7c30adb2318df7b47ad8d42`，现有正式 compact file SHA 为 `37a67d5e2a7c55a5548357f073b740801742691b72cc405f6b2355f22bc5dd92`，embedded evidence SHA 为 `a72b174a8984c9cec44137ff08b921aa89e937b4d5cc269e3d528492f84cf983`。prediction `1,701,623,030 B` 是 derived，不能冒充 measured PDE peak；17/17 marker、swap0、compiler descendants 为空且进程清理完成，只说明 action-only 资源证据闭合。

## W16B + W17A 二维离线 span 诊断

这项诊断只读取已保存的 W7 cumulative400 residual、W16B checkpoint NPY 和 W17A z/p NPY，不生成新 action。单方向投影使用 `alpha=(p^H r)/(p^H p)`，二维空间使用 `G=P^H P`、`h=P^H r`、`c=G^{-1}h`。独立重算得到 W16B rho `0.8796856414991874`、W17A rho `0.8917790380896956`、二维 rho `0.8781945094815413`；正式 raw/compact 的 W16B 记录 scalar 为 `0.8796856414991869`，与 dense 重算绝对差小于 `1e-15`。冻结的 blockwise normal-equation closure 为 `3.750159823210426e-15`，本次 dense 线性系统 closure 为 `1.2724784801792792e-16`；二者都低于 `1e-11`，差异来自浮点累加/运算顺序。`cond(P)=15.48530644048902`，归一化列对齐绝对值 `0.9657478231415315`。加入 W17A 方向只改善 `0.0014911320176460574`（约 `0.1695%`），二维 rho 仍高于离线门 `0.85`，所以 W16B+W17A span lane 关闭，不 formalize、不解锁 W17B。

W16B 的 `r0/r1/r2` 范数为 `1.6023954272 / 1.4123661053 / 1.4096042493`；第二步只下降约 `0.19555%`。要靠后两步达到 `rho4<=0.75`，剩余累计因子必须 `<=0.8525772897`，等效每步至少下降约 `7.6649%`；按当前趋势外推 rho4 约 `0.8762485870`，因此不盲跑 outer4。完整 hash-bound derived 记录见 [`m6b_w17a_w16b_span_diagnostic_v1.json`](../../benchmarks/cases/101_task37_extra_development/records/m6b_w17a_w16b_span_diagnostic_v1.json)，明确标记 `derived/offline_diagnostic/not_PDE/not_action_run`；文件 SHA 为 `cd21be1be0ee5c1847501e9ba10b520ad7254b81bbb71663ea25920b9c78c827`，embedded evidence SHA 为 `b9e25a9a1ef198694d95dc88d5eb761a548aedd143399dd0482d2066c890978d`。

full time-harmonic PDE、official field/RTA、direct-authority physics comparison 和最终 `<2,000,000,000 B` 的 PDE process-tree 测量仍为 `not_run`。action-only peak、derived prediction 和历史 checker 分类都不能替代这些未完成的 PDE 证据。

## W18A：nested auxiliary action-only 正式负结果

W18A 的 nested auxiliary 是一种两层方向测试：外层每一步先调用固定的辅助近似逆，再把方向交给物理 action 检查。它不求解完整 PDE。辅助算子固定为 `B=S(beta1)+T`，其中 `S` 为 beta=1 shifted volume action，`T` 为共享 matrix-free DtN80；每个辅助调用为 fixed40。物理检查使用 `A=beta0 volume+T`。本路线没有 physical KSP、场恢复、R/T/A 或 physical screen。

| 项目 | W18A 结果 | 结论 |
|---|---:|---|
| producer / checker source | `839ce6733db2dc737f5c8bfb6347633f53161d82` / `26ea955690b1541c2bd43856799508bc85ffe1e6` | 同一 raw 的独立 checker v2 |
| classification | `W18A_NESTED_AUXILIARY_NUMERIC_FAIL` | `problems` 仅 `worker_action_gate` |
| inner finals | `0.008234328428613734 / 0.012917460577236278` | 第二个 `>1e-2` |
| outer residuals | `0.09956749409891383 / 0.03857856488992854` | 均未达 `<=1e-2` |
| physical rho | `0.8814092210776835 / 0.8918283239976347` | rho2 `>0.85` 且比 rho1 更差 |
| repeat / closure | z、outer action、p exact；relative `0`；normal closure `0` | 重复与闭合通过 |
| orthogonality | finite，约 `4.66e-16 / 3.73e-16` | 通过 |
| measured peak / swap | `1,546,248,192 B / 0` | 仅 action-only 资源证据 |
| prediction | `1,734,993,014 B`，derived | 不是 PDE 实测峰值 |

v2 顶层共 23 项 checks，其中 22 项为 true，唯一失败为 `worker_action_gate`；worker 的 `inner_residual`、`outer_auxiliary_residual` 和 `measurements` 是实际数值失败，其余证据、执行和资源 checks 通过。精确 action 账本为 `outer_auxiliary/outer_pc/inner_global_shifted/local_pc/local_exact/shifted_total/auxiliary_DtN/physical_volume/physical_DtN/total_DtN = 8/4/172/160/160/340/8/4/4/12`。

v1 因 checker 对真实 production audit 的动态字段和 descriptor 形状作了错误假设而误判，原文件完整保留但不作为权威结论；v2 重新绑定同一 raw/watchdog 并独立复核真实数组、audit、scratch 和资源，因此 v2 是 W18A 权威结果。v1/v2 证据如下：

| 证据 | 路径 | SHA |
|---|---|---|
| raw summary | `benchmarks/artifacts/task037_extra_development/m6b_w18a_839ce67_formal_run1/m6b_w18a_summary.json` | `a82fb01c60b48575c2df59649375e3d330f85ba3edf43f1bd59c84bb2b29a4b5` |
| watchdog summary | `benchmarks/artifacts/task037_extra_development/m6b_w18a_839ce67_formal_watchdog_run1/w18a_watchdog_summary.json` | `a32275d426cfe826f80be46dc8fbeba481e5bd8047589454f77b77b7c7a953eb` |
| v1 compact | `benchmarks/cases/101_task37_extra_development/records/m6b_w18a_839ce67_formal_resource_closeout_v1.json` | `0c86b687fd76f366bd9148fec734794fdf21b2a3d0bf300fc502981cb48c210f` |
| v2 compact | `benchmarks/cases/101_task37_extra_development/records/m6b_w18a_839ce67_formal_resource_closeout_v2.json` | `3d9110cf7127333b676e96c5e7dd5cace23ecadc30127063d7f87171d510eb61` |

本轮主要根因边界是：`B` 的 nested solve 显著改善了辅助 residual，但产生的方向与 physical `A` 的校正不充分对齐。当前证据不支持把失败归因于 timeout，也不支持仅靠增加同一路线步数解决；这不是 modal decomposition 的数学证明。PDE、RTA 和 physical screen 继续锁定。下一步只允许先对已保存的 W18A `p1/p2` 做离线二维 span 诊断（0 action、0 PDE），不盲目重跑或延长 fixed40；该诊断尚未运行。
