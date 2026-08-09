# Task037b Review V5 response：唯一 MPI8 多指标 full-solve 结项

## 结论

本轮按 Review V5 只运行了一次同一 candidate 的 formal MPI8 full-solve。没有 retry、warm
start、continuation、参数修改、restart sweep 或第二次数值运行。V5 implementation
checkpoint 为 `770e74513b4444f032adb7f61c5d350fb53d9458`，formal candidate source 为
`892f186b39c0eb89f1912640430fd79599d86318`。formal 后的
`11c01d5268f1e0fc8eb307945179b540ccfcb2aa` 只修正 parent watchdog/evaluator 的状态合同，
不改变 solver record 或物理结果。

| 层次 | 最终结论 | 说明 |
|---|---|---|
| numerical | pass | KSP reason `2`、iteration `557`；五项 final residual 均 `<=1e-6` |
| recovery | pass | bottom/top external q identity 与 full-FE recovery 通过 |
| own physics | `fail_exact_traction_dual` | bottom/top exact traction dual 为 `9.609121539153052e-7 / 4.5634977013685214e-7`，限值 `1e-8` |
| overall | `MULTIMETRIC_LINEAR_PASS_RECOVERY_OR_PHYSICS_FAIL` | 受控 post-linear physical negative |
| resource | `MPI8_RESOURCE_NEGATIVE` | process-tree RSS `7.049583435058594 GiB > 6 GiB` |
| production | `not_qualified/research-only` | ordinary defaults unchanged；master merge 未授权 |

这不是“线性求解发散”：外层五项线性 residual 已通过，失败只来自冻结的 exact variational
traction dual physics Gate。它也不是资源杀死：worker 自然退出，未触发 warning/termination/
timeout 或 SIGKILL。

## 1. 冻结配置与完整线性证据

配置为 p6/h10、modal p6/h10、13.5 nm、S、10°、10/110 nm、M120/candidate240、每侧40
external modes、MPI8、static-condensed、`full3d_uniform_cg` /
`scalar_cg_discrete_derivative`、block-ldu-action-full-solve、right FGMRES restart90、
rtol `1e-6`、atol `0`、zero initial、max_it `700`。history 有558行，严格连续为0..557，
每个 iteration只有一条 exact row；monitor 不重复施加 exact residual action；postsolve retained-solution explicit audit执行1次。558条唯一 history row、postsolve count=`1`、两侧 online apply increment=`1114=2*557`共同支持这一执行合同。
outer operator 是 `exact monolithic Hybrid operator`；两侧 PC 是 `fixed whole-endcap ILU(0) + 40-mode DtN Woodbury action`，ordinary defaults unchanged。

| iteration | reported | global | bottom | top | modal | multimetric max | elapsed s | ksp reason | decision |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 2.2424710600856975e-6 | 2.242471060163116e-6 | 3.4111266901058858e-6 | 1.5835805727648354e-6 | 1.4094975322947167e-15 | 3.4111266901058858e-6 | 81.33067819301505 | 0 | `ITERATING` |
| 520 | 1.4265563629448059e-6 | 1.4265563629094859e-6 | 2.0548396968980893e-6 | 1.0386858184740322e-6 | 1.5241312777460737e-15 | 2.0548396968980893e-6 | 84.56075759895612 | 0 | `ITERATING` |
| 534 | 9.832241894524608e-7 | 9.832241891202619e-7 | 1.364175187660687e-6 | 7.290772088419766e-7 | 1.6064823432658189e-15 | 1.364175187660687e-6 | 86.82920670497697 | 0 | `ITERATING` |
| 540 | 8.137715143365693e-7 | 8.137715143585267e-7 | 1.2167293120702838e-6 | 5.8057495384064e-7 | 1.925960881288701e-15 | 1.2167293120702838e-6 | 87.80791945999954 | 0 | `ITERATING` |
| 550 | 7.243836969791837e-7 | 7.243836969886748e-7 | 1.1057248017639442e-6 | 5.104540257008618e-7 | 1.0202967889790073e-15 | 1.1057248017639442e-6 | 89.45420049794484 | 0 | `ITERATING` |
| 557 | 6.457740108721289e-7 | 6.45774010063497e-7 | 9.811891391712585e-7 | 4.5634977013685214e-7 | 1.3354878193519844e-15 | 9.811891391712585e-7 | 90.59673926699907 | 2 | `CONVERGED_RTOL` |

