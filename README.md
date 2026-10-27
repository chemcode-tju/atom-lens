# Structure Viewer for Codex

在 Codex 桌面端点击 `.extxyz` / `.xyz` 文件，在聊天侧面板查看、切换帧、编辑并保存原子结构。采用官方 MCP Apps **File Extension Entrypoint**，不包含技能，不需要通过聊天命令启动，也不需要本地 HTTP 服务。

## 初版功能

- 原子球、球棍、线棒；拖动旋转、滚轮缩放，晶胞和原子编号开关。
- 底部帧滑块、帧号跳转、前后帧、可调速播放；支持各帧原子数不同。
- XYZ/extxyz 先读取第一帧并显示，随后分批加载；加载过程中即可旋转、切帧，滑块随已加载范围增长。
- 点击原子查看坐标；XYZ/extxyz 可编辑单原子的笛卡尔坐标。
- 当前帧源码编辑；保留 extxyz 的 `Properties`、晶胞、PBC、能量、力及其他属性。
- 点击“保存”或 Cmd/Ctrl+S，通过宿主文件接口写回；使用 ETag 检查外部修改冲突。
- 渲染库随插件打包，结构查看和编辑不使用外部服务。

### 视图与外观（0.3.0，本地更新）

- 默认 XZ 正交视图：X 向右、Z 向上。底部可切换 XY、XZ、YZ 和透视视图，重复选择同一方向会复位。
- 单视图、双视图和四视图；点击面板激活，双击视图标题或点击展开按钮放大当前面板，再次点击恢复。
- 底部提供旋转、拖动平移、拖动缩放和适应视图按钮，以及帧刻度尺、首尾帧和播放控制。视图操作只移动相机，不修改原子坐标。
- 固定白色背景。移除常驻状态说明、操作提示、PBC 徽章等小字；失败时显示错误，未保存时保存按钮带 `*`。
- 默认 Jmol 配色，另提供 RasMol/CPK 和 VESTA。Jmol/RasMol 使用随包发布的 3Dmol 元素表；VESTA 使用 [OVITO 官方提供的 VESTA 主题](https://www.ovito.org/download/data/documentation/VESTA.ovito-theme)，不套用 VESTA 半径。
- 原子球使用 OVITO 3.15.5 元素显示半径表（通过本地 Python API 导入标准元素获取），例如 H 0.46、C 0.77、O 0.74、Cu 1.28 Å；可统一调为 75% / 100% / 125%。这是显示半径，不是统一缩放的范德华半径，参见 [OVITO 粒子设置](https://www.ovito.org/manual/reference/app_settings/particle_settings.html)。缺失半径回退到 1.2 Å，缺失配色回退到 Jmol。

此次仅更新本地安装，nd3 保持 0.2.0。无需为开发测试重启正在使用的 Codex；现有原生面板可能仍缓存旧版 UI，可在方便时重新打开面板或重启后确认。

### 交互、分析与快照（0.4.0，本地更新）

- 视图菜单每次选择都会重置旋转、平移和缩放，包括重复选择当前 Top/XY。原子采用环境补光与柔和高光，导出使用同一套着色。
- 复选框先绘制勾选状态，再更新结构。序号标签批量创建、每批统一绘制；单视图时不再反复重建其他隐藏视图。
- **氢键**：按几何筛选 N/O/F 供受体，D–H ≤ 1.3 Å、H···A ≤ 2.5 Å、D···A ≤ 3.5 Å、D–H···A ≥ 150°，显示青色虚线。对启用 PBC 的方向搜索周期镜像，支持斜晶胞。这是几何可视化，未推断供受体的电子结构；周期虚线可能连向晶胞外最近的镜像。
- **Wrap**：按晶胞分数坐标仅折回周期方向，作用于显示，不修改源码、原始坐标或计算属性。无有效晶胞时明确报错。
- **播放设置**：仅包含 Animation 与 Playback in interactive viewports。默认 60 fps × 1；可调 fps、倍速、每 N 帧与循环。绘制跟不上时跳帧维持时间进度，实际刷新率取决于硬件、原子数和显示选项。
- **跟随原子**：输入原子序号点击“指定中心”，或点击原子后“跟随此原子”。各视图保留视角和缩放，播放时将其持续放在中心。extxyz 有 `id`/`atom_id`/`identifier` 时按唯一 ID 跟随，否则要求各帧元素序列一致并按序号跟随。无法对应时停止切帧；800 帧训练集包含不同结构，不等同于同一组原子的连续动力学轨迹。
- **快照**：导出当前激活视图，保留视角、配色、显示样式、氢键、编号和光影，不包含工具栏/坐标轴/视图标题。PNG 支持透明背景，JPEG/PDF 使用白底。默认保留视口空白，可勾选紧贴可见内容的四边裁切。提供 96/150/300/600 DPI（默认 300），按 96 CSS px/in 增加实际渲染像素，并写入 PNG/JPEG 密度元数据或 PDF 页面尺寸。PDF 内嵌高分辨率栅格图，不是矢量原子图。
- 原生打开的文件：快照保存在结构文件旁的 `structure-snapshots/`，同名自动追加序号，绝不覆盖结构或已有图片。通过“打开”选择的本地文件：快照使用浏览器下载。单图上限 2000 万像素、单边 8192 像素；输出只包含当前视口内的内容，导出前可先适应视图。
- 现代 ASE **`.traj`** 按 ULM 帧索引渐进读取，支持每帧原子数变化、晶胞与 PBC。查看为只读，不将二进制文件改写为文本，不读取旧版 pickle 轨迹；运行插件无需额外安装 ASE。计算器结果、约束与其他自定义数组暂不提供编辑。
- 顶部 **打开** 可选择本地裸名 `POSCAR`、`CONTCAR`、`XDATCAR`，以及 `.xyz`、`.extxyz`、`.traj`。此入口仅查看，源文件写回仍需通过 Codex 原生文件链接打开。

此轮继续只更新本地，不操作 nd3，也不重启 Codex。新版原生面板和快照工具发现可能仍受当前宿主缓存影响；开发验证不等于原生缓存已经刷新。

## 安装

需要支持 MCP Apps 文件入口的新版 Codex 桌面端，以及 `python3`（3.9 或以上）。插件服务只使用 Python 标准库；运行插件不需要 ASE、Node.js 或 npm。

```sh
git clone https://github.com/liyang-tju/extxyz-extension.git
cd extxyz-extension
codex plugin marketplace add .
codex plugin add structure-viewer@atomic-structure-tools
```

安装后打开本地 `.extxyz` 文件。如果仍然使用内置文本编辑器，在文件的打开方式菜单中选择 **Structure Viewer**；宿主可以记住按扩展名选择的查看器。若新插件未被发现，重新打开聊天或重启桌面端后再试。

从 0.1.0 升级时，重新执行安装命令，并完整退出、重开桌面端。0.1.0 的 MCP 启动参数使用了未正确解析的插件根目录占位符，导致握手失败、查看器菜单缺失；0.1.1 改为以插件目录为工作目录运行 `server.py`。仅关闭文件标签可能仍沿用旧的插件发现缓存。

本地开发修改源码不会自动同步到插件安装缓存，更新后需重新安装对应版本。

### 远程聊天与渐进加载（0.2.0）

在 nd3 等服务器的 Codex 远程聊天中使用时，需要在**对应服务器上**执行同样的插件安装命令，再重新连接远程聊天；必要时完整退出、重开桌面端。本地安装不会自动为远程主机注册文件查看器。结构文件保留在服务器，插件通过 Codex 连接分批传输文本，三维渲染在本地侧面板执行，无需手动下载或开放额外端口。

XYZ/extxyz 首次只读取一个完整帧，后续每批最多 32 帧或约 256 KiB（不拆开单帧）。无需预先扫描全文件，帧数显示为已加载数量，完成后显示总数。播放到尚未加载的位置会等待。每批检查文件版本；文件在加载期间变化时停止，避免拼接不同版本。当前不是持续跟随正在写入的模拟轨迹。

分段预览只读；点击**启用编辑**后，读取完整文件及宿主保存版本，再启用原有的编辑/保存功能。因此查看大轨迹无需等待全量下载，编辑仍受宿主完整文件读写上限限制。分段读取依赖宿主为工具调用提供选中文件的路径；旧宿主不提供时回退到完整读取。单帧最多 8 MiB，全部已加载帧会保留在内存中；VASP 文件仍使用完整读取。

## 支持范围

| 格式 | 查看 | 编辑 |
| --- | --- | --- |
| `.traj` | 现代 ASE ULM 多帧、晶胞和 PBC | 只读 |
| `.xyz` / `.extxyz` | 多帧、属性列顺序变化、晶胞和 PBC | 原子坐标、当前帧源码 |
| `.poscar` / `.contcar` / `.vasp` | VASP 5/6，Direct/Cartesian、缩放因子 | 文件源码 |
| `.xdatcar` | 固定晶胞多帧 | 文件源码 |

**当前宿主的入口按扩展名匹配。**裸文件名 `POSCAR`、`CONTCAR`、`XDATCAR` 虽然解析器可以读取，但尚不能靠这个入口自动关联；可在查看器顶部点击“打开”直接选择这些本地文件；要从聊天文件链接自动关联，可使用 `structure.poscar`、`trajectory.xdatcar` 等带扩展名的副本。VASP 4 缺少元素名时明确报错，不猜测元素。

编辑不会重新运行计算。改变坐标后，原有能量、力、应力等标签仍被保留，但可能已不适用于新结构；将编辑结构用于训练前须重新计算标签。

测量目前显示两原子的**直接距离**，未实现周期最短距离。球棍连线按距离推断，不包含跨周期边界的键。XDATCAR 首版仅覆盖固定晶胞；大文件仍受宿主读写大小上限和内存限制。保存前请确认未保存标记已消失，避免关闭面板丢失草稿。

## 验证

```sh
node tests/test_parser.cjs
node tests/test_viewport.cjs
node tests/test_geometry.cjs
node tests/test_snapshot.cjs
node tests/test_ase_traj.cjs
python3 tests/test_binary_snapshot.py
python3 tests/test_server.py
python3 tests/test_trajectory.py
```

对真实数据做逐帧 ASE 对照（可选，测试数据不随仓库分发）：

```sh
conda install -n work -c conda-forge ase numpy
conda run -n work python tests/validate_real_data.py
```

将测试文件放在 `test-data/train.extxyz`。已在本地 800 帧、每帧 66–226 原子的文件上比对全部元素、坐标、晶胞和 PBC；未编辑文件可原文往返。解析器单元测试覆盖重排属性列、不同原子数、CRLF、单帧修改、错误输入和 VASP 格式。

`tests/preview_host.py` 是**仅供开发验证的协议模拟宿主**，不是插件的打开方式。运行后访问 `http://127.0.0.1:8767`，保存只写到 `test-results/roundtrip.extxyz`，不会覆盖原始测试文件。已验证加载 800 帧、跳到末帧、编辑及保存仅改变目标坐标行。原生文件入口和原生保存需要单独验证，模拟宿主通过不代表桌面端已成功加载插件。

0.1.1 已通过桌面端自带 app-server 的 `mcpServerStatus/list` 实测；完整重启后的本地原生结构显示已获用户确认。0.2.0 在协议模拟宿主中验证了尚未加载完即可切帧、加载全部 800 帧、切换完整编辑并仅修改目标坐标后保存副本。新增测试覆盖首帧读取不扫描损坏的后续帧、跨批原文保留、文件变化拒绝继续、截断帧和无宿主路径时回退。0.2.0 的远程原生显示仍需在 nd3 聊天中确认。

nd3 实测原轨迹大小 12,543,132 字节，第一帧只读取 23,889 字节；全部 800 帧共 50 批，重组内容的 SHA-256 与原文件一致。本地与 nd3 的新 app-server 均已发现 0.2.0 的文件入口和分段读取工具，无启动错误。后端验证不代替远程原生侧栏交互验证。

0.3.0 本地协议测试页已验证：XZ 默认取景、四视图及高晶胞完整显示、双击 YZ 面板展开、平移拖动、三种配色及球棍/线棒切换、首尾帧跳转，以及 540 px 侧栏布局。新增方向投影测试覆盖 XZ 的 X 向右/Z 向上、YZ 的 Y 向左/Z 向上，防止相机矩阵方向混淆造成晶胞裁切。按用户要求不重启 Codex，不更新 nd3，原生窗口中的新版 UI 待方便时确认。

0.4.0 验证覆盖：周期 wrap 不改源数据、斜晶胞最短距离、跨边界氢键与角度筛选、原子 ID 跟随、ASE ULM 头信息继承/变化和截断拒绝、透明裁切、PNG/JPEG DPI、PDF 页面尺寸，以及截图目录与同名文件保护。与本地 ASE 生成的变原子数轨迹做了元素、坐标、晶胞和 PBC 对照；协议测试页实际打开了裸名 POSCAR 与二进制 traj，并保存了三种图片格式。

## 目录

- `plugin/server.py`：MCP STDIO 入口、工具声明与内嵌 UI 资源。
- `plugin/trajectory.py`：仅对宿主选中文件执行有大小限制的分段读取与版本检查。
- `plugin/web/parser.js`：原文保留与按帧坐标解析。
- `plugin/web/app.js`：交互、渲染、宿主读写协议。
- `plugin/web/viewport.js`：多视图、正交取景、相机控制。
- `plugin/web/appearance.js`：元素配色与显示半径数据。
- `.agents/plugins/marketplace.json`：可安装的本地插件市场。
- `examples/water.xyz`：可公开的两帧小样例。

测试数据、测试输出、截图均已被 `.gitignore` 排除。

## 接口依据

- [OpenAI Plugin Extensions：File viewers and editors](https://developers.openai.com/plugins/build/extensions)
- [OpenAI 插件打包](https://developers.openai.com/plugins/build/plugins)
- [MCP 文件入口、读取和写入协议](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md#file-extension-entrypoint)

## 许可证

项目源码为 MIT。内置 3Dmol.js 使用其独立许可证，见 `plugin/web/vendor/LICENSE-3Dmol.txt`。3Dmol.js 下载来源为 https://3dmol.org/build/3Dmol-min.js；固定的完整文件随 Git 提交保存，使用时不从 CDN 加载。
