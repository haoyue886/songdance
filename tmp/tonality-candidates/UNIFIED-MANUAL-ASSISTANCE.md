# 局部调性固定集：统一人工协助清单

当前批次共 11 段公开真人录音。以下事项统一完成后，才能生成正式 `tests/fixtures/tonality/manifest.json` 并运行 Phase 33.1 门禁。

## A. 已有参考谱，待统一音乐真值确认

| 样本 | 作品/候选 | 参考谱 | 需要人工确认 |
| --- | --- | --- | --- |
| 03-mozart-sonata | Mozart K.545 第一乐章 | 公版 MIDI，1–17 小节已有对齐证据 | 起止小节、乐句边界、终止式、局部调性、reviewer |
| 08-chopin-a-major | Chopin Op.28 No.7 | IMSLP 公版 37 页 PDF | 起止小节、乐句边界、终止式、局部调性、reviewer |
| 10-rachmaninoff-c-sharp | Rachmaninoff Op.3 No.2 | IMSLP 公版印刷谱 30 页 | 起止小节、乐句边界、终止式、局部调性、reviewer |
| haydn-concerto-d-vivace-chestnut | Haydn Hob. XVIII:11 第一乐章 | IMSLP 公版总谱 44 页 | 钢琴声部对齐、起止小节、乐句边界、终止式、局部调性、reviewer |

## B. 需要先确认作品身份或补参考谱

| 样本 | provenance 线索 | 人工/资料确认 |
| --- | --- | --- |
| 01-bach-capriccio | Bach C 小调 Capriccio，Partita #2 | 确认 BWV/具体作品编号，再找公版谱 |
| 02-brahms-intermezzo | Brahms A 大调 Intermezzo | 确认 Opus/编号，再找公版谱 |
| 04-rachmaninoff-g-sharp | Rachmaninoff G♯ 小调 Prelude | 确认 Opus/编号；不能默认 Op.32 No.12 |
| 05-chopin-c-minor | Chopin C 小调 Prelude | 确认 Opus/编号；不能默认 Op.28 No.20 |
| 06-scriabin-etude | Scriabin D♯ 小调 Etude，provenance 写 Op.33 | 确认 Op.33 的具体编号；已下载的 Op.8 No.12 不适用 |
| 07-chopin-ballade | Chopin Ballade No.1 | 确认是否 Op.23，再找公版谱 |
| 09-chopin-waltz | Chopin 降 A 大调 Waltz | 确认 Opus/编号，再找公版谱 |

## C. 每个最终纳入样本统一填写

- 音频与谱面起止小节及对齐证据
- 乐句边界
- 终止式类型和位置
- 局部调性、major/minor
- 副属主音化或持续转调
- 原谱调号
- reviewer_id、确认日期和备注

未完成上述确认的条目保持 `eligible_for_tonality_manifest: false`，不计入准确率、校准误差或 notation 门禁。
