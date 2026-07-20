# MPI scalability 与 numerical identity

用户批准将代表性 S polarization p3/h5 作为 MPI 数量影响验证点。Full3D 与 Hybrid
M160 均在独立进程、同一方法内相同 clean SHA 下完成 MPI1/MPI8/MPI16；MPI32 为
exploratory，不能替代 MPI16。

| 方法 | MPI1 | MPI8 | MPI16 | MPI32 | 结论 |
|---|---|---|---|---|---|
| Full3D | identity pass | identity pass | identity pass | exploratory pass | qualified |
| Hybrid M160 | identity pass | identity pass | identity pass | exploratory pass | qualified |

checker 逐行重算/验证 official identity、true residual、R/T/A/A_volume drift、五平面与
接口 drift、significant-order power/amplitude/phase、beta、结构与 config identity、
zero swap 和 no oversubscription。正式 required set 固定为 `[1, 8, 16]`。

本结论只证明数值结果不受代表性 MPI rank 数量影响，不声称每个 p/h 都完成了 MPI
矩阵，也不把更多 rank 自动解释为更快。按照用户批准范围，MPI 数量扩展到此关闭，
MPI8 保持生产/开发 baseline。
