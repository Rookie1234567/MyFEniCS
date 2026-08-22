# Review V6 response：FC0–FC3 closeout

本文用中文记录 V6 hard-stop 的最终证据边界。**local factor** 指局部正定辅助矩阵的 Cholesky 三角因子；它把一个小 patch solve 变成前后两次三角回代。**process-tree memory authority** 指 watchdog 从整个 worker 进程树读取并按合同取的内存峰值，不是单 rank RSS，也不是把不同阶段历史峰值相加。**controlled resource negative** 指程序被冻结资源线主动停止，说明这一 run 没有资格化，不等于物理方程或所有数值路径都失败。

## Review V6 §13 的逐项回答

|#|问题|结论与证据|
|---:|---|---|
|1|分支、HEAD、base、upstream、ABI|formal/closeout source HEAD 为 `d5f86fc14c7f40ec58e3eb75e07146b4eb4cf066`；frozen master base `438caf150439343ee7c4c58ad7e02a3da812a23c`；当时 upstream `origin/codex/20260820-task38-extra-full3d-iterative-0p7nm` 为 `6bb307406dd0ee420fb7903b9411cb52a1731ec7`，ahead/behind=2/0，formal start clean。qualified activation=1，Linux Python `/home/shenjh/MyFEniCS-Surrogate/.venv/bin/python`，OpenMPI 4.1.6，PETSc/SLEPc/DOLFINx/Basix/SciPy 同一 Linux ABI，complex128/int32，OMP/OPENBLAS/MKL=1；startup MemAvailable 13,201,984 kB，system swap total/free=41,943,040/41,926,548 kB（约16.9 MB used），disk 可用约941,946,200,064 B。最终 docs commit 不能在本文中自引用，完整 final SHA/upstream 以交付报告为准。|
|2|旧 N2 v1/v2|保持原样、不删除、不覆盖、不重分类。v1 SHA `d02f416956a560c0837d067636d8f62d253c9d04da4e6bbe3b6194dd10098d40`；v2 SHA `d88330f2c9b038946c8f0b15e22b5850e6812c868366fa50f04e1e9b3962f763`。|
|3|FC0 implementation|source `d9f3c30285e169879891c7bef7896079b5a3babf`；focused 48 passed/1 skipped，compileall/AST/diff-check通过。它是实现合同，不是 p6 完整 setup。|
|4|固定数值合同|`eps64=2.220446049250313e-16`；`gamma_882=1.9584334154391596e-13`；Hermitian limit `1.5667467323513277e-12`；factorization/backward limit `3.1334934647026553e-12`；ordinary residual `1e-10`；`kappa2 <= 1e8`；factor/class `6,230,448 B`，global `199,374,336 B`。没有因结果改 threshold。|
|5|FC1 class inventory|FC1 case `p6-h10-mpi1`，26 classes，882 rows/class，missing/duplicate=0，all_processed/all_pass=true，order/repeat exact=true，order SHA `a7b649d25c7f843a160816a3c4fe3836243e9639eb7c0ba43dd2901955511028`。所有 class digest/slot/identity/hash 在 `n2_local_factor_all_class_cert_v2.json` 的 `classes` 中逐项保存。|
|6|每 class 指标|独立 checker 从 ignored B/RHS 和 worker facts 重算每类 finite、Hermitian/SPD、lambda min/max、kappa、factorization、packed identity、triangular residual、backward、repeat 和 Gates；tracked compact 只保留 scalar facts，不复制 dense arrays。全类通过仅属于 FC1 certification。|
|7|worst identity|Hermitian worst：digest `9a0d14a26cbd4f5272f3d9e3cfbeef1acdf521330034b7f960adb9acbee6e63b` slot14，`1.011861373443624e-16`；SPD/kappa worst：`2c0158caba9c69275ba88a85343a15ccffbef4bdb8d463d0be47ca8d18fec301` slot6，lambda-min `4.495428682394547e-4`，kappa `5.768906342088295e7`；factorization worst：`48f903688ffb4d930384ca6f8160e39f5938f71871de27fe8db0538d9b534d04` slot7，`9.360591063492774e-16`；ordinary/backward worst：`13597baf243c7cd52a5080b48e7361b3faa0e45cb4c937aa8a1c140a9e2b0c2a` slot4，residual `1.1713789755077614e-11`，backward `9.83496351829931e-19`；factor-size worst digest `0060a10f08d980ac618497c076b8c6d078d6d1841d3f37d8172bc6e5804f8563` slot0，恰为6,230,448 B。|
|8|factor ownership/bytes|FC1 MPI1 owner rank=0，unique factor count=26、duplicate=0、total `161,991,648 B <=199,374,336 B`。这是 FC1 的 owner closure；FC3 没有完成新的 252-patch/global retained closure。|
|9|FC1 resource/lifecycle|FC1 watchdog 127 samples，peak `1,547,800,576 B`，swap gate=true，worker rc0，`natural_exit=true`，already_exited/no orphan。FC1 只做 class certification；不能用它替代完整 N2 cold/post-setup Gate。|
|10|FC1 checker|独立 checker compact 131,002 B，SHA `2d25ba960fdd6939f5d9d5b66b7619c17c1838cc4b9befdb4a9b49cbaa3d8e80`，`passed=true`。它不导入 runner/solver/PETSc/MPI，且验证 worker summary、threshold contract、class order repeat、representative identity、count/bytes/owner closure。|
|11|FC2 wiring/production solve|`d5f86fc...` 是 prospective certification v2 wiring commit；没有把 FC1 class facts伪装成 complete N2。dedicated triangular solve保持已审路径，不加入 refinement、fallback、class-specific exception，也未改变 B0/patch/mode/regional/top 参数。|
|12|FC3 执行与 hard Gate|source `d5f86fc14c7f40ec58e3eb75e07146b4eb4cf066`，root `benchmarks/artifacts/task038_extra_full3d_iterative_fc3/d5f86fc/p6_h10_mpi1`。watchdog 3,637 samples，process-tree peak `2,228,187,136 B >= 2,000,000,000 B`，swap=0、swap gate=true、no orphan、worker rc=1、stop=`hard_stop_2gb`，所以 FC3 是 `FC3_CONTROLLED_RESOURCE_NEGATIVE`。实际 raw marker ledger 已进入 `regional_coarse_build`，但该阶段 completion/result 尚未取得；watchdog compact stage peak 与 fallback worker record 显示 startup/source null，只是 stop-time fallback attribution，不覆盖 raw marker authority。FC3 没得到 complete 252 inventory closure、post-setup retained、top/Z/AZ/E 或 identity apply。|
|13|FC4|`not_run_by_fc3_resource_hard_stop`；未启动。|
|14|N3|`not_run_by_fc3_resource_hard_stop`；未启动。|
|15|N4|`not_run_by_fc3_resource_hard_stop`；未启动。|
|16|证据口径|FC1 的 class metrics 是 measured/independently_recomputed；factor bytes、gamma 和 limits 是 exact arithmetic/contract；FC3 peak/samples/swap/no-orphan 是 measured watchdog authority；FC3 未完成的 inventory、retained、Z/AZ/E、identity、后续 phase 是 not_run。FC3 是 controlled resource stop，不是 numerical residual failure。|
|17|selective merge|FC0/FC1 certification evidence可保留；FC2 prospective wiring只作 research/opt-in，不能提升 ordinary default；FC3 local-spectral multilevel family 因资源 hard stop closed。watchdog ownership/marker provenance修复可独立审阅；任何未资格化 N2 setup 代码不作为 production default。|
|18|T6/official/T7–T9/full PDE|T6-F、official E/H/RTA、T7–T9、full0.7nm PDE均未运行；没有由 FC1 或 FC3 推导 official physics 结论。|
|19|提交、命令、artifact|FC0 source `d9f3c302...`；FC2 source `d5f86fc...`。FC1 raw/compact/record/log 位于 `benchmarks/artifacts/task038_extra_full3d_iterative_fc1/d9f3c30_attempt2/p6_h10_mpi1`；FC3 raw/compact/record/log 位于 `benchmarks/artifacts/task038_extra_full3d_iterative_fc3/d5f86fc/p6_h10_mpi1`。FC3 watchdog raw SHA `1216c79de11fe99bf827e71b8d9cc46114935f5cabbcbf23085ca567761eda99`，compact SHA `62172d1e44583168c35ed59fe359282193246eb90d738d529fe044f5a5e3fb0d`，fallback record SHA `2bcfa6c385e81c4e5a2162707544cee7094adbef94f2e8b4cb891b5afadff3f`，worker log SHA `781c9c56fc57d4f333cec5890cf4173da5c8e4bc96ca235e6d0e0c6ef28dc1a6`。FC1 主要 hash 见 `outcomes/local_factor_all_class_certification.md` 与 compact。|
|20|最终建议|将 FC3 视为完整 N2 family 的终止证据：不重跑、不调参、不进入 FC4/N3/N4。保留 FC1 独立 class certification 作为局部正证据，保留所有旧 N2 v1/v2 negative/raw；不要把“局部 class PASS”或“FC3 尚到 regional marker”写成完整 setup/resource/PDE PASS。|

