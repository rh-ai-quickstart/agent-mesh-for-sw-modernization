from jsonpath_ng import jsonpath, parse

from github import Github


def get_file_extensions_for_language(language):
    mappings = {
        "java":           [".java", ".kt"],
        "python":         [".py", ".pyi"],
        "c++":            [".c", ".h", ".i", ".C", ".cpp", ".cc", ".cxx"],
        "c":              [".c", ".h", ".i", ".C", ".cpp", ".cc", ".cxx"],
        "javascript":     [".js", ".ts"],
        "sql":            [".sql"],
        "ruby":           [".rb"],
        "shell":          [".sh"],
        "ansible":        [".yaml", ".yml"],
        "terraform":      [".tf", ".tfvars"],
        "cloudformation": [".yaml", ".yml", ".json", ".template"],
        "puppet":         [".pp", ".epp"],
    }

    if language not in mappings:
        raise ValueError(f"Language={language} has not been mapped")

    return mappings.get(language)


def get_config_file_extensions_for_language(language):
    mappings = {
        "java":       [".xml", ".gradle", ".properties", ".yaml", ".yml", ".json"],
        "python":     [".cfg", ".toml", ".ini", ".txt"],
        "c++":        [".cmake", ".mk"],
        "c":          [".cmake", ".mk"],
        "javascript": [".json", ".yaml", ".yml"],
        "typescript": [".json", ".yaml", ".yml"],
        "sql":        [".yaml", ".yml", ".json", ".ini"],
        "ruby":       [".gemspec", ".yaml", ".yml"],
        "shell":      [".env", ".conf", ".cfg"],
    }

    language = language.strip().lower()

    if language not in mappings:
        raise ValueError(f"Language={language} has not been mapped")

    return mappings[language]


def get_comment_delimiters_for_file_extension(file_extension):
    mappings = {
        ".xml":        ("<!--", "-->"),
        ".gradle":     ("/*", "*/"),
        ".properties": ("#", ""),
        ".yaml":       ("#", ""),
        ".yml":        ("#", ""),
        ".json":       ("/*", "*/"),
        ".cfg":        ("#", ""),
        ".toml":       ("#", ""),
        ".ini":        ("#", ""),
        ".txt":        ("#", ""),
        ".cmake":      ("#", ""),
        ".mk":         ("#", ""),
        ".gemspec":    ("#", ""),
        ".env":        ("#", ""),
        ".conf":       ("#", ""),
    }

    if file_extension not in mappings:
        raise ValueError(f"File extension={file_extension} has not been mapped")

    return mappings[file_extension]


def is_large_code_file(abs_path: str, max_size: int) -> bool:
    """
    Returns True if the file at abs_path exceeds max_size bytes, False otherwise.
    """
    import os
    return os.path.getsize(abs_path) > max_size


def process_large_code_file(abs_path: str, source_path: str):
    """
    Processes a large code file.

    Currently skips large files by logging them. In the future, this can be
    extended to support chunking large files into smaller segments for
    incremental processing rather than skipping them entirely.
    """
    import os
    import logging
    rel_path = os.path.relpath(abs_path, source_path)
    logging.info(f"Skipping large file: {rel_path}")


def get_exclude_dirs_for_language(language):
    mappings = {
        "java":           {"vendor", "node_modules", ".git", "bower_components", "target", ".gradle"},
        "python":         {"vendor", "node_modules", ".git", "__pycache__", ".venv", "dist", "build"},
        "javascript":     {"vendor", "node_modules", ".git", "bower_components", "dist", "build", "coverage"},
        "sql":            {"vendor", "node_modules", ".git"},
        "shell":          {"vendor", "node_modules", ".git"},
        "ruby":           {"vendor", "node_modules", ".git", ".bundle"},
        "c++":            {"vendor", "node_modules", ".git", "build", "cmake-build-debug"},
        "c":              {"vendor", "node_modules", ".git", "build", "cmake-build-debug"},
        "ansible":        {"vendor", "node_modules", ".git"},
        "terraform":      {"vendor", "node_modules", ".git", ".terraform"},
        "cloudformation": {"vendor", "node_modules", ".git"},
        "puppet":         {"vendor", "node_modules", ".git"},
    }

    language = language.strip().lower()

    if language not in mappings:
        raise ValueError(f"Language={language} has not been mapped")

    return mappings[language]


def get_comment_delimiters_for_language(language):
    mappings = {
        "java": ("/*", "*/"),
        "python": ("\"\"\"", "\"\"\""),
        "c++": ("/*", "*/"),
        "c": ("/*", "*/"),
        "javascript": ("/*", "*/"),
        "sql": ("/*", "*/"),
        "ruby": ("=begin", "=end"),
        "shell": ("<< 'COMMENT'", "COMMENT"),
    }

    if language not in mappings:
        raise ValueError(f"Language={language} has not been mapped")

    return mappings.get(language)