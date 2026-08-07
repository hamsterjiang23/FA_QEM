#include <Eigen/Dense>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace fs = std::filesystem;
using Vec2 = Eigen::Vector2d;
using Vec3 = Eigen::Vector3d;
using Vec4 = Eigen::Vector4d;
using Mat4 = Eigen::Matrix4d;

struct Edge {
    int a{};
    int b{};
    Edge(int x, int y) : a(std::min(x, y)), b(std::max(x, y)) {}
    bool operator==(const Edge& other) const { return a == other.a && b == other.b; }
};

struct EdgeHash {
    std::size_t operator()(const Edge& edge) const noexcept {
        return (static_cast<std::size_t>(static_cast<std::uint32_t>(edge.a)) << 32U) ^
               static_cast<std::uint32_t>(edge.b);
    }
};

struct Face {
    std::array<int, 3> v{};
    int material{};
    bool active{true};
};

struct Vertex {
    Vec3 p{Vec3::Zero()};
    Vec2 uv{Vec2::Zero()};
    Vec3 normal{Vec3::Zero()};
    Mat4 memory_quadric{Mat4::Zero()};
    bool has_uv{false};
    bool has_normal{false};
    bool active{true};
    std::uint64_t revision{0};
    std::unordered_set<int> faces;
    std::unordered_set<int> neighbors;
};

struct Mesh {
    std::vector<Vertex> vertices;
    std::vector<Face> faces;
    std::unordered_set<Edge, EdgeHash> virtual_edges;
    std::size_t active_faces{};
};

struct FaceSnapshot {
    std::uint32_t face{};
    std::array<Vec3, 3> vertices{};
};

struct CollapseRecord {
    std::vector<FaceSnapshot> before;
    std::vector<std::uint32_t> after;
};

struct Options {
    std::string method;
    fs::path input;
    fs::path output;
    fs::path checkpoint_dir;
    fs::path successive_map;
    std::size_t target_faces{};
    double virtual_radius{0.01};
    double boundary_weight{1000.0};
    double curvature_gain{10.0};
    double uv_weight{10.0};
    double normal_weight{1.0};
    double material_weight{1000.0};
};

struct Candidate {
    double cost{};
    int a{};
    int b{};
    std::uint64_t revision_a{};
    std::uint64_t revision_b{};
    Vec3 position{Vec3::Zero()};
    bool operator>(const Candidate& other) const {
        if (cost != other.cost) return cost > other.cost;
        if (a != other.a) return a > other.a;
        return b > other.b;
    }
};

class DisjointSet {
public:
    explicit DisjointSet(std::size_t size) : parent_(size), rank_(size, 0) {
        for (std::size_t index = 0; index < size; ++index) parent_[index] = static_cast<int>(index);
    }
    int find(int item) {
        if (parent_[item] != item) parent_[item] = find(parent_[item]);
        return parent_[item];
    }
    void unite(int a, int b) {
        a = find(a);
        b = find(b);
        if (a == b) return;
        if (rank_[a] < rank_[b]) std::swap(a, b);
        parent_[b] = a;
        if (rank_[a] == rank_[b]) ++rank_[a];
    }

private:
    std::vector<int> parent_;
    std::vector<int> rank_;
};

static std::vector<std::string> split(const std::string& value, char delimiter) {
    std::vector<std::string> parts;
    std::stringstream stream(value);
    std::string part;
    while (std::getline(stream, part, delimiter)) parts.push_back(part);
    return parts;
}

static int obj_index(const std::string& value, std::size_t count) {
    if (value.empty()) return -1;
    const int raw = std::stoi(value);
    if (raw > 0) return raw - 1;
    if (raw < 0) return static_cast<int>(count) + raw;
    throw std::runtime_error("OBJ indices are one-based");
}

