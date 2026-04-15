import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../cashier_tokens.dart';
import '../models/cart_model.dart';
import '../models/catalog_model.dart';
import '../models/inventory_feed_model.dart';
import '../models/sync_state_model.dart';
import '../services/authenticated_api.dart';
import '../services/inventory_api.dart';
import '../util/money_format.dart';
import '../widgets/archive_section_header.dart';
import '../widgets/product_card.dart';

sealed class _LookupListItem {}

class _LookupGroupHeader extends _LookupListItem {
  _LookupGroupHeader(this.title);
  final String title;
}

class _LookupProduct extends _LookupListItem {
  _LookupProduct(this.row);
  final ProductRow row;
}

int _compareProductRowGroups(ProductRow a, ProductRow b) {
  final au = a.groupTitle == null || a.groupTitle!.trim().isEmpty;
  final bu = b.groupTitle == null || b.groupTitle!.trim().isEmpty;
  if (au != bu) {
    return au ? 1 : -1;
  }
  if (!au) {
    final c = a.groupTitle!.trim().compareTo(b.groupTitle!.trim());
    if (c != 0) {
      return c;
    }
  }
  return a.name.compareTo(b.name);
}

List<_LookupListItem> _buildLookupList(List<ProductRow> filtered) {
  final sorted = List<ProductRow>.from(filtered)..sort(_compareProductRowGroups);
  final out = <_LookupListItem>[];
  String? lastGroup;
  for (final p in sorted) {
    final key = (p.groupTitle != null && p.groupTitle!.trim().isNotEmpty)
        ? p.groupTitle!.trim()
        : null;
    if (key != null && key != lastGroup) {
      out.add(_LookupGroupHeader(key));
      lastGroup = key;
    } else if (key == null) {
      lastGroup = null;
    }
    out.add(_LookupProduct(p));
  }
  return out;
}

class InventoryLookupScreen extends StatefulWidget {
  const InventoryLookupScreen({super.key, this.initialSearchQuery});

  final String? initialSearchQuery;

  @override
  State<InventoryLookupScreen> createState() => _InventoryLookupScreenState();
}

class _InventoryLookupScreenState extends State<InventoryLookupScreen> {
  final _search = TextEditingController();
  String? _category;

  @override
  void initState() {
    super.initState();
    _search.addListener(() => setState(() {}));
    final q = widget.initialSearchQuery;
    if (q != null && q.isNotEmpty) {
      _search.text = q;
    }
  }

  @override
  void didUpdateWidget(covariant InventoryLookupScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    final q = widget.initialSearchQuery;
    if (q != oldWidget.initialSearchQuery && q != null && q.isNotEmpty) {
      _search.text = q;
    }
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  List<String> _categories(List<ProductRow> all) {
    final s = <String>{};
    for (final p in all) {
      final c = p.category?.trim();
      if (c != null && c.isNotEmpty) s.add(c);
    }
    final out = s.toList()..sort();
    return out;
  }

  List<ProductRow> _filtered(List<ProductRow> all) {
    var list = all;
    final cat = _category;
    if (cat != null) {
      list = list.where((p) => p.category == cat).toList();
    }
    final q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return list;
    return list.where((p) {
      return p.name.toLowerCase().contains(q) || p.sku.toLowerCase().contains(q);
    }).toList();
  }

  Future<void> _pull() async {
    final feed = context.read<InventoryFeedModel>();
    await feed.refresh(
      auth: context.read<AuthenticatedApi>(),
      sync: context.read<SyncStateModel>(),
      catalog: context.read<CatalogModel>(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final feed = context.watch<InventoryFeedModel>();
    final cart = context.watch<CartModel>();
    final theme = Theme.of(context);
    final cats = _categories(feed.products);
    final filtered = _filtered(feed.products);
    final lookupItems = _buildLookupList(filtered);
    final code = feed.currencyCode;
    final exp = feed.currencyExponent;
    final sym = feed.currencySymbolOverride;

    return Scaffold(
      body: CustomScrollView(
        slivers: [
          SliverAppBar.medium(
            title: const Text('Inventory lookup'),
            actions: [
              IconButton(
                tooltip: 'Refresh catalog',
                onPressed: feed.loading ? null : _pull,
                icon: const Icon(Icons.sync_rounded),
              ),
            ],
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(
                CashierSpacing.gutter,
                0,
                CashierSpacing.gutter,
                CashierSpacing.sm,
              ),
              child: TextField(
                controller: _search,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search_rounded),
                  hintText: 'Search name or SKU',
                ),
              ),
            ),
          ),
          if (cats.isNotEmpty)
            SliverToBoxAdapter(
              child: SizedBox(
                height: 44,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        label: const Text('All'),
                        selected: _category == null,
                        onSelected: (_) => setState(() => _category = null),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(CashierRadius.chip),
                        ),
                      ),
                    ),
                    ...cats.map(
                      (c) => Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: FilterChip(
                          label: Text(c),
                          selected: _category == c,
                          onSelected: (_) => setState(() => _category = c),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(CashierRadius.chip),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          if (feed.error != null)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
                child: Text(
                  feed.error!,
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ),
            ),
          if (feed.loading && feed.products.isEmpty)
            const SliverFillRemaining(
              hasScrollBody: false,
              child: Center(child: CircularProgressIndicator()),
            )
          else ...[
            SliverToBoxAdapter(
              child: ArchiveSectionHeader(
                kicker: 'Archive',
                title: 'Inventory',
                subtitle: '${filtered.length} shown · ${cart.itemCount} items in cart',
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
              sliver: SliverList(
                delegate: SliverChildBuilderDelegate(
                  (context, i) {
                    final item = lookupItems[i];
                    if (item is _LookupGroupHeader) {
                      return Padding(
                        padding: EdgeInsets.only(
                          top: i == 0 ? CashierSpacing.sm : CashierSpacing.lg,
                          bottom: CashierSpacing.xs,
                        ),
                        child: Text(
                          item.title,
                          style: theme.textTheme.labelLarge?.copyWith(
                            color: CashierColors.primary,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.4,
                          ),
                        ),
                      );
                    }
                    final r = (item as _LookupProduct).row;
                    final price = formatMinorUnits(
                      r.unitPriceCents,
                      code: code,
                      exponent: exp,
                      symbolOverride: sym,
                    );
                    return Padding(
                      padding: const EdgeInsets.only(bottom: CashierSpacing.sm),
                      child: ProductCard(
                        product: r,
                        priceLabel: price,
                        onAdd: () {
                          final c = context.read<CartModel>();
                          final idx = c.lines.indexWhere((l) => l.productId == r.id);
                          final inCart = idx >= 0 ? c.lines[idx].quantity : 0;
                          if (inCart + 1 > r.quantity) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Not enough stock for this item')),
                            );
                            return;
                          }
                          HapticFeedback.lightImpact();
                          c.addProduct(r);
                        },
                      ),
                    );
                  },
                  childCount: lookupItems.length,
                ),
              ),
            ),
            const SliverToBoxAdapter(child: SizedBox(height: CashierSpacing.xl)),
          ],
        ],
      ),
    );
  }
}
