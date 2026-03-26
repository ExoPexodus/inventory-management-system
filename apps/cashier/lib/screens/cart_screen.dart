import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import '../cashier_tokens.dart';
import '../models/cart_model.dart';
import '../models/catalog_model.dart';
import '../models/sync_state_model.dart';
import '../services/inventory_api.dart';
import '../services/outbox_service.dart';
import '../services/session_store.dart';
import '../util/jwt_device_id.dart';
import '../util/json_map.dart';
import '../util/money_format.dart';
import '../util/push_conflict_message.dart';
import '../widgets/gradient_primary_button.dart';

class CartScreen extends StatefulWidget {
  const CartScreen({super.key, required this.onSaleComplete});

  final Future<void> Function() onSaleComplete;

  @override
  State<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends State<CartScreen> {
  String _tender = 'cash';
  String _currencyCode = 'USD';
  int _currencyExponent = 2;
  String? _currencySymbolOverride;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    _loadCurrency();
  }

  Future<void> _loadCurrency() async {
    final code = await SessionStore.getCurrencyCode();
    final exp = await SessionStore.getCurrencyExponent();
    final sym = await SessionStore.getCurrencySymbolOverride();
    if (!mounted) return;
    setState(() {
      _currencyCode = code;
      _currencyExponent = exp;
      _currencySymbolOverride = sym;
    });
  }

  Future<bool> _hasNetworkForCard() async {
    final r = await Connectivity().checkConnectivity();
    return r.any((e) =>
        e == ConnectivityResult.mobile ||
        e == ConnectivityResult.wifi ||
        e == ConnectivityResult.ethernet);
  }

  Future<bool> _cardAllowedByPolicy(SessionData session) async {
    // Default org policy: card tender requires live central connectivity.
    if (!await _hasNetworkForCard()) return false;
    final api = InventoryApi(session.baseUrl);
    return api.ping(timeoutMs: 2500);
  }

  Future<SessionData?> _refreshSessionIfNeeded(
    InventoryApi api,
    SessionData s,
  ) async {
    final body = await api.refresh(refreshToken: s.refreshToken);
    await SessionStore.save(
      baseUrl: s.baseUrl,
      accessToken: body['access_token'] as String,
      refreshToken: body['refresh_token'] as String,
      tenantId: body['tenant_id'] as String,
      shopIds: (body['shop_ids'] as List<dynamic>).map((x) => x.toString()).toList(),
    );
    return SessionStore.load();
  }

