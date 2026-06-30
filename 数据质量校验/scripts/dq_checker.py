#!/usr/bin/env python3
"""
高性能数据质量检查脚本 - 全自动版本
支持：多线程、大表自动抽样、唯一性/外键不抽样、跨数据库方言（含Oracle）、规则依赖串行执行、按需依赖检查、Schema分析自动生成规则
输出包含完整规则说明
"""
 
import json
import sys
import os
import re
import subprocess
import importlib
import argparse
from datetime import datetime, date
from functools import lru_cache
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus
 
# 全局配置：数据库驱动映射
DB_DRIVERS = {
    'mysql': 'pymysql',
    'postgresql': 'psycopg2',
    'oracle': 'oracledb',
    'sqlite': None
}
 
def install_and_import(package_name, import_name=None):
    """尝试导入包，如果失败则自动安装，然后再次导入"""
    if import_name is None:
        import_name = package_name
    try:
        return importlib.import_module(import_name)
    except ImportError:
        print(f"正在安装缺失的依赖包: {package_name}...", file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        return importlib.import_module(import_name)
 
def get_sqlalchemy_dialect(db_type):
    """根据数据库类型返回 SQLAlchemy 连接字符串前缀和所需的驱动"""
    if db_type == 'mysql':
        install_and_import('pymysql')
        return 'mysql+pymysql'
    elif db_type == 'postgresql':
        install_and_import('psycopg2', 'psycopg2')
        return 'postgresql'
    elif db_type == 'oracle':
        install_and_import('oracledb')
        return 'oracle+oracledb'
    elif db_type == 'sqlite':
        return 'sqlite'
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
 
class Dialect:
    """数据库方言适配器（支持 MySQL, PostgreSQL, SQLite, Oracle）"""
    def __init__(self, db_type: str):
        self.db_type = db_type
 
    def regex_not_match(self, column: str, pattern: str) -> str:
        if self.db_type == 'mysql':
            return f"{column} NOT REGEXP '{pattern}'"
        elif self.db_type == 'postgresql':
            return f"{column} !~ '{pattern}'"
        elif self.db_type == 'oracle':
            return f"NOT REGEXP_LIKE({column}, '{pattern}')"
        else:
            raise NotImplementedError(f"Database {self.db_type} does not support REGEXP; use custom_sql")
 
    def random_order(self) -> str:
        if self.db_type == 'mysql':
            return "RAND()"
        elif self.db_type == 'postgresql':
            return "RANDOM()"
        elif self.db_type == 'oracle':
            return "DBMS_RANDOM.VALUE"
        else:
            return "RANDOM()"
 
    def sample_clause(self, limit: int) -> str:
        if self.db_type == 'oracle':
            return f"ORDER BY {self.random_order()} FETCH FIRST {limit} ROWS ONLY"
        else:
            return f"ORDER BY {self.random_order()} LIMIT {limit}"
 
    def limit_clause(self, limit: int) -> str:
        if self.db_type == 'oracle':
            return f"AND ROWNUM <= {limit}"
        else:
            return f"LIMIT {limit}"
 
    def fetch_sample_query(self, table: str, limit: int) -> str:
        if self.db_type == 'oracle':
            return f"(SELECT * FROM {table} ORDER BY {self.random_order()} FETCH FIRST {limit} ROWS ONLY) sampled"
        else:
            return f"(SELECT * FROM {table} ORDER BY {self.random_order()} LIMIT {limit}) sampled"
 
    def limit_suffix(self, sql: str, limit: int) -> str:
        """为 SQL 添加 LIMIT 子句（兼容 Oracle）"""
        if self.db_type == 'oracle':
            return f"SELECT * FROM ({sql}) WHERE ROWNUM <= {limit}"
        else:
            return f"{sql} LIMIT {limit}"
 
 
class HighPerfDataQualityChecker:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.db_engine = None
        self.dialect = None
        self.performance = config.get('performance', {})
        self.max_rows_per_table = self.performance.get('max_rows_per_table', 10_000_000)
        self.sample_size = self.performance.get('sample_size', 1_000_000)
        self.sample_method = self.performance.get('sample_method', 'random')
        self.max_workers = self.performance.get('max_workers', 4)
        self.execution_mode = config.get('execution_mode', 'parallel')
        self.force_sample_for_unique = self.performance.get('force_sample_for_unique', False)
        self.results = []
        self.rules_description = []  # 存储规则说明
 
    def _connect_db(self):
        db_cfg = self.config.get('database', {})
        db_type = db_cfg.get('type', 'mysql').lower()
        self.dialect = Dialect(db_type)
 
        dialect_prefix = get_sqlalchemy_dialect(db_type)
 
        password = db_cfg.get('password', '')
        if password.startswith('${') and password.endswith('}'):
            env_var = password[2:-1]
            password = os.environ.get(env_var, '')
        # URL encode password to handle special characters like @, #, etc.
        password = quote_plus(password)
 
        if db_type == 'mysql':
            conn_str = f"{dialect_prefix}://{db_cfg['user']}:{password}@{db_cfg['host']}:{db_cfg.get('port', 3306)}/{db_cfg['database']}"
        elif db_type == 'postgresql':
            conn_str = f"{dialect_prefix}://{db_cfg['user']}:{password}@{db_cfg['host']}:{db_cfg.get('port', 5432)}/{db_cfg['database']}"
        elif db_type == 'oracle':
            host = db_cfg['host']
            port = db_cfg.get('port', 1521)
            db_name = db_cfg['database']
            dsn = f"{host}:{port}/{db_name}"
            conn_str = f"{dialect_prefix}://{db_cfg['user']}:{password}@{dsn}"
        elif db_type == 'sqlite':
            conn_str = f"{dialect_prefix}:///{db_cfg['database']}"
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
 
        import sqlalchemy as sa
        self.db_engine = sa.create_engine(conn_str, pool_size=self.max_workers + 2, max_overflow=10)
 
    @lru_cache(maxsize=128)
    def _get_table_row_count(self, table: str) -> int:
        import sqlalchemy as sa
        with self.db_engine.connect() as conn:
            try:
                result = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}"))
                return result.scalar()
            except Exception:
                return 0
 
    def _maybe_sample_table(self, table: str, original_sql: str, rule_type: str) -> Tuple[str, bool, Optional[str]]:
        no_sample_default = ['unique', 'foreign_key']
        if rule_type in no_sample_default and not self.force_sample_for_unique:
            row_count = self._get_table_row_count(table)
            if row_count > self.max_rows_per_table and self.max_rows_per_table > 0:
                warning = f"表 {table} 行数 {row_count} 超过阈值 {self.max_rows_per_table}，但规则类型 '{rule_type}' 要求准确性，进行全量检查，可能耗时较长。"
                return original_sql, False, warning
            return original_sql, False, None
 
        if self.max_rows_per_table <= 0:
            return original_sql, False, None
 
        row_count = self._get_table_row_count(table)
        if row_count <= self.max_rows_per_table:
            return original_sql, False, None
 
        if self.sample_method == 'random':
            sample_subquery = self.dialect.fetch_sample_query(table, self.sample_size)
        else:
            if self.dialect.db_type == 'oracle':
                sample_subquery = f"(SELECT * FROM {table} FETCH FIRST {self.sample_size} ROWS ONLY) sampled"
            else:
                sample_subquery = f"(SELECT * FROM {table} LIMIT {self.sample_size}) sampled"
 
        new_sql = re.sub(rf'\b{table}\b', sample_subquery, original_sql, flags=re.IGNORECASE)
        warning = f"表 {table} 数据量 {row_count} > {self.max_rows_per_table}，已随机抽样 {self.sample_size} 行。结果可能存在误差。"
        return new_sql, True, warning
 
    def _generate_rule_description(self, rule: Dict) -> Dict:
        """生成规则说明"""
        rule_type = rule.get('rule_type', 'unknown')
        table = rule.get('table', '-')
        column = rule.get('column', '-')
        
        description_map = {
            'not_null': f"检查 {table}.{column} 是否为空",
            'unique': f"检查 {table}.{column} 是否唯一",
            'value_in': f"检查 {table}.{column} 值是否在允许列表中: {rule.get('allowed_values', [])}",
            'range': f"检查 {table}.{column} 值范围: {rule.get('min', '-∞')} ~ {rule.get('max', '+∞')}",
            'length': f"检查 {table}.{column} 长度: 最小{rule.get('min_len', 0)}, 最大{rule.get('max_len', '∞')}",
            'regex': f"检查 {table}.{column} 是否符合正则: {rule.get('pattern', '')}",
            'foreign_key': f"检查 {table}.{column} 外键引用 {rule.get('ref_table')}.{rule.get('ref_column')} 是否存在",
            'custom_sql': f"自定义SQL检查: {rule.get('sql', '')[:50]}..."
        }
        
        return {
            'name': rule.get('name', description_map.get(rule_type, f"未知规则类型: {rule_type}")),
            'rule_type': rule_type,
            'table': table,
            'column': column,
            'description': description_map.get(rule_type, f"未知规则类型: {rule_type}"),
            'parameters': {k: v for k, v in rule.items() if k not in ['name', 'rule_type', 'table', 'column']}
        }
 
    def _execute_not_null(self, rule: Dict, conn) -> Dict:
        import pandas as pd
        table = rule['table']
        col = rule['column']
        threshold = rule.get('threshold', 0)
 
        sql = f"SELECT COUNT(*) as total, SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) as null_cnt FROM {table}"
        sql, sampled, warn = self._maybe_sample_table(table, sql, 'not_null')
        df = pd.read_sql(sql, conn)
        total = df.iloc[0]['total']
        null_cnt = df.iloc[0]['null_cnt']
        passed = null_cnt <= threshold
 
        result = {
            'name': rule.get('name', f'not_null_{table}_{col}'),
            'rule_type': 'not_null',
            'table': table,
            'column': col,
            'status': 'PASS' if passed else 'FAIL',
            'message': f"空值数量: {null_cnt}, 阈值: {threshold}",
            'error_count': null_cnt,
            'total_rows': total,
            'error_rate': null_cnt / total if total > 0 else 0,
            'sampled': sampled,
            'sample_warning': warn,
            'sample_errors': []
        }
        if not passed and null_cnt > 0:
            sample_sql = f"SELECT * FROM {table} WHERE {col} IS NULL"
            if self.dialect.db_type == 'oracle':
                sample_sql = f"{sample_sql} AND ROWNUM <= 5"
            else:
                sample_sql = f"{sample_sql} LIMIT 5"
            result['sample_errors'] = pd.read_sql(sample_sql, conn).to_dict(orient='records')
        return result
 
    def _execute_unique(self, rule: Dict, conn) -> Dict:
        import pandas as pd
        table = rule['table']
        col = rule['column']
 
        sql = f"SELECT COUNT(*) as total, COUNT(DISTINCT {col}) as distinct_cnt FROM {table}"
        sql, sampled, warn = self._maybe_sample_table(table, sql, 'unique')
        df = pd.read_sql(sql, conn)
        total = df.iloc[0]['total']
        distinct = df.iloc[0]['distinct_cnt']
        dup_cnt = total - distinct
        passed = dup_cnt == 0
 
        result = {
            'name': rule.get('name', f'unique_{table}_{col}'),
            'rule_type': 'unique',
            'table': table,
            'column': col,
            'status': 'PASS' if passed else 'FAIL',
            'message': f"重复记录数: {dup_cnt}",
            'error_count': dup_cnt,
            'total_rows': total,
            'error_rate': dup_cnt / total if total > 0 else 0,
            'sampled': sampled,
            'sample_warning': warn,
            'sample_errors': []
        }
        if not passed and dup_cnt > 0:
            dup_sql = f"SELECT {col}, COUNT(*) as cnt FROM {table} GROUP BY {col} HAVING COUNT(*) > 1"
            if self.dialect.db_type == 'oracle':
                dup_sql = f"SELECT * FROM ({dup_sql}) WHERE ROWNUM <= 5"
            else:
                dup_sql = f"{dup_sql} LIMIT 5"
            result['sample_errors'] = pd.read_sql(dup_sql, conn).to_dict(orient='records')
        return result
 
    def _execute_value_in(self, rule: Dict, conn) -> Dict:
        import pandas as pd
        table = rule['table']
        col = rule['column']
        allowed = rule.get('allowed_values', [])
        if not allowed:
            raise ValueError("value_in requires allowed_values")
        placeholders = ','.join([f"'{v}'" for v in allowed])
        sql = f"SELECT COUNT(*) as total, SUM(CASE WHEN {col} NOT IN ({placeholders}) THEN 1 ELSE 0 END) as invalid_cnt FROM {table}"
        sql, sampled, warn = self._maybe_sample_table(table, sql, 'value_in')
        df = pd.read_sql(sql, conn)
        total = df.iloc[0]['total']
        invalid_cnt = df.iloc[0]['invalid_cnt']
        passed = invalid_cnt == 0
 
        result = {
            'name': rule.get('name', f'value_in_{table}_{col}'),
            'rule_type': 'value_in',
            'table': table,
            'column': col,
            'status': 'PASS' if passed else 'FAIL',
            'message': f"不在允许值的记录数: {invalid_cnt}",
            'error_count': invalid_cnt,
            'total_rows': total,
            'error_rate': invalid_cnt / total if total > 0 else 0,
            'sampled': sampled,
            'sample_warning': warn,
            'sample_errors': []
        }
        if not passed and invalid_cnt > 0:
            sample_sql = f"SELECT {col} FROM {table} WHERE {col} NOT IN ({placeholders})"
            if self.dialect.db_type == 'oracle':
                sample_sql = f"{sample_sql} AND ROWNUM <= 5"
            else:
                sample_sql = f"{sample_sql} LIMIT 5"
            result['sample_errors'] = pd.read_sql(sample_sql, conn)[col].tolist()
        return result
 
    def _execute_range(self, rule: Dict, conn) -> Dict:
        import pandas as pd
        table = rule['table']
        col = rule['column']
        min_val = rule.get('min')
        max_val = rule.get('max')
        include_min = rule.get('include_min', True)
        include_max = rule.get('include_max', True)
 
        if min_val is None and max_val is None:
            raise ValueError("range rule requires min or max")
        if isinstance(min_val, str) and min_val.lower() == 'today':
            min_val = date.today().isoformat()
        if isinstance(max_val, str) and max_val.lower() == 'today':
            max_val = date.today().isoformat()
 
        conditions = []
        if min_val is not None:
            op = '>=' if include_min else '>'
            conditions.append(f"{col} {op} {min_val}")
        if max_val is not None:
            op = '<=' if include_max else '<'
            conditions.append(f"{col} {op} {max_val}")
        where_clause = ' AND '.join(conditions)
        sql = f"SELECT COUNT(*) as total, SUM(CASE WHEN NOT ({where_clause}) THEN 1 ELSE 0 END) as out_of_range_cnt FROM {table}"
        sql, sampled, warn = self._maybe_sample_table(table, sql, 'range')
        df = pd.read_sql(sql, conn)
        total = df.iloc[0]['total']
        invalid_cnt = df.iloc[0]['out_of_range_cnt']
        passed = invalid_cnt == 0
 
        result = {
            'name': rule.get('name', f'range_{table}_{col}'),
            'rule_type': 'range',
            'table': table,
            'column': col,
            'status': 'PASS' if passed else 'FAIL',
            'message': f"超出范围记录数: {invalid_cnt}",
            'error_count': invalid_cnt,
            'total_rows': total,
            'error_rate': invalid_cnt / total if total > 0 else 0,
            'sampled': sampled,
            'sample_warning': warn,
            'sample_errors': []
        }
        if not passed and invalid_cnt > 0:
            sample_sql = f"SELECT {col} FROM {table} WHERE NOT ({where_clause})"
            if self.dialect.db_type == 'oracle':
                sample_sql = f"{sample_sql} AND ROWNUM <= 5"
            else:
                sample_sql = f"{sample_sql} LIMIT 5"
            result['sample_errors'] = pd.read_sql(sample_sql, conn)[col].tolist()
        return result
 
    def _execute_length(self, rule: Dict, conn) -> Dict:
        import pandas as pd
        table = rule['table']
        col = rule['column']
        min_len = rule.get('min_len')
        max_len = rule.get('max_len')
        if min_len is None and max_len is None:
            raise ValueError("length rule requires min_len or max_len")
 
        conditions = []
        if min_len is not None:
            conditions.append(f"LENGTH({col}) >= {min_len}")
        if max_len is not None:
            conditions.append(f"LENGTH({col}) <= {max_len}")
        where_clause = ' AND '.join(conditions)
        sql = f"SELECT COUNT(*) as total, SUM(CASE WHEN NOT ({where_clause}) THEN 1 ELSE 0 END) as invalid_len_cnt FROM {table}"
        sql, sampled, warn = self._maybe_sample_table(table, sql, 'length')
        df = pd.read_sql(sql, conn)
        total = df.iloc[0]['total']
        invalid_cnt = df.iloc[0]['invalid_len_cnt']
        passed = invalid_cnt == 0
 
        result = {
            'name': rule.get('name', f'length_{table}_{col}'),
            'rule_type': 'length',
            'table': table,
            'column': col,
            'status': 'PASS' if passed else 'FAIL',
            'message': f"长度不符记录数: {invalid_cnt}",
            'error_count': invalid_cnt,
            'total_rows': total,
            'error_rate': invalid_cnt / total if total > 0 else 0,
            'sampled': sampled,
            'sample_warning': warn,
            'sample_errors': []
        }
        if not passed and invalid_cnt > 0:
            sample_sql = f"SELECT {col} FROM {table} WHERE NOT ({where_clause})"
            if self.dialect.db_type == 'oracle':
                sample_sql = f"{sample_sql} AND ROWNUM <= 5"
            else:
                sample_sql = f"{sample_sql} LIMIT 5"
            result['sample_errors'] = pd.read_sql(sample_sql, conn)[col].tolist()
        return result
 
    def _execute_regex(self, rule: Dict, conn) -> Dict:
        import pandas as pd
        table = rule['table']
        col = rule['column']
        pattern = rule['pattern']
        try:
            regex_condition = self.dialect.regex_not_match(col, pattern)
        except NotImplementedError:
            return self._execute_custom_sql({
                'name': rule.get('name', f'regex_{table}_{col}'),
                'sql': f"SELECT COUNT(*) FROM {table} WHERE 1=0",
                'expectation': 'value == 0'
            }, conn)
        sql = f"SELECT COUNT(*) as invalid_cnt FROM {table} WHERE {regex_condition}"
        sql, sampled, warn = self._maybe_sample_table(table, sql, 'regex')
        df = pd.read_sql(sql, conn)
        invalid_cnt = df.iloc[0]['invalid_cnt']
        passed = invalid_cnt == 0
 
        result = {
            'name': rule.get('name', f'regex_{table}_{col}'),
            'rule_type': 'regex',
            'table': table,
            'column': col,
            'status': 'PASS' if passed else 'FAIL',
            'message': f"不匹配正则的记录数: {invalid_cnt}",
            'error_count': invalid_cnt,
            'total_rows': None,
            'error_rate': None,
            'sampled': sampled,
            'sample_warning': warn,
            'sample_errors': []
        }
        if not passed and invalid_cnt > 0:
            sample_sql = f"SELECT {col} FROM {table} WHERE {regex_condition}"
            if self.dialect.db_type == 'oracle':
                sample_sql = f"{sample_sql} AND ROWNUM <= 5"
            else:
                sample_sql = f"{sample_sql} LIMIT 5"
            result['sample_errors'] = pd.read_sql(sample_sql, conn)[col].tolist()
        return result
 
    def _execute_foreign_key(self, rule: Dict, conn) -> Dict:
        import pandas as pd
        table = rule['table']
        col = rule['column']
        ref_table = rule['ref_table']
        ref_col = rule['ref_column']
        sql = f"""
            SELECT COUNT(*) as orphan_cnt
            FROM {table} t
            LEFT JOIN {ref_table} r ON t.{col} = r.{ref_col}
            WHERE t.{col} IS NOT NULL AND r.{ref_col} IS NULL
        """
        df = pd.read_sql(sql, conn)
        orphan_cnt = df.iloc[0]['orphan_cnt']
        passed = orphan_cnt == 0
 
        result = {
            'name': rule.get('name', f'fk_{table}_{col}_to_{ref_table}_{ref_col}'),
            'rule_type': 'foreign_key',
            'table': table,
            'column': col,
            'status': 'PASS' if passed else 'FAIL',
            'message': f"孤儿记录数（引用不存在）: {orphan_cnt}",
            'error_count': orphan_cnt,
            'total_rows': None,
            'error_rate': None,
            'sampled': False,
            'sample_warning': None,
            'sample_errors': []
        }
        if not passed and orphan_cnt > 0:
            sample_sql = f"""
                SELECT t.{col} FROM {table} t
                LEFT JOIN {ref_table} r ON t.{col} = r.{ref_col}
                WHERE t.{col} IS NOT NULL AND r.{ref_col} IS NULL
            """
            if self.dialect.db_type == 'oracle':
                sample_sql = f"SELECT * FROM ({sample_sql}) WHERE ROWNUM <= 5"
            else:
                sample_sql = f"{sample_sql} LIMIT 5"
            result['sample_errors'] = pd.read_sql(sample_sql, conn)[col].tolist()
        return result
 
    def _execute_custom_sql(self, rule: Dict, conn) -> Dict:
        import pandas as pd
        import sqlalchemy as sa
        sql = rule['sql']
        expectation = rule.get('expectation', 'value == 0')
        sql_lower = sql.lower()
        dangerous_keywords = ['insert', 'update', 'delete', 'drop', 'create', 'alter', 'truncate']
        if any(kw in sql_lower for kw in dangerous_keywords):
            raise ValueError("Custom SQL contains dangerous write operation, aborted.")
        # 使用 sa.text() 包装 SQL，防止 pymysql 的 % 格式化问题
        df = pd.read_sql(sa.text(sql), conn)
        value = df.iloc[0, 0] if not df.empty else None
        # 1. 预处理：将自然语言描述映射为 Python 表达式
        expectation_map = {"Empty set": "value is None", "空集": "value is None", "结果为空": "value is None"}
        actual_expectation = expectation_map.get(expectation, expectation) if isinstance(expectation, str) else expectation
 
        # 2. 扩展上下文：增加 count 变量（结果集行数），支持 "count == 0" 这种写法
        safe_dict = {'value': value, 'count': len(df)}
        
        try:
            # 3. 执行判定
            passed = eval(actual_expectation, {"__builtins__": {}}, safe_dict) if isinstance(actual_expectation, str) else False
        except Exception as e:
            # 4. 捕获语法错误，防止脚本崩溃
            return {
                'name': rule.get('name', 'custom_sql'),
                'rule_type': 'custom_sql',
                'table': rule.get('table'),
                'column': rule.get('column'),
                'status': 'ERROR',
                'message': f"预期条件 '{expectation}' 语法错误: {str(e)}。请使用 'value is None' 或 'count == 0'。",
                'error_count': 0,
                'sampled': False,
                'sample_warning': None,
                'sample_errors': []
            }
        
        # 提取错误明细：如果结果集不符合预期，则结果集中的每一行都被视为错误记录
        sample_errors = []
        if not passed:
            limit = 50
            for i in range(min(len(df), limit)):
                sample_errors.append(df.iloc[i].to_dict())
 
        return {
            'name': rule.get('name', 'custom_sql'),
            'rule_type': 'custom_sql',
            'table': rule.get('table'),
            'column': rule.get('column'),
            'status': 'PASS' if passed else 'FAIL',
            'message': f"查询结果数: {len(df)}, 期望: {expectation}",
            'error_count': len(df) if not passed else 0,
            'sampled': False,
            'sample_warning': None,
            'sample_errors': sample_errors
        }
 
    def _execute_single_rule(self, rule: Dict) -> Dict:
        with self.db_engine.connect() as conn:
            rule_type = rule.get('rule_type')
            method_map = {
                'not_null': self._execute_not_null,
                'unique': self._execute_unique,
                'value_in': self._execute_value_in,
                'range': self._execute_range,
                'length': self._execute_length,
                'regex': self._execute_regex,
                'foreign_key': self._execute_foreign_key,
                'custom_sql': self._execute_custom_sql
            }
            if rule_type not in method_map:
                return {
                    'name': rule.get('name', 'unknown'),
                    'rule_type': rule_type,
                    'status': 'ERROR',
                    'message': f'Unsupported rule type: {rule_type}',
                }
            try:
                return method_map[rule_type](rule, conn)
            except Exception as e:
                return {
                    'name': rule.get('name', rule_type),
                    'rule_type': rule_type,
                    'status': 'ERROR',
                    'message': str(e),
                }
 
    def _run_parallel(self, rules: List[Dict]) -> List[Dict]:
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_rule = {executor.submit(self._execute_single_rule, rule): rule for rule in rules}
            for future in as_completed(future_to_rule):
                results.append(future.result())
        return results
 
    def _run_sequential(self, rules: List[Dict]) -> List[Dict]:
        rule_map = {r['name']: r for r in rules if 'name' in r}
        dependencies = {r['name']: r.get('depends_on', []) for r in rules if 'name' in r}
        executed = set()
        results = []
        while len(executed) < len(rules):
            progress = False
            for name, deps in dependencies.items():
                if name not in executed and all(d in executed for d in deps):
                    res = self._execute_single_rule(rule_map[name])
                    results.append(res)
                    executed.add(name)
                    progress = True
            if not progress:
                for rule in rules:
                    if rule.get('name') not in executed:
                        res = self._execute_single_rule(rule)
                        results.append(res)
                        executed.add(rule.get('name'))
                break
        return results
 
    def run(self) -> List[Dict]:
        if not self.db_engine:
            self._connect_db()
        rules = self.config.get('rules', [])
        if not rules:
            raise ValueError("No rules specified. Please define at least one rule.")
 
        # 生成规则说明
        self.rules_description = [self._generate_rule_description(rule) for rule in rules]
 
        if self.execution_mode == 'parallel':
            self.results = self._run_parallel(rules)
        else:
            self.results = self._run_sequential(rules)
        return self.results
 
    def summary(self) -> Dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r['status'] == 'PASS')
        failed = sum(1 for r in self.results if r['status'] == 'FAIL')
        errors = sum(1 for r in self.results if r['status'] == 'ERROR')
        sampled_count = sum(1 for r in self.results if r.get('sampled', False))
        return {
            'total_rules': total,
            'passed': passed,
            'failed': failed,
            'errors': errors,
            'pass_rate': passed / total * 100 if total else 0,
            'rules_with_sampling': sampled_count,
            'generated_at': datetime.now().isoformat()
        }
 
 
