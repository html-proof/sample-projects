import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:just_audio/just_audio.dart';
import 'package:just_audio_background/just_audio_background.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:rxdart/rxdart.dart';
import 'package:audio_session/audio_session.dart';
import '../models/song.dart';
import '../models/position_data.dart';
import 'api_service.dart';
import 'cache_service.dart';

class PlayerService with ChangeNotifier {
  final AudioPlayer _player = AudioPlayer();
  final ApiService _apiService = ApiService();
  final SharedPreferences? _prefs;

  List<Song> _queue = [];
  List<Song> _originalQueue = [];
  int _currentIndex = 0;
  bool _isHeadsetConnected = false;
  final Map<String, int> _retryCounts = {};
  int _playSessionId = 0; 
  bool _isDisposed = false;
  bool _isPlayerStopping = false; // Serialize state transitions
  
  AudioPlayer get player => _player;
  bool get isHeadsetConnected => _isHeadsetConnected;
  int get currentIndex => _currentIndex;
  List<Song> get queue => _queue;
  
  Song? get currentSong {
    if (_currentIndex >= 0 && _currentIndex < _queue.length) {
      return _queue[_currentIndex];
    }
    return null;
  }

  PlayerService([this._prefs]) {
    _init();
  }

  Future<void> _init() async {
    // Handle player state changes
    _player.playerStateStream.listen((state) {
      if (state.processingState == ProcessingState.completed) {
        if (_player.loopMode == LoopMode.one) {
          _player.seek(Duration.zero);
          _player.play();
        } else {
          next(); // Auto-advance
        }
      }
      
      if (state.processingState == ProcessingState.idle && _player.playing) {
          _handlePlaybackError(PlayerException(0, 'Player entered idle state unexpectedly'));
      }
      notifyListeners();
    });

    _player.positionStream.listen((pos) {
       if (pos.inSeconds % 10 == 0) _saveState();
    });

    // Error handling
    _player.playbackEventStream.listen((event) {}, onError: (Object e, StackTrace stackTrace) {
      if (_isDisposed) return;
      if (e is PlayerException) {
        _handlePlaybackError(e);
      } else {
        debugPrint('Non-player error: $e');
        _handlePlaybackError(PlayerException(0, e.toString()));
      }
    });

    try {
      final session = await AudioSession.instance;
      await session.configure(const AudioSessionConfiguration.music());
      
      void checkDevices(Iterable<AudioDevice> devices) {
        final hasHeadset = devices.any((d) => 
          d.type == AudioDeviceType.wiredHeadset || 
          d.type == AudioDeviceType.wiredHeadphones ||
          d.type == AudioDeviceType.bluetoothA2dp ||
          d.type == AudioDeviceType.bluetoothSco
        );
        if (_isHeadsetConnected != hasHeadset) {
          _isHeadsetConnected = hasHeadset;
          notifyListeners();
        }
      }

      final devices = await session.getDevices();
      checkDevices(devices);

      session.devicesChangedEventStream.listen((event) async {
        final currentDevices = await session.getDevices();
        checkDevices(currentDevices);
      });
    } catch (e) {
      debugPrint('Error init audio session devices: $e');
    }

    _loadState();
  }

  Stream<PositionData> get positionDataStream =>
      Rx.combineLatest3<Duration, Duration, Duration?, PositionData>(
          _player.positionStream,
          _player.bufferedPositionStream,
          _player.durationStream,
          (position, bufferedPosition, duration) =>
              PositionData(position, bufferedPosition, duration ?? Duration.zero));

  Future<void> playSong(Song song) async {
    await playQueue([song]);
  }

  Future<void> playQueue(List<Song> songs, {int initialIndex = 0}) async {
    if (songs.isEmpty) return;
    
    _originalQueue = List.from(songs);
    _queue = List.from(songs);
    
    // Honor shuffle mode immediately if enabled
    if (_player.shuffleModeEnabled) {
      final selectedSong = _queue[initialIndex];
      _queue.shuffle();
      // Move selected song to front (standard Spotify behavior)
      _queue.remove(selectedSong);
      _queue.insert(0, selectedSong);
      _currentIndex = 0;
    } else {
      _currentIndex = (initialIndex >= 0 && initialIndex < _queue.length) ? initialIndex : 0;
    }
    
    debugPrint("Setting new queue: ${songs.length} tracks. Shuffle: ${_player.shuffleModeEnabled}");
    _retryCounts.clear();
    await _playAtIndex(_currentIndex);
  }

