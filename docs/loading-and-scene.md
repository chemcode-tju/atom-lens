# Loading and shared scene / 加载与统一场景

## 读取流程

1. 请求一个完整帧，解析、绘制后再启动索引任务，不等完整扫描。
2. 后台索引每轮最多 4096 帧或约 1 MiB，之后让出事件循环。文本索引只保存字节位置；不保存每帧坐标或所有原始文本。
3. 切帧命中缓存直接使用；未命中时从对应偏移读取、解析一帧。快速拖动合并成最新目标，导航最多一个读取请求在途。
4. 缓存采用 LRU：最多 16 帧，文本和原子对象估算预算 64 MiB。为允许大结构，单帧可超过预算；该预算不限制文件大小或轨迹帧数。

当前显示帧、固定的质心参考帧及导出中的场景可以额外持有常数个帧。估算预算不是整个浏览器进程的硬内存上限；帧索引随帧数增长，WebGL 模型、标签纹理、导出画布另占内存。

MCP `read_trajectory_frames` 新增 `indexOnly` 和响应中的 `offsets`。正常文本读取仍以 32 帧/约 256 KiB 为单批上限；当前导航请求一帧。索引模式可扫描 4096 帧/约 1 MiB，只返回位置。源文件版本校验也覆盖偏移 0 的重新读取。

浏览器本地文件使用 64 KiB 字节块建索引，再通过 `Blob.slice()` 读取目标帧；UTF-8 和 CRLF 均按字节定位。`.traj` 使用文件自带 ULM 索引，直接提供总帧数。原名 POSCAR/CONTCAR 读取单帧，不将速度数据当作第二帧。XDATCAR 仍要求固定晶胞。

未扫描到的文本帧暂不可跳转；错误尾帧不清除此前已建立的索引和当前画面。旧宿主若不提供源路径，仍只能回退到宿主的完整文本接口；要获得首帧优先的按需读取，应使用支持路径元数据的文件入口或“按路径打开”。

## 场景与光影

`scene.js` 捕获显示规则并统一执行：固定原子组质心校正 → Wrap → 原子样式/显隐。相机投影、视角、画布比例以及光照由预览和导出共同使用。动画将设置固定在开始导出时，按 ID 或兼容的原子顺序映射局部样式；不改变交互预览的帧号、选择或相机。

快照和动画沿用同一 WebGL 渲染器、半径、配色、编号、氢键。临时选择圈、测量线和界面控件仍不导出。PNG 可以透明，JPEG/PDF 和动画使用白底；画布尺寸受实际 GPU 能力限制。

新光照为相机方向的柔和主光、环境补光和微弱宽高光。参考 [ovito-tachyon](https://github.com/erwanjun/ovito-tachyon) 的哑光表现，未复制其实现，未添加光线追踪、真实投影阴影或环境遮蔽。对固定版本 3Dmol 的着色器替换会检查匹配数量，防止依赖更新后静默失效。

## Validation / 验证

- Backend: first frame before a malformed tail; >64 MiB XDATCAR; offset-only XYZ/VASP indexing; exact random refetch; file replacement detected even at offset 0.
- Browser readers/cache: CRLF and UTF-8 across chunk boundaries; POSCAR/CONTCAR/XDATCAR; early availability; LRU count/byte eviction and refetch; duplicate request coalescing; ASE logical offsets.
- Scene/navigation: last requested frame wins; stale file responses ignored; fixed style/camera during export; COM before wrap; atom-ID style mapping; original coordinates unchanged.
- Local browser protocol host: first frame displayed while indexing, random jump to frame 750 of 800, transparent cropped PNG and four-frame MP4 exported. Native Codex host and remote UI acceptance remain separate from these tests.

Run the regression suite from the repository root:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
for test in tests/test_*.cjs; do node "$test" || exit 1; done
```
