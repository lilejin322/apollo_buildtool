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
"""
support funtion of building module by cmake
"""
import os
import re
import subprocess
import shutil


from pathlib import Path
from pkg_resources import parse_version
from core.logging import get_logger

"""Environment variable to override the CMake executable"""
CMAKE_COMMAND_ENVIRONMENT_VARIABLE = "CMAKE_COMMAND"
"""Environment variable to override the CTest executable"""
CTEST_COMMAND_ENVIRONMENT_VARIABLE = "CTEST_COMMAND"
"""Global variable for the cached CMake version"""
_cached_cmake_version = None
logger = get_logger("apollo")

CMAKE_VARS = dict()

def which_executable(environment_variable, executable_name):
    """
    Determine the path of an executable.

    An environment variable can be used to override the location instead of
    relying on searching the PATH.

    :param str environment_variable: The name of the environment variable
    :param str executable_name: The name of the executable
    :rtype: str
    """
    value = os.getenv(environment_variable)
    if value:
        return value
    return shutil.which(executable_name)


CMAKE_EXECUTABLE = which_executable(CMAKE_COMMAND_ENVIRONMENT_VARIABLE, 'cmake')
CTEST_EXECUTABLE = which_executable(CTEST_COMMAND_ENVIRONMENT_VARIABLE, 'ctest')

def get_cmake_version():
    """
    Get the CMake version.

    The function caches the result on the first invocation and reuses that on
    subsequent invocations.

    :returns: The version as reported by `CMAKE_EXECUTABLE --version`, or None
      when the version number could not be determined
    :rtype pkg_resources.extern.packaging.version.Version
    """
    global _cached_cmake_version
    if _cached_cmake_version is None:
        _cached_cmake_version = _parse_cmake_version()
    return _cached_cmake_version


def get_cmake_required_version(path):
    """
    get required version of cmakelists.txt

    param: path of cmakelists.txt
    return: version
    rtype: str
    """
    re_pattern = r"cmake_minimum_required\(VERSION *(.*)\)"
    match = re.compile(re_pattern)
    cmakelist = Path(path)
    if not cmakelist.is_file():
        return None
    with cmakelist.open("r") as f:
        content = f.read()
        match_result = match.findall(content)
        if len(match_result) < 1:
            return None
        return match_result[-1]
    

def _parse_cmake_version():
    """
    Parse the CMake version printed by `CMAKE_EXECUTABLE --version`.

    :returns: The version parsed by pkg_resources.parse_version, or None
    :rtype pkg_resources.extern.packaging.version.Version
    """
    try:
        output = subprocess.check_output(
            [CMAKE_EXECUTABLE, '--version'], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.error('Failed to determine CMake version: ' + e.output.decode())
    else:
        lines = output.decode().splitlines()
        if lines:
            # Parse just the version part of the string.
            return _parse_cmake_version_string("".join(lines))
    return None


def _parse_cmake_version_string(version_string):
    """
    Parse the given CMake version string.

    Expects strings of the form 'cmake version 3.15.1'.

    :param str version_string: The version string to parse.
    :returns: The parsed version string or None on failure to parse.
    :rtype pkg_resources.extern.packaging.version.Version
    """
    ver_re_str = r'^(?:.*\s)?(\d+\.\d+\.\d+).*'
    ver_match = re.match(ver_re_str, version_string)
    if ver_match:
        return parse_version(ver_match.group(1))
    return None


def get_variable_from_cmake_cache(path, var):
    """
    Get a variable value from the CMake cache.

    :param str path: The path of the directory contain the CMake cache file
    :param str var: The name of the variable
    :param default: The default value returned if the variable is not defined
      in the cache
    :rtype: str
    """
    value = None
    lines = _get_cmake_cache_lines(path)
    if lines is None:
        return value
    line_prefix = '%s:' % var
    for line in lines:
        if line.startswith(line_prefix):
            try:
                index = line.index('=')
            except ValueError:
                continue
            return line[index + 1:]
    return value


def get_project_name(path):
    """
    get project name in cmakelists.txt

    param: path of cmakelists.txt
    return: project name
    """
    re_pattern = r"project\((.*)\)"
    match = re.compile(re_pattern)
    cmakelist = Path(path)
    if not cmakelist.is_file():
        raise RuntimeError("%s not found" % path)
    with cmakelist.open("r") as f:
        content = f.read()
    match_result = match.findall(content)
    if len(match_result) < 1:
        return ""
    else:
        return match_result[-1]


def _get_cmake_cache_lines(path):
    cmake_cache = Path(path) / 'CMakeCache.txt'
    if not cmake_cache.exists():
        return None
    with cmake_cache.open('r') as f:
        content = f.read()
    return content.splitlines()


def get_variable_from_cmake_list(path, var):
    """
    Get a variable value from the CMakeList.

    :param str path: The path of the directory contain the CMakeList file
    :param str var: The name of the variable
    :param default: The default value returned if the variable is not defined
      in the cache
    :rtype: str
    """
    CMAKE_VARS["PROJECT_SOURCE_DIR"] = path
    CMAKE_VARS["project_source_dir"] = CMAKE_VARS["PROJECT_SOURCE_DIR"] 
    content = _get_cmake_lists_content(path)
    if content is None:
        return ""
    return _parse_cmake_list_variable_string(content, var)
    

def _get_cmake_lists_content(path):
    cmake_list = Path(path) / "CMakeLists.txt"
    if not cmake_list.exists():
        return ""
    with cmake_list.open("r") as f:
        content = f.read()
    return content


def _parse_cmake_list_variable_string(content, var):
    """
    Parse the variable value string of given cmakelist content.

    :param str content: The content of the CMakeList file
    :rtype: str 
    """
    if var in CMAKE_VARS:
        return CMAKE_VARS[var]

    line_pattern = '[setSET]\(%s +.*\)' % var
    match = re.compile(line_pattern)
    match_results = match.findall(content)
    line = ""
    if len(match_results) == 0:
        logger.warning("Variable %s is not defined in CMakeLists.txt!" \
            "Build and install may fail!" % var)
        return line
    elif len(match_results) > 1:
        logger.info("Variable %s redefine in CMakeLists.txt." \
            "Use the last instead" % var)
        line = str(match_results[-1])
    else:
        line = str(match_results[0])

    prefix_pattern = '[setSET]\(%s +[\"\']?' % var 
    match = re.compile(prefix_pattern) 
    prefix = match.findall(line)
    assert len(prefix) == 1
    line = line.replace(prefix[0], "")
    suffix_pattern = '[\"\']?\)'
    match = re.compile(suffix_pattern) 
    suffix = match.findall(line)
    assert len(suffix) == 1
    line = line.replace(suffix[0], "")
    
    variable_pattern = r"(\${1}\{{1}[a-zA-Z0-9\/_\-]*\}{1})"
    match = re.compile(variable_pattern) 
    match_results = match.findall(line)
    for result in match_results:
        var = result[result.index("{")+1: result.index("}")]
        line = line.replace(result, \
            _parse_cmake_list_variable_string(content, var))
    return line


