# 2026-10-20 active订阅删除的本地准备

本地准备完成，尚未创建新checkout/付款、发信或删除申请。下一真实目标是一笔新Test订阅仍active时，原删除Worker先停止续费并核验，再清理业务账户。新库为notavue_active_deletion_20261020，采用Google登录，不开邮件Hook/Tunnel；收银台拟用support@notavue.io别名，但新客户是否独立须核供应商结果。

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

## 下一轮建议范围，尚未授权

用户Google登录；最多1checkout/1笔Notavue Pro Test月付，商品USD9.90含税不超USD12，收银台拟support@；OTP/Hook/Tunnel/Portal均0。最终确认页明确目标和文件数量后，原后台仅对权威核实的本轮新active订阅自动取消一次，核实停费前不得清理。结束由用户对原新交易累计全额模拟退款，Agent只读核对并更新保留账本，关闭全部服务。出现旧客户复用、未知交易或退款差额则停止/留审，不新建付款补余额。

当前无需用户操作网页。真实active取消、删除/退款及失败恢复、完整BA-13均尚未签收；原八库和已完成验收保持。

最终复审无可行动问题，原4处运行边界P2均关闭。文档/DEV-PLAN及私密准备证据计数一致、相对链接有效；源码与tools归档一致、配置0600/目录0700/10开关False、scope/最终删除授权均不存在且PG pid不存在。八库与文件摘要为主Agent真实准备/复核证据，审查者不重访现库。五端口全部关闭、供应商调用0；真实API/Web/进程树与供应商行为待下一轮按授权执行，本批不扩大为active删除通过。
