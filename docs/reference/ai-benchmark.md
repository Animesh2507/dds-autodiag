# AI model benchmark

Which model should you pick for **Configure RViz**, and does it work offline? This page answers that with a
reproducible benchmark: eight fixed scenarios, scored the same way for every model. Run it on your own machine with
`dds-autodiag bench` and share your results.

!!! tip "Short answer (October 2026)"
    - **Cloud:** all three Claude models got every scenario right. **Claude Haiku 5.5** was the fastest (median
      **2.1 s** per plan); Sonnet 5.5 (3.7 s) and Opus 5.5 (4.8 s) were equally accurate.
    - **Offline:** **`qwen3:4b-instruct`** also got every scenario right, at a median **32 s** per plan on a laptop
      CPU. `qwen2.5:3b` is faster (20 s) but missed the Nav2 view and one of two actions in "hide and rename".

## Results

Configure-RViz benchmark · DDS AutoDiag 0.1.0 · 2026-10-17 · AMD Ryzen AI 5 PRO 340 (6 cores), 23 GB RAM, Ollama
0.34 on the **CPU only** (no GPU), Ubuntu 24.04 · one run per scenario · default prompt (retrieval, see below).

**Median time per plan**, and how many of the 23 checks each model's plans passed:

--8<-- "assets/benchmarks/charts/median-time.svg"

Every chart on this page is drawn from the raw data ([`2026-10-17.json`](../assets/benchmarks/2026-10-17.json)) by
`tools/bench_charts.py`. Hover a mark for its exact numbers; the tables below hold the same values.
{ .ad-chart-note }

| Model | Scenarios fully right | Checks passed | Median time per plan | Prompt / output tokens |
|---|---|---|---|---|
| Claude `claude-opus-5-5` | 8/8 | 23/23 | 4.8 s | 2447 / 313 |
| Claude `claude-sonnet-5-5` | 8/8 | 23/23 | 3.7 s | 2447 / 297 |
| Claude `claude-haiku-5-5` | 8/8 | 23/23 | **2.1 s** | 2447 / 377 |
| Ollama `qwen3:4b-instruct` (local) | 8/8 | 23/23 | 32.1 s | 1200 / 433 |
| Ollama `qwen2.5:3b` (local) | 6/8 | 18/23 | 19.8 s | 1200 / 315 |

**Time per plan in each scenario.** The bar spans the three Claude models; a ring marks a plan that failed a check:

--8<-- "assets/benchmarks/charts/per-scenario.svg"

| Scenario | Opus 5.5 | Sonnet 5.5 | Haiku 5.5 | qwen3:4b-instruct | qwen2.5:3b |
|---|---|---|---|---|---|
| Fix two silent QoS problems | ✅ 2/2 · 5 s | ✅ 2/2 · 4 s | ✅ 2/2 · 2 s | ✅ 2/2 · 25 s | ✅ 2/2 · 24 s |
| Add a 3D cloud colored by height | ✅ 4/4 · 4 s | ✅ 4/4 · 4 s | ✅ 4/4 · 2 s | ✅ 4/4 · 31 s | ✅ 4/4 · 22 s |
| TF error + robot model + QoS + 3D cloud | ✅ 6/6 · 5 s | ✅ 6/6 · 4 s | ✅ 6/6 · 3 s | ✅ 6/6 · 71 s | ✅ 6/6 · 45 s |
| Follow-up: "make the points bigger" | ✅ 1/1 · 3 s | ✅ 1/1 · 2 s | ✅ 1/1 · 2 s | ✅ 1/1 · 15 s | ✅ 1/1 · 9 s |
| Show what Nav2 is planning | ✅ 5/5 · 7 s | ✅ 5/5 · 5 s | ✅ 5/5 · 4 s | ✅ 5/5 · 44 s | ❌ 1/5 · 19 s |
| Make a heavy cloud light-weight (and be honest) | ✅ 2/2 · 6 s | ✅ 2/2 · 3 s | ✅ 2/2 · 4 s | ✅ 2/2 · 44 s | ✅ 2/2 · 20 s |
| Pick the real camera topic | ✅ 1/1 · 3 s | ✅ 1/1 · 2 s | ✅ 1/1 · 2 s | ✅ 1/1 · 28 s | ✅ 1/1 · 16 s |
| Hide and rename | ✅ 2/2 · 5 s | ✅ 2/2 · 4 s | ✅ 2/2 · 2 s | ✅ 2/2 · 33 s | ❌ 1/2 · 16 s |