static Mesh load_obj(const fs::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open OBJ: " + path.string());
    std::vector<Vec3> positions;
    std::vector<Vec2> texcoords;
    std::vector<Vec3> normals;
    std::unordered_map<std::string, int> materials;
    int current_material = 0;
    Mesh mesh;
    std::vector<Vec2> uv_sum;
    std::vector<Vec3> normal_sum;
    std::vector<int> uv_count;
    std::vector<int> normal_count;
    std::string line;
    while (std::getline(input, line)) {
        if (line.rfind("v ", 0) == 0) {
            std::stringstream values(line.substr(2));
            Vec3 point;
            values >> point.x() >> point.y() >> point.z();
            positions.push_back(point);
            uv_sum.push_back(Vec2::Zero());
            normal_sum.push_back(Vec3::Zero());
            uv_count.push_back(0);
            normal_count.push_back(0);
        } else if (line.rfind("vt ", 0) == 0) {
            std::stringstream values(line.substr(3));
            Vec2 uv;
            values >> uv.x() >> uv.y();
            texcoords.push_back(uv);
        } else if (line.rfind("vn ", 0) == 0) {
            std::stringstream values(line.substr(3));
            Vec3 normal;
            values >> normal.x() >> normal.y() >> normal.z();
            normals.push_back(normal.normalized());
        } else if (line.rfind("usemtl ", 0) == 0) {
            const std::string name = line.substr(7);
            auto [iterator, inserted] = materials.emplace(name, static_cast<int>(materials.size()));
            current_material = iterator->second;
            (void)inserted;
        } else if (line.rfind("f ", 0) == 0) {
            std::stringstream values(line.substr(2));
            std::vector<std::array<int, 3>> corners;
            std::string token;
            while (values >> token) {
                const auto fields = split(token, '/');
                const int vertex = obj_index(fields.at(0), positions.size());
                int uv = -1;
                int normal = -1;
                if (fields.size() > 1) uv = obj_index(fields[1], texcoords.size());
                if (fields.size() > 2) normal = obj_index(fields[2], normals.size());
                corners.push_back({vertex, uv, normal});
                if (uv >= 0) {
                    uv_sum[vertex] += texcoords.at(static_cast<std::size_t>(uv));
                    ++uv_count[vertex];
                }
                if (normal >= 0) {
                    normal_sum[vertex] += normals.at(static_cast<std::size_t>(normal));
                    ++normal_count[vertex];
                }
            }
            for (std::size_t i = 1; i + 1 < corners.size(); ++i) {
                mesh.faces.push_back({{corners[0][0], corners[i][0], corners[i + 1][0]}, current_material, true});
            }
        }
    }
    mesh.vertices.resize(positions.size());
    for (std::size_t i = 0; i < positions.size(); ++i) {
        mesh.vertices[i].p = positions[i];
        if (uv_count[i] > 0) {
            mesh.vertices[i].uv = uv_sum[i] / static_cast<double>(uv_count[i]);
            mesh.vertices[i].has_uv = true;
        }
        if (normal_count[i] > 0 && normal_sum[i].norm() > 0) {
            mesh.vertices[i].normal = normal_sum[i].normalized();
            mesh.vertices[i].has_normal = true;
        }
    }
    mesh.active_faces = mesh.faces.size();
    return mesh;
}

static Mat4 plane_quadric(const Vec3& normal, const Vec3& point, double weight = 1.0) {
    Vec4 plane;
    plane << normal, -normal.dot(point);
    return weight * plane * plane.transpose();
}

static void rebuild_connectivity(Mesh& mesh) {
    for (auto& vertex : mesh.vertices) {
        vertex.faces.clear();
        vertex.neighbors.clear();
    }
    mesh.active_faces = 0;
    for (std::size_t face_index = 0; face_index < mesh.faces.size(); ++face_index) {
        auto& face = mesh.faces[face_index];
        if (!face.active) continue;
        if (face.v[0] == face.v[1] || face.v[1] == face.v[2] || face.v[2] == face.v[0]) {
            face.active = false;
            continue;
        }
        ++mesh.active_faces;
        for (int corner = 0; corner < 3; ++corner) {
            const int vertex = face.v[corner];
            const int next = face.v[(corner + 1) % 3];
            mesh.vertices[vertex].faces.insert(static_cast<int>(face_index));
            mesh.vertices[vertex].neighbors.insert(next);
            mesh.vertices[next].neighbors.insert(vertex);
        }
    }
}

static std::unordered_map<Edge, int, EdgeHash> edge_counts(const Mesh& mesh) {
    std::unordered_map<Edge, int, EdgeHash> counts;
    counts.reserve(mesh.active_faces * 2);
    for (const auto& face : mesh.faces) {
        if (!face.active) continue;
        ++counts[Edge(face.v[0], face.v[1])];
        ++counts[Edge(face.v[1], face.v[2])];
        ++counts[Edge(face.v[2], face.v[0])];
    }
    return counts;
}

