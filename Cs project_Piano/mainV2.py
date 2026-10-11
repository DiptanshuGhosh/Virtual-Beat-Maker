"""
Virtual Piano - mainV2
======================
Upgrades over mainV1 (the original Main.py):

  1. All 88 keys now fit on screen (original was wider than the window, so the
     top octaves were off-screen and octave 7/8 could not be seen).
  2. Crash fix: the original crashed with a ValueError on notes that don't
     exist (e.g. 'C0' or 'D8'). Octaves 0-8 all work now; keys with no note
     are simply ignored, so A0, A#0, B0 and C8 are reachable too.
  3. Real note hold/release: a note lasts while the key is held and fades out
     when released (original cut every sound at a fixed 1-3 seconds).
  4. Sustain pedal on SPACE.
  5. Keys stay lit while held (original only flashed for 30 frames).
  6. Volume control with  -  and  =
  7. Record / play back / save / load a melody (F5 / F6 / F7 / F8).
  8. Works on Windows, Mac and Linux (original used 'Notes\\\\' backslash paths)
     and the logo is loaded once instead of 60 times per second.
  9. Code cleaned up: the 100-line draw_hands() is now a short loop, and
     everything lives in one Piano class.

Run it from anywhere:   python mainV2.py
(It looks for Notes/, fonts and logo.png next to this file or one folder up.)
"""
import os
import pygame
from pygame import mixer
import Piano_List as pl

# low buffer = less delay between key press and sound
mixer.pre_init(44100, -16, 2, 512)
pygame.init()
mixer.set_num_channels(64)

HERE = os.path.dirname(os.path.abspath(__file__))
MELODY_FILE = os.path.join(HERE, 'saved_melody.txt')


def asset(*parts):
    """Find a file next to this script, or one folder up (the repo root)."""
    for base in (HERE, os.path.dirname(HERE)):
        path = os.path.join(base, *parts)
        if os.path.exists(path):
            return path
    return os.path.join(HERE, *parts)


def load_font(name, size):
    try:
        return pygame.font.Font(asset(name), size)
    except (FileNotFoundError, pygame.error):
        return pygame.font.Font(None, size)


def lerp(c1, c2, t):
    """Blend colour c1 -> c2 by t (0..1)."""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


# ---------------------------------------------------------------- constants
FPS = 60
KEY_W = 29                              # width of one white key
N_WHITE = len(pl.white_notes)           # 52
WIDTH = N_WHITE * KEY_W                 # 1508 -> whole keyboard fits
HEIGHT = 400
WHITE_H, BLACK_H, BLACK_W = 300, 200, 19
TOP = HEIGHT - WHITE_H                  # y where the keys start
MIN_OCT, MAX_OCT = 0, 8                 # octave 0 has only A0-B0, octave 8 only C8
RELEASE_MS = 180                        # fade-out when a key is released

WHITE, BLACK = (255, 255, 255), (0, 0, 0)
GREY, DARK_GREY = (128, 128, 128), (70, 70, 70)
GLOW_WHITE, GLOW_BLACK = (110, 225, 150), (30, 150, 80)
RED = (220, 40, 40)
GOLD = (255, 205, 80)

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
# where each semitone of an octave sits (for drawing the hand overlay)
WHITE_POS = {0: 0, 2: 1, 4: 2, 5: 3, 7: 4, 9: 5, 11: 6}
BLACK_POS = {1: 0, 3: 1, 6: 3, 8: 4, 10: 5}   # = index of the white key to its left


