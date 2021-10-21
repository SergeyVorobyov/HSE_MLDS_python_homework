import telebot
from telebot import types
import sqlite3
import requests
import boto3
import pandas as pd
import hashlib
import time

from config import bot_token
from config import bot_latest_version
from config import bot_latest_version_release_date
from config import bot_desc
from config import unsupported_content_types

from config import AWS_ACCESS_KEY_ID
from config import AWS_SECRET_ACCESS_KEY
from config import AWS_BUCKET_NAME

bot = telebot.TeleBot(bot_token)

### начальная клавиатура
start_keyboard = types.ReplyKeyboardMarkup(row_width=1)
start_button_1 = types.KeyboardButton('Режим "Я в магазине" - разделаемся с этим списком!')
start_button_2 = types.KeyboardButton('Просмотреть список покупок')
start_button_3 = types.KeyboardButton('Добавить покупку в список (чтобы не забыть ее купить)')
start_button_4 = types.KeyboardButton('Убрать покупку из списка (ее не нужно покупать)')
start_button_5 = types.KeyboardButton('Очистить весь список')
# start_button_6 = types.KeyboardButton('Добавить покупки из файла')
# start_button_7 = types.KeyboardButton('Сохранить список покупок в файл')
start_button_beta = types.KeyboardButton('Надиктовать покупки голосом (beta)')
start_button_8 = types.KeyboardButton('Завершить сеанс')
start_keyboard.add(start_button_1)
start_keyboard.add(start_button_2)
start_keyboard.add(start_button_3)
start_keyboard.add(start_button_4)
start_keyboard.add(start_button_5)
# start_keyboard.add(start_button_6)
# start_keyboard.add(start_button_7)
start_keyboard.add(start_button_beta)
start_keyboard.add(start_button_8)

# для ввода названия покупки в ответном сообщении
add_purchase_reply = types.ForceReply('Что добавить в список?')

# чтоб убирать начальную клавиатуру
remove_keyboard = types.ReplyKeyboardRemove()

shop_mode_list = list()
###

# соединение с БД
conn = sqlite3.connect('purchase_lists.db')
cursor = conn.cursor()
try:
    query = 'CREATE TABLE "purchase_list" ("purchase_id" INTEGER UNIQUE, "user_id" INTEGER, "purchase_nm" TEXT, PRIMARY KEY ("purchase_id"))'
    cursor.execute(query)
except:
    pass

# для загрузки файлов в облако AWS
try:
    s3 = boto3.client('s3',
                      aws_access_key_id = AWS_ACCESS_KEY_ID,
                      aws_secret_access_key = AWS_SECRET_ACCESS_KEY,
                      region_name = 'us-east-2')
except:
    pass

# начальная клавиатура
@bot.message_handler(func=lambda message: message.text == 'start', content_types=['text'])
@bot.message_handler(func=lambda message: message.text == '/start', content_types=['text'])
@bot.message_handler(commands=['start'])
def start_command(message, txt="Чтобы бы Вы хотели сделать?"):
    msg = bot.send_message(message.from_user.id, text=txt, reply_markup=start_keyboard)
    bot.register_next_step_handler(msg, callback_dispacher)

# кратко о боте
@bot.message_handler(func=lambda message: message.text == 'help', content_types=['text'])
@bot.message_handler(func=lambda message: message.text == '/help', content_types=['text'])
@bot.message_handler(commands=['help'])
def help_command(message):
    msg = bot.send_message(message.from_user.id,
                           text=bot_desc + ' \r\n' + 'version = ' + bot_latest_version \
                                + ' (' + bot_latest_version_release_date + ')'
                           )
    start_command(message)

# обработка не поддерживаемых типов
@bot.message_handler(content_types=unsupported_content_types)
def for_future_dev(message):
    #    bot.send_message(message.from_user.id, message.text)
    bot.send_message(message.from_user.id, 'Я Вас не понимаю :( не судите строго, я только учусь')
    start_command(message, 'Что-нибудь еще?')

