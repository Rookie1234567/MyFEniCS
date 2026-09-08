# Lifecycle and release before recovery

## 20260907 fresh attempt

该 producer+consumer attempt 在 consumer_exit(solution_snapshot_destroyed) 失败，分类为 IMPLEMENTATION_FAILURE。因此不能把它写成 formal solve/recovery success；consumer_summary 的 formal_result/gates/physics=null。其 producer 与 consumer/workflow 资源测量仍作为独立 resource evidence 保留。diagnostic lifecycle 记录 actions_destroyed=true、component_cleanup_pass=true、factor_cleanup_pass=true、factor_count_after_cleanup bottom/top=0/0、rss_drop=pass、memory authority=274205020160→260347596800 B；producer/consumer/workflow wall=18000.658898/22215.056788/40216.175178 s。

## 20260908 consumer-only retry

retry 的线性 solve 与 recovery mechanics 通过，own physics 因 abs(A_balance-A_volume)=1.9160032445286745e-5>1e-5 失败，authority 保持 candidate negative，official RTA unavailable。

| lifecycle Gate | 结果 |
|---|---|
| factor mode | MUMPS factor-only；ICNTL14=40；无 global direct/coarse/OOC |
| corrected bottom/top factor NNZ | 3.304e9 / 2.861e9 |
| bottom/top factor inventory | 1/1→0/0 |
| actions/components | destroyed |
| RSS drop | pass |
| cgroup authority | 229028663296→218838220800 B |
| final marker memory | 211014574080 B |

上述 release-before-recovery 证据不能覆盖 physics Gate，也不能把 candidate R/T/A 变成 official。失败 root、consumer summary 和 negative authority 必须保留。
