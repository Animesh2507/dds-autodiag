"""Start the DDS AutoDiag server and RViz2 with the AutoDiag panel in one command.

    ros2 launch rviz_autodiag_panel autodiag.launch.py
    ros2 launch rviz_autodiag_panel autodiag.launch.py port:=8090
    ros2 launch rviz_autodiag_panel autodiag.launch.py start_server:=false   # server already running

`dds-autodiag` must be on PATH (activate the virtual environment it is installed in first).
Closing RViz also stops the server started by this launch file.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, LogInfo, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = get_package_share_directory('rviz_autodiag_panel')
    port = LaunchConfiguration('port')
    start_server = LaunchConfiguration('start_server')

    server = ExecuteProcess(
        cmd=[LaunchConfiguration('server_cmd'), 'serve', '--port', port],
        name='autodiag_server', output='screen', condition=IfCondition(start_server))

    rviz = Node(
        package='rviz2', executable='rviz2', name='rviz2', output='screen',
        arguments=['-d', LaunchConfiguration('rviz_config')],
        additional_env={'AUTODIAG_SERVER_URL': ['http://127.0.0.1:', port]})

    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='8080', description='Port of the AutoDiag server'),
        DeclareLaunchArgument('start_server', default_value='true',
                              description='Start the AutoDiag server (false if one is already running)'),
        DeclareLaunchArgument('server_cmd', default_value='dds-autodiag',
                              description='AutoDiag executable; must be on PATH or an absolute path'),
        DeclareLaunchArgument('rviz_config', default_value=os.path.join(share, 'rviz', 'autodiag.rviz'),
                              description='RViz config to open (should contain the AutoDiag panel)'),
        LogInfo(msg=['DDS AutoDiag: dashboard at http://127.0.0.1:', port]),
        server,
        rviz,
        # Closing RViz ends the session, including the server started here.
        RegisterEventHandler(OnProcessExit(target_action=rviz, on_exit=[EmitEvent(event=Shutdown(reason='RViz closed'))])),
    ])
