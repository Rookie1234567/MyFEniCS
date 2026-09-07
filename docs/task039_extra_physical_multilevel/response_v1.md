# Task39extra Response V1：本机性能停止与 A5 集中审阅

| 交付身份 | 内容 |
|---|---|
| 分支 / base | `task39extra` / `2dc2e7305f10dc391a13970c6f0f0340cb87b6ee` |
| 唯一 A2R 正式源码 | `54ab46cf4c8378a9b27650ca6963cadb34013a2f`；运行前 clean，parent 的 source_after 亦通过 |
| 最后代码提交 | `adc448814c3022fdf6d1a688da69a28238e7db9c`，事后成本计数窄修；最终文档提交 SHA 由交付回复报告，避免文档自引用自身 SHA |
| 当前交付阶段 | 本轮 A5 收口等待集中审阅；最终文档 HEAD、upstream、同步状态由交付回复给出 |
| 本机结论 | `PERFORMANCE_CONTROLLED_STOP`，未满足主候选或 reference-only 成功移交状态 |

A2 主候选用 p4 原物理方程的有限迭代解修正 p6；其内部 shifted 方程只辅助中间求解。A2R 则用同一原 A4 的稀疏增广直接分解提供准确中间逆，额外付出装配与内存成本。保留原 A6、80 modes、传递、S6 pre/post、三个 MR 方向及 right FGMRES32/max512/zero start。MR 是沿一个方向选择复步长以减少当前残差，并不保证空间足够；不能用单 PC 残差不增宣称外层鲁棒。

这不同于 V17 的 p3 单位步长 coarse 修正、V18 standalone positive pMG、Task040 bare-F 和 V19 PML 双扫；本轮没有自动切换这些路线。旧 S6 优化只省掉取得精确对角时不需要的单元耦合，原积分与复杂约束保持。

| 实际运行 | 结果 |
|---|---|
| 旧 A2 setup | 用户 setup 受控停止；workflow 5946.465141321009 s；outer 未开始 |
| 优化后 A2 | 用户按成本停止；workflow 3015.3758775380556 s；7 完整 PC 各 36 inner 步，A4 残差 0.636–0.847，未达到中间目标 1e-2；第 8 partial |
| A2R 测量前入口 | adapter_unavailable，0.014696567959617823 s；遗漏 public profile 登记，修复及 3 个轻量回归后重新从 public 启动；未消耗 reference numerical 次数 |
| 唯一原尺寸 A2R | 一次 symbolic/numeric；163 reference RHS 各通过原 A4 1e-10，最大 5.7889315844880267e-11；solve 3600 s Gate 真实触发 |

A2R 外层第 32/64/96/128/160 步原 A6 真残差分别为 0.46338436888430473、0.41005441732961595、0.3139861672303239、0.2753887167051727、0.18250767622880507，均大于 1e-6；reported/explicit 对照通过。163 完整 PC、第 164 仅 positive_pre_started；没有停止瞬间最终残差，不把 160 checkpoint 冒称 163/164 结果。

workflow 4451.728501909005 s，parent 4451.582956286031 s；RSS peak 3588677632 B、swap 0，16993 RSS 样本均可读；PSS 最大可读值 3554077696 B，1 个 PSS 样本不可读。动态 cap 8736759808 B。parent 及已观察后代共 62 PID 清场、cache metadata 稳定。正常 worker summary 与 release/recovery/checker completion 缺失，不能宣称完整正常释放或物理输出通过；原 raw 不改。

成本 bug 仅影响汇总：旧 cycles 把 S6/S3 生命周期序号求和，五周期错误字段原样保留；从 pc_applies 重算每个 32-PC 周期各 64 次，总 163 PC 各 326 次。末 partial 不补算。未来 runner 修正此计数，checker 独立重算；最后 wiring/public/cost 轻量回归 19 passed（0.85 s），未因此重跑 PDE/FE。没有 full repository pytest 或 CI 通过声明。

原 p4 直接逆的资源与残差可行，但外层没有在本机预算内成功。这不能判定整个 p4 空间或 Full3D 迭代数学不可能，也不能凭中间逆通过授予 REFERENCE_ONLY_PASS。A3 非可分、A4 h5/独立 reference、official R/T/A/E/H/衍射级/A_volume、5 nm 和 0.7 nm 全部 not_run。

请 review 决定下一项机制比较与工作站阶段条件；本轮不扩预算、不换 PC、不增加 heavy。p1 的 4096 rows/512 MiB 底层限制仍保留，需要扩展时应资格化有界或分布式底层，而非取消限制。

完整表格、分阶段耗时、物理/模式/ABI 身份、源码及所有 raw hash 见 [summary](outcomes/summary.md)、[run_index](outcomes/records/run_index.json)、[test_summary](outcomes/test_summary.md)、[workstation_handoff](outcomes/workstation_handoff.md)。移交包含依赖分组及 2 TB/0.7 nm 的条件路线，当前仅为机制证据移交准备。