static void initialize_quadrics(Mesh& mesh, const Options& options) {
    for (auto& vertex : mesh.vertices) vertex.memory_quadric.setZero();
    for (const auto& face : mesh.faces) {
        const Vec3& a = mesh.vertices[face.v[0]].p;
        const Vec3& b = mesh.vertices[face.v[1]].p;
        const Vec3& c = mesh.vertices[face.v[2]].p;
        const Vec3 cross = (b - a).cross(c - a);
        if (cross.squaredNorm() <= 1e-30) continue;
        const Mat4 quadric = plane_quadric(cross.normalized(), a);
        for (const int vertex : face.v) mesh.vertices[vertex].memory_quadric += quadric;
    }
    if (options.method != "qem4vr") return;
    const auto counts = edge_counts(mesh);
    std::vector<std::vector<Vec3>> boundary_directions(mesh.vertices.size());
    for (const auto& [edge, count] : counts) {
        if (count != 1) continue;
        const Vec3 direction = (mesh.vertices[edge.b].p - mesh.vertices[edge.a].p).normalized();
        boundary_directions[edge.a].push_back(direction);
        boundary_directions[edge.b].push_back(-direction);
    }
    auto curvature = [&](int vertex) {
        const auto& directions = boundary_directions[vertex];
        if (directions.size() < 2) return 0.0;
        double maximum = 0.0;
        for (std::size_t i = 0; i < directions.size(); ++i) {
            for (std::size_t j = i + 1; j < directions.size(); ++j) {
                maximum = std::max(maximum, 1.0 - std::clamp(directions[i].dot(directions[j]), -1.0, 1.0));
            }
        }
        return maximum;
    };
    for (const auto& [edge, count] : counts) {
        if (count != 1) continue;
        int face_index = -1;
        for (const int candidate : mesh.vertices[edge.a].faces) {
            const auto& face = mesh.faces[candidate];
            if (std::find(face.v.begin(), face.v.end(), edge.b) != face.v.end()) {
                face_index = candidate;
                break;
            }
        }
        if (face_index < 0) continue;
        const auto& face = mesh.faces[face_index];
        const Vec3 a = mesh.vertices[edge.a].p;
        const Vec3 b = mesh.vertices[edge.b].p;
        const Vec3 c = mesh.vertices[face.v[0]].p;
        Vec3 face_normal = (mesh.vertices[face.v[1]].p - c).cross(mesh.vertices[face.v[2]].p - c);
        if (face_normal.norm() <= 1e-15) continue;
        face_normal.normalize();
        Vec3 constraint_normal = (b - a).normalized().cross(face_normal).normalized();
        const double curve = std::max(curvature(edge.a), curvature(edge.b));
        const double weight = options.boundary_weight * (1.0 + options.curvature_gain * curve);
        const Mat4 boundary = plane_quadric(constraint_normal, a, weight);
        mesh.vertices[edge.a].memory_quadric += boundary;
        mesh.vertices[edge.b].memory_quadric += boundary;
    }
}

static double point_triangle_squared_distance(const Vec3& point, const Vec3& a, const Vec3& b, const Vec3& c) {
    const Vec3 ab = b - a;
    const Vec3 ac = c - a;
    const Vec3 ap = point - a;
    const double d1 = ab.dot(ap);
    const double d2 = ac.dot(ap);
    if (d1 <= 0.0 && d2 <= 0.0) return ap.squaredNorm();
    const Vec3 bp = point - b;
    const double d3 = ab.dot(bp);
    const double d4 = ac.dot(bp);
    if (d3 >= 0.0 && d4 <= d3) return bp.squaredNorm();
    const double vc = d1 * d4 - d3 * d2;
    if (vc <= 0.0 && d1 >= 0.0 && d3 <= 0.0) {
        const double v = d1 / (d1 - d3);
        return (point - (a + v * ab)).squaredNorm();
    }
    const Vec3 cp = point - c;
    const double d5 = ab.dot(cp);
    const double d6 = ac.dot(cp);
    if (d6 >= 0.0 && d5 <= d6) return cp.squaredNorm();
    const double vb = d5 * d2 - d1 * d6;
    if (vb <= 0.0 && d2 >= 0.0 && d6 <= 0.0) {
        const double w = d2 / (d2 - d6);
        return (point - (a + w * ac)).squaredNorm();
    }
    const double va = d3 * d6 - d5 * d4;
    if (va <= 0.0 && (d4 - d3) >= 0.0 && (d5 - d6) >= 0.0) {
        const double w = (d4 - d3) / ((d4 - d3) + (d5 - d6));
        return (point - (b + w * (c - b))).squaredNorm();
    }
    const Vec3 normal = ab.cross(ac);
    const double denominator = normal.squaredNorm();
    if (denominator <= 1e-30) {
        return std::min({(point - a).squaredNorm(), (point - b).squaredNorm(), (point - c).squaredNorm()});
    }
    const double signed_distance = normal.dot(ap);
    return signed_distance * signed_distance / denominator;
}

static double segment_segment_squared_distance(const Vec3& p1, const Vec3& q1, const Vec3& p2, const Vec3& q2) {
    const Vec3 d1 = q1 - p1;
    const Vec3 d2 = q2 - p2;
    const Vec3 r = p1 - p2;
    const double a = d1.squaredNorm();
    const double e = d2.squaredNorm();
    const double f = d2.dot(r);
    double s = 0.0;
    double t = 0.0;
    if (a <= 1e-30 && e <= 1e-30) return r.squaredNorm();
    if (a <= 1e-30) {
        t = std::clamp(f / e, 0.0, 1.0);
    } else {
        const double c = d1.dot(r);
        if (e <= 1e-30) {
            s = std::clamp(-c / a, 0.0, 1.0);
        } else {
            const double b = d1.dot(d2);
            const double denominator = a * e - b * b;
            if (denominator > 1e-30) s = std::clamp((b * f - c * e) / denominator, 0.0, 1.0);
            t = (b * s + f) / e;
            if (t < 0.0) {
                t = 0.0;
                s = std::clamp(-c / a, 0.0, 1.0);
            } else if (t > 1.0) {
                t = 1.0;
                s = std::clamp((b - c) / a, 0.0, 1.0);
            }
        }
    }
    return ((p1 + s * d1) - (p2 + t * d2)).squaredNorm();
}

