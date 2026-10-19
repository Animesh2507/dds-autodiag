# Lab image: existing AutoDiag image plus Cyclone DDS.
# Isolated from any host ROS graph by using ROS_DOMAIN_ID=87 at runtime.
FROM dds-autodiag:test
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ros-jazzy-rmw-cyclonedds-cpp \
      ros-jazzy-rmw-zenoh-cpp \
 && rm -rf /var/lib/apt/lists/*
USER autodiag
ENTRYPOINT ["/ros_entrypoint.sh"]
CMD ["dds-autodiag", "doctor"]
