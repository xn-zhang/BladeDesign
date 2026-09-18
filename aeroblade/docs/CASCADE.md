# 自建二维冷态周期叶栅

该基线用于真实网格、周期边界和可压缩 RANS 计算链路验证，不是发动机性能或实验验证算例。

## 物理与几何

- OpenCFD v2512；rhoSimpleFoam；理想气体，定比热与定黏度；k–ω SST。
- 推荐弦长 40 mm、厚弦比 12%、节距 60 mm；前缘弯度线角 10°、后缘 −5°。
- 主流 x，周期方向 y。二维 empty 展向边界，参考展宽 10 mm；质量流量是此参考展宽对应的 kg/s。
- STL 高 60 mm；截取等截面再作单层平面挤出。服务强制 taper=1、twist=sweep=lean=0，不能用于扭转/积叠/端壁三维流动。
- 默认入口总压 100200 Pa、总温 300 K、出口静压 100000 Pa。
- 一阶迎风，无棱柱边界层。不能据此宣称损失、效率、转捩或高温涡轮性能准确。

## 自动管线

`米制 STL → blockMesh → snappyHexMesh → extrudeMesh → createPatch → checkMesh → rhoSimpleFoam → foamToVTK`

snappy 阶段保留周期面以保持匹配点；挤出前服务只将这两个生成网格的周期面临时改为普通 patch（OpenCFD extrudeMesh 不能直接处理这些耦合源边）。随后 createPatch 建立名为 cyclicLow/cyclicHigh 的新周期面并重排点。所有网格变更必须发生在 checkMesh 之前；不允许客户端传入脚本或任意命令。

最终检查为 `checkMesh -allTopology -meshQuality`，显式阈值在 system/meshQualityDict 中。必须输出 Mesh OK 才允许求解。严格 `-allGeometry` 凹性检查另行记录，可能报告凹单元；不要把流程检查通过描述成全部网格精度检查通过。

## 使用与重建

从 aeroblade 目录执行 `python3 bridge/create_cascade.py`，生成 templates/cold-periodic-cascade-2d；已有目录时拒绝覆盖。
执行 `bash bridge/start-local.sh`，在工作台连接后选择“二维冷态周期叶栅”，点击“应用模板推荐叶片”，再提交真实仿真。
默认令牌位于 WSL `~/.local/state/aeroblade/api-token`。在自己的终端读取并填入网页，勿发到聊天中。
推荐请求位于 `templates/cold-periodic-cascade-2d/recommended-request.json`。

## 验收

执行 `python3 bridge/validate_result.py jobs/<任务ID>`。必须有真实周期耦合、Mesh OK、求解器显式收敛、完整方程初始残差 <1e-5、入口负流量/出口正流量且相对不平衡 <0.1%、有限且正的压力/温度、二维展向速度 <1e-10，以及真实 VTK 和 ZIP。
同一步的多次压力校正取最大初始残差；二维方程要求 Ux/Uy，三维另要求 Uz。失败返回非零。
压力线性容差 1e-9，速度/能量/湍流 1e-10，relTol=0；SIMPLE 两次非正交校正，consistent=no，压力/密度松弛 0.15、速度 0.3；默认上限 3000 步。

## 未通过的三维试验

早期三维切片（包含 25°/−20° 与 10°/−5° 叶片）曾完成求解但未满足全部稳态残差门槛；保留任务与日志，不作为成功验证。旧三维模板描述符改名为 aeroblade-template.disabled.json，不再注册。
当前二维验证不能替代三维端壁/二次流研究。工程应用还需棱柱层、y+ 目标、二阶格式、网格独立性及实验对照。

参考：[rhoSimpleFoam](https://doc.openfoam.com/2312/tools/processing/solvers/rtm/compressible/rhoSimpleFoam/)、[周期边界](https://doc.openfoam.com/2212/tools/processing/boundary-conditions/rtm/derived/coupled/cyclic/)。挤出字典依据本机 v2512 官方教程及实际命令输出验证。
