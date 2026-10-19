#!/bin/bash
# Cyclone stack: mix of good links, QoS faults, a type mismatch, and a waiting subscriber.
set -e
source /opt/ros/jazzy/setup.bash
dds-autodiag serve --host 127.0.0.1 --port "${AUTODIAG_PORT:-18090}" --log-level warning &
# Broken: reliable reader on best-effort lidar
ros2 topic echo --qos-reliability reliable --qos-durability volatile /lab/scan std_msgs/msg/String &
# Warning: volatile reader on latched map
ros2 topic echo --qos-reliability reliable --qos-durability volatile /lab/map std_msgs/msg/String &
# Good: matching odom
ros2 topic echo --qos-reliability reliable --qos-durability volatile /lab/odom std_msgs/msg/String &
# Broken: reliable reader on best-effort camera
ros2 topic echo --qos-reliability reliable --qos-durability volatile /lab/camera std_msgs/msg/String &
# Good: matching camera reader (best effort) — second subscriber
ros2 topic echo --qos-reliability best_effort --qos-durability volatile /lab/camera std_msgs/msg/String &
# Type mismatch: Int32 reader on a String publisher
ros2 topic echo --qos-reliability reliable --qos-durability volatile /lab/status std_msgs/msg/Int32 &
# Waiting: nobody publishes this
ros2 topic echo --qos-reliability reliable --qos-durability volatile /lab/amcl_pose std_msgs/msg/String &
# Healthy command publisher
ros2 topic pub -r 1 -n lab_nav --qos-reliability reliable --qos-durability volatile \
  /lab/cmd_vel std_msgs/msg/String '{data: cmd}' &
wait