因此 560、580、600、630、700 未达到，不能在 compact 或 response 中补写预测值。iteration
534 的 bottom residual 为 `1.364175187660687e-6`，仍为 `ITERATING`；最终557步的五项
postsolve explicit audit 全通过。bottom/top direct factors 为0/0，ILU为1/1，global direct
factor为0，nested KSP/direct fallback均为false；K rank为40/40、condition为
`3.0331668903694333 / 4.1626875391737554`；modal Schur为240x240、rank240、condition
`1774.3032595169025`、complex128、normal equations=false。两侧 online apply increment为
`1114=2*557`。

## 2. Recovery 与 own physics

bottom/top external q identity relative residual为`0.0/0.0`，每侧40个mode，finite且unique。
full-FE逐侧证据为：bottom linear `7.128867121665533e-7`、interior relative
`1.964774406457519e-12`、interior max `8.726571982174999e-13`；top linear
`7.31449061294792e-7`、interior relative `2.0030607460888172e-12`、interior max
`1.123510764743594e-12`，均通过 raw recovery Gate。

own physics 中 sampled interface E 通过，bottom/top relative L2 为
`5.112828439237629e-7 / 5.438313443889813e-7`；energy diagnostic 通过，closure 为
`-1.002582173281752e-6`，`A_balance-A_volume`为`1.002582173337263e-6`。唯一失败是 exact
traction dual：bottom/top 为`9.609121539153052e-7 / 4.5634977013685214e-7`，都高于
冻结 `1e-8`。本轮不擅自放宽 traction Gate；科学含义是外层 `1e-6` 线性停止足以完成五项
linear Gate，但不足以满足 `1e-8` 端盖 traction physics Gate。是否收紧停止精度或调整资格
逻辑留待下一轮 review，本轮不实施。

## 3. Official boundary、authority gap 与生命周期

由于 own physics 未通过，official `field`、`R/T/A`、`A_volume`、orders、12+12、canonical、
direct-Hybrid 和 Full3D comparison 全部 `not_run`；energy diagnostic 不得改写为 official
output。H1 authority 仍缺 modal、canonical、selected-field 数值 payload，因此缺项标为
`not_run_authority_payload_gap`；conditional direct-Hybrid authority export 因 own physics
失败为 `not_run_dependency_gate`。本轮没有 direct authority export、Full3D comparison 或
checker 重跑。

### V5 authority payload inventory

| authority | 已实际核验的 payload | 缺失或仅引用的 payload |
|---|---|---|
| H1 direct（source `2990f357f7dec23b1713bd0088bdc43c3ce6f5bc`） | solver `benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8/solver_record.json`（SHA `290fc25c119bbf641b8f0277ed5f9a101bc11a4df898c9133509f53c56dd4a1c`）；summary `benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8.json`（SHA `e22aa1edfeab331d5a8be13ca085e029d5446a4fdf300a5787a00688ef700db2`）；scalar R/T/A、residual/field-error、q、orders、12+12 | modal numeric vector、canonical numeric manifests/vectors、selected interface/middle E/H numeric arrays 缺失；hash/pass label不替代数组 |
| pinned Full3D（source `244b62e1fb4f299a468363cf90a2dd548dc34ff6`） | record `/home/Projects/MyFEniCS/benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_full_static_mpi8_244b62e.json`（SHA `b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3`）；`full3d_reference_samples.npz`（SHA `f8d44616d8333188edfa2f903eaed14dc7c47e9b39b33921b91269fc9a04d2e3`，shape `5x20x40x3`）；metadata `full3d_reference_samples.json`（SHA `74ea1a9984625883a65da9a5f6c9187279665b23e5cc980e500f6eb39053b7b2`）；record scalar R/T/A/A_volume/closure已核验 | record-referenced dtn orders/amplitude paths未独立SHA核验 |
| Case095 significant reference | `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json`（SHA `83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3`）；12 numeric channel powers、complex amplitudes、mode keys、thresholds | 无本轮新增缺口 |

