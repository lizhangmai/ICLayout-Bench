"""Publication formats drawn from verified analysis rows, with missing cells."""

from pathlib import Path

try:
    import matplotlib
    import numpy as np

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as error:
    raise ValueError("Figures require: uv sync --locked --group analysis") from error

from .files import Asset


def render_figures(output, scores, task_scores, failures):
    def label(row):
        return row["configuration_id"] + "\n" + row["run_kind"]

    def save(figure, name):
        figure.tight_layout()
        for extension in ("svg", "pdf"):
            path = output / f"{name}.{extension}"
            figure.savefig(path, bbox_inches="tight")
            path.chmod(0o600)
        plt.close(figure)

    with plt.rc_context({"font.size": 9, "svg.fonttype": "none"}):
        figure, axis = plt.subplots(figsize=(9, max(3, len(scores) * 0.65)))
        values = [row["value"] if row["value"] is not None else 0 for row in scores]
        axis.barh(range(len(scores)), values, color="#326e9b")
        axis.set_yticks(range(len(scores)), [label(row) for row in scores])
        limit = max([100, *values]) * 1.1
        axis.set_xlim(0, limit)
        axis.set_xlabel("BenchScore")
        axis.set_title("Fixed-suite score — NA means missing or unknown results")
        for index, row in enumerate(scores):
            value = row["value"]
            axis.text(
                1 if value is None else min(value + 1, limit - 8),
                index,
                "NA" if value is None else f"{value:.2f}",
                va="center",
            )
        save(figure, "scores")

        tasks = sorted({row["task_id"] for row in task_scores})
        cohorts = [(row["configuration_id"], row["run_kind"]) for row in scores]
        cells = {
            (row["task_id"], row["configuration_id"], row["run_kind"]): row
            for row in task_scores
        }
        matrix = np.full((len(tasks), len(cohorts)), np.nan)
        for i, task in enumerate(tasks):
            for j, cohort in enumerate(cohorts):
                value = cells[(task, *cohort)]["value"]
                if value is not None:
                    matrix[i, j] = value
        figure, axis = plt.subplots(
            figsize=(max(8, len(cohorts) * 1.5), max(3, len(tasks) * 0.35))
        )
        palette = plt.get_cmap("viridis").with_extremes(bad="#d9d9d9")
        chart = axis.imshow(
            matrix, cmap=palette, vmin=0, vmax=max(100, float(np.nanmax(matrix))) if np.isfinite(matrix).any() else 100, aspect="auto"
        )
        axis.set_xticks(
            range(len(cohorts)), [label(row) for row in scores], rotation=30, ha="right"
        )
        axis.set_yticks(range(len(tasks)), tasks, fontsize=7)
        axis.set_title("Task scores — gray cells are missing or unknown, not zero")
        for i in range(len(tasks)):
            for j in range(len(cohorts)):
                if np.isnan(matrix[i, j]):
                    axis.text(j, i, "NA", ha="center", va="center", fontsize=7)
        figure.colorbar(chart, ax=axis, label="Mean task score")
        save(figure, "task_scores")

        reasons = sorted({row["reason"] for row in failures})
        figure, axis = plt.subplots(figsize=(10, max(3, len(reasons) * 0.4)))
        if reasons:
            width = 0.8 / len(cohorts)
            for j, cohort in enumerate(cohorts):
                counts = [
                    sum(
                        row["count"]
                        for row in failures
                        if row["reason"] == reason
                        and (row["configuration_id"], row["run_kind"]) == cohort
                    )
                    for reason in reasons
                ]
                axis.barh(
                    np.arange(len(reasons)) + j * width,
                    counts,
                    height=width,
                    label=label(scores[j]),
                )
            axis.set_yticks(
                np.arange(len(reasons)) + (len(cohorts) - 1) * width / 2, reasons
            )
            axis.legend(fontsize=7)
        else:
            axis.text(
                0.5,
                0.5,
                "No conclusive failure observations",
                ha="center",
                transform=axis.transAxes,
            )
        axis.set_xlabel("Occurrences (one attempt may contribute several causes)")
        axis.set_title("Failure diagnostics")
        save(figure, "failures")
    return {
        "matplotlib": matplotlib.__version__,
        "numpy": np.__version__,
        "implementation_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
    }


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
    axis.set_ylim(0, 110)
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
