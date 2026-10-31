import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../models/sound_models.dart';
import 'app_providers.dart';

class SoundboxState {
  final bool isRegistered;
  final String deviceKey;
  final int cursor;
  final List<SoundEventModel> events;
  final bool isMuted;
  final bool isSpeaking;
  final String? lastAnnouncedText;
  final String? errorMessage;

  SoundboxState({
    required this.isRegistered,
    required this.deviceKey,
    required this.cursor,
    this.events = const [],
    this.isMuted = false,
    this.isSpeaking = false,
    this.lastAnnouncedText,
    this.errorMessage,
  });

  SoundboxState copyWith({
    bool? isRegistered,
    String? deviceKey,
    int? cursor,
    List<SoundEventModel>? events,
    bool? isMuted,
    bool? isSpeaking,
    String? lastAnnouncedText,
    String? errorMessage,
  }) {
    return SoundboxState(
      isRegistered: isRegistered ?? this.isRegistered,
      deviceKey: deviceKey ?? this.deviceKey,
      cursor: cursor ?? this.cursor,
      events: events ?? this.events,
      isMuted: isMuted ?? this.isMuted,
      isSpeaking: isSpeaking ?? this.isSpeaking,
      lastAnnouncedText: lastAnnouncedText ?? this.lastAnnouncedText,
      errorMessage: errorMessage,
    );
  }
}

class SoundboxNotifier extends Notifier<SoundboxState> {
  static const String _prefDeviceKey = 'wapas_soundbox_device_key';
  FlutterTts? _tts;
  Timer? _pollTimer;
  final Set<int> _seenEventIds = {};

  @override
  SoundboxState build() {
    _initTts();
    Future.microtask(() => _initializeDevice());
    return SoundboxState(
      isRegistered: false,
      deviceKey: '',
      cursor: 0,
    );
  }

  void _initTts() {
    try {
      _tts = FlutterTts();
      _tts?.setLanguage('en-IN');
      _tts?.setPitch(1.0);
      _tts?.setSpeechRate(0.5);
      _tts?.setStartHandler(() {
        state = state.copyWith(isSpeaking: true);
      });
      _tts?.setCompletionHandler(() {
        state = state.copyWith(isSpeaking: false);
      });
      _tts?.setErrorHandler((_) {
        state = state.copyWith(isSpeaking: false);
      });
    } catch (e) {
      debugPrint('Soundbox TTS initialization failed: $e');
    }
  }

  Future<void> _initializeDevice() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      String? key = prefs.getString(_prefDeviceKey);
      if (key == null || key.isEmpty) {
        key = const Uuid().v4();
        await prefs.setString(_prefDeviceKey, key);
      }

      final soundRepo = ref.read(soundRepoProvider);
      final device = await soundRepo.registerDevice(key);

      state = state.copyWith(
        isRegistered: true,
        deviceKey: device.deviceKey,
        cursor: device.cursor,
        isMuted: device.soundDefault == 'MUTED',
      );

      startPolling();
    } catch (e) {
      state = state.copyWith(
        errorMessage: 'Device registration failed: $e',
      );
    }
  }

  void startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 4), (_) => pollEvents());
  }

  void stopPolling() {
    _pollTimer?.cancel();
  }

  Future<void> pollEvents() async {
    if (!state.isRegistered || state.deviceKey.isEmpty) return;

    try {
      final soundRepo = ref.read(soundRepoProvider);
      final newEvents = await soundRepo.getEvents(state.deviceKey);

      if (newEvents.isEmpty) return;

      final List<SoundEventModel> unhandled = [];
      for (final ev in newEvents) {
        if (!_seenEventIds.contains(ev.id) && ev.id > state.cursor) {
          unhandled.add(ev);
          _seenEventIds.add(ev.id);
        }
      }

      if (unhandled.isNotEmpty) {
        final updatedList = [...unhandled, ...state.events];
        state = state.copyWith(events: updatedList);

        for (final ev in unhandled) {
          await _announceEvent(ev);
          // Acknowledge event
          try {
            await soundRepo.acknowledgeEvent(state.deviceKey, ev.id);
            state = state.copyWith(cursor: ev.id);
          } catch (e) {
            debugPrint('Failed to acknowledge sound event ${ev.id}: $e');
          }
        }
      }
    } catch (e) {
      debugPrint('Soundbox poll error: $e');
    }
  }

  Future<void> _announceEvent(SoundEventModel ev) async {
    final amountStr = ev.amountInr.toStringAsFixed(0);
    final text = 'Paytm par $amountStr rupaye praapt hue';

    state = state.copyWith(lastAnnouncedText: text);

    if (!state.isMuted && _tts != null) {
      try {
        await _tts!.speak(text);
      } catch (e) {
        debugPrint('TTS speak error: $e');
      }
    }
  }

  Future<void> testBroadcast() async {
    const testText = 'Paytm par 245 rupaye praapt hue. Speaker test successful.';
    state = state.copyWith(lastAnnouncedText: testText);
    if (_tts != null) {
      await _tts!.speak(testText);
    }
  }

  void toggleMute() {
    state = state.copyWith(isMuted: !state.isMuted);
  }
}

final soundboxProvider = NotifierProvider<SoundboxNotifier, SoundboxState>(SoundboxNotifier.new);
