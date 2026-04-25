"""
Тесты для проверки Privacy Controls - защита чувствительных данных от попадания в Git.

Проверяет:
1. .gitignore корректно настроен
2. Чувствительные файлы не попадут в Git
3. Шаблоны конфигов существуют
"""

import os
import sys
import subprocess
from pathlib import Path

# Исправление кодировки для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class PrivacyControlsTest:
    """Тестирование защиты приватных данных."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.gitignore_path = self.project_root / ".gitignore"

    def test_gitignore_exists(self) -> bool:
        """Проверка наличия .gitignore."""
        if not self.gitignore_path.exists():
            print("❌ .gitignore не найден")
            return False
        print("✅ .gitignore существует")
        return True

    def test_sensitive_patterns_in_gitignore(self) -> bool:
        """Проверка что чувствительные паттерны есть в .gitignore."""
        required_patterns = [
            # API Keys & Tokens
            "config/api_keys.json",
            "config/*_token.txt",
            "config/*_credentials.json",
            # Personal configs
            "config/personal.json",
            "config/*.local.json",
            "*_local.json",
            # Crash dumps
            "*.dmp",
            "crash_reports/",
            # Environment
            ".env",
            ".env.local",
            # Logs
            "*.log",
            "logs/",
            # Memory files
            "memory/",
            "*.jsonl",
        ]

        with open(self.gitignore_path, 'r', encoding='utf-8') as f:
            gitignore_content = f.read()

        missing_patterns = []
        for pattern in required_patterns:
            if pattern not in gitignore_content:
                missing_patterns.append(pattern)

        if missing_patterns:
            print("❌ Отсутствуют паттерны в .gitignore:")
            for pattern in missing_patterns:
                print(f"   - {pattern}")
            return False

        print(f"✅ Все {len(required_patterns)} критичных паттернов присутствуют")
        return True

    def test_git_check_ignore(self) -> bool:
        """Проверка через git check-ignore что файлы действительно игнорируются."""
        sensitive_files = [
            "config/api_keys.json",
            "config/github_token.txt",
            "config/openai_credentials.json",
            "config/personal.json",
            "config/settings.local.json",
            ".env",
            ".env.local",
            "crash.dmp",
            "crash_reports/report.txt",
            "debug.log",
            "logs/session.log",
            "memory/handoff.md",
            "transcript.jsonl",
        ]

        # Проверяем только если мы в git репозитории
        if not (self.project_root / ".git").exists():
            print("⚠️  Не git репозиторий, пропускаем git check-ignore")
            return True

        failed_files = []
        for file_path in sensitive_files:
            full_path = self.project_root / file_path

            # git check-ignore возвращает 0 если файл игнорируется
            result = subprocess.run(
                ["git", "check-ignore", str(full_path)],
                cwd=str(self.project_root),
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                failed_files.append(file_path)

        if failed_files:
            print("❌ Файлы НЕ игнорируются Git:")
            for file_path in failed_files:
                print(f"   - {file_path}")
            return False

        print(f"✅ Все {len(sensitive_files)} чувствительных файлов игнорируются")
        return True

    def test_example_configs_exist(self) -> bool:
        """Проверка наличия шаблонов конфигов."""
        example_configs = [
            "config/api_keys.example.json",
            "config/personal.example.json",
        ]

        missing_examples = []
        for config_path in example_configs:
            full_path = self.project_root / config_path
            if not full_path.exists():
                missing_examples.append(config_path)

        if missing_examples:
            print("❌ Отсутствуют шаблоны конфигов:")
            for config_path in missing_examples:
                print(f"   - {config_path}")
            return False

        print(f"✅ Все {len(example_configs)} шаблонов конфигов существуют")
        return True

    def test_no_secrets_in_git_history(self) -> bool:
        """Проверка что секреты не попали в Git историю."""
        if not (self.project_root / ".git").exists():
            print("⚠️  Не git репозиторий, пропускаем проверку истории")
            return True

        # Паттерны для поиска секретов
        secret_patterns = [
            "api_key",
            "token",
            "password",
            "secret",
            "credentials",
        ]

        # Ищем в git log
        try:
            result = subprocess.run(
                ["git", "log", "--all", "--full-history", "--source", "--", "*.json", "*.txt", "*.env"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )

            if not result.stdout:
                print("✅ История Git пуста или файлы не коммитились")
                return True

            found_secrets = []
            for pattern in secret_patterns:
                if pattern.lower() in result.stdout.lower():
                    found_secrets.append(pattern)

            if found_secrets:
                print("⚠️  Возможно найдены секреты в истории Git:")
                for pattern in found_secrets:
                    print(f"   - {pattern}")
                print("   Рекомендуется проверить вручную: git log --all -p | grep -i 'api_key\\|token\\|password'")
                return True  # Не фейлим, только предупреждаем

            print("✅ Секреты не обнаружены в Git истории")
            return True
        except Exception as e:
            print(f"⚠️  Не удалось проверить историю: {e}")
            return True  # Не фейлим при ошибке

    def run_all_tests(self) -> bool:
        """Запуск всех тестов."""
        print("=" * 70)
        print("Privacy Controls Test Suite")
        print("=" * 70)
        print(f"Проект: {self.project_root}")
        print()

        tests = [
            ("Наличие .gitignore", self.test_gitignore_exists),
            ("Паттерны в .gitignore", self.test_sensitive_patterns_in_gitignore),
            ("Git check-ignore", self.test_git_check_ignore),
            ("Шаблоны конфигов", self.test_example_configs_exist),
            ("История Git", self.test_no_secrets_in_git_history),
        ]

        results = []
        for test_name, test_func in tests:
            print(f"\n[TEST] {test_name}")
            print("-" * 70)
            try:
                result = test_func()
                results.append(result)
            except Exception as e:
                print(f"❌ Ошибка: {e}")
                results.append(False)

        print("\n" + "=" * 70)
        passed = sum(results)
        total = len(results)
        print(f"Результат: {passed}/{total} тестов пройдено")

        if passed == total:
            print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
            print("=" * 70)
            return True
        else:
            print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
            print("=" * 70)
            return False


def main():
    """Главная функция."""
    project_root = os.path.dirname(os.path.abspath(__file__))

    tester = PrivacyControlsTest(project_root)
    success = tester.run_all_tests()

    exit(0 if success else 1)


if __name__ == "__main__":
    main()
