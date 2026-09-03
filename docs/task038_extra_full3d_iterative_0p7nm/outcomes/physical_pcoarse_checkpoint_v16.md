# Q2 checkpoint reference：真实结果

本文件整理 Q2 的唯一 MPI1 checkpoint-correction formal。它回答的是：把旧
checkpoint 恢复到同一 p6/h10 物理离散后，能否用冻结的 p3 inner correction
降低残差；它不是 official physics 结果，也不是 0.7nm/2TiB 可扩展性证据。

## 结论

| 项目 | 实际结果 | Gate | 判定 |
|---|---:|---:|---|
| checkpoint residual reproduction relative | `6.8416957056789795e-9` | `<=1e-11` | FAIL |
| p3 inner final true residual | `0.7749555148382701` | `<=1e-6` | FAIL |
| `rho_ref` | `2.7001483995603124` | `<=0.70` | FAIL |
| `rho3` | `0.774955514838267` | `<=0.10` | FAIL |
| parent process-tree peak RSS | `1,560,625,152 B` | `<2,000,000,000 B` | PASS |
| worker process-tree peak RSS | `873,783,296 B` | 记录值；Q2 不用 Q1 的 500 MB worker 门 | recorded |
| swap | `0 B` | `=0` | PASS |

因此 checker 的精确分类为
`Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL`；错误为
`numerical:inner final true residual failed`。这是实际数值 Gate 失败，不是
path、cache、lifecycle 或环境故障。独立 compact 见
[`physical_pcoarse_checkpoint_v16.json`](records/physical_pcoarse_checkpoint_v16.json)。

## 身份与可复核证据

| 身份 | 值 |
|---|---|
| source SHA | `9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b` |
| input SHA | `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| old checkpoint source SHA | `ee5920b9fa977a39fea7bc09cfbe155303acdb2d` |
| checkpoint manifest SHA | `7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139` |
| checkpoint solution SHA | `00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b` |
| model/mode | p6/h10, complex128；mode SHA `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |

Artifact root 为
`benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/q2_checkpoint_reference_v1/9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b/mpi1`。
以下是 W0 已绑定的五个正式文件及其实际 SHA256：

| 文件 | SHA256 |
|---|---|
| [`parent_record.json`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/q2_checkpoint_reference_v1/9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b/mpi1/parent_record.json) | `7957ceeb43b449aa5adf0281d77c69a43fde51ec17fb8d0adc8dee2f94b14cd6` |
| [`raw/worker_record.json`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/q2_checkpoint_reference_v1/9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b/mpi1/raw/worker_record.json) | `df541289efe0de98887f342a45125dc77b46cd3127a4a77835cd07767cca0f92` |
| [`parent_process.jsonl`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/q2_checkpoint_reference_v1/9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b/mpi1/parent_process.jsonl) | `a31cdf1b673777ec0f5eb3513ce311994959a15c07908a2914882f9eb1dc46c4` |
| [`marker_manifest.json`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/q2_checkpoint_reference_v1/9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b/mpi1/marker_manifest.json) | `451c336a031597735a40ab5d7035210eda517be409b10e5c99c769fbd8b4087a` |
| [`checker.json`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/q2_checkpoint_reference_v1/9f18a6ccdf979f13fcb8eaab2bd57defb55f3c7b/mpi1/checker.json) | `12e4fbe4d41a96afbc2bd4d644ae4e2b97756a3d6d2a5eccb0f7743dff48bde4` |

## correction 数学与残差历史

形式链为

```text
r6 = b6 - A6*x1000
r3 = P63^H*r6
A3*e3 = r3                 (right FGMRES, p3 -> p1 positive PC)
e6 = P63*e3
r6_new = r6 - A6*e6
r3_new = P63^H*r6_new
rho_ref = ||r6_new|| / ||r6||
rho3 = ||r3_new|| / ||r3||
```

Q2 只调用 p6/p3 split-volume + streaming-DtN physical action 和合法 p3→p1
positive cycle；上层 p6 smoother 的实测 apply delta 为 0，没有把完整 physical
p-cycle 偷换进本次 correction。原始 norm 为：

| 向量 | global norm |
|---|---:|
| `r6` / `r6_before` | `0.6412077991519661` |
| `r6_new` | `1.7313562126657716` |
| `r3` / `r3_before` | `0.39933395062332383` |
| `r3_new` | `0.309466047297697` |

checkpoint stored residual 为 `0.4837947981092168`，重算为
`0.48379479479924`；两者形成的 reproduction relative 为
`6.8416957056789795e-9`。inner 使用 zero start、right FGMRES、restart 20、
每 20 步显式重算 true residual、`max_it=10000`、`norm_type=unpreconditioned`。

| iteration | explicit true residual |
|---:|---:|
| 0 | `1.0` |
| 20 | `0.8309410237461273` |
| 1000 | `0.7830431676258411` |
| 2000 | `0.78048347154443` |
| 4000 | `0.7781984682037493` |
| 6000 | `0.7766983492676462` |
| 8000 | `0.7756091855405819` |
| 10000 | `0.7749555148382701` |

最终 10000 iterations，wall `2460.657032735995 s`；matvec `10999`，PC apply
`10000`，explicit action `501`，KSP destroy `500`。每个 restart-20 周期均
销毁 KSP/basis。operation ledger 为 p6 action delta `2`、p3 action delta
`11500`、lower-cycle delta `10000`、P63 primal `1`、P63 adjoint `2`，upper
cycle `0/0/0`（before/after/delta）。

## 完整性、资源与生命周期

| 类别 | raw fact |
|---|---|
| finite / input unchanged / owned-slave zero | 通过；checkpoint solution、rhs、r6/r3 before/after/new 与 correction 的约束事实均保留在 worker raw |
| architecture | p6/p3 exact split-volume + streaming DtN；无 global physical AIJ、dense DtN、physical factor、numeric allgather |
| cache | initial 0，before/after 各 54；manifest SHA `e87d8de150d74e16086d2fae37babda3cca3c71ebf47349abef07269314a6b18` |
| markers | `paths_ready → abi_ready → case_built → checkpoint_restored → residual_reproduced → inner_complete → correction_measured → release_complete → record_written` |
| process tree | parent max PSS `1,531,692,032 B`，worker max PSS `848,829,440 B`；all readable，swap=0，parent/worker/compiler/orted 均消失 |
| wall | marker span `8373.730396 s`；inner wall `2460.657032735995 s` |

## 阶段边界

Q2 的 official physics 未运行；Q3、Q4、Q5、Q6 均 `locked/not_run`，没有创建
screen 或 p6-physical outcome。Q2 的失败只证明这条 reference correction 在该
checkpoint 上未达到 contraction Gate，不把失败扩大为所有 future PC 的结论。
