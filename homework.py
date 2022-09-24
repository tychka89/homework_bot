import logging
import os
import time
import sys

import telegram
import requests

from dotenv import load_dotenv
from exeptions import NonTokenError, NotHTTPStatusOKError
from exeptions import ServerError, NonHomeworkError
from http import HTTPStatus

load_dotenv()

"""logging.basicConfig(
    level=logging.INFO,
    filename='main.log',
    format='%(asctime)s, %(levelname)s, %(message)s,'
           '%(funcName)s, %(lineno)s',
    filemode='a',
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)"""

# Товарищи из когорты сказали, что лучше писать свой логгер,
# чем воевать с базовым, поэтому я переписала этот код.
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler_recorder = logging.FileHandler('main.log')
formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(message)s, %(funcName)s, %(lineno)s'
)
handler.setFormatter(formatter)
handler_recorder.setFormatter(formatter)
logger.addHandler(handler)
logger.addHandler(handler_recorder)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат.
    Чат определяется переменной окружения TELEGRAM_CHAT_ID.
    Принимает на вход два параметра:
    экземпляр класса Bot и строку с текстом сообщения.
    """
    logger.info('Начинаем отправку сообщений')
    try:
        posted_message = bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message)
        logger.info(f'Сообщение отправлено в Telegram: "{message}"')
        return posted_message
    except telegram.error.TelegramError as error:
        raise telegram.error.TelegramError(f'Ошибка: {error}')


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра функция получает временную метку.
    В случае успешного запроса должна вернуть ответ API,
    преобразовав его из формата JSON к типам данных Python.
    """
    logger.info('Пытаемся отправить запрос')
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': params
    }
    try:
        response = requests.get(**request_params)
    except Exception as error:
        raise ServerError(f'Ошибка при запросе к эндпоинту: {error}')
    if response.status_code != HTTPStatus.OK:
        message = f'''Ошибка при получении ответа с сервера:
        {response.status_code}, {response.headers}, {response.text}'''
        raise NotHTTPStatusOKError(message)
    logger.info('Соединение с сервером установлено!')
    return response.json()


def check_response(response):
    """Проверяет ответ API на корректность.
    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    Если ответ API соответствует ожиданиям,
    то функция должна вернуть список домашних работ (он может быть и пустым),
    доступный в ответе API по ключу 'homeworks'.
    """
    try:
        homework_list = response['homeworks']
    except KeyError:
        raise KeyError('Отсутствует ключ у homeworks')
    except TypeError:
        raise TypeError("Ответ от API пришел не в виде словаря.")
    try:
        homework = homework_list[0]
    except IndexError:
        raise IndexError('Список домашних работ пуст')
    return homework


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает
     только один элемент из списка домашних работ.
    В случае успеха, функция возвращает
    подготовленную для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_STATUSES.
    """
    if homework is None:
        raise NonHomeworkError('Домашнаяя работа отсутствует')
    if 'homework_name' not in homework or 'status' not in homework:
        raise KeyError('Отсутствует имя или статус домашней работы')
    homework_name = homework['homework_name']
    homework_status = homework['status']
    try:
        verdict = VERDICTS[homework_status]
    except Exception as error:
        logging.error(f'Получен неизвестный статус {error}.')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет доступность переменных окружения, необходимые для программы.
    Если отсутствует хотя бы одна переменная окружения
    — функция должна вернуть False, иначе — True.
    """
    environment_variables = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    for key, value in environment_variables.items():
        if value in ('', None, False):
            logger.critical(f'Отсутствует токен: {key}')
            return False
        return True


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        message = 'Отсутствуют токены'
        logger.critical(message)
        raise NonTokenError(message)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    current_report = None
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homework = check_response(response)
            message = parse_status(homework)
            prev_report = current_report
            current_report = message
            if current_report != prev_report:
                logger.debug(message)
                send_message(bot, message)
                current_timestamp = int(time.time())
                time.sleep(RETRY_TIME)
        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logger.error(error_message)
            send_message(bot, error_message)
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
