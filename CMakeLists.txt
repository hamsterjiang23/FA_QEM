cmake_minimum_required(VERSION 3.20)
project(fa_qem_paper_baselines LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Eigen3 3.3 REQUIRED NO_MODULE)

add_executable(paper_simplify native/paper_simplify.cpp)
target_link_libraries(paper_simplify PRIVATE Eigen3::Eigen)
target_compile_options(paper_simplify PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang>:-O3;-Wall;-Wextra;-Wpedantic>
    $<$<CXX_COMPILER_ID:MSVC>:/O2;/W4>
)
set_target_properties(paper_simplify PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

include(CTest)
if(BUILD_TESTING)
    add_test(NAME paper_simplify_help COMMAND paper_simplify --help)
endif()

