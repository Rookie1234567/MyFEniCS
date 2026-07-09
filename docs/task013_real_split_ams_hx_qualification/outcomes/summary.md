# 结果总结

## 任务

Task013 是 real-split AMS/HX 的 qualification / go-no-go 任务，不是 production solver 实现任务。本轮新增一个隔离的实验脚本：

```text
src/studies/run_real_split_ams_qualification.py
```

脚本在 real PETSc 模式下显式构造 FE-only complex Maxwell block 的等价 real split 系统，并用 Python PC apply 调用 real hypre AMS。这样可以绕开 task011 中 complex hypre AMS 的崩溃风险，同时不修改正式 Stage 4 求解主线。

## 分支

```text
codex/20260707-real-split-ams-hx-qualification
```

## 总体结论

本轮得到 B 档结果：

```text
FE-only real-split AMS/HX 路线值得继续研究，但尚不能作为 production Stage 4 solver 合并。
```

最关键正结果是：

| case | auxiliary | status | iterations | true residual | RSS |
|---|---|---|---:|---:|---:|
| p=2 h=5 FE-only | H1 degree = p | converged | 310 | 9.964e-7 | 1.323 GB |

最关键限制是：

| 限制 | 含义 |
|---|---|
| 仍是 FE-only | 不含 Floquet MPC、DtN auxiliary 和 official R/T/A |
| standard H1=p+1 很贵 | p=2 h=5 RSS 到 6.306 GB，且 150 步 residual 与 Jacobi 接近 |
| same-H1 虽然省内存但迭代多 | p=2 h=5 需要 310 步才达到 rtol |
| full Stage 4 未进入 | 因为需要单独实现 real split 与 MPC/DtN FE/aux block 的安全集成 |

因此本轮建议：

```text
merge_code: no
merge_docs_only: yes / optional
recommended_next_branch: codex/20260708-real-split-stage4-reduced-block-pc
```

## 1. real split 等价性是否通过？

通过。所有测试 case 的 real block matvec 与手工 real/imag block 作用一致到 `1e-16` 量级。

| case | p | h/nm | auxiliary | n complex | n real | nnz real | matvec error | RSS assembly |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| p1 h10 | 1 | 10 | standard | 906 | 1,812 | 90,360 | 1.346e-16 | 0.177 GB |
| p1 h5 | 1 | 5 | standard | 5,183 | 10,366 | 580,892 | 1.404e-16 | 0.207 GB |
| p2 h10 | 2 | 10 | standard | 6,100 | 12,200 | 2,166,080 | 1.606e-16 | 0.301 GB |
| p2 h5 | 2 | 5 | standard | 37,446 | 74,892 | 14,233,968 | 1.659e-16 | 1.081 GB |
| p2 h5 | 2 | 5 | same | 37,446 | 74,892 | 14,233,968 | 1.659e-16 | 1.042 GB |
| p2 h5 | 2 | 5 | linear | 37,446 | 74,892 | 14,233,968 | 1.659e-16 | 1.058 GB |
| p2 h4 | 2 | 4 | same | 82,878 | 165,756 | 32,230,224 | 1.671e-16 | 1.924 GB |

## 2. real-split AMS/HX 是否比 Jacobi 改善 true residual？

答案是：在 p=2 h10 上明显改善；在 p=2 h5 上，标准 AMS 不理想，same-H1 auxiliary 才是可继续路线。

| case | profile | aux | max it | status | iterations | true residual | RSS |
|---|---|---|---:|---|---:|---:|---:|
| p2 h10 | Jacobi | none | 1000 | not converged | 1000 | 5.846e-3 | 0.301 GB |
| p2 h10 | blockdiag AMS | standard | 1000 | converged | 219 | 9.918e-7 | 0.888 GB |
| p2 h5 | Jacobi | none | 50 | not converged | 50 | 2.887e-3 | 1.080 GB |
| p2 h5 | AMS | standard | 50 | not converged | 50 | 3.515e-5 | 6.306 GB |
| p2 h5 | AMS | same | 50 | not converged | 50 | 9.502e-6 | 1.322 GB |
| p2 h5 | AMS | linear | 50 | not converged | 50 | 7.764e-5 | 1.322 GB |
| p2 h5 | Jacobi | none | 150 | not converged | 150 | 7.605e-6 | 1.080 GB |
| p2 h5 | AMS | standard | 150 | not converged | 150 | 8.004e-6 | 6.306 GB |
| p2 h5 | AMS | same | 150 | not converged | 150 | 2.602e-6 | 1.324 GB |
| p2 h5 | AMS | same | 350 | converged | 310 | 9.964e-7 | 1.323 GB |

