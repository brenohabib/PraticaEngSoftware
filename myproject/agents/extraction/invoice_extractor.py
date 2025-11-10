import os
import json

from ..agent import BaseAgent

class PDFExtractorAgent(BaseAgent):
    def __init__(self, model_name='gemini-2.5-flash-lite'):
        super().__init__(model_name)
        self.prompt_template = """
            Você é um especialista em análise de documentos fiscais. Analise a nota fiscal fornecida e extraia apenas as informações solicitadas, retornando um **JSON válido** no formato especificado abaixo.

            ### Campos a extrair:

            1. **Fornecedor (Emitente)**
            - razão_social
            - fantasia (ou null, se não houver)
            - cnpj

            2. **Faturado (Destinatário/Cliente)**
            - nome_completo
            - cpf_cnpj

            3. **Número da Nota Fiscal**
            4. **Data de Emissão** (DD/MM/AAAA)
            5. **Descrição dos Produtos** (array de strings)
            6. **Classificação de Despesa** (array de categorias, conforme critérios abaixo)
            7. **Quantidade de Parcelas** (1 se à vista)
            8. **Data de Vencimento** (DD/MM/AAAA)
            9. **Valor Total** (número decimal)

            ### Formato de Resposta:
            Retorne **apenas** um objeto JSON com a seguinte estrutura:
            {
            "fornecedor": {
                "razao_social": "string",
                "fantasia": "string ou null",
                "cnpj": "string"
            },
            "faturado": {
                "nome_completo": "string",
                "cpf_cnpj": "string"
            },
            "numero_nota_fiscal": "string",
            "data_emissao": "DD/MM/AAAA",
            "descricao_produtos": ["string"],
            "classificacao_despesa": ["string"],
            "quantidade_parcelas": número,
            "data_vencimento": "DD/MM/AAAA",
            "valor_total": número
            }

            ### Critério para “classificacao_despesa”:
            Associe `descricao_produtos` à categoria correspondente entre as opções abaixo (sem duplicar valores):

            - INSUMOS AGRÍCOLAS : Sementes, Fertilizantes, Defensivos (Apenas produtos associados à agricultura, não infraestrutura)
            - MANUTENÇÃO E OPERAÇÃO : Combustíveis, Peças, Pneus, Ferramentas, Parafusos, Infraestrutura, etc.
            - RECURSOS HUMANOS : Mão de obra, Salários
            - SERVIÇOS OPERACIONAIS : Frete, Transporte, Colheita, Armazenagem, Secagem
            - INFRAESTRUTURA E UTILIDADES : Energia, Arrendamento, Materiais de construção
            - ADMINISTRATIVAS : Honorários, Despesas bancárias, Contabilidade
            - SEGUROS E PROTEÇÃO : Seguros agrícolas ou de veículos
            - IMPOSTOS E TAXAS : ITR, IPTU, IPVA, INCRA, etc.
            - INVESTIMENTOS : Aquisição de máquinas, veículos, imóveis  
            - OUTRAS DESPESAS : Se não se enquadrar em nenhuma das anteriores

            ### Regras Gerais:
            - Retorne somente o JSON, sem explicações.  
            - Campos não encontrados → **null**
            - Datas → formato **DD/MM/AAAA**
            - Valores monetários → **número decimal (ex: 1500.50)**
            - Lista de classificações sem duplicatas

        """

    def extract_pdf_to_json(self, pdf_path, max_retries=3, retry_delay=2):
        """
        Extrai informações de um PDF e retorna em formato JSON usando upload direto do arquivo

        Args:
            pdf_path (str): Caminho para o arquivo PDF
            max_retries (int): Número máximo de tentativas em caso de falha
            retry_delay (int): Tempo de espera entre tentativas em segundos

        Returns:
            dict: Dados extraídos em formato JSON ou mensagem de erro
        """
        # Validação inicial do arquivo
        if not os.path.exists(pdf_path):
            self.logger.error(f"Arquivo não encontrado: {pdf_path}")
            return {"error": f"Arquivo não encontrado: {pdf_path}"}

        # Tenta fazer upload do arquivo
        try:
            self.logger.info(f"Fazendo upload do arquivo: {pdf_path}")
            uploaded_file = self.client.files.upload(file=pdf_path)
            self.logger.info(f"Arquivo enviado com sucesso. URI: {uploaded_file.uri}")
        except Exception as e:
            self.logger.error(f"Erro ao fazer upload do arquivo: {str(e)}")
            return {"error": f"Falha no upload do arquivo: {str(e)}"}

        # Define a operação de extração que será executada com retry
        def extraction_operation():
            # Gera o conteúdo usando o arquivo já carregado
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[self.prompt_template, uploaded_file]
            )

            # Extrai o texto da resposta
            if not response or not response.text:
                raise ValueError("Resposta vazia da API")

            response_text = response.text

            # Limpa e valida o JSON
            cleaned_json = self._clean_json_response(response_text)

            # Tenta fazer o parse do JSON
            extracted_data = json.loads(cleaned_json)

            return extracted_data

        # Executa a operação com retry
        return self._retry_with_backoff(
            operation=extraction_operation,
            max_retries=max_retries,
            retry_delay=retry_delay,
            operation_name="extração de PDF"
        )

    def process(self, pdf_path, max_retries=3, retry_delay=2):
        """
        Implementação do método abstrato process().
        Alias para extract_pdf_to_json() mantendo compatibilidade.

        Args:
            pdf_path (str): Caminho para o arquivo PDF
            max_retries (int): Número máximo de tentativas em caso de falha
            retry_delay (int): Tempo de espera entre tentativas em segundos

        Returns:
            dict: Dados extraídos em formato JSON ou mensagem de erro
        """
        return self.extract_pdf_to_json(pdf_path, max_retries, retry_delay)