Not measured this time: OpenAI `gpt-5-mini` (the test account had no API credits) and Gemini (not configured).
Raw data: [`2026-10-17.json`](../assets/benchmarks/2026-10-17.json).

## What is measured

Each scenario is a fixed RViz state (displays with their real RViz properties, TF frames, live topics and publisher
QoS), a request, and the checks a correct plan must pass:

| Scenario | Request (shortened) | A correct plan must… |
|---|---|---|
| Fix two silent QoS problems | "My LaserScan and map show nothing." | set LaserScan to Best Effort, Map to Transient Local |
| 3D cloud by height | "Show the 3D point cloud colored by height." | add PointCloud2 on `/points`, AxisColor, Axis Z, Best Effort |
| TF + robot + QoS + cloud | the request from the demo video | fix the Fixed Frame, add RobotModel, both QoS fixes, cloud by height |
| Follow-up | "Make the points bigger." (after adding a cloud) | change the cloud's point size |
| Nav2 view | "Show what navigation is planning…" | Path on `/plan`, both costmaps with the costmap scheme, footprint |
| Light-weight cloud | "…make it light-weight and downsample it." | set a load-reducing option and say that real downsampling needs a filter node |
| Camera topic | "Show the front camera image." | use `/front_camera/image_raw`, not the default name |
| Hide and rename | "Hide the grid and rename LaserScan to Front lidar." | both actions |

The **final plan** is scored: the model's answer after AutoDiag's validation and automatic fixes, i.e. exactly what
you would see in the panel. That is why cloud models reach the maximum: the benchmark separates small local models
much more than large ones. Times are per plan, measured end to end.

## Where the time goes, and the faster prompt

On a CPU, a 4B model reads the prompt at about **100 tokens/s** but writes the answer at only about **13 tokens/s**.
The answer (a JSON plan) is usually the larger part of the wait.

The planner now **retrieves** only what a request needs: the display types it mentions ("cloud" → PointCloud2,
"costmap" → Map, "footprint" → Polygon…), matching topics, and full settings only for the displays it touches. If
nothing matches, the full catalog is used as before. Same scenarios, same model (`qwen3:4b-instruct`, CPU):

--8<-- "assets/benchmarks/charts/retrieval.svg"

| Prompt | Scenarios fully right | Checks | Median per plan | Mean prompt tokens |
|---|---|---|---|---|
| Full catalog (before) | 6/8 | 21/23 | 49.2 s | 2144 |
| **Retrieval (now the default)** | **8/8** | **23/23** | **32.1 s** (−35%) | **1200** (−44%) |
| Retrieval + compact answers (tried, not used) | 5/8 | 18/23 | 27.1 s | 1221 |

A compact answer format (leaving out empty fields, skipping the fixes AutoDiag adds anyway) saved another 5 s but made
the small model drop fields it needed; 28 suggestions were rejected by validation. It is not used.

In the demo video, local plans took 1.5–2.5 minutes: the real panel state there had more displays and
topics, and the same CPU was also rendering RViz in software and recording the screen.

## Faster local models

- **Use your GPU.** The numbers above are CPU only. Check with `ollama ps`: "100% CPU" means no GPU is used. AMD and
  Intel integrated GPUs can work through Ollama's Vulkan backend, NVIDIA through CUDA.
- **Keep the model loaded:** the dashboard warms it up; `keep_alive` is 30 minutes.
- **Follow-ups are faster** because Ollama reuses the cached start of the prompt.

## Caveats

- One run per scenario at temperature 0.1; small differences between models can be chance. Use `--repeat 3` for
  firmer numbers.
- Cloud times depend on your network, region and the provider's load at that moment; local times on your hardware.
- Providers count prompt tokens differently (Ollama counts only tokens it had to process, Claude includes the
  instructions and the answer schema), so compare tokens within one provider.
- The scenarios are synthetic RViz states modeled on the demo robot, not recordings of real robots.

## Run it yourself

```bash
dds-autodiag bench                                         # your default provider; local Ollama is free
dds-autodiag bench --model ollama:qwen3:4b-instruct --model anthropic:claude-haiku-5-5 --markdown
dds-autodiag bench --scenario nav2_view --repeat 3         # one scenario, three runs
dds-autodiag bench --variant full                          # compare with the prompt before retrieval
```

Cloud models are billed per request on your API key (about 2,500 prompt and 300–400 output tokens per plan). No robot
or RViz is needed and nothing is changed. Please share your `--markdown` output, with your CPU or GPU, in a GitHub
issue: results from other machines and models make this page more useful for everyone.
