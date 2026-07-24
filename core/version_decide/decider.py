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
"""version decider"""
import os
import sys
import json
import pickle
import hashlib
from typing import Any, Dict, Hashable, List, Optional
from core import ErrCode
from core.version_decide.cyberfile import MetaDataCli

from core.version_decide.mixology.constraint import Constraint
from core.version_decide.mixology.package import Package
from core.package_descriptor import Status
from core.version_decide.mixology.package_source import PackageSource as BasePackageSource
from core.version_decide.mixology.range import Range
from core.version_decide.mixology.union import Union
from core.version_decide.semver import Version, VersionRange, parse_constraint
from core.version_decide.mixology.version_solver import VersionSolver
from core.package_descriptor import PackageDesc
from core.package_identification.identifier import PackageIdentification
from core.common import get_config
from core.logging import get_logger

logger = get_logger('buildtool')


class Dependency:
    """dependency descriptor"""
    def __init__(self, name, constraint):  # type: (str, str) -> None
        self.name = name
        self.constraint = parse_constraint(constraint)
        self.pretty_constraint = constraint
        self.package = Package(name)

    def __str__(self):  # type: () -> str
        return self.pretty_constraint


class PackageSource(BasePackageSource):
    """pakcage source"""
    def __init__(self):  # type: () -> None
        self._root_version = Version.parse("0.0.0")
        self._root_dependencies = []
        self._packages = {}

        super(PackageSource, self).__init__()

    @property
    def root_version(self):
        return self._root_version

    def add(self, name, version, deps=None):  
        # type: (str, str, Optional[Dict[str, str]]) -> None
        """add function"""
        if deps is None:
            deps = {}

        version = Version.parse(version)
        if name not in self._packages:
            self._packages[name] = {}

        if version in self._packages[name]:
            raise ValueError("{} ({}) already exists".format(name, version))

        dependencies = []
        for dep_name, spec in deps.items():
            dependencies.append(Dependency(dep_name, spec))

        self._packages[name][version] = dependencies

    def root_dep(self, name, constraint):  
        # type: (str, str) -> None
        self._root_dependencies.append(Dependency(name, constraint))

    def _versions_for(self, package, constraint=None):  
        # type: (Hashable, Any) -> List[Hashable]
        if package not in self._packages:
            return []

        versions = []
        for version in self._packages[package].keys():
            if not constraint or constraint.allows_any(
                Range(version, version, True, True)
            ):
                versions.append(version)

        return sorted(versions, reverse=True)

    def dependencies_for(self, package, version):  
        # type: (Hashable, Any) -> List[Any]
        if package == self.root:
            return self._root_dependencies

        return self._packages[package][version]

    def convert_dependency(self, dependency):  
        # type: (Dependency) -> Constraint
        if isinstance(dependency.constraint, VersionRange):
            constraint = Range(
                dependency.constraint.min,
                dependency.constraint.max,
                dependency.constraint.include_min,
                dependency.constraint.include_max,
                dependency.pretty_constraint,
            )
        else:
            # VersionUnion
            ranges = [
                Range(
                    _range.min,
                    _range.max,
                    _range.include_min,
                    _range.include_max,
                    str(_range),
                )
                for _range in dependency.constraint.ranges
            ]
            constraint = Union.of(*ranges)

        return Constraint(dependency.package, constraint)


