# Response V12：共享完整实体变换通过同80-cell full3D资格

本轮在 `3570347c` 完成共享变换存储的完整资格。独立checker保留原312项数值门，另通过38,881项存储、状态和生命周期门，evidence_valid=true。此处改变数值对象的存储与复用；完整原三维方程、四q、全部多项式与内部未知量、532个原端口仍保留。

## 实际对象体积与等价门

一个run-local bank覆盖1个实际Basix/basis身份、9个实际状态，intern为4个完整矩阵内容模板和4个共享lazy inverse。模板均为不可写的bytes-backed arrays；完整状态/通道/坐标/实际cell-info独立绑定，不能假定moment基unitary、inverse=adjoint或所有矩阵identity。

| 同时存活的数值对象口径 | 实测named bytes |
|---|---:|
| 完整outer与所有local record的matrix/inverse逻辑体积 | 69,435,392 |
| 8个共享matrix/inverse backing owners | 410,624 |
| 同阶段全部命名对象的unique owner体积 | 46,234,084 |
| 同阶段全部views含aliases之和 | 115,767,892 |

第一行是保留同样完整矩阵语义时的记录体积；第二行是实际共享模板owner体积。后两行还包括row arrays、局部稀疏映射等，不能混称模板体积。它们均不是整树RSS。所有full/local record的完整矩阵与inverse逐项相等；六个primal/dual/functional方向的全部列、native独立/slave和orbit/base/slot分区都通过。局部layout借已有entity对象，避免再次collect。cleanup证明全部声明weak anchors已释放；不声称allocator已把RSS归还。

四个fresh q CSR仍对不可变权威差0，并在完整存储等价门通过后才分解。四因子全部保留，原80-cell的15,872独立FE、8,640内部及532 aliases仍由原FFCx volume作用加DtN重算true residual。regular四载荷最大残差5.2675719230699435e-12；真实两cell三维notch的generic/interior/physical/support迭代4/4/3/4，最大残差7.96690203269436e-12。全部原输出门保持，未改容差或物理算子。

## 监督资源与限制

| 阶段 | seconds | sampled simultaneous whole-tree RSS bytes |
|---|---:|---:|
| worker（含独立unshared/evidence重叠） | 170.03514251799788 | 1,065,373,696 |
| 独立checker | 43.12502518900146 | 952,623,104 |

两阶段都COMPLETED、swap0、后代清场，仍为1.5GiB/600s、MPI1/maththreads1及原512MiB剩余factor policy加128MiB reserve。整树峰高于V11，因为本轮还建立并验证legacy对象与完整owner证据；本轮不授予RSS下降或加速结论。106项合同及86 subtests通过，另有实际ABI/语法/CLI预审。

历史raw端口与JIT身份保留，新的mapping/volume/recovery源身份明确。完整源、报告、check、owner阶段和监督哈希在[compact](outcomes/records/shared_transform_v12/shared_transform_v12_compact.json)中；[独立归档receipt](outcomes/records/shared_transform_v12/independent_verification.json)已完成47项元数据/身份绑定检查，重哈希1335项exports及10个private-checker/historical-Q文件；这是只读字节和保存证据核验，没有数组解码或数值重跑。最终freeze后原字节复制。

当前仅授予同80-cell、p4、manual532模式的离散架构/存储资格。p6、目标50×25×140nm/λ0.7nm的准确网格与全部AUTO库存、端口收敛、目标factor fill/backend/index宽度、≤2TB/≤48h、MPI及restart仍未资格。下一步先实现并准入X=6×4×5的fresh direct两cell设置，保留原full3D action，不建立fullNy参考CSR/F/Q；XZ与Ny6点随后按X结果依次审核。所有旧失败和早期资格范围保留。
