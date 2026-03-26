/// Basis-point sales tax aligned with server `app.services.tax.line_tax_cents` (half-up).
int lineTaxCents({
  required int lineSubtotalCents,
  required int effectiveTaxRateBps,
  required bool taxExempt,
}) {
  if (taxExempt || effectiveTaxRateBps <= 0 || lineSubtotalCents <= 0) {
    return 0;
  }
  return (lineSubtotalCents * effectiveTaxRateBps + 5000) ~/ 10000;
}
