# 教师反馈约束下的候选重建入口

本阶段是固定候选重建，不是已完成Transkun全链集成。使用api/scripts/build_reviewed_candidates.py，指定全新输出目录，可重复生成隔离候选。

```sh
cd songdance/api
.venv/bin/python -m scripts.build_reviewed_candidates --output tests/fixtures/audio/candidates/reviewed-candidates-v2
```

07输入SHA必须匹配教师回传记录，输出原样复制，保留已通过的检查项。10输入同样冻结，仅复用既有二分音符节奏修订，验证原音高起音与高音节点一致，状态明确为待教师复评且缺失低音仍待修复。06不输出新曲谱，标记blocked，先对齐音频与教师参考。

运行拒绝覆盖旧目录，已确认输入被改动时在写入之前失败；构建或解析出错保留failed清单，不能误标成功。manifest记录教师反馈、来源/结果、构建器和时值修订器哈希，始终production_eligible=false。

实际输出reviewed-candidates-v1已落盘；5测试通过、Ruff/compileall/xmllint通过。MuseScore 4本地存在，QT_QPA_PLATFORM=offscreen启动报只有cocoa插件可用；不能把此自动化启动失败说成XML无法导入，也不能把music21或xmllint成功代替MuseScore验收。fresh独立审查尝试因agent thread limit reached未能启动，当前仍非发布就绪。

## 用户确认后的默认模式

用户确认“都没问题进行下一步”后，默认CLI切换为accepted模式，按2026-09-16-accepted-candidates.json原样复制06/07/10曲谱及配套音频，不再次运行模型或改写时值。新模式保留来源为用户确认，不虚构老师逐条新评级或自动MuseScore验证通过。旧生成行为可显式使用--mode historical。

实际产物accepted-candidates-v1已建立，含3份MusicXML、3份对应WAV和manifest.json。06绑定新三音合成源；07保留原听审版；10绑定bass-rhythm-v2且保留0/15/16秒C2漏检的技术限制。确认候选与生产准入分别记录，production_eligible始终false。已接受文件或音频变动时先拒绝构建，不偷偷更新哈希。

15项相关测试、Ruff、compileall、3份xmllint通过。代码独立fresh复审仍待恢复可用审查资源后完成；没有创建最终ZIP、替换生产模型或宣称低音识别问题消失。

## 冻结候选的独立校验命令

```sh
.venv/bin/python -m scripts.validate_accepted_candidates tests/fixtures/audio/candidates/accepted-candidates-v1
```

可用--report指定新报告路径（排他创建，不覆盖旧报告）。验证器重新比对接受清单、候选集合、来源类型、已知限制、实际WAV/XML哈希和实际解析结构；缺组、重复组、换音频、删限制、改路径或production标记均失败。产物自报的通过状态不能替代这些检查。

实际三组校验通过，06/07单谱表、10双谱表，均0小节时值错误；10漏音限制保持。新增8项测试，相关共23 passed，Ruff/compileall通过。该校验不是模型上线门禁的替代，也不冒充独立人工代码复审。
