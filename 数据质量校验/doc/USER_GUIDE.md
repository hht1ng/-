# 数据质量检查技能 - 用户使用说明

## 1. 技能能力范围

本技能专为生产环境的大规模数据设计，能够帮助您快速发现数据质量问题。

### 支持的数据库
- MySQL
- PostgreSQL
- SQLite
- Oracle（11g 及以上）

### 支持的检查类型（覆盖常见数据质量问题）

检查类型：非空检查
功能：检查某列是否存在空值
示例场景："订单状态不能为空"

检查类型：唯一性检查
功能：检查某列值是否重复
示例场景："订单号必须唯一"

检查类型：值域检查
功能：检查列值是否在白名单内
示例场景："性别只能是 M 或 F"

检查类型：数值范围
功能：检查数值是否在区间内
示例场景："金额必须在 0 到 100000 之间"

检查类型：日期范围
功能：检查日期是否在某个范围内
示例场景："下单日期不能晚于今天"

检查类型：字符串长度
功能：检查字符长度限制
示例场景："客户姓名不超过 50 个字符"

检查类型：正则匹配
功能：检查格式（邮箱、手机号等）
示例场景："邮箱必须符合标准格式"

检查类型：外键存在性
功能：检查引用完整性
示例场景："客户ID必须在客户表中存在"

检查类型：自定义SQL
功能：实现任意复杂逻辑
示例场景："检查订单金额是否超过历史平均的2倍"

### 性能特性
- 大表自动抽样：当表记录数超过阈值（默认1000万行）时，自动随机抽样（默认100万行）进行快速检查。
- 唯一性和外键检查永不抽样：保证准确性（可强制抽样，不推荐）。
- 多线程并行执行：多条规则同时执行（默认4线程），大幅缩短等待时间。
- 跨数据库支持：自动适配不同数据库的语法差异。

### 依赖自动安装
技能会在首次连接时自动检查并安装所需的 Python 驱动包，无需手动安装全部依赖：

数据库类型：MySQL
驱动包：pymysql
自动安装：是

数据库类型：PostgreSQL
驱动包：psycopg2-binary
自动安装：是

数据库类型：Oracle
驱动包：oracledb
自动安装：是

数据库类型：SQLite
驱动包：无
自动安装：不适用

通用依赖：pandas, sqlalchemy
自动安装：是

如果自动安装失败（如网络问题或权限不足），技能会报错并提示您手动运行安装命令。

### 不支持的功能
- 数据写入或修复：本技能只读不写，不会修改任何数据。
- 实时流式数据检查：针对静态表。
- 跨数据库实例关联：只能检查同一数据库内的表。

## 2. 安装与配置

### 前提条件
- OpenClaw 已安装并正常运行。
- 目标数据库提供只读账号（强烈建议）。
- 数据库可从 OpenClaw 所在网络访问。

### 安装步骤

#### 2.1 创建技能目录

在终端中执行：
mkdir -p ~/.openclaw/workspace/skills/data-quality-checker/scripts

#### 2.2 放置技能文件

将以下两个文件放入对应位置：
- SKILL.md -> ~/.openclaw/workspace/skills/data-quality-checker/SKILL.md
- dq_checker.py -> ~/.openclaw/workspace/skills/data-quality-checker/scripts/dq_checker.py

#### 2.3 设置执行权限（Linux/macOS）

在终端中执行：
chmod +x ~/.openclaw/workspace/skills/data-quality-checker/scripts/dq_checker.py

#### 2.4 配置数据库环境变量（推荐方式）

编辑 ~/.bashrc 或 OpenClaw 的启动脚本，添加对应数据库的配置：

MySQL 示例：
export DQ_DB_TYPE="mysql"
export DQ_DB_HOST="your-db-host.example.com"
export DQ_DB_PORT="3306"
export DQ_DB_NAME="your_database"
export DQ_DB_USER="readonly_user"
export DQ_DB_PASSWORD="your_secure_password"

PostgreSQL 示例：
export DQ_DB_TYPE="postgresql"
export DQ_DB_HOST="your-db-host.example.com"
export DQ_DB_PORT="5432"
export DQ_DB_NAME="your_database"
export DQ_DB_USER="readonly_user"
export DQ_DB_PASSWORD="your_secure_password"

Oracle 示例：
export DQ_DB_TYPE="oracle"
export DQ_DB_HOST="oracle.example.com"
export DQ_DB_PORT="1521"
export DQ_DB_NAME="ORCL"
export DQ_DB_USER="readonly"
export DQ_DB_PASSWORD="your_password"

