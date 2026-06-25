# SQL数据库字典生成器

这是一个从SQL建表脚本自动生成Excel数据库表字典的工具。

## 快速开始

### 1. 安装依赖

```bash
pip install xlsxwriter
```

### 2. 使用工具

```bash
# 基本用法
python generate_dict.py database.sql

# 指定输出文件
python generate_dict.py database.sql my_dict.xlsx
```

### 3. 查看输出

打开生成的Excel文件，你将看到：

- **数据库表清单**：所有表的汇总，点击"查看"跳转到详情
- **每张表的详情**：包含表名、注释、字段列表、返回按钮

## 功能特点

- ✅ 自动解析表结构（表名、字段、类型）
- ✅ 提取表注释和字段注释
- ✅ 支持中文表名和字段名
- ✅ 每张表独立一个Sheet
- ✅ 汇总表与详情表超链接跳转
- ✅ 自动分类（Mapping、dim、ods、t_*等）
- ✅ 精美的Excel样式

## 支持的数据库

- PostgreSQL
- MySQL

## 示例

### 输入SQL

```sql
CREATE TABLE public.user (
    id serial4 NOT NULL,
    name varchar(50) NULL,
    email varchar(100) NULL
);

COMMENT ON TABLE public.user IS '用户表';
COMMENT ON COLUMN public.user.id IS '用户ID';
```

### 执行命令

```bash
python generate_dict.py user.sql
```

### 输出Excel

- Sheet1: 数据库表清单
- Sheet2: user（包含超链接跳转）

## 故障排除

### 问题：显示乱码

确保SQL文件使用UTF-8编码保存。

### 问题：超链接无法点击

使用Excel 2007及以上版本打开。

### 问题：部分表未解析

检查SQL语句格式是否完整。

## 详细文档

完整使用说明请查看 [SKILL.md](SKILL.md)

## 作者

小虾人
