# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 vionya

# Generates a file from an existing config file.
#
# The file to be read as input is sys.argv[1], or "config.toml" if that doesn't exist.
# The filename is sys.argv[2], or "example_config.toml" if that doesn't exist.
# If the output filename is provided, an input filename must also be provided.
#
# The generated file contains a recursively constructed copy of the input file,
# omitting the values, and replacing them with the expected type of the value.

from __future__ import annotations

from sys import argv

import toml

INPUT_FILE = next(iter(argv[1:]), "config.toml")
OUTPUT_FILE = next(iter(argv[2:]), "config.example.toml")

ORIGINAL = toml.load("config.toml")


class PrettyListEncoder(toml.TomlEncoder):  # Dump lists with newlines
    def dump_list(self, value):
        retval = "["
        endpoint = len(value)
        for index in range(endpoint):
            item = value[index]
            lineterm = ","
            if (index + 1) == endpoint:
                lineterm = ""
            retval += "\n    " + str(self.dump_value(item)) + lineterm
        retval += "\n]"
        return retval


def generate_template(data: dict) -> dict:
    data = data.copy()  # Preserve original
    for k, v in data.items():
        if isinstance(v, dict):
            v = generate_template(v)
        elif isinstance(v, list):
            for index, value in enumerate(v):
                if isinstance(value, dict):
                    v[index] = generate_template(value)
                else:
                    v[index] = type(value).__name__
        else:
            v = type(v).__name__
        data[k] = v
    return data


dumped = toml.dumps(generate_template(ORIGINAL), encoder=PrettyListEncoder())
with open(OUTPUT_FILE, "w") as output:
    output.write("# Autogenerated by config_gen.py\n")
    output.write(dumped)