SQLite 示例：
export DQ_DB_TYPE="sqlite"
export DQ_DB_NAME="/path/to/your/database.db"

注意：SQLite 不需要 host/port/user/password。

#### 2.5 重启 OpenClaw

方式1：重启网关
openclaw gateway restart

方式2：在对话中使用 /new 命令重新加载会话

### 验证安装

在 OpenClaw 对话中输入：
"列出已安装的技能"

应看到 data-quality-checker 出现在列表中。

## 3. 如何使用

### 基本使用流程

您只需要用自然语言描述检查需求，AI 会：
1. 提取规则并整理成表格
2. 请求您确认
3. 执行检查
4. 输出可读性强的报告

### 第一步：描述规则

您需要提供三要素：
- 数据库连接（如果环境变量已配好，可省略）
- 要检查的表名
- 每条规则的约束条件

### 第二步：AI 整理规则并请求确认

AI 会将解析后的规则以表格形式反馈给您。

### 第三步：用户确认

回复"确认"，AI 立即执行检查。脚本将自动检查并安装缺失的数据库驱动。

### 第四步：查看报告

AI 生成 Markdown 格式的质量报告。

## 4. 输入输出样例

### 样例1：基本检查（MySQL）

用户输入：
检查 users 表：email 不能为空，email 必须唯一。

AI 确认表格：
📋 即将执行的检查规则（共 2 条）：

| 序号 | 规则类型 | 表名 | 列名 | 参数/条件 |
|------|----------|------|------|------------|
| 1 | not_null | users | email | 允许空值：0 |
| 2 | unique | users | email | - |

请确认以上规则是否正确？回复"确认"开始检查。

用户确认后，AI 输出报告：

# 数据质量检查报告

**报告时间**: 2026-05-07 10:30:00
**数据库**: localhost / testdb
**检查表**: users

## 检查摘要

| 指标 | 数值 |
|------|------|
| 规则总数 | 2 |
| 通过 | 1 |
| 失败 | 1 |
| 执行错误 | 0 |
| 通过率 | 50.0% |

## 通过的规则

- users_email_not_null: 空值检查通过，空值数量 0 ≤ 阈值 0

## 失败的规则

### users_email_unique (表: users, 列: email)

- 失败原因: 存在 3 条重复记录
- 重复数: 3
- 错误率: 0.03%
- 错误样例:

| email | cnt |
|-------|-----|
| test@example.com | 2 |
| info@example.com | 2 |

## 修复建议

- users_email_unique: 为 email 列添加唯一约束，清洗重复数据：保留一条，删除其余。

### 样例2：带性能参数（PostgreSQL）

用户输入：
检查 orders 表：amount 不能为负数，order_date 必须是 2025年之后。表超过 500 万行随机抽样 50 万行，用 8 线程。

AI 确认表格：
📋 即将执行的检查规则（共 2 条）：

| 序号 | 规则类型 | 表名 | 列名 | 参数/条件 |
|------|----------|------|------|------------|
| 1 | range | orders | amount | min=0, include_min=True |
| 2 | range | orders | order_date | min=2025-01-01, include_min=True |

性能配置：超过 5,000,000 行抽样 500,000 行（随机），并发线程 8。

请确认后回复"确认"。

输出报告（含抽样警告）：

# 数据质量检查报告

**报告时间**: 2026-05-07 10:35:00
**数据库**: pg.example.com / sales
**检查表**: orders

## 检查摘要

| 指标 | 数值 |
|------|------|
| 规则总数 | 2 |
| 通过 | 1 |
| 失败 | 1 |
| 通过率 | 50.0% |
| 存在抽样规则 | 是 |

## 详细的规则结果

### 规则1: orders_amount_non_negative (range)

- 状态: PASS
- 表: orders, 列: amount
- 条件: amount >= 0
- 执行方式: 全表扫描（表行数 8,200,000，未超过阈值 5,000,000）
- 错误数量: 0

### 规则2: orders_order_date_after_2025 (range)

- 状态: FAIL
- 表: orders, 列: order_date
- 条件: order_date >= '2025-01-01'
- 基于抽样数据: 表行数 8,200,000 > 5,000,000，随机抽样 500,000 行。结果可能存在误差。
- 错误数量: 12（抽样中）
- 估计总体错误数: ~197
- 错误样例 (抽样中的5条):

