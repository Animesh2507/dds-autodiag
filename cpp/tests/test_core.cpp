#include "autodiag/core.hpp"
#include <cassert>
#include <memory>
#include <iostream>
int main(){
 autodiag::StrategyRegistry reg;reg.add(std::make_unique<autodiag::GenericStrategy>());
 autodiag::Endpoint a{"8","/pose","T","best_effort","volatile","Fast DDS"};
 autodiag::Endpoint b{"9","/pose","T","reliable","transient_local","Cyclone DDS"};
 auto f=reg.diagnose(a,b);assert(f.size()==3);
 b.domain="8";b.reliability="best_effort";b.durability="volatile";assert(reg.diagnose(a,b).empty());
 autodiag::EventBus bus;autodiag::HealthMonitor health(bus);int n=0;bus.subscribe([&](const autodiag::Event&){++n;});
 health.update(false,false,false);assert(n==0);health.update(true,false,false);assert(n==1);health.update(true,false,false);assert(n==1);
 health.update(true,true,false);assert(n==2);
 auto json=autodiag::json_report(a,b,f,autodiag::Health::Degraded);assert(json.find("RELIABILITY_MISMATCH")!=std::string::npos);
 std::cout<<"C++ core tests passed\n";
}
