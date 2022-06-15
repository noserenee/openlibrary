#!/usr/bin/env python
import os

root = os.path.dirname(__file__)
OVERRIDES = {'type': "Literal['work', 'author', 'subject']"}


def generate():
    """This function generates the types.py file."""
    import xml.etree.ElementTree as ET

    # read the managed-schema xml file
    solr_schema = ET.parse(os.path.join(root, '../../conf/solr/conf/managed-schema'))
    python_fields: list[str] = []
    seen_names: set[str] = set()
    for field in solr_schema.getroot().findall('field'):
        name = field.get('name')
        if name.startswith('_'):
            continue

        required = field.get('required') == 'true'
        typ = field.get('type')
        multivalued = field.get('multiValued') == 'true'
        type_map = {
            'pint': 'int',
            'string': 'str',
            'text_en_splitting': 'str',
            'text_general': 'str',
            'text_international': 'str',
            'boolean': 'bool',
        }

        if name in OVERRIDES:
            python_type = OVERRIDES[name]
        elif typ in type_map:
            python_type = type_map[typ]
        elif (
            field_type := solr_schema.find(f".//fieldType[@name='{typ}']")
        ) is not None:
            field_class = field_type.get('class')
            if field_class == 'solr.EnumFieldType':
                enumsConfigFile = field_type.get('enumsConfig')
                enumsConfig = ET.parse(
                    os.path.join(root, '../../conf/solr/conf/', enumsConfigFile)
                )
                enum_values = [
                    el.text
                    for el in enumsConfig.findall(
                        f".//enum[@name='{field_type.get('enumName')}']/value"
                    )
                ]
                python_type = f"Literal[{', '.join(map(repr, enum_values))}]"
            else:
                raise Exception(f"Unknown field type class {field_class}")
        else:
            raise Exception(f"Unknown field type {typ}")

        if name not in OVERRIDES:
            if multivalued:
                python_type = f"list[{python_type}]"
            if not required:
                python_type = f"Optional[{python_type}]"

        seen_names.add(name)
        python_fields.append(f"    {name}: {python_type}")

    for key in set(OVERRIDES) - seen_names:
        python_fields.append(f"    {key}: {OVERRIDES[key]}")

    body = '\n'.join(python_fields)
    python = f"""# This file is auto-generated by types_generator.py
# fmt: off
from typing import Literal, TypedDict, Optional


class SolrDocument(TypedDict):
{body}

# fmt: on"""

    return python


if __name__ == '__main__':
    print(generate())
