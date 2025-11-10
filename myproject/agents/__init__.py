"""
Módulo de agentes de IA para processamento de documentos e RAG.

Este módulo contém agentes baseados em Google Gemini para:
- Extração de dados de PDFs (invoices/notas fiscais)
- Consultas RAG (Retrieval-Augmented Generation)
- Consultas ao banco de dados via LLM
"""

from .agent import BaseAgent
from .extraction.invoice_extractor import PDFExtractorAgent
from .simple_rag.rag import SimpleRAGAgent

__all__ = ['BaseAgent', 'PDFExtractorAgent', 'SimpleRAGAgent']
