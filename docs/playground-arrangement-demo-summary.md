# Playground 精确示例说明

示例配置：`examples/playground_arrangement_demo.json`

这份示例严格对齐 [The playground](https://learningmusic.ableton.com/the-playground.html) 的真实状态模型，只描述网页本身可编辑的内容：

- `beats`：格子开 / 关
- `basslines/chords/melodies`：
  - 当前 `root`
  - 当前 `scale`
  - 音符块的 `lane / start / length`

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
- `ClosedHat`：按偶数拍形成稳定推动
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
