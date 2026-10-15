---
title: DDS AutoDiag
hide:
  - navigation
  - toc
---

<div class="ad-hero" markdown>

# DDS AutoDiag

<p class="ad-tagline">Find out why your ROS 2 nodes can't talk to each other, and let AI set up RViz for you, with every change checked against your live system first.</p>

[Get started :material-rocket-launch:](getting-started/installation.md){ .md-button .md-button--primary }
[See how it works :material-graph:](concepts/architecture.md){ .md-button }

<div class="ad-badges">
<span class="ad-badge ad-badge--version">v0.1.0</span>
<span class="ad-badge">ROS 2 Jazzy</span>
<span class="ad-badge">Fast DDS · Cyclone DDS · Zenoh-aware</span>
<span class="ad-badge">Read-only by design</span>
<span class="ad-badge">Works offline</span>
<span class="ad-badge">MIT licensed</span>
</div>

</div>

## The problem

Topics show up in `ros2 topic list`, but no data arrives. RViz stays empty. Two containers see each other's nodes
but never exchange a message. The cause is usually one of a dozen settings: a QoS mismatch, a different
`ROS_DOMAIN_ID`, a discovery range, the RMW implementation, or shared memory between containers. Finding it by
hand costs hours.

DDS AutoDiag checks all of them in seconds, explains what it found, and tells you exactly what to change.

--8<-- "assets/diagrams/diagnosis.svg"

## What you get

<div class="grid cards" markdown>

-   :material-stethoscope:{ .lg .middle } **Rule-based diagnosis**

    ---

    22 checks for QoS, domains, discovery range, RMW and distro mismatches, DDS XML, shared memory between
    containers and more. Every finding comes with evidence, a next step and official documentation.

    [:octicons-arrow-right-24: Diagnostic rules](reference/rules.md)

-   :material-access-point-network:{ .lg .middle } **Live topic inspection**

    ---

    Publishers, subscribers and their QoS for any topic, incompatibilities highlighted, and a one-shot message
    sample that proves data actually arrives.

    [:octicons-arrow-right-24: Web dashboard](guides/dashboard.md)

-   :material-robot-outline:{ .lg .middle } **Configure RViz with AI**

    ---

    Describe the view you want. The AI plans the displays, AutoDiag validates them against live topics and TF, adds
    the QoS fixes it diagnosed, and applies only what you confirm. With Undo.

    [:octicons-arrow-right-24: Configure RViz](guides/configure-rviz.md)

-   :material-book-search-outline:{ .lg .middle } **Grounded AI assistant**

    ---

    A RAG pipeline over curated official ROS 2, DDS and Docker docs. Answers stream in, cite real sources and
    remember the conversation. Local (Ollama) or Claude, ChatGPT and Gemini.

    [:octicons-arrow-right-24: RAG & AI pipeline](concepts/rag.md)

-   :material-compare-horizontal:{ .lg .middle } **Compare hosts & containers**

    ---

    Put two robots, PCs or containers side by side, from redacted snapshot files or a token-protected live
    collector, and see exactly what differs.

    [:octicons-arrow-right-24: Compare hosts](guides/compare-hosts.md)

-   :material-shield-check-outline:{ .lg .middle } **Safe by design**

    ---

    Never restarts, reconfigures or publishes anything. Loopback by default, token login, DNS-rebinding
    protection, strict CSP, and keys that never reach the browser.

    [:octicons-arrow-right-24: Security model](concepts/security.md)

</div>

## Three ways to use it

=== "Command line"

    ```bash
    dds-autodiag doctor              # is this machine ready?
    dds-autodiag check               # diagnose this host
    dds-autodiag inspect /scan       # endpoints, QoS, incompatibilities
    ```

    Scriptable, with `--json` output and CI-friendly exit codes. [Command line guide](guides/cli.md)

=== "Web dashboard"

    ```bash
    dds-autodiag serve --open        # http://127.0.0.1:8080
    ```

    Overview, topics, host comparison, transport checks and the AI assistant in one place.
    [Dashboard guide](guides/dashboard.md)

=== "RViz2 panel"

    ```bash
    cd ros2 && colcon build --packages-select rviz_autodiag_panel
    source install/setup.bash && rviz2
    ```

    Panels → Add New Panel → **AutoDiag**. Health, topic QoS, AI assistant and Configure RViz, right next to your
    visualization. [RViz2 panel guide](guides/rviz-panel.md)

## How it fits together

--8<-- "assets/diagrams/architecture.svg"

All interfaces talk to one local server. It probes your system read-only, runs the rule engine, and only reaches out
to an AI model when you ask it to. [Read the architecture](concepts/architecture.md)
