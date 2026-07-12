# 编号功能 Benchmark 索引

本目录是“某项能力由什么问题、什么参数和什么证据证明”的目录。重型输出仍写 `benchmarks/artifacts/`；case README 只链接配置、测试和 `benchmarks/records/`。`recorded` 表示有 canonical machine-readable record；`test-backed` 表示目前只有自动测试/轻量入口，不能宣称生产数值资格。

| ID | 能力 | 状态 | 顶层证据 |
|---|---|---|---|
| 001 | 2D TM PML + Floquet | test-backed | 2D tests/旧 validation |
| 002 | 2D TM DtN explicit/auxiliary | recorded | `2d_zero_contrast_dtn_smoke.json` |
| 003 | 2D TE/TM + 复材料吸收 | test-backed | TE/absorption tests |
| 010 | 3D Stage1 airbox | recorded | `3d_stage1_mpi2_smoke.json` |
| 011 | 3D Stage2A double Floquet | test-backed | test 05/06/17 |
| 012 | 3D Stage2B PML | test-backed/experimental | test 02/07/09/10 |
| 013 | 3D Stage2C Fresnel | test-backed/experimental | test 03/08/09/10 |
| 020 | 3D Stage4A flat DtN | test-backed | flat/DtN tests |
| 021 | 3D Stage4B direct | recorded | direct h5/h3 records |
| 022 | auxiliary/explicit/matrix-free 等价 | test-backed | test 22 |
| 030 | MUMPS OOC/BLR | test-backed/experimental | test 18/19、历史报告 |
| 031 | workstation iterative h5/h3/h2 | recorded/qualified | 三个 iterative records |
| 040 | MPI/p/algebra regression | test-backed | Level2 + test suite |

每个 README 使用相同 22 项契约。缺少 record 的 case 仍有价值：它明确告诉维护者还差什么证据，防止能力矩阵把“代码存在”写成“工程已验证”。
