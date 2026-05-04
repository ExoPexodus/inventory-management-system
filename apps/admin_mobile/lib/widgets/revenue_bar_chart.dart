import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../admin_tokens.dart';
import '../models/analytics.dart';

class RevenueBarChart extends StatefulWidget {
  const RevenueBarChart({
    super.key,
    required this.points,
    required this.formatValue,
  });

  final List<SalesPoint> points;
  final String Function(int cents) formatValue;

  @override
  State<RevenueBarChart> createState() => _RevenueBarChartState();
}

class _RevenueBarChartState extends State<RevenueBarChart> {
  int? _touched;

  // Pixels allocated per bar (bar + gap). Enough to be tappable and readable.
  static const double _slotWidth = 22.0;

  // Show a label every N bars to avoid overlap on dense views.
  int _labelStride(int count) {
    if (count <= 10) return 1;
    if (count <= 35) return 5;
    return 10;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final points = widget.points;

    if (points.isEmpty) {
      return SizedBox(
        height: 180,
        child: Center(
          child: Text(
            'No data',
            style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant),
          ),
        ),
      );
    }

    final maxVal = points.map((p) => p.grossCents).reduce((a, b) => a > b ? a : b);
    final stride = _labelStride(points.length);

    return LayoutBuilder(
      builder: (context, constraints) {
        final minChartWidth = points.length * _slotWidth;
        final chartWidth = minChartWidth > constraints.maxWidth ? minChartWidth : constraints.maxWidth;
        final needsScroll = chartWidth > constraints.maxWidth;

        Widget chart = SizedBox(
          height: 200,
          width: chartWidth,
          child: BarChart(
            BarChartData(
              maxY: maxVal == 0 ? 100 : maxVal * 1.25,
              barTouchData: BarTouchData(
                touchCallback: (event, response) {
                  setState(() {
                    if (event is FlTapUpEvent || event is FlPointerExitEvent) {
                      _touched = null;
                    } else {
                      _touched = response?.spot?.touchedBarGroupIndex;
                    }
                  });
                },
                touchTooltipData: BarTouchTooltipData(
                  getTooltipColor: (_) => AdminColors.primary,
                  getTooltipItem: (group, groupIndex, rod, rodIndex) {
                    final p = points[groupIndex];
                    return BarTooltipItem(
                      '${widget.formatValue(p.grossCents)}\n',
                      const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12),
                      children: [
                        TextSpan(
                          text: '${p.transactionCount} sales',
                          style: const TextStyle(color: Colors.white70, fontSize: 10),
                        ),
                      ],
                    );
                  },
                ),
              ),
              titlesData: FlTitlesData(
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    getTitlesWidget: (value, meta) {
                      final i = value.toInt();
                      if (i < 0 || i >= points.length) return const SizedBox.shrink();
                      // Only show every nth label to avoid overlap
                      if (i % stride != 0) return const SizedBox.shrink();
                      return Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(
                          points[i].label,
                          style: TextStyle(
                            fontSize: 10,
                            color: AdminColors.onSurfaceVariant,
                            fontWeight: _touched == i ? FontWeight.w700 : FontWeight.w400,
                          ),
                        ),
                      );
                    },
                    reservedSize: 26,
                  ),
                ),
                leftTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
              ),
              gridData: FlGridData(
                show: true,
                drawVerticalLine: false,
                horizontalInterval: maxVal == 0 ? 100 : maxVal / 4,
                getDrawingHorizontalLine: (_) => FlLine(
                  color: AdminColors.outlineVariant.withValues(alpha: 0.4),
                  strokeWidth: 1,
                ),
              ),
              borderData: FlBorderData(show: false),
              barGroups: List.generate(points.length, (i) {
                final p = points[i];
                final isTouched = _touched == i;
                return BarChartGroupData(
                  x: i,
                  barRods: [
                    BarChartRodData(
                      toY: p.grossCents.toDouble(),
                      color: isTouched
                          ? AdminColors.primary
                          : AdminColors.primary.withValues(alpha: 0.55),
                      width: points.length > 10 ? 10 : 20,
                      borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
                    ),
                  ],
                );
              }),
            ),
          ),
        );

        if (needsScroll) {
          chart = SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: chart,
          );
        }

        return chart;
      },
    );
  }
}
