import os
import matplotlib.pyplot as plt
import io
import pandas as pd
from io import BytesIO
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
import maritalk
from tabulate import tabulate

# Definindo os estados da conversa como constantes
AWAITING_RESPONSE = 0
BEFORE_DATA_CLEANING = 1
ASKING_DATA_CLEANING = 2
CONFIRM_DATA_CLEANING = 3
ASKING_ANALYSIS = 4
DECIDE_NEXT_STEP = 5
GETTING_ANALYSIS_TYPE = 6
CONFIRM_ANALYSIS_CLEANING = 7
ANALYSIS_NEXT_STEPS = 8

def initialize_model():
    KEY = os.getenv('MARITACA_KEY')

    model = maritalk.MariTalk(
        key = KEY,
        model = "sabia-3"
    )

    prompt_inicial = f'''Hoje você será uma IA especializada em análise de dados que conversará com um usuário
    como um chatbot do Telegram, que enviará um conjunto de dados para análise. Vou te enviar comandos e análises
    pedidas por mim ou pelo usuário e você responderá precisamente meus comandos e conversará com o usuário de forma 
    eficiente e concisa, mas focada em resolver o problema do usuário. Responda apenas "ok" agora, estou te informando.
    '''

    response = model.generate(prompt_inicial, max_tokens = 10)

    print(response['answer'])

    return model

async def send_dataframe_image(df, update, context, title="DataFrame Visualizado"):
    # Configura a figura para plotar o DataFrame como imagem
    fig, ax = plt.subplots(figsize=(10, 4))  # Ajusta o tamanho da imagem
    ax.axis('tight')
    ax.axis('off')
    
    # Converte o DataFrame para tabela dentro da imagem
    table = ax.table(cellText=df.values, colLabels=df.columns, cellLoc='center', loc='center')
    
    # Ajustes de estilo e formatação
    table.scale(1, 1.5)
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    
    # Salva a imagem em um buffer de bytes
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)  # Fecha a figura para evitar consumo de memória

    # Envia a imagem para o usuário no Telegram
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=InputFile(buf, filename="dataframe.png"), caption=title)

async def send_dataframe_as_ascii(df: pd.DataFrame, update: Update):
    # Limita o número de linhas e colunas para evitar tabelas muito grandes
    max_rows = 10  # Limita o número de linhas exibidas
    max_cols = 10  # Limita o número de colunas exibidas

    if df.shape[0] > max_rows:
        df = df.head(max_rows)

    if df.shape[1] > max_cols:
        df = df.iloc[:, :max_cols]

    # Converte o DataFrame para tabela ASCII usando tabulate
    df_str = tabulate(df, headers='keys', tablefmt='fancy_grid', showindex=False)
    
    # Envia a tabela no chat com formatação de código para garantir a legibilidade
    await update.message.reply_text(f"```\n{df_str}\n```", parse_mode='Markdown')

def find_between( s, first, last ):
    try:
        start = s.index( first ) + len( first )
        end = s.index( last, start )
        return s[start:end]
    except ValueError:
        return ""

async def execute_code(code, update, context):
    try:
        exec(code)
    except Exception as e:
        await update.message.reply_text(f"Houve um erro ao executar o código: {str(e)}")

# Função que recebe o arquivo e converte para DataFrame
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file = update.message.document
    file_name = file.file_name
    context.user_data['file_name'] = file_name 
    print(file_name)
    print(context.user_data['file_name'])

    if file.mime_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:  # Arquivo Excel
        file_id = file.file_id
        new_file = await context.bot.get_file(file_id)
        file_stream = BytesIO(await new_file.download_as_bytearray())
        
        # Leitura de arquivo Excel
        df = pd.read_excel(file_stream)
        context.user_data['df'] = df  # Armazenando o DataFrame no contexto do usuário
        await update.message.reply_text(f"Arquivo Excel convertido para DataFrame:\n\n{df.head()}")
        
    elif file.mime_type == 'text/csv':  # Arquivo CSV
        file_id = file.file_id
        new_file = await context.bot.get_file(file_id)
        file_stream = BytesIO(await new_file.download_as_bytearray())
        
        # Leitura de arquivo CSV
        df = pd.read_csv(file_stream)
        context.user_data['df'] = df  # Armazenando o DataFrame no contexto do usuário
        await update.message.reply_text(f"Arquivo CSV convertido para DataFrame:\n{df.head()}")
    
    else:
        await update.message.reply_text("Por favor, envie um arquivo .xlsx ou .csv.")
        return ConversationHandler.END

    # Pergunta ao usuário sobre o tratamento de dados
    await update.message.reply_text("Você gostaria de fazer algum tipo de Tratamento de Dados? (sim/não)")
    
    return BEFORE_DATA_CLEANING  # Avança para handle_data_cleaning

