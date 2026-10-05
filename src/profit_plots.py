import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter, PercentFormatter

from src.plots import BLUE, GRAY, ORANGE, save_figure, set_style


def plot_profit_intervals(policies, path, language="en"):
    set_style()
    italian = language == "it"
    table = policies.loc[policies.policy != "mail_all"]
    labels = [("Nessuna email" if italian else "No mail") if k == 0 else
              ("Email a tutti / top 100%" if italian else "Mail all / top 100%") if k == 100 else
              f"Top {k}%" for k in table.k]
    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    for i, row in enumerate(table.itertuples()):
        color = BLUE if row.k == 30 else GRAY
        ax.hlines(i, row.ci_low, row.ci_high, color=color, linewidth=2)
        ax.plot(row.profit, i, "o", color=color, markersize=6)
    ax.axvline(0, color=GRAY, linestyle="--", linewidth=1)
    ax.set_yticks(range(len(table)), labels)
    ax.invert_yaxis()
    ax.set_xlabel("Profitto incrementale, $ per 10.000 clienti" if italian else
                  "Incremental profit, $ per 10,000 customers")
    ax.set_title("Profitto delle strategie e IC 95%" if italian else "Policy profit and 95% confidence intervals",
                 loc="left", pad=16, fontsize=16)
    ax.grid(axis="x", alpha=0.15)
    note = ("IPW normalizzato | 1.000 ricampionamenti del test | Margine $30 | Contatto $0,15 | Sconto 0%"
            if italian else "Normalized IPW | 1,000 test-set resamples | Margin $30 | Contact $0.15 | Discount 0%")
    fig.text(0.02, 0.01, note, fontsize=10)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save_figure(fig, path)


def plot_sensitivity(grid, path, language="en"):
    set_style()
    italian = language == "it"
    gain = grid.pivot(index="discount", columns="contact_cost", values="gain_vs_mail_all")
    k = grid.pivot(index="discount", columns="contact_cost", values="optimal_k")
    fig, ax = plt.subplots(figsize=(13, 7))
    cmap = LinearSegmentedColormap.from_list("profit_gain", ["#f4f6f8", BLUE])
    chart = ax.imshow(gain, origin="lower", aspect="auto", cmap=cmap, vmin=0)
    for row in range(len(gain)):
        for col in range(len(gain.columns)):
            value = gain.iloc[row, col]
            color = "white" if value > gain.to_numpy().max() * 0.6 else "#202a35"
            ax.text(col, row, f"{int(k.iloc[row, col])}%\n+${value:,.0f}",
                    ha="center", va="center", color=color, fontsize=10)
    ax.set_xticks(range(len(gain.columns)), [f"${cost:.2f}" for cost in gain.columns])
    ax.set_yticks(range(len(gain)), [f"{discount:.0%}" for discount in gain.index])
    ax.set_xlabel("Costo per contatto" if italian else "Cost per contact", labelpad=10)
    ax.set_ylabel("Sconto sullo spend treatment" if italian else "Discount on treatment spend")
    ax.set_title("Sensibilità: quota ottimale e vantaggio rispetto a tutti" if italian else
                 "Sensitivity: optimal audience and gain vs mail-all", loc="left", pad=18, fontsize=16)
    fig.colorbar(chart, ax=ax, label="Vantaggio, $ per 10.000 clienti" if italian else
                 "Gain, $ per 10,000 customers", fraction=0.03, pad=0.03)
    note = ("Celle: quota K e vantaggio | K=0%: nessuna email | Margine $30 | Massimo su test, da validare"
            if italian else "Cells: K and profit gain | K=0%: no mail | Margin $30 | Test-set maximum, requires validation")
    fig.text(0.02, 0.02, note, fontsize=10)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save_figure(fig, path)


def plot_break_even(line, path, language="en"):
    set_style()
    italian = language == "it"
    fig, ax = plt.subplots(figsize=(11.5, 4.8))
    visible = line.loc[line.mail_all_possible]
    ax.plot(visible.discount, visible.max_contact_cost_for_mail_all, color=BLUE, linewidth=2,
            label="Limite per inviare a tutti" if italian else "Mail-all cost limit")
    ax.fill_between(visible.discount, 0, visible.max_contact_cost_for_mail_all, color=BLUE, alpha=0.1)
    ax.text(0.025, 0.025, "Email a tutti" if italian else "Mail everyone", color=BLUE)
    ax.text(0.14, 0.25, "Targeting o nessuna email" if italian else "Targeting or no mail", color=GRAY)
    ax.set(xlim=(0, 0.3), ylim=(0, 0.5))
    ax.set_xlabel("Sconto sullo spend treatment" if italian else "Discount on treatment spend")
    ax.set_ylabel("Costo per contatto, $" if italian else "Cost per contact, $")
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value:.2f}"))
    ax.set_title("Confine di pareggio: tutti o una strategia alternativa" if italian else
                 "Break-even boundary: mail-all vs alternative policies", loc="left", pad=18, fontsize=16)
    ax.grid(alpha=0.15)
    ax.legend(frameon=False, loc="upper right")
    note = ("Confine basato su stime puntuali IPW | K=0%, 10%, ..., 100% | Non è un intervallo di confidenza"
            if italian else "Boundary from IPW point estimates | K=0%, 10%, ..., 100% | This is not a confidence interval")
    fig.text(0.02, 0.01, note, fontsize=10)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save_figure(fig, path)


def plot_calibration(table, path, language="en"):
    set_style()
    italian = language == "it"
    fig, ax = plt.subplots(figsize=(11.5, 4.8))
    ax.plot(table.decile, table.predicted_uplift * 100, color=BLUE, linestyle="--", marker="o",
            linewidth=2, label="Uplift previsto" if italian else "Predicted uplift")
    errors = np.array([table.observed_uplift - table.observed_ci_low,
                       table.observed_ci_high - table.observed_uplift]) * 100
    ax.errorbar(table.decile, table.observed_uplift * 100, yerr=errors,
                color=GRAY, marker="o", linewidth=1.5, capsize=4,
                label="Osservato, IPW + IC 95%" if italian else "Observed, IPW + 95% CI")
    negative = table.loc[table.negative_observed]
    ax.scatter(negative.decile, negative.observed_uplift * 100, color=ORANGE, marker="x", s=100,
               linewidths=2, label="Osservato negativo" if italian else "Negative observed uplift", zorder=4)
    ax.axhline(0, color=GRAY, linewidth=1)
    ax.set_xticks(range(1, 11))
    ax.set_xlabel("Decile: 1 = uplift previsto più alto" if italian else "Decile: 1 = highest predicted uplift")
    ax.set_ylabel("Uplift di conversione, punti percentuali" if italian else "Conversion uplift, percentage points")
    ax.set_title("Calibrazione uplift sul test" if italian else "Uplift calibration on test", loc="left", pad=48, fontsize=16)
    ax.grid(alpha=0.15)
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=3, fontsize=10)
    note = ("8.523 clienti, 78 acquirenti | 1.000 campioni test IID | IC bootstrap puntuali al 95% | Decili e modello fissati"
            if italian else "8,523 customers, 78 buyers | 1,000 IID test resamples | Pointwise 95% bootstrap CI | Deciles and model fixed")
    fig.text(0.02, 0.01, note, fontsize=10)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save_figure(fig, path)
