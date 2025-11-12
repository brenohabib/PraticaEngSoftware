"""
EmbeddingAgent - Agente para geração de embeddings usando Google Gemini.
"""

import os
from typing import Optional, List
from langchain_google_genai import GoogleGenerativeAIEmbeddings

class EmbeddingAgent:
    """
    Agente simplificado para geração de embeddings.
    Não herda de BaseAgent pois usa API diferente (embeddings ao invés de chat).
    """

    def __init__(self):
        """Inicializa o agente de embeddings."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY não configurada")

        self.embeddings_model = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=api_key
        )

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Gera embedding para um texto.

        Args:
            text (str): Texto para gerar embedding

        Returns:
            Optional[List[float]]: Vetor de embedding ou None se falhar
        """
        if not text or text.strip() == '' or text.strip() == 'Sem descrição':
            print("Texto vazio ou 'Sem descrição', pulando embedding.")
            return None

        try:
            embedding = self.embeddings_model.embed_query(text)
            return embedding
        except Exception as e:
            print(f"Erro ao gerar embedding: {e}")
            return None

    def build_rich_context(
        self,
        data: dict,
        provider_name: str,
        invoiced_name: str,
        classifications: List[str]
    ) -> str:
        """
        Constrói contexto rico para embedding de transação financeira.

        Args:
            data (dict): Dados da transação extraídos do PDF
            provider_name (str): Nome do fornecedor
            invoiced_name (str): Nome do faturado
            classifications (List[str]): Lista de classificações

        Returns:
            str: Texto rico formatado
        """
        numero_nf = data.get('numero_nota_fiscal', 'S/N')
        valor_total = data.get('valor_total', 0)
        data_emissao = data.get('data_emissao', 'não informada')
        produtos = data.get('descricao_produtos', [])
        qtd_parcelas = data.get('quantidade_parcelas', 1)
        data_vencimento = data.get('data_vencimento', 'não informada')

        rich_text = f"""
Nota Fiscal: {numero_nf}
Fornecedor: {provider_name}
Cliente/Faturado: {invoiced_name}
Data de Emissão: {data_emissao}
Valor Total: R$ {valor_total}
Quantidade de Parcelas: {qtd_parcelas}
Data de Vencimento: {data_vencimento}

Produtos/Serviços:
{' | '.join(produtos) if produtos else 'Não especificado'}

Classificações/Categorias de Despesa:
{', '.join(classifications) if classifications else 'Não especificado'}

Tipo de Transação: A Pagar
Status: Ativo
""".strip()

        return rich_text

    def generate_transaction_embedding(
        self,
        data: dict,
        provider_name: str,
        invoiced_name: str,
        classifications: List[str]
    ) -> Optional[List[float]]:
        """
        Gera embedding completo para uma transação financeira.

        Args:
            data (dict): Dados da transação
            provider_name (str): Nome do fornecedor
            invoiced_name (str): Nome do faturado
            classifications (List[str]): Lista de classificações

        Returns:
            Optional[List[float]]: Vetor de embedding ou None
        """
        rich_context = self.build_rich_context(
            data=data,
            provider_name=provider_name,
            invoiced_name=invoiced_name,
            classifications=classifications
        )

        print(f"Contexto a ser indexado:\n{rich_context}")

        return self.generate_embedding(rich_context)

    def process(self, text: str) -> Optional[List[float]]:
        """
        Método de compatibilidade com padrão de agentes.
        Alias para generate_embedding().
        """
        return self.generate_embedding(text)
