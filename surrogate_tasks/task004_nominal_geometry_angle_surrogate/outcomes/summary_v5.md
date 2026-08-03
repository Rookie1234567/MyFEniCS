# Task004 M4F summary（Case127）

| 阶段 | 状态 | 证据 |
|---|---|---|
| M4E2 V3 support/acquisition Gates | pass | Case127 pre-FEM checker |
| Round1 FEM | 16/16 measured_pass | Case127 post-FEM checker + ignored records |
| train112 immutable package | pass | `case127_train112_check.json` |
| paired 96→112 | completed; partial tail improvement | paired learning curve |
| standard train112 CV | completed; Level A fail | `train112_cv/training_cv.json` |
| aggregate model lock | absent（按 Gate fail closed） | no lock file |
| order-resolved qualification | not qualified | `order_qualification_v3.md` |
| blind validation | sealed / not run | train112 manifest |
| second active learning / Task003 / Fisher / inversion | not run | scope boundary |

固定前向身份为 SHA `fdf961545f217d620e22800f2704ae9913a6d270`，Full3D static
uniform N1curl p5/h10/Ny4、mesh `(6,4,14)`、MUMPS ICNTL(14)=40、MPI2、
thread1。112 点 tuple hash 为
`00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68`。

CV 依据训练数据选择 `gp:F3`, jitter `1e-8`，但 R/T/A 的 NRMSE、p95 或
max 仍超限；因此本轮是受控负结果，不是模型锁或 blind authorization。
