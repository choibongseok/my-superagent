import 'package:flutter/material.dart';

/// Genspark-inspired dark theme color palette
class AppColors {
  // Dark Theme Base (Genspark style)
  static const backgroundDark = Color(0xFF0F0F0F);     // Main background
  static const backgroundCard = Color(0xFF1A1A1A);     // Card background
  static const backgroundInput = Color(0xFF1F1F1F);    // Input fields
  static const backgroundSidebar = Color(0xFF161616);  // Sidebar
  static const backgroundOverlay = Color(0xFF252525);  // Modal overlays

  // Primary Blue (Accent)
  static const primary = Color(0xFF3B82F6);            // Blue
  static const primaryHover = Color(0xFF2563EB);       // Darker blue
  static const primaryLight = Color(0xFF60A5FA);       // Lighter blue
  static const primaryDark = Color(0xFF1E40AF);        // Darkest blue

  // Text (Dark Theme)
  static const textPrimary = Color(0xFFE5E5E5);        // Light gray
  static const textSecondary = Color(0xFFA0A0A0);      // Medium gray
  static const textTertiary = Color(0xFF707070);       // Darker gray
  static const textDisabled = Color(0xFF4A4A4A);       // Disabled text

  // Borders & Dividers
  static const border = Color(0xFF2A2A2A);             // Default border
  static const borderFocus = Color(0xFF3B82F6);        // Focused input
  static const divider = Color(0xFF252525);            // Divider line

  // Status Colors
  static const success = Color(0xFF10B981);            // Green
  static const successLight = Color(0xFF34D399);
  static const warning = Color(0xFFF59E0B);            // Amber
  static const warningLight = Color(0xFFFBBF24);
  static const error = Color(0xFFEF4444);              // Red
  static const errorLight = Color(0xFFF87171);
  static const info = Color(0xFF3B82F6);               // Blue
  static const infoLight = Color(0xFF60A5FA);

  // Agent Colors (for 11 AI tools)
  static const agentDocs = Color(0xFF3B82F6);          // Blue
  static const agentSheets = Color(0xFF10B981);        // Green
  static const agentSlides = Color(0xFFF59E0B);        // Orange
  static const agentResearch = Color(0xFF8B5CF6);      // Purple
  static const agentCode = Color(0xFFEC4899);          // Pink
  static const agentImage = Color(0xFF14B8A6);         // Teal
  static const agentVideo = Color(0xFFEF4444);         // Red
  static const agentAudio = Color(0xFF06B6D4);         // Cyan
  static const agentData = Color(0xFF84CC16);          // Lime
  static const agentChat = Color(0xFF6366F1);          // Indigo
  static const agentCustom = Color(0xFFA855F7);        // Violet

  // Semantic Colors
  static const surface = backgroundCard;
  static const onSurface = textPrimary;
  static const onBackground = textPrimary;

  // Opacity variants
  static Color primaryWithOpacity(double opacity) =>
      primary.withOpacity(opacity);

  static Color textPrimaryWithOpacity(double opacity) =>
      textPrimary.withOpacity(opacity);

  static Color backgroundOverlayWithOpacity(double opacity) =>
      backgroundOverlay.withOpacity(opacity);
}
