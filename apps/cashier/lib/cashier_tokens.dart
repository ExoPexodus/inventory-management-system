import 'package:flutter/material.dart';

/// Spacing rhythm from Stitch “Tactile Archive” design system (spacing scale 3).
abstract final class CashierSpacing {
  static const double xs = 6;
  static const double sm = 10;
  static const double md = 16;
  static const double lg = 22;
  static const double xl = 28;
  static const double xxl = 36;
  static const double gutter = 20;
}

/// Radii used on hero bands and quick-access tiles (Stitch mobile HTML).
abstract final class CashierRadius {
  static const double hero = 20;
  static const double chip = 10;
  static const double quickTile = 16;
}

/// Named colors from Stitch project `2327673696871788694` (Tactile Archive).
abstract final class CashierColors {
  static const Color primary = Color(0xFF06274D);
  static const Color primaryContainer = Color(0xFF223D64);
  static const Color onPrimary = Color(0xFFFFFFFF);
  static const Color surface = Color(0xFFFBF9F4);
  static const Color surfaceContainerLow = Color(0xFFF5F3EE);
  static const Color surfaceContainer = Color(0xFFF0EEE9);
  static const Color surfaceContainerHigh = Color(0xFFEAE8E3);
  static const Color card = Color(0xFFFFFFFF);
  static const Color onSurface = Color(0xFF1B1C19);
  static const Color onSurfaceVariant = Color(0xFF43474C);
  static const Color secondaryContainer = Color(0xFFFED65B);
  static const Color onSecondaryContainer = Color(0xFF745C00);
  static const Color outlineVariant = Color(0xFFC4C6CD);
  static const Color tertiaryFixed = Color(0xFFFFDF99);
  static const Color error = Color(0xFFB3261E);
  static const Color errorContainer = Color(0xFFFFDAD6);
  static const Color onErrorContainer = Color(0xFF93000A);
  static const Color surfaceTint = Color(0xFF455F88);
}

/// Deep indigo → teal wash for dashboard hero (Stitch archive gradient).
abstract final class CashierHeroGradient {
  static const LinearGradient archive = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [
      Color(0xFF0A2540),
      Color(0xFF123A5C),
      Color(0xFF1B4D5C),
    ],
    stops: [0.0, 0.55, 1.0],
  );
}
