# V18 restart64 physical checkpoint qualification

## Authority and conclusion

V18 对同一 p6/h10 checkpoint-1000 运行一次固定 restart=64 的 physical Krylov
qualification。它测试较长但仍有界的重启周期，不能替代 fresh PDE、official
recovery 或新的 PC。独立 checker 读取 immutable parent/worker raw 后返回：
status=PASS、evidence_valid=true、errors=[]，classification=
V18_RESTART64_NUMERICAL_GATE_FAIL。

资源结果为 PASS：完整 parent process tree 的峰值 RSS 是 1,583,013,888 B，小于
严格的 2,000,000,000 B；swap=0，状态样本可读。64-step qualifier 通过。1024-step
screen 是真实 numerical FAIL：

| Gate | measured value | limit | result |
|---|---:|---:|---|
| screen step 512 | 0.35604872662297266 | <= 0.25 | failed |
| screen step 1024 | 0.27299642739429014 | <= 0.10 | failed |
| screen r1024/r768 | 0.8588033360973709 | <= 0.85 | failed |
| long continuation | not run | <= 1e-6 | not_run_screen_gate_failed |

screen 失败后 continuation 没有启动，因此 larger-restart/Krylov-memory lane
关闭。本结果不是 path/cache/import 工程失败，也不是资源停止。

## 与 V17 的并列比较

残差是显式 true residual 的归一化值，用来表示剩余代数误差；V17 的两项结果来自
同一 checkpoint/RHS 对照，V18 是同一 authority checkpoint 上的 restart64 测试。

| 方法 | 末步 | measured final residual | 结论 |
|---|---:|---:|---|
| V17 right GMRES(20) | 500 | 0.48362582271206495 | restarted reference |
| V17 unrestarted right FGMRES | 500 | 0.19374101288500692 | WEAK；ratio=0.4006010510326989 |
| V18 restart64 qualifier | 64 | 0.38962773965567615 | qualifier PASS |
| V18 restart64 screen | 1024 | 0.27299642739429014 | numerical Gate failed |

V18 使用 PETSc in-memory restart-64 basis；不继承 V17 disk-backed unrestarted 的
内存语义，也没有改变 physical operator、positive pMG、source、checkpoint 或材料。

## Same-start authority 与冻结设置

冻结 checkpoint 是 absolute iteration 1000，checkpoint source SHA 为
ee5920b9fa977a39fea7bc09cfbe155303acdb2d，stored explicit residual 为
0.4837947981092168，manifest SHA 为
7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139，solution SHA 为
00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b。V18 formal source
SHA 为 a20008734c8bf0df03890bf35576c697eb0967f0。

qualifier 与 screen 都以相同 initial true residual
0.48379479479924 开始；RHS、initial solution 输入 finite 且 unchanged。冻结设置为
restart/cycle=64、qualifier=64 additional steps、screen=1024 additional steps、
continuation cap=10240、solution-only checkpoint interval=256、RSS watchdog/hard
gate=2,000,000,000 B、warning=1,800,000,000 B、swap hard gate=0。

checkpoint 的 absolute iteration 不被强行取整。raw 使用 additional iteration
0、64、...，并由 absolute iteration = 1000 + additional iteration 得到绝对编号。

## 完整 explicit true-residual history

下面是 compact record 中的完整 screen cycle history。每个 restart-64 cycle 结束时
都销毁 KSP/basis；matvec、PC 和 wall 是该 cycle 的 raw 事实。

