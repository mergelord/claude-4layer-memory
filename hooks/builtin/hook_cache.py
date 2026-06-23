#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hook Cache - Универсальное кэширование результатов hooks

Кэширует вывод hooks на 5 минут для экономии токенов при частых перезапусках.
"""

import json
import time
from pathlib import Path
from typing import Optional, Callable


class HookCache:
    """Кэширование результатов hooks"""

    CACHE_TTL = 300  # 5 минут

    def __init__(self, hook_name: str):
        """
        Args:
            hook_name: Имя hook для идентификации кэша
        """
        self.hook_name = hook_name
        self.cache_dir = Path.home() / ".claude" / ".cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / f"{hook_name}.json"

    def get_or_run(self, func: Callable[[], str]) -> str:
        """
        Получить результат из кэша или выполнить функцию

        Args:
            func: Функция которая возвращает результат hook

        Returns:
            Результат из кэша или свежий результат
        """
        # Проверяем кэш
        cached = self._load_cache()
        if cached is not None:
            age_seconds = int(time.time() - cached['timestamp'])
            age_minutes = age_seconds // 60
            print(f"[OK] [{self.hook_name}] Loaded from cache ({age_minutes} min ago)")
            return cached['data']

        # Выполняем функцию
        result = func()

        # Сохраняем в кэш
        self._save_cache(result)

        return result

    def _load_cache(self) -> Optional[dict]:
        """Загрузить данные из кэша если они актуальны"""
        if not self.cache_file.exists():
            return None

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            # Проверяем TTL
            if time.time() - cache['timestamp'] < self.CACHE_TTL:
                return cache

            # Кэш устарел
            return None

        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def _save_cache(self, data: str) -> None:
        """Сохранить данные в кэш"""
        try:
            cache = {
                'timestamp': time.time(),
                'data': data
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # Игнорируем ошибки записи

    def invalidate(self) -> None:
        """Инвалидировать кэш (удалить файл)"""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
        except OSError:
            pass


def cached_hook(hook_name: str):
    """
    Декоратор для кэширования результатов hook функций

    Usage:
        @cached_hook("my-hook")
        def my_hook_main():
            # ... expensive operations ...
            return output_string
    """
    def decorator(func: Callable[[], str]) -> Callable[[], str]:
        def wrapper() -> str:
            cache = HookCache(hook_name)
            return cache.get_or_run(func)
        return wrapper
    return decorator
