# 初一两阶段评审服务

Python 3.11+ 标准库。环境变量 CHUYI_DATA_DIR、CHUYI_BASE_PATH（默认 /chuyi）、CHUYI_HOST（默认127.0.0.1）、CHUYI_PORT（默认5275）、CHUYI_PUBLIC_ORIGIN（默认 https://8.141.114.201）。运行与操作见项目 README.md。

首次启动创建管理员和私有 admin-access.txt，不预置简单密码。Cookie chuyi_session 使用 /chuyi 路径、HttpOnly、SameSite=Strict，HTTPS 自动 Secure。POST 必须 JSON、同源 Origin；所有管理接口验证 admin，评分验证 judge 及其 judgeStage。数据与 GOTC 完全独立。

公开 GET /api/board 返回路演排名、qualification、finalists 和 awards；隐藏成绩时去除对应分数、资格与获奖信息。GET /api/session 查询身份。POST /api/login /api/logout 登录退出。

路演默认 `minJudges=1`：评委身份数量不设上限，一位评委正式提交后即产生有效分；后续每增加一份正式评分，平台对全部有效分重新求平均并由看板轮询显示。决赛默认 `finalMinJudges=6`，每支入围队伍达到六位有效评委后才形成四奖均分。

GET /api/judge/roadshow、/api/judge/final 返回本阶段队伍、myScores、dimensions、scoringOpen。POST /api/score 必须 stage、teamId、status（draft/submitted/recused），非回避时填写本阶段全部 scores；feedback 可选。

管理员 GET /api/admin；POST /api/admin/settings、teams、invitations、revoke、qualify、unqualify、awards；GET /api/admin/export 导出两阶段CSV。invitations 使用 role=judge 和 judgeStage。qualify 在边界同分时需要严格N个teamIds；awards 使用 awardId 和 teamId，限当前最高分候选。所有操作校验阶段和状态并写审计日志。

正式活动可在私有数据目录放置 `shared-login-codes.json`，以 `{"judge":"六位或更长邀请码"}` 为所有评委启用统一邀请码。登录后仍需选择独立评委身份，路演与决赛身份及评分互不混用；配置文件不得提交到 Git。

可保留原观众接口供后续扩展，官网不开放观众投票，观众票不计入任何评审成绩。
