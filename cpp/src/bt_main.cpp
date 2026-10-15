#include "autodiag/core.hpp"
#include <behaviortree_cpp/bt_factory.h>
#include <iostream>
#include <memory>
#include <string>
// Emits JSON-line diagnostic events. SUCCESS means check executed, not DDS is healthy.
int main(int argc, char** argv) {
  const bool inject_fault = argc > 1 && std::string(argv[1]) == "--fault";
  autodiag::Endpoint a{"8", "/robot_pose", "geometry_msgs/msg/PoseStamped", "best_effort", "volatile", "Fast DDS"};
  autodiag::Endpoint b{"8", "/robot_pose", "geometry_msgs/msg/PoseStamped", inject_fault ? "reliable" : "best_effort", "volatile", "Cyclone DDS"};
  autodiag::StrategyRegistry strategies;
  strategies.add(std::make_unique<autodiag::GenericStrategy>());
  std::vector<autodiag::Finding> findings;
  int seq = 0;
  auto emit = [&](const std::string& node, const std::string& status) {
    std::cout << "{\"event\":\"bt_transition\",\"seq\":" << ++seq
              << ",\"node\":\"" << node << "\",\"status\":\"" << status << "\"}" << std::endl;
  };
  BT::BehaviorTreeFactory factory;
  factory.registerSimpleAction("CollectEvidence", [&](BT::TreeNode&) {
    emit("collect", "RUNNING");
    emit("collect", "SUCCESS");
    return BT::NodeStatus::SUCCESS;
  });
  factory.registerSimpleAction("DiagnoseQoS", [&](BT::TreeNode&) {
    emit("qos", "RUNNING");
    findings = strategies.diagnose(a, b);
    emit("qos", "SUCCESS");
    return BT::NodeStatus::SUCCESS;
  });
  factory.registerSimpleAction("Report", [&](BT::TreeNode&) {
    emit("report", "RUNNING");
    emit("report", "SUCCESS");
    return BT::NodeStatus::SUCCESS;
  });
  const char* xml = R"(<root BTCPP_format="4"><BehaviorTree ID="Main"><Sequence><CollectEvidence/><DiagnoseQoS/><Report/></Sequence></BehaviorTree></root>)";
  auto tree = factory.createTreeFromText(xml);
  emit("root", "RUNNING");
  auto bt_status = tree.tickOnce();
  emit("root", bt_status == BT::NodeStatus::SUCCESS ? "SUCCESS" : "FAILURE");
  // Report findings separately; no custom freeform strings in the JSONL event stream.
  std::cout << "{\"event\":\"diagnosis\",\"issue_count\":" << findings.size() << "}" << std::endl;
  return bt_status == BT::NodeStatus::SUCCESS ? 0 : 1;
}