def analyze_schema(config: Dict[str, Any]) -> Dict[str, Any]:
    """分析数据库 schema，自动生成候选规则"""
    import sqlalchemy as sa
    from sqlalchemy import inspect
 
    # 复用连接逻辑
    checker = HighPerfDataQualityChecker(config)
    checker._connect_db()
    engine = checker.db_engine
    inspector = sa.inspect(engine)
    db_cfg = config.get('database', {})
    schema = db_cfg.get('schema', None)
    tables = config.get('tables', inspector.get_table_names(schema=schema))
    candidate_rules = []
 
    for table in tables:
        # 主键
        pk_columns = []
        try:
            pk_constraint = inspector.get_pk_constraint(table, schema=schema)
            pk_columns = pk_constraint.get('constrained_columns', [])
        except:
            pass
        # 外键映射
        foreign_keys = inspector.get_foreign_keys(table, schema=schema)
        fk_map = {}
        for fk in foreign_keys:
            if fk['constrained_columns']:
                col = fk['constrained_columns'][0]
                fk_map[col] = (fk['referred_table'], fk['referred_columns'][0])
        # 列信息
        columns = inspector.get_columns(table, schema=schema)
        for col in columns:
            col_name = col['name']
            col_type = str(col['type'])
            nullable = col.get('nullable', True)
            max_len = None
            if 'VARCHAR' in col_type or 'CHAR' in col_type:
                match = re.search(r'\((\d+)\)', col_type)
                if match:
                    max_len = int(match.group(1))
            # 主键：唯一+非空
            if col_name in pk_columns:
                candidate_rules.append({
                    'name': f"pk_unique_{table}_{col_name}",
                    'table': table,
                    'column': col_name,
                    'rule_type': 'unique',
                    'generated_by': 'schema_analysis',
                    'reason': f'列 {col_name} 是主键'
                })
                candidate_rules.append({
                    'name': f"pk_not_null_{table}_{col_name}",
                    'table': table,
                    'column': col_name,
                    'rule_type': 'not_null',
                    'threshold': 0,
                    'generated_by': 'schema_analysis',
                    'reason': f'列 {col_name} 是主键'
                })
            elif not nullable:
                candidate_rules.append({
                    'name': f"not_null_{table}_{col_name}",
                    'table': table,
                    'column': col_name,
                    'rule_type': 'not_null',
                    'threshold': 0,
                    'generated_by': 'schema_analysis',
                    'reason': f'数据库定义 NOT NULL'
                })
            # 外键
            if col_name in fk_map:
                ref_table, ref_col = fk_map[col_name]
                candidate_rules.append({
                    'name': f"fk_{table}_{col_name}_to_{ref_table}_{ref_col}",
                    'table': table,
                    'column': col_name,
                    'rule_type': 'foreign_key',
                    'ref_table': ref_table,
                    'ref_column': ref_col,
                    'generated_by': 'schema_analysis',
                    'reason': f'外键引用 {ref_table}.{ref_col}'
                })
            # 长度建议
            if max_len:
                candidate_rules.append({
                    'name': f"length_{table}_{col_name}",
                    'table': table,
                    'column': col_name,
                    'rule_type': 'length',
                    'max_len': max_len,
                    'generated_by': 'schema_analysis',
                    'reason': f'列类型 {col_type}，建议长度 ≤ {max_len}'
                })
    # 去重
    seen = set()
    unique_rules = []
    for rule in candidate_rules:
        if rule['name'] not in seen:
            seen.add(rule['name'])
            unique_rules.append(rule)
    return {'candidate_rules': unique_rules, 'analyzed_tables': tables}
 
 
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, help='JSON config string')
    parser.add_argument('--export-errors', action='store_true', help='Export error samples to CSV')
    parser.add_argument('--analyze', action='store_true', help='Analyze schema and generate candidate rules')
    args = parser.parse_args()
 
    try:
        # 确保 pandas / sqlalchemy 已安装
        try:
            import pandas
            import sqlalchemy
        except ImportError:
            print("正在安装必需依赖包: pandas, sqlalchemy...", file=sys.stderr)
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas", "sqlalchemy"])
            import pandas
            import sqlalchemy
 
        config = json.loads(args.config)
 
        if args.analyze:
            result = analyze_schema(config)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0)
 
        # 正常执行检查
        checker = HighPerfDataQualityChecker(config)
        results = checker.run()
        
        def json_serial(obj):
            """JSON serializer for objects not serializable by default json code"""
            import numpy as np
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            if isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
 
        output = {
            'summary': checker.summary(),
            'rules_description': checker.rules_description,  # 新增：规则说明
            'results': results
        }
        
        if args.export_errors:
            import pandas as pd
            error_records = []
            for r in results:
                if r['status'] == 'FAIL' and r.get('sample_errors'):
                    for err in r['sample_errors']:
                        error_records.append({
                            'rule': r['name'],
                            'table': r.get('table'),
                            'column': r.get('column'),
                            'error_value': str(err)
                        })
            if error_records:
                df_err = pd.DataFrame(error_records)
                df_err.to_csv('dq_errors.csv', index=False)
                print(json.dumps({'warning': 'Error samples exported to dq_errors.csv'}, ensure_ascii=False))
        
        print(json.dumps(output, ensure_ascii=False, indent=2, default=json_serial))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        sys.exit(1)
 
 
if __name__ == '__main__':
    main()