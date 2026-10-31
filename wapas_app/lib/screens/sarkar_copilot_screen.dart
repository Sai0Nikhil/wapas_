import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

import '../models/sarkar_models.dart';
import '../providers/app_providers.dart';
import '../theme/app_theme.dart';

class SarkarChatMessage {
  final bool isUser;
  final String text;
  final DateTime timestamp;
  final SarkarAskResponse? response;
  bool isActionConfirmed;
  bool isActionCancelled;
  bool isConfirming;

  SarkarChatMessage({
    required this.isUser,
    required this.text,
    required this.timestamp,
    this.response,
    this.isActionConfirmed = false,
    this.isActionCancelled = false,
    this.isConfirming = false,
  });
}

class SarkarCopilotScreen extends ConsumerStatefulWidget {
  const SarkarCopilotScreen({super.key});

  @override
  ConsumerState<SarkarCopilotScreen> createState() => _SarkarCopilotScreenState();
}

class _SarkarCopilotScreenState extends ConsumerState<SarkarCopilotScreen> {
  final TextEditingController _msgCtrl = TextEditingController();
  final ScrollController _scrollCtrl = ScrollController();

  String _selectedLang = "en"; // "en", "hi_en", "te", "kn", "ta", "hi"

  final Map<String, String> _languages = {
    "en": "English",
    "hi_en": "Hinglish",
    "te": "తెలుగు (Telugu)",
    "kn": "ಕನ್ನಡ (Kannada)",
    "ta": "தமிழ் (Tamil)",
    "hi": "हिंदी (Hindi)",
  };

  final stt.SpeechToText _speech = stt.SpeechToText();
  bool _isListening = false;
  bool _speechAvailable = false;
  String _voiceBuffer = "";
  bool _isLoading = false;

  late List<SarkarChatMessage> _messages;

  @override
  void initState() {
    super.initState();
    _initSpeech();
    _messages = [
      _buildInitialWelcome("en"),
    ];
  }

  @override
  void dispose() {
    _msgCtrl.dispose();
    _scrollCtrl.dispose();
    _speech.stop();
    super.dispose();
  }

  Future<void> _initSpeech() async {
    try {
      _speechAvailable = await _speech.initialize(
        onError: (err) => debugPrint("STT error: $err"),
        onStatus: (status) {
          if (status == "notListening" || status == "done") {
            if (mounted && _isListening) {
              setState(() => _isListening = false);
              if (_voiceBuffer.trim().isNotEmpty) {
                _handleSend(_voiceBuffer.trim());
              }
            }
          }
        },
      );
      if (mounted) setState(() {});
    } catch (e) {
      debugPrint("STT init error: $e");
    }
  }

  SarkarChatMessage _buildInitialWelcome(String lang) {
    String greeting;
    switch (lang) {
      case "te":
        greeting = "నమస్తే! Wapas కోపైలట్‌కి స్వాగతం. మీ స్టోర్ సేల్స్, ఇన్వెంటరీ లేదా ఖాతా గురించి ఏదైనా అడగండి.";
        break;
      case "kn":
        greeting = "ನಮಸ್ಕಾರ! Wapas ಕೋಪೈಲಟ್‌ಗೆ ಸ್ವಾಗತ. ನಿಮ್ಮ ಅಂಗಡಿಯ ಮಾರಾಟ, ಖಾತಾ ಬಾಕಿ ಅಥವಾ ಸ್ಟಾಕ್ ಬಗ್ಗೆ ಕೇಳಿ.";
        break;
      case "hi_en":
        greeting = "Namaste! Main Wapas Retail Copilot hoon. Store turnover, stock ya Khata se judi koi bhi jaankari poochiye.";
        break;
      case "ta":
        greeting = "வணக்கம்! Wapas கோபிலட்டுக்கு வரவேற்கிறோம். உங்கள் கடை விற்பனை அல்லது கடன் கணக்கு பற்றி கேளுங்கள்.";
        break;
      case "hi":
        greeting = "नमस्ते! Wapas कोपायलट में आपका स्वागत है। आज दुकान के हिसाब, स्टॉक या खाते के बारे में पूछिए।";
        break;
      default:
        greeting = "Namaste! Welcome to Wapas Copilot. Ask about daily sales, low stock alerts, pending Khata dues, or restock receipts.";
        break;
    }

    return SarkarChatMessage(
      isUser: false,
      text: greeting,
      timestamp: DateTime.now(),
    );
  }

