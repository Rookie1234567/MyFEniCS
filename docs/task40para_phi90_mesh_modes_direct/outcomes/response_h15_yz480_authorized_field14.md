# H15-YZ480：唯一第14场的授权补充

本记录补充并只覆盖原13场总上限中的一个例外，不改写此前 B/X/Y/Z、D13 或其失败/通过记录。用户于 2026-10-17 明确授权：采用已审候选，执行**唯一一次**480-cell 非均匀 p6 凝聚直接完整求解；总完整场计数上限仅从13增至14。任何真实数值失败都保留并停止，不自动重跑。

候选静态文件为 `tmp/h15_y_refine_z_coarsen_480_candidate_v1.json`，SHA256 `688b99797aa25b67bf48fd1f7ca799d18ee6f814af4aba07864ec09bac996ae6`。其坐标已逐值进入独立 H15-YZ480 plan、profile 与 input：x 6格沿用 H15-Y；y 10格；z 8格；总数480。材料界面和端口坐标保留。按单元区间中点和方柱实际 x/y 覆盖独立计算的静态标签期望是 air/substrate/grating=`348/60/72`，正式 setup 仍须实测网格与标签。

| 身份 | 冻结值 |
|---|---|
| Run/profile | `task40_phi90_13p5_H15_YZ480_p6_direct_v1` / `task40para_phi90_13p5_H15_YZ480_p6_direct_v1` |
| Input / physical / resolved SHA256 | `1c6e25c48e8f86e722ee4992f6df42ee4723b97624d59937c42e2ef03291c75c` / `8b3d63f735e0fa5346ca6a03a54265a766065d4d9abdafdf884f75bb7df500a3` / `66258ee70b58b0e1073307a58f8c7c7e084cece11e0229d7e256d82c27099b25` |
| Axis counts and hashes | `[6,10,8]`; x `bb1d6be1…a5361`, y `9adb867e…b21a6`, z `3461ff84…dedd0` |
| Operator | p6 condensed direct MUMPS, 612 R13 modes SHA `1987a2b3…e522e`, surface q28, volume q15/default, scale-homogeneous relative cutoff `1e-13` |
| Single-field gates | condensed residual `<=1e-9`; independent active-A6 residual `<=1e-6`; energy error `<=1e-5`; at most two same-factor corrections |
| Resources | 64 GiB host-available floor; no fixed RSS cap; parent CPU9 / worker CPU24; MPI1 / math1; NUMA interleave0-1; PSS/USS off; swap observation only |

This run changes y and z together relative to H15-Y. It is a fixed-cell-budget redistribution observation, not a single-axis convergence test. Comparisons with H15-Y and same-policy D13-Y2/Y3 cannot isolate y from z; finite R13 remains `FULL_DTN_NOT_VERIFIED`, and overall status remains `AUTHORITY_LIMITED`.

At this record's creation the field is `AUTHORIZED_NOT_RUN`; the live run receipt and measured results must be appended after natural termination. The original 13-field contract remains preserved as historical evidence, with this file recording the single authorized exception.
