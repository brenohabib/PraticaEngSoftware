from .account_transaction import AccountTransaction
from .person import Person
from .classification import Classification
from .installment import Installment
from ..services import get_embedding  
from pgvector.django import L2Distance # Operador de distância de vetor do pgvector
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import os

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

def query_semantic_rag(question: str, top_k: int = 5) -> str:
    """
    Executa busca semântica (RAG) com contexto RICO e gera resposta usando Gemini.
    
    Args:
        question: Pergunta do usuário
        top_k: Número de transações similares a retornar (padrão: 5)
    
    Returns:
        Resposta gerada pelo LLM com base no contexto encontrado
    
    Exemplos de perguntas que FUNCIONAM com contexto rico:
    - "Quanto gastei com a IGUACU MAQUINAS?"
    - "Quais notas fiscais são de manutenção?"
    - "Mostre transações acima de R$ 3000"
    - "Quais fornecedores tenho cadastrados?"
    - "Qual o total de despesas com INSUMOS AGRÍCOLAS?"
    """
    
    print(f"\n Buscando por: '{question}'")
    
    # Gera embedding da pergunta do usuário
    query_vector = get_embedding(question)
    
    if query_vector is None:
        return "Não foi possível processar sua pergunta. Tente reformular."
    
    # Busca de transações semelhantes usando o embedding da descrição
    similar_transactions = AccountTransaction.objects.filter(
        descricao_embedding__isnull=False
    ).order_by(
        L2Distance('descricao_embedding', query_vector)
    ).prefetch_related(
        'fornecedor_cliente',
        'faturado', 
        'classificacoes',
        'parcelas'
    )[:top_k]
    
    if not similar_transactions:
        return "Não encontrei nenhuma transação no banco de dados que corresponda à sua pergunta."
    
    print(f"Encontradas {len(similar_transactions)} transações relevantes\n")
    
    # Monstagem de contexto
    context = "DADOS ENCONTRADOS NO BANCO DE DADOS:\n\n"    
    for idx, tx in enumerate(similar_transactions, 1):
        classificacoes = ", ".join([c.descricao for c in tx.classificacoes.all()])
        parcelas = tx.parcelas.all()
        total_parcelas = parcelas.count()
        parcelas_abertas = parcelas.filter(status_parcela='aberta').count()
        
        context += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRANSAÇÃO #{idx} - ID: {tx.id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nota Fiscal: {tx.numero_nota_fiscal}
Data de Emissão: {tx.data_emissao.strftime('%d/%m/%Y')}
Valor Total: R$ {tx.valor_total:.2f}
Fornecedor: {tx.fornecedor_cliente.razao_social}
Faturado: {tx.faturado.razao_social}
Descrição: {tx.descricao}
Classificações: {classificacoes or 'Não especificado'}
Parcelas: {total_parcelas} total ({parcelas_abertas} abertas)
Status: {tx.get_status_display()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
    
    # Geração de resposta com LLM
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0.1,
        google_api_key=GEMINI_API_KEY)
    
    prompt_template = """
Você é um assistente financeiro especializado em análise de notas fiscais e despesas.

INSTRUÇÕES IMPORTANTES:
1. Responda APENAS com base no contexto fornecido abaixo
2. Se a informação não estiver no contexto, diga claramente "Não encontrei essa informação nos dados disponíveis"
3. Quando falar sobre valores, sempre use formatação brasileira (R$ 1.234,56)
4. Seja claro, objetivo e organizado
5. Se houver múltiplas transações, organize a resposta de forma estruturada
6. Quando relevante, mostre totais e resumos
7. Não analise dados com status='inativo'

CONTEXTO (Dados do Banco de Dados):
{context}

PERGUNTA DO USUÁRIO:
{question}

RESPOSTA:
"""
    
    prompt = ChatPromptTemplate.from_template(prompt_template)
    
    rag_chain = (
        prompt
        | llm
        | StrOutputParser()
    )
    
    try:
        answer = rag_chain.invoke({
            "context": context,
            "question": question
        })
        
        print(f"Resposta gerada com sucesso!\n")
        return answer
        
    except Exception as e:
        print(f"Erro ao gerar resposta: {e}")
        return f"Erro ao processar sua pergunta: {str(e)}"