static double triangle_triangle_squared_distance(const Mesh& mesh, const Face& first, const Face& second) {
    std::array<Vec3, 3> a;
    std::array<Vec3, 3> b;
    for (int corner = 0; corner < 3; ++corner) {
        a[corner] = mesh.vertices[first.v[corner]].p;
        b[corner] = mesh.vertices[second.v[corner]].p;
    }
    double result = std::numeric_limits<double>::infinity();
    for (int corner = 0; corner < 3; ++corner) {
        result = std::min(result, point_triangle_squared_distance(a[corner], b[0], b[1], b[2]));
        result = std::min(result, point_triangle_squared_distance(b[corner], a[0], a[1], a[2]));
    }
    for (int edge_a = 0; edge_a < 3; ++edge_a) {
        for (int edge_b = 0; edge_b < 3; ++edge_b) {
            result = std::min(result, segment_segment_squared_distance(
                                          a[edge_a], a[(edge_a + 1) % 3], b[edge_b], b[(edge_b + 1) % 3]));
        }
    }
    return result;
}

static void build_virtual_edges(Mesh& mesh, double radius) {
    DisjointSet components(mesh.vertices.size());
    for (const auto& face : mesh.faces) {
        components.unite(face.v[0], face.v[1]);
        components.unite(face.v[1], face.v[2]);
    }
    std::unordered_set<int> roots;
    for (std::size_t index = 0; index < mesh.vertices.size(); ++index) {
        if (mesh.vertices[index].active) roots.insert(components.find(static_cast<int>(index)));
    }
    if (roots.size() <= 1) return;
    const double threshold = 2.0 * radius;
    const double cell = std::max(threshold, 1e-9);
    std::unordered_map<std::string, std::vector<int>> buckets;
    for (std::size_t face_index = 0; face_index < mesh.faces.size(); ++face_index) {
        const Face& face = mesh.faces[face_index];
        Vec3 minimum = mesh.vertices[face.v[0]].p;
        Vec3 maximum = minimum;
        for (int corner = 1; corner < 3; ++corner) {
            minimum = minimum.cwiseMin(mesh.vertices[face.v[corner]].p);
            maximum = maximum.cwiseMax(mesh.vertices[face.v[corner]].p);
        }
        minimum.array() -= radius;
        maximum.array() += radius;
        const Eigen::Vector3i start = (minimum / cell).array().floor().cast<int>();
        const Eigen::Vector3i stop = (maximum / cell).array().floor().cast<int>();
        for (int x = start.x(); x <= stop.x(); ++x) {
            for (int y = start.y(); y <= stop.y(); ++y) {
                for (int z = start.z(); z <= stop.z(); ++z) {
                    const std::string key = std::to_string(x) + ":" + std::to_string(y) + ":" + std::to_string(z);
                    buckets[key].push_back(static_cast<int>(face_index));
                }
            }
        }
    }
    std::unordered_set<std::uint64_t> tested_pairs;
    for (const auto& [key, faces] : buckets) {
        (void)key;
        for (std::size_t i = 0; i < faces.size(); ++i) {
            for (std::size_t j = i + 1; j < faces.size(); ++j) {
                const int first_index = std::min(faces[i], faces[j]);
                const int second_index = std::max(faces[i], faces[j]);
                const std::uint64_t pair_key = (static_cast<std::uint64_t>(static_cast<std::uint32_t>(first_index))
                                                << 32U) |
                                               static_cast<std::uint32_t>(second_index);
                if (!tested_pairs.insert(pair_key).second) continue;
                const Face& first = mesh.faces[first_index];
                const Face& second = mesh.faces[second_index];
                if (components.find(first.v[0]) == components.find(second.v[0])) continue;
                if (triangle_triangle_squared_distance(mesh, first, second) >= threshold * threshold) continue;
                Edge closest(first.v[0], second.v[0]);
                double closest_squared = std::numeric_limits<double>::infinity();
                for (const int vertex_a : first.v) {
                    for (const int vertex_b : second.v) {
                        const double squared = (mesh.vertices[vertex_a].p - mesh.vertices[vertex_b].p).squaredNorm();
                        if (squared < closest_squared) {
                            closest_squared = squared;
                            closest = Edge(vertex_a, vertex_b);
                        }
                    }
                }
                mesh.virtual_edges.insert(closest);
            }
        }
    }
}

