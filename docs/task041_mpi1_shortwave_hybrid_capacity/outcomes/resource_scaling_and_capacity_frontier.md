# 资源、阶段耗时与容量边界

## 本次运行安全合同

下面是用户后续为本次尝试指定的更严格合同，不删除或静默改写 task.md 原有 1.50 TiB planning history：

| scope | warning | hard | phase/workflow cap | swap |
|---|---:|---:|---:|---:|
| workflow envelope | 224 GiB | 256 GiB = 274877906944 B | 39600 s | 0 |
| producer | 176 GiB | 192 GiB | 18000 s | 0 |
| consumer | 224 GiB | 256 GiB | 21600 s | 0 |

shortwave supervisor timeout 按各自 phase elapsed；legacy 5 nm 仍按旧 workflow elapsed。producer 必须完全退出并释放后才启动 consumer。workflow simultaneous peak 是不重叠的 max(producer peak, consumer peak)，绝不相加。启动资格 MemAvailable floor 仍是 1869169767220 B。post-change formal performance 尚未有独立隔离测量；M1200 的当前 candidate 证据不等于 physics/official pass。

## 运行实测与 authority

| run | producer peak | consumer/workflow peak | wall | authority |
|---|---:|---:|---:|---|
| M800 fresh 20260907 | 16.784275055 GiB | 255.465618134 GiB | 40216.175178 s | diagnostic failed attempt |
| M800 consumer-only retry | NA producer；复用旧 packet | 213.299564362 GiB | 17047.323762 s | raw cgroup/process diagnostic，不能冒充 fresh workflow |
| M1200 producer | RSS/PSS/USS 28.318450928/27.452210427/27.341518402 GiB | consumer 250.271244049 GiB process-tree | producer/consumer compute sum 31136.212672 s | 两个独立阶段，外层 wrapper 有 terminal bookkeeping race |
| 5 nm MPI1 | 2.46059799194 GiB RSS | 43.2886276245 GiB raw workflow max | 49346.574875 s | raw telemetry diagnostic，outer authority 缺失 |

不同 run 的峰值可以作跨 run 比较，但不得相加为同一 workflow，也不得把峰值差当作对象释放量。M800 retry 的 213.299564362 GiB 明确是 consumer-only retry process-tree/cgroup diagnostic peak；它复用了旧 packet，不是 fresh producer+consumer workflow。

M1200 consumer 的 process-tree RSS/PSS/USS peak 为 250.271244049 / 248.480698 / 248.221230 GiB，cgroup peak 251.563114 GiB，hard 余量约 4.437 GiB，swap0；该 run 的阶段 wall 来自 marker 的相邻边界，不能相加为新的 workflow authority。M1200 producer parent telemetry 的 RSS/PSS/USS peak 为 28.318450928 / 27.452210426 / 27.341518402 GiB，raw diagnostic。

## LU factor / OOC 判断

M800 retry measured corrected factor NNZ bottom/top=3.304e9/2.861e9，总计 6.165e9。derived values-only complex128 lower bound 约 91.87 GiB；按 24 B/entry 的 factor+index proxy 约 137.80 GiB。Measured M800 retry system_ready=60.85385 GiB、bottom factor ready=134.0316 GiB、consumer-only retry process-tree peak=213.299564362 GiB。

每侧 mat_solve_call_count=132（setup 28、apply 104），apply_count=1622。若每次 solve 都完整流过 factor，derived nominal traffic 约 11.8 TiB values-only 或 17.8 TiB 24 B proxy；这是粗略上界式 I/O 压力估计，OS cache 和 MUMPS block reuse 会改变实际流量，cache 也会占用内存。Task29 historical case 的 worker RSS -13.744%、cgroup -18.737%、time 1.539x、scratch 559715776 B 不可直接外推 Task41。

结论：LU factor 放 NVMe/OOC 技术上可研究，但不能可靠地把 Task41 峰值压到“几十 GiB”，并会拖慢反复 side solves。Task41 formal 继续禁止 OOC；未来可做独立 supplemental A/B。one-side staged lifecycle 或 factor-free local service 更值得单独研究，本轮不实现，也不把上述数字写成 Task41 OOC 实测。

## 阶段和优化证据

M1200 producer raw measured compute wall=15386.145391 s；四段 QEP/basis timing 为 positive right 3329.204712 s、positive adjoint 4214.234450 s、negative right 3512.904907 s、negative adjoint 4243.992494 s，reciprocal pairing 81.190811 s。producer+consumer 31136.212672 s 只是独立阶段之和。

旧 producer 的 3PN reciprocal mass MatMult 为 M800 1920000、M1200 4320000；新实现为 P+N，即 1600/2400，但仍形成全部 P×N dots 和 Hungarian assignment，不能宣称整体 1200/1800 倍提速。K0/K1/K2 Frobenius norm 由逐 mode 重算改为每 operator tuple 一次，公式和 Gate 不变。timings[reciprocal_pairing] 已进入 producer record；下一 packet 有新的 source-bound hash，必须重新过 canonical/selection Gate，不承诺 byte-identical 旧 hash。

P1 fixed sampled direct relift 使用8列；M1200 bottom/top projection 约 17.80/17.77 s，旧观察 bottom projection 5119.42975 s，只能作为工程性能对比。P2 只在 post-change code 中加入 sparse smaps 诊断；M1200 producer 发生在 P2 前，没有 post-P2 heavy speed measurement。P3 full-ready→Schur 138.2211 s 尚含旧双 SVD+LU，未测精确节省；packet coupling cleanup 未重跑 heavy，不能声称减少多少 GiB。

## 容量结论

M800/M1200 own physics 均 negative，故 accuracy-qualified frontier=NA。3 nm candidate 的 213–255 GiB 峰值且 factors 主导，只能支持一个工程推断：0.7 nm 仍需 Task40 factor-free/scalable architecture；不能作正式 0.7 nm capacity extrapolation。M1600、2 nm 及后续 MPI1 均为 NOT_RUN_DUE_TO_3NM_M800_AND_M1200_OWN_PHYSICS_GATE，绝非资源试验失败。
