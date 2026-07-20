# 编号功能 Benchmark 索引

本目录是“某项能力由什么问题、什么参数和什么证据证明”的目录。重型输出仍写 `benchmarks/artifacts/`；case README 只链接配置、测试和 `benchmarks/records/`。`recorded` 表示有 canonical machine-readable record；`test-backed` 表示目前只有自动测试/轻量入口，不能宣称生产数值资格。

| ID | 能力 | 状态 | 顶层证据 |
|---|---|---|---|
| [`001`](001_2d_tm_pml_floquet/README.md) | 2D TM PML + Floquet | test-backed | case config/run + 2D tests |
| [`002`](002_2d_tm_dtn_equivalence/README.md) | 2D TM DtN explicit/auxiliary | recorded | explicit、auxiliary、comparison 三份 record |
| [`003`](003_2d_te_tm_complex_absorption/README.md) | 2D TE/TM + 复材料吸收 | recorded | TM/TE 两份 lossy record + automatic gates |
| [`010`](010_3d_stage1_airbox/README.md) | 3D Stage1 airbox | recorded | SHA-pinned Stage1 record |
| [`011`](011_3d_stage2a_floquet/README.md) | 3D Stage2A double Floquet | test-backed | test 05/06/12/17 |
| [`012`](012_3d_stage2b_pml/README.md) | 3D Stage2B PML | experimental | test 02/07 + case contract，精度未资格化 |
| [`013`](013_3d_stage2c_fresnel/README.md) | 3D Stage2C Fresnel | experimental | test 09/10 + case contract，精度未资格化 |
| [`020`](020_3d_stage4a_flat_dtn/README.md) | 3D Stage4A flat DtN | test-backed | flat/DtN tests，待冻结独立 record |
| [`021`](021_3d_stage4b_direct/README.md) | 3D Stage4B direct | recorded | h5/h3 canonical + h2 reviewed reference |
| [`022`](022_dtn_condensation_equivalence/README.md) | auxiliary/explicit/matrix-free 等价 | test-backed | fixture/expected + test 22 |
| [`030`](030_mumps_ooc_blr/README.md) | MUMPS OOC/BLR | experimental | profile/OOC tests，非迭代法 |
| [`031`](031_workstation_iterative/README.md) | workstation iterative h5/h3/h2 | recorded/qualified | 三个 SHA-pinned iterative records |
| [`040`](040_mpi_p_algebra_regression/README.md) | MPI/p/algebra regression | test-backed | fixture/expected + Level2 suite |
| [`050`](050_stage4_direct_memory_forensics/README.md) | Stage4 direct memory forensics | diagnostic_success | 最佳 h3 -15.119%；当前 image threaded direct unavailable；h2/threaded h3 均按 Gate 未运行 |
| [`060`](060_multilevel_hcurl_iterative_solver/README.md) | Task30 H(curl) transfer 与 compact low-memory iterative | workstation_success experimental | p/h coarse solver-negative；h5/h3/h2 通过，h2 1873 步、9.375 GB |
| [`070`](070_compact_physical_slab_memory_optimization/README.md) | Task31 matrix-free compact physical-slab memory-first | strong_memory_success experimental | clean h5/h3/h2；h2 1977 步、7.898 GiB、无 swap；solve 约 5.01x |
| [`080`](080_hybrid_fem_modal_direct_baseline/README.md) | Task32 Hybrid FEM-modal direct baseline | Phase 0–10 complete；`hybrid_direct_engineering_success`；h2 not_run；302/302 | clean h5/h3 full3D + M120/M160 Hybrid、QEP/modes/propagation/trace、E/H/absorption、Schur、funnel、30-point smoke、six-path memory；current direct 0.7 nm not scalable |
| [`090`](090_high_order_3d_floquet_hcurl/README.md) | Task33 p1–p4 high-order 3D Floquet | stage complete | clean source 下 MPI1/2/4 各 48、共 144 PDE；p3/p4 核心 Gate 通过 |
| [`091`](091_hybrid_hp_adaptivity_feasibility/README.md) | Task33 high-order/Hybrid fixed-p feasibility | reduced scope complete；p3/h5 同阶 closure；p3/h7.5 fixed-p clear success；p4 resource negative；variable-p fail closed；adaptive transferred | Stage1--5、D1/D2、source split 与 reduced completion tracked records；原 21-role full scope 保持 `NOT_RUN` |
| [`092`](092_workstation_wsl_adaptive_scalability/README.md) | Task034 WSL 工作站、hardening、资源与 adaptive 总记录 | in progress | WSL qualification、p3/h3、p4/h5、用户新增点和资源 Gate |
| [`093`](093_fixed_geometry_ph_convergence_mpi/README.md) | Task034 固定结构 p2/p3/p4 收敛、同阶 closure 与 MPI identity | canonical partial（用户批准缩减范围） | 9 个 S 偏振同阶 closure positive、p3/h10 Hybrid negative、p3/h5 MPI1/8/16 identity + MPI32 exploratory |

每个 README 使用相同 22 项契约，并在表后展开物理问题、参数、PyCharm、CLI、代码路径、结果、解释和限制。Recorded case 至少包含 `config.json`、`expected.json`、可执行 `run.sh` 与 `records/`；纯代数 case 用 `fixture.json` 和 `test_command.txt` 代替几何配置。缺少 record 的 case 仍有价值：它明确告诉维护者还差什么证据，防止能力矩阵把“代码存在”写成“工程已验证”。

canonical lightweight record 可以提交 Git；完整 mesh、field、VTU 和长日志必须写到 gitignored `benchmarks/artifacts/`。Case021/031 的 case-local reference 通过 SHA-256 指向顶层既有 records，避免复制两份数值产生漂移。