async def asking_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_response = update.message.text.lower()

    if user_response == 'sim':
        print("Usuário deseja fazer o 1° tratamento" )
        await update.message.reply_text("Qual tipo de tratamento você gostaria de fazer? (Exemplo: remover valores nulos, normalizar colunas, etc.)")
        return ASKING_DATA_CLEANING  # Retorna para mais tratamento de dados
    elif user_response == 'não' or user_response == 'nao':
        print("Usuário não deseja fazer tratamentos. Redirecionando ele para finalizar.")
        await update.message.reply_text("Gostaria de fazer uma Análise de Dados? (sim/não)")
        return ASKING_ANALYSIS  # Avança para a análise de dados
    else:
        await update.message.reply_text("Responda entre 'sim' ou 'não'.")
        return BEFORE_DATA_CLEANING  # Volta para confirmação

# Função para gerar e executar o código de tratamento de dados
async def handle_data_cleaning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    df = context.user_data.get('df')
    df_original = df.copy()
    df.head()
    ver_df = None 
    
    # Recupera e atualiza o histórico de contexto para manter as interações anteriores
    context.user_data.setdefault('historico', [])
    contexto_historico = "\n".join([f"Usuário: {item['prompt']}\nIA: {item['resposta']}" for item in context.user_data['historico']])

    if df is not None:
        user_input = update.message.text  # Pega a instrução do usuário
        ver_df = df.head()
        prompt = f'''{contexto_historico}

        Você é um analista de dados. Faça todo o código para df e considere usar variáveis de forma a obter automaticamente os numeros finais de linhas e colunas, de acordo com a descrição do usuário você deverá fazer para cada linha ou para cada coluna, deverá olhar para dentro do arquivo recebido e fazer as devidas alterações
        Você deverá ler a demanda de um cliente e gerar um output que contenha: 0) Não chame "df = pd.read_csv('')", entenda que o código só servirá para ser rodado no meio de outro código que já sabe o valor da variável df, portanto você só aplicará alterações a df. 1) Um código em python que resolva a demanda do cliente; 2) Indique se o output do código é uma imagem ou uma string utilizando o valor "0" para imagem e "1" para string.
        Abaixo vou fornecer para você em qual formato deve ser sua resposta e também a demanda do cliente.
        A demanda do cliente é: {user_input}
        O .head do arquivo é {ver_df}
        FORMATO_RESPOSTA_MARITALK:
        ```python
        # AQUI ESTARÁ O SEU CÓDIGO EM PYTHON
        ```
        TIPO_RESPOSTA: # AQUI VOCÊ INDICARÁ SE O OUTPUT É UMA IMAGEM (VALOR 0) OU UMA STRING (VALOR 1)

       Caso o usuário solicite um gráfico, crie no seu código essa estrutura pra enviar ao usuario # Envia o gráfico para o usuário
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=InputFile(buf, filename="grafico.png")
            ), onde "grafico.png" é a variavel que vai ser salva como png para enviar ao usuario

        Se o tratamento der ou não certo, deverá retornar nessa estrutura ao usuário:
        update.message.reply_text(f"Tratamento [tratamento solicitada pelo usuario] realizado com sucesso")
        '''

        response = model.generate(prompt, max_tokens=2000)      
        answer = response["answer"]
        code = find_between(answer, "```python", "```")
        output_type = find_between(answer, "TIPO_RESPOSTA:", "\n").strip()

        print(f"Pedido do usuário '{user_input}'")
        print(f"Resposta: {answer}")

        tries = 3
        tentativas_restantes = tries
        for i in range(tries):
            tentativas_restantes -= 1
            try:
                if output_type == '0':  # Imagem
                    buf = BytesIO()
                    exec(code)
                    print(f"Código da Maritaka '{code}'")
                    print(f"Código sendo executado... '{exec(code)}'")
                    buf.seek(0)
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=InputFile(buf, filename="grafico.png"))
                    # Mostra o DataFrame atualizado
                    await update.message.reply_text(f"DataFrame após o tratamento:\n{df.head()}")
                    # Pergunta se o usuário gostou do tratamento
                    await update.message.reply_text("Os dados tratados estão de acordo com o que foi solicitado? (sim/não)")
                    # Avança para o estado de confirmação do tratamento
                    return CONFIRM_DATA_CLEANING 
                else:  # Texto
                    exec(code)
                    print(f"Código da Maritaka '{code}'")
                    print(f"Código sendo executado... '{exec(code)}'")
                    if df_original.equals(df):
                        await update.message.reply_text(f"O código foi executado, mas não alterou o DataFrame.\nAinda restam {tentativas_restantes} tentativas.\nTentando novamente...")
                        ver_df = df.head()
                    else:
                        await update.message.reply_text("Tratamento executado com sucesso!")
                        await update.message.reply_text(f"Arquivo Tratado:\n\n{df.head()}")
                        await send_dataframe_image(df, update, context, title="DataFrame Tratado")
                        await send_dataframe_as_ascii(df, update)
                        # Exibe as alterações entre DataFrames.
                        print("Uma visão do excel tratado:")
                        df.head()
                        ver_df
                        # Pergunta se o usuário gostou do tratamento
                        await update.message.reply_text("Os dados tratados estão de acordo com o que foi solicitado? (sim/não)")
                        # Avança para o estado de confirmação do tratamento
                        return CONFIRM_DATA_CLEANING      
            except Exception as e:
                error_message = str(e)
                if not df_original.equals(df):
                    await update.message.reply_text(f"Tratamento executado com sucesso, mas ocorreu o seguinte erro durante a execução: '{error_message}'")
                    await update.message.reply_text("Os dados tratados estão de acordo com o que foi solicitado? (sim/não)")
                    # Avança para o estado de confirmação do tratamento
                    return CONFIRM_DATA_CLEANING
                else:
                    await update.message.reply_text(f"Tentativa número {i+1}. Erro ao executar o código gerado: '{error_message}'.\nTentando novamente...")
                    print(f"Mensagem de erro '{error_message}'")
                    if i < tries - 1:
                        # Recupera e atualiza o histórico de contexto para manter as interações anteriores
                        context.user_data.setdefault('historico', [])
                        contexto_historico = "\n".join([f"Usuário: {item['prompt']}\nIA: {item['resposta']}" for item in context.user_data['historico']])
                        prompt = f'''{contexto_historico}
                        A sua resposta anterior '{answer}' resultou em erro: {error_message}.
                        As colunas atuais do DataFrame são: {list(df.columns)} e os tipos de dados são: {df.dtypes.to_dict()}.
                        Como será enviado ao chat do usuário, 
                        Segue uma ideia da planilha:
                        {ver_df}

                        Segue solicitação do Usuário, atenção aos detalhes.
                        '{user_input}'

                        TIPO_RESPOSTA: # AQUI VOCÊ INDICARÁ SE O OUTPUT É UMA IMAGEM (VALOR 0) OU UMA STRING (VALOR 1)

                        Caso o usuário solicite um gráfico, crie no seu código essa estrutura pra enviar ao usuario # Envia o gráfico para o usuário
                            await context.bot.send_photo(
                                chat_id=update.effective_chat.id,
                                photo=InputFile(buf, filename="grafico.png")
                            ), onde "grafico.png" é a variavel que vai ser salva como png para enviar ao usuario

                        Se o tratamento der ou não certo, deverá retornar nessa estrutura ao usuário:
                        update.message.reply_text(f"Tratamento [tratamento solicitada pelo usuario] realizado com sucesso")
                        '''

                        response = model.generate(prompt, max_tokens=2000)
                        code = find_between(response['answer'], "```python", "```")
                        output_type = find_between(response['answer'], "TIPO_RESPOSTA:", "\n").strip()
                        answer = response["answer"]
                        print(f"Pedido do usuário '{user_input}'")
                        print(f"Resposta: {answer}")
                        # Armazena a nova interação no histórico
                        context.user_data['historico'].append({
                            'prompt': prompt,
                            'resposta': answer
                        })
                        
                        print(f"Quero ver se traz algum resultado aqui '{next}'")
                        next
                    else:
                        # Se todas as tentativas falharem, finaliza o processo
                        await update.message.reply_text(f"Código apresentou Erro: '{str(e)}'")
                        # Mostra o DataFrame atualizado
                        await update.message.reply_text(f"DataFrame após o tratamento:\n{df.head()}")
                        # Pergunta se o usuário gostou do tratamento
                        await update.message.reply_text("Os dados tratados estão de acordo com o que foi solicitado? (sim/não)")
                        # Avança para o estado de confirmação do tratamento
                        return CONFIRM_DATA_CLEANING 
    else:
        await update.message.reply_text("Nenhum DataFrame foi carregado ainda.")
        return ConversationHandler.END

