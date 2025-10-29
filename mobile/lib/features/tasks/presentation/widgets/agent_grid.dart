import 'package:flutter/material.dart';
import '../../../../shared/themes/app_colors.dart';
import '../../../../core/constants/app_constants.dart';

class AgentGrid extends StatelessWidget {
  const AgentGrid({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 20,
      runSpacing: 24,
      alignment: WrapAlignment.center,
      children: [
        _buildAgentCard(
          context: context,
          icon: Icons.description_outlined,
          label: AppConstants.agentLabels[AppConstants.agentDocs]!,
          color: AppColors.agentDocs,
          onTap: () => _handleAgentTap(context, AppConstants.agentDocs),
        ),
        _buildAgentCard(
          context: context,
          icon: Icons.table_chart_outlined,
          label: AppConstants.agentLabels[AppConstants.agentSheets]!,
          color: AppColors.agentSheets,
          onTap: () => _handleAgentTap(context, AppConstants.agentSheets),
        ),
        _buildAgentCard(
          context: context,
          icon: Icons.slideshow_outlined,
          label: AppConstants.agentLabels[AppConstants.agentSlides]!,
          color: AppColors.agentSlides,
          onTap: () => _handleAgentTap(context, AppConstants.agentSlides),
        ),
        _buildAgentCard(
          context: context,
          icon: Icons.search,
          label: AppConstants.agentLabels[AppConstants.agentResearch]!,
          color: AppColors.agentResearch,
          onTap: () => _handleAgentTap(context, AppConstants.agentResearch),
        ),
        _buildAgentCard(
          context: context,
          icon: Icons.code,
          label: AppConstants.agentLabels[AppConstants.agentCode]!,
          color: AppColors.agentCode,
          onTap: () => _handleAgentTap(context, AppConstants.agentCode),
        ),
        _buildAgentCard(
          context: context,
          icon: Icons.image_outlined,
          label: AppConstants.agentLabels[AppConstants.agentImage]!,
          color: AppColors.agentImage,
          onTap: () => _handleAgentTap(context, AppConstants.agentImage),
        ),
        _buildAgentCard(
          context: context,
          icon: Icons.videocam_outlined,
          label: AppConstants.agentLabels[AppConstants.agentVideo]!,
          color: AppColors.agentVideo,
          onTap: () => _handleAgentTap(context, AppConstants.agentVideo),
        ),
        _buildAgentCard(
          context: context,
          icon: Icons.audiotrack,
          label: AppConstants.agentLabels[AppConstants.agentAudio]!,
          color: AppColors.agentAudio,
          onTap: () => _handleAgentTap(context, AppConstants.agentAudio),
        ),
        _buildAgentCard(
          context: context,
          icon: Icons.analytics_outlined,
          label: AppConstants.agentLabels[AppConstants.agentData]!,
          color: AppColors.agentData,
          onTap: () => _handleAgentTap(context, AppConstants.agentData),
        ),
        _buildAgentCard(
          context: context,
          icon: Icons.chat_bubble_outline,
          label: AppConstants.agentLabels[AppConstants.agentChat]!,
          color: AppColors.agentChat,
          onTap: () => _handleAgentTap(context, AppConstants.agentChat),
        ),
        _buildAgentCard(
          context: context,
          icon: Icons.extension_outlined,
          label: AppConstants.agentLabels[AppConstants.agentCustom]!,
          color: AppColors.agentCustom,
          onTap: () => _handleAgentTap(context, AppConstants.agentCustom),
        ),
      ],
    );
  }

  Widget _buildAgentCard({
    required BuildContext context,
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          width: 90,
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Icon container
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: color.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: color.withOpacity(0.3),
                    width: 1,
                  ),
                ),
                child: Icon(
                  icon,
                  size: 32,
                  color: color,
                ),
              ),
              const SizedBox(height: 12),
              // Label
              Text(
                label,
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: AppColors.textPrimary,
                    ),
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _handleAgentTap(BuildContext context, String agentType) {
    // TODO: Navigate to agent-specific screen or show dialog
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '${AppConstants.agentLabels[agentType]} 선택됨',
        ),
        duration: const Duration(seconds: 1),
        backgroundColor: AppColors.backgroundCard,
      ),
    );
  }
}
