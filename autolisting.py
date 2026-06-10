#!/usr/bin/env python3
import os
import sys
import pyperclip
import ctypes

# Список расширений файлов, которые нужно включить в листинг по умолчанию
DEFAULT_CODE_EXTENSIONS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.json', '.md', '.txt', '.sh', '.cpp',
                           '.c', '.h', '.dart'}


def parse_autolisting_config(config_path):
    """
    Читает файл .autolisting и возвращает mode ('include' или 'exclude') и список путей.
    Если файл не найден, возвращает None, [].
    """
    if not os.path.exists(config_path):
        return None, []

    mode = None
    patterns = []
    multiline_comment = False
    with open(config_path, 'r', encoding='utf-8') as f:
        for line in f:
            l_stripped = line.strip()

            # Обработка многострочных комментариев
            if l_stripped.startswith('||') and l_stripped.endswith('||'):
                # Однострочный многострочный комментарий? Или просто строка || ?
                # Пропускаем строку типа || ... ||
                continue
            if l_stripped.startswith('||'):
                if not multiline_comment:
                    # Начало многострочного комментария
                    multiline_comment = True
                # Пропускаем строку начала
                continue
            if l_stripped.endswith('||'):
                if multiline_comment:
                    # Конец многострочного комментария
                    multiline_comment = False
                # Пропускаем строку окончания
                continue

            if multiline_comment:
                continue

            # Обработка однострочных комментариев
            if l_stripped.startswith('|'):
                continue

            # Разделение пути и комментария после |
            parts = line.split('|', 1)  # Разбиваем только по первому |
            path_part = parts[0].strip()

            # Обработка строки mode
            if path_part.startswith('mode '):
                if mode is not None:
                    print(f"⚠️  Warning: Multiple 'mode' lines found in {config_path}. Using the first one.")
                    continue
                mode_str = path_part[len('mode '):].strip()
                if mode_str in ['include', 'exclude']:
                    mode = mode_str
                else:
                    print(f"⚠️  Warning: Invalid mode '{mode_str}' in {config_path}. Must be 'include' or 'exclude'.")
                continue

            # Пропускаем пустые строки (после удаления комментариев)
            if not path_part:
                continue

            # Просто нормализуем и добавляем строку как есть (если она не пустая после strip)
            normalized_path = normalize_path(path_part)
            if normalized_path:  # Проверяем, что после нормализации путь не пустой
                patterns.append(normalized_path)

    if mode is None:
        print(f"⚠️  Warning: No 'mode' specified in {config_path}. Defaulting to 'include'.")
        mode = 'include'

    return mode, patterns


def normalize_path(raw_path):
    """
    Нормализует путь: убирает начальные ./ или /, затем добавляет ./.
    Возвращает строку вида './dir/subdir' или './file.ext'.
    """
    p = raw_path.strip()
    if not p:
        return ""
    p = p.rstrip('/')
    # Убираем возможные лидирующие ./ или /
    if p.startswith('./'):
        p = p[2:]
    elif p.startswith('/'):
        p = p[1:]
    # Всегда добавляем ./ в начало
    return './' + p


def should_include_path(norm_path, config_mode, config_patterns):
    """
    Проверяет, должен ли путь быть включён или исключён.
    Если config_mode и config_patterns равны None и [], использует поведение по умолчанию (включить всё).
    norm_path: нормализованный путь, например './lib/main.dart'
    config_mode: 'include', 'exclude' или None
    config_patterns: список нормализованных шаблонов или []
    """
    # Если конфиг не используется (None, []), включаем всё
    if config_mode is None and not config_patterns:
        return True

    # Иначе, используем логику фильтрации
    is_match = False
    for pattern in config_patterns:
        # Проверяем, начинается ли путь с шаблона (это покрывает файлы и подпапки)
        # Например, './lib' match './lib/main.dart'
        # './lib/main.dart' match './lib/main.dart'
        if norm_path == pattern or norm_path.startswith(pattern + '/'):
            is_match = True
            break

    if config_mode == 'include':
        return is_match
    elif config_mode == 'exclude':
        return not is_match
    # Fallback, хотя mode должен быть либо include, либо exclude, либо None
    return True  # или False, но логично вернуть True как "включить по умолчанию"


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def restart_as_admin():
    """Перезапускает текущий скрипт с правами администратора и завершает текущий процесс."""
    try:
        script = os.path.abspath(sys.argv[0])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, script, None, 1
        )
        if int(ret) <= 32:
            print("⚠️  Failed to elevate privileges (UAC denied or error). Continuing without admin rights.")
            return False
        else:
            print("🔄 Restarting with admin rights...")
            sys.exit(0)  # Выходим — новая копия уже запущена
    except Exception as e:
        print(f"⚠️  Error requesting admin rights: {e}")
        return False