# Função para confirmar se o usuário gostou do tratamento realizado
async def confirm_data_cleaning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_response = update.message.text.lower()

    if user_response == 'sim':
        await update.message.reply_text("Que bom que os dados estão corretos! Você deseja fazer outro Tratamento de Dados? (sim/não)")
        print("Código tratado da forma correta!")
        return DECIDE_NEXT_STEP  # Avança para decidir a próxima etapa
    elif user_response == 'não' or user_response == 'nao':
        await update.message.reply_text("O que você gostaria de mudar no Tratamento?")
        print("Erro no tratamento. Redirecionando a falar com a maritaka novamente!")
        return ASKING_DATA_CLEANING  # Usuário deseja mudar algo no tratamento
    else:
        await update.message.reply_text("Responda entre 'sim' ou 'não'.")
        return CONFIRM_DATA_CLEANING  # Continua esperando resposta válida

# Função para gerenciar a resposta após confirmação do tratamento
async def handle_next_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_response = update.message.text.lower()

    if user_response == 'sim':
        await update.message.reply_text("Que tipo de tratamento adicional você gostaria de fazer?")
        print("Novo tratamento. Redirecionando a falar com a maritaka novamente!")
        return ASKING_DATA_CLEANING  # Retorna para mais tratamento de dados
    elif user_response == 'não' or user_response == 'nao':
        await update.message.reply_text("Gostaria de fazer uma Análise de Dados? (sim/não)")
        print("Usuário não deseja mais fazer tratamento. Redireciando para a entrega do arquivo final.")
        return ASKING_ANALYSIS  # Avança para a análise de dados
    else:
        await update.message.reply_text("Responda entre 'sim' ou 'não'.")
        return DECIDE_NEXT_STEP  # Volta para confirmação
    
