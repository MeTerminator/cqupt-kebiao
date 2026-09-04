# CQUPT 课表查询

> **重庆邮电大学课表查询后端**。通过解析教务在线数据，提供稳定、快速、易于集成的课表接口。支持生成符合标准的 iCalendar (.ics) 文件，方便一键导入手机日历。


## ✨ 特性

* 🚀 **高性能响应**: 基于 **FastAPI** 异步 IO 构建；采用 **PostgreSQL 持久化缓存**，实现“先响应缓存，后台静默更新”。
* 🔄 **全量数据整合**:
    * **常规课表**: 精准解析课程代码、教学班、学分及修读类型。
    * **调停课**: 自动追踪“补课、代课、停课”信息并动态修正主课表。
    * **考试/补考**: 深度整合普通考试与补考安排，补考信息不受学年学期限制。

* 📅 **智能时间逻辑**:
    * **自动推导**: 实时从教务在线数据推导学期第一周周一，精准识别“第 0 周”开学预备期。
    * **跨周处理**: 智能切换视角，如周日晚自动呈现下周一的课程预告。

* 🛠️ **冲突标注算法**: 自动检测同时间段多门课程冲突，采用 `#1`, `#2` 格式合并描述，确保信息不遗漏。
* 🆔 **深度学号兼容**: 完美支持重邮 10 位纯数字学号及 **`L` 开头的特殊学号**，内置大小写标准化自动转换。
* 🔔 **高度定制导出**: 支持生成符合标准的 `.ics` 日历文件，支持自定义多重闹钟提醒逻辑（如：课前 30min 初提醒，10min 二次提醒）。
* 🎨 **优雅数据呈现**: 针对外教名与复杂教师备注（修、名单、学分）进行智能清洗拼接。

## 🛠️ 环境要求

* **内网环境**: 本程序必须部署于 **重邮校园网（校内 IP）** 环境下，才可穿透访问教务在线 API。
* **依赖服务**: PostgreSQL（用于持久化原始页面、缓存时间和学生姓名）。


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


### 3. 下学期课表

* `GET /api/curriculum/{student_id}/curriculum-next.json`
* `GET /api/curriculum/{student_id}/curriculum-next.ics`

数据来源为教务在线课表公示页。此功能受项目根目录 `config.json` 控制：

```json
{
  "next_curriculum": {
    "enabled": true,
    "week_1_monday": "2026-09-07"
  }
}
```

`enabled` 为 `false` 时，两个下学期接口均返回 HTTP 503 JSON：

```json
{
  "enabled": false,
  "message": "下学期课表查询功能暂未开启"
}
```

下学期的学年和学期直接从教务在线页面读取。只有能同时读取姓名、学年和学期的页面才会入库。


### 4. 课程总览

`GET /api/curriculum/{student_id}/overview`

返回学生当前学期的统计数据（如课程总数、学分概况等）。


## 🚀 快速开始

1. **克隆仓库**
```bash
git clone https://github.com/MeTerminator/cqupt-kebiao.git
cd cqupt-kebiao

```


2. **配置环境变量**
创建 `.env` 文件并配置 PostgreSQL 连接。教务在线请求使用内置请求头；如生产环境需要通过 SOCKS5 代理访问，可选地设置代理地址：
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cqupt_kebiao
# 未设置 KEBIAO_REQUEST_PROXY 时直连
KEBIAO_REQUEST_PROXY=socks5://user:password@proxy.example.com:1080
```

`KEBIAO_REQUEST_PROXY` 也可使用无需认证的地址，例如 `socks5://127.0.0.1:1080`。

应用启动时会自动创建或升级 `student_curriculum_cache` 表。表以
`student_id + academic_year + semester` 为联合主键，不指定学期时默认读取最新学期。
修改 `config.json` 后需要重启应用。


3. **运行服务**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000

```


## Redis 数据迁移

从旧版 Redis 复制课表 HTML、考试 HTML、补考 HTML、时间戳和可解析的学生姓名。
脚本不会删除 Redis 原数据，也不会覆盖 PostgreSQL 中已存在的同学号、同学期记录。
执行前需在 `.env` 中临时配置 `REDIS_URL`，或通过 `--redis-url` 传入旧 Redis 地址。

```bash
# 先预览
uv run --group migration python scripts/migrate_redis_to_postgres.py

# 确认后执行
uv run --group migration python scripts/migrate_redis_to_postgres.py --apply
```

可使用 `--student-id <学号>` 仅迁移单个学号，使用 `--verbose` 查看每条结果。


## 无姓名数据清理

清理脚本默认仅统计将被删除的记录：

```bash
python3 scripts/delete_nameless_postgres_data.py --verbose
```

确认后执行删除，并为 `student_name` 启用 `NOT NULL` 约束：

```bash
python3 scripts/delete_nameless_postgres_data.py --apply --verbose
```


## 📄 开源协议

本项目基于 **[MIT License](https://www.google.com/search?q=LICENSE)** 协议开源。
