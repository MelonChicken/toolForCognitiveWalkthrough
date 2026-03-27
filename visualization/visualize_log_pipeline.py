
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, Rectangle

PAGE_ENTRY_TYPES = {"page_load", "back_navigation"}
NON_INTERACTION_TYPES = {
    "session_start",
    "session_stop",
    "page_load",
    "back_navigation",
    "page_unload",
    "visibility_change",
}


def configure_matplotlib_fonts():
    preferred_fonts = [
        "Malgun Gothic",
        "AppleGothic",
        "NanumGothic",
        "Noto Sans CJK KR",
    ]
    available_fonts = {f.name for f in font_manager.fontManager.ttflist}
    for font_name in preferred_fonts:
        if font_name in available_fonts:
            plt.rcParams["font.family"] = font_name
            break
    plt.rcParams["axes.unicode_minus"] = False


def format_timestamp(ts_ms) -> str:
    if ts_ms is None or pd.isna(ts_ms):
        return ""
    if isinstance(ts_ms, str):
        return ts_ms
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%y-%m-%d %H:%M:%S")

def short_page_label(url: str, title: str = "") -> str:
    if title:
        return title.split("|")[0].strip()
    if not url:
        return "(unknown)"
    parsed = urlparse(url)
    page = parsed.path.split("/")[-1] or parsed.path
    qs = parse_qs(parsed.query)
    id_value = qs.get("id", [""])[0]
    return f"{page} ({id_value})" if id_value else page

def normalize_events(session: dict) -> pd.DataFrame:
    rows = []
    for i, ev in enumerate(session.get("events", [])):
        row = {
            "seq": i,
            "index": ev.get("index", i),
            "type": ev.get("type"),
            "timestamp": ev.get("timestampMs", ev.get("timestamp")),
            "elapsed_ms": ev.get("elapsedMs"),
            "delay": ev.get("delay"),
            "url": ev.get("url"),
            "title": ev.get("title"),
            "selector": ev.get("selector"),
            "text": ev.get("text"),
            "href": ev.get("href"),
            "scrollY": ev.get("scrollY"),
            "visibilityState": ev.get("visibilityState"),
        }
        rows.append(row)
    df = pd.DataFrame(rows).sort_values(["timestamp", "seq"]).reset_index(drop=True)
    start_ts = df["timestamp"].min()
    df["timestamp_text"] = [
        ev.get("timestamp", format_timestamp(ts))
        for ev, ts in zip(session.get("events", []), df["timestamp"])
    ]
    df["t_sec"] = (df["timestamp"] - start_ts) / 1000.0
    df["page_label"] = [
        short_page_label(url, title) for url, title in zip(df["url"], df["title"])
    ]
    return df

def infer_page_visits(df: pd.DataFrame) -> pd.DataFrame:
    loads = df[df["type"].isin(PAGE_ENTRY_TYPES)].copy()
    unloads = df[df["type"] == "page_unload"].copy()

    visits = []
    for _, load in loads.iterrows():
        current_ts = load["timestamp"]
        current_url = load["url"]

        # match the first unload on the same url after this load, before next load on same or different page
        future_unloads = unloads[unloads["timestamp"] >= current_ts]
        same_url_unloads = future_unloads[future_unloads["url"] == current_url]

        next_loads = loads[loads["timestamp"] > current_ts]
        next_load_ts = next_loads["timestamp"].min() if not next_loads.empty else None

        if not same_url_unloads.empty:
            cand = same_url_unloads.iloc[0]
            unload_ts = cand["timestamp"]
            if next_load_ts is not None and unload_ts > next_load_ts:
                unload_ts = next_load_ts
        else:
            unload_ts = next_load_ts if next_load_ts is not None else df["timestamp"].max()

        visits.append({
            "visit_index": len(visits),
            "entry_type": load["type"],
            "start_ts": current_ts,
            "end_ts": unload_ts,
            "start_time": format_timestamp(current_ts),
            "end_time": format_timestamp(unload_ts),
            "start_sec": (current_ts - df["timestamp"].min()) / 1000.0,
            "end_sec": (unload_ts - df["timestamp"].min()) / 1000.0,
            "duration_sec": max(0.0, (unload_ts - current_ts) / 1000.0),
            "url": current_url,
            "title": load["title"],
            "page_label": load["page_label"],
        })
    return pd.DataFrame(visits).sort_values("start_ts").reset_index(drop=True)

