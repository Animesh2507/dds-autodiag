# DDS AutoDiag in a ROS 2 Jazzy image.
# Run with host networking/IPC so DDS discovery sees the same graph as the host:
#   docker run --rm --net=host --ipc=host ros2-dds-autodiag            # dashboard on 127.0.0.1:8080
#   docker run --rm --net=host --ipc=host ros2-dds-autodiag check      # one-shot CLI check
ARG ROS_DISTRO=jazzy
FROM ros:${ROS_DISTRO}-ros-base

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3-pip python3-venv iproute2 cmake g++ \
    ros-${ROS_DISTRO}-behaviortree-cpp ros-${ROS_DISTRO}-demo-nodes-cpp \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/autodiag
COPY pyproject.toml README.md LICENSE ./
COPY autodiag ./autodiag
COPY cpp ./cpp
RUN python3 -m venv --system-site-packages /opt/autodiag/venv \
 && /opt/autodiag/venv/bin/pip install --no-cache-dir . \
 && . /opt/ros/${ROS_DISTRO}/setup.sh \
 && cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release && cmake --build cpp/build -j"$(nproc)"

ENV PATH=/opt/autodiag/venv/bin:$PATH \
    AUTODIAG_CPP_BINARY=/opt/autodiag/cpp/build/autodiag_core_cli \
    AUTODIAG_BT_BINARY=/opt/autodiag/cpp/build/autodiag_bt

RUN useradd --create-home autodiag
USER autodiag
HEALTHCHECK --interval=30s --timeout=5s CMD python3 -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('AUTODIAG_PORT','8080')+'/api/healthz',timeout=3)"
# /ros_entrypoint.sh (from the base image) sources ROS 2 before running the command.
ENTRYPOINT ["/ros_entrypoint.sh", "dds-autodiag"]
CMD ["serve"]
