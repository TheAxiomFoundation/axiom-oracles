from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .common import DEFAULT_TIMEOUT_SECONDS, OfficialArtifact, artifact_from_response, new_session


GST_HST_CALCULATOR_URL = (
    "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/"
    "gst-hst-businesses/charge-collect-which-rate/calculator.html"
)
_RATES_RE = re.compile(r"const rates\s*=\s*(\[.*?\]);", re.DOTALL)


@dataclass(frozen=True)
class SalesTaxCalculation:
    region: str
    amount_before_tax: Decimal
    gst: Decimal
    provincial_tax: Decimal
    total: Decimal
    artifact: OfficialArtifact


class GstHstCalculator:
    """Execute the arithmetic and live rate table published in CRA's page bundle."""

    def __init__(self, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout = timeout

    def calculate_before_tax(self, region: str, amount: Decimal) -> SalesTaxCalculation:
        response = new_session().get(GST_HST_CALCULATOR_URL, timeout=self.timeout)
        response.raise_for_status()
        match = _RATES_RE.search(response.text)
        if not match:
            raise RuntimeError("CRA GST/HST calculator rate table was not found")
        rates = json.loads(match.group(1))
        selected = next(
            (item for item in rates if item.get("regioncode") == region.lower()),
            None,
        )
        if selected is None:
            raise ValueError(f"unsupported CRA GST/HST region code: {region}")
        price = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        gst = price * Decimal(str(selected["baseamount"]))
        provincial_rate = Decimal(str(selected.get("provtax", {}).get("amount", 0)))
        provincial_tax = price * provincial_rate
        total = (price + gst + provincial_tax).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return SalesTaxCalculation(
            region=region.lower(),
            amount_before_tax=price,
            gst=gst,
            provincial_tax=provincial_tax,
            total=total,
            artifact=artifact_from_response(response),
        )
