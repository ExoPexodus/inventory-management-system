import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'admin_tokens.dart';

ThemeData adminTheme() {
  final colorScheme = ColorScheme(
    brightness: Brightness.light,
    primary: AdminColors.primary,
    onPrimary: AdminColors.onPrimary,
    primaryContainer: AdminColors.primaryContainer,
    onPrimaryContainer: const Color(0xFFD6E3FF),
    secondary: const Color(0xFF735C00),
    onSecondary: Colors.white,
    secondaryContainer: AdminColors.secondaryContainer,
    onSecondaryContainer: AdminColors.onSecondaryContainer,
    tertiary: const Color(0xFF322400),
    onTertiary: Colors.white,
    tertiaryContainer: const Color(0xFF4D3900),
    onTertiaryContainer: const Color(0xFFD09F05),
    error: const Color(0xFFBA1A1A),
    onError: Colors.white,
    errorContainer: AdminColors.errorContainer,
    onErrorContainer: AdminColors.onErrorContainer,
    surface: AdminColors.surface,
    onSurface: AdminColors.onSurface,
    surfaceContainerHighest: AdminColors.surfaceContainerHigh,
    surfaceContainerHigh: AdminColors.surfaceContainerHigh,
    surfaceContainer: AdminColors.surfaceContainer,
    surfaceContainerLow: AdminColors.surfaceContainerLow,
    surfaceContainerLowest: AdminColors.card,
    onSurfaceVariant: AdminColors.onSurfaceVariant,
    outline: const Color(0xFF74777D),
    outlineVariant: AdminColors.outlineVariant,
    shadow: AdminColors.onSurface.withValues(alpha: 0.06),
    scrim: AdminColors.onSurface.withValues(alpha: 0.35),
    inverseSurface: const Color(0xFF30312E),
    onInverseSurface: const Color(0xFFF2F1EC),
    inversePrimary: const Color(0xFFADC7F7),
    surfaceTint: AdminColors.surfaceTint,
  );

  final base = ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: AdminColors.surface,
  );

  final manrope = GoogleFonts.manropeTextTheme(base.textTheme);
  const tabFeatures = [FontFeature.tabularFigures()];

  final textTheme = GoogleFonts.publicSansTextTheme(manrope).copyWith(
    headlineMedium: GoogleFonts.manrope(
      fontSize: 24,
      fontWeight: FontWeight.w600,
      color: AdminColors.onSurface,
      fontFeatures: tabFeatures,
    ),
    headlineSmall: GoogleFonts.manrope(
      fontSize: 20,
      fontWeight: FontWeight.w600,
      color: AdminColors.onSurface,
      fontFeatures: tabFeatures,
    ),
    titleLarge: GoogleFonts.manrope(
      fontSize: 18,
      fontWeight: FontWeight.w600,
      color: AdminColors.onSurface,
      fontFeatures: tabFeatures,
    ),
    titleMedium: GoogleFonts.manrope(
      fontSize: 16,
      fontWeight: FontWeight.w600,
      color: AdminColors.onSurface,
      fontFeatures: tabFeatures,
    ),
    labelLarge: GoogleFonts.publicSans(
      fontSize: 14,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.2,
      color: AdminColors.onSurface,
      fontFeatures: tabFeatures,
    ),
    labelMedium: GoogleFonts.publicSans(
      fontSize: 12,
      fontWeight: FontWeight.w500,
      color: AdminColors.onSurfaceVariant,
    ),
    labelSmall: GoogleFonts.publicSans(
      fontSize: 11,
      fontWeight: FontWeight.w500,
      letterSpacing: 0.4,
      color: AdminColors.onSurfaceVariant,
    ),
    bodyLarge: GoogleFonts.publicSans(
      fontSize: 16,
      fontWeight: FontWeight.w400,
      color: AdminColors.onSurface,
      height: 1.45,
    ),
    bodyMedium: GoogleFonts.publicSans(
      fontSize: 14,
      fontWeight: FontWeight.w400,
      color: AdminColors.onSurface,
      height: 1.45,
    ),
    bodySmall: GoogleFonts.publicSans(
      fontSize: 12,
      color: AdminColors.onSurfaceVariant,
      height: 1.4,
    ),
  );

  return base.copyWith(
    textTheme: textTheme,
    appBarTheme: AppBarTheme(
      backgroundColor: AdminColors.surface,
      foregroundColor: AdminColors.onSurface,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: textTheme.titleLarge,
    ),
    cardTheme: CardThemeData(
      color: AdminColors.card,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AdminRadius.quickTile)),
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AdminColors.surfaceContainerLow,
      indicatorColor: AdminColors.primary.withValues(alpha: 0.14),
      elevation: 3,
      shadowColor: AdminColors.onSurface.withValues(alpha: 0.06),
      height: 72,
      labelTextStyle: WidgetStateProperty.resolveWith((s) {
        final selected = s.contains(WidgetState.selected);
        return GoogleFonts.publicSans(
          fontSize: 12,
          fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
          color: selected ? AdminColors.primary : AdminColors.onSurfaceVariant,
        );
      }),
      iconTheme: WidgetStateProperty.resolveWith((s) {
        final selected = s.contains(WidgetState.selected);
        return IconThemeData(
          color: selected ? AdminColors.primary : AdminColors.onSurfaceVariant,
          size: 24,
        );
      }),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AdminRadius.quickTile)),
        foregroundColor: AdminColors.onPrimary,
        textStyle: textTheme.labelLarge,
      ),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        padding: WidgetStateProperty.all(
          const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        ),
        shape: WidgetStateProperty.all(
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(AdminRadius.chip)),
        ),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AdminColors.surfaceContainerLow,
      hintStyle: textTheme.bodyMedium?.copyWith(color: AdminColors.onSurfaceVariant),
      labelStyle: textTheme.labelMedium,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AdminRadius.quickTile),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AdminRadius.quickTile),
        borderSide: BorderSide(color: AdminColors.outlineVariant.withValues(alpha: 0.35)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AdminRadius.quickTile),
        borderSide: const BorderSide(color: AdminColors.primary, width: 1.5),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: AdminSpacing.md, vertical: AdminSpacing.md),
    ),
    chipTheme: base.chipTheme.copyWith(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AdminRadius.chip)),
      side: BorderSide.none,
    ),
  );
}
