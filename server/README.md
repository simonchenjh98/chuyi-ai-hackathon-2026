# 初一两阶段评审服务

Python 3.11+ 标准库。环境变量 CHUYI_DATA_DIR、CHUYI_BASE_PATH（默认 /chuyi）、CHUYI_HOST（默认127.0.0.1）、CHUYI_PORT（默认5275）、CHUYI_PUBLIC_ORIGIN（默认 https://8.141.114.201）。运行与操作见项目 README.md。

首次启动创建管理员和私有 admin-access.txt，不预置简单密码。Cookie chuyi_session 使用 /chuyi 路径、HttpOnly、SameSite=Strict，HTTPS 自动 Secure。POST 必须 JSON、同源 Origin；所有管理接口验证 admin，评分验证 judge 及其 judgeStage。数据与 GOTC 完全独立。

公开 GET /api/board 返回路演排名、qualification、finalists、awards 和 mvp；隐藏成绩时去除对应分数、资格与获奖信息。GET /api/session 查询身份。POST /api/login /api/logout 登录退出。

路演默认 `minJudges=1`：评委身份数量不设上限，一位评委正式提交后即产生有效分；后续每增加一份正式评分，平台对全部有效分重新求平均并由看板轮询显示。决赛默认 `finalMinJudges=6`，四项各 25 分；每队最多 6 份正式评分。`finalTotals` 为四项累计分（各满分 150），`finalTotal` 为 MVP 累计总分（满分 600），第一份正式评分起实时展示。`finalReady` 表示已收齐规定人数；`finalScores` 保留收齐后的各项均分供兼容使用。

GET /api/judge/roadshow、/api/judge/final 返回本阶段队伍、myScores、dimensions、scoringOpen。POST /api/score 必须 stage、teamId、status（draft/submitted/recused），非回避时填写本阶段全部 scores；feedback 可选。

管理员 GET /api/admin；POST /api/admin/settings、teams、invitations、revoke、qualify、unqualify、awards；GET /api/admin/export 导出两阶段CSV。invitations 使用 role=judge 和 judgeStage。qualify 在边界同分时需要严格N个teamIds；awards 使用 awardId 和 teamId，限当前最高分候选。所有操作校验阶段和状态并写审计日志。

正式活动可在私有数据目录放置 `shared-login-codes.json`，分别为 `admin`、`judge`、`audience` 配置六位或更长的统一邀请码。登录后仍选择独立身份，组织方、路演与决赛权限及评分互不混用；配置文件不得提交到 Git。

新计分版本为 `finalScoringVersion=2`。升级旧库时如已有旧制决赛评分，启动会明确拒绝，避免把原 100 分制静默当作 25 分制；需在备份后由组织方确认处理。无旧决赛评分的库自动登记新版本，路演数据不变。

可保留原观众接口供后续扩展，官网不开放观众投票，观众票不计入任何评审成绩。
