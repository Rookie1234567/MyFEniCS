# Task037c response_v2：授权研究扩展最终资格化

## 1. 结论

`response_v1.md` 保留原 `6555663`、scalar traction、max_it=1600 冻结阶段的负结果，
不在本文件追溯改写。其结论 `M_robust=not_established` 仅作为原冻结阶段历史结论仍成立；
授权扩展有独立的 M 选择。

用户随后明确授权的 research extension 绑定 numerical code/config SHA
`f2d7719b6253251a06e8cd8388fd443bbf47d443`，采用：

- `full3d_one_cell_exact_schur`：用 10 nm 真实三维 H(curl) 单元端面 Schur 通量替代
  非零方位角下的 scalar-CG traction；
- fixed two-pass side correction：复用原 ILU(0)+40-mode Woodbury，固定做一次残差修正；
- M120、restart90、zero initial、rtol=`5e-9`、max_it=`4500`。

```math
z_1=P r,\qquad s=r-A_{side}z_1,\qquad z_2=z_1+P s.
```

三角度 MPI8/MPI1 数值与 identity 均通过，最终限定分类为：

```text
TASK037C_S_POL_1DEG_AZIMUTH_ROBUSTNESS_PASS_UNDER_USER_AUTHORIZED_RESEARCH_EXTENSION
```

这不是原任务默认能力，也不是 `production-qualified` 结论；ordinary defaults、原阈值、
原 scalar 路径和原 response_v1 均保留。

## 2. 根因与两项修复

原 max_it1600 阶段的失败分为两层：非零 phi 的 direct Hybrid 在 11 个低功率显著 order
通道上超出冻结 relative Gate；随后 M160 solver-vs-direct diagnostic 的 modal residual
已约 `1e-15`，但 bottom/top FEM residual 停在 `1e-4`--`1e-5`。证据指向 scalar-CG
traction 与真实 p6 H(curl) one-cell conormal 不一致，以及固定端盖近似逆的收敛瓶颈，
不是 comparator bug 或 M 容量不足。

研究扩展只做两项窄修复：exact one-cell Schur 提供真实端面 coupling；two-pass 对已有
固定侧向作用执行一次确定性 residual correction。它不增加 restart 空间、不引入新 PC、
不使用 warm start/continuation/fallback，也不改变 ordinary defaults。

## 3. MPI8 三角度表

`I120` residual 顺序为 reported/global/bottom/top/modal；direct 和 Full3D 报告可得
true residual。忽略目录中的 raw watchdog 路径以反引号代码形式保留，后接完整 SHA256；不伪造
GitHub Markdown 链接。