class DeciderInterface(object):
    """decider output interface"""
    def __init__(self, repositories):
        self.NON_VERSION = "None"

        self.source = None
        self.cyberfile_source = None
        self.result = None
        self.root_deps_info = []
        self.normal_deps_info = []
        self.package_version_info = {}
        self.repositories = repositories
        self.metadata_cli = MetaDataCli()
        self.metadata_cli.run(repositories)
        self._init_package_source()

    def _init_package_source(self):
        if not self.source:
            self.source = PackageSource()
        if not self.cyberfile_source:
            self.cyberfile_source = dict()

    def collect_root_depend(self, name, entry_version):
        """add root depend"""
        if not self.source:
            return False
        version = self.NON_VERSION

        if entry_version != "":
            version = entry_version

        if name not in self.package_version_info:
            self.package_version_info[name] = set()
            self.package_version_info[name].add(version)
        else:
            self.package_version_info[name].add(version)

        self.root_deps_info.append((name, version))

        # self.source.root_dep(name, version)
        return True

    def register_package(self, name: str, version: str, deps: dict):
        """register available package"""
        if not self.source:
            return False
        for dep_name in deps:
            if dep_name not in self.package_version_info:
                self.package_version_info[dep_name] = set()
                self.package_version_info[dep_name].add(deps[dep_name])
            else:
                self.package_version_info[dep_name].add(deps[dep_name]) 
        self.normal_deps_info.append((name, version, deps))
        # self.source.add(name, version, deps)
        return True

    def _reset_package_version(self):
        # reset all deps version to avoid conflict
        # between workspace version and default version
        # causing version determind failed
        for i in range(len(self.root_deps_info)):
            name = self.root_deps_info[i][0]
            version = self.root_deps_info[i][1]
            if version != self.NON_VERSION:
                self.source.root_dep(name, version) 
                continue
            if len(self.package_version_info[name]) == 1:
                # always equal with None, all version set to repository version
                version = self.NON_VERSION
                # only apollo 'module' package using repository version
                # TODO: change all package to 'module'
                if name.startswith("3rd") or name == "bazel-extend-tools":
                    version = self.metadata_cli.get_available_version_format(name)
                else:
                    ns = self.metadata_cli.get_repository(name)
                    for repo in self.repositories:
                        if repo.name == ns:
                            version = "={}".format(repo.version)
                            break
                    if version == self.NON_VERSION:
                        ErrCode.send_error(ErrCode.FileIoErr,
                            ["Internal error: missing version of root deps: {}".format(name)]
                        )
            else:
                # version specify, disable repository version
                version = self.metadata_cli.get_available_version_format(name)
            self.source.root_dep(name, version) 

        for i in self.normal_deps_info:
            register_pkg_name = i[0]
            register_pkg_version = i[1]
            register_pkg_deps = i[2]
            for register_pkg_dep_name in register_pkg_deps:
                register_pkg_dep_version = register_pkg_deps[register_pkg_dep_name]
                if register_pkg_dep_version != self.NON_VERSION:
                    continue
                if len(self.package_version_info[register_pkg_dep_name]) == 1:
                    # always equal with None, all version set to repository version
                    register_pkg_dep_version = self.NON_VERSION
                    # only apollo 'module' package using repository version 
                    if register_pkg_dep_name.startswith("3rd") or register_pkg_dep_name == "bazel-extend-tools":
                        register_pkg_dep_version = \
                            self.metadata_cli.get_available_version_format(register_pkg_dep_name)
                        register_pkg_deps[register_pkg_dep_name] = register_pkg_dep_version
                    else:
                        ns = self.metadata_cli.get_repository(register_pkg_dep_name)
                        for repo in self.repositories:
                            if repo.name == ns:
                                register_pkg_dep_version = "={}".format(repo.version)
                                break
                        if register_pkg_dep_version == self.NON_VERSION:
                            ErrCode.send_error(
                                ErrCode.FileIoErr,
                                ["Internal error: missing version of root deps: {}".format(register_pkg_dep_name)]
                            )
                        register_pkg_deps[register_pkg_dep_name] = register_pkg_dep_version 
                else:
                    # version specify, disable repository version
                    register_pkg_deps[register_pkg_dep_name] = \
                        self.metadata_cli.get_available_version_format(register_pkg_dep_name) 
            self.source.add(register_pkg_name, register_pkg_version, register_pkg_deps)

    def _get_result(self):
        solver = VersionSolver(self.source)
        solution = solver.solve()

        packages = {}
        for package, version in solution.decisions.items():
            if package == Package.root():
                continue

            packages[package] = str(version)
        return packages

    def get_result(self):
        """get decider results"""
        return self.result

    def _setting_local_target(self, pkg_desc, dep):
        pkg_desc.fulfill_src_type(dep)
        pkg_desc.import_type = "src"
        #pkg_desc.check_real_src()

    def get_cached_result(self, index):
        result_path = os.path.join(
            get_config("decider", "results"), index
        )
        if os.path.isfile(result_path):
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    cached_results = json.loads(f.read())
            except:
                return None
            serialized_results = {
                Package(k): cached_results[k] for _, k in enumerate(cached_results)
            }
            return serialized_results
        else:
            return None

    def get_cyberfile_source(self, index):
        cyberfile_source_path = os.path.join(
            get_config("decider", "cyberfile_source"), index
        )
        if os.path.isfile(cyberfile_source_path):
            try:
                with open(cyberfile_source_path, "rb") as f:
                    cyberfile_source = pickle.load(f)
            except:
                return None
            return cyberfile_source 
        else:
            return None 

    def _get_wrapped_target(self, index):
        cyberfile_source_path = os.path.join(
            get_config("decider", "targets"), index
        )
        if os.path.isfile(cyberfile_source_path):
            try:
                with open(cyberfile_source_path, "rb") as f:
                    targets = pickle.load(f)
            except:
                return None
            return targets 
        else:
            return None 

    def _get_targets_index(self, targets):
        sorted_targets = [target.__str__ for target in targets]
        sorted_targets.sort()
        return hashlib.md5(
            json.dumps(sorted_targets).encode("utf-8")
        ).hexdigest()

    def store_cache(self,targets):
        try:
            os.makedirs(get_config("decider", "results"), exist_ok=True)
            os.makedirs(get_config("decider", "cyberfile_source"), exist_ok=True)
            os.makedirs(get_config("decider", "targets"), exist_ok=True)
            targets_index = self._get_targets_index(targets)
            with open(
                os.path.join(get_config("decider", "results"), targets_index), "w+", encoding="utf-8"
            ) as f:
                f.write(json.dumps(
                    {k._pip_string: self.result[k] for _, k in enumerate(self.result)}
                ))
            with open(
                os.path.join(
                    get_config("decider", "cyberfile_source"), targets_index
                ), "wb"
            ) as f:
                f.write(pickle.dumps(self.cyberfile_source))
            with open(
                os.path.join(
                    get_config("decider", "targets"), targets_index
                ), "wb"
            ) as f:
                f.write(pickle.dumps(targets))
        except:
            pass 

    def __call__(self, targets):
        has_results = False
        self.target_names = dict()
        for i in targets:
            self.target_names[i.name] = i
            
        # force to discard cache

        # if not self.metadata_cli.get_recached_flags():
        #     index = self._get_targets_index(targets)
        #     cached_results = self.get_cached_result(index)
        #     cyberfile_source = self.get_cyberfile_source(index)
        #     possible_targets = self._get_wrapped_target(index)
        #     if cached_results is not None and \
        #         cyberfile_source is not None and \
        #         possible_targets is not None:
        #             self.result = cached_results 
        #             self.cyberfile_source = cyberfile_source
        #             targets = possible_targets
        #             has_results = True
        
        if not has_results:
            for target in targets:
                for dep in target.deps:
                    # ignore system depend and user prebuilt depend
                    _, cyberfile_contents = self.metadata_cli.acquire_cyberfile(dep.name)
                    if cyberfile_contents is None:
                        continue
                    # ignore workspace depend
                    if dep.name in self.target_names:
                        self._setting_local_target(self.target_names[dep.name], dep)
                        continue
                    self.collect_root_depend(dep.name, dep.version_format)
                self._stored_package_info_recu(target, targets)

            self._reset_package_version()

            self.result = self._get_result()
            # cache results and targets
            self.store_cache(targets)
        
        for target in targets:
            target.check_real_src()
        return targets
            

    def _check_package_is_in_targets(self, targets, name):
        for target in targets:
            if name == target.name:
                return True
        return False

    def _stored_package_info_recu(self, target: PackageDesc, targets):
        identifier = PackageIdentification()
        for dep in target.deps:
            dep_is_user_module = False
            for user_module in targets:
                if user_module.name == dep.name:
                    self._setting_local_target(user_module, dep)
                    dep_is_user_module = True
                    break
            
            if dep_is_user_module:
                continue

            if dep.name in self.cyberfile_source:
                # avoiding rewrite the previous setting of pkg_desc
                for version in self.cyberfile_source[dep.name]:
                    self.cyberfile_source[dep.name][version].fulfill_src_type(dep)
                continue

            self.cyberfile_source[dep.name] = dict()
            ns, cyberfile_contents = self.metadata_cli.acquire_cyberfile(dep.name)
            # ignore system depend
            if cyberfile_contents is None:
                continue
            next_level_all_desc = identifier.identify_all(cyberfile_contents, dep)

            for desc in next_level_all_desc:
                if desc.status == Status.INVALID:
                    ErrCode.send_error(
                        ErrCode.PackageAttrErr,
                        ["{} with invalid status".format(desc.name)]
                    )

                desc.repository = ns
                self.cyberfile_source[dep.name][desc.version] = desc
                desc_deps_dict = dict()
                for desc_dep in desc.deps:
                    # stop track local target
                    if self._check_package_is_in_targets(targets, desc_dep.name):
                        self._setting_local_target(self.target_names[desc_dep.name], desc_dep)
                        continue
                    _, cyberfile = self.metadata_cli.acquire_cyberfile(desc_dep.name)
                    if cyberfile is None:
                        # ignore system depend
                        continue
                    version_format = desc_dep.version_format
                    if version_format == "":
                        version_format = self.NON_VERSION
                    desc_deps_dict[desc_dep.name] = version_format
                self.register_package(desc.name, desc.version, desc_deps_dict)

            #TODO: same depend with different attribute may cause problem
            recu_desc = PackageDesc()
            if not recu_desc.fulfill_recu_desc(next_level_all_desc):
                ErrCode.send_error(
                    ErrCode.PackageAttrErr,
                    ["collect depend attribute failed, depend: {}".format(dep.name)]
                )

            self._stored_package_info_recu(recu_desc, targets)

    def find_suitable_desc(self, name):
        """find stored desc"""
        if self.result is None:
            logger.info("Please get the results before find suitable package desc")
            return None
        return self.cyberfile_source[name][self.result[name]]