| additional | absolute | explicit true residual | matvec | PC | KSP destroyed | wall seconds |
|---:|---:|---:|---:|---:|---|---:|
| 64 | 1064 | 0.38962773965567615 | 66 | 64 | yes | 624.9030772700207 |
| 128 | 1128 | 0.37667060380889733 | 66 | 64 | yes | 620.6052497870405 |
| 192 | 1192 | 0.37049604079499543 | 66 | 64 | yes | 635.9230083150323 |
| 256 | 1256 | 0.3663746937420886 | 66 | 64 | yes | 621.3134760280373 |
| 320 | 1320 | 0.36356581979016916 | 66 | 64 | yes | 622.2861189739779 |
| 384 | 1384 | 0.36123173651080465 | 66 | 64 | yes | 622.0136651609791 |
| 448 | 1448 | 0.35886075629549574 | 66 | 64 | yes | 622.8316032689763 |
| 512 | 1512 | 0.35604872662297266 | 66 | 64 | yes | 623.7745787349995 |
| 576 | 1576 | 0.35066246200307294 | 66 | 64 | yes | 622.6706513639656 |
| 640 | 1640 | 0.33927816594418947 | 66 | 64 | yes | 618.8519463840057 |
| 704 | 1704 | 0.3275011984102315 | 66 | 64 | yes | 613.6266970849829 |
| 768 | 1768 | 0.3178800266832427 | 66 | 64 | yes | 682.7961454369943 |
| 832 | 1832 | 0.30755175503568005 | 66 | 64 | yes | 742.8264940960216 |
| 896 | 1896 | 0.2964081024011118 | 66 | 64 | yes | 632.3923152100178 |
| 960 | 1960 | 0.2840466401029864 | 66 | 64 | yes | 606.1510012999643 |
| 1024 | 2024 | 0.27299642739429014 | 66 | 64 | yes | 601.1520078129834 |

qualifier raw summary is additional=64, absolute=1064, final true residual
0.38962773965567615, matvec/PC/explicit/KSP destroy=66/64/2/1, wall
618.2085667340434 seconds. Screen totals are 1024/1056/1024/17/16, with wall
10114.432694313 seconds. The four solution-only checkpoints are at additional
256/512/768/1024 and absolute 1256/1512/1768/2024.

## JIT, resources, cache, and lifecycle

Seven cold-staged children ran in the fixed order positive-p6, positive-p3, positive-p1,
dtn-surface, incident-rhs, physical-volume-curl, physical-volume-mass. All returned 0,
were readable, and their process groups were gone. Their peak RSS values, in that order,
were 1,583,013,888; 510,955,520; 372,953,088; 838,377,472; 767,823,872;
1,392,484,352; and 843,599,872 B.

The cache was empty initially (0 artifacts), contained 54 artifacts before the worker,
and contained the same 54 artifacts after it. The before/after manifest SHA was
15ad792c2e5dd24e096ee7b55c396261787e66123043bdd16c25a83cd261a48a. Measured free disk
was 907,356,512,256 B; V18 has no disk-capacity Gate.

Observed markers were:

    paths_ready -> abi_ready -> case_built -> checkpoint_restored
    -> qualifier_complete -> screen_complete -> record_written -> release_complete

There is no continuation marker because the screen Gate failed. Parent and worker returned
0 naturally; raw lifecycle records report process groups gone, readable status, and swap 0.

## Provenance and evidence

Artifact root:

    benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/v18_restart64_physical_v1/a20008734c8bf0df03890bf35576c697eb0967f0/mpi1

Compact hash-bound record:
[restart64_physical_checkpoint_v18.json](records/restart64_physical_checkpoint_v18.json)

| root-relative evidence | SHA-256 |
|---|---|
| parent_record.json | 06c1211590561daa3974c6da7f8b801468e5bf505d00474058bf4acd33d0753a |
| raw/worker_record.json | 4b7dcacdf3cd54b9c374dd5fd3d7eee6a4c8d2841ff23b7483bc9f96327841aa |
| checker.json | a1188e496948a0f09ee1a18eb7fc45fc8dd1c6aed4a1982081dc8b225b00c522 |
| marker_manifest.json | 6d7eb6a6f435d23b59c0e82260e0dede8238495098b82400f6c41c742366ed8b |
| parent_process.jsonl | d4c574d151b959ba19bdd5721c0bb8e61e030404b2ec292a76817488c3f6e432 |

本 outcome 的 measured 项来自 raw cycle、process、cache、marker 和 lifecycle 记录；
derived 项是 Gate 比较及 absolute/additional 映射；failed 仅指上表三项 screen Gate；
not_run 指 continuation、official physics、recovery 和其他 restart/Krylov lane。

V17 的 Oracle A FAIL、Oracle B WEAK signal、Q2 negative 及全部历史 evidence 不受
本次 V18 结果影响。V18 也没有产生 official complex E/H、near-field、R/T/A 或
0.7 nm/2 TiB scalable solve。
