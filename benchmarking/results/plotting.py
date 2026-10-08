"""Publication formats drawn from verified analysis rows, with missing cells."""


try:
    import matplotlib

    matplotlib.use("Agg")
except ImportError as error:
    raise ValueError("Figures require: uv sync --locked --group analysis") from error



def render_service_results(rows, output):
    """A per-attempt view: explicit missing values, no implied official ranking."""
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(max(6, len(rows) * 1.2), 4.5))
    colors = {
        "pass": "#338866",
        "fail": "#bb6644",
        "no_submission": "#888888",
        "error": "#8855aa",
    }
    for index, row in enumerate(rows):
        value = row["score"]
        if value is None:
            axis.text(index, 3, "NA", ha="center", color=colors["error"])
        else:
            axis.bar(index, value, color=colors.get(row["outcome"], "#888888"))
            axis.text(index, value + 2, f"{value:.1f}", ha="center")
    highest = max((row["score"] for row in rows if row["score"] is not None), default=0)
    axis.set_ylim(0, max(110, highest * 1.1 + 4))
    axis.set_ylabel("Task score / 100")
    axis.set_xticks(
        range(len(rows)),
        [row["task_id"].split(".")[-1] + "\n" + row["cohort"][:6] for row in rows],
    )
    axis.set_title("Individual attempts — cohorts must be compared separately")
    figure.tight_layout()
    figure.savefig(output / "scores.svg")
    figure.savefig(output / "scores.pdf")
    plt.close(figure)
