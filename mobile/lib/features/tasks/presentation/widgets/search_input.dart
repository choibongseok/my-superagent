import 'package:flutter/material.dart';
import '../../../../shared/themes/app_colors.dart';
import '../../../../core/constants/app_constants.dart';

class SearchInput extends StatefulWidget {
  const SearchInput({Key? key}) : super(key: key);

  @override
  State<SearchInput> createState() => _SearchInputState();
}

class _SearchInputState extends State<SearchInput> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  bool _isFocused = false;

  @override
  void initState() {
    super.initState();
    _focusNode.addListener(() {
      setState(() {
        _isFocused = _focusNode.hasFocus;
      });
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.backgroundInput,
        borderRadius: BorderRadius.circular(AppConstants.borderRadiusLarge),
        border: Border.all(
          color: _isFocused ? AppColors.primary : AppColors.border,
          width: 1.5,
        ),
      ),
      child: Column(
        children: [
          // Text input
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
            child: TextField(
              controller: _controller,
              focusNode: _focusNode,
              maxLines: null,
              style: Theme.of(context).textTheme.bodyLarge,
              decoration: InputDecoration(
                hintText: '무엇이든 질문하고 만들어보세요',
                hintStyle: Theme.of(context).textTheme.bodyLarge?.copyWith(
                      color: AppColors.textSecondary,
                    ),
                border: InputBorder.none,
                isDense: true,
                contentPadding: EdgeInsets.zero,
              ),
            ),
          ),
          // Bottom action bar
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 12,
            ),
            decoration: const BoxDecoration(
              border: Border(
                top: BorderSide(
                  color: AppColors.border,
                  width: 1,
                ),
              ),
            ),
            child: Row(
              children: [
                // Left actions
                _buildActionButton(
                  icon: Icons.chat_bubble_outline,
                  tooltip: '대화',
                  onPressed: () {},
                ),
                const SizedBox(width: 8),
                _buildActionButton(
                  icon: Icons.text_fields,
                  tooltip: '글꼴',
                  onPressed: () {},
                ),
                const SizedBox(width: 8),
                _buildActionButton(
                  icon: Icons.attach_file,
                  tooltip: '첨부',
                  onPressed: () {},
                ),
                const SizedBox(width: 8),
                _buildActionButton(
                  icon: Icons.mic_none,
                  tooltip: '음성',
                  onPressed: () {},
                ),
                const SizedBox(width: 8),
                _buildActionButton(
                  icon: Icons.image_outlined,
                  tooltip: '이미지',
                  onPressed: () {},
                ),
                const Spacer(),
                // Send button
                _buildSendButton(),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionButton({
    required IconData icon,
    required String tooltip,
    required VoidCallback onPressed,
  }) {
    return IconButton(
      onPressed: onPressed,
      icon: Icon(icon),
      iconSize: 20,
      color: AppColors.textSecondary,
      tooltip: tooltip,
      padding: const EdgeInsets.all(8),
      constraints: const BoxConstraints(
        minWidth: 36,
        minHeight: 36,
      ),
    );
  }

  Widget _buildSendButton() {
    final hasText = _controller.text.isNotEmpty;

    return AnimatedContainer(
      duration: AppConstants.animationDurationFast,
      child: Material(
        color: hasText ? AppColors.primary : AppColors.backgroundCard,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          onTap: hasText ? _handleSend : null,
          borderRadius: BorderRadius.circular(8),
          child: Container(
            padding: const EdgeInsets.all(8),
            child: Icon(
              Icons.send,
              size: 20,
              color: hasText ? Colors.white : AppColors.textTertiary,
            ),
          ),
        ),
      ),
    );
  }

  void _handleSend() {
    if (_controller.text.isEmpty) return;

    // TODO: Handle send action
    print('Sending: ${_controller.text}');
    _controller.clear();
  }
}
