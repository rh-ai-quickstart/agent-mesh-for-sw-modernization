
import json

import re
import yaml


def extract_json_from_string(text: str) -> dict | list | None:
    """Extracts json from given string."""
    try:
        match = re.search(r'\{.*\}|\[.*\]', text, re.DOTALL)

        return json.loads(match.group())

    except Exception:
        return None

def _str_representer(dumper, data):
    if '\n' in data:

        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')

    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

def get_as_json(obj, prefix: str ="", sep: str ="_"):
    """Flattens code metadata file."""

    items = {}

    if isinstance(obj, dict):

        for k, v in obj.items():

            items.update(get_as_json(v, f"{prefix}{sep}{k}" if prefix else k, sep))

    elif isinstance(obj, list):

        for i, v in enumerate(obj):

            items.update(get_as_json(v, f"{prefix}{sep}{i}" if prefix else str(i), sep))
    else:

        items[prefix] = obj

    return items

def flatten_code_metadata(obj):

    """Converts code metadata to a YAML string with literal block style for multiline fields."""

    yaml.add_representer(str, _str_representer)

    json_obj = get_as_json(obj)

    return yaml.dump(json_obj, default_flow_style=False, allow_unicode=True)

