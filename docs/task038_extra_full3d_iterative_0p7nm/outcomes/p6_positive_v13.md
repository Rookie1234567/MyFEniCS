# V13 C1 p6/h10 exact-input positive qualification

## 这项资格证明了什么

positive source 资格的通俗含义是：用几个固定诊断向量检查一个固定的 p6→p3→p1 预条件器，确认它在正定辅助算子上能够稳定地压低误差。它不是含波动、物理散射和 Fourier-DtN 的 Maxwell 求解；后者必须在 P0 中单独测量真实残差、内存和 official physics。

V13 的四个 source 都在同一个精确输入身份下完成了 MPI1 formal。每案使用 right-preconditioned GMRES、restart=20、cycle_max_it=20、max_it=10000、每 20 步 explicit true-residual replacement、solution-only checkpoint=500；process-tree hard RSS 为 2,000,000,000 B，swap Gate=0。

## 身份与架构

| 项目 | 固定事实 |
|---|---|
| input | input/templates/full3d_iterative_example.dat，SHA 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41 |
| physical configuration | physical model SHA 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f；grazing=1°、theta=89°、phi=0°、s、13.5 nm、p6/h10 |
| levels | same physical mesh，p6→p3→p1；p6 matrix-free，p3/p1 sparse positive matrices |
| selected hierarchy | same_mesh_hcurl_pmg_v1_requalified |
| forbidden objects | p6 global AIJ、global dense transfer、numeric allgather、p6 factor、physical/DtN solve、recovery |
| evidence schemas | positive worker/marker/checker lineage v4 |

## 四源结果

| source | source SHA | iterations | final explicit true residual | matvec / PC / KSP destroy | action total | raw samples | peak RSS / retained RSS | swap |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| random | 0da00e98c0423ade6cea38cabc3c8415ea32510e | 200 | 5.550975220267439e-9 | 209 / 210 / 10 | 223 | 29,428 | 1,517,903,872 / 772,497,408 B | 0 |
| gradient | 82c56d92ac80ddf84071a6e1eff6d28e3513af7e | 220 | 2.7889793119815017e-9 | 230 / 231 / 11 | 245 | 29,315 | 1,516,544,000 / 770,650,112 B | 0 |
| curl | 48866f2990a12113a28e556e6956104625b3da34 | 180 | 5.6105046279899595e-9 | 188 / 189 / 9 | 201 | 26,392 | 1,536,192,512 / 790,028,288 B | 0 |
| checkerboard | 80b0d8d36364007f4dda941d7770a307eee15dd4 | 200 | 7.760965317017376e-9 | 209 / 210 / 10 | 223 | 30,809 | 1,533,190,144 / 786,751,488 B | 0 |

每案均为 natural exit、no orphan、all watchdog samples readable。每案 action ledger 也闭合：random 为 driver explicit=11、extra=3、explicit total=14、action total=223；gradient 为 12、3、15、245；curl 为 10、3、13、201；checkerboard 为 11、3、14、223。四案 checker 的 contract_errors 与 gate_failures 均为空。

## 证据索引

四组 worker、watchdog compact、checker compact 均位于 outcomes/records，文件名分别以 same_mesh_hcurl_pmg_p6_positive_exact1_{random,gradient,curl,checkerboard}_v4 开头。相应的 source SHA 也绑定各自 ignored artifact root，不能把四案合并成一个未绑定 SHA 的“总记录”。

本阶段证明的是 C1 positive hierarchy qualification；P0 physical 并未因这四项通过而自动通过。P0 的 cold setup 资源 hard stop 见 p6_physical_v13.md。
