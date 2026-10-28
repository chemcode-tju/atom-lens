# 氢键显示调研（2026-10-29）

本次仅调研，不改现有氢键代码。

| 软件 | 官方资料中的显示方式 | 对本插件的启示 |
| --- | --- | --- |
| VMD | HBonds 用点虚线，线宽可调，与普通 Bonds 的带光照圆柱区分。 | 适合密集溶剂轨迹，细线能减少遮挡。 |
| PyMOL | 距离/氢键类虚线有 dash_width、dash_length、dash_gap 等设置；dash_as_cylinders 控制是否用圆柱绘制虚线。 | 虚线和圆柱是两个独立选择，不能笼统认为其他软件都不画圆柱。 |
| ChimeraX | hbonds 有 dashes、radius、color 等参数。官方用户支持示例使用 dashes 6、radius 0.06。 | 可借鉴虚线节奏与颜色控制；有半径参数不等于屏幕空间细线。 |

建议：默认细虚线，保留当前青蓝色，不做圆柱高光；虚线位于真实三维 H···A 连线上并参与遮挡。优先用稳定屏幕线宽（约 1–1.5 px），高 DPI 导出相应放大。线宽是否开放以及颜色可以下一轮讨论。

显示形状与氢键筛选分开：本插件目前 N/O/F 供受体、D–H ≤ 1.3 Å、H···A ≤ 2.5 Å、D···A ≤ 3.5 Å、D–H···A ≥ 150°，周期镜像搜索。改虚线无需改这些几何标准，也不代表电子结构意义上的成键判定。

来源：
- [VMD 官方当前用户手册，6.1.4 HBonds](https://www.ks.uiuc.edu/Research/vmd/current/ug.pdf)
- [PyMOL 官方设置说明：dash_as_cylinders / dash_width](https://github.com/schrodinger/pymol-open-source/blob/master/data/setting_help.csv)
- [PyMOL 官方设置源码](https://github.com/schrodinger/pymol-open-source/blob/master/layer1/SettingInfo.h)
- [PyMOL 官方虚线绘制源码](https://github.com/schrodinger/pymol-open-source/blob/master/layer2/RepDistDash.cpp)
- [ChimeraX 官方支持邮件：hbonds 参数](https://mail.cgl.ucsf.edu/mailman/archives/list/chimerax-users%40cgl.ucsf.edu/thread/J56KHJXTVDLPELTOKHBH7WIKR6SRFOH4/)

动画导出参考：[OVITO Rendering](https://www.ovito.org/manual/usage/rendering.html)、[Animation settings](https://www.ovito.org/manual_testing/reference/rendering/animation_settings_dialog.html)。参考了帧范围、帧率、倍速和抽帧；本插件只导出当前固定相机的轨迹，不声明支持 OVITO 的相机关键帧动画。