因 candidate own physics=false，conditional direct authority export 与 Full3D checker/comparison 均为
`not_run_dependency_gate`；H1 缺失项不能用旧 pass/hash label或零值替代。

postsolve 后释放顺序与重复 residual Gate均通过：KSP/Krylov、两侧 ILU、两侧 W/K/LU、approx
modal Schur均释放；retained solution、bottom/top split与modal snapshot最终四项
destroy/release均为true；borrowed exact actions仍可用，release-repeat relative difference
为`0.0`。这部分是生命周期证据，不是从 status 推断。

## 4. Resource、swap 与 parent postprocessor caveat

| 指标 | exact raw maximum |
|---|---:|
| process-tree RSS | `7218.7734375 MiB = 7.049583435058594 GiB` |
| worker RSS | `7204.125 MiB = 7.0352783203125 GiB` |
| worker PSS | `5500.109375 MiB = 5.3712005615234375 GiB` |
| worker USS | `5225.45703125 MiB = 5.102985382080078 GiB` |
| peak stage | `v4_worker_cleanup_finished` |
| resource `<=6 / <=5 / <=3.77 GiB` | `false / false / false` |

timeline 离线 audit 有1428 rows：worker-count `{0:2, 8:1426}`；1426条真正 all-eight-live
rows 的 smaps readable count 全部为8，worker/process-tree swap全部为0。因此对 observed
all-live rows 可记 `corrected offline audit zero-swap qualified`。首行是 process_start 的
0-worker，末行是 cleanup 后正常的0-worker terminal drain。immutable parent summary 的
`no_swap=false` 与 `terminated_for_authority_unreadable=true` 原样保留；它们来自修复前
terminal/postprocessor bug，不能被静默改写成正式 parent Gate pass。

raw parent watchdog 曾 exit1、status=`task037b_v4_implementation_gate_failed`，failure来自
两个已修复的合同错误：`terminal V4/V5 record legacy-field completeness contract` 与
`official-not-run energy evaluator contract`；它们产生了 `physics_contract`、
`record_status_mismatch`、`qualification_disposition_mismatch`、`v5_disposition_mismatch` 四个
parent failure label。同一 raw solver 的纯函数只读 evaluation 得到
contract/numerical/recovery=true、physics=false、failures=[] 和正确 disposition。这不是第二
次数值运行，也没有改变 raw solver 或物理结论。

## 5. 测试、artifact 与停止边界

preformal focused serial 为29 passed；MPI2指定节点5 passed/rank，MPI4同为5 passed/rank；
touched-file Ruff/format/compileall/diff-check pass。postprocessor correction 的 test244为9
passed，test59/test74相关节点为4 passed，两个文件 static checks pass。full pytest、CI、
restart sweep、MPI1/MPI4 full、资源优化、0.7nm、新PC和master merge均为`not_run`或未授权。

V5 compact record 为
[task037b_v5_mpi8_multimetric_full_qualification_v1.json](../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v5_mpi8_multimetric_full_qualification_v1.json)。
raw summary SHA为`1c0fcddeb011618e1306577a39e2c3983bb42fa7c4080efe2569dae7973f67ee`，solver
SHA为`237a7f5e2b21ac8ae61d842ee1b3ff3b433cbee82389c06575fe7e3a8913878e`，timeline SHA为
`166dce778af8f7e7115ee0b1ea2dcd67c3259ecde2204dc32cb6880920f463fd`，stages SHA为
`536ad9eafad3a9d17c962526f845305a07a6b21bf8f4f74aacbdced1e7864382`，stdout SHA为
`3d8d95ffb1185b6d2b9ffdecb0975f834c3b1686712539db0b581176f381dba5`，diagnostic NPZ SHA为
`f8e9eb9a47dbe91d374c04b3a74d0ea12df0ff538c23fafaa9a8c65089ac51fe`。

ordinary defaults unchanged；本轮只完成 V5 evidence closeout，停止在 Review V5 授权边界。
