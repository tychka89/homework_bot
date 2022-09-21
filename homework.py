import logging
import os
import time

import telegram
import requests

from dotenv import load_dotenv
from exeptions import NonTokenError, NotHTTPStatusOKError
from http import HTTPStatus

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    filename='main.log',
    format='%(asctime)s, %(levelname)s, %(message)s,'
           '%(funcName)s, %(lineno)s',
    filemode='a',
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат,
    определяемый переменной окружения TELEGRAM_CHAT_ID.
    Принимает на вход два параметра:
    экземпляр класса Bot и строку с текстом сообщения."""
    try:
        posted_message = bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message)
        logger.info(f'Сообщение отправлено в Telegram: "{message}"')
        return posted_message
    except telegram.error.TelegramError as error:
        logger.error(f'Ошибка: {error}')
        raise error


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра функция получает временную метку.
    В случае успешного запроса должна вернуть ответ API,
    преобразовав его из формата JSON к типам данных Python."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    response = requests.get(url=ENDPOINT, headers=HEADERS, params=params)
    if response.status_code != HTTPStatus.OK:
        message = 'Ошибка при получении ответа с сервера'
        raise NotHTTPStatusOKError(message)
    logger.info('Соединение с сервером установлено!')
    return response.json()


def check_response(response):
    """Проверяет ответ API на корректность.
    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    Если ответ API соответствует ожиданиям,
    то функция должна вернуть список домашних работ (он может быть и пустым),
    доступный в ответе API по ключу 'homeworks'."""
    try:
        homework_list = response['homeworks']
    except KeyError as error:
        logger.error('Отсутствует ключ у homeworks')
        raise error
    except TypeError as error:
        logger.error("Ответ от API пришел не в виде словаря.")
        raise error

    try:
        homework = homework_list[0]

    except IndexError as error:
        logger.error('Список домашних работ пуст')
        raise error
    return homework


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус этой работы.
    В качестве параметра функция получает
     только один элемент из списка домашних работ.
    В случае успеха, функция возвращает
    подготовленную для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_STATUSES."""
    if 'homework_name' not in homework or 'status' not in homework:
        raise KeyError('No homework name or status at homework dict!')
    homework_name = homework['homework_name']
    homework_status = homework['status']
    try:
        verdict = HOMEWORK_STATUSES[homework_status]
    except Exception as error:
        logging.error(f'Получен неизвестный статус {error}.')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет доступность переменных окружения,
    которые необходимы для работы программы.
    Если отсутствует хотя бы одна переменная окружения
    — функция должна вернуть False, иначе — True."""
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

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homework = check_response(response)
            message = parse_status(homework)
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
