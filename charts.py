"""Visualisation (Visualisation module).

Each function builds and returns a Matplotlib ``Figure``. The GUI embeds the
figure in a window, and the same figure can be saved as a PNG image.

Colour rules used here:
  * every category always gets the same colour (colour follows the thing,
    not its rank), taken from a palette checked for colour-blind safety;
  * text uses neutral ink colours, never the series colour;
  * amounts and percentages are printed next to the colours so nothing
    depends on colour alone.
"""

from __future__ import annotations

from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

import analysis
import config

# ------------------------------------------------------------------ palette
SURFACE = "#fcfcfb"
INK = "#0b0b0b"          # primary text
INK_SOFT = "#52514e"     # secondary text
GRID = "#e4e3df"

CATEGORY_COLORS = {
    "Food": "#2a78d6",       # blue
    "Travel": "#eb6834",     # orange
    "Shopping": "#1baf7a",   # aqua
    "Health": "#eda100",     # yellow
    "Other": "#e87ba4",      # magenta
}
INCOME_COLOR = "#6250d6"     # violet
EXPENSE_COLOR = "#e34948"    # red
DAILY_COLOR = "#256abf"      # single-series blue

FIGURE_SIZE = (7.2, 4.8)


# ------------------------------------------------------------------ helpers
def _new_figure() -> Figure:
    return Figure(figsize=FIGURE_SIZE, dpi=100, facecolor=SURFACE,
                  layout="constrained")


def _rupee_axis(ax) -> None:
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda v, _pos: f"{config.CURRENCY}{v:,.0f}"))


def _style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_SOFT, length=0, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _empty_figure(message: str) -> Figure:
    fig = _new_figure()
    ax = fig.add_subplot(111)
    ax.set_axis_off()
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=12, color=INK_SOFT, transform=ax.transAxes)
    return fig


def _title(ax, text: str) -> None:
    ax.set_title(text, loc="left", fontsize=12, fontweight="bold",
                 color=INK, pad=12)


# ------------------------------------------------------------------- charts
def category_pie(df, period_label: str = "All time") -> Figure:
    """Donut chart of expenses by category (share of total spending)."""
    summary = analysis.category_summary(df)
    if summary.empty:
        return _empty_figure("No expenses to show for this period.")

    total = float(summary.sum())
    colors = [CATEGORY_COLORS.get(name, "#8b8a86") for name in summary.index]

    fig = _new_figure()
    ax = fig.add_subplot(111)
    wedges, _texts, autotexts = ax.pie(
        summary.values,
        colors=colors,
        startangle=90,
        counterclock=False,
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 6 else "",
        pctdistance=0.79,
        wedgeprops={"width": 0.42, "edgecolor": SURFACE, "linewidth": 2},
        textprops={"fontsize": 9, "color": "white", "fontweight": "bold"},
    )
    for text in autotexts:
        text.set_color("white")
    ax.text(0, 0.07, "Total spent", ha="center", va="center",
            fontsize=9, color=INK_SOFT)
    ax.text(0, -0.09, analysis.format_inr(total, 0), ha="center", va="center",
            fontsize=13, fontweight="bold", color=INK)
    ax.set_title(f"Spending by category — {period_label}", loc="left",
                 fontsize=12, fontweight="bold", color=INK, pad=12)

    labels = [
        f"{name}  {analysis.format_inr(value, 0)} ({value / total * 100:.0f}%)"
        for name, value in summary.items()
    ]
    legend = ax.legend(wedges, labels, loc="center left",
                       bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=9.5)
    for text in legend.get_texts():
        text.set_color(INK)
    return fig


def monthly_trend(df) -> Figure:
    """Grouped bars: income and expense for every month."""
    table = analysis.monthly_summary(df)
    if table.empty:
        return _empty_figure("No data yet. Add some transactions first.")

    months = [analysis.month_label(m)[:3] + " " + m[2:4] for m in table.index]
    x = list(range(len(table)))
    width = 0.36

    fig = _new_figure()
    ax = fig.add_subplot(111)
    ax.bar([i - width / 2 for i in x], table["Income"], width,
           color=INCOME_COLOR, label="Income")
    ax.bar([i + width / 2 for i in x], table["Expense"], width,
           color=EXPENSE_COLOR, label="Expense")
    ax.set_xticks(x, months)
    _style_axes(ax)
    _rupee_axis(ax)
    _title(ax, "Monthly income vs expense")

    # Print the values above the bars when there are few enough months.
    if len(table) <= 6:
        for i, (inc, exp) in enumerate(zip(table["Income"], table["Expense"])):
            if inc:
                ax.text(i - width / 2, inc, analysis.format_inr(inc, 0),
                        ha="center", va="bottom", fontsize=8, color=INK_SOFT)
            if exp:
                ax.text(i + width / 2, exp, analysis.format_inr(exp, 0),
                        ha="center", va="bottom", fontsize=8, color=INK_SOFT)
    ax.margins(y=0.15)
    legend = ax.legend(loc="upper right", frameon=False, ncol=2, fontsize=10)
    for text in legend.get_texts():
        text.set_color(INK)
    return fig


def daily_trend(df, month: str | None = None) -> Figure:
    """Line chart of spending per day (for one month, or across all time)."""
    series = analysis.daily_spending(df, month)
    if series.empty or series.sum() == 0:
        return _empty_figure("No expenses to show for this period.")

    fig = _new_figure()
    ax = fig.add_subplot(111)
    if month:
        ax.plot(series.index, series.values, color=DAILY_COLOR,
                linewidth=2, marker="o", markersize=4,
                markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.set_xlim(1, max(len(series), 2))
        ax.set_xlabel("Day of month", color=INK_SOFT, fontsize=9)
        title = f"Daily spending — {analysis.month_label(month)}"
    else:
        ax.plot(series.index, series.values, color=DAILY_COLOR, linewidth=1.8)
        fig.autofmt_xdate()
        title = "Daily spending — all time"

    # Mark the highest-spending day instead of labelling every point.
    peak_x = series.idxmax()
    peak_y = float(series.max())
    ax.annotate(analysis.format_inr(peak_y, 0), (peak_x, peak_y),
                textcoords="offset points", xytext=(0, 9), ha="center",
                fontsize=9, color=INK)
    _style_axes(ax)
    _rupee_axis(ax)
    ax.margins(y=0.18)
    ax.set_ylim(bottom=0)
    _title(ax, title)
    return fig
