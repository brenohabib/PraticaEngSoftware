"""
SimpleRAGAgent - Agente de consulta com Function Calling para SQL.
Implementado seguindo a documentação oficial do Google Gen AI SDK.
Suporta chat com histórico de contexto.
"""

import json
from ..agent import BaseAgent
from ..chat_manager import chat_manager
from google import genai
from google.genai import types
from .db_tools import executar_consulta_sql


class SimpleRAGAgent(BaseAgent):
    """
    Agente RAG que responde perguntas consultando o banco de dados via Function Calling.
    """

    def __init__(self, model_name='gemini-2.5-flash-lite'):
        super().__init__(model_name)

        self.system_instruction = """Você é um assistente financeiro que responde perguntas sobre transações financeiras, notas fiscais e fornecedores.

**BANCO DE DADOS:**

Tabela: core_person
- id (integer): ID único
- documento (string): CPF/CNPJ normalizado
- tipo (string): 'fornecedor' ou 'faturado'
- razao_social (string): Nome da empresa
- fantasia (string, opcional): Nome fantasia
- status (string): 'ativo' ou 'inativo'

Tabela: core_accounttransaction
- id (integer): ID único
- numero_nota_fiscal (string): Número da nota (único)
- tipo (string): 'a pagar' ou 'a receber'
- data_emissao (date): Data de emissão
- descricao (text): Descrição dos produtos/serviços
- valor_total (decimal): Valor total
- fornecedor_cliente_id (integer): FK para core_person
- faturado_id (integer): FK para core_person
- status (string): 'ativo' ou 'inativo'

Tabela: core_installment
- id (integer): ID único
- account_transaction_id (integer): FK para core_accounttransaction
- identificacao (string): Ex: "1/3", "2/3"
- data_vencimento (date): Data de vencimento
- valor_parcela (decimal): Valor da parcela
- valor_pago (decimal): Valor já pago
- valor_saldo (decimal): Saldo restante
- status_parcela (string): 'aberta', 'paga', 'vencida', etc

Tabela: core_classification
- id (integer): ID único
- tipo (string): 'despesa' ou 'receita'
- descricao (string): Nome da classificação
- status (string): 'ativo' ou 'inativo'

Tabela: core_accounttransaction_classificacoes (N:N)
- accounttransaction_id (integer)
- classification_id (integer)

**FERRAMENTA DISPONÍVEL:**
Você tem acesso à função `executar_consulta_sql(query: str)` que executa queries SELECT no banco PostgreSQL.

**REGRAS:**
1. SEMPRE use `WHERE status = 'ativo'` nas tabelas que têm esse campo
2. Use LIMIT para evitar retornar muitos dados (máximo 50)
3. Use JOINs quando precisar relacionar tabelas
4. Para classificações, faça JOIN com core_accounttransaction_classificacoes
5. Após executar a consulta e receber os dados, SEMPRE gere uma resposta textual clara
6. Interprete os resultados e responda em linguagem natural
7. Formate valores em R$ e datas em DD/MM/AAAA
8. Sempre que necessário, busque as informações no banco de dados
9. O cliente não precisa saber sobre a estrutura do banco
```
"""

    def query(self, question, context="", max_retries=3, retry_delay=2):
        """
        Processa uma pergunta usando Function Calling com SQL.

        Args:
            question (str): Pergunta do usuário
            context (str): Contexto adicional (opcional)
            max_retries (int): Tentativas de retry
            retry_delay (int): Delay entre tentativas

        Returns:
            dict: Resposta com texto e metadados
        """
        if not question or not question.strip():
            return {
                "error": "Pergunta vazia",
                "response": None,
                "tools_used": [],
                "db_query_performed": False
            }

        def query_operation():
            tools_used = []

            # Prepara mensagem do usuário
            user_text = question.strip()
            if context and context.strip():
                user_text = f"Contexto: {context}\n\nPergunta: {user_text}"

            self.logger.info(f"Pergunta: {user_text}")

            # 1. Primeira chamada com tools
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_text,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    tools=[executar_consulta_sql],
                ),
            )

            # 2. Verifica se há function calls
            if response.function_calls:
                self.logger.info(f"Detectadas {len(response.function_calls)} function calls")

                # Executa as funções
                function_response_parts = []
                for fc in response.function_calls:
                    self.logger.info(f"Executando: {fc.name} com args: {dict(fc.args)}")
                    tools_used.append({"function": fc.name, "args": dict(fc.args)})

                    # Executa a função SQL
                    resultado = executar_consulta_sql(**fc.args)

                    # Cria resposta da função
                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"resultado": resultado}
                        )
                    )

                # 3. Segunda chamada com resultados
                self.logger.info("Enviando resultados para gerar resposta final")
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[
                        types.Content(
                            role='user',
                            parts=[types.Part.from_text(user_text)]
                        ),
                        response.candidates[0].content,
                        types.Content(role='tool', parts=function_response_parts)
                    ],
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_instruction,
                        tools=[executar_consulta_sql],
                    ),
                )

            # 4. Extrai resposta final
            response_text = None
            if hasattr(response, 'text') and response.text:
                response_text = response.text.strip()

            if not response_text:
                self.logger.error("Resposta vazia do modelo")
                raise ValueError("Modelo não retornou texto")

            self.logger.info(f"Resposta gerada: {response_text[:100]}...")

            return {
                "response": response_text,
                "context_used": bool(context and context.strip()),
                "tools_used": tools_used,
                "db_query_performed": len(tools_used) > 0,
                "error": None
            }

        # Executa com retry
        return self._retry_with_backoff(
            operation=query_operation,
            max_retries=max_retries,
            retry_delay=retry_delay,
            operation_name="consulta RAG"
        )

    def process(self, question, context="", max_retries=3, retry_delay=2):
        """
        Implementação do método abstrato process().
        Alias para query().
        """
        return self.query(question, context, max_retries, retry_delay)

    def query_with_chat(self, question, session_id=None, max_retries=3, retry_delay=2):
        """
        Processa uma pergunta usando chat com histórico de contexto.
        Mantém a conversa entre múltiplas mensagens armazenando o histórico.

        Args:
            question (str): Pergunta do usuário
            session_id (str, optional): ID da sessão de chat existente
            max_retries (int): Tentativas de retry
            retry_delay (int): Delay entre tentativas

        Returns:
            dict: Resposta com texto, metadados e session_id
        """
        if not question or not question.strip():
            return {
                "error": "Pergunta vazia",
                "response": None,
                "tools_used": [],
                "db_query_performed": False,
                "session_id": session_id
            }

        def query_operation():
            tools_used = []
            history = []
            is_new_session = False

            # 1. Recupera histórico existente ou cria nova sessão
            if session_id:
                session = chat_manager.get_session(session_id)
                if session and session["agent_type"] == "simple":
                    history = session["chat"].get("history", [])
                    self.logger.info(f"Usando sessão existente: {session_id} ({len(history)} mensagens)")
                else:
                    self.logger.warning(f"Sessão inválida ou expirada: {session_id}")
                    session_id_to_use = None

            if not session_id or not history:
                self.logger.info("Criando nova sessão de chat")
                is_new_session = True
                session_id_to_use = None
            else:
                session_id_to_use = session_id

            # 2. Prepara conteúdo com histórico
            user_text = question.strip()
            self.logger.info(f"Pergunta: {user_text}")

            # Monta contents com histórico + nova mensagem
            contents = []
            for msg in history:
                contents.append(msg)

            # Adiciona nova pergunta do usuário
            contents.append(types.Content(
                role='user',
                parts=[types.Part(text=user_text)]
            ))

            # 3. Primeira chamada com tools
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    tools=[executar_consulta_sql],
                ),
            )

            # 4. Processa function calls se houver
            if response.function_calls:
                self.logger.info(f"Detectadas {len(response.function_calls)} function calls")

                # Executa as funções
                function_response_parts = []
                for fc in response.function_calls:
                    self.logger.info(f"Executando: {fc.name} com args: {dict(fc.args)}")
                    tools_used.append({"function": fc.name, "args": dict(fc.args)})

                    # Executa a função SQL
                    resultado = executar_consulta_sql(**fc.args)

                    # Cria resposta da função
                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"resultado": resultado}
                        )
                    )

                # Adiciona resposta do modelo (com function calls) ao histórico
                contents.append(response.candidates[0].content)

                # Adiciona respostas das funções
                contents.append(types.Content(role='tool', parts=function_response_parts))

                # Segunda chamada para gerar resposta final
                self.logger.info("Enviando resultados para gerar resposta final")
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_instruction,
                        tools=[executar_consulta_sql],
                    ),
                )

            # 5. Extrai resposta final
            response_text = None
            if hasattr(response, 'text') and response.text:
                response_text = response.text.strip()

            if not response_text:
                self.logger.error("Resposta vazia do modelo")
                raise ValueError("Modelo não retornou texto")

            self.logger.info(f"Resposta gerada: {response_text[:100]}...")

            # 6. Atualiza histórico com pergunta do usuário e resposta do modelo
            # Adiciona mensagem do usuário
            history.append(types.Content(
                role='user',
                parts=[types.Part(text=user_text)]
            ))

            # Adiciona resposta do modelo
            history.append(response.candidates[0].content)

            # 7. Salva ou atualiza sessão
            if is_new_session:
                session_data = {"history": history}
                new_session_id = chat_manager.create_session(session_data, agent_type="simple")
            else:
                new_session_id = session_id_to_use
                session = chat_manager.get_session(new_session_id)
                if session:
                    session["chat"]["history"] = history
                    chat_manager.increment_message_count(new_session_id)

            return {
                "response": response_text,
                "tools_used": tools_used,
                "db_query_performed": len(tools_used) > 0,
                "error": None,
                "session_id": new_session_id,
                "is_new_session": is_new_session
            }

        # Executa com retry
        return self._retry_with_backoff(
            operation=query_operation,
            max_retries=max_retries,
            retry_delay=retry_delay,
            operation_name="consulta RAG com chat"
        )
