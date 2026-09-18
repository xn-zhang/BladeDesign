# 三维探索范围与判据

## 本轮问题

Pritchard参考截面能否在两侧端壁约束下完成真实三维网格、RANS求解、收敛与质量守恒检查，并观察到展向速度和展向流速变化？

## 模型

- `pritchard-cascade-3d`，Pritchard图19参考截面，等截面直叶片。
- 有限物理展宽10 mm：z=−5 mm与+5 mm为静止、无滑移、绝热端壁；不是empty或symmetry边界。
- UI的拉伸展宽是STL辅助几何长度，默认60 mm，伸出两侧端壁后由计算域裁切；**不等于CFD物理展宽**。
- 周期边界仍为节距s=2πR/N的平移叶栅。轴向/周向斜置域随Cx/Ct更新。
- p0=100200 Pa、T0=300 K、出口p=100000 Pa；入口速度由压力边界决定，几何入口角不等于强制流入角。
- rhoSimpleFoam，k-ω SST，一阶迎风。壁面函数用于叶身和端壁，首轮没有棱柱边界层。
- 原生三维blockMesh/snappyHexMesh，不执行extrudeMesh或降维。

参考OpenCFD说明：[empty仅用于降维](https://www.openfoam.com/documentation/user-guide/4-mesh-generation-and-conversion/4.2-boundaries)、[noSlip](https://doc.openfoam.com/2306/tools/processing/boundary-conditions/rtm/derived/wall/noSlip/)。实际执行环境为本机v2512。

## 成功与限制分开记录

1. 网格拓扑、显式meshQuality门槛、周期配对与三个求解方向。
2. 三维Uz方程也应满足残差门槛；进程End不等于收敛。
3. 质量守恒、有限场、正压力和温度、VTK导出。
4. 独立检查noSlip/绝热端壁、真实C/U场和展向分箱统计；字段缺失则诊断未知。
5. 单独记录严格allGeometry凹单元，不用流程成功掩盖严格几何失败。

本轮不是完整扭转叶片、叶根/叶尖圆柱映射、叶尖间隙、旋转叶排、传热或自动优化验证。单套网格不能支持网格独立性或性能精度结论。

## 执行与复验

```bash
python3 bridge/create_pritchard_3d.py
bash bridge/start-local.sh
```

连接工作台后选择“Pritchard · 三维端壁叶栅（探索）”。完成任务后，使用实际任务目录执行：

```bash
postProcess -case jobs/JOB_ID/case -func writeCellCentres -latestTime
checkMesh -case jobs/JOB_ID/case -allTopology -allGeometry > jobs/JOB_ID/strict-checkMesh.log 2>&1
python3 bridge/audit_3d.py jobs/JOB_ID
```

网页二维云图不会将三维体网格伪装为二维投影；三维场可下载VTK在ParaView中切片查看。原始求解结果ZIP在求解完成时生成；后续C字段和独立审计文件保留在任务目录，不自动改写已归档ZIP。

`--span-cells 24` 可用于生成展向更密的后续模板。只有完成对比后才能评价对网格的敏感性。
