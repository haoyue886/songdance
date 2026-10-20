# 2026-10-20 active订阅真实删除、自动停费与删除后退款

本轮限定真实Test闭环已完成：Google目标的新订阅active时，由原删除Worker自动取消一次、GET核实canceled后才清理业务账户；删除后用户累计全额模拟退款USD11.78，原后台成功将停用账户的既有权益撤销，重复处理数0。新库notavue_active_deletion_20261020、收银台support@notavue.io为独立新客户；原8库和保护账户不变，用户已退出，全部服务及五端口关闭。未使用OTP、邮件Hook/Tunnel或Portal。本记录保留下方准备阶段事实，当前结果以执行续记及收尾为准。

准备先发现并修复[删除后退款无法同步](2026-10-20-deleted-account-refund.md)，已提交67e2104。精确既有交易在inactive后可记录退款/争议，新期仍拒绝。193普通、20既有PG组合、7专项PG通过，独立审查无问题；本地结果不代表真实active删除已通过。

## 隔离数据

新库从template0创建并执行正式Alembic迁移，导入两份原User/AuthIdentity的精确issuer+subject映射。目标Google在此专用测试库无客户、checkout、订阅、付费/用量周期；原Google账本及已删除墓碑仍保留在来源库，未清除原记录或重置生产额度。

保护邮箱账户的真实全退财务图七表按原字段导入，与来源逐字段摘要一致。目标不导入旧付款历史是明确的新测试lane设计，避免将自然时间重叠的独立验收付款强塞同一周期；不是生产迁移或账本恢复。

两账户各有1复制任务、6存储文件、1合成pipeline临时文件。重写所有ID/文件键，清空reservation和guest引用、关闭dispatch；不是新上传/模型或真实consume/release。两个任务前8位不同，拒绝symlink，源文件只读复制。原八库（含刚完成删除副本）及来源storage准备前后数据摘要相同；摘要不代表数据库文件/schema/序列逐字节一致。

配置0600、外层0700，独立storage/tmp/Redis/queue。原load_settings实际加载全部10个功能开关和Web auth为false；不新建密钥。两个历史customer在私密排除列表，后续若复用任一个旧客户则拒绝继续，不自动取消其旧订阅。

## 受限运行边界

供应商调用先要求实际用户限定授权文件；当前external-test-scope和最终删除授权均不存在，只有planned-scope草案。Portal及OTP-start/attempt入口拒绝，不支持mail/tunnel运行模式。checkout仅目标990分USD/1800秒/90秒、整数units1且持久一次门闩，未知结果不自动POST重试。付款前仍由用户核Test Mode、商品、含税不超USD12并接受条款。

completed checkout GET核本地意图ID/product/units/非历史客户，subscription GET核同客户商品并固定latest transaction引用。交易GET须invoice、同tx/sub/customer、amount990/USD、整数amount_paid在990至1200之间，拒绝bool/float或超限。超额时阻止投影/后续验收，不冒称该门禁能代替用户付款前核总额。

自动取消须有最终目标授权、本地唯一目标pending/retry/billing删除义务、一份新binding和active付款，refs逐项匹配；POST前即时GET核新订阅仍active及最新交易/商品/客户不变。仅该新订阅immediate取消最多一次，POST前持久门闩，未知不重试；已canceled/scheduled_cancel只GET返回。旧客户/错owner/阶段/授权/交易、revoked期均拒绝。API沿用原JWT/session/最近登录，仅target且最终授权存在才DELETE，保护账户不能删。

## 检查与审查

准备脚本fresh审查无问题，17条FK顺序、10开关及权限、只读来源、PG启动故障finally路径离线核对。主Agent实际准备和单独只读复核通过：八来源库/storage不变，两身份精确相同，保护七财务表与源相同，目标七财务表为空，2复制任务/每owner6存储1tmp，删除申请0/外部调用0；PG均finally停机。

运行脚本初审发现并修正3个P2：导入app.main会先构造默认应用，现首次导入也绑定专用FileSettings、不读仓库.env并释放unused实例；旧O_EXCL marker阻止重启，现PG前仅归档已确认死亡PID、检查子进程/端口就绪且启动失败清理；原只声明1200上限，现检查实际交易返回的含税总额/币种。编辑时一次缩进编译错误在任何执行前修正，无真实服务启动。