## 3. p=2 h=5 是否收敛？内存如何？

是，但只有 `same-H1 auxiliary` 达到了可接受的内存和收敛组合：

| auxiliary | H1 dofs | G nnz | iterations | true residual | RSS after solve | 结论 |
|---|---:|---:|---:|---:|---:|---|
| standard H1=p+1 | 42,160 | 4,130,355 | 150 | 8.004e-6 | 6.306 GB | 内存高，速度慢，不推荐 |
| same H1=p | 13,167 | 1,572,090 | 310 | 9.964e-7 | 1.323 GB | 本轮最佳 |
| linear H1=1 | 1,914 | 354,855 | 50 | 7.764e-5 | 1.322 GB | 很便宜但太弱 |

## 4. p=2 h=4 是否仍触发内存压力？

本轮只做 equivalence-only / memory audit，没有求解。p=2 h4 same-H1 的显式 real block 组装 RSS 约 `1.924 GB`，没有触发内存压力。

| case | n real | nnz real | B nnz | G cols | G nnz | RSS assembly |
|---|---:|---:|---:|---:|---:|---:|
| p2 h4 same-H1 | 165,756 | 32,230,224 | 8,057,556 | 28,755 | 3,551,549 | 1.924 GB |

但没有运行 AMS setup/solve，因此不能声称 p=2 h4 已解决。task011 中 standard p=2 h4 曾触发 Docker memory pressure；same-H1 可能缓解，但需要下一轮专门测试。

## 5. low-order / p-coarsened auxiliary 是否降低内存？

是，且效果很明显。

| auxiliary | H1 dofs | G nnz | AMS setup RSS after | 50-step residual | 判断 |
|---|---:|---:|---:|---:|---|
| standard H1=p+1 | 42,160 | 4,130,355 | 6.306 GB | 3.515e-5 | 内存过高 |
| same H1=p | 13,167 | 1,572,090 | 1.322 GB | 9.502e-6 | 最佳 |
| linear H1=1 | 1,914 | 354,855 | 1.322 GB | 7.764e-5 | 太弱 |

## 6. reduced Stage 4 是否可运行？

未运行。原因不是 FE-only 失败，而是本轮有意不把实验性 Python PC 接入正式 Stage 4/MPC/DtN 主线。

进入 reduced Stage 4 需要新增：

```text
1. MPC 后 real split block 的安全构造；
2. FE block 与 DtN auxiliary block 的 real split 索引映射；
3. AMS PC 只作用于 FE block、aux block 用 identity/exact small solve；
4. true residual 与 official R/T/A 的守门逻辑。
```

这些已经超出本轮 isolated qualification runner 的安全范围。

## 7. full Stage 4 p=2 h=2 是否运行？

未运行。理由同上：full Stage 4 需要先通过 reduced Stage 4 real split PC 集成。没有运行 official R/T/A，也没有生成迭代 R/T/A。

参考 direct/BLR 仍为：

| source | R | T | A | RSS |
|---|---:|---:|---:|---:|
| direct p2 h2 | 0.001342932846 | 0.599213229444 | 0.399443837710 | 20.53 GB |
| BLR eps=1e-5 p2 h2 | 0.0013429328 | 0.5992132289 | 0.3994438376 | 17.85 GB |
| task013 | not run | not run | not run | not run |

## 8. full Stage 4 p=2 h=1.5 是否突破？

未运行。h=1.5 breakthrough 必须等待 full Stage 4 h=2 real-split validation 成功。

## 9. 是否建议合并代码？

不建议把 solver 代码作为 production 合并。原因：

| 项目 | 判断 |
|---|---|
| real split 数学 | 通过 |
| FE-only p2 h5 | B 档成功 |
| reduced Stage 4 | 未实现 |
| full Stage 4 R/T/A | 未运行 |
| 代码性质 | isolated research runner，不是正式 solver |

建议只合并文档，或者把脚本保留在研究分支供 Task014/Task014a 使用。

## 10. 下一步方向

推荐下一步不是 Rayleigh deflation，也不是 full p=2 h2 直接硬跑，而是：

```text
Task014a：reduced Stage 4 real-split FE/aux block PC integration
```

任务目标：

| 阶段 | 内容 |
|---|---|
| A | 在 Stage 4 assemble-only 后构造 real block residual diagnostic |
| B | 对 FE block 使用 same-H1 AMS，aux block 用 identity/exact small solve |
| C | reduced p1 h5 测试 true residual 是否优于 Jacobi |
| D | 如果 reduced 成功，再 gated 到 full p2 h2 |

Rayleigh/Floquet modal deflation 仍是后续强物理路线，但应叠加在一个能进入 Stage 4 的 FE/aux block PC 之后。
