#!/bin/bash
# Zenoh peer: its own router. DDS nodes never discover these topics.
set -e
source /opt/ros/jazzy/setup.bash
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
ros2 run rmw_zenoh_cpp rmw_zenohd &
sleep 2
dds-autodiag serve --host 127.0.0.1 --port "${AUTODIAG_PORT:-18093}" --log-level warning &
ros2 topic pub -r 1 -n lab_zenoh --qos-reliability reliable --qos-durability volatile \
  /lab/zenoh std_msgs/msg/String '{data: zenoh-ok}' &
wait
