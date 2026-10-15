#pragma once
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
namespace autodiag {
enum class Health { Unknown, Healthy, Degraded, Failed };
struct Endpoint { std::string domain, topic, type, reliability, durability, vendor; };
struct Finding { std::string code, severity, explanation, evidence, next_test; };
struct Event { std::string type, detail; };
class EventBus {
public:
 using Callback=std::function<void(const Event&)>;
 void subscribe(Callback callback);
 void publish(const Event& event);
private:
 std::mutex mutex_;
 std::vector<Callback> subscribers_;
};
class HealthMonitor {
public:
 explicit HealthMonitor(EventBus& bus):bus_(bus){}
 Health state() const {return state_;}
 void update(bool known, bool severe, bool warning);
private:
 EventBus& bus_;
 Health state_=Health::Unknown;
};
class DiagnosticStrategy {
public:
 virtual ~DiagnosticStrategy()=default;
 virtual std::string name() const=0;
 virtual std::vector<Finding> inspect(const Endpoint&,const Endpoint&) const=0;
};
class GenericStrategy final:public DiagnosticStrategy {
public:
 std::string name() const override {return "generic_dds";}
 std::vector<Finding> inspect(const Endpoint&,const Endpoint&) const override;
};
class StrategyRegistry {
public:
 void add(std::unique_ptr<DiagnosticStrategy> strategy);
 std::vector<Finding> diagnose(const Endpoint&,const Endpoint&) const;
private:
 std::vector<std::unique_ptr<DiagnosticStrategy>> strategies_;
};
std::string json_report(const Endpoint&,const Endpoint&,const std::vector<Finding>&, Health);
std::string health_name(Health h);
}