static double evaluate(const Mat4& quadric, const Vec3& position) {
    Vec4 homogeneous;
    homogeneous << position, 1.0;
    return homogeneous.dot(quadric * homogeneous);
}

static Vec3 optimal_position(const Mat4& quadric, const Vec3& a, const Vec3& b) {
    const Eigen::Matrix3d system = quadric.topLeftCorner<3, 3>();
    const Vec3 rhs = -quadric.topRightCorner<3, 1>();
    Eigen::FullPivLU<Eigen::Matrix3d> solver(system);
    if (solver.isInvertible()) {
        const Vec3 solved = solver.solve(rhs);
        if (solved.allFinite()) return solved;
    }
    const Vec3 middle = 0.5 * (a + b);
    const std::array<Vec3, 3> choices{a, b, middle};
    return *std::min_element(choices.begin(), choices.end(), [&](const Vec3& left, const Vec3& right) {
        return evaluate(quadric, left) < evaluate(quadric, right);
    });
}

static std::unordered_set<int> materials_at(const Mesh& mesh, int vertex) {
    std::unordered_set<int> materials;
    for (const int face_index : mesh.vertices[vertex].faces) {
        if (mesh.faces[face_index].active) materials.insert(mesh.faces[face_index].material);
    }
    return materials;
}

static int active_edge_incidence(const Mesh& mesh, int a, int b) {
    const auto& first = mesh.vertices[a].faces;
    const auto& second = mesh.vertices[b].faces;
    const auto& smaller = first.size() <= second.size() ? first : second;
    const auto& larger = first.size() <= second.size() ? second : first;
    int count = 0;
    for (const int face_index : smaller) {
        if (larger.contains(face_index) && mesh.faces[face_index].active) ++count;
    }
    return count;
}

static Eigen::Matrix3d cross_matrix(const Vec3& vector) {
    Eigen::Matrix3d matrix;
    matrix << 0.0, -vector.z(), vector.y(), vector.z(), 0.0, -vector.x(), -vector.y(), vector.x(), 0.0;
    return matrix;
}

static Mat4 memoryless_area_quadric(const Mesh& mesh, int a, int b) {
    std::unordered_set<int> local_faces = mesh.vertices[a].faces;
    local_faces.insert(mesh.vertices[b].faces.begin(), mesh.vertices[b].faces.end());
    std::unordered_set<Edge, EdgeHash> boundary_edges;
    for (const int face_index : local_faces) {
        const Face& face = mesh.faces[face_index];
        if (!face.active) continue;
        for (int corner = 0; corner < 3; ++corner) {
            const Edge edge(face.v[corner], face.v[(corner + 1) % 3]);
            if (active_edge_incidence(mesh, edge.a, edge.b) == 1) boundary_edges.insert(edge);
        }
    }
    Mat4 result = Mat4::Zero();
    for (const Edge& edge : boundary_edges) {
        const Vec3& va = mesh.vertices[edge.a].p;
        const Vec3& vb = mesh.vertices[edge.b].p;
        const Vec3 s = vb - va;
        const Vec3 t = va.cross(vb);
        Eigen::Matrix<double, 3, 4> expression;
        expression.leftCols<3>() = cross_matrix(s);
        expression.col(3) = t;
        result += 0.5 * expression.transpose() * expression;
    }
    return result;
}

static Candidate candidate_for(const Mesh& mesh, int a, int b, const Options& options) {
    const Vertex& first = mesh.vertices[a];
    const Vertex& second = mesh.vertices[b];
    Mat4 quadric = first.memory_quadric + second.memory_quadric;
    if (options.method == "stmw") quadric += memoryless_area_quadric(mesh, a, b);
    const Vec3 position = optimal_position(quadric, first.p, second.p);
    double cost = std::max(0.0, evaluate(quadric, position));
    if (options.method == "qem4vr") {
        if (first.has_uv && second.has_uv) cost += options.uv_weight * (first.uv - second.uv).squaredNorm();
        if (first.has_normal && second.has_normal) {
            cost += options.normal_weight * (1.0 - std::clamp(first.normal.dot(second.normal), -1.0, 1.0));
        }
        if (materials_at(mesh, a) != materials_at(mesh, b)) cost += options.material_weight;
    }
    return {cost, a, b, first.revision, second.revision, position};
}

static bool edge_exists(const Mesh& mesh, int a, int b) {
    return mesh.vertices[a].neighbors.contains(b) || mesh.virtual_edges.contains(Edge(a, b));
}