主Agent24项纯离线provider guard通过：checkout未知/合同拒绝、旧客户拒绝、精确取消一次/已停只GET、错owner/阶段/授权/交易拒绝、取消响应丢失两分支不重复POST、超额/bool/float/低额拒绝及1178分接受。独立24项及首次导入专用cfg、5个启动离线场景通过。复审还发现leader退出但后代忽略SIGTERM的P2，现按自建PGID是否仍有非zombie成员独立等待，必要时SIGKILL，确认后记录停止；未能清理时新lane的stopped保持false并报错。最终独立复核用自建dummy进程组确认leader退出/后代忽略SIGTERM也会被清理；group探测PermissionError时仍停模拟PG，新lane stopped=False并报错。未运行真实站点/PG或触网。

私密源码和测试保存data/tools，不提交客户引用/配置。当前所有服务停止、没有external scope/最终删除标记，不能进行真实供应商调用；未在本轮实际启动过API/Web/Redis，不把脚本编译或离线检查冒充真实运行。

## 准备阶段建议范围（后续已授权并执行）

用户Google登录；最多1checkout/1笔Notavue Pro Test月付，商品USD9.90含税不超USD12，收银台拟support@；OTP/Hook/Tunnel/Portal均0。最终确认页明确目标和文件数量后，原后台仅对权威核实的本轮新active订阅自动取消一次，核实停费前不得清理。结束由用户对原新交易累计全额模拟退款，Agent只读核对并更新保留账本，关闭全部服务。出现旧客户复用、未知交易或退款差额则停止/留审，不新建付款补余额。

准备批次结束时尚未执行真实active取消、删除/退款，原八库和已完成验收保持；后续限定分支结果见执行续记，完整BA-13仍未整体签收。

最终复审无可行动问题，原4处运行边界P2均关闭。文档/DEV-PLAN及私密准备证据计数一致、相对链接有效；源码与tools归档一致、配置0600/目录0700/10开关False、scope/最终删除授权均不存在且PG pid不存在。八库与文件摘要为主Agent真实准备/复核证据，审查者不重访现库。五端口全部关闭、供应商调用0；真实API/Web/进程树与供应商行为待下一轮按授权执行，本批不扩大为active删除通过。

## 真实执行续记（更新上述准备态）

用户随后明确授权本轮最多1个checkout、1笔Test付款（含税不超USD12）、最终确认目标后自动取消该新订阅最多1次，结束由用户全额模拟退款。第三方页面均由用户操作，本轮不发OTP、不启邮件Hook/Tunnel、不生成Portal。

首次创建在商品GET失败，原本地意图failed/PRODUCT_VERIFICATION_FAILED、无provider_id；供应商checkout POST门闩未消耗。只读商品GET恢复并核合同后，用独立本地幂等键继续原供应商唯一预算，保留旧failed记录。用户完成新付款；权威GET核completed、新customer不同于两个历史客户、订阅active、实付USD11.78。原投影产生一次1800秒、用量0/预占0；没有重复付款或删除旧意图。

付款/Worker脚本独立审查修正两处P2：选择全部checkout会被旧failed记录阻断，现明确唯一provider_id意图并核其余failed历史；pending-only和取消marker先验会阻断原退避恢复，现允许pending/retry、核原next_attempt_at，已停时GET-only恢复。24项provider guard及3项实际原服务离线执行通过，覆盖旧意图保留、取消成功但响应丢失后按原退避恢复、清理I/O失败恢复；均不替代真实供应商证据。

用户最终明确确认只删新库Google目标、1复制任务/6存储文件/1临时文件，自动停费只限本轮新订阅。原UI旧会话先403；Google重新认证后唯一DELETE202，认证距提交约36秒，pending/billing/attempts0。付款后的14表基线在申请前保存；独立审查要求的目标精确文件摘要补存在UI申请之后、首次Worker之前，核当时attempts0/active/取消门闩未用。如实区分时间边界，不将该补存摘要称为申请前证据。

原Worker真实billing handled1：供应商取消POST恰1且成功，后续GET确认为canceled，提交inactive/cleanup检查点，邮箱、1任务、6存储文件和1临时文件仍保留且文件摘要一致。第二批cleanup handled1后completed/attempts2，目标邮箱/任务及7文件清除；第三批repeat handled0。取消不等于退款，删除后的PaidPeriod此时仍active、1800/0/0保留。保护owner14表/6storage+1tmp、原8库和来源storage全摘要不变，目标身份与其余财务用量保持；订阅只允许显式核对的状态/供应商时间变化，所有账单事件不变。

