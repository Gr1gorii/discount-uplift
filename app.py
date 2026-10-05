import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data import ROOT
from src.evaluation import interval
from src.profit import net_profit, profit_difference
from src.text import TEXT


st.set_page_config(page_title="Uplift and profit", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 2rem; padding-bottom: 2rem;}
@media (max-width: 1000px) {
    [data-testid="stHorizontalBlock"] {flex-direction: column;}
    [data-testid="stColumn"] {width: 100% !important; flex: 1 1 100% !important;}
}
</style>
""", unsafe_allow_html=True)
language = st.sidebar.selectbox("Language / Lingua", ["English", "Italiano"])
text = TEXT[language]


def money(value):
    return f"{'+' if value >= 0 else '-'}${abs(value):,.0f}".replace(",", " ")


def bounds(low, high):
    low_text = f"{'-' if low < 0 else ''}${abs(low):,.0f}"
    high_text = f"{'-' if high < 0 else ''}${abs(high):,.0f}"
    return f"[{low_text}; {high_text}]".replace(",", " ")


def number(value, decimals=2):
    result = f"{value:.{decimals}f}"
    return result.replace(".", ",") if language == "Italiano" else result


def load_results():
    report = ROOT / "reports"
    return (json.loads((report / "summary.json").read_text()),
            json.loads((report / "profit_analysis.json").read_text()),
            pd.read_csv(report / "policy_profit.csv"),
            pd.read_csv(report / "bootstrap_components.csv"),
            pd.read_csv(report / "uplift_calibration.csv"))


@st.cache_data
def scenario(components, samples, contact_cost, discount):
    table = components.copy()
    table["contact_spend"] = table.contacts * contact_cost
    table["discount_spend"] = table.treated_spend * discount
    table["profit"] = net_profit(table, contact_cost, discount)
    values = samples.assign(profit=net_profit(samples, contact_cost, discount))
    for index, row in table.iterrows():
        table.loc[index, ["ci_low", "ci_high"]] = interval(values.loc[values.policy == row.policy, "profit"])
    return table


def label(row):
    if row.policy == "no_mail":
        return text["no_mail"]
    if row.policy in ["mail_all", "top_100"]:
        return text["mail_all"]
    return f"Top {int(row.k)}%"


def policy_chart(table):
    figure = go.Figure()
    labels = []
    for row in table.itertuples():
        name = label(row)
        labels.append(name)
        color = "#285b86" if row.k == share_pct else "#6b7280"
        figure.add_trace(go.Scatter(x=[row.ci_low, row.ci_high], y=[name, name], mode="lines",
                                   line=dict(color=color, width=2), hoverinfo="skip", showlegend=False))
        figure.add_trace(go.Scatter(x=[row.profit], y=[name], mode="markers",
                                   marker=dict(color=color, size=8), showlegend=False,
                                   hovertemplate="%{y}<br>$%{x:,.0f}<extra></extra>"))
    figure.add_vline(x=0, line_color="#9ca3af", line_dash="dash", line_width=1)
    figure.update_layout(template="plotly_white", height=430, margin=dict(l=10, r=20, t=10, b=40),
                         xaxis_title=text["profit_axis"],
                         yaxis=dict(categoryorder="array", categoryarray=labels, autorange="reversed"),
                         font=dict(size=13, color="#202a35"))
    return figure


if not (ROOT / "reports/profit_analysis.json").exists():
    st.error(text["missing"])
    st.stop()

summary, analysis, components, samples, calibration = load_results()
ab = summary["ab"]
model_name = summary["chosen_model"]
with st.sidebar:
    st.header(text["parameters"])
    contact_cost = st.slider(text["contact"], 0.0, 0.50, 0.15, step=0.05, format="$%.2f", key="contact")
    discount_pct = st.slider(text["discount"], 0, 30, 0, step=5, format="%d%%", key="discount")
    share_pct = st.select_slider(text["share"], list(range(0, 101, 10)), value=30, key="share")
    st.caption(text["currency_note"])
    st.caption(text["discount_note"])

policies = scenario(components, samples, contact_cost, discount_pct / 100)
selected_name = "no_mail" if share_pct == 0 else f"top_{share_pct}"
selected = policies.loc[policies.policy == selected_name].iloc[0]
all_policy = policies.loc[policies.policy == "mail_all"].iloc[0]
difference = selected.profit - all_policy.profit
difference_ci = profit_difference(samples, selected_name, "mail_all", contact_cost, discount_pct / 100)
candidates = policies.loc[policies.policy != "mail_all"].sort_values("k")
best = candidates.loc[candidates.profit.idxmax()]
suffix = "_it" if language == "Italiano" else ""
st.title(text["title"])
st.caption(text["caption"].format(n=f"{analysis['test_n']:,}".replace(",", " "), model=model_name))
tabs = st.tabs(text["tabs"])

with tabs[0]:
    columns = st.columns(3)
    columns[0].metric(text["effect"], f"+{number(ab['effect'] * 100)} {text['pp']}")
    columns[0].caption(f"{text['ci']}: [{number(ab['ci_low'] * 100)}; {number(ab['ci_high'] * 100)}] {text['pp']}")
    columns[1].metric(text["uplift_profit"].format(share=share_pct), money(selected.profit))
    columns[1].caption((text["ci"] + ": " + bounds(selected.ci_low, selected.ci_high)).replace("$", r"\$"))
    columns[2].metric(text["difference"], money(difference))
    columns[2].caption((text["diff_ci"] + ": " + bounds(*difference_ci)).replace("$", r"\$"))
    if difference_ci[0] <= 0 <= difference_ci[1]:
        st.info(text["uncertain"])
    elif difference_ci[0] > 0:
        st.info(text["positive"])
    else:
        st.info(text["negative"])
    st.subheader(text["profit_heading"])
    st.plotly_chart(policy_chart(candidates), use_container_width=True, config={"displayModeBar": False})
    st.caption(text["bootstrap"])
    rows = [{text["strategy"]: label(row), text["contacts"]: round(row.contacts),
             text["extra_orders"]: round(row.extra_orders, 1), text["profit"]: money(row.profit),
             text["profit_ci"]: bounds(row.ci_low, row.ci_high)} for row in candidates.itertuples()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(text["policy_note"])
    st.download_button(text["download"], policies.to_csv(index=False).encode("utf-8-sig"),
                       file_name="policy_intervals.csv", mime="text/csv")

with tabs[1]:
    st.subheader(text["ab_heading"])
    st.image(str(ROOT / f"reports/figures/experiment{suffix}.png"), use_container_width=True)
    st.markdown(text["ab_description"])
    st.dataframe(pd.DataFrame([
        {text["group"]: text["control"], text["customers"]: ab["control_n"],
         text["buyers"]: ab["control_orders"], text["conversion"]: number(ab["control_rate"] * 100, 3) + "%"},
        {text["group"]: text["treated"], text["customers"]: ab["treated_n"],
         text["buyers"]: ab["treated_orders"], text["conversion"]: number(ab["treated_rate"] * 100, 3) + "%"},
    ]), hide_index=True, use_container_width=True)
    st.write(text["p_values"].format(effect=f"{ab['p_value']:.2g}", srm=number(ab["srm_p_value"], 3)))
    st.caption(text["ab_note"])

with tabs[2]:
    st.subheader(text["qini_heading"])
    st.image(str(ROOT / f"reports/figures/qini{suffix}.png"), use_container_width=True)
    rows = [{text["model"]: name,
             text["qini_validation"]: summary["validation_metrics"].get(name, {}).get("qini"),
             text["qini_test"]: summary["test_metrics"][name]["qini"],
             text["uplift_30"]: summary["test_metrics"][name]["uplift_at_30"] * 100}
            for name in ["logistic", "forest", "response"]]
    st.dataframe(pd.DataFrame(rows).round(4), hide_index=True, use_container_width=True)
    st.markdown(text["qini_conclusion"])
    st.subheader(text["calibration_heading"])
    st.image(str(ROOT / f"reports/uplift_calibration{suffix}.png"), use_container_width=True)
    st.caption(text["calibration_note"])
    st.write(text["negative_deciles"].format(deciles=", ".join(map(str, analysis["negative_deciles"]))))
    calibration_display = calibration.copy()
    calibration_display[["predicted_uplift", "observed_uplift", "observed_ci_low", "observed_ci_high"]] *= 100
    st.dataframe(calibration_display.rename(columns=text["calibration_columns"]).round(4),
                 hide_index=True, use_container_width=True)
    st.subheader(text["budget_heading"])
    figure = go.Figure(go.Scatter(x=candidates.k, y=candidates.profit, mode="lines+markers",
                                  line=dict(color="#285b86"), name="Uplift"))
    figure.add_hline(y=0, line_color="#9ca3af", line_width=1)
    figure.add_vline(x=summary["selected_share"] * 100, line_color="#285b86", line_dash="dash")
    figure.update_layout(template="plotly_white", height=350, xaxis_title=text["budget_axis"],
                         yaxis_title=text["profit_axis"], showlegend=False)
    st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})
    st.caption(text["budget_note"])

with tabs[3]:
    st.subheader(text["sensitivity_heading"])
    st.write(text["best_scenario"].format(k=int(best.k), profit=money(best.profit),
                                         gain=money(best.profit - all_policy.profit)).replace("$", r"\$"))
    st.image(str(ROOT / f"reports/sensitivity_heatmap{suffix}.png"), use_container_width=True)
    st.caption(text["sensitivity_note"])
    st.image(str(ROOT / f"reports/break_even{suffix}.png"), use_container_width=True)
    conservative_discount = np.floor(analysis["mail_all_discount_limit_at_005_cost"] * 1000) / 10
    st.markdown(text["rule"].format(discount=number(conservative_discount, 1)))
    st.caption(text["rule_note"].replace("$", r"\$"))

with tabs[4]:
    st.subheader(text["calculation"])
    st.code(text["formula"], language="text")
    st.write(text["counts"].format(treated=int(selected.treated_n), control=int(selected.control_n)))
    st.write(text["breakdown"].format(orders=number(selected.extra_orders),
             contact=number(selected.contact_spend), discount=number(selected.discount_spend)).replace("$", r"\$"))
    for key in ["observed", "assumptions", "limits", "next", "source"]:
        st.markdown(text[key])
