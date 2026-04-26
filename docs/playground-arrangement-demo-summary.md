# Playground 精确示例说明

示例配置：`examples/playground_arrangement_demo.json`

这一版示例不再追求“更通用的编排器”，而是严格对齐 [The playground](https://learningmusic.ableton.com/the-playground.html) 本身的状态模型。

也就是说，这份示例现在只描述网页真实允许你改的东西：

- `beats`：哪些格子开，哪些格子关
- `basslines/chords/melodies`：
  - 当前 `root`
  - 当前 `scale`
  - 音符块的 `lane/start/length`

## 为什么这次和上一版不同

你指出得对：上一版虽然音乐上能工作，但自由度比网页更大，例如：

- beat 里加入了网页没有的额外参数
- tonal 部分允许了更泛化的事件写法
- 整体更像“通用音序器”，而不是 playground 本身

这次已经改成“只保留网页真实控件状态”。

## 这一版音乐结构

当前对齐模型改成了：

- `4` 小节
- 每小节 `4` 拍
- 总共 `16` 拍
- 总共 `16` 个 grid
- `1 grid = 1 beat`
- 如果按“每小节 `1s`”渲染，则示例使用 `240 BPM`

为了仍然体现教程里的“重复 + 小变化 + 收束”方法，我把这 4 小节写成四个 **1 小节短句**：

- `A`
- `A`
- `B`
- `C`

也就是一个完整的 4 小节 `AABC`。

## 四层写法

### 1. Beats

- `Kick`：每拍一个，保持 `four on the floor`
- `Clap`：每小节第 2、4 拍形成 backbeat
- `ClosedHat`：稳定细分推动
- `OpenHat`：只在第 2 个 A 结尾和 C 结尾打开一点，形成段尾提示

### 2. Basslines

- 第一个 `A`：`C-E-G-E`
- 第二个 `A`：完全重复
- `B`：改成 `A-C-A-G`
- `C`：`F-A-G-C`，最后回主音

### 3. Chords

- 第一个 `A`：`C major`
- 第二个 `A`：`C major`
- `B`：`A minor`
- `C`：先 `G major` 再回 `C major`

### 4. Melodies

- 第一个 `A`：`E-G-A-G`
- 第二个 `A`：完全重复
- `B`：改成 `A-C-A-G`
- `C`：`F-E-D-C` 下行解决

## 验证目标

这份示例现在验证的是：

1. 状态格式是否真正和 playground 对齐
2. 是否能在不超出网页自由度的前提下写出一个小型 `AABC` 循环
3. 是否能正确导出四条 stem 和最终混音
