cmake_minimum_required(VERSION 3.20)
project(ice_coarsening_cli LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)

if(NOT ICE_SOURCE_ROOT)
    message(FATAL_ERROR "ICE_SOURCE_ROOT must point to the official intrinsic-simplification checkout")
endif()

set(DFETCHCONTENT_SOURCE_DIR_LIBIGL "${ICE_SOURCE_ROOT}/externals/libigl")
list(PREPEND CMAKE_MODULE_PATH "${ICE_SOURCE_ROOT}/00_coarsening/cmake")
include(libigl)

file(GLOB ICE_CORE_SOURCES "${ICE_SOURCE_ROOT}/src/*.cpp")
list(FILTER ICE_CORE_SOURCES EXCLUDE REGEX "/bake_texture\\.cpp$")
add_executable(ice_coarsening "${CMAKE_CURRENT_LIST_DIR}/../ice_cli.cpp" ${ICE_CORE_SOURCES})
target_include_directories(ice_coarsening PRIVATE "${ICE_SOURCE_ROOT}/src")
target_link_libraries(ice_coarsening PRIVATE igl::core)
target_compile_options(ice_coarsening PRIVATE -O3 -fno-omit-frame-pointer)
set_target_properties(ice_coarsening PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)
