# 2026-10-20 不同付款邮箱的双客户补验准备

用户只读确认Creem现有客户邮箱为hello@notavue.io，两轮交易均归该客户；首次Google付款的交付记录也明确收银台使用hello@。前轮未满足两个独立付款客户前提，失败、退款、待审及修复记录见[客户冲突记录](2026-10-20-provider-customer-conflict.md)。用户现选择已有Google账号的Gmail作为下一轮付款邮箱，应用仍登录hello@，并亲自操作第三方软件/网页。**这仅确定测试输入，不构成新邮件、checkout、付款或Portal授权。**不同邮箱是否返回不同客户仍须真实核对，未验证Creem内部去重规则。

## 本地准备与边界

从10/19原账单隔离库克隆新库 `notavue_two_paid_distinct_20261020`，不从失败冲突库删除或重置数据；旧冲突库纳入只读摘要保护。新副本仅Google有原退款客户绑定及30秒已用历史，邮箱无客户绑定，两身份仍按精确issuer+subject映射，未伪造新付款/客户或额度。复制来源storage和mail至独立目录，tmp/Redis命名空间独立。

准备脚本 `/tmp/notavue-prepare-two-paid-distinct-20261020.py` 已执行成功：准备前后六份来源PG库全public表摘要一致，来源mail SHA不变；新库初始全表摘要匹配模板。新私密配置 `.env.two-paid-distinct-test.local` 和 `.env.two-paid-distinct-mail-test.local` 为0600，新目录为0700，付款邮箱计划仅保存在忽略目录。源码与证据备份于 `.data/notavue-two-paid-distinct-20261020/tools`；不提交配置、数据库、身份ID、客户ID或付款链接。

仅临时启动本机原隔离PG完成克隆，结束已停机；没有启动Web/API/Redis、邮件Hook或Tunnel，没有第三方调用。新邮件/交易/Portal授权均为零；旧邮件和付款次数门闩未修改。旧Send Email Hook已禁用、Creem webhook保持关闭，本步不重新访问第三方控制台。

## 验证与审查

准备脚本正常路径的摘要、两用户、唯一Google客户、邮箱无绑定、无删除单、原revoked/used30历史及停机断言通过。独立审查确认storage六文件哈希逐个相同，mail副本/来源SQLite全表逻辑摘要相同，私密文件权限及停机状态符合要求；审查者未独立启动PG重算六库。

审查发现并修复两个本地准备问题：启动PG和首次resources写入现均位于try/finally内，覆盖启动超时但已出现pid及资源文件写失败后的停机；配置原只禁用已存在的键，遗漏默认True的analysis_enabled，现枚举Settings全部_enabled字段显式写false，实际用两份原load_settings加载后全部10个功能开关均False。未改生产Settings或全局规则。

纯离线故障测试 `songdance/api/.venv/bin/python /tmp/notavue-test-distinct-prepare-cleanup-20261020.py` 两项通过，分别验证启动超时及resources写失败，均执行stop、清除模拟pid且保留原异常；不连接真实PG。初次故障测试因沙箱拒绝socket预检先失败，随后对探针作离线替身后测试通过，没有将初次失败计为清理分支通过。脚本语法及文档diff检查通过。本轮未改产品代码，不重复运行上一批业务回归或冒称本轮真实双客户验收通过。

## 下一轮操作顺序（待限定授权）

1. 开启新副本的本机测试站点；用户在普通Chrome登录原Google账户，无痕Chrome登录hello@邮箱账户。若需邮件，先取得最多1次发送及同范围临时签名邮件入口授权，再向hello@发送；保持2封/小时，未知结果不自动重发，完成后禁用Hook并关闭入口。
2. 本轮最多创建1个邮箱账户checkout、1笔Notavue Pro Test模拟付款，商品USD9.90、含税总额不超过USD12；用户亲自打开收银台，核对Test Mode和商品，**付款邮箱填已有Google账号的Gmail**，亲自确认最终金额/条款并提交。应用登录邮箱与付款邮箱可以不同，业务归属仍取已登录身份及持久checkout。
3. 后台通过受限GET核对权威checkout、新客户ID必须与原Google绑定不同，才继续双账户summary/query/body拒绝与两个客户各最多1次Portal检查。若客户仍复用，保留待审、停止矩阵，不能移动旧绑定或自动再付款。
4. 用户在Creem Test控制台对本轮唯一新交易全额模拟退款并停止新订阅续费；后台只读核对退款与停费。仅处理本轮新交易，不变更旧客户邮箱、旧订阅或旧付款记录。
5. 核对六份源库及原Google财务摘要，退出两会话、禁用邮件Hook、关闭临时入口及全部本轮服务、移除临时测试页，保留证据。本轮不做真实身份删除、Live付款或两个同时active订阅签收。

最终fresh独立复审未发现可行动问题，独立加载两份配置及重跑两项离线故障验证通过；未触网或重复执行prepare。结束时主Agent核对3002/8002/8024/58781/58776五端口全部关闭，新目录无供应商调用审计或发送/交易次数门闩，停机证据保留于final-preparation-check.json。

上述限定授权尚未取得，当前停在本地准备完成，不要求用户先操作第三方页面。
