---
name: DDL_TO_excel_dict
description: 上传数据库导出的ddl建表语句自动生成excel字典
metadata:
    skill-author: CHENGAOJIE
---


## 触发场景

以下情况必须触发此技能：
- 根据sql生成数据数据字典

# SQL Database Dictionary Generator Skill

生成数据库表字典Excel文档的技能。

## 功能

从SQL建表脚本中提取表结构信息，生成格式化的Excel数据库表字典文档，支持：
- 自动解析表名、字段名、字段类型
- 提取表注释和字段注释
- 每张表独立一个Sheet
- 汇总表与详情表之间的超链接跳转
- 按表名前缀分类（Mapping、dim、ods、t_*等）

## 使用方法

### 基本用法

```bash
# 生成数据库表字典
python generate_dict.py <SQL文件路径> [输出文件路径]
```

**示例：**
```bash
# 使用默认输出路径
python generate_dict.py D:\Desktop\database.sql

# 指定输出路径
python generate_dict.py D:\Desktop\database.sql D:\output\dict.xlsx
```

### 参数说明

- **SQL文件路径**（必需）：PostgreSQL/MySQL建表SQL脚本文件
- **输出文件路径**（可选）：生成的Excel文件路径，默认为当前目录下的 `database_dict.xlsx`

### 支持的SQL格式

支持PostgreSQL和MySQL的建表语句格式：

**PostgreSQL格式：**
```sql
CREATE TABLE public.table_name (
    id serial4 NOT NULL,
    name varchar(255) NULL,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL
);

COMMENT ON TABLE public.table_name IS '表注释';
COMMENT ON COLUMN public.table_name.id IS '字段注释';
```

**MySQL格式：**
```sql
CREATE TABLE table_name (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**混合格式（带引号）：**
```sql
CREATE TABLE public."Mapping_商品名与性质" (
    组别 varchar(510) NULL,
    药品通用名 varchar(510) NULL
);
```

## 输出格式

### Excel文件结构

生成的Excel文件包含以下内容：

1. **数据库表清单**（首页Sheet）
   - 序号
   - 表名
   - 中文名/注释
   - 字段数
   - 详情（超链接，点击跳转到对应表）

2. **每张表的详情Sheet**
   - 表名（标题行）
   - 表注释（如果有）
   - 字段列表（序号、字段名、数据类型、注释/说明、备注）
   - 返回汇总表（底部超链接按钮）

### 样式说明

- 表头：蓝色背景、白色文字、居中
- 表名：浅蓝色背景、加粗
- 表注释：浅灰色背景、斜体
- 超链接：蓝色文字、下划线
- 汇总统计：黄色背景、加粗

## 依赖安装

### Python版本

Python 3.6 或更高版本

### 安装依赖

```bash
pip install xlsxwriter
```

或者使用requirements.txt：

```bash
pip install -r requirements.txt
```

## 工作原理

### 解析流程

1. **读取SQL文件**：使用正则表达式提取CREATE TABLE语句
2. **解析表定义**：
   - 识别表名（支持带引号和不带引号的格式）
   - 分割字段定义（考虑括号嵌套）
   - 提取字段名、字段类型
3. **提取注释**：
   - 表注释（COMMENT ON TABLE）
   - 字段注释（COMMENT ON COLUMN）
4. **生成Excel**：
   - 创建汇总表
   - 为每张表创建详情Sheet
   - 设置超链接（汇总表→详情表，详情表→汇总表）
   - 应用样式

### 表名分类

自动按表名前缀分类：
- `Mapping_*` → Mapping映射表
- `dim_*` → 维度表
- `ods_*` → ODS数据层
- `t_*` → 临时表
- 其他 → 其他表

## 使用场景

1. **数据库文档化**：自动生成数据库设计文档
2. **数据迁移参考**：了解源数据库结构
3. **API开发辅助**：快速查询字段类型和含义
4. **团队协作**：分享数据库结构给团队成员
5. **数据字典维护**：定期更新数据库文档

## 注意事项

### SQL文件要求

- 文件必须使用UTF-8编码
- 支持中文表名和字段名
- 建议使用完整的建表语句（包含字段类型和约束）
- COMMENT语句可选，但强烈建议添加

### 限制

- 仅支持PostgreSQL和MySQL的建表语句
- 不支持复杂的视图、存储过程等对象
- Sheet名称限制31个字符（Excel限制），超出部分会截断
- Excel中的特殊字符会被替换为下划线

### 性能

- 支持100+张表的解析
- 大型SQL文件（10MB+）处理时间约5-10秒
- 生成的Excel文件大小取决于表数量和字段数量

## 故障排除

### 常见问题

**Q: 生成的Excel中显示乱码**
A: 确保SQL文件使用UTF-8编码，重新保存文件。

**Q: 超链接无法点击**
A: 确保Excel版本支持内部超链接（Excel 2007及以上）。

**Q: 部分表没有被解析**
A: 检查SQL语句格式，确保CREATE TABLE语句完整。

**Q: 字段注释没有显示**
A: 确保COMMENT ON COLUMN语句的格式正确，表名和字段名匹配。

## 示例

### 完整示例

**输入SQL文件（database.sql）：**
```sql
-- 用户表
CREATE TABLE public.dim_user (
    user_id serial4 NOT NULL,
    username varchar(50) NULL,
    email varchar(100) NULL,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL
);

COMMENT ON TABLE public.dim_user IS '用户维度表';
COMMENT ON COLUMN public.dim_user.user_id IS '用户ID';
COMMENT ON COLUMN public.dim_user.username IS '用户名';
COMMENT ON COLUMN public.dim_user.email IS '邮箱';
COMMENT ON COLUMN public.dim_user.created_at IS '创建时间';

-- 订单表
CREATE TABLE public.fact_order (
    order_id serial4 NOT NULL,
    user_id int4 NULL,
    order_amount numeric(18, 2) NULL,
    order_date date NULL,
    status varchar(20) NULL
);

COMMENT ON TABLE public.fact_order IS '订单事实表';
```

**执行命令：**
```bash
python generate_dict.py database.sql database_dict.xlsx
```

**输出：**
- 生成包含2个Sheet的Excel文件
- Sheet1: 数据库表清单（汇总）
- Sheet2: dim_user（用户表详情）
- Sheet3: fact_order（订单表详情）
- 支持超链接跳转

## 版本历史

### v1.0.0 (2026-03-23)

- 初始版本
- 支持PostgreSQL/MySQL建表语句解析
- 支持表注释和字段注释提取
- 生成Excel文档，带超链接跳转
- 按表名前缀自动分类

## 作者

由小虾人生成，基于实际项目需求开发。

## 许可

MIT License
