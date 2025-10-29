import 'package:flutter/material.dart';
import '../../../../shared/themes/app_colors.dart';
import '../../../../core/constants/app_constants.dart';

class TaskStatusChip extends StatelessWidget {
  final String status;

  const TaskStatusChip({
    Key? key,
    required this.status,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final statusConfig = _getStatusConfig(status);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: statusConfig.color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: statusConfig.color.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            statusConfig.icon,
            size: 14,
            color: statusConfig.color,
          ),
          const SizedBox(width: 6),
          Text(
            statusConfig.label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: statusConfig.color,
                  fontWeight: FontWeight.w600,
                ),
          ),
        ],
      ),
    );
  }

  _StatusConfig _getStatusConfig(String status) {
    switch (status) {
      case AppConstants.taskStatusCompleted:
        return _StatusConfig(
          label: AppConstants.taskStatusLabels[status]!,
          color: AppColors.success,
          icon: Icons.check_circle,
        );
      case AppConstants.taskStatusInProgress:
        return _StatusConfig(
          label: AppConstants.taskStatusLabels[status]!,
          color: AppColors.info,
          icon: Icons.cached,
        );
      case AppConstants.taskStatusFailed:
        return _StatusConfig(
          label: AppConstants.taskStatusLabels[status]!,
          color: AppColors.error,
          icon: Icons.error,
        );
      case AppConstants.taskStatusPending:
      default:
        return _StatusConfig(
          label: AppConstants.taskStatusLabels[status]!,
          color: AppColors.warning,
          icon: Icons.schedule,
        );
    }
  }
}

class _StatusConfig {
  final String label;
  final Color color;
  final IconData icon;

  _StatusConfig({
    required this.label,
    required this.color,
    required this.icon,
  });
}
