#include "autodiag/core.hpp"
#include <iostream>
#include <memory>
#include <string>
int main(int argc,char** argv){
 if(argc!=13){std::cerr<<"Usage: autodiag_core_cli <domain_a> <domain_b> <topic_a> <topic_b> <type_a> <type_b> <reliability_a> <reliability_b> <durability_a> <durability_b> <vendor_a> <vendor_b>\n";return 2;}
 autodiag::Endpoint a{argv[1],argv[3],argv[5],argv[7],argv[9],argv[11]};
 autodiag::Endpoint b{argv[2],argv[4],argv[6],argv[8],argv[10],argv[12]};
 autodiag::EventBus events;autodiag::HealthMonitor monitor(events);
 autodiag::StrategyRegistry registry;registry.add(std::make_unique<autodiag::GenericStrategy>());
 auto findings=registry.diagnose(a,b);
 // A clean configuration is not proof of DDS discovery or sample delivery.
 monitor.update(false,!findings.empty(),false);
 std::cout<<autodiag::json_report(a,b,findings,findings.empty()?autodiag::Health::Unknown:autodiag::Health::Degraded)<<'\n';
}
