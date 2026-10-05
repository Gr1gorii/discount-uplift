import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter, PercentFormatter


BLUE = "#285b86"
ORANGE = "#bd742e"
GRAY = "#6b7280"
LABELS = {"logistic": "T-learner: logistic", "forest": "T-learner: forest"}
TEXT = {
    "en": {
        "rates_title": "Purchase within two weeks", "rates_axis": "Customers with a purchase",
        "control": "No email", "treated": "Men's email", "effect_title": "Effect of email assignment",
        "effect_axis": "Conversion difference, percentage points", "pp": "pp",
        "ci": "95% CI", "customers": "customers", "ab_note": "95% normal intervals",
        "qini_title": "Qini curve on the holdout set", "response": "Purchase probability",
        "random_order": "Random order", "qini_axis": "Qini gain, purchases on the treatment-group scale",
        "share_axis": "Audience share ranked by model score",
        "qini_note": "Model selected on validation | Qini does not measure profit",
        "budget_title": "Profit at different campaign sizes", "uplift": "Uplift ranking",
        "random": "Random selection: expected value", "validation": "Share from validation",
        "budget_axis": "Share of customers contacted", "profit_axis": "Incremental profit, $ per 10,000 customers",
        "budget_note": "Margin: $30 | Contact: $0.15 | Discount: $0 | Other shares are diagnostic",
        "policies_title": "Profit and estimation uncertainty", "none": "Contact nobody",
        "all": "Contact everyone", "random_30": "Random 30%", "response_30": "Purchase probability: 30%",
        "uplift_30": "Uplift: 30%", "selected_30": "Uplift: 30% (validation)",
        "policies_note": "95% percentile bootstrap, 1,000 repetitions | Model and shares fixed | Overlap is not a test of the difference",
    },
    "it": {
        "rates_title": "Acquisto entro due settimane", "rates_axis": "Clienti con un acquisto",
        "control": "Nessuna email", "treated": "Email prodotti uomo", "effect_title": "Effetto dell'assegnazione dell'email",
        "effect_axis": "Differenza di conversione, punti percentuali", "pp": "p.p.",
        "ci": "IC 95%", "customers": "clienti", "ab_note": "Intervalli normali al 95%",
        "qini_title": "Curva Qini sul campione di test", "response": "Probabilità di acquisto",
        "random_order": "Ordine casuale", "qini_axis": "Qini gain, acquisti sulla scala del gruppo treatment",
        "share_axis": "Quota del pubblico ordinata per punteggio",
        "qini_note": "Modello scelto su validation | Qini non misura il profitto",
        "budget_title": "Profitto per diverse dimensioni della campagna", "uplift": "Ordine per uplift",
        "random": "Selezione casuale: valore atteso", "validation": "Quota scelta su validation",
        "budget_axis": "Quota di clienti contattati", "profit_axis": "Profitto incrementale, $ per 10.000 clienti",
        "budget_note": "Margine: $30 | Contatto: $0,15 | Sconto: $0 | Altre quote solo per diagnosi",
        "policies_title": "Profitto e incertezza della stima", "none": "Non contattare nessuno",
        "all": "Contattare tutti", "random_30": "30% casuale", "response_30": "Probabilità di acquisto: 30%",
        "uplift_30": "Uplift: 30%", "selected_30": "Uplift: 30% (validation)",
        "policies_note": "Bootstrap percentile al 95%, 1.000 ripetizioni | Modello e quote fissi | La sovrapposizione non testa la differenza",
    },
}


def set_style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "text.parse_math": False,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#b7bec7", "axes.labelcolor": "#202a35",
        "text.color": "#202a35", "xtick.color": "#525c68",
        "ytick.color": "#525c68", "figure.facecolor": "white",
        "axes.facecolor": "white", "savefig.facecolor": "white",
    })


