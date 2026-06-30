#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import xlsxwriter

def parse_sql_file(sql_file):
    """解析SQL文件，提取表结构"""
    with open(sql_file, 'r', encoding='utf-8') as f:
        content = f.read()

    quoted_pattern = r'CREATE TABLE\s+(?:public\.)?"([^"]+)"\s*\(([^;]+)\)\s*;'
    quoted_matches = re.findall(quoted_pattern, content, re.DOTALL)

    unquoted_pattern = r'CREATE TABLE\s+(?:public\.)?(\w+)\s*\(([^;]+)\)\s*;'
    unquoted_matches = re.findall(unquoted_pattern, content, re.DOTALL)

    all_matches = quoted_matches + unquoted_matches

    tables = {}

    for match in all_matches:
        table_name = match[0]
        columns_def = match[1]

        columns = []

        parts = []
        depth = 0
        current = ""
        for char in columns_def:
            if char == '(':
                depth += 1
                current += char
            elif char == ')':
                depth -= 1
                current += char
            elif char == ',' and depth == 0:
                parts.append(current.strip())
                current = ""
            else:
                current += char
        if current.strip():
            parts.append(current.strip())

        for part in parts:
            part = part.strip()
            if not part or part.startswith('CONSTRAINT') or part.startswith('PRIMARY'):
                continue

            col_match = re.match(r'^([^\s,]+)\s+(.+?)(?:\s+NULL|\s+NOT NULL|\s+DEFAULT|\s+PRIMARY\s+KEY|\s*$)', part, re.IGNORECASE)
            if col_match:
                col_name = col_match.group(1).replace('"', '').replace("'", '')
                col_type = col_match.group(2).strip()
                col_type = re.sub(r'\s+(NOT\s+NULL|NULL|DEFAULT\s+[^,\s]+|PRIMARY\s+KEY)', '', col_type, flags=re.IGNORECASE)
                col_type = col_type.strip()

                if col_name and col_type:
                    columns.append({
                        'name': col_name,
                        'type': col_type,
                        'comment': '',
                        'description': ''
                    })

        if table_name not in tables:
            tables[table_name] = {
                'columns': columns,
                'comment': ''
            }

    table_comment_pattern = r'COMMENT ON TABLE\s+(?:public\.)?"?([^"\s]+)"?\s+IS\s+[\'"]([^\'\"]+)[\'\"]'
    table_comment_matches = re.finditer(table_comment_pattern, content, re.IGNORECASE)
    for match in table_comment_matches:
        table_name = match.group(1)
        comment = match.group(2)
        if table_name in tables:
            tables[table_name]['comment'] = comment
        else:
            tables[table_name] = {
                'columns': [],
                'comment': comment
            }

    column_comment_pattern = r'COMMENT ON COLUMN\s+(?:public\.)?([^\s]+)\s+IS\s+[\'"]([^\'\"]+)[\'\"]'
    column_comment_matches = re.finditer(column_comment_pattern, content, re.IGNORECASE)
    for match in column_comment_matches:
        full_name = match.group(1)
        comment = match.group(2)

        parts = full_name.split('.')
        if len(parts) == 2:
            table_name = parts[0].replace('"', '').replace("'", '')
            column_name = parts[1].replace('"', '').replace("'", '')

            if table_name in tables:
                for col in tables[table_name]['columns']:
                    if col['name'] == column_name:
                        col['comment'] = comment
                        break

    return tables

def clean_sheet_name(name):
    """清理sheet名称，去除非法字符"""
    invalid_chars = ['\\', '/', '*', '?', ':', '[', ']']
    cleaned = name
    for char in invalid_chars:
        cleaned = cleaned.replace(char, '_')
    return cleaned[:31]

