# Discovering and handling tools
import logging
import pkgutil
import importlib
import inspect
from teleqwen.agent import tools

import inspect
import re
from typing import get_type_hints, get_origin, get_args, Union, Literal
import types

def python_type_to_json_type(annotation):
    origin = get_origin(annotation)

    if origin in (Union, types.UnionType):
        args = get_args(annotation)
        return list(dict.fromkeys(
            python_type_to_json_type(arg) for arg in args
        ))

    if origin is Literal:
        args = get_args(annotation)
        return python_type_to_json_type(type(args[0]))

    if origin in (list, tuple):
        return "array"

    if origin is dict:
        return "object"

    return {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }.get(annotation, "string")


def function_to_schema(func):
    signature = inspect.signature(func)
    hints = get_type_hints(func)
    doc = inspect.getdoc(func) or ""

    # Description before Args:
    description = doc.split("Args:")[0].strip()

    # Extract argument descriptions
    arg_descriptions = {}

    if "Args:" in doc:
        args_section = doc.split("Args:", 1)[1]

        for line in args_section.splitlines():
            match = re.match(r"^\s*(\w+):\s*(.+)", line)
            if match:
                arg_descriptions[match.group(1)] = match.group(2)

    properties = {}
    required = []

    for name, param in signature.parameters.items():
        annotation = hints.get(name, str)

        prop = {
            "type": python_type_to_json_type(annotation),
            "description": arg_descriptions.get(name, "")
        }

        if get_origin(annotation) is Literal:
            prop["enum"] = list(get_args(annotation))

        properties[name] = prop

        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            prop["default"] = param.default

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }

def discover_tools():
    # contains the name of the function and a reference to the function itself
    registry = {}
    # list of dictionaries that describe functions, used to inform Qwen about which tools are available and how to use them
    schemas = []

    for module_info in pkgutil.iter_modules(tools.__path__):
        module = importlib.import_module(
            f"{tools.__name__}.{module_info.name}"
        )

        for name, func in inspect.getmembers(module, inspect.isfunction):
            if func.__module__ != module.__name__:
                continue
            registry[name] = func
            schemas.append(function_to_schema(func))

    return registry, schemas

class ToolRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        logging.info("Initializing ToolRegistry")

        self.registry, self.tools = discover_tools()
        self._initialized = True

    def execute(self, name: str, arguments: dict):
        if name not in self.registry:
            raise ValueError(f"Unknown tool: {name}")

        func = self.registry[name]
        return func(**arguments)