完整性脚本与退款脚本fresh审查无遗留可行动问题。新增2项离线执行通过，部分退款拒绝、全退更新停用账户既有grant、退款恢复/repeat不新增供应商写；审查者另验证同数量文件篡改被摘要识别、退款provider拒绝POST/PUT/PATCH/DELETE。本段离线检查完成时，真实退款及收尾尚待完成；后续结果如下。


## 删除后全退、重复核验与收尾

用户确认原账户页“账户删除已完成”，在同一support@新交易累计退款USD11.78。受限GET确认交易refunded、实付和累计退款均1178分USD，订阅canceled；未以用户反馈替代供应商核验。原sync_transaction在账户inactive/email清除后仍精确核对既有PaidPeriod，更新revoked并产生唯一退款停费补偿。

首轮补偿复查GET失败，原后台保留retry/attempts1和原退避；PaidPeriod已撤销、删除completed，未重发取消POST。失败状态私密留档；实际时钟确认next_attempt_at已到后，GET-only恢复为verified/attempts2。首轮成功恢复handled1，随后完整退款快照保存；repeat handled0且全部target/protected表、账单事件、保护6storage+1tmp快照完全相同。目标原1800秒/consumed0/reserved0保留，权益revoked而非新授额；旧failed商品意图、退款失败和重试证据均保留。

用户确认最终仅退出Notavue应用会话。精确PID/命令收尾脚本停止本轮Web/API/Redis及原隔离PG，移除临时public验收页；五端口3002/8002/8024/58781/58776实测关闭，PG pid不存在。私密配置0600、外层0700，10个API开关及Web Auth均为false；未改系统代理或第三方开关。供应商审计总POST恰2次（唯一checkout与唯一自动取消），其他均GET，退款由用户在第三方页面提交。本轮从未启用邮件入口或Portal，没有供应商身份删除。

实际执行命令均在仓库根：`songdance/api/.venv/bin/python /tmp/notavue-active-deletion-paid-20261020.py`、`/tmp/notavue-run-active-deletion-worker-20261020.py billing|cleanup|repeat`、`/tmp/notavue-active-deletion-refund-20261020.py refund|repeat`、`/tmp/notavue-verify-active-deletion-20261020.py before|billing|cleanup|refund|final`和`/tmp/notavue-stop-active-deletion-20261020.py`；各脚本均使用同一venv，源码/测试及私密结果归档在本轮data/tools。首次沙箱本机PG访问被拒后通过审批执行，不伪称第一次成功；补存文件基线时UI申请已到，原before检查按约拒绝，随后明确验证attempts0/取消前再保存Worker前基线。收尾首次检查误把10个API开关与额外Web开关合计作10，改为分别检查10+1后通过，不涉及真实配置更改。

组合离线检查实际命令为`PYTHONPATH=songdance/api:/tmp songdance/api/.venv/bin/python -m pytest -q /tmp/test_notavue_active_deletion_guard_20261020.py /tmp/test_notavue_active_execution_20261020.py /tmp/test_notavue_active_refund_execution_20261020.py`，29 passed。保留Starlette/httpx和pkg_resources两项依赖弃用警告，不是本轮失败。独立复审另实跑退款2项及成功证据不可变恢复检查，通过；审查者未直接执行真实供应商或数据库操作，现场结果来自主Agent受限执行与用户页面反馈。

本批未改生产代码，不重复前轮已通过的193普通/20+7PG回归；未新跑转谱/专业谱面评审或生产部署。本轮目标夹具无reservation，真实单周期active停费/指定数据删除/删除后全退已通过；完整多周期、供应商失败卡/争议/退款续费竞态、运营保留策略及完整BA-13仍保留，不以单分支补证整体签收。前轮真实OTP重登墓碑验收不重复，本轮用户没有被要求重新登录已删除账户。

最终独立证据审查在本次三文档与私密快照范围内未发现可行动问题：复核Worker1/1/0、32 GET+2 POST（唯一checkout/自动取消）、原退避后verified/attempts2、保护14表/7文件、目标允许变化及旧failed历史、链接和范围声明一致。审查者未重启数据库或触网；原8库、供应商结果与端口关闭依据主Agent已保存的现场证据。
