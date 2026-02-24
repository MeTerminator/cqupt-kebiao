# CQUPT 课表查询

> 重庆邮电大学课表查询，需部署到校内网络环境才可访问教务在线。

## 介绍

- 基于 FastAPI 构建
- 支持 __调停课__ 合并主课表
- 自动计算学期开始日期
- 数据来源于教务在线
- 基于 redis 缓存课表数据

## API

- GET /api/curriculum/<学号>/curriculum.ics
  - 返回指定学号的课表 iCalendar 文件

- GET /api/curriculum/<学号>/curriculum.json
  - 返回指定学号的 json 格式课表数据

