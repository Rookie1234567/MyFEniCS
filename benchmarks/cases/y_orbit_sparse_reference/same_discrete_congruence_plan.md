# 当前冻结S0的positive-H坐标诊断：待审查

原sparse-p2 phi5 attempt1/source `f2bd95ba813b3243bdfd052e90c53ccb0cf0e006`保持失败。原完整2048-column A0 identity差0，native S covariance9.95e−17/off-q4.12e−16先通过；raw native O(1) auxiliary loads的q0因子true residual1.4342e12、linearity NaN，7.3205s/433651712B/zero swap/tree cleared。未保存旧中间解，不能由NaN norm反推其entry非有限。

本诊断只隔离当前已被上游absolute floor截断的算子中的辅助幅度坐标病态。它不重新装配carrier、不恢复已丢失functionals、不声称532个非零贡献。旧532是完整生成identity/slots；原S0和已消去的FE A0必须与冻结旧authority完全不变。upstream预sparsification边界phase gauge由portworker另一条线审查；p4保持held，避免在已知被clip的representation上先做degree sweep再重复。

## 精确可逆变换

取原carrier的完整real-positive finite diagonal H_original，σ=H_original^(-1/2)，并验证σ、1/σ有限非零。不把凝聚后的Hhat假定成diagonal。R_aux=diag(I_trace,σ)，完整primal P=R_aux Q_aug；变分load为P^H b，native primal为P z。对于制造的完整modal load f，native load必须是b=P^(-H)f，其中所有q槽先嵌入完整库存，不能遗漏R_aux或错误使用Q^-H。

端口R_aux与diag(η_n)平移可交换，原C/D/Hhat和所有Bi/Di/XiB公式不变。逐q因子矩阵是P_q^H S0 P_q，原basis输出alpha=σ beta。原FE Schur及所有内部恢复不变；schema/report显式记录positive-h而非raw。矩阵原S0仍原样保存hash-bound，不用均衡后的矩阵验证自己。

## 资格门与失败保存

- native原S0 covariance、所有cross-q完整审计及逐pair相对于两个diagonal block的门均保持原阈值；不silent drop或换sector
- 每实际q因子使用O(1) **均衡坐标** a/b重复、线性、block true residual；此负载坐标变化明确记录，原raw O(1)失败不改写为pass
- 每q制造负载先放入完整f，再映射b=P^-H f；用原保存S0独立核验S0(P_q x_q)−b的native residual≤1e−10。checker独立重算该inverse-dual mapping和原S0动作
- 固定原FE generic/all-interior/physical RHS完全不变；完整恢复须通过原A0 action/residual和旧full direct fields，再做同mesh full3D notch固定loads
- 整个案例仍1.5GiB aggregate tree/600s/zero swap/one thread，512MiB声明factor allowance+128MiB reserve，无fill保证
- q因子输入/输出在任何assert前保存有界raw NPY诊断（每vector≤65536 complex entries，禁止object），允许如实记录NaN/Inf；与finite-only成功artifact库存分离。JSON只写finite/nonfinite counts/有限最大幅度，不写伪finite值。checker成功时需raw实际vectors全finite；失败时保留raw原貌
- integration/新的source commit/targeted tests/ABI与准确命令均待root单独审查。没有numerical run许可

拟议后续命令（只p2，不自动p4）：

```bash
source ../complex_env_setup/activate_cloud_complex.sh
python -m benchmarks.run_y_orbit_sparse_probe --run --degree 2 --auxiliary-gauge positive-h --expected-head <REVIEWED_NEW_CLEAN_HEAD> --run-directory benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_equilibrated_attempt1
python -m benchmarks.check_y_orbit_sparse_probe benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_equilibrated_attempt1
```

无原尺寸accuracy、物理DtN完整贡献、2TB/48h或p4通过结论。本诊断positive若成立，只证明当前冻结离散算子的reference inverse可以由精确可逆factor坐标改进。
