# basic repo
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

#def eigen_repo():
#    native.new_local_repository(
#        name = "eigen",
#        build_file = clean_dep("//dev/bazel:eigen.BUILD"),
#        path = "/usr/include/eigen3",
#    )

def com_github_nlohmann_json_repo():
    http_archive(
        name = "com_github_nlohmann_json",
        sha256 = "7d0edf65f2ac7390af5e5a0b323b31202a6c11d744a74b588dc30f5a8c9865ba",
        strip_prefix = "json-3.8.0",
        build_file = clean_dep("//dev/bazel:base_repo.BUILD"),
        urls = [
            "https://apollo-system.cdn.bcebos.com/archive/6.0/v3.8.0.tar.gz",
            "https://github.com/nlohmann/json/archive/v3.8.0.tar.gz",
        ],
    )

#def tinyxml2_repo():
#    # tinyxml2
#    native.new_local_repository(
#        name = "tinyxml2",
#        build_file = clean_dep("//dev/bazel:base_repo.BUILD"),
#        path = "/usr/include",
#    )

#def ipopt_repo():
#    # ipopt
#    native.new_local_repository(
#        name = "ipopt",
#        build_file = clean_dep("//dev/bazel:base_repo.BUILD"),
#        path = "/usr/include",
#    )

def com_google_googletest_repo():
    # googletest (GTest and GMock)
    http_archive(
        name = "com_google_googletest",
        sha256 = "9dc9157a9a1551ec7a7e43daea9a694a0bb5fb8bec81235d8a1e6ef64c716dcb",
        strip_prefix = "googletest-release-1.10.0",
        urls = [
            "https://apollo-system.cdn.bcebos.com/archive/6.0/release-1.10.0.tar.gz",
            "https://github.com/google/googletest/archive/release-1.10.0.tar.gz",
        ],
    )

#def adolc_repo():
#    native.new_local_repository(
#        name = "adolc",
#        build_file = clean_dep("//dev/bazel:base_repo.BUILD"),
#        path = "/usr/include",
#    )

def python_repo():
    http_archive(
        name = "rules_python",
        sha256 = "b6d46438523a3ec0f3cead544190ee13223a52f6a6765a29eae7b7cc24cc83a0",
        urls = [
            "https://apollo-system.cdn.bcebos.com/archive/6.0/rules_python-0.1.0.tar.gz",
            "https://github.com/bazelbuild/rules_python/releases/download/0.1.0/rules_python-0.1.0.tar.gz",
        ],
    )

def bazel_skylib_repo():
    http_archive(
        name = "bazel_skylib",
        sha256 = "1c531376ac7e5a180e0237938a2536de0c54d93f5c278634818e0efc952dd56c",
        urls = [
            "https://apollo-system.cdn.bcebos.com/archive/6.0/bazel-skylib-1.0.3.tar.gz",
            "https://github.com/bazelbuild/bazel-skylib/releases/download/1.0.3/bazel-skylib-1.0.3.tar.gz",
        ],
    )

def proto_repo():
    http_archive(
        name = "rules_proto",
        sha256 = "602e7161d9195e50246177e7c55b2f39950a9cf7366f74ed5f22fd45750cd208",
        strip_prefix = "rules_proto-97d8af4dc474595af3900dd85cb3a29ad28cc313",
        urls = [
            "https://apollo-system.cdn.bcebos.com/archive/6.0/97d8af4dc474595af3900dd85cb3a29ad28cc313.tar.gz",
            "https://github.com/bazelbuild/rules_proto/archive/97d8af4dc474595af3900dd85cb3a29ad28cc313.tar.gz",
        ],
    )

def grpc_repo():
    http_archive(
        name = "com_github_grpc_grpc",
        sha256 = "419dba362eaf8f1d36849ceee17c3e2ff8ff12ac666b42d3ff02a164ebe090e9",
        strip_prefix = "grpc-1.30.0",
        urls = [
            "https://apollo-system.cdn.bcebos.com/archive/6.0/v1.30.0.tar.gz",
            "https://github.com/grpc/grpc/archive/v1.30.0.tar.gz",
        ],
    )

def protobuf_dev_repo():
    http_archive(
        name = "com_google_protobuf",
        sha256 = "d0f5f605d0d656007ce6c8b5a82df3037e1d8fe8b121ed42e536f569dec16113",
        strip_prefix = "protobuf-3.14.0",
        urls = [
            "https://apollo-system.cdn.bcebos.com/archive/6.0/v3.14.0.tar.gz",
            "https://github.com/protocolbuffers/protobuf/archive/v3.14.0.tar.gz",
        ],
    )
    
