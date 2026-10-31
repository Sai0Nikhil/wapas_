import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/network/api_client.dart';
import '../models/auth_models.dart';
import '../repositories/auth_repo.dart';
import '../repositories/recovery_repo.dart';
import '../repositories/catalog_repo.dart';
import '../repositories/billing_repo.dart';
import '../repositories/khata_repo.dart';
import '../repositories/sarkar_repo.dart';
import '../repositories/sound_repo.dart';
import '../repositories/orders_repo.dart';
import '../repositories/agents_repo.dart';

// ApiClient Provider
final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient();
  client.init();
  return client;
});

// Repository Providers
final authRepoProvider = Provider<AuthRepo>((ref) {
  return HttpAuthRepo(ref.watch(apiClientProvider));
});

final recoveryRepoProvider = Provider<RecoveryRepo>((ref) {
  return HttpRecoveryRepo(ref.watch(apiClientProvider));
});

final catalogRepoProvider = Provider<CatalogRepo>((ref) {
  return HttpCatalogRepo(ref.watch(apiClientProvider));
});

final billingRepoProvider = Provider<BillingRepo>((ref) {
  return HttpBillingRepo(ref.watch(apiClientProvider));
});

final khataRepoProvider = Provider<KhataRepo>((ref) {
  return HttpKhataRepo(ref.watch(apiClientProvider));
});

final sarkarRepoProvider = Provider<SarkarRepo>((ref) {
  return HttpSarkarRepo(ref.watch(apiClientProvider));
});

final soundRepoProvider = Provider<SoundRepo>((ref) {
  return HttpSoundRepo(ref.watch(apiClientProvider));
});

final ordersRepoProvider = Provider<OrdersRepo>((ref) {
  return HttpOrdersRepo(ref.watch(apiClientProvider));
});

final agentsRepoProvider = Provider<AgentsRepo>((ref) {
  return HttpAgentsRepo(ref.watch(apiClientProvider));
});

// Auth State Notifier
class AuthState {
  final bool isLoading;
  final AuthSession session;
  final List<StoreMembership> memberships;
  final String? errorMessage;

  AuthState({
    this.isLoading = false,
    required this.session,
    this.memberships = const [],
    this.errorMessage,
  });

  bool get isAuthenticated => session.authenticated;
  bool get isOwner => session.role == UserRole.owner;

  AuthState copyWith({
    bool? isLoading,
    AuthSession? session,
    List<StoreMembership>? memberships,
    String? errorMessage,
  }) {
    return AuthState(
      isLoading: isLoading ?? this.isLoading,
      session: session ?? this.session,
      memberships: memberships ?? this.memberships,
      errorMessage: errorMessage,
    );
  }
}

class AuthNotifier extends Notifier<AuthState> {
  @override
  AuthState build() {
    final client = ref.watch(apiClientProvider);
    client.onSessionExpired = () {
      state = AuthState(
        session: AuthSession.unauthenticated(),
        errorMessage: 'Session expired. Please sign in again.',
      );
    };
    return AuthState(session: AuthSession.unauthenticated());
  }

  Future<void> checkSession() async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      final authRepo = ref.read(authRepoProvider);
      final session = await authRepo.getSession();
      if (session.authenticated) {
        final memberships = await authRepo.getMemberships();
        state = state.copyWith(
          isLoading: false,
          session: session,
          memberships: memberships,
        );
      } else {
        state = state.copyWith(
          isLoading: false,
          session: AuthSession.unauthenticated(),
        );
      }
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        session: AuthSession.unauthenticated(),
      );
    }
  }

  Future<bool> login(String username, String password, {String? membershipId}) async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      final authRepo = ref.read(authRepoProvider);
      final session = await authRepo.login(username, password, membershipId: membershipId);
      final memberships = await authRepo.getMemberships();
      state = state.copyWith(
        isLoading: false,
        session: session,
        memberships: memberships,
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: e.toString(),
      );
      return false;
    }
  }

  Future<bool> switchMembership(String membershipId) async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      final authRepo = ref.read(authRepoProvider);
      final session = await authRepo.switchMembership(membershipId);
      state = state.copyWith(
        isLoading: false,
        session: session,
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: e.toString(),
      );
      return false;
    }
  }

  Future<void> logout() async {
    state = state.copyWith(isLoading: true);
    try {
      final authRepo = ref.read(authRepoProvider);
      await authRepo.logout();
    } catch (_) {}
    state = AuthState(session: AuthSession.unauthenticated());
  }
}

final authNotifierProvider = NotifierProvider<AuthNotifier, AuthState>(AuthNotifier.new);

