# 失败边界记录

## Assemble-only

- p=1：h=1 nm 完成 assemble-only，AIJ 矩阵约 2.179 GB，RSS 上界约 13.55 GB。
- p=2：h=2 nm 完成 assemble-only；h=1.5 超时；h=1 在 base matrix assembled 后被 signal 9 kill。
- p=2 h=1 的 base matrix rows=16,992,540，nnz=1,767,279,728，AIJ 矩阵估计约 40.58 GB，已明显超过当前 14 GB WSL 可承受范围。

## Default Direct

- p=1：最后完成 h=2 nm，第一个失败 h=1.5 nm，失败阶段 `stage4_dtn_augmented_ksp_setup`。
- p=2：最后完成 h=4 nm，第一个失败 h=3 nm，失败阶段 `stage4_dtn_augmented_ksp_setup`。

## MUMPS OOC

- p=1：h=2 nm 完成；h=1.5 nm 仍失败，未突破 default direct 的失败边界。
- p=2：h=4 nm OOC 运行 5400 s 超时；由于前一个边界点都未稳定完成，本轮未继续 h=3 OOC。

## MPI=1

- p=1：h=5/h=3 完成，h=2 超时。
- p=2：只完成 h=5；h=4 未运行，原因是 MPI=8 default direct 已耗时约 1800 s，MPI=1 预计过慢。
