# Transkun 扩展候选听审清单

本清单只用于人工听审，所有候选均 `production_eligible=false`，不属于最终评审包。

| 样本 | 候选文件 | 听审重点 | 结构验证 |
|---|---|---|---|
| 06-sustain | `tests/fixtures/audio/candidates/piano-model-comparison-expanded-v1/06-sustain/transkun-v2/chord-sync-candidate.musicxml` | 三和弦基音是否完整，延音是否被截短 | 1 Piano part，2 staff，13 和弦，0 小节时值错误 |
| 07-soft | `tests/fixtures/audio/candidates/piano-model-comparison-expanded-v1/07-soft/transkun-v2/monophonic-candidate.musicxml` | 弱音尾音是否需要踏板或延音标记 | 1 Piano part，1 treble staff，1 voice，0 休止符 |
| 10-device | `tests/fixtures/audio/candidates/piano-model-comparison-expanded-v1/10-device/transkun-v2/duration-candidate.musicxml` | 低音约 0.9 秒一拍是否符合原音频，左右手是否对齐 | 1 Piano part，2 staff，各1 voice，0 小节时值错误 |

OSMD 浏览器验证因本机 Chrome/Playwright 崩溃未通过；xmllint 和 music21 解析已通过。
