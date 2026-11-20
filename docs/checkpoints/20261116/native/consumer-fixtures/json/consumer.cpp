// Explicit supplemental header-only consumer; original upstream source stays intact.
#include <nlohmann/json.hpp>

int main() {
    const auto value = nlohmann::json::parse("{\"ready\":true,\"values\":[2,3,5]}");
    if (!value.at("ready").get<bool>()) return 1;
    if (value.at("values").size() != 3) return 2;
    if (value.at("values").at(2).get<int>() != 5) return 3;
    return 0;
}
