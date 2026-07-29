# Path A cycle 0 v28 action preflight

本文件由现有 v28 raw artifact 离线重放生成。数值 authority 固定为
`f1ba5627f163da54fa383b43be58fd38c0da7bc9`；没有运行 PDE、没有写 transition bundle、没有执行 selected
action，也没有推进 cycle。

## 冻结的两个独立 action

| action | selection role | target set | closure set | predicted FE DoF / rows / matrix NNZ / factor NNZ / peak bytes |
|---|---|---|---|---:|
| selected-p | `production_dorfler_marking` | `cell:r13:l0:i0:j0:k0`, `cell:r37:l0:i0:j0:k0`, `cell:r42:l1:i1:j0:k0`, `cell:r42:l1:i1:j1:k0` | 无 | `93 / 14 / 11830 / 73681 / 1711228` |
| selected-h | `verification_only_marking` | `cell:r47:l1:i1:j0:k1` | `cell:r45:l1:i0:j0:k1` | `14 / 7 / 19604 / 37025 / 1133084` |

上述 peak 仅为由实测 current/shadow endpoint 差分校准的
matrix/factor/vector 结构代理；它明确排除 MPI runtime、allocator arenas、
JIT、mesh、field 与 controller/postprocess 公共成本，不能冒充 future
candidate 的实测 process-tree RSS。

## 建议

若下一轮另行授权第一次 action，建议先验证 **selected-p**。原因是 p lane
已经给出 `REFERENCE_BLIND_LOCAL_MARKING_PASS` 的正式 Dörfler 正信号；h lane
仍是 `REFERENCE_BLIND_VERIFICATION_ONLY`，并带一个 periodic closure target。
两者没有合并为 combined action。

## 冻结状态

```text
selected_action = not_run
transition = not_run
candidate = not_run
cycle_advanced = false
combined_action = forbidden_not_constructed
```

JSON payload SHA-256：`7f57f2bacaf564268b0bd22a965fe8fc1504792b77fe549eb47d7fbab2b901a6`。