# Função para perguntar qual tipo de análise o usuário deseja fazer
async def ask_for_analysis_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Pergunta ao usuário sobre o tipo de análise
    user_response = update.message.text.lower()
    df = context.user_data.get('df')

    if user_response == 'sim':
        await update.message.reply_text("Qual tipo de análise você gostaria de realizar? Exemplo: contagem de valores, análise estatística, visualização gráfica, etc.")
        return GETTING_ANALYSIS_TYPE  # Avança para a função handle_analysis

    elif user_response == 'não' or user_response == 'nao':   
        nome_bot = 'GuruData'   
        df = context.user_data.get('df')
        print('Salvando o arquivo final.')
        if df is not None:
            original_file_name = context.user_data.get('file_name', 'arquivo_tratado.xlsx')
            modified_filename = os.path.splitext(original_file_name)[0] + '_v2.xlsx'
            # Salva o DataFrame final em um arquivo Excel
            output = BytesIO()
            df.to_excel(output, index=False)  # Converte o DataFrame para Excel sem o índice
            output.seek(0)  # Move o cursor para o início do arquivo
            # Envia o arquivo Excel final ao usuário
            await update.message.reply_text("Aqui está o arquivo final!")
            await update.message.reply_document(document=InputFile(output, filename=modified_filename))
            await update.message.reply_text(f"Obrigado por utilizar o {nome_bot}!")
        else:
            await update.message.reply_text("Nenhum arquivo foi carregado ou tratado.")