static bool collapse_valid(const Mesh& mesh, const Candidate& candidate) {
    const bool physical_edge = mesh.vertices[candidate.a].neighbors.contains(candidate.b);
    if (physical_edge) {
        std::unordered_set<int> common;
        for (const int neighbor : mesh.vertices[candidate.a].neighbors) {
            if (mesh.vertices[candidate.b].neighbors.contains(neighbor)) common.insert(neighbor);
        }
        std::unordered_set<int> edge_link;
        for (const int face_index : mesh.vertices[candidate.a].faces) {
            const Face& face = mesh.faces[face_index];
            if (!face.active || std::find(face.v.begin(), face.v.end(), candidate.b) == face.v.end()) continue;
            for (const int vertex : face.v) {
                if (vertex != candidate.a && vertex != candidate.b) edge_link.insert(vertex);
            }
        }
        if (common != edge_link) return false;
    }
    std::unordered_set<int> affected = mesh.vertices[candidate.a].faces;
    affected.insert(mesh.vertices[candidate.b].faces.begin(), mesh.vertices[candidate.b].faces.end());
    std::unordered_set<std::string> mapped_faces;
    for (const int face_index : affected) {
        const Face& face = mesh.faces[face_index];
        if (!face.active) continue;
        std::array<Vec3, 3> before;
        std::array<Vec3, 3> after;
        bool degenerates = false;
        for (int corner = 0; corner < 3; ++corner) {
            before[corner] = mesh.vertices[face.v[corner]].p;
            after[corner] = (face.v[corner] == candidate.a || face.v[corner] == candidate.b)
                                ? candidate.position
                                : before[corner];
        }
        std::array<int, 3> mapped = face.v;
        for (int& vertex : mapped) {
            if (vertex == candidate.b) vertex = candidate.a;
        }
        degenerates = mapped[0] == mapped[1] || mapped[1] == mapped[2] || mapped[2] == mapped[0];
        if (degenerates) continue;
        std::sort(mapped.begin(), mapped.end());
        const std::string face_key = std::to_string(mapped[0]) + ":" + std::to_string(mapped[1]) + ":" +
                                     std::to_string(mapped[2]);
        if (!mapped_faces.insert(face_key).second) return false;
        const Vec3 old_normal = (before[1] - before[0]).cross(before[2] - before[0]);
        const Vec3 new_normal = (after[1] - after[0]).cross(after[2] - after[0]);
        if (new_normal.squaredNorm() <= 1e-24) return false;
        if (old_normal.dot(new_normal) <= 1e-12 * old_normal.norm() * new_normal.norm()) return false;
    }
    return true;
}

static std::vector<int> collapse(
    Mesh& mesh, const Candidate& candidate, std::vector<CollapseRecord>* history_records) {
    Vertex& keep = mesh.vertices[candidate.a];
    Vertex& remove = mesh.vertices[candidate.b];
    std::unordered_set<int> affected = keep.faces;
    affected.insert(remove.faces.begin(), remove.faces.end());
    CollapseRecord history;
    if (history_records != nullptr) {
        history.before.reserve(affected.size());
        for (const int face_index : affected) {
            const Face& face = mesh.faces[face_index];
            if (!face.active) continue;
            FaceSnapshot snapshot;
            snapshot.face = static_cast<std::uint32_t>(face_index);
            for (int corner = 0; corner < 3; ++corner) {
                snapshot.vertices[corner] = mesh.vertices[face.v[corner]].p;
            }
            history.before.push_back(std::move(snapshot));
        }
    }
    std::unordered_set<int> impacted{candidate.a, candidate.b};
    for (const int face_index : affected) {
        const Face& face = mesh.faces[face_index];
        for (const int vertex : face.v) impacted.insert(vertex);
    }
    std::unordered_set<int> stale_neighbors;
    for (const int vertex : impacted) {
        stale_neighbors.insert(mesh.vertices[vertex].neighbors.begin(), mesh.vertices[vertex].neighbors.end());
    }
    for (const int neighbor : stale_neighbors) {
        for (const int vertex : impacted) mesh.vertices[neighbor].neighbors.erase(vertex);
    }
    for (const int face_index : affected) {
        const Face& face = mesh.faces[face_index];
        for (const int vertex : face.v) mesh.vertices[vertex].faces.erase(face_index);
    }

    keep.p = candidate.position;
    keep.memory_quadric += remove.memory_quadric;
    if (keep.has_uv && remove.has_uv) keep.uv = 0.5 * (keep.uv + remove.uv);
    if (keep.has_normal && remove.has_normal && (keep.normal + remove.normal).norm() > 0) {
        keep.normal = (keep.normal + remove.normal).normalized();
    }
    for (const int face_index : affected) {
        Face& face = mesh.faces[face_index];
        if (!face.active) continue;
        for (int& vertex : face.v) {
            if (vertex == candidate.b) vertex = candidate.a;
        }
        if (face.v[0] == face.v[1] || face.v[1] == face.v[2] || face.v[2] == face.v[0]) {
            face.active = false;
            --mesh.active_faces;
            continue;
        }
        for (const int vertex : face.v) {
            mesh.vertices[vertex].faces.insert(face_index);
            impacted.insert(vertex);
        }
    }
    if (history_records != nullptr) {
        history.after.reserve(affected.size());
        for (const int face_index : affected) {
            if (mesh.faces[face_index].active) {
                history.after.push_back(static_cast<std::uint32_t>(face_index));
            }
        }
        history_records->push_back(std::move(history));
    }
    remove.active = false;
    remove.faces.clear();
    remove.neighbors.clear();
    for (auto iterator = mesh.virtual_edges.begin(); iterator != mesh.virtual_edges.end();) {
        if (iterator->a == candidate.b || iterator->b == candidate.b) {
            const int other = iterator->a == candidate.b ? iterator->b : iterator->a;
            iterator = mesh.virtual_edges.erase(iterator);
            if (other != candidate.a && mesh.vertices[other].active) mesh.virtual_edges.insert(Edge(candidate.a, other));
        } else {
            ++iterator;
        }
    }
    for (const int vertex : impacted) {
        mesh.vertices[vertex].neighbors.clear();
    }
    for (const int vertex : impacted) {
        Vertex& current = mesh.vertices[vertex];
        ++current.revision;
        if (!current.active) continue;
        for (const int face_index : current.faces) {
            const Face& face = mesh.faces[face_index];
            if (!face.active) continue;
            for (const int other : face.v) {
                if (other == vertex || !mesh.vertices[other].active) continue;
                current.neighbors.insert(other);
                mesh.vertices[other].neighbors.insert(vertex);
            }
        }
    }
    std::vector<int> result;
    result.reserve(impacted.size());
    for (const int vertex : impacted) {
        if (mesh.vertices[vertex].active) result.push_back(vertex);
    }
    return result;
}