| phi | 方法 | raw watchdog / SHA256 | R / T / A / A_volume | residual / iterations | RSS MiB | total wall(s) | Gate |
|---:|---|---|---|---|---:|---:|---|
| 0° | Full3D | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/final_f2d7719/r2_full3d_phi_0/watchdog.json` / `586fbfb76d8aea7bad0f93e344f1b1e9207ec1c7043ed03fff0641338139fa6f` | .365625789179 / .012990632411 / .621383578410 / .621383578414 | `6.770520252e-11` | 15374.609 | 257.409715 | pass |
| 0° | direct M120 | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/final_f2d7719/r3_direct_phi_0_m120/watchdog.json` / `4fe81c2414a8eab57e7f33127ade3b52ed21bcad3caddd4884c2e7988bec1ca6` | .365625789179 / .012990632411 / .621383578411 / .621383579539 | `5.765468683e-11` | 7693.633 | 449.431714 | own pass |
| 0° | direct M160 | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/final_f2d7719/r3_direct_phi_0_m160/watchdog.json` / `c3722bf0e509ea5d60f5a04b14a36b7df0bd643beeaf3a2808615bc42e3aeac1` | .365625789178 / .012990632411 / .621383578411 / .621383579529 | `3.103124270e-11` | 8124.754 | 533.128482 | own pass |
| 0° | iterative M120 | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/qualification_f2d7719/r4_two_pass_phi_0_m120_maxit4500/watchdog.json` / `4cda183aa23edff5fab927923b681bb158e3aecf165b741f7aaea5840fa83012` | .365625786729 / .012990632358 / .621383580913 / .621383576626 | `3.061697359e-9 / 3.061697811e-9 / 4.880057389e-9 / 2.428280376e-9 / 2.974757976e-15` / 1771 | 6542.090 | 1041.404664 | pass; RSS preferred fail |
| -5° | Full3D | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/final_f2d7719/r2_full3d_phi_m5/watchdog.json` / `dda0fd57d0f335f4cf87a6d1fee4dc59cb4541ec42fae8538048108fff345ab3` | .365595712018 / .012994030264 / .621410257718 / .621410257720 | `9.001849713e-11` | 15248.820 | 230.831346 | pass |
| -5° | direct M120 | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/final_f2d7719/r3_direct_phi_m5_m120/watchdog.json` / `f5f74dd0ad68326cc30fa4e74395e5fc4809bfe52ce97518f19d7d9d82dbd1f5` | .365595712014 / .012994030264 / .621410257722 / .621410258879 | `7.449018674e-11` | 7481.434 | 421.923375 | own pass |
| -5° | direct M160 | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/final_f2d7719/r3_direct_phi_m5_m160/watchdog.json` / `17130b066f60f18329cf3221441e0ac96b72a6a0281ed09801bdc58fd63430bb` | .365595712013 / .012994030264 / .621410257724 / .621410258872 | `1.159358963e-10` | 8002.000 | 494.679228 | own pass |
| -5° | iterative M120 | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/qualification_f2d7719/r4_two_pass_phi_m5_m120_maxit4500/watchdog.json` / `2012bf0559aeeff1daf60b880d96b2e80ffc93aa16c44f0ea117d262f781435f` | .365595709120 / .012994030376 / .621410260504 / .621410260826 | `3.163761941e-9 / 3.163758891e-9 / 4.990863541e-9 / 2.512393573e-9 / 2.915153589e-15` / 3945 | 6623.156 | 1738.933491 | pass; RSS preferred fail |
| +5° | Full3D | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/final_f2d7719/r2_full3d_phi_p5/watchdog.json` / `02e5b7ea3cd62f6bbbc80de1e9e2e6c61035a776c0c36c812c380428aa1eafd3` | .365595712019 / .012994030264 / .621410257717 / .621410257720 | `4.905910037e-11` | 15124.184 | 245.132864 | pass |
| +5° | direct M120 | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/final_f2d7719/r3_direct_phi_p5_m120/watchdog.json` / `af2fd5516a9266058898c9e4fccf9e3245094ca9153a2c1c601a99b58f041b72` | .365595712014 / .012994030264 / .621410257723 / .621410258880 | `4.543355137e-11` | 7550.172 | 422.165235 | own pass |
| +5° | direct M160 | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/final_f2d7719/r3_direct_phi_p5_m160/watchdog.json` / `e1f600ba4728291208b2e6a8270b5a6acc87f61043dba1b69154aaba22bb5b4b` | .365595712013 / .012994030264 / .621410257723 / .621410258871 | `3.905341864e-11` | 8015.836 | 493.817763 | own pass |
| +5° | iterative M120 | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/qualification_f2d7719/r4_two_pass_phi_p5_m120_maxit4500/watchdog.json` / `7f12d20772bc172717f7affc6e15d4ec0dbfb3f6360008615187e5b4b532db17` | .365595709299 / .012994030228 / .621410260473 / .621410256101 | `3.429167916e-9 / 3.429170083e-9 / 4.847417910e-9 / 2.754454324e-9 / 3.151359880e-15` / 2832 | 6475.238 | 1356.707269 | pass; RSS preferred fail |

MPI8 三角度 Full3D、direct M120/M160、iterative M120 的 own Gate 与同 phi comparator 均通过。
Hybrid iterative 的 6144 MiB preferred 资源 Gate 三角度均未通过；这是资源结论，不是数值失败。

资源口径：Full3D 与 iterative 列是 process-tree peak；direct 列是各自 watchdog 的
`max_simultaneous_worker_rss_mb` 字段。表内保留这一差异，不把它们冒充完全同一采样字段。
授权扩展下 9 份 M120/M160/Full3D comparison 全部 pass，因此本扩展的 `M_robust=120`；
这不同于上一阶段历史 `M_robust=not_established`。

## 4. MPI1 资源表

