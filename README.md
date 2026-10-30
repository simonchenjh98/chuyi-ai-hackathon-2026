# 初一 AI 创想黑客松

北京亦庄实验中学 · 2026 年 11 月 1 日。直接复用 GOTC 官网结构、样式、评分服务和实时看板，使用初一活动现有机械臂主视觉与独立两阶段评审。

## 正式入口

- 官网：https://8.141.114.201/chuyi/
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

访问 http://127.0.0.1:5275/chuyi/ 。首次运行的管理码在指定数据目录 admin-access.txt。请勿提交、公开运行数据或邀请码。云端部署见 deploy/README.md。GitHub Pages 只支持静态信息页，本项目应完整部署 Python 服务才能使用评分。

## 评审流程

1. 管理员录入队号、队名、作品和创作方向，可从表格批量粘贴。每位评委创建专属邀请码并分配 roadshow 或 final 阶段；兼任者使用两个身份。
2. 路演采用六维 100 分配置（20/20/20/15/15/10），达到门槛后以已提交评分均分排名。默认至少 3 名评委，可调整。草稿、回避不计分；停用账号后其已提交评分继续保留。
3. 晋级名额选择 6 或 8。全部队伍达到门槛、关闭路演后确认名单；晋级线平分须现场裁定，只能在同分队中选择，其他更高分队伍必须保留。冻结后不能重开路演或更改路演资格规则；尚无决赛正式评分时可以撤销名单，清理决赛草稿。
4. 切换决赛阶段并开放决赛。四项各 0–100 分：最佳创意奖、最佳技术实现奖、最具应用潜力奖、最具社会关怀奖；各项分别计算均分、各项最高者获奖，路演分不带入，允许一队多奖。
5. 所有入围队伍达到决赛评委门槛后，关闭决赛评分；逐奖从最高分候选中确认获奖，平分由现场评审裁定。重新开放决赛或改变其门槛会清除获奖确认。
6. 路演、决赛分别控制公开成绩。看板每 2 秒刷新；路演大屏每 12 秒轮播 8 队。CSV 导出包含两阶段评分明细；决赛不计算跨奖项总分。

均分以精确十分数求和、四舍五入到两位小数；排名与同分按该显示分数比较。

## 内容与源码

- index.html / styles.css / app.js：活动内容、赛程、四方向、评分说明。
- platform.html / platform.css / platform.js：两类评委、两类看板、组织方。
- server/app.py：独立认证、阶段权限、SQLite 持久化及成绩聚合。
- assets/：仅初一活动主视觉。downloads/：提交自查清单、ICS 日历。

赛程依据用户提供的一页执行方案，标注为建议流程；15:10–16:40 内部路演与决赛分割待现场统筹。四个创作方向依据学生手册：现实问题、帮助学习、研究探索、创意小游戏。评分权重沿用 GOTC 平台配置，不冒充另行确认的现场最终规程。

## 验证

```powershell
node --check app.js
node --check platform.js
node --test tests/platform.test.mjs
python -B scripts/check_site.py
python -B -m unittest discover -s server -p 'test_*.py'
python -B -m unittest discover -s deploy -p 'test_install.py'
```

测试使用临时数据库，正式服务数据不在源码包中。代码沿用 MIT 许可；活动名称、主视觉与标识的权利归各自权利人所有。
