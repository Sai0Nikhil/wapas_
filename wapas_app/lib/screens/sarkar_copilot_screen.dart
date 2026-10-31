import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/sarkar_models.dart';
import '../providers/app_providers.dart';
import '../services/voice_service.dart';
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

// ── Voice State ──────────────────────────────────────────────────────────────
enum VoiceState { idle, recording, transcribing, thinking, speaking }

class SarkarCopilotScreen extends ConsumerStatefulWidget {
  const SarkarCopilotScreen({super.key});

  @override
  ConsumerState<SarkarCopilotScreen> createState() => _SarkarCopilotScreenState();
}

class _SarkarCopilotScreenState extends ConsumerState<SarkarCopilotScreen>
    with TickerProviderStateMixin {
  final TextEditingController _msgCtrl = TextEditingController();
  final ScrollController _scrollCtrl = ScrollController();

  // Language
  String _selectedLang = 'en';
  final Map<String, String> _languages = {
    'en': 'English',
    'hi_en': 'Hinglish',
    'te': 'తెలుగు',
    'kn': 'ಕನ್ನಡ',
    'ta': 'தமிழ்',
    'hi': 'हिंदी',
  };

  // Voice
  final VoiceService _voice = VoiceService();
  VoiceState _voiceState = VoiceState.idle;
  bool _autoSpeak = true;

  // Animations
  late AnimationController _pulseCtrl;
  late Animation<double> _pulseAnim;

  late AnimationController _waveCtrl;
  late AnimationController _typingCtrl;

  // Messages
  late List<SarkarChatMessage> _messages;
  bool _isLoading = false;

  // Dynamic Suggestion Chips
  List<String> _currentChips = [
    'How is the store doing?',
    'Who owes Khata?',
    'Any low stock items?',
    'Today summary',
    'We received 10 kg of Atta',
  ];

  @override
  void initState() {
    super.initState();

    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 1.0, end: 1.25).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );

    _waveCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000))
      ..repeat();

    _typingCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))
      ..repeat();

    _messages = [_buildWelcome('en')];
  }

  @override
  void dispose() {
    _msgCtrl.dispose();
    _scrollCtrl.dispose();
    _pulseCtrl.dispose();
    _waveCtrl.dispose();
    _typingCtrl.dispose();
    _voice.dispose();
    super.dispose();
  }

  // ── Welcome Message ─────────────────────────────────────────────────────────

  SarkarChatMessage _buildWelcome(String lang) {
    final greetings = {
      'te': 'నమస్తే! నేను సర్కార్ AI — మీ స్టోర్ అటానమస్ కోపైలట్. అమ్మకాలు, ఖతా బాకీలు లేదా స్టాక్ గురించి ఏదైనా అడగండి.',
      'kn': 'ನಮಸ್ಕಾರ! ನಾನು ಸರ್ಕಾರ್ AI. ನಿಮ್ಮ ಅಂಗಡಿಯ ಮಾರಾಟ, ಖಾತಾ ಅಥವಾ ಸ್ಟಾಕ್ ಬಗ್ಗೆ ಕೇಳಿ.',
      'hi_en': 'Namaste! Main Sarkar AI hoon — aapka 24/7 Kirana Copilot. Dukan ke sales, Khata ya stock ke baare mein kuch bhi poochiye.',
      'ta': 'வணக்கம்! நான் சர்க்கார் AI. உங்கள் கடை விற்பனை மற்றும் கடன் கணக்கு பற்றி கேளுங்கள்.',
      'hi': 'नमस्ते! मैं सरकार AI हूँ — आपकी दुकान का डिजिटल साथी। आज की बिक्री, खाता या स्टॉक के बारे में पूछिए।',
      'en': 'Namaste! I\'m Sarkar AI, your Autonomous Kirana Copilot. Ask about today\'s sales, low stock alerts, pending Khata dues, or restock orders.',
    };
    return SarkarChatMessage(
      isUser: false,
      text: greetings[lang] ?? greetings['en']!,
      timestamp: DateTime.now(),
    );
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

  // ── Voice Interaction ────────────────────────────────────────────────────────

  Future<void> _onMicTap() async {
    if (_voiceState == VoiceState.speaking) {
      await _voice.stopSpeaking();
      setState(() => _voiceState = VoiceState.idle);
      return;
    }

    if (_voiceState == VoiceState.recording) {
      setState(() => _voiceState = VoiceState.transcribing);
      final path = await _voice.stopRecording();
      if (path == null || path.isEmpty) {
        setState(() => _voiceState = VoiceState.idle);
        return;
      }
      try {
        final transcript = await _voice.transcribeWithSarvam(
          path,
          langCode: VoiceService.toSarvamLang(_selectedLang),
        );
        if (transcript.isNotEmpty) {
          await _handleSend(transcript);
        } else {
          _showSnack('Could not capture audio. Please try again.');
          setState(() => _voiceState = VoiceState.idle);
        }
      } catch (e) {
        _showSnack('Sarvam STT: $e');
        setState(() => _voiceState = VoiceState.idle);
      }
    } else {
      try {
        await _voice.startRecording();
        setState(() => _voiceState = VoiceState.recording);
      } catch (e) {
        _showSnack('Microphone error: $e');
      }
    }
  }

  // ── Send Message ─────────────────────────────────────────────────────────────

  Future<void> _handleSend(String query) async {
    if (query.trim().isEmpty) return;
    final q = query.trim();
    _msgCtrl.clear();

    setState(() {
      _messages.add(SarkarChatMessage(isUser: true, text: q, timestamp: DateTime.now()));
      _isLoading = true;
      _voiceState = VoiceState.thinking;
    });
    _scrollToBottom();

    try {
      final res = await ref.read(sarkarRepoProvider).ask(q);
      if (!mounted) return;

      // Update chips dynamically based on response content
      _updateContextualChips(res);

      setState(() {
        _isLoading = false;
        _messages.add(SarkarChatMessage(
          isUser: false,
          text: res.message,
          timestamp: DateTime.now(),
          response: res,
        ));
        _voiceState = _autoSpeak ? VoiceState.speaking : VoiceState.idle;
      });
      _scrollToBottom();

      if (_autoSpeak) {
        await _voice.speakWithElevenLabs(res.message);
        if (mounted) setState(() => _voiceState = VoiceState.idle);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _voiceState = VoiceState.idle;
        _messages.add(SarkarChatMessage(
          isUser: false,
          text: 'Connection failed: ${e.toString()}',
          timestamp: DateTime.now(),
        ));
      });
      _scrollToBottom();
    }
  }

  void _updateContextualChips(SarkarAskResponse res) {
    final lower = res.message.toLowerCase();
    if (lower.contains('low stock') || lower.contains('stock') || lower.contains('running low')) {
      _currentChips = [
        'We received 10 kg of Atta',
        'Show full inventory',
        'Check unmet demand',
        'Today summary',
      ];
    } else if (lower.contains('khata') || lower.contains('dues') || lower.contains('owe')) {
      _currentChips = [
        'Send Khata reminders',
        'Who owes the most?',
        'Today summary',
        'Record payment',
      ];
    } else if (lower.contains('sales') || lower.contains('summary') || lower.contains('billed')) {
      _currentChips = [
        'Any pending Khata?',
        'Low stock items',
        'Inspect unmet demand',
        'Recent counter bills',
      ];
    } else {
      _currentChips = [
        'Today summary',
        'Who owes Khata?',
        'Low stock items',
        'We received 10 kg of Atta',
      ];
    }
  }

  // ── Confirm Mutating Actions ─────────────────────────────────────────────────

  Future<void> _confirmAction(SarkarChatMessage msg) async {
    final conf = msg.response?.confirmation;
    if (conf == null) return;
    setState(() => msg.isConfirming = true);
    try {
      await ref.read(sarkarRepoProvider).confirmAction(conf.actionId, conf.token);
      if (mounted) setState(() { msg.isConfirming = false; msg.isActionConfirmed = true; });
      _showSnack('Stock updated in inventory ✓', success: true);
    } catch (e) {
      if (mounted) setState(() => msg.isConfirming = false);
      _showSnack('Confirmation failed: $e');
    }
  }

  void _showSnack(String msg, {bool success = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: success ? AppColors.tertiary : AppColors.error,
      behavior: SnackBarBehavior.floating,
    ));
  }

  // ── Main Build ───────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF7F8FC),
      appBar: _buildAppBar(),
      body: Column(
        children: [
          _buildDynamicSuggestionsBar(),
          Expanded(child: _buildMessageList()),
          _buildLiveStatusIndicator(),
          _buildInputBar(),
        ],
      ),
    );
  }

  AppBar _buildAppBar() {
    return AppBar(
      elevation: 0.5,
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.white,
      title: Row(
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF6C63FF), Color(0xFF4FACFE)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(12),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF6C63FF).withValues(alpha: 0.25),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: const Icon(Icons.psychology_rounded, color: Colors.white, size: 22),
          ),
          const SizedBox(width: 10),
          Flexible(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    const Text('Sarkar AI', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E))),
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                      decoration: const BoxDecoration(
                        color: Color(0xFFE8F5E9),
                        borderRadius: BorderRadius.all(Radius.circular(4)),
                      ),
                      child: const Text('LIVE', style: TextStyle(fontSize: 9, fontWeight: FontWeight.bold, color: Colors.green)),
                    ),
                  ],
                ),
                const Text(
                  'Sarvam-105B • ElevenLabs Voice',
                  style: TextStyle(fontSize: 10, color: Color(0xFF777788)),
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
      actions: [
        IconButton(
          tooltip: _autoSpeak ? 'Voice Audio ON' : 'Voice Audio OFF',
          icon: Icon(
            _autoSpeak ? Icons.volume_up_rounded : Icons.volume_off_rounded,
            color: _autoSpeak ? const Color(0xFF6C63FF) : Colors.grey.shade400,
          ),
          onPressed: () => setState(() => _autoSpeak = !_autoSpeak),
        ),
        Container(
          margin: const EdgeInsets.only(right: 12, top: 10, bottom: 10),
          padding: const EdgeInsets.symmetric(horizontal: 10),
          decoration: BoxDecoration(
            color: const Color(0xFFF0EEFF),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: const Color(0xFF6C63FF).withValues(alpha: 0.2)),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: _selectedLang,
              icon: const Icon(Icons.keyboard_arrow_down_rounded, size: 16, color: Color(0xFF6C63FF)),
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Color(0xFF6C63FF)),
              dropdownColor: Colors.white,
              onChanged: (val) {
                if (val != null && val != _selectedLang) {
                  setState(() {
                    _selectedLang = val;
                    _messages.add(_buildWelcome(val));
                  });
                  _scrollToBottom();
                }
              },
              items: _languages.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value))).toList(),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDynamicSuggestionsBar() {
    return Container(
      height: 46,
      color: Colors.white,
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: _currentChips.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8), // ignore: unnecessary_underscores
        itemBuilder: (ctx, i) => ActionChip(
          label: Text(_currentChips[i], style: const TextStyle(fontSize: 11.5, color: Color(0xFF4A44A4), fontWeight: FontWeight.w500)),
          backgroundColor: const Color(0xFFF2F0FF),
          side: const BorderSide(color: Color(0xFFE4E0FF)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          onPressed: () => _handleSend(_currentChips[i]),
        ),
      ),
    );
  }

  Widget _buildMessageList() {
    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      itemCount: _messages.length + (_isLoading ? 1 : 0),
      itemBuilder: (ctx, i) {
        if (i == _messages.length && _isLoading) {
          return _buildThinkingBubble();
        }
        return _buildMessageRow(_messages[i]);
      },
    );
  }

  // ── Thinking Bubble with animated bouncing dots ──────────────────────────────

  Widget _buildThinkingBubble() {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 32,
            height: 32,
            margin: const EdgeInsets.only(right: 10, top: 4),
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: [Color(0xFF6C63FF), Color(0xFF4FACFE)]),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.psychology_rounded, color: Colors.white, size: 16),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18).copyWith(topLeft: Radius.zero),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.04),
                  blurRadius: 10,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: AnimatedBuilder(
              animation: _typingCtrl,
              builder: (ctx, child) {
                return Row(
                  mainAxisSize: MainAxisSize.min,
                  children: List.generate(3, (idx) {
                    final delay = idx * 0.2;
                    final val = (_typingCtrl.value - delay) % 1.0;
                    final jump = (val < 0.5 ? val * 2 : (1.0 - val) * 2) * -6.0;
                    return Transform.translate(
                      offset: Offset(0, jump),
                      child: Container(
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        width: 7,
                        height: 7,
                        decoration: const BoxDecoration(
                          color: Color(0xFF6C63FF),
                          shape: BoxShape.circle,
                        ),
                      ),
                    );
                  }),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  // ── Message Row ──────────────────────────────────────────────────────────────

  Widget _buildMessageRow(SarkarChatMessage msg) {
    if (msg.isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(bottom: 14, left: 60),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF6C63FF), Color(0xFF4FACFE)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(18).copyWith(bottomRight: Radius.zero),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF6C63FF).withValues(alpha: 0.22),
                blurRadius: 8,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          child: Text(
            msg.text,
            style: const TextStyle(color: Colors.white, fontSize: 14.5, height: 1.4),
          ),
        ),
      );
    }

    final res = msg.response;
    final traces = res?.toolTrace ?? [];

    return Container(
      margin: const EdgeInsets.only(bottom: 18),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 32,
            height: 32,
            margin: const EdgeInsets.only(right: 10, top: 4),
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: [Color(0xFF6C63FF), Color(0xFF4FACFE)]),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.psychology_rounded, color: Colors.white, size: 16),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Engine / Tool badge
                if (res != null) ...[
                  Container(
                    margin: const EdgeInsets.only(bottom: 6),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2.5),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEDE9FE),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.bolt_rounded, size: 12, color: Color(0xFF6C63FF)),
                        const SizedBox(width: 4),
                        Text(
                          traces.isNotEmpty ? 'TOOL: ${traces.first.tool}' : 'BRAIN: ${res.engine}',
                          style: const TextStyle(fontSize: 9.5, fontWeight: FontWeight.bold, color: Color(0xFF6C63FF)),
                        ),
                      ],
                    ),
                  ),
                ],

                // Bubble Container
                Container(
                  padding: const EdgeInsets.all(15),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(18).copyWith(topLeft: Radius.zero),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.04),
                        blurRadius: 10,
                        offset: const Offset(0, 3),
                      ),
                    ],
                    border: Border.all(color: const Color(0xFFE8E8F0)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        msg.text,
                        style: const TextStyle(fontSize: 14.5, color: Color(0xFF1A1A2E), height: 1.5),
                      ),

                      // Structured Visual Cards (Inventory / Khata / Summary)
                      if (res?.data != null && res!.data!.isNotEmpty) ...[
                        const SizedBox(height: 12),
                        _buildRichDataCard(res.data!),
                      ],

                      // Confirmation Card
                      if (res != null && res.needsConfirmation && !msg.isActionConfirmed && !msg.isActionCancelled) ...[
                        const SizedBox(height: 12),
                        _buildConfirmCard(msg),
                      ],

                      if (msg.isActionConfirmed) _buildStatusChip('Stock receipt confirmed ✓', Colors.green),
                      if (msg.isActionCancelled) _buildStatusChip('Action cancelled', Colors.grey),
                    ],
                  ),
                ),

                // Audio replay button
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: GestureDetector(
                    onTap: () => _voice.speakWithElevenLabs(msg.text),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: const Color(0xFFE0E0EB)),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.volume_up_rounded, size: 14, color: Color(0xFF6C63FF)),
                          SizedBox(width: 4),
                          Text('Listen with ElevenLabs', style: TextStyle(fontSize: 11, color: Color(0xFF6C63FF), fontWeight: FontWeight.w600)),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Rich Structured Data Cards ───────────────────────────────────────────────

  Widget _buildRichDataCard(Map<String, dynamic> data) {
    // 1. Low Stock Card
    if (data.containsKey('items') && data['items'] is List) {
      final items = data['items'] as List;
      if (items.isEmpty) return const SizedBox.shrink();
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFFFFF5F5),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFFFCDD2)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.warning_amber_rounded, color: Colors.red, size: 16),
                SizedBox(width: 6),
                Text('Critical Stock Items', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.red)),
              ],
            ),
            const SizedBox(height: 8),
            ...items.take(4).map((it) {
              final name = it['name'] ?? 'Product';
              final avail = it['available'] ?? 0;
              final unit = it['unit'] ?? 'units';
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    Expanded(child: Text(name, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600))),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(color: Colors.red.shade100, borderRadius: BorderRadius.circular(6)),
                      child: Text('$avail $unit left', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.red.shade800)),
                    ),
                    const SizedBox(width: 8),
                    InkWell(
                      onTap: () => _handleSend('We received 10 $unit of $name'),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: const Color(0xFF6C63FF),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: const Text('+ Restock', style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold)),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      );
    }

    // 2. Khata Accounts Card
    if (data.containsKey('accounts') && data['accounts'] is List) {
      final accounts = data['accounts'] as List;
      final totalPaise = data['outstanding_total_paise'] ?? 0;
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFFFFFBEA),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFFFE082)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Row(
                  children: [
                    Icon(Icons.menu_book_rounded, color: Color(0xFFB78103), size: 16),
                    SizedBox(width: 6),
                    Text('Khata Ledger Dues', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Color(0xFFB78103))),
                  ],
                ),
                Text('Total: ₹${(totalPaise / 100).toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.red)),
              ],
            ),
            const SizedBox(height: 8),
            ...accounts.take(3).map((acc) {
              final name = acc['name'] ?? 'Customer';
              final due = (acc['outstanding_paise'] ?? 0) / 100;
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(name, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500)),
                    Text('₹${due.toStringAsFixed(0)}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.red)),
                  ],
                ),
              );
            }),
          ],
        ),
      );
    }

    // 3. Business Summary KPI Card
    if (data.containsKey('counter_issued_total_paise')) {
      final sales = (data['counter_issued_total_paise'] ?? 0) / 100;
      final bills = data['counter_issued_count'] ?? 0;
      final paytm = (data['paytm_verified_total_paise'] ?? 0) / 100;
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          gradient: const LinearGradient(colors: [Color(0xFFF0F4FF), Color(0xFFE8EEFF)]),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFC5D4FF)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.analytics_rounded, color: Color(0xFF3366FF), size: 16),
                SizedBox(width: 6),
                Text('Today\'s Performance KPI', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Color(0xFF3366FF))),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                _kpiTile('Counter Sales', '₹${sales.toStringAsFixed(0)}', Colors.black87),
                _kpiTile('Paytm UPI', '₹${paytm.toStringAsFixed(0)}', Colors.green.shade700),
                _kpiTile('Orders Billed', '$bills', const Color(0xFF6C63FF)),
              ],
            ),
          ],
        ),
      );
    }

    // Default fallback
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: const Color(0xFFF5F5FF), borderRadius: BorderRadius.circular(10)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: data.entries.take(4).map((e) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${e.key}: ', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 11, color: Color(0xFF6C63FF))),
              Expanded(child: Text('${e.value}', style: const TextStyle(fontSize: 11, color: Color(0xFF444466)))),
            ],
          ),
        )).toList(),
      ),
    );
  }

  Widget _kpiTile(String label, String value, Color valColor) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 10, color: Colors.black54)),
          const SizedBox(height: 2),
          Text(value, style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: valColor)),
        ],
      ),
    );
  }

  Widget _buildConfirmCard(SarkarChatMessage msg) {
    final conf = msg.response!.confirmation!;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF9E6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFFFCC00), width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.warning_amber_rounded, color: Color(0xFF996600), size: 18),
              SizedBox(width: 6),
              Text('Owner Stock Confirmation Required',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Color(0xFF996600))),
            ],
          ),
          const SizedBox(height: 6),
          Text(conf.summary, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
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
                  child: const Text('Cancel', style: TextStyle(fontSize: 11)),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton(
                  onPressed: msg.isConfirming ? null : () => _confirmAction(msg),
                  style: ElevatedButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    backgroundColor: const Color(0xFF6C63FF),
                    foregroundColor: Colors.white,
                  ),
                  child: msg.isConfirming
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Text('Confirm', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildStatusChip(String text, Color color) {
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(text.contains('✓') ? Icons.check_circle : Icons.cancel, size: 14, color: color),
          const SizedBox(width: 6),
          Text(text, style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: color)),
        ],
      ),
    );
  }

  // ── Live Status Bar ──────────────────────────────────────────────────────────

  Widget _buildLiveStatusIndicator() {
    if (_voiceState == VoiceState.idle && !_isLoading) return const SizedBox.shrink();

    final Map<VoiceState, (String, Color, IconData)> config = {
      VoiceState.recording: ('Listening live... speak in ${_languages[_selectedLang]}', Colors.red, Icons.mic_rounded),
      VoiceState.transcribing: ('Sarvam Saaras transcribing voice...', const Color(0xFF6C63FF), Icons.transcribe_rounded),
      VoiceState.thinking: ('Sarvam-105B reasoning over store data...', const Color(0xFF4FACFE), Icons.psychology_rounded),
      VoiceState.speaking: ('ElevenLabs reading response... tap mic to stop', const Color(0xFF00C9A7), Icons.volume_up_rounded),
    };

    final entry = config[_voiceState];
    final label = _isLoading && _voiceState == VoiceState.idle ? 'Sarvam-105B reasoning over store data...' : (entry?.$1 ?? '');
    final color = _isLoading && _voiceState == VoiceState.idle ? const Color(0xFF4FACFE) : (entry?.$2 ?? Colors.grey);
    final icon = _isLoading && _voiceState == VoiceState.idle ? Icons.psychology_rounded : (entry?.$3 ?? Icons.info);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: color.withValues(alpha: 0.08),
      child: Row(
        children: [
          SizedBox(
            width: 14, height: 14,
            child: CircularProgressIndicator(strokeWidth: 2, color: color),
          ),
          const SizedBox(width: 10),
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 6),
          Expanded(child: Text(label, style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }

  // ── Input Bar with Gradient Animated Mic ─────────────────────────────────────

  Widget _buildInputBar() {
    final bool isRecording = _voiceState == VoiceState.recording;
    final bool isBusy = _voiceState == VoiceState.transcribing || _voiceState == VoiceState.thinking;

    return Container(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 16),
      decoration: const BoxDecoration(
        color: Colors.white,
        boxShadow: [BoxShadow(color: Color(0x10000000), blurRadius: 16, offset: Offset(0, -4))],
      ),
      child: SafeArea(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            // Mic button with pulse
            GestureDetector(
              onTap: isBusy ? null : _onMicTap,
              child: AnimatedBuilder(
                animation: _pulseAnim,
                builder: (ctx, child) {
                  final scale = isRecording ? _pulseAnim.value : 1.0;
                  return Transform.scale(
                    scale: scale,
                    child: Container(
                      width: 50,
                      height: 50,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: LinearGradient(
                          colors: isRecording
                              ? [Colors.red.shade400, Colors.red.shade700]
                              : _voiceState == VoiceState.speaking
                                  ? [const Color(0xFF00C9A7), const Color(0xFF009E88)]
                                  : [const Color(0xFF6C63FF), const Color(0xFF4FACFE)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: (isRecording ? Colors.red : const Color(0xFF6C63FF)).withValues(alpha: 0.35),
                            blurRadius: isRecording ? 20 : 10,
                            spreadRadius: isRecording ? 4 : 0,
                          ),
                        ],
                      ),
                      child: Icon(
                        isRecording
                            ? Icons.stop_rounded
                            : _voiceState == VoiceState.speaking
                                ? Icons.stop_circle_outlined
                                : Icons.mic_rounded,
                        color: Colors.white,
                        size: 24,
                      ),
                    ),
                  );
                },
              ),
            ),
            const SizedBox(width: 10),

            // Text input
            Expanded(
              child: Container(
                constraints: const BoxConstraints(maxHeight: 120),
                decoration: BoxDecoration(
                  color: const Color(0xFFF6F6FA),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(color: const Color(0xFFE2E2EC)),
                ),
                child: TextField(
                  controller: _msgCtrl,
                  maxLines: null,
                  textInputAction: TextInputAction.send,
                  decoration: InputDecoration(
                    hintText: isRecording
                        ? 'Listening in ${_languages[_selectedLang]}…'
                        : 'Ask Sarkar in ${_languages[_selectedLang]}…',
                    hintStyle: const TextStyle(fontSize: 13, color: Color(0xFFA0A0B0)),
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  ),
                  onSubmitted: (val) => _handleSend(val),
                ),
              ),
            ),
            const SizedBox(width: 8),

            // Send button
            GestureDetector(
              onTap: () => _handleSend(_msgCtrl.text),
              child: Container(
                width: 46,
                height: 46,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(
                    colors: [Color(0xFF6C63FF), Color(0xFF4FACFE)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                ),
                child: const Icon(Icons.send_rounded, color: Colors.white, size: 20),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