def summarize_page_metrics(df: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, visit in visits.iterrows():
        window = df[(df["timestamp"] >= visit["start_ts"]) & (df["timestamp"] <= visit["end_ts"])].copy()
        interaction_df = window[~window["type"].isin(NON_INTERACTION_TYPES)]
        rows.append({
            "visit_index": visit["visit_index"],
            "page_label": visit["page_label"],
            "entry_type": visit["entry_type"],
            "start_time": visit["start_time"],
            "end_time": visit["end_time"],
            "duration_sec": visit["duration_sec"],
            "eventCount": int(len(interaction_df)),
            "click_count": int((interaction_df["type"] == "click").sum()),
            "scroll_count": int((interaction_df["type"] == "scroll").sum()),
            "keyinput_count": int(interaction_df["type"].isin(["keydown", "input", "change"]).sum()),
            "mousemove_count": int((interaction_df["type"] == "mousemove").sum()),
            "focus_blur_count": int(interaction_df["type"].isin(["focus", "blur"]).sum()),
        })
    return pd.DataFrame(rows)

def summarize_task_metrics(session: dict, df: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    start_ts = session.get("startTimeMs", session.get("startTime"))
    end_ts = session.get("endTimeMs", session.get("endTime"))
    if not isinstance(start_ts, (int, float)):
        start_ts = df["timestamp"].min()
    if not isinstance(end_ts, (int, float)):
        end_ts = df["timestamp"].max()

    metrics = [
        {"metric": "total_task_time_sec", "value": round(max(0.0, (end_ts - start_ts) / 1000.0), 2)},
        {"metric": "page_visit_count", "value": int(len(visits))},
        {"metric": "back_navigation_count", "value": int((df["type"] == "back_navigation").sum())},
        {"metric": "total_event_count", "value": int(len(df[~df["type"].isin(NON_INTERACTION_TYPES)]))},
    ]
    return pd.DataFrame(metrics)

def infer_transitions(df: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    transitions = []
    loads = df[df["type"].isin(PAGE_ENTRY_TYPES)].sort_values("timestamp").reset_index(drop=True)

    for i in range(len(loads) - 1):
        src = loads.iloc[i]
        dst = loads.iloc[i + 1]

        window = df[(df["timestamp"] >= src["timestamp"]) & (df["timestamp"] <= dst["timestamp"])]

        clicks = window[window["type"] == "click"]
        last_click = clicks.iloc[-1] if not clicks.empty else None

        nav_type = "unknown"
        evidence = ""
        if dst["type"] == "back_navigation":
            nav_type = "back_navigation"
        if last_click is not None:
            href = last_click.get("href")
            if isinstance(href, str) and href and href.split("#")[0] in (dst["url"] or ""):
                nav_type = "link_click"
                evidence = f"click: {last_click.get('text') or last_click.get('selector')}"
        if nav_type == "unknown":
            if src["url"] and dst["url"]:
                src_base = src["url"].split("#")[0]
                dst_base = dst["url"].split("#")[0]
                if src_base == dst_base:
                    nav_type = "same_document_state"
                else:
                    # heuristic: if page B unloads soon and then page A reloads, later edge might be back_forward
                    nav_type = "possible_back_or_other"

        transitions.append({
            "from_page": src["page_label"],
            "to_page": dst["page_label"],
            "from_url": src["url"],
            "to_url": dst["url"],
            "from_time": format_timestamp(src["timestamp"]),
            "to_time": format_timestamp(dst["timestamp"]),
            "from_t_sec": (src["timestamp"] - df["timestamp"].min()) / 1000.0,
            "to_t_sec": (dst["timestamp"] - df["timestamp"].min()) / 1000.0,
            "nav_type": nav_type,
            "evidence": evidence,
        })
    return pd.DataFrame(transitions)

def plot_transition_graph(transitions: pd.DataFrame, visits: pd.DataFrame, out_path: Path):
    pages = list(dict.fromkeys(list(visits["page_label"])))
    n = max(1, len(pages))

    fig, ax = plt.subplots(figsize=(11, 4 + 0.4 * n))
    ax.axis("off")

    positions = {page: (0.15 + i * (0.7 / max(1, n - 1)), 0.55) for i, page in enumerate(pages)} if n > 1 else {pages[0]: (0.5, 0.55)}

    # nodes
    visit_durations = visits.groupby("page_label")["duration_sec"].sum().to_dict()
    for page, (x, y) in positions.items():
        width = 0.22
        height = 0.16
        rect = Rectangle((x - width/2, y - height/2), width, height, fill=False, linewidth=2)
        ax.add_patch(rect)
        ax.text(x, y + 0.015, page, ha="center", va="center", fontsize=10, wrap=True)
        ax.text(x, y - 0.04, f"{visit_durations.get(page, 0):.2f}s", ha="center", va="center", fontsize=9)

    # edges
    for _, row in transitions.iterrows():
        x1, y1 = positions[row["from_page"]]
        x2, y2 = positions[row["to_page"]]
        rad = 0.0 if row["from_page"] != row["to_page"] else 0.4
        arrow = FancyArrowPatch((x1, y1 - 0.1), (x2, y2 - 0.1),
                                connectionstyle=f"arc3,rad={rad}",
                                arrowstyle="-|>", mutation_scale=15, linewidth=1.8)
        ax.add_patch(arrow)
        label_x = (x1 + x2) / 2
        label_y = (y1 + y2) / 2 - 0.12
        text = row["nav_type"]
        if row["evidence"]:
            text += f"\n{row['evidence']}"
        ax.text(label_x, label_y, text, ha="center", va="center", fontsize=8)

    ax.set_title("Page Transition Graph", fontsize=14)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

def plot_page_metrics(page_metrics: pd.DataFrame, out_path: Path):
    if page_metrics.empty:
        return

    fig, axes = plt.subplots(1, 3, figsize=(19, max(5, 1.2 * len(page_metrics))), gridspec_kw={"width_ratios": [1, 1.2, 1]})

    labels = [f"{int(row['visit_index']) + 1}. {row['page_label']}" for _, row in page_metrics.iterrows()]
    y_pos = range(len(page_metrics))

    axes[0].barh(y_pos, page_metrics["eventCount"], color="#2f6b8a")
    axes[0].set_yticks(list(y_pos))
    axes[0].set_yticklabels(labels, fontsize=9)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Total Count")
    axes[0].set_title("Page-Level eventCount")
    axes[0].grid(True, axis="x", alpha=0.3)

    left = [0] * len(page_metrics)
    for column, color, label in [
        ("click_count", "#d95f02", "click"),
        ("scroll_count", "#1b9e77", "scroll"),
        ("keyinput_count", "#e6ab02", "key/input"),
        ("mousemove_count", "#66a61e", "mousemove"),
        ("focus_blur_count", "#7570b3", "focus/blur"),
    ]:
        axes[1].barh(y_pos, page_metrics[column], left=left, color=color, label=label)
        left = [l + v for l, v in zip(left, page_metrics[column])]
    axes[1].set_yticks(list(y_pos))
    axes[1].set_yticklabels([])
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Count")
    axes[1].set_title("Interaction Breakdown")
    axes[1].grid(True, axis="x", alpha=0.3)
    axes[1].legend(loc="lower right", fontsize=8)

    axes[2].barh(y_pos, page_metrics["duration_sec"], color="#7570b3")
    axes[2].set_yticks(list(y_pos))
    axes[2].set_yticklabels([])
    axes[2].invert_yaxis()
    axes[2].set_xlabel("Seconds")
    axes[2].set_title("Page-Level Dwell Time")
    axes[2].grid(True, axis="x", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

def plot_task_summary(task_metrics: pd.DataFrame, out_path: Path):
    if task_metrics.empty:
        return

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(task_metrics["metric"], task_metrics["value"], color=["#7570b3", "#1b9e77", "#d95f02", "#2f6b8a"])
    ax.set_title("Task-Level Summary")
    ax.set_ylabel("Value")
    ax.grid(True, axis="y", alpha=0.3)
    plt.setp(ax.get_xticklabels(), rotation=15, ha="right")

    for i, value in enumerate(task_metrics["value"]):
        ax.text(i, value, f"{value}", ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

def plot_timeline(df: pd.DataFrame, visits: pd.DataFrame, out_path: Path):
    event_levels = {
        "page_load": 3.0,
        "back_navigation": 2.9,
        "page_unload": 2.8,
        "click": 2.2,
        "scroll": 1.6,
        "focus": 1.2,
        "blur": 1.0,
        "mousemove": 0.6,
        "visibility_change": 0.3,
    }

    fig, ax = plt.subplots(figsize=(13, 5))

    # page visit spans
    y0, h = 3.5, 0.35
    for i, row in visits.iterrows():
        ax.add_patch(Rectangle((row["start_sec"], y0), row["duration_sec"], h, fill=False, linewidth=1.5))
        ax.text(row["start_sec"] + row["duration_sec"]/2, y0 + h/2, row["page_label"],
                ha="center", va="center", fontsize=9)

    # markers
    plot_df = df[df["type"].isin(event_levels.keys())].copy()
    xs = plot_df["t_sec"].tolist()
    ys = [event_levels[t] for t in plot_df["type"]]
    ax.scatter(xs, ys, s=28)

    for _, row in plot_df.iterrows():
        if row["type"] in {"page_load", "back_navigation", "page_unload", "click"}:
            label = row["type"]
            if row["type"] == "click" and isinstance(row["text"], str) and row["text"]:
                label += f": {row['text'][:16]}"
            ax.text(row["t_sec"], event_levels[row["type"]] + 0.08, label, fontsize=8, rotation=35)

    ax.set_yticks([0.3, 0.6, 1.0, 1.2, 1.6, 2.2, 2.8, 2.9, 3.0, 3.68])
    ax.set_yticklabels(["visibility", "mousemove", "blur", "focus", "scroll", "click", "unload", "back", "load", "page span"])
    ax.set_xlabel("Seconds from session start")
    ax.set_title("Session Timeline")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

def make_html_report(session: dict, visits: pd.DataFrame, page_metrics: pd.DataFrame, task_metrics: pd.DataFrame, transitions: pd.DataFrame, out_path: Path, timeline_png: str, graph_png: str, page_metrics_png: str, task_summary_png: str):
    task_metric_map = {row["metric"]: row["value"] for _, row in task_metrics.iterrows()}
    html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>User Journey Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; line-height: 1.5; }}
h1, h2 {{ margin: 0 0 8px 0; }}
.card {{ border: 1px solid #ccc; padding: 16px; margin: 12px 0; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
img {{ max-width: 100%; border: 1px solid #ddd; }}
code {{ background: #f4f4f4; padding: 2px 4px; }}
</style>
</head>
<body>
<h1>User Journey Report</h1>

<div class="card">
  <b>participantId</b>: {session.get("participantId")}<br>
  <b>taskId</b>: {session.get("taskId")}<br>
  <b>sessionId</b>: {session.get("sessionId")}<br>
  <b>eventCount</b>: {session.get("eventCount")}<br>
  <b>startTime</b>: {format_timestamp(session.get("startTime") or session.get("startTimeMs"))}<br>
  <b>endTime</b>: {format_timestamp(session.get("endTime") or session.get("endTimeMs"))}<br>
  <b>backNavigationCount</b>: {task_metric_map.get("back_navigation_count", 0)}<br>
  <b>totalTaskTimeSec</b>: {task_metric_map.get("total_task_time_sec", 0)}<br>
</div>

<h2>1. Task Summary</h2>
<img src="{task_summary_png}" alt="task summary">

<h2>2. Page Visit Metrics</h2>
<table>
<thead><tr><th>Visit</th><th>Page</th><th>Entry Type</th><th>Start Time</th><th>End Time</th><th>Duration(s)</th><th>eventCount</th><th>Click</th><th>Scroll</th><th>KeyInput</th></tr></thead>
<tbody>
{''.join(f"<tr><td>{int(r['visit_index']) + 1}</td><td>{r['page_label']}</td><td>{r['entry_type']}</td><td>{r['start_time']}</td><td>{r['end_time']}</td><td>{r['duration_sec']:.2f}</td><td>{int(r['eventCount'])}</td><td>{int(r['click_count'])}</td><td>{int(r['scroll_count'])}</td><td>{int(r['keyinput_count'])}</td></tr>" for _, r in page_metrics.iterrows())}
</tbody>
</table>

<img src="{page_metrics_png}" alt="page metrics">

<h2>3. Page Visits</h2>
<table>
<thead><tr><th>Page</th><th>Start Time</th><th>End Time</th><th>Duration(s)</th></tr></thead>
<tbody>
{''.join(f"<tr><td>{r['page_label']}</td><td>{r['start_time']}</td><td>{r['end_time']}</td><td>{r['duration_sec']:.2f}</td></tr>" for _, r in visits.iterrows())}
</tbody>
</table>

<h2>4. Transitions</h2>
<table>
<thead><tr><th>From</th><th>To</th><th>From Time</th><th>To Time</th><th>Type</th><th>Evidence</th></tr></thead>
<tbody>
{''.join(f"<tr><td>{r['from_page']}</td><td>{r['to_page']}</td><td>{r['from_time']}</td><td>{r['to_time']}</td><td>{r['nav_type']}</td><td>{r['evidence']}</td></tr>" for _, r in transitions.iterrows())}
</tbody>
</table>

<h2>5. Transition Graph</h2>
<img src="{graph_png}" alt="transition graph">

<h2>6. Timeline</h2>
<img src="{timeline_png}" alt="timeline">

</body></html>"""
    out_path.write_text(html, encoding="utf-8")

def run_pipeline(input_json: str, out_dir: str):
    configure_matplotlib_fonts()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with open(input_json, "r", encoding="utf-8") as f:
        session = json.load(f)

    df = normalize_events(session)
    visits = infer_page_visits(df)
    page_metrics = summarize_page_metrics(df, visits)
    task_metrics = summarize_task_metrics(session, df, visits)
    transitions = infer_transitions(df, visits)

    df.to_csv(out / "normalized_events.csv", index=False, encoding="utf-8-sig")
    visits.to_csv(out / "page_visits.csv", index=False, encoding="utf-8-sig")
    page_metrics.to_csv(out / "page_metrics.csv", index=False, encoding="utf-8-sig")
    task_metrics.to_csv(out / "task_metrics.csv", index=False, encoding="utf-8-sig")
    transitions.to_csv(out / "transitions.csv", index=False, encoding="utf-8-sig")

    plot_transition_graph(transitions, visits, out / "transition_graph.png")
    plot_page_metrics(page_metrics, out / "page_metrics.png")
    plot_task_summary(task_metrics, out / "task_summary.png")
    plot_timeline(df, visits, out / "timeline.png")
    make_html_report(session, visits, page_metrics, task_metrics, transitions, out / "report.html", "timeline.png", "transition_graph.png", "page_metrics.png", "task_summary.png")

    print(f"Done. Files written to: {out.resolve()}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Visualize browser interaction log.")
    parser.add_argument("--input", required=True, help="Path to session JSON")
    parser.add_argument("--out", required=True, help="Output directory")
    args = parser.parse_args()

    run_pipeline(args.input, args.out)


if __name__ == "__main__":
    main()
