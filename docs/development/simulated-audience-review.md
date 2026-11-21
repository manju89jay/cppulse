# Simulated developer evaluations

On 20 November 2026, ten simulated audiences tried bounded cppulse workflows.
This summary is derived from the retained coordinator report, SHA-256
`2aa7681ee33936cf211d903bb66cac4ae758c245da823aeca8905f6863d50ac4`.
The source links identify pinned upstream inputs. The trial outcomes come from
the retained coordinator records. No upstream maintainer participated.

| Simulated audience and pinned source | What the trial established and where it stopped |
| --- | --- |
| R01 Gazebo plugin maintainer · [Gazebo](https://github.com/gazebosim/gz-sim/tree/18aa48fe7dc98a3d82216c8aab3f2c57eb97ff48) | The source probe could not resolve `gz/sim/System.hh`. Analysis and runtime checks did not run. |
| R02 ROS navigation maintainer · [Nav2](https://github.com/ros-navigation/navigation2/tree/c7046550547d382a5186d106b0895eda02485d7c) | The source probe could not resolve `nav2_util/lifecycle_node.hpp`. The ROS/ament analysis and test workflow remained unexecuted. |
| R03 Automotive algorithms developer · [Autoware Core](https://github.com/autowarefoundation/autoware_core/tree/5efdfd4461ae06e8ca4b4738c104061a490fab85) | Three interpolation tests passed before and after an experimental local reserve edit. One translation unit parsed with zero findings and unavailable health. No speedup was established. |
| R04 Reusable-library release maintainer · [fmt 10.2.1](https://github.com/fmtlib/fmt/tree/e69e5f977d458f2650bb346dadf2ad30c5320281) | Compiled and header-only consumers and two selected upstream cases passed. Analysis was partial. An indexed argv-loop suggestion was judged noisy. |
| R05 Header-only library maintainer · [nlohmann/json 3.11.3](https://github.com/nlohmann/json/tree/9cca280a4d0ccf0c08f47a99aa71d1b0e52f8d03) | Two macro contexts and 15 upstream diagnostic cases passed. Both analyses were partial and did not measure the header bodies. Two intentional void-discard hints were judged noisy. |
| R06 Concurrency and performance engineer · [oneTBB](https://github.com/uxlfoundation/oneTBB/tree/45587e94dfb6dfe00220c5f520020a5bc745e92f) | A consumer and three official cases passed. Analysis hit the external 180-second harness timeout, with no structured result. The JUnit total of 1,150,707 represented assertions. |
| R07 Platform and library infrastructure engineer · [Abseil](https://github.com/abseil/abseil-cpp/tree/4447c7562e3bc702ade25105912dce503f0c4010) | Five consumer checks and five unchanged upstream test bodies passed in a disclosed direct-source build. Analysis hit the external 180-second harness timeout, with no structured result. |
| R08 Serialization and RPC engineer · [Cap'n Proto KJ](https://github.com/capnproto/capnproto/tree/1a0e12c0a3ba1f0dbbad45ddfef555166e0a14fc) | Three GNU++14 syntax contexts passed. The original partial analysis omitted two declared `.c++` units and analyzed only `consumer.cpp`. It reported noisy hints for a project-qualified `kj/string.h` include and an intentional void discard. |
| R09 Task-runtime maintainer · [Taskflow](https://github.com/taskflow/taskflow/tree/45366fe5bc4f2f8ec9aa590b40c504e296886865) | Inputs were prepared and pinned. Storage admission refused executable stages, leaving no analysis or runtime result. |
| R10 Security-sensitive codec maintainer · [libjxl](https://github.com/libjxl/libjxl/tree/5a7da83447212fe4900fc29ce97430b881caa67e) | Inputs were prepared and pinned. Storage admission refused executable stages, leaving no analysis or runtime result. |

Six trials invoked analysis. Four returned structured partial results and two
timed out. Two additional trials lacked SDKs and two stopped at storage
admission. Five had passing bounded runtime checks, which overlap the analysis
categories. Adoption and upstream readiness remain unestablished, and
HUMAN-USEFULNESS remains blocked.

[PR #12](https://github.com/manju89jay/cppulse/pull/12) addressed three
priorities from this review. It added a truthful entry point and finite first
trial, repaired the `.c++` inventory, and tightened three modernization
checks. The later fmt, JSON and KJ replays executed eight selected translation
units without parse errors. All four public analyses still returned partial,
exit 3, because dependency and context closure were unverified. The other
trials retain their original limits. The [LevelDB showcase](../examples/leveldb/README.md)
comes from a separate historical run. [Repair and replay record](reviewer-fixes.md)
