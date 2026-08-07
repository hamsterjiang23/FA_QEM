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
    add_test(
        NAME stmw_virtual_edge_triangle_distance
        COMMAND paper_simplify
            --method stmw
            --input ${CMAKE_SOURCE_DIR}/tests/fixtures/interior_close_triangles.obj
            --output ${CMAKE_BINARY_DIR}/stmw-interior-close.obj
            --target-faces 1
            --virtual-radius 0.01
    )
    set_tests_properties(stmw_virtual_edge_triangle_distance PROPERTIES
        PASS_REGULAR_EXPRESSION "virtual_edges=1"
    )
    add_test(
        NAME stmw_closed_mesh_has_no_virtual_edges
        COMMAND paper_simplify
            --method stmw
            --input ${CMAKE_SOURCE_DIR}/tests/fixtures/octahedron.obj
            --output ${CMAKE_BINARY_DIR}/stmw-octahedron.obj
            --target-faces 4
            --virtual-radius 0.01
    )
    set_tests_properties(stmw_closed_mesh_has_no_virtual_edges PROPERTIES
        PASS_REGULAR_EXPRESSION "faces=4.*virtual_edges=0"
    )
    add_test(
        NAME qem4vr_welds_uv_seams
        COMMAND paper_simplify
            --method qem4vr
            --input ${CMAKE_SOURCE_DIR}/tests/fixtures/qem4vr_uv_seam.obj
            --output ${CMAKE_BINARY_DIR}/qem4vr-uv-seam.obj
            --target-faces 4
            --boundary-weight 5
            --material-weight 1000
    )
    set_tests_properties(qem4vr_welds_uv_seams PROPERTIES
        PASS_REGULAR_EXPRESSION "faces=4"
    )
    add_test(
        NAME faqem_composite_quadric_smoke
        COMMAND paper_simplify
            --method fa-qem
            --input ${CMAKE_SOURCE_DIR}/tests/fixtures/qem4vr_uv_seam.obj
            --output ${CMAKE_BINARY_DIR}/faqem-uv-seam.obj
            --target-faces 4
            --successive-map ${CMAKE_BINARY_DIR}/faqem-uv-seam-map.bin
            --area-weight 100
            --boundary-weight 500
            --uv-weight 5000
            --normal-weight 0.01
            --plane-area-weight 1
    )
    set_tests_properties(faqem_composite_quadric_smoke PROPERTIES
        PASS_REGULAR_EXPRESSION "method=fa-qem faces=4"
    )
    add_test(
        NAME faqem_centroid_virtual_edge
        COMMAND paper_simplify
            --method fa-qem
            --input ${CMAKE_SOURCE_DIR}/tests/fixtures/disconnected_triangles.obj
            --output ${CMAKE_BINARY_DIR}/faqem-disconnected.obj
            --target-faces 1
            --virtual-radius 0.01
    )
    set_tests_properties(faqem_centroid_virtual_edge PROPERTIES
        PASS_REGULAR_EXPRESSION "initial_virtual_edges=1"
    )
endif()
