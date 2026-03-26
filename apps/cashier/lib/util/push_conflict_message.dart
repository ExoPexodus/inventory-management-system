/// User-facing explanation for a rejected sync event.
String describePushConflict(Map<String, dynamic>? conflict, String? detail) {
  final c = conflict;
  if (c == null || c.isEmpty) {
    return detail ?? 'The sale was not accepted. Try syncing and try again.';
  }
  final code = c['code'] as String?;
  switch (code) {
    case 'insufficient_stock':
      final name = c['name'] as String? ?? c['sku'] as String? ?? 'This product';
      final avail = c['available_quantity'];
      final req = c['requested_quantity'];
      return 'Not enough stock for $name (available: $avail, in cart: $req). Sync inventory and adjust the cart.';
    case 'payment_total_mismatch':
      final grand = c['grand_total_cents'];
      final tender = c['tender_total_cents'];
      final tax = c['tax_cents'];
      if (grand != null && tender != null) {
        return 'Payment total ($tender) must equal grand total including tax ($grand${tax != null ? ', tax $tax' : ''}).';
      }
      return 'Payment total does not match subtotal plus tax.';
    case 'shop_not_allowed_for_device':
      return 'This register is not allowed to sell for this shop.';
    case 'unknown_product':
      return 'A product in the sale is missing or inactive. Sync and remove it from the cart.';
    case 'no_lines':
      return 'The sale had no line items.';
    case 'bad_line':
      return 'A line item had invalid quantity or price.';
    case 'bad_payment':
      return 'A payment had an invalid amount.';
    case 'card_requires_connectivity':
      return 'Card sales require a live connection to the server.';
    case 'zero_delta':
      return 'Adjustment amount cannot be zero.';
    case 'unknown_event':
      final t = c['event_type'];
      return 'Unsupported event type${t != null ? ' ($t)' : ''}.';
    default:
      return detail ?? code ?? 'The sale was not accepted.';
  }
}
