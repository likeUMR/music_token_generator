# music_token_generator

这个项目用于研究和复现 [Ableton Learning Music](https://learningmusic.ableton.com/) 中 `The playground` 页面的音频组织方式，并将页面状态渲染为可导出的音频结果。

当前仓库主要包含三部分：

- `tools/`
  - `ableton_playground_renderer.py`
    - 底层采样播放与变调渲染逻辑
  - `ableton_playground_exact.py`
    - 严格对齐 `The playground` 状态模型的渲染脚本
  - `ableton_playground_arranger.py`
    - 更泛化的编排层脚本

- `examples/`
  - 多个可直接渲染的 JSON 示例状态

- `docs/`
  - `playground-arrangement-format.md`
    - 精确状态格式说明与示例说明
  - `ableton-learningmusic-sidebar-summary.md`
    - Learning Music 侧边栏课程总结

## 页面发声逻辑

`The playground` 页面本身采用两套不同的播放路径：

- `beats`：`Tone.Players`
  - 基础路径：`/lessons/sounds/`
  - one-shot 播放
  - 使用很短的 `fadeOut`
  - 存在鼓组互斥行为，例如 `ClosedHat` 会截断 `OpenHat`

- `basslines / chords / melodies`：`Tone.Sampler`
  - 基础路径：`/lessons/sounds/`
  - 使用少量基准采样覆盖更多音高
  - 通过最近采样匹配 + 改播放速率进行变调
  - 不同模块使用不同 release：
    - `basslines = 0.10`
    - `chords = 0.40`
    - `melodies = 0.06`

仓库中的底层复现脚本是：

- `tools/ableton_playground_renderer.py`

## 当前精确模型

`tools/ableton_playground_exact.py` 目前使用的是这套时间定义：

- `4` 小节
- 每小节 `4` 拍
- 总共 `16` 拍
- 总共 `16` 个 grid
- `1 grid = 1 beat`

如果要得到：

- 每小节 `1s`
- 总长 `4s`

则应使用：

- `tempo = 240`

## 使用方式

渲染示例：

```bash
python tools/ableton_playground_exact.py --state examples/playground_arrangement_demo.json --output-dir out/playground-exact-demo --master-gain 1.0
```

渲染后会输出：

- 四条 stem
- 一条总混音
- `manifest.json`
- 一份输入配置副本

如果你想直接调用底层 renderer，也可以使用：

```bash
python tools/ableton_playground_renderer.py render-note --instrument chords --note C4 --duration-beats 2 --output out/c4.wav
```

```bash
python tools/ableton_playground_renderer.py render-sequence --sequence examples/ableton_playground_demo.json --output out/demo.wav
```

底层 renderer 的泛化输入格式支持：

- `tempo`
- `tracks`
- `instrument`
- `events`
- 音高输入：
  - `note`
  - `midi`
  - `frequency_hz`
- 时值输入：
  - `duration_beats`
  - `duration_seconds`

其中：

- `pitch_mode = "playground"`：先四舍五入到最近 MIDI，贴近页面行为
- `pitch_mode = "tone_sampler"`：保留更接近 `Tone.Sampler` 的分数音高逻辑

## 素材说明

仓库包含目录：

- `ableton-playground-audio/`

该目录中的音频素材为第三方学习资料整理副本，仅用于：

- 学术交流
- 技术研究
- 非商业学习与实验

**禁止商用。**

详细说明见：

- `ableton-playground-audio/NOTICE.md`

