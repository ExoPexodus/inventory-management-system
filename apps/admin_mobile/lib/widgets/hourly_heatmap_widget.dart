import 'package:flutter/material.dart';

import '../admin_tokens.dart';
import '../models/analytics.dart';

class HourlyHeatmapWidget extends StatefulWidget {
  const HourlyHeatmapWidget({
    super.key,
    required this.buckets,
    required this.formatValue,
  });

  final List<HeatmapBucket> buckets;
  final String Function(int cents) formatValue;

  @override
  State<HourlyHeatmapWidget> createState() => _HourlyHeatmapWidgetState();
}

class _HourlyHeatmapWidgetState extends State<HourlyHeatmapWidget> {
  int? _selectedHour;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final buckets = widget.buckets;

    if (buckets.isEmpty) {
      return SizedBox(
        height: 60,
        child: Center(
          child: Text(
            'No data',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: AdminColors.onSurfaceVariant),
          ),
        ),
      );
    }

    final maxCents = buckets
        .map((b) => b.avgGrossCents)
        .fold(0, (a, b) => a > b ? a : b);

    HeatmapBucket? selectedBucket;
    if (_selectedHour != null) {
      try {
        selectedBucket =
            buckets.firstWhere((b) => b.hour == _selectedHour);
      } catch (_) {}
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (selectedBucket != null)
          Padding(
            padding: const EdgeInsets.only(bottom: AdminSpacing.sm),
            child: Text(
              '${_selectedHour.toString().padLeft(2, '0')}:00 · avg ${widget.formatValue(selectedBucket.avgGrossCents)} · ${selectedBucket.avgTxCount.toStringAsFixed(1)} txns',
              style: theme.textTheme.bodySmall?.copyWith(
                color: AdminColors.primary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        SizedBox(
          height: 52,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: 24,
            separatorBuilder: (context, index) =>
                const SizedBox(width: 3),
            itemBuilder: (context, hour) {
              HeatmapBucket? bucket;
              try {
                bucket = buckets.firstWhere((b) => b.hour == hour);
              } catch (_) {}
              final cents = bucket?.avgGrossCents ?? 0;
              final intensity = maxCents > 0 ? cents / maxCents : 0.0;
              final isSelected = _selectedHour == hour;
              final hasData = cents > 0;

              return GestureDetector(
                onTap: () => setState(
                  () => _selectedHour = isSelected ? null : hour,
                ),
                child: Container(
                  width: 26,
                  decoration: BoxDecoration(
                    color: hasData
                        ? AdminColors.primary
                            .withValues(alpha: 0.10 + 0.75 * intensity)
                        : AdminColors.surfaceContainerHigh,
                    borderRadius: BorderRadius.circular(4),
                    border: isSelected
                        ? Border.all(
                            color: AdminColors.primary, width: 2)
                        : null,
                  ),
                  child: Center(
                    child: Text(
                      '$hour',
                      style: TextStyle(
                        fontSize: 9,
                        fontWeight: FontWeight.w600,
                        color: intensity > 0.55
                            ? Colors.white
                            : AdminColors.onSurfaceVariant,
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Text(
            'Tap a block to see details · hours 00–23',
            style: theme.textTheme.labelSmall?.copyWith(
              color: AdminColors.onSurfaceVariant,
            ),
          ),
        ),
      ],
    );
  }
}
