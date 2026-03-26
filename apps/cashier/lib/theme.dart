
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'cashier_tokens.dart';

ThemeData cashierTheme() {
  final colorScheme = ColorScheme(
    brightness: Brightness.light,
    primary: CashierColors.primary,
    onPrimary: CashierColors.onPrimary,
    primaryContainer: CashierColors.primaryContainer,
    onPrimaryContainer: const Color(0xFFD6E3FF),
    secondary: const Color(0xFF735C00),
    onSecondary: Colors.white,
    secondaryContainer: CashierColors.secondaryContainer,
    onSecondaryContainer: CashierColors.onSecondaryContainer,
    tertiary: const Color(0xFF322400),
    onTertiary: Colors.white,
    tertiaryContainer: const Color(0xFF4D3900),
    onTertiaryContainer: const Color(0xFFD09F05),
    error: const Color(0xFFBA1A1A),
    onError: Colors.white,
    errorContainer: CashierColors.errorContainer,
    onErrorContainer: CashierColors.onErrorContainer,
    surface: CashierColors.surface,
    onSurface: CashierColors.onSurface,
    surfaceContainerHighest: CashierColors.surfaceContainerHigh,
    surfaceContainerHigh: CashierColors.surfaceContainerHigh,
    surfaceContainer: CashierColors.surfaceContainer,
    surfaceContainerLow: CashierColors.surfaceContainerLow,
    surfaceContainerLowest: CashierColors.card,
    onSurfaceVariant: CashierColors.onSurfaceVariant,
    outline: const Color(0xFF74777D),
    outlineVariant: CashierColors.outlineVariant,
    shadow: CashierColors.onSurface.withValues(alpha: 0.06),
    scrim: CashierColors.onSurface.withValues(alpha: 0.35),
    inverseSurface: const Color(0xFF30312E),
    onInverseSurface: const Color(0xFFF2F1EC),
    inversePrimary: const Color(0xFFADC7F7),
    surfaceTint: CashierColors.surfaceTint,
  );

  final base = ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: CashierColors.surface,
  );

  final manrope = GoogleFonts.manropeTextTheme(base.textTheme);
  const tabFeatures = [FontFeature.tabularFigures()];

  final textTheme = GoogleFonts.publicSansTextTheme(manrope).copyWith(
    headlineMedium: GoogleFonts.manrope(
      fontSize: 24,
      fontWeight: FontWeight.w600,
      color: CashierColors.onSurface,
      fontFeatures: tabFeatures,
    ),
    headlineSmall: GoogleFonts.manrope(
      fontSize: 20,
      fontWeight: FontWeight.w600,
      color: CashierColors.onSurface,
      fontFeatures: tabFeatures,
    ),
    titleLarge: GoogleFonts.manrope(
      fontSize: 18,
      fontWeight: FontWeight.w600,
      color: CashierColors.onSurface,
      fontFeatures: tabFeatures,
    ),
    titleMedium: GoogleFonts.manrope(
      fontSize: 16,
      fontWeight: FontWeight.w600,
      color: CashierColors.onSurface,
      fontFeatures: tabFeatures,
    ),
    labelLarge: GoogleFonts.publicSans(
      fontSize: 14,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.2,
      color: CashierColors.onSurface,
      fontFeatures: tabFeatures,
    ),
    labelMedium: GoogleFonts.publicSans(
      fontSize: 12,
      fontWeight: FontWeight.w500,
      color: CashierColors.onSurfaceVariant,
    ),
    labelSmall: GoogleFonts.publicSans(
      fontSize: 11,
      fontWeight: FontWeight.w500,
      letterSpacing: 0.4,
      color: CashierColors.onSurfaceVariant,
    ),
    bodyLarge: GoogleFonts.publicSans(
      fontSize: 16,
      fontWeight: FontWeight.w400,
      color: CashierColors.onSurface,
      height: 1.45,
    ),
    bodyMedium: GoogleFonts.publicSans(
      fontSize: 14,
      fontWeight: FontWeight.w400,
      color: CashierColors.onSurface,
      height: 1.45,
    ),
    bodySmall: GoogleFonts.publicSans(
      fontSize: 12,
      color: CashierColors.onSurfaceVariant,
      height: 1.4,
    ),
  );

  return base.copyWith(
    textTheme: textTheme,
    appBarTheme: AppBarTheme(
      backgroundColor: CashierColors.surface,
      foregroundColor: CashierColors.onSurface,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: textTheme.titleLarge,
    ),
    cardTheme: CardThemeData(
      color: CashierColors.card,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(CashierRadius.quickTile)),
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: CashierColors.surfaceContainerLow,
      indicatorColor: CashierColors.primary.withValues(alpha: 0.14),
      elevation: 3,
      shadowColor: CashierColors.onSurface.withValues(alpha: 0.06),
      height: 72,
      labelTextStyle: WidgetStateProperty.resolveWith((s) {
        final selected = s.contains(WidgetState.selected);
        return GoogleFonts.publicSans(
          fontSize: 12,
          fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
          color: selected ? CashierColors.primary : CashierColors.onSurfaceVariant,
        );
      }),
      iconTheme: WidgetStateProperty.resolveWith((s) {
        final selected = s.contains(WidgetState.selected);
        return IconThemeData(
          color: selected ? CashierColors.primary : CashierColors.onSurfaceVariant,
          size: 24,
        );
      }),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(CashierRadius.quickTile)),
        foregroundColor: CashierColors.onPrimary,
        textStyle: textTheme.labelLarge,
      ),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        padding: WidgetStateProperty.all(
          const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        ),
        shape: WidgetStateProperty.all(
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(CashierRadius.chip)),
        ),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: CashierColors.surfaceContainerLow,
      hintStyle: textTheme.bodyMedium?.copyWith(color: CashierColors.onSurfaceVariant),
      labelStyle: textTheme.labelMedium,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(CashierRadius.quickTile),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(CashierRadius.quickTile),
        borderSide: BorderSide(color: CashierColors.outlineVariant.withValues(alpha: 0.35)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(CashierRadius.quickTile),
        borderSide: const BorderSide(color: CashierColors.primary, width: 1.5),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: CashierSpacing.md, vertical: CashierSpacing.md),
    ),
    chipTheme: base.chipTheme.copyWith(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(CashierRadius.chip)),
      side: BorderSide.none,
    ),
  );
}
