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
"""request metadata"""
import shutil
import subprocess
import requests
import json
import hashlib
import os
import xml.etree.ElementTree as ET

from functools import cmp_to_key
from pkg_resources import parse_version
from pathlib import Path
from core import ErrCode, get_token, get_arch, get_codename
from core.version_decide.semver import Version
from core.common import get_config, get_logger
from core.action import apollo_prefix
from core.package_identification.identifier import singleton
from core.task.bazel.handler import Procedure

logger = get_logger('buildtool')


@singleton
class MetaDataCli(object):
    def __init__(self, ignore_error=False):
        self.headers = {
            "Host": "apollo.baidu.com",
            'Authorization': 'Bearer {}'.format(get_token())
        }
        self.recache = False
        self.ignore_error = ignore_error
        self.offline_packages_filename = get_config("cache", "offline_packages_filename")
        self.offline_cyberfile_cache_filename = get_config("cache", "offline_cyberfile_cache_filename")
        self.running = False
        self.raw_metadata_pool = dict()
        self.raw_version_pool = dict()
        self.raw_cyberfile_path_pool = dict()
        self.raw_cyberfile_pool = dict()
        self.cyberfile_source = dict()
        self.procedure = Procedure()
        self.online = self.procedure.get_network_status()

    def get_recached_flags(self):
        """confirm it's recached or not"""
        return self.recache

    def run(self, repositories):
        """run the singleton"""
        if not self.running:
            self.running = True
            self.repositories = repositories
            self._init_metadata()

    def _init_metadata(self):
        raw_metadatas = None

        if self.online:
            arch = get_arch()
            codename = get_codename()

            request_url_base = get_config("api", "meta_api")
            metadata_request_url = "{}?repo_name={}&arch={}&codename={}".format(
                request_url_base, ",".join([i.name for i in self.repositories]),
                arch, codename
            )
            meta_resp = requests.get(
                url=metadata_request_url, headers=self.headers)
            if meta_resp.status_code != 200:
                ErrCode.send_error(ErrCode.NetworkIoError, [
                    "Request packages metadata failed! Status code={}".format(
                        meta_resp.status_code)])
            meta_resp_json = meta_resp.json()
            # assume return {
            #     "core": {"packages": packages_content, "cyberfiles": cyberfile_content},
            #     "universe": {"packages": packages_content, "cyberfiles": cyberfile_content}
            # }
            for repo in meta_resp_json:
                prefix = os.path.join(get_config("cache", "offline_metadata_prefix"), repo)
                os.makedirs(prefix, exist_ok=True)
                packages_path = os.path.join(prefix, self.offline_packages_filename)
                cyberfiles_path = os.path.join(prefix, self.offline_cyberfile_cache_filename)
                if "packages" not in meta_resp_json[repo] or \
                        "cyberfiles" not in meta_resp_json[repo]:
                    if not self.ignore_error:
                        ErrCode.send_error(ErrCode.NetworkIoError,
                                           ["Unauthorized access repository {}".format(repo)],
                                           ["Please use login command to access this repository"])
                    else:
                        exit(0)

                if not self.recache:
                    if not os.path.exists(packages_path) or not os.path.exists(packages_path):
                        self.recache = True
                    else:
                        with open(packages_path, "r") as f:
                            cached_packages = f.read()
                        with open(cyberfiles_path, "r") as f:
                            cached_cyberfiles = f.read()
                        if cached_packages != meta_resp_json[repo]["packages"] or \
                                cached_cyberfiles != meta_resp_json[repo]["cyberfiles"]:
                            self.recache = True

                with open(packages_path, "w+") as f:
                    f.write(meta_resp_json[repo]["packages"])

                with open(cyberfiles_path, "w+") as f:
                    f.write(meta_resp_json[repo]["cyberfiles"])
        else:
            for repo in self.repositories:
                prefix = os.path.join(get_config("cache", "offline_metadata_prefix"), repo.name)
                packages_path = os.path.join(prefix, self.offline_packages_filename)
                cyberfiles_path = os.path.join(prefix, self.offline_cyberfile_cache_filename)

                if not os.path.exists(packages_path) or not os.path.exists(cyberfiles_path):
                    ErrCode.send_error(ErrCode.FileIoErr,
                                       ["please use offline mode after initialize metadata"])

        for repo in self.repositories:
            self.raw_metadata_pool[repo.name] = dict()
            self.raw_version_pool[repo.name] = dict()
            self.raw_cyberfile_path_pool[repo.name] = dict()
            self.raw_cyberfile_pool[repo.name] = dict()
            self.cyberfile_source[repo.name] = dict()

            prefix = os.path.join(get_config("cache", "offline_metadata_prefix"), repo.name)
            packages_path = os.path.join(prefix, self.offline_packages_filename)
            cyberfiles_path = os.path.join(prefix, self.offline_cyberfile_cache_filename)
            with open(packages_path, "r") as f:
                raw_metadatas = f.read()

            raw_metadata_list = raw_metadatas.split("\n\n")

            # parse metadata
            for i in raw_metadata_list:
                if i == "":
                    continue
                terms = i.split("\n")
                terms_dict = dict()
                for term in terms:
                    k, v = term.split(":")[0], term.split(":")[1]
                    terms_dict[k] = v

                if terms_dict["Package"].strip() in self.raw_metadata_pool[repo.name]:
                    self.raw_metadata_pool[repo.name][
                        terms_dict["Package"].strip()].append(terms_dict)
                else:
                    self.raw_metadata_pool[repo.name][
                        terms_dict["Package"].strip()] = [terms_dict]

            for _, name in enumerate(self.raw_metadata_pool[repo.name]):
                # parse cyberfile path
                self.raw_cyberfile_path_pool[repo.name][name] = [
                    name for i in self.raw_metadata_pool[repo.name][name]
                ]

            self._register_local_package(repo)
            local_package_in_repo = []
            for _, name in enumerate(self.raw_metadata_pool[repo.name]):
                # parse version
                version_str = [i["Version"].strip() for i in self.raw_metadata_pool[repo.name][name]]
                versions = [parse_version(i["Version"].strip()) for i in self.raw_metadata_pool[repo.name][name]]

                if name in self.local_package_pool and \
                        self.local_package_pool[name]["repository"] == repo.name and \
                        self.local_package_pool[name]["version"].strip() not in version_str:
                    local_package_in_repo.append(name)
                    version_str.append(self.local_package_pool[name]["version"].strip())
                    versions.append(parse_version(self.local_package_pool[name]["version"].strip()))

                version_dict = {}
                for i in range(len(versions)):
                    version_dict[versions[i]] = version_str[i]
                versions.sort()

                self.raw_version_pool[repo.name][name] = [
                    Version.parse(version_dict[i]) for i in versions
                ]

            self._cached_all_cyberfile(repo.name, local_package_in_repo)

    def _register_local_package(self, repo):
        self.local_package_pool = {}
        package_meta_path = os.path.join(
            get_config("base", "apollo_root"), get_config("base", "package_meta_prefix"))
        if not os.path.exists(package_meta_path):
            return
        for pkg in os.listdir(package_meta_path):
            cyberfile = os.path.join(package_meta_path, pkg, "cyberfile.xml")
            if not os.path.exists(cyberfile):
                continue
            pkg = self.change_package_name(pkg)
            ns_location = None
            ns_version = None

            if pkg in self.raw_cyberfile_path_pool[repo.name]:
                ns_location = repo.name
                ns_version = repo.version

            # igonre non apollo package
            if ns_location is not None:
                try:
                    root = ET.parse(cyberfile).getroot()
                    pkg_version = root.find("version").text
                except Exception as ex:
                    logger.warning(f"Parse meta of {pkg} failed: {str(ex)}")
                    continue
                if pkg_version != "local":
                    self.local_package_pool[pkg] = {
                        "version": pkg_version,
                        "repository": ns_location,
                        "cyberfile": ET.tostring(root, encoding="utf-8").decode("utf-8")
                    }
                else:
                    # Set the package version number to the repository specified version 
                    # to avoid version leveling failures
                    root.find("version").text = ns_version
                    if not (ns_version[0].isdigit()):
                        ns_version = self._get_latest_version_before_merge(ns_location, "cyber")
                    cyberfile_content = ET.tostring(root, encoding="utf-8").decode("utf-8")
                    self.local_package_pool[pkg] = {
                        "version": ns_version,
                        "repository": ns_location,
                        "cyberfile": cyberfile_content
                    }

    def _get_latest_version_before_merge(self, repo_name, package_name):
        package_name = self.change_package_name(package_name)
        version_str = [i["Version"].strip() for i in self.raw_metadata_pool[repo_name][package_name]]
        versions = [parse_version(i["Version"].strip()) for i in self.raw_metadata_pool[repo_name][package_name]]

        version_dict = {}
        for i in range(len(versions)):
            version_dict[versions[i]] = version_str[i]
        versions.sort()

        return [Version.parse(version_dict[i]) for i in versions][-1].__str__()

    def _cached_all_cyberfile(self, ns, local_package):
        logger.info("update repo {}".format(ns))
        prefix = os.path.join(get_config("cache", "offline_metadata_prefix"), ns)
        cyberfiles_path = os.path.join(prefix, self.offline_cyberfile_cache_filename)
        if not os.path.exists(cyberfiles_path):
            ErrCode.send_error(
                ErrCode.FileIoErr,
                ["Internal error: can not find the cached cyberfile metadata"],
            )

        root = ET.parse(cyberfiles_path)
        elems = root.iterfind("package")
        for elem in elems:
            name = None
            for label in elem.iterfind("name"):
                name = self.change_package_name(label.text)
            if name is None:
                ErrCode.send_error(
                    ErrCode.NetworkIoError,
                    ["metadata of cyberfiles invalid"],
                    exit=True)
            if name not in self.raw_cyberfile_pool[ns]:
                self.raw_cyberfile_pool[ns][name] = list()
            self.raw_cyberfile_pool[ns][name].append(
                ET.tostring(elem, encoding='utf-8').decode("utf-8"))
        for name in self.raw_cyberfile_pool[ns]:
            remote_cyberfile_content = "\n".join(self.raw_cyberfile_pool[ns][name])
            local_cyberfile_content = ""
            if name in local_package:
                local_cyberfile_content = self.local_package_pool[name]["cyberfile"]

            merge_content = remote_cyberfile_content + "\n" + local_cyberfile_content
            self.cyberfile_source[ns][name] = "<root>\n" + merge_content + "\n</root>"

        logger.info("update complete")

    def get_all_package_name(self):
        pkg_names = []
        for i in self.repositories:
            pkg_names += [name.replace(apollo_prefix, "") for name in self.raw_cyberfile_path_pool[i.name]]
        return list(set(pkg_names))

    def acquire_cyberfile(self, name: str):
        # TODO: Compatible with cross-repository packages
        # format name to repo package name
        ret_namespace, ret_cyberfile = list(), list()

        name = self.change_package_name(name)
        for ns in self.repositories:
            if name in self.raw_cyberfile_path_pool[ns.name]:
                ret_namespace.append(ns.name)

        if len(ret_namespace) == 0:
            # system package or not found
            return None, None

        for ns in ret_namespace:
            if name not in self.cyberfile_source[ns]:
                prefix = os.path.join(get_config("cache", "offline_metadata_prefix"), ns)
                cyberfiles_path = os.path.join(prefix, self.offline_cyberfile_cache_filename)

                if os.path.exists(cyberfiles_path):
                    os.remove(cyberfiles_path)

                ErrCode.send_error(ErrCode.FileIoError,
                                   ["Internal error: missing cyberfile of {} in repository".format(name, ns)])
            ret_cyberfile.append(self.cyberfile_source[ns][name])

        return ret_namespace, ret_cyberfile

    def valid_repository_check(self, name: str, version: str, repo_name: str):
        """get package repository"""
        # TODO: Compatible with cross-repository packages
        prefix_name = self.change_package_name(name)
        ns, cyber_content = self.acquire_cyberfile(name)
        if cyber_content is None:
            return False

        if repo_name not in ns:
            return False

        available_version = \
            [i.__str__() for i in self.raw_version_pool[repo_name][prefix_name]]
        if version in available_version:
            return True
        else:
            return False

    def get_available_version_format(self, name: str):
        # TODO: Compatible with cross-repository packages
        prefix_name = self.change_package_name(name)
        ns, cyber_content = self.acquire_cyberfile(name)
        if cyber_content is None:
            return None

        version_range = []
        for single_repo in ns:
            version_range += [i.__str__() for i in self.raw_version_pool[single_repo][prefix_name]]

        version_range = list(set(version_range))
        versions = [parse_version(i) for i in version_range]

        look_up = {}
        for i in range(len(versions)):
            look_up[versions[i]] = version_range[i]
        versions.sort()

        sorted_version_range = [look_up[i] for i in versions]

        if len(sorted_version_range) > 1:
            return ">={} <={}".format(sorted_version_range[0], sorted_version_range[-1])
        else:
            return "={}".format(sorted_version_range[-1])

    def get_latest_version(self, name: str):
        # TODO: Compatible with cross-repository packages
        prefix_name = self.change_package_name(name)
        ns, cyber_content = self.acquire_cyberfile(name)
        if cyber_content is None:
            return None

        selected_version = []
        for repo in ns:
            selected_version.append(self.raw_version_pool[repo][prefix_name][-1].__str__())

        versions = [parse_version(i) for i in selected_version]
        look_up = {}
        for i in range(len(versions)):
            look_up[versions[i]] = selected_version[i]
        versions.sort()

        sorted_selected_version = [look_up[i] for i in versions]
        return sorted_selected_version[-1]

    def change_package_name(self, name):
        if apollo_prefix not in name:
            return "{}{}".format(apollo_prefix, name)
        return name
