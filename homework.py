import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

from exceptions import APIerror

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

FORMATTER = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    bot.send_message(TELEGRAM_CHAT_ID, message)


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except Exception as error:
        raise APIerror(
            f'Недоступен эндпоинт {ENDPOINT}. {error}',
            exc_info=True
        )
    if response.status_code != HTTPStatus.OK:
        raise ConnectionError(
            f'Статус ответа сервера не равен {HTTPStatus.OK}',
            exc_info=True
        )
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Некорректный тип данных в ответе API', exc_info=True)
    elif 'code' in response:
        logger.critical('Учетные данные не были предоставлены API',
                        exc_info=True)
    elif 'homeworks' not in response or 'current_date' not in response:
        raise ValueError('Отсутствуют ожидаемые ключи {homeworks}'
                         'и {current_date} в ответе API', exc_info=True)
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Некорректный тип данных в ответе API по ключу'
                        '{homeworks}', exc_info=True)
    return homeworks


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус."""
    if 'homework_name' not in homework or 'status' not in homework:
        message = 'Отсутствуют ключи в ответе API'
        raise APIerror(message)
    homework_name = homework.get('homework_name')
    if homework.get('status') not in HOMEWORK_VERDICTS:
        raise ValueError('Недокументированный статус домашней работы')
    verdict = HOMEWORK_VERDICTS[homework.get('status')]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    tokens_available = check_tokens()
    if not tokens_available:
        logger.critical('Отсутствует обязательная переменная окружения. '
                        'Программа принудительно остановлена.', exc_info=True)
        sys.exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    previous_message = ''
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if homeworks is None or len(homeworks) == 0:
                logger.debug('В ответе отсутствуют новые статусы')
                continue
            message = parse_status(homeworks[0])
            if message != previous_message:
                send_message(bot, message)
                logger.info(f'Бот отправил сообщение: "{message}"')
                previous_message = message
            current_timestamp = response.get('current_date')

        except Exception as error:
            message = 'Сбой в работе программы'
            logger.error(f'{message}. {error}')
            if message != previous_message:
                send_message(bot, message)
                logger.info(f'Бот отправил сообщение: "{message}"',
                            exc_info=True)
                previous_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s, %(name)s, %(levelname)s, %(message)s',
        filename='homework.log',
        encoding='UTF-8'
    )
    logger = logging.getLogger(__name__)
    console_handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(console_handler)
    console_handler.setFormatter(FORMATTER)
    main()
