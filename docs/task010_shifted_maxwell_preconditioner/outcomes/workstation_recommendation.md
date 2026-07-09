# Workstation Recommendation

## 当前本机边界

| case | result | note |
|---|---|---|
| p=2 h=2 eps=1e-5 | 收敛 | 4 iterations，RSS upper 约 17.85 GB |
| p=2 h=2 eps=1e-4 | 收敛 | 7 iterations，RSS upper 约 18.09 GB |
| p=2 h=2 eps=1e-3 | 超时 | 1800s 未完成 |
| p=2 h=1.5 eps=1e-5 | signal 9 killed | KSP setup 阶段失败，未进入正式解 |

## 推荐工作站顺序

| order | case | profile | RAM guidance | decision |
|---:|---|---|---:|---|
| 1 | p=2 h=1.5 | eps=1e-5 | 最低 64 GB，建议 128 GB | 第一优先级 |
| 2 | p=2 h=1.5 | eps=1e-4 | 最低 64 GB，建议 128 GB | eps=1e-5 失败时复跑 |
| 3 | p=2 h=1.0 | eps=1e-5 | 最低 256 GB，建议 512 GB | h=1.5 成功后再跑 |
| 4 | p=2 h=0.75 | eps=1e-5 | 最低 512 GB，建议 1 TB | h=1 成功后再跑 |
| 5 | p=2 h=0.5 | eps=1e-5 | 可能超过 1 TB，建议 2 TB 级别再考虑 | 当前不建议直接跑 |

## 估算口径

估算基于 h=2 的 empirical RSS upper / AIJ matrix memory 比例和近似 h^-3 缩放。由于 MUMPS factorization 有瞬时 workspace 峰值，推荐 RAM 必须留出 2x 以上余量。h=1.5 在本机 signal 9 说明真实峰值可能高于 CSV 采样到的 RSS upper。
