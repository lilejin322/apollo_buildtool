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
from core import ErrCode
from core.version_decide.semver import Version
from core.common import get_config, get_logger
from core.action import apollo_prefix
from core.package_identification.identifier import singleton
from core.task.bazel.handler import Procedure

logger = get_logger('buildtool')

@singleton
class MetaDataCli(object):
    def __init__(self):
        self.metadata_request_url = get_config("url", "metadata")
        self.raw_metadata_pool = dict()
        self.raw_version_pool = dict()
        self.raw_cyberfile_path_pool = dict()
        self.raw_cyberfile_pool = dict()
        self.cyberfile_source = dict()
        self.procedure = Procedure()
        self.online = self.procedure.get_network_status()
        self.need_cached = False
        self._init_metadata()

    def _init_metadata(self):
        raw_metadatas_file = get_config("url", "offline_metadata")
        cyberfile_cahce = get_config("url", "cyberfile_cache")
        raw_metadatas = None

        if self.online:
            raw_metadatas_resp = requests.get(self.metadata_request_url)
            if raw_metadatas_resp.status_code != 200:
                ErrCode.send_error(ErrCode.NetworkIoError, [
                        "Request packages metadata failed! Status code={}".format(
                            raw_metadatas_resp.status_code)])

            raw_metadatas = raw_metadatas_resp.text

            if not os.path.exists(raw_metadatas_file) or not os.path.exists(cyberfile_cahce):
                self.need_cached = True
            else:
                local_cached_md5 = None
                with open(raw_metadatas_file, "r") as f:
                    local_cached_md5 = hashlib.md5(f.read().encode('utf-8')).hexdigest()

                raw_metadatas_md5 = hashlib.md5(raw_metadatas.encode('utf-8')).hexdigest()
                if raw_metadatas_md5 != local_cached_md5:
                    self.need_cached = True

        else:
            if not os.path.exists(raw_metadatas_file) or not os.path.exists(cyberfile_cahce):
                ErrCode.send_error(ErrCode.FileIoErr,
                        ["can not find metadata file"])

            with open(raw_metadatas_file, "r") as f:
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

            if terms_dict["Package"].strip() in self.raw_metadata_pool:
                self.raw_metadata_pool[terms_dict["Package"].strip()].append(terms_dict)
            else:
                self.raw_metadata_pool[terms_dict["Package"].strip()] = [terms_dict]

        if self.online:
            for _, name in enumerate(self.raw_metadata_pool):
                # parse cyberfile path
                self.raw_cyberfile_path_pool[name] = [
                    "{}/{}".format(
                        get_config("url", "head"), (".".join(
                            (i["Filename"].split("."))[: len(i["Filename"].split("."))-1] \
                                + ["cyberfile"]).strip()
                        )
                    ) for i in self.raw_metadata_pool[name]
                ]

                # parse version
                versions = [parse_version(i["Version"].strip()) for i in self.raw_metadata_pool[name]]
                version_dict = {}
                for i in range(len(versions)):
                    version_dict[versions[i]] = self.raw_metadata_pool[name][i]["Version"].strip()
                versions.sort()

                self.raw_version_pool[name] = [
                    Version.parse(version_dict[i]) for i in versions
                ]
        else:
            for _, name in enumerate(self.raw_metadata_pool):
                # parse cyberfile path
                self.raw_cyberfile_path_pool[name] = [
                    "{}".format(((".".join(
                            (i["Filename"].split("."))[: len(i["Filename"].split("."))-1] \
                                + ["cyberfile"]).strip()).split("/"))[-1]
                    ) for i in self.raw_metadata_pool[name]
                ]

                # parse version
                versions = [parse_version(i["Version"].strip()) for i in self.raw_metadata_pool[name]]
                version_dict = {}
                for i in range(len(versions)):
                    version_dict[versions[i]] = self.raw_metadata_pool[name][i]["Version"].strip()
                versions.sort()

                self.raw_version_pool[name] = [
                    Version.parse(version_dict[i]) for i in versions
                ]

        if self.need_cached:
            cyberfile_cahce_dir = "/".join(
                cyberfile_cahce.split("/")[0: len(cyberfile_cahce.split("/"))-1])
            if not os.path.exists(cyberfile_cahce_dir):
                os.makedirs(cyberfile_cahce_dir)
            self._cached_all_cyberfile(cyberfile_cahce)

            with open(raw_metadatas_file, "w+") as f:
                f.write(raw_metadatas)
        else:
            with open(cyberfile_cahce, "r", encoding="utf-8") as f:
                self.cyberfile_source = json.loads(f.read())

    def _cached_all_cyberfile(self, cache_path):
        logger.info("update the local cache")
        cyberfiles_meta_url = get_config("url", "cyberfiles_meta")
        cyberfiles_resp = requests.get(cyberfiles_meta_url) 
        if cyberfiles_resp.status_code != 200:
            ErrCode.send_error(
                ErrCode.NetworkIoError,
                ["fetch metadata of cyberfiles failed"],
                ["may due to the network condition, please try again"],
                exit=True)
        root = ET.fromstring(cyberfiles_resp.text)
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
            if name not in self.raw_cyberfile_pool:
                self.raw_cyberfile_pool[name] = list()
            self.raw_cyberfile_pool[name].append(
                ET.tostring(elem, encoding='utf-8').decode("utf-8"))
        for name in self.raw_cyberfile_pool:
            self.cyberfile_source[name] = "<root>\n" + "\n".join(
                            self.raw_cyberfile_pool[name]) + "\n</root>"
        
        with open(cache_path, "w+", encoding="utf-8") as f:
            f.write(json.dumps(self.cyberfile_source))
        logger.info("update complete")

    def get_all_package_name(self):
        return [name.replace(apollo_prefix, "") for name in self.raw_cyberfile_path_pool]

    def acquire_cyberfile(self, name: str):
        # format name to repo package name
        name = self.change_package_name(name)
        if name not in self.raw_cyberfile_path_pool:
            # system package or not found
            return None

        if name not in self.cyberfile_source:
            cyberfile_cache = get_config("url", "cyberfile_cache")
            if os.path.exists(cyberfile_cache):
                os.remove(cyberfile_cache)
            ErrCode.send_error(
                    ErrCode.NetworkIoError,
                    ["Internal error: missing cyberfile of {}".format(name)],
                    exit=False)

        return self.cyberfile_source[name]

    def get_available_version_format(self, name: str):
        prefix_name = self.change_package_name(name)
        cyber_content = self.acquire_cyberfile(name)
        if cyber_content is None:
            return None

        version_range = self.raw_version_pool[prefix_name]
        if len(version_range) > 1:
            return ">={} <={}".format(version_range[0], version_range[-1])
        else:
            return "={}".format(version_range[-1])

    def get_recached_flags(self):
        return self.need_cached

    def get_latest_version(self, name: str):
        prefix_name = self.change_package_name(name)
        cyber_content = self.acquire_cyberfile(name)
        if cyber_content is None:
            return None

        version_range = self.raw_version_pool[prefix_name]
        return version_range[-1]

    def change_package_name(self, name):
        if apollo_prefix not in name:
            return "{}{}".format(apollo_prefix, name)
        return name