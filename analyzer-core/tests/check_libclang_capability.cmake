# A header predating the required API must fail before unrelated dependencies.
set(root "${CMAKE_CURRENT_BINARY_DIR}/libclang-capability")
file(REMOVE_RECURSE "${root}")
file(MAKE_DIRECTORY "${root}/include/clang-c")
file(WRITE "${root}/include/clang-c/Index.h"
    "typedef struct { int kind; } CXCursor;\nCXCursor clang_getNullCursor(void);\n")
execute_process(COMMAND "${CMAKE_COMMAND}"
    -S "${ANALYZER_SOURCE}" -B "${root}/build"
    "-DLIBCLANG_INCLUDE_DIR=${root}/include"
    "-DLIBCLANG_LIBRARY=${LIBCLANG_LIBRARY}"
    -DBUILD_TESTING=OFF
    RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE error)
if(result EQUAL 0)
    message(FATAL_ERROR "Unsupported libclang headers unexpectedly configured")
endif()
string(FIND "${output}${error}" "required binary-opcode API" diagnostic)
if(diagnostic EQUAL -1)
    message(FATAL_ERROR "Expected actionable libclang API diagnostic: ${output}${error}")
endif()
file(REMOVE_RECURSE "${root}")
