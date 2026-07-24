load("@rules_cc//cc:defs.bzl", "cc_test", "cc_binary", "cc_library")

package(default_visibility = ["//visibility:public"])

cc_library(
    name = "example-lib",
    srcs = glob(["lib/*.so*"]),
    hdrs = glob(["include/*.h"]),
    include_prefix = "example_lib",
    visibility = ["//visibility:public"],
)