# V7 bounded inexact outer：J1 控制证据与 J2 准备

本页是新的短证据页，不覆盖旧 V5/V6 结果。J1 只验证有界内层和成本控制；它不是正式 Full3D 外层求解，也没有产生新的 R/T/A、`A_volume` 或官方场输出。

| 项目 | 结果 |
|---|---|
| profile / 输入 | `bounded_entity16_v7`；13.5nm、p6/h10；输入 SHA `bcad5afe41adb16ee3753b3e7a2a2379d069bd2c8ddd25fb1311d77eae78307a` |
| J1 source | `874190e92e0f0639515715dd830cd275562c151f`，branch `task39extra`，ahead/behind `0/0` |
| J1 控制 | `J1_CONTROLS_COMPLETED`；1 次 setup、2 个完整 PC、4 个 I4 |
| I4 合同 | 每 PC 两个独立零初值 FGMRES16；target `1e-4`、soft `25 s`、hard `30 s`；有限 approximate return 合法，zero-RHS 单独合法 |
| 实际 H6 | **每个实际 PC 1 次 H6 smoother**。`positive_setup` 中继承的 H6=2 只是不适用的旧 metadata，不能用于计数判据 |
| J1 PC 时间 | A2R160 `44.268986623 s`；LIGHT448 `44.617366049 s`；均低于 `90 s` |
| J1 资源 | process-tree simultaneous RSS peak `1,507,594,240 B`；tree swap peak `0 B`；global swap delta `0/0`；watchdog conservative `293.380370661921 s`，outer ledger `293.408546875 s`；后代已清场 |
| J1 结论 | 两个 PC 的输入/数组/约束/有限性通过；inexact closure relative 分别 `7.436825933731343e-12`、`7.828053877249895e-12`，限值 `1e-8` |

J1 四个 I4 的 `final_true_residual` 为 `0.1688399730328266`、`0.008956127391392074`、`0.30047937256888035`、`0.010039186157406508`。这些是受 16 步上限返回的 inner approximate 结果，不能写成 `1e-4` 通过；J1 也没有把它们串成外层收敛结论。

本轮新增独立 checker 会从 `bounded_i4.jsonl`、`pc_applies.jsonl`、`bounded_exit_audit.jsonl`、外层 monitor 和 iterations 原始行重算：I4 norm/cost、每 PC 的 I4/H6 次数、首次/每 32 PC/exit closure、B4/S/MatSolve/audit lifetime counter（先减 setup baseline）、V7 8-step screen、128-or-1800 gate、5400 gate、10800/max2048/one-KSP 合同。成功仍消费既有 `BALANCED_OUTPUT_PASS`，不会新增结果状态；原有 V5 `.65` screen 路径不变。

## J2 入口（尚未运行）

J2 使用零初值 profile 默认值和同一个共享 batch ledger；不要另建 ledger 或把 setup/solve 嵌套时间重复收费：

```bash
source scripts/activate_myfenics_wsl.sh
export GIT_DIR="$PWD/.git-codex" GIT_WORK_TREE="$PWD"
python scripts/run_case.py input/task39extra/original_13p5nm_p6h10_bounded_entity16_v7.dat \
  --batch-budget-ledger benchmarks/artifacts/task39extra/v7_j1_controls/j1_budget.json
```

J2 资源合同为 workflow reservation `14400 s`、solve `10800 s`、outer FGMRES32/max2048/zero-start/one live KSP；必须保持专用 watchdog launch cap、全局 swap delta 为零、一次只运行一个 heavy case。共享账本在 J1 后为 `charged_seconds=593.408546875`、`remaining_seconds=42606.591453125`；本轮只准备入口，未预留或扣除 J2 费用。

## 证据索引

J1 根目录为 `benchmarks/artifacts/task39extra/v7_j1_controls/874190e92e0f0639515715dd830cd275562c151f/controls`（大型目录保持 ignored）。紧凑机器记录见 [bounded_inexact_outer_v7.json](records/bounded_inexact_outer_v7.json)。关键文件 SHA 在该 JSON 中逐项绑定；`j1_controls_summary.json` 的 SHA 为 `8106617b54b8ba49ce4a8f0b4a6326c6686704ceb0933387a1cd43ce93b58daa`。

本轮 targeted checker/schema tests：`6 passed`，pytest自身 `0.07 s` / 测试进程 wall `0.19 s`，最大 RSS `44,320 kB`；测试运行在 `874190e92e0f0639515715dd830cd275562c151f` 之后的未提交工作树，不应写成 clean `874190e92e0f0639515715dd830cd275562c151f` 执行；未启动 FE、MPI 或正式 PDE。
