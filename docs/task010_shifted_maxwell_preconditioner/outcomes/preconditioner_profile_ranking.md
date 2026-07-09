# Preconditioner Profile Ranking

## 总排序

| rank | profile/family | decision | evidence | next use |
|---:|---|---|---|---|
| 1 | `iter_fgmres_mumps_blr_eps1e-5` | 当前第一候选 | h=2 收敛，4 iterations，R/T/A 与 direct LU 一致；h=3/2.5/2 都稳定 | 工作站优先 h=1.5，然后 h=1 |
| 2 | `iter_fgmres_mumps_blr_eps1e-4` | 可作为折中备选 | h=2 收敛，7 iterations，R/T/A 一致；资源与 eps=1e-5 接近 | 若 eps=1e-5 在工作站出现问题，可复跑 |
| 3 | `iter_fgmres_mumps_blr_eps1e-3` | 粗网格可用，h=2 不推荐 | h=5/4/3/2.5 收敛，但 h=2 在 1800s 超时 | 仅作压缩强度对照 |
| 4 | shifted Maxwell minimal P + ASM/ILU0 | 保留基础设施，不作为 solver | h=5/h=4 均 1000 步未收敛，true residual 约 0.71-0.94 | 不继续盲调 ASM/ILU |
| 5 | positive Maxwell minimal P + ASM/ILU0/local LU | 保留基础设施，不作为 solver | h=5/h=4 均未收敛，best true residual 约 0.18-0.26 | 后续只作为 HX/AMS 的 P-form 雏形 |

## 推荐

下一步不应继续投入 Jacobi/ASM/ILU 黑盒调参。短期 production 路线是 MUMPS-BLR；中期研究路线是完整 Hiptmair-Xu / hypre AMS，而不是当前 minimal positive P。
