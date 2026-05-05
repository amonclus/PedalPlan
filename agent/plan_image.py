import io

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

def _fmt_duration(minutes: int) -> str:
    if minutes >= 60:
        h, m = divmod(minutes, 60)
        return f"{h}h {m}min" if m else f"{h}h"
    return f"{minutes}min"


# Zone → fill color, text color
_ZONE_STYLE = {
    "Z1":     ("#bbf7d0", "#14532d"),
    "Z1-Z2":  ("#86efac", "#14532d"),
    "Z2":     ("#4ade80", "#14532d"),
    "Z2-Z3":  ("#fde68a", "#78350f"),
    "Z3":     ("#fbbf24", "#78350f"),
    "Z3-Z4":  ("#fb923c", "#7c2d12"),
    "Z4":     ("#f97316", "#ffffff"),
    "Z4-Z5":  ("#ef4444", "#ffffff"),
    "Z5":     ("#dc2626", "#ffffff"),
    "Rest":   ("#e5e7eb", "#6b7280"),
}
_DEFAULT_STYLE = ("#d1d5db", "#374151")


def _zone_style(zone: str) -> tuple[str, str]:
    return _ZONE_STYLE.get(zone.strip(), _DEFAULT_STYLE)


def generate_plan_image(plan: dict) -> bytes:
    days = plan.get("days", [])
    n = len(days)
    week = plan.get("week_commencing", "")
    summary = plan.get("summary", "")

    fig_h = max(6, n * 1.1 + 2.5)
    fig, ax = plt.subplots(figsize=(18, fig_h))
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, n + 0.5)
    ax.axis("off")

    # Title
    fig.text(0.02, 0.97, f"Training Plan — week of {week}",
             fontsize=14, fontweight="bold", va="top")
    fig.text(0.02, 0.94, summary, fontsize=10, va="top", color="#4b5563",
             wrap=True)

    label_x = 0.0
    label_w = 0.13
    bar_x = label_w + 0.01
    bar_w = 0.85

    for i, day in enumerate(days):
        y = n - 1 - i
        session_type = day.get("type", "")
        structure = day.get("structure", [])
        total_min = sum(s.get("duration_min", 0) for s in structure)
        if total_min == 0:
            total_min = day.get("duration_min", 1)

        # Day label
        ax.text(label_x + label_w - 0.01, y + 0.5, day["day"],
                ha="right", va="center", fontsize=10, fontweight="bold", color="#111827")

        # Background track
        bg = mpatches.FancyBboxPatch(
            (bar_x, y + 0.08), bar_w, 0.84,
            boxstyle="round,pad=0.005", linewidth=0,
            facecolor="#f3f4f6",
        )
        ax.add_patch(bg)

        if session_type == "Rest" or not structure:
            fill_c, text_c = _zone_style("Rest")
            rest_block = mpatches.FancyBboxPatch(
                (bar_x, y + 0.08), bar_w, 0.84,
                boxstyle="round,pad=0.005", linewidth=0, facecolor=fill_c,
            )
            ax.add_patch(rest_block)
            ax.text(bar_x + bar_w / 2, y + 0.5, "REST",
                    ha="center", va="center", fontsize=9, color=text_c, fontweight="bold")
            continue

        # Zone blocks
        x = bar_x
        for idx, step in enumerate(structure):
            dur = step.get("duration_min", 0)
            if dur <= 0:
                continue
            w = (dur / total_min) * bar_w
            zone = step.get("zone", "Z1")
            fill_c, text_c = _zone_style(zone)

            # Clip first/last block corners to match background roundness
            block = mpatches.FancyBboxPatch(
                (x, y + 0.08), w, 0.84,
                boxstyle="round,pad=0.005" if idx == 0 or idx == len(structure) - 1 else "square,pad=0",
                linewidth=0.3, edgecolor="#ffffff", facecolor=fill_c,
            )
            ax.add_patch(block)

            # Label inside block if wide enough
            if w > 0.04:
                label = step.get("label", zone)
                if w < 0.09:
                    label = zone
                ax.text(x + w / 2, y + 0.72, label,
                        ha="center", va="center", fontsize=7.5, color=text_c,
                        fontweight="bold", clip_on=True)
                ax.text(x + w / 2, y + 0.32, f"{dur}′",
                        ha="center", va="center", fontsize=7, color=text_c,
                        clip_on=True)
            x += w

        # Session type label on right
        dur_label = _fmt_duration(day.get("duration_min", total_min))
        ax.text(bar_x + bar_w + 0.005, y + 0.5, f"{session_type}  {dur_label}",
                ha="left", va="center", fontsize=8, color="#6b7280")

    # Legend
    legend_items = [
        mpatches.Patch(facecolor=_ZONE_STYLE[z][0], edgecolor="#ccc", label=z)
        for z in ["Z1", "Z2", "Z3", "Z4", "Z5", "Rest"]
    ]
    ax.legend(handles=legend_items, loc="lower right", bbox_to_anchor=(1, -0.04),
              ncol=6, fontsize=8, frameon=False)

    plt.tight_layout(rect=[0, 0.02, 1, 0.92])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
