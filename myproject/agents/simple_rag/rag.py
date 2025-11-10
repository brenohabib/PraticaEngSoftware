import json
from ..agent import BaseAgent
from google import genai
from .db_tools import executar_consulta_sql

class SimpleRAGAgent(BaseAgent):
    def __init__(self, model_name='gemini-2.5-flash-lite'):
        super().__init__(model_name)

        self.system_instruction = """
Você é um assistente financeiro especializado em responder perguntas sobre notas fiscais,
transações financeiras, fornecedores, classificações de despesas e parcelas.

### Suas capacidades:
Você tem acesso direto ao banco de dados via SQL e pode executar consultas SELECT para
responder perguntas sobre dados financeiros.

### Schema do Banco de Dados:

**Tabela: core_person**
Armazena informações de pessoas/empresas (fornecedores e faturados)
- id: INTEGER (chave primária)
- documento: VARCHAR (CPF/CNPJ normalizado, único)
- tipo: VARCHAR ('fornecedor' ou 'faturado')
- razao_social: VARCHAR (razão social da empresa)
- fantasia: VARCHAR (nome fantasia, opcional)
- status: VARCHAR ('ativo' ou 'inativo')
- created_at: TIMESTAMP
- updated_at: TIMESTAMP

**Tabela: core_accounttransaction**
Armazena transações financeiras (notas fiscais)
- id: INTEGER (chave primária)
- numero_nota_fiscal: VARCHAR (número único da nota)
- tipo: VARCHAR ('a pagar' ou 'a receber')
- data_emissao: DATE
- descricao: TEXT
- valor_total: DECIMAL
- fornecedor_cliente_id: INTEGER (FK -> core_person.id)
- faturado_id: INTEGER (FK -> core_person.id)
- status: VARCHAR ('ativo' ou 'inativo')
- created_at: TIMESTAMP
- updated_at: TIMESTAMP

**Tabela: core_installment**
Armazena parcelas das transações
- id: INTEGER (chave primária)
- account_transaction_id: INTEGER (FK -> core_accounttransaction.id)
- identificacao: VARCHAR (formato "1/3", "2/3", etc.)
- data_vencimento: DATE
- valor_parcela: DECIMAL
- valor_pago: DECIMAL
- valor_saldo: DECIMAL
- status_parcela: VARCHAR ('aberta', 'paga', 'vencida', etc.)
- created_at: TIMESTAMP
- updated_at: TIMESTAMP

**Tabela: core_classification**
Armazena classificações de despesas/receitas
- id: INTEGER (chave primária)
- tipo: VARCHAR ('despesa' ou 'receita')
- descricao: VARCHAR (ex: "INSUMOS AGRÍCOLAS", "MANUTENÇÃO E OPERAÇÃO")
- status: VARCHAR ('ativo' ou 'inativo')
- created_at: TIMESTAMP
- updated_at: TIMESTAMP

**Relacionamento N:N entre AccountTransaction e Classification:**
- Tabela: core_accounttransaction_classificacoes
- accounttransaction_id: INTEGER (FK)
- classification_id: INTEGER (FK)

### Como usar a ferramenta SQL:
Você tem acesso à função `executar_consulta_sql(query)` que aceita queries SQL SELECT.

**IMPORTANTE:**
- Use SEMPRE filtros `WHERE status = 'ativo'` nas tabelas que têm esse campo
- Limite resultados com LIMIT para evitar retornar muitos dados
- Use JOINs para relacionar tabelas quando necessário
- Para acessar classificações, faça JOIN com a tabela n:n `core_accounttransaction_classificacoes`
- Evite responder uma pergunta com outra pergunta
- Responda considerando que haverá sinônimos como nf, transação, faturado e outras abreviações

**Aqui está alguns exemplos de queries úteis:**

1. Listar transações por faixa de valor:
```sql
SELECT numero_nota_fiscal, tipo, data_emissao, valor_total, descricao
FROM core_accounttransaction
WHERE status = 'ativo' AND valor_total BETWEEN 1000 AND 5000
LIMIT 20
```

2. Buscar transações de um fornecedor:
```sql
SELECT at.numero_nota_fiscal, at.tipo, at.data_emissao, at.valor_total, p.razao_social
FROM core_accounttransaction at
JOIN core_person p ON at.fornecedor_cliente_id = p.id
WHERE p.razao_social ILIKE '%nome_fornecedor%' AND at.status = 'ativo'
LIMIT 20
```

3. Obter totais por classificação:
```sql
SELECT c.descricao, c.tipo, COUNT(at.id) as quantidade, SUM(at.valor_total) as total
FROM core_classification c
JOIN core_accounttransaction_classificacoes atc ON c.id = atc.classification_id
JOIN core_accounttransaction at ON atc.accounttransaction_id = at.id
WHERE c.status = 'ativo' AND at.status = 'ativo'
GROUP BY c.id, c.descricao, c.tipo
```

4. Buscar parcelas em aberto:
```sql
SELECT i.identificacao, i.data_vencimento, i.valor_parcela, i.valor_saldo,
       at.numero_nota_fiscal, p.razao_social
FROM core_installment i
JOIN core_accounttransaction at ON i.account_transaction_id = at.id
JOIN core_person p ON at.fornecedor_cliente_id = p.id
WHERE i.status_parcela IN ('aberta', 'vencida') AND at.status = 'ativo'
LIMIT 30
```

5. Buscar transação específica com detalhes:
```sql
SELECT at.*,
       fc.razao_social as fornecedor, fc.documento as fornecedor_doc,
       fat.razao_social as faturado, fat.documento as faturado_doc
FROM core_accounttransaction at
JOIN core_person fc ON at.fornecedor_cliente_id = fc.id
JOIN core_person fat ON at.faturado_id = fat.id
WHERE at.numero_nota_fiscal = '12345' AND at.status = 'ativo'
```

### Instruções de formatação:
- Seja direto e objetivo nas respostas
- Formate valores monetários em reais (R$)
- Formate datas no padrão brasileiro (DD/MM/AAAA)
- Se não houver dados, informe claramente ao usuário
- Cite números de notas fiscais e nomes de fornecedores quando relevante
- Sempre construa queries SQL otimizadas e seguras
"""
        # Registra a ferramenta SQL para Function Calling
        self.tools = [executar_consulta_sql]

    def query(self, question, context="", max_retries=3, retry_delay=2):
        """
        Pipeline completo com Function Calling: recebe pergunta -> decide usar tool -> gera resposta.

        Args:
            question (str): Pergunta a ser respondida
            context (str): Contexto adicional opcional (para manter compatibilidade)
            max_retries (int): Número máximo de tentativas em caso de falha
            retry_delay (int): Tempo de espera entre tentativas em segundos

        Returns:
            dict: Resposta do modelo com informações sobre tools usadas
        """
        # Validação inicial
        if not question or not question.strip():
            self.logger.error("Pergunta vazia fornecida")
            return {
                "error": "Pergunta não pode estar vazia",
                "response": None,
                "tools_used": []
            }

        def query_operation():
            tools_used = []

            # Prepara o conteúdo inicial
            initial_contents = [{"role": "user", "parts": [{"text": question.strip()}]}]

            # Se houver contexto adicional, adiciona no prompt
            if context and context.strip():
                initial_contents[0]["parts"].insert(0, {
                    "text": f"Contexto adicional fornecido:\n{context}\n\n"
                })

            # 1. Primeira chamada à API com as ferramentas registradas
            self.logger.info("Enviando pergunta ao modelo com Function Calling habilitado...")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=initial_contents,
                config=genai.types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    tools=self.tools
                )
            )

            # 2. Verifica se o modelo solicitou chamadas de função
            if hasattr(response, 'function_calls') and response.function_calls:
                self.logger.info(f"Modelo solicitou {len(response.function_calls)} chamada(s) de função")

                # Executa todas as chamadas de função solicitadas
                tool_outputs = []
                for call in response.function_calls:
                    function_name = call.name
                    args = dict(call.args)

                    self.logger.info(f"Executando função: {function_name} com args: {args}")
                    tools_used.append({"function": function_name, "args": args})

                    # Executa a função SQL
                    result = None
                    if function_name == "executar_consulta_sql":
                        result = executar_consulta_sql(**args)
                    else:
                        self.logger.warning(f"Função desconhecida: {function_name}")
                        result = json.dumps({
                            "success": False,
                            "error": f"Função {function_name} não está disponível"
                        })

                    # Prepara o resultado da função para enviar de volta ao modelo
                    if result:
                        tool_outputs.append(
                            genai.types.Part.from_function_response(
                                name=function_name,
                                response={"content": result}
                            )
                        )

                # 3. Segunda chamada à API com os resultados das funções
                self.logger.info("Enviando resultados das funções ao modelo para resposta final...")
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[
                        *initial_contents,
                        {"role": "model", "parts": [genai.types.Part.from_function_call(call) for call in response.function_calls]},
                        {"role": "user", "parts": tool_outputs}
                    ],
                    config=genai.types.GenerateContentConfig(
                        system_instruction=self.system_instruction,
                        tools=self.tools
                    )
                )

            # 4. Extrai a resposta final
            if not response or not response.text:
                raise ValueError("Resposta vazia da API")

            response_text = response.text.strip()
            self.logger.info(f"Resposta final gerada: {response_text[:100]}...")

            return {
                "response": response_text,
                "context_used": bool(context.strip()),
                "tools_used": tools_used,
                "db_query_performed": len(tools_used) > 0,
                "error": None
            }

        # Executa a operação com retry
        return self._retry_with_backoff(
            operation=query_operation,
            max_retries=max_retries,
            retry_delay=retry_delay,
            operation_name="consulta RAG com Function Calling"
        )

    def process(self, question, context="", max_retries=3, retry_delay=2):
        """
        Implementação do método abstrato process().
        Alias para query() mantendo compatibilidade.

        Args:
            question (str): Pergunta a ser respondida
            context (str): Contexto ou documentos para embasar a resposta (opcional)
            max_retries (int): Número máximo de tentativas em caso de falha
            retry_delay (int): Tempo de espera entre tentativas em segundos

        Returns:
            dict: Resposta do modelo ou mensagem de erro
        """
        return self.query(question, context, max_retries, retry_delay)
