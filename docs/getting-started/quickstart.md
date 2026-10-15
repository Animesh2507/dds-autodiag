# Quick start

Five minutes, no robot needed. You'll break a topic on purpose, then let AutoDiag find and explain the problem.

!!! tip "In a hurry? One command"
    `dds-autodiag demo` creates two broken demo topics and diagnoses them for you. The steps below do the same by
    hand, so you see how each part works.

## 1. Create a broken topic

Open two terminals with ROS 2 sourced. The first publishes **Best Effort**, the second subscribes **Reliable**, a
combination that never delivers data.

=== "Terminal 1: publisher"

    ```bash
    ros2 topic pub /demo std_msgs/msg/String "data: hello" --qos-reliability best_effort -r 2
    ```

=== "Terminal 2: subscriber"

    ```bash
    ros2 topic echo /demo --qos-reliability reliable
    ```

The subscriber prints nothing, just a warning about incompatible QoS that's easy to miss in a real system.

## 2. Find it with the CLI

```bash
dds-autodiag inspect /demo
```

```text
/demo — 1 publisher(s), 1 subscriber(s)

  publisher  _ros2cli_12446    reliability=BEST_EFFORT  durability=VOLATILE
  subscriber _ros2cli_12647    reliability=RELIABLE     durability=VOLATILE

✖ problem  RELIABILITY_MISMATCH  Incompatible reliability: _ros2cli_12446 → _ros2cli_12647
    next:     Review requested/offered QoS policies. Do not change semantics blindly.
```

The exit code is `1` because a problem was found, so the same command works in scripts and CI.

## 3. See it in the dashboard

```bash
dds-autodiag serve --open
```

Open **Topics**, filter for `demo`, and click it. The endpoint table shows both sides with their QoS, and the finding
explains the mismatch. **Read one sample** confirms that data arrives with *Best effort* but not with *Reliable*.

## 4. Ask the assistant

Open **Assistant**, type *"Why does my subscriber receive nothing on /demo?"* and press **Explain with AI**. The
answer cites the official ROS 2 QoS documentation and can be followed up, for example *"How do I fix that in my
launch file?"*. Without an AI model, **Documentation only** still finds the right official pages.

## 5. Check your whole machine

```bash
dds-autodiag check
```

```text
This host
  Host             my-laptop
  ROS distro       jazzy
  Domain ID        0
  RMW              rmw_fastrtps_cpp
  Discovery range  SUBNET
  ...
✔ No configured rule detected a problem. This does not prove messages are delivered;
  use `dds-autodiag sample <topic>` to confirm.
```

!!! info "Why \"does not prove\"?"
    AutoDiag reports what it can observe. A clean configuration check is good news, but only a received message
    proves delivery. That's why every clean result points you to a live sample. See
    [How diagnosis works](../concepts/diagnosis.md).

## Where next

<div class="grid cards" markdown>

-   :material-monitor-dashboard: [**Web dashboard**](../guides/dashboard.md): every tab explained
-   :material-robot-outline: [**Configure RViz with AI**](../guides/configure-rviz.md): build views by describing them
-   :material-compare-horizontal: [**Compare hosts**](../guides/compare-hosts.md): robot vs. laptop, container vs. container
-   :material-alert-circle-outline: [**Diagnostic rules**](../reference/rules.md): what each finding means

</div>