## FC3 资源与阶段证据的明确边界

FC3 watchdog compact 的 resource authority 是有效的：raw 有 3,637 samples，peak `2,228,187,136 B`，hard line `2,000,000,000 B`，process-tree swap=0、swap gate=true、no orphan。它在资源上已经足以停止后续工作。

但 stop-time fallback record 没有及时取得 worker 的 source/marker ledger，因此其中 `last_marker=startup`、`marker_ledger=[]`、source null 不是实际阶段证明。实际 marker 文件和 worker.log 都由 source `d5f86fc...` 绑定，顺序明确显示进入 `regional_coarse_build`，但没有该阶段的 completion/result：

`preflight -> mesh_space_mpc -> JIT -> subdomain_inventory -> local_factor_build -> local_mode_build -> regional_coarse_build`。

这两组事实不能互相覆盖：资源 hard Gate 使用 watchdog authority；阶段 attribution 使用 raw marker ledger。因而无需重跑，也不能把 startup fallback 当成最后真实阶段。

## 关闭矩阵

|lane|状态|
|---|---|
|旧 N2 v1/v2|原样保留的 controlled negatives|
|FC1|all-class local factor certification PASS|
|FC3 complete N2|`FC3_CONTROLLED_RESOURCE_NEGATIVE`|
|FC4/N3/N4|not run by hard stop|
|T6-F/official/T7–T9/full0.7nm|not run|
|family recommendation|`CLOSED_BY_FC3_RESOURCE_HARD_STOP`，无资格继续|

本文件与新增 compact 属于 docs/evidence closeout；最终 docs commit SHA 不能在自身内容中自引用，交付报告给出最终 HEAD、upstream、ahead/behind 和 push 状态。
