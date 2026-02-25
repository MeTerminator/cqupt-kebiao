# CQUPT 课表查询

> **重庆邮电大学课表查询后端**。通过解析教务在线数据，提供稳定、快速、易于集成的课表接口。支持生成符合标准的 iCalendar (.ics) 文件，方便一键导入手机日历。


## ✨ 特性

* 🚀 **高性能**: 基于 **FastAPI** 构建，异步 IO 处理请求。
* 🔄 **智能合并**: 支持 **调停课信息** 自动合并至主课表。
* 📅 **自动计算**: 根据教务处数据自动推导学期第一周周一日期。
* 🚀 **高速缓存**: 基于 **Redis** 缓存机制，显著减少教务处内网穿透压力。
* 🔔 **高度定制**: 导出日历支持自定义多重闹钟提醒。

## 🛠️ 环境要求

* **内网环境**: 本程序必须部署于 **重邮校园网（校内 IP）** 环境下，才可穿透访问教务在线 API。
* **依赖服务**: Redis (用于数据持久化缓存)。


## 📖 接口文档

### 1. 日历导出 (iCalendar)

`GET /api/curriculum/{student_id}/curriculum.ics`

获取标准的日历文件，支持在 URL 中定制提醒。

| 参数 | 类型 | 必须 | 描述 |
| --- | --- | --- | --- |
| `first` | `int` | 否 | 第一优先级提醒时间（单位：分钟）。 |
| `second` | `int` | 否 | 第二优先级提醒时间（需小于 `first`）。 |

**示例:**

* 不带提醒: `/api/curriculum/202621xxxx/curriculum.ics`
* 30分钟及10分钟双重提醒: `.../curriculum.ics?first=30&second=10`


### 2. JSON 课表数据

`GET /api/curriculum/{student_id}/curriculum.json`

返回详细的 JSON 格式课表实例，适合移动端/小程序直接渲染。


### 3. 课程总览

`GET /api/curriculum/{student_id}/overview`

返回学生当前学期的统计数据（如课程总数、学分概况等）。


## 🚀 快速开始

1. **克隆仓库**
```bash
git clone https://github.com/MeTerminator/cqupt-kebiao.git
cd cqupt-kebiao

```


2. **配置环境变量**
创建 `.env` 文件并配置 Redis 连接：
```env
REDIS_URL=redis://localhost:6379/0

```


3. **运行服务**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000

```


## 📄 开源协议

本项目基于 **[MIT License](https://www.google.com/search?q=LICENSE)** 协议开源。
