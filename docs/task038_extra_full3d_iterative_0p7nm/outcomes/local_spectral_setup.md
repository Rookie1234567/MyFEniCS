# N2 local spectral setup：MPI1 controlled negative

## 结论

本轮只执行了一次 p6/h10、MPI1 的 N2 setup。N2 的 local factor Gate 要求：对每个确定性 exact-class 的局部辅助算子做 packed Cholesky，并用固定 RHS 检查 solve residual 不超过 `1e-11`。它检查的是一个局部线性代数块是否自洽，不是外层收敛率、PDE 解或物理结果。

|项目|实际值|限值/含义|分类|
|---|---:|---:|---|
|fixed RHS solve residual|`1.0426245523812324e-11`|`<=1.0e-11`|失败|
|超出限值|`4.26245523812324e-13`|不能四舍五入为通过|失败|
|相对超出|`4.26245523812324%`|固定 Gate|失败|
|worker marker wall|`125.03350535 s`|实际记录|measured|
|watchdog sampled elapsed|`126.7811168670014 s`|实际记录|measured|
|process-tree peak|`1,506,271,232 B`|warning `1,800,000,000 B`；hard `2,000,000,000 B`|partial measured|
|process-tree swap|`0 B`|必须为0|measured pass|
|watchdog samples|`127`|实际记录|measured|
|return/termination|rc=1；watchdog 未外部终止；already_exited / no orphan / no SIGKILL；natural_exit=false|受控负结果的终止事实|measured|

`1.0426245523812324e-11` 比 `1e-11` 多 `4.26245523812324e-13`，约为限值的 `4.26245523812324%`。这是实际越界，不能用显示精度或舍入把它写成 PASS。因此分类是 `CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE`，不是 watchdog 超限，也不是 PDE 性能失败。

## 生命周期边界

失败发生在 `local_factor_build`，marker 顺序为：

`preflight -> mesh_space_mpc -> JIT -> subdomain_inventory -> local_factor_build -> failure`

因此 `1,506,271,232 B` 只是到达失败点以前的 partial cold peak。它不是完整 N2 setup 的 `<2 GB` 资格，也不是 post-setup retained `<1.8 GB` 的测量。post-setup sample 数为0，252 patch/class inventory最终闭合、local modes、regional rank16、top rank32、Z16/Z32/AZ32/E32、zero identity apply和MPI2均为 `not_run_by_gate`。

worker 自行返回 rc=1；watchdog 未发 SIGTERM/SIGKILL，随后确认 process group 已退出、already_exited、无 orphan，process-tree swap 为0。原始 stop_reason 为 natural_exit，但本次 natural_exit=false，因为 worker 返回码不是0。系统全局 swap 的环境诊断值不等同于该 job 的 process-tree swap authority；本次正式资源 Gate 采用 watchdog 的 process-tree 值。

## 证据

tracked compact record：

`outcomes/records/n2_local_spectral_setup_mpi1_v1.json`

ignored 原始证据位于：

- `benchmarks/artifacts/task038_extra_full3d_n2_formal_v1/907fe8f/p6_h10_mpi1/record.json` — 6,573 B，SHA256 `32b96c90276ab6359bf62ddd6e7ab4e24fb55db82bef4fb04efb83cec22f4fb0`。
- `benchmarks/artifacts/task038_extra_full3d_n2_formal_v1/907fe8f/p6_h10_mpi1/check.json` — 3,694 B，SHA256 `7ee4b9cdc61dbf228df7074e52e06034e857cd0d04ed5ee463461eb0c5481c65`。
- `benchmarks/artifacts/task038_extra_full3d_n2_formal_v1/907fe8f/p6_h10_mpi1/watchdog.raw.json` — 179,475 B，SHA256 `cad5fbba7e76a1f6bec12f0034c6fb2b8469d17330a03dd1790ca4df013dedb0`。
- `benchmarks/artifacts/task038_extra_full3d_n2_formal_v1/907fe8f/p6_h10_mpi1/watchdog.compact.json` — 2,392 B，SHA256 `041cbd05da36a1cc023b8a84e949d9869726202883d35741adc1db621c913a22`。
- `benchmarks/artifacts/task038_extra_full3d_n2_formal_v1/907fe8f/p6_h10_mpi1/worker.log` — 2,532 B，SHA256 `7c8224c3578011d7ceaf0234e5292936cc23bf3af490ca37e9cb48f721818319`。

独立 checker 输出 `passed=false`，共12个 fail-closed success-schema 边界。它们表示负记录没有成功 setup 所需字段，并不表示又发生了12个独立数值错误；固定 local factor residual 是唯一实际数值硬 Gate 失败。原始 worker record 的 top-level `source_identity` 没有回填 `source_git_sha`（为 `null`，`tracked_status="not_measured"`），这是保留的 evidence metadata defect；其 `runtime.source_identity` 已正确绑定 `907fe8fb204cffa34a921c6d0cab7ff4dd4831b8`。未修改原始 ignored record。

## 后续边界

本轮不授权 MPI2 或 N3。不得调 solver、增加迭代、改变阈值或重跑以追逐通过；应先由 Review 判断这个 local algebra Gate 的后续处理。没有得到完整 setup 的结果前，不能声称 252 patches、factor/mode inventory、regional/top coarse、Z/AZ/E 或完整工作流内存已经资格化。
