#!/usr/bin/env python3
"""runner.py — JSON-in/JSON-out DICE damage-function wrapper.

Role in the FaIR → DICE → FinancePy pipeline
─────────────────────────────────────────────
FaIR emits a temperature trajectory for one or more emissions scenarios.
This script converts that trajectory to a per-year fraction of GDP lost,
using the DICE 2016R damage function (Nordhaus 2017, Eq. 5):

    DAMFRAC(T) = a1·T + a2·T^a3
               ≈ 0.00236 · T²   (a1 = 0 in published parameters)

It then averages that loss over the life of a bond and returns a climate
risk premium (as a decimal yield spread) ready for FinancePy to apply.

TO RUN:
  From inside the repo root:
    python runner.py fair_output.json
  Or piped:
    python runner.py < fair_output.json

INPUT JSON keys:
  timebounds            list[int]  calendar years from FaIR                (required)
  scenarios             list[str]  scenario labels from FaIR               (required)
  configs               list[str]  config labels from FaIR                 (required)
  temperature_K         dict       {scenario: {config: [float, ...]}}      (required)
  bond_horizon_end      int        bond maturity year; damages are averaged (default: last timebounds year)
                                   up to and including this year
  temperature_offset_K  float      shift applied to each temperature value  (default: 0.7)
                                   before the damage function is evaluated.
                                   FaIR initialises temperature to 0 at
                                   run-start; adding ~0.7 K converts a
                                   2000-baseline anomaly to a
                                   pre-industrial baseline, which is what
                                   the DICE damage function expects.
  baseline_ytm          float      if provided, adjusted_ytm is included    (optional)
                                   in the output for each scenario/config

OUTPUT JSON keys:
  scenarios              list   echoed from input
  configs                list   echoed from input
  timebounds             list   years clipped to [first timebounds year, bond_horizon_end]
  damage_fraction        dict   {scenario: {config: [float, ...]}}
                                DICE DAMFRAC per year — fractional GDP loss
  horizon_mean_damage    dict   {scenario: {config: float}}
                                mean annual damage fraction over the bond horizon
  climate_risk_premium   dict   {scenario: {config: float}}
                                decimal yield spread (e.g. 0.02 = 200 bps).
                                Equals horizon_mean_damage — a 2 % expected
                                GDP loss is treated as 200 bps of sovereign
                                risk premium (cf. Dietz & Stern 2015).
  adjusted_ytm           dict   {scenario: {config: float}}
                                baseline_ytm + climate_risk_premium.
                                Only present when baseline_ytm is supplied.
"""

import argparse
import json
import sys

# ── DICE 2016R damage-function parameters (Nordhaus 2017, Table 1) ──────────
# Source: dicepy/dice_params.py  _a1=0.0, _a2=0.00236, _a3=2.00
_A1 = 0.0
_A2 = 0.00236
_A3 = 2.00
# ────────────────────────────────────────────────────────────────────────────


def _damfrac(temp_c: float) -> float:
    """DICE 2016R quadratic damage function.

    Returns the fraction of GDP lost at a given temperature anomaly
    (degrees C above pre-industrial baseline).  Negative anomalies
    are clamped to zero — DICE does not model benefits from cooling.
    """
    t = max(temp_c, 0.0)
    return _A1 * t + _A2 * (t ** _A3)


def run(params: dict) -> dict:
    timebounds = params["timebounds"]
    scenarios = params["scenarios"]
    configs = params["configs"]
    temp_data = params["temperature_K"]

    bond_end = params.get("bond_horizon_end", timebounds[-1])
    offset = params.get("temperature_offset_K", 0.7)
    baseline_ytm = params.get("baseline_ytm")

    # Clip the time series to the bond's life
    clipped_years = [y for y in timebounds if y <= bond_end]
    n = len(clipped_years)

    damage_fraction: dict = {}
    horizon_mean_damage: dict = {}
    climate_risk_premium: dict = {}
    adjusted_ytm: dict | None = {} if baseline_ytm is not None else None

    for scenario in scenarios:
        damage_fraction[scenario] = {}
        horizon_mean_damage[scenario] = {}
        climate_risk_premium[scenario] = {}
        if adjusted_ytm is not None:
            adjusted_ytm[scenario] = {}

        for config in configs:
            temps = temp_data[scenario][config][:n]
            damages = [_damfrac(t + offset) for t in temps]
            mean_dmg = sum(damages) / len(damages) if damages else 0.0

            damage_fraction[scenario][config] = damages
            horizon_mean_damage[scenario][config] = mean_dmg
            climate_risk_premium[scenario][config] = mean_dmg

            if adjusted_ytm is not None:
                adjusted_ytm[scenario][config] = baseline_ytm + mean_dmg

    result: dict = {
        "scenarios": list(scenarios),
        "configs": list(configs),
        "timebounds": clipped_years,
        "damage_fraction": damage_fraction,
        "horizon_mean_damage": horizon_mean_damage,
        "climate_risk_premium": climate_risk_premium,
    }
    if adjusted_ytm is not None:
        result["adjusted_ytm"] = adjusted_ytm

    return result


def _load_input_json() -> dict:
    parser = argparse.ArgumentParser(
        description=(
            "DICE damage runner: convert FaIR temperature output to a "
            "climate risk premium for FinancePy bond pricing."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Path to input JSON file, or '-' to read from stdin (default).",
    )
    args = parser.parse_args()

    if args.input == "-":
        return json.load(sys.stdin)

    with open(args.input, "r", encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    input_data = _load_input_json()
    output_data = run(input_data)
    json.dump(output_data, sys.stdout, indent=2)
    print()  # trailing newline