def create_excel_dict_with_links(tables, output_file):
    """使用xlsxwriter创建Excel字典，每张表一个sheet，带超链接"""
    workbook = xlsxwriter.Workbook(output_file)

    # 定义格式
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'font_name': '微软雅黑',
        'font_size': 11,
        'align': 'center',
        'valign': 'vcenter',
        'border': 1
    })

    title_format = workbook.add_format({
        'bold': True,
        'bg_color': '#D9E2F3',
        'font_name': '微软雅黑',
        'font_size': 12,
        'align': 'left',
        'valign': 'vcenter',
        'border': 1
    })

    comment_format = workbook.add_format({
        'italic': True,
        'bg_color': '#F2F2F2',
        'font_name': '微软雅黑',
        'font_size': 10,
        'align': 'left',
        'valign': 'vcenter',
        'text_wrap': True,
        'border': 1
    })

    cell_format = workbook.add_format({
        'align': 'center',
        'valign': 'vcenter',
        'text_wrap': True,
        'border': 1
    })

    link_format = workbook.add_format({
        'font_color': 'blue',
        'underline': 1,
        'align': 'center',
        'valign': 'vcenter',
        'border': 1
    })

    summary_format = workbook.add_format({
        'bold': True,
        'bg_color': '#FFF2CC',
        'font_name': '微软雅黑',
        'font_size': 10,
        'align': 'center',
        'valign': 'vcenter',
        'border': 1
    })

    # 创建汇总Sheet
    summary_sheet_name = '数据库表清单'
    summary_sheet = workbook.add_worksheet(summary_sheet_name)

    # 设置列宽
    summary_sheet.set_column('A:A', 6)
    summary_sheet.set_column('B:B', 45)
    summary_sheet.set_column('C:C', 35)
    summary_sheet.set_column('D:D', 10)
    summary_sheet.set_column('E:E', 10)

    # 写入表头
    summary_sheet.write_row(0, 0, ['序号', '表名', '中文名/注释', '字段数', '详情'], header_format)

    table_sheet_map = {}
    row = 1

    for table_name in sorted(tables.keys()):
        table_info = tables[table_name]

        # 清理sheet名称
        sheet_name = clean_sheet_name(table_name)
        table_sheet_map[table_name] = sheet_name

        # 创建表详情Sheet
        sheet = workbook.add_worksheet(sheet_name)

        # 设置列宽
        sheet.set_column('A:A', 6)
        sheet.set_column('B:B', 35)
        sheet.set_column('C:C', 20)
        sheet.set_column('D:D', 40)
        sheet.set_column('E:E', 20)

        # 写入表头
        sheet.write_row(0, 0, ['序号', '字段名', '数据类型', '注释/说明', '备注'], header_format)

        # 插入表名行
        sheet.merge_range(1, 0, 1, 4, f"表名: {table_name}", title_format)

        # 插入表注释行
        detail_row = 2
        if table_info['comment']:
            sheet.merge_range(detail_row, 0, detail_row, 4, f"注释: {table_info['comment']}", comment_format)
            detail_row += 1

        # 插入字段列表
        for col_idx, column in enumerate(table_info['columns'], 1):
            sheet.write_row(detail_row, 0, [col_idx, column['name'], column['type'], column['comment'], ''], cell_format)
            detail_row += 1

        # 在详情表最后添加"返回汇总"按钮
        detail_row += 1
        sheet.merge_range(detail_row, 0, detail_row, 4, "返回汇总表", link_format)
        # 添加超链接
        sheet.write_url(detail_row, 0, f"internal:'{summary_sheet_name}'!A1", link_format, string="返回汇总表")

        # 在汇总表中添加行和超链接
        summary_sheet.write_row(row, 0, [row, table_name, table_info['comment'], len(table_info['columns']), '查看'], cell_format)
        # 添加超链接到"查看"列
        summary_sheet.write_url(row, 4, f"internal:'{sheet_name}'!A1", link_format, string="查看")

        row += 1

    # 在汇总表最后一行添加统计
    summary_sheet.merge_range(row, 0, row, 4, f'共 {len(tables)} 张表', summary_format)

    workbook.close()
    print(f"Excel字典已生成: {output_file}")
    print(f"共解析 {len(tables)} 张表")

if __name__ == '__main__':
    import sys
    import os

    # 解析命令行参数
    if len(sys.argv) < 2:
        print("用法: python generate_dict.py <SQL文件路径> [输出文件路径]")
        print("示例: python generate_dict.py database.sql")
        print("      python generate_dict.py database.sql output_dict.xlsx")
        sys.exit(1)

    sql_file = sys.argv[1]

    # 检查SQL文件是否存在
    if not os.path.exists(sql_file):
        print(f"错误: SQL文件不存在: {sql_file}")
        sys.exit(1)

    # 设置输出文件路径
    if len(sys.argv) >= 3:
        output_file = sys.argv[2]
    else:
        # 默认输出路径
        sql_dir = os.path.dirname(sql_file)
        output_file = os.path.join(sql_dir, 'database_dict.xlsx')

    print("开始解析SQL文件...")
    print(f"输入文件: {sql_file}")
    print(f"输出文件: {output_file}")

    try:
        tables = parse_sql_file(sql_file)
        print(f"解析完成，共找到 {len(tables)} 张表")

        print("\n开始生成Excel文件...")
        create_excel_dict_with_links(tables, output_file)
        print("生成完成!")
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
