# 生命周期与 recovery 前释放证据

## 3 nm M800

Fresh 20260907 attempt 在 solution_snapshot_destroyed 失败，但其 failed attempt lifecycle diagnostic 完整：actions_destroyed=true、component_cleanup_pass=true、factor_cleanup_pass=true、bottom/top factor count 1/1 -> 0/0、rss_drop pass；memory authority 274205020160 -> 260347596800 B。producer/consumer/workflow wall 为 18000.658898 / 22215.056788 / 40216.175178 s。这证明 cleanup 证据存在，但不把该 attempt 升级为 formal PASS。

M800 consumer-only retry 的 factor count 为 1/1 -> 0/0，actions/components destroyed，cleanup 和 rss_drop pass；cgroup authority 229028663296 -> 218838220800 B，final marker memory 211014574080 B。该 root 复用旧 packet，不能与 fresh producer peak 拼成同一 workflow。

## 3 nm M1200

producer packet 已完整写出并被 consumer retry hash-bound 复用；producer outer terminal sample race 与 packet 数值成功分开记录。producer raw parent telemetry peak 是 28.318450928 GiB，compute wall 15386.145391 s，packet bytes=1370082162，write max-rank 1.167526111 s，swap0。

consumer worker 在 recovery 后完成：factor count bottom/top 1/1 -> 0/0，actions/components destroyed，component/factor cleanup pass，collective cleanup completed，rss_drop pass。outer release 的 raw memory authority 为 before_high_water=50735435776 B、after_cleanup=47047143424 B，即十进制约 50.735 -> 47.047 GB，二进制约 47.2510566711 -> 43.8160667419 GiB。process-tree/cgroup peak 为 250.271244049/251.563114 GiB，swap0；outer supervisor 最终只因 terminal transition 的 incomplete resource authority 报 bookkeeping failure，不能改写 solve、recovery mechanics 或 physics negative。

## 5 nm MPI1

最后 MPI1 attempt raw memory_stages 有 61912 个 consumer samples，均 readable=true、swap0。producer/consumer/workflow wall 为 12285.1455821 / 37058.1461057 / 49346.574875 s，phase-separated diagnostic peak 为 2.46059799194 / 43.2886276245 / 43.2886276245 GiB，不求和。terminal process-tree unreadable 造成 outer task041_resource_sample_failure，所以 raw peak 不是 qualified resource PASS。

## 语义边界

不同 run 的 peak 可以比较，不能相加；peak 差不能直接解释为 lifecycle release bytes。producer 必须完全退出后才启动 consumer，workflow peak 是不重叠阶段的 max。M800/M1200 的 physics negative 永久保留，M1600 及后续未运行项不因 cleanup pass 而自动释放。
