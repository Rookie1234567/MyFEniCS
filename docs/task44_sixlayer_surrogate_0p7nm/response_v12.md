# Task44 Response v12：train_008 r2 离线收口

本轮完成 train_008 r2 的离线数值、输入身份、场/模态产物和资源核验，并按主控批准登记为 `qualified_v2_training_label`。该标签只绑定冻结的 P6 离散输入，不表示连续解精度、全厚度范围精度或 GP 泛化。`sample_design_v2.json` 仍保留运行前的 `planned_not_run`，没有回写。train_008 只计一个样本；r1 监控失败作为独立历史 attempt 保留。

## r2 核验结论

- 固定身份：source `586e270a5c79843f6ac2c8f610859f31d430ef42`；input SHA `6811ad334385feb0dea923a45e6db4b69d23f99650bdf8ad617cb4b7ea9e47c8`；physical SHA `ba742e6b430791bcc11ad1a6c88d36587a27e40b1a9f8e89d44226149f653978`；discrete SHA `19a726fc988bf9a476f6d710494098a28919642319e864ff70bbdb5e129802e2`。冻结六层厚度 `[0.6473146639177918, 0.8213074950648702, 0.5039836493852932, 0.8268139783059176, 0.7068539593525944, 0.5963325482191442] nm`。
- 数值门：`R_total/T_total=0.09760520879370416/0.8799314234420694`；`R00_s/p/total=0.09760480197859493/9.268408819992147e-23/0.09760480197859493`；`A_balance/A_volume=0.022463367764226416/0.022463367826854663`。full true relative residual `1.7907571605784237e-9≤1e-6`，`R+T+A_volume−1=6.262834695291986e-11` 且绝对值 `≤1e-5`。160 模态独立聚合与端口功率记录一致；所有场 NPZ 数值数组有限。
- 生命周期与成本：r2 service/watchdog `COMPLETED`，leader exit `0`，后代清空，无 stop event；service Invocation `0e92875cde1a48d1b20cd9f88c03fa4b`。service start `2026-11-02T03:51:56Z`；worker `03:51:58.552205Z–05:12:47.414410Z`，`4799.974475 s`；service wall `4863.370071 s`。P6 `[3,12,8]`、288 hex、MPI1、MUMPS exact；197,994 DoFs、59,776 rows、48,629,752 used NNZ。cgroup peak `13,886,492,672 B`，低于 128 GiB cap；zero-swap gate pass，swap `0 B`。
- 文件与哈希：manifest `39707e4b6da5fa673d480eade08c4fa1c1e0edf7c69266e433bcbe3c7b75a8d7`；numerical summary `ca5dbdd9e196958f21add1c8d2b655f78cdf07beaa0300e6bd346300e76bd450`；service summary `eadeadc69256ebf2b40d8b110bdec3888bfdc772a02187edc30b9e6a86f3e88a`；field NPZ `f5ecf602d2e6b8b05bfd33a008df368212204a449f3f1a6dce90cff75260e06a`；modal NPZ `7509fb74bc2e3b3790e148e943a8815826314d8eb7e5abcfd7ebbf0e77155b9f`；port-order JSON `74f95ca314c21c186f930e9b509864f3d93858dfa93116599ec624a03750bbbb`；auxiliary JSON `d4334d9a4a5682745f95b1f7ef5096c217463efdf43c99fa34b81a69d084487a`；port-power JSON `2ae9c10123daf6690cbda042942ad2050e554a179a16b26a359bd9a7a80c4b77`。派生 identity-difference receipt `125dc9ca5ddd6c7b773e94dc3eead939611eaf1093195ba5dce5ca0d27032696`。

## 保留的身份覆盖缺口

904 条资源快照中的身份字段均完整、状态可读；service 报告 3,696 次进程树身份采样。将 service summary 的 observed child identities 与 watchdog `members` 行对账后，37 个 live child identity 只有 36 个成员身份匹配。唯一差集 `(PID 499189,start_ticks 352129672)` 只在 elapsed `4787.653536661994 s` 的 `live_or_unreaped_children` 列表出现，没有直接 member 记录；其角色、状态/Tgid 与 per-PID RSS 均未知。原始 coverage flags 仍为 `incomplete_or_not_sampled` / `incomplete`，进程树 RSS 只作为采样峰值。主控接受该历史缺口已披露情况下的数值标签登记；它不被写成 monitor coverage complete。

## 并行授权误读与范围

我把用户此前对并行等待问题的“按并行授权立即启动”错误套用到一个已过时的提问上，并因此启动了 train_008 r2。主控指出该回复早于 formal runs 010/011，不是对其后新提议的授权。我已如实记录这一误读；r2 的数值记录和原始分类没有因执行授权误读而改写，主控按既定数值门独立审阅后批准了标签。此后按主控指令，没有启动 train_009 或其他后续 PDE，也没有改动 production monitor、源码、冻结设计或原始数值输出。

本轮仅做离线文件对账和 outcome 文档更新；没有运行测试。train_010 的 monitor root cause 仍未解决，stable-R/direct-membership 诊断继续限制为无 PDE。
