# Implementation Notes

## 本轮实现

1. 增加 MUMPS-BLR FGMRES profiles：`eps=5e-3/1e-3/1e-4/1e-5/1e-9`。
2. 增加 shifted Maxwell 与 positive Maxwell minimal profiles，均走 `KSP.setOperators(A, P)`，其中 `A` 是原始 DtN augmented 系统，`P` 是辅助预条件矩阵。
3. 对 BLR profiles 使用 `fgmres + right preconditioning + unpreconditioned norm + true residual monitor`，避免 task009 中残差口径混乱。
4. 对 shifted/positive profiles，装配 constrained FE block 的 P，并给 DtN auxiliary block 加单位对角；当前没有构造 DtN Schur 近似，因此记录为 `identity_auxiliary_block_no_dtn_schur_coupling`。
5. `run_3d_matrix_scale.py` 新增 BLR、P 矩阵、A/P nnz、A/P 内存估算、`pc_side`、`ksp_norm_type`、operator preconditioner 标志等字段。
6. 单元测试增加 task010 profiles 的 PETSc options 和 metadata 断言。

## 重要边界

- MUMPS-BLR 的 compression ratio 没有从当前 PETSc/petsc4py summary 中稳定暴露，本轮只记录 BLR 开关、epsilon、迭代数、RSS 上界和直接解对照。后续若要写入真实压缩率，需要接入 MUMPS verbose/INFOG 字段或 PETSc MatMumps 专用查询。
- shifted/positive minimal P 当前只是验证 `A/P` 双矩阵路径和物理近似矩阵装配；它不是完整 HX/AMS，也没有 nodal auxiliary space 或 discrete gradient。
