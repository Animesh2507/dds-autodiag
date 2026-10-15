# RViz2 panel

The **AutoDiag** panel brings diagnostics and AI into RViz2, right next to the displays you're debugging.

## Install

```bash
cd ros2
source /opt/ros/jazzy/setup.bash
colcon build --packages-select rviz_autodiag_panel
source install/setup.bash
rviz2
```

In RViz: **Panels → Add New Panel → rviz_autodiag_panel → AutoDiag**.

!!! important "The panel needs the AutoDiag server"
    The panel is a client of the server: diagnostics, documentation search and AI providers (including API keys)
    all stay there. Start it first with `dds-autodiag serve`. The browser dashboard doesn't need to be open.

## Connecting

The top row holds the server URL (default `http://127.0.0.1:8080`), **Connect**, and **Dashboard**, which opens the
web UI. If the server requires a token, enter it in the token field or start RViz with `AUTODIAG_UI_TOKEN` set.

## The four tabs

=== "Health"

    The overall status and every finding for this machine, sorted by severity. Hover a finding to see its next
    step. Tick **every 30 s** for automatic refresh.

=== "Topic"

    Pick a topic and press **Inspect** to see publishers, subscribers and QoS, with incompatibilities marked.
    Topics used by your RViz displays are listed first, and **⚠** marks a display that currently reports a
    problem. That's usually the one to inspect.

=== "AI assistant"

    Ask about your system in plain language. The answer streams in, cites official documentation as clickable
    links, and includes the selected topic's live endpoints and QoS as context when *Include the topic* is
    ticked. Follow-up questions keep the conversation; **New conversation** starts fresh.

=== "Configure RViz"

    Describe the view you want, and the AI plans display changes that AutoDiag validates before you apply them.
    This one gets its own guide: [Configure RViz with AI](configure-rviz.md).

## Making the panel bigger

RViz panels are dock widgets:

- **Double-click the panel's title bar** to float it as a separate, resizable window, for example full height on a
  second monitor. Double-click again to dock it.
- Or drag the divider between the panel column and the 3D view.
- **File → Save Config** remembers the layout.

## Saved settings

The server URL, provider, model and selected topic are stored in your `.rviz` file. The access token is deliberately
**not** saved, because `.rviz` files are often shared.
