# Response V6：冻结离散算子的端口坐标病态已隔离

状态：**同一已截断离散算子的scaled p2 full3D参考逆组件通过，物理边界修正与p4仍未运行**。原raw单位辅助载荷失败保持FAILED；本批不恢复已经裁掉的端口泛函，不把532个模式身份说成532个未裁剪非零贡献。

同一个端口场可以使用不同的振幅单位。旧单位包含从原点到边界的快速衰减相位，使某些归一化小到约1e−194；直接给这些辅助坐标单位量级载荷会得到巨大振幅并破坏数值范数。本批把因子内部端口坐标精确换成较均衡的单位，求解后换回原单位。**原保存矩阵、原完整三维FE方程、固定FE载荷及所有内部恢复公式不变**。这隔离了求逆坐标问题；上游装配截断仍需另外修正。

## 对象、数学及身份

同一80-cell/p2/phi5、λ0.7nm、真实Si、7/135缩放几何、2-cell真实非可分缺口；2048原独立FE含480内部、1568trace，全部4个q块及532有序端口身份。增广块468/544/544/544行，n=1与−3分别保留。full3D outer和full original residual不变，没有n0投影或二维最终解。

用原carrier的有限正对角H_original构造R_aux=diag(I,H_original^(-1/2))，**不假定凝聚后Hhat是对角**。完整primal map为P=R_aux Q_aug；load用P^H，原solution用P。制造的每q载荷先嵌入完整modal库存，再用P^(-H)映射回原坐标；不能遗漏R_aux。各q实际均衡矩阵的重复/线性/残差检查及原S0制造载荷检查同时通过，门限没有放宽。

| 身份/门 | measured结果 | 限定 |
|---|---|---|
| 原S0 byte hash | c8ce975d8c467e3b28b7dae2d3421afaf087b1147ccdfe6b52da24bc753ac061 | 与失败raw attempt完全相同 |
| 原A0全部2048列 | 相对差0，32-column panels | 与旧phi5 dense authority相同；未新建global dense矩阵 |
| native增广covariance / modal off-block | 9.9526e−17 /4.1270e−16 | 全部16个(p,q)块核验 |
| 每pair相对于两个diagonal块的最坏相对norm | 3.7954e−16 | ≤1e−11；zero diagonal受控停止；未删sector |
| 实际均衡q块true residual最大 | 7.9064e−14 | ≤1e−10；所有4因子保留，无±q复用 |
| 原S0制造载荷residual最大 | 1.1554e−13 | 独立原矩阵动作，不用均衡矩阵验证自己 |
| 原H最小 /原零C及零D泛函 | 1.0720e−194；172/174 | 保留既有裁剪状态；没有恢复丢失项 |

## 完整三维恢复与缺口

载荷generic由固定随机种子20261001生成并含全部q/全部cell interiors；physical为原incident RHS。额外notch-supported载荷仅支持真实改变的两个cell，帮助判断小扰动是否容易。原FE载荷未因换坐标而改写。

| 原FE对象/载荷 | full original residual | 保存full dense direct场差 | FGMRES步数 |
|---|---:|---:|---:|
| regular A0 generic | 9.9685e−13 | 5.0947e−13 | 不适用：reference inverse apply |
| regular A0 physical | 7.9961e−14 | 9.4279e−13 | 不适用 |
| full3D notch generic | 1.2843e−13 | 5.5730e−13 | 4 |
| full3D notch physical | 7.1414e−12 | 5.5652e−11 | 3 |
| full3D notch-supported | 3.1460e−13 | 未记录：无旧同载荷direct field | 4 |

原residual门1e−10、direct场差门1e−9、完整augmented闭合与原slave-zero门保持。physical notch非零q比例5.5252e−5，由独立checker重算。**少迭代不说明大型鲁棒性**：generic/physical/notch-supported的采样right-PC defect仅9.0807e−4/3.3164e−5/7.5088e−4，模型Si contrast及电尺寸小；这些是采样值，不是operator norm上界。

## 资源、独立检查及保留失败

| 运行/身份 | measured资源与状态 | 保存边界 |
|---|---|---|
| raw q0失败，worker f2bd95ba813b3243bdfd052e90c53ccb0cf0e006 | 7.3205s，RSS433651712B，swap0，tree cleared | raw混合FE/aux单位载荷残差1.4342e12、linearity NaN；未保存中间解，不反推entry非有限；[V5失败](response_v5.md)保持 |
| positive-H worker 1c83fae75e46e7e28c84d1e82ec9bb85e94fbc83 | COMPLETED，11.1352s，RSS437866496B，swap0，tree cleared | 24份raw input/output vectors在assert前保存，本次全finite；warm cache，非冷启动速度结论 |
| checker attempt1，原worker HEAD | WORKER_FAILED，1.7679s，RSS196321280B，swap0，tree cleared | 最终JSON序列化遇NumPy bool，未写checker结果；不冒称独立pass |
| checker attempt2，d0959c5b5ea78363b6428604a12a5281cfee3fd1 | COMPLETED，2.8673s，RSS253747200B，swap0，tree cleared | 88/88重算检查及库存/内部RHS/alias/slave-zero门通过 |

以上RSS均为独立父进程和全部后代的采样同时树口径，worker与checker峰值不相加。每次上限1.5GiB/600s、zero swap、MPI1/maththreads1；512MiB是声明factor/workspace policy allowance，128MiB为证据reserve，不是fill或目标峰值保证。

worker和checker源码身份明确分开。修复仅涉及checker及其own regression test；独立receipt验证另外1234份source/config/input dependency byte hashes完全不变，ABI dictionary及manifest007a5f79…完全一致，**没有PDE重跑、没有假称whole HEAD未变**。新worker31targeted tests通过；checker修复5targeted tests通过，compileall/diff通过；归档前component＋registry聚合39targeted tests通过/1.07s，registry checker及compact/table/link结构通过。全库pytest/MPI多rank/Ruff/CI未运行；本批GitHub rendered view待publisher核验。

完整hash-bound证据见[compact记录](outcomes/records/positive_H_same_discrete_p2_v1.json)。raw均在ignored `benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_equilibrated_attempt1`；原raw失败及两个checker supervision目录全部保留。当前checker CLI须显式给出checker源码，例如本次已经执行的artifact-only命令：

```bash
python -m benchmarks.check_y_orbit_sparse_probe benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_equilibrated_attempt1 --expected-checker-head d0959c5b5ea78363b6428604a12a5281cfee3fd1 --checker-attempt 2
```

该attempt目录已存在；不能把历史命令当作新的run许可或覆盖记录。旧case计划中的checker命令对应修复前接口，本节为当前接口说明。

## 下一门与主任务协作

本批只完成当前冻结已裁剪算子的conditioning诊断。上游absolute1e−30 floor可能删除本应有限的边界贡献，正H坐标缩放不能恢复它们；需复用已审计Task35b的装配前boundary-plane phase思路，以同Gauss/fullMPC未裁剪系数建立新权威。mode generator身份与assembly representation身份必须分开，不通过改evanescent_buffer偷换532库存。

**p4仍held**，待新p2 coefficient/action/original-residual资格及representation决策，避免在已知被clip的边界上重复degree研究。原尺寸50×25×140nm、0.7nm、≤2TB/≤48h、物理截断/连续精度、workstation portable ABI与restart仍未资格。交付继续补足main Task40extra和用户笔记本campaign，由用户执行大型工作站验证；不操作用户机器、其他分支或普通默认。
