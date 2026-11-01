# 初一 AI 创想黑客松

北京亦庄实验中学 · 2026 年 11 月 1 日。直接复用 GOTC 官网结构、样式、评分服务和实时看板，使用初一活动现有机械臂主视觉与独立两阶段评审。

## 正式入口

- GitHub Pages 官网镜像：https://simonchenjh98.github.io/chuyi-ai-hackathon-2026/
- 官网：https://8.141.114.201/chuyi/
- 学生作品提交：https://8.141.114.201/chuyi/submit.html
- 组织方作品下载：https://8.141.114.201/chuyi/submit.html#admin
- 路演评委：https://8.141.114.201/chuyi/platform.html#judge-roadshow
- 决赛评委：https://8.141.114.201/chuyi/platform.html#judge-final
- 路演成绩：https://8.141.114.201/chuyi/platform.html#board-roadshow
- 决赛奖项：https://8.141.114.201/chuyi/platform.html#board-final
- 组织方：https://8.141.114.201/chuyi/platform.html#admin

## 运行

零构建 HTML/CSS/JS；后端仅需 Python 3.11+ 标准库。

```powershell
$env:CHUYI_DATA_DIR = '.runtime/local-data'
$env:CHUYI_PORT = '5275'
$env:CHUYI_PUBLIC_ORIGIN = 'http://127.0.0.1:5275'
python -B server/app.py
```

访问 http://127.0.0.1:5275/chuyi/ 。首次运行的管理码在指定数据目录 admin-access.txt。请勿提交、公开运行数据或邀请码。云端部署见 deploy/README.md。GitHub Pages 镜像只展示活动官网，其评委与成绩入口会跳转到正式服务；本项目应完整部署 Python 服务才能使用评分。

## 学生作品提交与批量下载

`submit.html` 中学生按报名队号选择本组即可进入，无需活动提交码或修改凭证。
作品可上传 PPT/PPTX/PDF、HTML/HTM/ZIP，或填写在线演示链接；每组最多6个附件，每个100MB。
支持同队多设备同时登录，任何设备选择本组即可继续修改作品；老师后台仍使用组织方管理码。
作品记录在 SQLite，附件和临时 ZIP 位于私有 `CHUYI_DATA_DIR/project-files`，不进入源码或公开静态目录。

老师在 `submit.html#admin` 使用原组织方身份登录，按队号查看进度，搜索与筛选、勾选多组或全选，
一键下载全部／仅PPT／仅网页。ZIP按队号建立各组目录，并附作品说明和CSV清单。
只提供在线网址时保存链接与说明；完整网页原文件需学生上传HTML或ZIP，依赖外部API的网页仍需联网。

## 评审流程

1. 管理员录入队号、队名、作品和创作方向，可从表格批量粘贴。路演评委输入统一邀请码后直接进入，系统按浏览器自动保存独立身份；决赛评委继续选择自己的01—06号身份。两轮评分分别保存。
2. 路演采用六维 100 分配置（20/20/20/15/15/10），评委人数不设上限；一位评委正式提交后即产生有效分并同步看板，更多评委提交后按全部有效分取平均。草稿、回避不计分；停用账号后其已提交评分继续保留。
3. 路演可设置北京时间定时开放，本届设为2026年11月1日13:00。计划由服务器执行，重启后保留；到点开放后仍可人工关闭。前6或8名名单可供现场参考，同分由现场裁定；名单不控制独立决赛入口。
4. 决赛独立开放，不等待路演评分、晋级或阶段切换。评委点击全部队伍中的标签，填写四项各 0–25 分：最佳创意奖、最佳技术实现奖、最具应用潜力奖、最具社会关怀奖，每位评委合计满分 100。专项奖将 6 位评委对应项相加，满分 150；全场 MVP 将四项全部相加，满分 600。路演分不带入，允许一队多奖。
5. 决赛第一份正式评分提交后即显示暂定累计分和已提交人数。已有正式评分的参评队伍全部收到 6 位评委评分后，关闭决赛；逐项确认四个专项奖及 MVP，平分由现场裁定。未参评队伍不阻止确认；重新开放决赛或改变门槛会清除获奖确认。
6. 两轮分别控制评分与成绩公开。看板约每 1 秒更新；路演大屏在同一页面连续显示全部队伍，上下滚动查看，不分页；决赛大屏继续每12秒轮播，队伍明细每屏最多8队。CSV 导出包含两阶段评分明细、每位决赛评委总分和团队 MVP 累计分。

均分以精确十分数求和、四舍五入到两位小数；排名与同分按该显示分数比较。

## 内容与源码

- index.html / styles.css / app.js：活动内容、赛程、四方向、评分说明。
- platform.html / platform.css / platform.js：两类评委、两类看板、组织方。
- server/app.py：独立认证、阶段权限、SQLite 持久化及成绩聚合。
- assets/：仅初一活动主视觉。downloads/：提交自查清单、ICS 日历。
- event-data/teams.public.json：23 支队伍的公开字段；不含学生姓名、手机号、微信号等报名隐私。

赛程依据用户提供的一页执行方案，标注为建议流程；15:10–16:40 内部路演与决赛分割待现场统筹。四个创作方向依据学生手册：现实问题、帮助学习、研究探索、创意小游戏。评分权重沿用 GOTC 平台配置，不冒充另行确认的现场最终规程。

## 验证

```powershell
node --check app.js
node --check platform.js
node --check submit.js
node --test tests/platform.test.mjs tests/submit.test.mjs
python -B scripts/check_site.py
python -B -m unittest discover -s server -p 'test_*.py'
python -B -m unittest discover -s deploy -p 'test_install.py'
python -B scripts/check_concurrency.py
```

测试使用临时数据库，正式服务数据不在源码包中。代码沿用 MIT 许可；活动名称、主视觉与标识的权利归各自权利人所有。
