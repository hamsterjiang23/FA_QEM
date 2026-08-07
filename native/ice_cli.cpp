#include <Eigen/Core>
#include <Eigen/Dense>

#include <igl/read_triangle_mesh.h>
#include <igl/slice.h>
#include <igl/writeOBJ.h>

#include <build_intrinsic_info.h>
#include <coarsen_mesh.h>
#include <connected_components.h>
#include <get_barycentric_points.h>
#include <remove_unreferenced_intrinsic.h>

#include <chrono>
#include <iostream>
#include <map>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    using namespace Eigen;
    using namespace global_variables;
    if (argc != 4) {
        std::cerr << "usage: ice_coarsening INPUT.obj TARGET_VERTICES OUTPUT.obj\n";
        return 2;
    }
    const std::string input = argv[1];
    const int target_vertices = std::stoi(argv[2]);
    const std::string output = argv[3];

    MatrixXd original_vertices;
    MatrixXi original_faces;
    if (!igl::read_triangle_mesh(input, original_vertices, original_faces)) {
        std::cerr << "failed to read input mesh\n";
        return 3;
    }
    if (target_vertices <= 0 || target_vertices >= original_vertices.rows()) {
        std::cerr << "target vertex count must be positive and below input count\n";
        return 4;
    }

    MatrixXi faces = original_faces;
    MatrixXi glue;
    MatrixXd lengths;
    MatrixXd angles;
    MatrixXi vertex_to_faceside;
    build_intrinsic_info(original_vertices, original_faces, glue, lengths, angles, vertex_to_faceside);

    VectorXi vertex_components;
    VectorXi face_components;
    int component_count = 0;
    connected_components(original_faces, glue, component_count, vertex_components, face_components);
    if (component_count != 1) {
        std::cerr << "ICE requires one connected manifold component; got " << component_count << '\n';
        return 5;
    }

    MatrixXd barycentric_coordinates;
    std::vector<std::vector<int>> face_to_vertices;
    const int removal_count = original_vertices.rows() - target_vertices;
    const double weight = 0.0;
    const auto start = std::chrono::steady_clock::now();
    coarsen_mesh(
        removal_count,
        weight,
        faces,
        glue,
        lengths,
        angles,
        vertex_to_faceside,
        barycentric_coordinates,
        face_to_vertices
    );
    const auto stop = std::chrono::steady_clock::now();

    MatrixXd barycentric_points;
    get_barycentric_points(
        original_vertices,
        faces,
        barycentric_coordinates,
        face_to_vertices,
        barycentric_points
    );

    std::map<int, int> vertex_map;
    std::map<int, int> face_map;
    VectorXi retained_vertices;
    VectorXi retained_faces;
    remove_unreferenced_intrinsic(faces, vertex_map, face_map, retained_vertices, retained_faces);
    MatrixXd visualization_vertices;
    igl::slice(original_vertices, retained_vertices, 1, visualization_vertices);

    if (!igl::writeOBJ(output, visualization_vertices, faces)) {
        std::cerr << "failed to write output mesh\n";
        return 6;
    }
    const double seconds = std::chrono::duration<double>(stop - start).count();
    std::cerr << "ice_algorithm_seconds=" << seconds << " vertices=" << visualization_vertices.rows()
              << " faces=" << faces.rows() << " barycentric_points=" << barycentric_points.rows() << '\n';
    return 0;
}