def get_tree_structure(startpath, config_mode, config_patterns):
    """
    Строит строковое представление дерева папок/файлов с символами ├ ├── └── │.
    Учитывает настройки из .autolisting.
    """
    tree_lines = []

    def walk(path, prefix="", current_rel_path="./"):
        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            if not is_admin():
                print(f"🔒 Access denied to '{path}'. Requesting admin rights...")
                restart_as_admin()
            tree_lines.append(f"{prefix}[ПРОПУЩЕНО - ОТКАЗАН В ДОСТУПЕ] {os.path.basename(path)}/")
            return
        except OSError as e:
            tree_lines.append(f"{prefix}[ПРОПУЩЕНО - ОШИБКА ОС] {os.path.basename(path)}/ ({e})")
            return

        folders = []
        files = []
        for entry in entries:
            full_path = os.path.join(path, entry)
            rel_path_candidate = os.path.normpath(os.path.join(current_rel_path, entry)).replace('\\', '/')
            if not rel_path_candidate.startswith('./'):
                rel_path_candidate = './' + rel_path_candidate

            # Проверяем, включать ли этот элемент
            if not should_include_path(rel_path_candidate, config_mode, config_patterns):
                continue

            if os.path.isdir(full_path):
                folders.append((entry, rel_path_candidate))
            else:
                files.append((entry, rel_path_candidate))

        entries_count = len(folders) + len(files)
        for i, (folder, rel_path) in enumerate(folders):
            is_last_folder = (i == len(folders) - 1) and (len(files) == 0)
            connector = "└── " if is_last_folder else "├── "
            tree_lines.append(f"{prefix}{connector}{folder}/")

            next_prefix = prefix + ("    " if is_last_folder else "│   ")
            walk(os.path.join(path, folder), next_prefix, rel_path)

        for j, (file, rel_path) in enumerate(files):
            is_last_file = (j == len(files) - 1)
            connector = "└── " if is_last_file else "├── "
            tree_lines.append(f"{prefix}{connector}{file}")

    start_dir_name = os.path.basename(startpath)
    tree_lines.append(f"{start_dir_name}/")
    walk(startpath, "", "./")
    return "\n".join(tree_lines)


def collect_files_content(path, all_lines=None, config_mode=None, config_patterns=None, base_root_path=None):
    """
    Рекурсивно собирает содержимое файлов с нужными расширениями.
    Содержимое файлов копируется БЕЗ изменений.
    Учитывает настройки из .autolisting.
    base_root_path - корневая директория проекта, от которой считаются относительные пути.
    """
    if all_lines is None:
        all_lines = []

    # Устанавливаем базовый корень при первом вызове
    if base_root_path is None:
        base_root_path = path

    try:
        items = sorted(os.listdir(path))
    except PermissionError:
        # Если ошибка доступа и мы уже админы — пропускаем
        if is_admin():
            print(f"⚠️  Skipping due to access denied: {path}")
            return all_lines
        # Если не админы — пробуем перезапустить
        print(f"🔒 Access denied to '{path}'. Requesting admin rights...")
        restart_as_admin()
        # Если мы здесь — значит, не удалось получить права, но продолжаем
        return all_lines
    except OSError as e:
        print(f"⚠️  Skipping due to OS error: {path}, Error: {e}")
        return all_lines

    def get_relative_path(full_path, base_path):
        # Вычисляет относительный путь от base_root_path (а не от текущей папки) к full_path и нормализует его
        rel_p = os.path.relpath(full_path, base_root_path).replace('\\', '/')
        if not rel_p.startswith('./'):
            rel_p = './' + rel_p
        return rel_p

    folders = []
    files = []

    for item in items:
        full_path = os.path.join(path, item)
        rel_path_candidate = get_relative_path(full_path, base_root_path)

        # Проверяем, включать ли этот элемент
        if not should_include_path(rel_path_candidate, config_mode, config_patterns):
            continue

        if os.path.isdir(full_path):
            folders.append((item, full_path, rel_path_candidate))
        else:
            # Проверяем расширение файла
            _, ext = os.path.splitext(item)
            if ext.lower() in DEFAULT_CODE_EXTENSIONS:
                files.append((item, full_path, rel_path_candidate))

    for file, file_path, rel_path in files:
        all_lines.append(f"\n[ФАЙЛ] {file_path}:\n")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Копируем содержимое файла БЕЗ изменений
                all_lines.append(content)
        except UnicodeDecodeError:
            all_lines.append("[ДВОИЧНЫЙ ФАЙЛ ИЛИ ОШИБКА КОДИРОВКИ - ПРОПУЩЕН]")
        except PermissionError:
            all_lines.append("[ОТКАЗАН В ДОСТУПЕ - ПРОПУЩЕН]")
        except Exception as e:
            all_lines.append(f"[ОШИБКА ЧТЕНИЯ ФАЙЛА - ПРОПУЩЕН] ({e})")

        # Добавляем маркер конца файла и два перевода строки
        all_lines.append("\n[КОНЕЦ ФАЙЛА]\n\n")

    for folder, folder_path, rel_path in folders:
        collect_files_content(folder_path, all_lines, config_mode, config_patterns, base_root_path)

    return all_lines


