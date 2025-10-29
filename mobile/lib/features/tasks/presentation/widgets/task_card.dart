import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../../../shared/themes/app_colors.dart';
import '../../../../core/constants/app_constants.dart';
import 'task_status_chip.dart';

class TaskCard extends StatelessWidget {
  final String title;
  final String description;
  final String status;
  final String agentType;
  final DateTime createdAt;
  final VoidCallback onTap;
  final String? imageUrl;

  const TaskCard({
    Key? key,
    required this.title,
    required this.description,
    required this.status,
    required this.agentType,
    required this.createdAt,
    required this.onTap,
    this.imageUrl,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.backgroundCard,
      borderRadius: BorderRadius.circular(AppConstants.borderRadius),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppConstants.borderRadius),
        child: Container(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header row
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  // Agent type badge
                  _buildAgentBadge(context),
                  // Status chip
                  TaskStatusChip(status: status),
                ],
              ),
              const SizedBox(height: 12),
              // Title
              Text(
                title,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 8),
              // Description
              Text(
                description,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: AppColors.textSecondary,
                    ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              if (imageUrl != null) ...[
                const SizedBox(height: 12),
                // Preview image
                ClipRRect(
                  borderRadius: BorderRadius.circular(
                    AppConstants.borderRadiusSmall,
                  ),
                  child: Image.network(
                    imageUrl!,
                    height: 120,
                    width: double.infinity,
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) {
                      return Container(
                        height: 120,
                        color: AppColors.backgroundInput,
                        child: const Center(
                          child: Icon(
                            Icons.broken_image_outlined,
                            color: AppColors.textTertiary,
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ],
              const SizedBox(height: 12),
              // Footer row
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  // Timestamp
                  Text(
                    _formatDate(createdAt),
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: AppColors.textTertiary,
                        ),
                  ),
                  // AI Pods badge
                  _buildAIPodsBadge(context),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAgentBadge(BuildContext context) {
    final agentLabel = AppConstants.agentLabels[agentType] ?? agentType;
    final agentColor = _getAgentColor(agentType);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: agentColor.withOpacity(0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: agentColor.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            _getAgentIcon(agentType),
            size: 14,
            color: agentColor,
          ),
          const SizedBox(width: 6),
          Text(
            agentLabel,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: agentColor,
                  fontWeight: FontWeight.w600,
                ),
          ),
        ],
      ),
    );
  }

  Widget _buildAIPodsBadge(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: AppColors.backgroundInput,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: AppColors.border,
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(
            Icons.auto_awesome,
            size: 12,
            color: AppColors.primary,
          ),
          const SizedBox(width: 4),
          Text(
            'AI Pods',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: AppColors.textSecondary,
                  fontSize: 10,
                ),
          ),
        ],
      ),
    );
  }

  Color _getAgentColor(String agentType) {
    switch (agentType) {
      case AppConstants.agentDocs:
        return AppColors.agentDocs;
      case AppConstants.agentSheets:
        return AppColors.agentSheets;
      case AppConstants.agentSlides:
        return AppColors.agentSlides;
      case AppConstants.agentResearch:
        return AppColors.agentResearch;
      case AppConstants.agentCode:
        return AppColors.agentCode;
      case AppConstants.agentImage:
        return AppColors.agentImage;
      case AppConstants.agentVideo:
        return AppColors.agentVideo;
      case AppConstants.agentAudio:
        return AppColors.agentAudio;
      case AppConstants.agentData:
        return AppColors.agentData;
      case AppConstants.agentChat:
        return AppColors.agentChat;
      default:
        return AppColors.agentCustom;
    }
  }

  IconData _getAgentIcon(String agentType) {
    switch (agentType) {
      case AppConstants.agentDocs:
        return Icons.description_outlined;
      case AppConstants.agentSheets:
        return Icons.table_chart_outlined;
      case AppConstants.agentSlides:
        return Icons.slideshow_outlined;
      case AppConstants.agentResearch:
        return Icons.search;
      case AppConstants.agentCode:
        return Icons.code;
      case AppConstants.agentImage:
        return Icons.image_outlined;
      case AppConstants.agentVideo:
        return Icons.videocam_outlined;
      case AppConstants.agentAudio:
        return Icons.audiotrack;
      case AppConstants.agentData:
        return Icons.analytics_outlined;
      case AppConstants.agentChat:
        return Icons.chat_bubble_outline;
      default:
        return Icons.extension_outlined;
    }
  }

  String _formatDate(DateTime date) {
    final now = DateTime.now();
    final difference = now.difference(date);

    if (difference.inDays == 0) {
      if (difference.inHours == 0) {
        return '${difference.inMinutes}분 전';
      }
      return '${difference.inHours}시간 전';
    } else if (difference.inDays == 1) {
      return '어제';
    } else if (difference.inDays < 7) {
      return '${difference.inDays}일 전';
    } else {
      return DateFormat('MM/dd').format(date);
    }
  }
}
