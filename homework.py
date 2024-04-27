import logging
import os
import sys
import time
from http import HTTPStatus
import requests
import telegram
from dotenv import load_dotenv

load_dotenv()

PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RETRY_PERIOD = int(os.getenv("RETRY_TIME", 600))
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}

HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    logging.debug(f"Отправка боту: {bot} сообщения: {message}")
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
        logging.debug("Успешная отправка сообщения в Telegram")
    except telegram.error.TelegramError as error:
        logging.error(f"Ошибка при отправке сообщения: {error}")
        raise telegram.error.TelegramError


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    params = {"from_date": timestamp}
    logging.debug(f"{ENDPOINT}, headers {HEADERS}, params{params}, timeout=5")
    try:
        homework_status = requests.get(
            ENDPOINT, headers=HEADERS, params=params, timeout=5
        )
    except requests.RequestException as error:
        raise ConnectionError(f"Ошибка при запросе к API: {error}")
    status_code = homework_status.status_code
    if status_code != HTTPStatus.OK:
        raise ConnectionError(f"Ответ сервера: {status_code}")
    return homework_status.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    logging.debug(f"Начинается проверка ответа API: {response}")
    if not isinstance(response, dict):
        raise TypeError("Данные приходят не в виде словаря")
    if "homeworks" not in response:
        raise KeyError("Нет ключа 'homeworks'")
    if "current_date" not in response:
        raise KeyError("Нет ключа 'current_date'")
    if not isinstance(response["homeworks"], list):
        raise TypeError("Данные приходят не в виде списка")
    return response.get("homeworks")


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус."""
    logging.debug("Начали парсинг статуса")
    homework_name = homework.get("homework_name")
    if not homework_name:
        raise KeyError("Нет ключа 'homework_name'")
    status = homework.get("status")
    if not status:
        raise KeyError("Нет ключа 'status'")
    verdict = HOMEWORK_VERDICTS.get(status)
    if not verdict:
        raise KeyError("API домашки возвращает недокументированный статус")
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_message(bot, message, previous_message):
    """Функция отправляет сообщение боту, если оно изменилось."""
    if message != previous_message:
        send_message(bot, message)
    else:
        logging.debug("Повтор сообщения, не отправляется боту")
    return message


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical("Отсутствует токен")
        sys.exit()
    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
    except Exception as error:
        logging.critical(f"Ошибка при создании экземпляра Bot(): {error}")
        sys.exit()

    timestamp = int(time.time())
    previous_message = ""
    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get("current_date", timestamp)
            homework = check_response(response)
            if homework:
                message = parse_status(homework[0])
                previous_message = check_message(bot, message,
                                                 previous_message)
            else:
                logging.debug("Нет новых данных")
        except ConnectionError as error:
            message = f"Ошибка соединения: {error}"
            logging.exception(message)
            previous_message = check_message(bot, message, previous_message)
        except TypeError as error:
            message = f"Объект несоответствующего типа: {error}"
            logging.exception(message)
            previous_message = check_message(bot, message, previous_message)
        except Exception as error:
            message = f"Сбой в работе программы: {error}"
            logging.exception(message)
            previous_message = check_message(bot, message, previous_message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            '%(asctime)s, %(name)s, %(levelname)s, %(message)s'
        ),
    )
    main()