def main():
    current_dir = os.getcwd()
    print(f"📁 Scanning: {os.path.basename(current_dir)}/")

    # Читаем .autolisting
    config_path = os.path.join(current_dir, '.autolisting')
    config_mode, config_patterns = parse_autolisting_config(config_path)

    # --- НАЧАЛО: Генерация информации о настройках ---
    config_info_lines = []
    if config_patterns:
        config_info_lines.append("НАЙДЕН ФАЙЛ НАСТРОЕК .autolisting")
        if config_mode == 'include':
            config_info_lines.append("СЛЕДУЯ НАСТРОЙКАМ, ВСЕ ФАЙЛЫ И ПАПКИ ИСКЛЮЧЕНЫ ИЗ ЛИСТИНГА, КРОМЕ:")
        elif config_mode == 'exclude':
            config_info_lines.append("СЛЕДУЯ НАСТРОЙКАМ, ВСЕ ФАЙЛЫ И ПАПКИ ДОБАВЛЕНЫ В ЛИСТИНГ, КРОМЕ:")
        config_info_lines.extend(config_patterns)
        config_info = "\n".join(config_info_lines)
    else:
        if os.path.exists(config_path):
            print(f"⚙️  .autolisting found but no valid patterns or mode set. Using default behavior (include all).")
            config_info = "НАЙДЕН ФАЙЛ НАСТРОЕК .autolisting\nНО ФАЙЛ НЕ СОДЕРЖИТ ДЕЙСТВИТЕЛЬНЫХ НАСТРОЕК. ИСПОЛЬЗУЕТСЯ ПОВЕДЕНИЕ ПО УМОЛЧАНИЮ: ВСЕ ФАЙЛЫ И ПАПКИ ВКЛЮЧЕНЫ."
        else:
            print("⚙️  No .autolisting config found. Using default behavior (include all).")
            config_info = ""  # Не добавляем ничего в вывод, если файл не найден
    # --- КОНЕЦ: Генерация информации о настройках ---

    # Собираем структуру
    structure_output = get_tree_structure(current_dir, config_mode, config_patterns)

    # Собираем содержимое файлов
    content_lines = collect_files_content(current_dir, config_mode=config_mode, config_patterns=config_patterns,
                                          base_root_path=current_dir)
    content_output = "".join(content_lines)

    # Формируем итоговый вывод
    header_part = f"""[ЛИСТИНГ КОДА]
[АВТОМАТИЧЕСКИ СОЗДАНО С ПОМОЩЬЮ СКРИПТА AUTOLISTING]

ЛЕГЕНДА:
[СТРУКТУРА] - Дерево папок и файлов проекта
[ФАЙЛ] - Содержимое следующего файла
[КОНЕЦ ФАЙЛА] - Обозначает конец содержимого предыдущего файла


"""
    # Добавляем информацию о настройках, если она есть (после легенды)
    if config_info:
        header_part += config_info + "\n\n"

    header_part += f"""РАСПОЛОЖЕНИЕ КОРНЕВОЙ ПАПКИ: {current_dir}
[СТРУКТУРА]
{structure_output}


"""
    final_output = header_part + f"""{content_output}
"""

    # Копируем в буфер
    try:
        pyperclip.copy(final_output)
        print("\n✅ Listing copied to clipboard.")
    except Exception as e:
        print(f"\n❌ Failed to copy to clipboard: {e}")
        print("\n--- Listing (for manual copy): ---\n")
        print(final_output)


if __name__ == "__main__":
    main()