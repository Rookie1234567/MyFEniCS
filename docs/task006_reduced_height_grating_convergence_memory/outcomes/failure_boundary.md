# 失败边界记录

## Assemble-only

- p=1：h=1 nm 完成 assemble-only，AIJ 矩阵约 2.179 GB，RSS upper 约 13.55 GB。
- p=2：h=2 nm 完成 assemble-only，AIJ 矩阵约 5.794 GB，RSS upper 约 19.24 GB。
- p=2：h=1.5 nm 记录到 AIJ 矩阵约 12.632 GB 后 7200 s timeout。
- p=2：h=1 nm 记录到 AIJ 矩阵约 39.628 GB 后 signal 9 failed，swap 曾达到约 37.85 GB。

## Default Direct

- p=1：最后完成 h=2 nm；h=1.5 nm 在 `stage4_dtn_augmented_ksp_setup` 被 signal 9 kill。
- p=2：最后完成 h=4 nm；h=3 nm 在 `stage4_dtn_augmented_ksp_setup` 被 signal 9 kill。
- 失败点的 RSS 只代表最后一次成功 progress 记录，不代表 MUMPS factorization 峰值。

## MUMPS OOC

默认 OOC：

- p=1 h=2 nm 完成。
- p=1 h=1.5 nm 失败，MUMPS `INFOG(1)=-90`。
- p=2 h=4 nm 5400 s timeout。

tuned OOC，`mat_mumps_icntl_14=200`：

- p=2 h=5 nm 完成，OOC scratch 约 4.95 GB。
- p=2 h=4 nm 完成，OOC scratch 约 14.24 GB。
- p=2 h=3 nm 失败，MUMPS `INFOG(1)=-90`。
- p=1 h=1.5 nm 失败，MUMPS `INFOG(1)=-90`。

当前可认为 p=2 h=4 是 reduced-height domain 中 direct/OOC 路线的最细完成点；p=2 h=3 是下一失败边界。