def save_figure(fig, path):
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_experiment(ab, path, language="en"):
    set_style()
    text = TEXT[language]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2), gridspec_kw={"width_ratios": [1, 1.15]})
    rates = [ab["control_rate"], ab["treated_rate"]]
    sizes = [ab["control_n"], ab["treated_n"]]
    errors = [1.96 * np.sqrt(rate * (1 - rate) / size) for rate, size in zip(rates, sizes)]
    axes[0].bar([text["control"], text["treated"]], rates, color=[GRAY, BLUE], width=0.55)
    axes[0].errorbar([0, 1], rates, yerr=errors, fmt="none", color="#202a35", capsize=5)
    for i, rate in enumerate(rates):
        axes[0].text(i, rate + errors[i] + 0.0006, f"{rate:.2%}", ha="center", fontsize=12)
    axes[0].set_ylim(0, 0.016)
    axes[0].yaxis.set_major_formatter(PercentFormatter(1))
    axes[0].set_ylabel(text["rates_axis"])
    axes[0].set_title(text["rates_title"], loc="left", pad=18)
    axes[0].grid(axis="y", alpha=0.16)
    axes[0].set_axisbelow(True)
    axes[1].axvline(0, color=GRAY, linewidth=1, linestyle="--")
    effect = ab["effect"] * 100
    low, high = ab["ci_low"] * 100, ab["ci_high"] * 100
    axes[1].errorbar(effect, 0, xerr=[[effect - low], [high - effect]],
                     fmt="o", color=BLUE, markersize=9, capsize=7, linewidth=2)
    axes[1].text(effect, 0.24, f"+{effect:.2f} {text['pp']}", ha="center", fontsize=17)
    axes[1].text(effect, -0.3, f"{text['ci']}: [{low:.2f}; {high:.2f}] {text['pp']}", ha="center")
    axes[1].set_xlim(-0.15, 1.05)
    axes[1].set_ylim(-0.65, 0.65)
    axes[1].set_yticks([])
    axes[1].set_xlabel(text["effect_axis"])
    axes[1].set_title(text["effect_title"], loc="left", pad=18)
    axes[1].grid(axis="x", alpha=0.16)
    fig.text(0.02, -0.03, f"Hillstrom, 2008 | {sum(sizes):,} {text['customers']} | Mens E-Mail vs No E-Mail | {text['ab_note']}")
    fig.tight_layout(w_pad=3)
    save_figure(fig, path)


def plot_qini(curves, metrics, chosen_model, test_n, path, language="en"):
    set_style()
    text = TEXT[language]
    fig, ax = plt.subplots(figsize=(11.5, 4.8))
    for name, color, style in [(chosen_model, BLUE, "-"), ("response", ORANGE, "--")]:
        curve = curves[name]
        label = LABELS[name] if name in LABELS else text["response"]
        ax.plot(curve.share, curve.gain, color=color, linestyle=style, linewidth=2,
                label=f"{label} | Qini = {metrics[name]['qini']:.3f}")
    curve = curves[chosen_model]
    ax.plot([0, 1], [0, curve.gain.iloc[-1]], color=GRAY, linestyle=":", label=text["random_order"])
    ax.axhline(0, color=GRAY, linewidth=0.7)
    ax.set(xlim=(0, 1), xlabel=text["share_axis"], ylabel=text["qini_axis"])
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_title(text["qini_title"], loc="left", pad=18, fontsize=16)
    ax.grid(alpha=0.15)
    ax.legend(loc="upper left", frameon=False)
    fig.text(0.02, -0.02, f"Test: {test_n:,} {text['customers']} | {text['qini_note']}")
    fig.tight_layout()
    save_figure(fig, path)


def plot_budget(curves, selected_share, test_n, path, language="en"):
    set_style()
    text = TEXT[language]
    fig, ax = plt.subplots(figsize=(11.5, 4.8))
    for name, color, style in [("uplift", BLUE, "-"), ("response", ORANGE, "--"), ("random", GRAY, ":")]:
        curve = curves[name]
        ax.plot(curve.budget, curve.profit, color=color, linestyle=style, linewidth=2,
                marker="o" if name == "uplift" else None, markersize=4, label=text[name])
    ax.axvline(selected_share, color=BLUE, linestyle="--", alpha=0.6,
               label=f"{text['validation']}: {selected_share:.0%}")
    ax.axhline(0, color=GRAY, linewidth=1)
    ax.set(xlim=(0, 1), xlabel=text["budget_axis"], ylabel=text["profit_axis"])
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}".replace(",", " ")))
    ax.set_title(text["budget_title"], loc="left", pad=18, fontsize=16)
    ax.grid(alpha=0.15)
    ax.legend(frameon=False, loc="best")
    fig.text(0.02, -0.02, f"Test: {test_n:,} {text['customers']} | {text['budget_note']}")
    fig.tight_layout()
    save_figure(fig, path)


def plot_policies(policies, path, language="en"):
    set_style()
    text = TEXT[language]
    names = ["none", "all", "random_30", "response_30", "uplift_30", "selected"]
    labels = [text[name] for name in names[:-1]] + [text["validation"]]
    if policies["selected"]["share"] == policies["uplift_30"]["share"]:
        names, labels = names[:-1], labels[:-1]
        labels[-1] = text["selected_30"]
    values = [policies[name]["profit"] for name in names]
    lows = [policies[name]["ci"][0] for name in names]
    highs = [policies[name]["ci"][1] for name in names]
    fig, ax = plt.subplots(figsize=(11.5, 4.8))
    positions = np.arange(len(names))
    for i, name in enumerate(names):
        color = BLUE if name in ["uplift_30", "selected"] else GRAY
        ax.hlines(i, lows[i], highs[i], color=color, linewidth=2)
        ax.plot(values[i], i, "o", color=color, markersize=7)
    ax.axvline(0, color=GRAY, linewidth=0.8, linestyle="--")
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_xlabel(text["profit_axis"])
    ax.set_title(text["policies_title"], loc="left", pad=18, fontsize=16)
    ax.grid(axis="x", alpha=0.15)
    fig.text(0.02, -0.02, text["policies_note"])
    fig.tight_layout()
    save_figure(fig, path)
