#!/bin/bash
# Cyclone "robot": sensors + a healthy odom + a status topic (wrong type on the other side).
set -e
source /opt/ros/jazzy/setup.bash
dds-autodiag serve --host 127.0.0.1 --port "${AUTODIAG_PORT:-18089}" --log-level warning &
ros2 topic pub -r 2 -n lab_lidar --qos-reliability best_effort --qos-durability volatile \
  /lab/scan std_msgs/msg/String '{data: scan}' &
ros2 topic pub -r 1 -n lab_map --qos-reliability reliable --qos-durability transient_local \
  /lab/map std_msgs/msg/String '{data: latched-map}' &
ros2 topic pub -r 2 -n lab_odom --qos-reliability reliable --qos-durability volatile \
  /lab/odom std_msgs/msg/String '{data: odom-ok}' &
ros2 topic pub -r 1 -n lab_camera --qos-reliability best_effort --qos-durability volatile \
  /lab/camera std_msgs/msg/String '{data: image}' &
ros2 topic pub -r 1 -n lab_status --qos-reliability reliable --qos-durability volatile \
  /lab/status std_msgs/msg/String '{data: status-string}' &
wait
