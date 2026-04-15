
import requests
import time
import threading
import argparse
import json
import sys
import random # Добавляем модуль random
from collections import defaultdict

# Глобальные переменные для хранения результатов и синхронизации
all_results = []
results_lock = threading.Lock()

def make_request(url, method="GET", data=None, headers=None, timeout=10):
    """
    Отправляет один HTTP-запрос и записывает его результат.
    """
    start_time = time.time()
    status_code = None
    error = None

    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=timeout, headers=headers)
        elif method.upper() == "POST":
            if isinstance(data, dict):
                response = requests.post(url, timeout=timeout, headers=headers, json=data)
            else:
                response = requests.post(url, timeout=timeout, headers=headers, data=data)
        elif method.upper() == "PUT":
            if isinstance(data, dict):
                response = requests.put(url, timeout=timeout, headers=headers, json=data)
            else:
                response = requests.put(url, timeout=timeout, headers=headers, data=data)
        elif method.upper() == "DELETE":
            response = requests.delete(url, timeout=timeout, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        status_code = response.status_code
        # Optionally, check for non-2xx status codes as "failures"
        # if not 200 <= status_code < 300:
        #     error = f"HTTP Error: {status_code}"

    except requests.exceptions.Timeout:
        error = "Request timed out"
        status_code = "TIMEOUT"
    except requests.exceptions.ConnectionError:
        error = "Connection error"
        status_code = "CONN_ERROR"
    except requests.exceptions.RequestException as e:
        error = str(e)
        status_code = "REQ_ERROR"
    except ValueError as e:
        error = str(e)
        status_code = "SCRIPT_ERROR"
    finally:
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # Время в миллисекундах
        return {'status': status_code, 'time': response_time, 'error': error}

def thread_worker(url, num_requests_per_thread, method, data, headers, timeout, min_wait, max_wait):
    """
    Функция, которую выполняет каждый поток.
    Отправляет заданное количество запросов, добавляет результаты и делает паузы.
    """
    thread_results = []
    for _ in range(num_requests_per_thread):
        result = make_request(url, method, data, headers, timeout)
        thread_results.append(result)
        
        # Пауза для имитации пользовательского поведения
        if min_wait > 0 or max_wait > 0: # Только если заданы паузы
            wait_time = random.uniform(min_wait, max_wait)
            time.sleep(wait_time)
    
    with results_lock:
        all_results.extend(thread_results)

def run_test(url, num_requests, concurrency, method, data, headers, timeout, min_wait, max_wait):
    """
    Основная функция для запуска нагрузочного тестирования.
    """
    global all_results
    all_results = [] # Сброс результатов для нового запуска

    print(f"Запуск нагрузочного теста на: {url}")
    print(f"Всего запросов: {num_requests}, параллельных: {concurrency}")
    print(f"Метод: {method}, Таймаут: {timeout}с")
    if data:
        print(f"Данные: {data}")
    if headers:
        print(f"Заголовки: {headers}")
    if min_wait > 0 or max_wait > 0:
        print(f"Пауза между запросами (на поток): от {min_wait:.2f} до {max_wait:.2f} секунд")
    else:
        print("Паузы между запросами отключены.")
    print("-" * 40)

    start_total_time = time.time()
    threads = []

    # Распределение запросов между потоками
    requests_per_thread = num_requests // concurrency
    remaining_requests = num_requests % concurrency

    for i in range(concurrency):
        current_thread_requests = requests_per_thread
        if i < remaining_requests:
            current_thread_requests += 1

        if current_thread_requests > 0:
            thread = threading.Thread(
                target=thread_worker,
                args=(url, current_thread_requests, method, data, headers, timeout, min_wait, max_wait)
            )
            threads.append(thread)
            thread.start()

    # Ждем завершения всех потоков
    for thread in threads:
        thread.join()

    end_total_time = time.time()
    total_duration = end_total_time - start_total_time

    return all_results, total_duration

def analyze_results(results, total_duration):
    """
    Анализирует собранные результаты и выводит статистику.
    """
    total_requests = len(results)
    if total_requests == 0:
        print("Тест не сгенерировал ни одного запроса.")
        return

    successful_requests = 0
    failed_requests = 0
    response_times = []
    status_codes_count = defaultdict(int)

    for res in results:
        # Учитываем 2xx и 3xx как успешные, все остальное - ошибка или таймаут/ошибка соединения
        if res['error'] or not (200 <= res['status'] < 400):
            failed_requests += 1
        else:
            successful_requests += 1
        
        if isinstance(res['time'], (int, float)):
            response_times.append(res['time'])
        
        status_codes_count[str(res['status'])] += 1

    print("\n--- Результаты тестирования ---")
    print(f"Всего запросов: {total_requests}")
    print(f"Общая продолжительность: {total_duration:.2f} секунд")
    print(f"Запросов в секунду (RPS): {total_requests / total_duration:.2f}")
    print(f"Успешных запросов (2xx/3xx): {successful_requests}")
    print(f"Неуспешных запросов (ошибки/не 2xx/3xx): {failed_requests}")
    print(f"Процент ошибок: {(failed_requests / total_requests) * 100:.2f}%")

    if response_times:
        response_times.sort()
        print(f"Минимальное время ответа: {min(response_times):.2f} ms")
        print(f"Максимальное время ответа: {max(response_times):.2f} ms")
        print(f"Среднее время ответа: {(sum(response_times) / len(response_times)):.2f} ms")
        
        # Процентили
        p50 = response_times[int(len(response_times) * 0.5)] if len(response_times) > 0 else 0
        p90 = response_times[int(len(response_times) * 0.9)] if len(response_times) > 0 else 0
        p95 = response_times[int(len(response_times) * 0.95)] if len(response_times) > 0 else 0
        p99 = response_times[int(len(response_times) * 0.99)] if len(response_times) > 0 else 0
        print(f"P50 Время ответа: {p50:.2f} ms")
        print(f"P90 Время ответа: {p90:.2f} ms")
        print(f"P95 Время ответа: {p95:.2f} ms")
        print(f"P99 Время ответа: {p99:.2f} ms")
    else:
        print("Нет данных о времени ответа (все запросы могли быть ошибочными).")

    print("\nРаспределение кодов статуса HTTP:")
    for code, count in sorted(status_codes_count.items()):
        print(f"  {code}: {count} ({count / total_requests * 100:.2f}%)")

def parse_arguments():
    """
    Парсит аргументы командной строки.
    """
    parser = argparse.ArgumentParser(
        description="Скрипт для нагрузочного тестирования HTTP-сервера.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "-u", "--url", required=True,
        help="URL, который нужно протестировать (например, http://example.com/api/data)"
    )
    parser.add_argument(
        "-n", "--requests", type=int, default=100,
        help="Общее количество запросов, которое нужно сделать (по умолчанию: 100)"
    )
    parser.add_argument(
        "-c", "--concurrency", type=int, default=10,
        help="Количество параллельных пользователей/потоков (по умолчанию: 10)"
    )
    parser.add_argument(
        "-t", "--timeout", type=int, default=10,
        help="Таймаут запроса в секундах (по умолчанию: 10)"
    )
    parser.add_argument(
        "-m", "--method", default="GET", choices=["GET", "POST", "PUT", "DELETE"],
        help="HTTP-метод для использования (по умолчанию: GET)"
    )
    parser.add_argument(
        "-d", "--data",
        help="""Данные для POST/PUT запросов.
Если это JSON, используйте формат: '{"key": "value", "number": 123}'
Если это обычная строка, используйте: 'some plain text data'
"""
    )
    parser.add_argument(
        "-H", "--headers",
        help="""Пользовательские HTTP-заголовки в формате JSON:
'{"Content-Type": "application/json", "Authorization": "Bearer TOKEN"}'
"""
    )
    parser.add_argument(
        "--min-wait", type=float, default=0.0,
        help="Минимальное время паузы между запросами в секундах для каждого потока (по умолчанию: 0.0)"
    )
    parser.add_argument(
        "--max-wait", type=float, default=0.0,
        help="Максимальное время паузы между запросами в секундах для каждого потока (по умолчанию: 0.0)"
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()

    if args.min_wait < 0 or args.max_wait < 0:
        print("Ошибка: --min-wait и --max-wait не могут быть отрицательными.")
        sys.exit(1)
    if args.min_wait > args.max_wait:
        print("Ошибка: --min-wait не может быть больше --max-wait.")
        sys.exit(1)

    request_data = None
    if args.data:
        try:
            request_data = json.loads(args.data) # Попытка парсить как JSON
        except json.JSONDecodeError:
            request_data = args.data # Если не JSON, используем как обычную строку
            print(f"Предупреждение: --data не является корректным JSON, будет отправлено как обычная строка: '{args.data}'")
        except TypeError:
             print("Ошибка: --data должно быть строкой.")
             sys.exit(1)


    request_headers = None
    if args.headers:
        try:
            request_headers = json.loads(args.headers)
        except json.JSONDecodeError:
            print("Ошибка: --headers должно быть корректной JSON-строкой. Пример: '{\"Content-Type\": \"application/json\"}'")
            sys.exit(1)
        except TypeError:
            print("Ошибка: --headers должно быть строкой.")
            sys.exit(1)

    # Запуск теста
    results, duration = run_test(
        args.url,
        args.requests,
        args.concurrency,
        args.method,
        request_data,
        request_headers,
        args.timeout,
        args.min_wait, # Передаем новые аргументы
        args.max_wait  # Передаем новые аргументы
    )

    # Анализ и вывод результатов
    analyze_results(results, duration)
