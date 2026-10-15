#include "autodiag/core.hpp"
#include <sstream>
#include <utility>
namespace autodiag {
void EventBus::subscribe(Callback callback){std::lock_guard<std::mutex> lock(mutex_); subscribers_.push_back(std::move(callback));}
void EventBus::publish(const Event& e){std::vector<Callback> copy;{std::lock_guard<std::mutex> lock(mutex_);copy=subscribers_;}for(const auto& cb:copy)cb(e);}
std::string health_name(Health h){switch(h){case Health::Healthy:return "healthy";case Health::Degraded:return "degraded";case Health::Failed:return "failed";default:return "unknown";}}
void HealthMonitor::update(bool known,bool severe,bool warning){Health next=!known?Health::Unknown:severe?Health::Failed:warning?Health::Degraded:Health::Healthy;if(next!=state_){state_=next;bus_.publish({"HEALTH_CHANGED",health_name(next)});}}
std::vector<Finding> GenericStrategy::inspect(const Endpoint& a,const Endpoint& b) const {
 std::vector<Finding> out;
 auto add=[&](std::string code,std::string evidence,std::string next){out.push_back({std::move(code),"error","Observed endpoint configuration mismatch",std::move(evidence),std::move(next)});};
 if(!a.domain.empty()&&!b.domain.empty()&&a.domain!=b.domain) add("DOMAIN_MISMATCH",a.domain+" != "+b.domain,"Check the ROS_DOMAIN_ID used by each process; compare from independently collected host snapshots.");
 if(!a.topic.empty()&&!b.topic.empty()&&a.topic!=b.topic)add("TOPIC_MISMATCH",a.topic+" != "+b.topic,"Confirm both endpoint topic names, including namespace and remapping.");
 if(!a.type.empty()&&!b.type.empty()&&a.type!=b.type)add("TYPE_MISMATCH",a.type+" != "+b.type,"Check publisher and subscriber ROS interface types.");
 if(a.reliability=="best_effort"&&b.reliability=="reliable")add("QOS_RELIABILITY", "best_effort publisher cannot satisfy reliable subscriber", "Change the subscriber request if best-effort delivery is acceptable.");
 if(a.durability=="volatile"&&b.durability=="transient_local")add("QOS_DURABILITY","volatile publisher cannot satisfy transient_local subscriber","Use a volatile subscription or an appropriate durable publisher.");
 return out;
}
void StrategyRegistry::add(std::unique_ptr<DiagnosticStrategy> strategy){strategies_.push_back(std::move(strategy));}
std::vector<Finding> StrategyRegistry::diagnose(const Endpoint& a,const Endpoint& b) const{std::vector<Finding> all;for(const auto& s:strategies_){auto f=s->inspect(a,b);all.insert(all.end(),f.begin(),f.end());}return all;}
static std::string escape(std::string s){std::string out;for(char c:s){switch(c){case '"':out+="\\\"";break;case '\\':out+="\\\\";break;case '\n':out+="\\n";break;case '\r':out+="\\r";break;case '\t':out+="\\t";break;default:if(static_cast<unsigned char>(c)>=32)out+=c;}}return out;}
std::string json_report(const Endpoint& a,const Endpoint& b,const std::vector<Finding>& findings,Health h){
 std::ostringstream o;o<<"{\"source\":\"cpp_core\",\"health\":\""<<health_name(h)<<"\",\"verified_delivery\":false,\"scope\":\"provided_configuration_only\",\"a\":{\"domain\":\""<<escape(a.domain)<<"\",\"vendor\":\""<<escape(a.vendor)<<"\"},\"b\":{\"domain\":\""<<escape(b.domain)<<"\",\"vendor\":\""<<escape(b.vendor)<<"\"},\"findings\":[";
 for(size_t i=0;i<findings.size();++i){auto& f=findings[i];if(i)o<<',';o<<"{\"code\":\""<<escape(f.code)<<"\",\"severity\":\""<<escape(f.severity)<<"\",\"evidence\":\""<<escape(f.evidence)<<"\",\"next_test\":\""<<escape(f.next_test)<<"\"}";}
 o<<"]}";return o.str();
}
}