# Função para análise de dados e envio de gráficos
#async def handle_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
#    df = context.user_data.get('df')
#    df_original = df.copy()
#    
#    if df is not None:
#        user_input = update.message.text  # Pega a instrução do usuário
#
#        prompt = f'''Você é um analista de dados. Suponha que 'df' já é um DataFrame existente com as colunas df.columns.
#        Você deverá ler a demanda de um cliente e gerar um output que contenha: 1) Um código em python que resolva a demanda do cliente; 2) Indique se o output do código é uma imagem ou uma string utilizando o valor "0" para imagem e "1" para string.
#        Abaixo vou fornecer para você em qual formato deve ser sua resposta e também a demanda do cliente.
#
#        A demanda do cliente é: {user_input}
#
#        FORMATO_RESPOSTA_MARITALK:
#        ```python
#        # AQUI ESTARÁ O SEU CÓDIGO EM PYTHON
#        ```
#        TIPO_RESPOSTA: # AQUI VOCÊ INDICARÁ SE O OUTPUT É UMA IMAGEM (VALOR 0) OU UMA STRING (VALOR 1)
#
#        Caso o usuário solicite um gráfico, crie no seu código essa estrutura pra enviar ao usuario # Envia o gráfico para o usuário
#            await context.bot.send_photo(
#                chat_id=update.effective_chat.id,
#                photo=InputFile(buf, filename="grafico.png")
#            ), onde "grafico.png" é a variavel que vai ser salva como png para enviar ao usuario
#        
#        Salva o arquivo df final para salvar as alterações feitas.
#
#        Se a análise der ou não certo, deverá retornar nessa estrutura ao usuário:
#        await update.message.reply_text(f"Análise [análise solicitada pelo usuario] realizado com sucesso.")
#        '''
#
#        response = model.generate(prompt, max_tokens = 2000)      
#        answer = response["answer"]
#
#        print(f"Resposta: {answer}")
#        code = find_between(answer, "```python", "```")
#        output_type = find_between(response['answer'], "TIPO_RESPOSTA:", "\n").strip()
#
#        tries = 3
#        for i in range(tries):
#            try:
#                if output_type == '0':  # Imagem
#                    buf = BytesIO()
#                    exec(code)
#                    buf.seek(0)
#                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=InputFile(buf, filename="grafico.png"))
#                else:  # Texto
#                    exec(code)
#                    if df_original.equals(df):
#                        await update.message.reply_text("O código foi executado, mas não alterou o DataFrame.")
#                    else:
#                        await update.message.reply_text("Análise executada com sucesso!")
#                        # Exibe as alterações entre DataFrames
#                        diff = df_original.compare(df)
#                        await update.message.reply_text(f"As diferenças entre o DataFrame original e o modificado:\n{diff}")
#                        break
#
#                break
#            except Exception as e:
#                if i < tries - 1:
#                    # Gera novo código caso tenha ocorrido um erro e ainda haja tentativas restantes
#                    prompt = f'''O código gerado anteriormente resultou em erro: {e}. Por favor, gere um novo código corrigido.'''
#                    response = model.generate(prompt, max_tokens=2000)
#                    code = find_between(response['answer'], "```python", "```")
#                    output_type = find_between(response['answer'], "TIPO_RESPOSTA:", "\n").strip()
#                else:
#                    # Se todas as tentativas falharem, finaliza o processo
#                    await update.message.reply_text(f"Não foi possível realizar a análise após {tries} tentativas. Erro: {str(e)}")
#                    return DECIDE_NEXT_STEP
#        
#        # Mostra o DataFrame atualizado
#        await update.message.reply_text(f"DataFrame após o tratamento:\n{df.head()}")
#        
#        # Pergunta se o usuário gostou do tratamento
#        await update.message.reply_text("Os dados analisados estão de acordo com o que foi solicitado? (sim/não)")
#        
#        # Avança para o estado de confirmação do tratamento
#        return CONFIRM_ANALYSIS_CLEANING
#    
#    else:
#        # Caso nenhum DataFrame tenha sido carregado, informa ao usuário
#        await update.message.reply_text("Nenhum DataFrame foi carregado ainda.")
#        return ConversationHandler.END

