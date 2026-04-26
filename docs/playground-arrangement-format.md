# Playground 精确状态格式

用于脚本：`tools/ableton_playground_exact.py`

这份格式按 [The playground](https://learningmusic.ableton.com/the-playground.html) 的真实控件自由度来设计，不再使用之前那种更泛化的“任意事件参数”模型。

## 一、网页真实约束

### `beats`

- 固定 8 条鼓轨：
  - `Kick`
  - `Rim`
  - `Snare`
  - `Clap`
  - `ClosedHat`
  - `OpenHat`
  - `Tom`
  - `Ride`
- 固定 4 小节长度
- 每小节 4 拍
- 每拍 1 个 grid
- 总共 `16` 个 grid
- 每个格子只有 `开 / 关`
- 不能改音高
- 不能改时值
- 不能改力度

### `basslines` / `chords` / `melodies`

- 固定 4 小节长度
- 每小节 4 拍
- 每拍 1 个 grid
- 总共 `16` 个 grid
- 可以改：
  - `root`
  - `scale`
  - 音符块的位置与长度
- 不能改：
  - 力度
  - 每个音的独立音色参数
  - 任意超出当前可见音阶范围的音高
- 可用音高来自当前 widget 固定显示范围：
  - `basslines`：2 个八度范围
  - `chords`：2 个八度范围
  - `melodies`：2 个八度范围

## 二、顶层格式

```json
{
  "name": "playground-exact-aabc",
  "tempo": 240,
  "beats": {},
  "basslines": {},
  "chords": {},
  "melodies": {}
}
```

说明：

- `name`：最终总混音文件名前缀
- `tempo`：全局 BPM
- 其余四项就是网页上四个模块的状态

如果你希望渲染结果是“每小节 1 秒、4 小节总共 4 秒”，那么应使用 `tempo = 240`。在这个模型里，`1 grid = 1 beat`。

注意：`master_gain` 不属于网页状态本身，因此改为 CLI 参数 `--master-gain`。

## 三、beats 格式

```json
{
  "active_steps": {
    "Kick": [0, 1, 2, 3, 4, 5, 6, 7],
    "Clap": [1, 3, 5, 7],
    "ClosedHat": [0, 2, 4, 6]
  }
}
```

说明：

- 每条鼓轨是一组 step 索引
- step 范围固定是 `0..15`
- 这完全对应网页中的“格子开/关”

## 四、tonal widget 格式

```json
{
  "root": "C",
  "scale": "Major/Ionian",
  "notes": [
    { "lane": 0, "start": 0, "length": 1 },
    { "lane": 2, "start": 1, "length": 1 }
  ]
}
```

说明：

- `root`：当前根音
- `scale`：当前音阶
- `notes`：音符块数组

每个音符块字段：

- `lane`：音阶格子的纵向位置
- `start`：起始 step
- `length`：持续 step 数

限制：

- `start` 固定范围 `0..15`
- `length` 最少 `1`
- `start + length` 不能超过 `16`

## 五、lane 的含义

对于 `basslines` / `chords` / `melodies`：

- `lane = 0` 表示当前显示范围内最低的主音
- 后面沿当前音阶逐级向上排列
- 因为网页固定显示 2 个八度，所以总 lane 数是：
  - `7 * 2 + 1 = 15`
- 所以可用 lane 范围固定为 `0..14`

举例，在 `C Major/Ionian` 下：

- `0 = C`
- `1 = D`
- `2 = E`
- `3 = F`
- `4 = G`
- `5 = A`
- `6 = B`
- `7 = C`
- ...
- `14 = C`

## 六、支持的音阶

与网页一致：

- `Major/Ionian`
- `Minor/Aeolian`
- `Dorian`
- `Phrygian`
- `Lydian`
- `Mixolydian`
- `Locrian`

## 七、输出结果

脚本会生成：

- `beats.wav`
- `basslines.wav`
- `chords.wav`
- `melodies.wav`
- `<name>-full.wav`
- `manifest.json`

## 八、运行方式

```bash
python tools/ableton_playground_exact.py --state examples/playground_arrangement_demo.json --output-dir out/playground-exact-demo --master-gain 1.0
```
