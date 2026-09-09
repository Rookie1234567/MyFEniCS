# 笔记本 Codex 的最小元数据移交

目的：核对工作站 R1 的通道哈希差异和 p4 装配变慢，不启动新的 PDE，不修改历史成功目录，不复制虚拟环境或系统库。

请在 `task39extra_para_workstation_capacity` 分支的独立 worktree 中，先 fetch 最新远端，新增 `docs/task39extra_para_workstation_capacity/outcomes/records/laptop_handoff/` 下的小型文件并提交、普通 push。不要修改求解器、任务书、既有记录，不在 master、task41 或 task39extra 提交本移交。目录已存在时新增唯一命名文件，保留原件。

定位依据：`docs/task039_extra_physical_multilevel/outcomes/records/balanced_coupling_v5.json` 的 evidence，尤其 `benchmarks/artifacts/task39extra/v5_balanced/balanced_chain_raw_index.json`。原始成功 source 为 `2bb6770ad00b35881558c576e7296e250656e571`，notch 为 `094204b7281fe867744fe334e8753d2faebaf89b`。

需要以下小型资料，保留实际 provenance；找不到的字段写 missing，不猜测：

1. **原始完整 ordered mode manifest 原字节**，即 `build_ordered_mode_manifest` 返回的 encoded bytes，包含全部 80 通道的 side/m/n/polarization、alpha/gamma/beta、k/e/h vector、材料、功率、projection_denominator、traction_vector 等。预期旧 SHA256 为 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`。优先取历史保存文件，复制时不要重新排版 JSON。若历史文件没有，只用原 V5 输入和可核实的源代码/环境做轻量 inventory 重建，不生成 mesh、不装配；明确标 reconstructed、实际生成 source/环境/新 SHA，不能冒称旧原件。original/notch 相同通道无需复制两份，但各自标明来源。
2. **原始成功 R1 的 run_manifest、resolved_config、阶段时间小型记录**；若文件很大，提取带原路径和原文件 SHA 的 compact。需要能区分 JIT、p4 volume assembly、symbolic、numeric 和 solve_started；同时给出旧实际 MPI/线程设置。
3. **环境/编译证据**：CPU 型号；Python、NumPy、DOLFINx、Basix、FFCx、UFL、dolfinx_mpc、PETSc、MUMPS、GCC 版本；旧记录的 JIT cffi_extra_compile_args、有效 dolfinx_jit_options.json、FFCx options、相关 CFLAGS（只选这些字段，不导出全环境、凭据或 SSH 配置）。当前环境探针与历史运行记录分列，不能把当前版本冒充当时版本。
4. **旧 p4 volume 积分内核索引**：生成 C 文件名、大小、SHA256、exported tabulate_tensor 函数名、可核实编译命令/flags；无需上传 C 大文件或 .so。工作站当前热点为 `tabulate_tensor_integral_3e66f9d7904562beb69d74a67b0019cea5c86d37_hexahedron`，文件为 `libffcx_forms_79799d564a37286318398a320ab6392da8558533.c`，512 quadrature points、300×300 local tensor。旧文件名不同则记录实际值，不强行套用。

大矩阵、LU、JIT 二进制、完整场不提交 Git。可另外在索引中列出旧完整解/reference 数组的文件名、字节数、SHA256、canonical map 文件和来源；后续如确需搬运，再走合适的数据渠道。

完成后回复分支和完整 commit SHA，以及旧 manifest 是否取得或仅重建。工作站在身份桥验证前不替换固定哈希、不重跑正式 R1。
