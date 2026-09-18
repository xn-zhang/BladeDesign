# Pritchard 1985 十一参数截面模型

来源：L. J. Pritchard, *An Eleven Parameter Axial Turbine Airfoil Geometry Model*, ASME 85-GT-219 (1985), [DOI](https://doi.org/10.1115/85-GT-219)。实现核对原文图1、图5、公式1–16、附录C与图19。公开[论文镜像所在仓库](https://github.com/SergeyNM/RATD_RAPID_AXIAL_TURBINE_DESIGN)仅用于本机查阅，PDF不随项目发布。另查阅了[David Poves的MIT许可参考实现](https://github.com/DavidPoves/11-Parameters-Turbine-Blade-Generator)作为公式交叉核对；平台使用自己的JavaScript几何实现，不依赖该Python程序。

## 十一个输入

| 字段 | 含义 | 单位 |
|---|---|---|
| radius | 截面所在圆柱半径 R | mm |
| bladeCount | 整圈叶片数 N（整数） | — |
| axialChord | 轴向弦长 Cx | mm |
| tangentialChord | 周向弦长 Ct | mm |
| throat | 几何喉道 O | mm |
| leadingRadius | 前缘半径 RLE | mm |
| trailingRadius | 尾缘半径 RTE | mm |
| inletAngle | 进口叶片角 βin | deg |
| outletAngle | 出口叶片角 βout | deg |
| inletHalfWedge | 进口半楔角 εin（非全楔角） | deg |
| unguidedTurning | 无导向转折角 UGT | deg |

`height` 是另外的直线拉伸展宽设置，不属于论文11参数。当前展示单个半径处的展开截面及其等截面拉伸，未实现真实圆柱映射、径向多截面插值或自动优化。半径R和叶片数N通过节距影响截面；同比改变R与N保持节距时，二维形状不变。

## 坐标与构造

原始展开平面：x为轴向，y为周向。前缘圆心为 `(RLE,Ct)`，尾缘圆心为 `(Cx-RTE,0)`，相邻叶片沿y平移 `s=2πR/N`。切线斜率为 `tan(β)`。截面CSV导出原始毫米坐标；三维模型和CFD STL使用平移后的坐标 `(x-Cx/2,y-Ct/2,z)`，不额外旋转安装角。CFD STL以米输出。派生安装角显示为论文约定 `atan(Ct/Cx)`，不是又一次施加的旋转。

五个连接点按照原文式2–16计算。轮廓由吸力面三次多项式、喉后吸力面圆弧、尾缘圆弧、压力面三次多项式和前缘圆弧构成。三次多项式用Hermite形式计算，与附录C的幂基形式等价。

消去喉后圆弧圆心和半径，可将原附录F迭代条件写为：

```
s cos(βout − εout + UGT/2) = (O + 2 RTE) cos(UGT/2)
εout = βout + UGT/2 + acos((O + 2 RTE) cos(UGT/2) / s)
```

采用常规负出口角分支，内核统一使用弧度。由此求得尾缘半楔角，再检查圆弧半径一致性、连接点轴向顺序、离散轮廓自交与相邻叶片交叉。位置及一阶切线连续（C1），不宣称曲率连续（C2）。有限采样检查不替代精确CAD或工程有效性检验。

## 参考预设与范围

默认预设采用原文图19：R=5.500、Cx=1.102、Ct=0.591、RLE=0.031、RTE=0.016、N=51、βin=35°、βout=−57°、εin=9°、UGT=6.5°。原文允许一致的英制或公制单位；本平台将示例中的1个长度单位取为25.4 mm，作为统一尺度选择，**不把这一尺度解释为真实发动机尺寸**。图19喉道输入0表示使用默认规则，本平台将其显式展开为 `O=s cos(βout)−2RTE`，所以面板中的喉道不是0。

参考输出：节距17.210999753 mm，喉道8.560982297 mm，尾缘半楔角3.309822957°（原图打印约3.31°）。输入范围为软件支持范围；合法单项范围不保证组合可行。原FORTRAN通过数值大小触发的隐式默认规则不启用，所有输入保持明确物理含义。软件当前限定出口角−80°至−5°等范围，未覆盖原方法全部可能分支。

## 兼容与CFD

新JSON格式 `aeroblade-pritchard-v1`，参数含 `model: pritchard-1985`。旧 `aeroblade-v1` 仍由独立 `legacy-geometry.js` 处理，导入会明确切换为旧模型，不自动把两组参数互相转换。

Pritchard几何只能提交到 `pritchard-cascade-2d` 模板。周期节距由R/N计算；背景网格采用与弦线平行的斜置边界，周期平移量同步更新。冷态SST、无棱柱层设置用于集成验证，几何角不等于实际流入/流出角。新截面不得继承旧任务的收敛或精度结论。首次生成模板：

```bash
python3 bridge/create_pritchard_cascade.py
```

验证命令（仓库根目录）：`bash scripts/check.sh`。包括图19打印值、圆弧半径、连接切线、尺寸缩放、R/N不变性、封闭网格边拓扑与面积×展宽体积、无效输入、模型匹配和真实STL/节距映射。真实CFD集成运行情况见 [Pritchard验证记录](PRITCHARD_VALIDATION.md)。

三维有限展宽端壁叶栅已开展首轮探索，尚未通过稳态收敛，见 [三维验证记录](THREE_D_VALIDATION.md)。