  void _onLanguageChanged(String newLang) {
    if (newLang == _selectedLang) return;
    setState(() {
      _selectedLang = newLang;
      _messages.add(_buildInitialWelcome(newLang));
    });
    _scrollToBottom();
  }

  void _scrollToBottom() {
    Future.delayed(const Duration(milliseconds: 150), () {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _toggleVoiceListening() async {
    if (!_speechAvailable) {
      await _initSpeech();
    }

    if (_isListening) {
      await _speech.stop();
      setState(() => _isListening = false);
      if (_voiceBuffer.trim().isNotEmpty) {
        _handleSend(_voiceBuffer.trim());
      }
    } else {
      _voiceBuffer = "";
      setState(() => _isListening = true);

      String localeId = "en_IN";
      if (_selectedLang == "te") localeId = "te_IN";
      if (_selectedLang == "kn") localeId = "kn_IN";
      if (_selectedLang == "ta") localeId = "ta_IN";
      if (_selectedLang == "hi" || _selectedLang == "hi_en") localeId = "hi_IN";

      try {
        await _speech.listen(
          listenOptions: stt.SpeechListenOptions(localeId: localeId),
          onResult: (result) {
            setState(() {
              _voiceBuffer = result.recognizedWords;
            });
            if (result.finalResult && _voiceBuffer.trim().isNotEmpty) {
              setState(() => _isListening = false);
              _handleSend(_voiceBuffer.trim());
            }
          },
        );
      } catch (e) {
        debugPrint("Error listening: $e");
        setState(() => _isListening = false);
      }
    }
  }

  Future<void> _handleSend(String query) async {
    if (query.trim().isEmpty) return;

    final userQuery = query.trim();
    _msgCtrl.clear();

    setState(() {
      _messages.add(SarkarChatMessage(
        isUser: true,
        text: userQuery,
        timestamp: DateTime.now(),
      ));
      _isLoading = true;
    });
    _scrollToBottom();

    // POST /api/merchant/sarkar/ask
    final sarkarRepo = ref.read(sarkarRepoProvider);
    try {
      final res = await sarkarRepo.ask(userQuery);
      if (mounted) {
        setState(() {
          _isLoading = false;
          _messages.add(SarkarChatMessage(
            isUser: false,
            text: res.message,
            timestamp: DateTime.now(),
            response: res,
          ));
        });
        _scrollToBottom();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _messages.add(SarkarChatMessage(
            isUser: false,
            text: "Request failed: ${e.toString()}",
            timestamp: DateTime.now(),
          ));
        });
        _scrollToBottom();
      }
    }
  }

  Future<void> _confirmAction(SarkarChatMessage msg) async {
    final conf = msg.response?.confirmation;
    if (conf == null) return;

    setState(() => msg.isConfirming = true);
    final sarkarRepo = ref.read(sarkarRepoProvider);

    try {
      await sarkarRepo.confirmAction(conf.actionId, conf.token);
      if (mounted) {
        setState(() {
          msg.isConfirming = false;
          msg.isActionConfirmed = true;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text("Action confirmed and executed successfully"),
            backgroundColor: AppColors.tertiary,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => msg.isConfirming = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text("Confirmation failed: $e"),
            backgroundColor: AppColors.error,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        backgroundColor: AppColors.surfaceLowest,
        elevation: 0.5,
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: AppColors.primaryContainer,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(Icons.psychology, color: Colors.white, size: 20),
            ),
            const SizedBox(width: 8),
            const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  "Sarkar AI Copilot",
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
                Text(
                  "Deterministic Typed Router • Sarvam Indic",
                  style: TextStyle(fontSize: 10, color: AppColors.outline),
                ),
              ],
            ),
          ],
        ),
        actions: [
          // Language selector
          Container(
            margin: const EdgeInsets.only(right: 8, top: 8, bottom: 8),
            padding: const EdgeInsets.symmetric(horizontal: 8),
            decoration: BoxDecoration(
              color: AppColors.surfaceLow,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: AppColors.outline.withValues(alpha: 0.2)),
            ),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<String>(
                value: _selectedLang,
                icon: const Icon(Icons.keyboard_arrow_down, size: 16, color: AppColors.secondary),
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.secondary),
                onChanged: (val) {
                  if (val != null) _onLanguageChanged(val);
                },
                items: _languages.entries.map((entry) {
                  return DropdownMenuItem<String>(
                    value: entry.key,
                    child: Text(entry.value),
                  );
                }).toList(),
              ),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          // Suggestions Bar
          _buildQuickSuggestionsBar(),

          // Chat Messages List
          Expanded(
            child: ListView.builder(
              controller: _scrollCtrl,
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length,
              itemBuilder: (context, idx) {
                return _buildMessageBubble(_messages[idx]);
              },
            ),
          ),

          if (_isLoading)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              alignment: Alignment.centerLeft,
              child: const Row(
                children: [
                  SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.secondary),
                  ),
                  SizedBox(width: 8),
                  Text("Sarkar router thinking...", style: TextStyle(fontSize: 12, color: AppColors.outline)),
                ],
              ),
            ),

          // Voice / Text Input Box
          _buildInputBox(),
        ],
      ),
    );
  }

  Widget _buildQuickSuggestionsBar() {
    final chips = [
      "Summary today",
      "Who owes Khata?",
      "Low stock items",
      "We received 10 kg of Atta",
      "Inspect unmet demand",
    ];

    return Container(
      height: 42,
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: chips.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (ctx, i) {
          return ActionChip(
            label: Text(chips[i], style: const TextStyle(fontSize: 11, color: AppColors.onSurface)),
            backgroundColor: AppColors.surfaceLowest,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: BorderSide(color: AppColors.outlineVariant.withValues(alpha: 0.4)),
            ),
            onPressed: () => _handleSend(chips[i]),
          );
        },
      ),
    );
  }

  Widget _buildMessageBubble(SarkarChatMessage msg) {
    if (msg.isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(bottom: 12, left: 48),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: AppColors.primary,
            borderRadius: BorderRadius.circular(16).copyWith(bottomRight: Radius.zero),
          ),
          child: Text(
            msg.text,
            style: const TextStyle(color: Colors.white, fontSize: 14),
          ),
        ),
      );
    }

    final res = msg.response;
    final traces = res?.toolTrace ?? [];

    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 16, right: 40),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Provider / Engine Trace Chip
            if (res != null) ...[
              Container(
                margin: const EdgeInsets.only(bottom: 4),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.surfaceLow,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: AppColors.secondary.withValues(alpha: 0.2)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.bolt, size: 12, color: AppColors.secondary),
                    const SizedBox(width: 4),
                    Text(
                      traces.isNotEmpty
                          ? "TOOL: ${traces.first.tool} (v${traces.first.version}) • ${res.engine}"
                          : "ROUTER: ${res.engine}",
                      style: const TextStyle(fontSize: 9, fontWeight: FontWeight.bold, color: AppColors.secondary),
                    ),
                    if (res.input?.latencyMs != null && res.input!.latencyMs > 0)
                      Text(" • ${res.input!.latencyMs}ms", style: const TextStyle(fontSize: 9, color: AppColors.outline)),
                  ],
                ),
              ),
            ],

            // Message Body Container
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AppColors.surfaceLowest,
                borderRadius: BorderRadius.circular(16).copyWith(topLeft: Radius.zero),
                border: Border.all(color: AppColors.outlineVariant.withValues(alpha: 0.3)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.03),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    msg.text,
                    style: const TextStyle(fontSize: 14, color: AppColors.onSurface, height: 1.4),
                  ),

                  // Structured Data Preview if available
                  if (res?.data != null && res!.data!.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    _buildStructuredDataView(res.data!),
                  ],

                  // Confirmation Card for Mutating Actions
                  if (res != null && res.needsConfirmation && !msg.isActionConfirmed && !msg.isActionCancelled) ...[
                    const SizedBox(height: 12),
                    _buildConfirmationCard(msg),
                  ],

                  if (msg.isActionConfirmed) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: Colors.green.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Row(
                        children: [
                          Icon(Icons.check_circle, size: 16, color: Colors.green),
                          SizedBox(width: 6),
                          Text("Action Confirmed and Executed in Ledger/Stock",
                              style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.green)),
                        ],
                      ),
                    ),
                  ],

                  if (msg.isActionCancelled) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: Colors.grey.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Row(
                        children: [
                          Icon(Icons.cancel, size: 16, color: Colors.grey),
                          SizedBox(width: 6),
                          Text("Action Cancelled by Owner",
                              style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.grey)),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStructuredDataView(Map<String, dynamic> data) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.surfaceLow,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: data.entries.take(4).map((e) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text("${e.key}: ", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 11)),
                Expanded(
                  child: Text("${e.value}", style: const TextStyle(fontSize: 11, color: AppColors.onSurfaceVariant)),
                ),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildConfirmationCard(SarkarChatMessage msg) {
    final conf = msg.response!.confirmation!;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF9E6),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFFFCC00), width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.warning_amber_rounded, color: Color(0xFF996600), size: 18),
              const SizedBox(width: 6),
              const Expanded(
                child: Text(
                  "Owner Confirmation Required",
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Color(0xFF996600)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(conf.summary, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.onSurface)),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: msg.isConfirming ? null : () => setState(() => msg.isActionCancelled = true),
                  style: OutlinedButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    side: const BorderSide(color: Colors.grey),
                  ),
                  child: const Text("Cancel", style: TextStyle(color: Colors.black87, fontSize: 11)),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton(
                  onPressed: msg.isConfirming ? null : () => _confirmAction(msg),
                  style: ElevatedButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    backgroundColor: AppColors.secondary,
                    foregroundColor: Colors.white,
                  ),
                  child: msg.isConfirming
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Text("Confirm Action", style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildInputBox() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.surfaceLowest,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        child: Row(
          children: [
            // Microphone Button
            Container(
              decoration: BoxDecoration(
                color: _isListening ? Colors.red.shade50 : AppColors.surfaceLow,
                shape: BoxShape.circle,
              ),
              child: IconButton(
                icon: Icon(
                  _isListening ? Icons.mic : Icons.mic_none,
                  color: _isListening ? Colors.red : AppColors.secondary,
                ),
                onPressed: _toggleVoiceListening,
              ),
            ),
            const SizedBox(width: 8),

            // Input field
            Expanded(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14),
                decoration: BoxDecoration(
                  color: AppColors.surfaceLow,
                  borderRadius: BorderRadius.circular(24),
                ),
                child: TextField(
                  controller: _msgCtrl,
                  decoration: InputDecoration(
                    hintText: _isListening ? "Listening in ${_languages[_selectedLang]}..." : "Ask Sarkar in ${_languages[_selectedLang]}...",
                    border: InputBorder.none,
                    hintStyle: const TextStyle(fontSize: 13, color: AppColors.outline),
                  ),
                  onSubmitted: (val) => _handleSend(val),
                ),
              ),
            ),
            const SizedBox(width: 8),

            // Send Button
            CircleAvatar(
              backgroundColor: AppColors.primary,
              radius: 20,
              child: IconButton(
                icon: const Icon(Icons.send, color: Colors.white, size: 16),
                onPressed: () => _handleSend(_msgCtrl.text),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