# голосове сообщение в текст (beta)
@bot.message_handler(content_types=['voice'])
def from_voice(message):
    try:
        file_info = bot.get_file(message.voice.file_id)
        file = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(bot_token, file_info.file_path))
        open(message.voice.file_id+'.ogg', 'wb').write(file.content)
        hash_ = hashlib.sha1()
        hash_.update((str(message.voice.file_id)+str(time.time())).encode('utf-8'))

        s3.upload_file(message.voice.file_id+'.ogg', AWS_BUCKET_NAME, message.voice.file_id+'.ogg')
        job_name = hash_.hexdigest()
        job_uri = 's3://'+AWS_BUCKET_NAME+'/'+message.voice.file_id+'.ogg'

        transcribe = boto3.client('transcribe', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY, region_name='us-east-2')
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': job_uri},
            MediaFormat = 'ogg',
            LanguageCode='ru-RU')

        while True:
            result = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            if result['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
                break
            time.sleep(1)

        if result['TranscriptionJob']['TranscriptionJobStatus'] == "COMPLETED":
            data = pd.read_json(result['TranscriptionJob']['Transcript']['TranscriptFileUri'])
            bot.send_message(message.chat.id, data['results'][1][0]['transcript'])
            start_command(message)

        if result['TranscriptionJob']['TranscriptionJobStatus'] == "FAILED":
            bot.send_message(message.chat.id, 'С аудио что-то пошло не так :(')
            start_command(message)
    except:
        bot.send_message(message.chat.id, 'С аудио что-то пошло не так :((')
        start_command(message)


# @bot.message_handler(func=lambda message: message.document.mime_type == 'text/plain', content_types=['document'])
# def handle_text_doc(message):
#     try:
#         file_info = bot.get_file(message.document.file_id)
#         file = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(bot_token, file_info.file_path))
#         for line in file.content:
#             for el in line.strip().split(','):
#                 if el.strip() == '' or el.strip() == 'Выход из режима "Я в магазине"' or el.strip() == 'Выход' or el.strip() == '/start' or el.strip() == '/help':
#                     pass
#                 else:
#                     bot.send_message(message.from_user.id, el)
#                     start_command(message)
#     except:
#         bot.send_message(message.chat.id, 'Что-то пошло не так :(')
#         start_command(message)

####################################################################

# добавление покупки в список
def add_purchase(msg):

    # сформировать список покупок для вставки
    # TO DO: посчитать число вставляемых покупок и подобрать окончание слов Покупка добавлена
    insert_list = list()
    # insert_tuple = tuple()
    # purchase_count = 0
    for el in msg.text.strip().split(','):
        if el.strip() == '' or el.strip() == 'Выход из режима "Я в магазине"' or el.strip() == 'Выход' or el.strip() == '/start' or el.strip() == '/help':
            pass
        else:
            insert_tuple = (msg.from_user.id, el.strip())
            insert_list.append(insert_tuple)
    if len(insert_list) == 0:
        bot.send_message(msg.chat.id, 'Нет покупок для добавления')
        start_command(msg)
    else:
        with sqlite3.connect('purchase_lists.db') as con:
            cursor = con.cursor()
            try:
                cursor.executemany('INSERT INTO purchase_list (user_id, purchase_nm) VALUES (?, ?)',
                                   insert_list ) # (msg.from_user.id, msg.text.strip()))
                con.commit()

                bot.send_message(msg.chat.id, 'Покупка добавлена')
                start_command(msg, 'Что-нибудь еще?')
            except:
                bot.send_message(msg.chat.id, 'Что-то пошло не так :(')
                start_command(msg)

# удаление покупки из списка
def delete_purchases(msg):
    if(is_list_empty(msg)):
        bot.send_message(msg.chat.id, 'В списке пока нет покупок')
        start_command(msg, 'Что-нибудь еще?')
    else:
        markup = types.ReplyKeyboardMarkup(row_width=2)
        with sqlite3.connect('purchase_lists.db') as con:
            cursor = con.cursor()
            cursor.execute('SELECT distinct purchase_nm FROM purchase_list WHERE user_id=={}'.format(msg.from_user.id))
            purchases = cursor.fetchall()
            for purch in purchases:
                markup.add(types.KeyboardButton(purch[0]))
            msg = bot.send_message(msg.from_user.id,
                                   text = 'Выберите покупку для удаления из списка',
                                   reply_markup=markup)
            bot.register_next_step_handler(msg, delete_purchase)

# проверка есть ли покупка в списке
def is_purch_in_list(msg):
    with sqlite3.connect('purchase_lists.db') as con:
        cursor = con.cursor()
        cursor.execute('SELECT count(*) AS purch_count FROM purchase_list WHERE user_id==? AND purchase_nm==?', (msg.from_user.id, msg.text))
        purch_count = cursor.fetchall()[0][0]
        if purch_count == 0:
            return 0
        else:
            return 1

def delete_purchase(msg):
    # такой покупки нет в списке
    if(not is_purch_in_list(msg)):
        bot.send_message(msg.chat.id, 'Такой покупки нет в списке')
        start_command(msg, 'Что-нибудь еще?')
    else:
        with sqlite3.connect('purchase_lists.db') as con:
            cursor = con.cursor()
            cursor.execute('DELETE FROM purchase_list WHERE user_id==? AND purchase_nm==?', (msg.from_user.id, msg.text))
            bot.send_message(msg.chat.id, 'Покупка удалена из списка')
            start_command(msg, 'Что-нибудь еще?')


# взято с семинара - форматирование вывода списка
def puchase_list_2_string(purchases):
    output_str = []
    for val in list(enumerate(purchases)):
        output_str.append(str(val[0] + 1) + ') ' + val[1][0] + '\n')
    return ''.join(output_str)

def show_list(msg):
    # в списке нет покупок
    if(is_list_empty(msg)):
        bot.send_message(msg.chat.id, 'В списке пока нет покупок')
        start_command(msg, 'Что-нибудь еще?')
    else:
        # в списке есть покупки
        with sqlite3.connect('purchase_lists.db') as con:
            cursor = con.cursor()
            cursor.execute('SELECT purchase_nm FROM purchase_list WHERE user_id=={}'.format(msg.from_user.id))
            purchases = puchase_list_2_string(cursor.fetchall())
            bot.send_message(msg.chat.id, purchases)
            start_command(msg, 'Что-нибудь еще?')


def clear_list(msg):
    # TO DO: добавить запрос подтверждеия Да\Нет на очистку
    if(is_list_empty(msg)):
        bot.send_message(msg.chat.id, 'В списке пока нет покупок')
        start_command(msg, 'Что-нибудь еще?')
    else:
        with sqlite3.connect('purchase_lists.db') as con:
            cursor = con.cursor()
            cursor.execute('DELETE FROM purchase_list WHERE user_id=={}'.format(msg.from_user.id))
            con.commit()
        bot.send_message(msg.chat.id, 'Список покупок очищен')
        start_command(msg, 'Что-нибудь еще?')

def is_list_empty(msg):
    with sqlite3.connect('purchase_lists.db') as con:
        cursor = con.cursor()
        cursor.execute('SELECT count(*) AS purch_count FROM purchase_list WHERE user_id=={}'.format(msg.from_user.id))
        purch_count = cursor.fetchall()[0][0]
        if purch_count == 0:
            return 1
        else:
            return 0

# режим Я в магазине - быстрое удаление из списка
def delete_purchase_shop_mode(msg):
    # выход из режима
    if msg.text in ('Выход из режима "Я в магазине"', 'Выход'):
        shop_mode_list.clear()
        start_command(msg, 'Что-нибудь еще?')
    else:
        # такой покупки нет в списке
        if(not is_purch_in_list(msg)):
            pass
        else:
            with sqlite3.connect('purchase_lists.db') as con:
                cursor = con.cursor()
                cursor.execute('DELETE FROM purchase_list WHERE user_id==? AND purchase_nm==?', (msg.from_user.id, msg.text))
            shop_mode_keyboard = types.ReplyKeyboardMarkup(row_width=1)
            shop_mode_keyboard.add(types.KeyboardButton('Выход из режима "Я в магазине"'))
            with sqlite3.connect('purchase_lists.db') as con:
                cursor = con.cursor()
                cursor.execute('SELECT distinct purchase_nm FROM purchase_list WHERE user_id=={}'.format(msg.from_user.id))
                purchases = cursor.fetchall()
                for purch in purchases:
                    shop_mode_keyboard.add(types.KeyboardButton(purch[0])                                )

            for el in shop_mode_list:
                if el[0] == msg.text:
                    bot.send_message(msg.from_user.id, text =('<s>'+msg.text+'</s>'), parse_mode='HTML')
                    el[1] = 1 # зачеркнуто

            msg = bot.send_message(msg.from_user.id,
                                   text = 'Отмечайте уже купленные покупки и они будут удалены из списка. Для выхода нажмите на "Выход"',
                                   reply_markup=shop_mode_keyboard
                                   )
            bot.register_next_step_handler(msg, delete_purchase_shop_mode)

def shop_mode(msg):
    if(is_list_empty(msg)):
        bot.send_message(msg.chat.id, 'В списке пока нет покупок')
        start_command(msg, 'Что-нибудь еще?')
    else:
        shop_markup = types.ReplyKeyboardMarkup(row_width=1)
        shop_markup.add(types.KeyboardButton('Выход из режима "Я в магазине"')
                        )
        with sqlite3.connect('purchase_lists.db') as con:
            cursor = con.cursor()
            cursor.execute('SELECT distinct purchase_nm FROM purchase_list WHERE user_id=={}'.format(msg.from_user.id))
            purchases = cursor.fetchall()
            for purch in purchases:
                shop_markup.add(types.KeyboardButton(purch[0])
                                )
                shop_mode_list.append([purch[0], 0])
            msg = bot.send_message(msg.from_user.id,
                                   text = 'Отмечайте уже купленные покупки и они будут удалены из списка. Для выхода нажмите на "Выход"',
                                   reply_markup=shop_markup)
            bot.register_next_step_handler(msg, delete_purchase_shop_mode)


# обработчик команд
def callback_dispacher(call):
    if call.text == 'Добавить покупку в список (чтобы не забыть ее купить)':
        msg = bot.send_message(call.chat.id,
                               text = 'Напишите название покупки.\nИли перечислите сразу несколько покупок через запятую.'
                               , reply_markup= add_purchase_reply)
        bot.register_next_step_handler(msg, add_purchase)

    elif call.text == 'Просмотреть список покупок':
        try:
            show_list(call)
        except:
            bot.send_message(call.chat.id, 'Не удалось отобразить список запланированных покупок :(')
            start_command(call, 'Что-нибудь еще?')

    elif call.text == 'Очистить весь список':
        try:
            clear_list(call)
        except:
            bot.send_message(call.chat.id, 'Что-то пошло не так :(')
            start_command(call, 'Что-нибудь еще?')

    elif call.text == 'Убрать покупку из списка (ее не нужно покупать)':
        try:
            delete_purchases(call)
        except:
            bot.send_message(call.chat.id, 'Что-то пошло не так :(')
            start_command(call, 'Что-нибудь еще?')

    elif call.text == 'Завершить сеанс':
        bot.send_message(call.chat.id,
                         text = 'Спасибо! Для начала работы выберите в меню или введите команду /start'
                         , reply_markup = remove_keyboard)

    elif call.text == 'Режим "Я в магазине" - разделаемся с этим списком!':
        try:
            shop_mode(call)
        except:
            bot.send_message(call.chat.id, 'Что-то пошло не так :(')
            start_command(call, 'Что-нибудь еще?')

    #    elif call.text == 'Добавить покупки из файла':
    #        msg = bot.send_message(call.chat.id,
    #                               text = 'Пришлите текстовый файл со списком покупок.'
    #                               , reply_markup= remove_keyboard)
    #        bot.register_next_step_handler(msg, handle_text_doc)

    elif call.text == '/start':
        start_command(call, 'Что я могу для Вас сделать?')

    elif call.text == '/help':
        help_command(call)

    elif call.text == 'Надиктовать покупки голосом (beta)':
        msg = bot.send_message(call.chat.id,
                         text = 'Пришлите голосовое сообщение и я попробую перевести его в текст и направить в чат'
                         , reply_markup = remove_keyboard)
        bot.register_next_step_handler(msg, from_voice)

    else:
        bot.send_message(call.from_user.id, 'Я Вас не понимаю :( не судите строго, я только учусь')
        start_command(call, 'Что-нибудь еще?')

if __name__ == '__main__':
    bot.infinity_polling()
