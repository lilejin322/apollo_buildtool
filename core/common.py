# !/usr/bin/env python3
###############################################################################
# Copyright 2019 The Apollo Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
###############################################################################
"""bazel configuration function set"""
import hashlib
import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from jinja2.ext import Extension
import os
from configparser import ConfigParser
from core.logging import get_logger

logger = get_logger('buildtool')

root = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
cwd = os.getcwd()

CONFIG = ConfigParser()
CONFIG.read(os.path.join(root, "config/module.conf"))

if os.path.isfile(os.path.expanduser('~/.apollo/buildtool/config')):
    CONFIG.read(os.path.expanduser('~/.apollo/buildtool/config'))

if os.path.isfile(os.path.join(cwd, '.buildtool.conf')):
    CONFIG.read(os.path.join(cwd, '.buildtool.conf'))


def get_setup():
    """get setup"""
    with open(os.path.join(root, "setup.sh"), "r") as f:
        content = f.read()
    return content


def get_config(section, key):
    """Get the config stored in .conf of config_path."""
    global CONFIG
    return CONFIG.get(section, key)


def get_template(template_name):
    """get the template content"""
    template_wrapper = Path(root) / "data" / \
        "templates" / "{}".format(template_name)
    content = None
    if not template_wrapper.exists():
        return content
    with template_wrapper.open("r") as f:
        content = f.read()
    return content


def get_example():
    """get example component name and path"""
    example_name = ["example_components", "example_lib"]
    return [
        os.path.join(root, "data", "templates", example_name[0]),
        os.path.join(root, "data", "templates", example_name[1])
    ], example_name


def get_root():
    """return buildtool root dir"""
    return root


def get_str_md5(value):
    """get_str_md5"""
    return hashlib.md5(value.encode('utf8')).hexdigest()


def read_json_file(file_path):
    """read_json_file"""
    try:
        with open(file_path) as f:
            return json.load(f)
    except Exception as ex:
        return


def write_json_file(file_path, data):
    """write_json_file"""
    try:
        if not os.path.exists(os.path.dirname(file_path)):
            os.makedirs(os.path.dirname(file_path))
        with open(file_path, 'w') as wf:
            return json.dump(data, wf)
    except Exception as ex:
        return


def format_namespace_for_template(namespace):
    """format_namespaces_for_template"""
    if namespace:
        return "::".join(namespace) + "::"
    else:
        return ""


def name_convert_to_camel(name):
    """下划线转驼峰"""
    return "".join(list(map(lambda x: x.title(), name.split('_'))))


def reverse_list(lst):
    """reverse_list"""
    if isinstance(lst, list):
        res = lst.copy()
        res.reverse()
        return res
    else:
        return lst


def generate_template(template_path, output_path, **kwargs):
    """
    generate_template
    """
    template_wrapper = Path(root) / "data" / "templates"
    env = Environment(loader=FileSystemLoader(template_wrapper),
                      extensions=["jinja2.ext.do"]
                      )
    env.filters["format_namespace"] = format_namespace_for_template
    env.filters["name_convert_to_camel"] = name_convert_to_camel
    env.filters["reverse"] = reverse_list
    template = env.get_template(template_path)
    if not os.path.exists(os.path.dirname(output_path)):
        os.makedirs(os.path.dirname(output_path))
    with open(output_path, "w+") as fn:
        content = template.render(kwargs)
        fn.write(content)