template <typename Value>
static void write_binary(std::ofstream& output, const Value& value) {
    output.write(reinterpret_cast<const char*>(&value), sizeof(Value));
}

static void write_successive_map(
    const Mesh& mesh, const std::vector<CollapseRecord>& history, const fs::path& path) {
    fs::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::binary);
    if (!output) throw std::runtime_error("cannot write successive map: " + path.string());
    constexpr std::array<char, 8> magic{'F', 'Q', 'S', 'M', 'A', 'P', '1', '\0'};
    output.write(magic.data(), static_cast<std::streamsize>(magic.size()));
    const std::uint32_t version = 1;
    const std::uint32_t reserved = 0;
    const std::uint64_t record_count = history.size();
    const std::uint64_t final_face_count = mesh.active_faces;
    write_binary(output, version);
    write_binary(output, reserved);
    write_binary(output, record_count);
    write_binary(output, final_face_count);
    for (const CollapseRecord& record : history) {
        const std::uint32_t before_count = static_cast<std::uint32_t>(record.before.size());
        const std::uint32_t after_count = static_cast<std::uint32_t>(record.after.size());
        write_binary(output, before_count);
        write_binary(output, after_count);
        for (const FaceSnapshot& snapshot : record.before) {
            write_binary(output, snapshot.face);
            for (const Vec3& point : snapshot.vertices) {
                for (int axis = 0; axis < 3; ++axis) write_binary(output, point[axis]);
            }
        }
        for (const std::uint32_t face : record.after) write_binary(output, face);
    }
    for (std::size_t face_index = 0; face_index < mesh.faces.size(); ++face_index) {
        if (mesh.faces[face_index].active) {
            const auto value = static_cast<std::uint32_t>(face_index);
            write_binary(output, value);
        }
    }
    if (!output) throw std::runtime_error("failed while writing successive map: " + path.string());
}

static void write_obj(const Mesh& mesh, const fs::path& path) {
    fs::create_directories(path.parent_path());
    std::ofstream output(path);
    if (!output) throw std::runtime_error("cannot write OBJ: " + path.string());
    output << std::setprecision(17);
    std::vector<int> remap(mesh.vertices.size(), -1);
    int next = 1;
    for (std::size_t index = 0; index < mesh.vertices.size(); ++index) {
        if (!mesh.vertices[index].active || mesh.vertices[index].faces.empty()) continue;
        remap[index] = next++;
        const Vec3& point = mesh.vertices[index].p;
        output << "v " << point.x() << ' ' << point.y() << ' ' << point.z() << '\n';
    }
    for (const auto& face : mesh.faces) {
        if (!face.active) continue;
        output << "f " << remap[face.v[0]] << ' ' << remap[face.v[1]] << ' ' << remap[face.v[2]] << '\n';
    }
}