  Future<void> _playAtIndex(int index) async {
    if (index < 0 || index >= _queue.length) return;
    
    // Increment sessionId inside here to ENSURE every skip/play is a new session
    _playSessionId++; 
    final sessionId = _playSessionId;
    _currentIndex = index;
    final song = _queue[_currentIndex];
    
    notifyListeners(); 
    _saveState();

    try {
      final localPath = await CacheService.getCachedAudioPath(song.id);
      String? uriStr = localPath != null ? 'file://$localPath' : null;

      if (uriStr == null) {
        if (song.streamUrl.isNotEmpty && song.streamUrl.contains('aac.saavncdn.com')) {
          uriStr = song.streamUrl;
        } else {
          debugPrint("Fetching fresh URL for: ${song.title}");
          final freshSong = await _apiService.getSongDetails(song.id, refresh: false);
          
          if (sessionId != _playSessionId) return; 
          
          if (freshSong != null && freshSong.streamUrl.isNotEmpty) {
            _queue[_currentIndex] = freshSong;
            uriStr = freshSong.streamUrl;
          }
        }
      }

      if (uriStr == null || uriStr.isEmpty) {
        debugPrint("Skipping track ${song.title} - No valid URI found.");
        next();
        return;
      }

      if (sessionId != _playSessionId || _isDisposed) return;

      // Serialize teardown to prevent Android MediaCodec dead thread warnings
      // Await full release before creating next codec/player
      if (_player.playing || _player.processingState != ProcessingState.idle) {
        _isPlayerStopping = true;
        await _player.stop();
        _isPlayerStopping = false;
      }

      if (sessionId != _playSessionId || _isDisposed) return;

      final source = AudioSource.uri(
        Uri.parse(uriStr),
        headers: {'User-Agent': 'Mozilla/5.0'},
        tag: MediaItem(
          id: song.id,
          album: song.album,
          title: song.title,
          artist: song.artist,
          artUri: Uri.parse(song.imageUrl),
        ),
      );

      await _player.setAudioSource(source);
      _player.play();
      _apiService.logEvent(song.id, 'play');
    } catch (e) {
      debugPrint("Playback error for ${song.title}: $e");
      if (sessionId == _playSessionId) {
        _handlePlaybackError(PlayerException(0, e.toString()));
      }
    }
  }

  Future<void> _handlePlaybackError(PlayerException e) async {
    if (_currentIndex < 0 || _currentIndex >= _queue.length) return;
    
    // Check if it's a real error or just a cancelled session
    final sessionIdAtError = _playSessionId;
    final song = _queue[_currentIndex];
    
    final msg = e.message?.toLowerCase() ?? '';
    if (msg.contains('abort') || msg.contains('interrupted')) {
      debugPrint("Playback interrupted for ${song.title}, ignoring error.");
      return;
    }

    final retryCount = _retryCounts[song.id] ?? 0;

    if (retryCount < 3) {
      _retryCounts[song.id] = retryCount + 1;
      debugPrint('Retrying ${song.title} (${_retryCounts[song.id]}/3) after error: ${e.message}');
      
      final msg = e.message?.toLowerCase() ?? '';
      final isNetworkError = msg.contains('connection') || msg.contains('http') || msg.contains('network') || msg.contains('timeout');
      
      if (isNetworkError) {
        // Force URL refresh on network error as the link might have expired or be blocked
        final fresh = await _apiService.getSongDetails(song.id, refresh: true);
        if (fresh != null) _queue[_currentIndex] = fresh;
      }

      // Debounce retries with exponential backoff (1s, 2s, 4s) to prevent rapid cycle warnings
      final backoffSeconds = 1 << retryCount; 
      await Future.delayed(Duration(seconds: backoffSeconds));
      
      if (sessionIdAtError == _playSessionId && !_isDisposed && !_isPlayerStopping) {
        await _playAtIndex(_currentIndex);
      }
    } else {
      debugPrint('Max retries reached, skipping ${song.title}.');
      if (_queue.length > 1) {
        next();
      } else {
        await stop();
      }
    }
  }

  void next() {
    if (_currentIndex < _queue.length - 1) {
      _playAtIndex(_currentIndex + 1);
    } else {
      if (_player.loopMode == LoopMode.all) {
        _playAtIndex(0);
      } else {
        stop();
      }
    }
  }