| phi | raw watchdog / SHA256 | online SHA256 | iterations | residual max / modal | R / T / A / A_volume | RSS / total wall(s) | resource |
|---:|---|---|---:|---|---|---|---|
| 0° | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/qualification_f2d7719/r6_mpi1_two_pass_phi_0_m120_maxit4500/watchdog.json` / `cc14c7333409cd94d34d866fd7d6d9a5d8674a81dcb43143c595f66e07d7c25f` | `251294fdf15653a57ac9cd2f6fc073448d165e72bc9d7c0ec44376018235add4` | 1472 | `4.953887173e-9 / 2.452093037e-15` | .365625794231 / .012990632482 / .621383573287 / .621383578463 | 1751.320 / 1903.921641 | engineering; preferred fail |
| -5° | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/qualification_f2d7719/r6_mpi1_two_pass_phi_m5_m120_maxit4500/watchdog.json` / `c87b2439073c7245b6fc1fec64d2d6ee7548439060d4bbf33c2254171ccffe6b` | `963a9f40c293c6b653d3a87a716548f32425d44cb94ade4c3d7d4236a78a75ad` | 2160 | `4.845818350e-9 / 2.135024973e-15` | .365595714284 / .012994030084 / .621410255632 / .621410254316 | 1662.109 / 2194.594255 | engineering; preferred fail |
| +5° | `/home/Projects/MyFEniCS/benchmarks/artifacts/task037c/qualification_f2d7719/r6_mpi1_two_pass_phi_p5_m120_maxit4500/watchdog.json` / `a7eb581f6dfcb042a65855dc7d113aba2c56246a8d1865a3221d3d95ec6521f3` | `93bcfcdbde5d5c571fed3325ecf0f8db19b02788901eccb1018402002ee38149` | 3338 | `4.999743003e-9 / 2.026232764e-15` | .365595710967 / .012994030395 / .621410258638 / .621410262566 | 1744.570 / 2777.664623 | engineering; preferred fail |

MPI1 的 preferred=1536 MiB、engineering=2048 MiB；三角度均为 engineering pass、preferred
fail、swap=0。MPI8/MPI1 identity comparator 三份均通过。

## 5. 测试与提交

第一次 full pytest 在 style HEAD `9a51a76e44d43e9f35e545f6dc9a442f25bfb08d` 上为
`974 passed, 48 skipped, 1 failed`，1330.53 s，exit 1。失败是
`test_task036_hybrid_interface_semantics.py` 的 legacy `SimpleNamespace` 缺少正式
`modal_traction_model` 字段；日志 `/tmp/task037c_r7_full_pytest_9a51a76.log`，SHA256
`d14b92f0612f49964d86cabcb52addbb5b9facc599790bb649dc2988d98cceb2`。

收口 commit `d110e3b02f99ab26644af264446ad0d23d5d795b` 注册 Case102 compact carriers，
`7149b2ba7c0a373e8b8a828f2e57d18f6598f1fe` 修正 `A_volume`/RSS source 字段；获批的
test-only commit `2dbf898c431595982b84dedc14bd196cc7bf74cc` 只补该字段。修复后唯一一次
full pytest 在该 HEAD 上为 `975 passed, 48 skipped, 0 failed`，1328.33 s，exit 0；
日志 `/tmp/task037c_r7_full_pytest_2dbf898.log`，SHA256
`2cbc7c673887077af120b6678e540090a55e8ba8569957baf40f39caa3c25f6e`，1245 bytes。

style commit `9a51a76e44d43e9f35e545f6dc9a442f25bfb08d` 的两文件 Ruff format 机械变更已做
AST identity 检查；serial focused `107 passed`、MPI2/MPI4 lightweight、Ruff、compileall、
diff-check均通过。最终 docs-only commit 尚待本轮文档 Gate 后创建；full pytest 不因 docs
提交重复运行。

## 6. 限制与下一步

- 所有 PDE 证据绑定 `f2d7719`；其后只发生已审的两文件 Ruff 机械格式、test-only 夹具和
  evidence contract 变更，未改变 numerical algorithm、ordinary default 或阈值。
- `response_v1.md`、`6555663`/max_it1600 负结果、旧 R2/R3/R4 diagnostic 与 ignored raw
  artifacts均保留。
- MPI8 数值通过但 process-tree RSS 为 6475.238--6623.156 MiB，未过 6144 MiB preferred；
  MPI1 数值/identity通过但 RSS 1662.109--1751.320 MiB，未过 1536 MiB preferred。
- 不把本扩展提升为 production-qualified；不追加 M200、新 PC、更多角度、MPI1 以外的新
  资源结论或 continuum claim。后续若要产品化，需要新的 review、默认路径审查和 fresh PDE
  authorities。
