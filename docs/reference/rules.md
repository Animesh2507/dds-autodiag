# Diagnostic rules

DDS AutoDiag has **23 rules**. Each finding includes its evidence, a next step and, where one applies, official documentation. `dds-autodiag selftest` runs every rule against its synthetic faults (27 fixtures) on any installation.

!!! info "Generated from the rule engine"
    Severity, summary, next step and documentation on this page are produced by running each rule's self-test
    fixture (`python -m autodiag.rules_doc`). A test fails if the page and the code disagree.

| Code | Severity | Needs |
|---|---|---|
| [`ROS_ENV_NOT_SOURCED`](#ros_env_not_sourced) | :material-close-circle:{ style="color:#c2304a" } problem | this host |
| [`INVALID_DOMAIN_ID`](#invalid_domain_id) | :material-close-circle:{ style="color:#c2304a" } problem | this host |
| [`DOMAIN_ID_OUTSIDE_SAFE_RANGE`](#domain_id_outside_safe_range) | :material-alert:{ style="color:#a86400" } warning | this host |
| [`NO_NETWORK_INTERFACES`](#no_network_interfaces) | :material-alert:{ style="color:#a86400" } warning | this host |
| [`DOMAIN_MISMATCH`](#domain_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | two snapshots |
| [`LOCALHOST_ONLY`](#localhost_only) | :material-close-circle:{ style="color:#c2304a" } problem | two snapshots |
| [`DISCOVERY_RANGE_RESTRICTED`](#discovery_range_restricted) | :material-close-circle:{ style="color:#c2304a" } problem | two snapshots |
| [`DISCOVERY_DISABLED`](#discovery_disabled) | :material-alert:{ style="color:#a86400" } warning | this host |
| [`ROS_LOCALHOST_ONLY_DEPRECATED`](#ros_localhost_only_deprecated) | :material-information:{ style="color:#2f6fd0" } note | this host |
| [`MULTICAST_CAPABILITY_ABSENT`](#multicast_capability_absent) | :material-alert:{ style="color:#a86400" } warning | two snapshots |
| [`RMW_MISMATCH`](#rmw_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem / :material-alert:{ style="color:#a86400" } warning | two snapshots |
| [`DISTRO_MISMATCH`](#distro_mismatch) | :material-alert:{ style="color:#a86400" } warning | two snapshots |
| [`DDS_CONFIG_FILE_MISSING`](#dds_config_file_missing) | :material-close-circle:{ style="color:#c2304a" } problem | this host |
| [`CYCLONE_CONFIG_RMW_MISMATCH`](#cyclone_config_rmw_mismatch) | :material-alert:{ style="color:#a86400" } warning | this host |
| [`RELIABILITY_MISMATCH`](#reliability_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | topic inspection |
| [`DURABILITY_MISMATCH`](#durability_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | topic inspection |
| [`LATCHED_DATA_VOLATILE_SUBSCRIBER`](#latched_data_volatile_subscriber) | :material-alert:{ style="color:#a86400" } warning | topic inspection |
| [`TYPE_MISMATCH`](#type_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | topic inspection |
| [`SHM_IPC_NAMESPACE_DIFFERENCE`](#shm_ipc_namespace_difference) | :material-close-circle:{ style="color:#c2304a" } problem | two snapshots, `--transport dds_shm` |
| [`SHM_NAMESPACE_UNVERIFIED`](#shm_namespace_unverified) | :material-alert:{ style="color:#a86400" } warning | in a container, `--transport dds_shm` |
| [`INTRA_PROCESS_SEPARATE_PROCESSES`](#intra_process_separate_processes) | :material-close-circle:{ style="color:#c2304a" } problem | two snapshots, `--transport intra_process` |
| [`INTRA_PROCESS_NOT_AUTODETECTABLE`](#intra_process_not_autodetectable) | :material-information:{ style="color:#2f6fd0" } note | `--transport intra_process` |
| [`UNKNOWN_TRANSPORT_MODE`](#unknown_transport_mode) | :material-alert:{ style="color:#a86400" } warning | this host |

## Environment

### `ROS_ENV_NOT_SOURCED` {#ros_env_not_sourced}

**ros2 CLI found, but the ROS 2 environment is not sourced**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | Everything shows as unknown; `ros2` works in one terminal but not in the one running AutoDiag. |
| Runs with | this host |
| Next step | Run "source /opt/ros/<distro>/setup.bash" in the shell that starts AutoDiag (and your nodes), then restart it. |
| Documentation | [ROS 2 installation troubleshooting](https://docs.ros.org/en/jazzy/How-To-Guides/Installation-Troubleshooting.html) |

### `INVALID_DOMAIN_ID` {#invalid_domain_id}

**ROS_DOMAIN_ID is not a valid domain ID**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | Nodes fail to start or join an unexpected domain. |
| Runs with | this host |
| Next step | Use an integer from 0 to 101 (safe range on Linux). |
| Documentation | [ROS 2 domain IDs](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Domain-ID.html) |

### `DOMAIN_ID_OUTSIDE_SAFE_RANGE` {#domain_id_outside_safe_range}

**ROS_DOMAIN_ID is above the range recommended for Linux**

| | |
|---|---|
| Severity | :material-alert:{ style="color:#a86400" } warning (confidence: high) |
| Symptom | Intermittent discovery failures or port conflicts on Linux. |
| Runs with | this host |
| Next step | Domain IDs above 101 may collide with ephemeral ports on Linux; prefer 0 to 101. |
| Documentation | [ROS 2 domain IDs](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Domain-ID.html) |

### `NO_NETWORK_INTERFACES` {#no_network_interfaces}

**No network interface information obtained**

| | |
|---|---|
| Severity | :material-alert:{ style="color:#a86400" } warning (confidence: medium) |
| Symptom | Network-related checks are skipped. |
| Runs with | this host |
| Next step | Run diagnostics on a Linux host with iproute2 available. |
| Documentation | [ROS 2 installation troubleshooting](https://docs.ros.org/en/jazzy/How-To-Guides/Installation-Troubleshooting.html) |

## Discovery

### `DOMAIN_MISMATCH` {#domain_mismatch}

**Different ROS_DOMAIN_ID values**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | Two machines or containers never see each other's nodes or topics. |
| Runs with | two snapshots |
| Next step | Use a consistent ROS_DOMAIN_ID across intended peers, then restart managed processes. |
| Documentation | [ROS 2 domain IDs](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Domain-ID.html) |

### `LOCALHOST_ONLY` {#localhost_only}

**A host is configured for localhost-only discovery**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | Everything works on one machine, nothing across machines. |
| Runs with | two snapshots |
| Next step | Review ROS_LOCALHOST_ONLY and ROS_AUTOMATIC_DISCOVERY_RANGE; allow remote discovery when appropriate. |
| Documentation | [ROS 2 installation troubleshooting](https://docs.ros.org/en/jazzy/How-To-Guides/Installation-Troubleshooting.html) |

### `DISCOVERY_RANGE_RESTRICTED` {#discovery_range_restricted}

**Automatic discovery range prevents discovery between these hosts**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | Everything works on one machine, nothing across machines (Jazzy and newer). |
| Runs with | two snapshots |
| Next step | Set ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET on both peers, or list peers in ROS_STATIC_PEERS. |
| Documentation | [ROS 2 improved dynamic discovery](https://docs.ros.org/en/jazzy/Tutorials/Advanced/Improved-Dynamic-Discovery.html) |

### `DISCOVERY_DISABLED` {#discovery_disabled}

**Automatic discovery is disabled and no static peers are configured**

| | |
|---|---|
| Severity | :material-alert:{ style="color:#a86400" } warning (confidence: high) |
| Symptom | No other node is ever discovered. |
| Runs with | this host |
| Next step | Set ROS_AUTOMATIC_DISCOVERY_RANGE to LOCALHOST or SUBNET, or configure ROS_STATIC_PEERS. |
| Documentation | [ROS 2 improved dynamic discovery](https://docs.ros.org/en/jazzy/Tutorials/Advanced/Improved-Dynamic-Discovery.html) |

### `ROS_LOCALHOST_ONLY_DEPRECATED` {#ros_localhost_only_deprecated}

**ROS_LOCALHOST_ONLY is deprecated on this distribution**

| | |
|---|---|
| Severity | :material-information:{ style="color:#2f6fd0" } note (confidence: high) |
| Symptom | A legacy variable is still set; behaviour may differ from what you expect. |
| Runs with | this host |
| Next step | Use ROS_AUTOMATIC_DISCOVERY_RANGE (LOCALHOST, SUBNET or OFF) instead. |
| Documentation | [ROS 2 improved dynamic discovery](https://docs.ros.org/en/jazzy/Tutorials/Advanced/Improved-Dynamic-Discovery.html) |

### `MULTICAST_CAPABILITY_ABSENT` {#multicast_capability_absent}

**Neither snapshot reports a multicast-capable interface**

| | |
|---|---|
| Severity | :material-alert:{ style="color:#a86400" } warning (confidence: medium) |
| Symptom | Discovery across hosts fails on networks or VPNs without multicast. |
| Runs with | two snapshots |
| Next step | Check whether discovery uses static unicast peers or discovery server; multicast flags alone do not prove network delivery. |
| Documentation | [Cyclone DDS discovery](https://cyclonedds.io/docs/cyclonedds/latest/config/discovery-config.html) |

## Middleware & versions

### `RMW_MISMATCH` {#rmw_mismatch}

**Peers use different RMW implementations (Zenoh cannot talk to DDS-based RMWs)**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high): Zenoh RMW peer talking to a DDS RMW peer<br>:material-alert:{ style="color:#a86400" } warning (confidence: medium): Two different DDS RMWs (usually interoperable) |
| Symptom | Peers don't see each other at all (Zenoh vs DDS), or behave inconsistently across DDS vendors. |
| Runs with | two snapshots |
| Next step | Use the same RMW_IMPLEMENTATION on all peers.<br>Cross-vendor DDS interoperability usually works, but use the same RMW_IMPLEMENTATION where possible to rule it out. |
| Documentation | [Working with multiple RMW implementations](https://docs.ros.org/en/jazzy/How-To-Guides/Working-with-multiple-RMW-implementations.html) |

### `DISTRO_MISMATCH` {#distro_mismatch}

**Peers run different ROS 2 distributions**

| | |
|---|---|
| Severity | :material-alert:{ style="color:#a86400" } warning (confidence: medium) |
| Symptom | Some topics or services fail between machines, often with type or QoS-default differences. |
| Runs with | two snapshots |
| Next step | Communication across ROS 2 distributions is not officially supported; message definitions and defaults can differ. |
| Documentation | [ROS 2 distributions](https://docs.ros.org/en/jazzy/Releases.html) |

### `DDS_CONFIG_FILE_MISSING` {#dds_config_file_missing}

**DDS configuration file could not be found**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | Your DDS tuning (interfaces, peers, SHM) silently doesn't apply. |
| Runs with | this host |
| Next step | Correct the path or ensure the file is mounted inside the container. |
| Documentation | [Cyclone DDS network interfaces](https://cyclonedds.io/docs/cyclonedds/latest/config/network_interfaces.html) · [Fast DDS shared memory transport](https://fast-dds.docs.eprosima.com/en/stable/fastdds/transport/shared_memory/shared_memory.html) |

### `CYCLONE_CONFIG_RMW_MISMATCH` {#cyclone_config_rmw_mismatch}

**CycloneDDS configuration supplied while another RMW is selected**

| | |
|---|---|
| Severity | :material-alert:{ style="color:#a86400" } warning (confidence: medium) |
| Symptom | Cyclone DDS settings have no effect because another RMW is active. |
| Runs with | this host |
| Next step | Check RMW_IMPLEMENTATION and remove or correct unused DDS configuration. |
| Documentation | [Cyclone DDS network interfaces](https://cyclonedds.io/docs/cyclonedds/latest/config/network_interfaces.html) |

## QoS & types (live topics)

### `RELIABILITY_MISMATCH` {#reliability_mismatch}

**Incompatible reliability: publisher_node → subscriber_node**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | The topic is listed and both endpoints exist, but no message arrives. |
| Runs with | topic inspection |
| Next step | Review requested/offered QoS policies. Do not change semantics blindly. |
| Documentation | [ROS 2 QoS](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html) |

### `DURABILITY_MISMATCH` {#durability_mismatch}

**Incompatible durability: publisher_node → subscriber_node**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | The subscriber never receives anything: it requests Transient Local, but the publisher only offers Volatile. |
| Runs with | topic inspection |
| Next step | Review requested/offered QoS policies. Do not change semantics blindly. |
| Documentation | [ROS 2 QoS](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html) |

### `LATCHED_DATA_VOLATILE_SUBSCRIBER` {#latched_data_volatile_subscriber}

**subscriber_node requests Volatile from latched (Transient Local) publisher publisher_node**

| | |
|---|---|
| Severity | :material-alert:{ style="color:#a86400" } warning (confidence: high) |
| Symptom | Data published before the subscriber started never arrives; the classic empty map in RViz. The QoS is compatible, so ROS reports no error. |
| Runs with | topic inspection |
| Next step | Request Transient Local durability on the subscriber (e.g. RViz Map display: Topic → Durability Policy) so it receives the last message even when it starts later. |
| Documentation | [ROS 2 QoS](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html) |

### `TYPE_MISMATCH` {#type_mismatch}

**Different message types on this topic**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | Endpoints never match, or tools report type errors on the topic. |
| Runs with | topic inspection |
| Next step | Use matching interface types and type definitions. |
| Documentation | [ROS 2 interfaces](https://docs.ros.org/en/jazzy/Concepts/Basic/About-Interfaces.html) |

## Transport

### `SHM_IPC_NAMESPACE_DIFFERENCE` {#shm_ipc_namespace_difference}

**Containers have different IPC namespaces**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | Containers on one host discover each other but large messages never arrive. |
| Runs with | two snapshots, `--transport dds_shm` |
| Next step | Use supported shared IPC configuration only if needed and approved; otherwise prefer UDP transport. |
| Documentation | [Fast DDS shared memory in Docker](https://fast-dds.docs.eprosima.com/en/stable/docker/shm_docker.html) |

### `SHM_NAMESPACE_UNVERIFIED` {#shm_namespace_unverified}

**Container shared-memory namespace compatibility is unverified**

| | |
|---|---|
| Severity | :material-alert:{ style="color:#a86400" } warning (confidence: medium) |
| Symptom | Shared memory may silently fall back to UDP, or fail inside containers. |
| Runs with | in a container, `--transport dds_shm` |
| Next step | Check actual IPC namespace sharing between the two containers and vendor SHM settings; do not assume SHM is available. |
| Documentation | [Fast DDS shared memory in Docker](https://fast-dds.docs.eprosima.com/en/stable/docker/shm_docker.html) |

### `INTRA_PROCESS_SEPARATE_PROCESSES` {#intra_process_separate_processes}

**Intra-process delivery cannot connect different processes**

| | |
|---|---|
| Severity | :material-close-circle:{ style="color:#c2304a" } problem (confidence: high) |
| Symptom | Zero-copy intra-process delivery is expected but the nodes run in different processes. |
| Runs with | two snapshots, `--transport intra_process` |
| Next step | Use DDS shared memory or UDP/TCP for cross-process communications. |
| Documentation | [ROS 2 intra-process communication](https://docs.ros.org/en/jazzy/Tutorials/Demos/Intra-Process-Communication.html) |

### `INTRA_PROCESS_NOT_AUTODETECTABLE` {#intra_process_not_autodetectable}

**ROS 2 intra-process communication is a per-node/process decision**

| | |
|---|---|
| Severity | :material-information:{ style="color:#2f6fd0" } note (confidence: medium) |
| Symptom | You expect intra-process communication; this can't be confirmed from outside. |
| Runs with | `--transport intra_process` |
| Next step | Confirm publisher/subscriber are in the same process and intra-process communication is enabled in node options; DDS transport cannot prove this. |
| Documentation | [ROS 2 intra-process communication](https://docs.ros.org/en/jazzy/Tutorials/Demos/Intra-Process-Communication.html) |

### `UNKNOWN_TRANSPORT_MODE` {#unknown_transport_mode}

**Unknown requested transport mode**

| | |
|---|---|
| Severity | :material-alert:{ style="color:#a86400" } warning (confidence: medium) |
| Symptom | The requested transport mode is not recognised. |
| Runs with | this host |
| Next step | Use auto, intra_process, dds_shm, dds_udp or dds_tcp. |
| Documentation | — |

## Endpoint check

**Check endpoint** in the dashboard (`POST /api/endpoint-check`) compares a publisher and a subscriber that you
describe by hand, without a running ROS graph. It uses the native C++ core when it is built, otherwise a Python
fallback, and reports a smaller set of codes:

| Code | Severity | Meaning |
|---|---|---|
| [`DOMAIN_MISMATCH`](#domain_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | The two domain IDs differ. |
| `TOPIC_MISMATCH` | :material-close-circle:{ style="color:#c2304a" } problem | The topic names differ (check namespaces and remapping). |
| [`TYPE_MISMATCH`](#type_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | The message types differ. |
| [`RELIABILITY_MISMATCH`](#reliability_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | Best-effort publisher, reliable subscriber. |
| [`DURABILITY_MISMATCH`](#durability_mismatch) | :material-close-circle:{ style="color:#c2304a" } problem | Volatile publisher, transient-local subscriber. |

These are not counted separately in the rules above: `TOPIC_MISMATCH` only exists here, because a live topic
inspection always looks at one topic name.