| order_date |
|------------|
| 2024-12-31 |
| 2024-11-15 |
| 2024-10-20 |

## 修复建议

- 对于 order_date < 2025-01-01 的记录，请联系业务确认是否数据录入错误或历史数据迁移问题。

### 样例3：Oracle 数据库检查

用户输入：
连接到 Oracle 数据库（主机 oracle.example.com，端口 1521，SID ORCL），检查 employees 表：salary 必须大于 0，email 必须唯一，department_id 必须在 departments 表中存在。

AI 确认表格：
📋 即将执行的检查规则（共 3 条）：

| 序号 | 规则类型 | 表名 | 列名 | 参数/条件 |
|------|----------|------|------|------------|
| 1 | range | employees | salary | min=0, include_min=False |
| 2 | unique | employees | email | - |
| 3 | foreign_key | employees | department_id | 参照 departments.id |

数据库类型：Oracle（自动适配语法）
注意：唯一性和外键检查将进行全表扫描（保证准确性）。

请确认后回复"确认"。

### 样例4：自定义 SQL 规则

用户输入：
检查 orders 表：每个用户的最近订单金额是否大于该用户历史平均订单金额的 2 倍。

AI 响应：
我理解您需要一个复杂的业务规则检查。我将把它转换为自定义 SQL 规则，SQL 如下：

SELECT COUNT(*) FROM orders o1
JOIN (
    SELECT user_id, AVG(amount) as avg_amount
    FROM orders
    GROUP BY user_id
) o2 ON o1.user_id = o2.user_id
WHERE o1.order_date = (
    SELECT MAX(order_date) FROM orders WHERE user_id = o1.user_id
)
AND o1.amount > o2.avg_amount * 2

期望结果：value == 0（没有这样的异常订单）

请确认是否执行此自定义 SQL？

## 5. 高级用法

### 自定义 SQL 规则

如果内置规则无法满足需求，您可以直接用自然语言描述复杂逻辑，AI 会生成相应的 SQL 并请求您确认后再执行。

### 规则依赖串行执行

如果有规则A的结果需要被规则B使用，可以要求串行模式：
"先检查订单表是否有空值，然后再检查那些非空订单的金额是否异常。用串行执行。"

AI 会自动设置 execution_mode: "sequential" 并处理依赖。

### 导出错误明细

在对话要求："加上导出错误数据到 CSV"
AI 会调用脚本的 --export-errors 参数，生成 dq_errors.csv 文件并提供下载链接。

## 6. 常见问题

Q: 可以同时检查多张表吗？
A: 可以。只需在规则中分别指定表名，或使用 tables 参数过滤。

Q: 检查结果可以保存下来分享给其他人吗？
A: 可以。AI 输出的 Markdown 报告可以复制保存，或使用 OpenClaw 的文件功能导出。

Q: 唯一性检查为什么不会抽样？
A: 因为对表抽样后，可能会漏掉实际存在的重复值，导致误报"无重复"。为了准确性，唯一性始终全量检查。如果性能不允许，可以在对话中要求"强制抽样唯一性"，但会收到警告。

Q: 数据库密码不想写在环境变量里怎么办？
A: 您可以在对话中直接提供密码，AI 会临时使用，不会记录。例如："密码是 mypass123"。

Q: 如何修改默认性能参数？
A: 每次检查时在对话中说明即可，例如"抽样阈值改成 500 万，样本 20 万，线程 2"。

Q: Oracle 连接失败，提示 "DPI-1047" 或缺少客户端怎么办？
A: 本技能使用 oracledb 的纯 Python 模式，不需要 Oracle 客户端。如果遇到问题，请升级 oracledb 到最新版：pip3 install --upgrade oracledb

Q: 技能运行时提示缺少 pandas 或 sqlalchemy 怎么办？
A: 技能会自动尝试安装，若失败，请手动运行：pip3 install pandas sqlalchemy

Q: 大表抽样在 Oracle 中效果如何？
A: 使用 ORDER BY DBMS_RANDOM.VALUE FETCH FIRST n ROWS ONLY，性能取决于排序。对于超大表，建议设置较小的 sample_size（如 10 万行）。

## 7. 技术支持与反馈

如果您遇到以下问题：
- 技能未被触发
- 规则识别错误
- 数据库连接失败

请提供：
- 您使用的完整对话片段
- 数据库类型和版本
- 表的大致行数

我们将持续优化本技能。