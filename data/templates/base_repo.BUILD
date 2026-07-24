# basic repo build file
load("@rules_cc//cc:defs.bzl", "cc_library")
'''
licenses([
    # Note: Eigen is an MPL2 library that includes GPL v3 and LGPL v2.1+ code.
    #       We've taken special care to not reference any restricted code.
    "reciprocal",  # MPL2
    "notice",  # Portions BSD
])

exports_files(["COPYING.MPL2"])

EIGEN_FILES = [
    "Eigen/**",
    "unsupported/Eigen/CXX11/**",
    "unsupported/Eigen/FFT",
    "unsupported/Eigen/KroneckerProduct",
    "unsupported/Eigen/src/FFT/**",
    "unsupported/Eigen/src/KroneckerProduct/**",
    "unsupported/Eigen/MatrixFunctions",
    "unsupported/Eigen/SpecialFunctions",
    "unsupported/Eigen/src/MatrixFunctions/**",
    "unsupported/Eigen/src/SpecialFunctions/**",
]

# List of files picked up by glob but actually part of another target.
EIGEN_EXCLUDE_FILES = [
    "Eigen/src/Core/arch/AVX/PacketMathGoogleTest.cc",
]

EIGEN_MPL2_HEADER_FILES = glob(
    EIGEN_FILES,
    exclude = EIGEN_EXCLUDE_FILES,
)

cc_library(
    name = "eigen",
    hdrs = EIGEN_MPL2_HEADER_FILES,
    includes = ["."],
    visibility = ["//visibility:public"],
)
'''

cc_library(
    name = "json",
    hdrs = glob([
        "include/nlohmann/**/*.hpp",
    ]),
    includes = ["include"],
    visibility = ["//visibility:public"],
    alwayslink = 1,
)

cc_library(
    name = "single_json",
    hdrs = glob(["single_include/**/*.hpp"]),
    strip_include_prefix = "single_include",
    visibility = ["//visibility:public"],
    alwayslink = 1,
)

#cc_library(
#    name = "tinyxml2",
#    includes = [
#        ".",
#    ],
#    linkopts = [
#        "-ltinyxml2",
#    ],
#    visibility = ["//visibility:public"],
#)


#cc_library(
#    name = "ipopt",
#    includes = ["."],
#    linkopts = [
#        "-lipopt",
#    ],
#)

#cc_library(
#    name = "adolc",
#    includes = ["."],
#    linkopts = [
#        "-ladolc",
#    ],
#)