async def confirm_analise_cleaning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_response = update.message.text.lower()

    if user_response == 'sim':
        await update.message.reply_text("Que bom que os dados estão corretos! Você deseja fazer outra Análise de Dados? (sim/não)")
        return ANALYSIS_NEXT_STEPS  # Avança para decidir a próxima etapa
    elif user_response == 'não' or user_response == 'nao':
        await update.message.reply_text("O que você gostaria de mudar na Análise?")
        return GETTING_ANALYSIS_TYPE
    # Usuário deseja mudar algo na Análise
    else:
        await update.message.reply_text("Responda entre 'sim' ou 'não'.")
        return CONFIRM_ANALYSIS_CLEANING  # Continua esperando resposta válida

# Função para gerenciar a resposta após confirmação do tratamento
async def analysis_next_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_response = update.message.text.lower()

    if user_response == 'sim':
        await update.message.reply_text("Que tipo de análise adicional você gostaria de fazer?")
        return GETTING_ANALYSIS_TYPE  # Retorna para mais tratamento de dados
    elif user_response == 'não' or user_response == 'nao':
        df = context.user_data.get('df')
        nome_bot = 'GuruData'
        print('Salvando o arquivo final.')
        if df is not None:
            original_file_name = context.user_data.get('file_name', 'arquivo_tratado.xlsx')
            modified_filename = os.path.splitext(original_file_name)[0] + '_v2.xlsx'
            # Salva o DataFrame final em um arquivo Excel
            output = BytesIO()
            df.to_excel(output, index=False)  # Converte o DataFrame para Excel sem o índice
            output.seek(0)  # Move o cursor para o início do arquivo
            # Envia o arquivo Excel final ao usuário
            await update.message.reply_text("Aqui está o arquivo final!")
            await update.message.reply_document(document=InputFile(output, filename=modified_filename))
            await update.message.reply_text(f"Obrigado por utilizar o {nome_bot}!")
        else:
            await update.message.reply_text("Nenhum arquivo foi carregado ou tratado.")

        return ConversationHandler.END  # Finaliza a conversa
    else:
        await update.message.reply_text("Responda entre 'sim' ou 'não'.")
        return ANALYSIS_NEXT_STEPS  # Volta para confirmação

# Função de cancelamento
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END

# Função de start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Olá! Envie um arquivo .xlsx ou .csv para começar.')

def main():
    # Carrega o token do bot
    TOKEN = '7870801769:AAFHv05z4kSmqckgf3KMdxEhoSxtMXLW4A0'
    
    nome_bot = 'GuruData'

    global model 
    
    model = initialize_model()
    
    # Criando a aplicação
    application = Application.builder().token(TOKEN).connect_timeout(20).build()    

    # Configurando o ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Document.MimeType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") | 
                                     filters.Document.MimeType("application/vnd.ms-excel") | 
                                     filters.Document.MimeType("text/csv"), handle_file)],
        
        states={
            BEFORE_DATA_CLEANING: [MessageHandler(filters.TEXT, asking_data)],
            ASKING_DATA_CLEANING: [MessageHandler(filters.TEXT, handle_data_cleaning)],
            CONFIRM_DATA_CLEANING: [MessageHandler(filters.TEXT, confirm_data_cleaning)],
            DECIDE_NEXT_STEP: [MessageHandler(filters.TEXT, handle_next_step)],
            ASKING_ANALYSIS: [MessageHandler(filters.TEXT, ask_for_analysis_type)],
            CONFIRM_ANALYSIS_CLEANING: [MessageHandler(filters.TEXT, confirm_analise_cleaning)],
            ANALYSIS_NEXT_STEPS: [MessageHandler(filters.TEXT, analysis_next_step)],          
        },
        
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    # Comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)

    # Iniciando o bot
    application.run_polling()

if __name__ == '__main__':
    main()