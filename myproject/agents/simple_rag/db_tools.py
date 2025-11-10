"""
Ferramenta de consulta SQL ao banco de dados para o agente RAG.
Esta função é exposta como "tool" para o Gemini via Function Calling.
"""

import json
import re
from decimal import Decimal
from datetime import date, datetime
from django.db import connection

def _serialize_result(obj):
    """
    Serializa o resultado para formato JSON-friendly.

    Args:
        obj: Objeto a serializar

    Returns:
        Objeto serializado
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _serialize_result(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_serialize_result(item) for item in obj]
    else:
        return obj

def _validate_sql_query(query: str) -> tuple[bool, str]:
    """
    Valida se a query SQL é apenas uma consulta SELECT.

    Args:
        query: Query SQL a ser validada

    Returns:
        Tupla (is_valid, error_message)
    """
    if not query or not query.strip():
        return False, "Query vazia"

    # Remove comentários SQL
    query_clean = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    query_clean = re.sub(r'/\*.*?\*/', '', query_clean, flags=re.DOTALL)
    query_clean = query_clean.strip().upper()

    # Verifica se começa com SELECT
    if not query_clean.startswith('SELECT'):
        return False, "Apenas consultas SELECT são permitidas"

    # Lista de comandos proibidos
    forbidden_commands = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
        'TRUNCATE', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE',
        'CALL', 'MERGE', 'REPLACE', 'RENAME'
    ]

    # Verifica se contém comandos proibidos
    for cmd in forbidden_commands:
        # Usa word boundary para evitar falsos positivos (ex: "SELECTED" não deve dar match)
        if re.search(rf'\b{cmd}\b', query_clean):
            return False, f"Comando {cmd} não é permitido"

    # Verifica múltiplos statements (tentativa de SQL injection)
    if ';' in query_clean and not query_clean.endswith(';'):
        return False, "Múltiplos comandos SQL não são permitidos"

    return True, ""

def executar_consulta_sql(query: str) -> str:
    """
    Executa uma consulta SQL SELECT no banco de dados e retorna os resultados.

    IMPORTANTE: Esta função só aceita queries SELECT. Qualquer tentativa de
    modificar dados (INSERT, UPDATE, DELETE) será bloqueada.

    Args:
        query: Consulta SQL SELECT a ser executada

    Returns:
        JSON com os resultados da consulta ou mensagem de erro

    """
    try:
        # Valida a query
        is_valid, error_msg = _validate_sql_query(query)
        if not is_valid:
            return json.dumps({
                "success": False,
                "error": f"Query inválida: {error_msg}"
            }, ensure_ascii=False)

        # Executa a query
        with connection.cursor() as cursor:
            cursor.execute(query)

            # Obtém os nomes das colunas
            columns = [col[0] for col in cursor.description]

            # Busca os resultados
            rows = cursor.fetchall()

            # Converte para lista de dicionários
            results = [
                dict(zip(columns, row))
                for row in rows
            ]

        # Serializa os resultados
        results = _serialize_result(results)

        return json.dumps({
            "success": True,
            "count": len(results),
            "columns": columns,
            "data": results
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False)
