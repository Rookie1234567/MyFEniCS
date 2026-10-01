# Full3D y-orbit reference-inverse pilot

本case为真正三维80-cell/p2、缩放几何的代数架构试验，保留全部y blocks、内部DoF及532真实DtN aliases，并验证nonseparable notch的完整原A residual。不是原尺寸目标解、p2物理精度、2 TB或48h资格。

## Source与实际命令

成功source为18d7d0a27f73705366f8cb747c11cb9e68cc0ef6；source-clean/ABI及最终3个focused tests通过。使用同一shell激活自有cloud complex环境。正式入口已有dedicated subreaper whole-tree watchdog（1.5GiB/600s/zero swap/one thread），不再外加短timeout。

```text
source ../complex_env_setup/activate_cloud_complex.sh
python -m benchmarks.run_y_orbit_reference_probe --run --expected-head 18d7d0a27f73705366f8cb747c11cb9e68cc0ef6 --run-directory benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_p2_attempt2
python -m benchmarks.check_y_orbit_reference_probe benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_p2_attempt2
Y_ORBIT_PILOT_EVIDENCE=benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_p2_attempt2 python -m pytest -q src/test/test_task40extra_y_orbit_reference.py
```

重跑需要协调方明确授权、新artifact目录与真实source HEAD；上述目录已经存在，runner会拒绝覆盖。attempt1保留readonly Vec callback API failure；attempt2复用其JIT cache，所以8.839秒不是cold-success时长。phi0的y phase=1，phi5未运行。

[结果/数学身份/失败与边界](../../../../docs/task40extra_dot_parallel_cloud/outcomes/y_orbit_full3d_pilot_v1.md)；[hash-bound compact](../../../../docs/task40extra_dot_parallel_cloud/outcomes/records/y_orbit_full3d_pilot_v1.json)；[冻结计划](plan.json)。
