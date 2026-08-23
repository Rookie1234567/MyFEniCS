# Task038-extra V8 closeout summary

## 结果与范围

| 项目 | 状态 | 关键事实 |
|---|---|---|
| formal source | 已完成 M0 两次 attempt | f76a30e843dcc1e3e25aee6a73df6aca12222f10；9f44464eda27590492dcfe0432129a126625b5cc |
| branch | 当前执行分支 | codex/20260820-task38-extra-full3d-iterative-0p7nm |
| 旧 L2 one-apply | FAIL，永久保留 | rho=1.7348663090876784 > 0.45 |
| 旧 Krylov/v1 80-step | FAIL，永久保留 | 未满足冻结的 80-step performance qualification |
| additive-v2 | formally closed | 小型 MPI2 robustness failure；不重分类旧结果 |
| M0 attempt1 | negative | f76：edge orientation placement 与 exact-nodal MPI identity 均暴露问题 |
| M0 attempt2 | HARD STOP | 9f：edge placement 修复后 edge/pre 约 1e-15，但 exact-nodal pair 仍失败 |
| M1–M7 | NOT_RUN_BY_M0_HARD_STOP | V8 §12 禁止继续 |

M0 是 p2/h50、random、正定 auxiliary 的根因诊断，不是 PDE、p6/h10 或 official physics。9f 代码窄修已验证边方向放置，但整个 M0 没有闭合，不能提升 ordinary default。

## attempt2 关键事实

| metric | MPI1↔MPI2 canonical relative / value |
|---|---:|
| high source before | 1.417734557397384e-15 |
| high residual | 1.6029978812022376e-15 |
| low input | 1.6864438658655413e-15 |
| exact edge correction / action | 1.5658061021293675e-15 / 1.7783413648977776e-15 |
| exact nodal output | 0.03757191918203578 |
| first exact-nodal component | gradient.rhs=0.36157950436833775 |
| owner-consistent diagnostic | gradient.rhs=2.396070826157907e-15，但 nodal_delta=0.11660480519091415 |
| fixed lattice node_matrix action | 0.08847380943557186 |
| direct nodal residual | MPI1 5.310854724390275e-16；MPI2 4.602617923986701e-16 |

MPI2 的 92 个 negative cell-edge references、208 个 minus map factors 和 37 个 remote relation inconsistencies 已记录在 root-cause outcome。sign-only gradient.rhs 仍为 0.20630212828353248，说明不是单一 sign 问题。

## 资源与证据

| case | wall | GNU time max RSS | Swaps | 口径 |
|---|---:|---:|---:|---|
| 9f p2-mpi1 | 12.88 s | 199405568 B | 0 | 单 qualified Python 进程 |
| 9f p2-mpi2 | 7.42 s | 197115904 B | 0 | mpiexec launcher observation |

上述不是 process-tree/cgroup peak、p6 setup 或 2GB authority；系统约 16625664 B swap baseline 与 worker Swaps=0 分开。markers 到 cleanup_end，natural exit 后无 orphan。

证据入口为 outcomes/records/m0_attempt1_f76_*、m0_attempt2_9f_*、m0_postfailure_diagnostic_v1.json，以及 ignored raw roots。副本与源逐字节绑定，旧 negative 不删除、不覆盖。

## selective merge 与下一步

9f orientation placement + lattice evidence fix 可作为 research-only/pending follow-up review；M0 runner/checker/evidence 可独立审阅，但整个 M0 未资格化，不得合入 ordinary default。本分支没有 merge approval。

下一步不能自动进入 M1。若要继续，需新 review 先修复并独立资格化 scalar MPC / remote owner relation / node operator，再重新定义可审的 M0 Gate；本 closeout 不提出参数扫描或放宽阈值。