class Piano:
    def __init__(self):
        self.screen = pygame.display.set_mode([WIDTH, HEIGHT])
        pygame.display.set_caption('Virtual Piano - V2')
        self.clock = pygame.time.Clock()

        self.title_font = load_font('Angelos.ttf', 45)
        self.help_font = load_font('Terserah.ttf', 16)
        self.small_font = load_font('Terserah.ttf', 16)
        self.tiny_font = load_font('Terserah.ttf', 10)
        try:
            self.logo = pygame.transform.scale(pygame.image.load(asset('logo.png')), [200, 150])
        except (FileNotFoundError, pygame.error):
            self.logo = None

        self.sounds = {}
        self.load_sounds()
        self.build_keys()
        self.build_keymaps()

        self.left_oct, self.right_oct = 4, 5
        self.volume = 0.8
        self.apply_volume()

        self.held = set()        # notes currently pressed
        self.pending = set()     # released but kept ringing by the pedal
        self.channels = {}       # note -> mixer Channel playing it
        self.glow = {}           # note -> 0..1 highlight strength
        self.pressed = {}        # computer key -> note it started (so release matches)
        self.mouse_note = None
        self.pedal_live = False
        self.pedal_play = False
        self.last_note = None

        self.events = []         # recorded melody: (ms, kind, arg)
        self.recording = False
        self.rec_start = 0
        self.playing = False
        self.play_start = 0
        self.play_idx = 0
        self.play_held = set()

        self.message = ''
        self.message_timer = 0

    # ------------------------------------------------------------- set-up
    def load_sounds(self):
        self.screen.fill(GREY)
        txt = self.title_font.render('Loading piano sounds...', True, WHITE)
        self.screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - 25))
        pygame.display.flip()
        for label in pl.white_notes:
            self.sounds[label] = mixer.Sound(asset('Notes', f'{label}.wav'))
        for label, file_name in zip(pl.black_labels, pl.black_notes):
            self.sounds[label] = mixer.Sound(asset('Notes', f'{file_name}.wav'))

    def build_keys(self):
        """One Rect per key, keyed by note label like 'C4' or 'C#4'."""
        self.white_rects, self.black_rects = {}, {}
        for i, label in enumerate(pl.white_notes):
            self.white_rects[label] = pygame.Rect(i * KEY_W, TOP, KEY_W, WHITE_H)
            # a black key sits after every white key except B, E and the last key
            if label[0] not in 'BE' and i < N_WHITE - 1:
                black = f'{label[0]}#{label[1:]}'
                x = (i + 1) * KEY_W - BLACK_W // 2
                self.black_rects[black] = pygame.Rect(x, TOP, BLACK_W, BLACK_H)

    def build_keymaps(self):
        """computer key -> semitone number (0 = C ... 11 = B)."""
        self.left_keys = {pygame.key.key_code(c.lower()): i for i, c in enumerate(pl.left_hand)}
        self.right_keys = {pygame.key.key_code(c.lower()): i for i, c in enumerate(pl.right_hand)}

    # -------------------------------------------------------------- sound
    def apply_volume(self):
        for s in self.sounds.values():
            s.set_volume(self.volume)

    @property
    def sustain(self):
        return self.pedal_live or self.pedal_play

    def fade(self, note, ms):
        ch = self.channels.pop(note, None)
        # only fade if that channel is still playing THIS note
        if ch is not None and ch.get_sound() is self.sounds[note]:
            ch.fadeout(ms)

    def note_on(self, note, record=True):
        self.fade(note, 30)                 # re-pressed note: quickly cut the old one
        ch = self.sounds[note].play()
        if ch is not None:
            self.channels[note] = ch
        self.held.add(note)
        self.pending.discard(note)
        self.glow[note] = 1.0
        self.last_note = note
        if record and self.recording:
            self.log('on', note)

    def note_off(self, note, record=True):
        self.held.discard(note)
        if self.sustain:
            self.pending.add(note)          # pedal down: keep ringing
        else:
            self.fade(note, RELEASE_MS)
        if record and self.recording:
            self.log('off', note)

    def update_sustain(self):
        """Call after the pedal changes; lets go of notes held only by the pedal."""
        if not self.sustain:
            for n in self.pending:
                if n not in self.held:
                    self.fade(n, RELEASE_MS)
            self.pending.clear()

    def set_live_pedal(self, down, record=True):
        self.pedal_live = down
        if record and self.recording:
            self.log('pedal', 'down' if down else 'up')
        self.update_sustain()

    # ---------------------------------------------------- record / playback
    def log(self, kind, arg):
        self.events.append((pygame.time.get_ticks() - self.rec_start, kind, arg))

    def toggle_record(self):
        if not self.recording:
            self.stop_playback()
            self.events = []
            self.rec_start = pygame.time.get_ticks()
            self.recording = True
            self.show('Recording... press F5 to stop')
        else:
            for n in list(self.held):       # close any notes still held
                self.log('off', n)
            self.recording = False
            self.show(f'Recorded {len(self.events)} events - F6 to play, F7 to save')

    def toggle_playback(self):
        if self.playing:
            self.stop_playback()
            return
        if self.recording:
            self.toggle_record()
        if not self.events:
            self.show('Nothing recorded yet (F5 to record, F8 to load)')
            return
        self.playing = True
        self.play_idx = 0
        self.play_start = pygame.time.get_ticks()

    def stop_playback(self):
        if not self.playing:
            return
        self.playing = False
        for n in list(self.play_held):
            self.note_off(n, record=False)
        self.play_held.clear()
        self.pedal_play = False
        self.update_sustain()

    def update_playback(self):
        if not self.playing:
            return
        now = pygame.time.get_ticks() - self.play_start
        while self.play_idx < len(self.events) and self.events[self.play_idx][0] <= now:
            _, kind, arg = self.events[self.play_idx]
            if kind == 'on':
                self.note_on(arg, record=False)
                self.play_held.add(arg)
            elif kind == 'off':
                self.note_off(arg, record=False)
                self.play_held.discard(arg)
            elif kind == 'pedal':
                self.pedal_play = (arg == 'down')
                self.update_sustain()
            self.play_idx += 1
        if self.play_idx >= len(self.events):
            self.stop_playback()

    def save_melody(self):
        if not self.events:
            self.show('Nothing to save - record something first (F5)')
            return
        with open(MELODY_FILE, 'w') as f:
            for t, kind, arg in self.events:
                f.write(f'{t},{kind},{arg}\n')
        self.show(f'Melody saved ({len(self.events)} events)')

    def load_melody(self):
        try:
            loaded = []
            with open(MELODY_FILE) as f:
                for line in f:
                    t, kind, arg = line.strip().split(',')
                    if kind in ('on', 'off') and arg not in self.sounds:
                        raise ValueError(arg)
                    loaded.append((int(t), kind, arg))
        except (OSError, ValueError):
            self.show('No valid saved melody found (record one with F5, save with F7)')
            return
        self.stop_playback()
        self.events = loaded
        self.show(f'Loaded {len(loaded)} events - press F6 to play')

    def show(self, text):
        self.message, self.message_timer = text, FPS * 4

    # ------------------------------------------------------------- events
    def note_at(self, pos):
        for label, rect in self.black_rects.items():    # black keys are on top
            if rect.collidepoint(pos):
                return label
        for label, rect in self.white_rects.items():
            if rect.collidepoint(pos):
                return label
        return None

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            note = self.note_at(e.pos)
            if note:
                self.mouse_note = note
                self.note_on(note)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.mouse_note:
                self.note_off(self.mouse_note)
                self.mouse_note = None
        elif e.type == pygame.KEYDOWN:
            self.key_down(e.key)
        elif e.type == pygame.KEYUP:
            self.key_up(e.key)

    def key_down(self, key):
        if key in self.left_keys:
            self.start_key(key, self.left_oct, self.left_keys[key])
        elif key in self.right_keys:
            self.start_key(key, self.right_oct, self.right_keys[key])
        elif key == pygame.K_UP:
            self.left_oct = min(MAX_OCT, self.left_oct + 1)
        elif key == pygame.K_DOWN:
            self.left_oct = max(MIN_OCT, self.left_oct - 1)
        elif key == pygame.K_RIGHT:
            self.right_oct = min(MAX_OCT, self.right_oct + 1)
        elif key == pygame.K_LEFT:
            self.right_oct = max(MIN_OCT, self.right_oct - 1)
        elif key == pygame.K_SPACE:
            self.set_live_pedal(True)
        elif key == pygame.K_MINUS:
            self.volume = max(0.0, round(self.volume - 0.1, 1))
            self.apply_volume()
        elif key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self.volume = min(1.0, round(self.volume + 0.1, 1))
            self.apply_volume()
        elif key == pygame.K_F5:
            self.toggle_record()
        elif key == pygame.K_F6:
            self.toggle_playback()
        elif key == pygame.K_F7:
            self.save_melody()
        elif key == pygame.K_F8:
            self.load_melody()

    def start_key(self, key, octave, semitone):
        note = f'{NOTE_NAMES[semitone]}{octave}'
        if note not in self.sounds:         # e.g. C0 or D8: not on an 88-key piano
            self.show(f'{note} does not exist (piano goes A0 to C8)')
            return
        self.pressed[key] = note            # remember it, even if the octave changes later
        self.note_on(note)

    def key_up(self, key):
        if key in self.pressed:
            self.note_off(self.pressed.pop(key))
        elif key == pygame.K_SPACE:
            self.set_live_pedal(False)

    # ------------------------------------------------------------ updating
    def update(self):
        self.update_playback()
        for note in list(self.glow):
            if note in self.held:
                self.glow[note] = 1.0
            elif note in self.pending:
                self.glow[note] = max(0.45, self.glow[note] - 0.07)
            else:
                self.glow[note] -= 0.07
                if self.glow[note] <= 0:
                    del self.glow[note]
        if self.message_timer > 0:
            self.message_timer -= 1

    # ------------------------------------------------------------- drawing
    def draw_keys(self):
        for label, rect in self.white_rects.items():
            color = lerp(WHITE, GLOW_WHITE, self.glow.get(label, 0))
            pygame.draw.rect(self.screen, color, rect, 0, 2)
            pygame.draw.rect(self.screen, BLACK, rect, 2, 2)
            text = self.small_font.render(label, True, BLACK)
            self.screen.blit(text, (rect.x + 3, HEIGHT - 20))
        for label, rect in self.black_rects.items():
            color = lerp(BLACK, GLOW_BLACK, self.glow.get(label, 0))
            pygame.draw.rect(self.screen, color, rect, 0, 2)
            text = self.tiny_font.render(label, True, WHITE)
            self.screen.blit(text, (rect.x + 2, HEIGHT - 120))

    def draw_hand(self, octave, keys):
        """Grey strip showing which computer key plays which note of that octave."""
        x0 = ((octave - 1) * 7 + 2) * KEY_W          # x of that octave's C key
        pygame.draw.rect(self.screen, DARK_GREY, [x0, HEIGHT - 60, 7 * KEY_W, 30], 0, 4)
        pygame.draw.rect(self.screen, BLACK, [x0, HEIGHT - 60, 7 * KEY_W, 30], 4, 4)
        for semi, key_label in enumerate(keys):
            if semi in BLACK_POS:
                x, color = x0 + (BLACK_POS[semi] + 1) * KEY_W - 5, GOLD
            else:
                x, color = x0 + WHITE_POS[semi] * KEY_W + 8, WHITE
            self.screen.blit(self.small_font.render(key_label, True, color), (x, HEIGHT - 55))

    def draw_right_aligned(self, text, y, color=BLACK):
        surf = self.help_font.render(text, True, color)
        self.screen.blit(surf, (WIDTH - surf.get_width() - 10, y))
        return surf

    def draw_title_bar(self):
        if self.logo:
            self.screen.blit(self.logo, (-20, -30))
        self.screen.blit(self.title_font.render('Python Programmable Piano!', True, WHITE), (298, 18))
        self.screen.blit(self.title_font.render('Python Programmable Piano!', True, BLACK), (300, 20))

        self.draw_right_aligned('Up/Down: left octave   Left/Right: right octave   Space: sustain', 6)
        self.draw_right_aligned('F5 record   F6 play   F7 save   F8 load   -/= volume', 28)

        parts = [f'Vol {int(self.volume * 100)}%', f'Note {self.last_note or "-"}']
        if self.sustain:
            parts.append('SUSTAIN')
        if self.playing:
            parts.append('PLAYING')
        surf = self.draw_right_aligned('   '.join(parts), 50)
        if self.recording:
            x = WIDTH - surf.get_width() - 70
            pygame.draw.circle(self.screen, RED, (x, 58), 7)
            self.screen.blit(self.help_font.render('REC', True, RED), (x + 12, 50))
        if self.message_timer > 0:
            self.draw_right_aligned(self.message, 72, (20, 20, 120))

    def draw(self):
        self.screen.fill('grey')
        self.draw_keys()
        self.draw_hand(self.left_oct, pl.left_hand)
        self.draw_hand(self.right_oct, pl.right_hand)
        self.draw_title_bar()

    # ------------------------------------------------------------ main loop
    def run(self):
        running = True
        while running:
            self.clock.tick(FPS)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                else:
                    self.handle_event(e)
            self.update()
            self.draw()
            pygame.display.flip()
        pygame.quit()


if __name__ == '__main__':
    Piano().run()