static void simplify(Mesh& mesh, const Options& options) {
    rebuild_connectivity(mesh);
    initialize_quadrics(mesh, options);
    if (options.method == "stmw") build_virtual_edges(mesh, options.virtual_radius);
    std::priority_queue<Candidate, std::vector<Candidate>, std::greater<>> queue;
    auto enqueue = [&](int a, int b) {
        if (a == b || !mesh.vertices[a].active || !mesh.vertices[b].active) return;
        queue.push(candidate_for(mesh, std::min(a, b), std::max(a, b), options));
    };
    for (std::size_t index = 0; index < mesh.vertices.size(); ++index) {
        for (const int neighbor : mesh.vertices[index].neighbors) {
            if (static_cast<int>(index) < neighbor) enqueue(static_cast<int>(index), neighbor);
        }
    }
    for (const auto& edge : mesh.virtual_edges) enqueue(edge.a, edge.b);

    std::size_t collapses = 0;
    std::size_t rejected = 0;
    std::vector<CollapseRecord> history;
    std::vector<CollapseRecord>* history_records = options.successive_map.empty() ? nullptr : &history;
    auto last_checkpoint = std::chrono::steady_clock::now();
    while (mesh.active_faces > options.target_faces && !queue.empty()) {
        Candidate current = queue.top();
        queue.pop();
        if (!mesh.vertices[current.a].active || !mesh.vertices[current.b].active) continue;
        if (mesh.vertices[current.a].revision != current.revision_a ||
            mesh.vertices[current.b].revision != current.revision_b) {
            if (edge_exists(mesh, current.a, current.b)) enqueue(current.a, current.b);
            continue;
        }
        if (!edge_exists(mesh, current.a, current.b)) continue;
        if (!collapse_valid(mesh, current)) {
            ++rejected;
            continue;
        }
        const std::vector<int> impacted = collapse(mesh, current, history_records);
        ++collapses;
        for (const int vertex : impacted) {
            for (const int neighbor : mesh.vertices[vertex].neighbors) enqueue(vertex, neighbor);
        }
        for (const auto& edge : mesh.virtual_edges) {
            if (edge.a == current.a || edge.b == current.a) enqueue(edge.a, edge.b);
        }
        const auto now = std::chrono::steady_clock::now();
        if (!options.checkpoint_dir.empty() &&
            (collapses % 10000 == 0 || now - last_checkpoint >= std::chrono::minutes(5))) {
            write_obj(mesh, options.checkpoint_dir / ("collapse-" + std::to_string(collapses) + ".obj"));
            last_checkpoint = now;
        }
        if (collapses % 10000 == 0) {
            std::cerr << "progress collapses=" << collapses << " faces=" << mesh.active_faces
                      << " rejected=" << rejected << '\n';
        }
    }
    std::cerr << "complete method=" << options.method << " faces=" << mesh.active_faces
              << " collapses=" << collapses << " rejected=" << rejected
              << " virtual_edges=" << mesh.virtual_edges.size() << '\n';
    if (!options.successive_map.empty()) write_successive_map(mesh, history, options.successive_map);
}

static Options parse_options(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--help") {
        std::cout << "paper_simplify --method qem4vr|stmw --input mesh.obj --output result.obj "
                     "--target-faces N [--checkpoint-dir DIR] [--virtual-radius R] "
                     "[--successive-map FILE]\n";
        std::exit(0);
    }
    Options options;
    for (int index = 1; index < argc; ++index) {
        const std::string key = argv[index];
        if (index + 1 >= argc) throw std::runtime_error("missing value for " + key);
        const std::string value = argv[++index];
        if (key == "--method") options.method = value;
        else if (key == "--input") options.input = value;
        else if (key == "--output") options.output = value;
        else if (key == "--target-faces") options.target_faces = std::stoull(value);
        else if (key == "--checkpoint-dir") options.checkpoint_dir = value;
        else if (key == "--successive-map") options.successive_map = value;
        else if (key == "--virtual-radius") options.virtual_radius = std::stod(value);
        else if (key == "--boundary-weight") options.boundary_weight = std::stod(value);
        else if (key == "--curvature-gain") options.curvature_gain = std::stod(value);
        else if (key == "--uv-weight") options.uv_weight = std::stod(value);
        else if (key == "--normal-weight") options.normal_weight = std::stod(value);
        else if (key == "--material-weight") options.material_weight = std::stod(value);
        else throw std::runtime_error("unknown option: " + key);
    }
    if (options.method != "qem4vr" && options.method != "stmw") {
        throw std::runtime_error("--method must be qem4vr or stmw");
    }
    if (options.input.empty() || options.output.empty() || options.target_faces == 0) {
        throw std::runtime_error("--input, --output, and --target-faces are required");
    }
    if (options.method != "stmw" && !options.successive_map.empty()) {
        throw std::runtime_error("--successive-map is only valid with --method stmw");
    }
    return options;
}

int main(int argc, char** argv) {
    try {
        const Options options = parse_options(argc, argv);
        Mesh mesh = load_obj(options.input);
        if (options.target_faces >= mesh.faces.size()) throw std::runtime_error("target must be below input face count");
        simplify(mesh, options);
        write_obj(mesh, options.output);
        return mesh.active_faces <= options.target_faces ? 0 : 2;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 1;
    }
}