  Future<void> _finishQueuedSale(BuildContext context, CartModel cart) async {
    cart.clear();
    // Do not block cashier flow on a slow/failed refresh when offline.
    unawaited(widget.onSaleComplete());
    if (!context.mounted) return;
    final sync = context.read<SyncStateModel>();
    await sync.refreshFromStorage();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Sale queued. It will sync when you are online.')),
    );
  }

  Future<void> _submit(BuildContext context, CartModel cart) async {
    if (cart.lines.isEmpty || _submitting) return;

    final session = await SessionStore.load();
    if (session == null) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No session')),
        );
      }
      return;
    }

    if (_tender == 'card' && !await _cardAllowedByPolicy(session)) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Card payment blocked by organization policy. Connect to the central system to use card tender.',
          ),
        ),
      );
      return;
    }

    final deviceId = deviceIdFromAccessToken(session.accessToken);
    if (deviceId == null) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not read device id from token')),
        );
      }
      return;
    }

    final cartCopy = List<CartLine>.from(cart.lines);
    final subtotalCents = cartCopy.fold(0, (a, b) => a + b.lineSubtotalCents);
    final taxTotalCents = cartCopy.fold(0, (a, b) => a + b.lineTaxCents);
    final grandCents = subtotalCents + taxTotalCents;
    final clientMutationId = const Uuid().v4();
    final idempotencyKey = const Uuid().v4();
    final event = <String, dynamic>{
      'type': 'sale_completed',
      'occurred_at': DateTime.now().toUtc().toIso8601String(),
      'client_mutation_id': clientMutationId,
      'shop_id': session.defaultShopId,
      'lines': cartCopy
          .map(
            (l) => {
              'product_id': l.productId,
              'quantity': l.quantity,
              'unit_price_cents': l.unitPriceCents,
            },
          )
          .toList(),
      'payments': [
        {
          'tender_type': _tender,
          'amount_cents': grandCents,
          if (_tender == 'card') 'external_ref': 'client-mvp-card',
        },
      ],
    };

    if (_tender == 'cash' && !await _hasNetworkForCard()) {
      setState(() => _submitting = true);
      try {
        await OutboxService.enqueue(
          clientMutationId: clientMutationId,
          idempotencyKey: idempotencyKey,
          event: event,
        );
        if (!mounted || !context.mounted) return;
        await _finishQueuedSale(context, cart);
      } finally {
        if (mounted) setState(() => _submitting = false);
      }
      return;
    }

    if (!context.mounted) return;
    setState(() => _submitting = true);
    try {
      final api = InventoryApi(session.baseUrl);

      Future<Map<String, dynamic>> doPush(SessionData s) {
        final d = deviceIdFromAccessToken(s.accessToken) ?? deviceId;
        return api.syncPush(
          accessToken: s.accessToken,
          deviceId: d,
          idempotencyKey: idempotencyKey,
          events: [event],
          timeoutMs: _tender == 'cash' ? 2500 : null,
        );
      }

      late Map<String, dynamic> response;
      try {
        response = await doPush(session);
      } on ApiException catch (e) {
        if (e.statusCode == 401) {
          final next = await _refreshSessionIfNeeded(api, session);
          if (next == null) rethrow;
          response = await doPush(next);
        } else if (_tender == 'cash' && e.statusCode >= 500) {
          await OutboxService.enqueue(
            clientMutationId: clientMutationId,
            idempotencyKey: idempotencyKey,
            event: event,
          );
          if (!context.mounted) return;
          await _finishQueuedSale(context, cart);
          return;
        } else {
          rethrow;
        }
      } catch (e) {
        if (_tender == 'cash') {
          await OutboxService.enqueue(
            clientMutationId: clientMutationId,
            idempotencyKey: idempotencyKey,
            event: event,
          );
          if (!context.mounted) return;
          await _finishQueuedSale(context, cart);
          return;
        }
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Checkout failed: $e')),
          );
        }
        return;
      }

      final results = (response['results'] as List<dynamic>).cast<Map<String, dynamic>>();
      if (results.isEmpty) throw StateError('Empty results');
      final status = results.first['status'] as String?;
      final detail = results.first['detail'] as String?;

      if (!context.mounted) return;
      if (status == 'accepted' || status == 'duplicate') {
        cart.clear();
        await widget.onSaleComplete();
        if (!context.mounted) return;
        final syncOkWidget = context.read<SyncStateModel>();
        await syncOkWidget.refreshFromStorage();
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(status == 'duplicate' ? 'Sale already recorded.' : 'Sale completed.')),
          );
        }
      } else {
        final conflict = asJsonObject(results.first['conflict']);
        final msg = describePushConflict(conflict, detail);
        await showDialog<void>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Sale not accepted'),
            content: Text(msg),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text('OK'),
              ),
            ],
          ),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Checkout failed: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cart = context.watch<CartModel>();
    final theme = Theme.of(context);
    final subtotalFmt = formatMinorUnits(
      cart.subtotalCents,
      code: _currencyCode,
      exponent: _currencyExponent,
      symbolOverride: _currencySymbolOverride,
    );
    final taxFmt = formatMinorUnits(
      cart.taxCents,
      code: _currencyCode,
      exponent: _currencyExponent,
      symbolOverride: _currencySymbolOverride,
    );
    final grandFmt = formatMinorUnits(
      cart.grandTotalCents,
      code: _currencyCode,
      exponent: _currencyExponent,
      symbolOverride: _currencySymbolOverride,
    );

    return Scaffold(
      body: CustomScrollView(
        slivers: [
          const SliverAppBar.medium(
            title: Text('Checkout'),
          ),
          if (cart.lines.isNotEmpty)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  CashierSpacing.gutter,
                  0,
                  CashierSpacing.gutter,
                  CashierSpacing.sm,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Current order',
                      style: theme.textTheme.labelSmall?.copyWith(
                        letterSpacing: 1.1,
                        fontWeight: FontWeight.w700,
                        color: CashierColors.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text('Review lines, tax, and tender', style: theme.textTheme.bodySmall),
                  ],
                ),
              ),
            ),
          if (cart.lines.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: Padding(
                padding: const EdgeInsets.all(CashierSpacing.gutter),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.shopping_bag_outlined,
                      size: 56,
                      color: CashierColors.onSurfaceVariant.withValues(alpha: 0.5),
                    ),
                    const SizedBox(height: CashierSpacing.md),
                    Text(
                      'Your cart is empty',
                      style: theme.textTheme.titleLarge,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: CashierSpacing.sm),
                    Text(
                      'Add items from Inventory lookup to start a sale.',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: CashierColors.onSurfaceVariant,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            )
          else ...[
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
              sliver: SliverList.separated(
                itemCount: cart.lines.length,
                separatorBuilder: (context, _) => const SizedBox(height: CashierSpacing.sm),
                itemBuilder: (context, i) {
                  final l = cart.lines[i];
                  final stockLeft = context.watch<CatalogModel>().stockFor(l.productId);
                  final low = stockLeft > 0 && stockLeft <= 5;
                  final lineTotal = formatMinorUnits(
                    l.lineSubtotalCents,
                    code: _currencyCode,
                    exponent: _currencyExponent,
                    symbolOverride: _currencySymbolOverride,
                  );
                  final lineTax = formatMinorUnits(
                    l.lineTaxCents,
                    code: _currencyCode,
                    exponent: _currencyExponent,
                    symbolOverride: _currencySymbolOverride,
                  );
                  final unitPrice = formatMinorUnits(
                    l.unitPriceCents,
                    code: _currencyCode,
                    exponent: _currencyExponent,
                    symbolOverride: _currencySymbolOverride,
                  );
                  return Material(
                    color: CashierColors.card,
                    borderRadius: BorderRadius.circular(CashierRadius.quickTile),
                    child: Padding(
                      padding: const EdgeInsets.all(CashierSpacing.md),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(l.name, style: theme.textTheme.titleMedium),
                                    if (l.variantLabel != null && l.variantLabel!.trim().isNotEmpty) ...[
                                      const SizedBox(height: 4),
                                      Text(
                                        l.variantLabel!.trim(),
                                        style: theme.textTheme.bodySmall?.copyWith(
                                          color: CashierColors.onSurfaceVariant,
                                        ),
                                      ),
                                    ],
                                    const SizedBox(height: 6),
                                    Text(
                                      'Ref · ${l.sku} · $unitPrice each',
                                      style: theme.textTheme.labelMedium,
                                    ),
                                    if (low)
                                      Padding(
                                        padding: const EdgeInsets.only(top: 4),
                                        child: Text(
                                          'Low stock ($stockLeft on hand)',
                                          style: theme.textTheme.labelSmall?.copyWith(
                                            color: CashierColors.onSecondaryContainer,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                      ),
                                    if (l.lineTaxCents > 0 || l.taxExempt)
                                      Padding(
                                        padding: const EdgeInsets.only(top: 4),
                                        child: Text(
                                          l.taxExempt
                                              ? 'Tax exempt'
                                              : 'Tax · $lineTax',
                                          style: theme.textTheme.labelSmall,
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                              Text(
                                lineTotal,
                                style: theme.textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: CashierSpacing.sm),
                          Row(
                            children: [
                              _QtyIconBtn(
                                icon: Icons.remove_rounded,
                                onPressed: l.quantity > 1
                                    ? () => cart.setLineQuantity(l.productId, l.quantity - 1)
                                    : null,
                              ),
                              Padding(
                                padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.md),
                                child: Text(
                                  '${l.quantity}',
                                  style: theme.textTheme.titleMedium,
                                ),
                              ),
                              _QtyIconBtn(
                                icon: Icons.add_rounded,
                                onPressed: () {
                                  final maxQ = context.read<CatalogModel>().stockFor(l.productId);
                                  if (l.quantity >= maxQ) return;
                                  cart.setLineQuantity(l.productId, l.quantity + 1);
                                },
                              ),
                              const Spacer(),
                              IconButton(
                                tooltip: 'Remove line',
                                onPressed: () => cart.removeLine(l.productId),
                                icon: const Icon(Icons.delete_outline_rounded),
                                color: CashierColors.onSurfaceVariant,
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
            const SliverToBoxAdapter(child: SizedBox(height: 24)),
          ],
        ],
      ),
      bottomNavigationBar: cart.lines.isEmpty
          ? null
          : Container(
              padding: EdgeInsets.fromLTRB(
                CashierSpacing.gutter,
                CashierSpacing.md,
                CashierSpacing.md,
                CashierSpacing.md + MediaQuery.of(context).padding.bottom,
              ),
              decoration: BoxDecoration(
                color: CashierColors.surfaceContainerLow.withValues(alpha: 0.96),
                boxShadow: [
                  BoxShadow(
                    color: CashierColors.onSurface.withValues(alpha: 0.06),
                    blurRadius: 24,
                    offset: const Offset(0, -4),
                  ),
                ],
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Subtotal', style: theme.textTheme.labelMedium),
                      Text(subtotalFmt, style: theme.textTheme.titleSmall),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Tax', style: theme.textTheme.labelMedium),
                      Text(taxFmt, style: theme.textTheme.titleSmall),
                    ],
                  ),
                  const SizedBox(height: CashierSpacing.sm),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Grand total', style: theme.textTheme.labelLarge),
                      Text(
                        grandFmt,
                        style: theme.textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: CashierSpacing.md),
                  SegmentedButton<String>(
                    segments: const [
                      ButtonSegment(
                        value: 'cash',
                        label: Text('Cash'),
                        icon: Icon(Icons.payments_outlined),
                      ),
                      ButtonSegment(
                        value: 'card',
                        label: Text('Card'),
                        icon: Icon(Icons.credit_card_rounded),
                      ),
                    ],
                    selected: {_tender},
                    onSelectionChanged: (s) => setState(() => _tender = s.first),
                  ),
                  const SizedBox(height: CashierSpacing.sm),
                  Text(
                    'Card requires Wi‑Fi or mobile data.',
                    style: theme.textTheme.labelSmall,
                  ),
                  const SizedBox(height: CashierSpacing.md),
                  CashierGradientButton(
                    label: _submitting ? 'Processing…' : 'Complete sale',
                    icon: Icons.check_rounded,
                    onPressed: _submitting ? null : () => _submit(context, cart),
                  ),
                ],
              ),
            ),
    );
  }
}

class _QtyIconBtn extends StatelessWidget {
  const _QtyIconBtn({required this.icon, required this.onPressed});

  final IconData icon;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: CashierColors.surfaceContainer,
      borderRadius: BorderRadius.circular(CashierRadius.chip),
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(CashierRadius.chip),
        child: SizedBox(
          width: 40,
          height: 40,
          child: Icon(icon, size: 22),
        ),
      ),
    );
  }
}
