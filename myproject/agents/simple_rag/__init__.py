"""
Módulo RAG (Retrieval-Augmented Generation) com Function Calling integrado.
Permite consultas ao banco de dados de forma autônoma via LLM.
"""

from .rag import SimpleRAGAgent
from .db_tools import (
    executar_consulta_sql
)

__all__ = [
    'SimpleRAGAgent',
    'executar_consulta_sql'
]