  void previous() {
    if (_player.position.inSeconds > 5) {
      _player.seek(Duration.zero);
    } else if (_currentIndex > 0) {
      _playAtIndex(_currentIndex - 1);
    } else if (_player.loopMode == LoopMode.all && _queue.isNotEmpty) {
      _playAtIndex(_queue.length - 1);
    }
  }

  Future<void> stop() async {
    _isPlayerStopping = true;
    await _player.stop();
    _isPlayerStopping = false;
    notifyListeners();
  }

  Future<void> toggleShuffle() async {
    if (_queue.length < 2) {
      final target = !_player.shuffleModeEnabled;
      await _player.setShuffleModeEnabled(target);
      notifyListeners();
      _saveState();
      return;
    }
    
    final previouslyEnabled = _player.shuffleModeEnabled;
    final currentlyPlaying = currentSong;

    if (!previouslyEnabled) {
      // Enabling shuffle: store current as original, shuffle the active queue
      _originalQueue = List.from(_queue);
      _queue.shuffle();
      if (currentlyPlaying != null) {
        _queue.remove(currentlyPlaying);
        _queue.insert(0, currentlyPlaying);
        _currentIndex = 0;
      }
      await _player.setShuffleModeEnabled(true);
    } else {
      // Disabling shuffle: restore original queue
      if (_originalQueue.isNotEmpty) {
        _queue = List.from(_originalQueue);
        if (currentlyPlaying != null) {
          _currentIndex = _queue.indexWhere((s) => s.id == currentlyPlaying.id);
          if (_currentIndex == -1) _currentIndex = 0;
        }
      }
      await _player.setShuffleModeEnabled(false);
    }
    notifyListeners();
    _saveState();
  }

  Future<void> toggleLoopMode() async {
    final current = _player.loopMode;
    LoopMode next;
    if (current == LoopMode.off) {
      next = LoopMode.all;
    } else if (current == LoopMode.all) {
      next = LoopMode.one;
    } else {
      next = LoopMode.off;
    }
    await _player.setLoopMode(next);
    notifyListeners();
    _saveState();
  }

  Future<void> _saveState() async {
    if (_prefs == null) return;
    await _prefs!.setInt('last_index', _currentIndex);
    await _prefs!.setInt('last_position', _player.position.inMilliseconds);
    await _prefs!.setBool('shuffle_enabled', _player.shuffleModeEnabled);
    await _prefs!.setInt('loop_mode', _player.loopMode.index);
    final queueJson = jsonEncode(_queue.map((s) => s.toJson()).toList());
    await _prefs!.setString('last_queue', queueJson);
  }

  Future<void> _loadState() async {
    if (_prefs == null) return;
    final queueJson = _prefs!.getString('last_queue');
    if (queueJson != null) {
      final List<dynamic> decoded = jsonDecode(queueJson);
      _queue = decoded.map((item) => Song.fromJson(item)).toList();
      _currentIndex = _prefs!.getInt('last_index') ?? 0;
      final lastPos = _prefs!.getInt('last_position') ?? 0;
      final shuffleEnabled = _prefs!.getBool('shuffle_enabled') ?? false;
      final loopModeIndex = _prefs!.getInt('loop_mode') ?? 0;

      await _player.setShuffleModeEnabled(shuffleEnabled);
      await _player.setLoopMode(LoopMode.values[loopModeIndex]);
      
      // Don't auto-play on load, just hydrate if needed
      if (_queue.isNotEmpty && _currentIndex < _queue.length) {
         // Setup the source but don't play
         final song = _queue[_currentIndex];
         final localPath = await CacheService.getCachedAudioPath(song.id);
         String? uriStr = localPath != null ? 'file://$localPath' : (song.streamUrl.isNotEmpty ? song.streamUrl : null);
         
         if (uriStr != null) {
            await _player.setAudioSource(AudioSource.uri(
              Uri.parse(uriStr),
              tag: MediaItem(
                id: song.id,
                album: song.album,
                title: song.title,
                artist: song.artist,
                artUri: Uri.parse(song.imageUrl),
              ),
            ), initialPosition: Duration(milliseconds: lastPos));
         }
      }
    }
  }

  @override
  void dispose() {
    _isDisposed = true;
    _player.dispose();
    super.dispose();
  }
}
